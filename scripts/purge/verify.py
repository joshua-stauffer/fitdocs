"""`ReplacementVerification` (task 7.4, design.md `#### ReplacementVerification`,
Req 7.4, 7.5, 7.6, 7.7, 5.3, 10.3, 10.4, 11.3): prove the fresh-root
replacement by inspecting what the repository actually contains, pre-swap
and post-swap -- re-scoped from this module's retired `LocalVerification`
shape (task 5.4) to Decision 7's fresh-root, `.git`-swap mechanism
(design.md `#### HistoryReplacement`), never the retired in-place rewrite.

**Every row names the repository it runs against.** design.md's four
candidate subjects: `F` (the fresh scratch clone, pre-swap), `W` (the
working repository, post-swap), `C` (a `--no-local` verification clone of
`W`), `Rm` (a fresh clone from the published remote, `RemoteReconciliation`'s
concern below). `RowResult.subject` carries the `Path` each check function
was actually called with, so a caller (or a test) can pin which repository
produced a given verdict rather than trusting a row's name alone. The
unreachable-object half of `check_reflog_and_unreachable_gone` is meaningful
only against `W`: a `--no-local` clone has no unreachable objects by
construction, so running it there is vacuous by design -- this module does
not stop a caller from doing that, but does not do it either. Post-swap, `W`
*is* effectively a fresh clone (the fresh `.git` just swapped in), which is
exactly why the fsck and reflog rows are meaningful there and why `F` rows
alone prove nothing about the swap.

**Reuse, not rebuild.** `check_refs_clean`, `check_metadata_clean`,
`check_old_identifiers_refused`, `check_reflog_and_unreachable_gone`,
`check_no_token_in_any_commit_message`, `check_fresh_clone`,
`check_built_artifacts`, `clone_without_local` and the alternates assertion
below all survive the re-scoping from `LocalVerification` unchanged in
shape. Two rows are new: `check_exactly_one_commit_reachable` and
`check_tree_identity` (Req 10.3) -- the fresh root's central new claims.
One row is re-scoped in place: `check_working_tree_coincides` (Req 10.3,
tracked files only -- see its docstring for the declared correction, task
7.4, that scopes it there). One row is a merge of two retired ones:
`check_no_token_in_path_or_blob` folds the retired `check_no_token_in_any_
path`/`check_no_token_in_any_blob` into design.md's single combined row,
since the single reachable commit makes the two-surface split no longer
worth two rows. **Four rows are deleted with the mechanism whose subject no
longer exists**: `check_no_removed_path` (the tree-identity row already
makes the root exactly the certified, removed-path-free tree -- design.md
`#### ReplacementVerification`), `check_no_blob_reproduces_content` (the
whole-history value scan, whose multi-commit subject no longer exists; the
certified tip is scanned by both oracles at task 8.1 and the tree-identity
row carries that to the root -- design.md `#### ReplacementVerification`,
"Reuse, not rebuild"), `check_commit_map_complete` and `check_no_mailmap`
(both a multi-commit history's bookkeeping, and no multi-commit history
exists after the replacement).

**Req 7.4 forbids treating a passing test suite as evidence.** Every check
below reads the object database directly through `git`, never through this
project's own pytest suite.

**Verification clones are taken without the local optimisation.**
`clone_without_local` always passes `--no-local` and asserts
`.git/objects/info/alternates` is absent afterwards: a `--local` clone
hardlinks the object directory, unreachable objects included, which would
carry exactly what `check_reflog_and_unreachable_gone` exists to prove gone
into a "fresh" clone that never earned that description.

**The forbidden-string source is a required argument here, and this module
FAILS rather than skips when it is unset** -- `require_forbidden_strings`,
not `tests._forbidden_strings.require`. This is the opposite of the
test-suite guard's posture (`tests._forbidden_strings.require` turns an
unset source into `pytest.skip`) and is deliberate: a verification pass is a
one-shot acceptance procedure with an operator present, not a routine run.
Every token row is vacuous without it.

`verify_local`/`verify_remote` below (the `typer` commands `__main__.py`
already imports and registers) remain unimplemented stubs -- CLI wiring to a
real out-of-repository scratch source, a real replaced repository and a
real `uv build` invocation is task 7.6's responsibility (the `replace`
subcommand dispatch, out of this task's `ReplacementVerification` boundary),
run from `main` in the primary worktree once the fresh-root replacement
(Major 7/8) is underway, the same posture `scripts/purge/preflight.py::run`,
`scripts/purge/plan.py::run` and `scripts/purge/rewrite.py::run` state for
their own CLI wiring. This module's row functions (originally task 5.4, now
re-scoped by task 7.4) are what task 7.6 calls.

**`RemoteReconciliation` (`verify-remote`, task 5.7, design.md ####
RemoteReconciliation, Req 8.1, 8.3, 8.5) lives in this same module** --
sequenced after 5.4 rather than parallel with it, per that task's own text,
because both subcommands share one verification module.

**The only probe that can falsify retention is the authenticated web
request** `probe_identifier`/`probe_identifiers` drive through an injected
`WebTransport` callable -- never a real `requests`/`urllib` call inside this
module or its tests, the same "built, never executed for real in a test"
posture `scripts/purge/rewrite.py` states for its own injected
`CommandRunner`. `origin` advertises `allow-tip-sha1-in-want` and
`allow-reachable-sha1-in-want` but not `allow-any-sha1-in-want` (design.md
`#### RemoteReconciliation`), so a retained-but-unreachable object is
refused with the identical `upload-pack: not our ref` error as one that is
genuinely gone -- `git fetch origin <old-sha>` and a mirror clone plus an
object read are both false-negative machines and neither is implemented as
a usable probe here. `fetch_object_by_identifier` and
`mirror_clone_and_read_object` exist only to raise `DisqualifiedProbeError`
unconditionally, so they are unavailable rather than merely discouraged in
a docstring.

**The ref comparison is bidirectional** (Req 8.5): `compare_refs` checks
both that every local head is present on the remote at the same identifier
AND that no ref on the remote is absent locally -- the second half is what
catches a pre-rewrite ref left behind. `parse_ls_remote_output` is pure
text parsing of a caller-supplied `git ls-remote origin` transcript (never a
real `ls-remote` subprocess call in this module or its tests); `local_heads`
reads the LOCAL repository only, through the same read-only `_git_stdout`
helper the local-verification rows above already use, which never touches
the network.
"""

