"""Track-A backtest of the course's session rules on ES (ROADMAP step 23).

    uv run python -m quant_lab.backtest.orb

Rules (``conf/orb/backtest.yaml``; research/methodology/deepcharts_orb.md):

- **R1**: opening-range breakout. Range = first N minutes of RTH; the
  decision is the first 5-minute close beyond it; stop at the range midpoint
  or the opposite side; target none (RTH close), k x risk, or a 50%/100%
  range extension.
- **R1c**: R1 plus one re-entry in the other direction, on the first
  5-minute close beyond the other side after a stop-out.
- **R2**: RTH gap fade from the second minute toward the previous RTH close
  of the same contract; stop a multiple of the gap beyond the RTH open;
  exit after 60 minutes or at the close.
- **R3**: R1 only when the breakout points toward a gap that is still
  unfilled at entry; target the previous close.
- **R4**: R1 with a target at the excursion reached by (1 - q) of the
  *training-period* breakouts (step 22's definition), estimated on train
  usable sessions only.

**Execution** (``execution`` in the config):

- Market entry at the open of the first 1-minute bar after the decision
  bar's close, plus slippage.
- Stop and time exits are market orders: slippage, and a gap through the
  stop fills at the bar's open.
- A target is a resting limit that fills only when price trades through it
  by ``target_trade_through_ticks``.
- A bar that touches both stop and target is a stop (O10).
- One contract, no overnight position.

**Costs:**

- Commission per side.
- Slippage in ticks.
- Square-root impact over lagged volume and volatility (one session lag;
  no trade before ``min_sessions`` of history).
- Commission and point-value scenarios are arithmetic on the same fills;
  only a different slippage re-simulates.

The out-of-sample period is never read (``orb_stats.load_inputs``). Every
result is reported per period (train, validation, development) and per
universe (usable sessions, all sessions with bars). The pre-registered kill
criterion is evaluated on development / usable / base costs. MLflow
``es.orb_backtest/track_a``.
"""

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from quant_lab.backtest.stats import deflated_sharpe_ratio, sharpe
from quant_lab.models import orb_stats
from quant_lab.tracking import mlflow_utils

# ----------------------------------------------------------------- config


def load_config(root: Path, path: str = "conf/orb/backtest.yaml") -> DictConfig:
    cfg = OmegaConf.load(root / path)
    cfg.futures_cfg = OmegaConf.load(root / cfg.futures)
    cfg.split_cfg = OmegaConf.load(root / cfg.split)
    cfg.stats_cfg = OmegaConf.load(root / cfg.stats)
    return cfg


def configs(cfg: DictConfig) -> list[dict]:
    """Every rule configuration (the trials counted by the deflated Sharpe ratio)."""
    r = cfg.rules
    out = []
    for w in r.R1.windows:
        for s in r.R1.stops:
            for t in r.R1.targets:
                out.append({"rule": "R1", "window": int(w), "stop": s, "target": t})
    for w in r.R1c.windows:
        for s in r.R1c.stops:
            for t in r.R1c.targets:
                out.append({"rule": "R1c", "window": int(w), "stop": s, "target": t})
    for k in r.R2.stop_gap_multiples:
        for e in r.R2.exit_minutes:
            out.append(
                {
                    "rule": "R2",
                    "window": 0,
                    "stop": f"{float(k)}gap",
                    "target": "prev_close",
                    "exit": str(e),
                }
            )
    for w in r.R3.windows:
        for s in r.R3.stops:
            out.append({"rule": "R3", "window": int(w), "stop": s, "target": "prev_close"})
    for w in r.R4.windows:
        for s in r.R4.stops:
            for q in r.R4.quantiles:
                out.append({"rule": "R4", "window": int(w), "stop": s, "target": f"q{float(q)}"})
    for c in out:
        c.setdefault("exit", "close")
        c["family"] = f"{c['rule']}|{c['stop']}|{c['target']}|{c['exit']}"
        c["id"] = f"{c['family']}|{c['window']}"
    return out


# -------------------------------------------------------------- execution


@dataclass(frozen=True)
class Exec:
    tick: float
    slippage_ticks: float
    trade_through_ticks: float


