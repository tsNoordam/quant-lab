"""Robustness and multiple-testing report (ROADMAP step 9), logged to MLflow.

    uv run python -m quant_lab.backtest.robustness data=rd_shell
    uv run python -m quant_lab.backtest.robustness data=reed_elsevier

For every strategy in ``robustness.strategies`` and every case in
``robustness.cases`` (a list of Hydra overrides):

- on the development pair: a walk-forward (parameters chosen per fold) plus
  train and validation runs at the frozen config values;
- on any other pair: the frozen-value train and validation runs only (no tuning).

Each of those is an ordinary MLflow run (``run_label`` = case). The summary run
(experiment ``<data>.robustness``) adds, for the base case:

- sub-periods, calendar years and volatility regimes;
- trade concentration;
- where the walk-forward choices sit in the grid;
- the deflated Sharpe ratio, with the number of trials counted from MLflow.

The OOS period is never used: the runs go through the same guards as
quant_lab.backtest.run, and ``split.*``/``unlock_oos`` overrides are refused.
"""

import ast
import itertools
import tempfile
from collections.abc import Callable
from pathlib import Path

import hydra
import pandas as pd
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig

from quant_lab.backtest import stats
from quant_lab.backtest.run import (
    BacktestGuardError,
    check_overrides,
    run_backtest,
    run_params,
    run_tags,
)
from quant_lab.backtest.walkforward import run_walk_forward
from quant_lab.data.preprocess import PANEL_FILE
from quant_lab.strategies import STRATEGIES
from quant_lab.strategies.parity_zscore import relative_price
from quant_lab.tracking import mlflow_utils

Compose = Callable[[list[str]], DictConfig]

# Settings that do not define a different strategy configuration: the evaluated
# period, labels, the walk-forward procedure and analysis-only groups.
NOT_A_TRIAL = ("backtest.period", "run_label", "split.", "silta.", "robustness.", "walkforward.")


def case_overrides(case: DictConfig, strategy: str) -> list[str] | None:
    """Overrides of one case for one strategy, or None if the case skips it."""
    if "all" not in case and strategy not in case:
        return None
    out = [*case.get("all", []), *case.get(strategy, [])]
    for override in out:
        key = override.lstrip("+~").split("=", 1)[0]
        if key == "unlock_oos" or key == "backtest.period":
            raise BacktestGuardError(f"robustness cases may not set {key!r}")
    check_overrides(out)
    return list(out)


def run_cases(cfg: DictConfig, root: Path, base: list[str], compose: Compose) -> dict:
    """Run every case; return the per-run metric table and the base-case details."""
    rb = cfg.robustness
    develop = cfg.data.name == rb.development_pair
    rows, base_runs = [], {}
    for strategy in rb.strategies:
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        for case_name, case in rb.cases.items():
            extra = case_overrides(case, strategy)
            if extra is None:
                continue
            frozen = case.get("frozen", True)
            if not develop and not frozen:
                continue  # walk-forward-only case: no tuning off the development pair
            overrides = [*base, f"strategy={strategy}", f"run_label={case_name}", *extra]
            ccfg = compose(overrides)
            common = {"strategy": strategy, "case": case_name}
            if develop:
                wf = run_walk_forward(ccfg, root, overrides)
                rows.append({**common, "run": "walkforward", **_wf_row(wf)})
                if case_name == "base":
                    base_runs[strategy] = {"walkforward": wf, "cfg": ccfg}
            if frozen:
                for period in ("train", "validation"):
                    pcfg = compose([*overrides, f"backtest.period={period}"])
                    res = run_backtest(pcfg, root, overrides)
                    rows.append({**common, "run": period, **_single_row(res)})
    return {"table": pd.DataFrame(rows), "base": base_runs}


