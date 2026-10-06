import numpy as np
import pandas as pd
import pytest

from quant_lab.features.rolling import calculate_rolling_zscore


def calculate_unsafe_global_zscore(series: pd.Series) -> pd.Series:
    """ONVEILIGE z-score (hele dataset): bewust lekkend, alleen als negatieve controle."""
    return (series - series.mean()) / series.std()


@pytest.fixture
def sample_price_data():
    """Genereert 100 dagen aan testdata."""
    rng = np.random.default_rng(42)
    dates = pd.date_range(start="2026-01-01", periods=100, freq="D")
    prices = pd.Series(100 + np.cumsum(rng.standard_normal(100)), index=dates)
    return prices


def test_rolling_zscore_has_no_lookahead_leakage(sample_price_data):
    """
    Controleert dat het aanpassen van een toekomstige prijs GEEN invloed heeft
    op eerdere feature-waarden.
    """
    prices_original = sample_price_data.copy()

    # Bereken z-score op originele data
    zscore_original = calculate_rolling_zscore(prices_original, window=30)

    # Manipuleer de toekomst (dag 90) met een extreme prijsstijging
    prices_modified = prices_original.copy()
    prices_modified.iloc[90] = prices_modified.iloc[90] + 1000.0

    # Bereken z-score opnieuw
    zscore_modified = calculate_rolling_zscore(prices_modified, window=30)

    # De z-score op dag 50 MAG NIET veranderd zijn door de wijziging op dag 90
    np.testing.assert_almost_equal(
        zscore_original.iloc[50],
        zscore_modified.iloc[50],
        decimal=6,
        err_msg=(
            "Look-ahead bias gedetecteerd: historische feature veranderde "
            "door een toekomstige prijsmutatie!"
        ),
    )


def test_unsafe_global_zscore_fails_lookahead_check(sample_price_data):
    """
    Demonstreert dat de onveilige (globale) z-score WEL lekt en faalt in de test.
    """
    prices_original = sample_price_data.copy()
    prices_modified = prices_original.copy()
    prices_modified.iloc[90] = prices_modified.iloc[90] + 1000.0

    zscore_original = calculate_unsafe_global_zscore(prices_original)
    zscore_modified = calculate_unsafe_global_zscore(prices_modified)

    # Dit moet verschillen omdat de hele dataset meeweegt in mean() en std()
    assert zscore_original.iloc[50] != zscore_modified.iloc[50]
