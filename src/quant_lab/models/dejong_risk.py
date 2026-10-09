"""de Jong, Rosenthal & van Dijk (2009) Table VI: abnormal returns and risk of
the arbitrage strategies (ROADMAP step 17).

    uv run python -m quant_lab.models.dejong_risk

The daily returns of every position (quant_lab.backtest.dejong, including the
T-bill days that pad positions shorter than a month) are pooled per strategy:
one row per position and day, as the paper's "# Days" column counts them. The
excess return over the 3-month T-bill is regressed on the S&P 500 excess return
and the Fama-French SMB and HML factors (E5). Reported per strategy: alpha in %
per month (daily alpha x 22) and annualized (x 12), total and idiosyncratic
volatility, the S&P 500's volatility over the same days, skewness, kurtosis and
the 1% value-at-risk. The paper's p. 515 sensitivities (commission, spread,
rebate, one-day delay) give the benchmark alpha under other assumptions.

The IAPM columns need Datastream's World Market Index, which is not in our
data: not replicated (research/reports/dejong_table6.md).

Inputs: the step-16 engine and config (conf/dejong/default.yaml, section
``table6``), FRED DTB3, Kenneth French's daily factors, the S&P 500 from the
RD/Shell workbook's regression sheet. MLflow: experiment ``dejong.replication``,
run ``table6``.
"""

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from omegaconf import DictConfig, OmegaConf
from scipy import stats

from quant_lab.backtest.dejong import evaluate, evidence_label, load_config, variant_config
from quant_lab.data.dlc import load_twin_config, regression_path, trading_path, twins
from quant_lab.data.french import load_factors
from quant_lab.data.tbill import load_tbill
from quant_lab.models.dejong import EVIDENCE
from quant_lab.tracking import mlflow_utils

EVIDENCE_STATS = {
    "investments": "investments",
    "position days": "position_days",
    "FF3 alpha": "alpha",
    "FF3 annualized abnormal return": "alpha_annualized",
    "sigma": "sigma",
    "sigma S&P 500": "sigma_sp500",
    "FF3 idiosyncratic sigma": "sigma_eps",
    "skewness": "skewness",
    "kurtosis": "kurtosis",
    "1% VaR": "var_1pct",
}
# printed decimals: alpha three, annualized/sigmas/VaR one (in %), skew two, kurtosis one
TOLERANCE = {
    "investments": 0.0,
    "position_days": 0.0,
    "alpha": 0.0005,
    "alpha_annualized": 0.05,
    "sigma": 0.05,
    "sigma_sp500": 0.05,
    "sigma_eps": 0.05,
    "skewness": 0.005,
    "kurtosis": 0.05,
    "var_1pct": 0.05,
}
SIGNIFICANCE = ((0.01, "a"), (0.05, "b"), (0.10, "c"))


def market_returns(root: Path, spec: DictConfig) -> pd.Series:
    """Daily simple S&P 500 returns from a twin's regression data (log returns)."""
    data = pd.read_parquet(root / regression_path(load_twin_config(spec.twin, root)))
    log_r = data[f"index:{spec.column}"]
    return np.expm1(log_r).rename("market")


def pooled_frame(
    days: pd.DataFrame,
    market: pd.Series,
    factors: pd.DataFrame,
    tbill: pd.Series,
    per_year: int,
) -> pd.DataFrame:
    """Position-days with the excess return and the three factors, in % per day.

    The risk-free rate is the T-bill as of each day / ``per_year`` (the engine's
    convention). Every position-day is kept [PAPER-DERIVED, identified: the
    paper's "# Days" equals the padded position-days]; on days without a US
    factor observation (US holidays) SMB and HML are 0, as the Datastream S&P
    500 return is.
    """

    def ns(index: pd.Index) -> pd.DatetimeIndex:  # one datetime resolution for every join
        return pd.DatetimeIndex(index).astype("datetime64[ns]")

    days = days.assign(date=ns(days["date"]))
    market = market.set_axis(ns(market.index)).rename("market")
    factors = factors.set_axis(ns(factors.index))
    tbill = tbill.set_axis(ns(tbill.index))
    frame = days.merge(market, left_on="date", right_index=True, how="left")
    frame = frame.merge(factors[["SMB", "HML"]], left_on="date", right_index=True, how="left")
    frame[["SMB", "HML"]] = frame[["SMB", "HML"]].fillna(0.0)
    frame = frame.sort_values("date")
    rf = pd.merge_asof(
        frame[["date"]], tbill.rename("tbill").to_frame(), left_on="date", right_index=True
    )["tbill"].to_numpy()
    frame["rf"] = rf / per_year
    frame = frame.dropna(subset=["market", "rf"])
    return pd.DataFrame(
        {
            "date": frame["date"],
            "excess": 100 * (frame["return"] - frame["rf"]),
            "market": 100 * (frame["market"] - frame["rf"]),
            "smb": 100 * frame["SMB"],
            "hml": 100 * frame["HML"],
        }
    )


