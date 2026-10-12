"""Structured chart problems and the refusal exception.

Codes are append-only. ``message`` and ``fix`` are one sentence each, ending
with a full stop; they name the chart through ``ref`` only, never in the text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict


class ProblemCode(StrEnum):
    UNKNOWN_KIND = "unknown_kind"
    EMPTY_TITLE = "empty_title"
    DUPLICATE_COLUMN = "duplicate_column"
    UNKNOWN_CHANNEL = "unknown_channel"
    MISSING_CHANNEL = "missing_channel"
    UNKNOWN_COLUMN = "unknown_column"
    CHANNEL_KIND = "channel_kind"
    UNKNOWN_UNIT = "unknown_unit"
    UNIT_KIND = "unit_kind"
    UNIT_MISMATCH = "unit_mismatch"
    UNKNOWN_OPTION = "unknown_option"
    OPTION_VALUE = "option_value"
    OPTION_CONFLICT = "option_conflict"
    ROW_WIDTH = "row_width"
    VALUE_TYPE = "value_type"
    NON_FINITE = "non_finite"
    OVER_BOUND = "over_bound"
    TOO_MANY_SERIES = "too_many_series"
    DUPLICATE_POSITION = "duplicate_position"
    LOG_DOMAIN = "log_domain"
    STACK_ABSENT = "stack_absent"
    STACK_NEGATIVE = "stack_negative"
    STACK_INCOMPLETE = "stack_incomplete"
    # chart-catalog (appended after chart-kit's 23)
    NEGATIVE_VALUE = "negative_value"
    VALUE_ORDER = "value_order"
    SHARED_UNIT = "shared_unit"
    CHANNEL_UNIT = "channel_unit"


class ProblemDict(TypedDict):
    ref: str
    kind: str | None
    code: str
    message: str
    fix: str
    channel: str | None
    column: str | None
    option: str | None
    row: int | None
    rows: int | None
    accepted: list[str]


@dataclass(frozen=True)
class ChartProblem:
    ref: str
    kind: str | None
    code: ProblemCode
    message: str
    fix: str
    channel: str | None = None
    column: str | None = None
    option: str | None = None
    row: int | None = None  # 0-based
    rows: int | None = None
    accepted: tuple[str, ...] = ()

    def as_dict(self) -> ProblemDict:
        """JSON-ready form; keys are in field order, ``accepted`` is a list."""
        return {
            "ref": self.ref,
            "kind": self.kind,
            "code": self.code.value,
            "message": self.message,
            "fix": self.fix,
            "channel": self.channel,
            "column": self.column,
            "option": self.option,
            "row": self.row,
            "rows": self.rows,
            "accepted": list(self.accepted),
        }


class ChartError(ValueError):
    """Raised when a chart is refused; ``str(err)`` joins the messages by newline."""

    problems: tuple[ChartProblem, ...]

    def __init__(self, problems: tuple[ChartProblem, ...]) -> None:
        super().__init__("\n".join(p.message for p in problems))
        self.problems = problems
