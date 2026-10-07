---
name: audit-backtest
description: Audit a backtest (a run, a strategy, or the current diff) for look-ahead bias, data leakage, unrealistic execution and costs, and statistical problems, using the read-only backtest-auditor agent plus deterministic tests.
---

# Backtest audit

The audit has a deterministic half (tests) and an adversarial half (the
`backtest-auditor` agent). The agent's findings are hypotheses until a test
reproduces them (CLAUDE.md). Never modify strategy rules during an audit.

1. **Scope.** State what is audited: an MLflow run id, a strategy + dataset +
   period, or the current branch diff (`git diff main...HEAD`). Note the commit.
2. **Gate.** Run `uv run pytest -q` and `uv run ruff check .`. If anything fails,
   stop: the audit verdict is FAIL until the gate is green.
3. **Adversarial review.** Invoke the `backtest-auditor` agent with the scope,
   the configs involved, and the MLflow run ids/metrics if any. It is read-only.
4. **Settle every HYPOTHESIS.** For each finding marked HYPOTHESIS, add its
   falsification test under `tests/structural/` (look-ahead) or
   `tests/integration/` (costs, execution) and run it:
   - test fails -> the finding is CONFIRMED: keep the failing test, fix the
     code in a separate commit, and re-run the gate;
   - test passes -> the finding is REJECTED: keep the test as a regression guard.
   Never weaken or delete a test to make it pass.
5. **Record.** Write the report to
   `research/reports/audits/<YYYY-MM-DD>-<scope>.md`: the agent's report, plus a
   "Resolution" table (finding, CONFIRMED/REJECTED, test name, fix commit).
6. **Verdict.** PASS only when the gate is green and no finding remains FAIL or
   unresolved. A WARNING may stand if it is documented in the report.
