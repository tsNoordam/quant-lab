"""Unit tests for the Datastream workbook repairs (no real data needed)."""

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant_lab.data.datastream import DatastreamFormatError, Sheet, build_leg, repair_dates
from quant_lab.data.validation import check_ohlcv

D = dt.date


def test_dates_already_in_order_are_left_alone():
    entries = [("cell", D(2001, 1, 2)), ("cell", D(2001, 1, 3)), ("text", D(2001, 1, 15))]
    assert repair_dates(entries) == [D(2001, 1, 2), D(2001, 1, 3), D(2001, 1, 15)]


def test_day_month_swapped_cells_are_repaired():
    # Datastream wrote 11/01/01, 12/01/01 (dd/mm/yy); Excel stored them as 1 Nov and 1 Dec.
    entries = [
        ("cell", D(2001, 11, 1)),
        ("cell", D(2001, 12, 1)),
        ("text", D(2001, 1, 15)),
        ("text", D(2001, 1, 16)),
        ("cell", D(2001, 2, 2)),  # really 2 Feb: day == month, unchanged by the swap
    ]
    assert repair_dates(entries) == [
        D(2001, 1, 11),
        D(2001, 1, 12),
        D(2001, 1, 15),
        D(2001, 1, 16),
        D(2001, 2, 2),
    ]


def test_unrepairable_dates_raise():
    entries = [("text", D(2001, 1, 15)), ("text", D(2001, 1, 12))]
    with pytest.raises(DatastreamFormatError, match="increasing"):
        repair_dates(entries)


def test_weekend_dates_raise():
    with pytest.raises(DatastreamFormatError, match="weekend"):
        repair_dates([("text", D(2001, 1, 12)), ("text", D(2001, 1, 13))])


def make_sheet():
    header = [
        ["", "123(P)", "123(RI)", "LOG DEVIATIONS FROM PARITY", "LOG DEVIATIONS FROM PARITY"],
        ["", "", "", "", "absolute value"],
    ]
    data = pd.DataFrame(np.ones((2, 4)), columns=[1, 2, 3, 4])
    return Sheet("S", header, data)


def test_columns_are_found_by_exact_label():
    assert make_sheet().column("123(RI)").name == "123(RI)"


def test_ambiguous_or_missing_labels_raise():
    sheet = make_sheet()
    with pytest.raises(DatastreamFormatError, match="matches 2 columns"):
        sheet.column("LOG DEVIATIONS FROM PARITY")
    with pytest.raises(DatastreamFormatError, match="matches 0 columns"):
        sheet.column("123(NOSH)")


DATES = pd.bdate_range("2001-01-01", periods=6)


def series(values):
    return pd.Series(values, index=DATES, dtype=float)


def test_build_leg_converts_units_and_drops_padded_holidays():
    df, report = build_leg(
        price=series([200, 202, 202, 204, 206, 208]),  # pence
        total_return_index=series([100, 101, 101, 102, 103, 104]),
        volume=series([5, 6, np.nan, 7, 0, 8]),  # thousands; NaN and 0 = no trading
        bid=series([199, 201, 201, 203, 205, 207]),
        ask=series([201, 203, 203, 205, 207, 209]),
        price_scale=0.01,
        quote_scale=0.01,
        volume_multiplier=1000,
    )
    assert list(df.index) == list(DATES[[0, 1, 3, 5]])
    assert report["no_volume_rows_dropped"] == 2
    np.testing.assert_allclose(df["close"], [2.00, 2.02, 2.04, 2.08])
    np.testing.assert_allclose(df["volume"], [5000, 6000, 7000, 8000])
    np.testing.assert_allclose(df["bid"], [1.99, 2.01, 2.03, 2.07])


def test_build_leg_divides_by_fx_per_unit():
    df, _ = build_leg(
        price=series([22.0] * 6),  # EUR
        total_return_index=series([1.0] * 6),
        volume=series([1.0] * 6),
        fx_per_unit=series([1.1, 1.1, 1.2, 1.2, 1.25, 1.25]),  # EUR per GBP
    )
    np.testing.assert_allclose(df["close"], [20, 20, 22 / 1.2, 22 / 1.2, 17.6, 17.6])


