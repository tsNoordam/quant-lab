"""Dividend cash flows for total-return P&L accounting.

Fills and marks use unadjusted closes, so the ex-date price drop is in the
price P&L; the dividend itself must be booked separately:

- a long position receives the dividend net of withholding tax;
- a short position pays the full (manufactured) dividend to the stock lender.

The dividend per share on ex-date t is implied by the total-return series:

    D_t = close_{t-1} * adj_close_t / adj_close_{t-1} - close_t

Only residuals above ``min_yield`` x close_{t-1} count as dividends; smaller
ones are rounding noise between the price and total-return indices
([IMPLEMENTATION-ASSUMPTION], threshold in ``data.dividends.min_yield``).

The holder of record is the position at the previous close: shares bought on
the ex-date (filled at its close) do not receive that dividend.
"""

import pandas as pd
from omegaconf import DictConfig

from quant_lab.backtest.costs import LEGS


def dividends_per_share(panel: pd.DataFrame, leg: str, min_yield: float) -> pd.Series:
    """Implied cash dividend per share on each ex-date (0 elsewhere)."""
    close, adj = panel[f"close_{leg}"], panel[f"adj_close_{leg}"]
    prev = close.shift()
    dps = prev * adj / adj.shift() - close
    return dps.where(dps > min_yield * prev, 0.0).fillna(0.0)


def dividend_cash(shares: pd.DataFrame, dps: pd.DataFrame, withholding: dict) -> pd.Series:
    """Net dividend cash per day for end-of-bar share positions ``shares`` (one column per leg)."""
    held = shares.shift(fill_value=0.0)  # holder of record: position at the previous close
    flows = {
        leg: held[leg].clip(lower=0.0) * dps[leg] * (1 - withholding[leg])
        + held[leg].clip(upper=0.0) * dps[leg]
        for leg in shares.columns
    }
    return pd.DataFrame(flows).sum(axis=1)


def settings(data_cfg: DictConfig) -> tuple[float, dict[str, float]]:
    """``(min_yield, withholding per leg)`` from ``data.dividends``."""
    d = data_cfg.dividends
    return float(d.min_yield), {leg: float(d.withholding[leg]) for leg in LEGS}


def per_share_frame(panel: pd.DataFrame, rows: pd.Index, min_yield: float) -> pd.DataFrame:
    return pd.DataFrame({leg: dividends_per_share(panel, leg, min_yield) for leg in LEGS}).loc[rows]
