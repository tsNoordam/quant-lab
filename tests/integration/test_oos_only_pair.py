"""Freeze audit A4: a single run on an OOS-only split (rio_tinto's case), synthetic data.

The OOS period starts on the first data row, so every strategy must stay flat
through its own and the cost model's warm-up, and data after the period end
must not matter.
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest import run as bt
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw
from quant_lab.strategies import decide

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("oos_only")
    shutil.copytree(ROOT / "conf", root / "conf")
    cfg = load_dataset_config("synthetic_twin", root)
    write_raw(cfg, root)
    preprocess(cfg, root)
    return root


def oos_only(root: Path, strategy: str):
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        return compose(
            "config",
            overrides=[
                f"mlflow.tracking_uri=sqlite:///{root}/mlflow.db",
                f"strategy={strategy}",
                "split.train=null",
                "split.validation=null",
                "split.oos.start=2000-01-03",  # the first data row, as for rio_tinto
                "split.oos.end=2003-12-31",
                "backtest.period=oos",
                "+unlock_oos=true",
            ],
        )


@pytest.mark.parametrize("strategy", ["parity_zscore", "silta_parity"])
def test_oos_only_split_single_run(project, strategy):
    cfg = oos_only(project, strategy)
    period = bt.select_period(cfg)
    assert str(period.start.date()) == "2000-01-03"
    for name in ("train", "validation"):
        assert cfg.split[name] is None

    result = bt.run_backtest(cfg, project)
    assert result["unlock_oos"] == "true" and result["period"] == "oos"

    panel = pd.read_parquet(project / cfg.data.processed_dir / "panel.parquet")
    visible = panel.loc[: period.end]
    sim = bt.backtest_pair(visible, decide(visible, cfg)[0], period, cfg)
    warmup = max(cfg.costs.impact.vol_lookback_days + 1, cfg.strategy.get("window", 0))
    assert (sim.held.iloc[:warmup] == 0).all(), "position taken during warm-up"
    assert sim.held.ne(0).any(), "the test needs at least one position after warm-up"

    shocked = panel.copy()
    later = shocked.index > period.end
    shocked.loc[later, ["close_a", "open_a", "volume_a"]] *= 3
    visible2 = shocked.loc[: period.end]
    sim2 = bt.backtest_pair(visible2, decide(visible2, cfg)[0], period, cfg)
    pd.testing.assert_series_equal(sim.equity, sim2.equity)
