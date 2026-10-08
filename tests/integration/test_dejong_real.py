"""de Jong et al. (2009) Tables II and III on the real DLC workbooks (skipped without
the data).

Pins the replication: every statistic agrees with the paper within rounding,
except the documented differences below. If the data or the code changes, both
directions are caught: a new mismatch fails, and a documented difference that
disappears fails too (update the report, then this list).
"""

import shutil
from pathlib import Path

import pytest

from quant_lab.data.dlc import convert, load_twin_config, twins
from quant_lab.models.dejong import SUMS, table2, table3

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
    return reports, table2(lab), table3(lab)


# research/reports/dejong_table3.md explains each (identified specification).
KNOWN_T3_DIFFERENCES = {
    *(("abb", s) for s in ("r2", "df", "sum_index_a", "sum_fx")),  # one observation fewer
    ("brambles", "df"),  # 292 vs 293; every other Brambles value matches
    ("merita_nordbanken", "sum_lagged_dependent"),  # -0.317 vs -0.371: transposed digits
    ("smithkline", "durbin_watson"),  # 2.12 vs 2.14; every other value matches
}


def test_every_twin_reproduces_the_authors_deviation_column(result):
    reports, _, _ = result
    for twin, r in reports.items():
        kept = r["rows"] + r.get("rows_after_window", 0)  # window + trading extension
        assert r["rows_checked_against_workbook"] == kept > 0, twin
        assert r["max_abs_error_vs_workbook"] < 1e-12, twin
        assert r["ratio_constant"], twin
        reg = r["regression"]
        assert reg["returns_checked_against_panel"] > 0, twin
        assert reg["max_abs_error_vs_panel"] < 1e-12, twin


def test_table2_matches_except_documented_differences(result):
    _, t, _ = result
    off = {(r.twin, r.statistic) for r in t.itertuples() if not r.within_rounding}
    assert off == KNOWN_DIFFERENCES


def test_rio_tinto_differs_only_in_sign(result):
    _, t, _ = result
    row = t[(t.twin == "rio_tinto") & (t.statistic == "mean")].iloc[0]
    assert row.ours == pytest.approx(-row.paper, abs=0.01)


def test_table3_matches_except_documented_differences(result):
    _, _, t = result
    t = t[t.variant == "identified"]
    off = {(r.twin, r.statistic) for r in t.itertuples() if not r.within_rounding}
    assert off == KNOWN_T3_DIFFERENCES


def test_table3_significance_marks_all_match_with_eviews_newey_west(result):
    _, _, t = result
    sums = t[(t.variant == "identified") & t.statistic.isin(SUMS)]
    assert len(sums) == 48
    assert (sums.significance_nw == sums.significance_paper).all()


def test_table3_as_stated_departs_only_for_the_identified_twins(result):
    _, _, t = result
    off = {
        r.twin
        for r in t[t.variant == "as_stated"].itertuples()
        if not r.within_rounding and (r.twin, r.statistic) not in KNOWN_T3_DIFFERENCES
    }
    assert off == {"dexia", "rd_shell", "smithkline"}


def test_merita_lagged_dependent_is_a_digit_transposition(result):
    _, _, t = result
    row = t[
        (t.variant == "identified")
        & (t.twin == "merita_nordbanken")
        & (t.statistic == "sum_lagged_dependent")
    ].iloc[0]
    assert round(row.ours, 3) == -0.317 and row.paper == -0.371
