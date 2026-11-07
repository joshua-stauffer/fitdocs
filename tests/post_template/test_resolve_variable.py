"""Resolve one variable for one page (post-templates task 2.4).

Requirements 3.1, 3.2, 3.4 to 3.9. The value cases run against a real sandboxed
session over the synthetic index of `_index.py`, so the binding, the row cap,
a real timeout, a real failure and a real sandbox refusal use the production
paths. Values DuckDB cannot produce (a decimal with an exponent, NaN) go
straight to `to_text`. A fake session is used only for Ctrl-C, the error
mappings a real statement cannot reach, and to record the exact arguments
passed to `run`. Where a test names the whole expected `VariableOutcome`, an
extra or missing field is red; the others assert the fields they are about.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from fitdocs.post_template.model import Binding, FillCode, VariableOutcome
from fitdocs.post_template.resolve import (
    _TIMESTAMP_ADVICE,
    RESOLVE_MAX_ROWS,
    SessionResolver,
    ValueRefusal,
    open_resolver,
    to_text,
)
from fitdocs.post_template.template import Variable
from fitdocs.query.command import QuerySession, ScreenedStatement
from fitdocs.query.format import ResultSet
from fitdocs.query.statement import (
    TIMESTAMPTZ_HINT,
    Restriction,
    StatementFailed,
    StatementRefused,
    StatementTimedOut,
)
from tests.post_template._index import (
    AM,
    EXAMPLE_SHARE,
    EXAMPLE_SQL,
    MON,
    PAGES,
    PM,
    REST,
    FixturePage,
    IndexedPostRoot,
)

_TIMEOUT = 30.0


def _var(sql: str, name: str = "v") -> Variable:
    return Variable(name, sql)


def _binding(page: FixturePage) -> Binding:
    return Binding(page.start, page.key)


def _ok(value: str | None, name: str = "v") -> VariableOutcome:
    return VariableOutcome(name, value, None, None)


@pytest.fixture(scope="module")
def resolver(indexed_post_root: IndexedPostRoot) -> Iterator[SessionResolver]:
    opened = open_resolver(
        indexed_post_root.root, indexed_post_root.query_environment()
    )
    assert isinstance(opened, SessionResolver)
    yield opened
    opened.close()


def _resolve(
    resolver: SessionResolver,
    sql: str,
    page: FixturePage = MON,
    *,
    timeout_s: float = _TIMEOUT,
) -> VariableOutcome:
    return resolver.resolve(_var(sql), _binding(page), timeout_s=timeout_s)


# --------------------------------------------------------------------------- #
# The design's example, and the zero-load week
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("page", PAGES, ids=[p.name for p in PAGES])
def test_the_example_share_of_each_page(
    resolver: SessionResolver, page: FixturePage
) -> None:
    expected = EXAMPLE_SHARE[page.name]
    assert _resolve(resolver, EXAMPLE_SQL, page) == _ok(
        None if expected is None else str(expected)
    )


def test_a_zero_load_week_is_absent_through_nullif_not_an_error_or_zero(
    resolver: SessionResolver,
) -> None:
    outcome = _resolve(resolver, EXAMPLE_SQL, REST)
    assert outcome == VariableOutcome("v", None, None, None)
    # Without NULLIF the same week divides by zero: the absence is the SQL's.
    unguarded = EXAMPLE_SQL.replace("NULLIF(sum(load_value), 0)", "sum(load_value)")
    assert unguarded != EXAMPLE_SQL
    assert _resolve(resolver, unguarded, REST).value != "0"


# --------------------------------------------------------------------------- #
# Binding: $as_of (naive local start) and $page_key, exactly what is used
# --------------------------------------------------------------------------- #

_SAME_DAY = (
    "SELECT sum(CAST(load_value AS INTEGER)) FROM pages "
    "WHERE date = CAST($as_of AS DATE) AND start_time_local <= $as_of"
)


@pytest.mark.parametrize(
    ("page", "expected"),
    [(AM, "45"), (PM, "70"), (MON, "35")],
    ids=["am-excludes-the-later-pm", "pm-counts-the-earlier-am", "alone-on-its-day"],
)
def test_as_of_is_the_start_so_a_later_workout_on_the_same_day_is_excluded(
    resolver: SessionResolver, page: FixturePage, expected: str
) -> None:
    assert _resolve(resolver, _SAME_DAY, page) == _ok(expected)


@pytest.mark.parametrize("page", PAGES, ids=[p.name for p in PAGES])
def test_as_of_is_bound_as_the_naive_wall_clock_to_the_second(
    resolver: SessionResolver, page: FixturePage
) -> None:
    sql = "SELECT CAST($as_of AS VARCHAR)"
    assert _resolve(resolver, sql, page) == _ok(page.start.isoformat(sep=" "))


def test_as_of_keeps_fractional_seconds(resolver: SessionResolver) -> None:
    moment = datetime(2021, 9, 8, 17, 40, 1, 250000)
    outcome = resolver.resolve(
        _var("SELECT CAST($as_of AS VARCHAR)"),
        Binding(moment, PM.key),
        timeout_s=_TIMEOUT,
    )
    assert outcome == _ok("2021-09-08 17:40:01.25")


_OWN_LOAD = (
    "SELECT CAST(load_value AS INTEGER) FROM pages "
    "WHERE page_key = $page_key AND start_time_local <= $as_of"
)


@pytest.mark.parametrize(
    ("page", "expected"),
    [(MON, "35"), (AM, "45"), (PM, "25")],
    ids=["mon", "am", "pm"],
)
def test_page_key_is_bound_whole_and_names_the_pages_own_row(
    resolver: SessionResolver, page: FixturePage, expected: str
) -> None:
    assert _resolve(resolver, _OWN_LOAD, page) == _ok(expected)


def test_page_key_is_the_key_text_untouched(resolver: SessionResolver) -> None:
    assert _resolve(resolver, "SELECT $page_key", PM) == _ok(PM.key)
    assert _resolve(resolver, "SELECT $page_key", AM) == _ok(AM.key)


def test_a_page_that_records_no_archived_base_binds_null_and_finds_no_row(
    resolver: SessionResolver,
) -> None:
    outcome = resolver.resolve(
        _var(_OWN_LOAD), Binding(PM.start, None), timeout_s=_TIMEOUT
    )
    assert outcome == _ok(None)


def test_a_page_with_no_archived_base_binds_a_real_null_not_empty_text(
    resolver: SessionResolver,
) -> None:
    sql = "SELECT CASE WHEN $page_key IS NULL THEN 'null' ELSE 'set' END"
    assert resolver.resolve(
        _var(sql), Binding(PM.start, None), timeout_s=_TIMEOUT
    ) == _ok("null")
    assert resolver.resolve(
        _var(sql), Binding(PM.start, ""), timeout_s=_TIMEOUT
    ) == _ok("set")


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("SELECT 5", None),
        ("SELECT NULL", None),
        ("SELECT TRUE", FillCode.VALUE_REFUSED),
        ("SELECT 1, 2", FillCode.SHAPE_INVALID),
        ("SELECT nosuchcolumn", FillCode.STATEMENT_FAILED),
    ],
)
def test_every_outcome_carries_the_variables_own_name(
    resolver: SessionResolver, sql: str, code: FillCode | None
) -> None:
    outcome = resolver.resolve(
        _var(sql, "share_name"), _binding(MON), timeout_s=_TIMEOUT
    )
    assert outcome.name == "share_name"
    assert outcome.code is code


def test_only_the_parameters_the_statement_uses_are_bound(
    resolver: SessionResolver,
) -> None:
    # DuckDB rejects an extra parameter, so binding both names would fail these.
    assert _resolve(resolver, "SELECT CAST($as_of AS DATE)", PM) == _ok("2021-09-08")
    assert _resolve(resolver, "SELECT length($page_key)", PM) == _ok("64")
    assert _resolve(resolver, "SELECT 7", PM) == _ok("7")


class _Spy:
    """A fake session that records what the resolver asks of it."""

    def __init__(
        self,
        *,
        parameters: frozenset[str] = frozenset({"as_of"}),
        kind: str = "SELECT",
        screen: Callable[[str], ScreenedStatement] | None = None,
        run: Callable[..., ResultSet] | None = None,
        current: Callable[..., bool] | None = None,
    ) -> None:
        self.runs: list[dict[str, Any]] = []
        self.screens: list[str] = []
        self.currents: list[tuple[Any, ...]] = []
        self._screen = screen or (lambda _sql: ScreenedStatement(kind, parameters))
        self._run = run or (lambda *_a, **_k: ResultSet(("v",), ((1,),), False, 2))
        self._current = current or (lambda *_a: True)

    def screen(self, sql: str) -> ScreenedStatement:
        self.screens.append(sql)
        return self._screen(sql)

    def run(self, sql: str, **kwargs: Any) -> ResultSet:
        self.runs.append({"sql": sql, **kwargs})
        return self._run(sql, **kwargs)

    def page_is_current(self, page_key: str | None, path: str, data: bytes) -> bool:
        self.currents.append((page_key, path, data))
        return self._current(page_key, path, data)

    def close(self) -> None:  # pragma: no cover - the protocol needs it
        pass


def _fake(spy: _Spy) -> SessionResolver:
    return SessionResolver(cast(QuerySession, spy))


def test_the_statement_runs_with_the_two_row_cap_the_timeout_and_its_own_params() -> (
    None
):
    spy = _Spy(parameters=frozenset({"as_of", "page_key"}))
    moment = datetime(2021, 9, 8, 17, 40)
    outcome = _fake(spy).resolve(
        _var("SELECT 1 -- sql"), Binding(moment, "KEY"), timeout_s=4.5
    )
    assert outcome == _ok("1")
    assert RESOLVE_MAX_ROWS == 2
    assert spy.runs == [
        {
            "sql": "SELECT 1 -- sql",
            "params": {"as_of": moment, "page_key": "KEY"},
            "max_rows": 2,
            "timeout_s": 4.5,
        }
    ]
    assert spy.screens == ["SELECT 1 -- sql"]


def test_a_statement_using_one_parameter_is_given_only_that_one() -> None:
    for names, expected in (
        (frozenset({"as_of"}), {"as_of": datetime(2021, 9, 8)}),
        (frozenset({"page_key"}), {"page_key": "KEY"}),
        (frozenset(), {}),
    ):
        spy = _Spy(parameters=names)
        _fake(spy).resolve(
            _var("SELECT 1"), Binding(datetime(2021, 9, 8), "KEY"), timeout_s=1.0
        )
        assert spy.runs[0]["params"] == expected


# --------------------------------------------------------------------------- #
# Shape: one column, at most one row; none or NULL is absent
# --------------------------------------------------------------------------- #

_TWO_ROWS = "SELECT CAST(load_value AS INTEGER) FROM pages WHERE $as_of IS NOT NULL"


@pytest.mark.parametrize(
    ("sql", "detail"),
    [
        (
            "SELECT 1 UNION ALL SELECT 2",
            "must return at most one row; it returned more than one",
        ),
        (_TWO_ROWS, "must return at most one row; it returned more than one"),
        ("SELECT 1, 2", "must return one column; it returned 2"),
        # Shape is checked before absence: no rows from two columns is wrong.
        ("SELECT 1, 2 WHERE false", "must return one column; it returned 2"),
        ("SELECT 1, 2, 3", "must return one column; it returned 3"),
    ],
    ids=[
        "two-rows",
        "four-rows",
        "two-columns",
        "two-columns-no-rows",
        "three-columns",
    ],
)
def test_more_than_one_row_or_column_is_refused(
    resolver: SessionResolver, sql: str, detail: str
) -> None:
    assert _resolve(resolver, sql) == VariableOutcome(
        "v", None, FillCode.SHAPE_INVALID, detail
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 WHERE false",
        "SELECT NULL",
        "SELECT CAST(NULL AS INTEGER)",
        "SELECT CAST(NULL AS VARCHAR)",
        "SELECT CAST(NULL AS BOOLEAN)",
        "SELECT CAST(NULL AS DOUBLE)",
    ],
)
def test_no_rows_or_a_single_null_is_absent_whatever_the_type(
    resolver: SessionResolver, sql: str
) -> None:
    assert _resolve(resolver, sql) == VariableOutcome("v", None, None, None)


# --------------------------------------------------------------------------- #
# Values that pass
# --------------------------------------------------------------------------- #

_PASSING: dict[str, tuple[str, str]] = {
    "int": ("SELECT 42", "42"),
    "zero-is-a-value-not-absent": ("SELECT 0", "0"),
    "negative-int": ("SELECT -7", "-7"),
    "bigint-max": ("SELECT 9223372036854775807", "9223372036854775807"),
    "bigint-min": ("SELECT -9223372036854775807 - 1", "-9223372036854775808"),
    "hugeint": (
        "SELECT 170141183460469231731687303715884105727::HUGEINT",
        "170141183460469231731687303715884105727",
    ),
    "tinyint": ("SELECT 5::TINYINT", "5"),
    "decimal-keeps-trailing-zeros": ("SELECT 1.50::DECIMAL(5, 2)", "1.50"),
    "decimal-small": ("SELECT 0.00001::DECIMAL(10, 5)", "0.00001"),
    "decimal-negative": ("SELECT -3.25::DECIMAL(5, 2)", "-3.25"),
    "decimal-whole": ("SELECT 100::DECIMAL(5, 0)", "100"),
    "decimal-zero": ("SELECT 0.00::DECIMAL(5, 2)", "0.00"),
    "date": ("SELECT DATE '2021-09-08'", "2021-09-08"),
    "date-from-timestamp-cast": (
        "SELECT CAST(TIMESTAMP '2021-09-08 23:59:59' AS DATE)",
        "2021-09-08",
    ),
    "text": ("SELECT 'Tempo'", "Tempo"),
    "empty-text-is-a-value-not-absent": ("SELECT ''", ""),
    "text-with-edge-whitespace": ("SELECT '  a b  '", "  a b  "),
    "text-with-tab": ("SELECT 'a' || chr(9) || 'b'", "a\tb"),
    "text-with-braces": ("SELECT '{x} {{y}}'", "{x} {{y}}"),
    "text-with-unicode": ("SELECT 'Zürich — 10 km 🏃'", "Zürich — 10 km 🏃"),
    "text-with-near-marker-open": ("SELECT '<!- x'", "<!- x"),
    "text-with-near-marker-close": ("SELECT '-- >'", "-- >"),
    "text-with-near-marker-bang": ("SELECT '--!'", "--!"),
    "text-with-double-dash": ("SELECT 'a--b'", "a--b"),
}


@pytest.mark.parametrize(("sql", "expected"), _PASSING.values(), ids=_PASSING.keys())
def test_integers_decimals_dates_and_safe_text_pass(
    resolver: SessionResolver, sql: str, expected: str
) -> None:
    assert _resolve(resolver, sql) == _ok(expected)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1E+2"), "100"),
        (Decimal("-1.5E+3"), "-1500"),
        (Decimal("1E-7"), "0.0000001"),
        (Decimal("0.00001"), "0.00001"),
        (Decimal("1.50"), "1.50"),
        (Decimal("-0.5"), "-0.5"),
        (
            Decimal("123456789012345678901234567890.123456789"),
            "123456789012345678901234567890.123456789",
        ),
    ],
)
def test_a_decimal_is_written_without_an_exponent_and_with_its_digits(
    value: Decimal, expected: str
) -> None:
    assert to_text(value) == expected


def test_python_would_print_these_decimals_with_an_exponent() -> None:
    # The premise of the test above: str() is not what the post may carry.
    assert str(Decimal("1E+2")) == "1E+2"
    assert str(Decimal("1E-7")) == "1E-7"


@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_a_decimal_that_is_not_finite_is_refused(value: Decimal) -> None:
    assert isinstance(to_text(value), ValueRefusal)


def test_the_date_text_is_iso() -> None:
    assert to_text(date(2021, 9, 8)) == "2021-09-08"
    assert to_text(date(1999, 1, 2)) == "1999-01-02"


# --------------------------------------------------------------------------- #
# Values that are refused, each with advice
# --------------------------------------------------------------------------- #

_REFUSED: dict[str, tuple[str, tuple[str, ...]]] = {
    "bool-true": ("SELECT TRUE", ("boolean", "to text")),
    "bool-false": ("SELECT FALSE", ("boolean", "to text")),
    "bool-from-comparison": ("SELECT 1 = 1", ("boolean", "to text")),
    "double": ("SELECT 1.5::DOUBLE", ("floating-point", "::DECIMAL")),
    "whole-double": ("SELECT 2::DOUBLE", ("floating-point", "::DECIMAL")),
    "float": ("SELECT 1.5::FLOAT", ("floating-point", "::DECIMAL")),
    "round-without-cast": (
        "SELECT round(12.3456::DOUBLE, 1)",
        ("floating-point", "::DECIMAL"),
    ),
    "timestamp": (
        "SELECT TIMESTAMP '2021-09-08 06:05:00'",
        ("timestamp", "to text", "DATE"),
    ),
    "timestamp-at-midnight": (
        "SELECT TIMESTAMP '2021-09-08 00:00:00'",
        ("timestamp", "to text", "DATE"),
    ),
    "time": ("SELECT TIME '06:05:00'", ("time value", "to text")),
    "interval": ("SELECT INTERVAL 3 DAY", ("timedelta value", "to text")),
    "blob": ("SELECT 'abc'::BLOB", ("bytes value", "to text")),
    "list": ("SELECT [1, 2]", ("list value", "to text")),
    "struct": ("SELECT {'a': 1}", ("dict value", "to text")),
    "uuid": (
        "SELECT '00000000-0000-0000-0000-000000000001'::UUID",
        ("UUID value", "to text"),
    ),
}


@pytest.mark.parametrize(("sql", "phrases"), _REFUSED.values(), ids=_REFUSED.keys())
def test_each_type_the_post_cannot_carry_is_refused_with_advice(
    resolver: SessionResolver, sql: str, phrases: tuple[str, ...]
) -> None:
    outcome = _resolve(resolver, sql)
    assert outcome.name == "v"
    assert outcome.value is None
    assert outcome.code is FillCode.VALUE_REFUSED
    assert outcome.detail is not None
    for phrase in phrases:
        assert phrase in outcome.detail


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        1.5,
        float("nan"),
        float("inf"),
        datetime(2021, 9, 8, 6, 5),
        datetime(2021, 9, 8),
        time(6, 5),
        timedelta(days=1),
        b"x",
        [1],
        {"a": 1},
    ],
    ids=repr,
)
def test_a_bool_is_never_an_integer_and_a_datetime_never_a_date(value: object) -> None:
    assert isinstance(to_text(value), ValueRefusal)


def test_the_premises_bool_is_an_int_and_datetime_is_a_date() -> None:
    assert isinstance(True, int)
    assert isinstance(datetime(2021, 9, 8), date)
    assert to_text(1) == "1"
    assert to_text(0) == "0"
    assert to_text(date(2021, 9, 8)) == "2021-09-08"


_LINE_BREAKS: dict[str, str] = {
    "lf": "chr(10)",
    "cr": "chr(13)",
    "crlf": "chr(13) || chr(10)",
    "vertical-tab": "chr(11)",
    "form-feed": "chr(12)",
    "next-line": "chr(133)",
    "line-separator": "chr(8232)",
    "paragraph-separator": "chr(8233)",
}


@pytest.mark.parametrize("build", _LINE_BREAKS.values(), ids=_LINE_BREAKS.keys())
@pytest.mark.parametrize("where", ["middle", "end", "start", "only"])
def test_text_holding_a_line_break_of_any_kind_is_refused(
    resolver: SessionResolver, build: str, where: str
) -> None:
    sql = {
        "middle": f"SELECT 'a' || {build} || 'b'",
        "end": f"SELECT 'a' || {build}",
        "start": f"SELECT {build} || 'b'",
        "only": f"SELECT {build}",
    }[where]
    outcome = _resolve(resolver, sql)
    assert outcome.value is None
    assert outcome.code is FillCode.VALUE_REFUSED
    assert outcome.detail is not None
    assert "line break" in outcome.detail


_MARKERS = ["<!--", "-->", "--!>"]


@pytest.mark.parametrize("marker", _MARKERS)
@pytest.mark.parametrize("where", ["middle", "end", "start", "only"])
def test_text_holding_a_comment_marker_is_refused(
    resolver: SessionResolver, marker: str, where: str
) -> None:
    text = {
        "middle": f"a{marker}b",
        "end": f"a{marker}",
        "start": f"{marker}b",
        "only": marker,
    }[where]
    outcome = _resolve(resolver, f"SELECT '{text}'")
    assert outcome.value is None
    assert outcome.code is FillCode.VALUE_REFUSED
    assert outcome.detail is not None
    assert repr(marker) in outcome.detail
    assert "\n" not in outcome.detail


def test_the_marker_named_in_the_advice_is_the_one_found() -> None:
    for marker in _MARKERS:
        refusal = to_text(f"x {marker} y")
        assert isinstance(refusal, ValueRefusal)
        assert refusal.detail.count(repr(marker)) == 1
        others = [m for m in _MARKERS if m != marker]
        # `-->` is part of nothing else, `--!>` and `<!--` are distinct.
        assert all(repr(other) not in refusal.detail for other in others)


# --------------------------------------------------------------------------- #
# Timeouts, failures and refusals, each on one line
# --------------------------------------------------------------------------- #

_SLOW = (
    "SELECT sum(a.range * b.range) "
    "FROM range(1000000000) a, range(1000000000) b WHERE $as_of IS NOT NULL"
)


def test_a_statement_that_runs_too_long_is_reported_as_timed_out(
    resolver: SessionResolver,
) -> None:
    outcome = _resolve(resolver, _SLOW, timeout_s=0.05)
    assert outcome == VariableOutcome(
        "v",
        None,
        FillCode.TIMED_OUT,
        "statement ran longer than 0.05 seconds and was stopped",
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT TIMESTAMPTZ '2021-09-08 06:05:00+02'",
        "SELECT to_timestamp(0)",
    ],
)
def test_a_timestamp_with_a_zone_is_refused_with_the_timestamp_advice(
    resolver: SessionResolver, sql: str
) -> None:
    # The driver cannot hand such a value over without a zone library that
    # fitdocs does not depend on; the failure is still a refused timestamp.
    outcome = _resolve(resolver, sql)
    assert outcome.value is None
    assert outcome.code is FillCode.VALUE_REFUSED
    assert outcome.detail is not None
    assert "timestamp" in outcome.detail
    assert "to text" in outcome.detail
    assert "DATE" in outcome.detail
    assert "pytz" not in outcome.detail


def test_only_the_timestamp_hint_turns_a_failure_into_a_refused_value() -> None:
    other = _resolve_fake(_Spy(run=_raiser(StatementFailed("boom", "some other hint"))))
    assert other == VariableOutcome("v", None, FillCode.STATEMENT_FAILED, "boom")
    tz = _resolve_fake(_Spy(run=_raiser(StatementFailed("x", TIMESTAMPTZ_HINT))))
    assert tz == VariableOutcome("v", None, FillCode.VALUE_REFUSED, _TIMESTAMP_ADVICE)
    # A message that merely mentions the library is not the signal.
    named = _resolve_fake(_Spy(run=_raiser(StatementFailed("pytz is odd", None))))
    assert named == VariableOutcome("v", None, FillCode.STATEMENT_FAILED, "pytz is odd")


def test_a_real_failure_naming_pytz_as_a_column_is_a_failed_statement(
    resolver: SessionResolver,
) -> None:
    outcome = _resolve(resolver, "SELECT pytz FROM pages WHERE $as_of IS NOT NULL")
    assert outcome.value is None
    assert outcome.code is FillCode.STATEMENT_FAILED
    assert outcome.detail is not None
    assert "pytz" in outcome.detail
    assert "\n" not in outcome.detail


def test_a_real_run_time_refusal_is_a_failed_statement(
    resolver: SessionResolver,
) -> None:
    outcome = _resolve(
        resolver, "SELECT count(*) FROM read_csv('/etc/hosts') WHERE $as_of IS NOT NULL"
    )
    assert outcome.value is None
    assert outcome.code is FillCode.STATEMENT_FAILED
    assert outcome.detail
    assert "\n" not in outcome.detail


def test_the_session_still_answers_after_a_timeout(resolver: SessionResolver) -> None:
    _resolve(resolver, _SLOW, timeout_s=0.05)
    assert _resolve(resolver, EXAMPLE_SQL, AM) == _ok("56")


_BAD_COLUMN = "SELECT nosuchcolumn FROM pages WHERE start_time_local <= $as_of"


def test_a_failing_statement_gives_the_databases_message_on_one_line(
    resolver: SessionResolver,
) -> None:
    # The premise: DuckDB's own message spans several lines.
    session = cast(Any, resolver)._session
    with pytest.raises(StatementFailed) as raised:
        session.run(
            _BAD_COLUMN,
            params={"as_of": MON.start},
            max_rows=2,
            timeout_s=_TIMEOUT,
        )
    assert "\n" in str(raised.value)

    outcome = _resolve(resolver, _BAD_COLUMN)
    assert outcome.value is None
    assert outcome.code is FillCode.STATEMENT_FAILED
    assert outcome.detail == " ".join(str(raised.value).split())
    assert "nosuchcolumn" in outcome.detail
    assert "\n" not in outcome.detail


def test_a_statement_the_screen_refuses_at_resolve_time_is_a_failed_statement(
    resolver: SessionResolver,
) -> None:
    outcome = _resolve(resolver, "SELECT 1; SELECT 2")
    assert outcome.value is None
    assert outcome.code is FillCode.STATEMENT_FAILED
    assert outcome.detail
    assert "\n" not in outcome.detail


def test_a_statement_that_is_not_a_select_is_not_run(
    resolver: SessionResolver,
) -> None:
    outcome = _resolve(resolver, "EXPLAIN SELECT 1")
    assert outcome.value is None
    assert outcome.code is FillCode.STATEMENT_FAILED


def _raiser(error: BaseException) -> Callable[..., Any]:
    def raise_it(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    return raise_it


def _resolve_fake(spy: _Spy) -> VariableOutcome:
    return _fake(spy).resolve(
        _var("SELECT 1"), Binding(datetime(2021, 9, 8), "K"), timeout_s=2.0
    )


def test_screen_failures_and_refusals_map_to_a_failed_statement_on_one_line() -> None:
    failed = _resolve_fake(
        _Spy(screen=_raiser(StatementFailed("Parser Error:\n  near  x\n", None)))
    )
    assert failed == VariableOutcome(
        "v", None, FillCode.STATEMENT_FAILED, "Parser Error: near x"
    )
    refused = _resolve_fake(
        _Spy(screen=_raiser(StatementRefused(Restriction.ONE_STATEMENT, "")))
    )
    assert refused.code is FillCode.STATEMENT_FAILED
    assert refused.value is None
    assert refused.detail == " ".join(
        str(StatementRefused(Restriction.ONE_STATEMENT, "")).split()
    )


def test_a_run_refusal_gives_the_restriction_text() -> None:
    error = StatementRefused(Restriction.ONE_STATEMENT, "")
    outcome = _resolve_fake(_Spy(run=_raiser(error)))
    assert outcome == VariableOutcome("v", None, FillCode.STATEMENT_FAILED, str(error))


def test_a_run_failure_with_a_multi_line_message_is_joined_on_one_line() -> None:
    outcome = _resolve_fake(
        _Spy(run=_raiser(StatementFailed("Binder Error:\n\tno column\r\n  here", None)))
    )
    assert outcome == VariableOutcome(
        "v", None, FillCode.STATEMENT_FAILED, "Binder Error: no column here"
    )


def test_a_timeout_is_timed_out_not_a_failed_statement() -> None:
    outcome = _resolve_fake(_Spy(run=_raiser(StatementTimedOut(5.0))))
    assert outcome == VariableOutcome(
        "v",
        None,
        FillCode.TIMED_OUT,
        "statement ran longer than 5 seconds and was stopped",
    )


@pytest.mark.parametrize(
    "spy",
    [
        _Spy(kind="EXPLAIN"),
        _Spy(parameters=frozenset({"as_of", "other"})),
        _Spy(parameters=frozenset({"other"})),
    ],
    ids=["not-select", "unbound-name-beside-bound", "unbound-name-alone"],
)
def test_a_statement_that_cannot_be_bound_is_not_run(spy: _Spy) -> None:
    outcome = _resolve_fake(spy)
    assert outcome == VariableOutcome(
        "v",
        None,
        FillCode.STATEMENT_FAILED,
        "must be a SELECT that uses only $as_of and $page_key",
    )
    assert spy.runs == []


# --------------------------------------------------------------------------- #
# Ctrl-C, and the index-currency check
# --------------------------------------------------------------------------- #


def _interrupted() -> RuntimeError:
    error = RuntimeError("Query interrupted")
    error.__cause__ = KeyboardInterrupt()
    return error


def _spy_for(phase: str, error: BaseException) -> _Spy:
    if phase == "screen":
        return _Spy(screen=_raiser(error))
    if phase == "run":
        return _Spy(run=_raiser(error))
    return _Spy(current=_raiser(error))


def _drive(spy: _Spy, phase: str) -> object:
    resolver = _fake(spy)
    if phase == "page_is_current":
        return resolver.page_is_current("K", "workouts/x.md", b"x")
    return resolver.resolve(
        _var("SELECT 1"), Binding(datetime(2021, 9, 8), "K"), timeout_s=1.0
    )


_PHASES = ["screen", "run", "page_is_current"]


@pytest.mark.parametrize("phase", _PHASES)
def test_a_ctrl_c_surfaced_as_a_runtime_error_becomes_keyboard_interrupt(
    phase: str,
) -> None:
    with pytest.raises(KeyboardInterrupt) as caught:
        _drive(_spy_for(phase, _interrupted()), phase)
    assert str(caught.value.__cause__) == "Query interrupted"


@pytest.mark.parametrize("phase", _PHASES)
def test_a_bare_keyboard_interrupt_propagates_as_itself(phase: str) -> None:
    original = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt) as caught:
        _drive(_spy_for(phase, original), phase)
    assert caught.value is original


@pytest.mark.parametrize("phase", _PHASES)
def test_another_runtime_error_is_not_mistaken_for_ctrl_c(phase: str) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        _drive(_spy_for(phase, RuntimeError("boom")), phase)


@pytest.mark.parametrize("answer", [True, False])
def test_the_currency_check_is_the_sessions_answer_for_the_same_arguments(
    answer: bool,
) -> None:
    spy = _Spy(current=lambda *_a: answer)
    assert _fake(spy).page_is_current("KEY", "workouts/a.md", b"bytes") is answer
    assert spy.currents == [("KEY", "workouts/a.md", b"bytes")]


def test_a_page_the_index_holds_exactly_is_current(
    resolver: SessionResolver, indexed_post_root: IndexedPostRoot
) -> None:
    for page in PAGES:
        data = (indexed_post_root.root / page.path).read_bytes()
        assert resolver.page_is_current(page.key, page.path, data) is True


def test_a_page_that_differs_from_the_index_or_has_no_key_is_not_current(
    resolver: SessionResolver, indexed_post_root: IndexedPostRoot
) -> None:
    data = (indexed_post_root.root / PM.path).read_bytes()
    assert resolver.page_is_current(PM.key, PM.path, data + b"\n") is False
    assert (
        resolver.page_is_current(PM.key, PM.path, data.replace(b"Run", b"Ran")) is False
    )
    assert resolver.page_is_current(AM.key, PM.path, data) is False
    assert resolver.page_is_current(None, PM.path, data) is False
    assert resolver.page_is_current("0" * 64, PM.path, data) is False
