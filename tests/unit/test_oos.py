"""Pre-registered OOS evaluation: decision rules, Holm correction, guards."""

from pathlib import Path

import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest import oos
from quant_lab.backtest.run import BacktestGuardError

RULES = OmegaConf.create(
    {
        "dsr_threshold": 0.95,
        "min_entries_evidence": 10,
        "max_top_trade_share": 0.5,
        "holm_alpha": 0.05,
        "min_entries_evaluable": 5,
    }
)
GOOD = {"n_entries": 20, "dsr": 0.99, "top_trade_share": 0.2}


def test_holm_step_down():
    p = {"a": 0.001, "b": 0.02, "c": 0.04}
    # a: 0.001 <= 0.05/3; b: 0.02 <= 0.05/2; c: 0.04 <= 0.05/1
    assert oos.holm(p, 0.05) == {"a": True, "b": True, "c": True}
    p = {"a": 0.001, "b": 0.03, "c": 0.04}  # b fails 0.025, so b and c are not rejected
    assert oos.holm(p, 0.05) == {"a": True, "b": False, "c": False}


def test_verdict_needs_every_condition():
    assert oos.classify(GOOD, RULES, True, None) == "evidence of edge"
    assert oos.classify(GOOD, RULES, False, None) == "no evidence of edge"
    assert oos.classify({**GOOD, "dsr": 0.9}, RULES, True, None) == "no evidence of edge"
    assert oos.classify({**GOOD, "top_trade_share": 0.6}, RULES, True, None) == (
        "no evidence of edge"
    )
    assert oos.classify({**GOOD, "n_entries": 7}, RULES, True, None) == "no evidence of edge"
    assert oos.classify({**GOOD, "n_entries": 3}, RULES, True, None).startswith("not evaluable")
    assert oos.classify(GOOD, RULES, True, "one trade").startswith("not evaluable (pre-declared")


def test_ex_date_entry_share():
    idx = pd.bdate_range("2000-01-03", periods=12)
    # leg a pays a 2% dividend on day 3 (close drops, total-return close continuous)
    close = pd.Series(100.0, idx)
    close.iloc[3:] = 98.0
    panel = pd.DataFrame(
        {"close_a": close, "adj_close_a": 100.0, "close_b": 100.0, "adj_close_b": 100.0}, idx
    )
    held = pd.Series([0, 0, 0, 0, 1, 1, 0, 0, 0, 0, -1, -1], idx)
    share = oos.ex_date_entry_share(held, panel, 0.005, 5)
    assert share == pytest.approx(0.5)  # entry on day 4 follows the ex-date; day 10 does not


def test_refuses_without_unlock_or_deflation_inputs(tmp_path: Path):
    cfg = OmegaConf.create(
        {"oos": {"deflation": {"n_trials": 10, "var_sr_per_period": {"x": 1e-4}}}}
    )
    with pytest.raises(BacktestGuardError, match="unlock_oos"):
        oos.check_ready(cfg, tmp_path, require_freeze=False)
    cfg.unlock_oos = True
    cfg.oos.deflation.n_trials = None
    with pytest.raises(BacktestGuardError, match="not filled"):
        oos.check_ready(cfg, tmp_path, require_freeze=False)


def test_refuses_outside_a_frozen_clean_checkout(tmp_path: Path):
    cfg = OmegaConf.create(
        {"unlock_oos": True, "oos": {"deflation": {"n_trials": 10, "var_sr_per_period": {"x": 1}}}}
    )
    with pytest.raises(BacktestGuardError, match="clean tree|freeze"):
        oos.check_ready(cfg, tmp_path, require_freeze=True)  # not a git checkout
