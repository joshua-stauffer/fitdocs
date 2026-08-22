"""`scripts/purge/rewrite.py`'s builder/precondition functions, and
`scripts/purge/replace.py`'s `HistoryReplacement` driver (task 5.3's
`HistoryRewrite` retired at Amendment 1; task 7.6 re-targets this file's
gated-driver section to `HistoryReplacement`, design.md `####
HistoryReplacement`, Req 5.3, 6.2, 6.5, 7.7, 11.3). Filed at the path
design.md's Component -> file map names for this component:
`tests/purge/test_rewrite_gate.py` (`HistoryReplacement`'s row in the
Component -> file map names this file "re-targeted", not a new file).

**`build_path_directives`, `build_replacement_expressions`,
`build_filter_repo_command`, `build_remote_add_command` and `run_rewrite`
above the `HistoryReplacement` section below are untouched by task 7.6** --
`scripts/purge/rewrite.py` itself is out of this task's edit scope, and
those functions and their tests still exercise real, still-present code.
`assert_fresh_clone` and `_unreachable_object_ids` are the two pieces of
this retired module task 7.6 REUSES (see `scripts/purge/replace.py`'s own
module docstring): their tests below are the same tests, unmodified, that
now also cover the precondition `run_replace` calls on its own scratch
clone.

**Neither driver is ever executed for real here.** Every test in the
`HistoryRewrite` section exercises a pure builder function or calls
`run_rewrite` with an injected, list-recording `CommandRunner` -- no `git
filter-repo` process ever runs in this module. Every test in the
`HistoryReplacement` section below routes `commit-tree`, `update-ref` and
`clone --no-local` -- the three commands that create or fetch a git object
-- through an injected, recording-only `CommandRunner`; only the branch
rename, which creates no object, may be genuinely executed against the
disposable scratch clone that section's own fixtures build directly (see
`scripts/purge/replace.py`'s module docstring for why that one command is
different).

**Real clones, though.** `assert_fresh_clone` is a claim about a repository
on disk, so the repositories it is measured against here are built with
real `git clone` invocations in the shapes the claim discriminates between
-- `--no-local` (what the `HistoryReplacement` driver's own clone step
takes), `--local` (the same-filesystem default, which hardlinks the object
directory and carries every unreachable object with it) and `--shared`
(which borrows objects through an alternates file). Simulating them would
test the simulation. Every git command run here builds or inspects a
throwaway repository under `tmp_path`; **no maintenance command (`git gc`,
`git prune`, `git reflog expire`) is run anywhere in this module**, because
those are how a repository is made to look fresh and they reach into shared
object stores.
"""

from __future__ import annotations

import ast
import inspect
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts.purge import adopt
from scripts.purge import replace as replace_module
from scripts.purge.adopt import CarryOverError, IdentityError
from scripts.purge.preflight import Quiescence, gate
from scripts.purge.replace import (
    ROOT_COMMIT_MESSAGE,
    ArchiveNotReadableError,
    PreSwapVerificationError,
    RootMessageError,
    build_clone_command,
    build_commit_tree_command,
    build_rename_branch_command,
    build_update_ref_command,
    run_pre_swap_rows,
    run_replace,
)
from scripts.purge.rewrite import (
    FreshCloneError,
    _unreachable_object_ids,
    assert_fresh_clone,
    build_filter_repo_command,
    build_path_directives,
    build_remote_add_command,
    build_replacement_expressions,
    run_rewrite,
)

from tests._forbidden_strings import ForbiddenStrings, matches

# ---------------------------------------------------------------------------
# build_path_directives -- Hazard 1: directive order is load-bearing
# ---------------------------------------------------------------------------


def test_every_deletion_line_precedes_every_rename_line() -> None:
    """`removed_paths` and `rename_pairs` arrive as two separate parameters,
    so they cannot literally be "interleaved" by the caller.

    What this fixture defeats is a builder that merges both parameters into
    a single globally-sorted (e.g. lexicographic) list instead of rendering
    every deletion line, in order, before the whole rename block.

    `aaa/renamed.md==>aaa/new-name.md` sorts lexicographically BEFORE both
    `alpha/removed-two.md` and `zeta/removed-one.md`. A combined global sort
    would therefore emit the rename line first, ahead of both deletions --
    the wrong order this test exists to catch.
    """
    directives = build_path_directives(
        removed_paths=["zeta/removed-one.md", "alpha/removed-two.md"],
        rename_pairs=[("aaa/renamed.md", "aaa/new-name.md")],
    )
    lines = directives.splitlines()

    rename_index = lines.index("aaa/renamed.md==>aaa/new-name.md")
    deletion_indices = [
        lines.index(p) for p in ("zeta/removed-one.md", "alpha/removed-two.md")
    ]
    assert deletion_indices, "no deletion line found in the rendered directives"
    assert all(idx < rename_index for idx in deletion_indices)


def test_a_nested_rename_follows_its_parent_directory_rename() -> None:
    """Supplied in the WRONG order (child before parent) -- a builder that
    just echoed input order would keep the child first and this would fail."""
    directives = build_path_directives(
        removed_paths=[],
        rename_pairs=[
            (".kiro/queue/parent-dir/child.md", ".kiro/queue/parent-dir-new/child.md"),
            (".kiro/queue/parent-dir", ".kiro/queue/parent-dir-new"),
        ],
    )
    lines = directives.splitlines()

    parent_index = lines.index(".kiro/queue/parent-dir==>.kiro/queue/parent-dir-new")
    child_index = lines.index(
        ".kiro/queue/parent-dir/child.md==>.kiro/queue/parent-dir-new/child.md"
    )
    assert parent_index < child_index


def test_rename_line_uses_the_exact_arrow_syntax() -> None:
    directives = build_path_directives(
        removed_paths=[],
        rename_pairs=[("old/path.md", "new/path.md")],
    )
    assert directives == "old/path.md==>new/path.md\n"


def test_deletion_line_is_the_bare_path_with_no_arrow() -> None:
    directives = build_path_directives(
        removed_paths=["some/removed.md"], rename_pairs=[]
    )
    assert directives == "some/removed.md\n"
    assert "==>" not in directives


def test_empty_input_renders_empty_string() -> None:
    assert build_path_directives(removed_paths=[], rename_pairs=[]) == ""


# ---------------------------------------------------------------------------
# build_replacement_expressions -- Hazard 2: no word-boundary anchor
# ---------------------------------------------------------------------------


def test_no_expression_carries_a_word_boundary_anchor() -> None:
    expressions = build_replacement_expressions(
        [("alpha phrase", "neutral one"), ("beta", "neutral two")]
    )
    assert "\\b" not in expressions


def test_longest_phrase_is_ordered_before_its_component_word() -> None:
    """Supplied SHORT-first -- a builder that preserved input order would
    put the component word first and this would fail."""
    expressions = build_replacement_expressions(
        [("beta", "short-repl"), ("beta gamma extra", "long-repl")]
    )
    lines = expressions.splitlines()
    long_index = next(i for i, line in enumerate(lines) if "long-repl" in line)
    short_index = next(i for i, line in enumerate(lines) if "short-repl" in line)
    assert long_index < short_index


def test_expression_actually_matches_a_token_embedded_in_an_identifier() -> None:
    """The behavioural proof, not just a string check: a \\b-anchored
    pattern cannot match 'target' inside 'identifier_target_thing' because
    `_` is a word character. Render the expression, split off the `regex:`
    prefix and the `==>` replacement, and compile the remainder with Python's
    `re` module -- an approximation of what `git filter-repo` does (it
    compiles the same pattern text against `bytes`, not `str`, since its
    replace-text parser reads files opened in binary mode) close enough to
    prove the pattern text itself carries no anchor. Confirm it DOES match
    the embedded occurrence -- a fixture that only ever appeared at a word
    boundary could not tell an anchored implementation from an unanchored
    one."""
    expressions = build_replacement_expressions([("target", "neutral")])
    line = expressions.strip()
    assert line.startswith("regex:")
    pattern_and_repl = line[len("regex:") :]
    pattern, _, _replacement = pattern_and_repl.rpartition("==>")

    compiled = re.compile(pattern)
    assert compiled.search("identifier_target_thing") is not None


def test_expression_case_insensitive_flag_matches_a_differently_cased_token() -> None:
    expressions = build_replacement_expressions([("Target", "neutral")])
    line = expressions.strip()
    pattern, _, _replacement = line[len("regex:") :].rpartition("==>")

    compiled = re.compile(pattern)
    assert compiled.search("a TARGET here") is not None


def test_replacement_text_is_carried_through_after_the_arrow() -> None:
    expressions = build_replacement_expressions([("old-phrase", "the-replacement")])
    assert expressions.strip().endswith("==>the-replacement")


def test_regex_metacharacters_in_a_phrase_are_escaped_to_a_literal_match() -> None:
    """`re.escape` must actually run: a phrase containing a regex
    metacharacter (`.` matches any character) must be rendered so it matches
    ONLY the literal phrase, not every string that merely has the right
    length and structure. `"a.b"` unescaped would match `"axb"`; escaped, it
    must not."""
    expressions = build_replacement_expressions([("a.b", "neutral")])
    line = expressions.strip()
    pattern, _, _replacement = line[len("regex:") :].rpartition("==>")

    compiled = re.compile(pattern)
    assert compiled.search("axb") is None
    assert compiled.search("a.b") is not None


# ---------------------------------------------------------------------------
# build_filter_repo_command -- the single invocation, all four transforms
# ---------------------------------------------------------------------------


def test_filter_repo_command_is_exactly_the_expected_full_tuple() -> None:
    """Whole-tuple equality, not membership -- membership alone cannot
    distinguish a command missing `--invert-paths` (which would flip
    `--paths-from-file` from "remove these" to "keep only these", deleting
    the rest of the repository) or missing `-C <repo>` (which would run
    against the process's current working directory instead of the named
    clone) from the correct command, because neither omission changes which
    flags are merely PRESENT."""
    command = build_filter_repo_command(
        repo=Path("/scratch/clone"),
        paths_file=Path("/scratch/paths.txt"),
        replace_text_file=Path("/scratch/replace-text.txt"),
        replace_message_file=Path("/scratch/replace-message.txt"),
        mailmap_file=Path("/scratch/mailmap.txt"),
    )
    assert command == (
        "git",
        "-C",
        "/scratch/clone",
        "filter-repo",
        "--invert-paths",
        "--paths-from-file",
        "/scratch/paths.txt",
        "--replace-text",
        "/scratch/replace-text.txt",
        "--replace-message",
        "/scratch/replace-message.txt",
        "--mailmap",
        "/scratch/mailmap.txt",
        "--prune-empty",
        "never",
    )


def test_remote_add_command_names_origin_and_the_given_url() -> None:
    command = build_remote_add_command(Path("/scratch/clone"), "git@github.com:x/y.git")
    assert command == (
        "git",
        "-C",
        "/scratch/clone",
        "remote",
        "add",
        "origin",
        "git@github.com:x/y.git",
    )


