"""Falsification tests for the step-23 audit (research/reports/audits/2026-10-12-orb-track-a.md).

Each test settles one finding of the backtest-auditor or the red team; a
test that failed before its fix documents a CONFIRMED finding and now
guards against regression.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_lab.backtest import orb as b

ROOT = Path(__file__).resolve().parents[2]
TICK = 0.25


def range_then(path):
    closes = np.array([100.25, 100.75] * 7 + [100.5] + list(path))
    o = np.r_[closes[0], closes[:-1]]
    return np.arange(len(closes)), o, closes + 0.25, closes - 0.25, closes


# RT-1: a target the price has already passed at entry must not be filled at
# the target (below a long entry): a limit beyond the market is marketable and
# fills at the market, like any market exit.
@pytest.mark.parametrize("slip", [0, 1])
def test_passed_target_fills_at_the_market_not_behind_the_entry(slip):
    m, o, h, lo, c = range_then([101.75] * 5 + [102.5, 103.0] + [103.0] * 10)
    rng = b.opening_range(m, h, lo, c, 15, 5)
    conf = {"rule": "R1", "window": 15, "stop": "midpoint", "target": "ext50"}  # ext50 = 101.5
    ex = b.Exec(TICK, slippage_ticks=slip, trade_through_ticks=1)
    (t,) = b.session_trades((m, o, h, lo, c), {15: rng}, np.nan, conf, ex, step=5, min_gap_ticks=1, q_height=None)
    assert t["reason"] == "target" and t["exit_minute"] == t["entry_minute"]
    # entry at the open (101.75) + slip, exit at the same open - slip: only the slippage is lost
    assert t["fill_pts"] == pytest.approx(-2 * slip * TICK)


# RT-8: a session without bars must not remove the next sessions from trading
# through the rolling liquidity statistics.
def test_a_session_without_bars_does_not_exclude_the_following_sessions():
    cfg = b.load_config(ROOT)
    idx = pd.bdate_range("2015-01-05", periods=80)
    s = pd.DataFrame({"close": 2000.0, "prev_close": 2000.0, "volume": 1_000_000.0}, index=idx)
    s["close"] += np.arange(80) % 3  # some variation for the volatility
    s.loc[idx[40], ["close", "prev_close", "volume"]] = np.nan  # no bars that day
    imp = b.impact_points(s, cfg)
    after = imp.iloc[41:61]
    assert after.notna().all(), f"{int(after.isna().sum())} sessions silently excluded"
