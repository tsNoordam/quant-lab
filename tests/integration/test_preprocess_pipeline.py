"""End to end: synthetic raw files -> DVC preprocess stage -> panel + metrics."""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from omegaconf import OmegaConf

from quant_lab.data.preprocess import PANEL_FILE, REPORT_FILE, load_dataset_config, preprocess
from quant_lab.data.synthetic import generate_pair, write_raw
from quant_lab.data.validation import DataValidationError

ROOT = Path(__file__).resolve().parents[2]
DATASET = "synthetic_twin"


@pytest.fixture
def project(tmp_path):
    shutil.copytree(ROOT / "conf", tmp_path / "conf")
    cfg = load_dataset_config(DATASET, tmp_path)
    cfg.synthetic.n_days = 300
    write_raw(cfg, tmp_path)
    return tmp_path, cfg


def test_generator_is_deterministic_and_matches_its_ground_truth():
    cfg = load_dataset_config(DATASET, ROOT)
    legs1, truth = generate_pair(cfg)
    legs2, _ = generate_pair(cfg)
    for symbol in legs1:
        pd.testing.assert_frame_equal(legs1[symbol], legs2[symbol])

    a, b = legs1[cfg.legs.a]["close"], legs1[cfg.legs.b]["close"]
    common = a.index.intersection(b.index)
    implied = np.log(a[common] / (cfg.parity_ratio * b[common]))
    np.testing.assert_allclose(implied, truth.loc[common, "mispricing"], atol=1e-4)


def test_raw_files_are_immutable(project):
    root, cfg = project
    with pytest.raises(FileExistsError):
        write_raw(cfg, root)


def test_preprocess_writes_panel_and_report(project):
    root, cfg = project
    report = preprocess(cfg, root)

    panel = pd.read_parquet(root / cfg.processed_dir / PANEL_FILE)
    assert panel.index.is_monotonic_increasing and panel.index.is_unique
    assert {"close_a", "close_b", "volume_a", "volume_b", "stale_a", "stale_b"} <= set(panel)
    assert not panel.isna().any().any()
    assert report == json.loads((root / cfg.processed_dir / REPORT_FILE).read_text())
    assert report["rows"] == len(panel)


def test_preprocess_is_deterministic(project):
    root, cfg = project
    first = preprocess(cfg, root)
    panel_first = pd.read_parquet(root / cfg.processed_dir / PANEL_FILE)
    assert preprocess(cfg, root) == first
    pd.testing.assert_frame_equal(
        pd.read_parquet(root / cfg.processed_dir / PANEL_FILE), panel_first
    )


def test_corrupt_raw_data_stops_the_stage(project):
    root, cfg = project
    path = root / cfg.raw_dir / f"{cfg.legs.b}.csv"
    raw = pd.read_csv(path)
    raw.loc[5, "close"] = -1.0
    raw.to_csv(path, index=False)
    with pytest.raises(DataValidationError, match="non_positive_price"):
        preprocess(cfg, root)
    assert not (root / cfg.processed_dir / PANEL_FILE).exists()


def test_dvc_stage_params_exist_in_the_dataset_config():
    stage = yaml.safe_load((ROOT / "dvc.yaml").read_text())["stages"]["preprocess"]
    for dataset in stage["foreach"]:
        cfg = OmegaConf.to_container(load_dataset_config(dataset, ROOT))
        for entry in stage["do"]["params"]:
            (keys,) = entry.values()
            assert set(keys) <= set(cfg), f"{dataset}: dvc.yaml params missing from config"
