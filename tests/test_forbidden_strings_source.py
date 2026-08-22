"""Task 2.3 (encumbered-content-purge, Req 2.3, 11.7): the out-of-repository
forbidden-string source file itself is assembled by that task, at a path
outside the repository working tree, in the format
`tests/_forbidden_strings.py` reads (design.md `#### ForbiddenStrings`).

This module holds none of the forbidden strings. It reads only from the file
named by `FITDOCS_FORBIDDEN_STRINGS`, exactly like `tests/_forbidden_strings.py`
itself. When that variable is unset -- the default posture Req 11.8 documents
-- every check below skips rather than passing vacuously; a session with the
variable exported observes them execute.

Distinct from `tests/test_forbidden_strings.py`, which pins the loader's own
behaviour against synthetic sources: this module is the liveness check for
task 2.3's real, assembled source. Since task 6.3 the liveness probe runs
against this repository's full HISTORY rather than its current tracked
tree -- task 6.3's own job is to drive every tracked-tree occurrence to
zero, which makes a tracked-tree probe assert the opposite of liveness from
that task forward (`_history_contains` below).

**Re-based again, still within task 6.3, onto an era-aware posture.**
`_history_contains` is `git log --all -S<value>` -- a pickaxe over blob
CONTENT that reports commits where the value's occurrence COUNT changed.
That is a correct liveness probe only while some reachable blob still
carries the value. The history replacement (design.md
`#### HistoryReplacement`) redacts every `token`-category occurrence from
every reachable blob at every commit, by carrying no pre-existing commit at
all rather than by rewriting each one; once that has run, the count is 0 at every
commit and never changes, so `git log --all -S<value>` legitimately reports
nothing for every `token`-category value -- not because the probe is
broken, but because it is finally doing its job (Req 11.1, Req 11.2's
identifying-token clause).

**`path`-category values are a different question, deliberately not made
part of this claim (round-2 remediation).** The rewrite's `--invert-paths`
directives remove the *blobs at that path*; they do not, and are not
required to, scrub every textual *mention* of that path string out of every
OTHER file's historical blobs, and no `--replace-text` rule targets a
`path`-category value unless it happens to also be an identifying token.
Measured directly in a real rewritten clone (round-2 review): all four
`token`-category values and four of five `path`-category values go to 0
history occurrences, but the fifth -- the prior rewrite map's
`docs/reference/`-rooted path, which carries no identifying token -- still
returns commits from `git log --all -S<value>` after a spec-conformant
rewrite. Req 9.7.7 requires that path gone from the **working tree**; Req
11.2 governs paths *containing* an identifying token; a token-free path
string surviving in blob content elsewhere in history violates neither. So
every post-rewrite check below -- the era-aware assertions in
`test_forbidden_string_source_is_live_when_supplied` and the pairing check
described next -- is scoped to `by_category["token"]` only. Asserting the
same absence over `path`-category values would accuse a spec-conformant
rewrite of being incomplete.

A version of this test that asserted `_history_contains` must find
something, unconditionally, for a `token`-category value would therefore
assert something true exactly when Req 11.1/11.2 is FALSE, and would
hard-fail the moment the history replacement actually lands -- during task
8.3's supplied-source acceptance run, after the original (pre-replacement)
repository is already gone. That is the exact failure shape task 6.3 exists
to eliminate, so this module now reads an era signal (`_is_post_replacement_era`
below) and takes a different, explicit posture in each era:

- **Pre-replacement** (the era signal absent): a history occurrence MUST be
  found for at least one value in each category -- hard failure, not a
  skip, if not. This is the posture task 2.3 through 7.5 run under. Both
  categories are still checked here: pre-replacement, every value's history
  presence is real and checkable, and the `path`-category carve-out above
  applies only to the post-replacement side.
- **Post-replacement** (the era signal present): a history occurrence of a
  `token`-category value is a legitimate, expected absence -- Req 11.1's
  success condition, not a failure -- so this reports a **named**
  `pytest.skip` stating which era it detected and why, never a silent pass.
  Paired with an independent check (mirroring
  `tests/purge/test_rewrite_map_extraction.py::
  test_extraction_matches_the_real_prior_map_row_count_measured_
  independently`'s `reachable`/`text` pairing) that a `token`-category value
  STILL showing a history occurrence in this era is a hard failure, not
  folded into the same skip.

**What the era signal changing and `_history_contains` breaking cannot be
told apart from.** Mutating `_history_contains` to `return False`
unconditionally, run against a real replaced repository, makes the pairing
check vacuously pass (`not still_present` is trivially true when nothing is
ever reported present) and the run **skips** -- the same outcome a correctly
working probe produces in that era. A broken `_history_contains` and a
correctly working one are indistinguishable from this module's outcome alone
once the era signal is true, because the era signal is what selects the skip
branch, not `_history_contains`'s own result. What genuinely IS
distinguishable, and is what the pairing check actually buys: a
`_history_contains` that spuriously returns `True` (e.g. a broken argument
vector that stops scoping to `--all` and picks up an unrelated ref) surfaces
as a hard failure in this era, rather than silently passing. The asymmetry is
real -- false positives are caught, false negatives are not,
post-replacement -- and is stated as such rather than claimed away.

**Detection given up (Req 11.9), stated rather than left implicit.** Once
the era signal is present, this module gives up verifying, via `git log
--all -S`, that any specific `token`-category value WAS EVER present in
this repository's history. That fact stops being checkable from inside the
replaced repository by construction (Req 11.1's whole point is that it no
longer is), and this module does not attempt to substitute a weaker check
in its place -- the skip states the gap rather than quietly narrowing what
"live" means. `test_forbidden_string_source_is_live_when_supplied`'s
category-shape assertions (non-empty `token`/`path` categories, and
per-category count floors) remain the only checks this module still runs
post-replacement: they confirm the supplied SOURCE still carries real
values, not that this repository's history still carries them.

**Era signal, re-scoped at encumbered-content-purge task 7.2 for Amendment
1's fresh-root replacement mechanism (design.md `#### HistoryReplacement`,
`#### MachineryRetirement` Phase R0).** The prior two-signal mechanism (an
in-git-dir `git filter-repo` commit-map artifact, ORed with a tracked
provenance-record section) is gone, not merely re-implemented, because both
of the prior signal's premises are gone with it: `git filter-repo`
in-place rewrite is retired unused (design.md Decision 7; no tool in this
repository can ever write `<git-dir>/filter-repo/commit-map` again, so a
signal keyed on that path can never fire again), and the provenance record's
own replacement section (`## 3.`) is written by task 9.2 -- strictly AFTER
task 8.3 runs this module with the source supplied, so a signal that depends
on that section having landed would read every post-replacement run at 8.3
as pre-replacement.

The replacement-era signal reads **the repository's sole parentless
commit** (`_root_commit_ids`, `git rev-list --all --max-parents=0`): under
the replacement, history is exactly one commit with no parent
(design.md `#### HistoryReplacement`, step 3 -- `git commit-tree
<certified-tip-tree>` with no parent), and its message is fixed by that
design to state that it is the initial commit of the published history and
to name `docs/reference/history-rewrites.md` as the record of what was
removed and why -- a shape no pre-replacement ROOT commit carries, because
this repository's real, sole pre-replacement root (measured directly:
`git rev-list --all --max-parents=0` against this worktree returns exactly
one id, whose message is the actual "Initial repo setup ..." commit and does
not name the provenance record) was never written to say that. This is a
claim about the ROOT commit's message specifically, not about every commit
in this repository's history -- a handful of ordinary, non-root commits in
this very spec's history DO mention `docs/reference/history-rewrites.md` in
their own messages (measured: 2, discussing the file itself), which is
exactly why the signal below reads the sole root's message and no other
commit's -- see
`test_a_non_root_commit_naming_the_record_does_not_signal_post_replacement`.
`_is_post_replacement_era` is true only when EXACTLY ONE
parentless commit exists AND that commit's message names the provenance
record -- not "any root commit names it": a repository with more than one
parentless commit (an unusual but real git shape -- unrelated grafted
histories, for instance) is never read as the replacement, even if one of
its several roots happens to name the record, because the replacement's own
construction guarantees exactly one. Present in every clone, including a
plain `git clone` (task 8.4): a commit's message is ordinary reachable
history, not `.git`-directory-resident state a clone leaves behind, so
unlike the retired commit-map signal this one needs no second, worktree-local
fallback.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests._forbidden_strings import ENV_VAR, load


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _categorized_entries(source: Path) -> dict[str, tuple[str, ...]]:
    """Parse the source file's category prefixes directly.

    `tests/_forbidden_strings.py`'s own `_parse` deliberately discards the
    category -- design.md specifies `ForbiddenStrings.values` as a flat
    tuple -- so a per-category probe cannot be built by going through
    `load()`. This duplicates only the category split, test-only, and never
    touches the shared loader.
    """
    by_category: dict[str, list[str]] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        category, separator, rest = stripped.partition("\t")
        if not separator:
            # An uncategorised plain line -- not part of either category's
            # probe population.
            continue
        by_category.setdefault(category, []).append(rest)
    return {category: tuple(values) for category, values in by_category.items()}


def _history_contains(repo_root: Path, value: str) -> bool:
    """Whether `value`'s occurrence count changed in some blob at some
    commit reachable from any ref (`git log --all -S<value>`) -- i.e.
    whether `value` was ever added or removed anywhere in this
    repository's history.

    Re-based here (encumbered-content-purge task 6.3) from a tracked-tree
    probe to a full-history probe: task 6.3's own job is to drive every
    `path`/`token`-category value's occurrence in tracked file CONTENT to
    zero, so a probe against the current tracked tree can no longer
    demonstrate liveness -- it would prove the opposite of what task 2.3's
    observable wants. Before the history replacement runs, every one of
    these values' historical presence (the material task 3.1 deleted, the
    tokens task 3.1-3.12 redacted) is still reachable through history, which
    is what this probes instead: still a REAL, independent probe -- not a
    second read of the flat `values` tuple -- because it goes around `git
    log` rather than back through the loader.

    `-S` (not `-G`) is load-bearing: it is a literal pickaxe by default (no
    metacharacter risk, unlike `-G`'s regex mode), and it matches a commit
    where the string's occurrence COUNT changed -- exactly "added or
    removed somewhere" -- rather than `-G`'s "this pattern appears in any
    changed line of the diff", which can also fire on an unrelated line
    that merely sits next to a real change.
    """
    result = subprocess.run(
        ["git", "log", "--all", "-S", value, "--oneline"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


_PROVENANCE_RECORD_RELPATH = Path("docs/reference/history-rewrites.md")
"""The provenance record's path, relative to the repository root -- what the
fixed root commit message names (design.md `#### HistoryReplacement`, "The
root commit message is fixed by this design ... it states ... that
`docs/reference/history-rewrites.md` is the record of what was removed and
why"). The era signal below checks for this exact string inside the sole
parentless commit's message, never for the record's own tracked content --
unlike the retired `_provenance_record_signals_post_rewrite`, this does not
depend on that file's `## 3.` section having landed (task 9.2), only on the
root commit itself existing (task 8.2, strictly before 9.2)."""


def _root_commit_ids(repo_root: Path) -> tuple[str, ...]:
    """Every commit reachable from any ref with NO parent
    (`git rev-list --all --max-parents=0`) -- this repository's root
    commit(s).

    Pre-replacement, this repository has always had exactly one (its own
    actual first commit, `git rev-list --all --max-parents=0` measured
    directly against this worktree at the time this was written: exactly one
    id, whose message is this repository's real "Initial repo setup ..."
    commit and does not name the provenance record). Under the replacement
    (design.md `#### HistoryReplacement`, step 3: `git commit-tree
    <certified-tip-tree>` with no parent), the ENTIRE history becomes a
    single commit, so this also returns exactly one there -- but a fresh
    clone's shape is not asserted here as a general git property, only
    measured for this repository, which is why
    `_sole_root_commit_names_the_provenance_record` below treats anything
    other than exactly one root as "not the replacement shape" rather than
    picking one arbitrarily. Returns an empty tuple, never raising, when the
    `git` invocation itself fails (e.g. `repo_root` is not a git repository
    at all) -- the same safe-direction posture the retired commit-map signal
    took for a broken `git` binary."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-list", "--all", "--max-parents=0"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ()
    return tuple(result.stdout.split())


def _commit_message(repo_root: Path, commit_id: str) -> str:
    """`commit_id`'s full message (`git log -1 --format=%B`), or the empty
    string if the `git` invocation fails -- the safe direction, since an
    empty message can never contain `_PROVENANCE_RECORD_RELPATH`."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "-1", "--format=%B", commit_id],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def _sole_root_commit_names_the_provenance_record(repo_root: Path) -> bool:
    """`True` only when `repo_root` has EXACTLY ONE parentless commit AND
    that commit's message names the provenance record.

    Both halves are load-bearing. "Exactly one" is the shape
    `#### HistoryReplacement` step 3 constructs by design -- checking only
    "some root names it" would also fire on an unrelated repository shape
    (more than one parentless commit, one of which happens to mention the
    record's path in prose) that the replacement never produces. "Names the
    provenance record" is what distinguishes the replacement's fixed root
    message from THIS repository's own actual first commit, which is also a
    sole parentless commit and does not name it."""
    roots = _root_commit_ids(repo_root)
    if len(roots) != 1:
        return False
    return str(_PROVENANCE_RECORD_RELPATH) in _commit_message(repo_root, roots[0])


def _is_post_replacement_era(repo_root: Path) -> bool:
    """Whether `repo_root`'s history has already been replaced
    (design.md `#### HistoryReplacement`) by the fresh-root mechanism.

    A single signal now, not two ORed together: the retired commit-map
    signal's premise -- a local `git filter-repo` invocation leaving an
    artifact inside `.git/` -- cannot occur under Decision 7's fresh-root
    mechanism (no `git filter-repo` invocation writes history at all), and
    the retired provenance-record-section signal's premise -- that task 9.2
    has already appended `## 3.` -- is false for the entire span between
    task 8.2 (the replacement itself) and task 9.2, and task 8.3 (which runs
    this module with the source supplied) falls inside exactly that span --
    which is exactly the gap this re-scoping exists to close. See the module
    docstring for the full re-scoping rationale."""
    return _sole_root_commit_names_the_provenance_record(repo_root)


def test_forbidden_string_source_unset_skips_rather_than_passing_vacuously() -> None:
    # The one legitimate silent outcome (Req 11.8): confirms the negative
    # space of the rest of this module's checks is a skip, not a pass, when
    # the maintainer has not supplied the source this run.
    if os.environ.get(ENV_VAR) is not None:
        pytest.skip(f"{ENV_VAR} is set this run; the unset case is exercised elsewhere")
    repo_root = _repo_root()

    assert load(repo_root) is None


def test_forbidden_string_source_is_live_when_supplied() -> None:
    if os.environ.get(ENV_VAR) is None:
        pytest.skip(
            f"{ENV_VAR} is unset; task 2.3's source liveness is unverified this run "
            "-- this is the documented default posture (Req 11.8), not a failure"
        )

    repo_root = _repo_root().resolve()
    forbidden_strings = load(repo_root)

    assert forbidden_strings is not None
    assert len(forbidden_strings.values) > 0

    # The resolved source lies outside the repository working tree -- the
    # same check `load()` itself enforces, re-asserted here against the real
    # source rather than a synthetic one.
    assert not forbidden_strings.source.is_relative_to(repo_root)
    assert forbidden_strings.source != repo_root

    by_category = _categorized_entries(forbidden_strings.source)
    assert set(by_category) >= {"token", "path"}
    assert by_category["token"]
    assert by_category["path"]

    # Shape floors, not just non-empty (task 6.3 remediation): the supplied
    # source moved out-of-repository at task 2.3, so shrinking either
    # category no longer requires a tracked-file edit a review would catch
    # -- before task 6.3 the needle set was a literal tuple IN this
    # repository (`tests/purge/test_tree_removal.py`'s and this module's own
    # git history), so narrowing it required an in-repo diff; today it is
    # silently mutable from outside the repository entirely. Truncating
    # `by_category["token"]`/`["path"]` to a strict, still-non-empty subset
    # left every prior assertion here green (both category-non-empty checks
    # and, post-rewrite, the reachability checks below), so a count floor is
    # the only remaining guard against source erosion. Measured directly
    # against the real, currently-supplied source (independent of this
    # module's own logic): 4 `token`-category entries, 5 `path`-category
    # entries -- also recorded in
    # `tests/purge/test_rewrite_map_extraction.py::_real_prior_map_path`'s
    # docstring (5 `path` entries, suffixes `.md`:1, `.csv`:2, none:1,
    # `.tsv`:1) and in `tests/purge/test_tree_removal.py::
    # _removed_file_paths`'s docstring, which state the same `path`-category
    # shape independently.
    assert len(by_category["token"]) >= 4, (
        f"only {len(by_category['token'])} token-category entries in the "
        "supplied source, expected at least 4 -- the source may have eroded"
    )
    assert len(by_category["path"]) >= 5, (
        f"only {len(by_category['path'])} path-category entries in the "
        "supplied source, expected at least 5 -- the source may have eroded"
    )

    # Deliberate probe, Req 2.3/11.7's stated observable: at least one entry
    # of EACH category is proven to have been added or removed somewhere in
    # this repository's history, so the file is proven live rather than
    # merely present.
    #
    # Re-based here (encumbered-content-purge task 6.3) onto full HISTORY
    # (`_history_contains`) rather than the current tracked tree. The
    # tracked-tree version of this probe was live from task 2.3 (which runs
    # while the material still sits in the tracked tree) through task 6.2:
    # the path category was checked against the working tree's *filesystem*
    # before task 3.1 deleted the removed paths, then against tracked file
    # CONTENT (every fragment still cited as text somewhere -- the
    # stale-pointer citations task 3.2 through 3.12 record and redact) after
    # 3.1. Task 6.3's own job is to drive every one of those content
    # citations to zero (that is Req 3.3/3.4/11.7/11.8/11.10's point), which
    # makes a tracked-CONTENT probe assert the opposite of what it is meant
    # to prove from this task forward.
    #
    # Re-based AGAIN, still within task 6.3, onto an era-aware posture (see
    # module docstring): the history replacement (design.md
    # `#### HistoryReplacement`) is what finally drives every reachable
    # blob's TOKEN-category occurrence count to zero, at which point
    # `_history_contains` legitimately reports nothing for every
    # `token`-category value -- that is Req 11.1/11.2 succeeding, not this
    # probe breaking. `path`-category values carry no such guarantee (module
    # docstring) and are deliberately excluded from every post-replacement
    # assertion below. `_is_post_replacement_era` is the independent signal
    # that tells pre- from post-replacement apart.
    if _is_post_replacement_era(repo_root):
        # Post-replacement: absence is expected, for `token`-category values
        # only. Paired with an independent check (mirrors
        # `test_rewrite_map_extraction.py`'s `reachable`/`text` pairing)
        # that no `token`-category value STILL shows a history occurrence in
        # this era -- if one does, either the replacement did not actually
        # redact it or the era signal is a false positive, and that must
        # fail loudly here, never disappear into this skip. `path`-category
        # values are excluded from this pairing on purpose (module
        # docstring): the replacement is not required to, and measurably
        # does not, erase every textual mention of a token-free path
        # fragment from every other file's historical blob content.
        still_present = tuple(
            value
            for value in by_category["token"]
            if _history_contains(repo_root, value)
        )
        assert not still_present, (
            "post-replacement era detected but the following supplied-source "
            f"token-category value(s) still show a history occurrence: "
            f"{still_present!r} -- either the replacement did not actually "
            "redact these values, or the era signal is a false positive; "
            "this must fail, not silently skip"
        )
        pytest.skip(
            "post-replacement era detected (this repository's sole "
            "parentless commit names the provenance record), meaning the "
            "history replacement has already run -- Req 11.1/11.2 require "
            "every reachable blob's TOKEN-category occurrence count to be "
            "zero at this point, so `git log --all -S<value>` legitimately "
            "finds nothing for every token-category value (this says "
            "nothing about path-category values, which the replacement is "
            "not required to scrub from other files' historical blob "
            "content -- see module docstring); this module's "
            "history-liveness detection (Req 11.9: given up, not silently "
            "narrowed) ends here -- the category-shape assertions above "
            "remain the only post-replacement check that the supplied "
            "source still holds real values"
        )

    assert any(_history_contains(repo_root, token) for token in by_category["token"])
    assert any(
        _history_contains(repo_root, fragment) for fragment in by_category["path"]
    )


# --- Era mechanism pinning, re-scoped at task 7.2 for the fresh-root
# replacement (design.md `#### HistoryReplacement`, `#### MachineryRetirement`
# Phase R0) -----------------------------------------------------------------
#
# `_root_commit_ids`, `_commit_message`,
# `_sole_root_commit_names_the_provenance_record` and
# `_is_post_replacement_era` were referenced nowhere outside their own module
# and touched by neither `test_forbidden_string_source_*` test above -- both
# reach them only via `_is_post_replacement_era(repo_root)` against THIS
# repository's own, currently pre-replacement, state, which never exercises
# the post-replacement branch. The tests below construct real `tmp_path` git
# repositories (`git init`, real commits) so the post-replacement branch, the
# "sole" requirement, and the "root only, not any commit" requirement are
# each exercised directly, without depending on this repository's own era
# ever flipping.


def _init_repo_with_root_commit(
    repo: Path, message: str, filename: str = "file.txt"
) -> None:
    """A real `git init` at `repo`, with one commit -- `repo`'s sole root."""
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "era-fixture@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Era Fixture"],
        check=True,
        capture_output=True,
    )
    (repo / filename).write_text("content\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", filename], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
    )


