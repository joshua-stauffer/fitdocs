"""The ``mean-max`` kind: declaration, refusals, landmark ticks, labels and goldens.

Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.13, 9.1, 9.2, 9.3,
9.4, 9.5, 9.6, 9.7, 12.1, 12.3.

Run ``uv run python -m tests.render.charts.kit.test_mean_max`` to (re)write the
goldens under ``golden/mean-max/``; a pytest run never writes them.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import timedelta

import pytest

from fitdocs.metrics.mean_max_sources import MEAN_MAX_DURATIONS_S
from fitdocs.render.charts.kit import api, registry
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds import mean_max
from fitdocs.render.charts.kit.kinds.mean_max import KIND
from fitdocs.render.charts.kit.layout import text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import ScaleType, numeric_scale
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    OptionValue,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import series_style
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

PERIOD = column("period", ValueKind.CATEGORY)
DURATION = column("duration_s", unit="s")
POWER = column("power_w", unit="w")
CHANNELS = {"x": "duration_s", "y": "power_w", "color": "period"}
CHANNELS_XY = {"x": "duration_s", "y": "power_w"}

SVG = "{http://www.w3.org/2000/svg}"


def _render(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
    *,
    title: str = "Power curve",
) -> str:
    request = chart_request(
        "mean-max", ref="m1", title=title, channels=channels, options=options
    )
    return render_case(KIND, request, chart_data(columns, rows)).text


def _refusal(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
) -> tuple[ChartProblem, ...]:
    request = chart_request("mean-max", ref="m1", channels=channels)
    return problems_of(KIND, request, chart_data(columns, rows))


# --- the golden fixtures --------------------------------------------------------

# The durations of fitdocs.metrics.mean_max_sources up to one hour; a test pins
# this tuple against that module.
DURATIONS: tuple[float, ...] = (
    1.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 120.0, 180.0, 240.0,
    300.0, 360.0, 480.0, 600.0, 720.0, 900.0, 1200.0, 1800.0, 2400.0,
    2700.0, 3600.0,
)  # fmt: skip
THIS_SEASON: tuple[float | None, ...] = (
    1480.0, 1010.0, 880.0, 820.0, 790.0, 740.0, 700.0, 650.0, 520.0, 450.0,
    415.0, 390.0, 365.0, None, 325.0, 310.0, 300.0, 280.0, 265.0, 258.0,
    255.0, 240.0,
)  # fmt: skip
LAST_SEASON: tuple[float | None, ...] = (
    1420.0, 1060.0, 860.0, 800.0, 770.0, 735.0, 690.0, 635.0, 535.0, 470.0,
    430.0, 400.0, 375.0, 350.0, 330.0, 315.0, 295.0, 270.0, 250.0, 244.0,
    238.0, 231.0,
)  # fmt: skip

SHUFFLE_STRIDE = 7  # coprime with the 44 rows, so the shuffle visits every row


def _typical_rows() -> tuple[tuple[Value, ...], ...]:
    """Two seasons, This season first; shuffled so no period is in x order.

    This season's 480 s power is absent, between two present values.
    """
    rows: list[tuple[Value, ...]] = []
    for i, d in enumerate(DURATIONS):
        rows.append((d, THIS_SEASON[i], "This season"))
        rows.append((d, LAST_SEASON[i], "Last season"))
    return tuple(rows[(i * SHUFFLE_STRIDE) % len(rows)] for i in range(len(rows)))


TYPICAL_ROWS = _typical_rows()
TYPICAL_DESCRIPTION = (
    "Mean-max chart: Power curve. x: duration (h:mm:ss); y: power (W); color: period."
    " 44 rows, 2 series. Not drawn: 1 row without y."
    " duration (h:mm:ss) from 0:00:01 to 1:00:00; power (W) from 231 W to 1480 W."
)

ABSENT_ROWS: tuple[tuple[Value, ...], ...] = (
    (60.0, None, "This season"),
    (None, 300.0, "Last season"),
    (None, None, None),
)

NEGATIVE_Y = column("delta_w", unit="w")
NEGATIVE_ROWS: tuple[tuple[Value, ...], ...] = tuple(
    (d, v, "Change")
    for d, v in zip(
        (5.0, 60.0, 300.0, 1200.0, 3600.0),
        (35.0, 12.5, -4.0, -18.0, -22.5),
        strict=True,
    )
)

PACE = column("pace_s_per_km", unit="s_per_km")
PACE_ROWS: tuple[tuple[Value, ...], ...] = (
    (300.0, 252.0),
    (5.0, 171.0),
    (60.0, 198.0),
    (20.0, 183.0),
    (600.0, 266.0),
    (1200.0, 271.0),
)

LONG_X = column(
    "elapsed_time",
    ValueKind.DURATION,
    label="Elapsed time since the start of the whole ride day",
)
LONG_Y = column(
    "power_w",
    unit="w",
    label="Average mechanical power sustained across the interval as measured"
    " at the crank spider by the strain gauges",
)
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    (
        timedelta(minutes=20),
        250.0,
        "A very long season name that cannot fit its legend",
    ),
    (timedelta(minutes=1), 480.0, "A very long season name that cannot fit its legend"),
    (timedelta(minutes=5), 310.0, "Another extraordinarily long season name indeed"),
    (timedelta(minutes=60), 205.0, "Another extraordinarily long season name indeed"),
)
LONG_TITLE = (
    "A deliberately long chart title that cannot possibly fit within the width of"
    " the chart however small its type"
)

LIMIT = 1000
AT_BOUND_PERIODS = 8


def _at_bound_rows(count: int) -> tuple[tuple[Value, ...], ...]:
    each = count // AT_BOUND_PERIODS
    return tuple(
        (float(d), float(900 - 5 * d + (p * 13) % 40), f"Season {p}")
        for d in range(1, each + 1)
        for p in range(AT_BOUND_PERIODS)
    )


CASES: tuple[Case, ...] = (
    Case(
        "typical",
        # 480 px: here numeric_scale's own ticks (1 s, 10 s, 1 min, 10 min, 1 h)
        # differ from the landmark ticks, so the golden pins the landmark choice.
        chart_request(
            "mean-max",
            ref="m1",
            title="Power curve",
            channels=CHANNELS,
            options={"width": 480},
        ),
        chart_data((DURATION, POWER, PERIOD), TYPICAL_ROWS),
    ),
    Case(
        "empty",
        chart_request("mean-max", ref="m1", title="Power curve", channels=CHANNELS),
        chart_data((DURATION, POWER, PERIOD), []),
    ),
    Case(
        "all_absent",
        chart_request("mean-max", ref="m1", title="Power curve", channels=CHANNELS),
        chart_data((DURATION, POWER, PERIOD), ABSENT_ROWS),
    ),
    Case(
        "single",
        chart_request("mean-max", ref="m1", title="Power curve", channels=CHANNELS_XY),
        chart_data((DURATION, POWER), [(300.0, 245.0)]),
    ),
    Case(
        "negative",
        chart_request(
            "mean-max",
            ref="m1",
            title="Change in power",
            channels={"x": "duration_s", "y": "delta_w", "color": "period"},
        ),
        chart_data((DURATION, NEGATIVE_Y, PERIOD), NEGATIVE_ROWS),
    ),
    Case(
        "pace",
        chart_request(
            "mean-max",
            ref="m1",
            title="Pace curve",
            channels={"x": "duration_s", "y": "pace_s_per_km"},
        ),
        chart_data((DURATION, PACE), PACE_ROWS),
    ),
    Case(
        "long_labels",
        chart_request(
            "mean-max",
            ref="m1",
            title=LONG_TITLE,
            channels={"x": "elapsed_time", "y": "power_w", "color": "period"},
        ),
        chart_data((LONG_X, LONG_Y, PERIOD), LONG_ROWS),
    ),
    Case(
        "at_bound",
        chart_request("mean-max", ref="m1", title="Every season", channels=CHANNELS),
        chart_data((DURATION, POWER, PERIOD), _at_bound_rows(LIMIT)),
    ),
)


def _case(name: str) -> Case:
    return next(case for case in CASES if case.name == name)


def _render_case(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


# --- parsing helpers -------------------------------------------------------------


def _root(text: str) -> ET.Element:
    return ET.fromstring(text)


def _group(text: str, css_class: str) -> list[ET.Element]:
    return [g for g in _root(text).iter(f"{SVG}g") if g.get("class") == css_class]


def _texts(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{SVG}text"))


def _marks(text: str) -> list[tuple[str, str, str, list[tuple[float, float]]]]:
    """``(kind, stroke, dasharray, points)`` per mark: a polyline or a dot."""
    (marks,) = _group(text, "ck-marks")
    out: list[tuple[str, str, str, list[tuple[float, float]]]] = []
    for child in marks:
        stroke = child.get("stroke") or ""
        dash = child.get("stroke-dasharray") or ""
        if child.tag == f"{SVG}polyline":
            points = [
                (float(a), float(b))
                for a, b in (p.split(",") for p in (child.get("points") or "").split())
            ]
            out.append(("line", stroke, dash, points))
        else:
            assert child.tag == f"{SVG}path" and child.get("stroke-width") == "5"
            match = re.fullmatch(r"M(\S+) (\S+)h0", child.get("d") or "")
            assert match is not None
            out.append(("dot", stroke, dash, [(float(match[1]), float(match[2]))]))
    return out


def _x_axis_texts(text: str) -> list[ET.Element]:
    """The bottom axis's texts: tick labels, then its title."""
    axes = _group(text, "ck-axis")
    return [t for g in axes for t in _texts(g) if t.get("text-anchor") == "middle"]


