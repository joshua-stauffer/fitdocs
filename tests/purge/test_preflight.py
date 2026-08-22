"""`scripts/purge/preflight.py`: the quiescence gate (Req 6.1-6.6).

Every fixture here builds a synthetic repository under `tmp_path` with
`git init`. Nothing in this module runs a mutating git command against the
real worktree this test suite executes in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.purge.preflight import Quiescence, gate, inspect


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "alpha.txt").write_text("first commit content\n")
    _git(root, "add", "alpha.txt")
    _git(root, "commit", "-q", "-m", "initial")
    return root


def _git_dir(repo: Path) -> Path:
    out = _git(repo, "rev-parse", "--git-dir").stdout.strip()
    path = Path(out)
    return path if path.is_absolute() else repo / path


def _ref_and_reflog_snapshot(repo: Path) -> dict[str, bytes]:
    """Every byte of ref and reflog state, primary **and per-worktree**,
    keyed by path relative to the git dir: `HEAD`, `refs/`, `logs/` and
    `packed-refs` at the git dir, plus each linked worktree's own private
    `HEAD` and `logs/HEAD` under `worktrees/<name>/` -- a linked worktree's
    checked-out commit lives in `worktrees/<name>/HEAD`, not in the shared
    `refs/` or `logs/` this snapshot already covers, and
    `git checkout --detach` in a linked worktree changes that file and the
    worktree's own `logs/HEAD`, both of which this snapshot captures.

    Deliberately excludes `worktrees/<name>/index`: `git status` refreshes
    its on-disk stat cache as an ordinary side effect (confirmed by running
    it and diffing the file), and that is not a ref or a reflog -- including
    it would make a read-only `inspect` run look dirty.
    """
    git_dir = _git_dir(repo)
    snapshot: dict[str, bytes] = {}
    for name in ("HEAD", "refs", "logs", "packed-refs"):
        target = git_dir / name
        if target.is_file():
            snapshot[name] = target.read_bytes()
        elif target.is_dir():
            for f in sorted(target.rglob("*")):
                if f.is_file():
                    snapshot[str(f.relative_to(git_dir))] = f.read_bytes()
    worktrees_dir = git_dir / "worktrees"
    if worktrees_dir.is_dir():
        for entry in sorted(worktrees_dir.iterdir()):
            head = entry / "HEAD"
            if head.is_file():
                snapshot[str(head.relative_to(git_dir))] = head.read_bytes()
            logs = entry / "logs"
            if logs.is_dir():
                for f in sorted(logs.rglob("*")):
                    if f.is_file():
                        snapshot[str(f.relative_to(git_dir))] = f.read_bytes()
    return snapshot


def test_ref_and_reflog_snapshot_detects_a_linked_worktree_head_change(
    tmp_path: Path,
) -> None:
    """Positive control on the snapshot helper itself: a linked worktree's
    private `HEAD` moving (`git checkout --detach`) must show up as a
    difference. A snapshot that stayed equal across this change would pin
    nothing in `test_inspect_is_read_only_ref_and_reflog_state_byte_identical`
    -- it is exactly the gap a prior review round found by demonstration."""
    repo = _repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", str(linked), "-b", "peer-branch")

    before = _ref_and_reflog_snapshot(repo)
    _git(linked, "checkout", "--detach", "-q", "HEAD")
    after = _ref_and_reflog_snapshot(repo)

    assert after != before


# ---------------------------------------------------------------------------
# inspect() -- read-only inspection
# ---------------------------------------------------------------------------


def test_inspect_reports_quiet_for_a_repository_with_only_main(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    q = inspect(repo)

    assert q.extra_branches == ()
    assert q.extra_worktrees == ()
    assert q.dirty_trees == ()
    assert q.quiet is True


def test_inspect_reports_every_branch_other_than_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "branch", "feature/one")
    _git(repo, "branch", "feature/two")

    q = inspect(repo)

    # Pairwise-distinct branch names, and both non-main branches present --
    # a fixture with only one extra branch would not defeat an
    # implementation that reports just the first extra ref it finds.
    assert q.extra_branches == ("feature/one", "feature/two")
    assert q.quiet is False


def test_inspect_reports_every_linked_worktree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", str(linked), "-b", "peer-branch")

    q = inspect(repo)

    assert len(q.extra_worktrees) == 1
    assert Path(q.extra_worktrees[0]).resolve() == linked.resolve()
    assert q.quiet is False


def test_inspect_reports_dirty_tracked_path_with_its_porcelain_status(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "alpha.txt").write_text("modified content, not committed\n")

    q = inspect(repo)

    assert len(q.dirty_trees) == 1
    tree, status = q.dirty_trees[0]
    assert Path(tree).resolve() == repo.resolve()
    assert "alpha.txt" in status
    assert q.quiet is False


def test_inspect_reports_staged_tracked_path_too(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("a second tracked file\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "add beta")
    (repo / "beta.txt").write_text("staged edit\n")
    _git(repo, "add", "beta.txt")

    q = inspect(repo)

    assert len(q.dirty_trees) == 1
    assert "beta.txt" in q.dirty_trees[0][1]
    assert q.quiet is False


def test_inspect_ignores_untracked_files(tmp_path: Path) -> None:
    """A fixture that genuinely violates the property: an untracked file is
    present, and the repository must still read as quiet -- Req 6.1/6.2
    scope dirtiness to *tracked* changes only."""
    repo = _repo(tmp_path)
    (repo / "scratch.txt").write_text("never added to git\n")

    q = inspect(repo)

    assert q.dirty_trees == ()
    assert q.quiet is True


def test_inspect_reports_two_dirty_tracked_paths_in_the_same_tree(
    tmp_path: Path,
) -> None:
    """A fixture that defeats a first-only implementation of `_dirty_paths`:
    two distinct tracked files dirtied in the same worktree must both
    appear, not just the first one `git status --porcelain` lists."""
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("a second tracked file\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "add beta")
    (repo / "alpha.txt").write_text("dirty alpha\n")
    (repo / "beta.txt").write_text("dirty beta\n")

    q = inspect(repo)

    assert len(q.dirty_trees) == 2
    statuses = {status for _tree, status in q.dirty_trees}
    assert any("alpha.txt" in status for status in statuses)
    assert any("beta.txt" in status for status in statuses)


def test_inspect_reports_dirty_paths_in_a_linked_worktree_not_only_primary(
    tmp_path: Path,
) -> None:
    """Req 6.1 scopes dirtiness to "any tree", not only the tree `inspect`
    was called against. A fixture that dirties only the primary tree cannot
    defeat an implementation that scans `worktree_paths[:1]` -- it would
    read exactly the same either way. Dirty the linked tree instead."""
    repo = _repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", str(linked), "-b", "peer-branch")
    (linked / "alpha.txt").write_text("dirty in the linked worktree\n")

    q = inspect(repo)

    assert len(q.dirty_trees) == 1
    tree, status = q.dirty_trees[0]
    assert Path(tree).resolve() == linked.resolve()
    assert "alpha.txt" in status


def test_inspect_and_gate_halt_report_dirty_paths_from_two_different_trees(
    tmp_path: Path,
) -> None:
    """The combined fixture: one dirty tracked path in the primary tree and
    one in a linked worktree. Both must survive into `inspect`'s
    `dirty_trees` and both must survive into `gate`'s halt line -- a fixture
    with only one dirty path (in either tree) cannot defeat a `[:1]`
    truncation planted at `_dirty_paths`, `inspect`'s accumulation, or
    `_describe_halt`'s formatting, because each of those would coincidentally
    already return everything there is with only one entry present.

    `--detach` (not `-b <name>`) adds the linked worktree without also
    creating a branch: `extra_worktrees` legitimately names the linked path
    too, so an assertion that only checks the path appears *somewhere* in
    the halt line is confounded by that clause and cannot tell a truncated
    `dirty=` segment from an intact one. Count occurrences of the dirty
    *status* text instead -- it is only ever emitted from `dirty_trees`.
    """
    repo = _repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "--detach", str(linked))
    (repo / "alpha.txt").write_text("dirty in primary\n")
    (linked / "alpha.txt").write_text("dirty in linked\n")

    q = inspect(repo)

    assert len(q.dirty_trees) == 2
    trees = {Path(tree).resolve() for tree, _status in q.dirty_trees}
    assert repo.resolve() in trees
    assert linked.resolve() in trees

    log = tmp_path / "agent-log"
    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    line = _log_lines(log)[0]
    assert line.count(" M alpha.txt") == 2


def test_inspect_reports_surviving_original_refs_but_stays_quiet(
    tmp_path: Path,
) -> None:
    """A surviving backup ref is reported for information, and never makes
    an otherwise-quiet repository non-quiet (Req 6.6)."""
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/original/refs/heads/old-branch", head)

    q = inspect(repo)

    assert q.surviving_original_refs == ("refs/original/refs/heads/old-branch",)
    assert q.extra_branches == ()
    assert q.extra_worktrees == ()
    assert q.dirty_trees == ()
    assert q.quiet is True


def test_inspect_is_read_only_ref_and_reflog_state_byte_identical(
    tmp_path: Path,
) -> None:
    """`inspect` must open no ref for write and expire nothing (Req 6.1,
    6.3). Build a repository with content in every observable dimension
    first, so the snapshot is non-trivial -- an empty repository's ref
    state matching itself would prove nothing (self-referential compare)."""
    repo = _repo(tmp_path)
    _git(repo, "branch", "feature/one")
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", str(linked), "-b", "peer-branch")
    (repo / "alpha.txt").write_text("dirty before inspect\n")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/original/refs/heads/old-branch", head)

    before = _ref_and_reflog_snapshot(repo)
    assert before, "the snapshot is looking at the wrong git dir"

    inspect(repo)

    after = _ref_and_reflog_snapshot(repo)
    assert after == before


# ---------------------------------------------------------------------------
# gate() -- proceed/halt decision, agent-log write
# ---------------------------------------------------------------------------


def _log_lines(log: Path) -> list[str]:
    return log.read_text().splitlines()


def test_gate_log_line_has_four_tab_separated_fields_with_a_nonblank_session_id(
    tmp_path: Path,
) -> None:
    """`.kiro/steering/concurrency.md`'s shared agent-log format is four
    tab-separated fields: UTC timestamp, session id, event, body. Split on
    tab and check each field individually -- an `"\\tHALT\\t"` substring
    check elsewhere in this file cannot tell a real session id from a blank
    one, because both produce that same substring."""
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    fields = _log_lines(log)[0].split("\t")
    assert len(fields) == 4
    timestamp, session_id, event, body = fields
    assert timestamp  # non-empty ISO-ish UTC timestamp
    assert session_id.strip() != ""
    assert event == "PROCEEDING"
    assert body != ""


def test_gate_appends_to_a_nonempty_log_without_truncating_it_on_proceed(
    tmp_path: Path,
) -> None:
    """Req 6.4/6.5 and `concurrency.md`'s append-only contract: `gate` must
    never destroy a prior line already in the shared agent log. A fixture
    that starts from an empty log cannot tell an append from a truncating
    overwrite -- both leave exactly one line behind."""
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"
    log.write_text("2020-01-01T00:00:00Z\tsome-peer\tCLAIM\tprior work\n")

    gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    lines = _log_lines(log)
    assert len(lines) == 2
    assert lines[0] == "2020-01-01T00:00:00Z\tsome-peer\tCLAIM\tprior work"
    assert "\tPROCEEDING\t" in lines[1]


def test_gate_appends_to_a_nonempty_log_without_truncating_it_on_halt(
    tmp_path: Path,
) -> None:
    """Same contract, exercised on the halt path -- `gate` must not swap
    which branch is taken and inadvertently only guard one of them."""
    q = Quiescence(
        extra_branches=("feature/stray",),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"
    log.write_text("2020-01-01T00:00:00Z\tsome-peer\tCLAIM\tprior work\n")

    gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    lines = _log_lines(log)
    assert len(lines) == 2
    assert lines[0] == "2020-01-01T00:00:00Z\tsome-peer\tCLAIM\tprior work"
    assert "\tHALT\t" in lines[1]


def test_gate_proceeds_on_a_quiet_repository_with_abandonment_recorded(
    tmp_path: Path,
) -> None:
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    assert result == 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tPROCEEDING\t" in lines[0]
    assert "impl/athlete-benchmarks" in lines[0]
    assert "impl/training-load" in lines[0]


def test_gate_halts_on_extra_branch_and_names_it(tmp_path: Path) -> None:
    q = Quiescence(
        extra_branches=("feature/stray",),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]
    assert "feature/stray" in lines[0]


def test_gate_halts_on_extra_worktree_and_names_its_path(tmp_path: Path) -> None:
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=("/some/peer/worktree",),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]
    assert "/some/peer/worktree" in lines[0]


def test_gate_halts_on_dirty_tree_and_names_the_path_and_status(
    tmp_path: Path,
) -> None:
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=((str(tmp_path / "repo"), " M alpha.txt"),),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]
    assert "alpha.txt" in lines[0]
    assert " M alpha.txt" in lines[0]


def test_gate_halts_without_recorded_abandonment_even_when_quiet(
    tmp_path: Path,
) -> None:
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=False,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]
    # Req 6.4: the halt and its cause, not "not quiet" alone -- this is one
    # of the two halts a peer most needs to act on.
    assert "abandonment" in lines[0]
    assert "abandonment_recorded is False" in lines[0]


def test_gate_halts_on_empty_abandoned_branches_even_with_no_backup_ref(
    tmp_path: Path,
) -> None:
    """The near-miss this task exists to prevent: a quiet repository with
    zero surviving backup refs (today's measured state of `refs/original/`)
    must not let an empty `abandoned_branches` tuple discharge Req 6.6's
    naming obligation by accident. `abandonment_recorded=True` alone is not
    enough -- the tuple must actually name a branch."""
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=(),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]
    # Req 6.4: the halt and its cause.
    assert "no abandoned branch named" in lines[0]


def test_gate_halts_on_a_blank_abandoned_branch_entry(tmp_path: Path) -> None:
    """`("",)` is exactly what `tuple(out.split("\\n"))` produces over empty
    command output -- the same derivation-from-empty accident Req 6.6 exists
    to forbid, now reaching `gate` through a non-empty-looking tuple. A
    blank entry must halt exactly like an empty tuple does, not proceed and
    name nothing."""
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("",),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]
    assert "no abandoned branch named" in lines[0]


def test_gate_halts_on_a_whitespace_only_abandoned_branch_entry_among_real_ones(
    tmp_path: Path,
) -> None:
    """A blank entry must halt even when it rides alongside real-looking
    names -- a check that only inspects `abandoned_branches[0]` or only
    checks non-emptiness of the tuple as a whole would miss this."""
    q = Quiescence(
        extra_branches=(),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "   ", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    assert result != 0
    lines = _log_lines(log)
    assert len(lines) == 1
    assert "\tHALT\t" in lines[0]


def test_gate_writes_exactly_one_line_regardless_of_which_condition_fires(
    tmp_path: Path,
) -> None:
    """Multiple halt conditions firing at once must still produce one line,
    not one per condition."""
    q = Quiescence(
        extra_branches=("feature/stray",),
        extra_worktrees=("/some/peer/worktree",),
        dirty_trees=((str(tmp_path / "repo"), " M alpha.txt"),),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    gate(
        q,
        abandoned_branches=(),
        abandonment_recorded=False,
        log=log,
    )

    assert len(_log_lines(log)) == 1


def test_gate_does_not_rewrite_any_ref_on_proceed(tmp_path: Path) -> None:
    """`gate` on its own must never touch a ref -- only append to the log.
    Build a repository with content in every observable dimension first
    (non-trivial ref/reflog state), call `gate` with a matching quiet
    `Quiescence`, and assert byte-identical ref/reflog state afterwards."""
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/original/refs/heads/old-branch", head)
    q = inspect(repo)
    assert q.quiet is True
    log = tmp_path / "agent-log"

    before = _ref_and_reflog_snapshot(repo)
    assert before, "the snapshot is looking at the wrong git dir"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    after = _ref_and_reflog_snapshot(repo)
    assert result == 0
    assert after == before


def test_gate_does_not_rewrite_any_ref_on_halt(tmp_path: Path) -> None:
    """Req 6.3: on a halt the repository is left in the state it held before
    the check, with no ref rewritten and no history expired. `gate` halting
    on an extra branch must leave ref/reflog state byte-identical, just as
    the proceed path does."""
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/original/refs/heads/old-branch", head)
    q = Quiescence(
        extra_branches=("feature/stray",),
        extra_worktrees=(),
        dirty_trees=(),
        surviving_original_refs=(),
    )
    log = tmp_path / "agent-log"

    before = _ref_and_reflog_snapshot(repo)
    assert before, "the snapshot is looking at the wrong git dir"

    result = gate(
        q,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
    )

    after = _ref_and_reflog_snapshot(repo)
    assert result != 0
    assert after == before
