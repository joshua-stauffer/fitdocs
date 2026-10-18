"""The ``heatmap`` kind: a value over two band axes.

One cell per row at its ``x`` and ``y`` position, drawn by ``cells`` (a square
sized and shaded by the value's bin, an outlined square for zero, a cross for an
absent value). A position with no row draws nothing. Categories and booleans
take their first-appearance order, dates and numbers ascend, and an absent ``x``
or ``y`` forms a last band labelled with the em dash, so every row has a place
and no row is left undrawn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from fitdocs.render.charts.kit import cartesian, cells, frame
from fitdocs.render.charts.kit.data import Column, Value, ValueKind, to_number
from fitdocs.render.charts.kit.format import (
    ABSENT,
    axis_title,
    clean_text,
    format_duration,
    format_durations,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    TICK_GAP,
    TICK_LEN,
    FramePlan,
    Rect,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import BandScale, Side
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    KindSpec,
    MarkBound,
    Output,
    OverBound,
    svg_options,
)
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 1500
HEAT_X_LIMIT: Final = 60
HEAT_Y_LIMIT: Final = 40
HEAT_MIN_ROW: Final = 16.0
HEAT_MAX_ROW: Final = 32.0

_MIN_HEIGHT: Final = 160
_MAX_HEIGHT: Final = 1200
_PROBE_HEIGHT: Final = 1000
_LABEL_SHARE: Final = 0.4  # the left margin's share of the chart width
_LABEL_ROOM: Final = FONT_TEXT + 2  # a y label needs this much row pitch
_FIT_SLACK: Final = (
    1e-6  # frame.axis re-derives the room by subtraction; keep a label that fits
)
_LIMITS: Final = (("x", HEAT_X_LIMIT), ("y", HEAT_Y_LIMIT))
_ORDERED: Final = (ValueKind.DATE, ValueKind.NUMBER)
_AXIS_KINDS: Final = (
    ValueKind.CATEGORY,
    ValueKind.DATE,
    ValueKind.BOOLEAN,
    ValueKind.NUMBER,
)


@dataclass(frozen=True)
class _Bands:
    labels: tuple[str, ...]  # band order; the absent band, when any, is last
    of_row: tuple[int, ...]  # each row's band
    distinct: int  # present distinct values (the absent band is not one)
    title: str  # the axis title, in the labels' duration form when they are


def _bands(bound: BoundChart, channel: str) -> _Bands:
    column = bound.columns[channel]
    values = bound.values(channel)
    distinct: list[Value] = list(dict.fromkeys(v for v in values if v is not None))
    if column.kind in _ORDERED:
        distinct.sort(key=lambda v: to_number(v, column.kind) or 0.0)
    position = {value: index for index, value in enumerate(distinct)}
    if _is_duration(column):
        # one form per axis (A1), and the title names the form the labels use
        labels = list(
            format_durations([to_number(v, column.kind) or 0.0 for v in distinct])
        )
        hours = any(label.count(":") == 2 for label in labels)
    else:
        labels = [format_value(v, column, with_unit=False) for v in distinct]
        hours = True
    if any(v is None for v in values):
        labels.append(ABSENT)
    return _Bands(
        tuple(labels),
        tuple(len(distinct) if v is None else position[v] for v in values),
        len(distinct),
        axis_title(column, hours=hours),
    )


def _limit_problems(bound: BoundChart) -> tuple[ChartProblem, ...]:
    found: list[ChartProblem] = []
    for channel, limit in _LIMITS:
        count = _bands(bound, channel).distinct
        if count > limit:
            found.append(
                bound.problem(
                    ProblemCode.OVER_BOUND,
                    f"heatmap draws at most {limit} {channel} values; "
                    f"this data has {count}.",
                    f"Filter or group the {channel} column to at most {limit} values.",
                    channel=channel,
                    column=bound.columns[channel].name,
                )
            )
    return tuple(found)


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return (
        *cartesian.bound_problem(bound, len(bound.rows)),
        *_limit_problems(bound),
        *cartesian.duplicate_problem(bound, ("x", "y")),
        *cells.negative_problem(bound, "value"),
    )


def _is_duration(column: Column) -> bool:
    unit = None if column.unit is None else unit_named(column.unit)
    return column.kind is ValueKind.DURATION or (
        unit is not None and unit.family is UnitFamily.DURATION
    )


def _value_range(bound: BoundChart, scale: cells.BinnedScale) -> tuple[str, str] | None:
    """The smallest and largest present value, in the legend's duration form."""
    column = bound.columns["value"]
    values = bound.values("value")
    numeric = cartesian.numbers(bound, "value")
    present = [i for i, v in enumerate(numeric) if v is not None]
    if not present:
        return None
    lowest = min(present, key=lambda i: numeric[i] or 0.0)
    highest = max(present, key=lambda i: numeric[i] or 0.0)

    def shown(index: int) -> str:
        seconds = numeric[index]
        if _is_duration(column) and seconds is not None:
            return format_duration(seconds, hours=scale.zero_label.count(":") == 2)
        return format_value(values[index], column, with_unit=True)

    return shown(lowest), shown(highest)


