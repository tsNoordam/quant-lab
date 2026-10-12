"""Step 22 statistics on hand-built sessions with known answers."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_lab.models import orb_stats as o

ROOT = Path(__file__).resolve().parents[2]
TICK = 0.25


def bars_from(closes, *, spread=0.25, highs=None, lows=None):
    """1-minute bars (minute 0..) with the given closes; high/low +-spread."""
    c = np.asarray(closes, dtype=float)
    h = c + spread if highs is None else np.asarray(highs, dtype=float)
    lo = c - spread if lows is None else np.asarray(lows, dtype=float)
    return np.arange(len(c)), h, lo, c


def orb(closes, window=15, **kw):
    m, h, lo, c = bars_from(closes, **kw)
    return o.session_orb(m, h, lo, c, window=window, step=5, tick=TICK, r_multiples=[1, 2])


def range_then(path):
    """15 minutes inside 100..101 (closes 100.25..100.75), then ``path``."""
    return [100.25, 100.75] * 7 + [100.5] + list(path)


def test_single_upside_breakout_and_excursion():
    # minutes 15-19 close at 101.5 (beyond 101), then rise to 103
    r = orb(range_then([101.5] * 5 + [102, 102.5, 103] + [102.75] * 10))
    assert r["break"] == "single" and r["direction"] == 1
    assert r["range_ticks"] == pytest.approx((101.0 - 100.0) / TICK)
    # trigger close 101.5 at minute 20; best high 103.25 afterwards
    assert r["mfe_ticks"] == pytest.approx((103.25 - 101.5) / TICK)
    assert r["mfe_height"] == pytest.approx(1.75 / 1.0)
    # risk to midpoint 100.5 = 1.0: 1R = 102.5 reached, 2R = 103.5 not
    assert r["midpoint_1R"] == "target" and r["midpoint_2R"] == "neither"


def test_no_close_beyond_range_is_inside_even_if_touched():
    # a wick to 101.5 but every 5-minute close stays inside
    path = [100.75] * 30
    highs = [x + 0.25 for x in range_then(path)]
    highs[17] = 101.5
    r = orb(range_then(path), highs=highs)
    assert r["break"] == "none" and r["touch_up"] and not r["touch_dn"]


def test_trigger_uses_the_5_minute_close_not_a_1_minute_close():
    # minute 16 closes at 101.5, but the bucket 15-19 closes at 100.75
    path = [100.75, 101.5, 100.75, 100.75, 100.75] + [100.75] * 5 + [99.5] * 5 + [99.0] * 5
    r = orb(range_then(path))
    assert r["direction"] == -1  # the first 5-minute close outside is the downside one


def test_double_breakout():
    r = orb(range_then([101.5] * 5 + [100.5] * 5 + [99.5] * 5 + [99.0] * 5))
    assert r["break"] == "double" and r["direction"] == 1


def test_bar_touching_stop_and_target_counts_as_stopped():
    closes = range_then([101.5] * 5 + [101.5] * 3)
    m, h, lo, c = bars_from(closes)
    h[21], lo[21] = 103.0, 100.0  # one bar beyond 1R (102.5) and the midpoint (100.5)
    r = o.session_orb(m, h, lo, c, window=15, step=5, tick=TICK, r_multiples=[1])
    assert r["midpoint_1R"] == "stop"


def test_session_shorter_than_window_is_skipped():
    assert orb([100.0] * 10, window=15) is None


def test_gap_fill_definitions():
    m = np.arange(120)
    # gap up from 100 to 102: low reaches 101 (midline) at minute 30, 100 at minute 90
    low = np.full(120, 101.5)
    low[30], low[90] = 101.0, 100.0
    g = o.session_gap(m, low + 1, low, 102.0, 100.0, tick=TICK, early_minutes=60, min_ticks=1)
    assert g["gap_up"] and g["gap_pct"] == pytest.approx(2.0)
    assert g["full_fill"] and g["mid_fill"] and g["mid_fill_early"] and not g["full_fill_early"]
    # gap down from 100 to 99: high never above 99.4 -> no fill, no midline
    high = np.full(120, 99.4)
    g = o.session_gap(m, high, high - 1, 99.0, 100.0, tick=TICK, early_minutes=60, min_ticks=1)
    assert not g["gap_up"] and not g["full_fill"] and not g["mid_fill"]
    assert (
        o.session_gap(m, high, high, 100.0, 100.0, tick=TICK, early_minutes=60, min_ticks=1) is None
    )
    assert (
        o.session_gap(m, high, high, 100.0, np.nan, tick=TICK, early_minutes=60, min_ticks=1)
        is None
    )


def test_wilson_interval():
    lo, hi = o.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-4) and hi == pytest.approx(0.5962, abs=1e-4)


def synthetic_dev(cfg, days):
    rows, sess = [], []
    rng = np.random.default_rng(0)
    for i, d in enumerate(days):
        path = 100 + np.cumsum(rng.normal(0, 0.5, 390)).round(2)
        path = (path / TICK).round() * TICK
        for mnt, px in enumerate(path):
            rows.append(
                {
                    "session": d,
                    "minute": mnt,
                    "open": px,
                    "high": px + TICK,
                    "low": px - TICK,
                    "close": px,
                }
            )
        sess.append(
            {
                "session": d,
                "usable": i % 5 != 0,
                "bars": 390,
                "prev_close": path[0] - (1 if i % 2 else -1),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(sess).set_index("session")


def test_compute_reports_both_universes_and_all_periods():
    cfg = o.load_config(ROOT)
    days = list(pd.bdate_range("2015-03-02", periods=10)) + list(
        pd.bdate_range("2019-03-04", periods=10)
    )
    bars, sessions = synthetic_dev(cfg, days)
    out = o.compute(bars, sessions, cfg)
    counts = out["counts"].set_index(["period", "universe"])["sessions"]
    assert counts[("train", "with_bars")] == 10 and counts[("development", "with_bars")] == 20
    assert counts[("train", "usable")] == 8
    assert set(out["claims"]["claim"]) == {"C4", "C5", "C10", "G1", "G2", "G2m"}
    assert set(out["claims"]["period"]) == {"train", "validation", "development"}
    assert (
        out["claims"]["verdict"]
        .isin(["consistent", "lower than claimed", "higher than claimed"])
        .all()
    )
    # every gap here is 1 point: all sessions have a gap
    gd = out["gap"]
    all_dev = gd[
        (gd["period"] == "development") & (gd["universe"] == "with_bars") & (gd["bucket"] == "all")
    ]
    assert (all_dev["n"] == 20).all()


def test_out_of_sample_sessions_are_refused():
    cfg = o.load_config(ROOT)
    bars, sessions = synthetic_dev(cfg, [pd.Timestamp("2021-01-04")])
    with pytest.raises(ValueError, match="out-of-sample"):
        o.compute(bars, sessions, cfg)
    with pytest.raises(ValueError, match="OOS is locked"):
        o.period_bounds(cfg, "oos")


def test_claims_verdicts():
    cfg = o.load_config(ROOT)
    cols = ["stat", "window", "bucket", "p", "lo", "hi", "n"]
    rows = [
        ["p_inside_close", 15, np.nan, 0.05, 0.04, 0.06, 1000],
        ["p_full_fill", np.nan, "all", 0.70, 0.67, 0.73, 900],
    ]
    stats = pd.DataFrame(rows, columns=cols).assign(universe="usable", period="development")
    claims = o.claims_table(stats, cfg).set_index("claim")
    assert claims.loc["C4", "verdict"] == "lower than claimed"
    assert claims.loc["G2", "verdict"] == "consistent"
