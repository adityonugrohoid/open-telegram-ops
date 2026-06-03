# gpt-5-mini handoff note

Action items for wiring OpenClaw to the `gpt-5-mini` deployment (swedencentral, GlobalStandard,
OpenAI-compatible `openai/v1/` endpoint). Full capability analysis is in
`gpt-5-mini-openclaw-fit.md`.

## Required changes on the OpenClaw side (or requests 400)

These are real integration gaps, because gpt-5-mini is a reasoning-family model and rejects
the classic chat params:

1. Use `max_completion_tokens`, not `max_tokens`. `max_tokens` returns 400. (Responses API
   would use `max_output_tokens`, but OpenClaw is on Chat Completions, so
   `max_completion_tokens`.)
2. Remove `temperature`, `top_p`, `presence_penalty`, `frequency_penalty`, `logprobs`,
   `logit_bias` entirely. Not "set to default", absent. Any framework that silently injects
   `temperature=1` will break every call. The OpenClaw `openclaw.json` model block and any
   client defaults must be checked.
3. Structured outputs and parallel tool calls cannot be combined. When the pptx/xlsx agent
   uses `response_format: json_schema` with tools, set `parallel_tool_calls: false`.
4. `reasoning_effort=minimal` disables parallel tool calls. Only relevant if you later add
   minimal-effort fast turns.

## Recommended reasoning_effort per role

Since reasoning tokens bill at the $2.00/1M output rate, tune effort by task:

- Chat (Telegram): `low`. Snappy, cheap, Indonesian conversation needs little reasoning.
- xlsx + database agent: `medium`. SQL correctness and tabular logic benefit; watch
  `completion_tokens_details.reasoning_tokens`.
- pptx agent: `low` to `medium`. Structure over deep reasoning.
- Hard analytics: this is where `o4-mini` (the escalation) or `high` effort earns its cost.

## Caveats to log

- Indonesian is expected-strong but unverified by any published benchmark; worth a quick
  real-receipt test before going live.
- Knowledge cutoff 2024-05-31 is older than full gpt-5 (Sept 2024); fine for a cost bot, a
  limit only if pptx decks need post-May-2024 facts.
- Pricing: output figure includes hidden reasoning tokens, so a "2K token" answer at medium
  effort can bill as 3-4K. Budget multi-step agents accordingly.
