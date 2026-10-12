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
