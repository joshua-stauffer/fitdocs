"""`HistoryReplacement`: the gated driver that forges the fresh root, clones
it, verifies it, carries the shared agent log across and swaps `.git`
(task 7.6, design.md `#### HistoryReplacement`, Req 5.3, 6.2, 6.5, 7.7, 11.3).

**One driver, one ordering, and the ordering is the design** (design.md
`#### HistoryReplacement`, "Ordering, and the order is the design", steps
1-8): `gate` first, refusing on any non-zero result (Req 6.5); the certified
tip's commit and tree ids written into the agent log; the commit identity
asserted non-personal in both git config scopes before the forge (Req 5.3);
the fixed root commit message checked through the forbidden-string matcher
before the forge (Req 11.3); the root forged parentless from the certified
tree under a temporary branch; the reachable-only clone of that single
branch, checked fresh, then its branch renamed to `main`; the pre-swap
`ReplacementVerification` rows; the carry-over checklist copied then
asserted; the swap as two whole-directory moves; the archive readability
check.

**What is routed through the injected `runner`, and why only that much.**
`CommandRunner` here is `Callable[[Sequence[str]], str]` -- it returns the
command's stdout, unlike `rewrite.CommandRunner` (`-> None`), because this
driver has a genuine data dependency the retired rewrite driver never had:
the forged commit's id, read back from `commit-tree`'s own stdout, is what
`update-ref` and the clone's `--branch` argument need next. Four commands go
through `runner`, in order: `commit-tree`, `update-ref`, `clone --no-local`,
`branch -m`. The first three are the **structural, history-shaping**
operations that create or fetch an object -- the forge and the fetch half of
the clone -- and this module's own test suite never lets `runner` execute
them for real, matching `scripts/purge/rewrite.py`'s posture ("The driver
never runs a mutating git command itself"): `runner` is a pure recorder for
those three in every test. The fourth, the branch rename, creates no object
and only moves a ref inside the disposable scratch clone `runner` never
really created; a test may let its `runner` execute *that one* for real (see
the row checks below, which read the clone's ref state directly), the same
"real, but disposable-scratch-scoped" posture `rewrite.assert_fresh_clone`
already has in this spec's test suite. Task 7.7's rehearsal is where a real
runner is handed the whole sequence.

**Everything after the clone is a real, reused precondition check or a real,
already-tested helper**, run the same way `rewrite.run_rewrite` already runs
`assert_fresh_clone` for real against a real fixture repository, never
through `runner`: `rewrite.assert_fresh_clone` (reused unchanged) on the
freshly cloned scratch directory; six `ReplacementVerification` rows,
reused unchanged from `scripts/purge/verify.py`, against that same scratch
clone. Five of the six are what design.md `#### HistoryReplacement`'s
"Contracts" table marks `F` (pre-swap): exactly one commit reachable, root
tree identical to the certified tip tree, refs clean, metadata clean, no
token in any commit message. The sixth -- no token in any path or blob of
the single commit -- the table marks `W` only (post-swap); running it here,
pre-swap, against the scratch clone as well is a **declared strengthening**,
not a table match: catching a path/blob token before the swap discards a
merely-verified scratch clone (Req 7.7's "correct and re-verify" applies
cleanly there) rather than after `repo_root` itself has already been
swapped. `adopt.build_checklist` / `adopt.assert_carry_over`
(reused unchanged) for the carry-over, copied by this driver with
`shutil.copy2` before the assertion runs, matching `adopt.py`'s own "copy,
assert, then vacate" contract; `adopt.move_clone` (reused unchanged, see
`MOVE_CLONE_DECISION` in this task's status report) for both swap moves; and
a direct, read-only `git cat-file -e` / `git fsck --connectivity-only` pair
against the archive once it exists. None of these touch `repo_root`'s own
reachable history -- the scratch clone, the checklist copy and the two
archived/swapped directories are the only things this driver ever writes to
directly, and the swap is the only step that touches `repo_root` itself.

**A pre-swap failure discards the scratch clone and returns to the forge
with nothing touched** (Req 7.7): `PreSwapVerificationError` is raised after
`shutil.rmtree`-ing the scratch clone. The forge itself does write a new
commit object and a temporary ref into `repo_root`'s own object database
(design.md `#### HistoryReplacement` step 3) -- measured, not assumed
(design.md `#### HistoryReplacement`, step 3's "which is harmless: that
database is about to be archived whole"); that write is harmless because
`repo_root`'s `.git` is archived whole at the swap, not incrementally
undone. What is NOT written before the pre-swap rows have all passed is
`old_git_dir`'s own content and the working directory -- neither is opened
for write before that point, so neither needs anything undone on a pre-swap
failure. Nothing in this module deletes the old `.git`, prunes an object
database in place, or moves the working directory -- Decision 7's fixed
constraints (design.md `#### HistoryReplacement`).
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import typer
from tests._forbidden_strings import ForbiddenStrings, matches

from scripts.purge import adopt
from scripts.purge.preflight import Quiescence, gate
from scripts.purge.rewrite import assert_fresh_clone
from scripts.purge.verify import (
    RowResult,
    check_exactly_one_commit_reachable,
    check_metadata_clean,
    check_no_token_in_any_commit_message,
    check_no_token_in_path_or_blob,
    check_refs_clean,
    check_tree_identity,
)

CommandRunner = Callable[[Sequence[str]], str]
"""Injected by the caller: given a command as a tuple of arguments, run it
and return its stdout. Four commands are handed to it (see module
docstring); this module's own tests never let it execute the three that
create or fetch an object, matching the posture `scripts/purge/rewrite.py`
states for its own `CommandRunner` -- "the driver never runs a mutating git
command itself"."""

