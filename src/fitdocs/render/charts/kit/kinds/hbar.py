"""The ``hbar`` kind: one horizontal bar per row, ranked by value.

Rows are drawn top to bottom, 16 px bars on 26 px rows. ``sort: value`` ranks
by ``x`` descending with ties in row order and absent ``x`` last; ``sort:
rows`` keeps the row order. Under either order the rows whose ``y`` is absent
follow all others, labelled with the em dash. Every row is labelled: the row
labels are a band axis built here, never thinned by row height.
"""

from __future__ import annotations

import math
from typing import Final

from fitdocs.render.charts.kit import cartesian, frame, marks
from fitdocs.render.charts.kit.data import Column, Value, ValueKind, to_number
from fitdocs.render.charts.kit.format import (
    ABSENT,
    axis_title,
    clean_text,
    format_duration,
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
from fitdocs.render.charts.kit.problems import ChartProblem
from fitdocs.render.charts.kit.scales import (
    BandScale,
    NumericScale,
    ScaleType,
    Side,
    numeric_scale,
)
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
    svg_options,
)
from fitdocs.render.charts.kit.theme import TEXT, ink, series_style
from fitdocs.render.charts.svg import el, fmt_num, text
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 50
_ROW: Final = 26.0
_BAR: Final = 16.0
_MIN_HEIGHT: Final = 160
_STUB_WIDTH: Final = 2.0
_LABEL_GAP: Final = 4.0  # between a bar end (or the zero line) and its value label
_LABEL_DROP: Final = 4.0  # a label's baseline below its row centre
_LABEL_SHARE: Final = 0.4  # the left margin's share of the chart width
_PROBE_HEIGHT: Final = 1000
_FIT_SLACK: Final = (
    1e-6  # frame.axis re-derives the room by subtraction; keep a label that fits
)


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return cartesian.bound_problem(bound, len(bound.rows)) + (
        cartesian.duplicate_problem(bound, ("y",), skip_absent=("y",))
    )


def _order(bound: BoundChart) -> list[int]:
    """Row indices top to bottom; ``sorted`` is stable, so ties keep row order."""
    y_absent = [v is None for v in bound.values("y")]
    if bound.choice("sort") == "rows":
        return sorted(range(len(bound.rows)), key=lambda i: y_absent[i])
    xs = cartesian.numbers(bound, "x")

    def rank(i: int) -> tuple[bool, bool, float]:
        x = xs[i]
        return (y_absent[i], x is None, 0.0 if x is None else -x)

    return sorted(range(len(bound.rows)), key=rank)


