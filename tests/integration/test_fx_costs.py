"""A leg traded in a foreign currency pays an FX conversion cost (audit 2026-10-07, A5).

rd_shell converts Royal Dutch to GBP (``fx_per_unit``), so a GBP-funded desk
converts currency on every Royal Dutch order. The liquidity cost model must
have an explicit term for it, even if it is set to zero as a labelled assumption.
"""

from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.xfail(
    strict=True,
    reason="audit 2026-10-07 A5 CONFIRMED: liquidity cost model has no FX conversion term",
)
def test_cost_model_prices_fx_conversion_for_foreign_currency_legs():
    with initialize_config_dir(config_dir=str(ROOT / "conf"), version_base="1.3"):
        cfg = compose("config", overrides=["data=rd_shell"])
    fx_legs = [leg for leg, src in cfg.data.source.legs.items() if "fx_per_unit" in src]
    assert fx_legs, "rd_shell has a foreign-currency leg"
    assert "fx_conversion_bps" in cfg.costs
