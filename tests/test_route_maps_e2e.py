"""Feature-level end-to-end validation for route maps (RouteMapsE2E, task 7.1).

Where :mod:`tests.test_sync` unit-tests the engine's per-file map orchestration,
:mod:`tests.render.test_golden_docs` freezes the composed SVG byte-for-byte, and
:mod:`tests.test_determinism` guards the render + compose path against any socket,
this module drives the *whole* feature over disposable temporary data roots and
pins the user-visible guarantees route-maps promises:

* **Warm-cache byte-identity (Req 4.1).** Two full ``sync`` runs of the same
  inputs against a warm fake tile cache -- into two SEPARATE data roots so both
  genuinely write -- produce byte-identical documents AND byte-identical
  ``-map.svg`` assets. This is route-maps' refinement of the workout-docs
  byte-identical guarantee to "byte-identical given a warm tile cache".
* **Outdoor coverage (Req 1.1, 1.2, 1.4).** An activity whose samples carry GPS
  yields a ``## Map`` section immediately after Summary and before Telemetry,
  with a doc-relative image link and the ``assets/<stem>-map.svg`` asset on disk.
* **Clean omission + no resolution (Req 1.3, 3.2, 3.5).** An indoor run (no GPS)
  and a strength session (even one carrying GPS) yield no Map section, no
  ``-map.svg`` asset, and NEVER consult the tile source -- proven with a recording
  fake whose ``resolve`` records every call.
* **Warn, never fail (Req 4.3, 4.4).** A tile source that cannot resolve omits the
  map, warns naming the affected document, leaves every other section intact, and
  never fails the document or the run -- asserted at the engine level (the
  ``SyncReport.warnings`` channel alongside an empty ``failures``) and at the CLI
  level (the summary's Warnings row with a genuine exit code 0).

The timezone is PINNED to a fixed -06:00 offset so document stems are stable
wherever the engine-driven cases run; the CLI threads the *system local* zone, so
those cases match on the sport slug (``-run-`` / ``-ride-``) instead. Every path
is network-free: the warm/recording fakes serve bytes without a socket, and the
CLI case disables tile requests in ``fitdocs.toml`` (the opt-out gate raises
before any fetch) with the fetch seam additionally patched inert.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import Modality, parse_fit
from fitdocs.cli import app
from fitdocs.layout import ASSETS_SUBDIR, WORKOUTS_DIR, doc_path
from fitdocs.render import plan_map
from fitdocs.sync import DocWarning, sync
from fitdocs.tiles import TileUnavailableError
from tests.fixtures import builder

runner = CliRunner()

# PINNED timezone: a fixed -06:00 offset (never the system zone) so document stems
# are byte-stable wherever the engine-driven cases run. Every fixture starts
# 2021-09-08 01:46:40 UTC -> local 2021-09-07 19:46:40, hence the stems below.
_TZ = timezone(timedelta(hours=-6))

_RUN_STEM = "2021-09-07-run-1946"
_RIDE_STEM = "2021-09-07-ride-1946"
_STRENGTH_STEM = "2021-09-07-strength-1946"

_ATTRIBUTION = "© OpenStreetMap contributors"
#: Deterministic synthetic tile bytes -- ``compose_map`` only base64-encodes the
#: bytes (it never decodes the PNG), so any fixed payload composes deterministically.
_TILE_BYTES = b"\x89PNG\r\n\x1a\n synthetic route-map tile"


# --- fixtures / helpers -----------------------------------------------------


def _put(source_dir: Path, name: str, data: bytes) -> Path:
    """Write fixture ``.fit`` bytes into a (possibly fresh) source directory."""
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / name
    path.write_bytes(data)
    return path


def _docs(data_root: Path) -> dict[str, bytes]:
    """Every workout ``.md`` document under ``workouts/`` as ``{name: bytes}``."""
    workouts = data_root / WORKOUTS_DIR
    if not workouts.is_dir():
        return {}
    return {p.name: p.read_bytes() for p in sorted(workouts.glob("*.md"))}


def _map_assets(data_root: Path) -> dict[str, bytes]:
    """Every route-map SVG asset under ``workouts/assets/`` as ``{name: bytes}``."""
    assets = data_root / WORKOUTS_DIR / ASSETS_SUBDIR
    if not assets.is_dir():
        return {}
    return {p.name: p.read_bytes() for p in sorted(assets.glob("*-map.svg"))}


def _h2(md: str) -> list[str]:
    """The ``## `` section headings of ``md``, in document order."""
    return [line for line in md.splitlines() if line.startswith("## ")]


