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
    (t,) = b.session_trades(
        (m, o, h, lo, c), {15: rng}, np.nan, conf, ex, step=5, min_gap_ticks=1, q_height=None
    )
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


def bars(opens, highs, lows, closes):
    a = [np.asarray(x, dtype=float) for x in (opens, highs, lows, closes)]
    return (np.arange(len(a[0])), *a)


EX = b.Exec(TICK, slippage_ticks=1, trade_through_ticks=1)


# A1: whether a trade exists must not depend on the entry bar's open (known
# only after the decision); an entry bar opening beyond the stop is a trade
# stopped at that open.
def test_entry_bar_opening_beyond_the_stop_is_a_trade_stopped_at_the_open():
    m, o, h, lo, c = bars(
        [101, 100.0, 99.5], [101, 100.25, 99.75], [101, 99.5, 99.0], [101, 99.75, 99.25]
    )
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=100.5, target=None, exit_minute=None, ex=EX
    )
    assert t is not None and t["reason"] == "stop" and t["exit_minute"] == 1
    assert t["fill_pts"] == pytest.approx((100.0 - 0.25) - (100.0 + 0.25))
    m, o, h, lo, c = bars(
        [101, 100.5, 100], [101, 100.5, 100], [101, 100.0, 100], [101, 100.25, 100]
    )
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=100.75, target=None, exit_minute=None, ex=EX
    )
    assert t["fill_pts"] == pytest.approx((100.5 - 0.25) - (100.5 + 0.25))


# A3: stops and targets lie on the tick grid (rounded away from the entry).
def test_stop_fills_lie_on_the_tick_grid():
    rng = b.Range(101.25, 100.0, np.array([101.5]), np.array([20]))
    stop = b.stop_level(rng, 1, "midpoint")  # 100.625 before rounding
    m, o, h, lo, c = bars(
        [101.5, 101.5, 101.0],
        [101.5, 101.75, 101.0],
        [101.5, 101.25, 100.25],
        [101.5, 101.5, 100.5],
    )
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=stop, target=None, exit_minute=None, ex=EX
    )
    exit_px = (101.5 + 0.25) + t["fill_pts"]
    assert (exit_px / TICK) % 1 == pytest.approx(0)
    assert exit_px == pytest.approx(100.5 - 0.25)  # stop rounded down to 100.5, then slippage


def test_off_grid_target_rounds_away_from_the_entry():
    m, o, h, lo, c = bars([100, 100, 100], [100, 100, 102.0], [100, 99.5, 99.5], [100, 100, 101])
    t = b.simulate(
        m,
        o,
        h,
        lo,
        c,
        entry_minute=1,
        d=1,
        stop=99.0,
        target=101.625,
        exit_minute=None,
        ex=b.Exec(TICK, 0, 0),
    )
    assert t["reason"] == "target" and t["fill_pts"] == pytest.approx(101.75 - 100.0)


def driftless_sessions(n=400, seed=11):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2012-01-02", periods=n)
    rows, sess, prev = [], [], 1500.0
    for d in days:
        start = prev + round(rng.normal(0, 2) / TICK) * TICK
        c = start + np.round(np.cumsum(rng.normal(0, 0.5, 390)) / TICK) * TICK
        o = np.r_[start, c[:-1]]
        hi, low = np.maximum(o, c) + TICK, np.minimum(o, c) - TICK
        frame = {"open": o, "high": hi, "low": low, "close": c}
        rows.append(pd.DataFrame({"session": d, "minute": np.arange(390), **frame}))
        sess.append(
            {
                "session": d,
                "usable": True,
                "bars": 390,
                "close": c[-1],
                "prev_close": prev,
                "volume": 1.5e6,
            }
        )
        prev = float(c[-1])
    return pd.concat(rows, ignore_index=True), pd.DataFrame(sess).set_index("session")


@pytest.fixture(scope="module")
def walk():
    cfg = b.load_config(ROOT)
    bars_, sessions = driftless_sessions()
    return cfg, bars_, sessions, b.train_excursion_quantiles(bars_, sessions, cfg)


# A6 / RT-2: the engine's fill conventions on driftless walks, before costs.
# One path is noisy (all configurations share its sessions; sd about 7.5 USD
# per trade across seeds), so the test pairs both conventions on the same
# paths and averages over seeds.
def test_fill_conventions_on_driftless_walks():
    cfg = b.load_config(ROOT)
    base, opt = [], []
    for seed in range(8):
        bars_, sessions = driftless_sessions(n=300, seed=100 + seed)
        q = b.train_excursion_quantiles(bars_, sessions, cfg)
        base.append(
            b.run_trades(bars_, sessions, cfg, b.Exec(TICK, 0, 1), q)["fill_pts"].mean() * 50
        )
        opt.append(
            b.run_trades(bars_, sessions, cfg, b.Exec(TICK, 0, 0, 0, True), q)["fill_pts"].mean()
            * 50
        )
    diff = np.array(opt) - np.array(base)
    # the base conventions (trade-through, stop first) cost a few USD per trade
    assert (diff > 1).all() and 2 < diff.mean() < 7, diff
    # the optimistic conventions are neutral within the seed noise (8 seeds: se ~2.7)
    assert abs(np.mean(opt)) < 6, opt


# A7: the share of trades whose exit bar touched stop and target is reported.
def test_results_report_the_same_bar_share(walk):
    cfg, bars_, sessions, q = walk
    keys = {b.exec_key(cfg, b.scenario_costs(cfg, s)) for s in cfg.costs.scenarios}
    trades = {k: b.run_trades(bars_, sessions, cfg, b.make_exec(cfg, k), q) for k in keys}
    res = b.evaluate(trades, sessions, cfg)
    assert "share_both_touch" in res and res["share_both_touch"].notna().any()
    assert {"ci_lo_usd", "ci_hi_usd", "sd_usd"} <= set(res.columns)


# A4: no configuration or family turns positive when the unusable sessions
# are included (real data only).
@pytest.mark.skipif(
    not (ROOT / "data/processed/es/sessions.parquet").exists(),
    reason="ES data not present (dvc pull)",
)
def test_unusable_sessions_do_not_change_any_verdict():
    cfg = b.load_config(ROOT)
    bars_, sessions = b.load_inputs(ROOT, cfg)
    r = b.compute(bars_, sessions, cfg)["results"].query(
        "scenario == 'base' and period == 'development'"
    )
    piv = r.pivot_table(index="id", columns="universe", values="mean_usd", aggfunc="first")
    assert piv[(piv["usable"] <= 0) & (piv["with_bars"] > 0)].empty
    wb = r[r["universe"] == "with_bars"]
    assert not wb.groupby("family")["mean_usd"].apply(lambda s: bool((s > 0).all())).any()
