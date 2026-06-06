"""Seed budget lines (the client's chart of accounts) into the delivery-ops ledger.

Reads a JSON array of {"name": str, "allocated_amount": int} and upserts each
line for PROJECT_NAME into DELIVERY_OPS_DB_PATH. Idempotent: re-running updates
allocations in place. Run this before the bot logs any expense, since log_expense
rejects spend against an undefined budget line.

Usage (run as a module from the repo root so delivery_ops_mcp is importable):
    DELIVERY_OPS_DB_PATH=data/delivery_ops.db PROJECT_NAME=pilot \\
        python -m scripts.seed_budget scripts/budget_lines.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from delivery_ops_mcp import ledger

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger("seed_budget")


async def seed(db_path: str, project: str, lines: list[dict[str, object]]) -> int:
    """Upsert each budget line for the project. Returns the count seeded."""
    await ledger.init_db(db_path)
    for line in lines:
        name = line.get("name")
        allocated = line.get("allocated_amount")
        if not isinstance(name, str) or isinstance(allocated, bool) or not isinstance(allocated, int):
            raise ValueError(
                "each line needs a string 'name' and an integer 'allocated_amount', "
                f"got {line!r}"
            )
        await ledger.upsert_budget_line(
            db_path, project=project, name=name, allocated_amount=allocated
        )
        LOGGER.info("set %s = %d", name, allocated)
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed budget lines (chart of accounts) into the delivery-ops ledger."
    )
    parser.add_argument(
        "chart", type=Path, help="JSON file: array of {name, allocated_amount}"
    )
    args = parser.parse_args()

    db_path = os.environ["DELIVERY_OPS_DB_PATH"]
    project = os.environ["PROJECT_NAME"]

    if not args.chart.is_file():
        raise FileNotFoundError(f"chart of accounts not found: {args.chart}")
    lines = json.loads(args.chart.read_text(encoding="utf-8"))
    if not isinstance(lines, list):
        raise ValueError("chart of accounts must be a JSON array")

    count = asyncio.run(seed(db_path, project, lines))
    LOGGER.info("seeded %d budget line(s) for project %r into %s", count, project, db_path)


if __name__ == "__main__":
    main()
