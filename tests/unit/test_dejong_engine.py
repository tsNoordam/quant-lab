"""The paper-convention arbitrage engine (de Jong et al. 2009, Tables IV-V)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest.dejong import (
    evidence_label,
    find_positions,
    load_config,
    monthly_return,
    paper_rows,
    run_account,
    summarize,
    variant_config,
)
from quant_lab.data.dlc import DatastreamFormatError, assemble
from quant_lab.data.tbill import load_tbill, rate_on

ROOT = Path(__file__).resolve().parents[2]


def _find(d, **kw):
    args = {
        "buy": 0.10,
        "sell": 0.05,
        "horizon": 260,
        "last_entry": len(d) - 1,
        "close_at_end": False,
    }
    return find_positions(np.asarray(d, dtype=float), **(args | kw))


def test_entry_needs_a_crossing_and_exit_is_the_first_close_at_the_sell_threshold():
    d = [0.12, 0.11, 0.08, 0.11, 0.09, 0.06, 0.04, 0.0]
    (p,) = _find(d)
    # day 0 is already above b: no crossing; the crossing is at day 3
    assert (p.entry, p.exit, p.direction, p.cut) == (3, 6, -1, False)  # d > 0: short A
    (q,) = _find([-x for x in d])
    assert q.direction == 1  # d < 0: A cheap, long A


def test_horizon_cut_off_and_unlimited_horizon():
    d = [0.0, 0.11] + [0.12] * 30 + [0.0]
    (p,) = _find(d, horizon=22)
    assert (p.entry, p.exit, p.cut) == (1, 23, True)
    (q,) = _find(d, horizon=None)
    assert (q.entry, q.exit, q.cut) == (1, 32, False)


def test_no_new_entry_within_a_month_of_the_previous_entry():
    d = np.zeros(60)
    d[[1, 2]] = 0.11  # position 1: entry 1, exit 3
    d[[10, 11]] = 0.11  # crossing at 10: inside the month, ignored
    d[[30, 31]] = 0.11  # crossing at 30: taken
    entries = [p.entry for p in _find(d)]
    assert entries == [1, 30]
    assert [p.entry for p in _find(d, entry_gap=5)] == [1, 10, 30]


def test_open_position_at_the_end_is_discarded_or_closed():
    d = [0.0, 0.11, 0.12, 0.13, 0.12]
    assert _find(d) == []
    (p,) = _find(d, close_at_end=True, last_entry=2)
    assert (p.entry, p.exit, p.forced, p.cut) == (1, 4, True, False)
    assert _find(d, close_at_end=True, last_entry=0) == []  # no entry after the window


def test_delay_shifts_both_trades_by_one_close():
    d = [0.0, 0.11, 0.12, 0.04, 0.0, 0.0]
    (p,) = _find(d)
    (q,) = _find(d, delay=1)
    assert (q.entry, q.exit) == (p.entry + 1, p.exit + 1)


ACCOUNT = OmegaConf.create(
    {
        "initial_margin": 0.5,
        "maintenance_long": 0.25,
        "maintenance_short": 0.30,
        "margin_rule": "per_leg",
        "cash_rate": 0.0,
        "loan_rate": 0.0,
        "rebate_rate": 0.0,
        "short_deposit_earns": False,
        "days_per_year": 260,
    }
)
COSTS = OmegaConf.create({"commission": 0.0025, "half_spread": 0.002, "spread_at_exit": True})


def test_account_costs_and_convergence():
    flat = run_account(np.zeros(5), np.zeros(5), ACCOUNT, COSTS)
    assert flat["total_return"] == pytest.approx(-4 * (0.0025 + 0.002))  # in and out, 2 legs
    no_exit_spread = OmegaConf.merge(COSTS, {"spread_at_exit": False})
    flat2 = run_account(np.zeros(5), np.zeros(5), ACCOUNT, no_exit_spread)
    assert flat2["total_return"] == pytest.approx(-2 * 0.0045 - 2 * 0.0025)
    # the cheap leg gains 5%: the position earns 5% of capital, less costs on 2.05
    won = run_account(np.array([0.05]), np.array([0.0]), ACCOUNT, COSTS)
    assert won["total_return"] == pytest.approx(0.05 - 2 * 0.0045 - 0.0045 * 2.05)


def test_account_interest_on_free_cash_loan_and_rebate():
    rates = OmegaConf.merge(ACCOUNT, {"cash_rate": 0.05, "loan_rate": 0.055, "rebate_rate": 0.03})
    zero = OmegaConf.create({"commission": 0.0, "half_spread": 0.0, "spread_at_exit": False})
    out = run_account(np.zeros(260), np.zeros(260), rates, zero)
    # loan 0.5 at 5.5%, rebate on proceeds 1 at 3%, deposit idle, no free cash
    expected = (1 + 0.03 / 260) ** 260 - 1 - 0.5 * ((1 + 0.055 / 260) ** 260 - 1)
    assert out["total_return"] == pytest.approx(expected)
    earning = OmegaConf.merge(rates, {"short_deposit_earns": True})
    out2 = run_account(np.zeros(260), np.zeros(260), earning, zero)
    assert out2["total_return"] - out["total_return"] == pytest.approx(
        0.5 * ((1 + 0.05 / 260) ** 260 - 1)
    )


def test_margin_calls_per_leg_and_pooled():
    zero = OmegaConf.create({"commission": 0.0, "half_spread": 0.0, "spread_at_exit": False})
    # the shorted twin rises 20% while the long twin rises 15%: a 5% spread loss
    r_long, r_short = np.array([0.15, 0.0]), np.array([0.20, 0.0])
    per_leg = run_account(r_long, r_short, ACCOUNT, zero)
    pooled = run_account(r_long, r_short, OmegaConf.merge(ACCOUNT, {"margin_rule": "pooled"}), zero)
    assert per_leg["margin_calls"] == 1  # short equity 1.5 - 1.2 = 0.3 < 0.30 x 1.2
    assert pooled["margin_calls"] == 0  # account equity 0.95 >> 0.25 x 1.15 + 0.30 x 1.2
    # without costs a liquidation does not change equity
    assert per_leg["total_return"] == pytest.approx(pooled["total_return"]) == pytest.approx(-0.05)


def test_monthly_return_pads_short_positions_with_the_tbill():
    counted, m = monthly_return(0.03, 10, 0.05, 22, 260)
    assert counted == 22 and m == pytest.approx(100 * ((1.03) * (1 + 0.05 * 12 / 260) - 1))
    counted, m = monthly_return(0.10, 44, 0.05, 22, 260)
    assert counted == 44 and m == pytest.approx(5.0)


def test_summary_columns():
    pos = pd.DataFrame(
        {
            "long_a": [True, False, False],
            "days_counted": [22, 44, 66],
            "monthly_return": [1.0, -0.5, 2.0],
            "cut": [False, False, True],
            "margin_calls": [0, 2, 0],
        }
    )
    s = summarize(pos)
    assert (s["positions_long_a"], s["positions_short_a"]) == (1, 2)
    assert s["weighted_mean_return"] == pytest.approx((22 - 22 + 132) / 132)
    assert (s["cut_offs"], s["negative_returns"], s["margin_call_positions"]) == (1, 1, 1)


def test_paper_rows_and_labels():
    t4 = paper_rows(ROOT, "T4")
    assert len(t4) == 13 and t4["Total"]["positions_long_a"] == 58
    assert t4["Fortis"]["max_days"] == 99 and t4["Unilever"]["min_return"] == -1.374
    t5 = paper_rows(ROOT, "T5")
    cfg = load_config(ROOT)
    assert {evidence_label(s) for s in cfg.strategies} == set(t5)
    assert t5[evidence_label("10/5/12m")]["weighted_mean_return"] == 1.180


def test_config_variants_override_only_what_they_name():
    cfg = load_config(ROOT)
    base = variant_config(cfg, None)
    assert "variants" not in base and base.rules.delay == 0
    pooled = variant_config(cfg, "margin_pooled")
    assert pooled.account.margin_rule == "pooled" and pooled.account.loan_rate == 0.055
    assert variant_config(cfg, "dexia_spike_removed").exclude_dates.dexia == ["1997-12-19"]


def test_tbill_loader(tmp_path):
    f = tmp_path / "DTB3.csv"
    f.write_text("observation_date,DTB3\n1990-01-01,.\n1990-01-02,7.89\n1990-01-04,7.80\n")
    rate = load_tbill(f)
    assert list(rate.index.strftime("%Y-%m-%d")) == ["1990-01-02", "1990-01-04"]
    assert rate_on(rate, pd.Timestamp("1990-01-03")) == pytest.approx(0.0789)  # as of, not ahead
    with pytest.raises(ValueError):
        rate_on(rate, pd.Timestamp("1989-12-31"))
    old = tmp_path / "old.csv"
    old.write_text("DATE,DTB3\n1990-01-02,7.89\n")
    assert load_tbill(old).iloc[0] == pytest.approx(0.0789)
    bad = tmp_path / "bad.csv"
    bad.write_text("DATE,OTHER\n1990-01-02,7.89\n")
    with pytest.raises(ValueError, match="not a FRED"):
        load_tbill(bad)


def test_panel_extension_after_the_window():
    idx = pd.bdate_range("1990-01-01", periods=8)
    p = pd.Series(np.linspace(10, 11, 8), idx)
    one = pd.Series(1.0, idx)
    dev = np.log(p / p)
    frame, report = assemble(p, p, one, one, one, dev, fx=None, start="1990-01-01",
                             end="1990-01-05", extend_rows=2)  # fmt: skip
    assert list(frame["in_window"]) == [True] * 5 + [False] * 2
    assert report["rows"] == 5 and report["rows_after_window"] == 2
    with pytest.raises(DatastreamFormatError, match="fewer than 4"):
        assemble(p, p, one, one, one, dev, fx=None, start="1990-01-01", end="1990-01-05",
                 extend_rows=4)  # fmt: skip