from __future__ import annotations

import re
import subprocess
import tarfile
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import typer
from tests._content_oracle import scan
from tests._forbidden_strings import (
    ForbiddenStrings,
    ForbiddenStringsSourceError,
    matches,
)
from tests._forbidden_strings import (
    load as load_forbidden_strings,
)

from scripts.purge.plan import enumerate_blob_ids, enumerate_paths, read_blob_text

# `check_no_blob_reproduces_content` (the whole-history value scan) and
# `check_no_removed_path` were the only callers of the value matcher's
# `SYMBOLIC_PROBES`/`_classify_email_domain` probe set and the identity-
# probe `_EMAIL_PATTERN` -- both retired by this task (module docstring
# above: their multi-commit subject no longer exists, and the tree-identity
# row already makes the root exactly the certified, removed-path-free
# tree), so those imports go with them rather than surviving unused.


@dataclass(frozen=True)
class RowResult:
    """One row of the `ReplacementVerification` table. `row` names the check,
    `subject` is the `Path` this specific call ran against (design.md
    `#### ReplacementVerification` and task 7.4's own text, carried over
    from task 5.4's: "every row names the repository it runs against" --
    Req 7.4 itself only requires verification by inspection, never a passing
    test suite as evidence), `passed` is the verdict, and `detail` names
    what was found on a failure (never a matched substring or a removed-
    material value -- only identifiers, counts and locations)."""

    row: str
    subject: Path
    passed: bool
    detail: str


ROW_NAMES: tuple[str, ...] = (
    "exactly one commit reachable",
    "root tree identical to the certified tip tree",
    "working tree coincides with the root",
    "no refs/original, no extra refs",
    "metadata clean",
    "no token in any commit message",
    "no token in any path or blob of the single commit",
    "reflogs and unreachables gone",
    "old identifiers refused",
    "fresh clone clean",
    "artifacts clean",
)
"""The 11 row NAMES standing for the 12 non-remote rows of design.md's
`#### ReplacementVerification` table (`design.md:1604-1618`), in the table's
own order (reflog, then unreachable, then old identifiers refused --
`design.md:1613-1615`) -- an anchor over the ROW SET itself, not merely over
whatever a particular caller's fixture happens to iterate. The table has 13
rows; this module implements 12 of them directly (every row but the 13th,
remote-subject one), carried as 11 names because the reflog row and the
unreachable-objects row share one function, `check_reflog_and_unreachable_
gone`. `RowResult.row` values for the NINE row functions that return a
single `RowResult` against one subject (`check_exactly_one_commit_
reachable`, `check_tree_identity`, `check_working_tree_coincides`,
`check_refs_clean`, `check_metadata_clean`, `check_no_token_in_any_commit_
message`, `check_no_token_in_path_or_blob`, `check_reflog_and_unreachable_
gone`, `check_old_identifiers_refused`) match this tuple's entries
literally; `"fresh clone clean"` and `"artifacts clean"` are the table's own
row labels for the two remaining `C`-subject rows (`check_fresh_clone`'s
`RowResult`s reuse several of the other nine functions' own row labels with
`subject=C`, and `check_built_artifacts` reports as `"artifacts clean"`),
listed here so a caller iterating this tuple (task 7.6) has the complete row
set to drive from, and so a test can assert `len(ROW_NAMES) == 11`
independent of any one fixture's own row count. Task 7.4's own re-scoping
removed four rows whose subject (a multi-commit history to sweep, or the
whole-history value scan -- see `check_no_blob_reproduces_content`'s removal
note below) no longer exists: `check_no_removed_path`,
`check_no_blob_reproduces_content`, `check_commit_map_complete`,
`check_no_mailmap` -- none of the four remain in this module. The
`ReplacementVerification` table's 13th, remote-subject row (`Rm`, "remote
serves the replacement and only it") is implemented by the
`RemoteReconciliation` functions below this section, which return
`RefComparisonResult`/`ProbeResult`, never `RowResult`, so it is not a
member of this tuple."""


class VerificationCloneError(RuntimeError):
    """Raised by `clone_without_local` when the clone it just took carries
    `.git/objects/info/alternates` -- i.e. it was not, in fact, taken
    without the local optimisation."""


class VerificationInputsError(RuntimeError):
    """Raised by a row check that requires a non-empty sample (e.g.
    `check_old_identifiers_refused`) when handed nothing to sample -- the
    vacuous-walk anti-pattern: a check that scanned zero items must not
    report a pass having checked nothing."""


# --- subprocess helpers -------------------------------------------------------


