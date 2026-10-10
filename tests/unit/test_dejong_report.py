"""Step 19 report builder: every chart marker is filled, the page is
self-contained, and the report's numbers agree with the pinned results."""

import re
from pathlib import Path

import pytest

from quant_lab.reporting import charts as c
from quant_lab.reporting import dejong_final as r

ROOT = Path(__file__).resolve().parents[2]

# Pinned in tests/integration/test_dejong_engine_real.py (real data only); the
# report's data file must carry the same values.
WATERFALL = {
    "paper": 1.158,
    "dexia_cleaned": 1.201,
    "next_close": 0.530,
    "marked_at_end": 0.471,
    "no_padding": 0.662,
}
BENCHMARK_ALPHA = 0.794
STANDARD_SHARPE = 0.162


@pytest.fixture(scope="module")
def data():
    return r.load_data(ROOT)


@pytest.fixture(scope="module")
def html_page():
    return r.page(ROOT)


def test_every_marker_has_a_figure_and_every_figure_is_used(data):
    markers = set(r.MARKER.findall((ROOT / r.REPORT_MD).read_text(encoding="utf-8")))
    figs = set(r.build_figures(data))
    assert markers == figs


def test_page_is_standalone(html_page):
    assert not r.MARKER.search(html_page)
    assert "<title>" in html_page
    assert not re.search(r"<script[^>]+src=", html_page)
    assert not re.search(r"<link[^>]+stylesheet", html_page)
    assert not re.search(r"<img[^>]+src=\"?https?:", html_page)


def test_print_version_opens_table_views_and_forces_light():
    printed = r.page(ROOT, print_version=True)
    assert 'data-theme="light"' in printed
    assert '<details class="table-view print-open" open' in printed


def test_report_numbers_match_pins(data):
    steps = [s["id"] for s in data["waterfall"]["steps"]]
    groups = {g["id"]: g for g in data["waterfall"]["groups"]}
    assert dict(zip(steps, groups["all"]["wmean"], strict=True)) == WATERFALL
    assert groups["all"]["sharpe"][-1] == pytest.approx(STANDARD_SHARPE)
    bench = next(row for row in data["table6"]["rows"] if row["strategy"] == "10%/5%/12 months")
    assert bench["alpha"][0] == pytest.approx(BENCHMARK_ALPHA)
    lost = 1 - WATERFALL["next_close"] / WATERFALL["dexia_cleaned"]
    assert round(100 * lost) == 56


@pytest.mark.parametrize(("lo", "hi"), [(-1.9, 11.9), (0.0, 4.75), (-0.75, 0.66), (0.003, 0.0049)])
def test_nice_ticks_cover_the_data(lo, hi):
    ticks = c.nice_ticks(lo, hi, 5)
    assert ticks[0] <= lo and ticks[-1] >= hi
    assert ticks == sorted(ticks)
