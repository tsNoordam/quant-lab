"""SILTA regressions: Newey-West errors, standardization, slope recovery."""

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from quant_lab.models import silta


def _ar1(n: int, phi: float, rng) -> np.ndarray:
    e = rng.standard_normal(n)
    out = np.empty(n)
    out[0] = e[0]
    for i in range(1, n):
        out[i] = phi * out[i - 1] + e[i]
    return out


def _regression_data(n: int = 1500, phi: float = 0.8, beta: float = -0.3, seed: int = 1):
    rng = np.random.default_rng(seed)
    x = _ar1(n, phi, rng)
    y = 0.2 + beta * x + _ar1(n, phi, rng)
    idx = pd.bdate_range("1990-01-01", periods=n)
    return pd.Series(y, idx), pd.Series(x, idx)


@pytest.mark.parametrize("lag", [0, 5, 20])
def test_fixed_lag_hac_matches_statsmodels(lag):
    y, x = _regression_data()
    X = sm.add_constant(x.to_numpy())
    fit = sm.OLS(y.to_numpy(), X).fit()
    expected = fit.get_robustcov_results(cov_type="HAC", maxlags=lag, use_correction=True)
    cov, used = silta.newey_west_cov(X, fit.resid, lag=lag, prewhite=False)
    assert used == lag
    np.testing.assert_allclose(cov, expected.cov_params(), rtol=1e-10)


def test_automatic_lag_grows_with_autocorrelation():
    y, x = _regression_data(phi=0.0)
    white = silta.ols_nw(y, x, "w", prewhite=False).nw_lag
    y, x = _regression_data(phi=0.9)
    persistent = silta.ols_nw(y, x, "p", prewhite=False).nw_lag
    assert persistent > white


def test_hac_t_is_smaller_than_iid_t_under_autocorrelation():
    y, x = _regression_data(phi=0.9, beta=0.05)
    nw = silta.ols_nw(y, x, "nw")
    iid = sm.OLS(y.to_numpy(), sm.add_constant(x.to_numpy())).fit()
    assert abs(nw.t_beta) < abs(iid.tvalues[1])


def test_standardize_zero_mean_unit_std_and_no_trend():
    idx = pd.bdate_range("1990-01-01", periods=500)
    t = np.arange(500.0)
    s = pd.Series(3.0 + 0.01 * t + np.sin(t / 7), idx)
    for detrend in (False, True):
        z = silta.standardize(s, detrend)
        assert abs(z.mean()) < 1e-12
        assert z.std(ddof=1) == pytest.approx(1.0)
    z = silta.standardize(s, True)
    assert abs(np.polyfit(t, z.to_numpy(), 1)[0]) < 1e-12


def test_standardized_slope_equals_correlation():
    y, x = _regression_data()
    r = silta.ols_nw(silta.standardize(y, False), silta.standardize(x, False), "std")
    assert r.beta == pytest.approx(r.rho)
    assert r.alpha == pytest.approx(0.0, abs=1e-12)


def test_planted_slope_is_recovered_and_significant():
    y, x = _regression_data(n=3000, beta=-0.3)
    r = silta.ols_nw(y, x, "raw")
    assert r.beta == pytest.approx(-0.3, abs=0.05)
    assert r.t_beta < -3


def test_leg_orientation_leaves_standardized_slope_unchanged():
    """Swapping legs flips both y and x, so the slope and its t-stat are unchanged."""
    y, x = _regression_data()
    a = silta.ols_nw(silta.standardize(y, True), silta.standardize(x, True), "ab")
    b = silta.ols_nw(silta.standardize(-y, True), silta.standardize(-x, True), "ba")
    assert a.beta == pytest.approx(b.beta)
    assert a.t_beta == pytest.approx(b.t_beta)


def test_relative_series_and_notional_spec():
    idx = pd.bdate_range("1990-01-01", periods=3)
    panel = pd.DataFrame(
        {
            "close_a": [30.0, 31.0, 29.0],
            "close_b": [20.0, 20.0, 20.0],
            "volume_a": [100.0, 200.0, 50.0],
            "volume_b": [100.0, 100.0, 100.0],
        },
        idx,
    )
    rel = silta.relative_series(panel)
    np.testing.assert_allclose(rel["y"], np.log([1.5, 1.55, 1.45]))
    np.testing.assert_allclose(rel["x"], np.log([1.0, 2.0, 0.5]))


def test_chi_condition_orientation_and_bound():
    idx = pd.bdate_range("1990-01-01", periods=4)
    # leg a above parity on average and trading more: chi > 0
    rel = pd.DataFrame(
        {"y": np.log(1.5) + np.array([0.01, 0.03, 0.005, -0.01]), "x": [0.2, 0.4, 0.1, -0.1]},
        idx,
    )
    out = silta.chi_condition(rel, parity_ratio=1.5, cost_bound=0.018)
    assert out["chi_positive"]
    assert out["share_days_inside_cost_bound"] == pytest.approx(0.75)
    assert out["mu_inside_bound"] == pytest.approx((0.2 + 0.1 - 0.1) / 3)
    assert out["mean_log_value_ratio_expensive_over_cheap"] == pytest.approx(
        (rel["y"] + rel["x"]).mean()
    )
    # the same pair with legs swapped gives the same oriented answers
    swapped = silta.chi_condition(-rel, parity_ratio=1 / 1.5, cost_bound=0.018)
    for key in (
        "mean_log_volume_ratio_expensive_over_cheap",
        "mean_log_value_ratio_expensive_over_cheap",
    ):
        assert swapped[key] == pytest.approx(out[key])


def test_value_chi_corrects_for_share_size():
    """Leg a's share is worth 7 of b's: fewer a shares can still be more value traded."""
    idx = pd.bdate_range("1990-01-01", periods=3)
    rel = pd.DataFrame({"y": np.log(7.0 * 1.05) * np.ones(3), "x": np.log(0.5) * np.ones(3)}, idx)
    out = silta.chi_condition(rel, parity_ratio=7.0, cost_bound=0.018)
    assert not out["chi_positive"] and out["chi_positive_value"]
