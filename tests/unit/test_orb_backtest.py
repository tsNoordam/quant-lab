"""Step 23 engine on hand-built bars with known fills."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_lab.backtest import orb as b

ROOT = Path(__file__).resolve().parents[2]
TICK = 0.25
EX = b.Exec(TICK, slippage_ticks=1, trade_through_ticks=1)
EX0 = b.Exec(TICK, slippage_ticks=0, trade_through_ticks=1)


def bars(opens, highs, lows, closes):
    a = [np.asarray(x, dtype=float) for x in (opens, highs, lows, closes)]
    return (np.arange(len(a[0])), *a)


def flat(n, px=100.0):
    return bars([px] * n, [px] * n, [px] * n, [px] * n)


def test_market_entry_and_time_exit_with_slippage():
    m, o, h, lo, c = bars(
        [100, 101, 102, 103], [100, 101, 102, 103], [100, 101, 102, 103], [100, 101, 102, 103]
    )
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=90.0, target=None, exit_minute=None, ex=EX
    )
    assert t["reason"] == "time" and t["entry_minute"] == 1 and t["exit_minute"] == 3
    # entry 101 + 0.25, exit 103 - 0.25
    assert t["fill_pts"] == pytest.approx(103 - 0.25 - 101.25)
    assert t["risk_pts"] == pytest.approx(101.25 - 90.0)


def test_stop_counts_first_when_a_bar_touches_both():
    m, o, h, lo, c = bars([100, 100, 100], [100, 100, 120], [100, 100, 80], [100, 100, 100])
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=95.0, target=105.0, exit_minute=None, ex=EX0
    )
    assert t["reason"] == "stop" and t["fill_pts"] == pytest.approx(-5.0)


def test_target_needs_trade_through_and_fills_at_the_limit():
    m, o, h, lo, c = bars([100] * 4, [100, 100, 105.0, 105.25], [100, 99, 99, 104], [100] * 4)
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=95.0, target=105.0, exit_minute=None, ex=EX0
    )
    # minute 2 only touches 105.0; minute 3 trades through by one tick
    assert t["reason"] == "target" and t["exit_minute"] == 3
    assert t["fill_pts"] == pytest.approx(5.0)


def test_gap_through_the_stop_fills_at_the_open_plus_slippage():
    m, o, h, lo, c = bars([100, 100, 90], [100, 100, 91], [100, 100, 89], [100, 100, 90])
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=95.0, target=None, exit_minute=None, ex=EX
    )
    assert t["reason"] == "stop"
    assert t["fill_pts"] == pytest.approx((90 - 0.25) - (100 + 0.25))


def test_k_r_target_is_set_from_the_entry_fill():
    m, o, h, lo, c = bars([100, 100, 100], [100, 100, 110], [100, 100, 100], [100, 100, 100])
    target = lambda entry, risk: entry + 2 * risk  # noqa: E731
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=1, stop=98.0, target=target, exit_minute=None, ex=EX0
    )
    assert t["reason"] == "target" and t["fill_pts"] == pytest.approx(4.0)


def test_short_side_mirrors():
    m, o, h, lo, c = bars([100, 100, 100], [100, 100, 100], [100, 100, 94], [100, 100, 95])
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=-1, stop=103.0, target=95.0, exit_minute=None, ex=EX0
    )
    assert t["reason"] == "target" and t["fill_pts"] == pytest.approx(5.0)


def test_time_exit_minute_cuts_the_trade():
    m, o, h, lo, c = flat(120)
    t = b.simulate(
        m, o, h, lo, c, entry_minute=1, d=-1, stop=110.0, target=90.0, exit_minute=60, ex=EX0
    )
    assert t["reason"] == "time" and t["exit_minute"] == 59


def range_session(path, window=15):
    """15 minutes inside 100..101, then the given closes (high/low = close +- 0.25)."""
    closes = np.array([100.25, 100.75] * 7 + [100.5] + list(path))
    o = np.r_[closes[0], closes[:-1]]
    return np.arange(len(closes)), o, closes + 0.25, closes - 0.25, closes


def test_first_break_and_re_entry_after_a_stop():
    m, o, h, lo, c = range_session([101.5] * 5 + [100.0] * 5 + [99.0] * 5 + [98.0] * 10)
    rng = b.opening_range(m, h, lo, c, 15, 5)
    assert (rng.high, rng.low) == (101.0, 100.0)
    d, t_min, ref = b.first_break(rng)
    assert (d, t_min, ref) == (1, 20, 101.5)
    conf = {"rule": "R1c", "window": 15, "stop": "midpoint", "target": "none"}
    trades = b.session_trades(
        (m, o, h, lo, c), {15: rng}, np.nan, conf, EX0, step=5, min_gap_ticks=1, q_height=None
    )
    assert [t["direction"] for t in trades] == [1, -1]
    assert trades[0]["reason"] == "stop" and trades[1]["entry_minute"] > trades[0]["exit_minute"]
    r1 = b.session_trades(
        (m, o, h, lo, c),
        {15: rng},
        np.nan,
        {**conf, "rule": "R1"},
        EX0,
        step=5,
        min_gap_ticks=1,
        q_height=None,
    )
    assert len(r1) == 1


def test_extension_targets_and_stops():
    rng = b.Range(101.0, 100.0, np.array([101.5]), np.array([20]))
    assert b.stop_level(rng, 1, "midpoint") == 100.5 and b.stop_level(rng, 1, "opposite") == 100.0
    assert b.stop_level(rng, -1, "opposite") == 101.0
    assert b.target_spec(rng, 1, "ext50", 101.5, None, 15) == 101.5
    assert b.target_spec(rng, -1, "ext100", 99.5, None, 15) == 99.0
    assert b.target_spec(rng, 1, "q0.3", 101.5, {(15, 0.3): 0.5}, 15) == 102.0
    assert b.target_spec(rng, 1, "none", 101.5, None, 15) is None


def test_gap_fade_enters_on_the_second_minute_toward_the_previous_close():
    # previous close 98, RTH opens at 100 (gap up 2), fills at minute 30
    closes = np.full(120, 100.0)
    closes[30:] = 97.5
    m, o, h, lo, c = np.arange(120), np.r_[100.0, closes[:-1]], closes + 0.25, closes - 0.25, closes
    lo[0] = 99.75
    conf = {"rule": "R2", "window": 0, "stop": "1.0gap", "target": "prev_close", "exit": "60"}
    (t,) = b.session_trades(
        (m, o, h, lo, c), {}, 98.0, conf, EX0, step=5, min_gap_ticks=1, q_height=None
    )
    assert t["direction"] == -1 and t["entry_minute"] == 1 and t["reason"] == "target"
    assert t["fill_pts"] == pytest.approx(100.0 - 98.0)
    # filled inside the opening minute: no trade
    lo[0] = 97.0
    assert (
        b.session_trades(
            (m, o, h, lo, c), {}, 98.0, conf, EX0, step=5, min_gap_ticks=1, q_height=None
        )
        == []
    )


def test_r3_needs_a_breakout_toward_an_unfilled_gap():
    m, o, h, lo, c = range_session([99.5] * 5 + [99.0] * 30)  # downside breakout
    rng = b.opening_range(m, h, lo, c, 15, 5)
    conf = {"rule": "R3", "window": 15, "stop": "midpoint", "target": "prev_close"}
    kw = {"step": 5, "min_gap_ticks": 1, "q_height": None}
    o = o.copy()
    o[0] = 100.25
    (t,) = b.session_trades((m, o, h, lo, c), {15: rng}, 98.0, conf, EX0, **kw)  # gap up, unfilled
    assert t["direction"] == -1
    assert (
        b.session_trades((m, o, h, lo, c), {15: rng}, 102.0, conf, EX0, **kw) == []
    )  # gap down: wrong way


def test_impact_uses_lagged_statistics():
    idx = pd.bdate_range("2015-01-05", periods=30)
    s = pd.DataFrame({"close": 2000.0, "prev_close": 2000.0, "volume": 1_000_000.0}, index=idx)
    s.loc[idx[25], "close"] = 2100.0  # a shock on day 25
    cfg = b.load_config(ROOT)
    imp = b.impact_points(s, cfg)
    assert imp.iloc[:20].isna().all()
    assert imp.iloc[25] == imp.iloc[24]  # day 25 does not see its own move
    assert imp.iloc[26] > imp.iloc[25]


def test_cost_scenarios_are_arithmetic_on_fills():
    cfg = b.load_config(ROOT)
    trades = pd.DataFrame({"fill_pts": [2.0], "impact_pts": [0.01]})
    base = b.net_usd(trades, b.scenario_costs(cfg, "base")).iloc[0]
    assert base == pytest.approx(2.0 * 50 - 2 * 2.50 - 2 * 0.01 * 50)
    mes = b.net_usd(trades, b.scenario_costs(cfg, "mes")).iloc[0]
    assert mes == pytest.approx(2.0 * 5 - 2 * 0.62 - 2 * 0.01 * 5)
    gross = b.net_usd(trades, b.scenario_costs(cfg, "gross")).iloc[0]
    assert gross == pytest.approx(100.0)


def test_configuration_count_is_the_trial_count():
    cfg = b.load_config(ROOT)
    confs = b.configs(cfg)
    assert len(confs) == 36 + 12 + 4 + 6 + 12
    assert len({c["id"] for c in confs}) == len(confs)


def test_out_of_sample_sessions_are_refused():
    cfg = b.load_config(ROOT)
    s = pd.DataFrame(
        {"usable": [True], "bars": [390], "prev_close": [1.0]}, index=[pd.Timestamp("2021-01-04")]
    )
    bars_ = pd.DataFrame({"session": [pd.Timestamp("2021-01-04")], "minute": [0]})
    with pytest.raises(ValueError, match="out-of-sample"):
        b.compute(bars_, s, cfg)
