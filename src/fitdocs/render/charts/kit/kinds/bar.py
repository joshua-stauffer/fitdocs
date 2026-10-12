"""The ``bar`` kind: vertical bars per category or date, grouped or stacked.

Bands follow :func:`~fitdocs.render.charts.kit.cartesian.category_order`
(first appearance, dates ascending, the absent category ``—`` last). Grouped
bars sit side by side in legend order across 80 % of the band, each at most
48 px wide; stacked segments rise in legend order. An absent value draws
nothing and is counted in a note; a zero draws the two pixel stub.
"""

from __future__ import annotations

from typing import Final

from fitdocs.render.charts.kit import frame, marks
from fitdocs.render.charts.kit.cartesian import (
    SeriesGroup,
    bound_problem,
    category_order,
    duplicate_problem,
    numbers,
    series_groups,
    series_problem,
    stack_problems,
    undrawn,
)
from fitdocs.render.charts.kit.data import Value, ValueKind
from fitdocs.render.charts.kit.format import (
    ABSENT,
    axis_title,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    FramePlan,
    LegendEntry,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.problems import ChartProblem
from fitdocs.render.charts.kit.scales import (
    BandScale,
    NumericScale,
    ScaleType,
    Side,
    band_scale,
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
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 200
_BAND_SHARE: Final = 0.8  # of the band, all grouped bars together
_MAX_BAR: Final = 48.0  # px, one bar


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    problems = (
        *bound_problem(bound, len(bound.rows)),
        *series_problem(bound),
        # An absent x is the ``—`` category, so no key channel is exempt.
        *duplicate_problem(bound, ("x", "color")),
    )
    if bound.flag("stack"):
        problems = (
            *problems,
            *stack_problems(bound, x="x", y="y", complete=False),
        )
    return problems


def _label(bound: BoundChart, value: Value) -> str:
    return format_value(value, bound.columns["x"], with_unit=False)


def _bands(bound: BoundChart, labels: tuple[str, ...]) -> list[int]:
    """The band index of each row (an absent x belongs to the ``—`` band)."""
    index = {label: i for i, label in enumerate(labels)}
    return [
        index[ABSENT if value is None else _label(bound, value)]
        for value in bound.values("x")
    ]


def _y_scale(bound: BoundChart, values: list[float], plan: FramePlan) -> NumericScale:
    return numeric_scale(
        values,
        bound.columns["y"],
        plan.plot.bottom,
        plan.plot.top,
        scale=ScaleType.LINEAR,
        include_zero=True,
        nice=True,
        horizontal=False,
    )


def _extremes(bound: BoundChart, y_axis: NumericScale) -> tuple[str, str]:
    """The formatted smallest and largest present y, with units.

    A duration-family axis formats both in the axis's own ``h:mm:ss`` or
    ``m:ss`` form, so the range reads like the axis title says.
    """
    column = bound.columns["y"]
    present = [
        (number, cell)
        for number, cell in zip(numbers(bound, "y"), bound.values("y"), strict=True)
        if number is not None
    ]
    low = min(present, key=lambda pair: pair[0])
    high = max(present, key=lambda pair: pair[0])
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


def _segment(left: float, width: float, base: float, rise: float, color: str) -> str:
    """One bar from the pixel ``base``, ``rise`` px up (down when negative)."""
    if rise == 0:
        return marks.zero_stub(left, base, width, color)
    return marks.bar(left, base, width, rise, color)


def _grouped(
    bound: BoundChart,
    groups: tuple[SeriesGroup, ...],
    bands: list[int],
    x_axis: BandScale,
    y_axis: NumericScale,
) -> list[str]:
    zero_px = y_axis.position(0.0)
    values = numbers(bound, "y")
    drawn: list[str] = []
    for slot, group in enumerate(groups):
        for row in group.rows:
            value = values[row]
            if value is None:
                continue
            lo, hi = x_axis.band(bands[row])
            width = min(_MAX_BAR, _BAND_SHARE * (hi - lo) / len(groups))
            left = (lo + hi) / 2 - len(groups) * width / 2 + slot * width
            rise = zero_px - y_axis.position(value)
            drawn.append(_segment(left, width, zero_px, rise, group.style.color))
    return drawn


def _stacked(
    bound: BoundChart,
    groups: tuple[SeriesGroup, ...],
    bands: list[int],
    x_axis: BandScale,
    y_axis: NumericScale,
) -> list[str]:
    values = numbers(bound, "y")
    tops = [0.0] * len(x_axis.categories)
    drawn: list[str] = []
    stubs: list[str] = []
    for group in groups:
        for row in group.rows:
            value = values[row]
            if value is None:
                continue
            band = bands[row]
            lo, hi = x_axis.band(band)
            width = min(_MAX_BAR, _BAND_SHARE * (hi - lo))
            base = y_axis.position(tops[band])
            rise = base - y_axis.position(tops[band] + value)
            # A stub is drawn after every segment so no later segment covers it.
            (stubs if rise == 0 else drawn).append(
                _segment(
                    (lo + hi) / 2 - width / 2, width, base, rise, group.style.color
                )
            )
            tops[band] += value
    return [*drawn, *stubs]


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "bar declares a default height"
    values = numbers(bound, "y")
    if all(value is None for value in values):
        return frame.no_data(bound, height=height)

    stacked = bound.flag("stack")
    labels = category_order(bound, "x")
    bands = _bands(bound, labels)
    groups = series_groups(bound)
    coloured = bound.column("color") is not None
    not_drawn = undrawn(bound, ("y",))
    note = frame.not_drawn_note(not_drawn)
    lines = [] if note is None else [note]

    if stacked:
        totals = [0.0] * len(labels)
        for band, value in zip(bands, values, strict=True):
            if value is not None:
                totals[band] += value
        domain = totals
    else:
        domain = [value for value in values if value is not None]

    legend = (
        tuple(LegendEntry(g.label, g.style, "block") for g in groups)
        if coloured
        else ()
    )

    def plan_with(label_width: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=legend,
            y_label_width=label_width,
            x_label_overhang=0.0,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    first = _y_scale(bound, domain, plan_with(0.0))
    plan = plan_with(max(text_width(t.label, FONT_TEXT) for t in first.ticks))
    y_axis = _y_scale(bound, domain, plan)
    x_axis = band_scale(labels, plan.plot.left, plan.plot.right, font_px=FONT_TEXT)

    build = _stacked if stacked else _grouped
    low, high = _extremes(bound, y_axis)
    channels = [
        (ch, bound.columns[ch]) for ch in ("x", "y", "color") if bound.column(ch)
    ]
    description = frame.describe(
        "bar",
        bound.request.title,
        channels,
        rows=len(bound.rows),
        series=len(groups) if coloured else None,
        undrawn=not_drawn,
        ranges=(
            (axis_title(bound.columns["x"]), labels[0], labels[-1]),
            (
                axis_title(
                    bound.columns["y"],
                    clock_date=y_axis.clock_date,
                    hours=y_axis.hours,
                ),
                low,
                high,
            ),
        ),
    )
    body = [
        frame.grid(y_axis, plan.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, build(bound, groups, bands, x_axis, y_axis)),
        frame.axis(
            x_axis,
            plan.plot,
            Side.BOTTOM,
            title=axis_title(bound.columns["x"]),
            plan=plan,
        ),
        frame.axis(y_axis, plan.plot, Side.LEFT, plan=plan),
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


KIND: Final = KindSpec(
    name="bar",
    description="Vertical bars per category or date, grouped or stacked by colour",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The category or date each bar group stands at.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The bar's value; the axis always includes zero.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "Splits each group into one bar per value, in legend order.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "stack",
            OptionType.BOOLEAN,
            "Stack the colour series instead of placing them side by side.",
            False,
        ),
        height=320,
    ),
    bound=MarkBound(
        _LIMIT,
        "rows",
        OverBound.REFUSE,
        f"A bar chart draws at most {_LIMIT} rows; more are refused.",
    ),
    max_series=8,
    draw=_draw,
    check=_check,
)
