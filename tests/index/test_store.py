"""Connection-policy and facade tests for analytics-index task 4.1."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import ModuleType
from typing import Any, cast, get_args

import pytest

from fitdocs.index.store import (
    MANDATORY_SETTINGS,
    WRITER_SETTINGS,
    WRITER_SPILL_DIRNAME,
    FaultKind,
    IndexConnection,
    IndexFault,
    IndexInterrupted,
    IndexOpenError,
    IndexStatementError,
    ResultColumn,
    SettingValue,
    classify_error,
    create_index,
    duckdb_version,
    open_index,
)

_EXPECTED_MANDATORY = {
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "allow_community_extensions": False,
    "allow_persistent_secrets": False,
    "enable_external_access": False,
    "python_enable_replacements": False,
    "lock_configuration": True,
}


def _current_setting(connection: IndexConnection, name: str) -> object:
    result = connection.execute(f"SELECT current_setting('{name}')")
    return result.fetchall()[0][0]


def _created(path: Path) -> IndexConnection:
    return create_index(path)


def _created_read_write(path: Path) -> IndexConnection:
    return open_index(path, read_only=False)


def _created_read_only(path: Path) -> IndexConnection:
    return open_index(path, read_only=True)


def test_policy_constants_match_the_connection_contract() -> None:
    assert dict(MANDATORY_SETTINGS) == _EXPECTED_MANDATORY
    assert dict(WRITER_SETTINGS) == {"storage_compatibility_version": "v1.0.0"}
    assert WRITER_SPILL_DIRNAME == "writer-spill"


def test_public_fault_and_result_contracts_are_typed_and_frozen() -> None:
    assert get_args(SettingValue) == (str, int, bool)
    assert [(kind.name, kind.value) for kind in FaultKind] == [
        ("LOCKED", "locked"),
        ("MISSING", "missing"),
        ("INCOMPATIBLE", "incompatible"),
        ("CORRUPT", "corrupt"),
        ("OTHER", "other"),
    ]
    fault = IndexFault(FaultKind.OTHER, "unclassified", None)
    assert tuple(field.name for field in fields(fault)) == (
        "kind",
        "message",
        "holder_pid",
    )
    with pytest.raises(FrozenInstanceError):
        fault_field = "message"
        setattr(cast(Any, fault), fault_field, "changed")
    column = ResultColumn("answer", "INTEGER")
    assert tuple(field.name for field in fields(column)) == ("name", "type_name")
    with pytest.raises(FrozenInstanceError):
        column_field = "name"
        setattr(cast(Any, column), column_field, "changed")
    assert issubclass(IndexOpenError, Exception)
    assert issubclass(IndexStatementError, Exception)
    assert issubclass(IndexInterrupted, Exception)


def test_every_connection_applies_all_mandatory_settings(tmp_path: Path) -> None:
    path = tmp_path / "index.duckdb"
    factories = (_created, _created_read_write, _created_read_only)
    for factory in factories:
        with factory(path) as connection:
            for name, expected in _EXPECTED_MANDATORY.items():
                assert _current_setting(connection, name) is expected


def test_matching_mandatory_override_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "index.duckdb"
    with create_index(path) as connection:
        assert _current_setting(connection, "enable_external_access") is False
    with open_index(
        path, read_only=False, settings={"enable_external_access": False}
    ) as connection:
        assert _current_setting(connection, "enable_external_access") is False


def test_writer_and_reader_config_composition_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.index.store as store

    captured: list[tuple[Path, bool, dict[str, SettingValue]]] = []

    def capture(
        path: Path, *, read_only: bool, config: Mapping[str, SettingValue]
    ) -> IndexConnection:
        captured.append((path, read_only, dict(config)))
        return cast(IndexConnection, None)

    monkeypatch.setattr(store, "_connect", capture)
    writer_path = tmp_path / "writer" / "index.duckdb"
    reader_path = tmp_path / "reader" / "index.duckdb"
    open_index(writer_path, read_only=False, settings={"threads": 2})
    open_index(reader_path, read_only=True, settings={"threads": 2})

    mandatory = {
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "allow_community_extensions": False,
        "allow_persistent_secrets": False,
        "enable_external_access": False,
        "python_enable_replacements": False,
        "lock_configuration": True,
    }
    assert captured == [
        (
            writer_path,
            False,
            {
                **mandatory,
                "threads": 2,
                "storage_compatibility_version": "v1.0.0",
                "temp_directory": str(writer_path.parent / "writer-spill"),
            },
        ),
        (reader_path, True, {**mandatory, "threads": 2}),
    ]


def test_open_forwards_complete_path_mode_and_config_to_connection_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[str, bool, dict[str, SettingValue]]] = []

    class BackendError(Exception):
        pass

    class BackendInterrupt(BackendError):
        pass

    class BackendConnection:
        def sql(self, sql: str, params: object = ()) -> object:
            raise AssertionError("query is not part of this backend capture")

        def interrupt(self) -> None:
            pass

        def close(self) -> None:
            pass

    backend = ModuleType("duckdb")
    backend.Error = BackendError  # type: ignore[attr-defined]
    backend.InterruptException = BackendInterrupt  # type: ignore[attr-defined]

    def connect(
        path: str, *, read_only: bool, config: dict[str, SettingValue]
    ) -> BackendConnection:
        captured.append((path, read_only, config))
        return BackendConnection()

    backend.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "duckdb", backend)
    path = tmp_path / "reader" / "index.duckdb"
    with open_index(path, read_only=True, settings={"threads": 3}):
        pass

    assert captured == [
        (
            str(path),
            True,
            {
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
                "allow_community_extensions": False,
                "allow_persistent_secrets": False,
                "enable_external_access": False,
                "python_enable_replacements": False,
                "lock_configuration": True,
                "threads": 3,
            },
        )
    ]


@pytest.mark.parametrize(
    ("operation", "interrupted"),
    [
        ("execute", False),
        ("execute", True),
        ("fetchmany", False),
        ("fetchmany", True),
        ("fetchall", False),
        ("fetchall", True),
    ],
)
def test_facade_wraps_original_backend_errors_for_every_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    interrupted: bool,
) -> None:
    class BackendError(Exception):
        pass

    class BackendInterrupt(BackendError):
        pass

    original = (
        BackendInterrupt("original interrupted message")
        if interrupted
        else BackendError("original backend message")
    )

    class BackendRelation:
        columns = ["value"]
        types = ["INTEGER"]

        def fetchmany(self, size: int) -> list[tuple[int]]:
            if operation == "fetchmany":
                raise original
            return [(size,)]

        def fetchall(self) -> list[tuple[int]]:
            if operation == "fetchall":
                raise original
            return [(1,)]

    class BackendConnection:
        def sql(self, sql: str, params: object = ()) -> BackendRelation:
            if operation == "execute":
                raise original
            return BackendRelation()

        def interrupt(self) -> None:
            pass

        def close(self) -> None:
            pass

    backend = ModuleType("duckdb")
    backend.Error = BackendError  # type: ignore[attr-defined]
    backend.InterruptException = BackendInterrupt  # type: ignore[attr-defined]
    backend.connect = lambda *args, **kwargs: BackendConnection()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "duckdb", backend)

    connection = open_index(tmp_path / "synthetic.duckdb", read_only=True)
    expected = IndexInterrupted if interrupted else IndexStatementError
    with pytest.raises(expected) as raised:
        if operation == "execute":
            connection.execute("synthetic failure")
        elif operation == "fetchmany":
            connection.execute("synthetic relation").fetchmany(3)
        else:
            connection.execute("synthetic relation").fetchall()
    assert raised.value.__cause__ is original
    assert str(raised.value) == str(original)


@pytest.mark.parametrize("create_with_api", [False, True])
def test_open_error_preserves_original_backend_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    create_with_api: bool,
) -> None:
    class BackendError(Exception):
        pass

    class BackendInterrupt(BackendError):
        pass

    original = BackendError("No such file or directory: synthetic backend open failure")
    backend = ModuleType("duckdb")
    backend.Error = BackendError  # type: ignore[attr-defined]
    backend.InterruptException = BackendInterrupt  # type: ignore[attr-defined]

    def fail_connect(*args: object, **kwargs: object) -> None:
        raise original

    backend.connect = fail_connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "duckdb", backend)
    path = tmp_path / "missing.duckdb"
    with pytest.raises(IndexOpenError) as raised:
        if create_with_api:
            create_index(path)
        else:
            open_index(path, read_only=True)
    assert raised.value.__cause__ is original
    assert "No such file or directory" in str(original)
    assert raised.value.fault.kind is FaultKind.MISSING
    assert str(raised.value.__cause__) == str(original)
    if create_with_api:
        assert not path.exists()


@pytest.mark.parametrize(
    ("name", "wrong"),
    [
        ("autoinstall_known_extensions", True),
        ("autoload_known_extensions", True),
        ("allow_community_extensions", True),
        ("allow_persistent_secrets", True),
        ("enable_external_access", True),
        ("python_enable_replacements", True),
        ("lock_configuration", False),
    ],
)
@pytest.mark.parametrize("read_only", [False, True])
def test_mandatory_override_is_refused_before_path_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    wrong: bool,
    read_only: bool,
) -> None:
    import fitdocs.index.store as store

    path = tmp_path / "not-created" / "index.duckdb"

    def unexpected_connect(
        path: Path, *, read_only: bool, config: Mapping[str, SettingValue]
    ) -> IndexConnection:
        raise AssertionError("validation must happen before connection")

    monkeypatch.setattr(store, "_connect", unexpected_connect)
    with pytest.raises(ValueError, match=name):
        open_index(path, read_only=read_only, settings={name: wrong})
    assert not path.exists()
    assert not path.parent.exists()


def test_create_refuses_existing_index_without_changing_bytes(tmp_path: Path) -> None:
    path = tmp_path / "existing.duckdb"
    original = b"leave these existing bytes alone"
    path.write_bytes(original)
    with pytest.raises(FileExistsError):
        create_index(path)
    assert path.read_bytes() == original


def test_create_refuses_dangling_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "absent-target.duckdb"
    entry = tmp_path / "index.duckdb"
    entry.symlink_to(target)
    assert entry.is_symlink()
    assert not target.exists()

    with pytest.raises(FileExistsError):
        create_index(entry)

    assert entry.is_symlink()
    assert not target.exists()


def test_writers_use_compatibility_and_named_spill_directory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "nested" / "index.duckdb"
    for factory in (_created, _created_read_write):
        with factory(path) as connection:
            assert (
                _current_setting(connection, "storage_compatibility_version")
                == "v1.0.0"
            )
            spill = Path(str(_current_setting(connection, "temp_directory")))
            assert spill.resolve() == (path.parent / "writer-spill").resolve()
    with _created_read_only(path) as connection:
        readonly_spill = Path(str(_current_setting(connection, "temp_directory")))
        assert readonly_spill.resolve() != (path.parent / "writer-spill").resolve()


def test_created_database_header_uses_storage_version_64(tmp_path: Path) -> None:
    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    header = path.read_bytes()[12:20]
    assert len(header) == 8
    assert int.from_bytes(header, "little") == 64


@pytest.mark.parametrize(
    "statement",
    [
        "SET enable_external_access = true",
        "SET autoinstall_known_extensions = true",
        "SELECT * FROM read_csv('/etc/hosts')",
        "SELECT * FROM read_csv('https://example.invalid/x.csv')",
    ],
)
def test_external_and_configuration_statements_are_refused_without_home_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, statement: str
) -> None:
    path = tmp_path / "index.duckdb"
    fake_home = tmp_path / "absent-home"
    monkeypatch.setenv("HOME", str(fake_home))
    with create_index(path) as connection:
        with pytest.raises(IndexStatementError) as raised:
            connection.execute(statement).fetchall()
        assert raised.value.__cause__ is not None
        assert "config" in str(raised.value.__cause__).lower()
    assert not fake_home.exists()


def test_https_parameter_round_trips_as_plain_text(tmp_path: Path) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        value = "https://example.invalid/a.csv"
        assert connection.execute("SELECT ?", (value,)).fetchall() == [(value,)]


def test_multiple_heterogeneous_parameters_round_trip(tmp_path: Path) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        result = connection.execute(
            "SELECT ?::INTEGER, ?::VARCHAR, ?::BOOLEAN", (27, "typed-value", True)
        )
        assert result.fetchall() == [(27, "typed-value", True)]


def test_fetchmany_honors_repeated_sizes_and_fetchall_returns_remainder(
    tmp_path: Path,
) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        result = connection.execute("SELECT range AS n FROM range(7) ORDER BY n")
        assert result.fetchmany(2) == [(0,), (1,)]
        assert result.fetchmany(3) == [(2,), (3,), (4,)]
        assert result.fetchall() == [(5,), (6,)]


def test_idle_interrupt_is_harmless(tmp_path: Path) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        connection.interrupt()
        assert connection.execute("SELECT 1").fetchall() == [(1,)]


def test_result_columns_keep_name_and_type_and_execute_errors_chain(
    tmp_path: Path,
) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        result = connection.execute(
            "SELECT 3 AS first_value, 'z' AS second_value UNION ALL SELECT 9, 'a'"
        )
        assert result.columns == (
            ResultColumn("first_value", "INTEGER"),
            ResultColumn("second_value", "VARCHAR"),
        )
        assert result.fetchmany(1) == [(3, "z")]
        assert result.fetchall() == [(9, "a")]
        with pytest.raises(IndexStatementError) as raised:
            connection.execute("SELEC invalid")
        assert raised.value.__cause__ is not None
        assert str(raised.value) == str(raised.value.__cause__)


def test_nonquery_results_have_no_columns_or_rows(tmp_path: Path) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        result = connection.execute("CREATE TABLE empty_table (value INTEGER)")
        assert result.columns == ()
        assert result.fetchmany(2) == []
        assert result.fetchall() == []
        tables = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'empty_table'"
        )
        assert tables.fetchall() == [(1,)]


def test_read_only_connection_refuses_write(tmp_path: Path) -> None:
    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    with (
        pytest.raises(IndexStatementError) as raised,
        open_index(path, read_only=True) as connection,
    ):
        connection.execute("CREATE TABLE forbidden_write (value INTEGER)")
    assert raised.value.__cause__ is not None


def test_context_manager_closes_connection_even_when_body_raises(
    tmp_path: Path,
) -> None:
    connection = create_index(tmp_path / "index.duckdb")
    with pytest.raises(RuntimeError, match="body error"), connection:
        raise RuntimeError("body error")
    with pytest.raises(IndexStatementError) as raised:
        connection.execute("SELECT 1")
    assert raised.value.__cause__ is not None


def test_open_errors_expose_other_fault_for_later_classification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "not-a-database"
    path.mkdir()
    with pytest.raises(IndexOpenError) as raised:
        open_index(path, read_only=True)
    assert raised.value.fault.kind is FaultKind.OTHER
    assert raised.value.fault.holder_pid is None
    assert raised.value.fault.message
    assert raised.value.__cause__ is not None


@pytest.mark.parametrize("fetch_method", ["fetchmany", "fetchall"])
def test_fetch_conversion_errors_are_wrapped_and_chained(
    tmp_path: Path, fetch_method: str
) -> None:
    assert importlib.util.find_spec("pytz") is None
    with create_index(tmp_path / "index.duckdb") as connection:
        result = connection.execute("SELECT now()")
        with pytest.raises(IndexStatementError) as raised:
            getattr(result, fetch_method)(
                1
            ) if fetch_method == "fetchmany" else result.fetchall()
        assert raised.value.__cause__ is not None
        assert str(raised.value) == str(raised.value.__cause__)


def test_interrupt_at_fetch_is_wrapped_in_bounded_subprocess(tmp_path: Path) -> None:
    script = """
