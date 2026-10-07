"""Alignment must be causal: changing or removing a future bar never alters past rows.

The perturbation is repeated for every possible cutoff date, so any gap in
either leg sits right before a perturbed bar at some cutoff. A backward fill or
interpolation anywhere therefore changes a pre-cutoff row and fails the test.
"""

import pandas as pd
import pytest

from quant_lab.data.synchronization import align_pair

DATES = pd.bdate_range("2020-01-01", periods=40)
PRICES = ["open", "high", "low", "close", "adj_close"]


def perturb_after(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    out = df.copy()
    future = out.index > cutoff
    out.loc[future, PRICES] *= 3.0
    out.loc[future, "volume"] += 1_000_000
    return out.drop(out.index[future][::2])  # and remove some future bars entirely


@pytest.mark.parametrize(("policy", "limit"), [("drop", 0), ("ffill", 1), ("ffill", 3)])
def test_future_perturbation_does_not_change_the_past(ohlcv, policy, limit):
    a = ohlcv(DATES.delete([10, 20, 21]))
    b = ohlcv(DATES.delete([15, 30, 31, 32]), seed=1)
    base = align_pair(a, b, missing_policy=policy, ffill_limit=limit)

    for cutoff in DATES[:-1]:
        for leg in ("a", "b"):
            pa = perturb_after(a, cutoff) if leg == "a" else a
            pb = perturb_after(b, cutoff) if leg == "b" else b
            perturbed = align_pair(pa, pb, missing_policy=policy, ffill_limit=limit)
            pd.testing.assert_frame_equal(
                base.loc[:cutoff], perturbed.loc[:cutoff], obj=f"rows <= {cutoff.date()}"
            )
