# OpenClaw posture audit: onboarding coverage, capability surface, security

Date: 2026-06-05. Target: `openclaw-vm` (southeastasia), gateway `ghcr.io/openclaw/openclaw:2026.5.28`, agent `azure-oai/gpt-5-mini`, single agent `main`, Telegram bot @savannah_telco_ops_bot.

Method: interrogated the running gateway in-container (`openclaw <cmd>` over `docker compose exec`) as the authoritative source for a weekly-shipping runtime past the training cutoff, cross-checked against version-matched docs (`docs.openclaw.ai`). No config was changed; this is a read-only audit.

## 1. Did skipping `onboard` leave a gap?

`openclaw onboard` has eight stages (derived from its `--skip-*` flags). Coverage of our manual deploy:

| Onboard stage | Covered | By what |
|---|---|---|
| auth + models | yes | `azure-oai` provider, gpt-5-mini + o4-mini |
| gateway (auth/bind/port) | yes | `mode: local`, token auth, loopback bind |
| workspace bootstrap | yes (better) | replaced the generic creature-picker BOOTSTRAP with the Savannah persona files |
| channels | yes | Telegram (pairing DMs, allowlist groups) |
| memory/search embeddings | yes | text-embedding-3-small wired |
| skills | skipped (deliberate) | third-party ClawHub is the guardrail; see section 5 |
| hooks | partial | bundled hooks present, not explicitly enabled |
| web search provider | skipped | none configured |
| daemon install | n/a | we run Docker Compose instead |

Verdict: the load-bearing stages are covered. Crucially, skipping `onboard` did not create the security exposure in section 2. That wide-open tool posture is OpenClaw's default regardless of path, and `onboard` would have left it identical (it gates on an `--accept-risk` acknowledgment precisely because the defaults are powerful). The lever is "harden past the defaults," not "we missed a wizard."

### Empirical confirmation: reference-onboard diff (2026-06-05)

Ran a clean `openclaw onboard` (version 2026.5.28) in an isolated throwaway profile (`docker run --rm -v /tmp/oc-reference:/home/node/.openclaw --entrypoint openclaw <image> onboard --non-interactive --accept-risk --auth-choice skip --skip-daemon --skip-channels --skip-health`) and diffed its generated `openclaw.json` against the live deploy. The reference config is a strict subset of ours. Onboard's defaults that we do NOT have:

- `session.dmScope: "per-channel-peer"` - worth adopting (privacy between DM submitters; also a block-2 recommendation).
- `tools.profile: "coding"` - notable: the vendor default profile is `coding`, not `full`. We run with no profile (= `full`), so our live posture is actually BROADER than a default onboard would produce. Confirms we should set an explicit profile (the which is a block-1 capability decision).
- Minor: `agents.defaults.workspace` explicit path, `skills.install.nodeManager: "npm"`, and an explicit `gateway.auth`/`bind`/`port` block (the reference even wrote a literal gateway token; ours uses the `${OPENCLAW_GATEWAY_TOKEN}` env ref, which is more secure).

Onboard did NOT enable any powerful skill/hook/plugin set in config by default; those stay at runtime defaults, gated later by `agents.defaults.skills`. So there is no hidden "power pack" behind the wizard. Our config additionally carries everything onboard cannot reproduce (the tuned `azure-oai` provider + model params, memory embeddings, Telegram channel + group, the cost-ledger MCP, owner allowlist, and an explicit `update.auto.enabled:false` + `checkOnStart:false` that the reference does not set). Conclusion: skipping `onboard` lost nothing powerful; adopt `session.dmScope` and set an explicit tools profile, and we have matched-or-exceeded the wizard baseline.

## 2. Security audit findings

`openclaw security audit --json`: 0 critical, 2 warn, 1 info.

- Warn 1, trusted proxies: only relevant behind a reverse proxy. We bind loopback with no proxy. Ignore.
- Warn 2 (the real one): because a multi-person Telegram group is allowlisted, the audit flags that the agent runs `sandbox=off`, full `runtime=[exec, process]`, `fs=[read, write, edit, apply_patch]` with `fs.workspaceOnly=false`, and `tools.elevated.enabled=true`.

Supporting facts:

- `openclaw config get tools` returns "not found": we set no tools profile, so we inherit the wide-open default.
- `openclaw exec-policy show`: `security=full, ask=off` (no approval gate). `exec-approvals.json` is missing, no allowlist.
- `openclaw secrets audit`: 4 plaintext secrets at rest. The Azure key sits plaintext in `openclaw.json` and is duplicated in `agents/main/agent/models.json`; plus a stray `codex` provider key and the memory embeddings key.

Docs framing (`docs.openclaw.ai/gateway/security`): a group-reachable, tool-enabled agent means every allowed sender shares the same delegated authority. OpenClaw is explicitly not a hostile multi-tenant boundary. Per-session memory gives privacy between submitters but does not convert a shared agent into per-user host authorization. Real isolation between mutually-untrusted groups needs separate gateways/hosts. For our pilot (one client, semi-trusted field crew, no cross-tenant), tightening the tool surface is the right and sufficient move.

## 3. Surface reality

Corrects the earlier "8 plugins" assumption.

