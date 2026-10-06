"""Read raw per-symbol OHLCV files.

Raw layout: ``<raw_dir>/<SYMBOL>.csv`` with columns
``date, open, high, low, close, adj_close, volume`` (one row per trading day,
dates in exchange-local time without a timezone).

Loaders do not sort, deduplicate or fill: validation must see the file exactly
as the vendor delivered it.
"""

from pathlib import Path

import pandas as pd

OHLCV_COLUMNS = ("open", "high", "low", "close", "adj_close", "volume")


def load_symbol(raw_dir: Path | str, symbol: str) -> pd.DataFrame:
    path = Path(raw_dir) / f"{symbol}.csv"
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    return df.loc[:, list(OHLCV_COLUMNS)]
