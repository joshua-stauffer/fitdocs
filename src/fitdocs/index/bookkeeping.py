"""Typed refresh bookkeeping models and their index table specifications."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec


class ComputedState(StrEnum):
    """Outcome of computing a page's archived source values."""

    COMPUTED = "computed"
    SOURCE_MISSING = "source_missing"
    SOURCE_UNREADABLE = "source_unreadable"
    SOURCE_UNDECODABLE = "source_undecodable"


@dataclass(frozen=True)
class IndexMeta:
    """Metadata describing the inputs and versions of the latest refresh."""

    schema_version: int
    fitdocs_version: str | None
    duckdb_version: str
    data_root: str
    athlete_fingerprint: str


@dataclass(frozen=True)
class PageState:
    """Last document and computed-value state retained for one page."""

    page_key: str
    path: str
    document_fingerprint: str
    render_fingerprint: str | None
    computed_state: ComputedState


@dataclass(frozen=True)
class Bookkeeping:
    """The complete pass-owned metadata, page states and producer fingerprints."""

    meta: IndexMeta
    pages: Mapping[str, PageState]
    producers: Mapping[str, str | None]


BOOKKEEPING_TABLES: Final[tuple[TableSpec, ...]] = (
    TableSpec(
        name="index_meta",
        description="Metadata recorded by the most recent index refresh.",
        columns=(
            ColumnSpec(
                "schema_version", ColumnType.INTEGER, "Schema version of this index."
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
                "SHA-256 fingerprint of athlete inputs current at the last refresh.",
            ),
        ),
    ),
    TableSpec(
        name="index_pages",
        description="Document and computed-value bookkeeping "
        "for each indexed workout page.",
        columns=(
            ColumnSpec(
                "page_key", ColumnType.VARCHAR, "SHA-256 key of the page's base file."
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
        name="index_producers",
        description="Producer registrations and corpus fingerprints "
        "recorded by the index.",
        columns=(
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
