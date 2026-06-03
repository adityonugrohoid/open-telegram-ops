"""SQLite cost ledger: schema and async read/write.

Amounts are stored as integer rupiah (IDR has no sub-unit in practice). All I/O
is async via aiosqlite. Functions raise on misuse rather than failing silently.
"""

from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_lines (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project          TEXT    NOT NULL,
    name             TEXT    NOT NULL,
    allocated_amount INTEGER NOT NULL,
    UNIQUE (project, name)
);

CREATE TABLE IF NOT EXISTS expenses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project          TEXT    NOT NULL,
    telegram_user_id INTEGER NOT NULL,
    username         TEXT,
    amount           INTEGER NOT NULL,
    vendor           TEXT,
    expense_date     TEXT    NOT NULL,   -- ISO date, YYYY-MM-DD
    category         TEXT,
    budget_line      TEXT    NOT NULL,
    raw_ocr          TEXT,               -- raw model output, kept for audit
    created_at       TEXT    NOT NULL    -- ISO timestamp set by the caller
);

CREATE INDEX IF NOT EXISTS idx_expenses_project_date
    ON expenses (project, expense_date);
"""


async def init_db(db_path: str) -> None:
    """Create tables and indexes if they do not exist."""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def log_expense(
    db_path: str,
    *,
    project: str,
    telegram_user_id: int,
    username: str | None,
    amount: int,
    vendor: str | None,
    expense_date: str,
    category: str | None,
    budget_line: str,
    raw_ocr: str | None,
    created_at: str,
) -> int:
    """Insert one confirmed expense. Returns the new expense id.

    The caller (agent) must have confirmed the parsed values with the submitter
    before calling this. created_at is passed in, not generated here, to keep
    this layer free of ambient clock state.
    """
    if amount <= 0:
        raise ValueError(f"amount must be positive rupiah, got {amount!r}")
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO expenses (
                project, telegram_user_id, username, amount, vendor,
                expense_date, category, budget_line, raw_ocr, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project, telegram_user_id, username, amount, vendor,
                expense_date, category, budget_line, raw_ocr, created_at,
            ),
        )
        await db.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("insert returned no row id")
        return cursor.lastrowid


async def query_spend(
    db_path: str,
    *,
    project: str,
    since: str,
    until: str,
) -> dict[str, object]:
    """Return spend for [since, until] (inclusive ISO dates) for one project,
    broken down by budget line and by submitter, plus the total.
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        by_line = await (await db.execute(
            """
            SELECT budget_line, SUM(amount) AS total
            FROM expenses
            WHERE project = ? AND expense_date BETWEEN ? AND ?
            GROUP BY budget_line ORDER BY total DESC
            """,
            (project, since, until),
        )).fetchall()
        by_user = await (await db.execute(
            """
            SELECT telegram_user_id, username, SUM(amount) AS total
            FROM expenses
            WHERE project = ? AND expense_date BETWEEN ? AND ?
            GROUP BY telegram_user_id ORDER BY total DESC
            """,
            (project, since, until),
        )).fetchall()
    return {
        "project": project,
        "since": since,
        "until": until,
        "by_budget_line": [dict(r) for r in by_line],
        "by_submitter": [dict(r) for r in by_user],
        "total": sum(r["total"] for r in by_line),
    }


async def budget_status(db_path: str, *, project: str) -> list[dict[str, object]]:
    """Return budget-vs-actual per budget line for the active project."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            """
            SELECT
                bl.name AS budget_line,
                bl.allocated_amount AS allocated,
                COALESCE(SUM(e.amount), 0) AS spent
            FROM budget_lines bl
            LEFT JOIN expenses e
                ON e.project = bl.project AND e.budget_line = bl.name
            WHERE bl.project = ?
            GROUP BY bl.id ORDER BY bl.name
            """,
            (project,),
        )).fetchall()
    result: list[dict[str, object]] = []
    for r in rows:
        allocated = r["allocated"]
        spent = r["spent"]
        result.append({
            "budget_line": r["budget_line"],
            "allocated": allocated,
            "spent": spent,
            "remaining": allocated - spent,
            "pct_used": round(spent / allocated * 100, 1) if allocated else None,
        })
    return result
