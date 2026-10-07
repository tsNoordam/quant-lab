"""SILTA price-volume regressions (Maymin, Table II / Table VI), logged to MLflow.

    uv run python -m quant_lab.models.silta data=rd_shell

For a pair, y = ln(P_a/P_b) (raw closes, common currency) and x = ln(V_a/V_b)
(shares volume). Specifications (research/methodology/maymin_silta.md):

    raw_shares       y on x
    raw_notional     y on ln(P_a V_a / (P_b V_b)) = y + x
    std              Z0[y] on Z0[x], Z0 = demean and descale
    std_detrended    Z[y] on Z[x], Z = remove a linear time trend, then descale
    causal           trailing z-scores of y and x (window = silta.causal_window)

The full-sample standardizations use the whole analysed window: they are
explanatory, as in the paper, and must never feed a trading signal. The causal
variant uses only past data and is the one a strategy may build on.

t-statistics use Newey-West (1994) as implemented in R's sandwich::NeweyWest
(Zeileis 2004): automatic Bartlett lag, AR(1) prewhitening, n/(n-k) adjustment,
with a fixed-lag sensitivity table. The analysed window is the dataset's
development range (train start .. validation end); the OOS period is never read.
"""

import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig

from quant_lab.backtest.run import BacktestGuardError, Period, check_overrides, run_params, run_tags
from quant_lab.backtest.walkforward import development_range
from quant_lab.data.preprocess import PANEL_FILE
from quant_lab.features.rolling import calculate_rolling_zscore
from quant_lab.tracking import mlflow_utils

SPECS = ("raw_shares", "raw_notional", "std", "std_detrended", "causal")


# ---------------------------------------------------------------- Newey-West


def nw_bandwidth(v: np.ndarray, weights: np.ndarray, prewhitened: bool) -> float:
    """Newey-West (1994) automatic bandwidth for the Bartlett kernel (sandwich::bwNeweyWest)."""
    n = v.shape[0]
    m = int(np.floor((3 if prewhitened else 4) * (n / 100) ** (2 / 9)))
    f = v @ weights
    sigma = np.array([f[: n - j] @ f[j:] for j in range(m + 1)]) / n
    s0 = sigma[0] + 2 * sigma[1:].sum()
    s1 = 2 * (np.arange(1, m + 1) * sigma[1:]).sum()
    if s0 <= 0:
        return 0.0
    return float(1.1447 * ((s1 / s0) ** 2) ** (1 / 3) * n ** (1 / 3))


def newey_west_cov(
    X: np.ndarray,
    resid: np.ndarray,
    *,
    lag: int | None = None,
    prewhite: bool = True,
    adjust: bool = True,
) -> tuple[np.ndarray, int]:
    """HAC covariance of OLS coefficients. Returns (cov, lag used).

    Columns of X that are constant get weight 0 in the bandwidth rule, as for an
    intercept in sandwich::bwNeweyWest.
    """
    n, k = X.shape
    u = X * resid[:, None]  # estimating functions
    if prewhite:
        u0, u1 = u[:-1], u[1:]
        B = np.linalg.lstsq(u0, u1, rcond=None)[0]  # u1 ~ u0 @ B, i.e. A = B.T
        v = u1 - u0 @ B
        D = np.linalg.inv(np.eye(k) - B.T)
    else:
        v, D = u, np.eye(k)
    if lag is None:
        weights = np.array([0.0 if np.ptp(X[:, j]) == 0 else 1.0 for j in range(k)])
        lag = int(np.floor(nw_bandwidth(v, weights, prewhite)))
    nv = v.shape[0]
    S = v.T @ v
    for j in range(1, lag + 1):
        w = 1 - j / (lag + 1)
        G = v[j:].T @ v[:-j]
        S += w * (G + G.T)
    S = D @ (S / nv) @ D.T
    bread = np.linalg.inv(X.T @ X / n)
    cov = bread @ S @ bread / n
    if adjust:
        cov *= n / (n - k)
    return cov, lag


# ---------------------------------------------------------------- regressions


@dataclass(frozen=True)
class RegressionResult:
    spec: str
    nobs: int
    alpha: float
    beta: float
    t_alpha: float
    t_beta: float
    se_beta: float
    rho: float
    r2: float
    nw_lag: int