def _x_ticks(text: str) -> list[str]:
    return [t.text or "" for t in _x_axis_texts(text)][:-1]


def _x_title(text: str) -> str:
    return (_x_axis_texts(text)[-1].text) or ""


def _y_tick_labels(text: str) -> list[str]:
    return [
        t.text or ""
        for g in _group(text, "ck-axis")
        for t in _texts(g)
        if t.get("text-anchor") == "end"
    ]


def _legend_labels(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-legend") for t in _texts(g)]


def _note_lines(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-notes") for t in _texts(g)]


def _desc(text: str) -> str:
    element = _root(text).find(f"{SVG}desc")
    assert element is not None
    return element.text or ""


def _tick_extent(text: str) -> tuple[float, float]:
    """The x of the first and last x tick labels (the plot ends when both are
    the domain's ends)."""
    xs = [float(t.get("x") or "nan") for t in _x_axis_texts(text)[:-1]]
    return xs[0], xs[-1]


def _curve(durations: Sequence[float], width: int | None = None) -> str:
    """One un-coloured curve over ``durations`` (power falls as they grow)."""
    rows = [(d, 1000.0 - i * 10.0) for i, d in enumerate(durations)]
    options: dict[str, OptionValue] = {} if width is None else {"width": width}
    return _render((DURATION, POWER), rows, CHANNELS_XY, options)


# --- declaration -------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "mean-max"
    assert KIND.description == (
        "Best-effort curves over a log duration axis, one per period"
    )
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The duration of each best effort: a duration, or a number in seconds.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The best mean value over that duration: a number or duration.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One curve per value of this column, such as a season.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the y axis to include zero.",
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
        1000, "rows", OverBound.REFUSE, "At most 1000 rows; more are refused."
    )
    assert KIND.max_series == 8
    assert KIND.uses_all_columns is False


def test_the_landmark_priority_is_the_designed_tuple() -> None:
    assert mean_max.LANDMARK_PRIORITY == (
        60, 3600, 300, 1200, 5, 1, 15, 30, 120, 600,
        1800, 7200, 10800, 21600, 43200, 86400, 2, 10,
    )  # fmt: skip


# --- the channel unit ---------------------------------------------------------

DISTANCE = column("distance_m", unit="m")
MOVING = column("moving_time", ValueKind.DURATION)
UNITLESS = column("count")


def _channel_unit_problem(x: Column) -> ChartProblem:
    return ChartProblem(
        ref="m1",
        kind="mean-max",
        code=ProblemCode.CHANNEL_UNIT,
        message=(
            f"Channel x needs durations, but column '{x.name}' has "
            f"{'no unit' if x.unit is None else 'unit ' + x.unit}, not seconds."
        ),
        fix="Bind x to a duration column, or to seconds such as duration_s.",
        channel="x",
        column=x.name,
        accepted=("distance_s", "moving_time"),
    )


@pytest.mark.parametrize("x", [DISTANCE, UNITLESS], ids=["metres", "no-unit"])
def test_a_number_x_that_is_not_seconds_names_the_columns_that_fit(x: Column) -> None:
    columns = (
        x,
        column("distance_s", unit="s"),
        POWER,
        MOVING,
        column("moving_min", unit="m"),
    )
    request = chart_request(
        "mean-max", ref="m1", channels={"x": x.name, "y": "power_w"}
    )
    rows = [(1.0, 60.0, 250.0, timedelta(seconds=60), 1.0)]
    assert problems_of(KIND, request, chart_data(columns, rows)) == (
        _channel_unit_problem(x),
    )


def test_a_seconds_number_and_a_duration_x_have_no_problem() -> None:
    for x, value in ((DURATION, 60.0), (MOVING, timedelta(seconds=60))):
        request = chart_request(
            "mean-max", ref="m1", channels={"x": x.name, "y": "power_w"}
        )
        text = render_case(KIND, request, chart_data((x, POWER), [(value, 250.0)])).text
        assert text.startswith("<svg")


def test_validate_chart_reports_the_unit_without_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "KINDS", (*registry.KINDS, KIND))
    columns = (DISTANCE, POWER, MOVING, column("elapsed_s", unit="s"))
    request = chart_request(
        "mean-max", ref="m1", channels={"x": "distance_m", "y": "power_w"}
    )
    (problem,) = api.validate_chart(request, columns)
    assert problem.code is ProblemCode.CHANNEL_UNIT
    assert problem.channel == "x" and problem.column == "distance_m"
    assert problem.accepted == ("moving_time", "elapsed_s")
    good = chart_request(
        "mean-max", ref="m1", channels={"x": "elapsed_s", "y": "power_w"}
    )
    assert api.validate_chart(good, columns) == ()


