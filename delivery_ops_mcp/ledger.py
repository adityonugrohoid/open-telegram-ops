"""SQLite delivery-ops ledger: schema and async read/write.

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


async def upsert_budget_line(
    db_path: str,
    *,
    project: str,
    name: str,
    allocated_amount: int,
) -> None:
    """Create a budget line or update its allocation, for one project.

    Idempotent on (project, name): re-running with a new allocated_amount updates
    the allocation in place rather than inserting a duplicate. This is the only
    write path for budget allocations; budget lines must exist before expenses can
    be logged against them (see log_expense).
    """
    if allocated_amount < 0:
        raise ValueError(
            f"allocated_amount must be non-negative rupiah, got {allocated_amount!r}"
        )
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO budget_lines (project, name, allocated_amount)
            VALUES (?, ?, ?)
            ON CONFLICT (project, name)
                DO UPDATE SET allocated_amount = excluded.allocated_amount
            """,
            (project, name, allocated_amount),
        )
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

    budget_line must be a line already defined for the project (via
    upsert_budget_line / the seed script). Logging against an undefined line is
    rejected, so an expense can never silently fall out of budget_status.
    """
    if amount <= 0:
        raise ValueError(f"amount must be positive rupiah, got {amount!r}")
    async with aiosqlite.connect(db_path) as db:
        known_line = await (await db.execute(
            "SELECT 1 FROM budget_lines WHERE project = ? AND name = ?",
            (project, budget_line),
        )).fetchone()
        if known_line is None:
            raise ValueError(
                f"budget_line {budget_line!r} is not a defined line for project "
                f"{project!r}; define it with set_budget or the seed script first"
            )
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
    budget_line: str | None = None,
    category: str | None = None,
    submitter_id: int | None = None,
) -> dict[str, object]:
    """Return spend for [since, until] (inclusive ISO dates) for one project,
    broken down by budget line and by submitter, plus the total.

    The optional filters narrow the result. Each that is not None adds an equality
    condition (budget_line, category, telegram_user_id). They compose, so passing
    submitter_id and budget_line returns one submitter's spend on one line.
    """
    conditions = ["project = ?", "expense_date BETWEEN ? AND ?"]
    params: list[object] = [project, since, until]
    if budget_line is not None:
        conditions.append("budget_line = ?")
        params.append(budget_line)
    if category is not None:
        conditions.append("category = ?")
        params.append(category)
    if submitter_id is not None:
        conditions.append("telegram_user_id = ?")
        params.append(submitter_id)
    where = " AND ".join(conditions)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        by_line = await (await db.execute(
            f"""
            SELECT budget_line, SUM(amount) AS total
            FROM expenses
            WHERE {where}
            GROUP BY budget_line ORDER BY total DESC
            """,
            params,
        )).fetchall()
        by_user = await (await db.execute(
            f"""
            SELECT telegram_user_id, username, SUM(amount) AS total
            FROM expenses
            WHERE {where}
            GROUP BY telegram_user_id ORDER BY total DESC
            """,
            params,
        )).fetchall()
    return {
        "project": project,
        "since": since,
        "until": until,
        "filters": {"budget_line": budget_line, "category": category, "submitter_id": submitter_id},
        "by_budget_line": [dict(r) for r in by_line],
        "by_submitter": [dict(r) for r in by_user],
        "total": sum(r["total"] for r in by_line),
    }


async def fetch_expenses(
    db_path: str,
    *,
    project: str,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, object]]:
    """Return raw expense rows for one project, ordered by id ascending.

    This is the row-level read behind the CSV export. Unlike query_spend, which
    aggregates, it returns every column of every matching row (amount, vendor,
    date, category, budget line, submitter id, raw OCR, created_at), for audit.

    The optional since/until bound expense_date inclusively (ISO YYYY-MM-DD). With
    both omitted, every row for the project is returned.
    """
    conditions = ["project = ?"]
    params: list[object] = [project]
    if since is not None:
        conditions.append("expense_date >= ?")
        params.append(since)
    if until is not None:
        conditions.append("expense_date <= ?")
        params.append(until)
    where = " AND ".join(conditions)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            f"""
            SELECT
                id, project, telegram_user_id, username, amount, vendor,
                expense_date, category, budget_line, raw_ocr, created_at
            FROM expenses
            WHERE {where}
            ORDER BY id ASC
            """,
            params,
        )).fetchall()
    return [dict(r) for r in rows]


async def budget_status(
    db_path: str,
    *,
    project: str,
    budget_line: str | None = None,
) -> list[dict[str, object]]:
    """Return budget-vs-actual per budget line for the project.

    With budget_line set, returns just that one line (an empty list if no such
    line is defined); otherwise every line for the project.
    """
    conditions = ["bl.project = ?"]
    params: list[object] = [project]
    if budget_line is not None:
        conditions.append("bl.name = ?")
        params.append(budget_line)
    where = " AND ".join(conditions)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            f"""
            SELECT
                bl.name AS budget_line,
                bl.allocated_amount AS allocated,
                COALESCE(SUM(e.amount), 0) AS spent
            FROM budget_lines bl
            LEFT JOIN expenses e
                ON e.project = bl.project AND e.budget_line = bl.name
            WHERE {where}
            GROUP BY bl.id ORDER BY bl.name
            """,
            params,
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
