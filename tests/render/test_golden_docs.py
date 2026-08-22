"""Golden document suite over the real-shaped fixtures (task 5.1).

For every synthetic fixture shaped after the verified real HealthFit corpus
(task 1.6) this suite builds a :class:`~fitdocs.render.DocContext` *exactly as the
sync pipeline does* -- with a PINNED timezone and PINNED athlete inputs -- renders
it via :func:`~fitdocs.render.render_document`, and asserts the whole document
markdown and every chart SVG asset are BYTE-IDENTICAL to committed golden files
under ``tests/render/golden_docs/`` (Req 4.1). The committed goldens are the
frozen render contract: any change to the document format, section structure, or
chart output diverges from them and fails loudly.

On top of the byte-golden parity guard, the suite pins the requirement
*observables* structurally by reading the produced document (these encode the
per-modality and honest-absence rules, in addition to the byte match):

* **No fabricated zeros / honest absence** (Req 13.1): the GPS-less run omits the
  Climb row entirely -- never a fabricated ``0 m`` climb.
* **No default zones** (Req 8.2): the HR-zone strip and the TRIMP chip appear
  *only* because athlete ``hr_zones`` were supplied; rendered without athlete
  inputs, both are absent -- no invented boundaries.
* **Per-modality correctness**: the strength golden shows telemetry (the HR
  chart) plus the ``## Workout`` region and NO ``## Recorded Sets`` table (Req
  9.1, 9.6); the powerless-ride golden's hero chart uses the HR + Speed fallback,
  never power (Req 7.2); the GPS-less run omits climb while its chart still
  renders (Req 13.1, 13.2); the minimal file renders a generic document (Req
  12.1).

This module and its ``golden_docs/`` snapshot directory are deliberately
disjoint from task 5.2's sync end-to-end suite and its temp data roots.

Regenerating the committed goldens (only when an intended render change should
update them): ``uv run python -m tests.render.test_golden_docs``. The tests read
those files back and assert byte-equality, so goldens always equal live render
output -- never hand-edited.
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Callable
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from fitdocs import compute_metrics, parse_fit
from fitdocs.docmerge import extract_regions
from fitdocs.layout import activity_uid, doc_stem, source_ref
from fitdocs.metrics.types import AthleteInputs, ZoneSpec
from fitdocs.render import (
    Asset,
    DocContext,
    MapData,
    RenderedDoc,
    plan_map,
    render_document,
)
from fitdocs.render.charts.palette import (
    ROUTE_BIKE_TINT,
    ROUTE_NEUTRAL_TINT,
    ROUTE_RUN_TINT,
)
from fitdocs.render.sections import hero_chart_spec
from tests.fixtures import builder

_GOLDEN_DIR = Path(__file__).parent / "golden_docs"

# PINNED timezone: a FIXED -06:00 offset, never the system zone, so dates and
# document stems are byte-stable regardless of where the suite runs (Req 4.1).
# Every fixture starts 2021-09-08 01:46:40 UTC -> local 2021-09-07 19:46:40, so
# each stem is a stable ``2021-09-07-<slug>-1946``.
TZ: tzinfo = timezone(timedelta(hours=-6))

# PINNED athlete inputs: fixed thresholds plus strictly-ascending HR-zone
# dividers so the HR-zone strip renders and time-in-zone is computed (Req 8.1),
# with resting/max HR enabling TRIMP and ``ftp_watts`` enabling IF/TSS (Req 8.4).
# The dividers (110..170 bpm) split the fixtures' recorded HR ranges into real,
# non-empty zone occupancy. IF/TSS are honestly absent from these goldens: the
# 10-sample fixtures are far too short for a normalized-power window, so the
# metric cannot be computed -- a genuine no-fabrication outcome, not a missing
# input.
ATHLETE = AthleteInputs(
    ftp_watts=250.0,
    resting_hr_bpm=45,
    max_hr_bpm=190,
    hr_zones=ZoneSpec(dividers=(110.0, 125.0, 140.0, 155.0, 170.0)),
)

# Fixture key -> encoded ``.fit`` byte builder, each shaped after the verified
# real corpus (task 1.6): a run with native power + sparse HR, a run without
# GPS/altitude, a ride without power, a ride long enough to compute NP with a
# genuine mid-stream power dropout (chore/power-absent-sample-fill, closing the
# gap that no committed golden ever exercised a real NP value at all -- every
# other power-bearing fixture above is only 10 records, span 9 s, far below
# NP_MIN_SPAN_S), a strength session with HR-only records and no set messages,
# and the minimal (session-less) file.
FIXTURES: dict[str, Callable[[], bytes]] = {
    "run_native_power_sparse_hr": builder.run_native_power_sparse_hr_fit_bytes,
    "run_no_gps": builder.run_no_gps_fit_bytes,
    "ride_no_power": builder.ride_no_power_fit_bytes,
    "ride_power_dropout": builder.ride_power_dropout_fit_bytes,
    "strength_no_sets": builder.strength_no_sets_fit_bytes,
    "minimal": builder.minimal_fit_bytes,
}

# Map-bearing golden cases (route-maps task 4.2). Each is one of the FIXTURES'
# .fit bytes rendered with a prepared ``MapData`` injected into the DocContext --
# exactly what the sync engine does once it has planned and resolved a route's
# tiles. The .fit modality selects the outdoor-capable view (and thus the sport
# tint): a run (run tint), a ride (ride tint), and the session-less minimal file
# (generic view, neutral tint). ``map_data`` is injected directly, so the
# activity's own GPS channels are irrelevant here.
MAP_FIXTURES: dict[str, Callable[[], bytes]] = {
    "map_run": builder.run_native_power_sparse_hr_fit_bytes,
    "map_ride": builder.ride_no_power_fit_bytes,
    "map_generic": builder.minimal_fit_bytes,
}

# A short, stable curved route (no gaps) shared by every map case, planned once
# and resolved to a single synthetic tile, so the composed map is deterministic.
_MAP_LATS: tuple[float | None, ...] = (45.0, 45.0008, 45.0016, 45.0022, 45.0030)
_MAP_LONS: tuple[float | None, ...] = (10.0, 10.0010, 10.0016, 10.0026, 10.0032)
_MAP_ATTRIBUTION = "© OpenStreetMap contributors"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """One PNG chunk: length + type + data + CRC32(type + data), big-endian."""
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _solid_png(size: int, rgb: tuple[int, int, int]) -> bytes:
    """A minimal valid solid-color truecolor PNG, stdlib only (license-clean).

    A hand-built signature / ``IHDR`` / single ``IDAT`` / ``IEND`` raster --
    never a redistributed basemap-provider tile. Deterministic for identical
    inputs, so the composed map goldens stay byte-stable (Req 4.1).
    """
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    raw = (b"\x00" + bytes(rgb) * size) * size
    idat = zlib.compress(raw, 9)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _map_data() -> MapData:
    """Prepared, resolved map inputs for a map-bearing DocContext.

    Plans the shared route and resolves every tile it requires to one committed
    synthetic PNG's bytes (a real tile's pixels never show through the route), so
    the ``MapData`` is deterministic and license-clean (Req 4.1)."""
    plan = plan_map(_MAP_LATS, _MAP_LONS)
    assert plan is not None
    tile = _solid_png(4, (46, 139, 120))
    return MapData(
        plan=plan,
        tiles=tuple((ref, tile) for ref in plan.tiles),
        attribution=_MAP_ATTRIBUTION,
    )


def _build_ctx(
    fit_bytes: bytes,
    athlete: AthleteInputs | None = ATHLETE,
    map_data: MapData | None = None,
) -> DocContext:
    """Build a :class:`DocContext` the way the sync per-file pipeline does.

    Mirrors ``sync._process_file``: parse the bytes, compute metrics against the
    (pinned) athlete inputs, derive the stable activity uid and a realistic
    date-prefixed document stem from the pinned timezone (with a
    never-collides predicate), and assemble the single archive source ref. The
    result is a deterministic, byte-stable render input. ``map_data`` defaults to
    ``None`` -- the no-positions/omission shape -- so every position-less golden
    stays byte-identical; a map-bearing case passes a prepared :class:`MapData`.
    """
    activity = parse_fit(fit_bytes)
    metrics = compute_metrics(activity, athlete)
    sha = hashlib.sha256(fit_bytes).hexdigest()
    uid = activity_uid(activity, sha)
    stem = doc_stem(activity, uid, TZ, lambda _candidate: False)
    return DocContext(
        activity=activity,
        metrics=metrics,
        athlete=athlete,
        doc_stem=stem,
        source_refs=(source_ref(sha),),
        tz=TZ,
        map_data=map_data,
    )


def _render(key: str, athlete: AthleteInputs | None = ATHLETE) -> RenderedDoc:
    """Render the fixture ``key`` with the given (default pinned) athlete inputs."""
    return render_document(_build_ctx(FIXTURES[key](), athlete))


def _render_map(key: str, athlete: AthleteInputs | None = ATHLETE) -> RenderedDoc:
    """Render the map-bearing fixture ``key`` with a prepared ``MapData`` injected."""
    ctx = _build_ctx(MAP_FIXTURES[key](), athlete, map_data=_map_data())
    return render_document(ctx)


def _asset_golden_name(key: str, rel_path: str) -> str:
    """Golden filename for an asset: ``assets/<stem>-<chart>.svg`` -> ``<key>-<chart>``.

    The rendered rel_path embeds the per-fixture document stem; keying golden
    files by the stable fixture ``key`` keeps the snapshot directory readable and
    collision-free (the two run fixtures share a stem yet stay distinct here).
    """
    chart = rel_path.rsplit("-", 1)[1]  # e.g. "hero.svg" / "zones.svg"
    return f"{key}-{chart}"


def _read_golden(name: str) -> str:
    """Read a committed golden file (missing file -> the RED-phase failure)."""
    return (_GOLDEN_DIR / name).read_text(encoding="utf-8")


def _h1_lines(md: str) -> list[str]:
    """The top-level ``# `` headings (``## `` and deeper excluded)."""
    return [line for line in md.splitlines() if line.startswith("# ")]


