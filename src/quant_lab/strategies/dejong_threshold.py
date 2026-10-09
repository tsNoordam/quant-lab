"""de Jong, Rosenthal & van Dijk (2009): the threshold arbitrage rule, as a lab strategy.

Spec and rule classification: research/specs/replication/dejong_threshold.md.

The paper's rule (Tables IV-V) on the lab's parity deviation D_t = ln(P_A/P_B) -
ln(parity): open when |D| crosses the buy threshold (short the expensive leg,
long the cheap one), close when |D| is back within the sell threshold or the
position reaches the maximum horizon. The lab's engine fills one close later and
applies its own costs and P&L (quant_lab.backtest.run); this module only decides
the position at each close from data up to that close.

Spread position: +1 = long leg A / short leg B, -1 = short A / long B, 0 = flat.
"""

import numpy as np
import pandas as pd
from omegaconf import DictConfig

from quant_lab.strategies.silta_parity import parity_deviation


def threshold_positions(
    d: pd.Series, *, buy: float, sell: float, horizon: int | None, entry_gap: int
) -> pd.Series:
    """Positions decided on each close. An entry needs |D_t| >= buy and
    |D_{t-1}| < buy (a crossing) and at least ``entry_gap`` closes since the
    previous entry; the exit comes at the first close with |D| <= sell or after
    ``horizon`` closes. A missing D means no signal: flat."""
    if not 0 <= sell < buy:
        raise ValueError("need 0 <= sell < buy")
    a = d.abs().to_numpy()
    sign = np.sign(d.to_numpy())
    out = np.zeros(len(a), dtype=np.int8)
    pos, held, since_entry = 0, 0, None
    for t in range(len(a)):
        if np.isnan(a[t]):
            pos, held = 0, 0
        elif pos != 0:
            held += 1
            if a[t] <= sell or (horizon is not None and held >= horizon):
                pos, held = 0, 0
        elif (
            t > 0
            and a[t] >= buy
            and not np.isnan(a[t - 1])
            and a[t - 1] < buy
            and (since_entry is None or t - since_entry >= entry_gap)
        ):
            pos, held, since_entry = int(-sign[t]), 0, t
        out[t] = pos
    return pd.Series(out, index=d.index, name="spread_position")


def decide(panel: pd.DataFrame, s: DictConfig, data: DictConfig):
    d = parity_deviation(panel, float(data.parity_ratio))
    positions = threshold_positions(
        d, buy=s.buy, sell=s.sell, horizon=s.horizon, entry_gap=s.entry_gap
    )
    return positions, d
