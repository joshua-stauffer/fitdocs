"""Tests for the kit layout: text measurement, truncation and the frame plan
(chart-kit Req 6.3, 7.3, 7.4).

Constants and the field order of ``Rect``/``LegendEntry``/``FramePlan`` are
pinned against literals, as are the geometry results. The design leaves two
gaps open, the PAD between the title and the legend and the PAD between the
y-axis title and the plot; those are this task's own choices, made so that text
and the plot do not touch (Req 7.3).
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs.render.charts.kit.layout import (
    CHAR_EM,
    FONT_NO_DATA,
    FONT_TEXT,
    FONT_TITLE,
    LEGEND_GAP,
    LEGEND_ITEM_GAP,
    LEGEND_ROW,
    LEGEND_SWATCH,
    NOTE_ROW,
    PAD,
    TICK_GAP,
    TICK_LEN,
    FramePlan,
    LegendEntry,
    Rect,
    fit_text,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.theme import series_style

ELLIPSIS = "…"


def _entry(label: str, index: int = 0, swatch: str = "line") -> LegendEntry:
    return LegendEntry(label, series_style(index), swatch)  # type: ignore[arg-type]


def _plan(**over: object) -> FramePlan:
    args: dict[str, object] = {
        "legend": (),
        "y_label_width": 33.5,
        "x_label_overhang": 10.0,
        "has_x_title": True,
        "has_y_title": True,
        "notes": 2,
    }
    args.update(over)
    return plan_frame(400, 300, **args)  # type: ignore[arg-type]


# ---------------------------------------------------------------- constants


def test_constants_are_the_designed_values() -> None:
    assert CHAR_EM == 0.64
    assert (FONT_TITLE, FONT_TEXT, FONT_NO_DATA) == (13, 11, 13)
    assert (PAD, TICK_LEN, TICK_GAP) == (8.0, 5.0, 3.0)
    assert (LEGEND_ROW, LEGEND_SWATCH, LEGEND_GAP, LEGEND_ITEM_GAP) == (
        18.0,
        20.0,
        4.0,
        14.0,
    )
    assert NOTE_ROW == 15.0


def test_field_orders_and_frozenness() -> None:
    assert [f.name for f in dataclasses.fields(Rect)] == [
        "left",
        "top",
        "width",
        "height",
    ]
    assert [f.name for f in dataclasses.fields(LegendEntry)] == [
        "label",
        "style",
        "swatch",
    ]
    assert [f.name for f in dataclasses.fields(FramePlan)] == [
        "width",
        "height",
        "title_y",
        "legend_rows",
        "legend_top",
        "plot",
        "y_title_y",
        "x_labels_y",
        "x_title_y",
        "notes_y",
    ]
    for cls, args in (
        (Rect, (1.0, 2.0, 3.0, 4.0)),
        (LegendEntry, ("a", series_style(0), "line")),
    ):
        obj = cls(*args)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, dataclasses.fields(cls)[0].name, args[0])
    plan = _plan()
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.width = 1  # type: ignore[misc]


def test_rect_edges() -> None:
    r = Rect(10.5, 20.0, 30.25, 40.0)
    assert r.right == 40.75
    assert r.bottom == 60.0


# ---------------------------------------------------------------- text_width


def test_text_width_is_len_times_font_times_char_em() -> None:
    assert text_width("", 11) == 0.0
    assert text_width("abcde", 11) == pytest.approx(35.2)
    assert text_width("abcdefg", 13) == pytest.approx(58.24)
    assert text_width("ab", 100) == pytest.approx(128.0)


# ---------------------------------------------------------------- fit_text


def test_fit_text_unchanged_at_the_limit() -> None:
    text = "ABCDEFG"
    limit = text_width(text, 11)
    assert fit_text(text, limit, 11) == text
    assert fit_text(text, limit + 50, 11) == text


def test_fit_text_shortened_just_above_the_limit() -> None:
    text = "ABCDEFG"
    # "ABCDEF…" is 7 characters wide, a hair over the limit; the longest prefix
    # that fits is five characters plus "…".
    limit = text_width(text, 11) - 0.01
    assert text_width(text, 11) > limit
    assert fit_text(text, limit, 11) == "ABCDE" + ELLIPSIS


def test_fit_text_prefix_boundary_is_inclusive() -> None:
    text = "ABCDEFGHIJ"
    exact = text_width("ABCD" + ELLIPSIS, 11)
    assert fit_text(text, exact, 11) == "ABCD" + ELLIPSIS
    assert fit_text(text, exact - 0.01, 11) == "ABC" + ELLIPSIS
    assert fit_text(text, exact + 0.01, 11) == "ABCD" + ELLIPSIS


def test_fit_text_tiny_width_keeps_one_character_and_ellipsis() -> None:
    assert fit_text("ABCDEFG", 0.0, 11) == "A" + ELLIPSIS
    assert fit_text("ABCDEFG", 1.0, 11) == "A" + ELLIPSIS
    assert fit_text("ZYX", -5.0, 13) == "Z" + ELLIPSIS


def test_fit_text_font_size_scales_the_measure() -> None:
    assert fit_text("ABCDEFGHIJ", 40.0, 11) == "ABCD" + ELLIPSIS
    assert fit_text("ABCDEFGHIJ", 40.0, 13) == "ABC" + ELLIPSIS


def test_fit_text_empty_string_is_unchanged() -> None:
    assert fit_text("", 0.0, 11) == ""


# ---------------------------------------------------------------- plan_frame


def test_plan_frame_full_stack_geometry() -> None:
    plan = _plan()
    assert plan == FramePlan(
        width=400,
        height=300,
        title_y=21.0,
        legend_rows=(),
        legend_top=29.0,
        plot=Rect(left=49.5, top=48.0, width=334.5, height=179.0),
        y_title_y=40.0,
        x_labels_y=246.0,
        x_title_y=262.0,
        notes_y=(277.0, 292.0),
    )


def test_plan_frame_without_titles_notes_or_legend() -> None:
    plan = _plan(has_x_title=False, has_y_title=False, notes=0)
    assert plan.y_title_y is None
    assert plan.x_title_y is None
    assert plan.notes_y == ()
    assert plan.legend_rows == ()
    assert plan.plot == Rect(left=49.5, top=29.0, width=334.5, height=244.0)
    assert plan.x_labels_y == 292.0


def test_each_axis_title_is_independent() -> None:
    only_x = _plan(has_y_title=False, notes=0)
    assert only_x.y_title_y is None
    assert only_x.x_title_y == 292.0
    assert only_x.plot.top == 29.0
    assert only_x.plot.bottom == 300 - 8 - 16 - 19
    only_y = _plan(has_x_title=False, notes=0)
    assert only_y.x_title_y is None
    assert only_y.y_title_y == 40.0
    assert only_y.plot.top == 48.0
    assert only_y.plot.bottom == 300 - 8 - 19


def test_plot_moves_down_by_legend_row_per_row() -> None:
    base = _plan(legend=())
    one = _plan(legend=(_entry("a"),))
    two = _plan(legend=(_entry("a"), _entry("b", 1)))
    assert (base.plot.top, one.plot.top) == (48.0, 66.0)
    assert one.plot.top - base.plot.top == LEGEND_ROW
    assert len(one.legend_rows) == 1
    assert len(two.legend_rows) == 1
    assert one.plot.bottom == base.plot.bottom
    assert one.plot.height == base.plot.height - LEGEND_ROW
    assert one.legend_top == base.legend_top == 29.0


def test_plot_moves_up_by_note_row_per_note() -> None:
    zero = _plan(notes=0)
    one = _plan(notes=1)
    three = _plan(notes=3)
    assert zero.plot.bottom == 257.0
    assert one.plot.bottom == 242.0
    assert three.plot.bottom == 212.0
    assert zero.plot.bottom - one.plot.bottom == NOTE_ROW
    assert zero.plot.top == one.plot.top == three.plot.top


def test_left_margin_grows_with_the_y_label_width() -> None:
    narrow = _plan(y_label_width=10.0)
    wide = _plan(y_label_width=40.0)
    assert narrow.plot.left == 26.0
    assert wide.plot.left == 56.0
    assert narrow.plot.right == wide.plot.right == 384.0
    zero = _plan(y_label_width=0.0)
    assert zero.plot.left == 16.0


def test_right_margin_is_the_larger_of_16_and_overhang_plus_4() -> None:
    assert _plan(x_label_overhang=5.0).plot.right == 384.0
    assert _plan(x_label_overhang=12.0).plot.right == 384.0
    assert _plan(x_label_overhang=20.0).plot.right == 376.0
    assert _plan(x_label_overhang=0.0).plot.right == 384.0


def test_right_label_width_is_added_to_the_right_margin() -> None:
    assert _plan(right_label_width=12.5).plot.right == 371.5
    assert _plan(x_label_overhang=20.0, right_label_width=12.5).plot.right == 363.5
    assert _plan(right_label_width=0.0).plot.right == 384.0


def test_plan_carries_the_requested_size() -> None:
    plan = plan_frame(
        640,
        360,
        legend=(),
        y_label_width=20.0,
        x_label_overhang=0.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert (plan.width, plan.height) == (640, 360)
    assert plan.plot == Rect(36.0, 29.0, 588.0, 360 - 8 - 19 - 29.0)


# ----------------------------------------------------------------- legend


def test_legend_wrap_boundary_exactly_at_width_minus_pad_stays_on_the_row() -> None:
    # Label lengths 6, 9, 10: each entry is LEGEND_SWATCH + LEGEND_GAP + the
    # label; the third entry ends at exactly 284.0, which is 292 - PAD.
    entries = (_entry("a" * 6, 0), _entry("b" * 9, 1), _entry("c" * 10, 2))
    end = PAD
    for e in entries:
        end = end + (LEGEND_SWATCH + LEGEND_GAP + text_width(e.label, FONT_TEXT))
        end_of_last = end
        end = end + LEGEND_ITEM_GAP
    assert end_of_last == 284.0
    on = plan_frame(
        292,
        300,
        legend=entries,
        y_label_width=20.0,
        x_label_overhang=0.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert on.width - PAD == end_of_last
    assert [[e.label for e, _ in row] for row in on.legend_rows] == [
        ["a" * 6, "b" * 9, "c" * 10]
    ]
    assert [x for _, x in on.legend_rows[0]] == pytest.approx([8.0, 88.24, 189.6])


def test_legend_wrap_one_past_width_minus_pad_wraps() -> None:
    entries = (_entry("a" * 6, 0), _entry("b" * 9, 1), _entry("c" * 10, 2))
    plan = plan_frame(
        291,
        300,
        legend=entries,
        y_label_width=20.0,
        x_label_overhang=0.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert [[e.label for e, _ in row] for row in plan.legend_rows] == [
        ["a" * 6, "b" * 9],
        ["c" * 10],
    ]
    assert [x for _, x in plan.legend_rows[0]] == pytest.approx([8.0, 88.24])
    assert [x for _, x in plan.legend_rows[1]] == [8.0]
    # the second row costs one LEGEND_ROW of plot height
    assert plan.plot.top == 29.0 + 2 * LEGEND_ROW


def test_legend_entries_keep_style_and_swatch_in_order() -> None:
    entries = (
        _entry("one", 3, "shape"),
        _entry("two", 1, "block"),
        _entry("three", 5, "line"),
    )
    plan = _plan(legend=entries)
    (row,) = plan.legend_rows
    assert [e for e, _ in row] == list(entries)
    assert [e.swatch for e, _ in row] == ["shape", "block", "line"]
    assert [e.style for e, _ in row] == [
        series_style(3),
        series_style(1),
        series_style(5),
    ]


def test_legend_label_is_fitted_to_thirty_percent_of_the_width() -> None:
    label = "L" * 30
    cap = 0.3 * 400
    fitted = "L" * 16 + ELLIPSIS
    assert (
        text_width(fitted, FONT_TEXT)
        <= cap
        < text_width("L" * 17 + ELLIPSIS, FONT_TEXT)
    )
    plan = _plan(legend=(_entry(label, 2, "block"),))
    ((got, x),) = plan.legend_rows[0]
    assert got == LegendEntry(fitted, series_style(2), "block")
    assert x == 8.0


def test_legend_label_at_exactly_thirty_percent_is_unchanged() -> None:
    cap = 0.3 * 400
    label = "L" * 17
    assert text_width(label, FONT_TEXT) <= cap
    plan = _plan(legend=(_entry(label),))
    assert plan.legend_rows[0][0][0].label == label


def test_fitted_label_width_drives_the_next_entry_position() -> None:
    plan = _plan(legend=(_entry("L" * 30), _entry("z", 1)))
    (row,) = plan.legend_rows
    fitted_w = text_width("L" * 16 + ELLIPSIS, FONT_TEXT)
    assert row[1][1] == pytest.approx(8.0 + 24.0 + fitted_w + 14.0)


def test_an_entry_wider_than_the_row_still_takes_the_first_slot() -> None:
    width = 50
    fitted = fit_text("abcdefgh", 0.3 * width, FONT_TEXT)
    assert fitted == "a" + ELLIPSIS
    first_end = PAD + (LEGEND_SWATCH + LEGEND_GAP + text_width(fitted, FONT_TEXT))
    assert first_end > width - PAD  # the scenario: the first entry alone is too wide
    plan = plan_frame(
        width,
        300,
        legend=(_entry("abcdefgh"), _entry("i", 1)),
        y_label_width=5.0,
        x_label_overhang=0.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert [[e.label for e, _ in row] for row in plan.legend_rows] == [
        ["a" + ELLIPSIS],
        ["i"],
    ]
    assert plan.legend_rows[0][0][1] == 8.0
    assert plan.legend_rows[1][0][1] == 8.0


# ----------------------------------------------------------------- bounds


@pytest.mark.parametrize(
    "legend_n,notes,x_title,y_title",
    [(0, 0, False, False), (3, 2, True, True), (9, 4, True, False)],
)
def test_nothing_is_placed_outside_the_chart(
    legend_n: int, notes: int, x_title: bool, y_title: bool
) -> None:
    width, height = 480, 320
    plan = plan_frame(
        width,
        height,
        legend=tuple(_entry(f"series {i}", i % 8) for i in range(legend_n)),
        y_label_width=44.0,
        x_label_overhang=21.0,
        has_x_title=x_title,
        has_y_title=y_title,
        notes=notes,
        right_label_width=18.0,
    )
    ys = [plan.title_y, plan.x_labels_y, *plan.notes_y]
    for y in (plan.y_title_y, plan.x_title_y):
        if y is not None:
            ys.append(y)
    assert all(0.0 <= y <= height - PAD for y in ys)
    assert plan.plot.left >= 0.0 and plan.plot.top >= 0.0
    assert plan.plot.right <= width and plan.plot.bottom <= height
    assert plan.plot.width > 0 and plan.plot.height > 0
    for row in plan.legend_rows:
        for entry, x in row:
            end = x + LEGEND_SWATCH + LEGEND_GAP + text_width(entry.label, FONT_TEXT)
            assert x >= PAD and end <= width - PAD
    assert plan.plot.top >= plan.legend_top + len(plan.legend_rows) * LEGEND_ROW


def test_a_chart_too_small_for_its_margins_gets_a_zero_size_plot() -> None:
    plan = plan_frame(
        40,
        50,
        legend=(),
        y_label_width=30.0,
        x_label_overhang=10.0,
        has_x_title=True,
        has_y_title=True,
        notes=2,
    )
    assert plan.plot.width == 0.0
    assert plan.plot.height == 0.0
