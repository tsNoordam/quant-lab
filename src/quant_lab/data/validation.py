"""Deterministic data validation. No heuristics from an LLM: every check is code.

Errors stop the pipeline. Warnings are recorded in the stage's validation report
(DVC metrics) so they are visible in ``git diff`` and ``dvc metrics diff``.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Severity = Literal["error", "warning"]
PRICE_COLUMNS = ("open", "high", "low", "close", "adj_close")


@dataclass(frozen=True)
class Issue:
    check: str
    severity: Severity
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity}:{self.check}] {self.detail}"


class DataValidationError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__("\n".join(str(i) for i in issues))


def _dates(index: pd.Index, limit: int = 5) -> str:
    shown = [str(pd.Timestamp(d).date()) for d in index[:limit]]
    more = f" (+{len(index) - limit} more)" if len(index) > limit else ""
    return ", ".join(shown) + more


def check_ohlcv(df: pd.DataFrame, name: str, *, max_abs_log_return: float) -> list[Issue]:
    """Validate one symbol's daily OHLCV frame as loaded (unsorted, unfilled)."""
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        return [Issue("index_type", "error", f"{name}: index is {type(idx).__name__}")]

    issues: list[Issue] = []
    if idx.tz is not None:
        issues.append(Issue("timezone", "error", f"{name}: daily data must use naive local dates"))
    if idx.has_duplicates:
        dupes = idx[idx.duplicated()]
        issues.append(Issue("duplicate_dates", "error", f"{name}: {_dates(dupes)}"))
    if not idx.is_monotonic_increasing:
        issues.append(Issue("unsorted_dates", "error", f"{name}: dates are not increasing"))
    intraday = idx[idx != idx.normalize()]
    if len(intraday):
        issues.append(Issue("intraday_timestamps", "error", f"{name}: {_dates(intraday)}"))

    for col in (*PRICE_COLUMNS, "volume"):
        nan_dates = idx[df[col].isna().to_numpy()]
        if len(nan_dates):
            issues.append(Issue("missing_values", "error", f"{name}.{col}: {_dates(nan_dates)}"))
    for col in PRICE_COLUMNS:
        bad = idx[(df[col] <= 0).to_numpy()]
        if len(bad):
            issues.append(Issue("non_positive_price", "error", f"{name}.{col}: {_dates(bad)}"))

    high_floor = df[["open", "close", "low"]].max(axis=1)
    bad_high = idx[(df["high"] < high_floor).to_numpy()]
    if len(bad_high):
        issues.append(Issue("high_inconsistent", "error", f"{name}: {_dates(bad_high)}"))
    low_cap = df[["open", "close", "high"]].min(axis=1)
    bad_low = idx[(df["low"] > low_cap).to_numpy()]
    if len(bad_low):
        issues.append(Issue("low_inconsistent", "error", f"{name}: {_dates(bad_low)}"))
    neg_volume = idx[(df["volume"] < 0).to_numpy()]
    if len(neg_volume):
        issues.append(Issue("negative_volume", "error", f"{name}: {_dates(neg_volume)}"))

    if idx.is_monotonic_increasing and not idx.has_duplicates:
        with np.errstate(divide="ignore", invalid="ignore"):
            log_ret = np.log(df["adj_close"]).diff().abs()
        jumps = idx[(log_ret > max_abs_log_return).to_numpy()]
        if len(jumps):
            issues.append(
                Issue(
                    "extreme_return",
                    "warning",
                    f"{name}: |log return| > {max_abs_log_return} on {_dates(jumps)}",
                )
            )
    return issues


def coverage(index: pd.DatetimeIndex, reference: pd.DatetimeIndex) -> float:
    """Fraction of reference dates missing from ``index``."""
    if len(reference) == 0:
        return 0.0
    return float(1.0 - len(index.intersection(reference)) / len(reference))


def check_pair_coverage(
    index_a: pd.DatetimeIndex, index_b: pd.DatetimeIndex, *, max_missing_frac: float
) -> list[Issue]:
    """Each leg may miss at most ``max_missing_frac`` of the dates on which either traded."""
    reference = index_a.union(index_b)
    issues = []
    for name, index in (("a", index_a), ("b", index_b)):
        frac = coverage(index, reference)
        if frac > max_missing_frac:
            issues.append(
                Issue(
                    "missing_dates",
                    "error",
                    f"leg {name} misses {frac:.2%} of dates (limit {max_missing_frac:.2%})",
                )
            )
    return issues


def raise_on_errors(issues: list[Issue]) -> None:
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise DataValidationError(errors)
