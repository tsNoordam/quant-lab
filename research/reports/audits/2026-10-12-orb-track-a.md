# Audit: track-A backtest of the course's session rules on ES (step 23)

Date: 2026-10-12.

**Scope.**

- **Code:**
  - `src/quant_lab/backtest/orb.py` with `conf/orb/backtest.yaml`;
  - `src/quant_lab/models/orb_stats.py` (inputs, R4 quantiles);
  - `src/quant_lab/data/es_futures.py` (sessions, roll, previous close,
    usable rule).
- **Run:** the user's run `17635fdf…` (0 of 70 configurations positive
  after base costs).
- **Audited commit:** 7a65518.
- **Reviewers:** the read-only `backtest-auditor` agent (A-findings) and the
  `red-team` agent (RT-findings), asked to attack the *negative* result.
- Neither agent edited files, and neither had the licensed data. Their
  real-data claims were settled by tests the user ran.

**Gate at 7a65518:** pytest 510 passed, 50 skipped; ruff clean.

**Verdict at 7a65518: WARNING** from the auditor. No look-ahead or cost
defect could make a losing rule look profitable. Four fill and sample
defects were confirmed.

**After the fixes: PASS with documented WARNINGs.**

- Gate at 21b2762: pytest 725 passed, 85 skipped, 1 xfailed; ruff clean.
- The user's rerun on the fixed engine is `8c5e84e4…`.
- The real-data falsification test passed on the user's machine (9/9 in
  `tests/integration/test_orb_audit.py`).

## Findings and resolution

| ID | Severity | Finding | Status | Test | Fix |
|---|---|---|---|---|---|
| RT-1 = A2 | WARNING (against the rules) | A target already passed at entry was filled at the target, behind the entry, instead of at the market (a marketable limit) | CONFIRMED (test failed) | `test_passed_target_fills_at_the_market_not_behind_the_entry` | cb766c7 |
| RT-8 | WARNING | A session without bars blanked the rolling volume statistic and silently removed the next 20 sessions from trading (up to about 120 sessions) | CONFIRMED (test failed: 20 sessions) | `test_a_session_without_bars_does_not_exclude_the_following_sessions` | cb766c7: liquidity statistics over sessions with bars |
| A1 | WARNING (for the rules) | Whether a trade existed depended on the entry bar's open (known after the decision): trades opening beyond the stop were dropped; a stop on the entry bar filled at the stop, not the worse open | CONFIRMED (test failed) | `test_entry_bar_opening_beyond_the_stop_is_a_trade_stopped_at_the_open` | 21b2762 |
| A3 | WARNING (for the rules) | Midpoint and 0.5-gap stops and some targets were off the 0.25 tick grid | CONFIRMED (2 tests failed) | `test_stop_fills_lie_on_the_tick_grid`, `test_off_grid_target_rounds_away_from_the_entry` | 21b2762: rounded away from the entry |
| A4 | WARNING | `usable` uses whole-session coverage (after-the-fact); the $30 usable-vs-with_bars gap | REJECTED as verdict-changing (test passed on real data: no configuration or family turns positive) | `test_unusable_sessions_do_not_change_any_verdict` | 3212163: the summary reports the signed difference, its configuration and the with_bars family verdicts |
| A5 | WARNING | R4 targets fitted on train, scored on development, which includes train | Documented | n/a | `orb_backtest.md` §4: R4 is negative on validation alone too |
| A6 | WARNING | "gross" keeps the fill conventions; its null is not 0 | Measured | `test_fill_conventions_on_driftless_walks` (8 seeds, paired) | 3212163: scenario labelled. Engine nulls: base about −$3, optimistic about +$1 before costs |
| A7 | WARNING | The same-bar stop+target count promised by O10 was never reported | Resolved | `test_results_report_the_same_bar_share` | 3212163: `share_both_touch` per configuration |
| A8 | WARNING | Causality test did not touch the entry bar or the R1c re-entry; no test of the R4 quantiles | REJECTED (tests pass); coverage gap closed | `test_every_trade_ignores_the_entry_bar_after_its_open_and_later_bars` (40 seeds × 6 rules), `test_r4_quantiles_ignore_validation_and_unusable_sessions` | none needed |
| A9 | WARNING (low) | The R2 stop/exit grid and R4 q=0.5 were committed after step 22 had computed gap and excursion statistics on the same data: implicit trials outside the 70 | Documented | n/a | none; every configuration fails, so no selection benefited |
| A10 | PASS | yaml described the R2 stop as "beyond the entry"; it is measured from the RTH open | Fixed | n/a | 3212163 |
| A11 | PASS | Decision vs entry, range window, R3 "unfilled before entry", R1c timing, R2 minute-0 to minute-1, impact lag, train-only R4, OOS lock, same-contract previous close | n/a | existing and new structural tests | n/a |
| RT-2 | WARNING | "Realistic costs" is the conservative end: 1 tick on every market leg, trade-through, stop first, slippage at the close | Resolved as a sensitivity | `test_fill_conventions_on_driftless_walks` | 3212163: optimistic bracket. 2 of 70 configurations positive, best +$0.28 per trade |
| RT-3 | WARNING | Compare with a null from the same real bars (random direction) rather than a Gaussian walk | Not run (open) | n/a | Optional; the optimistic bracket and the per-configuration intervals already bound the edge |
| RT-4 | WARNING | Cost relative to risk was much higher at the 2010 price level; the regime differs from the course's 2021+ evidence | Measured | n/a | 3212163: per-year table. Gross positive in 3 of 11 years, no trend toward recent years |
| RT-5 | WARNING | Validation-positive cells are noise | Measured | n/a | Intervals per configuration; best validation cell t ≈ 0.7 |
| RT-6 | WARNING | The DSR clause has little power; "no edge" must state what it rules out | Documented | n/a | `orb_backtest.md` §2, §7: no configuration's 95% interval exceeds +$0.5 per trade; SR0 and var_sr reported |
| RT-7 | WARNING | Fidelity: POC/VAL stops, breakeven, the 5-minute window and the proprietary IVB levels are not tested; the opposite-side stop is not a course stop | Documented | n/a | `orb_backtest.md` §7; candidate families need a new pre-registration and trial count |

## Effect of the fixes on the result

| | 17635fdf (before) | 8c5e84e4 (after) |
|---|---|---|
| Configurations positive, base | 0 of 70 | 0 of 70 |
| Families surviving the kill criterion | 0 of 26 | 0 of 26 |
| Median net $/trade | −33.08 | −33.20 |
| Best net $/trade | −18.52 | −18.90 |

The fixes moved individual configurations by a few dollars in both
directions, and no verdict changed.
