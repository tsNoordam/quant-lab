"""Fama-French daily factors from Kenneth French's data library.

The raw file is the library's own zip, unmodified, in ``data/raw/french_ff/``
(DVC, metadata in ``data/metadata/french_ff.json``):

    https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip

The zip holds one CSV: a few lines of text, a header ``,Mkt-RF,SMB,HML,RF``,
one row per US trading day (``YYYYMMDD``, values in percent) and a copyright
line. Returned as decimals, indexed by date.
"""

import io
import re
import zipfile
from pathlib import Path

import pandas as pd

COLUMNS = ["Mkt-RF", "SMB", "HML", "RF"]
ROW = re.compile(r"^\s*(\d{8})\s*,")


def load_factors(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{path}: expected one CSV inside, found {names}")
        text = archive.read(names[0]).decode("latin-1")
    lines = text.splitlines()
    header = next((i for i, line in enumerate(lines) if "Mkt-RF" in line), None)
    if header is None:
        raise ValueError(f"{path}: no Mkt-RF header")
    names = [c.strip() for c in lines[header].split(",")]
    if names[1:] != COLUMNS:
        raise ValueError(f"{path}: unexpected columns {names}")
    body = []
    for line in lines[header + 1 :]:
        if not ROW.match(line):
            break  # the daily block ends at the first non-date line
        body.append(line)
    frame = pd.read_csv(io.StringIO("\n".join(body)), header=None, names=["date", *COLUMNS])
    frame["date"] = pd.to_datetime(frame["date"].astype(str), format="%Y%m%d")
    frame = frame.set_index("date")[COLUMNS] / 100
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError(f"{path}: dates are not strictly increasing")
    if frame.isna().any().any() or (frame.abs() > 0.5).any().any():
        raise ValueError(f"{path}: missing or implausible daily factor values")
    return frame
