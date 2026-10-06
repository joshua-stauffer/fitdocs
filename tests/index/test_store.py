"""Connection-policy and facade tests for analytics-index task 4.1."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, cast, get_args

import pytest

from fitdocs.index.bookkeeping import (
    BOOKKEEPING_TABLES,
    Bookkeeping,
    ComputedState,
    IndexMeta,
    PageState,
)
from fitdocs.index.schema import (
    PAGE_KEY_COLUMN,
    ColumnSpec,
    ColumnType,
    ResolvedTable,
    TableScope,
    resolve_tables,
)
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
    RowShapeError,
    SettingValue,
    apply_descriptions,
    checkpoint,
    classify_error,
    create_index,
    create_schema,
    delete_page_rows,
    delete_page_state,
    duckdb_version,
    insert_rows,
    open_index,
    read_bookkeeping,
    replace_table_rows,
    transaction,
    write_meta,
    write_page_state,
    write_producer_state,
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


# --- DDL, inserts, transactions and bookkeeping (task 4.3) ---

_ROW_COLUMNS = (
    ColumnSpec("label", ColumnType.VARCHAR, "A label."),
    ColumnSpec("enabled", ColumnType.BOOLEAN, "Whether it is enabled."),
    ColumnSpec("count_value", ColumnType.INTEGER, "An integer count."),
    ColumnSpec("large_value", ColumnType.BIGINT, "A large integer."),
    ColumnSpec("reading", ColumnType.DOUBLE, "A floating-point reading."),
    ColumnSpec("day", ColumnType.DATE, "A calendar date."),
    ColumnSpec("created_local", ColumnType.TIMESTAMP, "A local timestamp."),
    ColumnSpec("labels", ColumnType.VARCHAR_LIST, "A list of labels."),
)


def _resolved_table(
    name: str,
    scope: TableScope,
    columns: tuple[ColumnSpec, ...],
    *,
    description: str = "Synthetic test table.",
) -> ResolvedTable:
    resolved_columns = (
        (PAGE_KEY_COLUMN, *columns)
        if scope in (TableScope.DOCUMENT, TableScope.COMPUTED)
        else columns
    )
    return ResolvedTable(
        producer="test.producer",
        scope=scope,
        name=name,
        description=description,
        columns=resolved_columns,
    )


def _scalar_round_trip(connection: IndexConnection) -> list[tuple[object, ...]]:
    result = connection.execute(
        "SELECT label, enabled, count_value, large_value, reading, day, "
        "created_local, labels FROM all_scalar_types ORDER BY label NULLS LAST"
    )
    return result.fetchall()


def test_create_schema_round_trips_every_column_type_and_comments(
    tmp_path: Path,
) -> None:
    table = _resolved_table(
        "all_scalar_types",
        TableScope.DOCUMENT,
        _ROW_COLUMNS,
        description="An owner's table description.",
    )
    first = (
        "primary",
        True,
        17,
        8_000_000_000,
        1.25,
        date(2025, 1, 2),
        datetime(2025, 1, 2, 3, 4, 5, 678901),
        ("first", "second"),
    )
    second = (None, None, None, None, None, None, None, ())
    path = tmp_path / "ddl-roundtrip.duckdb"

    with create_index(path) as connection:
        create_schema(connection, (table,))
        assert (
            insert_rows(connection, table, (first, second), page_key="page-alpha") == 2
        )

        rows = connection.execute(
            "SELECT page_key, label, enabled, count_value, large_value, reading, "
            "day, created_local, labels FROM all_scalar_types "
            "ORDER BY label NULLS LAST"
        ).fetchall()
        assert rows == [
            ("page-alpha", *first[:-1], ["first", "second"]),
            ("page-alpha", *second[:-1], []),
        ]
        columns = connection.execute(
            "SELECT column_name, comment FROM duckdb_columns() "
            "WHERE table_name = 'all_scalar_types' ORDER BY column_index"
        ).fetchall()
        assert columns == [
            ("page_key", PAGE_KEY_COLUMN.description),
            ("label", "A label."),
            ("enabled", "Whether it is enabled."),
            ("count_value", "An integer count."),
            ("large_value", "A large integer."),
            ("reading", "A floating-point reading."),
            ("day", "A calendar date."),
            ("created_local", "A local timestamp."),
            ("labels", "A list of labels."),
        ]
        table_comment = connection.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = 'all_scalar_types'"
        ).fetchall()
        assert table_comment == [("An owner's table description.",)]

        constraints = connection.execute(
            "SELECT table_name FROM duckdb_constraints() "
            "WHERE table_name = 'all_scalar_types'"
        ).fetchall()
        indexes = connection.execute(
            "SELECT index_name FROM duckdb_indexes() "
            "WHERE table_name = 'all_scalar_types'"
        ).fetchall()
        assert constraints == []
        assert indexes == []


@pytest.mark.parametrize(
    "scope", (TableScope.DOCUMENT, TableScope.COMPUTED, TableScope.CORPUS)
)
def test_insert_rows_preserves_false_zero_null_and_empty_list(
    tmp_path: Path, scope: TableScope
) -> None:
    table = _resolved_table("value_matrix", scope, _ROW_COLUMNS)
    nulls = (None, None, None, None, None, None, None, None)
    values = (
        None,
        False,
        0,
        0,
        0.0,
        date(2024, 2, 3),
        datetime(2024, 2, 3, 4, 5, 6, 7000),
        (),
    )
    truthy = (
        "different",
        True,
        7,
        8,
        9.5,
        date(2024, 2, 4),
        datetime(2024, 2, 4),
        ("x",),
    )
    path = tmp_path / f"value-matrix-{scope.value}.duckdb"
    with create_index(path) as connection:
        create_schema(connection, (table,))
        key = (
            "page-distinct"
            if scope in (TableScope.DOCUMENT, TableScope.COMPUTED)
            else None
        )
        assert (
            insert_rows(connection, table, (nulls, values, truthy), page_key=key) == 3
        )
        rows = connection.execute(
            "SELECT label, enabled, count_value, large_value, reading, labels "
            "FROM value_matrix ORDER BY rowid"
        ).fetchall()
        assert rows == [
            (None, None, None, None, None, None),
            (None, False, 0, 0, 0.0, []),
            ("different", True, 7, 8, 9.5, ["x"]),
        ]


def test_schema_metadata_for_multiple_tables_is_exact_and_readable_read_only(
    tmp_path: Path,
) -> None:
    document = _resolved_table(
        "document_metadata",
        TableScope.DOCUMENT,
        _ROW_COLUMNS,
        description="Document-owned metadata table.",
    )
    corpus = _resolved_table(
        "corpus_metadata",
        TableScope.CORPUS,
        (
            ColumnSpec(
                "enabled", ColumnType.BOOLEAN, "Whether corpus data is enabled."
            ),
            ColumnSpec("recorded_day", ColumnType.DATE, "The recorded calendar day."),
        ),
        description="Corpus-owned metadata table.",
    )
    path = tmp_path / "multiple-metadata.duckdb"
    with create_index(path) as writer:
        create_schema(writer, (document, corpus))

    with open_index(path, read_only=True) as reader:
        columns = reader.execute(
            "SELECT table_name, column_name, data_type, comment "
            "FROM duckdb_columns() WHERE table_name IN "
            "('corpus_metadata', 'document_metadata') "
            "ORDER BY table_name, column_index"
        ).fetchall()
        assert columns == [
            (
                "corpus_metadata",
                "enabled",
                "BOOLEAN",
                "Whether corpus data is enabled.",
            ),
            ("corpus_metadata", "recorded_day", "DATE", "The recorded calendar day."),
            (
                "document_metadata",
                "page_key",
                "VARCHAR",
                "Key of the workout page: the SHA-256 (64 hex) of the page's "
                "base file, the last file its sources list.",
            ),
            ("document_metadata", "label", "VARCHAR", "A label."),
            ("document_metadata", "enabled", "BOOLEAN", "Whether it is enabled."),
            ("document_metadata", "count_value", "INTEGER", "An integer count."),
            ("document_metadata", "large_value", "BIGINT", "A large integer."),
            ("document_metadata", "reading", "DOUBLE", "A floating-point reading."),
            ("document_metadata", "day", "DATE", "A calendar date."),
            ("document_metadata", "created_local", "TIMESTAMP", "A local timestamp."),
            ("document_metadata", "labels", "VARCHAR[]", "A list of labels."),
        ]
        comments = reader.execute(
            "SELECT table_name, comment FROM duckdb_tables() "
            "WHERE table_name IN ('corpus_metadata', 'document_metadata') "
            "ORDER BY table_name"
        ).fetchall()
        assert comments == [
            ("corpus_metadata", "Corpus-owned metadata table."),
            ("document_metadata", "Document-owned metadata table."),
        ]


def test_apply_descriptions_restores_comments_on_existing_table(
    tmp_path: Path,
) -> None:
    table = _resolved_table(
        "described_rows",
        TableScope.CORPUS,
        (ColumnSpec("value", ColumnType.VARCHAR, "The owner's value."),),
        description="The owner's table.",
    )
    with create_index(tmp_path / "descriptions.duckdb") as connection:
        create_schema(connection, (table,))
        connection.execute("COMMENT ON TABLE described_rows IS NULL")
        connection.execute("COMMENT ON COLUMN described_rows.value IS NULL")

        apply_descriptions(connection, (table,))

        actual = connection.execute(
            "SELECT t.comment, c.comment FROM duckdb_tables() t "
            "JOIN duckdb_columns() c USING (table_name) "
            "WHERE t.table_name = 'described_rows' AND c.column_name = 'value'"
        ).fetchall()
        assert actual == [("The owner's table.", "The owner's value.")]


def test_comment_sql_literal_doubles_single_quotes() -> None:
    import fitdocs.index.store as store

    assert store._quote_literal("an owner's value") == "'an owner''s value'"


def test_create_schema_refuses_to_replace_existing_table(tmp_path: Path) -> None:
    table = _resolved_table(
        "stable_rows",
        TableScope.CORPUS,
        (ColumnSpec("value", ColumnType.VARCHAR, "A stable value."),),
    )
    with create_index(tmp_path / "no-replace.duckdb") as connection:
        create_schema(connection, (table,))
        insert_rows(connection, table, (("preserve-me",),), page_key=None)

        with pytest.raises(IndexStatementError):
            create_schema(connection, (table,))

        assert connection.execute("SELECT value FROM stable_rows").fetchall() == [
            ("preserve-me",)
        ]


def test_insert_rows_normalizes_nonfinite_floats_to_null(tmp_path: Path) -> None:
    table = _resolved_table(
        "float_values",
        TableScope.CORPUS,
        (ColumnSpec("reading", ColumnType.DOUBLE, "A reading."),),
    )
    with create_index(tmp_path / "nonfinite.duckdb") as connection:
        create_schema(connection, (table,))

        inserted = insert_rows(
            connection,
            table,
            ((float("nan"),), (float("inf"),), (float("-inf"),), (2.5,), (4,)),
            page_key=None,
        )

        assert inserted == 5
        assert connection.execute(
            "SELECT reading FROM float_values ORDER BY reading NULLS FIRST"
        ).fetchall() == [(None,), (None,), (None,), (2.5,), (4.0,)]


def test_insert_json_encoder_keeps_nan_guard_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_dumps = json.dumps
    allow_nan_values: list[object] = []

    def record_dumps(value: object, **kwargs: Any) -> str:
        if "allow_nan" in kwargs:
            allow_nan_values.append(kwargs["allow_nan"])
        return real_dumps(value, **kwargs)

    monkeypatch.setattr(json, "dumps", record_dumps)
    table = _resolved_table(
        "guarded_floats",
        TableScope.CORPUS,
        (ColumnSpec("reading", ColumnType.DOUBLE, "A reading."),),
    )
    with create_index(tmp_path / "json-guard.duckdb") as connection:
        create_schema(connection, (table,))
        insert_rows(connection, table, ((float("nan"),),), page_key=None)
        assert connection.execute("SELECT reading FROM guarded_floats").fetchall() == [
            (None,)
        ]

    assert allow_nan_values == [False]


def test_multrow_insert_uses_one_complete_columnar_json_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = _resolved_table("json_batch", TableScope.DOCUMENT, _ROW_COLUMNS)
    rows = (
        (
            "one",
            True,
            1,
            4_294_967_296,
            1.5,
            date(2024, 3, 4),
            datetime(2024, 3, 4, 5, 6, 7, 89012),
            ("alpha", "beta"),
        ),
        ("two", False, 0, 0, 0.0, date(2024, 3, 4), datetime(2024, 3, 4), ()),
        (None, None, None, None, None, None, None, None),
    )
    original_execute = IndexConnection.execute
    inserts: list[tuple[str, tuple[object, ...]]] = []

    def record_insert(
        connection: IndexConnection,
        sql: str,
        params: Sequence[object] = (),
    ) -> Any:
        if sql.startswith('INSERT INTO "json_batch"'):
            inserts.append((sql, tuple(params)))
        return original_execute(connection, sql, params)

    monkeypatch.setattr(IndexConnection, "execute", record_insert)
    with create_index(tmp_path / "json-batch.duckdb") as connection:
        create_schema(connection, (table,))
        assert insert_rows(connection, table, rows, page_key="page-json") == 3

    expected_payload = (
        '{"c0":["one","two",null],"c1":[true,false,null],'
        '"c2":[1,0,null],"c3":[4294967296,0,null],"c4":[1.5,0.0,null],'
        '"c5":["2024-03-04","2024-03-04",null],'
        '"c6":["2024-03-04T05:06:07.089012","2024-03-04T00:00:00.000000",null],'
        '"c7":[["alpha","beta"],[],null]}'
    )
    assert len(inserts) == 1
    assert inserts[0][1] == (expected_payload, "page-json")
    assert "from_json($1" in inserts[0][0]


@pytest.mark.parametrize(
    ("column", "value", "scope", "page_key", "row"),
    [
        (
            ColumnSpec("created_local", ColumnType.TIMESTAMP, "A local timestamp."),
            datetime(2025, 1, 1, tzinfo=UTC),
            TableScope.DOCUMENT,
            "page-a",
            (datetime(2025, 1, 1, tzinfo=UTC),),
        ),
        (
            ColumnSpec("reading", ColumnType.DOUBLE, "A reading."),
            True,
            TableScope.CORPUS,
            None,
            (True,),
        ),
        (
            ColumnSpec("enabled", ColumnType.BOOLEAN, "Whether it is enabled."),
            1,
            TableScope.CORPUS,
            None,
            (1,),
        ),
        (
            ColumnSpec("count_value", ColumnType.INTEGER, "An integer count."),
            True,
            TableScope.CORPUS,
            None,
            (True,),
        ),
        (
            ColumnSpec("large_value", ColumnType.BIGINT, "A large integer."),
            True,
            TableScope.CORPUS,
            None,
            (True,),
        ),
        (
            ColumnSpec("day", ColumnType.DATE, "A calendar date."),
            datetime(2025, 1, 1),
            TableScope.CORPUS,
            None,
            (datetime(2025, 1, 1),),
        ),
        (
            ColumnSpec("labels", ColumnType.VARCHAR_LIST, "A list of labels."),
            ["not", "a", "tuple"],
            TableScope.CORPUS,
            None,
            (["not", "a", "tuple"],),
        ),
        (
            ColumnSpec("labels", ColumnType.VARCHAR_LIST, "A list of labels."),
            ("valid", 7),
            TableScope.CORPUS,
            None,
            (("valid", 7),),
        ),
        (
            ColumnSpec("label", ColumnType.VARCHAR, "A label."),
            3,
            TableScope.CORPUS,
            None,
            (3,),
        ),
    ],
)
def test_insert_rows_rejects_values_that_do_not_match_declared_types(
    tmp_path: Path,
    column: ColumnSpec,
    value: object,
    scope: TableScope,
    page_key: str | None,
    row: tuple[object, ...],
) -> None:
    table = _resolved_table("invalid_values", scope, (column,))
    with create_index(tmp_path / f"invalid-{column.name}.duckdb") as connection:
        create_schema(connection, (table,))

        with pytest.raises(RowShapeError):
            insert_rows(connection, table, (cast(Any, row),), page_key=page_key)


def test_insert_rows_rejects_list_containers_even_with_valid_width(
    tmp_path: Path,
) -> None:
    table = _resolved_table(
        "list_rows",
        TableScope.CORPUS,
        (ColumnSpec("value", ColumnType.VARCHAR, "A value."),),
    )
    with create_index(tmp_path / "list-row.duckdb") as connection:
        create_schema(connection, (table,))
        with pytest.raises(RowShapeError):
            insert_rows(connection, table, cast(Any, (["value"],)), page_key=None)


def test_insert_rows_rejects_wrong_arity_and_per_page_key_mismatch(
    tmp_path: Path,
) -> None:
    per_page = _resolved_table(
        "per_page_values",
        TableScope.DOCUMENT,
        (ColumnSpec("value", ColumnType.VARCHAR, "A value."),),
    )
    corpus = _resolved_table(
        "corpus_values",
        TableScope.CORPUS,
        (
            ColumnSpec("page_key", ColumnType.VARCHAR, "A page key."),
            ColumnSpec("value", ColumnType.VARCHAR, "A value."),
        ),
    )
    with create_index(tmp_path / "wrong-shape.duckdb") as connection:
        create_schema(connection, (per_page, corpus))
        with pytest.raises(RowShapeError):
            insert_rows(connection, per_page, (("one", "extra"),), page_key="p1")
        with pytest.raises(RowShapeError):
            insert_rows(connection, per_page, (("one",),), page_key=None)
        with pytest.raises(RowShapeError):
            insert_rows(connection, corpus, (("p1", "one"),), page_key="p1")
        with pytest.raises(RowShapeError):
            insert_rows(connection, corpus, (("p1",),), page_key=None)


def test_replace_table_rows_and_delete_page_rows_keep_table_scopes_distinct(
    tmp_path: Path,
) -> None:
    document = _resolved_table(
        "document_rows",
        TableScope.DOCUMENT,
        (ColumnSpec("value", ColumnType.VARCHAR, "A value."),),
    )
    computed = _resolved_table(
        "computed_rows",
        TableScope.COMPUTED,
        (ColumnSpec("value", ColumnType.INTEGER, "An integer value."),),
    )
    corpus = _resolved_table(
        "corpus_rows",
        TableScope.CORPUS,
        (
            ColumnSpec("page_key", ColumnType.VARCHAR, "A page key."),
            ColumnSpec("value", ColumnType.VARCHAR, "A corpus value."),
        ),
    )
    with create_index(tmp_path / "delete-scope.duckdb") as connection:
        bookkeeping = resolve_tables((), (), (), BOOKKEEPING_TABLES)
        create_schema(connection, (document, computed, corpus, *bookkeeping))
        insert_rows(connection, document, (("old-document",),), page_key="page-a")
        insert_rows(connection, document, (("keep-document",),), page_key="page-b")
        insert_rows(connection, computed, ((1,),), page_key="page-a")
        insert_rows(connection, computed, ((2,),), page_key="page-b")
        insert_rows(
            connection,
            corpus,
            (("page-a", "corpus-a"), ("page-b", "corpus-b")),
            page_key=None,
        )
        write_meta(connection, IndexMeta(1, "4.3-test", "1.5.6", "/root", "fp"))
        write_page_state(
            connection,
            PageState("page-a", "a.md", "doc-a", "render-a", ComputedState.COMPUTED),
        )

        with pytest.raises(RowShapeError):
            replace_table_rows(connection, document, (("must-not-replace",),))
        assert connection.execute(
            "SELECT * FROM document_rows ORDER BY page_key"
        ).fetchall() == [
            ("page-a", "old-document"),
            ("page-b", "keep-document"),
        ]

        delete_page_rows(
            connection,
            "page-a",
            (document, computed, corpus),
        )

        assert connection.execute("SELECT * FROM document_rows").fetchall() == [
            ("page-b", "keep-document")
        ]
        assert connection.execute("SELECT * FROM computed_rows").fetchall() == [
            ("page-b", 2)
        ]
        assert connection.execute(
            "SELECT * FROM corpus_rows ORDER BY page_key"
        ).fetchall() == [
            ("page-a", "corpus-a"),
            ("page-b", "corpus-b"),
        ]
        assert read_bookkeeping(connection) == Bookkeeping(
            meta=IndexMeta(1, "4.3-test", "1.5.6", "/root", "fp"),
            pages={
                "page-a": PageState(
                    "page-a", "a.md", "doc-a", "render-a", ComputedState.COMPUTED
                )
            },
            producers={},
        )

        replaced = replace_table_rows(connection, corpus, (("page-b", "new"),))
        assert replaced == 1
        assert connection.execute("SELECT * FROM corpus_rows").fetchall() == [
            ("page-b", "new")
        ]

        assert insert_rows(connection, document, (), page_key="page-a") == 0
        assert replace_table_rows(connection, corpus, ()) == 0
        assert connection.execute("SELECT * FROM corpus_rows").fetchall() == []


def test_delete_page_rows_leaves_bookkeeping_tables_untouched(tmp_path: Path) -> None:
    bookkeeping = resolve_tables((), (), (), BOOKKEEPING_TABLES)
    meta = IndexMeta(3, "fitdocs", "1.5.7", "/root/data", "athlete-fp")
    state = PageState(
        "page-a", "workouts/a.md", "doc-fp", "render-fp", ComputedState.COMPUTED
    )
    with create_index(tmp_path / "bookkeeping-delete-scope.duckdb") as connection:
        create_schema(connection, bookkeeping)
        write_meta(connection, meta)
        write_page_state(connection, state)
        before = Bookkeeping(meta=meta, pages={"page-a": state}, producers={})
        assert read_bookkeeping(connection) == before

        delete_page_rows(connection, "page-a", (bookkeeping[1],))

        assert read_bookkeeping(connection) == before


def test_page_rows_are_replaced_once_inside_a_transaction(tmp_path: Path) -> None:
    table = _resolved_table(
        "page_values",
        TableScope.DOCUMENT,
        (ColumnSpec("value", ColumnType.VARCHAR, "A page value."),),
    )
    with create_index(tmp_path / "page-replace.duckdb") as connection:
        create_schema(connection, (table,))
        insert_rows(connection, table, (("old-a1",), ("old-a2",)), page_key="page-a")
        insert_rows(connection, table, (("keep-b",),), page_key="page-b")

        with transaction(connection):
            delete_page_rows(connection, "page-a", (table,))
            insert_rows(
                connection, table, (("new-a1",), ("new-a2",)), page_key="page-a"
            )

        assert connection.execute(
            "SELECT page_key, value FROM page_values ORDER BY page_key, value"
        ).fetchall() == [
            ("page-a", "new-a1"),
            ("page-a", "new-a2"),
            ("page-b", "keep-b"),
        ]


def test_transaction_rolls_back_and_reraises_the_original_exception(
    tmp_path: Path,
) -> None:
    table = _resolved_table(
        "transaction_rows",
        TableScope.CORPUS,
        (ColumnSpec("value", ColumnType.VARCHAR, "A value."),),
    )
    failure = RuntimeError("keep this exception instance")
    path = tmp_path / "rollback.duckdb"
    with create_index(path) as connection:
        create_schema(connection, (table,))

        with pytest.raises(RuntimeError) as raised, transaction(connection):
            insert_rows(connection, table, (("temporary",),), page_key=None)
            raise failure

        assert raised.value is failure
        assert connection.execute("SELECT * FROM transaction_rows").fetchall() == []
        with transaction(connection):
            insert_rows(connection, table, (("committed",),), page_key=None)

    with open_index(path, read_only=True) as reader:
        assert reader.execute("SELECT * FROM transaction_rows").fetchall() == [
            ("committed",)
        ]


def test_transaction_handles_baseexception_and_suppresses_rollback_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BodyAbort(BaseException):
        pass

    table = _resolved_table(
        "baseexception_rows",
        TableScope.CORPUS,
        (ColumnSpec("value", ColumnType.VARCHAR, "A value."),),
    )
    with create_index(tmp_path / "baseexception.duckdb") as connection:
        create_schema(connection, (table,))
        body_error = BodyAbort("preserve this body exception")
        with pytest.raises(BodyAbort) as raised, transaction(connection):
            insert_rows(connection, table, (("rolled-back",),), page_key=None)
            raise body_error
        assert raised.value is body_error
        assert connection.execute("SELECT * FROM baseexception_rows").fetchall() == []

        second_body_error = BodyAbort("rollback also fails")
        rollback_error = RuntimeError("synthetic rollback error")
        rollback_calls: list[str] = []
        original_execute = IndexConnection.execute

        def fail_rollback(
            target: IndexConnection,
            sql: str,
            params: Sequence[object] = (),
        ) -> Any:
            if sql == "ROLLBACK":
                rollback_calls.append(sql)
                raise rollback_error
            return original_execute(target, sql, params)

        monkeypatch.setattr(IndexConnection, "execute", fail_rollback)
        with (
            pytest.raises(BodyAbort) as raised_after_rollback_error,
            transaction(connection),
        ):
            insert_rows(connection, table, (("cleanup",),), page_key=None)
            raise second_body_error

        assert raised_after_rollback_error.value is second_body_error
        assert rollback_calls == ["ROLLBACK"]
        # The spy prevented rollback; clean up with the saved method.
        original_execute(connection, "ROLLBACK")
        assert connection.execute("SELECT * FROM baseexception_rows").fetchall() == []


def test_checkpoint_executes_the_duckdb_checkpoint_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_execute = IndexConnection.execute
    statements: list[str] = []

    def record_execute(
        connection: IndexConnection,
        sql: str,
        params: Sequence[object] = (),
    ) -> Any:
        statements.append(sql)
        return original_execute(connection, sql, params)

    monkeypatch.setattr(IndexConnection, "execute", record_execute)
    with create_index(tmp_path / "checkpoint.duckdb") as connection:
        checkpoint(connection)

    assert statements == ["CHECKPOINT"]


def test_bookkeeping_round_trips_and_missing_or_ambiguous_meta_is_none(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bookkeeping.duckdb"
    with create_index(path) as connection:
        assert read_bookkeeping(connection) is None
        create_schema(connection, resolve_tables((), (), (), BOOKKEEPING_TABLES))
        assert read_bookkeeping(connection) is None

        initial_meta = IndexMeta(7, "fitdocs-first", "1.5.5", "/root/first", "fp-first")
        write_meta(connection, initial_meta)
        assert read_bookkeeping(connection) == Bookkeeping(
            meta=initial_meta, pages={}, producers={}
        )
        meta = IndexMeta(2, None, "1.5.7", "/cache/root-b", "athlete-sha-b")
        page_a = PageState(
            "page-a", "workouts/a.md", "doc-a", "render-a", ComputedState.COMPUTED
        )
        page_b = PageState(
            "page-b",
            "workouts/b.md",
            "doc-b",
            None,
            ComputedState.SOURCE_MISSING,
        )
        page_c = PageState(
            "page-c",
            "workouts/c.md",
            "doc-c",
            "render-c",
            ComputedState.SOURCE_UNDECODABLE,
        )
        page_d = PageState(
            "page-d", "workouts/d.md", "doc-d", "render-d", ComputedState.COMPUTED
        )
        write_meta(connection, meta)
        write_meta(connection, meta)
        write_page_state(connection, page_a)
        write_page_state(connection, page_b)
        write_page_state(connection, page_c)
        write_page_state(connection, page_d)
        assert read_bookkeeping(connection) == Bookkeeping(
            meta=meta,
            pages={
                "page-a": page_a,
                "page-b": page_b,
                "page-c": page_c,
                "page-d": page_d,
            },
            producers={},
        )
        write_page_state(
            connection,
            PageState(
                "page-a",
                "workouts/a2.md",
                "doc-a2",
                None,
                ComputedState.SOURCE_UNREADABLE,
            ),
        )
        write_producer_state(
            connection, "core.documents", TableScope.DOCUMENT, ("pages", "loads"), None
        )
        write_producer_state(
            connection,
            "season.summary",
            TableScope.CORPUS,
            ("season_summary",),
            "corpus-sha",
        )
        write_producer_state(
            connection,
            "season.summary",
            TableScope.CORPUS,
            ("season_summary", "season_counts"),
            "corpus-sha-updated",
        )
        write_producer_state(
            connection,
            "core.computed",
            TableScope.COMPUTED,
            ("activities", "records", "zone_times"),
            "computed-sha",
        )

        assert read_bookkeeping(connection) == Bookkeeping(
            meta=meta,
            pages={
                "page-a": PageState(
                    "page-a",
                    "workouts/a2.md",
                    "doc-a2",
                    None,
                    ComputedState.SOURCE_UNREADABLE,
                ),
                "page-b": page_b,
                "page-c": page_c,
                "page-d": page_d,
            },
            producers={
                "core.documents": None,
                "core.computed": "computed-sha",
                "season.summary": "corpus-sha-updated",
            },
        )
        assert connection.execute("SELECT COUNT(*) FROM index_meta").fetchall() == [
            (1,)
        ]
        assert connection.execute(
            "SELECT COUNT(*) FROM index_pages WHERE page_key = 'page-a'"
        ).fetchall() == [(1,)]
        assert connection.execute(
            "SELECT COUNT(*) FROM index_producers WHERE producer = 'season.summary'"
        ).fetchall() == [(1,)]
        assert connection.execute(
            "SELECT producer, kind, tables, fingerprint FROM index_producers "
            "ORDER BY producer"
        ).fetchall() == [
            (
                "core.computed",
                "computed",
                ["activities", "records", "zone_times"],
                "computed-sha",
            ),
            ("core.documents", "document", ["pages", "loads"], None),
            (
                "season.summary",
                "corpus",
                ["season_summary", "season_counts"],
                "corpus-sha-updated",
            ),
        ]
        delete_page_state(connection, "page-b")
        checkpoint(connection)
        assert read_bookkeeping(connection) == Bookkeeping(
            meta=meta,
            pages={
                "page-a": PageState(
                    "page-a",
                    "workouts/a2.md",
                    "doc-a2",
                    None,
                    ComputedState.SOURCE_UNREADABLE,
                ),
                "page-c": page_c,
                "page-d": page_d,
            },
            producers={
                "core.documents": None,
                "core.computed": "computed-sha",
                "season.summary": "corpus-sha-updated",
            },
        )

        connection.execute("DELETE FROM index_meta")
        assert read_bookkeeping(connection) is None
        write_meta(connection, meta)
        connection.execute(
            "INSERT INTO index_meta VALUES "
            "(1, '2.4', '1.5.6', '/other/root', 'other-sha')"
        )
        assert read_bookkeeping(connection) is None