_SESSION_ID = "purge-replace"

ROOT_COMMIT_MESSAGE = (
    "Initial commit of the published history\n"
    "\n"
    "The prior history was replaced, not rewritten: this commit has no "
    "parent. See docs/reference/history-rewrites.md for a record of what "
    "was removed and why.\n"
)
"""The fixed root commit message (design.md `#### HistoryReplacement`,
"The root commit message is fixed by this design"). Carries no identifying
token, no personal address, no removed value and no pre-replacement commit
identifier -- asserted by running it through `ForbiddenStrings.matches`
before the forge (Req 11.3), not assumed."""


class RootMessageError(RuntimeError):
    """Raised when `ROOT_COMMIT_MESSAGE` itself matches the forbidden-string
    source -- refusing to forge rather than forging a root commit whose own
    message carries a token."""


class PreSwapVerificationError(RuntimeError):
    """Raised when any pre-swap `ReplacementVerification` row fails, naming
    every failing row. The scratch clone is discarded (`shutil.rmtree`)
    before this is raised -- Req 7.7's "correct and re-verify" applied at
    the swap boundary, before any push exists to be tempted by."""


class ArchiveNotReadableError(RuntimeError):
    """Raised when the archived old `.git` does not resolve the certified
    tip's pre-replacement commit id, or `git fsck --connectivity-only`
    reports a problem against it -- the swap's last step, run before any
    remote action."""


