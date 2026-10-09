"""Strategy registry: ``strategy.name`` in conf/strategy/ selects the decision function.

Every strategy decides the desired spread position at each close from data up to
and including that close (+1 = long A / short B, -1 = short A / long B, 0 = flat)
and returns the signal behind it. Execution timing, sizing and costs are applied
in quant_lab.backtest.run, never in a strategy.
"""

from collections.abc import Callable

import pandas as pd
from omegaconf import DictConfig

from quant_lab.strategies import dejong_threshold, parity_zscore, silta_parity

Decide = Callable[[pd.DataFrame, DictConfig, DictConfig], tuple[pd.Series, pd.Series]]

STRATEGIES: dict[str, Decide] = {
    "parity_zscore": parity_zscore.decide,
    "silta_parity": silta_parity.decide,
    "dejong_threshold": dejong_threshold.decide,
}


def decide(panel: pd.DataFrame, cfg: DictConfig) -> tuple[pd.Series, pd.Series]:
    """(spread positions, signal) for the configured strategy."""
    name = cfg.strategy.name
    if name not in STRATEGIES:
        raise ValueError(f"unknown strategy {name!r}; known: {sorted(STRATEGIES)}")
    return STRATEGIES[name](panel, cfg.strategy, cfg.data)
