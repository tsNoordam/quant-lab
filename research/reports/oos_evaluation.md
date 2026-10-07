# One-shot out-of-sample evaluation (step 11)

Date: 2026-10-07.

**How it was run.** The user ran it once, on their machine:

- on a clean checkout of `ff1e9eb`, tags `freeze-parity_zscore` and
  `freeze-silta_parity`;
- command: `uv run python -m quant_lab.backtest.oos +unlock_oos=true`;
- MLflow summary run: `c5a6c503f45a4d5e818a5b96c27b3ddb` (experiment
  `oos.evaluation`).

It is evaluated strictly against `research/specs/freeze/preregistration.md`.
Nothing was changed or rerun after the result was seen.

## Primary results (net of the frozen liquidity cost model)

Annualized Sharpe ratios. Gross means the zero-cost secondary case.

| Pair | Strategy | Net Sharpe | Net total return | Gross Sharpe | Entries | Largest trade share | DSR | PSR vs 0 | Holm | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| rd_shell | parity_zscore | -0.12 | -2.1% | +0.67 | 21 | 0.12 | 0.058 | 0.42 | no | no evidence of edge |
| rd_shell | silta_parity | +0.13 | +2.1% | +0.35 | 9 | 0.39 | 0.280 | 0.59 | no | not evaluable (pre-declared) |
| reed_elsevier | parity_zscore | -0.54 | -9.4% | +0.98 | 23 | 0.20 | 0.011 | 0.18 | no | no evidence of edge |
| reed_elsevier | silta_parity | -0.04 | -3.6% | +0.06 | 2 | 0.54 | 0.192 | 0.47 | no | not evaluable (too few entries) |
| rio_tinto | parity_zscore | -0.27 | -18.8% | +0.76 | 61 | 0.07 | 0.002 | 0.24 | no | no evidence of edge |
| rio_tinto | silta_parity | -0.28 | -41.0% | +0.84 | 123 | 0.04 | 0.023 | 0.23 | no | no evidence of edge |

**Secondary hypothesis (limits to arbitrage):** `parity_zscore` has gross >= 0
and net < 0.

- rd_shell: **holds**.
- reed_elsevier: **holds**.

## Against the pre-registered predictions

| Prediction (P) | Outcome |
|---|---|
| No "evidence of edge" verdict in any of the 6 runs (0.95) | **Held.** No run reached even PSR vs 0 > 0.6; every DSR < 0.3 |
| parity_zscore net Sharpe < 0 on RD/Shell (0.75) | **Held** (-0.12) |
| parity_zscore net Sharpe < 0 on Reed Elsevier (0.75) | **Held** (-0.54) |
| parity_zscore net Sharpe < 0 on Rio Tinto (0.85) | **Held** (-0.27) |
| Limits-to-arbitrage pattern on RD/Shell (0.6) | **Held** (gross +0.67, net -0.12) |
| Limits-to-arbitrage pattern on Reed Elsevier (0.6) | **Held** (gross +0.98, net -0.54) |
| silta_parity RD/Shell: 1-3 entries | **Failed**: 9 entries. The premium crossed the bounds more often than expected. The run stays not evaluable as pre-declared, whatever its sign (+0.13) |
| silta_parity Reed Elsevier: few trades, \|Sharpe\| < 0.5 | **Held** (2 entries, -0.04) |
| Surprise thresholds: net parity_zscore > 0.8 on RD/Shell or Reed; any Rio Sharpe > 0.5 with >= 10 entries | **Not reached** |

## Reading

1. **No edge out of sample, as in development.**
   - Neither strategy shows evidence of a positive net edge on any pair.
   - The bar was high, and stated in advance: an annualized Sharpe of about
     1.5-1.8. None of the six runs comes anywhere near it. The best is +0.13,
     and that run was pre-declared not evaluable.
2. **The gross-edge, net-loss pattern holds out of sample.** The baseline's
   gross Sharpe is positive on all three pairs (+0.67, +0.98, +0.76; the
   rio_tinto pattern was not pre-registered and is reported as exploratory),
   and it is negative after realistic costs on all three. This matches the
   development result (gross +0.75, net -0.34 in walk-forward) and the
   paper's mechanism: transaction costs and capacity limits keep arbitrage
   capital from closing twin-share discrepancies.
3. **`silta_parity` on Rio Tinto lost 41% with 123 entries.**
   - Gross it was +0.84 (Sharpe), so costs turned it into a large loss.
   - With parity 1.0 and the 180 bps bound, the deviation from parity crosses
     the bounds very often.
   - Rio Tinto's closes are about 10 hours apart, so part of that crossing is
     probably the non-synchronous noise the pre-registration warned about. It
     reverses on its own and pays costs on every trip.
   - This is an explanation, not a test: no further runs on the OOS period are
     allowed, and none were made.
4. **What this does and does not show.**
   - The power statement applies: about 690 OOS days on RD/Shell and Reed
     Elsevier give a standard error of about 0.6 on an annualized Sharpe.
   - These results rule out a large edge. They do not rule out a small one.

## Diagnostics

The pre-registered diagnostics are in the MLflow summary run's artifacts:

- `oos_results.csv`: the secondary cases `stamp_duty_50` and `impact_k_0.5`,
  traded orders, ex-date entry share, and SR0 per run;
- `oos_years.csv`: yearly net, gross and cost drag;
- `oos_subperiods.csv`: RD/Shell and Reed split at 2002-07-01; Rio Tinto split
  at 2000-01-01, to separate the part that shares the development calendar.

They are to be appended here unchanged. They do not affect the verdicts above,
which were fixed by the primary table alone.

## Conclusion of the project's main question

Maymin's mechanism describes these twin pairs well. Small, persistent
deviations from parity exist, and a mean-reversion trade on them is profitable
before costs. But realistic trading costs absorb the gain, in development
(1987-1999) and out of sample (2000-2002, and Rio Tinto 1996-2002) alike.

Neither the replicated relative-volume relation (H1: not found in our data,
step 7) nor a trade on parity itself (`silta_parity`) produced a tradable edge.
The research result is negative and was pre-registered as the most likely
outcome. The OOS period is now used and cannot be reused for these strategies.
