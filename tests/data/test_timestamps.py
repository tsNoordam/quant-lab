import pandas as pd

from quant_lab.data.validation import check_ohlcv

LIMIT = 0.25


def checks(df):
    return {i.check for i in check_ohlcv(df, "X", max_abs_log_return=LIMIT)}


def test_clean_frame_passes(ohlcv):
    assert checks(ohlcv(pd.bdate_range("2020-01-01", periods=50))) == set()


def test_duplicate_dates_are_errors(ohlcv):
    dates = pd.bdate_range("2020-01-01", periods=10)
    df = ohlcv(dates.insert(5, dates[4]))
    assert "duplicate_dates" in checks(df)


def test_unsorted_dates_are_errors(ohlcv):
    df = ohlcv(pd.bdate_range("2020-01-01", periods=10)[::-1])
    assert "unsorted_dates" in checks(df)


def test_timezone_aware_daily_index_is_an_error(ohlcv):
    df = ohlcv(pd.bdate_range("2020-01-01", periods=10, tz="UTC"))
    assert "timezone" in checks(df)


def test_intraday_timestamps_in_daily_data_are_errors(ohlcv):
    dates = pd.bdate_range("2020-01-01", periods=10) + pd.Timedelta(hours=16)
    assert "intraday_timestamps" in checks(ohlcv(dates))


def test_non_datetime_index_is_an_error(ohlcv):
    df = ohlcv(pd.bdate_range("2020-01-01", periods=5)).reset_index(drop=True)
    assert checks(df) == {"index_type"}
