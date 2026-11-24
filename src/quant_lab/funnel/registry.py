"""Append-only event log, derived SQLite index and the multiple-testing budget.

The log (research/funnel/log.jsonl) is the only place where status, stage and tests are
recorded. Entries are validated against the transition table and the actor rules before
they are appended; existing lines are never rewritten.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from scipy.stats import norm

from .cards import load_cards
from .schema import (
    ACTORS,
    CODE_MAY,
    COUNTED_KINDS,
    PROMOTION_NEEDS,
    REJECT_REASONS,
    STAGES,
    STATUSES,
    TERMINAL,
    TEST_KINDS,
    TRANSITIONS,
    VERDICTS,
)

ROOT = Path(__file__).resolve().parents[3]
FUNNEL_DIR = ROOT / "research" / "funnel"
CARDS_DIR = FUNNEL_DIR / "ideas"
LOG_FILE = FUNNEL_DIR / "log.jsonl"
INDEX_FILE = ROOT / ".cache" / "funnel_index.sqlite"


class LogError(ValueError):
    """An entry that would break the register's rules."""


@dataclass
class IdeaState:
    status: str | None = None
    stage: str | None = None
    tests: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def read_log(path: Path = LOG_FILE) -> list[dict]:
    if not Path(path).exists():
        return []
    out = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise LogError(f"log line {i} is not valid JSON: {e}") from e
    return out


def replay(entries: list[dict]) -> dict[str, IdeaState]:
    """Validate every entry in order and return the state per idea."""
    states: dict[str, IdeaState] = {}
    for i, e in enumerate(entries, 1):
        try:
            check(e, states)
        except LogError as err:
            raise LogError(f"log entry {i} ({e.get('idea')}): {err}") from err
        apply(e, states)
    return states


def check(e: dict, states: dict[str, IdeaState]) -> None:
    idea = e.get("idea")
    if not idea:
        raise LogError("entry without idea id")
    actor = e.get("actor")
    if actor not in ACTORS:
        raise LogError(f"actor must be one of {ACTORS}")
    st = states.get(idea, IdeaState())
    kind = e.get("type")
    if kind == "status":
        to, frm = e.get("to"), st.status
        if to not in STATUSES:
            raise LogError(f"unknown status {to!r}")
        if frm is None:
            if to != "inbox":
                raise LogError("the first status of an idea must be inbox")
        else:
            if frm in TERMINAL:
                raise LogError(f"{frm} is terminal; record a new card instead")
            if to not in TRANSITIONS.get(frm, ()) and not (actor == "code" and to == frm):
                raise LogError(f"transition {frm} -> {to} is not allowed")
        if actor == "judge":
            raise LogError("the Judge may not change a status")
        if actor == "code" and frm is not None and to not in CODE_MAY.get(frm, ()):
            raise LogError(f"code may not move {frm} -> {to}")
        is_rejection = to.startswith("rejected") or to == "duplicate"
        if is_rejection and e.get("reason") not in REJECT_REASONS:
            raise LogError(f"a rejection needs a reason from {sorted(REJECT_REASONS)}")
        need = PROMOTION_NEEDS.get((frm, to))
        if need and not any(t["kind"] == need and t["verdict"] == "pass" for t in st.tests):
            raise LogError(f"{frm} -> {to} needs a passed '{need}' test first")
        if e.get("override") and actor != "human":
            raise LogError("only a human may override a hard stop")
        if to == "hypothesis" and frm in ("inbox", "needs_info") and not e.get("override"):
            last = [t for t in st.tests if t["kind"] == "screen"]
            if not last or last[-1]["verdict"] != "pass":
                raise LogError(
                    "-> hypothesis needs a screen without FAIL or UNKNOWN "
                    "(or an explicit human override with its reason)"
                )
        if e.get("stage") is not None and e["stage"] not in STAGES:
            raise LogError(f"unknown stage {e['stage']!r}")
    elif kind == "test":
        if st.status is None:
            raise LogError("test for an idea that is not in the register")
        if e.get("kind") not in TEST_KINDS:
            raise LogError(f"test kind must be one of {TEST_KINDS}")
        if e.get("verdict") not in VERDICTS:
            raise LogError(f"verdict must be one of {VERDICTS}")
        if actor == "judge":
            raise LogError("the Judge may not record tests")
        if e["kind"] in COUNTED_KINDS and not e.get("spec"):
            raise LogError("a counted test needs the spec file written before it ran")
    elif kind == "note":
        if st.status is None:
            raise LogError("note for an idea that is not in the register")
    else:
        raise LogError("type must be status, test or note")