- Plugins: 65/94 enabled, but the bulk are dormant model-provider catalogs (alibaba/openai/mistral/...) that do nothing unless that provider is configured. Capability-granting plugins enabled and unused by a cost bot: `browser`, `canvas`, `phone-control`, `device-pair`, `file-transfer`, `talk-voice`. Keep: `telegram`, `memory-core`, `document-extract` (receipt attachments), `web-readability`.
- Skills: 14/58 "ready", all first-party `openclaw-bundled` / `openclaw-extra` (including the `1password` one named in the malware guardrail, and a `healthcheck` host-hardening skill). These are NOT third-party ClawHub installs, so the guardrail is not currently violated. Lock it forward with `agents.defaults.skills`.
- Hooks: 5/5 bundled ready. `command-logger` (centralized audit file, matches the brief's per-submitter accountability requirement) and `session-memory` (saves context to memory on /new and /reset) are worth enabling. `active-memory` plugin (disabled) does synchronous blocking memory-recall injection (an option; spawns a sub-agent per reply).

## 4. Powerful non-default config levers

Docs-recommended baseline for a group-reachable agent, mapped to our deploy:

```json5
// agents.defaults.tools (single "main" agent)
tools: {
  profile: "messaging",                 // narrow chat-only; vs "coding" / "full"
  fs: { workspaceOnly: true },          // no access to ~/.openclaw or the host
  exec: { security: "deny", ask: "always" },
  elevated: { enabled: false },         // currently true
  // Use group:fs (read+write+edit+apply_patch). NOTE: deny:["write"] does NOT
  // also deny edit/apply_patch, so listing only read+write would leave file
  // mutation open. group:fs is the correct single handle.
  deny: ["group:fs","exec","browser","cron","gateway","sessions_spawn"]
}
```

- `profile: "messaging"` keeps MCP tool calls (cost-ledger) and image input (receipt OCR) working while dropping shell/file/runtime.
- Deny-list semantics (per `gateway/config-tools.md`): `write`, `edit`, and `apply_patch` are separate tool ids; denying `write` alone leaves `edit`/`apply_patch` enabled. To block all file mutation, deny `group:fs` (used above) or list `write`, `edit`, `apply_patch` explicitly.
- Sandbox: `sandbox.mode: "all"` is the heavyweight option but needs nested Docker (docker.sock mounted into the gateway container, not currently mounted, and mounting it is its own risk). Profile + deny gets most of the benefit without it.
- Secrets at rest: move the 4 plaintext keys to SecretRef (`openclaw secrets configure`, `--secret-input-mode ref`) and tighten perms to 600/700.
- Hooks: enable `command-logger` + `session-memory`.
- Manager allowlist: `MANAGER_TELEGRAM_IDS` still blank; only owner `telegram:<OWNER_TELEGRAM_ID>` is privileged.
- Later: `openclaw cron` for scheduled budget digests; `openclaw backup` for state archives.

## 5. Recreating defaults with our own secure standards

- Skills: do not recreate the ClawHub grab-bag. Bundled skills are first-party (guardrail not violated), but lock forward with `agents.defaults.skills` so nothing third-party can creep in. Domain workflows already live in the cost-ledger MCP (financial data stays in our store). If a repeatable workflow emerges, author a first-party skill via the bundled `skill-creator`, never `skills install` from ClawHub.
- Plugins: disable unused capability plugins (`browser`, `canvas`, `phone-control`, `device-pair`, `file-transfer`, `talk-voice`). Keep `telegram`, `memory-core`, `document-extract`, `web-readability`. Provider catalogs are dormant; prune for tidiness only.
- MCP: the `cost-ledger` server is the secure standard (own code, our SQLite store, pinned, registered). Hold new MCP servers to the same bar.

## 6. Posture decision: power first, then secure

Owner direction (2026-06-05): do not strip the deployment to a powerless messaging-only bot. Keep OpenClaw's real capabilities (relevant skills, useful hooks, web search), then secure them, rather than removing them. Reconciliation with the guardrails lives in section 7 of the conversation and the follow-up plan; the non-negotiables stay: zero third-party ClawHub installs (first-party/bundled only), pinned version, dreaming off, financial writes only through the cost-ledger MCP, synchronous cost-entry flow.

## Appendix: capability vs relevance vs risk (for the curated enable list)

| Capability | Power for this bot | Risk | Call |
|---|---|---|---|
| web search (bundled `duckduckgo`, keyless) | look up vendors, answer ops questions | low (read-only, no key) | enable |
| `web-readability` | extract article/page text | low | keep (enabled) |
| `document-extract` | receipts, PDFs | low | keep (enabled) |
| `diagram-maker` skill | render budget/architecture diagrams | low | enable |
| `summarize` skill | summarize docs/links | low | optional enable |
| `command-logger` hook | audit trail (accountability) | low | enable |
| `session-memory` hook | memory persistence on /reset | low | enable |
| `coding-agent` / `oracle` / `spike` skills | dev power | high (exec) | leave off |
| `taskflow` | durable multi-step jobs | conflicts with synchronous-cost-entry guardrail | off for cost path |
| `browser` / `canvas` / `phone-control` / `file-transfer` / `device-pair` | none for a cost bot | high | disable |
