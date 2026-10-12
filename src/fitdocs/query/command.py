"""One-invocation orchestration for the read-only analytics query API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Final

from fitdocs.athlete import AthleteFileError
from fitdocs.index import registry
from fitdocs.index.bookkeeping import Bookkeeping
from fitdocs.index.corpus import CorpusScan, scan_workout_pages
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.schema import SCHEMA_VERSION
from fitdocs.index.store import (
    FaultKind,
    IndexConnection,
    IndexOpenError,
    IndexStatementError,
    read_bookkeeping,
)
from fitdocs.query.format import ResultSet
from fitdocs.query.freshness import (
    AthleteDrift,
    CorpusDrift,
    PageDrift,
    athlete_drift,
    corpus_drift,
    corpus_fingerprints,
    current_athlete_fingerprint,
    page_drift,
)
from fitdocs.query.sandbox import (
    IndexBusy,
    SandboxUnverified,
    open_sandboxed,
    remove_stale_spill,
)
from fitdocs.query.schemaview import CatalogTable, IndexState, read_catalog, row_counts
from fitdocs.query.statement import (
    Restriction,
    StatementFailed,
    StatementRefused,
    StatementTimedOut,
    TimerFactory,
    interrupt_quietly,
    is_user_interrupt,
    run_statement,
    screen_statement,
    statement_parameters,
)

DEFAULT_MAX_ROWS: Final[int] = 1000
DEFAULT_TIMEOUT_S: Final[float] = 30.0


@dataclass(frozen=True)
class QueryRequest:
    data_root: Path
    sql: str | None
    schema: bool
    max_rows: int
    timeout_s: float
    today: date


@dataclass(frozen=True)
class QueryEnvironment:
    environ: Mapping[str, str]
    home: Path
    pid: int
    monotonic: Callable[[], float]
    sleep: Callable[[float], None]
    on_wait: Callable[[int | None], None]
    is_running: Callable[[int], bool]
    timer: TimerFactory


class OutcomeKind(StrEnum):
    RESULT = "result"
    SCHEMA = "schema"
    NOT_BUILT = "not_built"
    NEEDS_REBUILD = "needs_rebuild"
    BUSY = "busy"
    REFUSED = "refused"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class SchemaReport:
    state: IndexState
    tables: tuple[CatalogTable, ...]
    counts: Mapping[str, int]


@dataclass(frozen=True)
class QueryOutcome:
    kind: OutcomeKind
    location: IndexLocation
    result: ResultSet | None = None
    drift: PageDrift | None = None
    schema: SchemaReport | None = None
    state: IndexState | None = None
    restriction: Restriction | None = None
    message: str | None = None
    hint: str | None = None
    holder_pid: int | None = None


def _without_computed(bookkeeping: Bookkeeping | None) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    if bookkeeping is None:
        return counts
    for page in bookkeeping.pages.values():
        state = page.computed_state.value
        if state != "computed":
            counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _state(
    location: IndexLocation,
    scan: CorpusScan,
    bookkeeping: Bookkeeping | None,
    *,
    rebuild_reason: str | None,
    drift: PageDrift | None = None,
    athlete: AthleteDrift | None = None,
    corpus: CorpusDrift | None = None,
) -> IndexState:
    return IndexState(
        database=location.database,
        recorded_schema_version=(
            bookkeeping.meta.schema_version if bookkeeping is not None else None
        ),
        reads_schema_version=SCHEMA_VERSION,
        fitdocs_version=(
            bookkeeping.meta.fitdocs_version if bookkeeping is not None else None
        ),
        drift=drift,
        left_out=scan.left_out,
        without_computed=_without_computed(bookkeeping),
        athlete=athlete,
        corpus=corpus,
        rebuild_reason=rebuild_reason,
    )


@dataclass(frozen=True)
class ScreenedStatement:
    kind: str
    parameters: frozenset[str]


@dataclass(frozen=True)
class SessionUnavailable:
    kind: OutcomeKind
    message: str | None
    holder_pid: int | None


def _locate(data_root: Path, env: QueryEnvironment) -> IndexLocation:
    """Resolve the index location and prune stale spill (before any open)."""
    location = resolve_index_location(data_root, env.environ, env.home)
    remove_stale_spill(location, own_pid=env.pid, is_running=env.is_running)
    return location


def _open(
    location: IndexLocation, env: QueryEnvironment
) -> IndexConnection | SessionUnavailable:
    """Open the sandboxed connection, or say why the index is unavailable."""
    try:
        return open_sandboxed(
            location,
            pid=env.pid,
            monotonic=env.monotonic,
            sleep=env.sleep,
            on_wait=env.on_wait,
        )
    except IndexBusy as error:
        return SessionUnavailable(OutcomeKind.BUSY, None, error.holder_pid)
    except IndexOpenError as error:
        if error.fault.kind is FaultKind.MISSING:
            return SessionUnavailable(OutcomeKind.NOT_BUILT, None, None)
        return SessionUnavailable(OutcomeKind.NEEDS_REBUILD, error.fault.message, None)
    except SandboxUnverified as error:
        actual = error.actual if error.actual is not None else "NULL"
        return SessionUnavailable(
            OutcomeKind.UNVERIFIED,
            f"the sandbox setting {error.setting} is {actual}, not {error.expected}",
            None,
        )


def _read_bookkeeping(
    connection: IndexConnection,
) -> tuple[
    Bookkeeping | None, IndexStatementError | ValueError | TypeError | None, str | None
]:
    """Read bookkeeping; return it with the load error and the rebuild reason."""
    try:
        bookkeeping = read_bookkeeping(connection)
    except (IndexStatementError, ValueError, TypeError) as error:
        return None, error, f"not a complete fitdocs index: {error}"
    if bookkeeping is None:
        return None, None, "not a complete fitdocs index"
    if bookkeeping.meta.schema_version != SCHEMA_VERSION:
        return (
            bookkeeping,
            None,
            f"index schema version {bookkeeping.meta.schema_version} differs "
            f"from readable schema version {SCHEMA_VERSION}",
        )
    return bookkeeping, None, None


def run_query(request: QueryRequest, env: QueryEnvironment) -> QueryOutcome:
    """Run one read-only query or schema request and return its typed outcome."""
    location = _locate(request.data_root, env)
    if not location.database.is_file():
        return QueryOutcome(OutcomeKind.NOT_BUILT, location)

    scan = scan_workout_pages(request.data_root)
    athlete_fingerprint = (
        current_athlete_fingerprint(request.data_root) if request.schema else None
    )
    opened = _open(location, env)
    if isinstance(opened, SessionUnavailable):
        return QueryOutcome(
            opened.kind, location, message=opened.message, holder_pid=opened.holder_pid
        )
    connection = opened

    bookkeeping: Bookkeeping | None = None
    bookkeeping_error: IndexStatementError | ValueError | TypeError | None = None
    rebuild_reason: str | None = None
    result: ResultSet | None = None
    refusal: StatementRefused | None = None
    statement_failure: StatementFailed | None = None
    timeout: StatementTimedOut | None = None
    parse_failure: IndexStatementError | None = None
    tables: tuple[CatalogTable, ...] | None = None
    counts: Mapping[str, int] | None = None
    athlete: AthleteDrift | None = None

    try:
        bookkeeping, bookkeeping_error, rebuild_reason = _read_bookkeeping(connection)

        if rebuild_reason is None:
            assert bookkeeping is not None
            if request.schema:
                assert athlete_fingerprint is not None
                tables = read_catalog(connection)
                counts = row_counts(connection, tables)
                athlete = athlete_drift(connection, athlete_fingerprint)
            else:
                assert request.sql is not None
                try:
                    result = run_statement(
                        connection,
                        request.sql,
                        max_rows=request.max_rows,
                        timeout_s=request.timeout_s,
                        timer=env.timer,
                    )
                except StatementRefused as error:
                    refusal = error
                except StatementFailed as error:
                    statement_failure = error
                except StatementTimedOut as error:
                    timeout = error
                except IndexStatementError as error:
                    parse_failure = error
    except BaseException as exc:
        # The statement path has already interrupted and converted; the
        # bookkeeping and schema reads have not. Stop whatever is running so
        # close() returns, and give DuckDB's interrupt the same shape.
        interrupt_quietly(connection)
        if not isinstance(exc, KeyboardInterrupt) and is_user_interrupt(exc):
            raise KeyboardInterrupt from exc
        raise
    finally:
        connection.close()

    if bookkeeping_error is not None or bookkeeping is None:
        assert rebuild_reason is not None
        state = (
            _state(location, scan, None, rebuild_reason=rebuild_reason)
            if request.schema
            else None
        )
        return QueryOutcome(
            OutcomeKind.NEEDS_REBUILD,
            location,
            state=state,
            message=rebuild_reason,
        )

    drift = page_drift(scan, bookkeeping.pages)
    if rebuild_reason is not None:
        state = (
            _state(
                location,
                scan,
                bookkeeping,
                rebuild_reason=rebuild_reason,
                drift=drift,
            )
            if request.schema
            else None
        )
        return QueryOutcome(
            OutcomeKind.NEEDS_REBUILD,
            location,
            drift=drift,
            state=state,
            message=rebuild_reason,
        )

    if request.schema:
        assert tables is not None and counts is not None
        assert athlete_fingerprint is not None
        if isinstance(athlete_fingerprint, AthleteFileError):
            corpus = CorpusDrift(
                (),
                tuple(
                    (producer.name, f"AthleteFileError: {athlete_fingerprint}")
                    for producer in registry.CORPUS_PRODUCERS
                ),
            )
        else:
            assert isinstance(athlete_fingerprint, str)
            current = corpus_fingerprints(
                scan,
                bookkeeping.pages,
                data_root=request.data_root,
                today=request.today,
                athlete_fingerprint=athlete_fingerprint,
            )
            producer_tables = {
                producer.name: tuple(table.name for table in producer.tables)
                for producer in registry.CORPUS_PRODUCERS
            }
            corpus = corpus_drift(current, bookkeeping.producers, producer_tables)
        state = _state(
            location,
            scan,
            bookkeeping,
            rebuild_reason=None,
            drift=drift,
            athlete=athlete,
            corpus=corpus,
        )
        report = SchemaReport(state, tables, counts)
        return QueryOutcome(OutcomeKind.SCHEMA, location, schema=report)

    if refusal is not None:
        return QueryOutcome(
            OutcomeKind.REFUSED,
            location,
            drift=drift,
            restriction=refusal.restriction,
            message=refusal.detail,
        )
    if statement_failure is not None:
        return QueryOutcome(
            OutcomeKind.FAILED,
            location,
            drift=drift,
            message=statement_failure.message,
            hint=statement_failure.hint,
        )
    if timeout is not None:
        return QueryOutcome(
            OutcomeKind.TIMED_OUT,
            location,
            drift=drift,
            message=str(timeout),
        )
    if parse_failure is not None:
        return QueryOutcome(
            OutcomeKind.FAILED,
            location,
            drift=drift,
            message=str(parse_failure),
        )
    assert result is not None
    return QueryOutcome(OutcomeKind.RESULT, location, result=result, drift=drift)


class QuerySession:
    """One sandboxed connection that runs many read-only statements.

    Every ``run`` consumes its statement into a ``ResultSet`` before returning,
    so the connection never holds an unfinished cursor-backed result when the
    next statement starts.
    """

    def __init__(self, connection: IndexConnection, timer: TimerFactory) -> None:
        self._connection = connection
        self._timer = timer
        self._closed = False

    def screen(self, sql: str) -> ScreenedStatement:
        """Classify ``sql`` without executing it."""
        try:
            kind = screen_statement(self._connection, sql)
            parameters = statement_parameters(self._connection, sql)
        except IndexStatementError as error:
            raise StatementFailed(str(error), None) from error
        return ScreenedStatement(kind, parameters)

    def run(
        self,
        sql: str,
        *,
        params: Mapping[str, object],
        max_rows: int,
        timeout_s: float,
    ) -> ResultSet:
        """Run one statement with ``params`` (possibly empty) and cap its rows."""
        try:
            return run_statement(
                self._connection,
                sql,
                max_rows=max_rows,
                timeout_s=timeout_s,
                timer=self._timer,
                params=params,
            )
        except (StatementRefused, StatementFailed, StatementTimedOut):
            raise
        except IndexStatementError as error:
            raise StatementFailed(str(error), None) from error
        except BaseException as exc:
            interrupt_quietly(self._connection)
            if not isinstance(exc, KeyboardInterrupt) and is_user_interrupt(exc):
                raise KeyboardInterrupt from exc
            raise

    def close(self) -> None:
        """Interrupt anything still running, then close; safe to repeat."""
        if self._closed:
            return
        self._closed = True
        interrupt_quietly(self._connection)
        self._connection.close()

    def __enter__(self) -> QuerySession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def open_session(
    data_root: Path, env: QueryEnvironment
) -> QuerySession | SessionUnavailable:
    """Open a sandboxed session, or say why the index cannot be queried."""
    location = _locate(data_root, env)
    if not location.database.is_file():
        return SessionUnavailable(OutcomeKind.NOT_BUILT, None, None)
    opened = _open(location, env)
    if isinstance(opened, SessionUnavailable):
        return opened
    try:
        _, _, rebuild_reason = _read_bookkeeping(opened)
    except BaseException as exc:
        interrupt_quietly(opened)
        opened.close()
        if not isinstance(exc, KeyboardInterrupt) and is_user_interrupt(exc):
            raise KeyboardInterrupt from exc
        raise
    if rebuild_reason is not None:
        opened.close()
        return SessionUnavailable(OutcomeKind.NEEDS_REBUILD, rebuild_reason, None)
    return QuerySession(opened, env.timer)
