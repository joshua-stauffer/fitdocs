"""The `calendar-heatmap` kind: one value per day on a week-by-weekday grid.

Days sit in Monday-start week columns, Monday at the top, each cell sized and
shaded by a value of zero or more (the `cells` module classifies and draws).
A day with no row draws nothing; a row with a date but no value draws a cross;
a zero draws an outline. Rows without a date are counted in the not-drawn note.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Final

from fitdocs.render.charts.kit import cells, frame
from fitdocs.render.charts.kit.cartesian import duplicate_problem, numbers
from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.format import (
    axis_title,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    TICK_GAP,
    TICK_LEN,
    FramePlan,
    Rect,
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
    ChannelSpec,
    KindSpec,
    MarkBound,
    Output,
    OverBound,
    svg_options,
)
from fitdocs.render.charts.kit.theme import TEXT, ink
from fitdocs.render.charts.svg import el, fmt_num, text
from fitdocs.units import UnitFamily, unit_named

CAL_MAX_CELL: Final = 20.0
_MAX_WEEKS: Final = 54
_MIN_HEIGHT: Final = 160
_PROBE_HEIGHT: Final = 1000
_LABEL_DROP: Final = 4.0  # a weekday label's baseline below its row centre
_WEEKDAY_LABELS: Final = ((0, "Mon"), (2, "Wed"), (4, "Fri"), (6, "Sun"))
_ROWS: Final = 7
_FIT_SLACK: Final = 1e-9
_RESERVE_PASSES: Final = 8


# --------------------------------------------------------------------- check


def _present_dates(bound: BoundChart) -> list[date]:
    """The present dates in row order."""
    return [v for v in bound.values("date") if isinstance(v, date)]


def _monday_on_or_before(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weeks_spanned(days: Sequence[date]) -> int:
    """Monday-start week columns from the earliest date's Monday to the latest."""
    first = _monday_on_or_before(min(days))
    return (max(days) - first).days // 7 + 1


def _span_problem(bound: BoundChart) -> tuple[ChartProblem, ...]:
    days = _present_dates(bound)
    if not days:
        return ()
    weeks = _weeks_spanned(days)
    if weeks <= _MAX_WEEKS:
        return ()
    return (
        bound.problem(
            ProblemCode.OVER_BOUND,
            f"calendar-heatmap draws at most {_MAX_WEEKS} weeks; "
            f"these dates span {weeks}.",
            f"Limit the rows to at most {_MAX_WEEKS} weeks of dates, "
            "for example the last 365 days.",
            channel="date",
            column=bound.columns["date"].name,
            rows=weeks,
        ),
    )


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    return (
        *_span_problem(bound),
        *duplicate_problem(bound, ("date",), skip_absent=("date",)),
        *cells.negative_problem(bound, "value"),
    )


# ---------------------------------------------------------------------- draw


def _is_duration(column: Column) -> bool:
    unit = None if column.unit is None else unit_named(column.unit)
    return column.kind is ValueKind.DURATION or (
        unit is not None and unit.family is UnitFamily.DURATION
    )


