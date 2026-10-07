"""One-shot out-of-sample evaluation of the frozen strategies (ROADMAP step 11).

    uv run python -m quant_lab.backtest.oos +unlock_oos=true

Everything this module does was fixed before the OOS data was seen: the runs,
the secondary cases, the diagnostics, the deflation inputs and the decision
rules all come from ``conf/oos/default.yaml``, written in step 10 and frozen
with a ``freeze-*`` git tag (research/specs/freeze/preregistration.md).

Guards: refuses to run without ``+unlock_oos=true``, on a dirty tree, or when
HEAD carries no ``freeze-*`` tag. Every backtest is an ordinary MLflow run
(tag ``unlock_oos=true``, ``run_label=oos_<case>``); the summary run goes to
the experiment ``oos.evaluation``.
"""

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import hydra
import pandas as pd
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig

from quant_lab.backtest import dividends, stats
from quant_lab.backtest.run import BacktestGuardError, check_overrides, run_backtest
from quant_lab.data.preprocess import PANEL_FILE
from quant_lab.tracking import mlflow_utils

Compose = Callable[[list[str]], DictConfig]


def freeze_tags(root: Path) -> list[str]:
    """``freeze-*`` tags pointing at HEAD (empty outside a git checkout)."""
    try:
        out = subprocess.run(
            ["git", "tag", "--points-at", "HEAD"], cwd=root, capture_output=True, text=True
        )
    except OSError:
        return []
    return [t for t in out.stdout.split() if t.startswith("freeze-")]


def holm(pvalues: dict, alpha: float) -> dict:
    """Holm-Bonferroni step-down: which hypotheses are rejected at family level alpha."""
    order = sorted(pvalues, key=lambda k: pvalues[k])
    m, rejected, stop = len(order), {}, False
    for i, key in enumerate(order):
        if not stop and pvalues[key] <= alpha / (m - i):
            rejected[key] = True
        else:
            stop = True
            rejected[key] = False
    return rejected


def ex_date_entry_share(held: pd.Series, panel: pd.DataFrame, min_yield: float, days: int):
    """Share of entries filled within ``days`` trading days after an ex-date of either leg."""
    dps = dividends.per_share_frame(panel, held.index, min_yield)
    ex = (dps > 0).any(axis=1).astype(float)
    recent = ex.shift(1).rolling(days, min_periods=1).max().fillna(0.0) > 0
    entries = held.ne(0) & held.ne(held.shift(fill_value=0))
    return float(recent[entries].mean()) if entries.any() else float("nan")


def classify(row: dict, rules: DictConfig, holm_rejected: bool, not_evaluable: str | None) -> str:
    """The pre-registered verdict for one (pair, strategy)."""
    if not_evaluable:
        return f"not evaluable (pre-declared: {not_evaluable})"
    if row["n_entries"] < rules.min_entries_evaluable:
        return "not evaluable (too few entries)"
    edge = (
        row["dsr"] > rules.dsr_threshold
        and row["n_entries"] >= rules.min_entries_evidence
        and row["top_trade_share"] < rules.max_top_trade_share
        and holm_rejected
    )
    return "evidence of edge" if edge else "no evidence of edge"


def check_ready(cfg: DictConfig, root: Path, require_freeze: bool) -> dict:
    if not cfg.get("unlock_oos", False):
        raise BacktestGuardError("the OOS evaluation needs +unlock_oos=true")
    d = cfg.oos.deflation
    if d.n_trials is None or any(v is None for v in d.var_sr_per_period.values()):
        raise BacktestGuardError("oos.deflation is not filled in: freeze it first (step 10)")
    git = mlflow_utils.git_state(root)
    if require_freeze:
        if git["git_dirty"] != "false":
            raise BacktestGuardError("the OOS evaluation runs only on a clean tree")
        if not freeze_tags(root):
            raise BacktestGuardError("HEAD has no freeze-* tag: the OOS run uses frozen code only")
    return git


