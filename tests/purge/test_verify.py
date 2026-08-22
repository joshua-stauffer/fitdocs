"""`scripts/purge/verify.py`: `ReplacementVerification`, the fresh-root
replacement verification runner (task 7.4, design.md `#### ReplacementVerification`,
Req 7.4, 7.5, 7.6, 7.7, 5.3, 10.3, 10.4, 11.3) -- re-scoped from this
module's retired `LocalVerification` shape (task 5.4; design.md names
`LocalVerification` only at `:83`, as the thing `ReplacementVerification`
replaced).

Every fixture here builds a synthetic git repository (and, for the built-
artifact rows, a synthetic tiny Python project) under `tmp_path`. Nothing
here runs a mutating git command against `fitdocs-purge`'s own working tree
or history.
"""

from __future__ import annotations

import os
import subprocess
import tarfile
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest
from scripts.purge.verify import (
    ROW_NAMES,
    DisqualifiedProbeError,
    ProbeResult,
    RefComparisonResult,
    RemoteProbeError,
    VerificationCloneError,
    VerificationInputsError,
    _iter_archive_members,
    build_artifacts,
    build_auth_headers,
    build_commit_url,
    check_built_artifacts,
    check_exactly_one_commit_reachable,
    check_fresh_clone,
    check_metadata_clean,
    check_no_token_in_any_commit_message,
    check_no_token_in_path_or_blob,
    check_old_identifiers_refused,
    check_reflog_and_unreachable_gone,
    check_refs_clean,
    check_remote_refs_match,
    check_tree_identity,
    check_working_tree_coincides,
    clone_without_local,
    compare_refs,
    fetch_object_by_identifier,
    local_heads,
    mirror_clone_and_read_object,
    parse_ls_remote_output,
    probe_identifier,
    probe_identifiers,
    require_forbidden_strings,
)

from tests._content_oracle import digest
from tests._forbidden_strings import (
    ENV_VAR,
    ForbiddenStrings,
    ForbiddenStringsSourceError,
)

_SALT = b"verify-fixture-salt"


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


def _forbidden(*values: str, tmp_path: Path) -> ForbiddenStrings:
    source = tmp_path / "forbidden-source-marker.tsv"
    return ForbiddenStrings(values=tuple(values), source=source)


