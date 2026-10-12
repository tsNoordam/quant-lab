"""ES ingest on synthetic minute bars: RTH boundaries (DST, early close),
coverage, rolls and the same-contract previous close (O2, O11)."""

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from quant_lab.data import es_futures as es

VCFG = OmegaConf.create(
    {
        "min_minute_coverage": 0.98,
        "max_gap_minutes": 5,
        "warn_abs_log_return": 0.02,
        "max_abs_log_return": 0.08,
    }
)
A, B = 101, 202  # instrument ids: old and new front month


@pytest.fixture(scope="module")
def schedule():
    return es.rth_schedule("XNYS", "2019-03-07", "2019-12-03")


def minute_bars(schedule, day, *, rank, instrument, base, eth=30, drop=(), volume=100):
    """One bar per minute from ``eth`` minutes before the open to ``eth`` after the close."""
    row = schedule.loc[pd.Timestamp(day)]
    ts = pd.date_range(
        row["open"] - eth * es.MINUTE, row["close"] + eth * es.MINUTE, freq="1min", inclusive="left"
    )
    keep = [t for t in ts if int((t - row["open"]) / es.MINUTE) not in set(drop)]
    n = len(keep)
    close = base + 0.25 * np.arange(n)
    return pd.DataFrame(
        {
            "ts": pd.DatetimeIndex(keep).astype("datetime64[ns, UTC]"),
            "rank": rank,
            "instrument_id": instrument,
            "open": close - 0.25,
            "high": close + 0.25,
            "low": close - 0.5,
            "close": close,
            "volume": volume,
        }
    )


def run(bars, schedule, days):
    sched = schedule.loc[[pd.Timestamp(d) for d in days]]
    rth = es.assign_sessions(bars, sched)
    return es.build_sessions(rth, sched, VCFG)


def test_schedule_follows_dst_and_early_closes(schedule):
    assert schedule.loc["2019-03-08", "open"] == pd.Timestamp("2019-03-08 14:30", tz="UTC")
    assert schedule.loc["2019-03-11", "open"] == pd.Timestamp("2019-03-11 13:30", tz="UTC")
    assert schedule.loc["2019-11-29", "minutes"] == 210
    assert schedule.loc["2019-11-29", "early_close"]
    assert not schedule.loc["2019-11-27", "early_close"]
    assert pd.Timestamp("2019-11-28") not in schedule.index  # Thanksgiving


