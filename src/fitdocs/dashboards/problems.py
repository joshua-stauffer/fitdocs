"""The one problem record shared by chart-kit problems and dashboard problems.

``DashboardCode`` is append-only: its values are the JSON codes, and the order
is pinned by a prefix test, so appending is free and editing or reordering is
not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, TypedDict

from fitdocs.render.charts.kit import ChartProblem


class Source(StrEnum):
    CHART = "chart"  # raised by the chart kit
    DASHBOARD = "dashboard"  # raised by this feature


class Severity(StrEnum):
    PROBLEM = "problem"
    NOTICE = "notice"


class DashboardCode(StrEnum):
    LOCATION_FOREIGN = "location_foreign"
    PAGE_NAME = "page_name"
    PAGE_UNREADABLE = "page_unreadable"
    PAGE_ENCODING = "page_encoding"
    PAGE_CHANGED = "page_changed"
    OPENER_MALFORMED = "opener_malformed"
    MARKER_MALFORMED = "marker_malformed"
    DIRECTIVE_UNCLOSED = "directive_unclosed"
    DIRECTIVE_TERMINATOR = "directive_terminator"
    YAML_SYNTAX = "yaml_syntax"
    YAML_SHAPE = "yaml_shape"
    DUPLICATE_KEY = "duplicate_key"
    MISSING_KEY = "missing_key"
    UNKNOWN_KEY = "unknown_key"
    FIELD_VALUE = "field_value"
    ID_GRAMMAR = "id_grammar"
    DUPLICATE_ID = "duplicate_id"
    MODE_VALUE = "mode_value"
    SQL_STYLE = "sql_style"
    REGION_MISPLACED = "region_misplaced"
    REGION_MISMATCH = "region_mismatch"
    REGION_UNCLOSED = "region_unclosed"
    REGION_CONTENTS = "region_contents"
    REGION_ORPHANED = "region_orphaned"
    INDEX_UNAVAILABLE = "index_unavailable"
    SQL_REFUSED = "sql_refused"
    SQL_PARAMETER = "sql_parameter"
    SQL_FAILED = "sql_failed"
    SQL_TIMEOUT = "sql_timeout"
    ROW_CAP = "row_cap"
    COLUMN_TYPE = "column_type"
    VALUE_KIND = "value_kind"
    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_UNREADABLE = "snapshot_unreadable"
    SQL_CHANGED = "sql_changed"
    FREEZE_RELATIVE = "freeze_relative"
    ASSET_FOREIGN = "asset_foreign"
    WRITE_FAILED = "write_failed"


NOTICE_CODES: Final[frozenset[DashboardCode]] = frozenset(
    {DashboardCode.SQL_CHANGED, DashboardCode.REGION_ORPHANED}
)


class ProblemDict(TypedDict):
    source: str
    code: str
    page: str | None
    chart: str | None
    line: int | None
    message: str
    fix: str
    kind: str | None
    channel: str | None
    column: str | None
    option: str | None
    row: int | None
    rows: int | None
    accepted: list[str]


@dataclass(frozen=True)
class Problem:
    source: Source
    code: str  # a DashboardCode value or a kit ProblemCode value
    page: str | None  # page name, or the file name for page_name
    chart: str | None
    line: int | None  # 1-based page line
    message: str  # one sentence, ends with "."
    fix: str  # one sentence, ends with "."
    kind: str | None = None
    channel: str | None = None
    column: str | None = None
    option: str | None = None
    row: int | None = None
    rows: int | None = None
    accepted: tuple[str, ...] = ()

    @property
    def severity(self) -> Severity:
        """NOTICE iff the problem is a dashboards one with a notice code."""
        if self.source is Source.DASHBOARD and self.code in NOTICE_CODES:
            return Severity.NOTICE
        return Severity.PROBLEM

    def as_dict(self) -> ProblemDict:
        """JSON-ready form; keys are in field order, ``accepted`` is a list."""
        return {
            "source": self.source.value,
            "code": self.code,
            "page": self.page,
            "chart": self.chart,
            "line": self.line,
            "message": self.message,
            "fix": self.fix,
            "kind": self.kind,
            "channel": self.channel,
            "column": self.column,
            "option": self.option,
            "row": self.row,
            "rows": self.rows,
            "accepted": list(self.accepted),
        }


def dashboard_problem(
    code: DashboardCode,
    message: str,
    fix: str,
    *,
    page: str | None,
    chart: str | None = None,
    line: int | None = None,
    **fields: Any,
) -> Problem:
    """A problem raised by this feature; ``fields`` are the optional record fields."""
    return Problem(
        Source.DASHBOARD,
        code.value,
        page,
        chart,
        line,
        message,
        fix,
        **fields,
    )


def from_chart_problem(
    problem: ChartProblem,
    *,
    page: str,
    chart: str,
    line: int,
    option: str | None = None,
) -> Problem:
    """A kit problem placed on a page; ``option`` overrides the kit's option."""
    return Problem(
        Source.CHART,
        problem.code.value,
        page,
        chart,
        line,
        problem.message,
        problem.fix,
        kind=problem.kind,
        channel=problem.channel,
        column=problem.column,
        option=option if option is not None else problem.option,
        row=problem.row,
        rows=problem.rows,
        accepted=problem.accepted,
    )
