# Audit: rd_shell walk-forward (parity_zscore, liquidity costs, next_close)

| | |
|---|---|
| Date | 2026-10-07 |
| Scope | `uv run python -m quant_lab.backtest.walkforward data=rd_shell`: train + validation, 1987-01-01 to 1999-12-31. OOS not touched. |
| Audited commit | `ea1827b`. Nothing in `src/` or `conf/` changed since `bfe79e7`. |
| MLflow runs | `81dcbbf2e02f4ecd9232a9f7eb45a920` (bfe79e7, clean): audited. `131d36012fec49c0aa17605f8c1e306e` (ba535b0, after the A4 fix): same metrics, adds cost/trial metrics. Dirty only because of untracked `node_modules/` and `package*.json` outside the project code. |
| Gate | Before: pytest 184 passed; ruff check and ruff format clean. After: 187 passed, 3 xfailed (strict); ruff clean. |
| Auditor | `backtest-auditor` agent (read-only) |
| **Verdict** | **FAIL.** A1 (P&L ignores dividends) is CONFIRMED and not yet fixed. |

Reported result (unchanged by this audit): walk-forward Sharpe -0.03, total
return -1.8%, max drawdown -4.4%, 9 folds, 23 entries, 92 orders, gross
leverage 1.0, 216 training backtests behind the selection.

## Agent report (summary of findings)

| ID | Severity | Area | Finding | Evidence |
|----|----------|------|---------|----------|
| A1 | FAIL | P&L | VectorBT fills and marks on unadjusted closes and nothing books dividends. A short across an ex-date gains the price drop without paying the manufactured dividend; a long loses the drop and gets nothing. The signal also sees ex-date jumps as relative-price deviations. | `run.py:138` (`close_*`), `run.py:121` |
| A2 | WARNING | costs | Royal Dutch quotes (1996-1999): about 40% of quoted days have bid == ask and a few are crossed. `ask >= bid` keeps locked quotes as a valid zero spread, so the 20-day median can be 0: 8 of 46 RD orders paid 0 bps half-spread, and an outlier paid about 100 bps. RD has no quotes before 1996 (fallback 10 bps). | `costs.py:36` |
| A3 | WARNING | stats | Under pure noise, `neighbourhood_mean` picks a grid corner about 47% of the time (uniform: 33%), because corners average over fewer neighbours. The run picked the corner (120, 2.5, 0.0) in 8 of 9 folds and (80, 2.5, 0.0) once: the grid does not bracket the chosen region. | `walkforward.py:104-118` |
| A4 | WARNING | logging | The walk-forward run logged no cost metrics, n_orders, leverage or trial count. It logged `strategy.window/entry_z/exit_z` and `backtest.period=train`, none of which it uses. | `walkforward.py:245-250` |
| A5 | WARNING (HYPOTHESIS) | costs | RD is traded as a GBP-converted leg with no FX conversion cost. Its GBP price uses Datastream's daily FX rate, and when that rate was fixed relative to the Amsterdam close is undocumented. | `datastream.py:147`; `costs.py` |
| A6 | WARNING | stats | Sharpe -0.03 with an annualised SE of about 0.33 over roughly 9 years: no evidence either way. Fold 9 (1999, -3.5%) is the whole loss. Only 2 distinct parameter sets were chosen. The validation years 1997-1999 are now used up as walk-forward test folds. | MLflow `folds.csv` |
| A7 | PASS | look-ahead | Checked and passed: fold isolation (train uses data up to train end, test up to test end), z-score/cost/ADV warm-up only before the test start, 5-day embargo, OOS cut at `split.validation.end` (last test bar 1999-12-30), decision→fill shift, cost and cap stats lagged, each test window starting flat and closing on its last bar with costed exits, both legs filled at t+1 closes (no stale-close capture), inner join on both-markets-open dates, no jump at the 1999 euro changeover. Grep found no `shift(-`, bfill, interpolate, `center=True` or merge_asof in `src/`. | `tests/structural/` |
| A8 | PASS | logging | `backtest.period` and `unlock_oos` are not read by the walk-forward path. | `walkforward.py:132-147` |

