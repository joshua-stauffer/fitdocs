"""Binned value scale, grid cell marks and grid scale legend for the grid kinds.

``binned_scale`` puts the present values into at most five bins above zero,
each bin excluding its lower edge and including its upper one, with zero and
absent as classes of their own. ``cell_marks`` draws one SVG path per value
class (never one per cell): a filled square whose area grows with the bin, an
outlined square for zero and a cross for absent, so magnitude, zero and absent
differ in shape as well as colour. The kind owns the grid geometry; this module
classifies values and draws inside the cells it is handed. Absent is ``None``
and is never classified as zero.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from fitdocs.render.charts.kit.data import Column, ValueKind, to_number
from fitdocs.render.charts.kit.format import (
    axis_title,
    clean_text,
    display_label,
    format_durations,
    format_number_tick,
    format_pace,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    LEGEND_GAP,
    LEGEND_ROW,
    LEGEND_SWATCH,
    FramePlan,
    LegendEntry,
    Rect,
)
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import BoundChart
from fitdocs.render.charts.kit.theme import STROKE, TEXT, SeriesStyle, Shape, ink
from fitdocs.render.charts.kit.ticks import linear_ticks
from fitdocs.render.charts.palette import SEQUENTIAL_RAMP
from fitdocs.render.charts.svg import el, fmt_num, text
from fitdocs.units import Unit, UnitFamily, unit_named

MAX_BINS: Final = 5
CELL_GAP: Final = 1.0  # px inset on each side of a cell's pitch box
MIN_MARK: Final = 2.0  # smallest drawn square side, px
ABSENT_LABEL: Final = "no value"

_OUTLINE_INSET: Final = 0.5
_CROSS_INSET: Final = 0.25  # fraction of the inner box: the cross spans the middle half
_STROKE_WIDTH: Final = "1"
_SWATCH_CELL: Final = 10.0  # the legend swatch is a 10 px cell
_LEGEND_MID: Final = 7.0  # swatch centre below the row top (as frame.legend)
_LEGEND_TEXT_DROP: Final = 11.0  # legend text baseline below its row top

_TAG_SHAPE: Final = Shape.SQUARE  # ``swatch`` is placement only; never drawn


@dataclass(frozen=True)
class BinnedScale:
    column: Column  # the value column
    edges: tuple[
        float, ...
    ]  # (0.0, e1, ..., en); n = len(edges) - 1, 0 <= n <= MAX_BINS
    labels: tuple[str, ...]  # formatted e1 ... en (one form for durations)
    zero_label: str  # the formatted zero ("0", "0:00", "0%")

    @property
    def bins(self) -> int:
        return len(self.edges) - 1

    def classify(self, value: float | None) -> int | None:
        """``None`` absent, ``0`` zero, ``1..n`` the bin (upper edge included).

        A positive value above the last edge lands in bin ``n``: the edges come
        from ``linear_ticks``, whose tolerance and rounding can leave the last
        edge a hair below the data maximum, and that maximum must still classify.
        """
        if value is None:
            return None
        if value < 0:
            raise ValueError(f"a binned scale takes no negative value, got {value!r}")
        if value == 0:
            return 0
        for index in range(1, len(self.edges)):
            if value <= self.edges[index]:
                return index
        if self.bins == 0:
            raise ValueError(f"{value!r} is positive but this scale has no bins")
        return self.bins

    def color(self, bin_index: int) -> str:
        """The top ``n`` ramp entries, so the largest bin is always the last."""
        self._check_bin(bin_index)
        return SEQUENTIAL_RAMP[MAX_BINS - self.bins + bin_index - 1]

    def fraction(self, bin_index: int) -> float:
        """The side fraction of a bin's square: area is proportional to the bin."""
        self._check_bin(bin_index)
        return math.sqrt(bin_index / self.bins)

    def _check_bin(self, bin_index: int) -> None:
        if not 1 <= bin_index <= self.bins:
            raise ValueError(
                f"bin {bin_index!r} is not one of 1..{self.bins} of this scale"
            )


def _unit_family(column: Column) -> tuple[Unit | None, UnitFamily | None]:
    unit = unit_named(column.unit) if column.unit is not None else None
    return unit, None if unit is None else unit.family


def _is_clock_duration(column: Column) -> bool:
    _, family = _unit_family(column)
    return column.kind is ValueKind.DURATION or family is UnitFamily.DURATION