import threading
from pathlib import Path
from fitdocs.index.store import IndexInterrupted, create_index

connection = create_index(Path(__import__('sys').argv[1]))
try:
    result = connection.execute('SELECT count(*) FROM range(1000000000000)')
    timer = threading.Timer(0.5, connection.interrupt)
    timer.start()
    try:
        result.fetchmany(1)
    except IndexInterrupted:
        print('interrupt-wrapped')
    else:
        raise AssertionError('large query was not interrupted at fetch')
    finally:
        timer.cancel()
finally:
    connection.close()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "interrupt.duckdb")],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=Path(__file__).parents[2],
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "interrupt-wrapped"


def test_duckdb_version_comes_from_installed_distribution_metadata() -> None:
    assert duckdb_version() == importlib.metadata.version("duckdb")


def test_created_connection_can_be_used_as_context_manager(tmp_path: Path) -> None:
    with create_index(tmp_path / "index.duckdb") as connection:
        assert connection.execute("SELECT 7").fetchall() == [(7,)]


# Classification


def _assert_open_fault(
    path: Path,
    *,
    read_only: bool,
    kind: FaultKind,
    stem: str,
    holder_pid: int | None = None,
) -> None:
    with pytest.raises(IndexOpenError) as raised:
        open_index(path, read_only=read_only)
    original = raised.value.__cause__
    assert original is not None
    message = str(original)
    assert stem in message
    assert raised.value.fault.message == message
    assert raised.value.fault.kind is kind
    assert raised.value.fault.holder_pid == holder_pid


