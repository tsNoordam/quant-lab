"""The causal SILTA standardization uses only past data; the full-sample one does not.

The full-sample Z[.] (as in the paper) is explanatory only. This test pins down
that difference so a strategy cannot silently build on the wrong one.
"""

import numpy as np
import pandas as pd
import pytest

from quant_lab.features.rolling import calculate_rolling_zscore
from quant_lab.models import silta

WINDOW = 60


def _series(n: int = 600, seed: int = 3) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(np.cumsum(rng.standard_normal(n)), pd.bdate_range("1990-01-01", periods=n))


def test_causal_zscore_ignores_the_future():
    s = _series()
    cut = s.index[400]
    shocked = s.copy()
    shocked[shocked.index > cut] += 50.0
    before = calculate_rolling_zscore(s, WINDOW).loc[:cut]
    pd.testing.assert_series_equal(before, calculate_rolling_zscore(shocked, WINDOW).loc[:cut])
    # mutation check: the shock does reach the causal z-score after the cut
    after = s.index > cut
    assert not np.allclose(
        calculate_rolling_zscore(s, WINDOW)[after], calculate_rolling_zscore(shocked, WINDOW)[after]
    )


def test_full_sample_standardization_looks_ahead():
    s = _series()
    cut = s.index[400]
    shocked = s.copy()
    shocked[shocked.index > cut] += 50.0
    for detrend in (False, True):
        before = silta.standardize(s, detrend).loc[:cut]
        assert not np.allclose(before, silta.standardize(shocked, detrend).loc[:cut])


def test_causal_spec_regressors_are_trailing():
    """Every value fed to the causal regression is computable from data up to that date."""
    rel = pd.DataFrame({"y": _series(seed=4), "x": _series(seed=5)})
    full = calculate_rolling_zscore(rel["x"], WINDOW)
    for i in (WINDOW + 5, 250, 599):
        prefix = rel["x"].iloc[: i + 1]
        assert calculate_rolling_zscore(prefix, WINDOW).iloc[-1] == pytest.approx(full.iloc[i])