def simulate(
    minute: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    lo: np.ndarray,
    c: np.ndarray,
    *,
    entry_minute: int,
    d: int,
    stop: float,
    target,
    exit_minute: int | None,
    ex: Exec,
) -> dict | None:
    """One trade on one session's bars (sorted by minute).

    ``target`` is None, a price, or a callable of the entry fill (k x risk).
    Returns fills in price points per contract, before commission and impact.
    """
    i0 = int(np.searchsorted(minute, entry_minute))
    end = len(minute) if exit_minute is None else int(np.searchsorted(minute, exit_minute))
    if i0 >= end:
        return None
    slip = ex.slippage_ticks * ex.tick
    entry = float(o[i0]) + d * slip
    risk = d * (entry - stop)
    if risk <= 0:
        return None
    tgt = target(entry, risk) if callable(target) else target
    hh, ll, oo = h[i0:end], lo[i0:end], o[i0:end]
    stop_hit = (ll <= stop) if d == 1 else (hh >= stop)
    js = orb_stats._first(stop_hit)
    jt = len(hh)
    if tgt is not None:
        thru = ex.trade_through_ticks * ex.tick
        tgt_hit = (hh >= tgt + thru) if d == 1 else (ll <= tgt - thru)
        jt = orb_stats._first(tgt_hit)
    if js <= jt and js < len(hh):
        j, reason = js, "stop"
        level = min(float(oo[j]), stop) if d == 1 else max(float(oo[j]), stop)
        if j == 0:
            level = stop
        fill = level - d * slip
    elif jt < len(hh):
        j, reason = jt, "target"
        if j == 0 and d * (tgt - float(oo[0])) <= 0:
            # the target is already passed at entry: the limit is marketable and
            # exits at the market on the entry bar's open (audit RT-1)
            fill = float(oo[0]) - d * slip
        elif j == 0:
            fill = tgt
        else:
            fill = max(float(oo[j]), tgt) if d == 1 else min(float(oo[j]), tgt)
    else:
        j, reason = len(hh) - 1, "time"
        fill = float(c[i0 + j]) - d * slip
    return {
        "direction": d,
        "entry_minute": int(minute[i0]),
        "exit_minute": int(minute[i0 + j]),
        "reason": reason,
        "risk_pts": risk,
        "fill_pts": d * (fill - entry),
    }


# ---------------------------------------------------------------- signals


@dataclass
class Range:
    high: float
    low: float
    b_close: np.ndarray  # 5-minute closes after the window
    b_end: np.ndarray  # minute at which each 5-minute bar has closed


def opening_range(minute, h, lo, c, window: int, step: int) -> Range | None:
    inside = minute < window
    after = ~inside
    if not inside.any() or not after.any():
        return None
    m_a, c_a = minute[after], c[after]
    bucket = m_a // step
    last = np.flatnonzero(np.r_[bucket[1:] != bucket[:-1], True])
    rh, rl = float(h[inside].max()), float(lo[inside].min())
    if rh <= rl:
        return None
    return Range(rh, rl, c_a[last], (bucket[last] + 1) * step)


def first_break(
    rng: Range, after_minute: int = -1, side: int | None = None
) -> tuple[int, int, float] | None:
    """(direction, decision minute, trigger close) of the first 5-minute close
    beyond the range that closes after ``after_minute`` (and on ``side``)."""
    ok = rng.b_end > after_minute
    up = (rng.b_close > rng.high) & ok
    dn = (rng.b_close < rng.low) & ok
    if side == 1:
        dn = np.zeros_like(dn)
    elif side == -1:
        up = np.zeros_like(up)
    i = orb_stats._first(up | dn)
    if i == len(rng.b_close):
        return None
    return (1 if up[i] else -1), int(rng.b_end[i]), float(rng.b_close[i])


def stop_level(rng: Range, d: int, kind: str) -> float:
    if kind == "midpoint":
        return (rng.high + rng.low) / 2
    return rng.low if d == 1 else rng.high


def target_spec(rng: Range, d: int, kind: str, ref: float, q_height: dict | None, window: int):
    if kind == "none":
        return None
    if kind.endswith("R"):
        k = float(kind[:-1])
        return lambda entry, risk: entry + d * k * risk
    height = rng.high - rng.low
    edge = rng.high if d == 1 else rng.low
    if kind == "ext50":
        return edge + d * 0.5 * height
    if kind == "ext100":
        return edge + d * 1.0 * height
    if kind.startswith("q"):
        return ref + d * q_height[(window, float(kind[1:]))] * height
    raise ValueError(f"unknown target {kind!r}")


