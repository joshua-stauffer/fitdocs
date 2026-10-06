"""Page-tier refresh and removal tests for task 6.1."""

from __future__ import annotations

import hashlib
import inspect
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final, cast, get_type_hints

import pytest

from fitdocs import Modality, contract
from fitdocs.docio import read_document, read_frontmatter
from fitdocs.index import derive, refresh, registry
from fitdocs.index.bookkeeping import Bookkeeping, ComputedState, IndexMeta, PageState
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.corpus import LeftOutPage, scan_workout_pages
from fitdocs.index.derive import Derived, base_archive, derive_page
from fitdocs.index.fingerprint import (
    athlete_fingerprint,
    document_fingerprint,
    render_fingerprint,
)
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.producer import (
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
                today=date(2026, 10, 6),
                progress=None,
            ),
        )


def _query(
    database: Path, sql: str, params: tuple[object, ...] = ()
) -> list[tuple[object, ...]]:
    with open_index(database, read_only=True) as connection:
        return connection.execute(sql, params).fetchall()


def _index_snapshot(index: BuiltIndex) -> tuple[object, ...]:
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

    def rows(self, page: PageDocument) -> Rows:
        self.seen.append(page)
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

    monkeypatch.setattr(derive, "derive_page", unexpected_retry)
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

    monkeypatch.undo()
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
    monkeypatch.setattr(Path, "read_bytes", deny_extra)
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
    original_derive = derive.derive_page
    repeated_attempts = 0

    def count_repeated_attempt(*args: object, **kwargs: object) -> object:
        nonlocal repeated_attempts
        repeated_attempts += 1
        return original_derive(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(derive, "derive_page", count_repeated_attempt)
    repeated = _refresh(index.database, index.data_root)
    after_repeat = _index_snapshot(index)
    assert repeated_attempts == 1
    assert (
        repeated.updated,
        repeated.without_computed,
        after_repeat,
    ) == ((), failed_source.without_computed, before_repeat)

    monkeypatch.undo()
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

    monkeypatch.setattr(derive, "derive_page", count_repeated_attempt)
    repeated = _refresh(index.database, index.data_root)
    after_repeat = _index_snapshot(index_snapshot)
    assert repeated_attempts == 1
    assert (
        repeated.updated,
        repeated.without_computed,
        after_repeat,
    ) == ((), failed_source.without_computed, before_repeat)
    monkeypatch.undo()

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
