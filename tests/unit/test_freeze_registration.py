"""Freeze audit A3/A5: the OOS evaluation is fully specified before it runs."""

from pathlib import Path

from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "research/specs/freeze/preregistration.md"


def test_preregistration_note_covers_the_protocol():
    text = PREREG.read_text()
    for required in (
        "rio_tinto_execution",
        "n_trials",
        "var_sr_per_period",
        "sr0_per_period",
        "decision_rule",
        "predictions",
        "if a run errors",
    ):
        assert required in text, f"pre-registration lacks '{required}'"


def test_deflation_inputs_are_frozen_numbers():
    d = OmegaConf.load(ROOT / "conf/oos/default.yaml").deflation
    assert isinstance(d.n_trials, int) and d.n_trials > 0
    for strategy in ("parity_zscore", "silta_parity"):
        assert d.var_sr_per_period[strategy] > 0


def test_rio_tinto_inputs_are_no_longer_unverified():
    assert "UNVERIFIED" not in (ROOT / "conf/data/rio_tinto.yaml").read_text()
