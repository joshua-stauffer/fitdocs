"""End-to-end ownership and migration validation (task 7.2, wiki-contract).

This module is the feature's final checkpoint: it drives the real engine
entry points (:func:`~fitdocs.sync.sync`, :func:`~fitdocs.sync.regen`) and the
read-only :func:`~fitdocs.audit.audit` pass over disposable data roots and
asserts the user-visible guarantees the whole spec exists to make true, rather
than any one module's internals:

* **Full round trip** (Req 1.6, 3.7, 5.4-5.6, 7.1, 7.3): a fixture source
  synced into an empty data root, a hand-edited user-owned region, a forced
  re-processing, and a regeneration -- the edit survives both, the
  provenance stamp and ``generator`` key are present, the ownership
  declarations exist, and nothing outside the permitted set was created or
  modified.
* **Migration by regeneration** (Req 5.3, 5.4, 5.6): a data root seeded with
  previous-format documents carrying user-owned content is reported
  out-of-date by :func:`audit`; a regeneration brings every document back to
  the current format version with its regions intact, and the inspection is
  then clean.

Task 1.3's write-confinement guard (Req 7.5, 7.6) is deliberately **not**
duplicated here -- it already exists, parameterized on entry point and
permitted set, in ``tests/test_confinement.py``; this module reuses its
exported :func:`~tests.test_confinement.assert_confined` rather than
re-implementing the guard inline.

Fully offline: the full round trip below runs under
``tests.test_determinism``'s ``_no_socket`` guard (the same mechanical guard
that module's own offline tests use), so "the whole run stays offline" is an
assertion here, not a comment.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

from fitdocs.athlete import load_athlete_inputs
from fitdocs.audit import FindingKind, audit
from fitdocs.contract import DOC_VERSION, GENERATED_PREFIX, GENERATOR, GENERATOR_KEY
from fitdocs.declaration import DECLARATION_FILENAME, declaration_path
from fitdocs.docmerge import begin_marker, end_marker, extract_regions
from fitdocs.layout import DECLARED_DIRS, WORKOUTS_DIR, doc_path
from fitdocs.sync import regen, sync
from tests.fixtures import builder
from tests.test_confinement import _snapshot, assert_confined, permitted_locations
from tests.test_determinism import _no_socket

# PINNED timezone: a FIXED -06:00 offset (never the system zone) so document
# stems are byte-stable wherever the suite runs.
_TZ = timezone(timedelta(hours=-6))

_RUN_STEM = "2021-09-07-run-1946"


class _ServingTiles:
    """An always-supplied, offline basemap-tile source (stateless -> shared)."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


def _put(source_dir: Path, name: str, data: bytes) -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / name
    path.write_bytes(data)
    return path


def _set_region(text: str, region_id: str, content: str) -> str:
    """Replace a preserved region's inner content in a document string."""
    begin, end = begin_marker(region_id), end_marker(region_id)
    start = text.index(begin)
    finish = text.index(end) + len(end)
    return text[:start] + f"{begin}\n{content}\n{end}" + text[finish:]


def _set_doc_version_line(text: str, replacement: str) -> str:
    """Replace the ``doc_version: N`` frontmatter line with an arbitrary line."""
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        if line.lstrip().startswith("doc_version:"):
            if replacement:
                out.append(replacement + "\n")
            continue
        out.append(line)
    return "".join(out)


# --- 1. full round trip: sync, hand-edit, force re-process, regen ----------


