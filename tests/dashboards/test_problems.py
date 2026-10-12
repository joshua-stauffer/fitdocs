"""The dashboards problem record: codes, fields, chart copy and severity."""

from __future__ import annotations

import json
from dataclasses import fields

from fitdocs.dashboards.problems import (
    NOTICE_CODES,
    DashboardCode,
    Problem,
    Severity,
    Source,
    dashboard_problem,
    from_chart_problem,
)
from fitdocs.query.command import QueryRequest, run_query
from fitdocs.render.charts.kit import ChartProblem, ProblemCode
from tests.dashboards._helpers import query_environment
from tests.dashboards.conftest import IndexedDashboardRoot

DESIGN_ORDER = (
    "location_foreign",
    "page_name",
    "page_unreadable",
    "page_encoding",
    "page_changed",
    "opener_malformed",
    "marker_malformed",
    "directive_unclosed",
    "directive_terminator",
    "yaml_syntax",
    "yaml_shape",
    "duplicate_key",
    "missing_key",
    "unknown_key",
    "field_value",
    "id_grammar",
    "duplicate_id",
    "mode_value",
    "sql_style",
    "region_misplaced",
    "region_mismatch",
    "region_unclosed",
    "region_contents",
    "region_orphaned",
    "index_unavailable",
    "sql_refused",
    "sql_parameter",
    "sql_failed",
    "sql_timeout",
    "row_cap",
    "column_type",
    "value_kind",
    "snapshot_missing",
    "snapshot_unreadable",
    "sql_changed",
    "freeze_relative",
    "asset_foreign",
    "write_failed",
)

FIELD_ORDER = (
    "source",
    "code",
    "page",
    "chart",
    "line",
    "message",
    "fix",
    "kind",
    "channel",
    "column",
    "option",
    "row",
    "rows",
    "accepted",
)


def _full_problem(
    source: Source = Source.DASHBOARD, code: str = "sql_failed"
) -> Problem:
    return Problem(
        source=source,
        code=code,
        page="weekly",
        chart="load",
        line=12,
        message="The query failed.",
        fix="Fix the query.",
        kind="bar",
        channel="x",
        column="day",
        option="limit",
        row=3,
        rows=40,
        accepted=("b", "a"),
    )


def test_dashboard_codes_are_the_design_prefix_in_order() -> None:
    values = tuple(code.value for code in DashboardCode)
    assert len(DESIGN_ORDER) == 38
    assert values[:38] == DESIGN_ORDER


def test_as_dict_keys_follow_field_order_and_serialise() -> None:
    problem = _full_problem()
    assert tuple(field.name for field in fields(Problem)) == FIELD_ORDER
    data = problem.as_dict()
    assert tuple(data) == FIELD_ORDER
    assert data["accepted"] == ["b", "a"]
    assert isinstance(data["accepted"], list)
    assert data["source"] == "dashboard"
    assert json.loads(json.dumps(data)) == data


def test_as_dict_values_match_a_literal() -> None:
    assert _full_problem().as_dict() == {
        "source": "dashboard",
        "code": "sql_failed",
        "page": "weekly",
        "chart": "load",
        "line": 12,
        "message": "The query failed.",
        "fix": "Fix the query.",
        "kind": "bar",
        "channel": "x",
        "column": "day",
        "option": "limit",
        "row": 3,
        "rows": 40,
        "accepted": ["b", "a"],
    }


def test_from_chart_problem_dict_matches_a_literal() -> None:
    problem = from_chart_problem(_chart_problem(), page="weekly", chart="load", line=21)
    assert problem.as_dict() == {
        "source": "chart",
        "code": "unknown_column",
        "page": "weekly",
        "chart": "load",
        "line": 21,
        "message": "Column not found.",
        "fix": "Name an existing column.",
        "kind": "line",
        "channel": "y",
        "column": "pace",
        "option": "smooth",
        "row": 7,
        "rows": 99,
        "accepted": ["distance_m", "pace_s_per_km"],
    }


def test_as_dict_keeps_absent_values_none() -> None:
    problem = dashboard_problem(
        DashboardCode.PAGE_NAME, "Bad name.", "Rename it.", page="Weekly Plan.md"
    )
    data = problem.as_dict()
    assert data["chart"] is None and data["line"] is None and data["rows"] is None
    assert data["accepted"] == []
    assert data["code"] == "page_name"


def test_dashboard_problem_passes_extra_fields() -> None:
    problem = dashboard_problem(
        DashboardCode.UNKNOWN_KEY,
        "Unknown key.",
        "Remove it.",
        page="weekly",
        chart="load",
        line=4,
        option="colour",
        accepted=("sql", "kind"),
    )
    assert problem.source is Source.DASHBOARD
    assert (problem.chart, problem.line, problem.option) == ("load", 4, "colour")
    assert problem.accepted == ("sql", "kind")


def _chart_problem() -> ChartProblem:
    return ChartProblem(
        ref="ignored-ref",
        kind="line",
        code=ProblemCode.UNKNOWN_COLUMN,
        message="Column not found.",
        fix="Name an existing column.",
        channel="y",
        column="pace",
        option="smooth",
        row=7,
        rows=99,
        accepted=("distance_m", "pace_s_per_km"),
    )


def test_from_chart_problem_copies_every_field() -> None:
    chart = _chart_problem()
    problem = from_chart_problem(chart, page="weekly", chart="load", line=21)
    assert problem == Problem(
        source=Source.CHART,
        code="unknown_column",
        page="weekly",
        chart="load",
        line=21,
        message="Column not found.",
        fix="Name an existing column.",
        kind="line",
        channel="y",
        column="pace",
        option="smooth",
        row=7,
        rows=99,
        accepted=("distance_m", "pace_s_per_km"),
    )
    assert isinstance(problem.code, str) and not isinstance(problem.code, ProblemCode)


def test_from_chart_problem_option_override() -> None:
    chart = _chart_problem()
    problem = from_chart_problem(
        chart, page="weekly", chart="load", line=21, option="show_rows"
    )
    assert problem.option == "show_rows"
    assert chart.option == "smooth"


def test_severity_is_notice_only_for_the_two_dashboard_notice_codes() -> None:
    assert {DashboardCode.SQL_CHANGED, DashboardCode.REGION_ORPHANED} == NOTICE_CODES
    for code in DashboardCode:
        problem = _full_problem(Source.DASHBOARD, code.value)
        expected = Severity.NOTICE if code in NOTICE_CODES else Severity.PROBLEM
        assert problem.severity is expected, code
    assert Severity.NOTICE.value == "notice" and Severity.PROBLEM.value == "problem"


def test_chart_source_problem_with_a_notice_code_string_stays_a_problem() -> None:
    chart_side = _full_problem(Source.CHART, "sql_changed")
    dashboard_side = _full_problem(Source.DASHBOARD, "sql_changed")
    assert dashboard_side.severity is Severity.NOTICE
    assert chart_side.severity is Severity.PROBLEM


def test_indexed_dashboard_root_is_live(
    indexed_dashboard_root: IndexedDashboardRoot,
) -> None:
    fixture = indexed_dashboard_root
    outcome = run_query(
        QueryRequest(
            fixture.root,
            "SELECT count(*) AS n FROM activities",
            False,
            10,
            30.0,
            fixture.today,
        ),
        query_environment(fixture.environ, fixture.home),
    )
    assert outcome.result is not None, outcome.kind
    assert outcome.result.columns == ("n",)
    count = outcome.result.rows[0][0]
    assert isinstance(count, int) and count > 0
