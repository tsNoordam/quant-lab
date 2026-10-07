import numpy as np
import pandas as pd

from quant_lab.strategies.parity_zscore import spread_positions


def positions(values, entry=2.0, exit_=0.5):
    return spread_positions(pd.Series(values, dtype=float), entry_z=entry, exit_z=exit_).tolist()


def test_short_spread_holds_until_inside_exit_band():
    assert positions([2.5, 1.5, 0.6, 0.4]) == [-1, -1, -1, 0]


def test_long_spread_holds_until_inside_exit_band():
    assert positions([-2.5, -1.0, -0.4]) == [1, 1, 0]


def test_crossing_the_opposite_threshold_flips_directly():
    assert positions([2.5, -2.5]) == [-1, 1]


def test_missing_signal_while_in_a_position_closes_it():
    assert positions([2.5, np.nan, 1.0]) == [-1, 0, 0]


def test_zero_exit_band_closes_on_the_mean_crossing():
    assert positions([2.5, 0.1, -0.1], exit_=0.0) == [-1, -1, 0]