# ---------------------------------------------------------------------------
# assert_fresh_clone -- the rewrite precondition, measured on real clones
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """A git command against a throwaway fixture repository. Identity is
    passed per-invocation so no test here depends on -- or touches -- the
    machine's own git configuration."""
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _source_repo(root: Path, *, amended: bool = True) -> Path:
    """A real source repository which, with `amended=True`, genuinely holds
    an **unreachable** commit: the last commit is amended, orphaning the
    pre-amend commit and its tree and blob.

    **What the amend is and is not needed for, measured rather than
    asserted.** It is what makes the *unreachable-object* row fire on a
    `--local` clone of this repository. It is **not** what makes a `--local`
    clone distinguishable at all: with `amended=False` a `--local` clone is
    still rejected (its hardlinked loose objects fail the fully-packed row)
    and a `--no-local` clone is still accepted. `amended=False` is used as
    exactly that control in the local-optimisation test.
    """
    source = root / "source"
    source.mkdir(parents=True)
    _git(source, "init", "-q", "-b", "main")
    (source / "a.txt").write_text("one\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "one")
    (source / "a.txt").write_text("one\ntwo\n")
    _git(source, "commit", "-qam", "two")
    if amended:
        (source / "a.txt").write_text("one\ntwo\nthree\n")
        _git(source, "commit", "-q", "--amend", "-a", "-m", "two amended")
    return source


def _unreachable_via_fsck(repo: Path) -> tuple[str, ...]:
    """`git fsck --unreachable`'s own answer to "what does this object
    database hold that nothing reaches" -- derived independently of
    `rewrite._unreachable_object_ids`' `cat-file`-minus-`rev-list` set
    difference, so a precondition asserted with it cannot silently agree
    with the code under test by sharing its implementation."""
    completed = subprocess.run(
        ["git", "-C", str(repo), "fsck", "--unreachable", "--no-progress"],
        check=False,
        capture_output=True,
        text=True,
    )
    return tuple(
        line
        for line in completed.stdout.splitlines()
        if line.startswith("unreachable ")
    )


def _clone(source: Path, destination: Path, *flags: str) -> Path:
    """`git clone` in the given shape. Read-only with respect to `source`;
    no maintenance command is ever run against either side."""
    subprocess.run(
        ["git", "clone", "-q", *flags, str(source), str(destination)],
        check=True,
        capture_output=True,
        text=True,
    )
    return destination


@pytest.fixture(scope="module")
def fresh_clone(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real `git clone --no-local` -- the clone task 7.2 takes and the one
    shape `assert_fresh_clone` must accept. Module-scoped because every user
    of it only ever *reads* it: `assert_fresh_clone` runs read-only queries,
    and `run_rewrite` hands its commands to a recording runner instead of
    executing them. Any test that modifies a clone builds its own."""
    root = tmp_path_factory.mktemp("fresh-clone")
    return _clone(_source_repo(root), root / "clone", "--no-local")


def test_assert_fresh_clone_accepts_a_real_no_local_clone(fresh_clone: Path) -> None:
    """Falsity check for every rejection below: the one shape task 7.2
    actually produces must pass, so a rejection elsewhere is about that
    fixture's defect and not about the assertion refusing everything."""
    assert_fresh_clone(fresh_clone)  # must not raise


def test_assert_fresh_clone_rejects_a_locally_optimised_clone(tmp_path: Path) -> None:
    """**The local optimisation, caught as a property rather than as a
    flag.** `git clone --local` hardlinks the source's whole object
    directory, so the clone carries the unreachable objects design.md's
    Ordering step 3 relies on the clone to drop. The precondition is
    measured with `git fsck`, not with the code under test.

    **The unreachable-object row is not the only thing rejecting this
    fixture, and saying otherwise would be false** -- a `--local` clone of a
    loose-object source is also not fully packed (measured: 9 loose objects
    here). What isolates the unreachable row is the `amended=False` control
    below: the same clone shape, from a source with no orphaned commit, is
    still rejected -- but *without* the unreachable phrase. So the phrase
    tracks the orphan, not the clone flag."""
    source = _source_repo(tmp_path)
    local_clone = _clone(source, tmp_path / "local-clone", "--local")
    no_local_clone = _clone(source, tmp_path / "no-local-clone", "--no-local")
    # The two clones really do differ in exactly this way.
    assert _unreachable_via_fsck(local_clone) != ()
    assert _unreachable_via_fsck(no_local_clone) == ()

    with pytest.raises(FreshCloneError) as excinfo:
        assert_fresh_clone(local_clone)

    assert "unreachable object" in str(excinfo.value)
    assert_fresh_clone(no_local_clone)  # the control, from the same source

    # The control that isolates the row: no orphaned commit in the source,
    # so no unreachable object in the --local clone -- still rejected, and
    # the unreachable phrase is absent.
    plain_source = _source_repo(tmp_path / "plain", amended=False)
    plain_local = _clone(plain_source, tmp_path / "plain-local", "--local")
    assert _unreachable_via_fsck(plain_local) == ()
    with pytest.raises(FreshCloneError) as plain_excinfo:
        assert_fresh_clone(plain_local)
    assert "unreachable object" not in str(plain_excinfo.value)


def test_unreachable_object_ids_does_not_report_a_reflog_pinned_object(
    tmp_path: Path,
) -> None:
    """The `--reflog` term on the reachable side, pinned directly rather
    than through `assert_fresh_clone`.

    A reflog entry is a real pin -- `git gc` honours it -- so an object it
    holds is not unreachable, and counting it as such would report a
    repository as unclean for something git considers rooted. That term
    cannot be falsified through `assert_fresh_clone`, because any repository
    where a reflog pins an otherwise-unreachable object necessarily has a
    reflog with more than one entry and is rejected on that row first. So it
    is measured here, against the helper, on a source repository whose
    amended-away commit is exactly such an object.

    Every precondition is asserted rather than assumed: the object is
    physically in the database, no ref reaches it, and the reflog does."""
    source = _source_repo(tmp_path)
    orphaned = _git(source, "rev-parse", "main@{1}").stdout.strip()

    on_disk = {
        line.split(" ", 1)[0]
        for line in _git(
            source, "cat-file", "--batch-all-objects", "--batch-check=%(objectname)"
        ).stdout.splitlines()
    }
    reachable_from_refs = {
        line.split(" ", 1)[0]
        for line in _git(source, "rev-list", "--objects", "--all").stdout.splitlines()
    }
    reflog_ids = _git(source, "reflog", "--format=%H").stdout.split()

    assert orphaned in on_disk  # physically present
    assert orphaned not in reachable_from_refs  # no ref reaches it
    assert orphaned in reflog_ids  # the reflog does

    assert orphaned not in _unreachable_object_ids(source)


def test_assert_fresh_clone_rejects_a_clone_borrowing_objects_via_alternates(
    tmp_path: Path,
) -> None:
    """`git clone --shared` writes an `objects/info/alternates` file, so the
    clone reads objects it does not hold. A rewrite there does not rewrite
    what is borrowed."""
    source = _source_repo(tmp_path)
    shared = _clone(source, tmp_path / "shared-clone", "--shared")
    assert (shared / ".git" / "objects" / "info" / "alternates").exists()

    with pytest.raises(FreshCloneError, match="alternates"):
        assert_fresh_clone(shared)


def test_assert_fresh_clone_rejects_a_clone_that_has_been_committed_in(
    tmp_path: Path,
) -> None:
    """A clone that was fresh when taken and has since been worked in: the
    reflog gains a second entry and the new objects are loose. Both are
    named, because either alone would be a weaker statement than "nothing
    has happened here since the clone"."""
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "clone", "--no-local")
    assert_fresh_clone(clone)  # fresh before the mutation, not assumed
    (clone / "b.txt").write_text("later work\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "work done in the clone")

    with pytest.raises(FreshCloneError) as excinfo:
        assert_fresh_clone(clone)

    message = str(excinfo.value)
    assert "more than one entry" in message
    assert "loose object" in message


def test_assert_fresh_clone_rejects_a_clone_with_a_second_remote(
    tmp_path: Path,
) -> None:
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "clone", "--no-local")
    _git(clone, "remote", "add", "upstream", str(source))

    with pytest.raises(FreshCloneError, match="exactly one remote"):
        assert_fresh_clone(clone)


def test_assert_fresh_clone_rejects_a_clone_with_a_stash(tmp_path: Path) -> None:
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "clone", "--no-local")
    (clone / "a.txt").write_text("uncommitted edit\n")
    _git(clone, "stash", "push", "-q", "-m", "fixture stash")

    with pytest.raises(FreshCloneError, match="stash"):
        assert_fresh_clone(clone)


def test_assert_fresh_clone_rejects_a_clone_with_a_second_worktree(
    tmp_path: Path,
) -> None:
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "clone", "--no-local")
    _git(clone, "worktree", "add", "-q", "-b", "side", str(tmp_path / "side-worktree"))

    with pytest.raises(FreshCloneError, match="exactly one worktree"):
        assert_fresh_clone(clone)


def test_assert_fresh_clone_rejects_a_head_with_no_origin_counterpart(
    tmp_path: Path,
) -> None:
    """A local branch created after the clone. Deliberately a case that
    leaves every OTHER property intact -- creating a branch writes a
    single-entry reflog and no new object -- so the head-vs-origin
    comparison is the only thing that can be doing the rejecting, which the
    negative assertions below pin."""
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "clone", "--no-local")
    _git(clone, "branch", "stray")

    with pytest.raises(FreshCloneError) as excinfo:
        assert_fresh_clone(clone)

    message = str(excinfo.value)
    assert "no refs/remotes/origin/stray counterpart" in message
    assert "more than one entry" not in message
    assert "loose object" not in message
    assert "unreachable object" not in message


def test_assert_fresh_clone_rejects_a_head_that_has_moved_from_its_origin_ref(
    tmp_path: Path,
) -> None:
    """The *inequality* half of property 8, which the no-counterpart test
    above does not reach: the branch still exists and still has an `origin`
    counterpart, but no longer points at it.

    The head is moved by **writing the loose ref file directly** rather than
    through `git update-ref`. Measured: `update-ref` appends to
    `logs/refs/heads/main` even under `-c core.logAllRefUpdates=false`,
    because git also logs whenever the reflog file already exists -- and a
    clone's does. That second reflog entry would have rejected the fixture
    on its own, making the negative assertions below false and the test
    unable to isolate property 8. Writing the ref file runs no git command,
    so no reflog entry and no object is written, and `git rev-parse` below
    confirms git reads the moved value. Without this fixture, replacing the
    inequality branch with `elif False:` leaves the whole suite green."""
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "clone", "--no-local")
    assert_fresh_clone(clone)  # equal before the move, not assumed
    previous = _git(clone, "rev-parse", "HEAD~1").stdout.strip()
    (clone / ".git" / "refs" / "heads" / "main").write_text(previous + "\n")
    assert _git(clone, "rev-parse", "refs/heads/main").stdout.strip() == previous
    assert (
        _git(clone, "rev-parse", "refs/remotes/origin/main").stdout.strip() != previous
    )

    with pytest.raises(FreshCloneError) as excinfo:
        assert_fresh_clone(clone)

    message = str(excinfo.value)
    assert "not equal to refs/remotes/origin/main" in message
    assert "more than one entry" not in message
    assert "loose object" not in message
    assert "unreachable object" not in message


def test_assert_fresh_clone_names_every_failing_property_not_only_the_first(
    tmp_path: Path,
) -> None:
    """A loop that reports the first failure would still pass a fixture
    with one defect. Three independently-introduced defects -- borrowed
    objects, a second remote and a stash -- plus a real count anchor.

    The count is **six**, not three, and the difference is the point of
    measuring it rather than assuming it: `git clone --shared` also leaves
    the clone unpacked *and* carries the source's unreachable objects (the
    amended commit `_source_repo` orphans), and `git stash push` writes a
    second `HEAD` reflog entry. An anchor asserting three would have been
    wrong, and so would one asserting five -- which is what this fixture
    produced before its source repository grew the amend. Asserting the
    measured six is what catches a report truncated after the first."""
    source = _source_repo(tmp_path)
    clone = _clone(source, tmp_path / "shared-clone", "--shared")
    _git(clone, "remote", "add", "upstream", str(source))
    (clone / "a.txt").write_text("uncommitted edit\n")
    _git(clone, "stash", "push", "-q", "-m", "fixture stash")

    with pytest.raises(FreshCloneError) as excinfo:
        assert_fresh_clone(clone)

    message = str(excinfo.value)
    assert "alternates" in message
    assert "exactly one remote" in message
    assert "stash" in message
    reported = message.split("optimisation; it ", 1)[1].split("; it ")
    assert len(reported) == 6, reported


def test_assert_fresh_clone_rejects_the_source_working_repository(
    tmp_path: Path,
) -> None:
    """design.md's Ordering step 3: "the working repository fails at least
    three of these, and `--force` is not the answer". Asserted rather than
    quoted."""
    source = _source_repo(tmp_path)

    with pytest.raises(FreshCloneError):
        assert_fresh_clone(source)


def test_assert_fresh_clone_rejects_a_path_that_is_not_a_repository(
    tmp_path: Path,
) -> None:
    """A directory that is not a repository at all must halt with that said,
    rather than quietly measuring every property against nothing -- an
    empty answer to each query would otherwise look like a clean result."""
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()

    with pytest.raises(FreshCloneError, match="not a git repository"):
        assert_fresh_clone(not_a_repo)


