"""Per-modality document assembly and total dispatch (task 3.6, 3.1).

These pin :func:`fitdocs.render.render_document` and the three
:mod:`fitdocs.render.views` assemblers against the approved DocViews /
RenderDispatcher contracts (design §DocViews, §RenderDispatcher; Req 2.7, 5.3,
5.4, 5.5, 6.1, 9.1, 9.5, 10.5, 12.1, 12.2). Contexts are built over real parsed
activities (``parse_fit`` / ``compute_metrics``) with a fixed timezone so titles
and local dates are deterministic; the section order, region presence, asset
links, portability, and byte-determinism are all asserted against complete
rendered documents.

Task 3.1 adds the generated-document provenance banner (design §FrontmatterBuilder
/ DocViews; Req 4.2-4.5): it sits outside every preserved region, survives a
region round-trip unchanged, and is invisible once HTML comments are stripped
(what any vanilla markdown renderer does to a comment) while remaining plainly
visible in the raw source.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import timedelta, timezone, tzinfo

import pytest

from fitdocs import DerivedMetrics, Modality, compute_metrics, parse_fit
from fitdocs.contract import DOC_BANNER, GENERATED_PREFIX, LOAD_NOT_COMPUTED
from fitdocs.docmerge import extract_regions, merge_regions
from fitdocs.metrics.types import AthleteInputs, ZoneSpec
from fitdocs.model import Samples
from fitdocs.render import DocContext, render_document

# The run/ride/strength fixtures start 2021-09-08 01:46:40 UTC; at -06:00 that is
# local 2021-09-07 19:46:40 -- pinned so titles and dates are deterministic.
TZ: tzinfo = timezone(timedelta(hours=-6))
_STEM = "2021-09-07-run-1946"
_REFS: tuple[str, ...] = ("fit-archive/aaaa.fit",)

_HERO_ASSET = "assets/2021-09-07-run-1946-hero.svg"
_ZONES_ASSET = "assets/2021-09-07-run-1946-zones.svg"


def _ctx(
    fit_bytes: bytes,
    *,
    athlete: AthleteInputs | None = None,
    activity_replace: dict[str, object] | None = None,
    metrics: DerivedMetrics | None = None,
) -> DocContext:
    activity = parse_fit(fit_bytes)
    if activity_replace:
        activity = dataclasses.replace(activity, **activity_replace)
    resolved = metrics if metrics is not None else compute_metrics(activity, athlete)
    return DocContext(
        activity=activity,
        metrics=resolved,
        athlete=athlete,
        doc_stem=_STEM,
        source_refs=_REFS,
        tz=TZ,
    )


def _h2s(md: str) -> list[str]:
    """The ``##`` section headings, in document order."""
    return [line for line in md.splitlines() if line.startswith("## ")]


def _h1_count(md: str) -> int:
    """How many top-level ``# `` headings the document carries."""
    return sum(1 for line in md.splitlines() if line.startswith("# "))


def _image_targets(md: str) -> list[str]:
    """Every markdown image link target ``![...](target)`` in the document."""
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)


def _html_comments(md: str) -> list[str]:
    """Every HTML comment in the document."""
    return re.findall(r"<!--.*?-->", md)


# --- run / ride view --------------------------------------------------------


