# quant-lab: Knowledge Transfer & Operations Guide

Deliverable 2 of the developer hand-over: how to set up, run, test, maintain,
change and extend the lab, and how to set up the AI tooling around it. The
architecture behind these procedures is in [ARCHITECTURE.md](ARCHITECTURE.md);
the lab rules are in [CLAUDE.md](../CLAUDE.md).

Written 2026-10-07 against commit `a847032`.

## Contents

1. [Full operation](#1-full-operation)
   1. [Environment setup](#11-environment-setup)
   2. [Getting the data](#12-getting-the-data)
   3. [Run the project end to end](#13-run-the-project-end-to-end)
   4. [Tests, linters and CI](#14-tests-linters-and-ci)
   5. [Routine maintenance](#15-routine-maintenance)
   6. [Troubleshooting](#16-troubleshooting)
2. [Editing & scaling (SOPs)](#2-editing--scaling-sops)
   1. [SOP-1: Safely edit existing logic](#21-sop-1-safely-edit-existing-logic)
   2. [SOP-2: Add a new paper and strategy (worked example)](#22-sop-2-add-a-new-paper-and-strategy-worked-example)
   3. [SOP-3: Add new components without breaking flows](#23-sop-3-add-new-components-without-breaking-flows)
3. [AI tooling & setup](#3-ai-tooling--setup)
   1. [What is already configured](#31-what-is-already-configured)
   2. [Recommended MCP servers](#32-recommended-mcp-servers)
   3. [Recommended skills](#33-recommended-skills)
   4. [Filesystem and other integrations](#34-filesystem-and-other-integrations)
   5. [Copy-paste prompts](#35-copy-paste-prompts)
4. [Assumptions](#4-assumptions)

---

## 1. Full operation

### 1.1 Environment setup

**Requirements:**

- Linux, macOS or WSL2 Ubuntu. On WSL, keep the repository on the Linux
  filesystem (`~/projects`), never under `/mnt/c`.
- git, plus about 2 GB of disk for `.venv` and the data.
- No secrets, API keys or `.env` file are needed to run the lab. `.env*` is
  git-ignored and Claude Code is denied read access to it, in case you add one.

```bash
# 1. uv and Python 3.12 (once per machine)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

# 2. Clone and install (runtime + dev dependency group, exactly as locked)
git clone https://github.com/tsNoordam/quant-lab.git ~/projects/quant-lab
cd ~/projects/quant-lab
uv sync --locked

# 3. Sanity check: synthetic-data tests pass without any licensed data
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

**Configuration files** (all committed; nothing to create by hand except the
DVC remote):

| File | Purpose | Edit when |
|---|---|---|
| `pyproject.toml` + `uv.lock` | dependencies (Python pinned to 3.12.*), pytest and ruff settings | adding a dependency (`uv add`) |
| `conf/config.yaml` | Hydra root: default groups, `run_label`, MLflow URI (`sqlite:///mlflow.db`) and artifact root | rarely |
| `conf/<group>/*.yaml` | data, split (locked), strategy, costs, backtest, walkforward, silta, robustness, oos (frozen) | per experiment, via a commit |
| `conf/dlc/<twin>.yaml` | paper-2 twin definitions | adding a twin |
| `dvc.yaml` / `dvc.lock` | pipeline DAG / exact data state | `dvc.lock` only through `dvc repro` |
| `.dvc/config.local` | your machine's DVC remote path (git-ignored) | once |
| `.claude/settings.json` | Claude Code permissions and the guard hook | rarely; Claude must ask first |

**Environment variables:**

| Variable | Default | Effect |
|---|---|---|
| `MLFLOW_DISABLE_AGENT_HINT` | set to `1` by `mlflow_utils` and `.claude/settings.json` | silences an MLflow banner |
| `HYDRA_FULL_ERROR=1` | unset | full stack traces from Hydra entry points |
| `MLFLOW_TRACKING_URI` | unused (the URI comes from `conf/config.yaml`) | none |

### 1.2 Getting the data

The Datastream data is licensed. It lives only in DVC, never in git, chat or
notes. The remote is a folder on the data owner's machine.

```bash
# once per machine: point DVC at the store (machine-local, git-ignored)
mkdir -p ~/dvc-store
uv run dvc remote add --local -d localstore ~/dvc-store

# fetch the exact data this commit points to
uv run dvc pull
md5sum data/raw/datastream_dlc/*.zip   # compare with data/metadata/datastream_dlc.json
```

Without access to that store you can still develop. All CI and unit tests run
on the synthetic pair, and every real-data test skips itself with
`... not present (dvc pull)`.

### 1.3 Run the project end to end

Run everything from the repository root (`cd ~/projects/quant-lab`). Running
from a subfolder makes pytest collect 0 tests and Hydra look for
`./data/...`.

```bash
# A. Rebuild derived data (only stages whose inputs changed)
uv run dvc repro                     # all stages
uv run dvc repro dlc_ingest          # just the 12 paper-2 twin panels
uv run dvc metrics show              # ingest/validation reports
git add dvc.lock data/interim data/processed && git commit -m "dvc repro"   # pointers + metrics only

# B. Paper 1 (Maymin): econometrics, backtests, walk-forward
uv run python -m quant_lab.models.silta data=rd_shell
uv run python -m quant_lab.backtest.run data=rd_shell strategy=silta_parity                       # train
uv run python -m quant_lab.backtest.run data=rd_shell strategy=silta_parity backtest.period=validation
uv run python -m quant_lab.backtest.walkforward data=rd_shell strategy=parity_zscore
uv run python -m quant_lab.backtest.robustness data=rd_shell          # ~35 min, 19 cases x 2 strategies

# C. Paper 2 (de Jong et al.): Table II and III replications, then Tables IV-V
uv run python -m quant_lab.models.dejong      # expect "58/72" (Table II), then "77/84" and "48/48" (Table III, identified)
uv run python -m quant_lab.backtest.dejong    # needs data/raw/fred_tbill (README); research/reports/dejong_tables45.md
uv run python -m quant_lab.models.dejong_risk # needs data/raw/french_ff too; research/reports/dejong_table6.md

# D. Check that the recorded headline numbers still reproduce
uv run python -m quant_lab.reproduce          # expect "10/10 headline numbers reproduced"

# E. Inspect results
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db    # http://127.0.0.1:5000
```

**Do not run** `uv run python -m quant_lab.backtest.oos +unlock_oos=true`.
The paper-1 OOS evaluation was a one-shot, pre-registered run (MLflow
`c5a6c503`, tags `freeze-*`), and it refuses to run anywhere but a clean
checkout of a freeze tag. Never pass `+unlock_oos=true`, `split.*` overrides or
`backtest.period=oos` unless the research lead explicitly asks.

**Citable runs.** For a result you will quote, require a clean tree, so the
MLflow tags pin the exact code:

```bash
git status                                    # must be clean
uv run python -m quant_lab.backtest.run data=rd_shell mlflow.require_clean_tree=true
```

### 1.4 Tests, linters and CI

| Tier | Folder | What it proves | Needs licensed data |
|---|---|---|---|
| unit | `tests/unit/` | functions, configs, Claude tooling (guard hook, agent/skill frontmatter) | no |
| data | `tests/data/` | deterministic data validation | some (skip) |
| structural | `tests/structural/` | no look-ahead: perturb the future, past outputs must not move (each with a mutation check) | no |
| integration | `tests/integration/` | end-to-end runs, VectorBT vs reference ledger, real-data pins (Table II, headlines, parity) | some (skip) |

```bash
uv run pytest -q                              # everything (~2 min)
uv run pytest -q tests/unit                   # fast loop (~40 s)
uv run pytest -q tests/structural             # look-ahead suite
uv run pytest -q -rs                          # show why tests were skipped
uv run pytest -q -k dejong                    # by keyword
uv run ruff check . && uv run ruff format --check .
uv run ruff check --fix . && uv run ruff format .     # auto-fix
```

**CI** (`.github/workflows/ci.yml`) runs on every push and pull request:

1. `uv sync --locked`;
2. ruff;
3. pytest (real-data tests skip);
4. a check that fails if any `data/(raw|interim|processed)/*.(parquet|csv|xls|xlsx|zip)`
   file is tracked by git.

To reproduce CI locally on a clean clone with no data:

```bash
git clone https://github.com/tsNoordam/quant-lab.git /tmp/ci-check && cd /tmp/ci-check
uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q -rs
```

**Definition of done for any change** (`CLAUDE.md`):

- pytest and ruff are green;
- the change is committed and pushed;
- `ROADMAP.md` is updated if it is a roadmap step.

### 1.5 Routine maintenance

| Task | How often | Commands / notes |
|---|---|---|
| Back up MLflow (runs are not in git) | weekly and before big runs | `mkdir -p ~/lab-backups && cp mlflow.db ~/lab-backups/mlflow-$(date +%F).db && tar czf ~/lab-backups/mlartifacts-$(date +%F).tgz mlartifacts/` (outside the repo, so the tree stays clean) |
| Back up the DVC store (the only copy of the licensed data) | after `dvc add` / `dvc push` | copy `~/dvc-store` to an encrypted external disk, or add a second remote (see the open questions) |
| Clean Hydra run folders | monthly | `rm -rf outputs/ multirun/` (git-ignored, safe) |
| Clean caches | as needed | `rm -rf .pytest_cache .ruff_cache`; `uv cache prune` |
| DVC cache housekeeping | rarely | `uv run dvc gc` is **denied** for Claude and dangerous: it deletes data not referenced by the current workspace. Run it only by hand, with `--all-commits`, after a backup |
| Upgrade dependencies | monthly, on a branch | `uv lock --upgrade` (or `uv add 'pkg>=x'`), then `uv sync`, the full pytest, `uv run python -m quant_lab.reproduce`; commit `pyproject.toml` and `uv.lock` together. A changed headline number means behaviour changed: investigate before merging |
| Python upgrade | rarely | the pin `==3.12.*` is deliberate (numba/vectorbt wheels). Change it only with a full rerun of `reproduce` |
| Moved or renamed the project folder | as needed | `rm -rf .venv && uv sync` (console scripts hard-code the old path) |
| New raw data | as needed | see SOP-3 "new data source" |
| Logs | none persistent | stdout only; run records live in MLflow; DVC stage reports are `*.ingest.json` and `validation.json` (`dvc metrics show`) |

### 1.6 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `collected 0 items`, or `FileNotFoundError: .../.claude/data/...` | command run from a subfolder | `cd` to the repo root |
| `Could not override 'costs.fee_bps'` | `fee_bps` exists only in `costs=flat_bps` | add `costs=flat_bps` first |
| `BacktestGuardError: refusing override 'split...'` | split boundaries are locked | edit `conf/split/<pair>.yaml` in a reviewed commit, and only before any result depends on it |
| `the out-of-sample period is locked` | `backtest.period=oos` without unlock | intended; see 1.3 |
| `DatastreamFormatError: deviation does not reproduce the workbook` | wrong `price_scale`, FX label or sheet in `conf/dlc/<twin>.yaml` | compare with the workbook (SOP-3 "new data source") |
| `Failed to spawn: ... No such file or directory` | `.venv` from an old path | `rm -rf .venv && uv sync` |
| `git push` gets `Internal Server Error` | GitHub-side, intermittent since the repo rename | retry; check the remote URL is `quant-lab` |
| MLflow tags `git_dirty=true` | untracked or modified files | commit or stash; Hydra `outputs/` and `mlflow.db` are already ignored |

---

## 2. Editing & scaling (SOPs)

### 2.1 SOP-1: Safely edit existing logic

1. **Branch.** Use `git switch -c fix/<topic>`. Never commit to `main`
   directly; never force-push. Force-push is denied for Claude; avoid it
   yourself too.
2. **Impact analysis.** Find every caller before changing a function.
   ```bash
   grep -rn "execution_targets\|backtest_pair" src tests      # callers and pins
   grep -rn "^from quant_lab" src | grep "backtest.run"       # who imports the module
   ```
   Then check the dependency diagram in
   [ARCHITECTURE.md §3.2](ARCHITECTURE.md#32-code-modules-and-their-dependencies).
   Any change to `backtest.run`, `costs`, `dividends` or `strategies.*` reaches
   every engine, robustness, OOS and reproduce.
3. **Classify the change:**
   - **Bug fix.** Write the failing test first, commit it, then fix in a
     separate commit (the audit convention; see
     `research/reports/audits/2026-10-07-freeze.md`).
   - **Behaviour change** to a rule, cost or execution. It needs a spec update
     in `research/specs/...` with a tag ([PAPER-DERIVED],
     [IMPLEMENTATION-ASSUMPTION] and so on). It must not be motivated by a bad
     result (golden rule).
   - **Refactor.** No numbers may move.
     `uv run python -m quant_lab.reproduce` must stay at 10/10.
4. **Test locally:**
   - `uv run pytest -q tests/unit tests/structural` while iterating;
   - then the full `uv run pytest -q`;
   - with data present, `uv run python -m quant_lab.reproduce`.
5. **Look-ahead-sensitive changes** (signals, timing, costs, splits) also
   need:
   - a structural test that shocks the future and asserts the past is
     unchanged;
   - a mutation check showing the test fails when the bug is reintroduced;
   - `/audit-backtest` before the change is relied on.
6. **Record it:**
   - one experiment equals one commit, so the MLflow `git_commit` tag
     identifies the code;
   - quote numbers only from clean-tree runs;
   - put changed results in `research/reports/` as a dated erratum. Never
     rewrite old numbers.
7. **Roll back:**
   ```bash
   git revert <commit>                 # code (keeps history)
   git checkout <commit> -- dvc.lock && uv run dvc checkout   # data state of that commit
   uv run dvc repro                    # rebuild derived data if needed
   ```
   MLflow runs are never deleted: filter by `tags.git_commit` instead.

### 2.2 SOP-2: Add a new paper and strategy (worked example)

**Example:** a hypothetical paper "Smith (2010), *Share-class arbitrage*" with
a strategy `band_reversion` on an existing pair. File names are the
convention; replace `smith_2010` and `band_reversion` with your own.

**Step 1: place and version the paper**

```bash
cp ~/Downloads/smith2010.pdf papers/raw/smith_2010.pdf
uv run dvc add papers/raw/smith_2010.pdf            # creates papers/raw/smith_2010.pdf.dvc
git add papers/raw/smith_2010.pdf.dvc papers/raw/.gitignore
git commit -m "Add Smith (2010) to DVC" && uv run dvc push
```

**Step 2: extract it (no strategy design yet)**

In Claude Code: `/extract-paper Smith (2010), papers/raw/smith_2010.pdf`.
This produces:

- `research/extraction/smith_2010.md`;
- `research/equations/smith_2010.md`;
- `research/methodology/smith_2010.md` (including a review);
- `research/assumptions/smith_2010.md` (ambiguities D1..Dn);
- `research/evidence/smith_2010_evidence.csv`, with the paper's numbers for
  later comparison.

Add the paper to the `Mission` line in `CLAUDE.md`, and add a numbered section
for it to `ROADMAP.md`.

**Step 3: data**

If the paper needs new data, follow SOP-3 "new data source". Then decide the
sample design: append a dated entry to `research/reports/data_decisions.md`
covering the train, validation and locked-OOS periods. Do this before running
anything, and add `conf/split/<dataset>.yaml`.

**Step 4: spec**

`/build-strategy` writes `research/specs/{replication,baseline,extensions}/band_reversion.md`.
Every rule gets a tag. A rule the paper does not state is
[IMPLEMENTATION-ASSUMPTION] or [PROPOSED-EXTENSION], never silent.

**Step 5: implement the decision function**

The strategy only decides positions at each close, from data up to that
close. `src/quant_lab/strategies/band_reversion.py`:

```python
"""Band reversion (Smith 2010). Spec: research/specs/replication/band_reversion.md."""

import numpy as np
import pandas as pd
from omegaconf import DictConfig

from quant_lab.strategies.parity_zscore import relative_price, spread_positions


def target_positions(panel: pd.DataFrame, *, parity_ratio: float, band: float, exit: float):
    d = (relative_price(panel) - np.log(parity_ratio)).rename("deviation")
    return spread_positions(d, entry_z=band, exit_z=exit), d


def decide(panel: pd.DataFrame, s: DictConfig, data: DictConfig):
    return target_positions(panel, parity_ratio=float(data.parity_ratio), band=s.band, exit=s.exit)
```

**Step 6: register it.** In `src/quant_lab/strategies/__init__.py`:

```python
from quant_lab.strategies import band_reversion, parity_zscore, silta_parity

STRATEGIES: dict[str, Decide] = {
    "parity_zscore": parity_zscore.decide,
    "silta_parity": silta_parity.decide,
    "band_reversion": band_reversion.decide,
}
```

**Step 7: configure it.** `conf/strategy/band_reversion.yaml`. No parameters
are hard-coded in Python; the grid lives with the strategy.

```yaml
# Spec: research/specs/replication/band_reversion.md
name: band_reversion
band: 0.05        # [PAPER-DERIVED] p. 12
exit: 0.01        # [PAPER-DERIVED] p. 12
leg_weight: 0.5   # [IMPLEMENTATION-ASSUMPTION]
grid:             # walk-forward neighbourhood, increasing order
  band: [0.03, 0.05, 0.07]
  exit: [0.0, 0.01]
```

**Step 8: test it.** The suite forces this.

`tests/structural/test_strategy_causality.py` fails until the new strategy has
a causality case. Add it to `STRATEGY_CONFIGS` there:

```python
"band_reversion": {"band": 0.01, "exit": 0.0},
```

Also add:

- `tests/unit/test_band_reversion.py` for the rule semantics (entry, exit,
  direction);
- a synthetic positive control in `tests/integration/`. Trading a known
  mispricing at zero cost must make money, and the test must fail when you
  flip the sign (see `test_silta_parity_run.py`).

```bash
uv run pytest -q tests/unit/test_band_reversion.py tests/structural tests/integration/test_band_reversion_run.py
```

**Step 9: run it.** Train and validation only.

```bash
uv run python -m quant_lab.backtest.run data=rd_shell strategy=band_reversion
uv run python -m quant_lab.backtest.run data=rd_shell strategy=band_reversion backtest.period=validation
uv run python -m quant_lab.backtest.walkforward data=rd_shell strategy=band_reversion
```

To include it in robustness, add it to `strategies:` in
`conf/robustness/default.yaml`, plus any strategy-specific `grid_wide` case.

**Step 10: audit, robustness, freeze, OOS, report**

1. `/audit-backtest`: settle every HYPOTHESIS with a test.
2. `/robustness`.
3. Freeze: pre-registration plus `conf/oos/`, then `git tag freeze-band_reversion`.
4. The one-shot OOS, only if an unused OOS period exists for this paper.
5. `/research-report`.

### 2.3 SOP-3: Add new components without breaking flows

**New data source (a vendor file):**

1. Put the immutable file under `data/raw/<source>/`, and write
   `data/metadata/<source>.json` (source, licence, md5 per file, known issues).
2. Version it: `uv run dvc add data/raw/<source>`, then commit the `.dvc` file
   and `.gitignore`, then `uv run dvc push`.
3. Write a converter stage in `src/quant_lab/data/`:
   - deterministic;
   - asserts its own invariants and raises on violation;
   - reuse `datastream.read_sheet` for these workbooks. Example of a
     self-check: `dlc.assemble` refuses any panel that does not reproduce the
     authors' column.
4. Add a config, either `conf/data/<dataset>.yaml` (lab schema → `preprocess`)
   or `conf/dlc/<twin>.yaml` (paper-2 schema).
5. Add a `foreach` entry to the right stage in `dvc.yaml`, with `deps`
   (raw folder, code), `params` (config keys) and `outs`.
6. Run `uv run dvc repro <stage>`, then commit `dvc.lock` and the
   `*.ingest.json` / `validation.json` metrics.
7. Write tests:
   - unit tests on synthetic inputs;
   - a real-data test that skips when the archive is absent (pattern:
     `tests/integration/test_dejong_real.py`).

**New Hydra config group** (e.g. `conf/<group>/default.yaml`):

- Add it to `defaults:` in `conf/config.yaml`.
- If it describes a list of runs rather than one run's settings (like
  `robustness` and `oos`), add its name to the `skip` set in
  `backtest.run.run_params`, so it is not logged as parameters of every run.
- `tests/unit/test_config_consistency.py` covers dataset/split pairing. Extend
  it if the group has invariants.

**New cost model:**

- Add `conf/costs/<model>.yaml` with `model: <model>`.
- Handle it in `backtest.run.simulate` and `backtest_pair`. Unknown models
  already raise `BacktestGuardError`.
- Every statistic must be lagged to the decision close: copy the pattern in
  `costs.market_stats`.
- Extend `tests/structural/test_cost_causality.py` and the reconciliation
  test.
- Per `CLAUDE.md`, a flat fee is only a labelled sensitivity case.

**New analysis module** (e.g. `models/<paper>.py`):

- Read panels; never write to `data/`.
- Log to MLflow through `tracking.mlflow_utils`, with git and data-provenance
  tags.
- Never read the OOS period unless the user approved it. If so, record it in
  `data_decisions.md` and tag `unlock_oos=true`.
- Add a CLI (`python -m quant_lab.models.<paper>`) and list it in
  [ARCHITECTURE.md §5](ARCHITECTURE.md#5-entry-points) and the README.

**Before merging any of these:**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
uv run python -m quant_lab.reproduce        # nothing old moved
uv run dvc status                           # pipeline consistent with dvc.lock
```

---

## 3. AI tooling & setup

### 3.1 What is already configured

| Item | Where | Notes |
|---|---|---|
| Lab rules | `CLAUDE.md` | read automatically by Claude Code at session start |
| Permissions | `.claude/settings.json` | denies writes to raw data and lockfiles, force-push, `dvc gc`, reading `.env`; asks before editing hooks and settings |
| Guard hook | `.claude/hooks/guard_bash.py` (PreToolUse, Bash) | blocks shell edits of protected paths; tested |
| Skills | `.claude/skills/{extract-paper, build-strategy, run-backtest, audit-backtest, robustness, research-report}` | invoke as `/name` |
| Agents | `.claude/agents/` | `backtest-auditor`, `red-team`, `paper-reader`, `quant-researcher`, `robustness-researcher` (read-only); `strategy-engineer` (can edit) |

### 3.2 Recommended MCP servers

Add them per project with `claude mcp add`, or share them through a committed
`.mcp.json` that holds no secrets (tokens come from your shell environment).
After adding, check with `claude mcp list` and `/mcp` inside a session.

**1. GitHub (official). Why:**

- PRs, reviews, CI status and issues without leaving the session;
- this repo's CI and PR loop depend on it.

```bash
export GITHUB_PAT=ghp_...        # fine-grained token, repo-scoped: contents read, pull requests rw, actions read
claude mcp add --transport http github https://api.githubcopilot.com/mcp/ \
  --header "Authorization: Bearer $GITHUB_PAT"
```

**2. Fetch (reference server). Why:** steps 17+ need public data, such as
Fama-French factors from Ken French's site and the 3-month T-bill from FRED,
plus paper landing pages.

```bash
claude mcp add fetch -- uvx mcp-server-fetch
```

**3. SQLite, on a snapshot of the MLflow store. Why:**

- it lets the agent answer questions like "which runs used commit X" or
  "list all walk-forward Sharpe values" by SQL;
- it never touches the live `mlflow.db`, because the server can also write.

```bash
cp mlflow.db /tmp/mlflow-snapshot.db
claude mcp add mlflow-db -- uvx mcp-server-sqlite --db-path /tmp/mlflow-snapshot.db
```

Example query to ask for: runs whose `tags.git_dirty` is `false` in experiment
`rd_shell.silta_parity`.

**4. MLflow's built-in MCP (optional). Why not by default:**

- `mlflow mcp run` (MLflow 3.16) exposes **traces** (GenAI logging), not
  experiment runs;
- add it only if you start tracing LLM calls.

```bash
claude mcp add mlflow-traces -- uv run mlflow mcp run
```

**5. arXiv (third-party, optional). Why:** to search and download candidate
papers for `/extract-paper`. Check the package before trusting it.

```bash
claude mcp add arxiv -- uvx arxiv-mcp-server
```

**Project-shared version** (`.mcp.json` at the repo root, no secrets; Claude
Code expands `${VAR}`):

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${GITHUB_PAT}" }
    },
    "fetch": { "command": "uvx", "args": ["mcp-server-fetch"] },
    "mlflow-db": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/tmp/mlflow-snapshot.db"]
    }
  }
}
```

**Not recommended:**

- MCP servers that touch `data/raw` or the DVC store: the data is licensed,
  and the deny rules exist for a reason.
- Any server that would send Datastream rows to an external service.

### 3.3 Recommended skills

**Already useful as is (built-in to Claude Code):**

- `/code-review`: before merging a PR.
- `/security-review`: before adding any network-facing code.
- `/simplify`: after a feature lands.
- `/fewer-permission-prompts`: after a few sessions, to allowlist safe
  read-only commands.

**Proposed new project skills.** Each is a `SKILL.md` in
`.claude/skills/<name>/`.

`add-dataset`: the SOP-3 data recipe as a checklist.

```markdown
---
name: add-dataset
description: Onboard a new raw dataset into the lab safely: metadata JSON, DVC add, converter stage with self-checks, config, dvc.yaml stage, tests that skip without the data.
---

# Add dataset

1. Never edit or copy into data/raw yourself: ask the user to place the files and run `uv run dvc add`.
2. Write data/metadata/<name>.json (source, licence, md5 per file, known issues).
3. Converter in src/quant_lab/data/: deterministic, asserts invariants, raises on violation.
4. Config in conf/data/ or conf/dlc/; foreach entry in dvc.yaml (deps, params, outs, metrics).
5. Tests: unit on synthetic inputs; real-data test that skips when the archive is absent.
6. Record any sample-design choice in research/reports/data_decisions.md before running analyses.
7. Gate: uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

`replicate-table`: compare our numbers with a paper's table.

```markdown
---
name: replicate-table
description: Replicate one table of a paper from the lab's data and compare every number with research/evidence/<paper>_evidence.csv, reporting matches, near-misses (rounding/truncation) and real differences without adjusting data to fit.
---

# Replicate table

1. Read the table's rows in research/evidence/<paper>_evidence.csv and the method in research/methodology/<paper>.md.
2. Compute with a module in src/quant_lab/models/<paper>.py; log to MLflow (dejong.replication pattern).
3. Compare per cell: within rounding or truncation of the printed decimals = match.
4. Never change data or code to make a number match. Investigate differences (window, units, data version) and document them.
5. Pin the outcome in a real-data test (matches + known differences), as tests/integration/test_dejong_real.py does.
6. Write research/reports/<paper>_<table>.md with the full comparison.
```

### 3.4 Filesystem and other integrations

**Claude Code** (CLI, desktop or web) already has filesystem access to the
repository. No filesystem MCP is needed there, and the permission deny-list
plus the guard hook protect raw data.

**Claude Desktop (chat app)** users who want the research notes, not the
code, can give it read access to `research/` and `docs/` only:

```json
{
  "mcpServers": {
    "lab-notes": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem",
               "/home/<you>/projects/quant-lab/research",
               "/home/<you>/projects/quant-lab/docs"]
    }
  }
}
```

Put this in `claude_desktop_config.json`. Do **not** include `data/` or the
DVC store.

**Hooks worth adding** in `.claude/settings.json`; Claude must ask before
editing this file.

Merge these into the existing `"hooks"` object, next to the current
`PreToolUse` guard:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv run ruff format -q src tests >/dev/null 2>&1 || true"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv sync --locked -q" }
        ]
      }
    ]
  }
}
```

- **PostToolUse** keeps ruff formatting clean after every edit.
- **SessionStart** installs the environment in cloud sessions, so tests can
  run straight away.

**Cloud Claude Code sessions** can't reach your local DVC store. Either upload
the archives to the session, which is what was done in this project, or set up
a cloud DVC remote (see the open questions).

### 3.5 Copy-paste prompts

```text
Read CLAUDE.md, ROADMAP.md, docs/ARCHITECTURE.md and docs/OPERATIONS.md. Then tell me the
current step, what is done, and the one proposed next step. Do not change anything yet.
```

```text
/audit-backtest Audit the current branch diff (git diff main...HEAD). Run the gate first,
then the backtest-auditor agent; settle every HYPOTHESIS with a falsification test.
```

```text
Impact analysis only, no edits: list every caller and every test that pins
quant_lab.backtest.run.execution_targets, and the MLflow numbers that could move if I change it.
```

```text
Using the mlflow-db MCP server, list all runs in experiment rd_shell.silta_parity with
git_dirty=false: run_id, period, sharpe, total_return, git_commit. Aggregates only.
```

```text
/replicate-table Replicate Table IV of research/extraction/dejong_dlc.md for all 12 twins
(ROADMAP step 16). Follow research/methodology/dejong_dlc.md; never adjust data to match.
```

---

## 4. Assumptions

- **Single owner, local infrastructure.** No server, scheduler, container,
  cloud storage or secret store exists in the repository, so none is
  documented. If one exists outside the repo, it is not covered here.
- **DVC remote.** `~/dvc-store` on the data owner's machine is the only data
  store, inferred from `README.md` and `.dvc/config.local`. Its backup
  arrangements are unknown.
- **GitHub repository.** `tsNoordam/quant-lab` (renamed from `quant-research`).
  `main` is the integration branch; paper-2 work flows through `Dijk-paper`.
- **Third-party MCP packages.** `mcp-server-fetch`, `mcp-server-sqlite` and
  `arxiv-mcp-server` were named from public registries and not executed in
  this environment. Verify versions before use. The GitHub MCP URL and
  `claude mcp add` syntax follow the current Claude Code documentation.
- **Run times** (about 2 min pytest, about 35 min robustness) were measured in
  a cloud container and will differ on a laptop.