def _commit_with_identity(
    repo: Path,
    *,
    message: str,
    author_name: str,
    author_email: str,
    committer_name: str,
    committer_email: str,
) -> None:
    """Commit whatever is currently staged in `repo` with an author identity
    and a committer identity that can differ from each other -- `git commit
    -c user.email=...` sets BOTH author and committer to the same value, so
    a fixture that needs them to diverge (to defeat a truncated `%ae`-only
    or `%ae%n%ce`-only metadata format string) must go through the
    `GIT_AUTHOR_*`/`GIT_COMMITTER_*` environment variables instead."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = author_name
    env["GIT_AUTHOR_EMAIL"] = author_email
    env["GIT_COMMITTER_NAME"] = committer_name
    env["GIT_COMMITTER_EMAIL"] = committer_email
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# ROW_NAMES -- the table itself, not any one fixture's row count
# ---------------------------------------------------------------------------


_DESIGN_MD = (
    Path(__file__).resolve().parents[2]
    / ".kiro"
    / "specs"
    / "encumbered-content-purge"
    / "design.md"
)

# Each entry pins one `#### ReplacementVerification` table row (design.md
# `:1604-1618`) to the `ROW_NAMES` entry it corresponds to, in the table's
# own top-to-bottom order. `find_text` is a substring unique to that row's
# "Check" cell -- unique enough that `str.index` locates the correct line
# and nothing earlier. `row_name` is `None` for the remote-subject row
# (returns `RefComparisonResult`/`ProbeResult`, never `RowResult`, so it has
# no `ROW_NAMES` entry); the reflog and unreachable-objects rows both name
# `"reflogs and unreachables gone"` because they share one function,
# `check_reflog_and_unreachable_gone`.
_DESIGN_TABLE_ROWS: tuple[tuple[str, str | None], ...] = (
    ("Exactly one commit reachable | F, W", "exactly one commit reachable"),
    (
        "**Root tree identical to the certified tip tree**",
        "root tree identical to the certified tip tree",
    ),
    (
        "Working tree coincides with the root, tracked files only",
        "working tree coincides with the root",
    ),
    (
        "Refs are `refs/heads/main` only, no `refs/original`",
        "no refs/original, no extra refs",
    ),
    ("Headers carry the non-personal address only", "metadata clean"),
    ("Root message clean (Req 11.3)", "no token in any commit message"),
    (
        "No token in any path or blob of the single commit",
        "no token in any path or blob of the single commit",
    ),
    (
        "Reflog references no pre-replacement commit",
        "reflogs and unreachables gone",
    ),
    ("No unreachable objects (Req 7.3)", "reflogs and unreachables gone"),
    ("Old identifiers refused (Req 7.6)", "old identifiers refused"),
    ("Fresh clone clean (Req 7.5)", "fresh clone clean"),
    ("Artifacts clean (Req 10.4)", "artifacts clean"),
    ("Remote serves the replacement and only it", None),
)


def test_row_names_has_eleven_names_for_twelve_non_remote_design_table_rows() -> None:
    """An anchor over the ROW SET design.md's `#### ReplacementVerification`
    table defines: 13 rows total, 12 non-remote (excluding the remote-subject
    row, which returns `RefComparisonResult`/`ProbeResult`, never
    `RowResult`), carried as 11 names because the reflog row and the
    unreachable-objects row share one function -- independent of what any
    one fixture happens to iterate."""
    assert len(ROW_NAMES) == 11
    assert len(set(ROW_NAMES)) == 11  # pairwise-distinct, no accidental repeat


def test_row_names_matches_the_design_table_in_the_table_s_own_order() -> None:
    """Reads `design.md`'s `#### ReplacementVerification` table directly and
    asserts `ROW_NAMES` is exactly its non-remote rows' names, in the
    table's own top-to-bottom order (reflog, then unreachable, then old
    identifiers refused). Locates each `_DESIGN_TABLE_ROWS` entry's `Check`-
    cell substring by `str.index` starting after the previous match, so a
    row dropped or reordered in `design.md` -- not merely in this tuple --
    reds this test.

    The monotonic cursor steps over any text between two known rows, so it
    is addition-blind on its own: the body-row count below is what closes
    that, and is the count anchor a walking guard owes. Measured: without
    it, a 14th row inserted mid-table leaves this module green."""
    text = _DESIGN_MD.read_text()
    cursor = text.index("#### ReplacementVerification")
    header = text.index("| Check | Run against |", cursor)
    table = text[header:].split("\n\n")[0]
    body_rows = [
        line
        for line in table.splitlines()[1:]
        if line.startswith("|") and not set(line) <= set("|-: ")
    ]
    assert len(body_rows) == len(_DESIGN_TABLE_ROWS), (
        f"the table has {len(body_rows)} body rows, not "
        f"{len(_DESIGN_TABLE_ROWS)}; a row was added or dropped"
    )
    derived_order: list[str] = []
    for find_text, row_name in _DESIGN_TABLE_ROWS:
        cursor = text.index(find_text, cursor)
        cursor += len(find_text)
        if row_name is not None and (
            not derived_order or derived_order[-1] != row_name
        ):
            derived_order.append(row_name)
    assert tuple(derived_order) == ROW_NAMES


def test_every_single_repo_row_function_emits_a_row_name_from_row_names(
    tmp_path: Path,
) -> None:
    """Every `RowResult.row` string this module's nine row functions that
    return a single `RowResult` against one subject actually emit must be a
    literal member of `ROW_NAMES` -- a typo or a drifted rename in either
    place would otherwise go unnoticed until a caller matched on the wrong
    string."""
    repo = _repo(tmp_path)
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)
    tree_id = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    emitted_rows = {
        check_exactly_one_commit_reachable(repo).row,
        check_tree_identity(repo, tree_id).row,
        check_working_tree_coincides(repo).row,
        check_refs_clean(repo).row,
        check_metadata_clean(repo, frozenset({"t@t", "t"})).row,
        check_no_token_in_any_commit_message(repo, forbidden).row,
        check_no_token_in_path_or_blob(repo, forbidden).row,
        check_old_identifiers_refused(repo, ("f" * 40,)).row,
        check_reflog_and_unreachable_gone(repo, head).row,
    }

    assert len(emitted_rows) == 9
    assert emitted_rows <= set(ROW_NAMES)


# ---------------------------------------------------------------------------
# check_exactly_one_commit_reachable (Req 7.1, 7.2)
# ---------------------------------------------------------------------------


def test_check_exactly_one_commit_reachable_passes_with_the_single_root(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)

    result = check_exactly_one_commit_reachable(repo)

    assert result.passed is True
    assert result.subject == repo
    assert result.row == "exactly one commit reachable"


def test_check_exactly_one_commit_reachable_fails_with_a_second_commit(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "second commit")

    result = check_exactly_one_commit_reachable(repo)

    assert result.passed is False
    assert "2" in result.detail


def test_check_exactly_one_commit_reachable_fails_with_a_second_branch(
    tmp_path: Path,
) -> None:
    """A second commit reachable only from a SECOND branch, not `main` --
    `--all` is load-bearing here; a `HEAD`-only count would report this
    fixture clean."""
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/other")
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "second commit")
    _git(repo, "checkout", "-q", "main")
    head_only_count = _git(repo, "rev-list", "--count", "HEAD").stdout.strip()
    assert head_only_count == "1"

    result = check_exactly_one_commit_reachable(repo)

    assert result.passed is False


# ---------------------------------------------------------------------------
# check_tree_identity (Req 10.3)
# ---------------------------------------------------------------------------


def test_check_tree_identity_passes_when_the_tree_matches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tree_id = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    result = check_tree_identity(repo, tree_id)

    assert result.passed is True
    assert result.subject == repo
    assert result.row == "root tree identical to the certified tip tree"


def test_check_tree_identity_fails_when_the_recorded_tree_id_differs(
    tmp_path: Path,
) -> None:
    """The single-line mutation this row exists to catch: the certified tip
    tree id recorded at gate time no longer matches the root's own tree --
    exercised here directly with a deliberately wrong id, rather than by
    mutating production code, since the row's whole job is to compare an
    externally supplied id against what `HEAD^{tree}` reports."""
    repo = _repo(tmp_path)
    wrong_tree_id = "f" * 40

    result = check_tree_identity(repo, wrong_tree_id)

    assert result.passed is False
    assert wrong_tree_id in result.detail


# ---------------------------------------------------------------------------
# check_working_tree_coincides (Req 10.3) -- tracked files only
# ---------------------------------------------------------------------------


def test_check_working_tree_coincides_passes_with_a_planted_untracked_file(
    tmp_path: Path,
) -> None:
    """The declared correction's whole point (task 7.4): an untracked file
    -- standing in for the untracked root `agent-log` symlink that survives
    every swap by Decision 7 -- must NOT fail this row. The bare,
    untracked-files-included `git status --porcelain` form would red here;
    that is exactly the row this function replaces."""
    repo = _repo(tmp_path)
    (repo / "agent-log").write_text("untracked, never added\n")

    result = check_working_tree_coincides(repo)

    assert result.passed is True
    assert result.subject == repo
    assert result.row == "working tree coincides with the root"


def test_check_working_tree_coincides_fails_on_a_modified_tracked_file(
    tmp_path: Path,
) -> None:
    """A TRACKED file, modified in the working tree but not committed, must
    still fail -- the scoping to tracked files narrows what is IGNORED
    (untracked material), never what is DETECTED (a real divergence in
    tracked state)."""
    repo = _repo(tmp_path)
    (repo / "alpha.txt").write_text("modified after commit\n")

    result = check_working_tree_coincides(repo)

    assert result.passed is False
    assert "alpha.txt" in result.detail


def test_check_working_tree_coincides_fails_on_modified_tracked_with_untracked(
    tmp_path: Path,
) -> None:
    """Both together: a planted untracked file (must be ignored) AND a
    modified tracked file (must still be caught) in the same fixture --
    defeats an implementation that turned off untracked-file scanning
    entirely rather than genuinely restricting to tracked state."""
    repo = _repo(tmp_path)
    (repo / "agent-log").write_text("untracked, never added\n")
    (repo / "alpha.txt").write_text("modified after commit\n")

    result = check_working_tree_coincides(repo)

    assert result.passed is False
    assert "alpha.txt" in result.detail
    assert "agent-log" not in result.detail


# ---------------------------------------------------------------------------
# check_no_token_in_path_or_blob
# ---------------------------------------------------------------------------


def test_check_no_token_in_path_or_blob_passes_when_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_path_or_blob(repo, forbidden)

    assert result.passed is True
    assert result.subject == repo
    assert result.row == "no token in any path or blob of the single commit"


def test_check_no_token_in_path_or_blob_fails_when_a_path_carries_a_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "secretlastname-notes.md").write_text("content\n")
    _git(repo, "add", "secretlastname-notes.md")
    _git(repo, "commit", "-q", "-m", "add notes")
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_path_or_blob(repo, forbidden)

    assert result.passed is False
    assert "secretlastname-notes.md" in result.detail


def test_check_no_token_in_path_or_blob_fails_when_a_blob_carries_a_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("written by secretlastname\n")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-q", "-m", "add notes")
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_path_or_blob(repo, forbidden)

    assert result.passed is False
    assert "token found in blob(s):" in result.detail
    assert "token found in path(s):" not in result.detail


def test_check_no_token_in_path_or_blob_fails_for_a_blob_that_only_exists_in_history(
    tmp_path: Path,
) -> None:
    """The token-bearing blob is unreachable from HEAD's tree (added, then
    deleted, before HEAD) but still reachable through the object graph.
    Only `scripts.purge.plan.enumerate_blob_ids`'s `rev-list --objects --all`
    walk finds it -- a HEAD-only `ls-tree -r HEAD` substitute would report
    this row clean."""
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("written by secretlastname\n")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-q", "-m", "add notes")
    _git(repo, "rm", "-q", "notes.txt")
    _git(repo, "commit", "-q", "-m", "remove notes")
    head_tree = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").stdout
    assert "notes.txt" not in head_tree
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_path_or_blob(repo, forbidden)

    assert result.passed is False


def test_check_no_token_in_path_or_blob_reports_both_surfaces_when_both_hit(
    tmp_path: Path,
) -> None:
    """A token in the PATH and a (different) token in a BLOB, in the same
    fixture -- an implementation that short-circuits after the path scan
    (or the blob scan) would report only one hit; both must be visible in
    `detail` and the row must still fail exactly once."""
    repo = _repo(tmp_path)
    (repo / "secretlastname-notes.md").write_text("credit to othertoken\n")
    _git(repo, "add", "secretlastname-notes.md")
    _git(repo, "commit", "-q", "-m", "add notes")
    forbidden = _forbidden("secretlastname", "othertoken", tmp_path=tmp_path)

    result = check_no_token_in_path_or_blob(repo, forbidden)

    assert result.passed is False
    assert "token found in path(s):" in result.detail
    assert "token found in blob(s):" in result.detail


# ---------------------------------------------------------------------------
# check_no_token_in_any_commit_message
# ---------------------------------------------------------------------------


def test_check_no_token_in_any_commit_message_passes_on_clean_messages(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_any_commit_message(repo, forbidden)

    assert result.passed is True
    assert result.subject == repo


def test_check_no_token_in_any_commit_message_fails_when_a_message_carries_a_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second file\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "credit to secretlastname for this")
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_any_commit_message(repo, forbidden)

    assert result.passed is False


def test_check_no_token_in_any_commit_message_fails_for_a_token_in_the_body(
    tmp_path: Path,
) -> None:
    """A CLEAN subject line, a token only in the BODY -- every other message
    fixture in this module uses a single-line `-m`, which never exercises
    anything beyond the subject. `--format=%B` (the whole message, subject
    and body) is design.md's specified shape precisely because a rewrite's
    own trailer, or a squashed body, is where prose survives; `--format=%s`
    (subject only) would report this row clean."""
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second file\n")
    _git(repo, "add", "beta.txt")
    _git(
        repo,
        "commit",
        "-q",
        "-m",
        "clean subject line",
        "-m",
        "body paragraph crediting secretlastname",
    )
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_any_commit_message(repo, forbidden)

    assert result.passed is False


def test_check_no_token_in_any_commit_message_fails_for_a_message_on_a_second_branch(
    tmp_path: Path,
) -> None:
    """The token-bearing commit is reachable only from a SECOND branch, not
    from `main` (the checked-out HEAD). Only `git log --all` finds it -- a
    `git log` (HEAD-only, first-parent-from-HEAD) substitute would report
    this row clean."""
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/other")
    (repo / "beta.txt").write_text("second file\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "credit to secretlastname for this")
    _git(repo, "checkout", "-q", "main")
    head_log = _git(repo, "log", "--format=%B").stdout
    assert "secretlastname" not in head_log
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_no_token_in_any_commit_message(repo, forbidden)

    assert result.passed is False


# ---------------------------------------------------------------------------
# check_refs_clean
# ---------------------------------------------------------------------------


def test_check_refs_clean_passes_with_only_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = check_refs_clean(repo)

    assert result.passed is True
    assert result.subject == repo


def test_check_refs_clean_fails_with_an_extra_branch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "branch", "feature/stray")

    result = check_refs_clean(repo)

    assert result.passed is False
    assert "feature/stray" in result.detail


def test_check_refs_clean_fails_with_a_surviving_refs_original(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/original/refs/heads/old-branch", head)

    result = check_refs_clean(repo)

    assert result.passed is False
    assert "refs/original" in result.detail


# ---------------------------------------------------------------------------
# check_metadata_clean
# ---------------------------------------------------------------------------


def test_check_metadata_clean_passes_when_every_value_is_allowed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is True
    assert result.subject == repo


def test_check_metadata_clean_fails_on_a_disallowed_author_email(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _git(
        repo,
        "-c",
        "user.email=personal@example.com",
        "-c",
        "user.name=Personal Name",
        "commit",
        "-q",
        "-m",
        "second commit",
    )
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is False
    assert "personal@example.com" in result.detail


def test_check_metadata_clean_fails_on_a_disallowed_author_email_alone(
    tmp_path: Path,
) -> None:
    """The COMMITTER identity is fully allowed; only the AUTHOR email is
    disallowed -- via `_commit_with_identity`, not `-c user.email=...`
    (which sets author and committer identically, the reason the original
    author-email fixture above cannot isolate `%ae` from `%ce`). Unreachable
    if the format string drops `%ae` alone -- e.g. a truncated
    `%ce%n%an%n%cn` -- so it defeats that specific mutation independently of
    every fixture above.

    Worth having on its own merits, not only as a mutation-killer: after a
    `git filter-repo` rewrite the committer is typically re-stamped with the
    configured identity while the AUTHOR is carried over unchanged from the
    original commit -- so a dirty author email beside a clean committer
    email is the most likely residual-identity shape this row exists to
    catch."""
    repo = _repo(tmp_path)
    (repo / "epsilon.txt").write_text("fifth\n")
    _git(repo, "add", "epsilon.txt")
    _commit_with_identity(
        repo,
        message="fifth commit",
        author_name="t",
        author_email="disallowed-author@example.com",
        committer_name="t",
        committer_email="t@t",
    )
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is False
    assert "disallowed-author@example.com" in result.detail


def test_check_metadata_clean_fails_on_a_disallowed_author_name_with_an_allowed_email(
    tmp_path: Path,
) -> None:
    """The EMAIL is allowed on both sides; only the author NAME is
    disallowed. This is unreachable if the format string omits `%an` --
    e.g. a truncated `%ae` or `%ae%n%ce` -- so it defeats that specific
    mutation independently of the email-carrying fixture above."""
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _commit_with_identity(
        repo,
        message="second commit",
        author_name="Personal Real Name",
        author_email="t@t",
        committer_name="t",
        committer_email="t@t",
    )
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is False
    assert "Personal Real Name" in result.detail


def test_check_metadata_clean_fails_on_a_disallowed_committer_email(
    tmp_path: Path,
) -> None:
    """The AUTHOR identity is fully allowed; only the COMMITTER email is
    disallowed. Unreachable if the format string omits `%ce` -- e.g. a
    truncated `%ae` alone -- so it defeats that mutation independently of
    the two fixtures above."""
    repo = _repo(tmp_path)
    (repo / "gamma.txt").write_text("third\n")
    _git(repo, "add", "gamma.txt")
    _commit_with_identity(
        repo,
        message="third commit",
        author_name="t",
        author_email="t@t",
        committer_name="t",
        committer_email="disallowed-committer@example.com",
    )
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is False
    assert "disallowed-committer@example.com" in result.detail


def test_check_metadata_clean_fails_on_a_disallowed_committer_name(
    tmp_path: Path,
) -> None:
    """Both emails and the author NAME are allowed; only the COMMITTER
    NAME is disallowed. Unreachable if the format string omits `%cn` --
    e.g. a truncated `%ae%n%ce%n%an` -- so it defeats that specific
    mutation independently of all three fixtures above (each of which is
    itself already caught by a shorter prefix of the format string)."""
    repo = _repo(tmp_path)
    (repo / "delta.txt").write_text("fourth\n")
    _git(repo, "add", "delta.txt")
    _commit_with_identity(
        repo,
        message="fourth commit",
        author_name="t",
        author_email="t@t",
        committer_name="Disallowed Committer Name",
        committer_email="t@t",
    )
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is False
    assert "Disallowed Committer Name" in result.detail


def test_check_metadata_clean_fails_for_an_identity_on_a_second_branch(
    tmp_path: Path,
) -> None:
    """The disallowed identity is reachable only from a SECOND branch, not
    from `main` (the checked-out HEAD) -- the metadata row's twin of
    `test_check_no_token_in_any_commit_message_fails_for_a_message_on_a_
    second_branch`. Only `git log --all` finds it; a `git log` (HEAD-only)
    substitute would report this row clean."""
    repo = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature/other")
    (repo / "beta.txt").write_text("second file\n")
    _git(repo, "add", "beta.txt")
    _commit_with_identity(
        repo,
        message="second commit",
        author_name="Disallowed Branch Author",
        author_email="disallowed-branch@example.com",
        committer_name="Disallowed Branch Author",
        committer_email="disallowed-branch@example.com",
    )
    _git(repo, "checkout", "-q", "main")
    head_log = _git(repo, "log", "--format=%ae%n%ce%n%an%n%cn").stdout
    assert "disallowed-branch@example.com" not in head_log
    allowed = frozenset({"t@t", "t"})

    result = check_metadata_clean(repo, allowed)

    assert result.passed is False
    assert "disallowed-branch@example.com" in result.detail


# ---------------------------------------------------------------------------
# check_old_identifiers_refused (Req 7.6)
# ---------------------------------------------------------------------------


def test_check_old_identifiers_refused_fails_when_the_id_still_resolves(
    tmp_path: Path,
) -> None:
    """A repository that has NOT actually had the identifier removed --
    e.g. a plain, un-rewritten fixture -- must fail this row: the id still
    resolves via `git cat-file -e`."""
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = check_old_identifiers_refused(repo, (head,))

    assert result.passed is False
    assert head in result.detail


def test_check_old_identifiers_refused_passes_when_the_id_is_absent(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    fake_sha = "f" * 40

    result = check_old_identifiers_refused(repo, (fake_sha,))

    assert result.passed is True
    assert result.subject == repo


def test_check_old_identifiers_refused_fails_when_a_second_id_still_resolves(
    tmp_path: Path,
) -> None:
    """A three-element sample with the resolvable id in the MIDDLE. Both
    outer ids are genuinely absent (fake shas). A walk truncated to
    `old_ids[:1]` sees only an absent id and reports clean; so does one
    truncated to `old_ids[-1:]`. Req 7.6 requires a non-zero result for
    EVERY sampled id, so both truncation directions must fail."""
    repo = _repo(tmp_path)
    fake_sha = "f" * 40
    other_fake_sha = "e" * 40
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = check_old_identifiers_refused(repo, (fake_sha, head, other_fake_sha))

    assert result.passed is False
    assert head in result.detail


def test_check_old_identifiers_refused_raises_on_an_empty_sample(
    tmp_path: Path,
) -> None:
    """An empty sample must raise, not report a vacuous pass -- a check that
    refused zero identifiers has proven nothing."""
    repo = _repo(tmp_path)

    with pytest.raises(VerificationInputsError):
        check_old_identifiers_refused(repo, ())


# ---------------------------------------------------------------------------
# check_reflog_and_unreachable_gone (R only)
# ---------------------------------------------------------------------------


def test_check_reflog_and_unreachable_gone_passes_referencing_only_allowed(
    tmp_path: Path,
) -> None:
    """Declared correction (this fix): the reflog half no longer demands
    literal emptiness. `_repo` leaves a genuinely non-empty reflog (branch
    creation, one commit) -- the retired literal-`not reflog` contract would
    have failed this exact state -- but every non-zero id in it is the
    allowed commit itself, so the row must PASS. Falsity in the starting
    state: the reflog is asserted non-empty before the call."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    reflog_before = _git(repo, "reflog", "show", "--all").stdout
    assert reflog_before.strip() != ""

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is True
    assert result.subject == repo


