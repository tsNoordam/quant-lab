"""Cost inputs and entry sizes for an order filled on bar t+1 come only from data up to close t.

The perturbation starts exactly on each fill bar, so a model that read the fill
bar's own statistics (instead of the decision close's) changes that order's cost
and fails the test.
"""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest import costs
from quant_lab.backtest.run import Period, execution_targets

DATES = pd.bdate_range("2020-01-01", periods=80)
CFG = OmegaConf.create(
    {
        "spread": {"lookback_days": 5, "min_quote_days": 3, "fallback_half_spread_bps": 10.0},
        "impact": {"coefficient": 1.0, "vol_lookback_days": 10, "adv_lookback_days": 5},
        "buy_tax_bps": 0.0,
        "limits": {"max_participation": 0.15},
    }
)
CAPITAL = 5e7  # large enough that the participation cap binds on some entries


@pytest.fixture
def panel(ohlcv):
    a, b = ohlcv(DATES, seed=3), ohlcv(DATES, seed=4)
    for df in (a, b):
        df["bid"] = df["close"] * 0.999
        df["ask"] = df["close"] * 1.001
    return a.add_suffix("_a").join(b.add_suffix("_b"))


def orders_and_costs(panel):
    decisions = pd.Series(np.where(np.arange(len(DATES)) % 20 < 10, 1, -1), index=DATES)
    stats = {leg: costs.market_stats(panel, leg, CFG) for leg in costs.LEGS}
    cap = costs.participation_cap(stats, CAPITAL, 0.15)
    _, orders = execution_targets(decisions, Period("p", DATES[0], DATES[-1]), 0.5, cap)
    at_fill = {leg: st.shift(1).reindex(orders.index) for leg, st in stats.items()}
    return orders, costs.order_costs(orders, at_fill, CAPITAL, CFG)


def test_fill_bar_and_later_data_do_not_change_costs_or_sizes(panel):
    base_orders, base_cost = orders_and_costs(panel)
    fills = base_cost.index[base_cost.notna().any(axis=1)]
    assert len(fills) >= 4
    assert (base_orders.abs().max(axis=1).dropna() < 0.5).any(), "cap never binds: weak test"

    cols = [c for c in panel if c.split("_")[0] in {"close", "bid", "ask", "volume"}]
    for fill in fills:
        shocked = panel.copy()
        shocked.loc[shocked.index >= fill, cols] *= 3.0  # the fill bar itself and later
        orders, cost = orders_and_costs(shocked)
        pd.testing.assert_frame_equal(base_orders.loc[:fill], orders.loc[:fill])
        pd.testing.assert_frame_equal(base_cost.loc[:fill], cost.loc[:fill])
