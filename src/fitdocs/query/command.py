"""One-invocation orchestration for the read-only analytics query API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Final

from fitdocs.athlete import AthleteFileError
from fitdocs.index import registry
from fitdocs.index.bookkeeping import Bookkeeping
from fitdocs.index.corpus import CorpusScan, scan_workout_pages
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.schema import SCHEMA_VERSION
from fitdocs.index.store import (
    FaultKind,
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
    run_statement,
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


def run_query(request: QueryRequest, env: QueryEnvironment) -> QueryOutcome:
    """Run one read-only query or schema request and return its typed outcome."""
    location = resolve_index_location(request.data_root, env.environ, env.home)
    remove_stale_spill(location, own_pid=env.pid, is_running=env.is_running)
    if not location.database.is_file():
        return QueryOutcome(OutcomeKind.NOT_BUILT, location)

    scan = scan_workout_pages(request.data_root)
    athlete_fingerprint = (
        current_athlete_fingerprint(request.data_root) if request.schema else None
    )
    try:
        connection = open_sandboxed(
            location,
            pid=env.pid,
            monotonic=env.monotonic,
            sleep=env.sleep,
            on_wait=env.on_wait,
        )
    except IndexBusy as error:
        return QueryOutcome(OutcomeKind.BUSY, location, holder_pid=error.holder_pid)
    except IndexOpenError as error:
        if error.fault.kind is FaultKind.MISSING:
            return QueryOutcome(OutcomeKind.NOT_BUILT, location)
        return QueryOutcome(
            OutcomeKind.NEEDS_REBUILD, location, message=error.fault.message
        )
    except SandboxUnverified as error:
        actual = error.actual if error.actual is not None else "NULL"
        return QueryOutcome(
            OutcomeKind.UNVERIFIED,
            location,
            message=(
                f"the sandbox setting {error.setting} is {actual}, not {error.expected}"
            ),
        )

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
        try:
            bookkeeping = read_bookkeeping(connection)
        except (IndexStatementError, ValueError, TypeError) as error:
            bookkeeping_error = error

        if bookkeeping_error is not None:
            rebuild_reason = f"not a complete fitdocs index: {bookkeeping_error}"
        elif bookkeeping is None:
            rebuild_reason = "not a complete fitdocs index"
        elif bookkeeping.meta.schema_version != SCHEMA_VERSION:
            rebuild_reason = (
                f"index schema version {bookkeeping.meta.schema_version} differs "
                f"from readable schema version {SCHEMA_VERSION}"
            )
        elif request.schema:
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
