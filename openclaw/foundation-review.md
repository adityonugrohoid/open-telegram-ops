# OpenClaw foundation review (block 2: everything except capability selection)

Date: 2026-06-05. Source: live `openclaw-vm`, gateway `2026.5.28`, read-only. Companion to `posture-audit.md` and `capability-audit.md`.

Scope: the operational and security foundation that should be powerful (reliable, observable, recoverable, properly authenticated) and secure regardless of which tools/skills get enabled in block 1. Capability on/off decisions are out of scope here.

Legend: OK = already good, GAP = needs work, MINOR = hygiene.

## Summary table

| # | Dimension | State | Priority |
|---|---|---|---|
| 1 | Control-plane exposure (gateway/dashboard/admin) | OK | - |
| 2 | Container hardening | OK | - |
| 3 | Secrets at rest | GAP | high |
| 4 | Access control / identity | GAP | high |
| 5 | Filesystem + host isolation | GAP | medium |
| 6 | Version lifecycle / pinning | OK (process note) | low |
| 7 | Backups / data durability | GAP | high |
| 8 | Observability / audit | GAP | medium |
| 9 | State hygiene | MINOR | low |
| 10 | Reliability guardrails | OK | low |

---

## 1. Control-plane exposure -- OK

Evidence: gateway is `local`, `ws://127.0.0.1:18789`, auth `token` (from `${OPENCLAW_GATEWAY_TOKEN}` env). Dashboard at `http://127.0.0.1:18789/` is loopback-only; Tailscale off. Compose publishes the port as `127.0.0.1:18789` only. `admin-http-rpc` plugin disabled. SSH is NSG-locked to the VPN egress `<ADMIN_IP>/32`.

Assessment: the control plane is not reachable from the public internet; access requires SSH from the VPN. Good as-is.

Recommendation: keep the port loopback-bound. If you ever need remote Control UI, use Tailscale serve (not a public bind) and set `gateway.trustedProxies`. No change now.

## 2. Container hardening -- OK

Evidence (`docker inspect` + compose): runs as non-root user `node`; `security_opt: no-new-privileges:true`; `cap_drop: [NET_RAW, NET_ADMIN]`; `init: true`; `restart: unless-stopped`; healthcheck on `/healthz`; no Docker socket mounted; sidecar has no published host port (internal `opsnet` only).