def _overhangs(scale: NumericScale) -> tuple[float, float]:
    """How far the date tick labels reach past the grid's left edge (to the pad)
    and past its right end."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - scale.end_px)
    return left, right


def _weekday_labels(plot: Rect, pitch: float) -> str:
    labels = [
        el(
            "text",
            {
                "x": fmt_num(plot.left - TICK_LEN - TICK_GAP),
                "y": fmt_num(plot.top + (row + 0.5) * pitch + _LABEL_DROP),
                "text-anchor": "end",
                "font-size": fmt_num(FONT_TEXT),
                **ink(TEXT),
            },
            [text(name)],
        )
        for row, name in _WEEKDAY_LABELS
    ]
    return el("g", {"class": "ck-axis"}, labels)


def _value_range(
    bound: BoundChart, rows: Sequence[int], hours: bool
) -> tuple[str, str] | None:
    """The least and greatest present value of the drawn ``rows``, as text."""
    column = bound.columns["value"]
    figures = numbers(bound, "value")
    present = [i for i in rows if figures[i] is not None]
    if not present:
        return None
    low = min(present, key=lambda i: figures[i] or 0.0)
    high = max(present, key=lambda i: figures[i] or 0.0)
    if _is_duration(column):
        return (
            format_duration(figures[low] or 0.0, hours=hours),
            format_duration(figures[high] or 0.0, hours=hours),
        )
    values = bound.values("value")
    return (
        format_value(values[low], column, with_unit=True),
        format_value(values[high], column, with_unit=True),
    )


def _draw(bound: BoundChart) -> str:
    width = bound.width
    date_col, value_col = bound.columns["date"], bound.columns["value"]
    dates = bound.values("date")
    figures = numbers(bound, "value")
    days = {i: d for i, d in enumerate(dates) if isinstance(d, date)}
    placed = list(days)
    if not placed:
        return frame.no_data(
            bound, height=_MIN_HEIGHT if bound.height is None else bound.height
        )

    first = _monday_on_or_before(min(days.values()))
    weeks = _weeks_spanned(list(days.values()))
    end_ordinal = (first + timedelta(days=7 * weeks)).toordinal()

    scale = cells.binned_scale([figures[i] for i in placed], value_col)
    classes = {i: scale.classify(figures[i]) for i in placed}
    entries = cells.legend_entries(
        scale,
        has_zero=any(c == 0 for c in classes.values()),
        has_absent=any(c is None for c in classes.values()),
    )
    missing = (("date", len(dates) - len(placed)),) if len(placed) < len(dates) else ()
    note = frame.not_drawn_note(missing)
    lines = [] if note is None else [note]
    mon_width = text_width("Mon", FONT_TEXT)

    def plan(height: int, overhang_left: float, overhang_right: float) -> FramePlan:
        return plan_frame(
            width,
            height,
            legend=entries,
            y_label_width=mon_width + overhang_left,
            x_label_overhang=overhang_right,
            has_x_title=True,
            has_y_title=False,
            notes=len(lines),
        )

    def pitch_of(p: FramePlan) -> float:
        pitch = min(p.plot.width / weeks, CAL_MAX_CELL)
        if bound.height is not None:
            # An explicit height is honoured: the seven rows must fit inside it.
            pitch = min(pitch, p.plot.height / _ROWS)
        return pitch

    def date_scale_of(p: FramePlan, pitch: float) -> NumericScale:
        return numeric_scale(
            [float(first.toordinal()), float(end_ordinal)],
            date_col,
            p.plot.left,
            p.plot.left + weeks * pitch,
            scale=ScaleType.TIME,
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    def layout(height: int) -> tuple[FramePlan, float, NumericScale]:
        # Reserve the first and last tick labels' overhang: plan, place the
        # ticks, measure how far they reach past the pad and the grid's right
        # end, and plan again with the larger reserve until nothing reaches
        # past it (the pitch and the ticks move with every plan).
        left = right = 0.0
        for _ in range(_RESERVE_PASSES):
            final = plan(height, left, right)
            pitch = pitch_of(final)
            date_scale = date_scale_of(final, pitch)
            need_left, need_right = _overhangs(date_scale)
            if need_left <= left and need_right <= right:
                break
            left, right = max(left, need_left), max(right, need_right)
        return final, pitch, date_scale

    if bound.height is None:
        probe, probe_pitch, _ = layout(_PROBE_HEIGHT)
        frame_px = _PROBE_HEIGHT - probe.plot.height
        height = max(
            _MIN_HEIGHT, math.ceil(frame_px + _ROWS * probe_pitch - _FIT_SLACK)
        )
    else:
        height = bound.height
    final, pitch, date_scale = layout(height)
    plot = final.plot

    grid_cells = [
        (
            Rect(
                plot.left + ((days[i] - first).days // 7) * pitch,
                plot.top + days[i].weekday() * pitch,
                pitch,
                pitch,
            ),
            classes[i],
        )
        for i in placed
    ]

    date_title = axis_title(
        date_col, clock_date=date_scale.clock_date, hours=date_scale.hours
    )
    lead = entries[0].label
    lead_hours = scale.zero_label.count(":") == 2
    ranges = [
        (
            date_title,
            format_value(min(days.values()), date_col, with_unit=True),
            format_value(max(days.values()), date_col, with_unit=True),
        )
    ]
    value_range = _value_range(bound, placed, lead_hours)
    if value_range is not None:
        ranges.append((lead, *value_range))
    description = frame.describe(
        "calendar-heatmap",
        bound.request.title,
        [("date", date_title), ("value", lead)],
        rows=len(dates),
        series=None,
        undrawn=missing,
        ranges=ranges,
    )
    body = [
        el("g", {"class": "ck-marks"}, cells.cell_marks(grid_cells, scale)),
        frame.axis(date_scale, plot, Side.BOTTOM, title=date_title, plan=final),
        _weekday_labels(plot, pitch),
        cells.legend(final, scale, entries),
        frame.title_text(final, bound.request.title),
        frame.notes(final, lines),
    ]
    return frame.document(
        width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="calendar-heatmap",
    description=(
        "One cell per day in Monday-start week columns, sized and shaded by a "
        "value of zero or more (negative values are refused); a day with no row "
        "draws nothing, so return a zero row to show a rest day"
    ),
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "date",
            (ValueKind.DATE,),
            True,
            "The day of each row; one row per day.",
        ),
        ChannelSpec(
            "value",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The amount shown for the day, zero or more.",
        ),
    ),
    options=svg_options(height=None),
    bound=MarkBound(
        _MAX_WEEKS,
        "weeks",
        OverBound.REFUSE,
        "At most 54 Monday-start week columns: any 366 consecutive days fit.",
    ),
    max_series=None,
    draw=_draw,
    check=_check,
)
