"""The page grammar: lines, fences, directives, regions and near misses."""

from __future__ import annotations

import pytest

from fitdocs.dashboards.grammar import (
    CHART_ID_RE,
    PAGE_NAME_RE,
    REFERENCE_RE,
    DirectiveBlock,
    PageScan,
    begin_marker,
    end_marker,
    following_region,
    scan_page,
    split_lines,
)
from fitdocs.dashboards.problems import DashboardCode, Source
from tests.dashboards._helpers import directive_block, page_text, region_block

PAGE = "weekly"


def chart(chart_id: str, *, ending: str = "\n") -> str:
    """A well-formed directive whose body is three lines."""
    return directive_block(
        [("id", chart_id), ("kind", "bar"), ("sql", "|\n  select 1")], ending=ending
    )


def codes(scan: PageScan) -> list[tuple[str, int | None]]:
    return [(problem.code, problem.line) for problem in scan.problems]


def numbers(scan: PageScan) -> list[int]:
    return [directive.open_line for directive in scan.directives]


# -- the page and chart-id rules (1.3, 4.4 shape) ---


@pytest.mark.parametrize("name", ["weekly", "a-b-1", "2026-10", "x", "a1-2b"])
def test_page_names_and_chart_ids_accept_slugs(name: str) -> None:
    assert PAGE_NAME_RE.fullmatch(name)
    assert CHART_ID_RE.fullmatch(name)


@pytest.mark.parametrize(
    "name",
    ["", "Weekly", "a--b", "-a", "a-", "a_b", "a.b", "a b", "é", "a\n", "a/b"],
)
def test_page_names_and_chart_ids_refuse_non_slugs(name: str) -> None:
    assert PAGE_NAME_RE.fullmatch(name) is None
    assert CHART_ID_RE.fullmatch(name) is None


def test_markers_and_reference_line_shapes() -> None:
    assert begin_marker("a-1") == "<!-- fitdocs:begin:chart:a-1 -->"
    assert end_marker("a-1") == "<!-- fitdocs:end:chart:a-1 -->"
    good = "<!-- fitdocs:snapshot assets/weekly/load-1.snapshot-12.json -->"
    assert REFERENCE_RE.fullmatch(good)
    for bad in (
        "<!-- fitdocs:snapshot assets/weekly/load-1.snapshot-012.json -->",
        "<!-- fitdocs:snapshot assets/weekly/load-1.snapshot-0.json -->",
        "<!-- fitdocs:snapshot assets/Weekly/load-1.snapshot-1.json -->",
        "<!-- fitdocs:snapshot assets/weekly/load-1.snapshot-1.json --> ",
        "<!-- fitdocs:snapshot ../assets/weekly/load-1.snapshot-1.json -->",
        "<!-- fitdocs:snapshot assets/weekly/load-1.svg -->",
    ):
        assert REFERENCE_RE.fullmatch(bad) is None, bad


# -- split_lines (16.5) ---


@pytest.mark.parametrize(
    "text",
    [
        "a\nb\nc\n",
        "a\r\nb\r\nc\r\n",
        "a\nb\r\nc\n",
        "a\r\nb\nc",
        "no newline at all",
        "\ufeffa\r\nb\n",
        "a\n\n\nb\n",
        "a\rb\n",
        "a\r\n\r\n",
        "\nabc\r",
        "",
    ],
)
def test_split_lines_round_trips_the_bytes(text: str) -> None:
    lines = split_lines(text)
    assert "".join(line.text + line.ending for line in lines) == text
    assert [line.number for line in lines] == list(range(1, len(lines) + 1))


def test_split_lines_keeps_each_ending_apart_from_the_text() -> None:
    lines = split_lines("\ufeffone\nt\rwo\r\nthree")
    assert [(line.text, line.ending) for line in lines] == [
        ("\ufeffone", "\n"),
        ("t\rwo", "\r\n"),
        ("three", ""),
    ]
    assert [(line.text, line.ending) for line in split_lines("\nabc\r")] == [
        ("", "\n"),
        ("abc\r", ""),
    ]
    assert split_lines("a\n")[-1].ending == "\n"
    assert len(split_lines("a\n")) == 1
    assert split_lines("") == ()