class _WarmCacheTiles:
    """A warm fake tile cache: deterministic bytes for any ref, no network.

    Serves the SAME bytes for the same ref on every call (as a warm ``TileStore``
    would), so two runs over identical inputs compose byte-identical maps.
    Stateless -> one shared instance is safe across runs.
    """

    attribution = _ATTRIBUTION

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: _TILE_BYTES for ref in refs}


class _RecordingTiles:
    """A serving ``TileSource`` that records every ``resolve`` it is asked for.

    Lets a test prove the map path DID reach the source (outdoor) or NEVER did
    (indoor / strength, Req 3.5). Serving raises nothing, so a wrongful strength
    call surfaces as a recorded resolve, not something the engine could swallow.
    """

    attribution = _ATTRIBUTION

    def __init__(self) -> None:
        self.resolved: list[tuple[object, ...]] = []

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        refs = tuple(refs)
        self.resolved.append(refs)
        return {ref: _TILE_BYTES for ref in refs}


class _FailingTiles:
    """A ``TileSource`` whose ``resolve`` always raises ``TileUnavailableError``.

    Models every non-fatal miss -- offline, provider error, or the persistent
    opt-out -- carried in the ``reason`` the warning detail surfaces (Req 4.3).
    """

    attribution = _ATTRIBUTION

    def __init__(self, reason: str = "offline: no route to host") -> None:
        self._reason = reason

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        raise TileUnavailableError(self._reason)


# --- 1. warm-cache byte-identity across two full runs (Req 4.1) -------------


def test_two_full_runs_over_warm_cache_are_byte_identical(tmp_path: Path) -> None:
    """Two full syncs of the same inputs over a warm tile cache -- into SEPARATE
    data roots so both genuinely WRITE -- produce byte-identical documents and
    byte-identical ``-map.svg`` map assets (Req 4.1).

    Mutation caught: any non-determinism in map planning or SVG composition (tile
    order, coordinate formatting, base64) would make a ``-map.svg`` differ between
    the two roots; any non-determinism in the document render would make an ``.md``
    differ. A real GPS fixture is included, so the compared map set is non-empty --
    the byte-identity assertion is not vacuous."""
    fixtures = {
        "run.fit": builder.run_fit_bytes(),  # GPS -> a real map asset
        "ride.fit": builder.ride_fit_bytes(),  # no GPS -> no map
        "strength.fit": builder.strength_fit_bytes(),  # strength -> no map
    }
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    reports = []
    for root in (first_root, second_root):
        root.mkdir()
        source = root / "src"
        for name, data in fixtures.items():
            _put(source, name, data)
        reports.append(
            sync(source, root, athlete=None, tz=_TZ, tiles=_WarmCacheTiles())
        )

    # Both runs wrote every activity (neither skipped nor failed nor warned).
    for report in reports:
        assert len(report.written) == 3
        assert report.failures == ()
        assert report.warnings == ()

    first_docs, second_docs = _docs(first_root), _docs(second_root)
    first_maps, second_maps = _map_assets(first_root), _map_assets(second_root)

    # A real map asset is in the comparison, so byte-identity is not vacuous.
    assert list(first_maps) == [f"{_RUN_STEM}-map.svg"]
    # Documents and map assets are byte-identical across the two full runs.
    assert first_docs == second_docs
    assert first_maps == second_maps