def _h2_lines(md: str) -> list[str]:
    """The ``## `` section headings, in document order."""
    return [line for line in md.splitlines() if line.startswith("## ")]


def _image_targets(md: str) -> list[str]:
    """Every markdown image-link target ``![...](target)``."""
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)


def _write_goldens() -> None:
    """(Re)generate every committed golden from the finished render output.

    Writes one ``<key>.md`` plus a ``<key>-<chart>.svg`` per emitted asset for
    each fixture. Intended for ``python -m tests.render.test_golden_docs`` only,
    when an intended render change should refresh the snapshots -- the tests read
    these files back and assert byte-equality, so goldens equal live output.
    """
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for key in FIXTURES:
        doc = _render(key)
        (_GOLDEN_DIR / f"{key}.md").write_text(doc.markdown, encoding="utf-8")
        for asset in doc.assets:
            name = _asset_golden_name(key, asset.rel_path)
            (_GOLDEN_DIR / name).write_text(asset.content, encoding="utf-8")
    # Map-bearing cases: commit the document plus only its ``-map.svg`` asset (the
    # hero/zones assets are byte-identical to the position-less fixtures' and are
    # already pinned there; the .md pins the Map section's placement and link).
    for key in MAP_FIXTURES:
        doc = _render_map(key)
        (_GOLDEN_DIR / f"{key}.md").write_text(doc.markdown, encoding="utf-8")
        for asset in doc.assets:
            if asset.rel_path.endswith("-map.svg"):
                name = _asset_golden_name(key, asset.rel_path)
                (_GOLDEN_DIR / name).write_text(asset.content, encoding="utf-8")


