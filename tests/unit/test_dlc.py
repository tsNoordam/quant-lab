"""Paper-convention DLC panels (de Jong et al. 2009) and the Table II statistics."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.data.datastream import TEXT_DATE_US, DatastreamFormatError, Sheet
from quant_lab.data.dlc import assemble, total_return_index, twins
from quant_lab.models.dejong import deviation_stats, normalize_name, paper_table2

ROOT = Path(__file__).resolve().parents[2]
IDX = pd.bdate_range("1990-01-01", periods=6)


def _inputs(ratio=1.5, fx=2.0):
    pa = pd.Series([30.0, 31, 32, 33, 34, 35], IDX)  # leg A in A's currency
    pb = pd.Series([10.0, 10, 10.5, 11, 11, 12], IDX)
    fxs = pd.Series(fx, IDX)
    dev = np.log(pa / fxs / pb) - np.log(ratio)
    tr = pd.Series([100.0, 101, 102, 103, 104, 105], IDX)
    return pa, pb, tr, tr * 2, pd.Series(ratio, IDX), dev, fxs


def test_panel_reproduces_the_workbook_deviation_and_rebases_total_returns():
    pa, pb, tra, trb, ratio, dev, fx = _inputs()
    panel, report = assemble(
        pa, pb, tra, trb, ratio, dev, fx=fx, start="1990-01-01", end="1990-01-08"
    )
    np.testing.assert_allclose(panel["deviation"], dev, atol=1e-15)
    np.testing.assert_allclose(panel["close_a"], pa / 2.0)
    assert panel["tr_a"].iloc[0] == 1.0 and panel["tr_b"].iloc[0] == 1.0
    assert report["rows"] == 6 and report["ratio_constant"]


def test_a_wrong_scale_or_ratio_is_refused():
    pa, pb, tra, trb, ratio, dev, fx = _inputs()
    with pytest.raises(DatastreamFormatError, match="does not reproduce"):
        assemble(pa * 100, pb, tra, trb, ratio, dev, fx=fx, start="1990-01-01", end="1990-01-08")
    with pytest.raises(DatastreamFormatError, match="does not reproduce"):
        assemble(pa, pb, tra, trb, ratio * 1.01, dev, fx=fx, start="1990-01-01", end="1990-01-08")


def test_window_must_lie_inside_the_workbook():
    pa, pb, tra, trb, ratio, dev, fx = _inputs()
    with pytest.raises(DatastreamFormatError, match="not inside"):
        assemble(pa, pb, tra, trb, ratio, dev, fx=fx, start="1989-01-01", end="1990-01-08")


def test_total_return_from_log_returns():
    r = pd.Series([np.nan, 0.1, -0.1, 0.0], IDX[:4])
    np.testing.assert_allclose(total_return_index(r, "log_return"), [1.0, np.exp(0.1), 1.0, 1.0])
    with pytest.raises(ValueError):
        total_return_index(r, "levels")


def test_bloomberg_us_text_dates_and_column_exclusion():
    assert TEXT_DATE_US.match("6/21/1989") and TEXT_DATE_US.match("12/26/2000")
    assert not TEXT_DATE_US.match("21/06/89")
    header = [
        ["", "LOG DEVIATIONS FROM PARITY", "LOG DEVIATIONS FROM PARITY"],
        ["", "", "absolute value"],
    ]
    sheet = Sheet("Ratio", header, pd.DataFrame({1: [0.1], 2: [0.1]}))
    with pytest.raises(DatastreamFormatError, match="2 columns"):
        sheet.column("LOG DEVIATIONS FROM PARITY")
    assert sheet.column("LOG DEVIATIONS FROM PARITY", exclude="absolute value").name


def test_deviation_stats_in_percent():
    d = pd.Series([-0.02, 0.01, 0.04, 0.0])
    s = deviation_stats(d)
    assert s["mean"] == pytest.approx(0.75)
    assert s["mean_abs"] == pytest.approx(1.75)
    assert s["min"] == pytest.approx(-2.0) and s["max"] == pytest.approx(4.0)
    assert s["pct_positive"] == pytest.approx(50.0)


def test_every_twin_config_matches_the_paper_and_table_i():
    names = twins(ROOT)
    assert len(names) == 12
    paper = {normalize_name(name) for name in paper_table2(ROOT).index}
    for twin in names:
        cfg = OmegaConf.load(ROOT / "conf" / "dlc" / f"{twin}.yaml")
        assert cfg.name == twin and normalize_name(cfg.paper_name) in paper
        assert cfg.interim_path == f"data/interim/dlc/{twin}.parquet"
        # Table II window lies inside the DLC's life (Table I)
        assert (
            pd.Timestamp(cfg.window.start)
            < pd.Timestamp(cfg.window.end)
            <= pd.Timestamp("2002-10-03")
        )
        if cfg.table_i.unification_announced:
            assert pd.Timestamp(cfg.window.end) < pd.Timestamp(cfg.table_i.unification_announced)
        for leg in ("a", "b"):
            assert {"sheet", "price", "total_return"} <= set(cfg.source.legs[leg])
