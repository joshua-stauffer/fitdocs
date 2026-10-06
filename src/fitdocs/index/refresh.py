"""Reconcile indexed workout pages with their current documents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from fitdocs.index import corpus, derive, fingerprint, registry
from fitdocs.index.bookkeeping import (
    BOOKKEEPING_TABLES,
    Bookkeeping,
    ComputedState,
    PageState,
)
from fitdocs.index.corpus import LeftOutPage, ScannedPage
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.producer import (
    ComputedProducer,
    DocumentProducer,
    PageComputed,
    PageDocument,
)
from fitdocs.index.schema import ResolvedTable, TableScope, resolve_tables
from fitdocs.index.store import (
    IndexConnection,
    delete_page_rows,
    delete_page_state,
    insert_rows,
    transaction,
    write_page_state,
)
from fitdocs.metrics.types import AthleteInputs

ProgressCallback = Callable[[int, int], None]
PROGRESS_EVERY: Final[int] = 100


@dataclass(frozen=True)
class RefreshInputs:
    data_root: Path
    athlete: AthleteInputs | None
    handoff: HandoffCollector | None
    today: date
    progress: ProgressCallback | None


@dataclass(frozen=True)
class RefreshResult:
    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    without_computed: tuple[tuple[str, ComputedState], ...]
    page_errors: tuple[tuple[str, str], ...]
    producer_errors: tuple[tuple[str, str], ...]
    left_out: tuple[LeftOutPage, ...]
    corpus_refreshed: tuple[str, ...]
    pages_held: int

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.corpus_refreshed)


def _computed_tables(tables: tuple[ResolvedTable, ...]) -> tuple[ResolvedTable, ...]:
    return tuple(table for table in tables if table.scope is TableScope.COMPUTED)


def _document_tables(tables: tuple[ResolvedTable, ...]) -> tuple[ResolvedTable, ...]:
    return tuple(table for table in tables if table.scope is TableScope.DOCUMENT)


def _insert_producer_rows(
    conn: IndexConnection,
    producer: DocumentProducer | ComputedProducer,
    supplied_tables: tuple[ResolvedTable, ...],
    value: PageDocument | PageComputed,
    *,
    page_key: str,
) -> None:
    rows = producer.rows(value)  # type: ignore[arg-type]
    resolved = {table.name: table for table in supplied_tables}
    for table_spec in producer.tables:
        table = resolved[table_spec.name]
        insert_rows(conn, table, rows[table.name], page_key=page_key)


def _document_for(page: ScannedPage) -> PageDocument:
    return PageDocument(
        page_key=page.page_key,
        path=page.path,
        text=page.text,
        frontmatter=page.frontmatter,
        sources=page.sources,
        load=corpus._load_region_reading(page.text),
    )


def _page_computed(
    document: PageDocument,
    inputs: RefreshInputs,
    page: ScannedPage,
) -> tuple[PageComputed | None, ComputedState]:
    handed = (
        inputs.handoff.take(page.page_key, page.sources)
        if inputs.handoff is not None
        else None
    )
    if handed is not None:
        return (
            PageComputed(
                document=document,
                activity=handed.composition.activity,
                metrics=handed.metrics,
                provenance=handed.composition.provenance,
                athlete=handed.athlete,
                athlete_fingerprint=fingerprint.athlete_fingerprint(handed.athlete),
            ),
            ComputedState.COMPUTED,
        )
    result = derive.derive_page(inputs.data_root, page.sources, inputs.athlete)
    if isinstance(result, derive.Derived):
        return (
            PageComputed(
                document=document,
                activity=result.composition.activity,
                metrics=result.metrics,
                provenance=result.composition.provenance,
                athlete=inputs.athlete,
                athlete_fingerprint=fingerprint.athlete_fingerprint(inputs.athlete),
            ),
            ComputedState.COMPUTED,
        )
    return None, result


def reconcile(
    conn: IndexConnection, bookkeeping: Bookkeeping, inputs: RefreshInputs
) -> RefreshResult:
    scan = corpus.scan_workout_pages(inputs.data_root)
    tables = resolve_tables(
        registry.DOCUMENT_PRODUCERS,
        registry.COMPUTED_PRODUCERS,
        registry.CORPUS_PRODUCERS,
        BOOKKEEPING_TABLES,
    )
    document_tables = _document_tables(tables)
    computed_tables = _computed_tables(tables)
    document_producers = registry.DOCUMENT_PRODUCERS
    computed_producers = registry.COMPUTED_PRODUCERS

    states = dict(bookkeeping.pages)
    added: list[str] = []
    updated: list[str] = []
    page_errors: list[tuple[str, str]] = []
    scanned_keys: set[str] = set()

    for page in scan.pages:
        page_key = page.page_key
        scanned_keys.add(page_key)
        previous = bookkeeping.pages.get(page_key)
        document_due = (
            previous is None
            or previous.document_fingerprint != page.document_fingerprint
        )
        current_render_fingerprint = fingerprint.render_fingerprint(
            page.text, page.frontmatter
        )
        computed_due = previous is None
        if previous is not None:
            source_still_missing = (
                previous.computed_state is ComputedState.SOURCE_MISSING
                and derive.base_archive(inputs.data_root, page.sources) is None
            )
            retry_due = (
                previous.computed_state is not ComputedState.COMPUTED
                and not source_still_missing
            )
            render_due = (
                document_due
                and current_render_fingerprint != previous.render_fingerprint
            )
            computed_due = retry_due or render_due

        if not document_due and not computed_due:
            continue

        try:
            document = _document_for(page)
            computed: PageComputed | None = None
            computed_state = (
                previous.computed_state
                if previous is not None
                else ComputedState.SOURCE_MISSING
            )
            render_state = (
                previous.render_fingerprint
                if previous is not None
                else current_render_fingerprint
            )
            if computed_due:
                computed, computed_state = _page_computed(document, inputs, page)
                render_state = current_render_fingerprint

            # A repeated failed attempt with no document change is a true no-op.
            same_failed_outcome = (
                previous is not None
                and not document_due
                and computed_due
                and computed_state is previous.computed_state
            )
            if same_failed_outcome:
                continue

            with transaction(conn):
                if document_due:
                    delete_page_rows(conn, page_key, document_tables)
                    for document_producer in document_producers:
                        _insert_producer_rows(
                            conn,
                            document_producer,
                            document_tables,
                            document,
                            page_key=page_key,
                        )
                if computed_due:
                    delete_page_rows(conn, page_key, computed_tables)
                    if computed is not None:
                        for computed_producer in computed_producers:
                            _insert_producer_rows(
                                conn,
                                computed_producer,
                                computed_tables,
                                computed,
                                page_key=page_key,
                            )
                write_page_state(
                    conn,
                    PageState(
                        page_key=page_key,
                        path=page.path,
                        document_fingerprint=page.document_fingerprint,
                        render_fingerprint=render_state,
                        computed_state=computed_state,
                    ),
                )
            states[page_key] = PageState(
                page_key=page_key,
                path=page.path,
                document_fingerprint=page.document_fingerprint,
                render_fingerprint=render_state,
                computed_state=computed_state,
            )
            if previous is None:
                added.append(page.path)
            else:
                updated.append(page.path)
        except Exception as error:
            page_errors.append((page.path, f"{type(error).__name__}: {error}"))

    removed_states = sorted(
        (state for key, state in bookkeeping.pages.items() if key not in scanned_keys),
        key=lambda state: state.path,
    )
    removed: list[str] = []
    for state in removed_states:
        with transaction(conn):
            delete_page_rows(conn, state.page_key, tables)
            delete_page_state(conn, state.page_key)
        states.pop(state.page_key, None)
        removed.append(state.path)

    without_computed = tuple(
        sorted(
            (
                (state.path, state.computed_state)
                for state in states.values()
                if state.computed_state is not ComputedState.COMPUTED
            ),
            key=lambda item: item[0],
        )
    )
    return RefreshResult(
        added=tuple(added),
        updated=tuple(updated),
        removed=tuple(removed),
        without_computed=without_computed,
        page_errors=tuple(page_errors),
        producer_errors=(),
        left_out=scan.left_out,
        corpus_refreshed=(),
        pages_held=len(states),
    )
