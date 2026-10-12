"""ES futures: Databento 1-minute bars to validated RTH sessions (ROADMAP step 21).

    uv run python -m quant_lab.data.es_futures --config conf/futures/es.yaml

(DVC stage ``es_ingest``.) Input: the raw DBN files of
``quant_lab.data.databento_fetch`` (rank 0 = front month, rank 1 = next, by
volume; unadjusted prices, each record with its contract's instrument_id).

Outputs:

- ``interim_path``: every bar of both ranks, UTC, unchanged values.
- ``processed_dir/rth_1m.parquet``: the front month's bars inside the NYSE
  cash session (RTH), one row per traded minute, with the session date.
- ``processed_dir/sessions.parquet``: one row per NYSE session: front
  contract, RTH open/high/low/close/volume, minute coverage, the longest run
  of missing minutes, early close, roll, the previous RTH close of the *same*
  contract (``prev_close``, the gap reference, O11) and ``usable``.
- ``processed_dir/../es.ingest.json``: the validation report (DVC metrics).

Rules (research/assumptions/deepcharts_orb.md, O2 and O11):

- RTH is the XNYS schedule (09:30-16:00 ET, early closes at 13:00), so a
  session's bars are those whose start lies in [open, close).
- A bar's timestamp is the start of its minute (Databento ``ts_event``).
- A minute without a trade has no bar; that is not an error. A session is
  ``usable`` only if the front month covers ``min_minute_coverage`` of the
  expected minutes with no missing run longer than ``max_gap_minutes``.
- The front month must not change inside a session (error). On a roll day
  ``prev_close`` comes from the new front's own previous session, when it was
  rank 1; a roll whose new front did not out-trade the old one in the previous
  RTH session is reported (Databento ranks on prior-day volume; this checks
  that the roll used no same-day information).
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from quant_lab.data.databento_fetch import raw_filename
from quant_lab.data.validation import DataValidationError, Issue

BAR_COLS = ["instrument_id", "open", "high", "low", "close", "volume"]
MINUTE = pd.Timedelta(minutes=1)


def load_raw(cfg: DictConfig, root: Path) -> pd.DataFrame:
    """All bars of all ranks: columns ts (UTC), rank, instrument_id, OHLCV."""
    import databento as db

    frames = []
    for rank, symbol in enumerate(cfg.source.symbols):
        path = root / cfg.source.raw_dir / raw_filename(symbol, cfg.source)
        df = db.DBNStore.from_file(path).to_df(map_symbols=False)
        frames.append(normalize(df, rank))
    return pd.concat(frames, ignore_index=True)


def normalize(df: pd.DataFrame, rank: int) -> pd.DataFrame:
    """Databento's frame (index ts_event) to the lab's bar columns."""
    out = df.reset_index().rename(columns={"ts_event": "ts"})[["ts", *BAR_COLS]].copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True).astype("datetime64[ns, UTC]")
    out["instrument_id"] = out["instrument_id"].astype("int64")
    out["volume"] = out["volume"].astype("int64")
    for c in ("open", "high", "low", "close"):
        out[c] = out[c].astype("float64")
    out.insert(1, "rank", rank)
    return out


def rth_schedule(calendar: str, start: str, end: str) -> pd.DataFrame:
    """NYSE sessions in [start, end): open and close (UTC) and early-close flag."""
    import exchange_calendars as xc

    last = pd.Timestamp(end) - pd.Timedelta(days=1)
    cal = xc.get_calendar(calendar, start=pd.Timestamp(start), end=last)
    s = cal.schedule.loc[pd.Timestamp(start) : last, ["open", "close"]].copy()
    s.index = pd.DatetimeIndex(s.index, name="session")
    s["open"] = s["open"].astype("datetime64[ns, UTC]")
    s["close"] = s["close"].astype("datetime64[ns, UTC]")
    s["minutes"] = ((s["close"] - s["open"]) / MINUTE).astype(int)
    s["early_close"] = s["minutes"] < 390
    return s


def assign_sessions(bars: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Bars inside an RTH session, with the session date and minute index."""
    sched = (
        schedule.reset_index()[["session", "open", "close"]]
        .rename(columns={"open": "rth_open", "close": "rth_close"})
        .sort_values("rth_open")
    )
    b = bars.sort_values("ts").reset_index(drop=True)
    m = pd.merge_asof(b, sched, left_on="ts", right_on="rth_open", direction="backward")
    inside = m["session"].notna() & (m["ts"] < m["rth_close"])
    m = m.loc[inside].copy()
    m["minute"] = ((m["ts"] - m["rth_open"]) / MINUTE).astype(int)
    return m.drop(columns=["rth_open", "rth_close"]).sort_values(["rank", "ts"], ignore_index=True)


