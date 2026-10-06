"""DVC stage: raw per-symbol files -> validated, aligned pair panel.

    uv run dvc repro                                          # via dvc.yaml
    uv run python -m quant_lab.data.preprocess --dataset synthetic_twin

Reads ``conf/data/<dataset>.yaml`` and writes to its ``processed_dir``:

    panel.parquet     aligned OHLCV for both legs + stale flags
    validation.json   DVC metrics: coverage, row counts, warnings

Any validation error aborts the stage, so DVC never caches a bad panel.
"""

import argparse
import json
from pathlib import Path

from omegaconf import DictConfig, OmegaConf

from quant_lab.data.loaders import load_symbol
from quant_lab.data.synchronization import align_pair
from quant_lab.data.validation import (
    check_ohlcv,
    check_pair_coverage,
    coverage,
    raise_on_errors,
)

PANEL_FILE = "panel.parquet"
REPORT_FILE = "validation.json"


def load_dataset_config(dataset: str, root: Path) -> DictConfig:
    return OmegaConf.load(root / "conf" / "data" / f"{dataset}.yaml")


def preprocess(cfg: DictConfig, root: Path) -> dict:
    raw_dir = root / cfg.raw_dir
    legs = {leg: load_symbol(raw_dir, symbol) for leg, symbol in cfg.legs.items()}

    issues = []
    for leg, df in legs.items():
        issues += check_ohlcv(
            df,
            f"{leg}:{cfg.legs[leg]}",
            max_abs_log_return=cfg.validation.max_abs_log_return,
        )
    issues += check_pair_coverage(
        legs["a"].index, legs["b"].index, max_missing_frac=cfg.validation.max_missing_frac
    )
    raise_on_errors(issues)

    panel = align_pair(
        legs["a"],
        legs["b"],
        missing_policy=cfg.alignment.missing_policy,
        ffill_limit=cfg.alignment.ffill_limit,
    )

    out_dir = root / cfg.processed_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out_dir / PANEL_FILE)

    reference = legs["a"].index.union(legs["b"].index)
    report = {
        "dataset": cfg.name,
        "legs": dict(cfg.legs),
        "start": str(panel.index.min().date()),
        "end": str(panel.index.max().date()),
        "rows": len(panel),
        "dates_either_leg": len(reference),
        "rows_dropped": len(reference) - len(panel),
        "missing_frac_a": round(coverage(legs["a"].index, reference), 6),
        "missing_frac_b": round(coverage(legs["b"].index, reference), 6),
        "stale_rows_a": int(panel["stale_a"].sum()),
        "stale_rows_b": int(panel["stale_b"].sum()),
        "warnings": [str(i) for i in issues if i.severity == "warning"],
    }
    # No timestamps in the report: identical inputs must give identical metrics.
    (out_dir / REPORT_FILE).write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True, help="name of conf/data/<dataset>.yaml")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    args = parser.parse_args(argv)
    report = preprocess(load_dataset_config(args.dataset, args.root), args.root)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
