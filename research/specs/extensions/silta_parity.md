# Extension: the SILTA arbitrageur (`silta_parity`)

Status: [PROPOSED-EXTENSION] as a whole. The paper proposes no trading rule
(`research/specs/replication/maymin_silta.md`). This strategy is the trade
the paper's arbitrageurs are modelled as doing. It is built from the paper's
own elements R1-R5 where they exist, and every gap is labelled.

Code: `src/quant_lab/strategies/silta_parity.py`. Parameters:
`conf/strategy/silta_parity.yaml`. Run with `strategy=silta_parity`.

Written before any run of this strategy on real data.

## How it differs from the baseline

`parity_zscore` (baseline) trades the relative price against its own trailing
60-day mean: a statistical, short-horizon mean-reversion bet. It ignores
parity. `silta_parity` trades the relative price against **theoretical
parity**, as Maymin's arbitrageur does. It holds until the discrepancy is
gone, which the paper models as a rare event.

## Rules

| # | Rule | Classification |
|---|---|---|
| 1 | D_t = ln(P_a,t / P_b,t) - ln(parity) on raw daily closes in the common currency. | [PAPER-DERIVED] (E1, R1; raw prices per A7). Parity value per pair (`data.parity_ratio`): RD/Shell [MATHEMATICALLY-DERIVED] 1.5 x N_Shell/N_RD from pre-2000 share counts = 6.9558 (changed from the workbook's 6.863 at the freeze audit, A1: that value carried OOS information); Reed/Elsevier 1.538 from the agreement text; Rio Tinto 1.0 (see the freeze pre-registration). |
| 2 | D_t uses only close t. No rolling window, no standardization. | [PAPER-DERIVED] (R1: the discrepancy itself is the opportunity). Consequence: no look-ahead and no warm-up. |
| 3 | Short A / long B when D_t > entry_bound; long A / short B when D_t < -entry_bound (short the expensive leg). | [PAPER-DERIVED] (R1) |
| 4 | entry_bound = 0.018 (180 bps). | [PAPER-DERIVED] (R2: HSBC's round-turn cost, used by the paper for all pairs). Applying it to RD/Shell in 1987-99 is the paper's own simplification, not a measured cost of this pair. |
| 5 | Close when D_t reaches or crosses parity (exit_bound = 0); flip directly if the opposite bound is crossed. | [PAPER-DERIVED] (R3: paid at convergence). Flipping: [IMPLEMENTATION-ASSUMPTION], same hysteresis code as the baseline. |
| 6 | Decision on close t, fill at close t+1 (`next_close`; the real pairs are close-only). | [IMPLEMENTATION-ASSUMPTION] (baseline rule 6) |
| 7 | Dollar-neutral, leg_weight 0.5 of equity per leg (gross 1x). The paper's 5x leverage example (p. 13) is not used, so results stay comparable with the baseline. | [IMPLEMENTATION-ASSUMPTION] |
| 8 | Self-imposed limits: an entry may trade at most 15% of either leg's 20-day ADV; the size is then held. | [PAPER-DERIVED] (R4, daily limit) turned into a sizing rule: [PROPOSED-EXTENSION]. Shared with the baseline (`costs.limits.max_participation`). |
| 9 | Overall position limit of N days of ADV. | [PAPER-DERIVED] (R4). **Not modelled**: with single-day entries the 15% daily cap is always tighter than N = 100 days. |
| 10 | Costs, borrow, dividends, FX, period end, and no position before the cost statistics exist: identical to the baseline (rules 5b and 8-11 of `research/specs/baseline/parity_zscore.md`). | as classified there |

## Walk-forward neighbourhood

The grid is `entry_bound` [0.018, 0.036, 0.054] (1x, 2x and 3x the paper's
bound) by `exit_bound` [0, 0.009] (parity, or half the bound). It is an
[IMPLEMENTATION-ASSUMPTION] that puts the paper's values in a corner. Audit A3
showed that `neighbourhood_mean` favours corners under noise, so the selected
point is reported together with the fixed paper-value run. 6 combinations per
fold.

## Relative volume (H1): not a signal here

The paper's H1 is the reason this paper is about volume. It is deliberately
**not** used as an entry or exit signal:

1. **It is contemporaneous, not predictive.** In the model
   V1/V2 = 1 + chi/(1+theta), where theta is current arbitrage activity
   (equations file). A wide D goes with heavy arbitrage and relative volume
   near 1. Nothing in the model says what D does next: convergence arrives
   with a constant probability p (P2). Any forward-looking volume rule would
   be an empirical observation turned into a trading rule, and its direction
   would have to be invented.
2. **The relation is absent in our development data** (step 7:
   RD/Shell b = +0.016, t 0.44). Building a filter on it now and tuning it on
   the same data would be data snooping.

What the strategy takes from the volume side of SILTA is the self-imposed
limits (rules 8-9). A volume-conditioned variant can still be added later as
its own extension spec. It would need the direction of the rule fixed in
advance, and it would count as an extra trial in step 9.

## Pre-registered expectation and comparison

Recorded before the first real-data run:

- RD/Shell development data: D averages +7.1% and is above parity on 84% of
  days (100% in validation; step 7). The strategy will be short Royal Dutch /
  long Shell almost all the time, with few round trips. P&L is driven by
  changes in the premium plus dividend and borrow carry, not by many small
  convergences.
- SILTA predicts that this trade is unattractive for capital-limited
  arbitrageurs: that is why the discrepancy persists. A poor result is
  consistent with the paper, not evidence against it.
- Reported, whatever the outcome:
  1. single runs at the paper's values on `rd_shell` train and validation;
  2. the walk-forward over the development range, with the same folds, costs
     and selection rule as the baseline walk-forward (Sharpe -0.34, total
     -11.5%, audit 5b).
- No rule, bound or parameter is changed because of these results. Reed
  Elsevier and robustness come in step 9; OOS only after the freeze.

## Known gaps

- Parity is a constant. For RD/Shell the agreement-implied ratio moved by
  about 1% in 1997-2002 (share counts drift), which is about half of the entry
  bound.
- Convergence in the paper is an exogenous event; in the backtest it is D
  crossing parity. A trade can stay open for years, and is closed by force at
  the end of each evaluated period.
- The pre-1997 UK tax credit, which drove the RD premium (tax clienteles), is
  not modelled. It is the main economic reason the trade may not converge
  within 1987-99.
