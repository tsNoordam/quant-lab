"""Freeze audit A1: a pair's parity must be knowable before the OOS period.

RD/Shell parity = 1.5 x N_Shell / N_RD (60/40 dividend split). The workbook
constant 6.863 matches the share counts of 2000-02 only (the OOS period); the
development-period share counts give 6.956 in every year once the 1989 and 1997
share splits are taken into account.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data/processed/rd_shell/panel.parquet"


@pytest.mark.skipif(not PANEL.exists(), reason="rd_shell panel not present (dvc pull)")
def test_rd_shell_parity_is_knowable_before_the_oos_period():
    cfg = OmegaConf.load(ROOT / "conf/data/rd_shell.yaml")
    split = OmegaConf.load(ROOT / "conf/split/rd_shell.yaml")
    p = pd.read_parquet(PANEL).loc["1997-07-01" : split.validation.end]  # after the 1997 splits
    implied = 1.5 * p["shares_outstanding_b"] / p["shares_outstanding_a"]
    gap = abs(np.log(cfg.parity_ratio / implied.median()))
    assert gap < 0.0025, f"parity is {gap * 1e4:.0f} bps from the development share-count parity"


@pytest.mark.skipif(not PANEL.exists(), reason="rd_shell panel not present (dvc pull)")
def test_split_adjusted_share_count_parity_is_stable_through_development():
    """The constant is the point-in-time value at every development date (within 0.1%)."""
    cfg = OmegaConf.load(ROOT / "conf/data/rd_shell.yaml")
    split = OmegaConf.load(ROOT / "conf/split/rd_shell.yaml")
    p = pd.read_parquet(PANEL).loc[: split.validation.end]
    raw = 1.5 * p["shares_outstanding_b"] / p["shares_outstanding_a"]
    # share splits change the raw ratio by these factors; undo them
    adjusted = raw.copy()
    adjusted[raw < 6.5] *= 9 / 8
    adjusted[raw > 8.0] *= 3 / 4
    assert (np.abs(np.log(adjusted / cfg.parity_ratio)) < 0.001).all()
