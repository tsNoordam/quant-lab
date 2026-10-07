# Robustness and multiple testing (Step 9)

Date: 2026-10-07. Code: `quant_lab.backtest.robustness`, `quant_lab.backtest.stats`,
cases in `conf/robustness/default.yaml`, committed in 895df80 before these runs.

Strategies:

- `parity_zscore` (baseline, defaults 60 / 2.0 / 0.5);
- `silta_parity` (paper values 0.018 / 0).

All runs use the liquidity cost model unless a case says otherwise, and
next-close fills.

Reproduce:

    uv run python -m quant_lab.backtest.robustness data=rd_shell
    uv run python -m quant_lab.backtest.robustness data=reed_elsevier

Train and validation only. `+unlock_oos` was not used, and the runner refuses
it. Aggregates only (licensed data).

These numbers come from a scratch copy of the data outside git. Their trial
count includes every exploratory run logged there since Step 4. Rerun on a
clean checkout to get citable MLflow runs and your own trial count.

## 1. Cost, capital and leverage sensitivity (RD/Shell)

Sharpe, with total return for the walk-forward (WF). WF: 1991-1999, 9 folds,
parameters chosen per fold. Frozen values: train 1987-96, validation 1997-99.

| Case | parity_zscore WF | train | validation | silta_parity WF | train | validation |
|---|---|---|---|---|---|---|
| base | -0.34 (-11.5%) | -0.38 | -0.98 | -0.02 (-3.5%) | -0.13 | +0.14 |
| impact k 0.5 | -0.17 (-5.4%) | -0.20 | -0.75 | -0.00 (-2.1%) | -0.03 | +0.14 |
| impact k 2.0 | -0.40 (-13.5%) | -0.72 | -1.40 | -0.07 (-6.1%) | -0.30 | +0.13 |
| fallback spread 5 bps | -0.38 | -0.32 | -0.95 | -0.02 | -0.10 | +0.14 |
| fallback spread 20 bps | -0.39 | -0.50 | -1.04 | -0.04 | -0.17 | +0.14 |
| commission 10 bps | -0.41 | -0.50 | -1.16 | -0.04 | -0.17 | +0.13 |
| borrow 150 bps | -0.38 | -0.43 | -1.01 | -0.09 | -0.20 | +0.08 |
| stamp duty 50 bps | -0.51 (-17.5%) | -0.94 | -1.76 | -0.10 (-7.9%) | -0.32 | +0.12 |
| withholding 0% | -0.34 | -0.37 | -0.98 | -0.02 | -0.12 | +0.14 |
| withholding 25% | -0.34 | -0.39 | -0.98 | -0.02 | -0.13 | +0.14 |
| capital 10m | -0.55 | -0.86 | -1.79 | -0.05 | -0.34 | +0.12 |
| capital 100m | -0.70 | -0.89 | -2.32 | -0.03 | -0.31 | +0.07 |
| gross 2x | -0.39 (-25.6%) | -0.51 | -1.14 | -0.01 (-9.7%) | -0.15 | +0.19 |
| **zero cost** (labelled, not a result) | **+0.75 (+30.9%)** | +0.60 | +0.79 | +0.13 (+5.7%) | +0.43 | +0.19 |

**Stable region.** There is none with a positive net Sharpe.

- **`parity_zscore`.** Negative in every realistic cost case, by every
  measure. Its walk-forward Sharpe stays between -0.17 and -0.70.
- **`silta_parity`.**
  - Walk-forward between -0.10 and 0.00 in every case: flat at best.
  - Its only positive figures are the validation runs (+0.07 to +0.19).
    Each is a single trade, opened at the start of 1997 and closed by force
    at the end of 1999.

**Gross edge vs costs.**

- **`parity_zscore`.** Before costs there is mean reversion: walk-forward
  Sharpe +0.75, 8 of 9 test years positive. Costs remove it entirely. Even
  half the impact coefficient leaves it negative.
- **`silta_parity`.** Its gross edge is small: +0.13 walk-forward.

**Capacity.** Losses grow with capital: 10m and 100m books are worse than 1m.
The pair cannot absorb even a modest book at these cost levels.

**Withholding has no effect on the walk-forward.** The withholding rate
changes the train runs only. In the walk-forward test windows the baseline
held no long Royal Dutch position over any RD ex-dividend date: it was flat
on 14 of them and short on 4. Withholding only applies to long positions.

This is systematic, not a bug. The signal uses raw closes, so on an ex-date
RD's price drop makes RD look cheap. The strategy then buys RD just *after*
the ex-date.

**Leverage.** 2x gross roughly doubles the losses. The paper's 5x example is
not in the table. The engine does fill those targets (the fill test now
covers 2x), but at 5x a single train run loses 91% of equity. Once equity is
near zero, daily returns explode and the Sharpe ratio is meaningless.

## 2. Selection and walk-forward design (RD/Shell, WF Sharpe)

| Case | parity_zscore | silta_parity |
|---|---|---|
| base (neighbourhood mean, anchored, 4y train, 12m test) | -0.34 | -0.02 |
| selection = best | -0.36 | -0.01 |
| 3-year training window | -0.52 | -0.02 |
| rolling (not anchored) | -0.33 | -0.02 |
| 6-month test windows | -0.48 | -0.13 |
| wider grid that brackets the corners (A3) | +0.03 (5 entries in 9 years) | +0.02 (9 entries) |

**Where the walk-forward choices sit in the base grids.** The choice is a
grid corner in every fold:

| Strategy | Parameter | Choice, out of 9 folds |
|---|---|---|
| `parity_zscore` | `entry_z` | max (2.5) in 9 |
| `parity_zscore` | `window` | max (120) in 7 |
| `parity_zscore` | `exit_z` | min (0.0) in 7 |
| `silta_parity` | `entry_bound` | max in 9 |
| `silta_parity` | `exit_bound` | max in 9 |

