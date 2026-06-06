# OpenClaw capability audit (full inventory)

Date: 2026-06-05. Source: live gateway `2026.5.28` on `openclaw-vm`, cross-checked with `docs.openclaw.ai`. Started as a read-only inventory; the block-1 review then applied owner decisions live (see section H for the change log). Companion to `posture-audit.md`. Purpose: enumerate every capability lever (tool taxonomy, plugins, skills, hooks, web search, exec policy) so we can decide what to enable with eyes open.

Non-negotiable guardrails that bound every choice below: zero third-party ClawHub installs (first-party/bundled only), pinned version, dreaming off, financial writes only through the cost-ledger MCP, synchronous cost-entry flow.

---

## A. The tool taxonomy (how OpenClaw gates capability)

Capability is gated in five layers (the audit originally said "three"; the runtime doc `gateway/config-tools.md` documents two more that matter for a shared group bot): `tools.profile` sets a base allowlist, then `tools.byProvider` narrows per model/provider, then `tools.allow` / `tools.deny` adjust globally (deny wins), then `tools.toolsBySender` adjusts per requester identity, then sandbox + exec policy constrain what the allowed tools can actually do.

- `tools.toolsBySender` is the lever for our multi-user group: it keys allow/deny on `channel:telegram:<senderId>` (or `"*"` for everyone-else), so the field crew can get a narrow tool set while the owner keeps exec/fs, inside the same single agent and without a second gateway. This is the documented answer to the section-2 warning that "every allowed sender shares the same delegated authority." Carry it into the block-1 decision.
- `tools.byProvider` narrows tools for a specific provider/model (order: base profile -> provider profile -> allow/deny).

### Profiles (`tools.profile`)

| Profile | Tools it enables |
|---|---|
| `minimal` | `session_status` only |
| `messaging` | `group:messaging`, `sessions_list`, `sessions_history`, `sessions_send`, `session_status` |
| `coding` | `group:fs`, `group:runtime`, `group:web`, `group:sessions`, `group:memory`, `cron`, `image`, `image_generate`, `video_generate` |
| `full` | no restrictions (equivalent to unset) -- **this is what we run today** |

### Tool groups

| Group | Individual tools |
|---|---|
| `group:runtime` | `exec`, `process`, `code_execution` (`bash` is an alias for `exec`) |
| `group:fs` | `read`, `write`, `edit`, `apply_patch` |
| `group:sessions` | `sessions_list`, `sessions_history`, `sessions_send`, `sessions_spawn`, `sessions_yield`, `subagents`, `session_status` |
| `group:memory` | `memory_search`, `memory_get` |
| `group:web` | `web_search`, `x_search`, `web_fetch` |
| `group:ui` | `browser`, `canvas` |
| `group:automation` | `heartbeat_respond`, `cron`, `gateway` |
| `group:messaging` | `message` |
| `group:media` | `image`, `image_generate`, `music_generate`, `video_generate`, `tts` |
| `group:nodes` | `nodes` |
| `group:agents` | `agents_list`, `update_plan` |
| `group:openclaw` | all built-in tools (excludes provider/MCP plugins) |
| `group:plugins` | tools owned by loaded plugins and MCP servers (our cost-ledger lands here) |

Key facts (verified against the live 2026.5.28 bundle, 2026-06-05):
- We run `tools.profile: "full"`, set explicitly in block-2 (not inferred from unset). Every tool above is live, including `exec`, `process`, and the `group:fs` mutators.
- `tools.fs.workspaceOnly` is `false` (set 2026-06-05). It was `true` in block-2, then deliberately widened to full container-fs scope for the owner. Safe because the base `tools.deny` removes `group:fs` from everyone and only the owner's `toolsBySender.alsoAllow` re-grants it (fail-safe inversion, below): only the owner can use fs tools, with full `~/.openclaw` reach (config, credentials, logs, memory) via chat; crew have no fs at all. The audit flags `workspaceOnly=false` as its own warn - an accepted owner tradeoff.
- MCP tools (our cost-ledger) are reached via `group:plugins`; under a sandbox you re-permit them with `tools.sandbox.tools.alsoAllow` including `bundle-mcp`.
- Deny semantics footgun (from `config-tools.md`): `deny: ["write"]` does NOT also deny `apply_patch`, and `edit` is its own id. To block file mutation, deny `group:fs` or list `write`, `edit`, `apply_patch` explicitly. The deny list proposed in posture-audit section 4 (`["read","write","exec",...]`) would leave `edit` and `apply_patch` enabled - fix it there before applying.