# --- 1. byte-golden parity: full document + every chart asset (Req 4.1) ------


@pytest.mark.parametrize("key", FIXTURES)
def test_document_markdown_matches_committed_golden(key: str) -> None:
    """The live-rendered document markdown equals its committed golden byte-for-byte."""
    doc = _render(key)
    assert doc.markdown == _read_golden(f"{key}.md")


@pytest.mark.parametrize("key", FIXTURES)
def test_chart_assets_match_committed_goldens(key: str) -> None:
    """Every rendered chart SVG asset equals its committed golden byte-for-byte."""
    doc = _render(key)
    assert doc.assets, f"{key} should render at least the hero chart asset"
    for asset in doc.assets:
        name = _asset_golden_name(key, asset.rel_path)
        assert asset.content == _read_golden(name)


# --- 2. determinism: render twice -> byte-identical (Req 4.1) ----------------


@pytest.mark.parametrize("key", FIXTURES)
def test_render_twice_is_byte_identical(key: str) -> None:
    """Rendering the same context twice yields identical markdown and assets."""
    ctx = _build_ctx(FIXTURES[key]())
    first = render_document(ctx)
    second = render_document(ctx)
    assert first.markdown == second.markdown
    assert first.assets == second.assets


def test_goldens_are_distinct_across_fixtures() -> None:
    """Each fixture's document matches only its own golden (guards copy/paste)."""
    for key in FIXTURES:
        live = _render(key).markdown
        for other in FIXTURES:
            if other == key:
                continue
            assert live != _read_golden(f"{other}.md"), (
                f"{key} document matched {other}.md"
            )