def _git_stdout(repo: Path, *args: str) -> str:
    """Run a read-only `git` subcommand rooted at `repo`, returning stdout.
    Every row check in this module reads state; none opens a ref for write
    or expires a reflog (that is `HistoryRewrite`'s and the one-shot rewrite
    operator's job, both outside this module's boundary)."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


# --- row: exactly one commit reachable (Req 7.1, 7.2) -------------------------


def check_exactly_one_commit_reachable(repo: Path) -> RowResult:
    """ "Exactly one commit reachable" -- run against `repo`. `git rev-list
    --all --count` must report `1`: the fresh root forged by `commit-tree`
    with no parent is the only commit reachable from any ref (design.md
    `#### HistoryReplacement`'s ordering step 3-4, `#### ReplacementVerification`
    Req 7.1/7.2 "satisfied by construction and still asserted")."""
    out = _git_stdout(repo, "rev-list", "--all", "--count").strip()
    passed = out == "1"
    return RowResult(
        row="exactly one commit reachable",
        subject=repo,
        passed=passed,
        detail=(
            "clean"
            if passed
            else f"rev-list --all --count reported {out!r}, expected '1'"
        ),
    )


# --- row: root tree identical to the certified tip tree (Req 10.3) ------------


def check_tree_identity(repo: Path, certified_tree_id: str) -> RowResult:
    """ "Root tree identical to the certified tip tree" (Req 10.3) -- run
    against `repo`. `git rev-parse HEAD^{tree}` must equal `certified_tree_id`
    -- the tree id design.md `#### HistoryReplacement` step 1 records at gate
    time, captured before anything else happens. Every change this spec makes
    lands on `main` before the tip is certified, so the replacement root
    carries the certified tree unchanged; this is that claim, measured."""
    out = _git_stdout(repo, "rev-parse", "HEAD^{tree}").strip()
    passed = out == certified_tree_id
    return RowResult(
        row="root tree identical to the certified tip tree",
        subject=repo,
        passed=passed,
        detail=(
            "clean"
            if passed
            else f"HEAD^{{tree}} is {out!r}, expected {certified_tree_id!r}"
        ),
    )


# --- row: working tree coincides with the root, tracked files only (Req 10.3) -


def check_working_tree_coincides(repo: Path) -> RowResult:
    """ "Working tree coincides with the root", tracked files only (Req 10.3)
    -- run against `repo`. `git status --porcelain --untracked-files=no`
    must report nothing.

    **Restricted to tracked files -- a declared correction, task 7.4**
    (design.md `#### HistoryReplacement` step 7 and `#### ReplacementVerification`,
    both amended in place in the same change as this function). The bare,
    untracked-files-included form of this row (`git status --porcelain` with
    no restriction) can never be empty in the fitdocs repository: the root
    `agent-log` symlink is untracked and matched by no ignore rule (measured:
    `git status --porcelain=v1 --untracked-files=all -- agent-log` reports
    `?? agent-log`, and `git check-ignore -v agent-log` reports nothing), and
    Decision 7 guarantees untracked material survives the swap unmoved, so an
    untracked-files-included porcelain would red on every run by
    construction, regardless of whether the swap itself is correct -- a
    guaranteed swap-back trigger. The identity claim was always about
    TRACKED state coinciding with the root commit's tree, which
    `--untracked-files=no` measures directly."""
    out = _git_stdout(repo, "status", "--porcelain", "--untracked-files=no").strip()
    passed = out == ""
    return RowResult(
        row="working tree coincides with the root",
        subject=repo,
        passed=passed,
        detail="clean" if passed else f"tracked-file status non-empty: {out!r}",
    )


# --- row: no token in any path or blob of the single commit -------------------


def check_no_token_in_path_or_blob(
    repo: Path, forbidden: ForbiddenStrings
) -> RowResult:
    """ "No token in any path or blob of the single commit" -- run against
    `repo`. Combines the standing token guard's two surfaces -- path and
    content, the same `ForbiddenStrings.matches` matcher
    `tests/test_forbidden_strings.py` uses over the working tree -- into the
    one row design.md `#### ReplacementVerification` states, over the
    complete path and blob enumeration
    (`scripts.purge.plan.enumerate_paths`/`enumerate_blob_ids`, both driven
    by `git rev-list --all`, which after the replacement is reachable from
    exactly the one root commit -- the retired mechanism's separate "no
    token in any path" and "no token in any blob" rows are folded into this
    one, since the single reachable commit makes the two-surface split no
    longer worth two table rows). This row's subjects (`F`, `W`, `C`) all
    hold exactly one commit by construction, so `enumerate_paths`'
    whole-history walk and a HEAD-only walk cannot diverge for either
    surface here; the path side carries no dedicated multi-commit-history
    fixture in this module's own tests for that reason, while the blob
    side keeps one -- each surface's whole-history behaviour stays pinned
    at its own shared enumerator's tests instead: `enumerate_paths`' walk at
    `tests/purge/test_plan.py:523` (deleted-before-HEAD) and `:554`
    (second-branch-only), `enumerate_blob_ids`' walk at
    `tests/purge/test_plan.py:158` (second-branch-only, with `:110`/`:131`
    covering distinct-blob and same-basename cases)."""
    hit_paths = tuple(
        sorted(path for path in enumerate_paths(repo) if matches(path, forbidden))
    )
    hit_blobs = tuple(
        blob_id
        for blob_id in enumerate_blob_ids(repo)
        if matches(read_blob_text(repo, blob_id), forbidden)
    )
    passed = not hit_paths and not hit_blobs
    detail_parts: list[str] = []
    if hit_paths:
        detail_parts.append(f"token found in path(s): {hit_paths}")
    if hit_blobs:
        detail_parts.append(f"token found in blob(s): {hit_blobs}")
    return RowResult(
        row="no token in any path or blob of the single commit",
        subject=repo,
        passed=passed,
        detail="clean" if passed else "; ".join(detail_parts),
    )


# --- row: no token in any commit message --------------------------------------


def check_no_token_in_any_commit_message(
    repo: Path, forbidden: ForbiddenStrings
) -> RowResult:
    """ "No token in any commit message" -- run against `repo`.
    `git log --all --format=%B` (every commit message, concatenated) through
    `ForbiddenStrings.matches`, matching the design table's command shape
    exactly."""
    text = _git_stdout(repo, "log", "--all", "--format=%B")
    hits = matches(text, forbidden)
    return RowResult(
        row="no token in any commit message",
        subject=repo,
        passed=not hits,
        detail=(
            "clean" if not hits else f"token(s) found across commit messages: {hits}"
        ),
    )


# --- row: no refs/original, no extra refs -------------------------------------


def check_refs_clean(repo: Path) -> RowResult:
    """ "No `refs/original`, no extra refs" -- run against `repo`.
    `git for-each-ref` must list exactly `refs/heads/main` and nothing
    else."""
    out = _git_stdout(repo, "for-each-ref", "--format=%(refname)")
    refs = tuple(sorted(line for line in out.splitlines() if line))
    passed = refs == ("refs/heads/main",)
    return RowResult(
        row="no refs/original, no extra refs",
        subject=repo,
        passed=passed,
        detail="clean" if passed else f"unexpected ref set: {refs}",
    )


# --- row: metadata clean ------------------------------------------------------


def check_metadata_clean(repo: Path, allowed: frozenset[str]) -> RowResult:
    """ "Metadata clean" -- run against `repo`. Every distinct author-email,
    committer-email, author-name and committer-name across every commit on
    every ref must be a member of `allowed` (the non-personal address/name
    the caller supplies as the only acceptable value)."""
    out = _git_stdout(repo, "log", "--all", "--format=%ae%n%ce%n%an%n%cn")
    distinct = tuple(sorted({line for line in out.splitlines() if line}))
    hits = tuple(value for value in distinct if value not in allowed)
    return RowResult(
        row="metadata clean",
        subject=repo,
        passed=not hits,
        detail="clean" if not hits else f"disallowed metadata value(s): {hits}",
    )


# --- row: old identifiers refused (Req 7.6) -----------------------------------


def check_old_identifiers_refused(repo: Path, old_ids: Sequence[str]) -> RowResult:
    """ "Old ids refused" (Req 7.6) -- run against `repo`. `git cat-file -e
    <id>` for every sampled pre-rewrite commit/blob identifier must be
    non-zero (object absent). `old_ids` must be non-empty: a check that
    samples nothing would pass vacuously having refused nothing.

    **Survivorship constraint on the sample, a declared correction (task
    7.4, matching task 8.1's constraint):** `old_ids`'s commit ids may be
    drawn freely -- no pre-replacement commit survives the replacement --
    but its blob ids must be drawn only from content ABSENT from the
    certified tree. A blob is content-addressed, so a blob whose content
    survives into the certified tree is re-created identically in the fresh
    repository by the forge-and-clone steps (design.md `####
    HistoryReplacement`); a sample drawn from such a blob would red by
    construction, refuting nothing about the replacement. This function
    itself performs no such filtering -- it trusts the caller's sample, as
    it always has -- the constraint binds task 8.1's sample-capture, not
    this row's mechanics."""
    if not old_ids:
        raise VerificationInputsError(
            "check_old_identifiers_refused called with an empty sample; "
            "a check over zero old identifiers would pass having refused nothing"
        )
    still_present = []
    for old_id in old_ids:
        result = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", old_id],
            capture_output=True,
        )
        if result.returncode == 0:
            still_present.append(old_id)
    passed = not still_present
    return RowResult(
        row="old identifiers refused",
        subject=repo,
        passed=passed,
        detail="clean" if passed else f"still resolvable: {tuple(still_present)}",
    )