def test_check_reflog_and_unreachable_gone_fails_on_a_disallowed_commit_id(
    tmp_path: Path,
) -> None:
    """A reflog line naming a REAL, resolvable commit other than the allowed
    one must still fail -- the ordinary case the walk exists to catch,
    independent of the absent-object edge case below."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "second commit")
    disallowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert disallowed != allowed

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert disallowed in result.detail


def test_check_reflog_and_unreachable_gone_fails_on_a_reflog_id_whose_object_is_absent(
    tmp_path: Path,
) -> None:
    """The motivating defect this fix closes: a reflog file holding a
    pre-replacement id whose object no longer exists in the object
    database. Measured directly below: `git reflog show --all` silently
    omits this exact line -- the planted line is invisible to it, though
    `reflog show --all` is not itself empty here (this fixture's `_repo`
    already carries one real, resolvable commit, so a literal-emptiness
    contract would fail this state anyway, just not by seeing the planted
    line). This row must FAIL it instead, because it reads the file on
    disk, never `reflog show`'s output."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    absent_object_id = "a" * 40
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", absent_object_id],
        capture_output=True,
    )
    assert probe.returncode != 0  # falsity check: the object really is absent

    log_path = repo / ".git" / "logs" / "HEAD"
    with log_path.open("a") as fh:
        fh.write(
            f"{'0' * 40} {absent_object_id} tester <t@t> 1700000000 +0000"
            "\tcommit (initial): pre-replacement id whose object is gone\n"
        )

    # The blind spot this row exists to close, measured: `reflog show --all`
    # cannot see the planted line at all.
    reflog_show = _git(repo, "reflog", "show", "--all").stdout
    assert absent_object_id not in reflog_show

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert absent_object_id in result.detail


def test_check_reflog_and_unreachable_gone_fails_via_the_scan_alone_on_an_absent_id(
    tmp_path: Path,
) -> None:
    """Isolates the id-scan mechanism from the previous test's `fsck`
    interaction: measured, real git's `fsck --unreachable --dangling`
    independently flags ANY well-formed reflog line naming an absent
    object as `invalid reflog entry <id>` (exit 2) regardless of which ref
    or how the line got there -- so the previous test's failure is doubly
    defended and does not, by itself, prove the id-scan (as opposed to the
    `fsck` fallback) is what is doing the work. This fixture instead writes
    the id inside a line `git`'s own reflog parser does not recognise as an
    entry at all (a `#`-prefixed comment, not `<old> <new> <ident> <ts>
    <tz>\\t<msg>`) -- measured below, `git fsck` reports this fixture
    clean, so ONLY the raw-text id-scan can be what fails this row."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    absent_object_id = "c" * 40
    probe = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", absent_object_id],
        capture_output=True,
    )
    assert probe.returncode != 0  # falsity check: the object really is absent

    log_path = repo / ".git" / "logs" / "HEAD"
    with log_path.open("a") as fh:
        fh.write(f"# stray line mentioning {absent_object_id} for testing\n")

    # Falsity in the starting state, and proof of isolation: fsck sees
    # nothing wrong with this fixture (unlike the well-formed-entry case
    # above).
    fsck_before = subprocess.run(
        ["git", "-C", str(repo), "fsck", "--unreachable", "--dangling"],
        capture_output=True,
        text=True,
    )
    assert fsck_before.returncode == 0
    assert fsck_before.stdout.strip() == ""
    assert fsck_before.stderr.strip() == ""

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert absent_object_id in result.detail
    assert "fsck" not in result.detail


def test_check_reflog_and_unreachable_gone_fails_on_a_dangling_unreachable_object(
    tmp_path: Path,
) -> None:
    """After `reflog expire`, the reflog itself is empty, but a genuinely
    unreachable object (created by `reset --hard` to an earlier commit) is
    still present until `gc --prune` runs -- this must still fail, proving
    the `fsck` half of the check discriminates independently of the reflog
    half."""
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "second commit")
    first_commit = _git(repo, "rev-parse", "HEAD~1").stdout.strip()
    _git(repo, "reset", "-q", "--hard", first_commit)
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    reflog_after_expire = _git(repo, "reflog", "show", "--all").stdout
    assert reflog_after_expire.strip() == ""

    result = check_reflog_and_unreachable_gone(repo, first_commit)

    assert result.passed is False
    assert "fsck" in result.detail


def test_check_reflog_and_unreachable_gone_passes_after_expire_and_gc(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "beta.txt").write_text("second\n")
    _git(repo, "add", "beta.txt")
    _git(repo, "commit", "-q", "-m", "second commit")
    first_commit = _git(repo, "rev-parse", "HEAD~1").stdout.strip()
    _git(repo, "reset", "-q", "--hard", first_commit)
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "-q", "--prune=now")

    result = check_reflog_and_unreachable_gone(repo, first_commit)

    assert result.passed is True


def _commit_tree_off_ref(repo: Path, *, parent: str, message: str) -> str:
    """A raw commit object, resolvable via `git cat-file`, that touches NO
    ref and writes NO reflog entry anywhere -- unlike `git commit`, which
    always updates the current branch's ref and its log file. Used to plant
    a genuinely disallowed, resolvable id into exactly one log file, without
    also leaving a trace in `refs/heads/main`'s own log the way `git commit`
    followed by `git reset --hard` would (that combination writes the same
    id into `refs/heads/main`'s log too, confounding a test that wants to
    isolate one specific `logs/**` subtree)."""
    tree = _git(repo, "rev-parse", f"{parent}^{{tree}}").stdout.strip()
    result = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree, "-p", parent, "-m", message],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_check_reflog_and_unreachable_gone_scans_the_remotes_logs_subtree(
    tmp_path: Path,
) -> None:
    """The walk must cover `logs/refs/remotes/**`, not merely `logs/HEAD`
    and `logs/refs/heads`. `disallowed` is built through `commit-tree`
    (`_commit_tree_off_ref`) rather than `git commit`, so it appears in NO
    log file except the one planted by hand below -- `refs/heads/main`'s own
    log is untouched by this fixture, which is what makes this test isolate
    the `remotes` subtree specifically rather than being satisfied by
    `refs/heads/main` alone. No remote exists in this fixture -- the
    directory and file are created by hand -- so before the plant, this
    subtree does not exist at all (falsity in the starting state)."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    disallowed = _commit_tree_off_ref(repo, parent=allowed, message="off-ref commit")
    main_log_before = (repo / ".git" / "logs" / "refs" / "heads" / "main").read_text()
    assert disallowed not in main_log_before
    remote_log = repo / ".git" / "logs" / "refs" / "remotes" / "origin" / "main"
    assert not remote_log.exists()
    remote_log.parent.mkdir(parents=True)
    remote_log.write_text(
        f"{'0' * 40} {disallowed} tester <t@t> 1700000000 +0000"
        "\tfetch: fetched from origin\n"
    )

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert disallowed in result.detail


