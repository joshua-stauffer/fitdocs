"""The query-backed chart source: screening, binding, typed columns, units."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from fitdocs.dashboards import binding
from fitdocs.dashboards.binding import (
    ROW_CAP,
    TODAY,
    TYPE_KINDS,
    QueryChartSource,
    column_kind,
    source_opener,
)
from fitdocs.dashboards.problems import Problem, Source
from fitdocs.dashboards.source import Fetched, SourceUnavailable
from fitdocs.index.location import IndexLocationError
from fitdocs.query import command as query_command
from fitdocs.query.command import (
    OutcomeKind,
    QuerySession,
    ScreenedStatement,
    SessionUnavailable,
    open_session,
)
from fitdocs.query.format import ResultSet
from fitdocs.query.statement import (
    RESTRICTION_TEXT,
    Restriction,
    StatementFailed,
    StatementRefused,
    StatementTimedOut,
)
from fitdocs.render.charts.kit import Column, ValueKind
from tests.dashboards._helpers import query_environment
from tests.dashboards.conftest import IndexedDashboardRoot

PAGE = "training-load"
CHART = "weekly-km"
LINE = 41
DEFAULT_FIX = "Fix the SQL and run `fitdocs dashboard check` again."
PARAMETER_FIX = "Use `$today` for the run date, or write the value into the SQL."
ONE_SELECT_FIX = "Give the chart exactly one SELECT statement."
CAST_FIX = (
    "Cast it in SQL (for example `CAST(x AS TIMESTAMP)`) or leave it out of the SELECT."
)

# -- the design table, both vocabularies -------------------------------------------

NEW_SPELLINGS: dict[str, ValueKind] = {
    **dict.fromkeys(
        (
            "TINYINT",
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "HUGEINT",
            "UTINYINT",
            "USMALLINT",
            "UINTEGER",
            "UBIGINT",
            "UHUGEINT",
            "FLOAT",
            "DOUBLE",
            "DECIMAL",
        ),
        ValueKind.NUMBER,
    ),
    "DATE": ValueKind.DATE,
    **dict.fromkeys(
        ("TIMESTAMP", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP_NS"),
        ValueKind.DATETIME,
    ),
    "INTERVAL": ValueKind.DURATION,
    **dict.fromkeys(("VARCHAR", "ENUM"), ValueKind.CATEGORY),
    "BOOLEAN": ValueKind.BOOLEAN,
}
OLD_SPELLINGS: dict[str, ValueKind] = {
    "NUMBER": ValueKind.NUMBER,
    "Date": ValueKind.DATE,
    "DATETIME": ValueKind.DATETIME,
    "TIMEDELTA": ValueKind.DURATION,
    "STRING": ValueKind.CATEGORY,
    "bool": ValueKind.BOOLEAN,
}
UNSUPPORTED = (
    "TIME",
    "Time",
    "TIMESTAMP WITH TIME ZONE",
    "BIGINT[]",
    "list",
    "STRUCT(a INTEGER)",
    "MAP(VARCHAR, INTEGER)",
    "BLOB",
    "UUID",
    "JSON",
    "dict",
    "BINARY",
    "DECIMAL(18,3)[]",
    "ENUM('a', 'b')[]",
    "date",
    "Bool",
    "",
    "DECIMAL(18",
)


@pytest.mark.parametrize(
    ("type_name", "kind"), [*NEW_SPELLINGS.items(), *OLD_SPELLINGS.items()]
)
def test_column_kind_maps_every_spelling_in_the_design_table(
    type_name: str, kind: ValueKind
) -> None:
    assert column_kind(type_name) is kind


def test_the_table_holds_exactly_the_design_spellings() -> None:
    assert dict(TYPE_KINDS) == {**NEW_SPELLINGS, **OLD_SPELLINGS}


@pytest.mark.parametrize(
    ("type_name", "kind"),
    [
        ("DECIMAL(18,3)", ValueKind.NUMBER),
        ("DECIMAL(38, 10)", ValueKind.NUMBER),
        ("ENUM('a', 'b')", ValueKind.CATEGORY),
        ("ENUM('x (y)', 'z')", ValueKind.CATEGORY),
        ("TIMESTAMP_NS", ValueKind.DATETIME),
    ],
)
def test_column_kind_strips_a_parenthesised_suffix(
    type_name: str, kind: ValueKind
) -> None:
    assert column_kind(type_name) is kind


@pytest.mark.parametrize("type_name", UNSUPPORTED)
def test_column_kind_is_none_for_everything_else(type_name: str) -> None:
    assert column_kind(type_name) is None


# -- sessions -----------------------------------------------------------------------


@dataclass(frozen=True)
class RunCall:
    sql: str
    params: Mapping[str, object]
    max_rows: int
    timeout_s: float


@dataclass
class SpySession:
    """Records ``screen``/``run``/``close``; answers from a script or a real session."""

    inner: QuerySession | None = None
    screened: ScreenedStatement | BaseException | None = None
    result: ResultSet | BaseException | None = None
    screens: list[str] = field(default_factory=list)
    runs: list[RunCall] = field(default_factory=list)
    closed: int = 0

    def screen(self, sql: str) -> ScreenedStatement:
        self.screens.append(sql)
        if isinstance(self.screened, BaseException):
            raise self.screened
        if self.screened is not None:
            return self.screened
        assert self.inner is not None
        return self.inner.screen(sql)

    def run(
        self,
        sql: str,
        *,
        params: Mapping[str, object],
        max_rows: int,
        timeout_s: float,
    ) -> ResultSet:
        self.runs.append(RunCall(sql, dict(params), max_rows, timeout_s))
        if isinstance(self.result, BaseException):
            raise self.result
        if self.result is not None:
            return self.result
        assert self.inner is not None
        return self.inner.run(
            sql, params=params, max_rows=max_rows, timeout_s=timeout_s
        )

    def close(self) -> None:
        self.closed += 1


def source_over(spy: SpySession) -> QueryChartSource:
    return QueryChartSource(cast(QuerySession, spy))


@pytest.fixture
def live(indexed_dashboard_root: IndexedDashboardRoot) -> Iterator[SpySession]:
    fixture = indexed_dashboard_root
    session = open_session(
        fixture.root, query_environment(fixture.environ, fixture.home)
    )
    assert isinstance(session, QuerySession), session
    spy = SpySession(inner=session)
    yield spy
    session.close()


def fetch(
    source: QueryChartSource, sql: str, today: date = date(2021, 9, 13)
) -> Fetched | tuple[Problem, ...]:
    return source.fetch(sql, today=today, page=PAGE, chart=CHART, line=LINE)


def problems_of(answer: Fetched | tuple[Problem, ...]) -> tuple[Problem, ...]:
    assert isinstance(answer, tuple), f"expected problems, got {answer!r}"
    assert answer, "an empty problem tuple"
    for problem in answer:
        assert problem.source is Source.DASHBOARD
        assert (problem.page, problem.chart, problem.line) == (PAGE, CHART, LINE)
        assert problem.message.endswith("."), problem.message
    return answer


def codes(answer: Fetched | tuple[Problem, ...]) -> list[str]:
    return [problem.code for problem in problems_of(answer)]


def fetched(answer: Fetched | tuple[Problem, ...]) -> Fetched:
    assert isinstance(answer, Fetched), f"expected data, got {answer!r}"
    return answer


def result_set(
    columns: tuple[str, ...],
    column_types: tuple[str, ...],
    rows: tuple[tuple[object, ...], ...],
    *,
    truncated: bool = False,
) -> ResultSet:
    return ResultSet(columns, rows, truncated, ROW_CAP, column_types)


def selected(parameters: frozenset[str] = frozenset()) -> ScreenedStatement:
    return ScreenedStatement("SELECT", parameters)


# -- parameters (7.3, 7.4, 7.5) -----------------------------------------------------

# Two activities are indexed, both starting 2021-09-08; a window 5 days back from
# the run date contains them for 2021-09-12 and misses them for 2021-09-14.
WINDOW = (
    "SELECT count(*) AS n FROM activities WHERE CAST(start_utc AS DATE) >= $today - 5"
)


def test_today_is_bound_to_the_injected_run_date(live: SpySession) -> None:
    source = source_over(live)
    inside = fetched(fetch(source, WINDOW, date(2021, 9, 12)))
    outside = fetched(fetch(source, WINDOW, date(2021, 9, 14)))
    assert inside.data.rows[0][0] == 2
    assert outside.data.rows[0][0] == 0
    first, second = live.runs
    assert first.params == {TODAY: date(2021, 9, 12)}
    assert second.params == {TODAY: date(2021, 9, 14)}
    for call in (first, second):
        value = call.params[TODAY]
        assert type(value) is date


def test_today_is_the_only_bound_name() -> None:
    assert TODAY == "today"


def test_no_parameter_is_bound_when_today_is_unused(live: SpySession) -> None:
    source = source_over(live)
    answer = fetched(fetch(source, "SELECT 1 AS n"))
    assert answer.data.rows == ((1,),)
    assert live.runs[0].params == {}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT '$today' AS s",
        "SELECT 'a' AS s -- $today\n",
        "SELECT 'a' AS s /* $today */",
    ],
)
def test_today_in_a_literal_or_comment_is_not_a_use(live: SpySession, sql: str) -> None:
    answer = fetched(fetch(source_over(live), sql))
    assert answer.data.rows[0][0] in {"$today", "a"}
    assert live.runs[0].params == {}


def test_today_among_other_parameters_is_not_bound_when_another_is_refused(
    live: SpySession,
) -> None:
    answer = fetch(source_over(live), "SELECT $today AS a, $min AS b")
    (problem,) = problems_of(answer)
    assert problem.code == "sql_parameter"
    assert "$min" in problem.message and "$today" not in problem.message
    assert live.runs == []


@pytest.mark.parametrize(
    ("sql", "named"),
    [
        ("SELECT $min AS a", "$min"),
        ("SELECT ? AS a", "positional"),
        ("SELECT $1 AS a", "positional"),
    ],
)
def test_other_parameters_are_refused_before_execution(
    live: SpySession, sql: str, named: str
) -> None:
    answer = fetch(source_over(live), sql)
    (problem,) = problems_of(answer)
    assert problem.code == "sql_parameter"
    assert problem.fix == PARAMETER_FIX
    if named == "positional":
        assert problem.message == (
            "The chart's SQL uses positional parameter 1, which a chart does not bind."
        )
    else:
        assert problem.message == (
            "The chart's SQL uses the parameter `$min`, which a chart does not bind."
        )
    assert live.screens == [sql]
    assert live.runs == []


def test_every_refused_parameter_is_named_in_name_order(live: SpySession) -> None:
    answer = fetch(source_over(live), "SELECT $zeta AS a, $alpha AS b, $today AS c")
    found = problems_of(answer)
    assert [p.code for p in found] == ["sql_parameter", "sql_parameter"]
    assert found[0].message == (
        "The chart's SQL uses the parameter `$alpha`, which a chart does not bind."
    )
    assert found[1].message == (
        "The chart's SQL uses the parameter `$zeta`, which a chart does not bind."
    )
    assert live.runs == []


def test_positional_parameters_are_reported_by_their_number(live: SpySession) -> None:
    found = problems_of(fetch(source_over(live), "SELECT ? AS a, ? AS b"))
    assert len(found) == 2
    assert found[0].message == (
        "The chart's SQL uses positional parameter 1, which a chart does not bind."
    )
    assert found[1].message == (
        "The chart's SQL uses positional parameter 2, which a chart does not bind."
    )
    assert found[0].fix == found[1].fix == PARAMETER_FIX
    assert live.runs == []


def test_parameters_come_from_the_screen_result_not_the_database_text() -> None:
    spy = SpySession(
        screened=selected(frozenset({"today"})),
        result=result_set(("n",), ("INTEGER",), ((1,),)),
    )
    fetched(fetch(source_over(spy), "SELECT 1 AS n -- not a use of the parameter"))
    assert spy.runs[0].params == {TODAY: date(2021, 9, 13)}
    unused = SpySession(
        screened=selected(), result=result_set(("n",), ("INTEGER",), ((1,),))
    )
    fetched(fetch(source_over(unused), "SELECT $today AS n"))
    assert unused.runs[0].params == {}


# -- one SELECT (7.2) and failures (7.9) --------------------------------------------


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        (
            "EXPLAIN SELECT 1",
            "The chart's SQL was refused: a chart runs exactly one SELECT "
            "statement; this is an EXPLAIN statement.",
        ),
        (
            "SELECT 1; SELECT 2",
            "The chart's SQL was refused: a chart runs exactly one SELECT statement.",
        ),
        ("", "The chart's SQL was refused: a chart runs exactly one SELECT statement."),
    ],
)
def test_explain_and_several_statements_are_refused(
    live: SpySession, sql: str, message: str
) -> None:
    answer = fetch(source_over(live), sql)
    (problem,) = problems_of(answer)
    assert problem.code == "sql_refused"
    assert problem.message == message
    assert problem.fix == ONE_SELECT_FIX
    assert live.runs == []


def test_explain_names_the_kind_and_wins_over_a_parameter(live: SpySession) -> None:
    answer = fetch(source_over(live), "EXPLAIN SELECT $min AS a")
    (problem,) = problems_of(answer)
    assert problem.code == "sql_refused"
    assert "EXPLAIN" in problem.message
    assert live.runs == []


def test_a_non_select_kind_is_refused_from_the_screen_result() -> None:
    spy = SpySession(screened=ScreenedStatement("EXPLAIN", frozenset()))
    (problem,) = problems_of(fetch(source_over(spy), "EXPLAIN SELECT 1"))
    assert problem.code == "sql_refused"
    assert spy.runs == []


def test_a_select_kind_runs() -> None:
    spy = SpySession(
        screened=selected(), result=result_set(("n",), ("INTEGER",), ((1,),))
    )
    fetched(fetch(source_over(spy), "SELECT 1 AS n"))
    assert len(spy.runs) == 1


def test_a_syntax_error_is_sql_failed_with_the_database_message(
    live: SpySession,
) -> None:
    answer = fetch(source_over(live), "SELEC 1")
    (problem,) = problems_of(answer)
    assert problem.code == "sql_failed"
    assert "syntax error" in problem.message
    assert problem.fix == DEFAULT_FIX
    assert live.runs == []


RUN_REFUSAL_FIXES = {
    Restriction.OUTSIDE_INDEX: (
        "Read only the index's tables; remove the file or address from the SQL."
    ),
    Restriction.LOCKED_SETTING: (
        "Remove the statement that changes a setting from the SQL."
    ),
    Restriction.READ_ONLY: (
        "Remove the statement that writes; a chart only reads the index."
    ),
    Restriction.EXTENSION: "Remove the extension, INSTALL or LOAD from the SQL.",
}


@pytest.mark.parametrize("restriction", list(RUN_REFUSAL_FIXES))
def test_a_run_refusal_keeps_the_query_layer_text_and_has_its_own_fix(
    restriction: Restriction,
) -> None:
    spy = SpySession(
        screened=selected(), result=StatementRefused(restriction, "the-detail")
    )
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert problem.code == "sql_refused"
    assert problem.message == (
        f"The chart's SQL was refused: {RESTRICTION_TEXT[restriction]}: the-detail."
    )
    assert problem.fix == RUN_REFUSAL_FIXES[restriction]
    assert "one SELECT" not in problem.fix


def test_a_live_file_read_is_refused_with_the_remedy_not_the_one_select_fix(
    live: SpySession,
) -> None:
    (problem,) = problems_of(
        fetch(source_over(live), "SELECT * FROM read_csv('/etc/passwd')")
    )
    assert problem.code == "sql_refused"
    assert RESTRICTION_TEXT[Restriction.OUTSIDE_INDEX] in problem.message
    assert problem.fix == RUN_REFUSAL_FIXES[Restriction.OUTSIDE_INDEX]
    assert len(live.runs) == 1


@pytest.mark.parametrize(
    ("restriction", "message"),
    [
        (
            Restriction.ONE_STATEMENT,
            "The chart's SQL was refused: a chart runs exactly one SELECT statement.",
        ),
        (
            Restriction.STATEMENT_KIND,
            "The chart's SQL was refused: a chart runs exactly one SELECT "
            "statement; this is an INSERT statement.",
        ),
    ],
)
def test_a_screen_refusal_uses_the_chart_message_not_the_query_layer_text(
    restriction: Restriction, message: str
) -> None:
    detail = "INSERT" if restriction is Restriction.STATEMENT_KIND else "SELECT"
    spy = SpySession(screened=StatementRefused(restriction, detail))
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1; SELECT 2"))
    assert problem.message == message
    assert problem.fix == ONE_SELECT_FIX
    assert spy.runs == []


def test_the_query_hint_becomes_the_fix() -> None:
    spy = SpySession(
        screened=selected(), result=StatementFailed("boom", "a distinctive hint.")
    )
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert problem.code == "sql_failed"
    assert "boom" in problem.message
    assert problem.fix == "a distinctive hint."
    assert problem.message == "The chart's SQL failed: boom."


def test_a_hint_without_a_capital_or_a_stop_becomes_a_sentence() -> None:
    spy = SpySession(
        screened=selected(),
        result=StatementFailed(
            "boom", "cast TIMESTAMP WITH TIME ZONE values to TIMESTAMP"
        ),
    )
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert problem.fix == "cast TIMESTAMP WITH TIME ZONE values to TIMESTAMP."


def test_a_screen_failure_hint_becomes_the_fix_too() -> None:
    spy = SpySession(screened=StatementFailed("bad parse", "screen hint."))
    (problem,) = problems_of(fetch(source_over(spy), "SELEC"))
    assert problem.code == "sql_failed"
    assert "bad parse" in problem.message
    assert problem.fix == "screen hint."


def test_a_failure_without_a_hint_gets_the_default_fix() -> None:
    spy = SpySession(screened=selected(), result=StatementFailed("boom", None))
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert problem.fix == DEFAULT_FIX


@pytest.mark.parametrize("stage", ["screen", "run"])
def test_a_keyboard_interrupt_propagates(stage: str) -> None:
    if stage == "screen":
        spy = SpySession(screened=KeyboardInterrupt())
    else:
        spy = SpySession(screened=selected(), result=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        fetch(source_over(spy), "SELECT 1")


# -- time limit and row cap (7.6, 7.7) -----------------------------------------------


def test_the_run_uses_the_default_time_limit_and_the_row_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binding, "DEFAULT_TIMEOUT_S", 7.5)
    spy = SpySession(
        screened=selected(), result=result_set(("n",), ("INTEGER",), ((1,),))
    )
    fetched(fetch(source_over(spy), "SELECT 1 AS n"))
    (call,) = spy.runs
    assert call.timeout_s == 7.5
    assert call.max_rows == ROW_CAP == 10_000


def test_the_unpatched_time_limit_is_the_one_fitdocs_query_uses() -> None:
    assert binding.DEFAULT_TIMEOUT_S == query_command.DEFAULT_TIMEOUT_S
    spy = SpySession(
        screened=selected(), result=result_set(("n",), ("INTEGER",), ((1,),))
    )
    fetched(fetch(source_over(spy), "SELECT 1 AS n"))
    assert spy.runs[0].timeout_s == query_command.DEFAULT_TIMEOUT_S


def test_a_timeout_is_sql_timeout_naming_the_limit() -> None:
    spy = SpySession(screened=selected(), result=StatementTimedOut(7.5))
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert problem.code == "sql_timeout"
    assert (
        problem.message
        == "The chart's SQL ran longer than 7.5 seconds and was stopped."
    )
    assert problem.fix == (
        "Make the query cheaper, for example by aggregating in SQL or "
        "narrowing the date range."
    )


def test_ten_thousand_rows_pass_and_one_more_is_the_row_cap(live: SpySession) -> None:
    source = source_over(live)
    sql = "SELECT i FROM range({n}) t(i)"
    at_cap = fetched(fetch(source, sql.format(n=ROW_CAP)))
    assert len(at_cap.data.rows) == 10_000
    assert live.runs[-1].max_rows == ROW_CAP
    over = fetch(source, sql.format(n=ROW_CAP + 1))
    (problem,) = problems_of(over)
    assert problem.code == "row_cap"
    assert problem.message == "The chart's SQL returned more than 10,000 rows."
    assert problem.fix == (
        "Aggregate in SQL (for example GROUP BY week) so the chart gets "
        "at most 10,000 rows."
    )


def test_a_truncated_result_is_the_row_cap_before_any_type_check() -> None:
    spy = SpySession(
        screened=selected(),
        result=result_set(("t",), ("TIME",), ((None,),), truncated=True),
    )
    assert codes(fetch(source_over(spy), "SELECT 1")) == ["row_cap"]


# -- types (8.1, 8.2) ---------------------------------------------------------------

ALL_KINDS_SQL = (
    "SELECT 1::DECIMAL(18,3) AS a, DATE '2021-01-01' AS d, "
    "TIMESTAMP '2021-01-01 05:06:07' AS t, TIMESTAMP_NS '2021-01-02 00:00:00' AS tn, "
    "INTERVAL 90 MINUTE AS i, 'x'::VARCHAR AS v, true AS b, 7::HUGEINT AS h, "
    "'a'::ENUM('a', 'b') AS e, 1.5::FLOAT AS f"
)


def test_a_real_result_carries_every_supported_kind(live: SpySession) -> None:
    answer = fetched(fetch(source_over(live), ALL_KINDS_SQL))
    assert [(c.name, c.kind) for c in answer.data.columns] == [
        ("a", ValueKind.NUMBER),
        ("d", ValueKind.DATE),
        ("t", ValueKind.DATETIME),
        ("tn", ValueKind.DATETIME),
        ("i", ValueKind.DURATION),
        ("v", ValueKind.CATEGORY),
        ("b", ValueKind.BOOLEAN),
        ("h", ValueKind.NUMBER),
        ("e", ValueKind.CATEGORY),
        ("f", ValueKind.NUMBER),
    ]
    assert answer.data.rows == (
        (
            Decimal("1.000"),
            date(2021, 1, 1),
            datetime(2021, 1, 1, 5, 6, 7),
            datetime(2021, 1, 2),
            timedelta(minutes=90),
            "x",
            True,
            7,
            "a",
            1.5,
        ),
    )
    assert str(answer.data.rows[0][0]) == "1.000"


def test_the_session_reports_one_resolvable_type_per_column(live: SpySession) -> None:
    session = live.inner
    assert session is not None
    result = session.run(ALL_KINDS_SQL, params={}, max_rows=10, timeout_s=30.0)
    assert len(result.column_types) == len(result.columns) == 10
    assert [column_kind(name) for name in result.column_types] == [
        ValueKind.NUMBER,
        ValueKind.DATE,
        ValueKind.DATETIME,
        ValueKind.DATETIME,
        ValueKind.DURATION,
        ValueKind.CATEGORY,
        ValueKind.BOOLEAN,
        ValueKind.NUMBER,
        ValueKind.CATEGORY,
        ValueKind.NUMBER,
    ]


UNSUPPORTED_SQL = (
    "SELECT 1 AS first_ok, TIME '01:02:03' AS clock, 'x' AS second_ok, "
    "[1, 2] AS items, {'a': 1} AS box, MAP {'a': 1} AS lookup, "
    "'x'::BLOB AS raw, '{}'::JSON AS doc, gen_random_uuid() AS ident, 2.5 AS last_ok"
)


def test_each_unsupported_column_is_one_column_type_problem(live: SpySession) -> None:
    found = problems_of(fetch(source_over(live), UNSUPPORTED_SQL))
    assert [(p.code, p.column) for p in found] == [
        ("column_type", name)
        for name in ("clock", "items", "box", "lookup", "raw", "doc", "ident")
    ]


def test_column_type_problems_name_the_column_and_the_type_and_fix_with_a_cast() -> (
    None
):
    spy = SpySession(
        screened=selected(),
        result=result_set(
            ("ok", "clock", "ok_too", "items"),
            ("INTEGER", "TIME", "VARCHAR", "BIGINT[]"),
            ((1, None, "x", None),),
        ),
    )
    found = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert [(p.code, p.column) for p in found] == [
        ("column_type", "clock"),
        ("column_type", "items"),
    ]
    assert found[0].message == (
        "Column `clock` has type TIME, which has no chart value kind."
    )
    assert found[1].message == (
        "Column `items` has type BIGINT[], which has no chart value kind."
    )
    assert found[0].fix == found[1].fix == CAST_FIX


def test_a_timestamp_with_time_zone_is_refused_with_a_cast(live: SpySession) -> None:
    answer = fetch(
        source_over(live), "SELECT TIMESTAMPTZ '2021-01-01 00:00:00+00' AS t"
    )
    (problem,) = problems_of(answer)
    assert problem.code in {"sql_failed", "column_type"}
    assert "cast" in problem.fix.lower()


def test_a_length_mismatch_between_names_and_types_is_a_defect() -> None:
    for types in ((), ("INTEGER",), ("INTEGER", "INTEGER", "INTEGER")):
        spy = SpySession(
            screened=selected(),
            result=result_set(("a", "b"), types, ((1, 2),)),
        )
        with pytest.raises(
            RuntimeError,
            match=f"reported {len(types)} column types for 2 columns.*defect",
        ):
            fetch(source_over(spy), "SELECT 1")


# -- values (8.4, 8.5, 8.6) ---------------------------------------------------------


def test_values_reach_the_chart_unconverted_and_null_stays_absent() -> None:
    drift = 0.1 + 0.2
    moment = datetime(2021, 9, 8, 1, 46, 40)
    rows = (
        (Decimal("2.50"), drift, None, "k", moment),
        (None, None, True, None, None),
        (7, 0.0, False, "", moment),
    )
    spy = SpySession(
        screened=selected(),
        result=result_set(
            ("a", "b", "c", "d", "e"),
            ("DECIMAL(18,2)", "DOUBLE", "BOOLEAN", "VARCHAR", "TIMESTAMP"),
            rows,
        ),
    )
    answer = fetched(fetch(source_over(spy), "SELECT 1"))
    assert answer.data.rows == rows
    assert str(answer.data.rows[0][0]) == "2.50"
    assert answer.data.rows[0][1] == 0.30000000000000004
    assert answer.data.rows[1] == (None, None, True, None, None)
    assert answer.data.rows[2][3] == "" and answer.data.rows[2][1] == 0.0
    assert answer.data.rows[0][4] is moment


GOOD_AND_BAD: tuple[tuple[str, object, bool], ...] = (
    ("NUMBER", 3, True),
    ("NUMBER", 3.5, True),
    ("NUMBER", Decimal("3.5"), True),
    ("NUMBER", True, False),
    ("NUMBER", "3", False),
    ("NUMBER", date(2021, 1, 1), False),
    ("Date", date(2021, 1, 1), True),
    ("Date", datetime(2021, 1, 1, 5), False),
    ("Date", "2021-01-01", False),
    ("DATETIME", datetime(2021, 1, 1, 5), True),
    ("DATETIME", datetime(2021, 1, 1, 5, tzinfo=UTC), False),
    ("DATETIME", date(2021, 1, 1), False),
    ("TIMEDELTA", timedelta(seconds=5), True),
    ("TIMEDELTA", 5, False),
    ("STRING", "abc", True),
    ("STRING", 5, False),
    ("STRING", b"abc", False),
    ("bool", True, True),
    ("bool", 1, False),
    ("bool", "true", False),
)


@pytest.mark.parametrize(("type_name", "value", "fits"), GOOD_AND_BAD)
def test_a_value_fits_its_kind_or_is_an_offender(
    type_name: str, value: object, fits: bool
) -> None:
    spy = SpySession(
        screened=selected(),
        result=result_set(("c",), (type_name,), ((None,), (value,), (None,))),
    )
    answer = fetch(source_over(spy), "SELECT 1")
    if fits:
        assert fetched(answer).data.rows == ((None,), (value,), (None,))
    else:
        (problem,) = problems_of(answer)
        assert problem.code == "value_kind"
        assert (problem.column, problem.row, problem.rows) == ("c", 1, 1)


def test_value_kind_names_the_first_row_and_the_count_per_column() -> None:
    values = [1.5, 2.5, "two", 4.5, 5.5, "five", 7.5]
    other = ["a", "b", "c", 1, "e", "f", "g"]
    spy = SpySession(
        screened=selected(),
        result=result_set(
            ("amount", "label"),
            ("DOUBLE", "VARCHAR"),
            tuple(zip(values, other, strict=True)),
        ),
    )
    found = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert [(p.code, p.column, p.row, p.rows) for p in found] == [
        ("value_kind", "amount", 2, 2),
        ("value_kind", "label", 3, 1),
    ]
    assert found[0].message == (
        "Column `amount` holds 2 value(s) that are not number values; "
        "the first is in row 2."
    )
    assert found[1].message == (
        "Column `label` holds 1 value(s) that are not category values; "
        "the first is in row 3."
    )
    assert found[0].fix == (
        "Cast the column in SQL so every value is a number, "
        "or leave it out of the SELECT."
    )
    assert found[1].fix == (
        "Cast the column in SQL so every value is a category, "
        "or leave it out of the SELECT."
    )


def test_a_time_column_is_column_type_not_value_kind() -> None:
    spy = SpySession(
        screened=selected(),
        result=result_set(("clock",), ("TIME",), ((1,),)),
    )
    (problem,) = problems_of(fetch(source_over(spy), "SELECT 1"))
    assert (problem.code, problem.column) == ("column_type", "clock")
    assert problem.message == (
        "Column `clock` has type TIME, which has no chart value kind."
    )


def test_value_kind_is_checked_on_a_real_result(live: SpySession) -> None:
    answer = fetched(
        fetch(
            source_over(live), "SELECT start_utc, sport FROM activities ORDER BY sport"
        )
    )
    assert [c.kind for c in answer.data.columns] == [
        ValueKind.DATETIME,
        ValueKind.CATEGORY,
    ]
    assert [row[1] for row in answer.data.rows] == ["Ride", "Run"]


# -- units (8.3) --------------------------------------------------------------------


def test_units_come_from_the_most_specific_suffix(live: SpySession) -> None:
    answer = fetched(
        fetch(
            source_over(live),
            "SELECT 1.5 AS distance_km, 300.0 AS avg_pace_s_per_km, 7 AS week, "
            "9.5 AS power_w",
        )
    )
    assert answer.data.columns == (
        Column("distance_km", ValueKind.NUMBER, "km"),
        Column("avg_pace_s_per_km", ValueKind.NUMBER, "s_per_km"),
        Column("week", ValueKind.NUMBER, None),
        Column("power_w", ValueKind.NUMBER, "w"),
    )


# -- the chart source's life (7.8, 13.3) ---------------------------------------------


def test_close_closes_the_session_once_per_call() -> None:
    spy = SpySession()
    source = source_over(spy)
    source.close()
    assert spy.closed == 1


def test_the_real_session_stays_usable_across_charts(live: SpySession) -> None:
    source = source_over(live)
    answers = [fetch(source, f"SELECT {n} AS n") for n in (11, 12, 13)]
    assert [fetched(a).data.rows for a in answers] == [((11,),), ((12,),), ((13,),)]
    assert len(live.runs) == 3


# -- source_opener ------------------------------------------------------------------

UNAVAILABLE = [
    (
        SessionUnavailable(OutcomeKind.NOT_BUILT, None, None),
        SourceUnavailable(
            "not_built", "the index is not built.", "Run `fitdocs index` to build it."
        ),
    ),
    (
        SessionUnavailable(OutcomeKind.NEEDS_REBUILD, "the schema is old", None),
        SourceUnavailable(
            "needs_rebuild",
            "the schema is old.",
            "Run `fitdocs index` to rebuild it.",
        ),
    ),
    (
        SessionUnavailable(OutcomeKind.NEEDS_REBUILD, None, None),
        SourceUnavailable(
            "needs_rebuild",
            "the index is incompatible.",
            "Run `fitdocs index` to rebuild it.",
        ),
    ),
    (
        SessionUnavailable(OutcomeKind.BUSY, None, 4242),
        SourceUnavailable(
            "busy",
            "the index is locked by process 4242.",
            "Run the command again once the other fitdocs command finishes.",
        ),
    ),
    (
        SessionUnavailable(OutcomeKind.BUSY, None, None),
        SourceUnavailable(
            "busy",
            "the index is locked.",
            "Run the command again once the other fitdocs command finishes.",
        ),
    ),
    (
        SessionUnavailable(OutcomeKind.UNVERIFIED, None, None),
        SourceUnavailable(
            "unverified",
            "the query sandbox could not be verified.",
            "This is a fitdocs defect; please report it.",
        ),
    ),
    (
        SessionUnavailable(OutcomeKind.UNVERIFIED, "setting X was not locked", None),
        SourceUnavailable(
            "unverified",
            "the query sandbox could not be verified: setting X was not locked.",
            "This is a fitdocs defect; please report it.",
        ),
    ),
]


@pytest.mark.parametrize(("unavailable", "expected"), UNAVAILABLE)
def test_each_unavailable_kind_maps_to_its_message_and_fix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    unavailable: SessionUnavailable,
    expected: SourceUnavailable,
) -> None:
    opened: list[Path] = []

    def fake_open(root: Path, env: object) -> SessionUnavailable:
        opened.append(root)
        return unavailable

    monkeypatch.setattr(binding, "open_session", fake_open)
    env = query_environment({}, tmp_path)
    opener = source_opener(tmp_path / "root", env)
    assert opened == []
    assert opener() == expected
    assert opener() == expected
    assert opened == [tmp_path / "root"]


def test_the_opener_opens_once_and_hands_back_the_same_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spy = SpySession(
        screened=selected(), result=result_set(("n",), ("INTEGER",), ((5,),))
    )
    calls: list[tuple[Path, object]] = []

    def fake_open(root: Path, env: object) -> QuerySession:
        calls.append((root, env))
        return cast(QuerySession, spy)

    monkeypatch.setattr(binding, "open_session", fake_open)
    env = query_environment({}, tmp_path)
    opener = source_opener(tmp_path / "root", env)
    first = opener()
    second = opener()
    assert isinstance(first, QueryChartSource) and second is first
    assert calls == [(tmp_path / "root", env)]
    assert fetched(fetch(first, "SELECT 5 AS n")).data.rows == ((5,),)
    assert spy.screens == ["SELECT 5 AS n"]


def test_a_location_error_propagates_from_the_opener(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_open(root: Path, env: object) -> QuerySession:
        raise IndexLocationError("no such place")

    monkeypatch.setattr(binding, "open_session", fake_open)
    opener = source_opener(tmp_path / "root", query_environment({}, tmp_path))
    with pytest.raises(IndexLocationError):
        opener()


def test_an_empty_root_reports_not_built_and_no_index_appears(
    tmp_path: Path, indexed_dashboard_root: IndexedDashboardRoot
) -> None:
    empty = tmp_path / "empty-root"
    empty.mkdir()
    environ = {
        "HOME": str(tmp_path / "home"),
        "FITDOCS_INDEX_DIR": str(tmp_path / "index-cache"),
    }
    opener = source_opener(empty, query_environment(environ, tmp_path / "home"))
    answer = opener()
    assert isinstance(answer, SourceUnavailable) and answer.state == "not_built"
    assert not (tmp_path / "index-cache").exists()
