#!/usr/bin/env python3
"""PreToolUse guard for Bash: protected files change only through Edit/Write.

Read-only agents (backtest-auditor, red-team, ...) have Bash but no Edit/Write
tool. This hook stops them, and everyone else, from editing protected paths
through the shell:

- deny: in-place edits (sed -i, perl -i, awk -i inplace), output redirects
  (>, >>, &>) and tee into a protected path.
- ask:  moving, copying over, or deleting a protected path (mv, cp, rm, ...,
  find -delete/-exec, git rm/mv/checkout --/restore), and git reset --hard /
  git clean, which rewrite the working tree.

Best-effort, not a sandbox: an interpreter that writes files itself
(``python -c "open(...)"``) is not detected.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import sys

PROTECTED_DIRS = ("src/", "tests/", "conf/", "data/raw/", "papers/raw/", ".claude/", ".dvc/")
PROTECTED_FILES = ("CLAUDE.md", "dvc.yaml", "dvc.lock", "pyproject.toml", "uv.lock", ".gitignore")

SEPARATORS = {";", "&&", "||", "|", "|&", "&", "(", ")", "\n"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
WRAPPERS = {"sudo", "command", "time", "nice", "nohup", "env", "xargs", "exec"}
SHELLS = {"bash", "sh", "zsh", "dash"}
DELETE_OR_MOVE = {"mv", "rm", "rmdir", "unlink", "shred", "chmod", "chown", "truncate"}
COPY_TO_LAST_ARG = {"cp", "ln", "install", "rsync"}
GIT_PATH_SUBCOMMANDS = {"rm", "mv", "checkout", "restore"}


def _relative(token: str, cwd: str, project: str) -> str | None:
    """Project-relative POSIX path for ``token``, or None if it is outside the project."""
    token = token.strip()
    if not token or token.startswith("-"):
        return None
    path = token if os.path.isabs(token) else os.path.join(cwd, token)
    rel = posixpath.normpath(os.path.relpath(os.path.normpath(path), project).replace(os.sep, "/"))
    if rel == ".." or rel.startswith("../"):
        return None
    return rel


def _is_protected(token: str, cwd: str, project: str) -> bool:
    rel = _relative(token, cwd, project)
    if rel is None:
        return False
    if rel == "." or rel.startswith("*"):
        return True  # the project root or a bare glob covers protected paths
    if rel in PROTECTED_FILES:
        return True
    return any(rel == d.rstrip("/") or rel.startswith(d) for d in PROTECTED_DIRS)


HEREDOC = re.compile(
    r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n.*?^[ \t]*\2[ \t]*$", re.M | re.S
)


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies: they are data (commit messages, file contents), not commands."""
    return HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0] + "\n", command)


def _tokens(command: str) -> list[str]:
    lexer = shlex.shlex(_strip_heredocs(command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _segments(tokens: list[str]) -> list[list[str]]:
    segments, current = [], []
    for tok in tokens:
        if tok in SEPARATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def _strip_prefix(seg: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and wrapper commands (sudo, env, xargs...)."""
    i = 0
    while i < len(seg):
        tok = seg[i]
        if "=" in tok and not tok.startswith("-") and tok.split("=", 1)[0].isidentifier():
            i += 1
        elif tok in WRAPPERS:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 1
        else:
            break
    return seg[i:]


def _has_inplace_flag(prog: str, args: list[str]) -> bool:
    if prog == "awk" or prog == "gawk":
        return "inplace" in args
    for a in args:
        if a == "--in-place" or a.startswith("--in-place="):
            return True
        if a.startswith("-") and not a.startswith("--") and "i" in a[1:]:
            return True
    return False


def _check_segment(seg: list[str], cwd: str, project: str) -> tuple[str, str] | None:
    # Output redirects anywhere in the segment.
    for i, tok in enumerate(seg[:-1]):
        if tok in REDIRECTS and _is_protected(seg[i + 1], cwd, project):
            return "deny", f"shell redirect into protected path '{seg[i + 1]}'"

    words = [t for i, t in enumerate(seg) if not (i > 0 and seg[i - 1] in REDIRECTS)]
    words = [w for w in words if w not in REDIRECTS and w not in {">&", "<", "<<", "<<<"}]
    words = _strip_prefix(words)
    if not words:
        return None
    prog, args = posixpath.basename(words[0]), words[1:]
    protected_args = [a for a in args if _is_protected(a, cwd, project)]

    if prog in SHELLS and "-c" in args:
        idx = args.index("-c")
        if idx + 1 < len(args):
            return check_command(args[idx + 1], cwd, project)

    if prog in {"sed", "perl", "awk", "gawk"} and protected_args and _has_inplace_flag(prog, args):
        return "deny", f"in-place '{prog}' edit of protected path '{protected_args[0]}'"
    if prog == "tee" and protected_args:
        return "deny", f"tee into protected path '{protected_args[0]}'"

    if prog in DELETE_OR_MOVE and protected_args:
        return "ask", f"'{prog}' on protected path '{protected_args[0]}'"
    if prog in COPY_TO_LAST_ARG and args and _is_protected(args[-1], cwd, project):
        return "ask", f"'{prog}' overwriting protected path '{args[-1]}'"
    if prog == "find" and protected_args and {"-delete", "-exec", "-execdir"} & set(args):
        return "ask", f"'find' with -delete/-exec under protected path '{protected_args[0]}'"

    if prog == "git" and args:
        sub, rest = args[0], args[1:]
        if sub == "reset" and "--hard" in rest:
            return "ask", "'git reset --hard' rewrites the working tree"
        if sub == "clean":
            return "ask", "'git clean' deletes untracked files"
        if sub in GIT_PATH_SUBCOMMANDS:
            hits = [a for a in rest if _is_protected(a, cwd, project)]
            if hits:
                return "ask", f"'git {sub}' on protected path '{hits[0]}'"
    return None


def check_command(command: str, cwd: str, project: str) -> tuple[str, str] | None:
    """Return (decision, reason) for a shell command, or None to allow it."""
    try:
        tokens = _tokens(command)
    except ValueError:
        return "ask", "could not parse the shell command"
    decisions = []
    for seg in _segments(tokens):
        if seg[0] == "cd":  # follow `cd dir && ...` so relative paths resolve correctly
            target = seg[1] if len(seg) > 1 else os.path.expanduser("~")
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
            continue
        if decision := _check_segment(seg, cwd, project):
            decisions.append(decision)
    for wanted in ("deny", "ask"):
        for decision in decisions:
            if decision[0] == wanted:
                return decision
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    cwd = payload.get("cwd") or os.getcwd()
    project = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    result = check_command(command, cwd, project)
    if result is None:
        return 0
    decision, reason = result
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": (
                    f"guard_bash: {reason}. Use the Edit/Write tools for code and config; "
                    "data/raw and papers/raw are immutable."
                ),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