def test_full_round_trip_preserves_edit_provenance_declarations_and_confinement(
    tmp_path: Path,
) -> None:
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source = sandbox / "src"
    _put(source, "run.fit", builder.run_fit_bytes())

    before = _snapshot(sandbox)
    # The whole round trip -- both `sync` calls and the `regen` below -- runs
    # under the same socket-construction guard `tests.test_determinism` uses,
    # so "fully offline" is asserted here rather than merely claimed in prose.
    with mock.patch("socket.socket", _no_socket):
        first = sync(
            source,
            data_root,
            athlete=load_athlete_inputs(data_root),
            tz=_TZ,
            tiles=_TILES,
        )
        assert first.failures == ()
        assert len(first.written) == 1

        doc = doc_path(data_root, _RUN_STEM)
        assert doc.is_file()

        # The provenance stamp and the `generator` frontmatter key are present.
        text = doc.read_text(encoding="utf-8")
        assert any(line.startswith(GENERATED_PREFIX) for line in text.splitlines())
        assert f"{GENERATOR_KEY}: {GENERATOR}" in text

        # The ownership declaration exists in every declared directory.
        for directory in DECLARED_DIRS:
            assert declaration_path(data_root, directory).is_file()

        # Hand-edit the user-owned `notes` region.
        note = "Felt strong; keep this note through everything that follows."
        doc.write_text(_set_region(text, "notes", note), encoding="utf-8")

        # Forced re-processing of the same source.
        forced = sync(
            source,
            data_root,
            athlete=load_athlete_inputs(data_root),
            tz=_TZ,
            tiles=_TILES,
            force=True,
        )
        assert forced.failures == ()
        assert extract_regions(doc.read_text(encoding="utf-8"))["notes"] == note

        # Regeneration from the archive.
        regenerated = regen(
            data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES
        )
        assert regenerated.failures == ()
        final_text = doc.read_text(encoding="utf-8")
        assert extract_regions(final_text)["notes"] == note
        assert any(
            line.startswith(GENERATED_PREFIX) for line in final_text.splitlines()
        )
        assert f"{GENERATOR_KEY}: {GENERATOR}" in final_text

    after = _snapshot(sandbox)
    assert_confined(sandbox, permitted_locations(data_root), before, after)


# --- 2. migration by regeneration: previous-format docs come current -------


def test_migration_by_regeneration_brings_previous_format_documents_current(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    fixtures = {
        "run.fit": builder.run_fit_bytes(),
        "ride.fit": builder.ride_fit_bytes(),
        "strength.fit": builder.strength_fit_bytes(),
    }
    for name, data in fixtures.items():
        _put(source, name, data)
    athlete = load_athlete_inputs(data_root)
    sync(source, data_root, athlete=athlete, tz=_TZ, tiles=_TILES)

    docs = sorted((data_root / WORKOUTS_DIR).glob("*.md"))
    docs = [doc for doc in docs if doc.name != DECLARATION_FILENAME]
    assert len(docs) == 3

    # Seed every document as "previous format": doc_version lower than
    # current, each carrying distinct user-owned content in `notes`.
    notes: dict[str, str] = {}
    for doc in docs:
        note = f"hand-written note for {doc.stem}"
        notes[doc.name] = note
        edited = _set_region(doc.read_text(encoding="utf-8"), "notes", note)
        older = _set_doc_version_line(edited, "doc_version: 1")
        doc.write_text(older, encoding="utf-8")

    # audit reports every one of them out of date.
    before_report = audit(data_root)
    outdated_subjects = {
        finding.subject
        for finding in before_report.findings
        if finding.kind is FindingKind.OUTDATED_VERSION
    }
    assert outdated_subjects == {f"{WORKOUTS_DIR}/{doc.name}" for doc in docs}

    # Regenerate: every document comes back at the current format version,
    # with its user-owned region intact.
    report = regen(
        data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES
    )
    assert report.failures == ()
    assert set(report.written) == {f"{WORKOUTS_DIR}/{doc.name}" for doc in docs}

    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert f"doc_version: {DOC_VERSION}" in text
        assert extract_regions(text)["notes"] == notes[doc.name]

    # The inspection is now clean of every out-of-date/newer-version finding.
    after_report = audit(data_root)
    assert not any(
        finding.kind in (FindingKind.OUTDATED_VERSION, FindingKind.NEWER_VERSION)
        for finding in after_report.findings
    )
