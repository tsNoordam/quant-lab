"""Independent reference bookkeeping for VectorBT backtests.

VectorBT is fast but opaque. These plain-Python functions recompute what its
results must be from first principles, so tests/integration can reconcile:

- fill prices: every executed order's price must equal the raw execution price
  moved against us by exactly the cost fraction we asked for;
- fees: commission must equal fee rate x executed notional;
- equity: replaying the executed orders through a simple cash + positions ledger,
  marked at the close, with borrow and dividend cash, must reproduce the
  backtest's net equity.
"""

import numpy as np
import pandas as pd


def expected_fill_prices(
    raw_price: pd.DataFrame, cost: pd.DataFrame, side: pd.DataFrame
) -> pd.DataFrame:
    """Buy fills at price x (1 + cost), sell fills at price x (1 - cost). ``side`` is +1/-1."""
    return raw_price * (1 + side * cost)


def replay_equity(
    orders: pd.DataFrame,
    close: pd.DataFrame,
    init_cash: float,
    borrow: pd.Series | None = None,
    dividends_per_share: pd.DataFrame | None = None,
    withholding: dict | None = None,
) -> pd.Series:
    """Mark-to-market equity from executed orders.

    ``orders`` columns: date, leg, size (shares, signed: + buy / - sell), price, fees.
    ``close`` is indexed by date with one column per leg. ``borrow`` (optional) is a
    daily charge subtracted cumulatively from cash. ``dividends_per_share`` (optional,
    same shape as ``close``) is paid on the shares held before the day's orders:
    longs receive it net of ``withholding[leg]``, shorts pay it in full.
    """
    cash = init_cash
    shares = dict.fromkeys(close.columns, 0.0)
    by_date = {d: g for d, g in orders.groupby("date")}
    equity = np.empty(len(close))
    for i, (date, row) in enumerate(close.iterrows()):
        if dividends_per_share is not None:
            for leg, n in shares.items():
                d = n * dividends_per_share.loc[date, leg]
                cash += d * (1 - withholding[leg]) if n > 0 else d
        for order in by_date.get(date, pd.DataFrame()).itertuples():
            cash -= order.size * order.price + order.fees
            shares[order.leg] += order.size
        if borrow is not None:
            cash -= borrow.get(date, 0.0)
        equity[i] = cash + sum(shares[leg] * row[leg] for leg in close.columns)
    return pd.Series(equity, index=close.index, name="equity")
