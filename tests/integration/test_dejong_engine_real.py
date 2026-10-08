"""de Jong et al. (2009) Tables IV-V on the real DLC workbooks (skipped without the data).

Positions, holding periods and cut-offs do not depend on the T-bill rate (it
only pads the returns of positions shorter than a month), so they are pinned
here with a constant placeholder rate. Return statistics need the real FRED
series (data/raw/fred_tbill) and are checked by the last test only.
research/reports/dejong_tables45.md explains every listed difference.
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest

from quant_lab.backtest.dejong import evaluate, load_config, load_trading, variant_config
from quant_lab.data.dlc import convert, load_twin_config, twins
from quant_lab.data.tbill import load_tbill

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / "data" / "raw" / "datastream_dlc"
TBILL = ROOT / "data" / "raw" / "fred_tbill" / "DTB3.csv"
NEEDED = {load_twin_config(t, ROOT).source.archive.split("/")[-1] for t in twins(ROOT)}

pytestmark = pytest.mark.skipif(
    not all((ARCHIVES / name).exists() for name in NEEDED),
    reason="all 12 DLC archives not present (dvc pull)",
)

HOLDING = {
    "positions_long_a",
    "positions_short_a",
    "mean_days",
    "median_days",
    "min_days",
    "max_days",
    "cut_offs",
}
# Table IV (benchmark 10%/5%/12 months), holding statistics that differ.
KNOWN_T4 = {
    ("abb", "median_days"),  # 51.5 vs 77: even count, the paper takes the upper middle value
    ("smithkline", "median_days"),  # 193.5 vs 260: idem
    ("dexia", "median_days"),  # 108 vs 46: even count, the paper takes the lower middle value
    ("merita_nordbanken", "median_days"),  # 25.5 vs 22: idem
    ("smithkline", "mean_days"),  # 166.8 vs 167.7 (Smithkline trades on Bloomberg dates here)
    ("rio_tinto", "mean_days"),  # 24.77 vs 24.6
    ("rd_shell", "cut_offs"),  # 4 vs 5
    ("reed_elsevier", "positions_long_a"),  # 7 vs 6
    ("reed_elsevier", "mean_days"),
    ("reed_elsevier", "median_days"),
    ("total", "positions_long_a"),  # 59 vs 58: Reed
    ("total", "mean_days"),  # 81.5 vs 82.0
    ("total", "cut_offs"),  # 17 vs 18: RD/Shell
}


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    lab = tmp_path_factory.mktemp("dlc_engine")
    shutil.copytree(ROOT / "conf", lab / "conf")
    (lab / "research" / "evidence").mkdir(parents=True)
    shutil.copy(ROOT / "research/evidence/dejong_dlc_evidence.csv", lab / "research/evidence")
    (lab / "data" / "raw").mkdir(parents=True)
    (lab / "data" / "raw" / "datastream_dlc").symlink_to(ARCHIVES)
    for twin in twins(lab):
        convert(load_twin_config(twin, lab), lab)
    return lab


@pytest.fixture(scope="module")
def placeholder(lab):
    tbill = pd.Series(0.05, index=pd.to_datetime(["1970-01-01"]))
    return evaluate(lab, variant_config(load_config(lab), None), tbill)


def test_unified_twins_close_on_the_first_trading_day_after_the_announcement(lab):
    for twin in twins(lab):
        cfg = load_twin_config(twin, lab)
        panel = load_trading(lab, twin, [])
        if cfg.trading.rows_after_window == 0:
            assert panel["in_window"].all(), twin
            continue
        announced = pd.Timestamp(cfg.table_i.unification_announced)
        last = panel.index[-1]
        assert last > announced, twin
        assert panel.index[-2] <= announced, twin  # the day before is not after it


def test_table4_holding_statistics(placeholder):
    t = placeholder["table4"]
    t = t[t.statistic.isin(HOLDING)]
    off = {(r.twin, r.statistic) for r in t.itertuples() if not r.within_rounding}
    assert off == KNOWN_T4


def test_table4_position_counts_match_for_eleven_twins(placeholder):
    t = placeholder["table4"]
    counts = t[t.statistic.isin({"positions_long_a", "positions_short_a"})]
    off = {r.twin for r in counts.itertuples() if not r.within_rounding}
    assert off == {"reed_elsevier", "total"}


def test_table5_position_counts_within_four_of_the_paper(placeholder):
    t = placeholder["table5"]
    counts = t[t.statistic.isin({"positions_long_a", "positions_short_a", "cut_offs"})]
    assert (counts.difference.abs() <= 4).all()


@pytest.mark.skipif(not TBILL.exists(), reason="FRED DTB3 not present (data/raw/fred_tbill)")
def test_benchmark_returns_with_the_real_tbill(lab):
    shutil.copytree(ROOT / "data" / "raw" / "fred_tbill", lab / "data" / "raw" / "fred_tbill")
    cfg = variant_config(load_config(lab), None)
    out = evaluate(lab, cfg, load_tbill(lab / cfg.tbill.path, cfg.tbill.series))
    t5 = out["table5"].set_index(["strategy", "statistic"])
    # provisional bounds until the step-16 report pins the numbers of the user's run
    assert abs(t5.loc[("10/5/12m", "weighted_mean_return"), "difference"]) < 0.1
    assert abs(t5.loc[("10/5/12m", "median_return"), "difference"]) < 0.1
