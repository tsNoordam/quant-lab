"""Dividend cash uses only information up to each ex-date (re-audit 2026-10-07, B2).

The synthetic pair has no dividends (adj_close == close) and the other
structural shocks scale close and adj_close together, so without this file no
structural test would exercise the dividend path.
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest.dividends import dividends_per_share
from quant_lab.backtest.run import Period, backtest_pair
from quant_lab.data.preprocess import load_dataset_config, preprocess
from quant_lab.data.synthetic import write_raw
from quant_lab.strategies.parity_zscore import target_positions

ROOT = Path(__file__).resolve().parents[2]
BARS = ("open", "high", "low", "close")


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab")
    shutil.copytree(ROOT / "conf", root / "conf")
    data_cfg = load_dataset_config("synthetic_twin", root)
    write_raw(data_cfg, root)
    preprocess(data_cfg, root)
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        cfg = compose("config", overrides=["backtest.execution=next_close"])
    panel = pd.read_parquet(root / cfg.data.processed_dir / "panel.parquet")
    period = Period("t", panel.index[0], panel.index[-1])
    decisions, _ = target_positions(panel, window=60, entry_z=2.0, exit_z=0.5)
    return cfg, panel, period, decisions, backtest_pair(panel, decisions, period, cfg)


def with_ex_dividend(panel, row, drop=0.97):
    out = panel.copy()
    for leg in "ab":
        cols = [out.columns.get_loc(f"{c}_{leg}") for c in BARS]
        out.iloc[row:, cols] *= drop  # price drops, adj_close (total return) unchanged
    return out


def test_future_dividends_do_not_change_past_equity(setup):
    cfg, panel, period, decisions, base = setup
    held = base.held
    cut = next(i for i in range(200, len(panel)) if held.iloc[i - 1] != 0 and held.iloc[i] != 0)
    sim = backtest_pair(with_ex_dividend(panel, cut), decisions, period, cfg)
    pd.testing.assert_series_equal(sim.equity.iloc[:cut], base.equity.iloc[:cut])
    assert sim.dividends.iloc[cut] != 0  # the held position is paid / charged on the ex-date
    # total-return neutral: only the borrow charge on the lower short value moves
    assert abs(sim.equity.iloc[cut] - base.equity.iloc[cut]) < 1.0


def test_dividend_on_a_dropped_day_is_booked_on_the_next_joint_row():
    idx = pd.bdate_range("2020-01-01", periods=6)
    full = pd.DataFrame({"close_a": 100.0, "adj_close_a": 100.0}, index=idx)
    full.iloc[3:, 0] = 97.0  # ex-date on row 3
    joint = full.drop(idx[3])  # the other market was closed on the ex-date
    dps = dividends_per_share(joint, "a", min_yield=0.005)
    assert dps.loc[idx[4]] == pytest.approx(3.0)
    assert (dps.drop(idx[4]) == 0).all()
