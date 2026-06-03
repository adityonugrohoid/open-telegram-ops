# open-telegram-ops

Conversational job-costing for a telecom subcontractor: a field worker snaps a receipt photo in Telegram, an agent reads it, attributes it to a budget line, logs it to a cost ledger, and managers get live budget-vs-actual visibility with a per-submitter accountability trail.

This is the first of several planned internal agents for one client. Demo first, with a path to a real running tool.

## What this repo is (and is not)

This repo owns two things:

- `cost_ledger_mcp/` - a custom MCP server that is the durable, swappable domain layer: the SQLite cost ledger, attribution, and reporting. This is the asset. The client's financial data lives here, in our controlled store, never inside OpenClaw's plaintext transcripts. It serves over two transports (one env var, `MCP_TRANSPORT`): stdio for the local demo, streamable-http for the 24/7 sidecar.
- `openclaw/` - config sample and runbooks for the OpenClaw runtime that provides Telegram, conversation memory, and the agent loop. OpenClaw is installed and pinned separately (see `openclaw/INSTALL.md` and `openclaw/DEPLOYMENT.md`); we do not vendor it.

Decoupling is deliberate: if OpenClaw proves too unstable, the runtime is swappable without touching the ledger or the MCP contract.

## Deployment topology

- **Demo:** OpenClaw on a laptop (npm, pinned) + the MCP server over stdio on the same host. See `openclaw/INSTALL.md`.
- **24/7:** Docker Compose (`docker-compose.yml`). The OpenClaw gateway runs from the stock pinned image; the cost-ledger MCP server runs as its own sidecar container over streamable-http, reached at `http://cost-ledger-mcp:8000/mcp`. See `openclaw/DEPLOYMENT.md`.

A stdio MCP server runs *inside* the gateway container, so a stdio ledger would have to be baked into a custom gateway image and rebuilt on every change. The HTTP sidecar avoids that and keeps the ledger upgradeable on its own schedule. Pinned image at verification time: `ghcr.io/openclaw/openclaw:2026.5.28` (re-confirm current stable before pinning; OpenClaw ships weekly).

## Stack

| Component | Choice |
|-----------|--------|
| Agent runtime | OpenClaw (self-hosted, Docker, pinned version), Telegram via grammY |
| Domain layer | Python 3.12+ stdio MCP server (`mcp` SDK) |
| LLM | Azure OpenAI: gpt-5-mini chat + inline vision OCR, o4-mini reasoning escalation; Mistral Document AI on standby for the OCR gate |
| Data | SQLite (via `aiosqlite`) |
| Charts | matplotlib (PNG, sent in-chat) |

LLM runs on **Azure OpenAI** via OpenClaw's built-in OpenAI-compatible provider (Path B): a custom `azure-oai` provider in `openclaw.json` pointed at the Azure v1 endpoint (`.../openai/v1/`) with a static key from `.env` (`AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_BASE_URL`), model refs `azure-oai/gpt-5-mini` (default chat plus inline vision OCR) and `azure-oai/o4-mini` (reasoning escalation). OpenClaw has no first-party Azure provider and the no-third-party-skills rule rules out the community keyless plugin, so a static key is the accepted trade. Host and model bill to the **Azure startup sponsorship** credit (subscription `<AZURE_SUBSCRIPTION_ID>`, the sponsorship tenant; expires 2026-07-13). Credit covers Microsoft-published models only (the gpt-5 and o-series families), not Marketplace partner models, so Mistral Document AI is provisioned only as a standby for the OCR gate, never wired as a chat provider. See `~/projects/azure-lab` for account/billing ops. This stays clear of every frozen GCP resource.

## Directory structure and entry points

