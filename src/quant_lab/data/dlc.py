"""DVC stage: DLC workbooks -> paper-convention twin panels (de Jong, Rosenthal &
van Dijk 2009; ROADMAP step 14).

    uv run python -m quant_lab.data.dlc --twin rd_shell

Reads the original archive in ``data/raw/datastream_dlc/`` (zipped legacy .xls)
and writes ``data/interim/dlc/<twin>.parquet`` plus an ingest report. Unlike
quant_lab.data.datastream (the lab's cleaned per-leg data), this stage follows
the paper's conventions (research/assumptions/dejong_dlc.md):

- every workbook row inside the paper's sample window (Table II) is kept, as
  delivered by Datastream: no volume filter, holiday-padded prices included
  [PAPER-DERIVED reading, D1];
- leg A's price is converted to leg B's currency with the workbook's own FX
  column; the parity deviation is d_t = ln(P_A/P_B) - ln(R) with the workbook's
  theoretical ratio R [PAPER-DERIVED, E1].

Validation (deterministic, the stage fails otherwise): our d_t must equal the
authors' "LOG DEVIATIONS FROM PARITY" column to 1e-9 on every row where both
exist, dates must be strictly increasing weekdays, and the window must lie
inside the workbook.

The stage also writes ``<twin>.regression.parquet``: the inputs of the Table III
comovement regression from the workbook's regression sheet (local-currency log
returns of both legs, the exchange-rate log change, the index log returns), on
every row of that sheet, since the regression's leads and lags read the rows
next to the window. Both legs' returns must equal the panel's total-return log
differences to 1e-9 on every panel date where those are defined.
"""

import argparse
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xlrd
from omegaconf import DictConfig, OmegaConf

from quant_lab.data.datastream import DatastreamFormatError, Sheet, read_sheet

TOLERANCE = 1e-9
# The regression sheet holds each leg's total return twice (local and foreign
# currency, same top label); the paper's regression uses the local one.
FOREIGN_CURRENCY = "foreign currency"
COLUMNS = [
    "price_a",  # leg A, local currency (x price_scale)
    "price_b",  # leg B, local currency (x price_scale)
    "fx",  # units of A's currency per unit of B's currency (1 if the same)
    "close_a",  # leg A in B's currency
    "close_b",
    "tr_a",  # total-return index, local currency, 1 at the window start
    "tr_b",
    "ratio",  # theoretical price ratio R
    "deviation",  # ours: ln(close_a / close_b) - ln(R)
    "deviation_workbook",  # the authors' column
]


def total_return_index(series: pd.Series, kind: str) -> pd.Series:
    """A total-return index from Datastream RI levels or from daily log returns."""
    if kind == "index":
        return series
    if kind == "log_return":
        return np.exp(series.fillna(0.0).cumsum())
    raise ValueError(f"unknown total_return_kind {kind!r}")


def assemble(
    price_a: pd.Series,
    price_b: pd.Series,
    tr_a: pd.Series,
    tr_b: pd.Series,
    ratio: pd.Series,
    deviation_workbook: pd.Series,
    *,
    fx: pd.Series | None,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, dict]:
    """Build the twin panel on the window and check it against the workbook."""
    frame = pd.DataFrame(
        {
            "price_a": price_a,
            "price_b": price_b,
            "fx": 1.0 if fx is None else fx,
            "tr_a": tr_a,
            "tr_b": tr_b,
            "ratio": ratio,
            "deviation_workbook": deviation_workbook,
        }
    )
    if frame.index.min() > pd.Timestamp(start) or frame.index.max() < pd.Timestamp(end):
        raise DatastreamFormatError(
            f"window {start}..{end} not inside the workbook "
            f"({frame.index.min().date()}..{frame.index.max().date()})"
        )
    frame = frame.loc[start:end]
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise DatastreamFormatError("dates are not strictly increasing")
    if (frame.index.dayofweek >= 5).any():
        raise DatastreamFormatError("weekend dates in the window")

    frame["close_a"] = frame["price_a"] / frame["fx"]
    frame["close_b"] = frame["price_b"]
    frame["deviation"] = np.log(frame["close_a"] / frame["close_b"]) - np.log(frame["ratio"])
    both = frame["deviation"].notna() & frame["deviation_workbook"].notna()
    err = (frame.loc[both, "deviation"] - frame.loc[both, "deviation_workbook"]).abs()
    if not both.any() or err.max() > TOLERANCE:
        worst = err.idxmax() if both.any() else None
        raise DatastreamFormatError(
            f"deviation does not reproduce the workbook (max error {err.max():.3g} on {worst})"
        )
    usable = frame["deviation"].notna()
    window_rows = len(frame)
    frame = frame.loc[usable].copy()
    for leg in ("a", "b"):
        tr = frame[f"tr_{leg}"]
        first = tr.first_valid_index()
        frame[f"tr_{leg}"] = tr / tr.loc[first] if first is not None else tr
    frame.index.name = "date"
    report = {
        "window": [start, end],
        "rows": len(frame),
        "start": str(frame.index.min().date()),
        "end": str(frame.index.max().date()),
        "rows_dropped_no_price": int(window_rows - len(frame)),
        "rows_checked_against_workbook": int(both.sum()),
        "max_abs_error_vs_workbook": float(err.max()),
        "ratio_constant": bool((frame["ratio"] == frame["ratio"].iloc[0]).all()),
        "ratio": float(frame["ratio"].iloc[0]),
        "total_return_missing": {leg: int(frame[f"tr_{leg}"].isna().sum()) for leg in ("a", "b")},
    }
    return frame[COLUMNS], report


