"""de Jong, Rosenthal & van Dijk (2009) replication: Tables II and III.

    uv run python -m quant_lab.models.dejong              # both tables
    uv run python -m quant_lab.models.dejong --table 3

Table II: for every twin in conf/dlc/ it reads the paper-convention panel
(quant_lab.data.dlc) and computes the statistics of the log deviation from
parity over the paper's sample window.

Table III: regression E2 of the twins' relative local-currency return on its
lag, the two domestic index returns and the exchange-rate change, with
Newey-West standard errors (research/equations/dejong_dlc.md), from the
workbook's own regression data (``<twin>.regression.parquet``).

Both are compared with the paper's values in
research/evidence/dejong_dlc_evidence.csv. Results go to MLflow (experiment
``dejong.replication``, runs ``table2`` and ``table3``) and are printed.

Descriptive only: no trading rule. The windows reach 2002-10-03, which the user
approved for this replication (research/reports/data_decisions.md).
"""

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf
from scipy import stats

from quant_lab.data.dlc import load_twin_config, regression_path, twins
from quant_lab.models.silta import newey_west_cov
from quant_lab.tracking import mlflow_utils

EVIDENCE = "research/evidence/dejong_dlc_evidence.csv"
STATS = ("mean", "mean_abs", "stdev", "min", "max", "pct_positive")
# Table II reports two decimals (one for % positive). Agreement "within rounding"
# allows rounding or truncation (the paper truncates some minima, e.g. ABB
# -20.477 -> -20.47) and, for % positive, one day either way.
TOLERANCE = {"pct_positive": 0.1}
DEFAULT_TOLERANCE = 0.01


def deviation_stats(deviation: pd.Series) -> dict[str, float]:
    """Table II statistics of a log deviation series, in percent."""
    d = deviation.dropna() * 100
    return {
        "mean": float(d.mean()),
        "mean_abs": float(d.abs().mean()),
        "stdev": float(d.std(ddof=1)),
        "min": float(d.min()),
        "max": float(d.max()),
        "pct_positive": float((d > 0).mean() * 100),
    }


def paper_table2(root: Path) -> pd.DataFrame:
    """Table II values from the evidence CSV, one row per twin (paper names)."""
    ev = pd.read_csv(root / EVIDENCE)
    t2 = ev[ev["claim_id"] == "T2"]
    rows = {}
    for r in t2.itertuples():
        label = r.statistic.split(" (")[0]
        stat = (
            "pct_positive"
            if label.startswith("share of days positive")
            else label.removeprefix("log deviation ")
        )
        rows.setdefault(r.item, {})[stat] = float(r.value)
    return pd.DataFrame(rows).T


def normalize_name(name: str) -> str:
    return name.replace("ü", "u").lower()


