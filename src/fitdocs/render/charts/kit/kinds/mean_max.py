"""The ``mean-max`` kind: the best mean value over each duration.

One curve per period (the colour channel) on a logarithmic duration axis, each
joined in ascending duration and broken wherever its value is absent. The x
ticks are landmark durations (5 s, 1 min, 5 min, 20 min, 1 h first) picked from
the kit's log-duration ladder so their labels do not collide; the labels and
the x axis title share one form (``h:mm:ss`` when the axis reaches an hour,
else ``m:ss``). The kind draws the rows it is given; the best efforts are
computed by the query.
"""

from __future__ import annotations

import dataclasses
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
from fitdocs.render.charts.kit.format import (
    axis_title,
    format_duration,
    format_durations,
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
from fitdocs.render.charts.kit.marks import line_series
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import (
    NumericScale,
    ScaleType,
    Side,
    Tick,
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
from fitdocs.render.charts.kit.ticks import LOG_DURATION_TICKS
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 1000
_DEFAULT_HEIGHT: Final = 320
_SECONDS: Final = "s"
_HOUR: Final = 3600.0
_LABEL_GAP: Final = 10.0

# Which ladder durations are labelled first: 1 min, 1 h, 5 min, 20 min, 5 s,
# then the rest. A candidate is kept only if its label clears every kept one.
LANDMARK_PRIORITY: Final[tuple[float, ...]] = (
    60, 3600, 300, 1200, 5, 1, 15, 30, 120, 600,
    1800, 7200, 10800, 21600, 43200, 86400, 2, 10,
)  # fmt: skip


def _is_duration(column: Column) -> bool:
    if column.kind is ValueKind.DURATION:
        return True
    unit = None if column.unit is None else unit_named(column.unit)
    return unit is not None and unit.family is UnitFamily.DURATION


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    x = bound.column("x")
    if x is None or x.kind is not ValueKind.NUMBER or x.unit == _SECONDS:
        return ()
    fitting = tuple(
        column.name
        for column in bound.all_columns
        if column.kind is ValueKind.DURATION
        or (column.kind is ValueKind.NUMBER and column.unit == _SECONDS)
    )
    unit = "no unit" if x.unit is None else f"unit {x.unit}"
    return (
        bound.problem(
            ProblemCode.CHANNEL_UNIT,
            f"Channel x needs durations, but column '{x.name}' has {unit}, not "
            "seconds.",
            "Bind x to a duration column, or to seconds such as duration_s.",
            channel="x",
            column=x.name,
            accepted=fitting,
        ),
    )


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    problems = [
        *bound_problem(bound, len(bound.rows)),
        *series_problem(bound),
        *duplicate_problem(bound, ("color", "x"), skip_absent=("x",)),
    ]
    for problem in log_problem(bound, "x"):
        # chart-kit's fix names an x_scale option this kind does not have.
        problems.append(
            dataclasses.replace(
                problem,
                fix="Remove the rows with a duration at or below zero.",
                option=None,
            )
        )
    return tuple(problems)


def _landmarks(scale: NumericScale) -> tuple[Tick, ...]:
    """The accepted landmark ticks of ``scale``, ascending, labelled in one form.

    The labels come from ``format_durations`` over every candidate in the
    domain, so their form is ``h:mm:ss`` exactly when the axis's upper end
    reaches an hour (see the comment below), matching the axis title.
    """
    candidates = [
        value
        for value in LANDMARK_PRIORITY
        if value in LOG_DURATION_TICKS and scale.lo <= value <= scale.hi
    ]
    # Candidates are ladder durations inside [lo, hi]. If hi < 3600 all are
    # below an hour; if lo <= 3600 <= hi, 3600 itself is a candidate; if
    # lo > 3600 all are above an hour. So ``format_durations`` picks h:mm:ss
    # exactly when hi >= 3600, the form ``_x_axis`` gives the title.
    labels = dict(zip(candidates, format_durations(candidates), strict=True))
    accepted: list[tuple[float, float, float]] = []  # (value, pixel, label width)
    for value in candidates:
        at = scale.position(value)
        width = text_width(labels[value], FONT_TEXT)
        if all(
            abs(at - other) >= (width + other_width) / 2 + _LABEL_GAP
            for _, other, other_width in accepted
        ):
            accepted.append((value, at, width))
    return tuple(Tick(value, labels[value]) for value, _, _ in sorted(accepted))


def _x_axis(
    values: Sequence[float], column: Column, plot: Rect
) -> tuple[NumericScale, bool]:
    """The log duration scale and whether its labels and title use ``h:mm:ss``."""
    base = numeric_scale(
        values,
        column,
        plot.left,
        plot.right,
        scale=ScaleType.LOG,
        include_zero=False,
        nice=True,
        horizontal=True,
    )
    hours = base.hi >= _HOUR
    ticks = _landmarks(base)
    if not ticks:  # the domain holds no ladder duration (for example, multi-day)
        return base, base.hours
    return dataclasses.replace(base, ticks=ticks, hours=hours), hours


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
    bound: BoundChart, channel: str, rows: Sequence[int], hours: bool
) -> tuple[str, str]:
    """The smallest and largest present value of ``channel`` in ``rows``.

    A duration channel writes them in the axis's own form (``hours``); any
    other channel, pace included, writes them with the column's unit.
    """
    column = bound.columns[channel]
    values = bound.values(channel)
    numeric = numbers(bound, channel)
    lowest = min(rows, key=lambda i: numeric[i] or 0.0)
    highest = max(rows, key=lambda i: numeric[i] or 0.0)

    def shown(index: int) -> str:
        seconds = numeric[index]
        if _is_duration(column) and seconds is not None:
            return format_duration(seconds, hours=hours)
        return format_value(values[index], column, with_unit=True)

    return shown(lowest), shown(highest)


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "mean-max declares a default height"
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
        scale=ScaleType.LINEAR,
        include_zero=bound.flag("y_zero"),
        nice=True,
        horizontal=False,
    )
    label_width = max(
        (text_width(t.label, FONT_TEXT) for t in y_scale.ticks), default=0.0
    )
    provisional = plan(label_width, 0.0)
    left, right = _overhangs(
        _x_axis(x_present, x_col, provisional.plot)[0], provisional.plot
    )
    final = plan(label_width + left, right)
    x_scale, hours = _x_axis(x_present, x_col, final.plot)

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

    x_title = axis_title(x_col, hours=hours)
    y_title = axis_title(y_col, clock_date=y_scale.clock_date, hours=y_scale.hours)
    body = [
        frame.grid(y_scale, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, marks),
        frame.axis(x_scale, final.plot, Side.BOTTOM, title=x_title, plan=final),
        frame.axis(y_scale, final.plot, Side.LEFT, title=y_title, plan=final),
        frame.legend(final),
        frame.title_text(final, bound.request.title),
        frame.notes(final, lines),
    ]
    x_low, x_high = _extremes(bound, "x", rows, hours)
    y_low, y_high = _extremes(bound, "y", rows, y_scale.hours)
    drawn_titles = {"x": x_title, "y": y_title}
    channels = [
        (name, drawn_titles.get(name, column)) for name, column in bound.columns.items()
    ]
    description = frame.describe(
        "mean-max",
        bound.request.title,
        channels,
        rows=len(bound.rows),
        series=len(groups) if coloured else None,
        undrawn=counts,
        ranges=[(x_title, x_low, x_high), (y_title, y_low, y_high)],
    )
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="mean-max",
    description="Best-effort curves over a log duration axis, one per period",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The duration of each best effort: a duration, or a number in seconds.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The best mean value over that duration: a number or duration.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One curve per value of this column, such as a season.",
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
    max_series=8,
    draw=_draw,
    validate=_validate,
    check=_check,
)
