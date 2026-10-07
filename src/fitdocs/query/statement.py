"""Timed, row-capped execution for one statement."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Final

from fitdocs.index.store import IndexConnection, IndexInterrupted, IndexStatementError
from fitdocs.query.format import ResultSet


class Restriction(StrEnum):
    """A sandbox policy that refused an executed statement."""

    ONE_STATEMENT = "one_statement"
    STATEMENT_KIND = "statement_kind"
    OUTSIDE_INDEX = "outside_index"
    LOCKED_SETTING = "locked_setting"
    READ_ONLY = "read_only"
    EXTENSION = "extension"


RESTRICTION_TEXT: Final[Mapping[Restriction, str]] = {
    Restriction.ONE_STATEMENT: "fitdocs query runs exactly one statement",
    Restriction.STATEMENT_KIND: (
        "the query sandbox runs only queries and EXPLAIN; this is a {TYPE} statement"
    ),
    Restriction.OUTSIDE_INDEX: (
        "the query sandbox cannot read or write files or addresses outside the index"
    ),
    Restriction.LOCKED_SETTING: "the query sandbox's settings are locked",
    Restriction.READ_ONLY: "the index is open read-only",
    Restriction.EXTENSION: "extensions are not available in the query sandbox",
}

TimerFactory = Callable[[float, Callable[[], None]], threading.Timer]


class StatementRefused(Exception):
    """An executed statement was blocked by the sandbox."""

    def __init__(self, restriction: Restriction, detail: str) -> None:
        self.restriction = restriction
        self.detail = detail
        clause = RESTRICTION_TEXT[restriction]
        super().__init__(f"{clause}: {detail}")


class StatementFailed(Exception):
    """An executed statement failed for a database reason."""

    def __init__(self, message: str, hint: str | None) -> None:
        self.message = message
        self.hint = hint
        super().__init__(message)


class StatementTimedOut(Exception):
    """An execution exceeded its configured time limit."""

    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        super().__init__(
            f"statement ran longer than {timeout_s:g} seconds and was stopped"
        )


def classify_statement_error(exc: IndexStatementError) -> Restriction | None:
    """Map stable facade causes and messages to sandbox refusal categories."""
    message = str(exc)
    cause_name = type(exc.__cause__).__name__
    if cause_name == "PermissionException":
        return Restriction.OUTSIDE_INDEX
    if (
        cause_name == "InvalidInputException"
        and "the configuration has been locked" in message
    ):
        return Restriction.LOCKED_SETTING
    if "read-only mode" in message:
        return Restriction.READ_ONLY
    if any(
        stem in message
        for stem in (
            "requires the extension",
            "requires extension",
            "exists in the httpfs extension",
        )
    ):
        return Restriction.EXTENSION
    return None


def failure_hint(exc: IndexStatementError) -> str | None:
    """Return a narrow recovery hint for known database failure causes."""
    if "Required module 'pytz'" in str(exc):
        return "cast TIMESTAMP WITH TIME ZONE values to TIMESTAMP"
    if type(exc.__cause__).__name__ == "OutOfMemoryException":
        return (
            "the statement needed more than the query sandbox's 1 GB of memory; "
            "aggregate, or filter earlier"
        )
    return None


def execute_statement(
    conn: IndexConnection,
    sql: str,
    *,
    max_rows: int,
    timeout_s: float,
    timer: TimerFactory = threading.Timer,
) -> ResultSet:
    """Execute one already-screened SQL statement and cap its in-memory rows."""
    fired = threading.Event()
    callback_lock = threading.Lock()
    stopping = False

    def fire() -> None:
        with callback_lock:
            if stopping:
                return
            fired.set()
            conn.interrupt()

    deadline = timer(timeout_s, fire)
    try:
        deadline.start()
        try:
            result = conn.execute(sql)
            rows = result.fetchmany(max_rows + 1)
        except IndexInterrupted as exc:
            if fired.is_set():
                raise StatementTimedOut(timeout_s) from exc
            raise
        except IndexStatementError as exc:
            restriction = classify_statement_error(exc)
            if restriction is not None:
                raise StatementRefused(restriction, str(exc)) from exc
            raise StatementFailed(str(exc), failure_hint(exc)) from exc
    finally:
        try:
            deadline.cancel()
        finally:
            # A callback that already owns the lock completes its interrupt
            # before this call returns. A callback arriving later sees
            # ``stopping`` and cannot act on the connection.
            with callback_lock:
                stopping = True

    return ResultSet(
        columns=tuple(column.name for column in result.columns),
        rows=tuple(rows[:max_rows]),
        truncated=len(rows) > max_rows,
        max_rows=max_rows,
    )
