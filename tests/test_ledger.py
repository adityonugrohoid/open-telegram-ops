"""Tests for the SQLite cost ledger: schema, budget lines, writes, reads, validation.

The ledger is the durable asset, so this suite pins its behaviour: amounts are
positive rupiah, every expense maps to a defined budget line (no silent vanish),
and query_spend and budget_status stay in agreement.
"""

from __future__ import annotations

from typing import Any, cast

import aiosqlite
import pytest
import pytest_asyncio

from delivery_ops_mcp import ledger

CREATED_AT = "2026-06-01T00:00:00Z"


@pytest_asyncio.fixture
async def db(tmp_path):
    """A freshly initialised ledger database, one per test."""
    path = str(tmp_path / "test_ledger.db")
    await ledger.init_db(path)
    return path


async def _log(
    db_path: str,
    *,
    project: str = "P",
    telegram_user_id: int = 1,
    username: str | None = "alice",
    amount: int = 250000,
    vendor: str | None = "SPBU",
    expense_date: str = "2026-06-01",
    category: str | None = "transport",
    budget_line: str = "Fuel",
    raw_ocr: str | None = None,
    created_at: str = CREATED_AT,
) -> int:
    """Log an expense with sensible test defaults; override fields per test."""
    return await ledger.log_expense(
        db_path,
        project=project,
        telegram_user_id=telegram_user_id,
        username=username,
        amount=amount,
        vendor=vendor,
        expense_date=expense_date,
        category=category,
        budget_line=budget_line,
        raw_ocr=raw_ocr,
        created_at=created_at,
    )


async def test_init_db_is_idempotent(db):
    await ledger.init_db(db)  # second call must not raise
    async with aiosqlite.connect(db) as c:
        rows = await (await c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )).fetchall()
    assert {r[0] for r in rows} == {"budget_lines", "expenses"}


async def test_upsert_budget_line_inserts_then_updates(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    status = await ledger.budget_status(db, project="P")
    assert status == [
        {"budget_line": "Fuel", "allocated": 1000000, "spent": 0, "remaining": 1000000, "pct_used": 0.0}
    ]
    # re-upsert updates the allocation in place, never duplicates the line
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=2000000)
    status = await ledger.budget_status(db, project="P")
    assert len(status) == 1
    assert status[0]["allocated"] == 2000000


async def test_upsert_budget_line_rejects_negative(db):
    with pytest.raises(ValueError, match="non-negative"):
        await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=-1)


async def test_log_expense_requires_defined_budget_line(db):
    with pytest.raises(ValueError, match="not a defined line"):
        await _log(db)  # no budget line seeded yet


