"""End-to-end checks on the real Datastream archives (skipped when not pulled).

The data is licensed and lives only in DVC. Run `uv run dvc pull` (or add the
archives, see README) to enable these tests.
"""

import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xlrd

from quant_lab.data.datastream import convert, read_sheet
from quant_lab.data.preprocess import load_dataset_config, preprocess

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / "data" / "raw" / "datastream_dlc"
PAIRS = ["rd_shell", "unilever", "reed_elsevier", "rio_tinto"]

pytestmark = pytest.mark.skipif(
    not any(ARCHIVES.glob("*.zip")), reason="Datastream archives not present (dvc pull)"
)


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    root = tmp_path_factory.mktemp("lab")
    shutil.copytree(ROOT / "conf", root / "conf")
    (root / "data" / "raw").mkdir(parents=True)
    (root / "data" / "raw" / "datastream_dlc").symlink_to(ARCHIVES)
    return root


@pytest.mark.parametrize("dataset", PAIRS)
def test_ingested_prices_reproduce_the_workbook_parity_deviations(lab, dataset):
    """Our GBP conversion must match the dataset authors' own parity computation."""
    cfg = load_dataset_config(dataset, lab)
    convert(cfg, lab)
    preprocess(cfg, lab)
    panel = pd.read_parquet(lab / cfg.processed_dir / "panel.parquet")

    with zipfile.ZipFile(lab / cfg.source.archive) as archive:
        book = xlrd.open_workbook(file_contents=archive.read(cfg.source.workbook))
    # Column 3 of 'Ratio' is "LOG DEVIATIONS FROM PARITY" on prices (all four workbooks).
    theirs = read_sheet(book, "Ratio").data[3].reindex(panel.index)
    ours = np.log(panel["close_a"] / panel["close_b"] / cfg.parity_ratio)

    assert theirs.notna().all()
    np.testing.assert_allclose(ours, theirs, atol=1e-12)


@pytest.mark.parametrize("dataset", PAIRS)
def test_ingest_is_deterministic(lab, dataset):
    cfg = load_dataset_config(dataset, lab)
    first = convert(cfg, lab)
    files = {p.name: p.read_bytes() for p in (lab / cfg.raw_dir).glob("*.csv")}
    assert convert(cfg, lab) == first
    assert files == {p.name: p.read_bytes() for p in (lab / cfg.raw_dir).glob("*.csv")}