def apply(e: dict, states: dict[str, IdeaState]) -> None:
    st = states.setdefault(e["idea"], IdeaState())
    st.events.append(e)
    if e["type"] == "status":
        st.status = e["to"]
        if e.get("stage"):
            st.stage = e["stage"]
    elif e["type"] == "test":
        st.tests.append(e)


def append(entry: dict, path: Path = LOG_FILE) -> dict:
    """Validate against the current log and append one line. Never rewrites the file."""
    entry = {"ts": entry.get("ts") or now(), **{k: v for k, v in entry.items() if k != "ts"}}
    states = replay(read_log(path))
    check(entry, states)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=False) + "\n")
    return entry


# ------------------------------------------------------------------ budget
def counted_tests(entries: list[dict]) -> int:
    return sum(1 for e in entries if e.get("type") == "test" and e.get("kind") in COUNTED_KINDS)


def t_hurdle(n_tests: int, t_floor: float = 3.0) -> float:
    """t-stat a new result must beat: max(floor, two-sided Bonferroni at 5% over n tests)."""
    n = max(int(n_tests), 1)
    return max(float(t_floor), float(norm.ppf(1 - 0.025 / n)))


# ------------------------------------------------------------------ index
def build_index(
    cards_dir: Path = CARDS_DIR, log_path: Path = LOG_FILE, db_path: Path = INDEX_FILE
) -> Path:
    """Rebuild the SQLite index from the cards and the log (derived, git-ignored)."""
    cards = load_cards(cards_dir)
    entries = read_log(log_path)
    states = replay(entries)
    missing = sorted(set(states) - set(cards))
    if missing:
        raise LogError(f"log mentions ideas without a card: {missing}")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(db_path).exists():
        Path(db_path).unlink()
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE ideas (id TEXT PRIMARY KEY, title TEXT, market_class TEXT, source_type TEXT,
                            source_ref TEXT, published TEXT, status TEXT, stage TEXT);
        CREATE TABLE events (seq INTEGER PRIMARY KEY, ts TEXT, idea TEXT, type TEXT, actor TEXT,
                             frm TEXT, to_status TEXT, stage TEXT, kind TEXT, verdict TEXT,
                             reason TEXT, note TEXT, spec TEXT, result TEXT);
    """)
    for c in cards.values():
        s = states.get(c.id, IdeaState())
        con.execute(
            "INSERT INTO ideas VALUES (?,?,?,?,?,?,?,?)",
            (
                c.id,
                c.title,
                c.market_class,
                c.source_type,
                c.source_ref,
                c.published,
                s.status,
                s.stage,
            ),
        )
    prev: dict[str, str | None] = {}
    for i, e in enumerate(entries, 1):
        frm = prev.get(e["idea"]) if e["type"] == "status" else None
        con.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                i,
                e.get("ts"),
                e["idea"],
                e["type"],
                e["actor"],
                frm,
                e.get("to"),
                e.get("stage"),
                e.get("kind"),
                e.get("verdict"),
                e.get("reason"),
                e.get("note"),
                e.get("spec"),
                e.get("result"),
            ),
        )
        if e["type"] == "status":
            prev[e["idea"]] = e["to"]
    con.commit()
    con.close()
    return Path(db_path)
