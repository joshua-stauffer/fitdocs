"""The push half of `change-guard.py`'s Stop check: a commit the remote lacks
is reported, and a pushed one is not.

Added 2026-09-16, the day `.git` was deleted with `main` eight commits ahead of
`origin/main` and a whole spec batch on a never-pushed branch. The rule this
pins (`change-protocol.md`, "Push On Commit"): every commit is pushed as it is
made, `-u` on a branch's first push, `--force-with-lease` after a rebase,
`git push origin main` after a merge.

Each scenario asserts the transition -- the finding is present in the unpushed
state and absent after the exact push the contract prescribes -- because the
merge-back finding that already existed fires on any branch with commits
`main` lacks, so a bare "blocks"/"does not block" cannot tell the two apart.
Every reachability precondition (`rev-list` counts) is asserted before the
verdict it justifies.

Mutation evidence for every assertion is recorded in the commit message.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "change-guard.py"

# Markers, one per finding the Stop handler can emit. Each is a phrase that
# appears in exactly one of the handler's messages.
MAIN_UNPUSHED = "`origin/main` does not have"
BRANCH_AHEAD = "its upstream"
NEVER_PUSHED = "never been pushed"
UNMERGED = "Merge-back is part of the change"

_session = itertools.count()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return proc.stdout.strip()


def _commit(repo: Path, name: str) -> None:
    (repo / name).write_text(f"{name}\n")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)


def _ahead(repo: Path, base: str, tip: str = "HEAD") -> int:
    return int(_git(repo, "rev-list", "--count", f"{base}..{tip}"))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on `main` with a bare `origin`, one seed commit, fully pushed."""
    remote = tmp_path / "origin.git"
    remote.mkdir()
    _git(remote, "init", "-q", "--bare", "-b", "main")
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "remote", "add", "origin", str(remote))
    _commit(root, "seed")
    _git(root, "push", "-q", "-u", "origin", "main")
    return root


def stop(repo: Path, tmp_path: Path) -> str:
    """Run the Stop hook with a fresh session id; the block reason, or ""."""
    payload = {
        "hook_event_name": "Stop",
        "session_id": f"t{next(_session)}",
        "cwd": str(repo),
        "transcript_path": str(tmp_path / "no-such-transcript.jsonl"),
        "stop_hook_active": False,
    }
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    assert proc.returncode == 0, proc.stderr
    if not proc.stdout.strip():
        return ""
    emitted = json.loads(proc.stdout)
    assert emitted["decision"] == "block"
    return str(emitted["reason"])


def test_silent_when_main_matches_origin(repo: Path, tmp_path: Path) -> None:
    assert _ahead(repo, "origin/main") == 0
    assert stop(repo, tmp_path) == ""


def test_main_ahead_of_origin_blocks_until_pushed(repo: Path, tmp_path: Path) -> None:
    _commit(repo, "trivial")
    assert _ahead(repo, "origin/main") == 1

    reason = stop(repo, tmp_path)
    assert MAIN_UNPUSHED in reason
    assert "`git push origin main`" in reason
    assert UNMERGED not in reason

    _git(repo, "push", "-q", "origin", "main")
    assert _ahead(repo, "origin/main") == 0
    assert stop(repo, tmp_path) == ""


def test_never_pushed_branch_blocks_until_push_u(repo: Path, tmp_path: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "chore/x")
    _commit(repo, "work")
    assert _ahead(repo, "main") == 1
    upstream = _git(repo, "for-each-ref", "--format=%(upstream)", "refs/heads/chore/x")
    assert upstream == ""

    reason = stop(repo, tmp_path)
    assert NEVER_PUSHED in reason
    assert "`git push -u origin chore/x`" in reason
    assert BRANCH_AHEAD not in reason
    assert UNMERGED in reason

    _git(repo, "push", "-q", "-u", "origin", "chore/x")
    reason = stop(repo, tmp_path)
    assert UNMERGED in reason
    assert NEVER_PUSHED not in reason
    assert BRANCH_AHEAD not in reason


def test_branch_ahead_of_upstream_blocks_until_push(repo: Path, tmp_path: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "chore/x")
    _commit(repo, "first")
    _git(repo, "push", "-q", "-u", "origin", "chore/x")
    _commit(repo, "second")
    assert _ahead(repo, "origin/chore/x") == 1

    reason = stop(repo, tmp_path)
    assert (
        "Branch `chore/x` holds 1 commit(s) its upstream `origin/chore/x` does not have"
        in reason
    )
    assert NEVER_PUSHED not in reason

    _git(repo, "push", "-q")
    assert _ahead(repo, "origin/chore/x") == 0
    reason = stop(repo, tmp_path)
    assert UNMERGED in reason
    assert BRANCH_AHEAD not in reason


def test_rebased_branch_is_unpushed_until_force_with_lease(
    repo: Path, tmp_path: Path
) -> None:
    _git(repo, "checkout", "-q", "-b", "chore/x")
    _commit(repo, "work")
    _git(repo, "push", "-q", "-u", "origin", "chore/x")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "peer")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "chore/x")
    assert _ahead(repo, "origin/chore/x") == 0

    _git(repo, "rebase", "-q", "main")
    assert _ahead(repo, "origin/chore/x") == 2  # peer's commit + the rewritten one
    assert _ahead(repo, "HEAD", "origin/chore/x") == 1  # the orphaned pre-rebase one
    assert BRANCH_AHEAD in stop(repo, tmp_path)

    _git(repo, "push", "-q", "--force-with-lease", "origin", "chore/x")
    assert BRANCH_AHEAD not in stop(repo, tmp_path)


def test_main_is_judged_from_a_branch_tree(repo: Path, tmp_path: Path) -> None:
    _commit(repo, "merged-not-pushed")
    _git(repo, "checkout", "-q", "-b", "chore/x")
    assert _ahead(repo, "main") == 0
    assert _ahead(repo, "origin/main", "main") == 1

    reason = stop(repo, tmp_path)
    assert MAIN_UNPUSHED in reason
    assert UNMERGED not in reason
    assert NEVER_PUSHED not in reason


def test_no_remote_is_out_of_scope(repo: Path, tmp_path: Path) -> None:
    _git(repo, "remote", "remove", "origin")
    assert _git(repo, "remote") == ""
    _commit(repo, "trivial")
    assert stop(repo, tmp_path) == ""

    _git(repo, "checkout", "-q", "-b", "chore/x")
    _commit(repo, "work")
    reason = stop(repo, tmp_path)
    assert UNMERGED in reason
    assert NEVER_PUSHED not in reason
    assert BRANCH_AHEAD not in reason
    assert MAIN_UNPUSHED not in reason