def _add_child_commit(repo: Path, message: str, filename: str = "file2.txt") -> None:
    """A second commit on `repo`'s current branch, with the root as its
    parent -- for pinning that the era signal reads the ROOT's message, not
    any reachable commit's."""
    (repo / filename).write_text("more\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", filename], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
    )


def _add_orphan_root_commit(
    repo: Path, message: str, filename: str = "other.txt"
) -> None:
    """A SECOND, unrelated root commit in `repo`, on a new branch with no
    history in common with the first -- `git checkout --orphan` -- so `repo`
    ends up with two parentless commits reachable from `--all`."""
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "--orphan", "second-root"],
        check=True,
        capture_output=True,
    )
    (repo / filename).write_text("other\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", filename], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
    )


def test_root_commit_ids_finds_exactly_one_root_in_this_repository() -> None:
    # A real, non-brittle fact about this repository regardless of era: it
    # has always had exactly one commit with no parent, before AND after the
    # replacement (design.md `#### HistoryReplacement` step 3 forges exactly
    # one root, and this repository has never had more than one). Unlike an
    # assertion on WHICH era that root reads as, this one does not flip when
    # the replacement lands, so it stays a safe permanent pin.
    assert len(_root_commit_ids(_repo_root())) == 1


def test_root_commit_ids_returns_empty_for_a_non_git_directory(tmp_path: Path) -> None:
    assert _root_commit_ids(tmp_path) == ()


