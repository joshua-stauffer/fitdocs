"""The ``histogram`` kind: counts of one numeric column in equal-width bins.

Binning (chart-kit Req 14.4, 14.5): by default ``k = clamp(ceil(log2 n) + 1,
1, 50)`` bins of the decimal (duration, for duration columns) ladder step
nearest above ``(max - min) / k``, the first edge the multiple of that step at
or below the minimum; ``bins`` splits ``[min, max]`` into equal parts;
``bin_width`` fixes the step. Bins are half-open ``[a, a + w)`` except the last,
which includes its upper edge. Edges are rounded to 15 significant digits so a
value written as ``0.3`` sits on the edge ``0.3`` and not beside it.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from fitdocs.render.charts.kit import frame, marks
from fitdocs.render.charts.kit.cartesian import numbers, undrawn
from fitdocs.render.charts.kit.data import Column, Value, ValueKind, to_number
from fitdocs.render.charts.kit.format import axis_title, format_duration, format_value
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
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
from fitdocs.render.charts.kit.ticks import nice_step
from fitdocs.render.charts.svg import el
from fitdocs.units import UnitFamily, unit_named

_BIN_BOUND: Final = 100
_MAX_DEFAULT_BINS: Final = 50
_DEFAULT_HEIGHT: Final = 280
_BAR_GAP: Final = 1.0  # px between neighbouring bars
_MIN_GAPPED_BAR: Final = 3.0  # narrower bars touch rather than vanish
_EXACT_LIMIT: Final = 10**6  # beyond this the count is exact arithmetic only
_DIGITS: Final = ".15g"
_COUNT_COLUMN: Final = Column("count", ValueKind.NUMBER, label="Count")


# ----------------------------------------------------------------------- binning


@dataclass(frozen=True)
class _Shape:
    """Where the bins start, how wide they are and how many there are.

    ``first`` is meaningful only while ``count`` is within the bound: a larger
    count is refused before any edge is built.
    """

    first: float
    width: float
    count: int
    spans_data: bool  # ``bins`` rule: the first and last edges are min and max


@dataclass(frozen=True)
class _Binned:
    edges: tuple[float, ...]
    counts: tuple[int, ...]


def _clean(value: float) -> float:
    return float(format(value, _DIGITS))


def _sturges(n: int) -> int:
    """``clamp(ceil(log2 n) + 1, 1, 50)`` for ``n >= 1``."""
    return min((n - 1).bit_length() + 1, _MAX_DEFAULT_BINS)


def _first_edge(value: float, width: float) -> float:
    """The largest multiple of ``width`` that is at most ``value``."""
    multiple = math.floor(value / width)
    while _clean(multiple * width) > value:
        multiple -= 1
    while _clean((multiple + 1) * width) <= value:
        multiple += 1
    return _clean(multiple * width)


def _shape(
    values: list[float], *, duration: bool, bins: int | None, bin_width: float | None
) -> _Shape:
    low, high = min(values), max(values)
    if low == high:
        width = 1.0 if low == 0 else nice_step(abs(low) / 10, duration=duration)
        return _Shape(_first_edge(low, width), width, 1, False)
    if bins is not None:
        return _Shape(low, (high - low) / bins, bins, True)
    if bin_width is not None:
        width = bin_width
    else:
        width = nice_step((high - low) / _sturges(len(values)), duration=duration)
    exact_width = Fraction(width)
    exact_first = (Fraction(low) // exact_width) * exact_width
    exact_count = math.ceil((Fraction(high) - exact_first) / exact_width)
    if exact_count > _EXACT_LIMIT:
        return _Shape(low, width, exact_count, False)
    first = _first_edge(low, width)
    count = max(1, exact_count - 1)
    while count > 1 and _clean(first + (count - 1) * width) >= high:
        count -= 1
    while _clean(first + count * width) < high:
        count += 1
    return _Shape(first, width, count, False)


def _histogram(
    values: list[float], *, duration: bool, bins: int | None, bin_width: float | None
) -> _Binned:
    shape = _shape(values, duration=duration, bins=bins, bin_width=bin_width)
    edges = [_clean(shape.first + i * shape.width) for i in range(shape.count + 1)]
    if shape.spans_data:
        edges[0], edges[-1] = min(values), max(values)
    counts = [0] * shape.count
    for value in values:
        index = min(bisect.bisect_right(edges, value) - 1, shape.count - 1)
        counts[index] += 1
    return _Binned(tuple(edges), tuple(counts))


def _on_duration_ladder(column: Column) -> bool:
    if column.kind is ValueKind.DURATION:
        return True
    unit = unit_named(column.unit) if column.unit is not None else None
    return unit is not None and unit.family in (UnitFamily.DURATION, UnitFamily.PACE)


def _overhangs(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    """How far the x tick labels reach past the plot's left and right edges."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - plot.right)
    return left, right


