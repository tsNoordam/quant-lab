"""Step 23: every decision uses only bars that closed before the entry bar;
the entry is the open of a later bar (no same-bar decision and fill)."""

import numpy as np
import pytest

from quant_lab.backtest import orb as b

TICK = 0.25
EX = b.Exec(TICK, slippage_ticks=1, trade_through_ticks=1)
KW = {"step": 5, "min_gap_ticks": 1, "q_height": {(w, 0.3): 0.5 for w in (15, 30, 60)}}


def session(seed: int):
    rng = np.random.default_rng(seed)
    c = (2000 + np.cumsum(rng.normal(0, 0.6, 390)) / TICK).round() * TICK
    o = np.r_[c[0] + rng.choice([-2.0, 2.0]), c[:-1]]
    return np.arange(390), o, np.maximum(o, c) + TICK, np.minimum(o, c) - TICK, c


CONFS = [
    {"rule": "R1", "window": 15, "stop": "midpoint", "target": "2R"},
    {"rule": "R1", "window": 30, "stop": "opposite", "target": "ext50"},
    {"rule": "R1c", "window": 60, "stop": "midpoint", "target": "none"},
    {"rule": "R3", "window": 15, "stop": "midpoint", "target": "prev_close"},
    {"rule": "R4", "window": 30, "stop": "opposite", "target": "q0.3"},
    {"rule": "R2", "window": 0, "stop": "1.0gap", "target": "prev_close", "exit": "60"},
]


@pytest.mark.parametrize("seed", range(15))
@pytest.mark.parametrize("conf", CONFS, ids=lambda c: f"{c['rule']}-{c['window']}")
def test_entry_ignores_bars_from_the_entry_bar_on(seed, conf):
    m, o, h, lo, c = session(seed)
    prev_close = float(o[0]) - 2.0 if seed % 2 else float(o[0]) + 2.0
    ranges = {w: b.opening_range(m, h, lo, c, w, 5) for w in (15, 30, 60)}
    base = b.session_trades((m, o, h, lo, c), ranges, prev_close, conf, EX, **KW)
    if not base:
        pytest.skip("no trade on this path")
    first = base[0]
    e = first["entry_minute"]
    # the decision bar closed before the entry bar opened
    assert e >= (conf["window"] or 1)

    shocked = [x.copy() for x in (o, h, lo, c)]
    future = m > e  # every bar after the entry bar
    for x in shocked:
        x[future] = x[future] + 40.0 * -first["direction"]
    so, sh, sl, sc = shocked
    sh[future] = np.maximum(sh[future], np.maximum(so[future], sc[future]))
    sl[future] = np.minimum(sl[future], np.minimum(so[future], sc[future]))
    ranges2 = {w: b.opening_range(m, sh, sl, sc, w, 5) for w in (15, 30, 60)}
    pert = b.session_trades((m, so, sh, sl, sc), ranges2, prev_close, conf, EX, **KW)
    assert pert, "a trade disappeared when only later bars changed"
    assert pert[0]["direction"] == first["direction"]
    assert pert[0]["entry_minute"] == e
    assert pert[0]["risk_pts"] == pytest.approx(first["risk_pts"])


# Audit A8: perturb the entry bar too (all but its open, which is the fill),
# check every trade of a session (the R1c re-entry included), and cover R2/R3
# with sessions that gap.
@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("conf", CONFS, ids=lambda c: f"{c['rule']}-{c['window']}")
def test_every_trade_ignores_the_entry_bar_after_its_open_and_later_bars(seed, conf):
    m, o, h, lo, c = session(seed)
    prev_close = float(o[0]) + (3.0 if seed % 2 else -3.0)
    ranges = {w: b.opening_range(m, h, lo, c, w, 5) for w in (15, 30, 60)}
    base = b.session_trades((m, o, h, lo, c), ranges, prev_close, conf, EX, **KW)
    if not base:
        pytest.skip("no trade on this path")
    for k, trade in enumerate(base):
        e = trade["entry_minute"]
        so, sh, sl, sc = (x.copy() for x in (o, h, lo, c))
        later, at = m > e, m == e
        shift = 40.0 * -trade["direction"]
        so[later] += shift
        sc[later | at] += shift
        sh[later | at] = np.maximum(
            sh[later | at] + shift, np.maximum(so[later | at], sc[later | at])
        )
        sl[later | at] = np.minimum(
            sl[later | at] + shift, np.minimum(so[later | at], sc[later | at])
        )
        r2 = {w: b.opening_range(m, sh, sl, sc, w, 5) for w in (15, 30, 60)}
        pert = b.session_trades((m, so, sh, sl, sc), r2, prev_close, conf, EX, **KW)
        assert len(pert) > k, "a trade disappeared when only its entry bar and later bars changed"
        assert pert[k]["direction"] == trade["direction"]
        assert pert[k]["entry_minute"] == e


def test_r4_quantiles_ignore_validation_and_unusable_sessions():
    import pandas as pd

    from quant_lab.backtest.orb import load_config, train_excursion_quantiles

    root = __import__("pathlib").Path(__file__).resolve().parents[2]
    cfg = load_config(root)
    rng = np.random.default_rng(3)
    days = list(pd.bdate_range("2017-11-01", periods=40)) + list(
        pd.bdate_range("2018-01-02", periods=20)
    )
    rows, sess = [], []
    for i, d in enumerate(days):
        c = (2000 + np.cumsum(rng.normal(0, 0.6, 390)) / TICK).round() * TICK
        o = np.r_[c[0], c[:-1]]
        hi, low = np.maximum(o, c) + TICK, np.minimum(o, c) - TICK
        frame = {"open": o, "high": hi, "low": low, "close": c}
        rows.append(pd.DataFrame({"session": d, "minute": np.arange(390), **frame}))
        sess.append(
            {
                "session": d,
                "usable": i % 7 != 0,
                "bars": 390,
                "close": c[-1],
                "prev_close": c[0] - 1,
                "volume": 1e6,
            }
        )
    bars_ = pd.concat(rows, ignore_index=True)
    s = pd.DataFrame(sess).set_index("session")
    q0 = train_excursion_quantiles(bars_, s, cfg)
    b2 = bars_.copy()
    val = b2["session"] >= pd.Timestamp("2018-01-01")
    for col in ("open", "high", "low", "close"):
        b2.loc[val, col] *= 3
    b2.loc[b2["session"].isin(s.index[~s["usable"]]), "high"] += 500
    assert train_excursion_quantiles(b2, s, cfg) == q0
