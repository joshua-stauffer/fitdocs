"""Unit tests for `tests/_forbidden_strings.py` (`ForbiddenStrings`,
design.md `#### ForbiddenStrings`, Req 3.3, 3.4, 3.7, 11.8, 11.10).

These pin the loader itself: the skip-or-load helper, the case-insensitive
"every match" matcher, and the content-and-path-name tree scanner. The
standing guard that consumes this module against the real repository (Req
11.2, 11.7) is task 4.3's `tests/test_forbidden_strings.py` addition -- this
file is the meta-test the design's Implementation Notes describe for
`ForbiddenStrings` itself:

- Req 11.8's sharpest failure mode is collapsing a *broken* source (missing,
  unreadable, empty, or resolving inside the repository) into the *unset*
  outcome. `load` must raise for all four broken cases and return `None`
  only when the variable is genuinely unset -- never the reverse.
- `require` turns `None` into a `pytest.skip`, asserted as the skip
  *exception* here, never as a bare pass: a skip that a caller only checks
  "did not raise" on is indistinguishable from a real pass, which is exactly
  the failure Req 11.8 exists to make visible.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tarfile
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests._forbidden_strings import (
    _NOTICE_PHRASE_WORDS,
    ENV_VAR,
    ForbiddenStrings,
    ForbiddenStringsSourceError,
    Hit,
    _count_notice_phrase,
    load,
    matches,
    require,
    scan_tree,
)
from tests._forbidden_strings import _TRADEMARK_MARK as _NOTICE_TRADEMARK_MARK

_BUILD_TIMEOUT_S = 120

# --- load(): the only silent outcome is unset ------------------------------


def test_load_returns_none_when_variable_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert load(tmp_path) is None


def test_load_succeeds_for_a_genuinely_valid_outside_repo_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The necessary contrast for the four raising tests below: a valid
    # source does NOT raise, so those tests are pinning something real
    # rather than "load always raises".
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "outside" / "forbidden.txt"
    source.parent.mkdir()
    source.write_text("PlantedForbiddenValue\n")
    monkeypatch.setenv(ENV_VAR, str(source))

    fs = load(repo_root)

    assert fs is not None
    assert fs.values == ("PlantedForbiddenValue",)
    assert fs.source == source.resolve()


def test_load_raises_for_a_missing_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    missing = tmp_path / "outside" / "does-not-exist.txt"
    monkeypatch.setenv(ENV_VAR, str(missing))

    with pytest.raises(ForbiddenStringsSourceError):
        load(repo_root)


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="chmod(0o000) does not deny read access to uid 0",
)
def test_load_raises_for_an_unreadable_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "outside" / "forbidden.txt"
    source.parent.mkdir()
    source.write_text("SomeValue\n")
    source.chmod(0o000)
    monkeypatch.setenv(ENV_VAR, str(source))

    try:
        with pytest.raises(ForbiddenStringsSourceError):
            load(repo_root)
    finally:
        # Restore permissions so pytest's tmp_path cleanup can remove it.
        source.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_load_raises_for_an_empty_source_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "outside" / "forbidden.txt"
    source.parent.mkdir()
    source.write_text("")
    monkeypatch.setenv(ENV_VAR, str(source))

    with pytest.raises(ForbiddenStringsSourceError):
        load(repo_root)


def test_load_raises_for_a_source_file_of_only_comments_and_blank_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A file with bytes but no entries is the same "empty" outcome as a
    # zero-byte file -- it must not slip through as a non-empty source.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "outside" / "forbidden.txt"
    source.parent.mkdir()
    source.write_text("# just a comment\n\n   \n")
    monkeypatch.setenv(ENV_VAR, str(source))

    with pytest.raises(ForbiddenStringsSourceError):
        load(repo_root)


def test_load_raises_for_a_source_path_directly_inside_the_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "sub").mkdir(parents=True)
    source = repo_root / "sub" / "forbidden.txt"
    source.write_text("SomeValue\n")
    monkeypatch.setenv(ENV_VAR, str(source))

    with pytest.raises(ForbiddenStringsSourceError):
        load(repo_root)


def test_load_raises_for_a_source_path_resolving_inside_the_repo_via_dotdot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spelled so the unresolved string does NOT start with `repo_root` at
    # all (it starts with a sibling "outside" directory) -- a naive prefix
    # check on the raw path would call this fine. Only resolving the path
    # first reveals the ".." segments walk it back inside the repo, which
    # is what `load` must catch.
    repo_root = tmp_path / "repo"
    (repo_root / "sub").mkdir(parents=True)
    source = repo_root / "sub" / "forbidden.txt"
    source.write_text("SomeValue\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    escaping_spelling = outside / ".." / "repo" / "sub" / "forbidden.txt"
    assert not str(escaping_spelling).startswith(str(repo_root))
    monkeypatch.setenv(ENV_VAR, str(escaping_spelling))

    with pytest.raises(ForbiddenStringsSourceError):
        load(repo_root)


def test_load_raises_for_a_source_path_resolving_inside_the_repo_via_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "sub").mkdir(parents=True)
    real_target = repo_root / "sub" / "forbidden.txt"
    real_target.write_text("SomeValue\n")
    symlink_outside = tmp_path / "outside-link.txt"
    symlink_outside.symlink_to(real_target)
    monkeypatch.setenv(ENV_VAR, str(symlink_outside))

    with pytest.raises(ForbiddenStringsSourceError):
        load(repo_root)


def test_load_does_not_raise_for_a_symlink_that_genuinely_resolves_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Negative counterpart for the two symlink/dotdot tests above: a
    # symlink is not itself disqualifying -- only one that resolves inside
    # the repo is. Without this, a mutation that rejected every symlinked
    # source (whatever it resolves to) would pass every test above.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    real_target = tmp_path / "outside" / "forbidden.txt"
    real_target.parent.mkdir()
    real_target.write_text("SomeValue\n")
    symlink_inside_pointing_out = repo_root / "link.txt"
    symlink_inside_pointing_out.symlink_to(real_target)
    monkeypatch.setenv(ENV_VAR, str(symlink_inside_pointing_out))

    fs = load(repo_root)

    assert fs is not None
    assert fs.values == ("SomeValue",)


def test_load_parses_category_prefixed_lines_plain_lines_comments_and_blanks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "outside" / "forbidden.txt"
    source.parent.mkdir()
    source.write_text(
        "# a comment line\n"
        "\n"
        "token\tThirdPartyName\n"
        "path\tremoved/directory\n"
        "PlainValueWithNoCategory\n"
        "   \n"
    )
    monkeypatch.setenv(ENV_VAR, str(source))

    fs = load(repo_root)

    assert fs is not None
    assert fs.values == (
        "ThirdPartyName",
        "removed/directory",
        "PlainValueWithNoCategory",
    )


def test_forbidden_strings_construction_rejects_empty_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ForbiddenStrings(values=(), source=tmp_path / "forbidden.txt")


# --- require(): skip is the unset outcome, asserted as the skip exception -


def test_require_raises_the_skip_exception_when_variable_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)

    with pytest.raises(pytest.skip.Exception):
        require(tmp_path)


def test_require_returns_forbidden_strings_when_variable_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Negative counterpart for the skip test above: `require` does not
    # *always* skip -- only when the variable is genuinely unset.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = tmp_path / "outside" / "forbidden.txt"
    source.parent.mkdir()
    source.write_text("SomeValue\n")
    monkeypatch.setenv(ENV_VAR, str(source))

    try:
        fs = require(repo_root)
    except pytest.skip.Exception as exc:
        # `pytest.skip.Exception` derives from `BaseException`, so it would
        # otherwise propagate straight past a bare call and this test would
        # go SKIPPED rather than FAILED if `require` ever skipped although
        # the variable is set -- indistinguishable from a pass. Convert it
        # to an explicit failure so that defect cannot hide as a skip.
        pytest.fail(f"require() skipped although {ENV_VAR} is set: {exc}")

    assert fs.values == ("SomeValue",)


def test_require_does_not_convert_a_broken_source_into_a_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A broken (missing/unreadable/empty/in-repo) source must still raise
    # through `require`, not be swallowed into the "unset" skip outcome --
    # the exact collapse Req 11.8 forbids, one level up the call stack.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    missing = tmp_path / "outside" / "does-not-exist.txt"
    monkeypatch.setenv(ENV_VAR, str(missing))

    with pytest.raises(ForbiddenStringsSourceError):
        try:
            require(repo_root)
        except pytest.skip.Exception as exc:
            # Same BaseException-propagation hazard as above: a mutation
            # that skips instead of raising must fail this test, not skip
            # past the `pytest.raises` block entirely.
            pytest.fail(f"require() skipped instead of raising: {exc}")


# --- matches(): case-insensitive, every match, not just the first ---------


def test_matches_is_case_insensitive() -> None:
    fs = ForbiddenStrings(values=("ThirdPartyName",), source=Path("/outside/x.txt"))

    assert matches("a doc mentions thirdpartyname in passing", fs) == (
        "ThirdPartyName",
    )


def test_matches_returns_every_present_value_not_only_the_first() -> None:
    # `values` is deliberately NOT in alphabetical order, so returning
    # `sorted(...)` instead of `values` order is a distinguishable mutation.
    fs = ForbiddenStrings(
        values=("GammaToken", "AlphaToken", "BetaToken"),
        source=Path("/outside/x.txt"),
    )

    found = matches("text containing AlphaToken and also GammaToken here", fs)

    assert found == ("GammaToken", "AlphaToken")


def test_matches_returns_empty_tuple_when_nothing_is_present() -> None:
    fs = ForbiddenStrings(values=("AlphaToken",), source=Path("/outside/x.txt"))

    assert matches("nothing forbidden in this sentence", fs) == ()


# --- matches(): a multi-word value survives a line wrap --------------------
#
# Markdown prose wraps. A flat `value.lower() in text.lower()` cannot see a
# multi-word value whose words land on either side of a line break, and
# EVERYTHING built on this matcher inherited that blindness: the standing
# tracked-tree guard below, `scripts/purge/plan.py`'s content classification
# (which decides which historical blobs are `literal_replaceable`, i.e. which
# blobs the one-shot rewrite even attempts to redact), and the surviving-blob
# check of `tests/purge/test_replacements.py`'s invariant 1. Measured over
# every reachable blob of this repository at `89b06b8`: 448 flat occurrences
# of the two multi-word values against 485 wrap-tolerant ones -- 37 wrapped
# occurrences invisible to the flat test, in 13 (value, blob) pairs the flat
# test saw ZERO of.
#
# The redaction *rules* were never blind this way -- `build_rules` runs every
# multi-word token through `scripts/purge/replacements.py::
# _whitespace_tolerant_pattern` -- which is exactly why this went unnoticed:
# redaction was wrap-tolerant while every check on it was not, so no check
# could observe whether the rules had done their job on a wrapped occurrence.
#
# Every expectation below is written as literal text with a literal expected
# result. None of it is derived by calling `_whitespace_tolerant_pattern`,
# the helper `matches` now reuses: a test that computed its expectation from
# the implementation under test would agree with that implementation by
# construction and could not disagree with it -- the exact shape that let
# task 6.5's survivor counter score 49 -> 0 while the notice still stood in
# 11 blobs.


def test_matches_finds_a_multi_word_value_wrapped_across_a_line_break() -> None:
    fs = ForbiddenStrings(
        values=("Planted Wrapped Token",), source=Path("/outside/x.txt")
    )
    # The wrap falls after the FIRST word.
    early = "a paragraph mentioning Planted\nWrapped Token in passing\n"
    # ...and, in a second document, after the SECOND word: a matcher that
    # only tolerated a break at one fixed position would pass one and fail
    # the other.
    late = "a paragraph mentioning Planted Wrapped\nToken in passing\n"
    # A real markdown wrap re-indents the continuation line.
    indented = "  - a list item naming Planted\n    Wrapped Token in passing\n"

    assert matches(early, fs) == ("Planted Wrapped Token",)
    assert matches(late, fs) == ("Planted Wrapped Token",)
    assert matches(indented, fs) == ("Planted Wrapped Token",)


def test_matches_tolerates_any_whitespace_run_between_a_values_words() -> None:
    fs = ForbiddenStrings(values=("Planted Token",), source=Path("/outside/x.txt"))

    assert matches("a doc says Planted  Token here", fs) == ("Planted Token",)
    assert matches("a doc says Planted\tToken here", fs) == ("Planted Token",)
    # Across a blank line -- a paragraph break is still whitespace, and the
    # redaction rule matches there too, so the check must agree with it.
    assert matches("a doc says Planted\n\nToken here", fs) == ("Planted Token",)


def test_matches_does_not_join_a_multi_word_value_across_non_whitespace() -> None:
    """Wrap tolerance is whitespace tolerance and nothing wider. A pattern
    that joined the words with `.*?` (or that dropped word order) would pass
    the wrap tests above while matching text that does not contain the value
    at all -- an over-matching guard flags clean files and, worse, marks
    blobs `literal_replaceable` that carry nothing to replace."""
    fs = ForbiddenStrings(values=("Planted Token",), source=Path("/outside/x.txt"))

    assert matches("Planted, Token", fs) == ()
    assert matches("Planted and then Token", fs) == ()
    assert matches("PlantedToken", fs) == ()
    assert matches("Token Planted", fs) == ()
    # Only part of the value present, wrapped -- still not a match.
    assert matches("Planted\nnothing else", fs) == ()


def test_matches_single_word_value_is_not_split_by_wrap_tolerance() -> None:
    """A single-word value cannot wrap, so wrap tolerance must be a no-op
    for it. This is the regression this change is most able to cause: a
    matcher that inserted flexible whitespace BETWEEN CHARACTERS, or that
    treated a hyphen or a dot as a word split, would match text that does
    not contain the value -- and seven of this repository's nine real
    forbidden values are single-word."""
    fs = ForbiddenStrings(values=("AlphaToken",), source=Path("/outside/x.txt"))

    assert matches("AlphaToken", fs) == ("AlphaToken",)
    assert matches("Alpha\nToken", fs) == ()
    assert matches("Alpha Token", fs) == ()
    assert matches("Alpha\tToken", fs) == ()


def test_matches_treats_regex_metacharacters_in_a_value_literally() -> None:
    """The values are literals read from a file, not patterns. A dotted
    module path and a `+`-carrying name are both realistic entries, and both
    are regex metacharacter carriers -- an unescaped value would match text
    that merely has the same shape."""
    dotted = ForbiddenStrings(values=("a.b.c",), source=Path("/outside/x.txt"))
    assert matches("import a.b.c here", dotted) == ("a.b.c",)
    assert matches("import axbxc here", dotted) == ()

    plussed = ForbiddenStrings(values=("C++ Corp",), source=Path("/outside/x.txt"))
    assert matches("written by C++ Corp", plussed) == ("C++ Corp",)
    assert matches("written by CCC Corp", plussed) == ()
    assert matches("written by C++\nCorp", plussed) == ("C++ Corp",)


def test_matches_finds_a_wrapped_value_case_insensitively() -> None:
    """The two properties are independent: a wrap-tolerant pattern compiled
    without `re.IGNORECASE` would silently drop the case-insensitivity the
    flat matcher had."""
    fs = ForbiddenStrings(
        values=("Planted Wrapped Token",), source=Path("/outside/x.txt")
    )

    assert matches("says PLANTED\nWRAPPED token here", fs) == ("Planted Wrapped Token",)


def test_matches_on_a_path_name_is_unaffected_by_wrap_tolerance() -> None:
    """`matches` runs against path names as well as content (`scan_tree`,
    `_scan_content_and_path`, `scripts/purge/plan.py::classify_path`). A path
    cannot carry a newline, so wrap tolerance must neither find nor miss
    anything there -- a multi-word value still matches a path that spells it
    with a space, and does not match one that spells it with a separator."""
    fs = ForbiddenStrings(values=("Planted Token",), source=Path("/outside/x.txt"))

    assert matches("docs/Planted Token/notes.md", fs) == ("Planted Token",)
    assert matches("docs/planted token/notes.md", fs) == ("Planted Token",)
    assert matches("docs/Planted-Token/notes.md", fs) == ()
    assert matches("docs/Planted/Token/notes.md", fs) == ()


def test_matches_over_a_large_text_is_not_pathologically_slow() -> None:
    """A crude ceiling, not a benchmark: the wrap-tolerant pattern must not
    turn a whole-repository scan into something nobody runs. Measured over
    the real corpus (1936 blobs, 42.7 MB, 9 values of which 2 are
    multi-word), best of three passes each: 0.169s flat, 0.459s with this
    matcher, 1.445s without its single-word fast path, and 0.441s vs 0.449s
    with and without a compiled-pattern cache of its own -- which is why
    `_wrap_tolerant_pattern` has none. This pins only the crude
    property that a single scan of a ~1MB text full of near-misses stays
    well under a second -- what it is really there to catch is a pattern
    that backtracks catastrophically on a haystack of partial matches."""
    fs = ForbiddenStrings(
        values=("Planted Wrapped Token", "AlphaToken"),
        source=Path("/outside/x.txt"),
    )
    haystack = ("Planted words that never complete the value. " * 25_000) + "\n"
    assert len(haystack) > 1_000_000

    started = time.perf_counter()
    found = matches(haystack, fs)
    elapsed = time.perf_counter() - started

    assert found == ()
    assert elapsed < 1.0, f"one scan of a ~1MB text took {elapsed:.3f}s"


# --- scan_tree(): content AND path name, root as a parameter ---------------


def test_scan_tree_flags_content_and_path_matches_but_not_a_clean_file(
    tmp_path: Path,
) -> None:
    fs = ForbiddenStrings(values=("PlantedToken",), source=tmp_path / "src.txt")
    root = tmp_path / "synthetic"
    root.mkdir()
    content_hit = root / "clean-name.txt"
    content_hit.write_text("this file's content says PlantedToken right here\n")
    path_hit = root / "PlantedToken-in-the-name.txt"
    path_hit.write_text("nothing forbidden in here\n")
    clean = root / "entirely-clean.txt"
    clean.write_text("nothing forbidden in here either\n")
    # A file nested several directories deep, whose CONTENT carries the
    # token -- pins that scanning actually descends the tree rather than
    # only listing `root`'s immediate children (`root.rglob` vs `root.glob`).
    nested_content_hit = root / "nested" / "deep" / "f.txt"
    nested_content_hit.parent.mkdir(parents=True)
    nested_content_hit.write_text("PlantedToken buried in a nested file\n")
    # A nested DIRECTORY whose name (not the leaf file's name) carries the
    # token -- pins that the path-surface check considers parent path
    # components, not only the file's own basename.
    nested_dir_name_hit = root / "PlantedToken-dir" / "leaf.txt"
    nested_dir_name_hit.parent.mkdir(parents=True)
    nested_dir_name_hit.write_text("nothing forbidden in here\n")
    # Inside a DOT-directory. The tree this guard really runs against keeps
    # its token-bearing prose in `.kiro/`, so a walk that skipped dot-paths
    # would miss the material while still reporting a clean scan.
    dot_dir_hit = root / ".hidden" / "note.txt"
    dot_dir_hit.parent.mkdir(parents=True)
    dot_dir_hit.write_text("PlantedToken inside a dot-directory\n")

    hits = scan_tree(root, fs)

    by_path = {(hit.path, hit.surface) for hit in hits}
    assert (Path("clean-name.txt"), "content") in by_path
    assert (Path("PlantedToken-in-the-name.txt"), "path") in by_path
    assert not any(hit.path == Path("entirely-clean.txt") for hit in hits)
    assert (Path("nested/deep/f.txt"), "content") in by_path
    assert (Path("PlantedToken-dir/leaf.txt"), "path") in by_path
    assert (Path(".hidden/note.txt"), "content") in by_path
    # And the clean file contributed no hit of either surface at all.
    assert len(hits) == 5


def test_scan_tree_finds_no_hits_over_a_tree_with_no_planted_instance(
    tmp_path: Path,
) -> None:
    # Positive control's negative counterpart at the whole-scan level: an
    # entirely clean tree must come back empty. Pinned directly here rather
    # than inferred from the positive control above, which only asserts
    # specific hits and a specific count over a tree that mixes clean and
    # planted files.
    fs = ForbiddenStrings(values=("PlantedToken",), source=tmp_path / "src.txt")
    root = tmp_path / "synthetic-clean"
    root.mkdir()
    (root / "a.txt").write_text("nothing here\n")
    (root / "b.txt").write_text("nothing here either\n")

    assert scan_tree(root, fs) == ()


def test_scan_tree_takes_the_scanned_root_as_a_parameter_not_a_constant(
    tmp_path: Path,
) -> None:
    fs = ForbiddenStrings(values=("PlantedToken",), source=tmp_path / "src.txt")
    root_with_hit = tmp_path / "root-a"
    root_with_hit.mkdir()
    (root_with_hit / "f.txt").write_text("PlantedToken appears here\n")
    root_without_hit = tmp_path / "root-b"
    root_without_hit.mkdir()
    (root_without_hit / "f.txt").write_text("nothing here\n")

    assert len(scan_tree(root_with_hit, fs)) == 1
    assert scan_tree(root_without_hit, fs) == ()


def test_scan_tree_completes_over_an_undecodable_file_matching_only_its_path(
    tmp_path: Path,
) -> None:
    # Pins the documented binary-file guard: a file that cannot be decoded
    # as UTF-8 must not abort the scan (Req 3.1 -- a scan must run to
    # completion). Its content is skipped rather than raising, but its path
    # name is still checked like any other file's.
    fs = ForbiddenStrings(values=("PlantedToken",), source=tmp_path / "src.txt")
    root = tmp_path / "synthetic-binary"
    root.mkdir()
    binary_hit = root / "PlantedToken-binary.bin"
    binary_hit.write_bytes(b"\xff\xfe\x00PlantedToken")
    clean = root / "clean.txt"
    clean.write_text("nothing forbidden in here\n")

    hits = scan_tree(root, fs)

    by_path = {(hit.path, hit.surface) for hit in hits}
    assert (Path("PlantedToken-binary.bin"), "path") in by_path
    assert not any(
        hit.path == Path("PlantedToken-binary.bin") and hit.surface == "content"
        for hit in hits
    )
    assert len(hits) == 1


def test_hit_is_constructible_with_the_documented_fields() -> None:
    hit = Hit(path=Path("a/b.txt"), surface="content", found=("X",))

    assert hit.path == Path("a/b.txt")
    assert hit.surface == "content"
    assert hit.found == ("X",)


def test_env_var_name_matches_the_name_design_md_documents() -> None:
    # Pinned literally rather than only exercised through monkeypatch above:
    # this is the exact string a maintainer must export, and Req 11.10
    # forbids a token in it, so the name itself is worth asserting directly.
    assert ENV_VAR == "FITDOCS_FORBIDDEN_STRINGS"


# ============================================================================
# The standing guard (task 4.3, design.md `#### ForbiddenStrings`
# Implementation Notes, Req 3.3, 3.4, 3.5, 11.2, 11.7, 11.8, 11.10).
#
# Everything above this line pins `tests/_forbidden_strings.py`'s loader
# behaviour with synthetic sources and invented values. Everything below is
# the standing guard itself: the ONE mechanism in this suite that scans the
# REAL repository -- every tracked file's content, every tracked path name,
# a built sdist's members, and a built wheel's members -- for whatever
# `FITDOCS_FORBIDDEN_STRINGS` supplies. Before this landed, nothing did:
# a real token-category value planted in README.md, or in docs/plugins.md,
# left `uv run pytest` green (measured directly, not inferred). The five
# `*_{is,are}_scanned_and_clean` guards in tests/purge/test_sweep.py that
# this subsumes name EIGHT sites between them, not five or six: three are
# singular (`_is_scanned_and_clean`, one site each) and two are plural
# (`_are_scanned_and_clean`, three training-load documents in one function
# and two steering documents in the other) -- 1 + 3 + 2 + 1 + 1 = 8. This
# guard covers every tracked path and both built artifacts by construction,
# not by naming sites.
# ============================================================================


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tracked_files(repo_root: Path) -> tuple[Path, ...]:
    """Every path `git ls-files` reports, as absolute paths under
    `repo_root`.

    Deliberately NOT `scan_tree`'s own filesystem walk: `scan_tree`'s
    docstring says plainly that it does no tracked/ignored filtering of its
    own, so calling it directly against the real repository root would also
    descend `.venv/` and `dist/` -- out of universe and prohibitively slow.
    `scripts/purge/sweep.py`'s own `tracked_files` solves the identical
    problem the same way: the universe is `git ls-files`, never a
    filesystem walk.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    return tuple(repo_root / name for name in names)


