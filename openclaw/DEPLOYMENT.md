# OpenClaw 24/7 deployment (Azure VM + Azure OpenAI)

> **Historical (Azure, decommissioned 2026-06-13).** Describes the retired Azure
> VM + Azure OpenAI deployment, torn down on 2026-06-13. Production moved to the
> `open-claude` repo on AWS. Kept as an archive, not current run instructions.
> The `az group delete` mention below is superseded: see the teardown-status
> section in `AZURE-HANDOFF.md` (`openclaw-rg` must NOT be group-deleted).

Always-on deployment on a persistent Azure Linux VM, with the LLM served by Azure
OpenAI through OpenClaw's built-in OpenAI-compatible provider. The runtime, the
hardening, and the model all sit on one vendor and one credit (the Azure startup
sponsorship). The OpenClaw gateway runs from a pinned image; the delivery-ops MCP
server runs as a separate sidecar container that the gateway reaches over HTTP.

Verified against Azure docs, docs.openclaw.ai, and the OpenClaw repo on 2026-06-04.
Re-confirm the current stable version before pinning (OpenClaw ships multiple
releases per week), and confirm Azure OpenAI pricing on the official page before
budgeting (the figures below are from a secondary source).

## Why Azure + Azure OpenAI

- The Azure sponsorship credit covers both the compute and the LLM. The VM is a
  first-party metered charge (covered). Azure OpenAI is a first-party,
  Microsoft-published Cognitive Services charge, so the USD 1,000 sponsorship
  offsets it automatically. Verify the model's Publisher shows "Microsoft" in AI
  Foundry: partner models routed through Foundry (Anthropic Claude on Azure, some
  Llama/Cohere variants) are Marketplace-billed and the credit does NOT apply.
- We use OpenClaw's built-in `openai` provider pointed at Azure's OpenAI-compatible
  v1 endpoint with a static API key (this is the chosen "Path B"). OpenClaw has no
  first-party Azure provider; the only keyless/managed-identity route is a community
  ClawHub plugin, which conflicts with this project's "no third-party skills" rule.
  Path B keeps us on a first-party OpenClaw provider. The cost is a static Azure
  OpenAI key in `.env` instead of keyless instance auth; we accept and document that.
- There is no one-click OpenClaw image on Azure (confirmed: none exists on Azure
  Marketplace, as a VM image, or a Container Apps template). The path is a plain VM
  plus our compose, which is a clean match for the gateway + sidecar design anyway.

The USD 1,000 Azure sponsorship (expires 2026-07-13) is more than enough for this
workload, so this is a single-vendor deployment with no second-cloud fallback.

## Why a sidecar (the one architecture decision that matters)

A stdio MCP server runs as a child process *inside* the OpenClaw gateway container.
That means a stdio delivery-ops would have to be baked into a custom gateway image and
rebuilt on every ledger change, and it would couple our upgrades to OpenClaw's weekly
releases. Instead we run the delivery-ops MCP server as its own container over
`streamable-http` and point OpenClaw at it by URL. The gateway stays on a stock
pinned image, and the ledger upgrades on its own schedule. The ledger is also
model-agnostic: switching the LLM between Azure OpenAI models (or off Azure entirely)
never touches it.

## Topology

```
host (Azure Linux VM, Docker)
├── openclaw-gateway   pinned image ghcr.io/openclaw/openclaw:<pinned>
│                       Telegram (long-poll, outbound) + agent loop + memory
│                       LLM via Azure OpenAI v1 endpoint over HTTPS,
│                       static key from .env (built-in openai-compatible provider)
│                       port 18789 published on loopback only
│                       --MCP over http--> delivery-ops-mcp:8000/mcp
└── delivery-ops-mcp    our image (deploy/Dockerfile.mcp)
                        streamable-http on :8000, internal network only
                        SQLite at /data (persisted volume)
```

## Model choice (Azure OpenAI)