def table2(root: Path) -> pd.DataFrame:
    """Our Table II next to the paper's, one row per twin and statistic."""
    paper = paper_table2(root)
    paper.index = [normalize_name(i) for i in paper.index]
    rows = []
    for twin in twins(root):
        cfg = load_twin_config(twin, root)
        panel = pd.read_parquet(root / cfg.interim_path)
        ours = deviation_stats(panel["deviation"])
        theirs = paper.loc[normalize_name(cfg.paper_name)]
        for stat in STATS:
            diff = ours[stat] - theirs[stat]
            rows.append(
                {
                    "twin": twin,
                    "paper_name": cfg.paper_name,
                    "window": f"{cfg.window.start}..{cfg.window.end}",
                    "n_days": len(panel),
                    "statistic": stat,
                    "ours": ours[stat],
                    "paper": theirs[stat],
                    "difference": diff,
                    "within_rounding": bool(abs(diff) <= TOLERANCE.get(stat, DEFAULT_TOLERANCE)),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Table III

T3_STATS = (
    "r2",
    "durbin_watson",
    "df",
    "sum_lagged_dependent",
    "sum_index_a",
    "sum_index_b",
    "sum_fx",
)
T3_EVIDENCE = {
    "R2": "r2",
    "Durbin-Watson": "durbin_watson",
    "degrees of freedom": "df",
    "sum lagged dependent": "sum_lagged_dependent",
    "sum market index country 1": "sum_index_a",
    "sum market index country 2": "sum_index_b",
    "sum exchange rate": "sum_fx",
}
SUMS = {
    "sum_lagged_dependent": "lagged_dependent",
    "sum_index_a": "index_a",
    "sum_index_b": "index_b",
    "sum_fx": "fx",
}
# Table III reports three decimals (two for Durbin-Watson) and exact degrees of
# freedom; as for Table II, "within rounding" allows rounding or truncation.
T3_TOLERANCE = {"durbin_watson": 0.01, "df": 0.0}
T3_DEFAULT_TOLERANCE = 0.001
SIGNIFICANCE = ((0.01, "a"), (0.05, "b"), (0.10, "c"))  # the paper's superscripts
VARIANTS = ("identified", "as_stated")


def regression_spec(cfg: DictConfig, variant: str) -> dict:
    """Index labels and excluded dates of one twin's Table III regression.

    ``identified``: the specification that the paper's numbers identify (conf
    comments say where it departs from the text); ``as_stated``: the paper's text
    taken literally (the ``as_stated`` overrides in conf/dlc/<twin>.yaml).
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    reg = cfg.regression
    spec = {
        "index_a": reg.index_a,
        "index_b": reg.index_b,
        "exclude_dates": list(reg.exclude_dates),
    }
    if variant == "as_stated" and reg.get("as_stated"):
        spec.update(OmegaConf.to_container(reg.as_stated))
    return spec


def comovement_design(
    data: pd.DataFrame,
    *,
    index_a: str,
    index_b: str,
    start: str,
    end: str,
    contemporaneous_only: bool,
    exclude_dates: list[str] = (),
) -> pd.DataFrame:
    """y and the regressors of E2 on the window, one row per regression observation.

    y_t = r_A,t - r_B,t (local-currency log returns). Regressors: y_{t-1};
    Index1_t, Index1_{t+1}; Index2_{t-1}, Index2_t (only the contemporaneous
    index returns if the twins trade in the same time zone); e.r._{t-1..t+1}.

    [PAPER-DERIVED, identified from Table III] e.r. is the log change of B's
    currency per unit of A's, the negative of the workbook column (D13); leads
    and lags read the workbook rows next to the window, so the sample is every
    window row with complete data (D17); ``exclude_dates`` drops observations
    from the sample without touching their neighbours' lags (D15).
    """
    y = data["r_a"] - data["r_b"]
    fx = -data["fx"]
    i1, i2 = data[f"index:{index_a}"], data[f"index:{index_b}"]
    cols = {"y": y, "const": pd.Series(1.0, index=data.index), "lagged_dependent": y.shift(1)}
    if contemporaneous_only:
        cols |= {"index_a[t]": i1, "index_b[t]": i2}
    else:
        cols |= {
            "index_a[t]": i1,
            "index_a[t+1]": i1.shift(-1),
            "index_b[t-1]": i2.shift(1),
            "index_b[t]": i2,
        }
    cols |= {"fx[t-1]": fx.shift(1), "fx[t]": fx, "fx[t+1]": fx.shift(-1)}
    frame = pd.DataFrame(cols).loc[start:end]
    frame = frame.drop(index=pd.to_datetime(list(exclude_dates)))  # KeyError if absent
    return frame.dropna()


def eviews_lag(n: int) -> int:
    """Newey-West truncation lag floor(4 (n/100)^(2/9)) (Newey and West 1994; EViews)."""
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


def significance(p: float) -> str:
    return next((mark for level, mark in SIGNIFICANCE if p < level), "")


def comovement(frame: pd.DataFrame) -> dict:
    """OLS of E2: R2 (unadjusted, D17), Durbin-Watson, df and the coefficient sums
    with Wald-test p-values under two Newey-West variants:

    - ``nw``: Bartlett kernel, fixed lag floor(4 (n/100)^(2/9)), no prewhitening,
      n/(n-k) adjustment, as in EViews [IMPLEMENTATION-ASSUMPTION, D18];
    - ``nw_auto``: the lab's R-sandwich default (automatic lag, prewhitened).
    """
    names = [c for c in frame.columns if c != "y"]
    X, y = frame[names].to_numpy(), frame["y"].to_numpy()
    n, k = X.shape
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    rss, tss = resid @ resid, (y - y.mean()) @ (y - y.mean())
    lag = eviews_lag(n)
    covs = {
        "nw": newey_west_cov(X, resid, lag=lag, prewhite=False)[0],
        "nw_auto": newey_west_cov(X, resid)[0],
    }
    out = {
        "r2": 1 - rss / tss,
        "r2_adjusted": 1 - (rss / (n - k)) / (tss / (n - 1)),
        "durbin_watson": float(np.sum(np.diff(resid) ** 2) / rss),
        "df": n - k,
        "nobs": n,
        "nw_lag": lag,
    }
    for stat, group in SUMS.items():
        w = np.array([1.0 if c.startswith(group) else 0.0 for c in names])
        out[stat] = float(w @ coef)
        for name, cov in covs.items():
            t = out[stat] / np.sqrt(w @ cov @ w)
            out[f"{stat}.p_{name}"] = float(2 * stats.t.sf(abs(t), n - k))  # Wald F(1, n-k)
    return out


def paper_table3(root: Path) -> pd.DataFrame:
    """Table III values (and significance marks) from the evidence CSV, one row per twin."""
    ev = pd.read_csv(root / EVIDENCE)
    rows = {}
    for r in ev[ev["claim_id"] == "T3"].itertuples():
        stat = T3_EVIDENCE[r.statistic]
        row = rows.setdefault(normalize_name(r.item), {})
        row[stat] = float(r.value)
        if stat in SUMS:
            note = "" if pd.isna(r.note) else str(r.note)
            row[f"{stat}.significance"] = next(
                (mark for level, mark in SIGNIFICANCE if f"{level * 100:g}%" in note), ""
            )
    return pd.DataFrame(rows).T


def twin_table3(root: Path, twin: str, variant: str) -> dict:
    cfg = load_twin_config(twin, root)
    data = pd.read_parquet(root / regression_path(cfg))
    frame = comovement_design(
        data,
        **regression_spec(cfg, variant),
        start=cfg.window.start,
        end=cfg.window.end,
        contemporaneous_only=cfg.table_i.time_diff_hours == 0,
    )
    return comovement(frame)


def table3(root: Path, variants: tuple[str, ...] = VARIANTS) -> pd.DataFrame:
    """Our Table III next to the paper's, one row per twin, variant and statistic."""
    paper = paper_table3(root)
    rows = []
    for twin in twins(root):
        cfg = load_twin_config(twin, root)
        theirs = paper.loc[normalize_name(cfg.paper_name)]
        for variant in variants:
            ours = twin_table3(root, twin, variant)
            for stat in T3_STATS:
                diff = ours[stat] - theirs[stat]
                row = {
                    "twin": twin,
                    "paper_name": cfg.paper_name,
                    "variant": variant,
                    "statistic": stat,
                    "ours": ours[stat],
                    "paper": theirs[stat],
                    "difference": diff,
                    "within_rounding": bool(
                        abs(diff) <= T3_TOLERANCE.get(stat, T3_DEFAULT_TOLERANCE) + 1e-12
                    ),
                    "nobs": ours["nobs"],
                    "nw_lag": ours["nw_lag"],
                }
                if stat in SUMS:
                    row |= {
                        "significance_paper": theirs[f"{stat}.significance"],
                        "significance_nw": significance(ours[f"{stat}.p_nw"]),
                        "significance_nw_auto": significance(ours[f"{stat}.p_nw_auto"]),
                        "p_nw": ours[f"{stat}.p_nw"],
                        "p_nw_auto": ours[f"{stat}.p_nw_auto"],
                    }
                rows.append(row)
    return pd.DataFrame(rows)


def run_table3(root: Path) -> dict:
    result = table3(root)
    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "dejong.replication", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="table3") as run:
        # Same approved 1980-2002 windows as Table II (data_decisions.md, 2026-10-07).
        mlflow.set_tags({**git, "kind": "dejong_table3", "unlock_oos": "true"})
        for twin in twins(root):
            prov = mlflow_utils.data_provenance(root, regression_path(load_twin_config(twin, root)))
            mlflow.set_tag(f"data_md5.{twin}", prov["data_md5"])
            mlflow.set_tag(f"data_matches_dvc_lock.{twin}", prov["data_matches_dvc_lock"])
        for variant in VARIANTS:
            part = result[result["variant"] == variant]
            sums = part[part["statistic"].isin(SUMS)]
            mlflow.log_metric(f"{variant}.within_rounding", int(part["within_rounding"].sum()))
            mlflow.log_metric(f"{variant}.total", len(part))
            for nw in ("nw", "nw_auto"):
                agree = int((sums[f"significance_{nw}"] == sums["significance_paper"]).sum())
                mlflow.log_metric(f"{variant}.significance_agrees_{nw}", agree)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "table3.csv"
            result.to_csv(path, index=False)
            mlflow.log_artifact(str(path))
    return {"run_id": run.info.run_id, "table": result}


def run_table2(root: Path) -> dict:
    result = table2(root)
    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "dejong.replication", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="table2") as run:
        # Windows reach 2002-10-03: OOS-period data, approved by the user for this
        # replication (research/reports/data_decisions.md, 2026-10-07).
        mlflow.set_tags({**git, "kind": "dejong_table2", "unlock_oos": "true"})
        for twin in twins(root):
            prov = mlflow_utils.data_provenance(root, load_twin_config(twin, root).interim_path)
            mlflow.set_tag(f"data_md5.{twin}", prov["data_md5"])
            mlflow.set_tag(f"data_matches_dvc_lock.{twin}", prov["data_matches_dvc_lock"])
        mlflow.log_metric("statistics_within_rounding", int(result["within_rounding"].sum()))
        mlflow.log_metric("statistics_total", len(result))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "table2.csv"
            result.to_csv(path, index=False)
            mlflow.log_artifact(str(path))
    return {"run_id": run.info.run_id, "table": result}


