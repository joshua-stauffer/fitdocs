"""Engine: pages, targets, associations, data need, charts written, frozen charts.

The planning tests read the report of a ``CHECK`` run over a source that answers
every ``chart`` with the same two rows. The rendering tests give each chart its
own SQL (``select <id>``) and its own rows, run ``REFRESH``, and compare page
bytes, image bytes and ``st_mtime_ns``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest

from fitdocs.dashboards import engine, storage
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
    Source,
    dashboard_problem,
)
from fitdocs.dashboards.snapshot import decode
from fitdocs.dashboards.source import ChartSource, SourceUnavailable
from fitdocs.dashboards.storage import ASSET_MARK, PageFile, Refusal
from fitdocs.render.charts.kit import (
    ChartData,
    ChartRequest,
    Output,
    RenderedChart,
    kind_names,
    registry,
    render_chart,
)
from fitdocs.render.charts.kit.schema import KindSpec, MarkBound, OverBound
from tests.dashboards._helpers import (
    FakeSource,
    FetchCall,
    MustNotOpen,
    assert_untouched,
    category_column,
    category_number_data,
    chart_data,
    directive_block,
    make_data_root,
    number_column,
    page_text,
    region_block,
    snapshot_of,
    unavailable_opener,
    write_page,
)

TODAY = date(2026, 10, 12)
GOLDEN = (
    Path(__file__).resolve().parents[1] / "declaration_golden" / "dashboards.AGENTS.md"
)
OPENER = "<!-- fitdocs:chart"


GOOD_CHANNELS = "\n  x: label\n  y: value"
DEFAULT_SQL = "select 1 as a"
DEFAULT_DATA = category_number_data([("one", 1.0), ("two", 2.0)])


def keys(
    chart_id: str,
    *,
    mode: str = "relative",
    sql: str = DEFAULT_SQL,
    kind: str = "bar",
    channels: str | None = GOOD_CHANNELS,
    extra: Sequence[tuple[str, str]] = (),
) -> list[tuple[str, str]]:
    return [
        ("id", chart_id),
        ("kind", kind),
        ("mode", mode),
        ("title", f"Title of {chart_id}"),
        ("sql", f"|\n  {sql}"),
        *([("channels", channels)] if channels is not None else []),
        *extra,
    ]


def chart(
    chart_id: str,
    *,
    mode: str = "relative",
    sql: str = DEFAULT_SQL,
    kind: str = "bar",
    channels: str | None = GOOD_CHANNELS,
    extra: Sequence[tuple[str, str]] = (),
) -> str:
    return directive_block(
        keys(chart_id, mode=mode, sql=sql, kind=kind, channels=channels, extra=extra)
    )


def own(chart_id: str, **more: object) -> str:
    """A relative chart whose SQL is ``select <id>``, so a source can tell it apart."""
    return chart(chart_id, sql=f"select {chart_id}", **more)  # type: ignore[arg-type]


def fetch_key(chart_id: str) -> str:
    return f"select {chart_id}\n"


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
    source = FakeSource()
    source.queue(f"{DEFAULT_SQL}\n", DEFAULT_DATA)
    return run_dashboards(request(root, *targets, action=action), source.opener())


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
    ordered = [
        *keys("late", channels=None),
        *(extra if unknown_first else extra[::-1]),
    ]
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
    plan = plan_run(request(root, action=action))
    assert [each.name for each in plan.pages] == ["p", "q"]
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


# -- rendering and writing relative charts -------------------------------------

D1 = date(2026, 10, 12)
D2 = date(2026, 10, 13)
DATA_A = category_number_data([("beta", 2.0), ("alpha", 7.0), ("gamma", 4.0)])
DATA_B = category_number_data([("zeta", 11.0), ("eta", 5.0), ("theta", 9.0)])
OLD_TIME_NS = 1_000_000_000 * 10**9
BEGIN_PREFIX = "<!-- fitdocs:begin:chart:"
END_PREFIX = "<!-- fitdocs:end:chart:"


def source_of(answers: dict[str, ChartData | tuple[Problem, ...]]) -> FakeSource:
    """A source answering ``select <id>`` for each chart id in ``answers``."""
    source = FakeSource()
    for chart_id, answer in answers.items():
        # A literal block keeps its final newline only when another key follows.
        source.queue(fetch_key(chart_id), answer)
        source.queue(fetch_key(chart_id).rstrip("\n"), answer)
    return source


def go(
    root: Path,
    source: FakeSource,
    *targets: Target,
    action: Action = Action.REFRESH,
    today: date = D1,
) -> RunReport:
    return run_dashboards(
        RunRequest(action, root, tuple(targets), today), source.opener()
    )


def age(root: Path) -> None:
    """Give every file under ``root`` an old, fixed mtime, so a rewrite shows."""
    for current, _directories, names in os.walk(root):
        for name in names:
            os.utime(Path(current) / name, ns=(OLD_TIME_NS, OLD_TIME_NS))


def page_bytes(root: Path, name: str) -> str:
    return (root / "dashboards" / f"{name}.md").read_bytes().decode("utf-8")


def asset_path(root: Path, page: str, chart_id: str) -> Path:
    return root / "dashboards" / "assets" / page / f"{chart_id}.svg"


def region_lines(text: str, chart_id: str) -> list[str]:
    """The lines strictly between the chart's markers (the region must be closed)."""
    lines = text.split("\n")
    start = lines.index(f"{BEGIN_PREFIX}{chart_id} -->")
    end = lines.index(f"{END_PREFIX}{chart_id} -->", start)
    return lines[start + 1 : end]


def strip_regions(text: str) -> str:
    """The text without any closed region, markers included."""
    kept: list[str] = []
    inside = False
    for each in text.split("\n"):
        if each.startswith(BEGIN_PREFIX):
            inside = True
        if not inside:
            kept.append(each)
        if each.startswith(END_PREFIX):
            inside = False
    return "\n".join(kept)


def remove_region(text: str, chart_id: str) -> str:
    """The text without the chart's closed region, markers included."""
    lines = text.split("\n")
    start = lines.index(f"{BEGIN_PREFIX}{chart_id} -->")
    end = lines.index(f"{END_PREFIX}{chart_id} -->", start)
    return "\n".join(lines[:start] + lines[end + 1 :])