**The training data keeps saying "trade less".** When the grid is widened,
the selection moves further out. `parity_zscore` then trades 5 times in 9
years, and the Sharpe goes to about zero because almost nothing is traded.
The A3 corner preference is not a selection artefact: it reflects a
cost-dominated objective.

The wide grid is reported as a sensitivity only. Adopting it after seeing
these results would be a choice made from the data.

## 3. Sub-periods, years, regimes, concentration (RD/Shell base walk-forward)

**Sub-periods.** The split at the UK budget of 2 July 1997 [EXTERNAL-RESEARCH]
ended dividend tax-credit repayments to pension funds:

| | parity_zscore | silta_parity |
|---|---|---|
| 1991-01 .. 1997-07-01 | -0.34 (-7.1%) | -0.11 (-4.2%) |
| 1997-07-02 .. 1999-12 | -0.37 (-4.8%) | +0.08 (+0.8%) |

**Calendar years.** Positive years:

- `parity_zscore`: 3 of 9;
- `silta_parity`: 3 of 9 (1992, 1996, 1999).

No single year carries either result.

**Volatility regimes.** Each day is classified by the pair's own trailing
60-day volatility, known the day before, against its expanding median:

| | parity_zscore | silta_parity |
|---|---|---|
| low vol (1,423 days) | -0.19 | -0.04 |
| high vol (775 days) | -0.54 | -0.01 |

The baseline does worse when the spread is volatile. There, z-score entries
are more often followed by further divergence.

**Trade concentration:**

| | parity_zscore | silta_parity |
|---|---|---|
| trades | 24 | 10 |
| share of absolute P&L from the top 10 days | 7% | 3% |
| share from the largest trade | 13% | 26% |
| winning trades | 63% | 40% |

The baseline wins most trades but loses on costs and on the losers.

The market regime against an index is not tested: there is no index in the
data. Out-of-sample is not tested: it stays locked until the freeze.

## 4. Multiple testing: deflated Sharpe ratio

Number of trials: **502** distinct strategy configurations evaluated on
RD/Shell, counted from MLflow (`count_trials`). That counts every walk-forward
grid point and every cost or capital variant. Reruns and fold-design variants
are not counted.

| | per-period SR | E[max SR] of 502 null trials | DSR | PSR vs 0 |
|---|---|---|---|---|
| parity_zscore WF | -0.021 | 0.049 | 0.001 | 0.16 |
| silta_parity WF | -0.001 | 0.040 | 0.027 | 0.47 |

Neither strategy shows skill, even before deflation (PSR vs 0 < 0.5). After
502 trials the bar is a per-period SR of about 0.04-0.05, i.e. 0.6-0.8
annualized. Any future candidate would have to clear it.

The baseline's returns are fat-tailed (kurtosis 17), which widens the
uncertainty further.

## 5. Reed Elsevier at frozen values (no tuning on this pair)

| Case | parity_zscore train / validation | silta_parity train / validation |
|---|---|---|
| base | -1.36 / -1.09 (-18.1%) | -0.06 / +0.05 (-0.4%) |
| impact k 0.5 | -1.12 / -0.81 | -0.05 / +0.09 |
| stamp duty 50 bps | -1.83 / -1.53 | -0.07 / -0.00 |
| zero cost (labelled) | -0.03 / +0.47 | +0.20 / +0.22 |

**On the validation pair the frozen strategies behave as on RD/Shell.**

- **`parity_zscore`.** Clearly negative after costs. Before costs it is
  barely positive in validation.
- **`silta_parity`.** About zero, with only 2-3 trades per period.

## Conclusion

Neither strategy has an edge after realistic costs on the development data.
This holds:

- across every cost, capital, leverage, selection and fold-design case;
- on the validation pair;
- after accounting for 502 trials.

The baseline has a gross mean-reversion edge that costs consume. The SILTA
arbitrageur is roughly flat, because the discrepancy rarely converges by more
than the round-trip cost. This is the paper's own mechanism: self-imposed
limits and costs keep arbitrage capital out, which is why the discrepancy
persists.

Per the golden rules, nothing is changed because of these results.

## Implications for step 10 (freeze)

- **Freeze as specified, no tuning.** Freeze both strategies at their current
  config values: baseline 60 / 2.0 / 0.5, SILTA 0.018 / 0.
- **Pre-register the expectation:** no positive net Sharpe out of sample. A
  positive OOS result would need DSR > 0.95 at the trial count frozen at
  step 10 before it counts as evidence.
- **The out-of-sample run is informative even so.** It tests whether the
  limits-to-arbitrage pattern (gross edge, net loss) holds in 2000-02 and on
  Rio Tinto. Whether to run it is the user's decision.

## Erratum 2026-10-07 (freeze audit, A1 and A2)

Two defects found at the freeze audit change some numbers above. The original
figures are left as reported.

- **A1:** the RD/Shell parity is now 6.9558 instead of 6.863.
- **A2:** no position is taken before the cost statistics exist.

Corrected `silta_parity` figures (clean rerun at 9498679; details in
`research/reports/audits/2026-10-07-freeze.md`):

| Run | Corrected |
|---|---|
| RD/Shell train | Sharpe -0.08 (-9.4%), 28 entries |
| RD/Shell validation | unchanged |
| RD/Shell walk-forward | +0.02 (-0.7%) |
| Reed train | +0.02 (-1.8%) |
| DSR | 0.09 |

`parity_zscore` is unchanged. **No conclusion changes:** neither strategy has
an edge after costs.