# --- refusals, each alone ---------------------------------------------------------


def test_a_zero_duration_refuses_with_the_column_and_first_row() -> None:
    rows = [(60.0, 300.0, "A"), (0.0, 900.0, "A"), (-5.0, 800.0, "A")]
    (problem,) = _refusal((DURATION, POWER, PERIOD), rows)
    assert problem.code is ProblemCode.LOG_DOMAIN
    assert problem.row == 1
    assert problem.column == "duration_s" and problem.channel == "x"
    assert problem.message == (
        "Column duration_s holds 0:00 in row 1, which a logarithmic scale cannot draw."
    )
    # mean-max has no x_scale option, so neither the fix nor the problem names one.
    assert problem.fix == "Remove the rows with a duration at or below zero."
    assert problem.option is None


def test_a_negative_duration_refuses_with_its_row() -> None:
    rows = [(60.0, 300.0, "A"), (-5.0, 800.0, "A")]
    (problem,) = _refusal((DURATION, POWER, PERIOD), rows)
    assert (problem.code, problem.row) == (ProblemCode.LOG_DOMAIN, 1)


def test_an_absent_duration_is_not_a_log_domain_problem() -> None:
    text = _render((DURATION, POWER, PERIOD), [(None, 300.0, "A"), (60.0, 250.0, "A")])
    assert _note_lines(text) == ["Not drawn: 1 row without x."]


