"""SILTA regressions through Hydra and MLflow on a self-contained synthetic project."""

import shutil
from pathlib import Path

import mlflow
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest.run import BacktestGuardError
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw
from quant_lab.models import silta

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("silta")
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


def _panel(root: Path, cfg) -> pd.DataFrame:
    return pd.read_parquet(root / cfg.data.processed_dir / "panel.parquet")


def test_run_logs_regressions_to_mlflow(project):
    out = silta.run_silta(config(project), project)
    run = mlflow.get_run(out["run_id"])
    assert run.data.tags["kind"] == "silta_regressions"
    assert run.data.tags["unlock_oos"] == "false"
    assert len(run.data.tags["data_md5"]) == 32
    assert {f"{s}_t_beta" for s in silta.SPECS} <= set(run.data.metrics)
    assert run.data.params["silta.causal_window"] == "250"
    artifacts = {a.path for a in mlflow.MlflowClient().list_artifacts(out["run_id"])}
    assert {"regressions.csv", "chi_condition.csv", "lag_sensitivity.csv"} <= artifacts
    assert set(out["results"]["window"]) == {"development", "train", "validation"}


def test_independent_volume_gives_no_significant_slope(project):
    """Negative control: the synthetic pair's volume is independent of its prices."""
    res = silta.analyse(config(project), _panel(project, config(project))).get("results")
    dev = res[res["window"] == "development"].set_index("spec")
    for spec in ("raw_shares", "std", "std_detrended", "causal"):
        assert abs(dev.loc[spec, "t_beta"]) < 2.5, spec


def test_data_after_validation_cannot_affect_the_results(project):
    cfg = config(project)
    panel = _panel(project, cfg)
    end = pd.Timestamp(cfg.split.validation.end)
    shocked = panel.copy()
    later = shocked.index > end
    shocked.loc[later, ["close_a", "volume_a"]] *= 3.0
    base = silta.analyse(cfg, panel)
    pd.testing.assert_frame_equal(base["results"], silta.analyse(cfg, shocked)["results"])
    # mutation check: the same shock inside the validation window does change them
    inside = (panel.index > pd.Timestamp(cfg.split.validation.start)) & (panel.index <= end)
    moved = panel.copy()
    moved.loc[inside, ["close_a", "volume_a"]] *= 3.0
    assert not base["results"].equals(silta.analyse(cfg, moved)["results"])


def test_oos_only_dataset_is_refused(project):
    cfg = config(project, "data=rio_tinto")
    with pytest.raises(BacktestGuardError, match="OOS-only"):
        silta.analyse(cfg, pd.DataFrame())


def test_unreliable_volume_is_refused(project):
    cfg = config(project, "+data.volume_reliable=false")
    with pytest.raises(BacktestGuardError, match="volume_reliable"):
        silta.analyse(cfg, _panel(project, cfg))


def test_split_overrides_are_refused(project):
    with pytest.raises(BacktestGuardError, match="locked"):
        silta.run_silta(config(project), project, ["split.validation.end=2010-01-01"])
