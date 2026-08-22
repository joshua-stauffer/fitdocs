"""Per-modality document assembly (design: DocViews).

This module turns a :class:`~fitdocs.render.DocContext` into a complete workout
document for one modality: the single H1 title, the reserved content regions
(``notes`` everywhere, ``workout`` for strength), and the ``##`` sections in the
exact reference order for run/ride, strength, and the generic fallback (design
§DocViews; Req 6.1, 9.1, 12.1). Assembly is pure and deterministic -- strings
and chart :class:`~fitdocs.render.Asset`s out, no file I/O (the sync engine owns
all writes, Req 4.1).

Three rules govern every view:

- **One H1, headings outside regions.** The ``# <title>`` line is the document's
  only top-level heading (Req 5.3); every section is a ``##``. Section headings
  live *outside* the region markers so a downstream pass (training-load) replaces
  only a region's inner content, never its heading (Req 10.5, 11.3). The
  ``notes`` region is emitted bare (no heading) right after the H1; the ``load``
  region lives under ``## Training Load``; the strength ``workout`` region lives
  under ``## Workout``.
- **Honest omission.** A ``## Splits`` / ``## Recorded Sets`` / ``## Telemetry``
  section whose body would be empty is omitted entirely -- heading and all (Req
  9.6, 13.2). ``## Summary``, ``## Training Load``, ``## Device & Data Quality``,
  and the ``notes`` region are always present.
- **Portable, plugin-free markdown.** The only PKM affordances are the YAML
  frontmatter, the HTML-comment region markers, and the HTML-comment provenance
  banner -- all invisible or harmless in a vanilla renderer (Req 5.4). Charts
  are embedded as standard doc-relative image links
  ``![...](assets/<stem>-...svg)`` (Req 2.7, 5.5); there are no wikilinks and no
  plugin syntax.

Which regions exist and what a fresh one says are **not** decided here: the
``workout`` region id and both instructive placeholders -- the ``notes`` text
(Req 10.5) and the ``workout`` text (Req 9.5) -- come from
:mod:`fitdocs.contract`, which is also what the merge preserves and what the
published ownership contract names (wiki-contract Req 1.4). This module decides
only *where* each region sits in the document -- including
:data:`~fitdocs.contract.DOC_BANNER`, placed by :func:`_assemble` between the
frontmatter block and the H1, outside every preserved region, so it is
refreshed by every regeneration (Req 4.2-4.4).
"""

from __future__ import annotations

from fitdocs.contract import (
    DOC_BANNER,
    NOTES_PLACEHOLDER,
    WORKOUT_PLACEHOLDER,
    WORKOUT_REGION,
    region_block,
)
from fitdocs.render import Asset, DocContext, RenderedDoc
from fitdocs.render.frontmatter import build_frontmatter
from fitdocs.render.sections import (
    devices_section,
    hero_chart,
    hero_stats,
    load_section,
    map_section,
    notes_region,
    telemetry_chips,
    zone_strip,
)
from fitdocs.render.splits import splits_section
from fitdocs.render.strength import sets_section

__all__ = ["render_generic", "render_run_ride", "render_strength"]


def _title(ctx: DocContext) -> str:
    """The single H1 title: ``"<Sport> <YYYY-MM-DD> <HH:MM>"`` in local time.

    Mirrors the frontmatter ``title`` so the visible heading and the metadata
    agree. Degrades to ``"<Sport> <doc_stem>"`` when the activity recorded no
    start time -- always a non-empty, deterministic string, never a fabricated
    date.
    """
    sport = ctx.activity.sport.value
    start = ctx.activity.start_time
    if start is None:
        return f"{sport} {ctx.doc_stem}"
    local = start.astimezone(ctx.tz)
    return f"{sport} {local:%Y-%m-%d} {local:%H:%M}"


def _section(heading: str, body: str) -> str:
    """A ``## <heading>`` block over ``body`` (heading outside any region)."""
    return f"## {heading}\n\n{body}"


def _region_section(heading: str, region: str) -> str:
    """A ``## <heading>`` block whose body is a region (heading outside markers).

    ``region`` is a :func:`~fitdocs.docmerge.region_block` string; its trailing
    newline is dropped so the block joins uniformly with its neighbours while the
    end marker keeps its own line.
    """
    return f"## {heading}\n\n{region.rstrip(chr(10))}"


def _telemetry_body(ctx: DocContext) -> tuple[str, tuple[Asset, ...]] | None:
    """The ``## Telemetry`` body and its chart assets, or ``None`` when empty.

    Gathers the average chips line, the hero chart, and the HR-zone strip (each
    optional). Returns ``None`` -- so the caller omits the whole section -- when
    there is nothing to show (no chips, no chart, no zone strip). Assets are
    collected in a stable order (hero, then zones).
    """
    chips = telemetry_chips(ctx)
    hero = hero_chart(ctx)
    zones = zone_strip(ctx)

    parts: list[str] = []
    assets: list[Asset] = []
    if chips:
        parts.append(chips)
    if hero is not None:
        link, asset = hero
        parts.append(link)
        assets.append(asset)
    if zones is not None:
        link, asset = zones
        parts.append(link)
        assets.append(asset)

    if not parts:
        return None
    return "\n\n".join(parts), tuple(assets)