def _create_damaged_fixture(path: Path) -> None:
    payload = "".join(str(index % 10) for index in range(48_000))
    with create_index(path) as connection:
        connection.execute("CREATE TABLE damage (payload VARCHAR)")
        connection.execute("INSERT INTO damage VALUES (?)", (payload,))
        connection.execute("CHECKPOINT")
    assert path.stat().st_size > 4096


def test_classifies_read_write_lock_and_extracts_holder_pid(tmp_path: Path) -> None:
    from tests.index._helpers import hold_index

    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    with hold_index(path, read_only=False) as holder_pid:
        _assert_open_fault(
            path,
            read_only=False,
            kind=FaultKind.LOCKED,
            stem="Could not set lock on file",
            holder_pid=holder_pid,
        )


def test_classifies_read_only_lock_when_writer_attempts_open(tmp_path: Path) -> None:
    from tests.index._helpers import hold_index

    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    with hold_index(path, read_only=True) as holder_pid:
        _assert_open_fault(
            path,
            read_only=False,
            kind=FaultKind.LOCKED,
            stem="Could not set lock on file",
            holder_pid=holder_pid,
        )


@pytest.mark.parametrize(
    ("relative", "read_only", "stem"),
    [
        (False, True, "database does not exist"),
        (True, False, "No such file or directory"),
    ],
)
def test_classifies_missing_database(
    tmp_path: Path, relative: bool, read_only: bool, stem: str
) -> None:
    path = (
        tmp_path / "missing-dir" / "index.duckdb"
        if relative
        else tmp_path / "absent.duckdb"
    )
    _assert_open_fault(
        path,
        read_only=read_only,
        kind=FaultKind.MISSING,
        stem=stem,
    )


