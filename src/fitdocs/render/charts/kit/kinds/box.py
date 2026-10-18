"""The ``box`` kind: per-category quartile boxes with whiskers.

The kit computes no quantile: each row carries its own ``low``, ``q1``,
``median``, ``q3`` and ``high``, and the box is drawn exactly from them. A row
missing ``q1``, ``median`` or ``q3`` draws no box but keeps its labelled band
and is counted as not drawn. A missing ``low`` or ``high`` draws the box
without that whisker and is counted in a ``No whisker:`` note. Every drawn
whisker ends in a cap, so a whisker of zero length still shows.
"""

from __future__ import annotations

from typing import Final

from fitdocs.render.charts.kit import frame
from fitdocs.render.charts.kit.cartesian import (
    band_x_axis,
    bound_problem,
    category_bands,
    category_order,
    duplicate_problem,
    numbers,
)
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.format import (
    axis_title,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    FramePlan,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import (
    BandScale,
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
from fitdocs.render.charts.svg import el, fmt_num
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 60
_VALUES: Final = ("low", "q1", "median", "q3", "high")
_BAND_SHARE: Final = 0.6  # of the band, one box
_MAX_BOX: Final = 40.0  # px, one box
_FILL_OPACITY: Final = "0.2"
_MEDIAN_WIDTH: Final = "2.5"
_EDGE_WIDTH: Final = "1"


def _unit_text(column: Column) -> str:
    return "no unit" if column.unit is None else f"unit '{column.unit}'"


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    first = bound.column(_VALUES[0])
    if first is None:
        return ()
    found: list[ChartProblem] = []
    for channel in _VALUES[1:]:
        column = bound.column(channel)
        if column is None:
            continue
        if column.kind is not first.kind:
            found.append(
                bound.problem(
                    ProblemCode.CHANNEL_KIND,
                    f"Channel '{channel}' must be the same kind as channel "
                    f"'{_VALUES[0]}', but column '{first.name}' is "
                    f"{first.kind.value} and column '{column.name}' is "
                    f"{column.kind.value}.",
                    "Bind the five value channels to columns that are all number "
                    "or all duration.",
                    channel=channel,
                    column=column.name,
                    accepted=tuple(
                        c.name for c in bound.all_columns if c.kind is first.kind
                    ),
                )
            )
        elif column.unit != first.unit:
            found.append(
                bound.problem(
                    ProblemCode.UNIT_MISMATCH,
                    f"Channel '{channel}' must have the unit of channel "
                    f"'{_VALUES[0]}', but column '{first.name}' has "
                    f"{_unit_text(first)} and column '{column.name}' has "
                    f"{_unit_text(column)}.",
                    f"Bind '{channel}' to a column with the same unit as "
                    f"'{_VALUES[0]}'.",
                    channel=channel,
                    column=column.name,
                    accepted=tuple(
                        c.name
                        for c in bound.all_columns
                        if c.kind is first.kind and c.unit == first.unit
                    ),
                )
            )
    return tuple(found)


def _exact(number: float | None, column: Column) -> str:
    """A value to ten significant digits; seconds for a duration column."""
    assert number is not None
    text = f"{number:.10g}"
    if column.kind is ValueKind.DURATION:
        return f"{text} s"
    return text if column.unit is None else f"{text} {column.unit}"


def _order_problem(bound: BoundChart) -> tuple[ChartProblem, ...]:
    """The first row whose present values are not low <= q1 <= ... <= high."""
    views = {ch: numbers(bound, ch) for ch in _VALUES}
    cells = {ch: bound.values(ch) for ch in _VALUES}
    offending: list[tuple[int, str, str]] = []
    for row in range(len(bound.rows)):
        present = [ch for ch in _VALUES if views[ch][row] is not None]
        for before, after in zip(present, present[1:], strict=False):
            low, high = views[before][row], views[after][row]
            assert low is not None and high is not None
            if low > high:
                offending.append((row, before, after))
                break
    if not offending:
        return ()
    row, before, after = offending[0]
    shown = [
        format_value(cells[ch][row], bound.columns[ch], with_unit=True)
        for ch in (before, after)
    ]
    if shown[0] == shown[1]:
        # Rounding hid the difference; say the exact numbers instead.
        shown = [_exact(views[ch][row], bound.columns[ch]) for ch in (before, after)]
    return (
        bound.problem(
            ProblemCode.VALUE_ORDER,
            f"Row {row} has {before} {shown[0]} above {after} {shown[1]}.",
            "Bind each channel to its own column, or correct the query so that "
            "low ≤ q1 ≤ median ≤ q3 ≤ high.",
            channel=after,
            column=bound.columns[after].name,
            row=row,
            rows=len(offending),
        ),
    )


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return (
        *bound_problem(bound, len(bound.rows)),
        # An absent x is the ``—`` category, so no key channel is exempt.
        *duplicate_problem(bound, ("x",)),
        *_order_problem(bound),
    )


def _y_scale(
    bound: BoundChart, values: list[float], plan: FramePlan, *, y_zero: bool
) -> NumericScale:
    return numeric_scale(
        values,
        bound.columns["median"],
        plan.plot.bottom,
        plan.plot.top,
        scale=ScaleType.LINEAR,
        include_zero=y_zero,
        nice=True,
        horizontal=False,
    )


def _line(x1: float, y1: float, x2: float, y2: float, color: str, width: str) -> str:
    return el(
        "line",
        {
            "x1": fmt_num(x1),
            "y1": fmt_num(y1),
            "x2": fmt_num(x2),
            "y2": fmt_num(y2),
            "stroke": color,
            "stroke-width": width,
        },
    )


def _whisker(
    centre: float, edge: float, end: float, half_cap: float, color: str
) -> list[str]:
    """A stem from the box edge to ``end`` (none when they coincide), then a cap."""
    parts = []
    if end != edge:
        parts.append(_line(centre, edge, centre, end, color, _EDGE_WIDTH))
    parts.append(
        _line(centre - half_cap, end, centre + half_cap, end, color, _EDGE_WIDTH)
    )
    return parts


def _box(
    x_axis: BandScale,
    y_axis: NumericScale,
    band: int,
    values: dict[str, float | None],
    color: str,
) -> list[str]:
    q1, median, q3 = values["q1"], values["median"], values["q3"]
    assert q1 is not None and median is not None and q3 is not None
    lo, hi = x_axis.band(band)
    centre = (lo + hi) / 2
    width = min(_BAND_SHARE * (hi - lo), _MAX_BOX)
    left = centre - width / 2
    bottom, top = y_axis.position(q1), y_axis.position(q3)
    parts = [
        el(
            "rect",
            {
                "x": fmt_num(left),
                "y": fmt_num(top),
                "width": fmt_num(width),
                "height": fmt_num(bottom - top),
                "fill": color,
                "fill-opacity": _FILL_OPACITY,
                "stroke": color,
                "stroke-width": _EDGE_WIDTH,
            },
        )
    ]
    if values["low"] is not None:
        parts += _whisker(
            centre, bottom, y_axis.position(values["low"]), width / 4, color
        )
    if values["high"] is not None:
        parts += _whisker(
            centre, top, y_axis.position(values["high"]), width / 4, color
        )
    at = y_axis.position(median)
    parts.append(_line(left, at, left + width, at, color, _MEDIAN_WIDTH))
    return parts


def _whisker_note(missing: tuple[tuple[str, int], ...]) -> str | None:
    parts = [
        f"{n} row without {ch}" if n == 1 else f"{n} rows without {ch}"
        for ch, n in missing
        if n
    ]
    return f"No whisker: {', '.join(parts)}." if parts else None


def _extremes(
    bound: BoundChart, drawn: list[int], y_axis: NumericScale
) -> tuple[str, str]:
    """The formatted smallest and largest drawn value, with units.

    A duration-family axis formats both in the axis's own ``h:mm:ss`` or
    ``m:ss`` form, so the range reads like the axis title says.
    """
    present: list[tuple[float, Value]] = []
    for channel in _VALUES:
        for row in drawn:
            number = numbers(bound, channel)[row]
            if number is not None:
                present.append((number, bound.values(channel)[row]))
    low = min(present, key=lambda pair: pair[0])
    high = max(present, key=lambda pair: pair[0])
    column = bound.columns["median"]
    unit = unit_named(column.unit) if column.unit is not None else None
    if column.kind is ValueKind.DURATION or (
        unit is not None and unit.family is UnitFamily.DURATION
    ):
        return (
            format_duration(low[0], hours=y_axis.hours),
            format_duration(high[0], hours=y_axis.hours),
        )
    return (
        format_value(low[1], column, with_unit=True),
        format_value(high[1], column, with_unit=True),
    )


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "box declares a default height"
    views = {ch: numbers(bound, ch) for ch in _VALUES}
    drawn = [
        row
        for row in range(len(bound.rows))
        if all(views[ch][row] is not None for ch in ("q1", "median", "q3"))
    ]
    if not drawn:
        return frame.no_data(bound, height=height)

    labels = category_order(bound, "x")
    bands = category_bands(bound, "x")
    # An absent x is the ``—`` band, so every row is positioned; each box
    # channel counts its own absent values (a row absent on two counts under both).
    not_drawn = tuple(
        (ch, sum(1 for v in views[ch] if v is None)) for ch in ("q1", "median", "q3")
    )
    not_drawn = tuple((ch, n) for ch, n in not_drawn if n)
    whiskers = tuple(
        (ch, sum(1 for row in drawn if views[ch][row] is None))
        for ch in ("low", "high")
    )
    lines = [
        line
        for line in (frame.not_drawn_note(not_drawn), _whisker_note(whiskers))
        if line is not None
    ]
    domain = [
        number
        for ch in _VALUES
        for row in drawn
        if (number := views[ch][row]) is not None
    ]
    y_zero = bound.flag("y_zero")

    def plan_with(label_width: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=(),
            y_label_width=label_width,
            x_label_overhang=0.0,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    first = _y_scale(bound, domain, plan_with(0.0), y_zero=y_zero)
    label_width = max(text_width(t.label, FONT_TEXT) for t in first.ticks)
    plan, x_axis = band_x_axis(labels, plan_with, label_width)
    y_axis = _y_scale(bound, domain, plan, y_zero=y_zero)

    color = series_style(0).color
    shapes: list[str] = []
    for row in drawn:
        shapes += _box(
            x_axis,
            y_axis,
            bands[row],
            {ch: views[ch][row] for ch in _VALUES},
            color,
        )

    low, high = _extremes(bound, drawn, y_axis)
    y_title = axis_title(
        bound.columns["median"], clock_date=y_axis.clock_date, hours=y_axis.hours
    )
    x_title = axis_title(bound.columns["x"])
    channels = [("x", x_title)] + [
        (
            ch,
            axis_title(
                bound.columns[ch], clock_date=y_axis.clock_date, hours=y_axis.hours
            ),
        )
        for ch in _VALUES
    ]
    description = frame.describe(
        "box",
        bound.request.title,
        channels,
        rows=len(bound.rows),
        series=None,
        undrawn=not_drawn,
        ranges=(
            (x_title, labels[0], labels[-1]),
            (y_title, low, high),
        ),
    )
    body = [
        frame.grid(y_axis, plan.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, shapes),
        frame.axis(x_axis, plan.plot, Side.BOTTOM, title=x_title, plan=plan),
        frame.axis(y_axis, plan.plot, Side.LEFT, title=y_title, plan=plan),
        frame.legend(plan),
        frame.title_text(plan, bound.request.title),
        frame.notes(plan, lines),
    ]
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


_VALUE_KINDS: Final = (ValueKind.NUMBER, ValueKind.DURATION)

KIND: Final = KindSpec(
    name="box",
    description="One box-and-whisker per category from given quartiles",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The category or date each box stands at.",
        ),
        ChannelSpec("low", _VALUE_KINDS, True, "The lower whisker end."),
        ChannelSpec("q1", _VALUE_KINDS, True, "The bottom edge of the box."),
        ChannelSpec("median", _VALUE_KINDS, True, "The line across the box."),
        ChannelSpec("q3", _VALUE_KINDS, True, "The top edge of the box."),
        ChannelSpec("high", _VALUE_KINDS, True, "The upper whisker end."),
    ),
    options=svg_options(
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the y axis to include zero.",
            False,
        ),
        height=320,
    ),
    bound=MarkBound(
        _LIMIT,
        "rows",
        OverBound.REFUSE,
        f"A box chart draws at most {_LIMIT} rows; more are refused.",
    ),
    max_series=None,
    draw=_draw,
    check=_check,
    validate=_validate,
)