def test_a_duplicate_period_and_duration_refuses_alone() -> None:
    rows = [
        (60.0, 300.0, "This season"),
        (300.0, 280.0, "This season"),
        (60.0, 310.0, "Last season"),
        (300.0, 290.0, "This season"),
    ]
    assert _refusal((DURATION, POWER, PERIOD), rows) == (
        ChartProblem(
            ref="m1",
            kind="mean-max",
            code=ProblemCode.DUPLICATE_POSITION,
            message="Row 3 repeats row 1, which has the same period (This season) "
            "and duration (5:00).",
            fix="Aggregate the rows that share this position, or bind a column to "
            "color or x that separates them.",
            row=3,
        ),
    )


def test_one_duration_in_two_periods_is_not_a_duplicate() -> None:
    rows = [(60.0, 300.0, "A"), (60.0, 310.0, "B")]
    text = _render((DURATION, POWER, PERIOD), rows)
    assert [m[0] for m in _marks(text)] == ["dot", "dot"]


def test_1001_rows_refuse_alone_and_1000_render() -> None:
    columns = (DURATION, POWER, PERIOD)
    assert _refusal(
        columns, _at_bound_rows(1001 - 1) + ((9999.0, 1.0, "Season 0"),)
    ) == (
        ChartProblem(
            ref="m1",
            kind="mean-max",
            code=ProblemCode.OVER_BOUND,
            message="mean-max draws at most 1000 rows; this data has 1001.",
            fix="Aggregate the rows (for example by day or week) or limit them to "
            "at most 1000.",
            rows=1001,
        ),
    )
    text = _render(columns, _at_bound_rows(1000))
    assert sum(len(m[3]) for m in _marks(text)) == 1000


def test_nine_periods_refuse_alone_and_eight_render() -> None:
    columns = (DURATION, POWER, PERIOD)
    nine = [(60.0, 300.0 + i, f"p{9 - i}") for i in range(9)]
    assert _refusal(columns, nine) == (
        ChartProblem(
            ref="m1",
            kind="mean-max",
            code=ProblemCode.TOO_MANY_SERIES,
            message="mean-max draws at most 8 series; the colour channel yields 9.",
            fix="Filter the rows or bind a colour column with at most 8 distinct "
            "values.",
            channel="color",
            column="period",
        ),
    )
    text = _render(columns, nine[:8])
    assert _legend_labels(text) == [f"p{9 - i}" for i in range(8)]


# --- landmark ticks and their labels ---------------------------------------------

REQUIRED = ("0:00:05", "0:01:00", "0:05:00", "0:20:00", "1:00:00")


