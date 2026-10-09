# Replication rule under lab conventions: de Jong et al. threshold arbitrage (`dejong_threshold`)

Status: the trading rule is [PAPER-DERIVED] (de Jong, Rosenthal & van Dijk
2009, Tables IV-V, the benchmark 10%/5%/12 months). Execution, costs, P&L and
sizing are the lab's, so the run answers ROADMAP step 18's question: what is
left of the paper's result under our standard.

- **Code:** `src/quant_lab/strategies/dejong_threshold.py`.
- **Parameters:** `conf/strategy/dejong_threshold.yaml`.
- **Run with:** `strategy=dejong_threshold`.

The paper's own conventions are reproduced separately by
`quant_lab.backtest.dejong` (step 16). The convention waterfall between the two
is in `quant_lab.models.dejong_standard`.

Written before any lab-engine run of this strategy on real data. Nothing is
chosen on the data: the thresholds and horizon are the paper's benchmark.

## Rules

| # | Rule | Classification |
|---|---|---|
| 1 | D_t = ln(P_a,t / P_b,t) - ln(parity) on raw closes in the common currency, with the lab's `data.parity_ratio` (RD/Shell 6.9558, point in time; Reed/Elsevier 1.538) | [PAPER-DERIVED] (E1); the point-in-time RD/Shell ratio replaces the workbook's 6.863 (audit A1, look-ahead) |
| 2 | Open when \|D_t\| >= 10% and \|D_t-1\| < 10% (a crossing): short the expensive leg, long the cheap one | [PAPER-DERIVED] (identified, D6) |
| 3 | Close at the first close with \|D\| <= 5%, or after 260 closes | [PAPER-DERIVED] (Table IV benchmark; identified, D4) |
| 4 | At most one position per pair; no minimum gap between entries (`entry_gap: 0`) | [PAPER-DERIVED] one position; the paper's 22-day gap is a by-product of its T-bill padding (D5): [IMPLEMENTATION-ASSUMPTION] to drop it |
| 5 | A missing D (a missing close) means flat | [IMPLEMENTATION-ASSUMPTION] |
| 6 | Decision on close t, fill at close t+1 (`next_close`) | [IMPLEMENTATION-ASSUMPTION], the lab's execution; the paper trades on close t (D4) |
| 7 | Dollar-neutral, leg_weight 0.5 of equity per leg (gross 1x) | [IMPLEMENTATION-ASSUMPTION]; the paper is 2x gross on Regulation T margin. Sharpe ratios do not depend on it |
| 8 | Costs, borrow, dividends (with withholding), FX, participation cap, period end, warm-up: the lab's (`research/specs/baseline/parity_zscore.md`, rules 5b and 8-11) | as classified there |

## Data and periods

- The lab's validated pairs only: RD/Shell (development) and Reed/Elsevier
  (validation pair), on train and validation.
- The out-of-sample periods (2000 on) and Rio Tinto stay locked
  (`research/reports/data_decisions.md`). Running them needs the user's
  explicit `+unlock_oos=true`.
- The other nine twins have no lab panels. The waterfall covers them under the
  paper engine.

## What would change the conclusion

With 3-5 positions per pair and period, no Sharpe ratio here is
distinguishable from zero. The run measures whether the result survives the
lab's execution and costs, not whether there is an edge. The pooled answer
across twins is the waterfall's calendar-time Sharpe ratio.
