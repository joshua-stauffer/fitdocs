"""The ``bar`` kind: bands, grouping, stacking, refusals and goldens.

Regenerate the goldens with ``uv run python -m tests.render.charts.kit.test_bar``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, timedelta
from typing import NamedTuple

import pytest

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.bar import KIND
from fitdocs.render.charts.kit.layout import text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    ChartRequest,
    MarkBound,
    OptionSpec,
    OptionType,
    OptionValue,
    Output,
    OverBound,
)
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

SPORT = column("sport", ValueKind.CATEGORY)
DAY = column("day", ValueKind.CATEGORY)
KM = column("distance_km", unit="km")
WEEK = column("week", ValueKind.DATE)

# Columns (sport, day, km): neither x nor y is column 0, colour precedes both.
COLUMNS = [SPORT, DAY, KM]
PLAIN = {"x": "day", "y": "distance_km"}
COLOURED = {**PLAIN, "color": "sport"}


def _request(
    *,
    coloured: bool = False,
    stack: bool | None = None,
    title: str = "Weekly distance",
    channels: dict[str, str] | None = None,
) -> ChartRequest:
    options: dict[str, OptionValue] = {} if stack is None else {"stack": stack}
    return chart_request(
        "bar",
        title=title,
        channels=channels or (COLOURED if coloured else PLAIN),
        options=options,
    )


def _case(
    name: str,
    rows: Sequence[Sequence[Value]],
    *,
    coloured: bool = False,
    stack: bool | None = None,
    title: str = "Weekly distance",
    columns: Sequence[Column] = COLUMNS,
    channels: dict[str, str] | None = None,
) -> Case:
    request = _request(coloured=coloured, stack=stack, title=title, channels=channels)
    return Case(name, request, chart_data(columns, rows))


def _text(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


def _render(
    rows: Sequence[Sequence[Value]],
    *,
    coloured: bool = False,
    stack: bool | None = None,
    columns: Sequence[Column] = COLUMNS,
    channels: dict[str, str] | None = None,
) -> str:
    return _text(
        _case(
            "t",
            rows,
            coloured=coloured,
            stack=stack,
            columns=columns,
            channels=channels,
        )
    )


def _problems(
    rows: Sequence[Sequence[Value]],
    *,
    coloured: bool = False,
    stack: bool | None = None,
) -> tuple[ChartProblem, ...]:
    case = _case("t", rows, coloured=coloured, stack=stack)
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


def _texts(group: str) -> list[str]:
    return re.findall(r"<text [^>]*>(.*?)</text>", group)


def _x_labels(svg: str) -> list[str]:
    """The bottom axis's tick labels (its last text is the axis title)."""
    first_axis = re.search(r'<g class="ck-axis">(.*?)</g>', svg, re.S)
    assert first_axis
    return _texts(first_axis.group(1))[:-1]


def _x_centres(svg: str) -> list[float]:
    """The bottom axis's band centres, from its tick label positions."""
    first_axis = re.search(r'<g class="ck-axis">(.*?)</g>', svg, re.S)
    assert first_axis
    found = re.findall(r'<text x="([^"]+)"', first_axis.group(1))
    return [float(x) for x in found[:-1]]


def _y_labels(svg: str) -> list[str]:
    axes = re.findall(r'<g class="ck-axis">(.*?)</g>', svg, re.S)
    assert len(axes) == 2
    return _texts(axes[1])[:-1]


def _legend(svg: str) -> list[str]:
    return _texts(_group(svg, "ck-legend"))


def _description(svg: str) -> str:
    found = re.search(r"<desc>(.*?)</desc>", svg, re.S)
    assert found
    return found.group(1)


def _by_x(rects: list[Rect]) -> list[Rect]:
    return sorted(rects, key=lambda r: r.x)


# Declaration -----------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "bar"
    assert (
        KIND.description
        == "Vertical bars per category or date, grouped or stacked by colour"
    )
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The category or date each bar group stands at.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The bar's value; the axis always includes zero.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "Splits each group into one bar per value, in legend order.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "stack",
            OptionType.BOOLEAN,
            "Stack the colour series instead of placing them side by side.",
            False,
        ),
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
        200,
        "rows",
        OverBound.REFUSE,
        "A bar chart draws at most 200 rows; more are refused.",
    )
    assert KIND.max_series == 8
    assert KIND.uses_all_columns is False


