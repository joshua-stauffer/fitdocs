"""Pins for analytics-index's result facade on the query call path."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest

from fitdocs.index.store import (
    IndexInterrupted,
    IndexStatementError,
    create_index,
    open_index,
)
from tests.query.conftest import HomeDirectory


@pytest.fixture
def read_only_database(tmp_path: Path, home_dir: HomeDirectory) -> Path:
    database = tmp_path / "index.duckdb"
    with create_index(database):
        pass
    return database


def test_fetchmany_wraps_missing_optional_timezone_module(
    read_only_database: Path, home_dir: HomeDirectory
) -> None:
    assert importlib.util.find_spec("pytz") is None
    with open_index(read_only_database, read_only=True) as connection:
        result = connection.execute("SELECT now()")
        with pytest.raises(IndexStatementError) as raised:
            result.fetchmany(1)
    assert raised.value.__cause__ is not None
    home_dir.assert_untouched()


def test_fetchall_wraps_missing_optional_timezone_module(
    read_only_database: Path, home_dir: HomeDirectory
) -> None:
    assert importlib.util.find_spec("pytz") is None
    with open_index(read_only_database, read_only=True) as connection:
        result = connection.execute("SELECT now()")
        with pytest.raises(IndexStatementError) as raised:
            result.fetchall()
    assert raised.value.__cause__ is not None
    home_dir.assert_untouched()


def test_aggregate_interrupt_is_chained_during_execute_or_fetch(
    read_only_database: Path, home_dir: HomeDirectory
) -> None:
    script = textwrap.dedent(
        """
        import threading
        from pathlib import Path
        from fitdocs.index.store import IndexInterrupted, open_index

        connection = open_index(Path(__import__('sys').argv[1]), read_only=True)
        timer = threading.Timer(0.5, connection.interrupt)
        timer.start()
        phase = "execute"
        try:
            try:
                result = connection.execute(
                    "SELECT count(*) FROM range(1000000000000)"
                )
                phase = "fetchmany"
                result.fetchmany(1)
            except IndexInterrupted as error:
                print(f"INTERRUPTED:{phase}:{error.__cause__ is not None}")
            else:
                raise AssertionError("aggregate completed without interruption")
        finally:
            timer.cancel()
            connection.close()
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(read_only_database)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() in {
        "INTERRUPTED:execute:True",
        "INTERRUPTED:fetchmany:True",
    }
    home_dir.assert_untouched()


def test_fetchmany_wraps_synthetic_interrupt_from_backend(
    home_dir: HomeDirectory,
) -> None:
    from fitdocs.index import store

    class BackendError(Exception):
        pass

    class BackendInterrupt(BackendError):
        pass

    class InterruptedRelation:
        columns: tuple[str, ...] = ()
        types: tuple[str, ...] = ()

        def fetchmany(self, size: int) -> list[tuple[object, ...]]:
            raise original

    original = BackendInterrupt("synthetic fetch interruption")
    errors = store._DuckDBErrorTypes(BackendError, BackendInterrupt)
    result = store.IndexResult(cast(Any, InterruptedRelation()), errors)
    with pytest.raises(IndexInterrupted) as raised:
        result.fetchmany(1)
    assert str(raised.value) == "synthetic fetch interruption"
    assert raised.value.__cause__ is original
    home_dir.assert_untouched()


# Statement types are parsed for query validation without running SQL.


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1", ("SELECT",)),
        ("WITH rows AS (SELECT 1 AS n) SELECT n FROM rows", ("SELECT",)),
        ("FROM range(1)", ("SELECT",)),
        ("VALUES (1)", ("SELECT",)),
        ("DESCRIBE SELECT 1", ("SELECT",)),
        ("SHOW TABLES", ("SELECT",)),
        ("SUMMARIZE SELECT 1", ("SELECT",)),
        ("PRAGMA version", ("SELECT",)),
        ("PRAGMA table_info('query_test')", ("SELECT",)),
        ("EXPLAIN ANALYZE SELECT 1", ("EXPLAIN",)),
        ("INSTALL httpfs", ("LOAD",)),
        ("LOAD httpfs", ("LOAD",)),
        ("SET threads = 1", ("SET",)),
        ("RESET threads", ("SET",)),
        ("USE memory", ("SET",)),
        ("SET VARIABLE query_test = 1", ("SET",)),
        ("CALL checkpoint()", ("CALL",)),
        ("CHECKPOINT", ("CALL",)),
        ("CREATE TEMP TABLE query_test (n INTEGER)", ("CREATE",)),
        (
            "CREATE SECRET query_test (TYPE http, SCOPE 'https://example.invalid')",
            ("CREATE",),
        ),
        ("COPY (SELECT 1) TO '/tmp/query-test.csv'", ("COPY",)),
        ("ATTACH ':memory:' AS query_test", ("ATTACH",)),
        ("DETACH query_test", ("DETACH",)),
        ("EXPORT DATABASE '/tmp/query-test-export'", ("EXPORT",)),
        ("SELECT 1; SELECT 2", ("SELECT", "SELECT")),
        ("SELECT 1; COPY (SELECT 2) TO '/tmp/query-test.csv'", ("SELECT", "COPY")),
    ],
)
def test_statement_types_returns_duckdb_type_names(
    read_only_database: Path,
    home_dir: HomeDirectory,
    sql: str,
    expected: tuple[str, ...],
) -> None:
    with open_index(read_only_database, read_only=True) as connection:
        assert connection.statement_types(sql) == expected
    home_dir.assert_untouched()