def test_check_reflog_and_unreachable_gone_scans_the_stash_log(
    tmp_path: Path,
) -> None:
    """The walk must cover `logs/refs/stash`, not merely `logs/HEAD` and
    `logs/refs/heads`. `disallowed` is built through `commit-tree`
    (`_commit_tree_off_ref`), so it appears in NO log file except the one
    planted by hand below -- see that helper's docstring for why a `git
    commit`/`reset --hard` pair would confound this isolation. Nothing was
    ever stashed in this fixture -- the file is created by hand -- so before
    the plant, this file does not exist at all (falsity in the starting
    state)."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    disallowed = _commit_tree_off_ref(repo, parent=allowed, message="off-ref commit")
    main_log_before = (repo / ".git" / "logs" / "refs" / "heads" / "main").read_text()
    assert disallowed not in main_log_before
    stash_log = repo / ".git" / "logs" / "refs" / "stash"
    assert not stash_log.exists()
    stash_log.write_text(
        f"{'0' * 40} {disallowed} tester <t@t> 1700000000 +0000\tstash: pushed\n"
    )

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert disallowed in result.detail


def test_check_reflog_and_unreachable_gone_fails_for_a_stale_reflog_on_a_second_branch(
    tmp_path: Path,
) -> None:
    """The retired `LocalVerification`-era second-branch scenario, rebuilt
    against this row's new per-file id-scan mechanism (a declared
    correction, this fix). A foreign id is planted into
    `logs/refs/heads/other` ONLY -- never `logs/HEAD` -- so this test cannot
    pass via the `HEAD` log: it isolates the walk's coverage of
    `logs/refs/heads/**` beyond the single branch (`main`) a real
    `run_replace` swap leaves behind (module docstring: the swapped
    repository carries exactly `logs/HEAD` and `logs/refs/heads/main`, no
    `other`). `disallowed` is built through `commit-tree`
    (`_commit_tree_off_ref`), so it appears in NO log file except the one
    planted by hand below -- see that helper's docstring for why a `git
    commit`/`reset --hard` pair would confound this isolation. Measured
    falsity below: before the plant, `logs/HEAD` does not contain
    `disallowed` and `logs/refs/heads/other` does not exist at all. This is
    the exact property a mutant that blinds the walk to every path
    containing `refs/heads` (leaving only `logs/HEAD` scanned) would defeat
    -- and did, before this test existed."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    disallowed = _commit_tree_off_ref(
        repo, parent=allowed, message="off-ref commit on a second branch"
    )
    head_log_before = (repo / ".git" / "logs" / "HEAD").read_text()
    assert disallowed not in head_log_before
    other_log = repo / ".git" / "logs" / "refs" / "heads" / "other"
    assert not other_log.exists()
    other_log.parent.mkdir(parents=True, exist_ok=True)
    other_log.write_text(
        f"{'0' * 40} {disallowed} tester <t@t> 1700000000 +0000"
        "\tbranch: Created from HEAD\n"
    )

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert disallowed in result.detail


def test_check_reflog_and_unreachable_gone_does_not_crash_on_non_utf8_committer_bytes(
    tmp_path: Path,
) -> None:
    """A reflog line's committer name is history-controlled bytes, never
    validated as UTF-8 by git's own reflog format -- a declared correction
    (this fix): the walk used to read every log file through
    `Path.read_text()`'s default UTF-8 codec, which raises
    `UnicodeDecodeError` and crashes this row (rather than failing it) on a
    non-UTF-8 byte. Measured falsity below: the planted byte (`0xe9`, valid
    latin-1, not valid standalone UTF-8) really does make the default-codec
    `read_text()` raise on this exact file. The row itself must not raise --
    it must still find and report the disallowed id planted in the same
    line, the same "fail, never crash" posture this function's docstring
    already states for its `fsck` half."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    disallowed = _commit_tree_off_ref(
        repo, parent=allowed, message="off-ref commit behind a non-utf8 name"
    )
    log_path = repo / ".git" / "logs" / "HEAD"
    prefix = f"{'0' * 40} {disallowed} ".encode("ascii")
    name = "latin1 committer name ".encode("ascii") + bytes([0xE9])
    suffix = " <t@t> 1700000000 +0000\tcommit: non-utf8 committer name\n".encode(
        "ascii"
    )
    with log_path.open("ab") as fh:
        fh.write(prefix + name + suffix)
    with pytest.raises(UnicodeDecodeError):
        log_path.read_text()  # falsity check: the default codec really does raise

    result = check_reflog_and_unreachable_gone(repo, allowed)  # must not raise

    assert result.passed is False
    assert disallowed in result.detail


def test_check_reflog_and_unreachable_gone_fails_on_a_zero_padded_filemode_warning(
    tmp_path: Path,
) -> None:
    """M13's exact target: the `rc==0 && stdout empty && stderr non-empty`
    fsck shape. A `fsck --unreachable --dangling` reimplementation that
    reads only stdout and ignores the exit code would report this state
    clean; this row's `fsck_output = (fsck_proc.stdout + fsck_proc.stderr)
    .strip()` and `fsck_clean = fsck_proc.returncode == 0 and not
    fsck_output` combination catches it because stderr is folded in even
    though the exit code itself is 0 here.

    Built with `git hash-object -w -t tree --literally` -- a real git tree
    object carrying a zero-padded file mode (`0100644` rather than
    `100644`), which git's normal tree-write path normalises away and only
    `--literally` bypasses -- committed via `commit-tree` as a PARENTLESS
    root and pointed at by `refs/heads/main` via `update-ref`, never through
    `git commit` and never through any of this module's own code. Built as
    the repository's first and only commit specifically so `update-ref`'s
    own reflog write (`git update-ref` logs even though `git commit` never
    ran) carries only `0*40 -> commit_id` in both `logs/HEAD` and
    `logs/refs/heads/main` -- measured below -- isolating this fixture to
    the `fsck` half alone: a second, earlier commit (as `_repo` provides)
    would leave that earlier commit's own id as the reflog's "old" side,
    which is neither `commit_id` nor all-zeros and would fail the reflog
    half too, confounding which half of the row actually discriminates.
    Measured falsity below, directly against real git, before the row is
    called: `fsck` exits `0`, stdout is empty, and stderr carries the
    `zeroPaddedFilemode` warning -- so this fixture cannot be satisfied by a
    returncode check alone, nor by a stdout-only check alone. It is the
    stderr fold that catches THIS fixture: measured, dropping the
    `fsck_proc.returncode == 0` conjunct on its own leaves this test green,
    so that conjunct is defensive here and no fixture in this module pins it
    (queued follow-up). What this test pins is the stderr fold."""
    repo = tmp_path / "zero-padded-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "alpha.txt").write_text("first commit content\n")
    blob_id = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-w", "alpha.txt"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree_content = tmp_path / "zero-padded-tree-content"
    tree_content.write_bytes(b"0100644 alpha.txt\x00" + bytes.fromhex(blob_id))
    tree_id = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "hash-object",
            "-w",
            "-t",
            "tree",
            "--literally",
            str(tree_content),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    commit_id = subprocess.run(
        ["git", "-C", str(repo), "commit-tree", tree_id, "-m", "zp"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(repo, "update-ref", "refs/heads/main", commit_id)
    head_log = (repo / ".git" / "logs" / "HEAD").read_text()
    main_log = (repo / ".git" / "logs" / "refs" / "heads" / "main").read_text()
    assert commit_id in head_log and commit_id in main_log
    assert "0" * 40 in head_log and "0" * 40 in main_log

    fsck_before = subprocess.run(
        ["git", "-C", str(repo), "fsck", "--unreachable", "--dangling"],
        capture_output=True,
        text=True,
    )
    assert fsck_before.returncode == 0
    assert fsck_before.stdout.strip() == ""
    assert fsck_before.stderr.strip() != ""

    result = check_reflog_and_unreachable_gone(repo, commit_id)

    assert result.passed is False
    assert "fsck" in result.detail


def test_check_reflog_and_unreachable_gone_catches_a_64_hex_id(
    tmp_path: Path,
) -> None:
    """The id pattern must catch a 64-hex (sha256) id, not only 40-hex --
    the widening this fix makes. Plants a foreign 64-hex string, distinct
    from any 40-hex substring reading of it, and asserts it is reported
    whole, not merely detected."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    sha256_like = "b" * 64
    log_path = repo / ".git" / "logs" / "HEAD"
    with log_path.open("a") as fh:
        fh.write(
            f"{'0' * 40} {sha256_like} tester <t@t> 1700000000 +0000"
            "\tcommit: a sha256-shaped foreign id\n"
        )

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is False
    assert sha256_like in result.detail


def test_check_reflog_and_unreachable_gone_ignores_a_41_hex_run_boundary_case(
    tmp_path: Path,
) -> None:
    """Pins the id pattern's negative lookarounds (`.kiro/queue/2026-08-19-
    reflog-id-scan-is-sha1-only-and-misses-the-common-dir.md`'s "widened ...
    with the negative lookarounds pinned" claim, otherwise unsubstantiated).
    A run of 41 consecutive hex characters is neither a 40-hex nor a 64-hex
    id -- it is one hex digit too long to be either -- so it must be
    reported CLEAN: without the lookarounds, `[0-9a-f]{40}` alone would
    still match the run's first 40 characters as a spurious, well-formed-
    looking "id" that is not actually a valid-length id embedded there at
    all (this exact false positive is `M15`, the mutation that deletes both
    lookarounds and leaves the rest of this module's suite green -- run
    manually, confirmed to red only this test). A run this long and uniform
    stands in for a plausible real shape: a long hex-looking string in a
    reflog message (a content hash, a truncated-differently digest) abutting
    or overlapping what would otherwise read as a valid id length."""
    repo = _repo(tmp_path)
    allowed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    boundary_run = "d" * 41
    log_path = repo / ".git" / "logs" / "HEAD"
    with log_path.open("a") as fh:
        fh.write(
            f"{'0' * 40} {allowed} tester <t@t> 1700000000 +0000"
            f"\tcommit: mentions {boundary_run} in passing\n"
        )

    result = check_reflog_and_unreachable_gone(repo, allowed)

    assert result.passed is True
    assert result.detail == "clean"


def test_check_reflog_and_unreachable_gone_raises_on_a_missing_logs_directory(
    tmp_path: Path,
) -> None:
    """A walk over a nonexistent `.git/logs` must raise
    `VerificationInputsError` rather than pass having scanned nothing -- the
    vacuous-walk guard, pointed at the wrong directory."""
    repo = tmp_path / "not-a-repo"
    repo.mkdir()

    with pytest.raises(VerificationInputsError):
        check_reflog_and_unreachable_gone(repo, "f" * 40)


# `check_commit_map_complete` and `check_no_mailmap` -- and their tests --
# are deleted with the mechanism whose subject no longer exists (task 7.4;
# scripts/purge/verify.py module docstring; design.md `####
# ReplacementVerification`, "Reuse, not rebuild").


# ---------------------------------------------------------------------------
# clone_without_local (Req 7.5)
# ---------------------------------------------------------------------------


