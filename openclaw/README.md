# OpenClaw runtime

> **Historical (Azure, decommissioned 2026-06-13).** The Azure runbooks below
> (`DEPLOYMENT.md`, `AZURE-HANDOFF.md`) describe the retired deployment, torn down
> on 2026-06-13. Production moved to the `open-claude` repo on AWS.

OpenClaw is the agent runtime: Telegram channel, conversation memory, and the LLM
loop. It is installed and pinned separately from this repo (we do not vendor it).
This directory holds the config sample and the runbooks for wiring it to our
delivery-ops MCP server.

- [INSTALL.md](INSTALL.md) - local / demo install (OpenClaw + stdio MCP on one host).
- [DEPLOYMENT.md](DEPLOYMENT.md) - 24/7 deployment (Docker, delivery-ops as an HTTP sidecar).
- [openclaw.sample.json](openclaw.sample.json) - config to copy into the state dir.

## Why OpenClaw, and the guardrails

Verified June 2026: OpenClaw is MIT-licensed (maintained by the OpenClaw
Foundation; no OpenAI sponsorship confirmed, earlier notes overstated this),
official Telegram Bot API via grammY (no Baileys ban risk), mature MCP client.
Maturity is pilot-ready, not enterprise-production-ready. Non-negotiable guardrails
for a client deployment:

- **Pin the version.** It ships breaking config changes weekly. Never auto-update
  the client box (`update.auto.enabled: false`, `checkOnStart: false`). Upgrade in
  staging only, then promote.
- **No third-party ClawHub skills.** Own code only (documented supply-chain malware
  history, 1Password, early 2026). The only sanctioned installs are first-party
  `@openclaw/*` diagnostics plugins (OTel, Prometheus).
- **Disable the "dreaming" memory pipeline** (`plugins.entries.memory-core.config.dreaming.enabled: false`)
  until upstream #89444 is fixed (it writes junk into MEMORY.md).
- **Keep cost-entry flows synchronous** (reply in the same turn). OpenClaw drops
  async background replies on idle sessions (upstream #89641).

## MCP wiring (two modes)

- **Local / demo:** stdio. OpenClaw spawns `python -m delivery_ops_mcp.server` as a
  subprocess on the same host.
- **Production:** streamable-http. The delivery-ops runs as its own sidecar
  container; OpenClaw connects to `http://delivery-ops-mcp:8000/mcp`. The gateway
  stays on the stock pinned image. See DEPLOYMENT.md for why.

Restrict the agent to the three delivery-ops tools (`log_expense`, `query_spend`,
`budget_status`) plus the built-ins it needs. Do not expose `exec`/`browser` to a
cost-entry agent.

## LLM provider

- Azure OpenAI via OpenClaw's built-in OpenAI-compatible provider (Path B). Set a
  custom `azure-oai` provider in `openclaw.json` (already in the sample) with the
  Azure v1 base URL and a static key from `.env`, and use model ref
  `azure-oai/gpt-5-mini` (default chat plus inline vision OCR; `azure-oai/o4-mini` for
  reasoning escalation).
- OpenClaw has no first-party Azure provider; the only keyless route is a community
  ClawHub plugin, which the no-third-party-skills rule rules out. We accept a static
  Azure OpenAI key in `.env` as the trade. The credit covers Microsoft-published models
  only (the gpt-5 and o-series families), not Marketplace partner models, so Mistral
  Document AI is provisioned only as a standby for the OCR gate. See DEPLOYMENT.md.

## TODO before the pilot

- Pin the exact OpenClaw version and record it in `.env` (`OPENCLAW_IMAGE`).
- Hosting: Azure Linux VM (`southeastasia`) + Azure OpenAI on the startup
  sponsorship credit (expires 2026-07-13). See DEPLOYMENT.md.
- Write the agent system prompt: confirm-before-commit flow, budget-line buttons,
  manager-command allowlist.
