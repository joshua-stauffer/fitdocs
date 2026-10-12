"""The ``stat`` kind: one headline value, with an optional change, as markdown.

Output is ``**<title>:** <value>`` and, when a ``compare`` channel is bound,
`` (<delta> vs <compare>)``. Absent values show as the em dash, never as zero.
"""

from __future__ import annotations

from typing import Final

from fitdocs.render.charts.kit.data import Column, Value, ValueKind, to_number
from fitdocs.render.charts.kit.format import (
    ABSENT,
    clean_text,
    escape_markdown,
    format_delta,
    format_value,
)
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
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
)

_COMPARABLE: Final = (ValueKind.NUMBER, ValueKind.DURATION)

_LIMIT: Final = 1


def _unit_text(column: Column) -> str:
    return "no unit" if column.unit is None else f"unit '{column.unit}'"


def _validate(bound: BoundRequest) -> tuple[ChartProblem, ...]:
    value = bound.column("value")
    compare = bound.column("compare")
    if value is None or compare is None:
        return ()
    if compare.kind is not value.kind:
        accepted = (
            tuple(
                c.name
                for c in bound.all_columns
                if c.kind is value.kind and c.name != value.name
            )
            if value.kind in _COMPARABLE
            else ()
        )
        return (
            bound.problem(
                ProblemCode.CHANNEL_KIND,
                "Channel 'compare' must be the same kind as channel 'value', but "
                f"column '{value.name}' is {value.kind.value} and column "
                f"'{compare.name}' is {compare.kind.value}.",
                "Bind 'value' and 'compare' to columns that are both number or "
                "both duration.",
                channel="compare",
                column=compare.name,
                accepted=accepted,
            ),
        )
    if value.unit != compare.unit:
        return (
            bound.problem(
                ProblemCode.UNIT_MISMATCH,
                "Channel 'compare' must have the unit of channel 'value', but "
                f"column '{value.name}' has {_unit_text(value)} and column "
                f"'{compare.name}' has {_unit_text(compare)}.",
                "Bind 'compare' to a column with the same unit as 'value'.",
                channel="compare",
                column=compare.name,
                accepted=tuple(
                    c.name
                    for c in bound.all_columns
                    if c.kind is value.kind
                    and c.unit == value.unit
                    and c.name != value.name
                ),
            ),
        )
    return ()


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    count = len(bound.rows)
    if count > _LIMIT:
        return (
            bound.problem(
                ProblemCode.OVER_BOUND,
                f"stat draws at most {_LIMIT} row; this data has {count}.",
                "Aggregate the rows to one (for example with a SQL aggregate) or "
                "limit them to one.",
                rows=count,
            ),
        )
    return ()


def _shown(value: Value, column: Column) -> str:
    """One value as the headline shows it; category text is markdown-escaped."""
    text = format_value(value, column, with_unit=True)
    if column.kind is ValueKind.CATEGORY:
        return escape_markdown(text)
    return text


def _percent_text(delta: float, base: float) -> str:
    if base == 0:
        return ABSENT
    change = delta / abs(base) * 100
    sign = "±" if change == 0 else "+" if change > 0 else "-"
    return f"{sign}{abs(change):.1f}%"


def _comparison(bound: BoundChart, value_col: Column, compare_col: Column) -> str:
    value = bound.rows[0][_position(bound, value_col)]
    compare = bound.rows[0][_position(bound, compare_col)]
    delta_text = ABSENT
    percent_text = ABSENT
    if value is not None and compare is not None:
        now = to_number(value, value_col.kind)
        before = to_number(compare, compare_col.kind)
        assert now is not None and before is not None
        delta = now - before
        delta_text = format_delta(delta, value_col)
        percent_text = _percent_text(delta, before)
    mode = bound.choice("delta")
    if value is None or compare is None:
        shown = ABSENT
    elif mode == "percent":
        shown = percent_text
    elif mode == "both":
        shown = f"{delta_text}, {percent_text}"
    else:
        shown = delta_text
    return f" ({shown} vs {_shown(compare, compare_col)})"


def _position(bound: BoundChart, column: Column) -> int:
    return next(i for i, c in enumerate(bound.all_columns) if c.name == column.name)


def _draw(bound: BoundChart) -> str:
    title = f"**{escape_markdown(clean_text(bound.request.title))}:**"
    if not bound.rows:
        return f"{title} {ABSENT} (no data)"
    value_col = bound.columns["value"]
    value = bound.rows[0][_position(bound, value_col)]
    text = f"{title} {_shown(value, value_col)}"
    compare_col = bound.column("compare")
    if compare_col is not None:
        text += _comparison(bound, value_col, compare_col)
    return text


KIND: Final = KindSpec(
    name="stat",
    description="One headline value with its unit and an optional change",
    output=Output.MARKDOWN,
    channels=(
        ChannelSpec(
            "value",
            (
                ValueKind.NUMBER,
                ValueKind.DATE,
                ValueKind.DATETIME,
                ValueKind.DURATION,
                ValueKind.CATEGORY,
                ValueKind.BOOLEAN,
            ),
            True,
            "The headline value.",
        ),
        ChannelSpec(
            "compare",
            _COMPARABLE,
            False,
            "The value to compare against, of the same kind and unit.",
        ),
    ),
    options=(
        OptionSpec(
            "delta",
            OptionType.CHOICE,
            "How the change from the comparison is shown.",
            "absolute",
            choices=("absolute", "percent", "both"),
        ),
    ),
    bound=MarkBound(
        _LIMIT, "rows", OverBound.REFUSE, "A stat shows one row; more are refused."
    ),
    max_series=None,
    draw=_draw,
    validate=_validate,
    check=_check,
)