def test_a_second_chart_gets_a_region_and_an_image_and_a_rerun_writes_nothing(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    original = page_text(
        "# Weekly",
        own("one"),
        "Prose between the charts.",
        own("two", extra=[("window", "last 12 weeks")]),
        "Closing prose.",
    )
    write_page(root, "p", original)
    assert (
        BEGIN_PREFIX not in original and not (root / "dashboards" / "assets").exists()
    )
    first = go(root, source_of({"one": DATA_B, "two": DATA_A}))
    text = page_bytes(root, "p")
    assert strip_regions(text) == strip_regions(original) == original
    assert text.count(BEGIN_PREFIX) == 2
    assert region_lines(text, "two") == [
        "![Title of two](assets/p/two.svg)",
        "",
        "*last 12 weeks*",
        "",
    ]
    assert region_lines(text, "one")[0] == "![Title of one](assets/p/one.svg)"
    assert text.index(f"{BEGIN_PREFIX}one -->") < text.index("Prose between")
    assert text.index("Prose between") < text.index(f"{BEGIN_PREFIX}two -->")
    one_svg = asset_path(root, "p", "one").read_bytes().decode("utf-8")
    two_svg = asset_path(root, "p", "two").read_bytes().decode("utf-8")
    assert one_svg.startswith(ASSET_MARK + "\n<svg")
    assert two_svg.startswith(ASSET_MARK + "\n<svg")
    assert "alpha" in two_svg and "alpha" not in one_svg
    assert "zeta" in one_svg and "zeta" not in two_svg
    page = first.pages[0]
    assert page.written
    assert [(each.chart, each.outcome) for each in page.charts] == [
        ("one", Outcome.RENDERED),
        ("two", Outcome.RENDERED),
    ]
    assert not first.failed and first.index == "ready"

    age(root)
    before = snapshot_of(root)
    again_source = source_of({"one": DATA_B, "two": DATA_A})
    again = go(root, again_source)
    assert_untouched(before, snapshot_of(root))
    assert again.pages[0].written is False
    assert [each.outcome for each in again.pages[0].charts] == [Outcome.UNCHANGED] * 2
    assert not again.failed
    assert len(again_source.calls) == 2, "the rerun did reach the source"


def test_the_source_is_asked_in_page_order_with_the_run_date_and_directive_line(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    late = page_text(own("zeta"), own("mid"), own("alpha"))
    write_page(root, "b", late)
    first = page_text("intro", own("only"))
    write_page(root, "a", first)
    source = source_of({"zeta": DATA_A, "mid": DATA_B, "alpha": DATA_A, "only": DATA_B})
    go(root, source, today=D2)
    assert source.calls == [
        FetchCall(fetch_key("only"), D2, "a", "only", line_of(first, OPENER, 0)),
        FetchCall(fetch_key("zeta"), D2, "b", "zeta", line_of(late, OPENER, 0)),
        FetchCall(fetch_key("mid"), D2, "b", "mid", line_of(late, OPENER, 1)),
        FetchCall(fetch_key("alpha"), D2, "b", "alpha", line_of(late, OPENER, 2)),
    ]
    assert source.opened == 1 and source.closed == 1


def test_a_changed_result_rewrites_the_image_and_leaves_an_unchanged_page_alone(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("lead"), own("flow")))
    go(root, source_of({"lead": DATA_B, "flow": DATA_A}))
    age(root)
    page_before = snapshot_of(root / "dashboards")["p.md"]
    image_before = asset_path(root, "p", "flow").read_bytes()
    other_before = snapshot_of(root / "dashboards")["assets/p/lead.svg"]
    changed = category_number_data([("beta", 20.0), ("alpha", 70.0), ("gamma", 40.0)])
    report = go(root, source_of({"lead": DATA_B, "flow": changed}))
    after = snapshot_of(root / "dashboards")
    assert after["p.md"] == page_before, "the page bytes and mtime are untouched"
    assert after["assets/p/lead.svg"] == other_before
    assert asset_path(root, "p", "flow").read_bytes() != image_before
    assert after["assets/p/flow.svg"][1] != OLD_TIME_NS
    page = report.pages[0]
    assert page.written is False
    assert [(c.chart, c.outcome) for c in page.charts] == [
        ("lead", Outcome.UNCHANGED),
        ("flow", Outcome.RENDERED),
    ]


def test_the_run_date_is_in_no_byte_a_relative_chart_writes(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(
        root, "p", page_text(own("lead"), own("pace", extra=[("window", "84 days")]))
    )
    answers: dict[str, ChartData | tuple[Problem, ...]] = {
        "lead": DATA_B,
        "pace": DATA_A,
    }
    first_source = source_of(answers)
    go(root, first_source, today=D1)
    written = snapshot_of(root)
    for name, (data, _mtime) in written.items():
        text = data.decode("utf-8")
        assert D1.isoformat() not in text and D2.isoformat() not in text, name
        assert D1.strftime("%d") + " Oct" not in text, name
    age(root)
    before = snapshot_of(root)
    second_source = source_of(answers)
    report = go(root, second_source, today=D2)
    assert_untouched(before, snapshot_of(root))
    assert [each.today for each in first_source.calls] == [D1, D1]
    assert [each.today for each in second_source.calls] == [D2, D2]
    assert timedelta(days=1) == D2 - D1
    assert [each.outcome for each in report.pages[0].charts] == [Outcome.UNCHANGED] * 2


OLD_BODY = "![Old](assets/p/kept.svg)\n\n*the old caption*\n"


def _sql_failed(chart_id: str) -> tuple[Problem, ...]:
    return (
        dashboard_problem(
            DashboardCode.SQL_FAILED,
            f"The statement for {chart_id} failed: boom.",
            "Fix the SQL.",
            page="p",
            chart=chart_id,
            line=1,
        ),
    )


def test_a_failing_chart_costs_only_that_chart(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    kept_region = region_block("kept", OLD_BODY)
    contents_region = region_block("contents", "half", closed=False)
    text = page_text(
        own("ok"),
        own("kept", channels="\n  x: label\n  y: nope"),
        kept_region,
        own("fresh"),
        own("blank"),
        region_block("blank"),
        own("contents"),
        contents_region,
        own("tail"),
    )
    write_page(root, "p", text)
    write_page(root, "q", page_text(own("qok")))
    source = source_of(
        {
            "ok": DATA_A,
            "kept": DATA_B,
            "fresh": _sql_failed("fresh"),
            "blank": _sql_failed("blank"),
            "tail": DATA_B,
            "qok": DATA_A,
        }
    )
    report = go(root, source)
    page = page_of(report, "p")
    outcome = {each.chart: each for each in page.charts}
    assert {name: each.outcome for name, each in outcome.items()} == {
        "ok": Outcome.RENDERED,
        "kept": Outcome.FAILED,
        "fresh": Outcome.FAILED,
        "blank": Outcome.FAILED,
        "contents": Outcome.FAILED,
        "tail": Outcome.RENDERED,
    }
    assert codes(outcome["kept"].problems) == ["unknown_column"]
    assert outcome["kept"].problems[0].source is Source.CHART
    assert codes(outcome["fresh"].problems) == [DashboardCode.SQL_FAILED.value]
    assert codes(outcome["blank"].problems) == [DashboardCode.SQL_FAILED.value]
    assert codes(outcome["contents"].problems) == [DashboardCode.REGION_CONTENTS.value]
    assert page_of(report, "q").charts[0].outcome is Outcome.RENDERED
    assert [each.chart for each in source.calls] == [
        "ok",
        "kept",
        "fresh",
        "blank",
        "tail",
        "qok",
    ], "a chart with a planning problem is never queried"

    now = page_bytes(root, "p")
    assert kept_region in now, "a chart rendered before keeps its region exactly"
    assert contents_region in now, "a chart with a region problem is not touched"
    written_ids = ("ok", "fresh", "blank", "tail")
    outside = now
    for chart_id in written_ids:
        outside = remove_region(outside, chart_id)
    assert outside == remove_region(text, "blank"), "only those regions changed"
    for noted in ("fresh", "blank"):
        body = region_lines(now, noted)
        assert body[0].startswith("*Not rendered: The statement for ")
        assert "boom" in body[0] and body[0].endswith("*")
        assert body[1:] == [""]
        assert not asset_path(root, "p", noted).exists()
    assert not asset_path(root, "p", "kept").exists()
    for healthy in ("ok", "tail"):
        assert region_lines(now, healthy)[0] == (
            f"![Title of {healthy}](assets/p/{healthy}.svg)"
        )
        assert (
            asset_path(root, "p", healthy).read_bytes().startswith(ASSET_MARK.encode())
        )
    assert region_lines(page_bytes(root, "q"), "qok")[0].startswith("![Title of qok]")


def test_a_note_is_kept_while_the_chart_fails_and_replaced_once_it_renders(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("lead"), own("fresh")))
    answers: dict[str, ChartData | tuple[Problem, ...]] = {
        "lead": DATA_A,
        "fresh": _sql_failed("fresh"),
    }
    go(root, source_of(answers))
    noted = page_bytes(root, "p")
    assert region_lines(noted, "fresh")[0].startswith("*Not rendered:")

    age(root)
    before = snapshot_of(root)
    still = go(root, source_of(answers))
    assert_untouched(before, snapshot_of(root))
    assert still.pages[0].written is False
    assert [each.outcome for each in still.pages[0].charts] == [
        Outcome.UNCHANGED,
        Outcome.FAILED,
    ]

    lead_region = region_lines(noted, "lead")
    unavailable = run_dashboards(
        request(root, action=Action.REFRESH), unavailable_opener(UNAVAILABLE)
    )
    different = page_bytes(root, "p")
    assert region_lines(different, "fresh")[0].startswith(
        "*Not rendered: The chart was not queried: the index is not built."
    ), "a note is rewritten when the first problem changes"
    assert region_lines(different, "fresh") != region_lines(noted, "fresh")
    assert region_lines(different, "lead") == lead_region
    assert [each.outcome for each in unavailable.pages[0].charts] == [
        Outcome.FAILED
    ] * 2

    answers["fresh"] = DATA_B
    healed = go(root, source_of(answers))
    now = page_bytes(root, "p")
    assert region_lines(now, "fresh")[0] == "![Title of fresh](assets/p/fresh.svg)"
    assert "Not rendered" not in now
    assert asset_path(root, "p", "fresh").exists()
    assert [each.outcome for each in healed.pages[0].charts] == [
        Outcome.UNCHANGED,
        Outcome.RENDERED,
    ]


def test_show_rows_adds_the_kit_table_to_that_chart_only(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(
        root,
        "p",
        page_text(own("plain"), own("rows", extra=[("show_rows", "true")])),
    )
    report = go(root, source_of({"plain": DATA_B, "rows": DATA_A}))
    assert not report.failed
    text = page_bytes(root, "p")
    plain = region_lines(text, "plain")
    rows = region_lines(text, "rows")
    assert not any(each.startswith("|") for each in plain)
    table = [each for each in rows if each.startswith("|")]
    assert table == [
        "| label | value |",
        "| --- | ---: |",
        "| beta | 2 |",
        "| alpha | 7 |",
        "| gamma | 4 |",
    ]
    assert rows[0] == "![Title of rows](assets/p/rows.svg)"


def test_a_table_over_its_bound_fails_the_chart_with_the_show_rows_option(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    wide = category_number_data([(f"c{n:03d}", float(n)) for n in range(101)])
    write_page(
        root,
        "p",
        page_text(
            own("plain"),
            own("rows", extra=[("show_rows", "true")]),
        ),
    )
    report = go(root, source_of({"plain": wide, "rows": wide}))
    plain, rows = report.pages[0].charts
    assert plain.outcome is Outcome.RENDERED, "the bar chart alone takes 101 rows"
    assert rows.outcome is Outcome.FAILED
    assert codes(rows.problems) == ["over_bound"]
    (problem,) = rows.problems
    assert problem.source is Source.CHART
    assert problem.option == "show_rows"
    assert problem.rows == 101
    assert problem.chart == "rows" and problem.page == "p"
    assert not asset_path(root, "p", "rows").exists()
    assert region_lines(page_bytes(root, "p"), "rows")[0].startswith("*Not rendered:")


def test_an_unregistered_kind_reports_the_registered_kinds(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("good"), own("odd", kind="nosuchkind")))
    report = go(root, source_of({"good": DATA_A, "odd": DATA_B}))
    good, odd = report.pages[0].charts
    assert good.outcome is Outcome.RENDERED
    assert codes(odd.problems) == ["unknown_kind"]
    (problem,) = odd.problems
    assert problem.source is Source.CHART
    assert problem.accepted == tuple(kind_names())
    assert problem.accepted, "the registry lists its kinds"
    assert "nosuchkind" in problem.message


def test_kit_problems_keep_the_kits_order_after_earlier_charts_problems(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(
        root,
        "p",
        page_text(
            own("early"),
            own(
                "late",
                channels="\n  x: nope\n  y: value\n  z: label",
                extra=[("options", "\n  zz: 1")],
            ),
        ),
    )
    report = go(root, source_of({"early": _sql_failed("early"), "late": DATA_A}))
    early, late = report.pages[0].charts
    kit_order = [each.code for each in late.problems]
    assert kit_order == ["unknown_column", "unknown_channel", "unknown_option"]
    assert kit_order != sorted(kit_order), "the kit's order is not code order"
    assert [each.channel for each in late.problems] == ["x", "z", None]
    assert [each.option for each in late.problems] == [None, None, "zz"]
    flat = [each.code for c in report.pages[0].charts for each in c.problems]
    assert flat == ["sql_failed", *kit_order]
    assert early.line < late.line
    for each in late.problems:
        assert (each.page, each.chart, each.line) == ("p", "late", late.line)
        assert each.source is Source.CHART
    note = region_lines(page_bytes(root, "p"), "late")[0]
    assert "bound to column" in note, "the note states the kit's first problem"
    assert "not declared" not in note


# -- the source: opened once, closed when a chart raises, unavailable ---------


def test_the_source_opens_once_for_charts_on_two_pages(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(own("a1"), own("a2")))
    write_page(root, "b", page_text(own("b1"), own("b2")))
    source = source_of({"a1": DATA_A, "a2": DATA_B, "b1": DATA_A, "b2": DATA_B})
    report = go(root, source)
    assert (source.opened, source.closed) == (1, 1)
    assert [each.chart for each in source.calls] == ["a1", "a2", "b1", "b2"]
    assert report.index == "ready" and report.index_problem is None


def test_the_source_is_not_opened_for_a_page_whose_only_chart_has_a_planning_problem(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "bad", page_text(chart("typo", mode="relatve")))
    write_page(root, "empty", page_text("just prose"))
    guard = MustNotOpen()
    report = run_dashboards(request(root, action=Action.REFRESH), guard)
    assert guard.attempts == 0
    assert report.index == "not_needed" and report.index_problem is None
    assert codes(page_of(report, "bad").charts[0].problems) == ["mode_value"]
    write_page(root, "good", page_text(own("fine")))
    source = source_of({"fine": DATA_A})
    reached = go(root, source)
    assert (source.opened, source.closed) == (1, 1)
    assert [each.chart for each in source.calls] == ["fine"]
    assert reached.index == "ready"


@dataclass
class ExplodingSource:
    closed: int = 0

    def fetch(
        self, sql: str, *, today: date, page: str, chart: str, line: int
    ) -> object:
        raise RuntimeError("fitdocs defect")

    def close(self) -> None:
        self.closed += 1


def test_a_defect_in_the_source_propagates_and_the_source_is_still_closed(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("lead"), own("next")))
    age(root)
    before = snapshot_of(root)
    exploding = ExplodingSource()

    def opener() -> ChartSource | SourceUnavailable:
        return exploding  # type: ignore[return-value]

    with pytest.raises(RuntimeError, match="fitdocs defect"):
        run_dashboards(request(root, action=Action.REFRESH), opener)
    assert exploding.closed == 1
    assert_untouched(before, snapshot_of(root))


UNAVAILABLE = SourceUnavailable(
    "not_built", "the index is not built.", "Run `fitdocs index` to build it."
)


def test_an_unavailable_index_fails_each_relative_chart_and_the_page_is_still_handled(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    done = region_block("done", OLD_BODY.replace("kept", "done"))
    text = page_text(
        own("fresh"),
        own("done"),
        done,
        chart("typo", mode="relatve"),
        own("later"),
    )
    write_page(root, "p", text)
    write_page(root, "q", page_text(own("qfresh")))
    report = run_dashboards(
        request(root, action=Action.REFRESH), unavailable_opener(UNAVAILABLE)
    )
    assert report.index == "not_built"
    assert report.index_problem is not None
    assert report.index_problem.code == "index_unavailable"
    assert (report.index_problem.page, report.index_problem.chart) == (None, None)
    assert report.failed
    page = page_of(report, "p")
    by_id = {each.chart: each for each in page.charts}
    for name in ("fresh", "done", "later"):
        (problem,) = by_id[name].problems
        assert (
            problem.code == "index_unavailable" and problem.source is Source.DASHBOARD
        )
        assert "the index is not built." in problem.message
        assert problem.fix == UNAVAILABLE.fix
        assert (problem.page, problem.chart) == ("p", name)
        assert problem.line == by_id[name].line
        assert by_id[name].outcome is Outcome.FAILED
    assert codes(by_id["typo"].problems) == ["mode_value"], "a planning problem stays"
    assert codes(page_of(report, "q").charts[0].problems) == ["index_unavailable"]
    now = page_bytes(root, "p")
    assert done in now, "a chart rendered before keeps its region"
    for noted in ("fresh", "later"):
        assert region_lines(now, noted)[0].startswith(
            "*Not rendered: The chart was not"
        )
    assert f"{BEGIN_PREFIX}typo" not in now
    assert not (root / "dashboards" / "assets").exists()


def test_a_run_over_charts_that_need_no_query_reports_the_index_as_not_needed(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(chart("typo", mode="relatve"), "prose"))
    report = run_dashboards(
        request(root, action=Action.REFRESH), unavailable_opener(UNAVAILABLE)
    )
    assert report.index == "not_needed" and report.index_problem is None


# -- check, writes that go wrong, foreign images -------------------------------


def _check_root(tmp_path: Path, name: str) -> Path:
    root = make_data_root(tmp_path, name)
    stale = region_block("good", "![Stale](assets/p/good.svg)\n\n*stale*\n")
    write_page(
        root,
        "p",
        page_text(
            own("good"),
            stale,
            own("bad", channels="\n  x: nope\n  y: value"),
            own("fresh"),
        ),
    )
    return root


def test_check_renders_in_memory_and_creates_or_changes_no_file(tmp_path: Path) -> None:
    answers: dict[str, ChartData | tuple[Problem, ...]] = {
        "good": DATA_A,
        "bad": DATA_B,
        "fresh": DATA_B,
    }
    refreshed = _check_root(tmp_path, "refresh")
    go(refreshed, source_of(answers))
    assert asset_path(refreshed, "p", "good").exists(), "a refresh does write here"
    assert asset_path(refreshed, "p", "fresh").exists()

    root = _check_root(tmp_path, "check")
    age(root)
    before = snapshot_of(root)
    report = go(root, source_of(answers), action=Action.CHECK)
    assert_untouched(before, snapshot_of(root))
    assert not (root / "dashboards" / "assets").exists()
    page = report.pages[0]
    assert page.written is False
    assert [(each.chart, each.outcome) for each in page.charts] == [
        ("good", Outcome.CHECKED),
        ("bad", Outcome.FAILED),
        ("fresh", Outcome.CHECKED),
    ]
    assert codes(page.charts[1].problems) == ["unknown_column"]
    assert report.failed


def _two_pages(tmp_path: Path) -> Path:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(own("a1"), own("a2")))
    write_page(root, "b", page_text(own("b1")))
    return root


A_B_ANSWERS: dict[str, ChartData | tuple[Problem, ...]] = {
    "a1": DATA_A,
    "a2": DATA_B,
    "b1": DATA_A,
}


def test_a_page_changed_between_read_and_replace_fails_only_its_edited_charts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(own("a1")))
    write_page(root, "b", page_text(own("b1")))
    go(root, source_of({"a1": DATA_A, "b1": DATA_A}))
    write_page(root, "a", page_bytes(root, "a") + own("a2"))
    write_page(root, "b", "changed\n" + page_bytes(root, "b") + own("b2"))
    real = storage.replace_page
    intruder = b"someone else edited this page\n"

    def racing(page: PageFile, text: str) -> str:
        if page.name == "a":
            page.path.write_bytes(intruder)
        return real(page, text)

    monkeypatch.setattr(engine, "replace_page", racing)
    report = go(
        root, source_of({"a1": DATA_A, "a2": DATA_B, "b1": DATA_A, "b2": DATA_B})
    )
    assert (root / "dashboards" / "a.md").read_bytes() == intruder
    a = page_of(report, "a")
    assert a.written is False
    first, second = a.charts
    assert (first.chart, first.outcome, first.problems) == (
        "a1",
        Outcome.UNCHANGED,
        (),
    ), "a chart with no edit is not blamed"
    assert second.outcome is Outcome.FAILED
    assert codes(second.problems) == ["page_changed"]
    assert (second.problems[0].page, second.problems[0].chart) == ("a", "a2")
    assert second.problems[0].line == second.line
    b = page_of(report, "b")
    assert b.written is True
    assert [each.outcome for each in b.charts] == [Outcome.UNCHANGED, Outcome.RENDERED]


@pytest.mark.parametrize("vanished", [False, True])
def test_a_page_that_cannot_be_replaced_is_write_failed_not_page_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vanished: bool
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(own("a1")))
    write_page(root, "b", page_text(own("b1")))
    go(root, source_of({"a1": DATA_A, "b1": DATA_A}))
    write_page(root, "a", page_bytes(root, "a") + own("a2"))
    write_page(root, "b", page_bytes(root, "b") + own("b2"))
    real = storage.replace_page

    def failing(page: PageFile, text: str) -> str:
        if page.name == "a":
            if vanished:
                page.path.unlink()
            else:
                raise OSError("disk full")
        return real(page, text)

    monkeypatch.setattr(engine, "replace_page", failing)
    report = go(root, source_of({**A_B_ANSWERS, "b2": DATA_B}))
    a = page_of(report, "a")
    assert a.written is False
    first, second = a.charts
    assert (first.chart, first.outcome, first.problems) == (
        "a1",
        Outcome.UNCHANGED,
        (),
    ), "a chart with no edit is not blamed"
    assert codes(second.problems) == ["write_failed"]
    assert second.outcome is Outcome.FAILED
    (problem,) = second.problems
    assert problem.message.endswith(".")
    assert (problem.page, problem.chart, problem.line) == ("a", "a2", second.line)
    assert (root / "dashboards" / "a.md").exists() is not vanished
    assert page_of(report, "b").written is True
    assert report.failed


@pytest.mark.parametrize("action", list(Action))
def test_the_report_names_the_requested_action(tmp_path: Path, action: Action) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(chart("typo", mode="relatve")))
    age(root)
    before = snapshot_of(root)
    report = run_dashboards(request(root, action=action), MustNotOpen())
    assert report.action is action
    assert_untouched(before, snapshot_of(root))