def _hours_form(scale: BinnedScale) -> bool:
    """Whether the edge labels are in ``h:mm:ss``, read from the labels themselves
    (the zero label is formatted with the edges, so it shares their form)."""
    return scale.zero_label.count(":") == 2


def binned_scale(values: Sequence[float | None], column: Column) -> BinnedScale:
    """The bins of the present ``values`` (their numeric view; ``None`` ignored)."""
    present = [v for v in values if v is not None]
    unit, family = _unit_family(column)
    clock = _is_clock_duration(column)
    positive = [v for v in present if v > 0]
    edges: tuple[float, ...]
    if positive:
        whole = all(float(v).is_integer() for v in present)
        ladder = clock or family is UnitFamily.PACE
        _, _, edges = linear_ticks(
            0.0, max(positive), MAX_BINS + 1, duration=ladder, integer=whole
        )
    else:
        edges = (0.0,)
    if clock:
        everything = format_durations(edges)
        zero_label, labels = everything[0], everything[1:]
    elif family is UnitFamily.PACE:
        zero_label, labels = format_pace(0.0), tuple(format_pace(e) for e in edges[1:])
    else:
        step = edges[1] if len(edges) > 1 else 1.0
        zero_label = format_number_tick(0.0, step, unit)
        labels = tuple(format_number_tick(e, step, unit) for e in edges[1:])
    return BinnedScale(column, edges, labels, zero_label)


def negative_problem(bound: BoundChart, channel: str) -> tuple[ChartProblem, ...]:
    """Refuse a negative value: names the column, the first row and the count."""
    column = bound.column(channel)
    if column is None:
        return ()
    numbers = [to_number(v, column.kind) for v in bound.values(channel)]
    negative = [i for i, n in enumerate(numbers) if n is not None and n < 0]
    if not negative:
        return ()
    return (
        bound.problem(
            ProblemCode.NEGATIVE_VALUE,
            f"{display_label(column)} has a negative value at row {negative[0]}; "
            f"{bound.spec.name} shades values from zero up.",
            "Use a line or bar chart for signed values, "
            "or select a value that cannot be negative.",
            channel=channel,
            column=column.name,
            row=negative[0],
            rows=len(negative),
        ),
    )


# ---------------------------------------------------------------- cell marks


def _inner(rect: Rect) -> Rect:
    return Rect(
        rect.left + CELL_GAP,
        rect.top + CELL_GAP,
        rect.width - 2 * CELL_GAP,
        rect.height - 2 * CELL_GAP,
    )


def _box(left: float, top: float, width: float, height: float) -> str:
    return (
        f"M{fmt_num(left)} {fmt_num(top)}H{fmt_num(left + width)}"
        f"V{fmt_num(top + height)}H{fmt_num(left)}Z"
    )


def _bin_subpath(rect: Rect, fraction: float) -> str:
    inner = _inner(rect)
    width = max(MIN_MARK, inner.width * fraction)
    height = max(MIN_MARK, inner.height * fraction)
    left = inner.left + (inner.width - width) / 2
    top = inner.top + (inner.height - height) / 2
    return _box(left, top, width, height)


def _zero_subpath(rect: Rect) -> str:
    inner = _inner(rect)
    return _box(
        inner.left + _OUTLINE_INSET,
        inner.top + _OUTLINE_INSET,
        inner.width - 2 * _OUTLINE_INSET,
        inner.height - 2 * _OUTLINE_INSET,
    )


def _cross_subpath(rect: Rect) -> str:
    inner = _inner(rect)
    left = inner.left + inner.width * _CROSS_INSET
    right = inner.right - inner.width * _CROSS_INSET
    top = inner.top + inner.height * _CROSS_INSET
    bottom = inner.bottom - inner.height * _CROSS_INSET
    return (
        f"M{fmt_num(left)} {fmt_num(top)}L{fmt_num(right)} {fmt_num(bottom)}"
        f"M{fmt_num(left)} {fmt_num(bottom)}L{fmt_num(right)} {fmt_num(top)}"
    )


