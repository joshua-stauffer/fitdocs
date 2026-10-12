"""Request validation, option parsing and binding (stages 1 and 2).

Stage 1 (:func:`validate_request`) needs the request and column descriptions
only; stage 2 (:func:`check_data`) needs the bound request and the rows. Every
loop runs over the kind's declared channels and options in spec order and over
unknown names in sorted order, never the request's mapping order.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from fitdocs.render.charts.kit.data import (
    Column,
    Value,
    ValueKind,
    accepts,
    is_finite_number,
)
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    BoundRequest,
    ChartRequest,
    KindSpec,
    OptionSpec,
    OptionType,
    OptionValue,
)
from fitdocs.units import UnitFamily, unit_named

_INTEGER_TEXT = re.compile(r"-?[0-9]+")
_NUMBER_TEXT = re.compile(r"-?[0-9]+(\.[0-9]+)?")

_CLOCK_KINDS = (ValueKind.DATE, ValueKind.DATETIME)


def _problem(
    request: ChartRequest,
    kind: str | None,
    code: ProblemCode,
    message: str,
    fix: str,
    *,
    channel: str | None = None,
    column: str | None = None,
    option: str | None = None,
    row: int | None = None,
    rows: int | None = None,
    accepted: tuple[str, ...] = (),
) -> ChartProblem:
    return ChartProblem(
        ref=request.ref,
        kind=kind,
        code=code,
        message=message,
        fix=fix,
        channel=channel,
        column=column,
        option=option,
        row=row,
        rows=rows,
        accepted=accepted,
    )


def _kinds_text(kinds: Sequence[ValueKind]) -> str:
    return " or ".join(k.value for k in kinds)


def _bound_text(value: float) -> str:
    """A bound written without loss: whole numbers plain, others by ``repr``."""
    number = float(value)
    return str(int(number)) if number.is_integer() else repr(number)


def _bounds_text(spec: OptionSpec) -> str:
    if spec.minimum is not None and spec.maximum is not None:
        return f" from {_bound_text(spec.minimum)} to {_bound_text(spec.maximum)}"
    if spec.minimum is not None:
        return f" of at least {_bound_text(spec.minimum)}"
    if spec.maximum is not None:
        return f" of at most {_bound_text(spec.maximum)}"
    return ""


def _accepts_text(spec: OptionSpec) -> str:
    if spec.type is OptionType.BOOLEAN:
        return "true or false"
    if spec.type is OptionType.INTEGER:
        return f"an integer{_bounds_text(spec)}"
    if spec.type is OptionType.NUMBER:
        return f"a finite number{_bounds_text(spec)}"
    return "one of " + ", ".join(spec.choices)


def _in_bounds(spec: OptionSpec, value: float) -> bool:
    if spec.minimum is not None and value < spec.minimum:
        return False
    return spec.maximum is None or value <= spec.maximum


def parse_option(spec: OptionSpec, raw: OptionValue) -> OptionValue | None:
    """The typed value of ``raw`` for ``spec``, or ``None`` if it is invalid.

    A typed value of the right type is kept; a string is accepted in its
    canonical text form (``true``/``false``, ``-?[0-9]+``,
    ``-?[0-9]+(\\.[0-9]+)?``, an exact choice). Bounds are inclusive.
    """
    if spec.type is OptionType.BOOLEAN:
        if isinstance(raw, bool):
            return raw
        if raw == "true":
            return True
        if raw == "false":
            return False
        return None
    if spec.type is OptionType.INTEGER:
        if isinstance(raw, bool | float):
            return None
        if isinstance(raw, str):
            if not _INTEGER_TEXT.fullmatch(raw):
                return None
            try:
                parsed = int(raw)
            except ValueError:  # beyond the interpreter's digit limit
                return None
        else:
            parsed = raw
        return parsed if _in_bounds(spec, parsed) else None
    if spec.type is OptionType.NUMBER:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, str):
            if not _NUMBER_TEXT.fullmatch(raw):
                return None
            number = float(raw)
            typed: OptionValue = number
        else:
            number = float(raw)
            typed = raw
        if not math.isfinite(number):
            return None
        return typed if _in_bounds(spec, number) else None
    if isinstance(raw, str) and raw in spec.choices:
        return raw
    return None


def _fitting(
    channel_accepts: Sequence[ValueKind], columns: Sequence[Column]
) -> tuple[str, ...]:
    return tuple(c.name for c in columns if c.kind in channel_accepts)


def _first_named(columns: Sequence[Column], name: str) -> Column | None:
    for column in columns:
        if column.name == name:
            return column
    return None


def _unit_problem(
    request: ChartRequest,
    kind: str,
    column: Column,
    channel: str | None,
) -> ChartProblem | None:
    if column.unit is None:
        return None
    unit = unit_named(column.unit)
    if unit is None:
        return _problem(
            request,
            kind,
            ProblemCode.UNKNOWN_UNIT,
            f"Column '{column.name}' (kind {column.kind.value}) has unit "
            f"'{column.unit}', which is not in the unit vocabulary.",
            "Use a unit token from the unit vocabulary, or give the column no unit.",
            channel=channel,
            column=column.name,
        )
    if unit.family is UnitFamily.CLOCK:
        applies = column.kind in _CLOCK_KINDS
    else:
        applies = column.kind is ValueKind.NUMBER
    if applies:
        return None
    return _problem(
        request,
        kind,
        ProblemCode.UNIT_KIND,
        f"Column '{column.name}' (kind {column.kind.value}) cannot carry unit "
        f"'{column.unit}'.",
        "Alias the column in the query to a name without a unit suffix, or "
        "with one that fits its value kind.",
        channel=channel,
        column=column.name,
    )


def validate_request(
    request: ChartRequest,
    columns: Sequence[Column],
    spec: KindSpec | None,
    registered: Sequence[str],
) -> tuple[ChartProblem, ...]:
    """Stage 1: every request-level problem, in the designed order."""
    kind = spec.name if spec is not None else None
    problems: list[ChartProblem] = []

    if spec is None:
        problems.append(
            _problem(
                request,
                None,
                ProblemCode.UNKNOWN_KIND,
                f"Kind '{request.kind}' is not registered.",
                "Use one of the registered kinds.",
                accepted=tuple(registered),
            )
        )
    if not request.title.strip():
        problems.append(
            _problem(
                request,
                kind,
                ProblemCode.EMPTY_TITLE,
                "The title is empty.",
                "Give the chart a non-empty title.",
            )
        )
    seen: set[str] = set()
    reported: set[str] = set()
    for column in columns:
        if column.name in seen and column.name not in reported:
            reported.add(column.name)
            problems.append(
                _problem(
                    request,
                    kind,
                    ProblemCode.DUPLICATE_COLUMN,
                    f"Column '{column.name}' appears more than once.",
                    "Give every column a unique name, for example with an alias in the "
                    "query.",
                    column=column.name,
                )
            )
        seen.add(column.name)

    if spec is None:
        return tuple(problems)

    for channel in spec.channels:
        bound_name = request.channels.get(channel.name)
        fitting = _fitting(channel.accepts, columns)
        kinds = _kinds_text(channel.accepts)
        if bound_name is None:
            if channel.required:
                problems.append(
                    _problem(
                        request,
                        kind,
                        ProblemCode.MISSING_CHANNEL,
                        f"Required channel '{channel.name}' is not bound.",
                        f"Bind '{channel.name}' to a column of kind {kinds}.",
                        channel=channel.name,
                        accepted=fitting,
                    )
                )
            continue
        found = _first_named(columns, bound_name)
        if found is None:
            problems.append(
                _problem(
                    request,
                    kind,
                    ProblemCode.UNKNOWN_COLUMN,
                    f"Channel '{channel.name}' is bound to column '{bound_name}', "
                    "which is not among the columns.",
                    f"Bind '{channel.name}' to a column of kind {kinds}.",
                    channel=channel.name,
                    column=bound_name,
                    accepted=fitting,
                )
            )
            continue
        if found.kind not in channel.accepts:
            problems.append(
                _problem(
                    request,
                    kind,
                    ProblemCode.CHANNEL_KIND,
                    f"Channel '{channel.name}' accepts {kinds} columns, but "
                    f"column '{found.name}' is {found.kind.value}.",
                    f"Bind '{channel.name}' to a column of kind {kinds}.",
                    channel=channel.name,
                    column=found.name,
                    accepted=fitting,
                )
            )
        if not spec.uses_all_columns:
            unit_problem = _unit_problem(request, spec.name, found, channel.name)
            if unit_problem is not None:
                problems.append(unit_problem)
    if spec.uses_all_columns:
        for column in columns:
            unit_problem = _unit_problem(request, spec.name, column, None)
            if unit_problem is not None:
                problems.append(unit_problem)

    declared_channels = tuple(c.name for c in spec.channels)
    for name in sorted(set(request.channels) - set(declared_channels)):
        problems.append(
            _problem(
                request,
                kind,
                ProblemCode.UNKNOWN_CHANNEL,
                f"Channel '{name}' is not declared by kind '{spec.name}'.",
                "Bind only the channels the kind declares.",
                channel=name,
                accepted=declared_channels,
            )
        )

    for option in spec.options:
        if option.name not in request.options:
            continue
        if parse_option(option, request.options[option.name]) is None:
            problems.append(
                _problem(
                    request,
                    kind,
                    ProblemCode.OPTION_VALUE,
                    f"Option '{option.name}' does not accept this value; it takes "
                    f"{_accepts_text(option)}.",
                    f"Set '{option.name}' to {_accepts_text(option)}.",
                    option=option.name,
                    accepted=option.choices,
                )
            )
    declared_options = tuple(o.name for o in spec.options)
    for name in sorted(set(request.options) - set(declared_options)):
        problems.append(
            _problem(
                request,
                kind,
                ProblemCode.UNKNOWN_OPTION,
                f"Option '{name}' is not declared by kind '{spec.name}'.",
                "Set only the options the kind declares.",
                option=name,
                accepted=declared_options,
            )
        )

    if not problems:
        problems.extend(spec.validate(bind_request(request, columns, spec)))
    return tuple(problems)


def bind_request(
    request: ChartRequest, columns: Sequence[Column], spec: KindSpec
) -> BoundRequest:
    """Bind a request that :func:`validate_request` found clean.

    Channels follow the spec's order; options are typed with defaults applied.
    Nothing is inferred from column names. Raises ``ValueError`` when a bound
    channel names a missing column or an option value is invalid; it does no
    other validation.
    """
    bound_columns: dict[str, Column] = {}
    for channel in spec.channels:
        name = request.channels.get(channel.name)
        if name is None:
            continue
        column = _first_named(columns, name)
        if column is None:
            raise ValueError(f"channel '{channel.name}' is bound to a missing column")
        bound_columns[channel.name] = column
    options: dict[str, OptionValue | None] = {}
    for option in spec.options:
        if option.name not in request.options:
            options[option.name] = option.default
            continue
        parsed = parse_option(option, request.options[option.name])
        if parsed is None:
            raise ValueError(f"option '{option.name}' has an invalid value")
        options[option.name] = parsed
    return BoundRequest(
        request=request,
        spec=spec,
        columns=bound_columns,
        all_columns=tuple(columns),
        options=options,
    )


def check_data(
    bound: BoundRequest, rows: Sequence[Sequence[Value]]
) -> tuple[ChartProblem, ...]:
    """Stage 2: row widths, then per used column ``value_type`` and ``non_finite``."""
    request = bound.request
    kind = bound.spec.name
    width = len(bound.all_columns)
    for index, row in enumerate(rows):
        if len(row) != width:
            return (
                _problem(
                    request,
                    kind,
                    ProblemCode.ROW_WIDTH,
                    f"Row {index} holds {len(row)} values but there are {width} "
                    "columns.",
                    "Give every row exactly one value per column.",
                    row=index,
                ),
            )
    used = (
        bound.all_columns
        if bound.spec.uses_all_columns
        else tuple(bound.columns.values())
    )
    problems: list[ChartProblem] = []
    done: set[str] = set()
    for column in used:
        if column.name in done:
            continue
        done.add(column.name)
        position = next(
            i for i, c in enumerate(bound.all_columns) if c.name == column.name
        )
        wrong = [
            i for i, row in enumerate(rows) if not accepts(column.kind, row[position])
        ]
        if wrong:
            problems.append(
                _problem(
                    request,
                    kind,
                    ProblemCode.VALUE_TYPE,
                    f"Column '{column.name}' holds values that are not of kind "
                    f"{column.kind.value} (first at row {wrong[0]}, rows affected: "
                    f"{len(wrong)}).",
                    f"Give column '{column.name}' only {column.kind.value} values or "
                    "absent ones.",
                    column=column.name,
                    row=wrong[0],
                    rows=len(wrong),
                )
            )
        if column.kind is ValueKind.NUMBER:
            infinite = [
                i
                for i, row in enumerate(rows)
                if accepts(column.kind, row[position])
                and row[position] is not None
                and not is_finite_number(row[position])
            ]
            if infinite:
                problems.append(
                    _problem(
                        request,
                        kind,
                        ProblemCode.NON_FINITE,
                        f"Column '{column.name}' holds NaN or infinite numbers "
                        f"(first at row {infinite[0]}, rows affected: "
                        f"{len(infinite)}).",
                        f"Replace them in column '{column.name}' with finite "
                        "numbers or absent values.",
                        column=column.name,
                        row=infinite[0],
                        rows=len(infinite),
                    )
                )
    return tuple(problems)


def bind_chart(bound: BoundRequest, rows: Sequence[Sequence[Value]]) -> BoundChart:
    """The bound request plus its rows, frozen."""
    return BoundChart(
        request=bound.request,
        spec=bound.spec,
        columns=bound.columns,
        all_columns=bound.all_columns,
        options=bound.options,
        rows=tuple(tuple(row) for row in rows),
    )