def test_each_kit_request_is_named_page_colon_chart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refs: list[tuple[str, str]] = []
    real = render_chart

    def spy(chart_request: ChartRequest, data: ChartData) -> RenderedChart:
        refs.append((chart_request.ref, chart_request.kind))
        return real(chart_request, data)

    monkeypatch.setattr(engine, "render_chart", spy)
    root = make_data_root(tmp_path)
    write_page(
        root, "p", page_text(own("lead"), own("rows", extra=[("show_rows", "true")]))
    )
    go(root, source_of({"lead": DATA_A, "rows": DATA_B}))
    assert refs == [("p:lead", "bar"), ("p:rows", "bar"), ("p:rows", "table")]


@pytest.mark.parametrize(
    "error", [OSError("no space left"), FileNotFoundError("dashboards/ is gone")]
)
def test_an_image_that_cannot_be_written_fails_that_chart_and_drops_its_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("ok1"), own("broken"), own("ok2")))
    real = storage.write_asset

    def failing(data_root: Path, page: str, chart_id: str, svg: str) -> str:
        if chart_id == "broken":
            raise error
        return real(data_root, page, chart_id, svg)

    monkeypatch.setattr(engine, "write_asset", failing)
    report = go(root, source_of({"ok1": DATA_A, "broken": DATA_B, "ok2": DATA_B}))
    ok1, broken, ok2 = report.pages[0].charts
    assert codes(broken.problems) == ["write_failed"]
    assert broken.outcome is Outcome.FAILED
    assert (broken.problems[0].page, broken.problems[0].chart) == ("p", "broken")
    assert broken.problems[0].line == broken.line
    assert (ok1.outcome, ok2.outcome) == (Outcome.RENDERED, Outcome.RENDERED)
    text = page_bytes(root, "p")
    assert f"{BEGIN_PREFIX}broken" not in text
    assert f"{BEGIN_PREFIX}ok1 -->" in text and f"{BEGIN_PREFIX}ok2 -->" in text
    assert report.pages[0].written is True


