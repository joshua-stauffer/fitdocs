"""Task 7.7: rehearse `HistoryReplacement`/`ReplacementVerification`
end to end against a real, throwaway git repository -- forward (forge,
clone, swap) and rollback (swap back from the archive) -- design.md
`#### HistoryReplacement` ordering steps 1 and 3-8, `#### ReplacementVerification`
(Req 7.1, 7.3, 10.3).

**Real git, real `run_replace`, a real command runner.** Every earlier
`run_replace` test in `tests/purge/test_rewrite_gate.py` either short-circuits
before any command reaches `runner` (the gating/identity tests) or hands
`runner` a recording stand-in that never actually executes `commit-tree`,
`update-ref` or `clone` -- the scratch clone those tests assert against is
pre-built by a SEPARATE helper (`_forge_and_clone_for_real`) that duplicates
the driver's own commands outside it. This module does the opposite: `_real_
runner` below executes every command `run_replace` hands it, for real,
against a scratch repository built under `tmp_path` -- the whole point of
task 7.7 being to exercise the SHIPPED path (`run_replace` itself) rather
than a second, hand-rolled implementation of its steps.

**The porcelain assertion is tracked-files-scoped, not "empty porcelain
status".** `.kiro/queue/2026-08-18-task-7-7-inherits-the-porcelain-trap.md`
records why: this rehearsal PLANTS the untracked root `agent-log` symlink in
the scratch working tree (Decision 7 point 4's own resolution observable),
so a bare, untracked-files-included `git status --porcelain` can never be
empty here by construction (it reports `?? agent-log`) regardless of whether
the swap is correct -- a guaranteed false red identical to the one task 7.4
removed for the real repository. The row this rehearsal reuses,
`scripts.purge.verify.check_working_tree_coincides`, already runs the
tracked-files-scoped form (`--untracked-files=no`); this test asserts the
UNSCOPED form is genuinely non-empty first, so the scoped row is proven to be
doing real work rather than passing vacuously because nothing was ever
untracked in the fixture.

**A genuine finding, since corrected upstream: the reflog is not literally
empty post-swap.** Measured here against a real `run_replace` swap (no
rehearsal-only shortcut, no extra git config): a real `git clone` followed by
the driver's own `git branch -m` rename leaves reflog entries behind
(`clone: from <source>`, `Branch: renamed ...`) -- measured, three lines in
`logs/HEAD` and two in `logs/refs/heads/main`, the rename writing to HEAD's
log twice -- and neither `run_replace` nor any function it calls clears
them. Every entry resolves to the SAME
commit -- the forged root -- so Req 7.3's actual text ("reflogs ... shall
reference no pre-replacement commit") holds, and task 7.7's own wording ("a
reflog referencing only the root") holds too. This finding is what the task
7.7 remediation's own declared correction to `scripts.purge.verify.check_
reflog_and_unreachable_gone` fixed: that row's reflog half no longer demands
`git reflog show --all` report literal emptiness, and now DOES pass this
driver-produced state -- a fact measured directly, not merely argued.
`_assert_reflog_references_only` below still implements the same Req 7.3
property independently (reading every file under `.git/logs/**` on disk,
never `git reflog show`'s output) -- equivalent on sha1, though the two id
scans have since diverged in width, the row's catching 64-hex ids and this
one not (queued follow-up) -- rather than being replaced by a call to
the now-corrected row function: switching this rehearsal onto that function
is a separate, out-of-scope change (queued follow-up), not something this
finding's correction forces on its own. `git reflog show --all` remains a
structurally unsound way to measure Req 7.3 either way: measured against
real git 2.54.0, it silently omits any reflog line whose named object is
absent from the object database and still exits 0 -- exactly the shape a
genuine pre-replacement id left behind post-swap would have, so a `reflog
show`-based check structurally cannot see the one failure mode Req 7.3
exists to catch, independent of whether the row currently in
`scripts/purge/verify.py` happens to pass this particular fixture. The row
function's `fsck` half (an entirely separate assertion, genuinely empty and
unaffected by any of this) is NOT called by this module -- the same command
shape (`git fsck --unreachable --dangling`) is re-issued directly below,
which is a duplicated command shape, not function reuse. See CONCERNS in
this task's status report and the queued follow-up this finding produced.

**Nothing here ever touches the real working repository.** Every path this
module builds lives under `tmp_path`; `_assert_untouched` below captures the
real repository's `HEAD` and, in the worktree this test runs in, the `.git`
**pointer file's** device/inode/mtime -- before the rehearsal runs, and
re-asserts them unchanged at the end. An assertion, not a claim, per this
task's hard safety constraint.

A worktree checkout's `.git` is a small regular file (`gitdir: <path>`), not
a directory, so this stat is insensitive to any activity inside the real
gitdir it points at -- writes inside the real gitdir change neither its
device/inode nor its `st_mtime_ns`. It is not inert: measured, a
byte-identical rewrite of the pointer file changes its `(st_dev, st_ino)`
while `git rev-parse HEAD` is unchanged, so for that one tamper class this
stat is the only arm that fires. It is not a general detector of `.git`
being replaced -- a pointer rewritten to name a different gitdir is caught
by the `HEAD` arm too, and a move-aside-and-back is caught by neither
(queued: `2026-08-18-assert-untouched-is-blind-to-move-aside-and-back.md`).
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts.purge import adopt
from scripts.purge.preflight import Quiescence
from scripts.purge.replace import run_replace
from scripts.purge.verify import (
    check_exactly_one_commit_reachable,
    check_tree_identity,
    check_working_tree_coincides,
)

from tests._forbidden_strings import ForbiddenStrings

_NON_PERSONAL_ADDRESS = "noreply@fitdocs.example"
_NON_PERSONAL_NAME = "fitdocs maintainer"
_TEMP_BRANCH = "purge-replacement-root"
_ABANDONED_BRANCHES = ("impl/athlete-benchmarks", "impl/training-load")

_FIRST_CONTENT = "first commit content\n"
_TIP_A_CONTENT = "certified tip content, file a\n"
_TIP_B_CONTENT = "certified tip content, file b\n"
_AGENT_LOG_CONTENT = (
    "2026-01-01T00:00:00Z\tsession-a\tCLAIM\tdemo coordination line\n"
    "2026-01-01T00:05:00Z\tsession-a\tMERGE\tdemo merge line\n"
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_stdout(repo: Path, *args: str) -> str:
    return _git(repo, *args).stdout


def _real_runner(command: Sequence[str]) -> str:
    """Execute every command `run_replace` hands it, for real -- the
    opposite of `test_rewrite_gate.py`'s `_ReplaceRunner`, which never
    really runs `commit-tree`, `update-ref` or `clone`. This is the whole
    point of task 7.7: rehearsing the SHIPPED path, not a stand-in for it."""
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout


def _identity_env(tmp_path: Path, address: str) -> dict[str, str]:
    """Same `GIT_CONFIG_GLOBAL`-override pattern as
    `tests/purge/test_rewrite_gate.py`/`tests/purge/test_adopt.py`: this
    rehearsal never touches the real machine-wide global git config."""
    global_cfg = tmp_path / "scratch-global-gitconfig"
    global_cfg.write_text(f"[user]\n\temail = {address}\n")
    return {"GIT_CONFIG_GLOBAL": str(global_cfg)}


def _clean_forbidden() -> ForbiddenStrings:
    return ForbiddenStrings(
        values=("zzz-not-present-anywhere-zzz",), source=Path("/dev/null")
    )


def _build_repo_root(tmp_path: Path) -> tuple[Path, str, str, str]:
    """A real repository standing in for the certified tip, with TWO real
    commits (not one) -- this is what makes "exactly one commit reachable"
    and the reflog/old-identifier assertions below pin something: if the
    fixture had only ever had one commit, "exactly one reachable" and "no
    pre-replacement commit in the reflog" would already have been true
    before `run_replace` ran anything. Returns `(repo_root, first_commit,
    tip_commit, tip_tree)`."""
    root = tmp_path / "repo-root"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", _NON_PERSONAL_ADDRESS)
    _git(root, "config", "user.name", _NON_PERSONAL_NAME)
    (root / "a.txt").write_text(_FIRST_CONTENT)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first commit")
    first_commit = _git_stdout(root, "rev-parse", "HEAD").strip()

    (root / "a.txt").write_text(_TIP_A_CONTENT)
    (root / "b.txt").write_text(_TIP_B_CONTENT)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "certified tip")
    tip_commit = _git_stdout(root, "rev-parse", "HEAD").strip()
    tip_tree = _git_stdout(root, "rev-parse", "HEAD^{tree}").strip()
    return root, first_commit, tip_commit, tip_tree


def _plant_root_symlink(root: Path) -> Path:
    """The untracked root `agent-log` symlink Decision 7 point 4 names --
    pointing at `.git/agent-log`, the same relative shape the real
    repository uses. Planted BEFORE the swap, over content that already
    exists at `.git/agent-log`, so it resolves immediately (not dangling)."""
    link = root / "agent-log"
    link.symlink_to(Path(".git") / "agent-log")
    return link


def _assert_untouched(real_repo: Path, before: tuple[str, os.stat_result]) -> None:
    """Assert nothing in this rehearsal touched `real_repo` -- an assertion,
    not a claim (this task's hard safety constraint). Compares `HEAD` and
    the device/inode/mtime of `real_repo / ".git"` against a snapshot taken
    before the rehearsal ran. In the worktree this test runs in, `.git` is a
    small regular file (`gitdir: <path>`), not a directory, so this stat is
    insensitive to any activity inside the real gitdir it points at --
    writes inside the real gitdir change neither its device/inode nor its
    `st_mtime_ns`. It is not inert: measured, a byte-identical rewrite of the
    pointer file changes its `(st_dev, st_ino)` while `git rev-parse HEAD` is
    unchanged, so for that one tamper class this stat is the only arm that
    fires. It is not a general detector of `.git` being replaced -- a pointer
    rewritten to name a different gitdir is caught by the `HEAD` arm too, and
    a move-aside-and-back is caught by neither (queued:
    `2026-08-18-assert-untouched-is-blind-to-move-aside-and-back.md`)."""
    head_before, stat_before = before
    head_after = _git_stdout(real_repo, "rev-parse", "HEAD").strip()
    stat_after = (real_repo / ".git").stat()
    assert head_after == head_before
    assert (stat_after.st_dev, stat_after.st_ino) == (
        stat_before.st_dev,
        stat_before.st_ino,
    )
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns


_REFLOG_HEX_ID_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
_REFLOG_NULL_ID = "0" * 40


def _assert_reflog_references_only(repo: Path, allowed_commit: str) -> None:
    """The literal property task 7.7 names -- "a reflog referencing only the
    root" -- and the literal property Req 7.3 states -- "reflogs ... shall
    reference no pre-replacement commit". Reads every file under
    `.git/logs/**` directly and asserts no 40-hex id other than
    `allowed_commit` (and the ref-creation placeholder, 40 zero characters)
    appears in them. This is deliberately NOT built on `git reflog show`:
    measured against real git 2.54.0, `reflog show --all` silently omits any
    line whose named object is absent from the object database and still
    exits 0, so it structurally cannot see a pre-replacement id left behind
    in a reflog file once the object it names is gone -- exactly the
    post-swap shape Req 7.3 forbids (see the module docstring's "genuine
    finding" note). This function is deliberately NOT
    `check_reflog_and_unreachable_gone` -- not because that row's contract
    fails this driver-produced state (it does not: the task 7.7
    remediation's declared correction to that row means it now passes this
    exact state, measured),
    but because reusing it here is a separate, out-of-scope change (module
    docstring, queued follow-up), so this function stays an independent
    implementation of the same Req 7.3 property."""
    logs_dir = repo / ".git" / "logs"
    scanned = 0
    found: set[str] = set()
    for log_file in logs_dir.rglob("*"):
        if log_file.is_file():
            scanned += 1
            found.update(_REFLOG_HEX_ID_RE.findall(log_file.read_text()))
    assert scanned, (
        f"no reflog files found under {logs_dir} -- the walk is looking at "
        f"the wrong directory"
    )
    found.discard(_REFLOG_NULL_ID)
    disallowed = found - {allowed_commit}
    assert not disallowed, (
        f"reflog files under {logs_dir} reference ids other than the "
        f"allowed root {allowed_commit!r}: {sorted(disallowed)}"
    )


def test_forge_clone_swap_and_rollback_against_a_real_throwaway_repository(
    tmp_path: Path,
) -> None:
    real_repo = Path(__file__).resolve().parents[2]
    real_before = (
        _git_stdout(real_repo, "rev-parse", "HEAD").strip(),
        (real_repo / ".git").stat(),
    )

    root, first_commit, tip_commit, tip_tree = _build_repo_root(tmp_path)
    old_git_dir = root / ".git"
    (old_git_dir / "agent-log").write_text(_AGENT_LOG_CONTENT)
    symlink = _plant_root_symlink(root)
    assert symlink.is_symlink()
    assert symlink.read_text() == _AGENT_LOG_CONTENT  # resolves pre-swap

    # --- preconditions: falsity in the starting state -----------------
    # Multiple commits reachable, so "exactly one commit reachable" pins
    # something rather than being true by accident.
    pre_count = _git_stdout(root, "rev-list", "--all", "--count").strip()
    assert pre_count == "2"
    # The reflog references BOTH commits pre-swap, so "references only the
    # root" post-swap is a genuine change, not a vacuous restatement.
    pre_reflog = _git_stdout(root, "reflog", "show", "--all")
    assert first_commit[:7] in pre_reflog
    assert tip_commit[:7] in pre_reflog
    # The bare, untracked-files-included porcelain is NON-empty because of
    # the planted symlink -- proving the tracked-scoped row (used below,
    # post-swap) is doing real work rather than passing vacuously.
    pre_bare_porcelain = _git_stdout(
        root, "status", "--porcelain", "--untracked-files=all"
    ).strip()
    assert pre_bare_porcelain == "?? agent-log"
    pre_scoped = check_working_tree_coincides(root)
    assert pre_scoped.passed, pre_scoped.detail

    scratch_clone_dir = tmp_path / "scratch-clone"
    archive_dir = tmp_path / "archive"
    driver_log = tmp_path / "driver-agent-log"
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)

    result = run_replace(
        quiescence=Quiescence(
            extra_branches=(),
            extra_worktrees=(),
            dirty_trees=(),
            surviving_original_refs=(),
        ),
        abandoned_branches=_ABANDONED_BRANCHES,
        abandonment_recorded=True,
        log=driver_log,
        repo_root=root,
        certified_tip_commit=tip_commit,
        certified_tip_tree=tip_tree,
        non_personal_address=_NON_PERSONAL_ADDRESS,
        non_personal_name=_NON_PERSONAL_NAME,
        forbidden=_clean_forbidden(),
        temp_branch=_TEMP_BRANCH,
        scratch_clone_dir=scratch_clone_dir,
        old_git_dir=old_git_dir,
        archive_dir=archive_dir,
        runner=_real_runner,
        env=env,
    )
    assert result == 0

    new_head = _git_stdout(root, "rev-parse", "HEAD").strip()
    assert new_head != tip_commit  # a fresh, parentless commit, not the old tip

    # --- post-swap assertions, every one the task names ------------------

    # Tree identity with the source tree (Req 10.3).
    tree_row = check_tree_identity(root, tip_tree)
    assert tree_row.passed, tree_row.detail

    # Exactly one reachable commit.
    count_row = check_exactly_one_commit_reachable(root)
    assert count_row.passed, count_row.detail

    # Porcelain, tracked-files-scoped (declared correction, task 7.4 --
    # NOT the bare form, which the planted symlink guarantees is non-empty).
    scoped_row = check_working_tree_coincides(root)
    assert scoped_row.passed, scoped_row.detail
    post_bare_porcelain = _git_stdout(
        root, "status", "--porcelain", "--untracked-files=all"
    ).strip()
    assert post_bare_porcelain == "?? agent-log"  # still non-empty; still by design

    # A reflog referencing only the root (Req 7.3) -- literal property, see
    # module docstring for why this is not `check_reflog_and_unreachable_gone`.
    _assert_reflog_references_only(root, new_head)

    # Remediation 1 discrimination -- the reviewer's own scenario. Plant a
    # genuine pre-replacement commit id (`tip_commit`, already unresolvable
    # in `root` post-swap -- the precondition is asserted below, not assumed)
    # directly into `.git/logs/refs/heads/main`. `git reflog show --all`
    # still does not mention it -- measured: `reflog show` silently drops
    # any line whose object is absent from the object database -- so a
    # `reflog show`-based check would pass this corrupted state, while
    # `_assert_reflog_references_only`, which reads the file directly, reds
    # on it. Then revert and confirm green again.
    main_log = root / ".git" / "logs" / "refs" / "heads" / "main"
    pre_mutation_log = main_log.read_text()
    stale_precheck = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", tip_commit],
        capture_output=True,
    )
    assert stale_precheck.returncode != 0  # tip_commit truly unresolvable here
    planted_line = (
        f"{'0' * 40} {tip_commit} {_NON_PERSONAL_NAME} <{_NON_PERSONAL_ADDRESS}> "
        "1700000000 +0000\tplanted pre-replacement entry\n"
    )
    main_log.write_text(planted_line + pre_mutation_log)
    reflog_show_after_plant = _git_stdout(root, "reflog", "show", "--all")
    assert tip_commit[:7] not in reflog_show_after_plant  # reflog show stays blind
    with pytest.raises(AssertionError):
        _assert_reflog_references_only(root, new_head)
    main_log.write_text(pre_mutation_log)  # revert
    _assert_reflog_references_only(root, new_head)  # green again, precondition undone

    # Remediation 3 discrimination -- pin the walk's BREADTH, not only that
    # it reaches SOME file. Plant a second, distinct foreign id
    # (`first_commit`, also unresolvable post-swap -- precondition asserted
    # below, not assumed) into `.git/logs/HEAD`, a subtree outside
    # `logs/refs/heads` entirely. A walk narrowed to `logs/refs/heads` (the
    # mutation that SURVIVED before this block existed -- measured green then,
    # and measured red at this block now: `logs_dir = repo / ".git" / "logs" /
    # "refs" / "heads"`) would still catch the `main_log` plant above, since
    # that lives inside `refs/heads` -- so this second plant is what makes
    # that narrowing observable.
    head_log = root / ".git" / "logs" / "HEAD"
    pre_mutation_head_log = head_log.read_text()
    stale_head_precheck = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", first_commit],
        capture_output=True,
    )
    assert stale_head_precheck.returncode != 0  # first_commit truly unresolvable here
    planted_head_line = (
        f"{'0' * 40} {first_commit} {_NON_PERSONAL_NAME} <{_NON_PERSONAL_ADDRESS}> "
        "1700000001 +0000\tplanted pre-replacement entry (HEAD)\n"
    )
    head_log.write_text(planted_head_line + pre_mutation_head_log)
    with pytest.raises(AssertionError):
        _assert_reflog_references_only(root, new_head)
    head_log.write_text(pre_mutation_head_log)  # revert
    _assert_reflog_references_only(root, new_head)  # green again, precondition undone

    # An empty unreachable-objects report (Req 7.3) -- re-issues the row
    # function's `fsck` command shape directly (the row function itself is
    # never called here, so this is a duplicated command, not reuse); this
    # half of the contract DOES hold.
    fsck_out = _git_stdout(root, "fsck", "--unreachable", "--dangling").strip()
    assert fsck_out == ""

    # The carried `.git`-resident agent-log fixture, present at its
    # destination with its content intact.
    carried_log = old_git_dir / "agent-log"
    assert carried_log.read_text() == _AGENT_LOG_CONTENT

    # The planted root symlink survives the swap and RESOLVES again --
    # Decision 7 point 4's own stated observable.
    assert symlink.is_symlink()
    assert symlink.read_text() == _AGENT_LOG_CONTENT

    # No pre-replacement identifier resolves any longer.
    stale = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", first_commit],
        capture_output=True,
    )
    assert stale.returncode != 0
    stale_tip = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", tip_commit],
        capture_output=True,
    )
    assert stale_tip.returncode != 0

    assert archive_dir.is_dir()
    archive_head = _git_stdout(archive_dir, "rev-parse", "refs/heads/main").strip()
    assert archive_head == tip_commit  # the archive holds the OLD certified tip

    # --- rollback: swap back from the archive -----------------------------
    post_swap_git_backup = tmp_path / "post-swap-git-backup"
    adopt.move_clone(root / ".git", post_swap_git_backup)
    adopt.move_clone(archive_dir, root / ".git")

    assert not archive_dir.exists()
    restored_head = _git_stdout(root, "rev-parse", "refs/heads/main").strip()
    assert restored_head == tip_commit
    # Restricted to `main` -- the archived `.git` also still carries the
    # temporary `refs/heads/<temp_branch>` ref the forge created (design.md
    # `#### HistoryReplacement` step 3: the forged commit lands in the OLD
    # object database, "harmless... that database is about to be archived
    # whole"), so `rev-list --all --count` here is 3, not 2.
    restored_count = _git_stdout(root, "rev-list", "main", "--count").strip()
    assert restored_count == "2"
    restored_first = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", first_commit],
        capture_output=True,
    )
    assert restored_first.returncode == 0
    # The working tree was never touched by either the swap or the
    # rollback -- Decision 7's fixed constraint 1 -- so the checked-out
    # file content is exactly what it was before any of this ran.
    assert (root / "a.txt").read_text() == _TIP_A_CONTENT
    assert (root / "b.txt").read_text() == _TIP_B_CONTENT
    restored_scoped = check_working_tree_coincides(root)
    assert restored_scoped.passed, restored_scoped.detail

    _assert_untouched(real_repo, real_before)


def test_a_pre_swap_failure_discards_the_scratch_clone_with_a_real_runner(
    tmp_path: Path,
) -> None:
    """The correct-and-re-verify half of Req 7.7, driven through the SAME
    real runner as the forward rehearsal above. A real runner FORGES a real
    commit from a real tree, so a nonexistent or mismatched tree id (the
    approach `test_rewrite_gate.py`'s equivalent test uses, where `runner`
    never really executes `commit-tree`) cannot be used here to force a
    pre-swap failure -- `git commit-tree` would simply fail outright on an
    unknown tree, or trivially succeed with a matching one, since the same
    `certified_tip_tree` value feeds both the forge and the tree-identity
    row. Instead this test forces the `no token in any path or blob` row to
    fail for real: `forbidden` matches the literal path `a.txt`, which the
    real forge-and-clone actually carries into the scratch clone's tree, so
    the failure is genuinely content-driven rather than a re-implementation
    of the driver's own check."""
    real_repo = Path(__file__).resolve().parents[2]
    real_before = (
        _git_stdout(real_repo, "rev-parse", "HEAD").strip(),
        (real_repo / ".git").stat(),
    )

    root, _first_commit, tip_commit, tip_tree = _build_repo_root(tmp_path)
    old_git_dir = root / ".git"
    (old_git_dir / "agent-log").write_text(_AGENT_LOG_CONTENT)
    old_main_before = _git_stdout(root, "rev-parse", "refs/heads/main").strip()

    scratch_clone_dir = tmp_path / "scratch-clone"
    archive_dir = tmp_path / "archive"
    driver_log = tmp_path / "driver-agent-log"
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    path_forbidden = ForbiddenStrings(values=("a.txt",), source=Path("/dev/null"))

    from scripts.purge.replace import PreSwapVerificationError

    with pytest.raises(PreSwapVerificationError, match="no token in any path or blob"):
        run_replace(
            quiescence=Quiescence(
                extra_branches=(),
                extra_worktrees=(),
                dirty_trees=(),
                surviving_original_refs=(),
            ),
            abandoned_branches=_ABANDONED_BRANCHES,
            abandonment_recorded=True,
            log=driver_log,
            repo_root=root,
            certified_tip_commit=tip_commit,
            certified_tip_tree=tip_tree,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=path_forbidden,
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=scratch_clone_dir,
            old_git_dir=old_git_dir,
            archive_dir=archive_dir,
            runner=_real_runner,
            env=env,
        )

    assert not scratch_clone_dir.exists()  # discarded
    assert not archive_dir.exists()  # the swap never ran
    assert old_git_dir.is_dir()  # untouched
    assert _git_stdout(root, "rev-parse", "refs/heads/main").strip() == old_main_before
    assert (old_git_dir / "agent-log").read_text() == _AGENT_LOG_CONTENT

    _assert_untouched(real_repo, real_before)
