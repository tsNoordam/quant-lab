"""de Jong et al. (2009) under the lab's standard: a convention waterfall
(ROADMAP step 18, part 1).

    uv run python -m quant_lab.models.dejong_standard

Keeps the paper's trading rules (thresholds, horizons) and changes its
conventions one at a time, cumulatively (``standard.steps`` in
conf/dejong/default.yaml): the cleaned Dexia spike, trading one close after
the signal, no holding into unification announcements with open positions
marked at the end, and no T-bill padding or lockout. Every step is evaluated
two ways:

- the paper's metric: the days-weighted mean of position returns in % per month;
- calendar time: one daily portfolio return (equal weight over the positions
  open that day, the T-bill when none is), its excess over the T-bill
  annualized (x 260), volatility and Sharpe ratio.

Both for all twins and per time-zone gap between the twins' markets (0, 1, 5
and 10 hours, Table I). The difference between the first and the last step is
the result: how much of the paper's return is convention.

Descriptive, on the user-approved 1980-2002 windows; the lab-engine part of
step 18 (liquidity costs) runs through quant_lab.backtest.run on the lab pairs.
"""

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from quant_lab.backtest.dejong import evaluate, load_config, variant_config
from quant_lab.data.dlc import load_twin_config, twins
from quant_lab.data.tbill import load_tbill
from quant_lab.tracking import mlflow_utils

PER_YEAR = 260


def time_zone_groups(root: Path) -> dict[str, str]:
    """twin -> '0h', '1h', '5h' or '10h' (absolute closing-time gap, Table I)."""
    return {
        t: f"{abs(int(load_twin_config(t, root).table_i.time_diff_hours))}h" for t in twins(root)
    }


def step_configs(cfg: DictConfig) -> list[tuple[str, DictConfig]]:
    """The cumulative configurations of the waterfall."""
    current = variant_config(cfg, None)
    out = []
    for step in cfg.standard.steps:
        current = OmegaConf.merge(current, step.overrides)
        out.append((step.name, current))
    return out


def position_metric(pos: pd.DataFrame) -> dict:
    r, w = pos["monthly_return"], pos["days_counted"]
    return {
        "positions": len(pos),
        "weighted_mean_pm": float((r * w).sum() / w.sum()) if len(pos) else np.nan,
        "share_negative": float((r < 0).mean()) if len(pos) else np.nan,
    }


def calendar_metric(days: pd.DataFrame, tbill: pd.Series, start: str, end: str) -> dict:
    """Daily equal-weight portfolio over open positions; flat days earn the T-bill."""
    calendar = pd.bdate_range(start, end)
    rf = tbill.reindex(calendar, method="ffill").to_numpy() / PER_YEAR
    port = days.groupby("date")["return"].mean().reindex(calendar)
    invested = port.notna().to_numpy()
    excess = np.where(invested, port.to_numpy() - rf, 0.0)
    mean, sd = excess.mean(), excess.std(ddof=1)
    return {
        "excess_return_pa": float(mean * PER_YEAR * 100),
        "volatility_pa": float(sd * np.sqrt(PER_YEAR) * 100),
        "sharpe": float(mean / sd * np.sqrt(PER_YEAR)) if sd > 0 else np.nan,
        "share_days_invested": float(invested.mean()),
    }


def waterfall(root: Path, cfg: DictConfig, tbill: pd.Series, strategy: str) -> pd.DataFrame:
    groups = time_zone_groups(root)
    rows = []
    for name, step_cfg in step_configs(cfg):
        run_cfg = step_cfg.copy()
        run_cfg.strategies = {strategy: cfg.strategies[strategy]}
        result = evaluate(root, run_cfg, tbill, tables=False)
        pos, days = result["positions"], result["days"]
        pos = pos.assign(group=pos["twin"].map(groups))
        days = days.assign(group=days["twin"].map(groups))
        for group in ["all", *sorted(set(groups.values()), key=lambda g: int(g[:-1]))]:
            p = pos if group == "all" else pos[pos["group"] == group]
            d = days if group == "all" else days[days["group"] == group]
            members = sorted(t for t, g in groups.items() if group in ("all", g))
            windows = [load_twin_config(t, root).window for t in members]
            start = min(w.start for w in windows)
            end = max(w.end for w in windows)
            rows.append(
                {
                    "strategy": strategy,
                    "step": name,
                    "group": group,
                    **position_metric(p),
                    **calendar_metric(d, tbill, start, end),
                }
            )
    return pd.DataFrame(rows)


def run_standard(root: Path) -> dict:
    cfg = load_config(root)
    if not (root / cfg.tbill.path).exists():
        raise FileNotFoundError(f"{cfg.tbill.path} missing (README, Paper 2)")
    tbill = load_tbill(root / cfg.tbill.path, cfg.tbill.series)
    table = pd.concat(
        [waterfall(root, cfg, tbill, strategy) for strategy in cfg.strategies], ignore_index=True
    )
    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "dejong.replication", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="standard") as run:
        # Approved 1980-2002 windows (research/reports/data_decisions.md, 2026-10-07).
        mlflow.set_tags({**git, "kind": "dejong_standard", "unlock_oos": "true"})
        mlflow.set_tag("tbill_md5", mlflow_utils.file_md5(root / cfg.tbill.path))
        bench = table[(table.strategy == cfg.benchmark) & (table.group == "all")]
        for r in bench.itertuples():
            mlflow.log_metric(f"{r.step}.weighted_mean_pm", r.weighted_mean_pm)
            mlflow.log_metric(f"{r.step}.sharpe", r.sharpe)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "waterfall.csv"
            table.to_csv(path, index=False)
            mlflow.log_artifact(str(path))
    return {"run_id": run.info.run_id, "table": table, "benchmark": cfg.benchmark}


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    out = run_standard(Path.cwd())
    t = out["table"]
    pd.set_option("display.width", 250)
    steps = list(dict.fromkeys(t["step"]))
    bench = t[t.strategy == out["benchmark"]]
    for metric, label in (
        ("weighted_mean_pm", "paper metric: weighted mean % per month"),
        ("excess_return_pa", "calendar time: excess return % per year"),
        ("sharpe", "calendar time: Sharpe ratio"),
        ("positions", "positions"),
    ):
        wide = bench.pivot_table(index="group", columns="step", values=metric)[steps]
        wide = wide.reindex(["all", "0h", "1h", "5h", "10h"])
        print(f"\n{out['benchmark']}, {label}")
        print(wide.round(3).to_string())
    last = t[(t.step == steps[-1]) & (t.group == "all")].set_index("strategy")
    first = t[(t.step == steps[0]) & (t.group == "all")].set_index("strategy")
    print(f"\nAll strategies, all twins: {steps[0]} -> {steps[-1]}")
    summary = pd.DataFrame(
        {
            "wm_paper_conv": first["weighted_mean_pm"],
            "wm_our_standard": last["weighted_mean_pm"],
            "sharpe_paper_conv": first["sharpe"],
            "sharpe_our_standard": last["sharpe"],
        }
    )
    print(summary.round(3).to_string())
    print("run_id:", out["run_id"])


if __name__ == "__main__":
    main()
