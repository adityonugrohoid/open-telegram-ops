"""Tests for the budget seed script's core logic."""

from __future__ import annotations

import pytest
import pytest_asyncio

from delivery_ops_mcp import ledger
from scripts import seed_budget


@pytest_asyncio.fixture
async def db(tmp_path):
    return str(tmp_path / "seed.db")


async def test_seed_upserts_all_lines(db):
    lines = [
        {"name": "Fuel", "allocated_amount": 1000000},
        {"name": "Tools", "allocated_amount": 500000},
    ]
    count = await seed_budget.seed(db, "P", lines)
    assert count == 2
    status = await ledger.budget_status(db, project="P")
    assert {s["budget_line"]: s["allocated"] for s in status} == {"Fuel": 1000000, "Tools": 500000}


async def test_seed_is_idempotent_and_updates(db):
    await seed_budget.seed(db, "P", [{"name": "Fuel", "allocated_amount": 1000000}])
    await seed_budget.seed(db, "P", [{"name": "Fuel", "allocated_amount": 1500000}])
    status = await ledger.budget_status(db, project="P")
    assert len(status) == 1
    assert status[0]["allocated"] == 1500000


async def test_seed_rejects_malformed_line(db):
    with pytest.raises(ValueError, match="allocated_amount"):
        await seed_budget.seed(db, "P", [{"name": "Fuel", "allocated_amount": "lots"}])
