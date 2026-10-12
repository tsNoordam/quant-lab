"""Step 22 end to end on synthetic processed files: MLflow run, tables, summary."""

import shutil
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from quant_lab.models import orb_stats as o

ROOT = Path(__file__).resolve().parents[2]


def test_run_logs_tables_and_prints_summary(tmp_path):
    for rel in ("conf/orb/default.yaml", "conf/futures/es.yaml", "conf/split/es.yaml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    (tmp_path / "conf/config.yaml").write_text(
        f"mlflow:\n  tracking_uri: sqlite:///{tmp_path}/mlflow.db\n  artifact_root: mlartifacts\n"
    )
    rng = np.random.default_rng(3)
    days = list(pd.bdate_range("2016-05-02", periods=8)) + list(
        pd.bdate_range("2021-02-01", periods=3)
    )
    rows, sess = [], []
    for d in days:
        path = (100 + np.cumsum(rng.normal(0, 0.5, 390)) / 0.25).round() * 0.25
        for m, px in enumerate(path):
            bar = {"open": px, "high": px + 0.25, "low": px - 0.25, "close": px, "volume": 10}
            rows.append({"session": d, "minute": m, "instrument_id": 1, **bar})
        sess.append({"session": d, "usable": True, "bars": 390, "prev_close": path[0] + 2.0})
    proc = tmp_path / "data/processed/es"
    proc.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(proc / "rth_1m.parquet", index=False)
    pd.DataFrame(sess).set_index("session").to_parquet(proc / "sessions.parquet")

    out = o.run(tmp_path)
    # the three 2021 sessions are out-of-sample and never read
    counts = out["counts"].set_index(["period", "universe"])["sessions"]
    assert counts[("development", "usable")] == 8

    run = mlflow.get_run(out["run_id"])
    assert run.data.tags["unlock_oos"] == "false"
    assert run.data.params["date_range"] == "2010-06-07..2020-12-31"
    assert "sessions.parquet.data_md5" in run.data.tags
    text = o._summary(out)
    assert "Claims vs ours" in text and "Gap fill" in text