def test_a_foreign_image_fails_its_chart_and_edits_no_region(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    held = region_block("held")
    write_page(
        root, "p", page_text(own("ok1"), own("mine"), own("held"), held, own("ok2"))
    )
    folder = root / "dashboards" / "assets" / "p"
    folder.mkdir(parents=True)
    (folder / "mine.svg").write_bytes(b"not ours\n")
    (folder / "held.svg").write_bytes(b"also not ours\n")
    report = go(
        root,
        source_of({"ok1": DATA_A, "mine": DATA_B, "held": DATA_A, "ok2": DATA_B}),
    )
    ok1, mine, held_result, ok2 = report.pages[0].charts
    for foreign in (mine, held_result):
        assert codes(foreign.problems) == ["asset_foreign"]
        assert foreign.outcome is Outcome.FAILED
        assert f"dashboards/assets/p/{foreign.chart}.svg" in foreign.problems[0].message
    assert (ok1.outcome, ok2.outcome) == (Outcome.RENDERED, Outcome.RENDERED)
    assert (folder / "mine.svg").read_bytes() == b"not ours\n"
    assert (folder / "held.svg").read_bytes() == b"also not ours\n"
    text = page_bytes(root, "p")
    assert f"{BEGIN_PREFIX}mine" not in text
    assert region_lines(text, "held") == [], "an empty region is not turned into a note"
    assert report.pages[0].written is True


def test_an_asset_directory_that_is_a_link_is_foreign_and_nothing_goes_through_it(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("lead"), own("linked")))
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "dashboards" / "assets").mkdir()
    (root / "dashboards" / "assets" / "p").symlink_to(outside)
    report = go(root, source_of({"lead": DATA_A, "linked": DATA_B}))
    assert report.location_problems == ()
    assert [codes(each.problems) for each in report.pages[0].charts] == [
        ["asset_foreign"],
        ["asset_foreign"],
    ]
    assert list(outside.iterdir()) == []
    assert BEGIN_PREFIX not in page_bytes(root, "p")


# -- endings, registry kinds, defects --------------------------------------------------


def test_inserted_and_replaced_lines_take_the_directive_closers_ending(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    crlf = "\r\n"
    text = (
        directive_block(keys("fresh", sql="select fresh"), ending=crlf)
        + directive_block(keys("stale", sql="select stale"), ending=crlf)
        + region_block("stale", "old", ending="\n")
    )
    write_page(root, "p", text)
    assert "old\n" in text and "old\r\n" not in text
    go(root, source_of({"fresh": DATA_A, "stale": DATA_B}))
    lines = page_bytes(root, "p").splitlines(keepends=True)

    def region(chart_id: str) -> list[str]:
        start = next(
            n
            for n, each in enumerate(lines)
            if each.startswith(f"{BEGIN_PREFIX}{chart_id} ")
        )
        end = next(
            n
            for n, each in enumerate(lines)
            if each.startswith(f"{END_PREFIX}{chart_id} ")
        )
        return lines[start : end + 1]

    inserted = region("fresh")
    assert len(inserted) >= 4 and all(each.endswith("\r\n") for each in inserted)
    replaced = region("stale")
    assert replaced[0].endswith("\n") and not replaced[0].endswith("\r\n")
    assert replaced[-1].endswith("\n") and not replaced[-1].endswith("\r\n")
    assert len(replaced) > 2
    assert all(each.endswith("\r\n") for each in replaced[1:-1])
    assert "old" not in "".join(replaced)


def test_a_kind_registered_later_is_drawn_without_any_change_to_the_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = KindSpec(
        name="stubkind",
        description="A kind registered after the dashboards feature landed.",
        output=Output.MARKDOWN,
        channels=(),
        options=(),
        bound=MarkBound(10, "rows", OverBound.REFUSE, "at most ten rows"),
        max_series=None,
        draw=lambda _bound: "STUB LINE ONE\nSTUB LINE TWO",
    )
    monkeypatch.setattr(registry, "KINDS", (*registry.KINDS, stub))
    root = make_data_root(tmp_path)
    write_page(
        root, "p", page_text(own("lead"), own("odd", kind="stubkind", channels=None))
    )
    report = go(root, source_of({"lead": DATA_A, "odd": DATA_B}))
    assert not report.failed
    assert region_lines(page_bytes(root, "p"), "odd") == [
        "STUB LINE ONE",
        "STUB LINE TWO",
        "",
    ]
    assert not asset_path(root, "p", "odd").exists(), "markdown output has no image"
    assert asset_path(root, "p", "lead").exists()


def test_a_kit_line_that_would_open_a_fitdocs_comment_is_a_defect_not_a_chart_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile = RenderedChart("bar", Output.MARKDOWN, "<!-- fitdocs:begin:chart:x -->")
    monkeypatch.setattr(engine, "render_chart", lambda _request, _data: hostile)
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("lead"), own("next")))
    age(root)
    before = snapshot_of(root)
    source = source_of({"lead": DATA_A, "next": DATA_B})
    with pytest.raises(ValueError, match="comment marker"):
        go(root, source)
    assert source.closed == 1
    assert_untouched(before, snapshot_of(root))


