"""Domains, value-to-pixel mapping and labelled ticks (chart-kit Req 6.1-6.5, 6.7).

``numeric_scale`` chooses the scale from the column's value kind, builds the
domain from the present values only (``include_zero`` first, then the
degenerate rules), asks ``ticks`` for round values and labels them with
``format``. Horizontal axes shrink their tick count until the estimated label
extents are at least ``_LABEL_GAP`` px apart. ``band_scale`` lays out equal
category bands and thins their labels.

Callers pass the numeric view of the values (``data.to_number``): proleptic
ordinal days for dates, seconds since the ordinal epoch for date-times,
seconds for durations. Absent values never reach a scale.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.format import (
    format_duration,
    format_number_tick,
    format_pace,
)
from fitdocs.render.charts.kit.layout import FONT_TEXT, text_width
from fitdocs.render.charts.kit.ticks import (
    CalendarStep,
    calendar_ticks,
    clock_ticks,
    linear_ticks,
    log_ticks,
    nice_step,
)
from fitdocs.units import UnitFamily, unit_named

_DAY: Final = 86400.0
_HOUR: Final = 3600.0
_LABEL_GAP: Final = 10.0
_VERTICAL_PER_TICK: Final = 36
_HORIZONTAL_PER_TICK: Final = 48
_MAX_VERTICAL_TICKS: Final = 8
_BAND_MARGIN: Final = 4.0
_CLOCK_SPAN_LIMIT: Final = 2 * _DAY
_ESCALATION_LIMIT: Final = 1000


class ScaleType(StrEnum):
    LINEAR = "linear"
    LOG = "log"
    TIME = "time"


class Side(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTTOM = "bottom"


@dataclass(frozen=True)
class Tick:
    value: float  # in the scale's numeric domain
    label: str


@dataclass(frozen=True)
class NumericScale:
    type: ScaleType
    lo: float
    hi: float  # final domain
    start_px: float
    end_px: float  # range (end < start for vertical axes)
    ticks: tuple[Tick, ...]
    column: Column
    # What the axis title needs (``format.axis_title``): the one date of a
    # clock-ladder axis whose ticks fall on a single date, and the duration
    # label form (``True`` is ``h:mm:ss``, ``False`` is ``m:ss``).
    clock_date: date | None = None
    hours: bool = True

    def position(self, value: float) -> float:
        if self.type is ScaleType.LOG:
            fraction = (math.log10(value) - math.log10(self.lo)) / (
                math.log10(self.hi) - math.log10(self.lo)
            )
        else:
            fraction = (value - self.lo) / (self.hi - self.lo)
        return self.start_px + fraction * (self.end_px - self.start_px)


@dataclass(frozen=True)
class BandScale:
    categories: tuple[str, ...]  # formatted labels in band order
    start_px: float
    end_px: float
    labelled: tuple[int, ...]  # indices whose label is drawn (thinning)

    def band(self, index: int) -> tuple[float, float]:
        """The ``[left, right)`` pixel extent of band ``index``."""
        width = (self.end_px - self.start_px) / len(self.categories)
        first = self.start_px + index * width
        second = first + width
        return (min(first, second), max(first, second))

    def centre(self, index: int) -> float:
        width = (self.end_px - self.start_px) / len(self.categories)
        return self.start_px + (index + 0.5) * width


# ------------------------------------------------------------------ helpers


def _scale_type(kind: ValueKind, requested: ScaleType) -> ScaleType:
    if kind in (ValueKind.DATE, ValueKind.DATETIME):
        if requested is ScaleType.LOG:
            raise ValueError("a log scale applies to number and duration columns only")
        return ScaleType.TIME
    if kind in (ValueKind.NUMBER, ValueKind.DURATION):
        if requested is ScaleType.TIME:
            raise ValueError("a time scale applies to date and date-time columns only")
        return requested
    raise ValueError(f"{kind.value} columns have no numeric scale")


def _duration_family(column: Column) -> UnitFamily | None:
    """DURATION or PACE when the column's labels use a clock form, else ``None``."""
    unit = unit_named(column.unit) if column.unit is not None else None
    if column.kind is ValueKind.DURATION:
        return UnitFamily.DURATION
    if unit is not None and unit.family in (UnitFamily.DURATION, UnitFamily.PACE):
        return unit.family
    return None


