"""Page-tier refresh and removal tests for task 6.1."""

from __future__ import annotations

import hashlib
import inspect
import shutil
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, cast, get_type_hints

import pytest

from fitdocs import Modality, contract, version
from fitdocs.docio import read_document, read_frontmatter
from fitdocs.index import corpus, derive, refresh, registry
from fitdocs.index.bookkeeping import Bookkeeping, ComputedState, IndexMeta, PageState
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.corpus import LeftOutPage, scan_workout_pages
from fitdocs.index.derive import Derived, base_archive, derive_page
from fitdocs.index.fingerprint import (
    athlete_fingerprint,
    combined_corpus_fingerprint,
    document_fingerprint,
    render_fingerprint,
)
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.producer import (
    CorpusLeftOut,
    CorpusPage,
    CorpusSnapshot,
    LoadRegionReading,
    PageComputed,
    PageDocument,
    Row,
    Rows,
)
from fitdocs.index.schema import (
    SCHEMA_VERSION,
    ColumnSpec,
    ColumnType,
    ResolvedTable,
    TableScope,
    TableSpec,
)
from fitdocs.index.store import (
    IndexConnection,
    create_index,
    create_schema,
    duckdb_version,
    insert_rows,
    open_index,
    read_bookkeeping,
    transaction,
    write_meta,
)
from fitdocs.layout import archive_path
from fitdocs.load import registry as load_registry
from fitdocs.load.engine import apply_load
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.types import (
    AthleteField,
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
)
from fitdocs.metrics.types import AthleteInputs, DerivedMetrics, ZoneSpec
from fitdocs.model import Activity
from fitdocs.sync import sync
from fitdocs.version import tool_version
from tests.fixtures import builder
from tests.index.conftest import BuiltIndex, _SyntheticTiles
from tests.index.test_handoff import _page as rendered_handoff_page


class _FieldFreeCalculator:
    calculator_id = "stub-sync-field-free"
    display_name = "Sync Test Stub Field-Free Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=42.0,
                basis="stub field-free basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


@contextmanager
def _forced_field_free_calculator() -> Iterator[None]:
    saved = dict(load_registry._REGISTRY)
    load_registry._REGISTRY.clear()
    load_registry.register(_FieldFreeCalculator())
    try:
        yield
    finally:
        load_registry._REGISTRY.clear()
        load_registry._REGISTRY.update(saved)


def _refresh(
    database: Path,
    data_root: Path,
    *,
    athlete: AthleteInputs | None = None,
    handoff: HandoffCollector | None = None,
    progress: refresh.ProgressCallback | None = None,
    today: date = date(2026, 10, 6),
) -> refresh.RefreshResult:
    with open_index(database, read_only=False) as connection:
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
        return refresh.reconcile(
            connection,
            bookkeeping,
            refresh.RefreshInputs(
                data_root=data_root,
                athlete=athlete,
                handoff=handoff,
                today=today,
                progress=progress,
            ),
        )


def _query(
    database: Path, sql: str, params: tuple[object, ...] = ()
) -> list[tuple[object, ...]]:
    with open_index(database, read_only=True) as connection:
        return connection.execute(sql, params).fetchall()


@contextmanager
def _record_sql_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[str]]:
    statements: list[str] = []
    original_execute = IndexConnection.execute

    def execute(
        connection: IndexConnection,
        sql: str,
        params: Sequence[object] = (),
    ) -> Any:
        normalized = " ".join(sql.split())
        if normalized.split(" ", 1)[0].upper() in {
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
            "DELETE",
            "INSERT",
            "UPDATE",
            "COMMENT",
        }:
            statements.append(normalized)
        return original_execute(connection, sql, params)

    try:
        with monkeypatch.context() as observer:
            observer.setattr(IndexConnection, "execute", execute)
            yield statements
    finally:
        assert IndexConnection.execute is original_execute


