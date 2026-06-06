"""Tests for the demo seed script's core logic."""

from __future__ import annotations

import pytest
import pytest_asyncio

from delivery_ops_mcp import ledger
from scripts import seed_demo


@pytest_asyncio.fixture
async def db(tmp_path):
    return str(tmp_path / "demo.db")


async def test_seed_creates_full_dataset(db):
    lines, expenses = await seed_demo.seed(db, "P", reset_expenses=False)
    assert lines == len(seed_demo.BUDGET_LINES)
    assert expenses == len(seed_demo._RAW)
    rows = await ledger.fetch_expenses(db, project="P")
    assert len(rows) == expenses
    status = await ledger.budget_status(db, project="P")
    assert len(status) == lines


async def test_seed_has_one_over_budget_line(db):
    # Tools and safety gear is sized to exceed its allocation, so the chart shows
    # the red over-budget bar. Guard that the demo keeps that property.
    await seed_demo.seed(db, "P", reset_expenses=False)
    status = await ledger.budget_status(db, project="P")
    over = [s for s in status if s["spent"] > s["allocated"]]
    assert [s["budget_line"] for s in over] == ["Tools and safety gear"]


async def test_seed_refuses_to_duplicate_without_reset(db):
    await seed_demo.seed(db, "P", reset_expenses=False)
    with pytest.raises(RuntimeError, match="already has"):
        await seed_demo.seed(db, "P", reset_expenses=False)


async def test_seed_reset_replaces_not_appends(db):
    await seed_demo.seed(db, "P", reset_expenses=False)
    await seed_demo.seed(db, "P", reset_expenses=True)
    rows = await ledger.fetch_expenses(db, project="P")
    assert len(rows) == len(seed_demo._RAW)  # replaced, not doubled


async def test_seed_isolates_other_projects(db):
    await seed_demo.seed(db, "P", reset_expenses=False)
    # a different project with its own expenses is untouched by a reset of P
    await ledger.upsert_budget_line(db, project="Q", name="Fuel and transport", allocated_amount=1_000_000)
    await ledger.log_expense(
        db, project="Q", telegram_user_id=1, username="x", amount=5000,
        vendor="v", expense_date="2026-06-01", category="transport",
        budget_line="Fuel and transport", raw_ocr=None, created_at="2026-06-01T00:00:00Z",
    )
    await seed_demo.seed(db, "P", reset_expenses=True)
    assert len(await ledger.fetch_expenses(db, project="Q")) == 1
