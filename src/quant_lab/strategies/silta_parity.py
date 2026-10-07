"""The SILTA arbitrageur: trade a twin pair's deviation from theoretical parity.

Spec and rule classification: research/specs/extensions/silta_parity.md.

Maymin's arbitrageurs hold the discrepancy D = ln(P1/P2) - ln(parity), short the
expensive class and long the cheap one, when D exceeds round-turn transaction
costs, and are paid when the discrepancy disappears. This module decides that
position at each close from that close only (D_t uses no history at all).

Spread position: +1 = long leg A / short leg B, -1 = short A / long B, 0 = flat.
"""

import numpy as np
import pandas as pd
from omegaconf import DictConfig

from quant_lab.strategies.parity_zscore import relative_price, spread_positions


def parity_deviation(panel: pd.DataFrame, parity_ratio: float) -> pd.Series:
    """D_t = ln(P_a/P_b) - ln(parity): > 0 when leg A is expensive relative to parity."""
    if not parity_ratio > 0:
        raise ValueError(f"parity_ratio must be positive, got {parity_ratio}")
    return (relative_price(panel) - np.log(parity_ratio)).rename("parity_deviation")


def target_positions(
    panel: pd.DataFrame, *, parity_ratio: float, entry_bound: float, exit_bound: float
) -> tuple[pd.Series, pd.Series]:
    """Short the expensive leg once |D| > entry_bound; close once D is back within exit_bound
    of parity (exit_bound = 0: when D reaches or crosses parity); flip on the other side."""
    d = parity_deviation(panel, parity_ratio)
    return spread_positions(d, entry_z=entry_bound, exit_z=exit_bound), d


def decide(panel: pd.DataFrame, s: DictConfig, data: DictConfig):
    return target_positions(
        panel,
        parity_ratio=float(data.parity_ratio),
        entry_bound=s.entry_bound,
        exit_bound=s.exit_bound,
    )
