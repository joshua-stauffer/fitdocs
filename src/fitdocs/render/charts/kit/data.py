"""The kit's typed data contract and its numeric view.

A :class:`Column` names a :class:`ValueKind`; a cell is a :data:`Value`, with
``None`` meaning absent. Absent is never replaced by zero or any default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TypeAlias


class ValueKind(StrEnum):
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    DURATION = "duration"
    CATEGORY = "category"
    BOOLEAN = "boolean"


Value: TypeAlias = (
    int | float | Decimal | str | bool | date | datetime | timedelta | None
)


@dataclass(frozen=True)
class Column:
    name: str
    kind: ValueKind
    unit: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class ChartData:
    columns: tuple[Column, ...]
    rows: tuple[tuple[Value, ...], ...]


def accepts(kind: ValueKind, value: object) -> bool:
    """Whether ``value`` is a legal cell of ``kind``; absent is always legal.

    Non-finite numbers are accepted here and refused separately so the
    problem is specific.
    """
    if value is None:
        return True
    if kind is ValueKind.NUMBER:
        return type(value) is int or isinstance(value, float | Decimal)
    if kind is ValueKind.DATE:
        return type(value) is date
    if kind is ValueKind.DATETIME:
        return isinstance(value, datetime) and value.tzinfo is None
    if kind is ValueKind.DURATION:
        return isinstance(value, timedelta)
    if kind is ValueKind.CATEGORY:
        return isinstance(value, str)
    return isinstance(value, bool)


def is_finite_number(value: object) -> bool:
    """True for a finite ``int``, ``float`` or ``Decimal`` (never a ``bool``)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return False


def to_number(value: Value, kind: ValueKind) -> float | None:
    """The numeric view of a cell: days, seconds or a float; ``None`` if absent.

    DATE is the proleptic ordinal (days); DATETIME is ``toordinal() * 86400``
    plus the seconds of the day (naive, timezone-free); DURATION is seconds.
    CATEGORY and BOOLEAN are not numeric and callers never ask.
    """
    if value is None:
        return None
    if kind is ValueKind.NUMBER:
        assert isinstance(value, int | float | Decimal)
        return float(value)
    if kind is ValueKind.DURATION:
        assert isinstance(value, timedelta)
        return value.total_seconds()
    if kind is ValueKind.DATE:
        assert isinstance(value, date)
        return float(value.toordinal())
    if kind is ValueKind.DATETIME:
        assert isinstance(value, datetime)
        seconds = (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1e6
        )
        return value.toordinal() * 86400 + seconds
    raise ValueError(f"{kind.value} values have no numeric view")