def _y_scale(labels: tuple[str, ...], plot: Rect) -> BandScale:
    """Rows top to bottom; every row is labelled when its pitch holds a label,
    else every k-th from the first, with the smallest k that does."""
    pitch = plot.height / len(labels)
    k = 1
    while k < len(labels) and k * pitch < _LABEL_ROOM:
        k += 1
    return BandScale(labels, plot.top, plot.bottom, tuple(range(0, len(labels), k)))


def _draw(bound: BoundChart) -> str:
    width = bound.width
    if not bound.rows:
        return frame.no_data(
            bound, height=_MIN_HEIGHT if bound.height is None else bound.height
        )

    x_bands, y_bands = _bands(bound, "x"), _bands(bound, "y")
    value_col = bound.columns["value"]
    numeric = cartesian.numbers(bound, "value")
    scale = cells.binned_scale(numeric, value_col)
    entries = cells.legend_entries(
        scale,
        has_zero=any(v == 0 for v in numeric if v is not None),
        has_absent=any(v is None for v in numeric),
    )

    widest = max(text_width(clean_text(label), FONT_TEXT) for label in y_bands.labels)
    label_room = _LABEL_SHARE * width - PAD - TICK_GAP - TICK_LEN
    y_label_width = min(widest + _FIT_SLACK, label_room)

    def plan(height: int, label_width: float = y_label_width) -> FramePlan:
        return plan_frame(
            width,
            height,
            legend=entries,
            y_label_width=label_width,
            x_label_overhang=0.0,
            has_x_title=True,
            has_y_title=True,
            notes=0,
        )

    height = bound.height
    if height is None:
        probe = plan(_PROBE_HEIGHT)
        frame_px = _PROBE_HEIGHT - probe.plot.height
        pitch = min(
            max(probe.plot.width / len(x_bands.labels), HEAT_MIN_ROW), HEAT_MAX_ROW
        )
        height = min(
            _MAX_HEIGHT,
            max(_MIN_HEIGHT, math.ceil(len(y_bands.labels) * pitch + frame_px)),
        )
    final, x_axis = cartesian.band_x_axis(
        x_bands.labels, lambda label_width: plan(height, label_width), y_label_width
    )
    plot = final.plot
    y_axis = _y_scale(y_bands.labels, plot)

    placed: list[tuple[Rect, int | None]] = []
    for row, value in enumerate(numeric):
        left, right = x_axis.band(x_bands.of_row[row])
        top, bottom = y_axis.band(y_bands.of_row[row])
        rect = Rect(left, top, right - left, bottom - top)
        placed.append((rect, scale.classify(value)))

    x_title, y_title = x_bands.title, y_bands.title
    value_title = entries[0].label
    ranges = [
        (x_title, x_bands.labels[0], x_bands.labels[-1]),
        (y_title, y_bands.labels[0], y_bands.labels[-1]),
    ]
    extremes = _value_range(bound, scale)
    if extremes is not None:
        ranges.append((value_title, *extremes))
    description = frame.describe(
        "heatmap",
        bound.request.title,
        (("x", x_title), ("y", y_title), ("value", value_title)),
        rows=len(bound.rows),
        series=None,
        undrawn=(),
        ranges=ranges,
    )
    body = [
        el("g", {"class": "ck-marks"}, cells.cell_marks(placed, scale)),
        frame.axis(x_axis, plot, Side.BOTTOM, title=x_title, plan=final),
        frame.axis(y_axis, plot, Side.LEFT, title=y_title, plan=final),
        cells.legend(final, scale, entries),
        frame.title_text(final, bound.request.title),
    ]
    return frame.document(
        width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="heatmap",
    description=(
        "A grid of cells over two category, date, boolean or number axes, "
        "sized and shaded by a value of zero or more (negative values are "
        "refused); a position with no row draws nothing"
    ),
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            _AXIS_KINDS,
            True,
            "The column each cell sits in: a category, date, boolean or number.",
        ),
        ChannelSpec(
            "y",
            _AXIS_KINDS,
            True,
            "The row each cell sits in: a category, date, boolean or number.",
        ),
        ChannelSpec(
            "value",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The size and shade of each cell: a number or duration, zero or more.",
        ),
    ),
    options=svg_options(height=None),
    bound=MarkBound(
        _LIMIT,
        "cells",
        OverBound.REFUSE,
        f"At most {_LIMIT} cells, {HEAT_X_LIMIT} x values and {HEAT_Y_LIMIT} y values.",
    ),
    max_series=None,
    draw=_draw,
    check=_check,
)
