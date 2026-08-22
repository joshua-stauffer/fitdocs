"""The one property `queue-commit-guard.py` exists to have: a queue edit that
never reached a commit is reported, and nothing else is.

A queue close is three acts -- flip ``status:``, append a ``## Resolution``,
``git mv`` into ``closed/`` -- and none of them is the commit. Two items were
found in exactly that state on 2026-07-27, each carrying a finished, verified
resolution that no other worktree could see. This hook exists to make that
state loud at the moment it becomes permanent.

The property is stated as an invariance rather than a list of cases, in the
shape ``test_log_guard.py`` established for the sibling hook:

* **The verdict depends only on the working tree.** Unlike ``log-guard.py``,
  whose two shipped defects both came from asking a *shared* artifact a
  session-scoped question, this hook reads no transcript, no shared log, and
  no peer state. So the parametrised suites below vary the transcript and the
  shared log across their full realistic range and assert the verdict does not
  move -- the failure mode that cost that hook two review rounds cannot recur
  here, and now cannot be *introduced* here either.
* **Scope is the queue directory.** A dirty tree elsewhere is another rule's
  business (``change-guard.py``); this hook must stay silent for it.

Mutation evidence for every assertion is recorded in the commit message; each
listed mutation was run against production code and observed red, then
reverted and observed green.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = (
    Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "queue-commit-guard.py"
)

ITEM = ".kiro/queue/2026-07-27-a-surfaced-thing.md"
CLOSED_ITEM = ".kiro/queue/closed/2026-07-27-a-surfaced-thing.md"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with a committed, clean `.kiro/queue/` holding one open item."""
    root = tmp_path / "repo"
    (root / ".kiro" / "queue" / "closed").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / ".kiro" / "queue" / "README.md").write_text("the contract\n")
    (root / ITEM).write_text("---\nstatus: open\n---\n\n## What\nA thing.\n")
    (root / "src.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return root


def _run(repo: Path, *, session_id: str = "", transcript: Path | None = None) -> str:
    """Run the hook against a synthetic Stop payload; return raw stdout.

    ``TMPDIR`` is redirected into this test's own ``tmp_path`` so the hook's
    per-session sentinel cannot outlive the test. Without this the sentinel
    assertions below are order- and machine-dependent: they pass on a clean
    checkout and then fail on every subsequent run, because a fixed
    ``session_id`` writes a real file into the developer's shared temp dir.
    """
    payload = {
        "hook_event_name": "Stop",
        "session_id": session_id,  # "" means no sentinel: judged fresh
        "cwd": str(repo),
        "transcript_path": str(transcript) if transcript else "",
    }
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
        env={**os.environ, "TMPDIR": str(repo.parent)},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _nudged(repo: Path, **kwargs: object) -> bool:
    return bool(_run(repo, **kwargs).strip())  # type: ignore[arg-type]


# --- the three ways a close fails to land -------------------------------------


def _close_in_working_tree(repo: Path) -> None:
    """Perform a real close, exactly as the kiro-queue skill does -- and stop
    short of committing it, which is the whole defect."""
    (repo / ITEM).write_text(
        "---\nstatus: done\n---\n\n## What\nA thing.\n\n## Resolution\nDone.\n"
    )
    _git(repo, "mv", ITEM, CLOSED_ITEM)


UNCOMMITTED_STATES = pytest.mark.parametrize(
    "dirty",
    [
        pytest.param(_close_in_working_tree, id="a-full-close-never-committed"),
        pytest.param(
            lambda r: (r / ITEM).write_text("---\nstatus: done\n---\n"),
            id="unstaged-frontmatter-flip",
        ),
        pytest.param(
            lambda r: (r / ".kiro/queue/2026-07-27-brand-new.md").write_text("new\n"),
            id="untracked-new-item",
        ),
        pytest.param(
            lambda r: (
                (r / ITEM).write_text("---\nstatus: done\n---\n"),
                _git(r, "add", ITEM),
            ),
            id="staged-but-uncommitted",
        ),
    ],
)


@UNCOMMITTED_STATES
def test_any_uncommitted_queue_edit_is_reported(repo: Path, dirty) -> None:
    """The four shapes a queue edit can take without reaching a commit.

    `staged-but-uncommitted` and `a-full-close-never-committed` are the two
    that actually occurred: `git mv` stages the rename, so the tree looks
    "handled" to anything that only checks for *unstaged* changes.
    """
    dirty(repo)
    assert _nudged(repo) is True


@UNCOMMITTED_STATES
def test_committing_the_same_edit_silences_it(repo: Path, dirty) -> None:
    """The paired half: each state above, committed, must go quiet.

    Without this, a hook that simply always nudged would pass the suite above.
    """
    dirty(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "chore(queue): close the item")
    assert _nudged(repo) is False


def test_a_clean_queue_is_silent(repo: Path) -> None:
    assert _nudged(repo) is False


# --- scope: the queue directory, not the tree ---------------------------------


DIRT_OUTSIDE_THE_QUEUE = pytest.mark.parametrize(
    "elsewhere",
    [
        pytest.param(lambda r: (r / "src.py").write_text("x = 2\n"), id="tracked-src"),
        pytest.param(
            lambda r: (r / "new.py").write_text("y = 1\n"), id="untracked-src"
        ),
        pytest.param(
            lambda r: (r / ".kiro" / "steering.md").write_text("a rule\n"),
            id="untracked-kiro-sibling",
        ),
    ],
)


@DIRT_OUTSIDE_THE_QUEUE
def test_dirt_outside_the_queue_is_another_rules_business(
    repo: Path, elsewhere
) -> None:
    """`change-guard.py` owns the worktree ritual for `src/`; this hook must
    not duplicate it. `untracked-kiro-sibling` pins the pathspec specifically:
    a prefix match on `.kiro` rather than `.kiro/queue/` would catch it."""
    elsewhere(repo)
    assert _nudged(repo) is False


@DIRT_OUTSIDE_THE_QUEUE
def test_queue_dirt_is_still_reported_alongside_unrelated_dirt(
    repo: Path, elsewhere
) -> None:
    """The scoping must narrow *which files are reported*, not switch the hook
    off whenever the rest of the tree is also dirty -- the realistic case, since
    a session that closes an item is usually doing something else too."""
    elsewhere(repo)
    _close_in_working_tree(repo)
    payload = json.loads(_run(repo))
    assert CLOSED_ITEM in payload["systemMessage"]
    assert "src.py" not in payload["systemMessage"]
    assert "steering.md" not in payload["systemMessage"]


# --- invariance: no session-scoped or peer-scoped input can move the verdict ---

PEER_LINE_NAMING_BRANCHES = (
    "2026-07-27T06:06:53Z\tqueue-sweep-0727\tNOTE\tten implementer branches "
    "are committed and UNMERGED: chore/queue-commit-guard, impl/plugin-api-surface"
)

TRANSCRIPTS = pytest.mark.parametrize(
    "commands",
    [
        pytest.param([], id="empty-transcript"),
        pytest.param(
            [f"git add {ITEM} && git commit -m 'chore(queue): close it'"],
            id="session-says-it-committed",
        ),
        pytest.param(
            [f"cat {ITEM}", 'printf "..." >> "$(git rev-parse --git-dir)/agent-log"'],
            id="session-read-the-item-and-logged",
        ),
    ],
)


@TRANSCRIPTS
def test_the_verdict_ignores_the_transcript(
    repo: Path, tmp_path: Path, commands
) -> None:
    """`log-guard.py` shipped two defects by deriving a session-scoped fact
    from a shared artifact. This hook derives *nothing* from any artifact but
    the working tree, so a transcript that claims the commit happened must not
    silence a tree that says otherwise -- `session-says-it-committed` is a
    session asserting exactly the thing `git status` disproves.
    """
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": c},
                            }
                        ]
                    },
                }
            )
            for c in commands
        )
        + "\n"
    )
    _close_in_working_tree(repo)
    assert _nudged(repo, transcript=transcript) is True


