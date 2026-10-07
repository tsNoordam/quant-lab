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
| 6 | Paper extraction: `research/{extraction,equations,methodology,assumptions,evidence}/maymin_silta.*`; parity checked against the equalization agreements | (this step) |

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

7. **SILTA econometric replication.** `quant_lab.models`: the paper's
   relative-price-on-relative-volume regressions with Newey-West errors for
   `rd_shell` and `reed_elsevier`, compared with the paper's numbers; full-
   sample standardization labelled as explanatory only, plus a causal (rolling)
   version. Logged to MLflow, tested.
8. **SILTA-informed strategy.** `/build-strategy`: a strategy spec that uses the
   replicated relation, every rule tagged; implemented in
   `quant_lab.strategies`; walk-forward on `rd_shell` train+validation only.
   Adds the `run-backtest` skill.
9. **Robustness and multiple testing.** `/robustness`: parameter neighbourhoods,
   cost and capital sensitivity (stamp duty, impact k, init_cash), sub-periods,
   the `reed_elsevier` validation pair, number of trials from MLflow and a
   deflated Sharpe ratio.
10. **Freeze.** `/audit-backtest` and red-team on the final candidate; a
    pre-registration note (what OOS result would count as success or failure,
    how Rio Tinto's non-synchronous closes are handled); git tag
    `freeze-<strategy>`.
11. **One-shot out-of-sample evaluation.** 2000-2002 for `rd_shell` and
    `reed_elsevier`, all of `rio_tinto`, with `+unlock_oos=true`, run once on the
    frozen tag and reported whatever the outcome.
12. **Final report and reproducibility.** `research-report` skill and report;
    clean-clone reproduction (dvc pull, uv sync, dvc repro, pytest, headline
    runs match MLflow); CI on GitHub Actions running pytest + ruff on synthetic
    data only (licensed data never leaves DVC).
