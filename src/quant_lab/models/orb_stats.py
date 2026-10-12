"""The course's opening-range and gap statistics on ES (ROADMAP step 22).

    uv run python -m quant_lab.models.orb_stats

Reproduces the probability claims of the DeepCharts course
(research/extraction/deepcharts_orb.md: C1-C5, C10, G1-G2) on the ES
development period, before any trade is simulated. Definitions are fixed in
``conf/orb/default.yaml`` and research/assumptions/deepcharts_orb.md:

- **Range**: high and low of the 1-minute bars in the first N minutes of RTH.
- **Breakout**: the first 5-minute bar (aligned to 09:30) after the range
  whose close is beyond the range; ``double`` when a later 5-minute close is
  beyond the other side, ``none`` when no close ever leaves the range.
- **Touch**: any 1-minute high/low beyond the range after the window.
- **Excursion**: from the trigger close, the best price in the breakout
  direction until the RTH close (and until the stop, for the stop variants).
- **Targets**: k x risk from the trigger close, risk to the range midpoint or
  the opposite side; a bar touching both counts as stopped.
- **Gap**: first RTH open vs the previous RTH close of the same contract;
  filled when RTH trades back to that close (full) or to the gap midpoint.

Only sessions up to the end of the validation period are loaded: the
out-of-sample period is never read here. Every statistic is reported on
usable sessions and on all sessions with bars (data_decisions.md), with a
Wilson 95% interval. Outputs are aggregates only (licensed data); the MLflow
run ``es.orb_stats/course_statistics`` holds the tables.
"""

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from quant_lab.tracking import mlflow_utils

STOPS = ("midpoint", "opposite")


# ---------------------------------------------------------------- inputs


def load_config(root: Path, path: str = "conf/orb/default.yaml") -> DictConfig:
    cfg = OmegaConf.load(root / path)
    cfg.futures_cfg = OmegaConf.load(root / cfg.futures)
    cfg.split_cfg = OmegaConf.load(root / cfg.split)
    return cfg


def development_end(cfg: DictConfig) -> pd.Timestamp:
    return pd.Timestamp(cfg.split_cfg.validation.end)


