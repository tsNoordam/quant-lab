"""Probabilistic and deflated Sharpe ratios, sub-periods, regimes and concentration."""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest import stats
from quant_lab.backtest.robustness import case_overrides, grid_position
from quant_lab.backtest.run import BacktestGuardError

IDX = pd.bdate_range("1990-01-01", periods=1000)


def test_psr_is_one_half_at_the_benchmark_and_matches_the_normal_formula():
    assert stats.probabilistic_sharpe_ratio(0.1, 0.1, 500) == pytest.approx(0.5)
    sr, n = 0.08, 750
    expected = stats.stats.norm.cdf(sr * np.sqrt(n - 1) / np.sqrt(1 + sr**2 / 2))
    assert stats.probabilistic_sharpe_ratio(sr, 0.0, n) == pytest.approx(expected)
    assert stats.probabilistic_sharpe_ratio(sr, 0.0, 2 * n) > stats.probabilistic_sharpe_ratio(
        sr, 0.0, n
    )


@pytest.mark.parametrize("n_trials", [10, 100, 1000])
def test_expected_max_sharpe_matches_simulation(n_trials):
    """False-strategy theorem: E[max of N null SR estimates] ~ the closed form."""
    rng = np.random.default_rng(7)
    var = 0.04**2
    sims = rng.normal(0.0, np.sqrt(var), size=(4000, n_trials)).max(axis=1).mean()
    assert stats.expected_max_sharpe(n_trials, var) == pytest.approx(sims, rel=0.05)
    assert stats.expected_max_sharpe(1, var) == 0.0


def test_deflated_sharpe_punishes_selection_from_many_trials():
    rng = np.random.default_rng(3)
    skill = pd.Series(rng.normal(0.001, 0.01, 2500))  # per-period SR ~ 0.1
    few = stats.deflated_sharpe_ratio(skill, n_trials=1, var_sr=0.0)
    many = stats.deflated_sharpe_ratio(skill, n_trials=10_000, var_sr=0.05**2)
    assert few["dsr"] > 0.99
    assert many["dsr"] < few["dsr"] and many["sr0_per_period"] > 0
    noise = pd.Series(rng.normal(0.0, 0.01, 2500))
    assert stats.deflated_sharpe_ratio(noise, n_trials=100, var_sr=0.03**2)["dsr"] < 0.5


def test_subperiods_split_at_the_break_dates():
    r = pd.Series(0.001, IDX)
    out = stats.subperiods(r, ["1991-01-01"], 252)
    assert len(out) == 2
    assert out["n_days"].sum() == len(r)
    assert str(out.loc[1, "start"]) == "1991-01-01"


def test_volatility_regime_of_a_day_uses_only_earlier_prices():
    rng = np.random.default_rng(1)
    rel = pd.Series(np.cumsum(rng.normal(0, 0.01, len(IDX))), IDX)
    r = pd.Series(rng.normal(0, 0.01, len(IDX)), IDX)
    base = stats.volatility_regimes(r.iloc[:600], rel.iloc[:600], 60, 252)
    shocked = rel.copy()
    shocked.iloc[600:] += np.cumsum(rng.normal(0, 0.2, len(IDX) - 600))
    pd.testing.assert_frame_equal(base, stats.volatility_regimes(r.iloc[:600], shocked, 60, 252))
    assert base["n_days"].sum() <= 600


def test_trade_concentration_counts_trades_and_shares():
    held = pd.Series([0, 1, 1, 0, -1, -1, -1, 0], index=IDX[:8])
    r = pd.Series([0, 0.01, 0.02, 0, -0.01, 0.0, 0.0, 0], index=IDX[:8])
    out = stats.trade_concentration(r, held)
    assert out["n_trades"] == 2
    assert out["top_trade_share"] == pytest.approx(0.03 / 0.04)
    assert out["positive_trades"] == pytest.approx(0.5)


def test_grid_position_flags_corners():
    folds = pd.DataFrame({"chosen_a": [1, 3, 2], "chosen_b": [5, 5, 5]})
    grid = OmegaConf.create({"a": [1, 2, 3], "b": [4, 5]})
    out = grid_position(folds, grid).set_index("parameter")
    assert out.loc["a", "at_min"] == 1 and out.loc["a", "at_max"] == 1
    assert out.loc["a", "interior"] == 1
    assert out.loc["b", "at_max"] == 3


def test_cases_cannot_touch_the_split_or_the_oos_lock():
    for bad in ("split.train.end=2000-01-01", "+unlock_oos=true", "backtest.period=oos"):
        with pytest.raises(BacktestGuardError):
            case_overrides(OmegaConf.create({"all": [bad]}), "parity_zscore")
    case = OmegaConf.create({"silta_parity": ["strategy.entry_bound=0.03"]})
    assert case_overrides(case, "parity_zscore") is None
    assert case_overrides(case, "silta_parity") == ["strategy.entry_bound=0.03"]
