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

from quant_lab.backtest import costs
from quant_lab.backtest.costs import LEGS
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
    decisions: pd.Series,
    period: Period,
    leg_weight: float,
    weight_cap: pd.Series | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Spread position held from each fill bar, and per-leg target weights for VectorBT.

    The decision taken on close t is filled on bar t+1 (shift by one bar). The
    book is flat on the first bar of the period and closed on its last bar.

    ``weight_cap`` (as of each decision close) limits the |leg weight| taken at
    entry; the size is then held until the position changes. A missing cap
    (statistics still warming up) means no entry.
    """
    held = decisions.shift(1).fillna(0).astype(int).loc[period.start : period.end].copy()
    if held.empty:
        raise BacktestGuardError(f"no data in {period.name} period")
    held.iloc[0] = 0
    held.iloc[-1] = 0
    size = pd.Series(float(leg_weight), index=held.index)
    if weight_cap is not None:
        cap = weight_cap.shift(1).reindex(held.index)
        size = np.minimum(size, cap.fillna(0.0))
    size = size.where(held.ne(held.shift())).ffill()  # sized at entry, then held
    weights = pd.DataFrame({"a": held * size, "b": -held * size}, dtype=float)
    orders = weights.where(weights.ne(weights.shift()))  # only trade when the target changes
    return held, orders


EXECUTION_PRICE = {"next_open": "open", "next_close": "close"}


def fill_prices(panel: pd.DataFrame, rows: pd.Index, cfg: DictConfig) -> pd.DataFrame:
    """Raw (pre-cost) execution prices: the fill bar's open, or its close for close-only data."""
    execution = cfg.backtest.execution
    if execution not in EXECUTION_PRICE:
        raise BacktestGuardError(f"backtest.execution must be one of {list(EXECUTION_PRICE)}")
    fill = EXECUTION_PRICE[execution]
    if f"{fill}_a" not in panel:
        raise BacktestGuardError(
            f"execution={execution} needs '{fill}' prices, which dataset {cfg.data.name!r} "
            "does not have; use backtest.execution=next_close"
        )
    return pd.DataFrame({leg: panel.loc[rows, f"{fill}_{leg}"] for leg in LEGS})


def simulate(
    panel: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: DictConfig,
    order_cost: pd.DataFrame | None = None,
) -> vbt.Portfolio:
    """Run the orders through VectorBT.

    flat_bps:  constant fee + slippage (sensitivity case).
    liquidity: commission as fee; ``order_cost`` (spread + impact + tax, per order)
               as slippage, i.e. an adverse move of the fill price.
    """
    rows = orders.index
    price = fill_prices(panel, rows, cfg)
    close = pd.DataFrame({leg: panel.loc[rows, f"close_{leg}"] for leg in LEGS})
    c = cfg.costs
    if c.model == "flat_bps":
        fees, slippage = c.fee_bps / 1e4, c.slippage_bps / 1e4
    elif c.model == "liquidity":
        if order_cost is None:
            raise ValueError("cost model 'liquidity' needs order_cost")
        fees, slippage = c.commission_bps / 1e4, order_cost.reindex(rows).fillna(0.0)
    else:
        raise BacktestGuardError(f"unknown cost model {c.model!r}")
    return vbt.Portfolio.from_orders(
        close=close,
        size=orders,
        size_type="targetpercent",
        price=price,
        direction="both",
        fees=fees,
        slippage=slippage,
        init_cash=cfg.backtest.init_cash,
        cash_sharing=True,
        group_by=True,
        call_seq="auto",
        freq="1D",
    )


@dataclass(frozen=True)
class Simulation:
    pf: vbt.Portfolio
    held: pd.Series
    orders: pd.DataFrame
    order_cost: pd.DataFrame | None
    borrow: pd.Series
    equity: pd.Series  # portfolio value net of borrow charges
    cost_metrics: dict


def backtest_pair(
    panel: pd.DataFrame, decisions: pd.Series, period: Period, cfg: DictConfig
) -> Simulation:
    """Decisions (as of each close) -> sized orders -> costs -> VectorBT -> net equity."""
    c, capital = cfg.costs, cfg.backtest.init_cash
    leg_weight = cfg.strategy.leg_weight
    if c.model != "liquidity":
        held, orders = execution_targets(decisions, period, leg_weight)
        pf = simulate(panel, orders, cfg)
        borrow = pd.Series(0.0, index=held.index)
        return Simulation(pf, held, orders, None, borrow, pf.value(), {})

    if not cfg.data.get("volume_reliable", True):
        raise BacktestGuardError(
            f"dataset {cfg.data.name!r} has volume_reliable: false; the liquidity cost model "
            "needs volume (ADV). Use costs=flat_bps as a labelled sensitivity case instead."
        )
    stats = {leg: costs.market_stats(panel, leg, c) for leg in LEGS}
    cap = costs.participation_cap(stats, capital, c.limits.max_participation)
    held, orders = execution_targets(decisions, period, leg_weight, weight_cap=cap)
    at_fill = {leg: st.shift(1).reindex(orders.index) for leg, st in stats.items()}  # decision-day
    order_cost = costs.order_costs(orders, at_fill, capital, c)
    pf = simulate(panel, orders, cfg, order_cost)

    short_value = pf.asset_value(group_by=False).clip(upper=0.0).sum(axis=1)
    borrow = costs.borrow_charges(short_value, c.borrow_bps_annual, cfg.backtest.annualization)
    equity = pf.value() - borrow.cumsum()

    records = pf.orders.records_readable
    raw = fill_prices(panel, orders.index, cfg)
    rows = raw.index.get_indexer(records["Timestamp"])
    cols = raw.columns.get_indexer(records["Column"])
    raw_at_order = raw.to_numpy()[rows, cols]
    entry_rows = held.ne(0) & held.ne(held.shift(fill_value=0))
    entry_caps = cap.shift(1).reindex(held.index)[entry_rows]
    has_order = order_cost.notna().to_numpy()
    quoted = pd.DataFrame({leg: at_fill[leg]["quoted"] for leg in LEGS}).fillna(False).to_numpy()
    paid = order_cost.to_numpy()[has_order]
    cost_metrics = {
        "cost_spread_impact_tax": float(
            (records["Size"] * (records["Price"] - raw_at_order).abs()).sum()
        ),
        "cost_commission": float(records["Fees"].sum()),
        "cost_borrow": float(borrow.sum()),
        "median_order_cost_bps": float(np.median(paid) * 1e4) if paid.size else 0.0,
        "entries_capped": int((entry_caps < leg_weight).sum()),
        "quoted_spread_share": float(quoted[has_order].mean()) if paid.size else 0.0,
    }
    return Simulation(pf, held, orders, order_cost, borrow, equity, cost_metrics)


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
    sim = backtest_pair(panel, decisions, period, cfg)
    equity = sim.equity
    metrics = compute_metrics(equity, sim.held, sim.pf, cfg.backtest.annualization)
    metrics |= sim.cost_metrics
    held, pf = sim.held, sim.pf

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