def _hms(seconds: float) -> str:
    whole = round(seconds)
    sign = "-" if whole < 0 else ""
    whole = abs(whole)
    return f"{sign}{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def _widened(
    lo: float,
    hi: float,
    scale_type: ScaleType,
    column: Column,
    *,
    include_zero: bool,
    integer: bool,
) -> tuple[float, float]:
    """The domain after ``include_zero`` and, if every value is equal, widening."""
    if scale_type is ScaleType.LOG:
        if lo == hi:
            return lo / 10, hi * 10
        return lo, hi
    if scale_type is ScaleType.TIME:
        if lo == hi:
            pad = 1.0 if column.kind is ValueKind.DATE else _HOUR
            return lo - pad, hi + pad
        return lo, hi
    if include_zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    if lo < hi:
        return lo, hi
    value = lo
    if include_zero:  # every value is 0: the only way to be degenerate here
        return 0.0, 1.0
    if integer or value == 0:
        pad = 1.0
    else:
        pad = nice_step(abs(value) / 10, duration=_duration_family(column) is not None)
    return value - pad, value + pad


def _inside(domain: tuple[float, float], ticks: tuple[float, ...]) -> tuple[float, ...]:
    slack = 1e-9 * (domain[1] - domain[0])
    return tuple(t for t in ticks if domain[0] - slack <= t <= domain[1] + slack)


def _number_ticks(
    values: tuple[float, ...],
    labels_step: float,
    column: Column,
) -> tuple[Tick, ...]:
    family = _duration_family(column)
    if family is UnitFamily.PACE:
        return tuple(Tick(v, format_pace(v)) for v in values)
    if family is UnitFamily.DURATION:
        if any(abs(v) >= _HOUR for v in values):
            return tuple(Tick(v, _hms(v)) for v in values)
        return tuple(Tick(v, format_duration(v)) for v in values)
    unit = unit_named(column.unit) if column.unit is not None else None
    return tuple(Tick(v, format_number_tick(v, labels_step, unit)) for v in values)


def _hours_form(column: Column, ticks: tuple[Tick, ...]) -> bool:
    if _duration_family(column) is not UnitFamily.DURATION:
        return True
    return any(abs(t.value) >= _HOUR for t in ticks)


_DAY_STEPS: Final = (CalendarStep.DAY, CalendarStep.TWO_DAYS, CalendarStep.WEEK)
_MONTH_STEPS: Final = (CalendarStep.MONTH, CalendarStep.QUARTER, CalendarStep.HALF)


def _calendar_label(step: CalendarStep, day: date) -> str:
    if step in _DAY_STEPS:
        return f"{day.year:04d}-{day.month:02d}-{day.day:02d}"
    if step in _MONTH_STEPS:
        return f"{day.year:04d}-{day.month:02d}"
    return f"{day.year:04d}"


