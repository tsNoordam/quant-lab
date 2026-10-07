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
| 6 | Decision on close `t`, order filled on bar `t+1`: its open (`next_open`) or, for close-only data, its close (`next_close`). | [IMPLEMENTATION-ASSUMPTION] |
| 7 | Dollar-neutral: each leg `leg_weight` of equity, rebalanced only when the spread position changes. | [IMPLEMENTATION-ASSUMPTION] |
| 8 | Positions are closed on the last bar of the evaluated period. | [IMPLEMENTATION-ASSUMPTION] |
| 9 | Costs (default `costs=liquidity`): per order half quoted spread (fallback when unquoted) + `k·σ·sqrt(shares/ADV)` impact + commission; daily borrow fee on the short leg. Statistics as of the decision close. | [EXTERNAL-RESEARCH] (square-root impact law) + [IMPLEMENTATION-ASSUMPTION] (parameter values in `conf/costs/liquidity.yaml`). Flat bps (`costs=flat_bps`) only as a labelled sensitivity case. |
| 10 | Entry size per leg capped so neither leg trades more than `max_participation` (15%) of its ADV; the size is then held to exit. | [PAPER-DERIVED] example of a self-imposed limit (Maymin), turned into a sizing rule: [PROPOSED-EXTENSION]. |

## Known gaps

- Relative volume, the variable SILTA is about, is not used.
- The paper also describes a cap on total position as a multiple of daily
  volume; with single-day entries the 15% participation cap is always the
  binding one, so it is not modelled separately.
- Funding of the long leg and interest on short proceeds are ignored (they
  roughly offset for a dollar-neutral book).
- Trade size for the impact model uses `backtest.init_cash` as the equity scale,
  not the running equity.
- Dividends: signal and P&L use unadjusted closes; twin share classes can pay
  different dividends, which matters for real data.
