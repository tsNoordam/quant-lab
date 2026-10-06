---
name: robustness
description: Perform parameter sensitivity, cost sensitivity, walk-forward, out-of-sample, and regime robustness analysis for a quantitative strategy.
---

# Robustness

Do not search for the best parameter.

Test parameter neighborhoods.

Test:

- transaction costs
- slippage
- different periods
- walk-forward windows
- out-of-sample
- volatility regimes
- market regimes
- trade concentration

Run sweeps through Hydra multirun on the train/validation split only.
Never pass +unlock_oos=true.

Every run is logged to MLflow. Write the written summary
(sensitivity tables, stable regions, conclusion) to:

research/reports/