# --- 3. honest absence: no fabricated zeros (Req 13.1, 13.2) -----------------


def test_gps_less_run_omits_climb_and_still_renders_chart() -> None:
    """The GPS-less run omits the Climb row (no fabricated ``0 m``) while its hero
    chart still renders. The fixture keeps distance/speed (only GPS + altitude are
    absent), so the axis is km -- the load-bearing observable is that climb is
    omitted, not zeroed, and the chart is present (Req 13.1, 13.2)."""
    doc = _render("run_no_gps")
    md = doc.markdown

    assert "| Climb |" not in md  # the Climb row is omitted entirely...
    assert "| Climb | 0 m" not in md  # ...never a fabricated zero climb.

    # The hero chart still renders over the retained distance axis (km), from the
    # HR + Pace fallback (this run has no power).
    spec = hero_chart_spec(_build_ctx(builder.run_no_gps_fit_bytes()))
    assert spec is not None
    assert spec.x_unit == "km"
    assert [s.label for s in spec.series] == ["HR", "Pace"]
    assert spec.backdrop is None  # no altitude -> no elevation backdrop band
    assert any(a.rel_path.endswith("-hero.svg") for a in doc.assets)


# --- 4. no default zones: strip + threshold chips are athlete-gated (Req 8.2) -


def test_zone_strip_and_trimp_appear_only_with_athlete_inputs() -> None:
    """The HR-zone strip and TRIMP chip appear only because athlete ``hr_zones``
    and HR thresholds were supplied; without athlete inputs both vanish -- proving
    the strip reflects supplied zones and never invents default boundaries (Req
    8.2, 8.4)."""
    with_athlete = _render("run_native_power_sparse_hr", ATHLETE)
    without_athlete = _render("run_native_power_sparse_hr", None)

    assert any(a.rel_path.endswith("-zones.svg") for a in with_athlete.assets)
    assert "-zones.svg" in with_athlete.markdown
    assert "TRIMP" in with_athlete.markdown

    assert all(not a.rel_path.endswith("-zones.svg") for a in without_athlete.assets)
    assert "-zones.svg" not in without_athlete.markdown
    assert "TRIMP" not in without_athlete.markdown


# --- 5. per-modality correctness --------------------------------------------


