"""Region bodies: composing, classifying and splicing into a page."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from fitdocs.contract import GENERATED_PREFIX
from fitdocs.dashboards.grammar import (
    Line,
    begin_marker,
    end_marker,
    following_region,
    scan_page,
    split_lines,
)
from fitdocs.dashboards.region import (
    NOTE_RE,
    BodyState,
    ChartBody,
    RegionEdit,
    apply_edits,
    caption,
    chart_body,
    classify_body,
    note_body,
    recorded_snapshot,
)
from fitdocs.render.charts.kit import (
    ChartData,
    ChartRequest,
    Column,
    Output,
    RenderedChart,
    ValueKind,
    render_chart,
)
from tests.dashboards._helpers import (
    category_column,
    chart_data,
    date_column,
    directive_block,
    number_column,
    page_text,
    region_block,
)

PAGE = "weekly"
CHART = "load-trend"
IMAGE = f"![Load trend](assets/{PAGE}/{CHART}.svg)"
SNAPSHOT = f"assets/{PAGE}/{CHART}.snapshot-12.json"
REFERENCE = f"<!-- fitdocs:snapshot {SNAPSHOT} -->"

SVG = RenderedChart("bar", Output.SVG, "<svg>NOT-IN-THE-BODY</svg>")
STAT = RenderedChart("stat", Output.MARKDOWN, "**Form:** 4.5\nsecond kit line")
ROWS = RenderedChart("table", Output.MARKDOWN, "| a | b |\n| --- | --- |\n| 1 | 2 |")


def body(
    *,
    title: str = "Load trend",
    rendered: RenderedChart = SVG,
    caption_text: str | None = None,
    rows_table: RenderedChart | None = None,
    snapshot_path: str | None = None,
) -> tuple[str, ...]:
    return chart_body(
        page=PAGE,
        chart_id=CHART,
        title=title,
        rendered=rendered,
        caption=caption_text,
        rows_table=rows_table,
        snapshot_path=snapshot_path,
    ).lines


def as_lines(*texts: str) -> list[Line]:
    return [Line(number, text, "\n") for number, text in enumerate(texts, start=1)]


# -- chart_body: the lines of a region (5.4, 5.5, 5.6, 10.3) ---


def test_svg_chart_body_is_one_image_link_and_a_blank_line() -> None:
    assert body() == (IMAGE, "")


def test_svg_chart_body_names_the_page_and_chart_in_the_asset_path() -> None:
    lines = chart_body(
        page="monthly",
        chart_id="sleep",
        title="T",
        rendered=SVG,
        caption=None,
        rows_table=None,
        snapshot_path=None,
    ).lines
    assert lines == ("![T](assets/monthly/sleep.svg)", "")


def test_markdown_chart_body_is_the_kits_lines_and_not_an_image() -> None:
    assert body(rendered=STAT) == ("**Form:** 4.5", "second kit line", "")


def test_markdown_chart_body_from_the_real_stat_kind() -> None:
    data = chart_data((category_column("label"), number_column("value")), [("a", 4.5)])
    rendered = render_chart(
        ChartRequest(ref="c1", kind="stat", title="Form", channels={"value": "value"}),
        data,
    )
    assert rendered.output is Output.MARKDOWN
    assert rendered.text == "**Form:** 4.5"
    assert body(rendered=rendered) == ("**Form:** 4.5", "")


def test_caption_follows_the_chart_after_a_blank_line() -> None:
    assert body(caption_text="*through 2026-03-01*") == (
        IMAGE,
        "",
        "*through 2026-03-01*",
        "",
    )


def test_rows_table_follows_the_chart_and_the_caption() -> None:
    assert body(caption_text="*cap*", rows_table=ROWS) == (
        IMAGE,
        "",
        "*cap*",
        "",
        "| a | b |",
        "| --- | --- |",
        "| 1 | 2 |",
        "",
    )


def test_rows_table_without_a_caption_has_no_doubled_blank_line() -> None:
    assert body(rendered=STAT, rows_table=ROWS) == (
        "**Form:** 4.5",
        "second kit line",
        "",
        "| a | b |",
        "| --- | --- |",
        "| 1 | 2 |",
        "",
    )


def test_a_frozen_chart_starts_with_its_reference_line() -> None:
    assert body(
        caption_text="*Snapshot 2026-03-04*", rows_table=ROWS, snapshot_path=SNAPSHOT
    ) == (
        REFERENCE,
        "",
        IMAGE,
        "",
        "*Snapshot 2026-03-04*",
        "",
        "| a | b |",
        "| --- | --- |",
        "| 1 | 2 |",
        "",
    )


def test_a_relative_chart_has_no_reference_line() -> None:
    assert not any("fitdocs:snapshot" in line for line in body(rendered=STAT))


def test_title_is_escaped_and_cleaned_in_the_alt_text() -> None:
    title = "a[b]c*d_e\\f\x01g\nh"
    assert body(title=title)[0] == (
        "![a\\[b\\]c\\*d\\_e\\\\f\ufffdg h](assets/weekly/load-trend.svg)"
    )


def test_a_title_that_looks_like_a_marker_stays_inside_the_image_text() -> None:
    lines = body(title="<!-- fitdocs:generated: x -->")
    assert lines[0].startswith("![\\<!-- fitdocs:generated")
    assert not any(line.startswith(GENERATED_PREFIX) for line in lines)


@pytest.mark.parametrize(
    "path",
    [
        f"assets/{PAGE}/{CHART}.snapshot-0.json",
        f"assets/{PAGE}/{CHART}.snapshot-12.json -->\nmore",
        f"assets/Weekly/{CHART}.snapshot-12.json",
        f"{CHART}.snapshot-12.json",
        "",
    ],
)
def test_a_snapshot_path_the_grammar_cannot_read_back_is_refused(path: str) -> None:
    with pytest.raises(ValueError, match="snapshot path"):
        body(snapshot_path=path)


def test_a_rows_table_must_be_markdown() -> None:
    with pytest.raises(ValueError, match="markdown"):
        body(rows_table=SVG)


@pytest.mark.parametrize(
    "line",
    [
        f"{GENERATED_PREFIX}: x -->",
        end_marker(CHART),
        begin_marker("other"),
        "<!-- fitdocs:snapshot assets/a/b.snapshot-1.json -->",
    ],
)
def test_a_kit_line_that_starts_like_a_marker_is_refused(line: str) -> None:
    hostile = RenderedChart("stat", Output.MARKDOWN, f"first\n{line}\nlast")
    with pytest.raises(ValueError, match="marker"):
        body(rendered=hostile)
    with pytest.raises(ValueError, match="marker"):
        body(rows_table=RenderedChart("table", Output.MARKDOWN, f"| a |\n{line}"))


def test_a_marker_that_does_not_start_the_line_is_not_refused() -> None:
    kept = (
        "see <!-- fitdocs:end:chart:x -->",
        f" {GENERATED_PREFIX}",
        "<!-- other -->",
    )
    rendered = RenderedChart("stat", Output.MARKDOWN, "\n".join(kept))
    assert body(rendered=rendered) == (*kept, "")


# -- caption (5.5, 9.3, 9.4) ---


def days(*pairs: tuple[date | None, date | None]) -> ChartData:
    return chart_data(
        (date_column("start"), date_column("finish")), [list(pair) for pair in pairs]
    )


def test_through_is_the_latest_date_over_every_date_column() -> None:
    data = days(
        (date(2026, 3, 1), date(2026, 4, 10)),
        (date(2026, 3, 15), date(2026, 2, 1)),
        (date(2026, 1, 9), date(2026, 3, 2)),
    )
    assert caption(data, window=None, snapshot_date=None) == "*through 2026-04-10*"


def test_through_skips_absent_values_and_other_column_kinds() -> None:
    data = chart_data(
        (
            category_column("label"),
            date_column("day"),
            number_column("n"),
            Column("other", ValueKind.DATE),
        ),
        [
            ("2099-12-31", None, 20991231, None),
            ("2099-12-30", date(2026, 3, 9), 20991230, None),
            ("2099-12-29", None, 20991229, date(2026, 3, 5)),
        ],
    )
    assert caption(data, window=None, snapshot_date=None) == "*through 2026-03-09*"


def test_through_takes_the_date_part_of_a_datetime() -> None:
    data = chart_data(
        (Column("when", ValueKind.DATETIME), date_column("day")),
        [
            (datetime(2026, 5, 2, 23, 59, 58), date(2026, 5, 1)),
            (datetime(2026, 5, 1, 1, 2, 3), None),
        ],
    )
    assert caption(data, window=None, snapshot_date=None) == "*through 2026-05-02*"


def test_through_of_a_lone_datetime_column_is_a_date() -> None:
    data = chart_data(
        (Column("when", ValueKind.DATETIME),),
        [[datetime(2026, 1, 3, 4, 5, 6)], [datetime(2026, 1, 2, 22, 0, 0)]],
    )
    assert caption(data, window=None, snapshot_date=None) == "*through 2026-01-03*"


def test_no_rows_is_stated_even_with_date_columns() -> None:
    assert caption(days(), window=None, snapshot_date=None) == "*no rows*"


def test_no_rows_in_a_data_set_without_date_columns() -> None:
    data = chart_data((category_column("label"),), [])
    assert caption(data, window=None, snapshot_date=None) == "*no rows*"


def test_no_caption_when_no_part_applies() -> None:
    data = chart_data((category_column("label"), number_column("n")), [("a", 1.0)])
    assert caption(data, window=None, snapshot_date=None) is None


def test_no_caption_when_every_date_is_absent() -> None:
    assert (
        caption(days((None, None), (None, None)), window=None, snapshot_date=None)
        is None
    )


def test_the_parts_come_in_order_joined_by_a_middle_dot() -> None:
    data = days((date(2026, 2, 1), date(2026, 2, 8)), (date(2026, 1, 1), None))
    assert caption(data, window="last 12 weeks", snapshot_date=date(2026, 3, 4)) == (
        "*Snapshot 2026-03-04 · last 12 weeks · through 2026-02-08*"
    )


def test_snapshot_and_window_alone() -> None:
    data = chart_data((category_column("label"),), [("a",)])
    assert caption(data, window="W", snapshot_date=date(2026, 3, 4)) == (
        "*Snapshot 2026-03-04 · W*"
    )


def test_a_frozen_chart_with_no_rows_states_the_snapshot_window_and_no_rows() -> None:
    assert caption(days(), window="last 12 weeks", snapshot_date=date(2026, 3, 4)) == (
        "*Snapshot 2026-03-04 · last 12 weeks · no rows*"
    )


def test_a_frozen_chart_with_no_rows_and_no_window() -> None:
    assert caption(days(), window=None, snapshot_date=date(2026, 3, 4)) == (
        "*Snapshot 2026-03-04 · no rows*"
    )


def test_window_and_no_rows() -> None:
    assert caption(days(), window="last 12 weeks", snapshot_date=None) == (
        "*last 12 weeks · no rows*"
    )


def test_snapshot_date_is_zero_padded() -> None:
    data = chart_data((category_column("label"),), [("a",)])
    assert caption(data, window=None, snapshot_date=date(2026, 3, 4)) == (
        "*Snapshot 2026-03-04*"
    )


@pytest.mark.parametrize("window", ["", "   ", " \t\n "])
def test_an_empty_or_blank_window_states_nothing(window: str) -> None:
    data = days((date(2026, 2, 8), None))
    assert caption(data, window=window, snapshot_date=None) == "*through 2026-02-08*"


def test_window_is_escaped() -> None:
    data = chart_data((category_column("label"),), [("a",)])
    assert caption(data, window="a]b*c_d\\e", snapshot_date=None) == (
        "*a\\]b\\*c\\_d\\\\e*"
    )


def test_window_control_characters_are_cleaned() -> None:
    data = chart_data((category_column("label"),), [("a",)])
    assert caption(data, window="x\x01y\tz\nw", snapshot_date=None) == (
        "*x\ufffdy z w*"
    )


# -- note_body and NOTE_RE (12.3) ---


def test_note_body_is_one_italic_line_and_a_blank_line() -> None:
    assert note_body("the index is not built").lines == (
        "*Not rendered: the index is not built*",
        "",
    )


def test_note_message_is_escaped_and_cleaned() -> None:
    assert note_body("bad ]x*y_z\\ \x02 q\nr").lines[0] == (
        "*Not rendered: bad \\]x\\*y\\_z\\\\ \ufffd q r*"
    )


def test_a_note_body_line_matches_the_note_pattern() -> None:
    assert NOTE_RE.fullmatch(note_body("a\\b *c*").lines[0]) is not None


@pytest.mark.parametrize(
    "text",
    [
        "*Not rendered x*",
        "*Not rendered:x*",
        "Not rendered: x*",
        "*Not rendered: x",
        "*Not rendered: x* tail",
        " *Not rendered: x*",
        "*not rendered: x*",
        "*Not rendered: x*\n",
    ],
)
def test_the_note_pattern_refuses_look_alikes(text: str) -> None:
    assert NOTE_RE.fullmatch(text) is None


def test_the_note_pattern_accepts_an_empty_message() -> None:
    assert NOTE_RE.fullmatch("*Not rendered: *") is not None


# -- classify_body and recorded_snapshot (5.3, 12.3, 10.3) ---


def test_an_empty_or_blank_body_is_empty() -> None:
    assert classify_body([]) is BodyState.EMPTY
    assert classify_body(as_lines("", "   ", "\t")) is BodyState.EMPTY


def test_a_note_is_a_note_whatever_blank_lines_surround_it() -> None:
    assert classify_body(as_lines(*note_body("m").lines)) is BodyState.NOTE
    assert classify_body(as_lines("", " ", "*Not rendered: m*", "")) is BodyState.NOTE


def test_a_rendered_chart_is_rendered() -> None:
    assert classify_body(as_lines(*body())) is BodyState.RENDERED
    assert classify_body(as_lines(*body(rendered=STAT))) is BodyState.RENDERED


@pytest.mark.parametrize(
    "texts",
    [
        ("*Not rendered: m* and more",),
        ("*Not rendered: m*", "*Not rendered: n*"),
        ("*Not rendered: m*", "", "text"),
        ("text", "", "*Not rendered: m*"),
        (" *Not rendered: m*",),
        ("some prose",),
        (REFERENCE,),
    ],
)
def test_anything_else_is_rendered(texts: tuple[str, ...]) -> None:
    assert classify_body(as_lines(*texts)) is BodyState.RENDERED


def test_the_recorded_snapshot_is_the_reference_path() -> None:
    assert recorded_snapshot(as_lines(*body(snapshot_path=SNAPSHOT))) == SNAPSHOT


def test_a_body_without_a_reference_records_none() -> None:
    assert recorded_snapshot(as_lines(*body(rendered=STAT))) is None
    assert recorded_snapshot([]) is None
    assert recorded_snapshot(as_lines(*note_body("m").lines)) is None


def test_the_first_reference_line_wins_wherever_it_sits() -> None:
    other = f"<!-- fitdocs:snapshot assets/{PAGE}/{CHART}.snapshot-3.json -->"
    lines = as_lines("text", "", REFERENCE, other)
    assert recorded_snapshot(lines) == SNAPSHOT
    assert recorded_snapshot(as_lines(other, REFERENCE)) == other.split()[2]


@pytest.mark.parametrize(
    "text",
    [
        f" {REFERENCE}",
        f"{REFERENCE} ",
        f"text {REFERENCE}",
        f"<!-- fitdocs:snapshot assets/{PAGE}/{CHART}.snapshot-0.json -->",
        f"<!-- fitdocs:snapshot assets/Weekly/{CHART}.snapshot-1.json -->",
        f"<!-- fitdocs:snapshot  {SNAPSHOT} -->",
    ],
)
def test_a_line_that_is_not_exactly_a_reference_records_none(text: str) -> None:
    assert recorded_snapshot(as_lines("x", text)) is None


# -- apply_edits (2.1, 2.2, 5.2, 5.3, 16.5) ---

NEW = ChartBody(("new one", "", "new three", ""))


def directive(chart_id: str, *, ending: str = "\n") -> str:
    return directive_block(
        [("id", chart_id), ("kind", "bar"), ("sql", "|\n  select 1")], ending=ending
    )


def new_region(chart_id: str, ending: str) -> str:
    """The region ``NEW`` is written as, every line ending as given."""
    lines = [
        begin_marker(chart_id),
        "new one",
        "",
        "new three",
        "",
        end_marker(chart_id),
    ]
    return "".join(line + ending for line in lines)


def insert(chart_id: str, lines_: list[Line], new: ChartBody = NEW) -> RegionEdit:
    scan = scan_page("".join(line.text + line.ending for line in lines_), page=PAGE)
    block = next(
        each
        for each in scan.directives
        if each.body is not None and f"id: {chart_id}" in each.body
    )
    assert block.close_line is not None
    return RegionEdit(chart_id, new, None, block.close_line)


def replace(chart_id: str, lines_: list[Line], new: ChartBody = NEW) -> RegionEdit:
    scan = scan_page("".join(line.text + line.ending for line in lines_), page=PAGE)
    block = next(each for each in scan.regions if each.chart_id == chart_id)
    close = next(
        each
        for each in scan.directives
        if each.body is not None and f"id: {chart_id}" in each.body
    )
    assert close.close_line is not None
    return RegionEdit(chart_id, new, block, close.close_line)


def test_a_missing_region_is_inserted_after_the_closing_line() -> None:
    text = page_text(
        "# Title",
        directive("first") + region_block("first", "kept\n"),
        directive("second"),
        "after",
    )
    lines = list(split_lines(text))
    assert apply_edits(lines, [insert("second", lines)]) == page_text(
        "# Title",
        directive("first") + region_block("first", "kept\n"),
        directive("second") + new_region("second", "\n"),
        "after",
    )


def test_inserted_lines_take_the_closing_lines_crlf() -> None:
    text = page_text("# T", directive("a", ending="\r\n"), "tail", ending="\r\n")
    lines = list(split_lines(text))
    out = apply_edits(lines, [insert("a", lines)])
    assert out == page_text(
        "# T",
        directive("a", ending="\r\n") + new_region("a", "\r\n"),
        "tail",
        ending="\r\n",
    )
    assert out.count("\n") == out.count("\r\n")


def test_the_ending_comes_from_the_closer_not_from_the_page() -> None:
    crlf_closer = directive("a", ending="\r\n")
    text = "first line\n" + crlf_closer + "tail\n"
    lines = list(split_lines(text))
    out = apply_edits(lines, [insert("a", lines)])
    assert out == ("first line\n" + crlf_closer + new_region("a", "\r\n") + "tail\n")
    lf_closer = directive("b", ending="\n")
    text = "first line\r\n" + lf_closer + "tail\r\n"
    lines = list(split_lines(text))
    out = apply_edits(lines, [insert("b", lines)])
    assert out == ("first line\r\n" + lf_closer + new_region("b", "\n") + "tail\r\n")


def test_a_final_closer_without_an_ending_gets_one_and_the_lines_use_lf() -> None:
    text = "# T\n" + directive("a").removesuffix("\n")
    lines = list(split_lines(text))
    assert lines[-1].ending == ""
    out = apply_edits(lines, [insert("a", lines)])
    assert out == ("# T\n" + directive("a") + new_region("a", "\n"))


def test_a_final_closer_without_an_ending_on_a_crlf_page_still_uses_lf() -> None:
    text = "# T\r\n" + directive("a", ending="\r\n").removesuffix("\r\n")
    lines = list(split_lines(text))
    assert lines[-1].ending == ""
    out = apply_edits(lines, [insert("a", lines)])
    assert out == (
        "# T\r\n"
        + directive("a", ending="\r\n").removesuffix("\r\n")
        + "\n"
        + new_region("a", "\n")
    )


def test_two_regions_are_replaced_in_one_page_and_nothing_else_moves() -> None:
    prose = "Prose with trailing spaces   \n\n\tTabbed line\n"
    text = (
        "\ufeff# Heading\r\n"
        + prose
        + directive("a")
        + region_block("a", "old a1\nold a2\nold a3\n")
        + "between *prose*\n"
        + directive("c")
        + region_block("c", "keep c\n")
        + directive("b", ending="\r\n")
        + region_block("b", "old b\n", ending="\n")
        + "last prose without ending"
    )
    lines = list(split_lines(text))
    first = ChartBody(("A1", "", "A2", ""))
    second = ChartBody(("B1", ""))
    out = apply_edits(lines, [replace("b", lines, second), replace("a", lines, first)])
    assert out == (
        "\ufeff# Heading\r\n"
        + prose
        + directive("a")
        + f"{begin_marker('a')}\nA1\n\nA2\n\n{end_marker('a')}\n"
        + "between *prose*\n"
        + directive("c")
        + region_block("c", "keep c\n")
        + directive("b", ending="\r\n")
        + f"{begin_marker('b')}\n"
        + "B1\r\n\r\n"
        + f"{end_marker('b')}\n"
        + "last prose without ending"
    )


def test_replacing_an_empty_region_fills_it() -> None:
    text = directive("a") + region_block("a")
    lines = list(split_lines(text))
    assert apply_edits(lines, [replace("a", lines)]) == (
        directive("a") + new_region("a", "\n")
    )


def test_an_insert_and_a_replace_in_one_call() -> None:
    text = (
        "intro\n"
        + directive("a")
        + region_block("a", "old\n")
        + "mid\n"
        + directive("b")
        + "end\n"
    )
    lines = list(split_lines(text))
    out = apply_edits(
        lines,
        [insert("b", lines, ChartBody(("B", ""))), replace("a", lines)],
    )
    assert out == (
        "intro\n"
        + directive("a")
        + new_region("a", "\n")
        + "mid\n"
        + directive("b")
        + f"{begin_marker('b')}\nB\n\n{end_marker('b')}\n"
        + "end\n"
    )


def test_a_leading_bom_survives_an_insert() -> None:
    text = "\ufeff" + directive("a") + "tail\n"
    lines = list(split_lines(text))
    out = apply_edits(lines, [insert("a", lines)])
    assert out.startswith("\ufeff<!-- fitdocs:chart\n")
    assert out == ("\ufeff" + directive("a") + new_region("a", "\n") + "tail\n")


def test_no_edits_returns_the_page_bytes() -> None:
    text = "\ufeffone\r\ntwo\nthree"
    assert apply_edits(split_lines(text), []) == text


def test_the_result_scans_back_to_the_body_that_was_written() -> None:
    chart = body(caption_text="*cap*", snapshot_path=SNAPSHOT)
    text = "# T\n" + directive(CHART) + "tail\n"
    lines = list(split_lines(text))
    out = apply_edits(lines, [insert(CHART, lines, ChartBody(chart))])
    scan = scan_page(out, page=PAGE)
    assert scan.problems == ()
    region = following_region(scan, scan.directives[0])
    assert region is not None
    assert tuple(line.text for line in region.body) == chart
    assert classify_body(region.body) is BodyState.RENDERED
    assert recorded_snapshot(region.body) == SNAPSHOT


def test_no_emitted_line_starts_with_the_generated_prefix() -> None:
    hostile = body(
        title=f"{GENERATED_PREFIX}: banner",
        caption_text=caption(
            days((date(2026, 1, 1), None)),
            window=f"{GENERATED_PREFIX}: window",
            snapshot_date=None,
        ),
        snapshot_path=SNAPSHOT,
    )
    text = directive("a") + directive("b") + "tail\n"
    lines = list(split_lines(text))
    out = apply_edits(
        lines,
        [insert("a", lines, ChartBody(hostile)), insert("b", lines, note_body("m"))],
    )
    assert len(hostile) == 6
    assert all(not line.startswith(GENERATED_PREFIX) for line in out.split("\n"))
    note = note_body(f"{GENERATED_PREFIX}: note")
    assert not any(line.startswith(GENERATED_PREFIX) for line in note.lines)


def test_an_edit_whose_closing_line_is_off_the_page_is_refused() -> None:
    lines = list(split_lines("a\nb\n"))
    for after in (0, 3):
        with pytest.raises(ValueError, match="closing line"):
            apply_edits(lines, [RegionEdit("a", NEW, None, after)])


def test_an_unclosed_region_cannot_be_replaced() -> None:
    text = directive("a") + region_block("a", "old\n", closed=False)
    lines = list(split_lines(text))
    scan = scan_page(text, page=PAGE)
    assert scan.regions[0].end_line is None
    edit = RegionEdit("a", NEW, scan.regions[0], scan.directives[0].close_line or 0)
    with pytest.raises(ValueError, match="unclosed"):
        apply_edits(lines, [edit])


def test_an_edit_cannot_replace_the_region_of_another_chart() -> None:
    text = directive("a") + region_block("a", "old\n") + directive("b")
    lines = list(split_lines(text))
    scan = scan_page(text, page=PAGE)
    edit = RegionEdit("b", NEW, scan.regions[0], scan.directives[1].close_line or 0)
    with pytest.raises(ValueError, match="another chart"):
        apply_edits(lines, [edit])


def test_edits_that_touch_the_same_lines_are_refused() -> None:
    text = directive("a") + region_block("a", "old\n")
    lines = list(split_lines(text))
    with pytest.raises(ValueError, match="same lines"):
        apply_edits(lines, [insert("a", lines), insert("a", lines)])
    with pytest.raises(ValueError, match="same lines"):
        apply_edits(lines, [replace("a", lines), replace("a", lines)])
    scan = scan_page(text, page=PAGE)
    inside = RegionEdit("x", NEW, None, scan.regions[0].begin_line)
    with pytest.raises(ValueError, match="same lines"):
        apply_edits(lines, [replace("a", lines), inside])
