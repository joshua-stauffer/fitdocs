"""Execution, configuration refusal, failure classification and row caps."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest

from fitdocs.index.location import resolve_index_location
from fitdocs.index.store import (
    IndexConnection,
    IndexInterrupted,
    IndexResult,
    IndexStatementError,
)
from fitdocs.query import sandbox, statement
from fitdocs.query.format import ResultSet
from tests.query._helpers import plain_database
from tests.query.conftest import HomeDirectory


@pytest.fixture
def sandbox_connection(
    tmp_path: Path, home_dir: HomeDirectory
) -> Iterator[IndexConnection]:
    database = plain_database(tmp_path / "index.duckdb")
    location = resolve_index_location(
        tmp_path / "data",
        {"FITDOCS_INDEX_DIR": str(tmp_path / "index")},
        home=home_dir.path,
    )
    location.directory.mkdir(parents=True, exist_ok=True)
    database.replace(location.database)
    connection = sandbox.open_sandboxed(
        location,
        pid=97231,
        monotonic=lambda: 0.0,
        sleep=lambda _: None,
        on_wait=lambda _: None,
    )
    try:
        yield connection
    finally:
        connection.close()
        home_dir.assert_untouched()


def test_restriction_text_is_the_approved_literal_mapping() -> None:
    assert dict(statement.RESTRICTION_TEXT) == {
        statement.Restriction.ONE_STATEMENT: "fitdocs query runs exactly one statement",
        statement.Restriction.STATEMENT_KIND: (
            "the query sandbox runs only queries and EXPLAIN; "
            "this is a {TYPE} statement"
        ),
        statement.Restriction.OUTSIDE_INDEX: (
            "the query sandbox cannot read or write files or addresses "
            "outside the index"
        ),
        statement.Restriction.LOCKED_SETTING: "the query sandbox's settings are locked",
        statement.Restriction.READ_ONLY: "the index is open read-only",
        statement.Restriction.EXTENSION: (
            "extensions are not available in the query sandbox"
        ),
    }


@pytest.mark.parametrize(
    ("sql", "restriction", "target"),
    [
        ("SELECT * FROM read_csv('{target}')", "OUTSIDE_INDEX", "x.csv"),
        ("SELECT * FROM read_text('/etc/hosts')", "OUTSIDE_INDEX", None),
        ("SELECT * FROM glob('/etc/*')", "OUTSIDE_INDEX", None),
        (
            "SELECT * FROM read_csv('https://example.invalid/x.csv')",
            "OUTSIDE_INDEX",
            None,
        ),
        ("COPY (SELECT 1) TO '{target}'", "OUTSIDE_INDEX", "out.csv"),
        ("EXPLAIN ANALYZE COPY (SELECT 1) TO '{target}'", "OUTSIDE_INDEX", "out2.csv"),
        ("EXPORT DATABASE '{target}'", "OUTSIDE_INDEX", "exp"),
        ("ATTACH '{target}' AS o", "OUTSIDE_INDEX", "other.duckdb"),
        ("SET threads = 8", "LOCKED_SETTING", None),
        ("SET autoinstall_known_extensions = true", "LOCKED_SETTING", None),
    ],
    ids=[
        "csv",
        "text",
        "glob",
        "url-read_csv",
        "copy",
        "explain-copy",
        "export",
        "attach",
        "threads",
        "autoinstall",
    ],
)
def test_configuration_refusal(
    sql: str,
    restriction: str,
    target: str | None,
    sandbox_connection: IndexConnection,
    tmp_path: Path,
) -> None:
    target_path = tmp_path / target if target else None
    if target == "x.csv":
        assert target_path is not None
        target_path.write_text("only_local_decoy\n941\n", encoding="utf-8")
    if target_path is not None:
        if target in {"out.csv", "out2.csv", "exp", "other.duckdb"}:
            assert not target_path.exists()
        sql = sql.format(target=target_path)
    captured: list[IndexStatementError] = []

    class CapturingConnection:
        def execute(self, query: str) -> IndexResult:
            try:
                return sandbox_connection.execute(query)
            except IndexStatementError as error:
                captured.append(error)
                raise

        def interrupt(self) -> None:
            sandbox_connection.interrupt()

    with pytest.raises(statement.StatementRefused) as raised:
        statement.execute_statement(
            cast(IndexConnection, CapturingConnection()),
            sql,
            max_rows=12,
            timeout_s=2.0,
        )
    assert len(captured) == 1
    assert raised.value.restriction is getattr(statement.Restriction, restriction)
    assert raised.value.detail == str(captured[0])
    assert raised.value.detail in str(raised.value)
    if target_path is not None and target in {
        "out.csv",
        "out2.csv",
        "exp",
        "other.duckdb",
    }:
        assert not target_path.exists()


def test_enable_logging_does_not_create_a_log_directory(
    sandbox_connection: IndexConnection, tmp_path: Path
) -> None:
    log_directory = tmp_path / "logs"
    assert not log_directory.exists()
    try:
        statement.execute_statement(
            sandbox_connection,
            "SELECT * FROM enable_logging(storage='file', storage_path='"
            + str(log_directory)
            + "')",
            max_rows=10,
            timeout_s=2.0,
        )
    except (statement.StatementRefused, statement.StatementFailed) as error:
        assert error
    assert not log_directory.exists()


def test_classifier_fixed_inputs_and_hints() -> None:
    permission = IndexStatementError("opaque")
    permission.__cause__ = type("PermissionException", (Exception,), {})("opaque")
    locked = IndexStatementError("the configuration has been locked")
    locked.__cause__ = type("InvalidInputException", (Exception,), {})("locked")
    other_locked = IndexStatementError("the configuration has been locked")
    other_locked.__cause__ = RuntimeError("locked")
    inputs = [
        (permission, statement.Restriction.OUTSIDE_INDEX),
        (locked, statement.Restriction.LOCKED_SETTING),
        (other_locked, None),
        (IndexStatementError("read-only mode"), statement.Restriction.READ_ONLY),
        (
            IndexStatementError("requires the extension httpfs"),
            statement.Restriction.EXTENSION,
        ),
        (
            IndexStatementError("requires extension httpfs"),
            statement.Restriction.EXTENSION,
        ),
        (
            IndexStatementError("exists in the httpfs extension"),
            statement.Restriction.EXTENSION,
        ),
        (IndexStatementError("Binder Error: missing table"), None),
    ]
    assert [statement.classify_statement_error(exc) for exc, _ in inputs] == [
        expected for _, expected in inputs
    ]
    pytz = IndexStatementError("Required module 'pytz' not found")
    memory = IndexStatementError("opaque")
    memory.__cause__ = type("OutOfMemoryException", (Exception,), {})("opaque")
    false_memory = IndexStatementError("out of memory")
    false_memory.__cause__ = RuntimeError("out of memory")
    assert (
        statement.failure_hint(pytz)
        == "cast TIMESTAMP WITH TIME ZONE values to TIMESTAMP"
    )
    assert statement.failure_hint(memory) == (
        "the statement needed more than the query sandbox's 1 GB of memory; "
        "aggregate, or filter earlier"
    )
    assert statement.failure_hint(false_memory) is None
    assert statement.failure_hint(IndexStatementError("binder")) is None


def test_facade_binder_error_preserves_message_and_no_hint(
    sandbox_connection: IndexConnection,
) -> None:
    with pytest.raises(IndexStatementError) as original:
        sandbox_connection.execute("SELECT missing_column")
    with pytest.raises(statement.StatementFailed) as raised:
        statement.execute_statement(
            sandbox_connection, "SELECT missing_column", max_rows=4, timeout_s=2.0
        )
    assert raised.value.message == str(original.value)
    assert raised.value.hint is None


def test_facade_read_only_and_extension_classifier(
    sandbox_connection: IndexConnection,
) -> None:
    captured: list[IndexStatementError] = []
    for sql in (
        "ATTACH ':memory:' AS other",
        "CREATE SECRET s (TYPE S3, KEY_ID 'x', SECRET 'y')",
    ):
        with pytest.raises(IndexStatementError) as error:
            sandbox_connection.execute(sql)
        captured.append(error.value)
    assert [statement.classify_statement_error(exc) for exc in captured] == [
        statement.Restriction.READ_ONLY,
        statement.Restriction.EXTENSION,
    ]


def test_timestamp_fetch_failure_gets_hint(sandbox_connection: IndexConnection) -> None:
    with pytest.raises(statement.StatementFailed) as raised:
        statement.execute_statement(
            sandbox_connection, "SELECT now()", max_rows=4, timeout_s=2.0
        )
    assert raised.value.message
    assert raised.value.hint == "cast TIMESTAMP WITH TIME ZONE values to TIMESTAMP"


class TimerControl(threading.Timer):
    def __init__(self, timeout_s: float, callback: Callable[[], None]) -> None:
        super().__init__(timeout_s, callback)
        self.events: list[str] = []
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.events.append("start")
        self.started = True

    def cancel(self) -> None:
        self.events.append("cancel")
        self.cancelled = True


@pytest.mark.parametrize("fails", [False, True], ids=["success", "execute-error"])
def test_timer_starts_before_execution_and_is_cancelled(
    sandbox_connection: IndexConnection, fails: bool
) -> None:
    created: list[TimerControl] = []
    events: list[str] = []

    class ResultProxy:
        columns = ()

        def fetchmany(self, size: int) -> list[tuple[object, ...]]:
            events.append(f"fetch:{size}")
            return []

    class ConnectionProxy:
        def execute(self, sql: str) -> ResultProxy:
            events.append("execute")
            if fails:
                raise IndexStatementError("Binder Error: wrong")
            return ResultProxy()

        def interrupt(self) -> None:
            events.append("interrupt")

    def factory(timeout_s: float, callback: Callable[[], None]) -> TimerControl:
        timer = TimerControl(timeout_s, callback)
        created.append(timer)
        events.append("timer-created")
        timer.events = events
        return timer

    connection = cast(IndexConnection, ConnectionProxy())
    if fails:
        with pytest.raises(statement.StatementFailed):
            statement.execute_statement(
                connection, "SELECT 1", max_rows=3, timeout_s=4.25, timer=factory
            )
    else:
        result = statement.execute_statement(
            connection, "SELECT 1", max_rows=3, timeout_s=4.25, timer=factory
        )
        assert result == ResultSet((), (), False, 3)
    assert created[0].interval == 4.25
    assert created[0].started and created[0].cancelled
    assert events.index("timer-created") < events.index("start")
    assert events.index("start") < events.index("execute")
    if not fails:
        assert events.index("execute") < events.index("fetch:4")


def test_facade_permission_and_locked_cause_classifier_controls(
    sandbox_connection: IndexConnection,
) -> None:
    cases = (
        ("SELECT * FROM read_csv('/etc/hosts')", statement.Restriction.OUTSIDE_INDEX),
        ("SET threads = 8", statement.Restriction.LOCKED_SETTING),
    )
    captures: list[IndexStatementError] = []
    for sql, expected in cases:
        with pytest.raises(IndexStatementError) as captured:
            sandbox_connection.execute(sql)
        captures.append(captured.value)
        assert statement.classify_statement_error(captured.value) is expected
        assert captured.value.__cause__ is not None
    assert type(captures[0].__cause__).__name__ == "PermissionException"
    assert type(captures[1].__cause__).__name__ == "InvalidInputException"
    opaque_with_invalid_input_cause = IndexStatementError(
        "opaque without the locked-setting stem"
    )
    opaque_with_invalid_input_cause.__cause__ = captures[1].__cause__
    assert statement.classify_statement_error(opaque_with_invalid_input_cause) is None
    assert (
        statement.classify_statement_error(
            IndexStatementError("opaque without a recognized cause")
        )
        is None
    )


def test_row_cap_and_result_shape(sandbox_connection: IndexConnection) -> None:
    capped = statement.execute_statement(
        sandbox_connection,
        "SELECT range AS left_name, 2001 - range AS right_name FROM range(1001)",
        max_rows=1000,
        timeout_s=4.0,
    )
    assert capped.columns == ("left_name", "right_name")
    assert len(capped.rows) == 1000
    assert capped.rows[0] == (0, 2001)
    assert capped.rows[999] == (999, 1002)
    assert capped.max_rows == 1000
    assert capped.truncated is True
    exact = statement.execute_statement(
        sandbox_connection,
        "SELECT range AS third_name, 3000 - range AS fourth_name FROM range(1000)",
        max_rows=1000,
        timeout_s=4.0,
    )
    assert exact.columns == ("third_name", "fourth_name")
    assert len(exact.rows) == 1000
    assert exact.rows[0] == (0, 3000)
    assert exact.rows[999] == (999, 2001)
    assert exact.max_rows == 1000
    assert exact.truncated is False


def test_small_nondefault_cap_preserves_distinct_ordered_rows(
    sandbox_connection: IndexConnection,
) -> None:
    result = statement.execute_statement(
        sandbox_connection,
        "SELECT range AS first_label, 19 - range AS second_label "
        "FROM range(7) ORDER BY range DESC",
        max_rows=3,
        timeout_s=2.0,
    )
    assert result.columns == ("first_label", "second_label")
    assert result.rows == ((6, 13), (5, 14), (4, 15))
    assert result.max_rows == 3
    assert result.truncated is True


def test_actual_timeout_has_bounded_safety_interrupt(
    sandbox_connection: IndexConnection,
) -> None:
    safety = threading.Timer(10.0, sandbox_connection.interrupt)
    started = time.monotonic()
    safety.daemon = True
    safety.start()
    try:
        with pytest.raises(statement.StatementTimedOut) as raised:
            statement.execute_statement(
                sandbox_connection,
                "SELECT count(*) FROM range(1000000000000)",
                max_rows=10,
                timeout_s=0.5,
            )
        assert raised.value.timeout_s == 0.5
        assert time.monotonic() - started <= 3.0
    finally:
        safety.cancel()
        safety.join(timeout=1.0)


class MatrixTimer(threading.Timer):
    def __init__(self, timeout_s: float, callback: Callable[[], None]) -> None:
        super().__init__(timeout_s, callback)
        self.events: list[str] = []
        self.events.append("created")

    def start(self) -> None:
        self.events.append("start")

    def cancel(self) -> None:
        self.events.append("cancel")


class MatrixResult:
    columns = ()

    def __init__(
        self,
        events: list[str],
        outcome: BaseException | None = None,
        on_fetch: Callable[[], None] | None = None,
    ) -> None:
        self.events = events
        self.outcome = outcome
        self.on_fetch = on_fetch

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        self.events.append(f"fetch:{size}")
        if self.on_fetch is not None:
            self.on_fetch()
        if self.outcome is not None:
            raise self.outcome
        return [(29,)]


@pytest.mark.parametrize(
    "phase", ["execute", "fetch"], ids=["execute-phase", "fetch-phase"]
)
@pytest.mark.parametrize("fired", [False, True], ids=["user-interrupt", "timer-fired"])
def test_interruption_phase_identity_and_cleanup(phase: str, fired: bool) -> None:
    events: list[str] = []
    original = IndexInterrupted("interrupted by user")
    timer_box: list[MatrixTimer] = []

    def factory(timeout_s: float, callback: Callable[[], None]) -> MatrixTimer:
        timer = MatrixTimer(timeout_s, callback)
        timer.events = events
        timer_box.append(timer)
        return timer

    class Connection:
        def execute(self, sql: str) -> MatrixResult:
            events.append("execute")
            if phase == "execute":
                if fired:
                    timer_box[0].function()
                raise original
            return MatrixResult(
                events,
                original if not fired else None,
                timer_box[0].function if fired else None,
            )

        def interrupt(self) -> None:
            events.append("interrupt")
            if fired:
                raise original

    conn = cast(IndexConnection, Connection())
    if fired:
        with pytest.raises(statement.StatementTimedOut) as timed_out:
            statement.execute_statement(
                conn, "SELECT 1", max_rows=2, timeout_s=0.75, timer=factory
            )
        assert timed_out.value.timeout_s == 0.75
        assert events.index("interrupt") > events.index("start")
    else:
        with pytest.raises(IndexInterrupted) as interrupted:
            statement.execute_statement(
                conn, "SELECT 1", max_rows=2, timeout_s=0.75, timer=factory
            )
        assert interrupted.value is original
        assert "interrupt" not in events
    assert events.count("cancel") == 1
    assert events.index("start") < events.index("execute")
    if phase == "fetch":
        assert "fetch:3" in events
        if fired:
            assert events.index("interrupt") > events.index("fetch:3")


@pytest.mark.parametrize("phase", ["execute", "fetch"], ids=["execute", "fetch"])
@pytest.mark.parametrize(
    "classified", [False, True], ids=["unclassified", "classified"]
)
def test_statement_error_mapping_and_cancellation_on_each_phase(
    phase: str, classified: bool
) -> None:
    events: list[str] = []
    cause = type("PermissionException", (Exception,), {})("opaque")
    error = IndexStatementError("opaque detail")
    if classified:
        error.__cause__ = cause
    timer_box: list[MatrixTimer] = []

    def factory(timeout_s: float, callback: Callable[[], None]) -> MatrixTimer:
        timer = MatrixTimer(timeout_s, callback)
        timer.events = events
        timer_box.append(timer)
        return timer

    class Connection:
        def execute(self, sql: str) -> MatrixResult:
            events.append("execute")
            if phase == "execute":
                raise error
            return MatrixResult(events, error)

        def interrupt(self) -> None:
            events.append("interrupt")

    conn = cast(IndexConnection, Connection())
    if classified:
        with pytest.raises(statement.StatementRefused) as refused:
            statement.execute_statement(
                conn, "SELECT 1", max_rows=5, timeout_s=1.25, timer=factory
            )
        assert refused.value.restriction is statement.Restriction.OUTSIDE_INDEX
        assert refused.value.detail == "opaque detail"
    else:
        with pytest.raises(statement.StatementFailed) as failed:
            statement.execute_statement(
                conn, "SELECT 1", max_rows=5, timeout_s=1.25, timer=factory
            )
        assert failed.value.message == "opaque detail"
        assert failed.value.hint is None
    assert events.count("cancel") == 1
    assert events.index("start") < events.index("execute")
    assert timer_box[0].interval == 1.25
    if phase == "fetch":
        assert events.index("execute") < events.index("fetch:6")


def test_timestamp_statement_error_from_fetch_carries_hint() -> None:
    events: list[str] = []
    error = IndexStatementError("Required module 'pytz' is missing")
    timer_box: list[MatrixTimer] = []

    def factory(timeout_s: float, callback: Callable[[], None]) -> MatrixTimer:
        timer = MatrixTimer(timeout_s, callback)
        timer.events = events
        timer_box.append(timer)
        return timer

    class Connection:
        def execute(self, sql: str) -> MatrixResult:
            events.append("execute")
            return MatrixResult(events, error)

        def interrupt(self) -> None:
            events.append("interrupt")

    with pytest.raises(statement.StatementFailed) as raised:
        statement.execute_statement(
            cast(IndexConnection, Connection()),
            "SELECT now()",
            max_rows=5,
            timeout_s=1.25,
            timer=factory,
        )
    assert raised.value.message == "Required module 'pytz' is missing"
    assert raised.value.hint == "cast TIMESTAMP WITH TIME ZONE values to TIMESTAMP"
    assert events.count("cancel") == 1
    assert events.index("start") < events.index("execute")
    assert timer_box[0].interval == 1.25


@pytest.mark.parametrize(
    "escaping",
    [KeyboardInterrupt(), RuntimeError("unexpected")],
    ids=["keyboard-interrupt", "other-error"],
)
def test_timer_cancelled_for_keyboard_interrupt_and_other_escaping_error(
    escaping: BaseException,
) -> None:
    events: list[str] = []

    def factory(timeout_s: float, callback: Callable[[], None]) -> MatrixTimer:
        timer = MatrixTimer(timeout_s, callback)
        timer.events = events
        return timer

    class Connection:
        def execute(self, sql: str) -> MatrixResult:
            events.append("execute")
            raise escaping

        def interrupt(self) -> None:
            events.append("interrupt")

    with pytest.raises(type(escaping)) as raised:
        statement.execute_statement(
            cast(IndexConnection, Connection()),
            "SELECT 1",
            max_rows=2,
            timeout_s=3.0,
            timer=factory,
        )
    assert raised.value is escaping
    assert events.count("cancel") == 1
    assert events.index("start") < events.index("execute")


def test_restriction_members_are_exact_str_enum_contract() -> None:
    assert issubclass(statement.Restriction, StrEnum)
    assert {
        name: member.value for name, member in statement.Restriction.__members__.items()
    } == {
        "ONE_STATEMENT": "one_statement",
        "STATEMENT_KIND": "statement_kind",
        "OUTSIDE_INDEX": "outside_index",
        "LOCKED_SETTING": "locked_setting",
        "READ_ONLY": "read_only",
        "EXTENSION": "extension",
    }


@pytest.mark.parametrize(
    ("error", "cause_name"),
    [
        (IndexStatementError("PermissionException is just message text"), None),
        (IndexStatementError("the configuration has been locked"), None),
        (IndexStatementError("Binder Error: unrelated extension column"), None),
        (IndexStatementError("the configuration has been locked"), "RuntimeError"),
    ],
    ids=[
        "permission-message-only",
        "locked-without-cause",
        "extension-word",
        "locked-wrong-cause",
    ],
)
def test_classifier_negative_partitions(
    error: IndexStatementError, cause_name: str | None
) -> None:
    if cause_name is not None:
        error.__cause__ = type(cause_name, (Exception,), {})("not the required cause")
    assert statement.classify_statement_error(error) is None


def test_unrelated_pytz_identifier_has_no_failure_hint() -> None:
    assert (
        statement.failure_hint(
            IndexStatementError("Binder Error: column pytz does not exist")
        )
        is None
    )


def test_result_max_rows_remains_an_integer() -> None:
    class TinyResult:
        columns = (
            type("Column", (), {"name": "second"})(),
            type("Column", (), {"name": "first"})(),
        )

        def fetchmany(self, size: int) -> list[tuple[int, int]]:
            assert size == 4
            return [(8, 3), (7, 4), (6, 5), (5, 6)]

    class TinyConnection:
        def execute(self, sql: str) -> TinyResult:
            return TinyResult()

        def interrupt(self) -> None:
            raise AssertionError("the quiet timer must not interrupt")

    result = statement.execute_statement(
        cast(IndexConnection, TinyConnection()),
        "already-screened-test-input",
        max_rows=3,
        timeout_s=1.0,
        timer=TimerControl,
    )
    assert type(result.max_rows) is int
    assert result.max_rows == 3
    assert result.columns == ("second", "first")
    assert result.rows == ((8, 3), (7, 4), (6, 5))
    assert result.truncated is True


def test_timer_start_failure_cancels_timer_before_work() -> None:
    events: list[str] = []
    failure = RuntimeError("timer start failed")

    class FailingTimer(threading.Timer):
        def start(self) -> None:
            events.append("start")
            raise failure

        def cancel(self) -> None:
            events.append("cancel")

    class NeverExecute:
        def execute(self, sql: str) -> IndexResult:
            raise AssertionError("execution must not follow timer start failure")

        def interrupt(self) -> None:
            raise AssertionError("timer callback must not run")

    with pytest.raises(RuntimeError) as raised:
        statement.execute_statement(
            cast(IndexConnection, NeverExecute()),
            "SELECT 1",
            max_rows=1,
            timeout_s=1.0,
            timer=FailingTimer,
        )
    assert raised.value is failure
    assert events == ["start", "cancel"]


@pytest.mark.parametrize(
    "phase",
    ["success", "execute-error", "fetch-error"],
    ids=["success", "execute-error", "fetch-error"],
)
def test_real_timer_interrupt_action_finishes_before_return(
    sandbox_connection: IndexConnection, phase: str
) -> None:
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    action_finished: list[int] = []
    timers: list[threading.Timer] = []

    class ControlledConnection:
        def execute(self, sql: str) -> IndexResult:
            assert entered.wait(1.0), "real Timer must enter its callback"
            if phase == "execute-error":
                raise RuntimeError("controlled execution failure")
            if phase == "fetch-error":

                class FetchFailure:
                    columns = ()

                    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
                        raise RuntimeError("controlled execution failure")

                return cast(IndexResult, FetchFailure())
            return sandbox_connection.execute(sql)

        def interrupt(self) -> None:
            entered.set()
            release.wait(0.5)
            sandbox_connection.interrupt()
            action_finished.append(time.monotonic_ns())
            finished.set()

    def factory(interval: float, callback: Callable[[], None]) -> threading.Timer:
        timer = threading.Timer(interval, callback)
        timer.daemon = True
        timers.append(timer)
        return timer

    safety_release = threading.Timer(0.15, release.set)
    safety_release.daemon = True
    safety_release.start()
    try:
        if phase != "success":
            with pytest.raises(RuntimeError, match="controlled execution failure"):
                statement.execute_statement(
                    cast(IndexConnection, ControlledConnection()),
                    "SELECT 31 AS value",
                    max_rows=2,
                    timeout_s=0.01,
                    timer=factory,
                )
        else:
            result = statement.execute_statement(
                cast(IndexConnection, ControlledConnection()),
                "SELECT 31 AS value",
                max_rows=2,
                timeout_s=0.01,
                timer=factory,
            )
            assert result.rows == ((31,),)
        returned_ns = time.monotonic_ns()
        assert entered.is_set()
        release.set()
        assert finished.wait(1.0), "the real Timer callback must finish during cleanup"
        assert action_finished[0] < returned_ns
    finally:
        release.set()
        safety_release.cancel()
        safety_release.join(timeout=1.0)
        for timer in timers:
            timer.cancel()
            timer.join(timeout=1.0)
            assert not timer.is_alive(), "timer cleanup must finish within the bound"


def test_callback_arriving_after_return_cannot_interrupt_connection() -> None:
    events: list[str] = []
    timers: list[MatrixTimer] = []

    def factory(timeout_s: float, callback: Callable[[], None]) -> MatrixTimer:
        timer = MatrixTimer(timeout_s, callback)
        timer.events = events
        timers.append(timer)
        return timer

    class Connection:
        def execute(self, sql: str) -> MatrixResult:
            events.append("execute")
            return MatrixResult(events)

        def interrupt(self) -> None:
            events.append("interrupt")

    result = statement.execute_statement(
        cast(IndexConnection, Connection()),
        "SELECT 1",
        max_rows=2,
        timeout_s=3.0,
        timer=factory,
    )
    assert result.rows == ((29,),)
    assert events.count("cancel") == 1
    assert "interrupt" not in events
    assert len(timers) == 1

    timers[0].function()
    assert "interrupt" not in events


# Late callback cleanup across bounded error exits
@pytest.mark.parametrize("phase", ["execute", "fetch"])
@pytest.mark.parametrize(
    "kind",
    [
        "classified",
        "unclassified",
        "user-interrupt",
        "keyboard",
        "other",
        "timer-fired",
    ],
)
def test_late_callback_cannot_interrupt_after_error_exit(
    phase: str,
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    events: list[str] = []
    interrupt_actions: list[str] = []
    timers: list[threading.Timer] = []
    classified = IndexStatementError("opaque classified detail")
    classified.__cause__ = type("PermissionException", (Exception,), {})("opaque")
    unclassified = IndexStatementError("Binder Error: controlled missing column")
    user_interrupt = IndexInterrupted("controlled user interrupt")
    keyboard_interrupt = KeyboardInterrupt("controlled keyboard interrupt")
    other_error = RuntimeError("controlled escaping error")
    timer_interrupt = IndexInterrupted("controlled timeout interrupt")
    errors: dict[str, BaseException] = {
        "classified": classified,
        "unclassified": unclassified,
        "user-interrupt": user_interrupt,
        "keyboard": keyboard_interrupt,
        "other": other_error,
        "timer-fired": timer_interrupt,
    }
    expected_types: dict[str, type[BaseException]] = {
        "classified": statement.StatementRefused,
        "unclassified": statement.StatementFailed,
        "user-interrupt": IndexInterrupted,
        "keyboard": KeyboardInterrupt,
        "other": RuntimeError,
        "timer-fired": statement.StatementTimedOut,
    }
    original = errors[kind]

    class CapturedTimer(threading.Timer):
        def start(self) -> None:
            events.append("start")

        def cancel(self) -> None:
            events.append("cancel")

    def factory(timeout_s: float, callback: Callable[[], None]) -> CapturedTimer:
        timer = CapturedTimer(timeout_s, callback)
        timers.append(timer)
        return timer

    class Result:
        columns: tuple[()] = ()

        def fetchmany(self, size: int) -> list[tuple[int, ...]]:
            if kind == "timer-fired":
                timers[0].function()
            raise original

    class Connection:
        def execute(self, sql: str) -> Result:
            if phase == "execute":
                if kind == "timer-fired":
                    timers[0].function()
                raise original
            return Result()

        def interrupt(self) -> None:
            events.append("interrupt")
            interrupt_actions.append("interrupt")

    with pytest.raises(expected_types[kind]) as raised:
        statement.execute_statement(
            cast(IndexConnection, Connection()),
            "SELECT 1",
            max_rows=2,
            timeout_s=0.75,
            timer=factory,
        )

    if kind == "classified":
        assert isinstance(raised.value, statement.StatementRefused)
        assert raised.value.restriction is statement.Restriction.OUTSIDE_INDEX
        assert raised.value.detail == "opaque classified detail"
    elif kind == "unclassified":
        assert isinstance(raised.value, statement.StatementFailed)
        assert raised.value.message == "Binder Error: controlled missing column"
        assert raised.value.hint is None
    elif kind in {"user-interrupt", "keyboard", "other"}:
        assert raised.value is original
    else:
        assert isinstance(raised.value, statement.StatementTimedOut)
        assert raised.value.timeout_s == 0.75

    expected_interrupts = 1 if kind == "timer-fired" else 0
    expected_events = ["start"]
    if expected_interrupts:
        expected_events.append("interrupt")
    expected_events.append("cancel")
    assert events == expected_events
    interrupt_count_before_late_callback = len(interrupt_actions)
    assert interrupt_count_before_late_callback == expected_interrupts
    timers[0].function()
    assert len(interrupt_actions) == interrupt_count_before_late_callback
    assert events == expected_events
    assert not list(home.iterdir())


def test_late_callback_cannot_interrupt_after_timer_start_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    events: list[str] = []
    interrupt_actions: list[str] = []
    timers: list[threading.Timer] = []
    start_error = RuntimeError("controlled timer start failure")

    class CapturedTimer(threading.Timer):
        def start(self) -> None:
            events.append("start")
            raise start_error

        def cancel(self) -> None:
            events.append("cancel")

    def factory(timeout_s: float, callback: Callable[[], None]) -> CapturedTimer:
        timer = CapturedTimer(timeout_s, callback)
        timers.append(timer)
        return timer

    class Connection:
        def execute(self, sql: str) -> IndexResult:
            raise AssertionError(
                "statement execution must not follow timer start failure"
            )

        def interrupt(self) -> None:
            events.append("interrupt")
            interrupt_actions.append("interrupt")

    with pytest.raises(RuntimeError) as raised:
        statement.execute_statement(
            cast(IndexConnection, Connection()),
            "SELECT 1",
            max_rows=2,
            timeout_s=0.75,
            timer=factory,
        )
    assert raised.value is start_error
    assert events == ["start", "cancel"]
    interrupt_count_before_late_callback = len(interrupt_actions)
    assert interrupt_count_before_late_callback == 0
    timers[0].function()
    assert len(interrupt_actions) == interrupt_count_before_late_callback
    assert events == ["start", "cancel"]
    assert not list(home.iterdir())
