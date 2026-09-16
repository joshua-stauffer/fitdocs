#!/usr/bin/env python3
"""PreToolUse + Stop guard for the change protocol.

The worktree-and-merge-back ritual was written for spec implementation and
obeyed only there: steering, skills, hooks and spec docs were edited straight
onto ``main`` and left uncommitted. Those files decide how every later session
behaves, so this guard applies the same ritual to all of them.

Two events, one policy (contract: ``.kiro/steering/change-protocol.md``):

* **PreToolUse** — deny ``Edit``/``Write``/``NotebookEdit`` against a tracked
  repo path while ``HEAD`` is ``main``, and deny ``git commit`` on ``main``.
* **Stop** — block once if the session wrote tracked files that are still
  uncommitted, is sitting on a branch holding commits ``main`` lacks, is on a
  branch holding commits its upstream lacks (or with commits and no upstream
  at all — never pushed), or if ``main`` holds commits ``origin/main`` lacks.

The push half dates from 2026-09-16, when a subagent's ``cd <missing> && rm
-rf .git`` ran in the main tree with ``main`` eight commits and a whole spec
batch ahead of the remote. A commit that exists on one machine is not landed;
the remote is only guaranteed current if every commit is pushed as it is made.

Escape hatch: ``touch "$TMPDIR/fitdocs-trivial-<session-id>"`` declares the
session's change trivial. Deliberate, one command, visible in the transcript.

Limits, by design: file tools and ``git commit`` only — writes through other
shell commands are on the honor system — and any git command that fails lets
the write through. A ratchet against drift, not a security boundary.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAIN_BRANCH = "main"
REMOTE = "origin"

WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

# Paths that stay writable on main. .kiro/queue/ is exempt because the Stop
# hook in queue-guard.py demands a queue write at session end; guarding it
# would deadlock the two hooks against each other.
EXEMPT_PREFIXES = (".kiro/queue/", ".git/", ".claude/settings.local.json")

# `git commit` in any form (incl. `git -C path commit`, `git commit --amend`).
# `git merge --ff-only`, the sanctioned way work reaches main, is untouched.
GIT_COMMIT = re.compile(r"\bgit\b(?:\s+-[^\s]+(?:\s+[^\s]+)?)*\s+commit\b")

# `git -C <path> commit` lands in <path>'s tree, which is often not the
# session's cwd — a session rooted at main driving a commit into its worktree.
GIT_DASH_C = re.compile(r"\bgit\b[^|&;]*?\s-C\s+(\"[^\"]+\"|'[^']+'|\S+)")

# `cd ../fitdocs-<slug> && git commit` is the lifecycle change-protocol.md
# prescribes. The Bash tool resets its working directory between calls, so the
# command text is the only place that directory change is visible — a session
# working inside a worktree still reports the main tree as its cwd.
CD_PREFIX = re.compile(r"^\s*(?:cd|pushd)\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)")

# A path the shell would expand ($VAR, `cmd`, globs) cannot be resolved from
# text alone. Guessing at one is how a guard denies the wrong thing, so an
# unresolvable target is reported rather than silently judged as cwd.
UNRESOLVABLE = re.compile(r"[$`*?]")

WORKTREE_HINT = """Start a worktree instead:

  git worktree add ../fitdocs-<slug> -b chore/<slug>   # impl/<spec> for spec work
  cd ../fitdocs-<slug> && uv sync

Or, if this change really is trivial (a typo, a stale path — nothing that
changes how a later session behaves), declare it in its OWN tool call — this
one is judged before any of it runs, so a `touch && git commit` one-liner is
still denied — and then retry:

  touch "{sentinel}"