def test_sole_root_commit_names_the_record_reads_false_for_a_non_git_dir(
    tmp_path: Path,
) -> None:
    # The direct replacement for the retired
    # test_post_rewrite_commit_map_path_absent_file_reads_as_pre_rewrite_era
    # (`tests/purge/test_replacements.py`, deleted in this re-homing): a
    # directory that is not a git repository at all -- `_root_commit_ids`
    # returns `()` here -- must read pre-replacement without raising. This
    # pins `_sole_root_commit_names_the_provenance_record`'s
    # `if len(roots) != 1: return False` guard specifically: a narrower
    # `if len(roots) > 1: return False` mutant lets `len(roots) == 0` fall
    # through to `roots[0]`, which raises `IndexError` on an empty tuple --
    # contradicting this function's own docstring ("Both halves are
    # load-bearing") and `_root_commit_ids`' docstring ("Returns an empty
    # tuple, never raising").
    assert not _sole_root_commit_names_the_provenance_record(tmp_path)
    assert not _is_post_replacement_era(tmp_path)


def test_root_commit_ids_finds_the_sole_root_of_a_synthetic_repository(
    tmp_path: Path,
) -> None:
    _init_repo_with_root_commit(tmp_path, "an ordinary first commit")
    root = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert _root_commit_ids(tmp_path) == (root,)


