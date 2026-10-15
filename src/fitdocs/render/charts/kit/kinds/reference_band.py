"""Values as points against a segmented reference band, with optional flags."""

from __future__ import annotations

from typing import Final

from fitdocs.render.charts.kit import frame
from fitdocs.render.charts.kit.cartesian import (
    bound_problem,
    duplicate_problem,
    numbers,
)
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.format import (
    ABSENT,
    axis_title,
    display_label,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    FramePlan,
    LegendEntry,
    Rect,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.marks import band_path, line_series
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
from fitdocs.render.charts.kit.theme import (
    STROKE,
    SeriesStyle,
    Shape,
    ink,
    series_style,
    shape_path,
)
from fitdocs.render.charts.series import gap_segments
from fitdocs.render.charts.svg import el, fmt_num
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 1000
_DEFAULT_HEIGHT: Final = 320
_FILL_OPACITY: Final = "0.2"
_OUTLINE_WIDTH: Final = "1"
_LINE_WIDTH: Final = "1.8"
_VALUE_KINDS: Final = (ValueKind.NUMBER, ValueKind.DURATION)


def _unit_text(column: Column) -> str:
    return "no unit" if column.unit is None else f"unit '{column.unit}'"


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    first = bound.column("y")
    if first is None:
        return ()
    problems: list[ChartProblem] = []
    for channel in ("low", "high", "mid"):
        column = bound.column(channel)
        if column is None:
            continue
        if column.kind is not first.kind:
            problems.append(
                bound.problem(
                    ProblemCode.CHANNEL_KIND,
                    f"Channel '{channel}' must be the same kind as channel 'y', "
                    f"but column '{first.name}' is {first.kind.value} "
                    f"({_unit_text(first)}) and column "
                    f"'{column.name}' is {column.kind.value} ({_unit_text(column)}).",
                    "Bind 'y', 'low', 'high' and 'mid' to columns that are all number "
                    "or all duration.",
                    channel=channel,
                    column=column.name,
                    accepted=tuple(
                        c.name
                        for c in bound.all_columns
                        if c.kind is first.kind and c.name != first.name
                    ),
                )
            )
        elif column.unit != first.unit:
            problems.append(
                bound.problem(
                    ProblemCode.UNIT_MISMATCH,
                    f"Channel '{channel}' must have the unit of channel 'y', but "
                    f"column '{first.name}' has {_unit_text(first)} and column "
                    f"'{column.name}' has {_unit_text(column)}.",
                    f"Bind '{channel}' to a column with the same unit as 'y'.",
                    channel=channel,
                    column=column.name,
                    accepted=tuple(
                        c.name
                        for c in bound.all_columns
                        if c.kind is first.kind
                        and c.unit == first.unit
                        and c.name != first.name
                    ),
                )
            )
    low, high = bound.column("low"), bound.column("high")
    if (low is None) != (high is None):
        missing = "low" if low is None else "high"
        problems.append(
            bound.problem(
                ProblemCode.MISSING_CHANNEL,
                f"Channel '{missing}' must be bound when the other band edge is bound.",
                f"Bind '{missing}', or leave both band edges unbound.",
                channel=missing,
            )
        )
    return tuple(problems)


def _exact(number: float | None, column: Column) -> str:
    """A value to ten significant digits, in seconds for a duration column."""
    assert number is not None
    text = f"{number:.10g}"
    if column.kind is ValueKind.DURATION:
        return f"{text} s"
    return text if column.unit is None else f"{text} {column.unit}"


def _order_problem(bound: BoundChart) -> tuple[ChartProblem, ...]:
    if bound.column("low") is None:
        return ()
    low_col, high_col = bound.columns["low"], bound.columns["high"]
    lows, highs = numbers(bound, "low"), numbers(bound, "high")
    offending = [
        i
        for i, (low, high) in enumerate(zip(lows, highs, strict=True))
        if low is not None and high is not None and low > high
    ]
    if not offending:
        return ()
    first = offending[0]
    low_text = format_value(bound.values("low")[first], low_col, with_unit=True)
    high_text = format_value(bound.values("high")[first], high_col, with_unit=True)
    if low_text == high_text:
        # Rounding hid the difference; say the exact numbers instead.
        low_text = _exact(lows[first], low_col)
        high_text = _exact(highs[first], high_col)
    message = f"Row {first} has low {low_text} above high {high_text}."
    return (
        bound.problem(
            ProblemCode.VALUE_ORDER,
            message,
            "Swap the low and high bindings, or correct the query so that low "
            "is at most high.",
            channel="low",
            column=low_col.name,
            row=first,
            rows=len(offending),
        ),
    )


def _segments(
    bound: BoundChart, placed: list[int]
) -> tuple[list[Value], tuple[Value, ...]]:
    values = (
        bound.values("segment")
        if bound.column("segment") is not None
        else (None,) * len(bound.rows)
    )
    order = list(dict.fromkeys(values[i] for i in placed if values[i] is not None))
    if any(values[i] is None for i in placed):
        order.append(None)
    return order, values


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    order, _ = _segments(bound, list(range(len(bound.rows))))
    segment = bound.column("segment")
    series = (
        ()
        if len(order) <= 8
        else (
            bound.problem(
                ProblemCode.TOO_MANY_SERIES,
                "reference-band draws at most 8 segments; "
                f"the segment channel yields {len(order)}.",
                "Filter the rows or bind a segment column with at most "
                "8 distinct values.",
                channel="segment",
                column=None if segment is None else segment.name,
            ),
        )
    )
    return (
        *bound_problem(bound, len(bound.rows)),
        *duplicate_problem(bound, ("x",), skip_absent=("x",)),
        *_order_problem(bound),
        *series,
    )


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


def _axis_title(scale: NumericScale) -> str:
    return axis_title(scale.column, clock_date=scale.clock_date, hours=scale.hours)


def _extremes(
    entries: list[tuple[float, Value]], column: Column, scale: NumericScale
) -> tuple[str, str]:
    """The smallest and largest drawn value, in the axis's own form."""

    def shown(entry: tuple[float, Value]) -> str:
        if _is_duration(column):
            return format_duration(entry[0], hours=scale.hours)
        return format_value(entry[1], column, with_unit=True)

    return (
        shown(min(entries, key=lambda e: e[0])),
        shown(max(entries, key=lambda e: e[0])),
    )


def _vertical(x: float, low: float, high: float, color: str) -> str:
    return el(
        "line",
        {
            "x1": fmt_num(x),
            "y1": fmt_num(low),
            "x2": fmt_num(x),
            "y2": fmt_num(high),
            "stroke": color,
            "stroke-width": _LINE_WIDTH,
            "stroke-linecap": "round",
        },
    )


def _draw_flags(
    bound: BoundChart,
    height: int,
    legend: list[LegendEntry],
    x_entries: list[tuple[float, Value]],
    counts: tuple[tuple[str, int], ...],
    notes: list[str],
    series: int | None,
) -> str:
    x_col = bound.columns["x"]

    def plan(left: float, right: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=legend,
            y_label_width=left,
            x_label_overhang=right,
            has_x_title=True,
            has_y_title=False,
            notes=len(notes),
        )

    def scale(plot: Rect) -> NumericScale:
        return numeric_scale(
            [x for x, _ in x_entries],
            x_col,
            plot.left,
            plot.right,
            scale=ScaleType.LINEAR,
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    first = plan(0.0, 0.0)
    left, right = _overhangs(scale(first.plot), first.plot)
    final = plan(left, right)
    x_scale = scale(final.plot)
    flagged = [(x_scale.position(x), final.plot.bottom - 5) for x, _ in x_entries]
    body = [
        el(
            "g",
            {"class": "ck-marks"},
            [shape_path(Shape.TRIANGLE_UP, flagged, ink(STROKE)["stroke"])],
        ),
        frame.axis(x_scale, final.plot, Side.BOTTOM, plan=final),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, notes),
    ]
    low, high = _extremes(x_entries, x_col, x_scale)
    description = frame.describe(
        "reference-band",
        bound.request.title,
        [
            (name, _axis_title(x_scale) if name == "x" else axis_title(column))
            for name, column in bound.columns.items()
        ],
        rows=len(bound.rows),
        series=series,
        undrawn=counts,
        ranges=[(_axis_title(x_scale), low, high)],
    )
    description += (
        f" {axis_title(bound.columns['y'])} range: no numeric values to draw."
    )
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None
    rows = len(bound.rows)
    if rows == 0:
        return frame.no_data(bound, height=height)
    xs, ys = numbers(bound, "x"), numbers(bound, "y")
    has_band = bound.column("low") is not None
    has_mid = bound.column("mid") is not None
    has_flag = bound.column("flag") is not None
    lows = numbers(bound, "low") if has_band else (None,) * rows
    highs = numbers(bound, "high") if has_band else (None,) * rows
    mids = numbers(bound, "mid") if has_mid else (None,) * rows
    flags = bound.values("flag") if has_flag else (None,) * rows

    def banded(i: int) -> bool:
        return lows[i] is not None and highs[i] is not None

    def marked(i: int) -> bool:
        return ys[i] is not None or banded(i) or mids[i] is not None or flags[i] is True

    placed = sorted(
        (i for i in range(rows) if xs[i] is not None), key=lambda i: xs[i] or 0.0
    )
    drawn = [i for i in placed if marked(i)]
    if not drawn:
        return frame.no_data(bound, height=height)
    counts = tuple(
        (name, n)
        for name, n in (
            ("x", rows - len(placed)),
            ("y", sum(ys[i] is None for i in placed)),
            ("low", sum(has_band and lows[i] is None for i in placed)),
            ("high", sum(has_band and highs[i] is None for i in placed)),
            ("mid", sum(has_mid and mids[i] is None for i in placed)),
        )
        if n > 0
    )
    note = frame.not_drawn_note(counts)
    notes = [] if note is None else [note]
    order, segments = _segments(bound, placed)
    styles = {value: series_style(i) for i, value in enumerate(order)}
    segmented = bound.column("segment") is not None
    neutral = (
        SeriesStyle(ink(STROKE)["stroke"], None, Shape.CIRCLE)
        if segmented
        else series_style(0)
    )
    legend: list[LegendEntry] = []
    if segmented:
        legend.extend(
            LegendEntry(ABSENT if value is None else str(value), styles[value], "shape")
            for value in order
            if any(segments[i] == value for i in drawn)
        )
    legend.append(LegendEntry(display_label(bound.columns["y"]), neutral, "shape"))
    if has_mid:
        legend.append(LegendEntry(display_label(bound.columns["mid"]), neutral, "line"))
    if has_band:
        legend.append(
            LegendEntry(
                f"{display_label(bound.columns['low'])} to "
                f"{display_label(bound.columns['high'])}",
                neutral,
                "block",
            )
        )
    if has_flag:
        legend.append(
            LegendEntry(
                display_label(bound.columns["flag"]),
                SeriesStyle(neutral.color, None, Shape.TRIANGLE_UP),
                "shape",
            )
        )
    x_col, y_col = bound.columns["x"], bound.columns["y"]
    x_entries = [(x, bound.values("x")[i]) for i in drawn if (x := xs[i]) is not None]
    y_entries: list[tuple[float, Value]] = []
    for i in drawn:
        if (y := ys[i]) is not None:
            y_entries.append((y, bound.values("y")[i]))
        if (mid := mids[i]) is not None:
            y_entries.append((mid, bound.values("mid")[i]))
        low, high = lows[i], highs[i]
        if low is not None and high is not None:
            y_entries.extend(
                ((low, bound.values("low")[i]), (high, bound.values("high")[i]))
            )

    if not y_entries:
        return _draw_flags(
            bound,
            height,
            legend,
            x_entries,
            counts,
            notes,
            len(order) if segmented else None,
        )

    def plan(y_label_width: float, x_label_overhang: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=legend,
            y_label_width=y_label_width,
            x_label_overhang=x_label_overhang,
            has_x_title=True,
            has_y_title=True,
            notes=len(notes),
        )

    first = plan(0.0, 0.0)
    y_scale = numeric_scale(
        [v for v, _ in y_entries],
        y_col,
        first.plot.bottom,
        first.plot.top,
        scale=ScaleType.LINEAR,
        include_zero=bound.flag("y_zero"),
        nice=True,
        horizontal=False,
    )
    label_width = max(
        (text_width(t.label, FONT_TEXT) for t in y_scale.ticks), default=0.0
    )

    def x_axis(plot: Rect) -> NumericScale:
        return numeric_scale(
            [x for x, _ in x_entries],
            x_col,
            plot.left,
            plot.right,
            scale=ScaleType.LINEAR,
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    provisional = plan(label_width, 0.0)
    left, right = _overhangs(x_axis(provisional.plot), provisional.plot)
    final = plan(label_width + left, right)
    x_scale = x_axis(final.plot)
    runs: list[list[int]] = []
    for i in placed:
        if not runs or segments[runs[-1][-1]] != segments[i]:
            runs.append([])
        runs[-1].append(i)
    marks: list[str] = []
    for run in runs:
        style = styles[segments[run[0]]]
        edge = [lows[i] if banded(i) else None for i in run]
        for contiguous in gap_segments([float(k) for k in range(len(run))], edge):
            members = [run[int(k)] for k, _ in contiguous]
            px = [x_scale.position(xs[i] or 0.0) for i in members]
            low_px = [y_scale.position(lows[i] or 0.0) for i in members]
            high_px = [y_scale.position(highs[i] or 0.0) for i in members]
            if len(members) == 1:
                marks.append(_vertical(px[0], low_px[0], high_px[0], style.color))
            else:
                attrs = {
                    "d": band_path(px, low_px, high_px),
                    "fill": style.color,
                    "fill-opacity": _FILL_OPACITY,
                    "stroke": style.color,
                    "stroke-width": _OUTLINE_WIDTH,
                }
                if style.dash is not None:
                    attrs["stroke-dasharray"] = style.dash
                marks.append(el("path", attrs))
        if has_mid:
            marks.extend(
                line_series(
                    [
                        (
                            x_scale.position(xs[i] or 0.0),
                            None
                            if mids[i] is None
                            else y_scale.position(mids[i] or 0.0),
                        )
                        for i in run
                    ],
                    style,
                )
            )
    for value in order:
        style = styles[value]
        points = [
            (x_scale.position(xs[i] or 0.0), y_scale.position(ys[i] or 0.0))
            for i in placed
            if segments[i] == value and ys[i] is not None
        ]
        if points:
            marks.append(shape_path(style.shape, points, style.color))
    flagged = [
        (x_scale.position(xs[i] or 0.0), final.plot.bottom - 5)
        for i in placed
        if flags[i] is True
    ]
    if flagged:
        marks.append(shape_path(Shape.TRIANGLE_UP, flagged, ink(STROKE)["stroke"]))
    body = [
        frame.grid(y_scale, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, marks),
        frame.axis(x_scale, final.plot, Side.BOTTOM, plan=final),
        frame.axis(y_scale, final.plot, Side.LEFT, plan=final),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, notes),
    ]
    x_low, x_high = _extremes(x_entries, x_col, x_scale)
    y_low, y_high = _extremes(y_entries, y_col, y_scale)
    channels = [
        (
            name,
            _axis_title(x_scale)
            if name == "x"
            else axis_title(column, hours=y_scale.hours),
        )
        for name, column in bound.columns.items()
    ]
    description = frame.describe(
        "reference-band",
        bound.request.title,
        channels,
        rows=rows,
        series=len(order) if segmented else None,
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
    name="reference-band",
    description="Values as points against a segmented reference band, "
    "with optional centre line and flags.",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION, ValueKind.DATE, ValueKind.DATETIME),
            True,
            "Horizontal position.",
        ),
        ChannelSpec(
            "y", (ValueKind.NUMBER, ValueKind.DURATION), True, "Values as points."
        ),
        ChannelSpec(
            "low", (ValueKind.NUMBER, ValueKind.DURATION), False, "Lower band edge."
        ),
        ChannelSpec(
            "high", (ValueKind.NUMBER, ValueKind.DURATION), False, "Upper band edge."
        ),
        ChannelSpec(
            "mid", (ValueKind.NUMBER, ValueKind.DURATION), False, "Centre line."
        ),
        ChannelSpec(
            "segment", (ValueKind.CATEGORY,), False, "Separate source segments."
        ),
        ChannelSpec(
            "flag", (ValueKind.BOOLEAN,), False, "Rows marked along the bottom axis."
        ),
    ),
    options=svg_options(
        OptionSpec(
            "y_zero", OptionType.BOOLEAN, "Extend the y axis to include zero.", False
        ),
        height=_DEFAULT_HEIGHT,
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, "At most 1000 rows; more are refused."
    ),
    max_series=8,
    draw=_draw,
    validate=_validate,
    check=_check,
)
