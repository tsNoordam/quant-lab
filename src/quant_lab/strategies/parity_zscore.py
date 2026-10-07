"""Baseline convergence trade on a twin pair's relative price.

Spec and rule classification: research/specs/baseline/parity_zscore.md.

This module only decides the desired spread position at each close, using data
up to and including that close. Execution timing (next open) is applied in one
place, quant_lab.backtest.run, never here.

Spread position: +1 = long leg A / short leg B, -1 = short A / long B, 0 = flat.
"""

import numpy as np
import pandas as pd

from quant_lab.features.rolling import calculate_rolling_zscore


def relative_price(panel: pd.DataFrame) -> pd.Series:
    """ln(P_a / P_b) on closing prices (Maymin's definition of relative price)."""
    return np.log(panel["close_a"] / panel["close_b"]).rename("relative_price")


def spread_positions(z: pd.Series, *, entry_z: float, exit_z: float) -> pd.Series:
    """Hysteresis rule: open beyond +/-entry_z, close inside +/-exit_z, flip on the other side.

    A missing z (warm-up, zero variance) means no signal: flat.
    """
    if not 0 <= exit_z < entry_z:
        raise ValueError("need 0 <= exit_z < entry_z")
    out = np.zeros(len(z), dtype=np.int8)
    pos = 0
    for i, value in enumerate(z.to_numpy()):
        if np.isnan(value):
            pos = 0
        elif value > entry_z:
            pos = -1  # A rich relative to B: short A, long B
        elif value < -entry_z:
            pos = 1
        elif (pos == -1 and value < exit_z) or (pos == 1 and value > -exit_z):
            pos = 0
        out[i] = pos
    return pd.Series(out, index=z.index, name="spread_position")


def target_positions(panel: pd.DataFrame, *, window: int, entry_z: float, exit_z: float):
    """Desired spread position decided on each close, plus the signal behind it."""
    rel = relative_price(panel)
    z = calculate_rolling_zscore(rel, window=window).rename("zscore")
    return spread_positions(z, entry_z=entry_z, exit_z=exit_z), z