def test_root_commit_ids_finds_both_roots_of_a_repository_with_an_orphan_branch(
    tmp_path: Path,
) -> None:
    _init_repo_with_root_commit(tmp_path, "first root")
    _add_orphan_root_commit(tmp_path, "second, unrelated root")

    assert len(_root_commit_ids(tmp_path)) == 2


def _add_orphan_root_commit_reachable_only_via_tag(
    repo: Path, message: str, tag: str, filename: str = "tagged.txt"
) -> None:
    """A SECOND, unrelated root commit reachable from NO branch at all --
    only from a lightweight tag -- then the branch that momentarily held it
    is deleted, so `--branches` (and `HEAD`, and `--tags` alone without the
    root branch) cannot see it, while `--all` (which includes tags) can.

    Step 3 fixture (repair round): `_root_commit_ids` uses `git rev-list
    --all --max-parents=0`. Mutating `--all` to `--branches` left the module
    green under every fixture that existed before this one, because both
    prior orphan roots
    (`_add_orphan_root_commit`) were left checked out on ordinary local
    branches -- `--branches` sees them too. This constructs the one shape
    that discriminates: a root reachable ONLY via a ref outside
    `refs/heads/`."""
    original_branch = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "--orphan", "tag-only-root"],
        check=True,
        capture_output=True,
    )
    (repo / filename).write_text("tagged\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", filename], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "tag", tag], check=True, capture_output=True
    )
    # Return to the first root's branch, then delete the transient branch
    # that held the second root -- only the tag keeps it reachable now.
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", original_branch],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "branch", "-D", "tag-only-root"],
        check=True,
        capture_output=True,
    )


