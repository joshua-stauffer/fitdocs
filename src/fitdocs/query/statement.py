"""Timed, row-capped execution for one statement."""

from __future__ import annotations

import contextlib
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
        "the query sandbox runs only queries and EXPLAIN; "
        "this is {ARTICLE} {TYPE} statement"
    ),
    Restriction.OUTSIDE_INDEX: (
        "the query sandbox cannot read or write files or addresses outside the index"
    ),
    Restriction.LOCKED_SETTING: "the query sandbox's settings are locked",
    Restriction.READ_ONLY: "the index is open read-only",
    Restriction.EXTENSION: "extensions are not available in the query sandbox",
}

TimerFactory = Callable[[float, Callable[[], None]], threading.Timer]


def statement_kind_refusal(statement_type: str) -> str:
    """The refusal text for a statement of type ``statement_type`` (no full stop)."""
    display = {"LOAD": "INSTALL or LOAD", "SET": "SET, RESET or USE"}.get(
        statement_type, statement_type
    )
    article = "an" if display[:1].upper() in "AEIOU" else "a"
    message = RESTRICTION_TEXT[Restriction.STATEMENT_KIND].format(
        ARTICLE=article, TYPE=display
    )
    if statement_type == "CALL":
        message += "; use SELECT * FROM <function>(…) instead"
    return message


class StatementRefused(Exception):
    """An executed statement was blocked by the sandbox."""

    def __init__(self, restriction: Restriction, detail: str) -> None:
        self.restriction = restriction
        self.detail = detail
        if restriction is Restriction.ONE_STATEMENT:
            super().__init__(RESTRICTION_TEXT[restriction])
            return
        if restriction is Restriction.STATEMENT_KIND:
            super().__init__(statement_kind_refusal(detail))
            return
        super().__init__(f"{RESTRICTION_TEXT[restriction]}: {detail}")


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


def is_user_interrupt(exc: BaseException) -> bool:
    """Whether ``exc`` is a Ctrl-C, however the DuckDB binding surfaced it.

    A SIGINT during a running statement reaches Python as a bare
    ``KeyboardInterrupt`` or, from inside DuckDB's fetch, as a
    ``RuntimeError("Query interrupted")`` whose ``__cause__`` is the
    ``KeyboardInterrupt``.
    """
    return isinstance(exc, KeyboardInterrupt) or isinstance(
        exc.__cause__, KeyboardInterrupt
    )


def interrupt_quietly(conn: IndexConnection) -> None:
    """Interrupt ``conn``; a failure to do so must not mask the real error."""
    with contextlib.suppress(Exception):
        conn.interrupt()


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
        except BaseException as exc:
            # Anything else escaping a running statement (a user interrupt, a
            # defect) leaves DuckDB executing it; ``close()`` would then block
            # in its destructor until the statement finished. Interrupt first.
            interrupt_quietly(conn)
            if not isinstance(exc, KeyboardInterrupt) and is_user_interrupt(exc):
                raise KeyboardInterrupt from exc
            raise
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


ALLOWED_STATEMENT_TYPES: Final[frozenset[str]] = frozenset({"SELECT", "EXPLAIN"})


def screen_statement(conn: IndexConnection, sql: str) -> None:
    """Refuse empty, multiple, or non-query statements before execution."""
    types = conn.statement_types(sql)
    if len(types) != 1:
        raise StatementRefused(Restriction.ONE_STATEMENT, ", ".join(types))
    statement_type = types[0]
    if statement_type not in ALLOWED_STATEMENT_TYPES:
        raise StatementRefused(Restriction.STATEMENT_KIND, statement_type)


def run_statement(
    conn: IndexConnection,
    sql: str,
    *,
    max_rows: int,
    timeout_s: float,
    timer: TimerFactory = threading.Timer,
) -> ResultSet:
    """Screen a statement before passing it to the timed executor."""
    screen_statement(conn, sql)
    return execute_statement(
        conn, sql, max_rows=max_rows, timeout_s=timeout_s, timer=timer
    )