async def test_log_expense_rejects_nonpositive_amount(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    with pytest.raises(ValueError, match="positive"):
        await _log(db, amount=0)


async def test_log_and_query_spend_breaks_down_by_line_and_submitter(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await ledger.upsert_budget_line(db, project="P", name="Tools", allocated_amount=500000)
    await _log(db, amount=250000, budget_line="Fuel", telegram_user_id=1, username="alice")
    await _log(db, amount=100000, budget_line="Tools", telegram_user_id=2, username="bob")
    await _log(db, amount=50000, budget_line="Fuel", telegram_user_id=2, username="bob")
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30")
    assert qs["total"] == 400000
    by_line = {r["budget_line"]: r["total"] for r in cast("list[dict[str, Any]]", qs["by_budget_line"])}
    assert by_line == {"Fuel": 300000, "Tools": 100000}
    by_user = {r["username"]: r["total"] for r in cast("list[dict[str, Any]]", qs["by_submitter"])}
    assert by_user == {"alice": 250000, "bob": 150000}


async def test_query_spend_respects_the_date_window(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await _log(db, amount=100000, expense_date="2026-05-31")
    await _log(db, amount=200000, expense_date="2026-06-15")
    await _log(db, amount=400000, expense_date="2026-07-01")
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30")
    assert qs["total"] == 200000


async def test_query_spend_isolates_projects(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await ledger.upsert_budget_line(db, project="Q", name="Fuel", allocated_amount=1000000)
    await _log(db, project="P", amount=250000)
    await _log(db, project="Q", amount=999999)
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30")
    assert qs["total"] == 250000


async def test_budget_status_math(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await _log(db, amount=250000, budget_line="Fuel")
    status = await ledger.budget_status(db, project="P")
    assert status[0] == {
        "budget_line": "Fuel",
        "allocated": 1000000,
        "spent": 250000,
        "remaining": 750000,
        "pct_used": 25.0,
    }


async def test_query_spend_and_budget_status_agree(db):
    # Regression for the silent-vanish gap: because every logged line must be a
    # defined line, query_spend's total equals the sum of budget_status spent.
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await ledger.upsert_budget_line(db, project="P", name="Tools", allocated_amount=500000)
    await _log(db, amount=250000, budget_line="Fuel")
    await _log(db, amount=100000, budget_line="Tools")
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30")
    status = await ledger.budget_status(db, project="P")
    assert qs["total"] == sum(s["spent"] for s in cast("list[dict[str, Any]]", status))


async def _seed_mixed(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await ledger.upsert_budget_line(db, project="P", name="Tools", allocated_amount=500000)
    await _log(db, amount=250000, budget_line="Fuel", category="transport", telegram_user_id=1, username="alice")
    await _log(db, amount=50000, budget_line="Fuel", category="transport", telegram_user_id=2, username="bob")
    await _log(db, amount=100000, budget_line="Tools", category="equipment", telegram_user_id=1, username="alice")


async def test_query_spend_filter_by_budget_line(db):
    await _seed_mixed(db)
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30", budget_line="Fuel")
    assert qs["total"] == 300000
    assert {r["budget_line"] for r in cast("list[dict[str, Any]]", qs["by_budget_line"])} == {"Fuel"}


async def test_query_spend_filter_by_submitter(db):
    await _seed_mixed(db)
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30", submitter_id=1)
    assert qs["total"] == 350000  # alice: 250000 Fuel + 100000 Tools


async def test_query_spend_filter_by_category(db):
    await _seed_mixed(db)
    qs = await ledger.query_spend(db, project="P", since="2026-06-01", until="2026-06-30", category="equipment")
    assert qs["total"] == 100000


async def test_query_spend_filters_compose(db):
    await _seed_mixed(db)
    qs = await ledger.query_spend(
        db, project="P", since="2026-06-01", until="2026-06-30", budget_line="Fuel", submitter_id=2
    )
    assert qs["total"] == 50000  # bob on Fuel only


async def test_budget_status_single_line(db):
    await _seed_mixed(db)
    status = await ledger.budget_status(db, project="P", budget_line="Tools")
    assert len(status) == 1
    assert status[0]["budget_line"] == "Tools"
    assert status[0]["spent"] == 100000


async def test_budget_status_unknown_line_is_empty(db):
    await _seed_mixed(db)
    status = await ledger.budget_status(db, project="P", budget_line="Nope")
    assert status == []


async def test_fetch_expenses_returns_every_column(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await _log(db, amount=250000, budget_line="Fuel", vendor="SPBU", raw_ocr="TOTAL 250000")
    rows = await ledger.fetch_expenses(db, project="P")
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {
        "id", "project", "telegram_user_id", "username", "amount", "vendor",
        "expense_date", "category", "budget_line", "raw_ocr", "created_at",
    }
    assert row["amount"] == 250000
    assert row["vendor"] == "SPBU"
    assert row["raw_ocr"] == "TOTAL 250000"  # raw audit field is preserved


async def test_fetch_expenses_orders_by_id_ascending(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await _log(db, amount=100000, budget_line="Fuel")
    await _log(db, amount=200000, budget_line="Fuel")
    rows = await ledger.fetch_expenses(db, project="P")
    assert [r["amount"] for r in rows] == [100000, 200000]
    ids = [int(r["id"]) for r in rows]  # type: ignore[call-overload]
    assert ids == sorted(ids)


async def test_fetch_expenses_respects_date_range(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await _log(db, amount=100000, expense_date="2026-05-31")
    await _log(db, amount=200000, expense_date="2026-06-15")
    await _log(db, amount=400000, expense_date="2026-07-01")
    rows = await ledger.fetch_expenses(db, project="P", since="2026-06-01", until="2026-06-30")
    assert [r["amount"] for r in rows] == [200000]


async def test_fetch_expenses_isolates_projects(db):
    await ledger.upsert_budget_line(db, project="P", name="Fuel", allocated_amount=1000000)
    await ledger.upsert_budget_line(db, project="Q", name="Fuel", allocated_amount=1000000)
    await _log(db, project="P", amount=250000)
    await _log(db, project="Q", amount=999999)
    rows = await ledger.fetch_expenses(db, project="P")
    assert [r["amount"] for r in rows] == [250000]


async def test_fetch_expenses_empty_is_empty_list(db):
    rows = await ledger.fetch_expenses(db, project="P")
    assert rows == []
