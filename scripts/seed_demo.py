"""Seed a rich, realistic demo dataset into the delivery-ops ledger.

This is fake data for portfolio demos and screenshots: a full chart of accounts
plus ~30 expenses spread across several field submitters and six weeks, sized so
that budget_status, query_spend, and budget_chart all look populated. One line
(Tools and safety gear) is deliberately over budget, so the chart renders its red
over-budget bar.

Budget lines are upserted idempotently. Expenses are NOT deduplicated, so the
script refuses to run if the project already has expenses unless you pass
--reset-expenses, which deletes the project's existing expenses first. It only
ever touches the project named by PROJECT_NAME.

Usage (run as a module from the repo root so delivery_ops_mcp is importable):
    DELIVERY_OPS_DB_PATH=data/delivery_ops.db PROJECT_NAME=savannah-telco-ops \\
        python -m scripts.seed_demo --reset-expenses
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

import aiosqlite
from dotenv import load_dotenv

from delivery_ops_mcp import ledger

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger("seed_demo")

# Chart of accounts (integer rupiah). Mirrors scripts/budget_lines.sample.json.
BUDGET_LINES: list[dict[str, object]] = [
    {"name": "Fuel and transport", "allocated_amount": 15_000_000},
    {"name": "Tower materials", "allocated_amount": 80_000_000},
    {"name": "Subcontractor labor", "allocated_amount": 45_000_000},
    {"name": "Permits and site access", "allocated_amount": 8_000_000},
    {"name": "Tools and safety gear", "allocated_amount": 6_000_000},
    {"name": "Accommodation and meals", "allocated_amount": 12_000_000},
]

# Fake field submitters (Telegram user ids + usernames). Not real people.
_BUDI = (810_000_001, "budi_santoso")
_SARI = (810_000_002, "sari_dewi")
_AGUS = (810_000_003, "agus_pratama")
_RINA = (810_000_004, "rina_wijaya")
_DEDI = (810_000_005, "dedi_kurniawan")

# Each expense: (submitter, amount, vendor, date, category, budget_line, raw_ocr).
# raw_ocr is a plausible receipt total for photo entries, None for typed ones.
_RAW: list[tuple[tuple[int, str], int, str, str, str, str, str | None]] = [
    (_BUDI, 850_000, "SPBU Pertamina Cibitung", "2026-04-22", "transport", "Fuel and transport", "TOTAL Rp 850.000"),
    (_SARI, 2_500_000, "Dinas Perizinan Kabupaten", "2026-04-23", "permits", "Permits and site access", None),
    (_RINA, 18_500_000, "PT Baja Konstruksi Nusantara", "2026-04-24", "materials", "Tower materials", "TOTAL Rp 18.500.000"),
    (_BUDI, 2_200_000, "Safety Gear Indonesia", "2026-04-25", "safety", "Tools and safety gear", "TOTAL Rp 2.200.000"),
    (_DEDI, 8_500_000, "CV Mitra Karya Rigger", "2026-04-26", "labor", "Subcontractor labor", None),
    (_AGUS, 2_400_000, "Penginapan Melati", "2026-04-27", "lodging", "Accommodation and meals", "TOTAL Rp 2.400.000"),
    (_AGUS, 1_200_000, "SPBU Shell Karawang", "2026-04-28", "transport", "Fuel and transport", "TOTAL Rp 1.200.000"),
    (_RINA, 12_750_000, "CV Galvanis Jaya", "2026-05-02", "materials", "Tower materials", "TOTAL Rp 12.750.000"),
    (_BUDI, 760_000, "SPBU Pertamina Cikampek", "2026-05-04", "transport", "Fuel and transport", "TOTAL Rp 760.000"),
    (_AGUS, 1_650_000, "Toko Perkakas Maju", "2026-05-05", "equipment", "Tools and safety gear", "TOTAL Rp 1.650.000"),
    (_DEDI, 7_800_000, "Tim Sipil Pak Joko", "2026-05-06", "labor", "Subcontractor labor", None),
    (_SARI, 1_800_000, "Retribusi akses lahan desa", "2026-05-07", "permits", "Permits and site access", None),
    (_DEDI, 1_450_000, "Sewa pickup L300", "2026-05-08", "transport", "Fuel and transport", "TOTAL Rp 1.450.000"),
    (_SARI, 1_850_000, "Rumah Makan Padang Sederhana", "2026-05-09", "meals", "Accommodation and meals", "TOTAL Rp 1.850.000"),
    (_AGUS, 9_800_000, "Toko Besi Sumber Makmur", "2026-05-11", "materials", "Tower materials", "TOTAL Rp 9.800.000"),
    (_SARI, 680_000, "SPBU Pertamina Bekasi", "2026-05-14", "transport", "Fuel and transport", "TOTAL Rp 680.000"),
    (_BUDI, 1_450_000, "APD set lengkap", "2026-05-15", "safety", "Tools and safety gear", "TOTAL Rp 1.450.000"),
    (_BUDI, 6_200_000, "Crew climbing tower", "2026-05-16", "labor", "Subcontractor labor", None),
    (_RINA, 1_600_000, "Warung Bu Tini", "2026-05-18", "meals", "Accommodation and meals", "TOTAL Rp 1.600.000"),
    (_RINA, 7_200_000, "PT Kabel Optik Indo", "2026-05-19", "materials", "Tower materials", "TOTAL Rp 7.200.000"),
    (_BUDI, 920_000, "SPBU Total Cikarang", "2026-05-20", "transport", "Fuel and transport", "TOTAL Rp 920.000"),
    (_RINA, 1_100_000, "Izin warga setempat", "2026-05-21", "permits", "Permits and site access", None),
    (_DEDI, 980_000, "Sewa genset + tools", "2026-05-23", "equipment", "Tools and safety gear", "TOTAL Rp 980.000"),
    (_DEDI, 5_400_000, "CV Mitra Karya Rigger", "2026-05-24", "labor", "Subcontractor labor", None),
    (_AGUS, 1_350_000, "Sewa truk material", "2026-05-26", "transport", "Fuel and transport", "TOTAL Rp 1.350.000"),
    (_AGUS, 1_950_000, "Penginapan Melati", "2026-05-28", "lodging", "Accommodation and meals", "TOTAL Rp 1.950.000"),
    (_AGUS, 4_150_000, "Toko Bangunan Sentosa", "2026-05-29", "materials", "Tower materials", "TOTAL Rp 4.150.000"),
    (_SARI, 3_300_000, "Tenaga harian lokal", "2026-06-01", "labor", "Subcontractor labor", None),
    (_BUDI, 870_000, "Toko Perkakas Maju", "2026-06-02", "equipment", "Tools and safety gear", "TOTAL Rp 870.000"),
    (_DEDI, 880_000, "SPBU Pertamina Subang", "2026-06-02", "transport", "Fuel and transport", "TOTAL Rp 880.000"),
    (_SARI, 850_000, "Biaya koordinasi RT/RW", "2026-06-03", "permits", "Permits and site access", None),
    (_SARI, 1_400_000, "Ojek dan travel crew", "2026-06-04", "transport", "Fuel and transport", "TOTAL Rp 1.400.000"),
]


async def _count_expenses(db_path: str, project: str) -> int:
    """Return how many expenses already exist for the project."""
    async with aiosqlite.connect(db_path) as db:
        row = await (await db.execute(
            "SELECT COUNT(*) FROM expenses WHERE project = ?", (project,)
        )).fetchone()
    return int(row[0]) if row else 0


async def _delete_expenses(db_path: str, project: str) -> int:
    """Delete the project's expenses (demo reset only). Returns rows deleted."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("DELETE FROM expenses WHERE project = ?", (project,))
        await db.commit()
        return cursor.rowcount


