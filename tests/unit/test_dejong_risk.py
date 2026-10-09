"""Table VI (de Jong et al. 2009): factor loader, pooling and risk statistics."""

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.backtest.dejong import evidence_label, load_config
from quant_lab.data.french import load_factors
from quant_lab.models.dejong_risk import (
    paper_sensitivities,
    paper_table6,
    pooled_frame,
    risk_statistics,
)

ROOT = Path(__file__).resolve().parents[2]
T6 = OmegaConf.create({"month_days": 22, "volatility_scale": 22})


def _french_zip(path: Path, header: str = ",Mkt-RF,SMB,HML,RF") -> Path:
    text = "\n".join(
        [
            "This file was created by CMPT_ME_BEME_RETS_DAILY",
            "",
            header,
            "19900102,    1.50,   -0.25,    0.10,    0.03",
            "19900103,   -0.50,    0.20,   -0.05,    0.03",
            "",
            "Copyright 2026 Kenneth R. French",
        ]
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("F-F_Research_Data_Factors_daily.CSV", text)
    return path


def test_french_daily_factors(tmp_path):
    f = load_factors(_french_zip(tmp_path / "ff.zip"))
    assert list(f.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert f.loc["1990-01-02", "SMB"] == pytest.approx(-0.0025)
    assert len(f) == 2
    with pytest.raises(ValueError, match="unexpected columns"):
        load_factors(_french_zip(tmp_path / "bad.zip", ",Mkt-RF,SMB,HML,RF,X"))


def test_pooling_keeps_every_position_day():
    dates = pd.to_datetime(["1990-01-01", "1990-01-02", "1990-01-03"])  # Jan 1: US holiday
    days = pd.DataFrame({"date": dates.repeat(2), "return": [0.01, 0.02, 0.0, -0.01, 0.005, 0.0]})
    market = pd.Series([0.0, 0.015, -0.005], index=dates)
    factors = pd.DataFrame({"SMB": [-0.0025, 0.002], "HML": [0.001, -0.0005]}, index=dates[1:])
    tbill = pd.Series([0.078], index=pd.to_datetime(["1989-12-29"]))
    p = pooled_frame(days, market, factors, tbill, 260)
    assert len(p) == 6  # the holiday rows stay
    holiday = p[p["date"] == dates[0]]
    assert (holiday["smb"] == 0).all() and (holiday["hml"] == 0).all()
    rf = 100 * 0.078 / 260
    assert p["excess"].iloc[0] == pytest.approx(1.0 - rf)  # % per day, T-bill as of the day
    assert p.loc[p["date"] == dates[1], "market"].iloc[0] == pytest.approx(1.5 - rf)


def test_risk_statistics_units():
    rng = np.random.default_rng(3)
    n = 20_000
    market = rng.normal(0, 1, n)
    pooled = pd.DataFrame(
        {
            "date": pd.bdate_range("1990-01-01", periods=n),
            "market": market,
            "smb": rng.normal(0, 0.5, n),
            "hml": rng.normal(0, 0.5, n),
        }
    )
    pooled["excess"] = 0.03 + 0.2 * market + rng.normal(0, 1.5, n)
    s = risk_statistics(pooled, 10, T6)
    assert s["alpha"] == pytest.approx(0.03 * 22, abs=0.5)  # daily alpha x 22 = % per month
    assert s["alpha_annualized"] == pytest.approx(12 * s["alpha"])
    assert s["beta_market"] == pytest.approx(0.2, abs=0.03)
    assert s["sigma"] == pytest.approx(pooled["excess"].std() * 22)
    assert s["sigma_sp500"] == pytest.approx(pooled["market"].std() * 22)
    assert s["var_1pct"] == pytest.approx(np.quantile(pooled["excess"], 0.01))
    assert s["kurtosis"] == pytest.approx(3.0, abs=0.2)  # raw (Pearson) kurtosis
    assert (s["investments"], s["position_days"]) == (10, n)


def test_paper_table6_and_sensitivities_from_the_evidence():
    t6 = paper_table6(ROOT)
    cfg = load_config(ROOT)
    assert {evidence_label(s) for s in cfg.strategies} == set(t6)
    bench = t6[evidence_label("10/5/12m")]
    assert (bench["alpha"], bench["significance"], bench["position_days"]) == (0.718, "a", 10422)
    assert t6[evidence_label("5/1/12m")]["significance"] == "b"
    sens = paper_sensitivities(ROOT)
    assert {c.paper_item for c in cfg.table6.sensitivities.values()} <= set(sens)
    assert sens["one extra trading day delay"] == 0.382
