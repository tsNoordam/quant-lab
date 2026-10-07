"""The SILTA arbitrageur through Hydra, the engine, walk-forward and MLflow (synthetic data)."""

import shutil
from pathlib import Path

import mlflow
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest import run as bt
from quant_lab.backtest.walkforward import evaluate, walk_forward
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("silta_parity")
    shutil.copytree(ROOT / "conf", root / "conf")
    cfg = load_dataset_config("synthetic_twin", root)
    write_raw(cfg, root)
    preprocess(cfg, root)
    return root


def config(root: Path, *overrides: str):
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        return compose(
            "config",
            overrides=[
                f"mlflow.tracking_uri=sqlite:///{root}/mlflow.db",
                "strategy=silta_parity",
                *overrides,
            ],
        )


def test_run_logs_the_parity_deviation_signal(project):
    result = bt.run_backtest(config(project), project)
    run = mlflow.get_run(result["run_id"])
    assert run.data.tags["strategy"] == "silta_parity"
    assert run.data.params["strategy.entry_bound"] == "0.018"
    assert run.data.metrics["n_entries"] > 0
    path = mlflow.artifacts.download_artifacts(run_id=result["run_id"], artifact_path="daily.csv")
    assert "parity_deviation" in pd.read_csv(path).columns


def test_trading_the_known_mispricing_at_zero_cost_is_profitable(project):
    """Positive control: the synthetic deviation from parity is a mean-zero OU process,
    so shorting it beyond the bound and closing at parity must make money before costs.
    Fails if the trade direction, the parity or the execution lag is wrong."""
    flat = ("costs=flat_bps", "costs.fee_bps=0", "costs.slippage_bps=0")
    for period in ("train", "validation"):
        result = bt.run_backtest(config(project, *flat, f"backtest.period={period}"), project)
        assert result["total_return"] > 0, period
    flipped = config(project, *flat, "data.parity_ratio=1.6")  # wrong parity: no edge
    assert bt.run_backtest(flipped, project)["n_entries"] <= 2


def test_walk_forward_searches_the_strategy_own_grid(project):
    cfg = config(project, "walkforward.train_years=3")
    result = walk_forward(cfg, pd.read_parquet(project / cfg.data.processed_dir / "panel.parquet"))
    assert {"chosen_entry_bound", "chosen_exit_bound"} <= set(result["folds"].columns)
    assert set(result["grid"]["entry_bound"]) == {0.018, 0.036, 0.054}
    assert result["summary"]["wf_n_trials"] == 6 * result["summary"]["wf_n_folds"]


def test_grid_parameters_must_belong_to_the_strategy(project):
    cfg = config(project)
    panel = pd.read_parquet(project / cfg.data.processed_dir / "panel.parquet")
    with pytest.raises(bt.BacktestGuardError, match="not in strategy config"):
        evaluate(panel, bt.select_period(cfg), cfg, {"window": 60})
