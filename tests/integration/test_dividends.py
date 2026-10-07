"""P&L must be dividend-consistent (audit 2026-10-07, finding A1).

A short position held across an ex-dividend date pays the (manufactured)
dividend; it must not book the ex-date price drop as a gain. With close falling
by the dividend and adj_close continuous, a zero-cost short-A / long-B position
in otherwise flat prices earns nothing economically. A long receives the
dividend net of withholding tax.
"""

from pathlib import Path

import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest.dividends import dividends_per_share
from quant_lab.backtest.run import Period, backtest_pair

ROOT = Path(__file__).resolve().parents[2]
DIVIDEND = 0.03
EX_DATE = 50


def zero_cost_config(*overrides):
    with initialize_config_dir(config_dir=str(ROOT / "conf"), version_base="1.3"):
        return compose(
            "config",
            overrides=[
                "costs=flat_bps",
                "costs.fee_bps=0",
                "costs.slippage_bps=0",
                "backtest.execution=next_close",
                *overrides,
            ],
        )


def flat_pair_with_ex_dividend(n: int = 100) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=n)
    panel = pd.DataFrame(
        {
            "close_a": 100.0,
            "adj_close_a": 100.0,
            "volume_a": 1e6,
            "close_b": 100.0,
            "adj_close_b": 100.0,
            "volume_b": 1e6,
        },
        index=idx,
    )
    # Ex-date: the price drops by the dividend; the total-return series (price plus
    # dividend) stays flat, so adj_close is left unchanged.
    panel.iloc[EX_DATE:, panel.columns.get_loc("close_a")] *= 1 - DIVIDEND
    return panel


def pnl(position: int, first_decision: int, *overrides) -> float:
    cfg = zero_cost_config(*overrides)
    panel = flat_pair_with_ex_dividend()
    decisions = pd.Series(0, index=panel.index)
    decisions.iloc[first_decision:80] = position
    period = Period("p", panel.index[0], panel.index[-1])
    sim = backtest_pair(panel, decisions, period, cfg)
    return sim.equity.iloc[-1] / cfg.backtest.init_cash - 1


def test_short_leg_pays_the_ex_dividend():
    # short A / long B across A's ex-date: before the fix about +leg_weight * DIVIDEND
    assert abs(pnl(-1, 10)) < 1e-9


def test_long_leg_receives_the_dividend_net_of_withholding():
    w = 0.5  # strategy.leg_weight
    assert pnl(1, 10, "data.dividends.withholding.a=0.0") == pytest.approx(0.0, abs=1e-9)
    taxed = pnl(1, 10, "data.dividends.withholding.a=0.15")
    assert taxed == pytest.approx(-w * DIVIDEND * 0.15, rel=1e-6)


def test_shares_bought_on_the_ex_date_do_not_receive_the_dividend():
    # Decision on EX_DATE - 1 -> filled at the ex-date close, after the drop.
    assert pnl(1, EX_DATE - 1) == pytest.approx(0.0, abs=1e-9)


def test_dividends_are_implied_from_total_return_above_the_noise_threshold():
    panel = flat_pair_with_ex_dividend()
    dps = dividends_per_share(panel, "a", min_yield=0.005)
    assert dps.iloc[EX_DATE] == pytest.approx(100 * DIVIDEND)
    assert (dps.drop(panel.index[EX_DATE]) == 0).all()
    assert (dividends_per_share(panel, "b", min_yield=0.005) == 0).all()
    # a residual below min_yield is rounding noise, not a dividend
    noisy = panel.copy()
    noisy.iloc[70:, noisy.columns.get_loc("close_b")] *= 0.999
    assert (dividends_per_share(noisy, "b", min_yield=0.005) == 0).all()