def cell_marks(
    cells: Sequence[tuple[Rect, int | None]], scale: BinnedScale
) -> list[str]:
    """One path per non-empty class, back to front: bins ascending, zero, absent."""
    for _, value_class in cells:
        if value_class is not None and not 0 <= value_class <= scale.bins:
            raise ValueError(
                f"class {value_class!r} is not absent, zero or one of "
                f"1..{scale.bins} of this scale"
            )
    marks: list[str] = []
    for index in range(1, scale.bins + 1):
        subpaths = [
            _bin_subpath(rect, scale.fraction(index))
            for rect, value_class in cells
            if value_class == index
        ]
        if subpaths:
            marks.append(
                el("path", {"d": "".join(subpaths), "fill": scale.color(index)})
            )
    zeros = [_zero_subpath(rect) for rect, value_class in cells if value_class == 0]
    if zeros:
        marks.append(
            el(
                "path",
                {
                    "d": "".join(zeros),
                    "fill": "none",
                    "stroke": SEQUENTIAL_RAMP[0],
                    "stroke-width": _STROKE_WIDTH,
                },
            )
        )
    crosses = [
        _cross_subpath(rect) for rect, value_class in cells if value_class is None
    ]
    if crosses:
        marks.append(
            el(
                "path",
                {
                    "d": "".join(crosses),
                    **ink(STROKE),
                    "fill": "none",
                    "stroke-width": _STROKE_WIDTH,
                },
            )
        )
    return marks


# -------------------------------------------------------------------- legend


def _tag(color: str) -> SeriesStyle:
    return SeriesStyle(color, None, _TAG_SHAPE)


def legend_entries(
    scale: BinnedScale, *, has_zero: bool, has_absent: bool
) -> tuple[LegendEntry, ...]:
    """Lead, zero (when present), one per bin by upper edge, absent (when present)."""
    hours = _hours_form(scale) if _is_clock_duration(scale.column) else True
    lead = axis_title(scale.column, hours=hours)
    entries = [LegendEntry(lead, _tag(SEQUENTIAL_RAMP[0]), "block")]
    if has_zero:
        entries.append(LegendEntry(scale.zero_label, _tag(SEQUENTIAL_RAMP[0]), "block"))
    for index in range(1, scale.bins + 1):
        entries.append(
            LegendEntry(
                "≤ " + scale.labels[index - 1],
                _tag(scale.color(index)),
                "block",
            )
        )
    if has_absent:
        entries.append(LegendEntry(ABSENT_LABEL, _tag(ink(STROKE)["stroke"]), "block"))
    return tuple(entries)


def legend(plan: FramePlan, scale: BinnedScale, entries: Sequence[LegendEntry]) -> str:
    """The scale legend at the positions ``plan`` laid out for ``entries``."""
    if not plan.legend_rows:
        return ""
    planned = [pair for row in plan.legend_rows for pair in row]
    if len(planned) != len(entries):
        raise ValueError(
            f"the plan laid out {len(planned)} legend entries, got {len(entries)}"
        )
    has_zero = len(entries) > 1 and entries[1].label == scale.zero_label
    classes: list[int | None | str] = ["lead"]
    if has_zero:
        classes.append(0)
    classes.extend(range(1, scale.bins + 1))
    if len(classes) + 1 == len(entries):
        classes.append(None)
    if len(classes) != len(entries):
        raise ValueError("the entries are not those of legend_entries for this scale")
    items: list[str] = []
    position = 0
    for row_number, row in enumerate(plan.legend_rows):
        top = plan.legend_top + row_number * LEGEND_ROW
        mid = top + _LEGEND_MID
        for entry, x in row:
            value_class = classes[position]
            position += 1
            label_x = x
            if value_class != "lead":
                assert not isinstance(value_class, str)
                swatch = Rect(
                    x + (LEGEND_SWATCH - _SWATCH_CELL) / 2,
                    mid - _SWATCH_CELL / 2,
                    _SWATCH_CELL,
                    _SWATCH_CELL,
                )
                items.extend(cell_marks([(swatch, value_class)], scale))
                label_x = x + LEGEND_SWATCH + LEGEND_GAP
            attrs = {
                "x": fmt_num(label_x),
                "y": fmt_num(top + _LEGEND_TEXT_DROP),
                "font-size": fmt_num(FONT_TEXT),
                **ink(TEXT),
            }
            items.append(el("text", attrs, [text(clean_text(entry.label))]))
    return el("g", {"class": "ck-legend"}, items)
