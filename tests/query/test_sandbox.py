"""Read-back and lock behavior of the query sandbox."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn, cast

import pytest

from fitdocs.index import store
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.store import (
    FaultKind,
    IndexConnection,
    IndexFault,
    IndexOpenError,
    IndexResult,
    SettingValue,
)
from fitdocs.query import sandbox
from tests.index._helpers import hold_index
from tests.query._helpers import plain_database
from tests.query.conftest import HomeDirectory


@pytest.fixture
def index_location(tmp_path: Path, home_dir: HomeDirectory) -> IndexLocation:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        home_dir.path,
    )
    location.directory.mkdir(parents=True)
    plain_database(location.database)
    return location


@pytest.fixture
def database(index_location: IndexLocation) -> Path:
    return index_location.database


def test_required_settings_are_literal_and_cover_store_mandatory() -> None:
    assert set(store.MANDATORY_SETTINGS) <= set(sandbox.REQUIRED_SANDBOX)
    assert dict(sandbox.REQUIRED_SANDBOX) == {
        "enable_external_access": "false",
        "autoinstall_known_extensions": "false",
        "autoload_known_extensions": "false",
        "allow_community_extensions": "false",
        "allow_persistent_secrets": "false",
        "python_enable_replacements": "false",
        "lock_configuration": "true",
        "threads": "2",
    }
    assert dict(sandbox.RESOURCE_SETTINGS) == {
        "memory_limit": "1GB",
        "threads": 2,
        "max_temp_directory_size": "4GB",
    }


def test_verification_uses_one_read_and_reports_first_map_mismatch() -> None:
    rows: list[tuple[object, ...]] = [
        ("enable_external_access", "true"),
        ("autoinstall_known_extensions", "true"),
        ("autoload_known_extensions", "false"),
        ("allow_community_extensions", "false"),
        ("allow_persistent_secrets", "false"),
        ("python_enable_replacements", "false"),
        ("lock_configuration", "true"),
        ("threads", "2"),
    ]

    class ResultRows:
        def fetchall(self) -> list[tuple[object, ...]]:
            return rows

    class ConnectionRecorder:
        statements: list[str]

        def __init__(self) -> None:
            self.statements = []

        def execute(self, sql: str, params: Sequence[object] = ()) -> ResultRows:
            self.statements.append(sql)
            return ResultRows()

    recorder = ConnectionRecorder()
    with pytest.raises(sandbox.SandboxUnverified) as raised:
        sandbox.verify_sandbox(cast(IndexConnection, recorder))

    assert raised.value.setting == "enable_external_access"
    assert raised.value.expected == "false"
    assert raised.value.actual == "true"
    assert len(recorder.statements) == 1
    assert all(name in recorder.statements[0] for name in sandbox.REQUIRED_SANDBOX)


@pytest.mark.parametrize("setting", tuple(sandbox.REQUIRED_SANDBOX))
@pytest.mark.parametrize("actual", [None, "wrong"])
def test_verification_rejects_each_missing_or_wrong_readback(
    setting: str, actual: str | None
) -> None:
    rows: list[tuple[object, ...]] = [
        (name, value) for name, value in sandbox.REQUIRED_SANDBOX.items()
    ]
    if actual is None:
        rows = [(name, value) for name, value in rows if name != setting]
    else:
        rows = [(name, actual if name == setting else value) for name, value in rows]

    readback: dict[object, object] = {row[0]: row[1] for row in rows}
    assert len(readback) == len(sandbox.REQUIRED_SANDBOX) - (actual is None)
    assert all(
        readback[name] == expected
        for name, expected in sandbox.REQUIRED_SANDBOX.items()
        if name != setting
    )
    assert (setting in readback) is (actual is not None)
    if actual is not None:
        assert readback[setting] != sandbox.REQUIRED_SANDBOX[setting]

    class ResultRows:
        def fetchall(self) -> list[tuple[object, ...]]:
            return rows

    class ConnectionRecorder:
        statements: list[str]

        def __init__(self) -> None:
            self.statements = []

        def execute(self, sql: str, params: Sequence[object] = ()) -> ResultRows:
            self.statements.append(sql)
            return ResultRows()

    recorder = ConnectionRecorder()
    with pytest.raises(sandbox.SandboxUnverified) as raised:
        sandbox.verify_sandbox(cast(IndexConnection, recorder))

    assert raised.value.setting == setting
    assert raised.value.expected == sandbox.REQUIRED_SANDBOX[setting]
    assert raised.value.actual == actual
    assert len(recorder.statements) == 1


@pytest.mark.parametrize("setting", tuple(sandbox.REQUIRED_SANDBOX))
def test_verification_rejects_each_null_readback(setting: str) -> None:
    rows: list[tuple[object, ...]] = [
        (name, None if name == setting else value)
        for name, value in sandbox.REQUIRED_SANDBOX.items()
    ]
    readback: dict[object, object] = {row[0]: row[1] for row in rows}
    assert len(readback) == len(sandbox.REQUIRED_SANDBOX)
    assert all(
        readback[name] == expected
        for name, expected in sandbox.REQUIRED_SANDBOX.items()
        if name != setting
    )
    assert readback[setting] is None

    class ResultRows:
        def fetchall(self) -> list[tuple[object, ...]]:
            return rows

    class ConnectionRecorder:
        statements: list[str]

        def __init__(self) -> None:
            self.statements = []

        def execute(self, sql: str, params: Sequence[object] = ()) -> ResultRows:
            self.statements.append(sql)
            return ResultRows()

    recorder = ConnectionRecorder()
    with pytest.raises(sandbox.SandboxUnverified) as raised:
        sandbox.verify_sandbox(cast(IndexConnection, recorder))

    assert raised.value.setting == setting
    assert raised.value.expected == sandbox.REQUIRED_SANDBOX[setting]
    assert raised.value.actual is None
    assert len(recorder.statements) == 1


def test_real_connection_reads_back_every_sandbox_setting(
    index_location: IndexLocation, home_dir: HomeDirectory
) -> None:
    location = index_location
    connection = sandbox.open_sandboxed(
        location,
        pid=27183,
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        on_wait=lambda _: None,
    )
    try:
        rows = connection.execute(
            "SELECT name, value FROM duckdb_settings() WHERE name IN ("
            + ", ".join("'" + name + "'" for name in sandbox.REQUIRED_SANDBOX)
            + ")"
        ).fetchall()
        values = {str(name): str(value) for name, value in rows}
        for name, expected in sandbox.REQUIRED_SANDBOX.items():
            assert values[name] == expected, name
        assert connection.execute(
            "SELECT current_setting('memory_limit')"
        ).fetchall() == [("953.6 MiB",)]
        assert connection.execute(
            "SELECT current_setting('max_temp_directory_size')"
        ).fetchall() == [("3.7 GiB",)]
        assert connection.execute("SELECT current_setting('threads')").fetchall() == [
            (2,)
        ]
    finally:
        connection.close()
    home_dir.assert_untouched()


def test_missing_mandatory_external_access_fails_closed_and_closes(
    index_location: IndexLocation,
    database: Path,
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location = index_location
    original = store.open_index
    closed: list[bool] = []

    class ConnectionSpy:
        def __init__(self, connection: IndexConnection) -> None:
            self.connection = connection

        def execute(self, sql: str, params: Sequence[object] = ()) -> IndexResult:
            return self.connection.execute(sql, params)

        def close(self) -> None:
            closed.append(True)
            self.connection.close()

    def open_and_spy(
        path: Path, *, read_only: bool, settings: Mapping[str, SettingValue]
    ) -> IndexConnection:
        return cast(
            IndexConnection,
            ConnectionSpy(original(path, read_only=read_only, settings=settings)),
        )

    monkeypatch.setattr(store, "open_index", open_and_spy)
    monkeypatch.setattr(
        store,
        "MANDATORY_SETTINGS",
        {
            key: value
            for key, value in store.MANDATORY_SETTINGS.items()
            if key != "enable_external_access"
        },
    )
    with pytest.raises(sandbox.SandboxUnverified) as raised:
        sandbox.open_sandboxed(
            location,
            pid=27184,
            monotonic=lambda: 0.0,
            sleep=lambda _: None,
            on_wait=lambda _: None,
        )
    assert raised.value.setting == "enable_external_access"
    assert raised.value.expected == "false"
    assert raised.value.actual == "true"
    assert closed == [True]
    home_dir.assert_untouched()


def test_locked_writer_retries_with_capped_schedule_and_reports_pid(
    index_location: IndexLocation, database: Path, home_dir: HomeDirectory
) -> None:
    location = index_location
    sleeps: list[float] = []
    waits: list[int | None] = []
    current = [0.0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += seconds if seconds else 0.001

    with (
        hold_index(database, read_only=False) as holder_pid,
        pytest.raises(sandbox.IndexBusy) as raised,
    ):
        sandbox.open_sandboxed(
            location,
            pid=27185,
            monotonic=lambda: current[0],
            sleep=fake_sleep,
            on_wait=waits.append,
        )
    assert sleeps == pytest.approx([0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 2.0, 2.0, 2.0, 0.85])
    assert waits == [holder_pid]
    assert raised.value.holder_pid == holder_pid
    with pytest.raises(ProcessLookupError):
        os.kill(holder_pid, 0)
    home_dir.assert_untouched()


def test_final_open_attempt_occurs_at_window_boundary(
    index_location: IndexLocation,
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location = index_location
    attempts: list[float] = []
    current = [0.0]

    def fake_open(
        path: Path, *, read_only: bool, settings: Mapping[str, SettingValue]
    ) -> NoReturn:
        attempts.append(current[0])
        if len(attempts) == 1:
            current[0] += 0.25
        raise IndexOpenError(IndexFault(FaultKind.LOCKED, "locked", 404))

    def fake_sleep(seconds: float) -> None:
        current[0] += seconds if seconds else 0.001

    monkeypatch.setattr(store, "open_index", fake_open)
    with pytest.raises(sandbox.IndexBusy):
        sandbox.open_sandboxed(
            location,
            pid=27186,
            monotonic=lambda: current[0],
            sleep=fake_sleep,
            on_wait=lambda _: None,
        )
    assert attempts[0] == 0.0
    assert attempts[-1] == 10.0
    assert len(attempts) == len(sandbox.LOCK_RETRY_DELAYS_S) + 4
    home_dir.assert_untouched()


def test_non_locked_open_fault_is_not_retried(
    index_location: IndexLocation,
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location = index_location
    calls: list[tuple[Path, bool, dict[str, SettingValue]]] = []

    def fake_open(
        path: Path, *, read_only: bool, settings: Mapping[str, SettingValue]
    ) -> NoReturn:
        calls.append((path, read_only, dict(settings)))
        raise IndexOpenError(IndexFault(FaultKind.CORRUPT, "junk database", None))

    current = [0.0]

    def advance(seconds: float) -> None:
        current[0] += seconds

    monkeypatch.setattr(store, "open_index", fake_open)
    with pytest.raises(IndexOpenError) as raised:
        sandbox.open_sandboxed(
            location,
            pid=27187,
            monotonic=lambda: current[0],
            sleep=advance,
            on_wait=lambda _: None,
        )
    assert raised.value.fault.kind is FaultKind.CORRUPT
    assert calls == [
        (
            location.database,
            True,
            dict(sandbox.RESOURCE_SETTINGS)
            | {"temp_directory": str(location.directory / "query-spill-27187")},
        )
    ]
    home_dir.assert_untouched()


def test_corrupt_junk_database_propagates_without_retry(
    tmp_path: Path, home_dir: HomeDirectory
) -> None:
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        home_dir.path,
    )
    location.directory.mkdir(parents=True)
    database = location.database
    database.write_bytes(b"not a DuckDB database")
    now = [0.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    with pytest.raises(IndexOpenError) as raised:
        sandbox.open_sandboxed(
            location,
            pid=27188,
            monotonic=lambda: now[0],
            sleep=fake_sleep,
            on_wait=lambda _: None,
        )
    assert raised.value.fault.kind is FaultKind.CORRUPT
    assert sleeps == []
    home_dir.assert_untouched()


def test_read_only_holder_does_not_wait(
    index_location: IndexLocation, database: Path, home_dir: HomeDirectory
) -> None:
    location = index_location
    sleeps: list[float] = []
    waits: list[int | None] = []
    current = [0.0]

    def advance(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += seconds

    with hold_index(database, read_only=True) as holder_pid:
        connection = sandbox.open_sandboxed(
            location,
            pid=27189,
            monotonic=lambda: current[0],
            sleep=advance,
            on_wait=waits.append,
        )
        connection.close()
    assert sleeps == []
    assert waits == []
    assert holder_pid > 0
    home_dir.assert_untouched()
