"""The ``table`` kind: every column of the data as a markdown table.

Headers are the escaped axis titles, numbers and durations are right-aligned,
cells are formatted without their unit (the header carries it), absent values
are an em dash and caller text is escaped so no value can break the table.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Final

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.format import (
    axis_title,
    clean_text,
    escape_markdown,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    BoundRequest,
    KindSpec,
    MarkBound,
    Output,
    OverBound,
)
from fitdocs.units import UnitFamily, unit_named

_MAX_ROWS: Final = 100
_MAX_COLUMNS: Final = 12
_RIGHT_ALIGNED: Final = (ValueKind.NUMBER, ValueKind.DURATION)


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    count = len(bound.all_columns)
    if count > _MAX_COLUMNS:
        return (
            bound.problem(
                ProblemCode.OVER_BOUND,
                f"table draws at most {_MAX_COLUMNS} columns; this data has {count}.",
                f"Select at most {_MAX_COLUMNS} columns in the query.",
            ),
        )
    return ()


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    count = len(bound.rows)
    if count > _MAX_ROWS:
        return (
            bound.problem(
                ProblemCode.OVER_BOUND,
                f"table draws at most {_MAX_ROWS} rows; this data has {count}.",
                "Aggregate the rows (for example by day or week) or limit them to "
                f"at most {_MAX_ROWS}.",
                rows=count,
            ),
        )
    return ()


def _line(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _is_duration(column: Column) -> bool:
    if column.kind is ValueKind.DURATION:
        return True
    unit = None if column.unit is None else unit_named(column.unit)
    return (
        column.kind is ValueKind.NUMBER
        and unit is not None
        and unit.family is UnitFamily.DURATION
    )


def _seconds(value: Value) -> float:
    assert isinstance(value, int | float | Decimal | timedelta)
    if isinstance(value, timedelta):
        return value.total_seconds()
    return float(value)


def _needs_hours(column: Column, values: tuple[Value, ...]) -> bool | None:
    """For a duration column: does any present value reach an hour?"""
    if not _is_duration(column):
        return None
    return any(v is not None and round(abs(_seconds(v))) >= 3600 for v in values)


def _cell(value: Value, column: Column, hours: bool | None) -> str:
    if hours is not None and value is not None:
        return format_duration(_seconds(value), hours=hours)
    text = format_value(value, column, with_unit=False)
    return escape_markdown(text) if column.kind is ValueKind.CATEGORY else text


def _draw(bound: BoundChart) -> str:
    columns = bound.all_columns
    hours = [
        _needs_hours(c, tuple(row[i] for row in bound.rows))
        for i, c in enumerate(columns)
    ]
    lines = [
        _line(
            [
                escape_markdown(
                    clean_text(axis_title(c, hours=True if h is None else h))
                )
                for c, h in zip(columns, hours, strict=True)
            ]
        ),
        _line(["---:" if c.kind in _RIGHT_ALIGNED else "---" for c in columns]),
    ]
    if not bound.rows:
        return "\n".join([*lines, "", "No data"])
    for row in bound.rows:
        lines.append(
            _line([_cell(v, c, h) for v, c, h in zip(row, columns, hours, strict=True)])
        )
    return "\n".join(lines)


KIND: Final = KindSpec(
    name="table",
    description="The rows as a markdown table with unit-aware cells",
    output=Output.MARKDOWN,
    channels=(),
    options=(),
    bound=MarkBound(
        _MAX_ROWS,
        "rows",
        OverBound.REFUSE,
        f"At most {_MAX_ROWS} rows and {_MAX_COLUMNS} columns.",
    ),
    max_series=None,
    draw=_draw,
    validate=_validate,
    check=_check,
    uses_all_columns=True,
)
