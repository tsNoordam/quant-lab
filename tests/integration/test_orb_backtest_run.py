"""Step 23 end to end on synthetic processed files: MLflow run with the lab's
required provenance, results, verdicts and summary; OOS never read."""

import shutil
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from quant_lab.backtest import orb as b

ROOT = Path(__file__).resolve().parents[2]


def test_track_a_run(tmp_path):
    for rel in (
        "conf/orb/backtest.yaml",
        "conf/orb/default.yaml",
        "conf/futures/es.yaml",
        "conf/split/es.yaml",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    (tmp_path / "conf/config.yaml").write_text(
        f"mlflow:\n  tracking_uri: sqlite:///{tmp_path}/mlflow.db\n  artifact_root: mlartifacts\n"
    )
    rng = np.random.default_rng(5)
    days = list(pd.bdate_range("2016-01-04", periods=40)) + list(
        pd.bdate_range("2019-01-02", periods=30)
    )
    days += list(pd.bdate_range("2021-02-01", periods=5))  # out-of-sample: must not be read
    rows, sess, prev = [], [], 2000.0
    for d in days:
        c = (prev + rng.normal(0, 3) + np.cumsum(rng.normal(0, 0.6, 390)) / 0.25).round() * 0.25
        o = np.r_[c[0], c[:-1]]
        for m in range(390):
            px = {
                "open": o[m],
                "high": max(o[m], c[m]) + 0.25,
                "low": min(o[m], c[m]) - 0.25,
                "close": c[m],
            }
            rows.append({"session": d, "minute": m, "instrument_id": 1, "volume": 100, **px})
        sess.append(
            {
                "session": d,
                "usable": True,
                "bars": 390,
                "close": c[-1],
                "prev_close": prev,
                "volume": 1.5e6,
            }
        )
        prev = float(c[-1])
    proc = tmp_path / "data/processed/es"
    proc.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(proc / "rth_1m.parquet", index=False)
    pd.DataFrame(sess).set_index("session").to_parquet(proc / "sessions.parquet")

    out = b.run(tmp_path)
    res = out["results"]
    assert set(res["period"]) == {"train", "validation", "development"}
    assert set(res["universe"]) == {"usable", "with_bars"}
    assert len(out["verdicts"]) == len({c["family"] for c in b.configs(b.load_config(tmp_path))})
    assert out["n_trials"] == 70

    tags = mlflow.get_run(out["run_id"]).data
    for key in ("git_commit", "git_dirty", "sessions.parquet.data_md5", "unlock_oos"):
        assert key in tags.tags
    for key in (
        "date_range",
        "timeframe",
        "execution_model",
        "position_sizing",
        "leverage",
        "costs.base.slippage_ticks",
    ):
        assert key in tags.params, key
    assert tags.params["date_range"] == "2010-06-07..2020-12-31"
    text = b._summary(out)
    assert "Kill criterion" in text and "Cost scenarios" in text
