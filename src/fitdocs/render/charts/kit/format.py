"""Every string the kit shows: labels, values, ticks and text safety.

Pure and independent of the host: numbers are formatted with explicit
precision only, dates from their fields, and no value is converted between
units. Absent values show as :data:`ABSENT`, never as zero.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Final

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.units import Unit, UnitFamily, unit_named

ABSENT: Final = "—"  # em dash
ELLIPSIS: Final = "…"

_REPLACEMENT: Final = "�"

_CLEAN_TABLE: Final[dict[int, str]] = {
    **{
        code: _REPLACEMENT
        for code in (*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20))
    },
    0x09: " ",
    0x0A: " ",
    0x0D: " ",
    0xFFFE: _REPLACEMENT,
    0xFFFF: _REPLACEMENT,
    **{code: _REPLACEMENT for code in range(0xD800, 0xE000)},
}

_MARKDOWN_SPECIALS: Final = "\\`*_[]<>|&~#$"
_MARKDOWN_TABLE: Final[dict[int, str]] = {
    ord(char): "\\" + char for char in _MARKDOWN_SPECIALS
}


def _unit_of(column: Column) -> Unit | None:
    return None if column.unit is None else unit_named(column.unit)


def _is_duration(column: Column, unit: Unit | None) -> bool:
    return column.kind is ValueKind.DURATION or (
        unit is not None and unit.family is UnitFamily.DURATION
    )


def display_label(column: Column) -> str:
    """The explicit label, else the name without its unit suffix, spaced."""
    if column.label is not None:
        return column.label
    name = column.name
    unit = _unit_of(column)
    if unit is not None and name.endswith(unit.suffix):
        name = name[: -len(unit.suffix)]
    return name.replace("_", " ")


def axis_title(
    column: Column, *, clock_date: date | None = None, hours: bool = True
) -> str:
    """The display label plus ``(<symbol>)``; ``hours`` picks the duration form."""
    unit = _unit_of(column)
    parts: list[str] = []
    if _is_duration(column, unit):
        parts.append("h:mm:ss" if hours else "m:ss")
    elif unit is not None:
        parts.append(unit.symbol)
    if clock_date is not None:
        parts.append(_format_date(clock_date))
    label = display_label(column)
    if not parts:
        return label
    return f"{label} ({', '.join(parts)})"


def _format_date(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"


def _fixed(value: float | Decimal, decimals: int) -> str:
    text = format(value, f".{decimals}f")
    if text.startswith("-") and not text.strip("-0."):
        text = text[1:]
    return text


def _trimmed(value: float | Decimal) -> str:
    text = _fixed(value, 2)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _number_text(value: int | float | Decimal, unit: Unit | None) -> str:
    if type(value) is int:
        return str(value)
    if unit is not None and unit.family in (UnitFamily.QUANTITY, UnitFamily.PERCENT):
        return _fixed(value, unit.decimals)
    return _trimmed(value)


def _with_symbol(text: str, unit: Unit | None) -> str:
    if unit is None or unit.family not in (UnitFamily.QUANTITY, UnitFamily.PERCENT):
        return text
    if unit.family is UnitFamily.PERCENT or not unit.spaced:
        return text + unit.symbol
    return f"{text} {unit.symbol}"


def format_value(value: Value, column: Column, *, with_unit: bool) -> str:
    """One cell as text; absent is :data:`ABSENT`."""
    if value is None:
        return ABSENT
    unit = _unit_of(column)
    kind = column.kind
    if kind is ValueKind.DURATION:
        assert isinstance(value, timedelta)
        return format_duration(value.total_seconds())
    if kind is ValueKind.NUMBER:
        assert isinstance(value, int | float | Decimal)
        if unit is not None and unit.family is UnitFamily.DURATION:
            return format_duration(float(value))
        if unit is not None and unit.family is UnitFamily.PACE:
            text = format_pace(float(value))
            return text + " /km" if with_unit else text
        text = _number_text(value, unit)
        return _with_symbol(text, unit) if with_unit else text
    if kind is ValueKind.DATE:
        assert isinstance(value, date)
        return _format_date(value)
    if kind is ValueKind.DATETIME:
        assert isinstance(value, datetime)
        text = f"{_format_date(value)} {value.hour:02d}:{value.minute:02d}"
        if with_unit and unit is not None and unit.token == "utc":
            text += " UTC"
        return text
    if kind is ValueKind.BOOLEAN:
        return "true" if value else "false"
    assert isinstance(value, str)
    return clean_text(value)


def format_number_tick(value: float, step: float, unit: Unit | None) -> str:
    """A tick label: decimals follow the step; only percent carries a symbol."""
    decimals = max(0, -math.floor(math.log10(step)))
    text = _fixed(value, decimals)
    if unit is not None and unit.family is UnitFamily.PERCENT:
        return text + unit.symbol
    return text


def _clock(seconds: float, *, hours: bool | None) -> str:
    """``hours`` None: h:mm:ss from one hour; True: always; False: never."""
    whole = round(seconds)
    sign = "-" if whole < 0 else ""
    whole = abs(whole)
    if hours is True or (hours is None and whole >= 3600):
        return f"{sign}{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"
    return f"{sign}{whole // 60}:{whole % 60:02d}"


def format_duration(seconds: float, *, hours: bool | None = None) -> str:
    """Whole seconds (half to even) as ``m:ss`` or, from one hour, ``h:mm:ss``.

    ``hours=True`` always writes ``h:mm:ss``; ``hours=False`` always writes
    ``m:ss`` with unbounded minutes (5400 s is ``90:00``).
    """
    return _clock(seconds, hours=hours)


def format_pace(seconds_per_km: float) -> str:
    """Seconds per kilometre as ``m:ss``, minutes unbounded."""
    return _clock(seconds_per_km, hours=False)


def format_delta(delta: float, column: Column) -> str:
    """A signed difference in the column's own format and unit."""
    sign = "±" if delta == 0 else "+" if delta > 0 else "-"
    magnitude = abs(delta)
    unit = _unit_of(column)
    if _is_duration(column, unit):
        return sign + format_duration(magnitude)
    if unit is not None and unit.family is UnitFamily.PACE:
        return f"{sign}{format_pace(magnitude)} /km"
    text = _number_text(magnitude, unit)
    if unit is not None and unit.family is UnitFamily.PERCENT:
        return f"{sign}{text} pp"
    return sign + _with_symbol(text, unit)


def clean_text(text: str) -> str:
    """Replace characters XML 1.0 forbids with U+FFFD; tab, CR, LF become a space."""
    return text.translate(_CLEAN_TABLE)


def escape_markdown(text: str) -> str:
    """Backslash-escape the markdown-significant characters of caller text."""
    return text.translate(_MARKDOWN_TABLE)
