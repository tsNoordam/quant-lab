"""Read raw per-symbol daily files.

Raw layout: ``<raw_dir>/<SYMBOL>.csv``, one row per trading day, dates in
exchange-local time without a timezone. Columns:

    required   date, close, adj_close, volume
    bars       open, high, low        (all three or none; close-only vendors omit them)
    quotes     bid, ask               (optional; may be empty on days without a quote)

Loaders do not sort, deduplicate or fill: validation must see the file exactly
as the vendor delivered it.
"""

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ("close", "adj_close", "volume")
BAR_COLUMNS = ("open", "high", "low")
QUOTE_COLUMNS = ("bid", "ask")
COLUMN_ORDER = ("open", "high", "low", "close", "adj_close", "volume", "bid", "ask")


def load_symbol(raw_dir: Path | str, symbol: str) -> pd.DataFrame:
    path = Path(raw_dir) / f"{symbol}.csv"
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    bars = [c for c in BAR_COLUMNS if c in df.columns]
    if bars and len(bars) != len(BAR_COLUMNS):
        raise ValueError(f"{path}: has {bars} but bars need all of {list(BAR_COLUMNS)}")
    return df.loc[:, [c for c in COLUMN_ORDER if c in df.columns]]
