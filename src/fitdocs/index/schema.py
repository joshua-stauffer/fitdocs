"""Pure schema contracts, validation and versioned schema fingerprints."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

SCHEMA_VERSION: Final[int] = 2
RESERVED_PREFIX: Final[str] = "index_"


class ColumnType(StrEnum):
    """Types supported by the portable, timezone-free index schema."""

    VARCHAR = "VARCHAR"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    DOUBLE = "DOUBLE"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    VARCHAR_LIST = "VARCHAR[]"


@dataclass(frozen=True)
class ColumnSpec:
    """A typed and described database column."""

    name: str
    type: ColumnType
    description: str


@dataclass(frozen=True)
class TableSpec:
    """An ordered set of described columns supplied by one producer."""

    name: str
    description: str
    columns: tuple[ColumnSpec, ...]


class TableScope(StrEnum):
    """Refresh tier which owns a resolved table."""

    DOCUMENT = "document"
    COMPUTED = "computed"
    CORPUS = "corpus"
    BOOKKEEPING = "bookkeeping"


@dataclass(frozen=True)
class ResolvedTable:
    """A table annotated with its owner and resolved per-page key column."""

    producer: str
    scope: TableScope
    name: str
    description: str
    columns: tuple[ColumnSpec, ...]


PAGE_KEY_COLUMN: Final[ColumnSpec] = ColumnSpec(
    name="page_key",
    type=ColumnType.VARCHAR,
    description=(
        "Key of the workout page: the SHA-256 (64 hex) of the page's base file, "
        "the last file its sources list."
    ),
)

UNIT_SUFFIXES: Final[tuple[tuple[str, str], ...]] = (
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


class SchemaError(ValueError):
    """A producer declared a table which violates the schema contract."""


class DocumentProducerLike(Protocol):
    """Structural inputs needed from a document producer before producer.py exists."""

    @property
    def name(self) -> str: ...

    @property
    def tables(self) -> tuple[TableSpec, ...]: ...


class ComputedProducerLike(Protocol):
    """Structural inputs needed from a computed producer before producer.py exists."""

    @property
    def name(self) -> str: ...

    @property
    def tables(self) -> tuple[TableSpec, ...]: ...


class CorpusProducerLike(Protocol):
    """Structural inputs needed from a corpus producer before producer.py exists."""

    @property
    def name(self) -> str: ...

    @property
    def tables(self) -> tuple[TableSpec, ...]: ...


_SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z", re.ASCII)


def _matching_unit_suffix(column_name: str) -> tuple[str, str] | None:
    """Return the most specific documented unit suffix for a column name."""
    for suffix, unit in UNIT_SUFFIXES:
        if column_name.endswith(suffix):
            return suffix, unit
    return None


def _contains_unit_phrase(description: str, unit: str) -> bool:
    """Match unit words as complete, consecutive words, ignoring case."""
    description_words = re.findall(r"[^\W_]+", description.casefold())
    unit_words = re.findall(r"[^\W_]+", unit.casefold())
    width = len(unit_words)
    return any(
        description_words[index : index + width] == unit_words
        for index in range(len(description_words) - width + 1)
    )


def _validate_column(column: ColumnSpec, table_name: str) -> None:
    if not _SNAKE_CASE.fullmatch(column.name):
        raise SchemaError(
            f"column {column.name!r} in table {table_name!r} is not snake_case"
        )
    if not column.description.strip():
        raise SchemaError(
            f"column {column.name!r} in table {table_name!r} has an empty description"
        )

    unit_suffix = _matching_unit_suffix(column.name)
    if unit_suffix is not None:
        _, unit = unit_suffix
        if not _contains_unit_phrase(column.description, unit):
            raise SchemaError(
                f"column {column.name!r} description must name the unit {unit!r}"
            )

    if column.type is ColumnType.TIMESTAMP and not column.name.endswith(
        ("_utc", "_local")
    ):
        raise SchemaError(
            f"timestamp column {column.name!r} must end in _utc or _local"
        )


def resolve_tables(
    document: Sequence[DocumentProducerLike],
    computed: Sequence[ComputedProducerLike],
    corpus: Sequence[CorpusProducerLike],
    bookkeeping: Sequence[TableSpec],
) -> tuple[ResolvedTable, ...]:
    """Validate and order bookkeeping and producer tables for schema creation."""
    resolved: list[ResolvedTable] = []
    table_names: set[str] = set()
    producer_names: set[str] = set()

    def append_table(
        producer_name: str,
        scope: TableScope,
        spec: TableSpec,
        *,
        is_producer_table: bool,
    ) -> None:
        if not _SNAKE_CASE.fullmatch(spec.name):
            raise SchemaError(f"table {spec.name!r} is not snake_case")
        if spec.name in table_names:
            raise SchemaError(f"duplicate table name {spec.name!r}")
        table_names.add(spec.name)

        if is_producer_table and spec.name.startswith(RESERVED_PREFIX):
            raise SchemaError(
                f"producer table {spec.name!r} uses reserved prefix {RESERVED_PREFIX!r}"
            )
        if not spec.description.strip():
            raise SchemaError(f"table {spec.name!r} has an empty description")

        for column_spec in spec.columns:
            _validate_column(column_spec, spec.name)
        columns = spec.columns
        if scope in (TableScope.DOCUMENT, TableScope.COMPUTED):
            if any(column_spec.name == PAGE_KEY_COLUMN.name for column_spec in columns):
                raise SchemaError(
                    f"per-page table {spec.name!r} must not declare page_key"
                )
            columns = (PAGE_KEY_COLUMN, *columns)

        resolved.append(
            ResolvedTable(
                producer=producer_name,
                scope=scope,
                name=spec.name,
                description=spec.description,
                columns=columns,
            )
        )

    for spec in bookkeeping:
        append_table(
            "bookkeeping", TableScope.BOOKKEEPING, spec, is_producer_table=False
        )

    groups: tuple[
        tuple[
            TableScope,
            Sequence[DocumentProducerLike | ComputedProducerLike | CorpusProducerLike],
        ],
        ...,
    ] = (
        (TableScope.DOCUMENT, document),
        (TableScope.COMPUTED, computed),
        (TableScope.CORPUS, corpus),
    )
    for scope, producers in groups:
        for item in producers:
            if item.name in producer_names:
                raise SchemaError(f"duplicate producer name {item.name!r}")
            producer_names.add(item.name)
            for spec in item.tables:
                append_table(item.name, scope, spec, is_producer_table=True)

    return tuple(resolved)


def schema_manifest(
    tables: Sequence[ResolvedTable],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Return table names, ordered column names and types, without descriptions."""
    return tuple(
        sorted(
            (
                (
                    table.name,
                    tuple((column.name, column.type.value) for column in table.columns),
                )
                for table in tables
            ),
            key=lambda entry: entry[0],
        )
    )


def schema_digest(tables: Sequence[ResolvedTable]) -> str:
    """Hash the canonical JSON representation of the schema manifest."""
    canonical_json = json.dumps(schema_manifest(tables), separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