def test_strength_golden_shows_telemetry_and_workout_but_no_sets_table() -> None:
    """The strength (no-set-messages) golden shows a Telemetry HR chart plus the
    ``## Workout`` region and NO ``## Recorded Sets`` table -- an HR-only strength
    document, never an empty sets scaffold (Req 9.1, 9.6)."""
    doc = _render("strength_no_sets")
    md = doc.markdown

    assert _h2_lines(md) == [
        "## Summary",
        "## Telemetry",
        "## Workout",
        "## Training Load",
        "## Device & Data Quality",
    ]
    assert "## Recorded Sets" not in md
    assert "| Set | Reps | Load | Rest |" not in md
    assert "workout" in extract_regions(md)
    assert any(a.rel_path.endswith("-hero.svg") for a in doc.assets)

    # HR-only, distance-less strength telemetry -> the genuine elapsed-time axis.
    spec = hero_chart_spec(_build_ctx(builder.strength_no_sets_fit_bytes()))
    assert spec is not None
    assert spec.x_unit == "min"
    assert [s.label for s in spec.series] == ["HR"]


def test_powerless_ride_golden_uses_hr_plus_speed_fallback() -> None:
    """The powerless ride's hero chart falls back to HR + Speed, never power, and
    the summary carries no Power row (Req 7.2, 13.1)."""
    spec = hero_chart_spec(_build_ctx(builder.ride_no_power_fit_bytes()))
    assert spec is not None
    assert [s.label for s in spec.series] == ["HR", "Speed"]
    assert all(s.label != "Power" for s in spec.series)

    md = _render("ride_no_power").markdown
    assert "| Power |" not in md  # no fabricated power stat on a powerless ride


def test_minimal_fixture_renders_a_generic_document() -> None:
    """The minimal (session-less) file renders a generic document without error --
    no run/ride or strength-only sections leak through (Req 12.1)."""
    doc = _render("minimal")
    md = doc.markdown

    assert _h2_lines(md) == [
        "## Summary",
        "## Telemetry",
        "## Training Load",
        "## Device & Data Quality",
    ]
    assert "## Splits" not in md
    assert "## Workout" not in md
    assert "## Recorded Sets" not in md
    regions = extract_regions(md)
    assert "notes" in regions
    assert "load" in regions
    assert "workout" not in regions


# --- 6. committed-golden portability + well-formedness spot checks -----------


@pytest.mark.parametrize("key", FIXTURES)
def test_committed_markdown_is_portable(key: str) -> None:
    """Each committed golden document: valid ``type: workout`` YAML frontmatter,
    exactly one ``# `` H1, and only relative ``assets/`` image links (Req 5.1,
    5.3, 5.5). The exhaustive portability gate is task 5.3; this is a spot check
    that the goldens are portable at rest."""
    md = _read_golden(f"{key}.md")

    assert md.startswith("---\n")
    _, _, after = md.partition("---\n")
    block, fence, _ = after.partition("\n---\n")
    assert fence == "\n---\n", "frontmatter must be a closed --- block"
    frontmatter = yaml.safe_load(block)
    assert isinstance(frontmatter, dict)
    assert frontmatter.get("type") == "workout"

    assert len(_h1_lines(md)) == 1
    for target in _image_targets(md):
        assert target.startswith("assets/")


def test_committed_svgs_are_well_formed_xml() -> None:
    """Every committed golden ``.svg`` parses as well-formed XML."""
    svg_paths = sorted(_GOLDEN_DIR.glob("*.svg"))
    assert svg_paths, "expected committed golden SVG assets"
    for path in svg_paths:
        ET.fromstring(path.read_text(encoding="utf-8"))


# --- 7. route maps: presence + placement, byte goldens, tints, omission ------


@pytest.mark.parametrize("key", MAP_FIXTURES)
def test_map_document_markdown_matches_committed_golden(key: str) -> None:
    """A map-bearing document's markdown equals its committed golden byte-for-byte."""
    doc = _render_map(key)
    assert doc.markdown == _read_golden(f"{key}.md")