# --- row: reflogs and unreachables gone (R only) ------------------------------

# Longest alternative first so a 64-hex (sha256) run is matched whole rather
# than read as an unanchored 40-char substring; the negative lookarounds on
# both sides are what make that hold regardless of alternative order (a
# 40-char match immediately preceding or following more hex digits fails its
# own boundary and the engine falls through to the 64-alternative instead).
_REFLOG_HEX_ID_RE = re.compile(
    r"(?<![0-9a-f])(?:[0-9a-f]{64}|[0-9a-f]{40})(?![0-9a-f])"
)
_REFLOG_NULL_IDS = frozenset({"0" * 40, "0" * 64})


def check_reflog_and_unreachable_gone(repo: Path, allowed_commit: str) -> RowResult:
    """ "Reflogs and unreachables gone" (Req 7.3) -- run against `repo`
    **only**; vacuous against any fresh `--no-local` clone, which has no
    unreachable object by construction (see module docstring).

    **Reflog half, a declared correction (this fix; design.md
    `#### ReplacementVerification`, amended in place in the same change).**
    This half no longer demands `git reflog show --all` report literally
    nothing. Measured against a real `run_replace` swap (real git 2.54.0):
    the shipped clone-then-rename path leaves reflog entries behind (`clone:
    from <source>`, `Branch: renamed ...`), so a literal-emptiness contract
    reds on every CORRECT replacement -- the same false-red shape task 7.4
    already removed once, for the porcelain row. Worse, `reflog show --all`
    is not even a sound way to MEASURE Req 7.3's actual text ("reflogs ...
    shall reference no pre-replacement commit"): measured directly, it
    silently omits any reflog line whose named object is absent from the
    object database and still exits 0 -- exactly the shape a genuine
    leftover pre-replacement id would have post-swap, so a `reflog show`-
    based check structurally cannot see the one failure mode Req 7.3 exists
    to catch.

    This half instead reads every file under `.git/logs/**` directly --
    `logs/HEAD`, `logs/refs/heads/**`, `logs/refs/remotes/**`, `logs/refs/
    stash`, whatever is present -- and asserts no hex object id other than
    `allowed_commit` (the replacement root) appears in any of them. The
    all-zeros placeholder id (`"0" * 40`, or `"0" * 64` for a sha256
    repository) is discarded by exact value match, never by whether it
    resolves: it legitimately appears as the "from" side of a branch
    creation (measured: `git branch <name>` writes exactly that shape), and
    a resolvability-based filter would reintroduce the exact blindness this
    correction exists to fix -- an id whose object is gone also fails to
    resolve. A walk that reads zero files under `.git/logs` raises
    `VerificationInputsError` rather than passing having scanned nothing,
    the same vacuous-walk posture `check_old_identifiers_refused` uses for
    an empty sample.

    **Read as `surrogateescape`, not the default UTF-8 codec -- a second
    declared correction (this same fix).** A reflog line's committer name
    and its trailing message are both attacker- and history-controlled
    bytes (a message can embed an arbitrary filesystem path), not text this
    module gets to assume is valid UTF-8; measured, a single latin-1 byte
    planted in a committer name makes `Path.read_text()`'s default codec
    raise `UnicodeDecodeError`, which would propagate out of this row and
    crash the one-shot verification pass rather than fail it -- the exact
    "must fail, never crash" posture this docstring already states for the
    fsck half, previously violated by this half. `errors="surrogateescape"`
    preserves every byte (round-trippable, and every hex digit this
    function's own regex matches is plain ASCII either way), so the id-scan
    behaves identically on a clean file and gains the ability to finish,
    rather than crash, on one that is not valid UTF-8.

    **Fsck half, still asserted, no longer run through `_git_stdout`'s
    `check=True`.** `git fsck --unreachable --dangling` must still report
    nothing on either stream and exit `0` -- but measured directly, real
    git does not exit `0` with plain dangling-object output for the exact
    motivating defect above (a reflog file naming an id whose object is
    absent): it exits `2` and writes `invalid reflog entry <id>` to
    stderr. `_git_stdout`'s `check=True` would turn that into an uncaught
    `CalledProcessError`, crashing the row instead of failing it, so this
    half runs `fsck` directly and folds a non-zero exit (with its stderr)
    into the same failing detail rather than propagating it."""
    logs_dir = repo / ".git" / "logs"
    found: set[str] = set()
    scanned = 0
    for log_file in logs_dir.rglob("*"):
        if log_file.is_file():
            scanned += 1
            found.update(
                _REFLOG_HEX_ID_RE.findall(log_file.read_text(errors="surrogateescape"))
            )
    if scanned == 0:
        raise VerificationInputsError(
            f"no reflog files found under {logs_dir}; a reflog check that "
            "scanned nothing would pass having verified nothing"
        )
    found -= _REFLOG_NULL_IDS
    disallowed = found - {allowed_commit}
    fsck_proc = subprocess.run(
        ["git", "-C", str(repo), "fsck", "--unreachable", "--dangling"],
        capture_output=True,
        text=True,
    )
    fsck_output = (fsck_proc.stdout + fsck_proc.stderr).strip()
    fsck_clean = fsck_proc.returncode == 0 and not fsck_output
    passed = not disallowed and fsck_clean
    detail_parts = []
    if disallowed:
        detail_parts.append(
            f"reflog files reference id(s) other than {allowed_commit!r}: "
            f"{sorted(disallowed)}"
        )
    if not fsck_clean:
        detail_parts.append(f"fsck reported: {fsck_output!r}")
    return RowResult(
        row="reflogs and unreachables gone",
        subject=repo,
        passed=passed,
        detail="clean" if passed else "; ".join(detail_parts),
    )


