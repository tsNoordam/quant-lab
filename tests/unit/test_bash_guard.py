"""The Bash guard hook is what keeps read-only agents read-only, so pin its behaviour."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "guard_bash.py"

_spec = importlib.util.spec_from_file_location("guard_bash", HOOK)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

PROJECT = "/work/quant-lab"


def decision(command: str, cwd: str = PROJECT) -> str:
    result = guard.check_command(command, cwd, PROJECT)
    return "allow" if result is None else result[0]


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest",
        "uv add statsmodels",
        "uv run dvc repro",
        "dvc add data/raw/rds_prices.parquet",
        "grep -rn rolling src/",
        "sed -n '1,20p' src/quant_lab/features/rolling.py",
        "cat src/quant_lab/backtest/run.py > /tmp/run_copy.py",
        "uv run pytest 2>&1 | tee reports.log",
        "uv run python -m quant_lab.backtest.run > research/reports/run.txt",
        "rm -rf .venv mlruns outputs",
        "cp src/quant_lab/features/rolling.py /tmp/",
        "git status && git diff src/",
        "git checkout -b experiment/rolling-zscore",
        "mkdir -p data/processed",
    ],
)
def test_allows_read_and_tooling_commands(command):
    assert decision(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "sed -i 's/60/20/' src/quant_lab/features/rolling.py",
        "sed -Ei.bak 's/a/b/' conf/split/default.yaml",
        "perl -pi -e 's/shift\\(1\\)//' src/quant_lab/strategies/baseline.py",
        "echo 'x = 1' > src/quant_lab/backtest/costs.py",
        "printf 'fees: 0\\n' >> conf/costs/flat.yaml",
        "echo hacked | tee tests/structural/test_future_leakage.py",
        "cat new.csv > data/raw/prices.csv",
        "echo '{}' > .claude/settings.json",
        "cd src/quant_lab && sed -i 's/a/b/' features/rolling.py",
        "bash -c \"sed -i 's/a/b/' tests/unit/test_costs.py\"",
        "FOO=1 sudo sed --in-place 's/a/b/' pyproject.toml",
        f"sed -i 's/a/b/' {PROJECT}/src/quant_lab/data/validation.py",
    ],
)
def test_denies_in_place_edits_of_protected_paths(command):
    assert decision(command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "rm tests/unit/test_costs.py",
        "rm -rf src",
        "rm -rf *",
        "mv conf/split/default.yaml /tmp/",
        "cp /tmp/evil.py src/quant_lab/backtest/run.py",
        "find tests -name '*.py' -delete",
        "git checkout -- src/quant_lab/features/rolling.py",
        "git restore tests/",
        "git reset --hard HEAD~1",
        "git clean -fdx",
        "echo 'unbalanced",
    ],
)
def test_asks_before_moving_or_deleting_protected_paths(command):
    assert decision(command) == "ask"


def test_heredoc_bodies_are_data_not_commands():
    commit = "git commit -F - <<'EOF'\nRename claude.md -> CLAUDE.md\n> src/x.py\nEOF\ngit push"
    assert decision(commit) == "allow"
    write = "cat > src/quant_lab/backtest/costs.py <<EOF\nx = 1\nEOF"
    assert decision(write) == "deny"


def test_relative_paths_resolve_against_cwd():
    assert decision("sed -i 's/a/b/' rolling.py", cwd=f"{PROJECT}/src/quant_lab/features") == "deny"
    assert decision("sed -i 's/a/b/' notes.md", cwd=f"{PROJECT}/research") == "allow"


def test_hook_protocol_end_to_end(tmp_path):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "sed -i 's/a/b/' src/quant_lab/features/rolling.py"},
        "cwd": str(tmp_path),
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
        check=True,
    )
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"

    payload["tool_input"]["command"] = "uv run pytest"
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
        check=True,
    )
    assert proc.stdout == ""
