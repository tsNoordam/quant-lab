---
name: run-backtest
description: Run a strategy backtest or walk-forward through Hydra on the train/validation split, log it to MLflow with full provenance, and report the result honestly, including when it is bad.
---

# Run backtest

Backtests run only through the Hydra entry points and are logged to MLflow.
No hand-made result folders, no parameters typed into Python.

1. **Check the tree.** Run `git status`. Results you will cite need a clean
   tree. Commit first, or pass `mlflow.require_clean_tree=true` so a dirty tree
   is refused. Note the commit hash.
2. **Check the data.** Run `uv run dvc status`. If a stage is stale, run
   `uv run dvc repro` first. The run tags record the panel md5 against
   `dvc.lock`.
3. **Pick the run.** Always from the project root:

   ```bash
   # single period (train is the default; validation compares frozen variants)
   uv run python -m quant_lab.backtest.run data=<pair> strategy=<name>
   uv run python -m quant_lab.backtest.run data=<pair> strategy=<name> backtest.period=validation
   # walk-forward over train + validation, grid = strategy.grid
   uv run python -m quant_lab.backtest.walkforward data=<pair> strategy=<name>
   ```

   Real pairs are close-only: their dataset config already selects
   `next_close`. Develop on `rd_shell` only. `reed_elsevier` validation is for
   variants frozen on `rd_shell`. `rio_tinto` is OOS-only.
4. **Never** pass `+unlock_oos=true`, `split.*` overrides or
   `backtest.period=oos` unless the user explicitly asks for the one-shot OOS
   evaluation of a frozen strategy (ROADMAP step 11).
5. **Costs.** The default is `costs=liquidity`. `costs=flat_bps` is a labelled
   sensitivity case only: give it a `run_label=<name>`.
6. **Report** from MLflow, not from memory:
   - run id and commit;
   - dataset, period, strategy, parameters, cost model, execution;
   - Sharpe, total return, max drawdown, number of entries, exposure;
   - cost breakdown;
   - for a walk-forward: the chosen parameters per fold and `wf_n_trials`.

   Compare with the baseline on the same period and costs. A bad result is
   reported as it is, and is not a reason to change the strategy (CLAUDE.md
   golden rules).
7. **Write it down.** Results that matter for a decision go in
   `research/reports/` with run ids. Licensed data stays out (aggregates only).
