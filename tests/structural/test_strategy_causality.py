"""Signals use only past and current closes; fills happen one bar later."""

import pandas as pd
import pytest

from quant_lab.backtest.run import Period, execution_targets
from quant_lab.strategies.parity_zscore import target_positions

DATES = pd.bdate_range("2020-01-01", periods=120)


@pytest.fixture
def panel(ohlcv):
    a, b = ohlcv(DATES, seed=1), ohlcv(DATES, seed=2)
    return a.add_suffix("_a").join(b.add_suffix("_b"))


def test_decisions_ignore_future_prices(panel):
    base, _ = target_positions(panel, window=20, entry_z=1.0, exit_z=0.2)
    for cutoff in DATES[30:-1:7]:
        shocked = panel.copy()
        shocked.loc[shocked.index > cutoff, ["close_a", "open_a"]] *= 1.5
        perturbed, _ = target_positions(shocked, window=20, entry_z=1.0, exit_z=0.2)
        pd.testing.assert_series_equal(base.loc[:cutoff], perturbed.loc[:cutoff])


def test_position_held_from_open_t_is_the_decision_from_close_t_minus_1():
    decisions = pd.Series([0, 1, 1, -1, 0, 1, 1, 0], index=DATES[:8])
    period = Period("train", DATES[0], DATES[7])
    held, _ = execution_targets(decisions, period, leg_weight=0.5)
    expected = decisions.shift(1).fillna(0).astype(int)
    expected.iloc[-1] = 0  # flat at the end of the period
    pd.testing.assert_series_equal(held, expected, check_names=False)


def test_period_starts_flat_even_if_a_signal_was_live_before_it():
    decisions = pd.Series([1, 1, 1, 1, 1], index=DATES[:5])
    held, orders = execution_targets(decisions, Period("v", DATES[2], DATES[4]), 0.5)
    assert held.tolist() == [0, 1, 0]
    assert orders["a"].tolist()[1] == 0.5 and orders["b"].tolist()[1] == -0.5