# --- 2. outdoor coverage: Map section + asset, placed correctly (1.1, 1.2, 1.4)


def test_outdoor_activity_yields_map_section_between_summary_and_telemetry(
    tmp_path: Path,
) -> None:
    """A GPS run yields a ``## Map`` section immediately after Summary and before
    Telemetry, a doc-relative ``-map.svg`` image link, and the asset on disk
    (Req 1.1, 1.2, 1.4)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(data_root / "src", "run.fit", builder.run_fit_bytes())

    report = sync(
        data_root / "src", data_root, athlete=None, tz=_TZ, tiles=_WarmCacheTiles()
    )

    assert report.written == (f"{WORKOUTS_DIR}/{_RUN_STEM}.md",)
    assert report.warnings == ()
    md = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    h2 = _h2(md)
    # Placement: Map sits between Summary and Telemetry, adjacent to Summary (1.2).
    assert h2.index("## Summary") < h2.index("## Map") < h2.index("## Telemetry")
    assert h2[h2.index("## Summary") + 1] == "## Map"
    # A standard, doc-relative image link consistent with the other charts (6.2).
    assert f"![Route map]({ASSETS_SUBDIR}/{_RUN_STEM}-map.svg)" in md
    # The self-contained asset is on disk under the standard assets dir (1.4).
    map_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_RUN_STEM}-map.svg"
    assert map_asset.is_file()
    assert map_asset.read_text(encoding="utf-8").startswith("<svg")


# --- 3. clean omission: no GPS -> no section, no asset, no resolution (1.3, 3.5)


def test_indoor_run_yields_no_map_no_asset_and_no_tile_resolution(
    tmp_path: Path,
) -> None:
    """An indoor run (no GPS) omits the Map section and asset entirely and NEVER
    consults the tile source -- no plan, no resolution, no warning (Req 1.3, 3.5).

    A fully-cached warm source stays inert here: with no complete position pair,
    the engine plans no route and so never reaches the source (Req 3.2)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(data_root / "src", "run.fit", builder.run_no_gps_fit_bytes())
    tiles = _RecordingTiles()

    report = sync(data_root / "src", data_root, athlete=None, tz=_TZ, tiles=tiles)

    assert len(report.written) == 1
    assert report.warnings == ()  # a silent, expected omission (never a warning)
    assert tiles.resolved == []  # the source was never consulted (3.5)
    md = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert "## Map" not in md
    assert "![Route map](" not in md
    map_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_RUN_STEM}-map.svg"
    assert not map_asset.exists()


def test_strength_with_gps_yields_no_map_no_asset_and_no_tile_resolution(
    tmp_path: Path,
) -> None:
    """A STRENGTH session that DOES carry GPS still yields no Map section, no
    ``-map.svg`` asset, and no tile resolution: the engine's strength guard -- not
    an absent route -- is what suppresses it (Req 3.5).

    Non-vacuous by construction: the fixture parses to STRENGTH modality AND
    ``plan_map`` over its positions returns a non-None plan, so a deleted guard
    WOULD resolve tiles. A no-GPS strength file would pass regardless of the
    guard, so this fixture is the only shape that actually exercises it."""
    strength_gps = builder.strength_with_gps_fit_bytes()
    activity = parse_fit(strength_gps)
    assert activity.modality is Modality.STRENGTH
    assert (
        plan_map(activity.samples.latitude_deg, activity.samples.longitude_deg)
        is not None
    )

    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(data_root / "src", "strength.fit", strength_gps)
    tiles = _RecordingTiles()

    report = sync(data_root / "src", data_root, athlete=None, tz=_TZ, tiles=tiles)

    assert report.written == (f"{WORKOUTS_DIR}/{_STRENGTH_STEM}.md",)
    assert report.warnings == ()
    assert tiles.resolved == []  # never consulted for a strength session (3.5)
    md = doc_path(data_root, _STRENGTH_STEM).read_text(encoding="utf-8")
    assert "## Map" not in md
    map_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_STRENGTH_STEM}-map.svg"
    assert not map_asset.exists()


