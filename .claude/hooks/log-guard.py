#!/usr/bin/env python3
"""Stop-hook nudge for the shared agent log (advisory only, never blocks).

``concurrency.md`` makes the shared log a first-class session artifact, but
until now nothing detected the failure mode the steering doc names explicitly:
a session that stops writing to it partway through, in silence. This hook
detects the mechanical fact — this session's branch holds commits `main`
lacks, and this session's own transcript contains no append to the shared log
— and prints a one-time nudge naming the ``printf`` line to fix it.

It is deliberately **not** ``change-guard.py``: that file enforces the
worktree-and-merge-back ritual (a different rule, with a blocking Stop check
already earned by its own contract) and mixing a second, advisory-only rule
into it would blur which rule any given block belongs to — the same reasoning
that keeps ``queue-guard.py`` separate. This hook shares its structural
pattern (payload -> per-session sentinel -> transcript-derived signal) but not
its file, and unlike both siblings it never sets ``decision: block``.

**What this does not, and must not, do** (``concurrency.md``, "What the log is
not"): it never reads or judges ``CLAIM`` lines, never treats a peer's claim as
something to gate on, and never fires because a *peer* did or did not log.

Why "did I log" is answered from the TRANSCRIPT, not from the log
-----------------------------------------------------------------
Two earlier versions of this hook tried to answer "did *this session* write to
the shared log" by reading the shared log. Both were wrong, in the same way.

The first scoped both signals to "since this session's first transcript
timestamp", so ``log_touched_since`` returned true if **any** peer logged
inside the window. Replayed against 33 real transcripts it was silent on 33 of
33. The second rekeyed to branch identity and substring-matched
``{branch, branch-with-dashes, slug}`` against every line. One real peer line
— ``.git/agent-log`` line 180, a ``queue-sweep-0727`` NOTE enumerating ten
unmerged implementer branches — names all ten of those sessions' branches and
would have suppressed every one of their nudges.

The shared log simply carries no field that identifies a session:

* Column 4 is free prose, and peers routinely name each other's branches.
* Column 2 *is* a real tab-delimited field, but it is a **work label** chosen
  freely by each session's own prose, and it is many-to-many with sessions in
  this repo's own history: the label ``impl-training-load`` was written by two
  distinct Claude Code sessions, and one session wrote under both
  ``impl-athlete-benchmarks`` and ``impl-load-channels``. So even *exact*
  column-2 matching lets a peer suppress this session's nudge. There is no
  tightening of a log-derived match that fixes this; the information is not
  in the file.

The one artifact that is this session's by construction is its **transcript**,
handed to the hook as ``transcript_path`` in the Stop payload. A peer's tool
calls cannot appear in it. ``queue-guard.py``'s ``wrote_to_queue`` already
answers the sibling Development Rule's identical question exactly this way;
this hook now follows that precedent rather than only its structural shape.

The two signals are therefore:

* **Commits** — ``git rev-list --count main..HEAD``, i.e. commits this branch
  holds that `main` does not. Session-scoped via this repo's own rule
  (concurrency.md: "one git worktree per session... never two sessions in one
  working tree"), unaffected by rebase (no dates involved) and by how long the
  session has been paused (no transcript timestamp involved).
* **Logged** — did a tool call *in this session's transcript* append to the
  agent log. Requires a redirect, not a mention: real transcripts here read
  the log far more often than they write it (one has 11 read-only touches
  against 3 appends), and reading coordinates nothing.

Residual imprecision, stated rather than hidden: a session resumed into a
*new* transcript file cannot see its earlier appends and may be nudged
redundantly. That is a false *positive* on an advisory nudge — it costs a
line the peer can already read. The failure both previous rounds had was the
false *negative*, silence, which is unrecoverable.

Known gap, stated rather than hidden: this only fires while the session is on
a non-``main`` branch. A session that commits directly to `main` (the
declared-trivial escape hatch in ``change-guard.py``) or that performs the
``--ff-only`` merge itself from the `main` tree produces no branch-relative
commit count to check, and is silently out of scope here. Catching that case
would need a true session-scoped baseline (a ``SessionStart`` hook recording
a byte offset into the log, unavailable to a Stop-only hook) rather than a
heuristic layered on top of an already-approximate one.

Uses ``datetime.timezone.utc`` rather than the ``datetime.UTC`` alias
(``ruff --select UP017`` will suggest the alias): hooks run as plain
``python3`` per ``.claude/settings.json``, whatever interpreter is first on
``PATH`` at hook-run time, not this repo's pinned ``uv`` environment.
``timezone.utc`` works on every Python 3 this hook might run under; the
``UTC`` alias needs 3.11+. (Not a claim about which interpreter this
machine's login shell actually resolves ``python3`` to — see the commit
message / queue for that.)

``systemMessage`` vs ``hookSpecificOutput.additionalContext`` on Stop
-----------------------------------------------------------------------
Claude Code's own bundled documentation (``claude-code-docs`` skill content,
present verbatim in the installed CLI binary) draws a real distinction here:
``systemMessage`` is "a message to the user" (all hooks) — UI-only — while
``hookSpecificOutput`` for the ``Stop`` event carries ``additionalContext``,
documented as "non-error feedback delivered to the model; the conversation
continues so the model can act on it." A Stop hook that wants the *session*
(the only actor that can still append a log line before it ends) to see the
nudge — without blocking, per this hook's advisory contract — needs
``additionalContext``, not a bare ``systemMessage``. This hook sets both: the
``systemMessage`` so a human watching the transcript sees it too, and
``hookSpecificOutput.additionalContext`` so the model actually receives it
and can act before the session truly ends. This was confirmed by reading the
docs Claude Code itself ships (two independent doc strings, in different
locations, agreeing); a live nested-session test to observe the behavior
directly was attempted and blocked by this environment's permission
classifier, so this is the strongest evidence available from inside this
worktree, not a live behavioral trace. **This is the reason the "blocking or
advisory" open question in the queue item is still worth putting to the
maintainer**: the previous ``systemMessage``-only version of this hook may
have never been seen by any session at all.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

NUDGE_TEMPLATE = """This session's branch `{branch}` holds {count} commit(s) `main` \
doesn't, and this session appended nothing to the shared agent log:

  {log_path}

