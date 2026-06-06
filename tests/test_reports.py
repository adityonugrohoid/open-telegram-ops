"""Tests for report formatting and budget-vs-actual chart rendering."""

from __future__ import annotations

import stat

import pytest

from delivery_ops_mcp import reports

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_format_rupiah():
    assert reports.format_rupiah(1234567) == "Rp 1.234.567"
    assert reports.format_rupiah(0) == "Rp 0"
    assert reports.format_rupiah(500) == "Rp 500"


def test_render_budget_chart_returns_png_bytes():
    status = [
        {"budget_line": "Fuel", "allocated": 1000000, "spent": 250000},
        {"budget_line": "Tools", "allocated": 500000, "spent": 600000},  # over budget
    ]
    png = reports.render_budget_chart(status, title="Test project")
    assert png[:8] == PNG_MAGIC
    assert len(png) > 1000  # a real rendered image, not an empty buffer


def test_render_budget_chart_empty_raises():
    with pytest.raises(ValueError, match="no budget lines"):
        reports.render_budget_chart([])


def test_write_chart_png_creates_world_readable_file(tmp_path):
    png = reports.render_budget_chart(
        [{"budget_line": "Fuel", "allocated": 1000000, "spent": 250000}]
    )
    path = reports.write_chart_png(png, str(tmp_path / "charts"), "Pilot Project")
    assert path.exists()
    assert path.name == "budget-pilot-project.png"  # slugified, stable name
    assert path.read_bytes()[:8] == PNG_MAGIC
    assert stat.S_IMODE(path.stat().st_mode) == 0o644  # gateway (non-root) can read


def test_write_chart_png_overwrites_same_project(tmp_path):
    png = reports.render_budget_chart(
        [{"budget_line": "Fuel", "allocated": 1000000, "spent": 250000}]
    )
    p1 = reports.write_chart_png(png, str(tmp_path), "Pilot")
    p2 = reports.write_chart_png(png, str(tmp_path), "Pilot")
    assert p1 == p2  # stable name, not accumulating files


def _expense_row(**overrides):
    row = {
        "id": 1, "project": "Pilot", "telegram_user_id": 1, "username": "alice",
        "amount": 250000, "vendor": "SPBU", "expense_date": "2026-06-01",
        "category": "transport", "budget_line": "Fuel", "raw_ocr": "TOTAL 250000",
        "created_at": "2026-06-01T00:00:00Z",
    }
    row.update(overrides)
    return row


def test_write_ledger_csv_creates_world_readable_file(tmp_path):
    path = reports.write_ledger_csv([_expense_row()], str(tmp_path / "exports"), "Pilot Project")
    assert path.exists()
    assert path.name == "ledger-pilot-project.csv"  # slugified, stable name
    assert stat.S_IMODE(path.stat().st_mode) == 0o644  # gateway (non-root) can read
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == (
        "id,project,telegram_user_id,username,amount,vendor,"
        "expense_date,category,budget_line,raw_ocr,created_at"
    )
    assert "SPBU" in lines[1]
    assert "250000" in lines[1]


def test_write_ledger_csv_empty_writes_header_only(tmp_path):
    path = reports.write_ledger_csv([], str(tmp_path), "Pilot")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # header row only, no data
    assert lines[0].startswith("id,project,")


def test_write_ledger_csv_overwrites_same_project(tmp_path):
    p1 = reports.write_ledger_csv([_expense_row()], str(tmp_path), "Pilot")
    p2 = reports.write_ledger_csv([_expense_row(id=2)], str(tmp_path), "Pilot")
    assert p1 == p2  # stable name, not accumulating files