def print_table2(out: dict) -> None:
    wide = out["table"].pivot_table(
        index="twin", columns="statistic", values=["ours", "paper"], aggfunc="first"
    )
    pd.set_option("display.width", 200)
    print(wide.round(2).to_string())
    bad = out["table"][~out["table"]["within_rounding"]]
    print(f"\n{len(out['table']) - len(bad)}/{len(out['table'])} statistics within rounding")
    if len(bad):
        print(
            bad[["twin", "statistic", "ours", "paper", "difference"]]
            .round(3)
            .to_string(index=False)
        )
    print("run_id:", out["run_id"])


def print_table3(out: dict) -> None:
    t = out["table"]
    pd.set_option("display.width", 200)
    for variant in VARIANTS:
        part = t[t["variant"] == variant]
        wide = part.pivot_table(
            index="twin", columns="statistic", values=["ours", "paper"], aggfunc="first"
        )
        print(f"\nTable III, {variant}")
        print(wide.round(3).to_string())
        bad = part[~part["within_rounding"]]
        print(f"{len(part) - len(bad)}/{len(part)} statistics within rounding")
        if len(bad):
            print(
                bad[["twin", "statistic", "ours", "paper", "difference"]]
                .round(4)
                .to_string(index=False)
            )
        sums = part[part["statistic"].isin(SUMS)]
        for nw in ("nw", "nw_auto"):
            agree = int((sums[f"significance_{nw}"] == sums["significance_paper"]).sum())
            print(f"significance marks equal to the paper ({nw}): {agree}/{len(sums)}")
    print("run_id:", out["run_id"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", choices=["2", "3"], help="one table (default: both)")
    args = parser.parse_args(argv)
    root = Path.cwd()
    if args.table in (None, "2"):
        print_table2(run_table2(root))
    if args.table in (None, "3"):
        print_table3(run_table3(root))


if __name__ == "__main__":
    main()
