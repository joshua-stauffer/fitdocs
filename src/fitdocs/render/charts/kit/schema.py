"""The chart request, the kind declaration and the bound inputs a kind receives.

A :class:`KindSpec` declares a kind; the pipeline binds a request against it
into a :class:`BoundRequest` (columns only) and a :class:`BoundChart`
(columns and rows) that the kind's hooks read.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode

OptionValue = bool | int | float | str


class Output(StrEnum):
    SVG = "svg"
    MARKDOWN = "markdown"


class OptionType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    CHOICE = "choice"


class OverBound(StrEnum):
    REFUSE = "refuse"
    REDUCE = "reduce"


@dataclass(frozen=True)
class ChartRequest:
    ref: str
    kind: str
    title: str
    channels: Mapping[str, str] = field(default_factory=dict)
    options: Mapping[str, OptionValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    accepts: tuple[ValueKind, ...]
    required: bool
    description: str


@dataclass(frozen=True)
class OptionSpec:
    name: str
    type: OptionType
    description: str
    default: OptionValue | None
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class MarkBound:
    limit: int
    counts: str
    over: OverBound
    rule: str


def no_problems(_: object) -> tuple[ChartProblem, ...]:
    """The default ``validate`` and ``check`` hook: finds nothing."""
    return ()


@dataclass(frozen=True)
class KindSpec:
    name: str
    description: str
    output: Output
    channels: tuple[ChannelSpec, ...]
    options: tuple[OptionSpec, ...]
    bound: MarkBound
    max_series: int | None
    draw: Callable[[BoundChart], str]
    validate: Callable[[BoundRequest], tuple[ChartProblem, ...]] = no_problems
    check: Callable[[BoundChart], tuple[ChartProblem, ...]] = no_problems
    uses_all_columns: bool = False


@dataclass(frozen=True)
class BoundRequest:
    request: ChartRequest
    spec: KindSpec
    columns: Mapping[str, Column]  # bound channel -> column, spec order
    all_columns: tuple[Column, ...]
    options: Mapping[str, OptionValue | None]  # typed, defaults applied

    def column(self, channel: str) -> Column | None:
        return self.columns.get(channel)

    def flag(self, option: str) -> bool:
        value = self.options[option]
        assert isinstance(value, bool)
        return value

    def integer(self, option: str) -> int | None:
        value = self.options[option]
        if value is None:
            return None
        assert isinstance(value, int) and not isinstance(value, bool)
        return value

    def number(self, option: str) -> float | None:
        value = self.options[option]
        if value is None:
            return None
        assert isinstance(value, int | float) and not isinstance(value, bool)
        return float(value)

    def choice(self, option: str) -> str:
        value = self.options[option]
        assert isinstance(value, str)
        return value

    def problem(
        self,
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
            ref=self.request.ref,
            kind=self.spec.name,
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


@dataclass(frozen=True)
class BoundChart(BoundRequest):
    rows: tuple[tuple[Value, ...], ...]

    def values(self, channel: str) -> tuple[Value, ...]:
        """The bound column's values, in row order."""
        name = self.columns[channel].name
        index = next(i for i, c in enumerate(self.all_columns) if c.name == name)
        return tuple(row[index] for row in self.rows)

    @property
    def width(self) -> int:
        """SVG kinds: the ``width`` option (its default is applied)."""
        value = self.integer("width")
        assert value is not None
        return value

    @property
    def height(self) -> int | None:
        """The ``height`` option; ``None`` means the kind computes it."""
        return self.integer("height")


def svg_options(*own: OptionSpec, height: int | None) -> tuple[OptionSpec, ...]:
    """``own`` followed by the shared ``width`` and ``height`` options."""
    return (
        *own,
        OptionSpec(
            "width",
            OptionType.INTEGER,
            "Chart width in pixels.",
            720,
            minimum=320,
            maximum=1600,
        ),
        OptionSpec(
            "height",
            OptionType.INTEGER,
            "Chart height in pixels.",
            height,
            minimum=160,
            maximum=1200,
        ),
    )