def test_crlf_and_lf_pages_scan_to_the_same_blocks() -> None:
    def build(ending: str) -> str:
        return page_text(
            "intro",
            chart("one", ending=ending),
            region_block("one", "![x](a.svg)", ending=ending),
            chart("two", ending=ending),
            region_block("two", "![y](b.svg)", ending=ending),
            ending=ending,
        )

    lf = scan_page(build("\n"), page=PAGE)
    crlf = scan_page(build("\r\n"), page=PAGE)
    assert len(lf.directives) == 2 and len(lf.regions) == 2
    assert crlf.directives == lf.directives
    assert [(r.chart_id, r.begin_line, r.end_line) for r in crlf.regions] == [
        (r.chart_id, r.begin_line, r.end_line) for r in lf.regions
    ]
    assert all("\r" not in line.text for line in crlf.lines)
    assert crlf.problems == lf.problems == ()


def test_a_leading_bom_does_not_move_a_first_line_opener_off_column_zero() -> None:
    text = page_text(chart("one"), chart("two"), bom=True)
    assert text.startswith("\ufeff<!-- fitdocs:chart\n")
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1, 7]
    assert scan.problems == ()
    assert scan.lines[0].text.startswith("\ufeff")


def test_a_first_line_fence_after_a_bom_hides_what_it_fences() -> None:
    text = page_text("```", chart("hidden"), "```", chart("second"), bom=True)
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [9]
    assert scan.problems == ()


def test_a_first_line_begin_marker_after_a_bom_opens_a_region() -> None:
    text = page_text(region_block("first", "x"), chart("second"), bom=True)
    scan = scan_page(text, page=PAGE)
    assert [(r.chart_id, r.begin_line, r.end_line) for r in scan.regions] == [
        ("first", 1, 3)
    ]
    assert scan.problems == ()


def test_a_first_line_end_marker_after_a_bom_is_an_orphan() -> None:
    text = page_text(end_marker("orphan"), chart("second"), bom=True)
    (problem,) = scan_page(text, page=PAGE).problems
    assert problem.line == 1
    assert "no open region" in problem.message


def test_a_bom_on_a_later_line_is_not_stripped() -> None:
    text = page_text(chart("first"), "\ufeff<!-- fitdocs:chart", "id: x", "-->")
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1]
    assert codes(scan) == [(DashboardCode.OPENER_MALFORMED.value, 7)]


# -- openers and closers (3.1, 3.5) ---


def test_an_exact_directive_is_found_with_its_lines_and_body() -> None:
    text = page_text("# Title", chart("first"), "prose", chart("second"))
    scan = scan_page(text, page=PAGE)
    assert scan.problems == ()
    assert scan.directives == (
        DirectiveBlock(2, 7, "id: first\nkind: bar\nsql: |\n  select 1", None),
        DirectiveBlock(9, 14, "id: second\nkind: bar\nsql: |\n  select 1", None),
    )


@pytest.mark.parametrize(
    "offending",
    [
        "<!-- fitdocs:chart -->",
        "<!-- fitdocs:chart ",
        " <!-- fitdocs:chart",
        "    <!-- fitdocs:chart",
        "text <!-- fitdocs:chart",
        "<!-- fitdocs:chart: extra",
        "<!-- fitdocs:charts",
    ],
)
def test_a_malformed_opener_is_reported_and_is_not_a_chart(offending: str) -> None:
    text = page_text(chart("first"), offending, "id: second", "-->")
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1]  # only the first chart is a directive
    assert codes(scan) == [(DashboardCode.OPENER_MALFORMED.value, 7)]
    problem = scan.problems[0]
    assert problem.source is Source.DASHBOARD
    assert problem.page == PAGE and problem.chart is None
    assert "7" in problem.message and "column 0" in problem.fix
    assert problem.message.endswith(".") and problem.fix.endswith(".")


def test_a_closer_must_be_exactly_the_closing_line() -> None:
    text = page_text(chart("first"), "<!-- fitdocs:chart", "id: x", "  -->", "-->")
    scan = scan_page(text, page=PAGE)
    second = scan.directives[1]
    assert (second.open_line, second.close_line) == (7, 10)
    assert second.terminator_line == 9