def test_clone_without_local_produces_a_clone_with_no_alternates_file(
    tmp_path: Path,
) -> None:
    source = _repo(tmp_path, name="source")
    dest = tmp_path / "clone"

    returned = clone_without_local(source, dest)

    assert returned == dest
    assert (dest / "alpha.txt").read_text() == "first commit content\n"
    assert not (dest / ".git" / "objects" / "info" / "alternates").exists()


def test_clone_without_local_leaves_no_unreachable_object_behind(
    tmp_path: Path,
) -> None:
    """The stronger form: take the clone THROUGH `clone_without_local`
    itself (not a raw `subprocess.run` positive control) from a source that
    genuinely carries an unreachable object, and assert the clone has none.
    This is the one assertion that actually depends on `clone_without_local`
    passing `--no-local` rather than `--local` -- on this machine, neither
    flag leaves an `alternates` file behind (see the positive control
    below), so `_assert_no_alternates` alone cannot catch a `--local`
    regression; this can."""
    source = _repo(tmp_path, name="source")
    (source / "beta.txt").write_text("second\n")
    _git(source, "add", "beta.txt")
    _git(source, "commit", "-q", "-m", "second commit")
    first_commit = _git(source, "rev-parse", "HEAD~1").stdout.strip()
    _git(source, "reset", "-q", "--hard", first_commit)
    # The reflog itself keeps the discarded commit reachable until expired --
    # expire it so the object is genuinely unreachable, not merely
    # reflog-pinned (matches `check_reflog_and_unreachable_gone`'s own
    # fixtures above).
    _git(source, "reflog", "expire", "--expire=now", "--all")
    # Falsity in the starting state: the SOURCE does carry an unreachable
    # object before the clone is taken.
    source_fsck = _git(source, "fsck", "--unreachable", "--dangling").stdout
    assert source_fsck.strip() != ""
    dest = tmp_path / "clone"

    clone_without_local(source, dest)

    dest_fsck = _git(dest, "fsck", "--unreachable", "--dangling").stdout
    assert dest_fsck.strip() == ""