def _append_certified_tip_line(log: Path, commit_id: str, tree_id: str) -> None:
    """Append one line recording the certified tip's commit and tree ids to
    the shared agent log -- design.md step 1: "captured before anything else
    happens". Distinct from `preflight.gate`'s own `PROCEEDING` line (this
    module does not touch that private helper), written immediately after
    `gate` has already logged `PROCEEDING` and before any other action."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"{timestamp}\t{_SESSION_ID}\tCERTIFIED_TIP\t"
        f"commit={commit_id} tree={tree_id}\n"
    )
    with log.open("a") as handle:
        handle.write(line)


# --- the forge (design.md step 3) -------------------------------------------


def build_commit_tree_command(
    repo: Path, tree_id: str, message: str
) -> tuple[str, ...]:
    """`git commit-tree <tree> -m <message>`, run rooted at `repo` -- no
    `-p`, so the forged commit is parentless by construction."""
    return ("git", "-C", str(repo), "commit-tree", tree_id, "-m", message)


def build_update_ref_command(
    repo: Path, temp_branch: str, commit_id: str
) -> tuple[str, ...]:
    """`git update-ref refs/heads/<temp_branch> <commit_id>` -- the
    temporary ref design.md step 3 forges the root under, never
    `refs/heads/main` directly: `repo_root`'s own `main` stays untouched
    until the swap replaces the whole `.git`."""
    ref = f"refs/heads/{temp_branch}"
    return ("git", "-C", str(repo), "update-ref", ref, commit_id)


# --- the clone (design.md step 4) -------------------------------------------


def build_clone_command(source: Path, temp_branch: str, dest: Path) -> tuple[str, ...]:
    """`git clone --no-local --single-branch --branch <temp_branch>` of
    `source` into `dest` -- the reachable-only copy design.md step 4 calls
    "true by construction": a `--no-local` clone of a single branch carries
    exactly the forged root, its tree and its blobs."""
    return (
        "git",
        "clone",
        "--no-local",
        "--single-branch",
        "--branch",
        temp_branch,
        "--",
        str(source),
        str(dest),
    )


def build_rename_branch_command(
    repo: Path, temp_branch: str, target_branch: str = "main"
) -> tuple[str, ...]:
    """`git branch -m <temp_branch> <target_branch>`, run rooted at `repo`.
    Run only AFTER `assert_fresh_clone` has checked the clone still named
    `temp_branch` -- renaming first would break that check's "every local
    head equal to its origin counterpart" property, since the remote never
    had a branch named `main`."""
    return ("git", "-C", str(repo), "branch", "-m", temp_branch, target_branch)


def _remove_origin_remote(repo: Path) -> None:
    """`git remote remove origin` in the scratch clone, run directly (never
    through `runner`, for the same "disposable scratch, no object created"
    reason the branch rename is): a `--no-local` clone always keeps
    `origin` and its remote-tracking refs -- measured, not assumed, on a
    real `git clone --no-local --single-branch --branch <name>` here, which
    leaves `refs/remotes/origin/<name>` behind -- so `check_refs_clean`'s
    "exactly `refs/heads/main` and nothing else" would fail on every real
    clone by construction unless this runs before those checks. Run after
    `assert_fresh_clone`, which needs `origin` present to check its own
    "every local head equal to its origin counterpart" property."""
    subprocess.run(
        ["git", "-C", str(repo), "remote", "remove", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )


# --- pre-swap verification (design.md step 5) -------------------------------


def run_pre_swap_rows(
    repo: Path,
    certified_tree_id: str,
    forbidden: ForbiddenStrings,
    allowed: frozenset[str],
) -> tuple[RowResult, ...]:
    """Five of these six rows are what design.md's table marks `F`
    (pre-swap): exactly one commit reachable, root tree identical to the
    certified tip tree, refs clean, metadata clean, no token in any commit
    message. The sixth, no token in any path or blob, the table marks `W`
    only (post-swap) -- running it here too, pre-swap, is a declared
    strengthening (see the module docstring's "Everything after the clone"
    paragraph), not a table match. Every function is reused unchanged from
    `scripts/purge/verify.py` -- "Reuse, not rebuild"."""
    return (
        check_exactly_one_commit_reachable(repo),
        check_tree_identity(repo, certified_tree_id),
        check_refs_clean(repo),
        check_metadata_clean(repo, allowed),
        check_no_token_in_any_commit_message(repo, forbidden),
        check_no_token_in_path_or_blob(repo, forbidden),
    )


# --- the archive readability check (design.md step 8) -----------------------


def _assert_archive_readable(archive_dir: Path, old_tip_commit: str) -> None:
    """ "The archive is verified readable before any remote action" -- the
    old `main` tip resolves in it and `git fsck --connectivity-only` runs
    clean. Read-only queries against `archive_dir`, run directly (never
    through `runner`): once the swap has moved the old `.git` there, reading
    it back is exactly the kind of precondition check
    `rewrite.assert_fresh_clone` already runs for real in this spec's
    own test suite, not a mutation this module needs to keep out of a test.

    `cat-file -e` rather than `rev-parse --verify`, and the difference is
    load-bearing at the one point it is checked. `git rev-parse --verify
    --quiet` validates only the SHAPE of a 40-hex string: measured on git
    2.54.0, it exits 0 and echoes the id back for an object that does not
    exist, while `git cat-file -e` on the same id exits 1. This check is the
    last gate before the archive becomes the only copy of the old history
    ON THIS MACHINE -- a shape check would report a corrupted or truncated
    archive readable. (Amendment 3, 2026-08-22: the retained `fitdocs_oss`
    remote also keeps the old history, so the archive is no longer the only
    copy ANYWHERE. That widens the margin; it does not relax this check,
    which is the last local gate and runs before any remote is consulted.)"""
    resolved = subprocess.run(
        [
            "git",
            "-C",
            str(archive_dir),
            "cat-file",
            "-e",
            old_tip_commit,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if resolved.returncode != 0:
        raise ArchiveNotReadableError(
            f"archive at {archive_dir} does not hold the old tip "
            f"{old_tip_commit!r} (git cat-file -e exit {resolved.returncode})"
        )
    fsck = subprocess.run(
        ["git", "-C", str(archive_dir), "fsck", "--connectivity-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    if fsck.returncode != 0 or fsck.stdout.strip() or fsck.stderr.strip():
        raise ArchiveNotReadableError(
            f"archive at {archive_dir} failed git fsck --connectivity-only: "
            f"exit={fsck.returncode} stdout={fsck.stdout!r} stderr={fsck.stderr!r}"
        )


# --- orchestration -----------------------------------------------------------


def run_replace(
    *,
    quiescence: Quiescence,
    abandoned_branches: tuple[str, ...],
    abandonment_recorded: bool,
    log: Path,
    repo_root: Path,
    certified_tip_commit: str,
    certified_tip_tree: str,
    non_personal_address: str,
    non_personal_name: str,
    forbidden: ForbiddenStrings,
    temp_branch: str,
    scratch_clone_dir: Path,
    old_git_dir: Path,
    archive_dir: Path,
    runner: CommandRunner,
    env: Mapping[str, str] | None = None,
) -> int:
    """Call the gate first (Req 6.5); refuse on a non-zero result, emitting
    NO command through `runner` and returning the gate's own exit code. On a
    zero result -- already logged as `PROCEEDING` by `gate`, in `log`,
    before returning -- run design.md's ordering steps 1 and 3-8 in order
    (step 2, operator acceptance of the certified tip, is a precondition of
    calling this function at all, not something it performs).

    Every parameter is keyword-only: `repo_root`, `scratch_clone_dir`,
    `old_git_dir` and `archive_dir` are four `Path` arguments a caller could
    otherwise transpose silently.

    `env` is forwarded, unchanged, to `adopt.assert_commit_identity` --
    `None` means that function's own default (`os.environ`). A test
    overrides `GIT_CONFIG_GLOBAL` there, the same reason
    `tests/purge/test_adopt.py` never touches the real machine-wide global
    git config for `assert_commit_identity`'s own tests.

    Returns `gate`'s exit code: 0 on proceed, non-zero on halt.
    """
    exit_code = gate(quiescence, abandoned_branches, abandonment_recorded, log)
    if exit_code != 0:
        return exit_code

    _append_certified_tip_line(log, certified_tip_commit, certified_tip_tree)

    adopt.assert_commit_identity(repo_root, non_personal_address, env=env)

    hits = matches(ROOT_COMMIT_MESSAGE, forbidden)
    if hits:
        raise RootMessageError(
            f"the fixed root commit message matches the forbidden-string source: {hits}"
        )

    new_commit_id = runner(
        build_commit_tree_command(repo_root, certified_tip_tree, ROOT_COMMIT_MESSAGE)
    ).strip()
    runner(build_update_ref_command(repo_root, temp_branch, new_commit_id))

    runner(build_clone_command(repo_root, temp_branch, scratch_clone_dir))
    assert_fresh_clone(scratch_clone_dir)
    runner(build_rename_branch_command(scratch_clone_dir, temp_branch))
    _remove_origin_remote(scratch_clone_dir)

    rows = run_pre_swap_rows(
        scratch_clone_dir,
        certified_tip_tree,
        forbidden,
        frozenset({non_personal_address, non_personal_name}),
    )
    failed = tuple(row for row in rows if not row.passed)
    if failed:
        shutil.rmtree(scratch_clone_dir, ignore_errors=True)
        raise PreSwapVerificationError(
            "pre-swap verification failed; scratch clone discarded, nothing "
            "else touched: " + "; ".join(f"{row.row}: {row.detail}" for row in failed)
        )

    items = adopt.build_checklist(
        clone_git_dir=scratch_clone_dir / ".git", old_git_dir=old_git_dir
    )
    for item in items:
        if item.source is not None:
            item.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source, item.path)
    adopt.assert_carry_over(items, doomed_root=old_git_dir)

    adopt.move_clone(old_git_dir, archive_dir)
    adopt.move_clone(scratch_clone_dir / ".git", repo_root / ".git")

    _assert_archive_readable(archive_dir, certified_tip_commit)

    return 0


def run() -> None:
    """`purge replace` -- not yet wired to a real certified tip, real
    scratch/archive paths or a real command runner. `run_replace` above
    (task 7.6, design.md `#### HistoryReplacement`) implements the full
    ordering and is tested; wiring the CLI to those real, out-of-repository
    inputs is Major 8's responsibility, run from `main` in the primary
    worktree once the quiescence gate has already proceeded -- the same
    posture `scripts/purge/preflight.py::run`, `scripts/purge/rewrite.py::run`
    and `scripts/purge/verify.py::verify_local` state for their own CLI
    wiring.
    """
    typer.echo(
        "purge replace: HistoryReplacement CLI wiring not yet implemented "
        "(run_replace is implemented and tested, task 7.6; Major 8 supplies "
        "the real certified tip, scratch/archive paths and command runner "
        "at the call site)",
        err=True,
    )
    raise typer.Exit(code=1)
