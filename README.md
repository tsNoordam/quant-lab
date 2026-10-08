# quant-lab

Reproducible quantitative research lab: academic paper → research notes → strategy →
backtest → audit → robustness → out-of-sample. Papers: Maymin, *Self-Imposed
Limits to Arbitrage* (steps 1-12, done); de Jong, Rosenthal & van Dijk (2009),
*The Risk and Return of Arbitrage in Dual-Listed Companies* (steps 13+).

Developer hand-over: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (architecture,
diagrams, entry points) and [docs/OPERATIONS.md](docs/OPERATIONS.md) (setup,
operations, SOPs, AI tooling).

Stack: Python 3.12 · uv · DVC (data) · Hydra (config) · MLflow (experiments) ·
VectorBT (backtests) · statsmodels (econometrics) · pytest + ruff (verification).

## Setup (WSL2 Ubuntu)

Keep the repo on the Linux filesystem (`~/projects`), not under `/mnt/c`.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # once per machine
uv python install 3.12

git clone https://github.com/tsNoordam/quant-lab.git ~/projects/quant-lab
cd ~/projects/quant-lab
uv sync                       # creates .venv from uv.lock (runtime + dev group)
uv run pytest                 # must pass
uv run ruff check . && uv run ruff format --check .
```

Moved or renamed the project folder? Recreate the environment with
`rm -rf .venv && uv sync`. Console scripts in `.venv/bin/` (dvc, pytest,
ruff, ...) hard-code the old interpreter path and otherwise fail with
"Failed to spawn: ... No such file or directory".

## Layout

```
quant-lab/
├── .claude/            agents, skills, settings.json, hooks/guard_bash.py
├── conf/               Hydra config groups (data, split, strategy, costs, backtest, walkforward,
│                       silta, robustness, oos) + dlc/ (paper-2 twins)
├── docs/               ARCHITECTURE.md, OPERATIONS.md (developer hand-over)
├── data/
│   ├── raw/            immutable vendor data            (DVC: dvc add)
│   ├── processed/      dvc.yaml stage outputs           (DVC: stage outs)
│   └── metadata/       provenance JSON per dataset      (Git)
├── papers/             raw/ PDFs (DVC), extracted/ text
├── research/           extraction, equations, methodology, assumptions, evidence,
│                       specs/{replication,baseline,extensions}, reports
├── notebooks/          exploration only
├── src/quant_lab/
│   ├── data/           loaders, validation, cleaning, synchronization, preprocess (DVC stages)
│   ├── features/       signals and rolling metrics
│   ├── models/         econometrics (statsmodels: OLS, HAC/Newey-West)
│   ├── strategies/     replication / baseline implementations
│   ├── backtest/       run (Hydra+MLflow entry), costs, splits, reference engine
│   └── tracking/       MLflow helpers (git commit, DVC hash, dirty-tree tags)
├── tests/
│   ├── unit/           costs, execution, entries/exits, sizing, tooling
│   ├── data/           deterministic data validation
│   ├── structural/     look-ahead / leakage perturbation tests
│   └── integration/    VectorBT vs reference engine reconciliation
├── CLAUDE.md           lab rules for Claude Code
├── dvc.yaml            pipeline DAG (Step 3)
└── pyproject.toml / uv.lock
```

MLflow (`mlflow.db`, `mlruns/`) and Hydra (`outputs/`, `multirun/`) write
local, git-ignored state.

## Data (DVC)

One-time per machine (the remote path is machine-local, kept in the
git-ignored `.dvc/config.local`):

```bash
mkdir -p ~/dvc-store
uv run dvc remote add --local -d localstore ~/dvc-store
uv run dvc pull                      # fetch the data this commit points to
```

Daily workflow:

```bash
# new raw dataset (immutable): write files + data/metadata/<name>.json, then
uv run dvc add data/raw/<name>
# rebuild whatever is out of date and inspect data-quality metrics
uv run dvc repro
uv run dvc metrics show              # or: dvc metrics diff main
uv run dvc push && git push          # data blobs to the store, pointers to GitHub
```

The synthetic twin pair (`conf/data/synthetic_twin.yaml`) is regenerable from
code: `uv run python -m quant_lab.data.synthetic --dataset synthetic_twin`.

### Datastream dual-listed pairs (licensed, DVC only)

The original archives live unmodified in `data/raw/datastream_dlc/`
(`RoyalDutchShell.zip`, `Unilever.zip`, `ReedElsevier.zip`, `RioTinto.zip`;
md5s in `data/metadata/datastream_dlc.json`). Adding them the first time:

```bash
mkdir -p data/raw/datastream_dlc
cp /mnt/c/Users/<you>/Downloads/RoyalDutchShell.zip data/raw/datastream_dlc/   # etc., exact names above
md5sum data/raw/datastream_dlc/*.zip     # compare with data/metadata/datastream_dlc.json
uv run dvc add data/raw/datastream_dlc   # writes data/raw/datastream_dlc.dvc (+ .gitignore entry)
uv run dvc repro                         # ingest -> data/interim/<pair>, preprocess -> data/processed/<pair>
uv run dvc push                          # blobs to ~/dvc-store
git add data/raw/datastream_dlc.dvc data/raw/.gitignore dvc.lock data/interim/*.ingest.json data/processed/*/validation.json
git commit -m "Add Datastream DLC archives via DVC" && git push
```

`ingest` converts each workbook (date repair, #N/A, holiday padding, units to
GBP, total-return adjusted close) into the per-leg CSV schema; `preprocess`
validates and aligns the pair. Pairs: `rd_shell`, `reed_elsevier`, `rio_tinto`
(Unilever is in the archive but excluded: see `research/reports/data_decisions.md`). They are close-only, so backtest them with
`backtest.execution=next_close`.

## Backtests (Hydra + VectorBT + MLflow)

```bash
uv run python -m quant_lab.backtest.run                              # train period
uv run python -m quant_lab.backtest.run backtest.period=validation
uv run python -m quant_lab.backtest.run -m strategy.window=40,60,80  # sweep (train only)
uv run python -m quant_lab.backtest.run costs=flat_bps costs.fee_bps=20   # labelled flat-fee sensitivity

