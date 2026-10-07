"""Walk-forward selection sees only its training window; the OOS period is never used."""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest.run import BacktestGuardError
from quant_lab.backtest.walkforward import walk_forward
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw

ROOT = Path(__file__).resolve().parents[2]
SMALL_GRID = [
    "walkforward.grid.window=[40,80]",
    "walkforward.grid.entry_z=[1.5,2.5]",
    "walkforward.grid.exit_z=[0.0]",
    "walkforward.train_years=3",
]
PRICES = ["open_a", "high_a", "low_a", "close_a", "adj_close_a"]


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab")
    shutil.copytree(ROOT / "conf", root / "conf")
    data_cfg = load_dataset_config("synthetic_twin", root)
    write_raw(data_cfg, root)
    preprocess(data_cfg, root)
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        cfg = compose("config", overrides=SMALL_GRID)
    panel = pd.read_parquet(root / cfg.data.processed_dir / "panel.parquet")
    return cfg, panel, walk_forward(cfg, panel)


def shocked_after(panel, date):
    out = panel.copy()
    later = out.index > date
    out.loc[later, PRICES] *= 1.5
    out.loc[later, ["volume_a"]] *= 10
    return out


def test_oos_data_cannot_change_anything(setup):
    cfg, panel, base = setup
    result = walk_forward(cfg, shocked_after(panel, pd.Timestamp(cfg.split.validation.end)))
    pd.testing.assert_frame_equal(base["folds"], result["folds"])
    pd.testing.assert_series_equal(base["equity"], result["equity"])


def test_selection_and_test_returns_ignore_later_data(setup):
    cfg, panel, base = setup
    assert len(base["folds"]) >= 3
    fold = base["folds"].iloc[1]
    # Shock everything after fold 2's test window: folds 1-2 must be identical.
    result = walk_forward(cfg, shocked_after(panel, pd.Timestamp(fold["test_end"])))
    pd.testing.assert_frame_equal(base["folds"].iloc[:2], result["folds"].iloc[:2])
    # Shock the test window of fold 2 and everything after it. The boundary is the
    # test start (not the reported train_end, which a leaky fold builder could
    # misreport): fold 2's choice and selection score must not move.
    day_before_test = pd.Timestamp(fold["test_start"]) - pd.Timedelta(days=1)
    result = walk_forward(cfg, shocked_after(panel, day_before_test))
    chosen = [c for c in base["folds"] if c.startswith("chosen_") or c.startswith("train_")]
    pd.testing.assert_frame_equal(base["folds"].iloc[:2][chosen], result["folds"].iloc[:2][chosen])


def test_oos_only_datasets_are_refused(setup):
    cfg, panel, _ = setup
    oos_only = cfg.copy()
    oos_only.split.train = None
    with pytest.raises(BacktestGuardError, match="OOS-only"):
        walk_forward(oos_only, panel)
