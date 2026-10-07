"""Headline reproduction (step 12): the recorded numbers are development-only and,
when the licensed data is present, reproduce within tolerance."""

from pathlib import Path

import pytest
from omegaconf import OmegaConf

from quant_lab import reproduce

ROOT = Path(__file__).resolve().parents[2]
SPEC = OmegaConf.load(ROOT / "research/reports/headlines.yaml")
HAVE_DATA = all(
    (ROOT / f"data/processed/{d}/panel.parquet").exists() for d in {c.data for c in SPEC.checks}
)


def test_headlines_never_reference_the_oos_period():
    for check in SPEC.checks:
        assert check.kind in {"silta", "backtest", "walkforward"}
        assert check.get("period", "train") in {"train", "validation"}
        assert check.data != "rio_tinto"  # OOS-only pair


def test_compare_uses_absolute_tolerance():
    assert reproduce.compare(0.5, 0.50009, 1e-4)
    assert not reproduce.compare(0.5, 0.5002, 1e-4)


@pytest.mark.skipif(not HAVE_DATA, reason="licensed panels not present (dvc pull && dvc repro)")
def test_headline_numbers_reproduce():
    outcomes = reproduce.run_checks(ROOT)
    failed = [(o.name, o.expected, o.actual) for o in outcomes if not o.ok]
    assert not failed, failed
