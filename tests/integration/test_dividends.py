"""P&L must be dividend-consistent (audit 2026-10-07, finding A1).

A short position held across an ex-dividend date pays the (manufactured)
dividend; it must not book the ex-date price drop as a gain. With close falling
by the dividend and adj_close continuous, a zero-cost short-A / long-B position
in otherwise flat prices earns nothing economically.
"""

from pathlib import Path

import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest.run import Period, backtest_pair

ROOT = Path(__file__).resolve().parents[2]
DIVIDEND = 0.03
EX_DATE = 50


def zero_cost_config():
    with initialize_config_dir(config_dir=str(ROOT / "conf"), version_base="1.3"):
        return compose(
            "config",
            overrides=[
                "costs=flat_bps",
                "costs.fee_bps=0",
                "costs.slippage_bps=0",
                "backtest.execution=next_close",
            ],
        )


def flat_pair_with_ex_dividend(n: int = 100) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=n)
    panel = pd.DataFrame(
        {
            "close_a": 100.0,
            "adj_close_a": 100.0,
            "volume_a": 1e6,
            "close_b": 100.0,
            "adj_close_b": 100.0,
            "volume_b": 1e6,
        },
        index=idx,
    )
    panel.iloc[EX_DATE:, panel.columns.get_loc("close_a")] *= 1 - DIVIDEND
    # total-return series is continuous across the ex-date: rebase history instead
    panel.iloc[:EX_DATE, panel.columns.get_loc("adj_close_a")] *= 1 - DIVIDEND
    return panel


@pytest.mark.xfail(
    strict=True,
    reason="audit 2026-10-07 A1 CONFIRMED: P&L uses unadjusted closes, dividends not booked",
)
def test_short_leg_pays_the_ex_dividend():
    cfg = zero_cost_config()
    panel = flat_pair_with_ex_dividend()
    decisions = pd.Series(0, index=panel.index)
    decisions.iloc[10:80] = -1  # short A / long B across A's ex-date
    period = Period("p", panel.index[0], panel.index[-1])
    sim = backtest_pair(panel, decisions, period, cfg)
    pnl = sim.equity.iloc[-1] / cfg.backtest.init_cash - 1
    assert abs(pnl) < 1e-3  # today: about +leg_weight * DIVIDEND = +1.5%
