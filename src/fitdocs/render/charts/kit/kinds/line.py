"""The ``line`` kind: one polyline per colour value over a numeric or time x.

Each series is joined in ascending x order and split wherever its y is absent,
so a gap is never bridged and a point with no present neighbour is a dot. A row
without an x or a y leaves no mark and is counted in the chart's note and
description. The x axis keeps the exact data extent; the y axis is niced.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from fitdocs.render.charts.kit import frame
from fitdocs.render.charts.kit.cartesian import (
    bound_problem,
    duplicate_problem,
    log_problem,
    numbers,
    series_groups,
    series_problem,
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
from fitdocs.render.charts.kit.marks import line_series
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import (
    NumericScale,
    ScaleType,
    Side,
    numeric_scale,
)
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    BoundRequest,
    ChannelSpec,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
    svg_options,
)
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 2000
_DEFAULT_HEIGHT: Final = 320
_TIME_KINDS: Final = (ValueKind.DATE, ValueKind.DATETIME)


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    x = bound.column("x")
    if x is None or x.kind not in _TIME_KINDS or bound.choice("x_scale") != "log":
        return ()
    return (
        bound.problem(
            ProblemCode.OPTION_CONFLICT,
            f"Option x_scale cannot be log for column '{x.name}': it is a "
            f"{x.kind.value} column, and a logarithmic scale applies to number and "
            "duration columns only.",
            "Set x_scale to linear.",
            channel="x",
            column=x.name,
            option="x_scale",
        ),
    )


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    problems = [
        *bound_problem(bound, len(bound.rows)),
        *series_problem(bound),
        *duplicate_problem(bound, ("color", "x"), skip_absent=("x",)),
    ]
    for channel in ("x", "y"):
        if bound.choice(f"{channel}_scale") == "log":
            problems.extend(log_problem(bound, channel))
    return tuple(problems)


def _scale_type(bound: BoundChart, option: str) -> ScaleType:
    return ScaleType(bound.choice(option))


def _overhangs(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    """How far the x tick labels reach past the plot's left and right edges."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - plot.right)
    return left, right


def _is_duration(column: Column) -> bool:
    if column.kind is ValueKind.DURATION:
        return True
    unit = None if column.unit is None else unit_named(column.unit)
    return unit is not None and unit.family is UnitFamily.DURATION


def _extremes(
    bound: BoundChart, channel: str, rows: Sequence[int], scale: NumericScale
) -> tuple[str, str]:
    """The smallest and largest present value of ``channel`` in ``rows``.

    A duration axis writes them in the axis's own form (``scale.hours``);
    any other axis writes them with the column's unit.
    """
    column = bound.columns[channel]
    values = bound.values(channel)
    numeric = numbers(bound, channel)
    lowest = min(rows, key=lambda i: numeric[i] or 0.0)
    highest = max(rows, key=lambda i: numeric[i] or 0.0)

    def shown(index: int) -> str:
        seconds = numeric[index]
        if _is_duration(column) and seconds is not None:
            return format_duration(seconds, hours=scale.hours)
        return format_value(values[index], column, with_unit=True)

    return shown(lowest), shown(highest)


def _axis_title(scale: NumericScale) -> str:
    return axis_title(scale.column, clock_date=scale.clock_date, hours=scale.hours)


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "line declares a default height"
    xs = numbers(bound, "x")
    ys = numbers(bound, "y")
    rows = [
        i for i in range(len(bound.rows)) if xs[i] is not None and ys[i] is not None
    ]
    if not rows:
        return frame.no_data(bound, height=height)

    x_col, y_col = bound.columns["x"], bound.columns["y"]
    groups = series_groups(bound)
    coloured = bound.column("color") is not None
    legend = (
        [LegendEntry(group.label, group.style, "line") for group in groups]
        if coloured
        else []
    )
    counts = undrawn(bound, ("x", "y"))
    note = frame.not_drawn_note(counts)
    lines = [] if note is None else [note]
    x_present = [x for i in rows if (x := xs[i]) is not None]
    y_present = [y for i in rows if (y := ys[i]) is not None]

    def plan(y_label_width: float, x_label_overhang: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=legend,
            y_label_width=y_label_width,
            x_label_overhang=x_label_overhang,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    first = plan(0.0, 0.0)
    y_scale = numeric_scale(
        y_present,
        y_col,
        first.plot.bottom,
        first.plot.top,
        scale=_scale_type(bound, "y_scale"),
        include_zero=bound.flag("y_zero"),
        nice=True,
        horizontal=False,
    )
    label_width = max(
        (text_width(t.label, FONT_TEXT) for t in y_scale.ticks), default=0.0
    )

    def x_axis(plot: Rect) -> NumericScale:
        return numeric_scale(
            x_present,
            x_col,
            plot.left,
            plot.right,
            scale=_scale_type(bound, "x_scale"),
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    provisional = plan(label_width, 0.0)
    left, right = _overhangs(x_axis(provisional.plot), provisional.plot)
    final = plan(label_width + left, right)
    x_scale = x_axis(final.plot)

    marks: list[str] = []
    for group in groups:
        points = sorted(
            ((x, ys[i]) for i in group.rows if (x := xs[i]) is not None),
            key=lambda p: p[0],
        )
        pixels = [
            (x_scale.position(x), None if y is None else y_scale.position(y))
            for x, y in points
        ]
        marks.extend(line_series(pixels, group.style))

    body = [
        frame.grid(y_scale, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, marks),
        frame.axis(x_scale, final.plot, Side.BOTTOM, plan=final),
        frame.axis(y_scale, final.plot, Side.LEFT, plan=final),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, lines),
    ]
    x_low, x_high = _extremes(bound, "x", rows, x_scale)
    y_low, y_high = _extremes(bound, "y", rows, y_scale)
    drawn_titles = {"x": _axis_title(x_scale), "y": _axis_title(y_scale)}
    channels = [
        (name, drawn_titles.get(name, column)) for name, column in bound.columns.items()
    ]
    description = frame.describe(
        "line",
        bound.request.title,
        channels,
        rows=len(bound.rows),
        series=len(groups) if coloured else None,
        undrawn=counts,
        ranges=[
            (_axis_title(x_scale), x_low, x_high),
            (_axis_title(y_scale), y_low, y_high),
        ],
    )
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="line",
    description="Lines over a numeric or time x, one per colour value",
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
            "The horizontal position: a number, duration, date or date-time.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The vertical value: a number or duration.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One line per value of this column.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "x_scale",
            OptionType.CHOICE,
            "The x axis scale; log needs a number or duration x.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "y_scale",
            OptionType.CHOICE,
            "The y axis scale; log needs values above zero.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the y axis to include zero.",
            False,
        ),
        height=_DEFAULT_HEIGHT,
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, "At most 2000 rows; more are refused."
    ),
    max_series=8,
    draw=_draw,
    validate=_validate,
    check=_check,
)
