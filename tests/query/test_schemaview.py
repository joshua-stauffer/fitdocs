"""Catalog projection and deterministic schema-reference tests."""

from __future__ import annotations

import os
import time
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import cast

import pytest

from fitdocs.index import store
from fitdocs.index.corpus import LeftOutPage
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.registry import registered_tables
from fitdocs.index.schema import UNIT_SUFFIXES
from fitdocs.index.store import IndexConnection, IndexResult
from fitdocs.query import format as query_format
from fitdocs.query import sandbox, schemaview
from fitdocs.query.freshness import AthleteDrift, CorpusDrift, PageDrift
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
                    assert _description_contains_unit_word(
                        expected, column_spec.description
                    )
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


# State view (task 5.1)


def _state_fixture(tmp_path: Path) -> schemaview.IndexState:
    return schemaview.IndexState(
        database=tmp_path / 'opaque "index".duckdb',
        recorded_schema_version=17,
        reads_schema_version=29,
        fitdocs_version="fitdocs-3.7.11",
        drift=PageDrift(43, 31, 5, 7, 11),
        left_out=(
            LeftOutPage(
                "workouts/alpha.md",
                "no_base_reference",
                "archive/a",
                "SECRET_FINGERPRINT_ALPHA",
            ),
            LeftOutPage(
                "workouts/beta.md", "duplicate_base", None, "SECRET_FINGERPRINT_BETA"
            ),
        ),
        without_computed={"source_missing": 13, "source_unreadable": 19},
        athlete=AthleteDrift(23, None),
        corpus=CorpusDrift(
            ("weekly_load", "power_curve"),
            (("derived-a", "ValueError: one"), ("derived-b", "OSError: two")),
        ),
        rebuild_reason="schema version differs: 17 != 29",
    )


