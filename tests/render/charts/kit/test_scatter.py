"""The ``scatter`` kind: declaration, refusals, marks, trend lines and goldens.

Regenerate the goldens with
``uv run python -m tests.render.charts.kit.test_scatter``.

Pixel positions in a rendered chart are read back to data values through the
chart's own tick labels (two labelled ticks fix an axis), so the assertions
compare data-space numbers that were worked out by hand, not the kind's own
arithmetic.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import pytest

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.scatter import KIND
from fitdocs.render.charts.kit.layout import FONT_TEXT, PAD, text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    ChartRequest,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import Shape, series_style, shape_path
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import (
    GOLDEN_ROOT,
    assert_golden,
    golden_path,
    write_golden,
)

X = column("distance_km", unit="km")
Y = column("elevation_m", unit="m")
SPORT = column("sport", ValueKind.CATEGORY)
COLUMNS = (X, Y, SPORT)
CHANNELS = {"x": "distance_km", "y": "elevation_m", "color": "sport"}


def _request(
    *,
    channels: dict[str, str] | None = None,
    title: str = "Elevation by distance",
    **options: Any,
) -> ChartRequest:
    return chart_request(
        "scatter",
        title=title,
        channels=CHANNELS if channels is None else channels,
        options=options,
    )


def _svg(data: ChartData, **options: Any) -> str:
    return render_case(KIND, _request(**options), data).text


def _rows(*rows: tuple[Value, ...]) -> ChartData:
    return chart_data(COLUMNS, rows)


# --- reading a rendered chart back --------------------------------------------

_TEXT = re.compile(
    r'<text x="([^"]*)" y="([^"]*)"(?: text-anchor="([^"]*)")? '
    r'font-size="[^"]*" class="ck-t" fill="[^"]*">([^<]*)</text>'
)
_DASHED = re.compile(
    r'<line x1="([^"]*)" y1="([^"]*)" x2="([^"]*)" y2="([^"]*)" '
    r'stroke="([^"]*)" stroke-width="1.2" stroke-dasharray="5 3"/>'
)
_MARKS = re.compile(r'<g class="ck-marks">(.*?)</g>', re.DOTALL)
_PATH = re.compile(r'<path d="([^"]*)"[^>]*/>')
_ELEMENT = re.compile(r"<path [^>]*/>")
_DOT = re.compile(r"M(-?[\d.]+) (-?[\d.]+)h0")
_TRIANGLE = re.compile(r"M(-?[\d.]+) (-?[\d.]+)l3.5 7h-7z")


def _group(svg: str, name: str) -> str:
    found = re.search(rf'<g class="{name}">(.*?)</g>', svg, re.DOTALL)
    assert found is not None, f"no {name} group"
    return found.group(1)


def _ticks(
    svg: str, anchor: str, parse: Callable[[str], float]
) -> list[tuple[float, float]]:
    """``(pixel, value)`` for every parseable tick label of one axis."""
    found: list[tuple[float, float]] = []
    assert len(_TEXT.findall(svg)) == svg.count("<text ")
    for x, y, shown, label in _TEXT.findall(svg):
        if shown != anchor:
            continue
        try:
            value = parse(label)
        except ValueError:
            continue
        found.append((float(x) if anchor == "middle" else float(y) - 4.0, value))
    return found


def _number(label: str) -> float:
    return float(label.split(" ")[0].replace("\N{MINUS SIGN}", "-"))


def _ordinal(label: str) -> float:
    return float(date.fromisoformat(label).toordinal())


def _inverse(ticks: Sequence[tuple[float, float]]) -> Callable[[float], float]:
    assert len(ticks) >= 2, f"need two parseable ticks, got {ticks}"
    (p0, v0), (p1, v1) = ticks[0], ticks[-1]
    assert p0 != p1
    return lambda px: v0 + (px - p0) * (v1 - v0) / (p1 - p0)


def _axes(
    svg: str, x_parse: Callable[[str], float] = _number
) -> tuple[Callable[[float], float], Callable[[float], float]]:
    return (
        _inverse(_ticks(svg, "middle", x_parse)),
        _inverse(_ticks(svg, "end", _number)),
    )


def _trend_lines(
    svg: str, x_parse: Callable[[str], float] = _number
) -> list[tuple[tuple[float, float], tuple[float, float], str]]:
    to_x, to_y = _axes(svg, x_parse)
    return [
        (
            (to_x(float(x1)), to_y(float(y1))),
            (to_x(float(x2)), to_y(float(y2))),
            colour,
        )
        for x1, y1, x2, y2, colour in _DASHED.findall(_group(svg, "ck-marks"))
    ]


def _centres(element: str) -> list[tuple[float, float]]:
    """Marker centres of one points ``<path>`` (circle, square, triangle-up)."""
    d = re.search(r' d="([^"]*)"', element)
    assert d is not None
    dots = [(float(x), float(y)) for x, y in _DOT.findall(d.group(1))]
    triangles = [(float(x), float(y) + 3.5) for x, y in _TRIANGLE.findall(d.group(1))]
    assert bool(dots) != bool(triangles), d.group(1)
    return dots or triangles


def _point_paths(svg: str) -> list[str]:
    return _ELEMENT.findall(_group(svg, "ck-marks"))


def _data_points(svg: str, element: str) -> list[tuple[float, float]]:
    to_x, to_y = _axes(svg)
    return [(to_x(x), to_y(y)) for x, y in _centres(element)]


def _assert_close(
    got: Sequence[tuple[float, float]],
    want: Sequence[tuple[float, float]],
    tolerance: float = 0.02,
) -> None:
    assert len(got) == len(want), (got, want)
    for (gx, gy), (wx, wy) in zip(got, want, strict=True):
        assert gx == pytest.approx(wx, abs=tolerance), (got, want)
        assert gy == pytest.approx(wy, abs=tolerance), (got, want)


def _texts(svg: str) -> list[str]:
    return [label for *_, label in _TEXT.findall(svg)]


# --- data ---------------------------------------------------------------------

TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (12.4, 310.0, "run"),
    (1.5, 0.0, "swim"),
    (36.0, 540.0, "bike"),
    (5.2, 95.0, "run"),
    (0.0, 12.0, "swim"),
    (22.8, None, "bike"),
    (None, 40.0, "run"),
    (28.1, 410.0, "bike"),
    (9.7, 150.0, "run"),
    (None, None, "swim"),
)

# Four series; "run" and "bike" have a fit, "swim" has one distinct x on two rows,
# "walk" has two distinct x but only one drawn point.
TREND_ROWS: tuple[tuple[Value, ...], ...] = (
    (3.0, 5.0, "run"),
    (2.0, 3.0, "swim"),
    (5.0, 13.0, "bike"),
    (1.0, 4.0, "run"),
    (2.0, 9.0, "swim"),
    (2.0, 14.0, "bike"),
    (5.0, 12.0, "run"),
    (1.0, 7.0, "walk"),
    (6.0, 20.0, "bike"),
    (2.0, 7.0, "run"),
    (4.0, None, "walk"),
    (3.0, 17.0, "bike"),
)

NEGATIVE_ROWS: tuple[tuple[Value, ...], ...] = (
    (-12.5, -40.0, "run"),
    (-3.0, 15.0, "swim"),
    (7.5, -8.5, "run"),
    (0.0, 0.0, "bike"),
    (4.0, -22.0, "swim"),
    (-6.5, 31.0, "bike"),
)

LONG_X = column(
    "distance_km",
    unit="km",
    label="Total distance covered during the long weekend group ride",
)
LONG_Y = column(
    "elevation_m",
    unit="m",
    label="Cumulative elevation gained across every climb of the day",
)
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    (12.4, 310.0, "Saturday morning club ride with the hills group"),
    (5.2, 95.0, "Sunday recovery spin around the reservoir loop"),
    (36.0, 540.5, "Saturday morning club ride with the hills group"),
    (9.7, 150.0, "Wednesday evening intervals on the canal towpath"),
)
LONG_TITLE = (
    "How the total elevation gained over a ride varies with the distance of "
    "that ride across the whole season so far"
)


def _at_bound_data() -> ChartData:
    names = ("run", "swim", "bike")
    rows: list[tuple[Value, ...]] = []
    for i in range(2000):
        rows.append(
            (
                ((i * 7919) % 2003) / 20,
                float((i * 104729) % 1009),
                names[i % 3],
            )
        )
    return chart_data(COLUMNS, rows)


def _case(
    name: str,
    data: ChartData,
    *,
    title: str = "Elevation by distance",
    **options: Any,
) -> Case:
    return Case(name, _request(title=title, **options), data)


CASES: tuple[Case, ...] = (
    _case("typical", _rows(*TYPICAL_ROWS)),
    _case("empty", _rows()),
    _case(
        "all_absent",
        _rows((None, None, "run"), (4.0, None, "swim"), (None, 7.0, "bike")),
    ),
    _case("single", _rows((5.0, 120.0, "run"))),
    _case("negative", _rows(*NEGATIVE_ROWS)),
    _case(
        "long_labels",
        chart_data((LONG_X, LONG_Y, SPORT), LONG_ROWS),
        title=LONG_TITLE,
    ),
    _case("at_bound", _at_bound_data()),
    _case("trend", _rows(*TREND_ROWS), trend=True),
)


# --- the declaration ----------------------------------------------------------


def test_the_kind_declaration() -> None:
    assert KIND.name == "scatter"
    assert KIND.description == (
        "One point per row, with optional colour and least-squares trend"
    )
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (
                ValueKind.NUMBER,
                ValueKind.DURATION,
                ValueKind.DATE,
                ValueKind.DATETIME,
            ),
            True,
            "The horizontal position of each point.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The vertical position of each point.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One series, with its own marker shape, per distinct value.",
        ),
    )
    assert KIND.options[:3] == (
        OptionSpec(
            "x_scale",
            OptionType.CHOICE,
            "The scale of the x axis.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "y_scale",
            OptionType.CHOICE,
            "The scale of the y axis.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "trend",
            OptionType.BOOLEAN,
            "Draw a least-squares trend line for each series.",
            False,
        ),
    )
    assert [o.name for o in KIND.options] == [
        "x_scale",
        "y_scale",
        "trend",
        "width",
        "height",
    ]
    assert KIND.options[3].default == 720
    assert KIND.options[4].default == 360
    assert KIND.bound == MarkBound(
        2000, "rows", OverBound.REFUSE, "At most 2000 rows; more are refused."
    )
    assert KIND.max_series == 8
    assert KIND.uses_all_columns is False


# --- refusals, each alone -----------------------------------------------------

DAY = column("day", ValueKind.DATE)
STAMP = column("started", ValueKind.DATETIME)


def test_trend_with_a_log_x_scale_is_refused_alone() -> None:
    data = _rows((1.0, 2.0, "run"), (10.0, 5.0, "run"))
    assert problems_of(KIND, _request(trend=True, x_scale="log"), data) == (
        ChartProblem(
            ref="c1",
            kind="scatter",
            code=ProblemCode.OPTION_CONFLICT,
            message=(
                "Option 'trend' cannot be combined with a logarithmic scale, "
                "but 'x_scale' is log."
            ),
            fix="Set 'trend' to false or set 'x_scale' to linear.",
            channel="x",
            column="distance_km",
            option="x_scale",
        ),
    )


def test_trend_with_a_log_y_scale_is_refused_alone() -> None:
    data = _rows((1.0, 2.0, "run"), (10.0, 5.0, "run"))
    assert problems_of(KIND, _request(trend=True, y_scale="log"), data) == (
        ChartProblem(
            ref="c1",
            kind="scatter",
            code=ProblemCode.OPTION_CONFLICT,
            message=(
                "Option 'trend' cannot be combined with a logarithmic scale, "
                "but 'y_scale' is log."
            ),
            fix="Set 'trend' to false or set 'y_scale' to linear.",
            channel="y",
            column="elevation_m",
            option="y_scale",
        ),
    )


def test_trend_with_both_scales_log_names_each() -> None:
    data = _rows((1.0, 2.0, "run"), (10.0, 5.0, "run"))
    problems = problems_of(
        KIND, _request(trend=True, x_scale="log", y_scale="log"), data
    )
    assert [(p.code, p.option) for p in problems] == [
        (ProblemCode.OPTION_CONFLICT, "x_scale"),
        (ProblemCode.OPTION_CONFLICT, "y_scale"),
    ]


@pytest.mark.parametrize("kind_column", [DAY, STAMP], ids=["date", "datetime"])
def test_a_log_scale_on_a_time_column_is_refused_alone(kind_column: Column) -> None:
    value: Value = (
        date(2026, 3, 1) if kind_column.kind is ValueKind.DATE else datetime(2026, 3, 1)
    )
    data = chart_data([kind_column, Y], [(value, 5.0)])
    request = _request(
        channels={"x": kind_column.name, "y": "elevation_m"}, x_scale="log"
    )
    assert problems_of(KIND, request, data) == (
        ChartProblem(
            ref="c1",
            kind="scatter",
            code=ProblemCode.OPTION_CONFLICT,
            message=(
                f"Option 'x_scale' cannot be log for column '{kind_column.name}', "
                f"which is a {kind_column.kind.value}."
            ),
            fix="Set 'x_scale' to linear.",
            channel="x",
            column=kind_column.name,
            option="x_scale",
        ),
    )


def test_a_trend_on_a_time_axis_and_linear_scales_renders() -> None:
    data = chart_data(
        [DAY, Y],
        [(date(2026, 3, 1), 5.0), (date(2026, 3, 4), 8.0)],
    )
    request = _request(channels={"x": "day", "y": "elevation_m"}, trend=True)
    assert len(_DASHED.findall(render_case(KIND, request, data).text)) == 1


def test_a_zero_in_a_log_column_is_refused_at_its_row() -> None:
    data = _rows((1.0, 2.0, "run"), (None, 9.0, "run"), (0.0, 4.0, "swim"))
    problems = problems_of(KIND, _request(x_scale="log"), data)
    assert [(p.code, p.channel, p.column, p.option, p.row) for p in problems] == [
        (ProblemCode.LOG_DOMAIN, "x", "distance_km", "x_scale", 2)
    ]


def test_a_negative_in_a_log_y_is_refused_and_absent_is_not_an_offender() -> None:
    data = _rows((1.0, 2.0, "run"), (3.0, None, "run"), (4.0, -5.0, "swim"))
    problems = problems_of(KIND, _request(y_scale="log"), data)
    assert [(p.code, p.channel, p.column, p.option, p.row) for p in problems] == [
        (ProblemCode.LOG_DOMAIN, "y", "elevation_m", "y_scale", 2)
    ]


def test_log_scales_over_positive_data_draw_decade_ticks() -> None:
    data = _rows(
        (1.0, 5.0, "run"),
        (None, 7.0, "run"),
        (100.0, 50.0, "swim"),
        (1000.0, 5000.0, "bike"),
    )
    svg = _svg(data, x_scale="log", y_scale="log")
    x_ticks = [v for _, v in _ticks(svg, "middle", _number)]
    y_ticks = [v for _, v in _ticks(svg, "end", _number)]
    assert 1.0 in x_ticks and 1000.0 in x_ticks and 10.0 in x_ticks
    assert 10.0 in y_ticks and 1000.0 in y_ticks


def test_the_bound_is_2000_rows() -> None:
    names = ("run", "swim")

    def rows(n: int) -> list[tuple[Value, ...]]:
        return [(float(i), float(i % 7), names[i % 2]) for i in range(n)]

    at_bound = _svg(chart_data(COLUMNS, rows(2000)))
    assert len(_point_paths(at_bound)) == 2
    problems = problems_of(KIND, _request(), chart_data(COLUMNS, rows(2001)))
    assert problems == (
        ChartProblem(
            ref="c1",
            kind="scatter",
            code=ProblemCode.OVER_BOUND,
            message="scatter draws at most 2000 rows; this data has 2001.",
            fix=(
                "Aggregate the rows (for example by day or week) or limit them "
                "to at most 2000."
            ),
            rows=2001,
        ),
    )


def test_nine_series_are_refused_and_eight_draw() -> None:
    def build(count: int) -> ChartData:
        return _rows(*[(float(i), float(i * 3), f"s{i}") for i in range(count)])

    assert len(_point_paths(_svg(build(8)))) == 8
    problems = problems_of(KIND, _request(), build(9))
    assert [(p.code, p.channel, p.column) for p in problems] == [
        (ProblemCode.TOO_MANY_SERIES, "color", "sport")
    ]


# --- marks --------------------------------------------------------------------


def test_one_points_path_per_series_with_its_shape_and_colour() -> None:
    svg = _svg(_rows(*TYPICAL_ROWS))
    paths = _point_paths(svg)
    assert len(paths) == 3
    shapes = (Shape.CIRCLE, Shape.SQUARE, Shape.TRIANGLE_UP)
    for index, (path, shape) in enumerate(zip(paths, shapes, strict=True)):
        style = series_style(index)
        assert style.shape is shape
        assert path == shape_path(shape, _centres(path), style.color)
    assert len({series_style(i).color for i in range(3)}) == 3


def test_points_sit_at_their_row_values_in_series_order() -> None:
    svg = _svg(_rows(*TYPICAL_ROWS))
    run, swim, bike = (_data_points(svg, p) for p in _point_paths(svg))
    _assert_close(run, [(12.4, 310.0), (5.2, 95.0), (9.7, 150.0)])
    _assert_close(swim, [(1.5, 0.0), (0.0, 12.0)])
    _assert_close(bike, [(36.0, 540.0), (28.1, 410.0)])


def test_the_legend_names_series_in_first_appearance_order() -> None:
    svg = _svg(_rows(*TYPICAL_ROWS))
    legend = re.findall(r"<text[^>]*>([^<]*)</text>", _group(svg, "ck-legend"))
    assert legend == ["run", "swim", "bike"]
    assert sorted(legend) != legend


def test_rows_without_a_colour_form_their_own_last_series() -> None:
    svg = _svg(
        _rows((1.0, 2.0, None), (3.0, 4.0, "swim"), (5.0, 6.0, None), (7.0, 8.0, "run"))
    )
    legend = re.findall(r"<text[^>]*>([^<]*)</text>", _group(svg, "ck-legend"))
    assert legend == ["swim", "run", "\N{EM DASH}"]
    paths = _point_paths(svg)
    assert len(paths) == 3
    _assert_close(_data_points(svg, paths[2]), [(1.0, 2.0), (5.0, 6.0)])


def test_without_a_colour_channel_there_is_one_series_and_no_legend() -> None:
    request = _request(channels={"x": "distance_km", "y": "elevation_m"})
    svg = render_case(KIND, request, _rows((3.0, 4.0, "a"), (1.0, 9.0, "b"))).text
    assert len(_point_paths(svg)) == 1
    assert 'class="ck-legend"' not in svg
    assert "1 series" not in svg


def test_a_series_with_no_drawn_row_keeps_its_legend_entry_and_has_no_marks() -> None:
    data = _rows(
        (1.0, 2.0, "run"),
        (3.0, None, "ghost"),
        (4.0, 8.0, "swim"),
        (None, 5.0, "ghost"),
    )
    svg = _svg(data, trend=True)
    legend = re.findall(r"<text[^>]*>([^<]*)</text>", _group(svg, "ck-legend"))
    assert legend == ["run", "ghost", "swim"]
    paths = _point_paths(svg)
    assert len(paths) == 2
    assert paths[0] == shape_path(
        Shape.CIRCLE, _centres(paths[0]), series_style(0).color
    )
    assert paths[1] == shape_path(
        Shape.TRIANGLE_UP, _centres(paths[1]), series_style(2).color
    )
    notes = re.findall(r"<text[^>]*>([^<]*)</text>", _group(svg, "ck-notes"))
    assert notes == [
        "Not drawn: 1 row without x, 1 row without y.",
        "No trend line for run, ghost, swim: fewer than 2 distinct x values.",
    ]


def test_the_axes_are_titled_with_label_and_unit() -> None:
    texts = _texts(_svg(_rows(*TYPICAL_ROWS)))
    assert "distance (km)" in texts
    assert "elevation (m)" in texts
    assert "Elevation by distance" in texts


def test_width_and_height_options_set_the_canvas() -> None:
    svg = _svg(_rows(*TYPICAL_ROWS), width=480, height=500)
    assert svg.startswith(
        '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="500" '
        'viewBox="0 0 480 500"'
    )
    assert 'height="360"' in _svg(_rows(*TYPICAL_ROWS))


def test_wide_end_tick_labels_stay_inside_the_canvas() -> None:
    # One-digit y labels leave far less margin than a ten-character date label
    # needs on either side of its tick.
    data = chart_data(
        [DAY, Y],
        [(date(2026, 3, 1), 1.0), (date(2026, 3, 6), 9.0), (date(2026, 3, 4), 4.0)],
    )
    request = _request(channels={"x": "day", "y": "elevation_m"})
    svg = render_case(KIND, request, data).text
    every_text = _TEXT.findall(svg)
    assert len(every_text) == svg.count("<text ")
    labels = [
        (float(x), label)
        for x, _, shown, label in every_text
        if shown == "middle" and label.startswith("2026-")
    ]
    assert len(labels) >= 2
    assert all(len(label) == 10 for _, label in labels)
    for x, label in labels:
        half = text_width(label, FONT_TEXT) / 2
        assert x - half >= PAD
        assert x + half <= 720
    assert labels[0][0] - text_width(labels[0][1], FONT_TEXT) / 2 < PAD + 1
    assert labels[-1][0] + text_width(labels[-1][1], FONT_TEXT) / 2 > 720 - PAD - 8


# --- undrawn rows -------------------------------------------------------------


def test_rows_without_x_or_y_are_counted_in_the_note_and_the_description() -> None:
    svg = _svg(_rows(*TYPICAL_ROWS))
    note = "Not drawn: 2 rows without x, 1 row without y."
    assert re.findall(r"<text[^>]*>([^<]*)</text>", _group(svg, "ck-notes")) == [note]
    assert f" {note} " in svg


def test_a_chart_with_every_row_drawn_has_no_notes() -> None:
    svg = _svg(_rows((1.0, 2.0, "run"), (3.0, 4.0, "swim")))
    assert "ck-notes" not in svg
    assert "Not drawn" not in svg


def test_the_description_summarises_the_chart() -> None:
    svg = _svg(_rows(*TYPICAL_ROWS))
    assert (
        "<desc>Scatter chart: Elevation by distance. x: distance (km); "
        "y: elevation (m); color: sport. 10 rows, 3 series. "
        "Not drawn: 2 rows without x, 1 row without y. "
        "distance (km) from 0.0 km to 36.0 km; "
        "elevation (m) from 0 m to 540 m.</desc>"
    ) in svg


def _duration_desc(
    seconds: tuple[float | None, ...], moving: Column | None = None
) -> str:
    if moving is None:
        moving = column("moving_time", ValueKind.DURATION)
    data = chart_data(
        [X, moving],
        [
            (
                float(i),
                v
                if v is None or moving.kind is ValueKind.NUMBER
                else timedelta(seconds=v),
            )
            for i, v in enumerate(seconds)
        ],
    )
    request = _request(channels={"x": "distance_km", "y": moving.name})
    svg = render_case(KIND, request, data).text
    found = re.search(r"<desc>(.*?)</desc>", svg)
    assert found is not None
    return found.group(1)


def test_a_sub_hour_duration_axis_reads_minutes_and_seconds_in_the_description() -> (
    None
):
    desc = _duration_desc((2700.0, 1500.0, None, 2100.0))
    assert desc.endswith("moving time (m:ss) from 25:00 to 45:00.")


def test_an_hours_duration_axis_reads_hours_in_the_description() -> None:
    desc = _duration_desc((3600.0, 1.0, 1800.0))
    assert desc.endswith("moving time (h:mm:ss) from 0:00:01 to 1:00:00.")


def test_a_number_column_with_a_duration_unit_reads_hours_too() -> None:
    desc = _duration_desc((3600.0, 1.0, 1800.0), column("moving_s", unit="s"))
    assert desc.endswith("from 0:00:01 to 1:00:00.")


def test_both_bounds_use_the_axis_form_when_the_domain_reaches_an_hour() -> None:
    desc = _duration_desc((3300.0, 1200.0))
    assert desc.endswith("moving time (h:mm:ss) from 0:20:00 to 0:55:00.")


def test_a_same_day_datetime_range_names_the_date_in_its_header() -> None:
    stamp = column("t", ValueKind.DATETIME)
    data = chart_data(
        [stamp, Y],
        [
            (datetime(2026, 3, 1, 9, 30), 5.0),
            (datetime(2026, 3, 1, 8, 0), 3.0),
            (datetime(2026, 3, 1, 11, 15), 8.0),
        ],
    )
    request = _request(channels={"x": "t", "y": "elevation_m"})
    svg = render_case(KIND, request, data).text
    found = re.search(r"<desc>(.*?)</desc>", svg)
    assert found is not None
    assert found.group(1).endswith(
        "t (2026-03-01) from 2026-03-01 08:00 to 2026-03-01 11:15; "
        "elevation (m) from 3 m to 8 m."
    )


def test_no_rows_and_no_drawable_rows_are_the_no_data_states() -> None:
    empty = _svg(_rows())
    assert (
        "<desc>Scatter chart: Elevation by distance. No data: no rows.</desc>" in empty
    )
    assert 'height="360"' in empty
    absent = _svg(CASES[2].data)
    assert (
        "<desc>Scatter chart: Elevation by distance. No data: none of the 3 rows "
        "has a value to draw.</desc>"
    ) in absent
    assert "None of the 3 rows has a value to draw." in _texts(absent)


# --- trend lines --------------------------------------------------------------


def test_trend_endpoints_equal_the_hand_computed_least_squares_fit() -> None:
    svg = _svg(_rows(*TREND_ROWS), trend=True)
    lines = _trend_lines(svg)
    assert [c for *_, c in lines] == [series_style(0).color, series_style(2).color]
    # run: x 1,2,3,5 / y 4,7,5,12 -> y = 69/35 + 64/35 x
    # bike: x 2,3,5,6 / y 14,17,13,20 -> y = 12.8 + 0.8 x
    _assert_close(
        [lines[0][0], lines[0][1]],
        [(1.0, 3.8), (5.0, 11.114286)],
    )
    _assert_close(
        [lines[1][0], lines[1][1]],
        [(2.0, 14.4), (6.0, 17.6)],
    )


def test_no_trend_unless_requested() -> None:
    svg = _svg(_rows(*TREND_ROWS))
    assert _DASHED.findall(svg) == []
    assert "No trend line" not in svg


def test_series_with_too_few_distinct_x_are_named_and_get_no_line() -> None:
    svg = _svg(_rows(*TREND_ROWS), trend=True)
    notes = re.findall(r"<text[^>]*>([^<]*)</text>", _group(svg, "ck-notes"))
    assert notes == [
        "Not drawn: 1 row without y.",
        "No trend line for swim, walk: fewer than 2 distinct x values.",
    ]
    assert len(_DASHED.findall(svg)) == 2


def test_a_series_with_two_distinct_x_draws_one_line_and_no_note() -> None:
    svg = _svg(_rows((1.0, 2.0, "run"), (4.0, 9.0, "run")), trend=True)
    assert "No trend line" not in svg
    assert len(_DASHED.findall(svg)) == 1


def test_date_x_regresses_on_days() -> None:
    # In days from 2026-03-02: x 0,1,4,9 / y 3,8,2,12 -> y = 3.642857 + 0.744898 x.
    data = chart_data(
        [DAY, Y, SPORT],
        [
            (date(2026, 3, 11), 12.0, "run"),
            (date(2026, 3, 2), 3.0, "run"),
            (date(2026, 3, 6), 2.0, "run"),
            (date(2026, 3, 3), 8.0, "run"),
        ],
    )
    request = _request(
        channels={"x": "day", "y": "elevation_m", "color": "sport"}, trend=True
    )
    svg = render_case(KIND, request, data).text
    ((start, end, _),) = _trend_lines(svg, _ordinal)
    first = date(2026, 3, 2).toordinal()
    _assert_close(
        [start, end],
        [(first, 3.642857), (first + 9, 10.346939)],
    )


def test_datetime_x_regresses_on_seconds() -> None:
    stamps = (
        (datetime(2026, 3, 1, 6, 0), 5.0),
        (datetime(2026, 3, 3, 18, 0), 3.0),
        (datetime(2026, 3, 5, 0, 0), 8.0),
        (datetime(2026, 3, 9, 12, 0), 12.0),
    )
    data = chart_data([STAMP, Y], [(s, y) for s, y in reversed(stamps)])
    request = _request(channels={"x": "started", "y": "elevation_m"}, trend=True)
    svg = render_case(KIND, request, data).text
    ((start, end, _),) = _trend_lines(svg, _ordinal)
    # In days from 2026-03-01 06:00: x 0, 2.5, 3.75, 8.25 / y 5, 3, 8, 12
    # -> mean x 3.625, mean y 7, slope 0.977312, so y(0) = 3.457243 and
    # y(8.25) = 11.52007.
    origin = datetime(2026, 3, 1, 6, 0).toordinal() + 0.25
    _assert_close(
        [start, end],
        [(origin, 3.457243), (origin + 8.25, 11.52007)],
        tolerance=0.03,
    )


def test_a_trend_line_is_clipped_to_the_plot() -> None:
    # x 0,1,2,20 / y 100,100,100,0: the fit is y = 105.041247 - 5.224565 x, so
    # 105.041247 at x = 0, above the axis top (the data maximum is 100); it
    # crosses 100 at x = 0.964912 and ends at 0.549954 at x = 20.
    data = _rows(
        (0.0, 100.0, "run"),
        (1.0, 100.0, "run"),
        (2.0, 100.0, "run"),
        (20.0, 0.0, "run"),
    )
    svg = _svg(data, trend=True)
    ((start, end, _),) = _trend_lines(svg)
    _assert_close([start, end], [(0.964912, 100.0), (20.0, 0.549954)])
    assert max(v for _, v in _ticks(svg, "end", _number)) == 100.0


def test_a_trend_line_is_clipped_at_its_high_x_end_too() -> None:
    # The mirror image: x 0,18,19,20 / y 0,100,100,100 gives y = 0.549954 at
    # x = 0 and 105.041247 at x = 20; it crosses 100 at x = 19.035088.
    data = _rows(
        (19.0, 100.0, "run"),
        (0.0, 0.0, "run"),
        (20.0, 100.0, "run"),
        (18.0, 100.0, "run"),
    )
    svg = _svg(data, trend=True)
    ((start, end, _),) = _trend_lines(svg)
    _assert_close([start, end], [(0.0, 0.549954), (19.035088, 100.0)])
    assert max(v for _, v in _ticks(svg, "end", _number)) == 100.0


# --- goldens ------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    assert_golden(
        golden_path("scatter", case.name, "svg"),
        render_case(KIND, case.request, case.data).text,
    )


def test_cases_are_the_designed_eight() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "long_labels",
        "at_bound",
        "trend",
    ]


def test_no_stale_goldens() -> None:
    directory = GOLDEN_ROOT / "scatter"
    assert directory.is_dir()
    assert sorted(p.name for p in directory.iterdir()) == sorted(
        f"{case.name}.svg" for case in CASES
    )


def test_golden_fixtures_hold_what_they_claim() -> None:
    by_name = {case.name: case for case in CASES}
    typical = by_name["typical"].data
    assert any(row[0] is None for row in typical.rows)
    assert any(row[1] is None for row in typical.rows)
    assert len({row[2] for row in typical.rows}) == 3
    assert any(row[0] == 0.0 for row in typical.rows)
    assert any(row[1] == 0.0 for row in typical.rows)
    assert by_name["empty"].data.rows == ()
    assert len(by_name["single"].data.rows) == 1
    assert any(
        isinstance(row[0], float) and row[0] < 0
        for row in by_name["negative"].data.rows
    )
    assert any(
        isinstance(row[1], float) and row[1] < 0
        for row in by_name["negative"].data.rows
    )
    long_svg = render_case(
        KIND, by_name["long_labels"].request, by_name["long_labels"].data
    ).text
    assert "\N{HORIZONTAL ELLIPSIS}" in long_svg
    assert len(by_name["at_bound"].data.rows) == 2000
    assert by_name["trend"].request.options == {"trend": True}


def main() -> None:
    for case in CASES:
        write_golden(
            golden_path("scatter", case.name, "svg"),
            render_case(KIND, case.request, case.data).text,
        )


if __name__ == "__main__":
    main()
