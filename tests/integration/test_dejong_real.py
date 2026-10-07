"""de Jong et al. (2009) Table II on the real DLC workbooks (skipped without the data).

Pins the replication: every Table II statistic agrees with the paper within
rounding, except the documented differences below. If the data or the code
changes, both directions are caught: a new mismatch fails, and a documented
difference that disappears fails too (update the report, then this list).
"""

import shutil
from pathlib import Path

import pytest

from quant_lab.data.dlc import convert, load_twin_config, twins
from quant_lab.models.dejong import table2

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / "data" / "raw" / "datastream_dlc"
NEEDED = {load_twin_config(t, ROOT).source.archive.split("/")[-1] for t in twins(ROOT)}

pytestmark = pytest.mark.skipif(
    not all((ARCHIVES / name).exists() for name in NEEDED),
    reason="all 12 DLC archives not present (dvc pull)",
)

# research/reports/dejong_table2.md explains each.
KNOWN_DIFFERENCES = {
    ("abb", "stdev"),  # 10.02 vs 10.17; every other ABB statistic matches
    ("rio_tinto", "mean"),  # -1.90 vs +1.90: sign (37.5% of days positive => negative mean)
    *(("dexia", s) for s in ("mean", "mean_abs", "stdev", "min", "max", "pct_positive")),
    *(("fortis", s) for s in ("mean", "mean_abs", "stdev", "min", "max", "pct_positive")),
}


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    lab = tmp_path_factory.mktemp("dlc")
    shutil.copytree(ROOT / "conf", lab / "conf")
    (lab / "research" / "evidence").mkdir(parents=True)
    shutil.copy(ROOT / "research/evidence/dejong_dlc_evidence.csv", lab / "research/evidence")
    (lab / "data" / "raw").mkdir(parents=True)
    (lab / "data" / "raw" / "datastream_dlc").symlink_to(ARCHIVES)
    reports = {t: convert(load_twin_config(t, lab), lab) for t in twins(lab)}
    return reports, table2(lab)


def test_every_twin_reproduces_the_authors_deviation_column(result):
    reports, _ = result
    for twin, r in reports.items():
        assert r["rows_checked_against_workbook"] == r["rows"] > 0, twin
        assert r["max_abs_error_vs_workbook"] < 1e-12, twin
        assert r["ratio_constant"], twin


def test_table2_matches_except_documented_differences(result):
    _, t = result
    off = {(r.twin, r.statistic) for r in t.itertuples() if not r.within_rounding}
    assert off == KNOWN_DIFFERENCES


def test_rio_tinto_differs_only_in_sign(result):
    _, t = result
    row = t[(t.twin == "rio_tinto") & (t.statistic == "mean")].iloc[0]
    assert row.ours == pytest.approx(-row.paper, abs=0.01)