def test_a_chart_target_fetches_and_writes_only_that_chart(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("one"), own("two")))
    source = source_of({"two": DATA_B})
    report = go(root, source, Target("p", "two"))
    assert [each.chart for each in source.calls] == ["two"]
    text = page_bytes(root, "p")
    assert f"{BEGIN_PREFIX}two -->" in text and f"{BEGIN_PREFIX}one" not in text
    assert not asset_path(root, "p", "one").exists()
    assert [each.chart for each in report.pages[0].charts] == ["two"]


def test_a_chart_and_its_rows_table_both_refused_report_the_chart_first(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    wide = category_number_data([(f"c{n:03d}", float(n)) for n in range(101)])
    write_page(
        root,
        "p",
        page_text(
            own("lead"),
            own(
                "both",
                channels="\n  x: nope\n  y: value",
                extra=[("show_rows", "true")],
            ),
        ),
    )
    report = go(root, source_of({"lead": DATA_A, "both": wide}))
    both = report.pages[0].charts[1]
    assert [(each.code, each.option) for each in both.problems] == [
        ("unknown_column", None),
        ("over_bound", "show_rows"),
    ]


def test_an_opener_that_raises_ends_the_run_before_any_write(tmp_path: Path) -> None:
    root = _two_pages(tmp_path)
    age(root)
    before = snapshot_of(root)

    def broken() -> ChartSource | SourceUnavailable:
        raise RuntimeError("index location is misconfigured")

    with pytest.raises(RuntimeError, match="misconfigured"):
        run_dashboards(request(root, action=Action.REFRESH), broken)
    assert_untouched(before, snapshot_of(root))
    assert not (root / "dashboards" / "assets").exists()


# -- frozen charts: first freeze, stored snapshots, re-freeze, cleanup -----------

DATA_C = category_number_data([("kappa", 3.0), ("iota", 8.0), ("lambda", 6.0)])


def fro(chart_id: str, **more: object) -> str:
    """A frozen chart whose SQL is ``select <id>``."""
    return own(chart_id, mode="frozen", **more)


def digest(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def snap_ref(page: str, chart_id: str, generation: int) -> str:
    return (
        f"<!-- fitdocs:snapshot assets/{page}/{chart_id}.snapshot-{generation}.json -->"
    )


def snap_path(root: Path, page: str, chart_id: str, generation: int) -> Path:
    return (
        root / "dashboards" / "assets" / page / f"{chart_id}.snapshot-{generation}.json"
    )


def snap_files(root: Path, page: str) -> list[str]:
    folder = root / "dashboards" / "assets" / page
    if not folder.is_dir():
        return []
    return sorted(each for each in os.listdir(folder) if ".snapshot-" in each)


def go_offline(
    root: Path,
    *targets: Target,
    action: Action = Action.REFRESH,
    today: date = D2,
) -> RunReport:
    """A run whose source must never be opened."""
    opener = MustNotOpen()
    report = run_dashboards(RunRequest(action, root, tuple(targets), today), opener)
    assert opener.attempts == 0, "the source was opened"
    return report


def frozen_root(tmp_path: Path, name: str = "data") -> Path:
    """Page ``p``: frozen ``lead`` then frozen ``fro``; both taken at ``D1``."""
    root = make_data_root(tmp_path, name)
    write_page(root, "p", page_text("# Weekly", fro("lead"), "between", fro("fro")))
    first = go(root, source_of({"lead": DATA_B, "fro": DATA_A}), today=D1)
    assert not first.failed
    return root


def test_a_first_freeze_stores_generation_one_and_the_region_records_it(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text("# Weekly", fro("lead"), "between", fro("fro")))
    assert not (root / "dashboards" / "assets").exists()
    source = source_of({"lead": DATA_B, "fro": DATA_A})
    report = go(root, source, today=D1)
    assert not report.failed and report.index == "ready"
    assert snap_files(root, "p") == ["fro.snapshot-1.json", "lead.snapshot-1.json"]
    stored = decode(snap_path(root, "p", "fro", 1).read_bytes())
    assert (stored.page, stored.chart, stored.generation) == ("p", "fro", 1)
    assert stored.today == D1
    assert stored.sql == "select fro\n"
    assert stored.sql_sha256 == digest("select fro")
    assert stored.data == DATA_A
    other = decode(snap_path(root, "p", "lead", 1).read_bytes())
    assert other.data == DATA_B and other.sql_sha256 == digest("select lead")
    text = page_bytes(root, "p")
    assert region_lines(text, "fro") == [
        snap_ref("p", "fro", 1),
        "",
        "![Title of fro](assets/p/fro.svg)",
        "",
        "*Snapshot 2026-10-12*",
        "",
    ]
    assert region_lines(text, "lead")[0] == snap_ref("p", "lead", 1)
    page = report.pages[0]
    assert [(c.chart, c.outcome) for c in page.charts] == [
        ("lead", Outcome.RENDERED),
        ("fro", Outcome.RENDERED),
    ]
    assert page.charts[1].snapshot == "assets/p/fro.snapshot-1.json"
    assert "alpha" in asset_path(root, "p", "fro").read_text()

    age(root)
    before = snapshot_of(root)
    again = go_offline(root, today=D2)
    assert_untouched(before, snapshot_of(root))
    assert [c.outcome for c in again.pages[0].charts] == [Outcome.UNCHANGED] * 2
    assert not again.failed and again.index == "not_needed"
    assert [c.snapshot for c in again.pages[0].charts] == [
        "assets/p/lead.snapshot-1.json",
        "assets/p/fro.snapshot-1.json",
    ]


def test_a_frozen_chart_redraws_from_its_rows_when_its_presentation_changes(
    tmp_path: Path,
) -> None:
    root = frozen_root(tmp_path)
    age(root)
    before = snapshot_of(root / "dashboards")
    old_image = asset_path(root, "p", "fro").read_bytes()
    text = page_bytes(root, "p")
    old_directive = fro("fro")
    assert old_directive in text
    new_directive = fro(
        "fro",
        kind="hbar",
        channels="\n  x: value\n  y: label",
        extra=[("window", "28 days"), ("show_rows", "true")],
    )
    retitled = text.replace(old_directive, new_directive)
    assert retitled.count("title: Title of fro") == 1
    write_page(root, "p", retitled.replace("title: Title of fro", "title: Renamed"))
    age_page = root / "dashboards" / "p.md"
    os.utime(age_page, ns=(OLD_TIME_NS, OLD_TIME_NS))
    report = go_offline(root)
    redrawn = page_bytes(root, "p")
    lines = region_lines(redrawn, "fro")
    assert lines[0] == snap_ref("p", "fro", 1)
    assert lines[4] == "*Snapshot 2026-10-12 · 28 days*"
    assert "![Renamed](assets/p/fro.svg)" in lines
    assert any(each.startswith("| ") for each in lines), "the rows table was added"
    assert asset_path(root, "p", "fro").read_bytes() != old_image
    after = snapshot_of(root / "dashboards")
    for name in ("assets/p/fro.snapshot-1.json", "assets/p/lead.snapshot-1.json"):
        assert after[name] == before[name], name
    assert after["assets/p/lead.svg"] == before["assets/p/lead.svg"]
    assert [(c.chart, c.outcome) for c in report.pages[0].charts] == [
        ("lead", Outcome.UNCHANGED),
        ("fro", Outcome.RENDERED),
    ]
    assert snap_files(root, "p") == ["fro.snapshot-1.json", "lead.snapshot-1.json"]


def test_a_changed_sql_keeps_the_snapshot_and_reports_a_notice(tmp_path: Path) -> None:
    root = frozen_root(tmp_path)
    age(root)
    before = snapshot_of(root / "dashboards")
    text = page_bytes(root, "p")
    new_directive = chart("fro", mode="frozen", sql="select changed")
    assert fro("fro") in text
    write_page(root, "p", text.replace(fro("fro"), new_directive))
    os.utime(root / "dashboards" / "p.md", ns=(OLD_TIME_NS, OLD_TIME_NS))
    page_before = snapshot_of(root / "dashboards")["p.md"]
    report = go_offline(root)
    after = snapshot_of(root / "dashboards")
    assert after["p.md"] == page_before, "the page is not rewritten"
    for name in before:
        if name != "p.md":
            assert after[name] == before[name], name
    page = report.pages[0]
    first, second = page.charts
    assert (first.notices, first.problems) == ((), ())
    assert codes(second.notices) == ["sql_changed"]
    assert second.problems == ()
    notice = second.notices[0]
    assert notice.severity is Severity.NOTICE
    assert (notice.page, notice.chart, notice.line) == ("p", "fro", second.line)
    assert "p:fro" in notice.fix
    assert "assets/p/fro.snapshot-1.json" in notice.message
    assert second.outcome is Outcome.UNCHANGED
    assert report.failed is False


@pytest.mark.parametrize("changed", [True, False])
def test_an_adopted_latest_snapshot_reports_a_changed_sql(
    tmp_path: Path, changed: bool
) -> None:
    root = frozen_root(tmp_path)
    text = page_bytes(root, "p")
    if changed:
        text = text.replace(
            fro("fro"), chart("fro", mode="frozen", sql="select changed")
        )
    stripped = remove_region(text, "fro")
    write_page(root, "p", stripped)
    assert snap_ref("p", "fro", 1) not in stripped
    report = go_offline(root)
    chart_result = result_of(report.pages[0], "fro")
    assert region_lines(page_bytes(root, "p"), "fro")[0] == snap_ref("p", "fro", 1)
    assert chart_result.problems == ()
    assert chart_result.outcome is Outcome.RENDERED
    if changed:
        assert codes(chart_result.notices) == ["sql_changed"]
        assert "assets/p/fro.snapshot-1.json" in chart_result.notices[0].message
    else:
        assert chart_result.notices == ()
    assert report.failed is False


def test_moving_a_key_after_sql_is_not_a_sql_change(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    sql_last = directive_block(
        [
            ("id", "fro"),
            ("kind", "bar"),
            ("mode", "frozen"),
            ("title", "Title of fro"),
            ("channels", GOOD_CHANNELS),
            ("sql", "|\n  select fro"),
        ]
    )
    write_page(root, "p", page_text(fro("lead"), sql_last))
    go(root, source_of({"lead": DATA_B, "fro": DATA_A}), today=D1)
    stored = decode(snap_path(root, "p", "fro", 1).read_bytes())
    assert stored.sql == "select fro", "the block was last, so it had no final newline"
    text = page_bytes(root, "p")
    sql_first = directive_block(
        [
            ("id", "fro"),
            ("kind", "bar"),
            ("mode", "frozen"),
            ("title", "Title of fro"),
            ("sql", "|\n  select fro"),
            ("channels", GOOD_CHANNELS),
        ]
    )
    assert sql_last in text
    write_page(root, "p", text.replace(sql_last, sql_first))
    report = go_offline(root, today=D1)
    second = report.pages[0].charts[1]
    assert (second.chart, second.notices, second.problems) == ("fro", (), ())
    assert report.failed is False


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_a_recorded_snapshot_that_cannot_be_used_leaves_the_chart_alone(
    tmp_path: Path, damage: str
) -> None:
    root = frozen_root(tmp_path)
    path = snap_path(root, "p", "fro", 1)
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"this is not a snapshot\n")
    age(root)
    before = snapshot_of(root)
    report = go_offline(root)
    assert_untouched(before, snapshot_of(root))
    first, second = report.pages[0].charts
    assert first.outcome is Outcome.UNCHANGED and first.problems == ()
    assert second.outcome is Outcome.FAILED
    expected = "snapshot_missing" if damage == "missing" else "snapshot_unreadable"
    assert codes(second.problems) == [expected]
    (problem,) = second.problems
    assert problem.source is Source.DASHBOARD
    assert (problem.page, problem.chart, problem.line) == ("p", "fro", second.line)
    assert "assets/p/fro.snapshot-1.json" in problem.message
    assert "fitdocs dashboard freeze p:fro" in problem.fix
    assert report.failed


def test_a_deleted_region_adopts_the_highest_generation_without_a_fetch(
    tmp_path: Path,
) -> None:
    root = frozen_root(tmp_path)
    again = go(
        root, source_of({"fro": DATA_B}), Target("p", "fro"), action=Action.FREEZE
    )
    assert not again.failed
    assert snap_files(root, "p") == [
        "fro.snapshot-1.json",
        "fro.snapshot-2.json",
        "lead.snapshot-1.json",
    ]
    stripped = remove_region(page_bytes(root, "p"), "fro")
    write_page(root, "p", stripped)
    assert snap_ref("p", "fro", 2) not in stripped
    asset_path(root, "p", "fro").unlink()
    before = snapshot_of(root / "dashboards")
    report = go_offline(root)
    text = page_bytes(root, "p")
    assert region_lines(text, "fro")[0] == snap_ref("p", "fro", 2)
    assert "zeta" in asset_path(root, "p", "fro").read_text()
    assert "alpha" not in asset_path(root, "p", "fro").read_text()
    assert report.pages[0].charts[1].snapshot == "assets/p/fro.snapshot-2.json"
    after = snapshot_of(root / "dashboards")
    for name in before:
        if name.startswith("assets/p/") and ".snapshot-" in name:
            assert after[name] == before[name], name
    assert snap_files(root, "p") == [
        "fro.snapshot-1.json",
        "fro.snapshot-2.json",
        "lead.snapshot-1.json",
    ]


def test_a_renamed_page_keeps_its_recorded_snapshot_and_moves_its_image(
    tmp_path: Path,
) -> None:
    root = frozen_root(tmp_path)
    old = root / "dashboards" / "p.md"
    old.rename(root / "dashboards" / "q.md")
    snapshot_before = snapshot_of(root / "dashboards")
    report = go_offline(root)
    text = page_bytes(root, "q")
    lines = region_lines(text, "fro")
    assert lines[0] == snap_ref("p", "fro", 1), "the record still names the old page"
    assert lines[2] == "![Title of fro](assets/q/fro.svg)"
    assert asset_path(root, "q", "fro").exists()
    assert not asset_path(root, "p", "fro").exists(), "the old image is gone"
    assert not asset_path(root, "p", "lead").exists()
    assert report.removed == ("assets/p/fro.svg", "assets/p/lead.svg")
    after = snapshot_of(root / "dashboards")
    for name in ("assets/p/fro.snapshot-1.json", "assets/p/lead.snapshot-1.json"):
        assert after[name] == snapshot_before[name], name
    assert snap_files(root, "q") == [], "no snapshot was taken for the new name"
    assert "alpha" in asset_path(root, "q", "fro").read_text()


def test_freezing_one_of_two_pages_sharing_a_snapshot_repoints_only_that_page(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(fro("lead"), fro("fro")))
    go(root, source_of({"lead": DATA_B, "fro": DATA_A}), today=D1)
    shared = page_bytes(root, "a")
    write_page(root, "b", shared)
    go_offline(root)  # b draws its own image from a's snapshot
    assert region_lines(page_bytes(root, "b"), "fro")[0] == snap_ref("a", "fro", 1)
    assert snap_files(root, "b") == []

    age(root)
    before = snapshot_of(root / "dashboards")
    report = go(
        root, source_of({"fro": DATA_B}), Target("a", "fro"), action=Action.FREEZE
    )
    assert not report.failed
    assert snap_files(root, "a") == [
        "fro.snapshot-1.json",
        "fro.snapshot-2.json",
        "lead.snapshot-1.json",
    ]
    assert region_lines(page_bytes(root, "a"), "fro")[0] == snap_ref("a", "fro", 2)
    after = snapshot_of(root / "dashboards")
    for name in before:
        if name.startswith(("b.md", "assets/b/")) or name.endswith("snapshot-1.json"):
            assert after[name] == before[name], name
    assert region_lines(page_bytes(root, "b"), "fro")[0] == snap_ref("a", "fro", 1)
    assert "alpha" in asset_path(root, "b", "fro").read_text()

    other = go(
        root, source_of({"fro": DATA_C}), Target("b", "fro"), action=Action.FREEZE
    )
    assert not other.failed
    assert snap_files(root, "b") == ["fro.snapshot-1.json"]
    assert region_lines(page_bytes(root, "b"), "fro")[0] == snap_ref("b", "fro", 1)
    assert region_lines(page_bytes(root, "a"), "fro")[0] == snap_ref("a", "fro", 2)
    assert "kappa" in asset_path(root, "b", "fro").read_text()
    assert "zeta" in asset_path(root, "a", "fro").read_text()


def test_a_freeze_never_overwrites_an_earlier_generation(tmp_path: Path) -> None:
    root = frozen_root(tmp_path)
    first = snap_path(root, "p", "fro", 1).read_bytes()
    first_mtime = snap_path(root, "p", "fro", 1).stat().st_mtime_ns
    go(
        root,
        source_of({"fro": DATA_B}),
        Target("p", "fro"),
        action=Action.FREEZE,
        today=D2,
    )
    go(root, source_of({"fro": DATA_C}), Target("p", "fro"), action=Action.FREEZE)
    assert snap_files(root, "p") == [
        "fro.snapshot-1.json",
        "fro.snapshot-2.json",
        "fro.snapshot-3.json",
        "lead.snapshot-1.json",
    ]
    assert snap_path(root, "p", "fro", 1).read_bytes() == first
    assert snap_path(root, "p", "fro", 1).stat().st_mtime_ns == first_mtime
    second = decode(snap_path(root, "p", "fro", 2).read_bytes())
    third = decode(snap_path(root, "p", "fro", 3).read_bytes())
    assert (second.generation, second.data, second.today) == (2, DATA_B, D2)
    assert (third.generation, third.data) == (3, DATA_C)
    assert region_lines(page_bytes(root, "p"), "fro")[0] == snap_ref("p", "fro", 3)


def test_freezing_a_relative_chart_is_refused_naming_its_mode(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(fro("lead"), own("rel")))
    go(root, source_of({"lead": DATA_B, "rel": DATA_A}), today=D1)
    age(root)
    before = snapshot_of(root)
    report = go_offline(root, Target("p", "rel"), action=Action.FREEZE)
    assert_untouched(before, snapshot_of(root))
    (only,) = report.pages[0].charts
    assert only.outcome is Outcome.FAILED
    assert codes(only.problems) == ["freeze_relative"]
    (problem,) = only.problems
    assert "relative" in problem.message and "mode: frozen" in problem.fix
    assert (problem.page, problem.chart, problem.line) == ("p", "rel", only.line)
    assert report.failed and report.index == "not_needed"


def test_a_page_target_freezes_the_frozen_charts_and_leaves_relative_ones_alone(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(fro("lead"), own("rel"), fro("fro")))
    go(root, source_of({"lead": DATA_A, "rel": DATA_B, "fro": DATA_A}), today=D1)
    age(root)
    before = snapshot_of(root / "dashboards")
    rel_region = region_lines(page_bytes(root, "p"), "rel")
    assert rel_region, "the relative chart has a rendered region to keep"
    source = source_of({"lead": DATA_C, "fro": DATA_C})
    report = go(root, source, Target("p", None), action=Action.FREEZE, today=D2)
    assert [each.chart for each in source.calls] == ["lead", "fro"]
    by_id = {each.chart: each for each in report.pages[0].charts}
    assert by_id["rel"].problems == () and by_id["rel"].notices == ()
    assert by_id["rel"].outcome is Outcome.CHECKED
    assert by_id["lead"].outcome is Outcome.RENDERED
    assert by_id["fro"].outcome is Outcome.RENDERED
    assert report.failed is False
    after = snapshot_of(root / "dashboards")
    assert after["assets/p/rel.svg"] == before["assets/p/rel.svg"]
    assert "assets/p/fro.snapshot-2.json" in after
    assert "assets/p/lead.snapshot-2.json" in after
    text = page_bytes(root, "p")
    assert region_lines(text, "fro")[0] == snap_ref("p", "fro", 2)
    assert region_lines(text, "rel") == rel_region


def test_a_chart_target_naming_a_relative_chart_is_still_refused_in_a_mixed_page(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(fro("lead"), own("rel")))
    go(root, source_of({"lead": DATA_A, "rel": DATA_B}), today=D1)
    age(root)
    before = snapshot_of(root)
    report = go_offline(root, Target("p", "rel"), action=Action.FREEZE)
    assert_untouched(before, snapshot_of(root))
    (only,) = report.pages[0].charts
    assert codes(only.problems) == ["freeze_relative"]
    assert report.failed


@pytest.mark.parametrize("cause", ["sql", "kit"])
@pytest.mark.parametrize("action", [Action.FREEZE, Action.REFRESH])
def test_a_failing_first_freeze_writes_a_note_on_refresh_but_nothing_on_freeze(
    tmp_path: Path, cause: str, action: Action
) -> None:
    root = make_data_root(tmp_path)
    channels = "\n  x: nope\n  y: value" if cause == "kit" else GOOD_CHANNELS
    write_page(root, "p", page_text("# Weekly", fro("fro", channels=channels)))
    age(root)
    before = snapshot_of(root)
    answer = _sql_failed("fro") if cause == "sql" else DATA_B
    report = go(root, source_of({"fro": answer}), Target("p", "fro"), action=action)
    (only,) = report.pages[0].charts
    assert only.outcome is Outcome.FAILED and only.problems
    if action is Action.FREEZE:
        assert_untouched(before, snapshot_of(root))
        assert not (root / "dashboards" / "assets").exists()
        assert report.pages[0].written is False
    else:
        assert region_lines(page_bytes(root, "p"), "fro")[0].startswith(
            "*Not rendered:"
        )
        assert snap_files(root, "p") == []


@pytest.mark.parametrize("cause", ["sql", "kit"])
def test_a_failing_freeze_leaves_region_image_and_snapshots_alone(
    tmp_path: Path, cause: str
) -> None:
    root = frozen_root(tmp_path)
    if cause == "kit":
        text = page_bytes(root, "p")
        broken = fro("fro", channels="\n  x: nope\n  y: value")
        write_page(root, "p", text.replace(fro("fro"), broken))
    age(root)
    before = snapshot_of(root)
    answer = _sql_failed("fro") if cause == "sql" else DATA_B
    source = source_of({"fro": answer})
    report = go(root, source, Target("p", "fro"), action=Action.FREEZE)
    assert len(source.calls) == 1, "the freeze did reach the source"
    assert_untouched(before, snapshot_of(root))
    (only,) = report.pages[0].charts
    assert only.outcome is Outcome.FAILED
    assert codes(only.problems) == [
        "sql_failed" if cause == "sql" else "unknown_column"
    ]
    assert report.pages[0].written is False


def test_a_freeze_without_an_index_is_refused_with_the_indexs_state(
    tmp_path: Path,
) -> None:
    root = frozen_root(tmp_path)
    age(root)
    before = snapshot_of(root)
    report = run_dashboards(
        RunRequest(Action.FREEZE, root, (Target("p", "fro"),), D2),
        unavailable_opener(UNAVAILABLE),
    )
    assert_untouched(before, snapshot_of(root))
    assert report.index == "not_built"
    (only,) = report.pages[0].charts
    assert codes(only.problems) == ["index_unavailable"]
    assert "the index is not built." in only.problems[0].message
    assert only.problems[0].fix == UNAVAILABLE.fix
    assert report.failed


def test_charts_that_need_no_query_still_render_while_the_index_is_unavailable(
    tmp_path: Path,
) -> None:
    root = frozen_root(tmp_path)
    text = page_bytes(root, "p")
    retitled = fro("fro", extra=[("window", "6 weeks")])
    write_page(
        root, "p", text.replace(fro("fro"), retitled) + own("rel") + fro("newbie")
    )
    age(root)
    report = run_dashboards(
        RunRequest(Action.REFRESH, root, (), D2), unavailable_opener(UNAVAILABLE)
    )
    assert report.index == "not_built" and report.index_problem is not None
    by_id = {each.chart: each for each in report.pages[0].charts}
    assert by_id["fro"].outcome is Outcome.RENDERED and by_id["fro"].problems == ()
    assert by_id["lead"].outcome is Outcome.UNCHANGED
    assert codes(by_id["rel"].problems) == ["index_unavailable"]
    assert codes(by_id["newbie"].problems) == ["index_unavailable"]
    assert "6 weeks" in "".join(region_lines(page_bytes(root, "p"), "fro"))
    assert snap_files(root, "p") == ["fro.snapshot-1.json", "lead.snapshot-1.json"]


def test_a_first_freeze_whose_render_fails_creates_no_snapshot(tmp_path: Path) -> None:
    root = make_data_root(tmp_path)
    write_page(
        root,
        "p",
        page_text(
            fro("lead"), fro("bad", channels="\n  x: nope\n  y: value"), fro("later")
        ),
    )
    report = go(root, source_of({"lead": DATA_A, "bad": DATA_B, "later": DATA_C}))
    bad = report.pages[0].charts[1]
    assert codes(bad.problems) == ["unknown_column"]
    assert snap_files(root, "p") == [
        "later.snapshot-1.json",
        "lead.snapshot-1.json",
    ]
    assert not asset_path(root, "p", "bad").exists()
    assert region_lines(page_bytes(root, "p"), "bad")[0].startswith("*Not rendered:")
    assert bad.snapshot is None
    assert [c.outcome for c in report.pages[0].charts] == [
        Outcome.RENDERED,
        Outcome.FAILED,
        Outcome.RENDERED,
    ]


def test_check_of_a_never_frozen_chart_fetches_but_creates_no_snapshot(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("lead"), fro("fro")))
    age(root)
    before = snapshot_of(root)
    source = source_of({"lead": DATA_B, "fro": DATA_A})
    report = go(root, source, action=Action.CHECK)
    assert [each.chart for each in source.calls] == ["lead", "fro"]
    assert_untouched(before, snapshot_of(root))
    assert not (root / "dashboards" / "assets").exists()
    assert [c.outcome for c in report.pages[0].charts] == [Outcome.CHECKED] * 2
    assert report.pages[0].charts[1].snapshot is None


def test_check_of_a_frozen_chart_with_a_snapshot_reads_it_and_changes_nothing(
    tmp_path: Path,
) -> None:
    root = frozen_root(tmp_path)
    age(root)
    before = snapshot_of(root)
    report = go_offline(root, action=Action.CHECK)
    assert_untouched(before, snapshot_of(root))
    assert [c.outcome for c in report.pages[0].charts] == [Outcome.CHECKED] * 2
    assert not report.failed


def test_a_result_with_a_value_that_cannot_be_stored_fails_the_freeze(
    tmp_path: Path,
) -> None:
    unusable = chart_data(
        (category_column("label"), number_column("value"), number_column("extra")),
        [("one", 1.0, 2.0), ("two", 2.0, float("nan")), ("three", 3.0, 4.0)],
    )
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(own("ctl"), fro("lead"), fro("fro")))
    source = source_of({"ctl": unusable, "lead": DATA_B, "fro": unusable})
    report = go(root, source, today=D1)
    by_id = {each.chart: each for each in report.pages[0].charts}
    assert by_id["ctl"].outcome is Outcome.RENDERED, "the same rows draw as relative"
    assert by_id["lead"].outcome is Outcome.RENDERED
    failed = by_id["fro"]
    assert failed.outcome is Outcome.FAILED
    assert codes(failed.problems) == ["write_failed"]
    (problem,) = failed.problems
    assert "`extra`" in problem.message and "`value`" not in problem.message
    assert "number column" in problem.message
    assert problem.column == "extra"
    assert problem.fix == "Exclude or cast the non-finite values in the SQL."
    assert (problem.page, problem.chart, problem.line) == ("p", "fro", failed.line)
    assert snap_files(root, "p") == ["lead.snapshot-1.json"]
    assert not asset_path(root, "p", "fro").exists()
    assert region_lines(page_bytes(root, "p"), "fro")[0].startswith("*Not rendered:")
    assert failed.snapshot is None