def _overhangs(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    """How far the x tick labels reach past the plot's left and right edges."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - plot.right)
    return left, right


def _auto_height(rows: int, width: int) -> int:
    probe = plan_frame(
        width,
        _PROBE_HEIGHT,
        legend=(),
        y_label_width=0.0,
        x_label_overhang=0.0,
        has_x_title=True,
        has_y_title=True,
        notes=0,
    )
    frame_px = _PROBE_HEIGHT - probe.plot.height
    return max(_MIN_HEIGHT, math.ceil(rows * _ROW + frame_px))


def _label_attrs(x: float, y: float) -> dict[str, str]:
    attrs = {"x": fmt_num(x), "y": fmt_num(y), "font-size": fmt_num(FONT_TEXT)}
    attrs.update(ink(TEXT))
    return attrs


def _draw(bound: BoundChart) -> str:
    y_col, x_col = bound.columns["y"], bound.columns["x"]
    width = bound.width
    rows = len(bound.rows)
    x_values = bound.values("x")
    xs = cartesian.numbers(bound, "x")
    present = [v for v in xs if v is not None]
    if not present:
        return frame.no_data(
            bound, height=_MIN_HEIGHT if bound.height is None else bound.height
        )
    height = _auto_height(rows, width) if bound.height is None else bound.height

    order = _order(bound)
    y_values = bound.values("y")
    row_labels = tuple(
        ABSENT
        if y_values[i] is None
        else format_value(y_values[i], y_col, with_unit=False)
        for i in order
    )
    value_texts = [format_value(x_values[i], x_col, with_unit=False) for i in order]

    widest = max(text_width(clean_text(label), FONT_TEXT) for label in row_labels)
    label_room = _LABEL_SHARE * width - PAD - TICK_GAP - TICK_LEN
    y_label_width = min(widest + _FIT_SLACK, label_room)
    value_room = max(text_width(t, FONT_TEXT) for t in value_texts) + _LABEL_GAP

    def plan(label_width: float, overhang: float) -> FramePlan:
        return plan_frame(
            width,
            height,
            legend=(),
            y_label_width=label_width,
            x_label_overhang=overhang,
            has_x_title=True,
            has_y_title=True,
            notes=0,
            right_label_width=value_room,
        )

    def x_axis(p: FramePlan) -> NumericScale:
        return numeric_scale(
            present,
            x_col,
            p.plot.left,
            p.plot.right,
            scale=ScaleType.LINEAR,
            include_zero=True,
            nice=True,
            horizontal=True,
        )

    provisional = plan(y_label_width, 0.0)
    left, right = _overhangs(x_axis(provisional), provisional.plot)
    frame_plan = plan(y_label_width + left, right)
    scale = x_axis(frame_plan)
    plot = frame_plan.plot

    band = plot.height / rows
    bar_height = min(_BAR, band * _BAR / _ROW)
    zero = scale.position(0.0)
    color = series_style(0).color

    bars: list[str] = []
    labels: list[str] = []
    for position, index in enumerate(order):
        top = plot.top + position * band
        bar_top = top + (band - bar_height) / 2
        value = xs[index]
        label_x = zero + _LABEL_GAP
        if value is not None:
            if value == 0:
                bars.append(
                    marks.bar(
                        zero - _STUB_WIDTH / 2,
                        bar_top + bar_height,
                        _STUB_WIDTH,
                        bar_height,
                        color,
                    )
                )
            else:
                length = scale.position(value) - zero
                bars.append(
                    marks.bar(zero, bar_top + bar_height, length, bar_height, color)
                )
                if length > 0:
                    label_x = zero + length + _LABEL_GAP
        labels.append(
            el(
                "text",
                _label_attrs(label_x, top + band / 2 + _LABEL_DROP),
                [text(value_texts[position])],
            )
        )

    band_scale = BandScale(row_labels, plot.top, plot.bottom, tuple(range(rows)))
    low = min(
        (v for v in x_values if v is not None), key=lambda v: _number(v, x_col.kind)
    )
    high = max(
        (v for v in x_values if v is not None), key=lambda v: _number(v, x_col.kind)
    )
    x_title = axis_title(x_col, clock_date=scale.clock_date, hours=scale.hours)
    description = frame.describe(
        "hbar",
        bound.request.title,
        (("y", axis_title(y_col)), ("x", x_title)),
        rows=rows,
        series=None,
        undrawn=(),
        ranges=(
            (
                x_title,
                _range_text(low, x_col, scale.hours),
                _range_text(high, x_col, scale.hours),
            ),
        ),
    )
    body = [
        frame.grid(scale, plot, horizontal_lines=False),
        el("g", {"class": "ck-marks"}, bars),
        el("g", {"class": "ck-values"}, labels),
        frame.axis(
            band_scale, plot, Side.LEFT, title=axis_title(y_col), plan=frame_plan
        ),
        frame.axis(scale, plot, Side.BOTTOM, plan=frame_plan),
        frame.title_text(frame_plan, bound.request.title),
    ]
    return frame.document(
        width,
        height,
        title=bound.request.title,
        description=description,
        body=body,
    )


def _range_text(value: Value, column: Column, hours: bool) -> str:
    """A range end; a duration uses the same form as its axis title."""
    unit = None if column.unit is None else unit_named(column.unit)
    if column.kind is ValueKind.DURATION or (
        unit is not None and unit.family is UnitFamily.DURATION
    ):
        number = to_number(value, column.kind)
        assert number is not None
        return format_duration(number, hours=hours)
    return format_value(value, column, with_unit=True)


def _number(value: Value, kind: ValueKind) -> float:
    number = to_number(value, kind)
    assert number is not None
    return number


KIND: Final = KindSpec(
    name="hbar",
    description="Horizontal bars, one per row, ranked by value",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "y",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The label of each bar.",
        ),
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The length of each bar.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "sort",
            OptionType.CHOICE,
            "Rank the bars by value, or keep the row order.",
            "value",
            choices=("value", "rows"),
        ),
        height=None,
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, f"At most {_LIMIT} rows; more are refused."
    ),
    max_series=None,
    draw=_draw,
    check=_check,
)
