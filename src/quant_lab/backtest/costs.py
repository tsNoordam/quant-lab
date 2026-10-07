"""Liquidity-scaled transaction costs, borrow cost and participation limits.

Per order, as a fraction of traded notional (applied by VectorBT as an adverse
move of the fill price):

    cost = half_spread + k * sigma * sqrt(shares / ADV) + buy_tax (purchases only)
           + fx_conversion (legs quoted in a foreign currency)

plus a flat commission (``fees``) and a daily borrow charge on the short leg.

Timing: every statistic is computed "as of close t" from data up to and
including t. The backtest uses the stats of the decision close t for the order
filled on bar t+1, so no cost input ever uses information from the fill bar or
later (asserted in tests/structural/test_cost_causality.py).
"""

import numpy as np
import pandas as pd
from omegaconf import DictConfig

LEGS = ("a", "b")


def market_stats(panel: pd.DataFrame, leg: str, cfg: DictConfig) -> pd.DataFrame:
    """Per-day liquidity statistics of one leg, as of each close.

    half_spread  rolling median quoted half-spread (fraction of mid), falling back to
                 ``spread.fallback_half_spread_bps`` without enough recent quotes;
                 locked (bid == ask) and crossed quotes count as missing
    sigma        rolling std of daily log close returns
    adv          rolling mean daily volume, in shares
    price        close (used to convert notional into shares)
    """
    close = panel[f"close_{leg}"]
    sp = cfg.spread
    if f"bid_{leg}" in panel and f"ask_{leg}" in panel:
        bid, ask = panel[f"bid_{leg}"], panel[f"ask_{leg}"]
        quoted = ((ask - bid) / ((ask + bid) / 2) / 2).where(ask > bid)
    else:
        quoted = pd.Series(np.nan, index=panel.index)
    half_spread = quoted.rolling(sp.lookback_days, min_periods=sp.min_quote_days).median()
    fallback = sp.fallback_half_spread_bps / 1e4
    imp = cfg.impact
    return pd.DataFrame(
        {
            "half_spread": half_spread.fillna(fallback),
            "quoted": half_spread.notna(),
            "sigma": np.log(close).diff().rolling(imp.vol_lookback_days).std(),
            "adv": panel[f"volume_{leg}"].rolling(imp.adv_lookback_days).mean(),
            "price": close,
        }
    )


def participation_cap(stats: dict[str, pd.DataFrame], capital: float, max_participation: float):
    """Largest |leg weight| an entry may take so neither leg trades more than
    ``max_participation`` x ADV in one day. NaN while ADV is still warming up."""
    caps = [max_participation * s["adv"] * s["price"] / capital for s in stats.values()]
    return pd.concat(caps, axis=1).min(axis=1, skipna=False)


def order_costs(
    orders: pd.DataFrame,
    stats_at_fill: dict[str, pd.DataFrame],
    capital: float,
    cfg: DictConfig,
    fx_legs: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Cost fraction for each order (NaN where there is no order).

    ``orders`` holds target weights per leg (NaN = no order); ``stats_at_fill``
    must already be shifted so that the row of a fill carries the decision-day
    stats. Order size uses ``capital`` as the equity scale. Orders in ``fx_legs``
    (quoted in a foreign currency) also pay ``fx_conversion_bps``.
    """
    out = {}
    for leg in LEGS:
        target = orders[leg]
        held = target.ffill().fillna(0.0)
        delta = (held - held.shift(fill_value=0.0)).where(target.notna())
        s = stats_at_fill[leg].reindex(orders.index)
        shares = delta.abs() * capital / s["price"]
        impact = cfg.impact.coefficient * s["sigma"] * np.sqrt(shares / s["adv"])
        buy_tax = np.where(delta > 0, cfg.buy_tax_bps / 1e4, 0.0)
        fx = cfg.fx_conversion_bps / 1e4 if leg in fx_legs else 0.0
        cost = s["half_spread"] + impact + buy_tax + fx
        traded = delta.abs() > 0
        if cost[traded].isna().any():
            missing = cost[traded].isna()
            raise ValueError(
                f"leg {leg}: {int(missing.sum())} orders without cost statistics, first on "
                f"{missing.idxmax().date()}; an order must never be filled at zero cost"
            )
        out[leg] = cost.where(traded)
    return pd.DataFrame(out)


def statistics_ready(stats: dict[str, pd.DataFrame]) -> pd.Series:
    """True on closes where every leg's sigma, ADV and price are defined."""
    cols = ["sigma", "adv", "price"]
    return pd.concat([s[cols].notna().all(axis=1) for s in stats.values()], axis=1).all(axis=1)


def fx_legs(data_cfg: DictConfig) -> tuple[str, ...]:
    """Legs converted into the dataset currency (``fx_per_unit`` in their source)."""
    source = data_cfg.get("source") or {}
    return tuple(leg for leg in LEGS if "fx_per_unit" in (source.get("legs") or {}).get(leg, {}))


def borrow_charges(short_value: pd.Series, borrow_bps_annual: float, ann: int) -> pd.Series:
    """Daily borrow fee on the absolute value of short positions (accrued at each close)."""
    return short_value.abs() * borrow_bps_annual / 1e4 / ann
