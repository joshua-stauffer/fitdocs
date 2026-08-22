#!/usr/bin/env python3
"""Stop-hook nudge for uncommitted queue items (advisory only, never blocks).

``CLAUDE.md``'s Follow-up Queue rule is enforced by ``queue-guard.py``, which
blocks a Stop when a session's prose defers work and nothing was *written* to
``.kiro/queue/``. Writing is not landing. A queue close is three separate acts
-- flip ``status:``, append a ``## Resolution``, ``git mv`` into ``closed/`` --
and **none of them is the commit**, so a complete, correct, fully verified
resolution can sit in the working tree indefinitely, visible to nobody.

That is not hypothetical. On 2026-07-27 a single session found *two* items in
exactly this state: ``2026-07-25-devfield-declared-scale-ignored`` carried a
finished resolution written by an earlier session and never committed, and the
close of ``2026-07-26-second-load-reader-spellings-escape-guards`` had the same
shape. Both were discovered only because a human happened to look at
``git status``.

The same failure has a worse-known sibling one step further along: the
2026-07-26 closure of the second-reader item cited commit ``8688dcc``, which
was real but lived only on a worktree branch that never merged, so the closure
record survived while its evidence did not. This hook catches the *earlier*
case -- never committed at all -- which is the one a hook can see. See "What
this deliberately does not catch" below.

Why this is its own file, and its own sentinel
----------------------------------------------
``log-guard.py`` sets the precedent (one rule per hook file, so a reader can
tell which rule any given output belongs to), and here that separation is
load-bearing rather than stylistic: ``queue-guard.py`` writes a per-session
sentinel when it fires, and it is a **blocking** hook. Folding this advisory
check into that file and reusing its sentinel would make the two rules
*mutually suppressing* -- a session blocked once for not queueing would then
never be told its queue edits are uncommitted, and vice versa. Separate file,
separate sentinel, no interaction.

Why this needs no session identity
----------------------------------
``log-guard.py``'s two rejected rounds both failed by asking a *shared*
artifact a question only the *session* could answer. This hook cannot repeat
that mistake, because it asks no question about a session at all: the working
tree is the evidence, and ``git status`` reports the same fact no matter who
dirtied it. Nothing here reads the transcript, the shared log, or any peer
state, so no peer's activity can move the verdict in either direction.

This also means the hook fires on dirt this session did not create -- which is
correct and is exactly the case that motivated it. The nudge is worded for
that: it never asserts the session is at fault, only that the tree is dirty.
Per this repo's own rule of one worktree per session (``concurrency.md``), the
dirt is in *this* session's reach regardless of who left it.

Advisory, not blocking
----------------------
A session may legitimately be mid-edit on a queue item when it stops, and the
cost of a miss (one uncommitted file, still on disk, still recoverable) does
not justify refusing to stop. It sets both ``systemMessage`` and
``hookSpecificOutput.additionalContext`` for the reason documented at length
in ``log-guard.py``: on ``Stop``, ``additionalContext`` is what reaches the
*model*, which is the only actor that can still run ``git commit`` before the
session ends.

What this deliberately does not catch
-------------------------------------
* **Committed on a branch that never merges.** ``8688dcc`` above. Detecting it
  would mean judging whether a branch is destined to merge, which is not a
  fact in the repository at Stop time. ``log-guard.py`` covers the adjacent
  case (commits `main` lacks, nothing logged) from a different angle.
* **Committed but not pushed.** This repo has no remote in its workflow;
  ``main`` is the integration point.
* **A close that is wrong.** No hook can verify a resolution's evidence. That
  is ``kiro-queue``'s never-auto-close rule and the reviewer's job.

Uses ``timezone``-free, dependency-free stdlib only and plain ``python3``:
hooks run under whatever interpreter is first on ``PATH`` at hook-run time,
not this repo's pinned ``uv`` environment (see ``log-guard.py``).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

QUEUE_PATHSPEC = ".kiro/queue/"

NUDGE_TEMPLATE = """`.kiro/queue/` has {count} uncommitted change(s):

{listing}

A queue close is three acts -- `status:`, a `## Resolution`, and a `git mv` \
into `closed/` -- and none of them is the commit. Until it is committed, the \
close is invisible to every other worktree, and the next `/kiro-queue` run \
will rank the item as still open.

Appending to or closing a `.kiro/queue/` item is trivial per \
change-protocol.md, so this may be committed on `main` directly -- declare it \
trivial in its own tool call first if `change-guard.py` asks:

  git add .kiro/queue && git commit -m "chore(queue): <what changed>"

This is advisory only -- it never blocks stopping. If these edits are genuinely \
still in progress, ignore it."""


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
    return proc.returncode, proc.stdout


def repo_root(cwd: Path) -> Path | None:
    code, out = run_git(["rev-parse", "--show-toplevel"], cwd)
    out = out.strip()
    return Path(out) if code == 0 and out else None


def dirty_queue_entries(root: Path) -> list[str]:
    """``git status --porcelain`` lines scoped to ``.kiro/queue/``.

    Run from the repository root so the pathspec means the same thing however
    deep in the tree the session's cwd happens to be.

    Covers every way a queue edit can fail to land, because ``--porcelain``
    reports all of them: unstaged (` M`), staged-but-uncommitted (`M `, and
    `R ` for the ``git mv`` a close performs), and untracked (`??`) -- a
    brand-new item file that was never `git add`ed at all.
    """
    code, out = run_git(["status", "--porcelain", "--", QUEUE_PATHSPEC], root)
    if code != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("hook_event_name", "Stop") != "Stop":
        return 0
    # Already continuing because of a stop hook — never chain.
    if payload.get("stop_hook_active"):
        return 0

    session_id = str(payload.get("session_id", ""))
    sentinel = (
        Path(os.environ.get("TMPDIR", "/tmp")) / f"queue-commit-guard-{session_id}"
    )
    if session_id and sentinel.exists():
        return 0

    cwd = Path(payload.get("cwd") or Path.cwd())
    root = repo_root(cwd)
    if root is None:
        return 0

    # No `.kiro/queue/`-exists check here on purpose: an earlier round had one
    # and it was measured INERT -- replacing it with `if False` left all 25
    # tests green, because a pathspec matching nothing already yields no
    # entries. A repo that does not run this workflow is silenced by
    # `dirty_queue_entries` itself, which `test_a_repo_without_a_queue_is_silent`
    # pins (it reddens when the pathspec is dropped). Do not reinstate it as
    # belt-and-braces: it would be an unpinnable line whose deletion nothing
    # detects.
    entries = dirty_queue_entries(root)
    if not entries:
        return 0

    if session_id:
        with contextlib.suppress(OSError):
            sentinel.touch()

    message = NUDGE_TEMPLATE.format(
        count=len(entries),
        listing="\n".join(f"  {entry}" for entry in entries),
    )
    json.dump(
        {
            "continue": True,
            "systemMessage": message,
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": message,
            },
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