def test_local_clone_carries_unreachable_objects_but_no_local_clone_does_not(
    tmp_path: Path,
) -> None:
    """Positive control on the underlying git behaviour this whole row
    exists to distrust -- design.md's own "controlled experiment": a
    `--local` clone hardlinks the object directory, unreachable objects
    included, while `--no-local` does not carry them across at all.
    `clone_without_local`'s deliberate `--no-local` choice is therefore not
    a distinction without a difference. (Measured on this machine's git:
    neither flag leaves an `alternates` file behind -- that assertion lives
    on `clone_without_local`/`_assert_no_alternates` as a separate hygiene
    guard against `--shared`/`--reference`, tested directly below, not as
    the thing that differentiates `--local` from `--no-local`.)"""
    source = _repo(tmp_path, name="source")
    (source / "beta.txt").write_text("second\n")
    _git(source, "add", "beta.txt")
    _git(source, "commit", "-q", "-m", "second commit")
    first_commit = _git(source, "rev-parse", "HEAD~1").stdout.strip()
    _git(source, "reset", "-q", "--hard", first_commit)

    local_dest = tmp_path / "local-clone"
    nolocal_dest = tmp_path / "nolocal-clone"
    subprocess.run(
        ["git", "clone", "--local", "--", str(source), str(local_dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "clone", "--no-local", "--", str(source), str(nolocal_dest)],
        check=True,
        capture_output=True,
        text=True,
    )

    local_fsck = _git(local_dest, "fsck", "--unreachable", "--dangling").stdout
    nolocal_fsck = _git(nolocal_dest, "fsck", "--unreachable", "--dangling").stdout

    assert local_fsck.strip() != ""
    assert nolocal_fsck.strip() == ""


def test_assert_no_alternates_raises_when_the_file_is_planted(tmp_path: Path) -> None:
    """The extracted guard `clone_without_local` calls after every clone:
    plant the exact file at the exact path it inspects and confirm it
    raises. Directly testable this way, independent of what any particular
    git version's `--no-local` flag happens to do on the machine running the
    test (see `test_local_clone_carries_unreachable_objects_but_no_local_clone_does_not`
    for the git-behaviour side of the story)."""
    from scripts.purge.verify import _assert_no_alternates  # noqa: PLC2701

    dest = tmp_path / "clone"
    alternates = dest / ".git" / "objects" / "info" / "alternates"
    alternates.parent.mkdir(parents=True)
    alternates.write_text("/some/other/repo/.git/objects\n")

    with pytest.raises(VerificationCloneError):
        _assert_no_alternates(dest)


def test_assert_no_alternates_does_not_raise_when_the_file_is_absent(
    tmp_path: Path,
) -> None:
    from scripts.purge.verify import _assert_no_alternates  # noqa: PLC2701

    dest = tmp_path / "clone"
    (dest / ".git" / "objects" / "info").mkdir(parents=True)

    _assert_no_alternates(dest)  # must not raise


def test_clone_without_local_actually_invokes_the_alternates_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the WIRING, not just the guard: `clone_without_local` must call
    `_assert_no_alternates` on every clone, not merely define it. A forced
    raise from the (monkeypatched) guard must propagate out of
    `clone_without_local` -- if the call were ever dropped, this raise would
    never happen and the test would fail to raise."""
    import scripts.purge.verify as verify_module

    source = _repo(tmp_path, name="source")
    dest = tmp_path / "clone"

    def _always_raise(_dest: Path) -> None:
        raise VerificationCloneError("forced for wiring test")

    monkeypatch.setattr(verify_module, "_assert_no_alternates", _always_raise)

    with pytest.raises(VerificationCloneError, match="forced for wiring test"):
        clone_without_local(source, dest)


# ---------------------------------------------------------------------------
# check_fresh_clone (Req 7.5)
# ---------------------------------------------------------------------------


def test_check_fresh_clone_reruns_the_tree_identity_token_message_and_old_id_rows(
    tmp_path: Path,
) -> None:
    source = _repo(tmp_path, name="source")
    (source / "notes.txt").write_text("written by secretlastname\n")
    _git(source, "add", "notes.txt")
    _git(source, "commit", "-q", "-m", "notes")
    dest = tmp_path / "clone"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)
    tree_id = _git(source, "rev-parse", "HEAD^{tree}").stdout.strip()
    fake_old_id = "f" * 40

    results = check_fresh_clone(
        replaced_repo=source,
        clone_dest=dest,
        certified_tree_id=tree_id,
        forbidden=forbidden,
        old_ids=(fake_old_id,),
    )

    assert len(results) == 4
    # Every returned row's subject is the CLONE, never the source repo --
    # Req 7.4's "every row names the repository it runs against", exercised
    # on the fresh-clone composition specifically.
    assert all(r.subject == dest for r in results)
    token_row = next(
        r
        for r in results
        if r.row == "no token in any path or blob of the single commit"
    )
    assert token_row.passed is False
    tree_row = next(
        r for r in results if r.row == "root tree identical to the certified tip tree"
    )
    assert tree_row.passed is True
    old_id_row = next(r for r in results if r.row == "old identifiers refused")
    assert old_id_row.passed is True


def test_check_fresh_clone_reds_when_the_certified_tree_id_is_wrong(
    tmp_path: Path,
) -> None:
    """The tree-identity row re-run against the clone must discriminate too
    -- a wrong `certified_tree_id` passed through `check_fresh_clone` must
    surface as a failing row, not be silently swallowed by the aggregation."""
    source = _repo(tmp_path, name="source")
    dest = tmp_path / "clone"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    results = check_fresh_clone(
        replaced_repo=source,
        clone_dest=dest,
        certified_tree_id="f" * 40,
        forbidden=forbidden,
        old_ids=("e" * 40,),
    )

    tree_row = next(
        r for r in results if r.row == "root tree identical to the certified tip tree"
    )
    assert tree_row.passed is False


def test_check_fresh_clone_reruns_old_identifiers_refused_against_the_clone(
    tmp_path: Path,
) -> None:
    """design.md:1615 marks "old identifiers refused" `W, C` -- run against
    both the working repository and the fresh verification clone. Uses a
    fixture that was never actually put through `HistoryReplacement`, so an
    identifier genuinely present in `source`'s own history is still
    resolvable inside `dest` too (a `--no-local` clone of an un-rewritten
    repository carries its history across unchanged): this proves the row
    is actually RE-RUN against `clone_dest`, not merely defaulted to a
    vacuous pass."""
    source = _repo(tmp_path, name="source")
    dest = tmp_path / "clone"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)
    tree_id = _git(source, "rev-parse", "HEAD^{tree}").stdout.strip()
    old_head = _git(source, "rev-parse", "HEAD").stdout.strip()

    results = check_fresh_clone(
        replaced_repo=source,
        clone_dest=dest,
        certified_tree_id=tree_id,
        forbidden=forbidden,
        old_ids=(old_head,),
    )

    old_id_row = next(r for r in results if r.row == "old identifiers refused")
    assert old_id_row.subject == dest
    assert old_id_row.passed is False
    assert old_head in old_id_row.detail


def test_check_fresh_clone_forwards_a_multi_element_old_ids_sample_unfiltered(
    tmp_path: Path,
) -> None:
    """`old_ids` at `check_fresh_clone`'s own call site must not be
    truncated -- mirrors `test_check_old_identifiers_refused_fails_when_a_
    second_id_still_resolves`'s three-element, resolvable-in-the-middle
    shape one level down. Uses a fixture that was never actually put
    through `HistoryReplacement`, so `old_head` (the second of three ids)
    is genuinely still resolvable inside `dest` (a `--no-local` clone of an
    un-rewritten repository carries its history across unchanged); both
    outer ids are absent fake shas. `tuple(old_ids)[:1]` would see only the
    first, absent id and report clean -- this must fail."""
    source = _repo(tmp_path, name="source")
    dest = tmp_path / "clone"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)
    tree_id = _git(source, "rev-parse", "HEAD^{tree}").stdout.strip()
    old_head = _git(source, "rev-parse", "HEAD").stdout.strip()
    fake_first = "f" * 40
    fake_last = "e" * 40

    results = check_fresh_clone(
        replaced_repo=source,
        clone_dest=dest,
        certified_tree_id=tree_id,
        forbidden=forbidden,
        old_ids=(fake_first, old_head, fake_last),
    )

    old_id_row = next(r for r in results if r.row == "old identifiers refused")
    assert old_id_row.passed is False
    assert old_head in old_id_row.detail


def test_check_fresh_clone_raises_on_an_empty_old_ids_sample(tmp_path: Path) -> None:
    """The same vacuous-walk guard `check_old_identifiers_refused` enforces
    on its own must not be bypassable by routing the call through
    `check_fresh_clone` with an empty sample."""
    source = _repo(tmp_path, name="source")
    dest = tmp_path / "clone"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)
    tree_id = _git(source, "rev-parse", "HEAD^{tree}").stdout.strip()

    with pytest.raises(VerificationInputsError):
        check_fresh_clone(
            replaced_repo=source,
            clone_dest=dest,
            certified_tree_id=tree_id,
            forbidden=forbidden,
            old_ids=(),
        )


# ---------------------------------------------------------------------------
# built artifacts (Req 10.4)
# ---------------------------------------------------------------------------


def test_iter_archive_members_zip_skips_directory_entries(tmp_path: Path) -> None:
    archive = tmp_path / "sample.whl"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("pkg/", "")
        zf.writestr("pkg/file.txt", "hello from the wheel\n")

    members = dict(_iter_archive_members(archive))

    assert members == {"pkg/file.txt": b"hello from the wheel\n"}


def test_iter_archive_members_tar_skips_directory_entries(tmp_path: Path) -> None:
    archive = tmp_path / "sample.tar.gz"
    directory = tmp_path / "payload"
    directory.mkdir()
    (directory / "file.txt").write_text("hello from the sdist\n")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(directory, arcname="pkg")

    members = dict(_iter_archive_members(archive))

    assert members == {"pkg/file.txt": b"hello from the sdist\n"}


def test_iter_archive_members_tar_reads_a_symlink_to_an_in_archive_target(
    tmp_path: Path,
) -> None:
    """A symlink whose target IS present in the archive must be readable --
    `member.isfile()` is `False` for a symlink too, so a naive
    `if not member.isfile(): continue` guard would silently DROP this
    readable, scannable member. `TarFile.extractfile` handles it fine; this
    pins that the function does not add its own blind spot on top."""
    archive = tmp_path / "sample.tar.gz"
    directory = tmp_path / "payload"
    directory.mkdir()
    (directory / "real.txt").write_text("hello from the real file\n")
    (directory / "link.txt").symlink_to("real.txt")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(directory, arcname="pkg")

    members = dict(_iter_archive_members(archive))

    assert members["pkg/link.txt"] == b"hello from the real file\n"


def test_iter_archive_members_tar_does_not_crash_on_a_dangling_symlink(
    tmp_path: Path,
) -> None:
    """The exact shape `.kiro/queue/2026-07-31-agent-log-symlink-ships-in-
    sdist.md` records this project's own built sdist carrying: a symlink
    whose target is NOT present in the archive. `TarFile.extractfile` raises
    `KeyError` for this -- not merely returns `None` -- so a version of this
    function that only guards `extractfile(...) is None` still crashes here.
    The member must come back with `content is None`, never propagate the
    `KeyError`."""
    archive = tmp_path / "sample.tar.gz"
    directory = tmp_path / "payload"
    directory.mkdir()
    (directory / "dangling.txt").symlink_to("nowhere.txt")
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(directory, arcname="pkg")

    members = dict(_iter_archive_members(archive))  # must not raise

    assert members == {"pkg/dangling.txt": None}


def _fixture_project(
    root: Path,
    *,
    extra_line: str | None,
    readme_line: str | None = None,
    root_extra_filename: str | None = None,
) -> None:
    """A minimal hatchling-buildable project. `readme_line`, appended to
    `README.md`, is a way to plant content that ships in the SDIST but not
    the WHEEL (this fixture's wheel target only declares the
    `verify_fixture` package, never `README.md`) -- `wheel`-only tests
    cannot exercise the sdist half of Req 10.4. `root_extra_filename`, when
    given, adds an EMPTY-content file of that name at the PROJECT ROOT
    (never inside the `verify_fixture` package): the sdist's default
    include copies the whole source tree, so this file ships there, but the
    wheel target only declares `verify_fixture`, so it never appears in the
    wheel AT ALL -- not even indirectly via `dist-info/RECORD`, which (for a
    file that DOES ship in the wheel) lists every wheel member's path as
    RECORD's own content and would otherwise let a content-only scan
    "accidentally" catch a path-only hit through RECORD's text."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        """
[project]
name = "verify-fixture"
version = "0.0.1"
requires-python = ">=3.11"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["verify_fixture"]
"""
    )
    readme = "clean readme, nothing forbidden here\n"
    if readme_line is not None:
        readme += readme_line + "\n"
    (root / "README.md").write_text(readme)
    pkg = root / "verify_fixture"
    pkg.mkdir()
    content = "clean fixture content, nothing forbidden here\n"
    if extra_line is not None:
        content += extra_line + "\n"
    (pkg / "__init__.py").write_text(content)
    if root_extra_filename is not None:
        (root / root_extra_filename).write_text("clean content, name is the hit\n")


def test_check_built_artifacts_passes_on_a_clean_project(tmp_path: Path) -> None:
    project = tmp_path / "clean-project"
    _fixture_project(project, extra_line=None)
    output_dir = tmp_path / "clean-dist"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    sdist, wheel = build_artifacts(project, output_dir)
    result = check_built_artifacts(
        subject=project,
        sdist=sdist,
        wheel=wheel,
        forbidden=forbidden,
        fingerprints=frozenset({digest(["999"], _SALT)}),
        window_lengths=frozenset({1}),
        salt=_SALT,
    )

    assert result.passed is True
    assert result.subject == project
    # `ROW_NAMES`' own docstring claims `check_built_artifacts` reports as
    # `"artifacts clean"` -- an otherwise-unpinned prose claim. Renaming
    # either the production `row=` literal or its `ROW_NAMES` entry must
    # break this.
    assert result.row == "artifacts clean"
    assert result.row in ROW_NAMES


def test_check_built_artifacts_fails_when_a_token_ships_in_the_wheel(
    tmp_path: Path,
) -> None:
    project = tmp_path / "dirty-project"
    _fixture_project(project, extra_line="written by secretlastname")
    output_dir = tmp_path / "dirty-dist"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    sdist, wheel = build_artifacts(project, output_dir)
    result = check_built_artifacts(
        subject=project,
        sdist=sdist,
        wheel=wheel,
        forbidden=forbidden,
        fingerprints=frozenset({digest(["999"], _SALT)}),
        window_lengths=frozenset({1}),
        salt=_SALT,
    )

    assert result.passed is False
    assert "verify_fixture-0.0.1-py3-none-any.whl" in result.detail


def test_check_built_artifacts_fails_on_a_value_matcher_hit_in_the_wheel(
    tmp_path: Path,
) -> None:
    """Distinct from the token-forbidden-string branch above: a value the
    fingerprint set recognises, with no forbidden string anywhere, must
    still fail this row through the `scan()` branch."""
    project = tmp_path / "value-project"
    _fixture_project(project, extra_line="noise 333 noise")
    output_dir = tmp_path / "value-dist"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    sdist, wheel = build_artifacts(project, output_dir)
    result = check_built_artifacts(
        subject=project,
        sdist=sdist,
        wheel=wheel,
        forbidden=forbidden,
        fingerprints=frozenset({digest(["333"], _SALT)}),
        window_lengths=frozenset({1}),
        salt=_SALT,
    )

    assert result.passed is False
    assert "(value)" in result.detail


def test_check_built_artifacts_fails_on_a_token_in_a_member_path(
    tmp_path: Path,
) -> None:
    """The token is in a MEMBER'S NAME, never in any content and never in
    the wheel at all (the planted file ships only in the sdist, at the
    project root -- see `_fixture_project`'s docstring for why that
    specifically avoids `dist-info/RECORD` incidentally carrying the same
    string as content). Only a check that inspects the path surface
    independently of content catches this; content-only scanning -- exactly
    what a naive `if matches(text, ...)` implementation, with no separate
    name check, would do -- reports this clean."""
    project = tmp_path / "path-token-project"
    _fixture_project(
        project, extra_line=None, root_extra_filename="secretlastname_extra.txt"
    )
    output_dir = tmp_path / "path-token-dist"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    sdist, wheel = build_artifacts(project, output_dir)
    result = check_built_artifacts(
        subject=project,
        sdist=sdist,
        wheel=wheel,
        forbidden=forbidden,
        fingerprints=frozenset({digest(["999"], _SALT)}),
        window_lengths=frozenset({1}),
        salt=_SALT,
    )

    assert result.passed is False
    assert "(token in path)" in result.detail
    assert "secretlastname_extra.txt" in result.detail
    assert "-py3-none-any.whl" not in result.detail


def test_check_built_artifacts_fails_when_a_token_ships_only_in_the_sdist(
    tmp_path: Path,
) -> None:
    """`README.md` ships in the SDIST (hatchling's default sdist include)
    but NOT the WHEEL (this fixture's wheel target declares only the
    `verify_fixture` package) -- a version of `check_built_artifacts` that
    only scanned the wheel, or that scanned `(sdist, wheel)` but broke out
    of the loop after the first archive, reports this clean."""
    project = tmp_path / "sdist-only-project"
    _fixture_project(project, extra_line=None, readme_line="written by secretlastname")
    output_dir = tmp_path / "sdist-only-dist"
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    sdist, wheel = build_artifacts(project, output_dir)
    result = check_built_artifacts(
        subject=project,
        sdist=sdist,
        wheel=wheel,
        forbidden=forbidden,
        fingerprints=frozenset({digest(["999"], _SALT)}),
        window_lengths=frozenset({1}),
        salt=_SALT,
    )

    assert result.passed is False
    assert "verify_fixture-0.0.1.tar.gz" in result.detail
    assert "-py3-none-any.whl" not in result.detail


def test_check_built_artifacts_does_not_crash_on_a_dangling_symlink_in_the_sdist(
    tmp_path: Path,
) -> None:
    """Reproduces the exact shape this project's OWN built sdist carries
    (`.kiro/queue/2026-07-31-agent-log-symlink-ships-in-sdist.md`): a
    dangling symlink inside the sdist. `uv build`/hatchling refuses outright
    to build a WHEEL containing a dangling symlink (confirmed directly --
    `FileNotFoundError` deep inside hatchling's own wheel builder), so this
    shape can only be reproduced through a real build for the archive that
    actually carries it in practice: the sdist. The sdist here is
    constructed by hand for that reason and paired with a real, clean,
    `uv`-built wheel.

    The dangling member's NAME itself carries the forbidden token -- not a
    clean name -- so this fixture pins the module docstring's own promise
    ("an unreadable member's PATH is still checked; only its content is
    skipped") rather than merely proving the function doesn't crash. A
    version that checks the path only AFTER the `raw is None: continue`
    guard reports this clean, since the guard fires first and the path
    check is never reached for this member."""
    project = tmp_path / "dangling-project"
    _fixture_project(project, extra_line=None)
    output_dir = tmp_path / "dangling-dist"
    _real_sdist, wheel = build_artifacts(project, output_dir)

    sdist = output_dir / "hand-built-with-dangling-symlink.tar.gz"
    payload = tmp_path / "sdist-payload"
    payload.mkdir()
    (payload / "real.txt").write_text("clean\n")
    (payload / "secretlastname-dangling-link.txt").symlink_to("nowhere.txt")
    with tarfile.open(sdist, "w:gz") as tf:
        tf.add(payload, arcname="verify_fixture-0.0.1")

    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    result = check_built_artifacts(
        subject=project,
        sdist=sdist,
        wheel=wheel,
        forbidden=forbidden,
        fingerprints=frozenset({digest(["999"], _SALT)}),
        window_lengths=frozenset({1}),
        salt=_SALT,
    )  # must not raise KeyError

    assert result.passed is False
    assert "(token in path)" in result.detail
    assert "secretlastname-dangling-link.txt" in result.detail
    assert "unreadable member" in result.detail


# ---------------------------------------------------------------------------
# require_forbidden_strings -- fails, never skips (opposite of the guard)
# ---------------------------------------------------------------------------


def test_require_forbidden_strings_raises_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    repo_root = tmp_path / "repo-root"
    repo_root.mkdir()

    with pytest.raises(ForbiddenStringsSourceError):
        require_forbidden_strings(repo_root)


def test_require_forbidden_strings_returns_the_loaded_source_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "outside"
    source_dir.mkdir()
    source_file = source_dir / "forbidden.tsv"
    source_file.write_text("secretlastname\n")
    monkeypatch.setenv(ENV_VAR, str(source_file))
    repo_root = tmp_path / "repo-root"
    repo_root.mkdir()

    result = require_forbidden_strings(repo_root)

    assert result.values == ("secretlastname",)


# ---------------------------------------------------------------------------
# The deliberately incomplete fixture -- proves the rows DISCRIMINATE
# ---------------------------------------------------------------------------


def test_deliberately_incomplete_fixture_repository_fails_the_rows_it_should(
    tmp_path: Path,
) -> None:
    """A single un-replaced fixture repository (multiple commits, an extra
    branch, nothing forged or swapped), run through every single-subject row
    this module implements. Because the repository was never actually put
    through `HistoryReplacement`, several rows MUST fail (they are checking
    for exactly the state a real replacement would have produced) while
    others legitimately pass. Asserting each row's verdict individually --
    and the row count -- is what proves the table discriminates rather than
    merely executes: a row that always passes regardless of fixture state
    would be invisible to this test, but a row that always FAILS regardless
    of state would also be invisible to a test that only checked "some rows
    failed" -- pinning each row by name closes both gaps.
    """
    repo = _repo(tmp_path, name="incomplete")
    forbidden = _forbidden("secretlastname", tmp_path=tmp_path)

    # FAIL row (exactly one commit reachable, reflogs/unreachables gone):
    # a second commit, still on `main`.
    (repo / "docs").mkdir()
    (repo / "docs" / "withdrawn-table.md").write_text("still present\n")
    _git(repo, "add", "docs/withdrawn-table.md")
    _git(repo, "commit", "-q", "-m", "add withdrawn table")

    # FAIL row (no token in any path or blob): a blob still carries the
    # forbidden token.
    (repo / "credits.txt").write_text("thanks to secretlastname\n")
    _git(repo, "add", "credits.txt")
    _git(repo, "commit", "-q", "-m", "credits")

    # FAIL row (refs clean): an extra branch still exists (no
    # HistoryReplacement ran).
    _git(repo, "branch", "feature/stray")

    # FAIL row (old identifiers refused): an old identifier still resolves
    # (nothing was replaced).
    old_head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    tree_id = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()

    results = {
        "exactly one commit reachable": check_exactly_one_commit_reachable(repo),
        "root tree identical to the certified tip tree": check_tree_identity(
            repo, tree_id
        ),
        "working tree coincides with the root": check_working_tree_coincides(repo),
        "no refs/original, no extra refs": check_refs_clean(repo),
        "metadata clean": check_metadata_clean(repo, frozenset({"t@t", "t"})),
        "no token in any commit message": check_no_token_in_any_commit_message(
            repo, forbidden
        ),
        "no token in any path or blob of the single commit": (
            check_no_token_in_path_or_blob(repo, forbidden)
        ),
        "old identifiers refused": check_old_identifiers_refused(repo, (old_head,)),
        "reflogs and unreachables gone": check_reflog_and_unreachable_gone(
            repo, old_head
        ),
    }

    # Independent count anchor -- a loop/dict-comprehension bug that dropped
    # a row would still leave every REMAINING assertion below green.
    assert len(results) == 9

    expected_pass = {
        "exactly one commit reachable": False,
        "root tree identical to the certified tip tree": True,
        "working tree coincides with the root": True,
        "no refs/original, no extra refs": False,
        "metadata clean": True,
        "no token in any commit message": True,
        "no token in any path or blob of the single commit": False,
        "old identifiers refused": False,
        "reflogs and unreachables gone": False,
    }
    actual_pass = {name: result.passed for name, result in results.items()}
    assert actual_pass == expected_pass

    # Every result names the ONE subject repository this test built.
    for result in results.values():
        assert result.subject == repo


# ===========================================================================
# RemoteReconciliation (task 5.7, design.md #### RemoteReconciliation,
# Req 8.1, 8.3, 8.5)
#
# No test in this section makes a real network request. `probe_identifier`/
# `probe_identifiers` are driven through an injected recording `WebTransport`
# callable; `parse_ls_remote_output` is fed a literal `git ls-remote`-shaped
# string rather than the output of a real `ls-remote` invocation.
# ===========================================================================


class _RecordingTransport:
    """Records every `(url, headers)` pair it is called with and returns a
    caller-supplied status code per URL. Never opens a socket."""

    def __init__(self, status_by_url: dict[str, int]) -> None:
        self.status_by_url = status_by_url
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> int:
        self.calls.append((url, dict(headers)))
        return self.status_by_url[url]


# ---------------------------------------------------------------------------
# build_commit_url / build_auth_headers
# ---------------------------------------------------------------------------


def test_build_commit_url_is_exactly_the_expected_web_path() -> None:
    """Whole-string equality, not membership -- a defeat for an argument
    swap (owner/repo transposed) or a wrong path segment (`commits` for
    `commit`, or a missing `/`)."""
    url = build_commit_url("acme-org", "acme-repo", "deadbeef" * 5)

    assert url == "https://github.com/acme-org/acme-repo/commit/" + "deadbeef" * 5


def test_build_auth_headers_returns_exactly_a_bearer_authorization_header() -> None:
    headers = build_auth_headers("secret-token-value")

    assert headers == {"Authorization": "Bearer secret-token-value"}


def test_build_auth_headers_raises_on_an_empty_token() -> None:
    """An empty token must not silently produce an unauthenticated-looking
    header; Req 8.1/8.3's probe is explicitly an *authenticated* request."""
    with pytest.raises(ValueError):
        build_auth_headers("")


# ---------------------------------------------------------------------------
# probe_identifier / probe_identifiers (Req 8.1, 8.3)
# ---------------------------------------------------------------------------


def test_probe_identifier_reports_served_on_a_200() -> None:
    old_sha = "1111111111111111111111111111111111111a"
    url = build_commit_url("acme-org", "acme-repo", old_sha)
    transport = _RecordingTransport({url: 200})

    result = probe_identifier(
        transport, owner="acme-org", repo="acme-repo", identifier=old_sha, token="tok"
    )

    assert result == ProbeResult(
        identifier=old_sha, url=url, status_code=200, served=True
    )


def test_probe_identifier_reports_gone_on_a_404() -> None:
    """Pairwise-distinct from the 200 fixture above: a different identifier,
    a different status, a different expected `served` value -- not merely
    the boolean flip of one shared fixture."""
    old_sha = "2222222222222222222222222222222222222b"
    url = build_commit_url("acme-org", "acme-repo", old_sha)
    transport = _RecordingTransport({url: 404})

    result = probe_identifier(
        transport, owner="acme-org", repo="acme-repo", identifier=old_sha, token="tok"
    )

    assert result == ProbeResult(
        identifier=old_sha, url=url, status_code=404, served=False
    )


def test_probe_identifier_raises_on_unrecognised_status_not_reporting_gone() -> None:
    """The core distinction this row exists to preserve: "gone" and "cannot
    tell" must never collapse into the same observable. A `500` is neither
    `200` nor `404` and must raise `RemoteProbeError`, not silently report
    `served=False` (which a naive `if status != 200: served = False` would
    do, indistinguishable from a genuine 404 in the caller's eyes)."""
    old_sha = "3333333333333333333333333333333333333c"
    url = build_commit_url("acme-org", "acme-repo", old_sha)
    transport = _RecordingTransport({url: 500})

    with pytest.raises(RemoteProbeError):
        probe_identifier(
            transport,
            owner="acme-org",
            repo="acme-repo",
            identifier=old_sha,
            token="tok",
        )


def test_probe_identifier_calls_the_transport_with_the_exact_url_and_headers() -> None:
    """Assert the whole recorded call, not a substring or membership check
    -- tasks.md `## Implementation Notes`, "Assert whole values, not
    membership." A truncated URL, a missing scheme, or a header dict
    carrying an extra or differently-named key would all still pass a
    membership check but fail this whole-tuple equality."""
    old_sha = "4444444444444444444444444444444444444d"
    url = build_commit_url("owner-x", "repo-y", old_sha)
    transport = _RecordingTransport({url: 200})

    probe_identifier(
        transport, owner="owner-x", repo="repo-y", identifier=old_sha, token="tok-z"
    )

    assert transport.calls == [
        (
            "https://github.com/owner-x/repo-y/commit/" + old_sha,
            {"Authorization": "Bearer tok-z"},
        )
    ]


def test_probe_identifiers_reports_one_result_per_identifier_in_order() -> None:
    """Two pairwise-distinct identifiers, one served and one gone -- proves
    per-identifier discrimination rather than a single shared verdict
    broadcast across the whole sample."""
    served_sha = "5555555555555555555555555555555555555e"
    gone_sha = "6666666666666666666666666666666666666f"
    served_url = build_commit_url("acme-org", "acme-repo", served_sha)
    gone_url = build_commit_url("acme-org", "acme-repo", gone_sha)
    transport = _RecordingTransport({served_url: 200, gone_url: 404})

    results = probe_identifiers(
        transport,
        owner="acme-org",
        repo="acme-repo",
        identifiers=(served_sha, gone_sha),
        token="tok",
    )

    assert results == (
        ProbeResult(
            identifier=served_sha, url=served_url, status_code=200, served=True
        ),
        ProbeResult(identifier=gone_sha, url=gone_url, status_code=404, served=False),
    )


def test_probe_identifiers_raises_on_an_empty_sample() -> None:
    """A probe over zero identifiers must not report a vacuous pass -- the
    same anti-pattern `check_old_identifiers_refused` above guards
    against."""
    transport = _RecordingTransport({})

    with pytest.raises(VerificationInputsError):
        probe_identifiers(
            transport, owner="acme-org", repo="acme-repo", identifiers=(), token="tok"
        )


# ---------------------------------------------------------------------------
# fetch_object_by_identifier / mirror_clone_and_read_object -- unavailable,
# not merely discouraged
# ---------------------------------------------------------------------------


def test_fetch_object_by_identifier_always_raises_with_no_arguments() -> None:
    with pytest.raises(DisqualifiedProbeError):
        fetch_object_by_identifier()


def test_fetch_object_by_identifier_always_raises_even_with_plausible_arguments() -> (
    None
):
    """Raises unconditionally regardless of what looks like a legitimate
    call -- proving the refusal is not gated on argument validation (which
    would leave open the possibility of some "correct" call succeeding)."""
    with pytest.raises(DisqualifiedProbeError):
        fetch_object_by_identifier(
            "acme-org", "acme-repo", "1111111111111111111111111111111111111a"
        )


def test_mirror_clone_and_read_object_always_raises_with_no_arguments() -> None:
    with pytest.raises(DisqualifiedProbeError):
        mirror_clone_and_read_object()


def test_mirror_clone_and_read_object_always_raises_even_with_plausible_arguments() -> (
    None
):
    with pytest.raises(DisqualifiedProbeError):
        mirror_clone_and_read_object(
            "git@github.com:acme-org/acme-repo.git",
            "1111111111111111111111111111111111111a",
        )


# ---------------------------------------------------------------------------
# parse_ls_remote_output
# ---------------------------------------------------------------------------


def test_parse_ls_remote_output_drops_head_symref_and_peeled_duplicates() -> None:
    """The `HEAD` symref line and a `^{}`-peeled duplicate must both be
    dropped -- but everything else is KEPT, including a plain tag and a
    `refs/original/*` leftover: design.md's remote operand is unfiltered
    `git ls-remote origin`, so `remote_only` must be able to see any ref
    class, not only `refs/heads/*`. Whole-dict equality closes
    the keep-rule, the drop-rule and the sha-per-name mapping in one
    assertion."""
    text = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\tHEAD\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/heads/main\n"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/v0.1.0\n"
        "cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v0.1.0^{}\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/original/refs/heads/main\n"
    )

    parsed = parse_ls_remote_output(text)

    assert parsed == {
        "refs/heads/main": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "refs/tags/v0.1.0": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "refs/original/refs/heads/main": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }


def test_parse_ls_remote_output_normalizes_crlf_and_skips_blank_lines() -> None:
    """Whitespace normalization is deliberately UNPINNED as a general claim
    (no docstring here asserts full normalization), but this one case is
    pinned so a `\\r`-suffixed name (a `\\r\\n`-terminated transcript line)
    and a blank line between entries do not corrupt the result.

    The two halves are pinned differently, and the asymmetry is measured
    rather than assumed. `splitlines()` and `line.strip()` are mutually
    REDUNDANT against a trailing `\\r` -- either one alone removes it, so
    substituting `split("\\n")` while keeping the strip leaves this test
    green, and dropping the strip while keeping `splitlines()` does too.
    What this fixture pins is their CONJUNCTION: replacing both at once
    reds it. The `not name` guard is pinned individually -- dropping it
    alone reds this test, because a blank line's empty name would
    otherwise reach the dict."""
    text = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/heads/main\r\n"
        "\n"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/heads/dev\n"
    )

    parsed = parse_ls_remote_output(text)

    assert parsed == {
        "refs/heads/main": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "refs/heads/dev": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }


def test_parse_ls_remote_output_on_empty_text_returns_an_empty_dict() -> None:
    assert parse_ls_remote_output("") == {}


# ---------------------------------------------------------------------------
# local_heads
# ---------------------------------------------------------------------------


def test_local_heads_reports_every_branch_and_its_sha(tmp_path: Path) -> None:
    """Whole-dict equality against a fixture that ALSO carries a ref outside
    `refs/heads` (`refs/original/refs/heads/main`, planted directly with
    `update-ref`, mirroring the leftover `HistoryRewrite` can carry
    forward). Dropping the `"refs/heads"` pattern argument from the
    underlying `for-each-ref` call would add that ref to this dict -- on a
    real working tree it would add `refs/remotes/*` too -- which this
    equality assertion must catch."""
    repo = _repo(tmp_path)
    _git(repo, "branch", "feature/second")
    main_sha = _git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    second_sha = _git(repo, "rev-parse", "refs/heads/feature/second").stdout.strip()
    _git(repo, "update-ref", "refs/original/refs/heads/main", main_sha)

    heads = local_heads(repo)

    assert heads == {
        "refs/heads/main": main_sha,
        "refs/heads/feature/second": second_sha,
    }


# ---------------------------------------------------------------------------
# compare_refs (Req 8.5) -- both directions, pinned independently
# ---------------------------------------------------------------------------


def test_compare_refs_passes_when_local_and_remote_match_exactly() -> None:
    local = {"refs/heads/main": "aaa", "refs/heads/dev": "bbb"}
    remote = {"refs/heads/main": "aaa", "refs/heads/dev": "bbb"}

    result = compare_refs(local, remote)

    assert result == RefComparisonResult(
        passed=True, missing_from_remote=(), remote_only=()
    )


def test_compare_refs_fails_when_a_local_head_is_absent_from_the_remote() -> None:
    """Direction one only: `dev` exists locally but not on the remote at
    all. `remote_only` must stay empty -- proving this branch of the check
    is independent of the other."""
    local = {"refs/heads/main": "aaa", "refs/heads/dev": "bbb"}
    remote = {"refs/heads/main": "aaa"}

    result = compare_refs(local, remote)

    assert result == RefComparisonResult(
        passed=False, missing_from_remote=("refs/heads/dev",), remote_only=()
    )


def test_compare_refs_fails_when_a_local_head_is_at_a_different_identifier() -> None:
    """`main` exists on both sides but at different shas -- present-but-
    wrong, distinct from absent-entirely above."""
    local = {"refs/heads/main": "aaa"}
    remote = {"refs/heads/main": "zzz"}

    result = compare_refs(local, remote)

    assert result == RefComparisonResult(
        passed=False, missing_from_remote=("refs/heads/main",), remote_only=()
    )


def test_compare_refs_fails_when_the_remote_carries_a_ref_not_local() -> None:
    """Direction two only, and the one design.md calls out by name: a
    pre-rewrite ref left behind on the remote. `missing_from_remote` must
    stay empty -- proving this branch is independent of the first."""
    local = {"refs/heads/main": "aaa"}
    remote = {"refs/heads/main": "aaa", "refs/heads/pre-rewrite-leftover": "ccc"}

    result = compare_refs(local, remote)

    assert result == RefComparisonResult(
        passed=False,
        missing_from_remote=(),
        remote_only=("refs/heads/pre-rewrite-leftover",),
    )


def test_compare_refs_fails_on_both_directions_simultaneously_with_distinct_names() -> (
    None
):
    """Both violations present at once, with pairwise-distinct ref names on
    each side -- a version that only checked one direction, or that
    conflated the two result tuples, cannot pass this."""
    local = {"refs/heads/main": "aaa", "refs/heads/only-local": "bbb"}
    remote = {"refs/heads/main": "aaa", "refs/heads/only-remote": "ccc"}

    result = compare_refs(local, remote)

    assert result == RefComparisonResult(
        passed=False,
        missing_from_remote=("refs/heads/only-local",),
        remote_only=("refs/heads/only-remote",),
    )


def test_compare_refs_sorts_both_missing_from_remote_and_remote_only() -> None:
    """Two entries in EACH tuple, inserted in non-alphabetical order on
    BOTH sides -- every fixture above carries at most one entry per
    direction, so neither `sorted()` call is pinned by any of them.
    Removing either `sorted()` independently leaves that half
    in dict-iteration (insertion) order, which this whole-dataclass
    equality catches without touching the other half."""
    local = {
        "refs/heads/zzz-local": "aaa",
        "refs/heads/aaa-local": "bbb",
        "refs/heads/main": "ccc",
    }
    remote = {
        "refs/heads/main": "ccc",
        "refs/heads/zzz-remote": "ddd",
        "refs/heads/aaa-remote": "eee",
    }

    result = compare_refs(local, remote)

    assert result == RefComparisonResult(
        passed=False,
        missing_from_remote=("refs/heads/aaa-local", "refs/heads/zzz-local"),
        remote_only=("refs/heads/aaa-remote", "refs/heads/zzz-remote"),
    )


def test_check_remote_refs_match_fails_when_a_remote_only_ref_is_present_in_a_fixture(
    tmp_path: Path,
) -> None:
    """The task's own named observable: "the ref comparison fails when a
    remote-only ref is present in a fixture." A real local repo (`main`
    only) composed with a literal `git ls-remote`-shaped transcript naming
    an extra `pre-rewrite-leftover` branch -- no network anywhere in this
    test."""
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    remote_ls_output = (
        f"{main_sha}\trefs/heads/main\n"
        "cccccccccccccccccccccccccccccccccccccccc\trefs/heads/pre-rewrite-leftover\n"
    )

    result = check_remote_refs_match(repo, remote_ls_output)

    assert result.passed is False
    assert result.remote_only == ("refs/heads/pre-rewrite-leftover",)
    assert result.missing_from_remote == ()


def test_check_remote_refs_match_passes_when_remote_mirrors_local_exactly(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    remote_ls_output = f"{main_sha}\trefs/heads/main\n"

    result = check_remote_refs_match(repo, remote_ls_output)

    assert result == RefComparisonResult(
        passed=True, missing_from_remote=(), remote_only=()
    )


def test_check_remote_refs_match_fails_when_refs_original_survives_on_the_remote(
    tmp_path: Path,
) -> None:
    """`refs/original/*` is the named pre-rewrite ref class
    (design.md `#### HistoryRewrite`: filter-repo "does not drop
    `refs/original/*`; it rewrites them forward, carrying the encumbered
    files and the personal address into the rewritten repository under new
    SHAs"). A parser that kept only `refs/heads/*` would discard this
    line before `compare_refs` ever saw it, so this exact leftover shape
    would pass silently -- which is what this fixture exists to prevent."""
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    remote_ls_output = (
        f"{main_sha}\trefs/heads/main\n{main_sha}\trefs/original/refs/heads/main\n"
    )

    result = check_remote_refs_match(repo, remote_ls_output)

    assert result.passed is False
    assert result.remote_only == ("refs/original/refs/heads/main",)
    assert result.missing_from_remote == ()


def test_check_remote_refs_match_fails_when_a_pre_rewrite_tag_survives_on_the_remote(
    tmp_path: Path,
) -> None:
    """A `refs/tags/*` line the local repository does not have. design.md
    `#### RemoteReconciliation`'s remote operand is unfiltered `git
    ls-remote origin` -- nothing there restricts it to branch heads -- so a
    pre-rewrite tag left on the remote must surface in `remote_only`, not
    be discarded before `compare_refs` runs."""
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    remote_ls_output = (
        f"{main_sha}\trefs/heads/main\n"
        "cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v0.1.0\n"
    )

    result = check_remote_refs_match(repo, remote_ls_output)

    assert result.passed is False
    assert result.remote_only == ("refs/tags/v0.1.0",)
    assert result.missing_from_remote == ()