def session_trades(
    arrays: tuple,
    ranges: dict[int, Range | None],
    prev_close: float,
    conf: dict,
    ex: Exec,
    *,
    step: int,
    min_gap_ticks: int,
    q_height: dict | None,
) -> list[dict]:
    minute, o, h, lo, c = arrays
    rule = conf["rule"]
    if rule == "R2":
        return _gap_fade(arrays, prev_close, conf, ex, min_gap_ticks)
    rng = ranges.get(conf["window"])
    if rng is None:
        return []
    brk = first_break(rng)
    if brk is None:
        return []
    d, t_min, ref = brk
    if rule == "R3":
        gap = _gap(minute, o, prev_close, ex.tick, min_gap_ticks)
        if gap is None or d != -int(np.sign(gap)):
            return []
        before = minute < t_min
        filled = (lo[before] <= prev_close).any() if gap > 0 else (h[before] >= prev_close).any()
        if filled:
            return []
        tgt = prev_close
    else:
        tgt = target_spec(rng, d, conf["target"], ref, q_height, conf["window"])
    t = simulate(
        minute, o, h, lo, c, entry_minute=t_min, d=d, stop=stop_level(rng, d, conf["stop"]),
        target=tgt, exit_minute=None, ex=ex,
    )  # fmt: skip
    trades = [t] if t else []
    if rule == "R1c" and t and t["reason"] == "stop":
        again = first_break(rng, after_minute=t["exit_minute"], side=-d)
        if again is not None:
            d2, t2, ref2 = again
            tgt2 = target_spec(rng, d2, conf["target"], ref2, q_height, conf["window"])
            t_b = simulate(
                minute, o, h, lo, c, entry_minute=t2, d=d2, stop=stop_level(rng, d2, conf["stop"]),
                target=tgt2, exit_minute=None, ex=ex,
            )  # fmt: skip
            if t_b:
                trades.append(t_b)
    return trades


def _gap(minute, o, prev_close: float, tick: float, min_gap_ticks: int) -> float | None:
    if not np.isfinite(prev_close) or minute[0] != 0:
        return None
    gap = float(o[0]) - prev_close
    return gap if abs(gap) >= min_gap_ticks * tick - 1e-9 else None


def _gap_fade(arrays, prev_close, conf, ex: Exec, min_gap_ticks: int) -> list[dict]:
    minute, o, h, lo, c = arrays
    gap = _gap(minute, o, prev_close, ex.tick, min_gap_ticks)
    if gap is None:
        return []
    s = int(np.sign(gap))
    if (lo[0] <= prev_close) if s > 0 else (h[0] >= prev_close):
        return []  # filled within the opening minute: nothing left to fade
    k = float(conf["stop"].removesuffix("gap"))
    stop = float(o[0]) + s * k * abs(gap)
    exit_minute = None if conf["exit"] == "close" else int(conf["exit"])
    t = simulate(
        minute, o, h, lo, c, entry_minute=1, d=-s, stop=stop, target=prev_close,
        exit_minute=exit_minute, ex=ex,
    )  # fmt: skip
    return [t] if t else []


# ------------------------------------------------------------------ costs


def impact_points(sessions: pd.DataFrame, cfg: DictConfig) -> pd.Series:
    """Per-side square-root impact in index points for one contract, from
    statistics lagged by one session; NaN during the warm-up (no trading).

    Computed over the sessions that have bars, so that a session without
    bars does not blank the next ones through the rolling window (audit RT-8).
    """
    ic = cfg.costs.impact
    s = sessions[sessions["volume"].notna() & sessions["close"].notna()]
    ret = np.log(s["close"] / s["prev_close"])
    sigma = ret.rolling(ic.vol_lookback_sessions, min_periods=ic.min_sessions).std().shift(1)
    adv = s["volume"].rolling(ic.adv_lookback_sessions, min_periods=ic.min_sessions).mean().shift(1)
    q = float(cfg.execution.contracts)
    impact = ic.coefficient * sigma * s["close"].shift(1) * np.sqrt(q / adv)
    return impact.reindex(sessions.index)


def scenario_costs(cfg: DictConfig, name: str) -> dict:
    base = OmegaConf.to_container(cfg.costs.base)
    over = OmegaConf.to_container(cfg.costs.scenarios[name])
    return {**base, "impact_off": False, **over}


