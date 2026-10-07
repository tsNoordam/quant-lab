"""Quote quality on the real development data (re-audit 2026-10-07, B6).

Skipped unless the processed panels are present (`uv run dvc pull && uv run dvc repro`).
Only train + validation years are read.
"""

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "rd_shell" / "panel.parquet"

pytestmark = pytest.mark.skipif(not PANEL.exists(), reason="rd_shell panel not present")


def quarterly_median_half_spread(panel, leg):
    bid, ask = panel[f"bid_{leg}"], panel[f"ask_{leg}"]
    half = ((ask - bid) / ((ask + bid) / 2) / 2).where(ask > bid)
    return half.groupby(pd.Grouper(freq="QE")).median()


@pytest.mark.xfail(
    strict=True,
    reason="re-audit 2026-10-07 B6 CONFIRMED: RD 1997-Q2..1998-Q1 quotes 4-8x Shell's; "
    "costed as quoted (conservative) pending a sourced decision; validation warns",
)
def test_rd_quotes_have_no_implausibly_wide_regime():
    panel = pd.read_parquet(PANEL).loc["1996":"1999"]
    ratio = (
        quarterly_median_half_spread(panel, "a") / quarterly_median_half_spread(panel, "b")
    ).dropna()
    assert (ratio <= 3.0).all(), f"RD quarterly median half-spread up to {ratio.max():.1f}x Shell"
