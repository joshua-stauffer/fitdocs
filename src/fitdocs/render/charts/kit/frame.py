"""Every non-mark element of an SVG chart, and the no-data state (chart-kit
Req 7.1, 7.2, 8.1, 8.3, 8.5, 9.3, 9.6, 9.7, 10.1-10.3).

The root, metadata, gridlines, axes, legend, title and notes, each in its own
group, plus the descriptions. Every ``<text>`` carries ``ink(TEXT)`` and every
stroked grid or axis element ``ink(STROKE)``; every coordinate goes through
``fmt_num``. The legend's shape swatch is drawn by ``theme.shape_path``, the
one marker geometry, so this module never needs ``marks``.

Layout choices this module makes within the plan's rows and columns: the left
axis title sits at the plot's left edge on the plan's y-title row (a right axis
title ends at the plot's right edge on the same row); legend text sits 11 px
below its row top, which keeps the top y tick label (4 px below its tick) a full
line (11 px) clear of the last legend row when the plot abuts it.
"""

from __future__ import annotations

from collections.abc import Sequence

from fitdocs.render.charts.kit.data import Column
from fitdocs.render.charts.kit.format import axis_title, clean_text
from fitdocs.render.charts.kit.layout import (
    FONT_NO_DATA,
    FONT_TEXT,
    FONT_TITLE,
    LEGEND_GAP,
    LEGEND_ROW,
    LEGEND_SWATCH,
    PAD,
    TICK_GAP,
    TICK_LEN,
    FramePlan,
    Rect,
    fit_text,
    plan_frame,
)
from fitdocs.render.charts.kit.scales import BandScale, NumericScale, Side
from fitdocs.render.charts.kit.schema import BoundChart
from fitdocs.render.charts.kit.theme import (
    GRID_OPACITY,
    STROKE,
    TEXT,
    InkRole,
    ink,
    shape_path,
    style_element,
)
from fitdocs.render.charts.svg import SVG_NAMESPACE, el, fmt_num, text

_LEGEND_TEXT_DROP = 11.0  # legend text baseline below its row top
_LEGEND_MID = 7.0  # swatch centre below the row top
_LEGEND_LINE_WIDTH = "1.8"
_BLOCK = 10.0
_LABEL_DROP = 4.0  # a left/right tick label's baseline below its tick
_NO_DATA_LINE = 18.0
_BAND_MARGIN = 4.0  # scales' band-label margin


# ------------------------------------------------------------------ helpers


def _text(
    x: float, y: float, content: str, *, size: float, anchor: str | None = None
) -> str:
    attrs = {"x": fmt_num(x), "y": fmt_num(y)}
    if anchor is not None:
        attrs["text-anchor"] = anchor
    attrs["font-size"] = fmt_num(size)
    attrs.update(ink(TEXT))
    return el("text", attrs, [text(content)])


def _line(
    x1: float, y1: float, x2: float, y2: float, *, opacity: str | None = None
) -> str:
    attrs = {
        "x1": fmt_num(x1),
        "y1": fmt_num(y1),
        "x2": fmt_num(x2),
        "y2": fmt_num(y2),
    }
    attrs.update(ink(STROKE))
    if opacity is not None:
        attrs["stroke-opacity"] = opacity
    return el("line", attrs)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


# ------------------------------------------------------------------ wording


def not_drawn_note(counts: Sequence[tuple[str, int]]) -> str | None:
    """``Not drawn: 1 row without y.`` / ``Not drawn: 3 rows without x, 2 rows
    without y.`` over the non-zero counts in the given order; ``None`` when
    every count is zero."""
    parts = [f"{_count(n, 'row')} without {ch}" for ch, n in counts if n]
    if not parts:
        return None
    return f"Not drawn: {', '.join(parts)}."


def no_trend_note(series: Sequence[str]) -> str:
    """``No trend line for Bike, Swim: fewer than 2 distinct x values.``"""
    if not series:
        raise ValueError("a no-trend note needs at least one series")
    return f"No trend line for {', '.join(series)}: fewer than 2 distinct x values."


def describe(
    kind: str,
    title: str,
    channels: Sequence[tuple[str, Column | str]],
    *,
    rows: int,
    series: int | None,
    undrawn: Sequence[tuple[str, int]],
    ranges: Sequence[tuple[str, str, str]],
) -> str:
    """The chart's description, one paragraph.

    No rows, or rows but no ``ranges`` (nothing was drawable), give the two
    no-data forms; ``channels``, ``series`` and ``undrawn`` are then unused.
    A channel is ``(name, Column)`` (titled by default) or ``(name, str)``, the
    drawn axis title used verbatim after ``clean_text``.
    """
    head = f"{kind[:1].upper()}{kind[1:]} chart: {clean_text(title)}."
    if rows == 0:
        return f"{head} No data: no rows."
    if not ranges:
        return f"{head} No data: none of the {_count(rows, 'row')} has a value to draw."
    parts = [head]
    if channels:
        parts.append(
            "; ".join(
                f"{ch}: {clean_text(col) if isinstance(col, str) else axis_title(col)}"
                for ch, col in channels
            )
            + "."
        )
    count = _count(rows, "row")
    if series is not None:
        count += f", {series} series"
    parts.append(count + ".")
    note = not_drawn_note(undrawn)
    if note is not None:
        parts.append(note)
    parts.append("; ".join(f"{a} from {lo} to {hi}" for a, lo, hi in ranges) + ".")
    return " ".join(parts)


