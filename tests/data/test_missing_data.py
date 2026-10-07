import pandas as pd
import pytest

from quant_lab.data.synchronization import align_pair
from quant_lab.data.validation import check_pair_coverage

DATES = pd.bdate_range("2020-01-01", periods=30)


def test_coverage_within_limit_passes():
    assert check_pair_coverage(DATES, DATES.delete([3]), max_missing_frac=0.05) == []


def test_coverage_above_limit_fails():
    found = check_pair_coverage(DATES, DATES.delete([1, 2, 3]), max_missing_frac=0.05)
    assert [(i.check, i.severity) for i in found] == [("missing_dates", "error")]
    assert "leg b" in found[0].detail


def test_drop_policy_keeps_only_common_dates(ohlcv):
    a, b = ohlcv(DATES), ohlcv(DATES.delete([5, 6]), seed=1)
    panel = align_pair(a, b, missing_policy="drop")
    assert panel.index.equals(DATES.delete([5, 6]))
    assert not panel[["stale_a", "stale_b"]].any().any()


def test_ffill_creates_flagged_no_trade_bars(ohlcv):
    a, b = ohlcv(DATES), ohlcv(DATES.delete([5]), seed=1)
    panel = align_pair(a, b, missing_policy="ffill", ffill_limit=2)
    row = panel.loc[DATES[5]]
    last_close = b.loc[DATES[4], "close"]
    assert row["stale_b"] and not row["stale_a"]
    assert row["close_b"] == row["open_b"] == row["high_b"] == row["low_b"] == last_close
    assert row["volume_b"] == 0
    assert panel.index.equals(DATES)


def test_ffill_respects_limit(ohlcv):
    a, b = ohlcv(DATES), ohlcv(DATES.delete([10, 11, 12]), seed=1)
    panel = align_pair(a, b, missing_policy="ffill", ffill_limit=2)
    assert DATES[10] in panel.index and DATES[11] in panel.index
    assert DATES[12] not in panel.index


def test_leg_that_starts_later_is_never_backfilled(ohlcv):
    a, b = ohlcv(DATES), ohlcv(DATES[5:], seed=1)
    panel = align_pair(a, b, missing_policy="ffill", ffill_limit=5)
    assert panel.index[0] == DATES[5]


def test_invalid_policy_settings_raise(ohlcv):
    a = ohlcv(DATES)
    with pytest.raises(ValueError, match="ffill_limit"):
        align_pair(a, a, missing_policy="ffill", ffill_limit=0)
    with pytest.raises(ValueError, match="unknown"):
        align_pair(a, a, missing_policy="interpolate")