def test_run_routes_to_run_ride_with_full_section_order(run_fit_bytes: bytes) -> None:
    """A run renders the run/ride document: H1 → notes region → Summary →
    Telemetry → Splits → Training Load → Device & Data Quality, with the hero
    chart asset linked and the notes/load regions present (6.1, 10.5)."""
    doc = render_document(_ctx(run_fit_bytes))
    md = doc.markdown

    assert md.startswith("---\n")  # frontmatter first
    assert _h1_count(md) == 1
    assert "# Run 2021-09-07 19:46" in md
    assert "title: Run 2021-09-07 19:46\n" in md  # H1 matches frontmatter title
    assert _h2s(md) == [
        "## Summary",
        "## Telemetry",
        "## Splits",
        "## Training Load",
        "## Device & Data Quality",
    ]

    regions = extract_regions(md)
    assert "notes" in regions
    assert "load" in regions
    assert regions["load"] == LOAD_NOT_COMPUTED
    assert regions["notes"].strip()  # instructive placeholder, not empty
    # The notes region sits between the H1 and the first heading.
    assert md.index("fitdocs:begin:notes") < md.index("## Summary")
    # The load region lives *inside* the Training Load section (heading outside).
    assert md.index("## Training Load") < md.index("fitdocs:begin:load")
    assert md.index("fitdocs:end:load") < md.index("## Device & Data Quality")

    assert len(doc.assets) == 1
    hero = doc.assets[0]
    assert hero.rel_path == _HERO_ASSET
    assert f"]({_HERO_ASSET})" in md
    assert hero.content  # the SVG payload the sync engine writes

    targets = _image_targets(md)
    assert targets
    assert all(target.startswith("assets/") for target in targets)


def test_ride_routes_to_run_ride(ride_no_power_fit_bytes: bytes) -> None:
    """A powerless ride still routes to the run/ride view; telemetry shows the
    HR+Speed hero chart and splits render from the recorded distance."""
    doc = render_document(_ctx(ride_no_power_fit_bytes))
    md = doc.markdown

    assert "# Ride 2021-09-07 19:46" in md
    assert _h2s(md) == [
        "## Summary",
        "## Telemetry",
        "## Splits",
        "## Training Load",
        "## Device & Data Quality",
    ]
    assert any(target.endswith("-hero.svg") for target in _image_targets(md))


# --- strength view ----------------------------------------------------------


def test_strength_with_sets(strength_fit_bytes: bytes) -> None:
    """A strength session with sets renders Summary → Telemetry (HR chart) →
    Workout region → Recorded Sets → Training Load → Devices, with the notes,
    workout, and load regions all present (9.1, 9.5, 10.5)."""
    doc = render_document(_ctx(strength_fit_bytes))
    md = doc.markdown

    assert "# Workout 2021-09-07 19:46" in md
    assert _h2s(md) == [
        "## Summary",
        "## Telemetry",
        "## Workout",
        "## Recorded Sets",
        "## Training Load",
        "## Device & Data Quality",
    ]

    regions = extract_regions(md)
    assert "notes" in regions
    assert "load" in regions
    assert "workout" in regions
    assert regions["workout"].strip()  # instructive placeholder

    assert any(target.endswith("-hero.svg") for target in _image_targets(md))
    assert "| Set | Reps | Load | Rest |" in md  # sets table header
    # The workout region sits inside its heading, ahead of Recorded Sets.
    assert md.index("## Workout") < md.index("fitdocs:begin:workout")
    assert md.index("fitdocs:end:workout") < md.index("## Recorded Sets")


def test_strength_without_sets_omits_recorded_sets(
    strength_no_sets_fit_bytes: bytes,
) -> None:
    """No set data → the Recorded Sets section is omitted entirely (no empty
    scaffold, 9.6); the workout region and the HR-only telemetry chart still
    render."""
    doc = render_document(_ctx(strength_no_sets_fit_bytes))
    md = doc.markdown

    assert "## Recorded Sets" not in md
    assert _h2s(md) == [
        "## Summary",
        "## Telemetry",
        "## Workout",
        "## Training Load",
        "## Device & Data Quality",
    ]
    assert "workout" in extract_regions(md)
    assert any(target.endswith("-hero.svg") for target in _image_targets(md))


# --- generic view + total dispatch ------------------------------------------