def significance(p: float) -> str:
    return next((mark for level, mark in SIGNIFICANCE if p < level), "")


def risk_statistics(pooled: pd.DataFrame, positions: int, t6: DictConfig) -> dict:
    """Table VI columns of one strategy from its pooled position-days."""
    X = sm.add_constant(pooled[["market", "smb", "hml"]].to_numpy())
    y = pooled["excess"].to_numpy()
    ols = sm.OLS(y, X).fit()
    hac = ols.get_robustcov_results("cluster", groups=pd.factorize(pooled["date"])[0])
    scale = t6.volatility_scale
    alpha = ols.params[0] * t6.month_days
    return {
        "investments": positions,
        "position_days": len(pooled),
        "alpha": alpha,
        "alpha_annualized": 12 * alpha,
        "p_ols": float(ols.pvalues[0]),
        "p_cluster_date": float(hac.pvalues[0]),
        "significance_ols": significance(ols.pvalues[0]),
        "significance_cluster_date": significance(hac.pvalues[0]),
        "sigma": float(y.std(ddof=1) * scale),
        "sigma_sp500": float(pooled["market"].std(ddof=1) * scale),
        "sigma_eps": float(ols.resid.std(ddof=1) * scale),
        "skewness": float(stats.skew(y)),
        "kurtosis": float(stats.kurtosis(y, fisher=False)),
        "var_1pct": float(np.quantile(y, 0.01)),
        "beta_market": float(ols.params[1]),
        "beta_smb": float(ols.params[2]),
        "beta_hml": float(ols.params[3]),
        "r2": float(ols.rsquared),
    }


def paper_table6(root: Path) -> dict[str, dict[str, float]]:
    ev = pd.read_csv(root / EVIDENCE)
    out: dict[str, dict[str, float]] = {}
    for r in ev[ev["claim_id"] == "T6"].itertuples():
        if r.statistic not in EVIDENCE_STATS:
            continue
        row = out.setdefault(r.item, {})
        row[EVIDENCE_STATS[r.statistic]] = float(r.value)
        if r.statistic == "FF3 alpha":
            note = "" if pd.isna(r.note) else str(r.note)
            row["significance"] = next(
                (m for level, m in SIGNIFICANCE if f"{level * 100:g}%" in note), ""
            )
    return out


def paper_sensitivities(root: Path) -> dict[str, float]:
    """The p. 515 benchmark FF3 alphas (evidence S53)."""
    ev = pd.read_csv(root / EVIDENCE)
    rows = ev[(ev["claim_id"] == "S53") & (ev["statistic"] == "FF3 alpha")]
    return {r.item: float(r.value) for r in rows.itertuples()}


def table6(root: Path, result: dict, inputs: dict, t6: DictConfig) -> pd.DataFrame:
    paper = paper_table6(root)
    rows = []
    for name in result["positions"]["strategy"].unique():
        days = result["days"][result["days"]["strategy"] == name]
        positions = int((result["positions"]["strategy"] == name).sum())
        pooled = pooled_frame(
            days, inputs["market"], inputs["factors"], inputs["tbill"], t6.days_per_year
        )
        ours = risk_statistics(pooled, positions, t6)
        theirs = paper[evidence_label(name)]
        for stat, value in theirs.items():
            if stat == "significance":
                continue
            diff = ours[stat] - value
            rows.append(
                {
                    "strategy": name,
                    "statistic": stat,
                    "ours": ours[stat],
                    "paper": value,
                    "difference": diff,
                    "within_rounding": bool(abs(diff) <= TOLERANCE[stat] + 1e-9),
                }
            )
        rows.append(
            {
                "strategy": name,
                "statistic": "significance",
                "ours": f"{ours['significance_ols']}/{ours['significance_cluster_date']}",
                "paper": theirs["significance"],
                "difference": None,
                "within_rounding": ours["significance_ols"] == theirs["significance"],
            }
        )
        for extra in ("beta_market", "beta_smb", "beta_hml", "r2", "p_ols", "p_cluster_date"):
            rows.append({"strategy": name, "statistic": extra, "ours": ours[extra]})
    return pd.DataFrame(rows)


