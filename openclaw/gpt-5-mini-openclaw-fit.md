# gpt-5-mini fit for OpenClaw

Does gpt-5-mini cover what the OpenClaw model lineup needs, and what must change on the
client side. Researched 2026-06-04 against primary sources: Microsoft Learn (Azure OpenAI /
AI Foundry) and OpenAI model docs. Azure provisioning of these deployments is done in the
`azure-lab` repo; this doc is the client-side fit reference.

Model: `gpt-5-mini`, version `2025-08-07`, OpenAI format. Deployed GlobalStandard in
`swedencentral` (the only region with deployable interactive gpt-5 quota for this
subscription). Inference support through 2027-02-06.

## Lineup role

gpt-5-mini is the single model for four roles: Telegram chat (Bahasa Indonesia), receipt OCR
(vision), the xlsx + database toolset agent, and the pptx toolset agent. `o4-mini` is the
reasoning escalation for hard analytics; `mistral-document-ai-2512` is the optional dedicated
OCR (needs an AIServices-kind account, the rest are OpenAI-kind).

## Capability checklist

| Capability | Needed for | gpt-5-mini | Verdict |
|---|---|---|---|
| Chat Completions on `openai/v1/` | all roles | supported; no `api-version` param on the v1 path | MET |
| Vision / image input | receipt OCR | PNG/JPEG/WEBP/GIF, URL or base64, up to 512 MB / 1500 images per request | MET |
| Function / tool calling + parallel | agents, MCP cost-ledger | both supported | MET |
| Structured outputs (JSON schema, `strict`) | ledger extraction, agent output | supported (v1 GA) | MET |
| Streaming | responsive chat | supported | MET |
| `reasoning_effort` (minimal/low/medium/high) | analytical queries, agent loops | supported; reasoning tokens billed at output rate | MET |
| Context window | transcripts, multi-tool loops, decks | 400K total (272K input / 128K output) | MET |
| Bahasa Indonesia | chat with the user | strong (GPT-5 family); no official ID benchmark | PARTIAL |
| Knowledge cutoff | minor for a cost bot | 2024-05-31 | MET (note) |
| Pricing (GlobalStandard) | budget | $0.25 input / $0.025 cached / $2.00 output per 1M | MET |

## Required client changes (or requests fail with HTTP 400)

gpt-5-mini is a reasoning-family model and rejects the classic chat params:

1. Use `max_completion_tokens`, not `max_tokens`. `max_tokens` returns 400. (Responses API
   would use `max_output_tokens`, but OpenClaw is on Chat Completions, so
   `max_completion_tokens`.)
2. Remove `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, `logprobs`,
   `logit_bias` entirely. Not "set to default", absent. Any framework that silently injects
   `temperature=1` will break every call. Check the OpenClaw `openclaw.json` model block and
   any client defaults.
3. Structured outputs and parallel tool calls cannot be combined. When the pptx/xlsx agent
   uses `response_format: json_schema` with tools, set `parallel_tool_calls: false`.
4. `reasoning_effort=minimal` disables parallel tool calls. Only relevant if you later add
   minimal-effort fast turns.

## reasoning_effort per role

Reasoning tokens bill at the $2.00/1M output rate, so tune effort by task:

- Chat (Telegram): `low`. Snappy and cheap; Indonesian conversation needs little reasoning.
- xlsx + database agent: `medium`. SQL correctness and tabular logic benefit; watch
  `completion_tokens_details.reasoning_tokens` in the response.
- pptx agent: `low` to `medium`. Structure over deep reasoning.
- Hard analytics: where `o4-mini` (the escalation) or `high` effort earns its cost.

## Caveats

- Indonesian is expected-strong but unverified by any published benchmark; run a quick
  real-receipt test before going live.
- Knowledge cutoff 2024-05-31 is older than full gpt-5 (Sept 2024); fine for a cost bot, a
  limit only if pptx decks need post-May-2024 facts.
- Pricing: the output figure includes hidden reasoning tokens, so a "2K token" answer at
  medium effort can bill as 3-4K. Budget multi-step agents accordingly.

## Sources

- Azure OpenAI reasoning models, GPT-5 series (MS Learn, updated 2026-05-27): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning
- Foundry Models sold by Azure, capability table (MS Learn, 2026-05-19): https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure
- Structured outputs with Azure OpenAI (MS Learn, 2026-05-13): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs
- Vision-enabled chat models on Azure (MS Learn, 2026-04-14): https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/gpt-with-vision
- GPT-5 Mini model page (OpenAI): https://developers.openai.com/api/docs/models/gpt-5-mini

Pricing cross-checked against the OpenAI model card and third-party calculators; confirm on
the Azure pricing portal before budget math.
