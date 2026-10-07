"""Hydra config -> VectorBT -> MLflow, on a self-contained synthetic project."""

import shutil
import subprocess
import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest import run as bt
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import simulate_truth, write_raw
from quant_lab.strategies.parity_zscore import spread_positions

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab")
    shutil.copytree(ROOT / "conf", root / "conf")
    cfg = load_dataset_config("synthetic_twin", root)
    write_raw(cfg, root)
    preprocess(cfg, root)
    return root


def config(root: Path, *overrides: str):
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        return compose(
            "config",
            overrides=[f"mlflow.tracking_uri=sqlite:///{root}/mlflow.db", *overrides],
        )


def test_run_logs_metrics_tags_and_artifacts(project):
    result = bt.run_backtest(config(project), project)

    run = mlflow.get_run(result["run_id"])
    assert {"sharpe", "max_drawdown", "total_return", "n_entries"} <= set(run.data.metrics)
    assert run.data.tags["period"] == "train"
    assert run.data.tags["cost_model"] == "liquidity"
    assert {"cost_spread_impact_tax", "cost_commission", "cost_borrow"} <= set(run.data.metrics)
    assert run.data.tags["unlock_oos"] == "false"
    assert len(run.data.tags["data_md5"]) == 32
    assert run.data.params["strategy.window"] == "60"
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(result["run_id"])}
    assert {"equity_curve.png", "config.yaml", "daily.csv", "orders.csv"} <= artifacts


def test_oos_is_locked_by_default(project):
    with pytest.raises(bt.BacktestGuardError, match="locked"):
        bt.run_backtest(config(project, "backtest.period=oos"), project)


def test_oos_unlock_is_recorded(project):
    result = bt.run_backtest(config(project, "backtest.period=oos", "+unlock_oos=true"), project)
    assert result["unlock_oos"] == "true" and result["period"] == "oos"


def test_split_overrides_are_refused():
    with pytest.raises(bt.BacktestGuardError, match="locked"):
        bt.check_overrides(["split.train.end=2009-01-01"])
    bt.check_overrides(["split=synthetic_twin", "strategy.window=40"])  # allowed


def test_liquidity_costs_refuse_datasets_with_unreliable_volume(project):
    with pytest.raises(bt.BacktestGuardError, match="volume_reliable"):
        bt.run_backtest(config(project, "+data.volume_reliable=false"), project)
    flat = bt.run_backtest(
        config(project, "+data.volume_reliable=false", "costs=flat_bps"), project
    )
    assert flat["cost_model"] == "flat_bps"


def test_clean_tree_requirement_is_enforced(project):
    # tmp project is not a git repo, so its state is unknown and must not pass.
    with pytest.raises(bt.BacktestGuardError, match="dirty"):
        bt.run_backtest(config(project, "mlflow.require_clean_tree=true"), project)


def test_data_after_the_period_cannot_affect_the_run(project, tmp_path):
    cfg = config(project)
    period = bt.select_period(cfg)
    panel = pd.read_parquet(project / cfg.data.processed_dir / "panel.parquet")
    shocked = panel.copy()
    later = shocked.index > period.end
    shocked.loc[later, ["open_a", "close_a", "high_a", "low_a", "adj_close_a"]] *= 2.0

    shocked.loc[later, ["volume_a"]] *= 10  # liquidity after the period must not matter either

    def equity(p):
        p = p.loc[: period.end]
        s = cfg.strategy
        decisions, _ = bt.target_positions(p, window=s.window, entry_z=s.entry_z, exit_z=s.exit_z)
        return bt.backtest_pair(p, decisions, period, cfg).equity

    pd.testing.assert_series_equal(equity(panel), equity(shocked))