Other checklist items, all PASS: impact (k = 1, daily sigma, sqrt of
shares/ADV), borrow (50 bps/yr on the short leg), commission (5 bps per
order), capacity (largest order is about 4% of ADV; the 15% cap never binds at
£1M).

**Size of A1 (agent estimate, not covered by a test).** The agent summed held
weight × ex-dividend yield, using jumps in ln(adj_close/close) above 50 bps as
the ex-dates. The omitted dividend P&L comes to about -4.2% of capital, mostly
from short-RD positions held across RD ex-dates. That is more than twice the
reported -1.8%. A dividend-consistent figure would be roughly -6%. This number
is for orientation only: the fix will settle it.

**Not checked:** whether raw-price parity is the right signal for an equalized
dividend pair (step 6, paper extraction); the FX fixing time in the workbook;
VectorBT target-percent behaviour beyond the existing reconciliation tests;
survivorship (the sample is the paper's pairs). No OOS run.

## Resolution

Before a finding was marked, each falsification test was run with
`--runxfail`. The three findings left unfixed are kept as
`xfail(strict=True)`: the gate stays green, and the test turns red as soon as
the defect is fixed, which forces the marker to be removed in the fix commit.

| Finding | Status | Test | Fix commit |
|---|---|---|---|
| A1 dividends omitted from P&L | **CONFIRMED** (+1.50% phantom P&L on a 3% dividend at leg weight 0.5) | `tests/integration/test_dividends.py::test_short_leg_pays_the_ex_dividend` (strict xfail) | open |
| A2 locked quotes priced as zero spread | **CONFIRMED** | `tests/unit/test_costs.py::test_locked_quotes_are_not_a_zero_spread` (strict xfail) | open |
| A3 neighbourhood selection favours corners | **CONFIRMED** (WARNING stands, documented here) | `tests/unit/test_walkforward.py::test_neighbourhood_mean_favours_grid_corners_under_noise` (characterization) | none: changing the selection rule is a research decision, not an audit fix |
| A4 incomplete walk-forward logging | **CONFIRMED** → fixed | `tests/integration/test_backtest_run.py::test_walk_forward_run_logs_costs_trades_and_trials` | `ba535b0` |
| A5 no FX conversion cost | **CONFIRMED** (the model has no FX term) | `tests/integration/test_fx_costs.py::test_cost_model_prices_fx_conversion_for_foreign_currency_legs` (strict xfail) | open |
| A6 statistical weight | WARNING stands, documented | none (descriptive) | none |
| A7 look-ahead / fold mechanics | PASS | existing `tests/structural/` | none |
| A8 `backtest.period` cosmetic | **REJECTED** as a defect, regression guard added | `tests/structural/test_walkforward_causality.py::test_backtest_period_and_oos_unlock_do_not_affect_walk_forward` | none |

## What the open fixes need (decisions, not audit work)

- **A1:** use total-return accounting for both legs: credit dividends on
  longs and charge manufactured dividends on shorts. The withholding-tax
  treatment for the Dutch leg is an [IMPLEMENTATION-ASSUMPTION] and must be
  stated. Separately, decide whether the signal uses raw or dividend-adjusted
  relative price; that is a strategy-rule decision and belongs to step 6/8.
- **A2:** treat locked and crossed quotes as missing, and add a quote-sanity
  check (share of locked quotes, crossed count, spread outliers) to
  `quant_lab/data/validation.py`, tested in `tests/data/`.
- **A5:** add a `costs.fx_conversion_bps` term charged on orders of a leg
  converted with `fx_per_unit`, labelled as an assumption. Record the FX
  source timing in `data/metadata/datastream_dlc.json`.

Once these are fixed, re-run the walk-forward on train+validation only. Do not
tune anything in response to the new number.