@pytest.mark.parametrize(
    ("fixture", "stem"),
    [
        ("junk", "is not a valid DuckDB database file"),
        ("empty", "is not a valid DuckDB database file"),
        ("truncated", "Could not read enough bytes"),
        ("flipped", "Corrupt database file"),
    ],
)
def test_classifies_corrupt_database_files(
    tmp_path: Path, fixture: str, stem: str
) -> None:
    path = tmp_path / f"{fixture}.duckdb"
    if fixture == "junk":
        path.write_bytes(b"not a duckdb file")
    elif fixture == "empty":
        path.write_bytes(b"")
    else:
        _create_damaged_fixture(path)
        data = bytearray(path.read_bytes())
        if fixture == "truncated":
            del data[12_288:]
        else:
            data[4096 + 128] ^= 0x01
        path.write_bytes(data)
    _assert_open_fault(
        path,
        read_only=True,
        kind=FaultKind.CORRUPT,
        stem=stem,
    )


def test_classifies_forged_storage_version_as_incompatible(tmp_path: Path) -> None:
    from tests.index._helpers import forge_storage_version

    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    forge_storage_version(path, 69)
    _assert_open_fault(
        path,
        read_only=True,
        kind=FaultKind.INCOMPATIBLE,
        stem="Trying to read a database file with version number",
    )


