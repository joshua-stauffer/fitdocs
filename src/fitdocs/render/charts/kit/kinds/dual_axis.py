"""The ``dual-axis`` kind: two value channels, each on its own y axis.

``y`` is a solid line against the left axis and ``y2`` a dashed line against the
right axis; the legend names each side, so colour is never the only carrier. The
two columns must not share a unit (one axis would do), a series breaks at its
own absent rows, and only the left axis has gridlines. A row without an x
leaves no mark; a row absent on ``y`` or ``y2`` is counted under that channel.
"""

from __future__ import annotations

from typing import Final

from fitdocs.render.charts.kit import frame
from fitdocs.render.charts.kit.cartesian import (
    bound_problem,
    duplicate_problem,
    numbers,
)
from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.format import (
    axis_title,
    display_label,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    TICK_GAP,
    TICK_LEN,
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
from fitdocs.render.charts.kit.theme import series_style
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 2000
_DEFAULT_HEIGHT: Final = 320
_DURATION_AXIS: Final = "duration"


def _is_duration(column: Column) -> bool:
    if column.kind is ValueKind.DURATION:
        return True
    unit = None if column.unit is None else unit_named(column.unit)
    return unit is not None and unit.family is UnitFamily.DURATION


def _axis_unit(column: Column) -> str | None:
    """The unit an axis shows: durations share one, else the unit token."""
    if _is_duration(column):
        return _DURATION_AXIS
    return column.unit


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    y, y2 = bound.column("y"), bound.column("y2")
    if y is None or y2 is None:
        return ()
    shared = _axis_unit(y)
    if y.name == y2.name:
        shown = shared if shared is not None else display_label(y)
    elif shared is not None and shared == _axis_unit(y2):
        shown = shared
    else:
        return ()
    return (
        bound.problem(
            ProblemCode.SHARED_UNIT,
            f"y and y2 both show {shown}; one unit belongs on one axis.",
            "Draw both columns on one axis with the line kind and a colour "
            "column, or bind y2 to a column in another unit.",
            channel="y2",
            column=y2.name,
        ),
    )


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return (
        *bound_problem(bound, len(bound.rows)),
        *duplicate_problem(bound, ("x",), skip_absent=("x",)),
    )


def _undrawn(
    xs: tuple[float | None, ...],
    ys: tuple[float | None, ...],
    y2s: tuple[float | None, ...],
) -> tuple[tuple[str, int], ...]:
    """Rows without an x, then each series' own absent values among the rest."""
    placed = [i for i, x in enumerate(xs) if x is not None]
    counts = (
        ("x", len(xs) - len(placed)),
        ("y", sum(1 for i in placed if ys[i] is None)),
        ("y2", sum(1 for i in placed if y2s[i] is None)),
    )
    return tuple(count for count in counts if count[1] > 0)


def _overhangs(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    """How far the x tick labels reach past the plot's left and right edges."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - plot.right)
    return left, right


def _extremes(
    bound: BoundChart, channel: str, rows: list[int], scale: NumericScale
) -> tuple[str, str]:
    """The smallest and largest present value of ``channel`` in ``rows``."""
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


def _y_scale(
    values: list[float], column: Column, plan: FramePlan, *, include_zero: bool
) -> NumericScale:
    """The niced value scale; a series with no present value gets a tickless one."""
    if not values:
        return NumericScale(
            ScaleType.LINEAR,
            0.0,
            1.0,
            plan.plot.bottom,
            plan.plot.top,
            (),
            column,
        )
    return numeric_scale(
        values,
        column,
        plan.plot.bottom,
        plan.plot.top,
        scale=ScaleType.LINEAR,
        include_zero=include_zero,
        nice=True,
        horizontal=False,
    )


def _widest(scale: NumericScale) -> float:
    return max((text_width(t.label, FONT_TEXT) for t in scale.ticks), default=0.0)


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "dual-axis declares a default height"
    xs = numbers(bound, "x")
    ys = numbers(bound, "y")
    y2s = numbers(bound, "y2")
    rows = [
        i
        for i in range(len(bound.rows))
        if xs[i] is not None and (ys[i] is not None or y2s[i] is not None)
    ]
    if not rows:
        return frame.no_data(bound, height=height)

    x_col, y_col, y2_col = (bound.columns[c] for c in ("x", "y", "y2"))
    counts = _undrawn(xs, ys, y2s)
    note = frame.not_drawn_note(counts)
    lines = [] if note is None else [note]
    legend = [
        LegendEntry(f"{display_label(y_col)} (left axis)", series_style(0), "line"),
        LegendEntry(f"{display_label(y2_col)} (right axis)", series_style(1), "line"),
    ]
    x_present = [x for i in rows if (x := xs[i]) is not None]
    y_rows = [i for i in rows if ys[i] is not None]
    y2_rows = [i for i in rows if y2s[i] is not None]
    y_present = [y for i in y_rows if (y := ys[i]) is not None]
    y2_present = [y for i in y2_rows if (y := y2s[i]) is not None]
    y_zero, y2_zero = bound.flag("y_zero"), bound.flag("y2_zero")

    def plan(
        y_label_width: float, x_label_overhang: float, right_label_width: float
    ) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=legend,
            y_label_width=y_label_width,
            x_label_overhang=x_label_overhang,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
            right_label_width=right_label_width,
        )

    first = plan(0.0, 0.0, 0.0)
    label_width = _widest(_y_scale(y_present, y_col, first, include_zero=y_zero))
    right_width = (
        _widest(_y_scale(y2_present, y2_col, first, include_zero=y2_zero))
        + TICK_GAP
        + TICK_LEN
    )

    def x_axis(plot: Rect) -> NumericScale:
        return numeric_scale(
            x_present,
            x_col,
            plot.left,
            plot.right,
            scale=ScaleType.LINEAR,
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    provisional = plan(label_width, 0.0, right_width)
    left, right = _overhangs(x_axis(provisional.plot), provisional.plot)
    final = plan(label_width + left, right, right_width)
    x_scale = x_axis(final.plot)
    y_scale = _y_scale(y_present, y_col, final, include_zero=y_zero)
    y2_scale = _y_scale(y2_present, y2_col, final, include_zero=y2_zero)

    # every row with an x, so a row with neither value still breaks both lines
    ordered = sorted(
        (i for i, x in enumerate(xs) if x is not None), key=lambda i: xs[i] or 0.0
    )
    marks: list[str] = []
    for values, scale, style in (
        (ys, y_scale, series_style(0)),
        (y2s, y2_scale, series_style(1)),
    ):
        pixels = [
            (
                x_scale.position(x),
                None if (v := values[i]) is None else scale.position(v),
            )
            for i in ordered
            if (x := xs[i]) is not None
        ]
        marks.extend(line_series(pixels, style))

    share = (final.plot.right - final.plot.left - PAD) / 2
    x_title = _axis_title(x_scale)
    left_title = _axis_title(y_scale)
    right_title = _axis_title(y2_scale)
    body = [
        frame.grid(y_scale, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, marks),
        frame.axis(x_scale, final.plot, Side.BOTTOM, plan=final),
        frame.axis(
            y_scale,
            final.plot,
            Side.LEFT,
            title=left_title,
            plan=final,
            title_room=share,
        ),
        frame.axis(
            y2_scale,
            final.plot,
            Side.RIGHT,
            title=right_title,
            plan=final,
            title_room=share,
        ),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, lines),
    ]
    drawn_titles = {"x": x_title, "y": left_title, "y2": right_title}
    channels = [
        (name, drawn_titles.get(name, column)) for name, column in bound.columns.items()
    ]
    x_low, x_high = _extremes(bound, "x", rows, x_scale)
    ranges = [(x_title, x_low, x_high)]
    if y_rows:
        low, high = _extremes(bound, "y", y_rows, y_scale)
        ranges.append((left_title, low, high))
    if y2_rows:
        low, high = _extremes(bound, "y2", y2_rows, y2_scale)
        ranges.append((right_title, low, high))
    description = frame.describe(
        "dual-axis",
        bound.request.title,
        channels,
        rows=len(bound.rows),
        series=None,
        undrawn=counts,
        ranges=ranges,
    )
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="dual-axis",
    description=(
        "Two series over one x, each on its own y axis with its own unit; "
        "unless the two are a deliberate pair, prefer small-multiples or one "
        "line with a colour column"
    ),
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
            "The value drawn solid against the left axis: a number or duration.",
        ),
        ChannelSpec(
            "y2",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The value drawn dashed against the right axis, in another unit "
            "than y: a number or duration.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the left axis to include zero.",
            False,
        ),
        OptionSpec(
            "y2_zero",
            OptionType.BOOLEAN,
            "Extend the right axis to include zero.",
            False,
        ),
        height=_DEFAULT_HEIGHT,
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, "At most 2000 rows; more are refused."
    ),
    max_series=None,
    draw=_draw,
    validate=_validate,
    check=_check,
)
