"""Align the two legs of a pair on a common daily index.

Both policies are causal: a row only ever uses that leg's own past. There is no
backward fill and no interpolation, so a future observation can never leak into
an earlier row (asserted in tests/structural/).
"""

from typing import Literal

import pandas as pd

from quant_lab.data.loaders import OHLCV_COLUMNS

MissingPolicy = Literal["drop", "ffill"]


def align_pair(
    a: pd.DataFrame,
    b: pd.DataFrame,
    *,
    missing_policy: MissingPolicy,
    ffill_limit: int = 0,
) -> pd.DataFrame:
    """Return a panel with ``<col>_a``, ``<col>_b`` and boolean ``stale_a``/``stale_b`` columns.

    drop:  keep only dates on which both legs traded.
    ffill: keep dates on which either leg traded; carry a missing leg's last close
           forward for at most ``ffill_limit`` days as a no-trade bar
           (open = high = low = close, volume = 0, stale = True). Dates still
           missing after that are dropped.
    """
    a = a.loc[:, list(OHLCV_COLUMNS)].add_suffix("_a")
    b = b.loc[:, list(OHLCV_COLUMNS)].add_suffix("_b")

    if missing_policy == "drop":
        panel = a.join(b, how="inner")
        panel["stale_a"] = False
        panel["stale_b"] = False
        return panel

    if missing_policy != "ffill":
        raise ValueError(f"unknown missing_policy {missing_policy!r}")
    if ffill_limit < 1:
        raise ValueError("missing_policy='ffill' needs ffill_limit >= 1")

    panel = a.join(b, how="outer").sort_index()
    for leg in ("a", "b"):
        stale = panel[f"close_{leg}"].isna()
        close = panel[f"close_{leg}"].ffill(limit=ffill_limit)
        panel[f"adj_close_{leg}"] = panel[f"adj_close_{leg}"].ffill(limit=ffill_limit)
        for col in ("open", "high", "low"):
            panel[f"{col}_{leg}"] = panel[f"{col}_{leg}"].fillna(close)
        panel[f"close_{leg}"] = close
        panel[f"volume_{leg}"] = panel[f"volume_{leg}"].fillna(0)
        panel[f"stale_{leg}"] = stale
    return panel.dropna(subset=["close_a", "close_b"])
