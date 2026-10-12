"""Pure tick arithmetic: nice steps and ladders for every axis family.

No labels and no pixels: each function returns numbers or dates. Decimal axes
use 1, 2 and 5 times a power of ten; duration axes use second, minute, hour and
day steps (never below one second for linear axes); log axes use decades and,
under three decades, 2x and 5x each decade; date axes use days, Monday-starting
weeks, months, quarters, half years and years; date-time axes under two days
use clock steps aligned to multiples of the step since midnight.

Preconditions are enforced with ``ValueError``: callers (``scales``) widen a
degenerate domain (Req 6.4) before asking for ticks.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from enum import StrEnum
from itertools import islice
from typing import Final, TypeVar

DECIMAL_MANTISSAS: Final = (1.0, 2.0, 5.0)
DURATION_STEPS: Final[tuple[float, ...]] = (
    1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
    3600, 7200, 10800, 21600, 43200, 86400,
)  # fmt: skip
LOG_DURATION_TICKS: Final[tuple[float, ...]] = (
    1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800,
    3600, 7200, 10800, 21600, 43200, 86400,
)  # fmt: skip
CLOCK_STEPS: Final[tuple[int, ...]] = (
    60,
    300,
    900,
    1800,
    3600,
    7200,
    10800,
    21600,
    43200,
)

_DAY: Final = 86400
# Relative slack that absorbs float noise (0.3 / 0.1 == 2.9999999999999996).
_TOLERANCE: Final = 1e-9


class CalendarStep(StrEnum):
    DAY = "day"
    TWO_DAYS = "2day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    HALF = "half"
    YEAR = "year"
    YEARS_2 = "2year"
    YEARS_5 = "5year"
    YEARS_10 = "10year"


# ------------------------------------------------------------------ helpers

_T = TypeVar("_T")


def _decimal(mantissa: float, exponent: int) -> float:
    """``mantissa`` x 10^``exponent`` as the correctly rounded float."""
    return float(f"{int(mantissa)}e{exponent}")


def _clean(value: float) -> float:
    """Round away float noise (0.30000000000000004)."""
    return float(f"{value:.12g}")


def _floor(q: float, slack: float = 0.0) -> int:
    """floor(q), treating a q within ``slack`` above an integer as that integer."""
    nearest = round(q)
    return nearest if abs(q - nearest) <= slack else math.floor(q)


def _ceil(q: float, slack: float = 0.0) -> int:
    """ceil(q), treating a q within ``slack`` below an integer as that integer."""
    nearest = round(q)
    return nearest if abs(q - nearest) <= slack else math.ceil(q)


def _thin(ticks: tuple[_T, ...], max_count: int) -> tuple[_T, ...]:
    """Keep every k-th tick, starting with the first, for the smallest k that fits."""
    if len(ticks) <= max_count:
        return ticks
    k = math.ceil(len(ticks) / max_count)
    return ticks[::k]


def _require_finite(*values: float) -> None:
    for value in values:
        if not math.isfinite(value):
            raise ValueError(f"tick input must be finite, got {value!r}")


# ---------------------------------------------------------------- nice_step


def nice_step(raw: float, *, duration: bool) -> float:
    """The smallest ladder step that is at least ``raw``."""
    _require_finite(raw)
    if raw <= 0:
        raise ValueError(f"raw step must be positive, got {raw!r}")
    floor = raw * (1 - _TOLERANCE)
    if duration:
        for step in DURATION_STEPS:
            if step >= floor:
                return float(step)
        exponent = 0
        while True:
            for mantissa in DECIMAL_MANTISSAS:
                candidate = int(mantissa) * 10**exponent * _DAY
                if candidate >= floor:
                    return float(candidate)
            exponent += 1
    exponent = math.floor(math.log10(raw)) - 1
    while True:
        for mantissa in DECIMAL_MANTISSAS:
            candidate = _decimal(mantissa, exponent)
            if candidate >= floor:
                return candidate
        exponent += 1


def _steps_from(raw: float, *, duration: bool) -> Iterator[float]:
    step = nice_step(raw, duration=duration)
    while True:
        yield step
        step = nice_step(step * (1 + 1e-6), duration=duration)


# ------------------------------------------------------------- linear_ticks


def linear_ticks(
    lo: float, hi: float, max_count: int, *, duration: bool, integer: bool = False
) -> tuple[float, float, tuple[float, ...]]:
    """Niced domain and ticks for a linear axis over ``[lo, hi]``.

    Uses the smallest ladder step giving at most ``max_count`` ticks; the
    outermost ticks enclose the data. ``integer`` forbids steps below 1.
    Requires ``lo < hi`` and ``max_count >= 2``. A range with ``lo < 0 < hi``
    cannot be enclosed by fewer than three ticks, so ``max_count`` is then
    taken as at least 3.
    """
    _require_finite(lo, hi)
    if not lo < hi:
        raise ValueError(f"linear ticks need lo < hi, got {lo!r}, {hi!r}")
    if max_count < 2:
        raise ValueError(f"max_count must be at least 2, got {max_count!r}")
    # Two ticks cannot enclose a range that straddles zero (0 is a multiple of
    # every step), so such a range gets three.
    allowed = max(max_count, 3) if lo < 0 < hi else max_count
    raw = (hi - lo) / (allowed - 1)
    if integer:
        raw = max(raw, 1.0)
    scale = max(abs(lo), abs(hi))
    for step in _steps_from(raw, duration=duration):
        slack = _TOLERANCE * scale / step
        first = _floor(lo / step, slack)
        last = _ceil(hi / step, slack)
        if last - first + 1 <= allowed:
            ticks = tuple(_clean(k * step) for k in range(first, last + 1))
            return ticks[0], ticks[-1], ticks
    raise AssertionError("unreachable: the step ladder is unbounded")


# ---------------------------------------------------------------- log_ticks


def _decade_floor(value: float) -> int:
    """Largest exponent e with 10^e <= value."""
    exponent = math.floor(math.log10(value))
    while _decimal(1, exponent) > value:
        exponent -= 1
    return exponent


def _decade_ceil(value: float) -> int:
    """Smallest exponent e with 10^e >= value."""
    exponent = math.ceil(math.log10(value))
    while _decimal(1, exponent) < value:
        exponent += 1
    return exponent


def _log_duration_ladder(lo: float, hi: float) -> list[float]:
    """``LOG_DURATION_TICKS`` extended below 1 s and above a day by 1, 2, 5 x 10^k."""
    ladder = {float(tick) for tick in LOG_DURATION_TICKS}
    for exponent in range(_decade_floor(lo) - 1, 0):
        ladder.update(_decimal(m, exponent) for m in DECIMAL_MANTISSAS)
    exponent = 0
    while True:
        ladder.update(int(m) * 10**exponent * _DAY * 1.0 for m in DECIMAL_MANTISSAS)
        if 10**exponent * _DAY >= hi:
            break
        exponent += 1
    return sorted(ladder)


def log_ticks(
    lo: float, hi: float, max_count: int, *, duration: bool
) -> tuple[float, float, tuple[float, ...]]:
    """Domain and ticks for a logarithmic axis over ``[lo, hi]``.

    Plain numbers: decades, plus 2x and 5x each decade under three decades.
    Durations: ``LOG_DURATION_TICKS`` (extended in decimal days, and below one
    second in 1, 2, 5 x 10^k). The domain runs from the largest tick <= ``lo``
    to the smallest tick >= ``hi``; ticks beyond ``max_count`` are thinned by
    keeping every k-th, leaving the domain as stated. Requires ``0 < lo < hi``
    and ``max_count >= 2``.
    """
    _require_finite(lo, hi)
    if not 0 < lo < hi:
        raise ValueError(f"log ticks need 0 < lo < hi, got {lo!r}, {hi!r}")
    if max_count < 2:
        raise ValueError(f"max_count must be at least 2, got {max_count!r}")
    if duration:
        ladder = _log_duration_ladder(lo, hi)
    else:
        lo_exp, hi_exp = _decade_floor(lo), _decade_ceil(hi)
        if hi_exp - lo_exp >= 3:
            ladder = [_decimal(1, e) for e in range(lo_exp, hi_exp + 1)]
        else:
            ladder = [
                _decimal(m, e)
                for e in range(lo_exp, hi_exp + 1)
                for m in DECIMAL_MANTISSAS
            ]
    lower = max(tick for tick in ladder if tick <= lo)
    upper = min(tick for tick in ladder if tick >= hi)
    inside = tuple(tick for tick in ladder if lower <= tick <= upper)
    return lower, upper, _thin(inside, max_count)


# ----------------------------------------------------------- calendar_ticks


def _every_day(first: date, last: date) -> Iterator[date]:
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _even_days(first: date, last: date) -> Iterator[date]:
    return (d for d in _every_day(first, last) if d.toordinal() % 2 == 0)


def _mondays(first: date, last: date) -> Iterator[date]:
    day = first + timedelta(days=(7 - first.weekday()) % 7)
    while day <= last:
        yield day
        day += timedelta(days=7)


def _months(allowed: frozenset[int]) -> Callable[[date, date], Iterator[date]]:
    def generate(first: date, last: date) -> Iterator[date]:
        for year in range(first.year, last.year + 1):
            for month in sorted(allowed):
                tick = date(year, month, 1)
                if first <= tick <= last:
                    yield tick

    return generate


def _years(multiple: int) -> Callable[[date, date], Iterator[date]]:
    def generate(first: date, last: date) -> Iterator[date]:
        for year in range(first.year, last.year + 1):
            if year % multiple == 0 and first <= date(year, 1, 1) <= last:
                yield date(year, 1, 1)

    return generate


_CALENDAR_LADDER: Final[
    tuple[tuple[CalendarStep, Callable[[date, date], Iterator[date]]], ...]
] = (
    (CalendarStep.DAY, _every_day),
    (CalendarStep.TWO_DAYS, _even_days),
    (CalendarStep.WEEK, _mondays),
    (CalendarStep.MONTH, _months(frozenset(range(1, 13)))),
    (CalendarStep.QUARTER, _months(frozenset({1, 4, 7, 10}))),
    (CalendarStep.HALF, _months(frozenset({1, 7}))),
    (CalendarStep.YEAR, _years(1)),
    (CalendarStep.YEARS_2, _years(2)),
    (CalendarStep.YEARS_5, _years(5)),
    (CalendarStep.YEARS_10, _years(10)),
)


def calendar_ticks(
    first: date, last: date, max_count: int
) -> tuple[CalendarStep, tuple[date, ...]]:
    """The finest calendar step with 2 to ``max_count`` ticks in ``[first, last]``.

    Both ends are inclusive; weeks start on Monday; two-day ticks fall on dates
    with an even proleptic Gregorian ordinal; multi-year ticks are Jan 1st of
    multiples of the step. A span that holds two or more ticks of some step
    never comes back tickless or with a lone tick: when no step gives between 2
    and ``max_count`` ticks, the coarsest step that still gives more than that
    is thinned (every k-th from the first) to at most ``max(max_count, 2)``
    ticks, so a ``max_count`` of 1 yields two ticks there. A span that holds
    fewer than two ticks of every step gets the finest step, with its 0 or 1
    ticks.
    """
    if first > last:
        raise ValueError(f"calendar ticks need first <= last, got {first!r}, {last!r}")
    if max_count < 1:
        raise ValueError(f"max_count must be at least 1, got {max_count!r}")
    allowed = max(max_count, 2)
    overflowing: Callable[[date, date], Iterator[date]] | None = None
    overflowing_step = CalendarStep.DAY
    for step, generate in _CALENDAR_LADDER:
        count = len(list(islice(generate(first, last), allowed + 1)))
        if 2 <= count <= allowed:
            return step, tuple(generate(first, last))
        if count > allowed:
            overflowing, overflowing_step = generate, step
    if overflowing is not None:
        return overflowing_step, _thin(tuple(overflowing(first, last)), allowed)
    return CalendarStep.DAY, tuple(_every_day(first, last))


# --------------------------------------------------------------- clock_ticks


def clock_ticks(
    lo_s: float, hi_s: float, max_count: int
) -> tuple[int, tuple[float, ...]]:
    """The finest ``CLOCK_STEPS`` step with 2 to ``max_count`` ticks in the span.

    Ticks are multiples of the step counted from midnight, both ends inclusive.
    A span that holds two or more ticks of some step never comes back tickless
    or with a lone tick: when no step gives between 2 and ``max_count`` ticks,
    the coarsest step that still gives more than that is thinned (every k-th
    from the first) to at most ``max(max_count, 2)`` ticks. A span that holds
    fewer than two ticks of every step gets the finest step, with its 0 or 1
    ticks.
    """
    _require_finite(lo_s, hi_s)
    if hi_s < lo_s:
        raise ValueError(f"clock ticks need lo <= hi, got {lo_s!r}, {hi_s!r}")
    if max_count < 1:
        raise ValueError(f"max_count must be at least 1, got {max_count!r}")
    scale = max(abs(lo_s), abs(hi_s))

    def multiples(step: int) -> tuple[float, ...]:
        slack = _TOLERANCE * scale / step
        first, last = _ceil(lo_s / step, slack), _floor(hi_s / step, slack)
        return tuple(float(k * step) for k in range(first, last + 1))

    allowed = max(max_count, 2)
    overflowing: int | None = None
    for step in CLOCK_STEPS:
        ticks = multiples(step)
        if 2 <= len(ticks) <= allowed:
            return step, ticks
        if len(ticks) > allowed:
            overflowing = step
    if overflowing is not None:
        return overflowing, _thin(multiples(overflowing), allowed)
    return CLOCK_STEPS[0], multiples(CLOCK_STEPS[0])
