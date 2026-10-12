"""The ``area`` kind: filled areas over a numeric or time x, optionally stacked.

Unstacked series are translucent fills to the zero line under their outlines;
stacked series are opaque bands, bottom to top in legend order. An absent ``y``
breaks a series (the fill and the outline), and the y axis always holds zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from fitdocs.render.charts.kit import frame, marks
from fitdocs.render.charts.kit.cartesian import (
    SeriesGroup,
    bound_problem,
    duplicate_problem,
    numbers,
    series_groups,
    series_problem,
    stack_problems,
    undrawn,
)
from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.format import axis_title, format_duration, format_value
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    FramePlan,
    LegendEntry,
    Rect,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.problems import ChartProblem
from fitdocs.render.charts.kit.scales import (
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
from fitdocs.render.charts.kit.theme import SeriesStyle
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 1000
_FILL_OPACITY: Final = "0.2"
_DEFAULT_HEIGHT: Final = 320


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    problems = (
        *bound_problem(bound, len(bound.rows)),
        *series_problem(bound),
        *duplicate_problem(bound, ("color", "x"), skip_absent=("x",)),
    )
    if bound.flag("stack"):
        problems += stack_problems(bound, x="x", y="y", complete=True)
    return problems


def _is_duration(column: Column) -> bool:
    unit = None if column.unit is None else unit_named(column.unit)
    return column.kind is ValueKind.DURATION or (
        unit is not None and unit.family is UnitFamily.DURATION
    )


def _extremes(
    bound: BoundChart, channel: str, rows: Sequence[int], scale: NumericScale
) -> tuple[str, str]:
    """The least and greatest present value of ``channel`` over ``rows``, as text."""
    column = scale.column
    values = bound.values(channel)
    figures = numbers(bound, channel)
    low = min(rows, key=lambda i: figures[i] or 0.0)
    high = max(rows, key=lambda i: figures[i] or 0.0)
    if _is_duration(column):
        # the same clock form as the axis, whatever each value would read alone
        return (
            format_duration(figures[low] or 0.0, hours=scale.hours),
            format_duration(figures[high] or 0.0, hours=scale.hours),
        )
    return (
        format_value(values[low], column, with_unit=True),
        format_value(values[high], column, with_unit=True),
    )


def _title_of(scale: NumericScale) -> str:
    return axis_title(scale.column, clock_date=scale.clock_date, hours=scale.hours)


def _overhangs(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    """How far the x tick labels reach past the plot's left and right edges."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - plot.right)
    return left, right


def _x_scale_type(column: Column) -> ScaleType:
    if column.kind in (ValueKind.DATE, ValueKind.DATETIME):
        return ScaleType.TIME
    return ScaleType.LINEAR


