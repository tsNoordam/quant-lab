"""A leg traded in a foreign currency pays an FX conversion cost (audit 2026-10-07, A5).

rd_shell converts Royal Dutch to GBP (``fx_per_unit``), so a GBP-funded desk
converts currency on every Royal Dutch order. The liquidity cost model must
have an explicit term for it, even if it is set to zero as a labelled assumption.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hydra import compose, initialize_config_dir

from quant_lab.backtest import costs

ROOT = Path(__file__).resolve().parents[2]


def compose_for(dataset):
    with initialize_config_dir(config_dir=str(ROOT / "conf"), version_base="1.3"):
        return compose("config", overrides=[f"data={dataset}"])


def test_cost_model_prices_fx_conversion_for_foreign_currency_legs():
    cfg = compose_for("rd_shell")
    fx_legs = [leg for leg, src in cfg.data.source.legs.items() if "fx_per_unit" in src]
    assert fx_legs, "rd_shell has a foreign-currency leg"
    assert "fx_conversion_bps" in cfg.costs


@pytest.mark.parametrize(
    ("dataset", "expected"),
    [
        ("rd_shell", ("a",)),
        ("reed_elsevier", ("a",)),
        ("rio_tinto", ("a",)),
        ("synthetic_twin", ()),
    ],
)
def test_fx_legs_follow_the_dataset_source(dataset, expected):
    assert costs.fx_legs(compose_for(dataset).data) == expected


def test_fx_leg_orders_pay_exactly_the_conversion_cost():
    cfg = compose_for("rd_shell").costs
    idx = pd.bdate_range("2020-01-01", periods=2)
    stats = pd.DataFrame(
        {"half_spread": 0.001, "sigma": 0.02, "adv": 1e6, "price": 10.0, "quoted": True}, index=idx
    )
    orders = pd.DataFrame({"a": [0.5, np.nan], "b": [-0.5, np.nan]}, index=idx)
    with_fx = costs.order_costs(orders, {"a": stats, "b": stats}, 1e6, cfg, fx_legs=("a",))
    without = costs.order_costs(orders, {"a": stats, "b": stats}, 1e6, cfg)
    assert with_fx.iloc[0]["a"] - without.iloc[0]["a"] == pytest.approx(cfg.fx_conversion_bps / 1e4)
    assert with_fx.iloc[0]["b"] == without.iloc[0]["b"]
    assert with_fx.iloc[1].isna().all()  # no order, no cost