# ---------------------------------------------------------------------------
# run_rewrite -- the gated orchestration
# ---------------------------------------------------------------------------


class _RecordingRunner:
    """Records every emitted command, and -- for the ordering test -- the
    content of the shared agent log at the moment of the FIRST call."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.commands: list[tuple[str, ...]] = []
        self.log_at_first_call: str | None = None

    def __call__(self, command: object) -> None:
        if self.log_at_first_call is None:
            self.log_at_first_call = (
                self.log_path.read_text() if self.log_path.exists() else ""
            )
        self.commands.append(tuple(command))  # type: ignore[arg-type]


_QUIET = Quiescence(
    extra_branches=(),
    extra_worktrees=(),
    dirty_trees=(),
    surviving_original_refs=(),
)
_DIRTY = Quiescence(
    extra_branches=("feature/stray",),
    extra_worktrees=(),
    dirty_trees=(),
    surviving_original_refs=(),
)


def _spec_files(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Every spec file lives under `tmp_path/scratch`, deliberately a
    SIBLING of `tmp_path/repo` (the fixture `repo_root`) and of
    `tmp_path/clone` (the fixture `repo`) -- three distinct directories, so
    a test can tell "the clone" from "the repository root" from "scratch"
    apart by path alone."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    paths_file = scratch / "paths.txt"
    replace_text_file = scratch / "replace-text.txt"
    replace_message_file = scratch / "replace-message.txt"
    mailmap_file = scratch / "mailmap.txt"
    for f in (paths_file, replace_text_file, replace_message_file, mailmap_file):
        f.write_text("placeholder\n")
    return paths_file, replace_text_file, replace_message_file, mailmap_file


def test_run_rewrite_emits_exactly_the_filter_repo_invocation_then_the_remote_add(
    tmp_path: Path, fresh_clone: Path
) -> None:
    """`repo` (the clone `filter-repo` must operate on) and `repo_root` (the
    real working repository the mailmap must never live under) are distinct
    fixture directories. `commands[0]` is checked by WHOLE-TUPLE equality
    against the clone path -- a defeat for a swap that passed `repo_root`
    into `build_filter_repo_command` instead of `repo`, which a mere
    membership or substring check on `commands[0]` could not catch, since
    both `repo` and `repo_root` are non-empty path strings."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    clone = fresh_clone
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    run_rewrite(
        quiescence=_QUIET,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
        repo=clone,
        repo_root=repo_root,
        paths_file=paths_file,
        replace_text_file=replace_text_file,
        replace_message_file=replace_message_file,
        mailmap_file=mailmap_file,
        origin_url="git@github.com:x/y.git",
        runner=runner,
    )

    assert len(runner.commands) == 2
    assert runner.commands[0] == (
        "git",
        "-C",
        str(clone),
        "filter-repo",
        "--invert-paths",
        "--paths-from-file",
        str(paths_file),
        "--replace-text",
        str(replace_text_file),
        "--replace-message",
        str(replace_message_file),
        "--mailmap",
        str(mailmap_file),
        "--prune-empty",
        "never",
    )
    assert str(repo_root) not in runner.commands[0]
    assert runner.commands[1] == (
        "git",
        "-C",
        str(clone),
        "remote",
        "add",
        "origin",
        "git@github.com:x/y.git",
    )


# --- spec-file placement guard: all four arguments, not only the mailmap ---


@pytest.mark.parametrize(
    "field_name",
    ["paths_file", "replace_text_file", "replace_message_file", "mailmap_file"],
)
def test_run_rewrite_rejects_any_spec_file_living_inside_the_repository(
    tmp_path: Path, fresh_clone: Path, field_name: str
) -> None:
    """Parametrized over all four spec-file arguments -- a guard applied to
    only some of them (e.g. only `paths_file` and `mailmap_file`) would pass
    this test for the two it skips."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fields = dict(
        zip(
            ("paths_file", "replace_text_file", "replace_message_file", "mailmap_file"),
            _spec_files(tmp_path),
            strict=True,
        )
    )
    inside_repo = repo_root / "inside.txt"
    inside_repo.write_text("placeholder\n")
    fields[field_name] = inside_repo
    runner = _RecordingRunner(log)

    with pytest.raises(ValueError, match="inside the repository"):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=fresh_clone,
            repo_root=repo_root,
            paths_file=fields["paths_file"],
            replace_text_file=fields["replace_text_file"],
            replace_message_file=fields["replace_message_file"],
            mailmap_file=fields["mailmap_file"],
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_rejects_a_mailmap_at_the_conventional_repository_root_path(
    tmp_path: Path,
    fresh_clone: Path,
) -> None:
    """The specific hazard the task calls out: `<repo_root>/.mailmap` is an
    absolute path, so a check that only tested `is_absolute()` would pass it
    -- the fixture must actually be under `repo_root` while remaining
    absolute, to defeat that weaker implementation."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths_file, replace_text_file, replace_message_file, _ = _spec_files(tmp_path)
    conventional_mailmap = repo_root / ".mailmap"
    conventional_mailmap.write_text("placeholder\n")
    runner = _RecordingRunner(log)

    with pytest.raises(ValueError, match="inside the repository"):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=fresh_clone,
            repo_root=repo_root,
            paths_file=paths_file,
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=conventional_mailmap,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_rejects_the_repo_root_path_itself_as_a_spec_file(
    tmp_path: Path,
    fresh_clone: Path,
) -> None:
    """Exact-equality case: `spec_file == repo_root`, not merely a child of
    it. `Path.is_relative_to` is reflexive, so this case is covered by the
    `is_relative_to` check alone -- this test documents that case as a
    concrete, named scenario rather than pinning a separate code branch."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    with pytest.raises(ValueError, match="inside the repository"):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=fresh_clone,
            repo_root=repo_root,
            paths_file=repo_root,
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=mailmap_file,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_rejects_a_symlink_outside_the_repo_that_resolves_inside_it(
    tmp_path: Path,
    fresh_clone: Path,
) -> None:
    """`spec_file` itself is an absolute path OUTSIDE `repo_root` by every
    literal, unresolved measure -- but it is a symlink whose target is
    `<repo_root>/.mailmap`. Only a check that calls `.resolve()` on
    `spec_file` (following the symlink) catches this; a check comparing the
    literal, un-resolved `spec_file` path against `repo_root` would miss it
    entirely, because the symlink's own path never appears under
    `repo_root`."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    real_mailmap = repo_root / ".mailmap"
    real_mailmap.write_text("placeholder\n")
    outside_link = tmp_path / "external-link.mailmap"
    outside_link.symlink_to(real_mailmap)
    paths_file, replace_text_file, replace_message_file, _ = _spec_files(tmp_path)
    runner = _RecordingRunner(log)

    assert outside_link.is_absolute()
    assert not str(outside_link).startswith(str(repo_root))

    with pytest.raises(ValueError, match="inside the repository"):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=fresh_clone,
            repo_root=repo_root,
            paths_file=paths_file,
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=outside_link,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_rejects_a_spec_file_inside_a_symlinked_repo_root(
    tmp_path: Path,
    fresh_clone: Path,
) -> None:
    """`repo_root` itself is passed as an UNRESOLVED symlink to the real
    repository directory, and `spec_file` is given as the already-resolved
    real path under that real directory. The literal strings of `repo_root`
    (the symlink path) and `spec_file` (the real path) share no common
    prefix, so only a check that calls `.resolve()` on `repo_root` -- not
    only on `spec_file` -- catches this."""
    log = tmp_path / "agent-log"
    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    linked_repo_root = tmp_path / "linked-repo"
    linked_repo_root.symlink_to(real_repo)
    inside_real_repo = real_repo / "inside.txt"
    inside_real_repo.write_text("placeholder\n")
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    assert not str(inside_real_repo).startswith(str(linked_repo_root))

    with pytest.raises(ValueError, match="inside the repository"):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=fresh_clone,
            repo_root=linked_repo_root,
            paths_file=inside_real_repo,
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=mailmap_file,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_rejects_a_relative_spec_file_path(
    tmp_path: Path, fresh_clone: Path
) -> None:
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    with pytest.raises(ValueError, match="absolute"):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=fresh_clone,
            repo_root=repo_root,
            paths_file=Path("relative/paths.txt"),
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=mailmap_file,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_accepts_spec_files_outside_the_repository(
    tmp_path: Path, fresh_clone: Path
) -> None:
    """The positive control for the rejection tests above: identical setup
    but with every spec file genuinely outside `repo_root`, which must
    succeed and emit both commands."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    result = run_rewrite(
        quiescence=_QUIET,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=True,
        log=log,
        repo=fresh_clone,
        repo_root=repo_root,
        paths_file=paths_file,
        replace_text_file=replace_text_file,
        replace_message_file=replace_message_file,
        mailmap_file=mailmap_file,
        origin_url="git@github.com:x/y.git",
        runner=runner,
    )

    assert result == 0
    assert len(runner.commands) == 2


# --- the gate is the real preflight.gate, not a local re-derivation --------


@pytest.mark.parametrize("abandonment_recorded_value", [True, False])
def test_run_rewrite_calls_preflight_gate_with_exactly_its_own_arguments(
    tmp_path: Path,
    fresh_clone: Path,
    monkeypatch: pytest.MonkeyPatch,
    abandonment_recorded_value: bool,
) -> None:
    """Patch `scripts.purge.rewrite.gate` with a spy and assert it was
    called with exactly the four arguments `run_rewrite` received --
    positive proof that `run_rewrite` delegates to the real function object
    rather than re-deriving a halt/proceed decision inline. A reimplementation
    would never call this patched spy at all, so `calls` would stay empty.

    Parametrized over `abandonment_recorded_value` (`True` and `False`) so a
    hardcoded literal in the `gate(...)` call -- which would forward the same
    constant regardless of what `run_rewrite` received -- fails on whichever
    case does not match that constant, instead of being invisible behind a
    fixture that only ever supplies `True`.
    """
    import scripts.purge.rewrite as rewrite_module

    calls: list[tuple[object, ...]] = []

    def _spy_gate(
        q: Quiescence,
        abandoned_branches: tuple[str, ...],
        abandonment_recorded: bool,
        log: Path,
    ) -> int:
        calls.append((q, abandoned_branches, abandonment_recorded, log))
        return 0

    monkeypatch.setattr(rewrite_module, "gate", _spy_gate)

    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    run_rewrite(
        quiescence=_QUIET,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=abandonment_recorded_value,
        log=log,
        repo=fresh_clone,
        repo_root=repo_root,
        paths_file=paths_file,
        replace_text_file=replace_text_file,
        replace_message_file=replace_message_file,
        mailmap_file=mailmap_file,
        origin_url="git@github.com:x/y.git",
        runner=runner,
    )

    assert calls == [
        (
            _QUIET,
            ("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded_value,
            log,
        )
    ]


def test_run_rewrite_halts_on_a_blank_abandoned_branch_entry_like_the_real_gate_does(
    tmp_path: Path,
) -> None:
    """`("",)` is exactly the blank-entry accident `preflight.gate` refuses
    (see `tests/purge/test_preflight.py`). A naive local re-derivation that
    only checks `bool(abandoned_branches)` -- true for a one-element tuple,
    blank or not -- would proceed here where the real gate halts; this
    fixture is chosen specifically because it distinguishes the two."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    # Sanity: the real preflight.gate does halt on this input directly.
    direct_result = gate(
        _QUIET,
        abandoned_branches=("",),
        abandonment_recorded=True,
        log=tmp_path / "direct-check-log",
    )
    assert direct_result != 0

    result = run_rewrite(
        quiescence=_QUIET,
        abandoned_branches=("",),
        abandonment_recorded=True,
        log=log,
        repo=tmp_path / "clone",
        repo_root=repo_root,
        paths_file=paths_file,
        replace_text_file=replace_text_file,
        replace_message_file=replace_message_file,
        mailmap_file=mailmap_file,
        origin_url="git@github.com:x/y.git",
        runner=runner,
    )

    assert result != 0
    assert runner.commands == []