def period_bounds(cfg: DictConfig, period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    s = cfg.split_cfg
    if period == "development":
        return pd.Timestamp(s.train.start), pd.Timestamp(s.validation.end)
    if period in ("train", "validation"):
        return pd.Timestamp(s[period].start), pd.Timestamp(s[period].end)
    raise ValueError(f"period {period!r} is not a development period (OOS is locked)")


def load_inputs(root: Path, cfg: DictConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Front-month RTH bars and sessions up to the end of validation only."""
    proc = root / cfg.futures_cfg.processed_dir
    end = development_end(cfg)
    sessions = pd.read_parquet(proc / "sessions.parquet")
    sessions = sessions.loc[sessions.index <= end]
    bars = pd.read_parquet(
        proc / "rth_1m.parquet",
        columns=["session", "minute", "open", "high", "low", "close"],
        filters=[("session", "<=", end)],
    )
    return bars, sessions


# ---------------------------------------------------------- per session


def _first(mask: np.ndarray) -> int:
    """Index of the first True, or len(mask) when there is none."""
    hit = np.flatnonzero(mask)
    return int(hit[0]) if hit.size else len(mask)


def session_orb(
    minute: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    *,
    window: int,
    step: int,
    tick: float,
    r_multiples: list[int],
) -> dict | None:
    """Opening-range statistics of one session (bars sorted by minute)."""
    in_window = minute < window
    after = ~in_window
    if not in_window.any() or not after.any():
        return None
    rh, rl = float(high[in_window].max()), float(low[in_window].min())
    height = rh - rl
    out: dict = {
        "range_ticks": height / tick,
        "touch_up": bool((high[after] > rh).any()),
        "touch_dn": bool((low[after] < rl).any()),
        "break": "none",
    }

    # 5-minute closes after the window: last 1-minute close of each bucket
    m_a, c_a = minute[after], close[after]
    bucket = m_a // step
    last = np.flatnonzero(np.r_[bucket[1:] != bucket[:-1], True])
    b_close, b_end = c_a[last], (bucket[last] + 1) * step
    up, dn = b_close > rh, b_close < rl
    i = _first(up | dn)
    if i == len(b_close) or height <= 0:
        return out

    d = 1 if up[i] else -1
    later_other = dn[i + 1 :] if d == 1 else up[i + 1 :]
    out["break"] = "double" if later_other.any() else "single"
    out["direction"] = d
    ref = float(b_close[i])
    post = minute >= b_end[i]
    hp, lp = high[post], low[post]
    fav = (hp - ref) if d == 1 else (ref - lp)
    mfe = max(float(fav.max()), 0.0) if fav.size else 0.0
    out["mfe_ticks"] = mfe / tick
    out["mfe_height"] = mfe / height

    for stop in STOPS:
        level = (rh + rl) / 2 if stop == "midpoint" else (rl if d == 1 else rh)
        risk = d * (ref - level)
        s_idx = _first(lp <= level) if d == 1 else _first(hp >= level)
        before = fav[:s_idx]
        out[f"mfe_before_{stop}_ticks"] = (
            max(float(before.max()), 0.0) / tick if before.size else 0.0
        )
        for k in r_multiples:
            target = ref + d * k * risk
            t_idx = _first(hp >= target) if d == 1 else _first(lp <= target)
            if t_idx < s_idx:
                outcome = "target"
            elif s_idx < len(hp):
                outcome = "stop"  # includes a bar touching both (O10)
            else:
                outcome = "neither"
            out[f"{stop}_{k}R"] = outcome
    return out


def session_gap(
    minute: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    first_open: float,
    prev_close: float,
    *,
    tick: float,
    early_minutes: int,
    min_ticks: int,
) -> dict | None:
    """RTH gap of one session against the same contract's previous RTH close."""
    if not np.isfinite(prev_close):
        return None
    gap = first_open - prev_close
    if abs(gap) < min_ticks * tick - 1e-9:
        return None
    mid = prev_close + gap / 2
    early = minute < early_minutes

    def reached(level: float, mask: np.ndarray) -> bool:
        return bool((low[mask] <= level).any()) if gap > 0 else bool((high[mask] >= level).any())

    every = np.ones_like(early)
    return {
        "gap_pct": 100 * gap / prev_close,
        "gap_up": gap > 0,
        "full_fill": reached(prev_close, every),
        "mid_fill": reached(mid, every),
        "full_fill_early": reached(prev_close, early),
        "mid_fill_early": reached(mid, early),
    }


def per_session(
    bars: pd.DataFrame, sessions: pd.DataFrame, cfg: DictConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per (session, window) for the range, one per session for the gap."""
    tick = float(cfg.futures_cfg.contract.tick_size)
    orb_rows, gap_rows = [], []
    for session, g in bars.sort_values(["session", "minute"]).groupby("session", sort=True):
        m = g["minute"].to_numpy()
        h, lo, c = g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy()
        for w in cfg.range.windows:
            row = session_orb(
                m, h, lo, c,
                window=int(w), step=int(cfg.range.trigger_minutes), tick=tick,
                r_multiples=list(cfg.targets.r_multiples),
            )  # fmt: skip
            if row is not None:
                orb_rows.append({"session": session, "window": int(w), **row})
        gap = session_gap(
            m, h, lo, float(g["open"].iloc[0]), float(sessions.loc[session, "prev_close"]),
            tick=tick, early_minutes=int(cfg.gap.early_minutes), min_ticks=int(cfg.gap.min_ticks),
        )  # fmt: skip
        if gap is not None:
            gap_rows.append({"session": session, **gap})
    return pd.DataFrame(orb_rows), pd.DataFrame(gap_rows)


# ---------------------------------------------------------- aggregation


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(float(centre - half), 0.0), min(float(centre + half), 1.0)


def proportion(mask: pd.Series, **keys) -> dict:
    k, n = int(mask.sum()), int(len(mask))
    lo, hi = wilson(k, n)
    return {**keys, "k": k, "n": n, "p": k / n if n else float("nan"), "lo": lo, "hi": hi}


def orb_table(orb: pd.DataFrame, cfg: DictConfig, **keys) -> list[dict]:
    rows = []
    for w, g in orb.groupby("window"):
        k = {**keys, "window": int(w)}
        touched = g["touch_up"] | g["touch_dn"]
        rows += [
            proportion(touched, stat="p_any_side_touch", **k),
            proportion(~touched, stat="p_inside_touch", **k),
            proportion(g["break"] == "none", stat="p_inside_close", **k),
            proportion(g["break"] == "single", stat="p_single_close", **k),
            proportion(g["break"] == "double", stat="p_double_close", **k),
        ]
        b = g[g["break"] != "none"]
        for x in cfg.excursion.height_multiples:
            rows.append(proportion(b["mfe_height"] >= x, stat="p_mfe_height", x=float(x), **k))
        for t in cfg.excursion.ticks:
            rows.append(proportion(b["mfe_ticks"] >= t, stat="p_mfe_ticks", x=float(t), **k))
        q = float(cfg.excursion.quantile)
        for col in (
            "mfe_ticks",
            "mfe_height",
            "mfe_before_midpoint_ticks",
            "mfe_before_opposite_ticks",
        ):
            rows.append(
                {**k, "stat": f"q_{col}", "x": q, "n": len(b), "value": float(b[col].quantile(q))}
            )
        rows.append(
            {
                **k,
                "stat": "median_range_ticks",
                "n": len(g),
                "value": float(g["range_ticks"].median()),
            }
        )
        for stop in STOPS:
            for r in cfg.targets.r_multiples:
                col = f"{stop}_{r}R"
                rows.append(
                    proportion(b[col] == "target", stat=f"p_target_{stop}", x=float(r), **k)
                )
                rows.append(
                    proportion(b[col] == "neither", stat=f"p_neither_{stop}", x=float(r), **k)
                )
    return rows


def gap_table(gaps: pd.DataFrame, cfg: DictConfig, **keys) -> list[dict]:
    rows = []
    edges = [float(e) for e in cfg.gap.buckets_pct]
    size = gaps["gap_pct"].abs()
    groups = {"all": gaps}
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        groups[f"{lo:g}-{hi:g}%"] = gaps[(size > lo) & (size <= hi)]
    groups["gap_up"] = gaps[gaps["gap_up"]]
    groups["gap_down"] = gaps[~gaps["gap_up"]]
    for name, g in groups.items():
        for col in ("full_fill", "mid_fill", "full_fill_early", "mid_fill_early"):
            rows.append(proportion(g[col].astype(bool), stat=f"p_{col}", bucket=name, **keys))
    return rows


def claims_table(stats: pd.DataFrame, cfg: DictConfig) -> pd.DataFrame:
    rows = []
    for c in cfg.claims:
        sel = (stats["stat"] == c.stat) & (stats["universe"] == "usable")
        if "window" in c:
            sel &= stats["window"] == c.window
        else:
            sel &= stats["bucket"] == "all"
        lo_c, hi_c = (float(v) for v in c.claimed)
        for period in cfg.periods:
            r = stats[sel & (stats["period"] == period)]
            if r.empty:
                continue
            r = r.iloc[0]
            if r["hi"] < lo_c:
                verdict = "lower than claimed"
            elif r["lo"] > hi_c:
                verdict = "higher than claimed"
            else:
                verdict = "consistent"
            rows.append(
                {
                    "claim": c.id, "text": c.text, "period": period, "n": int(r["n"]),
                    "ours": r["p"], "lo": r["lo"], "hi": r["hi"],
                    "claimed": f"{lo_c:.2f}" if lo_c == hi_c else f"{lo_c:.2f}-{hi_c:.2f}",
                    "verdict": verdict,
                }
            )  # fmt: skip
    return pd.DataFrame(rows)


def compute(bars: pd.DataFrame, sessions: pd.DataFrame, cfg: DictConfig) -> dict:
    end = development_end(cfg)
    if (sessions.index > end).any() or (bars["session"] > end).any():
        raise ValueError("out-of-sample sessions passed to the development statistics")
    orb, gaps = per_session(bars, sessions, cfg)
    universes = {
        "usable": sessions.index[sessions["usable"]],
        "with_bars": sessions.index[sessions["bars"] > 0],
    }
    orb_rows, gap_rows, counts = [], [], []
    for period in cfg.periods:
        start, stop = period_bounds(cfg, period)
        for uni in cfg.universes:
            keep = universes[uni]
            keep = keep[(keep >= start) & (keep <= stop)]
            keys = {"period": period, "universe": uni}
            o = orb[orb["session"].isin(keep)]
            g = gaps[gaps["session"].isin(keep)] if len(gaps) else gaps
            orb_rows += orb_table(o, cfg, **keys)
            gap_rows += gap_table(g, cfg, **keys)
            counts.append({**keys, "sessions": len(keep), "gap_sessions": len(g)})
    orb_stats = pd.DataFrame(orb_rows)
    gap_stats = pd.DataFrame(gap_rows)
    both = pd.concat([orb_stats, gap_stats], ignore_index=True)
    return {
        "orb": orb_stats,
        "gap": gap_stats,
        "claims": claims_table(both, cfg),
        "counts": pd.DataFrame(counts),
    }


# ------------------------------------------------------------- run / CLI


def run(root: Path) -> dict:
    cfg = load_config(root)
    bars, sessions = load_inputs(root, cfg)
    out = compute(bars, sessions, cfg)

    proc = cfg.futures_cfg.processed_dir
    git = mlflow_utils.git_state(root)
    ml = OmegaConf.load(root / "conf" / "config.yaml").mlflow
    mlflow_utils.set_experiment(ml.tracking_uri, "es.orb_stats", root / ml.artifact_root)
    mlflow = mlflow_utils.mlflow
    with mlflow.start_run(run_name="course_statistics") as run_:
        mlflow.set_tags({**git, "kind": "orb_course_statistics", "unlock_oos": "false"})
        for name in ("sessions.parquet", "rth_1m.parquet"):
            prov = mlflow_utils.data_provenance(root, f"{proc}/{name}")
            mlflow.set_tags({f"{name}.{k}": v for k, v in prov.items()})
        params = OmegaConf.to_container(cfg, resolve=True)
        params.pop("claims")
        mlflow.log_params(mlflow_utils.flatten(params))
        mlflow.log_param(
            "date_range", f"{cfg.split_cfg.train.start}..{cfg.split_cfg.validation.end}"
        )
        mlflow.log_param("timeframe", "1m bars, 5m trigger")
        for r in out["claims"].itertuples():
            mlflow.log_metric(f"{r.claim}.{r.period}", float(r.ours))
        with tempfile.TemporaryDirectory() as tmp:
            for name, frame in out.items():
                path = Path(tmp) / f"{name}.csv"
                frame.to_csv(path, index=False)
                mlflow.log_artifact(str(path))
    return {"run_id": run_.info.run_id, **out}


def _table(frame: pd.DataFrame, index: str, columns: str, values: str) -> pd.DataFrame:
    """Wide view of the long statistics table (one value per cell)."""
    return frame.pivot_table(index=index, columns=columns, values=values, aggfunc="first")


def _summary(out: dict) -> str:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    o, g = out["orb"], out["gap"]
    dev = (o["period"] == "development") & (o["universe"] == "usable")
    lines = [
        f"MLflow run: {out['run_id']}",
        "",
        "Sessions:",
        out["counts"].to_string(index=False),
        "",
    ]
    lines += ["Claims vs ours (usable sessions, 95% Wilson interval):"]
    lines += [out["claims"].round(3).to_string(index=False), ""]
    core = [
        "p_any_side_touch",
        "p_inside_touch",
        "p_inside_close",
        "p_single_close",
        "p_double_close",
    ]
    t = _table(o[dev & o["stat"].isin(core)], "stat", "window", "p").loc[core]
    lines += [
        "Range statistics, development, usable (share of sessions):",
        t.round(3).to_string(),
        "",
    ]
    for stat in ("p_mfe_height", "p_target_midpoint", "p_target_opposite"):
        t = _table(o[dev & (o["stat"] == stat)], "x", "window", "p")
        lines += [
            f"{stat} by x, development, usable (share of breakouts):",
            t.round(3).to_string(),
            "",
        ]
    q = _table(o[dev & o["stat"].str.startswith(("q_", "median_"))], "stat", "window", "value")
    lines += [
        "Quantiles (30% = what 70% of breakouts reach), development, usable:",
        q.round(2).to_string(),
        "",
    ]
    gd = g[(g["period"] == "development") & (g["universe"] == "usable")]
    order = list(dict.fromkeys(gd["bucket"]))  # as defined: all, sizes, up, down
    t = _table(gd, "bucket", "stat", "p").reindex(order)
    t["n"] = gd.groupby("bucket")["n"].first().reindex(order)
    lines += ["Gap fill, development, usable:", t.round(3).to_string()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    print(_summary(run(Path.cwd())))


if __name__ == "__main__":
    main()