def _present(bound: BoundChart) -> list[float]:
    return [n for n in numbers(bound, "x") if n is not None]


def _options(bound: BoundRequest) -> tuple[int | None, float | None]:
    return bound.integer("bins"), bound.number("bin_width")


# ------------------------------------------------------------------------- hooks


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    bins, width = _options(bound)
    problems: list[ChartProblem] = []
    if bins is not None and width is not None:
        problems.append(
            bound.problem(
                ProblemCode.OPTION_CONFLICT,
                "Options 'bins' and 'bin_width' cannot both be set.",
                "Set either 'bins' or 'bin_width', not both.",
                option="bin_width",
                accepted=("bins", "bin_width"),
            )
        )
    if width is not None and width <= 0:
        problems.append(
            bound.problem(
                ProblemCode.OPTION_VALUE,
                "Option 'bin_width' does not accept this value; it takes a "
                "number greater than zero.",
                "Set 'bin_width' to a number greater than zero.",
                option="bin_width",
            )
        )
    return tuple(problems)


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    values = _present(bound)
    if not values:
        return ()
    bins, width = _options(bound)
    shape = _shape(
        values,
        duration=_on_duration_ladder(bound.columns["x"]),
        bins=bins,
        bin_width=width,
    )
    if shape.count > _BIN_BOUND:
        return (
            bound.problem(
                ProblemCode.OVER_BOUND,
                f"histogram draws at most {_BIN_BOUND} bins; this binning "
                f"yields {shape.count}.",
                f"Raise 'bin_width' so the binning yields at most {_BIN_BOUND} "
                "bins, or limit the range of the values.",
                option="bin_width",
                rows=shape.count,
            ),
        )
    return ()


# -------------------------------------------------------------------------- draw


def _clock_family(column: Column) -> bool:
    """Whether the column's values read as clock durations (not paces)."""
    if column.kind is ValueKind.DURATION:
        return True
    unit = unit_named(column.unit) if column.unit is not None else None
    return unit is not None and unit.family is UnitFamily.DURATION


def _extreme(bound: BoundChart, *, largest: bool, hours: bool) -> str:
    """The formatted extreme present value, in the form the drawn axis uses."""
    column = bound.columns["x"]
    present: list[Value] = [v for v in bound.values("x") if v is not None]
    chosen = (max if largest else min)(
        present, key=lambda v: to_number(v, column.kind) or 0.0
    )
    if _clock_family(column):
        seconds = to_number(chosen, column.kind)
        assert seconds is not None
        return format_duration(seconds, hours=hours)
    return format_value(chosen, column, with_unit=True)