def run_oos(
    cfg: DictConfig, root: Path, base: list[str], compose: Compose, *, require_freeze: bool = True
) -> dict:
    check_overrides(base)
    git = check_ready(cfg, root, require_freeze)
    o = cfg.oos
    runs: dict[tuple, dict] = {}
    for pair in o.pairs:
        for strategy in o.strategies:
            cases = [("primary", [])] + [(k, list(v)) for k, v in o.secondary.items()]
            for case, extra in cases:
                check_overrides(extra)
                overrides = [
                    *base,
                    f"data={pair}",
                    f"strategy={strategy}",
                    "backtest.period=oos",
                    f"run_label=oos_{case}",
                    *extra,
                ]
                ccfg = compose(overrides)
                runs[(pair, strategy, case)] = {"cfg": ccfg, **run_backtest(ccfg, root, overrides)}

    ann = cfg.backtest.annualization
    declared = {(n.pair, n.strategy): n.reason for n in o.not_evaluable}
    rows, years, subs = [], [], []
    for pair in o.pairs:
        panel = pd.read_parquet(
            root / runs[(pair, o.strategies[0], "primary")]["cfg"].data.processed_dir / PANEL_FILE
        )
        for strategy in o.strategies:
            res = runs[(pair, strategy, "primary")]
            gross = runs.get((pair, strategy, "zero_cost"))
            r = res["equity"].pct_change().dropna()
            conc = stats.trade_concentration(r, res["held"])
            dsr = stats.deflated_sharpe_ratio(
                r, int(o.deflation.n_trials), float(o.deflation.var_sr_per_period[strategy])
            )
            row = {
                "pair": pair,
                "strategy": strategy,
                "run_id": res["run_id"],
                "sharpe": res["sharpe"],
                "total_return": res["total_return"],
                "max_drawdown": res["max_drawdown"],
                "n_entries": res["n_entries"],
                "n_orders": res["n_orders"],
                "gross_sharpe": gross["sharpe"] if gross else float("nan"),
                "gross_total_return": gross["total_return"] if gross else float("nan"),
                "top_trade_share": conc["top_trade_share"],
                "n_trades": conc["n_trades"],
                "ex_date_entry_share": ex_date_entry_share(
                    res["held"],
                    panel.loc[: res["held"].index[-1]],
                    float(res["cfg"].data.dividends.min_yield),
                    int(o.ex_date_window_days),
                ),
                "dsr": dsr["dsr"],
                "psr_vs_zero": dsr["psr_vs_zero"],
                "sr0_per_period": dsr["sr0_per_period"],
            }
            for case in o.secondary:
                row[f"{case}_sharpe"] = runs[(pair, strategy, case)]["sharpe"]
            rows.append(row)
            breaks = list(o.subperiod_breaks.get(pair, []))
            subs.append(stats.subperiods(r, breaks, ann).assign(pair=pair, strategy=strategy))
            net_y = stats.calendar_years(r, ann).set_index("year")
            frame = net_y[["total_return", "sharpe"]].add_prefix("net_")
            if gross:
                g = gross["equity"].pct_change().dropna()
                gy = stats.calendar_years(g, ann).set_index("year")
                frame = frame.join(gy[["total_return"]].add_prefix("gross_"))
                frame["cost_drag"] = frame["gross_total_return"] - frame["net_total_return"]
            years.append(frame.reset_index().assign(pair=pair, strategy=strategy))

    table = pd.DataFrame(rows)
    pvals = {(x.pair, x.strategy): 1 - x.psr_vs_zero for x in table.itertuples()}
    rejected = holm(pvals, float(o.decision.holm_alpha))
    table["holm_reject"] = [rejected[(x.pair, x.strategy)] for x in table.itertuples()]
    table["verdict"] = [
        classify(x._asdict(), o.decision, x.holm_reject, declared.get((x.pair, x.strategy)))
        for x in table.itertuples()
    ]
    pattern = {}
    for pair in o.prediction_pairs:
        x = table[(table.pair == pair) & (table.strategy == "parity_zscore")].iloc[0]
        pattern[pair] = bool(x.gross_total_return >= 0 and x.total_return < 0)

    mlflow_utils.set_experiment(
        cfg.mlflow.tracking_uri, "oos.evaluation", root / cfg.mlflow.artifact_root
    )
    mlflow = mlflow_utils.mlflow
    tags = {
        "kind": "oos_evaluation",
        "unlock_oos": "true",
        "freeze_tags": ",".join(freeze_tags(root)),
        **git,
    }
    with mlflow.start_run(run_name="oos-evaluation") as run:
        mlflow.set_tags(tags)
        mlflow.log_params(
            {
                "oos.n_trials": o.deflation.n_trials,
                "oos.pairs": str(list(o.pairs)),
                "oos.strategies": str(list(o.strategies)),
            }
        )
        mlflow.log_metric("n_evidence_of_edge", int((table["verdict"] == "evidence of edge").sum()))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            table.to_csv(tmp / "oos_results.csv", index=False)
            pd.concat(years).to_csv(tmp / "oos_years.csv", index=False)
            pd.concat(subs).to_csv(tmp / "oos_subperiods.csv", index=False)
            pd.Series(pattern, name="gross_ge_0_and_net_lt_0").to_csv(tmp / "oos_pattern.csv")
            mlflow.log_artifacts(str(tmp))
    return {
        "run_id": run.info.run_id,
        "table": table,
        "years": pd.concat(years),
        "subperiods": pd.concat(subs),
        "pattern": pattern,
    }


@hydra.main(version_base="1.3", config_path="../../../conf", config_name="config")
def main(cfg: DictConfig) -> None:
    base = list(HydraConfig.get().overrides.task)
    out = run_oos(cfg, Path.cwd(), base, lambda o: hydra.compose("config", overrides=o))
    pd.set_option("display.width", 220)
    cols = [
        "pair",
        "strategy",
        "sharpe",
        "total_return",
        "gross_sharpe",
        "n_entries",
        "top_trade_share",
        "dsr",
        "psr_vs_zero",
        "holm_reject",
        "verdict",
    ]
    print(out["table"][cols].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("limits-to-arbitrage pattern (gross >= 0, net < 0):", out["pattern"])
    print("run_id:", out["run_id"])


if __name__ == "__main__":
    main()