def test_numeric_scales_own_ticks_omit_a_landmark_the_kind_keeps() -> None:
    # Precondition for the 720 px test: the kit's own ladder thinning at this
    # width drops at least one of the five landmarks, so keeping them is the kind's.
    first, last = _tick_extent(_curve([2.0, 3600.0]))  # both are the domain's ends
    own = numeric_scale(
        [2.0, 3600.0],
        DURATION,
        first,
        last,
        scale=ScaleType.LOG,
        include_zero=False,
        nice=True,
        horizontal=True,
    )
    own_labels = {t.label for t in own.ticks}
    assert not set(REQUIRED) <= own_labels
    assert set(REQUIRED) <= set(
        _x_ticks(_curve([2.0, 5.0, 60.0, 300.0, 1200.0, 3600.0]))
    )


def test_the_typical_golden_width_separates_landmarks_from_the_scales_ticks() -> None:
    first, last = _tick_extent(_render_case(_case("typical")))
    own = numeric_scale(
        [1.0, 3600.0],
        DURATION,
        first,
        last,
        scale=ScaleType.LOG,
        include_zero=False,
        nice=True,
        horizontal=True,
    )
    assert [t.label for t in own.ticks] == [
        "0:00:01",
        "0:00:10",
        "0:01:00",
        "0:10:00",
        "1:00:00",
    ]
    assert _x_ticks(_render_case(_case("typical"))) == [
        "0:00:01",
        "0:00:05",
        "0:01:00",
        "0:05:00",
        "1:00:00",
    ]


def test_the_five_landmarks_lead_on_a_wide_axis() -> None:
    ticks = _x_ticks(_curve([2.0, 5.0, 60.0, 300.0, 1200.0, 3600.0], 720))
    assert set(REQUIRED) <= set(ticks)
    assert ticks == sorted(ticks)  # ascending durations, fixed-width labels


def test_a_narrow_axis_keeps_one_minute_and_one_hour() -> None:
    ticks = _x_ticks(_curve([2.0, 5.0, 60.0, 300.0, 1200.0, 3600.0], 320))
    assert ticks == ["0:00:05", "0:01:00", "1:00:00"]


def test_ticks_are_ladder_durations_only() -> None:
    root = _root(_curve([3.0, 7.0, 90.0, 400.0, 2500.0]))
    labels = _x_ticks(ET.tostring(root, encoding="unicode"))
    ladder = {"0:00:01", "0:00:02", "0:00:05", "0:00:10", "0:00:15", "0:00:30"}
    ladder |= {"0:01:00", "0:02:00", "0:05:00", "0:10:00", "0:20:00", "0:30:00"}
    ladder |= {"1:00:00", "2:00:00"}
    assert labels and set(labels) <= ladder


def test_every_landmark_label_clears_its_neighbours() -> None:
    for width in (320, 480, 720, 1600):
        text = _curve([1.0, 2.0, 5.0, 60.0, 300.0, 1200.0, 3600.0], width)
        placed = sorted(
            (
                float(t.get("x") or "nan"),
                text_width(t.text or "", float(t.get("font-size") or "nan")),
            )
            for t in _x_axis_texts(text)[:-1]
        )
        for (a, wa), (b, wb) in zip(placed, placed[1:], strict=False):
            assert b - a >= (wa + wb) / 2 + 10.0 - 1e-6


def test_the_hours_form_labels_and_titles_the_axis_alike() -> None:
    text = _curve([2.0, 60.0, 3600.0])
    assert all(t.count(":") == 2 for t in _x_ticks(text))
    assert _x_title(text) == "duration (h:mm:ss)"
    assert "duration (h:mm:ss) from 0:00:02 to 1:00:00" in _desc(text)


def test_the_minutes_form_labels_and_titles_the_axis_alike() -> None:
    text = _curve([2.0, 60.0, 1200.0])
    ticks = _x_ticks(text)
    assert ticks and all(t.count(":") == 1 for t in ticks)
    assert "0:05" in ticks and "1:00" in ticks and "20:00" in ticks
    assert _x_title(text) == "duration (m:ss)"
    assert "duration (m:ss) from 0:02 to 20:00" in _desc(text)


def test_a_domain_reaching_an_hour_labels_every_tick_in_hours() -> None:
    # The data ends at 3000 s, but the axis rounds out to 3600 s; that upper end
    # decides the form, not the largest data value.
    text = _curve([2.0, 5.0, 60.0, 3000.0], 320)
    ticks = _x_ticks(text)
    assert ticks and all(t.count(":") == 2 for t in ticks)
    assert _x_title(text) == "duration (h:mm:ss)"


