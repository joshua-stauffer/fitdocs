"""Sync end-to-end suite over temp data roots (SyncE2ESuite, task 5.2).

Where :mod:`tests.test_sync` unit-tests the per-file pipeline and document
lookup, and :mod:`tests.render.test_golden_docs` (task 5.1) freezes the render
output byte-for-byte, this module drives the *whole* engine -- :func:`sync` and
:func:`regen`, with athlete inputs loaded exactly as the CLI loads them via
:func:`~fitdocs.athlete.load_athlete_inputs` -- over disposable temporary data
roots and asserts the user-visible end-to-end guarantees:

* **Double-sync idempotency** (Req 4.1, 4.2): a no-op re-run writes nothing and
  leaves the data-root tree byte-identical.
* **Renamed duplicate** (Req 3.3): byte-identical content under a second
  filename produces no second document.
* **Re-export convergence** (Req 3.6, 10.2): a re-export -- same session UUID,
  different bytes -- updates the same document in place, preserving an edited
  region verbatim and appending the new source ref last.
* **Damaged-markers conflict** (Req 10.3): a document with damaged region
  markers is left untouched and reported as a conflict while its neighbours in
  the same run still succeed.
* **Athlete flip** (Req 8.1, 8.2, 8.4): with an ``athlete.toml`` the zone strip
  asset and the threshold-dependent TRIMP chip appear; without it both are
  absent and no default zone boundaries are invented anywhere.

The timezone is PINNED to a fixed -06:00 offset so document stems are stable
regardless of where the suite runs. This module and its temp data roots are
deliberately disjoint from task 5.1's ``golden_docs/`` snapshots and from
``tests/test_sync.py`` -- it shares no fixtures, files, or golden artifacts with
either. TSS/IF are honestly absent: the ~10-sample fixtures are far too short
for a normalized-power window, so ``power_tss``/``intensity_factor`` compute to
``None`` regardless of ``ftp_watts``; the genuinely rendered threshold metric is
TRIMP, which this suite asserts (never a fabricated TSS/IF chip).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import yaml

from fitdocs.athlete import ATHLETE_FILE, load_athlete_inputs
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker, extract_regions
from fitdocs.layout import (
    ARCHIVE_DIR,
    ASSETS_SUBDIR,
    WORKOUTS_DIR,
    archive_path,
    doc_path,
    source_ref,
)
from fitdocs.sync import FileFailure, SyncReport, regen, sync
from tests.fixtures import builder

# PINNED timezone: a FIXED -06:00 offset (never the system zone) so document
# stems are byte-stable wherever the suite runs. Every fixture starts
# 2021-09-08 01:46:40 UTC -> local 2021-09-07 19:46:40, hence the stems below.
_TZ = timezone(timedelta(hours=-6))

_RUN_STEM = "2021-09-07-run-1946"
_RIDE_STEM = "2021-09-07-ride-1946"
_STRENGTH_STEM = "2021-09-07-strength-1946"
_MINIMAL_STEM = "2021-09-07-workout-1946"

# The stable session UUID both re-export fixtures record (task 1.6 builder), and
# the strictly-ascending HR-zone dividers the athlete file supplies.
_ZONE_DIVIDERS = (110, 125, 140, 155, 170)


# --- helpers ----------------------------------------------------------------


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


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _frontmatter(doc: Path) -> dict[str, object]:
    """Parse a written document's leading YAML frontmatter block."""
    block = doc.read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    return parsed


def _md_docs(data_root: Path) -> list[str]:
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


def _svg_assets(data_root: Path) -> list[str]:
    """Sorted names of every ``.svg`` asset under ``workouts/assets/``."""
    assets = data_root / WORKOUTS_DIR / ASSETS_SUBDIR
    return sorted(p.name for p in assets.glob("*.svg"))


def _archives(data_root: Path) -> list[str]:
    """Sorted names of every archived ``.fit`` under ``fit-archive/``."""
    return sorted(p.name for p in (data_root / ARCHIVE_DIR).glob("*.fit"))


