"""`scripts/purge/rewrite_map.py`: extraction of the prior rewrite map's data
rows before task 3.1 deletes the file (Req 9.7).

Every fixture here is synthetic -- invented shas and subjects -- because the
extraction *mechanism* (separating data rows from the `#`-prefixed prose
header and blank lines, then round-tripping through disk) is what this file
pins. The real file's row count is independently re-derived (not compared
against this module's own output) in
``test_extraction_matches_the_real_prior_map_row_count_measured_independently``
below, using a plain ``awk``-equivalent count over the pre-deletion content --
the same recount idiom the forbidden-string match-data artifact records in
its own ``.meta.json`` (``recount_command``) -- so the pin is never a
self-referential compare of the production code against itself.

That check resolves the pre-deletion content through history rather than a
fixed ref (``HEAD:<path>``), because a fixed ref cannot survive this task's
own commit: once task 3.1 lands, ``HEAD`` no longer carries the deleted path
at all, and a bare ``git show HEAD:<path>`` would raise instead of skip. See
``_resolve_prior_map_pre_deletion_text`` below.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.purge.rewrite_map import (
    parse_data_rows,
    read_extracted_rows,
    write_extracted_rows,
)

from tests._forbidden_strings import ForbiddenStringsSourceError, require

_REPO_ROOT = Path(__file__).resolve().parents[2]

_KNOWN_PRIOR_MAP_DATA_ROW_COUNT = 174
"""The prior rewrite map's data-row count (187 lines total = 13 header/prose
+ blank lines, 174 data rows), recorded independently of this test: the
queue item `.kiro/queue/2026-07-26-rewrite-map-not-durable.md` states "it
changed all 174 SHAs" and the map's own header records the same figure.
This number carries no forbidden value (it is a row count, not a path or a
token), so pinning against it here does not reintroduce one. Used below to
pin WHICH file `_real_prior_map_path` resolved: 174 is real data, not
derived from any file's own text the way `independent_count` (computed
per-run from whatever `text` was resolved) is -- so it is a check the
withdrawn writeup's `.md` path (a different `path`-category entry) cannot
also satisfy."""

_SYNTHETIC_PRIOR_MAP_PATH = "docs/reference/synthetic-prior-map-for-this-test.tsv"
"""A made-up path, unrelated to the real prior rewrite map, used only to pin
`_resolve_prior_map_pre_deletion_text`'s and `_prior_map_is_reachable_from_
head`'s git-argument-vector mechanism against a MOCKED `subprocess.run`.
Every test that uses it fakes the git calls (never touches real git), so it
needs no relation to the actual prior map's path and this file holds no copy
of that path. The end-to-end test against the real repository resolves the
real path separately, via `_real_prior_map_path` below, from the file
`FITDOCS_FORBIDDEN_STRINGS` names."""


def _real_prior_map_path(repo_root: Path) -> str:
    """The real prior rewrite map's tracked path (before task 3.1 deleted
    it), resolved from `FITDOCS_FORBIDDEN_STRINGS`'s ``path``-category
    entries rather than hard-coded here -- this test file holds no copy of
    the removed path itself (task 6.3).

    The map is the only removed ``path``-category entry ending `.tsv`.
    Measured directly (`tests/purge/test_tree_removal.py::_removed_file_paths`
    states the same fact): the other four `path`-category entries have
    suffixes `.md` (one), `.csv` (two), and one entry with no suffix at all --
    the extension-less containing-directory entry `_removed_file_paths`
    filters out because it names no removed FILE (`scripts/purge/
    fingerprints.py::_default_sources` is correct to filter on
    `endswith((".md", ".csv"))` only because that directory entry carries
    neither suffix). So the `.tsv` suffix is what picks the map out of the
    flat, uncategorised value set `require()` returns without needing a
    second, category-preserving parse.

    Skips via `require()` when `FITDOCS_FORBIDDEN_STRINGS` is unset (Req
    11.8's one legitimate silent outcome). Raises `ForbiddenStringsSourceError`
    when it is set but names a source with no `.tsv` entry -- the same
    "set but absent" failure `require`/`load` raise for a broken source,
    never collapsed into the skip a genuinely unset variable takes.
    """
    forbidden_strings = require(repo_root)
    for value in forbidden_strings.values:
        if value.endswith(".tsv"):
            return value
    raise ForbiddenStringsSourceError(
        "FITDOCS_FORBIDDEN_STRINGS is set but names no .tsv path-category "
        "entry -- the prior rewrite map's path cannot be resolved from it"
    )


# --- parse_data_rows() -------------------------------------------------------


def test_parse_data_rows_skips_the_prose_header() -> None:
    text = (
        "# fitdocs_oss commit SHA map: pre- vs post- author/committer email "
        "rewrite\n"
        "# Rewritten 2026-07-26, some.address@example.com -> other@example.com\n"
        "#\n"
        "aaa111\tbbb222\tfeat: first commit\n"
    )

    rows = parse_data_rows(text)

    assert rows == ("aaa111\tbbb222\tfeat: first commit",)
    for row in rows:
        assert "example.com" not in row, (
            "a data row must never carry header prose -- the header is where "
            "the personal address lives and must not leak into the "
            "extraction"
        )


def test_parse_data_rows_skips_blank_lines() -> None:
    text = "aaa\tbbb\tone\n\naaa2\tbbb2\ttwo\n"

    rows = parse_data_rows(text)

    assert rows == ("aaa\tbbb\tone", "aaa2\tbbb2\ttwo")


def test_parse_data_rows_preserves_file_order() -> None:
    # Distinct, non-alphabetically-sortable subjects so a mutant that sorts
    # the rows (rather than preserving file order) is caught.
    text = "z\tz2\tzeta commit\na\ta2\talpha commit\nm\tm2\tmid commit\n"

    rows = parse_data_rows(text)

    assert rows == (
        "z\tz2\tzeta commit",
        "a\ta2\talpha commit",
        "m\tm2\tmid commit",
    )


def test_parse_data_rows_over_a_header_only_file_is_empty() -> None:
    # Positive control for the header/blank-line filter: a file with only
    # comments and blank lines must yield zero rows, not silently keep
    # something.
    text = "# header line one\n# header line two\n\n"

    rows = parse_data_rows(text)

    assert rows == ()


# --- write_extracted_rows() / read_extracted_rows() round trip --------------


def test_write_then_read_back_round_trips_field_by_field_and_in_order(
    tmp_path: Path,
) -> None:
    # An artifact-producing function must read back what it wrote (this cost
    # three review rounds on task 2.4 in three different places) -- so this
    # compares the read-back rows against the rows that produced them,
    # field-by-field and in order, rather than merely asserting the artifact
    # exists.
    #
    # Deliberately NOT already sorted (mirrors the zeta/alpha/mid shape
    # `test_parse_data_rows_preserves_file_order` uses above): a fixture
    # already in sorted order cannot distinguish "preserves the given order"
    # from "silently sorts", so both `write_extracted_rows` and
    # `read_extracted_rows` could each independently sort their rows and this
    # assertion would still pass. Sorted, these three subjects would read
    # alpha/beta/gamma; the fixture order below is deliberately not that.
    rows = (
        "sha3a\tsha3b\tfeat: gamma",
        "sha1a\tsha1b\tfeat: alpha",
        "sha2a\tsha2b\tfeat: beta",
    )
    out_path = tmp_path / "scratch" / "rewrite-map-rows.tsv"

    write_extracted_rows(rows, out_path)
    read_back = read_extracted_rows(out_path)

    assert read_back == rows


def test_write_extracted_rows_creates_missing_parent_directories(
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "does" / "not" / "exist" / "rows.tsv"

    write_extracted_rows(("a\tb\tc",), out_path)

    assert out_path.exists()
    assert read_extracted_rows(out_path) == ("a\tb\tc",)


def test_write_extracted_rows_of_empty_sequence_writes_an_empty_file(
    tmp_path: Path,
) -> None:
    # Positive control for the round trip above: an empty input must produce
    # a genuinely empty read-back, not a stray blank line masquerading as a
    # row.
    out_path = tmp_path / "rows.tsv"

    write_extracted_rows((), out_path)

    assert out_path.read_text(encoding="utf-8") == ""
    assert read_extracted_rows(out_path) == ()


def test_read_extracted_rows_skips_a_trailing_blank_line(tmp_path: Path) -> None:
    out_path = tmp_path / "rows.tsv"
    # Deliberately not alphabetically sorted ("d" before "a"), for the same
    # reason as the round-trip fixture above: a sorted fixture cannot
    # distinguish order-preservation from silent sorting.
    out_path.write_text("d\te\tf\na\tb\tc\n\n", encoding="utf-8")

    assert read_extracted_rows(out_path) == ("d\te\tf", "a\tb\tc")


# --- end-to-end pin against the real, still-present prior map ---------------


def _resolve_prior_map_pre_deletion_text(path: str) -> str | None:
    """The prior map's content exactly as it stood immediately before task
    3.1 deleted it, resolved through history rather than a fixed ref.
    `path` is a parameter -- never a module constant -- so a mocked test can
    pin the mechanism with a synthetic path while the real end-to-end test
    supplies the real one, resolved separately.

    A bare ``git show HEAD:<path>`` only works while the deletion is
    uncommitted -- once task 3.1's commit lands, ``HEAD`` no longer carries
    the path at all, and that call would raise `CalledProcessError` rather
    than degrade legibly (a hard error task 3.2 onward, and 6.2's landing
    gate, would inherit). This resolves the two cases explicitly, `check=False`
    throughout, and returns ``None`` -- never raises -- when neither
    resolves, which is expected after Major 7's history rewrite redacts the
    blob and no commit-ish can reach it any longer.

    1. The direct case: the deletion is still only staged (or has not been
       made at all), so `HEAD` itself still carries the file. Read it
       directly.
    2. The committed case: `git rev-list -1 HEAD -- <path>` finds the most
       recent commit reachable from `HEAD` that touched the path -- with the
       deletion committed, that is the deleting commit itself -- and the
       content immediately before deletion is that commit's *parent* version
       of the path (`<commit>~1:<path>`).
    """
    exists_at_head = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if exists_at_head.returncode == 0:
        show = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return show.stdout if show.returncode == 0 else None

    rev_list = subprocess.run(
        ["git", "rev-list", "-1", "HEAD", "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    touching_commit = rev_list.stdout.strip()
    if rev_list.returncode != 0 or not touching_commit:
        return None

    show = subprocess.run(
        ["git", "show", f"{touching_commit}~1:{path}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return show.stdout if show.returncode == 0 else None


def _prior_map_is_reachable_from_head(path: str) -> bool:
    """Whether the prior map's pre-deletion content is, in principle,
    resolvable from `HEAD` right now: `True` if `HEAD:<path>` itself
    resolves, or if `git rev-list -1 HEAD -- <path>` names a commit at all.
    `path` is a parameter for the same reason it is on
    `_resolve_prior_map_pre_deletion_text`.

    Deliberately independent of `_resolve_prior_map_pre_deletion_text`
    rather than reusing its return value or its intermediate results --
    reusing them would make this a restatement of "the resolver concluded
    something is reachable," which cannot catch the resolver itself being
    broken (Req 11.8's distinguishable-absence contract is a PAIR:
    unresolvable-input skips, reachable-input never silently skips too --
    `tests/test_forbidden_strings_source.py` pins both halves; this pairs
    with `test_extraction_matches_the_real_prior_map_row_count_measured_
    independently`'s skip to cover the second half here). This performs the
    same two real git probes the resolver does, but only to answer "does
    anything exist to resolve" -- it does not attempt the resolution itself.
    """
    exists_at_head = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if exists_at_head.returncode == 0:
        return True

    rev_list = subprocess.run(
        ["git", "rev-list", "-1", "HEAD", "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return rev_list.returncode == 0 and bool(rev_list.stdout.strip())


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


# The exact argument vectors `_resolve_prior_map_pre_deletion_text` must
# issue. Defined once here and compared with `==` (full-vector equality, not
# `args[:N]` prefix matching) in every fake below: a prefix match cannot
# distinguish a correct invocation from a malformed one that happens to share
# a prefix -- e.g. `git rev-list -1 HEAD <path>` (missing the `--` path
# separator) shares `args[:3] == ["git", "rev-list", "-1"]` with the correct
# form, but real git *fatally rejects* the former
# ("ambiguous argument ... Use '--' to separate paths from revisions"). A
# prefix-matching fake cannot red that mutation; a full-vector fake must.
_CAT_FILE_ARGS = ["git", "cat-file", "-e", f"HEAD:{_SYNTHETIC_PRIOR_MAP_PATH}"]
_REV_LIST_ARGS = ["git", "rev-list", "-1", "HEAD", "--", _SYNTHETIC_PRIOR_MAP_PATH]
_SHOW_HEAD_ARGS = ["git", "show", f"HEAD:{_SYNTHETIC_PRIOR_MAP_PATH}"]


def test_resolve_prior_map_text_reads_directly_when_head_still_has_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The uncommitted-deletion case: `git cat-file -e HEAD:<path>` succeeds,
    # so the direct `git show HEAD:<path>` branch is taken and the
    # history-fallback branch (`rev-list`) is never invoked.
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(args)
        if args == _CAT_FILE_ARGS:
            return _FakeCompletedProcess(returncode=0)
        if args == _SHOW_HEAD_ARGS:
            return _FakeCompletedProcess(returncode=0, stdout="direct-head-content\n")
        raise AssertionError(
            f"unexpected git invocation in the direct-HEAD case: {args}"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    text = _resolve_prior_map_pre_deletion_text(_SYNTHETIC_PRIOR_MAP_PATH)

    assert text == "direct-head-content\n"
    assert not any(args[:2] == ["git", "rev-list"] for args in calls), (
        "the history-fallback path ran even though HEAD still had the file"
    )


def test_resolve_prior_map_text_falls_back_to_the_deleting_commits_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The committed-deletion case: `git cat-file -e HEAD:<path>` fails (HEAD
    # no longer carries the path), so the fallback resolves the deleting
    # commit via `rev-list` and reads the path at that commit's PARENT
    # (`<commit>~1:<path>`) -- not at the deleting commit itself, which would
    # raise (the path does not exist there).
    fake_deleting_commit = "deadbeef" * 5

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        if args == _CAT_FILE_ARGS:
            return _FakeCompletedProcess(returncode=1)
        if args == _REV_LIST_ARGS:
            return _FakeCompletedProcess(
                returncode=0, stdout=f"{fake_deleting_commit}\n"
            )
        expected_show_args = [
            "git",
            "show",
            f"{fake_deleting_commit}~1:{_SYNTHETIC_PRIOR_MAP_PATH}",
        ]
        if args == expected_show_args:
            return _FakeCompletedProcess(returncode=0, stdout="parent-content\n")
        raise AssertionError(f"unexpected git invocation in the fallback case: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    text = _resolve_prior_map_pre_deletion_text(_SYNTHETIC_PRIOR_MAP_PATH)

    assert text == "parent-content\n"


def test_resolve_prior_map_text_returns_none_rather_than_raise_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Expected after Major 7's history rewrite: neither HEAD nor rev-list can
    # resolve the path any longer. Must return None -- never raise -- so the
    # caller can skip rather than error.
    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        if args == _CAT_FILE_ARGS:
            return _FakeCompletedProcess(returncode=1)
        if args == _REV_LIST_ARGS:
            return _FakeCompletedProcess(returncode=128, stdout="")
        raise AssertionError(
            f"unexpected git invocation in the unresolvable case: {args}"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _resolve_prior_map_pre_deletion_text(_SYNTHETIC_PRIOR_MAP_PATH) is None


def test_resolve_prior_map_text_returns_none_when_rev_list_succeeds_with_no_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The REAL git behaviour for a path that was never in history at all
    # (verified directly against this repository:
    # `git rev-list -1 HEAD -- docs/reference/never-existed.md` exits 0 with
    # EMPTY stdout, not a nonzero returncode). The sibling test above only
    # covers the `returncode != 0` half of the resolver's
    # `if rev_list.returncode != 0 or not touching_commit:` guard -- with a
    # nonzero returncode, that guard would still return None even if the
    # `or not touching_commit` half were deleted, so that mutation would
    # survive the sibling test. This covers the OTHER half directly: success
    # with nothing found.
    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        if args == _CAT_FILE_ARGS:
            return _FakeCompletedProcess(returncode=1)
        if args == _REV_LIST_ARGS:
            return _FakeCompletedProcess(returncode=0, stdout="\n")
        raise AssertionError(
            f"unexpected git invocation in the empty-rev-list case: {args}"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _resolve_prior_map_pre_deletion_text(_SYNTHETIC_PRIOR_MAP_PATH) is None


def test_extraction_matches_the_real_prior_map_row_count_measured_independently() -> (
    None
):
    """The real prior map's pre-deletion content has its data-row count
    independently re-derived here -- a plain line count over non-blank,
    non-`#`-prefixed lines, deliberately not calling `parse_data_rows` -- and
    that independent count must equal what `parse_data_rows` itself reports.
    A self-referential compare (asserting `parse_data_rows`'s own output
    against itself) would prove nothing; this computes the expected count a
    second, independent way.

    Skips, rather than erroring, when the content cannot be resolved through
    history at all (expected once Major 7's history rewrite redacts the
    blob) -- the same distinguishable-absence posture Req 11.8 requires of
    the forbidden-string source: an unresolvable input degrades to a visible
    skip, never a silent pass and never a hard `CalledProcessError`.

    That posture is a PAIR, not just a skip -- Req 11.8's contract, and
    `tests/test_forbidden_strings_source.py`'s own two complementary tests,
    require BOTH halves: an unresolvable input skips, AND a resolvable input
    never silently skips too. This asserts the second half directly, gated
    on `_prior_map_is_reachable_from_head`'s independent probe: if the prior
    map IS reachable from HEAD right now, `_resolve_prior_map_pre_deletion_
    text` returning `None` anyway is a broken resolver (e.g. a malformed git
    argument vector that real git rejects), not a legitimate unresolvable
    input -- and that must fail loudly here, never disappear into the same
    skip a genuinely unresolvable input takes.

    Also skips (via `_real_prior_map_path`) when `FITDOCS_FORBIDDEN_STRINGS`
    itself is unset -- the real path is resolved from that source (task
    6.3), never hard-coded in this file, so this end-to-end check is
    unverifiable without it, the same as every other check this source
    feeds.
    """
    path = _real_prior_map_path(_REPO_ROOT)
    reachable = _prior_map_is_reachable_from_head(path)
    text = _resolve_prior_map_pre_deletion_text(path)

    if text is None:
        assert not reachable, (
            "the prior map IS reachable from HEAD right now, but "
            "_resolve_prior_map_pre_deletion_text returned None anyway -- "
            "this is a broken resolver (e.g. a malformed git argument "
            "vector), not a legitimate unresolvable input, and must not "
            "disappear into a skip"
        )
        pytest.skip(
            "the prior map's pre-deletion content is not resolvable through "
            "history from HEAD (expected after Major 7's history rewrite "
            "redacts the blob) -- this pin is unverifiable rather than "
            "falsely red or falsely green"
        )

    assert text, (
        "the resolved prior-map content is empty -- this check is reading "
        "the wrong content, not proving the real map is empty"
    )

    independent_count = sum(
        1 for line in text.splitlines() if line.strip() and not line.startswith("#")
    )
    assert independent_count > 0, (
        "the independent line count found zero data rows -- this check is "
        "reading the wrong content, not proving the real map is empty"
    )
    assert independent_count == _KNOWN_PRIOR_MAP_DATA_ROW_COUNT, (
        f"resolved {independent_count} data rows, expected "
        f"{_KNOWN_PRIOR_MAP_DATA_ROW_COUNT} -- `_real_prior_map_path` "
        "resolved the wrong file. `independent_count` alone is "
        "self-consistent for ANY resolved file (it is derived from that "
        "file's own text), so it cannot by itself catch "
        "`_real_prior_map_path` picking up a different `path`-category "
        "entry -- e.g. the withdrawn writeup's `.md` path instead of the "
        f"map's `.tsv` path; this pin against the row count recorded "
        "independently (the queue item and the map's own header both "
        f"record {_KNOWN_PRIOR_MAP_DATA_ROW_COUNT}, not derived from this "
        "test or from parse_data_rows) is what catches that."
    )

    rows = parse_data_rows(text)
    assert len(rows) == independent_count


# --- _real_prior_map_path(): both directions of Req 11.8's contract --------


def test_real_prior_map_path_skips_when_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests._forbidden_strings import ENV_VAR

    monkeypatch.delenv(ENV_VAR, raising=False)

    with pytest.raises(pytest.skip.Exception):
        _real_prior_map_path(_REPO_ROOT)


def test_real_prior_map_path_raises_when_set_but_no_tsv_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests._forbidden_strings import ENV_VAR

    # A genuinely valid, outside-repo source -- so `require()` loads it
    # successfully -- that happens to carry no `.tsv` path-category entry.
    # Collapsing this into the unset case's skip is exactly the defect Req
    # 11.8 exists to make visible: a set-but-unresolvable source must raise,
    # never silently skip alongside a genuinely unset variable.
    source = tmp_path / "no-tsv-entries.tsv"
    source.write_text("path\tsome/removed/document.md\ntoken\tsome-token\n")
    monkeypatch.setenv(ENV_VAR, str(source))

    with pytest.raises(ForbiddenStringsSourceError, match=r"\.tsv"):
        _real_prior_map_path(_REPO_ROOT)
