import numpy as np
import pandas as pd
import pytest

from quant_lab.strategies.parity_zscore import relative_price, spread_positions


def positions(values, entry=2.0, exit_=0.5):
    z = pd.Series(values, dtype=float)
    return spread_positions(z, entry_z=entry, exit_z=exit_).tolist()


def test_rich_leg_a_opens_short_spread():
    assert positions([0.0, 2.1]) == [0, -1]


def test_cheap_leg_a_opens_long_spread():
    assert positions([0.0, -2.1]) == [0, 1]


def test_threshold_must_be_exceeded():
    assert positions([2.0, -2.0]) == [0, 0]


def test_no_signal_during_warm_up():
    assert positions([np.nan, np.nan, 2.5]) == [0, 0, -1]


def test_relative_price_is_log_close_ratio():
    panel = pd.DataFrame({"close_a": [150.0, 165.0], "close_b": [100.0, 100.0]})
    np.testing.assert_allclose(relative_price(panel), np.log([1.5, 1.65]))


@pytest.mark.parametrize(("entry", "exit_"), [(1.0, 1.0), (1.0, 2.0), (1.0, -0.1)])
def test_invalid_thresholds_raise(entry, exit_):
    with pytest.raises(ValueError):
        positions([0.0], entry, exit_)