def test_rth_excludes_eth_and_the_closing_minute(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    rth = es.assign_sessions(bars, schedule.loc[["2019-03-11"]])
    local = rth["ts"].dt.tz_convert("America/New_York")
    assert local.min().strftime("%H:%M") == "09:30"
    assert local.max().strftime("%H:%M") == "15:59"
    assert len(rth) == 390
    assert rth["minute"].tolist() == list(range(390))


def test_session_ohlc_comes_from_rth_bars_only(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    front, s, issues = run(bars, schedule, ["2019-03-11"])
    rth = front.sort_values("ts")
    row = s.loc["2019-03-11"]
    assert row["open"] == rth["open"].iloc[0]
    assert row["close"] == rth["close"].iloc[-1]
    assert row["high"] == rth["high"].max() and row["low"] == rth["low"].min()
    assert row["usable"] and row["coverage"] == 1.0 and row["max_gap"] == 0
    assert not [i for i in issues if i.severity == "error"]


def test_early_close_session_is_complete_at_210_minutes(schedule):
    bars = minute_bars(schedule, "2019-11-29", rank=0, instrument=A, base=3150)
    _, s, _ = run(bars, schedule, ["2019-11-29"])
    assert s.loc["2019-11-29", "bars"] == 210
    assert s.loc["2019-11-29", "usable"]


def test_coverage_rules(schedule):
    scattered = minute_bars(
        schedule, "2019-03-11", rank=0, instrument=A, base=2800, drop=(10, 50, 200)
    )
    run_of_six = minute_bars(
        schedule, "2019-03-12", rank=0, instrument=A, base=2800, drop=range(100, 106)
    )
    late_start = minute_bars(
        schedule, "2019-03-13", rank=0, instrument=A, base=2800, drop=range(0, 6)
    )
    _, s, _ = run(
        pd.concat([scattered, run_of_six, late_start]),
        schedule,
        ["2019-03-11", "2019-03-12", "2019-03-13"],
    )
    assert s.loc["2019-03-11", "usable"] and s.loc["2019-03-11", "max_gap"] == 1
    assert s.loc["2019-03-12", "max_gap"] == 6 and not s.loc["2019-03-12", "usable"]
    assert s.loc["2019-03-13", "max_gap"] == 6 and not s.loc["2019-03-13", "usable"]


def test_roll_uses_the_new_fronts_own_previous_close(schedule):
    day1, day2 = "2019-03-11", "2019-03-12"
    bars = pd.concat(
        [
            minute_bars(schedule, day1, rank=0, instrument=A, base=2800, volume=100),
            minute_bars(schedule, day1, rank=1, instrument=B, base=2810, volume=300),
            minute_bars(schedule, day2, rank=0, instrument=B, base=2820),
        ]
    )
    front, s, issues = run(bars, schedule, [day1, day2])
    assert s.loc[day2, "roll"] and not s.loc[day1, "roll"]
    rth = es.assign_sessions(bars, schedule.loc[[day1]])
    b_close_day1 = rth[(rth["instrument_id"] == B)]["close"].iloc[-1]
    assert s.loc[day2, "prev_close"] == b_close_day1
    assert front["instrument_id"].tolist().count(B) == 390
    assert not [i for i in issues if i.check == "roll_point_in_time"]


def test_roll_without_volume_lead_is_reported(schedule):
    day1, day2 = "2019-03-11", "2019-03-12"
    bars = pd.concat(
        [
            minute_bars(schedule, day1, rank=0, instrument=A, base=2800, volume=300),
            minute_bars(schedule, day1, rank=1, instrument=B, base=2810, volume=100),
            minute_bars(schedule, day2, rank=0, instrument=B, base=2820),
        ]
    )
    _, _, issues = run(bars, schedule, [day1, day2])
    assert [i for i in issues if i.check == "roll_point_in_time" and i.severity == "warning"]


def test_front_month_change_inside_rth_is_an_error(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    bars.loc[bars.index[-60:], "instrument_id"] = B
    _, _, issues = run(bars, schedule, ["2019-03-11"])
    assert [i for i in issues if i.check == "roll_inside_rth" and i.severity == "error"]


def test_bad_print_is_an_error(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    i = bars.index[100]
    bars.loc[i, ["open", "high", "low", "close"]] = [2800 * 1.2] * 4
    _, _, issues = run(bars, schedule, ["2019-03-11"])
    assert [x for x in issues if x.check == "bar_jump" and x.severity == "error"]


def test_check_bars_catches_inconsistent_ohlc(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    bars.loc[bars.index[5], "high"] = 1.0
    issues = es.check_bars(bars, VCFG)
    assert [i for i in issues if i.check == "ohlc_order"]
    assert not es.check_bars(
        minute_bars(schedule, "2019-03-12", rank=0, instrument=A, base=2800), VCFG
    )


def test_missing_session_is_a_warning_not_usable(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    _, s, issues = run(bars, schedule, ["2019-03-11", "2019-03-12"])
    assert s.loc["2019-03-12", "bars"] == 0 and not s.loc["2019-03-12", "usable"]
    assert [i for i in issues if i.check == "session_without_bars" and i.severity == "warning"]


def test_normalize_databento_frame():
    idx = pd.DatetimeIndex(["2019-03-11 13:30", "2019-03-11 13:31"], tz="UTC", name="ts_event")
    raw = pd.DataFrame(
        {
            "rtype": 33,
            "publisher_id": 1,
            "instrument_id": np.array([A, A], dtype="uint32"),
            "open": [2800.0, 2800.25],
            "high": [2800.5, 2800.5],
            "low": [2799.75, 2800.0],
            "close": [2800.25, 2800.5],
            "volume": np.array([10, 20], dtype="uint64"),
        },
        index=idx,
    )
    out = es.normalize(raw, rank=1)
    assert out.columns.tolist() == ["ts", "rank", *es.BAR_COLS]
    assert out["rank"].eq(1).all() and str(out["ts"].dtype) == "datetime64[ns, UTC]"
    assert out["volume"].dtype == "int64"


def write_dbn(path, bars):
    """Synthetic bars as a Databento DBN file (zstd), as the vendor delivers them."""
    import databento_dbn as dbn
    import zstandard

    ns = bars["ts"].astype("int64")
    meta = dbn.Metadata(
        dataset="GLBX.MDP3",
        start=int(ns.min()),
        end=int(ns.max()) + 60_000_000_000,
        stype_in=dbn.SType.CONTINUOUS,
        stype_out=dbn.SType.INSTRUMENT_ID,
        schema=dbn.Schema.OHLCV_1M,
        symbols=[],
        partial=[],
        not_found=[],
        mappings=[],
    )
    raw = bytearray(meta.encode())
    fx = 1_000_000_000
    for t, r in zip(ns, bars.itertuples(), strict=True):
        px = [round(v * fx) for v in (r.open, r.high, r.low, r.close)]
        msg = dbn.OHLCVMsg(dbn.RType.OHLCV_1M, 1, int(r.instrument_id), int(t), *px, int(r.volume))
        raw += bytes(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstandard.ZstdCompressor().compress(bytes(raw)))


def test_convert_end_to_end_from_dbn_files(schedule, tmp_path):
    from quant_lab.data.databento_fetch import raw_filename

    cfg = OmegaConf.create(
        {
            "name": "es",
            "source": {
                "dataset": "GLBX.MDP3",
                "schema": "ohlcv-1m",
                "stype_in": "continuous",
                "symbols": ["ES.v.0", "ES.v.1"],
                "start": "2019-03-11",
                "end": "2019-03-13",
                "raw_dir": "raw",
            },
            "session": {"calendar": "XNYS", "tz": "America/New_York"},
            "validation": OmegaConf.to_container(VCFG),
            "interim_path": "interim/es/bars_1m.parquet",
            "processed_dir": "processed/es",
        }
    )
    rank0 = pd.concat(
        [
            minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800, volume=100),
            minute_bars(schedule, "2019-03-12", rank=0, instrument=B, base=2820),
        ]
    )
    rank1 = minute_bars(schedule, "2019-03-11", rank=1, instrument=B, base=2810, volume=300)
    for symbol, bars in (("ES.v.0", rank0), ("ES.v.1", rank1)):
        write_dbn(tmp_path / "raw" / raw_filename(symbol, cfg.source), bars)

    rep = es.convert(cfg, tmp_path)
    assert rep["sessions"] == 2 and rep["sessions_usable"] == 2 and rep["rolls"] == 1
    assert rep["bars"] == len(rank0) + len(rank1)
    s = pd.read_parquet(tmp_path / "processed/es/sessions.parquet")
    rth1 = pd.read_parquet(tmp_path / "processed/es/rth_1m.parquet")
    assert len(rth1) == 780
    assert s.loc["2019-03-12", "prev_close"] == pytest.approx(rank1["close"].iloc[30 + 389])
    assert (tmp_path / "processed/es.ingest.json").exists()
    assert (tmp_path / "interim/es/bars_1m.parquet").exists()


def test_report_holds_no_prices(schedule):
    bars = minute_bars(schedule, "2019-03-11", rank=0, instrument=A, base=2800)
    _, s, issues = run(bars, schedule, ["2019-03-11"])
    rep = es.report(bars, s, issues)
    text = str(rep)
    assert "2800" not in text and "2801" not in text
    assert rep["sessions_usable"] == 1
