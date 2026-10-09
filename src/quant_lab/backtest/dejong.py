"""de Jong, Rosenthal & van Dijk (2009): arbitrage strategies under the paper's
conventions (Tables IV-V; ROADMAP step 16).

    uv run python -m quant_lab.backtest.dejong

For every twin (conf/dlc/) and strategy (conf/dejong/default.yaml) it finds the
paper's arbitrage positions on the parity deviation, runs each through a
Regulation T margin account and reports the Table IV (per twin, benchmark
strategy) and Table V (all twins, eight strategies) statistics next to the
paper's values from research/evidence/dejong_dlc_evidence.csv. The
``variants`` in the config are sensitivity cases. Results go to MLflow
(experiment ``dejong.replication``, run ``tables45``).

This is the paper's engine, not the lab's: fixed costs and interest, positions
traded at the close on which the signal is observed (the paper's convention;
the lab's engine trades one bar later), no market impact. Every convention is
tagged in the config; research/reports/dejong_tables45.md has the evidence.
Descriptive replication on the user-approved 1980-2002 windows; no parameter
is chosen here.
"""

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from quant_lab.data.dlc import load_twin_config, trading_path, twins
from quant_lab.data.tbill import load_tbill, rate_on
from quant_lab.models.dejong import EVIDENCE, normalize_name
from quant_lab.tracking import mlflow_utils

CONFIG = "conf/dejong/default.yaml"


# ---------------------------------------------------------------- positions


@dataclass(frozen=True)
class Position:
    entry: int  # row of the entry trade
    exit: int  # row of the exit trade
    direction: int  # +1: long A, short B (A cheap, d < 0); -1: short A, long B
    cut: bool  # closed at the maximum horizon
    forced: bool  # closed at the end of a unified twin's trading panel


def find_positions(
    deviation: np.ndarray,
    *,
    buy: float,
    sell: float,
    horizon: int | None,
    last_entry: int,
    close_at_end: bool,
    month_days: int = 22,
    delay: int = 0,
) -> list[Position]:
    """The paper's positions on one twin (E3 and conf/dejong rules).

    Signals are read on closes: an entry signal at close s needs |d_s| >= buy,
    |d_{s-1}| < buy and s <= last_entry; the exit signal is the first later
    close v with |d_v| <= sell, or v = s + horizon (a cut-off). Trades happen
    ``delay`` closes after their signal. A position still open on the last row
    is closed there if ``close_at_end``, otherwise discarded. The next entry
    signal can come at max(v + 1, s + month_days) at the earliest.
    """
    a = np.abs(deviation)
    last = len(a) - 1
    positions: list[Position] = []
    s = 1
    while s <= min(last_entry, last - delay):
        if not (a[s] >= buy and a[s - 1] < buy):
            s += 1
            continue
        exit_signal, cut = None, False
        for v in range(s + 1, last - delay + 1):
            if a[v] <= sell:
                exit_signal = v
                break
            if horizon is not None and v - s >= horizon:
                exit_signal, cut = v, True
                break
        direction = 1 if deviation[s] < 0 else -1
        if exit_signal is None:
            if close_at_end:
                positions.append(Position(s + delay, last, direction, False, True))
            break
        positions.append(Position(s + delay, exit_signal + delay, direction, cut, False))
        s = max(exit_signal + 1, s + month_days)
    return positions


# ---------------------------------------------------------------- the account


