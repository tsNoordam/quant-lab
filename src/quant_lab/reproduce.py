"""Reproduce the headline development results and compare them with the record.

    uv run python -m quant_lab.reproduce            # all checks
    uv run python -m quant_lab.reproduce rd_shell   # checks on one dataset

Expected values live in research/reports/headlines.yaml (taken from the clean
MLflow runs at the freeze). Nothing is logged to MLflow and the OOS period is
never touched: these are train, validation and walk-forward numbers only (the
OOS evaluation was a one-shot run and is not repeated).
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from quant_lab.backtest.run import backtest_pair, compute_metrics, select_period
from quant_lab.backtest.walkforward import walk_forward
from quant_lab.data.preprocess import PANEL_FILE
from quant_lab.models import silta
from quant_lab.strategies import decide

ROOT = Path(__file__).resolve().parents[2]
HEADLINES = ROOT / "research/reports/headlines.yaml"


@dataclass(frozen=True)
class Outcome:
    name: str
    expected: float
    actual: float
    ok: bool


def _cfg(root: Path, overrides: list[str]):
    with initialize_config_dir(config_dir=str(root / "conf"), version_base="1.3"):
        return compose("config", overrides=overrides)


def measure(check, root: Path) -> float:
    """Recompute one headline number (no MLflow logging)."""
    cfg = _cfg(root, [f"data={check.data}", f"strategy={check.get('strategy', 'parity_zscore')}"])
    panel = pd.read_parquet(root / cfg.data.processed_dir / PANEL_FILE)
    if check.kind == "silta":
        res = silta.analyse(cfg, panel)["results"]
        row = res[(res["window"] == check.window) & (res["spec"] == check.spec)].iloc[0]
        return float(row[check.metric])
    if check.kind == "backtest":
        cfg = _cfg(
            root,
            [f"data={check.data}", f"strategy={check.strategy}", f"backtest.period={check.period}"],
        )
        period = select_period(cfg)
        visible = panel.loc[: period.end]
        sim = backtest_pair(visible, decide(visible, cfg)[0], period, cfg)
        return float(
            compute_metrics(sim.equity, sim.held, sim.pf, cfg.backtest.annualization)[check.metric]
        )
    if check.kind == "walkforward":
        return float(walk_forward(cfg, panel)["summary"][check.metric])
    raise ValueError(f"unknown check kind {check.kind!r}")


def compare(expected: float, actual: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


def run_checks(root: Path = ROOT, only: str | None = None) -> list[Outcome]:
    spec = OmegaConf.load(root / "research/reports/headlines.yaml")
    out = []
    for check in spec.checks:
        if only and check.data != only:
            continue
        actual = measure(check, root)
        out.append(
            Outcome(
                check.name, check.expected, actual, compare(check.expected, actual, spec.tolerance)
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    outcomes = run_checks(ROOT, argv[0] if argv else None)
    for o in outcomes:
        status = "OK  " if o.ok else "FAIL"
        print(f"{status} {o.name:<40} expected {o.expected:+.4f}  got {o.actual:+.4f}")
    failed = [o for o in outcomes if not o.ok]
    print(f"{len(outcomes) - len(failed)}/{len(outcomes)} headline numbers reproduced")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
