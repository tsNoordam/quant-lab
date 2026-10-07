"""Hydra + VectorBT + MLflow backtest entry point.

    uv run python -m quant_lab.backtest.run [hydra overrides]

Pipeline: processed panel (DVC) -> strategy signal on close t -> order at open
t+1 -> VectorBT portfolio -> metrics -> MLflow run with provenance tags.

Guards (see CLAUDE.md):
- `split.*` cannot be overridden on the command line;
- `backtest.period=oos` requires `+unlock_oos=true`;
- data after the evaluated period is removed before any signal is computed.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import hydra
import numpy as np
import pandas as pd
import vectorbt as vbt
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from quant_lab.backtest.report import plot_equity
from quant_lab.data.preprocess import PANEL_FILE
from quant_lab.strategies.parity_zscore import target_positions
from quant_lab.tracking import mlflow_utils

PERIODS = ("train", "validation", "oos")


class BacktestGuardError(RuntimeError):
    """A run was refused because it would break a research rule."""


@dataclass(frozen=True)
class Period:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


def check_overrides(overrides: list[str]) -> None:
    """Split boundaries are locked: selecting a split file is fine, editing one is not."""
    for override in overrides:
        key = override.lstrip("+~").split("=", 1)[0]
        if key.startswith("split."):
            raise BacktestGuardError(
                f"refusing override '{override}': split boundaries are locked in conf/split/"
            )


def select_period(cfg: DictConfig) -> Period:
    name = cfg.backtest.period
    if name not in PERIODS:
        raise BacktestGuardError(f"backtest.period must be one of {PERIODS}, got {name!r}")
    if name == "oos" and not cfg.get("unlock_oos", False):
        raise BacktestGuardError(
            "the out-of-sample period is locked; pass +unlock_oos=true only when you "
            "deliberately evaluate a frozen strategy"
        )
    bounds = cfg.split[name]
    return Period(name, pd.Timestamp(bounds.start), pd.Timestamp(bounds.end))


def execution_targets(
    decisions: pd.Series, period: Period, leg_weight: float
) -> tuple[pd.Series, pd.DataFrame]:
    """Spread position held from each open, and per-leg target weights for VectorBT.

    The decision taken on close t is filled at open t+1 (shift by one bar). The
    book is flat on the first open of the period and closed on its last open.
    """
    held = decisions.shift(1).fillna(0).astype(int).loc[period.start : period.end].copy()
    if held.empty:
        raise BacktestGuardError(f"no data in {period.name} period")
    held.iloc[0] = 0
    held.iloc[-1] = 0
    weights = pd.DataFrame({"a": held * leg_weight, "b": -held * leg_weight}, dtype=float)
    orders = weights.where(weights.ne(weights.shift()))  # only trade when the target changes
    return held, orders


EXECUTION_PRICE = {"next_open": "open", "next_close": "close"}


def simulate(panel: pd.DataFrame, orders: pd.DataFrame, cfg: DictConfig) -> vbt.Portfolio:
    """Fill orders at the bar after the decision: its open, or its close for close-only data."""
    execution = cfg.backtest.execution
    if execution not in EXECUTION_PRICE:
        raise BacktestGuardError(f"backtest.execution must be one of {list(EXECUTION_PRICE)}")
    fill = EXECUTION_PRICE[execution]
    if f"{fill}_a" not in panel:
        raise BacktestGuardError(
            f"execution={execution} needs '{fill}' prices, which dataset {cfg.data.name!r} "
            "does not have; use backtest.execution=next_close"
        )
    rows = orders.index
    close = pd.DataFrame({leg: panel.loc[rows, f"close_{leg}"] for leg in ("a", "b")})
    price = pd.DataFrame({leg: panel.loc[rows, f"{fill}_{leg}"] for leg in ("a", "b")})
    if cfg.costs.model != "flat_bps":
        raise NotImplementedError(f"cost model {cfg.costs.model!r} is not implemented yet")
    return vbt.Portfolio.from_orders(
        close=close,
        size=orders,
        size_type="targetpercent",
        price=price,
        direction="both",
        fees=cfg.costs.fee_bps / 1e4,
        slippage=cfg.costs.slippage_bps / 1e4,
        init_cash=cfg.backtest.init_cash,
        cash_sharing=True,
        group_by=True,
        call_seq="auto",
        freq="1D",
    )


def compute_metrics(equity: pd.Series, held: pd.Series, pf: vbt.Portfolio, ann: int) -> dict:
    returns = equity.pct_change().dropna()
    std = returns.std(ddof=1)
    n = len(returns)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1)
    entries = int(((held != 0) & (held != held.shift(fill_value=0))).sum())
    return {
        "sharpe": float(returns.mean() / std * np.sqrt(ann)) if std > 0 else 0.0,
        "total_return": total,
        "annual_return": float((1 + total) ** (ann / n) - 1) if n else 0.0,
        "annual_volatility": float(std * np.sqrt(ann)),
        "max_drawdown": float((equity / equity.cummax() - 1).min()),
        "n_entries": entries,
        "n_orders": int(pf.orders.count()),
        "exposure": float((held != 0).mean()),
        "total_fees": float(pf.orders.fees.sum()),
        "n_days": n + 1,
    }


def run_backtest(cfg: DictConfig, root: Path, overrides: list[str] | None = None) -> dict:
    check_overrides(overrides or [])
    period = select_period(cfg)

    git = mlflow_utils.git_state(root)
    if cfg.mlflow.require_clean_tree and git["git_dirty"] != "false":
        raise BacktestGuardError("mlflow.require_clean_tree=true but the git tree is dirty")

    panel_rel = f"{cfg.data.processed_dir}/{PANEL_FILE}"
    panel = pd.read_parquet(root / panel_rel).loc[: period.end]  # nothing after the period

    s = cfg.strategy
    decisions, z = target_positions(panel, window=s.window, entry_z=s.entry_z, exit_z=s.exit_z)
    held, orders = execution_targets(decisions, period, s.leg_weight)
    pf = simulate(panel, orders, cfg)
    equity = pf.value()
    metrics = compute_metrics(equity, held, pf, cfg.backtest.annualization)

    mlflow_utils.set_experiment(
        cfg.mlflow.tracking_uri, cfg.mlflow.experiment, root / cfg.mlflow.artifact_root
    )
    resolved = OmegaConf.to_container(cfg, resolve=True)
    tags = {
        **git,
        **mlflow_utils.data_provenance(root, panel_rel),
        "period": period.name,
        "period_start": str(period.start.date()),
        "period_end": str(period.end.date()),
        "unlock_oos": str(bool(cfg.get("unlock_oos", False))).lower(),
        "cost_model": cfg.costs.model,
        "execution": cfg.backtest.execution,
        "strategy": s.name,
        "dataset": cfg.data.name,
    }
    mlflow = mlflow_utils.mlflow  # imported there, after its env defaults are set
    with mlflow.start_run(run_name=f"{s.name}-{period.name}") as run:
        mlflow.set_tags(tags)
        mlflow.log_params(
            mlflow_utils.flatten({k: v for k, v in resolved.items() if k != "mlflow"})
        )
        mlflow.log_metrics(metrics)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            title = (
                f"{cfg.data.name} · {s.name} · {period.name} "
                f"({period.start.date()} to {period.end.date()}) · Sharpe {metrics['sharpe']:.2f}"
            )
            plot_equity(equity, title, tmp / "equity_curve.png")
            (tmp / "config.yaml").write_text(OmegaConf.to_yaml(cfg, resolve=True))
            pd.DataFrame({"equity": equity, "spread_position": held, "zscore": z}).dropna(
                subset=["equity"]
            ).to_csv(tmp / "daily.csv", index_label="date")
            pf.orders.records_readable.to_csv(tmp / "orders.csv", index=False)
            mlflow.log_artifacts(str(tmp))

    return {"run_id": run.info.run_id, **metrics, **tags}


@hydra.main(version_base="1.3", config_path="../../../conf", config_name="config")
def main(cfg: DictConfig) -> None:
    result = run_backtest(cfg, Path.cwd(), list(HydraConfig.get().overrides.task))
    keys = ("run_id", "period", "sharpe", "total_return", "max_drawdown", "n_entries", "git_dirty")
    for key in keys:
        print(f"{key:>14}: {result[key]}")


if __name__ == "__main__":
    main()
