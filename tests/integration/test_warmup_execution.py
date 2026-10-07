"""Freeze audit (step 10), red-team findings on the liquidity model's warm-up.

Before the ADV and volatility statistics exist, an entry could be "taken" with
size 0 and then held at size 0 for as long as the signal persisted, and an order
filled without sigma paid commission only. Both happen only at the very start of
a dataset, where a period starts on the first panel row (train for rd_shell and
reed_elsevier, OOS for rio_tinto).
"""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from quant_lab.backtest import run as bt
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("warmup")
    shutil.copytree(ROOT / "conf", root / "conf")
    data_cfg = load_dataset_config("synthetic_twin", root)
    write_raw(data_cfg, root)
    preprocess(data_cfg, root)
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        cfg = compose("config")
    period = bt.select_period(cfg)
    panel = pd.read_parquet(root / cfg.data.processed_dir / "panel.parquet").loc[: period.end]
    assert period.start == panel.index[0]  # the period starts on the first data row
    # A signal that is live from the first close and held for 200 bars, then flat.
    decisions = pd.Series(0, index=panel.index, dtype=int)
    decisions.iloc[:200] = -1
    return cfg, panel, period, bt.backtest_pair(panel, decisions, period, cfg)


def test_no_zero_size_position_is_held(setup):
    _, _, _, sim = setup
    weights = sim.orders.ffill().fillna(0.0)
    phantom = sim.held.ne(0) & weights["a"].eq(0)
    assert not phantom.any(), f"{int(phantom.sum())} bars held a position of size 0"


def test_every_order_pays_spread_and_impact(setup):
    _, _, _, sim = setup
    traded = sim.orders.notna() & sim.orders.ne(sim.orders.ffill().shift())
    rec = sim.pf.orders.records_readable
    assert len(rec) > 0
    costs = sim.order_cost.to_numpy()[sim.order_cost.notna().to_numpy()]
    assert np.isfinite(costs).all()
    # every executed order has a cost entry (no NaN cost filled with 0 by the engine)
    rows = sim.order_cost.index.get_indexer(rec["Timestamp"])
    cols = sim.order_cost.columns.get_indexer(rec["Column"])
    paid = sim.order_cost.to_numpy()[rows, cols]
    assert np.isfinite(paid).all() and (paid > 0).all(), "an order was filled without costs"
    assert traded.to_numpy().sum() >= 2


def test_position_opens_once_liquidity_statistics_exist(setup):
    cfg, panel, _, sim = setup
    held = sim.held
    first = held.ne(0).idxmax()
    # sigma needs vol_lookback_days + 1 closes; the fill is one bar after the decision
    assert panel.index.get_loc(first) >= cfg.costs.impact.vol_lookback_days + 1


def test_alternating_signal_from_the_first_row_has_no_free_orders_or_ghosts(ohlcv):
    """The auditor's in-memory reproduction (freeze audit A2)."""
    dates = pd.bdate_range("2020-01-01", periods=150)
    cfg = OmegaConf.create(
        {
            "strategy": {"name": "silta_parity", "leg_weight": 0.5},
            "data": {
                "name": "t",
                "dividends": {"min_yield": 0.005, "withholding": {"a": 0, "b": 0}},
            },
            "backtest": {"init_cash": 1e6, "execution": "next_close", "annualization": 252},
            "costs": {
                "model": "liquidity",
                "commission_bps": 5.0,
                "fx_conversion_bps": 0.0,
                "borrow_bps_annual": 50.0,
                "buy_tax_bps": 0.0,
                "spread": {
                    "lookback_days": 20,
                    "min_quote_days": 10,
                    "fallback_half_spread_bps": 10,
                },
                "impact": {"coefficient": 1.0, "vol_lookback_days": 60, "adv_lookback_days": 20},
                "limits": {"max_participation": 0.15},
            },
        }
    )
    panel = ohlcv(dates, seed=1).add_suffix("_a").join(ohlcv(dates, seed=2).add_suffix("_b"))
    dec = pd.Series(np.where((np.arange(len(dates)) // 15) % 2 == 0, 1, -1), index=dates)
    sim = bt.backtest_pair(panel, dec, bt.Period("oos", dates[0], dates[-1]), cfg)
    w = sim.orders.ffill().fillna(0.0)
    traded = (w - w.shift(fill_value=0.0)).where(sim.orders.notna()).abs() > 0
    assert traded.to_numpy().sum() > 0
    assert sim.order_cost[traded].notna().sum().sum() == traded.sum().sum()
    assert not ((sim.held != 0) & (w["a"] == 0)).any()
