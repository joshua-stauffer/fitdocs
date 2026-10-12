"""Engine, discovery and planning half: pages, targets, associations, data need.

``run`` passes an opener that raises, because the planning half renders nothing
and opens no source. ``test_planning_changes_no_file`` compares bytes and
``st_mtime_ns`` of the whole data root before and after a run.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from fitdocs.dashboards import engine
from fitdocs.dashboards.engine import (
    Action,
    ChartResult,
    DataNeed,
    Outcome,
    PageResult,
    PlannedChart,
    PlannedPage,
    RunReport,
    RunRequest,
    Target,
    TargetError,
    has_dashboards,
    plan_run,
    resolve_targets,
    run_dashboards,
)
from fitdocs.dashboards.problems import (
    DashboardCode,
    Problem,
    Severity,
    dashboard_problem,
)
from fitdocs.dashboards.storage import Refusal
from tests.dashboards._helpers import (
    MustNotOpen,
    assert_untouched,
    directive_block,
    make_data_root,
    page_text,
    region_block,
    snapshot_of,
    write_page,
)

TODAY = date(2026, 10, 12)
GOLDEN = (
    Path(__file__).resolve().parents[1] / "declaration_golden" / "dashboards.AGENTS.md"
)
OPENER = "<!-- fitdocs:chart"


def keys(chart_id: str, *, mode: str = "relative") -> list[tuple[str, str]]:
    return [
        ("id", chart_id),
        ("kind", "bar"),
        ("mode", mode),
        ("title", f"Title of {chart_id}"),
        ("sql", "|\n  select 1 as a"),
    ]


def chart(chart_id: str, *, mode: str = "relative") -> str:
    return directive_block(keys(chart_id, mode=mode))


def line_of(text: str, needle: str, nth: int = 0) -> int:
    found = [n for n, each in enumerate(text.split("\n"), 1) if each == needle]
    return found[nth]


def begin(chart_id: str) -> str:
    return f"<!-- fitdocs:begin:chart:{chart_id} -->"


def request(
    root: Path,
    *targets: Target,
    action: Action = Action.CHECK,
) -> RunRequest:
    return RunRequest(action, root, tuple(targets), TODAY)


def run(root: Path, *targets: Target, action: Action = Action.CHECK) -> RunReport:
    guard = MustNotOpen()
    report = run_dashboards(request(root, *targets, action=action), guard)
    assert guard.attempts == 0, "5.1 plans only: the source is never opened"
    return report


def page_of(report: RunReport, name: str) -> PageResult:
    found = [each for each in report.pages if each.page == name]
    assert len(found) == 1, [each.page for each in report.pages]
    return found[0]


def result_of(page: PageResult, chart_id: str) -> ChartResult:
    found = [each for each in page.charts if each.chart == chart_id]
    assert len(found) == 1, [each.chart for each in page.charts]
    return found[0]


def codes(problems: Sequence[Problem]) -> list[str]:
    return [each.code for each in problems]


def planned(
    plan_pages: Sequence[PlannedPage], name: str, chart_id: str
) -> PlannedChart:
    page = next(each for each in plan_pages if each.name == name)
    return next(each for each in page.charts if each.chart == chart_id)


# -- discovery -----------------------------------------------------------------


def test_declaration_file_is_neither_a_page_nor_a_misnamed_file(tmp_path: Path) -> None:
    golden = GOLDEN.read_bytes()
    assert b"<!-- fitdocs:begin:chart:<id> -->" in golden, "the golden is a decoy"
    root = make_data_root(tmp_path)
    write_page(root, "zeta", page_text(chart("first"), chart("second")))
    (root / "dashboards" / "AGENTS.md").write_bytes(golden)
    report = run(root)
    assert [each.page for each in report.pages] == ["zeta"]
    assert report.location_problems == ()
    assert report.pages[0].problems == ()
    assert [each.chart for each in report.pages[0].charts] == ["first", "second"]


def test_misnamed_file_is_reported_and_the_next_page_is_planned(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "Running", page_text("prose"))
    write_page(root, "weekly", page_text(chart("a"), chart("b")))
    write_page(root, "weekly_2026", page_text(chart("c"), chart("d")))
    report = run(root)
    assert [each.page for each in report.pages] == ["weekly"]
    assert [each.page for each in report.location_problems] == [
        "Running.md",
        "weekly_2026.md",
    ]
    problem = report.location_problems[0]
    assert problem.code == DashboardCode.PAGE_NAME.value
    assert problem.page == "Running.md"
    assert problem.chart is None and problem.line is None
    assert "Running.md" in problem.message
    assert "lowercase" in problem.message and "hyphens" in problem.message
    assert report.failed
    assert [each.outcome for each in report.pages[0].charts] == [Outcome.CHECKED] * 2


def test_nested_files_are_not_pages(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "top", page_text(chart("a"), chart("b")))
    nested = root / "dashboards" / "sub"
    nested.mkdir()
    (nested / "x.md").write_bytes(page_text(chart("nested")).encode())
    (nested / "Bad Name.md").write_bytes(b"prose\n")
    report = run(root)
    assert [each.page for each in report.pages] == ["top"]
    assert report.location_problems == ()
    assert not report.failed


@pytest.mark.parametrize("shape", ["page_link", "dir_link", "assets_link", "file"])
def test_foreign_location_is_one_problem_and_no_pages(
    tmp_path: Path, shape: str
) -> None:
    root = make_data_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "inside.md").write_bytes(page_text(chart("a"), chart("b")).encode())
    if shape == "dir_link":
        (root / "dashboards").symlink_to(elsewhere)
    elif shape == "file":
        (root / "dashboards").write_bytes(b"not a directory\n")
    else:
        write_page(root, "real", page_text(chart("a"), chart("b")))
        if shape == "assets_link":
            (root / "dashboards" / "assets").symlink_to(elsewhere)
        else:
            (root / "dashboards" / "linked.md").symlink_to(elsewhere / "inside.md")
    report = run(root)
    if shape == "page_link":
        assert report.location_problems == ()
        return
    (problem,) = report.location_problems
    assert problem.code == DashboardCode.LOCATION_FOREIGN.value
    assert report.pages == ()
    assert report.failed


def test_symlinked_and_non_utf8_pages_do_not_stop_later_pages(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_bytes(page_text(chart("a"), chart("b")).encode())
    directory = root / "dashboards"
    directory.mkdir()
    (directory / "aaa.md").symlink_to(outside)
    (directory / "bbb.md").write_bytes(b"caf\xe9 \xff\xfe\n")
    (directory / "ccc.md").mkdir()
    write_page(root, "ddd", page_text(chart("one"), chart("two")))
    report = run(root)
    assert [each.page for each in report.pages] == ["aaa", "bbb", "ccc", "ddd"]
    aaa, bbb, ccc, ddd = report.pages
    assert codes(aaa.problems) == [DashboardCode.PAGE_UNREADABLE.value]
    assert codes(bbb.problems) == [DashboardCode.PAGE_ENCODING.value]
    assert codes(ccc.problems) == [DashboardCode.PAGE_UNREADABLE.value]
    for broken in (aaa, bbb, ccc):
        assert broken.charts == () and not broken.written
        assert broken.problems[0].page == broken.page
        assert broken.problems[0].line is None
    assert ddd.problems == ()
    assert [each.outcome for each in ddd.charts] == [Outcome.CHECKED] * 2
    assert report.failed


@pytest.mark.parametrize(
    ("refusal", "code"),
    [
        (Refusal.SYMLINK, DashboardCode.PAGE_UNREADABLE),
        (Refusal.NOT_REGULAR, DashboardCode.PAGE_UNREADABLE),
        (Refusal.UNREADABLE, DashboardCode.PAGE_UNREADABLE),
        (Refusal.NOT_UTF8, DashboardCode.PAGE_ENCODING),
    ],
)
def test_every_read_refusal_maps_to_a_page_problem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refusal: Refusal,
    code: DashboardCode,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "page", page_text(chart("a")))
    monkeypatch.setattr(engine, "read_page", lambda _root, _name: refusal)
    report = run(root)
    (problem,) = report.pages[0].problems
    assert problem.code == code.value
    assert problem.page == "page"
    assert problem.message.endswith(".") and problem.fix.endswith(".")


def test_frontmatter_is_not_consulted(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "plain", page_text(chart("a"), chart("b")))
    write_page(
        root,
        "tagged",
        page_text(chart("a"), chart("b"), frontmatter={"type": "workout"}),
    )
    report = run(root)
    assert [each.page for each in report.pages] == ["plain", "tagged"]
    for page in report.pages:
        assert [each.outcome for each in page.charts] == [Outcome.CHECKED] * 2


def test_pages_are_planned_in_name_order_whatever_the_listing_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    for name in ("mid", "zulu", "alpha"):
        write_page(root, name, page_text(chart("a"), chart("b")))
    write_page(root, "Zed", "prose\n")
    write_page(root, "Abc", "prose\n")
    scrambled = ("zulu", "Zed", "mid", "alpha", "Abc")
    monkeypatch.setattr(engine, "list_markdown", lambda _root: scrambled)
    report = run(root)
    assert [each.page for each in report.pages] == ["alpha", "mid", "zulu"]
    assert [each.page for each in report.location_problems] == ["Abc.md", "Zed.md"]
    targeted = run(root, Target("zulu", None), Target("alpha", None))
    assert [each.page for each in targeted.pages] == ["alpha", "zulu"]


def test_charts_are_in_page_order_not_id_order(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(chart("zeta"), chart("mid"), chart("alpha"))
    write_page(root, "p", text)
    page = run(root).pages[0]
    assert [each.chart for each in page.charts] == ["zeta", "mid", "alpha"]
    assert [each.line for each in page.charts] == [
        line_of(text, OPENER, n) for n in range(3)
    ]


# -- has_dashboards ------------------------------------------------------------


def test_has_dashboards(tmp_path: Path) -> None:
    def fresh(name: str) -> Path:
        return make_data_root(tmp_path, name)

    assert not has_dashboards(fresh("none"))

    empty = fresh("empty")
    (empty / "dashboards").mkdir()
    assert not has_dashboards(empty)

    only_declaration = fresh("declaration")
    (only_declaration / "dashboards").mkdir()
    (only_declaration / "dashboards" / "AGENTS.md").write_bytes(GOLDEN.read_bytes())
    assert not has_dashboards(only_declaration)

    nested_only = fresh("nested")
    (nested_only / "dashboards" / "sub").mkdir(parents=True)
    (nested_only / "dashboards" / "sub" / "x.md").write_bytes(b"prose\n")
    assert not has_dashboards(nested_only)

    page = fresh("page")
    write_page(page, "weekly", "prose\n")
    assert has_dashboards(page)

    misnamed = fresh("misnamed")
    write_page(misnamed, "Weekly", "prose\n")
    assert has_dashboards(misnamed)

    target = tmp_path / "linked-target"
    target.mkdir()
    linked = fresh("linked")
    (linked / "dashboards").symlink_to(target)
    assert has_dashboards(linked), "a symlinked dashboards/ holding nothing"

    dangling = fresh("dangling")
    (dangling / "dashboards").symlink_to(tmp_path / "nowhere")
    assert has_dashboards(dangling)

    assets_link = fresh("assets-link")
    (assets_link / "dashboards").mkdir()
    (assets_link / "dashboards" / "assets").symlink_to(target)
    assert has_dashboards(assets_link)

    a_file = fresh("a-file")
    (a_file / "dashboards").write_bytes(b"x")
    assert has_dashboards(a_file)


# -- directive problems and attribution ------------------------------------------


def test_unparsed_directives_keep_the_chart_the_parser_left_none(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    shape = f"{OPENER}\n- one\n- two\n-->\n"
    syntax = f"{OPENER}\nid: [oops\n-->\n"
    duplicate_key = directive_block([("id", "dk"), ("id", "dk-again"), *keys("x")[1:]])
    missing = directive_block([item for item in keys("miss") if item[0] != "kind"])
    text = page_text(chart("good"), shape, syntax, duplicate_key, missing)
    write_page(root, "p", text)
    page = run(root).pages[0]
    by_line = {each.line: each for each in page.charts}
    assert sorted(by_line) == [line_of(text, OPENER, n) for n in range(5)]
    good, s_shape, s_syntax, s_dup, s_miss = (by_line[k] for k in sorted(by_line))
    assert good.outcome is Outcome.CHECKED and good.problems == ()
    for unparsed, code in (
        (s_shape, DashboardCode.YAML_SHAPE),
        (s_syntax, DashboardCode.YAML_SYNTAX),
        (s_dup, DashboardCode.DUPLICATE_KEY),
    ):
        assert unparsed.chart is None
        assert unparsed.outcome is Outcome.FAILED
        assert unparsed.kind is None and unparsed.mode is None
        assert code.value in codes(unparsed.problems)
        assert all(each.chart is None for each in unparsed.problems)
    assert s_miss.chart == "miss" and s_miss.outcome is Outcome.FAILED
    assert codes(s_miss.problems) == [DashboardCode.MISSING_KEY.value]
    assert s_miss.problems[0].chart == "miss"
    for each in page.charts:
        for problem in each.problems:
            assert problem.page == "p"
            assert problem.line is not None


def test_a_parsed_chart_reports_its_kind_and_mode_and_opener_line(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    text = page_text("# Heading", chart("first"), chart("later", mode="frozen"))
    write_page(root, "p", text)
    page = run(root).pages[0]
    later = result_of(page, "later")
    assert (later.kind, later.mode) == ("bar", "frozen")
    assert later.line == line_of(text, OPENER, 1)
    assert later.problems == () and later.notices == ()
    assert later.outcome is Outcome.CHECKED
    assert later.snapshot is None


@pytest.mark.parametrize("unknown_first", [False, True])
def test_a_chart_problems_are_in_page_line_order(
    tmp_path: Path, unknown_first: bool
) -> None:
    root = make_data_root(tmp_path)
    extra = [("zzz", "1"), ("channels", "nope")]
    ordered = [*keys("late"), *(extra if unknown_first else extra[::-1])]
    text = page_text(chart("first"), directive_block(ordered))
    write_page(root, "p", text)
    result = result_of(run(root).pages[0], "late")
    lines = [each.line for each in result.problems]
    assert all(each is not None for each in lines)
    assert lines == sorted(each for each in lines if each is not None)
    assert sorted(codes(result.problems)) == [
        DashboardCode.FIELD_VALUE.value,
        DashboardCode.UNKNOWN_KEY.value,
    ]
    expected = (
        ["zzz: 1", "channels: nope"] if unknown_first else ["channels: nope", "zzz: 1"]
    )
    assert lines == [line_of(text, each) for each in expected]
    assert codes(result.problems) == (
        [DashboardCode.UNKNOWN_KEY.value, DashboardCode.FIELD_VALUE.value]
        if unknown_first
        else [DashboardCode.FIELD_VALUE.value, DashboardCode.UNKNOWN_KEY.value]
    )


def test_terminator_and_unclosed_directives_fail_alone(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    terminator = directive_block(
        [("id", "term"), *[(k, v) for k, v in keys("x")[1:]], ("window", "a --> b")]
    )
    unclosed = f"{OPENER}\nid: open\n"
    text = page_text(chart("good"), terminator, "between", unclosed)
    write_page(root, "p", text)
    page = run(root).pages[0]
    good, term, opened = page.charts
    assert good.outcome is Outcome.CHECKED
    assert term.chart == "term" and term.outcome is Outcome.FAILED
    (term_problem,) = term.problems
    assert term_problem.code == DashboardCode.DIRECTIVE_TERMINATOR.value
    assert term_problem.line == line_of(text, "window: a --> b")
    assert term_problem.chart == "term"
    assert opened.chart is None and opened.outcome is Outcome.FAILED
    (open_problem,) = opened.problems
    assert open_problem.code == DashboardCode.DIRECTIVE_UNCLOSED.value
    assert open_problem.line == opened.line == line_of(text, OPENER, 2)


def test_page_scan_problems_are_page_problems(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("a"), "  <!-- fitdocs:chart", chart("b"), "<!-- fitdocs:end:chart:z -->"
    )
    write_page(root, "p", text)
    page = run(root).pages[0]
    assert codes(page.problems) == [
        DashboardCode.OPENER_MALFORMED.value,
        DashboardCode.MARKER_MALFORMED.value,
    ]
    assert [each.line for each in page.problems] == [
        line_of(text, "  <!-- fitdocs:chart"),
        line_of(text, "<!-- fitdocs:end:chart:z -->"),
    ]
    assert [each.outcome for each in page.charts] == [Outcome.CHECKED] * 2


# -- duplicate ids ---------------------------------------------------------------


def test_duplicate_ids_fail_every_chart_that_shares_the_id(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("pace"),
        region_block("pace", "one"),
        chart("other"),
        region_block("other", "two"),
        chart("pace"),
        region_block("pace", "three"),
        chart("pace"),
    )
    write_page(root, "p", text)
    page = run(root).pages[0]
    outcomes = [(each.chart, each.outcome) for each in page.charts]
    assert outcomes == [
        ("pace", Outcome.FAILED),
        ("other", Outcome.CHECKED),
        ("pace", Outcome.FAILED),
        ("pace", Outcome.FAILED),
    ]
    for each in (page.charts[0], page.charts[2], page.charts[3]):
        assert codes(each.problems) == [DashboardCode.DUPLICATE_ID.value]
        assert each.problems[0].chart == "pace"
        assert each.problems[0].line == each.line


def test_exactly_two_directives_with_one_id_both_fail(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(chart("fine"), chart("twin"), chart("twin")))
    page = run(root).pages[0]
    assert [(each.chart, each.outcome) for each in page.charts] == [
        ("fine", Outcome.CHECKED),
        ("twin", Outcome.FAILED),
        ("twin", Outcome.FAILED),
    ]


# -- regions ---------------------------------------------------------------------


def test_region_under_another_directive_is_a_mismatch(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("fine"),
        region_block("fine", "ok"),
        chart("a"),
        region_block("b", "mine"),
        chart("c"),
    )
    write_page(root, "p", text)
    page = run(root).pages[0]
    a = result_of(page, "a")
    assert codes(a.problems) == [DashboardCode.REGION_MISMATCH.value]
    assert a.problems[0].line == line_of(text, begin("b"))
    assert a.problems[0].chart == "a"
    assert a.outcome is Outcome.FAILED
    assert result_of(page, "fine").outcome is Outcome.CHECKED
    assert result_of(page, "c").outcome is Outcome.CHECKED
    assert page.notices == (), "a region under a directive is not an orphan"
    planned_a = planned(plan_run(request(root)).pages, "p", "a")
    assert planned_a.region is None
    assert planned(plan_run(request(root)).pages, "p", "fine").region is not None


def test_a_mismatched_region_whose_id_is_a_directive_elsewhere_is_misplaced_there(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    text = page_text(chart("keep"), chart("a"), region_block("b"), chart("b"))
    write_page(root, "p", text)
    page = run(root).pages[0]
    assert codes(result_of(page, "a").problems) == [DashboardCode.REGION_MISMATCH.value]
    b = result_of(page, "b")
    assert codes(b.problems) == [DashboardCode.REGION_MISPLACED.value]
    assert b.problems[0].line == line_of(text, begin("b"))
    assert b.problems[0].chart == "b"
    assert page.notices == ()


@pytest.mark.parametrize("where", ["below", "above"])
def test_region_not_directly_below_is_misplaced(tmp_path: Path, where: str) -> None:
    root = make_data_root(tmp_path)
    region = region_block("x", "hand placed")
    if where == "below":
        parts = [chart("ok"), region_block("ok"), chart("x"), "prose", region]
    else:
        parts = [chart("ok"), region_block("ok"), region, "prose", chart("x")]
    text = page_text(*parts)
    write_page(root, "p", text)
    page = run(root).pages[0]
    x = result_of(page, "x")
    assert codes(x.problems) == [DashboardCode.REGION_MISPLACED.value]
    assert x.problems[0].line == line_of(text, begin("x"))
    assert x.outcome is Outcome.FAILED
    assert result_of(page, "ok").outcome is Outcome.CHECKED
    assert page.notices == ()


def test_a_region_below_a_directive_without_an_id_is_not_an_orphan(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("ok"), f"{OPENER}\nid: [oops\n-->\n", region_block("ghost", "x")
    )
    write_page(root, "p", text)
    page = run(root).pages[0]
    assert [each.chart for each in page.charts] == ["ok", None]
    assert page.charts[1].outcome is Outcome.FAILED
    assert codes(page.charts[1].problems) == [DashboardCode.YAML_SYNTAX.value]
    assert page.charts[0].problems == ()
    assert page.notices == ()


def test_a_region_far_from_a_chart_that_failed_to_parse_is_misplaced_not_orphaned(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    broken = directive_block([item for item in keys("miss") if item[0] != "kind"])
    text = page_text(chart("ok"), broken, "prose", region_block("miss", "hand placed"))
    write_page(root, "p", text)
    page = run(root).pages[0]
    miss = result_of(page, "miss")
    assert codes(miss.problems) == [
        DashboardCode.MISSING_KEY.value,
        DashboardCode.REGION_MISPLACED.value,
    ]
    assert page.notices == ()


def test_unclosed_region_cut_by_a_directive_leaves_the_next_chart_planned(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("ok"),
        region_block("ok", "fine"),
        chart("a"),
        region_block("a", "half", closed=False),
        chart("b"),
        region_block("b", "whole"),
    )
    write_page(root, "p", text)
    page = run(root).pages[0]
    a = result_of(page, "a")
    assert codes(a.problems) == [DashboardCode.REGION_CONTENTS.value]
    assert a.problems[0].line == line_of(text, OPENER, 2)
    assert a.outcome is Outcome.FAILED
    assert result_of(page, "b").outcome is Outcome.CHECKED
    assert result_of(page, "ok").outcome is Outcome.CHECKED


@pytest.mark.parametrize(
    "intruder",
    [
        "<!-- fitdocs:begin:chart:z -->",
        "<!-- fitdocs:end:chart:z -->",
    ],
)
def test_region_cut_by_another_marker_is_region_contents(
    tmp_path: Path, intruder: str
) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("ok"),
        region_block("ok", "fine"),
        chart("a"),
        region_block("a", "half", closed=False),
        intruder,
    )
    write_page(root, "p", text)
    a = result_of(run(root).pages[0], "a")
    assert codes(a.problems) == [DashboardCode.REGION_CONTENTS.value]
    assert a.problems[0].line == line_of(text, intruder)


def test_region_running_to_the_end_of_the_page_is_unclosed(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("ok"),
        region_block("ok", "fine"),
        chart("a"),
        region_block("a", "half", closed=False),
    )
    write_page(root, "p", text)
    page = run(root).pages[0]
    a = result_of(page, "a")
    assert codes(a.problems) == [DashboardCode.REGION_UNCLOSED.value]
    assert a.problems[0].line == line_of(text, begin("a"))
    assert result_of(page, "ok").outcome is Outcome.CHECKED


def test_orphan_region_is_a_notice_only(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("one"),
        region_block("one", "kept"),
        "prose",
        region_block("ghost", "left alone"),
    )
    write_page(root, "p", text)
    report = run(root)
    page = report.pages[0]
    (notice,) = page.notices
    assert notice.code == DashboardCode.REGION_ORPHANED.value
    assert notice.severity is Severity.NOTICE
    assert notice.line == line_of(text, begin("ghost"))
    assert notice.page == "p"
    assert page.problems == ()
    assert all(each.problems == () for each in page.charts)
    assert not report.failed


# -- targets ---------------------------------------------------------------------


def _targets_root(tmp_path: Path) -> Path:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("zeta"),
        f"{OPENER}\nid: broken\n-->\n",
        f"{OPENER}\nid: [oops\n-->\n",
        "  <!-- fitdocs:chart",
        chart("alpha"),
    )
    write_page(root, "alpha", text)
    write_page(root, "mid", page_text(chart("m-one"), chart("m-two")))
    write_page(root, "zulu", page_text(chart("a-one"), f"{OPENER}\nid: a-bad\n-->\n"))
    return root


def test_a_chart_target_reports_only_that_chart_and_still_the_page_problems(
    tmp_path: Path,
) -> None:
    root = _targets_root(tmp_path)
    everything = run(root)
    assert everything.failed
    report = run(root, Target("alpha", "alpha"))
    assert [each.page for each in report.pages] == ["alpha"]
    page = report.pages[0]
    assert [each.chart for each in page.charts] == ["alpha"]
    assert page.charts[0].outcome is Outcome.CHECKED
    assert codes(page.problems) == [DashboardCode.OPENER_MALFORMED.value]
    assert report.location_problems == ()


def test_a_page_target_covers_every_chart_of_that_page_only(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    report = run(root, Target("zulu", None))
    assert [each.page for each in report.pages] == ["zulu"]
    assert len(report.pages[0].charts) == 2
    assert report.failed


@pytest.mark.parametrize("page_first", [False, True])
def test_a_page_target_subsumes_a_chart_target_on_the_same_page(
    tmp_path: Path, page_first: bool
) -> None:
    root = _targets_root(tmp_path)
    pair = (Target("mid", "m-two"), Target("mid", None))
    report = run(root, *(pair[::-1] if page_first else pair))
    assert [each.chart for each in report.pages[0].charts] == ["m-one", "m-two"]


def test_misnamed_files_are_only_reported_for_a_whole_run(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    write_page(root, "Bad", "prose\n")
    assert codes(run(root).location_problems) == [DashboardCode.PAGE_NAME.value]
    assert run(root, Target("mid", None)).location_problems == ()


def test_two_chart_targets_on_one_page_cover_both_charts(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    report = run(root, Target("mid", "m-two"), Target("mid", "m-one"))
    assert [each.chart for each in report.pages[0].charts] == ["m-one", "m-two"]
    only_first = run(root, Target("mid", "m-one"))
    assert [each.chart for each in only_first.pages[0].charts] == ["m-one"]


def test_resolve_targets_collapses_sorts_and_subsumes(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    resolved = resolve_targets(
        root, ["zulu:a-one", "mid:m-two", "alpha", "alpha", "alpha:zeta", "zulu:a-one"]
    )
    assert resolved == (
        Target("alpha", None),
        Target("mid", "m-two"),
        Target("zulu", "a-one"),
    )
    assert resolve_targets(root, []) == ()


def test_unknown_page_lists_the_page_names(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    write_page(root, "Bad", "prose\n")
    with pytest.raises(TargetError) as excinfo:
        resolve_targets(root, ["mid", "nope"])
    message = str(excinfo.value)
    assert "nope" in message and "alpha, mid, zulu" in message
    assert "Bad" not in message
    assert isinstance(excinfo.value, ValueError)


def test_unknown_chart_lists_that_pages_chart_ids_in_page_order(
    tmp_path: Path,
) -> None:
    root = _targets_root(tmp_path)
    with pytest.raises(TargetError) as excinfo:
        resolve_targets(root, ["mid:m-one", "alpha:nope"])
    message = str(excinfo.value)
    assert "nope" in message and "zeta, broken, alpha" in message
    assert "m-one" not in message


def test_a_chart_whose_directive_has_problems_is_still_targetable(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    bad_mode = directive_block(
        [(k, "relatve" if k == "mode" else v) for k, v in keys("load")]
    )
    write_page(root, "weekly", page_text(chart("other"), bad_mode))
    assert resolve_targets(root, ["weekly:load"]) == (Target("weekly", "load"),)
    page = run(root, Target("weekly", "load")).pages[0]
    (result,) = page.charts
    assert result.chart == "load" and result.outcome is Outcome.FAILED
    assert codes(result.problems) == [DashboardCode.MODE_VALUE.value]
    (tmp_path / "again").mkdir()
    root2 = _targets_root(tmp_path / "again")
    assert resolve_targets(root2, ["alpha:broken"]) == (Target("alpha", "broken"),)
    broken = run(root2, Target("alpha", "broken")).pages[0].charts
    assert [(c.chart, c.outcome) for c in broken] == [("broken", Outcome.FAILED)]


def test_a_valid_chart_and_a_same_id_chart_with_problems_both_fail(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    bad_mode = directive_block(
        [(k, "relatve" if k == "mode" else v) for k, v in keys("load")]
    )
    write_page(root, "p", page_text(chart("lead"), chart("load"), bad_mode))
    plan = plan_run(request(root, action=Action.REFRESH))
    good = planned(plan.pages, "p", "lead")
    assert good.need is DataNeed.FETCH
    first, second = [c for c in plan.pages[0].charts if c.chart == "load"]
    assert codes(first.problems) == [DashboardCode.DUPLICATE_ID.value]
    assert first.need is None
    assert sorted(codes(second.problems)) == [
        DashboardCode.DUPLICATE_ID.value,
        DashboardCode.MODE_VALUE.value,
    ]
    lines = [each.line for each in second.problems]
    assert lines == sorted(each for each in lines if each is not None)


def test_a_page_with_no_charts_says_so_and_a_repeated_id_is_listed_once(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "bare", page_text("just prose"))
    write_page(root, "twins", page_text(chart("twin"), chart("other"), chart("twin")))
    with pytest.raises(TargetError, match="has no charts"):
        resolve_targets(root, ["bare:x"])
    with pytest.raises(TargetError) as excinfo:
        resolve_targets(root, ["twins:x"])
    assert str(excinfo.value).endswith("the charts are twin, other")


def test_no_pages_at_all_still_raises_with_an_empty_list(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    with pytest.raises(TargetError, match="no dashboard pages"):
        resolve_targets(root, ["anything"])


@pytest.mark.parametrize(
    "raw", ["", ":chart", "mid:", "mid:m-one:m-two", "mid:m-one:", ":", "::"]
)
def test_malformed_targets_are_refused(tmp_path: Path, raw: str) -> None:
    root = _targets_root(tmp_path)
    with pytest.raises(TargetError):
        resolve_targets(root, [raw])


def test_a_chart_target_on_an_unreadable_page_is_accepted(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "bad", "x")
    (root / "dashboards" / "bad.md").write_bytes(b"\xff\xfe")
    assert resolve_targets(root, ["bad:anything"]) == (Target("bad", "anything"),)


def test_targets_under_a_foreign_location_are_left_for_the_run_to_report(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "dashboards").symlink_to(elsewhere)
    assert resolve_targets(root, ["zed:one", "alpha"]) == (
        Target("alpha", None),
        Target("zed", "one"),
    )
    report = run(root, Target("alpha", None))
    assert codes(report.location_problems) == [DashboardCode.LOCATION_FOREIGN.value]


def test_run_refuses_an_unknown_page_target(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    with pytest.raises(TargetError):
        run(root, Target("nope", None))
    with pytest.raises(TargetError):
        run(root, Target("mid", "nope"))


# -- data need -------------------------------------------------------------------


def _write_files(root: Path, names: Sequence[str]) -> None:
    folder = root / "dashboards" / "assets" / "p"
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"{}\n")


def _need_page(root: Path, body: str = "") -> str:
    text = page_text(
        chart("lead"),
        chart("fro", mode="frozen"),
        region_block("fro", body) if body else "",
    )
    write_page(root, "p", text)
    return text


def _need(
    root: Path, action: Action = Action.REFRESH, chart_id: str = "fro"
) -> PlannedChart:
    return planned(plan_run(request(root, action=action)).pages, "p", chart_id)


def test_relative_charts_need_a_fetch_even_if_a_reference_is_in_the_region(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("lead"),
        chart("rel"),
        region_block("rel", "<!-- fitdocs:snapshot assets/p/rel.snapshot-1.json -->"),
    )
    write_page(root, "p", text)
    _write_files(root, ["rel.snapshot-1.json"])
    chosen = _need(root, chart_id="rel")
    assert chosen.need is DataNeed.FETCH and chosen.snapshot is None


def test_frozen_without_a_record_or_a_file_needs_a_fetch(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    _need_page(root)
    _write_files(root, ["other.snapshot-9.json"])
    chosen = _need(root)
    assert chosen.need is DataNeed.FETCH and chosen.snapshot is None


def test_frozen_without_a_record_adopts_the_highest_generation(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    _need_page(root)
    _write_files(
        root,
        ["fro.snapshot-2.json", "fro.snapshot-10.json", "other.snapshot-99.json"],
    )
    chosen = _need(root)
    assert chosen.need is DataNeed.LATEST
    assert chosen.snapshot == "assets/p/fro.snapshot-10.json"


def test_a_recorded_snapshot_wins_over_a_higher_generation(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    _need_page(root, "<!-- fitdocs:snapshot assets/p/fro.snapshot-2.json -->\n\nimg")
    _write_files(root, ["fro.snapshot-2.json", "fro.snapshot-10.json"])
    chosen = _need(root)
    assert chosen.need is DataNeed.RECORDED
    assert chosen.snapshot == "assets/p/fro.snapshot-2.json"


def test_a_recorded_snapshot_of_another_page_is_still_the_charts_record(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    _need_page(
        root, "<!-- fitdocs:snapshot assets/old-page/fro.snapshot-1.json -->\n\nimg"
    )
    _write_files(root, ["fro.snapshot-5.json"])
    chosen = _need(root)
    assert chosen.need is DataNeed.RECORDED
    assert chosen.snapshot == "assets/old-page/fro.snapshot-1.json"
    assert chosen.problems == ()


def test_a_recorded_snapshot_of_another_chart_is_honoured_as_written(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    _need_page(root, "<!-- fitdocs:snapshot assets/p/old-id.snapshot-1.json -->\n\nimg")
    _write_files(root, ["fro.snapshot-3.json"])
    chosen = _need(root)
    assert chosen.need is DataNeed.RECORDED
    assert chosen.snapshot == "assets/p/old-id.snapshot-1.json"
    assert chosen.problems == ()


def test_a_freeze_always_needs_a_fetch_for_a_frozen_chart(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    _need_page(root, "<!-- fitdocs:snapshot assets/p/fro.snapshot-2.json -->\n\nimg")
    _write_files(root, ["fro.snapshot-2.json", "fro.snapshot-10.json"])
    assert _need(root, Action.REFRESH).need is DataNeed.RECORDED
    frozen = _need(root, Action.FREEZE)
    assert frozen.need is DataNeed.FETCH and frozen.snapshot is None
    assert _need(root, Action.CHECK).need is DataNeed.RECORDED


def test_a_failed_chart_has_no_data_need(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    text = page_text(
        chart("lead"),
        chart("fro", mode="frozen"),
        region_block("fro", "half", closed=False),
    )
    write_page(root, "p", text)
    _write_files(root, ["fro.snapshot-2.json"])
    chosen = _need(root)
    assert codes(chosen.problems) == [DashboardCode.REGION_UNCLOSED.value]
    assert chosen.need is None and chosen.snapshot is None


def test_the_report_carries_the_planned_snapshot_path(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    _need_page(root)
    _write_files(root, ["fro.snapshot-4.json"])
    page = run(root).pages[0]
    assert result_of(page, "fro").snapshot == "assets/p/fro.snapshot-4.json"
    assert result_of(page, "lead").snapshot is None


# -- the run is read-only and the report is shaped as designed ------------------------


@pytest.mark.parametrize("action", list(Action))
def test_planning_changes_no_file(tmp_path: Path, action: Action) -> None:
    root = make_data_root(tmp_path)
    _need_page(root, "<!-- fitdocs:snapshot assets/p/fro.snapshot-2.json -->\n\nimg")
    _write_files(root, ["fro.snapshot-2.json"])
    write_page(root, "q", page_text(chart("a"), chart("b")))
    before = snapshot_of(root)
    report = run(root, action=action)
    assert report.action is action
    assert report.index == "not_needed" and report.index_problem is None
    assert report.removed == ()
    assert not any(each.written for each in report.pages)
    assert_untouched(before, snapshot_of(root))


def test_the_same_inputs_give_the_same_report(tmp_path: Path) -> None:
    root = _targets_root(tmp_path)
    assert run(root) == run(root)


def _problem(code: DashboardCode = DashboardCode.PAGE_NAME) -> Problem:
    return dashboard_problem(code, "A.", "B.", page="p")


def _chart_result(
    problems: tuple[Problem, ...] = (), notices: tuple[Problem, ...] = ()
) -> ChartResult:
    return ChartResult(
        "c", 1, "bar", "relative", Outcome.CHECKED, None, problems, notices
    )


def _report(
    *,
    location: tuple[Problem, ...] = (),
    index_problem: Problem | None = None,
    page_problems: tuple[Problem, ...] = (),
    page_notices: tuple[Problem, ...] = (),
    charts: tuple[ChartResult, ...] = (),
) -> RunReport:
    page = PageResult("p", False, page_problems, page_notices, charts)
    return RunReport(Action.CHECK, "ready", index_problem, location, (page,), ())


def test_failed_counts_problems_anywhere_and_never_notices() -> None:
    notice = _problem(DashboardCode.REGION_ORPHANED)
    assert notice.severity is Severity.NOTICE
    assert not _report().failed
    assert not _report(
        page_notices=(notice,), charts=(_chart_result(notices=(notice,)),)
    ).failed
    assert _report(location=(_problem(),)).failed
    assert _report(index_problem=_problem(DashboardCode.INDEX_UNAVAILABLE)).failed
    assert _report(page_problems=(_problem(DashboardCode.PAGE_UNREADABLE),)).failed
    assert _report(charts=(_chart_result(problems=(_problem(),)),)).failed
    assert not RunReport(Action.CHECK, "ready", None, (), (), ()).failed
