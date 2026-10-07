"""DVC stage: Datastream dual-listed-company workbooks -> per-leg raw CSVs.

    uv run python -m quant_lab.data.datastream --dataset rd_shell

Reads the original, immutable archive in ``data/raw/datastream_dlc/`` (zipped
legacy ``.xls``) without extracting it, and writes ``<raw_dir>/<SYMBOL>.csv`` in
the close-only raw schema (see quant_lab.data.loaders) plus an ingest report.

Every repair is deterministic and asserted:

1. Dates. Datastream exported dd/mm/yy. Days 13-31 stayed text; days 1-12 were
   read by Excel as month/day. Text is parsed as dd/mm/yy and date cells are
   swapped back. The result must be strictly increasing weekdays.
2. Excel error cells (#N/A is stored as code 42) are missing values, never numbers.
3. Datastream pads exchange holidays with the previous price. A day without
   volume (missing or zero) is a non-trading day for that leg and is dropped.
4. Units. Prices and quotes are converted to the dataset currency with the
   workbook's own FX column; volume is converted to shares.
5. adj_close = close x total-return factor (RI_t/RI_0)/(P_t/P_0), anchored on the
   first day of the window, so it only uses information up to t.

Columns are located by their exact header label (e.g. ``902178(P)``), never by
position, and each label must match exactly one column.
"""

import argparse
import datetime as dt
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xlrd
from omegaconf import DictConfig, OmegaConf

TEXT_DATE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
# Bloomberg exports (e.g. the Smithkline Beecham workbook) write m/d/yyyy text.
TEXT_DATE_US = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
EXCEL_SERIAL_RANGE = (20_000, 50_000)  # 1954-10-03 .. 2036-11-21


class DatastreamFormatError(ValueError):
    """The workbook does not look the way the converter expects."""


def normalize(text: object) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def repair_dates(entries: list[tuple[str, dt.date]]) -> list[dt.date]:
    """Undo the dd/mm vs mm/dd mix-up. ``entries`` are (kind, date), kind 'cell' or 'text'."""
    dates = [d for _, d in entries]
    if not all(b > a for a, b in zip(dates, dates[1:], strict=False)):
        dates = [d.replace(month=d.day, day=d.month) if k == "cell" else d for k, d in entries]
    if not all(b > a for a, b in zip(dates, dates[1:], strict=False)):
        raise DatastreamFormatError("dates are not strictly increasing after repair")
    weekend = [d for d in dates if d.weekday() >= 5]
    if weekend:
        raise DatastreamFormatError(f"weekend dates after repair, e.g. {weekend[:3]}")
    return dates


@dataclass(frozen=True)
class Sheet:
    name: str
    header: list[list[str]]  # rows above the data, normalized text per column
    data: pd.DataFrame  # one float column per sheet column (1-based), NaN if not a number

    def column(self, label: str, exclude: str | None = None) -> pd.Series:
        """The one column with a header row equal to ``label``; columns with any header
        row containing ``exclude`` are skipped (e.g. an absolute-value duplicate)."""
        want = normalize(label)
        hits = [
            c
            for c in self.data.columns
            if any(row[c] == want for row in self.header)
            and not (exclude and any(exclude in row[c] for row in self.header))
        ]
        if len(hits) != 1:
            raise DatastreamFormatError(
                f"sheet '{self.name}': header '{label}' matches {len(hits)} columns"
            )
        return self.data[hits[0]].rename(want)


def read_sheet(book: xlrd.Book, name: str) -> Sheet:
    sh = book.sheet_by_name(name)
    entries, rows = [], []
    for r in range(sh.nrows):
        kind, value = sh.cell_type(r, 0), sh.cell_value(r, 0)
        is_serial = kind in (xlrd.XL_CELL_DATE, xlrd.XL_CELL_NUMBER) and (
            EXCEL_SERIAL_RANGE[0] < value < EXCEL_SERIAL_RANGE[1]
        )
        if is_serial:
            entries.append(("cell", xlrd.xldate_as_datetime(value, book.datemode).date()))
        elif kind == xlrd.XL_CELL_TEXT and TEXT_DATE.match(value.strip()):
            entries.append(("text", dt.datetime.strptime(value.strip(), "%d/%m/%y").date()))
        elif kind == xlrd.XL_CELL_TEXT and TEXT_DATE_US.match(value.strip()):
            entries.append(("text", dt.datetime.strptime(value.strip(), "%m/%d/%Y").date()))
        else:
            continue
        rows.append(r)
    if not rows:
        raise DatastreamFormatError(f"sheet '{name}' has no dated rows")

    width = range(1, sh.ncols)
    header = [[""] + [normalize(sh.cell_value(r, c)) for c in width] for r in range(rows[0])]
    values = [
        [
            sh.cell_value(r, c) if sh.cell_type(r, c) == xlrd.XL_CELL_NUMBER else np.nan
            for c in width
        ]
        for r in rows
    ]
    index = pd.DatetimeIndex(repair_dates(entries), name="date")
    return Sheet(name, header, pd.DataFrame(values, index=index, columns=list(width)))


