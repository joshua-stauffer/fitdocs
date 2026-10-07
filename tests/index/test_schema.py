"""Synthetic schema specs for analytics-index task 2.1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from typing import Any, get_type_hints

import pytest

from fitdocs.index.bookkeeping import (
    BOOKKEEPING_TABLES,
    Bookkeeping,
    ComputedState,
    IndexMeta,
    PageState,
)
from fitdocs.index.schema import (
    PAGE_KEY_COLUMN,
    RESERVED_PREFIX,
    SCHEMA_VERSION,
    UNIT_SUFFIXES,
    ColumnSpec,
    ColumnType,
    ResolvedTable,
    SchemaError,
    TableScope,
    TableSpec,
    _contains_unit_phrase,
    _matching_unit_suffix,
    resolve_tables,
    schema_digest,
    schema_manifest,
)
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Lap, Samples, StrengthSet


@dataclass(frozen=True)
class SyntheticProducer:
    name: str
    tables: tuple[TableSpec, ...]


def column(
    name: str = "value",
    kind: ColumnType = ColumnType.VARCHAR,
    description: str = "A value.",
) -> ColumnSpec:
    return ColumnSpec(name=name, type=kind, description=description)


def table(
    name: str = "samples",
    columns: tuple[ColumnSpec, ...] | None = None,
    description: str = "Sample values.",
) -> TableSpec:
    return TableSpec(name=name, description=description, columns=columns or (column(),))


def producer(name: str, *tables: TableSpec) -> SyntheticProducer:
    return SyntheticProducer(name=name, tables=tuple(tables))


def resolve_scoped_producers(
    scoped: tuple[tuple[str, SyntheticProducer], ...],
    bookkeeping: tuple[TableSpec, ...] = (),
) -> tuple[ResolvedTable, ...]:
    by_scope: dict[str, list[SyntheticProducer]] = {
        "document": [],
        "computed": [],
        "corpus": [],
    }
    for scope, item in scoped:
        by_scope[scope].append(item)
    return resolve_tables(
        document=tuple(by_scope["document"]),
        computed=tuple(by_scope["computed"]),
        corpus=tuple(by_scope["corpus"]),
        bookkeeping=bookkeeping,
    )


def resolve_single_table(scope: str, spec: TableSpec) -> tuple[ResolvedTable, ...]:
    item = producer("core.valid", spec)
    if scope == "document":
        return resolve_tables((item,), (), (), ())
    if scope == "computed":
        return resolve_tables((), (item,), (), ())
    if scope == "corpus":
        return resolve_tables((), (), (item,), ())
    return resolve_tables((), (), (), (spec,))


def test_schema_public_types_and_constants_match_the_contract() -> None:
    assert SCHEMA_VERSION == 2
    assert all(isinstance(member, str) for member in ColumnType)
    assert all(isinstance(member, str) for member in TableScope)
    assert [member.value for member in ColumnType] == [
        "VARCHAR",
        "BOOLEAN",
        "INTEGER",
        "BIGINT",
        "DOUBLE",
        "DATE",
        "TIMESTAMP",
        "VARCHAR[]",
    ]
    assert [(member.name, member.value) for member in ColumnType] == [
        ("VARCHAR", "VARCHAR"),
        ("BOOLEAN", "BOOLEAN"),
        ("INTEGER", "INTEGER"),
        ("BIGINT", "BIGINT"),
        ("DOUBLE", "DOUBLE"),
        ("DATE", "DATE"),
        ("TIMESTAMP", "TIMESTAMP"),
        ("VARCHAR_LIST", "VARCHAR[]"),
    ]
    assert issubclass(SchemaError, ValueError)
    assert [member.value for member in TableScope] == [
        "document",
        "computed",
        "corpus",
        "bookkeeping",
    ]
    assert [(member.name, member.value) for member in TableScope] == [
        ("DOCUMENT", "document"),
        ("COMPUTED", "computed"),
        ("CORPUS", "corpus"),
        ("BOOKKEEPING", "bookkeeping"),
    ]
    assert [member.name for member in fields(ColumnSpec)] == [
        "name",
        "type",
        "description",
    ]
    assert [member.name for member in fields(TableSpec)] == [
        "name",
        "description",
        "columns",
    ]
    assert [member.name for member in fields(ResolvedTable)] == [
        "producer",
        "scope",
        "name",
        "description",
        "columns",
    ]
    assert get_type_hints(ColumnSpec) == {
        "name": str,
        "type": ColumnType,
        "description": str,
    }
    assert get_type_hints(TableSpec) == {
        "name": str,
        "description": str,
        "columns": tuple[ColumnSpec, ...],
    }
    assert get_type_hints(ResolvedTable) == {
        "producer": str,
        "scope": TableScope,
        "name": str,
        "description": str,
        "columns": tuple[ColumnSpec, ...],
    }
    assert (
        ColumnSpec(
            name="page_key",
            type=ColumnType.VARCHAR,
            description=(
                "Key of the workout page: the SHA-256 (64 hex) of the "
                "page's base file, "
                "the last file its sources list."
            ),
        )
        == PAGE_KEY_COLUMN
    )
    assert RESERVED_PREFIX == "index_"
    assert UNIT_SUFFIXES == (
        ("_s_per_km", "seconds per kilometre"),
        ("_local", "local"),
        ("_kn_m", "kilonewtons per metre"),
        ("_kcal", "kilocalories"),
        ("_mps", "metres per second"),
        ("_bpm", "beats per minute"),
        ("_rpm", "revolutions per minute"),
        ("_deg", "degrees"),
        ("_pct", "percent"),
        ("_utc", "UTC"),
        ("_mm", "millimetres"),
        ("_ms", "milliseconds"),
        ("_bw", "body weights"),
        ("_kg", "kilograms"),
        ("_km", "kilometres"),
        ("_m", "metres"),
        ("_s", "seconds"),
        ("_w", "watts"),
        ("_c", "degrees Celsius"),
    )
    assert len(UNIT_SUFFIXES) == 19
    assert [len(suffix) for suffix, _ in UNIT_SUFFIXES] == sorted(
        (len(suffix) for suffix, _ in UNIT_SUFFIXES), reverse=True
    )


def test_bookkeeping_models_and_table_specs_match_the_contract() -> None:
    assert all(isinstance(member, str) for member in ComputedState)
    assert [member.value for member in ComputedState] == [
        "computed",
        "source_missing",
        "source_unreadable",
        "source_undecodable",
    ]
    assert [(member.name, member.value) for member in ComputedState] == [
        ("COMPUTED", "computed"),
        ("SOURCE_MISSING", "source_missing"),
        ("SOURCE_UNREADABLE", "source_unreadable"),
        ("SOURCE_UNDECODABLE", "source_undecodable"),
    ]
    assert [member.name for member in fields(IndexMeta)] == [
        "schema_version",
        "fitdocs_version",
        "duckdb_version",
        "data_root",
        "athlete_fingerprint",
    ]
    assert [member.name for member in fields(PageState)] == [
        "page_key",
        "path",
        "document_fingerprint",
        "render_fingerprint",
        "computed_state",
    ]
    assert [member.name for member in fields(Bookkeeping)] == [
        "meta",
        "pages",
        "producers",
    ]
    assert get_type_hints(IndexMeta) == {
        "schema_version": int,
        "fitdocs_version": str | None,
        "duckdb_version": str,
        "data_root": str,
        "athlete_fingerprint": str,
    }
    assert get_type_hints(PageState) == {
        "page_key": str,
        "path": str,
        "document_fingerprint": str,
        "render_fingerprint": str | None,
        "computed_state": ComputedState,
    }
    assert get_type_hints(Bookkeeping) == {
        "meta": IndexMeta,
        "pages": Mapping[str, PageState],
        "producers": Mapping[str, str | None],
    }
    assert tuple(spec.name for spec in BOOKKEEPING_TABLES) == (
        "index_meta",
        "index_pages",
        "index_producers",
    )
    expected = (
        TableSpec(
            "index_meta",
            "Metadata recorded by the most recent index refresh.",
            (
                ColumnSpec(
                    "schema_version",
                    ColumnType.INTEGER,
                    "Schema version of this index.",
                ),
                ColumnSpec(
                    "fitdocs_version",
                    ColumnType.VARCHAR,
                    "Version of fitdocs that last wrote the index; NULL "
                    "when not installed as a distribution.",
                ),
                ColumnSpec(
                    "duckdb_version",
                    ColumnType.VARCHAR,
                    "Version of DuckDB that wrote the index.",
                ),
                ColumnSpec(
                    "data_root",
                    ColumnType.VARCHAR,
                    "Resolved absolute path of the data root.",
                ),
                ColumnSpec(
                    "athlete_fingerprint",
                    ColumnType.VARCHAR,
                    "SHA-256 fingerprint of athlete inputs current "
                    "at the last refresh.",
                ),
            ),
        ),
        TableSpec(
            "index_pages",
            "Document and computed-value bookkeeping for each indexed workout page.",
            (
                ColumnSpec(
                    "page_key",
                    ColumnType.VARCHAR,
                    "SHA-256 key of the page's base file.",
                ),
                ColumnSpec(
                    "path",
                    ColumnType.VARCHAR,
                    "Data-root-relative POSIX path of the workout page.",
                ),
                ColumnSpec(
                    "document_fingerprint",
                    ColumnType.VARCHAR,
                    "Fingerprint of the page document.",
                ),
                ColumnSpec(
                    "render_fingerprint",
                    ColumnType.VARCHAR,
                    "Fingerprint of the rendering at the last computed attempt; "
                    "NULL when none.",
                ),
                ColumnSpec(
                    "computed_state",
                    ColumnType.VARCHAR,
                    "Computed state: computed, source_missing, source_unreadable "
                    "or source_undecodable.",
                ),
            ),
        ),
        TableSpec(
            "index_producers",
            "Producer registrations and corpus fingerprints recorded by the index.",
            (
                ColumnSpec("producer", ColumnType.VARCHAR, "Registered producer name."),
                ColumnSpec(
                    "kind",
                    ColumnType.VARCHAR,
                    "Producer scope: document, computed or corpus.",
                ),
                ColumnSpec(
                    "tables",
                    ColumnType.VARCHAR_LIST,
                    "Names of tables declared by the producer.",
                ),
                ColumnSpec(
                    "fingerprint",
                    ColumnType.VARCHAR,
                    "Combined corpus fingerprint; NULL for per-page producers.",
                ),
            ),
        ),
    )
    assert expected == BOOKKEEPING_TABLES


def test_resolved_tables_have_scope_order_and_page_key_only_for_per_page() -> None:
    document_first = producer("core.zed", table("doc_zed"))
    document_second = producer("core.able", table("doc_able"))
    computed = producer("core.metrics", table("computed_values"))
    corpus = producer(
        "derived.summary",
        table("summary", (column("page_key"), column("measure"))),
    )
    bookkeeping = BOOKKEEPING_TABLES

    resolved = resolve_tables(
        document=(document_first, document_second),
        computed=(computed,),
        corpus=(corpus,),
        bookkeeping=bookkeeping,
    )

    assert [(item.scope.value, item.name, item.producer) for item in resolved] == [
        ("bookkeeping", "index_meta", "bookkeeping"),
        ("bookkeeping", "index_pages", "bookkeeping"),
        ("bookkeeping", "index_producers", "bookkeeping"),
        ("document", "doc_zed", "core.zed"),
        ("document", "doc_able", "core.able"),
        ("computed", "computed_values", "core.metrics"),
        ("corpus", "summary", "derived.summary"),
    ]
    assert tuple(item.columns for item in resolved[:3]) == tuple(
        spec.columns for spec in BOOKKEEPING_TABLES
    )
    assert [spec.name for spec in resolved[3].columns] == ["page_key", "value"]
    assert [spec.name for spec in resolved[4].columns] == ["page_key", "value"]
    assert [spec.name for spec in resolved[5].columns] == ["page_key", "value"]
    assert [spec.name for spec in resolved[6].columns] == ["page_key", "measure"]


ResolutionCase = tuple[
    tuple[SyntheticProducer, ...],
    tuple[SyntheticProducer, ...],
    tuple[SyntheticProducer, ...],
    tuple[TableSpec, ...],
    tuple[ResolvedTable, ...],
]


def _document_resolved_output_case() -> ResolutionCase:
    return (
        (
            producer(
                "core.zulu_documents",
                TableSpec(
                    "z_doc_summary",
                    "Zulu document summary.",
                    (
                        column(
                            "z_count",
                            ColumnType.INTEGER,
                            "Zulu count from document.",
                        ),
                        column(
                            "a_value",
                            ColumnType.DOUBLE,
                            "Zulu value from document.",
                        ),
                    ),
                ),
                TableSpec(
                    "a_doc_detail",
                    "Zulu document detail.",
                    (
                        column(
                            "z_flag", ColumnType.BOOLEAN, "Zulu flag from document."
                        ),
                        column(
                            "a_label",
                            ColumnType.VARCHAR,
                            "Zulu label from document.",
                        ),
                    ),
                ),
            ),
            producer(
                "core.alpha_documents",
                TableSpec(
                    "z_alpha_summary",
                    "Alpha document summary.",
                    (
                        column(
                            "z_rank", ColumnType.BIGINT, "Alpha rank from document."
                        ),
                        column(
                            "a_score",
                            ColumnType.DOUBLE,
                            "Alpha score from document.",
                        ),
                    ),
                ),
                TableSpec(
                    "a_alpha_detail",
                    "Alpha document detail.",
                    (
                        column("z_date", ColumnType.DATE, "Alpha date from document."),
                        column(
                            "a_note",
                            ColumnType.VARCHAR,
                            "Alpha note from document.",
                        ),
                    ),
                ),
            ),
        ),
        (),
        (),
        (),
        (
            ResolvedTable(
                "core.zulu_documents",
                TableScope.DOCUMENT,
                "z_doc_summary",
                "Zulu document summary.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec(
                        "z_count", ColumnType.INTEGER, "Zulu count from document."
                    ),
                    ColumnSpec(
                        "a_value", ColumnType.DOUBLE, "Zulu value from document."
                    ),
                ),
            ),
            ResolvedTable(
                "core.zulu_documents",
                TableScope.DOCUMENT,
                "a_doc_detail",
                "Zulu document detail.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec(
                        "z_flag", ColumnType.BOOLEAN, "Zulu flag from document."
                    ),
                    ColumnSpec(
                        "a_label", ColumnType.VARCHAR, "Zulu label from document."
                    ),
                ),
            ),
            ResolvedTable(
                "core.alpha_documents",
                TableScope.DOCUMENT,
                "z_alpha_summary",
                "Alpha document summary.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec(
                        "z_rank", ColumnType.BIGINT, "Alpha rank from document."
                    ),
                    ColumnSpec(
                        "a_score", ColumnType.DOUBLE, "Alpha score from document."
                    ),
                ),
            ),
            ResolvedTable(
                "core.alpha_documents",
                TableScope.DOCUMENT,
                "a_alpha_detail",
                "Alpha document detail.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec("z_date", ColumnType.DATE, "Alpha date from document."),
                    ColumnSpec(
                        "a_note", ColumnType.VARCHAR, "Alpha note from document."
                    ),
                ),
            ),
        ),
    )


def _computed_resolved_output_case() -> ResolutionCase:
    return (
        (),
        (
            producer(
                "core.zulu_metrics",
                TableSpec(
                    "z_computed_summary",
                    "Zulu computed summary.",
                    (
                        column(
                            "z_peak", ColumnType.DOUBLE, "Zulu peak computed value."
                        ),
                        column(
                            "a_total",
                            ColumnType.INTEGER,
                            "Zulu total computed value.",
                        ),
                    ),
                ),
                TableSpec(
                    "a_computed_detail",
                    "Zulu computed detail.",
                    (
                        column(
                            "z_valid",
                            ColumnType.BOOLEAN,
                            "Zulu validity computed value.",
                        ),
                        column(
                            "a_label",
                            ColumnType.VARCHAR,
                            "Zulu label computed value.",
                        ),
                    ),
                ),
            ),
            producer(
                "core.alpha_metrics",
                TableSpec(
                    "z_alpha_summary",
                    "Alpha computed summary.",
                    (
                        column(
                            "z_created_utc",
                            ColumnType.TIMESTAMP,
                            "Alpha creation instant in UTC.",
                        ),
                        column("a_ratio", ColumnType.DOUBLE, "Alpha computed ratio."),
                    ),
                ),
                TableSpec(
                    "a_alpha_detail",
                    "Alpha computed detail.",
                    (
                        column("z_count", ColumnType.BIGINT, "Alpha computed count."),
                        column("a_note", ColumnType.VARCHAR, "Alpha computed note."),
                    ),
                ),
            ),
        ),
        (),
        (),
        (
            ResolvedTable(
                "core.zulu_metrics",
                TableScope.COMPUTED,
                "z_computed_summary",
                "Zulu computed summary.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec(
                        "z_peak", ColumnType.DOUBLE, "Zulu peak computed value."
                    ),
                    ColumnSpec(
                        "a_total", ColumnType.INTEGER, "Zulu total computed value."
                    ),
                ),
            ),
            ResolvedTable(
                "core.zulu_metrics",
                TableScope.COMPUTED,
                "a_computed_detail",
                "Zulu computed detail.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec(
                        "z_valid",
                        ColumnType.BOOLEAN,
                        "Zulu validity computed value.",
                    ),
                    ColumnSpec(
                        "a_label", ColumnType.VARCHAR, "Zulu label computed value."
                    ),
                ),
            ),
            ResolvedTable(
                "core.alpha_metrics",
                TableScope.COMPUTED,
                "z_alpha_summary",
                "Alpha computed summary.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec(
                        "z_created_utc",
                        ColumnType.TIMESTAMP,
                        "Alpha creation instant in UTC.",
                    ),
                    ColumnSpec("a_ratio", ColumnType.DOUBLE, "Alpha computed ratio."),
                ),
            ),
            ResolvedTable(
                "core.alpha_metrics",
                TableScope.COMPUTED,
                "a_alpha_detail",
                "Alpha computed detail.",
                (
                    ColumnSpec(
                        "page_key",
                        ColumnType.VARCHAR,
                        (
                            "Key of the workout page: the SHA-256 (64 hex) "
                            "of the page's base file, the last file its "
                            "sources list."
                        ),
                    ),
                    ColumnSpec("z_count", ColumnType.BIGINT, "Alpha computed count."),
                    ColumnSpec("a_note", ColumnType.VARCHAR, "Alpha computed note."),
                ),
            ),
        ),
    )


def _corpus_resolved_output_case() -> ResolutionCase:
    return (
        (),
        (),
        (
            producer(
                "derived.zulu_catalog",
                TableSpec(
                    "z_corpus_summary",
                    "Zulu corpus summary.",
                    (
                        column(
                            "z_members",
                            ColumnType.BIGINT,
                            "Zulu corpus member count.",
                        ),
                        column("a_weight", ColumnType.DOUBLE, "Zulu corpus weight."),
                    ),
                ),
                TableSpec(
                    "a_corpus_detail",
                    "Zulu corpus detail.",
                    (
                        column(
                            "z_active",
                            ColumnType.BOOLEAN,
                            "Zulu corpus active state.",
                        ),
                        column("a_name", ColumnType.VARCHAR, "Zulu corpus name."),
                    ),
                ),
            ),
            producer(
                "derived.alpha_catalog",
                TableSpec(
                    "z_alpha_corpus",
                    "Alpha corpus summary.",
                    (
                        column("z_day", ColumnType.DATE, "Alpha corpus day."),
                        column("a_score", ColumnType.DOUBLE, "Alpha corpus score."),
                    ),
                ),
                TableSpec(
                    "a_alpha_corpus",
                    "Alpha corpus detail.",
                    (
                        column("z_depth", ColumnType.INTEGER, "Alpha corpus depth."),
                        column("a_label", ColumnType.VARCHAR, "Alpha corpus label."),
                    ),
                ),
            ),
        ),
        (),
        (
            ResolvedTable(
                "derived.zulu_catalog",
                TableScope.CORPUS,
                "z_corpus_summary",
                "Zulu corpus summary.",
                (
                    ColumnSpec(
                        "z_members", ColumnType.BIGINT, "Zulu corpus member count."
                    ),
                    ColumnSpec("a_weight", ColumnType.DOUBLE, "Zulu corpus weight."),
                ),
            ),
            ResolvedTable(
                "derived.zulu_catalog",
                TableScope.CORPUS,
                "a_corpus_detail",
                "Zulu corpus detail.",
                (
                    ColumnSpec(
                        "z_active", ColumnType.BOOLEAN, "Zulu corpus active state."
                    ),
                    ColumnSpec("a_name", ColumnType.VARCHAR, "Zulu corpus name."),
                ),
            ),
            ResolvedTable(
                "derived.alpha_catalog",
                TableScope.CORPUS,
                "z_alpha_corpus",
                "Alpha corpus summary.",
                (
                    ColumnSpec("z_day", ColumnType.DATE, "Alpha corpus day."),
                    ColumnSpec("a_score", ColumnType.DOUBLE, "Alpha corpus score."),
                ),
            ),
            ResolvedTable(
                "derived.alpha_catalog",
                TableScope.CORPUS,
                "a_alpha_corpus",
                "Alpha corpus detail.",
                (
                    ColumnSpec("z_depth", ColumnType.INTEGER, "Alpha corpus depth."),
                    ColumnSpec("a_label", ColumnType.VARCHAR, "Alpha corpus label."),
                ),
            ),
        ),
    )


def _bookkeeping_resolved_output_case() -> ResolutionCase:
    return (
        (),
        (),
        (),
        (
            TableSpec(
                "z_bookkeeping_summary",
                "Zulu bookkeeping summary.",
                (
                    column("z_name", ColumnType.VARCHAR, "Zulu bookkeeping name."),
                    column("a_count", ColumnType.INTEGER, "Zulu bookkeeping count."),
                ),
            ),
            TableSpec(
                "a_bookkeeping_detail",
                "Alpha bookkeeping detail.",
                (
                    column(
                        "z_enabled",
                        ColumnType.BOOLEAN,
                        "Alpha bookkeeping enabled state.",
                    ),
                    column("a_total", ColumnType.BIGINT, "Alpha bookkeeping total."),
                ),
            ),
        ),
        (
            ResolvedTable(
                "bookkeeping",
                TableScope.BOOKKEEPING,
                "z_bookkeeping_summary",
                "Zulu bookkeeping summary.",
                (
                    ColumnSpec("z_name", ColumnType.VARCHAR, "Zulu bookkeeping name."),
                    ColumnSpec(
                        "a_count", ColumnType.INTEGER, "Zulu bookkeeping count."
                    ),
                ),
            ),
            ResolvedTable(
                "bookkeeping",
                TableScope.BOOKKEEPING,
                "a_bookkeeping_detail",
                "Alpha bookkeeping detail.",
                (
                    ColumnSpec(
                        "z_enabled",
                        ColumnType.BOOLEAN,
                        "Alpha bookkeeping enabled state.",
                    ),
                    ColumnSpec(
                        "a_total", ColumnType.BIGINT, "Alpha bookkeeping total."
                    ),
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    "case_factory",
    [
        _document_resolved_output_case,
        _computed_resolved_output_case,
        _corpus_resolved_output_case,
        _bookkeeping_resolved_output_case,
    ],
    ids=["document", "computed", "corpus", "bookkeeping"],
)
def test_resolved_table_outputs_preserve_complete_metadata_and_order(
    case_factory: Callable[[], ResolutionCase],
) -> None:
    document, computed, corpus, bookkeeping, expected = case_factory()
    resolved = resolve_tables(document, computed, corpus, bookkeeping)
    assert resolved == expected


def test_duplicate_producer_names_are_rejected() -> None:
    one = producer("core.same", table("first"))
    two = producer("core.same", table("second"))
    with pytest.raises(SchemaError, match="producer"):
        resolve_tables((one,), (two,), (), ())


@pytest.mark.parametrize(
    ("first_scope", "second_scope"),
    [
        ("document", "document"),
        ("document", "computed"),
        ("document", "corpus"),
        ("computed", "computed"),
        ("computed", "corpus"),
        ("corpus", "corpus"),
    ],
    ids=[
        "document-within",
        "document-computed",
        "document-corpus",
        "computed-within",
        "computed-corpus",
        "corpus-within",
    ],
)
def test_duplicate_producer_names_are_rejected_within_and_across_registries(
    first_scope: str, second_scope: str
) -> None:
    first = producer("core.shared", table("first_table"))
    second = producer("core.shared", table("second_table"))
    with pytest.raises(SchemaError, match="producer"):
        resolve_scoped_producers(((first_scope, first), (second_scope, second)))


def test_duplicate_table_names_are_rejected() -> None:
    one = producer("core.one", table("reused"))
    two = producer("core.two", table("reused"))
    with pytest.raises(SchemaError, match="table"):
        resolve_tables((one, two), (), (), ())


@pytest.mark.parametrize(
    ("first_scope", "second_scope"),
    [
        ("document", "document"),
        ("document", "computed"),
        ("document", "corpus"),
        ("document", "bookkeeping"),
        ("computed", "computed"),
        ("computed", "corpus"),
        ("computed", "bookkeeping"),
        ("corpus", "corpus"),
        ("corpus", "bookkeeping"),
        ("bookkeeping", "bookkeeping"),
    ],
    ids=[
        "document-within",
        "document-computed",
        "document-corpus",
        "document-bookkeeping",
        "computed-within",
        "computed-corpus",
        "computed-bookkeeping",
        "corpus-within",
        "corpus-bookkeeping",
        "bookkeeping-within",
    ],
)
def test_duplicate_table_names_are_rejected_within_and_across_scopes(
    first_scope: str, second_scope: str
) -> None:
    shared = "shared_table"
    first = producer("core.first", table(shared))
    second = producer("core.second", table(shared))
    scoped: list[tuple[str, SyntheticProducer]] = []
    bookkeeping: list[TableSpec] = []
    if first_scope == "bookkeeping":
        bookkeeping.append(table(shared))
    else:
        scoped.append((first_scope, first))
    if second_scope == "bookkeeping":
        bookkeeping.append(table(shared))
    else:
        scoped.append((second_scope, second))
    with pytest.raises(SchemaError, match="duplicate table"):
        resolve_scoped_producers(tuple(scoped), tuple(bookkeeping))


def test_non_snake_table_name_is_rejected() -> None:
    with pytest.raises(SchemaError, match="table"):
        resolve_tables((producer("core.valid", table("badTable")),), (), (), ())


@pytest.mark.parametrize(
    "name",
    [
        "2starts_with_digit",
        "bad.name",
        "bad-name",
        "_leading",
        "trailing_",
        "double__underscore",
    ],
)
def test_invalid_table_identifier_shapes_are_rejected(name: str) -> None:
    with pytest.raises(SchemaError, match="table"):
        resolve_tables((producer("core.valid", table(name)),), (), (), ())


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
@pytest.mark.parametrize(
    "name",
    [
        "badTable",
        "2starts_with_digit",
        "bad.name",
        "bad-name",
        "_leading",
        "trailing_",
        "double__underscore",
    ],
)
def test_invalid_table_identifier_shapes_are_rejected_in_every_scope(
    scope: str, name: str
) -> None:
    spec = table(name)
    with pytest.raises(SchemaError, match="table"):
        if scope == "bookkeeping":
            resolve_tables((), (), (), (spec,))
        elif scope == "document":
            resolve_tables((producer("core.valid", spec),), (), (), ())
        elif scope == "computed":
            resolve_tables((), (producer("core.valid", spec),), (), ())
        else:
            resolve_tables((), (), (producer("core.valid", spec),), ())


def test_non_snake_column_name_is_rejected() -> None:
    with pytest.raises(SchemaError, match="column"):
        resolve_tables(
            (producer("core.valid", table(columns=(column("badName"),))),), (), (), ()
        )


@pytest.mark.parametrize(
    "name",
    [
        "2starts_with_digit",
        "bad.name",
        "bad-name",
        "_leading",
        "trailing_",
        "double__underscore",
    ],
)
def test_invalid_column_identifier_shapes_are_rejected(name: str) -> None:
    with pytest.raises(SchemaError, match="column"):
        resolve_tables(
            (producer("core.valid", table(columns=(column(name),))),), (), (), ()
        )


def test_reserved_prefix_is_rejected_for_producer_tables() -> None:
    with pytest.raises(SchemaError, match="reserved"):
        resolve_tables((producer("core.valid", table("index_private")),), (), (), ())


@pytest.mark.parametrize("scope", ["document", "computed", "corpus"])
def test_reserved_prefix_is_rejected_for_every_producer_scope(scope: str) -> None:
    item = producer("core.valid", table("index_private"))
    with pytest.raises(SchemaError, match="reserved"):
        resolve_scoped_producers(((scope, item),))


def test_reserved_prefix_remains_available_to_bookkeeping_tables() -> None:
    resolved = resolve_tables((), (), (), (table("index_auxiliary"),))
    assert [(item.scope, item.name) for item in resolved] == [
        (TableScope.BOOKKEEPING, "index_auxiliary")
    ]


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_empty_column_description_is_rejected_in_every_scope(scope: str) -> None:
    spec = table("description_checks", (column("status", description=""),))
    with pytest.raises(SchemaError, match="column"):
        if scope == "document":
            resolve_tables((producer("core.valid", spec),), (), (), ())
        elif scope == "computed":
            resolve_tables((), (producer("core.valid", spec),), (), ())
        elif scope == "corpus":
            resolve_tables((), (), (producer("core.valid", spec),), ())
        else:
            resolve_tables((), (), (), (spec,))


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_wrong_unit_is_rejected_in_every_scope(scope: str) -> None:
    spec = table(
        "unit_checks",
        (column("duration_s", ColumnType.DOUBLE, "Duration in milliseconds."),),
    )
    with pytest.raises(SchemaError, match="unit"):
        if scope == "document":
            resolve_tables((producer("core.valid", spec),), (), (), ())
        elif scope == "computed":
            resolve_tables((), (producer("core.valid", spec),), (), ())
        elif scope == "corpus":
            resolve_tables((), (), (producer("core.valid", spec),), ())
        else:
            resolve_tables((), (), (), (spec,))


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_invalid_timestamp_name_is_rejected_in_every_scope(scope: str) -> None:
    spec = table(
        "timestamp_checks",
        (column("measured_at", ColumnType.TIMESTAMP, "Instant in UTC."),),
    )
    with pytest.raises(SchemaError, match="_utc or _local"):
        if scope == "document":
            resolve_tables((producer("core.valid", spec),), (), (), ())
        elif scope == "computed":
            resolve_tables((), (producer("core.valid", spec),), (), ())
        elif scope == "corpus":
            resolve_tables((), (), (producer("core.valid", spec),), ())
        else:
            resolve_tables((), (), (), (spec,))


def test_explicit_page_key_is_preserved_for_corpus_and_bookkeeping() -> None:
    corpus = table("corpus_keys", (column("page_key"), column("value")))
    bookkeeping = table("index_custom", (column("page_key"), column("value")))
    resolved = resolve_tables(
        (), (), (producer("derived.keys", corpus),), (bookkeeping,)
    )
    assert [item.name for item in resolved[0].columns] == ["page_key", "value"]
    assert [item.name for item in resolved[1].columns] == ["page_key", "value"]


@pytest.mark.parametrize("scope", ["document", "computed"])
def test_declared_page_key_is_rejected_for_per_page_tables(scope: str) -> None:
    per_page = producer("core.valid", table(columns=(column("page_key"),)))
    with pytest.raises(SchemaError, match="page_key"):
        if scope == "document":
            resolve_tables((per_page,), (), (), ())
        else:
            resolve_tables((), (per_page,), (), ())


@pytest.mark.parametrize(
    ("spec", "scope"),
    [
        (table(description="   "), "table"),
        (table(columns=(column(description=""),)), "column"),
    ],
    ids=["empty-table-description", "empty-column-description"],
)
def test_empty_descriptions_are_rejected(spec: TableSpec, scope: str) -> None:
    with pytest.raises(SchemaError, match=scope):
        resolve_tables((producer("core.valid", spec),), (), (), ())


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_whitespace_only_column_description_is_rejected_in_every_scope(
    scope: str,
) -> None:
    invalid = table(columns=(column("status", description=" \t\n "),))
    with pytest.raises(SchemaError, match="column"):
        resolve_single_table(scope, invalid)


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_column_validation_applies_in_every_scope(scope: str) -> None:
    invalid = table("invalid_values", (column("badName"),))
    with pytest.raises(SchemaError, match="column"):
        if scope == "document":
            resolve_tables((producer("core.valid", invalid),), (), (), ())
        elif scope == "computed":
            resolve_tables((), (producer("core.valid", invalid),), (), ())
        elif scope == "corpus":
            resolve_tables((), (), (producer("core.valid", invalid),), ())
        else:
            resolve_tables((), (), (), (invalid,))


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_table_description_validation_applies_in_every_scope(scope: str) -> None:
    invalid = table("invalid_values", description=" \t\n ")
    with pytest.raises(SchemaError, match="table"):
        if scope == "document":
            resolve_tables((producer("core.valid", invalid),), (), (), ())
        elif scope == "computed":
            resolve_tables((), (producer("core.valid", invalid),), (), ())
        elif scope == "corpus":
            resolve_tables((), (), (producer("core.valid", invalid),), ())
        else:
            resolve_tables((), (), (), (invalid,))


def test_unit_suffix_requires_its_unit_in_the_description() -> None:
    invalid = table(
        columns=(column("avg_heart_rate_bpm", description="Average heart rate."),)
    )
    with pytest.raises(SchemaError, match="beats per minute"):
        resolve_tables((producer("core.valid", invalid),), (), (), ())


@pytest.mark.parametrize(
    ("name", "kind", "description"),
    [
        ("duration_s", ColumnType.DOUBLE, "Duration in milliseconds."),
        ("distance_m", ColumnType.DOUBLE, "Distance in millimetres."),
        ("start_local", ColumnType.TIMESTAMP, "Timestamp in locale time."),
    ],
)
def test_misleading_unit_substrings_are_rejected(
    name: str, kind: ColumnType, description: str
) -> None:
    invalid = table("unit_checks", (column(name, kind, description),))
    with pytest.raises(SchemaError, match="unit"):
        resolve_tables((producer("core.valid", invalid),), (), (), ())


@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
@pytest.mark.parametrize("suffix,unit", UNIT_SUFFIXES)
def test_every_unit_suffix_requires_its_complete_unit_phrase(
    scope: str, suffix: str, unit: str
) -> None:
    name = f"measurement{suffix}"
    valid = table(
        "unit_checks",
        (column(name, ColumnType.DOUBLE, f"Measured in {unit.upper()}!"),),
    )
    resolved = resolve_single_table(scope, valid)
    assert resolved[0].columns[-1].name == name

    invalid = table(
        "unit_checks", (column(name, ColumnType.DOUBLE, "Measured quantity."),)
    )
    with pytest.raises(SchemaError, match="unit"):
        resolve_single_table(scope, invalid)


def test_s_per_km_suffix_is_matched_before_km() -> None:
    assert _matching_unit_suffix("avg_pace_s_per_km") == (
        "_s_per_km",
        "seconds per kilometre",
    )
    pace = table(
        "pace_metrics",
        (
            column(
                "avg_pace_s_per_km",
                ColumnType.DOUBLE,
                "Average pace in seconds per kilometre.",
            ),
        ),
    )
    resolved = resolve_tables((producer("core.valid", pace),), (), (), ())
    assert [spec.name for spec in resolved[0].columns] == [
        "page_key",
        "avg_pace_s_per_km",
    ]


def test_kn_m_suffix_is_matched_before_m() -> None:
    assert _matching_unit_suffix("leg_spring_stiffness_kn_m") == (
        "_kn_m",
        "kilonewtons per metre",
    )
    stiffness = table(
        "stiffness_metrics",
        (
            column(
                "leg_spring_stiffness_kn_m",
                ColumnType.DOUBLE,
                "Leg spring stiffness in kilonewtons per metre.",
            ),
        ),
    )
    resolved = resolve_tables((producer("core.valid", stiffness),), (), (), ())
    assert [spec.name for spec in resolved[0].columns] == [
        "page_key",
        "leg_spring_stiffness_kn_m",
    ]


def test_timestamp_columns_name_utc_or_local_time() -> None:
    invalid = table(
        columns=(column("measured_at", ColumnType.TIMESTAMP, "Instant in UTC."),)
    )
    with pytest.raises(SchemaError, match="_utc or _local"):
        resolve_tables((producer("core.valid", invalid),), (), (), ())


@pytest.mark.parametrize(
    ("name", "description"),
    [("created_utc", "Creation timestamp."), ("start_local", "Start timestamp.")],
)
@pytest.mark.parametrize("scope", ["document", "computed", "corpus", "bookkeeping"])
def test_timestamp_description_names_its_time_basis(
    name: str, description: str, scope: str
) -> None:
    invalid = table(columns=(column(name, ColumnType.TIMESTAMP, description),))
    with pytest.raises(SchemaError, match="unit"):
        resolve_single_table(scope, invalid)


def test_timestamp_descriptions_name_their_utc_or_local_basis() -> None:
    valid = table(
        columns=(
            column("start_utc", ColumnType.TIMESTAMP, "Activity start instant in UTC."),
            column("start_local", ColumnType.TIMESTAMP, "Local wall-clock start time."),
        )
    )
    resolved = resolve_tables((producer("core.valid", valid),), (), (), ())
    assert [spec.name for spec in resolved[0].columns] == [
        "page_key",
        "start_utc",
        "start_local",
    ]


def test_schema_manifest_sorts_tables_and_preserves_declared_column_order() -> None:
    tables = (
        ResolvedTable(
            "core.zed",
            TableScope.DOCUMENT,
            "zeta",
            "Zeta table.",
            (
                column("page_key"),
                column("second", ColumnType.INTEGER, "Second value."),
                column("first", ColumnType.VARCHAR, "First value."),
            ),
        ),
        ResolvedTable(
            "core.alpha",
            TableScope.CORPUS,
            "alpha",
            "Alpha table.",
            (column("identifier"),),
        ),
    )
    expected = (
        ("alpha", (("identifier", "VARCHAR"),)),
        (
            "zeta",
            (("page_key", "VARCHAR"), ("second", "INTEGER"), ("first", "VARCHAR")),
        ),
    )
    manifest = schema_manifest(tables)
    assert manifest == expected
    canonical_json = json.dumps(expected, separators=(",", ":"))
    assert (
        schema_digest(tables)
        == hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    )


def test_description_changes_do_not_change_manifest_or_digest() -> None:
    original = ResolvedTable(
        "core.documents",
        TableScope.DOCUMENT,
        "pages",
        "One row per workout page.",
        (
            PAGE_KEY_COLUMN,
            column("duration_s", ColumnType.DOUBLE, "Duration in seconds."),
        ),
    )
    changed = replace(
        original,
        description="Different table description.",
        columns=(
            PAGE_KEY_COLUMN,
            column("duration_s", ColumnType.DOUBLE, "Elapsed seconds."),
        ),
    )
    assert schema_manifest((original,)) == schema_manifest((changed,))
    assert schema_digest((original,)) == schema_digest((changed,))


def test_column_type_changes_change_the_schema_digest() -> None:
    varchar_table = ResolvedTable(
        "core.documents",
        TableScope.DOCUMENT,
        "pages",
        "Pages.",
        (column("status", ColumnType.VARCHAR, "State label."),),
    )
    integer_table = replace(
        varchar_table,
        columns=(column("status", ColumnType.INTEGER, "State label."),),
    )
    assert schema_digest((varchar_table,)) != schema_digest((integer_table,))


def test_schema_digest_is_independent_of_input_table_order() -> None:
    first = ResolvedTable(
        "core.first", TableScope.CORPUS, "alpha", "Alpha.", (column(),)
    )
    second = ResolvedTable(
        "core.second", TableScope.CORPUS, "zeta", "Zeta.", (column(),)
    )
    assert schema_digest((first, second)) == schema_digest((second, first))


@pytest.mark.parametrize(
    ("instance", "attribute", "replacement"),
    (
        (column(), "name", "changed"),
        (table(), "name", "changed"),
        (
            ResolvedTable("core.test", TableScope.CORPUS, "test", "Test.", (column(),)),
            "name",
            "changed",
        ),
    ),
)
def test_schema_contract_dataclasses_are_frozen(
    instance: object, attribute: str, replacement: object
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, attribute, replacement)


@pytest.mark.parametrize(
    ("instance", "attribute", "replacement"),
    (
        (IndexMeta(1, None, "duckdb", "/data", "fingerprint"), "schema_version", 2),
        (
            PageState("key", "page.md", "document", None, ComputedState.COMPUTED),
            "path",
            "other.md",
        ),
        (
            Bookkeeping(IndexMeta(1, None, "duckdb", "/data", "fp"), {}, {}),
            "meta",
            None,
        ),
    ),
)
def test_bookkeeping_contract_dataclasses_are_frozen(
    instance: object, attribute: str, replacement: object
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(instance, attribute, replacement)


# Task 3.3: registered schema, model drift, and registry extension seam.


def _registered_tables() -> tuple[ResolvedTable, ...]:
    from fitdocs.index.registry import registered_tables

    return registered_tables()


def _assert_model_field_columns(
    resolved: ResolvedTable,
    model: type[Any],
    *,
    excluded: frozenset[str] = frozenset(),
    leading: tuple[str, ...] = (),
) -> None:
    actual = tuple(column.name for column in resolved.columns[1:])
    expected = (
        *leading,
        *(field.name for field in fields(model) if field.name not in excluded),
    )
    assert actual == expected


def test_registered_tables_pin_schema_and_model_fields() -> None:
    resolution_error: SchemaError | None = None
    resolved: tuple[ResolvedTable, ...] = ()
    try:
        resolved = _registered_tables()
    except SchemaError as error:
        resolution_error = error
    assert resolution_error is None, "registered table descriptions must validate"
    by_name = {item.name: item for item in resolved}
    assert tuple(item.name for item in resolved) == (
        "index_meta",
        "index_pages",
        "index_producers",
        "pages",
        "page_sources",
        "loads",
        "quality_flags",
        "activities",
        "records",
        "laps",
        "strength_sets",
        "zone_times",
        "channel_sources",
        "mean_max",
        "load_series",
        "daily_load",
        "weekly_load",
        "benchmarks",
        "benchmark_periods",
        "blocks",
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    )
    assert len(by_name) == 24
    assert tuple(item.scope for item in resolved[:3]) == (
        TableScope.BOOKKEEPING,
        TableScope.BOOKKEEPING,
        TableScope.BOOKKEEPING,
    )
    assert all(item.scope is TableScope.DOCUMENT for item in resolved[3:7])
    assert all(item.scope is TableScope.COMPUTED for item in resolved[7:14])
    assert all(item.scope is TableScope.CORPUS for item in resolved[14:])
    assert all(item.columns[0].name == "page_key" for item in resolved[3:14])

    for item in resolved:
        assert item.description.strip()
        for column_spec in item.columns:
            assert column_spec.description.strip()
            suffix = _matching_unit_suffix(column_spec.name)
            if suffix is not None:
                assert _contains_unit_phrase(column_spec.description, suffix[1])

    records = by_name["records"]
    _assert_model_field_columns(
        records,
        Samples,
        excluded=frozenset({"time_s"}),
        leading=("sample_index", "time_utc", "elapsed_s"),
    )

    @dataclass(frozen=True)
    class SamplesWithAddedChannel(Samples):
        test_only_channel: tuple[float | None, ...] = ()

    with pytest.raises(AssertionError):
        _assert_model_field_columns(
            records,
            SamplesWithAddedChannel,
            excluded=frozenset({"time_s"}),
            leading=("sample_index", "time_utc", "elapsed_s"),
        )

    activity_columns = tuple(
        column_spec.name for column_spec in by_name["activities"].columns
    )
    metric_columns = activity_columns[7:-1]
    excluded_metrics = frozenset(
        {"hr_time_in_zone_s", "power_time_in_zone_s", "pace_time_in_zone_s"}
    )
    assert metric_columns == tuple(
        field.name
        for field in fields(DerivedMetrics)
        if field.name not in excluded_metrics
    )

    lap_renames = {
        "start_time": "start_utc",
        "start_index": "start_sample",
        "end_index": "end_sample",
    }
    assert tuple(column_spec.name for column_spec in by_name["laps"].columns[1:]) == (
        "lap_index",
        *(lap_renames.get(field.name, field.name) for field in fields(Lap)),
    )
    set_renames = {"start_time": "start_utc"}
    assert tuple(
        column_spec.name for column_spec in by_name["strength_sets"].columns[1:]
    ) == (
        "set_index",
        *(
            set_renames.get(field.name, field.name)
            for field in fields(StrengthSet)
            if field.name != "message_index"
        ),
    )


def test_registry_forwards_all_producer_tuples_and_bookkeeping_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitdocs.index.registry as registry
    from fitdocs.index.core.computed import CORE_COMPUTED
    from fitdocs.index.core.documents import CORE_DOCUMENTS
    from fitdocs.index.derived.benchmarks import BENCHMARK_PRODUCER
    from fitdocs.index.derived.blocks import BLOCK_PRODUCER
    from fitdocs.index.derived.load_series import LOAD_SERIES_PRODUCER
    from fitdocs.index.derived.mean_max import MEAN_MAX_PRODUCER

    assert registry.DOCUMENT_PRODUCERS == (CORE_DOCUMENTS,)
    assert registry.COMPUTED_PRODUCERS == (CORE_COMPUTED, MEAN_MAX_PRODUCER)
    assert registry.CORPUS_PRODUCERS == (
        LOAD_SERIES_PRODUCER,
        BENCHMARK_PRODUCER,
        BLOCK_PRODUCER,
    )
    assert tuple(item.name for item in registry.registered_tables()) == (
        "index_meta",
        "index_pages",
        "index_producers",
        "pages",
        "page_sources",
        "loads",
        "quality_flags",
        "activities",
        "records",
        "laps",
        "strength_sets",
        "zone_times",
        "channel_sources",
        "mean_max",
        "load_series",
        "daily_load",
        "weekly_load",
        "benchmarks",
        "benchmark_periods",
        "blocks",
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    )

    document_first = producer(
        "probe.document.alpha",
        table(
            "z_doc",
            (
                column("z_enabled", ColumnType.BOOLEAN, "Document z enabled."),
                column("z_label", ColumnType.VARCHAR, "Document z label."),
            ),
            "Document z table.",
        ),
        table(
            "a_doc",
            (
                column("a_count", ColumnType.BIGINT, "Document a count."),
                column("a_note", ColumnType.VARCHAR, "Document a note."),
            ),
            "Document a table.",
        ),
    )
    document_second = producer(
        "probe.document.beta",
        table(
            "m_doc",
            (
                column("m_day", ColumnType.DATE, "Document m day."),
                column("m_value", ColumnType.DOUBLE, "Document m value."),
            ),
            "Document m table.",
        ),
        table(
            "b_doc",
            (
                column("b_tags", ColumnType.VARCHAR_LIST, "Document b tags."),
                column("b_ready", ColumnType.BOOLEAN, "Document b ready."),
            ),
            "Document b table.",
        ),
    )
    computed_first = producer(
        "probe.computed.alpha",
        table(
            "z_computed",
            (
                column("z_rate", ColumnType.DOUBLE, "Computed z rate."),
                column("z_valid", ColumnType.BOOLEAN, "Computed z validity."),
            ),
            "Computed z table.",
        ),
        table(
            "a_computed",
            (
                column("a_index", ColumnType.INTEGER, "Computed a index."),
                column("a_text", ColumnType.VARCHAR, "Computed a text."),
            ),
            "Computed a table.",
        ),
    )
    computed_second = producer(
        "probe.computed.beta",
        table(
            "m_computed",
            (
                column("m_day", ColumnType.DATE, "Computed m day."),
                column("m_amount", ColumnType.BIGINT, "Computed m amount."),
            ),
            "Computed m table.",
        ),
        table(
            "b_computed",
            (
                column("b_values", ColumnType.VARCHAR_LIST, "Computed b values."),
                column("b_score", ColumnType.DOUBLE, "Computed b score."),
            ),
            "Computed b table.",
        ),
    )
    corpus_first = producer(
        "probe.corpus.alpha",
        table(
            "z_corpus",
            (
                column("z_total", ColumnType.BIGINT, "Corpus z total."),
                column("z_live", ColumnType.BOOLEAN, "Corpus z live."),
            ),
            "Corpus z table.",
        ),
        table(
            "a_corpus",
            (
                column("a_day", ColumnType.DATE, "Corpus a day."),
                column("a_ratio", ColumnType.DOUBLE, "Corpus a ratio."),
            ),
            "Corpus a table.",
        ),
    )
    corpus_second = producer(
        "probe.corpus.beta",
        table(
            "m_corpus",
            (
                column("m_label", ColumnType.VARCHAR, "Corpus m label."),
                column("m_count", ColumnType.INTEGER, "Corpus m count."),
            ),
            "Corpus m table.",
        ),
        table(
            "b_corpus",
            (
                column("b_codes", ColumnType.VARCHAR_LIST, "Corpus b codes."),
                column("b_score", ColumnType.DOUBLE, "Corpus b score."),
            ),
            "Corpus b table.",
        ),
    )
    bookkeeping_z = table(
        "index_z_probe",
        (
            column("z_number", ColumnType.INTEGER, "Bookkeeping z number."),
            column("z_text", ColumnType.VARCHAR, "Bookkeeping z text."),
        ),
        "Bookkeeping z table.",
    )
    bookkeeping_a = table(
        "index_a_probe",
        (
            column("a_active", ColumnType.BOOLEAN, "Bookkeeping a active."),
            column("a_date", ColumnType.DATE, "Bookkeeping a date."),
        ),
        "Bookkeeping a table.",
    )

    monkeypatch.setattr(
        registry,
        "DOCUMENT_PRODUCERS",
        (document_first, document_second),
    )
    monkeypatch.setattr(
        registry,
        "COMPUTED_PRODUCERS",
        (computed_first, computed_second),
    )
    monkeypatch.setattr(
        registry,
        "CORPUS_PRODUCERS",
        (corpus_first, corpus_second),
    )
    monkeypatch.setattr(
        registry,
        "BOOKKEEPING_TABLES",
        (bookkeeping_z, bookkeeping_a),
    )

    literal_page_key = ColumnSpec(
        "page_key",
        ColumnType.VARCHAR,
        "Key of the workout page: the SHA-256 (64 hex) of the page's base file, "
        "the last file its sources list.",
    )
    extended = registry.registered_tables()
    expected = (
        ResolvedTable(
            "bookkeeping",
            TableScope.BOOKKEEPING,
            "index_z_probe",
            "Bookkeeping z table.",
            (
                column("z_number", ColumnType.INTEGER, "Bookkeeping z number."),
                column("z_text", ColumnType.VARCHAR, "Bookkeeping z text."),
            ),
        ),
        ResolvedTable(
            "bookkeeping",
            TableScope.BOOKKEEPING,
            "index_a_probe",
            "Bookkeeping a table.",
            (
                column("a_active", ColumnType.BOOLEAN, "Bookkeeping a active."),
                column("a_date", ColumnType.DATE, "Bookkeeping a date."),
            ),
        ),
        ResolvedTable(
            "probe.document.alpha",
            TableScope.DOCUMENT,
            "z_doc",
            "Document z table.",
            (
                literal_page_key,
                column("z_enabled", ColumnType.BOOLEAN, "Document z enabled."),
                column("z_label", ColumnType.VARCHAR, "Document z label."),
            ),
        ),
        ResolvedTable(
            "probe.document.alpha",
            TableScope.DOCUMENT,
            "a_doc",
            "Document a table.",
            (
                literal_page_key,
                column("a_count", ColumnType.BIGINT, "Document a count."),
                column("a_note", ColumnType.VARCHAR, "Document a note."),
            ),
        ),
        ResolvedTable(
            "probe.document.beta",
            TableScope.DOCUMENT,
            "m_doc",
            "Document m table.",
            (
                literal_page_key,
                column("m_day", ColumnType.DATE, "Document m day."),
                column("m_value", ColumnType.DOUBLE, "Document m value."),
            ),
        ),
        ResolvedTable(
            "probe.document.beta",
            TableScope.DOCUMENT,
            "b_doc",
            "Document b table.",
            (
                literal_page_key,
                column("b_tags", ColumnType.VARCHAR_LIST, "Document b tags."),
                column("b_ready", ColumnType.BOOLEAN, "Document b ready."),
            ),
        ),
        ResolvedTable(
            "probe.computed.alpha",
            TableScope.COMPUTED,
            "z_computed",
            "Computed z table.",
            (
                literal_page_key,
                column("z_rate", ColumnType.DOUBLE, "Computed z rate."),
                column("z_valid", ColumnType.BOOLEAN, "Computed z validity."),
            ),
        ),
        ResolvedTable(
            "probe.computed.alpha",
            TableScope.COMPUTED,
            "a_computed",
            "Computed a table.",
            (
                literal_page_key,
                column("a_index", ColumnType.INTEGER, "Computed a index."),
                column("a_text", ColumnType.VARCHAR, "Computed a text."),
            ),
        ),
        ResolvedTable(
            "probe.computed.beta",
            TableScope.COMPUTED,
            "m_computed",
            "Computed m table.",
            (
                literal_page_key,
                column("m_day", ColumnType.DATE, "Computed m day."),
                column("m_amount", ColumnType.BIGINT, "Computed m amount."),
            ),
        ),
        ResolvedTable(
            "probe.computed.beta",
            TableScope.COMPUTED,
            "b_computed",
            "Computed b table.",
            (
                literal_page_key,
                column("b_values", ColumnType.VARCHAR_LIST, "Computed b values."),
                column("b_score", ColumnType.DOUBLE, "Computed b score."),
            ),
        ),
        ResolvedTable(
            "probe.corpus.alpha",
            TableScope.CORPUS,
            "z_corpus",
            "Corpus z table.",
            (
                column("z_total", ColumnType.BIGINT, "Corpus z total."),
                column("z_live", ColumnType.BOOLEAN, "Corpus z live."),
            ),
        ),
        ResolvedTable(
            "probe.corpus.alpha",
            TableScope.CORPUS,
            "a_corpus",
            "Corpus a table.",
            (
                column("a_day", ColumnType.DATE, "Corpus a day."),
                column("a_ratio", ColumnType.DOUBLE, "Corpus a ratio."),
            ),
        ),
        ResolvedTable(
            "probe.corpus.beta",
            TableScope.CORPUS,
            "m_corpus",
            "Corpus m table.",
            (
                column("m_label", ColumnType.VARCHAR, "Corpus m label."),
                column("m_count", ColumnType.INTEGER, "Corpus m count."),
            ),
        ),
        ResolvedTable(
            "probe.corpus.beta",
            TableScope.CORPUS,
            "b_corpus",
            "Corpus b table.",
            (
                column("b_codes", ColumnType.VARCHAR_LIST, "Corpus b codes."),
                column("b_score", ColumnType.DOUBLE, "Corpus b score."),
            ),
        ),
    )
    assert extended == expected