def _stack(
    groups: Sequence[SeriesGroup],
    xs: Sequence[float | None],
    ys: Sequence[float | None],
    union: Sequence[float],
) -> list[tuple[list[float], list[float]]]:
    """Per series, bottom to top: the lower and upper edge at every x of ``union``."""
    running = [0.0] * len(union)
    edges: list[tuple[list[float], list[float]]] = []
    for group in groups:
        at: dict[float, float] = {}
        for row in group.rows:
            x, y = xs[row], ys[row]
            if x is not None and y is not None:
                at[x] = y
        lower = list(running)
        running = [r + at[x] for r, x in zip(running, union, strict=True)]
        edges.append((lower, list(running)))
    return edges


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None
    x_col, y_col = bound.columns["x"], bound.columns["y"]
    xs, ys = numbers(bound, "x"), numbers(bound, "y")
    drawn = [
        i for i in range(len(bound.rows)) if xs[i] is not None and ys[i] is not None
    ]
    if not drawn:
        return frame.no_data(bound, height=height)

    stacked = bound.flag("stack")
    groups = series_groups(bound)
    union = sorted({x for i in drawn if (x := xs[i]) is not None})
    edges = _stack(groups, xs, ys, union) if stacked else []
    x_values = [x for i in drawn if (x := xs[i]) is not None]
    y_values = (
        [v for _, upper in edges for v in upper]
        if stacked
        else [y for i in drawn if (y := ys[i]) is not None]
    )

    legend = (
        [LegendEntry(g.label, g.style, "block" if stacked else "line") for g in groups]
        if bound.column("color") is not None
        else []
    )
    missing = undrawn(bound, ("x", "y"))
    note = frame.not_drawn_note(missing)
    lines = [] if note is None else [note]

    def plan(y_label_width: float, overhang: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=legend,
            y_label_width=y_label_width,
            x_label_overhang=overhang,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    def y_scale_of(frame_plan: FramePlan) -> NumericScale:
        return numeric_scale(
            y_values,
            y_col,
            frame_plan.plot.bottom,
            frame_plan.plot.top,
            scale=ScaleType.LINEAR,
            include_zero=True,
            nice=True,
            horizontal=False,
        )

    def x_scale_of(frame_plan: FramePlan) -> NumericScale:
        return numeric_scale(
            x_values,
            x_col,
            frame_plan.plot.left,
            frame_plan.plot.right,
            scale=_x_scale_type(x_col),
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    # The fixed layout passes: y ticks from the plot height; x ticks on the width
    # that leaves; then the final frame, whose left margin is the widest y label
    # plus the x labels' left overhang and whose right margin is the x labels'
    # right overhang past the plot; x ticks once more on the final width.
    first = plan(0.0, 0.0)
    y_scale = y_scale_of(first)
    y_label_width = max(text_width(t.label, FONT_TEXT) for t in y_scale.ticks)
    second = plan(y_label_width, 0.0)
    provisional = x_scale_of(second)
    left, right = _overhangs(provisional, second.plot)
    final = plan(y_label_width + left, right)
    x_scale = x_scale_of(final)

    baseline = y_scale.position(0.0)
    body_marks: list[str] = []
    if stacked:
        px = [x_scale.position(x) for x in union]
        for group, (lower, upper) in zip(groups, edges, strict=True):
            if len(union) < 2:
                break
            d = marks.band_path(
                px,
                [y_scale.position(v) for v in lower],
                [y_scale.position(v) for v in upper],
            )
            body_marks.append(el("path", {"d": d, "fill": group.style.color}))
        for group, (_, upper) in zip(groups, edges, strict=True):
            tops = [(x, y_scale.position(v)) for x, v in zip(px, upper, strict=True)]
            body_marks.extend(marks.line_series(tops, group.style))
    else:
        for group in groups:
            body_marks.extend(
                _unstacked(group.style, group.rows, xs, ys, x_scale, y_scale, baseline)
            )

    ranges = [
        (_title_of(x_scale), *_extremes(bound, "x", drawn, x_scale)),
        (_title_of(y_scale), *_extremes(bound, "y", drawn, y_scale)),
    ]
    description = frame.describe(
        "area",
        bound.request.title,
        [(name, col) for name, col in bound.columns.items()],
        rows=len(bound.rows),
        series=len(groups) if bound.column("color") is not None else None,
        undrawn=missing,
        ranges=ranges,
    )
    body = [
        frame.grid(y_scale, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, body_marks),
        frame.axis(x_scale, final.plot, Side.BOTTOM, plan=final),
        frame.axis(y_scale, final.plot, Side.LEFT, plan=final),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, lines),
    ]
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


def _unstacked(
    style: SeriesStyle,
    rows: Sequence[int],
    xs: Sequence[float | None],
    ys: Sequence[float | None],
    x_scale: NumericScale,
    y_scale: NumericScale,
    baseline: float,
) -> list[str]:
    placed = sorted((xs[i], ys[i]) for i in rows if xs[i] is not None)
    points = [
        (x_scale.position(x), None if y is None else y_scale.position(y))
        for x, y in placed
        if x is not None
    ]
    return marks.area_series(points, baseline, style, opacity=_FILL_OPACITY)


KIND: Final = KindSpec(
    name="area",
    description="Filled areas over a numeric or time x, optionally stacked",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (
                ValueKind.NUMBER,
                ValueKind.DURATION,
                ValueKind.DATE,
                ValueKind.DATETIME,
            ),
            True,
            "The horizontal position of each row.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The height of the area at each row.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One series per distinct value.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "stack",
            OptionType.BOOLEAN,
            "Stack the series in legend order instead of overlaying them.",
            False,
        ),
        height=_DEFAULT_HEIGHT,
    ),
    bound=MarkBound(
        _LIMIT,
        "rows",
        OverBound.REFUSE,
        "An area chart draws at most 1000 rows; more are refused.",
    ),
    max_series=8,
    draw=_draw,
    check=_check,
)