def regression_path(cfg: DictConfig) -> Path:
    return Path(cfg.interim_path).with_suffix(".regression.parquet")


def regression_indices(spec: DictConfig) -> list[str]:
    """Index labels used by the regression spec and its as-stated variant."""
    labels = [spec.index_a, spec.index_b]
    for key in ("index_a", "index_b"):
        alt = spec.get("as_stated", {}).get(key)
        if alt and alt not in labels:
            labels.append(alt)
    return labels


def regression_panel(
    sheet: Sheet, spec: DictConfig, panel: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
    """Table III inputs from the regression sheet, checked against the twin panel.

    Columns: r_a, r_b (local-currency log returns), fx (log change of A's currency
    per unit of B's, as in the workbook) and ``index:<label>`` per index.
    """
    frame = pd.DataFrame(
        {
            "r_a": sheet.column(spec.return_a, exclude=FOREIGN_CURRENCY),
            "r_b": sheet.column(spec.return_b, exclude=FOREIGN_CURRENCY),
            "fx": sheet.column(spec.fx),
            **{f"index:{label}": sheet.column(label) for label in regression_indices(spec)},
        }
    )
    frame.index.name = "date"
    checked, worst = 0, 0.0
    for leg in ("a", "b"):
        ours = np.log(panel[f"tr_{leg}"]).diff().dropna()
        theirs = frame[f"r_{leg}"].reindex(ours.index)
        err = (ours - theirs).abs()
        if err.isna().any() or err.max() > TOLERANCE:
            bad = err[err.isna() | (err > TOLERANCE)].index[0]
            raise DatastreamFormatError(
                f"regression sheet return r_{leg} does not match the panel on {bad.date()}"
            )
        checked += len(err)
        worst = max(worst, float(err.max()))
    report = {
        "sheet": sheet.name,
        "rows": len(frame),
        "start": str(frame.index.min().date()),
        "end": str(frame.index.max().date()),
        "returns_checked_against_panel": checked,
        "max_abs_error_vs_panel": worst,
    }
    return frame, report


def convert(cfg: DictConfig, root: Path) -> dict:
    src = cfg.source
    with zipfile.ZipFile(root / src.archive) as archive:
        book = xlrd.open_workbook(file_contents=archive.read(src.workbook), on_demand=True)
    legs = {}
    for leg in ("a", "b"):
        spec = src.legs[leg]
        sheet = read_sheet(book, spec.sheet)
        price = sheet.column(spec.price) * spec.get("price_scale", 1.0)
        tr = total_return_index(
            sheet.column(spec.total_return), spec.get("total_return_kind", "index")
        )
        fx = sheet.column(spec.fx_per_b) if spec.get("fx_per_b") else None
        legs[leg] = (price, tr, fx)
    ratio_sheet = read_sheet(book, src.ratio.sheet)
    panel, report = assemble(
        legs["a"][0],
        legs["b"][0],
        legs["a"][1],
        legs["b"][1],
        ratio_sheet.column(src.ratio.theoretical_ratio),
        ratio_sheet.column(src.ratio.deviation, exclude=src.ratio.get("deviation_exclude")),
        fx=legs["a"][2],
        start=cfg.window.start,
        end=cfg.window.end,
    )
    out = root / cfg.interim_path
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out)
    regression, report["regression"] = regression_panel(
        read_sheet(book, cfg.regression.sheet), cfg.regression, panel
    )
    regression.to_parquet(root / regression_path(cfg))
    report = {"twin": cfg.name, "archive": src.archive, "workbook": src.workbook, **report}
    out.with_suffix(".ingest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def load_twin_config(twin: str, root: Path) -> DictConfig:
    return OmegaConf.load(root / "conf" / "dlc" / f"{twin}.yaml")


def twins(root: Path) -> list[str]:
    return sorted(p.stem for p in (root / "conf" / "dlc").glob("*.yaml"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--twin", required=True, help="name of conf/dlc/<twin>.yaml")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    args = parser.parse_args(argv)
    print(json.dumps(convert(load_twin_config(args.twin, args.root), args.root), indent=2))


if __name__ == "__main__":
    main()