def load_inputs(root: Path, cfg: DictConfig) -> dict:
    t6 = cfg.table6
    for path in (cfg.tbill.path, t6.factors.path):
        if not (root / path).exists():
            raise FileNotFoundError(f"{path} missing: download it and dvc add it (README, Paper 2)")
    return {
        "tbill": load_tbill(root / cfg.tbill.path, cfg.tbill.series),
        "factors": load_factors(root / t6.factors.path),
        "market": market_returns(root, t6.market),
    }


def sensitivity_alphas(root: Path, cfg: DictConfig, inputs: dict) -> pd.DataFrame:
    """Benchmark FF3 alpha under the paper's p. 515 cases."""
    t6 = cfg.table6
    paper = paper_sensitivities(root)
    rows = []
    for name, case in t6.sensitivities.items():
        run_cfg = OmegaConf.merge(variant_config(cfg, None), case.overrides)
        run_cfg.strategies = {cfg.benchmark: cfg.strategies[cfg.benchmark]}
        result = evaluate(root, run_cfg, inputs["tbill"])
        pooled = pooled_frame(
            result["days"], inputs["market"], inputs["factors"], inputs["tbill"], t6.days_per_year
        )
        ours = risk_statistics(pooled, len(result["positions"]), t6)
        rows.append(
            {
                "case": name,
                "paper_item": case.paper_item,
                "alpha": ours["alpha"],
                "paper": paper[case.paper_item],
                "difference": ours["alpha"] - paper[case.paper_item],
            }
        )
    return pd.DataFrame(rows)


def run_table6(root: Path) -> dict:
    cfg = load_config(root)
    inputs = load_inputs(root, cfg)
    tables = []
    for variant in [None, *cfg.variants]:
        result = evaluate(root, variant_config(cfg, variant), inputs["tbill"])
        t = table6(root, result, inputs, cfg.table6)
        tables.append(t.assign(variant=variant or "primary"))
    t6_table = pd.concat(tables, ignore_index=True)
    sens = sensitivity_alphas(root, cfg, inputs)

    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "dejong.replication", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="table6") as run:
        # Approved 1980-2002 windows (research/reports/data_decisions.md, 2026-10-07).
        mlflow.set_tags({**git, "kind": "dejong_table6", "unlock_oos": "true"})
        mlflow.set_tag("tbill_md5", mlflow_utils.file_md5(root / cfg.tbill.path))
        mlflow.set_tag("factors_md5", mlflow_utils.file_md5(root / cfg.table6.factors.path))
        for twin in twins(root):
            path = str(trading_path(load_twin_config(twin, root)))
            mlflow.set_tag(f"data_md5.{twin}", mlflow_utils.data_provenance(root, path)["data_md5"])
        market = str(regression_path(load_twin_config(cfg.table6.market.twin, root)))
        mlflow.set_tag("market_md5", mlflow_utils.data_provenance(root, market)["data_md5"])
        for variant, part in t6_table.groupby("variant"):
            compared = part[part["within_rounding"].notna()]
            ok = int(compared["within_rounding"].astype(bool).sum())
            mlflow.log_metric(f"{variant}.within_rounding", ok)
            mlflow.log_metric(f"{variant}.compared", len(compared))
        with tempfile.TemporaryDirectory() as tmp:
            for name, frame in (("table6", t6_table), ("sensitivities", sens)):
                path = Path(tmp) / f"{name}.csv"
                frame.to_csv(path, index=False)
                mlflow.log_artifact(str(path))
    return {"run_id": run.info.run_id, "table6": t6_table, "sensitivities": sens}


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    out = run_table6(Path.cwd())
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)

    def cell(r) -> str:
        if isinstance(r.ours, str):
            return f"{r.ours} / {r.paper}"
        return f"{r.ours:.3f} / {r.paper:.3f}"

    for variant, t in out["table6"].groupby("variant", sort=False):
        compared = t[t["within_rounding"].notna()].copy()
        compared["cell"] = [cell(r) for r in compared.itertuples()]
        wide = compared.pivot_table(
            index="strategy", columns="statistic", values="cell", aggfunc="first"
        )
        ok = int(compared["within_rounding"].astype(bool).sum())
        print(f"\nTable VI (FF3), {variant}: ours / paper ({ok}/{len(compared)} within rounding)")
        print(wide.to_string())
        if variant == "primary":
            extra = t[t["within_rounding"].isna()].pivot_table(
                index="strategy", columns="statistic", values="ours", aggfunc="first"
            )
            print("\nLoadings, R2 and alpha p-values (OLS / clustered by date):")
            print(extra.astype(float).round(4).to_string())
    print("\nBenchmark alpha, p. 515 sensitivities (% p.m.):")
    print(out["sensitivities"].round(3).to_string(index=False))
    print("run_id:", out["run_id"])


if __name__ == "__main__":
    main()
