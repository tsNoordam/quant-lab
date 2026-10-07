"""Static report figures logged to MLflow as artifacts."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SERIES = "#2a78d6"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#e4e3df"


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def plot_equity(equity: pd.Series, title: str, path: Path) -> Path:
    """Equity (indexed to 1) and drawdown as two stacked panels sharing the date axis."""
    growth = equity / equity.iloc[0]
    drawdown = equity / equity.cummax() - 1.0

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1.2]}
    )
    fig.patch.set_facecolor(SURFACE)
    for ax in (top, bottom):
        _style(ax)

    top.plot(growth.index, growth.to_numpy(), color=SERIES, linewidth=2)
    top.axhline(1.0, color=INK_MUTED, linewidth=0.8)
    top.set_ylabel("Equity (start = 1)", color=INK_MUTED, fontsize=9)
    top.set_title(title, color=INK, fontsize=11, loc="left")

    bottom.fill_between(drawdown.index, drawdown.to_numpy(), 0.0, color=SERIES, alpha=0.35)
    bottom.plot(drawdown.index, drawdown.to_numpy(), color=SERIES, linewidth=1)
    bottom.set_ylabel("Drawdown", color=INK_MUTED, fontsize=9)
    bottom.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))

    fig.tight_layout()
    fig.savefig(path, dpi=120, facecolor=SURFACE)
    plt.close(fig)
    return path