def _oracle_sharpe(root: Path, sign: int) -> float:
    cfg = config(root, "costs=flat_bps", "costs.fee_bps=0", "costs.slippage_bps=0")
    period = bt.select_period(cfg)
    panel = pd.read_parquet(root / cfg.data.processed_dir / "panel.parquet").loc[: period.end]
    truth = simulate_truth(cfg.data)["mispricing"].reindex(panel.index)
    oracle = sign * spread_positions(truth / truth.std(), entry_z=1.0, exit_z=0.0)
    held, orders = bt.execution_targets(oracle, period, 0.5)
    pf = bt.simulate(panel, orders, cfg)
    return bt.compute_metrics(pf.value(), held, pf, 252)["sharpe"]


def test_known_signal_is_profitable_through_the_engine(project):
    """Trading the true (hidden) mispricing must make money at next-open fills.

    Fails if leg signs, the execution lag or the synthetic opens are wrong.
    """
    assert _oracle_sharpe(project, +1) > 0.5
    assert _oracle_sharpe(project, -1) < -0.5


def test_close_only_data_requires_next_close_execution(project):
    cfg = config(project, "costs=flat_bps")
    period = bt.select_period(cfg)
    panel = pd.read_parquet(project / cfg.data.processed_dir / "panel.parquet")
    close_only = panel.drop(columns=[f"{c}_{leg}" for c in ("open", "high", "low") for leg in "ab"])
    decisions = pd.Series(0, index=close_only.index)
    _, orders = bt.execution_targets(decisions, period, 0.5)

    with pytest.raises(bt.BacktestGuardError, match="next_close"):
        bt.simulate(close_only, orders, cfg)
    next_close = config(project, "costs=flat_bps", "backtest.execution=next_close")
    pf = bt.simulate(close_only, orders, next_close)
    assert pf.value().iloc[-1] == cfg.backtest.init_cash
    with pytest.raises(bt.BacktestGuardError, match="must be one of"):
        bt.simulate(panel, orders, config(project, "costs=flat_bps", "backtest.execution=x"))


def test_costs_reduce_returns(project):
    flat = ("costs=flat_bps",)
    cheap = bt.run_backtest(
        config(project, *flat, "costs.fee_bps=0", "costs.slippage_bps=0"), project
    )
    dear = bt.run_backtest(
        config(project, *flat, "costs.fee_bps=20", "costs.slippage_bps=20"), project
    )
    assert dear["total_return"] < cheap["total_return"]
    assert dear["n_entries"] == cheap["n_entries"]


def test_walk_forward_run_is_logged(project):
    from quant_lab.backtest.walkforward import run_walk_forward

    cfg = config(
        project,
        "walkforward.grid.window=[40,80]",
        "walkforward.grid.entry_z=[2.0]",
        "walkforward.grid.exit_z=[0.5]",
    )
    result = run_walk_forward(cfg, project)
    run = mlflow.get_run(result["run_id"])
    assert run.data.tags["kind"] == "walkforward"
    assert run.data.tags["period_end"] == cfg.split.validation.end  # never past validation
    assert {"wf_sharpe", "wf_n_folds", "wf_positive_folds"} <= set(run.data.metrics)
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(result["run_id"])}
    assert {"folds.csv", "grid_scores.csv", "walkforward_equity.png", "config.yaml"} <= artifacts
    assert result["folds"]["test_end"].max() <= pd.Timestamp(cfg.split.validation.end).date()


def test_hydra_cli_end_to_end(project, tmp_path):
    cmd = [
        sys.executable,
        "-m",
        "quant_lab.backtest.run",
        f"mlflow.tracking_uri=sqlite:///{project}/mlflow.db",
        f"hydra.run.dir={tmp_path}/hydra",
    ]
    ok = subprocess.run(cmd, cwd=project, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert "sharpe" in ok.stdout

    refused = subprocess.run(
        [*cmd, "split.train.end=2009-01-01"], cwd=project, capture_output=True, text=True
    )
    assert refused.returncode != 0
    assert "split boundaries are locked" in refused.stderr
    assert np.isfinite(float(ok.stdout.split("sharpe:")[1].split()[0]))
