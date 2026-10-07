"""Every dataset composes with its own locked split and a valid execution model."""

from pathlib import Path

import pandas as pd
import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from quant_lab.backtest import run as bt

ROOT = Path(__file__).resolve().parents[2]
DATASETS = sorted(p.stem for p in (ROOT / "conf" / "data").glob("*.yaml"))
REAL = {"rd_shell", "reed_elsevier", "rio_tinto"}


def compose_for(*overrides):
    with initialize_config_dir(config_dir=str(ROOT / "conf"), version_base="1.3"):
        return compose("config", overrides=list(overrides))


@pytest.mark.parametrize("dataset", DATASETS)
def test_dataset_selects_its_own_split(dataset):
    cfg = compose_for(f"data={dataset}")
    assert cfg.split.name == cfg.data.name == dataset


@pytest.mark.parametrize("dataset", DATASETS)
def test_close_only_datasets_fill_at_the_next_close(dataset):
    cfg = compose_for(f"data={dataset}")
    assert cfg.backtest.execution == ("next_close" if dataset in REAL else "next_open")


@pytest.mark.parametrize("dataset", DATASETS)
def test_split_periods_are_ordered_and_inside_the_data_window(dataset):
    cfg = compose_for(f"data={dataset}")
    periods = [
        (pd.Timestamp(cfg.split[p].start), pd.Timestamp(cfg.split[p].end))
        for p in ("train", "validation", "oos")
        if cfg.split[p] is not None
    ]
    assert periods, "every dataset needs at least an OOS period"
    for (s1, e1), (s2, _) in zip(periods, periods[1:], strict=False):
        assert s1 <= e1 < s2
    window = OmegaConf.select(cfg, "data.source.window")
    if window is not None:
        assert periods[0][0] >= pd.Timestamp(window.start)
        assert periods[-1][1] <= pd.Timestamp(window.end)


def test_mismatched_split_is_refused():
    cfg = compose_for("data=rd_shell", "split=synthetic_twin")
    with pytest.raises(bt.BacktestGuardError, match="does not belong"):
        bt.select_period(cfg)


def test_oos_only_pair_has_no_development_periods():
    cfg = compose_for("data=rio_tinto")
    for period in ("train", "validation"):
        with pytest.raises(bt.BacktestGuardError, match="no .* period"):
            bt.select_period(compose_for("data=rio_tinto", f"backtest.period={period}"))
    assert cfg.split.oos is not None
