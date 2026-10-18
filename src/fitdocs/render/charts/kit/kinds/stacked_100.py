"""The ``stacked-100`` kind: composition bars, each bar summing to 100 percent.

One bar per x value (bands follow
:func:`~fitdocs.render.charts.kit.cartesian.category_order`). Each part is its
share of its own bar's total, stacked bottom to top in legend order, with a
one pixel gap at every internal boundary (less only beside a segment whose
share is under 2 px) so a boundary never rests on colour alone. A bar whose
parts are all zero has no shares: it is marked with the kit's zero stub and
counted in a note. A missing (x, part) row draws no segment; an absent or
negative part is refused.
"""

from __future__ import annotations

from typing import Final

from fitdocs.render.charts.kit import frame, marks, theme
from fitdocs.render.charts.kit.cartesian import (
    SeriesGroup,
    bound_problem,
    category_bands,
    category_order,
    duplicate_problem,
    numbers,
    series_groups,
    series_problem,
    stack_problems,
)
from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.format import axis_title
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    FramePlan,
    LegendEntry,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.problems import ChartProblem
from fitdocs.render.charts.kit.scales import (
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
    Output,
    OverBound,
    svg_options,
)
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_LIMIT: Final = 400
_BAND_SHARE: Final = 0.8  # of the band
_MAX_BAR: Final = 48.0  # px, one bar
_GAP: Final = 1.0  # px between adjacent segments
_SHARE: Final = Column("share", ValueKind.NUMBER, unit="pct", label="share")


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return (
        *bound_problem(bound, len(bound.rows)),
        *series_problem(bound),
        # An absent x is the ``—`` category, so no key channel is exempt.
        *duplicate_problem(bound, ("x", "color")),
        *stack_problems(bound, x="x", y="y", complete=False),
    )


def _y_hours(bound: BoundChart) -> bool:
    """The y title's duration form: ``h:mm:ss`` once any present part reaches
    an hour; ignored (``True``) when y is not a duration."""
    column = bound.columns["y"]
    unit = unit_named(column.unit) if column.unit is not None else None
    if column.kind is not ValueKind.DURATION and not (
        unit is not None and unit.family is UnitFamily.DURATION
    ):
        return True
    return any(abs(round(v)) >= 3600 for v in numbers(bound, "y") if v is not None)


def _share_scale(plan: FramePlan) -> NumericScale:
    return numeric_scale(
        [0.0, 100.0],
        _SHARE,
        plan.plot.bottom,
        plan.plot.top,
        scale=ScaleType.LINEAR,
        include_zero=True,
        nice=True,
        horizontal=False,
    )


def _parts(
    bound: BoundChart, groups: tuple[SeriesGroup, ...], bands: list[int], count: int
) -> list[list[tuple[float, str]]]:
    """Each band's present ``(value, colour)`` parts in legend order."""
    values = numbers(bound, "y")
    parts: list[list[tuple[float, str]]] = [[] for _ in range(count)]
    for group in groups:
        for row in group.rows:
            value = values[row]
            if value is not None:
                parts[bands[row]].append((value, group.style.color))
    return parts


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None, "stacked-100 declares a default height"
    if not bound.rows:
        return frame.no_data(bound, height=height)

    labels = category_order(bound, "x")
    bands = category_bands(bound, "x")
    groups = series_groups(bound)
    parts = _parts(bound, groups, bands, len(labels))

    legend = tuple(LegendEntry(g.label, g.style, "block") for g in groups)

    zero_total = sum(1 for band in parts if band and sum(v for v, _ in band) == 0)
    lines = (
        []
        if zero_total == 0
        else [
            "Zero total, no shares drawn: "
            f"{zero_total} {'bar' if zero_total == 1 else 'bars'}."
        ]
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

    first = _share_scale(plan_with(0.0))
    plan = plan_with(max(text_width(t.label, FONT_TEXT) for t in first.ticks))
    y_axis = _share_scale(plan)
    x_axis = band_scale(labels, plan.plot.left, plan.plot.right, font_px=FONT_TEXT)
    zero_px = y_axis.position(0.0)

    segments: list[str] = []
    stubs: list[str] = []
    for band, band_parts in enumerate(parts):
        if not band_parts:
            continue
        lo, hi = x_axis.band(band)
        width = min(_MAX_BAR, _BAND_SHARE * (hi - lo))
        left = (lo + hi) / 2 - width / 2
        total = sum(value for value, _ in band_parts)
        if total == 0:
            stubs.append(marks.zero_stub(left, zero_px, width, theme.STROKE.base))
            continue
        # A zero part in a bar with shares has zero height: it draws nothing.
        drawn = [(v, c) for v, c in band_parts if v > 0]
        before = 0.0
        for index, (value, color) in enumerate(drawn):
            low_px = y_axis.position(100.0 * before / total)
            before += value
            high_px = y_axis.position(100.0 * before / total)
            rise = low_px - high_px
            inset = min(_GAP / 2, rise / 4)
            below = inset if index > 0 else 0.0
            above = inset if index < len(drawn) - 1 else 0.0
            segments.append(
                marks.bar(left, low_px - below, width, rise - below - above, color)
            )

    x_title = axis_title(bound.columns["x"])
    y_title = axis_title(_SHARE)
    description = frame.describe(
        "stacked-100",
        bound.request.title,
        [
            ("x", x_title),
            ("y", axis_title(bound.columns["y"], hours=_y_hours(bound))),
            ("color", bound.columns["color"]),
        ],
        rows=len(bound.rows),
        series=len(groups),
        undrawn=(),
        ranges=(
            (x_title, labels[0], labels[-1]),
            (y_title, y_axis.ticks[0].label, y_axis.ticks[-1].label),
        ),
    )
    body = [
        frame.grid(y_axis, plan.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, [*segments, *stubs]),
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


KIND: Final = KindSpec(
    name="stacked-100",
    description="Bars that split each category or date into shares of 100%",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The category or date each bar stands at.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "Each part's value; never absent or negative.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            True,
            "The part: one segment per value, in legend order, bottom to top.",
        ),
    ),
    options=svg_options(height=320),
    bound=MarkBound(
        _LIMIT,
        "rows",
        OverBound.REFUSE,
        f"A stacked-100 chart draws at most {_LIMIT} rows; more are refused.",
    ),
    max_series=8,
    draw=_draw,
    check=_check,
)
