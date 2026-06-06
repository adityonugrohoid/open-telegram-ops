"""MCP server exposing the cost ledger to the OpenClaw runtime.

Registers three tools: log_expense, query_spend, budget_status.

Two transports, selected by MCP_TRANSPORT:
  - "stdio" (default): OpenClaw spawns this as a subprocess. Used for the local
    demo (OpenClaw and Python on the same host).
  - "streamable-http": this runs as a standalone sidecar container; OpenClaw
    connects by URL. Used for the 24/7 deployment, so the gateway image stays
    stock and the ledger upgrades independently. See openclaw/DEPLOYMENT.md.

NOTE: the FastMCP wiring follows the current `mcp` Python SDK. Verify against the
installed SDK version on first run; the ledger logic in ledger.py is settled.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from cost_ledger_mcp import ledger

load_dotenv()

DB_PATH = os.environ["COST_LEDGER_DB_PATH"]
PROJECT = os.environ["PROJECT_NAME"]

TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("MCP_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("MCP_HTTP_PORT", "8000"))

mcp = FastMCP("cost-ledger", host=HTTP_HOST, port=HTTP_PORT)


@mcp.tool()
async def log_expense(
    telegram_user_id: int,
    username: str | None,
    amount: int,
    vendor: str | None,
    expense_date: str,
    category: str | None,
    budget_line: str,
    raw_ocr: str | None,
) -> dict[str, object]:
    """Record one confirmed expense (integer rupiah) for the active project.

    Call only after the submitter has confirmed the parsed amount and chosen the
    budget line. expense_date is ISO YYYY-MM-DD.
    """
    expense_id = await ledger.log_expense(
        DB_PATH,
        project=PROJECT,
        telegram_user_id=telegram_user_id,
        username=username,
        amount=amount,
        vendor=vendor,
        expense_date=expense_date,
        category=category,
        budget_line=budget_line,
        raw_ocr=raw_ocr,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"expense_id": expense_id, "status": "logged"}


@mcp.tool()
async def set_budget(name: str, allocated_amount: int) -> dict[str, object]:
    """Create or update a budget line allocation (integer rupiah) for the active
    project. A manager action: define the chart of accounts before expenses are
    logged against it. Idempotent on the line name, so re-calling adjusts the
    allocation in place.
    """
    await ledger.upsert_budget_line(
        DB_PATH, project=PROJECT, name=name, allocated_amount=allocated_amount
    )
    return {"budget_line": name, "allocated_amount": allocated_amount, "status": "set"}


@mcp.tool()
async def query_spend(since: str, until: str) -> dict[str, object]:
    """Return spend for [since, until] (inclusive ISO dates), by budget line and
    by submitter, plus the total, for the active project.
    """
    return await ledger.query_spend(DB_PATH, project=PROJECT, since=since, until=until)


@mcp.tool()
async def budget_status() -> list[dict[str, object]]:
    """Return budget-vs-actual per budget line for the active project."""
    return await ledger.budget_status(DB_PATH, project=PROJECT)


def main() -> None:
    import asyncio

    asyncio.run(ledger.init_db(DB_PATH))
    mcp.run(transport=TRANSPORT)


if __name__ == "__main__":
    main()
