"""What every x/y kind shares: series, numbers, counts and the shared checks.

Absent values are never replaced: an absent colour is its own series labelled
:data:`~fitdocs.render.charts.kit.format.ABSENT`, ordered last, and an absent
number stays ``None``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from fitdocs.render.charts.kit import frame
from fitdocs.render.charts.kit.data import Value, ValueKind, to_number
from fitdocs.render.charts.kit.format import (
    ABSENT,
    clean_text,
    display_label,
    format_value,
)
from fitdocs.render.charts.kit.layout import FONT_TEXT, PAD, FramePlan, text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import BandScale, band_scale
from fitdocs.render.charts.kit.schema import BoundChart
from fitdocs.render.charts.kit.theme import MAX_SERIES, SeriesStyle, series_style


@dataclass(frozen=True)
class SeriesGroup:
    label: str  # formatted colour value, or ABSENT
    rows: tuple[int, ...]  # row indices in row order
    style: SeriesStyle


def _y_label(bound: BoundChart) -> str:
    y = bound.column("y")
    assert y is not None, "series need a bound y channel"
    return display_label(y)


def _grouped(bound: BoundChart, channel: str) -> list[tuple[str, tuple[int, ...]]]:
    """``(label, rows)`` per series: first appearance, absent last."""
    column = bound.column(channel)
    if column is None:
        return [(_y_label(bound), tuple(range(len(bound.rows))))]
    present: dict[Value, list[int]] = {}
    absent: list[int] = []
    for index, value in enumerate(bound.values(channel)):
        if value is None:
            absent.append(index)
        else:
            present.setdefault(value, []).append(index)
    groups = [
        (format_value(value, column, with_unit=False), tuple(rows))
        for value, rows in present.items()
    ]
    if absent:
        groups.append((ABSENT, tuple(absent)))
    return groups


def series_groups(bound: BoundChart, channel: str = "color") -> tuple[SeriesGroup, ...]:
    """The series of ``channel``; more than ``MAX_SERIES`` cannot be styled."""
    return tuple(
        SeriesGroup(label, rows, series_style(index))
        for index, (label, rows) in enumerate(_grouped(bound, channel))
    )


def _category_keys(bound: BoundChart, channel: str) -> list[Value]:
    """The distinct present values of ``channel`` in band order (absent excluded)."""
    column = bound.columns[channel]
    distinct: list[Value] = list(
        dict.fromkeys(v for v in bound.values(channel) if v is not None)
    )
    if column.kind in (ValueKind.DATE, ValueKind.DATETIME):
        distinct.sort(key=lambda v: to_number(v, column.kind) or 0.0)
    return distinct


def category_order(bound: BoundChart, channel: str) -> tuple[str, ...]:
    """Labels in first appearance; dates and date-times ascending; absent last.

    One label per distinct raw value, so two values that format alike give two
    equal labels: bands are keyed on :func:`category_bands`, never on a label.
    """
    column = bound.columns[channel]
    order = [
        format_value(v, column, with_unit=False) for v in _category_keys(bound, channel)
    ]
    if any(v is None for v in bound.values(channel)):
        order.append(ABSENT)
    return tuple(order)


def category_bands(bound: BoundChart, channel: str) -> list[int]:
    """The index into :func:`category_order` of each row's value.

    Keyed on the raw value, so categories that format alike keep their own
    band; an absent value belongs to the last (``—``) band.
    """
    position = {v: i for i, v in enumerate(_category_keys(bound, channel))}
    absent = len(position)
    return [absent if v is None else position[v] for v in bound.values(channel)]


def numbers(bound: BoundChart, channel: str) -> tuple[float | None, ...]:
    """The channel's numeric view in row order; absent stays ``None``."""
    kind = bound.columns[channel].kind
    return tuple(to_number(v, kind) for v in bound.values(channel))


