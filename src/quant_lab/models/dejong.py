"""de Jong, Rosenthal & van Dijk (2009) replication: Table II, deviations from parity.

    uv run python -m quant_lab.models.dejong

For every twin in conf/dlc/ it reads the paper-convention panel
(quant_lab.data.dlc), computes the Table II statistics of the log deviation from
parity over the paper's sample window, and compares them with the paper's
values in research/evidence/dejong_dlc_evidence.csv. Results go to MLflow
(experiment ``dejong.replication``, run ``table2``) and are printed.

Descriptive only: no trading rule. The windows reach 2002-10-03, which the user
approved for this replication (research/reports/data_decisions.md).
"""

import tempfile
from pathlib import Path

import pandas as pd
from omegaconf import OmegaConf

from quant_lab.data.dlc import load_twin_config, twins
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


def main() -> None:
    out = run_table2(Path.cwd())
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


if __name__ == "__main__":
    main()