---

## B. Plugins (65/94 enabled) -- full list by category

### B1. Capability plugins currently ENABLED (these grant real surface now)

Owner decision (2026-06-05): keep all of these ON; revisit per required case. The "Take: disable" suggestions below are deferred, not adopted.

| Plugin | What it does | Relevance to cost bot | Risk | Take |
|---|---|---|---|---|
| `telegram` | the chat channel | core | n/a | keep |
| `memory-core` | memory store + index (dreaming off) | core | low | keep |
| `document-extract` | text + page images from attachments | high (receipts/PDFs) | low | keep |
| `web-readability` | clean article text from fetched HTML | useful with web search | low | keep |
| `browser` | full browser automation | low (DDG covers lookup) | high (drives a real browser) | enable only if web automation is wanted |
| `canvas` | experimental A2UI rendering on paired nodes | none | medium | disable |
| `device-pair` | generate setup codes, approve device pairing | none | medium | disable |
| `phone-control` | arm/disarm phone node camera/screen/writes | none | high | disable |
| `file-transfer` | read/list/write files on paired nodes, base64 to 16MB | none | high (host file exfil path) | disable |
| `talk-voice` | voice selection for Talk | none | low | disable (tidiness) |
| `azure-speech`, `microsoft`, `elevenlabs`, `inworld`, `tts-local-cli` | speech/text-to-speech providers (all enabled) | none (text bot) | low | disable (tidiness) |

### B2. Capability plugins DISABLED but relevant to consider

Owner decision (2026-06-05): the 8 marked **ENABLED** below are now live (verified; total enabled plugins 65 -> 73); `searxng`, the paid-search group, and `active-memory` stay disabled. webhooks added no inbound surface (httpRoutes=0 until a webhook is defined); diagnostics-otel is inert until an OTLP endpoint is set.

| Plugin | What it does | Take |
|---|---|---|
| `duckduckgo` | keyless web search | **ENABLED 2026-06-05** -- live; registers the web_search provider |
| `memory-wiki` | Obsidian-style knowledge vault | **ENABLED 2026-06-05** |
| `llm-task` | JSON-only structured LLM tool for workflows | **ENABLED 2026-06-05** -- structured-output building block |
| `skill-workshop` | capture workflows into workspace skills | **ENABLED 2026-06-05** -- pairs with authoring first-party skills |
| `webhooks` | authenticated inbound webhooks to TaskFlows | **ENABLED 2026-06-05** -- note: adds an inbound HTTP surface, currently unreachable behind the loopback bind |
| `policy` | policy-backed doctor checks for workspace conformance | **ENABLED 2026-06-05** -- low-risk governance/lint add |
| `oc-path` | `oc://` workspace file addressing CLI | **ENABLED 2026-06-05** |
| `diagnostics-otel` | OpenTelemetry metrics/traces export | **ENABLED 2026-06-05** -- inert until an OTLP endpoint is configured |
| `searxng` | self-hosted metasearch (keyless if you host it) | leave disabled; needs a SearXNG instance |
| `exa`, `tavily`, `firecrawl`, `perplexity` | hosted search/crawl | leave disabled; need paid API keys |
| `active-memory` | synchronous blocking memory-recall injection before replies | leave disabled; spawns a sub-agent per reply (latency/cost) |

### B3. Other chat-channel plugins (all disabled, keep disabled)

`signal`, `irc`, `mattermost`, `imessage`, `clickclack` -- we are Telegram-only. No reason to enable.

### B4. Migration / admin plugins (disabled)

`migrate-claude`, `migrate-hermes` (one-time importers), `admin-http-rpc` (HTTP admin surface -- keep disabled, it widens the control plane), `bonjour` (mDNS advertise -- keep disabled), `codex` + `codex-supervisor` (Codex harness), `open-prose`, `workboard`, `thread-ownership` (Slack-specific).

### B5. Model-provider catalogs (dormant unless that provider is configured)

