"""Check a template's SQL against the index (post-templates task 2.3).

Requirements 2.1 to 2.5 and 13.3. The SQL cases run against a real sandboxed
session over the synthetic index of `_index.py`; the interrupt, timeout and
walker cases use a fake session or hand-built serialized statements, because a
real index cannot be made to fail that way on demand. Expected problems are
compared as whole lists of exact strings, so an extra problem is as red as a
missing one.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from fitdocs.index.store import open_index
from fitdocs.post_template import resolve
from fitdocs.post_template.model import Unavailable
from fitdocs.post_template.resolve import (
    VOLATILE_FUNCTIONS,
    VOLATILE_KEYWORDS,
    SessionResolver,
    lint_findings,
    open_resolver,
)
from fitdocs.post_template.template import PostTemplate, parse_post_template
from fitdocs.query import command
from fitdocs.query.command import (
    OutcomeKind,
    QuerySession,
    ScreenedStatement,
    SessionUnavailable,
)
from fitdocs.query.format import ResultSet
from fitdocs.query.sandbox import SandboxUnverified
from fitdocs.query.statement import (
    StatementFailed,
    StatementRefused,
    StatementTimedOut,
)
from tests.index._helpers import hold_index
from tests.post_template._index import EXAMPLE_SQL, IndexedPostRoot

_PATH = Path("/data/post-template.toml")
_Make = Callable[[str], Path]


def _template(**sql_by_name: str) -> PostTemplate:
    """A parsed template whose variables are the given names and SQL."""
    names = sorted(sql_by_name)
    title = " ".join("{" + name + "}" for name in names)
    text = f"since = 2026-11-07\ntitle = {json.dumps(title)}\n"
    for name in names:
        text += f"\n[vars.{name}]\nsql = {json.dumps(sql_by_name[name])}\n"
    return parse_post_template(text.encode("utf-8"), path=_PATH)


def _problem(name: str, reason: str) -> str:
    return f"{_PATH}: vars.{name}.sql: {reason}"


@pytest.fixture(scope="module")
def resolver(indexed_post_root: IndexedPostRoot) -> Iterator[SessionResolver]:
    opened = open_resolver(
        indexed_post_root.root, indexed_post_root.query_environment()
    )
    assert isinstance(opened, SessionResolver)
    yield opened
    opened.close()


# --------------------------------------------------------------------------- #
# SQL that passes
# --------------------------------------------------------------------------- #

_CLEAN: dict[str, str] = {
    "design_example": EXAMPLE_SQL,
    "as_of_only": "SELECT count(*) FROM pages WHERE start_time_local <= $as_of",
    "both_parameters": (
        "SELECT load_value FROM pages WHERE page_key = $page_key "
        "AND start_time_local <= $as_of"
    ),
    # Names that are text, not calls or references, must not trip the lint.
    "names_as_text": (
        "SELECT 'now()', 'current_date', 'random', 'USING SAMPLE', 'query(x)' "
        "FROM pages WHERE start_time_local <= $as_of"
    ),
    # A qualified reference to a real column named like the keyword.
    "qualified_keyword_column": (
        "SELECT p.current_date FROM (SELECT 1 AS current_date) p "
        "WHERE $as_of IS NOT NULL"
    ),
    # A qualified column is not the keyword; only a single-part reference is.
    "qualified_column": (
        "SELECT p.date FROM pages p WHERE p.start_time_local <= $as_of"
    ),
}


@pytest.mark.parametrize("sql", _CLEAN.values(), ids=_CLEAN.keys())
def test_sql_that_is_one_select_bound_to_as_of_passes(
    resolver: SessionResolver, sql: str
) -> None:
    assert resolver.check(_template(share=sql)) == ()


def test_several_variables_are_checked_and_no_variables_give_no_problems(
    resolver: SessionResolver,
) -> None:
    template = _template(alpha=_CLEAN["design_example"], beta=_CLEAN["as_of_only"])
    assert resolver.check(template) == ()


# --------------------------------------------------------------------------- #
# SQL that is refused: one statement, a SELECT, $as_of, the bound parameters
# --------------------------------------------------------------------------- #

_AS_OF_ONLY = "start_time_local <= $as_of"

_SCREEN_REFUSALS: dict[str, tuple[str, list[str]]] = {
    "explain": (
        f"EXPLAIN SELECT 1 FROM pages WHERE {_AS_OF_ONLY}",
        ["must be a SELECT, not EXPLAIN"],
    ),
    "no_as_of": ("SELECT count(*) FROM pages", ["must reference $as_of"]),
    "page_key_without_as_of": (
        "SELECT count(*) FROM pages WHERE page_key = $page_key",
        ["must reference $as_of"],
    ),
    "unknown_parameter": (
        f"SELECT $foo FROM pages WHERE {_AS_OF_ONLY}",
        ["uses $foo, but only $as_of and $page_key are bound"],
    ),
    "unknown_parameters_in_name_order": (
        "SELECT $zeta, $alpha, $mid, $beta, $omega, $kappa FROM pages "
        f"WHERE {_AS_OF_ONLY}",
        [
            f"uses ${name}, but only $as_of and $page_key are bound"
            for name in ("alpha", "beta", "kappa", "mid", "omega", "zeta")
        ],
    ),
    "no_as_of_and_an_unknown_parameter": (
        "SELECT $foo FROM pages",
        [
            "must reference $as_of",
            "uses $foo, but only $as_of and $page_key are bound",
        ],
    ),
    "two_statements": (
        f"SELECT 1 WHERE {_AS_OF_ONLY.replace('start_time_local', '$as_of')}; SELECT 2",
        ["fitdocs query runs exactly one statement"],
    ),
    "not_a_query": (
        f"DELETE FROM pages WHERE {_AS_OF_ONLY}",
        ["the query sandbox runs only queries and EXPLAIN; this is a DELETE statement"],
    ),
}


@pytest.mark.parametrize(
    ("sql", "reasons"), _SCREEN_REFUSALS.values(), ids=_SCREEN_REFUSALS.keys()
)
def test_a_statement_the_screen_or_the_parameter_rules_refuse_names_its_variable(
    resolver: SessionResolver, sql: str, reasons: list[str]
) -> None:
    assert resolver.check(_template(share=sql)) == tuple(
        _problem("share", reason) for reason in reasons
    )


def test_a_statement_with_a_syntax_error_is_one_line(
    resolver: SessionResolver,
) -> None:
    (problem,) = resolver.check(_template(share="SELECT $as_of FROM FROM pages"))
    assert problem.startswith(_problem("share", "")), problem
    assert "syntax error" in problem.lower()
    assert "\n" not in problem


# --------------------------------------------------------------------------- #
# The lint, over real serialized statements
# --------------------------------------------------------------------------- #

#: One call per listed function, each written as the athlete would write it.
#: `query` and `query_table` are table functions.
_BOUND = "$as_of IS NOT NULL"

_CALLS: dict[str, str] = {
    name: f"SELECT {call} FROM pages WHERE {_BOUND}"
    for name, call in {
        "now": "now()",
        "today": "today()",
        "current_timestamp": "current_timestamp()",
        "get_current_time": "get_current_time()",
        "get_current_timestamp": "get_current_timestamp()",
        "transaction_timestamp": "transaction_timestamp()",
        "current_localtime": "current_localtime()",
        "current_localtimestamp": "current_localtimestamp()",
        "random": "random()",
        "setseed": "setseed(0.5)",
        "uuid": "uuid()",
        "uuidv4": "uuidv4()",
        "uuidv7": "uuidv7()",
        "gen_random_uuid": "gen_random_uuid()",
        "nextval": "nextval('s')",
        "currval": "currval('s')",
        # The call forms of the keywords.
        "current_date": "current_date()",
        "current_time": "current_time()",
        "localtime": "localtime()",
        "localtimestamp": "localtimestamp()",
        "ago": "ago(INTERVAL 1 DAY)",
        "pg_conf_load_time": "pg_conf_load_time()",
        "pg_postmaster_start_time": "pg_postmaster_start_time()",
        "current_transaction_id": "current_transaction_id()",
        "txid_current": "txid_current()",
        "current_query_id": "current_query_id()",
        "current_connection_id": "current_connection_id()",
    }.items()
} | {
    # Table functions.
    "query": f"SELECT * FROM query('SELECT random()') WHERE {_BOUND}",
    "query_table": f"SELECT * FROM query_table('pages') WHERE {_BOUND}",
}


def test_every_listed_function_has_exactly_one_call_case() -> None:
    assert set(_CALLS) == VOLATILE_FUNCTIONS


def _call_reason(name: str) -> str:
    if name in {"query", "query_table"}:
        return f"`{name}(...)` runs SQL the check cannot see"
    return f"`{name}()` gives a different value on each run"


@pytest.mark.parametrize("name", _CALLS)
def test_each_listed_function_is_refused_by_name(
    resolver: SessionResolver, name: str
) -> None:
    assert resolver.check(_template(share=_CALLS[name])) == (
        _problem("share", _call_reason(name)),
    )


#: One bare reference per listed keyword, in the cases an athlete might type.
_KEYWORD_CASES: dict[str, tuple[str, ...]] = {
    "current_date": ("current_date", "CURRENT_DATE", "Current_Date"),
    "current_time": ("current_time", "CURRENT_TIME", "Current_Time"),
    "current_timestamp": ("current_timestamp", "CURRENT_TIMESTAMP"),
    "localtime": ("localtime", "LOCALTIME", "LocalTime"),
    "localtimestamp": ("localtimestamp", "LOCALTIMESTAMP"),
}


def test_every_listed_keyword_has_cases() -> None:
    assert set(_KEYWORD_CASES) == VOLATILE_KEYWORDS


@pytest.mark.parametrize(
    ("keyword", "spelling"),
    [(k, s) for k, spellings in _KEYWORD_CASES.items() for s in spellings],
)
def test_each_keyword_column_reference_is_refused_in_any_case(
    resolver: SessionResolver, keyword: str, spelling: str
) -> None:
    sql = f"SELECT {spelling} FROM pages WHERE $as_of IS NOT NULL"
    assert resolver.check(_template(share=sql)) == (
        _problem("share", f"`{keyword}` gives a different value on each run"),
    )


def test_a_keyword_and_the_same_name_as_a_call_are_told_apart(
    resolver: SessionResolver,
) -> None:
    sql = "SELECT current_timestamp, current_timestamp() WHERE $as_of IS NOT NULL"
    assert resolver.check(_template(share=sql)) == (
        _problem("share", "`current_timestamp()` gives a different value on each run"),
        _problem("share", "`current_timestamp` gives a different value on each run"),
    )


_SAMPLE_REASON = "sampling (`USING SAMPLE` or `TABLESAMPLE`) is not repeatable"

_SAMPLES: dict[str, str] = {
    "using_sample_rows": f"SELECT count(*) FROM pages WHERE {_BOUND} USING SAMPLE 3",
    "using_sample_percent_method": (
        f"SELECT count(*) FROM pages WHERE {_BOUND} USING SAMPLE 50 PERCENT (bernoulli)"
    ),
    "tablesample": f"SELECT count(*) FROM pages TABLESAMPLE 50 PERCENT WHERE {_BOUND}",
    "sample_on_a_subquery": (
        f"SELECT count(*) FROM (SELECT 1 AS x) WHERE {_BOUND} USING SAMPLE 1"
    ),
    "sample_in_a_join_arm": (
        "SELECT count(*) FROM pages a JOIN (SELECT * FROM pages USING SAMPLE 2) b "
        f"ON a.page_key = b.page_key AND {_BOUND}"
    ),
}


@pytest.mark.parametrize("sql", _SAMPLES.values(), ids=_SAMPLES.keys())
def test_sampling_is_refused(resolver: SessionResolver, sql: str) -> None:
    assert resolver.check(_template(share=sql)) == (_problem("share", _SAMPLE_REASON),)


#: A forbidden call hidden in each place a walker might not look.
_NESTED: dict[str, str] = {
    "subquery_in_where": (
        f"SELECT 1 FROM pages WHERE {_BOUND} AND EXISTS (SELECT 1 WHERE now() > $as_of)"
    ),
    "cte": f"WITH c AS (SELECT now() AS t) SELECT t FROM c WHERE {_BOUND}",
    "case_arm": "SELECT CASE WHEN $as_of > now() THEN 1 ELSE 0 END",
    "case_else": (
        "SELECT CASE WHEN $as_of IS NULL THEN 0 ELSE extract(year FROM now()) END"
    ),
    "set_operation": (f"SELECT 1 WHERE {_BOUND} UNION SELECT 2 WHERE now() > $as_of"),
    "window_order": (
        f"SELECT sum(load_value) OVER (ORDER BY now()) FROM pages WHERE {_BOUND}"
    ),
    "aggregate_filter": (
        "SELECT sum(load_value) FILTER (start_time_local < now()) FROM pages "
        f"WHERE {_BOUND}"
    ),
    "derived_table": f"SELECT * FROM (SELECT now() AS t) d WHERE {_BOUND}",
}


@pytest.mark.parametrize("sql", _NESTED.values(), ids=_NESTED.keys())
def test_a_forbidden_call_is_found_wherever_it_is_nested(
    resolver: SessionResolver, sql: str
) -> None:
    assert resolver.check(_template(share=sql)) == (
        _problem("share", _call_reason("now")),
    )


_NESTED_KEYWORDS: dict[str, str] = {
    "subquery": f"SELECT 1 WHERE {_BOUND} AND (SELECT CURRENT_DATE) IS NOT NULL",
    "cte": f"WITH c AS (SELECT Current_Date AS d) SELECT d FROM c WHERE {_BOUND}",
    "case_arm": "SELECT CASE WHEN $as_of > CURRENT_DATE THEN 1 ELSE 0 END",
}


@pytest.mark.parametrize("sql", _NESTED_KEYWORDS.values(), ids=_NESTED_KEYWORDS.keys())
def test_a_keyword_reference_is_found_wherever_it_is_nested(
    resolver: SessionResolver, sql: str
) -> None:
    assert resolver.check(_template(share=sql)) == (
        _problem("share", "`current_date` gives a different value on each run"),
    )


def test_every_finding_is_reported_once_in_a_stable_order(
    resolver: SessionResolver,
) -> None:
    sql = (
        "SELECT * FROM (SELECT random(), now(), random(), CURRENT_DATE, uuid() "
        "FROM pages USING SAMPLE 2) WHERE $as_of IS NOT NULL"
    )
    assert resolver.check(_template(share=sql)) == tuple(
        _problem("share", reason)
        for reason in sorted(
            [
                "`random()` gives a different value on each run",
                "`now()` gives a different value on each run",
                "`current_date` gives a different value on each run",
                "`uuid()` gives a different value on each run",
                _SAMPLE_REASON,
            ]
        )
    )


def test_a_parameter_problem_and_a_lint_finding_are_both_reported(
    resolver: SessionResolver,
) -> None:
    clock = "`current_date` gives a different value on each run"
    rand = "`random()` gives a different value on each run"
    missing = resolver.check(
        _template(share="SELECT count(*) FROM pages WHERE date >= current_date - 7")
    )
    assert missing == (
        _problem("share", "must reference $as_of"),
        _problem("share", clock),
    )
    unknown = resolver.check(
        _template(share="SELECT $foo, random() WHERE $as_of IS NOT NULL")
    )
    assert unknown == (
        _problem("share", "uses $foo, but only $as_of and $page_key are bound"),
        _problem("share", rand),
    )


def test_findings_in_nested_calls_are_all_reported(
    resolver: SessionResolver,
) -> None:
    sql = "SELECT setseed(random()) WHERE $as_of IS NOT NULL"
    assert resolver.check(_template(share=sql)) == (
        _problem("share", "`random()` gives a different value on each run"),
        _problem("share", "`setseed()` gives a different value on each run"),
    )


def test_a_template_with_no_variables_has_no_problems(
    resolver: SessionResolver,
) -> None:
    template = parse_post_template(
        b'since = 2026-11-07\ntitle = "{title}"\n', path=_PATH
    )
    assert template.variables == ()
    assert resolver.check(template) == ()


# --------------------------------------------------------------------------- #
# Every problem names its variable
# --------------------------------------------------------------------------- #


def test_each_problem_names_its_own_variable_and_clean_variables_have_none(
    resolver: SessionResolver,
) -> None:
    template = _template(
        alpha=EXAMPLE_SQL,
        beta="SELECT count(*) FROM pages",
        gamma="SELECT $as_of, random()",
        delta="SELECT $as_of, $nope",
    )
    assert resolver.check(template) == (
        _problem("beta", "must reference $as_of"),
        _problem("delta", "uses $nope, but only $as_of and $page_key are bound"),
        _problem("gamma", "`random()` gives a different value on each run"),
    )


# --------------------------------------------------------------------------- #
# Lint walker over hand-built serialized statements
# --------------------------------------------------------------------------- #


def _fn(name: str) -> dict[str, Any]:
    return {"class": "FUNCTION", "function_name": name, "children": []}


def _col(*names: str) -> dict[str, Any]:
    return {"class": "COLUMN_REF", "column_names": list(names)}


def test_the_walker_compares_function_names_lowercased() -> None:
    assert lint_findings({"x": [_fn("NOW")]}) == (
        "`now()` gives a different value on each run",
    )


def test_the_walker_reads_a_single_part_reference_only_and_lowercases_it() -> None:
    assert lint_findings([_col("Current_Date")]) == (
        "`current_date` gives a different value on each run",
    )
    assert lint_findings([_col("pages", "current_date"), _col("now")]) == ()
    assert (
        lint_findings([{"class": "CONSTANT", "column_names": ["current_date"]}]) == ()
    )
    assert lint_findings([_col("current_date", "extra")]) == ()


def test_the_walker_ignores_a_reference_that_is_not_a_list_of_text() -> None:
    assert lint_findings([{"class": "COLUMN_REF", "column_names": 5}]) == ()
    assert lint_findings([{"class": "COLUMN_REF", "column_names": [7]}]) == ()
    assert (
        lint_findings([{"class": "COLUMN_REF", "column_names": ("localtime",)}]) == ()
    )
    assert lint_findings([{"class": "COLUMN_REF"}]) == ()


def test_the_walker_reads_a_function_name_only_when_it_is_text() -> None:
    assert lint_findings({"function_name": None, "x": {"function_name": 7}}) == ()
    assert lint_findings({"function_name": "sum"}) == ()


def test_the_walker_refuses_a_non_null_sample_wherever_it_sits_and_not_a_null_one() -> (
    None
):
    assert lint_findings({"a": {"b": [{"sample": None}]}}) == ()
    assert lint_findings({"a": {"b": [{"sample": {"seed": 1}}]}}) == (_SAMPLE_REASON,)


def test_the_walker_returns_each_finding_once_in_sorted_order() -> None:
    node = [
        _fn("uuid"),
        _fn("random"),
        _fn("now"),
        _fn("random"),
        _fn("setseed"),
        _fn("today"),
        _col("localtime"),
        {"sample": {"seed": 1}},
    ]
    findings = lint_findings(node)
    assert findings == tuple(sorted(set(findings)))
    assert len(findings) == 7


# --------------------------------------------------------------------------- #
# A lint that cannot run, and Ctrl-C
# --------------------------------------------------------------------------- #


class _FakeSession:
    """Just enough of a `QuerySession` for the resolver's two session reads."""

    def __init__(
        self,
        *,
        screen: Callable[[str], ScreenedStatement] | None = None,
        run: Callable[..., ResultSet] | None = None,
    ) -> None:
        self.closed = 0
        self._screen = screen or (
            lambda _sql: ScreenedStatement("SELECT", frozenset({"as_of"}))
        )
        self._run = run or (lambda *_a, **_k: _serialized({"error": False}))

    def screen(self, sql: str) -> ScreenedStatement:
        return self._screen(sql)

    def run(self, sql: str, **kwargs: Any) -> ResultSet:
        return self._run(sql, **kwargs)

    def close(self) -> None:
        self.closed += 1