def test_run_rewrite_halts_when_abandonment_is_not_recorded_like_the_real_gate_does(
    tmp_path: Path,
) -> None:
    """`abandonment_recorded=False`, otherwise entirely valid input (a quiet
    `Quiescence`, two non-blank abandoned-branch names). The real
    `preflight.gate` halts on this (Req 6.6); a `run_rewrite` that hardcoded
    `True` into its own `gate(...)` call would ignore the caller's `False`
    and proceed to emit both commands regardless. This mirrors the blank-
    entry test above for the sibling half of the same obligation."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    # Sanity: the real preflight.gate does halt on this input directly.
    direct_result = gate(
        _QUIET,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=False,
        log=tmp_path / "direct-check-log",
    )
    assert direct_result != 0

    result = run_rewrite(
        quiescence=_QUIET,
        abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
        abandonment_recorded=False,
        log=log,
        repo=tmp_path / "clone",
        repo_root=repo_root,
        paths_file=paths_file,
        replace_text_file=replace_text_file,
        replace_message_file=replace_message_file,
        mailmap_file=mailmap_file,
        origin_url="git@github.com:x/y.git",
        runner=runner,
    )

    assert result != 0
    assert runner.commands == []
    log_text = log.read_text()
    assert "\tHALT\t" in log_text
    assert "abandonment_recorded is False" in log_text


def test_run_rewrite_requires_keyword_arguments(tmp_path: Path) -> None:
    """`run_rewrite`'s parameters are keyword-only (the bare `*`) so `repo`
    and `repo_root` cannot be transposed by position at a call site.

    Passing all twelve parameters positionally, in their declared order --
    not a partial/short positional call, which `TypeError`s anyway for
    missing arguments and so would pass this test whether or not `*` is
    present -- must raise `TypeError` specifically because keyword-only
    parameters cannot be filled positionally at all, however many are
    supplied.
    """
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(tmp_path / "agent-log")

    with pytest.raises(TypeError):
        run_rewrite(  # type: ignore[call-arg]
            _QUIET,
            ("impl/athlete-benchmarks", "impl/training-load"),
            True,
            tmp_path / "agent-log",
            tmp_path / "clone",
            tmp_path / "repo",
            paths_file,
            replace_text_file,
            replace_message_file,
            mailmap_file,
            "git@github.com:x/y.git",
            runner,
        )


def test_run_rewrite_refuses_a_repo_that_is_not_a_fresh_clone(tmp_path: Path) -> None:
    """The precondition is asserted by the driver, not remembered by the
    operator: a proceeding gate followed by a `repo` that is not a fresh
    clone must raise and emit ZERO commands. Zero is the load-bearing part
    -- an assertion that raised only after the `git filter-repo` command had
    been handed to the runner would be no assertion at all on a one-shot
    run."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = _source_repo(tmp_path)
    local_clone = _clone(source, tmp_path / "local-clone", "--local")
    paths_file, replace_text_file, replace_message_file, mailmap_file = _spec_files(
        tmp_path
    )
    runner = _RecordingRunner(log)

    with pytest.raises(FreshCloneError):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=local_clone,
            repo_root=repo_root,
            paths_file=paths_file,
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=mailmap_file,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


def test_run_rewrite_checks_the_clone_before_the_spec_file_placement(
    tmp_path: Path,
) -> None:
    """Both preconditions are violated at once -- a locally-optimised clone
    AND a spec file living inside the repository. The clone is the subject
    every other check is about, so it is checked first; without this the
    order would be an accident of the implementation."""
    log = tmp_path / "agent-log"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = _source_repo(tmp_path)
    local_clone = _clone(source, tmp_path / "local-clone", "--local")
    paths_file, replace_text_file, replace_message_file, _mailmap = _spec_files(
        tmp_path
    )
    inside_mailmap = repo_root / ".mailmap"
    inside_mailmap.write_text("placeholder\n")
    runner = _RecordingRunner(log)

    with pytest.raises(FreshCloneError):
        run_rewrite(
            quiescence=_QUIET,
            abandoned_branches=("impl/athlete-benchmarks", "impl/training-load"),
            abandonment_recorded=True,
            log=log,
            repo=local_clone,
            repo_root=repo_root,
            paths_file=paths_file,
            replace_text_file=replace_text_file,
            replace_message_file=replace_message_file,
            mailmap_file=inside_mailmap,
            origin_url="git@github.com:x/y.git",
            runner=runner,
        )

    assert runner.commands == []


# ============================================================================
# HistoryReplacement -- scripts/purge/replace.py (task 7.6, re-targeted here
# per design.md's Component -> file map)
# ============================================================================

# ---------------------------------------------------------------------------
# build_* -- pure command builders, whole-tuple equality
# ---------------------------------------------------------------------------


def test_build_commit_tree_command_is_exactly_the_expected_tuple() -> None:
    command = build_commit_tree_command(
        Path("/scratch/repo"), "deadbeef" * 5, "root message\n"
    )
    assert command == (
        "git",
        "-C",
        "/scratch/repo",
        "commit-tree",
        "deadbeef" * 5,
        "-m",
        "root message\n",
    )


def test_build_update_ref_command_is_exactly_the_expected_tuple() -> None:
    command = build_update_ref_command(
        Path("/scratch/repo"), "purge-replacement-root", "cafebabe" * 5
    )
    assert command == (
        "git",
        "-C",
        "/scratch/repo",
        "update-ref",
        "refs/heads/purge-replacement-root",
        "cafebabe" * 5,
    )


def test_build_clone_command_is_exactly_the_expected_tuple() -> None:
    command = build_clone_command(
        Path("/scratch/repo"), "purge-replacement-root", Path("/scratch/clone")
    )
    assert command == (
        "git",
        "clone",
        "--no-local",
        "--single-branch",
        "--branch",
        "purge-replacement-root",
        "--",
        "/scratch/repo",
        "/scratch/clone",
    )


def test_build_rename_branch_command_defaults_the_target_to_main() -> None:
    command = build_rename_branch_command(
        Path("/scratch/clone"), "purge-replacement-root"
    )
    assert command == (
        "git",
        "-C",
        "/scratch/clone",
        "branch",
        "-m",
        "purge-replacement-root",
        "main",
    )


def test_build_rename_branch_command_accepts_an_explicit_target() -> None:
    command = build_rename_branch_command(Path("/scratch/clone"), "old", "new")
    assert command == ("git", "-C", "/scratch/clone", "branch", "-m", "old", "new")


# ---------------------------------------------------------------------------
# ROOT_COMMIT_MESSAGE -- the fixed root commit message (Req 11.3)
# ---------------------------------------------------------------------------


def test_root_commit_message_is_clean_against_an_absent_forbidden_string() -> None:
    """A token absent by construction holds for every possible
    `ROOT_COMMIT_MESSAGE` and pins nothing on its own -- the positive
    control immediately below is what proves `matches()` is actually being
    run against this message's real text rather than a fixture that would
    report `()` regardless of content."""
    forbidden = ForbiddenStrings(
        values=("zzz-not-present-in-the-message-zzz",), source=Path("/dev/null")
    )
    assert matches(ROOT_COMMIT_MESSAGE, forbidden) == ()


def test_root_commit_message_is_dirty_against_its_own_forbidden_substring() -> None:
    """The positive control: a `ForbiddenStrings` value drawn straight from
    `ROOT_COMMIT_MESSAGE`'s own text ("replaced, not rewritten") must be
    reported as a match, proving the test above is discriminating and not
    vacuously true for any message."""
    forbidden = ForbiddenStrings(
        values=("replaced, not rewritten",), source=Path("/dev/null")
    )
    assert matches(ROOT_COMMIT_MESSAGE, forbidden) != ()


def test_root_commit_message_names_the_provenance_record() -> None:
    assert "docs/reference/history-rewrites.md" in ROOT_COMMIT_MESSAGE


# ---------------------------------------------------------------------------
# run_replace -- fixtures
# ---------------------------------------------------------------------------

_NON_PERSONAL_ADDRESS = "noreply@fitdocs.example"
_NON_PERSONAL_NAME = "fitdocs maintainer"
_TEMP_BRANCH = "purge-replacement-root"

_REPLACE_ABANDONED = ("impl/athlete-benchmarks", "impl/training-load")