def test_rows_wider_than_their_columns_are_a_defect_not_a_chart_failure(
    tmp_path: Path,
) -> None:
    wide = ChartData(DATA_A.columns, (("one", 1.0, 99.0),))
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(fro("fro")))
    age(root)
    before = snapshot_of(root)
    with pytest.raises(ValueError, match="width"):
        go(root, source_of({"fro": wide}))
    assert_untouched(before, snapshot_of(root))


def test_a_snapshot_that_cannot_be_created_fails_the_chart_and_writes_no_image(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "p", page_text(fro("lead"), fro("fro")))
    (root / "dashboards" / "assets").mkdir()
    (root / "dashboards" / "assets" / "p").write_text("in the way\n")
    report = go(root, source_of({"lead": DATA_B, "fro": DATA_A}))
    for each in report.pages[0].charts:
        assert codes(each.problems) == ["write_failed"], each.chart
        assert each.outcome is Outcome.FAILED
        assert "snapshot" in each.problems[0].message
    assert (root / "dashboards" / "assets" / "p").read_text() == "in the way\n"
    assert BEGIN_PREFIX not in page_bytes(root, "p")


def test_a_frozen_chart_draws_the_same_bytes_as_a_relative_one_over_the_same_rows(
    tmp_path: Path,
) -> None:
    pace = chart_data(
        (
            category_column("label"),
            number_column("pace_s_per_km", unit="s_per_km"),
        ),
        [("beta", 341.0), ("alpha", 305.0), ("gamma", 322.0)],
    )
    bare = chart_data(
        (category_column("label"), number_column("pace_s_per_km")),
        [("beta", 341.0), ("alpha", 305.0), ("gamma", 322.0)],
    )
    channels = "\n  x: label\n  y: pace_s_per_km"
    root = make_data_root(tmp_path)
    for name, mode in (("rel", "relative"), ("bare", "relative"), ("froz", "frozen")):
        write_page(
            root,
            name,
            page_text(
                own("pad", mode=mode),
                chart("pace", mode=mode, sql="select pace", channels=channels),
            ),
        )
    source = FakeSource()
    source.queue("select pad\n", DATA_A)
    source.queue("select pad", DATA_A)
    source.queue("select pace\n", pace)
    source.queue("select pace", pace)
    go(root, source, Target("rel", None), Target("froz", None))
    bare_source = FakeSource()
    bare_source.queue("select pad\n", DATA_A)
    bare_source.queue("select pace\n", bare)
    go(root, bare_source, Target("bare", None))
    relative = asset_path(root, "rel", "pace").read_bytes()
    assert asset_path(root, "bare", "pace").read_bytes() != relative, "units matter"
    assert asset_path(root, "froz", "pace").read_bytes() == relative
    asset_path(root, "froz", "pace").unlink()
    go_offline(root, Target("froz", None))
    assert asset_path(root, "froz", "pace").read_bytes() == relative


