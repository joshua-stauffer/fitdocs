"""Catalog projection and deterministic schema-reference tests."""

from __future__ import annotations

import os
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from fitdocs.index import store
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.registry import registered_tables
from fitdocs.index.schema import UNIT_SUFFIXES
from fitdocs.index.store import IndexConnection, IndexResult
from fitdocs.query import sandbox, schemaview
from tests.query._helpers import plain_database, schema_only_index
from tests.query.conftest import HomeDirectory


@pytest.fixture
def catalog_location(tmp_path: Path, home_dir: HomeDirectory) -> IndexLocation:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n", encoding="utf-8"
    )
    index_base = tmp_path / "index-cache"
    location = resolve_index_location(
        data_root,
        {"FITDOCS_INDEX_DIR": str(index_base)},
        home_dir.path,
    )
    location.directory.mkdir(parents=True)
    return location


def _open_catalog(location: IndexLocation) -> IndexConnection:
    return sandbox.open_sandboxed(
        location,
        pid=os.getpid(),
        monotonic=time.monotonic,
        sleep=time.sleep,
        on_wait=lambda _: None,
    )


class _RecordingConnection:
    def __init__(self, connection: IndexConnection) -> None:
        self.connection = connection
        self.statements: list[str] = []

    def execute(self, sql: str) -> IndexResult:
        self.statements.append(sql)
        return self.connection.execute(sql)


def test_read_catalog_excludes_system_views_and_temporary_tables(
    catalog_location: IndexLocation, home_dir: HomeDirectory
) -> None:
    database = schema_only_index(catalog_location.database)
    assert database == catalog_location.database
    connection = _open_catalog(catalog_location)
    try:
        system_views = connection.execute(
            "SELECT database_name, schema_name, view_name FROM duckdb_views() "
            "WHERE database_name != current_database() AND schema_name = 'main' "
            "ORDER BY database_name, view_name"
        ).fetchall()
        assert system_views

        connection.execute(
            "CREATE TEMP TABLE query_catalog_temp_positive (value INTEGER)"
        )
        temp_control = connection.execute(
            "SELECT table_name, temporary FROM duckdb_tables() "
            "WHERE table_name = 'query_catalog_temp_positive'"
        ).fetchall()
        assert temp_control == [("query_catalog_temp_positive", True)]

        recording = _RecordingConnection(connection)
        tables = schemaview.read_catalog(cast(IndexConnection, recording))
        assert len(recording.statements) == 2
        assert all(
            "database_name = current_database()" in statement
            and "schema_name = 'main'" in statement
            for statement in recording.statements
        )
        assert "NOT temporary" in recording.statements[0]
        assert "ORDER BY table_name, column_index" in recording.statements[1]
        names = tuple(table.name for table in tables)
        declared = registered_tables()
        expected_names = tuple(
            sorted(
                (table.name for table in declared),
                key=lambda name: (name.startswith("index_"), name),
            )
        )
        assert names == expected_names
        assert "query_catalog_temp_positive" not in names
        system_view_names = {row[2] for row in system_views}
        assert all(table.name not in system_view_names for table in tables)
        by_name = {table.name: table for table in tables}
        for spec in declared:
            table = by_name[spec.name]
            assert table.description == spec.description
            assert tuple(column.name for column in table.columns) == tuple(
                column.name for column in spec.columns
            )
            assert tuple(column.type_name for column in table.columns) == tuple(
                column.type.value for column in spec.columns
            )
            assert tuple(column.description for column in table.columns) == tuple(
                column.description for column in spec.columns
            )
    finally:
        connection.close()
    home_dir.assert_untouched()