concurrency.md: "A session that believes it is solo still writes." If this \
session's work is coordination-relevant to a peer, append a line before \
finishing, e.g.:

  LOG="$(git rev-parse --git-common-dir)/agent-log"
  printf '%s\\t%s\\t%s\\t%s\\n' "$(date -u +%FT%TZ)" "<session>" MERGED \
"<what landed, and where>" >> "$LOG"

(Use CLAIM / TOUCHING / TASK-DONE / WARN / NOTE / RELEASE / BLOCKED instead of \
MERGED as fits what actually happened — vocabulary: concurrency.md.)

This is advisory only — it never blocks stopping and never judges a peer's \
claim, only this session's own branch. If there is genuinely nothing a peer \
needs to know, ignore this."""


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


def common_git_dir(cwd: Path) -> Path | None:
    code, out = run_git(["rev-parse", "--git-common-dir"], cwd)
    if code != 0 or not out:
        return None
    path = Path(out)
    return path if path.is_absolute() else cwd / path


def current_branch(cwd: Path) -> str | None:
    code, out = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if code != 0 or not out or out == "HEAD":
        return None
    return out


def commits_ahead_of_main(cwd: Path) -> int:
    """Commits on HEAD that `main` does not have. Not date-based: immune to

    `git rebase` rewriting committer dates and to multi-day/paused sessions,
    and — because it is a set difference against `main`, not a window over
    "reachable from HEAD" — immune to a peer's unrelated commit or merge
    landing on `main` during this session's run.
    """
    code, out = run_git(["rev-list", "--count", "main..HEAD"], cwd)
    if code != 0 or not out.isdigit():
        return 0
    return int(out)


def session_appended_to_log(transcript: Path) -> bool:
    """True if a tool call *in this session* appended to the agent log.

    The transcript is the only artifact that is this session's by
    construction, so nothing a peer did can move this answer — the property
    both earlier log-derived versions of this check failed.

    A redirect is required, not a mention: `cat "$LOG"` names the log and
    coordinates nothing, and real transcripts in this repo read the log more
    often than they write it.
    """
    if not transcript.is_file():
        return False
    try:
        with transcript.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "agent-log" not in line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = (entry.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue
                    command = (block.get("input") or {}).get("command")
                    if not isinstance(command, str):
                        continue
                    if "agent-log" in command and ">>" in command:
                        return True
    except OSError:
        return False
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("hook_event_name", "Stop") != "Stop":
        return 0
    if payload.get("stop_hook_active"):
        return 0

    session_id = str(payload.get("session_id", ""))
    sentinel = Path(os.environ.get("TMPDIR", "/tmp")) / f"log-guard-{session_id}"
    if session_id and sentinel.exists():
        return 0

    cwd = Path(payload.get("cwd") or Path.cwd())
    root = repo_root(cwd)
    if root is None:
        return 0

    log_dir = common_git_dir(cwd)
    if log_dir is None:
        return 0
    log_path = log_dir / "agent-log"

    branch = current_branch(cwd)
    if not branch or branch == "main":
        # Known gap (see module docstring): a session committing directly to
        # `main`, or merging from the `main` tree, has no branch-relative
        # commit count to check here.
        return 0

    ahead = commits_ahead_of_main(cwd)
    if ahead == 0:
        return 0

    if session_appended_to_log(Path(payload.get("transcript_path", ""))):
        return 0

    if session_id:
        with contextlib.suppress(OSError):
            sentinel.touch()

    message = NUDGE_TEMPLATE.format(branch=branch, count=ahead, log_path=log_path)
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