def _set_region(text: str, region_id: str, content: str) -> str:
    """Replace a preserved region's inner content in a document string."""
    begin, end = begin_marker(region_id), end_marker(region_id)
    start = text.index(begin)
    finish = text.index(end) + len(end)
    return text[:start] + f"{begin}\n{content}\n{end}" + text[finish:]


def _write_athlete(data_root: Path) -> None:
    """Write an ``athlete.toml`` with ascending HR zones and HR thresholds.

    Mirrors the shape the CLI reads: strictly-ascending ``hr_zones`` dividers
    that unlock the zone strip (Req 8.1) plus ``resting_hr_bpm``/``max_hr_bpm``
    that unlock TRIMP (Req 8.4).
    """
    dividers = ", ".join(str(d) for d in _ZONE_DIVIDERS)
    (data_root / ATHLETE_FILE).write_text(
        f"resting_hr_bpm = 45\nmax_hr_bpm = 190\nhr_zones = [{dividers}]\n",
        encoding="utf-8",
    )


def _athlete(data_root: Path):
    """Load the optional athlete inputs exactly as the CLI's ``sync``/``regen`` do."""
    return load_athlete_inputs(data_root)


class _ServingTiles:
    """The always-supplied basemap-tile source these end-to-end runs inject.

    ``tiles`` is now a required engine argument (task 6.1), so every ``sync`` /
    ``regen`` here supplies one. It serves deterministic PNG bytes for any ref, so
    a GPS-bearing fixture (``run``/``reexport``/native-power) now renders a Map
    section and a ``<stem>-map.svg`` asset; the no-GPS ride, the strength session,
    and the session-less minimal fixture plan no route and never consult it.
    Stateless -> one shared instance is safe across calls.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


#: One shared, stateless serving source for the end-to-end sync/regen runs.
_TILES: _ServingTiles = _ServingTiles()


# --- 1. double-sync idempotency: byte-identical, all skipped (Req 4.1, 4.2) --


def test_double_sync_leaves_data_root_byte_identical_and_all_skipped(
    tmp_path: Path,
) -> None:
    """A second sync of the same source writes nothing and leaves the data root
    byte-for-byte unchanged -- a no-op re-run performs no writes (Req 4.1, 4.2).

    Mutation caught: if the archive-presence skip broke (files reprocessed on
    re-run), ``second.written`` would be non-empty and the tree snapshot would
    differ."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    fixtures = {
        "run.fit": builder.run_fit_bytes(),
        "ride.fit": builder.ride_fit_bytes(),
        "strength.fit": builder.strength_fit_bytes(),
        "minimal.fit": builder.minimal_fit_bytes(),
    }
    for name, data in fixtures.items():
        _put(source, name, data)

    first = sync(source, data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES)
    assert isinstance(first, SyncReport)
    assert len(first.written) == 4
    assert first.skipped == ()
    assert first.failures == ()
    # One document per activity landed in the data root (deterministic stems).
    assert _md_docs(data_root) == sorted(
        f"{stem}.md" for stem in (_RUN_STEM, _RIDE_STEM, _STRENGTH_STEM, _MINIMAL_STEM)
    )
    tree_after_first = _tree(data_root)

    second = sync(source, data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES)

    # Every file is already archived -> nothing written, everything skipped.
    assert second.written == ()
    assert len(second.skipped) == 4
    assert second.failures == ()
    # The whole data-root tree is byte-identical: the re-run wrote nothing.
    assert _tree(data_root) == tree_after_first


# --- 2. renamed byte-identical duplicate -> no second document (Req 3.3) -----