def test_generic_view_for_other_modality(minimal_fit_bytes: bytes) -> None:
    """An ``other`` modality renders the generic document: Summary → Telemetry →
    Training Load → Devices, with no Splits / Workout / Recorded Sets (12.1)."""
    doc = render_document(_ctx(minimal_fit_bytes))
    md = doc.markdown

    assert "# Workout 2021-09-07 19:46" in md
    assert _h2s(md) == [
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


@pytest.mark.parametrize("modality", [Modality.SWIM, Modality.OTHER])
def test_unrecognized_modality_routes_to_generic(
    run_fit_bytes: bytes, modality: Modality
) -> None:
    """Total dispatch: degrading a fully-populated activity to an unrecognized
    modality never raises and yields the generic view -- no run/ride or
    strength-only sections leak through (12.2)."""
    doc = render_document(_ctx(run_fit_bytes, activity_replace={"modality": modality}))
    md = doc.markdown

    assert "## Summary" in md
    assert "## Training Load" in md
    assert "## Device & Data Quality" in md
    assert "## Splits" not in md
    assert "## Workout" not in md
    assert "## Recorded Sets" not in md


# --- telemetry omission -----------------------------------------------------


def test_telemetry_section_omitted_when_no_content(minimal_fit_bytes: bytes) -> None:
    """With no plottable series and no average chips, the Telemetry section is
    omitted entirely while Summary / Training Load / Devices always remain."""
    empty = Samples(
        time_s=(),
        heart_rate_bpm=(),
        power_w=(),
        cadence_rpm=(),
        speed_mps=(),
        distance_m=(),
        altitude_m=(),
        latitude_deg=(),
        longitude_deg=(),
        temperature_c=(),
    )
    doc = render_document(
        _ctx(
            minimal_fit_bytes,
            activity_replace={"modality": Modality.OTHER, "samples": empty},
            metrics=DerivedMetrics(),
        )
    )
    md = doc.markdown

    assert "## Telemetry" not in md
    assert _h2s(md) == ["## Summary", "## Training Load", "## Device & Data Quality"]
    regions = extract_regions(md)
    assert "notes" in regions
    assert "load" in regions
    assert not doc.assets


# --- assets + portability + determinism -------------------------------------


def test_assets_ordered_hero_then_zone_with_athlete_inputs(
    run_fit_bytes: bytes,
) -> None:
    """Athlete inputs enable the HR-zone strip and TRIMP: both assets are
    collected in a stable order (hero, then zones) and both are linked, hero
    ahead of zones (8.1, 8.4)."""
    athlete = AthleteInputs(
        resting_hr_bpm=50,
        max_hr_bpm=190,
        hr_zones=ZoneSpec(dividers=(120.0, 130.0, 140.0, 150.0, 160.0)),
    )
    doc = render_document(_ctx(run_fit_bytes, athlete=athlete))
    md = doc.markdown

    assert [asset.rel_path for asset in doc.assets] == [_HERO_ASSET, _ZONES_ASSET]
    assert md.index("-hero.svg") < md.index("-zones.svg")
    assert "TRIMP" in md


def test_portability_only_frontmatter_and_markers(
    run_fit_bytes: bytes, strength_fit_bytes: bytes
) -> None:
    """Portable, plugin-free output: exactly one H1, no wikilinks, image links
    relative to ``assets/``, and the only HTML comments are fitdocs region
    markers plus the one generated-document provenance banner (2.7, 4.2, 5.3,
    5.4, 5.5)."""
    for fit_bytes in (run_fit_bytes, strength_fit_bytes):
        md = render_document(_ctx(fit_bytes)).markdown
        assert _h1_count(md) == 1
        assert "[[" not in md
        assert "]]" not in md
        for target in _image_targets(md):
            assert target.startswith("assets/")
        for comment in _html_comments(md):
            assert comment.startswith(
                ("<!-- fitdocs:begin:", "<!-- fitdocs:end:", GENERATED_PREFIX)
            )


def test_render_is_byte_identical(
    run_fit_bytes: bytes,
    strength_fit_bytes: bytes,
    minimal_fit_bytes: bytes,
) -> None:
    """Identical context → byte-identical markdown and assets on every call
    (4.1)."""
    for fit_bytes in (run_fit_bytes, strength_fit_bytes, minimal_fit_bytes):
        ctx = _ctx(fit_bytes)
        first = render_document(ctx)
        second = render_document(ctx)
        assert first.markdown == second.markdown
        assert first.assets == second.assets


# --- generated-document provenance banner (task 3.1; Req 4.2-4.5) -----------


def test_banner_is_present_and_sits_between_frontmatter_and_title(
    run_fit_bytes: bytes,
) -> None:
    """``DOC_BANNER`` appears once, on its own line, between the closing
    frontmatter fence and the H1 title -- ahead of every region marker (4.2,
    4.4)."""
    md = render_document(_ctx(run_fit_bytes)).markdown
    assert md.count(DOC_BANNER) == 1

    close_fence = md.index("\n---\n") + len("\n---\n")
    banner_index = md.index(DOC_BANNER)
    title_index = md.index("# Run ")
    first_region_index = md.index("fitdocs:begin:")

    assert close_fence <= banner_index < title_index < first_region_index


def test_banner_sits_outside_every_extracted_region(run_fit_bytes: bytes) -> None:
    """The banner is not itself a region and is not nested inside one: removing
    every extracted region's markers and content still leaves the banner text
    behind untouched (4.4)."""
    md = render_document(_ctx(run_fit_bytes)).markdown
    regions = extract_regions(md)
    assert DOC_BANNER in md  # non-vacuous: absence must not pass as "outside"
    assert regions  # non-vacuous: real regions were actually found

    for region_id, content in regions.items():
        assert DOC_BANNER not in content, f"banner leaked into region {region_id!r}"


def test_banner_survives_a_region_round_trip_unchanged(run_fit_bytes: bytes) -> None:
    """Merging a hand-edited existing document's regions into a fresh render
    leaves the fresh render's banner untouched -- the banner lives outside every
    region span :func:`~fitdocs.docmerge.merge_regions` ever touches (4.4)."""
    fresh = render_document(_ctx(run_fit_bytes)).markdown
    existing = fresh.replace(
        "_Your notes go here.", "A hand-written note the user added."
    )
    assert existing != fresh  # the edit actually changed something

    merged = merge_regions(fresh, existing)

    assert merged.count(DOC_BANNER) == 1
    assert DOC_BANNER in merged
    assert "A hand-written note the user added." in merged  # the edit carried over


def test_banner_is_invisible_once_html_comments_are_stripped(
    run_fit_bytes: bytes,
) -> None:
    """The banner is plainly visible in the raw source, yet -- being a single
    well-formed HTML comment -- contributes nothing once comments are stripped,
    which is exactly what a vanilla (CommonMark) renderer does to it (4.3).

    Checked over the BODY only (everything after the frontmatter's closing
    fence): the frontmatter's own ``generator: fitdocs`` key legitimately names
    the tool as visible YAML metadata -- a PKM's properties panel is expected to
    show it -- so this test is about the banner's *body* text disappearing, not
    about every occurrence of the word "fitdocs" anywhere in the document."""
    md = render_document(_ctx(run_fit_bytes)).markdown
    assert DOC_BANNER in md  # plainly visible in source

    # A well-formed single-line HTML comment: what makes it invisible when
    # rendered, everywhere, without a plugin.
    assert re.fullmatch(r"<!--.*-->", DOC_BANNER)

    body = md.split("\n---\n", 1)[1]
    assert DOC_BANNER in body  # plainly visible in the body's raw source too

    without_comments = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    assert DOC_BANNER not in without_comments
    assert "AGENTS.md" not in without_comments  # the declaration pointer is gone


def test_banner_contains_no_run_or_release_varying_value(run_fit_bytes: bytes) -> None:
    """No value that varies between runs or between releases lives in the banner
    (4.5): no digit (a version, a timestamp, a byte count) and no ``uuid``
    module-shaped hex run anywhere in it."""
    assert not any(char.isdigit() for char in DOC_BANNER)

    first = render_document(_ctx(run_fit_bytes)).markdown
    second = render_document(_ctx(run_fit_bytes)).markdown
    assert first.count(DOC_BANNER) == second.count(DOC_BANNER) == 1
    assert first == second
