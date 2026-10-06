"""Build and atomically swap the per-data-root analytics index."""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import suppress
from datetime import date
from pathlib import Path

from fitdocs import version
from fitdocs.index import registry
from fitdocs.index.bookkeeping import Bookkeeping, IndexMeta
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.location import (
    IndexLocation,
    IndexLocationError,
    ensure_directory,
    resolve_index_location,
)
from fitdocs.index.lock import WriterBusy, writer_lock
from fitdocs.index.refresh import (
    IndexReport,
    Outcome,
    ProgressCallback,
    RefreshInputs,
    RefreshResult,
)
from fitdocs.index.refresh import (
    reconcile as reconcile,
)
from fitdocs.index.schema import SCHEMA_VERSION, TableScope
from fitdocs.index.store import (
    IndexOpenError,
    checkpoint,
    create_index,
    create_schema,
    duckdb_version,
    open_index,
    read_bookkeeping,
    write_meta,
    write_producer_state,
)
from fitdocs.metrics.types import AthleteInputs


def run_index_command(
    data_root: Path,
    *,
    environ: Mapping[str, str],
    home: Path,
    athlete: AthleteInputs | None,
    today: date,
    rebuild: bool,
    progress: ProgressCallback | None,
) -> IndexReport:
    """Build or refresh, preserving config errors for the CLI."""
    location: IndexLocation | None = None
    try:
        location = resolve_index_location(data_root, environ, home)
        ensure_directory(location)
        with writer_lock(location.lock):
            if location.staged.exists():
                try:
                    _swap(location, location.staged)
                except PermissionError as error:
                    return IndexReport(Outcome.STAGED, location, str(error), None, None)

            reason: str | None = None
            bookkeeping: Bookkeeping | None = None
            if rebuild:
                reason = "rebuild requested"
            elif not location.database.exists():
                reason = "index does not exist"
            else:
                try:
                    with open_index(location.database, read_only=False) as connection:
                        bookkeeping = read_bookkeeping(connection)
                except IndexOpenError as error:
                    if error.fault.kind.value == "locked":
                        return IndexReport(
                            Outcome.BUSY,
                            location,
                            error.fault.message,
                            error.fault.holder_pid,
                            None,
                        )
                    if error.fault.kind.value == "missing":
                        reason = error.fault.message
                    else:
                        reason = error.fault.message

                if reason is None and bookkeeping is None:
                    reason = "not a complete fitdocs index"
                elif (
                    reason is None
                    and bookkeeping is not None
                    and bookkeeping.meta.schema_version != SCHEMA_VERSION
                ):
                    reason = (
                        f"schema version {bookkeeping.meta.schema_version}; "
                        f"this fitdocs uses {SCHEMA_VERSION}"
                    )

            if reason is not None:
                result = _build(
                    location, athlete=athlete, today=today, progress=progress
                )
                try:
                    _swap(location, location.building)
                except PermissionError as error:
                    return IndexReport(Outcome.STAGED, location, str(error), None, None)
                return IndexReport(Outcome.BUILT, location, reason, None, result)

            with open_index(location.database, read_only=False) as connection:
                current = _require_bookkeeping(read_bookkeeping(connection))
                result = reconcile(
                    connection,
                    current,
                    RefreshInputs(
                        data_root=location.data_root,
                        athlete=athlete,
                        handoff=None,
                        today=today,
                        progress=progress,
                    ),
                )
            outcome = Outcome.REFRESHED if result.changed else Outcome.UNCHANGED
            return IndexReport(outcome, location, None, None, result)
    except WriterBusy as error:
        return IndexReport(Outcome.BUSY, location, str(error), None, None)
    except IndexLocationError:
        raise
    except Exception as error:
        return IndexReport(
            Outcome.FAILED,
            location,
            f"{type(error).__name__}: {error}",
            None,
            None,
        )


def _require_bookkeeping(value: Bookkeeping | None) -> Bookkeeping:
    if value is None:
        raise RuntimeError("index is missing fitdocs bookkeeping")
    return value


def _build(
    location: IndexLocation,
    *,
    athlete: AthleteInputs | None,
    today: date,
    progress: ProgressCallback | None,
) -> RefreshResult:
    location.building.unlink(missing_ok=True)
    location.building.with_name(location.building.name + ".wal").unlink(missing_ok=True)

    tables = registry.registered_tables()
    documents = registry.DOCUMENT_PRODUCERS
    computed = registry.COMPUTED_PRODUCERS
    corpus = registry.CORPUS_PRODUCERS
    meta = IndexMeta(
        schema_version=SCHEMA_VERSION,
        fitdocs_version=version.tool_version(),
        duckdb_version=duckdb_version(),
        data_root=str(location.data_root),
        athlete_fingerprint=athlete_fingerprint(athlete),
    )
    producer_states: dict[str, str | None] = {}
    for document_producer in documents:
        producer_states[document_producer.name] = None
    for computed_producer in computed:
        producer_states[computed_producer.name] = None
    for corpus_producer in corpus:
        producer_states[corpus_producer.name] = None

    with create_index(location.building) as connection:
        create_schema(connection, tables)
        write_meta(connection, meta)
        for document_producer in documents:
            write_producer_state(
                connection,
                document_producer.name,
                TableScope.DOCUMENT,
                tuple(table.name for table in document_producer.tables),
                None,
            )
        for computed_producer in computed:
            write_producer_state(
                connection,
                computed_producer.name,
                TableScope.COMPUTED,
                tuple(table.name for table in computed_producer.tables),
                None,
            )
        for corpus_producer in corpus:
            write_producer_state(
                connection,
                corpus_producer.name,
                TableScope.CORPUS,
                tuple(table.name for table in corpus_producer.tables),
                None,
            )
        result = reconcile(
            connection,
            Bookkeeping(meta, {}, producer_states),
            RefreshInputs(
                data_root=location.data_root,
                athlete=athlete,
                handoff=None,
                today=today,
                progress=progress,
            ),
        )
        checkpoint(connection)
    return result


def _swap(location: IndexLocation, source: Path) -> None:
    location.wal.unlink(missing_ok=True)
    try:
        os.replace(source, location.database)
    except PermissionError:
        if source != location.building:
            raise
        with suppress(FileNotFoundError):
            location.staged.unlink()
        os.replace(location.building, location.staged)
        raise
