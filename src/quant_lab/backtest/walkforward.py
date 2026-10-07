"""Walk-forward evaluation with embargo, logged to MLflow.

    uv run python -m quant_lab.backtest.walkforward data=rd_shell

The evaluated range is the dataset's train + validation periods; the OOS period
is never used. For each fold:

1. every parameter combination in ``walkforward.grid`` is backtested on the
   training window, using data up to the training window's end only;
2. the selection rule (``best`` or ``neighbourhood_mean``) picks one combination
   from the training scores alone;
3. that combination is traded, unchanged, on the test window, which starts
   ``embargo_days`` trading days after the training window and only sees data up
   to its own end.

The test windows' daily returns are stitched into the walk-forward equity curve.
Costs, sizing and execution are exactly those of quant_lab.backtest.run.
"""

import itertools
import tempfile
from dataclasses import dataclass
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from quant_lab.backtest.report import plot_equity
from quant_lab.backtest.run import (
    BacktestGuardError,
    Period,
    backtest_pair,
    check_overrides,
    compute_metrics,
    run_params,
    run_tags,
)
from quant_lab.data.preprocess import PANEL_FILE
from quant_lab.strategies.parity_zscore import target_positions
from quant_lab.tracking import mlflow_utils

MIN_TEST_DAYS = 20


@dataclass(frozen=True)
class Fold:
    number: int
    train: Period
    test: Period


def make_folds(
    dates: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    anchored: bool,
    train_years: int,
    test_months: int,
    embargo_days: int,
) -> list[Fold]:
    """Calendar-based folds over trading ``dates`` within [start, end].

    Training windows end just before a calendar boundary; the test window starts
    ``embargo_days`` trading days after that boundary and runs ``test_months``.
    A final, shorter test window is kept if it has at least MIN_TEST_DAYS days.
    """
    dates = dates[(dates >= start) & (dates <= end)]
    folds: list[Fold] = []
    boundary = start + pd.DateOffset(years=train_years)
    while True:
        test_end_cal = boundary + pd.DateOffset(months=test_months)
        train_start = start if anchored else boundary - pd.DateOffset(years=train_years)
        train_dates = dates[(dates >= train_start) & (dates < boundary)]
        test_dates = dates[(dates >= boundary) & (dates < test_end_cal)][embargo_days:]
        if len(test_dates) < MIN_TEST_DAYS or len(train_dates) == 0:
            break
        n = len(folds) + 1
        folds.append(
            Fold(
                n,
                Period(f"wf{n}-train", train_dates[0], train_dates[-1]),
                Period(f"wf{n}-test", test_dates[0], test_dates[-1]),
            )
        )
        if test_end_cal > end:
            break
        boundary = test_end_cal
    return folds


def parameter_grid(grid: DictConfig) -> tuple[list[str], list[tuple]]:
    names = list(grid.keys())
    for name in names:
        values = list(grid[name])
        if values != sorted(values):
            raise ValueError(f"walkforward.grid.{name} must be in increasing order")
    return names, list(itertools.product(*(grid[n] for n in names)))


def neighbourhood_scores(names: list[str], grid: DictConfig, raw: dict[tuple, float]):
    """Mean score of each grid point and its direct neighbours (NaN-aware)."""
    axes = [list(grid[n]) for n in names]
    out = {}
    for combo in raw:
        idx = [axes[d].index(v) for d, v in enumerate(combo)]
        members = [combo]
        for d in range(len(names)):
            for step in (-1, 1):
                j = idx[d] + step
                if 0 <= j < len(axes[d]):
                    members.append(combo[:d] + (axes[d][j],) + combo[d + 1 :])
        values = [raw[m] for m in members if np.isfinite(raw[m])]
        out[combo] = float(np.mean(values)) if values else float("nan")
    return out


def evaluate(panel: pd.DataFrame, period: Period, cfg: DictConfig, params: dict):
    """Backtest one parameter set on one window, seeing data up to its end only."""
    visible = panel.loc[: period.end]
    s = OmegaConf.merge(cfg.strategy, params)
    decisions, _ = target_positions(visible, window=s.window, entry_z=s.entry_z, exit_z=s.exit_z)
    run_cfg = OmegaConf.merge(cfg, {"strategy": params})
    sim = backtest_pair(visible, decisions, period, run_cfg)
    metrics = compute_metrics(sim.equity, sim.held, sim.pf, cfg.backtest.annualization)
    return sim, metrics


def development_range(cfg: DictConfig) -> tuple[pd.Timestamp, pd.Timestamp]:
    if cfg.split.name != cfg.data.name:
        raise BacktestGuardError(
            f"split {cfg.split.name!r} does not belong to dataset {cfg.data.name!r}"
        )
    if cfg.split.train is None or cfg.split.validation is None:
        raise BacktestGuardError(
            f"dataset {cfg.data.name!r} has no train/validation periods: it is OOS-only"
        )
    return pd.Timestamp(cfg.split.train.start), pd.Timestamp(cfg.split.validation.end)