def test_a_duration_column_x_is_titled_in_the_same_form_as_its_labels() -> None:
    moving = column("moving_time", ValueKind.DURATION)
    short = _render(
        (moving, POWER),
        [(timedelta(seconds=s), 300.0 - s / 100) for s in (5, 60, 900)],
        {"x": "moving_time", "y": "power_w"},
    )
    assert _x_title(short) == "moving time (m:ss)"
    assert all(t.count(":") == 1 for t in _x_ticks(short))
    long = _render(
        (moving, POWER),
        [(timedelta(seconds=s), 300.0 - s / 100) for s in (5, 60, 7200)],
        {"x": "moving_time", "y": "power_w"},
    )
    assert _x_title(long) == "moving time (h:mm:ss)"
    assert all(t.count(":") == 2 for t in _x_ticks(long))


def test_the_x_axis_is_logarithmic() -> None:
    text = _curve([1.0, 10.0, 100.0, 1000.0])
    ((_, _, _, points),) = _marks(text)
    steps = [b[0] - a[0] for a, b in zip(points, points[1:], strict=False)]
    assert max(steps) - min(steps) <= 0.02  # equal ratios, pixels rounded to 0.01
    assert steps[0] > 0


def test_a_sub_second_domain_renders_in_the_minutes_form() -> None:
    text = _render((DURATION, POWER), [(0.2, 900.0), (0.8, 700.0)], CHANNELS_XY)
    assert _x_ticks(text)
    assert _x_title(text) == "duration (m:ss)"


def test_a_multi_day_domain_holds_no_landmark_and_keeps_the_scales_ticks() -> None:
    text = _render(
        (DURATION, POWER), [(200000.0, 300.0), (400000.0, 250.0)], CHANNELS_XY
    )
    ticks = _x_ticks(text)
    assert len(ticks) >= 2
    seconds = [
        int(h) * 3600 + int(m) * 60 + int(s)
        for h, m, s in (t.split(":") for t in ticks)
    ]
    assert seconds == sorted(seconds)
    assert seconds[0] >= 172800 and seconds[-1] <= 432000  # the scale's own domain
    assert _x_title(text) == "duration (h:mm:ss)"


# --- pace ----------------------------------------------------------------------


def test_a_pace_y_is_labelled_as_pace() -> None:
    text = _render_case(_case("pace"))
    labels = _y_tick_labels(text)
    assert labels and all(re.fullmatch(r"\d+:\d\d", t) for t in labels)
    axis_titles = [
        t.text
        for g in _group(text, "ck-axis")
        for t in _texts(g)
        if t.get("transform") or t.get("text-anchor") == "start"
    ]
    assert "pace (min/km)" in axis_titles
    assert _desc(text).endswith(
        "duration (m:ss) from 0:05 to 20:00; pace (min/km) from 2:51 /km to 4:31 /km."
    )


def test_pace_is_drawn_linearly_and_not_inverted() -> None:
    ((_, _, _, points),) = _marks(_render_case(_case("pace")))
    # The slowest pace (largest seconds per km) is the longest duration and is
    # drawn highest (smallest pixel y); the fastest (5 s) lowest.
    assert points[0][1] > points[-1][1]
    ys = [y for _, y in points]
    assert ys == sorted(ys, reverse=True)
    labels = _y_tick_labels(_render_case(_case("pace")))
    seconds = [int(m) * 60 + int(s) for m, s in (t.split(":") for t in labels)]
    assert seconds == sorted(seconds)


def test_a_duration_y_is_titled_and_labelled_in_its_own_form() -> None:
    moving = column("moving_time", ValueKind.DURATION)
    rows = [
        (5.0, timedelta(seconds=300)),
        (60.0, timedelta(seconds=900)),
        (600.0, timedelta(seconds=1500)),
    ]
    text = _render((DURATION, moving), rows, {"x": "duration_s", "y": "moving_time"})
    assert "moving time (m:ss)" in {t.text for t in _texts(_root(text))}
    assert all(t.count(":") == 1 for t in _y_tick_labels(text))
    assert "moving time (m:ss) from 5:00 to 25:00." in _desc(text)


# --- curves ---------------------------------------------------------------------


def test_each_period_is_one_curve_joined_in_ascending_duration() -> None:
    marks = _marks(_render_case(_case("typical")))
    lines = [m for m in marks if m[0] == "line"]
    assert len(lines) == 3  # This season breaks at its absent value
    for _, _, _, points in lines:
        xs = [x for x, _ in points]
        assert xs == sorted(xs) and len(set(xs)) == len(xs)
    assert [len(p) for _, _, _, p in lines] == [13, 8, 22]