def _wf_row(wf: dict) -> dict:
    return {
        "run_id": wf["run_id"],
        "sharpe": wf["wf_sharpe"],
        "total_return": wf["wf_total_return"],
        "max_drawdown": wf["wf_max_drawdown"],
        "n_entries": wf["wf_n_entries"],
        "positive_folds": wf["wf_positive_folds"],
        "distinct_param_sets": wf["wf_distinct_param_sets"],
        "cost_total": sum(
            wf.get(k, 0.0)
            for k in ("wf_cost_spread_impact_tax", "wf_cost_commission", "wf_cost_borrow")
        ),
    }


def _single_row(res: dict) -> dict:
    return {
        "run_id": res["run_id"],
        "sharpe": res["sharpe"],
        "total_return": res["total_return"],
        "max_drawdown": res["max_drawdown"],
        "n_entries": res["n_entries"],
        "cost_total": sum(
            res.get(k, 0.0) for k in ("cost_spread_impact_tax", "cost_commission", "cost_borrow")
        ),
    }


def grid_position(folds: pd.DataFrame, grid: DictConfig) -> pd.DataFrame:
    """For each parameter: in how many folds the chosen value is the grid's min or max."""
    rows = []
    for name in grid:
        values = list(grid[name])
        chosen = folds[f"chosen_{name}"]
        rows.append(
            {
                "parameter": name,
                "grid": str(values),
                "folds": len(chosen),
                "at_min": int((chosen == values[0]).sum()),
                "at_max": int((chosen == values[-1]).sum()),
                "interior": int(((chosen != values[0]) & (chosen != values[-1])).sum()),
            }
        )
    return pd.DataFrame(rows)


def count_trials(tracking_uri: str, data_name: str) -> int:
    """Distinct strategy configurations ever evaluated on this pair, from MLflow.

    A configuration is the set of logged params minus NOT_A_TRIAL. A walk-forward
    run counts every point of its grid. Rerunning an identical configuration, on
    another period or in another fold design, does not add a trial.
    """
    mlflow = mlflow_utils.mlflow
    mlflow.set_tracking_uri(tracking_uri)
    names = [f"{data_name}.{s}" for s in STRATEGIES]
    exps = [e.experiment_id for n in names if (e := mlflow.get_experiment_by_name(n))]
    if not exps:
        return 0
    configs: set[frozenset] = set()
    for run in mlflow.search_runs(experiment_ids=exps, output_format="list"):
        params = {
            k: v
            for k, v in run.data.params.items()
            if not k.startswith(NOT_A_TRIAL) and not k.startswith("strategy.grid.")
        }
        if run.data.tags.get("kind") == "walkforward":
            grid = {
                k.removeprefix("strategy.grid."): ast.literal_eval(v)
                for k, v in run.data.params.items()
                if k.startswith("strategy.grid.")
            }
            names_ = list(grid)
            for combo in itertools.product(*(grid[n] for n in names_)):
                point = {f"strategy.{n}": str(c) for n, c in zip(names_, combo, strict=True)}
                configs.add(frozenset({**params, **point}.items()))
        else:
            configs.add(frozenset(params.items()))
    return len(configs)


def base_diagnostics(cfg: DictConfig, panel: pd.DataFrame, base: dict, n_trials: int) -> dict:
    """Sub-periods, years, regimes, concentration, grid position and DSR per strategy."""
    rb, ann = cfg.robustness, cfg.backtest.annualization
    out: dict[str, pd.DataFrame] = {}
    dsr_rows, conc_rows = [], []
    for strategy, info in base.items():
        wf, scfg = info["walkforward"], info["cfg"]
        r, held = wf["returns"], wf["held"]
        rel = relative_price(panel.loc[: wf["range"].end])
        for key, frame in (
            ("subperiods", stats.subperiods(r, list(rb.subperiod_breaks), ann)),
            ("years", stats.calendar_years(r, ann)),
            ("vol_regimes", stats.volatility_regimes(r, rel, rb.vol_regime_window, ann)),
            ("grid_position", grid_position(wf["folds"], scfg.strategy.grid)),
        ):
            out[f"{strategy}_{key}"] = frame.assign(strategy=strategy)
        conc_rows.append({"strategy": strategy, **stats.trade_concentration(r, held)})
        train_sr = wf["grid"]["train_metric"].dropna()  # annualized Sharpe of every grid point
        var_sr = float(train_sr.var(ddof=1) / ann) if len(train_sr) > 1 else 0.0
        dsr_rows.append(
            {"strategy": strategy, **stats.deflated_sharpe_ratio(r, max(n_trials, 1), var_sr)}
        )
    out["concentration"] = pd.DataFrame(conc_rows)
    out["deflated_sharpe"] = pd.DataFrame(dsr_rows)
    return out