def _assemble(
    ctx: DocContext, blocks: list[str], assets: tuple[Asset, ...]
) -> RenderedDoc:
    """Join the frontmatter and body blocks into a complete :class:`RenderedDoc`.

    ``DOC_BANNER`` sits on its own line between the frontmatter block and the
    H1 title (``blocks[0]``), separated from the body by a blank line, so it
    sits outside every preserved region and is refreshed by every regeneration
    (Req 4.4). Blocks are joined with a blank line and the body is
    newline-terminated; identical inputs yield byte-identical output (Req 4.1).
    """
    body = "\n\n".join(blocks)
    markdown = f"{build_frontmatter(ctx)}\n{DOC_BANNER}\n\n{body}\n"
    return RenderedDoc(markdown=markdown, assets=assets)


def render_run_ride(ctx: DocContext) -> RenderedDoc:
    """Assemble a run/ride document (Req 6.1, route-maps 1.1, 1.2).

    Order: H1 → ``notes`` region → ``## Summary`` → ``## Map`` → ``## Telemetry``
    → ``## Splits`` → ``## Training Load`` → ``## Device & Data Quality``. The Map
    section sits immediately after Summary and before Telemetry, present only when
    the context carries prepared map inputs; its asset leads the assets tuple.
    The Map, Telemetry, and Splits sections are omitted when they would be empty.
    """
    blocks: list[str] = [
        f"# {_title(ctx)}",
        notes_region(NOTES_PLACEHOLDER).rstrip("\n"),
        _section("Summary", hero_stats(ctx)),
    ]

    assets: tuple[Asset, ...] = ()
    mapsec = map_section(ctx)
    if mapsec is not None:
        link, map_asset = mapsec
        blocks.append(_section("Map", link))
        assets = (map_asset,)

    telemetry = _telemetry_body(ctx)
    if telemetry is not None:
        body, tel_assets = telemetry
        blocks.append(_section("Telemetry", body))
        assets = assets + tel_assets

    splits = splits_section(ctx.activity, ctx.activity.modality)
    if splits:
        blocks.append(_section("Splits", splits))

    blocks.append(_region_section("Training Load", load_section()))
    blocks.append(_section("Device & Data Quality", devices_section(ctx)))
    return _assemble(ctx, blocks, assets)


def render_strength(ctx: DocContext) -> RenderedDoc:
    """Assemble a strength document (Req 9.1, 9.5, 9.6).

    Order: H1 → ``notes`` region → ``## Summary`` → ``## Telemetry`` (HR chart
    when plottable) → ``## Workout`` (workout region) → ``## Recorded Sets``
    (only when sets exist) → ``## Training Load`` → ``## Device & Data Quality``.
    """
    blocks: list[str] = [
        f"# {_title(ctx)}",
        notes_region(NOTES_PLACEHOLDER).rstrip("\n"),
        _section("Summary", hero_stats(ctx)),
    ]

    assets: tuple[Asset, ...] = ()
    telemetry = _telemetry_body(ctx)
    if telemetry is not None:
        body, assets = telemetry
        blocks.append(_section("Telemetry", body))

    workout = region_block(WORKOUT_REGION, WORKOUT_PLACEHOLDER)
    blocks.append(_region_section("Workout", workout))

    sets = sets_section(ctx.activity.sets)
    if sets:
        blocks.append(_section("Recorded Sets", sets))

    blocks.append(_region_section("Training Load", load_section()))
    blocks.append(_section("Device & Data Quality", devices_section(ctx)))
    return _assemble(ctx, blocks, assets)


def render_generic(ctx: DocContext) -> RenderedDoc:
    """Assemble the generic fallback document (Req 12.1, route-maps 1.1, 1.2).

    Order: H1 → ``notes`` region → ``## Summary`` → ``## Map`` → ``## Telemetry``
    (when plottable) → ``## Training Load`` → ``## Device & Data Quality``. The
    Map section sits immediately after Summary and before Telemetry, present only
    when the context carries prepared map inputs (its asset leads the assets
    tuple); it uses the neutral tint for these non-run/ride activities. No splits,
    workout, or sets sections -- those are modality-specific.
    """
    blocks: list[str] = [
        f"# {_title(ctx)}",
        notes_region(NOTES_PLACEHOLDER).rstrip("\n"),
        _section("Summary", hero_stats(ctx)),
    ]

    assets: tuple[Asset, ...] = ()
    mapsec = map_section(ctx)
    if mapsec is not None:
        link, map_asset = mapsec
        blocks.append(_section("Map", link))
        assets = (map_asset,)

    telemetry = _telemetry_body(ctx)
    if telemetry is not None:
        body, tel_assets = telemetry
        blocks.append(_section("Telemetry", body))
        assets = assets + tel_assets

    blocks.append(_region_section("Training Load", load_section()))
    blocks.append(_section("Device & Data Quality", devices_section(ctx)))
    return _assemble(ctx, blocks, assets)