def test_an_absent_power_value_breaks_its_periods_curve() -> None:
    marks = _marks(_render_case(_case("typical")))
    this_season = [m for m in marks if m[1] == marks[0][1]]
    assert [len(m[3]) for m in this_season] == [13, 8]
    # The two parts are separated by the 480 s gap, not bridged.
    gap = this_season[1][3][0][0] - this_season[0][3][-1][0]
    assert gap > 0
    assert 480.0 in [
        r[0] for r in TYPICAL_ROWS if r[2] == "This season" and r[1] is None
    ]


def test_an_absent_power_is_not_drawn_as_zero() -> None:
    marks = _marks(_render_case(_case("typical")))
    bottom = max(y for _, _, _, points in marks for _, y in points)
    plot_bottom = float(
        next(
            line.get("y1")
            for g in _group(_render_case(_case("typical")), "ck-axis")
            for line in g.iter(f"{SVG}line")
            if line.get("y1") == line.get("y2")
        )
        or "nan"
    )
    assert bottom < plot_bottom - 1.0  # nothing sits on the zero-power baseline


def test_a_point_with_no_present_neighbour_is_a_dot() -> None:
    rows = [(5.0, 900.0), (60.0, None), (300.0, 500.0), (600.0, None)]
    text = _render((DURATION, POWER), rows, CHANNELS_XY)
    assert [m[0] for m in _marks(text)] == ["dot", "dot"]
    assert _note_lines(text) == ["Not drawn: 2 rows without y."]


def test_periods_in_first_appearance_with_the_absent_one_last() -> None:
    rows = [
        (60.0, 300.0, "Summer"),
        (60.0, 310.0, None),
        (60.0, 320.0, "Autumn"),
        (300.0, 290.0, "Summer"),
        (300.0, 295.0, None),
        (300.0, 305.0, "Autumn"),
    ]
    text = _render((DURATION, POWER, PERIOD), rows)
    assert _legend_labels(text) == ["Summer", "Autumn", "—"]
    marks = _marks(text)
    assert len(marks) == 3
    styles = [(stroke, dash) for _, stroke, dash, _ in marks]
    assert len(set(styles)) == 3  # colour and dash, each period its own
    assert len({dash for _, dash in styles}) == 3
    expected = [series_style(i) for i in range(3)]
    assert [dash for _, dash in styles] == [e.dash or "" for e in expected]
    assert [s for s, _ in styles] == [e.color for e in expected]


def test_y_zero_extends_the_y_axis_to_zero() -> None:
    rows = [(5.0, 900.0), (60.0, 500.0)]
    without = _render((DURATION, POWER), rows, CHANNELS_XY)
    with_zero = _render((DURATION, POWER), rows, CHANNELS_XY, {"y_zero": True})
    assert "0" not in _y_tick_labels(without)
    assert _y_tick_labels(with_zero)[0] == "0"


def test_a_longer_duration_with_a_higher_value_is_drawn_where_it_is() -> None:
    rows = [(60.0, 400.0), (300.0, 300.0), (600.0, 350.0), (3600.0, 250.0)]
    ((_, _, _, points),) = _marks(_render((DURATION, POWER), rows, CHANNELS_XY))
    ys = [y for _, y in points]
    assert ys[2] < ys[1]  # 600 s (350 W) sits above 300 s (300 W): no envelope
    assert ys[0] < ys[2] < ys[3]


def test_rows_are_drawn_as_given_with_no_aggregate() -> None:
    marks = _marks(_render_case(_case("typical")))
    assert sum(len(m[3]) for m in marks) == 43  # 44 rows, one without power


# --- accessibility ---------------------------------------------------------------


def test_undrawn_counts_are_x_first_then_y_on_the_chart_and_in_the_description() -> (
    None
):
    rows = [(None, 100.0), (60.0, None), (None, None), (300.0, 50.0), (600.0, 40.0)]
    text = _render((DURATION, POWER), rows, CHANNELS_XY)
    line = "Not drawn: 2 rows without x, 1 row without y."
    assert _note_lines(text) == [line]
    assert line in _desc(text)


def test_rows_without_a_duration_in_one_period_are_not_duplicates() -> None:
    rows = [(None, 300.0, "A"), (None, 310.0, "A"), (60.0, 250.0, "A")]
    text = _render((DURATION, POWER, PERIOD), rows)
    assert _note_lines(text) == ["Not drawn: 2 rows without x."]


def test_typical_description() -> None:
    assert _desc(_render_case(_case("typical"))) == TYPICAL_DESCRIPTION