uv run mlflow ui --backend-store-uri sqlite:///mlflow.db   # http://127.0.0.1:5000
```

Config lives in `conf/` (`config.yaml` + groups data, split, strategy, costs,
backtest). Each run logs params, metrics (Sharpe, drawdown, ...), provenance tags
(git commit, dirty tree, input md5 vs `dvc.lock`) and artifacts (equity curve,
resolved config, daily positions, orders).

Guards: split boundaries in `conf/split/` cannot be overridden from the CLI, and
`backtest.period=oos` refuses to run without `+unlock_oos=true`. Each dataset
uses its own split file (`data=rd_shell` selects `conf/split/rd_shell.yaml`);
the sample design is in `research/reports/data_decisions.md`.

Walk-forward evaluation (train + validation only; parameters chosen per fold on
the training window, traded unchanged on the next test window):

```bash
uv run python -m quant_lab.backtest.walkforward data=rd_shell
uv run python -m quant_lab.backtest.walkforward data=rd_shell walkforward.selection=best
```

Settings in `conf/walkforward/default.yaml` (fold lengths, embargo, selection
rule); the parameter grid is `strategy.grid` in `conf/strategy/<name>.yaml`.
MLflow artifacts: `folds.csv`, `grid_scores.csv`, equity plot.

Strategies (`strategy=<name>`; specs in `research/specs/`):

| Name | What | Spec |
|---|---|---|
| `parity_zscore` (default) | baseline: trailing z-score of the relative price | `baseline/parity_zscore.md` |
| `silta_parity` | the SILTA arbitrageur: deviation from parity, 180 bps entry, exit at parity | `extensions/silta_parity.md` |

```bash
uv run python -m quant_lab.backtest.run data=rd_shell strategy=silta_parity
uv run python -m quant_lab.backtest.walkforward data=rd_shell strategy=silta_parity
```

## Paper 2: de Jong, Rosenthal & van Dijk (2009)

Paper-convention panels for all 12 dual-listed companies (`conf/dlc/<twin>.yaml`,
DVC stage `dlc_ingest`), each checked row by row against the authors' own
deviation-from-parity column, plus each workbook's regression data; the Table II
(deviations) and Table III (comovement) replications:

```bash
uv run dvc repro dlc_ingest
uv run python -m quant_lab.models.dejong      # both tables; --table 2 or --table 3 for one
```

MLflow experiment `dejong.replication`, runs `table2` and `table3`. Results:
`research/reports/dejong_table2.md`, `research/reports/dejong_table3.md`.
Notes: `research/*/dejong_dlc.md`.

## Robustness (step 9)

Every case in `conf/robustness/default.yaml` (costs, dividends, capital and
leverage, selection rule, fold design, a wider grid) for both strategies:
walk-forward plus frozen-value train/validation runs on `rd_shell`, frozen
values only elsewhere. The summary run (experiment `<data>.robustness`) holds
sub-periods, volatility regimes, trade concentration, grid position and the
deflated Sharpe ratio with the number of trials counted from MLflow.

```bash
uv run python -m quant_lab.backtest.robustness data=rd_shell        # ~35 min
uv run python -m quant_lab.backtest.robustness data=reed_elsevier
```

Results: `research/reports/robustness_step9.md`.

## Reproduce

```bash
uv sync --locked
uv run dvc pull && uv run dvc repro      # licensed data (DVC remote access needed)
uv run pytest
uv run python -m quant_lab.reproduce     # 10 headline development numbers vs research/reports/headlines.yaml
```

CI (`.github/workflows/ci.yml`) runs ruff and pytest on synthetic data only.
Final report: `research/reports/final_report.md`.

## Freeze and one-shot out-of-sample evaluation (steps 10-11)

The strategies, costs, deflation inputs and decision rules for the OOS run are
frozen in `research/specs/freeze/preregistration.md` and `conf/oos/default.yaml`
(tags `freeze-parity_zscore`, `freeze-silta_parity`). The evaluation runs only
on a clean checkout of a `freeze-*` tag, and only with the explicit unlock:

```bash
git checkout freeze-silta_parity
uv run python -m quant_lab.backtest.oos +unlock_oos=true
```

## SILTA regressions (paper replication)

Maymin's relative-price on relative-volume regressions with Newey-West errors,
on the development range (train + validation) only:

```bash
uv run python -m quant_lab.models.silta data=rd_shell
uv run python -m quant_lab.models.silta data=reed_elsevier
```

Settings in `conf/silta/default.yaml`. MLflow experiment `<data>.silta`;
artifacts `regressions.csv`, `chi_condition.csv`, `lag_sensitivity.csv`.
Results and caveats: `research/reports/silta_replication.md`.

## Dependencies

| Group | Packages | Why |
|---|---|---|
| runtime | numpy, pandas, pyarrow, scipy, statsmodels, scikit-learn | data, econometrics (HAC/Newey-West), CV splitters |
| runtime | vectorbt | vectorized backtesting |
| runtime | hydra-core | hierarchical config, CLI overrides |
| runtime | mlflow | experiment tracking (params, metrics, artifacts) |
| runtime | matplotlib, plotly | research plots / MLflow artifacts |
| dev | dvc | data versioning + pipeline DAG (CLI, not imported by the library) |
| dev | pytest, ruff | tests, lint, format |
| dev | jupyterlab, ipykernel | exploratory notebooks only; final backtests live in `.py` |

Add a dependency with `uv add <pkg>` (or `uv add --dev <pkg>`); always commit
`pyproject.toml` and `uv.lock` together.
