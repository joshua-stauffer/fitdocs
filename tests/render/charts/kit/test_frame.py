"""Tests for the kit frame: root, metadata, grid, axes, legend, notes, the
no-data state and the descriptions (chart-kit Req 7.1, 7.2, 8.1, 8.3, 8.5, 9.3,
9.6, 9.7, 10.1, 10.2, 10.3).

Whole elements are pinned against literals. Pixel positions are chosen so that
``fmt_num`` changes them (three or more decimals), so a coordinate written
without it shows.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from fitdocs.render.charts.kit import frame, marks
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.frame import (
    axis,
    describe,
    document,
    grid,
    legend,
    no_data,
    no_trend_note,
    not_drawn_note,
    notes,
    title_text,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    LegendEntry,
    Rect,
    plan_frame,
)
from fitdocs.render.charts.kit.scales import (
    BandScale,
    NumericScale,
    ScaleType,
    Side,
    Tick,
    band_scale,
)
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    KindSpec,
    MarkBound,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import (
    MAX_SERIES,
    InkRole,
    SeriesStyle,
    Shape,
    series_style,
    shape_path,
)

from ._helpers import chart_request

STYLE = (
    "@media (prefers-color-scheme:light){.ck-t{fill:#707070}.ck-s{stroke:#707070}}"
    "@media (prefers-color-scheme:dark){.ck-t{fill:#8e8e8e}.ck-s{stroke:#8e8e8e}}"
)

DISTANCE = Column("distance_km", ValueKind.NUMBER, unit="km")
ELAPSED = Column("elapsed", ValueKind.DURATION)
START = Column("start", ValueKind.DATETIME, unit="utc")
SPORT = Column("sport", ValueKind.CATEGORY)


def _t(
    x: str, y: str, content: str, anchor: str | None = None, size: str = "11"
) -> str:
    a = "" if anchor is None else f' text-anchor="{anchor}"'
    return (
        f'<text x="{x}" y="{y}"{a} font-size="{size}" class="ck-t" fill="#7f7f7f">'
        f"{content}</text>"
    )


def _s(x1: str, y1: str, x2: str, y2: str, opacity: str | None = None) -> str:
    o = "" if opacity is None else f' stroke-opacity="{opacity}"'
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="ck-s"'
        f' stroke="#7f7f7f"{o}/>'
    )


def _entry(label: str, index: int, swatch: str) -> LegendEntry:
    return LegendEntry(label, series_style(index), swatch)  # type: ignore[arg-type]


# Plot Rect(36.5, 48, 347.5, 179): bottom 227, right 384; x labels y 246, x title
# y 262, y title y 40, notes y 277 and 292.
PLAN = plan_frame(
    400,
    300,
    legend=(),
    y_label_width=20.5,
    x_label_overhang=10.0,
    has_x_title=True,
    has_y_title=True,
    notes=2,
)
PLOT = PLAN.plot

# Vertical ticks at 227, 150.2857..., 99.1428..., 48.
VSCALE = NumericScale(
    ScaleType.LINEAR,
    0.0,
    7.0,
    227.0,
    48.0,
    (Tick(0.0, "0"), Tick(3.0, "3.1"), Tick(5.0, "5.2"), Tick(7.0, "7.4")),
    DISTANCE,
)
# Horizontal ticks at 36.5, 113.7222..., 190.9444..., 384.
HSCALE = NumericScale(
    ScaleType.LINEAR,
    0.0,
    9.0,
    36.5,
    384.0,
    (Tick(0.0, "0:00"), Tick(2.0, "0:02"), Tick(4.0, "0:04"), Tick(9.0, "0:09")),
    ELAPSED,
)


def test_plan_fixture_is_the_geometry_the_literals_assume() -> None:
    assert Rect(36.5, 48.0, 347.5, 179.0) == PLOT
    assert (PLAN.y_title_y, PLAN.x_labels_y, PLAN.x_title_y) == (40.0, 246.0, 262.0)
    assert PLAN.notes_y == (277.0, 292.0)
    assert PLAN.title_y == 21.0


# ------------------------------------------------------------------ document


def test_document_is_root_then_title_desc_style_then_body() -> None:
    out = document(
        400,
        300,
        title="My chart",
        description="A description.",
        body=["<g/>", '<g class="b"/>'],
    )
    assert out == (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"'
        ' viewBox="0 0 400 300" role="img" font-family="sans-serif">'
        "<title>My chart</title><desc>A description.</desc>"
        f"<style>{STYLE}</style>"
        '<g/><g class="b"/></svg>'
    )


def test_document_has_no_id_and_no_background_rect() -> None:
    out = document(320, 160, title="T", description="D", body=[])
    assert "id=" not in out
    assert "<rect" not in out
    assert "<image" not in out
    assert "light-dark(" not in out
    assert "currentColor" not in out
    assert out.count("<style>") == 1
    assert "\n" not in out


def test_document_escapes_and_cleans_caller_text() -> None:
    out = document(
        400,
        300,
        title='A<b & "c"\x01\tD',
        description="x > y\x02&z",
        body=[],
    )
    assert "<title>A&lt;b &amp; &quot;c&quot;� D</title>" in out
    assert "<desc>x &gt; y�&amp;z</desc>" in out
    assert "\x01" not in out
    assert "\x02" not in out


def test_document_extra_roles_add_their_rule_after_the_core_roles() -> None:
    extra = InkRole("ck-x", "fill", "#111111", "#222222", "#333333", False)
    out = document(400, 300, title="T", description="D", body=[], extra_roles=(extra,))
    assert (
        "@media (prefers-color-scheme:light){.ck-t{fill:#707070}.ck-s{stroke:#707070}"
        ".ck-x{fill:#222222}}"
        "@media (prefers-color-scheme:dark){.ck-t{fill:#8e8e8e}.ck-s{stroke:#8e8e8e}"
        ".ck-x{fill:#333333}}"
    ) in out


# --------------------------------------------------------------------- title


def test_title_text_is_one_ink_text_at_the_title_baseline() -> None:
    assert title_text(PLAN, "Weekly <km>") == _t(
        "8", "21", "Weekly &lt;km&gt;", size="13"
    )


def test_title_text_is_fitted_with_an_ellipsis_and_cleaned() -> None:
    long = "0123456789" * 6
    assert title_text(PLAN, long) == _t(
        "8", "21", "012345678901234567890123456789012345678901234…", size="13"
    )
    assert title_text(PLAN, "a\x01b\tc") == _t("8", "21", "a�b c", size="13")


# ---------------------------------------------------------------------- grid


def test_horizontal_gridlines_span_the_plot_at_each_tick_with_decorative_opacity() -> (
    None
):
    assert grid(VSCALE, PLOT, horizontal_lines=True) == (
        '<g class="ck-grid">'
        + _s("36.5", "227", "384", "227", "0.25")
        + _s("36.5", "150.29", "384", "150.29", "0.25")
        + _s("36.5", "99.14", "384", "99.14", "0.25")
        + _s("36.5", "48", "384", "48", "0.25")
        + "</g>"
    )


def test_vertical_gridlines_span_the_plot_height_at_each_tick() -> None:
    assert grid(HSCALE, PLOT, horizontal_lines=False) == (
        '<g class="ck-grid">'
        + _s("36.5", "48", "36.5", "227", "0.25")
        + _s("113.72", "48", "113.72", "227", "0.25")
        + _s("190.94", "48", "190.94", "227", "0.25")
        + _s("384", "48", "384", "227", "0.25")
        + "</g>"
    )


# ---------------------------------------------------------------------- axis


def test_left_axis_labels_end_anchored_title_from_the_column() -> None:
    assert axis(VSCALE, PLOT, Side.LEFT, title=None, plan=PLAN) == (
        '<g class="ck-axis">'
        + _s("36.5", "48", "36.5", "227")
        + _s("36.5", "227", "31.5", "227")
        + _s("36.5", "150.29", "31.5", "150.29")
        + _s("36.5", "99.14", "31.5", "99.14")
        + _s("36.5", "48", "31.5", "48")
        + _t("28.5", "231", "0", "end")
        + _t("28.5", "154.29", "3.1", "end")
        + _t("28.5", "103.14", "5.2", "end")
        + _t("28.5", "52", "7.4", "end")
        + _t("36.5", "40", "distance (km)", "start")
        + "</g>"
    )


def test_right_axis_labels_start_anchored_title_ends_at_the_plot_edge() -> None:
    assert axis(VSCALE, PLOT, Side.RIGHT, title=None, plan=PLAN) == (
        '<g class="ck-axis">'
        + _s("384", "48", "384", "227")
        + _s("384", "227", "389", "227")
        + _s("384", "150.29", "389", "150.29")
        + _s("384", "99.14", "389", "99.14")
        + _s("384", "48", "389", "48")
        + _t("392", "231", "0", "start")
        + _t("392", "154.29", "3.1", "start")
        + _t("392", "103.14", "5.2", "start")
        + _t("392", "52", "7.4", "start")
        + _t("384", "40", "distance (km)", "end")
        + "</g>"
    )


def test_bottom_axis_labels_centred_on_ticks_title_centred_on_the_plot() -> None:
    assert axis(HSCALE, PLOT, Side.BOTTOM, title=None, plan=PLAN) == (
        '<g class="ck-axis">'
        + _s("36.5", "227", "384", "227")
        + _s("36.5", "227", "36.5", "232")
        + _s("113.72", "227", "113.72", "232")
        + _s("190.94", "227", "190.94", "232")
        + _s("384", "227", "384", "232")
        + _t("36.5", "246", "0:00", "middle")
        + _t("113.72", "246", "0:02", "middle")
        + _t("190.94", "246", "0:04", "middle")
        + _t("384", "246", "0:09", "middle")
        + _t("210.25", "262", "elapsed (h:mm:ss)", "middle")
        + "</g>"
    )


def test_numeric_axis_title_takes_hours_and_clock_date_from_the_scale() -> None:
    minutes = NumericScale(
        ScaleType.LINEAR,
        0.0,
        9.0,
        36.5,
        384.0,
        (Tick(0.0, "0:00"),),
        ELAPSED,
        hours=False,
    )
    assert _t("210.25", "262", "elapsed (m:ss)", "middle") in axis(
        minutes, PLOT, Side.BOTTOM, title=None, plan=PLAN
    )
    clock = NumericScale(
        ScaleType.TIME,
        0.0,
        9.0,
        36.5,
        384.0,
        (Tick(0.0, "08:00"),),
        START,
        clock_date=date(2026, 3, 9),
    )
    assert _t("210.25", "262", "start (UTC, 2026-03-09)", "middle") in axis(
        clock, PLOT, Side.BOTTOM, title=None, plan=PLAN
    )
    undated = NumericScale(
        ScaleType.TIME, 0.0, 9.0, 36.5, 384.0, (Tick(0.0, "08:00"),), START
    )
    assert _t("210.25", "262", "start (UTC)", "middle") in axis(
        undated, PLOT, Side.BOTTOM, title=None, plan=PLAN
    )


def test_axis_title_is_cleaned_whether_derived_from_the_column_or_given() -> None:
    labelled = NumericScale(
        ScaleType.LINEAR,
        0.0,
        9.0,
        36.5,
        384.0,
        (Tick(0.0, "0"),),
        Column("v", ValueKind.NUMBER, label="L\x01\tM"),
    )
    assert _t("210.25", "262", "L\ufffd M", "middle") in axis(
        labelled, PLOT, Side.BOTTOM, title=None, plan=PLAN
    )
    assert _t("210.25", "262", "a\ufffdb c", "middle") in axis(
        BANDS, PLOT, Side.BOTTOM, title="a\x01b\tc", plan=PLAN
    )


def test_axis_title_is_fitted_to_the_room_at_its_own_anchor() -> None:
    long = "x" * 80
    assert _t("210.25", "262", "x" * 50 + "…", "middle") in axis(
        BANDS, PLOT, Side.BOTTOM, title=long, plan=PLAN
    )
    assert _t("36.5", "40", "x" * 49 + "…", "start") in axis(
        BANDS, PLOT, Side.LEFT, title=long, plan=PLAN
    )
    assert _t("384", "40", "x" * 52 + "…", "end") in axis(
        BANDS, PLOT, Side.RIGHT, title=long, plan=PLAN
    )


def test_every_axis_title_extent_lies_within_the_chart_at_width_320() -> None:
    plan = plan_frame(
        320,
        300,
        legend=(),
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=True,
        has_y_title=True,
        notes=0,
    )
    plot = plan.plot
    assert plot.right == 320 - 16  # right margin 16: the right title ends at 304
    for side in (Side.LEFT, Side.RIGHT, Side.BOTTOM):
        out = axis(BANDS, plot, side, title="x" * 80, plan=plan)
        found = re.findall(
            r'<text x="([^"]+)" y="[^"]+" text-anchor="(start|end|middle)"'
            r' font-size="11" class="ck-t" fill="#7f7f7f">(x+…)</text>',
            out,
        )
        assert len(found) == 1
        x, anchor, content = found[0]
        width = len(content) * FONT_TEXT * 0.64
        left = {
            "start": float(x),
            "end": float(x) - width,
            "middle": float(x) - width / 2,
        }[anchor]
        assert left >= 8 - 1e-9
        assert left + width <= 320 - 8 + 1e-9


def test_axis_title_none_derives_a_string_is_verbatim_and_empty_draws_none() -> None:
    derived = axis(VSCALE, PLOT, Side.LEFT, title=None, plan=PLAN)
    assert _t("36.5", "40", "distance (km)", "start") in derived
    given = axis(VSCALE, PLOT, Side.LEFT, title="Given <t>", plan=PLAN)
    assert _t("36.5", "40", "Given &lt;t&gt;", "start") in given
    assert "distance" not in given
    for scale, side in (
        (VSCALE, Side.LEFT),
        (HSCALE, Side.BOTTOM),
        (BANDS, Side.BOTTOM),
    ):
        none = axis(scale, PLOT, side, title="", plan=PLAN)
        assert "<text" in none  # tick labels remain
        assert 'y="40"' not in none and 'y="262"' not in none
    with pytest.raises(ValueError):
        axis(BANDS, PLOT, Side.BOTTOM, plan=PLAN)


def test_bottom_band_labels_are_cleaned_and_fitted_to_their_spacing() -> None:
    # band 115.83 px, every band labelled: room 111.83 px -> 14 chars + ellipsis
    bands = BandScale(("x" * 30, "a\x01b\tc", "Mid"), 36.5, 384.0, (0, 1, 2))
    out = axis(bands, PLOT, Side.BOTTOM, title="S", plan=PLAN)
    assert _t("94.42", "246", "x" * 14 + "…", "middle") in out
    assert _t("210.25", "246", "a\ufffdb c", "middle") in out
    # labelled (0, 2): spacing room 227.67 px, but the chart edge clamps each label
    # to twice its distance from the nearer edge less PAD: 172.83 px at x 94.42
    # (23 chars + ellipsis) and 131.84 px at x 326.08 (17 chars + ellipsis)
    thinned = BandScale(("x" * 40, "b", "y" * 40), 36.5, 384.0, (0, 2))
    out = axis(thinned, PLOT, Side.BOTTOM, title="S", plan=PLAN)
    assert _t("94.42", "246", "x" * 23 + "…", "middle") in out
    assert _t("326.08", "246", "y" * 17 + "…", "middle") in out


def test_bottom_band_label_with_one_label_drawn_is_spaced_by_all_bands() -> None:
    # labelled (0,): spacing is the three bands (343.5 px), clamped by the edge to
    # 172.83 px (23 chars); a spacing of one band would give 111.83 px (14 chars)
    bands = BandScale(("x" * 60, "y" * 60, "z" * 60), 36.5, 384.0, (0,))
    out = axis(bands, PLOT, Side.BOTTOM, title="S", plan=PLAN)
    assert _t("94.42", "246", "x" * 23 + "…", "middle") in out


def test_bottom_band_spacing_is_the_gap_between_the_first_two_labelled_bands() -> None:
    # four bands of 86.875 px, labelled (1, 3): gap 2 -> 169.75 px (23 chars) at
    # x 166.81; the right label at x 340.56 is clamped to 102.88 px (13 chars)
    bands = BandScale(("a", "x" * 60, "b", "y" * 60), 36.5, 384.0, (1, 3))
    out = axis(bands, PLOT, Side.BOTTOM, title="S", plan=PLAN)
    assert _t("166.81", "246", "x" * 23 + "…", "middle") in out
    assert _t("340.56", "246", "y" * 13 + "…", "middle") in out


def test_real_band_scale_labels_stay_inside_the_chart_at_width_320() -> None:
    plan = plan_frame(
        320,
        300,
        legend=(),
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=True,
        has_y_title=True,
        notes=0,
    )
    plot = plan.plot
    cases = [
        ("x" * 60, "y" * 60, "z" * 60),
        ("Alpha" * 4, "B", "C", "D", "E", "F"),
        ("Alpha" * 4, "B", "C", "D", "E", "F" * 40),
    ]
    for labels in cases:
        scale = band_scale(labels, plot.left, plot.right, font_px=FONT_TEXT)
        out = axis(scale, plot, Side.BOTTOM, title="S", plan=plan)
        found = re.findall(
            rf'<text x="([^"]+)" y="{plan.x_labels_y:g}" text-anchor="middle"'
            r' font-size="11" class="ck-t" fill="#7f7f7f">([^<]*)</text>',
            out,
        )
        assert len(found) == len(scale.labelled)
        for x, content in found:
            half = len(content) * FONT_TEXT * 0.64 / 2
            assert float(x) - half >= 8 - 1e-9, (labels, x, content)
            assert float(x) + half <= 320 - 8 + 1e-9, (labels, x, content)
    # the first case has one label drawn, so it ran the clamp on the long label
    scale = band_scale(cases[0], plot.left, plot.right, font_px=FONT_TEXT)
    assert scale.labelled == (0,)


def test_side_band_labels_are_cleaned() -> None:
    wide = Rect(100.0, 48.0, 200.0, 179.0)  # left and right room 84 px
    bands = BandScale(("a\x01b\tc", "Mid"), 48.0, 227.0, (0, 1))
    out = axis(bands, wide, Side.LEFT, title="S", plan=PLAN)
    assert _t("92", "96.75", "a\ufffdb c", "end") in out
    out = axis(bands, wide, Side.RIGHT, title="S", plan=PLAN)
    assert _t("308", "96.75", "a\ufffdb c", "start") in out


def test_right_band_labels_are_fitted_to_the_room_right_of_the_plot() -> None:
    narrow = Rect(36.5, 48.0, 300.0, 179.0)  # right edge 336.5: room 47.5 px
    bands = BandScale(("Extraordinarily long", "Mid"), 48.0, 227.0, (0, 1))
    right = axis(bands, narrow, Side.RIGHT, title="S", plan=PLAN)
    assert _t("344.5", "96.75", "Extra…", "start") in right
    left = axis(bands, narrow, Side.LEFT, title="S", plan=PLAN)
    assert _t("28.5", "96.75", "E…", "end") in left


def test_axis_titles_are_omitted_where_the_plan_has_no_row_for_them() -> None:
    bare = plan_frame(
        400,
        300,
        legend=(),
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert bare.y_title_y is None and bare.x_title_y is None
    assert "distance" not in axis(VSCALE, bare.plot, Side.LEFT, title="t", plan=bare)
    assert "distance" not in axis(VSCALE, bare.plot, Side.RIGHT, title="t", plan=bare)
    assert "elapsed" not in axis(HSCALE, bare.plot, Side.BOTTOM, title="t", plan=bare)


BANDS = BandScale(("Zeta", "Alpha", "Mid"), 36.5, 384.0, (0, 2))


def test_bottom_band_axis_labels_only_the_thinned_bands_at_their_centres() -> None:
    assert axis(BANDS, PLOT, Side.BOTTOM, title="Sport", plan=PLAN) == (
        '<g class="ck-axis">'
        + _s("36.5", "227", "384", "227")
        + _s("94.42", "227", "94.42", "232")
        + _s("326.08", "227", "326.08", "232")
        + _t("94.42", "246", "Zeta", "middle")
        + _t("326.08", "246", "Mid", "middle")
        + _t("210.25", "262", "Sport", "middle")
        + "</g>"
    )


def test_left_band_axis_fits_long_labels_to_the_room_left_of_the_plot() -> None:
    vertical = BandScale(
        ("Extraordinarily long name", "Alpha", "Mid"), 48.0, 227.0, (0, 1, 2)
    )
    out = axis(vertical, PLOT, Side.LEFT, title="Sport", plan=PLAN)
    assert out == (
        '<g class="ck-axis">'
        + _s("36.5", "48", "36.5", "227")
        + _s("36.5", "77.83", "31.5", "77.83")
        + _s("36.5", "137.5", "31.5", "137.5")
        + _s("36.5", "197.17", "31.5", "197.17")
        + _t("28.5", "81.83", "E…", "end")
        + _t("28.5", "141.5", "A…", "end")
        + _t("28.5", "201.17", "M…", "end")
        + _t("36.5", "40", "Sport", "start")
        + "</g>"
    )


# -------------------------------------------------------------------- legend

LEGEND_ENTRIES = (
    _entry("Run", 0, "line"),
    _entry("Bike", 1, "shape"),
    _entry("Swim", 2, "block"),
)
LPLAN = plan_frame(
    400,
    300,
    legend=LEGEND_ENTRIES,
    y_label_width=20.5,
    x_label_overhang=10.0,
    has_x_title=False,
    has_y_title=False,
    notes=0,
)


def test_legend_plan_fixture_is_the_geometry_the_literals_assume() -> None:
    assert len(LPLAN.legend_rows) == 1
    assert [x for _, x in LPLAN.legend_rows[0]] == [8.0, 67.12, 133.28]
    assert LPLAN.legend_top == 29.0
    assert LPLAN.plot.top == 47.0


def test_legend_draws_a_swatch_of_each_kind_then_the_label() -> None:
    assert legend(LPLAN) == (
        '<g class="ck-legend">'
        '<line x1="8" y1="36" x2="28" y2="36" stroke="#3284d0" stroke-width="1.8"/>'
        + _t("32", "40", "Run")
        + '<path d="M77.12 36h0" fill="none" stroke="#e86518" stroke-width="7"'
        ' stroke-linecap="square"/>'
        + _t("91.12", "40", "Bike")
        + '<rect x="138.28" y="31" width="10" height="10" fill="#ac4e87"/>'
        + _t("157.28", "40", "Swim")
        + "</g>"
    )


def test_line_swatch_carries_the_series_dash_only_when_it_has_one() -> None:
    plan = plan_frame(
        400,
        300,
        legend=(_entry("Run", 0, "line"), _entry("Bike", 1, "line")),
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    out = legend(plan)
    assert (
        '<line x1="8" y1="36" x2="28" y2="36" stroke="#3284d0" stroke-width="1.8"/>'
        in out
    )
    assert (
        '<line x1="67.12" y1="36" x2="87.12" y2="36" stroke="#e86518"'
        ' stroke-width="1.8" stroke-dasharray="6 3"/>'
    ) in out


def test_wrapped_legend_rows_step_down_by_the_row_height() -> None:
    plan = plan_frame(
        180,
        300,
        legend=LEGEND_ENTRIES,
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert [len(r) for r in plan.legend_rows] == [2, 1]
    out = legend(plan)
    assert _t("32", "58", "Swim") in out
    assert '<rect x="13" y="49" width="10" height="10" fill="#ac4e87"/>' in out
    assert _t("32", "40", "Run") in out


def test_legend_label_is_cleaned_and_escaped() -> None:
    plan = plan_frame(
        400,
        300,
        legend=(_entry("A&B<\x01", 0, "line"),),
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert _t("32", "40", "A&amp;B&lt;�") in legend(plan)


def test_empty_legend_is_empty_text() -> None:
    assert legend(PLAN) == ""


@pytest.mark.parametrize("shape", list(Shape))
def test_shape_swatch_is_the_marker_geometry_at_the_swatch_centre(shape: Shape) -> None:
    style = SeriesStyle("#123456", None, shape)
    plan = plan_frame(
        400,
        300,
        legend=(_entry("Run", 0, "line"), LegendEntry("Bike", style, "shape")),
        y_label_width=20.5,
        x_label_overhang=10.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )
    assert plan.legend_rows[0][1][1] == 67.12
    swatch = marks.points([(77.12, 36.0)], style)
    assert swatch == shape_path(shape, [(77.12, 36.0)], "#123456")
    assert swatch in legend(plan)


def test_circle_and_triangle_markers_differ() -> None:
    circle = marks.points([(77.12, 36.0)], SeriesStyle("#123456", None, Shape.CIRCLE))
    triangle = marks.points(
        [(77.12, 36.0)], SeriesStyle("#123456", None, Shape.TRIANGLE_UP)
    )
    assert circle != triangle


def test_top_y_tick_label_baseline_is_a_full_line_below_the_last_legend_row_text() -> (
    None
):
    top_scale = NumericScale(
        ScaleType.LINEAR,
        0.0,
        7.0,
        273.0,
        47.0,
        (Tick(0.0, "0"), Tick(7.0, "7.4")),
        DISTANCE,
    )
    legend_ys = re.findall(r'<text x="[^"]+" y="([^"]+)"', legend(LPLAN))
    label_ys = re.findall(
        r'<text x="[^"]+" y="([^"]+)" text-anchor="end"',
        axis(top_scale, LPLAN.plot, Side.LEFT, title="t", plan=LPLAN),
    )
    assert legend_ys == ["40", "40", "40"]
    assert label_ys == ["277", "51"]
    assert float(label_ys[1]) - float(legend_ys[0]) >= FONT_TEXT


def test_frame_never_imports_marks() -> None:
    tree = ast.parse(Path(frame.__file__).read_text())
    imported: list[str] = []
    marks_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.append(module)
            for alias in node.names:
                if alias.name == "marks":
                    marks_imports.append(f"from {module} import marks")
            if module.split(".")[-1] == "marks":
                marks_imports.append(f"from {module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
                if alias.name.split(".")[-1] == "marks":
                    marks_imports.append(f"import {alias.name}")
    assert "fitdocs.render.charts.kit.theme" in imported
    assert marks_imports == []


# --------------------------------------------------------------------- notes


def test_notes_are_text_lines_at_the_reserved_rows() -> None:
    assert notes(PLAN, ["Not drawn: 1 row without y.", "A & B"]) == (
        '<g class="ck-notes">'
        + _t("8", "277", "Not drawn: 1 row without y.")
        + _t("8", "292", "A &amp; B")
        + "</g>"
    )


def test_notes_are_fitted_to_the_width() -> None:
    out = notes(PLAN, ["x" * 80, "y"])
    assert _t("8", "277", "x" * 53 + "…") in out


def test_notes_text_is_cleaned() -> None:
    assert _t("8", "277", "a�b c") in notes(PLAN, ["ab	c", "y"])


def test_notes_count_must_match_the_reserved_rows() -> None:
    with pytest.raises(ValueError, match="1 note lines for 2 reserved rows"):
        notes(PLAN, ["only one"])
    assert notes(LPLAN, []) == ""


def test_not_drawn_wording_singular_plural_and_several_channels() -> None:
    assert not_drawn_note([("y", 1)]) == "Not drawn: 1 row without y."
    assert not_drawn_note([("x", 3), ("y", 2)]) == (
        "Not drawn: 3 rows without x, 2 rows without y."
    )
    assert not_drawn_note([("x", 1), ("y", 1)]) == (
        "Not drawn: 1 row without x, 1 row without y."
    )


def test_not_drawn_skips_zero_counts_keeps_order_and_is_none_when_all_zero() -> None:
    assert not_drawn_note((("x", 0), ("y", 1))) == "Not drawn: 1 row without y."
    assert not_drawn_note((("y", 2), ("x", 3))) == (
        "Not drawn: 2 rows without y, 3 rows without x."
    )
    assert not_drawn_note((("x", 0),)) is None
    assert not_drawn_note(()) is None


def test_no_trend_wording() -> None:
    assert no_trend_note(["Bike", "Swim"]) == (
        "No trend line for Bike, Swim: fewer than 2 distinct x values."
    )
    assert no_trend_note(["Bike"]) == (
        "No trend line for Bike: fewer than 2 distinct x values."
    )
    with pytest.raises(ValueError):
        no_trend_note([])


# ------------------------------------------------------------------ describe

CHANNELS = [
    ("x", Column("day", ValueKind.DATE)),
    ("y", DISTANCE),
    ("color", SPORT),
]
RANGES = [
    ("day", "2026-01-05", "2026-03-02"),
    ("distance (km)", "3.5 km", "42.2 km"),
]


def test_describe_a_chart_in_one_paragraph() -> None:
    assert describe(
        "line",
        "Weekly km",
        CHANNELS,
        rows=12,
        series=2,
        undrawn=[("x", 3), ("y", 2)],
        ranges=RANGES,
    ) == (
        "Line chart: Weekly km. x: day; y: distance (km); color: sport."
        " 12 rows, 2 series. Not drawn: 3 rows without x, 2 rows without y."
        " day from 2026-01-05 to 2026-03-02;"
        " distance (km) from 3.5 km to 42.2 km."
    )


def test_describe_without_series_or_undrawn_rows() -> None:
    assert describe(
        "hbar",
        "Rank",
        CHANNELS[:2],
        rows=1,
        series=None,
        undrawn=[],
        ranges=RANGES[1:],
    ) == (
        "Hbar chart: Rank. x: day; y: distance (km). 1 row."
        " distance (km) from 3.5 km to 42.2 km."
    )


def test_describe_all_zero_undrawn_counts_add_no_sentence() -> None:
    out = describe(
        "bar",
        "T",
        CHANNELS[:1],
        rows=5,
        series=None,
        undrawn=[("x", 0)],
        ranges=RANGES[:1],
    )
    assert out == "Bar chart: T. x: day. 5 rows. day from 2026-01-05 to 2026-03-02."


def test_describe_a_string_channel_is_the_drawn_title_verbatim() -> None:
    out = describe(
        "line",
        "T",
        [
            ("x", "moving (m:ss)"),
            ("y", "start (UTC, 2026-03-02)"),
            ("color", SPORT),
        ],
        rows=2,
        series=None,
        undrawn=[],
        ranges=RANGES[:1],
    )
    assert out == (
        "Line chart: T. x: moving (m:ss); y: start (UTC, 2026-03-02);"
        " color: sport. 2 rows. day from 2026-01-05 to 2026-03-02."
    )


def test_describe_a_string_channel_differs_from_the_column_default() -> None:
    column = Column("moving", ValueKind.DURATION)
    ranges = RANGES[:1]
    default = describe(
        "bar", "T", [("y", column)], rows=1, series=None, undrawn=[], ranges=ranges
    )
    drawn = describe(
        "bar",
        "T",
        [("y", "moving (m:ss)")],
        rows=1,
        series=None,
        undrawn=[],
        ranges=ranges,
    )
    assert (
        default == "Bar chart: T. y: moving (h:mm:ss). 1 row."
        " day from 2026-01-05 to 2026-03-02."
    )
    assert (
        drawn
        == "Bar chart: T. y: moving (m:ss). 1 row. day from 2026-01-05 to 2026-03-02."
    )


def test_describe_a_string_channel_is_cleaned() -> None:
    out = describe(
        "bar",
        "T",
        [("y", "a\x01b\nc")],
        rows=1,
        series=None,
        undrawn=[],
        ranges=RANGES[:1],
    )
    assert (
        out == "Bar chart: T. y: a\ufffdb c. 1 row. day from 2026-01-05 to 2026-03-02."
    )


def test_describe_without_channels_has_no_channel_sentence() -> None:
    out = describe("bar", "T", [], rows=2, series=None, undrawn=[], ranges=RANGES[:1])
    assert out == "Bar chart: T. 2 rows. day from 2026-01-05 to 2026-03-02."


def test_describe_none_of_the_rows_is_singular_for_one_row() -> None:
    one = describe("bar", "T", [], rows=1, series=None, undrawn=[], ranges=[])
    two = describe("bar", "T", [], rows=2, series=None, undrawn=[], ranges=[])
    assert one == "Bar chart: T. No data: none of the 1 row has a value to draw."
    assert two == "Bar chart: T. No data: none of the 2 rows has a value to draw."


def test_describe_zero_series_is_stated_not_dropped() -> None:
    out = describe(
        "bar", "T", CHANNELS[:1], rows=5, series=0, undrawn=[], ranges=RANGES[:1]
    )
    assert "5 rows, 0 series." in out
    assert "Not drawn" not in out


def test_describe_title_is_cleaned() -> None:
    out = describe("bar", "A\x01\tB", [], rows=0, series=None, undrawn=[], ranges=[])
    assert out == "Bar chart: A� B. No data: no rows."


def test_describe_no_rows() -> None:
    assert (
        describe(
            "line", "Weekly km", CHANNELS, rows=0, series=None, undrawn=[], ranges=[]
        )
        == "Line chart: Weekly km. No data: no rows."
    )
    assert (
        describe(
            "line",
            "Weekly km",
            CHANNELS,
            rows=0,
            series=2,
            undrawn=[("x", 1)],
            ranges=RANGES,
        )
        == "Line chart: Weekly km. No data: no rows."
    )


def test_describe_rows_without_a_drawable_value() -> None:
    assert (
        describe(
            "line",
            "Weekly km",
            CHANNELS,
            rows=7,
            series=None,
            undrawn=[("x", 7)],
            ranges=[],
        )
        == "Line chart: Weekly km. No data: none of the 7 rows has a value to draw."
    )


# ------------------------------------------------------------------- no data


def _no_data_bound(rows: Sequence[Sequence[Value]], width: int = 701) -> BoundChart:
    columns = (Column("day", ValueKind.DATE), DISTANCE)
    spec = KindSpec(
        name="line",
        description="A test kind.",
        output=Output.SVG,
        channels=(ChannelSpec("x", (ValueKind.DATE,), True, "x"),),
        options=(),
        bound=MarkBound(2000, "rows", OverBound.REFUSE, "rule"),
        max_series=MAX_SERIES,
        draw=lambda chart: "",
    )
    return BoundChart(
        request=chart_request("area", title="My <title>"),
        spec=spec,
        columns={"x": columns[0], "y": columns[1]},
        all_columns=columns,
        options={"width": width, "height": None},
        rows=tuple(tuple(r) for r in rows),
    )


NO_DATA_HEAD = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="701" height="241"'
    ' viewBox="0 0 701 241" role="img" font-family="sans-serif">'
    "<title>My &lt;title&gt;</title>"
)


def test_no_data_without_rows_is_one_message_at_the_given_size() -> None:
    assert no_data(_no_data_bound([]), height=241) == (
        NO_DATA_HEAD
        + "<desc>Line chart: My &lt;title&gt;. No data: no rows.</desc>"
        + f"<style>{STYLE}</style>"
        + _t("8", "21", "My &lt;title&gt;", size="13")
        + _t("350.5", "120.5", "No data", "middle", "13")
        + "</svg>"
    )


def test_no_data_with_rows_adds_the_second_line_with_the_row_count() -> None:
    rows: list[list[Value]] = [[None, None], [None, None], [None, None]]
    assert no_data(_no_data_bound(rows), height=241) == (
        NO_DATA_HEAD
        + "<desc>Line chart: My &lt;title&gt;. No data: none of the 3 rows has a"
        " value to draw.</desc>"
        + f"<style>{STYLE}</style>"
        + _t("8", "21", "My &lt;title&gt;", size="13")
        + _t("350.5", "120.5", "No data", "middle", "13")
        + _t("350.5", "138.5", "None of the 3 rows has a value to draw.", "middle")
        + "</svg>"
    )


def test_no_data_second_line_is_singular_for_one_row() -> None:
    one = no_data(_no_data_bound([[None, None]]), height=241)
    assert (
        _t("350.5", "138.5", "None of the 1 row has a value to draw.", "middle") in one
    )
    two = no_data(_no_data_bound([[None, None], [None, None]]), height=241)
    assert (
        _t("350.5", "138.5", "None of the 2 rows has a value to draw.", "middle") in two
    )


def test_no_data_second_line_is_fitted_to_a_narrow_chart() -> None:
    rows: list[list[Value]] = [[None, None], [None, None], [None, None]]
    out = no_data(_no_data_bound(rows, width=200), height=160)
    assert _t("100", "98", "None of the 3 rows has a …", "middle") in out


# ---------------------------------------------------------------- ink classes


def test_every_text_carries_ck_t_and_every_stroked_grid_and_axis_element_ck_s() -> None:
    out = "".join(
        [
            grid(VSCALE, PLOT, horizontal_lines=True),
            grid(HSCALE, PLOT, horizontal_lines=False),
            axis(VSCALE, PLOT, Side.LEFT, title=None, plan=PLAN),
            axis(HSCALE, PLOT, Side.BOTTOM, title=None, plan=PLAN),
            axis(BANDS, PLOT, Side.BOTTOM, title="Sport", plan=PLAN),
            legend(LPLAN),
            title_text(PLAN, "T"),
            notes(PLAN, ["a", "b"]),
            no_data(_no_data_bound([]), height=241),
        ]
    )
    texts = re.findall(r"<text [^>]*>", out)
    # left axis 5, bottom axis 5, band axis 3, legend 3, title 1, notes 2, no-data 2
    assert len(texts) == 21
    assert all(' class="ck-t" fill="#7f7f7f"' in t for t in texts)

    for group in ("ck-grid", "ck-axis"):
        bodies = re.findall(rf'<g class="{group}">(.*?)</g>', out)
        assert bodies
        for body in bodies:
            elements = re.findall(r"<(?:line|path|rect|polyline)[^>]*>", body)
            assert elements
            assert all(' class="ck-s" stroke="#7f7f7f"' in e for e in elements)
    grid_lines = re.findall(r'<g class="ck-grid">(.*?)</g>', out)
    assert all(
        'stroke-opacity="0.25"' in e for g in grid_lines for e in g.split("/>")[:-1]
    )
    axis_lines = re.findall(r'<g class="ck-axis">(.*?)</g>', out)
    assert not any("stroke-opacity" in g for g in axis_lines)