async def seed(db_path: str, project: str, *, reset_expenses: bool) -> tuple[int, int]:
    """Seed budget lines and demo expenses for the project.

    Args:
        db_path: Path to the SQLite ledger database.
        project: PROJECT_NAME the data belongs to.
        reset_expenses: If True, delete the project's existing expenses first;
            if False and any exist, raise rather than create duplicates.

    Returns:
        A (budget_lines, expenses) count tuple of what was seeded.

    Raises:
        RuntimeError: The project already has expenses and reset_expenses is False.
    """
    await ledger.init_db(db_path)

    existing = await _count_expenses(db_path, project)
    if existing:
        if not reset_expenses:
            raise RuntimeError(
                f"project {project!r} already has {existing} expense(s); pass "
                "--reset-expenses to replace them, or point at an empty project"
            )
        deleted = await _delete_expenses(db_path, project)
        LOGGER.info("reset: deleted %d existing expense(s) for %r", deleted, project)

    for line in BUDGET_LINES:
        await ledger.upsert_budget_line(
            db_path,
            project=project,
            name=str(line["name"]),
            allocated_amount=int(line["allocated_amount"]),  # type: ignore[call-overload]
        )
    LOGGER.info("seeded %d budget line(s)", len(BUDGET_LINES))

    for submitter, amount, vendor, date, category, budget_line, raw_ocr in _RAW:
        user_id, username = submitter
        await ledger.log_expense(
            db_path,
            project=project,
            telegram_user_id=user_id,
            username=username,
            amount=amount,
            vendor=vendor,
            expense_date=date,
            category=category,
            budget_line=budget_line,
            raw_ocr=raw_ocr,
            created_at=f"{date}T09:00:00+00:00",
        )
    LOGGER.info("seeded %d expense(s)", len(_RAW))
    return len(BUDGET_LINES), len(_RAW)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a rich demo dataset into the delivery-ops ledger."
    )
    parser.add_argument(
        "--reset-expenses",
        action="store_true",
        help="delete the project's existing expenses before seeding (demo reset)",
    )
    args = parser.parse_args()

    db_path = os.environ["DELIVERY_OPS_DB_PATH"]
    project = os.environ["PROJECT_NAME"]

    lines, expenses = asyncio.run(
        seed(db_path, project, reset_expenses=args.reset_expenses)
    )
    LOGGER.info(
        "done: %d budget line(s) + %d expense(s) for project %r into %s",
        lines, expenses, project, db_path,
    )


if __name__ == "__main__":
    main()
