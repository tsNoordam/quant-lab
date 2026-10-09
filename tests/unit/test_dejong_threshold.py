"""The de Jong threshold rule as a lab strategy agrees with the paper engine."""

import numpy as np
import pandas as pd
import pytest

from quant_lab.backtest.dejong import find_positions
from quant_lab.strategies.dejong_threshold import threshold_positions


def _d(values):
    return pd.Series(values, index=pd.bdate_range("2000-01-03", periods=len(values)), dtype=float)


def test_crossing_exit_and_horizon():
    d = _d([0.12, 0.11, 0.08, 0.11, 0.09, 0.06, 0.04, 0.0])
    pos = threshold_positions(d, buy=0.10, sell=0.05, horizon=None, entry_gap=0)
    # day 0 is above b without a crossing; entry on close 3 (short A), exit on close 6
    assert pos.tolist() == [0, 0, 0, -1, -1, -1, 0, 0]
    cut = threshold_positions(_d([0.0, 0.11, 0.12, 0.12, 0.12]), buy=0.1, sell=0.05, horizon=2,
                              entry_gap=0)  # fmt: skip
    assert cut.tolist() == [0, 1 * -1, -1, 0, 0]
    with pytest.raises(ValueError):
        threshold_positions(d, buy=0.05, sell=0.10, horizon=None, entry_gap=0)


def test_missing_deviation_is_flat():
    d = _d([0.0, 0.11, np.nan, 0.12])
    assert threshold_positions(d, buy=0.1, sell=0.05, horizon=None, entry_gap=0).tolist() == [
        0,
        -1,
        0,
        0,
    ]


@pytest.mark.parametrize("gap", [0, 22])
def test_same_entries_and_exits_as_the_paper_engine(gap):
    rng = np.random.default_rng(7)
    d = np.zeros(3000)
    for t in range(1, len(d)):  # mean-reverting deviation, stationary sd about 8%
        d[t] = 0.97 * d[t - 1] + rng.normal(0, 0.02)
    pos = threshold_positions(_d(d), buy=0.10, sell=0.05, horizon=260, entry_gap=gap).to_numpy()
    paper = find_positions(d, buy=0.10, sell=0.05, horizon=260, last_entry=len(d) - 1,
                           close_at_end=True, entry_gap=gap, delay=0)  # fmt: skip
    assert len(paper) > 5
    for p in paper:
        assert pos[p.entry] == p.direction  # decided on the entry close
        assert (pos[p.entry : p.exit] == p.direction).all()
        if not p.forced:
            assert pos[p.exit] == 0  # flat from the exit close
    # a position still open on the last close is held there (the engine flattens at
    # the period end); the paper engine counts that close as its exit
    assert (pos != 0).sum() == sum(p.exit - p.entry + p.forced for p in paper)