def _replace_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """A plain git command against a throwaway fixture repository -- unlike
    the `HistoryRewrite` section's `_git` above, this does NOT inject a
    hardcoded `-c user.name=`/`-c user.email=` override: this section's own
    fixtures configure a specific non-personal identity via `git config`
    and rely on it surviving into the commits they build, which the
    override would silently replace."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _identity_env(tmp_path: Path, address: str) -> dict[str, str]:
    """The same `GIT_CONFIG_GLOBAL`-override pattern
    `tests/purge/test_adopt.py` uses so `assert_commit_identity`'s tests
    never touch the real machine-wide global git config."""
    global_cfg = tmp_path / "scratch-global-gitconfig"
    global_cfg.write_text(f"[user]\n\temail = {address}\n")
    return {"GIT_CONFIG_GLOBAL": str(global_cfg)}


def _repo_root(tmp_path: Path) -> tuple[Path, str, str]:
    """A real repository standing in for the certified tip: one commit,
    identity configured in both scopes to `_NON_PERSONAL_ADDRESS` (local
    here; global via `_identity_env`). Returns `(repo_root, commit_id,
    tree_id)`."""
    root = tmp_path / "repo-root"
    root.mkdir()
    _replace_git(root, "init", "-q", "-b", "main")
    _replace_git(root, "config", "user.email", _NON_PERSONAL_ADDRESS)
    _replace_git(root, "config", "user.name", _NON_PERSONAL_NAME)
    (root / "a.txt").write_text("certified content\n")
    _replace_git(root, "add", "-A")
    _replace_git(root, "commit", "-q", "-m", "certified tip")
    commit_id = _replace_git(root, "rev-parse", "HEAD").stdout.strip()
    tree_id = _replace_git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    return root, commit_id, tree_id


def _forge_and_clone_for_real(
    repo_root: Path, tree_id: str, scratch_clone_dir: Path
) -> str:
    """Build, by plain `git` commands -- never through `run_replace`'s own
    `runner` -- exactly the state the driver's own forge and clone commands
    would produce: a parentless root commit over `tree_id` under
    `refs/heads/_TEMP_BRANCH` in `repo_root`, then a real `--no-local
    --single-branch` clone of it into `scratch_clone_dir`, left named
    `_TEMP_BRANCH` (NOT renamed -- `assert_fresh_clone`'s "every local head
    equal to its origin counterpart" property holds only before the rename,
    since `origin` never had a branch named `main`). Returns the forged
    commit id."""
    root_commit = _replace_git(
        repo_root, "commit-tree", tree_id, "-m", ROOT_COMMIT_MESSAGE
    ).stdout.strip()
    _replace_git(repo_root, "update-ref", f"refs/heads/{_TEMP_BRANCH}", root_commit)
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--no-local",
            "--single-branch",
            "--branch",
            _TEMP_BRANCH,
            "--",
            str(repo_root),
            str(scratch_clone_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return root_commit


class _ReplaceRunner:
    """Records every emitted command; the content of the shared agent log at
    the moment of the FIRST call (mirroring this file's own
    `_RecordingRunner`, above, for `run_rewrite`); and, if given a
    `timeline`, appends every command there too, so a single test can order
    `runner` calls against non-`runner` events (the swap) on one axis.

    Returns the forged commit id (never executed for real) for a
    `commit-tree` command, and -- ONLY for the branch-rename command --
    actually runs it, since that command moves a ref inside a disposable
    scratch clone this module's own fixtures already built directly (see
    module docstring)."""

    def __init__(
        self,
        log_path: Path,
        forged_commit_id: str,
        timeline: list[tuple[str, ...]] | None = None,
    ) -> None:
        self.log_path = log_path
        self.forged_commit_id = forged_commit_id
        self.commands: list[tuple[str, ...]] = []
        self.log_at_first_call: str | None = None
        self.timeline = timeline

    def __call__(self, command: Sequence[str]) -> str:
        if self.log_at_first_call is None:
            self.log_at_first_call = (
                self.log_path.read_text() if self.log_path.exists() else ""
            )
        cmd: tuple[str, ...] = tuple(command)
        self.commands.append(cmd)
        if self.timeline is not None:
            self.timeline.append(cmd)
        if "commit-tree" in cmd:
            return self.forged_commit_id + "\n"
        if "branch" in cmd and "-m" in cmd:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        return ""


def _clean_forbidden() -> ForbiddenStrings:
    return ForbiddenStrings(
        values=("zzz-not-present-anywhere-zzz",), source=Path("/dev/null")
    )


def _write_agent_log(old_git_dir: Path) -> Path:
    old_git_dir.mkdir(parents=True, exist_ok=True)
    log = old_git_dir / "agent-log"
    log.write_text("2026-01-01T00:00:00Z\tsession\tNOTE\tsomething coordinated\n")
    return log


# ---------------------------------------------------------------------------
# run_replace -- gating (re-targeted from test_rewrite_gate.py)
# ---------------------------------------------------------------------------


def test_a_failing_gate_emits_zero_commands(tmp_path: Path) -> None:
    """`repo_root` here is deliberately not a real repository at all -- a
    halting gate must decide the outcome before anything else in the driver
    runs. `_append_certified_tip_line` is the very next thing `run_replace`
    calls on a passing gate; `adopt.assert_commit_identity` is the one after
    that, against `repo_root` itself -- either would fail loudly against a
    nonexistent `repo_root` if the halting gate did not short-circuit
    first."""
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id="0" * 40)

    result = run_replace(
        quiescence=_DIRTY,
        abandoned_branches=_REPLACE_ABANDONED,
        abandonment_recorded=True,
        log=log,
        repo_root=tmp_path / "does-not-exist",
        certified_tip_commit="a" * 40,
        certified_tip_tree="b" * 40,
        non_personal_address=_NON_PERSONAL_ADDRESS,
        non_personal_name=_NON_PERSONAL_NAME,
        forbidden=_clean_forbidden(),
        temp_branch=_TEMP_BRANCH,
        scratch_clone_dir=tmp_path / "scratch-clone",
        old_git_dir=tmp_path / "old-git",
        archive_dir=tmp_path / "archive",
        runner=runner,
    )

    assert result != 0
    assert runner.commands == []
    assert "\tHALT\t" in log.read_text()
    assert "\tCERTIFIED_TIP\t" not in log.read_text()


def test_a_passing_gate_logs_proceeding_before_the_first_emitted_command(
    tmp_path: Path,
) -> None:
    """The gate proceeds, the certified-tip line and `gate`'s own
    `PROCEEDING` line are both written, and both are present in the log
    BEFORE the first command reaches `runner` -- regardless of what happens
    to the pipeline afterward (here, a forbidden-string source that DOES
    match the fixed root message, so `RootMessageError` is raised before any
    command is emitted at all: zero commands is a stronger proof than one)."""
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    log = tmp_path / "agent-log"
    dirty_forbidden = ForbiddenStrings(values=("Initial commit",), source=Path("/x"))
    runner = _ReplaceRunner(log, forged_commit_id="deadbeef" * 5)

    with pytest.raises(RootMessageError):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=dirty_forbidden,
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=tmp_path / "scratch-clone",
            old_git_dir=tmp_path / "old-git",
            archive_dir=tmp_path / "archive",
            runner=runner,
            env=env,
        )

    assert runner.commands == []
    log_text = log.read_text()
    assert "\tPROCEEDING\t" in log_text
    assert "\tCERTIFIED_TIP\t" in log_text
    assert log_text.index("\tPROCEEDING\t") < log_text.index("\tCERTIFIED_TIP\t")


# ---------------------------------------------------------------------------
# run_replace -- the commit-identity precondition (Req 5.3): design.md
# states a fresh clone inherits global git config, so global drift is the
# one setting whose corruption would silently violate Req 5.3 while every
# local check kept passing. Each test below leaves ONE of the two scopes
# personal and asserts run_replace refuses before any command reaches
# runner -- deleting the `adopt.assert_commit_identity(...)` call from
# `run_replace` leaves the full suite green without these.
# ---------------------------------------------------------------------------

_PERSONAL_ADDRESS = "josh@personal.example"


def test_run_replace_refuses_when_the_global_identity_is_personal(
    tmp_path: Path,
) -> None:
    """`repo_root`'s LOCAL `user.email` is correctly the non-personal
    address (`_repo_root` sets it); only the GLOBAL scope, fed through
    `GIT_CONFIG_GLOBAL`, still names a personal one."""
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _PERSONAL_ADDRESS)
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id="deadbeef" * 5)

    with pytest.raises(IdentityError, match="global"):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=tmp_path / "scratch-clone",
            old_git_dir=tmp_path / "old-git",
            archive_dir=tmp_path / "archive",
            runner=runner,
            env=env,
        )

    assert runner.commands == []


def test_run_replace_refuses_when_the_local_identity_is_personal(
    tmp_path: Path,
) -> None:
    """`repo_root`'s GLOBAL scope (via `GIT_CONFIG_GLOBAL`) is correctly the
    non-personal address; only the LOCAL `user.email`, set directly on
    `repo_root`, is personal."""
    repo_root = tmp_path / "repo-root-personal-local"
    repo_root.mkdir()
    _replace_git(repo_root, "init", "-q", "-b", "main")
    _replace_git(repo_root, "config", "user.email", _PERSONAL_ADDRESS)
    _replace_git(repo_root, "config", "user.name", "Josh Personal")
    (repo_root / "a.txt").write_text("certified content\n")
    _replace_git(repo_root, "add", "-A")
    _replace_git(repo_root, "commit", "-q", "-m", "certified tip")
    commit_id = _replace_git(repo_root, "rev-parse", "HEAD").stdout.strip()
    tree_id = _replace_git(repo_root, "rev-parse", "HEAD^{tree}").stdout.strip()

    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id="deadbeef" * 5)

    with pytest.raises(IdentityError, match="local"):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=tmp_path / "scratch-clone",
            old_git_dir=tmp_path / "old-git",
            archive_dir=tmp_path / "archive",
            runner=runner,
            env=env,
        )

    assert runner.commands == []


# ---------------------------------------------------------------------------
# run_replace -- the full ordering, an injected runner, never executed for
# real except the disposable branch rename (see module docstring)
# ---------------------------------------------------------------------------


def test_run_replace_emits_the_full_sequence_with_swap_after_every_pre_swap_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    scratch_clone_dir = tmp_path / "scratch-clone"
    forged_commit_id = _forge_and_clone_for_real(repo_root, tree_id, scratch_clone_dir)

    old_git_dir = repo_root / ".git"
    agent_log = _write_agent_log(old_git_dir)
    agent_log_content_before = agent_log.read_text()
    archive_dir = tmp_path / "archive"
    log = tmp_path / "agent-log"

    timeline: list[tuple[str, ...]] = []
    runner = _ReplaceRunner(log, forged_commit_id, timeline=timeline)

    real_move_clone = adopt.move_clone

    def _spy_move_clone(clone: Path, target: Path) -> Path:
        result = real_move_clone(clone, target)
        timeline.append(("SWAP", str(clone), str(target)))
        return result

    monkeypatch.setattr(adopt, "move_clone", _spy_move_clone)

    real_run_pre_swap_rows = replace_module.run_pre_swap_rows

    def _spy_run_pre_swap_rows(
        repo: Path,
        certified_tree_id: str,
        forbidden: ForbiddenStrings,
        allowed: frozenset[str],
    ) -> tuple[object, ...]:
        rows = real_run_pre_swap_rows(repo, certified_tree_id, forbidden, allowed)
        timeline.append(("VERIFY_ROWS_DONE",))
        return rows

    monkeypatch.setattr(replace_module, "run_pre_swap_rows", _spy_run_pre_swap_rows)

    result = run_replace(
        quiescence=_QUIET,
        abandoned_branches=_REPLACE_ABANDONED,
        abandonment_recorded=True,
        log=log,
        repo_root=repo_root,
        certified_tip_commit=commit_id,
        certified_tip_tree=tree_id,
        non_personal_address=_NON_PERSONAL_ADDRESS,
        non_personal_name=_NON_PERSONAL_NAME,
        forbidden=_clean_forbidden(),
        temp_branch=_TEMP_BRANCH,
        scratch_clone_dir=scratch_clone_dir,
        old_git_dir=old_git_dir,
        archive_dir=archive_dir,
        runner=runner,
        env=env,
    )

    assert result == 0

    # The whole emitted command sequence, in design order, by whole-tuple
    # equality (change-protocol's "assert whole values, not membership").
    assert tuple(runner.commands) == (
        build_commit_tree_command(repo_root, tree_id, ROOT_COMMIT_MESSAGE),
        build_update_ref_command(repo_root, _TEMP_BRANCH, forged_commit_id),
        build_clone_command(repo_root, _TEMP_BRANCH, scratch_clone_dir),
        build_rename_branch_command(scratch_clone_dir, _TEMP_BRANCH),
    )

    # The swap is strictly after every pre-swap row: an ordering anchor, not
    # membership -- moving either `adopt.move_clone` call above the
    # `run_pre_swap_rows` call in `run_replace`'s body reds this.
    verify_done_index = timeline.index(("VERIFY_ROWS_DONE",))
    swap_indices = [i for i, entry in enumerate(timeline) if entry[0] == "SWAP"]
    assert len(swap_indices) == 2, timeline
    assert all(index > verify_done_index for index in swap_indices), timeline

    # The archive is genuinely readable, and the working repository now
    # holds the fresh root -- `old_git_dir` and `repo_root / ".git"` are the
    # SAME path, so after the swap it holds the FRESH `.git` (the archive
    # copy, not this path, is where the pre-replacement history now lives).
    assert archive_dir.is_dir()
    assert old_git_dir == repo_root / ".git"
    fresh_head = _replace_git(repo_root, "rev-parse", "HEAD").stdout.strip()
    assert fresh_head == forged_commit_id
    assert _replace_git(repo_root, "rev-list", "--all", "--count").stdout.strip() == "1"
    archive_head = subprocess.run(
        ["git", "-C", str(archive_dir), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert archive_head == commit_id  # the OLD certified-tip commit, archived

    # The shared agent log's SURVIVAL is an observable, not an assumption
    # (design.md `#### HistoryReplacement`): its CONTENT, not merely its
    # presence, must be readable at the new `.git`'s path after the swap --
    # deleting the carry-over step in `run_replace` (`adopt.build_checklist`,
    # the `shutil.copy2` loop, `adopt.assert_carry_over`) leaves the full
    # suite green without this assertion.
    post_swap_agent_log = repo_root / ".git" / "agent-log"
    assert post_swap_agent_log.read_text() == agent_log_content_before


def test_run_replace_refuses_and_does_not_swap_when_the_carry_over_checklist_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A carry-over failure (forced here by making `adopt.assert_carry_over`
    always raise, standing in for a real digest mismatch) must refuse BEFORE
    the swap runs -- neither `adopt.move_clone` call fires, `repo_root`'s own
    `.git` is untouched, and `archive_dir` never comes to exist."""
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    scratch_clone_dir = tmp_path / "scratch-clone"
    forged_commit_id = _forge_and_clone_for_real(repo_root, tree_id, scratch_clone_dir)

    old_git_dir = repo_root / ".git"
    agent_log = _write_agent_log(old_git_dir)
    agent_log_content_before = agent_log.read_text()
    old_main_before = _replace_git(
        repo_root, "rev-parse", "refs/heads/main"
    ).stdout.strip()
    archive_dir = tmp_path / "archive"
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id)

    move_clone_calls: list[tuple[Path, Path]] = []
    real_move_clone = adopt.move_clone

    def _spy_move_clone(clone: Path, target: Path) -> Path:
        move_clone_calls.append((clone, target))
        return real_move_clone(clone, target)

    monkeypatch.setattr(adopt, "move_clone", _spy_move_clone)

    def _always_fail_carry_over(items: object, *, doomed_root: Path) -> None:
        raise CarryOverError("forced digest mismatch for this test")

    monkeypatch.setattr(adopt, "assert_carry_over", _always_fail_carry_over)

    with pytest.raises(CarryOverError, match="forced digest mismatch"):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=scratch_clone_dir,
            old_git_dir=old_git_dir,
            archive_dir=archive_dir,
            runner=runner,
            env=env,
        )

    assert move_clone_calls == []  # the swap never ran
    assert not archive_dir.exists()
    assert old_git_dir.is_dir()
    assert agent_log.read_text() == agent_log_content_before
    assert (
        _replace_git(repo_root, "rev-parse", "refs/heads/main").stdout.strip()
        == old_main_before
    )