# ------------------------------------------------------------- simulation


def run_trades(
    bars: pd.DataFrame,
    sessions: pd.DataFrame,
    cfg: DictConfig,
    slippage_ticks: float,
    q_height: dict,
) -> pd.DataFrame:
    """Every configuration's trades at one slippage level (fills before commission/impact)."""
    tick = float(cfg.futures_cfg.contract.tick_size)
    step = int(cfg.execution.trigger_minutes)
    ex = Exec(tick, float(slippage_ticks), float(cfg.execution.target_trade_through_ticks))
    confs = configs(cfg)
    windows = sorted({c["window"] for c in confs if c["window"]})
    impact = impact_points(sessions, cfg)
    rows = []
    for session, g in bars.sort_values(["session", "minute"]).groupby("session", sort=True):
        if not np.isfinite(impact.get(session, np.nan)):
            continue  # warm-up: cost statistics not yet available
        arrays = tuple(g[col].to_numpy() for col in ("minute", "open", "high", "low", "close"))
        ranges = {
            w: opening_range(arrays[0], arrays[2], arrays[3], arrays[4], w, step) for w in windows
        }
        prev_close = float(sessions.loc[session, "prev_close"])
        for conf in confs:
            for t in session_trades(
                arrays, ranges, prev_close, conf, ex, step=step,
                min_gap_ticks=int(cfg.rules.R2.min_gap_ticks), q_height=q_height,
            ):  # fmt: skip
                rows.append({"session": session, "id": conf["id"], **t})
    trades = pd.DataFrame(rows)
    if len(trades):
        trades["impact_pts"] = trades["session"].map(impact)
    return trades


def train_excursion_quantiles(bars: pd.DataFrame, sessions: pd.DataFrame, cfg: DictConfig) -> dict:
    """R4 targets: quantiles of the trigger-to-close excursion (range heights)
    of TRAIN usable breakouts only, per window."""
    start, stop = orb_stats.period_bounds(cfg, "train")
    keep = sessions.index[sessions["usable"] & (sessions.index >= start) & (sessions.index <= stop)]
    stats_cfg = cfg.stats_cfg.copy()
    stats_cfg.range.windows = list(cfg.rules.R4.windows)
    stats_cfg.futures_cfg = cfg.futures_cfg
    orb, _ = orb_stats.per_session(bars[bars["session"].isin(keep)], sessions, stats_cfg)
    br = orb[orb["break"] != "none"]
    return {
        (int(w), float(q)): float(br.loc[br["window"] == w, "mfe_height"].quantile(q))
        for w in cfg.rules.R4.windows
        for q in cfg.rules.R4.quantiles
    }


# ------------------------------------------------------------ evaluation


def net_usd(trades: pd.DataFrame, costs: dict) -> pd.Series:
    pv = float(costs["point_value"])
    impact = 0.0 if costs["impact_off"] else 2 * trades["impact_pts"] * pv
    return trades["fill_pts"] * pv - 2 * float(costs["commission_per_side_usd"]) - impact


def metrics(t: pd.DataFrame, days: pd.Index, ann: int) -> dict:
    """Per-trade and daily statistics of one configuration's trades (USD, 1 contract)."""
    daily = t.groupby("session")["net_usd"].sum().reindex(days, fill_value=0.0)
    equity = daily.cumsum()
    wins, losses = (
        t.loc[t["net_usd"] > 0, "net_usd"].sum(),
        -t.loc[t["net_usd"] < 0, "net_usd"].sum(),
    )
    n = len(t)
    std = t["net_usd"].std(ddof=1) if n > 1 else np.nan
    return {
        "trades": n,
        "sessions": len(days),
        "win_rate": float((t["net_usd"] > 0).mean()) if n else np.nan,
        "mean_usd": float(t["net_usd"].mean()) if n else np.nan,
        "t_stat": float(t["net_usd"].mean() / std * np.sqrt(n)) if n > 1 and std > 0 else np.nan,
        "mean_R": float((t["fill_pts"] / t["risk_pts"]).mean()) if n else np.nan,
        "total_usd": float(t["net_usd"].sum()),
        "sharpe_ann": sharpe(daily) * np.sqrt(ann),
        "max_dd_usd": float((equity - equity.cummax()).min()) if len(equity) else 0.0,
        "profit_factor": float(wins / losses) if losses > 0 else np.nan,
        "share_stop": float((t["reason"] == "stop").mean()) if n else np.nan,
        "share_target": float((t["reason"] == "target").mean()) if n else np.nan,
        "share_time": float((t["reason"] == "time").mean()) if n else np.nan,
    }