# --- fresh clone (Req 7.5) ------------------------------------------------------
#
# `check_commit_map_complete` and `check_no_mailmap` -- both a multi-commit
# history's bookkeeping -- are deleted with the mechanism whose subject no
# longer exists (task 7.4; module docstring above; design.md `####
# ReplacementVerification`, "Reuse, not rebuild"). Neither has a replacement
# row: no commit map can exist by construction (Req 9.3, design.md ####
# ProvenanceRecord), and `.mailmap` was never tracked at any commit this
# replacement's certified tip carries.


def _assert_no_alternates(dest: Path) -> None:
    """Raise `VerificationCloneError` if `dest/.git/objects/info/alternates`
    exists. Extracted from `clone_without_local` so the guard itself --
    "a verification clone must carry no alternates file" -- is directly
    testable against a planted file, independent of what any particular git
    version's `--no-local` flag happens to do on the machine running the
    test."""
    alternates = dest / ".git" / "objects" / "info" / "alternates"
    if alternates.exists():
        raise VerificationCloneError(
            f"{alternates} is present -- {dest} was not taken without the "
            "local optimisation"
        )


def clone_without_local(source: Path, dest: Path) -> Path:
    """Take a verification clone of `source` at `dest` **without** the local
    optimisation (`--no-local`), then assert
    `dest/.git/objects/info/alternates` is absent -- raising
    `VerificationCloneError` if it is present. A `--local` clone hardlinks
    the object directory, unreachable objects included; a `--no-local` clone
    does not (see module docstring)."""
    subprocess.run(
        ["git", "clone", "--no-local", "--", str(source), str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    _assert_no_alternates(dest)
    return dest


def check_fresh_clone(
    *,
    replaced_repo: Path,
    clone_dest: Path,
    certified_tree_id: str,
    forbidden: ForbiddenStrings,
    old_ids: Sequence[str],
) -> tuple[RowResult, ...]:
    """ "Fresh clone clean" (Req 7.5) -- `clone_without_local` from
    `replaced_repo` (`W`) to `clone_dest` (`C`), then re-run the tree-
    identity, path/blob-token, message-token and old-identifiers-refused
    rows against `clone_dest` (never against `replaced_repo` -- every
    returned `RowResult.subject` is `clone_dest`): re-scoped (task 7.4) from
    the retired removed-path, path-token, value-oracle, blob-token and
    message-token rows (task 5.4) to the four that survive the mechanism
    change. `old_ids` is forwarded to `check_old_identifiers_refused`
    without truncation -- the full sample the caller passed in, not merely
    its first element -- so a survivorship-filtered sample with more than
    one id (task 8.1's captured sample is at minimum two: the old root and
    the certified tip) is checked against `clone_dest` in full. An empty
    sample raises `VerificationInputsError` there, the same vacuous-walk
    guard, not bypassable through this composition.

    Of the nine single-subject row functions, five are NOT re-run here.
    design.md `#### ReplacementVerification`'s table (`design.md:1604-1618`)
    disagrees with itself about which ones: its "Fresh clone clean" row
    says "re-run the rows above" (all nine), while its per-row **Run
    against** column marks only `check_old_identifiers_refused` as `C`. That
    disagreement is an open question, not resolved here (queued follow-up,
    `.kiro/queue/2026-08-18-replacement-verification-table-halves-
    disagree.md`). The five omitted below is this function's own judgment
    call, not derived from either half of the table alone, and for two
    different measured reasons:

    - `check_exactly_one_commit_reachable` and `check_metadata_clean` are
      omitted as genuinely redundant with their own `F, W` runs
      (`design.md:1606, 1610`): `clone_without_local` clones the same
      single commit, so the commit count and the set of author/committer
      identities `git log` reports cannot differ between `W` and `C`.
    - `check_refs_clean` and `check_working_tree_coincides` are omitted
      because a plain (non-`--bare`) `git clone` changes what each of them
      measures, not because they would be redundant: `check_refs_clean`
      would report NOT clean on every run, by construction, because `git
      clone` itself creates `refs/remotes/origin/HEAD` and
      `refs/remotes/origin/main` in `C` that do not exist in `W` (measured);
      `check_working_tree_coincides` would pass, but only because a freshly
      cloned checkout starts clean by construction (measured), the same
      vacuous-by-construction shape as the `fsck` half just below, so
      re-running it proves nothing about the swap either.
    - `check_reflog_and_unreachable_gone` is also omitted, but the reflog
      half's reason has changed (a correction to this note, made in the same
      change as the row's own declared correction). Under this row's
      now-current reference-only-the-root contract it is NOT a
      guaranteed-red hazard against `C`: measured, cloning `W` (a
      single-commit repository) writes `clone: from <source>` reflog
      entries whose only non-zero id is that same single commit, so the
      reflog scan finds nothing disallowed and the reflog half would PASS
      against `C` too. It stays out of this composition anyway -- not
      because it would fail, but because re-scoping which rows re-run
      against `C` is outside this fix's boundary; its `fsck` half remains
      separately vacuous by construction, unaffected (module docstring
      above). Whether it belongs back in this tuple now that the
      guaranteed-red reason is gone is an open question, not resolved here
      (queued follow-up).

    `check_tree_identity`, `check_no_token_in_path_or_blob` and
    `check_no_token_in_any_commit_message` ARE re-run here despite none
    being marked `C` in the per-row column, because none of the hazards
    above apply to them: cloning reproduces the same tree, paths, blobs and
    commit messages exactly, so these three retain real discriminating
    power against `C` (`test_check_fresh_clone_reds_when_the_certified_
    tree_id_is_wrong` exercises this for tree identity). The remaining one,
    `check_old_identifiers_refused`, IS marked `W, C` (`design.md:1615`) and
    is re-run here -- see `old_ids` above."""
    clone_without_local(replaced_repo, clone_dest)
    return (
        check_tree_identity(clone_dest, certified_tree_id),
        check_no_token_in_path_or_blob(clone_dest, forbidden),
        check_no_token_in_any_commit_message(clone_dest, forbidden),
        check_old_identifiers_refused(clone_dest, old_ids),
    )


# --- built artifacts (Req 10.4) -------------------------------------------------


def build_artifacts(source_repo: Path, output_dir: Path) -> tuple[Path, Path]:
    """Build an sdist and a wheel from `source_repo` into `output_dir` with
    `uv build --sdist --wheel`, returning `(sdist_path, wheel_path)`. Raises
    if either artifact is missing from the output directory afterwards."""
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "uv",
            "build",
            "--sdist",
            "--wheel",
            "-o",
            str(output_dir),
            str(source_repo),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    sdists = sorted(output_dir.glob("*.tar.gz"))
    wheels = sorted(output_dir.glob("*.whl"))
    if not sdists or not wheels:
        raise RuntimeError(
            f"uv build did not produce both a sdist and a wheel in {output_dir}: "
            f"sdists={sdists} wheels={wheels}"
        )
    return sdists[-1], wheels[-1]


def _iter_archive_members(archive: Path) -> Iterator[tuple[str, bytes | None]]:
    """Every non-directory member of `archive` (a `.tar.gz` sdist or a `.whl`
    wheel, which is a zip) as `(member_name, raw_bytes_or_None)`.

    `raw_bytes` is `None` when the member's content could not be read --
    this happens for a symlink or hardlink whose target is not itself
    present in the archive, which `tarfile.TarFile.extractfile` does NOT
    signal by returning `None` (that would be the directory case, already
    excluded below) but by RAISING `KeyError`. This is not hypothetical: a
    dangling `agent-log -> .git/agent-log` symlink ships in THIS project's
    own built sdist (`.kiro/queue/2026-07-31-agent-log-symlink-ships-in-sdist
    .md`), and `check_built_artifacts` below runs against exactly that
    shape. A caller that gets `None` back still has `member_name` -- an
    unreadable member's PATH is still checked; only its content is skipped,
    the same "scan to completion, report what could not be read" posture
    `tests._forbidden_strings.scan_tree` documents for an unreadable file in
    a working tree.

    Deliberately no `member.isfile()` guard for the tar branch: one was
    tried and found to be dead code given the `extractfile() is None` check
    already below it (confirmed by disabling the `isfile()` guard while
    keeping the `None` check -- the directory-exclusion test still passed,
    proving `extractfile` alone already excludes a directory). Restoring
    `isfile()` as the ONLY guard, as an earlier revision of this function
    did, is what created the `KeyError` this docstring exists to warn
    against: `isfile()` is `False` for a symlink too, so a naive
    `if not member.isfile(): continue` swallows a real, readable symlink
    silently -- exactly the blind spot this function must not reintroduce.
    """
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                yield name, zf.read(name)
        return
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            try:
                extracted = tf.extractfile(member)
            except KeyError:
                yield member.name, None
                continue
            if extracted is None:
                # Defensive only -- not reached by any fixture in this test
                # module (a directory is already excluded above, and a
                # symlink/hardlink with a missing target raises `KeyError`,
                # caught above, rather than returning `None`). Kept for any
                # OTHER non-regular member type `tarfile` might one day
                # return `None` for (e.g. a FIFO or device file) without
                # raising -- untested, not claimed to be pinned.
                yield member.name, None
                continue
            yield member.name, extracted.read()


def check_built_artifacts(
    *,
    subject: Path,
    sdist: Path,
    wheel: Path,
    forbidden: ForbiddenStrings,
    fingerprints: frozenset[str],
    window_lengths: frozenset[int],
    salt: bytes,
) -> RowResult:
    """ "Artifacts clean" (Req 10.4) -- run against `subject` (the repository
    `sdist`/`wheel` were built from, named for the row even though the
    actual scan reads the archive bytes). Every member's NAME (path surface,
    Req 10.4's "at any path") and, separately, its decoded CONTENT (when
    readable -- see `_iter_archive_members`) through both oracles:
    `ForbiddenStrings.matches` and `ContentOracle.scan`. Both `sdist` and
    `wheel` are scanned independently -- a wheel omits files (e.g. a
    `README.md`) a sdist includes, so neither archive alone is Req 10.4's
    "at any path"."""
    hits: list[str] = []
    unreadable: list[str] = []
    for archive in (sdist, wheel):
        for name, raw in _iter_archive_members(archive):
            if matches(name, forbidden):
                hits.append(f"{archive.name}:{name} (token in path)")
            if raw is None:
                unreadable.append(f"{archive.name}:{name}")
                continue
            text = raw.decode("utf-8", errors="replace")
            if matches(text, forbidden):
                hits.append(f"{archive.name}:{name} (token in content)")
            elif scan(text, fingerprints, window_lengths, salt):
                hits.append(f"{archive.name}:{name} (value)")
    passed = not hits
    detail_parts = []
    if hits:
        detail_parts.append(f"match(es) in built artifact(s): {tuple(hits)}")
    if unreadable:
        detail_parts.append(
            f"unreadable member(s), content not scanned: {tuple(unreadable)}"
        )
    detail = "clean" if not detail_parts else "; ".join(detail_parts)
    return RowResult(
        row="artifacts clean",
        subject=subject,
        passed=passed,
        detail=detail,
    )


# --- required forbidden-string source (opposite of the test-suite guard) -----


def require_forbidden_strings(repo_root: Path) -> ForbiddenStrings:
    """Load the forbidden-string source and **fail** -- never skip -- when it
    is unset. The opposite of `tests._forbidden_strings.require`, which
    turns an unset source into `pytest.skip`: a verification pass is a
    one-shot acceptance procedure with an operator present, not a routine
    run, and every token row above is vacuous without this."""
    forbidden = load_forbidden_strings(repo_root)
    if forbidden is None:
        raise ForbiddenStringsSourceError(
            "the forbidden-string source is unset; purge verify-local "
            "refuses to start without it rather than skipping its token "
            "rows (this is the opposite of the test-suite guard's posture)"
        )
    return forbidden


# =================================================================================
# RemoteReconciliation (`verify-remote`, task 5.7, design.md ####
# RemoteReconciliation, Req 8.1, 8.3, 8.5)
# =================================================================================

# --- the only probe that can falsify retention (Req 8.1, 8.3) ------------------

WebTransport = Callable[[str, Mapping[str, str]], int]
"""Injected by the caller: given a URL and a headers mapping, return an
HTTP status code. Never a real `requests`/`urllib` call inside this module
or its tests -- see the module docstring. The real HTTP client is Major 8's
CLI-wiring responsibility, exactly as `rewrite.CommandRunner` is
caller-supplied and unexercised inside `scripts/purge/rewrite.py`."""


class RemoteProbeError(RuntimeError):
    """Raised by `probe_identifier` when the transport returns a status
    code that is neither `200` (served) nor `404` (gone). A probe result
    must never collapse "gone" and "cannot tell" into the same outcome --
    this exception is how an unrecognised status is kept distinguishable
    from a genuine `404` rather than silently reported as removal."""


@dataclass(frozen=True)
class ProbeResult:
    """One identifier's result from `probe_identifier`. `served=True` means
    the web request returned `200` (still served from that path);
    `served=False` means it returned `404` (gone from that path). Any other
    status raises `RemoteProbeError` instead of producing a `ProbeResult` --
    there is no third `served` value standing in for "cannot tell"."""

    identifier: str
    url: str
    status_code: int
    served: bool


def build_commit_url(owner: str, repo: str, commit_id: str) -> str:
    """The one web path design.md `#### RemoteReconciliation` names as the
    only probe that can falsify retention: `https://github.com/<owner>/
    <repo>/commit/<old-sha>`."""
    return f"https://github.com/{owner}/{repo}/commit/{commit_id}"


def build_auth_headers(token: str) -> dict[str, str]:
    """Req 8.1/8.3's probe is an *authenticated* web request. Raises
    `ValueError` for an empty token rather than silently sending an
    unauthenticated request that a private repository would 404 regardless
    of whether the object is actually gone."""
    if not token:
        raise ValueError(
            "an authenticated probe requires a non-empty token; an empty "
            "token would send an unauthenticated request indistinguishable "
            "from one that never carried credentials at all"
        )
    return {"Authorization": f"Bearer {token}"}


def probe_identifier(
    transport: WebTransport,
    *,
    owner: str,
    repo: str,
    identifier: str,
    token: str,
) -> ProbeResult:
    """Issue one authenticated web request for `identifier` through the
    injected `transport` and classify the result: `200` -> served, `404` ->
    gone, anything else -> `RemoteProbeError` (see that exception's
    docstring)."""
    url = build_commit_url(owner, repo, identifier)
    headers = build_auth_headers(token)
    status = transport(url, headers)
    if status == 200:
        served = True
    elif status == 404:
        served = False
    else:
        raise RemoteProbeError(
            f"probe for {identifier} at {url} returned status {status}; "
            "neither 200 (served) nor 404 (gone) -- cannot conclude "
            "removal from this result"
        )
    return ProbeResult(
        identifier=identifier, url=url, status_code=status, served=served
    )


def probe_identifiers(
    transport: WebTransport,
    *,
    owner: str,
    repo: str,
    identifiers: Sequence[str],
    token: str,
) -> tuple[ProbeResult, ...]:
    """`probe_identifier` for every member of `identifiers`, in order.
    `identifiers` must be non-empty: a probe over zero identifiers would
    report clean having probed nothing -- the same vacuous-walk hazard
    `check_old_identifiers_refused` above already guards against, raising
    the same `VerificationInputsError`."""
    if not identifiers:
        raise VerificationInputsError(
            "probe_identifiers called with an empty sample; a probe over "
            "zero identifiers would report clean having probed nothing"
        )
    return tuple(
        probe_identifier(
            transport, owner=owner, repo=repo, identifier=identifier, token=token
        )
        for identifier in identifiers
    )


# --- the two disqualified probes: unavailable, not merely discouraged ----------


class DisqualifiedProbeError(RuntimeError):
    """Raised unconditionally by `fetch_object_by_identifier` and
    `mirror_clone_and_read_object` -- see the module docstring. Both
    functions raise before doing anything else, for any arguments, so
    neither can ever produce a result a caller might mistake for evidence
    of removal."""


def fetch_object_by_identifier(*_args: object, **_kwargs: object) -> NoReturn:
    """Disqualified. A direct `git fetch origin <sha>` cannot prove
    removal: `origin` advertises `allow-tip-sha1-in-want` and
    `allow-reachable-sha1-in-want` but not `allow-any-sha1-in-want`, so a
    retained-but-unreachable object is refused with the identical
    `upload-pack: not our ref` error as an object that is genuinely gone.
    Always raises `DisqualifiedProbeError`, regardless of the arguments
    supplied."""
    raise DisqualifiedProbeError(
        "fetch_object_by_identifier is disqualified as a probe: a direct "
        "`git fetch origin <sha>` is a false-negative machine -- a "
        "retained-but-unreachable object is refused with the same error "
        "as one that is genuinely gone, so this function refuses to run "
        "rather than return a result that cannot be trusted"
    )


def mirror_clone_and_read_object(*_args: object, **_kwargs: object) -> NoReturn:
    """Disqualified. A mirror clone plus a direct object read shares the
    identical blind spot as `fetch_object_by_identifier`. Always raises
    `DisqualifiedProbeError`, regardless of the arguments supplied."""
    raise DisqualifiedProbeError(
        "mirror_clone_and_read_object is disqualified as a probe: it "
        "shares the identical blind spot as fetch_object_by_identifier "
        "and cannot prove removal, so this function refuses to run rather "
        "than return a result that cannot be trusted"
    )


# --- the bidirectional ref comparison (Req 8.5) ---------------------------------


@dataclass(frozen=True)
class RefComparisonResult:
    """`passed` is true only when both directions hold. `missing_from_remote`
    names every local head absent from the remote, or present there at a
    different identifier. `remote_only` names every remote ref absent
    locally -- design.md states this half is "what catches a pre-rewrite
    ref left behind"."""

    passed: bool
    missing_from_remote: tuple[str, ...]
    remote_only: tuple[str, ...]


def parse_ls_remote_output(text: str) -> dict[str, str]:
    """Parse `git ls-remote`'s `<sha>\\t<refname>` lines. Returns EVERY
    remote ref except the `HEAD` symref line and any `^{}`-peeled duplicate
    (e.g. `refs/tags/v0.1.0^{}`, the dereferenced-tag-object line
    `ls-remote` emits alongside the tag ref itself). design.md
    `#### RemoteReconciliation`'s remote operand is unfiltered `git
    ls-remote origin` -- nothing there restricts it to `refs/heads/*` -- and
    Req 8.5's `remote_only` half must be able to report ANY leftover ref,
    not only a branch head: `refs/original/refs/heads/*` is the named
    pre-rewrite ref class (design.md `#### HistoryRewrite`: filter-repo
    "does not drop `refs/original/*`; it rewrites them forward, carrying
    the encumbered files and the personal address into the rewritten
    repository under new SHAs"), and a pre-rewrite tag left on the remote
    is exactly the kind of leftover this comparison exists to catch. Pure
    text parsing, no subprocess and no network in this function."""
    refs: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        sha, _, name = stripped.partition("\t")
        if not name or name == "HEAD" or name.endswith("^{}"):
            continue
        refs[name] = sha
    return refs


def local_heads(repo: Path) -> dict[str, str]:
    """Every local branch head in `repo`, through the same read-only
    `_git_stdout` helper the local-verification rows above already use --
    reads `repo` only, never the network."""
    out = _git_stdout(
        repo, "for-each-ref", "--format=%(objectname)\t%(refname)", "refs/heads"
    )
    heads: dict[str, str] = {}
    for line in out.splitlines():
        if not line:
            continue
        sha, _, name = line.partition("\t")
        heads[name] = sha
    return heads


def compare_refs(
    local: Mapping[str, str], remote: Mapping[str, str]
) -> RefComparisonResult:
    """Req 8.5, both directions. `missing_from_remote`: a local head is a
    miss when the remote lacks it, or carries it at a DIFFERENT identifier.
    `remote_only`: a remote ref is a miss when no local ref of the same
    name exists at all, regardless of identifier."""
    missing = tuple(
        sorted(name for name, sha in local.items() if remote.get(name) != sha)
    )
    remote_only = tuple(sorted(name for name in remote if name not in local))
    passed = not missing and not remote_only
    return RefComparisonResult(
        passed=passed, missing_from_remote=missing, remote_only=remote_only
    )


def check_remote_refs_match(repo: Path, remote_ls_output: str) -> RefComparisonResult:
    """Compose `local_heads` (real, local-only `git for-each-ref` against
    `repo` -- no network) with `parse_ls_remote_output` (pure parsing of a
    caller-supplied `git ls-remote origin` transcript -- also no network in
    this module or its tests) through `compare_refs`."""
    return compare_refs(local_heads(repo), parse_ls_remote_output(remote_ls_output))


# --- CLI stubs -----------------------------------------------------------------


def verify_local() -> None:
    """`purge verify-local` -- not yet implemented.

    The `ReplacementVerification` row functions above (task 7.4) are
    implemented and tested; wiring the CLI to a real fresh-root replacement,
    a real out-of-repository forbidden-string source and real scratch paths
    is task 7.6's responsibility (the `replace` subcommand dispatch, out of
    this task's `ReplacementVerification` boundary), run from `main` in the
    primary worktree once the fresh-root replacement (Major 7/8) is
    underway.
    """
    typer.echo(
        "purge verify-local: CLI wiring not yet implemented (task 7.6, "
        "ReplacementVerification) -- the row functions in "
        "scripts/purge/verify.py are implemented and tested (task 7.4)",
        err=True,
    )
    raise typer.Exit(code=1)


def verify_remote() -> None:
    """`purge verify-remote` -- not yet implemented.

    The functions above (`probe_identifier`, `probe_identifiers`,
    `compare_refs`, `check_remote_refs_match`, and the two disqualified
    probes) are implemented and tested (task 5.7); wiring the CLI to a real
    authenticated HTTP client, a real `git ls-remote origin` invocation and
    real out-of-repository scratch inputs is task 8.x's responsibility, run
    from `main` in the primary worktree once the one-shot rewrite has been
    pushed -- the same posture `verify_local` above states for its own CLI
    wiring.
    """
    typer.echo(
        "purge verify-remote: CLI wiring not yet implemented (task 8.x, "
        "RemoteReconciliation) -- the probe and ref-comparison functions in "
        "scripts/purge/verify.py are implemented and tested (task 5.7)",
        err=True,
    )
    raise typer.Exit(code=1)