def test_root_commit_ids_finds_a_second_root_reachable_only_via_a_tag(
    tmp_path: Path,
) -> None:
    # Step 3 (repair round, findings 2/3/4's Cluster A gap): the second root
    # below is reachable from no branch (`--branches` misses it) and from no
    # single-ref query (`HEAD` misses it too), only from the tag
    # `only-a-tag-reaches-me` -- `--all` is the only flag among the three
    # that can see it. A repository shaped exactly like this, with a second
    # root hidden this way, is what would make `_is_post_replacement_era`
    # read `True` under the `--branches` mutation (only one root visible,
    # matching the replacement's own "exactly one root" shape) even though
    # the real repository has two -- a false replacement detection, which is
    # exactly the failure the module's own "exactly one root" language
    # exists to prevent.
    _init_repo_with_root_commit(tmp_path, "first root")
    _add_orphan_root_commit_reachable_only_via_tag(
        tmp_path, "second root, tag-only", tag="only-a-tag-reaches-me"
    )

    assert len(_root_commit_ids(tmp_path)) == 2
    assert not _is_post_replacement_era(tmp_path)


def test_commit_message_reads_a_real_commits_message(tmp_path: Path) -> None:
    _init_repo_with_root_commit(tmp_path, "a distinctive planted message\n")
    (root,) = _root_commit_ids(tmp_path)

    assert "a distinctive planted message" in _commit_message(tmp_path, root)


def test_commit_message_returns_exactly_the_percent_b_format_no_more(
    tmp_path: Path,
) -> None:
    # Sweep finding: `--format=%B` dropped entirely (bare `git log -1
    # <commit_id>`) still leaves every existing containment-based assertion
    # in this module green, because git's default log format still carries
    # the message text verbatim, merely wrapped in a `commit <hash>` /
    # `Author:` / `Date:` header and re-indented by four spaces -- an `in`
    # check cannot see the difference. Only an EXACT equality against the
    # real `%B` output (measured directly: message text, then a trailing
    # blank line -- `"a distinctive planted message\n\n"`) can. This test
    # kills that mutation; every other assertion in this module legitimately
    # stays containment-based, so this is the sole place that pins the
    # format string's presence.
    _init_repo_with_root_commit(tmp_path, "a distinctive planted message\n")
    (root,) = _root_commit_ids(tmp_path)

    assert _commit_message(tmp_path, root) == "a distinctive planted message\n\n"


