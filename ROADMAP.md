# Roadmap

Work proceeds in numbered steps. A step is done when its code, tests, docs and
commit are pushed and the user has confirmed it on their machine. Only then is
the next step started (see "Working in steps" in CLAUDE.md).

## Done

| Step | What | Commit |
|---|---|---|
| 1 | uv project, single `quant_lab` package, locked dependencies | 267df81 |
| 2 | v3 scaffolding, DVC-safe `.gitignore`, `CLAUDE.md`, Bash guard hook | 9dfc488 |
| 3 | DVC pipeline, validated preprocessing, synthetic twin pair | e7cbddf |
| 4 | Hydra + VectorBT + MLflow backtest, provenance tags, OOS lock | 0be0676 |
| 4a | Datastream DLC ingest (date repair, units, holidays) | ad06c25 |
| 4b | Liquidity-scaled costs, borrow, participation cap, VectorBT reconciliation | 0f891be |
| 4c | Locked sample design, walk-forward, Unilever dropped | bfe79e7 |
| 5 | `backtest-auditor` agent + audit workflow | ea1827b |
| 5a | First audit: rd_shell walk-forward. Verdict FAIL (A1 dividends); A4 logging fixed | ffcf775 |
| 5b | Fixes A1 (total-return dividends), A2 (locked quotes), A5 (FX cost); re-audit verdict WARNING. Walk-forward Sharpe -0.34, total -11.5% | befb58f |
| 6 | Paper extraction: `research/{extraction,equations,methodology,assumptions,evidence}/maymin_silta.*`; parity checked against the equalization agreements | d063320 |
| 7 | SILTA regressions (`quant_lab.models.silta`), Newey-West as in R sandwich, causal variant, chi check. H1 not supported on 1987-99 data (RD/Shell b=+0.02, t 0.4; Reed Elsevier b=+0.08, t 1.9, sign unstable); `research/reports/silta_replication.md` | 5079cb1 |
| 8 | Strategy registry; `silta_parity` (the SILTA arbitrageur: deviation from parity, 180 bps entry, exit at parity) with replication/extension specs and `run-backtest` skill. RD/Shell: train Sharpe -0.12, validation +0.14, walk-forward -0.02 (-3.5%) vs baseline -0.34 (-11.5%); cost-dominated, no edge after costs. `research/reports/silta_parity_rd_shell.md` | b555c5e, 21b18c9 |
| 9 | Robustness runner (`quant_lab.backtest.robustness`), deflated Sharpe and MLflow trial count. 19 cases x 2 strategies: no positive net Sharpe in any realistic cost/capital/leverage/selection case; baseline gross WF Sharpe +0.75 consumed by costs; DSR 0.001 / 0.027 at 502 trials; Reed Elsevier at frozen values agrees. `research/reports/robustness_step9.md` | 895df80, 0d96ef1 |
| 10 | Freeze audit (auditor + red-team): FAIL fixed. A1 RD/Shell parity carried OOS share counts -> 6.9558; A2 warm-up zero-size positions and zero-cost orders -> fixed. OOS evaluation code and pre-registration frozen (`conf/oos/`, `research/specs/freeze/preregistration.md`); n_trials 600. Tags `freeze-parity_zscore`, `freeze-silta_parity`. `research/reports/audits/2026-10-07-freeze.md` | ff1e9eb |
| 11 | One-shot OOS evaluation on the frozen tag (run once by the user, MLflow c5a6c503): no evidence of edge in any run; parity_zscore net -0.12 / -0.54 / -0.27 vs gross +0.67 / +0.98 / +0.76 (limits-to-arbitrage pattern holds); silta_parity RD/Shell not evaluable (pre-declared), Reed too few entries, Rio -41%. `research/reports/oos_evaluation.md` | bc3a8e8, 4131fc9 |
| 12 | Final report (`research/reports/final_report.md`, `research-report` skill); `quant_lab.reproduce` checks 10 headline development numbers (10/10); CI on synthetic data (`.github/workflows/ci.yml`); fresh clone without data: 268 passed, 11 real-data skips | a84c952 + (this step) |