def build_leg(
    price: pd.Series,
    total_return_index: pd.Series,
    volume: pd.Series,
    *,
    fx_per_unit: pd.Series | None = None,
    bid: pd.Series | None = None,
    ask: pd.Series | None = None,
    shares_outstanding: pd.Series | None = None,
    price_scale: float = 1.0,
    quote_scale: float = 1.0,
    volume_multiplier: float = 1.0,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Assemble one leg in the raw schema. All inputs are indexed by date.

    Volume and shares outstanding share Datastream's unit, so both are scaled by
    ``volume_multiplier``.
    """
    frame = pd.DataFrame({"price": price, "ri": total_return_index, "volume": volume})
    frame["fx"] = 1.0 if fx_per_unit is None else fx_per_unit
    frame["bid"] = np.nan if bid is None else bid
    frame["ask"] = np.nan if ask is None else ask
    if shares_outstanding is not None:
        frame["nosh"] = shares_outstanding
    frame = frame.loc[start:end]

    traded = frame["volume"].notna() & (frame["volume"] > 0)
    report = {"window_rows": len(frame), "no_volume_rows_dropped": int((~traded).sum())}
    frame = frame.loc[traded]
    needed = frame[["price", "ri", "fx"]]
    if needed.isna().any().any():
        missing = needed.index[needed.isna().any(axis=1)]
        raise DatastreamFormatError(f"price/RI/FX missing on traded days, e.g. {list(missing[:3])}")

    close = frame["price"] * price_scale / frame["fx"]
    tr_factor = (frame["ri"] / frame["ri"].iloc[0]) / (frame["price"] / frame["price"].iloc[0])
    out = pd.DataFrame(
        {
            "close": close,
            "adj_close": close * tr_factor,
            "volume": frame["volume"] * volume_multiplier,
            "bid": frame["bid"] * quote_scale / frame["fx"],
            "ask": frame["ask"] * quote_scale / frame["fx"],
        }
    )
    if shares_outstanding is not None:
        out["shares_outstanding"] = frame["nosh"] * volume_multiplier
    out.index.name = "date"
    report |= {
        "rows": len(out),
        "start": str(out.index.min().date()),
        "end": str(out.index.max().date()),
        "quote_coverage": round(float(out[["bid", "ask"]].notna().all(axis=1).mean()), 6),
    }
    return out, report


def convert(cfg: DictConfig, root: Path) -> dict:
    src = cfg.source
    with zipfile.ZipFile(root / src.archive) as archive:
        book = xlrd.open_workbook(file_contents=archive.read(src.workbook), on_demand=True)
    flows = read_sheet(book, src.volume_sheet)

    out_dir = root / cfg.raw_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"dataset": cfg.name, "archive": src.archive, "workbook": src.workbook, "legs": {}}
    for leg, symbol in cfg.legs.items():
        spec = src.legs[leg]
        prices = read_sheet(book, spec.sheet)
        df, leg_report = build_leg(
            prices.column(spec.price),
            prices.column(spec.total_return_index),
            flows.column(spec.volume),
            fx_per_unit=prices.column(spec.fx_per_unit) if spec.get("fx_per_unit") else None,
            bid=flows.column(spec.bid) if spec.get("bid") else None,
            ask=flows.column(spec.ask) if spec.get("ask") else None,
            shares_outstanding=(
                prices.column(spec.shares_outstanding) if spec.get("shares_outstanding") else None
            ),
            price_scale=spec.price_scale,
            quote_scale=spec.quote_scale,
            volume_multiplier=src.volume_multiplier,
            start=src.window.start,
            end=src.window.end,
        )
        df.to_csv(out_dir / f"{symbol}.csv", date_format="%Y-%m-%d")
        report["legs"][symbol] = leg_report

    report_path = root / f"{cfg.raw_dir}.ingest.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, help="name of conf/data/<dataset>.yaml")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    args = parser.parse_args(argv)
    cfg = OmegaConf.load(args.root / "conf" / "data" / f"{args.dataset}.yaml")
    print(json.dumps(convert(cfg, args.root), indent=2))


if __name__ == "__main__":
    main()
