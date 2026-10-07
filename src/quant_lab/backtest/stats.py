"""Statistics for robustness reports: probabilistic and deflated Sharpe ratios,
sub-period, regime and concentration breakdowns of a daily return series.

Sharpe ratios in the PSR/DSR formulas are per period (not annualized), as in
Bailey and Lopez de Prado (2012, 2014). [EXTERNAL-RESEARCH]
"""

import numpy as np
import pandas as pd
from scipy import stats

EULER_GAMMA = 0.5772156649015329


def sharpe(returns: pd.Series) -> float:
    """Per-period Sharpe ratio (mean / std, ddof=1)."""
    r = returns.dropna()
    std = r.std(ddof=1)
    return float(r.mean() / std) if len(r) > 1 and std > 0 else 0.0


def probabilistic_sharpe_ratio(
    sr: float, sr_benchmark: float, n: int, skew: float = 0.0, kurtosis: float = 3.0
) -> float:
    """P(true SR > sr_benchmark) given an observed per-period SR over n returns.

    ``kurtosis`` is the plain (non-excess) kurtosis: 3 for normal returns.
    """
    denom = 1 - skew * sr + (kurtosis - 1) / 4 * sr**2
    if n < 2 or denom <= 0:
        return float("nan")
    return float(stats.norm.cdf((sr - sr_benchmark) * np.sqrt(n - 1) / np.sqrt(denom)))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Expected maximum of n_trials independent SR estimates with true SR 0 and
    variance var_sr (the false-strategy theorem, Bailey et al. 2014)."""
    if n_trials < 1 or var_sr < 0:
        raise ValueError("need n_trials >= 1 and var_sr >= 0")
    if n_trials == 1:
        return 0.0
    z1 = stats.norm.ppf(1 - 1 / n_trials)
    z2 = stats.norm.ppf(1 - 1 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * ((1 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int, var_sr: float) -> dict:
    """PSR of the observed SR against the SR expected from the best of n_trials
    worthless strategies. A DSR near 1 is evidence of skill after selection."""
    r = returns.dropna()
    sr = sharpe(r)
    sr0 = expected_max_sharpe(n_trials, var_sr)
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))
    return {
        "sr_per_period": sr,
        "sr0_per_period": sr0,
        "n_trials": int(n_trials),
        "var_sr_per_period": float(var_sr),
        "n_returns": len(r),
        "skew": skew,
        "kurtosis": kurt,
        "dsr": probabilistic_sharpe_ratio(sr, sr0, len(r), skew, kurt),
        "psr_vs_zero": probabilistic_sharpe_ratio(sr, 0.0, len(r), skew, kurt),
    }


def period_metrics(returns: pd.Series, ann: int) -> dict:
    r = returns.dropna()
    total = float((1 + r).prod() - 1) if len(r) else 0.0
    return {
        "n_days": len(r),
        "total_return": total,
        "sharpe": sharpe(r) * np.sqrt(ann),
        "annual_volatility": float(r.std(ddof=1) * np.sqrt(ann)) if len(r) > 1 else 0.0,
    }


def subperiods(returns: pd.Series, breaks: list[str], ann: int) -> pd.DataFrame:
    """Metrics between consecutive break dates (each break starts a new sub-period)."""
    edges = [returns.index[0], *[pd.Timestamp(b) for b in breaks], None]
    rows = []
    for start, end in zip(edges[:-1], edges[1:], strict=True):
        part = returns.loc[start:]
        if end is not None:
            part = part.loc[: end - pd.Timedelta(days=1)]
        if len(part):
            span = {"start": part.index[0].date(), "end": part.index[-1].date()}
            rows.append({**span, **period_metrics(part, ann)})
    return pd.DataFrame(rows)


def calendar_years(returns: pd.Series, ann: int) -> pd.DataFrame:
    rows = [{"year": y, **period_metrics(r, ann)} for y, r in returns.groupby(returns.index.year)]
    return pd.DataFrame(rows)


def volatility_regimes(returns: pd.Series, relative_price: pd.Series, window: int, ann: int):
    """Split days by the pair's own volatility regime, known before each day.

    Regime of day t: trailing ``window``-day std of daily changes of the relative
    price as of close t-1, above or below its expanding median up to t-1.
    """
    vol = relative_price.diff().rolling(window).std().shift(1)
    high = vol > vol.expanding().median()
    regime = high.reindex(returns.index)
    rows = []
    for name, mask in (("low_vol", regime.eq(False)), ("high_vol", regime.eq(True))):
        rows.append({"regime": name, **period_metrics(returns[mask], ann)})
    return pd.DataFrame(rows)


def trade_concentration(returns: pd.Series, held: pd.Series) -> dict:
    """How much of the P&L comes from a few days or a few trades.

    A trade is a run of consecutive days with the same non-zero spread position.
    Shares are of the sum of absolute contributions, so they lie in [0, 1].
    """
    r = returns.reindex(held.index).fillna(0.0)
    trade_id = (held.ne(held.shift()) | held.eq(0)).cumsum().where(held.ne(0))
    per_trade = r.groupby(trade_id).sum()
    abs_days = r.abs().sort_values(ascending=False)
    abs_trades = per_trade.abs().sort_values(ascending=False)

    def share(top: pd.Series, total: pd.Series) -> float:
        return float(top.sum() / total.sum()) if total.sum() > 0 else 0.0

    return {
        "n_trades": int(len(per_trade)),
        "top10_days_share": share(abs_days.head(10), abs_days),
        "top_trade_share": share(abs_trades.head(1), abs_trades),
        "positive_trades": float((per_trade > 0).mean()) if len(per_trade) else float("nan"),
    }
