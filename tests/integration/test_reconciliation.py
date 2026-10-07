"""VectorBT must reconcile with the independent reference bookkeeping (CLAUDE.md)."""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest import reference
from quant_lab.backtest import run as bt
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw
from quant_lab.strategies.parity_zscore import target_positions

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab")
    shutil.copytree(ROOT / "conf", root / "conf")
    cfg = load_dataset_config("synthetic_twin", root)
    write_raw(cfg, root)
    preprocess(cfg, root)
    return root


def simulate(root: Path, *overrides: str):
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        cfg = compose("config", overrides=list(overrides))
    period = bt.select_period(cfg)
    panel = pd.read_parquet(root / cfg.data.processed_dir / "panel.parquet").loc[: period.end]
    s = cfg.strategy
    decisions, _ = target_positions(panel, window=s.window, entry_z=s.entry_z, exit_z=s.exit_z)
    return cfg, panel, bt.backtest_pair(panel, decisions, period, cfg)


@pytest.mark.parametrize("execution", ["next_open", "next_close"])
def test_fills_fees_and_equity_reconcile(project, execution):
    cfg, panel, sim = simulate(project, f"backtest.execution={execution}")
    rec = sim.pf.orders.records_readable
    assert len(rec) > 20

    raw = bt.fill_prices(panel, sim.orders.index, cfg)
    rows, cols = raw.index.get_indexer(rec["Timestamp"]), raw.columns.get_indexer(rec["Column"])
    side = np.where(rec["Side"] == "Buy", 1.0, -1.0)
    cost = sim.order_cost.to_numpy()[rows, cols]
    expected = raw.to_numpy()[rows, cols] * (1 + side * cost)
    np.testing.assert_allclose(rec["Price"], expected, rtol=1e-12)

    commission = cfg.costs.commission_bps / 1e4
    np.testing.assert_allclose(rec["Fees"], rec["Size"] * rec["Price"] * commission, rtol=1e-12)

    ledger = pd.DataFrame(
        {
            "date": rec["Timestamp"],
            "leg": rec["Column"],
            "size": side * rec["Size"],
            "price": rec["Price"],
            "fees": rec["Fees"],
        }
    )
    close = pd.DataFrame({leg: panel.loc[sim.orders.index, f"close_{leg}"] for leg in "ab"})
    replayed = reference.replay_equity(ledger, close, cfg.backtest.init_cash, sim.borrow)
    np.testing.assert_allclose(replayed, sim.equity, rtol=1e-10)


def test_participation_limit_binds_for_large_capital(project):
    small = simulate(project, "backtest.init_cash=1000000")[2]
    cfg, panel, big = simulate(project, "backtest.init_cash=100000000000")
    assert small.cost_metrics["entries_capped"] == 0
    assert big.cost_metrics["entries_capped"] > 0
    # No entry may trade more than max_participation x decision-day ADV in either leg.
    rec = big.pf.orders.records_readable
    adv = panel[["volume_a", "volume_b"]].rolling(cfg.costs.impact.adv_lookback_days).mean()
    adv = adv.shift(1).reindex(big.orders.index).set_axis(["a", "b"], axis=1)
    held = big.held
    entries = held.index[held.ne(0) & held.ne(held.shift(fill_value=0))]
    entry_orders = rec[rec["Timestamp"].isin(entries)]
    limit = (
        cfg.costs.limits.max_participation
        * adv.to_numpy()[
            adv.index.get_indexer(entry_orders["Timestamp"]),
            adv.columns.get_indexer(entry_orders["Column"]),
        ]
    )
    # Equity drifts from init_cash between entries, so allow a small tolerance.
    assert (entry_orders["Size"].to_numpy() <= limit * 1.05).all()


def test_costs_rise_with_capital_and_hurt_returns(project):
    small = simulate(project, "backtest.init_cash=1000000")[2]
    big = simulate(project, "backtest.init_cash=1000000000")[2]
    assert big.cost_metrics["median_order_cost_bps"] > small.cost_metrics["median_order_cost_bps"]
    flat_free = simulate(project, "costs=flat_bps", "costs.fee_bps=0", "costs.slippage_bps=0")[2]
    assert small.equity.iloc[-1] < flat_free.equity.iloc[-1]