def test_adj_close_adds_dividends_without_looking_ahead():
    # Price flat; total return index jumps 2% on day 3 (a dividend).
    price = series([10.0] * 6)
    ri = series([100, 100, 102, 102, 102, 102])
    df, _ = build_leg(price, ri, series([1.0] * 6))
    np.testing.assert_allclose(df["adj_close"], [10, 10, 10.2, 10.2, 10.2, 10.2])
    # Anchored on the first day: truncating the future leaves the past unchanged.
    early, _ = build_leg(price[:3], ri[:3], series([1.0] * 6)[:3])
    pd.testing.assert_series_equal(early["adj_close"], df["adj_close"][:3])


def test_window_is_applied_before_anything_else():
    df, report = build_leg(
        series([1.0] * 6),
        series([1.0] * 6),
        series([1.0] * 6),
        start="2001-01-03",
        end="2001-01-05",
    )
    assert report["window_rows"] == 3 and len(df) == 3


def test_missing_price_on_a_traded_day_raises():
    with pytest.raises(DatastreamFormatError, match="missing on traded days"):
        build_leg(series([1, np.nan, 1, 1, 1, 1]), series([1.0] * 6), series([1.0] * 6))


def test_quotes_in_the_wrong_unit_are_rejected():
    df, _ = build_leg(
        price=series([5.0] * 6),  # already GBP
        total_return_index=series([1.0] * 6),
        volume=series([1.0] * 6),
        bid=series([499.0] * 6),  # still pence: forgot quote_scale
        ask=series([501.0] * 6),
    )
    checks = {i.check: i.severity for i in check_ohlcv(df, "X", max_abs_log_return=0.25)}
    assert checks.get("quote_units") == "error"


def test_locked_quotes_are_reported():
    df, _ = build_leg(
        price=series([5.0] * 6),
        total_return_index=series([1.0] * 6),
        volume=series([1.0] * 6),
        bid=series([5.0, 5.0, 4.99, 4.99, 4.99, 4.99]),
        ask=series([5.0, 5.0, 5.01, 5.01, 5.01, 5.01]),
    )
    checks = {i.check: i.severity for i in check_ohlcv(df, "X", max_abs_log_return=0.25)}
    assert checks.get("locked_quotes") == "warning"


def test_a_quarter_of_wide_quotes_is_reported_even_if_the_full_sample_median_is_fine():
    dates = pd.bdate_range("2001-01-01", "2001-12-31")
    wide = (dates >= "2001-04-01") & (dates < "2001-07-01")
    half = np.where(wide, 0.01, 0.0005)  # 200 bps vs 10 bps full spread
    df = pd.DataFrame(
        {
            "close": 5.0,
            "adj_close": 5.0,
            "volume": 1.0,
            "bid": 5.0 * (1 - half),
            "ask": 5.0 * (1 + half),
        },
        index=dates,
    )
    issues = check_ohlcv(df, "X", max_abs_log_return=0.25)
    found = {i.check: i for i in issues}
    assert "wide_quotes" not in found  # full-sample median is narrow
    assert found["wide_quote_regime"].severity == "warning"
    assert "1 quarter(s) ending 2001-06-30" in found["wide_quote_regime"].detail


def test_close_only_frames_validate_without_bars():
    df, _ = build_leg(series([5.0] * 6), series([1.0] * 6), series([1.0] * 6))
    assert check_ohlcv(df, "X", max_abs_log_return=0.25) == []


def leg_with_turnover(volume_thousands):
    return build_leg(
        series([5.0] * 6),
        series([1.0] * 6),
        series([volume_thousands] * 6),
        shares_outstanding=series([1_000_000.0] * 6),  # thousands, like Datastream NOSH
        volume_multiplier=1000,
    )[0]


def test_shares_outstanding_uses_the_volume_unit():
    df = leg_with_turnover(3_000.0)
    assert df["shares_outstanding"].iloc[0] == 1e9
    assert df["volume"].iloc[0] == 3e6  # 0.3% daily turnover


@pytest.mark.parametrize(
    ("volume", "minimum", "expect_error"),
    [(3_000.0, 0.0002, False), (5.0, 0.0002, True), (5.0, 0.0, False), (5.0, None, False)],
)
def test_implausible_turnover_check(volume, minimum, expect_error):
    issues = check_ohlcv(
        leg_with_turnover(volume), "X", max_abs_log_return=0.25, min_median_turnover=minimum
    )
    assert ("implausible_turnover" in {i.check for i in issues}) == expect_error
