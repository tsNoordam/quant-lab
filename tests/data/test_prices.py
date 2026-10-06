import numpy as np
import pandas as pd
import pytest

from quant_lab.data.validation import DataValidationError, check_ohlcv, raise_on_errors

DATES = pd.bdate_range("2020-01-01", periods=20)


def issues(df):
    return check_ohlcv(df, "X", max_abs_log_return=0.25)


def checks(df):
    return {i.check for i in issues(df)}


@pytest.mark.parametrize("col", ["open", "high", "low", "close", "adj_close"])
def test_non_positive_prices_are_errors(ohlcv, col):
    df = ohlcv(DATES)
    df.loc[DATES[3], col] = 0.0
    assert "non_positive_price" in checks(df)


def test_missing_values_are_errors(ohlcv):
    df = ohlcv(DATES)
    df.loc[DATES[7], "close"] = np.nan
    assert "missing_values" in checks(df)


def test_high_below_close_is_an_error(ohlcv):
    df = ohlcv(DATES)
    df.loc[DATES[2], "high"] = df.loc[DATES[2], "close"] * 0.9
    assert "high_inconsistent" in checks(df)


def test_low_above_open_is_an_error(ohlcv):
    df = ohlcv(DATES)
    df.loc[DATES[2], "low"] = df.loc[DATES[2], "open"] * 1.1
    assert "low_inconsistent" in checks(df)


def test_negative_volume_is_an_error(ohlcv):
    df = ohlcv(DATES)
    df.loc[DATES[4], "volume"] = -1
    assert "negative_volume" in checks(df)


def test_extreme_return_is_only_a_warning(ohlcv):
    closes = np.full(len(DATES), 100.0)
    closes[10:] = 50.0  # looks like an unadjusted 2:1 split
    found = issues(ohlcv(DATES, closes))
    assert [(i.check, i.severity) for i in found] == [("extreme_return", "warning")]
    raise_on_errors(found)  # warnings never stop the pipeline


def test_raise_on_errors_lists_every_error(ohlcv):
    df = ohlcv(DATES)
    df.loc[DATES[1], "close"] = -5.0
    df.loc[DATES[2], "volume"] = -1
    with pytest.raises(DataValidationError) as exc:
        raise_on_errors(issues(df))
    assert {i.check for i in exc.value.issues} >= {"non_positive_price", "negative_volume"}