Contract: .kiro/steering/change-protocol.md"""


def run_git(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run git, returning (returncode, stdout). Any failure is a soft no."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def repo_root(cwd: Path) -> Path | None:
    code, out = run_git(["rev-parse", "--show-toplevel"], cwd)
    return Path(out) if code == 0 and out else None


def current_branch(cwd: Path) -> str | None:
    """Branch name, or None when detached (mid-rebase) or git is unavailable."""
    code, out = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if code != 0 or not out or out == "HEAD":
        return None
    return out


def trivial_sentinel(session_id: str) -> Path:
    tmp = Path(os.environ.get("TMPDIR", "/tmp"))
    return tmp / f"fitdocs-trivial-{session_id or 'unknown'}"


def guarded_path(path_str: str, root: Path) -> str | None:
    """Repo-relative path if the guard covers it, else None.

    Not covered: anything outside the repo (scratchpad, other checkouts),
    gitignored machine-local files, and the exempt prefixes above.
    """
    if not path_str:
        return None
    try:
        resolved = Path(path_str).expanduser().resolve()
        rel = resolved.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    if rel.startswith(EXEMPT_PREFIXES):
        return None
    code, _ = run_git(["check-ignore", "-q", "--", rel], root)
    if code == 0:
        return None
    return rel


def nearest_dir(path: Path) -> Path:
    """Closest existing ancestor directory — the target file may not exist yet."""
    candidate = path if path.is_dir() else path.parent
    while not candidate.is_dir() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def resolve_tree(raw: str, base: Path) -> Path:
    """A path from a command, resolved against the directory it was written in."""
    path = Path(raw).expanduser()
    return nearest_dir(path if path.is_absolute() else base / path)


def commit_tree(command: str, cwd: Path) -> tuple[Path, str | None]:
    """The tree a `git commit` in this command lands in, plus any skipped target.

    A leading `cd` moves the shell; a `git -C` then applies relative to that,
    mirroring what the shell itself would do. Both beat the session's cwd,
    which the Bash tool resets between calls — so a session working inside a
    worktree still reports the main tree. A target the shell would expand
    cannot be resolved from text and is handed back rather than guessed at.
    """
    base, unresolved = nearest_dir(cwd), None
    for pattern in (CD_PREFIX, GIT_DASH_C):
        match = pattern.search(command)
        if not match:
            continue
        raw = match.group(1).strip("\"'")
        if UNRESOLVABLE.search(raw):
            unresolved = unresolved or raw
            continue
        base = resolve_tree(raw, base)
    return base, unresolved


def deny(reason: str) -> int:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    return 0


def handle_pre_tool_use(payload: dict, cwd: Path, session_id: str) -> int:
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if tool not in WRITE_TOOLS and tool != "Bash":
        return 0
    if trivial_sentinel(session_id).exists():
        return 0

    hint = WORKTREE_HINT.format(sentinel=trivial_sentinel(session_id))

    # Judge the tree the write actually lands in, never the session's cwd: a
    # session rooted at main legitimately drives edits and commits into its
    # worktree, and one rooted in a worktree can still reach back into main.
    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        if not GIT_COMMIT.search(command):
            return 0
        tree, unresolved = commit_tree(command, cwd)
        if current_branch(tree) != MAIN_BRANCH:
            return 0
        note = (
            f"\n\n(`{unresolved}` is shell-expanded, so the target tree could "
            f"not be read from the command text and this was judged against "
            f"`{tree}`. Re-run with a literal path if that is not where the "
            f"commit lands.)"
            if unresolved
            else ""
        )
        return deny(
            f"Committing on {MAIN_BRANCH}. Work reaches {MAIN_BRANCH} by "
            f"`git merge --ff-only <branch>`, not by committing into it.{note}"
            f"\n\n{hint}"
        )

    raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not raw:
        return 0
    target = Path(str(raw)).expanduser()
    if not target.is_absolute():
        target = cwd / target
    tree = nearest_dir(target)
    root = repo_root(tree)
    if root is None or current_branch(tree) != MAIN_BRANCH:
        return 0
    rel = guarded_path(str(target), root)
    if rel is None:
        return 0
    return deny(
        f"`{rel}` is a versioned repo path and its tree is on {MAIN_BRANCH}. "
        f"Non-trivial changes — steering, skills, hooks and spec docs included, "
        f"not just src/ — are made on a branch and merged back.\n\n{hint}"
    )


def session_writes(transcript: Path) -> list[str]:
    """File paths this session wrote via file tools, in first-seen order."""
    seen: dict[str, None] = {}
    try:
        with transcript.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                content = entry.get("message", {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    if block.get("name") not in WRITE_TOOLS:
                        continue
                    params = block.get("input") or {}
                    target = params.get("file_path") or params.get("notebook_path")
                    if isinstance(target, str) and target:
                        seen.setdefault(target, None)
    except OSError:
        return []
    return list(seen)


def commits_ahead(branch: str, base: str, cwd: Path) -> int | None:
    """Commits on `branch` that `base` lacks; None when git cannot say."""
    code, out = run_git(["rev-list", "--count", f"{base}..{branch}"], cwd)
    if code != 0 or not out.isdigit():
        return None
    return int(out)


def unpushed(branch: str, cwd: Path) -> str | None:
    """One sentence naming what `branch` holds that the remote lacks, or None.

    `main` is judged against `origin/main` by name from any tree: its upstream
    is fixed by contract, and tracking config is exactly the local state the
    2026-09-16 `.git` loss erased. Any other branch is judged against the
    upstream `git push -u` recorded; none recorded, with commits `main` lacks,
    is itself the finding. A tree with no remote configured is out of scope,
    and a remote ref git cannot resolve is a soft no, as everywhere here.
    """
    code, remotes = run_git(["remote"], cwd)
    if code != 0 or not remotes:
        return None
    if branch == MAIN_BRANCH:
        ahead = commits_ahead(branch, f"{REMOTE}/{MAIN_BRANCH}", cwd)
        if ahead:
            return (
                f"`{MAIN_BRANCH}` holds {ahead} commit(s) that "
                f"`{REMOTE}/{MAIN_BRANCH}` does not have: "
                f"`git push {REMOTE} {MAIN_BRANCH}`."
            )
        return None
    code, upstream = run_git(
        ["for-each-ref", "--format=%(upstream:short)", f"refs/heads/{branch}"], cwd
    )
    if code != 0:
        return None
    ahead = commits_ahead(branch, upstream, cwd) if upstream else None
    if ahead:
        return (
            f"Branch `{branch}` holds {ahead} commit(s) its upstream `{upstream}` "
            f"does not have: `git push` (`--force-with-lease` after a rebase)."
        )
    if ahead is None and commits_ahead(branch, MAIN_BRANCH, cwd):
        return (
            f"Branch `{branch}` has never been pushed — it holds commits and no "
            f"upstream resolves for it: `git push -u {REMOTE} {branch}`."
        )
    return None


def handle_stop(payload: dict, cwd: Path, session_id: str) -> int:
    if payload.get("stop_hook_active"):
        return 0

    sentinel = Path(os.environ.get("TMPDIR", "/tmp")) / f"change-guard-{session_id}"
    if session_id and sentinel.exists():
        return 0

    root = repo_root(cwd)
    if root is None:
        return 0

    transcript = Path(payload.get("transcript_path", ""))
    written = [
        rel
        for path in (session_writes(transcript) if transcript.is_file() else [])
        if (rel := guarded_path(path, root)) is not None
    ]

    problems: list[str] = []

    if written:
        code, out = run_git(["status", "--porcelain", "--", *written], root)
        if code == 0 and out:
            dirty = "\n".join(f"  {line}" for line in out.splitlines())
            problems.append("Files this session wrote are still uncommitted:\n" + dirty)

    branch = current_branch(cwd)
    if branch and branch != MAIN_BRANCH:
        code, out = run_git(["rev-list", "--count", f"{MAIN_BRANCH}..HEAD"], cwd)
        if code == 0 and out.isdigit() and int(out) > 0:
            problems.append(
                f"Branch `{branch}` holds {out} commit(s) that {MAIN_BRANCH} "
                f"does not have. Merge-back is part of the change, not a "
                f"follow-up."
            )
        if (finding := unpushed(branch, cwd)) is not None:
            problems.append(finding)

    # main is everyone's, so it is judged from every tree — including a
    # worktree whose own branch is already merged and whose merge was not pushed.
    if (finding := unpushed(MAIN_BRANCH, cwd)) is not None:
        problems.append(finding)

    if not problems:
        return 0

    if session_id:
        with contextlib.suppress(OSError):
            sentinel.touch()

    reason = (
        "The change protocol's Definition of Done is not met "
        "(.kiro/steering/change-protocol.md):\n\n"
        + "\n\n".join(problems)
        + "\n\nFinish it: run the validation for the change class, commit the "
        "paths by name (never `git add -A`) and push, rebase onto current "
        f"{MAIN_BRANCH} and push `--force-with-lease`, re-run validation, "
        f"merge `--ff-only`, and `git push {REMOTE} {MAIN_BRANCH}`. A commit "
        "that exists on one machine is not landed.\n\n"
        "If the work is deliberately unfinished — a blocked merge, a base that "
        "belongs to someone else, an explicitly mid-flight session — say so in "
        "one line, name what is left uncommitted, and stop."
    )
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = Path(payload.get("cwd") or Path.cwd())
    session_id = str(payload.get("session_id", ""))
    event = payload.get("hook_event_name", "")

    if event == "PreToolUse":
        return handle_pre_tool_use(payload, cwd, session_id)
    if event == "Stop":
        return handle_stop(payload, cwd, session_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