def test_commit_message_on_a_child_commit_excludes_the_roots_own_message(
    tmp_path: Path,
) -> None:
    # Sweep finding: dropping `-1` (bare `git log --format=%B <commit_id>`,
    # no count limit) survives every existing fixture, because every
    # existing call site -- both `_sole_root_commit_names_the_provenance_
    # record`'s own call and every direct unit test above -- only ever
    # queries a commit with NO parents (a root), so `git log` already stops
    # after a single commit regardless of `-1`. `_commit_message` is a
    # general two-argument helper, not one hard-coded to roots, so this
    # constructs a repository where the queried commit DOES have an
    # ancestor: without `-1`, `git log --format=%B <child>` walks back
    # through history and would also emit the root's message, which this
    # asserts is absent.
    _init_repo_with_root_commit(tmp_path, "the root's own distinctive message\n")
    _add_child_commit(tmp_path, "the child's own distinctive message\n")
    child = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    message = _commit_message(tmp_path, child)

    assert "the child's own distinctive message" in message
    assert "the root's own distinctive message" not in message


def test_commit_message_returns_empty_string_for_an_unknown_commit_id(
    tmp_path: Path,
) -> None:
    _init_repo_with_root_commit(tmp_path, "an ordinary first commit")

    assert _commit_message(tmp_path, "0" * 40) == ""


