"""Tests for the kit's data contract (chart-kit Req 1.1, 1.2)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from fitdocs.render.charts.kit.data import (
    ChartData,
    Column,
    ValueKind,
    accepts,
    is_finite_number,
    to_number,
)

ALL_KINDS = tuple(ValueKind)


def test_value_kind_members_and_order() -> None:
    assert [(k.name, k.value) for k in ValueKind] == [
        ("NUMBER", "number"),
        ("DATE", "date"),
        ("DATETIME", "datetime"),
        ("DURATION", "duration"),
        ("CATEGORY", "category"),
        ("BOOLEAN", "boolean"),
    ]


def test_column_and_chartdata_shape() -> None:
    col = Column("distance_km", ValueKind.NUMBER)
    assert (col.unit, col.label) == (None, None)
    data = ChartData((col,), ((1,),))
    assert data.columns == (col,)
    assert data.rows == ((1,),)


@pytest.mark.parametrize("value", [3, 2.5, Decimal("1.5"), 0])
def test_number_accepts(value: object) -> None:
    assert accepts(ValueKind.NUMBER, value)


@pytest.mark.parametrize("value", [True, False, "3", date(2026, 1, 1)])
def test_number_refuses(value: object) -> None:
    assert not accepts(ValueKind.NUMBER, value)


def test_date_takes_date_refuses_datetime() -> None:
    assert accepts(ValueKind.DATE, date(2026, 1, 1))
    assert not accepts(ValueKind.DATE, datetime(2026, 1, 1, 8, 0))


def test_datetime_naive_only() -> None:
    assert accepts(ValueKind.DATETIME, datetime(2026, 1, 1, 8, 0))
    assert not accepts(ValueKind.DATETIME, datetime(2026, 1, 1, 8, 0, tzinfo=UTC))
    assert not accepts(ValueKind.DATETIME, date(2026, 1, 1))


def test_duration_takes_timedelta() -> None:
    assert accepts(ValueKind.DURATION, timedelta(seconds=5))
    assert not accepts(ValueKind.DURATION, 5)


def test_category_str_only() -> None:
    assert accepts(ValueKind.CATEGORY, "run")
    for bad in (1, True, b"run", date(2026, 1, 1)):
        assert not accepts(ValueKind.CATEGORY, bad)


def test_boolean_bool_only() -> None:
    assert accepts(ValueKind.BOOLEAN, True)
    assert accepts(ValueKind.BOOLEAN, False)
    for bad in (1, 0, "true"):
        assert not accepts(ValueKind.BOOLEAN, bad)


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_none_accepted_for_every_kind(kind: ValueKind) -> None:
    assert accepts(kind, None)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_non_finite_numbers(value: object) -> None:
    assert not is_finite_number(value)
    assert accepts(ValueKind.NUMBER, value)


@pytest.mark.parametrize("value", [0, 3, -2.5, Decimal("1.5"), 1e300])
def test_finite_numbers(value: object) -> None:
    assert is_finite_number(value)


def test_is_finite_number_refuses_non_numbers() -> None:
    for bad in (True, "1", None, date(2026, 1, 1)):
        assert not is_finite_number(bad)


def test_to_number_number() -> None:
    result = to_number(Decimal("1.5"), ValueKind.NUMBER)
    assert result == 1.5
    assert type(result) is float
    result_int = to_number(3, ValueKind.NUMBER)
    assert result_int == 3.0
    assert type(result_int) is float


def test_to_number_date_is_ordinal_days() -> None:
    d = date(2026, 3, 9)
    assert to_number(d, ValueKind.DATE) == float(d.toordinal())
    assert to_number(date(2026, 3, 10), ValueKind.DATE) == d.toordinal() + 1


def test_to_number_duration_seconds() -> None:
    value = timedelta(minutes=2, seconds=30, milliseconds=500)
    assert to_number(value, ValueKind.DURATION) == 150.5


def test_to_number_datetime_ordinal_seconds() -> None:
    dt = datetime(2026, 3, 9, 1, 2, 3)
    assert to_number(dt, ValueKind.DATETIME) == dt.toordinal() * 86400 + 3723
    later = datetime(2026, 3, 10, 1, 2, 3)
    assert to_number(later, ValueKind.DATETIME) == dt.toordinal() * 86400 + 86400 + 3723


def test_to_number_datetime_keeps_microseconds() -> None:
    dt = datetime(2026, 3, 9, 1, 2, 3, microsecond=500_000)
    assert to_number(dt, ValueKind.DATETIME) == dt.toordinal() * 86400 + 3723.5


@pytest.mark.parametrize("kind", [ValueKind.CATEGORY, ValueKind.BOOLEAN])
def test_to_number_non_numeric_kind_raises(kind: ValueKind) -> None:
    with pytest.raises(ValueError):
        to_number("run", kind)


@pytest.mark.parametrize(
    "kind", [ValueKind.NUMBER, ValueKind.DATE, ValueKind.DATETIME, ValueKind.DURATION]
)
def test_to_number_absent_is_none_not_zero(kind: ValueKind) -> None:
    assert to_number(None, kind) is None