These do nothing without a configured provider/key, so "enabled" here is harmless. They are: `alibaba, anthropic, arcee, byteplus, cerebras, chutes, cloudflare-ai-gateway, comfy, copilot-proxy, deepgram, deepinfra, deepseek, fal, fireworks, github-copilot, google, groq, huggingface, kilocode, kimi, litellm, lmstudio, microsoft-foundry, minimax, mistral, moonshot, nvidia, ollama, opencode, opencode-go, openai, openrouter, qianfan, qwen, runway, senseaudio, sglang, stepfun, synthetic, tencent, together, venice, vercel-ai-gateway, vllm, volcengine, voyage, vydra, xai, xiaomi, zai`. We use a custom `azure-oai` provider, so none of these are load-bearing. Leave as-is (pruning is cosmetic). (`gradium`, a speech provider, is the one such catalog that ships disabled, not enabled.)

---

## C. Skills (15 ready / 43 need setup, 58 total)

All bundled skills are first-party (`openclaw-bundled` / `openclaw-extra`), so their presence does not touch the ClawHub guardrail. A skill is **R (ready/eligible)** when every requirement it declares is met, and **S (needs setup)** when something is `missing`. OpenClaw computes eligibility from exactly four declared requirement kinds: a host CLI binary (`bins`/`anyBins`), an env var/API key (`env`), a config/channel/plugin/skill flag (`config`), or the OS (`os`).

IMPORTANT (verified live 2026-06-05): there is NO `agents.defaults.skills` allowlist and no `skills` config block, and `blockedByAllowlist` is empty for all 58. So `agents.defaults.skills` is a RESTRICT list, not an enable list (unset = all eligible skills active; `[]` = none). All 15 ready skills are ACTIVE for the agent right now - including the exec-heavy dev skills and `taskflow`. Owner decision (2026-06-05): keep all 15 active, no allowlist restriction; review per case (same stance as B1). One standing caveat remains: `taskflow`/`taskflow-inbox-triage` must never carry the receipt/log path (see the synchronous-cost-entry guardrail).

Does enabling the 8 B2 plugins flip any S to R? **No.** Skill setup is host binaries, API keys, OS, or channel/other-plugin/skill flags. None of the 8 B2 plugins (duckduckgo, memory-wiki, llm-task, skill-workshop, webhooks, policy, oc-path, diagnostics-otel) supplies a binary, key, or one of the specific `config` keys an S skill names, so the 14/44 split is unchanged by the B2 decision.

### C-R. Ready and ACTIVE now (15) - all kept active

Owner decision: keep all 15 enabled, revisit per case. The last column flags what to keep an eye on, not what to remove.

| Skill | What it does | Relevance here | Watch / note |
|---|---|---|---|
| `diagram-maker` | SVG/HTML/Excalidraw diagrams | budget/flow visuals | - |
| `skill-creator` | author/validate first-party skills | author our own skills | - |
| `healthcheck` | audit/harden the host (SSH, firewall, updates, gateway) | ops-useful but exec-heavy | owner-only in practice |
| `session-logs` | search own past sessions (`jq`+`rg`) | introspection/debugging | promoted 2026-06-05 |
| `weather` | wttr.in via curl | trivial | - |
| `taskflow` | durable multi-step async jobs | useful for non-cost async work | **keep off the receipt/log path** (synchronous-cost-entry guardrail) |
| `taskflow-inbox-triage` | inbox triage on taskflow | manager-side triage | same async caveat |
| `spike` | throwaway code prototypes | dev | exec-capable |
| `python-debugpy` | Python debugger attach | dev | exec-capable |
| `node-inspect-debugger` | Node inspector debugger | dev | exec-capable |
| `browser-automation` | drive a real browser | web automation | inert unless the `browser` plugin is used |
| `canvas` | A2UI rendering on nodes | low | needs a paired node to render |
| `meme-maker` | image macros | low | - |
| `node-connect` | diagnose device-node pairing | low | no paired nodes today |
| `notion` | Notion read/write | low | inert without a Notion token |

