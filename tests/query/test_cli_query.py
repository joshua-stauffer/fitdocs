"""CLI contract tests for the read-only analytics query command."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from fitdocs.cli import app
from fitdocs.config import DataRootError
from fitdocs.index.location import IndexLocationError, resolve_index_location
from fitdocs.index.schema import SCHEMA_VERSION
from fitdocs.query.command import (
    DEFAULT_MAX_ROWS,
    DEFAULT_TIMEOUT_S,
    OutcomeKind,
    QueryEnvironment,
    QueryOutcome,
    QueryRequest,
    SchemaReport,
)
from fitdocs.query.format import ResultSet
from fitdocs.query.freshness import PageDrift
from fitdocs.query.schemaview import (
    CatalogColumn,
    CatalogTable,
    IndexState,
    render_schema_text,
)
from fitdocs.query.statement import Restriction
from tests.index._helpers import hold_index
from tests.query.conftest import HomeDirectory

runner = CliRunner()


def _invoke(args: list[str], *, input_text: str | bytes | None = None) -> Result:
    return runner.invoke(app, ["query", *args], input=input_text)


def _state(database: Path, *, version: int | None = SCHEMA_VERSION) -> IndexState:
    return IndexState(
        database=database,
        recorded_schema_version=version,
        reads_schema_version=SCHEMA_VERSION,
        fitdocs_version="fitdocs-test",
        drift=PageDrift(7, 7, 0, 0, 0),
        left_out=(),
        without_computed={},
        athlete=None,
        corpus=None,
        rebuild_reason=None,
    )


def _outcome(
    root: Path,
    home: Path,
    kind: OutcomeKind,
    *,
    result: ResultSet | None = None,
    drift: PageDrift | None = None,
    state: IndexState | None = None,
    schema: SchemaReport | None = None,
    restriction: Restriction | None = None,
    message: str | None = None,
    hint: str | None = None,
    holder_pid: int | None = None,
) -> QueryOutcome:
    location = resolve_index_location(
        root,
        {"FITDOCS_INDEX_DIR": str(root.parent / f"{root.name}-index-cache")},
        home,
    )
    return QueryOutcome(
        kind=kind,
        location=location,
        result=result,
        drift=drift,
        schema=schema,
        state=state,
        restriction=restriction,
        message=message,
        hint=hint,
        holder_pid=holder_pid,
    )


def _mock_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: QueryOutcome,
) -> list[tuple[QueryRequest, QueryEnvironment]]:
    import fitdocs.cli as cli

    calls: list[tuple[QueryRequest, QueryEnvironment]] = []

    def fake_run(request: QueryRequest, env: QueryEnvironment) -> QueryOutcome:
        calls.append((request, env))
        return outcome

    monkeypatch.setattr(cli, "_resolved_data_root", lambda _out: tmp_path)
    monkeypatch.setattr(cli, "run_query", fake_run)
    return calls


def test_help_registers_contract_sentence_and_all_options() -> None:
    result = _invoke(["--help"])
    help_text = " ".join(result.output.split())
    assert result.exit_code == 0
    assert (
        "Run one read-only SQL statement against the analytics index, "
        "or describe its schema." in help_text
    )
    for option in (
        "--file",
        "--schema",
        "--format",
        "--max-rows",
        "--timeout",
        "--out",
    ):
        assert option in help_text
    assert all(word in help_text for word in ("table", "csv", "json"))


def test_stdout_terminal_helper_reads_isatty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitdocs.cli as cli

    class StreamProbe:
        def __init__(self, terminal: bool) -> None:
            self.terminal = terminal

        def isatty(self) -> bool:
            return self.terminal

    for terminal in (False, True):
        monkeypatch.setattr("sys.stdout", StreamProbe(terminal))
        assert cli._stdout_is_terminal() is terminal


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        ([], "exactly one"),
        (["SELECT 1", "--file", "query.sql"], "exactly one"),
        (["-", "--file", "query.sql"], "exactly one"),
        (["--schema", "SELECT 1"], "exactly one"),
        (["--schema", "--file", "query.sql"], "exactly one"),
        (["--schema", "-"], "exactly one"),
        (["--schema", "--format", "csv"], "schema"),
    ],
)
def test_source_and_schema_conflicts_exit_two_before_index(
    args: list[str], fragment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    def forbidden(*_args: object, **_kwargs: object) -> object:
        pytest.fail("invalid CLI input reached index resolution or service")

    monkeypatch.setattr(cli, "_resolved_data_root", forbidden)
    monkeypatch.setattr(cli, "run_query", forbidden)
    result = _invoke(args)
    assert result.exit_code == 2
    assert fragment in result.stderr.lower()


@pytest.mark.parametrize("timeout", ["0", "-0.5", "nan", "inf"])
def test_invalid_timeout_exits_two_before_index(
    timeout: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    monkeypatch.setattr(
        cli, "_resolved_data_root", lambda _out: pytest.fail("root resolved")
    )
    result = _invoke(["SELECT 1", "--timeout", timeout])
    assert result.exit_code == 2
    assert "timeout" in result.stderr.lower()


def test_validation_order_timeout_then_schema_format_then_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitdocs.cli as cli

    monkeypatch.setattr(
        cli, "_resolved_data_root", lambda _out: pytest.fail("root resolved")
    )
    timeout = _invoke(["--schema", "SELECT 1", "--format", "csv", "--timeout", "0"])
    assert timeout.exit_code == 2
    assert "timeout" in timeout.stderr.lower()
    csv = _invoke(["--schema", "SELECT 1", "--format", "csv"])
    assert csv.exit_code == 2
    assert "csv" in csv.stderr.lower()


def test_file_and_explicit_stdin_are_strict_utf8_and_sql_is_untrimmed(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    calls: list[QueryRequest] = []
    expected = ResultSet(("marker",), ((731,),), False, DEFAULT_MAX_ROWS)
    outcome = _outcome(tmp_path, home_dir.path, OutcomeKind.RESULT, result=expected)

    def fake_run(request: QueryRequest, _env: QueryEnvironment) -> QueryOutcome:
        calls.append(request)
        return outcome

    monkeypatch.setattr(cli, "_resolved_data_root", lambda _out: tmp_path)
    monkeypatch.setattr(cli, "run_query", fake_run)
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)
    source = tmp_path / "query.sql"
    source.write_bytes("  SELECT 'café'  \n".encode())
    file_result = _invoke(["--file", str(source)])
    assert (file_result.exit_code, file_result.stdout, file_result.stderr) == (
        0,
        "marker\n731\n",
        "",
    )
    stdin_result = _invoke(["-"], input_text="SELECT 419")
    assert stdin_result.exit_code == 0
    malformed_stdin = _invoke(["-"], input_text=b"SELECT \xff")
    assert malformed_stdin.exit_code == 2
    assert "utf-8" in malformed_stdin.stderr.lower()
    assert calls[0].sql == "  SELECT 'café'  \n"
    assert calls[1].sql == "SELECT 419"
    home_dir.assert_untouched()


def test_bad_empty_and_unreadable_sources_exit_two_without_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    monkeypatch.setattr(
        cli, "_resolved_data_root", lambda _out: pytest.fail("root resolved")
    )
    bad_utf8 = tmp_path / "bad.sql"
    bad_utf8.write_bytes(b"SELECT \xff")
    empty = tmp_path / "empty.sql"
    empty.write_text(" \n\t", encoding="utf-8")
    cases = ((bad_utf8, "utf-8"), (empty, "empty"), (tmp_path / "missing.sql", "read"))
    for path, expected in cases:
        result = _invoke(["--file", str(path)])
        assert result.exit_code == 2
        assert expected in result.stderr.lower()
    positional_whitespace = _invoke(["  \n"])
    assert positional_whitespace.exit_code == 2
    assert "empty" in positional_whitespace.stderr.lower()
    implicit = _invoke([], input_text="SELECT 1")
    assert implicit.exit_code == 2
    assert "exactly one" in implicit.stderr.lower()


def test_comment_only_statement_is_a_gate_refusal(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    calls: list[QueryRequest] = []
    refusal = _outcome(
        tmp_path,
        home_dir.path,
        OutcomeKind.REFUSED,
        restriction=Restriction.ONE_STATEMENT,
        message="facade reported zero statements",
    )

    def fake_run(request: QueryRequest, _env: QueryEnvironment) -> QueryOutcome:
        calls.append(request)
        return refusal

    monkeypatch.setattr(cli, "_resolved_data_root", lambda _out: tmp_path)
    monkeypatch.setattr(cli, "run_query", fake_run)
    result = _invoke(["--format", "json", "--", "-- comment only"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Query refused: fitdocs query runs exactly one statement.\n"
    assert calls[0].sql == "-- comment only"
    home_dir.assert_untouched()


def test_timeout_and_row_limit_are_forwarded_as_distinct_typed_values(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    result_set = ResultSet(("marker",), ((731,),), False, 7)
    outcome = _outcome(tmp_path, home_dir.path, OutcomeKind.RESULT, result=result_set)
    calls = _mock_outcome(monkeypatch, tmp_path, outcome)
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)
    monkeypatch.setattr(cli, "_today", lambda: date(2033, 4, 5))
    result = _invoke(
        ["SELECT 731", "--max-rows", "7", "--timeout", "2.5", "--format", "JsOn"]
    )
    assert (result.exit_code, result.stdout, result.stderr) == (
        0,
        '{"columns": ["marker"], "rows": [\n'
        "[731]\n"
        '], "row_count": 1, "truncated": false, "max_rows": 7, '
        '"freshness": {}}\n',
        "",
    )
    assert len(calls) == 1
    request, env = calls[0]
    assert request.sql == "SELECT 731"
    assert (request.max_rows, request.timeout_s) == (7, 2.5)
    assert request.today == date(2033, 4, 5)
    assert env.home == Path.home()
    assert env.pid == os.getpid() and env.pid != 4317
    assert env.environ is os.environ
    assert env.monotonic is time.monotonic
    assert env.sleep is time.sleep
    assert env.timer is threading.Timer
    home_dir.assert_untouched()


def test_default_limit_timeout_and_explicit_format_contract(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    result_set = ResultSet(("marker",), ((731,),), False, DEFAULT_MAX_ROWS)
    outcome = _outcome(tmp_path, home_dir.path, OutcomeKind.RESULT, result=result_set)
    calls = _mock_outcome(monkeypatch, tmp_path, outcome)
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)
    monkeypatch.setattr(cli, "_today", lambda: date(2033, 4, 5))
    result = _invoke(["SELECT 731"])
    assert result.exit_code == 0
    request, _env = calls[0]
    assert request.max_rows == DEFAULT_MAX_ROWS
    assert request.timeout_s == DEFAULT_TIMEOUT_S
    assert result.stdout == "marker\n731\n"
    home_dir.assert_untouched()


def test_explicit_out_is_passed_to_existing_root_resolver(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    resolved_root = tmp_path / "resolved-data-root"
    explicit_out = tmp_path / "explicit-output-root"
    resolved_root.mkdir()
    explicit_out.mkdir()
    result_set = ResultSet(("marker",), ((731,),), False, DEFAULT_MAX_ROWS)
    outcome = _outcome(
        resolved_root, home_dir.path, OutcomeKind.RESULT, result=result_set
    )
    calls = _mock_outcome(monkeypatch, tmp_path, outcome)
    seen_out: list[Path | None] = []

    def resolve(out: Path | None) -> Path:
        seen_out.append(out)
        return resolved_root

    monkeypatch.setattr(cli, "_resolved_data_root", resolve)
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)
    result = _invoke(["SELECT 1", "--out", str(explicit_out)])
    assert result.exit_code == 0
    assert seen_out == [explicit_out]
    assert calls[0][0].data_root == resolved_root
    home_dir.assert_untouched()


def test_actual_fixture_result_schema_json_and_schema_text_defaults(
    use_indexed_root: tuple[Path, Path],
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitdocs.cli as cli

    root, _index_dir = use_indexed_root
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)
    result = _invoke(["SELECT 731 AS marker", "--out", str(root)])
    assert (result.exit_code, result.stdout, result.stderr) == (0, "marker\n731\n", "")
    schema_json = _invoke(["--schema", "--format", "json", "--out", str(root)])
    assert schema_json.exit_code == 0
    parsed = json.loads(schema_json.stdout)
    assert parsed["index"]["schema_version"] == SCHEMA_VERSION
    assert "pages" in {table["name"] for table in parsed["tables"]}
    schema_text_piped = _invoke(["--schema", "--out", str(root)])
    assert schema_text_piped.exit_code == 0
    assert "Database:" in schema_text_piped.stdout
    assert schema_text_piped.stderr == ""
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: True)
    schema_text = _invoke(["--schema", "--out", str(root)])
    assert schema_text.exit_code == 0
    assert "Database:" in schema_text.stdout
    assert schema_text.stderr == ""
    home_dir.assert_untouched()
    assert root.is_dir()


def test_default_result_format_switches_with_tty_and_explicit_wins(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    result_set = ResultSet(("marker",), ((731,),), False, DEFAULT_MAX_ROWS)
    outcome = _outcome(tmp_path, home_dir.path, OutcomeKind.RESULT, result=result_set)
    _mock_outcome(monkeypatch, tmp_path, outcome)
    for terminal, args, expected in (
        (False, ["SELECT 1"], "marker\n731\n"),
        (True, ["SELECT 1"], "marker\n------\n   731\n(1 row)\n"),
        (True, ["SELECT 1", "--format", "csv"], "marker\n731\n"),
    ):
        monkeypatch.setattr(
            cli, "_stdout_is_terminal", lambda terminal=terminal: terminal
        )
        result = _invoke(args)
        assert result.exit_code == 0
        assert result.stdout == expected
        assert result.stderr == ""
    home_dir.assert_untouched()


def test_schema_csv_parser_limits_and_format_choices_are_usage_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitdocs.cli as cli

    monkeypatch.setattr(
        cli, "_resolved_data_root", lambda _out: pytest.fail("root resolved")
    )
    for args in (
        ["--schema", "--format", "CSV"],
        ["SELECT 1", "--max-rows", "0"],
        ["SELECT 1", "--max-rows", "many"],
        ["SELECT 1", "--format", "yaml"],
        ["SELECT 1", "--timeout", "soon"],
    ):
        result = _invoke(args)
        assert result.exit_code == 2


def test_result_not_built_behind_truncated_and_waiting_streams(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)
    not_built = _outcome(tmp_path, home_dir.path, OutcomeKind.NOT_BUILT)
    _mock_outcome(monkeypatch, tmp_path, not_built)
    missing = _invoke(["SELECT 1"])
    assert (missing.exit_code, missing.stdout, missing.stderr) == (
        1,
        "",
        "Index: not built; run 'fitdocs index' to build it.\n",
    )

    drift = PageDrift(10, 10, 2, 3, 5)
    behind = _outcome(
        tmp_path,
        home_dir.path,
        OutcomeKind.RESULT,
        result=ResultSet(("marker",), ((731,),), True, 1),
        drift=drift,
    )
    calls: list[tuple[QueryRequest, QueryEnvironment]] = []

    def busy_after_wait(request: QueryRequest, env: QueryEnvironment) -> QueryOutcome:
        calls.append((request, env))
        env.on_wait(4317)
        return behind

    monkeypatch.setattr(cli, "run_query", busy_after_wait)
    result = _invoke(["SELECT 731", "--max-rows", "1"])
    assert result.exit_code == 0
    assert result.stdout == "marker\n731\n"
    assert result.stderr.splitlines() == [
        "Index: waiting for another process (process 4317) to finish "
        "writing the index…",
        "Index: behind the data root (2 added, 3 changed, 5 removed pages "
        "since the last refresh); run 'fitdocs index' to bring it level.",
        "Query: showing the first 1 rows; the result has more. Narrow or "
        "aggregate the query, or raise --max-rows.",
    ]
    assert len(calls) == 1
    home_dir.assert_untouched()


def test_outcome_error_categories_keep_exact_typed_messages_and_codes(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    categories: list[tuple[QueryOutcome, int, str]] = [
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.UNVERIFIED,
                message="the sandbox setting enable_external_access is false, not true",
            ),
            1,
            "Query not run: the sandbox setting enable_external_access is "
            "false, not true. This is a fitdocs defect; please report it.",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.UNVERIFIED,
                message="the sandbox setting enable_external_access is NULL, not true",
            ),
            1,
            "Query not run: the sandbox setting enable_external_access is "
            "NULL, not true. This is a fitdocs defect; please report it.",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.ONE_STATEMENT,
                message="ONE_STATEMENT",
            ),
            1,
            "Query refused: fitdocs query runs exactly one statement.",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.STATEMENT_KIND,
                message="CALL",
            ),
            1,
            "Query refused: the query sandbox runs only queries and EXPLAIN; "
            "this is a CALL statement; use SELECT * FROM <function>(…) instead.",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.STATEMENT_KIND,
                message="LOAD",
            ),
            1,
            "Query refused: the query sandbox runs only queries and EXPLAIN; "
            "this is an INSTALL or LOAD statement.",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.STATEMENT_KIND,
                message="SET",
            ),
            1,
            "Query refused: the query sandbox runs only queries and EXPLAIN; "
            "this is a SET, RESET or USE statement.",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.OUTSIDE_INDEX,
                message="IO Error: denied path /private/value",
            ),
            1,
            "Query refused: the query sandbox cannot read or write files or "
            "addresses outside the index.\nDuckDB: IO Error: denied path "
            "/private/value",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.LOCKED_SETTING,
                message="Invalid Input Error: setting locked",
            ),
            1,
            "Query refused: the query sandbox's settings are locked.\n"
            "DuckDB: Invalid Input Error: setting locked",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.READ_ONLY,
                message="Catalog Error: read only",
            ),
            1,
            "Query refused: the index is open read-only.\n"
            "DuckDB: Catalog Error: read only",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.REFUSED,
                restriction=Restriction.EXTENSION,
                message="Extension Error: extension disabled",
            ),
            1,
            "Query refused: extensions are not available in the query sandbox.\n"
            "DuckDB: Extension Error: extension disabled",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.FAILED,
                message="[red]Binder Error[/red]: missing column",
                hint="[blue]Check the column name.[/blue]",
            ),
            1,
            "Query failed: [red]Binder Error[/red]: missing column\n"
            "Hint: [blue]Check the column name.[/blue]",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.FAILED,
                message="Parser Error: bad SQL",
            ),
            1,
            "Query failed: Parser Error: bad SQL",
        ),
        (
            _outcome(
                tmp_path,
                home_dir.path,
                OutcomeKind.TIMED_OUT,
                message="database timeout expired after a different duration",
            ),
            1,
            "Query stopped: it ran longer than 2.5 s. Narrow it, or raise --timeout.",
        ),
        (
            _outcome(tmp_path, home_dir.path, OutcomeKind.BUSY, holder_pid=4317),
            1,
            "Index: still locked after 10 s by process 4317: a fitdocs command "
            "is refreshing it, or another program has it open for writing. "
            "Run the query again once that finishes.",
        ),
    ]
    for outcome, expected_code, expected_stderr in categories:
        _mock_outcome(monkeypatch, tmp_path, outcome)
        result = _invoke(["SELECT 1", "--timeout", "2.5"])
        assert result.exit_code == expected_code
        assert result.stdout == ""
        assert result.stderr.rstrip("\n") == expected_stderr
    home_dir.assert_untouched()


def test_schema_failure_state_is_printed_and_missing_descriptions_split_streams(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _state(tmp_path / "missing" / "index.duckdb", version=99)
    needs_rebuild = _outcome(
        tmp_path,
        home_dir.path,
        OutcomeKind.NEEDS_REBUILD,
        state=state,
        message=(
            f"index schema version 99 differs from readable schema version "
            f"{SCHEMA_VERSION}"
        ),
    )
    _mock_outcome(monkeypatch, tmp_path, needs_rebuild)
    failed = _invoke(["--schema"])
    assert failed.exit_code == 1
    assert "Recorded schema version: 99" in failed.stderr
    assert (
        f"Index: index schema version 99 differs from readable schema version "
        f"{SCHEMA_VERSION}; run 'fitdocs index' to rebuild it." in failed.stderr
    )

    import fitdocs.cli as cli

    table = CatalogTable(
        "special_table", None, (CatalogColumn("special_value", "VARCHAR", None, None),)
    )
    report = SchemaReport(
        state=_state(tmp_path / "index.duckdb"),
        tables=(table,),
        counts={"special_table": 4},
    )
    schema = _outcome(
        tmp_path,
        home_dir.path,
        OutcomeKind.SCHEMA,
        drift=PageDrift(10, 7, 1, 2, 3),
        schema=report,
    )
    _mock_outcome(monkeypatch, tmp_path, schema)
    rendered = render_schema_text(report.state, report.tables, report.counts)
    warning_lines = [
        "Index: behind the data root (1 added, 2 changed, 3 removed pages "
        "since the last refresh); run 'fitdocs index' to bring it level.",
        "Schema: special_table has no description. This is a fitdocs defect; "
        "please report it.",
        "Schema: special_table.special_value has no description. This is a "
        "fitdocs defect; please report it.",
    ]
    for terminal in (False, True):
        monkeypatch.setattr(
            cli, "_stdout_is_terminal", lambda terminal=terminal: terminal
        )
        result = _invoke(["--schema"])
        assert result.exit_code == 0
        assert result.stdout == rendered + "\n"
        assert (
            "fitdocs defect: missing descriptions for: special_table, "
            "special_table.special_value" in result.stdout
        )
        assert result.stderr.splitlines() == warning_lines
    home_dir.assert_untouched()


def test_actual_absent_index_and_schema_version_99_are_typed_cli_outcomes(
    copy_indexed_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli
    from fitdocs.index.store import open_index

    root, index_dir = copy_indexed_root
    absent_index_base = root.parent / "empty-index-cache"
    absent_index_base.mkdir()
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(absent_index_base))
    monkeypatch.setattr(cli, "_today", lambda: date(2024, 4, 5))
    absent = _invoke(["SELECT 1", "--out", str(root)])
    assert absent.exit_code == 1
    assert "run 'fitdocs index' to build it" in absent.stderr
    schema_absent = _invoke(["--schema", "--out", str(root)])
    assert schema_absent.exit_code == 1
    assert schema_absent.stdout == ""
    assert "run 'fitdocs index' to build it" in schema_absent.stderr
    with open_index(index_dir / "index.duckdb", read_only=False) as connection:
        connection.execute("UPDATE index_meta SET schema_version = 99")
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir.parent))
    incompatible = _invoke(["--schema", "--out", str(root)])
    assert incompatible.exit_code == 1
    assert "Recorded schema version: 99" in incompatible.stderr
    assert (
        f"index schema version 99 differs from readable schema version {SCHEMA_VERSION}"
        in incompatible.stderr
    )
    assert "run 'fitdocs index' to rebuild it" in incompatible.stderr
    assert tuple(Path(os.environ["HOME"]).iterdir()) == ()


def test_real_busy_holder_uses_fixture_pid_not_controlled_pid(
    copy_indexed_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir = copy_indexed_root
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir.parent))
    with hold_index(index_dir / "index.duckdb", read_only=False) as holder_pid:
        result = _invoke(["SELECT 1", "--out", str(root)])
    assert result.exit_code == 1
    assert "waiting for another process" in result.stderr
    assert str(holder_pid) in result.stderr
    assert holder_pid != 4317
    assert tuple(Path(os.environ["HOME"]).iterdir()) == ()


def test_data_root_and_index_location_errors_exit_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fitdocs.cli as cli

    monkeypatch.setattr(
        cli,
        "resolve_data_root",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            DataRootError("cannot resolve data root")
        ),
    )
    root = _invoke(["SELECT 1"])
    assert root.exit_code == 2
    assert "cannot resolve data root" in root.stderr

    monkeypatch.setattr(cli, "_resolved_data_root", lambda _out: tmp_path)

    def bad_location(request: QueryRequest, _env: QueryEnvironment) -> QueryOutcome:
        raise IndexLocationError("index directory lies inside the data root")

    monkeypatch.setattr(cli, "run_query", bad_location)
    location = _invoke(["SELECT 1"])
    assert location.exit_code == 2
    assert "index directory lies inside the data root" in location.stderr


def test_registered_command_count_and_module_help_count() -> None:
    import typer.core
    import typer.main

    import fitdocs.cli as cli

    command = typer.main.get_command(app)
    assert isinstance(command, typer.core.TyperGroup)
    assert len(command.commands) == 13
    assert "Thirteen" in (cli.__doc__ or "")[:400]


@pytest.mark.parametrize(
    "args",
    [
        ["SELECT 1", "--format", "table"],
        ["SELECT 1", "--format", "csv"],
        ["SELECT 1", "--format", "json"],
        ["--schema"],
        ["--schema", "--format", "json"],
    ],
    ids=["table", "csv", "json", "schema-text", "schema-json"],
)
def test_stdout_ends_with_exactly_one_newline(
    args: list[str],
    tmp_path: Path,
    home_dir: HomeDirectory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitdocs.cli as cli

    report = SchemaReport(
        _state(tmp_path / "index.duckdb"),
        (
            CatalogTable(
                "t", "described", (CatalogColumn("c", "INTEGER", None, "described"),)
            ),
        ),
        {"t": 1},
    )
    if "--schema" in args:
        outcome = _outcome(tmp_path, home_dir.path, OutcomeKind.SCHEMA, schema=report)
    else:
        outcome = _outcome(
            tmp_path,
            home_dir.path,
            OutcomeKind.RESULT,
            result=ResultSet(("marker",), ((731,),), False, DEFAULT_MAX_ROWS),
        )
    _mock_outcome(monkeypatch, tmp_path, outcome)
    monkeypatch.setattr(cli, "_stdout_is_terminal", lambda: False)

    result = _invoke(args)

    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() != ""
    assert result.stdout.endswith("\n")
    assert not result.stdout.endswith("\n\n")
