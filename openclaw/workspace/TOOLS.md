# TOOLS.md - Local Notes

Environment specifics for Savannah. Config and skills define which tools exist; this file is just notes.

## Cost ledger (MCP server: cost-ledger)

- Reached at `http://cost-ledger-mcp:8000/mcp` (streamable-http sidecar).
- Tools: `log_expense`, `query_spend`, `budget_status`.
- Store: SQLite, scoped by `PROJECT_NAME`. Amounts are integer rupiah.

## Surface

- Telegram (long-poll). Owner: Adityo (telegram:<OWNER_TELEGRAM_ID>).