def _synthetic_files(root: Path) -> tuple[Path, ...]:
    """Every file under a synthetic control tree, for the same shared
    content-and-path scanner `_tracked_files` feeds against the real repo."""
    return tuple(
        sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
    )


def _scan_content_and_path(
    files: Sequence[Path], root: Path, forbidden_strings: ForbiddenStrings
) -> tuple[tuple[Hit, ...], tuple[Path, ...]]:
    """Content-and-path scan over an explicit file list, one shared
    mechanism the positive controls and the real-tree absence scan below
    both exercise -- so a control that pins this function's path-name
    branch also pins what the real-tree scan depends on, rather than
    pinning a duplicate, unused implementation.

    Returns the hits, and SEPARATELY every file whose bytes could not even
    be opened (a broken symlink, a permission-denied file) -- the
    "unreadable file is silent" gap `tests/_forbidden_strings.py`'s own
    `scan_tree` docstring names ("an unreadable file whose content carries
    a forbidden value yields no hit and no report"). A file that opens but
    is not valid UTF-8 is NOT in that second tuple: its bytes are decoded
    permissively (``errors="replace"``) and scanned like any other file's,
    so an undecodable byte narrows nothing (Req 3.1 -- a scan must run to
    completion). A `try`/`except` that instead skipped undecodable content
    would be an exemption whose width is whatever the exception covers --
    task 4.1's own history records a single stray non-UTF-8 byte defeating
    a decode-and-skip sdist scan built exactly that way.
    """
    hits: list[Hit] = []
    unreadable: list[Path] = []
    for path in files:
        relative = path.relative_to(root)

        path_matches = matches(str(relative), forbidden_strings)
        if path_matches:
            hits.append(Hit(path=relative, surface="path", found=path_matches))

        try:
            raw = path.read_bytes()
        except OSError:
            unreadable.append(relative)
            continue
        content = raw.decode("utf-8", errors="replace")
        content_matches = matches(content, forbidden_strings)
        if content_matches:
            hits.append(Hit(path=relative, surface="content", found=content_matches))

    return tuple(hits), tuple(unreadable)