def test_renamed_byte_identical_file_produces_no_second_document(
    tmp_path: Path,
) -> None:
    """The same bytes under a different filename dedup to one document and one
    archive; the duplicate is reported skipped (Req 3.3).

    Mutation caught: if content-hash dedup broke, both files would be written and
    two documents / two archives would appear."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    data = builder.run_fit_bytes()
    # Identical bytes under two different names; sorted discovery processes
    # ``a.fit`` first (written) and ``b-renamed.fit`` second (skipped as a dup).
    _put(source, "a.fit", data)
    _put(source, "b-renamed.fit", data)

    report = sync(source, data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES)

    assert len(report.written) == 1
    assert len(report.skipped) == 1
    assert any("b-renamed.fit" in s for s in report.skipped)
    # Exactly one document and one archive despite two source files.
    assert _md_docs(data_root) == [f"{_RUN_STEM}.md"]
    assert _archives(data_root) == [f"{_sha(data)}.fit"]


# --- 3. re-export convergence: same doc, region kept, source appended --------


def test_reexport_updates_same_document_preserving_region_and_appending_source(
    tmp_path: Path,
) -> None:
    """A re-export (same session UUID, different bytes) updates the SAME document
    in place: an edited preserved region survives verbatim and the new source ref
    is appended LAST, with exactly one document for the activity (Req 3.6, 10.2).

    Mutation caught: if UUID convergence broke, a second document would appear; if
    ``merge_regions`` dropped the region, the note would be lost; if the source
    history broke, ``sources`` would not list both refs with the new one last."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    a = builder.reexport_a_fit_bytes()
    b = builder.reexport_b_fit_bytes()
    ref_a = source_ref(_sha(a))
    ref_b = source_ref(_sha(b))
    doc = doc_path(data_root, _RUN_STEM)

    # First export (file A).
    _put(tmp_path / "src_a", "a.fit", a)
    sync(
        tmp_path / "src_a", data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES
    )
    assert doc.is_file()
    assert _frontmatter(doc)["sources"] == [ref_a]

    # The user hand-writes real text into the preserved ``notes`` region.
    note = "Felt strong on the second interval; a new PB pace."
    doc.write_text(
        _set_region(doc.read_text(encoding="utf-8"), "notes", note), encoding="utf-8"
    )

    # Re-export (file B): SAME session UUID, DIFFERENT bytes.
    _put(tmp_path / "src_b", "b.fit", b)
    report = sync(
        tmp_path / "src_b", data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES
    )

    # Exactly one document, updated in place (not duplicated).
    assert report.written == (f"{WORKOUTS_DIR}/{_RUN_STEM}.md",)
    assert _md_docs(data_root) == [f"{_RUN_STEM}.md"]
    # Both sources archived; the new ref is appended LAST (last = current).
    assert archive_path(data_root, _sha(a)).is_file()
    assert archive_path(data_root, _sha(b)).is_file()
    assert _frontmatter(doc)["sources"] == [ref_a, ref_b]
    # The hand-written note survived the in-place regeneration verbatim.
    assert extract_regions(doc.read_text(encoding="utf-8"))["notes"] == note


# --- 4. damaged markers -> conflict, doc untouched, others proceed (Req 10.3) -