def _index_snapshot(
    index: BuiltIndex,
) -> tuple[
    tuple[tuple[str, int, int, str], ...],
    tuple[tuple[str, tuple[str, ...], tuple[tuple[object, ...], ...]], ...],
]:
    files = tuple(
        (
            path.name,
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(index.database.parent.iterdir())
        if path.is_file()
    )
    rows = tuple(
        (
            table.name,
            tuple(column.name for column in table.columns),
            tuple(
                _query(
                    index.database,
                    f"SELECT * FROM {table.name} ORDER BY "
                    + ", ".join(column.name for column in table.columns),
                )
            ),
        )
        for table in index.tables
    )
    return files, rows


def _page_rows(index: BuiltIndex, page_key: str) -> dict[str, list[tuple[object, ...]]]:
    captured: dict[str, list[tuple[object, ...]]] = {}
    for table in index.tables:
        if table.scope not in {TableScope.DOCUMENT, TableScope.COMPUTED}:
            continue
        if not any(column.name == "page_key" for column in table.columns):
            continue
        order = ", ".join(column.name for column in table.columns)
        captured[table.name] = _query(
            index.database,
            f"SELECT * FROM {table.name} WHERE page_key = ? ORDER BY {order}",
            (page_key,),
        )
    return captured


def _empty_registered_index(
    database: Path, data_root: Path, tables: tuple[ResolvedTable, ...]
) -> BuiltIndex:
    with create_index(database) as connection:
        create_schema(connection, tables)
        write_meta(
            connection,
            IndexMeta(
                schema_version=SCHEMA_VERSION,
                fitdocs_version=tool_version(),
                duckdb_version=duckdb_version(),
                data_root=str(data_root.resolve()),
                athlete_fingerprint=athlete_fingerprint(None),
            ),
        )
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
        result = refresh.reconcile(
            connection,
            bookkeeping,
            refresh.RefreshInputs(data_root, None, None, date(2026, 10, 6), None),
        )
        assert result.pages_held == 0
        assert result.added == ()
    return BuiltIndex(data_root, database, tables)


def _document_table_specs(
    prefix: str, first: str, second: str
) -> tuple[TableSpec, ...]:
    return (
        TableSpec(
            first,
            f"Synthetic {prefix} path and source table.",
            (
                ColumnSpec("path", ColumnType.VARCHAR, "Document path."),
                ColumnSpec("source_count", ColumnType.INTEGER, "Listed source count."),
            ),
        ),
        TableSpec(
            second,
            f"Synthetic {prefix} title and base table.",
            (
                ColumnSpec("title", ColumnType.VARCHAR, "Document title."),
                ColumnSpec("base_ref", ColumnType.VARCHAR, "Base source reference."),
            ),
        ),
    )


def _computed_table_specs(
    prefix: str, first: str, second: str
) -> tuple[TableSpec, ...]:
    return (
        TableSpec(
            first,
            f"Synthetic {prefix} sport and sample table.",
            (
                ColumnSpec("sport", ColumnType.VARCHAR, "Activity sport."),
                ColumnSpec(
                    "sample_count", ColumnType.INTEGER, "Activity sample count."
                ),
            ),
        ),
        TableSpec(
            second,
            f"Synthetic {prefix} metric and athlete table.",
            (
                ColumnSpec(
                    "distance_m", ColumnType.DOUBLE, "Activity distance in metres."
                ),
                ColumnSpec(
                    "athlete_fingerprint",
                    ColumnType.VARCHAR,
                    "Athlete inputs fingerprint.",
                ),
            ),
        ),
    )


@dataclass
class _RecordingDocumentProducer:
    name: str
    tables: tuple[TableSpec, ...]
    seen: list[PageDocument]
    rows_error: Exception | None = None

    def rows(self, page: PageDocument) -> Rows:
        self.seen.append(page)
        if self.rows_error is not None:
            raise self.rows_error
        title = page.frontmatter.get("title")
        assert isinstance(title, str)
        assert page.sources
        return {
            self.tables[0].name: ((page.path, len(page.sources)),),
            self.tables[1].name: ((title, page.sources[-1]),),
        }


@dataclass
class _RecordingComputedProducer:
    name: str
    tables: tuple[TableSpec, ...]
    seen: list[PageComputed]

    def rows(self, page: PageComputed) -> Rows:
        self.seen.append(page)
        return {
            self.tables[0].name: (
                (page.activity.sport.value, len(page.activity.samples.time_s)),
            ),
            self.tables[1].name: ((page.metrics.distance_m, page.athlete_fingerprint),),
        }


def _corpus_table_specs(prefix: str, first: str, second: str) -> tuple[TableSpec, ...]:
    return (
        TableSpec(
            first,
            f"Synthetic {prefix} corpus primary table.",
            (
                ColumnSpec("label", ColumnType.VARCHAR, "Producer label."),
                ColumnSpec("score", ColumnType.DOUBLE, "Producer score."),
            ),
        ),
        TableSpec(
            second,
            f"Synthetic {prefix} corpus secondary table.",
            (
                ColumnSpec("detail", ColumnType.VARCHAR, "Producer detail."),
                ColumnSpec("count", ColumnType.INTEGER, "Producer count."),
            ),
        ),
    )


@dataclass
class _RecordingCorpusProducer:
    name: str
    tables: tuple[TableSpec, ...]
    fingerprint_value: str
    label: str
    fingerprint_snapshots: list[CorpusSnapshot]
    row_snapshots: list[CorpusSnapshot]
    fingerprint_error: Exception | None = None
    rows_error: Exception | None = None
    fingerprint_snapshot_contents: bool = False
    rows_override: Rows | None = None

    def fingerprint(self, snapshot: CorpusSnapshot) -> str:
        self.fingerprint_snapshots.append(snapshot)
        if self.fingerprint_error is not None:
            raise self.fingerprint_error
        if self.fingerprint_snapshot_contents:
            pages = tuple(
                (page.path, page.document_fingerprint) for page in snapshot.pages
            )
            left_out = tuple(
                (page.path, page.document_fingerprint) for page in snapshot.left_out
            )
            return f"{self.fingerprint_value}:{pages!r}:{left_out!r}"
        return self.fingerprint_value

    def rows(self, snapshot: CorpusSnapshot) -> Rows:
        self.row_snapshots.append(snapshot)
        if self.rows_error is not None:
            raise self.rows_error
        if self.rows_override is not None:
            return self.rows_override
        return {
            self.tables[0].name: ((self.label, 1.25),),
            self.tables[1].name: ((f"{self.label}-detail", 7),),
        }


def _add_hike_page(source_root: Path, data_root: Path, *, serial: int) -> str:
    source_root.mkdir()
    (source_root / "hike.fit").write_bytes(
        builder.small_sport_fit_bytes(serial, "hiking", timestamp_offset=serial)
    )
    before = {page.path for page in scan_workout_pages(data_root).pages}
    report = sync(
        source_root,
        data_root,
        athlete=None,
        tz=UTC,
        tiles=_SyntheticTiles(),
    )
    assert report.failures == ()
    added = {page.path for page in scan_workout_pages(data_root).pages} - before
    assert len(added) == 1
    return next(iter(added))


def _write_missing_source_pages(
    data_root: Path, source_page: Path, page_count: int
) -> tuple[str, ...]:
    source_text = source_page.read_text(encoding="utf-8")
    source_frontmatter = read_frontmatter(source_page)
    assert source_frontmatter is not None
    old_sources = contract.source_refs(source_frontmatter)
    assert old_sources
    generated_dir = data_root / "workouts"
    generated_dir.mkdir()
    paths: list[str] = []
    for page_number in range(page_count):
        rendered = source_text
        for source_number, source_ref in enumerate(old_sources):
            digest = hashlib.sha256(
                f"missing-{page_number}-{source_number}".encode()
            ).hexdigest()
            rendered = rendered.replace(source_ref, f"fit-archive/{digest}.fit")
        path = generated_dir / f"progress-{page_number:03}.md"
        path.write_text(rendered, encoding="utf-8")
        paths.append(path.relative_to(data_root).as_posix())
    return tuple(paths)


def test_refresh_public_carriers_are_frozen_and_typed() -> None:
    assert refresh.PROGRESS_EVERY == 100
    assert get_type_hints(refresh, include_extras=True)["PROGRESS_EVERY"] == Final[int]
    params_attribute = "__dataclass_params__"
    assert getattr(refresh.RefreshInputs, params_attribute).frozen is True
    assert getattr(refresh.RefreshResult, params_attribute).frozen is True
    assert tuple(field.name for field in fields(refresh.RefreshInputs)) == (
        "data_root",
        "athlete",
        "handoff",
        "today",
        "progress",
    )
    assert tuple(field.name for field in fields(refresh.RefreshResult)) == (
        "added",
        "updated",
        "removed",
        "without_computed",
        "page_errors",
        "producer_errors",
        "left_out",
        "corpus_refreshed",
        "pages_held",
    )
    assert get_type_hints(refresh.RefreshInputs) == {
        "data_root": Path,
        "athlete": AthleteInputs | None,
        "handoff": HandoffCollector | None,
        "today": date,
        "progress": Callable[[int, int], None] | None,
    }
    assert get_type_hints(refresh.RefreshResult) == {
        "added": tuple[str, ...],
        "updated": tuple[str, ...],
        "removed": tuple[str, ...],
        "without_computed": tuple[tuple[str, ComputedState], ...],
        "page_errors": tuple[tuple[str, str], ...],
        "producer_errors": tuple[tuple[str, str], ...],
        "left_out": tuple[LeftOutPage, ...],
        "corpus_refreshed": tuple[str, ...],
        "pages_held": int,
    }
    changed_property = inspect.getattr_static(refresh.RefreshResult, "changed")
    assert isinstance(changed_property, property)
    changed_getter = changed_property.fget
    assert changed_getter is not None
    assert get_type_hints(changed_getter) == {"return": bool}
    signature = inspect.signature(refresh.reconcile)
    assert tuple(signature.parameters) == ("conn", "bookkeeping", "inputs")
    assert get_type_hints(refresh.reconcile) == {
        "conn": IndexConnection,
        "bookkeeping": Bookkeeping,
        "inputs": refresh.RefreshInputs,
        "return": refresh.RefreshResult,
    }


def test_refresh_result_changed_truth_table() -> None:
    empty = refresh.RefreshResult((), (), (), (), (), (), (), (), 0)
    assert empty.changed is False
    assert replace(empty, added=("workouts/added.md",)).changed is True
    assert replace(empty, updated=("workouts/updated.md",)).changed is True
    assert replace(empty, removed=("workouts/removed.md",)).changed is True
    assert replace(empty, corpus_refreshed=("core.summary",)).changed is True


@pytest.mark.parametrize("use_handoff", (True, False))
def test_all_registered_page_producers_receive_and_write_complete_inputs(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    synced_corpus: Path,
    use_handoff: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "producer-data"
    data_root.mkdir()

    document_alpha = _RecordingDocumentProducer(
        "test.documents.alpha",
        _document_table_specs("alpha", "z_document_alpha", "a_document_alpha"),
        [],
    )
    document_beta = _RecordingDocumentProducer(
        "test.documents.beta",
        _document_table_specs("beta", "y_document_beta", "b_document_beta"),
        [],
    )
    computed_alpha = _RecordingComputedProducer(
        "test.computed.alpha",
        _computed_table_specs("alpha", "z_computed_alpha", "a_computed_alpha"),
        [],
    )
    computed_beta = _RecordingComputedProducer(
        "test.computed.beta",
        _computed_table_specs("beta", "y_computed_beta", "b_computed_beta"),
        [],
    )
    monkeypatch.setattr(
        registry,
        "DOCUMENT_PRODUCERS",
        (CORE_DOCUMENTS, document_alpha, document_beta),
    )
    monkeypatch.setattr(
        registry,
        "COMPUTED_PRODUCERS",
        (CORE_COMPUTED, computed_alpha, computed_beta),
    )
    tables = registry.registered_tables()
    document_names = {
        "pages",
        "page_sources",
        "loads",
        "quality_flags",
        "z_document_alpha",
        "a_document_alpha",
        "y_document_beta",
        "b_document_beta",
    }
    computed_names = {
        "activities",
        "records",
        "laps",
        "strength_sets",
        "zone_times",
        "channel_sources",
        "z_computed_alpha",
        "a_computed_alpha",
        "y_computed_beta",
        "b_computed_beta",
    }
    assert {table.name for table in tables if table.scope is TableScope.DOCUMENT} == (
        document_names
    )
    assert {table.name for table in tables if table.scope is TableScope.COMPUTED} == (
        computed_names
    )

    index = _empty_registered_index(
        tmp_path / "all-producers.duckdb", data_root, tables
    )
    shutil.copytree(synced_corpus, data_root, dirs_exist_ok=True)
    strength_source = tmp_path / "strength-source"
    strength_source.mkdir()
    (strength_source / "strength.fit").write_bytes(builder.strength_fit_bytes())
    strength_sync = sync(
        strength_source,
        data_root,
        athlete=None,
        tz=timezone(timedelta(hours=-5)),
        tiles=_SyntheticTiles(),
    )
    assert strength_sync.failures == ()
    athlete = AthleteInputs(
        ftp_watts=287.0,
        max_hr_bpm=192,
        hr_zones=ZoneSpec((118.0, 154.0)),
        power_zones=ZoneSpec((175.0, 245.0)),
        pace_zones=ZoneSpec((260.0, 340.0)),
    )
    hand_athlete = AthleteInputs(
        ftp_watts=319.0,
        max_hr_bpm=188,
        hr_zones=ZoneSpec((111.0, 149.0)),
        power_zones=ZoneSpec((163.0, 231.0)),
        pace_zones=ZoneSpec((250.0, 330.0)),
    )
    scanned_pages = scan_workout_pages(data_root).pages
    assert len(scanned_pages) == 3
    assert {len(page.sources) for page in scanned_pages} == {1, 2}

    expected_documents: list[PageDocument] = []
    for path in sorted((data_root / "workouts").glob("*.md")):
        read_result = read_document(path)
        if read_result is None or read_result.frontmatter is None:
            continue
        if not contract.is_workout_document(read_result.frontmatter):
            continue
        sources = contract.source_refs(read_result.frontmatter)
        assert sources
        page_key = contract.sha_of_ref(sources[-1])
        assert page_key is not None
        expected_documents.append(
            PageDocument(
                page_key=page_key,
                path=path.relative_to(data_root).as_posix(),
                text=read_result.text,
                frontmatter=read_result.frontmatter,
                sources=sources,
                load=LoadRegionReading("not_computed", None),
            )
        )
    assert len(expected_documents) == 3
    assert {document.path for document in expected_documents} == {
        path.relative_to(data_root).as_posix()
        for path in (data_root / "workouts").glob("*.md")
        if contract.is_workout_document(read_frontmatter(path))
    }
    hand_page = next(
        document for document in expected_documents if len(document.sources) == 2
    )
    derived_hand_composition = derive_page(data_root, hand_page.sources, None)
    assert isinstance(derived_hand_composition, Derived)
    assert derived_hand_composition.composition.provenance.extras
    hand_metrics = DerivedMetrics(
        avg_heart_rate_bpm=179.0,
        avg_power_w=263.5,
        distance_m=9876.5,
    )
    handoff: HandoffCollector | None = None
    rendered = None
    if use_handoff:
        rendered = rendered_handoff_page(
            hand_page.path,
            hand_page.page_key,
            len(derived_hand_composition.composition.activity.samples.time_s),
            sources=hand_page.sources,
            athlete=hand_athlete,
        )
        rendered = replace(
            rendered,
            composition=derived_hand_composition.composition,
            metrics=hand_metrics,
        )
        handoff = HandoffCollector()
        handoff.add(rendered)

    expected_computed: list[PageComputed] = []
    for document in expected_documents:
        if document.path == hand_page.path and use_handoff:
            assert rendered is not None
            expected_computed.append(
                PageComputed(
                    document=document,
                    activity=rendered.composition.activity,
                    metrics=hand_metrics,
                    provenance=rendered.composition.provenance,
                    athlete=hand_athlete,
                    athlete_fingerprint=athlete_fingerprint(hand_athlete),
                )
            )
            continue
        derived = derive_page(data_root, document.sources, athlete)
        assert isinstance(derived, Derived)
        if document.path == hand_page.path:
            assert derived.composition.provenance.extras
            expected_extra = derived.composition.provenance.extras[0]
            expected_extra_sha = contract.sha_of_ref(hand_page.sources[0])
            assert expected_extra_sha is not None
            assert expected_extra.sha256 == expected_extra_sha
            assert "form_power_w" in expected_extra.channels
        expected_computed.append(
            PageComputed(
                document=document,
                activity=derived.composition.activity,
                metrics=derived.metrics,
                provenance=derived.composition.provenance,
                athlete=athlete,
                athlete_fingerprint=athlete_fingerprint(athlete),
            )
        )

    result = _refresh(index.database, data_root, athlete=athlete, handoff=handoff)

    assert result.added == tuple(document.path for document in expected_documents)
    assert result.page_errors == ()
    assert result.without_computed == ()
    assert result.pages_held == 3
    for document_producer in (document_alpha, document_beta):
        assert document_producer.seen == expected_documents
    for computed_producer in (computed_alpha, computed_beta):
        assert computed_producer.seen == expected_computed

    expected_rows: dict[str, list[tuple[object, ...]]] = {
        table.name: [] for table in tables
    }
    for document in expected_documents:
        doc_rows = CORE_DOCUMENTS.rows(document)
        for table_name, rows in doc_rows.items():
            expected_rows[table_name].extend((document.page_key, *row) for row in rows)
        for document_producer in (document_alpha, document_beta):
            fake_rows = document_producer.rows(document)
            for table_name, rows in fake_rows.items():
                expected_rows[table_name].extend(
                    (document.page_key, *row) for row in rows
                )
    for page in expected_computed:
        computed_rows = CORE_COMPUTED.rows(page)
        for table_name, rows in computed_rows.items():
            expected_rows[table_name].extend(
                (page.document.page_key, *row) for row in rows
            )
        for computed_producer in (computed_alpha, computed_beta):
            fake_rows = computed_producer.rows(page)
            for table_name, rows in fake_rows.items():
                expected_rows[table_name].extend(
                    (page.document.page_key, *row) for row in rows
                )

    order_columns = {
        "page_sources": ("position",),
        "loads": ("channel", "selected"),
        "quality_flags": ("flag",),
        "records": ("sample_index",),
        "laps": ("lap_index",),
        "strength_sets": ("set_index",),
        "zone_times": ("channel", "zone"),
        "channel_sources": ("channel", "source_sha256", "role"),
    }
    for table in tables:
        if table.scope is TableScope.BOOKKEEPING:
            continue
        names = order_columns.get(table.name, ())
        if names:
            sql_order = ", ".join(("page_key", *names))
            indexes = tuple(
                table_column_index
                for table_column_index in (
                    tuple(column.name for column in table.columns).index(name)
                    for name in names
                )
            )
            expected = sorted(
                expected_rows[table.name],
                key=lambda row: (row[0], *(row[index] for index in indexes)),
            )
        else:
            sql_order = "page_key"
            expected = sorted(expected_rows[table.name], key=lambda row: str(row[0]))
        actual = _query(
            index.database, f"SELECT * FROM {table.name} ORDER BY {sql_order}"
        )
        assert actual == expected, table.name
    assert expected_rows["laps"]
    assert expected_rows["strength_sets"]
    assert expected_rows["zone_times"]
    if use_handoff:
        assert any(page.athlete == hand_athlete for page in expected_computed)
    else:
        assert all(page.athlete == athlete for page in expected_computed)
    assert any(page.athlete == athlete for page in expected_computed)


def test_corpus_producers_replace_tables_only_when_fingerprint_changes(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "corpus-data"
    data_root.mkdir()
    alpha = _RecordingCorpusProducer(
        "test.corpus.alpha",
        _corpus_table_specs("alpha", "z_corpus_alpha", "a_corpus_alpha"),
        "alpha-input-v0",
        "alpha-v0",
        [],
        [],
    )
    beta = _RecordingCorpusProducer(
        "test.corpus.beta",
        _corpus_table_specs("beta", "y_corpus_beta", "b_corpus_beta"),
        "beta-input-v0",
        "beta-v0",
        [],
        [],
    )
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (alpha, beta))
    tables = registry.registered_tables()
    assert core_registry
    assert tuple(
        table.name for table in tables if table.scope is TableScope.CORPUS
    ) == (
        "z_corpus_alpha",
        "a_corpus_alpha",
        "y_corpus_beta",
        "b_corpus_beta",
    )

    index = _empty_registered_index(tmp_path / "corpus-index.duckdb", data_root, tables)
    expected_rows = {
        "z_corpus_alpha": [("alpha-v0", 1.25)],
        "a_corpus_alpha": [("alpha-v0-detail", 7)],
        "y_corpus_beta": [("beta-v0", 1.25)],
        "b_corpus_beta": [("beta-v0-detail", 7)],
    }
    assert {
        table: _query(index.database, f"SELECT * FROM {table}")
        for table in expected_rows
    } == expected_rows
    assert len(alpha.row_snapshots) == 1
    assert len(beta.row_snapshots) == 1

    with open_index(index.database, read_only=True) as connection:
        initial_bookkeeping = read_bookkeeping(connection)
    assert initial_bookkeeping is not None
    initial_snapshot = corpus.corpus_snapshot(
        data_root,
        corpus.scan_workout_pages(data_root),
        today=date(2026, 10, 6),
        athlete_fingerprint=athlete_fingerprint(None),
        held=frozenset(initial_bookkeeping.pages),
    )
    assert alpha.row_snapshots[-1] == initial_snapshot
    assert beta.row_snapshots[-1] == initial_snapshot
    assert initial_bookkeeping.producers[alpha.name] == combined_corpus_fingerprint(
        alpha, initial_snapshot
    )
    assert initial_bookkeeping.producers[beta.name] == combined_corpus_fingerprint(
        beta, initial_snapshot
    )

    before_noop = _index_snapshot(index)
    with _record_sql_writes(monkeypatch) as writes:
        noop = _refresh(index.database, data_root)
    assert noop.corpus_refreshed == ()
    assert len(alpha.row_snapshots) == 1
    assert len(beta.row_snapshots) == 1
    assert writes == []
    assert _index_snapshot(index) == before_noop

    alpha.fingerprint_value = "alpha-input-v1"
    alpha.label = "alpha-v1"
    with _record_sql_writes(monkeypatch) as writes:
        updated = _refresh(index.database, data_root)

    assert updated.corpus_refreshed == ("test.corpus.alpha",)
    assert writes[0] == "BEGIN"
    assert writes[-1] == "COMMIT"
    assert sum(statement == "BEGIN" for statement in writes) == 1
    assert tuple(
        next(
            name
            for name in ("z_corpus_alpha", "a_corpus_alpha", "index_producers")
            if name in statement
        )
        for statement in writes[1:-1]
    ) == (
        "z_corpus_alpha",
        "z_corpus_alpha",
        "a_corpus_alpha",
        "a_corpus_alpha",
        "index_producers",
        "index_producers",
    )
    assert len(alpha.row_snapshots) == 2
    assert len(beta.row_snapshots) == 1
    assert _query(index.database, "SELECT * FROM z_corpus_alpha") == [
        ("alpha-v1", 1.25)
    ]
    assert _query(index.database, "SELECT * FROM a_corpus_alpha") == [
        ("alpha-v1-detail", 7)
    ]
    assert _query(index.database, "SELECT * FROM y_corpus_beta") == [("beta-v0", 1.25)]
    assert _query(index.database, "SELECT * FROM b_corpus_beta") == [
        ("beta-v0-detail", 7)
    ]
    with open_index(index.database, read_only=True) as connection:
        updated_bookkeeping = read_bookkeeping(connection)
    assert updated_bookkeeping is not None
    assert updated_bookkeeping.producers[alpha.name] == combined_corpus_fingerprint(
        alpha, alpha.fingerprint_snapshots[-1]
    )
    assert (
        updated_bookkeeping.producers[beta.name]
        == initial_bookkeeping.producers[beta.name]
    )
    assert _query(
        index.database,
        "SELECT producer, kind, tables, fingerprint FROM index_producers "
        "ORDER BY producer",
    ) == [
        (
            alpha.name,
            "corpus",
            ["z_corpus_alpha", "a_corpus_alpha"],
            updated_bookkeeping.producers[alpha.name],
        ),
        (
            beta.name,
            "corpus",
            ["y_corpus_beta", "b_corpus_beta"],
            initial_bookkeeping.producers[beta.name],
        ),
    ]


def test_corpus_snapshot_uses_pages_held_after_addition_and_removal(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    synced_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "snapshot-data"
    data_root.mkdir()
    producer = _RecordingCorpusProducer(
        "test.corpus.snapshot",
        _corpus_table_specs("snapshot", "z_snapshot", "a_snapshot"),
        "snapshot-v0",
        "snapshot-v0",
        [],
        [],
    )
    producer.fingerprint_snapshot_contents = True
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (producer,))
    tables = registry.registered_tables()
    assert core_registry
    index = _empty_registered_index(tmp_path / "snapshot.duckdb", data_root, tables)
    shutil.copytree(synced_corpus, data_root, dirs_exist_ok=True)
    initial = _refresh(index.database, data_root)
    assert initial.added == tuple(
        sorted(page.path for page in scan_workout_pages(data_root).pages)
    )

    before = scan_workout_pages(data_root)
    held_path = before.pages[0].path
    (data_root / held_path).unlink()
    new_path = _add_hike_page(tmp_path / "new-hike-source", data_root, serial=88001)
    producer.fingerprint_value = "snapshot-v1"
    caller_today = date(2038, 3, 14)
    athlete = AthleteInputs(
        max_hr_bpm=188,
        resting_hr_bpm=47,
        ftp_watts=276.0,
    )
    expected_athlete_fingerprint = athlete_fingerprint(athlete)
    original_scan = corpus.scan_workout_pages
    original_snapshot_builder = corpus.corpus_snapshot
    scan_calls: list[tuple[Path, corpus.CorpusScan]] = []
    snapshot_calls: list[tuple[Path, corpus.CorpusScan, date, str, frozenset[str]]] = []

    def observe_scan(root: Path) -> corpus.CorpusScan:
        scanned = original_scan(root)
        scan_calls.append((root, scanned))
        return scanned

    def observe_snapshot(
        root: Path,
        scanned: corpus.CorpusScan,
        *,
        today: date,
        athlete_fingerprint: str,
        held: frozenset[str],
    ) -> CorpusSnapshot:
        snapshot_calls.append((root, scanned, today, athlete_fingerprint, held))
        return original_snapshot_builder(
            root,
            scanned,
            today=today,
            athlete_fingerprint=athlete_fingerprint,
            held=held,
        )

    with monkeypatch.context() as observer:
        observer.setattr(corpus, "scan_workout_pages", observe_scan)
        observer.setattr(corpus, "corpus_snapshot", observe_snapshot)
        result = _refresh(
            index.database,
            data_root,
            athlete=athlete,
            today=caller_today,
        )
    assert corpus.scan_workout_pages is original_scan
    assert corpus.corpus_snapshot is original_snapshot_builder

    assert result.removed == (held_path,)
    assert result.added == (new_path,)
    assert len(producer.row_snapshots) == 3
    snapshot = producer.row_snapshots[-1]
    assert len(scan_calls) == 1
    assert scan_calls[0][0] == data_root
    assert len(snapshot_calls) == 1
    assert snapshot_calls[0][0] == data_root
    assert snapshot_calls[0][1] is scan_calls[0][1]
    assert snapshot_calls[0][2:] == (
        caller_today,
        expected_athlete_fingerprint,
        frozenset(read_bookkeeping_for(index).pages),
    )
    bookkeeping = read_bookkeeping_for(index)
    post_scan = original_scan(data_root)
    assert post_scan == scan_calls[0][1]
    held_after_pages = frozenset(bookkeeping.pages)
    expected_pages = tuple(
        CorpusPage(
            page.page_key,
            page.path,
            page.frontmatter,
            page.document_fingerprint,
        )
        for page in post_scan.pages
        if page.page_key in held_after_pages
    )
    expected_left_out = tuple(
        sorted(
            [
                CorpusLeftOut(page.path, page.document_fingerprint)
                for page in post_scan.left_out
            ]
            + [
                CorpusLeftOut(page.path, page.document_fingerprint)
                for page in post_scan.pages
                if page.page_key not in held_after_pages
            ],
            key=lambda page: page.path,
        )
    )
    expected_snapshot = CorpusSnapshot(
        data_root.resolve(),
        expected_pages,
        expected_left_out,
        caller_today,
        expected_athlete_fingerprint,
    )
    assert snapshot == expected_snapshot
    assert snapshot == original_snapshot_builder(
        data_root,
        post_scan,
        today=caller_today,
        athlete_fingerprint=expected_athlete_fingerprint,
        held=held_after_pages,
    )
    assert tuple(page.path for page in snapshot.pages) == tuple(
        sorted(page.path for page in expected_pages)
    )
    assert tuple(page.path for page in snapshot.left_out) == tuple(
        page.path for page in expected_left_out
    )


def test_corpus_snapshot_keeps_failed_held_page_and_reports_failed_new_page(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    synced_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "snapshot-errors-data"
    data_root.mkdir()
    document_error = _RecordingDocumentProducer(
        "test.documents.failure",
        _document_table_specs("failure", "z_failure", "a_failure"),
        [],
    )
    corpus_producer = _RecordingCorpusProducer(
        "test.corpus.errors",
        _corpus_table_specs("errors", "z_errors", "a_errors"),
        "errors-v0",
        "errors-v0",
        [],
        [],
    )
    corpus_producer.fingerprint_snapshot_contents = True
    monkeypatch.setattr(
        registry, "DOCUMENT_PRODUCERS", (CORE_DOCUMENTS, document_error)
    )
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (corpus_producer,))
    tables = registry.registered_tables()
    assert core_registry
    index = _empty_registered_index(
        tmp_path / "snapshot-errors.duckdb", data_root, tables
    )
    shutil.copytree(synced_corpus, data_root, dirs_exist_ok=True)
    initial = _refresh(index.database, data_root)
    assert initial.added == tuple(
        sorted(page.path for page in scan_workout_pages(data_root).pages)
    )

    initial_scan = scan_workout_pages(data_root)
    assert len(initial_scan.pages) == 2
    held_page = initial_scan.pages[0]
    held_path = data_root / held_page.path
    held_path.write_text(held_page.text + "\nA changed rendered body.\n")
    removed_path = initial_scan.pages[1].path
    (data_root / removed_path).unlink()
    new_path = _add_hike_page(tmp_path / "failed-new-source", data_root, serial=88002)
    document_error.rows_error = RuntimeError("deliberate page producer failure")
    corpus_producer.fingerprint_value = "errors-v1"

    failed = _refresh(index.database, data_root)
    assert failed.removed == (removed_path,)
    assert failed.page_errors == (
        (held_page.path, "RuntimeError: deliberate page producer failure"),
        (new_path, "RuntimeError: deliberate page producer failure"),
    )
    assert len(corpus_producer.row_snapshots) == 3
    failed_snapshot = corpus_producer.row_snapshots[-1]
    with open_index(index.database, read_only=True) as connection:
        failed_bookkeeping = read_bookkeeping(connection)
    assert failed_bookkeeping is not None
    assert held_page.page_key in failed_bookkeeping.pages
    assert failed_bookkeeping.pages[held_page.page_key].document_fingerprint == (
        held_page.document_fingerprint
    )
    snapshot_held = next(
        page for page in failed_snapshot.pages if page.path == held_page.path
    )
    current_held_scan = next(
        page
        for page in scan_workout_pages(data_root).pages
        if page.path == held_page.path
    )
    assert snapshot_held.document_fingerprint == current_held_scan.document_fingerprint
    assert (
        snapshot_held.document_fingerprint
        != failed_bookkeeping.pages[held_page.page_key].document_fingerprint
    )
    assert new_path not in {state.path for state in failed_bookkeeping.pages.values()}
    assert failed_snapshot == corpus.corpus_snapshot(
        data_root,
        scan_workout_pages(data_root),
        today=date(2026, 10, 6),
        athlete_fingerprint=athlete_fingerprint(None),
        held=frozenset(failed_bookkeeping.pages),
    )
    assert tuple(page.path for page in failed_snapshot.pages) == (held_page.path,)
    assert tuple(page.path for page in failed_snapshot.left_out) == (new_path,)

    document_error.rows_error = None
    corpus_producer.fingerprint_value = "errors-v2"
    recovered = _refresh(index.database, data_root)
    assert recovered.page_errors == ()
    assert new_path in {
        state.path for state in read_bookkeeping_for(index).pages.values()
    }
    assert tuple(
        page.path for page in corpus_producer.row_snapshots[-1].pages
    ) == tuple(sorted(page.path for page in scan_workout_pages(data_root).pages))
    assert corpus_producer.row_snapshots[-1].left_out == ()


def read_bookkeeping_for(index: BuiltIndex) -> Bookkeeping:
    with open_index(index.database, read_only=True) as connection:
        bookkeeping = read_bookkeeping(connection)
    assert bookkeeping is not None
    return bookkeeping


def test_refresh_updates_only_meta_for_athlete_input_change(
    built_index: BuiltIndex,
    synced_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert first.added
    before = _index_snapshot(index)
    athlete = AthleteInputs(
        max_hr_bpm=194,
        resting_hr_bpm=49,
        ftp_watts=291.0,
    )
    previous_activity_rows = _query(
        index.database,
        "SELECT page_key, athlete_fingerprint FROM activities ORDER BY page_key",
    )
    previous_meta = read_bookkeeping_for(index).meta
    current_athlete_fingerprint = athlete_fingerprint(athlete)
    current_fitdocs_version = version.tool_version()
    current_duckdb_version = duckdb_version()
    assert previous_meta.schema_version == SCHEMA_VERSION
    assert previous_meta.fitdocs_version == current_fitdocs_version
    assert previous_meta.duckdb_version == current_duckdb_version
    assert previous_meta.data_root == str(index.data_root.resolve())
    assert previous_meta.athlete_fingerprint != current_athlete_fingerprint
    assert previous_activity_rows
    assert all(
        row_fingerprint == previous_meta.athlete_fingerprint
        for _, row_fingerprint in previous_activity_rows
    )

    with _record_sql_writes(monkeypatch) as writes:
        result = _refresh(index.database, index.data_root, athlete=athlete)

    assert result.added == ()
    assert result.updated == ()
    assert result.removed == ()
    assert result.corpus_refreshed == ()
    assert result.changed is False
    after = _index_snapshot(index)
    rows_before = {row[0]: row[2] for row in before[1]}
    rows_after = {row[0]: row[2] for row in after[1]}
    assert set(rows_before) == set(rows_after)
    assert all(
        rows_before[name] == rows_after[name]
        for name in rows_before
        if name != "index_meta"
    )
    assert (
        _query(
            index.database,
            "SELECT page_key, athlete_fingerprint FROM activities ORDER BY page_key",
        )
        == previous_activity_rows
    )
    meta = read_bookkeeping_for(index).meta
    assert meta == IndexMeta(
        schema_version=SCHEMA_VERSION,
        fitdocs_version=current_fitdocs_version,
        duckdb_version=current_duckdb_version,
        data_root=str(index.data_root.resolve()),
        athlete_fingerprint=current_athlete_fingerprint,
    )
    data_statements = [
        statement
        for statement in writes
        if statement.split(" ", 1)[0].upper()
        in {"DELETE", "INSERT", "UPDATE", "COMMENT"}
    ]
    assert [tuple(statement.split(" ", 3)[:3]) for statement in data_statements] == [
        ("DELETE", "FROM", "index_meta"),
        ("INSERT", "INTO", "index_meta"),
    ]
    assert [
        statement
        for statement in writes
        if statement in {"BEGIN", "COMMIT", "ROLLBACK"}
    ] == ["BEGIN", "COMMIT"]


def test_refresh_reapplies_descriptions_when_fitdocs_version_changes(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "description-data"
    data_root.mkdir()
    producer = _RecordingCorpusProducer(
        "test.corpus.descriptions",
        _corpus_table_specs("description-old", "z_descriptions", "a_descriptions"),
        "same-inputs",
        "same-rows",
        [],
        [],
    )
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (producer,))
    tables = registry.registered_tables()
    assert core_registry
    index = _empty_registered_index(tmp_path / "descriptions.duckdb", data_root, tables)
    old_comments = _query(
        index.database,
        "SELECT column_name, comment FROM duckdb_columns() "
        "WHERE table_name = 'z_descriptions' ORDER BY column_index",
    )
    assert old_comments == [("label", "Producer label."), ("score", "Producer score.")]
    replacement_tables = _corpus_table_specs(
        "description-new", "z_descriptions", "a_descriptions"
    )
    producer.tables = (
        replace(
            replacement_tables[0],
            columns=(
                replace(
                    replacement_tables[0].columns[0],
                    description="Updated producer label.",
                ),
                replacement_tables[0].columns[1],
            ),
        ),
        replacement_tables[1],
    )
    original_tool_version = version.tool_version
    previous_meta = read_bookkeeping_for(index).meta
    assert previous_meta.fitdocs_version == original_tool_version()
    assert previous_meta.duckdb_version == duckdb_version()
    assert previous_meta.schema_version == SCHEMA_VERSION
    assert previous_meta.data_root == str(data_root.resolve())
    changed_fitdocs_version = "6.2-description-test"
    expected_tables = registry.registered_tables()
    with open_index(index.database, read_only=False) as connection:
        for table in expected_tables:
            connection.execute(f'COMMENT ON TABLE "{table.name}" IS NULL')
            for column in table.columns:
                connection.execute(
                    f'COMMENT ON COLUMN "{table.name}"."{column.name}" IS NULL'
                )
    assert all(
        _query(
            index.database,
            "SELECT comment FROM duckdb_tables() WHERE table_name = ?",
            (table.name,),
        )
        == [(None,)]
        for table in expected_tables
    )
    assert all(
        _query(
            index.database,
            "SELECT column_name, comment FROM duckdb_columns() "
            "WHERE table_name = ? ORDER BY column_index",
            (table.name,),
        )
        == [(column.name, None) for column in table.columns]
        for table in expected_tables
    )

    with monkeypatch.context() as version_override:
        version_override.setattr(
            version, "tool_version", lambda: changed_fitdocs_version
        )
        result = _refresh(index.database, data_root)
    assert version.tool_version is original_tool_version

    assert result.corpus_refreshed == (producer.name,)
    assert read_bookkeeping_for(index).meta == IndexMeta(
        schema_version=previous_meta.schema_version,
        fitdocs_version=changed_fitdocs_version,
        duckdb_version=previous_meta.duckdb_version,
        data_root=previous_meta.data_root,
        athlete_fingerprint=previous_meta.athlete_fingerprint,
    )
    for table in expected_tables:
        assert _query(
            index.database,
            "SELECT comment FROM duckdb_tables() WHERE table_name = ?",
            (table.name,),
        ) == [(table.description,)]
        assert _query(
            index.database,
            "SELECT column_name, comment FROM duckdb_columns() "
            "WHERE table_name = ? ORDER BY column_index",
            (table.name,),
        ) == [(column.name, column.description) for column in table.columns]


def test_refresh_updates_full_meta_on_duckdb_only_version_change(
    built_index: BuiltIndex,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    previous_meta = read_bookkeeping_for(index).meta
    duckdb_version_attr = "duckdb_version"
    original_duckdb_version = cast(
        Callable[[], str], getattr(refresh, duckdb_version_attr)
    )
    changed_duckdb_version = "synthetic-duckdb-version-change"
    current_fitdocs_version = version.tool_version()
    assert previous_meta.schema_version == SCHEMA_VERSION
    assert previous_meta.fitdocs_version == current_fitdocs_version
    assert previous_meta.duckdb_version == original_duckdb_version()
    assert previous_meta.duckdb_version != changed_duckdb_version
    assert previous_meta.data_root == str(index.data_root.resolve())

    table_comment = "local table comment survives driver-only update"
    column_comment = "local column comment survives driver-only update"
    with open_index(index.database, read_only=False) as connection:
        connection.execute(f"COMMENT ON TABLE \"activities\" IS '{table_comment}'")
        connection.execute(
            f'COMMENT ON COLUMN "activities"."page_key" IS \'{column_comment}\''
        )
    assert _query(
        index.database,
        "SELECT comment FROM duckdb_tables() WHERE table_name = 'activities'",
    ) == [(table_comment,)]
    assert _query(
        index.database,
        "SELECT comment FROM duckdb_columns() "
        "WHERE table_name = 'activities' AND column_name = 'page_key'",
    ) == [(column_comment,)]
    before_rows = {row[0]: row[2] for row in _index_snapshot(index)[1]}

    with monkeypatch.context() as version_override:
        version_override.setattr(
            refresh, "duckdb_version", lambda: changed_duckdb_version
        )
        with _record_sql_writes(monkeypatch) as writes:
            result = _refresh(index.database, index.data_root)
    assert getattr(refresh, duckdb_version_attr) is original_duckdb_version

    assert result.corpus_refreshed == ()
    assert read_bookkeeping_for(index).meta == IndexMeta(
        schema_version=SCHEMA_VERSION,
        fitdocs_version=current_fitdocs_version,
        duckdb_version=changed_duckdb_version,
        data_root=str(index.data_root.resolve()),
        athlete_fingerprint=athlete_fingerprint(None),
    )
    after_rows = {row[0]: row[2] for row in _index_snapshot(index)[1]}
    assert {
        name: rows for name, rows in before_rows.items() if name != "index_meta"
    } == {name: rows for name, rows in after_rows.items() if name != "index_meta"}
    assert _query(
        index.database,
        "SELECT comment FROM duckdb_tables() WHERE table_name = 'activities'",
    ) == [(table_comment,)]
    assert _query(
        index.database,
        "SELECT comment FROM duckdb_columns() "
        "WHERE table_name = 'activities' AND column_name = 'page_key'",
    ) == [(column_comment,)]
    data_statements = [
        statement
        for statement in writes
        if statement.split(" ", 1)[0].upper()
        in {"DELETE", "INSERT", "UPDATE", "COMMENT"}
    ]
    assert [tuple(statement.split(" ", 3)[:3]) for statement in data_statements] == [
        ("DELETE", "FROM", "index_meta"),
        ("INSERT", "INTO", "index_meta"),
    ]
    assert [
        statement
        for statement in writes
        if statement in {"BEGIN", "COMMIT", "ROLLBACK"}
    ] == ["BEGIN", "COMMIT"]


@pytest.mark.parametrize(
    ("page_count", "fail_first", "expected_calls"),
    (
        (100, False, ()),
        (101, False, ((100, 101), (101, 101))),
        (101, True, ((100, 101), (101, 101))),
        (201, False, ((100, 201), (200, 201), (201, 201))),
    ),
)
def test_refresh_progress_counts_only_large_computed_attempt_batches(
    built_index: BuiltIndex,
    synced_workout_pages: tuple[Path, ...],
    page_count: int,
    fail_first: bool,
    expected_calls: tuple[tuple[int, int], ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    expected_paths = _write_missing_source_pages(
        index.data_root, synced_workout_pages[0], page_count
    )
    actual_missing = scan_workout_pages(index.data_root)
    assert len(actual_missing.pages) == page_count
    assert all(
        derive.base_archive(index.data_root, page.sources) is None
        for page in actual_missing.pages
    )
    if fail_first:
        original_compute = refresh._page_computed
        failed_path = expected_paths[0]

        def fail_first_page(
            document: PageDocument,
            inputs: refresh.RefreshInputs,
            page: corpus.ScannedPage,
        ) -> tuple[PageComputed | None, ComputedState]:
            if page.path == failed_path:
                raise RuntimeError("synthetic computed attempt failure")
            return original_compute(document, inputs, page)

        monkeypatch.setattr(refresh, "_page_computed", fail_first_page)
    calls: list[tuple[int, int]] = []

    result = _refresh(
        index.database,
        index.data_root,
        progress=lambda done, total: calls.append((done, total)),
    )

    assert calls == list(expected_calls)
    assert result.pages_held == page_count - int(fail_first)
    assert result.page_errors == (
        ((expected_paths[0], "RuntimeError: synthetic computed attempt failure"),)
        if fail_first
        else ()
    )
    assert result.without_computed == tuple(
        (page.path, ComputedState.SOURCE_MISSING)
        for page in actual_missing.pages
        if not fail_first or page.path != expected_paths[0]
    )


def test_refresh_progress_excludes_document_only_changes(
    built_index: BuiltIndex,
    synced_workout_pages: tuple[Path, ...],
) -> None:
    index = built_index
    paths = _write_missing_source_pages(index.data_root, synced_workout_pages[0], 101)
    first = _refresh(index.database, index.data_root)
    assert first.pages_held == 101
    assert first.without_computed == tuple(
        (path, ComputedState.SOURCE_MISSING) for path in paths
    )
    note_placeholder = (
        "_Your notes go here. This section is preserved when "
        "the document is regenerated._"
    )
    before_bookkeeping = read_bookkeeping_for(index)
    for path in paths:
        page_path = index.data_root / path
        page_text = page_path.read_text(encoding="utf-8")
        assert note_placeholder in page_text
        page_path.write_text(
            page_text.replace(note_placeholder, f"Changed note for {path}.", 1),
            encoding="utf-8",
        )
    changed_scan = scan_workout_pages(index.data_root)
    assert len(changed_scan.pages) == 101
    for page in changed_scan.pages:
        previous = before_bookkeeping.pages[page.page_key]
        assert previous.document_fingerprint != page.document_fingerprint
        assert previous.render_fingerprint == render_fingerprint(
            page.text, page.frontmatter
        )
    calls: list[tuple[int, int]] = []

    result = _refresh(
        index.database,
        index.data_root,
        progress=lambda done, total: calls.append((done, total)),
    )

    assert calls == []
    assert result.updated == paths
    assert result.without_computed == tuple(
        (path, ComputedState.SOURCE_MISSING) for path in paths
    )


def test_corpus_row_failure_rolls_back_only_its_producer_and_retries(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "row-failure-data"
    data_root.mkdir()
    alpha = _RecordingCorpusProducer(
        "test.corpus.alpha",
        _corpus_table_specs("alpha", "z_row_alpha", "a_row_alpha"),
        "alpha-v0",
        "alpha-v0",
        [],
        [],
    )
    beta = _RecordingCorpusProducer(
        "test.corpus.beta",
        _corpus_table_specs("beta", "z_row_beta", "a_row_beta"),
        "beta-v0",
        "beta-v0",
        [],
        [],
    )
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (alpha, beta))
    tables = registry.registered_tables()
    assert core_registry
    index = _empty_registered_index(tmp_path / "row-failure.duckdb", data_root, tables)

    before_alpha = {
        name: _query(index.database, f"SELECT * FROM {name}")
        for name in ("z_row_alpha", "a_row_alpha")
    }
    before_beta = {
        name: _query(index.database, f"SELECT * FROM {name}")
        for name in ("z_row_beta", "a_row_beta")
    }
    before_bookkeeping = read_bookkeeping_for(index)
    alpha.fingerprint_value = "alpha-v1"
    alpha.label = "alpha-v1"
    alpha.rows_error = ValueError("synthetic corpus row failure")
    beta.fingerprint_value = "beta-v1"
    beta.label = "beta-v1"
    assert before_bookkeeping.producers[alpha.name] != combined_corpus_fingerprint(
        alpha, alpha.fingerprint_snapshots[-1]
    )
    assert before_bookkeeping.producers[beta.name] != combined_corpus_fingerprint(
        beta, beta.fingerprint_snapshots[-1]
    )
    with _record_sql_writes(monkeypatch) as writes:
        failed = _refresh(index.database, data_root)
    assert failed.corpus_refreshed == (beta.name,)
    assert failed.producer_errors == (
        (alpha.name, "ValueError: synthetic corpus row failure"),
    )
    assert {
        name: _query(index.database, f"SELECT * FROM {name}") for name in before_alpha
    } == before_alpha
    assert {
        name: _query(index.database, f"SELECT * FROM {name}") for name in before_beta
    } == {
        "z_row_beta": [("beta-v1", 1.25)],
        "a_row_beta": [("beta-v1-detail", 7)],
    }
    after_failure = read_bookkeeping_for(index)
    assert (
        after_failure.producers[alpha.name] == before_bookkeeping.producers[alpha.name]
    )
    assert after_failure.producers[beta.name] != before_bookkeeping.producers[beta.name]
    failed_transaction_statements = [
        statement
        for statement in writes
        if statement in {"BEGIN", "COMMIT", "ROLLBACK"}
    ]
    assert any("z_row_beta" in statement for statement in writes)
    assert any("a_row_beta" in statement for statement in writes)
    assert not any(
        "z_row_alpha" in statement or "a_row_alpha" in statement for statement in writes
    )

    alpha.rows_error = None
    alpha.rows_override = {
        "z_row_alpha": (("alpha-v1", 1.25),),
        "a_row_alpha": (("alpha-v1-detail", "wrong integer type"),),
    }
    with _record_sql_writes(monkeypatch) as writes:
        bad_shape = _refresh(index.database, data_root)
    assert bad_shape.corpus_refreshed == ()
    assert bad_shape.producer_errors[0][0] == alpha.name
    assert bad_shape.producer_errors[0][1].startswith("RowShapeError:")
    bad_shape_transaction_statements = [
        statement
        for statement in writes
        if statement in {"BEGIN", "COMMIT", "ROLLBACK"}
    ]
    assert (
        _query(index.database, "SELECT * FROM z_row_alpha")
        == before_alpha["z_row_alpha"]
    )
    assert (
        _query(index.database, "SELECT * FROM a_row_alpha")
        == before_alpha["a_row_alpha"]
    )
    assert (
        read_bookkeeping_for(index).producers[alpha.name]
        == before_bookkeeping.producers[alpha.name]
    )
    assert bad_shape_transaction_statements == [
        "BEGIN",
        "ROLLBACK",
    ]
    assert failed_transaction_statements == [
        "BEGIN",
        "ROLLBACK",
        "BEGIN",
        "COMMIT",
    ]

    alpha.rows_override = None
    with _record_sql_writes(monkeypatch) as writes:
        retried = _refresh(index.database, data_root)
    assert retried.corpus_refreshed == (alpha.name,)
    assert _query(index.database, "SELECT * FROM z_row_alpha") == [("alpha-v1", 1.25)]
    assert _query(index.database, "SELECT * FROM a_row_alpha") == [
        ("alpha-v1-detail", 7)
    ]


def test_corpus_fingerprint_failure_skips_its_transaction_and_keeps_meta_current(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "fingerprint-failure-data"
    data_root.mkdir()
    alpha = _RecordingCorpusProducer(
        "test.corpus.alpha",
        _corpus_table_specs("alpha", "z_fp_alpha", "a_fp_alpha"),
        "alpha-v0",
        "alpha-v0",
        [],
        [],
    )
    beta = _RecordingCorpusProducer(
        "test.corpus.beta",
        _corpus_table_specs("beta", "z_fp_beta", "a_fp_beta"),
        "beta-v0",
        "beta-v0",
        [],
        [],
    )
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (alpha, beta))
    tables = registry.registered_tables()
    assert core_registry
    index = _empty_registered_index(
        tmp_path / "fingerprint-failure.duckdb", data_root, tables
    )
    before = _index_snapshot(index)
    before_bookkeeping = read_bookkeeping_for(index)
    alpha.fingerprint_value = "alpha-v1"
    alpha.label = "alpha-v1"
    alpha.fingerprint_error = LookupError("synthetic fingerprint failure")
    beta.fingerprint_value = "beta-v1"
    beta.label = "beta-v1"
    athlete = AthleteInputs(
        max_hr_bpm=191,
        resting_hr_bpm=51,
        ftp_watts=283.0,
    )
    changed_snapshot = corpus.corpus_snapshot(
        data_root,
        scan_workout_pages(data_root),
        today=date(2026, 10, 6),
        athlete_fingerprint=athlete_fingerprint(athlete),
        held=frozenset(),
    )
    assert before_bookkeeping.producers[beta.name] != combined_corpus_fingerprint(
        beta, changed_snapshot
    )

    with _record_sql_writes(monkeypatch) as writes:
        failed = _refresh(index.database, data_root, athlete=athlete)
    assert failed.corpus_refreshed == (beta.name,)
    assert failed.producer_errors == (
        (alpha.name, "LookupError: synthetic fingerprint failure"),
    )
    assert len(alpha.row_snapshots) == 1
    assert _query(index.database, "SELECT * FROM z_fp_alpha") == [("alpha-v0", 1.25)]
    assert _query(index.database, "SELECT * FROM a_fp_alpha") == [
        ("alpha-v0-detail", 7)
    ]
    assert _query(index.database, "SELECT * FROM z_fp_beta") == [("beta-v1", 1.25)]
    after = read_bookkeeping_for(index)
    assert after.producers[alpha.name] == before_bookkeeping.producers[alpha.name]
    assert after.producers[beta.name] != before_bookkeeping.producers[beta.name]
    assert after.meta.athlete_fingerprint == athlete_fingerprint(athlete)
    assert after.meta.athlete_fingerprint != before_bookkeeping.meta.athlete_fingerprint
    assert [
        statement
        for statement in writes
        if statement in {"BEGIN", "COMMIT", "ROLLBACK"}
    ] == ["BEGIN", "COMMIT", "BEGIN", "COMMIT"]
    rows_after = {row[0]: row[2] for row in _index_snapshot(index)[1]}
    rows_before = {row[0]: row[2] for row in before[1]}
    for table in ("activities", "pages", "page_sources", "loads", "quality_flags"):
        assert rows_after[table] == rows_before[table]

    alpha.fingerprint_error = None
    retried = _refresh(index.database, data_root, athlete=athlete)
    assert retried.corpus_refreshed == (alpha.name,)
    assert _query(index.database, "SELECT * FROM z_fp_alpha") == [("alpha-v1", 1.25)]


def test_empty_index_refresh_adds_both_tiers_for_synthetic_pages(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
) -> None:
    index = built_index
    database = index.database
    data_root = index.data_root
    expected_paths = tuple(
        sorted(
            path.relative_to(synced_corpus).as_posix() for path in synced_workout_pages
        )
    )
    assert len(expected_paths) == 2
    assert _query(database, "SELECT COUNT(*) FROM index_pages") == [(0,)]

    shutil.copytree(synced_corpus, data_root, dirs_exist_ok=True)
    result = _refresh(database, data_root)

    assert result.added == expected_paths
    assert result.updated == ()
    assert result.removed == ()
    assert result.page_errors == ()
    assert result.producer_errors == ()
    assert result.left_out == ()
    assert result.corpus_refreshed == ()
    assert result.pages_held == 2
    assert result.changed is True
    assert _query(database, "SELECT COUNT(*) FROM pages") == [(2,)]
    assert _query(database, "SELECT COUNT(*) FROM activities") == [(2,)]
    assert cast(int, _query(database, "SELECT COUNT(*) FROM records")[0][0]) > 0
    assert _query(database, "SELECT COUNT(*) FROM index_pages") == [(2,)]


def test_refresh_result_retains_duplicate_base_left_out_page(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    original = synced_workout_pages[0]
    duplicate_relative = Path("workouts/z-duplicate.md")
    duplicate = index.data_root / duplicate_relative
    duplicate.write_bytes(original.read_bytes())
    expected_path = duplicate_relative.as_posix()
    duplicate_document = read_document(duplicate)
    assert duplicate_document is not None
    expected_left_out = LeftOutPage(
        path=expected_path,
        reason="duplicate_base",
        collides_with=original.relative_to(synced_corpus).as_posix(),
        document_fingerprint=document_fingerprint(
            expected_path, duplicate_document.data
        ),
    )

    result = _refresh(index.database, index.data_root)

    assert result.left_out == (expected_left_out,)
    assert result.pages_held == 2
    assert len(result.added) == 2


def test_render_change_retries_computed_state_when_base_is_still_missing(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
) -> None:
    index = built_index
    database = index.database
    data_root = index.data_root
    shutil.copytree(synced_corpus / "workouts", data_root / "workouts")
    first = _refresh(database, data_root)
    assert len(first.added) == 2
    page_path = synced_workout_pages[0].relative_to(synced_corpus)
    assert first.without_computed == tuple(
        sorted(
            (
                path.relative_to(synced_corpus).as_posix(),
                ComputedState.SOURCE_MISSING,
            )
            for path in synced_workout_pages
        )
    )

    copied_page = data_root / page_path
    page_text = copied_page.read_text(encoding="utf-8")
    frontmatter = read_frontmatter(copied_page)
    assert frontmatter is not None
    sources = contract.source_refs(frontmatter)
    assert sources
    assert base_archive(data_root, sources) is None
    changed_text = page_text + "\nA body change while the source is missing.\n"
    copied_page.write_text(changed_text, encoding="utf-8")
    changed_scan = scan_workout_pages(data_root)
    changed_page = next(
        item for item in changed_scan.pages if item.path == page_path.as_posix()
    )
    expected_render_fingerprint = render_fingerprint(
        changed_page.text, changed_page.frontmatter
    )
    result = _refresh(database, data_root)

    assert result.updated == (page_path.as_posix(),)
    assert result.without_computed == first.without_computed
    assert _query(
        database,
        "SELECT render_fingerprint FROM index_pages WHERE path = ?",
        (page_path.as_posix(),),
    ) == [(expected_render_fingerprint,)]


def test_effort_edit_updates_document_tier_without_deriving(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    relative_path = synced_workout_pages[0].relative_to(synced_corpus)
    page = index.data_root / relative_path
    original = page.read_text(encoding="utf-8")
    frontmatter_end = "\n---\n"
    assert original.count(frontmatter_end) >= 1
    edited = original.replace(frontmatter_end, "\neffort: race" + frontmatter_end, 1)
    assert edited != original
    page.write_text(edited, encoding="utf-8")

    def unexpected_derive(*args: object, **kwargs: object) -> object:
        raise AssertionError("effort-only changes do not derive computed values")

    monkeypatch.setattr(derive, "derive_page", unexpected_derive)
    result = _refresh(index.database, index.data_root)

    assert result.updated == (relative_path.as_posix(),)
    assert result.page_errors == ()
    assert _query(
        index.database,
        "SELECT effort FROM pages WHERE path = ?",
        (relative_path.as_posix(),),
    ) == [("race",)]


def test_rename_updates_document_path_without_deriving(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    old_relative = synced_workout_pages[0].relative_to(synced_corpus)
    new_relative = old_relative.with_name("renamed-workout.md")
    old_page = index.data_root / old_relative
    new_page = index.data_root / new_relative
    assert old_page.is_file()
    old_page.rename(new_page)

    def unexpected_derive(*args: object, **kwargs: object) -> object:
        raise AssertionError("a path-only rename does not derive computed values")

    monkeypatch.setattr(derive, "derive_page", unexpected_derive)
    result = _refresh(index.database, index.data_root)

    assert result.updated == (new_relative.as_posix(),)
    assert result.removed == ()
    assert result.page_errors == ()
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM pages WHERE path = ?",
        (new_relative.as_posix(),),
    ) == [(1,)]
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM pages WHERE path = ?",
        (old_relative.as_posix(),),
    ) == [(0,)]
    assert _query(
        index.database,
        "SELECT path FROM index_pages WHERE path = ?",
        (new_relative.as_posix(),),
    ) == [(new_relative.as_posix(),)]


def test_render_body_change_recomputes_computed_tier(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    relative_path = synced_workout_pages[0].relative_to(synced_corpus)
    page = index.data_root / relative_path
    original = page.read_text(encoding="utf-8")
    changed = original + "\nA rendered body change.\n"
    assert changed != original
    page.write_text(changed, encoding="utf-8")

    derive_page = derive.derive_page
    calls: list[tuple[object, ...]] = []

    def observe_derive(
        data_root: Path,
        sources: tuple[str, ...],
        athlete: AthleteInputs | None,
    ) -> object:
        calls.append((data_root, sources, athlete))
        return derive_page(data_root, sources, athlete)

    monkeypatch.setattr(derive, "derive_page", observe_derive)
    result = _refresh(index.database, index.data_root)

    assert result.updated == (relative_path.as_posix(),)
    assert len(calls) == 1
    frontmatter = read_frontmatter(page)
    assert frontmatter is not None
    sources = contract.source_refs(frontmatter)
    assert sources
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM activities WHERE page_key = ?",
        (contract.sha_of_ref(sources[-1]),),
    ) == [(1,)]


def test_real_load_pass_rewrite_updates_documents_without_deriving(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2
    run_source = next(
        source_page
        for source_page in synced_workout_pages
        if "-run-" in source_page.name
    )
    page = index.data_root / run_source.relative_to(synced_corpus)
    before = page.read_bytes()
    assert b"load_value:" not in before

    with _forced_field_free_calculator():
        load_report = apply_load(
            index.data_root,
            session=NonInteractiveSession(),
            calculator_id="stub-sync-field-free",
        )
    after = page.read_bytes()
    assert load_report.failures == ()
    assert after != before

    activity_rows = _query(index.database, "SELECT * FROM activities ORDER BY page_key")

    def unexpected_derive(*args: object, **kwargs: object) -> object:
        raise AssertionError("load-region changes do not derive computed values")

    monkeypatch.setattr(derive, "derive_page", unexpected_derive)
    result = _refresh(index.database, index.data_root)

    assert result.updated == tuple(
        sorted(
            path.relative_to(synced_corpus).as_posix() for path in synced_workout_pages
        )
    )
    assert result.page_errors == ()
    assert _query(
        index.database,
        "SELECT load_status, load_value, load_methodology, load_basis "
        "FROM pages WHERE path = ?",
        (page.relative_to(index.data_root).as_posix(),),
    ) == [("computed", 42.0, "stub-sync-field-free", "stub field-free basis")]
    assert (
        _query(index.database, "SELECT * FROM activities ORDER BY page_key")
        == activity_rows
    )


def test_page_producer_error_rolls_back_only_its_page(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = tuple(path.relative_to(synced_corpus) for path in synced_workout_pages)
    failed_path = paths[0].as_posix()
    fail_now = False
    transaction_active = False
    transaction_id: int | None = None
    transaction_count = 0
    producer_calls: list[tuple[str, int | None, bool]] = []
    state_writes: list[tuple[str, int | None, bool]] = []

    original_transaction = transaction
    write_page_state_name = "write_page_state"
    original_write_page_state = getattr(refresh, write_page_state_name)

    @contextmanager
    def observe_transaction(connection: IndexConnection) -> Iterator[None]:
        nonlocal transaction_active, transaction_id, transaction_count
        transaction_count += 1
        current_id = transaction_count
        with original_transaction(connection):
            transaction_active = True
            transaction_id = current_id
            try:
                yield
            finally:
                transaction_active = False
                transaction_id = None

    def observe_state_write(connection: IndexConnection, state: PageState) -> None:
        state_writes.append((state.page_key, transaction_id, transaction_active))
        original_write_page_state(connection, state)

    monkeypatch.setattr(refresh, "transaction", observe_transaction)

    @dataclass(frozen=True)
    class FailingDocumentProducer:
        name: str = "test.failing-document"
        tables: tuple[TableSpec, ...] = ()

        def rows(self, page: PageDocument) -> Rows:
            producer_calls.append((page.path, transaction_id, transaction_active))
            if fail_now and page.path == failed_path:
                raise ValueError("synthetic producer failure")
            return {}

    producer = FailingDocumentProducer()
    monkeypatch.setattr(
        registry,
        "DOCUMENT_PRODUCERS",
        (*registry.DOCUMENT_PRODUCERS, producer),
    )
    tables = (*core_registry,)
    database = tmp_path / "index-with-test-producer.duckdb"
    data_root = tmp_path / "producer-data"
    data_root.mkdir()
    with create_index(database) as connection:
        create_schema(connection, tables)
        write_meta(
            connection,
            IndexMeta(
                schema_version=SCHEMA_VERSION,
                fitdocs_version=tool_version(),
                duckdb_version=duckdb_version(),
                data_root=str(data_root.resolve()),
                athlete_fingerprint=athlete_fingerprint(None),
            ),
        )
        bookkeeping = read_bookkeeping(connection)
        assert bookkeeping is not None
        initial = refresh.reconcile(
            connection,
            bookkeeping,
            refresh.RefreshInputs(data_root, None, None, date(2026, 10, 6), None),
        )
        assert initial.pages_held == 0

    shutil.copytree(synced_corpus, data_root, dirs_exist_ok=True)
    first = _refresh(database, data_root)
    assert len(first.added) == 2
    producer_calls.clear()
    state_writes.clear()
    transaction_count = 0

    failed_sources = contract.source_refs(read_frontmatter(data_root / paths[0]) or {})
    assert failed_sources
    failed_key = contract.sha_of_ref(failed_sources[-1])
    assert failed_key is not None

    def page_rows() -> dict[str, list[tuple[object, ...]]]:
        captured: dict[str, list[tuple[object, ...]]] = {}
        for table in tables:
            if table.scope not in {TableScope.DOCUMENT, TableScope.COMPUTED}:
                continue
            if not any(column.name == "page_key" for column in table.columns):
                continue
            order = ", ".join(column.name for column in table.columns)
            captured[table.name] = _query(
                database,
                f"SELECT * FROM {table.name} WHERE page_key = ? ORDER BY {order}",
                (failed_key,),
            )
        return captured

    failed_rows_before = page_rows()
    assert failed_rows_before["pages"]
    assert failed_rows_before["records"]
    state_before = _query(
        database,
        "SELECT * FROM index_pages WHERE page_key = ?",
        (failed_key,),
    )
    assert len(state_before) == 1
    for relative_path in paths:
        page = data_root / relative_path
        original = page.read_text(encoding="utf-8")
        edited = original.replace("\n---\n", "\neffort: test\n---\n", 1)
        assert edited != original
        page.write_text(edited, encoding="utf-8")

    unexpected_error: ValueError | None = None
    result: refresh.RefreshResult | None = None
    with monkeypatch.context() as state_patch:
        state_patch.setattr(refresh, write_page_state_name, observe_state_write)
        assert getattr(refresh, write_page_state_name) is not original_write_page_state
        fail_now = True
        try:
            result = _refresh(database, data_root)
        except ValueError as error:
            unexpected_error = error
    assert getattr(refresh, write_page_state_name) is original_write_page_state

    assert unexpected_error is None, "non-RuntimeError producer failures are page-local"
    assert result is not None
    assert result.updated == (paths[1].as_posix(),)
    assert {path for path, _, _ in producer_calls} == {
        paths[0].as_posix(),
        paths[1].as_posix(),
    }
    assert len({tx_id for _, tx_id, _ in producer_calls}) == 2
    assert all(tx_id is not None and active for _, tx_id, active in producer_calls)
    assert result.page_errors == (
        (failed_path, "ValueError: synthetic producer failure"),
    )
    assert page_rows() == failed_rows_before
    assert (
        _query(
            database,
            "SELECT * FROM index_pages WHERE page_key = ?",
            (failed_key,),
        )
        == state_before
    )
    assert _query(
        database,
        "SELECT effort FROM pages WHERE path = ?",
        (paths[1].as_posix(),),
    ) == [("test",)]
    healthy_sources = contract.source_refs(read_frontmatter(data_root / paths[1]) or {})
    assert healthy_sources
    healthy_key = contract.sha_of_ref(healthy_sources[-1])
    assert healthy_key is not None
    failed_transactions = {
        tx_id for path, tx_id, _ in producer_calls if path == failed_path
    }
    healthy_transactions = {
        tx_id for path, tx_id, _ in producer_calls if path == paths[1].as_posix()
    }
    assert state_writes == [(healthy_key, next(iter(healthy_transactions)), True)]
    assert not any(key == failed_key for key, _, _ in state_writes)
    assert next(iter(failed_transactions)) != next(iter(healthy_transactions))

    fail_now = False
    monkeypatch.setattr(
        registry,
        "DOCUMENT_PRODUCERS",
        tuple(registry.DOCUMENT_PRODUCERS[:-1]),
    )
    retried = _refresh(database, data_root)
    assert retried.updated == (paths[0].as_posix(),)
    assert retried.page_errors == ()


def test_non_runtime_computed_error_keeps_new_page_out_until_retry(
    tmp_path: Path,
    core_registry: tuple[ResolvedTable, ...],
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "computed-error-data"
    data_root.mkdir()
    fail_now = False
    failed_paths: set[str] = set()

    @dataclass(frozen=True)
    class FailingComputedProducer:
        name: str = "test.failing-computed"
        tables: tuple[TableSpec, ...] = ()

        def rows(self, page: PageComputed) -> Rows:
            if fail_now and page.document.path in failed_paths:
                raise ValueError("synthetic computed producer failure")
            return {}

    failing_producer = FailingComputedProducer()
    monkeypatch.setattr(
        registry,
        "COMPUTED_PRODUCERS",
        (*registry.COMPUTED_PRODUCERS, failing_producer),
    )

    index = _empty_registered_index(
        tmp_path / "computed-error.duckdb", data_root, registry.registered_tables()
    )
    shutil.copytree(synced_corpus, data_root, dirs_exist_ok=True)
    initial = _refresh(index.database, data_root)
    assert len(initial.added) == 2

    source = tmp_path / "new-source"
    source.mkdir()
    (source / "new-ride.fit").write_bytes(
        builder.small_sport_fit_bytes(
            serial=99887766,
            fit_sport="cycling",
            timestamp_offset=5000,
        )
    )
    report = sync(
        source,
        index.data_root,
        athlete=None,
        tz=UTC,
        tiles=_SyntheticTiles(),
    )
    assert report.failures == ()
    scanned = scan_workout_pages(index.data_root).pages
    existing_keys: set[str] = set()
    for path in synced_workout_pages:
        sources = contract.source_refs(
            read_frontmatter(index.data_root / path.relative_to(synced_corpus)) or {}
        )
        assert sources
        page_key = contract.sha_of_ref(sources[-1])
        assert page_key is not None
        existing_keys.add(page_key)
    new_page = next(page for page in scanned if page.page_key not in existing_keys)
    failed_paths.add(new_page.path)
    existing_failed_page = index.data_root / synced_workout_pages[1].relative_to(
        synced_corpus
    )
    existing_failed_path = existing_failed_page.relative_to(index.data_root).as_posix()
    existing_sources = contract.source_refs(
        read_frontmatter(existing_failed_page) or {}
    )
    assert existing_sources
    existing_failed_key = contract.sha_of_ref(existing_sources[-1])
    assert existing_failed_key is not None
    failed_paths.add(existing_failed_path)
    previous_existing_rows = _page_rows(index, existing_failed_key)
    previous_existing_state = _query(
        index.database,
        "SELECT * FROM index_pages WHERE page_key = ?",
        (existing_failed_key,),
    )
    existing_failed_scanned = next(
        page for page in scanned if page.page_key == existing_failed_key
    )
    existing_composition = derive_page(
        index.data_root, existing_failed_scanned.sources, None
    )
    assert isinstance(existing_composition, Derived)
    handoff_metrics = DerivedMetrics(
        avg_heart_rate_bpm=181.5,
        avg_power_w=271.25,
        distance_m=12345.75,
    )
    rendered = rendered_handoff_page(
        existing_failed_path,
        existing_failed_key,
        len(existing_composition.composition.activity.samples.time_s),
        sources=existing_failed_scanned.sources,
        athlete=None,
    )
    rendered = replace(
        rendered,
        composition=existing_composition.composition,
        metrics=handoff_metrics,
    )
    handoff = HandoffCollector()
    handoff.add(rendered)
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM index_pages WHERE page_key = ?",
        (new_page.page_key,),
    ) == [(0,)]

    healthy_page = index.data_root / synced_workout_pages[0].relative_to(synced_corpus)
    healthy_sources = contract.source_refs(read_frontmatter(healthy_page) or {})
    assert healthy_sources
    healthy_key = contract.sha_of_ref(healthy_sources[-1])
    assert healthy_key is not None
    healthy_state_before = _query(
        index.database,
        "SELECT document_fingerprint FROM index_pages WHERE page_key = ?",
        (healthy_key,),
    )
    before = healthy_page.read_text(encoding="utf-8")
    changed = before + "\nA healthy page update while another page fails.\n"
    assert changed != before
    healthy_page.write_text(changed, encoding="utf-8")
    failed_before = existing_failed_page.read_text(encoding="utf-8")
    failed_changed = (
        failed_before + "\nA computed producer fails for this existing page.\n"
    )
    assert failed_changed != failed_before
    existing_failed_page.write_text(failed_changed, encoding="utf-8")
    fail_now = True
    unexpected_error: ValueError | None = None
    result: refresh.RefreshResult | None = None
    try:
        result = _refresh(index.database, index.data_root, handoff=handoff)
    except ValueError as error:
        unexpected_error = error

    assert unexpected_error is None, "non-RuntimeError computed failures are page-local"
    assert result is not None
    healthy_path = healthy_page.relative_to(index.data_root).as_posix()
    assert result.updated == (healthy_path,)
    assert result.added == ()
    assert tuple(sorted(result.page_errors)) == tuple(
        (path, "ValueError: synthetic computed producer failure")
        for path in sorted(failed_paths)
    )
    assert result.pages_held == 2
    assert all(path not in failed_paths for path, _ in result.without_computed)
    assert _page_rows(index, existing_failed_key) == previous_existing_rows
    assert (
        _query(
            index.database,
            "SELECT * FROM index_pages WHERE page_key = ?",
            (existing_failed_key,),
        )
        == previous_existing_state
    )
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM index_pages WHERE page_key = ?",
        (new_page.page_key,),
    ) == [(0,)]
    for table in index.tables:
        if table.scope in {TableScope.DOCUMENT, TableScope.COMPUTED} and any(
            column.name == "page_key" for column in table.columns
        ):
            assert _query(
                index.database,
                f"SELECT COUNT(*) FROM {table.name} WHERE page_key = ?",
                (new_page.page_key,),
            ) == [(0,)]
    healthy_state_after = _query(
        index.database,
        "SELECT document_fingerprint FROM index_pages WHERE page_key = ?",
        (healthy_key,),
    )
    assert healthy_state_after != healthy_state_before

    fail_now = False
    retried = _refresh(index.database, index.data_root)
    assert retried.added == (new_page.path,)
    assert retried.updated == (existing_failed_path,)
    assert retried.page_errors == ()
    assert retried.pages_held == 3
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM index_pages WHERE page_key = ?",
        (new_page.page_key,),
    ) == [(1,)]


def test_removal_deletes_page_rows_and_index_state(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    removed_pages = tuple(
        path.relative_to(synced_corpus) for path in synced_workout_pages
    )
    removed_keys: dict[Path, str] = {}
    for removed_page in removed_pages:
        removed_sources = contract.source_refs(
            read_frontmatter(index.data_root / removed_page) or {}
        )
        assert removed_sources
        removed_key = contract.sha_of_ref(removed_sources[-1])
        assert removed_key is not None
        removed_keys[removed_page] = removed_key
        assert (index.data_root / removed_page).is_file()
    per_page_tables = tuple(
        table
        for table in index.tables
        if table.scope in {TableScope.DOCUMENT, TableScope.COMPUTED}
        and any(column.name == "page_key" for column in table.columns)
    )
    assert per_page_tables
    with open_index(index.database, read_only=False) as connection:
        for removed_key in removed_keys.values():
            for table in per_page_tables:
                row = tuple(
                    {
                        ColumnType.VARCHAR: "seeded-removal-row",
                        ColumnType.INTEGER: 17,
                        ColumnType.DOUBLE: 17.25,
                        ColumnType.BOOLEAN: True,
                        ColumnType.DATE: date(2001, 2, 3),
                        ColumnType.TIMESTAMP: datetime(2001, 2, 3, 4, 5, 6),
                        ColumnType.VARCHAR_LIST: ("seeded-removal-row",),
                    }[column.type]
                    for column in table.columns
                    if column.name != "page_key"
                )
                insert_rows(connection, table, (cast(Row, row),), page_key=removed_key)
    for removed_key in removed_keys.values():
        for table in per_page_tables:
            assert (
                cast(
                    int,
                    _query(
                        index.database,
                        f"SELECT COUNT(*) FROM {table.name} WHERE page_key = ?",
                        (removed_key,),
                    )[0][0],
                )
                > 0
            )

    active = False
    current_transaction_id: int | None = None
    transaction_count = 0
    delete_events: list[tuple[str, tuple[str, ...], int | None, bool]] = []
    state_deletes: list[tuple[str, int | None, bool]] = []
    original_transaction = transaction
    delete_page_rows_name = "delete_page_rows"
    original_delete_page_rows = getattr(refresh, delete_page_rows_name)
    delete_page_state_name = "delete_page_state"
    original_delete_page_state = getattr(refresh, delete_page_state_name)

    @contextmanager
    def observe_transaction(connection: IndexConnection) -> Iterator[None]:
        nonlocal active, current_transaction_id, transaction_count
        transaction_count += 1
        current_id = transaction_count
        with original_transaction(connection):
            active = True
            current_transaction_id = current_id
            try:
                yield
            finally:
                active = False
                current_transaction_id = None

    def observe_delete(
        connection: IndexConnection,
        page_key: str,
        tables: tuple[ResolvedTable, ...],
    ) -> None:
        delete_events.append(
            (
                page_key,
                tuple(table.name for table in tables),
                current_transaction_id,
                active,
            )
        )
        original_delete_page_rows(connection, page_key, tables)

    def observe_state_delete(connection: IndexConnection, page_key: str) -> None:
        state_deletes.append((page_key, current_transaction_id, active))
        original_delete_page_state(connection, page_key)

    with monkeypatch.context() as removal_patch:
        removal_patch.setattr(refresh, "transaction", observe_transaction)
        removal_patch.setattr(refresh, delete_page_rows_name, observe_delete)
        removal_patch.setattr(refresh, delete_page_state_name, observe_state_delete)
        for removed_page in removed_pages:
            (index.data_root / removed_page).unlink()
        result = _refresh(index.database, index.data_root)

    assert result.removed == tuple(path.as_posix() for path in removed_pages)
    assert result.pages_held == 0
    assert transaction_count == len(removed_keys)
    expected_tables = tuple(table.name for table in index.tables)
    assert delete_events == [
        (removed_keys[path], expected_tables, tx_id, True)
        for tx_id, path in enumerate(sorted(removed_keys), 1)
    ]
    assert state_deletes == [
        (removed_keys[path], tx_id, True)
        for tx_id, path in enumerate(sorted(removed_keys), 1)
    ]
    assert all(
        state_event[1] == row_event[2]
        for state_event, row_event in zip(state_deletes, delete_events, strict=True)
    )
    for removed_key in removed_keys.values():
        assert _query(
            index.database,
            "SELECT COUNT(*) FROM index_pages WHERE page_key = ?",
            (removed_key,),
        ) == [(0,)]
        for table in per_page_tables:
            assert _query(
                index.database,
                f"SELECT COUNT(*) FROM {table.name} WHERE page_key = ?",
                (removed_key,),
            ) == [(0,)]


def test_unchanged_refresh_preserves_index_directory_files(
    built_index: BuiltIndex,
    synced_corpus: Path,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    def snapshot() -> dict[str, tuple[int, int, str]]:
        return {
            path.name: (
                path.stat().st_size,
                path.stat().st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted(index.database.parent.iterdir())
            if path.is_file()
        }

    before = snapshot()
    assert before
    result = _refresh(index.database, index.data_root)
    after = snapshot()

    assert after == before
    assert result.added == ()
    assert result.updated == ()
    assert result.removed == ()
    assert result.changed is False


def test_missing_base_noop_retries_when_archive_reappears(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus / "workouts", index.data_root / "workouts")
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2
    page_source = next(
        source_page
        for source_page in synced_workout_pages
        if len(contract.source_refs(read_frontmatter(source_page) or {})) == 2
    )
    page_relative = page_source.relative_to(synced_corpus)
    page = index.data_root / page_relative
    sources = contract.source_refs(read_frontmatter(page) or {})
    assert sources
    assert base_archive(index.data_root, sources) is None

    database_before = (
        index.database.stat().st_size,
        index.database.stat().st_mtime_ns,
        hashlib.sha256(index.database.read_bytes()).hexdigest(),
    )

    def unexpected_retry(*args: object, **kwargs: object) -> object:
        raise AssertionError("a still-missing base is not retried without a change")

    with monkeypatch.context() as scoped:
        scoped.setattr(derive, "derive_page", unexpected_retry)
        unchanged = _refresh(index.database, index.data_root)
        database_after = (
            index.database.stat().st_size,
            index.database.stat().st_mtime_ns,
            hashlib.sha256(index.database.read_bytes()).hexdigest(),
        )
        assert unchanged.updated == ()
        assert unchanged.page_errors == ()
        assert unchanged.without_computed == first.without_computed
        assert database_after == database_before

    archived_base = base_archive(synced_corpus, sources)
    assert archived_base is not None and archived_base.is_file()
    destination = index.data_root / archived_base.relative_to(synced_corpus)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archived_base, destination)
    assert base_archive(index.data_root, sources) is not None
    retried = _refresh(index.database, index.data_root)

    assert retried.updated == (page_relative.as_posix(),)
    assert retried.without_computed == tuple(
        entry
        for entry in first.without_computed
        if entry[0] != page_relative.as_posix()
    )
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM activities WHERE page_key = ?",
        (contract.sha_of_ref(sources[-1]),),
    ) == [(1,)]


def test_unreadable_extra_records_state_and_retries_later(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    source_page = next(
        path
        for path in synced_workout_pages
        if len(contract.source_refs(read_frontmatter(path) or {})) > 1
    )
    relative_page = source_page.relative_to(synced_corpus)
    page = index.data_root / relative_page
    sources = contract.source_refs(read_frontmatter(page) or {})
    assert len(sources) > 1
    extra_sha = contract.sha_of_ref(sources[0])
    assert extra_sha is not None
    unreadable_extra = archive_path(index.data_root, extra_sha)
    assert unreadable_extra.is_file()
    original_read_bytes = Path.read_bytes

    def deny_extra(path: Path) -> bytes:
        if path == unreadable_extra:
            raise PermissionError("synthetic archived extra read refusal")
        return original_read_bytes(path)

    original_text = page.read_text(encoding="utf-8")
    changed_text = original_text + "\nRetry an unreadable listed extra.\n"
    assert changed_text != original_text
    page.write_text(changed_text, encoding="utf-8")
    original_derive = derive.derive_page
    repeated_attempts = 0

    def count_repeated_attempt(*args: object, **kwargs: object) -> object:
        nonlocal repeated_attempts
        repeated_attempts += 1
        return original_derive(*args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "read_bytes", deny_extra)
        failed_source = _refresh(index.database, index.data_root)

        assert failed_source.page_errors == ()
        assert failed_source.without_computed == (
            (relative_page.as_posix(), ComputedState.SOURCE_UNREADABLE),
        )
        key = contract.sha_of_ref(sources[-1])
        assert key is not None
        assert _query(
            index.database,
            "SELECT COUNT(*) FROM activities WHERE page_key = ?",
            (key,),
        ) == [(0,)]

        before_repeat = _index_snapshot(index)
        scoped.setattr(derive, "derive_page", count_repeated_attempt)
        repeated = _refresh(index.database, index.data_root)
        after_repeat = _index_snapshot(index)
        assert repeated_attempts == 1
        assert (
            repeated.updated,
            repeated.without_computed,
            after_repeat,
        ) == ((), failed_source.without_computed, before_repeat)

    retried = _refresh(index.database, index.data_root)
    assert retried.page_errors == ()
    assert all(path != relative_page.as_posix() for path, _ in retried.without_computed)
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM activities WHERE page_key = ?",
        (key,),
    ) == [(1,)]


def test_undecodable_base_records_state_and_retries_later(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    relative_page = synced_workout_pages[0].relative_to(synced_corpus)
    page = index.data_root / relative_page
    sources = contract.source_refs(read_frontmatter(page) or {})
    assert sources
    base_sha = contract.sha_of_ref(sources[-1])
    assert base_sha is not None
    base = archive_path(index.data_root, base_sha)
    valid_bytes = base.read_bytes()
    assert valid_bytes
    base.write_bytes(b"synthetic bytes that are not a FIT archive")
    original_text = page.read_text(encoding="utf-8")
    changed_text = original_text + "\nRetry an undecodable base.\n"
    assert changed_text != original_text
    page.write_text(changed_text, encoding="utf-8")

    failed_source = _refresh(index.database, index.data_root)

    assert failed_source.page_errors == ()
    assert failed_source.without_computed == (
        (relative_page.as_posix(), ComputedState.SOURCE_UNDECODABLE),
    )
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM activities WHERE page_key = ?",
        (base_sha,),
    ) == [(0,)]

    index_snapshot = BuiltIndex(index.data_root, index.database, index.tables)
    before_repeat = _index_snapshot(index_snapshot)
    original_derive = derive.derive_page
    repeated_attempts = 0

    def count_repeated_attempt(*args: object, **kwargs: object) -> object:
        nonlocal repeated_attempts
        repeated_attempts += 1
        return original_derive(*args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as scoped:
        scoped.setattr(derive, "derive_page", count_repeated_attempt)
        repeated = _refresh(index.database, index.data_root)
        after_repeat = _index_snapshot(index_snapshot)
        assert repeated_attempts == 1
        assert (
            repeated.updated,
            repeated.without_computed,
            after_repeat,
        ) == ((), failed_source.without_computed, before_repeat)

    base.write_bytes(valid_bytes)
    retried = _refresh(index.database, index.data_root)
    assert retried.page_errors == ()
    assert all(path != relative_page.as_posix() for path, _ in retried.without_computed)
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM activities WHERE page_key = ?",
        (base_sha,),
    ) == [(1,)]


def test_higher_ranked_source_becomes_new_page_key(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    first = _refresh(index.database, index.data_root)
    assert len(first.added) == 2

    page_source = next(
        source_page
        for source_page in synced_workout_pages
        if len(contract.source_refs(read_frontmatter(source_page) or {})) == 2
    )
    page_relative = page_source.relative_to(synced_corpus)
    page = index.data_root / page_relative
    frontmatter = read_frontmatter(page)
    assert frontmatter is not None
    sources = contract.source_refs(frontmatter)
    assert len(sources) == 2
    old_key = contract.sha_of_ref(sources[-1])
    new_key = contract.sha_of_ref(sources[0])
    assert old_key is not None and new_key is not None and old_key != new_key
    scan_keys = {item.page_key for item in scan_workout_pages(index.data_root).pages}
    assert new_key not in scan_keys

    original = page.read_text(encoding="utf-8")
    original_listing = f"- {sources[0]}\n- {sources[1]}"
    reordered_listing = f"- {sources[1]}\n- {sources[0]}"
    assert original.count(original_listing) == 1
    changed = original.replace(original_listing, reordered_listing, 1)
    assert changed != original
    page.write_text(changed, encoding="utf-8")
    result = _refresh(index.database, index.data_root)

    assert result.added == (page_relative.as_posix(),)
    assert result.removed == (page_relative.as_posix(),)
    assert result.pages_held == 2
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM index_pages WHERE page_key = ?",
        (old_key,),
    ) == [(0,)]
    assert _query(
        index.database,
        "SELECT COUNT(*) FROM index_pages WHERE page_key = ?",
        (new_key,),
    ) == [(1,)]


def test_handoff_uses_handed_metrics_and_athlete_without_deriving_that_page(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = built_index
    shutil.copytree(synced_corpus, index.data_root, dirs_exist_ok=True)
    pages = scan_workout_pages(index.data_root).pages
    target = next(page for page in pages if len(page.sources) > 1)
    target_key = target.page_key
    handed_athlete = AthleteInputs(ftp_watts=311.0)
    command_athlete = AthleteInputs(ftp_watts=201.0)
    assert athlete_fingerprint(handed_athlete) != athlete_fingerprint(command_athlete)
    composed = derive_page(index.data_root, target.sources, None)
    assert isinstance(composed, Derived)
    assert composed.composition.provenance.extras
    rendered = rendered_handoff_page(
        target.path,
        target_key,
        3,
        sources=target.sources,
        athlete=handed_athlete,
    )
    rendered = replace(
        rendered,
        composition=composed.composition,
        metrics=DerivedMetrics(avg_heart_rate_bpm=177.0, distance_m=4321.0),
    )
    collector = HandoffCollector()
    collector.add(rendered)
    assert collector.take(target_key, target.sources) is rendered

    original_derive = derive.derive_page
    derive_calls: list[tuple[Path, tuple[str, ...]]] = []

    def observe_derive(
        data_root: Path, sources: tuple[str, ...], athlete: AthleteInputs | None
    ) -> object:
        derive_calls.append((data_root, sources))
        return original_derive(data_root, sources, athlete)

    monkeypatch.setattr(derive, "derive_page", observe_derive)
    result = _refresh(
        index.database,
        index.data_root,
        athlete=command_athlete,
        handoff=collector,
    )

    assert len(result.added) == 2
    assert len(derive_calls) == 1
    assert derive_calls[0][1] != target.sources
    assert _query(
        index.database,
        "SELECT avg_heart_rate_bpm, distance_m, athlete_fingerprint "
        "FROM activities WHERE page_key = ?",
        (target_key,),
    ) == [
        (
            177.0,
            4321.0,
            athlete_fingerprint(handed_athlete),
        )
    ]
    expected_channel_sources = tuple(
        (channel, composed.composition.provenance.base.sha256, "base")
        for channel in composed.composition.provenance.base.channels
    ) + tuple(
        (channel, extra.sha256, "extra")
        for extra in composed.composition.provenance.extras
        for channel in extra.channels
    )
    assert len(expected_channel_sources) > 0
    assert _query(
        index.database,
        "SELECT channel, source_sha256, role FROM channel_sources "
        "WHERE page_key = ? ORDER BY channel, source_sha256, role",
        (target_key,),
    ) == sorted(expected_channel_sources)
