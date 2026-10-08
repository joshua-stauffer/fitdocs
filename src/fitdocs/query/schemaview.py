"""Read the live index catalog and render its schema reference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from fitdocs.index.corpus import LeftOutPage
from fitdocs.index.schema import UNIT_SUFFIXES
from fitdocs.index.store import IndexConnection
from fitdocs.query import format as query_format
from fitdocs.query.freshness import AthleteDrift, CorpusDrift, PageDrift


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


@dataclass(frozen=True)
class IndexState:
    database: Path
    recorded_schema_version: int | None
    reads_schema_version: int
    fitdocs_version: str | None
    drift: PageDrift | None
    left_out: tuple[LeftOutPage, ...]
    without_computed: Mapping[str, int]
    athlete: AthleteDrift | None
    corpus: CorpusDrift | None
    rebuild_reason: str | None


# Requirement 10.3 (regen) and 10.4 (index); Requirement 8.2 names `fitdocs index`
# as the rebuild for an incompatible index.
STATE_ADVICE: tuple[str, str] = (
    "Run fitdocs regen to bring documents and the index forward together "
    "under the current athlete profile.",
    "Run fitdocs index to bring corpus tables that are behind level, "
    "or to rebuild an incompatible index.",
)


def render_state_text(state: IndexState) -> str:
    drift = state.drift
    lines = [
        f"Database: {state.database}",
        "Recorded schema version: "
        + (
            str(state.recorded_schema_version)
            if state.recorded_schema_version is not None
            else "unknown"
        ),
        f"Read schema version: {state.reads_schema_version}",
        "Written by fitdocs: "
        + (state.fitdocs_version if state.fitdocs_version is not None else "unknown"),
        f"Pages held: {drift.pages_held if drift is not None else 'unknown'} / "
        f"workout pages: {drift.workout_pages if drift is not None else 'unknown'}",
        f"Behind: {str(drift.behind).lower() if drift is not None else 'unknown'}",
        f"Added: {drift.added if drift is not None else 'unknown'}",
        f"Changed: {drift.changed if drift is not None else 'unknown'}",
        f"Removed: {drift.removed if drift is not None else 'unknown'}",
    ]
    if state.left_out:
        lines.append("Left-out pages:")
        lines.extend(
            f"  {page.path}: {page.reason}; collides_with: "
            f"{page.collides_with if page.collides_with is not None else 'none'}"
            for page in state.left_out
        )
    else:
        lines.append("Left-out pages: none")
    lines.append("Pages without computed values:")
    lines.extend(
        f"  {status}: {count}" for status, count in state.without_computed.items()
    )
    if not state.without_computed:
        lines.append("  none")
    if state.athlete is None:
        lines.append("Activities with other athlete inputs: unassessed")
        lines.append("Athlete drift skipped reason: unavailable")
    elif state.athlete.skipped_reason is not None:
        lines.append("Activities with other athlete inputs: unassessed")
        lines.append(f"Athlete drift skipped reason: {state.athlete.skipped_reason}")
    else:
        lines.append(
            "Activities with other athlete inputs: "
            f"{state.athlete.activities_other_inputs}"
        )
        lines.append("Athlete drift skipped reason: none")
    if state.corpus is None:
        lines.extend(
            (
                "Corpus tables behind: unassessed",
                "Corpus producers unassessed: unassessed",
            )
        )
    else:
        lines.append(
            "Corpus tables behind: "
            + (", ".join(state.corpus.behind) if state.corpus.behind else "none")
        )
        lines.append("Corpus producers unassessed:")
        if state.corpus.unassessed:
            lines.extend(
                f"  {producer}: {reason}"
                for producer, reason in state.corpus.unassessed
            )
        else:
            lines.append("  none")
    lines.append(
        "Rebuild reason: "
        + (state.rebuild_reason if state.rebuild_reason is not None else "none")
    )
    lines.extend(STATE_ADVICE)
    return "\n".join(lines)


def render_schema_text(
    state: IndexState, tables: Sequence[CatalogTable], counts: Mapping[str, int]
) -> str:
    sections: list[str] = []
    for table in tables:
        heading = f"### `{_markdown(table.name)}`"
        section = render_reference((table,))
        count = counts[table.name]
        counted_heading = f"{heading} ({count} {'row' if count == 1 else 'rows'})"
        sections.append(section.replace(heading, counted_heading, 1))
    reference = "\n\n".join(sections)
    state_text = render_state_text(state)
    missing = undescribed(tables)
    if missing:
        reference += "\n\nfitdocs defect: missing descriptions for: " + ", ".join(
            missing
        )
    return state_text + ("\n\n" + reference if reference else "")


def render_schema_json(
    state: IndexState, tables: Sequence[CatalogTable], counts: Mapping[str, int]
) -> str:
    drift = state.drift
    athlete = state.athlete
    corpus = state.corpus
    index = {
        "database": str(state.database),
        "schema_version": state.recorded_schema_version,
        "reads_schema_version": state.reads_schema_version,
        "fitdocs_version": state.fitdocs_version,
        "pages_held": drift.pages_held if drift is not None else None,
        "workout_pages": drift.workout_pages if drift is not None else None,
        "behind": drift.behind if drift is not None else None,
        "added": drift.added if drift is not None else None,
        "changed": drift.changed if drift is not None else None,
        "removed": drift.removed if drift is not None else None,
        "left_out": [
            {
                "path": page.path,
                "reason": page.reason,
                "collides_with": page.collides_with,
            }
            for page in state.left_out
        ],
        "without_computed": dict(state.without_computed),
        "athlete": {
            "activities_other_inputs": athlete.activities_other_inputs
            if athlete is not None
            else None,
            "skipped_reason": athlete.skipped_reason if athlete is not None else None,
        },
        "corpus_behind": list(corpus.behind) if corpus is not None else None,
        "corpus_unassessed": [list(item) for item in corpus.unassessed]
        if corpus is not None
        else None,
        "rebuild_reason": state.rebuild_reason,
        "advice": list(STATE_ADVICE),
    }
    table_values = [
        {
            "name": table.name,
            "description": table.description,
            "rows": counts[table.name],
            "columns": [
                {
                    "name": column.name,
                    "type": column.type_name,
                    "unit": column.unit,
                    "description": column.description,
                }
                for column in table.columns
            ],
        }
        for table in tables
    ]
    return query_format.json_value({"index": index, "tables": table_values})
