"""Step 18 waterfall: cumulative steps, time-zone groups, calendar-time metric."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_lab.backtest.dejong import load_config, monthly_return
from quant_lab.models.dejong_standard import calendar_metric, step_configs, time_zone_groups

ROOT = Path(__file__).resolve().parents[2]


def test_steps_are_cumulative_and_start_at_the_paper():
    steps = step_configs(load_config(ROOT))
    names = [n for n, _ in steps]
    assert names == ["paper", "dexia_cleaned", "next_close", "marked_at_end", "no_padding"]
    paper, last = steps[0][1], steps[-1][1]
    assert paper.rules.delay == 0 and paper.returns.padding and paper.rules.lockout_days == 22
    assert paper.exclude_dates == {}
    # the last step carries every change before it
    assert last.rules.delay == 1 and not last.rules.hold_after_window
    assert last.rules.open_at_end == "mark" and last.rules.lockout_days == 0
    assert not last.returns.padding and list(last.exclude_dates.dexia) == ["1997-12-19"]
    assert last.costs.commission == paper.costs.commission  # costs stay the paper's


def test_time_zone_groups_follow_table_i():
    groups = time_zone_groups(ROOT)
    assert len(groups) == 12
    assert {t for t, g in groups.items() if g == "10h"} == {"rio_tinto", "bhp_billiton", "brambles"}
    assert {t for t, g in groups.items() if g == "0h"} == {"abb", "dexia", "fortis"}
    assert groups["smithkline"] == "5h" and groups["rd_shell"] == "1h"


def test_calendar_metric_counts_flat_days_at_the_tbill():
    dates = pd.bdate_range("2000-01-03", periods=10)
    tbill = pd.Series(0.052, index=dates[:1])
    rf = 0.052 / 260
    days = pd.DataFrame(
        {"date": dates[[0, 0, 1]], "return": [rf + 0.01, rf - 0.01, rf + 0.002]}
    )  # two positions on day 0 average to the T-bill; one position on day 1
    m = calendar_metric(days, tbill, str(dates[0].date()), str(dates[-1].date()))
    excess = np.zeros(10)
    excess[1] = 0.002
    assert m["excess_return_pa"] == pytest.approx(excess.mean() * 260 * 100)
    assert m["share_days_invested"] == pytest.approx(0.2)
    assert m["sharpe"] == pytest.approx(excess.mean() / excess.std(ddof=1) * np.sqrt(260))


def test_no_padding_counts_a_position_by_its_own_days():
    assert monthly_return(0.02, 5, 0.05, 22, 260, padding=False) == (5, pytest.approx(8.8))
    counted, _ = monthly_return(0.02, 5, 0.05, 22, 260, padding=True)
    assert counted == 22
