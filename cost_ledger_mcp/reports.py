"""Reporting: text summaries and matplotlib charts for manager queries.

Text summaries are returned by the MCP tools as data; the agent formats them for
chat. Charts are rendered to PNG bytes and sent in-chat as a photo. Keep the
chart path synchronous end to end (OpenClaw drops async replies on idle sessions,
upstream issue #89641).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

# House palette (matches the README architecture diagram).
COLOR_ALLOCATED = "#0f3460"
COLOR_SPENT = "#533483"
COLOR_OVER = "#c1121f"


def format_rupiah(amount: int) -> str:
    """Format integer rupiah as 'Rp 1.234.567' (Indonesian thousands separator)."""
    return "Rp " + f"{amount:,}".replace(",", ".")


def render_budget_chart(status: list[dict[str, object]], *, title: str | None = None) -> bytes:
    """Render a budget-vs-actual grouped bar chart to PNG bytes.

    Input is the output of ledger.budget_status: one dict per budget line with
    'budget_line', 'allocated', and 'spent'. Each line gets a pair of bars
    (allocated vs spent); over-budget spent bars are coloured red. The whole path
    is synchronous, so the agent can send the PNG in the same turn (OpenClaw drops
    async replies on idle sessions, upstream #89641).

    Raises ValueError on empty input: there is nothing to plot until budgets are
    defined.
    """
    if not status:
        raise ValueError(
            "no budget lines to chart; define budgets with set_budget first"
        )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    lines = [str(r["budget_line"]) for r in status]
    allocated = [int(r["allocated"]) for r in status]  # type: ignore[call-overload]
    spent = [int(r["spent"]) for r in status]  # type: ignore[call-overload]
    spent_colors = [COLOR_OVER if s > a else COLOR_SPENT for s, a in zip(spent, allocated)]

    positions = range(len(lines))
    width = 0.4

    fig, ax = plt.subplots(figsize=(max(6.0, len(lines) * 1.4), 5.0))
    ax.bar([p - width / 2 for p in positions], allocated, width, label="Allocated", color=COLOR_ALLOCATED)
    ax.bar([p + width / 2 for p in positions], spent, width, label="Spent", color=spent_colors)

    ax.set_xticks(list(positions))
    ax.set_xticklabels(lines, rotation=30, ha="right")
    ax.set_ylabel("Rupiah")
    ax.set_title(title or "Budget vs actual")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: format_rupiah(int(value))))
    ax.legend()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def write_chart_png(png: bytes, output_dir: str, project: str) -> Path:
    """Write chart PNG bytes to output_dir and return the path.

    The file is named per project (stable, so it is overwritten each render) and
    made world-readable: the cost-ledger sidecar writes it as root, but the
    OpenClaw gateway reads it as a non-root user to send it as a Telegram photo,
    so both containers must share output_dir as a volume.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", project.lower()).strip("-") or "project"
    path = directory / f"budget-{slug}.png"
    path.write_bytes(png)
    path.chmod(0o644)
    return path
