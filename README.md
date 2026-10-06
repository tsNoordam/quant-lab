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