# -- cleanup ---------------------------------------------------------------------


def test_cleanup_removes_unreferenced_images_and_keeps_every_snapshot(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(own("keep"), fro("gone"), fro("stay")))
    write_page(root, "b", page_text(own("other")))
    go(
        root,
        source_of({"keep": DATA_A, "gone": DATA_B, "stay": DATA_C, "other": DATA_A}),
    )
    assert (
        asset_path(root, "a", "gone").exists()
        and asset_path(root, "b", "other").exists()
    )
    text = page_bytes(root, "a")
    trimmed = remove_region(text.replace(fro("gone"), ""), "gone")
    write_page(root, "a", trimmed)
    (root / "dashboards" / "b.md").unlink()
    snapshots = {
        name: state
        for name, state in snapshot_of(root / "dashboards").items()
        if ".snapshot-" in name
    }
    assert snapshots, "there are snapshots to keep"

    checked = go(root, source_of({"keep": DATA_A, "stay": DATA_C}), action=Action.CHECK)
    assert checked.removed == () and asset_path(root, "a", "gone").exists()
    assert asset_path(root, "b", "other").exists(), "check never cleans up"

    report = go(root, source_of({"keep": DATA_A, "stay": DATA_C}), Target("a", "keep"))
    assert report.removed == ("assets/a/gone.svg", "assets/b/other.svg")
    assert not asset_path(root, "a", "gone").exists()
    assert not asset_path(root, "b", "other").exists()
    assert (
        not (root / "dashboards" / "assets" / "b").exists()
        or snap_files(root, "b") == []
    )
    assert (
        asset_path(root, "a", "keep").exists()
        and asset_path(root, "a", "stay").exists()
    )
    after = {
        name: state
        for name, state in snapshot_of(root / "dashboards").items()
        if ".snapshot-" in name
    }
    assert after == snapshots, "no snapshot was touched"


