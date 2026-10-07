# Quant Research Lab

## Mission

This repository converts academic quantitative finance research papers into
reproducible, testable trading strategies. Current paper: Maymin,
*Self-Imposed Limits to Arbitrage* (dual-listed share pairs).

The goal is NOT to maximize historical returns.

Priority:

1. Research fidelity
2. Reproducibility
3. No look-ahead bias
4. Realistic execution
5. Statistical validity
6. Robustness
7. Performance

The golden rules:

- A failed backtest is a research result. Do not modify the strategy merely
  because the result is bad.
- Never use the out-of-sample period to decide what to change.

## Division of labour

Claude extracts, drafts and reviews. Python computes. pytest verifies.
Git + DVC + MLflow record what happened.

- AI agents never validate data (timestamps, missing values, alignment,
  corporate actions). That is done by deterministic code in
  `src/quant_lab/data/validation.py` and asserted in `tests/data/`.
- An agent's audit finding is a hypothesis until a test reproduces it.
  Look-ahead claims are settled by the structural tests in `tests/structural/`,
  not by argument.

## Repository map

| Path | Contents | Versioned by |
|---|---|---|
| `papers/raw/` | Source PDFs (immutable) | DVC |
| `research/` | Extraction notes, equations, methodology, assumptions, evidence, strategy specs (`specs/`), written reports (`reports/`) | Git |
| `data/raw/` | Immutable vendor data (`datastream_dlc/` original zips, `synthetic_twin/`) | DVC (`dvc add`) |
| `data/interim/` | Vendor formats converted to the per-leg raw CSV schema (`ingest` stage) | DVC (stage outs) |
| `data/processed/` | Validated, aligned pair panels (`preprocess` stage), never edited by hand | DVC (stage outs) |
| `data/metadata/` | Source/provenance JSON per dataset | Git |
| `conf/` | Hydra config groups: data, features, strategy, costs, split, backtest | Git |
| `src/quant_lab/` | `data`, `features`, `models` (statsmodels), `strategies`, `backtest`, `tracking` | Git |
| `tests/` | `unit`, `data`, `structural` (look-ahead/leakage), `integration` (engine reconciliation) | Git |
| `notebooks/` | Exploration only. Final backtests live in `.py` files | Git |
| `mlflow.db`, `mlruns/` | Experiment tracking (local, not committed) | MLflow |

## Research rules

Every strategy rule must be classified as:

[PAPER-DERIVED]
[MATHEMATICALLY-DERIVED]
[IMPLEMENTATION-ASSUMPTION]
[EXTERNAL-RESEARCH]
[PROPOSED-EXTENSION]

Never silently introduce a trading rule.

Never convert an empirical observation into a trading rule
without explicitly identifying that transformation.

Never optimize solely for historical performance.

Never use future information.

Never use the out-of-sample period for strategy development.

## Data

- `data/raw/` is immutable. Fix data problems in a processing stage, never in
  the raw file.
- Every dataset in `data/raw/` has a metadata JSON in `data/metadata/`.
- `data/interim/` and `data/processed/` are produced only by `uv run dvc repro`.
- Datastream data is licensed: it stays in DVC and is never committed to Git
  or pasted into notes, issues or chat.
- Real pairs are close-only (no open/high/low): backtest them with
  `backtest.execution=next_close`.
- `volume_reliable: false` in a dataset config means its volume must not be
  used: no ADV-based costs, no relative-volume analysis.
- Sample design (pair roles, splits, what is locked) is fixed in
  `research/reports/data_decisions.md`. Develop on `rd_shell` train+validation
  only; `rio_tinto` and everything from 2000 on are out-of-sample.
- Any rolling statistic used by a cost or signal model (volatility, ADV,
  spread) must be lagged so that it only uses information available before
  the decision time.

## Backtesting

- Backtests run through Hydra (`conf/`) and log to MLflow. No parameters
  hardcoded in Python, no hand-made result folders.
- Every MLflow run must record: dataset + DVC hash, date range, timeframe,
  parameters, cost and slippage model, execution model, position sizing,
  leverage, number of trades, git commit, and whether the tree was dirty.
- Train/validation/OOS boundaries live in `conf/split/` and are not
  overridden from the command line. Touching the OOS window requires
  `+unlock_oos=true`, which is logged as an MLflow tag. Do not set it unless
  the user explicitly asks.
- Hydra multirun sweeps run on train/validation only. Report parameter
  neighbourhoods, not the single best point.
- Costs scale with trade size and liquidity (square-root impact over lagged
  ADV and volatility), plus borrow cost on the short leg. A flat bps fee is
  only acceptable as a labelled sensitivity case.
- VectorBT results must reconcile with the reference implementation in
  `src/quant_lab/backtest/reference.py` (`tests/integration/`).

## Statistical standards

Investigate:

- look-ahead bias
- survivorship bias
- data snooping
- multiple testing
- overfitting
- parameter sensitivity
- walk-forward stability (purged, embargoed)
- out-of-sample performance
- transaction costs
- liquidity
- regime dependence

## Coding standards

Use:

- Python 3.12 via uv (`uv add`, `uv run`; never bare `pip`)
- pytest, ruff
- pandas, numpy, scipy, statsmodels
- VectorBT, Hydra, MLflow, DVC

Change files with the Edit/Write tools, not with shell commands such as
`sed -i` or `>` redirects. A PreToolUse hook (`.claude/hooks/guard_bash.py`)
blocks in-place shell edits to `src/`, `tests/`, `conf/`, raw data and
project config. This is what keeps the read-only agents read-only.

Before declaring a task complete:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Git

Never delete or rewrite research history without explicit permission.

Use descriptive commits. One experiment = one commit, so an MLflow run's
git commit tag identifies exactly the code that produced it.

Commit `pyproject.toml` and `uv.lock` together, and `*.dvc` / `dvc.lock`
with the code that produced them.

Never commit:

- API keys
- credentials
- .env files
- private tokens
- raw or processed data (DVC handles it)
