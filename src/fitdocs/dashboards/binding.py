"""The query-backed chart source: the only importer of ``fitdocs.query``.

A chart's SQL is screened, bound and run through a query session, and the
result is typed column by column for the chart kit. Values pass through
unchanged; an absent value stays ``None``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final, cast

from fitdocs.dashboards.problems import DashboardCode, Problem, dashboard_problem
from fitdocs.dashboards.source import Fetched, SourceOpener, SourceUnavailable
from fitdocs.query.command import (
    DEFAULT_TIMEOUT_S,
    OutcomeKind,
    QueryEnvironment,
    QuerySession,
    SessionUnavailable,
    open_session,
)
from fitdocs.query.format import ResultSet
from fitdocs.query.statement import (
    Restriction,
    StatementFailed,
    StatementRefused,
    StatementTimedOut,
)
from fitdocs.render.charts.kit import ChartData, Column, Value, ValueKind
from fitdocs.units import unit_for_column

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ROW_CAP",
    "TODAY",
    "TYPE_KINDS",
    "QueryChartSource",
    "column_kind",
    "source_opener",
]

ROW_CAP: Final = 10_000
TODAY: Final = "today"

# Both vocabularies the supported database versions report: the SQL names
# (duckdb 1.3 and later, and relations) and the 1.2 ``description`` names.
TYPE_KINDS: Final[Mapping[str, ValueKind]] = {
    **dict.fromkeys(
        (
            "TINYINT",
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "HUGEINT",
            "UTINYINT",
            "USMALLINT",
            "UINTEGER",
            "UBIGINT",
            "UHUGEINT",
            "FLOAT",
            "DOUBLE",
            "DECIMAL",
            "NUMBER",
        ),
        ValueKind.NUMBER,
    ),
    **dict.fromkeys(("DATE", "Date"), ValueKind.DATE),
    **dict.fromkeys(
        ("TIMESTAMP", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS", "DATETIME"),
        ValueKind.DATETIME,
    ),
    **dict.fromkeys(("INTERVAL", "TIMEDELTA"), ValueKind.DURATION),
    **dict.fromkeys(("VARCHAR", "ENUM", "STRING"), ValueKind.CATEGORY),
    **dict.fromkeys(("BOOLEAN", "bool"), ValueKind.BOOLEAN),
}

_PARENTHESISED: Final = re.compile(r"([^(]+)\(.*\)", re.DOTALL)
_DEFAULT_FIX: Final = "Fix the SQL and run `fitdocs dashboard check` again."
_CAST_FIX: Final = (
    "Cast it in SQL (for example `CAST(x AS TIMESTAMP)`) or leave it out of the SELECT."
)
_ONE_SELECT_FIX: Final = "Give the chart exactly one SELECT statement."
_REFUSAL_FIX: Final[Mapping[Restriction, str]] = {
    Restriction.ONE_STATEMENT: _ONE_SELECT_FIX,
    Restriction.STATEMENT_KIND: _ONE_SELECT_FIX,
    Restriction.OUTSIDE_INDEX: (
        "Read only the index's tables; remove the file or address from the SQL."
    ),
    Restriction.LOCKED_SETTING: (
        "Remove the statement that changes a setting from the SQL."
    ),
    Restriction.READ_ONLY: (
        "Remove the statement that writes; a chart only reads the index."
    ),
    Restriction.EXTENSION: "Remove the extension, INSTALL or LOAD from the SQL.",
}
_PARAMETER_FIX: Final = (
    "Use `$today` for the run date, or write the value into the SQL."
)


def column_kind(type_name: str) -> ValueKind | None:
    """The chart value kind of a database type name, or ``None`` if it has none.

    A parenthesised suffix is dropped when the name ends with it
    (``DECIMAL(18,3)``); the lookup is then case-sensitive.
    """
    stripped = _PARENTHESISED.fullmatch(type_name)
    name = stripped.group(1) if stripped else type_name
    return TYPE_KINDS.get(name)


def _fits(kind: ValueKind, value: object) -> bool:
    """Whether a present value is of ``kind``; ``bool`` is never a number."""
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
    return type(value) is bool


def _kind_refusal(kind: str) -> str:
    article = "an" if kind[:1] in "AEIOU" else "a"
    return (
        f"a chart runs exactly one SELECT statement; this is {article} {kind} statement"
    )


def _sentence(text: str) -> str:
    return text.strip().rstrip(".") + "."


class QueryChartSource:
    """A :class:`ChartSource` that runs chart SQL through one query session."""

    def __init__(self, session: QuerySession) -> None:
        self._session = session

    def fetch(
        self, sql: str, *, today: date, page: str, chart: str, line: int
    ) -> Fetched | tuple[Problem, ...]:
        def problem(
            code: DashboardCode, message: str, fix: str, **fields: object
        ) -> Problem:
            return dashboard_problem(
                code, message, fix, page=page, chart=chart, line=line, **fields
            )

        def refused(error: StatementRefused) -> tuple[Problem, ...]:
            if error.restriction is Restriction.ONE_STATEMENT:
                message = "a chart runs exactly one SELECT statement"
            elif error.restriction is Restriction.STATEMENT_KIND:
                message = _kind_refusal(error.detail)
            else:
                message = str(error)
            return (
                problem(
                    DashboardCode.SQL_REFUSED,
                    _sentence(f"The chart's SQL was refused: {message}"),
                    _REFUSAL_FIX[error.restriction],
                ),
            )

        def failed(error: StatementFailed) -> tuple[Problem, ...]:
            return (
                problem(
                    DashboardCode.SQL_FAILED,
                    _sentence(f"The chart's SQL failed: {error.message}"),
                    _sentence(error.hint) if error.hint else _DEFAULT_FIX,
                ),
            )

        try:
            screened = self._session.screen(sql)
        except StatementRefused as error:
            return refused(error)
        except StatementFailed as error:
            return failed(error)
        if screened.kind != "SELECT":
            return (
                problem(
                    DashboardCode.SQL_REFUSED,
                    _sentence(
                        f"The chart's SQL was refused: {_kind_refusal(screened.kind)}"
                    ),
                    _ONE_SELECT_FIX,
                ),
            )
        offending = sorted(screened.parameters - {TODAY})
        if offending:
            return tuple(
                problem(
                    DashboardCode.SQL_PARAMETER,
                    f"The chart's SQL uses positional parameter {name}, which a "
                    "chart does not bind."
                    if name.isdigit()
                    else f"The chart's SQL uses the parameter `${name}`, which a "
                    "chart does not bind.",
                    _PARAMETER_FIX,
                )
                for name in offending
            )
        params: Mapping[str, object] = (
            {TODAY: today} if TODAY in screened.parameters else {}
        )
        try:
            result = self._session.run(
                sql, params=params, max_rows=ROW_CAP, timeout_s=DEFAULT_TIMEOUT_S
            )
        except StatementRefused as error:
            return refused(error)
        except StatementFailed as error:
            return failed(error)
        except StatementTimedOut as error:
            return (
                problem(
                    DashboardCode.SQL_TIMEOUT,
                    f"The chart's SQL ran longer than {error.timeout_s:g} seconds "
                    "and was stopped.",
                    "Make the query cheaper, for example by aggregating in SQL or "
                    "narrowing the date range.",
                ),
            )
        if result.truncated:
            return (
                problem(
                    DashboardCode.ROW_CAP,
                    f"The chart's SQL returned more than {ROW_CAP:,} rows.",
                    f"Aggregate in SQL (for example GROUP BY week) so the chart gets "
                    f"at most {ROW_CAP:,} rows.",
                ),
            )
        return self._typed(result, problem)

    def _typed(
        self,
        result: ResultSet,
        problem: Callable[..., Problem],
    ) -> Fetched | tuple[Problem, ...]:
        if len(result.column_types) != len(result.columns):
            raise RuntimeError(
                f"the query session reported {len(result.column_types)} column "
                f"types for {len(result.columns)} columns. "
                "This is a fitdocs defect; please report it."
            )
        kinds = [column_kind(name) for name in result.column_types]
        untyped = [
            problem(
                DashboardCode.COLUMN_TYPE,
                f"Column `{name}` has type {type_name}, which has no chart value kind.",
                _CAST_FIX,
                column=name,
            )
            for name, type_name, kind in zip(
                result.columns, result.column_types, kinds, strict=True
            )
            if kind is None
        ]
        if untyped:
            return tuple(untyped)
        mismatched: list[Problem] = []
        columns: list[Column] = []
        for position, (name, kind) in enumerate(
            zip(result.columns, kinds, strict=True)
        ):
            assert kind is not None
            offenders = [
                row
                for row, values in enumerate(result.rows)
                if values[position] is not None and not _fits(kind, values[position])
            ]
            if offenders:
                mismatched.append(
                    problem(
                        DashboardCode.VALUE_KIND,
                        f"Column `{name}` holds {len(offenders)} value(s) that are "
                        f"not {kind.value} values; the first is in row {offenders[0]}.",
                        "Cast the column in SQL so every value is a "
                        f"{kind.value}, or leave it out of the SELECT.",
                        column=name,
                        row=offenders[0],
                        rows=len(offenders),
                    )
                )
            unit = unit_for_column(name)
            columns.append(Column(name, kind, unit.token if unit else None))
        if mismatched:
            return tuple(mismatched)
        return Fetched(
            ChartData(
                tuple(columns), cast("tuple[tuple[Value, ...], ...]", result.rows)
            )
        )

    def close(self) -> None:
        """Interrupt anything still running, then close the session."""
        self._session.close()


_UNAVAILABLE_FIX: Final[Mapping[OutcomeKind, str]] = {
    OutcomeKind.NOT_BUILT: "Run `fitdocs index` to build it.",
    OutcomeKind.NEEDS_REBUILD: "Run `fitdocs index` to rebuild it.",
    OutcomeKind.BUSY: "Run the command again once the other fitdocs command finishes.",
    OutcomeKind.UNVERIFIED: "This is a fitdocs defect; please report it.",
}


def _unavailable(reason: SessionUnavailable) -> SourceUnavailable:
    kind = reason.kind
    if kind is OutcomeKind.NOT_BUILT:
        message = "the index is not built."
    elif kind is OutcomeKind.NEEDS_REBUILD:
        message = _sentence(reason.message or "the index is incompatible")
    elif kind is OutcomeKind.BUSY:
        holder = (
            f" by process {reason.holder_pid}" if reason.holder_pid is not None else ""
        )
        message = f"the index is locked{holder}."
    else:
        detail = f": {reason.message}" if reason.message else ""
        message = _sentence(f"the query sandbox could not be verified{detail}")
    return SourceUnavailable(kind.value, message, _UNAVAILABLE_FIX[kind])


def source_opener(data_root: Path, env: QueryEnvironment) -> SourceOpener:
    """An opener that opens the session on first use and then hands back that result."""
    opened: list[QueryChartSource | SourceUnavailable] = []

    def open_source() -> QueryChartSource | SourceUnavailable:
        if not opened:
            session = open_session(data_root, env)
            opened.append(
                _unavailable(session)
                if isinstance(session, SessionUnavailable)
                else QueryChartSource(session)
            )
        return opened[0]

    return open_source