# ----------------------------------------------------------------- document


def document(
    width: int,
    height: int,
    *,
    title: str,
    description: str,
    body: Sequence[str],
    extra_roles: tuple[InkRole, ...] = (),
) -> str:
    """The root ``<svg>``: ``<title>``, ``<desc>``, the style element, ``body``."""
    attrs = {
        "xmlns": SVG_NAMESPACE,
        "width": str(width),
        "height": str(height),
        "viewBox": f"0 0 {width} {height}",
        "role": "img",
        "font-family": "sans-serif",
    }
    children = [
        el("title", {}, [text(clean_text(title))]),
        el("desc", {}, [text(clean_text(description))]),
        el("style", {}, [style_element(extra_roles)]),
        *body,
    ]
    return el("svg", attrs, children)


def title_text(plan: FramePlan, title: str) -> str:
    shown = fit_text(clean_text(title), plan.width - 2 * PAD, FONT_TITLE)
    return _text(PAD, plan.title_y, shown, size=FONT_TITLE)


# --------------------------------------------------------------------- grid


def grid(scale: NumericScale, plot: Rect, *, horizontal_lines: bool) -> str:
    """Light gridlines at the scale's ticks, across (or down) the plot."""
    lines: list[str] = []
    for tick in scale.ticks:
        at = scale.position(tick.value)
        if horizontal_lines:
            lines.append(_line(plot.left, at, plot.right, at, opacity=GRID_OPACITY))
        else:
            lines.append(_line(at, plot.top, at, plot.bottom, opacity=GRID_OPACITY))
    return el("g", {"class": "ck-grid"}, lines)


# --------------------------------------------------------------------- axis


def _capped(room: float, cap: float | None) -> float:
    return room if cap is None else min(room, cap)


def band_label_room(scale: BandScale) -> float:
    """The width a bottom band label may take: the labelled bands' pitch less a
    margin (the room before the canvas edge also clamps it, in :func:`axis`)."""
    gap = (
        scale.labelled[1] - scale.labelled[0]
        if len(scale.labelled) > 1
        else len(scale.categories)
    )
    lo, hi = scale.band(0)
    return gap * (hi - lo) - _BAND_MARGIN


def axis(
    scale: NumericScale | BandScale,
    plot: Rect,
    side: Side,
    *,
    title: str | None = None,
    plan: FramePlan,
    title_room: float | None = None,
) -> str:
    """One axis: baseline, tick marks, tick labels, then its title.

    ``title=None`` derives the title from a ``NumericScale``'s column
    (``axis_title`` with the scale's ``clock_date`` and ``hours``); a string is
    used exactly as given and ``""`` draws no title. A ``BandScale`` has no
    column, so its ``title`` must be given. A title is drawn only where the
    plan has a row for it. Each title is fitted to the room at its own anchor,
    or to ``title_room`` when that is narrower: a chart drawing a left and a
    right axis passes each side its share of the shared y-title row.
    """
    if isinstance(scale, NumericScale):
        marks = [(scale.position(t.value), t.label) for t in scale.ticks]
        if title is None:
            title = axis_title(
                scale.column, clock_date=scale.clock_date, hours=scale.hours
            )
    else:
        marks = [(scale.centre(i), scale.categories[i]) for i in scale.labelled]
        if title is None:
            raise ValueError("a band axis needs a title (or '' for none)")
    shown = clean_text(title)

    ticks: list[str] = []
    labels: list[str] = []
    if side is Side.BOTTOM:
        baseline = _line(plot.left, plot.bottom, plot.right, plot.bottom)
        centre = plot.left + plot.width / 2
        room = band_label_room(scale) if isinstance(scale, BandScale) else 0.0
        for at, label in marks:
            ticks.append(_line(at, plot.bottom, at, plot.bottom + TICK_LEN))
            shown_label = (
                label
                if isinstance(scale, NumericScale)
                else fit_text(
                    clean_text(label),
                    min(room, 2 * min(at - PAD, plan.width - PAD - at)),
                    FONT_TEXT,
                )
            )
            labels.append(
                _text(at, plan.x_labels_y, shown_label, size=FONT_TEXT, anchor="middle")
            )
        title_el = (
            None
            if plan.x_title_y is None or not shown
            else _text(
                centre,
                plan.x_title_y,
                fit_text(
                    shown,
                    _capped(
                        2 * min(centre - PAD, plan.width - PAD - centre), title_room
                    ),
                    FONT_TEXT,
                ),
                size=FONT_TEXT,
                anchor="middle",
            )
        )
    else:
        left = side is Side.LEFT
        edge = plot.left if left else plot.right
        step = -1.0 if left else 1.0
        room = (
            plot.left - TICK_LEN - TICK_GAP - PAD
            if left
            else (plan.width - plot.right - TICK_LEN - TICK_GAP - PAD)
        )
        baseline = _line(edge, plot.top, edge, plot.bottom)
        for at, label in marks:
            ticks.append(_line(edge, at, edge + step * TICK_LEN, at))
            shown_label = (
                label
                if isinstance(scale, NumericScale)
                else fit_text(clean_text(label), room, FONT_TEXT)
            )
            labels.append(
                _text(
                    edge + step * (TICK_LEN + TICK_GAP),
                    at + _LABEL_DROP,
                    shown_label,
                    size=FONT_TEXT,
                    anchor="end" if left else "start",
                )
            )
        anchor_room = plan.width - PAD - plot.left if left else plot.right - PAD
        title_el = (
            None
            if plan.y_title_y is None or not shown
            else _text(
                edge,
                plan.y_title_y,
                fit_text(shown, _capped(anchor_room, title_room), FONT_TEXT),
                size=FONT_TEXT,
                anchor="start" if left else "end",
            )
        )
    children = [baseline, *ticks, *labels]
    if title_el is not None:
        children.append(title_el)
    return el("g", {"class": "ck-axis"}, children)


