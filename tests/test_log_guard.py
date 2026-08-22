"""The one property `log-guard.py` exists to have: it judges *this* session.

The hook nudges a session that ended with commits on a branch but never
appended to the shared agent log. Two shipped versions got the "never
appended" half wrong in the same way, and both shipped because nothing here
pinned it:

* **Round 1** scoped both signals to a *time window* over the whole repo, so
  ``log_touched_since`` returned true if **any** peer logged inside the
  window. Replayed against 33 real transcripts it was silent on 33 of 33.
* **Round 2** rekeyed to *branch identity* and substring-matched
  ``{branch, branch-with-dashes, slug}`` against every line of the log. One
  real peer line -- ``.git/agent-log`` line 180, a ``queue-sweep-0727`` NOTE
  enumerating ten unmerged implementer branches -- names all ten sessions'
  branches and would suppress every one of their nudges.

Both rounds are the same defect: the hook asked the *shared* log a question
only the *session* can answer. The shared log carries no field that
identifies a session --

* column 4 is free prose, and peers routinely name each other's branches
  (line 180);
* column 2 is a real tab-delimited field but a *work label*, chosen freely by
  each session's prose and many-to-many with sessions in this repo's own
  history: label ``impl-training-load`` was written by two distinct Claude
  Code sessions, and one session wrote under both ``impl-athlete-benchmarks``
  and ``impl-load-channels``. So even exact column-2 matching lets a peer
  suppress this session's nudge.

The only artifact that is this session's by construction is its transcript,
which the Stop payload hands the hook as ``transcript_path``. Its tool calls
cannot contain a peer's work. ``queue-guard.wrote_to_queue`` already answers
the sibling Development Rule's identical question that way.

So the property below is stated as an invariance, not as a list of cases:
**the verdict must not change when the shared log changes underneath it.**
Any signal read out of the shared log violates this; only a transcript-derived
signal satisfies it. Round 1 and round 2 each fail it on their own real-world
evidence, included here verbatim as parameters.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "log-guard.py"

# Verbatim from `.git/agent-log` line 180 -- written by the coordinating
# session `queue-sweep-0727`, naming ten *other* sessions' branches.
PEER_LINE_NAMING_TEN_BRANCHES = (
    "2026-07-27T06:06:53Z\tqueue-sweep-0727\tNOTE\tten implementer branches "
    "are committed and UNMERGED, awaiting adversarial review: "
    "chore/sha-map-durable, impl/plugin-api-surface, impl/load-second-reader, "
    "chore/mutation-evidence-reverify, chore/agent-log-enforcement, "
    "chore/withdrawal-guards-widen, chore/spec-status-args, "
    "chore/training-load-spec-repin, impl/devfield-declared-scale, "
    "chore/protocol-purity-audit"
)

# A peer working the same spec -- explicitly contemplated by concurrency.md,
# and real: two sessions logged under `impl-athlete-benchmarks`. This is the
# line that defeats exact column-2 matching, not just substring matching.
PEER_LINE_SAME_WORK_LABEL = (
    "2026-07-27T06:00:00Z\tchore-agent-log-enforcement\tNOTE\t"
    "a peer session using the same work label"
)

# Round 1's failure mode: a peer logged, recently, about anything at all.
PEER_LINE_RECENT_UNRELATED = (
    "2026-07-27T06:10:00Z\timpl-load-channels\tWARN\t"
    "load/settings.py reshaped on my branch, consume it"
)

BRANCH = "chore/agent-log-enforcement"


def _load_hook():
    spec = importlib.util.spec_from_file_location("log_guard", _HOOK)
    module = importlib.util.module_from_spec(spec)
    sys.modules["log_guard"] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo on a non-`main` branch holding one commit `main` lacks."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "seed").write_text("seed\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    _git(root, "checkout", "-qb", BRANCH)
    (root / "work").write_text("work\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "work on the branch")
    return root


def _write_transcript(path: Path, *commands: str) -> None:
    """A transcript whose assistant turns issue `commands` as Bash tool calls."""
    entries = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ]
            },
        }
        for command in commands
    ]
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")


APPEND_BY_THIS_SESSION = (
    'LOG="$(git rev-parse --git-common-dir)/agent-log" && '
    "printf '%s\\t%s\\t%s\\t%s\\n' \"$(date -u +%FT%TZ)\" "
    '"chore-agent-log-enforcement" CLAIM "the log hook" >> "$LOG"'
)

READ_ONLY_BY_THIS_SESSION = 'cat "$(git rev-parse --git-common-dir)/agent-log"'


def _nudged(repo: Path, transcript: Path, log_lines: list[str]) -> bool:
    """Run the hook against a synthetic Stop payload; True if it nudged."""
    log = repo / ".git" / "agent-log"
    log.write_text("".join(line + "\n" for line in log_lines))
    payload = {
        "hook_event_name": "Stop",
        "session_id": "",  # no sentinel: every call is judged fresh
        "cwd": str(repo),
        "transcript_path": str(transcript),
    }
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert proc.returncode == 0, proc.stderr
    return bool(proc.stdout.strip())


# Every log state below differs only in lines *this session did not write*.
PEER_ONLY_LOG_STATES = pytest.mark.parametrize(
    "peer_lines",
    [
        pytest.param([], id="empty-log"),
        pytest.param([PEER_LINE_NAMING_TEN_BRANCHES], id="round2-peer-names-my-branch"),
        pytest.param([PEER_LINE_SAME_WORK_LABEL], id="peer-uses-my-work-label"),
        pytest.param([PEER_LINE_RECENT_UNRELATED], id="round1-peer-logged-recently"),
        pytest.param(
            [
                PEER_LINE_RECENT_UNRELATED,
                PEER_LINE_SAME_WORK_LABEL,
                PEER_LINE_NAMING_TEN_BRANCHES,
            ],
            id="all-three-peer-lines",
        ),
    ],
)


@PEER_ONLY_LOG_STATES
def test_no_peer_line_can_suppress_this_sessions_nudge(
    repo: Path, tmp_path: Path, peer_lines: list[str]
) -> None:
    """This is the assertion whose absence shipped the defect twice.

    The session has commits on its branch and never appended to the log, so it
    must be nudged -- no matter what any *peer* wrote. Round 2 fails
    `round2-peer-names-my-branch` and `peer-uses-my-work-label`; any
    log-derived signal fails at least one of these.
    """
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, "git commit -qm work", READ_ONLY_BY_THIS_SESSION)
    assert _nudged(repo, transcript, peer_lines) is True


@PEER_ONLY_LOG_STATES
def test_a_session_that_logged_is_never_nudged_whatever_peers_wrote(
    repo: Path, tmp_path: Path, peer_lines: list[str]
) -> None:
    """The other half of the invariance: no peer line can *cause* a nudge."""
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, APPEND_BY_THIS_SESSION)
    assert _nudged(repo, transcript, peer_lines) is False


def test_the_verdict_is_invariant_under_every_peer_only_log_state(
    repo: Path, tmp_path: Path
) -> None:
    """Stated once, as the general property both rounds violated.

    A session's verdict is a function of what *it* did. Mutating the shared
    log with lines it did not write must not move the verdict in either
    direction -- which is exactly what "immune to a peer's unrelated line"
    means, and what the round-2 commit message claimed without pinning.
    """
    silent = tmp_path / "silent.jsonl"
    _write_transcript(silent, READ_ONLY_BY_THIS_SESSION)
    logged = tmp_path / "logged.jsonl"
    _write_transcript(logged, APPEND_BY_THIS_SESSION)

    states = [
        [],
        [PEER_LINE_NAMING_TEN_BRANCHES],
        [PEER_LINE_SAME_WORK_LABEL],
        [PEER_LINE_RECENT_UNRELATED],
        [PEER_LINE_NAMING_TEN_BRANCHES, PEER_LINE_SAME_WORK_LABEL],
    ]
    assert {_nudged(repo, silent, state) for state in states} == {True}
    assert {_nudged(repo, logged, state) for state in states} == {False}


def test_reading_the_log_is_not_writing_to_it(repo: Path, tmp_path: Path) -> None:
    """`cat "$LOG"` mentions the log but coordinates nothing.

    Guards the transcript signal against the mirror of the substring bug:
    matching the *word* `agent-log` anywhere in this session's own transcript
    would let a session that only ever read the log escape the nudge. Real
    transcripts in this repo touch the log without appending (one has 11 such
    calls and 3 appends), so this is not hypothetical.
    """
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, READ_ONLY_BY_THIS_SESSION)
    assert _nudged(repo, transcript, []) is True


def test_no_commits_means_no_nudge(repo: Path, tmp_path: Path) -> None:
    """The hook judges silence *about work*, not silence."""
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-qb", "chore/nothing-yet")
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, READ_ONLY_BY_THIS_SESSION)
    assert _nudged(repo, transcript, [PEER_LINE_NAMING_TEN_BRANCHES]) is False


def test_the_hook_never_blocks(repo: Path, tmp_path: Path) -> None:
    """concurrency.md: the log is not a lock. Advisory means advisory."""
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, READ_ONLY_BY_THIS_SESSION)
    log = repo / ".git" / "agent-log"
    log.write_text("")
    payload = {
        "hook_event_name": "Stop",
        "session_id": "",
        "cwd": str(repo),
        "transcript_path": str(transcript),
    }
    proc = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
    )
    emitted = json.loads(proc.stdout)
    assert emitted["continue"] is True
    assert "decision" not in emitted


def test_the_hook_reads_no_claim(repo: Path, tmp_path: Path) -> None:
    """Structural: the hook must not parse peers' CLAIM lines at all.

    concurrency.md, "What the log is not". A hook that gated on a peer's claim
    would convert an advisory artifact into the lock steering forbids.
    """
    module = _load_hook()
    source = _HOOK.read_text()
    body = source.split('"""', 2)[-1]  # exclude the module docstring
    assert "CLAIM" not in body.replace("CLAIM / TOUCHING", "")
    assert not hasattr(module, "log_mentions"), (
        "log_mentions reads the shared log for a session-identity signal that "
        "is not in the shared log -- see this module's docstring."
    )
