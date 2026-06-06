# OpenClaw install (local / demo)

This is the fast path for the demo: OpenClaw on your laptop, the delivery-ops MCP
server running on the same host over stdio. For the always-on deployment, see
[DEPLOYMENT.md](DEPLOYMENT.md).

All commands and config keys here were verified against docs.openclaw.ai and the
repo on 2026-06-03. OpenClaw ships multiple releases per week, so step 1 is to
re-confirm the current stable version before pinning.

## 0. Prerequisites

- Node 22.19+ (Node 24 recommended)
- Python 3.12+ (for the MCP server)
- A Telegram bot token from @BotFather
- An Azure OpenAI resource with a `gpt-5-mini` deployment (vision-capable), plus
  its key and `.../openai/v1/` base URL

## 1. Confirm the current stable version (do not skip)

```bash
gh api repos/openclaw/openclaw/releases --jq '[.[] | select(.prerelease==false)][0].tag_name'
```

At verification time the latest stable was `v2026.5.28`. Use whatever that command
returns now, and pin to it. Do not install `@latest` on a machine you will demo on.

## 2. Install OpenClaw, pinned

```bash
npm install -g openclaw@2026.5.28      # use the version from step 1
openclaw onboard                        # interactive onboarding
```

(`openclaw onboard --install-daemon` installs it as a background systemd user
service. For a laptop demo you can skip the daemon and run the gateway in the
foreground.)

## 3. Install the delivery-ops MCP server deps

From the repo root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Confirm it runs over stdio:

```bash
COST_LEDGER_DB_PATH=data/cost_ledger.db PROJECT_NAME=demo python -m delivery_ops_mcp.server
```

(It will wait on stdio; Ctrl-C to stop. OpenClaw will launch it the same way.)

## 4. Configure OpenClaw

Copy the sample config into your OpenClaw state dir and switch the MCP server to
the stdio (local) block:

```bash
cp openclaw/openclaw.sample.json ~/.openclaw/openclaw.json
```

Edit `~/.openclaw/openclaw.json`: comment out the `url`/`streamable-http` block and
uncomment the `command`/`stdio` block (it points at `python -m delivery_ops_mcp.server`).
Set `cwd` to the repo path and make sure the venv's `python` is on PATH, or use the
venv's absolute python in `command`. Keep the `azure-oai` provider block,
`dreaming.enabled: false`, and the pinned `update` block as-is.

Set the env the gateway needs (the `azure-oai` provider reads the two Azure vars via
`${...}` interpolation):

```bash
export TELEGRAM_BOT_TOKEN=...        # from @BotFather
export AZURE_OPENAI_API_KEY=...      # Azure OpenAI resource key
export AZURE_OPENAI_BASE_URL=https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1/
export COST_LEDGER_DB_PATH=data/cost_ledger.db
export PROJECT_NAME=<pilot-project>
```

## 5. Start and verify

```bash
openclaw gateway start         # or run `openclaw` in the foreground
curl -fsS http://127.0.0.1:18789/healthz && echo OK
```

Message your bot on Telegram. The agent should answer and have the three
delivery-ops tools available.

## Before the demo

Run the OCR accuracy gate first (`scripts/ocr_test/`). It decides how heavily the
confirm-before-commit flow leans on correction. Do not build the receipt flow
until that test has been run on real client receipts.
