# Baseline: parity z-score convergence trade

Status: pipeline baseline. It exercises data -> signal -> execution -> costs ->
MLflow end to end. It is **not** a replication of Maymin (SILTA): the paper
explains why twin mispricings persist and proposes no trading rule. A
SILTA-informed strategy follows after `/extract-paper` has produced
`research/extraction/`.

Code: `src/quant_lab/strategies/parity_zscore.py`. Parameters: `conf/strategy/parity_zscore.yaml`.

## Rules

| # | Rule | Classification |
|---|---|---|
| 1 | Relative price `r_t = ln(P_a,t / P_b,t)` on daily closes. | [PAPER-DERIVED] (definition, p. 5) |
| 2 | Standardise `r_t` with a trailing `window`-day mean and standard deviation, using closes up to and including `t`. | [IMPLEMENTATION-ASSUMPTION]. The paper standardises (demean, descale, detrend) over the full sample, which is look-ahead in a trading context. |
| 3 | No detrending. | [IMPLEMENTATION-ASSUMPTION]. A trailing mean absorbs slow drift; explicit detrending is deferred until the paper's procedure is extracted. |
| 4 | Short A / long B when `z_t > entry_z`; long A / short B when `z_t < -entry_z`; close when `|z_t| < exit_z`; flip directly when the opposite threshold is crossed. | [PROPOSED-EXTENSION]. The paper contains no entry/exit rule. |
| 5 | No position while `z_t` is undefined (warm-up). | [IMPLEMENTATION-ASSUMPTION] |
| 6 | Decision on close `t`, order filled at open `t+1`. | [IMPLEMENTATION-ASSUMPTION] |
| 7 | Dollar-neutral: each leg `leg_weight` of equity, rebalanced only when the spread position changes. | [IMPLEMENTATION-ASSUMPTION] |
| 8 | Positions are closed at the open of the last day of the evaluated period. | [IMPLEMENTATION-ASSUMPTION] |
| 9 | Costs: flat bps per order (sensitivity case). | [IMPLEMENTATION-ASSUMPTION]. Replaced by liquidity-scaled impact + borrow in Step 4b. |

## Known gaps

- Relative volume, the variable SILTA is about, is not used.
- No position limit relative to traded volume (the paper discusses arbitrageurs
  capping trading at a fraction of daily volume, e.g. 15%, and total position
  at a multiple of daily volume). Planned for Step 4b together with the impact model.
- No borrow or funding cost on the short leg.
- Dividends: signal and P&L use unadjusted closes; twin share classes can pay
  different dividends, which matters for real data.