# -- bodies, blank lines and terminators (3.2, 3.3) ---


def test_blank_lines_and_sql_comments_stay_in_the_body() -> None:
    body = ["id: second", "", "sql: |", "  -- a comment", "", "  select 1", ""]
    text = page_text(chart("first"), "<!-- fitdocs:chart", *body, "-->")
    scan = scan_page(text, page=PAGE)
    second = scan.directives[1]
    assert second.body == "\n".join(body)
    assert second.terminator_line is None
    assert (second.open_line, second.close_line) == (7, 15)
    assert scan.problems == ()


@pytest.mark.parametrize("sequence", ["-->", "--!>"])
def test_a_comment_terminator_mid_body_is_marked_at_its_line(sequence: str) -> None:
    text = page_text(
        chart("first"),
        "<!-- fitdocs:chart",
        "id: second",
        f"sql: select 1 {sequence} select 2",
        "title: later",
        f"note: {sequence}",
        "-->",
    )
    scan = scan_page(text, page=PAGE)
    second = scan.directives[1]
    assert second.terminator_line == 9  # the first such line, not the last
    assert (second.open_line, second.close_line) == (7, 12)
    assert scan.directives[0].terminator_line is None


def test_both_terminator_forms_are_found_independently() -> None:
    text = page_text(chart("first"), "<!-- fitdocs:chart", "a: --!>", "b: -->", "-->")
    assert scan_page(text, page=PAGE).directives[1].terminator_line == 8
    text = page_text(chart("first"), "<!-- fitdocs:chart", "a: -->", "b: --!>", "-->")
    assert scan_page(text, page=PAGE).directives[1].terminator_line == 8


# -- unclosed directives (3.4) ---


def test_an_unclosed_directive_is_marked_and_the_scan_resumes_after_its_opener() -> (
    None
):
    text = page_text(
        chart("first"),
        "<!-- fitdocs:chart",  # 7: no closing line follows anywhere
        "id: second",
        region_block("later", "![x](a.svg)"),  # 9-11
        " <!-- fitdocs:chart",  # 12
        "```",
        "<!-- fitdocs:chart",  # 14, fenced
        "```",
        "<!-- fitdocs:chart",  # 16: a second unclosed opener
        "tail",
    )
    scan = scan_page(text, page=PAGE)
    assert [(d.open_line, d.close_line) for d in scan.directives] == [
        (1, 6),
        (7, None),
        (16, None),
    ]
    assert scan.directives[0].body is not None  # a closed directive has a body
    assert scan.directives[1].body is None
    assert scan.directives[1].terminator_line is None
    assert scan.directives[2].body is None
    assert [(r.chart_id, r.begin_line, r.end_line) for r in scan.regions] == [
        ("later", 9, 11)
    ]
    assert codes(scan) == [(DashboardCode.OPENER_MALFORMED.value, 12)]


# -- fences (3.6) ---


EXAMPLE = [
    "<!-- fitdocs:chart",
    "id: example",
    "-->",
    "<!-- fitdocs:begin:chart:example -->",
    "<!-- fitdocs:end:chart:example -->",
    " <!-- fitdocs:chart",
    "<!-- fitdocs:begin:chart:Bad_Id -->",
]


def fenced(opener: str, closer: str, *lines: str) -> str:
    return page_text(chart("first"), opener, *lines, closer, chart("second"))


@pytest.mark.parametrize(
    ("opener", "closer"),
    [
        ("```", "```"),
        ("~~~", "~~~"),
        ("```python", "```"),
        ("~~~ info `with` ticks", "~~~"),
        ("   ```", "   ```"),
        ("```", "````````"),
        ("~~~~", "~~~~~~"),
        ("````", "```` \t "),
    ],
)
def test_nothing_inside_a_fence_is_recognised(opener: str, closer: str) -> None:
    scan = scan_page(fenced(opener, closer, *EXAMPLE), page=PAGE)
    assert scan.problems == ()
    assert scan.regions == ()
    first, second = scan.directives
    assert (first.open_line, second.open_line) == (1, 9 + len(EXAMPLE))


