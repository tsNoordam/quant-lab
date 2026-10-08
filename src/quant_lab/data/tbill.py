"""3-month US Treasury bill rate (FRED series DTB3), the paper's padding rate.

The raw file is FRED's own CSV export, unmodified, in ``data/raw/fred_tbill/``
(DVC, metadata in ``data/metadata/fred_tbill.json``):

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3

Columns: a date column (``observation_date``, or ``DATE`` in older exports)
and ``DTB3`` in percent per year on a discount basis; FRED marks holidays with
"." or an empty field. Values are returned as decimals; a rate is looked up as
of a date (the last observation on or before it), never from a later day.
"""

from pathlib import Path

import pandas as pd

DATE_COLUMNS = ("observation_date", "DATE")


def load_tbill(path: Path, series: str = "DTB3") -> pd.Series:
    raw = pd.read_csv(path, dtype=str)
    date_col = next((c for c in DATE_COLUMNS if c in raw.columns), None)
    if date_col is None or series not in raw.columns:
        raise ValueError(f"{path} is not a FRED {series} export (columns {list(raw.columns)})")
    dates = pd.to_datetime(raw[date_col], format="%Y-%m-%d")
    values = pd.to_numeric(raw[series].str.strip().replace({".": None, "": None}))
    rate = pd.Series(values.to_numpy() / 100, index=dates, name=series).dropna()
    if not rate.index.is_monotonic_increasing or rate.index.has_duplicates:
        raise ValueError(f"{path}: dates are not strictly increasing")
    if not ((rate > -0.01) & (rate < 0.25)).all():
        raise ValueError(f"{path}: rates outside -1%..25% per year")
    return rate


def rate_on(rate: pd.Series, date: pd.Timestamp) -> float:
    """The last observed rate on or before ``date``."""
    upto = rate.loc[:date]
    if upto.empty:
        raise ValueError(f"no T-bill observation on or before {date.date()}")
    return float(upto.iloc[-1])
