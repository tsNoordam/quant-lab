"""SILTA arbitrageur: deviation from parity, entry beyond the cost bound, exit at parity."""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.strategies import STRATEGIES, decide
from quant_lab.strategies.silta_parity import parity_deviation, target_positions

PARITY = 1.5


def _panel(deviations) -> pd.DataFrame:
    """Leg B fixed at 10; leg A priced at parity * exp(D)."""
    d = np.asarray(deviations, dtype=float)
    idx = pd.bdate_range("1990-01-01", periods=len(d))
    return pd.DataFrame({"close_a": 10 * PARITY * np.exp(d), "close_b": 10.0}, idx)


def test_deviation_is_log_price_ratio_minus_log_parity():
    d = parity_deviation(_panel([0.0, 0.05, -0.02]), PARITY)
    np.testing.assert_allclose(d, [0.0, 0.05, -0.02], atol=1e-12)


def test_parity_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        parity_deviation(_panel([0.0]), 0.0)


def test_short_the_expensive_leg_beyond_the_bound_and_exit_at_parity():
    d = [0.01, 0.02, 0.015, 0.004, -0.001, -0.01, -0.03, -0.01, 0.001]
    pos, _ = target_positions(_panel(d), parity_ratio=PARITY, entry_bound=0.018, exit_bound=0.0)
    # 0.02 > bound: A expensive -> short A (-1); held until D < 0; long A once D < -0.018,
    # held until D > 0.
    assert pos.tolist() == [0, -1, -1, -1, 0, 0, 1, 1, 0]


def test_exit_bound_closes_before_parity():
    d = [0.03, 0.01, 0.008]
    pos, _ = target_positions(_panel(d), parity_ratio=PARITY, entry_bound=0.018, exit_bound=0.009)
    assert pos.tolist() == [-1, -1, 0]


def test_direct_flip_when_the_other_bound_is_crossed():
    pos, _ = target_positions(
        _panel([0.03, -0.03]), parity_ratio=PARITY, entry_bound=0.018, exit_bound=0.0
    )
    assert pos.tolist() == [-1, 1]


def test_registry_dispatches_on_strategy_name():
    cfg = OmegaConf.create(
        {
            "strategy": {"name": "silta_parity", "entry_bound": 0.018, "exit_bound": 0.0},
            "data": {"parity_ratio": PARITY},
        }
    )
    pos, signal = decide(_panel([0.0, 0.03]), cfg)
    assert pos.tolist() == [0, -1] and signal.name == "parity_deviation"
    assert set(STRATEGIES) >= {"parity_zscore", "silta_parity"}
    cfg.strategy.name = "nope"
    with pytest.raises(ValueError, match="unknown strategy"):
        decide(_panel([0.0]), cfg)