These stay active per the power-first stance. The only behavioral guardrail to enforce is that the receipt/log flow never routes through `taskflow` (async replies get dropped on idle, bug #89641).

### C-S. Need setup (44) - grouped by the kind of setup

**S1. macOS-only - cannot run on this Linux VM (7).** Hard-blocked by `os=darwin`; no setup makes them work here.
`apple-notes` (`memo`), `apple-reminders` (`remindctl`), `bear-notes` (`grizzly`), `things-mac` (`things`), `peekaboo` (`peekaboo`), `imsg` (`imsg`), `model-usage` (`codexbar`, Codex cost logs).

**S2. Need a host CLI binary installed (27).** Each becomes R only if you install the named binary on the VM. The gateway is the stock pinned image running non-root, so durable installs use official static binaries bind-mounted into `/usr/local/bin` via `docker-compose.yml` (see `deploy/bin/fetch-static-bins.sh`), not in-container `apt`. For a Telegram cost bot almost none are relevant; the few that could be are flagged.
- Promoted to R (2026-06-05): `session-logs` (`jq` + `rg`) - both fetched as official static binaries and mounted into the gateway; verified eligible.
- Held as third-party (owner decision, supply-chain): `summarize` (`summarize` - only distributed via a personal Homebrew tap, `steipete/tap/summarize`) and `mcporter` (`mcporter` - npm package). Both useful in principle (summarize pairs with DDG web search; mcporter is MCP admin) but pull unaudited third-party binaries onto the client box, so left off.
- Dev/code (leave off): `tmux` (`tmux`), `oracle` (`oracle`), `gh-issues` (`gh`), `github` (`gh`), `gemini` (`gemini`), `openai-whisper` (`whisper`).
- Not relevant (leave off): `nano-pdf` (`nano-pdf`), `obsidian` (`obsidian`), `himalaya` (`himalaya`), `gog` (`gog`), `gifgrep` (`gifgrep`), `ordercli` (`ordercli`), `wacli` (`wacli`), `xurl` (`xurl`), `songsee` (`songsee`), `sonoscli` (`sonos`), `blucli` (`blu`), `eightctl` (`eightctl`), `openhue` (`openhue`), `camsnap` (`camsnap`), `spotify-player` (`spogo`/`spotify_player`).
- Special: `1password` (`op` - the skill named in the malware guardrail; leave off), `clawhub` (`clawhub` - **never install; this is the ClawHub path the guardrail forbids**).

**S3. Need a CLI binary AND an API key (3).** Leave off.
`goplaces` (`goplaces` + `GOOGLE_PLACES_API_KEY`), `sag` (`sag` + `ELEVENLABS_API_KEY`), `trello` (`jq` + `TRELLO_API_KEY`/`TRELLO_TOKEN`).

**S4. Need only an env var / model dir (2).** Leave off.
`openai-whisper-api` (`OPENAI_API_KEY`), `sherpa-onnx-tts` (`SHERPA_ONNX_RUNTIME_DIR` + `SHERPA_ONNX_MODEL_DIR`).

**S5. Need a channel / plugin / skill config flag, not a host install (4).** These flip to R by editing OpenClaw config, not by installing anything.
`discord` (`channels.discord.token`), `slack` (`channels.slack`), `voice-call` (`plugins.entries.voice-call.enabled`), `coding-agent` (`skills.entries.coding-agent.enabled` plus one of `claude`/`codex`/`opencode`). All leave off (Telegram-only, no dev-in-chat).

---

## D. Hooks (5 bundled; all enabled, 2 inert)

Live state verified 2026-06-05.

| Hook | Fires on | Live state | Note |
|---|---|---|---|
| `command-logger` | every command | **ENABLED** (block-2) | centralized audit file (per-submitter accountability), host-mounted at `~/.openclaw/logs/commands.log` |
| `session-memory` | `/new`, `/reset` | **ENABLED** (block-2) | saves session context to memory on reset; reinforces our memory work |
| `boot-md` | gateway start | enabled by default, **inert** | runs `BOOT.md` if present; we ship none, so it is a no-op until we add one |
| `bootstrap-extra-files` | agent bootstrap | enabled by default, **inert** | injects extra workspace files by glob; none configured, so a no-op |
| `compaction-notifier` | session compaction | **ENABLED** (owner decision 2026-06-05) | posts a visible notice into the Telegram group on every compaction; re-enabled for transparency (was off in block-2 to avoid chatter) |

---

## E. Web search options (ranked for our constraints)

1. `duckduckgo` (bundled plugin): **ENABLED (live 2026-06-05)**. keyless, free, no ClawHub. Registers the `duckduckgo` `web_search` provider (verified active). Best default for power-without-cost.
2. `searxng` (bundled): keyless but you must host a SearXNG instance. More control, more ops.
3. `tavily` / `exa` / `firecrawl` / `perplexity`: higher-quality search/crawl, but each needs a paid third-party API key (not Azure-credit-covered). `firecrawl` also registers a `web_fetch` provider.
4. `web_fetch` + `web-readability`: not search, but fetch-and-extract a known URL into clean text. **Both live (verified 2026-06-05):** `web_fetch` is a built-in tool (`group:web`), active under our `full` profile with no separate enable; the `web-readability` plugin is ENABLED to clean fetched HTML. Pairs with any of the above.

Nuance (verified 2026-06-05): several already-enabled model-provider catalogs also expose a `web_search` provider - `google` (gemini), `xai` (grok), `moonshot` (kimi), `minimax`, `ollama` - but all are dormant without that provider's key, and we run azure-oai only. So `duckduckgo` is the only keyless search we would actually run.

Recommendation stands: start with `duckduckgo` + `web-readability`; revisit a paid provider only if DDG quality is insufficient.

---

## F. Exec policy explained (your "explain this" item)

Exec is governed by three independent knobs plus an approvals file. Today we are at the most permissive setting on all of them.

### F1. `tools.exec.security` -- what is allowed to run

- `deny`: exec is blocked entirely (this is the default *inside a sandbox*).
- `allowlist`: a command runs only if every pipeline segment matches an explicit allowlist entry or a `safeBins` stream filter (`grep`, `sed`, ...). Interpreters (`python3`, `node`, `bash`) are deliberately not safe-bins; you must allowlist them explicitly.
- `full`: any command runs, no restriction (the default for `gateway`/`node` execution). **This is us.**

### F2. `tools.exec.ask` -- whether a human approves

- `off`: no prompt. **This is us** -- exec runs silently.
- `on-miss`: prompt only when a command is not allowlisted.
- `always`: prompt for every command. Approval routes to the owner; the agent waits.

### F3. `tools.exec.host` -- where it runs

- `auto` (default): resolves to `sandbox` when sandboxing is on, else `gateway`. Sandboxing is off by default, so `auto` means "on the gateway host." **This is us.**
- `sandbox` / `gateway` / `node`: explicit. Not a hostname selector.

### F4. `exec-approvals.json` and elevated

- The host approvals file is the enforceable source of truth; the requested `tools.exec` policy can narrow or broaden intent, but the effective result is derived from the host rules. Our approvals file is **missing**, so the effective policy falls to the requested defaults (`full`/`off`) and nothing narrows `full`.
- `tools.elevated.enabled` is `true` by **default** (not set in our config; `config get tools.elevated` returns "not found", but the security audit reports it enabled). Elevated exec bypasses the sandbox onto the host escape path and forces `security=full`. `tools.elevated.allowFrom` can scope it by channel/user; per-session `/elevated on|off|ask|full` toggles it.

### F4b. `askFallback` (security-material, was missing here)

`askFallback` (live: `full`) governs what happens when an approval **cannot be obtained** (no operator reachable, channel offline). Default `full` means "allow the command anyway." So `ask=always` is only as strong as `askFallback`: with `askFallback=full`, an undeliverable approval silently runs. Any owner-gated posture must set `askFallback` (to `deny`) as well, or the gate has a hole.

### F5. Presets (`openclaw exec-policy preset`)

- `yolo`: `security=full`, `ask=off` (today's effective state).
- `cautious`: tightened (allowlist + prompting).
- `deny-all`: exec blocked.

### F6. What each choice means for us

| Choice | Config | Effect | Who can trigger shell |
|---|---|---|---|
| Keep full (current) | `security=full, ask=off` | any command runs silently | any allowed group sender, no gate |
| Owner-gated | `security=full, ask=always`, `elevated=false` | exec available, but every command waits for your approval | only with your per-command approval |
| Allowlist | `security=allowlist, ask=on-miss` | only pre-approved commands run unattended | bounded to the allowlist |
| Deny | `security=deny` or `deny:[group:runtime]` | no shell at all | nobody |

The trade is power vs. who holds the trigger. "Owner-gated" keeps the capability fully intact (any command is still possible) while removing the silent-shell-for-any-group-member exposure. "Deny" is simplest but breaks exec-dependent skills (coding-agent, healthcheck, spike).

How to apply (durable, synchronized): use `openclaw exec-policy set --host gateway --security <s> --ask <a> --ask-fallback <f>` or a `preset` (yolo/cautious/deny-all). These write both the config and the enforceable host approvals file together; a raw `config set tools.exec.*` can leave the approvals file out of step. For owner-gated, that is `--security full --ask always --ask-fallback deny`.

Power-preserving alternative (pairs with task #13): keep exec `full`/`off` for the owner but use `tools.toolsBySender` to `deny: ["group:runtime"]` for non-owner senders. This removes the group-member shell exposure without weakening the owner's capability or touching the exec policy globally. Decision tracked as task #18.

---

## G. Memory / embeddings

Decided (2026-06-05, azure-lab audit) and APPLIED (block-2 execution): switched to `text-embedding-3-large` (3072 dims, better multilingual recall for Bahasa content, Microsoft-published so credit-covered). The `text-embedding-3-small` deployment was deleted. `agents.defaults.memorySearch.model` now points at `text-embedding-3-large`; `openclaw memory index` rebuilt against 3072 dims; endpoint verified reachable (HTTP 200). Memory embedding is functional again.

---

## H. Applied changes (block-1 review, 2026-06-05)

This started as inventory only; the block-1 review then applied the owner's decisions live on the VM. State as of 2026-06-05:

- **A (tool taxonomy):** corrected the doc (five gating layers, `group:openclaw`, deny-list semantics). `tools.profile: "full"` from block-2. `tools.fs.workspaceOnly` flipped `true` -> `false` on 2026-06-05 (full container-fs scope for the owner; safe because crew are denied `group:fs` via `toolsBySender`). Backup: `state/backups/openclaw.json.pre-fsscope`.
- **B1 (capability plugins):** kept all enabled, revisit per case (owner decision, no change).
- **B2 (disabled-but-relevant):** enabled 8 - `duckduckgo`, `memory-wiki`, `llm-task`, `skill-workshop`, `webhooks`, `policy`, `oc-path`, `diagnostics-otel`. Enabled plugin count 65 -> 73. `searxng`, paid-search group, `active-memory` left off.
- **C (skills):** all 15 ready skills kept active, no allowlist (owner decision). `session-logs` promoted to R by mounting official static `jq`+`rg` into the gateway (`deploy/bin/` + `docker-compose.yml`). Standing rule: receipt/log path must never route through `taskflow`.
- **D (hooks):** all 5 now enabled - `compaction-notifier` re-enabled (group transparency); `command-logger` + `session-memory` already on; `boot-md` + `bootstrap-extra-files` on but inert.
- **E (web search):** `duckduckgo` web_search live; `web-readability` + built-in `web_fetch` active.
- **F (exec policy):** reviewed 2026-06-05; doc corrected (added `askFallback`, source-of-truth nuance, `exec-policy set`). Global exec left at the `yolo` posture for the owner; crew exec exposure closed via `toolsBySender` (below) rather than a global exec-policy change. Tasks #18 + #13 done.
- **owner/crew split (A/F, applied 2026-06-05, then inverted to fail-safe):** final config is base `tools.deny: ["group:runtime","group:fs","browser","canvas","cron","gateway","sessions_spawn"]` (restricts everyone, keeps MCP + image + messaging for crew) plus `toolsBySender: { "id:<OWNER_TELEGRAM_ID>": { alsoAllow: [same list] } }` (re-grants full power to the owner only). Mechanism: "deny wins within a layer, most specific wins across layers" - a per-sender `alsoAllow` overrides the broader `deny` (documented in `channels/groups.md`). This is fail-safe: an unmatched sender lands on the restricted base, not full. After the inversion the security audit reports "No unguarded runtime/process tools / filesystem contexts detected" - the real crew-shell exposure is resolved (the residual multi-user warn is now the informational group-reachability heuristic only). Backups: `state/backups/openclaw.json.pre-toolsbysender`, `.pre-inversion`.
- **fs scope:** `tools.fs.workspaceOnly=false` (owner full container-fs; crew have no fs). The audit flags this as its own warn ("dangerous config flag") - an accepted owner tradeoff, independent of the inversion.

Remaining block-1: none requiring owner input. Posture: 0 critical, 3 warn (reverse-proxy N/A on loopback; `workspaceOnly=false` accepted; multi-user heuristic informational).