def test_run_replace_discards_the_scratch_clone_on_a_pre_swap_failure(
    tmp_path: Path,
) -> None:
    """A pre-swap row failure (here: the tree-identity row, forced by
    passing a `certified_tip_tree` that does not match what the pre-built
    scratch clone actually carries) discards the scratch clone and touches
    NOTHING else (Req 7.7) -- asserted below by the two things actually
    checked: the agent log's *content* is unchanged, and `repo_root`'s own
    `refs/heads/main` still resolves to what it resolved to before the
    call. That is not the same claim as `old_git_dir` being byte-for-byte
    identical before and after; nothing here hashes the whole directory."""
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    scratch_clone_dir = tmp_path / "scratch-clone"
    forged_commit_id = _forge_and_clone_for_real(repo_root, tree_id, scratch_clone_dir)

    old_git_dir = repo_root / ".git"
    agent_log = _write_agent_log(old_git_dir)
    agent_log_content_before = agent_log.read_text()
    old_main_before = _replace_git(
        repo_root, "rev-parse", "refs/heads/main"
    ).stdout.strip()
    archive_dir = tmp_path / "archive"
    log = tmp_path / "agent-log"

    runner = _ReplaceRunner(log, forged_commit_id)
    wrong_tree_id = "f" * 40

    with pytest.raises(PreSwapVerificationError, match="root tree identical"):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=wrong_tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=scratch_clone_dir,
            old_git_dir=old_git_dir,
            archive_dir=archive_dir,
            runner=runner,
            env=env,
        )

    assert not scratch_clone_dir.exists()  # discarded
    assert not archive_dir.exists()  # the swap never ran
    assert old_git_dir.is_dir()  # untouched
    assert agent_log.read_text() == agent_log_content_before  # untouched
    assert (
        _replace_git(repo_root, "rev-parse", "refs/heads/main").stdout.strip()
        == old_main_before
    )  # repo_root's own main ref is untouched


def test_run_replace_requires_keyword_arguments(tmp_path: Path) -> None:
    """`run_replace`'s parameters are keyword-only so `repo_root`,
    `scratch_clone_dir`, `old_git_dir` and `archive_dir` -- four `Path`
    arguments -- cannot be transposed by position at a call site."""
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id="0" * 40)

    with pytest.raises(TypeError):
        run_replace(  # type: ignore[call-arg]
            _QUIET,
            _REPLACE_ABANDONED,
            True,
            log,
            tmp_path / "repo",
            "a" * 40,
            "b" * 40,
            _NON_PERSONAL_ADDRESS,
            _NON_PERSONAL_NAME,
            _clean_forbidden(),
            _TEMP_BRANCH,
            tmp_path / "scratch",
            tmp_path / "old-git",
            tmp_path / "archive",
            runner,
        )


# ---------------------------------------------------------------------------
# run_pre_swap_rows -- pinned as a whole value (change-protocol's "assert
# whole values, not membership"). Without this, `check_exactly_one_commit_
# reachable`, `check_refs_clean`, `check_no_token_in_any_commit_message` and
# `check_no_token_in_path_or_blob` are each individually deletable from
# `run_pre_swap_rows`'s body with the full suite green.
# ---------------------------------------------------------------------------


def test_run_pre_swap_rows_returns_exactly_the_six_rows_in_design_order(
    tmp_path: Path,
) -> None:
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    scratch_clone_dir = tmp_path / "scratch-clone"
    _forge_and_clone_for_real(repo_root, tree_id, scratch_clone_dir)

    rows = run_pre_swap_rows(
        scratch_clone_dir,
        tree_id,
        _clean_forbidden(),
        frozenset({_NON_PERSONAL_ADDRESS, _NON_PERSONAL_NAME}),
    )

    # A whole-value pin of the *labels*, in call order -- independent of
    # whether each row happens to pass against this particular fixture (the
    # scratch clone here still carries `origin`, so the refs-clean row is
    # expected to fail; only the row LABELS are pinned here).
    assert tuple(row.row for row in rows) == (
        "exactly one commit reachable",
        "root tree identical to the certified tip tree",
        "no refs/original, no extra refs",
        "metadata clean",
        "no token in any commit message",
        "no token in any path or blob of the single commit",
    )


# ---------------------------------------------------------------------------
# run_replace -- assert_fresh_clone is called for real against the scratch
# clone (Req 7.2's "alternates file asserted absent"). Deleting `run_replace`'s
# `assert_fresh_clone(scratch_clone_dir)` call leaves the full suite
# green without this test: the scratch clone here is pre-built with `--shared`
# (an alternates-bearing clone) rather than `--no-local`, so `run_replace`
# must raise `FreshCloneError` when it actually calls `assert_fresh_clone` on
# it.
# ---------------------------------------------------------------------------


def _forge_and_shared_clone_for_real(
    repo_root: Path, tree_id: str, scratch_clone_dir: Path
) -> str:
    """The same forge `_forge_and_clone_for_real` performs, but the clone
    step uses `--shared` instead of `--no-local` -- an alternates-bearing
    clone `assert_fresh_clone` must reject on sight."""
    root_commit = _replace_git(
        repo_root, "commit-tree", tree_id, "-m", ROOT_COMMIT_MESSAGE
    ).stdout.strip()
    _replace_git(repo_root, "update-ref", f"refs/heads/{_TEMP_BRANCH}", root_commit)
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--shared",
            "--single-branch",
            "--branch",
            _TEMP_BRANCH,
            "--",
            str(repo_root),
            str(scratch_clone_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return root_commit


def test_run_replace_rejects_an_alternates_bearing_scratch_clone(
    tmp_path: Path,
) -> None:
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    scratch_clone_dir = tmp_path / "scratch-clone"
    forged_commit_id = _forge_and_shared_clone_for_real(
        repo_root, tree_id, scratch_clone_dir
    )
    assert (
        scratch_clone_dir / ".git" / "objects" / "info" / "alternates"
    ).exists()  # the fixture really is alternates-bearing

    old_git_dir = repo_root / ".git"
    _write_agent_log(old_git_dir)
    archive_dir = tmp_path / "archive"
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id)

    with pytest.raises(FreshCloneError, match="alternates"):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=scratch_clone_dir,
            old_git_dir=old_git_dir,
            archive_dir=archive_dir,
            runner=runner,
            env=env,
        )

    assert not archive_dir.exists()  # the swap never ran


# ---------------------------------------------------------------------------
# run_replace -- the archive readability check (design.md step 8). Deleting
# `run_replace`'s `_assert_archive_readable(archive_dir, certified_tip_commit)`
# call leaves the full suite green without this test: a
# `certified_tip_commit` that does not actually resolve in the archived old
# `.git` (the tree id is still correct, so every pre-swap row still passes
# and the swap runs) must still be caught, after the swap, before
# `run_replace` returns 0.
# ---------------------------------------------------------------------------


def test_run_replace_asserts_archive_readability_against_the_certified_tip_commit(
    tmp_path: Path,
) -> None:
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    scratch_clone_dir = tmp_path / "scratch-clone"
    forged_commit_id = _forge_and_clone_for_real(repo_root, tree_id, scratch_clone_dir)

    old_git_dir = repo_root / ".git"
    _write_agent_log(old_git_dir)
    archive_dir = tmp_path / "archive"
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id)
    # Deliberately a well-formed 40-hex id that is absent from the archive,
    # because that is the case a shape check cannot see: `git rev-parse
    # --verify --quiet` exits 0 and echoes this id back even though no such
    # object exists (measured, git 2.54.0), while `git cat-file -e` exits 1.
    # A non-hex bogus id would pass this test under either implementation and
    # so would pin nothing about which check the row uses.
    bogus_certified_tip_commit = "f" * 40

    with pytest.raises(
        ArchiveNotReadableError, match=re.escape(bogus_certified_tip_commit)
    ):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=bogus_certified_tip_commit,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=scratch_clone_dir,
            old_git_dir=old_git_dir,
            archive_dir=archive_dir,
            runner=runner,
            env=env,
        )

    assert archive_dir.is_dir()  # the swap DID run before the archive check
    assert not (repo_root / "does-not-matter").exists()  # sanity: no crash mid-swap


# ---------------------------------------------------------------------------
# _assert_archive_readable -- the fsck arm's output strictness. Narrowing
# `if fsck.returncode != 0 or fsck.stdout.strip() or fsck.stderr.strip():`
# to `if fsck.returncode != 0:` leaves the full suite green: `git fsck
# --connectivity-only` exits 0 while printing `dangling commit <id>` to
# stdout for an object unreachable from any ref, so the return-code-only
# check would report a corrupted-in-that-specific-way archive readable.
# ---------------------------------------------------------------------------


def test_assert_archive_readable_rejects_an_archive_with_a_dangling_object(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "archive-source"
    repo.mkdir()
    _replace_git(repo, "init", "-q", "-b", "main")
    _replace_git(repo, "config", "user.email", _NON_PERSONAL_ADDRESS)
    _replace_git(repo, "config", "user.name", _NON_PERSONAL_NAME)
    (repo / "a.txt").write_text("tip content\n")
    _replace_git(repo, "add", "-A")
    _replace_git(repo, "commit", "-q", "-m", "tip")
    tip_commit = _replace_git(repo, "rev-parse", "HEAD").stdout.strip()
    tree_id = _replace_git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    # A commit object with no ref pointing at it -- `git fsck
    # --connectivity-only` reports this on stdout as `dangling commit <id>`
    # while still exiting 0, which is exactly the shape the return-code-only
    # mutant cannot see.
    _replace_git(repo, "commit-tree", tree_id, "-m", "dangling, unreachable")

    fsck_before_fix_check = _replace_git(repo, "fsck", "--connectivity-only")
    assert fsck_before_fix_check.returncode == 0  # confirms the false precondition
    assert "dangling commit" in fsck_before_fix_check.stdout

    archive_dir = repo / ".git"
    with pytest.raises(ArchiveNotReadableError, match="fsck"):
        replace_module._assert_archive_readable(archive_dir, tip_commit)


# ---------------------------------------------------------------------------
# run_replace -- the gate's own forwarded arguments, never a literal
# stand-in (the recurring defeat: `abandonment_recorded`, `abandoned_
# branches` and the returned exit code have each been replaced by a literal
# with the full suite still green in earlier rounds of this task).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("abandonment_recorded", [True, False])
def test_run_replace_forwards_abandonment_recorded_to_the_real_gate(
    tmp_path: Path, abandonment_recorded: bool
) -> None:
    """`abandonment_recorded=True` with `_QUIET` and a real, non-empty
    `abandoned_branches` proceeds past the gate; `abandonment_recorded=False`
    halts, EVEN with the identical quiet quiescence and the identical
    non-empty `abandoned_branches` -- so a mutant that replaces the
    forwarded parameter with a literal `True` cannot pass both parametrized
    cases. `abandoned_branches` must be non-empty here (`_REPLACE_ABANDONED`,
    not `()`): the real gate already halts on an empty tuple regardless of
    `abandonment_recorded` (preflight.py's own "no abandoned branch named"
    branch), which would make an empty tuple unable to isolate this
    parameter at all."""
    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id="0" * 40)
    kwargs = dict(
        quiescence=_QUIET,
        abandoned_branches=_REPLACE_ABANDONED,
        abandonment_recorded=abandonment_recorded,
        log=log,
        repo_root=tmp_path / "does-not-exist",
        certified_tip_commit="a" * 40,
        certified_tip_tree="b" * 40,
        non_personal_address=_NON_PERSONAL_ADDRESS,
        non_personal_name=_NON_PERSONAL_NAME,
        forbidden=_clean_forbidden(),
        temp_branch=_TEMP_BRANCH,
        scratch_clone_dir=tmp_path / "scratch-clone",
        old_git_dir=tmp_path / "old-git",
        archive_dir=tmp_path / "archive",
        runner=runner,
    )

    if abandonment_recorded:
        # Proceeds past the gate; `repo_root` does not exist, so
        # `adopt.assert_commit_identity` raises `IdentityError` next (its
        # `_git_config_value` swallows the git failure on a nonexistent
        # `repo_root` as `None`, which never equals `_NON_PERSONAL_ADDRESS`)
        # -- but it does NOT halt at the gate, and the gate's own
        # PROCEEDING log line is present before that later failure.
        with pytest.raises(IdentityError):
            run_replace(**kwargs)  # type: ignore[arg-type]
        assert "\tPROCEEDING\t" in log.read_text()
        assert "\tHALT\t" not in log.read_text()
    else:
        result = run_replace(**kwargs)  # type: ignore[arg-type]
        assert result != 0
        assert runner.commands == []
        assert "\tHALT\t" in log.read_text()
        assert "\tPROCEEDING\t" not in log.read_text()