def run_robustness(
    cfg: DictConfig, root: Path, base_overrides: list[str], compose: Compose
) -> dict:
    check_overrides(base_overrides)
    if cfg.get("unlock_oos", False):
        raise BacktestGuardError("robustness never runs with unlock_oos")
    git = mlflow_utils.git_state(root)
    if cfg.mlflow.require_clean_tree and git["git_dirty"] != "false":
        raise BacktestGuardError("mlflow.require_clean_tree=true but the git tree is dirty")
    panel_rel = f"{cfg.data.processed_dir}/{PANEL_FILE}"
    panel = pd.read_parquet(root / panel_rel)

    result = run_cases(cfg, root, base_overrides, compose)
    table = result["table"]
    n_trials = count_trials(cfg.mlflow.tracking_uri, cfg.data.name)
    diag = base_diagnostics(cfg, panel, result["base"], n_trials) if result["base"] else {}

    mlflow_utils.set_experiment(
        cfg.mlflow.tracking_uri, f"{cfg.data.name}.robustness", root / cfg.mlflow.artifact_root
    )
    first = next(iter(result["base"].values()), None)
    period = first["walkforward"]["range"] if first else None
    tags = {"kind": "robustness_summary", "dataset": cfg.data.name, **git}
    if period is not None:
        tags = run_tags(cfg, root, panel_rel, git, period) | tags
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="robustness") as run:
        mlflow.set_tags(tags)
        rb = cfg.robustness
        mlflow.log_params(
            {k: v for k, v in run_params(cfg).items() if k.startswith("data.")}
            | {
                "robustness.strategies": str(list(rb.strategies)),
                "robustness.cases": str(list(rb.cases)),
                "robustness.development_pair": rb.development_pair,
                "robustness.subperiod_breaks": str(list(rb.subperiod_breaks)),
            }
        )
        mlflow.log_metric("n_trials", n_trials)
        mlflow.log_metric("n_case_runs", len(table))
        for row in diag.get("deflated_sharpe", pd.DataFrame()).itertuples():
            mlflow.log_metric(f"{row.strategy}_dsr", row.dsr)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            table.to_csv(tmp / "cases.csv", index=False)
            for name, frame in diag.items():
                frame.to_csv(tmp / f"{name}.csv", index=False)
            mlflow.log_artifacts(str(tmp))
    return {"run_id": run.info.run_id, "table": table, "n_trials": n_trials, **diag}


@hydra.main(version_base="1.3", config_path="../../../conf", config_name="config")
def main(cfg: DictConfig) -> None:
    base = list(HydraConfig.get().overrides.task)
    out = run_robustness(cfg, Path.cwd(), base, lambda o: hydra.compose("config", overrides=o))
    pd.set_option("display.width", 200)
    fmt = {"float_format": lambda v: f"{v:.3f}"}
    print(out["table"].drop(columns=["run_id"]).to_string(index=False, **fmt))
    for name in ("concentration", "deflated_sharpe"):
        if name in out:
            print(out[name].to_string(index=False, **fmt))
    print("n_trials:", out["n_trials"], " run_id:", out["run_id"])


if __name__ == "__main__":
    main()
