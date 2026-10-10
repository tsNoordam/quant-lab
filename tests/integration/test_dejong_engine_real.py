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


def test_table6_position_days_within_one_and_a_half_percent(lab, placeholder):
    from quant_lab.backtest.dejong import evidence_label
    from quant_lab.models.dejong_risk import paper_table6

    paper = paper_table6(lab)
    days = placeholder["days"].groupby("strategy").size()
    for strategy, count in days.items():
        expected = paper[evidence_label(strategy)]["position_days"]
        assert abs(count / expected - 1) < 0.015, strategy


FACTORS = ROOT / "data" / "raw" / "french_ff" / "F-F_Research_Data_Factors_daily_CSV.zip"


@pytest.mark.skipif(
    not (TBILL.exists() and FACTORS.exists()), reason="FRED DTB3 or French factors not present"
)
def test_table6_sp500_volatility_matches_the_paper_convention(lab):
    from quant_lab.models.dejong_risk import load_inputs, table6

    for name in ("fred_tbill", "french_ff"):
        shutil.copytree(
            ROOT / "data" / "raw" / name, lab / "data" / "raw" / name, dirs_exist_ok=True
        )
    cfg = load_config(lab)
    inputs = load_inputs(lab, cfg)
    result = evaluate(lab, variant_config(cfg, None), inputs["tbill"])
    t = table6(lab, result, inputs, cfg.table6).set_index(["strategy", "statistic"])
    for strategy in cfg.strategies:
        ours = t.loc[(strategy, "sigma_sp500"), "ours"]
        paper = t.loc[(strategy, "sigma_sp500"), "paper"]
        assert abs(ours / paper - 1) < 0.025, strategy  # sigma = daily sd x 22 (D23)
        alpha = t.loc[(strategy, "alpha"), "ours"]
        assert alpha == pytest.approx(PINNED_ALPHA[strategy], abs=6e-4), strategy


# FF3 alpha % p.m. per strategy, primary configuration: French factors md5
# 95ef09e3ae6feb0733058de5c78c22a0, DTB3 md5 7edbf761... (MLflow run 4d73e5e3).
PINNED_ALPHA = {
    "5/1/1m": -0.353,
    "5/1/3m": 0.280,
    "5/1/12m": 0.419,
    "5/1/inf": 0.284,
    "10/5/1m": 0.157,
    "10/5/3m": 0.693,
    "10/5/12m": 0.794,
    "10/5/inf": 0.705,
}


# Weighted mean % p.m. per strategy, primary configuration, FRED DTB3 md5
# 7edbf7612395ad04c5f850a742743705 (MLflow run 1d9f0b53, 2026-10-09).
PINNED_WEIGHTED_MEAN = {
    "5/1/1m": -0.140,
    "5/1/3m": 0.497,
    "5/1/12m": 0.689,
    "5/1/inf": 0.639,
    "10/5/1m": 0.484,
    "10/5/3m": 1.043,
    "10/5/12m": 1.158,
    "10/5/inf": 1.131,
}


@pytest.mark.skipif(not TBILL.exists(), reason="FRED DTB3 not present (data/raw/fred_tbill)")
def test_returns_with_the_real_tbill(lab):
    shutil.copytree(
        ROOT / "data" / "raw" / "fred_tbill",
        lab / "data" / "raw" / "fred_tbill",
        dirs_exist_ok=True,
    )
    cfg = variant_config(load_config(lab), None)
    out = evaluate(lab, cfg, load_tbill(lab / cfg.tbill.path, cfg.tbill.series))
    t5 = out["table5"].set_index(["strategy", "statistic"])
    for strategy, value in PINNED_WEIGHTED_MEAN.items():
        ours = t5.loc[(strategy, "weighted_mean_return"), "ours"]
        assert ours == pytest.approx(value, abs=6e-4), strategy
    assert t5.loc[("10/5/12m", "median_return"), "ours"] == pytest.approx(3.697, abs=6e-4)


@pytest.mark.skipif(not TBILL.exists(), reason="FRED DTB3 not present (data/raw/fred_tbill)")
def test_waterfall_starts_at_the_paper_conventions(lab):
    from quant_lab.models.dejong_standard import waterfall

    shutil.copytree(
        ROOT / "data" / "raw" / "fred_tbill",
        lab / "data" / "raw" / "fred_tbill",
        dirs_exist_ok=True,
    )
    cfg = load_config(lab)
    t = waterfall(lab, cfg, load_tbill(lab / cfg.tbill.path, cfg.tbill.series), "10/5/12m")
    t = t[t.group == "all"].set_index("step")
    assert t.loc["paper", "weighted_mean_pm"] == pytest.approx(
        PINNED_WEIGHTED_MEAN["10/5/12m"], abs=6e-4
    )
    assert t.loc["paper", "positions"] == 128
    # trading one close later is the largest single change (report: dejong_standard.md)
    steps = list(t.index)
    drops = {
        s: t.loc[a, "weighted_mean_pm"] - t.loc[s, "weighted_mean_pm"]
        for a, s in zip(steps[:-1], steps[1:], strict=True)
    }
    assert max(drops, key=drops.get) == "next_close"
    # the user's run 8b36f314 (DTB3 md5 7edbf761...), all twins
    pinned = {"paper": 1.158, "dexia_cleaned": 1.201, "next_close": 0.530,
              "marked_at_end": 0.471, "no_padding": 0.662}  # fmt: skip
    for step, value in pinned.items():
        assert t.loc[step, "weighted_mean_pm"] == pytest.approx(value, abs=6e-4), step
    assert t.loc["no_padding", "sharpe"] == pytest.approx(0.162, abs=6e-4)