def _clock_label(seconds: float, *, with_date: bool) -> str:
    day = date.fromordinal(int(seconds // _DAY))
    rest = int(seconds % _DAY)
    clock = f"{rest // 3600:02d}:{rest % 3600 // 60:02d}"
    return f"{day.month:02d}-{day.day:02d} {clock}" if with_date else clock


# -------------------------------------------------------------- numeric_scale


def _linear(
    lo: float,
    hi: float,
    count: int,
    column: Column,
    *,
    nice: bool,
    integer: bool,
) -> tuple[float, float, tuple[Tick, ...]]:
    duration = _duration_family(column) is not None
    for extra in range(_ESCALATION_LIMIT):
        dom_lo, dom_hi, values = linear_ticks(
            lo, hi, count + extra, duration=duration, integer=integer
        )
        if nice:
            break
        values = _inside((lo, hi), values)
        if len(values) >= 2:
            dom_lo, dom_hi = lo, hi
            break
    else:
        raise AssertionError("unreachable: finer steps always put two ticks inside")
    return dom_lo, dom_hi, _number_ticks(values, values[1] - values[0], column)


def _logarithmic(
    lo: float, hi: float, count: int, column: Column, *, nice: bool
) -> tuple[float, float, tuple[Tick, ...]]:
    duration = _duration_family(column) is not None
    dom_lo, dom_hi, values = log_ticks(lo, hi, count, duration=duration)
    if not nice:
        dom_lo, dom_hi, values = lo, hi, _inside((lo, hi), values)
    if not values:
        return dom_lo, dom_hi, ()
    return dom_lo, dom_hi, _number_ticks(values, min(values), column)


def _time(
    lo: float, hi: float, count: int, column: Column
) -> tuple[float, float, tuple[Tick, ...], date | None]:
    if column.kind is ValueKind.DATE:
        step, days = calendar_ticks(
            date.fromordinal(math.ceil(lo)), date.fromordinal(math.floor(hi)), count
        )
        ticks = tuple(
            Tick(float(d.toordinal()), _calendar_label(step, d)) for d in days
        )
        return lo, hi, ticks, None
    if hi - lo >= _CLOCK_SPAN_LIMIT:
        step, days = calendar_ticks(
            date.fromordinal(math.ceil(lo / _DAY)),
            date.fromordinal(math.floor(hi / _DAY)),
            count,
        )
        ticks = tuple(
            Tick(d.toordinal() * _DAY, _calendar_label(step, d)) for d in days
        )
        return lo, hi, ticks, None
    # clock_ticks' float tolerance scales with the magnitude it is given, so ask
    # in seconds since midnight of lo's day (keeps it small); the
    # filter then drops any tick that tolerance let in just outside the domain.
    base = math.floor(lo / _DAY) * _DAY
    _, relative = clock_ticks(lo - base, hi - base, count)
    seconds = _inside((lo, hi), tuple(base + s for s in relative))
    dates = {int(s // _DAY) for s in seconds}
    crossing = len(dates) > 1
    ticks = tuple(Tick(s, _clock_label(s, with_date=crossing)) for s in seconds)
    only = date.fromordinal(next(iter(dates))) if len(dates) == 1 else None
    return lo, hi, ticks, only


def _fits(scale: NumericScale) -> bool:
    """Whether adjacent estimated label extents are at least ``_LABEL_GAP`` apart."""
    placed = [
        (scale.position(t.value), text_width(t.label, FONT_TEXT)) for t in scale.ticks
    ]
    return all(
        abs(b[0] - a[0]) >= (a[1] + b[1]) / 2 + _LABEL_GAP
        for a, b in zip(placed, placed[1:], strict=False)
    )


def numeric_scale(
    values: Sequence[float],
    column: Column,
    start_px: float,
    end_px: float,
    *,
    scale: ScaleType,
    include_zero: bool,
    nice: bool,
    horizontal: bool,
    integer: bool = False,
) -> NumericScale:
    """A labelled scale over the present ``values`` (their numeric view)."""
    scale_type = _scale_type(column.kind, scale)
    if not values:
        raise ValueError("a scale needs at least one value; no-data is drawn instead")
    data = [float(v) for v in values]
    if not all(math.isfinite(v) for v in data):
        raise ValueError("scale values must be finite")
    lo, hi = min(data), max(data)
    if scale_type is ScaleType.LOG and lo <= 0:
        raise ValueError("a log scale needs positive values")
    lo, hi = _widened(
        lo, hi, scale_type, column, include_zero=include_zero, integer=integer
    )

    length = abs(end_px - start_px)

    def build(count: int) -> NumericScale:
        clock_date: date | None = None
        if scale_type is ScaleType.LINEAR:
            dom_lo, dom_hi, ticks = _linear(
                lo, hi, count, column, nice=nice, integer=integer
            )
        elif scale_type is ScaleType.LOG:
            dom_lo, dom_hi, ticks = _logarithmic(lo, hi, count, column, nice=nice)
        else:
            dom_lo, dom_hi, ticks, clock_date = _time(lo, hi, count, column)
        return NumericScale(
            scale_type,
            dom_lo,
            dom_hi,
            start_px,
            end_px,
            ticks,
            column,
            clock_date=clock_date,
            hours=_hours_form(column, ticks),
        )

    if not horizontal:
        count = max(
            2, min(_MAX_VERTICAL_TICKS, math.floor(length / _VERTICAL_PER_TICK))
        )
        return build(count)
    for count in range(max(2, math.floor(length / _HORIZONTAL_PER_TICK)), 2, -1):
        candidate = build(count)
        if _fits(candidate):
            return candidate
    return build(2)


# ----------------------------------------------------------------- band_scale


def band_scale(
    labels: Sequence[str], start_px: float, end_px: float, *, font_px: float
) -> BandScale:
    """Equal bands in the given order; label every band, else every k-th from 0."""
    if not labels:
        raise ValueError("a band scale needs at least one category")
    width = abs(end_px - start_px) / len(labels)
    widest = max(text_width(label, font_px) for label in labels)
    k = 1
    while widest > k * width - _BAND_MARGIN:
        k += 1
        if k >= len(labels):
            break
    return BandScale(tuple(labels), start_px, end_px, tuple(range(0, len(labels), k)))