def test_render_state_text_reports_every_populated_state_field(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    text = schemaview.render_state_text(state)
    expected_fragments = (
        f"Database: {state.database}",
        "Recorded schema version: 17",
        "Read schema version: 29",
        "Written by fitdocs: fitdocs-3.7.11",
        "Pages held: 31 / workout pages: 43",
        "Added: 5",
        "Changed: 7",
        "Removed: 11",
        "Behind: true",
        "workouts/alpha.md",
        "no_base_reference",
        "archive/a",
        "workouts/beta.md: duplicate_base; collides_with: none",
        "source_missing: 13",
        "source_unreadable: 19",
        "Activities with other athlete inputs: 23",
        "weekly_load",
        "power_curve",
        "derived-a",
        "ValueError: one",
        "derived-b",
        "OSError: two",
        "schema version differs: 17 != 29",
        "fitdocs regen",
        "fitdocs index",
    )
    for fragment in expected_fragments:
        assert fragment in text
    assert "SECRET_FINGERPRINT_" not in text


def test_render_state_text_keeps_unassessed_distinct_from_zero(tmp_path: Path) -> None:
    state = schemaview.IndexState(
        database=tmp_path / "index.duckdb",
        recorded_schema_version=None,
        reads_schema_version=29,
        fitdocs_version=None,
        drift=None,
        left_out=(),
        without_computed={"computed": 0},
        athlete=AthleteDrift(None, "athlete.toml is unreadable"),
        corpus=None,
        rebuild_reason=None,
    )
    text = schemaview.render_state_text(state)
    assert "Recorded schema version: unknown" in text
    assert "Written by fitdocs: unknown" in text
    assert "Pages held: unknown" in text
    assert "Behind: unknown" in text
    assert "Activities with other athlete inputs: unassessed" in text
    assert "athlete.toml is unreadable" in text
    assert "computed: 0" in text
    assert "Rebuild reason: none" in text


def test_render_schema_json_has_exact_literal_projection(tmp_path: Path) -> None:
    import json

    state = _state_fixture(tmp_path)
    tables = (
        schemaview.CatalogTable(
            "zeta|table",
            'quote " and newline\n雪',
            (
                schemaview.CatalogColumn(
                    "power|w", "DOUBLE", "watt|unit", 'quoted "column"'
                ),
            ),
        ),
        schemaview.CatalogTable(
            "alpha",
            None,
            (schemaview.CatalogColumn("blank", "VARCHAR", None, None),),
        ),
    )
    rendered = schemaview.render_schema_json(
        state, tables, {"zeta|table": 37, "alpha": 41}
    )
    parsed = json.loads(rendered)
    assert set(parsed) == {"index", "tables"}
    index = parsed["index"]
    assert set(index) == {
        "database",
        "schema_version",
        "reads_schema_version",
        "fitdocs_version",
        "pages_held",
        "workout_pages",
        "behind",
        "added",
        "changed",
        "removed",
        "left_out",
        "without_computed",
        "athlete",
        "corpus_behind",
        "corpus_unassessed",
        "rebuild_reason",
    }
    assert set(index["left_out"][0]) == {"path", "reason", "collides_with"}
    assert set(index["athlete"]) == {"activities_other_inputs", "skipped_reason"}
    assert [set(table) for table in parsed["tables"]] == [
        {"name", "description", "rows", "columns"},
        {"name", "description", "rows", "columns"},
    ]
    assert set(parsed["tables"][0]["columns"][0]) == {
        "name",
        "type",
        "unit",
        "description",
    }
    assert set(parsed["tables"][1]["columns"][0]) == {
        "name",
        "type",
        "unit",
        "description",
    }
    assert type(index["behind"]) is bool
    assert type(index["added"]) is int
    assert parsed == {
        "index": {
            "database": str(state.database),
            "schema_version": 17,
            "reads_schema_version": 29,
            "fitdocs_version": "fitdocs-3.7.11",
            "pages_held": 31,
            "workout_pages": 43,
            "behind": True,
            "added": 5,
            "changed": 7,
            "removed": 11,
            "left_out": [
                {
                    "path": "workouts/alpha.md",
                    "reason": "no_base_reference",
                    "collides_with": "archive/a",
                },
                {
                    "path": "workouts/beta.md",
                    "reason": "duplicate_base",
                    "collides_with": None,
                },
            ],
            "without_computed": {"source_missing": 13, "source_unreadable": 19},
            "athlete": {"activities_other_inputs": 23, "skipped_reason": None},
            "corpus_behind": ["weekly_load", "power_curve"],
            "corpus_unassessed": [
                ["derived-a", "ValueError: one"],
                ["derived-b", "OSError: two"],
            ],
            "rebuild_reason": "schema version differs: 17 != 29",
        },
        "tables": [
            {
                "name": "zeta|table",
                "description": 'quote " and newline\n雪',
                "rows": 37,
                "columns": [
                    {
                        "name": "power|w",
                        "type": "DOUBLE",
                        "unit": "watt|unit",
                        "description": 'quoted "column"',
                    }
                ],
            },
            {
                "name": "alpha",
                "description": None,
                "rows": 41,
                "columns": [
                    {
                        "name": "blank",
                        "type": "VARCHAR",
                        "unit": None,
                        "description": None,
                    }
                ],
            },
        ],
    }
    assert "SECRET_FINGERPRINT_" not in rendered


def test_render_schema_json_preserves_absent_assessments_as_null(
    tmp_path: Path,
) -> None:
    import json

    state = schemaview.IndexState(
        database=tmp_path / "absent.duckdb",
        recorded_schema_version=None,
        reads_schema_version=29,
        fitdocs_version=None,
        drift=None,
        left_out=(),
        without_computed={},
        athlete=None,
        corpus=None,
        rebuild_reason=None,
    )
    index = json.loads(schemaview.render_schema_json(state, (), {}))["index"]
    assert index == {
        "database": str(state.database),
        "schema_version": None,
        "reads_schema_version": 29,
        "fitdocs_version": None,
        "pages_held": None,
        "workout_pages": None,
        "behind": None,
        "added": None,
        "changed": None,
        "removed": None,
        "left_out": [],
        "without_computed": {},
        "athlete": {"activities_other_inputs": None, "skipped_reason": None},
        "corpus_behind": None,
        "corpus_unassessed": None,
        "rebuild_reason": None,
    }
    zero = schemaview.IndexState(
        database=tmp_path / "zero.duckdb",
        recorded_schema_version=29,
        reads_schema_version=29,
        fitdocs_version="0.0.1",
        drift=PageDrift(0, 0, 0, 0, 0),
        left_out=(),
        without_computed={"computed": 0},
        athlete=AthleteDrift(0, None),
        corpus=CorpusDrift((), ()),
        rebuild_reason=None,
    )
    zero_index = json.loads(schemaview.render_schema_json(zero, (), {}))["index"]
    assert zero_index["pages_held"] == 0 and zero_index["behind"] is False
    assert zero_index["athlete"]["activities_other_inputs"] == 0
    assert zero_index["corpus_behind"] == [] and zero_index["corpus_unassessed"] == []
    assert zero_index["rebuild_reason"] is None


def test_render_schema_text_adds_counts_and_named_defect_and_clean_case(
    tmp_path: Path,
) -> None:
    state = _state_fixture(tmp_path)
    tables = (
        schemaview.CatalogTable(
            "one",
            None,
            (schemaview.CatalogColumn("absent", "INTEGER", None, None),),
        ),
        schemaview.CatalogTable(
            "decoy",
            "### `two`",
            (schemaview.CatalogColumn("decoy_value", "VARCHAR", None, "Present"),),
        ),
        schemaview.CatalogTable(
            "two",
            "Known table",
            (schemaview.CatalogColumn("known", "VARCHAR", None, "Known column"),),
        ),
    )
    text = schemaview.render_schema_text(
        state, tables, {"one": 53, "decoy": 57, "two": 59}
    )
    assert "### `one` (53 rows)" in text
    assert "### `two` (59 rows)" in text
    assert text.splitlines().count("### `two` (59 rows)") == 1
    assert "### `decoy` (57 rows)\n### `two`\n\n" in text
    assert "| decoy_value | VARCHAR |  | Present |" in text
    assert "### `two` (59 rows)\nKnown table" in text
    assert "### `one` (53 rows)\n(no description)" in text
    assert "fitdocs defect: missing descriptions for: one, one.absent" in text
    assert "| absent | INTEGER |  | (no description) |" in text
    assert "| known | VARCHAR |  | Known column |" in text
    assert text.index("Pages held:") < text.index("### `one` (53 rows)")
    clean = (
        schemaview.CatalogTable(
            "clean",
            "Described",
            (schemaview.CatalogColumn("value", "INTEGER", None, "Value"),),
        ),
    )
    clean_text = schemaview.render_schema_text(state, clean, {"clean": 61})
    assert "### `clean` (61 rows)" in clean_text
    assert "fitdocs defect" not in clean_text


def test_render_schema_text_keeps_markdown_escaping_with_counted_heading(
    tmp_path: Path,
) -> None:
    state = _state_fixture(tmp_path)
    table = schemaview.CatalogTable(
        "power|output",
        "Power | output",
        (
            schemaview.CatalogColumn(
                "power|w",
                "DOUBLE|precise",
                "watts|units",
                "Power | measured",
            ),
        ),
    )
    output = schemaview.render_schema_text(state, (table,), {"power|output": 67})
    expected = (
        "### `power\\|output` (67 rows)\n"
        "Power \\| output\n\n"
        "| Column | Type | Unit | Description |\n"
        "| --- | --- | --- | --- |\n"
        "| power\\|w | DOUBLE\\|precise | watts\\|units | Power \\| measured |"
    )
    assert output.endswith(expected)


def test_index_state_is_frozen(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    assert [field.name for field in fields(state)] == [
        "database",
        "recorded_schema_version",
        "reads_schema_version",
        "fitdocs_version",
        "drift",
        "left_out",
        "without_computed",
        "athlete",
        "corpus",
        "rebuild_reason",
    ]
    with pytest.raises(FrozenInstanceError):
        state.reads_schema_version = 30  # type: ignore[misc]


def test_render_state_text_reports_skipped_athlete_and_empty_assessed_corpus(
    tmp_path: Path,
) -> None:
    import json

    state = schemaview.IndexState(
        database=tmp_path / "skip.duckdb",
        recorded_schema_version=29,
        reads_schema_version=29,
        fitdocs_version="fitdocs-4.2.0",
        drift=PageDrift(0, 0, 0, 0, 0),
        left_out=(),
        without_computed={},
        athlete=AthleteDrift(None, "athlete file unreadable: detail-unique"),
        corpus=CorpusDrift((), ()),
        rebuild_reason=None,
    )
    text = schemaview.render_state_text(state)
    assert "Activities with other athlete inputs: unassessed" in text
    assert (
        "Athlete drift skipped reason: athlete file unreadable: detail-unique" in text
    )
    assert "Corpus tables behind: none" in text
    assert "Corpus producers unassessed:\n  none" in text
    assert "Pages held: 0 / workout pages: 0" in text
    assert "Behind: false" in text
    index = json.loads(schemaview.render_schema_json(state, (), {}))["index"]
    assert index["athlete"] == {
        "activities_other_inputs": None,
        "skipped_reason": "athlete file unreadable: detail-unique",
    }


def test_render_schema_json_delegates_the_complete_object_to_json_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    state = _state_fixture(tmp_path)
    original = query_format.json_value
    observed: list[object] = []

    def recording_json_value(value: object) -> str:
        observed.append(value)
        return original(value)

    monkeypatch.setattr(query_format, "json_value", recording_json_value)
    output = schemaview.render_schema_json(state, (), {})
    assert observed
    assert isinstance(observed[0], dict)
    assert set(observed[0]) == {"index", "tables"}
    assert json.loads(output)["index"]["reads_schema_version"] == 29


def test_state_json_assessed_zero_values_are_typed_and_complete(tmp_path: Path) -> None:
    import json

    state = schemaview.IndexState(
        tmp_path / "zero.duckdb",
        29,
        31,
        "writer-5.1",
        PageDrift(0, 0, 0, 0, 0),
        (),
        {"source_missing": 0},
        AthleteDrift(0, None),
        CorpusDrift((), ()),
        None,
    )
    parsed = json.loads(schemaview.render_schema_json(state, (), {}))
    index = parsed["index"]
    for field in ("pages_held", "workout_pages", "added", "changed", "removed"):
        assert type(index[field]) is int
        assert index[field] == 0
    assert type(index["behind"]) is bool
    assert index["behind"] is False
    assert type(index["athlete"]["activities_other_inputs"]) is int
    assert index["athlete"]["activities_other_inputs"] == 0
    assert index["without_computed"] == {"source_missing": 0}
    assert type(index["without_computed"]["source_missing"]) is int
    assert index["corpus_behind"] == []
    assert index["corpus_unassessed"] == []
    assert parsed["tables"] == []


def test_populated_json_counts_are_integer_primitives(tmp_path: Path) -> None:
    import json

    table = schemaview.CatalogTable(
        "populated",
        "Populated table",
        (schemaview.CatalogColumn("value", "INTEGER", None, "Value"),),
    )
    parsed = json.loads(
        schemaview.render_schema_json(
            _state_fixture(tmp_path), (table,), {"populated": 13}
        )
    )
    index = parsed["index"]
    for field in (
        "schema_version",
        "reads_schema_version",
        "pages_held",
        "workout_pages",
        "added",
        "changed",
        "removed",
    ):
        assert type(index[field]) is int
    assert all(type(value) is int for value in index["without_computed"].values())
    assert type(index["athlete"]["activities_other_inputs"]) is int
    assert type(parsed["tables"][0]["rows"]) is int


def test_state_json_absence_is_null_and_not_assessed_empty(tmp_path: Path) -> None:
    import json

    state = schemaview.IndexState(
        tmp_path / "absent.duckdb", None, 31, None, None, (), {}, None, None, None
    )
    index = json.loads(schemaview.render_schema_json(state, (), {}))["index"]
    assert index["schema_version"] is None
    assert index["fitdocs_version"] is None
    for field in (
        "pages_held",
        "workout_pages",
        "behind",
        "added",
        "changed",
        "removed",
        "corpus_behind",
        "corpus_unassessed",
        "rebuild_reason",
    ):
        assert index[field] is None
    assert index["athlete"] == {
        "activities_other_inputs": None,
        "skipped_reason": None,
    }
    assert index["without_computed"] == {}
    assert index["left_out"] == []


def test_state_text_pins_unassessed_and_assessed_empty_lines(tmp_path: Path) -> None:
    absent = schemaview.IndexState(
        tmp_path / "absent.duckdb", None, 31, None, None, (), {}, None, None, None
    )
    absent_lines = schemaview.render_state_text(absent).splitlines()
    for line in (
        "Pages held: unknown / workout pages: unknown",
        "Behind: unknown",
        "Added: unknown",
        "Changed: unknown",
        "Removed: unknown",
        "Left-out pages: none",
        "  none",
        "Activities with other athlete inputs: unassessed",
        "Athlete drift skipped reason: unavailable",
        "Corpus tables behind: unassessed",
        "Corpus producers unassessed: unassessed",
        "Rebuild reason: none",
    ):
        assert line in absent_lines

    zero = schemaview.IndexState(
        tmp_path / "zero.duckdb",
        29,
        31,
        "writer-5.1",
        PageDrift(0, 0, 0, 0, 0),
        (),
        {},
        AthleteDrift(0, None),
        CorpusDrift((), ()),
        None,
    )
    zero_lines = schemaview.render_state_text(zero).splitlines()
    for line in (
        "Pages held: 0 / workout pages: 0",
        "Behind: false",
        "Added: 0",
        "Changed: 0",
        "Removed: 0",
        "Left-out pages: none",
        "Pages without computed values:",
        "  none",
        "Activities with other athlete inputs: 0",
        "Athlete drift skipped reason: none",
        "Corpus tables behind: none",
        "Corpus producers unassessed:",
    ):
        assert line in zero_lines


def test_corpus_text_keeps_each_unassessed_producer_with_its_reason(
    tmp_path: Path,
) -> None:
    lines = schemaview.render_state_text(_state_fixture(tmp_path)).splitlines()
    assert "  derived-a: ValueError: one" in lines
    assert "  derived-b: OSError: two" in lines


def test_schema_wrappers_preserve_supplied_order_and_zero_row_heading(
    tmp_path: Path,
) -> None:
    import json

    tables = (
        schemaview.CatalogTable(
            "zulu",
            "Last alphabetically",
            (
                schemaview.CatalogColumn("zeta", "BIGINT", "count", "First"),
                schemaview.CatalogColumn("alpha", "VARCHAR", None, "Second"),
            ),
        ),
        schemaview.CatalogTable(
            "alpha",
            "First alphabetically",
            (schemaview.CatalogColumn("only", "INTEGER", None, "Only"),),
        ),
    )
    state = _state_fixture(tmp_path)
    text = schemaview.render_schema_text(state, tables, {"zulu": 0, "alpha": 7})
    assert text.index("### `zulu` (0 rows)") < text.index("### `alpha` (7 rows)")
    parsed = json.loads(
        schemaview.render_schema_json(state, tables, {"zulu": 0, "alpha": 7})
    )
    assert [table["name"] for table in parsed["tables"]] == ["zulu", "alpha"]
    assert type(parsed["tables"][0]["rows"]) is int
    assert parsed["tables"][0]["rows"] == 0
    assert [column["name"] for column in parsed["tables"][0]["columns"]] == [
        "zeta",
        "alpha",
    ]


def test_schema_json_encoder_receives_complete_payload_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _state_fixture(tmp_path)
    tables = (
        schemaview.CatalogTable(
            "payload_table",
            "Payload description",
            (schemaview.CatalogColumn("payload_col", "INTEGER", "items", "Payload"),),
        ),
    )
    expected = {
        "index": {
            "database": str(state.database),
            "schema_version": 17,
            "reads_schema_version": 29,
            "fitdocs_version": "fitdocs-3.7.11",
            "pages_held": 31,
            "workout_pages": 43,
            "behind": True,
            "added": 5,
            "changed": 7,
            "removed": 11,
            "left_out": [
                {
                    "path": "workouts/alpha.md",
                    "reason": "no_base_reference",
                    "collides_with": "archive/a",
                },
                {
                    "path": "workouts/beta.md",
                    "reason": "duplicate_base",
                    "collides_with": None,
                },
            ],
            "without_computed": {"source_missing": 13, "source_unreadable": 19},
            "athlete": {"activities_other_inputs": 23, "skipped_reason": None},
            "corpus_behind": ["weekly_load", "power_curve"],
            "corpus_unassessed": [
                ["derived-a", "ValueError: one"],
                ["derived-b", "OSError: two"],
            ],
            "rebuild_reason": "schema version differs: 17 != 29",
        },
        "tables": [
            {
                "name": "payload_table",
                "description": "Payload description",
                "rows": 2,
                "columns": [
                    {
                        "name": "payload_col",
                        "type": "INTEGER",
                        "unit": "items",
                        "description": "Payload",
                    }
                ],
            }
        ],
    }
    original = query_format.json_value
    observed: list[object] = []
    sentinel = "encoder-result-sentinel"

    def record(value: object) -> str:
        observed.append(value)
        if len(observed) == 1:
            return sentinel
        return original(value)

    monkeypatch.setattr(query_format, "json_value", record)
    output = schemaview.render_schema_json(state, tables, {"payload_table": 2})
    assert observed[0] == expected
    assert output == sentinel


def test_json_type_and_key_ordering_controls_cover_two_columns(tmp_path: Path) -> None:
    import json

    tables = (
        schemaview.CatalogTable(
            "zulu",
            None,
            (
                schemaview.CatalogColumn("zeta", "BIGINT", "count", "First"),
                schemaview.CatalogColumn("alpha", "VARCHAR", None, None),
            ),
        ),
        schemaview.CatalogTable(
            "alpha",
            "Known",
            (schemaview.CatalogColumn("only", "INTEGER", None, "Only"),),
        ),
    )
    parsed = json.loads(
        schemaview.render_schema_json(
            _state_fixture(tmp_path), tables, {"zulu": 0, "alpha": 9}
        )
    )
    assert [table["name"] for table in parsed["tables"]] == ["zulu", "alpha"]
    assert [column["name"] for column in parsed["tables"][0]["columns"]] == [
        "zeta",
        "alpha",
    ]
    assert parsed["tables"][0]["columns"] == [
        {"name": "zeta", "type": "BIGINT", "unit": "count", "description": "First"},
        {"name": "alpha", "type": "VARCHAR", "unit": None, "description": None},
    ]


def test_render_state_text_absent_values_bind_empty_markers_to_sections(
    tmp_path: Path,
) -> None:
    database = tmp_path / "opaque.duckdb"
    state = schemaview.IndexState(
        database, None, 31, None, None, (), {}, None, None, None
    )
    expected = [
        f"Database: {database}",
        "Recorded schema version: unknown",
        "Read schema version: 31",
        "Written by fitdocs: unknown",
        "Pages held: unknown / workout pages: unknown",
        "Behind: unknown",
        "Added: unknown",
        "Changed: unknown",
        "Removed: unknown",
        "Left-out pages: none",
        "Pages without computed values:",
        "  none",
        "Activities with other athlete inputs: unassessed",
        "Athlete drift skipped reason: unavailable",
        "Corpus tables behind: unassessed",
        "Corpus producers unassessed: unassessed",
        "Rebuild reason: none",
        "Run fitdocs regen to update workout pages and athlete inputs.",
        "Run fitdocs index to rebuild the index when it is incompatible.",
    ]
    assert schemaview.render_state_text(state).splitlines() == expected


def test_render_state_text_assessed_zero_binds_empty_markers_to_sections(
    tmp_path: Path,
) -> None:
    database = tmp_path / "opaque.duckdb"
    state = schemaview.IndexState(
        database,
        29,
        31,
        "writer",
        PageDrift(0, 0, 0, 0, 0),
        (),
        {},
        AthleteDrift(0, None),
        CorpusDrift((), ()),
        None,
    )
    expected = [
        f"Database: {database}",
        "Recorded schema version: 29",
        "Read schema version: 31",
        "Written by fitdocs: writer",
        "Pages held: 0 / workout pages: 0",
        "Behind: false",
        "Added: 0",
        "Changed: 0",
        "Removed: 0",
        "Left-out pages: none",
        "Pages without computed values:",
        "  none",
        "Activities with other athlete inputs: 0",
        "Athlete drift skipped reason: none",
        "Corpus tables behind: none",
        "Corpus producers unassessed:",
        "  none",
        "Rebuild reason: none",
        "Run fitdocs regen to update workout pages and athlete inputs.",
        "Run fitdocs index to rebuild the index when it is incompatible.",
    ]
    assert schemaview.render_state_text(state).splitlines() == expected


def _description_contains_unit_word(unit: str, description: str) -> bool:
    return unit.casefold() in description.casefold()


def test_unit_word_presence_ignores_case_and_rejects_absence() -> None:
    assert _description_contains_unit_word("seconds", "elapsed in seconds")
    assert _description_contains_unit_word("seconds", "Seconds since activity start")
    assert not _description_contains_unit_word("seconds", "Elapsed time in minutes")