## Notes from the steps

Open from the audits (decisions, not fixes): B6 treatment of RD/Elsevier
1996-98 wide quotes (needs a source); A3 corner-biased selection (documented
in step 9 as cost-driven). Rio Tinto Ltd withholding: settled at the freeze
(fully franked dividends, 0%).

Settled in step 6: the paper's relative price uses raw prices (A7 in
`research/assumptions/maymin_silta.md`), so the signal stays on raw closes.
Found in step 6: the paper's twin sample is 2002-04-25..2007-04-24, which our
data does not cover, so step 7 tests H1 on an earlier, disjoint period instead
of replicating Table VI numbers. Also: `shares_outstanding` (NOSH) is not
split-adjusted while volume is, so the turnover check overstates pre-split
turnover (less sensitive, never a false failure); fix before relying on it.

Found in step 7: chi is measured in value traded as well as shares (RD and
Shell shares differ in size ~6.9x); H2 calibration (eq. 1) deferred, since only
~1-13% of development days lie inside the 180 bps bound. Block bootstrap and a
differenced specification of the step 7 regression were not run (open).

Decided in step 8: the paper has no trading rule, so there is no replication
strategy (`research/specs/replication/maymin_silta.md`); relative volume (H1)
is not used as a signal (contemporaneous, and absent in our data); the
walk-forward grid now lives in each strategy's config (`strategy.grid`).

Found in step 9: with the raw-close signal, the baseline buys Royal Dutch just
after its ex-dividend drop, so it is never long RD over an RD ex-date in the
walk-forward (withholding has no effect there). The paper's 5x leverage is
outside the useful range of the metrics (equity near zero).

All numbered steps are done. Open items for any follow-up study (not started):
B6 sourced RD/Elsevier spreads 1996-98; impact sized on running equity (A7);
H2 calibration (needs the paper's 2002-07 sample); the 2000-02 OOS period is
spent for these strategies.

# Paper 2: de Jong, Rosenthal & van Dijk (2009), DLC arbitrage

Same data source (the authors built the Datastream DLC workbooks). The paper is
in-sample over 1980-2002 and specifies trading rules with per-twin results, so
a numerical replication is possible. Branch: work on `claude/sharp-bohr-snz350`
(restarted from main), merged by the user into `Dijk-paper`.

| Step | What | Commit |
|---|---|---|
| 13 | Paper extraction: `research/{extraction,equations,methodology,assumptions}/dejong_dlc.md`, evidence CSV (539 rows: Tables II-VI, sensitivity, unifications); ambiguities D1-D12; review | (this step) |

Planned, in order:

14. **Data for all 12 DLCs.** Ingest configs for the 8 new workbooks (sheets,
    units, theoretical ratio from the workbook), validation, per-twin sample
    windows of Table II (unified twins end 20 trading days before the
    announcement). Reproduce Table II from our panels. Sample-design decision
    recorded in `data_decisions.md`, including whether the replication may
    touch 2000-02 (`+unlock_oos`; the user's call).
15. **Comovement (Table III).** Regression E2 with Newey-West errors from the
    workbooks' `Regression data`; compare with the paper per twin.
16. **Paper-convention arbitrage engine (Tables IV-V).** Threshold strategy
    with Reg T margin account, maintenance calls, fixed interest, flat costs
    and the T-bill padding convention; resolve D1-D12 against the per-twin
    table values; all eight strategies.
17. **Abnormal returns (Table VI).** Fama-French factors and 3-month T-bill
    (public data, versioned with DVC); FF3 and IAPM alphas, risk statistics.
18. **Our standard.** The same rules through the lab's engine (liquidity
    costs, total-return P&L, no padding, open positions marked at the end),
    split by time-zone gap; the gap between conventions is a result.
19. **Report.**