def _days(dates, limit: int = 10) -> str:
    shown = [str(pd.Timestamp(d).date()) for d in list(dates)[:limit]]
    more = f" (+{len(dates) - limit} more)" if len(dates) > limit else ""
    return ", ".join(shown) + more


def vendor_bad_days(cfg: DictConfig, root: Path) -> frozenset[pd.Timestamp]:
    """Dates Databento marks degraded/pending/missing, from the provenance file."""
    from quant_lab.data.databento_fetch import metadata_path

    meta = json.loads(metadata_path(cfg, root).read_text())
    if "conditions" not in meta:
        raise ValueError(
            "the provenance file has no dataset conditions: rerun "
            "`python -m quant_lab.data.databento_fetch --config ... --download` "
            "(present files are not bought again)"
        )
    return frozenset(pd.Timestamp(c["date"]) for c in meta["conditions"])


def check_bars(bars: pd.DataFrame, vcfg: DictConfig) -> list[Issue]:
    issues: list[Issue] = []
    dup = bars.duplicated(["rank", "ts"]).sum()
    if dup:
        issues.append(Issue("duplicate_bars", "error", f"{dup} duplicate (rank, ts) bars"))
    p = bars[["open", "high", "low", "close"]]
    if (p <= 0).any().any() or p.isna().any().any():
        issues.append(Issue("price_values", "error", "non-positive or missing prices"))
    bad = (bars["high"] < p.max(axis=1) - 1e-9) | (bars["low"] > p.min(axis=1) + 1e-9)
    if bad.any():
        issues.append(
            Issue("ohlc_order", "error", f"{int(bad.sum())} bars with high/low outside open/close")
        )
    if (bars["volume"] < 0).any():
        issues.append(Issue("volume", "error", "negative volume"))
    return issues


def check_jumps(front: pd.DataFrame, vcfg: DictConfig) -> list[Issue]:
    """Close-to-close log moves between consecutive front bars of one session."""
    same = front["session"].eq(front["session"].shift()) & front["instrument_id"].eq(
        front["instrument_id"].shift()
    )
    r = np.log(front["close"]).diff().where(same).abs()
    issues = []
    hard = front.loc[r > vcfg.max_abs_log_return, "ts"]
    if len(hard):
        detail = f"{len(hard)} 1-minute moves above {vcfg.max_abs_log_return}: {_days(hard)}"
        issues.append(Issue("bar_jump", "error", detail))
    soft = front.loc[(r > vcfg.warn_abs_log_return) & (r <= vcfg.max_abs_log_return), "ts"]
    if len(soft):
        detail = f"{len(soft)} 1-minute moves above {vcfg.warn_abs_log_return}: {_days(soft)}"
        issues.append(Issue("bar_jump", "warning", detail))
    return issues


def longest_missing_run(minutes: np.ndarray, expected: int) -> int:
    """Longest run of minutes in [0, expected) without a bar."""
    m = np.unique(minutes)
    edges = np.concatenate(([-1], m, [expected]))
    return int((np.diff(edges) - 1).max())


