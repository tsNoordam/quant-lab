import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest import costs

DATES = pd.bdate_range("2020-01-01", periods=8)
CFG = OmegaConf.create(
    {
        "commission_bps": 5.0,
        "spread": {"lookback_days": 3, "min_quote_days": 2, "fallback_half_spread_bps": 10.0},
        "impact": {"coefficient": 1.0, "vol_lookback_days": 3, "adv_lookback_days": 2},
        "borrow_bps_annual": 50.0,
        "buy_tax_bps": 50.0,
        "limits": {"max_participation": 0.15},
    }
)


def panel(with_quotes=True):
    close = [100.0, 101, 99, 100, 102, 101, 100, 99]
    df = pd.DataFrame(
        {"close_a": close, "volume_a": [1000.0] * 8, "close_b": close, "volume_b": [4000.0] * 8},
        index=DATES,
    )
    if with_quotes:
        df["bid_a"] = [c - 0.1 for c in close]  # spread 0.2 on ~100: half-spread ~10 bps
        df["ask_a"] = [c + 0.1 for c in close]
    return df


def test_half_spread_comes_from_quotes_when_available():
    stats = costs.market_stats(panel(), "a", CFG)
    assert stats["half_spread"].iloc[2] == pytest.approx(0.1 / 99, rel=0.02)
    assert stats["quoted"].iloc[2]


def test_half_spread_falls_back_without_quotes():
    stats = costs.market_stats(panel(with_quotes=False), "a", CFG)
    assert (stats["half_spread"] == 0.001).all()
    assert not stats["quoted"].any()


def test_stats_use_only_data_up_to_each_close():
    stats = costs.market_stats(panel(), "a", CFG)
    # 3-day window at t=3: the returns into t-2, t-1 and t, i.e. closes t-3..t
    expected_sigma = np.log(pd.Series([100.0, 101, 99, 100])).diff().std()
    assert stats["sigma"].iloc[3] == pytest.approx(expected_sigma)
    assert np.isnan(stats["adv"].iloc[0]) and stats["adv"].iloc[1] == 1000.0


def test_participation_cap_is_the_tighter_leg():
    stats = {"a": costs.market_stats(panel(), "a", CFG), "b": costs.market_stats(panel(), "b", CFG)}
    cap = costs.participation_cap(stats, capital=1_000.0, max_participation=0.15)
    # leg a: 0.15 * 1000 shares * close / 1000 capital
    assert cap.iloc[2] == pytest.approx(0.15 * 1000 * 99 / 1000)
    assert np.isnan(cap.iloc[0])


def test_order_cost_formula():
    stats = pd.DataFrame(
        {"half_spread": 0.001, "sigma": 0.02, "adv": 10_000.0, "price": 50.0, "quoted": True},
        index=DATES[:3],
    )
    orders = pd.DataFrame({"a": [0.5, np.nan, 0.0], "b": [-0.5, np.nan, 0.0]}, index=DATES[:3])
    cost = costs.order_costs(orders, {"a": stats, "b": stats}, 1_000_000.0, CFG)
    shares = 0.5 * 1_000_000 / 50.0  # 10_000 = 100% of ADV
    impact = 0.02 * np.sqrt(shares / 10_000.0)
    assert cost.loc[DATES[0], "a"] == pytest.approx(0.001 + impact + 0.005)  # buy: + stamp duty
    assert cost.loc[DATES[0], "b"] == pytest.approx(0.001 + impact)  # sell: no tax
    assert cost.loc[DATES[1]].isna().all()  # no order, no cost
    assert cost.loc[DATES[2], "b"] == pytest.approx(0.001 + impact + 0.005)  # covering short = buy


def test_impact_grows_with_the_square_root_of_size():
    stats = pd.DataFrame(
        {"half_spread": 0.0, "sigma": 0.02, "adv": 1e6, "price": 1.0, "quoted": True},
        index=DATES[:1],
    )
    cfg = OmegaConf.merge(CFG, {"buy_tax_bps": 0.0})
    small = costs.order_costs(
        pd.DataFrame({"a": [0.1], "b": [0.1]}, index=DATES[:1]), {"a": stats, "b": stats}, 1e6, cfg
    )
    large = costs.order_costs(
        pd.DataFrame({"a": [0.4], "b": [0.4]}, index=DATES[:1]), {"a": stats, "b": stats}, 1e6, cfg
    )
    assert large.iloc[0, 0] == pytest.approx(2 * small.iloc[0, 0])


def test_borrow_charges_accrue_on_the_short_value():
    charges = costs.borrow_charges(pd.Series([-500_000.0, 0.0]), 50.0, 252)
    assert charges.tolist() == pytest.approx([500_000 * 0.005 / 252, 0.0])