def test_a_peer_log_line_cannot_move_the_verdict(repo: Path) -> None:
    """The sibling hook's round-2 defect, made unreachable by construction."""
    (repo / ".git" / "agent-log").write_text(PEER_LINE_NAMING_BRANCHES + "\n")
    _close_in_working_tree(repo)
    assert _nudged(repo) is True


# --- the advisory contract ----------------------------------------------------


def test_it_never_blocks_and_reaches_the_model(repo: Path) -> None:
    """Advisory, per this hook's contract: a session may legitimately be
    mid-edit. `additionalContext` is the field that reaches the *model* on
    Stop -- the only actor that can still run `git commit` -- so a nudge that
    set only `systemMessage` would be seen by nobody who can act on it."""
    _close_in_working_tree(repo)
    payload = json.loads(_run(repo))
    assert "decision" not in payload
    assert payload["continue"] is True
    assert payload["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert (
        payload["hookSpecificOutput"]["additionalContext"] == payload["systemMessage"]
    )


def test_it_fires_once_per_session(repo: Path) -> None:
    """A per-session sentinel, as both sibling hooks use. Without it a session
    that chooses not to commit is nudged on every subsequent Stop."""
    _close_in_working_tree(repo)
    assert _nudged(repo, session_id="s-1") is True
    assert _nudged(repo, session_id="s-1") is False
    assert _nudged(repo, session_id="s-2") is True


def test_it_never_chains_off_another_stop_hook(repo: Path) -> None:
    _close_in_working_tree(repo)
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": True}),
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert proc.stdout.strip() == ""


# --- degrade quietly ----------------------------------------------------------


def test_outside_a_git_repo_it_is_silent(tmp_path: Path) -> None:
    loose = tmp_path / "loose"
    (loose / ".kiro" / "queue").mkdir(parents=True)
    (loose / ".kiro" / "queue" / "x.md").write_text("not in git\n")
    assert _nudged(loose) is False


def test_a_repo_without_a_queue_is_silent(tmp_path: Path) -> None:
    """fitdocs' own hooks are copied into sibling repos; a repo that does not
    run this workflow must never be nudged about a directory it lacks."""
    root = tmp_path / "other"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "f.txt").write_text("dirty\n")
    assert _nudged(root) is False


def test_malformed_payload_is_silent(repo: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
