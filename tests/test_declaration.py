"""In-tree ownership declaration: text composition and placement (Req 3.1-3.8).

Covers :mod:`fitdocs.declaration`'s pure text builder and its two placement
functions -- ``ensure_declarations`` (write-when-different) and
``inspect_declarations`` (read-only). Task 4.2 owns wiring the refresh into
``sync``/``regen``; this module tests the standalone unit only.

Prose-content assertions live in ``tests/test_declaration_goldens.py`` as
committed byte-goldens, not here. Three review rounds proved substring
assertions are not a viable verification strategy for generated prose: a text
asserting the opposite of the truth on every load-bearing claim passed 40/40
of them. This module keeps only *structural* assertions -- the generated-file
marker, frontmatter absence, URL form, region-id presence, determinism, the
no-quantify-over-documents guard, and every placement/state behavior.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.declaration import (
    DECLARATION_FILENAME,
    DeclarationOutcome,
    DeclarationState,
    declaration_path,
    declaration_text,
    ensure_declarations,
    inspect_declarations,
)
from fitdocs.layout import (
    ARCHIVE_DIR,
    CACHE_DIR,
    DECLARED_DIRS,
    TOOL_STATE_DIR,
    WORKOUTS_DIR,
)

_WORKOUTS = f"{WORKOUTS_DIR}/"
_ARCHIVE = f"{ARCHIVE_DIR}/"


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    """Bytes and mtime (nanoseconds) of every file under ``root``."""
    state: dict[str, tuple[bytes, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            state[path.relative_to(root).as_posix()] = (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
    return state


def _age(path: Path) -> None:
    """Set ``path``'s mtime to a distinctly old value so a later comparison is
    never flaky on filesystem timestamp granularity."""
    old = time.time() - 3600
    os.utime(path, (old, old))


# --- declaration_text: pure, deterministic -----------------------------------


def test_declaration_text_is_deterministic() -> None:
    assert declaration_text(_WORKOUTS) == declaration_text(_WORKOUTS)
    assert declaration_text(_ARCHIVE) == declaration_text(_ARCHIVE)


def test_declaration_text_differs_between_directories() -> None:
    assert declaration_text(_WORKOUTS) != declaration_text(_ARCHIVE)


def test_declaration_text_begins_with_the_generated_prefix() -> None:
    for directory in DECLARED_DIRS:
        assert declaration_text(directory).startswith(contract.GENERATED_PREFIX)


def test_declaration_text_states_the_contract_version_and_owner() -> None:
    for directory in DECLARED_DIRS:
        text = declaration_text(directory)
        assert contract.CONTRACT_VERSION in text
        assert contract.GENERATOR in text


def test_workouts_declaration_names_every_user_owned_key() -> None:
    # `contract.EFFORT_KEYS` is the ordered tuple the fragment is built from
    # (task 4.1) -- every key must appear backticked in the workouts text, so
    # adding an effort key cannot silently go unmentioned here either.
    text = declaration_text(_WORKOUTS)
    for key in contract.EFFORT_KEYS:
        assert f"`{key}`" in text


def test_archive_declaration_names_no_user_owned_key() -> None:
    # Req 6.4: the source-archive declaration is unchanged apart from the
    # restated version -- it must gain none of the user-owned keys.
    text = declaration_text(_ARCHIVE)
    for key in contract.EFFORT_KEYS:
        assert f"`{key}`" not in text


def test_workouts_declaration_names_every_user_owned_region() -> None:
    # Region cardinality is never hardcoded prose: every user-owned region id
    # `contract` declares must actually appear in the docs-holding directory's
    # text, so adding a region to the contract cannot silently go unmentioned.
    # Per Req 3.2a this element does NOT apply to the source archive -- it has
    # no user-owned regions of its own -- so this is scoped to `workouts/`
    # only, not asserted over every declared directory.
    text = declaration_text(_WORKOUTS)
    for region in contract.USER_REGIONS:
        assert f"`{region}`" in text


# --- no distributive universals over documents (fix plan step 3) ------------

# Words that would make a declaration sentence a false per-document claim:
# only `render_strength` emits WORKOUT_REGION, so 8 of the 9 golden documents
# carry `notes` + `load` alone. This is the exact false-claim shape that sank
# review rounds 2 and 3 -- a real, mechanical guard over every declared
# directory, not a one-off pin on a single sentence.
#
# Originally this guard only examined lines containing "region", on the theory
# that a document-distributive claim only mattered next to a region mention.
# Task 4.1 added `_USER_KEYS`, a sentence naming the four user-owned
# frontmatter keys with no region word in it, and the guard never looked at
# it -- only the byte-golden would have noticed a quantifier landing there
# (queue: 2026-09-11-declaration-quantifier-guard-only-sees-region-lines). The
# hazard this guard exists for -- a sentence claiming something is true of
# *every* document -- is not specific to region prose, so the predicate now
# inspects every line of the emitted text (including `fit-archive/`'s, which
# the region-only filter never inspected at all). Widening it was checked
# against the two current declaration texts line by line and trips no
# existing sentence: neither text contains any of `_QUANTIFIER_WORDS`
# anywhere, region line or not.
_QUANTIFIER_WORDS = ("each", "every", "all documents", "any document")


def _quantifier_hits(text: str) -> list[str]:
    """Every line in ``text`` containing one of `_QUANTIFIER_WORDS`, described
    as ``"<word> in line <line>"``.

    Factored out of the guard test below so the predicate itself -- not just
    its behavior against the two live declaration texts -- can be pinned
    directly against a synthetic string
    (:func:`test_quantifier_hits_flags_a_synthetic_document_quantifying_sentence`).
    """
    hits: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        for word in _QUANTIFIER_WORDS:
            if word in lowered:
                hits.append(f"{word!r} in line {line!r}")
    return hits


def test_quantifier_hits_flags_a_synthetic_document_quantifying_sentence() -> None:
    # Synthetic corpus, not the real declaration text: pins `_quantifier_hits`
    # itself, independent of whatever the two shipped declarations currently
    # say. None of these lines mentions "region", so this also pins that the
    # predicate is no longer scoped to region-adjacent lines. Every quantifier
    # sits mid-line, never at line start -- a corpus with the quantifier
    # leading its line (e.g. "Every document...") is satisfied identically by
    # `word in lowered` and by `lowered.startswith(word)`, so it cannot tell a
    # substring predicate apart from a prefix one; mid-line placement can.
    # One entry is capitalised for the same reason in the other direction:
    # an all-lowercase corpus is matched identically with and without the
    # predicate's `.lower()`, so deleting that call would stay green.
    text = (
        "The policy applies to each document in turn.\n"
        "The rest of the block is rebuilt, in every document.\n"
        "This clause covers All Documents without exception.\n"
        "Nothing here is exempt: any document counts.\n"
        "This line names no quantifier at all.\n"
    )
    hits = _quantifier_hits(text)
    # Every hit string has the fixed shape `f"{word!r} in line {line!r}"`
    # (see `_quantifier_hits`); slicing off the repr quotes recovers the word.
    found_words = {hit.split(" in line ", 1)[0][1:-1] for hit in hits}
    # A literal expected set, NOT `set(_QUANTIFIER_WORDS)`: comparing against
    # the constant under test would be self-referential -- deleting an entry
    # from `_QUANTIFIER_WORDS` would shrink both sides identically and this
    # assertion would still pass.
    assert found_words == {"each", "every", "all documents", "any document"}, hits
    assert not any("no quantifier at all" in hit for hit in hits), hits


@pytest.mark.parametrize("directory", DECLARED_DIRS)
def test_no_declaration_quantifies_over_documents(directory: str) -> None:
    text = declaration_text(directory)
    lines = text.splitlines()
    assert lines, (
        f"{directory!r} declaration text is empty -- the guard is not "
        "looking at real content"
    )
    hits = _quantifier_hits(text)
    assert not hits, f"{directory!r} declaration quantifies over documents: {hits}"


# --- portability and invisibility to document scans --------------------------


def test_declaration_text_is_plain_markdown_with_no_frontmatter() -> None:
    for directory in DECLARED_DIRS:
        text = declaration_text(directory)
        assert contract.parse_frontmatter(text) is None
        assert not contract.is_workout_document(contract.parse_frontmatter(text))


def test_contract_documentation_pointer_is_a_url_not_a_repo_relative_path() -> None:
    # Pinned independently of the constant's own value. The subtraction check
    # below derives its expectation FROM the constant, so it passes vacuously if
    # the constant itself becomes a repo-relative path -- which is exactly the
    # form design.md forbids: this text lands in a user's tree, which has no
    # repository layout, and ships in an sdist whose file list excludes docs/.
    from fitdocs.declaration import CONTRACT_DOCUMENTATION_URL

    assert CONTRACT_DOCUMENTATION_URL.startswith("https://")
    assert not CONTRACT_DOCUMENTATION_URL.startswith("docs/")


def test_declaration_text_contains_no_repo_relative_documentation_path() -> None:
    from fitdocs.declaration import CONTRACT_DOCUMENTATION_URL

    for directory in DECLARED_DIRS:
        text = declaration_text(directory)
        # The published-contract path may appear only as part of the full URL,
        # never as a bare repo-relative path a reader could mistake for a
        # resolvable local reference.
        assert CONTRACT_DOCUMENTATION_URL in text
        without_url = text.replace(CONTRACT_DOCUMENTATION_URL, "")
        assert "docs/ownership-contract.md" not in without_url


def test_declaration_text_is_recognized_as_generated() -> None:
    for directory in DECLARED_DIRS:
        assert contract.is_generated(declaration_text(directory))


# --- declaration_path ---------------------------------------------------------


def test_declaration_path_places_the_conventional_filename_in_the_directory(
    tmp_path: Path,
) -> None:
    path = declaration_path(tmp_path, _WORKOUTS)
    assert path == tmp_path / WORKOUTS_DIR / DECLARATION_FILENAME


# --- ensure_declarations: placement rules ------------------------------------


def test_ensure_declarations_creates_when_absent(tmp_path: Path) -> None:
    outcomes = ensure_declarations(tmp_path)

    assert len(outcomes) == len(DECLARED_DIRS)
    for directory, outcome in zip(DECLARED_DIRS, outcomes, strict=True):
        assert outcome == DeclarationOutcome(
            directory=directory,
            path=f"{directory}{DECLARATION_FILENAME}",
            state=DeclarationState.WRITTEN,
        )
        path = declaration_path(tmp_path, directory)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == declaration_text(directory)


def test_ensure_declarations_leaves_a_current_file_untouched(tmp_path: Path) -> None:
    ensure_declarations(tmp_path)
    before = _snapshot(tmp_path)
    for directory in DECLARED_DIRS:
        _age(declaration_path(tmp_path, directory))
    aged = _snapshot(tmp_path)
    assert aged != before  # mtimes really did change after aging

    outcomes = ensure_declarations(tmp_path)

    after = _snapshot(tmp_path)
    assert after == aged  # bytes AND mtimes: completely untouched
    assert all(outcome.state == DeclarationState.CURRENT for outcome in outcomes)


def test_ensure_declarations_refreshes_a_stale_file(tmp_path: Path) -> None:
    ensure_declarations(tmp_path)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    stale_text = contract.GENERATED_PREFIX + ": stale content -->\nold\n"
    workouts_path.write_text(stale_text, encoding="utf-8")
    _age(workouts_path)
    aged_mtime = workouts_path.stat().st_mtime_ns

    outcomes = ensure_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.WRITTEN
    assert workouts_path.read_text(encoding="utf-8") == declaration_text(_WORKOUTS)
    assert workouts_path.stat().st_mtime_ns != aged_mtime


def test_ensure_declarations_preserves_a_foreign_file(tmp_path: Path) -> None:
    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    foreign_path = declaration_path(tmp_path, _WORKOUTS)
    foreign_text = "# My own AGENTS.md\n\nHands off.\n"
    foreign_path.write_text(foreign_text, encoding="utf-8")
    _age(foreign_path)
    before = _snapshot(tmp_path)

    outcomes = ensure_declarations(tmp_path)

    after = _snapshot(tmp_path)
    # The foreign path's bytes and mtime are exactly what they were.
    key = foreign_path.relative_to(tmp_path).as_posix()
    assert after[key] == before[key]
    assert foreign_path.read_text(encoding="utf-8") == foreign_text

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    # The archive directory is untouched by the workouts directory's foreign file.
    archive_outcome = next(o for o in outcomes if o.directory == _ARCHIVE)
    assert archive_outcome.state == DeclarationState.WRITTEN


def test_ensure_declarations_never_writes_at_the_data_root(tmp_path: Path) -> None:
    ensure_declarations(tmp_path)
    assert not (tmp_path / DECLARATION_FILENAME).exists()


def test_ensure_declarations_never_writes_in_cache_or_tool_state_dirs(
    tmp_path: Path,
) -> None:
    ensure_declarations(tmp_path)
    # `layout.CACHE_DIR`/`layout.TOOL_STATE_DIR`, not hardcoded literals, so
    # renaming either constant cannot make this assertion vacuously pass.
    assert not (tmp_path / CACHE_DIR).exists()
    assert not (tmp_path / TOOL_STATE_DIR).exists()


# --- inspect_declarations: read-only ------------------------------------------


def test_inspect_declarations_reports_missing_on_a_fresh_data_root(
    tmp_path: Path,
) -> None:
    outcomes = inspect_declarations(tmp_path)

    assert len(outcomes) == len(DECLARED_DIRS)
    for outcome in outcomes:
        assert outcome.state == DeclarationState.MISSING


def test_inspect_declarations_writes_nothing(tmp_path: Path) -> None:
    # Before: an entirely empty data root -- no directories at all.
    before = sorted(p for p in tmp_path.rglob("*"))
    assert before == []

    inspect_declarations(tmp_path)

    after = sorted(p for p in tmp_path.rglob("*"))
    assert after == []


def test_inspect_declarations_reports_current_stale_and_foreign(
    tmp_path: Path,
) -> None:
    ensure_declarations(tmp_path)

    # workouts/: make it stale.
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.write_text(
        contract.GENERATED_PREFIX + ": stale -->\nold\n", encoding="utf-8"
    )

    # fit-archive/: make it foreign.
    archive_path = declaration_path(tmp_path, _ARCHIVE)
    archive_path.write_text("# hands off\n", encoding="utf-8")

    outcomes = {o.directory: o.state for o in inspect_declarations(tmp_path)}

    assert outcomes[_WORKOUTS] == DeclarationState.STALE
    assert outcomes[_ARCHIVE] == DeclarationState.FOREIGN


def test_inspect_declarations_reports_current_when_matching(tmp_path: Path) -> None:
    ensure_declarations(tmp_path)

    outcomes = inspect_declarations(tmp_path)

    assert all(outcome.state == DeclarationState.CURRENT for outcome in outcomes)


def test_inspect_declarations_leaves_a_populated_tree_completely_unchanged(
    tmp_path: Path,
) -> None:
    # A stronger no-mutation proof than an empty root: populate the tree for
    # real, age every file, and assert bytes AND mtimes are untouched across
    # an inspect_declarations call.
    ensure_declarations(tmp_path)
    for directory in DECLARED_DIRS:
        _age(declaration_path(tmp_path, directory))
    before = _snapshot(tmp_path)

    inspect_declarations(tmp_path)

    after = _snapshot(tmp_path)
    assert after == before


# --- symlinks and hostile occupants: degrade to FOREIGN, never write through -


def _escape_target(tmp_path: Path) -> Path:
    """A path clearly outside the data root that a malicious symlink might
    point at."""
    return tmp_path.parent / "ESCAPED_TARGET.md"


def test_ensure_declarations_treats_a_dangling_symlink_as_foreign(
    tmp_path: Path,
) -> None:
    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    escape_target = _escape_target(tmp_path)
    assert not escape_target.exists()
    workouts_path.symlink_to(escape_target)

    outcomes = ensure_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    # Nothing was ever created outside the data root through the symlink.
    assert not escape_target.exists()
    # The symlink itself is untouched -- still a symlink, still dangling.
    assert workouts_path.is_symlink()
    assert not workouts_path.exists()


def test_inspect_declarations_treats_a_dangling_symlink_as_foreign(
    tmp_path: Path,
) -> None:
    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    escape_target = _escape_target(tmp_path)
    workouts_path.symlink_to(escape_target)

    outcomes = inspect_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    assert not escape_target.exists()


def test_ensure_declarations_treats_a_directory_at_the_declaration_path_as_foreign(
    tmp_path: Path,
) -> None:
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.mkdir(parents=True)  # a directory sits where the file belongs

    outcomes = ensure_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    assert workouts_path.is_dir()


def test_inspect_declarations_treats_a_directory_at_the_declaration_path_as_foreign(
    tmp_path: Path,
) -> None:
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.mkdir(parents=True)

    outcomes = inspect_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    assert workouts_path.is_dir()


def test_ensure_declarations_treats_an_unreadable_file_as_foreign(
    tmp_path: Path,
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.write_text("# hands off\n", encoding="utf-8")
    workouts_path.chmod(0o000)
    try:
        outcomes = ensure_declarations(tmp_path)
    finally:
        workouts_path.chmod(0o644)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN


def test_inspect_declarations_treats_an_unreadable_file_as_foreign(
    tmp_path: Path,
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("permission bits are not enforced when running as root")

    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.write_text("# hands off\n", encoding="utf-8")
    workouts_path.chmod(0o000)
    try:
        outcomes = inspect_declarations(tmp_path)
    finally:
        workouts_path.chmod(0o644)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN


def test_ensure_declarations_treats_non_utf8_bytes_as_foreign(tmp_path: Path) -> None:
    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.write_bytes(b"\xff\xfe\x00 not utf-8 at all")

    outcomes = ensure_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    assert workouts_path.read_bytes() == b"\xff\xfe\x00 not utf-8 at all"


def test_inspect_declarations_treats_non_utf8_bytes_as_foreign(tmp_path: Path) -> None:
    (tmp_path / WORKOUTS_DIR).mkdir(parents=True)
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True)
    workouts_path = declaration_path(tmp_path, _WORKOUTS)
    workouts_path.write_bytes(b"\xff\xfe\x00 not utf-8 at all")

    outcomes = inspect_declarations(tmp_path)

    outcome = next(o for o in outcomes if o.directory == _WORKOUTS)
    assert outcome.state == DeclarationState.FOREIGN
    assert workouts_path.read_bytes() == b"\xff\xfe\x00 not utf-8 at all"
