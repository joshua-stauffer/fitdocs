"""The run report as text and JSON: exact keys, exact lines, fixed order."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from fitdocs.dashboards.engine import (
    Action,
    ChartResult,
    Outcome,
    PageResult,
    RunReport,
)
from fitdocs.dashboards.problems import (
    DashboardCode,
    Problem,
    Source,
    dashboard_problem,
)
from fitdocs.dashboards.report import render_json, render_text

PROBLEM_KEYS = [
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
]
CHART_KEYS = [
    "id",
    "line",
    "kind",
    "mode",
    "outcome",
    "snapshot",
    "problems",
    "notices",
]
PAGE_KEYS = ["page", "written", "problems", "notices", "charts"]
TOP_KEYS = ["action", "index", "location_problems", "pages", "removed", "summary"]


def dash(
    code: DashboardCode,
    tag: str,
    *,
    page: str | None,
    chart: str | None = None,
    line: int | None = None,
    **fields: Any,
) -> Problem:
    return dashboard_problem(
        code,
        f"Message {tag}.",
        f"Fix {tag}.",
        page=page,
        chart=chart,
        line=line,
        **fields,
    )


def kit(
    code: str, tag: str, *, page: str, chart: str, line: int, **fields: Any
) -> Problem:
    return Problem(
        Source.CHART,
        code,
        page,
        chart,
        line,
        f"Kit message {tag}.",
        f"Kit fix {tag}.",
        **fields,
    )


def chart(
    chart_id: str | None,
    line: int,
    outcome: Outcome,
    *,
    kind: str | None = "bar",
    mode: str | None = "relative",
    snapshot: str | None = None,
    problems: tuple[Problem, ...] = (),
    notices: tuple[Problem, ...] = (),
) -> ChartResult:
    return ChartResult(chart_id, line, kind, mode, outcome, snapshot, problems, notices)


# -- the main fixture ----------------------------------------------------------
# Every collection is deliberately out of order: pages zeta, mid, alpha;
# alpha's charts at lines 30, 7, 19, 44, 3; problems at lines 9, 7, 7, 7.

LOC_ZZ = dash(DashboardCode.PAGE_NAME, "loc-zz", page="zz.md")
LOC_NONE = dash(DashboardCode.LOCATION_FOREIGN, "loc-none", page=None)
LOC_MM = dash(DashboardCode.PAGE_NAME, "loc-mm", page="mm.md")

PAGE_P40 = dash(DashboardCode.PAGE_CHANGED, "p40", page="alpha", line=40)
PAGE_PNONE = dash(DashboardCode.PAGE_ENCODING, "pnone", page="alpha")
PAGE_P12 = dash(DashboardCode.MARKER_MALFORMED, "p12", page="alpha", line=12)
PAGE_N55 = dash(DashboardCode.REGION_ORPHANED, "n55", page="alpha", line=55)
PAGE_N2 = dash(DashboardCode.REGION_ORPHANED, "n2", page="alpha", line=2)

DELTA_9 = dash(
    DashboardCode.FIELD_VALUE,
    "d9",
    page="alpha",
    chart="delta-c",
    line=9,
    option="title",
)
DELTA_7A = kit(
    "channel_missing",
    "d7a",
    page="alpha",
    chart="delta-c",
    line=7,
    channel="x",
    kind="bar",
    accepted=("number", "date"),
)
DELTA_7B = kit(
    "option_value",
    "d7b",
    page="alpha",
    chart="delta-c",
    line=7,
    option="bins",
    row=3,
    rows=11,
)
# Three kit problems share line 7. They arrive as option_value, channel_missing,
# row_cap with messages d7b, d7a, d7c: neither ascending nor descending by code,
# message or fix, so only a stable sort by line reproduces the arrival order.
DELTA_7C = kit(
    "row_cap",
    "d7c",
    page="alpha",
    chart="delta-c",
    line=7,
    rows=500,
)
DELTA_N = dash(DashboardCode.SQL_CHANGED, "dn", page="alpha", chart="delta-c", line=7)
EPS_N1 = dash(DashboardCode.SQL_CHANGED, "en1", page="alpha", chart="eps-c", line=44)
EPS_N0 = dash(DashboardCode.SQL_CHANGED, "en0", page="alpha", chart="eps-c", line=40)
NOID_P = dash(DashboardCode.YAML_SYNTAX, "noid", page="alpha", line=3)

ALPHA = PageResult(
    "alpha",
    True,
    (PAGE_P40, PAGE_PNONE, PAGE_P12),
    (PAGE_N55, PAGE_N2),
    (
        chart(
            "gamma-c",
            30,
            Outcome.RENDERED,
            mode="frozen",
            snapshot="assets/alpha/gamma-c.snapshot-2.json",
        ),
        chart(
            "delta-c",
            7,
            Outcome.FAILED,
            kind="line",
            problems=(DELTA_9, DELTA_7B, DELTA_7A, DELTA_7C),
            notices=(DELTA_N,),
        ),
        chart("beta-c", 19, Outcome.UNCHANGED),
        chart("eps-c", 44, Outcome.CHECKED, kind="table", notices=(EPS_N1, EPS_N0)),
        chart(None, 3, Outcome.FAILED, kind=None, mode=None, problems=(NOID_P,)),
    ),
)
MID = PageResult(
    "mid",
    False,
    (),
    (),
    (
        chart("m-two", 20, Outcome.UNCHANGED),
        chart("m-one", 10, Outcome.UNCHANGED),
        chart("m-chk", 15, Outcome.CHECKED),
        chart("m-three", 5, Outcome.UNCHANGED),
        chart("m-cx", 25, Outcome.CHECKED),
        chart("m-cy", 8, Outcome.CHECKED),
        chart("m-cz", 17, Outcome.CHECKED),
        chart("m-cw", 12, Outcome.CHECKED),
    ),
)
ZETA = PageResult(
    "zeta",
    True,
    (),
    (),
    (
        chart("z-late", 5, Outcome.RENDERED, kind="hbar"),
        chart("z-early", 2, Outcome.RENDERED, kind="stat"),
    ),
)
REMOVED = (
    "assets/zeta/b.svg",
    "assets/alpha/a.svg",
    "assets/mid/z.svg",
    "assets/alpha/Z.svg",
    "assets/beta/q.svg",
)
REPORT = RunReport(
    Action.REFRESH,
    "ready",
    None,
    (LOC_ZZ, LOC_NONE, LOC_MM),
    (ZETA, MID, ALPHA),
    REMOVED,
)
# charts 15: rendered 3 (gamma, z-late, z-early), unchanged 4 (beta + 3 on mid),
# failed 2 (delta, the id-less one), checked 6 (eps-c, m-chk and four more on mid).
SUMMARY = {"charts": 15, "rendered": 3, "unchanged": 4, "failed": 2}
CHECKED = 6


def text_lines() -> list[str]:
    return [
        "location_foreign: Message loc-none. Fix loc-none.",
        "page_name: Message loc-mm. Fix loc-mm.",
        "page_name: Message loc-zz. Fix loc-zz.",
        "alpha",
        "  page_encoding: Message pnone. Fix pnone.",
        "  marker_malformed: Message p12. Fix p12.",
        "  page_changed: Message p40. Fix p40.",
        "  notice region_orphaned: Message n2. Fix n2.",
        "  notice region_orphaned: Message n55. Fix n55.",
        "alpha:3 - failed",
        "  yaml_syntax: Message noid. Fix noid.",
        "alpha:7 delta-c failed",
        "  option_value: Kit message d7b. Kit fix d7b.",
        "  channel_missing: Kit message d7a. Kit fix d7a. Accepted: number, date.",
        "  row_cap: Kit message d7c. Kit fix d7c.",
        "  field_value: Message d9. Fix d9.",
        "  notice sql_changed: Message dn. Fix dn.",
        "alpha:30 gamma-c rendered",
        "alpha:44 eps-c checked",
        "  notice sql_changed: Message en0. Fix en0.",
        "  notice sql_changed: Message en1. Fix en1.",
        "zeta:2 z-early rendered",
        "zeta:5 z-late rendered",
        "Dashboards: 3 rendered, 4 unchanged, 2 failed, 6 checked, 5 images removed.",
    ]


def only(*pages: PageResult, **fields: Any) -> RunReport:
    return RunReport(
        fields.pop("action", Action.CHECK),
        fields.pop("index", "not_needed"),
        fields.pop("index_problem", None),
        fields.pop("location_problems", ()),
        pages,
        fields.pop("removed", ()),
    )


def quiet_page(*outcomes: Outcome, written: bool = False) -> PageResult:
    return PageResult(
        "quiet",
        written,
        (),
        (),
        tuple(chart(f"c{n}", 10 + n, each) for n, each in enumerate(outcomes)),
    )


# -- JSON ----------------------------------------------------------------------


def test_json_keys_are_in_documented_order_at_every_level() -> None:
    document = json.loads(render_json(REPORT))
    assert list(document) == TOP_KEYS
    assert list(document["index"]) == ["state", "problem"]
    assert list(document["summary"]) == ["charts", "rendered", "unchanged", "failed"]
    pages = document["pages"]
    assert pages, "the fixture has pages"
    for page in pages:
        assert list(page) == PAGE_KEYS
        assert page["charts"], "every fixture page has charts"
        for each in page["charts"]:
            assert list(each) == CHART_KEYS
    alpha = pages[0]
    for group in (
        alpha["problems"],
        alpha["notices"],
        alpha["charts"][1]["problems"],
        alpha["charts"][1]["notices"],
        document["location_problems"],
    ):
        assert group
        for each in group:
            assert list(each) == PROBLEM_KEYS


def test_json_orders_pages_charts_problems_and_removed() -> None:
    document = json.loads(render_json(REPORT))
    assert [page["page"] for page in document["pages"]] == ["alpha", "mid", "zeta"]
    alpha, mid, zeta = document["pages"]
    assert [each["id"] for each in alpha["charts"]] == [
        None,
        "delta-c",
        "beta-c",
        "gamma-c",
        "eps-c",
    ]
    assert [each["line"] for each in alpha["charts"]] == [3, 7, 19, 30, 44]
    assert [each["line"] for each in mid["charts"]] == [5, 8, 10, 12, 15, 17, 20, 25]
    assert [each["line"] for each in zeta["charts"]] == [2, 5]
    assert [each["line"] for each in alpha["problems"]] == [None, 12, 40]
    assert [each["line"] for each in alpha["notices"]] == [2, 55]
    delta = alpha["charts"][1]
    assert [each["message"] for each in delta["problems"]] == [
        "Kit message d7b.",
        "Kit message d7a.",
        "Kit message d7c.",
        "Message d9.",
    ]
    assert [each["message"] for each in alpha["charts"][4]["notices"]] == [
        "Message en0.",
        "Message en1.",
    ]
    assert [each["page"] for each in document["location_problems"]] == [
        None,
        "mm.md",
        "zz.md",
    ]
    assert document["removed"] == sorted(REMOVED)
    assert document["removed"] != list(REMOVED)


def test_json_summary_counts_charts_by_outcome() -> None:
    document = json.loads(render_json(REPORT))
    assert document["summary"] == SUMMARY
    assert len({*SUMMARY.values(), CHECKED, len(REMOVED)}) == 6, "pairwise distinct"


def test_json_carries_action_index_page_and_chart_fields() -> None:
    document = json.loads(render_json(REPORT))
    assert document["action"] == "refresh"
    assert document["index"] == {"state": "ready", "problem": None}
    alpha, mid, zeta = document["pages"]
    assert (alpha["written"], mid["written"], zeta["written"]) == (True, False, True)
    gamma = alpha["charts"][3]
    assert gamma == {
        "id": "gamma-c",
        "line": 30,
        "kind": "bar",
        "mode": "frozen",
        "outcome": "rendered",
        "snapshot": "assets/alpha/gamma-c.snapshot-2.json",
        "problems": [],
        "notices": [],
    }
    assert alpha["charts"][0] == {
        "id": None,
        "line": 3,
        "kind": None,
        "mode": None,
        "outcome": "failed",
        "snapshot": None,
        "problems": [NOID_P.as_dict()],
        "notices": [],
    }
    assert [each["outcome"] for each in mid["charts"]] == [
        "unchanged",
        "checked",
        "unchanged",
        "checked",
        "checked",
        "checked",
        "unchanged",
        "checked",
    ]
    assert [each["kind"] for each in zeta["charts"]] == ["stat", "hbar"]


def test_json_problems_are_as_dict() -> None:
    document = json.loads(render_json(REPORT))
    delta = document["pages"][0]["charts"][1]
    assert delta["problems"][0] == DELTA_7B.as_dict()
    assert delta["problems"][0]["row"] == 3
    assert delta["problems"][1] == DELTA_7A.as_dict()
    assert delta["problems"][1]["accepted"] == ["number", "date"]
    assert delta["problems"][2] == DELTA_7C.as_dict()
    assert delta["problems"][2]["rows"] == 500
    assert delta["problems"][3] == DELTA_9.as_dict()
    assert delta["notices"] == [DELTA_N.as_dict()]
    assert document["location_problems"][0] == LOC_NONE.as_dict()


def test_json_index_state_and_problem() -> None:
    problem = dash(DashboardCode.INDEX_UNAVAILABLE, "idx", page=None)
    report = only(
        quiet_page(Outcome.CHECKED),
        action=Action.REFRESH,
        index="busy",
        index_problem=problem,
    )
    document = json.loads(render_json(report))
    assert document["action"] == "refresh"
    assert document["index"] == {"state": "busy", "problem": problem.as_dict()}
    assert list(document["index"]["problem"]) == PROBLEM_KEYS


def test_json_is_one_non_ascii_preserving_document() -> None:
    problem = dash(DashboardCode.PAGE_NAME, "caf\u00e9", page="caf\u00e9.md")
    report = only(location_problems=(problem,))
    text = render_json(report)
    assert "caf\u00e9.md" in text
    assert json.loads(text)["location_problems"] == [problem.as_dict()]


def test_json_of_an_empty_run() -> None:
    document = json.loads(render_json(only()))
    assert document == {
        "action": "check",
        "index": {"state": "not_needed", "problem": None},
        "location_problems": [],
        "pages": [],
        "removed": [],
        "summary": {"charts": 0, "rendered": 0, "unchanged": 0, "failed": 0},
    }
    assert list(document) == TOP_KEYS


# -- text ----------------------------------------------------------------------


def test_text_lists_exact_lines_in_page_then_line_order() -> None:
    assert render_text(REPORT, chained=False).split("\n") == text_lines()


def test_text_omits_unchanged_and_checked_charts_without_findings() -> None:
    text = render_text(REPORT, chained=False)
    assert "beta-c" not in text
    assert "m-" not in text
    assert "mid" not in text
    assert "eps-c checked" in text


def test_text_shows_an_unchanged_chart_that_has_a_finding() -> None:
    finding = dash(DashboardCode.SQL_CHANGED, "uc", page="quiet", chart="c0", line=10)
    page = PageResult(
        "quiet",
        False,
        (),
        (),
        (chart("c0", 10, Outcome.UNCHANGED, notices=(finding,)),),
    )
    assert render_text(only(page), chained=False).split("\n") == [
        "quiet:10 c0 unchanged",
        "  notice sql_changed: Message uc. Fix uc.",
        "Dashboards: 0 rendered, 1 unchanged, 0 failed.",
    ]


def test_text_shows_a_checked_chart_that_has_a_problem() -> None:
    finding = dash(DashboardCode.WRITE_FAILED, "up", page="quiet", chart="c0", line=10)
    page = PageResult(
        "quiet",
        False,
        (),
        (),
        (chart("c0", 10, Outcome.CHECKED, problems=(finding,)),),
    )
    assert render_text(only(page), chained=False).split("\n") == [
        "quiet:10 c0 checked",
        "  write_failed: Message up. Fix up.",
        "Dashboards: 0 rendered, 0 unchanged, 0 failed, 1 checked.",
    ]


def test_text_of_an_empty_run_is_the_summary_line() -> None:
    assert render_text(only(), chained=False) == (
        "Dashboards: 0 rendered, 0 unchanged, 0 failed."
    )


def test_text_prints_the_index_problem_after_location_problems() -> None:
    problem = dash(DashboardCode.INDEX_UNAVAILABLE, "idx", page=None)
    report = only(
        quiet_page(Outcome.UNCHANGED),
        index="busy",
        index_problem=problem,
        location_problems=(LOC_ZZ,),
    )
    assert render_text(report, chained=False).split("\n") == [
        "page_name: Message loc-zz. Fix loc-zz.",
        "index_unavailable: Message idx. Fix idx.",
        "Dashboards: 0 rendered, 1 unchanged, 0 failed.",
    ]


def test_text_summary_names_removed_images_only_when_there_are_some() -> None:
    page = quiet_page(Outcome.RENDERED)
    without = render_text(only(page), chained=False)
    with_one = render_text(only(page, removed=("assets/a.svg",)), chained=False)
    assert without.split("\n")[-1] == "Dashboards: 1 rendered, 0 unchanged, 0 failed."
    assert with_one.split("\n")[-1] == (
        "Dashboards: 1 rendered, 0 unchanged, 0 failed, 1 images removed."
    )


def test_text_collapses_a_multi_line_database_message_to_one_line() -> None:
    message = (
        'Parser Error: syntax error at or near "SELEC"\n\nLINE 1: SELEC 1\n        ^.'
    )
    problem = replace(
        dash(DashboardCode.SQL_FAILED, "db", page="quiet", chart="c0", line=10),
        message=message,
        fix="Fix the statement,\r\n\tthen run it again.",
    )
    page = PageResult(
        "quiet", False, (), (), (chart("c0", 10, Outcome.FAILED, problems=(problem,)),)
    )
    lines = render_text(only(page), chained=False).split("\n")
    assert lines == [
        "quiet:10 c0 failed",
        '  sql_failed: Parser Error: syntax error at or near "SELEC" LINE 1: SELEC 1 ^.'
        " Fix the statement, then run it again.",
        "Dashboards: 0 rendered, 0 unchanged, 1 failed.",
    ]
    assert (
        json.loads(render_json(only(page)))["pages"][0]["charts"][0]["problems"][0][
            "message"
        ]
        == message
    )


@pytest.mark.parametrize(
    "separator", ["\u2028", "\u2029", "\x85", "\x0b", "\x0c", "\x1c"]
)
def test_text_problem_stays_on_one_line_for_unicode_line_separators(
    separator: str,
) -> None:
    problem = replace(
        dash(DashboardCode.SQL_FAILED, "db", page="quiet", chart="c0", line=10),
        message=f"first{separator}Dashboards: 9 rendered, 9 unchanged, 9 failed.",
    )
    page = PageResult(
        "quiet", False, (), (), (chart("c0", 10, Outcome.FAILED, problems=(problem,)),)
    )
    text = render_text(only(page), chained=False)
    assert text.splitlines() == text.split("\n"), "only newlines separate lines"
    assert len(text.split("\n")) == 3
    assert text.split("\n")[1].startswith("  sql_failed: first Dashboards: 9 ")


def test_text_marks_notice_severity_from_the_problem_not_the_list() -> None:
    # A notice code placed in the problems list keeps its notice label, and a
    # problem code placed in the notices list does not gain one.
    notice_in_problems = dash(
        DashboardCode.SQL_CHANGED, "np", page="quiet", chart="c0", line=10
    )
    problem_in_notices = dash(
        DashboardCode.WRITE_FAILED, "pn", page="quiet", chart="c0", line=10
    )
    page = PageResult(
        "quiet",
        False,
        (),
        (),
        (
            chart(
                "c0",
                10,
                Outcome.FAILED,
                problems=(notice_in_problems,),
                notices=(problem_in_notices,),
            ),
        ),
    )
    lines = render_text(only(page), chained=False).split("\n")
    assert lines[1] == "  notice sql_changed: Message np. Fix np."
    assert lines[2] == "  write_failed: Message pn. Fix pn."


# -- chained -------------------------------------------------------------------


def test_chained_text_is_empty_for_unchanged_charts_without_findings() -> None:
    report = only(quiet_page(Outcome.UNCHANGED, Outcome.CHECKED, Outcome.UNCHANGED))
    assert render_text(report, chained=True) == ""
    assert render_text(report, chained=False) != "", "the plain form still reports"


def test_chained_text_is_empty_for_a_run_with_no_pages() -> None:
    assert render_text(only(), chained=True) == ""


def test_chained_text_equals_plain_text_when_there_is_something_to_say() -> None:
    assert render_text(REPORT, chained=True) == render_text(REPORT, chained=False)
    assert "beta-c" not in render_text(REPORT, chained=True)
    assert "m-" not in render_text(REPORT, chained=True)


def test_chained_text_does_not_list_unchanged_charts() -> None:
    report = only(
        PageResult(
            "quiet",
            True,
            (),
            (),
            (
                chart("kept", 40, Outcome.RENDERED),
                chart("same", 20, Outcome.UNCHANGED),
            ),
        )
    )
    assert render_text(report, chained=True).split("\n") == [
        "quiet:40 kept rendered",
        "Dashboards: 1 rendered, 1 unchanged, 0 failed.",
    ]


@pytest.mark.parametrize(
    "report",
    [
        only(quiet_page(Outcome.UNCHANGED, Outcome.RENDERED)),
        only(quiet_page(Outcome.UNCHANGED, Outcome.FAILED)),
        only(quiet_page(Outcome.UNCHANGED), removed=("assets/a.svg",)),
        only(quiet_page(Outcome.UNCHANGED), location_problems=(LOC_MM,)),
        only(
            quiet_page(Outcome.UNCHANGED),
            index="busy",
            index_problem=dash(DashboardCode.INDEX_UNAVAILABLE, "i", page=None),
        ),
        only(quiet_page(Outcome.UNCHANGED, written=True)),
        only(
            replace(
                quiet_page(Outcome.UNCHANGED),
                problems=(dash(DashboardCode.PAGE_CHANGED, "pp", page="quiet"),),
            )
        ),
        only(
            replace(
                quiet_page(Outcome.UNCHANGED),
                notices=(dash(DashboardCode.REGION_ORPHANED, "pn", page="quiet"),),
            )
        ),
        only(
            PageResult(
                "quiet",
                False,
                (),
                (),
                (
                    chart(
                        "c0",
                        10,
                        Outcome.UNCHANGED,
                        problems=(
                            dash(DashboardCode.WRITE_FAILED, "cp", page="quiet"),
                        ),
                    ),
                ),
            )
        ),
        only(
            PageResult(
                "quiet",
                False,
                (),
                (),
                (
                    chart(
                        "c0",
                        10,
                        Outcome.UNCHANGED,
                        notices=(dash(DashboardCode.SQL_CHANGED, "cn", page="quiet"),),
                    ),
                ),
            )
        ),
    ],
    ids=[
        "rendered",
        "failed",
        "removed",
        "location",
        "index",
        "page-written",
        "page-problem",
        "page-notice",
        "chart-problem",
        "chart-notice",
    ],
)
def test_chained_text_speaks_for_each_kind_of_news(report: RunReport) -> None:
    assert render_text(only(quiet_page(Outcome.UNCHANGED)), chained=True) == ""
    assert render_text(report, chained=True) != ""


def test_chained_failed_chart_without_a_problem_still_speaks() -> None:
    report = only(quiet_page(Outcome.FAILED))
    assert render_text(report, chained=True).split("\n") == [
        "quiet:10 c0 failed",
        "Dashboards: 0 rendered, 0 unchanged, 1 failed.",
    ]


# -- failed (the engine's property, as the exit code reads it) -----------------


def test_failed_is_false_for_notices_only() -> None:
    notice = dash(DashboardCode.REGION_ORPHANED, "n", page="quiet", line=1)
    page_with_notices = PageResult(
        "quiet",
        False,
        (),
        (notice,),
        (chart("c0", 10, Outcome.UNCHANGED, notices=(notice,)),),
    )
    report = only(page_with_notices)
    assert report.failed is False
    assert render_text(report, chained=True) != "", "the notices are still reported"


@pytest.mark.parametrize(
    "report",
    [
        only(location_problems=(LOC_MM,)),
        only(index_problem=dash(DashboardCode.INDEX_UNAVAILABLE, "i", page=None)),
        only(replace(quiet_page(Outcome.UNCHANGED), problems=(PAGE_P12,))),
        only(
            PageResult(
                "quiet",
                False,
                (),
                (),
                (chart("c0", 10, Outcome.FAILED, problems=(DELTA_9,)),),
            )
        ),
    ],
    ids=["location", "index", "page", "chart"],
)
def test_failed_is_true_for_a_problem_anywhere(report: RunReport) -> None:
    assert only(quiet_page(Outcome.UNCHANGED)).failed is False
    assert report.failed is True


def test_json_layout_of_an_empty_run_is_pinned_byte_for_byte() -> None:
    assert render_json(only()) == "\n".join(
        [
            "{",
            '  "action": "check",',
            '  "index": {',
            '    "state": "not_needed",',
            '    "problem": null',
            "  },",
            '  "location_problems": [],',
            '  "pages": [],',
            '  "removed": [],',
            '  "summary": {',
            '    "charts": 0,',
            '    "rendered": 0,',
            '    "unchanged": 0,',
            '    "failed": 0',
            "  }",
            "}",
        ]
    )


def test_text_puts_location_then_index_problems_before_every_page() -> None:
    problem = dash(DashboardCode.INDEX_UNAVAILABLE, "idx", page=None)
    report = replace(REPORT, index="needs_rebuild", index_problem=problem)
    lines = render_text(report, chained=False).split("\n")
    expected = text_lines()
    assert lines == [
        *expected[:3],
        "index_unavailable: Message idx. Fix idx.",
        *expected[3:],
    ]


def test_text_summary_counts_checked_charts_before_removed_images() -> None:
    clean = only(quiet_page(Outcome.CHECKED, Outcome.CHECKED, Outcome.CHECKED))
    assert render_text(clean, chained=False) == (
        "Dashboards: 0 rendered, 0 unchanged, 0 failed, 3 checked."
    )
    both = only(
        quiet_page(Outcome.CHECKED, Outcome.CHECKED, Outcome.RENDERED),
        removed=("assets/a.svg", "assets/b.svg"),
    )
    assert render_text(both, chained=False).split("\n")[-1] == (
        "Dashboards: 1 rendered, 0 unchanged, 0 failed, 2 checked, 2 images removed."
    )
    none = only(quiet_page(Outcome.RENDERED))
    assert "checked" not in render_text(none, chained=False)


def test_text_appends_accepted_values_after_the_fix_only_when_present() -> None:
    with_values = replace(
        dash(DashboardCode.MISSING_KEY, "mk", page="quiet", chart="c0", line=10),
        accepted=("sql", "ki\n  nd", "title"),
    )
    single = replace(with_values, accepted=("sql",))
    without = dash(DashboardCode.FIELD_VALUE, "fv", page="quiet", chart="c0", line=11)
    page = PageResult(
        "quiet",
        False,
        (),
        (),
        (chart("c0", 10, Outcome.FAILED, problems=(with_values, single, without)),),
    )
    lines = render_text(only(page), chained=False).split("\n")
    assert lines[1:4] == [
        "  missing_key: Message mk. Fix mk. Accepted: sql, ki nd, title.",
        "  missing_key: Message mk. Fix mk. Accepted: sql.",
        "  field_value: Message fv. Fix fv.",
    ]
    document = json.loads(render_json(only(page)))
    problems = document["pages"][0]["charts"][0]["problems"]
    assert [each["accepted"] for each in problems] == [
        ["sql", "ki\n  nd", "title"],
        ["sql"],
        [],
    ]