def test_a_freeze_run_cleans_up_too(tmp_path: Path) -> None:
    root = frozen_root(tmp_path)
    stripped = remove_region(page_bytes(root, "p").replace(fro("lead"), ""), "lead")
    write_page(root, "p", stripped)
    report = go(
        root, source_of({"fro": DATA_B}), Target("p", "fro"), action=Action.FREEZE
    )
    assert report.removed == ("assets/p/lead.svg",)
    assert snap_path(root, "p", "lead", 1).exists()


@pytest.mark.parametrize("how", ["changed", "failed"])
def test_an_image_left_unreferenced_by_a_failed_page_write_is_removed_in_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    root = make_data_root(tmp_path)
    write_page(root, "a", page_text(own("a1")))
    go(root, source_of({"a1": DATA_A}))
    write_page(root, "a", page_bytes(root, "a") + own("a2"))
    real = storage.replace_page

    def racing(page: PageFile, text: str) -> str:
        if how == "failed":
            raise OSError("disk full")
        page.path.write_bytes(page.raw + b"edited elsewhere\n")
        return real(page, text)

    monkeypatch.setattr(engine, "replace_page", racing)
    report = go(root, source_of({"a1": DATA_A, "a2": DATA_B}))
    expected = "page_changed" if how == "changed" else "write_failed"
    assert codes(report.pages[0].charts[1].problems) == [expected]
    assert report.removed == ("assets/a/a2.svg",)
    assert not asset_path(root, "a", "a2").exists()
    assert asset_path(root, "a", "a1").exists()


def test_every_chart_gets_its_own_image_whatever_the_names_share(
    tmp_path: Path,
) -> None:
    root = make_data_root(tmp_path)
    labels = {
        ("a-b", "c"): "p1",
        ("a", "b-c"): "p2",
        ("x", "pace"): "p3",
        ("y", "pace"): "p4",
    }
    source = FakeSource()
    for (page, chart_id), label in labels.items():
        write_page(root, page, page_text(own(chart_id)))
        for suffix in ("\n", ""):
            source.queue(
                f"select {chart_id}{suffix}", category_number_data([(label, 1.0)])
            )
    report = go(root, source)
    assert not report.failed
    seen: dict[str, tuple[str, str]] = {}
    for (page, chart_id), label in labels.items():
        rel = storage.asset_rel_path(page, chart_id)
        text = (root / "dashboards" / rel).read_text()
        assert label in text, rel
        assert text not in seen, "two charts share one image"
        seen[text] = (page, chart_id)
        assert f"]({rel})" in page_bytes(root, page), "the link is the asset path"
    assert len(seen) == 4
    assert len(list((root / "dashboards" / "assets").rglob("*.svg"))) == 4
    again = FakeSource()
    again.results = {key: list(value) for key, value in source.results.items()}
    cleaned = go(root, again, Target("a-b", "c"))
    assert cleaned.removed == (), "cleanup kept all four images"
    assert len(list((root / "dashboards" / "assets").rglob("*.svg"))) == 4