@pytest.mark.parametrize("key", MAP_FIXTURES)
def test_map_asset_matches_committed_golden(key: str) -> None:
    """The rendered ``-map.svg`` asset equals its committed golden byte-for-byte."""
    doc = _render_map(key)
    map_assets = [a for a in doc.assets if a.rel_path.endswith("-map.svg")]
    assert len(map_assets) == 1, f"{key} should emit exactly one map asset"
    assert map_assets[0].content == _read_golden(f"{key}-map.svg")


@pytest.mark.parametrize("key", MAP_FIXTURES)
def test_map_section_sits_between_summary_and_telemetry(key: str) -> None:
    """The Map section is emitted immediately after Summary and before Telemetry,
    with its image link, and the map asset is FIRST in the assets tuple (Req 1.1,
    1.2, 1.4, 6.2)."""
    doc = _render_map(key)
    md = doc.markdown
    h2 = _h2_lines(md)

    assert "## Map" in h2
    assert h2.index("## Summary") < h2.index("## Map") < h2.index("## Telemetry")
    # Summary -> Map are adjacent (nothing wedged between them).
    assert h2[h2.index("## Summary") + 1] == "## Map"

    # A standard, doc-relative image link consistent with the other charts (6.2).
    assert "![Route map](" in md
    map_targets = [t for t in _image_targets(md) if t.endswith("-map.svg")]
    assert len(map_targets) == 1
    assert map_targets[0].startswith("assets/")

    # Section order == asset order: the map asset leads the tuple (1.1, 1.2).
    assert doc.assets, f"{key} should emit assets"
    assert doc.assets[0].rel_path.endswith("-map.svg")
    assert doc.assets[0].rel_path == map_targets[0]


def test_run_and_ride_maps_use_their_sport_tints() -> None:
    """Run and ride maps tint the route with their sport tints (Req 2.3)."""
    run_map = _map_asset(_render_map("map_run"))
    ride_map = _map_asset(_render_map("map_ride"))

    assert ROUTE_RUN_TINT in run_map.content
    assert ROUTE_BIKE_TINT not in run_map.content

    assert ROUTE_BIKE_TINT in ride_map.content
    assert ROUTE_RUN_TINT not in ride_map.content


def test_generic_map_uses_neutral_tint() -> None:
    """A generic (non-strength, non-run/ride) map uses the neutral tint (Req 2.3)."""
    generic_map = _map_asset(_render_map("map_generic"))
    assert ROUTE_NEUTRAL_TINT in generic_map.content
    assert ROUTE_RUN_TINT not in generic_map.content
    assert ROUTE_BIKE_TINT not in generic_map.content


def test_strength_view_never_emits_a_map_even_with_map_data() -> None:
    """The strength view never renders a Map section -- even if map inputs are
    (wrongly) present, ``render_strength`` stays untouched: no ``## Map`` heading
    and no map asset (Req 1.2 boundary; the strength view is out of scope)."""
    doc = render_document(
        _build_ctx(builder.strength_no_sets_fit_bytes(), ATHLETE, map_data=_map_data())
    )
    assert "## Map" not in doc.markdown
    assert "![Route map](" not in doc.markdown
    assert all(not a.rel_path.endswith("-map.svg") for a in doc.assets)


def test_position_less_documents_omit_the_map_section_and_asset() -> None:
    """With no prepared map inputs (the committed ``FIXTURES``, all ``map_data``
    ``None``) every document omits the Map section AND its asset entirely, leaving
    the rest unchanged (Req 1.3) -- this is what keeps the existing goldens
    byte-identical."""
    for key in FIXTURES:
        doc = _render(key)
        assert "## Map" not in doc.markdown, f"{key} unexpectedly emitted a Map section"
        assert "![Route map](" not in doc.markdown
        assert all(not a.rel_path.endswith("-map.svg") for a in doc.assets)


def _map_asset(doc: RenderedDoc) -> Asset:
    """The single ``-map.svg`` asset from a map-bearing rendered document."""
    map_assets = [a for a in doc.assets if a.rel_path.endswith("-map.svg")]
    assert len(map_assets) == 1
    return map_assets[0]


if __name__ == "__main__":
    _write_goldens()