# Goldens ---------------------------------------------------------------------

_LONG_A = "Long steady aerobic base session around the lake and back"
_LONG_B = "Tempo repeats on the track with a long warm-up and cool-down"
_LONG_C = "Recovery spin"


def _at_bound_rows(count: int) -> list[tuple[Value, ...]]:
    rows: list[tuple[Value, ...]] = []
    for index in range(count // 2):
        label = f"d{index:03d}"
        rows.append(("Run", label, round(5 + (index * 37 % 91) / 3, 2)))
        rows.append(("Bike", label, round(10 + (index * 53 % 89) / 4, 2)))
    return rows


CASES: tuple[Case, ...] = (
    _case(
        "typical",
        [
            ("Run", "Wed", 12.5),
            ("Bike", "Wed", 30.0),
            ("Run", "Mon", 0),
            ("Bike", "Mon", 45.5),
            ("Run", "Fri", None),
            ("Bike", "Fri", 22.25),
            ("Run", "Tue", 8.0),
            ("Bike", "Tue", 18.0),
            ("Run", None, 6.75),
            (None, "Tue", 3.5),
        ],
        coloured=True,
    ),
    _case("empty", []),
    _case(
        "all_absent",
        [("Run", "Mon", None), ("Run", "Tue", None), ("Run", "Wed", None)],
    ),
    _case("single", [("Run", "Solo", 7.5)]),
    _case(
        "negative",
        [
            ("Run", "Mon", -5.5),
            ("Run", "Tue", 12.0),
            ("Run", "Wed", -20.25),
            ("Run", "Thu", 3.0),
        ],
    ),
    _case(
        "long_labels",
        [
            ("Run", _LONG_A, 14.5),
            ("Bike", _LONG_A, 32.0),
            ("Run", _LONG_B, 9.25),
            ("Bike", _LONG_B, 21.5),
            ("Run", _LONG_C, 4.0),
            ("Bike", _LONG_C, 16.75),
        ],
        coloured=True,
        title="A weekly training summary with a title far longer than any chart "
        "could hope to show in one line of text",
        columns=[
            column("sport", ValueKind.CATEGORY, label=_LONG_A + " sport"),
            DAY,
            column(
                "distance_km",
                unit="km",
                label="Total distance covered during the whole training block",
            ),
        ],
    ),
    _case("at_bound", _at_bound_rows(200), coloured=True),
    _case(
        "stacked",
        [
            ("Tempo", "Wk 3", 9.5),
            ("Easy", "Wk 3", 21.0),
            ("Long", "Wk 3", 16.5),
            ("Tempo", "Wk 1", 6.25),
            ("Easy", "Wk 1", 18.5),
            ("Tempo", "Wk 2", 0),
            ("Easy", "Wk 2", 24.25),
            ("Long", "Wk 2", 20.0),
            ("Tempo", "Wk 4", 12.0),
            ("Easy", "Wk 4", 15.75),
            ("Long", "Wk 4", 28.75),
        ],
        coloured=True,
        stack=True,
    ),
    _case(
        "dates",
        [
            ("Run", date(2026, 3, 16), 20.5),
            ("Run", date(2026, 3, 2), 10.25),
            ("Run", date(2026, 3, 30), 50.0),
            ("Run", date(2026, 3, 9), 15.75),
            ("Run", date(2026, 3, 23), 35.5),
            ("Run", date(2026, 4, 6), 41.0),
        ],
        columns=[SPORT, WEEK, KM],
        channels={"x": "week", "y": "distance_km"},
    ),
)


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "long_labels",
        "at_bound",
        "stacked",
        "dates",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "bar"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("bar", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("bar", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        write_golden(golden_path("bar", case.name, "svg"), _text(case))


def _case_named(name: str) -> Case:
    (case,) = [c for c in CASES if c.name == name]
    return case


def test_goldens_hold_their_precondition() -> None:
    long_labels = _text(_case_named("long_labels"))
    assert any(label.endswith("…") for label in _x_labels(long_labels))
    assert _LONG_A not in _x_labels(long_labels)
    typical = _text(_case_named("typical"))
    assert len(_marks(typical)) == 9  # ten rows, one absent
    at_bound = _case_named("at_bound")
    assert len(at_bound.data.rows) == KIND.bound.limit
    assert "Not drawn" not in _text(_case_named("stacked"))
    dates = _text(_case_named("dates"))
    assert _x_labels(dates)[0] == "2026-03-02"


def test_empty_and_all_absent_say_why() -> None:
    assert "No data: no rows." in _description(_text(_case_named("empty")))
    assert "No data: none of the 3 rows has a value to draw." in _description(
        _text(_case_named("all_absent"))
    )


# Categories and dates ---------------------------------------------------------


def test_categories_keep_first_appearance_with_absent_last() -> None:
    svg = _render(
        [
            ("Run", "Wed", 1.5),
            ("Run", None, 2.5),
            ("Run", "Mon", 3.5),
            ("Run", "Fri", 4.5),
        ]
    )
    assert _x_labels(svg) == ["Wed", "Mon", "Fri", "—"]
    # Bars follow the same left-to-right order: heights by position.
    heights = [r.height for r in _by_x(_marks(svg))]
    assert [h / heights[0] for h in heights] == pytest.approx(
        [1.0, 3.5 / 1.5, 4.5 / 1.5, 2.5 / 1.5], abs=0.02
    )


def test_bars_stand_at_their_category_not_their_row() -> None:
    svg = _render(
        [
            ("Run", "Wed", 3.0),
            ("Run", None, 1.0),
            ("Run", "Mon", 2.0),
        ]
    )
    # Left to right: Wed (3), Mon (2), absent (1): heights fall.
    heights = [r.height for r in _by_x(_marks(svg))]
    assert heights == sorted(heights, reverse=True)
    assert len(set(heights)) == 3


def test_dates_ascend_from_unsorted_rows() -> None:
    svg = _render(
        [
            ("Run", date(2026, 3, 9), 30.0),
            ("Run", date(2026, 3, 2), 10.0),
            ("Run", date(2026, 3, 23), 40.0),
            ("Run", date(2026, 3, 16), 20.0),
        ],
        columns=[SPORT, WEEK, KM],
        channels={"x": "week", "y": "distance_km"},
    )
    assert _x_labels(svg) == ["2026-03-02", "2026-03-09", "2026-03-16", "2026-03-23"]
    heights = [r.height for r in _by_x(_marks(svg))]
    assert [h / heights[0] for h in heights] == pytest.approx(
        [1.0, 3.0, 2.0, 4.0], abs=0.02
    )


def test_absent_colour_is_the_last_series_labelled_with_a_dash() -> None:
    svg = _render(
        [
            (None, "Mon", 1.0),
            ("Run", "Mon", 2.0),
            ("Bike", "Mon", 3.0),
        ],
        coloured=True,
    )
    assert _legend(svg) == ["Run", "Bike", "—"]


# Zero, absent and negative -----------------------------------------------------


@pytest.mark.parametrize("zero", [0, 0.0])
def test_a_zero_bar_is_a_stub_and_an_absent_bar_is_nothing(zero: Value) -> None:
    svg = _render(
        [
            ("Run", "A", 5.0),
            ("Run", "B", zero),
            ("Run", "C", None),
            ("Run", "D", None),
        ]
    )
    marks = _by_x(_marks(svg))
    assert len(marks) == 2  # A and the stub; C and D draw nothing
    bar, stub = marks
    assert stub.height == 2.0
    assert bar.height > 2.0
    assert stub.y + 1 == pytest.approx(bar.bottom, abs=0.02)  # stub on the zero line
    assert stub.width == bar.width
    note = "Not drawn: 2 rows without y."
    assert _texts(_group(svg, "ck-notes")) == [note]
    assert note in _description(svg)


def test_a_row_absent_on_y_alone_is_counted_once_in_the_singular() -> None:
    svg = _render([("Run", "A", 5.0), ("Run", None, None)])
    assert _texts(_group(svg, "ck-notes")) == ["Not drawn: 1 row without y."]
    assert _x_labels(svg) == ["A", "—"]  # the absent x keeps its category


def test_negative_values_extend_below_the_zero_line() -> None:
    svg = _render([("Run", "A", 12.0), ("Run", "B", -5.5), ("Run", "C", 0)])
    up, down, stub = _by_x(_marks(svg))
    assert down.y == pytest.approx(up.bottom, abs=0.02)
    assert down.height / up.height == pytest.approx(5.5 / 12.0, abs=0.01)
    assert stub.y + 1 == pytest.approx(up.bottom, abs=0.02)


def test_the_value_axis_includes_zero() -> None:
    svg = _render([("Run", "A", 30.0), ("Run", "B", 45.0), ("Run", "C", 60.0)])
    assert "0" in _y_labels(svg)
    all_negative = _render([("Run", "A", -30.0), ("Run", "B", -60.0)])
    assert "0" in _y_labels(all_negative)


# Widths -------------------------------------------------------------------------


def test_a_lone_bar_is_capped_at_48_px() -> None:
    (rect,) = _marks(_render([("Run", "Solo", 7.5)]))
    assert rect.width == 48.0


def test_bars_fill_80_percent_of_a_narrow_band() -> None:
    names = [f"c{i:02d}" for i in range(12)]
    svg = _render([("Run", n, float(i + 1)) for i, n in enumerate(names)])
    rects = _by_x(_marks(svg))
    spacing = rects[1].x - rects[0].x
    assert spacing < 60  # 80% of the band is under the 48 px cap
    for rect in rects:
        assert rect.width == pytest.approx(0.8 * spacing, abs=0.02)


def test_grouped_bars_share_80_percent_of_the_band_in_legend_order() -> None:
    names = [f"c{i}" for i in range(8)]
    rows: list[tuple[Value, ...]] = []
    for index, name in enumerate(names):
        rows.append(("Run", name, float(index + 1)))
        rows.append(("Bike", name, float(index + 10)))
        rows.append(("Swim", name, float(index + 20)))
    svg = _render(rows, coloured=True)
    rects = _marks(svg)
    colours = {
        "Run": CATEGORICAL_RAMP[0],
        "Bike": CATEGORICAL_RAMP[1],
        "Swim": CATEGORICAL_RAMP[2],
    }
    assert len(rects) == 24
    first_band = _by_x(rects)[:3]
    assert [r.fill for r in first_band] == [
        colours["Run"],
        colours["Bike"],
        colours["Swim"],
    ]
    width = first_band[0].width
    assert [r.width for r in first_band] == [width] * 3
    assert first_band[1].x == pytest.approx(first_band[0].x + width, abs=0.02)
    assert first_band[2].x == pytest.approx(first_band[1].x + width, abs=0.02)
    second_band = _by_x(rects)[3]
    spacing = second_band.x - first_band[0].x
    assert 3 * width == pytest.approx(0.8 * spacing, abs=0.03)
    assert 3 * width < 3 * 48


def test_grouped_slots_belong_to_series_even_when_a_row_is_missing() -> None:
    svg = _render(
        [
            ("Run", "A", 1.0),
            ("Bike", "A", 2.0),
            ("Bike", "B", 3.0),
        ],
        coloured=True,
    )
    by_x = _by_x(_marks(svg))
    run_a, bike_a, bike_b = by_x
    assert run_a.fill == CATEGORICAL_RAMP[0]
    assert bike_a.fill == CATEGORICAL_RAMP[1]
    assert bike_b.fill == CATEGORICAL_RAMP[1]
    centre_a, centre_b = _x_centres(svg)
    offset = bike_a.x - centre_a
    # Band B has no Run row: the Bike bar keeps the slot it has in band A.
    assert bike_b.x - centre_b == pytest.approx(offset, abs=0.02)
    assert offset == pytest.approx(0.0, abs=0.02)  # slot 1 of 2 starts at the centre
    assert offset != pytest.approx(-bike_b.width / 2, abs=0.02)  # not a lone bar


# Stacking -----------------------------------------------------------------------


def test_stacked_segments_rise_in_legend_order() -> None:
    svg = _render(
        [
            ("Tempo", "A", 2.0),
            ("Easy", "A", 5.0),
            ("Long", "A", 3.0),
        ],
        coloured=True,
        stack=True,
    )
    rects = _marks(svg)
    assert len(rects) == 3
    by_fill = {r.fill: r for r in rects}
    tempo, easy, long = (by_fill[CATEGORICAL_RAMP[i]] for i in range(3))
    assert tempo.x == easy.x == long.x
    assert easy.bottom == pytest.approx(tempo.y, abs=0.02)
    assert long.bottom == pytest.approx(easy.y, abs=0.02)
    assert long.y < easy.y < tempo.y < tempo.bottom
    assert [r.height / tempo.height for r in (easy, long)] == pytest.approx(
        [2.5, 1.5], abs=0.02
    )


def test_a_stacked_bar_is_capped_at_48_px() -> None:
    svg = _render([("Tempo", "A", 2.0), ("Easy", "A", 5.0)], coloured=True, stack=True)
    assert [r.width for r in _marks(svg)] == [48.0, 48.0]


def test_a_missing_series_row_in_a_stack_draws_no_segment() -> None:
    svg = _render(
        [
            ("Tempo", "A", 2.0),
            ("Easy", "A", 5.0),
            ("Tempo", "B", 4.0),
        ],
        coloured=True,
        stack=True,
    )
    rects = _marks(svg)
    assert len(rects) == 3  # three rows, three segments; B has no Easy
    band_b = [r for r in rects if r.x == max(x.x for x in rects)]
    assert [r.fill for r in band_b] == [CATEGORICAL_RAMP[0]]


def test_a_zero_segment_in_a_stack_is_a_stub_on_the_segment_baseline() -> None:
    svg = _render(
        [("Tempo", "A", 2.0), ("Easy", "A", 0), ("Long", "A", 3.0)],
        coloured=True,
        stack=True,
    )
    by_fill = {r.fill: r for r in _marks(svg)}
    tempo, easy, long = (by_fill[CATEGORICAL_RAMP[i]] for i in range(3))
    assert easy.height == 2.0
    assert easy.y + 1 == pytest.approx(tempo.y, abs=0.02)
    assert long.bottom == pytest.approx(tempo.y, abs=0.02)


def test_an_unstacked_chart_accepts_absent_and_negative_values() -> None:
    svg = _render(
        [("Run", "A", None), ("Run", "B", -2.0), ("Run", "C", 4.0)], stack=False
    )
    assert len(_marks(svg)) == 2


# Refusals -----------------------------------------------------------------------


def test_stack_with_an_absent_value_is_refused_alone() -> None:
    (problem,) = _problems(
        [("Tempo", "A", 2.0), ("Easy", "A", None)], coloured=True, stack=True
    )
    assert problem.code is ProblemCode.STACK_ABSENT
    assert problem.row == 1


def test_stack_with_a_negative_value_is_refused_alone() -> None:
    (problem,) = _problems(
        [("Tempo", "A", 2.0), ("Easy", "A", -1.5)], coloured=True, stack=True
    )
    assert problem.code is ProblemCode.STACK_NEGATIVE
    assert problem.row == 1


def test_stack_does_not_demand_a_row_for_every_series() -> None:
    assert _render([("Tempo", "A", 2.0), ("Easy", "B", 1.0)], coloured=True, stack=True)


def test_two_rows_at_one_x_and_colour_are_refused_alone() -> None:
    (problem,) = _problems(
        [("Run", "A", 1.0), ("Run", "B", 2.0), ("Run", "A", 3.0)], coloured=True
    )
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 2
    assert "row 0" in problem.message


def test_the_same_x_with_different_colours_is_not_a_duplicate() -> None:
    assert _render([("Run", "A", 1.0), ("Bike", "A", 2.0)], coloured=True)


def test_two_rows_with_absent_x_collide_because_absent_is_a_category() -> None:
    (problem,) = _problems([("Run", None, 1.0), ("Run", None, 2.0)])
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 1


def test_more_than_eight_series_are_refused_alone() -> None:
    rows: list[tuple[Value, ...]] = [(f"s{i}", "A", float(i + 1)) for i in range(9)]
    (problem,) = _problems(rows, coloured=True)
    assert problem.code is ProblemCode.TOO_MANY_SERIES


def test_200_rows_render_and_201_are_refused_alone() -> None:
    assert _render(_at_bound_rows(200), coloured=True)
    rows = _at_bound_rows(200) + [("Run", "extra", 1.0)]
    (problem,) = _problems(rows, coloured=True)
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.rows == 201


def test_a_stacked_chart_reports_the_bound_and_the_stack_together() -> None:
    rows = _at_bound_rows(200) + [("Run", "extra", -1.0)]
    codes = [p.code for p in _problems(rows, coloured=True, stack=True)]
    assert codes == [ProblemCode.OVER_BOUND, ProblemCode.STACK_NEGATIVE]


def test_description_summarises_the_chart() -> None:
    svg = _render(
        [("Run", "A", 5.0), ("Run", "B", 0), ("Run", "C", None), ("Run", "D", 12.5)]
    )
    assert _description(svg) == (
        "Bar chart: Weekly distance. x: day; y: distance (km). 4 rows. "
        "Not drawn: 1 row without y. day from A to D; "
        "distance (km) from 0 km to 12.5 km."
    )


def test_duration_ranges_use_the_axis_form() -> None:
    minutes = column("elapsed", ValueKind.DURATION)
    short = _render(
        [("Run", "A", timedelta(minutes=45)), ("Run", "B", timedelta(minutes=25))],
        columns=[SPORT, DAY, minutes],
        channels={"x": "day", "y": "elapsed"},
    )
    assert "elapsed (m:ss) from 25:00 to 45:00." in _description(short)
    long = _render(
        [("Run", "A", timedelta(minutes=45)), ("Run", "B", timedelta(minutes=90))],
        columns=[SPORT, DAY, minutes],
        channels={"x": "day", "y": "elapsed"},
    )
    assert "elapsed (h:mm:ss) from 0:45:00 to 1:30:00." in _description(long)
    niced = _render(
        [("Run", "A", timedelta(minutes=20)), ("Run", "B", timedelta(minutes=55))],
        columns=[SPORT, DAY, minutes],
        channels={"x": "day", "y": "elapsed"},
    )
    assert "elapsed (h:mm:ss) from 0:20:00 to 0:55:00." in _description(niced)


def test_duration_unit_number_ranges_use_the_axis_form() -> None:
    moving = column("moving_time", unit="s")
    channels = {"x": "day", "y": "moving_time"}
    short = _render(
        [("Run", "A", 2700.0), ("Run", "B", 1500.0)],
        columns=[SPORT, DAY, moving],
        channels=channels,
    )
    assert "moving time (m:ss) from 25:00 to 45:00." in _description(short)
    long = _render(
        [("Run", "A", 2700.0), ("Run", "B", 5400.0)],
        columns=[SPORT, DAY, moving],
        channels=channels,
    )
    assert "moving time (h:mm:ss) from 0:45:00 to 1:30:00." in _description(long)
    niced = _render(
        [("Run", "A", 1200.0), ("Run", "B", 3300.0)],
        columns=[SPORT, DAY, moving],
        channels=channels,
    )
    assert "moving time (h:mm:ss) from 0:20:00 to 0:55:00." in _description(niced)


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


def test_stacked_stubs_are_drawn_after_every_segment() -> None:
    svg = _render(
        [("Tempo", "A", 2.0), ("Easy", "A", 0), ("Long", "A", 3.0)],
        coloured=True,
        stack=True,
    )
    heights = [r.height for r in _marks(svg)]
    assert sorted(heights)[0] == 2.0
    assert heights[-1] == 2.0  # the stub is last, on top of Long's segment
    assert len([h for h in heights if h == 2.0]) == 1


if __name__ == "__main__":
    main()