def ols_nw(y: pd.Series, x: pd.Series, spec: str, **nw) -> RegressionResult:
    data = pd.concat({"y": y, "x": x}, axis=1).dropna()
    X = np.column_stack([np.ones(len(data)), data["x"].to_numpy()])
    yv = data["y"].to_numpy()
    coef, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ coef
    cov, lag = newey_west_cov(X, resid, **nw)
    se = np.sqrt(np.diag(cov))
    rho = float(np.corrcoef(data["x"], data["y"])[0, 1])
    return RegressionResult(
        spec=spec,
        nobs=len(data),
        alpha=float(coef[0]),
        beta=float(coef[1]),
        t_alpha=float(coef[0] / se[0]) if se[0] > 0 else 0.0,
        t_beta=float(coef[1] / se[1]),
        se_beta=float(se[1]),
        rho=rho,
        r2=rho**2,
        nw_lag=lag,
    )


def standardize(s: pd.Series, detrend: bool) -> pd.Series:
    """Full-sample Z[.]: (optionally) remove an OLS linear time trend, demean, descale.

    Uses the whole series: explanatory only, never a trading input.
    """
    s = s.dropna()
    if detrend:
        t = np.arange(len(s), dtype=float)
        slope, intercept = np.polyfit(t, s.to_numpy(), 1)
        s = s - (intercept + slope * t)
    s = s - s.mean()
    return s / s.std(ddof=1)


def relative_series(panel: pd.DataFrame) -> pd.DataFrame:
    """y = ln(P_a/P_b) on raw closes, x = ln(V_a/V_b) in shares."""
    return pd.DataFrame(
        {
            "y": np.log(panel["close_a"] / panel["close_b"]),
            "x": np.log(panel["volume_a"] / panel["volume_b"]),
        }
    )


def regressions(rel: pd.DataFrame, causal_window: int, **nw) -> list[RegressionResult]:
    y, x = rel["y"], rel["x"]
    return [
        ols_nw(y, x, "raw_shares", **nw),
        ols_nw(y, y + x, "raw_notional", **nw),
        ols_nw(standardize(y, False), standardize(x, False), "std", **nw),
        ols_nw(standardize(y, True), standardize(x, True), "std_detrended", **nw),
        ols_nw(
            calculate_rolling_zscore(y, causal_window),
            calculate_rolling_zscore(x, causal_window),
            "causal",
            **nw,
        ),
    ]


def chi_condition(rel: pd.DataFrame, parity_ratio: float, cost_bound: float) -> dict:
    """Does the leg that is expensive relative to parity also trade more (chi > 0)?

    Also returns the paper's Table VII statistics: mean and std of the log volume
    ratio (oriented so the on-average expensive leg is in the numerator) on days
    when |deviation from parity| is inside ``cost_bound``.

    chi is reported twice. In shares (the paper's proxy, exact for HSBC's 1:1
    shares) and in value traded, ln(P_a V_a / (P_b V_b)). The value version is
    the comparable one when one share of a is worth ``parity_ratio`` shares of b
    (RD/Shell: about 6.9). [IMPLEMENTATION-ASSUMPTION, A6]
    """
    dev = rel["y"] - np.log(parity_ratio)
    sign = 1.0 if dev.mean() >= 0 else -1.0  # orientation: on-average expensive leg first
    x = sign * rel["x"]
    value = sign * (rel["y"] + rel["x"])
    inside = dev.abs() < cost_bound
    return {
        "mean_deviation_from_parity": float(dev.mean()),
        "share_days_a_expensive": float((dev > 0).mean()),
        "mean_log_volume_ratio_expensive_over_cheap": float(x.mean()),
        "chi_positive": bool(x.mean() > 0),
        "mean_log_value_ratio_expensive_over_cheap": float(value.mean()),
        "chi_positive_value": bool(value.mean() > 0),
        "share_days_inside_cost_bound": float(inside.mean()),
        "mu_inside_bound": float(x[inside].mean()) if inside.any() else float("nan"),
        "sigma_inside_bound": float(x[inside].std(ddof=1)) if inside.sum() > 1 else float("nan"),
    }