# --- 4. warn, never fail: a failing source omits + warns, run succeeds (4.3, 4.4)


def test_failing_source_warns_keeps_other_sections_and_run_does_not_fail(
    tmp_path: Path,
) -> None:
    """A tile source that cannot resolve omits the map, warns naming the document,
    leaves every other section intact, and never fails the document or the run
    (Req 4.3, 4.4).

    Mutation caught: if a tile miss were promoted to a per-file failure, the doc
    would land in ``failures`` (and, via the CLI, flip the exit code); if the
    omission suppressed the whole document, Summary/Telemetry would be gone."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(data_root / "src", "run.fit", builder.run_fit_bytes())

    report = sync(
        data_root / "src", data_root, athlete=None, tz=_TZ, tiles=_FailingTiles()
    )

    doc_ref = f"{WORKOUTS_DIR}/{_RUN_STEM}.md"
    # The document is WRITTEN (not a failure) and the run does not fail (4.4).
    assert report.written == (doc_ref,)
    assert report.failures == ()
    # Exactly one warning, naming the affected document, with the miss reason (4.3).
    assert len(report.warnings) == 1
    warning = report.warnings[0]
    assert isinstance(warning, DocWarning)
    assert warning.doc == doc_ref
    assert "no route to host" in warning.detail
    # The map is gone but every other section renders normally (4.3).
    md = doc_path(data_root, _RUN_STEM).read_text(encoding="utf-8")
    assert "## Map" not in md
    assert "![Route map](" not in md
    assert "## Summary" in md
    assert "## Telemetry" in md
    map_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_RUN_STEM}-map.svg"
    assert not map_asset.exists()


def test_failing_map_via_cli_reports_warning_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven end-to-end through the CLI: a batch whose GPS run's map cannot be
    rendered (tile requests disabled, cold cache) reports a Warnings row naming the
    affected document and exits 0, while a no-GPS ride in the same run is written
    cleanly with no warning (Req 4.3, 4.4).

    This pins the literal user-visible ``exit 0`` that only the CLI exposes -- the
    ``sync`` engine has no exit code. Offline by construction: the persistent
    opt-out gate raises before any fetch, and the fetch seam is patched inert as
    belt-and-suspenders so no test performs real network access."""
    # Belt-and-suspenders: even were a fetch attempted, it would stay offline.
    monkeypatch.setattr("fitdocs.tiles._default_fetch", lambda _url: _TILE_BYTES)
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())  # GPS -> a map that fails
    _put(source, "ride.fit", builder.ride_fit_bytes())  # no GPS -> no map
    # Persistent opt-out: no tile requests. The GPS run plans a map whose tiles are
    # not cached, so the map is omitted with a warning -- entirely offline.
    (data_root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    # A map omission never changes the exit code: the whole run still succeeds (4.4).
    assert result.exit_code == 0
    assert "Warnings" in result.output
    # The CLI threads the system local zone, so match documents by their sport slug.
    docs = sorted(p.name for p in (data_root / WORKOUTS_DIR).glob("*.md"))
    run_doc = next(name for name in docs if "-run-" in name)
    ride_doc = next(name for name in docs if "-ride-" in name)
    # The warning names the GPS document and says why (its map requests are off).
    assert run_doc in result.output
    assert "disabled" in result.output.lower()
    # Both documents were written; the failing one keeps every non-map section.
    run_text = (data_root / WORKOUTS_DIR / run_doc).read_text(encoding="utf-8")
    ride_text = (data_root / WORKOUTS_DIR / ride_doc).read_text(encoding="utf-8")
    assert "## Map" not in run_text
    assert "## Summary" in run_text
    assert "## Map" not in ride_text  # the ride never carried GPS