def walk_forward(cfg: DictConfig, panel: pd.DataFrame) -> dict:
    wf = cfg.walkforward
    start, end = development_range(cfg)
    panel = panel.loc[:end]  # the OOS period is not even loaded into the loop
    folds = make_folds(
        panel.index,
        start,
        end,
        anchored=wf.anchored,
        train_years=wf.train_years,
        test_months=wf.test_months,
        embargo_days=wf.embargo_days,
    )
    if not folds:
        raise BacktestGuardError("no walk-forward folds fit in the development range")
    names, combos = parameter_grid(wf.grid)

    fold_rows, grid_rows, returns = [], [], []
    for fold in folds:
        raw = {}
        for combo in combos:
            params = dict(zip(names, combo, strict=True))
            try:
                raw[combo] = evaluate(panel, fold.train, cfg, params)[1][wf.metric]
            except ValueError:  # invalid combination, e.g. exit_z >= entry_z
                raw[combo] = float("nan")
        if wf.selection == "best":
            score = raw
        elif wf.selection == "neighbourhood_mean":
            score = neighbourhood_scores(names, wf.grid, raw)
        else:
            raise ValueError(f"unknown walkforward.selection {wf.selection!r}")
        finite = {c: v for c, v in score.items() if np.isfinite(v)}
        if not finite:
            raise BacktestGuardError(f"fold {fold.number}: no valid parameter combination")
        chosen = max(finite, key=lambda c: (finite[c], tuple(-x for x in c)))  # ties: smaller
        params = dict(zip(names, chosen, strict=True))

        sim, test_metrics = evaluate(panel, fold.test, cfg, params)
        returns.append(sim.equity.pct_change().fillna(0.0))
        for combo in combos:
            grid_rows.append(
                {
                    "fold": fold.number,
                    **dict(zip(names, combo, strict=True)),
                    "train_metric": raw[combo],
                    "selection_score": score[combo],
                }
            )
        fold_rows.append(
            {
                "fold": fold.number,
                "train_start": fold.train.start.date(),
                "train_end": fold.train.end.date(),
                "test_start": fold.test.start.date(),
                "test_end": fold.test.end.date(),
                **{f"chosen_{k}": v for k, v in params.items()},
                "train_selection_score": finite[chosen],
                **{f"test_{k}": v for k, v in test_metrics.items()},
            }
        )

    stitched = pd.concat(returns)
    equity = cfg.backtest.init_cash * (1 + stitched).cumprod()
    ann = cfg.backtest.annualization
    std = stitched.std(ddof=1)
    folds_df = pd.DataFrame(fold_rows)
    summary = {
        "wf_sharpe": float(stitched.mean() / std * np.sqrt(ann)) if std > 0 else 0.0,
        "wf_total_return": float(equity.iloc[-1] / cfg.backtest.init_cash - 1),
        "wf_max_drawdown": float((equity / equity.cummax() - 1).min()),
        "wf_annual_volatility": float(std * np.sqrt(ann)),
        "wf_n_folds": len(folds),
        "wf_positive_folds": float((folds_df["test_total_return"] > 0).mean()),
        "wf_distinct_param_sets": int(
            folds_df[[f"chosen_{n}" for n in names]].drop_duplicates().shape[0]
        ),
        "wf_n_entries": int(folds_df["test_n_entries"].sum()),
    }
    return {
        "summary": summary,
        "folds": folds_df,
        "grid": pd.DataFrame(grid_rows),
        "equity": equity,
        "range": Period("walkforward", start, end),
    }


def run_walk_forward(cfg: DictConfig, root: Path, overrides: list[str] | None = None) -> dict:
    check_overrides(overrides or [])
    git = mlflow_utils.git_state(root)
    if cfg.mlflow.require_clean_tree and git["git_dirty"] != "false":
        raise BacktestGuardError("mlflow.require_clean_tree=true but the git tree is dirty")

    panel_rel = f"{cfg.data.processed_dir}/{PANEL_FILE}"
    result = walk_forward(cfg, pd.read_parquet(root / panel_rel))
    summary, rng = result["summary"], result["range"]

    mlflow_utils.set_experiment(
        cfg.mlflow.tracking_uri, cfg.mlflow.experiment, root / cfg.mlflow.artifact_root
    )
    tags = run_tags(cfg, root, panel_rel, git, rng) | {"kind": "walkforward"}
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name=f"{cfg.strategy.name}-walkforward") as run:
        mlflow.set_tags(tags)
        mlflow.log_params(run_params(cfg))
        mlflow.log_metrics(summary)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            title = (
                f"{cfg.data.name} · {cfg.strategy.name} · walk-forward test windows "
                f"({rng.start.date()} to {rng.end.date()}) · Sharpe {summary['wf_sharpe']:.2f}"
            )
            plot_equity(result["equity"], title, tmp / "walkforward_equity.png")
            result["folds"].to_csv(tmp / "folds.csv", index=False)
            result["grid"].to_csv(tmp / "grid_scores.csv", index=False)
            (tmp / "config.yaml").write_text(OmegaConf.to_yaml(cfg, resolve=True))
            mlflow.log_artifacts(str(tmp))
    return {"run_id": run.info.run_id, **summary, **tags, "folds": result["folds"]}


@hydra.main(version_base="1.3", config_path="../../../conf", config_name="config")
def main(cfg: DictConfig) -> None:
    result = run_walk_forward(cfg, Path.cwd(), list(HydraConfig.get().overrides.task))
    cols = (
        ["fold", "test_start", "test_end"]
        + [c for c in result["folds"] if c.startswith("chosen_")]
        + ["test_sharpe", "test_total_return", "test_n_entries"]
    )
    print(result["folds"][cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    for key in ("run_id", "wf_sharpe", "wf_total_return", "wf_max_drawdown", "git_dirty"):
        print(f"{key:>16}: {result[key]}")


if __name__ == "__main__":
    main()