def lag_sensitivity(rel: pd.DataFrame, lags: list[int]) -> pd.DataFrame:
    """t-statistic of the std_detrended slope for fixed lags (no prewhitening) and auto."""
    zy, zx = standardize(rel["y"], True), standardize(rel["x"], True)
    rows = [
        {"lag": lag, "t_beta": ols_nw(zy, zx, "std_detrended", lag=lag, prewhite=False).t_beta}
        for lag in lags
    ]
    auto = ols_nw(zy, zx, "std_detrended")
    rows.append({"lag": f"auto({auto.nw_lag}, prewhitened)", "t_beta": auto.t_beta})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- runner


def analysis_windows(cfg: DictConfig) -> list[Period]:
    """Development range plus its train and validation parts; never OOS."""
    start, end = development_range(cfg)
    s = cfg.split
    return [
        Period("development", start, end),
        Period("train", pd.Timestamp(s.train.start), pd.Timestamp(s.train.end)),
        Period("validation", pd.Timestamp(s.validation.start), pd.Timestamp(s.validation.end)),
    ]


def analyse(cfg: DictConfig, panel: pd.DataFrame) -> dict:
    if not cfg.data.get("volume_reliable", True):
        raise BacktestGuardError(f"dataset {cfg.data.name!r} has volume_reliable: false")
    windows = analysis_windows(cfg)
    panel = panel.loc[: windows[0].end]  # the OOS period is not even loaded
    rows, chi = [], {}
    for w in windows:
        rel = relative_series(panel.loc[w.start : w.end])
        for r in regressions(rel, cfg.silta.causal_window):
            rows.append({"window": w.name, **asdict(r)})
        chi[w.name] = chi_condition(rel, cfg.data.parity_ratio, cfg.silta.cost_bound)
    dev_rel = relative_series(panel.loc[windows[0].start : windows[0].end])
    return {
        "results": pd.DataFrame(rows),
        "chi": pd.DataFrame(chi).T,
        "lags": lag_sensitivity(dev_rel, list(cfg.silta.sensitivity_lags)),
        "range": windows[0],
    }


def run_silta(cfg: DictConfig, root: Path, overrides: list[str] | None = None) -> dict:
    check_overrides(overrides or [])
    git = mlflow_utils.git_state(root)
    panel_rel = f"{cfg.data.processed_dir}/{PANEL_FILE}"
    out = analyse(cfg, pd.read_parquet(root / panel_rel))
    res = out["results"]
    dev = res[res["window"] == "development"].set_index("spec")

    mlflow_utils.set_experiment(
        cfg.mlflow.tracking_uri, f"{cfg.data.name}.silta", root / cfg.mlflow.artifact_root
    )
    tags = run_tags(cfg, root, panel_rel, git, out["range"]) | {"kind": "silta_regressions"}
    metrics = {f"{spec}_{k}": float(dev.loc[spec, k]) for spec in SPECS for k in ("beta", "t_beta")}
    metrics |= {"nobs": float(dev.loc["std_detrended", "nobs"])}
    metrics |= {
        f"chi_{k}": float(v)
        for k, v in out["chi"].loc["development"].items()
        if isinstance(v, (int, float, bool, np.bool_, np.floating))
    }
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="silta-regressions") as run:
        mlflow.set_tags(tags)
        mlflow.log_params(
            {
                k: v
                for k, v in run_params(cfg).items()
                if k.split(".")[0] in ("data", "silta", "split")
            }
        )
        mlflow.log_metrics(metrics)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            res.to_csv(tmp / "regressions.csv", index=False)
            out["chi"].to_csv(tmp / "chi_condition.csv", index_label="window")
            out["lags"].to_csv(tmp / "lag_sensitivity.csv", index=False)
            mlflow.log_artifacts(str(tmp))
    return {"run_id": run.info.run_id, **out}


@hydra.main(version_base="1.3", config_path="../../../conf", config_name="config")
def main(cfg: DictConfig) -> None:
    out = run_silta(cfg, Path.cwd(), list(HydraConfig.get().overrides.task))
    cols = ["window", "spec", "nobs", "beta", "t_beta", "rho", "nw_lag"]
    print(out["results"][cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(out["chi"].to_string(float_format=lambda v: f"{v:.3f}"))
    print(out["lags"].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("run_id:", out["run_id"])


if __name__ == "__main__":
    main()
