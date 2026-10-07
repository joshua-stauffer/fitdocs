"""Read the live index catalog and render its schema reference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fitdocs.index.schema import UNIT_SUFFIXES
from fitdocs.index.store import IndexConnection


@dataclass(frozen=True)
class CatalogColumn:
    name: str
    type_name: str
    unit: str | None
    description: str | None


@dataclass(frozen=True)
class CatalogTable:
    name: str
    description: str | None
    columns: tuple[CatalogColumn, ...]


def _normalized_comment(comment: object) -> str | None:
    if comment is None:
        return None
    value = str(comment)
    return value if value.strip() else None


def _markdown(value: str) -> str:
    return value.replace("|", r"\|")


def read_catalog(conn: IndexConnection) -> tuple[CatalogTable, ...]:
    table_rows = conn.execute(
        "SELECT table_name, comment FROM duckdb_tables() "
        "WHERE database_name = current_database() AND schema_name = 'main' "
        "AND NOT temporary"
    ).fetchall()
    column_rows = conn.execute(
        "SELECT table_name, column_name, data_type, comment "
        "FROM duckdb_columns() "
        "WHERE database_name = current_database() AND schema_name = 'main' "
        "ORDER BY table_name, column_index"
    ).fetchall()
    descriptions = {
        str(name): _normalized_comment(comment) for name, comment in table_rows
    }
    columns: dict[str, list[CatalogColumn]] = {}
    for table_name, column_name, type_name, comment in column_rows:
        name = str(table_name)
        columns.setdefault(name, []).append(
            CatalogColumn(
                str(column_name),
                str(type_name),
                unit_of(str(column_name)),
                _normalized_comment(comment),
            )
        )
    names = sorted(descriptions, key=lambda name: (name.startswith("index_"), name))
    return tuple(
        CatalogTable(name, descriptions[name], tuple(columns.get(name, ())))
        for name in names
    )


def row_counts(
    conn: IndexConnection, tables: Sequence[CatalogTable]
) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        quoted_name = table.name.replace('"', '""')
        result = conn.execute(f'SELECT count(*) FROM "{quoted_name}"').fetchall()
        counts[table.name] = int(str(result[0][0]))
    return counts


def unit_of(column_name: str) -> str | None:
    for suffix, unit in UNIT_SUFFIXES:
        if column_name.endswith(suffix):
            return unit
    return None


def undescribed(tables: Sequence[CatalogTable]) -> tuple[str, ...]:
    missing: list[str] = []
    for table in tables:
        if table.description is None:
            missing.append(table.name)
        missing.extend(
            f"{table.name}.{column.name}"
            for column in table.columns
            if column.description is None
        )
    return tuple(missing)


def render_reference(tables: Sequence[CatalogTable]) -> str:
    sections: list[str] = []
    for table in tables:
        description = _markdown(table.description or "(no description)")
        lines = [
            f"### `{_markdown(table.name)}`",
            description,
            "",
            "| Column | Type | Unit | Description |",
            "| --- | --- | --- | --- |",
        ]
        lines.extend(
            "| "
            + " | ".join(
                (
                    _markdown(column.name),
                    _markdown(column.type_name),
                    _markdown(column.unit or ""),
                    _markdown(column.description or "(no description)"),
                )
            )
            + " |"
            for column in table.columns
        )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)
