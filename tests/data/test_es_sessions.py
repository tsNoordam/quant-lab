"""ES processed sessions (dvc stage es_ingest): checks on the real data.

Skipped until the user has downloaded the Databento files and run
``uv run dvc repro es_ingest``.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[2]
CFG = OmegaConf.load(ROOT / "conf/futures/es.yaml")
SPLIT = OmegaConf.load(ROOT / "conf/split/es.yaml")
PROCESSED = ROOT / CFG.processed_dir

pytestmark = pytest.mark.skipif(
    not (PROCESSED / "sessions.parquet").exists(),
    reason="ES data not present (dvc repro es_ingest)",
)


@pytest.fixture(scope="module")
def sessions():
    return pd.read_parquet(PROCESSED / "sessions.parquet")


@pytest.fixture(scope="module")
def rth():
    return pd.read_parquet(PROCESSED / "rth_1m.parquet")


def test_sessions_cover_every_split_period(sessions):
    for period in ("train", "validation", "oos"):
        p = SPLIT[period]
        inside = sessions.loc[p.start : p.end]
        assert len(inside) > 200, period
        assert inside["usable"].mean() > 0.95, period


def test_prices_are_on_the_tick_grid(rth):
    ticks = rth[["open", "high", "low", "close"]].to_numpy() / CFG.contract.tick_size
    assert np.allclose(ticks, np.round(ticks), atol=1e-6)


def test_gap_reference_exists_on_usable_sessions(sessions):
    used = sessions[sessions["usable"]].iloc[1:]
    assert used["prev_close"].notna().mean() > 0.99
    assert used.loc[used["roll"], "prev_close"].notna().mean() > 0.95


def test_rolls_are_quarterly(sessions):
    per_year = sessions["roll"].groupby(sessions.index.year).sum()
    full_years = per_year.loc[2011:2025]
    assert full_years.between(4, 6).all(), full_years.to_dict()


def test_front_month_bars_belong_to_their_session(rth, sessions):
    contract = rth.groupby("session")["instrument_id"].first()
    assert (contract == sessions.loc[contract.index, "instrument_id"].astype("int64")).all()
