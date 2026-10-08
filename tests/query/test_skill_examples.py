"""Executable examples in the packaged analytics skill."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict, cast

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.index import registry
from fitdocs.index.core.computed import CORE_COMPUTED
from fitdocs.index.core.documents import CORE_DOCUMENTS
from fitdocs.index.location import INDEX_FILENAME
from fitdocs.index.registry import registered_tables
from fitdocs.index.schema import (
    ColumnSpec,
    ColumnType,
    ResolvedTable,
    TableScope,
    TableSpec,
)
from fitdocs.index.store import open_index
from tests.query._helpers import copy_indexed_root as copy_indexed_root_helper
from tests.query.conftest import HomeDirectory


@dataclass(frozen=True)
class _Fence:
    heading: str
    sql: str


@dataclass(frozen=True)
class _Producer:
    name: str
    tables: tuple[str, ...]


@dataclass(frozen=True)
class _RegistryProducer:
    name: str
    tables: tuple[TableSpec, ...]


class _CliPayload(TypedDict):
    columns: list[str]
    rows: list[list[object]]
    row_count: int


def test_producer_matcher_requires_whole_case_sensitive_table_names() -> None:
    producers = (_Producer("derived.alpha", ("daily_load",)),)
    assert _producer_table_matches("SELECT * FROM daily_load", producers)
    assert not _producer_table_matches("SELECT * FROM xdaily_load", producers)
    assert not _producer_table_matches("SELECT * FROM daily_loadx", producers)
    assert not _producer_table_matches("SELECT * FROM Daily_Load", producers)


def test_every_skill_sql_fence_runs_and_returns_topic_rows(
    use_indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
) -> None:
    root, _index_dir = use_indexed_root
    fences = _skill_fences()
    expected_headings = {
        "Weekly running volume",
        "Time in zones",
        "Training load",
        "Races, tests and hard efforts",
        "Best efforts",
        "Fitness, fatigue and form",
        "Thresholds in force",
        "Planned sessions not logged",
    }
    assert expected_headings <= {fence.heading for fence in fences}
    assert len(fences) >= 8

    observed: dict[str, list[dict[str, object]]] = {}
    for fence in fences:
        payload = _run_sql(root, fence.sql)
        assert payload["row_count"] >= 1, fence.heading
        observed[fence.heading] = _records(payload)

    weekly = observed["Weekly running volume"]
    assert any(row.get("sport") == "Run" for row in weekly)
    assert any(str(row.get("week_start", "")).startswith("2021-09") for row in weekly)

    zones = observed["Time in zones"]
    assert zones
    assert all(row.get("channel") == "heart_rate" for row in zones)
    assert all(row.get("bound_unit") == "bpm" for row in zones)
    assert any(
        float(cast(int | float | str, row.get("seconds", 0))) > 0 for row in zones
    )

    loads = observed["Training load"]
    assert loads
    assert all(row.get("selected") is True for row in loads)
    assert all(row.get("calculator_id") == "threshold" for row in loads)

    efforts = observed["Races, tests and hard efforts"]
    assert efforts == [
        {
            "date": "2021-09-08",
            "effort": "race",
            "effort_distance_m": 42195.0,
            "effort_time_s": 12345.0,
            "effort_event": "Fixture Marathon",
        }
    ]

    best_efforts = observed["Best efforts"]
    assert {
        int(cast(int | float | str, row["duration_s"])) for row in best_efforts
    } == {1, 5, 10}
    assert len(best_efforts) == 3
    assert all(row["power_w"] is not None for row in best_efforts)
    assert all(row["sport"] == "Ride" for row in best_efforts)
    assert all(row["path"] and row["title"] for row in best_efforts)

    form = observed["Fitness, fatigue and form"]
    assert {row["methodology"] for row in form} == {"threshold"}
    form_dates = [str(row["day"]) for row in form]
    assert form_dates == sorted(form_dates)
    assert form_dates[-1] == "2021-09-08"
    assert all(day >= "2021-08-11" for day in form_dates)

    thresholds = observed["Thresholds in force"]
    assert thresholds == [
        {
            "date": "2021-09-08",
            "sport": "Ride",
            "kind": "ftp_watts",
            "discipline": "Ride",
            "starts_on": "2021-09-02",
            "ends_before": None,
            "value": 250.0,
            "unit": "w",
            "measured_on": "2021-09-02",
        }
    ]

    planned = observed["Planned sessions not logged"]
    assert planned == [
        {
            "block_id": "analytics-query-examples",
            "workout_id": "query-not-logged",
            "day": "2021-09-20",
            "sport": "Run",
            "title": "Planned run",
            "state": "not logged",
        }
    ]
    home_dir.assert_untouched()


def test_plan_and_benchmark_fixture_rows_match_literal_inputs(
    use_indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
) -> None:
    _root, index_dir = use_indexed_root
    with open_index(index_dir / INDEX_FILENAME, read_only=True) as connection:
        benchmark_rows = tuple(
            connection.execute(
                "SELECT kind, discipline, value, unit, measured_on "
                "FROM benchmarks WHERE kind = 'ftp_watts' AND discipline = 'Ride' "
                "ORDER BY measured_on"
            ).fetchall()
        )
        period_rows = tuple(
            connection.execute(
                "SELECT kind, discipline, starts_on, ends_before, value, unit, "
                "measured_on "
                "FROM benchmark_periods WHERE kind = 'ftp_watts' "
                "AND discipline = 'Ride' ORDER BY starts_on"
            ).fetchall()
        )
        plan_rows = tuple(
            connection.execute(
                "SELECT workout_id, day, state FROM planned_workouts "
                "WHERE block_id = 'analytics-query-examples' ORDER BY day"
            ).fetchall()
        )
        default_series = tuple(
            connection.execute(
                "SELECT methodology, history_default FROM load_series "
                "WHERE history_default IS TRUE ORDER BY methodology"
            ).fetchall()
        )
    assert benchmark_rows == (
        ("ftp_watts", "Ride", 250.0, "w", date(2021, 9, 1)),
        ("ftp_watts", "Ride", 250.0, "w", date(2021, 9, 2)),
    )
    assert period_rows == (
        (
            "ftp_watts",
            "Ride",
            date(2021, 9, 1),
            date(2021, 9, 2),
            250.0,
            "w",
            date(2021, 9, 1),
        ),
        (
            "ftp_watts",
            "Ride",
            date(2021, 9, 2),
            None,
            250.0,
            "w",
            date(2021, 9, 2),
        ),
    )
    assert plan_rows == (
        ("query-not-logged", date(2021, 9, 20), "not logged"),
        ("query-upcoming", date(2021, 10, 3), "upcoming"),
    )
    assert default_series == (("threshold", True),)
    home_dir.assert_untouched()


def test_thresholds_example_includes_a_historical_closed_period(
    use_indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root, source_index = use_indexed_root
    root, index_dir = copy_indexed_root_helper(
        source_root, source_index, tmp_path / "historical-closed-period"
    )
    with open_index(index_dir / INDEX_FILENAME, read_only=False) as connection:
        before = connection.execute(
            "SELECT date, sport FROM pages WHERE sport = 'Ride'"
        ).fetchall()
        periods = connection.execute(
            "SELECT starts_on, ends_before, value FROM benchmark_periods "
            "WHERE kind = 'ftp_watts' AND discipline = 'Ride' ORDER BY starts_on"
        ).fetchall()
        assert before == [(date(2021, 9, 8), "Ride")]
        assert periods == [
            (date(2021, 9, 1), date(2021, 9, 2), 250.0),
            (date(2021, 9, 2), None, 250.0),
        ]
        connection.execute(
            "UPDATE pages SET date = DATE '2021-09-01' WHERE sport = 'Ride'"
        )
        after = connection.execute(
            "SELECT date, sport FROM pages WHERE sport = 'Ride'"
        ).fetchall()
    assert before != after
    assert after == [(date(2021, 9, 1), "Ride")]

    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir.parent))
    sql = next(
        fence.sql for fence in _skill_fences() if fence.heading == "Thresholds in force"
    )
    rows = _records(_run_sql(root, sql))
    assert rows == [
        {
            "date": "2021-09-01",
            "sport": "Ride",
            "kind": "ftp_watts",
            "discipline": "Ride",
            "starts_on": "2021-09-01",
            "ends_before": "2021-09-02",
            "value": 250.0,
            "unit": "w",
            "measured_on": "2021-09-01",
        }
    ]
    home_dir.assert_untouched()


def test_best_efforts_example_selects_the_highest_record_per_duration() -> None:
    fence = next(fence for fence in _skill_fences() if fence.heading == "Best efforts")
    normalized_sql = " ".join(fence.sql.casefold().split())
    assert (
        "qualify row_number() over ( partition by m.duration_s order by m.power_w desc"
    ) in normalized_sql


@pytest.mark.parametrize(
    "comment_witness", [False, True], ids=("actual", "comment-witness")
)
def test_every_non_core_producer_has_a_live_row_selecting_example(
    home_dir: HomeDirectory,
    use_indexed_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    comment_witness: bool,
) -> None:
    source_root, source_index = use_indexed_root
    producer_tables = _producer_tables(registered_tables())
    fences = _skill_fences()
    if comment_witness:
        fences = tuple(
            _Fence(
                fence.heading,
                fence.sql.replace(
                    "WITH data_end AS (",
                    "WITH\n"
                    "    -- FTP dates are in benchmark_periods.\n"
                    "    data_end AS (",
                    1,
                )
                if fence.heading == "Best efforts"
                else fence.sql,
            )
            for fence in fences
        )
        assert "-- FTP dates are in benchmark_periods." in next(
            fence.sql for fence in fences if fence.heading == "Best efforts"
        )
    assert producer_tables
    observed: dict[str, list[tuple[str, bool, int]]] = {}
    copies: dict[str, tuple[tuple[Path, Path], tuple[Path, Path]]] = {}
    source_counts: dict[str, tuple[int, ...]] = {}

    def execute(sql: str, producer: str, names: tuple[str, ...], emptied: bool) -> int:
        if producer not in observed:
            positive_root, positive_index = copy_indexed_root_helper(
                source_root,
                source_index,
                tmp_path / f"{producer.replace('.', '-')}-positive",
            )
            empty_root, empty_index = copy_indexed_root_helper(
                source_root,
                source_index,
                tmp_path / f"{producer.replace('.', '-')}-empty",
            )
            observed[producer] = []
            copies[producer] = (
                (positive_root, positive_index),
                (empty_root, empty_index),
            )
            source_counts[producer] = tuple(
                _facade_count(positive_index, name) for name in names
            )
            assert any(count > 0 for count in source_counts[producer])
            assert (
                tuple(_facade_count(empty_index, name) for name in names)
                == (source_counts[producer])
            )
        assert names == producer_tables[producer]
        (positive_root, positive_index), (empty_root, empty_index) = copies[producer]
        root, index_dir = (
            (empty_root, empty_index) if emptied else (positive_root, positive_index)
        )
        if emptied:
            with open_index(index_dir / INDEX_FILENAME, read_only=False) as connection:
                for name in names:
                    connection.execute(f'DELETE FROM "{name}"')
            assert tuple(_facade_count(index_dir, name) for name in names) == (
                0,
            ) * len(names)
        monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir.parent))
        payload = _run_sql(root, sql)
        count = int(payload["row_count"])
        observed[producer].append((sql, emptied, count))
        return count

    missing = _unrepresented_producers(producer_tables, fences, execute)
    assert missing == ()
    assert set(observed) == set(producer_tables)
    for producer in producer_tables:
        attempts = observed[producer]
        assert len(attempts) >= 2 and len(attempts) % 2 == 0
        pairs = tuple(zip(attempts[::2], attempts[1::2], strict=True))
        assert all(
            not normal[1] and emptied[1] and normal[0] == emptied[0]
            for normal, emptied in pairs
        )
        assert any(normal[2] >= 1 and emptied[2] == 0 for normal, emptied in pairs)
    home_dir.assert_untouched()


def _skill_fences() -> tuple[_Fence, ...]:
    skill = (
        Path(__file__).resolve().parents[2]
        / "src/fitdocs/skills/fitdocs-analytics/SKILL.md"
    )
    lines = skill.read_text(encoding="utf-8").splitlines()
    heading = ""
    fences: list[_Fence] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("### "):
            heading = line.removeprefix("### ")
        if line == "```sql":
            query_lines: list[str] = []
            index += 1
            while index < len(lines) and lines[index] != "```":
                query_lines.append(lines[index])
                index += 1
            fences.append(_Fence(heading, "\n".join(query_lines)))
        index += 1
    assert fences
    return tuple(fences)


def _run_sql(root: Path, sql: str) -> _CliPayload:
    result = CliRunner().invoke(
        app, ["query", "--format", "json", sql, "--out", str(root)]
    )
    assert result.exit_code == 0, result.output
    return cast(_CliPayload, json.loads(result.stdout))


def _records(payload: _CliPayload) -> list[dict[str, object]]:
    columns = payload["columns"]
    rows = payload["rows"]
    assert isinstance(columns, list)
    assert isinstance(rows, list)
    return [dict(zip(columns, row, strict=True)) for row in rows]


def test_producer_map_excludes_bookkeeping_and_imported_core_names() -> None:
    tables = (
        _table(CORE_DOCUMENTS.name, "pages", TableScope.DOCUMENT),
        _table(CORE_COMPUTED.name, "activities", TableScope.COMPUTED),
        _table("index.bookkeeping", "index_meta", TableScope.BOOKKEEPING),
        _table("derived.alpha", "daily_load", TableScope.CORPUS),
        _table("derived.alpha", "weekly_load", TableScope.CORPUS),
        _table("derived.beta", "planned_workouts", TableScope.CORPUS),
    )
    assert _producer_tables(tables) == {
        "derived.alpha": ("daily_load", "weekly_load"),
        "derived.beta": ("planned_workouts",),
    }


def test_registered_extra_producer_with_one_row_and_no_example_is_missing(
    indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _RegistryProducer(
        "derived.fake",
        (
            TableSpec(
                "fake_rows",
                "One synthetic table for the checker control.",
                (ColumnSpec("value", ColumnType.INTEGER, "Literal test value."),),
            ),
        ),
    )
    monkeypatch.setattr(
        registry, "CORPUS_PRODUCERS", (*registry.CORPUS_PRODUCERS, fake)
    )
    producer_tables = _producer_tables(registry.registered_tables())
    assert producer_tables["derived.fake"] == ("fake_rows",)

    source_root, source_index = indexed_root
    fake_root, fake_index = copy_indexed_root_helper(
        source_root, source_index, tmp_path / "fake-producer-copy"
    )
    assert fake_root.is_dir()
    _create_fake_table(fake_index, with_row=True)
    assert _facade_count(fake_index, "fake_rows") == 1

    fences = (_Fence("Unrelated", "SELECT * FROM pages"),)

    def unused_executor(
        _sql: str, _producer: str, _names: tuple[str, ...], _emptied: bool
    ) -> int:
        raise AssertionError("no unmatched fence should execute")

    missing = _unrepresented_producers(producer_tables, fences, unused_executor)
    assert "derived.fake" in missing
    home_dir.assert_untouched()


@pytest.mark.parametrize(
    ("sql", "expected_initial_counts", "expected_counts", "expected_match"),
    [
        ("SELECT * FROM fake_rows", (1, 0), (1, 0), True),
        ("SELECT count(*) AS n FROM fake_rows", (1, 0), (1, 1), False),
        (
            "SELECT p.title FROM pages AS p LEFT JOIN fake_rows AS f ON TRUE LIMIT 1",
            (1, 0),
            (1, 1),
            False,
        ),
        ("SELECT * FROM fake_rows", (0, 0), (0, 0), False),
    ],
    ids=("select-star", "count-aggregate", "outer-join", "zero-zero"),
)
def test_row_selecting_checker_uses_real_populated_and_empty_cli_results(
    sql: str,
    expected_initial_counts: tuple[int, int],
    expected_counts: tuple[int, int],
    expected_match: bool,
    indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    use_indexed_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root, source_index = indexed_root
    populated_root, populated_index = copy_indexed_root_helper(
        source_root, source_index, tmp_path / "populated-copy"
    )
    empty_root, empty_index = copy_indexed_root_helper(
        source_root, source_index, tmp_path / "empty-copy"
    )
    _create_fake_table(populated_index, with_row=expected_initial_counts[0] > 0)
    _create_fake_table(empty_index, with_row=expected_initial_counts[1] > 0)

    observed_initial_counts = (
        _facade_count(populated_index, "fake_rows"),
        _facade_count(empty_index, "fake_rows"),
    )
    assert observed_initial_counts == expected_initial_counts

    observed: list[int] = []

    def execute(
        sql_text: str,
        producer: str,
        table_names: tuple[str, ...],
        emptied: bool,
    ) -> int:
        assert producer == "derived.fake"
        assert table_names == ("fake_rows",)
        root, index_dir = (
            (empty_root, empty_index) if emptied else (populated_root, populated_index)
        )
        assert root.is_dir()
        monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir.parent))
        result = CliRunner().invoke(
            app, ["query", "--format", "json", sql_text, "--out", str(root)]
        )
        assert result.exit_code == 0, result.output
        row_count = cast(_CliPayload, json.loads(result.stdout))["row_count"]
        observed.append(row_count)
        return row_count

    callback_counts = (
        execute(sql, "derived.fake", ("fake_rows",), False),
        execute(sql, "derived.fake", ("fake_rows",), True),
    )
    assert callback_counts == expected_counts
    observed.clear()
    assert (
        _has_row_selecting_example(sql, "derived.fake", ("fake_rows",), execute)
        is expected_match
    )
    assert tuple(observed) == expected_counts
    home_dir.assert_untouched()


def _create_fake_table(index_dir: Path, *, with_row: bool) -> None:
    with open_index(index_dir / INDEX_FILENAME, read_only=False) as connection:
        connection.execute("CREATE TABLE fake_rows (value INTEGER)")
        if with_row:
            connection.execute("INSERT INTO fake_rows VALUES (17)")


def _facade_count(index_dir: Path, table: str) -> int:
    with open_index(index_dir / INDEX_FILENAME, read_only=True) as connection:
        value = connection.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0]
        return cast(int, value)


def _table(producer: str, name: str, scope: TableScope) -> ResolvedTable:
    return ResolvedTable(producer, scope, name, "test table", ())


def _producer_table_matches(sql: str, producers: tuple[_Producer, ...]) -> bool:
    return any(
        re.search(rf"\b{re.escape(table)}\b", sql) is not None
        for producer in producers
        for table in producer.tables
    )


def _producer_tables(tables: tuple[ResolvedTable, ...]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    core_names = {CORE_DOCUMENTS.name, CORE_COMPUTED.name}
    for table in tables:
        if table.scope is TableScope.BOOKKEEPING or table.producer in core_names:
            continue
        grouped.setdefault(table.producer, []).append(table.name)
    return {
        producer: tuple(sorted(names)) for producer, names in sorted(grouped.items())
    }


def _missing_producers(
    producer_tables: dict[str, tuple[str, ...]], fences: tuple[_Fence, ...]
) -> tuple[str, ...]:
    return tuple(
        producer
        for producer, tables in sorted(producer_tables.items())
        if not _producer_table_matches(
            "\n".join(fence.sql for fence in fences),
            (_Producer(producer, tables),),
        )
    )


def _has_row_selecting_example(
    sql: str,
    producer: str,
    table_names: tuple[str, ...],
    execute: Callable[[str, str, tuple[str, ...], bool], int],
) -> bool:
    if not _producer_table_matches(sql, (_Producer(producer, table_names),)):
        return False
    normal_rows = execute(sql, producer, table_names, False)
    emptied_rows = execute(sql, producer, table_names, True)
    return normal_rows >= 1 and emptied_rows == 0


def _unrepresented_producers(
    producer_tables: dict[str, tuple[str, ...]],
    fences: tuple[_Fence, ...],
    execute: Callable[[str, str, tuple[str, ...], bool], int],
) -> tuple[str, ...]:
    missing = set(_missing_producers(producer_tables, fences))
    for producer, tables in sorted(producer_tables.items()):
        if producer in missing:
            continue
        candidates = tuple(
            fence
            for fence in fences
            if _producer_table_matches(fence.sql, (_Producer(producer, tables),))
        )
        if not any(
            _has_row_selecting_example(fence.sql, producer, tables, execute)
            for fence in candidates
        ):
            missing.add(producer)
    return tuple(sorted(missing))
