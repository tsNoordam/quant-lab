"""The robustness runner end to end on a synthetic project (small grids)."""

import shutil
from pathlib import Path

import mlflow
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf, open_dict

from quant_lab.backtest import robustness
from quant_lab.backtest.run import BacktestGuardError, run_backtest
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw

ROOT = Path(__file__).resolve().parents[2]
SMALL = {
    "parity_zscore": [
        "strategy.grid.window=[40,80]",
        "strategy.grid.entry_z=[2.0]",
        "strategy.grid.exit_z=[0.5]",
    ],
    "silta_parity": ["strategy.grid.entry_bound=[0.018,0.036]", "strategy.grid.exit_bound=[0.0]"],
}


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("robust")
    shutil.copytree(ROOT / "conf", root / "conf")
    cfg = load_dataset_config("synthetic_twin", root)
    write_raw(cfg, root)
    preprocess(cfg, root)
    return root


def _setup(root: Path, development_pair: str):
    base = [f"mlflow.tracking_uri=sqlite:///{root}/mlflow.db", "walkforward.train_years=3"]

    def comp(overrides):
        with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
            return compose("config", overrides=overrides)

    cfg = comp(base)
    with open_dict(cfg):
        cfg.robustness.development_pair = development_pair
        cfg.robustness.cases = OmegaConf.create(
            {
                "base": SMALL,
                "zero_cost": {
                    "all": ["costs=flat_bps", "costs.fee_bps=0", "costs.slippage_bps=0"],
                    **SMALL,
                },
                "wf_rolling": {"frozen": False, "all": ["walkforward.anchored=false"], **SMALL},
            }
        )
    return cfg, base, comp


def test_development_pair_runs_walk_forward_and_frozen_runs(project):
    cfg, base, comp = _setup(project, "synthetic_twin")
    out = robustness.run_robustness(cfg, project, base, comp)
    t = out["table"]
    assert set(t["strategy"]) == {"parity_zscore", "silta_parity"}
    assert set(t["run"]) == {"walkforward", "train", "validation"}
    rolling = t[t["case"] == "wf_rolling"]
    assert set(rolling["run"]) == {"walkforward"}  # frozen: false
    for name in ("deflated_sharpe", "concentration", "parity_zscore_subperiods"):
        assert name in out
    # 2 strategies x 2 grid points x 2 cost settings, at least
    assert out["n_trials"] >= 8
    run = mlflow.get_run(out["run_id"])
    assert run.data.tags["kind"] == "robustness_summary"
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(out["run_id"])}
    assert {"cases.csv", "deflated_sharpe.csv", "silta_parity_grid_position.csv"} <= artifacts


def test_other_pairs_are_only_evaluated_at_frozen_values(project):
    cfg, base, comp = _setup(project, "some_other_pair")
    out = robustness.run_robustness(cfg, project, base, comp)
    t = out["table"]
    assert "walkforward" not in set(t["run"])
    assert "wf_rolling" not in set(t["case"])
    assert "deflated_sharpe" not in out


def test_rerunning_an_identical_configuration_adds_no_trial(project):
    cfg, base, comp = _setup(project, "synthetic_twin")
    uri = cfg.mlflow.tracking_uri
    before = robustness.count_trials(uri, "synthetic_twin")
    run_backtest(
        comp(
            [
                *base,
                "strategy=silta_parity",
                "strategy.grid.entry_bound=[0.018,0.036]",
                "strategy.grid.exit_bound=[0.0]",
            ]
        ),
        project,
    )
    assert robustness.count_trials(uri, "synthetic_twin") == before
    run_backtest(comp([*base, "strategy=silta_parity", "strategy.entry_bound=0.05"]), project)
    assert robustness.count_trials(uri, "synthetic_twin") == before + 1


def test_oos_unlock_is_refused(project):
    cfg, base, comp = _setup(project, "synthetic_twin")
    with open_dict(cfg):
        cfg.unlock_oos = True
    with pytest.raises(BacktestGuardError, match="unlock_oos"):
        robustness.run_robustness(cfg, project, base, comp)
