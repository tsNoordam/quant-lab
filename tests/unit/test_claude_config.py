"""The Claude Code agents, skills and settings are part of the lab's controls: pin them."""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENTS = sorted((ROOT / ".claude" / "agents").glob("*.md"))
SKILLS = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
KNOWN_TOOLS = {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
READ_ONLY_AGENTS = {
    "backtest-auditor",
    "red-team",
    "paper-reader",
    "quant-researcher",
    "robustness-researcher",
}


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    _, header, body = text.split("---\n", 2)
    return yaml.safe_load(header), body


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_agent_frontmatter(path):
    meta, body = frontmatter(path)
    assert meta["name"] == path.stem
    assert len(meta["description"]) > 40
    tools = {t.strip() for t in meta["tools"].split(",")}
    assert tools <= KNOWN_TOOLS, tools - KNOWN_TOOLS
    assert body.strip()


@pytest.mark.parametrize("name", sorted(READ_ONLY_AGENTS))
def test_read_only_agents_have_no_write_tools(name):
    meta, _ = frontmatter(ROOT / ".claude" / "agents" / f"{name}.md")
    tools = {t.strip() for t in meta["tools"].split(",")}
    assert not tools & WRITE_TOOLS, f"{name} must stay read-only"


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_skill_frontmatter(path):
    meta, body = frontmatter(path)
    assert meta["name"] == path.parent.name
    assert len(meta["description"]) > 40
    assert body.strip()


def test_backtest_auditor_contract():
    meta, body = frontmatter(ROOT / ".claude" / "agents" / "backtest-auditor.md")
    for required in ("READ-ONLY", "unlock_oos", "HYPOTHESIS", "CONFIRMED", "Falsification test"):
        assert required in body, f"auditor prompt lost its '{required}' rule"


def test_bash_guard_hook_is_wired():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    commands = [h["command"] for e in settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("guard_bash.py" in c for c in commands)
    assert (ROOT / ".claude" / "hooks" / "guard_bash.py").exists()
