"""Delivery-ops MCP server: the durable domain layer for open-telegram-ops.

Owns the SQLite delivery-ops ledger, expense attribution, and reporting. Exposed to the
OpenClaw runtime over stdio as three tools: log_expense, query_spend,
budget_status. The agent runtime is swappable; this layer and its data are not.
"""