@pytest.mark.parametrize(
    ("opener", "not_a_close"),
    [
        ("```", "~~~"),
        ("```", "``"),
        ("```", "``` text"),
        ("```", "    ```"),
        ("````", "```"),
        ("~~~", "```"),
        ("~~~", "~~"),
        ("~~~", "~~~ text"),
        ("~~~", "    ~~~"),
        ("~~~~", "~~~"),
    ],
)
def test_a_fence_stays_open_through_a_line_that_does_not_close_it(
    opener: str, not_a_close: str
) -> None:
    lines = [not_a_close, *EXAMPLE]
    scan = scan_page(fenced(opener, opener, *lines), page=PAGE)
    assert numbers(scan) == [1, 9 + len(lines)]
    assert scan.problems == () and scan.regions == ()


@pytest.mark.parametrize(
    "not_a_fence",
    ["    ```", "\t```", "    ~~~", "``", "~~", "``` has `tick", "text ```"],
)
def test_a_line_that_is_not_a_fence_opener_hides_nothing(not_a_fence: str) -> None:
    text = page_text(chart("first"), not_a_fence, chart("second"))
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1, 8]
    assert scan.problems == ()


def test_an_unclosed_fence_hides_a_later_directive_to_the_end_of_the_page() -> None:
    text = page_text(
        chart("first"), "```", "prose", chart("second"), region_block("second")
    )
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1]
    assert scan.regions == () and scan.problems == ()


def test_the_scan_leaves_a_fence_at_its_close_and_sees_the_next_chart() -> None:
    text = page_text(
        chart("first"),
        "```",
        "<!-- fitdocs:chart",
        "```",
        "~~~",
        "<!-- fitdocs:begin:chart:x -->",
        "~~~",
        chart("second"),
    )
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1, 13]


@pytest.mark.parametrize("fence", ["```", "~~~", "  ```", "````python"])
def test_a_fence_line_inside_a_directive_body_is_body_text(fence: str) -> None:
    text = page_text(
        chart("first"), "<!-- fitdocs:chart", "sql: |", fence, "-->", chart("third")
    )
    scan = scan_page(text, page=PAGE)
    assert [(d.open_line, d.close_line) for d in scan.directives] == [
        (1, 6),
        (7, 10),
        (11, 16),
    ]
    assert scan.directives[1].body == f"sql: |\n{fence}"


# -- regions (5.1, 5.7) ---


def test_a_closed_region_is_found_with_its_body_lines() -> None:
    text = page_text(
        chart("first"),
        region_block("first", "line a\n\nline b"),
        chart("second"),
        region_block("second", "![t](assets/weekly/second.svg)\n"),
    )
    scan = scan_page(text, page=PAGE)
    assert scan.problems == ()
    first, second = scan.regions
    assert (first.chart_id, first.begin_line, first.end_line) == ("first", 7, 11)
    assert [line.text for line in first.body] == ["line a", "", "line b"]
    assert [line.number for line in first.body] == [8, 9, 10]
    assert first.intruder_line is None
    assert (second.chart_id, second.begin_line, second.end_line) == ("second", 18, 21)
    assert [line.text for line in second.body] == [
        "![t](assets/weekly/second.svg)",
        "",
    ]
    assert second.intruder_line is None


def test_a_reference_line_is_allowed_inside_a_region() -> None:
    ref = "<!-- fitdocs:snapshot assets/weekly/second.snapshot-3.json -->"
    text = page_text(
        chart("first"),
        region_block("first"),
        chart("second"),
        region_block("second", f"{ref}\n![t](a.svg)"),
    )
    second = scan_page(text, page=PAGE).regions[1]
    assert second.end_line is not None and second.intruder_line is None
    assert [line.text for line in second.body] == [ref, "![t](a.svg)"]


@pytest.mark.parametrize(
    "lookalike",
    [
        "<!-- fitdocs:snapshot assets/weekly/second.snapshot-03.json -->",
        "<!-- fitdocs:snapshot ../assets/weekly/second.snapshot-3.json -->",
        "<!-- fitdocs:snapshot assets/weekly/second.snapshot-3.json --> x",
    ],
)
def test_a_snapshot_lookalike_is_not_a_reference_line(lookalike: str) -> None:
    text = page_text(
        chart("first"),
        region_block("first"),
        chart("second"),
        region_block("second", lookalike),
    )
    second = scan_page(text, page=PAGE).regions[1]
    assert second.end_line is None
    assert second.intruder_line == 16


