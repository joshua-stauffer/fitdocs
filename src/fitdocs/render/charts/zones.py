"""The HR time-in-zone strip as static, deterministic SVG (Req 8.1, 8.2).

This module renders the reference "HR-zone strip" of
``docs/reference/fitdocs-ai-reference.md`` section 3 as hand-built SVG text --
no matplotlib, no template engine, no scripts -- so a workout document shows how
the effort was distributed across heart-rate zones in any markdown renderer with
zero plugins.

Honest-zones contract (Req 8.2): this renderer draws *exactly* the
:class:`ZoneBand` values it is handed. Each band's ``seconds`` is the athlete's
real time-in-zone (computed upstream by fit-ingest from athlete-supplied
dividers, ``metrics.hr_time_in_zone_s``) and each band's ``color`` is chosen by
the caller from :mod:`fitdocs.render.charts.palette`. This module therefore
contains **no zone boundaries, no default colors, and no default zone count** --
it invents nothing. ``sections.py`` includes the strip only when
``hr_time_in_zone_s`` is available, so without computed zone times the caller
passes nothing and the strip does not exist: :func:`render_zone_strip` returns
the empty string for empty input (and, equivalently, for an all-zero total --
no time recorded in any zone is not zone data to display).

Layout (all constants below, in SVG user units; SVG y grows downward):

- **The proportional bar** (top): a horizontal stacked bar spanning the full
  width. Each band with positive time is one ``<rect>`` whose width is
  ``seconds / total`` of the strip width; segments tile left to right with no
  gaps and the last ends exactly at the right edge (boundaries are computed from
  cumulative seconds, so rounding never drifts). A zero-time band contributes no
  segment -- it occupies no proportional width.
- **The label row** (below the bar): every band -- zero-time included -- gets one
  entry in an evenly divided column (``width / len(bands)`` wide), so labels
  never overlap regardless of how skewed the proportions are. Each entry is a
  color swatch (tying the band's color to its label) plus a caption
  ``"<label> <h:mm> <pct>%"``. ``h:mm`` is the band's duration rounded to the
  nearest whole minute (e.g. ``3660 s -> "1:01"``); ``pct`` is its integer
  percentage of the total. A zero-time band therefore reads ``"Z5 0:00 0%"``.

Determinism (Req 4.1 by extension): identical ``bands`` -> byte-identical SVG.
Every coordinate is formatted through
:func:`~fitdocs.render.charts.svg.fmt_num`; nothing reads the clock or draws on
randomness, and no ids are generated. This module imports the standard library
plus sibling ``render.charts`` modules only -- never fit-ingest, never non-charts
``fitdocs``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fitdocs.render.charts.svg import el, fmt_num, svg_document, text

# --- public spec ------------------------------------------------------------


@dataclass(frozen=True)
class ZoneBand:
    """One heart-rate zone's time-in-zone, ready to render.

    ``label`` is the zone name (``"Z1"``..``"Zn"``). ``seconds`` is the
    athlete's real time-in-zone (``0`` is a genuine "no time in this zone", never
    a fabricated fill). ``color`` is a caller-supplied hex string picked from
    :mod:`fitdocs.render.charts.palette`. This dataclass carries no zone
    boundary and no default of any kind (Req 8.2).
    """

    label: str
    seconds: float
    color: str


# --- layout + style constants ----------------------------------------------

_BAR_TOP = 0.0
_BAR_HEIGHT = 14.0
_LABEL_PAD = 4.0
_SWATCH_SIZE = 10.0
_SWATCH_Y = 26.0
_SWATCH_TEXT_GAP = 4.0
_LABEL_BASELINE = 34.0
_LABEL_FONT_SIZE = "11"
_LABEL_TEXT_COLOR = "#333"


# --- rendering --------------------------------------------------------------


def render_zone_strip(
    bands: Sequence[ZoneBand],
    width: int = 800,
    height: int = 46,
) -> str:
    """Render ``bands`` as a proportional stacked HR-zone strip (Req 8.1, 8.2).

    The strip is a horizontal stacked bar: each band's segment width is
    proportional to its share of the total time, and every band gets a label +
    ``h:mm`` duration + percentage in the row beneath. Zero-time bands keep their
    label (at ``0:00`` / ``0%``) but occupy no proportional width.

    Returns the empty string when ``bands`` is empty or the total time is zero --
    the "no output without supplied zone times" contract (Req 8.1, 8.2): the
    renderer never invents a strip, boundaries, colors, or a zone count. Identical
    ``bands`` yield byte-identical output.
    """
    total = sum(band.seconds for band in bands)
    if not bands or total <= 0:
        return ""

    children = [
        _render_bar(bands, total, width),
        _render_labels(bands, total, width),
    ]
    return svg_document(width, height, children)


def _render_bar(bands: Sequence[ZoneBand], total: float, width: int) -> str:
    """The proportional stacked bar: one colored rect per positive-time band.

    Segment boundaries are computed from cumulative seconds mapped onto the strip
    width, so segments tile with no gaps and the final one ends exactly at
    ``width``. Zero-time bands contribute no rect (no proportional width).
    """
    segments: list[str] = []
    cumulative = 0.0
    for band in bands:
        left = cumulative / total * width
        cumulative += band.seconds
        right = cumulative / total * width
        segment_width = right - left
        if segment_width <= 0:
            continue
        segments.append(
            el(
                "rect",
                {
                    "class": "zone-seg",
                    "x": fmt_num(left),
                    "y": fmt_num(_BAR_TOP),
                    "width": fmt_num(segment_width),
                    "height": fmt_num(_BAR_HEIGHT),
                    "fill": band.color,
                },
            )
        )
    return el("g", {"class": "bar"}, segments)


def _render_labels(bands: Sequence[ZoneBand], total: float, width: int) -> str:
    """The label row: a swatch + ``"<label> <h:mm> <pct>%"`` per band.

    Bands are laid out in evenly divided columns (so labels never overlap and
    zero-time bands still appear); the swatch carries the band's color and the
    caption carries its label, duration, and percentage.
    """
    column_width = width / len(bands)
    items: list[str] = []
    for index, band in enumerate(bands):
        column_left = index * column_width
        swatch = el(
            "rect",
            {
                "class": "zone-swatch",
                "x": fmt_num(column_left + _LABEL_PAD),
                "y": fmt_num(_SWATCH_Y),
                "width": fmt_num(_SWATCH_SIZE),
                "height": fmt_num(_SWATCH_SIZE),
                "fill": band.color,
            },
        )
        caption = (
            f"{band.label} {_format_hmm(band.seconds)} "
            f"{_format_pct(band.seconds, total)}"
        )
        text_x = column_left + _LABEL_PAD + _SWATCH_SIZE + _SWATCH_TEXT_GAP
        label = el(
            "text",
            {
                "x": fmt_num(text_x),
                "y": fmt_num(_LABEL_BASELINE),
                "font-size": _LABEL_FONT_SIZE,
                "fill": _LABEL_TEXT_COLOR,
            },
            [text(caption)],
        )
        items.append(el("g", {"class": "zone-label"}, [swatch, label]))
    return el("g", {"class": "labels"}, items)


def _format_hmm(seconds: float) -> str:
    """Format a duration as ``h:mm``, rounded to the nearest whole minute.

    ``3660 s -> "1:01"``, ``3600 s -> "1:00"``, ``0 s -> "0:00"``. Minutes are
    always two digits; hours are unpadded and unbounded.
    """
    total_minutes = round(seconds / 60.0)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}"


def _format_pct(seconds: float, total: float) -> str:
    """Format ``seconds`` as an integer percentage of ``total`` (``total > 0``)."""
    return f"{round(seconds / total * 100)}%"