def test_root_commit_ids_splits_stdout_on_any_whitespace_not_on_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Step 4 (repair round). Round 3 declared `.split()` -> `.splitlines()`
    # "UNPINNED by construction -- equivalent mutant", on the grounds that no
    # real `git rev-list` output distinguishes them. That claim is false: a
    # blank line in stdout does distinguish them (`"deadbeef\n\n".split()`
    # is `("deadbeef",)`, one root; `.splitlines()` is
    # `["deadbeef", ""]`, two entries, one of them an empty string that is
    # not a valid commit id), and it is also inconsistent with round 3's own
    # position elsewhere in this module -- monkeypatching `subprocess.run` is
    # exactly the argument already used to justify the three fixtures above
    # for the `returncode` guards, applied here to the parsing call instead.
    #
    # Non-vacuity (the general rule in this repair's instructions): the
    # unpatched call against `tmp_path`, a plain (non-git) directory, returns
    # `()`; the patched call returns a real one-element tuple, so `got !=
    # unpatched` is itself part of the pin, and the tuple's LENGTH -- not
    # just its non-emptiness -- is what discriminates `.split()` from
    # `.splitlines()`.
    unpatched = _root_commit_ids(tmp_path)
    assert unpatched == ()

    def _fake_run(
        cmd: Sequence[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=0,
            stdout="deadbeef\n\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    got = _root_commit_ids(tmp_path)
    assert got != unpatched, (
        "the monkeypatch did not change the result -- it may not have been "
        "in effect (e.g. the module resolved a bound `subprocess.run` name "
        "at import time rather than looking it up on the patched module)"
    )
    # `.split()`: one root, "deadbeef". `.splitlines()`: two entries,
    # `["deadbeef", ""]` -- the length assertion is what kills that mutation.
    assert got == ("deadbeef",)


def test_root_commit_ids_discards_stdout_when_the_git_invocation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Findings 2/3 (round 3 remediation), the M9 half: an unknown commit id
    # cannot distinguish "the `returncode != 0` guard fired" from "the guard
    # is gone and `git` simply wrote nothing to stdout for a bad id" --
    # `git rev-list` on an unknown ref writes its diagnostic to STDERR and
    # leaves stdout empty either way, so `tuple(result.stdout.split())` is
    # `()` under both the guarded and the unguarded implementation. The only
    # way to make the guard itself observable is a `git` invocation that
    # fails (nonzero returncode) while somehow still carrying stdout content
    # -- monkeypatching `subprocess.run` is the only way to construct that
    # combination, since a real `git` failure never populates stdout this
    # way.
    #
    # Repair round (rejected three times for a fixture that pinned nothing
    # about the double): `tmp_path` used to be asserted against directly, but
    # `tmp_path` is not a git repository, so the UNPATCHED call also returns
    # `()` -- nothing here proved the monkeypatch ever took effect. This now
    # builds a real repository first, captures what the unpatched call
    # returns against it (a real, non-empty root tuple), and only then
    # monkeypatches -- so `got != unpatched` is itself part of the pin, not
    # an assumption.
    _init_repo_with_root_commit(tmp_path, "an ordinary first commit")
    unpatched = _root_commit_ids(tmp_path)
    assert unpatched != ()

    def _fake_run(
        cmd: Sequence[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=1,
            stdout="deadbeef\ncafebabe\n",
            stderr="fatal: simulated git failure\n",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    got = _root_commit_ids(tmp_path)
    assert got != unpatched, (
        "the monkeypatch did not change the result -- it may not have been "
        "in effect (e.g. the module resolved a bound `subprocess.run` name "
        "at import time rather than looking it up on the patched module)"
    )
    assert got == ()


def test_commit_message_discards_stdout_when_the_git_invocation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Findings 2/3 (round 3 remediation), the M7 half: the same argument
    # applies to `_commit_message` -- `git log` on an unknown commit id also
    # writes its diagnostic to stderr and leaves stdout empty, so an
    # unknown-commit-id fixture cannot distinguish "the `returncode == 0`
    # guard fired" from "the guard is gone and stdout was simply empty
    # regardless".
    #
    # Repair round: rebuilt on a real repository and queried by `"HEAD"`
    # (not an unknown id) so the unpatched call has real, non-empty message
    # content to differ from -- the same non-vacuity requirement as the
    # sibling test above.
    _init_repo_with_root_commit(tmp_path, "a distinctive planted message\n")
    unpatched = _commit_message(tmp_path, "HEAD")
    assert unpatched != ""

    def _fake_run(
        cmd: Sequence[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=1,
            stdout="a message that must never surface on failure\n",
            stderr="fatal: simulated git failure\n",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    got = _commit_message(tmp_path, "HEAD")
    assert got != unpatched, (
        "the monkeypatch did not change the result -- it may not have been "
        "in effect (e.g. the module resolved a bound `subprocess.run` name "
        "at import time rather than looking it up on the patched module)"
    )
    assert got == ""


def test_root_commit_ids_treats_a_signal_killed_git_as_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sweep finding: `result.returncode != 0` loosened to `result.returncode
    # > 0` survives every fixture above -- a real `git` invocation's
    # returncode is 0 (success) or a small positive number (failure) in
    # every scenario those fixtures construct, so `!= 0` and `> 0` agree on
    # all of them. The two operators diverge only for a NEGATIVE returncode,
    # which Python's `subprocess` reports when the child process was
    # terminated by a signal (`returncode = -signal_number`) -- a real,
    # documented `git` failure mode (killed, OOM, etc.), not a synthetic
    # case. `!= 0` must still treat it as a failure; `> 0` would not.
    #
    # Repair round: same non-vacuity fix as the two tests above -- a real
    # repository first, the unpatched (non-empty) result captured before the
    # double is installed.
    _init_repo_with_root_commit(tmp_path, "an ordinary first commit")
    unpatched = _root_commit_ids(tmp_path)
    assert unpatched != ()

    def _fake_run(
        cmd: Sequence[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=-9,  # SIGKILL
            stdout="deadbeef\ncafebabe\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    got = _root_commit_ids(tmp_path)
    assert got != unpatched, (
        "the monkeypatch did not change the result -- it may not have been "
        "in effect (e.g. the module resolved a bound `subprocess.run` name "
        "at import time rather than looking it up on the patched module)"
    )
    assert got == ()


def test_sole_root_commit_not_naming_the_provenance_record_reads_pre_replacement(
    tmp_path: Path,
) -> None:
    # The pre-replacement fixture the gate requires (change-protocol.md):
    # exactly one root, an ordinary message that never mentions the
    # provenance record, so a permissive signal (one that returned `True`
    # unconditionally) is the mutation this kills.
    _init_repo_with_root_commit(tmp_path, "Initial repo setup, nothing special")

    assert not _sole_root_commit_names_the_provenance_record(tmp_path)
    assert not _is_post_replacement_era(tmp_path)


def test_root_message_sharing_the_records_directory_stays_pre_replacement(
    tmp_path: Path,
) -> None:
    # A near-miss decoy that shares `_PROVENANCE_RECORD_RELPATH`'s directory
    # prefix ("docs/reference/") and most of its filename ("history-rewrites")
    # but is not the constant, and does not contain the constant's bare
    # filename either ("history-rewrites-notes.md" is not
    # "history-rewrites.md"). Isolates Finding 1's first reviewer mutation,
    # `"history" in message`: the decoy contains "history" but neither the
    # exact path nor the bare filename, so it kills that mutation alone. See
    # the sibling test below for the second mutation's own near miss.
    decoy = "docs/reference/history-rewrites-notes.md"
    assert str(_PROVENANCE_RECORD_RELPATH) not in decoy
    assert _PROVENANCE_RECORD_RELPATH.name not in decoy
    assert "history" in decoy  # confirms the loosened `"history" in ...`
    # signal WOULD read this fixture as post-replacement -- the gate's
    # falsity-in-starting-state check, verified directly against the decoy
    # string rather than trusted.
    _init_repo_with_root_commit(
        tmp_path, f"An ordinary commit that happens to name {decoy}."
    )

    assert not _sole_root_commit_names_the_provenance_record(tmp_path)
    assert not _is_post_replacement_era(tmp_path)


def test_root_message_naming_only_the_records_filename_stays_pre_replacement(
    tmp_path: Path,
) -> None:
    # A second near-miss decoy that shares `_PROVENANCE_RECORD_RELPATH`'s bare
    # filename ("history-rewrites.md") but omits its directory prefix -- kills
    # a signal loosened to `_PROVENANCE_RECORD_RELPATH.name in message`
    # (Finding 1's second reviewer mutation) without also satisfying the
    # correct, exact-path check.
    decoy = "history-rewrites.md"
    assert str(_PROVENANCE_RECORD_RELPATH) not in f"See {decoy} for details."
    assert _PROVENANCE_RECORD_RELPATH.name in decoy  # confirms the loosened
    # `_PROVENANCE_RECORD_RELPATH.name in ...` signal WOULD read this fixture
    # as post-replacement -- falsity-in-starting-state, verified directly.
    _init_repo_with_root_commit(tmp_path, f"See {decoy} for details.")

    assert not _sole_root_commit_names_the_provenance_record(tmp_path)
    assert not _is_post_replacement_era(tmp_path)


def test_root_message_varying_spelling_stays_pre_replacement(tmp_path: Path) -> None:
    # Finding 1 (round 3 remediation): the two near-miss decoys above each
    # vary the needle's EXTENT (dropping the directory, or the exact
    # filename) -- neither varies its SPELLING, so a signal loosened to a
    # normalising comparison stays green under both. Two such loosenings
    # measured green at full-suite scope by the round-2 reviewer: M5
    # (`str(_PROVENANCE_RECORD_RELPATH).lower() in
    # _commit_message(...).lower()`) and M11
    # (`str(_PROVENANCE_RECORD_RELPATH).replace("-", "") in
    # _commit_message(...).replace("-", "")`). This test carries one decoy
    # for each.
    decoy_case = "Docs/Reference/History-Rewrites.md"
    decoy_no_hyphen = "docs/reference/historyrewrites.md"

    # Falsity-in-starting-state, verified directly rather than trusted:
    # neither decoy is the exact constant string...
    assert str(_PROVENANCE_RECORD_RELPATH) not in decoy_case
    assert str(_PROVENANCE_RECORD_RELPATH) not in decoy_no_hyphen
    # ...but each WOULD be read as post-replacement by the loosening it
    # targets, and only that one:
    assert str(_PROVENANCE_RECORD_RELPATH).lower() in decoy_case.lower()  # M5
    assert str(_PROVENANCE_RECORD_RELPATH).lower() not in decoy_no_hyphen.lower()
    assert str(_PROVENANCE_RECORD_RELPATH).replace("-", "") in decoy_no_hyphen.replace(
        "-", ""
    )  # M11
    assert str(_PROVENANCE_RECORD_RELPATH).replace("-", "") not in decoy_case.replace(
        "-", ""
    )

    _init_repo_with_root_commit(
        tmp_path,
        f"An ordinary commit citing {decoy_case} and {decoy_no_hyphen}.",
    )

    assert not _sole_root_commit_names_the_provenance_record(tmp_path)
    assert not _is_post_replacement_era(tmp_path)


def test_sole_root_commit_naming_the_provenance_record_reads_post_replacement(
    tmp_path: Path,
) -> None:
    _init_repo_with_root_commit(
        tmp_path,
        "Initial commit of the published history.\n\n"
        "The prior history was replaced rather than rewritten. See "
        f"{_PROVENANCE_RECORD_RELPATH} for the record of what was removed "
        "and why.\n",
    )

    assert _sole_root_commit_names_the_provenance_record(tmp_path)
    assert _is_post_replacement_era(tmp_path)


def test_two_root_commits_read_pre_replacement_even_when_one_names_the_record(
    tmp_path: Path,
) -> None:
    # Kills the plausible wrong implementation "some root names the record"
    # (rather than "the SOLE root does"): one of the two roots below names
    # the provenance record, and the era must still read pre-replacement,
    # because the replacement's own construction (design.md
    # `#### HistoryReplacement` step 3) never produces more than one root.
    _init_repo_with_root_commit(tmp_path, "an ordinary first commit")
    _add_orphan_root_commit(
        tmp_path,
        f"a second root that happens to mention {_PROVENANCE_RECORD_RELPATH}",
    )

    assert len(_root_commit_ids(tmp_path)) == 2
    assert not _is_post_replacement_era(tmp_path)


def test_two_root_commits_both_naming_the_record_still_read_pre_replacement(
    tmp_path: Path,
) -> None:
    # Sweep finding: the sibling test above (only one of two roots names the
    # record) cannot, on its own, distinguish the correct `if len(roots) !=
    # 1: return False` guard from a narrower `if len(roots) < 1: return
    # False` -- the narrower guard lets `len(roots) == 2` fall through to
    # `roots[0]`, and whichever root `git rev-list --all --max-parents=0`
    # happens to order first there determines the (unspecified, ordering-
    # dependent) outcome; measured against this git installation, that
    # ordering happens to put the non-naming root first, so the sibling test
    # passes under the narrower guard too, by ordering luck rather than by
    # the guard being correct. This test removes the ordering dependency
    # entirely: BOTH roots name the record, so `roots[0]` is a record-naming
    # message regardless of `git`'s ordering, and only the correct "exactly
    # one" guard -- not the narrower "at least one" guard -- returns `False`
    # here.
    _init_repo_with_root_commit(
        tmp_path, f"a first root mentioning {_PROVENANCE_RECORD_RELPATH}"
    )
    _add_orphan_root_commit(
        tmp_path,
        f"a second, unrelated root also mentioning {_PROVENANCE_RECORD_RELPATH}",
    )

    assert len(_root_commit_ids(tmp_path)) == 2
    assert not _sole_root_commit_names_the_provenance_record(tmp_path)
    assert not _is_post_replacement_era(tmp_path)


def test_a_non_root_commit_naming_the_record_does_not_signal_post_replacement(
    tmp_path: Path,
) -> None:
    # Kills the plausible wrong implementation "any reachable commit names
    # the record" (rather than "the root does"): the record is named only by
    # a CHILD commit here, with the root's own message left ordinary.
    _init_repo_with_root_commit(tmp_path, "an ordinary first commit")
    _add_child_commit(
        tmp_path, f"a later commit mentioning {_PROVENANCE_RECORD_RELPATH}"
    )

    assert len(_root_commit_ids(tmp_path)) == 1
    assert not _is_post_replacement_era(tmp_path)


def test_provenance_record_relpath_matches_the_real_tracked_file() -> None:
    """Pin `_PROVENANCE_RECORD_RELPATH` against the real tree and against a
    written-out literal, rather than against a fixture that derives its
    expectation from the constant under test.

    Finding 4 (round 3 remediation): a prior version of this docstring
    claimed "every fixture above plants `_PROVENANCE_RECORD_RELPATH` itself
    into a commit message, so a typo in the constant would be invisible to
    all of them" -- measured false. A typo in the constant (e.g.
    `history-rewrite.md`, dropping the final `s`) DOES surface: measured
    directly, that mutation reds
    `test_root_message_naming_only_the_records_filename_stays_pre_replacement`,
    whose decoy is exactly the correctly-spelled literal `"history-rewrites.md"`.
    This test pins the value directly and doubles as a rename guard for the
    tracked file it names."""
    assert Path("docs/reference/history-rewrites.md") == _PROVENANCE_RECORD_RELPATH
    assert (_repo_root() / _PROVENANCE_RECORD_RELPATH).is_file()