def test_a_region_with_an_opener_after_it_is_unclosed_and_the_directive_stands() -> (
    None
):
    text = page_text(
        chart("first"),
        region_block("first", "stale", closed=False),  # 7-8
        chart("second"),  # 9-14
        region_block("second"),
    )
    scan = scan_page(text, page=PAGE)
    first, second = scan.regions
    assert (first.begin_line, first.end_line, first.intruder_line) == (7, None, 9)
    assert [line.text for line in first.body] == ["stale"]
    assert (second.begin_line, second.end_line) == (15, 16)
    assert numbers(scan) == [1, 9]
    assert scan.problems == ()


def test_an_intruding_begin_marker_unseats_the_open_region() -> None:
    text = page_text(
        chart("first"),
        region_block("first", closed=False),  # 7
        region_block("second", "body"),  # 8-10
    )
    scan = scan_page(text, page=PAGE)
    first, second = scan.regions
    assert (first.chart_id, first.end_line, first.intruder_line) == ("first", None, 8)
    assert first.body == ()
    assert (second.chart_id, second.begin_line, second.end_line) == ("second", 8, 10)
    assert second.intruder_line is None


def test_a_region_at_the_end_of_the_page_is_unclosed_without_an_intruder() -> None:
    text = page_text(chart("first"), region_block("first", "a\nb", closed=False))
    region = scan_page(text, page=PAGE).regions[0]
    assert region.end_line is None and region.intruder_line is None
    assert [line.text for line in region.body] == ["a", "b"]


def test_a_fenced_example_after_an_unclosed_region_is_not_live() -> None:
    text = page_text(
        chart("a"),
        "<!-- fitdocs:begin:chart:a -->",  # 7: never closed
        "My own prose paragraph",
        "```markdown",  # 9
        chart("example"),  # 10-15
        region_block("example", "![x](x.svg)"),  # 16-18
        "```",  # 19
        chart("real"),  # 20-25
    )
    scan = scan_page(text, page=PAGE)
    assert numbers(scan) == [1, 20]  # no live `example` directive
    (region,) = scan.regions  # no region inside the fence
    assert (region.chart_id, region.begin_line) == ("a", 7)
    assert (region.end_line, region.intruder_line) == (None, 20)
    assert [line.number for line in region.body] == list(range(8, 20))
    assert scan.problems == ()


def test_a_fenced_end_marker_does_not_close_a_region() -> None:
    text = page_text(
        chart("a"),
        "<!-- fitdocs:begin:chart:a -->",  # 7
        "My own prose paragraph",
        "```",
        "<!-- fitdocs:end:chart:a -->",  # 10, fenced
        "```",
    )
    scan = scan_page(text, page=PAGE)
    (region,) = scan.regions
    assert (region.end_line, region.intruder_line) == (None, None)
    assert [line.number for line in region.body] == [8, 9, 10, 11]
    assert scan.problems == ()


def test_a_region_fence_left_open_runs_the_region_to_the_end_of_the_page() -> None:
    text = page_text(
        chart("a"),
        "<!-- fitdocs:begin:chart:a -->",
        "~~~",
        chart("hidden"),
        "<!-- fitdocs:end:chart:a -->",
    )
    scan = scan_page(text, page=PAGE)
    (region,) = scan.regions
    assert (region.end_line, region.intruder_line) == (None, None)
    assert numbers(scan) == [1]


def test_a_region_fence_closes_and_the_end_marker_after_it_closes_the_region() -> None:
    text = page_text(
        chart("a"),
        "<!-- fitdocs:begin:chart:a -->",
        "````",
        "<!-- fitdocs:chart",
        "```",
        "<!-- fitdocs:begin:chart:b -->",
        "````",
        "<!-- fitdocs:end:chart:a -->",  # 13
    )
    (region,) = scan_page(text, page=PAGE).regions
    assert (region.end_line, region.intruder_line) == (13, None)


def test_an_end_marker_for_another_id_does_not_close_the_region() -> None:
    text = page_text(
        chart("first"), region_block("first", closed=False), end_marker("other")
    )
    scan = scan_page(text, page=PAGE)
    region = scan.regions[0]
    assert (region.end_line, region.intruder_line) == (None, 8)
    assert codes(scan) == [(DashboardCode.MARKER_MALFORMED.value, 8)]


