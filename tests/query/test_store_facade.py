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
