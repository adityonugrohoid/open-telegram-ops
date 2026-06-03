"""Reporting: text summaries and matplotlib charts for manager queries.

Text summaries are returned by the MCP tools as data; the agent formats them for
chat. Charts are rendered to PNG bytes and sent in-chat as a photo. Keep the
chart path synchronous end to end (OpenClaw drops async replies on idle sessions,
upstream issue #89641).
"""

from __future__ import annotations


def format_rupiah(amount: int) -> str:
    """Format integer rupiah as 'Rp 1.234.567' (Indonesian thousands separator)."""
    return "Rp " + f"{amount:,}".replace(",", ".")


def render_budget_chart(status: list[dict[str, object]]) -> bytes:
    """Render a budget-vs-actual bar chart to PNG bytes.

    Input is the output of ledger.budget_status: one dict per budget line with
    'budget_line', 'allocated', 'spent'.

    TODO: implement with matplotlib (allocated vs spent grouped bars per line).
    Kept as a stub until the OCR gate passes and the ledger has real data to plot.
    """
    raise NotImplementedError("budget chart rendering not implemented yet")
    # Sketch:
    # import matplotlib
    # matplotlib.use("Agg")
    # import matplotlib.pyplot as plt
    # ... build grouped bars, then:
    # buf = io.BytesIO(); fig.savefig(buf, format="png"); return buf.getvalue()
