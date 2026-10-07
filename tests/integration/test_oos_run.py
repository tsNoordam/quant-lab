"""The OOS evaluation end to end on the synthetic pair (its own locked OOS window)."""

import shutil
from pathlib import Path

import mlflow
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf, open_dict

from quant_lab.backtest import oos
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("oos")
    shutil.copytree(ROOT / "conf", root / "conf")
    cfg = load_dataset_config("synthetic_twin", root)
    write_raw(cfg, root)
    preprocess(cfg, root)
    return root


def test_oos_evaluation_runs_every_preregistered_case(project):
    base = [f"mlflow.tracking_uri=sqlite:///{project}/mlflow.db", "+unlock_oos=true"]

    def comp(overrides):
        with initialize_config_dir(config_dir=str(project / "conf"), version_base="1.3"):
            return compose("config", overrides=overrides)

    cfg = comp(base)
    with open_dict(cfg):
        cfg.oos.pairs = ["synthetic_twin"]
        cfg.oos.prediction_pairs = ["synthetic_twin"]
        cfg.oos.subperiod_breaks = OmegaConf.create({"synthetic_twin": ["2009-01-01"]})
        cfg.oos.not_evaluable = OmegaConf.create(
            [{"pair": "synthetic_twin", "strategy": "silta_parity", "reason": "test"}]
        )
        cfg.oos.deflation.n_trials = 100
        cfg.oos.deflation.var_sr_per_period = {"parity_zscore": 1e-4, "silta_parity": 1e-4}
    out = oos.run_oos(cfg, project, base, comp, require_freeze=False)

    t = out["table"].set_index("strategy")
    assert set(t.index) == {"parity_zscore", "silta_parity"}
    assert t.loc["silta_parity", "verdict"].startswith("not evaluable (pre-declared")
    for case in cfg.oos.secondary:
        assert f"{case}_sharpe" in t.columns
    assert set(out["pattern"]) == {"synthetic_twin"}
    run = mlflow.get_run(out["run_id"])
    assert run.data.tags["kind"] == "oos_evaluation" and run.data.tags["unlock_oos"] == "true"
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(out["run_id"])}
    assert {"oos_results.csv", "oos_years.csv", "oos_subperiods.csv"} <= artifacts
    # every backtest behind it is tagged as an OOS run
    exp = mlflow.get_experiment_by_name("synthetic_twin.parity_zscore")
    labels = mlflow.search_runs([exp.experiment_id])["tags.run_label"]
    assert {"oos_primary", "oos_zero_cost"} <= set(labels)
