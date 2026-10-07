# Re-audit: rd_shell walk-forward after fixes A1, A2, A5 (step 5b)

| | |
|---|---|
| Date | 2026-10-07 |
| Scope | `git diff ffcf775..50333bf`: A2 locked quotes `c4443f7`, A5 FX conversion `d42fdd5`, A1 total-return dividends `50333bf`. Applied to the rd_shell walk-forward, train + validation 1987-1999. OOS and rio_tinto not touched. |
| Prior audit | `2026-10-07-rd_shell-walkforward.md`, verdict FAIL (A1) |
| User decisions (implemented, not audited) | Longs receive dividends net of per-leg withholding: Dutch 15% (UK-NL treaty), UK 0%; 0% and 25% as sensitivity runs. Shorts pay the full dividend. The signal stays on raw closes (paper definition; revisit in step 6). The pre-1997 UK tax credit is not modelled. |
| MLflow runs @ 50333bf | `0276593b477c450d982f15acb41387ce` (run_label=baseline), `bbba597ba4b747aa8ad88690ec12dbbe` (wht0), `7b9fd63f33454e5b9429bdb0faac8557` (wht25). All tagged git_dirty=true only because of untracked files outside the project code (`node_modules/`, `package*.json`, `.claude/claude.json`). |
| Gate | Before: 205 passed. After resolution: 208 passed, 1 xfailed (strict, B6); ruff clean. |
| **Verdict** | **WARNING.** No FAIL. Open warnings: B5, B6, B10, and A3 (carried over). |

## Result

| | Before fixes (`81dcbbf2`, bfe79e7) | After fixes (`0276593b`, 50333bf) |
|---|---|---|
| Walk-forward Sharpe | -0.03 | **-0.34** |
| Total return | -1.8% | **-11.5%** |
| Max drawdown | -4.4% | -11.6% |
| Entries / orders | 23 / 92 | 24 / 96 |
| Positive folds | 5 of 9 | 3 of 9 |
| Distinct parameter sets | 2 | 4 |
| Net dividend cash | not booked | -£48.1k (-4.8% of capital) |
| Spread + impact + tax | £116.7k | £134.0k |

The auditor decomposed the change by removing one fix at a time from HEAD:

| Change | Effect on total return |
|---|---|
| Dividends | -8.5pp |
| FX conversion cost | -0.6pp |
| A2 spread fix | -0.5pp |

The dividend effect has two parts. About -4.8pp is direct dividend cash. The rest (about -3.7pp) comes from re-selection: training scores now include dividends, so folds 2-4 choose different parameters.

**Withholding sensitivity:** 0% gives -11.54% and 25% gives -11.51%, the same as the 15% baseline. In the test windows, no long Royal Dutch position is ever held across an RD ex-date. All dividend cash comes from short legs, which pay in full (short RD -£48.9k, short Shell -£30.8k), and from long Shell (+£31.6k, which has no withholding). The 0% run differs only through a different selection in fold 7. On this data the withholding assumption does not matter.

## Findings

| ID | Severity | Area | Finding |
|----|----------|------|---------|
| B1 | PASS | look-ahead | Dividend timing is correct. The holder of record is the position at the previous close. A buy filled at the ex-date close does not receive the dividend; a sale at the ex-date close does. The cash on ex-date t uses only rows t-1 and t. The FX rate cancels in the implied dividend. An injected dividend left earlier equity exactly unchanged. |
| B2 | WARNING | test coverage | No structural test exercised the dividend path. The synthetic data has adj_close == close, and the existing shocks scale close and adj_close together. |
| B3 | PASS | data | The 50 bps threshold is safe. There are 25 dividends per leg (2 per year), with yields of 112-423 bps. No residual falls between 20 and 75 bps. Noise is at most 11 bps. No ex-date was lost to the inner join. The RD/Shell dividend ratio is close to parity, so both legs' total-return indices use gross dividends on the same basis. |
| B4 | PASS | accounting | Signs and withholding are correct. The reference ledger books dividends independently and reconciles to 1e-10. VectorBT sizes on its own value rather than net equity, so leg weights drift by at most 1.8%, the same kind of approximation as the documented init_cash sizing. |
| B5 | WARNING | research | Raw-close signal with total-return P&L: 8 of 24 entries come within 5 days after an ex-date, about 4x the base rate. The raw relative price reads one leg's ex-date drop as a mispricing, and the short leg then pays the dividend. This follows from the user's decision to keep raw closes (step 6); it is not a code defect. |
| B6 | WARNING (HYPOTHESIS) | costs / data | From 1997-Q3 to 1998-Q1, valid RD quotes have a median half-spread of about 90-97 bps, against 8-17 bps for Shell. A2 does not cover this, and the full-sample median check misses it. About 0.9% of capital in extra cost; the error makes costs too high, not too low. |
| B7 | PASS | costs | A2 fix as specified: tradable spread is `ask > bid`, plus a `locked_quotes` validation warning. |
| B8 | PASS | costs | A5 fix as specified: 3 bps charged on the fx leg only. |
| B9 | PASS | costs | The flat_bps path books dividends. It still has no borrow charge, which is acceptable for a labelled sensitivity case. |
| B10 | WARNING | stats | Sharpe -0.34 is about one standard error (SE ≈ 0.33). The experiment now holds 5 walk-forward runs on the same validation years. None of them may drive strategy changes. |

## Resolution

| Finding | Status | Test | Fix commit |
|---|---|---|---|
| B2 | **CONFIRMED** (coverage gap) → closed | `tests/structural/test_dividend_causality.py::test_future_dividends_do_not_change_past_equity`, `::test_dividend_on_a_dropped_day_is_booked_on_the_next_joint_row` (both pass) | `599b25d` |
| B6 | **CONFIRMED.** RD's quarterly median half-spread is 4-8x Shell's in 1997-Q2..1998-Q1, against 0.4-0.9x in other quarters. | `tests/data/test_quote_regimes.py::test_rd_quotes_have_no_implausibly_wide_regime` (strict xfail); `tests/data/test_datastream.py::test_a_quarter_of_wide_quotes_is_reported_even_if_the_full_sample_median_is_fine` | `9ad91e4`: validation now emits `wide_quote_regime`, which also flags Elsevier in 1996-98 and Shell in 1987-Q4. **Treatment open:** the quotes are still costed as quoted, which is conservative. Treating them as missing would lower costs and needs a documented source; it should not be done to improve the result. |
| B5, B10 | WARNING stands, documented | none | none |
| A3 (prior audit) | WARNING stands: selection still lands on the corner entry_z = 2.5 | existing characterization test | none |
| Minor: stale comment in `walkforward.py`, spec rule order | fixed | none | `9ad91e4` |