def test_damaged_markers_leave_document_untouched_while_others_proceed(
    tmp_path: Path,
) -> None:
    """A document with damaged region markers is a reported conflict left
    byte-for-byte untouched, while its healthy neighbours in the same run still
    regenerate (Req 10.3).

    Mutation caught: if the merge wrote before validating regions, the damaged
    document would be overwritten (its bytes would change and no failure would be
    reported); if a per-file failure aborted the batch, the neighbours would not
    be written."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())
    _put(source, "strength.fit", builder.strength_fit_bytes())
    sync(source, data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES)

    # Damage the run document's ``load`` region: delete its end marker so the
    # markers are unbalanced. A matching re-render must refuse to overwrite it.
    run_doc = doc_path(data_root, _RUN_STEM)
    original = run_doc.read_text(encoding="utf-8")
    damaged = original.replace(end_marker("load") + "\n", "", 1)
    assert damaged != original  # the damaging edit actually applied
    run_doc.write_text(damaged, encoding="utf-8")

    report = regen(data_root, athlete=_athlete(data_root), tz=_TZ, tiles=_TILES)

    # The damaged document is the sole failure, naming a region conflict, and is
    # left byte-for-byte untouched.
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert isinstance(failure, FileFailure)
    assert _RUN_STEM in failure.source
    assert "RegionError" in failure.reason
    assert run_doc.read_text(encoding="utf-8") == damaged
    # The healthy neighbours in the same run still regenerated.
    assert set(report.written) == {
        f"{WORKOUTS_DIR}/{_RIDE_STEM}.md",
        f"{WORKOUTS_DIR}/{_STRENGTH_STEM}.md",
    }


# --- 5. athlete flip: zone strip + TRIMP gated on athlete inputs (Req 8.x) ----


def test_athlete_file_present_renders_zone_strip_and_trimp_chip(
    tmp_path: Path,
) -> None:
    """With an ``athlete.toml`` supplying HR zones and HR thresholds, a HR-bearing
    activity's document gains the zone-strip asset (a ``-zones.svg`` under
    ``workouts/assets/`` and its image link) and the threshold-dependent TRIMP
    chip (Req 8.1, 8.4).

    Mutation caught: if the zone strip stopped reading supplied ``hr_zones``, the
    ``-zones.svg`` asset and link would vanish; if TRIMP stopped reading
    resting/max HR, its chip would disappear."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_athlete(data_root)
    _put(source, "run.fit", builder.run_native_power_sparse_hr_fit_bytes())

    athlete = _athlete(data_root)
    assert athlete is not None  # the athlete file was loaded, mirroring the CLI
    report = sync(source, data_root, athlete=athlete, tz=_TZ, tiles=_TILES)
    assert len(report.written) == 1

    md = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    zones_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_RUN_STEM}-zones.svg"
    # The supplied zones unlock the zone-strip asset and its doc-relative link...
    assert zones_asset.is_file()
    assert f"{ASSETS_SUBDIR}/{_RUN_STEM}-zones.svg" in md
    assert f"{_RUN_STEM}-zones.svg" in _svg_assets(data_root)
    # ...and the resting/max HR thresholds unlock the TRIMP chip (Req 8.4).
    assert "TRIMP" in md


def test_no_athlete_file_omits_zone_strip_and_trimp_with_no_defaults(
    tmp_path: Path,
) -> None:
    """Without an ``athlete.toml`` the zone strip and TRIMP chip are absent and NO
    default zone boundaries are invented anywhere -- ``load_athlete_inputs``
    returns ``None`` and the athlete-gated content simply degrades to omission
    (Req 8.2, 8.4).

    Mutation caught: if a default zone set were substituted when athlete inputs
    are absent, a ``-zones.svg`` asset would be written and the supplied dividers
    (or any invented boundaries) would appear in the document."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    # No athlete.toml is written: the athlete-gated features must all degrade off.
    _put(source, "run.fit", builder.run_native_power_sparse_hr_fit_bytes())

    athlete = _athlete(data_root)
    assert athlete is None  # absent file -> None, exactly as the CLI sees it
    sync(source, data_root, athlete=athlete, tz=_TZ, tiles=_TILES)

    md = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    zones_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_RUN_STEM}-zones.svg"
    # No zone-strip asset at all -- only the hero chart and the always-supplied
    # route map (this fixture carries GPS) are emitted; no ``-zones.svg``.
    assert not zones_asset.exists()
    assert _svg_assets(data_root) == [f"{_RUN_STEM}-hero.svg", f"{_RUN_STEM}-map.svg"]
    assert "-zones.svg" not in md
    # No threshold-dependent chip and no invented zone boundaries anywhere.
    assert "TRIMP" not in md
    for divider in _ZONE_DIVIDERS:
        assert str(divider) not in md
