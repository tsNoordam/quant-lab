import pandas as pd


def calculate_rolling_zscore(series: pd.Series, window: int = 60) -> pd.Series:
    """Veilige z-score berekening met een rolling venster (geen look-ahead bias)."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    return (series - rolling_mean) / rolling_std