def test_run_replace_forwards_abandoned_branches_to_the_real_gate(
    tmp_path: Path,
) -> None:
    """`quiescence=_QUIET` (which never itself halts) with
    `abandonment_recorded=True` and an EMPTY `abandoned_branches` still
    halts -- the real gate's own "no abandoned branch named" rule
    (preflight.py: `if not abandoned_branches: HALT`) -- while the identical
    call with `abandoned_branches=_REPLACE_ABANDONED` proceeds. The two
    calls differ in exactly one forwarded argument, so a mutant that
    replaces `abandoned_branches` with a literal non-empty tuple at the
    `gate(...)` call site in `run_replace` would make the empty-tuple case
    incorrectly proceed too."""
    log_empty = tmp_path / "agent-log-empty"
    runner_empty = _ReplaceRunner(log_empty, forged_commit_id="0" * 40)
    result_empty = run_replace(
        quiescence=_QUIET,
        abandoned_branches=(),
        abandonment_recorded=True,
        log=log_empty,
        repo_root=tmp_path / "does-not-exist",
        certified_tip_commit="a" * 40,
        certified_tip_tree="b" * 40,
        non_personal_address=_NON_PERSONAL_ADDRESS,
        non_personal_name=_NON_PERSONAL_NAME,
        forbidden=_clean_forbidden(),
        temp_branch=_TEMP_BRANCH,
        scratch_clone_dir=tmp_path / "scratch-empty",
        old_git_dir=tmp_path / "old-git-empty",
        archive_dir=tmp_path / "archive-empty",
        runner=runner_empty,
    )

    assert result_empty != 0
    assert runner_empty.commands == []
    assert "\tHALT\t" in log_empty.read_text()
    assert "\tPROCEEDING\t" not in log_empty.read_text()

    log_named = tmp_path / "agent-log-named"
    runner_named = _ReplaceRunner(log_named, forged_commit_id="0" * 40)

    with pytest.raises(IdentityError):
        # Proceeds past the gate (repo_root does not exist, so the identity
        # check fails next -- see the sibling `abandonment_recorded` test
        # above for why that is the expected next failure).
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log_named,
            repo_root=tmp_path / "does-not-exist",
            certified_tip_commit="a" * 40,
            certified_tip_tree="b" * 40,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=_clean_forbidden(),
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=tmp_path / "scratch-named",
            old_git_dir=tmp_path / "old-git-named",
            archive_dir=tmp_path / "archive-named",
            runner=runner_named,
        )

    assert "\tPROCEEDING\t" in log_named.read_text()
    assert "\tHALT\t" not in log_named.read_text()


def test_run_replace_returns_the_gates_own_exit_code_not_a_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing `run_replace`'s `return exit_code` with a hardcoded
    `return 1` is indistinguishable from the real gate's own exit code
    whenever the real gate happens to also return 1 -- so this test forces
    the real `gate` to return a distinctive non-1 sentinel via a spy, and
    asserts `run_replace` forwards THAT value unchanged."""

    def _spy_gate(
        quiescence: Quiescence,
        abandoned_branches: tuple[str, ...],
        abandonment_recorded: bool,
        log: Path,
    ) -> int:
        real_result = gate(quiescence, abandoned_branches, abandonment_recorded, log)
        assert real_result != 0  # precondition: the real gate really halts here
        return 7  # a sentinel no literal stand-in for `exit_code` would emit

    monkeypatch.setattr(replace_module, "gate", _spy_gate)

    log = tmp_path / "agent-log"
    runner = _ReplaceRunner(log, forged_commit_id="0" * 40)

    result = run_replace(
        quiescence=_DIRTY,
        abandoned_branches=_REPLACE_ABANDONED,
        abandonment_recorded=True,
        log=log,
        repo_root=tmp_path / "does-not-exist",
        certified_tip_commit="a" * 40,
        certified_tip_tree="b" * 40,
        non_personal_address=_NON_PERSONAL_ADDRESS,
        non_personal_name=_NON_PERSONAL_NAME,
        forbidden=_clean_forbidden(),
        temp_branch=_TEMP_BRANCH,
        scratch_clone_dir=tmp_path / "scratch-clone",
        old_git_dir=tmp_path / "old-git",
        archive_dir=tmp_path / "archive",
        runner=runner,
    )

    assert result == 7
    assert runner.commands == []


# ---------------------------------------------------------------------------
# _append_certified_tip_line -- commit and tree ids are not interchangeable
# (design.md `#### HistoryReplacement`: the tree id is specifically
# load-bearing). Swapping `certified_tip_commit`/`certified_tip_tree` at
# their one call site, `_append_certified_tip_line`'s call in `run_replace`,
# leaves the suite green without this test, which only asserted the marker
# substring.
# ---------------------------------------------------------------------------


def test_run_replace_logs_the_certified_tip_commit_and_tree_ids_in_the_right_fields(
    tmp_path: Path,
) -> None:
    repo_root, commit_id, tree_id = _repo_root(tmp_path)
    env = _identity_env(tmp_path, _NON_PERSONAL_ADDRESS)
    log = tmp_path / "agent-log"
    dirty_forbidden = ForbiddenStrings(values=("Initial commit",), source=Path("/x"))
    runner = _ReplaceRunner(log, forged_commit_id="deadbeef" * 5)

    assert commit_id != tree_id  # precondition: the two ids differ

    with pytest.raises(RootMessageError):
        run_replace(
            quiescence=_QUIET,
            abandoned_branches=_REPLACE_ABANDONED,
            abandonment_recorded=True,
            log=log,
            repo_root=repo_root,
            certified_tip_commit=commit_id,
            certified_tip_tree=tree_id,
            non_personal_address=_NON_PERSONAL_ADDRESS,
            non_personal_name=_NON_PERSONAL_NAME,
            forbidden=dirty_forbidden,
            temp_branch=_TEMP_BRANCH,
            scratch_clone_dir=tmp_path / "scratch-clone",
            old_git_dir=tmp_path / "old-git",
            archive_dir=tmp_path / "archive",
            runner=runner,
            env=env,
        )

    certified_tip_line = next(
        line for line in log.read_text().splitlines() if "\tCERTIFIED_TIP\t" in line
    )
    assert f"commit={commit_id} tree={tree_id}" in certified_tip_line


# ---------------------------------------------------------------------------
# structural: replace.py's effectful surface (no destructive call outside
# what the design admits)
#
# **Scope note.** This guard is pinned to `scripts/purge/replace.py` as it
# stands at task 7.6's remediation: any red means re-verify by hand before
# touching a pin.
#
# **Why name-set rules (blocklist or allowlist) cannot discriminate here.**
# `replace.py` legitimately needs `subprocess.run` and `shutil.move` (via
# `adopt.move_clone`, which itself calls `shutil.move`), and each of the two
# names underneath this module's own admitted surface -- `subprocess.run`
# and `shutil.rmtree` -- is, by itself, sufficient to destroy `repo_root`
# (`subprocess.run(["git", "-C", str(repo_root), "clean", "-xdff"])`;
# `shutil.move(str(repo_root), decoy)`). Any rule that discriminates on the
# *set of names* used must admit both to allow the module's real behaviour,
# and admitting them admits destruction too. The discriminating information
# lives in the *arguments* passed to those names, in *how many times, and in
# what syntactic position*, each appears -- and, for `subprocess.run`
# specifically, in *which path* is ever handed to a `-C` flag. Three arms
# below cover exactly that, modeled on `tests/purge/test_adopt.py`'s own
# three-arm guard for `adopt.py` (`_bound_names`, `_arm_a_surface_hits`,
# `_arm_b_argument_hits`, `_arm_c_position_hits`, `_planted`).
# ---------------------------------------------------------------------------


def _replace_bound_names(tree: ast.AST) -> set[str]:
    """Every name `scripts/purge/replace.py`'s own source binds -- the same
    walk `tests/purge/test_adopt.py::_bound_names` runs for `adopt.py`."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
    return bound


# -- Arm A: closed surface allowlist -----------------------------------------
#
# Pinned by exact equality (both directions) against `replace.py`'s own AST
# at the time this remediation landed: every `ast.Attribute.attr`, every
# free `ast.Name` (`Load` context, minus every name `_replace_bound_names`
# reports bound), and every `ast.Import`/`ast.ImportFrom` (module dotted
# with the imported name).

_REPLACE_PINNED_ATTRS = frozenset(
    {
        "Exit",
        "assert_carry_over",
        "assert_commit_identity",
        "build_checklist",
        "copy2",
        "detail",
        "echo",
        "join",
        "mkdir",
        "move_clone",
        "now",
        "open",
        "parent",
        "passed",
        "path",
        "returncode",
        "rmtree",
        "row",
        "run",
        "source",
        "stderr",
        "stdout",
        "strftime",
        "strip",
        "write",
    }
)
_REPLACE_PINNED_FREE_NAMES = frozenset(
    {
        "RuntimeError",
        "bool",
        "frozenset",
        "int",
        "str",
        "tuple",
    }
)
_REPLACE_PINNED_IMPORTS = frozenset(
    {
        "__future__.annotations",
        "collections.abc.Callable",
        "collections.abc.Mapping",
        "collections.abc.Sequence",
        "datetime.UTC",
        "datetime.datetime",
        "pathlib.Path",
        "scripts.purge.adopt",
        "scripts.purge.preflight.Quiescence",
        "scripts.purge.preflight.gate",
        "scripts.purge.rewrite.assert_fresh_clone",
        "scripts.purge.verify.RowResult",
        "scripts.purge.verify.check_exactly_one_commit_reachable",
        "scripts.purge.verify.check_metadata_clean",
        "scripts.purge.verify.check_no_token_in_any_commit_message",
        "scripts.purge.verify.check_no_token_in_path_or_blob",
        "scripts.purge.verify.check_refs_clean",
        "scripts.purge.verify.check_tree_identity",
        "shutil",
        "subprocess",
        "tests._forbidden_strings.ForbiddenStrings",
        "tests._forbidden_strings.matches",
        "typer",
    }
)


def _replace_arm_a_surface_hits(tree: ast.AST) -> list[str]:
    found_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    bound = _replace_bound_names(tree)
    found_free_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    } - bound
    found_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                found_imports.add(f"{module}.{alias.name}")

    hits: list[str] = []
    for label, found, pinned in (
        ("attr", found_attrs, _REPLACE_PINNED_ATTRS),
        ("free-name", found_free_names, _REPLACE_PINNED_FREE_NAMES),
        ("import", found_imports, _REPLACE_PINNED_IMPORTS),
    ):
        for item in sorted(found ^ pinned):
            hits.append(f"surface-{label}:{item}")
    return hits


# -- Arm B: argument pinning for the module's admitted effectful names ------
#
# `subprocess.run`, `shutil.rmtree`, `shutil.copy2`, `adopt.move_clone`,
# `Path.open`, the open file handle's `write`, and `Path.mkdir` are the
# module's calls that touch the filesystem or spawn a process. Each element
# of an argv (or a non-string argument) is represented by its own literal
# value when it is a string constant, and by its *unparsed source text*
# otherwise -- so `str(repo)` and `str(repo_root)` are two distinct,
# non-colliding shapes, which is what lets this arm literally discriminate
# "repo_root never appearing as a -C target" rather than only discriminating
# on argv length and the constant positions.

_EFFECTFUL_ATTRS = frozenset(
    {"run", "rmtree", "copy2", "move_clone", "open", "write", "mkdir"}
)


