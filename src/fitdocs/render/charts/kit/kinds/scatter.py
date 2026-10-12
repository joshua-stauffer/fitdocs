"""The ``scatter`` kind: one marker per row, one series per colour value.

Both axes are niced value axes. A series is one ``<path>`` of markers in its own
shape. Rows without an x or a y cannot be placed: they are counted in a note and
in the description. With ``trend`` each series with at least two distinct x
values among its drawn points gets its least-squares line from its smallest to
its largest x, clipped to the plot; the other series are named in a note.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs.render.charts.kit import cartesian, frame, marks
from fitdocs.render.charts.kit.data import ValueKind
from fitdocs.render.charts.kit.format import axis_title, format_duration, format_value
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    TICK_GAP,
    TICK_LEN,
    FramePlan,
    LegendEntry,
    plan_frame,
    text_width,
)
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
_HEIGHT: Final = 360
_TIME_KINDS: Final = (ValueKind.DATE, ValueKind.DATETIME)


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    found: list[ChartProblem] = []
    trend = bound.flag("trend")
    for channel in ("x", "y"):
        option = f"{channel}_scale"
        column = bound.column(channel)
        if column is None or bound.choice(option) != "log":
            continue
        if column.kind in _TIME_KINDS:
            found.append(
                bound.problem(
                    ProblemCode.OPTION_CONFLICT,
                    f"Option '{option}' cannot be log for column '{column.name}', "
                    f"which is a {column.kind.value}.",
                    f"Set '{option}' to linear.",
                    channel=channel,
                    column=column.name,
                    option=option,
                )
            )
        if trend:
            found.append(
                bound.problem(
                    ProblemCode.OPTION_CONFLICT,
                    "Option 'trend' cannot be combined with a logarithmic scale, "
                    f"but '{option}' is log.",
                    f"Set 'trend' to false or set '{option}' to linear.",
                    channel=channel,
                    column=column.name,
                    option=option,
                )
            )
    return tuple(found)


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    found = [*cartesian.bound_problem(bound, len(bound.rows))]
    found.extend(cartesian.series_problem(bound))
    for channel in ("x", "y"):
        if bound.choice(f"{channel}_scale") == "log":
            found.extend(cartesian.log_problem(bound, channel))
    return tuple(found)


@dataclass(frozen=True)
class _Trend:
    x_mean: float
    y_mean: float
    slope: float
    x_lo: float
    x_hi: float

    def at(self, x: float) -> float:
        return self.y_mean + self.slope * (x - self.x_mean)


def _fit(points: list[tuple[float, float]]) -> _Trend | None:
    """The least-squares line of ``points``, or ``None`` with under two distinct x."""
    xs = [x for x, _ in points]
    if len(set(xs)) < 2:
        return None
    x_mean = sum(xs) / len(points)
    y_mean = sum(y for _, y in points) / len(points)
    sxx = sum((x - x_mean) ** 2 for x in xs)
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in points)
    return _Trend(x_mean, y_mean, sxy / sxx, min(xs), max(xs))


def _clipped(trend: _Trend, y_scale: NumericScale) -> tuple[float, float]:
    """The x extent of the trend that stays inside the y axis."""
    if trend.slope == 0:
        return trend.x_lo, trend.x_hi
    at_lo = trend.x_mean + (y_scale.lo - trend.y_mean) / trend.slope
    at_hi = trend.x_mean + (y_scale.hi - trend.y_mean) / trend.slope
    return (
        max(trend.x_lo, min(at_lo, at_hi)),
        min(trend.x_hi, max(at_lo, at_hi)),
    )


def _scale_type(bound: BoundChart, channel: str) -> ScaleType:
    return ScaleType(bound.choice(f"{channel}_scale"))


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "scatter declares a default height"
    width = bound.width
    x_col, y_col = bound.columns["x"], bound.columns["y"]
    x_all, y_all = cartesian.numbers(bound, "x"), cartesian.numbers(bound, "y")
    placed: dict[int, tuple[float, float]] = {}
    for i, (x, y) in enumerate(zip(x_all, y_all, strict=True)):
        if x is not None and y is not None:
            placed[i] = (x, y)
    if not placed:
        return frame.no_data(bound, height=height)

    groups = cartesian.series_groups(bound)
    points = [[placed[i] for i in g.rows if i in placed] for g in groups]
    x_values = [x for series in points for x, _ in series]
    y_values = [y for series in points for _, y in series]

    legend = (
        [LegendEntry(g.label, g.style, "shape") for g in groups]
        if bound.column("color") is not None
        else []
    )
    undrawn = cartesian.undrawn(bound, ("x", "y"))
    trend = bound.flag("trend")
    fits = [_fit(series) if trend else None for series in points]
    lines: list[str] = []
    not_drawn = frame.not_drawn_note(undrawn)
    if not_drawn is not None:
        lines.append(not_drawn)
    if trend:
        short = [g.label for g, fit in zip(groups, fits, strict=True) if fit is None]
        if short:
            lines.append(frame.no_trend_note(short))

    def planned(label_width: float, overhang: float) -> FramePlan:
        return plan_frame(
            width,
            height,
            legend=legend,
            y_label_width=label_width,
            x_label_overhang=overhang,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    def y_axis(plan: FramePlan) -> NumericScale:
        return numeric_scale(
            y_values,
            y_col,
            plan.plot.bottom,
            plan.plot.top,
            scale=_scale_type(bound, "y"),
            include_zero=False,
            nice=True,
            horizontal=False,
        )

    def x_axis(plan: FramePlan) -> NumericScale:
        return numeric_scale(
            x_values,
            x_col,
            plan.plot.left,
            plan.plot.right,
            scale=_scale_type(bound, "x"),
            include_zero=False,
            nice=True,
            horizontal=True,
        )

    y_scale = y_axis(planned(0.0, 0.0))
    y_width = max((text_width(t.label, FONT_TEXT) for t in y_scale.ticks), default=0.0)
    x_scale = x_axis(planned(y_width, 0.0))
    first = text_width(x_scale.ticks[0].label, FONT_TEXT) / 2 if x_scale.ticks else 0.0
    last = text_width(x_scale.ticks[-1].label, FONT_TEXT) / 2 if x_scale.ticks else 0.0
    plan = planned(max(y_width, first - TICK_GAP - TICK_LEN), last)
    x_scale = x_axis(plan)
    y_scale = y_axis(plan)

    drawn_marks: list[str] = []
    for group, series, fit in zip(groups, points, fits, strict=True):
        if not series:
            continue
        drawn_marks.append(
            marks.points(
                [(x_scale.position(x), y_scale.position(y)) for x, y in series],
                group.style,
            )
        )
        if fit is not None:
            start, end = _clipped(fit, y_scale)
            drawn_marks.append(
                marks.trend(
                    x_scale.position(start),
                    y_scale.position(fit.at(start)),
                    x_scale.position(end),
                    y_scale.position(fit.at(end)),
                    group.style.color,
                )
            )

    def extent(channel: str, scale: NumericScale) -> tuple[str, str, str]:
        at = 0 if channel == "x" else 1
        column = x_col if channel == "x" else y_col
        values = bound.values(channel)
        ordered = sorted(placed, key=lambda i: placed[i][at])
        unit = None if column.unit is None else unit_named(column.unit)
        if column.kind is ValueKind.DURATION or (
            unit is not None and unit.family is UnitFamily.DURATION
        ):
            low, high = (
                format_duration(placed[i][at], hours=scale.hours)
                for i in (ordered[0], ordered[-1])
            )
        else:
            low, high = (
                format_value(values[i], column, with_unit=True)
                for i in (ordered[0], ordered[-1])
            )
        return (
            axis_title(column, clock_date=scale.clock_date, hours=scale.hours),
            low,
            high,
        )

    description = frame.describe(
        bound.spec.name,
        bound.request.title,
        [(c, bound.columns[c]) for c in ("x", "y", "color") if c in bound.columns],
        rows=len(bound.rows),
        series=len(groups) if bound.column("color") is not None else None,
        undrawn=undrawn,
        ranges=[extent("x", x_scale), extent("y", y_scale)],
    )
    body = [
        frame.grid(y_scale, plan.plot, horizontal_lines=True),
        frame.grid(x_scale, plan.plot, horizontal_lines=False),
        el("g", {"class": "ck-marks"}, drawn_marks),
        frame.axis(x_scale, plan.plot, Side.BOTTOM, plan=plan),
        frame.axis(y_scale, plan.plot, Side.LEFT, plan=plan),
        frame.legend(plan),
        frame.title_text(plan, bound.request.title),
        frame.notes(plan, lines),
    ]
    return frame.document(
        width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="scatter",
    description="One point per row, with optional colour and least-squares trend",
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
            "The horizontal position of each point.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The vertical position of each point.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One series, with its own marker shape, per distinct value.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "x_scale",
            OptionType.CHOICE,
            "The scale of the x axis.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "y_scale",
            OptionType.CHOICE,
            "The scale of the y axis.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "trend",
            OptionType.BOOLEAN,
            "Draw a least-squares trend line for each series.",
            False,
        ),
        height=_HEIGHT,
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, f"At most {_LIMIT} rows; more are refused."
    ),
    max_series=8,
    draw=_draw,
    validate=_validate,
    check=_check,
)