Assessment: solid container baseline. The absence of a mounted Docker socket is good security, but it also means `sandbox.mode: "all"` (nested per-session containers) is not available without adding the socket -- and adding it would undo this hardening. So host isolation must come from tool policy, not nested sandboxing (see #5).

Recommendation: do not mount the Docker socket. No change.

## 3. Secrets at rest -- GAP (high)

Evidence:
- `.env` is `600`, state dir `700`, `openclaw.json` `600`, all `*.bak`/`*.last-good` `600`. Good perms.
- `openclaw.json` stores keys as `${AZURE_OPENAI_API_KEY}` etc. (env interpolation, 4 refs). The secrets audit still labels these "plaintext" because they are raw `${ENV}` interpolation, not OpenClaw's managed SecretRef format.
- The real issue: `agents/main/agent/models.json` (auto-generated per-agent registry) holds the **literal** Azure key (`"apiKey": "6IkUiR0..."`, 0 env-refs) and a stray `codex` provider with a literal `"apiKey": "codex-a..."`. We do not use codex; that entry is junk carried in by a default.
- Keys are also present as container env vars (visible via `docker inspect` / `/proc`). This is inherent to env-injection and is the docs-preferred pattern; acceptable.

Assessment: the credential lives plaintext at rest in `models.json` even though `openclaw.json` is ref-based. Anyone who reads that one file (or an unencrypted disk image / backup) gets the key. The codex entry is dead weight that also carries a secret.

Recommendation:
- Convert provider keys to managed SecretRefs: `openclaw secrets configure` then `openclaw secrets reload`, so `models.json` references the env var instead of materializing it.
- Remove the stray `codex` provider from the model registry.
- Confirm full-disk encryption on the VM data disk (Azure: host-level encryption is on by default; verify in the azure-lab session).
- Re-run `openclaw secrets audit` to confirm `plaintext=0` (or only the accepted `${ENV}` interpolation remains).

## 4. Access control / identity -- GAP (high)

Evidence: `dmPolicy: pairing`, `groupPolicy: allowlist`, one allowlisted group `-<GROUP_ID>` with `requireMention:false`. `commands.ownerAllowFrom: ["telegram:<OWNER_TELEGRAM_ID>"]` (owner only). `MANAGER_TELEGRAM_IDS` is blank. Session scope is at defaults (`session.dmScope` unset). The group is a single shared session (`agent:main:telegram:group:-5226...`), so all group members share one conversation context.

Assessment: only the owner is privileged. The persona gates manager queries by prompt, but there is no config-level manager allowlist, so manager authorization currently rests on the model honoring AGENTS.md rather than an enforced boundary. Cross-submitter privacy inside the group is inherently limited (shared session); the real accountability boundary is per-message submitter tagging in our cost-ledger MCP, not session isolation.

Recommendation (this is power + security, not lockdown):
- Define `MANAGER_TELEGRAM_IDS` and wire manager-only commands/queries to it. Enforced authorization beats prompt-only gating for financial reads.
- Keep `query_spend` / `budget_status` enforced at the MCP layer too (defense in depth: the tool itself checks the caller id), so a prompt-injection in the group cannot leak another submitter's data.
- Set `session.dmScope: "per-channel-peer"` explicitly so DM contexts stay per-person.
- Treat the cost-ledger submitter-id tag as the system of record for the accountability trail.

## 5. Filesystem + host isolation -- GAP (medium)

Evidence: `tools.fs.workspaceOnly=false` (security audit), sandbox `mode:off`, `tools` profile unset (= `full`). With sandbox off, `host=auto` resolves to the gateway host, so `read`/`write`/`edit` reach the whole container filesystem including `~/.openclaw` (where credentials and `models.json` live).

Assessment: the filesystem tools can read the agent's own secrets and write anywhere in the container. Nested sandboxing is not available (no Docker socket, #2), so the right lever is filesystem scoping plus tool policy.

Recommendation:
- Set `tools.fs.workspaceOnly: true`. This keeps the fs tools usable for skills (diagrams, summaries) but confines them to the workspace, away from `~/.openclaw` secrets. Power preserved, secret-read path closed.
- The exec stance is a block-1 decision; whatever is chosen there, `workspaceOnly` is worth setting independently.

## 6. Version lifecycle / pinning -- OK (process note)

Evidence: image pinned to `ghcr.io/openclaw/openclaw:2026.5.28`. In-container update channel is `stable`; `openclaw update status` reports `2026.6.1` available. No systemd user services installed (gateway and node services both "not installed"), so nothing auto-updates on a timer. Updates inside the container are non-persistent (image is immutable; a recreate reverts).

Assessment: we are pinned at the image layer, which satisfies the "pin the version, never auto-update the client box" guardrail. The in-container update notice is informational only.

Recommendation: do not run `openclaw update` inside the container. Upgrade by repinning the image tag in `docker-compose.yml` and recreating, after testing in staging. Re-confirm the current stable tag before bumping (OpenClaw ships weekly; `2026.6.1` is now out).

## 7. Backups / data durability -- GAP (high)

Evidence: no backups exist. The cost ledger lives at `state/ledger/cost_ledger.db` (bind mount). `openclaw backup create` exists but nothing is scheduled. State volumes (`state/openclaw`, `state/openclaw-auth`, `state/ledger`) are host bind mounts with no snapshot.

Assessment: the ledger is the asset (the whole point of the repo per CLAUDE.md), and it currently has zero backup. A disk loss or a bad write loses the client's financial record.

Recommendation:
- Cron a nightly job: `openclaw backup create` (config/creds/sessions/workspaces) plus a `sqlite3 .backup` (or file copy under a lock) of `cost_ledger.db`, written to a separate location and ideally off-box (Azure Blob in the same sponsorship subscription).
- Verify with `openclaw backup verify` and a periodic test restore.
- Keep backups `600` and encrypted if off-box.

## 8. Observability / audit -- GAP (medium)

Evidence: logs go to the in-container file log `/tmp/openclaw/openclaw-<date>.log` (richer than `docker compose logs` stdout) and `state/openclaw/logs`. The `command-logger` hook (centralized audit file) is available but not enabled. `diagnostics-otel` plugin available, disabled.

Assessment: there is no durable, centralized audit trail of who asked the agent to do what. For a client deployment with a financial ledger, that is a real gap (and the brief explicitly wants a per-submitter accountability trail).

Recommendation:
- Enable the `command-logger` hook and ship its audit file to the host bind mount so it survives container recreate.
- Ensure the in-container file log is mounted to the host (currently `/tmp` inside the container is ephemeral); point it at `state/openclaw/logs` or a mounted path so logs persist.
- `diagnostics-otel` is optional; only add if you want metrics/traces later.

## 9. State hygiene -- MINOR (low)

Evidence: proliferating config backups (`openclaw.json.bak`, `.bak.1`..`.bak.4`, `.last-good`, plus a `644` world-readable `openclaw.json.commented-bak` -- the obsolete comment-heavy version, which uses `${ENV}` refs so it carries no literal secret). Three group sessions persist including the two removed/deleted groups (`-5294...`, `-5279...`). `workspace`, `memory`, `plugin-skills` dirs are `755` (world-readable on the host).

Recommendation: delete `openclaw.json.commented-bak` (obsolete) and prune `.bak.1`..`.bak.4` (keep `.last-good` + one). Prune stale group sessions. Tighten the `755` dirs to `750` for hygiene (single-user VM, so low urgency).

## 10. Reliability guardrails -- OK (low)

Evidence: dreaming disabled (`memory-core.config.dreaming.enabled=false`, satisfies the guardrail). Heartbeat 30m. A `delivery-queue` dir exists (the async delivery spool tied to issue #89641, where idle async replies are dropped). Cost-entry persona is synchronous by design.

Assessment: compliant. The async-drop issue (#89641) is mitigated by keeping the cost flow synchronous (persona rule), not by relying on the delivery queue.

Recommendation: keep cost-entry synchronous. No change.

---

## Block-2 work order: EXECUTED 2026-06-05

Applied to the live deploy. Pre-flight backup taken first (`state/backups/openclaw.json.pre-block2`, `cost_ledger.db.pre-block2`, `models.json.pre-block2`). One gateway restart applied all config changes; verified healthy and Telegram provider polling after.

1. Secrets - DONE. `secrets audit` is now CLEAN (plaintext=0, unresolved=0, shadowed=0, legacy=0). Ran the interactive `openclaw secrets configure --skip-provider-setup` (TTY, owner-driven) to convert both `openclaw.json` apiKey fields (`models.providers.azure-oai.apiKey`, `agents.defaults.memorySearch.remote.apiKey`) to managed SecretRef objects of the form `{"source":"env","provider":"default","id":"AZURE_OPENAI_API_KEY"}`, then `secrets reload`. A restart regenerated the derived `agents/main/agent/models.json` to match (clearing the `unresolved` note). Regeneration re-injected the `codex` provider with its sentinel apiKey `codex-app-server` (a non-secret constant, not a credential, flagged as a false-positive plaintext); resolved permanently by disabling the unused `codex` + `codex-supervisor` plugins and dropping the provider, so it no longer regenerates. Auth verified intact throughout (`models status` shows azure-oai resolving to the real key); migration ran via hot-swap + restarts with the state volume intact (no recreation; pairing/persona/memory preserved).
2. Backups - DONE (on-box). `/home/azureuser/backup-openclaw.sh` + cron `30 2 * * *`: consistent SQLite ledger snapshot (sqlite backup API) + `openclaw backup create` state archive, both copied out of the containers to `state/backups/`, chmod 600, 14-day retention. Verified one manual run (ledger .db + 762KB state archive). RESIDUAL: off-box replication to Azure Blob (needs a storage account) - deferred.
3. Access control - NOT DONE (needs input). `MANAGER_TELEGRAM_IDS` still blank; MCP-layer manager enforcement is a `cost_ledger_mcp` code change. Awaiting the manager Telegram IDs.
4. `session.dmScope: "per-channel-peer"` - DONE. (Does not change who can DM; only you are paired.)
5. Memory embeddings - DONE. `agents.defaults.memorySearch.model` = `text-embedding-3-large`; `openclaw memory index` rebuilt against 3072 dims (FTS ready, embedding cache enabled; 0 files since no memories saved yet). 3-large endpoint verified reachable (HTTP 200).
6. `tools.profile: "full"` - DONE (explicit).
7. `tools.fs.workspaceOnly: true` - DONE (confirmed in the re-run security audit).
8. Observability - DONE. `command-logger` hook enabled (writes JSONL to `~/.openclaw/logs/commands.log` = host-mounted `state/openclaw/logs/`, persists across recreate; file appears on first command). Side effect: enabling it turned on the internal-hooks category, so `compaction-notifier` was explicitly disabled to avoid posting notices into the client group.
9. Hygiene - DONE. Deleted the obsolete 644 `openclaw.json.commented-bak` and `openclaw.json.bak.1..4`; tightened `workspace`/`memory`/`plugin-skills` to 750; ran `openclaw sessions cleanup`.
10. Lifecycle - confirmed compliant. Live config already carries `update.auto.enabled:false` + `checkOnStart:false`; image pinned. No change.

### Post-execution audit state

`openclaw security audit`: 0 critical, 2 warn (unchanged count). Warn 1 (trusted proxies) is moot on loopback. Warn 2 (multi-user runtime exposure) now reports `fs.workspaceOnly=true` (our change registered); the residual exec/process/elevated/browser exposure it flags is by design - those are block-1 capability decisions (full profile, exec, elevated, browser kept on for power). It will not clear until block-1 narrows capability.