def run_account(r_long: np.ndarray, r_short: np.ndarray, account: DictConfig, costs) -> dict:
    """One position through a Regulation T margin account, capital 1.

    Entry: long 1 and short 1 (50% initial margin on each leg uses all equity);
    the long half is financed with a margin loan, the short proceeds earn the
    rebate, the short margin deposit is collateral. Every day: legs move, interest
    accrues, then the maintenance check; a margin call unwinds the smallest
    fraction of both legs that restores it, paying commission. Exit pays
    commission (and the half spread if ``spread_at_exit``) on both legs.

    Returns the total return on capital, the number of margin calls and the
    daily returns on equity (day 1 includes the entry costs, the last day the
    exit costs).
    """
    dt = 1 / account.days_per_year
    im = account.initial_margin
    long_v = short_v = 1.0
    loan = (1 - im) * long_v
    proceeds = short_v
    deposit = im * short_v
    entry_cost = 2 * (costs.commission + costs.half_spread)
    cash = 1.0 - im * long_v - deposit - entry_cost  # free cash (negative = borrowed)
    deposit_rate = account.cash_rate if account.short_deposit_earns else 0.0
    calls = 0
    n = len(r_long)
    equity_path = np.empty(n)
    for k in range(n):
        long_v *= 1 + r_long[k]
        short_v *= 1 + r_short[k]
        cash *= 1 + (account.cash_rate if cash >= 0 else account.loan_rate) * dt
        loan *= 1 + account.loan_rate * dt
        proceeds *= 1 + account.rebate_rate * dt
        deposit *= 1 + deposit_rate * dt
        equity_path[k] = cash + deposit + long_v - loan + proceeds - short_v
        if k == n - 1:
            break  # the position is closed today
        f = liquidation_fraction(long_v, short_v, loan, proceeds, deposit, cash, account, costs)
        if f > 0:
            calls += 1
            cash -= costs.commission * f * (long_v + short_v)
            loan -= f * long_v
            proceeds -= f * short_v
            long_v *= 1 - f
            short_v *= 1 - f
            if loan < 0:
                cash, loan = cash - loan, 0.0
            equity_path[k] = cash + deposit + long_v - loan + proceeds - short_v
    exit_rate = costs.commission + (costs.half_spread if costs.spread_at_exit else 0.0)
    equity = cash + deposit + long_v - loan + proceeds - short_v
    equity -= exit_rate * (long_v + short_v)
    equity_path[-1] = equity
    daily = np.diff(np.concatenate([[1.0], equity_path])) / np.concatenate(
        [[1.0], equity_path[:-1]]
    )
    return {"total_return": equity - 1.0, "margin_calls": calls, "daily_returns": daily}


def liquidation_fraction(long_v, short_v, loan, proceeds, deposit, cash, account, costs) -> float:
    """Smallest fraction of both legs to unwind so maintenance holds (0 if it does)."""
    if long_v <= 0 and short_v <= 0:
        return 0.0  # fully liquidated: only cash is left
    if account.margin_rule == "per_leg":
        # unwinding a fraction keeps each leg's equity and scales its requirement
        need = []
        long_eq = long_v - loan
        if long_eq < account.maintenance_long * long_v:
            need.append(1 - long_eq / (account.maintenance_long * long_v))
        short_eq = proceeds + deposit - short_v
        if short_eq < account.maintenance_short * short_v:
            need.append(1 - short_eq / (account.maintenance_short * short_v))
        return float(min(1.0, max(need))) if need else 0.0
    if account.margin_rule == "pooled":
        equity = cash + deposit + long_v - loan + proceeds - short_v
        req = account.maintenance_long * long_v + account.maintenance_short * short_v
        if equity >= req:
            return 0.0
        return float(min(1.0, (req - equity) / (req - costs.commission * (long_v + short_v))))
    raise ValueError(f"unknown margin_rule {account.margin_rule!r}")


def monthly_return(total: float, days: int, tbill: float, month_days: int, per_year: int):
    """(days counted, % per month): short positions earn the T-bill to a full month."""
    if days < month_days:
        total = (1 + total) * (1 + tbill * (month_days - days) / per_year) - 1
    counted = max(days, month_days)
    return counted, 100 * total * month_days / counted


# ---------------------------------------------------------------- one strategy


def leg_returns(panel: pd.DataFrame, returns: DictConfig) -> tuple[np.ndarray, np.ndarray]:
    """Daily simple returns of A and B (A in B's currency if ``currency: common``)."""
    a = panel["tr_a"] if returns.total_return else panel["price_a"]
    b = panel["tr_b"] if returns.total_return else panel["price_b"]
    if returns.currency == "common":
        a = a / panel["fx"]
    elif returns.currency != "local":
        raise ValueError(f"unknown currency {returns.currency!r}")
    return a.pct_change().to_numpy(), b.pct_change().to_numpy()


