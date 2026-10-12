"""The ``band`` kind: a low-to-high band over a numeric or time x, with a centre line.

Rows are joined in ascending x order. The band breaks wherever a row's low or
high is absent and a lone band position is a vertical line from low to high;
the optional centre line breaks wherever ``mid`` is absent and a lone centre
point is a dot. A row with no x is counted under x, and every other row
counts each of its absent low, high and mid values, in the chart's note and
description. The x axis keeps the exact data extent; the y axis is niced.
"""

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
from fitdocs.render.charts.kit.theme import series_style
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
    first = bound.column("low")
    if first is None:
        return ()
    problems: list[ChartProblem] = []
    for channel in ("high", "mid"):
        column = bound.column(channel)
        if column is None:
            continue
        if column.kind is not first.kind:
            problems.append(
                bound.problem(
                    ProblemCode.CHANNEL_KIND,
                    f"Channel '{channel}' must be the same kind as channel 'low', "
                    f"but column '{first.name}' is {first.kind.value} and column "
                    f"'{column.name}' is {column.kind.value}.",
                    "Bind 'low', 'high' and 'mid' to columns that are all number "
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
                    f"Channel '{channel}' must have the unit of channel 'low', but "
                    f"column '{first.name}' has {_unit_text(first)} and column "
                    f"'{column.name}' has {_unit_text(column)}.",
                    f"Bind '{channel}' to a column with the same unit as 'low'.",
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
    return tuple(problems)


def _exact(number: float | None, column: Column) -> str:
    """A value to ten significant digits, in seconds for a duration column."""
    assert number is not None
    text = f"{number:.10g}"
    if column.kind is ValueKind.DURATION:
        return f"{text} s"
    return text if column.unit is None else f"{text} {column.unit}"


def _order_problem(bound: BoundChart) -> tuple[ChartProblem, ...]:
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


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return (
        *bound_problem(bound, len(bound.rows)),
        *duplicate_problem(bound, ("x",), skip_absent=("x",)),
        *_order_problem(bound),
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


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "band declares a default height"
    rows = len(bound.rows)
    xs = numbers(bound, "x")
    lows, highs = numbers(bound, "low"), numbers(bound, "high")
    has_mid = bound.column("mid") is not None
    mids = numbers(bound, "mid") if has_mid else (None,) * rows

    def banded(i: int) -> bool:
        return lows[i] is not None and highs[i] is not None

    def marked(i: int) -> bool:
        return xs[i] is not None and (banded(i) or mids[i] is not None)

    # Rows that leave a mark.
    drawn = [i for i in range(rows) if marked(i)]
    if not drawn:
        return frame.no_data(bound, height=height)

    # Rows with no x count under x; among the rest each value channel counts
    # its own absent values (a row absent on two channels counts under both).
    placed_rows = [i for i in range(rows) if xs[i] is not None]
    counts = tuple(
        (name, n)
        for name, n in (
            ("x", rows - len(placed_rows)),
            ("low", sum(1 for i in placed_rows if lows[i] is None)),
            ("high", sum(1 for i in placed_rows if highs[i] is None)),
            ("mid", sum(1 for i in placed_rows if has_mid and mids[i] is None)),
        )
        if n > 0
    )
    note = frame.not_drawn_note(counts)
    lines = [] if note is None else [note]

    x_col = bound.columns["x"]
    low_col, high_col = bound.columns["low"], bound.columns["high"]
    y_col = bound.columns["mid"] if has_mid else low_col
    style = series_style(0)
    legend = [
        LegendEntry(
            f"{display_label(low_col)} to {display_label(high_col)}", style, "block"
        )
    ]
    if has_mid:
        legend.append(LegendEntry(display_label(y_col), style, "line"))

    x_entries = [(x, bound.values("x")[i]) for i in drawn if (x := xs[i]) is not None]
    y_entries: list[tuple[float, Value]] = []
    for i in drawn:
        low, high, mid = lows[i], highs[i], mids[i]
        if low is not None and high is not None:
            y_entries.append((low, bound.values("low")[i]))
            y_entries.append((high, bound.values("high")[i]))
        if mid is not None:
            y_entries.append((mid, bound.values("mid")[i]))

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

    # Band runs: position k is ``placed[k]``; a position without both edges
    # carries no y and so ends the run it is in.
    # Every row with an x is a position, so a row holding only one edge still
    # breaks the band.
    placed = sorted(
        (i for i in range(rows) if xs[i] is not None), key=lambda i: xs[i] or 0.0
    )
    edge = [lows[i] if banded(i) else None for i in placed]
    marks: list[str] = []
    for run in gap_segments([float(k) for k in range(len(placed))], edge):
        members = [placed[int(k)] for k, _ in run]
        px = [x_scale.position(xs[i] or 0.0) for i in members]
        low_px = [y_scale.position(lows[i] or 0.0) for i in members]
        high_px = [y_scale.position(highs[i] or 0.0) for i in members]
        if len(members) == 1:
            marks.append(_vertical(px[0], low_px[0], high_px[0], style.color))
            continue
        marks.append(
            el(
                "path",
                {
                    "d": band_path(px, low_px, high_px),
                    "fill": style.color,
                    "fill-opacity": _FILL_OPACITY,
                    "stroke": style.color,
                    "stroke-width": _OUTLINE_WIDTH,
                },
            )
        )
    if has_mid:
        centre = [
            (
                x_scale.position(xs[i] or 0.0),
                None if mids[i] is None else y_scale.position(mids[i] or 0.0),
            )
            for i in placed
        ]
        marks.extend(line_series(centre, style))

    body = [
        frame.grid(y_scale, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, marks),
        frame.axis(x_scale, final.plot, Side.BOTTOM, plan=final),
        frame.axis(y_scale, final.plot, Side.LEFT, plan=final),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, lines),
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
        "band",
        bound.request.title,
        channels,
        rows=rows,
        series=None,
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
    name="band",
    description=(
        "A band from low to high over a numeric or time x, with an optional centre line"
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
            "low",
            _VALUE_KINDS,
            True,
            "The lower edge of the band: a number or duration.",
        ),
        ChannelSpec(
            "high",
            _VALUE_KINDS,
            True,
            "The upper edge of the band, in the kind and unit of low.",
        ),
        ChannelSpec(
            "mid",
            _VALUE_KINDS,
            False,
            "The centre line (for example a median), in the kind and unit of low.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the y axis to include zero.",
            False,
        ),
        height=_DEFAULT_HEIGHT,
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, "At most 1000 rows; more are refused."
    ),
    max_series=None,
    draw=_draw,
    validate=_validate,
    check=_check,
)