def test_not_drawn_is_stated_on_the_chart_and_in_the_description() -> None:
    text = _render_case(_case("typical"))
    assert _note_lines(text) == ["Not drawn: 1 row without y."]
    assert "Not drawn: 1 row without y." in _desc(text)


def test_no_rows_is_the_no_data_state() -> None:
    text = _render_case(_case("empty"))
    assert _group(text, "ck-marks") == []
    assert _desc(text) == "Mean-max chart: Power curve. No data: no rows."
    assert ">No data<" in text
    assert 'height="320"' in text.split(">")[0]


def test_rows_without_a_drawable_value_are_the_no_data_state() -> None:
    text = _render_case(_case("all_absent"))
    assert _group(text, "ck-marks") == []
    assert _desc(text) == (
        "Mean-max chart: Power curve. No data: none of the 3 rows has a value to draw."
    )
    assert "None of the 3 rows has a value to draw." in text


def test_negative_values_are_drawn_below_the_zero_line() -> None:
    text = _render_case(_case("negative"))
    labels = _y_tick_labels(text)
    assert any(t.startswith("-") for t in labels) and "0" in labels
    ((_, _, _, points),) = _marks(text)
    assert points[-1][1] > points[0][1]


# --- goldens ---------------------------------------------------------------------


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "pace",
        "long_labels",
        "at_bound",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "mean-max"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("mean-max", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("mean-max", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    root = _root(_render_case(case))
    width = float(root.get("width") or "nan")
    texts = _texts(root)
    assert texts
    for element in texts:
        x = float(element.get("x") or "nan")
        reach = text_width(element.text or "", float(element.get("font-size") or "nan"))
        anchor = element.get("text-anchor")
        left = (
            x - reach / 2 if anchor == "middle" else x - reach if anchor == "end" else x
        )
        assert left >= 8.0 - 1e-6, element.text
        assert left + reach <= width - 4.0 + 1e-6, element.text


def test_every_text_stays_inside_a_narrow_chart() -> None:
    for width in (320, 400):
        text = _curve([1.0, 5.0, 60.0, 300.0, 1200.0, 3600.0], width)
        root = _root(text)
        texts = _texts(root)
        assert len(texts) >= 6
        for element in texts:
            x = float(element.get("x") or "nan")
            reach = text_width(
                element.text or "", float(element.get("font-size") or "nan")
            )
            anchor = element.get("text-anchor")
            left = (
                x - reach / 2
                if anchor == "middle"
                else x - reach
                if anchor == "end"
                else x
            )
            assert left >= 8.0 - 1e-6, element.text
            assert left + reach <= width - 4.0 + 1e-6, element.text


def test_the_first_tick_label_clears_the_left_edge() -> None:
    rows = [(1.0, 5.0), (60.0, 3.0), (3600.0, 1.0)]
    root = _root(_render((DURATION, POWER), rows, CHANNELS_XY))
    first = _x_axis_texts(ET.tostring(root, encoding="unicode"))[0]
    reach = text_width(first.text or "", float(first.get("font-size") or "nan"))
    assert first.text == "0:00:01"
    assert float(first.get("x") or "nan") - reach / 2 >= 8.0 - 1e-6


def test_typical_fixture_has_the_distinguishing_values() -> None:
    xs = [r[0] for r in TYPICAL_ROWS if r[2] == "This season"]
    assert xs != [d for d in DURATIONS]  # rows out of order
    assert list(dict.fromkeys(r[2] for r in TYPICAL_ROWS))[0] == "This season"
    assert {r[2] for r in TYPICAL_ROWS} == {"Last season", "This season"}
    assert sum(1 for r in TYPICAL_ROWS if r[1] is None) == 1
    assert math.gcd(SHUFFLE_STRIDE, len(TYPICAL_ROWS)) == 1
    assert len({r[:1] + r[2:] for r in TYPICAL_ROWS}) == len(TYPICAL_ROWS)
    assert (
        tuple(float(c.value) for c in MEAN_MAX_DURATIONS_S if c.value <= 3600)
        == DURATIONS
    )


def test_long_labels_golden_is_shortened() -> None:
    assert "…" in _render_case(_case("long_labels"))


def test_at_bound_golden_is_at_the_bound() -> None:
    case = _case("at_bound")
    assert len(case.data.rows) == LIMIT == KIND.bound.limit
    assert len({r[2] for r in case.data.rows}) == KIND.max_series == 8


def main() -> None:
    for case in CASES:
        write_golden(golden_path("mean-max", case.name, "svg"), _render_case(case))


if __name__ == "__main__":
    main()