def _draw(bound: BoundChart) -> str:
    height = bound.height
    assert height is not None
    values = _present(bound)
    if not values:
        return frame.no_data(bound, height=height)
    x_column = bound.columns["x"]
    bins, width = _options(bound)
    binned = _histogram(
        values,
        duration=_on_duration_ladder(x_column),
        bins=bins,
        bin_width=width,
    )
    counts = [float(c) for c in binned.counts]
    absent = undrawn(bound, ("x",))
    note = frame.not_drawn_note(absent)
    lines = [] if note is None else [note]

    def plan(y_label_width: float, overhang: float) -> FramePlan:
        return plan_frame(
            bound.width,
            height,
            legend=(),
            y_label_width=y_label_width,
            x_label_overhang=overhang,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    def y_scale(current: FramePlan) -> NumericScale:
        return numeric_scale(
            counts,
            _COUNT_COLUMN,
            current.plot.bottom,
            current.plot.top,
            scale=ScaleType.LINEAR,
            include_zero=True,
            nice=True,
            horizontal=False,
            integer=True,
        )

    def x_scale(current: FramePlan) -> NumericScale:
        return numeric_scale(
            [binned.edges[0], binned.edges[-1]],
            x_column,
            current.plot.left,
            current.plot.right,
            scale=ScaleType.LINEAR,
            include_zero=False,
            nice=True,
            horizontal=True,
        )

    first = plan(0.0, 0.0)
    left = max(text_width(t.label, FONT_TEXT) for t in y_scale(first).ticks)
    second = plan(left, 0.0)
    reach_left, reach_right = _overhangs(x_scale(second), second.plot)
    final = plan(left + reach_left, reach_right)
    y = y_scale(final)
    x = x_scale(final)
    zero = y.position(0.0)
    colour = series_style(0).color
    bars: list[str] = []
    for index, count in enumerate(binned.counts):
        if count == 0:
            continue
        left_px = x.position(binned.edges[index])
        right_px = x.position(binned.edges[index + 1])
        bar_width = right_px - left_px
        gap = _BAR_GAP if bar_width >= _MIN_GAPPED_BAR else 0.0
        bars.append(
            marks.bar(
                left_px + gap / 2,
                zero,
                bar_width - gap,
                zero - y.position(float(count)),
                colour,
            )
        )
    body = [
        frame.grid(y, final.plot, horizontal_lines=True),
        el("g", {"class": "ck-marks"}, bars),
        frame.axis(x, final.plot, Side.BOTTOM, plan=final),
        frame.axis(y, final.plot, Side.LEFT, plan=final),
        frame.title_text(final, bound.request.title),
    ]
    if lines:
        body.append(frame.notes(final, lines))
    description = frame.describe(
        bound.spec.name,
        bound.request.title,
        (("x", axis_title(x_column, clock_date=x.clock_date, hours=x.hours)),),
        rows=len(bound.rows),
        series=None,
        undrawn=absent,
        ranges=(
            (
                axis_title(x_column, clock_date=x.clock_date, hours=x.hours),
                _extreme(bound, largest=False, hours=x.hours),
                _extreme(bound, largest=True, hours=x.hours),
            ),
            (
                axis_title(_COUNT_COLUMN),
                str(min(binned.counts)),
                str(max(binned.counts)),
            ),
        ),
    )
    return frame.document(
        bound.width,
        height,
        title=bound.request.title,
        description=description,
        body=body,
    )


KIND: Final = KindSpec(
    name="histogram",
    description="Counts of one numeric column in equal-width bins",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The values to count.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "bins",
            OptionType.INTEGER,
            "The number of equal-width bins.",
            None,
            minimum=1,
            maximum=_BIN_BOUND,
        ),
        OptionSpec(
            "bin_width",
            OptionType.NUMBER,
            "The width of each bin, in the column's unit (seconds for durations).",
            None,
        ),
        height=_DEFAULT_HEIGHT,
    ),
    bound=MarkBound(
        _BIN_BOUND,
        "bins",
        OverBound.REDUCE,
        "Any number of values is binned; a binning that yields more than 100 "
        "bins is refused.",
    ),
    max_series=None,
    draw=_draw,
    validate=_validate,
    check=_check,
)
