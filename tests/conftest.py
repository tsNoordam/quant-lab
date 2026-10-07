import numpy as np
import pandas as pd
import pytest


def make_ohlcv(dates, closes=None, seed: int = 0) -> pd.DataFrame:
    """A clean, internally consistent daily OHLCV frame."""
    dates = pd.DatetimeIndex(dates, name="date")
    rng = np.random.default_rng(seed)
    if closes is None:
        closes = 100 * np.exp(np.cumsum(0.01 * rng.standard_normal(len(dates))))
    close = np.asarray(closes, dtype=float)
    open_ = close * (1 + 0.002 * rng.standard_normal(len(dates)))
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * 1.01,
            "low": np.minimum(open_, close) * 0.99,
            "close": close,
            "adj_close": close,
            "volume": rng.integers(1_000, 10_000, len(dates)),
        },
        index=dates,
    )


@pytest.fixture
def ohlcv():
    return make_ohlcv
