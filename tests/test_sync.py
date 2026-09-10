"""Tests for the sync engine's document lookup (design: SyncEngine, ``sync.py``).

This module locks the activity-identity resolution the per-file pipeline uses to
decide whether a ``.fit`` file updates an existing document or seeds a fresh one
(Req 3.6). ``find_document`` scans ``<data-root>/workouts/*.md`` frontmatter and
matches by session ``uuid`` first, then by ``sources`` membership -- a
content-based match that survives user renames and timezone changes because it
never looks at the document's filename.

The lookup is exercised over temporary document trees built with realistic,
frontmatter-carrying ``.md`` files (mirroring the emission of
:mod:`fitdocs.render.frontmatter`). It is read-only: no case may write, move, or
delete anything under the data root.

The second half of this module exercises the end-to-end per-file pipeline
(:func:`~fitdocs.sync.sync`) over synthetic ``.fit`` fixtures in temporary data
roots: full-run discovery, case-insensitive/recursive walking, corrupt-file
isolation, sha256 dedup, collision disambiguation, re-export convergence with
region preservation, skip idempotency (a byte-identical tree on re-run),
source-directory immutability, force semantics, and region-conflict failures.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest
import yaml

from fitdocs import Modality, compute_metrics, parse_fit
from fitdocs.audit import FindingKind, audit
from fitdocs.contract import DOC_VERSION, LOAD_KEYS
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import (
    begin_marker,
    end_marker,
    extract_regions,
    merge_regions,
)
from fitdocs.layout import (
    ARCHIVE_DIR,
    WORKOUTS_DIR,
    archive_path,
    doc_path,
    source_ref,
)
from fitdocs.render import plan_map
from fitdocs.sync import (
    DocumentMatch,
    DocWarning,
    FileFailure,
    SyncReport,
    find_document,
    regen,
    sync,
)
from fitdocs.tiles import TileUnavailableError
from tests.fixtures import builder

# A canonical session UUID (the shape frontmatter records under ``uuid``).
_UUID = "00010203-0405-0607-0809-0a0b0c0d0e0f"
_OTHER_UUID = "ffffffff-0405-0607-0809-0a0b0c0d0e0f"
# A plain content hash: what ``activity_uid`` degrades to with no session UUID.
_SHA = "a" * 64
_REF = f"fit-archive/{_SHA}.fit"
_OTHER_REF = "fit-archive/" + ("b" * 64) + ".fit"


# --- document tree construction --------------------------------------------


def _workout_md(
    *,
    uuid: str | None = None,
    sources: Sequence[str] = (),
    include_type: bool = True,
    body: str = "\n# Workout\n\nbody text\n",
) -> str:
    """A realistic workout document string, mirroring the frontmatter emitter."""
    data: dict[str, object] = {"title": "Run 2026-07-12 07:30"}
    if include_type:
        data["type"] = "workout"
    data["doc_version"] = 1
    if uuid is not None:
        data["uuid"] = uuid
    data["sport"] = "Run"
    data["modality"] = "run"
    if sources:
        data["sources"] = list(sources)
    dumped = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"---\n{dumped}---\n{body}"


def _write(workouts: Path, name: str, content: str) -> Path:
    workouts.mkdir(parents=True, exist_ok=True)
    path = workouts / name
    path.write_text(content, encoding="utf-8")
    return path


def _workouts(data_root: Path) -> Path:
    return data_root / WORKOUTS_DIR


# --- identity (uuid) match --------------------------------------------------


def test_identity_match_found_even_when_source_ref_absent(tmp_path: Path) -> None:
    # A re-export: same session UUID, DIFFERENT bytes -> its source_ref is NOT
    # yet in the document's sources, but the uuid still converges onto this doc.
    doc = _write(
        _workouts(tmp_path),
        "2026-07-12-run-0730.md",
        _workout_md(uuid=_UUID, sources=[_OTHER_REF]),
    )
    match = find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    assert match == DocumentMatch(path=doc, sources=(_OTHER_REF,))


def test_identity_match_returns_existing_sources_history(tmp_path: Path) -> None:
    history = [_OTHER_REF, _REF]
    doc = _write(
        _workouts(tmp_path),
        "2026-07-12-run-0730.md",
        _workout_md(uuid=_UUID, sources=history),
    )
    match = find_document(tmp_path, activity_uid=_UUID, source_ref="fit-archive/x.fit")
    assert match is not None
    assert match.path == doc
    # Append-ordered history preserved verbatim (last entry = current).
    assert match.sources == tuple(history)


# --- source-ref match -------------------------------------------------------


def test_source_ref_match_when_no_uuid(tmp_path: Path) -> None:
    # A doc without a recorded session UUID is matched by an exact archive ref;
    # the incoming identity is a plain sha256 (no session UUID recorded).
    doc = _write(
        _workouts(tmp_path),
        "2026-07-12-run-0730.md",
        _workout_md(uuid=None, sources=[_REF]),
    )
    match = find_document(tmp_path, activity_uid=_SHA, source_ref=_REF)
    assert match == DocumentMatch(path=doc, sources=(_REF,))


def test_source_ref_match_finds_ref_anywhere_in_history(tmp_path: Path) -> None:
    doc = _write(
        _workouts(tmp_path),
        "2026-07-12-run-0730.md",
        _workout_md(uuid=None, sources=[_REF, _OTHER_REF]),
    )
    # The searched ref is the FIRST (older) entry, not the current one.
    match = find_document(tmp_path, activity_uid=_SHA, source_ref=_REF)
    assert match is not None
    assert match.path == doc
    assert match.sources == (_REF, _OTHER_REF)


# --- precedence: uuid over sources ------------------------------------------


def test_uuid_match_wins_over_sources_match(tmp_path: Path) -> None:
    workouts = _workouts(tmp_path)
    # The sources-matching doc sorts FIRST (scanned first); the uuid-matching doc
    # sorts LAST -- proving precedence is by match kind, not scan order.
    _write(workouts, "aaa-sources.md", _workout_md(uuid=None, sources=[_REF]))
    uuid_doc = _write(
        workouts, "zzz-uuid.md", _workout_md(uuid=_UUID, sources=[_OTHER_REF])
    )
    match = find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    assert match is not None
    assert match.path == uuid_doc
    assert match.sources == (_OTHER_REF,)


# --- rename / timezone survival (content-based match) -----------------------


def test_rename_survival_by_uuid(tmp_path: Path) -> None:
    # The user renamed the document to something arbitrary; the uuid match is
    # content-based, so the doc is still found.
    doc = _write(_workouts(tmp_path), "my-cool-run.md", _workout_md(uuid=_UUID))
    match = find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    assert match is not None
    assert match.path == doc


def test_rename_survival_by_sources(tmp_path: Path) -> None:
    doc = _write(
        _workouts(tmp_path), "leg-day-notes.md", _workout_md(uuid=None, sources=[_REF])
    )
    match = find_document(tmp_path, activity_uid=_SHA, source_ref=_REF)
    assert match is not None
    assert match.path == doc


def test_timezone_change_resolves_to_same_document(tmp_path: Path) -> None:
    # A doc named from one local date is still found by uuid regardless of the
    # filename -- a timezone change that would rename the doc never forks it.
    doc = _write(_workouts(tmp_path), "2026-07-11-run-2330.md", _workout_md(uuid=_UUID))
    match = find_document(tmp_path, activity_uid=_UUID, source_ref="fit-archive/z.fit")
    assert match is not None
    assert match.path == doc


# --- no match ---------------------------------------------------------------


def test_no_match_returns_none(tmp_path: Path) -> None:
    _write(
        _workouts(tmp_path),
        "2026-07-12-run-0730.md",
        _workout_md(uuid=_OTHER_UUID, sources=[_OTHER_REF]),
    )
    assert find_document(tmp_path, activity_uid=_UUID, source_ref=_REF) is None


def test_missing_workouts_dir_returns_none(tmp_path: Path) -> None:
    # No workouts/ directory has been created yet: no docs, no match, no error.
    assert find_document(tmp_path, activity_uid=_UUID, source_ref=_REF) is None


def test_only_non_fitdocs_md_returns_none(tmp_path: Path) -> None:
    workouts = _workouts(tmp_path)
    # A non-fitdocs page: valid YAML frontmatter, but not type: workout, and it
    # even carries a uuid/sources that happen to collide -- must be ignored.
    _write(
        workouts,
        "some-note.md",
        _workout_md(uuid=_UUID, sources=[_REF], include_type=False),
    )
    _write(
        workouts,
        "typed-note.md",
        "---\ntitle: A Note\ntype: note\nuuid: " + _UUID + "\n---\n\n# A Note\n",
    )
    assert find_document(tmp_path, activity_uid=_UUID, source_ref=_REF) is None


# --- garbled / stray files skipped safely -----------------------------------


def test_garbled_md_skipped_without_raising(tmp_path: Path) -> None:
    workouts = _workouts(tmp_path)
    # A stray markdown file with no frontmatter at all.
    _write(workouts, "stray.md", "# Just a heading\n\nno frontmatter here\n")
    # An unterminated frontmatter fence (opening ---, never closed).
    _write(workouts, "unterminated.md", "---\ntitle: broken\n\nbody with no fence\n")
    # Frontmatter that is not a mapping (a YAML list).
    _write(workouts, "listy.md", "---\n- a\n- b\n---\n\nbody\n")
    # The real matching doc lives alongside the garbage.
    doc = _write(workouts, "2026-07-12-run-0730.md", _workout_md(uuid=_UUID))
    match = find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    assert match is not None
    assert match.path == doc


def test_malformed_yaml_frontmatter_skipped(tmp_path: Path) -> None:
    workouts = _workouts(tmp_path)
    # Frontmatter whose YAML cannot parse -- must be skipped, never raised.
    _write(workouts, "bad-yaml.md", "---\ntitle: : : :\n\tfoo: [unclosed\n---\nbody\n")
    doc = _write(workouts, "good.md", _workout_md(uuid=_UUID))
    match = find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    assert match is not None
    assert match.path == doc


# --- read-only guarantee ----------------------------------------------------


def test_lookup_is_read_only(tmp_path: Path) -> None:
    workouts = _workouts(tmp_path)
    _write(workouts, "a.md", _workout_md(uuid=_UUID))
    _write(workouts, "b.md", _workout_md(uuid=None, sources=[_OTHER_REF]))
    before = {p: p.stat().st_mtime_ns for p in workouts.iterdir()}

    find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    find_document(tmp_path, activity_uid=_SHA, source_ref="fit-archive/none.fit")

    after = {p: p.stat().st_mtime_ns for p in workouts.iterdir()}
    # No files added, removed, or rewritten.
    assert before == after


# --- deterministic scan order -----------------------------------------------


def test_sources_absent_key_yields_empty_tuple(tmp_path: Path) -> None:
    doc = _write(_workouts(tmp_path), "no-sources.md", _workout_md(uuid=_UUID))
    match = find_document(tmp_path, activity_uid=_UUID, source_ref=_REF)
    assert match == DocumentMatch(path=doc, sources=())


# ===========================================================================
# Per-file sync pipeline (task 4.2)
# ===========================================================================

# A fixed non-UTC zone: determinism with user-correct local dates in names.
_TZ = timezone(timedelta(hours=-6))

# The stable stems every fixture resolves to under ``_TZ`` (start time
# 2021-09-07 19:46 local); collisions and re-exports are asserted against them.
_RUN_STEM = "2021-09-07-run-1946"
_RIDE_STEM = "2021-09-07-ride-1946"
_STRENGTH_STEM = "2021-09-07-strength-1946"
_MINIMAL_STEM = "2021-09-07-workout-1946"
# The canonical session UUID both re-export fixtures record (task 1.6 builder).
_REEXPORT_UUID = "64656667-6869-6a6b-6c6d-6e6f70717273"


class _ServingTiles:
    """The always-supplied basemap-tile source for pipeline tests (task 6.1).

    ``tiles`` is now a required engine argument, so every ``sync``/``regen`` call
    injects one. This minimal source serves deterministic PNG bytes for any ref:
    a GPS-bearing fixture (``run``/``reexport``) therefore now renders a ``## Map``
    section and a ``<stem>-map.svg`` asset, while a no-GPS or strength fixture
    plans no route and never consults it (the source stays inert). Stateless, so
    one shared instance is safe across calls.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