@pytest.mark.parametrize("sql", ["", "   \n\t", "-- c", "/* c */"])
def test_statement_types_returns_empty_for_empty_or_comments(
    read_only_database: Path, home_dir: HomeDirectory, sql: str
) -> None:
    with open_index(read_only_database, read_only=True) as connection:
        assert connection.statement_types(sql) == ()
    home_dir.assert_untouched()


def test_statement_types_chains_parse_errors(
    read_only_database: Path, home_dir: HomeDirectory
) -> None:
    with (
        open_index(read_only_database, read_only=True) as connection,
        pytest.raises(IndexStatementError) as raised,
    ):
        connection.statement_types("SELEC 1")
    assert 'syntax error at or near "SELEC"' in str(raised.value)
    assert raised.value.__cause__ is not None
    home_dir.assert_untouched()


def test_statement_types_preserves_original_parse_error(
    read_only_database: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs.index import store

    class SyntheticParseError(Exception):
        pass

    original = SyntheticParseError("known synthetic parser detail")

    class ParserProxy:
        def __init__(self, backend: object) -> None:
            self.backend = backend

        def extract_statements(self, sql: str) -> object:
            assert sql == "synthetic invalid SQL"
            raise original

        def __getattr__(self, name: str) -> object:
            return getattr(self.backend, name)

    with open_index(read_only_database, read_only=True) as connection:
        monkeypatch.setattr(
            connection, "_connection", ParserProxy(connection._connection)
        )
        monkeypatch.setattr(
            connection,
            "_errors",
            store._DuckDBErrorTypes(SyntheticParseError, KeyboardInterrupt),
        )
        with pytest.raises(IndexStatementError) as raised:
            connection.statement_types("synthetic invalid SQL")
    assert str(raised.value) == "known synthetic parser detail"
    assert raised.value.__cause__ is original
    home_dir.assert_untouched()


def test_statement_types_never_calls_execute(
    read_only_database: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    with open_index(read_only_database, read_only=True) as connection:
        backend_calls: list[tuple[str, str]] = []

        class BackendProxy:
            def __init__(self, backend: object) -> None:
                self.backend = backend

            def extract_statements(self, sql: str) -> object:
                return cast(Any, self.backend).extract_statements(sql)

            def execute(self, sql: str, *args: object) -> None:
                backend_calls.append(("execute", sql))

            def sql(self, sql: str, *args: object) -> None:
                backend_calls.append(("sql", sql))

            def query(self, sql: str, *args: object) -> None:
                backend_calls.append(("query", sql))

            def __getattr__(self, name: str) -> object:
                return getattr(self.backend, name)

        monkeypatch.setattr(
            connection, "_connection", BackendProxy(connection._connection)
        )
        execute_calls: list[tuple[str, tuple[object, ...]]] = []

        def record_execute(sql: str, params: tuple[object, ...] = ()) -> None:
            execute_calls.append((sql, params))

        monkeypatch.setattr(connection, "execute", record_execute)
        connection.execute("SELECT 99")
        assert len(execute_calls) == 1
        assert backend_calls == []
        execute_calls.clear()
        connection._connection.execute("SELECT recorder control")
        connection._connection.sql("SELECT sql recorder control")
        connection._connection.query("SELECT query recorder control")
        assert backend_calls == [
            ("execute", "SELECT recorder control"),
            ("sql", "SELECT sql recorder control"),
            ("query", "SELECT query recorder control"),
        ]
        backend_calls.clear()

        assert connection.statement_types("SELECT 1") == ("SELECT",)
        assert execute_calls == []
        assert backend_calls == []
    home_dir.assert_untouched()