def _decode_permissively(content: bytes) -> str:
    """Same permissive decode `_scan_content_and_path` uses, for archive
    members. ``errors="replace"`` rather than skipping undecodable content
    -- see `_scan_content_and_path`'s docstring for why a skip is the wrong
    shape here."""
    return content.decode("utf-8", errors="replace")


def _build_artifact(repo_root: Path, out_dir: Path, flag: str) -> None:
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required to build the artifact this guard scans but was not "
        "found on PATH; install uv (https://docs.astral.sh/uv/) to run it"
    )
    build = subprocess.run(
        [uv, "build", flag, "--out-dir", str(out_dir)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_S,
        check=False,
    )
    assert build.returncode == 0, (
        f"`uv build {flag}` failed:\n{build.stdout}\n{build.stderr}"
    )


def _scan_members(
    members: Sequence[tuple[str, bytes]], forbidden_strings: ForbiddenStrings
) -> tuple[Hit, ...]:
    """Content-and-name scan over an explicit ``(member name, raw bytes)``
    sequence -- the ONE mechanism both the sdist and the wheel absence
    scans below use to build their `Hit`s, and the mechanism
    `test_scan_members_flags_content_and_name_but_not_a_clean_member` below
    pins directly with a synthetic member list. Without a shared,
    positive-controlled helper here, the wheel scan in particular has no
    real *forbidden-string* content to prove its own content/name gating
    fires: the wheel carries real content (including `dist-info/METADATA`,
    which embeds the whole of `README.md`), but none of it matches any
    value `FITDOCS_FORBIDDEN_STRINGS` supplies today, so an "assert hits"
    sanity check against real wheel content would have nothing to lean on,
    and the gating logic (``if content_matches: hits.append(...)``) would
    be reachable but unpinned.
    """
    hits: list[Hit] = []
    for name, raw in members:
        relative = Path(name)
        name_matches = matches(name, forbidden_strings)
        if name_matches:
            hits.append(Hit(path=relative, surface="path", found=name_matches))
        content = _decode_permissively(raw)
        content_matches = matches(content, forbidden_strings)
        if content_matches:
            hits.append(Hit(path=relative, surface="content", found=content_matches))
    return tuple(hits)


def test_scan_members_flags_content_and_name_but_not_a_clean_member() -> None:
    """The archive-member positive control the sdist/wheel absence scans
    below depend on: `_scan_members` flags a member whose content carries a
    genuinely loaded forbidden value, flags a second member whose NAME
    does, and does not flag a third, clean member -- so the control cannot
    pass by matching everything, the same three-file shape
    `test_standing_guard_positive_controls_flag_content_and_path_but_not_clean_file`
    uses for the tracked-tree scan.
    """
    forbidden_strings = require(_repo_root())
    supplied = forbidden_strings.values[0]
    members = [
        ("clean-name.txt", f"this member's content says {supplied} here".encode()),
        (f"{supplied}-in-the-name.txt", b"nothing forbidden in here"),
        ("entirely-clean.txt", b"nothing forbidden in here either"),
    ]

    hits = _scan_members(members, forbidden_strings)

    by_path_surface = {(hit.path, hit.surface) for hit in hits}
    assert (Path("clean-name.txt"), "content") in by_path_surface, (
        "the content-surface positive control was not flagged"
    )
    assert (Path(f"{supplied}-in-the-name.txt"), "path") in by_path_surface, (
        "the name-surface positive control was not flagged"
    )
    assert not any(hit.path == Path("entirely-clean.txt") for hit in hits), (
        "the clean sibling member was flagged -- the control passes by "
        "matching everything, which pins nothing"
    )
    assert len(hits) == 2, (
        f"expected exactly the two planted hits, got {len(hits)}: "
        f"{[(h.surface, str(h.path)) for h in hits]}"
    )


# --- Req 11.8: the guard's own skip is a skip, never a pass ---------------


def test_standing_guard_source_raises_skip_exception_when_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact call every surface test below makes first: `require()`,
    against this guard's own real `_repo_root()`, raises pytest's skip
    exception -- not a bare return, not a pass -- when
    `FITDOCS_FORBIDDEN_STRINGS` is unset. Distinct from the generic version
    of this assertion in `tests/test_forbidden_strings_source.py` (which
    uses a synthetic `tmp_path` repo root): every surface test in this
    section is only as skip-safe as this exact call is, so it is pinned
    here too, against the real root this guard actually uses.
    """
    monkeypatch.delenv(ENV_VAR, raising=False)
    repo_root = _repo_root()

    with pytest.raises(pytest.skip.Exception):
        require(repo_root)


# --- Req 3.3, 3.4: two positive controls, run before any absence scan -----


def test_standing_guard_positive_controls_flag_content_and_path_but_not_clean_file(
    tmp_path: Path,
) -> None:
    """The guard has two matchers -- content and path name -- so it needs
    two controls: a control that only plants a content hit leaves the
    path-name matcher entirely unpinned, and the path-name matcher is the
    only thing carrying Req 11.2 forward as a standing property.

    Both controls run through `_scan_content_and_path`, the exact function
    `test_standing_guard_scans_tracked_content_and_path_names` below uses
    against the real repository -- not a separate, unused implementation --
    so a mutation that disables one matcher there is caught here first, and
    a plain (no try/except) assertion failure below is a real failure, not
    a skip.

    Seeded from a genuinely loaded `ForbiddenStrings.values[0]` via
    `require()`, not an invented string: the observable this pins is "a
    source supplied from outside the repository", the real mechanism, not
    a stand-in for it.
    """
    repo_root = _repo_root()
    forbidden_strings = require(repo_root)
    supplied = forbidden_strings.values[0]

    root = tmp_path / "standing-guard-positive-control"
    root.mkdir()
    content_hit = root / "clean-name.txt"
    content_hit.write_text(f"this file's content says {supplied} right here\n")
    path_hit = root / f"{supplied}-in-the-name.txt"
    path_hit.write_text("nothing forbidden in here\n")
    clean = root / "entirely-clean.txt"
    clean.write_text("nothing forbidden in here either\n")

    hits, unreadable = _scan_content_and_path(
        _synthetic_files(root), root, forbidden_strings
    )

    assert not unreadable, (
        f"the control's own planted files were unreadable: {unreadable}"
    )
    by_path_surface = {(hit.path, hit.surface) for hit in hits}
    assert (Path("clean-name.txt"), "content") in by_path_surface, (
        "the content-surface positive control was not flagged"
    )
    assert (Path(f"{supplied}-in-the-name.txt"), "path") in by_path_surface, (
        "the path-name-surface positive control was not flagged"
    )
    assert not any(hit.path == Path("entirely-clean.txt") for hit in hits), (
        "the clean sibling file was flagged -- the control passes by "
        "matching everything, which pins nothing"
    )
    assert len(hits) == 2, (
        f"expected exactly the two planted hits, got {len(hits)}: "
        f"{[(h.surface, str(h.path)) for h in hits]}"
    )


def test_standing_guard_flags_a_multi_word_value_wrapped_across_a_line_break(
    tmp_path: Path,
) -> None:
    """The blast radius of the flat matcher reached this guard: a wrapped
    multi-word value pasted into a tracked file passed it, so the tip was
    not as clean as the guard reported -- and invariant 6 (the tip no-op)
    would have fired instead, at the point where it is least convenient to
    diagnose. Pinned here at the guard's own level -- `_scan_content_and_path`,
    the exact function `test_standing_guard_scans_tracked_content_and_path_names`
    runs against the real repository -- not only at `matches`'s.

    The planted value is synthetic rather than `require()`d from
    `FITDOCS_FORBIDDEN_STRINGS`, for two reasons: the real source's
    `values[0]` happening to be multi-word today is an accident of that
    file's contents (a conditional skip here would make this pin disappear
    the day it changes), and a synthetic value keeps this control running in
    the unset configuration too, where the real-tree guard skips.

    The clean sibling spells both of the value's outer words, separated by
    text -- so a matcher that over-tolerated its way to a pass on the
    wrapped file fails here instead of quietly flagging everything.
    """
    forbidden_strings = ForbiddenStrings(
        values=("Planted Wrapped Token",), source=tmp_path / "outside.tsv"
    )
    root = tmp_path / "wrapped-positive-control"
    root.mkdir()
    wrapped = root / "wrapped.md"
    wrapped.write_text(
        "a paragraph of prose that names Planted\nWrapped Token mid-sentence\n"
    )
    clean = root / "entirely-clean.md"
    clean.write_text("a paragraph naming Planted, and separately a Wrapped Token\n")

    hits, unreadable = _scan_content_and_path(
        _synthetic_files(root), root, forbidden_strings
    )

    assert not unreadable, (
        f"the control's own planted files were unreadable: {unreadable}"
    )
    assert {(hit.path, hit.surface) for hit in hits} == {
        (Path("wrapped.md"), "content")
    }


# --- Req 3.1: an unreadable file is reported, never silently clean --------


def test_scan_content_and_path_reports_a_genuinely_unreadable_file(
    tmp_path: Path,
) -> None:
    """A file whose bytes cannot even be opened (a broken symlink here) is
    reported in the second return value, never silently contributing no hit
    and no report -- the exact "unreadable file is silent" gap
    `tests/_forbidden_strings.py`'s own `scan_tree` docstring names.

    Distinct from a file that opens but decodes badly (pinned separately
    below): this fixture's target does not exist at all, so `read_bytes()`
    itself raises `OSError`, never reaching a decode step.

    Passes the file list explicitly rather than through `_synthetic_files`:
    `Path.is_file()` follows symlinks and returns `False` for a broken one,
    so `_synthetic_files`'s own `rglob(...).is_file()` filter silently
    drops it before `_scan_content_and_path` ever sees it -- the identical
    "silent" failure shape one level earlier, and not what this test means
    to pin.
    """
    fs = ForbiddenStrings(values=("PlantedToken",), source=tmp_path / "src.txt")
    root = tmp_path / "unreadable-fixture"
    root.mkdir()
    broken = root / "broken-link.txt"
    broken.symlink_to(root / "does-not-exist.txt")
    clean = root / "clean.txt"
    clean.write_text("nothing forbidden in here\n")

    hits, unreadable = _scan_content_and_path((broken, clean), root, fs)

    assert unreadable == (Path("broken-link.txt"),), (
        f"expected exactly the broken symlink reported as unreadable, got {unreadable}"
    )
    assert hits == (), (
        f"expected no hits (the clean file is clean and the broken symlink "
        f"contributed no content match), got {hits}"
    )


# --- Req 3.1: undecodable bytes are scanned, never skipped -----------------


def test_scan_content_and_path_still_matches_content_beside_an_undecodable_byte(
    tmp_path: Path,
) -> None:
    """A numeric-token-style byte that is not valid UTF-8 sitting beside a
    genuinely present forbidden string must not hide it: content is decoded
    permissively (``errors="replace"``), never skipped outright on a decode
    failure. A `try`/`except` around the decode that instead skipped the
    whole file would be an unbounded exemption -- task 4.1's own history
    (see `tests/load/test_packaging.py`'s module docstring) records exactly
    this defect in a sibling guard: one stray non-UTF-8 byte made an entire
    member's content invisible to that scan.
    """
    fs = ForbiddenStrings(values=("PlantedToken",), source=tmp_path / "src.txt")
    root = tmp_path / "undecodable-fixture"
    root.mkdir()
    # 0xB0 alone is not a valid UTF-8 byte sequence (a continuation byte
    # with no leading byte before it) -- confirmed below, not merely
    # asserted, so this fixture is proven to exercise the decode failure it
    # claims to.
    undecodable = root / "undecodable.bin"
    undecodable_bytes = b"\xb0PlantedToken is right here\xb0"
    with pytest.raises(UnicodeDecodeError):
        undecodable_bytes.decode("utf-8")
    undecodable.write_bytes(undecodable_bytes)

    hits, unreadable = _scan_content_and_path(_synthetic_files(root), root, fs)

    assert unreadable == (), (
        f"the undecodable file must not be reported as unreadable -- its "
        f"bytes opened fine, only decoding needed the permissive fallback: "
        f"{unreadable}"
    )
    assert (Path("undecodable.bin"), "content") in {
        (hit.path, hit.surface) for hit in hits
    }, "a genuinely present value beside undecodable bytes was not flagged"


def test_standing_guard_scans_tracked_content_and_path_names() -> None:
    """The path-name surface is what carries Req 11.2 forward as a standing
    property rather than a one-time act (it subsumes the retired package
    path-existence assertion, tasks 4.1/4.4); the content surface is what
    closes the measured gap this task exists to close (a real token planted
    in README.md, or docs/plugins.md, left `uv run pytest` green before this
    guard existed).

    Reports counts and locations to stdout. For a CONTENT-surface hit the
    matched string appears only in the assertion message below, never in a
    print -- but for a PATH-surface hit the "location" printed here IS the
    matched string, since the match is the path itself; that overlap is
    inherent to what a path-name scan reports, not an omission (a false
    claim of a blanket property here was corrected at review -- reviewer
    finding F6).
    """
    repo_root = _repo_root()
    forbidden_strings = require(repo_root)
    files = _tracked_files(repo_root)

    assert files, (
        "git ls-files reported zero tracked files -- this guard is looking "
        "at the wrong root, not proving the tree is clean"
    )
    scanned_relative = {str(path.relative_to(repo_root)) for path in files}
    # Coverage pin, not just non-emptiness (reviewer finding F1): `git
    # ls-files -z ... src` (dropping .kiro/ -- the Implementation Notes'
    # own load-bearing case) or `[...][:1]` (one file) both leave `files`
    # non-empty, so `assert files` alone does not catch a narrowed walk.
    # `.kiro/`, `src/` and `tests/` are all real, permanently-tracked
    # directories independent of anything this task's own diff touches.
    # `tests/purge/` served the third role until encumbered-content-purge
    # task 9.3 deleted it (design.md `#### MachineryRetirement`); `tests/`
    # itself replaces it here as the third coverage pin, because a walk
    # that narrows away the entire `tests/` tree -- `git ls-files -z src
    # .kiro docs` -- leaves this guard's own helpers and match-data loader
    # unscanned and would report a false clean about the guards' own home;
    # `src/` alone does not defeat that narrowing.
    assert any(rel.startswith(".kiro/") for rel in scanned_relative), (
        "the tracked-file walk covers no .kiro/ path -- this repository's "
        "token-bearing prose lives there (Implementation Notes), so a walk "
        "that silently narrowed away from it would report a false clean"
    )
    assert any(rel.startswith("src/") for rel in scanned_relative), (
        "the tracked-file walk covers no src/ path -- a narrowed walk "
        "excluding it would report a false clean"
    )
    assert any(rel.startswith("tests/") for rel in scanned_relative), (
        "the tracked-file walk covers no tests/ path -- this guard's own "
        "helpers and match-data loader live there, so a walk that "
        "narrowed away the entire tests/ tree would report a false clean "
        "about the guards' own home"
    )

    hits, unreadable = _scan_content_and_path(files, repo_root, forbidden_strings)

    print(
        f"forbidden-string tracked-tree scan: {len(files)} tracked file(s) "
        f"scanned, {len(hits)} total hit(s), {len(unreadable)} unreadable "
        f"file(s)"
    )
    for hit in hits:
        print(f"  {hit.surface}: {hit.path}")
    for path in unreadable:
        print(f"  unreadable: {path}")

    assert not unreadable, (
        f"{len(unreadable)} tracked file(s) could not even be opened, so "
        f"this scan cannot vouch for their content -- absence of a hit for "
        f"these files is not absence of a forbidden string: "
        f"{[str(p) for p in unreadable]}"
    )
    # Task 6.3: the tracked tree carries zero forbidden values -- every
    # former reviewed-exemption entry pointed at content that has since been
    # redacted or sourced from FITDOCS_FORBIDDEN_STRINGS itself, so there is
    # no exemption table to consult here any more. A hit is a hit.
    assert not hits, (
        f"tracked tree contains a forbidden string: "
        f"{[(h.surface, str(h.path), h.found) for h in hits]}"
    )


# --- Req 11.7: absence scan, surface 3 of 4 -- built sdist members ---------


def _strip_archive_prefix(member_name: str) -> str:
    """Drop a built sdist's ``fitdocs-X.Y.Z/`` top-level directory, so the
    remainder matches the repo-relative paths reported for the tracked-tree
    scan above -- one set of reported paths, not a second, version-sensitive
    one keyed by prefixed archive member names."""
    _, _, rest = member_name.partition("/")
    return rest


def test_standing_guard_scans_sdist_members_content_and_names(
    tmp_path: Path,
) -> None:
    """A built sdist ships the working tree minus `.gitignore` (hatchling's
    default sdist scope -- not "whatever git tracks": an untracked-but-
    unignored file ships too, `tests/load/test_packaging.py`'s own module
    docstring measured this directly). Ships under the archive's
    ``fitdocs-X.Y.Z/`` prefix, stripped above before reporting.
    """
    repo_root = _repo_root()
    forbidden_strings = require(repo_root)
    _build_artifact(repo_root, tmp_path, "--sdist")

    sdists = sorted(tmp_path.glob("*.tar.gz"))
    assert len(sdists) == 1, f"expected exactly one built sdist, got {sdists}"

    members: list[tuple[str, bytes]] = []
    with tarfile.open(sdists[0]) as sdist:
        for member in sdist.getmembers():
            if not member.isfile():
                continue
            fileobj = sdist.extractfile(member)
            if fileobj is None:
                continue
            members.append((_strip_archive_prefix(member.name), fileobj.read()))

    assert members, (
        "the sdist member scan opened zero regular members -- this guard's "
        "walk is inspecting nothing, not proving the archive is clean"
    )
    # Coverage pin, not just non-emptiness (reviewer finding F1): a member
    # loop narrowed to a single fixed member (e.g. only `PKG-INFO`) leaves
    # `members` non-empty, so `assert members` alone would not catch it.
    # TWO anchors of DIFFERENT extensions, not one: a `.py`-only member
    # loop is a plausible narrowing ("just scan source") that a single
    # `.py` anchor cannot detect by construction -- it would still find
    # itself. `README.md` is a non-`.py` anchor at the archive's top level,
    # so a `.py`-only filter reds this second assertion (reviewer finding,
    # round 2 item 4).
    scanned_names = {name for name, _ in members}
    assert "src/fitdocs/__init__.py" in scanned_names, (
        "the sdist member scan did not reach src/fitdocs/__init__.py -- "
        "the member loop is narrower than the built archive, not proving "
        "the whole archive is clean"
    )
    assert "README.md" in scanned_names, (
        "the sdist member scan did not reach README.md -- a member loop "
        "narrowed to only .py files would still satisfy the src/fitdocs/"
        "__init__.py anchor above, so this second, non-.py anchor is what "
        "catches that narrowing"
    )

    hits = _scan_members(members, forbidden_strings)

    print(
        f"forbidden-string sdist scan: {len(members)} member(s) scanned, "
        f"{len(hits)} total hit(s)"
    )
    for hit in hits:
        print(f"  {hit.surface}: {hit.path}")

    # Task 6.3: no exemption table exists any more -- a hit is a hit.
    assert not hits, (
        f"built sdist contains a forbidden string: "
        f"{[(h.surface, str(h.path), h.found) for h in hits]}"
    )


# --- Req 11.7: absence scan, surface 4 of 4 -- built wheel members ---------


def test_standing_guard_scans_wheel_members_content_and_names(
    tmp_path: Path,
) -> None:
    """A built wheel is NOT scoped to only `src/fitdocs`: it also carries
    `*.dist-info/` metadata, including `METADATA`, which embeds the whole
    of `long_description` (this project's `README.md`, per `pyproject.toml`)
    -- confirmed directly, not assumed: the wheel this test builds opens 68
    members, and planting a value in `README.md` reds this test through
    `METADATA`, exactly the same as it reds the tracked-tree and sdist
    scans (a prior draft's "expected to be clean" / "scoped to src/fitdocs"
    claim here was wrong -- reviewer finding F7).
    """
    repo_root = _repo_root()
    forbidden_strings = require(repo_root)
    _build_artifact(repo_root, tmp_path, "--wheel")

    wheels = sorted(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"

    members: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(wheels[0]) as wheel:
        for name in wheel.namelist():
            if name.endswith("/"):
                continue
            members.append((name, wheel.read(name)))

    assert members, (
        "the wheel member scan opened zero regular members -- this guard's "
        "walk is inspecting nothing, not proving the archive is clean"
    )
    # Coverage pin, not just non-emptiness (reviewer finding F1): a member
    # loop narrowed to `members[:1]` leaves `members` non-empty, and
    # `fitdocs/__init__.py` alone is not enough either -- it is the FIRST
    # member `zipfile.namelist()` reports for this wheel (measured
    # directly), so `members[:1]` alone would satisfy that one check too.
    # The `dist-info/METADATA` member is near the end of the same listing,
    # so both together defeat any single-element or short-prefix slice.
    # Matched by suffix, not the version-embedded exact path (a wheel's
    # `dist-info/` directory name carries the project version).
    scanned_names = {name for name, _ in members}
    assert "fitdocs/__init__.py" in scanned_names, (
        "the wheel member scan did not reach fitdocs/__init__.py -- the "
        "member loop is narrower than the built wheel, not proving the "
        "whole wheel is clean"
    )
    assert any(name.endswith(".dist-info/METADATA") for name in scanned_names), (
        "the wheel member scan did not reach the dist-info METADATA member "
        "-- the member loop is narrower than the built wheel, not proving "
        "the whole wheel is clean"
    )

    hits = _scan_members(members, forbidden_strings)

    print(
        f"forbidden-string wheel scan: {len(members)} member(s) scanned, "
        f"{len(hits)} total hit(s)"
    )
    for hit in hits:
        print(f"  {hit.surface}: {hit.path}")

    # Task 6.3: no exemption table exists any more -- a hit is a hit.
    assert not hits, (
        f"built wheel contains a forbidden string: "
        f"{[(h.surface, str(h.path), h.found) for h in hits]}"
    )


# ============================================================================
# The notice/mark tip guard (encumbered-content-purge task 6.5, re-homed here
# by task 7.2, design.md `#### MachineryRetirement` Phase R0, Req 3.3, 11.4,
# 11.6, 11.8, 11.9, 11.12, 12.2).
#
# NOTHING BELOW SPELLS THE RESERVED-RIGHTS PHRASE OR THE TRADEMARK MARK, and
# this guard is what keeps that true of the whole repository rather than of
# only this file. `_count_notice_phrase` -- the survivor counter this guard
# calls -- lives in `tests/_forbidden_strings.py`, built from nothing
# `matches`/`_wrap_tolerant_pattern` above define: see that module's own
# notice/mark section header for why (an earlier counter that shared an
# implementation with the redaction rule under test scored a real corpus
# 49 -> 0 while 11 comment-wrapped notices stood untouched).
#
# Distinct from every guard above this section: this one is UNGATED (needs no
# FITDOCS_FORBIDDEN_STRINGS) and matches two needles that are not identifying
# tokens at all -- they name nobody, which is why `matches()` above never
# flags them -- but ARE matched by `scripts/purge/replacements.py::
# notice_rules` / `trademark_mark_rule`'s emitted rules, so any tracked blob
# spelling either contiguously is a real hazard for that rule set's own
# tip-no-op invariant (`scripts/purge/replacements.py`'s module docstring,
# "invariant 6").
# ============================================================================

_NOTICE_PHRASE = " ".join(_NOTICE_PHRASE_WORDS)


def _notice_guard_tracked_texts() -> tuple[dict[str, str], dict[str, str]]:
    """Every tracked file's WORKING-TREE text (name -> text), plus every
    tracked file that could not be read as UTF-8 text (name -> reason).

    Ungated and reads the WORKING tree (not `HEAD`'s blobs), same as
    `_tracked_files` above -- an uncommitted paste is caught in the run that
    made it. Kept independent of `_tracked_files`/`_scan_content_and_path`
    above only in what it returns (a name -> text mapping plus an explicit
    unreadable-reason mapping, rather than `Hit`s against a `ForbiddenStrings`
    source): this guard has no `ForbiddenStrings` source to match against."""
    repo_root = _repo_root()
    texts: dict[str, str] = {}
    unreadable: dict[str, str] = {}
    for path in _tracked_files(repo_root):
        relative = str(path.relative_to(repo_root))
        if not path.is_file():
            unreadable[relative] = "not a regular file"
            continue
        try:
            texts[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            unreadable[relative] = "not UTF-8"
        except OSError as exc:
            unreadable[relative] = f"unreadable: {exc.strerror}"
    return texts, unreadable


def test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file() -> None:
    """The standing tip guard for these two needles, and the reason any test
    module in this repository may talk about them at all.

    This is not a restatement of `scripts/purge/replacements.py`'s invariant
    6: that one applies the built rule set to `HEAD`'s blobs and needs
    `FITDOCS_FORBIDDEN_STRINGS`; this one is ungated, reads the working tree,
    and names the needle in its failure message, so a session that pastes a
    notice into a spec file or a queue item finds out in the same run rather
    than at the next acceptance pass."""
    texts, unreadable = _notice_guard_tracked_texts()
    assert len(texts) > 100, (
        "the walk is looking at the wrong directory -- "
        f"only {len(texts)} tracked text files found"
    )
    unexpected_unreadable = {
        name: why
        for name, why in unreadable.items()
        if not name.endswith((".fit", ".png", ".gz"))
    }
    assert not unexpected_unreadable, (
        "tracked file(s) neither read nor accounted for by the notice/mark "
        f"guard: {unexpected_unreadable}"
    )

    # Req 3.3: the matcher demonstrates in THIS run that it finds a genuinely
    # present instance -- in every wrap shape it claims to cover: flat, a
    # bare line wrap (no comment marker on the continuation line), and a
    # comment-continuation wrap (the shape that slipped past an earlier
    # version of this guard and left 11 real notices undetected).
    words = _NOTICE_PHRASE.split()
    planted_flat = f"a notice: {_NOTICE_PHRASE}."
    planted_line_wrapped = "a notice: {} {}\n{}.".format(*words[:2], words[2])
    planted_comment_wrapped = "# {} {}\n# {}".format(*words[:2], words[2])
    assert _count_notice_phrase(planted_flat) == 1, planted_flat
    assert _count_notice_phrase(planted_line_wrapped) == 1, planted_line_wrapped
    assert _count_notice_phrase(planted_comment_wrapped) == 1, planted_comment_wrapped
    assert _NOTICE_TRADEMARK_MARK in f"x{_NOTICE_TRADEMARK_MARK}y"

    offenders = {
        name: (_count_notice_phrase(text), text.count(_NOTICE_TRADEMARK_MARK))
        for name, text in texts.items()
        if _count_notice_phrase(text) or _NOTICE_TRADEMARK_MARK in text
    }
    assert not offenders, (
        "the reserved-rights phrase or the trademark mark is present in a "
        f"tracked file (name -> (phrase count, mark count)): {offenders}. "
        "Describe the notice instead of reproducing it -- Req 11.4 forbids "
        "it at any commit, and the one-shot rewrite's rules would rewrite "
        "the tip."
    )