#: One shared, stateless serving source for the non-map pipeline/regen tests.
_TILES: _ServingTiles = _ServingTiles()


def _put(source_dir: Path, relname: str, data: bytes) -> Path:
    """Write fixture bytes to a (possibly nested) file under the source dir."""
    path = source_dir / relname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _tree(root: Path) -> dict[str, bytes]:
    """A ``{relative-posix-path: bytes}`` snapshot of every file under ``root``."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _frontmatter(doc: Path) -> dict[str, object]:
    """Parse a written document's leading YAML frontmatter block."""
    block = doc.read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    return parsed


def _md_names(data_root: Path) -> list[str]:
    """Sorted names of every ``.md`` document under ``workouts/``.

    Excludes the in-tree ownership declaration (``AGENTS.md``, task 4.2, Req
    3.7): it is a real file placed by ``sync``/``regen`` and its name happens
    to end in ``.md``, but it is not a workout document.
    """
    return sorted(
        p.name
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    )


def _asset_names(data_root: Path) -> list[str]:
    """Sorted names of every ``.svg`` asset under ``workouts/assets/``."""
    return sorted(p.name for p in (data_root / WORKOUTS_DIR / "assets").glob("*.svg"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _set_region(text: str, region_id: str, content: str) -> str:
    """Replace a preserved region's inner content in a document string."""
    begin, end = begin_marker(region_id), end_marker(region_id)
    start = text.index(begin)
    finish = text.index(end) + len(end)
    return text[:start] + f"{begin}\n{content}\n{end}" + text[finish:]


def _add_frontmatter_key(text: str, line: str) -> str:
    """Insert an extra frontmatter line just before the closing ``---`` fence."""
    first_idx = text.index("---\n")
    second_idx = text.index("---\n", first_idx + len("---\n"))
    return text[:second_idx] + line + "\n" + text[second_idx:]


def _set_doc_version_line(text: str, replacement: str) -> str:
    """Replace the ``doc_version: N`` frontmatter line with an arbitrary line.

    ``replacement`` is the literal YAML line (e.g. ``"doc_version: 999"`` or
    ``"doc_version: not-a-number"``); an empty string removes the line
    entirely, simulating a document with no recorded version.
    """
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        if line.lstrip().startswith("doc_version:"):
            if replacement:
                out.append(replacement + "\n")
            continue
        out.append(line)
    return "".join(out)


# --- full run: one doc + assets + archive per activity (1.1, 1.2, 2.8, 3.1) --


def test_full_run_writes_doc_assets_and_archive_per_activity(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixtures = {
        "run.fit": builder.run_fit_bytes(),
        "ride.fit": builder.ride_fit_bytes(),
        "strength.fit": builder.strength_no_sets_fit_bytes(),
        "minimal.fit": builder.minimal_fit_bytes(),
    }
    for name, data in fixtures.items():
        _put(source, name, data)

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert isinstance(report, SyncReport)
    assert report.skipped == ()
    assert report.failures == ()
    assert len(report.written) == 4

    # One document per activity (deterministic, sport-aware names).
    assert _md_names(data_root) == [
        f"{_RIDE_STEM}.md",
        f"{_RUN_STEM}.md",
        f"{_STRENGTH_STEM}.md",
        f"{_MINIMAL_STEM}.md",
    ]
    # Its hero chart asset alongside each; the GPS-bearing run also gets a route
    # map asset now that tiles are always supplied (the no-GPS ride, the strength
    # session, and the session-less minimal fixture plan no route, Req 1.3, 1.4).
    assert _asset_names(data_root) == [
        f"{_RIDE_STEM}-hero.svg",
        f"{_RUN_STEM}-hero.svg",
        f"{_RUN_STEM}-map.svg",
        f"{_STRENGTH_STEM}-hero.svg",
        f"{_MINIMAL_STEM}-hero.svg",
    ]
    # The archive is populated for every source, keyed by content hash (3.1).
    for data in fixtures.values():
        assert archive_path(data_root, _sha(data)).is_file()
    assert len(list((data_root / ARCHIVE_DIR).glob("*.fit"))) == 4


# --- recursive + case-insensitive discovery (1.1) ---------------------------


def test_discovery_is_recursive_and_case_insensitive(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    # A ``.FIT`` (uppercase) file nested two directories deep must be found.
    _put(source, "exports/2021/WORKOUT.FIT", builder.run_fit_bytes())

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert len(report.written) == 1
    assert doc_path(data_root, _RUN_STEM).is_file()


# --- corrupt-file isolation: batch never aborts (1.3) -----------------------


def test_corrupt_files_fail_without_aborting_the_batch(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "bad-not-fit.fit", builder.non_fit_bytes())
    _put(source, "bad-truncated.fit", builder.truncated_fit_bytes())
    good = builder.run_fit_bytes()
    _put(source, "good.fit", good)

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # Each corrupt file is a failure that names it, with a non-empty reason.
    assert len(report.failures) == 2
    assert all(isinstance(f, FileFailure) and f.reason for f in report.failures)
    failed = {f.source for f in report.failures}
    assert any("bad-not-fit.fit" in s for s in failed)
    assert any("bad-truncated.fit" in s for s in failed)
    # The healthy file still produced its document, asset, and archive.
    assert len(report.written) == 1
    assert doc_path(data_root, _RUN_STEM).is_file()
    assert archive_path(data_root, _sha(good)).is_file()
    # A file that failed decoding was never archived (self-healing next run).
    assert not archive_path(data_root, _sha(builder.non_fit_bytes())).exists()


# --- dedup: identical bytes -> one doc, one archive (3.3) --------------------


def test_identical_bytes_dedup_to_one_document_and_archive(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    # Two differently named files with byte-identical content.
    _put(source, "a-first.fit", data)
    _put(source, "b-second.fit", data)

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # The first (sorted) file is written; the second is skipped as a duplicate.
    assert len(report.written) == 1
    assert len(report.skipped) == 1
    assert any("b-second.fit" in s for s in report.skipped)
    # Exactly one document and one archive despite two source files.
    assert _md_names(data_root) == [f"{_RUN_STEM}.md"]
    assert len(list((data_root / ARCHIVE_DIR).glob("*.fit"))) == 1


# --- collision disambiguation: never overwrite a different activity (2.6) ----


def test_name_collision_between_activities_disambiguates(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    # Two DIFFERENT activities that resolve to the same base stem (same start
    # time): a plain run (sha identity) and a re-export (session-UUID identity).
    _put(source, "1-run.fit", builder.run_fit_bytes())
    _put(source, "2-reexport.fit", builder.reexport_a_fit_bytes())

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert len(report.written) == 2
    # Two distinct documents; the second is suffixed with its identity, so the
    # first activity's document is never overwritten.
    assert _md_names(data_root) == sorted(
        [f"{_RUN_STEM}.md", f"{_RUN_STEM}-{_REEXPORT_UUID[:8]}.md"]
    )


# --- re-export convergence with region preservation (3.6, 10.2) -------------


def test_reexport_converges_on_one_document_preserving_regions(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    ref_a = source_ref(_sha(a))
    ref_b = source_ref(_sha(b))
    doc = doc_path(data_root, _RUN_STEM)

    # First export (file A).
    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert doc.is_file()
    assert _frontmatter(doc)["sources"] == [ref_a]

    # The user hand-writes into the preserved ``notes`` region.
    text = doc.read_text(encoding="utf-8")
    begin, end = begin_marker("notes"), end_marker("notes")
    start, finish = text.index(begin), text.index(end) + len(end)
    note = "MY HAND-WRITTEN NOTE"
    doc.write_text(text[:start] + f"{begin}\n{note}\n{end}" + text[finish:], "utf-8")

    # Re-export (file B): SAME session UUID, DIFFERENT bytes.
    _put(tmp_path / "src_b", "b.fit", b)
    report = sync(tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # Still exactly one document, updated in place (not duplicated).
    assert len(report.written) == 1
    assert _md_names(data_root) == [f"{_RUN_STEM}.md"]
    # Both archives kept; the new source ref is appended last (last = current).
    assert archive_path(data_root, _sha(a)).is_file()
    assert archive_path(data_root, _sha(b)).is_file()
    assert _frontmatter(doc)["sources"] == [ref_a, ref_b]
    # The hand-written note survived the regeneration verbatim.
    assert extract_regions(doc.read_text(encoding="utf-8"))["notes"] == note


# --- skip idempotency: second run writes nothing (3.2, 4.2) -----------------


def test_second_sync_skips_all_and_leaves_tree_identical(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())

    first = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert len(first.written) == 2
    assert first.skipped == ()
    tree_after_first = _tree(data_root)

    second = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # Everything is already archived -> all skipped, nothing written or failed.
    assert second.written == ()
    assert len(second.skipped) == 2
    assert second.failures == ()
    # The data root is byte-identical: a no-op re-run performs no writes (4.2).
    assert _tree(data_root) == tree_after_first


# --- source directory immutability (1.6) ------------------------------------


def test_source_directory_is_never_modified(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "a/run.fit", builder.run_fit_bytes())
    _put(source, "b/ride.FIT", builder.ride_fit_bytes())
    before = _tree(source)

    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)  # a second run too

    # No source file was added, removed, moved, or rewritten.
    assert _tree(source) == before


# --- force re-processes but never rewrites the archive (3.5, 4.3) -----------


def test_force_reprocesses_without_rewriting_the_archive(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    _put(source, "run.fit", data)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    archive = archive_path(data_root, _sha(data))
    before_mtime = archive.stat().st_mtime_ns
    before_bytes = archive.read_bytes()

    forced = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES, force=True)

    # ``force`` re-processes the already-archived file instead of skipping it.
    assert len(forced.written) == 1
    assert forced.skipped == ()
    # The archived source is immutable: neither rewritten nor changed (3.5).
    assert archive.stat().st_mtime_ns == before_mtime
    assert archive.read_bytes() == before_bytes


# --- region conflict: doc untouched, failure reported, others proceed (10.3) -


def test_region_conflict_reports_failure_and_leaves_the_document_untouched(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    workouts = data_root / WORKOUTS_DIR
    workouts.mkdir(parents=True)

    # Pre-place a document a re-export matches (same session UUID) whose ``notes``
    # region is DAMAGED -- a begin marker with no matching end.
    damaged = (
        "---\n"
        "title: Run 2021-09-07 19:46\n"
        "type: workout\n"
        "doc_version: 1\n"
        f"uuid: {_REEXPORT_UUID}\n"
        "sport: Run\n"
        "modality: run\n"
        "---\n\n"
        f"{begin_marker('notes')}\n"
        "a note whose end marker was deleted\n"
    )
    doc = doc_path(data_root, _RUN_STEM)
    doc.write_text(damaged, encoding="utf-8")

    a = builder.reexport_a_fit_bytes()
    _put(source, "reexport.fit", a)
    _put(source, "ride.fit", builder.ride_fit_bytes())

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # The conflicted file is a failure that names it; the damaged doc is untouched.
    assert any("reexport.fit" in f.source for f in report.failures)
    assert doc.read_text(encoding="utf-8") == damaged
    # A file that hit a region conflict was never archived.
    assert not archive_path(data_root, _sha(a)).exists()
    # The healthy neighbour still went all the way through.
    assert len(report.written) == 1
    assert doc_path(data_root, _RIDE_STEM).is_file()


# ===========================================================================
# Regeneration from the archive alone (task 4.3)
# ===========================================================================


# --- primary observable: all three regions preserved, generated refreshed ----


def test_regen_preserves_all_three_regions_and_refreshes_generated(
    tmp_path: Path,
) -> None:
    # A strength document is the only view carrying all three preserved regions
    # (notes, workout, load); it exercises the full merge contract on regen.
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "strength.fit", builder.strength_fit_bytes())

    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _STRENGTH_STEM)
    assert doc.is_file()
    first_text = doc.read_text(encoding="utf-8")
    assert set(extract_regions(first_text)) >= {"notes", "workout", "load"}

    # The original source directory is deleted: regen must rebuild from the
    # archived .fit alone, never the source dir (Req 4.4).
    shutil.rmtree(source)

    # The user edits ALL THREE regions -- notes, workout, and a hand-filled load
    # region that mimics a computed value -- and corrupts a generated (non-region)
    # tail to prove the generated content is refreshed on regen.
    edited = first_text
    edited = _set_region(edited, "notes", "MY HAND-WRITTEN NOTES")
    edited = _set_region(edited, "workout", "Squat 3x5 @ 100 kg\nBench 3x5 @ 60 kg")
    edited = _set_region(edited, "load", "Load: 42 (hand-filled to mimic a load)")
    edited = edited + "\nCORRUPTED-GENERATED-CONTENT\n"
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert report.skipped == ()
    assert len(report.written) == 1

    final = doc.read_text(encoding="utf-8")
    regions = extract_regions(final)
    # All three region bodies carried over verbatim (Req 4.3, 10.2).
    assert regions["notes"] == "MY HAND-WRITTEN NOTES"
    assert regions["workout"] == "Squat 3x5 @ 100 kg\nBench 3x5 @ 60 kg"
    assert regions["load"] == "Load: 42 (hand-filled to mimic a load)"
    # Generated content refreshed: the corruption is gone and the document equals
    # the canonical fresh render with the edited regions merged back in.
    assert "CORRUPTED-GENERATED-CONTENT" not in final
    assert final == merge_regions(first_text, edited)


def test_regen_cannot_recover_region_content_once_the_document_is_deleted(
    tmp_path: Path,
) -> None:
    """Region content is COPIED from the existing document, never derived.

    The claim anchor for the ownership declaration's re-derivability sentence
    (`fitdocs.declaration._REDERIVABILITY_DOCS`, wiki-contract Req 3.2/3.2a).
    ``merge_regions`` runs only when ``find_document`` matches an existing
    document, so the archive plus the athlete profile, timezone, and tile source
    rebuild the *generated* content alone. Delete the document and regen
    succeeds -- no failure, no warning -- with the user's writing replaced by the
    placeholder. The declaration must therefore never say that documents in
    ``workouts/`` are re-derivable without scoping the claim to generated
    content; an unscoped claim is what licenses an agent to delete and rebuild.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    doc.write_text(
        _set_region(doc.read_text(encoding="utf-8"), "notes", "IRREPLACEABLE"),
        encoding="utf-8",
    )

    # With the document present, the writing survives regeneration.
    assert regen(data_root, athlete=None, tz=_TZ, tiles=_TILES).failures == ()
    assert extract_regions(doc.read_text(encoding="utf-8"))["notes"] == "IRREPLACEABLE"

    # Delete it, and regen "succeeds" while losing the writing for good.
    doc.unlink()
    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert report.warnings == ()
    assert len(report.written) == 1
    assert doc.is_file()
    assert "IRREPLACEABLE" not in doc.read_text(encoding="utf-8")


# --- regen from the data root alone rebuilds every document (Req 4.4) --------


def test_regen_rebuilds_every_document_from_the_data_root_alone(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    tree_after_sync = _tree(data_root)

    # No source directory exists at all when regen runs (Req 4.4).
    shutil.rmtree(source)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    # Every document is re-rendered from its current source.
    assert set(report.written) == {
        f"{WORKOUTS_DIR}/{_RUN_STEM}.md",
        f"{WORKOUTS_DIR}/{_RIDE_STEM}.md",
    }
    # Regenerating unedited documents from the archive reproduces the synced tree
    # byte-for-byte (deterministic; archives are never rewritten).
    assert _tree(data_root) == tree_after_sync


# --- unreferenced archive renders a fresh document (Req 4.4) -----------------


def test_regen_renders_fresh_document_for_unreferenced_archive(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    assert doc.is_file()

    # The user deletes the generated document; its archived source remains --
    # documents are derived artifacts (Req 4.4).
    doc.unlink()

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert report.written == (f"{WORKOUTS_DIR}/{_RUN_STEM}.md",)
    # A fresh document is rebuilt from the orphaned archive, with its regions.
    assert doc.is_file()
    assert set(extract_regions(doc.read_text(encoding="utf-8"))) >= {"notes", "load"}


# --- re-export: regen re-renders from the LAST (current) source (Req 4.3) ----


def test_regen_re_renders_from_last_source_of_a_reexport(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    ref_a = source_ref(_sha(a))
    ref_b = source_ref(_sha(b))
    doc = doc_path(data_root, _RUN_STEM)

    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)
    _put(tmp_path / "src_b", "b.fit", b)
    sync(tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES)
    # One document, its append-ordered history [older, current].
    assert _frontmatter(doc)["sources"] == [ref_a, ref_b]

    # Hand-write into the notes region.
    doc.write_text(
        _set_region(doc.read_text(encoding="utf-8"), "notes", "REEXPORT NOTE"),
        encoding="utf-8",
    )

    # Delete the OLDER archive: regen must read the LAST (current) source, ref_b,
    # so a missing older source cannot break regeneration.
    archive_path(data_root, _sha(a)).unlink()

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert report.written == (f"{WORKOUTS_DIR}/{_RUN_STEM}.md",)
    # Re-rendered from the last source; provenance history and the note intact.
    assert _frontmatter(doc)["sources"] == [ref_a, ref_b]
    assert extract_regions(doc.read_text(encoding="utf-8"))["notes"] == "REEXPORT NOTE"


# --- determinism: regen twice is byte-identical (Req 4.1) --------------------


def test_regen_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "strength.fit", builder.strength_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # Edit a preserved region so the merge path is exercised, not just fresh
    # renders of a pristine document.
    doc = doc_path(data_root, _STRENGTH_STEM)
    doc.write_text(
        _set_region(doc.read_text(encoding="utf-8"), "workout", "5x5 @ 80 kg"),
        encoding="utf-8",
    )

    first = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)
    tree_first = _tree(data_root)
    second = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert first.failures == () and second.failures == ()
    assert len(first.written) == 2
    # The second regeneration is byte-identical to the first (Req 4.1).
    assert _tree(data_root) == tree_first
    # The edited region survives every regeneration verbatim.
    assert extract_regions(doc.read_text(encoding="utf-8"))["workout"] == "5x5 @ 80 kg"


# --- failure isolation: a damaged document is left untouched (Req 10.3) ------


def test_regen_isolates_a_document_with_damaged_markers(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # Damage the run document's load region: delete its end marker (unbalanced).
    run_doc = doc_path(data_root, _RUN_STEM)
    damaged = run_doc.read_text(encoding="utf-8").replace(
        end_marker("load") + "\n", "", 1
    )
    run_doc.write_text(damaged, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # The damaged document is a per-file failure, left byte-for-byte untouched.
    assert len(report.failures) == 1
    assert any(_RUN_STEM in f.source and f.reason for f in report.failures)
    assert run_doc.read_text(encoding="utf-8") == damaged
    # The healthy neighbour still regenerated.
    assert report.written == (f"{WORKOUTS_DIR}/{_RIDE_STEM}.md",)


# --- graceful handling of a document with no resolvable source --------------


def test_regen_reports_failure_for_document_without_a_resolvable_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    workouts = data_root / WORKOUTS_DIR
    workouts.mkdir(parents=True)
    # A workout document whose 'sources' history is empty: there is no archive to
    # regenerate it from. It must fail gracefully without aborting the batch.
    orphan = workouts / "hand-made.md"
    orphan_text = (
        "---\n"
        "title: Orphan\n"
        "type: workout\n"
        "doc_version: 1\n"
        "sport: Run\n"
        "modality: run\n"
        "---\n\n"
        "body\n"
    )
    orphan.write_text(orphan_text, encoding="utf-8")

    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # The sourceless document is a failure naming it and is left untouched; the
    # healthy synced document still regenerates.
    assert any("hand-made.md" in f.source and f.reason for f in report.failures)
    assert orphan.read_text(encoding="utf-8") == orphan_text
    assert f"{WORKOUTS_DIR}/{_RUN_STEM}.md" in report.written


# ===========================================================================
# Warn-and-continue channel on the sync report (task 5.1)
# ===========================================================================
#
# The warnings channel is ADDITIVE and ORTHOGONAL to the written/skipped/
# failures partition: a ``DocWarning`` names an affected document but never
# moves a file out of (or into) a bucket, and never enters ``failures`` (Req
# 4.3, 4.4). Task 5.1 delivers only the channel (the ``DocWarning`` value plus
# the ``SyncReport.warnings`` field); the map orchestration that populates it is
# task 5.2, so ``warnings`` is empty ``()`` on every real run for now.


def test_docwarning_is_a_frozen_dataclass_with_doc_and_detail() -> None:
    warning = DocWarning(
        doc=f"{WORKOUTS_DIR}/{_RUN_STEM}.md",
        detail="map omitted: tiles unavailable (offline)",
    )
    # Two human-readable string fields: the affected doc (4.3) and the reason.
    assert warning.doc == f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert warning.detail == "map omitted: tiles unavailable (offline)"
    assert isinstance(warning.doc, str) and isinstance(warning.detail, str)
    # Frozen: a doc-scoped condition is an immutable value.
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        warning.detail = "changed"  # type: ignore[misc]


def test_sync_report_defaults_warnings_to_empty() -> None:
    # The channel is the last, defaulted field: every existing three-arg
    # construction site stays valid and reports an empty warnings channel.
    report = SyncReport(written=(), skipped=(), failures=())
    assert report.warnings == ()


def test_sync_report_carries_an_empty_warnings_channel(tmp_path: Path) -> None:
    # A run that populates ALL THREE buckets -- a written doc, a byte-identical
    # duplicate (skipped), and a corrupt file (failure) -- to prove the warnings
    # channel rides alongside an undisturbed written/skipped/failures partition.
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    good = builder.run_fit_bytes()
    _put(source, "a-run.fit", good)
    _put(source, "b-run-dup.fit", good)  # identical bytes -> skipped
    _put(source, "c-corrupt.fit", builder.non_fit_bytes())  # -> failure
    discovered = 3

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # The channel exists and is empty (task 5.2 populates it).
    assert report.warnings == ()
    # Every discovered file lands in EXACTLY ONE bucket; warnings add nothing to
    # and remove nothing from that partition.
    assert len(report.written) == 1
    assert len(report.skipped) == 1
    assert len(report.failures) == 1
    assert (
        len(report.written) + len(report.skipped) + len(report.failures) == discovered
    )


def test_regen_report_carries_an_empty_warnings_channel(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    # regen carries the same additive channel: present, empty, partition intact.
    assert report.warnings == ()
    assert len(report.written) == 2
    assert report.skipped == ()
    assert report.failures == ()


def test_warnings_are_additive_and_orthogonal_to_the_buckets() -> None:
    # A directly-constructed report proves the orthogonality contract: a doc can
    # be BOTH counted once in a bucket (here ``written``) AND named by a warning,
    # with the warning living ONLY in ``warnings`` -- never in ``failures`` and
    # never displacing the file from its bucket (Req 4.3, 4.4).
    doc = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    warning = DocWarning(doc=doc, detail="map omitted: tiles unavailable")
    report = SyncReport(
        written=(doc,),
        skipped=(),
        failures=(),
        warnings=(warning,),
    )
    # The doc is counted exactly once, in ``written`` -- a warning never moves it.
    assert report.written == (doc,)
    assert doc not in report.skipped
    # The warning names that same doc but is NOT a failure; it rides alongside.
    assert report.failures == ()
    assert report.warnings == (warning,)
    assert report.warnings[0].doc == doc
    # A ``DocWarning`` is not a ``FileFailure``: the two channels never conflate.
    assert not isinstance(warning, FileFailure)


# ===========================================================================
# Map orchestration in the sync engine (task 5.2)
# ===========================================================================
#
# After stem/match resolution and before ``DocContext`` construction, the engine
# runs a map path -- but ONLY for non-strength modalities, the exact set of views
# that render a ``## Map`` section (so "tiles fetched" == "a map is rendered",
# Req 3.5). It plans from the position channels, resolves the exact tile set
# through the INJECTED ``TileSource``, and injects a complete ``MapData``; a tile
# miss becomes a ``DocWarning`` naming the target document while the doc renders
# WITHOUT a Map section (Req 4.3) and the run still reports success (Req 4.4).
# ``tiles`` is OPTIONAL in this task: absent ⇒ the map path is skipped entirely,
# so every pre-existing (``tiles``-less) call stays valid and offline.

_ATTR = "© OpenStreetMap contributors"


class _RecordingTiles:
    """A ``TileSource`` that serves bytes for every ref and records each resolve.

    Records the exact ref tuples it is asked to resolve, so a test can assert the
    map path DID reach the source (outdoor) or NEVER did (strength, Req 3.5).
    Serving raises nothing: a strength miscall surfaces as a recorded resolve, not
    something the engine could swallow into a ``FileFailure``.
    """

    def __init__(self, attribution: str = _ATTR) -> None:
        self._attribution = attribution
        self.resolved: list[tuple[object, ...]] = []

    @property
    def attribution(self) -> str:
        return self._attribution

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        refs = tuple(refs)
        self.resolved.append(refs)
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


class _UnavailableTiles:
    """A ``TileSource`` whose ``resolve`` always raises ``TileUnavailableError``.

    Models every non-fatal tile miss -- offline, provider error, or the persistent
    opt-out (``enabled = false``) -- via the ``reason`` string the warning detail
    carries (Req 4.3, 5.4).
    """

    def __init__(
        self, reason: str = "offline: no route to host", attribution: str = _ATTR
    ) -> None:
        self._attribution = attribution
        self._reason = reason
        self.resolved: list[tuple[object, ...]] = []

    @property
    def attribution(self) -> str:
        return self._attribution

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        self.resolved.append(tuple(refs))
        raise TileUnavailableError(self._reason)


def _map_asset(data_root: Path, stem: str) -> Path:
    """The document-relative map SVG asset path for ``stem`` (Req 1.4)."""
    return data_root / WORKOUTS_DIR / "assets" / f"{stem}-map.svg"


# --- success: a resolved tile set is injected as a Map section (1.1, 3.5) ----


def test_sync_injects_map_for_outdoor_activity(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    tiles = _RecordingTiles()

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=tiles)

    doc_ref = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert report.written == (doc_ref,)
    assert report.failures == ()
    # No omission: the map resolved, so there is no warning at all.
    assert report.warnings == ()
    # The document carries a Map section and its self-contained SVG asset.
    text = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert "## Map" in text
    assert _map_asset(data_root, _RUN_STEM).is_file()
    # The map path reached the injected source exactly once, for a real tile set.
    assert len(tiles.resolved) == 1
    assert tiles.resolved[0]  # the plan's covering tile set, non-empty


# --- unavailable: omit the Map, warn naming the doc, run succeeds (4.3, 4.4) --


def test_sync_omits_map_with_warning_when_tiles_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_UnavailableTiles())

    doc_ref = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    # The document is WRITTEN (run reports success), never a failure (4.4).
    assert report.written == (doc_ref,)
    assert report.failures == ()
    # It renders WITHOUT a Map section or a map asset (4.3).
    text = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert "## Map" not in text
    assert not _map_asset(data_root, _RUN_STEM).exists()
    # Other sections are intact -- only the map is omitted.
    assert "## Summary" in text
    # Exactly one warning, naming the affected document, with a non-empty reason.
    assert len(report.warnings) == 1
    warning = report.warnings[0]
    assert isinstance(warning, DocWarning)
    assert warning.doc == doc_ref
    assert warning.detail
    assert "no route to host" in warning.detail


# --- opt-out disabled: same omission-with-warning path (5.4) -----------------


def test_sync_disabled_tiles_with_miss_warns_and_omits(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    # A source simulating the persistent opt-out: disabled with a cache miss.
    disabled = _UnavailableTiles(reason="tile requests are disabled")

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=disabled)

    doc_ref = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert report.written == (doc_ref,)
    assert report.failures == ()
    text = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert "## Map" not in text
    assert not _map_asset(data_root, _RUN_STEM).exists()
    assert len(report.warnings) == 1
    assert report.warnings[0].doc == doc_ref
    # The reason surfaces the disabled opt-out.
    assert "disabled" in report.warnings[0].detail.lower()


# --- strength: no tile resolution is ever attempted (3.5) --------------------


def test_sync_never_resolves_tiles_for_strength(tmp_path: Path) -> None:
    # A strength session that DOES carry GPS: this is the only shape that exercises
    # the guard itself. The guard (``modality is not STRENGTH``) -- NOT an absent
    # route -- is what must keep tiles from being resolved. Confirm the fixture has
    # both guard-defeating properties up front, so the test can never be vacuous:
    # parse yields STRENGTH modality AND ``plan_map`` over its positions is non-None
    # (a no-GPS strength file would make the source unconsulted regardless of the
    # guard, silently passing this test even if the guard were deleted).
    strength_gps = builder.strength_with_gps_fit_bytes()
    activity = parse_fit(strength_gps)
    assert activity.modality is Modality.STRENGTH
    assert (
        plan_map(activity.samples.latitude_deg, activity.samples.longitude_deg)
        is not None
    )

    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "strength.fit", strength_gps)
    tiles = _RecordingTiles()

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=tiles)

    doc_ref = f"{WORKOUTS_DIR}/{_STRENGTH_STEM}.md"
    assert report.written == (doc_ref,)
    assert report.warnings == ()
    # The strength view never renders a map, so the source is NEVER consulted --
    # even though the activity carries a resolvable route (guard, not no-GPS).
    assert tiles.resolved == []
    text = doc_path(data_root, _STRENGTH_STEM).read_text(encoding="utf-8")
    assert "## Map" not in text
    assert not _map_asset(data_root, _STRENGTH_STEM).exists()


# --- indoor run (no GPS): clean omission, no warning (1.3) -------------------


def test_sync_no_gps_omits_map_without_warning(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_no_gps_fit_bytes())
    tiles = _RecordingTiles()

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=tiles)

    # No position pair ⇒ no plan ⇒ no section and NO warning (silent, expected).
    assert len(report.written) == 1
    assert report.warnings == ()
    # A no-GPS run has no complete position pair, so the source is never consulted.
    assert tiles.resolved == []
    text = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert "## Map" not in text
    assert not _map_asset(data_root, _RUN_STEM).exists()


# --- invariant: a warning rides ONLY with a written file, never a failure -----


def test_map_warning_is_discarded_when_the_file_fails(tmp_path: Path) -> None:
    # An outdoor re-export whose matched document has a DAMAGED region: the map
    # path runs (GPS present) and would warn (tiles unavailable), but the merge
    # then raises RegionError -> the file becomes a FileFailure and the warning is
    # discarded. A warning must never accompany a failed file (Req 4.4).
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    workouts = data_root / WORKOUTS_DIR
    workouts.mkdir(parents=True)
    damaged = (
        "---\n"
        "title: Run 2021-09-07 19:46\n"
        "type: workout\n"
        "doc_version: 1\n"
        f"uuid: {_REEXPORT_UUID}\n"
        "sport: Run\n"
        "modality: run\n"
        "---\n\n"
        f"{begin_marker('notes')}\n"
        "a note whose end marker was deleted\n"
    )
    doc = doc_path(data_root, _RUN_STEM)
    doc.write_text(damaged, encoding="utf-8")
    _put(source, "reexport.fit", builder.reexport_a_fit_bytes())

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_UnavailableTiles())

    # The file failed (region conflict); it is NOT written and NOT warned about.
    assert any("reexport.fit" in f.source for f in report.failures)
    assert report.written == ()
    assert report.warnings == ()
    # The damaged document is left byte-for-byte untouched.
    assert doc.read_text(encoding="utf-8") == damaged


# --- regen gains the injected source too; warm cache stays byte-identical (4.1)


def test_regen_with_tiles_injects_maps_and_stays_byte_identical(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    tiles = _RecordingTiles()
    sync(source, data_root, athlete=None, tz=_TZ, tiles=tiles)
    doc = doc_path(data_root, _RUN_STEM)
    assert "## Map" in doc.read_text(encoding="utf-8")

    # Regen rebuilds from the archive alone; the injected source serves the tiles.
    shutil.rmtree(source)
    first = regen(data_root, athlete=None, tz=_TZ, tiles=tiles)
    tree_first = _tree(data_root)
    second = regen(data_root, athlete=None, tz=_TZ, tiles=tiles)

    assert first.failures == () and second.failures == ()
    assert first.warnings == () and second.warnings == ()
    assert first.written == (f"{WORKOUTS_DIR}/{_RUN_STEM}.md",)
    # The Map section survives regeneration and both runs are byte-identical (4.1).
    assert "## Map" in doc.read_text(encoding="utf-8")
    assert _map_asset(data_root, _RUN_STEM).is_file()
    assert _tree(data_root) == tree_first


def test_regen_warns_when_tiles_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    # Initial sync whose tiles were unavailable too: a GPS run document already
    # rendered without a Map section (the map is not part of the archive state).
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_UnavailableTiles())
    shutil.rmtree(source)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_UnavailableTiles())

    doc_ref = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    # Regen behaves identically to sync: warn + omit, exit-code-neutral.
    assert report.written == (doc_ref,)
    assert report.failures == ()
    assert "## Map" not in doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert len(report.warnings) == 1
    assert report.warnings[0].doc == doc_ref


# ===========================================================================
# Document-format version gate (task 5.1, Req 5.4-5.9)
# ===========================================================================
#
# A matched document's frontmatter is parsed once before any write. A version
# strictly greater than the installed fitdocs' DOC_VERSION means: write
# nothing for that source, warn naming the document, and count the file as
# skipped. Missing, unusable, or lower versions proceed to the normal
# merge-and-write path and come out at DOC_VERSION. The two entry points
# differ in what "skipped" costs: sync leaves the source unarchived (retried
# idempotently next run); regen leaves the archive untouched either way (it
# never writes to the archive on this pass regardless of the gate).


@pytest.mark.parametrize("force", [False, True], ids=["no-force", "force"])
def test_sync_skips_newer_document_leaves_source_unarchived_and_retries(
    tmp_path: Path, force: bool
) -> None:
    # Parametrized over ``force`` because Req 5.5 grants it NO exemption: a
    # newer document is left unchanged whether or not the user forces
    # re-processing. Without this, the no-force-bypass behavior is pinned only
    # incidentally (via regen, which passes force=True internally), and a future
    # change adding ``and not force`` to the gate would look safe.
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    doc = doc_path(data_root, _RUN_STEM)

    # First export creates the document at the current version.
    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert doc.is_file()
    assert _frontmatter(doc)["doc_version"] == DOC_VERSION

    # Simulate the document being written by a NEWER fitdocs.
    newer = _set_doc_version_line(doc.read_text(encoding="utf-8"), "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    # A re-export (same session UUID, different bytes -- NOT yet archived)
    # matches this document via `uuid`.
    _put(tmp_path / "src_b", "b.fit", b)
    first = sync(
        tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES, force=force
    )

    # Nothing was written for the gated source; it lands in `skipped` (the
    # shared bucket) rather than `written`, and the run does not fail.
    assert first.written == ()
    assert len(first.skipped) == 1
    assert first.failures == ()
    # A warning names the affected document.
    assert len(first.warnings) == 1
    assert first.warnings[0].doc == f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert "999" in first.warnings[0].detail

    # The document is byte-identical to the newer-version state; the gated
    # source's archive entry was never created.
    assert doc.read_text(encoding="utf-8") == newer
    assert not archive_path(data_root, _sha(b)).exists()

    # A second run over the SAME source repeats the gate -- it is not treated
    # as a completed/processed file just because it landed in `skipped` once.
    second = sync(
        tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES, force=force
    )
    assert second.written == ()
    assert len(second.skipped) == 1
    assert second.failures == ()
    assert len(second.warnings) == 1
    assert doc.read_text(encoding="utf-8") == newer
    assert not archive_path(data_root, _sha(b)).exists()


def test_regen_skips_newer_document_archive_untouched(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    assert _frontmatter(doc)["doc_version"] == DOC_VERSION

    archive = archive_path(data_root, _sha(builder.run_fit_bytes()))
    before_bytes = archive.read_bytes()
    before_mtime = archive.stat().st_mtime_ns

    # Simulate the document being written by a NEWER fitdocs.
    newer = _set_doc_version_line(doc.read_text(encoding="utf-8"), "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.written == ()
    assert len(report.skipped) == 1
    assert report.failures == ()
    assert len(report.warnings) == 1
    assert report.warnings[0].doc == f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert "999" in report.warnings[0].detail

    # The document is left byte-identical, and the archive -- which regen
    # never writes to on this pass -- is completely untouched either way.
    assert doc.read_text(encoding="utf-8") == newer
    assert archive.read_bytes() == before_bytes
    assert archive.stat().st_mtime_ns == before_mtime


def test_sync_upgrades_older_document_preserving_notes_region(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    _put(source, "run.fit", data)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)

    # Hand-write a note and simulate an OLDER document format.
    edited = _set_region(doc.read_text(encoding="utf-8"), "notes", "MY HAND NOTE")
    older = _set_doc_version_line(edited, "doc_version: 1")
    doc.write_text(older, encoding="utf-8")

    # A force re-sync of the same bytes matches this document via `sources`
    # and takes the normal merge-and-write path (the gate does not fire for a
    # lower version).
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES, force=True)

    assert report.failures == ()
    assert len(report.written) == 1
    final = doc.read_text(encoding="utf-8")
    assert extract_regions(final)["notes"] == "MY HAND NOTE"
    assert _frontmatter(doc)["doc_version"] == DOC_VERSION


def test_regen_upgrades_older_document_preserving_notes_region(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _set_region(doc.read_text(encoding="utf-8"), "notes", "MY HAND NOTE")
    older = _set_doc_version_line(edited, "doc_version: 1")
    doc.write_text(older, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    final = doc.read_text(encoding="utf-8")
    assert extract_regions(final)["notes"] == "MY HAND NOTE"
    assert _frontmatter(doc)["doc_version"] == DOC_VERSION


@pytest.mark.parametrize(
    ("label", "line"),
    [
        ("missing", ""),
        ("string", "doc_version: not-a-number"),
        ("bool", "doc_version: true"),
        ("float", "doc_version: 1.5"),
        ("lower", "doc_version: 1"),
        ("equal", f"doc_version: {DOC_VERSION}"),
    ],
)
def test_sync_proceeds_normally_for_non_newer_or_unusable_versions(
    tmp_path: Path, label: str, line: str
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    _put(source, "run.fit", data)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)

    doc.write_text(
        _set_doc_version_line(doc.read_text(encoding="utf-8"), line),
        encoding="utf-8",
    )

    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES, force=True)

    # None of these values are "newer": the gate never fires, the file
    # proceeds through the normal merge-and-write path, and comes out at the
    # current version.
    assert report.failures == ()
    assert len(report.written) == 1
    assert report.skipped == ()
    assert _frontmatter(doc)["doc_version"] == DOC_VERSION


# ===========================================================================
# End-to-end regeneration rehearsal (task 13.3, Req 18.2, 18.3)
# ===========================================================================
#
# fit-ingest's Amendment 1 (task 13.1) moves a metric value -- normalized
# power and everything downstream of it -- for already-documented activities,
# and task 13.2 advanced `contract.DOC_VERSION` from 3 to 4 on that account.
# Neither `sync.regen` nor `audit.audit` needed a single new line for this:
# the version gate and the staleness check already existed. This rehearsal
# exercises that existing machinery end to end rather than adding any, per
# Req 18.5 ("the fit-ingest library reads, writes and migrates no document").
#
# The value-recompute discriminator: `render.frontmatter.build_frontmatter`
# takes every metric value from a freshly computed `DerivedMetrics` and never
# reads an existing document's frontmatter as a value source. `regen` passes
# `force=True` for every document it re-renders, so `sync._process_file` always
# reaches `parse_fit`/`compute_metrics` on this path -- its only pre-parse
# return is the already-archived dedup skip, which `force` disables -- and it
# only ever reuses the existing text for its NOTES/WORKOUT/LOAD regions and its
# version/key warnings. A document hand-tampered with an impossible `avg_hr_bpm` at the
# pre-amendment version therefore has that value overwritten by regeneration
# with the value a fresh, independent `parse_fit` + `compute_metrics` call
# produces from the archived source bytes -- never with the tampered value an
# in-place edit (one that patched only `doc_version` and left the rest alone)
# would have preserved.

_PRE_AMENDMENT_DOC_VERSION: int = 3
"""The document-format version `contract.DOC_VERSION` held before fit-ingest
task 13.2 advanced it to 4 (see that constant's own docstring: "Raised from 3
to 4 by fit-ingest's Amendment 1..."). Named here, with its provenance, rather
than left as a bare literal in the test body."""


def test_regeneration_rehearsal_rewrites_stale_document_from_source_not_in_place(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    _put(source, "run.fit", data)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)  # regen must rebuild from the archive alone (Req 4.4)

    # Ground truth: an independent parse + compute over the same source bytes,
    # never read back from the document under test, is what the "after" value
    # is checked against.
    true_activity = parse_fit(data)
    true_metrics = compute_metrics(true_activity, None)
    assert true_metrics.avg_heart_rate_bpm is not None
    true_avg_hr = int(round(true_metrics.avg_heart_rate_bpm))

    # Hand-simulate a document written before Amendment 1: stamp the
    # pre-amendment version, and corrupt avg_hr_bpm to a sentinel the source
    # .fit could never produce.
    sentinel_hr = true_avg_hr + 111
    edited = doc.read_text(encoding="utf-8")
    edited = _set_doc_version_line(edited, f"doc_version: {_PRE_AMENDMENT_DOC_VERSION}")
    edited = re.sub(r"avg_hr_bpm:\s*\d+", f"avg_hr_bpm: {sentinel_hr}", edited)
    doc.write_text(edited, encoding="utf-8")

    # Precondition, asserted honestly rather than assumed: genuinely at the
    # pre-amendment version, and the sentinel is genuinely in place.
    before_fm = _frontmatter(doc)
    assert before_fm["doc_version"] == _PRE_AMENDMENT_DOC_VERSION
    assert before_fm["avg_hr_bpm"] == sentinel_hr

    # Stale before (Req 18.3): the audit reports it, and reports it for
    # exactly this reason.
    doc_ref = doc.relative_to(data_root).as_posix()
    before_report = audit(data_root)
    before_findings = [f for f in before_report.findings if f.subject == doc_ref]
    assert len(before_findings) == 1
    assert before_findings[0].kind is FindingKind.OUTDATED_VERSION

    # The regeneration pass rewrites it from its archived source (Req 18.2).
    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert doc_ref in report.written

    after_fm = _frontmatter(doc)
    # Current after.
    assert after_fm["doc_version"] == DOC_VERSION
    # The rewritten value is traceable to a re-parse of the source, not to an
    # edit of the old, sentinel-carrying document.
    assert after_fm["avg_hr_bpm"] == true_avg_hr
    # No `!= sentinel_hr` assertion here: `sentinel_hr` is `true_avg_hr + 111`,
    # so once the line above holds it holds by construction and no production
    # mutation can red it without redding that line first. It would read as a
    # second pin and be none. What actually carries the in-place-edit case is
    # the line above plus the asserted false pre-state (`before_fm` holds the
    # sentinel, not the true value) -- an edit that patched only `doc_version`
    # leaves the sentinel in place and reds that assertion.

    # Current after, confirmed independently through the audit too.
    after_report = audit(data_root)
    after_findings = [f for f in after_report.findings if f.subject == doc_ref]
    assert after_findings == []


# ===========================================================================
# Unmanaged-frontmatter-key warning on rewrite (task 5.2, Req 6.3)
# ===========================================================================
#
# Reusing the frontmatter parsed by the version gate, a rewrite that would
# drop keys outside `contract.MANAGED_KEYS` records a DocWarning naming the
# document and the sorted key names; the rewrite still proceeds (the key is
# genuinely gone from the rewritten document) and the run still succeeds.


def test_regen_warns_and_drops_a_hand_added_frontmatter_key(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    doc.write_text(
        _add_frontmatter_key(doc.read_text(encoding="utf-8"), "tags: hiking"),
        encoding="utf-8",
    )
    assert "tags" in _frontmatter(doc)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert len(report.warnings) == 1
    assert report.warnings[0].doc == f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert "tags" in report.warnings[0].detail
    # The rewrite genuinely proceeded and the key is now gone.
    assert "tags" not in _frontmatter(doc)


def test_sync_warns_and_drops_a_hand_added_frontmatter_key(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    _put(source, "run.fit", data)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)

    doc.write_text(
        _add_frontmatter_key(doc.read_text(encoding="utf-8"), "tags: hiking"),
        encoding="utf-8",
    )

    # A force re-sync of the same bytes matches this document via `sources`
    # and takes the normal rewrite path.
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES, force=True)

    assert report.failures == ()
    assert len(report.written) == 1
    assert len(report.warnings) == 1
    assert report.warnings[0].doc == f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert "tags" in report.warnings[0].detail
    assert "tags" not in _frontmatter(doc)


def test_regen_reports_multiple_unmanaged_keys_in_sorted_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    # Inserted NON-MONOTONICALLY, which is the whole point: any strictly
    # descending insertion makes reversal coincide with sorting, so it cannot
    # tell "sorted" from "reversed insertion order" at any key count. Here
    # insertion is middle, zeta, alpha -- sorted gives "alpha, middle, zeta"
    # while reversed insertion would give "alpha, zeta, middle", so the two
    # genuinely diverge.
    edited = doc.read_text(encoding="utf-8")
    edited = _add_frontmatter_key(edited, "middle: 1")
    edited = _add_frontmatter_key(edited, "zeta: 2")
    edited = _add_frontmatter_key(edited, "alpha: 3")
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert len(report.warnings) == 1
    # The exact joined run, not relative indices: pins the separator and the
    # full ordering in one assertion.
    assert "alpha, middle, zeta" in report.warnings[0].detail


def test_one_document_carries_both_an_unmanaged_key_and_a_map_warning(
    tmp_path: Path,
) -> None:
    """Two warnings for one file, both surviving in fixed order.

    This is the whole reason ``_process_file`` returns a *tuple* of warnings
    rather than an optional scalar: the unmanaged-key notice (Req 6.3) and the
    map omission (Req 4.3) are computed at different points in the same rewrite,
    and a scalar would force silently discarding one. Without this test the
    widening is unpinned -- truncating the return to ``warnings[:1]`` passes the
    entire suite.

    Order is fixed by code order, not by iteration: the unmanaged-key warning is
    recorded before the map is resolved.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    doc.write_text(
        _add_frontmatter_key(doc.read_text(encoding="utf-8"), "tags: hiking"),
        encoding="utf-8",
    )

    # Tiles unavailable on the rebuild: the map is omitted AND the hand-added
    # key is dropped, in the same rewrite of the same document.
    report = regen(data_root, athlete=None, tz=_TZ, tiles=_UnavailableTiles())

    assert report.failures == ()
    assert len(report.written) == 1
    assert len(report.warnings) == 2

    expected_doc = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert [w.doc for w in report.warnings] == [expected_doc, expected_doc]
    assert "tags" in report.warnings[0].detail
    assert "no route to host" in report.warnings[1].detail

    # The rewrite still happened: the unmanaged key is genuinely gone.
    assert "tags" not in doc.read_text(encoding="utf-8")


def test_regen_produces_no_warning_for_a_document_with_only_managed_keys(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    shutil.rmtree(source)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert report.warnings == ()


def test_regen_produces_no_warning_after_a_training_load_pass(
    tmp_path: Path,
) -> None:
    """The anti-false-positive case: `LOAD_KEYS` are managed, not unmanaged.

    A document carrying the three training-load frontmatter keys is exactly
    the shape a real load pass leaves behind (design: LOAD_KEYS is a subset of
    MANAGED_KEYS). A rewrite over it must not warn -- a warning on every
    load-processed document would train users to ignore the channel.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = doc.read_text(encoding="utf-8")
    for key in LOAD_KEYS:
        edited = _add_frontmatter_key(edited, f"{key}: 42")
    doc.write_text(edited, encoding="utf-8")
    for key in LOAD_KEYS:
        assert key in _frontmatter(doc)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert report.warnings == ()


def test_sync_version_gated_document_produces_no_unmanaged_key_warning(
    tmp_path: Path,
) -> None:
    """A version-gated document is never rewritten, so it drops nothing (5.5, 6.3).

    A document that is both newer-versioned AND carries a hand-added key must
    warn exactly once -- for the version gate -- and never for the unmanaged
    key, because the gate's early return leaves before the rewrite that would
    have dropped it.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    doc = doc_path(data_root, _RUN_STEM)

    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), "tags: hiking")
    newer = _set_doc_version_line(edited, "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    _put(tmp_path / "src_b", "b.fit", b)
    report = sync(tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.written == ()
    assert len(report.skipped) == 1
    assert report.failures == ()
    # Exactly one warning -- the version gate's -- never a second one for the
    # unmanaged "tags" key.
    assert len(report.warnings) == 1
    assert "999" in report.warnings[0].detail
    assert "tags" not in report.warnings[0].detail
    # Untouched: still carries the hand-added key, byte-identical.
    assert doc.read_text(encoding="utf-8") == newer


def test_regen_version_gated_document_produces_no_unmanaged_key_warning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)

    edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), "tags: hiking")
    newer = _set_doc_version_line(edited, "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.written == ()
    assert len(report.skipped) == 1
    assert len(report.warnings) == 1
    assert "999" in report.warnings[0].detail
    assert "tags" not in report.warnings[0].detail
    assert doc.read_text(encoding="utf-8") == newer


# ===========================================================================
# User-owned frontmatter carry on every rewrite (task 2.2, Req 4.1, 4.2, 4.4,
# 4.5, 4.6)
# ===========================================================================
#
# In the matched-document branch of ``_process_file``, after the version gate
# (which still returns first and rewrites nothing), the user-owned lines of
# the existing document are carried forward verbatim into the rewritten
# frontmatter block -- regardless of whether they form a valid effort tag.
# Carrying never inspects validity (that is task 2.3's warning, not this
# task's boundary).


def test_block_scalar_effort_event_survives_forced_resync_with_notes_edited(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    _put(source, "run.fit", data)
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)

    edited = doc.read_text(encoding="utf-8")
    edited = _add_frontmatter_key(
        edited, "effort: race\neffort_event: >-\n  Boston\n  Marathon"
    )
    edited = _set_region(edited, "notes", "MY HAND-WRITTEN NOTE")
    doc.write_text(edited, encoding="utf-8")

    # A forced re-sync of the same bytes matches this document and rewrites it.
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES, force=True)

    assert report.failures == ()
    assert len(report.written) == 1
    rewritten = doc.read_text(encoding="utf-8")
    assert "effort: race\neffort_event: >-\n  Boston\n  Marathon" in rewritten
    assert extract_regions(rewritten)["notes"] == "MY HAND-WRITTEN NOTE"


def test_block_scalar_effort_event_survives_regen_with_notes_edited(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = doc.read_text(encoding="utf-8")
    edited = _add_frontmatter_key(
        edited, "effort: race\neffort_event: >-\n  Boston\n  Marathon"
    )
    edited = _set_region(edited, "notes", "MY HAND-WRITTEN NOTE")
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    rewritten = doc.read_text(encoding="utf-8")
    assert "effort: race\neffort_event: >-\n  Boston\n  Marathon" in rewritten
    assert extract_regions(rewritten)["notes"] == "MY HAND-WRITTEN NOTE"


def test_single_line_quoted_wikilink_event_survives_regen_with_notes_edited(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = doc.read_text(encoding="utf-8")
    edited = _add_frontmatter_key(
        edited, 'effort: race\neffort_event: "[[Boston Marathon]]"'
    )
    edited = _set_region(edited, "notes", "ANOTHER HAND-WRITTEN NOTE")
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    rewritten = doc.read_text(encoding="utf-8")
    assert 'effort: race\neffort_event: "[[Boston Marathon]]"' in rewritten
    assert extract_regions(rewritten)["notes"] == "ANOTHER HAND-WRITTEN NOTE"


def test_malformed_tag_lines_survive_a_rewrite(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    # "Race" (wrong case) with no ``effort_time_s``/``effort_distance_m``
    # value is not a rule the reader accepts -- but the carry never inspects
    # validity, so it is preserved unchanged regardless.
    edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), "effort: Race")
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert "effort: Race" in doc.read_text(encoding="utf-8")


def test_regenerating_a_tagged_page_twice_is_byte_identical(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: 3600"
    )
    doc.write_text(edited, encoding="utf-8")

    regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)
    first = doc.read_text(encoding="utf-8")
    assert "effort: race\neffort_time_s: 3600" in first

    regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)
    second = doc.read_text(encoding="utf-8")

    assert second == first


def test_carried_lines_sit_after_the_last_managed_key(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: 3600"
    )
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    rewritten = doc.read_text(encoding="utf-8")
    # The carried lines are the last content before the closing fence -- i.e.
    # after every managed key, since the managed block is a single
    # ``yaml.safe_dump`` immediately preceding them.
    assert "effort: race\neffort_time_s: 3600\n---\n" in rewritten


def test_version_gated_tagged_page_is_untouched(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    doc = doc_path(data_root, _RUN_STEM)

    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: 3600"
    )
    newer = _set_doc_version_line(edited, "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    _put(tmp_path / "src_b", "b.fit", b)
    report = sync(tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.written == ()
    assert len(report.skipped) == 1
    assert report.failures == ()
    # Untouched: still carries the hand-added tag, byte-identical.
    assert doc.read_text(encoding="utf-8") == newer
    assert "effort: race" in doc.read_text(encoding="utf-8")


# ===========================================================================
# Malformed-tag warning on rewrite, and the unmanaged warning stays honest
# (task 2.3, Req 1.4, 3.4, 3.6, 4.7)
# ===========================================================================
#
# Reusing the same already-parsed frontmatter the unmanaged-key check reads,
# a rewrite that finds a malformed effort tag records a second DocWarning
# naming the document, with a detail built from the design's fixed prefix
# followed by ``InvalidEffortTag.describe()`` -- the same renderer ``check``
# uses. The unmanaged-key warning (now user-key-exempt, task 1.1/2.2) is
# unaffected: a page whose only extra content is a valid or malformed tag
# produces no unmanaged-key warning at all. Intra-file order is fixed by
# statement order: unmanaged-key, then invalid-effort-tag, then map omission.

_INVALID_TAG_PREFIX = (
    "carries an effort tag fitdocs cannot read -- preserved unchanged, not "
    "in effect until corrected: "
)


def test_malformed_tag_warns_exactly_once_with_the_renderers_text(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: abc"
    )
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    # Exactly one warning -- not merely "a warning is present".
    assert len(report.warnings) == 1
    assert report.warnings[0].doc == f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    expected_detail = (
        _INVALID_TAG_PREFIX
        + "effort_time_s: must be a positive number of seconds; got 'abc'"
    )
    assert report.warnings[0].detail == expected_detail
    # The malformed lines are still present -- carried, not dropped.
    assert "effort_time_s: abc" in doc.read_text(encoding="utf-8")


def test_tagged_page_with_no_other_extra_key_produces_no_warning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    # A VALID tag and nothing else extra: this proves the unmanaged-key
    # exemption (task 1.1) still holds once the malformed-tag warning exists
    # alongside it.
    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: 3600"
    )
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert report.warnings == ()


def test_page_with_tags_key_and_valid_tag_warns_once_naming_tags_only(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), "tags: hiking")
    edited = _add_frontmatter_key(edited, "effort: race\neffort_time_s: 3600")
    doc.write_text(edited, encoding="utf-8")
    assert "tags" in _frontmatter(doc)

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert len(report.warnings) == 1
    assert "tags" in report.warnings[0].detail
    assert "effort" not in report.warnings[0].detail

    rewritten = doc.read_text(encoding="utf-8")
    assert "tags" not in _frontmatter(doc)
    assert "effort: race" in rewritten
    assert "effort_time_s: 3600" in rewritten


def test_unmanaged_key_warning_precedes_invalid_tag_warning_for_one_document(
    tmp_path: Path,
) -> None:
    """Both fire for one document; the unmanaged-key notice comes first.

    Distinct from the ``tags:`` + valid-tag scenario above (which produces
    only ONE warning): here the extra key (``notes_pinned``) is unrelated to
    the tag, so both the unmanaged-key warning and the invalid-effort-tag
    warning fire for the same rewrite, and their order is exactly the module
    docstring's stated sequence (unmanaged-key, invalid-effort-tag, map
    omission).
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _add_frontmatter_key(doc.read_text(encoding="utf-8"), "notes_pinned: yes")
    edited = _add_frontmatter_key(edited, "effort: race\neffort_time_s: abc")
    doc.write_text(edited, encoding="utf-8")

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert len(report.written) == 1
    assert len(report.warnings) == 2
    assert "notes_pinned" in report.warnings[0].detail
    assert report.warnings[1].detail.startswith(_INVALID_TAG_PREFIX)


def test_malformed_tag_with_no_tile_source_warns_before_map_warning(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    shutil.rmtree(source)

    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: abc"
    )
    doc.write_text(edited, encoding="utf-8")

    # No tile source available on the rebuild: the map is omitted AND the
    # tag is malformed, in the same rewrite of the same document.
    report = regen(data_root, athlete=None, tz=_TZ, tiles=_UnavailableTiles())

    assert report.failures == ()
    assert len(report.written) == 1
    assert len(report.warnings) == 2

    expected_doc = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    assert [w.doc for w in report.warnings] == [expected_doc, expected_doc]
    assert report.warnings[0].detail.startswith(_INVALID_TAG_PREFIX)
    assert "no route to host" in report.warnings[1].detail


def test_version_gated_tagged_page_is_warned_only_for_its_version(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    doc = doc_path(data_root, _RUN_STEM)

    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    edited = _add_frontmatter_key(
        doc.read_text(encoding="utf-8"), "effort: race\neffort_time_s: abc"
    )
    newer = _set_doc_version_line(edited, "doc_version: 999")
    doc.write_text(newer, encoding="utf-8")

    _put(tmp_path / "src_b", "b.fit", b)
    report = sync(tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.written == ()
    assert len(report.skipped) == 1
    assert report.failures == ()
    # Warned ONLY for its version -- the version gate returns before the tag
    # is ever read, so no invalid-effort-tag warning is added.
    assert len(report.warnings) == 1
    assert "999" in report.warnings[0].detail
    assert _INVALID_TAG_PREFIX not in report.warnings[0].detail
    # Untouched: byte-identical, still carrying the malformed tag.
    assert doc.read_text(encoding="utf-8") == newer


# ===========================================================================
# Symlink confinement: a workouts/*.md symlink is never followed for writing
# (task 7.2, Req 7.5, 7.6)
# ===========================================================================
#
# The audit (task 6.1) refuses to follow a `workouts/*.md` symlink -- it
# reports it as unreadable rather than opening it. A writing entry point that
# still followed such a symlink would write through it to whatever path it
# points at, including outside the data root; the two commands must agree.


def test_regen_does_not_follow_a_workouts_symlink_pointing_outside_the_data_root(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())
    sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    doc_text = doc.read_text(encoding="utf-8")

    # Replace the real document with a symlink pointing OUTSIDE the data
    # root, at a copy of the same (genuine, recognized) document text -- so a
    # discovery bug that follows the symlink would find a real, rewritable
    # workout document at the far end, not merely a stray non-document.
    outside = tmp_path / "outside.md"
    outside.write_text(doc_text, encoding="utf-8")
    doc.unlink()
    doc.symlink_to(outside)
    before_mtime = outside.stat().st_mtime_ns

    report = regen(data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    # The symlink itself, and the file it points at, are completely
    # untouched -- regen must never follow it to write outside the data root.
    # Content equality alone is not enough here (regen can legitimately
    # re-render byte-identical output), so the mtime is the proof nothing was
    # written through the symlink at all.
    assert doc.is_symlink()
    assert doc.resolve() == outside.resolve()
    assert outside.read_text(encoding="utf-8") == doc_text
    assert outside.stat().st_mtime_ns == before_mtime


def test_sync_does_not_match_or_write_through_a_workouts_symlink(
    tmp_path: Path,
) -> None:
    """A ``uuid``/``sources`` match must never be made against a symlinked
    document either -- ``find_document`` shares the same read helper as
    ``_discover_documents`` (Req 7.5, 7.6)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()

    # First export creates the real document.
    _put(tmp_path / "src_a", "a.fit", a)
    sync(tmp_path / "src_a", data_root, athlete=None, tz=_TZ, tiles=_TILES)
    doc = doc_path(data_root, _RUN_STEM)
    assert doc.is_file()

    # Move the real document content to a symlink pointing outside the data
    # root, standing in for a hostile/mistaken symlink at the same identity.
    outside = tmp_path / "outside.md"
    outside.write_text(doc.read_text(encoding="utf-8"), encoding="utf-8")
    doc.unlink()
    doc.symlink_to(outside)
    outside_before = outside.read_text(encoding="utf-8")

    # A re-export (same session uuid, different bytes) must NOT be merged
    # into the symlinked path -- it should be treated as a fresh document.
    _put(tmp_path / "src_b", "b.fit", b)
    report = sync(tmp_path / "src_b", data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert report.failures == ()
    assert doc.is_symlink()
    assert outside.read_text(encoding="utf-8") == outside_before
