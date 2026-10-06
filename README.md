# quant-lab

Reproducible quantitative research lab: academic paper → research notes → strategy →
backtest → audit → robustness → out-of-sample. Current paper: Maymin,
*Self-Imposed Limits to Arbitrage* (dual-listed share pairs).

Stack: Python 3.12 · uv · DVC (data) · Hydra (config) · MLflow (experiments) ·
VectorBT (backtests) · statsmodels (econometrics) · pytest + ruff (verification).

## Setup (WSL2 Ubuntu)

Keep the repo on the Linux filesystem (`~/projects`), not under `/mnt/c`.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # once per machine
uv python install 3.12

git clone <repo-url> ~/projects/quant-research
cd ~/projects/quant-research
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
quant-research/
├── .claude/            agents, skills, settings.json, hooks/guard_bash.py
├── conf/               Hydra config groups: data, features, strategy, costs, split, backtest
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