# ------------------------------------------------------------------- legend


def legend(plan: FramePlan) -> str:
    """The legend rows of the plan; empty text when the plan has none."""
    if not plan.legend_rows:
        return ""
    items: list[str] = []
    for r, row in enumerate(plan.legend_rows):
        top = plan.legend_top + r * LEGEND_ROW
        mid = top + _LEGEND_MID
        for entry, x in row:
            style = entry.style
            if entry.swatch == "line":
                attrs = {
                    "x1": fmt_num(x),
                    "y1": fmt_num(mid),
                    "x2": fmt_num(x + LEGEND_SWATCH),
                    "y2": fmt_num(mid),
                    "stroke": style.color,
                    "stroke-width": _LEGEND_LINE_WIDTH,
                }
                if style.dash is not None:
                    attrs["stroke-dasharray"] = style.dash
                items.append(el("line", attrs))
            elif entry.swatch == "shape":
                items.append(
                    shape_path(style.shape, [(x + LEGEND_SWATCH / 2, mid)], style.color)
                )
            else:
                items.append(
                    el(
                        "rect",
                        {
                            "x": fmt_num(x + (LEGEND_SWATCH - _BLOCK) / 2),
                            "y": fmt_num(mid - _BLOCK / 2),
                            "width": fmt_num(_BLOCK),
                            "height": fmt_num(_BLOCK),
                            "fill": style.color,
                        },
                    )
                )
            items.append(
                _text(
                    x + LEGEND_SWATCH + LEGEND_GAP,
                    top + _LEGEND_TEXT_DROP,
                    clean_text(entry.label),
                    size=FONT_TEXT,
                )
            )
    return el("g", {"class": "ck-legend"}, items)


# -------------------------------------------------------------------- notes


def notes(plan: FramePlan, lines: Sequence[str]) -> str:
    """One text line per note at the plan's note rows, fitted to the width.

    The number of lines must equal the number of note rows the plan reserved;
    empty text when there are none.
    """
    if len(lines) != len(plan.notes_y):
        raise ValueError(
            f"{len(lines)} note lines for {len(plan.notes_y)} reserved rows"
        )
    if not lines:
        return ""
    room = plan.width - 2 * PAD
    rows = [
        _text(PAD, y, fit_text(clean_text(line), room, FONT_TEXT), size=FONT_TEXT)
        for y, line in zip(plan.notes_y, lines, strict=True)
    ]
    return el("g", {"class": "ck-notes"}, rows)


# ------------------------------------------------------------------ no data


def no_data(bound: BoundChart, *, height: int) -> str:
    """The whole no-data chart at the chart's width and the given ``height``."""
    width = bound.width
    title = bound.request.title
    count = len(bound.rows)
    plan = plan_frame(
        width,
        height,
        legend=(),
        y_label_width=0.0,
        x_label_overhang=0.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    middle = height / 2
    body = [
        title_text(plan, title),
        _text(width / 2, middle, "No data", size=FONT_NO_DATA, anchor="middle"),
    ]
    if count:
        body.append(
            _text(
                width / 2,
                middle + _NO_DATA_LINE,
                fit_text(
                    f"None of the {_count(count, 'row')} has a value to draw.",
                    width - 2 * PAD,
                    FONT_TEXT,
                ),
                size=FONT_TEXT,
                anchor="middle",
            )
        )
    description = describe(
        bound.spec.name,
        title,
        (),
        rows=count,
        series=None,
        undrawn=(),
        ranges=(),
    )
    return document(width, height, title=title, description=description, body=body)