- Default: `gpt-5-mini` (vision-capable, reasoning-family). Microsoft-published, so
  credit-eligible. It handles chat, typed expense parsing, and inline vision OCR on
  receipt photos. Check current rates on the Azure OpenAI pricing page before sizing.
- Reasoning escalation: `o4-mini` for hard analytics, also Microsoft-published and
  credit-eligible.
- OCR standby: `mistral-document-ai-2512` is a dedicated Foundry OCR API
  (`POST {AZURE_AI_FOUNDRY_ENDPOINT}providers/mistral/azure/ocr`, Bearer auth), NOT a
  chat model, so it is not an OpenClaw provider. It stays provisioned only as a fallback
  for the OCR gate if `gpt-5-mini` underperforms on Indonesian thermal and handwritten
  receipts; wire it out of band (a delivery-ops MCP tool or the standalone harness),
  never as a chat provider.
- Reasoning-family wire format: `gpt-5-mini` and `o4-mini` need `max_completion_tokens`
  (not `max_tokens`) and reject `temperature` / `top_p`. The sample config sets
  `reasoning: true` on each model so OpenClaw emits the correct format automatically.
- Region: Azure OpenAI quota is region- and subscription-specific. This deployment runs
  the models in `swedencentral` because `southeastasia` had zero deployable chat/vision
  quota for the sponsored subscription; the VM sits in `southeastasia` (Singapore) near
  the field crew and calls the swedencentral endpoint over the internet (~190 ms, fine
  for a receipt bot). Azure OpenAI is NOT available in `indonesiacentral` (Jakarta) as
  of mid-2026. Confirm quota with `az cognitiveservices account list-models` first.
- Naming gotcha: Azure calls the *deployment* name, not the base model name. Name your
  deployments exactly `gpt-5-mini` and `o4-mini` so the OpenClaw model id matches the
  deployment.

Model reference format is `<provider-id>/<deployment-name>`, e.g.
`azure-oai/gpt-5-mini` with the provider block from `openclaw.sample.json`.

## Provision Azure (owned by the azure-lab session)

Azure account, billing, provisioning, inventory/cost recording, and teardown for this
deployment are done in the `~/projects/azure-lab` session, per its runbook, not here.
That keeps this project's credit burn tracked against the USD 1,000 sponsorship and
keeps the teardown discipline (`az group delete`) where it belongs. The `az` commands
live in `azure-lab/runbook/README.md` (the OpenClaw cost-bot recipe). This repo only
consumes the result.

What this deployment needs (the spec the azure-lab session fulfills):

- One resource group holding everything, so tear-down is one command.
- An Azure OpenAI resource in `swedencentral` (kind `OpenAI`). Confirm the model
  version, the Global Standard SKU token, and capacity via
  `az cognitiveservices account list-models` before deploying.
- Two Global Standard deployments named exactly `gpt-5-mini` and `o4-mini` (the names
  must match the model ids in `openclaw.sample.json`).
- PTU guard: every deployment must use the `GlobalStandard` SKU (pay-per-token), never
  `GlobalProvisionedManaged` (PTU), which is a fixed hourly throughput reservation that
  bills even at zero traffic (thousands/month). The azure-lab recipe enforces this: it
  pins `--sku-name GlobalStandard`, reads back `sku.name` after create, and deletes the
  deployment if it is anything else. PTU quota on a fresh sponsorship subscription is
  zero, so a PTU deployment also cannot be created without first requesting that quota,
  a second backstop. Confirm the model offers `GlobalStandard` via
  `az cognitiveservices account list-models` before deploying.
- A `Standard_B2s` Ubuntu VM (2 vCPU / 4 GB; the OpenClaw image build wants >= 2 GB),
  with the NSG allowing port 22 only from your own IP and nothing else inbound
  (Telegram is long-poll outbound, so the bot needs no inbound rule).
- A Cost Management budget alert on the subscription.