def evaluate(trades_by_slip: dict, sessions: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    confs = {c["id"]: c for c in configs(cfg)}
    universes = {"usable": sessions["usable"], "with_bars": sessions["bars"] > 0}
    ann = int(cfg.kill.annualization)
    rows = []
    for scn in cfg.costs.scenarios:
        costs = scenario_costs(cfg, scn)
        trades = trades_by_slip[float(costs["slippage_ticks"])].copy()
        trades["net_usd"] = net_usd(trades, costs)
        by_id = dict(tuple(trades.groupby("id")))
        for period in cfg.periods:
            start, stop = orb_stats.period_bounds(cfg, period)
            for uni, mask in universes.items():
                days = sessions.index[mask & (sessions.index >= start) & (sessions.index <= stop)]
                for cid, conf in confs.items():
                    t = by_id.get(cid, trades.iloc[:0])
                    t = t[t["session"].isin(days)]
                    rows.append(
                        {
                            "scenario": scn,
                            "period": period,
                            "universe": uni,
                            **conf,
                            **metrics(t, days, ann),
                        }
                    )
    return pd.DataFrame(rows)


def deflate(trades_by_slip: dict, sessions: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    """Deflated Sharpe ratio per configuration: development, usable, base costs,
    against all configurations as trials (variance of their daily SRs)."""
    costs = scenario_costs(cfg, "base")
    trades = trades_by_slip[float(costs["slippage_ticks"])].copy()
    trades["net_usd"] = net_usd(trades, costs)
    start, stop = orb_stats.period_bounds(cfg, "development")
    days = sessions.index[sessions["usable"] & (sessions.index >= start) & (sessions.index <= stop)]
    trades = trades[trades["session"].isin(days)]
    daily = {
        cid: trades[trades["id"] == cid]
        .groupby("session")["net_usd"]
        .sum()
        .reindex(days, fill_value=0.0)
        for cid in (c["id"] for c in configs(cfg))
    }
    srs = np.array([sharpe(s) for s in daily.values()])
    var_sr = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
    rows = [{"id": cid, **deflated_sharpe_ratio(s, len(daily), var_sr)} for cid, s in daily.items()]
    return pd.DataFrame(rows)


def kill_verdicts(results: pd.DataFrame, dsr: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    base = results[
        (results["scenario"] == "base")
        & (results["period"] == "development")
        & (results["universe"] == "usable")
    ].merge(dsr[["id", "dsr"]], on="id")
    rows = []
    for fam, g in base.groupby("family", sort=False):
        positive = bool((g["mean_usd"] > 0).all())
        deflated = bool((g["dsr"] > cfg.kill.dsr_threshold).all())
        rows.append(
            {
                "family": fam,
                "windows": ",".join(str(w) for w in g["window"]),
                "min_mean_usd": float(g["mean_usd"].min()),
                "max_mean_usd": float(g["mean_usd"].max()),
                "min_dsr": float(g["dsr"].min()),
                "all_positive": positive,
                "all_dsr_above": deflated,
                "survives": positive and deflated,
            }
        )
    return pd.DataFrame(rows)


def compute(bars: pd.DataFrame, sessions: pd.DataFrame, cfg: DictConfig) -> dict:
    end = orb_stats.development_end(cfg)
    if (sessions.index > end).any() or (bars["session"] > end).any():
        raise ValueError("out-of-sample sessions passed to the development backtest")
    q_height = train_excursion_quantiles(bars, sessions, cfg)
    slips = sorted({float(scenario_costs(cfg, s)["slippage_ticks"]) for s in cfg.costs.scenarios})
    trades_by_slip = {s: run_trades(bars, sessions, cfg, s, q_height) for s in slips}
    results = evaluate(trades_by_slip, sessions, cfg)
    dsr = deflate(trades_by_slip, sessions, cfg)
    return {
        "results": results,
        "dsr": dsr,
        "verdicts": kill_verdicts(results, dsr, cfg),
        "q_height": q_height,
        "n_trials": len(configs(cfg)),
    }


# --------------------------------------------------------------- run / CLI


def run(root: Path) -> dict:
    cfg = load_config(root)
    bars, sessions = load_inputs(root, cfg)
    out = compute(bars, sessions, cfg)

    proc = cfg.futures_cfg.processed_dir
    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "es.orb_backtest", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="track_a") as run_:
        mlflow.set_tags({**git, "kind": "orb_track_a", "unlock_oos": "false"})
        for name in ("sessions.parquet", "rth_1m.parquet"):
            prov = mlflow_utils.data_provenance(root, f"{proc}/{name}")
            mlflow.set_tags({f"{name}.{k}": v for k, v in prov.items()})
        params = OmegaConf.to_container(cfg, resolve=True)
        params.pop("stats_cfg")
        mlflow.log_params(mlflow_utils.flatten(params))
        mlflow.log_params(
            {
                "date_range": f"{cfg.split_cfg.train.start}..{cfg.split_cfg.validation.end}",
                "timeframe": "1m bars, 5m decision",
                "execution_model": (
                    "next 1m open market entry; stop/time market; target limit with trade-through"
                ),
                "position_sizing": f"{cfg.execution.contracts} contract, intraday",
                "leverage": "not modelled (P&L per contract)",
                "n_trials": out["n_trials"],
            }
        )
        for (w, q), v in out["q_height"].items():
            mlflow.log_param(f"R4.q_height.{w}.{q}", round(v, 4))
        base = out["results"].query(
            "scenario == 'base' and period == 'development' and universe == 'usable'"
        )
        mlflow.log_metric("trades_total_dev_usable_base", int(base["trades"].sum()))
        mlflow.log_metric("families_surviving", int(out["verdicts"]["survives"].sum()))
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("results", "dsr", "verdicts"):
                path = Path(tmp) / f"{name}.csv"
                out[name].to_csv(path, index=False)
                mlflow.log_artifact(str(path))
    return {"run_id": run_.info.run_id, **out}


def load_inputs(root: Path, cfg: DictConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Development-period bars and sessions only (orb_stats never reads OOS)."""
    bars, sessions = orb_stats.load_inputs(root, cfg)
    return bars, sessions


def _summary(out: dict) -> str:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 200)
    r = out["results"]
    lines = [f"MLflow run: {out['run_id']}", f"trials (configurations): {out['n_trials']}", ""]
    lines += ["R4 targets from TRAIN excursions (range heights):"]
    lines += [f"  window {w}, q {q}: {v:.3f}" for (w, q), v in out["q_height"].items()]
    lines += ["", "Kill criterion (development, usable, base costs; every window):"]
    lines += [out["verdicts"].round(3).to_string(index=False), ""]
    for period in ("train", "validation", "development"):
        sel = r.query("scenario == 'base' and universe == 'usable' and period == @period")
        t = sel.pivot_table(
            index="family", columns="window", values="mean_usd", aggfunc="first", sort=False
        )
        n = sel.pivot_table(
            index="family", columns="window", values="trades", aggfunc="first", sort=False
        )
        lines += [f"Mean net USD per trade, {period}, usable, base costs (trades in brackets):"]
        cell = t.round(1).astype(str) + " (" + n.fillna(0).astype(int).astype(str) + ")"
        lines += [cell.where(n.notna(), "").to_string(), ""]  # R2 has no window
    dev = r.query("period == 'development' and universe == 'usable'")
    s = dev.groupby("scenario", sort=False).agg(
        configs=("id", "size"),
        positive=("mean_usd", lambda x: int((x > 0).sum())),
        median_mean_usd=("mean_usd", "median"),
        best_mean_usd=("mean_usd", "max"),
        median_sharpe=("sharpe_ann", "median"),
    )
    lines += [
        "Cost scenarios, development, usable (all configurations):",
        s.round(2).to_string(),
        "",
    ]
    both = r.query("scenario == 'base' and period == 'development'").pivot_table(
        index="id", columns="universe", values="mean_usd", aggfunc="first"
    )
    diff = (both["with_bars"] - both["usable"]).abs()
    lines += [f"Both ways: max |mean USD/trade| difference usable vs with_bars: {diff.max():.2f}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    print(_summary(run(Path.cwd())))


if __name__ == "__main__":
    main()
