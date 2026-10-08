"""Table III comovement regression (de Jong et al. 2009, E2): design, estimator, inputs."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.data.datastream import DatastreamFormatError, Sheet
from quant_lab.data.dlc import load_twin_config, regression_panel, twins
from quant_lab.models.dejong import (
    T3_STATS,
    comovement,
    comovement_design,
    eviews_lag,
    paper_table3,
    regression_spec,
    significance,
)

ROOT = Path(__file__).resolve().parents[2]

# Paper p. 501: the domestic index per country, as labelled in the workbooks.
PAPER_INDEX = {
    "Australia": "ASX ALL ORD",
    "Belgium": "BRUSSELS ALL SHARE",
    "France": "SBF 250 (BROAD FRENCH)",
    "Finland": "HELSINKI HEX",
    "Netherlands": "CBS ALLSHARE PRICE INDEX",
    "Sweden": "Stockholmborsen allshare",
    "Switzerland": "SWISS PERFORMANCE INDEX",
    "United Kingdom": "FTSE Allshare",
    "United States": "S&P 500",
}


def _data(n=12, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=n)
    return pd.DataFrame(
        {
            "r_a": rng.normal(0, 0.01, n),
            "r_b": rng.normal(0, 0.01, n),
            "fx": rng.normal(0, 0.005, n),
            "index:I1": rng.normal(0, 0.01, n),
            "index:I2": rng.normal(0, 0.01, n),
        },
        index=idx,
    )


def _design(data, **kw):
    args = {
        "index_a": "I1",
        "index_b": "I2",
        "start": str(data.index[2].date()),
        "end": str(data.index[-2].date()),
        "contemporaneous_only": False,
    }
    return comovement_design(data, **(args | kw))


def test_design_leads_lags_and_exchange_rate_sign():
    data = _data()
    f = _design(data)
    y = data["r_a"] - data["r_b"]
    t = f.index[3]
    pos = data.index.get_loc(t)
    assert f.loc[t, "y"] == y.iloc[pos]
    assert f.loc[t, "lagged_dependent"] == y.iloc[pos - 1]
    assert f.loc[t, "index_a[t+1]"] == data["index:I1"].iloc[pos + 1]
    assert f.loc[t, "index_b[t-1]"] == data["index:I2"].iloc[pos - 1]
    # e.r. is B's currency per unit of A's: the negative of the workbook column (D13)
    assert f.loc[t, "fx[t]"] == -data["fx"].iloc[pos]
    assert f.loc[t, "fx[t+1]"] == -data["fx"].iloc[pos + 1]


def test_leads_and_lags_read_the_rows_next_to_the_window():
    data = _data()
    f = _design(data)
    # every window row is an observation: the first uses the row before the
    # window for its lags, the last the row after it for its leads (D17)
    assert f.index[0] == data.index[2] and f.index[-1] == data.index[-2]
    assert f.loc[f.index[-1], "index_a[t+1]"] == data["index:I1"].iloc[-1]


def test_same_time_zone_uses_contemporaneous_index_returns_only():
    f = _design(_data(), contemporaneous_only=True)
    assert [c for c in f.columns if c.startswith("index")] == ["index_a[t]", "index_b[t]"]
    assert [c for c in f.columns if c.startswith("fx")] == ["fx[t-1]", "fx[t]", "fx[t+1]"]


def test_excluded_dates_leave_the_neighbours_lags_alone():
    data = _data()
    gone = data.index[5]
    f = _design(data, exclude_dates=[str(gone.date())])
    assert gone not in f.index
    nxt = data.index[6]
    assert f.loc[nxt, "lagged_dependent"] == (data["r_a"] - data["r_b"]).loc[gone]
    with pytest.raises(KeyError):
        _design(data, exclude_dates=["1999-01-01"])


def test_comovement_recovers_known_sums_with_unadjusted_r2():
    rng = np.random.default_rng(1)
    n = 3000
    data = _data(n, seed=2)
    i1, i2, fx = data["index:I1"], data["index:I2"], -data["fx"]
    y = np.zeros(n)
    e = rng.normal(0, 0.002, n)
    for t in range(1, n - 1):
        y[t] = (
            -0.2 * y[t - 1]
            + 0.3 * i1.iloc[t]
            + 0.1 * i1.iloc[t + 1]
            - 0.25 * i2.iloc[t - 1]
            - 0.25 * i2.iloc[t]
            - 0.6 * fx.iloc[t]
            + e[t]
        )
    data["r_a"], data["r_b"] = y, 0.0
    f = comovement_design(
        data,
        index_a="I1",
        index_b="I2",
        start=str(data.index[1].date()),
        end=str(data.index[-2].date()),
        contemporaneous_only=False,
    )
    out = comovement(f)
    assert out["sum_lagged_dependent"] == pytest.approx(-0.2, abs=0.02)
    assert out["sum_index_a"] == pytest.approx(0.4, abs=0.02)
    assert out["sum_index_b"] == pytest.approx(-0.5, abs=0.02)
    assert out["sum_fx"] == pytest.approx(-0.6, abs=0.02)
    assert out["df"] == len(f) - 9 and out["nobs"] == len(f)
    resid_share = 1 - out["r2"]
    n_, k = len(f), 9
    assert out["r2_adjusted"] == pytest.approx(1 - resid_share * (n_ - 1) / (n_ - k))
    assert out["sum_index_a.p_nw"] < 0.01 and out["sum_index_a.p_nw_auto"] < 0.01
    assert 1.8 < out["durbin_watson"] < 2.2


def test_newey_west_lag_and_significance_marks():
    assert eviews_lag(100) == 4 and eviews_lag(5936) == 9 and eviews_lag(300) == 5
    assert [significance(p) for p in (0.001, 0.02, 0.07, 0.2)] == ["a", "b", "c", ""]


def test_paper_table3_from_the_evidence():
    t = paper_table3(ROOT)
    assert len(t) == 12 and set(T3_STATS) <= set(t.columns)
    rd = t.loc["royal dutch/shell"]
    assert rd["df"] == 5927 and rd["sum_fx"] == -0.806 and rd["sum_fx.significance"] == "a"
    sk = t.loc["smithkline beecham"]
    assert sk["sum_index_a.significance"] == "c" and sk["sum_fx.significance"] == ""
    assert t.loc["fortis", "sum_fx.significance"] == "b"


def test_regression_indices_follow_the_paper_except_identified_departures():
    for twin in twins(ROOT):
        cfg = load_twin_config(twin, ROOT)
        country_a, country_b = cfg.table_i.countries.split("/")
        named = {"index_a": PAPER_INDEX[country_a], "index_b": PAPER_INDEX[country_b]}
        identified = regression_spec(cfg, "identified")
        stated = regression_spec(cfg, "as_stated")
        # rd_shell: CBS Allshare ex. Royal Dutch (D14)
        if twin != "rd_shell":
            assert {k: identified[k] for k in named} == named, twin
        # smithkline: p. 501 says Bloomberg FTSE (the FTSE 100 column) (D16)
        if twin != "smithkline":
            assert {k: stated[k] for k in named} == named, twin
        assert stated["exclude_dates"] == []
        if twin != "dexia":  # D15
            assert identified["exclude_dates"] == []
        assert {"sheet", "return_a", "return_b", "fx"} <= set(cfg.regression)
    assert regression_spec(load_twin_config("dexia", ROOT), "identified")["exclude_dates"] == [
        "1997-12-19",
        "1997-12-22",
    ]


def test_regression_panel_must_match_the_panel_returns():
    idx = pd.bdate_range("2000-01-03", periods=4)
    tr_a = pd.Series([1.0, 1.01, 0.99, 1.02], idx)
    tr_b = pd.Series([1.0, 1.02, 1.03, 1.01], idx)
    ra, rb = np.log(tr_a).diff(), np.log(tr_b).diff()
    header = [
        ["", "TOTAL RETURN A", "TOTAL RETURN A", "TOTAL RETURN B", "A/ B", "IDX1", "IDX2"],
        ["", "local currency", "foreign currency", "local currency", "log returns", "", ""],
    ]
    values = pd.DataFrame(
        {1: ra, 2: ra + 0.5, 3: rb, 4: 0.001, 5: 0.002, 6: 0.003}, index=idx
    ).fillna(0.0)
    spec = OmegaConf.create(
        {"return_a": "TOTAL RETURN A", "return_b": "TOTAL RETURN B", "fx": "A/ B"}
        | {"index_a": "IDX1", "index_b": "IDX2", "as_stated": {"index_a": "IDX2"}}
    )
    panel = pd.DataFrame({"tr_a": tr_a, "tr_b": tr_b})
    frame, report = regression_panel(Sheet("Regression data", header, values), spec, panel)
    assert list(frame.columns) == ["r_a", "r_b", "fx", "index:IDX1", "index:IDX2"]
    np.testing.assert_allclose(frame["r_a"].iloc[1:], ra.iloc[1:])  # local, not foreign
    assert report["returns_checked_against_panel"] == 6
    bad = values.copy()
    bad.loc[idx[2], 3] += 1e-6
    with pytest.raises(DatastreamFormatError, match="r_b"):
        regression_panel(Sheet("Regression data", header, bad), spec, panel)
    short = values.drop(index=idx[3])
    with pytest.raises(DatastreamFormatError, match="r_a"):
        regression_panel(Sheet("Regression data", header, short), spec, panel)