Handoff back into this repo (carry these by hand; the key never goes through git, a
branch, or a committed file):

| Artifact from azure-lab | Goes into |
|---|---|
| Azure OpenAI endpoint + `/openai/v1/` | `.env` `AZURE_OPENAI_BASE_URL` (the v1 endpoint needs no `api-version` param) |
| Azure OpenAI resource key | `.env` `AZURE_OPENAI_API_KEY` |
| VM public IP + SSH access | the deploy target below |

## Deploy OpenClaw + the delivery-ops sidecar on the VM

With the handoff above in hand, SSH to the VM (`ssh azureuser@<vm-public-ip>`), then:

1. Install Docker + Compose and enable Docker on boot:

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo systemctl enable --now docker
   sudo usermod -aG docker azureuser   # re-login for the group to take effect
   ```

2. Clone the repo and pin the OpenClaw version:

   ```bash
   gh api repos/openclaw/openclaw/releases --jq '[.[] | select(.prerelease==false)][0].tag_name'
   ```

   Set the result in `.env` as `OPENCLAW_IMAGE=ghcr.io/openclaw/openclaw:<version>`.

3. Configure:

   ```bash
   cp .env.example .env
   # Fill: OPENCLAW_GATEWAY_TOKEN (openssl rand -hex 32), TELEGRAM_BOT_TOKEN,
   # PROJECT_NAME, AZURE_OPENAI_API_KEY (key1 from step 3 above),
   # AZURE_OPENAI_BASE_URL (the .../openai/v1/ URL), LLM_MODEL=gpt-5-mini.

   mkdir -p state/openclaw state/openclaw-auth state/ledger
   cp openclaw/openclaw.sample.json state/openclaw/openclaw.json
   ```

   The sample config already carries the `azure-oai` provider block (base URL and key
   come from `.env` via `${...}` interpolation) and sets the model to
   `azure-oai/gpt-5-mini`. Keep the production (`url` / `streamable-http`) MCP block,
   `dreaming.enabled: false`, and the pinned `update` block as-is.

4. Bring it up:

   ```bash
   docker compose up -d --build
   ```

5. Verify:

   ```bash
   curl -fsS http://127.0.0.1:18789/healthz && echo " healthz OK"
   curl -fsS http://127.0.0.1:18789/readyz  && echo " readyz OK"
   docker compose logs -f openclaw-gateway   # watch it connect to the MCP server
   ```

   Message the bot on Telegram and confirm the delivery-ops tools respond.

6. Apply the guardrails from `openclaw/README.md` (pin the version, dreaming off, no
   third-party skills beyond first-party `@openclaw/*` diagnostics, synchronous flows).

## Prerequisites

- An Azure VM with at least 2 GB RAM (the image build wants >= 2 GB; `Standard_B2s` at
  4 GB is comfortable). Only a `Stopped (deallocated)` VM stops billing compute; a
  merely stopped VM still bills, and the managed disk bills regardless of state.
- An Azure OpenAI resource in `swedencentral` with `gpt-5-mini` and `o4-mini`
  deployed (Global Standard), and a key in `.env`.
- Docker + Docker Compose on the VM.
- The repo cloned on the host.
- No sensitive personal data, so data residency is not a hard constraint.

## Hardening on Azure

- Network security group: allow 22 (SSH) only from your own IP, nothing else inbound.
  Telegram is long-poll outbound, so the bot needs no inbound port. Use SSH key auth
  (the `az vm create` above generates keys); disable password auth.
- Encryption at rest: Azure managed disks are encrypted by default with
  platform-managed keys, so the VM disk holding `state/` is encrypted at rest with no
  extra step.
- The static Azure OpenAI key is the one secret on the box. It lives in `.env`
  (gitignored). Rotate with the resource's two-key rotation if it is ever exposed. This
  is the accepted cost of Path B over keyless instance auth.
- `state/`, `secrets/`, and `.env` are gitignored. Never commit them.

## Operations

### Remote access

The gateway port is published on loopback only. Reach it via Tailscale (preferred) or
an SSH tunnel:

```bash
ssh -N -L 18789:127.0.0.1:18789 azureuser@<vm-public-ip>
# then open http://127.0.0.1:18789/ locally
```

The gateway token is required even over a tunnel. Never expose 18789 to the public
internet.

### Telegram needs no inbound port

The Telegram channel uses long polling and dials out to Telegram's API, so the host
does not need a public HTTPS endpoint for the bot to work.

### Upgrades (deliberate, never automatic)

`update.auto.enabled` is false and `checkOnStart` is false in the sample config. To
upgrade: bump `OPENCLAW_IMAGE` to the new pinned tag in `.env`, test in a staging
copy, then `docker compose up -d`. The ledger sidecar upgrades independently with
`docker compose up -d --build delivery-ops-mcp`.

### Health and observability

`/healthz` and `/readyz` need no auth. For metrics, install the first-party plugins:

```bash
openclaw plugins install clawhub:@openclaw/diagnostics-otel
openclaw plugins install clawhub:@openclaw/diagnostics-prometheus
```

Prometheus is at `GET /api/diagnostics/prometheus` and requires the gateway token.
Installing these `@openclaw/*` diagnostics is the one sanctioned exception to "no
third-party skills" (first-party, not community skills).

### Backups

State lives in `state/openclaw`, `state/openclaw-auth`, and `state/ledger`. Back up
all three:

```bash
docker compose stop
tar -czf openclaw-backup-$(date +%Y%m%d).tar.gz state/
docker compose start
```

### Cost watch-outs

- A `Stopped (deallocated)` VM stops compute charges; a merely `Stopped` VM does not.
  Managed disks and any Standard public IP bill regardless of VM state.
- Azure OpenAI: deploy on `GlobalStandard` (pay-per-token), never `GlobalProvisionedManaged`
  (PTU), a fixed hourly reservation that bills at zero traffic. See the PTU guard in the
  provisioning spec above; the azure-lab recipe pins and verifies the SKU.
- Azure budgets notify but do not stop spend. A hard stop needs custom automation
  (an Action Group invoking a Function/runbook that deallocates resources).
- The sponsorship balance is reliable only in the sponsorship portal, not the CLI.
  Check it by hand and log it in `~/projects/azure-lab/credits/azure-sponsorship.md`.
- The credit expiry (2026-07-13) is hard, with no grace assumption. Export anything
  worth keeping and tear the group down before then.

### Security

The gateway writes chat transcripts as plaintext under `state/openclaw`; they will
contain cost figures and vendor names. The VM managed disk is encrypted at rest, so
`state/` is covered. `state/`, `secrets/`, and `.env` are gitignored; never commit them.

## Azure-native alternatives to explore later

Not the v0 path, but worth a spike if the plain VM proves limiting and there is credit
runway to burn:

- Azure Container Apps or Container Instances could host the gateway + sidecar with a
  system-assigned managed identity. That would unlock keyless auth to Azure OpenAI,
  but only through the community `azure-openai` ClawHub plugin, which is the
  third-party dependency Path B deliberately avoids. Treat it as an experiment, not the
  client path.

## Gotcha

- If you point OpenClaw at a stdio delivery-ops using a stock gateway image, it will
  fail to start the MCP server: the stock image does not contain our Python package.
  Either use the sidecar (streamable-http) or build a custom gateway image with the
  package baked in. The sidecar is the supported path here.
- Auth header: Azure's v1 endpoint is designed to accept the standard
  `Authorization: Bearer <key>` that the built-in openai provider sends, so it should
  work unmodified. If Azure returns 401, add an explicit header override to the
  `azure-oai` provider block: `request.headers: { "api-key": "${AZURE_OPENAI_API_KEY}" }`
  (Azure's older surface expects the `api-key` header rather than Bearer).