def test_an_indented_opener_inside_a_region_is_body_text() -> None:
    text = page_text(
        chart("first"), region_block("first", "  <!-- fitdocs:chart\ntext")
    )
    scan = scan_page(text, page=PAGE)
    region = scan.regions[0]
    assert region.end_line == 10 and region.intruder_line is None
    assert scan.problems == ()


@pytest.mark.parametrize(
    "marker",
    [
        "<!-- fitdocs:end:chart:orphan -->",
        "<!-- fitdocs:begin:chart:Bad_Id -->",
        "<!-- fitdocs:end:chart:Bad_Id -->",
        "<!-- fitdocs:begin:chart: -->",
        "<!-- fitdocs:begin:chart:a--b -->",
        " <!-- fitdocs:begin:chart:ok -->",
        "<!-- fitdocs:begin:chart:ok --> ",
        "<!--fitdocs:begin:chart:ok -->",
        "<!-- fitdocs:begin:chart:ok",
        "x <!-- fitdocs:end:chart:ok -->",
    ],
)
def test_a_malformed_or_orphan_marker_is_reported_and_opens_no_region(
    marker: str,
) -> None:
    text = page_text(chart("first"), region_block("first"), marker)
    scan = scan_page(text, page=PAGE)
    assert len(scan.regions) == 1
    assert codes(scan) == [(DashboardCode.MARKER_MALFORMED.value, 9)]
    assert "9" in scan.problems[0].message


def test_an_end_marker_without_a_region_is_named_as_such() -> None:
    text = page_text(
        chart("first"),
        region_block("first"),
        end_marker("orphan"),
        "<!-- fitdocs:end:chart:Bad_Id -->",
    )
    orphan, invalid = scan_page(text, page=PAGE).problems
    assert (orphan.line, invalid.line) == (9, 10)
    assert "no open region" in orphan.message
    assert "no open region" not in invalid.message


def test_markers_inside_a_fence_are_not_reported() -> None:
    text = page_text(
        chart("first"),
        "```",
        "<!-- fitdocs:end:chart:orphan -->",
        "<!-- fitdocs:begin:chart:Bad_Id -->",
        "```",
    )
    assert scan_page(text, page=PAGE).problems == ()


# -- the region below a directive (5.1) ---


def test_following_region_skips_only_blank_lines() -> None:
    text = page_text(
        chart("first"),
        "",
        "  \t",
        "",
        region_block("first", "x"),
        chart("second"),
        region_block("second", "y"),
    )
    scan = scan_page(text, page=PAGE)
    first, second = scan.directives
    below_first = following_region(scan, first)
    below_second = following_region(scan, second)
    assert below_first is not None and below_first.chart_id == "first"
    assert below_first.begin_line == 10
    assert below_second is not None and below_second.chart_id == "second"
    assert below_second.begin_line == 19


def test_following_region_is_none_when_prose_intervenes() -> None:
    text = page_text(
        chart("first"),
        region_block("first"),
        chart("second"),
        "",
        "prose",
        region_block("second"),
        chart("third"),
        "<!-- a comment -->",
        region_block("third"),
    )
    scan = scan_page(text, page=PAGE)
    assert len(scan.regions) == 3
    _first, second, third = scan.directives
    assert following_region(scan, second) is None
    assert following_region(scan, third) is None


def test_following_region_is_none_without_a_region_or_a_closer() -> None:
    text = page_text(chart("first"), chart("second"), "")
    scan = scan_page(text, page=PAGE)
    assert [following_region(scan, each) for each in scan.directives] == [None, None]
    unclosed = scan_page(page_text("<!-- fitdocs:chart", "x"), page=PAGE)
    assert unclosed.directives[0].close_line is None
    assert following_region(unclosed, unclosed.directives[0]) is None


def test_following_region_returns_an_unclosed_region() -> None:
    text = page_text(chart("first"), region_block("first", "stale", closed=False))
    scan = scan_page(text, page=PAGE)
    region = following_region(scan, scan.directives[0])
    assert region is not None and region.end_line is None
