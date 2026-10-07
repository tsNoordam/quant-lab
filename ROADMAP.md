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
| 9 | Robustness runner (`quant_lab.backtest.robustness`), deflated Sharpe and MLflow trial count. 19 cases x 2 strategies: no positive net Sharpe in any realistic cost/capital/leverage/selection case; baseline gross WF Sharpe +0.75 consumed by costs; DSR 0.001 / 0.027 at 502 trials; Reed Elsevier at frozen values agrees. `research/reports/robustness_step9.md` | 895df80 + (this step) |

## Remaining, in order

Open from the audits (decisions, not fixes): B6 treatment of RD/Elsevier
1996-98 wide quotes (needs a source); A3 corner-biased selection; Rio Tinto
Ltd withholding (before step 10).

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
differenced specification of the step 7 regression are left for step 9.

Decided in step 8: the paper has no trading rule, so there is no replication
strategy (`research/specs/replication/maymin_silta.md`); relative volume (H1)
is not used as a signal (contemporaneous, and absent in our data); the
walk-forward grid now lives in each strategy's config (`strategy.grid`).

Found in step 9: with the raw-close signal, the baseline buys Royal Dutch just
after its ex-dividend drop, so it is never long RD over an RD ex-date in the
walk-forward (withholding has no effect there). The paper's 5x leverage is
outside the useful range of the metrics (equity near zero).

10. **Freeze.** `/audit-backtest` and red-team on both strategies at their
    current values (no tuning after step 9); a pre-registration note (expected
    outcome: no positive net Sharpe; what OOS result would count as evidence,
    e.g. DSR > 0.95 at the frozen trial count; how Rio Tinto's non-synchronous
    closes are handled); git tag `freeze-<strategy>`. Whether to run step 11
    at all is the user's decision.
11. **One-shot out-of-sample evaluation.** 2000-2002 for `rd_shell` and
    `reed_elsevier`, all of `rio_tinto`, with `+unlock_oos=true`, run once on the
    frozen tag and reported whatever the outcome.
12. **Final report and reproducibility.** `research-report` skill and report;
    clean-clone reproduction (dvc pull, uv sync, dvc repro, pytest, headline
    runs match MLflow); CI on GitHub Actions running pytest + ruff on synthetic
    data only (licensed data never leaves DVC).