def _elt_repr(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


_PINNED_RUN_ARGV_SHAPES: frozenset[tuple[int, tuple[str, ...]]] = frozenset(
    {
        (6, ("git", "-C", "str(repo)", "remote", "remove", "origin")),
        # `cat-file -e`, not `rev-parse --verify --quiet`: the latter
        # validates only the SHAPE of a 40-hex id and exits 0 for an object
        # that does not exist (measured, git 2.54.0), which would report a
        # corrupted archive readable at the last gate before the remote is
        # deleted. Narrowing this shape is a strengthening of the check, not
        # a widening of the allowlist.
        (
            6,
            (
                "git",
                "-C",
                "str(archive_dir)",
                "cat-file",
                "-e",
                "old_tip_commit",
            ),
        ),
        (5, ("git", "-C", "str(archive_dir)", "fsck", "--connectivity-only")),
    }
)
_PINNED_RUN_CALL_COUNT = 3

_PINNED_RMTREE_FIRST_ARG = frozenset({"scratch_clone_dir"})
_PINNED_RMTREE_CALL_COUNT = 1

_PINNED_COPY2_ARGS = frozenset({("item.source", "item.path")})
_PINNED_COPY2_CALL_COUNT = 1

_PINNED_MOVE_CLONE_ARGS = frozenset(
    {
        ("old_git_dir", "archive_dir"),
        ("scratch_clone_dir / '.git'", "repo_root / '.git'"),
    }
)
_PINNED_MOVE_CLONE_CALL_COUNT = 2

# `_append_certified_tip_line`'s `log.open("a")` -- the mode distinguishes
# the legitimate append from a truncating `"w"` open, which is the shape the
# "quietly destructive" finding demonstrated leaves the module green with no
# other pin catching it.
_PINNED_OPEN_RECEIVERS = frozenset({"log"})
_PINNED_OPEN_MODES = frozenset({"a"})
_PINNED_OPEN_CALL_COUNT = 1

# `handle.write(line)`, the one write the append helper performs.
_PINNED_WRITE_CALL_COUNT = 1

# `item.path.parent.mkdir(parents=True, exist_ok=True)` in the carry-over
# copy loop.
_PINNED_MKDIR_RECEIVERS = frozenset({"item.path.parent"})
_PINNED_MKDIR_CALL_COUNT = 1


def _replace_arm_b_argument_hits(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    run_shapes: set[tuple[int, tuple[str, ...]]] = set()
    run_call_count = 0
    rmtree_first_args: set[str] = set()
    rmtree_call_count = 0
    copy2_args: set[tuple[str, ...]] = set()
    copy2_call_count = 0
    move_clone_args: set[tuple[str, ...]] = set()
    move_clone_call_count = 0
    open_receivers: set[str] = set()
    open_modes: set[str] = set()
    open_call_count = 0
    write_call_count = 0
    mkdir_receivers: set[str] = set()
    mkdir_call_count = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr == "run":
            run_call_count += 1
            first_arg = node.args[0] if node.args else None
            if isinstance(first_arg, ast.List):
                run_shapes.add(
                    (len(first_arg.elts), tuple(_elt_repr(e) for e in first_arg.elts))
                )
            else:
                hits.append("subprocess-run-non-list-argv")
        elif attr == "rmtree":
            rmtree_call_count += 1
            first_arg = node.args[0] if node.args else None
            rmtree_first_args.add(_elt_repr(first_arg) if first_arg else "<missing>")
        elif attr == "copy2":
            copy2_call_count += 1
            copy2_args.add(tuple(_elt_repr(a) for a in node.args))
        elif attr == "move_clone":
            move_clone_call_count += 1
            move_clone_args.add(tuple(_elt_repr(a) for a in node.args))
        elif attr == "open":
            open_call_count += 1
            open_receivers.add(ast.unparse(node.func.value))
            first_arg = node.args[0] if node.args else None
            open_modes.add(_elt_repr(first_arg) if first_arg else "<missing>")
        elif attr == "write":
            write_call_count += 1
        elif attr == "mkdir":
            mkdir_call_count += 1
            mkdir_receivers.add(ast.unparse(node.func.value))

    if run_shapes and run_shapes != _PINNED_RUN_ARGV_SHAPES:
        for shape in sorted(run_shapes - _PINNED_RUN_ARGV_SHAPES, key=repr):
            hits.append(f"subprocess-run-argv:{shape!r}")
    if run_call_count and run_call_count != _PINNED_RUN_CALL_COUNT:
        hits.append(f"subprocess-run-call-count:{run_call_count}")

    if rmtree_first_args and rmtree_first_args != _PINNED_RMTREE_FIRST_ARG:
        for arg in sorted(rmtree_first_args - _PINNED_RMTREE_FIRST_ARG):
            hits.append(f"shutil-rmtree-arg:{arg}")
    if rmtree_call_count and rmtree_call_count != _PINNED_RMTREE_CALL_COUNT:
        hits.append(f"shutil-rmtree-call-count:{rmtree_call_count}")

    if copy2_args and copy2_args != _PINNED_COPY2_ARGS:
        for args in sorted(copy2_args - _PINNED_COPY2_ARGS, key=repr):
            hits.append(f"shutil-copy2-args:{args!r}")
    if copy2_call_count and copy2_call_count != _PINNED_COPY2_CALL_COUNT:
        hits.append(f"shutil-copy2-call-count:{copy2_call_count}")

    if move_clone_args and move_clone_args != _PINNED_MOVE_CLONE_ARGS:
        for args in sorted(move_clone_args - _PINNED_MOVE_CLONE_ARGS, key=repr):
            hits.append(f"adopt-move_clone-args:{args!r}")
    if move_clone_call_count and move_clone_call_count != _PINNED_MOVE_CLONE_CALL_COUNT:
        hits.append(f"adopt-move_clone-call-count:{move_clone_call_count}")

    if open_receivers and open_receivers != _PINNED_OPEN_RECEIVERS:
        for receiver in sorted(open_receivers - _PINNED_OPEN_RECEIVERS):
            hits.append(f"path-open-receiver:{receiver}")
    if open_modes and open_modes != _PINNED_OPEN_MODES:
        for mode in sorted(open_modes - _PINNED_OPEN_MODES):
            hits.append(f"path-open-mode:{mode}")
    if open_call_count and open_call_count != _PINNED_OPEN_CALL_COUNT:
        hits.append(f"path-open-call-count:{open_call_count}")

    if write_call_count and write_call_count != _PINNED_WRITE_CALL_COUNT:
        hits.append(f"handle-write-call-count:{write_call_count}")

    if mkdir_receivers and mkdir_receivers != _PINNED_MKDIR_RECEIVERS:
        for receiver in sorted(mkdir_receivers - _PINNED_MKDIR_RECEIVERS):
            hits.append(f"path-mkdir-receiver:{receiver}")
    if mkdir_call_count and mkdir_call_count != _PINNED_MKDIR_CALL_COUNT:
        hits.append(f"path-mkdir-call-count:{mkdir_call_count}")

    # Explicit, redundant-by-design check for the finding's own wording:
    # `repo_root` (in any of its unparsed spellings) must never be the
    # argument immediately following a literal "-C" in any subprocess.run
    # argv, recognised shape or not -- an unrecognised shape is already
    # flagged above, but this makes the "-C target" claim a direct
    # assertion rather than an inference from shape-set membership.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "run":
            continue
        first_arg = node.args[0] if node.args else None
        if not isinstance(first_arg, ast.List):
            continue
        elts = first_arg.elts
        for index, elt in enumerate(elts[:-1]):
            if isinstance(elt, ast.Constant) and elt.value == "-C":
                target_repr = _elt_repr(elts[index + 1])
                if "repo_root" in target_repr:
                    hits.append(f"subprocess-run-dash-C-repo_root:{target_repr}")

    return hits


# -- Arm C: position pinning (closes aliasing) -------------------------------


def _replace_arm_c_position_hits(tree: ast.AST) -> list[str]:
    call_func_ids = {
        id(call.func) for call in ast.walk(tree) if isinstance(call, ast.Call)
    }
    hits: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in _EFFECTFUL_ATTRS
            and id(node) not in call_func_ids
        ):
            hits.append(f"bare-reference:{node.attr}")
    return hits


def _replace_removal_call_names(source: str) -> list[str]:
    """Walk `source`'s AST and return a label for every shape Arms A, B and
    C (above) flag. This holds for `scripts/purge/replace.py` exactly as it
    stands at this task's remediation (see the module-level scope note
    above `_replace_bound_names`)."""
    tree = ast.parse(source)
    hits: list[str] = []
    hits.extend(_replace_arm_a_surface_hits(tree))
    hits.extend(_replace_arm_b_argument_hits(tree))
    hits.extend(_replace_arm_c_position_hits(tree))
    return hits


def _real_replace_module_source() -> str:
    return Path(inspect.getfile(replace_module)).read_text(encoding="utf-8")


def _replace_planted(snippet: str) -> str:
    """The real module's own source with `snippet` appended at module level
    -- see `tests/purge/test_adopt.py::_planted` for why the snippet is
    always appended to a full copy rather than tested in isolation (Arm A's
    surface check is a symmetric difference, so a bare snippet always
    reports non-empty regardless of content)."""
    return _real_replace_module_source() + "\n" + snippet


def test_replace_removal_call_detector_reports_the_three_demonstrated_evasions() -> (
    None
):
    """Positive control for `_replace_removal_call_names`: the three shapes
    the reviewer demonstrated leave the full suite green must all be
    reported by the detector."""
    assert (
        _replace_removal_call_names(
            _replace_planted(
                "import subprocess\n"
                "def _evasion_clean(repo_root):\n"
                "    subprocess.run(['git', '-C', str(repo_root), 'clean', '-xdff'])\n"
            )
        )
        != []
    )
    assert (
        _replace_removal_call_names(
            _replace_planted(
                "import shutil\n"
                "def _evasion_move(repo_root, decoy):\n"
                "    shutil.move(str(repo_root), str(decoy))\n"
            )
        )
        != []
    )
    assert (
        _replace_removal_call_names(
            _replace_planted(
                "def _quietly_destructive(old_git_dir):\n"
                '    with (old_git_dir / "packed-refs").open("w") as handle:\n'
                '        handle.write("")\n'
            )
        )
        != []
    )


def test_replace_module_source_contains_no_undeclared_effectful_call() -> None:
    """`replace.py`'s effectful surface is exactly what design.md
    `#### HistoryReplacement` admits: the three `subprocess.run` argv
    shapes, the one `shutil.rmtree` call on `scratch_clone_dir`, the one
    `shutil.copy2` call in the carry-over loop, the two `adopt.move_clone`
    calls that perform the swap, the one `log.open("a")` / `handle.write`
    pair in `_append_certified_tip_line`, and the one
    `item.path.parent.mkdir` in the carry-over copy loop -- every other
    shape Arms A, B and C can see is flagged."""
    source = _real_replace_module_source()
    assert source, "the walk is looking at the wrong file"
    hits = _replace_removal_call_names(source)
    assert hits == [], (
        "replace.py's effectful surface or call sites changed -- re-verify "
        "by hand and update the pin"
    )


def test_replace_arm_a_vacuity_emptying_pinned_attrs_reds_the_clean_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_replace_module_source()
    assert _replace_removal_call_names(source) == []  # false precondition confirmed

    monkeypatch.setattr(sys.modules[__name__], "_REPLACE_PINNED_ATTRS", frozenset())

    assert _replace_removal_call_names(source) != []


def test_replace_arm_b_vacuity_blanking_the_pinned_run_shapes_reds_the_clean_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_replace_module_source()
    assert _replace_removal_call_names(source) == []  # false precondition confirmed

    monkeypatch.setattr(sys.modules[__name__], "_PINNED_RUN_ARGV_SHAPES", frozenset())

    assert _replace_removal_call_names(source) != []


def test_replace_arm_b_vacuity_dropping_the_move_clone_call_count_reds_the_clean_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_replace_module_source()
    assert _replace_removal_call_names(source) == []  # false precondition confirmed

    monkeypatch.setattr(sys.modules[__name__], "_PINNED_MOVE_CLONE_CALL_COUNT", 0)

    assert _replace_removal_call_names(source) != []


def test_replace_arm_c_vacuity_emptying_effectful_attrs_undetects_a_bare_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _replace_planted("_run = subprocess.run\n")
    assert _replace_removal_call_names(fixture) != []  # true before the mutation

    monkeypatch.setattr(sys.modules[__name__], "_EFFECTFUL_ATTRS", frozenset())

    assert _replace_removal_call_names(fixture) == []