def undrawn(bound: BoundChart, channels: Sequence[str]) -> tuple[tuple[str, int], ...]:
    """Rows that leave no mark, by the first listed channel they are absent on."""
    counts = dict.fromkeys(channels, 0)
    present = [bound.values(ch) for ch in channels if bound.column(ch) is not None]
    names = [ch for ch in channels if bound.column(ch) is not None]
    for index in range(len(bound.rows)):
        for name, values in zip(names, present, strict=True):
            if values[index] is None:
                counts[name] += 1
                break
    return tuple((name, counts[name]) for name in names if counts[name] > 0)


def bound_problem(bound: BoundChart, count: int) -> tuple[ChartProblem, ...]:
    limit = bound.spec.bound.limit
    if count <= limit:
        return ()
    return (
        bound.problem(
            ProblemCode.OVER_BOUND,
            f"{bound.spec.name} draws at most {limit} {bound.spec.bound.counts}; "
            f"this data has {count}.",
            "Aggregate the rows (for example by day or week) or limit them to "
            f"at most {limit}.",
            rows=count,
        ),
    )


def series_problem(bound: BoundChart) -> tuple[ChartProblem, ...]:
    count = len(_grouped(bound, "color"))
    if count <= MAX_SERIES:
        return ()
    colour = bound.column("color")
    return (
        bound.problem(
            ProblemCode.TOO_MANY_SERIES,
            f"{bound.spec.name} draws at most {MAX_SERIES} series; "
            f"the colour channel yields {count}.",
            "Filter the rows or bind a colour column with at most "
            f"{MAX_SERIES} distinct values.",
            channel="color",
            column=None if colour is None else colour.name,
        ),
    )