def test_units_match_registered_columns_and_longest_fixed_suffixes(
    catalog_location: IndexLocation, home_dir: HomeDirectory
) -> None:
    schema_only_index(catalog_location.database)
    connection = _open_catalog(catalog_location)
    try:
        catalog = {table.name: table for table in schemaview.read_catalog(connection)}
        declared = registered_tables()
        unit_columns = 0
        for table_spec in declared:
            catalog_columns = {
                column.name: column for column in catalog[table_spec.name].columns
            }
            for column_spec in table_spec.columns:
                expected = next(
                    (
                        unit
                        for suffix, unit in UNIT_SUFFIXES
                        if column_spec.name.endswith(suffix)
                    ),
                    None,
                )
                assert schemaview.unit_of(column_spec.name) == expected
                assert catalog_columns[column_spec.name].unit == expected
                if expected is not None:
                    unit_columns += 1
                    assert expected in column_spec.description
        assert unit_columns > 0
    finally:
        connection.close()
    assert schemaview.unit_of("pace_s_per_km") == "seconds per kilometre"
    assert schemaview.unit_of("force_kn_m") == "kilonewtons per metre"
    home_dir.assert_untouched()


def test_catalog_normalizes_blank_and_null_comments_and_quotes_row_count_names(
    catalog_location: IndexLocation, home_dir: HomeDirectory
) -> None:
    database = plain_database(
        catalog_location.database,
        'CREATE TABLE "odd""name" (value INTEGER)',
        'INSERT INTO "odd""name" VALUES (11), (23), (47)',
        'COMMENT ON TABLE "odd""name" IS \'   \'',
        'COMMENT ON COLUMN "odd""name"."value" IS \'\'',
        "CREATE TABLE bare (plain VARCHAR)",
    )
    assert database == catalog_location.database
    connection = _open_catalog(catalog_location)
    try:
        tables = schemaview.read_catalog(connection)
        by_name = {table.name: table for table in tables}
        assert set(by_name) == {"bare", 'odd"name'}
        assert by_name['odd"name'].description is None
        assert by_name['odd"name'].columns[0].description is None
        assert by_name["bare"].description is None
        assert by_name["bare"].columns[0].description is None
        assert schemaview.undescribed(tables) == (
            "bare",
            "bare.plain",
            'odd"name',
            'odd"name.value',
        )
        assert schemaview.row_counts(connection, tables) == {
            "bare": 0,
            'odd"name': 3,
        }
    finally:
        connection.close()
    home_dir.assert_untouched()


def test_catalog_reads_live_table_comment_exactly(
    catalog_location: IndexLocation, home_dir: HomeDirectory
) -> None:
    schema_only_index(catalog_location.database)
    comment = "  Live table comment | café  "
    with store.open_index(catalog_location.database, read_only=False) as writer:
        writer.execute(
            f"COMMENT ON TABLE activities IS '{comment.replace(chr(39), chr(39) * 2)}'"
        )

    connection = _open_catalog(catalog_location)
    try:
        table = next(
            table
            for table in schemaview.read_catalog(connection)
            if table.name == "activities"
        )
        assert table.description == comment
        assert comment not in {spec.description for spec in registered_tables()}
    finally:
        connection.close()
    home_dir.assert_untouched()


@pytest.mark.parametrize(
    ("column_name", "comment", "unit"),
    [
        ("distance_m", "\tLive unit-column comment with padding  ", "metres"),
        ("sport", "  Live plain-column comment café\n", None),
    ],
    ids=["unit-column", "plain-column"],
)
def test_catalog_reads_live_column_comment_exactly(
    catalog_location: IndexLocation,
    home_dir: HomeDirectory,
    column_name: str,
    comment: str,
    unit: str | None,
) -> None:
    schema_only_index(catalog_location.database)
    with store.open_index(catalog_location.database, read_only=False) as writer:
        writer.execute(
            f"COMMENT ON COLUMN activities.{column_name} IS "
            f"'{comment.replace(chr(39), chr(39) * 2)}'"
        )

    connection = _open_catalog(catalog_location)
    try:
        activities = next(
            table
            for table in schemaview.read_catalog(connection)
            if table.name == "activities"
        )
        column = next(
            column for column in activities.columns if column.name == column_name
        )
        assert column.description == comment
        assert column.unit == unit
        registered_comments = {
            registered_column.description
            for spec in registered_tables()
            for registered_column in spec.columns
        }
        assert comment not in registered_comments
    finally:
        connection.close()
    home_dir.assert_untouched()


