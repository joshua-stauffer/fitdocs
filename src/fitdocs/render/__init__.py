"""Pure rendering layer for fitdocs workout documents.

This package turns the fit-ingest activity model into markdown documents and
static SVG chart assets. Rendering is pure -- strings and SVG text out, with no
file I/O (the sync engine owns all writes).

This module holds the shared render *contracts* every renderer consumes and
returns: :class:`DocContext` (the immutable render input -- activity, derived
metrics, optional athlete inputs, document stem, append-ordered source
references, timezone, and optional prepared map inputs), :class:`Asset` (a
doc-relative chart asset), :class:`RenderedDoc` (the rendered markdown plus its
assets), and :class:`MapData` (a route map's plan plus its resolved tiles,
carried across the purity boundary). All are frozen dataclasses so rendering
stays deterministic (Req 4.1).

The map planning types -- :class:`~fitdocs.render.charts.map.TileRef`,
:class:`~fitdocs.render.charts.map.MapPlan`, and
:func:`~fitdocs.render.charts.map.plan_map` -- are re-exported here so the sync
engine imports the whole map surface from ``fitdocs.render`` and never reaches
into chart internals (Req 1.1).

:func:`render_document` is the package's total dispatcher: it produces a
:class:`RenderedDoc` from a :class:`DocContext` by routing on the activity's
modality -- run/bike to the run/ride view, strength to the strength view, and
every other sport (swim, other, any degraded/unknown modality) to the generic
view. Dispatch is total and never raises on any sport (Req 12.2). The per-modality
assemblers live in :mod:`fitdocs.render.views`, imported lazily inside the
dispatcher so ``views`` can import these contract types from ``fitdocs.render``
without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import tzinfo

from fitdocs import Activity, AthleteInputs, DerivedMetrics, Modality

# Re-export the pure map planning surface (Req 1.1) so downstream callers -- the
# sync engine especially -- import map types from ``fitdocs.render`` rather than
# from ``fitdocs.render.charts.map``. ``charts.map`` depends only on sibling
# ``charts`` modules (``svg``/``series``/``palette``) and stdlib, so this
# module-level import introduces no cycle.
from fitdocs.render.charts.map import MapPlan, TileRef, plan_map

__all__ = [
    "Asset",
    "DocContext",
    "MapData",
    "MapPlan",
    "RenderedDoc",
    "TileRef",
    "plan_map",
    "render_document",
]


@dataclass(frozen=True)
class Asset:
    """A generated chart asset written alongside the document.

    :attr:`rel_path` is a POSIX path relative to the document's own directory,
    so moving the data root as a whole never breaks the link (Req 2.7).
    :attr:`content` is the asset's full text (SVG).
    """

    rel_path: str
    content: str


@dataclass(frozen=True)
class RenderedDoc:
    """The result of rendering one activity: the document plus its assets.

    :attr:`markdown` is the complete document -- YAML frontmatter, body, and all
    region markers. :attr:`assets` are the doc-relative chart assets to write
    (empty when the activity has no plottable telemetry).
    """

    markdown: str
    assets: tuple[Asset, ...]


@dataclass(frozen=True)
class MapData:
    """Prepared map inputs: the plan plus its resolved tiles, ready to compose.

    The impure sync engine plans the route (:func:`plan_map`), resolves the
    plan's exact tile set through the tile store, and freezes the result into
    this value before it crosses into the pure render layer -- so composition
    consumes only immutable, already-fetched inputs.

    :attr:`tiles` is ordered exactly as :attr:`MapPlan.tiles`; each ``bytes``
    payload is an immutable tile image. That ordering, together with the
    immutability, is what keeps warm-cache renders byte-identical (Req 4.1).
    """

    plan: MapPlan
    tiles: tuple[tuple[TileRef, bytes], ...]  # aligned with plan.tiles order
    attribution: str


@dataclass(frozen=True)
class DocContext:
    """The immutable input every renderer consumes.

    Rendering is a pure function of this context (Req 4.1): no I/O, no clock, no
    randomness. :attr:`doc_stem` drives asset filenames; :attr:`source_refs` are
    the append-ordered, data-root-relative archive references with the last
    entry being the current render source (Req 3.4, 3.6); :attr:`tz` is passed
    in explicitly (the CLI supplies the system local zone, tests pin a fixed
    one) so dates are user-correct yet deterministic. :attr:`map_data` carries
    prepared route-map inputs when the sync engine could plan and resolve them
    (Req 1.1); it defaults to ``None`` so every existing constructor call stays
    valid.
    """

    activity: Activity
    metrics: DerivedMetrics
    athlete: AthleteInputs | None
    doc_stem: str
    source_refs: tuple[str, ...]
    tz: tzinfo
    map_data: MapData | None = None  # None: no positions, tiles unavailable,
    #   or strength modality


def render_document(ctx: DocContext) -> RenderedDoc:
    """Render a complete workout document, dispatching on modality (Req 12.2).

    Total over :class:`~fitdocs.model.Modality`: ``RUN``/``BIKE`` render the
    run/ride view, ``STRENGTH`` the strength view, and everything else
    (``SWIM``, ``OTHER``, and any degraded/unknown modality) the generic
    fallback view -- so no successfully parsed activity is ever rejected for its
    sport (Req 12.1, 12.2, 6.1, 9.1). A pure function of ``ctx`` (Req 4.1): no
    I/O, no clock, no randomness.

    The per-modality assemblers are imported lazily here (not at module load) so
    :mod:`fitdocs.render.views` can import the contract types above from
    ``fitdocs.render`` without a circular import.
    """
    from fitdocs.render import views

    modality = ctx.activity.modality
    if modality is Modality.RUN or modality is Modality.BIKE:
        return views.render_run_ride(ctx)
    if modality is Modality.STRENGTH:
        return views.render_strength(ctx)
    return views.render_generic(ctx)