def test_classifies_unrecognized_duckdb_statement_as_other(
    tmp_path: Path,
) -> None:
    with (
        create_index(tmp_path / "index.duckdb") as connection,
        pytest.raises(IndexStatementError) as raised,
    ):
        connection.execute("SELECT * FROM no_such_table").fetchall()
    original = raised.value.__cause__
    assert original is not None
    assert str(original)
    fault = classify_error(original)
    assert fault.kind is FaultKind.OTHER
    assert fault.message == str(original)
    assert fault.holder_pid is None


def test_non_duckdb_exception_with_lock_stem_is_other(tmp_path: Path) -> None:
    with create_index(tmp_path / "classifier-gate.duckdb"):
        pass
    original = OSError("Could not set lock on file x")
    fault = classify_error(original)
    assert fault.kind is FaultKind.OTHER
    assert fault.message == str(original)
    assert fault.holder_pid is None


def test_locked_duckdb_error_without_pid_preserves_message_and_cause(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class BackendError(Exception):
        pass

    class BackendInterrupt(BackendError):
        pass

    original = BackendError("Could not set lock on file synthetic lock")
    backend = ModuleType("duckdb")
    backend_module = cast(Any, backend)
    backend_module.Error = BackendError
    backend_module.InterruptException = BackendInterrupt

    def fail_connect(*args: object, **kwargs: object) -> None:
        raise original

    backend_module.connect = fail_connect
    monkeypatch.setitem(sys.modules, "duckdb", backend)

    with pytest.raises(IndexOpenError) as raised:
        open_index(tmp_path / "locked-without-pid.duckdb", read_only=True)

    assert raised.value.__cause__ is original
    assert raised.value.fault == IndexFault(FaultKind.LOCKED, str(original), None)