def build_sessions(
    rth: pd.DataFrame,
    schedule: pd.DataFrame,
    vcfg: DictConfig,
    bad_days: frozenset[pd.Timestamp] = frozenset(),
) -> tuple[pd.DataFrame, pd.DataFrame, list[Issue]]:
    """Front-month RTH bars and the per-session table, with issues.

    ``bad_days`` are the dates the vendor marks degraded or missing; their
    sessions are kept but not ``usable``.
    """
    issues: list[Issue] = []
    front = rth.loc[rth["rank"] == 0].drop(columns="rank").reset_index(drop=True)

    contracts = front.groupby("session")["instrument_id"].nunique()
    switched = contracts.index[contracts > 1]
    if len(switched):
        days = ", ".join(str(d.date()) for d in switched[:5])
        issues.append(
            Issue("roll_inside_rth", "error", f"front month changes inside RTH on {days}")
        )

    g = front.groupby("session")
    s = pd.DataFrame(
        {
            "instrument_id": g["instrument_id"].first(),
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(),
            "bars": g.size(),
        }
    )
    s = schedule[["minutes", "early_close"]].join(s, how="left")
    missing = s.index[s["bars"].isna()]
    if len(missing):
        issues.append(
            Issue(
                "session_without_bars",
                "warning",
                f"{len(missing)} NYSE sessions without front-month bars: {_days(missing)}",
            )
        )
    s["bars"] = s["bars"].fillna(0).astype(int)
    s["coverage"] = s["bars"] / s["minutes"]
    runs = g["minute"].apply(lambda m: m.to_numpy()).to_dict()
    s["max_gap"] = [
        longest_missing_run(runs[d], n) if d in runs else n
        for d, n in zip(s.index, s["minutes"], strict=True)
    ]

    # previous RTH close of the same contract, from either rank
    closes = rth.groupby(["session", "instrument_id"])["close"].last()
    vols = rth.groupby(["session", "instrument_id"])["volume"].sum()
    prev_session = pd.Series(s.index[:-1], index=s.index[1:])
    s["prev_session"] = prev_session.reindex(s.index)
    keys = list(zip(s["prev_session"], s["instrument_id"], strict=True))
    s["prev_close"] = [
        closes.get(k, np.nan) if pd.notna(k[0]) and pd.notna(k[1]) else np.nan for k in keys
    ]
    # the front month of the last session that had bars (a session without
    # bars must not hide a roll)
    prev_front = s["instrument_id"].ffill().shift()
    s["roll"] = s["instrument_id"].notna() & prev_front.notna() & s["instrument_id"].ne(prev_front)

    late = []
    for d in s.index[s["roll"]]:
        p, new, old = s.loc[d, "prev_session"], s.loc[d, "instrument_id"], prev_front[d]
        if vols.get((p, new), 0) <= vols.get((p, old), 0):
            late.append(d)
    if late:
        days = ", ".join(str(d.date()) for d in late[:5])
        detail = (
            f"{len(late)} rolls where the new front did not out-trade the old one "
            f"in the previous RTH session: {days}"
        )
        issues.append(Issue("roll_point_in_time", "warning", detail))
    nan_prev = int((s["roll"] & s["prev_close"].isna()).sum())
    if nan_prev:
        issues.append(
            Issue(
                "roll_prev_close",
                "warning",
                f"{nan_prev} roll days without the new front's previous close",
            )
        )

    s["vendor_flagged"] = s.index.isin(list(bad_days))
    s["usable"] = (
        (s["bars"] > 0)
        & (s["coverage"] >= vcfg.min_minute_coverage)
        & (s["max_gap"] <= vcfg.max_gap_minutes)
        & ~s["vendor_flagged"]
    )
    s["instrument_id"] = s["instrument_id"].astype("Int64")
    issues += check_jumps(front, vcfg)
    return front, s.drop(columns="prev_session"), issues


def report(bars: pd.DataFrame, sessions: pd.DataFrame, issues: list[Issue]) -> dict:
    """Aggregates only (licensed data): counts and dates, no prices."""
    used = sessions[sessions["usable"]]
    return {
        "bars": int(len(bars)),
        "bars_by_rank": {
            int(k): int(v) for k, v in bars["rank"].value_counts().sort_index().items()
        },
        "sessions": int(len(sessions)),
        "sessions_usable": int(len(used)),
        "sessions_early_close": int(sessions["early_close"].sum()),
        "sessions_without_bars": int((sessions["bars"] == 0).sum()),
        "sessions_without_bars_dates": [
            str(d.date()) for d in sessions.index[sessions["bars"] == 0]
        ],
        "sessions_vendor_flagged": int(sessions["vendor_flagged"].sum()),
        "sessions_unusable_dates": [str(d.date()) for d in sessions.index[~sessions["usable"]]],
        "rolls_per_year": {
            int(y): int(n) for y, n in sessions["roll"].groupby(sessions.index.year).sum().items()
        },
        "rolls": int(sessions["roll"].sum()),
        "first_session": str(sessions.index.min().date()),
        "last_session": str(sessions.index.max().date()),
        "median_coverage": round(float(sessions["coverage"].median()), 4),
        "issues": [str(i) for i in issues],
    }


def convert(cfg: DictConfig, root: Path) -> dict:
    bars = load_raw(cfg, root)
    issues = check_bars(bars, cfg.validation)
    schedule = rth_schedule(cfg.session.calendar, cfg.source.start, cfg.source.end)
    rth = assign_sessions(bars, schedule)
    bad = vendor_bad_days(cfg, root)
    front, sessions, more = build_sessions(rth, schedule, cfg.validation, bad)
    issues += more
    rep = report(bars, sessions, issues)
    errors = [i for i in issues if i.severity == "error"]

    out_dir = root / cfg.processed_dir
    (out_dir.parent / f"{cfg.name}.ingest.json").parent.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / f"{cfg.name}.ingest.json").write_text(json.dumps(rep, indent=2) + "\n")
    if errors:
        raise DataValidationError(errors)

    interim = root / cfg.interim_path
    interim.parent.mkdir(parents=True, exist_ok=True)
    bars.to_parquet(interim, index=False)
    out_dir.mkdir(parents=True, exist_ok=True)
    front.to_parquet(out_dir / "rth_1m.parquet", index=False)
    sessions.to_parquet(out_dir / "sessions.parquet")
    return rep


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    cfg = OmegaConf.load(args.root / args.config)
    print(json.dumps(convert(cfg, args.root), indent=2))


if __name__ == "__main__":
    main()