```
open-telegram-ops/
├── cost_ledger_mcp/
│   ├── server.py        # entry point: MCP server (stdio or streamable-http), 3 tools
│   ├── ledger.py        # SQLite schema + async read/write
│   └── reports.py       # text summary + matplotlib chart rendering
├── openclaw/
│   ├── README.md        # runtime overview + guardrails + MCP wiring (index)
│   ├── INSTALL.md       # local / demo install
│   ├── DEPLOYMENT.md    # 24/7 Docker deployment (sidecar topology)
│   └── openclaw.sample.json  # config to copy into the OpenClaw state dir
├── deploy/
│   └── Dockerfile.mcp   # builds the cost-ledger MCP sidecar image
├── docker-compose.yml   # gateway (stock image) + cost-ledger-mcp sidecar
├── scripts/ocr_test/
│   ├── run_ocr_test.py  # the mandatory pre-build OCR accuracy harness
│   └── README.md        # the 10-receipt test protocol and pass/fail thresholds
├── data/                # local runtime: SQLite DB, receipts, charts (gitignored)
├── state/               # deploy runtime: OpenClaw + ledger volumes (gitignored)
└── tests/
```

The three MCP tools (the contract OpenClaw calls): `log_expense`, `query_spend`, `budget_status`.

## Dev commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the cost-ledger MCP server over stdio (OpenClaw launches it this way)
python -m cost_ledger_mcp.server

# Run the mandatory OCR accuracy test (see the gate below)
python scripts/ocr_test/run_ocr_test.py

# Tests
python -m pytest tests/ -v
```

## The OCR gate (do this before building features)

idea-validator (verdict: BUILD) flagged OCR accuracy on Indonesian thermal/handwritten field receipts as the one kill-shot risk, and there is no published Bahasa OCR benchmark. Before writing the bot flows, run `scripts/ocr_test/run_ocr_test.py` on 10 real field receipts and measure amount-parse accuracy:

- `>80%` amount accuracy: ship as designed.
- `60-70%`: design the confirm-before-commit UX around correction being the expected case, not the edge.
- `<60%` on amounts: defer, or go hybrid (ask the worker to type the amount when model confidence is low).

Confirm-before-commit (echo parsed values, ask for the budget line via inline-keyboard buttons) is in scope regardless. It is the correct mitigation for any OCR pipeline.

## Conventions

- Python 3.12+, async for all I/O, type hints on every function signature.
- Never use silent fallbacks. Raise explicit errors with context. No bare `except`/`pass`.
- No default parameter values that hide complexity. Required params stay explicit.
- Minimal changes scoped to the request. Do not add abstractions that were not asked for.
- `.env` for secrets, always gitignored. `.env.example` is the template. Never commit `.env`, keys, or the OpenClaw state dir.

## OpenClaw guardrails (non-negotiable for a client deployment)

- Pin the OpenClaw version. Never auto-update the client box; it ships breaking config changes weekly. Upgrade in staging only.
- Install zero third-party ClawHub skills. Own code only. ClawHub has a documented supply-chain malware history (1Password, early 2026).
- Disable the "dreaming" memory pipeline until issue #89444 is fixed (it writes junk into long-term memory).
- Keep cost-entry flows fully synchronous (reply in the same turn). OpenClaw drops async background replies when a session is idle (issue #89641).

## Open questions (from the BRIEF, still to decide)

- Budget structure: the client's chart of accounts / cost categories per project.
- Roles and counts: how many field submitters vs managers in the pilot.
- Receipt samples: language mix and format (thermal, handwritten) for the OCR gate.
- Hosting: Azure Linux VM (`southeastasia`) + Azure OpenAI on the startup sponsorship credit (decided; expires 2026-07-13). No sensitive personal data, so residency is not a hard constraint.
- Whether to spike the Azure Container Apps + managed-identity keyless path before the credit expires (would need the community azure-openai plugin; out of scope for v0).
- Demo deadline.
- Locked-before-build: who may run manager query commands (`MANAGER_TELEGRAM_IDS` allowlist vs open to any user).

## Git workflow

Feature branches (`feat/`, `fix/`, `docs/`, `chore/`). Conventional commits. Solo author, no Co-Authored-By trailer. Do not commit directly to main except this initial scaffold. The first `git push -u origin main` is done by hand outside an assistant session.
