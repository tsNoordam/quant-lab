"""Opening-range breakout (step 22): the range and the breakout decision use
only bars up to the trigger bar's close; the excursion starts after it."""

import numpy as np
import pytest

from quant_lab.models.orb_stats import session_orb

TICK = 0.25


def session(seed: int):
    rng = np.random.default_rng(seed)
    c = (100 + np.cumsum(rng.normal(0, 0.3, 390)) / TICK).round() * TICK
    return np.arange(390), c + TICK, c - TICK, c


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("window", [15, 30, 60])
def test_breakout_ignores_bars_after_the_trigger(seed, window):
    m, h, lo, c = session(seed)
    base = session_orb(m, h, lo, c, window=window, step=5, tick=TICK, r_multiples=[1])
    if base is None or base["break"] == "none":
        pytest.skip("no breakout in this path")
    # the trigger bar ends at the first 5-minute close beyond the range
    after = m >= window
    rh, rl = h[m < window].max(), lo[m < window].min()
    buckets = m[after] // 5
    closes = c[after][np.r_[buckets[1:] != buckets[:-1], True]]
    ends = (np.unique(buckets) + 1) * 5
    first = np.flatnonzero((closes > rh) | (closes < rl))[0]
    t_end = ends[first]

    shocked_h, shocked_l, shocked_c = h.copy(), lo.copy(), c.copy()
    future = m >= t_end
    shocked_c[future] += 50 * base["direction"] * -1
    shocked_h[future] = shocked_c[future] + TICK
    shocked_l[future] = shocked_c[future] - TICK
    pert = session_orb(
        m, shocked_h, shocked_l, shocked_c, window=window, step=5, tick=TICK, r_multiples=[1]
    )

    assert pert["direction"] == base["direction"]
    assert pert["range_ticks"] == base["range_ticks"]


@pytest.mark.parametrize("seed", range(10))
def test_range_ignores_bars_after_the_window(seed):
    m, h, lo, c = session(seed)
    base = session_orb(m, h, lo, c, window=30, step=5, tick=TICK, r_multiples=[1])
    h2, l2 = h.copy(), lo.copy()
    h2[m >= 30] += 100
    l2[m >= 30] -= 100
    pert = session_orb(m, h2, l2, c, window=30, step=5, tick=TICK, r_multiples=[1])
    assert pert["range_ticks"] == base["range_ticks"]