def _serialized(payload: dict[str, Any]) -> ResultSet:
    return ResultSet(("json_serialize_sql",), ((json.dumps(payload),),), False, 2)


def _fake_resolver(session: _FakeSession) -> SessionResolver:
    return SessionResolver(cast(QuerySession, session))


def _raiser(error: BaseException) -> Callable[..., Any]:
    def raise_it(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    return raise_it


def _interrupted() -> RuntimeError:
    error = RuntimeError("Query interrupted")
    error.__cause__ = KeyboardInterrupt()
    return error


@pytest.mark.parametrize("phase", ["screen", "lint"])
def test_a_ctrl_c_surfaced_as_a_runtime_error_becomes_keyboard_interrupt(
    phase: str,
) -> None:
    session = _FakeSession(
        **{("screen" if phase == "screen" else "run"): _raiser(_interrupted())}
    )
    with pytest.raises(KeyboardInterrupt) as caught:
        _fake_resolver(session).check(_template(share="SELECT $as_of"))
    assert caught.value.__cause__ is not None
    assert str(caught.value.__cause__) == "Query interrupted"


@pytest.mark.parametrize("phase", ["screen", "lint"])
def test_a_bare_keyboard_interrupt_propagates_as_itself(phase: str) -> None:
    original = KeyboardInterrupt()
    session = _FakeSession(
        **{("screen" if phase == "screen" else "run"): _raiser(original)}
    )
    with pytest.raises(KeyboardInterrupt) as caught:
        _fake_resolver(session).check(_template(share="SELECT $as_of"))
    assert caught.value is original


@pytest.mark.parametrize("phase", ["screen", "lint"])
def test_another_runtime_error_is_not_mistaken_for_ctrl_c(phase: str) -> None:
    session = _FakeSession(
        **{("screen" if phase == "screen" else "run"): _raiser(RuntimeError("boom"))}
    )
    with pytest.raises(RuntimeError, match="boom"):
        _fake_resolver(session).check(_template(share="SELECT $as_of"))


def test_a_lint_that_times_out_is_a_problem_naming_the_limit() -> None:
    session = _FakeSession(run=_raiser(StatementTimedOut(30.0)))
    assert _fake_resolver(session).check(_template(share="SELECT $as_of")) == (
        _problem(
            "share",
            "could not be linted: statement ran longer than 30 seconds and was stopped",
        ),
    )


def test_a_lint_that_the_sandbox_refuses_or_fails_is_a_one_line_problem() -> None:
    refused = _FakeSession(
        run=_raiser(StatementRefused(command.Restriction.ONE_STATEMENT, ""))
    )
    failed = _FakeSession(run=_raiser(StatementFailed("bad\nthing", None)))
    template = _template(share="SELECT $as_of")
    assert _fake_resolver(refused).check(template) == (
        _problem(
            "share", "could not be linted: fitdocs query runs exactly one statement"
        ),
    )
    assert _fake_resolver(failed).check(template) == (
        _problem("share", "could not be linted: bad thing"),
    )


def test_a_serialization_error_is_a_one_line_problem_with_its_message() -> None:
    session = _FakeSession(
        run=lambda *_a, **_k: _serialized(
            {"error": True, "error_message": "cannot  serialize\nthis"}
        )
    )
    assert _fake_resolver(session).check(_template(share="SELECT $as_of")) == (
        _problem("share", "could not be linted: cannot serialize this"),
    )


def test_a_serialization_error_without_a_message_still_names_a_reason() -> None:
    session = _FakeSession(run=lambda *_a, **_k: _serialized({"error": True}))
    assert _fake_resolver(session).check(_template(share="SELECT $as_of")) == (
        _problem("share", "could not be linted: unknown error"),
    )


def test_the_lint_is_given_the_variable_sql_as_a_parameter_with_a_row_cap() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    def run(sql: str, **kwargs: Any) -> ResultSet:
        seen.append((sql, kwargs))
        return _serialized({"error": False})

    template = _template(alpha="SELECT $as_of -- one", beta="SELECT $as_of -- two")
    assert _fake_resolver(_FakeSession(run=run)).check(template) == ()
    assert [kwargs["params"] for _sql, kwargs in seen] == [
        {"sql": "SELECT $as_of -- one"},
        {"sql": "SELECT $as_of -- two"},
    ]
    assert {kwargs["max_rows"] for _sql, kwargs in seen} == {2}
    assert {kwargs["timeout_s"] for _sql, kwargs in seen} == {30.0}
    assert {sql for sql, _kwargs in seen} == {"SELECT json_serialize_sql($sql)"}


def test_a_statement_that_fails_the_screen_is_not_linted() -> None:
    def run(*_args: Any, **_kwargs: Any) -> ResultSet:
        raise AssertionError("linted a refused statement")

    session = _FakeSession(screen=_raiser(StatementFailed("no good", None)), run=run)
    assert _fake_resolver(session).check(_template(share="SELECT 1")) == (
        _problem("share", "no good"),
    )


def test_close_closes_the_session_each_time_it_is_called() -> None:
    session = _FakeSession()
    resolver_ = _fake_resolver(session)
    resolver_.close()
    assert session.closed == 1
    resolver_.close()
    assert session.closed == 2


# --------------------------------------------------------------------------- #
# Opening: why the index is unavailable
# --------------------------------------------------------------------------- #


def _open(root: Path, env: command.QueryEnvironment) -> SessionResolver | Unavailable:
    return open_resolver(root, env)


def test_an_index_that_is_not_built_says_so_and_names_the_next_step(
    indexed_post_root: IndexedPostRoot, per_test_directory: _Make
) -> None:
    empty_root = per_test_directory("no-index")
    assert _open(empty_root, indexed_post_root.query_environment()) == Unavailable(
        "the index is not built", "run `fitdocs index`"
    )


def test_an_index_with_another_schema_version_needs_a_rebuild(
    post_root_copy: IndexedPostRoot,
) -> None:
    with open_index(post_root_copy.index_dir / "index.duckdb", read_only=False) as conn:
        conn.execute("UPDATE index_meta SET schema_version = 99")
    assert _open(
        post_root_copy.root, post_root_copy.query_environment()
    ) == Unavailable(
        "the index needs a rebuild: index schema version 99 differs from readable "
        "schema version 3",
        "run `fitdocs index` to rebuild it",
    )


def test_an_index_held_by_another_process_is_busy_and_names_it(
    post_root_copy: IndexedPostRoot,
) -> None:
    now = [0.0]

    def sleep(delay: float) -> None:
        now[0] += delay

    base = post_root_copy.query_environment()
    env = command.QueryEnvironment(
        environ=base.environ,
        home=base.home,
        pid=base.pid,
        monotonic=lambda: now[0],
        sleep=sleep,
        on_wait=base.on_wait,
        is_running=base.is_running,
        timer=base.timer,
    )
    with hold_index(post_root_copy.index_dir / "index.duckdb", read_only=False) as pid:
        outcome = _open(post_root_copy.root, env)
    assert outcome == Unavailable(
        f"the index is locked by process {pid}",
        "run the command again once the other fitdocs command finishes",
    )


def test_a_sandbox_that_cannot_be_verified_is_a_defect_to_report(
    post_root_copy: IndexedPostRoot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        command,
        "open_sandboxed",
        _raiser(SandboxUnverified("threads", "2", None)),
    )
    assert _open(
        post_root_copy.root, post_root_copy.query_environment()
    ) == Unavailable(
        "the query sandbox could not be verified: "
        "the sandbox setting threads is NULL, not 2",
        "this is a fitdocs defect; please report it",
    )


@pytest.mark.parametrize(
    ("unavailable", "expected"),
    [
        (
            SessionUnavailable(OutcomeKind.NEEDS_REBUILD, None, None),
            Unavailable(
                "the index needs a rebuild", "run `fitdocs index` to rebuild it"
            ),
        ),
        (
            SessionUnavailable(
                OutcomeKind.NEEDS_REBUILD, "not a\ncomplete index", None
            ),
            Unavailable(
                "the index needs a rebuild: not a complete index",
                "run `fitdocs index` to rebuild it",
            ),
        ),
        (
            SessionUnavailable(OutcomeKind.BUSY, None, None),
            Unavailable(
                "the index is locked",
                "run the command again once the other fitdocs command finishes",
            ),
        ),
        (
            SessionUnavailable(OutcomeKind.UNVERIFIED, None, None),
            Unavailable(
                "the query sandbox could not be verified",
                "this is a fitdocs defect; please report it",
            ),
        ),
        (
            SessionUnavailable(OutcomeKind.UNVERIFIED, "two\nlines", None),
            Unavailable(
                "the query sandbox could not be verified: two lines",
                "this is a fitdocs defect; please report it",
            ),
        ),
    ],
)
def test_reasons_without_a_detail_or_with_a_multi_line_one_read_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    unavailable: SessionUnavailable,
    expected: Unavailable,
) -> None:
    monkeypatch.setattr(resolve, "open_session", lambda *_a, **_k: unavailable)
    assert open_resolver(Path("/unused"), cast(Any, None)) == expected