@pytest.mark.parametrize(
    "comment",
    [None, "", "   ", "\t", "\n", "\r", "\r\n", " \t\r\n "],
    ids=["null", "empty", "spaces", "tab", "lf", "cr", "crlf", "mixed-blank"],
)
@pytest.mark.parametrize("kind", ["table", "column"])
def test_catalog_treats_all_blank_live_comments_as_missing(
    catalog_location: IndexLocation,
    home_dir: HomeDirectory,
    comment: str | None,
    kind: str,
) -> None:
    schema_only_index(catalog_location.database)
    subject = "TABLE activities" if kind == "table" else "COLUMN activities.sport"
    value = "NULL" if comment is None else "'" + comment.replace("'", "''") + "'"
    with store.open_index(catalog_location.database, read_only=False) as writer:
        writer.execute(f"COMMENT ON {subject} IS {value}")

    connection = _open_catalog(catalog_location)
    try:
        activities = next(
            table
            for table in schemaview.read_catalog(connection)
            if table.name == "activities"
        )
        if kind == "table":
            assert activities.description is None
        else:
            sport = next(
                column for column in activities.columns if column.name == "sport"
            )
            assert sport.description is None
    finally:
        connection.close()
    home_dir.assert_untouched()


def test_undescribed_lists_fixed_table_and_column_names() -> None:
    tables = (
        schemaview.CatalogTable(
            "alpha",
            "present",
            (
                schemaview.CatalogColumn("missing", "INTEGER", None, None),
                schemaview.CatalogColumn("described", "VARCHAR", None, "Known"),
            ),
        ),
        schemaview.CatalogTable(
            "beta",
            None,
            (schemaview.CatalogColumn("also_missing", "DOUBLE", None, None),),
        ),
    )
    assert schemaview.undescribed(tables) == (
        "alpha.missing",
        "beta",
        "beta.also_missing",
    )


def test_catalog_values_are_frozen() -> None:
    column = schemaview.CatalogColumn("value", "INTEGER", None, "Value")
    table = schemaview.CatalogTable("values", "Values", (column,))
    with pytest.raises(FrozenInstanceError):
        column.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        table.name = "changed"  # type: ignore[misc]


def test_render_reference_escapes_pipes_and_is_deterministic() -> None:
    tables = (
        schemaview.CatalogTable(
            "power|output",
            "Power | output",
            (
                schemaview.CatalogColumn(
                    "power|w",
                    "DOUBLE|precise",
                    "watts|units",
                    "Power | measured",
                ),
                schemaview.CatalogColumn("label", "VARCHAR", None, None),
            ),
        ),
        schemaview.CatalogTable(
            "bare",
            None,
            (schemaview.CatalogColumn("absent", "INTEGER", None, None),),
        ),
    )
    expected = (
        "### `power\\|output`\n"
        "Power \\| output\n\n"
        "| Column | Type | Unit | Description |\n"
        "| --- | --- | --- | --- |\n"
        "| power\\|w | DOUBLE\\|precise | watts\\|units | Power \\| measured |\n"
        "| label | VARCHAR |  | (no description) |\n\n"
        "### `bare`\n"
        "(no description)\n\n"
        "| Column | Type | Unit | Description |\n"
        "| --- | --- | --- | --- |\n"
        "| absent | INTEGER |  | (no description) |"
    )
    first = schemaview.render_reference(tables)
    second = schemaview.render_reference(tables)
    assert first == expected
    assert second == first


def test_schema_created_without_refresh_has_no_missing_descriptions(
    catalog_location: IndexLocation, home_dir: HomeDirectory
) -> None:
    schema_only_index(catalog_location.database)
    connection = _open_catalog(catalog_location)
    try:
        tables = schemaview.read_catalog(connection)
        assert len(tables) >= 13
        assert schemaview.undescribed(tables) == ()
    finally:
        connection.close()
    home_dir.assert_untouched()