def _joined(parts: Sequence[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def duplicate_problem(
    bound: BoundChart, keys: Sequence[str], *, skip_absent: Sequence[str] = ()
) -> tuple[ChartProblem, ...]:
    """The first row whose ``keys`` repeat an earlier row's.

    Absent is a key value, except that a row absent on a ``skip_absent``
    channel is exempt; a key channel that is not bound is left out.
    """
    bound_keys = [k for k in keys if bound.column(k) is not None]
    if not bound_keys:
        return ()
    columns = [bound.columns[k] for k in bound_keys]
    per_key = [bound.values(k) for k in bound_keys]
    exempt = [bound.values(k) for k in skip_absent if bound.column(k) is not None]
    seen: dict[tuple[Value, ...], int] = {}
    for index in range(len(bound.rows)):
        if any(values[index] is None for values in exempt):
            continue
        position = tuple(values[index] for values in per_key)
        if position not in seen:
            seen[position] = index
            continue
        parts = [
            f"{display_label(col)} ({format_value(value, col, with_unit=True)})"
            for col, value in zip(columns, position, strict=True)
        ]
        return (
            bound.problem(
                ProblemCode.DUPLICATE_POSITION,
                f"Row {index} repeats row {seen[position]}, which has the same "
                f"{_joined(parts)}.",
                "Aggregate the rows that share this position, or bind a "
                f"column to {' or '.join(keys)} that separates them.",
                row=index,
            ),
        )
    return ()


def log_problem(bound: BoundChart, channel: str) -> tuple[ChartProblem, ...]:
    """The first present value at or below zero on a logarithmic axis."""
    column = bound.columns[channel]
    for index, (value, number) in enumerate(
        zip(bound.values(channel), numbers(bound, channel), strict=True)
    ):
        if number is not None and number <= 0:
            text = format_value(value, column, with_unit=True)
            return (
                bound.problem(
                    ProblemCode.LOG_DOMAIN,
                    f"Column {column.name} holds {text} in row {index}, "
                    "which a logarithmic scale cannot draw.",
                    f"Set {channel}_scale to linear or remove the rows with "
                    "values at or below zero.",
                    channel=channel,
                    column=column.name,
                    option=f"{channel}_scale",
                    row=index,
                ),
            )
    return ()


def _x_union(bound: BoundChart, x: str) -> list[Value]:
    """Distinct present x values: ascending for numbers and times, else as met."""
    kind = bound.columns[x].kind
    distinct: list[Value] = list(
        dict.fromkeys(v for v in bound.values(x) if v is not None)
    )
    if kind not in (ValueKind.CATEGORY, ValueKind.BOOLEAN):
        distinct.sort(key=lambda v: to_number(v, kind) or 0.0)
    return distinct


def stack_problems(
    bound: BoundChart, *, x: str, y: str, complete: bool
) -> tuple[ChartProblem, ...]:
    """Absent, negative and (when ``complete``) missing values a stack cannot hold."""
    x_col, y_col = bound.columns[x], bound.columns[y]
    y_label = display_label(y_col)
    x_label = display_label(x_col)
    y_values = bound.values(y)
    y_numbers = numbers(bound, y)
    found: list[ChartProblem] = []

    absent_row = next((i for i, v in enumerate(y_values) if v is None), None)
    if absent_row is not None:
        found.append(
            bound.problem(
                ProblemCode.STACK_ABSENT,
                f"Row {absent_row} has no {y_label}, "
                "which a stacked chart cannot draw.",
                "Unstack the chart or supply the missing value.",
                channel=y,
                column=y_col.name,
                row=absent_row,
            )
        )
    negative_row = next(
        (i for i, n in enumerate(y_numbers) if n is not None and n < 0), None
    )
    if negative_row is not None:
        text = format_value(y_values[negative_row], y_col, with_unit=True)
        found.append(
            bound.problem(
                ProblemCode.STACK_NEGATIVE,
                f"Row {negative_row} holds the negative {y_label} {text}, "
                "which a stacked chart cannot add up.",
                "Unstack the chart or replace the negative values.",
                channel=y,
                column=y_col.name,
                row=negative_row,
            )
        )
    if complete:
        x_values = bound.values(x)
        for label, rows in _grouped(bound, "color"):
            have = {x_values[i] for i in rows}
            gaps = [v for v in _x_union(bound, x) if v not in have]
            if not gaps:
                continue
            missing = gaps[0]
            found.append(
                bound.problem(
                    ProblemCode.STACK_INCOMPLETE,
                    f"Series {label} has no row at {x_label} "
                    f"{format_value(missing, x_col, with_unit=True)}, "
                    "which a stacked chart needs.",
                    "Unstack the chart or supply a row for every series at "
                    f"every {x_label}.",
                    channel=x,
                    column=x_col.name,
                )
            )
            break
    return tuple(found)


_EDGE_SLACK = 0.5  # px kept beyond the first label's half width
_EDGE_PASSES = 6
_EDGE_SHARE = 0.25  # most of the canvas width a first label may claim


def band_x_axis(
    labels: Sequence[str], plan_with: Callable[[float], FramePlan], label_width: float
) -> tuple[FramePlan, BandScale]:
    """The plan and band scale of a bottom band axis whose first label is whole.

    ``plan_with`` builds the frame plan from the width reserved for the y tick
    labels. The first band's label is centred half a band in from the plot's
    left edge, so it is cut at the canvas edge unless the left margin holds its
    half width: this widens the margin by exactly the shortfall (the way the
    numeric kinds reserve their first tick's overhang), re-planning because the
    narrower plot can thin the labels differently. A label longer than the room
    its band pitch allows is fitted to that room, which the shortfall honours;
    a label wider than a quarter of the canvas reserves only that quarter (the
    rest is cut at the canvas edge as before), so one long category cannot
    squeeze the plot.
    """
    extra = 0.0
    for _ in range(_EDGE_PASSES):
        plan = plan_with(label_width + extra)
        scale = band_scale(labels, plan.plot.left, plan.plot.right, font_px=FONT_TEXT)
        shown = min(
            text_width(clean_text(labels[0]), FONT_TEXT),
            frame.band_label_room(scale),
            _EDGE_SHARE * plan.width,
        )
        short = shown / 2 - (scale.centre(0) - PAD)
        if short <= 0:
            break
        extra += short + _EDGE_SLACK
    return plan, scale
