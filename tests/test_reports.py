"""Tests for report formatting and budget-vs-actual chart rendering."""

from __future__ import annotations

import stat

import pytest

from cost_ledger_mcp import reports

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
