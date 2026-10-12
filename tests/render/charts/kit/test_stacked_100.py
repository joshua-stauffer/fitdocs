"""The ``stacked-100`` kind: shares, order, gaps, zero totals, refusals, goldens.

Regenerate the goldens with
``uv run python -m tests.render.charts.kit.test_stacked_100``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, timedelta
from typing import NamedTuple

import pytest

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.stacked_100 import KIND
from fitdocs.render.charts.kit.layout import text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import STROKE
from fitdocs.render.charts.palette import CATEGORICAL_RAMP
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

ZONE = column("zone", ValueKind.CATEGORY)
LABEL = column("label", ValueKind.CATEGORY)
WEEK = column("week", ValueKind.DATE)
SECONDS = column("time_in_zone_s", unit="s")

# Columns (zone, label, seconds): colour first, x second, y last.
COLUMNS = [ZONE, LABEL, SECONDS]
CHANNELS = {"x": "label", "y": "time_in_zone_s", "color": "zone"}
TITLE = "Time in zone"


def _case(
    name: str,
    rows: Sequence[Sequence[Value]],
    *,
    title: str = TITLE,
    columns: Sequence[Column] = COLUMNS,
    channels: dict[str, str] | None = None,
) -> Case:
    request = chart_request("stacked-100", title=title, channels=channels or CHANNELS)
    return Case(name, request, chart_data(columns, rows))


def _text(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


def _render(
    rows: Sequence[Sequence[Value]],
    *,
    columns: Sequence[Column] = COLUMNS,
    channels: dict[str, str] | None = None,
) -> str:
    return _text(_case("t", rows, columns=columns, channels=channels))


def _problems(rows: Sequence[Sequence[Value]]) -> tuple[ChartProblem, ...]:
    case = _case("t", rows)
    return problems_of(KIND, case.request, case.data)


# Reading an SVG --------------------------------------------------------------


class Rect(NamedTuple):
    x: float
    y: float
    width: float
    height: float
    fill: str

    @property
    def bottom(self) -> float:
        return self.y + self.height


_RECT = re.compile(
    r'<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)" '
    r'fill="([^"]+)"/>'
)


def _group(svg: str, name: str) -> str:
    found = re.search(rf'<g class="{name}">(.*?)</g>', svg, re.S)
    assert found, f"no {name} group"
    return found.group(1)


def _marks(svg: str) -> list[Rect]:
    rects = [
        Rect(float(x), float(y), float(w), float(h), fill)
        for x, y, w, h, fill in _RECT.findall(_group(svg, "ck-marks"))
    ]
    assert rects, "the marks group holds no rectangle"
    return rects


def _bars(svg: str) -> list[list[Rect]]:
    """The rects of each bar, bars left to right, segments bottom to top."""
    by_x: dict[float, list[Rect]] = {}
    for rect in _marks(svg):
        by_x.setdefault(rect.x, []).append(rect)
    return [sorted(by_x[x], key=lambda r: -r.bottom) for x in sorted(by_x)]


def _texts(group: str) -> list[str]:
    return re.findall(r"<text [^>]*>(.*?)</text>", group)


def _axes(svg: str) -> list[str]:
    axes = re.findall(r'<g class="ck-axis">(.*?)</g>', svg, re.S)
    assert len(axes) == 2
    return axes


def _x_labels(svg: str) -> list[str]:
    return _texts(_axes(svg)[0])[:-1]


def _y_labels(svg: str) -> list[str]:
    return _texts(_axes(svg)[1])[:-1]


def _legend(svg: str) -> list[str]:
    return _texts(_group(svg, "ck-legend"))


def _notes(svg: str) -> list[str]:
    return _texts(_group(svg, "ck-notes"))


def _description(svg: str) -> str:
    found = re.search(r"<desc>(.*?)</desc>", svg, re.S)
    assert found
    return found.group(1)


def _zero_and_full(svg: str) -> tuple[float, float]:
    """The y pixel of 0% and of 100%: the first and last gridline."""
    ys = [
        float(y) for y in re.findall(r'<line [^>]*y1="([^"]+)"', _group(svg, "ck-grid"))
    ]
    return ys[0], ys[-1]


def _shares(svg: str, bar: list[Rect]) -> list[float]:
    """Each segment's share in percent, read against the 0% and 100% gridlines.

    A boundary is the middle of the gap between two segments.
    """
    zero, full = _zero_and_full(svg)
    edges = [zero]
    edges += [
        (lower.y + upper.bottom) / 2 for lower, upper in zip(bar, bar[1:], strict=False)
    ]
    edges.append(bar[-1].y)
    return [
        (a - b) / (zero - full) * 100 for a, b in zip(edges, edges[1:], strict=False)
    ]


# Declaration -----------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "stacked-100"
    assert (
        KIND.description == "Bars that split each category or date into shares of 100%"
    )
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The category or date each bar stands at.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "Each part's value; never absent or negative.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            True,
            "The part: one segment per value, in legend order, bottom to top.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "width",
            OptionType.INTEGER,
            "Chart width in pixels.",
            720,
            minimum=320,
            maximum=1600,
        ),
        OptionSpec(
            "height",
            OptionType.INTEGER,
            "Chart height in pixels.",
            320,
            minimum=160,
            maximum=1200,
        ),
    )
    assert KIND.bound == MarkBound(
        400,
        "rows",
        OverBound.REFUSE,
        "A stacked-100 chart draws at most 400 rows; more are refused.",
    )
    assert KIND.max_series == 8
    assert KIND.uses_all_columns is False


# Goldens ---------------------------------------------------------------------

_LONG_A = "Long steady aerobic base session around the lake and back"
_LONG_B = "Tempo repeats on the track with a long warm-up and cool-down"
_LONG_C = "Recovery spin"
_LONG_ZONE = "Threshold intervals at the very top of the aerobic range"


def _at_bound_rows(count: int) -> list[tuple[Value, ...]]:
    """``count`` rows: 8 parts for each of count // 8 bars, totals all different."""
    rows: list[tuple[Value, ...]] = []
    for bar in range(count // 8):
        for part in range(8):
            rows.append(
                (f"Z{part + 1}", f"w{bar:02d}", float(60 + (bar * 31 + part * 17) % 97))
            )
    return rows


CASES: tuple[Case, ...] = (
    _case(
        "typical",
        [
            ("Z2", date(2026, 3, 9), 1800.0),
            ("Z1", date(2026, 3, 9), 600.0),
            ("Z3", date(2026, 3, 9), 1200.0),
            (None, date(2026, 3, 9), 300.0),
            ("Z2", date(2026, 3, 2), 3000.0),
            ("Z1", date(2026, 3, 2), 1500.0),
            ("Z3", date(2026, 3, 2), 500.0),
            ("Z1", date(2026, 3, 23), 900.0),
            ("Z3", date(2026, 3, 23), 0),
            ("Z2", date(2026, 3, 23), 2700.0),
            (None, date(2026, 3, 16), 450.0),
            ("Z2", date(2026, 3, 16), 2100.0),
            ("Z1", date(2026, 3, 16), 1350.0),
            ("Z3", date(2026, 3, 16), 150.0),
        ],
        columns=[ZONE, WEEK, SECONDS],
        channels={"x": "week", "y": "time_in_zone_s", "color": "zone"},
    ),
    _case("empty", []),
    _case(
        "single",
        [("Easy", "Wk 1", 1200.0), ("Hard", "Wk 1", 400.0), ("Long", "Wk 1", 2000.0)],
    ),
    _case(
        "zero_total",
        [
            ("Easy", "Wk 3", 1500.0),
            ("Hard", "Wk 3", 500.0),
            ("Easy", "Wk 1", 0),
            ("Hard", "Wk 1", 0),
            ("Easy", "Wk 2", 900.0),
            ("Hard", "Wk 2", 2700.0),
            ("Easy", "Wk 4", 0.0),
            ("Hard", "Wk 4", 0.0),
        ],
    ),
    _case(
        "missing_part",
        [
            ("Long", "Wk 1", 2000.0),
            ("Easy", "Wk 1", 1200.0),
            ("Hard", "Wk 1", 800.0),
            ("Easy", "Wk 2", 1800.0),
            ("Long", "Wk 2", 600.0),
            ("Hard", "Wk 3", 900.0),
            ("Long", "Wk 3", 300.0),
        ],
    ),
    _case(
        "long_labels",
        [
            (_LONG_ZONE, _LONG_A, 1400.0),
            ("Easy", _LONG_A, 3200.0),
            (_LONG_ZONE, _LONG_B, 925.0),
            ("Easy", _LONG_B, 2150.0),
            (_LONG_ZONE, _LONG_C, 400.0),
            ("Easy", _LONG_C, 1675.0),
        ],
        title="A weekly training summary with a title far longer than any chart "
        "could hope to show in one line of text",
        columns=[
            column("zone", ValueKind.CATEGORY, label=_LONG_A + " zone"),
            LABEL,
            column(
                "time_in_zone_s",
                unit="s",
                label="Total time spent in the zone during the whole training block",
            ),
        ],
    ),
    _case("at_bound", _at_bound_rows(400)),
)


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "single",
        "zero_total",
        "missing_part",
        "long_labels",
        "at_bound",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "stacked-100"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("stacked-100", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("stacked-100", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        write_golden(golden_path("stacked-100", case.name, "svg"), _text(case))


def _case_named(name: str) -> Case:
    (case,) = [c for c in CASES if c.name == name]
    return case


def test_goldens_hold_their_precondition() -> None:
    typical = _text(_case_named("typical"))
    assert len(_bars(typical)) == 4
    assert _legend(typical) == ["Z2", "Z1", "Z3", "—"]  # not alphabetical
    assert _x_labels(typical)[0] == "2026-03-02"  # rows start at 03-09
    assert len(_marks(typical)) == 13  # fourteen rows, one zero part
    totals: dict[Value, float] = {}
    for _, week, seconds in _case_named("typical").data.rows:
        assert isinstance(seconds, (int, float))
        totals[week] = totals.get(week, 0.0) + seconds
    assert len(set(totals.values())) == 4  # pairwise distinct bar totals
    zero_total = _text(_case_named("zero_total"))
    assert _notes(zero_total) == ["Zero total, no shares drawn: 2 bars."]
    assert len(_marks(zero_total)) == 4 + 2  # two bars of segments, two stubs
    missing = _text(_case_named("missing_part"))
    assert [len(bar) for bar in _bars(missing)] == [3, 2, 2]
    long_labels = _text(_case_named("long_labels"))
    assert any(label.endswith("…") for label in _x_labels(long_labels))
    assert any(label.endswith("…") for label in _legend(long_labels))
    assert _LONG_A not in _x_labels(long_labels)
    at_bound = _case_named("at_bound")
    assert len(at_bound.data.rows) == KIND.bound.limit
    assert len(_bars(_text(at_bound))) == 50
    single = _bars(_text(_case_named("single")))
    assert len(single) == 1 and len(single[0]) == 3


def test_the_empty_case_says_why() -> None:
    assert "No data: no rows." in _description(_text(_case_named("empty")))


# Shares ------------------------------------------------------------------------


def test_each_bar_splits_its_own_total_while_another_bar_differs() -> None:
    svg = _render(
        [
            ("Easy", "Wk 2", 1.0),
            ("Hard", "Wk 2", 1.0),
            ("Long", "Wk 2", 1.0),
            ("Long", "Wk 1", 300.0),  # rows out of x and legend order
            ("Easy", "Wk 1", 100.0),
            ("Hard", "Wk 1", 200.0),
        ]
    )
    wk2, wk1 = _bars(svg)  # band order is first appearance
    # Wk 1 splits 1 : 2 : 3 and Wk 2, with a different total, splits evenly.
    assert _shares(svg, wk1) == pytest.approx([100 / 6, 200 / 6, 300 / 6], abs=0.1)
    assert _shares(svg, wk2) == pytest.approx([100 / 3] * 3, abs=0.1)


def test_every_bar_reaches_100_percent() -> None:
    svg = _text(_case_named("typical"))
    zero, full = _zero_and_full(svg)
    for bar in _bars(svg):
        assert bar[0].bottom == pytest.approx(zero, abs=0.02)
        assert bar[-1].y == pytest.approx(full, abs=0.02)


def test_the_axis_runs_from_0_to_100_percent() -> None:
    svg = _render([("Easy", "A", 5.0), ("Hard", "A", 7.0)])
    labels = _y_labels(svg)
    assert labels[0] == "0%"
    assert labels[-1] == "100%"
    assert all(label.endswith("%") for label in labels)


def test_a_lone_part_fills_its_bar() -> None:
    svg = _render([("Easy", "A", 5.0), ("Easy", "B", 9.0), ("Hard", "B", 1.0)])
    lone, split = _bars(svg)
    assert _shares(svg, lone) == pytest.approx([100.0], abs=0.1)
    assert len(split) == 2


def test_a_zero_part_in_a_bar_with_shares_draws_nothing() -> None:
    svg = _render([("Easy", "A", 5.0), ("Hard", "A", 0), ("Long", "A", 5.0)])
    (bar,) = _bars(svg)
    assert [r.fill for r in bar] == [CATEGORICAL_RAMP[0], CATEGORICAL_RAMP[2]]
    assert _shares(svg, bar) == pytest.approx([50.0, 50.0], abs=0.1)
    assert "Zero total" not in svg


def test_a_share_under_a_pixel_stays_inside_its_own_interval() -> None:
    svg = _render(
        [("Easy", "A", 100000.0), ("Hard", "A", 100.0), ("Long", "A", 100000.0)]
    )
    ((low, mid, high),) = _bars(svg)
    zero, full = _zero_and_full(svg)
    first = zero - (zero - full) * 100000 / 200100  # Easy / Hard boundary
    second = zero - (zero - full) * 100100 / 200100  # Hard / Long boundary
    assert first - second < 0.2  # the share is about a tenth of a pixel
    assert mid.height > 0
    assert mid.y >= second - 0.02
    assert mid.bottom <= first + 0.02
    assert high.bottom <= mid.y < mid.bottom <= low.y


def test_a_duration_column_is_shared_out_like_a_number() -> None:
    minutes = column("elapsed", ValueKind.DURATION)
    svg = _render(
        [
            ("Easy", "A", timedelta(minutes=30)),
            ("Hard", "A", timedelta(minutes=10)),
        ],
        columns=[ZONE, LABEL, minutes],
        channels={"x": "label", "y": "elapsed", "color": "zone"},
    )
    (bar,) = _bars(svg)
    assert _shares(svg, bar) == pytest.approx([75.0, 25.0], abs=0.1)
    assert _y_labels(svg)[-1] == "100%"


# Order, gaps and widths ---------------------------------------------------------


def test_segments_rise_in_first_appearance_order_not_alphabetical() -> None:
    svg = _render(
        [
            ("Tempo", "A", 2.0),
            ("Easy", "A", 5.0),
            ("Long", "A", 3.0),
        ]
    )
    (bar,) = _bars(svg)
    assert [r.fill for r in bar] == list(CATEGORICAL_RAMP[:3])
    assert _legend(svg) == ["Tempo", "Easy", "Long"]
    assert _shares(svg, bar) == pytest.approx([20.0, 50.0, 30.0], abs=0.1)


def test_adjacent_segments_leave_a_one_pixel_gap() -> None:
    svg = _render([("Easy", "A", 2.0), ("Hard", "A", 5.0), ("Long", "A", 3.0)])
    (bar,) = _bars(svg)
    assert [
        lower.y - upper.bottom for lower, upper in zip(bar, bar[1:], strict=False)
    ] == (pytest.approx([1.0, 1.0], abs=0.02))


def test_the_gap_is_split_evenly_across_the_boundary() -> None:
    svg = _render([("Easy", "A", 1.0), ("Hard", "A", 1.0)])
    (bar,) = _bars(svg)
    zero, full = _zero_and_full(svg)
    middle = (zero + full) / 2
    assert bar[0].y == pytest.approx(middle + 0.5, abs=0.02)
    assert bar[1].bottom == pytest.approx(middle - 0.5, abs=0.02)
    assert bar[0].bottom == pytest.approx(zero, abs=0.02)  # no gap at the base
    assert bar[1].y == pytest.approx(full, abs=0.02)  # nor at the top


def test_a_lone_bar_is_capped_at_48_px() -> None:
    svg = _render([("Easy", "Solo", 7.0), ("Hard", "Solo", 3.0)])
    assert [r.width for r in _marks(svg)] == [48.0, 48.0]


def test_bars_fill_80_percent_of_a_narrow_band() -> None:
    names = [f"c{i:02d}" for i in range(12)]
    svg = _render([("Easy", n, float(i + 1)) for i, n in enumerate(names)])
    bars = _bars(svg)
    spacing = bars[1][0].x - bars[0][0].x
    assert spacing < 60  # 80% of the band is under the 48 px cap
    for bar in bars:
        assert bar[0].width == pytest.approx(0.8 * spacing, abs=0.02)


# Categories ---------------------------------------------------------------------


def test_dates_ascend_and_the_absent_x_is_last() -> None:
    svg = _render(
        [
            ("Easy", date(2026, 3, 9), 1.0),
            ("Easy", None, 1.0),
            ("Easy", date(2026, 3, 2), 1.0),
        ],
        columns=[ZONE, WEEK, SECONDS],
        channels={"x": "week", "y": "time_in_zone_s", "color": "zone"},
    )
    assert _x_labels(svg) == ["2026-03-02", "2026-03-09", "—"]


def test_absent_colour_is_the_last_series_labelled_with_a_dash() -> None:
    svg = _render(
        [
            (None, "A", 1.0),
            ("Run", "A", 2.0),
            ("Bike", "A", 3.0),
        ]
    )
    assert _legend(svg) == ["Run", "Bike", "—"]
    (bar,) = _bars(svg)
    assert bar[-1].fill == CATEGORICAL_RAMP[2]
    assert _shares(svg, bar) == pytest.approx(
        [2 / 6 * 100, 3 / 6 * 100, 1 / 6 * 100], abs=0.1
    )


# Zero totals ----------------------------------------------------------------------


def test_an_all_zero_bar_is_one_stub_and_a_singular_note() -> None:
    svg = _render(
        [
            ("Easy", "A", 4.0),
            ("Hard", "A", 6.0),
            ("Easy", "B", 0),
            ("Hard", "B", 0.0),
        ]
    )
    split, stub_bar = _bars(svg)
    assert len(split) == 2
    (stub,) = stub_bar
    zero, _ = _zero_and_full(svg)
    assert stub.height == 2.0
    assert stub.y + 1 == pytest.approx(zero, abs=0.02)
    assert stub.fill == STROKE.base
    assert stub.width == split[0].width
    assert _notes(svg) == ["Zero total, no shares drawn: 1 bar."]


def test_two_zero_bars_are_counted_in_the_plural() -> None:
    svg = _text(_case_named("zero_total"))
    assert _notes(svg) == ["Zero total, no shares drawn: 2 bars."]
    stubs = [r for r in _marks(svg) if r.height == 2.0]
    assert [r.fill for r in stubs] == [STROKE.base, STROKE.base]


def test_every_bar_zero_still_draws_the_stubs_and_the_note() -> None:
    svg = _render([("Easy", "A", 0), ("Easy", "B", 0)])
    assert len(_marks(svg)) == 2
    assert _notes(svg) == ["Zero total, no shares drawn: 2 bars."]


def test_without_a_zero_total_there_is_no_note() -> None:
    assert "ck-notes" not in _text(_case_named("typical"))


# Missing, absent, negative ----------------------------------------------------------


def test_a_missing_part_row_draws_no_segment_and_refuses_nothing() -> None:
    svg = _text(_case_named("missing_part"))
    wk1, wk2, wk3 = _bars(svg)
    # Legend order is Long, Easy, Hard (ramp 0, 1, 2).
    assert [r.fill for r in wk2] == [CATEGORICAL_RAMP[0], CATEGORICAL_RAMP[1]]
    assert [r.fill for r in wk3] == [CATEGORICAL_RAMP[0], CATEGORICAL_RAMP[2]]
    assert _shares(svg, wk2) == pytest.approx([25.0, 75.0], abs=0.1)
    assert _shares(svg, wk3) == pytest.approx([25.0, 75.0], abs=0.1)
    assert len(wk1) == 3


def test_an_absent_part_is_refused_alone() -> None:
    (problem,) = _problems(
        [("Easy", "A", 2.0), ("Hard", "A", 1.0), ("Long", "A", None)]
    )
    assert problem.code is ProblemCode.STACK_ABSENT
    assert problem.row == 2


def test_a_negative_part_is_refused_alone() -> None:
    (problem,) = _problems(
        [("Easy", "A", 2.0), ("Hard", "A", 1.0), ("Long", "A", -1.5)]
    )
    assert problem.code is ProblemCode.STACK_NEGATIVE
    assert problem.row == 2


def test_every_part_absent_is_refused() -> None:
    (problem,) = _problems([("Easy", "A", None), ("Hard", "A", None)])
    assert problem.code is ProblemCode.STACK_ABSENT


def test_two_rows_at_one_x_and_colour_are_refused_alone() -> None:
    (problem,) = _problems([("Easy", "A", 1.0), ("Easy", "B", 2.0), ("Easy", "A", 3.0)])
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 2
    assert "row 0" in problem.message


def test_the_same_x_with_different_colours_is_not_a_duplicate() -> None:
    assert _render([("Easy", "A", 1.0), ("Hard", "A", 2.0)])


def test_two_rows_with_absent_x_collide_because_absent_is_a_category() -> None:
    (problem,) = _problems([("Easy", None, 1.0), ("Easy", None, 2.0)])
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 1


# Bounds ---------------------------------------------------------------------------


def test_400_rows_render_and_401_are_refused_alone() -> None:
    assert _render(_at_bound_rows(400))
    rows = _at_bound_rows(400) + [("Z1", "extra", 1.0)]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.rows == 401


def test_8_parts_render_and_9_are_refused_alone() -> None:
    assert _render([(f"p{i}", "A", float(i + 1)) for i in range(8)])
    (problem,) = _problems([(f"p{i}", "A", float(i + 1)) for i in range(9)])
    assert problem.code is ProblemCode.TOO_MANY_SERIES


def test_the_bound_and_the_stack_are_reported_together() -> None:
    rows = _at_bound_rows(400) + [("Z1", "extra", -1.0)]
    assert [p.code for p in _problems(rows)] == [
        ProblemCode.OVER_BOUND,
        ProblemCode.STACK_NEGATIVE,
    ]


# Description and layout -------------------------------------------------------------


def test_description_summarises_the_chart() -> None:
    svg = _render([("Easy", "Wk 1", 5.0), ("Hard", "Wk 1", 0), ("Easy", "Wk 2", 12.5)])
    assert _description(svg) == (
        "Stacked-100 chart: Time in zone. x: label; y: time in zone (m:ss); "
        "color: zone. 3 rows, 2 series. label from Wk 1 to Wk 2; "
        "share (%) from 0% to 100%."
    )


def test_the_description_names_the_bound_y_column() -> None:
    watts = column("mean_power_w", unit="w", label="Mean power")
    number = _render(
        [("Easy", "A", 5.0), ("Hard", "A", 7.0)],
        columns=[ZONE, LABEL, watts],
        channels={"x": "label", "y": "mean_power_w", "color": "zone"},
    )
    assert "y: Mean power (W);" in _description(number)
    elapsed = column("elapsed", ValueKind.DURATION, label="Time on feet")
    channels = {"x": "label", "y": "elapsed", "color": "zone"}
    short = _render(
        [("Easy", "A", timedelta(minutes=30)), ("Hard", "A", timedelta(minutes=10))],
        columns=[ZONE, LABEL, elapsed],
        channels=channels,
    )
    assert "y: Time on feet (m:ss);" in _description(short)
    long = _render(
        [("Easy", "A", timedelta(minutes=90)), ("Hard", "A", timedelta(minutes=10))],
        columns=[ZONE, LABEL, elapsed],
        channels=channels,
    )
    assert "y: Time on feet (h:mm:ss);" in _description(long)
    # The A1 edge: exactly one hour, and 3599.6 s (which rounds to an hour).
    for seconds in (3600.0, 3599.6):
        edge = _render(
            [
                ("Easy", "A", timedelta(seconds=seconds)),
                ("Hard", "A", timedelta(minutes=10)),
            ],
            columns=[ZONE, LABEL, elapsed],
            channels=channels,
        )
        assert "y: Time on feet (h:mm:ss);" in _description(edge), seconds


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    svg = _text(case)
    width = float(re.search(r'<svg [^>]*width="([^"]+)"', svg).group(1))  # type: ignore[union-attr]
    found = re.findall(
        r'<text x="([^"]+)" y="[^"]+"(?: text-anchor="([^"]+)")? '
        r'font-size="([^"]+)"[^>]*>(.*?)</text>',
        svg,
    )
    assert found
    assert len(found) == svg.count("<text ")
    for x, anchor, size, content in found:
        reach = text_width(content, float(size))
        left = (
            float(x) - reach / 2
            if anchor == "middle"
            else float(x) - reach
            if anchor == "end"
            else float(x)
        )
        assert left >= 8.0 - 1e-6, content
        assert left + reach <= width - 4.0 + 1e-6, content


if __name__ == "__main__":
    main()