def padding_dates(panel: pd.DataFrame, exit_row: int, count: int) -> pd.DatetimeIndex:
    """The ``count`` trading days after an exit: the twin's next rows, then weekdays."""
    dates = panel.index[exit_row + 1 : exit_row + 1 + count]
    missing = count - len(dates)
    if missing:
        after = pd.bdate_range(panel.index[-1] + pd.offsets.BDay(1), periods=missing)
        dates = dates.append(after)
    return dates


def twin_positions(
    panel: pd.DataFrame, spec: DictConfig, cfg: DictConfig, tbill: pd.Series, twin: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The positions of one twin and strategy, and their daily returns.

    Daily rows cover each position's days and, for a position shorter than a
    month, the padding days that earn the T-bill (Table VI pools these rows).
    """
    in_window = panel["in_window"].to_numpy()
    positions = find_positions(
        panel["deviation"].to_numpy(),
        buy=spec.buy,
        sell=spec.sell,
        horizon=spec.horizon,
        last_entry=int(np.flatnonzero(in_window)[-1]),
        close_at_end=not in_window[-1],
        month_days=cfg.rules.month_days,
        delay=cfg.rules.delay,
    )
    ra, rb = leg_returns(panel, cfg.returns)
    rows, daily = [], []
    for number, p in enumerate(positions):
        days = slice(p.entry + 1, p.exit + 1)
        r_long, r_short = (ra[days], rb[days]) if p.direction > 0 else (rb[days], ra[days])
        if np.isnan(r_long).any() or np.isnan(r_short).any():
            raise ValueError(f"{twin}: missing price inside a position ({panel.index[p.entry]})")
        acct = run_account(r_long, r_short, cfg.account, cfg.costs)
        exit_date = panel.index[p.exit]
        exit_tbill = rate_on(tbill, exit_date)
        counted, monthly = monthly_return(
            acct["total_return"],
            p.exit - p.entry,
            exit_tbill,
            cfg.rules.month_days,
            cfg.account.days_per_year,
        )
        pad = counted - (p.exit - p.entry)
        daily.append(
            pd.DataFrame(
                {
                    "twin": twin,
                    "position": number,
                    "date": panel.index[days].append(padding_dates(panel, p.exit, pad)),
                    "return": np.concatenate(
                        [
                            acct["daily_returns"],
                            np.full(pad, exit_tbill / cfg.account.days_per_year),
                        ]
                    ),
                    "padding": np.r_[np.zeros(p.exit - p.entry, bool), np.ones(pad, bool)],
                }
            )
        )
        rows.append(
            {
                "twin": twin,
                "entry_date": panel.index[p.entry],
                "exit_date": exit_date,
                "long_a": p.direction > 0,
                "days": p.exit - p.entry,
                "days_counted": counted,
                "cut": p.cut,
                "forced_close": p.forced,
                "margin_calls": acct["margin_calls"],
                "total_return": acct["total_return"],
                "monthly_return": monthly,
            }
        )
    days_frame = pd.concat(daily, ignore_index=True) if daily else pd.DataFrame()
    return pd.DataFrame(rows), days_frame


def load_trading(root: Path, twin: str, exclude: list[str]) -> pd.DataFrame:
    panel = pd.read_parquet(root / trading_path(load_twin_config(twin, root)))
    return panel.drop(index=pd.to_datetime(list(exclude)))  # KeyError if a date is absent


def all_positions(
    root: Path, cfg: DictConfig, tbill: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Positions and their daily returns, every twin and strategy."""
    frames, daily = [], []
    for twin in twins(root):
        panel = load_trading(root, twin, cfg.exclude_dates.get(twin, []))
        for name, spec in cfg.strategies.items():
            pos, days = twin_positions(panel, spec, cfg, tbill, twin)
            frames.append(pos.assign(strategy=name))
            daily.append(days.assign(strategy=name))
    return pd.concat(frames, ignore_index=True), pd.concat(daily, ignore_index=True)


# ---------------------------------------------------------------- tables


def summarize(pos: pd.DataFrame) -> dict:
    """The Table IV/V columns of a group of positions."""
    r, w = pos["monthly_return"], pos["days_counted"]
    long_a = pos["long_a"].astype(bool)
    return {
        "positions_long_a": int(long_a.sum()),
        "positions_short_a": int((~long_a).sum()),
        "mean_days": float(w.mean()),
        "median_days": float(w.median()),
        "min_days": int(w.min()),
        "max_days": int(w.max()),
        "weighted_mean_return": float((r * w).sum() / w.sum()),
        "median_return": float(r.median()),
        "min_return": float(r.min()),
        "max_return": float(r.max()),
        "cut_offs": int(pos["cut"].sum()),
        "negative_returns": int((r < 0).sum()),
        "margin_call_positions": int((pos["margin_calls"] > 0).sum()),
    }


EVIDENCE_STATS = {
    "positions long A short B": "positions_long_a",
    "positions short A long B": "positions_short_a",
    "mean days": "mean_days",
    "median days": "median_days",
    "weighted mean return": "weighted_mean_return",
    "median return": "median_return",
    "min return": "min_return",
    "max return": "max_return",
    "cut-off at horizon": "cut_offs",
    "negative returns": "negative_returns",
    "margin calls": "margin_call_positions",
}
# printed decimals: days one, returns three; counts exact
TOLERANCE = {"mean_days": 0.05, "median_days": 0.5, "min_days": 0.0, "max_days": 0.0}
RETURN_TOLERANCE = 0.0005


def paper_rows(root: Path, claim: str) -> dict[str, dict[str, float]]:
    ev = pd.read_csv(root / EVIDENCE)
    out: dict[str, dict[str, float]] = {}
    for r in ev[ev["claim_id"] == claim].itertuples():
        if r.statistic == "min/max days":
            lo, hi = str(r.value).split("/")
            out.setdefault(r.item, {}).update(min_days=float(lo), max_days=float(hi))
        elif r.statistic in EVIDENCE_STATS:
            out.setdefault(r.item, {})[EVIDENCE_STATS[r.statistic]] = float(r.value)
    return out


def compare(ours: dict, theirs: dict) -> list[dict]:
    rows = []
    for stat, paper in theirs.items():
        tol = TOLERANCE.get(stat, RETURN_TOLERANCE if "return" in stat else 0.0)
        diff = ours[stat] - paper
        rows.append(
            {
                "statistic": stat,
                "ours": ours[stat],
                "paper": paper,
                "difference": diff,
                "within_rounding": bool(abs(diff) <= tol + 1e-9),
            }
        )
    return rows


def table4(root: Path, pos: pd.DataFrame, benchmark: str) -> pd.DataFrame:
    paper = {normalize_name(k): v for k, v in paper_rows(root, "T4").items()}
    bench = pos[pos["strategy"] == benchmark]
    rows = []
    for twin in twins(root):
        name = load_twin_config(twin, root).paper_name
        ours = summarize(bench[bench["twin"] == twin])
        rows += [{"twin": twin, **r} for r in compare(ours, paper[normalize_name(name)])]
    rows += [{"twin": "total", **r} for r in compare(summarize(bench), paper["total"])]  # "Total"
    return pd.DataFrame(rows)


def table5(root: Path, pos: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    paper = paper_rows(root, "T5")
    rows = []
    for name in cfg.strategies:
        ours = summarize(pos[pos["strategy"] == name])
        rows += [{"strategy": name, **r} for r in compare(ours, paper[evidence_label(name)])]
    return pd.DataFrame(rows)


def evidence_label(name: str) -> str:
    """'10/5/12m' -> 'all twins 10%/5%/12 months' (the evidence CSV's item)."""
    buy, sell, horizon = name.split("/")
    horizon = {"1m": "1 month", "3m": "3 months", "12m": "12 months", "inf": "unlimited"}[horizon]
    return f"all twins {buy}%/{sell}%/{horizon}"


# ---------------------------------------------------------------- runs


def load_config(root: Path) -> DictConfig:
    return OmegaConf.load(root / CONFIG)


def variant_config(cfg: DictConfig, variant: str | None) -> DictConfig:
    base = OmegaConf.masked_copy(cfg, [k for k in cfg if k != "variants"])
    return base if variant is None else OmegaConf.merge(base, cfg.variants[variant])


def evaluate(root: Path, cfg: DictConfig, tbill: pd.Series) -> dict:
    pos, days = all_positions(root, cfg, tbill)
    return {
        "positions": pos,
        "days": days,
        "table4": table4(root, pos, cfg.benchmark),
        "table5": table5(root, pos, cfg),
    }


def run_tables45(root: Path) -> dict:
    cfg = load_config(root)
    if not (root / cfg.tbill.path).exists():
        raise FileNotFoundError(
            f"{cfg.tbill.path} missing: download FRED DTB3 and dvc add it (README, Paper 2)"
        )
    tbill = load_tbill(root / cfg.tbill.path, cfg.tbill.series)
    results = {"primary": evaluate(root, variant_config(cfg, None), tbill)}
    for variant in cfg.variants:
        results[variant] = evaluate(root, variant_config(cfg, variant), tbill)

    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "dejong.replication", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="tables45") as run:
        # Approved 1980-2002 windows (research/reports/data_decisions.md, 2026-10-07).
        mlflow.set_tags({**git, "kind": "dejong_tables45", "unlock_oos": "true"})
        mlflow.set_tag("tbill_md5", mlflow_utils.file_md5(root / cfg.tbill.path))
        for twin in twins(root):
            prov = mlflow_utils.data_provenance(
                root, str(trading_path(load_twin_config(twin, root)))
            )
            mlflow.set_tag(f"data_md5.{twin}", prov["data_md5"])
            mlflow.set_tag(f"data_matches_dvc_lock.{twin}", prov["data_matches_dvc_lock"])
        mlflow.log_params(mlflow_utils.flatten(OmegaConf.to_container(variant_config(cfg, None))))
        with tempfile.TemporaryDirectory() as tmp:
            for variant, res in results.items():
                for key in ("table4", "table5"):
                    t = res[key]
                    mlflow.log_metric(
                        f"{variant}.{key}.within_rounding", int(t.within_rounding.sum())
                    )
                    mlflow.log_metric(f"{variant}.{key}.total", len(t))
                    path = Path(tmp) / f"{variant}.{key}.csv"
                    t.to_csv(path, index=False)
                    mlflow.log_artifact(str(path))
                path = Path(tmp) / f"{variant}.positions.csv"
                res["positions"].to_csv(path, index=False)
                mlflow.log_artifact(str(path))
    return {"run_id": run.info.run_id, "results": results}


def wide(t: pd.DataFrame, index: str) -> pd.DataFrame:
    return t.pivot_table(
        index=index, columns="statistic", values=["ours", "paper"], aggfunc="first"
    )


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    out = run_tables45(Path.cwd())
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    primary = out["results"]["primary"]
    for key, index in (("table4", "twin"), ("table5", "strategy")):
        t = primary[key]
        print(f"\n{key}, primary")
        print(wide(t, index).round(3).to_string())
        print(f"{int(t.within_rounding.sum())}/{len(t)} statistics within rounding")
    print("\nTable V totals by variant (weighted mean % p.m., ours / paper):")
    for variant, res in out["results"].items():
        t = res["table5"]
        w = t[t.statistic == "weighted_mean_return"].set_index("strategy")
        cells = "  ".join(f"{s} {r.ours:.3f}/{r.paper:.3f}" for s, r in w.iterrows())
        print(f"  {variant:20s} {cells}")
    print("run_id:", out["run_id"])


if __name__ == "__main__":
    main()
