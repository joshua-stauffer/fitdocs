"""Band x axes: the first label is whole, and categories keep their identity.

Two defects the band kinds (bar, stacked-100, heatmap, box) shared. A band
axis reserved nothing for the first label's left half, so a weekly axis read
``2026-01-…`` at the canvas edge; and bar, stacked-100 and box keyed bands on
the formatted label, so two raw categories that format alike drew in one band.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.data import ChartData, Value, ValueKind
from fitdocs.render.charts.kit.kinds import bar, box, heatmap, stacked_100
from fitdocs.render.charts.kit.schema import ChartRequest, KindSpec, OptionValue
from tests.render.charts.kit._helpers import (
    chart_data,
    chart_request,
    column,
    render_case,
)

WEEK = column("week", ValueKind.DATE)
LABEL = column("label", ValueKind.CATEGORY)
ZONE = column("zone", ValueKind.CATEGORY)
Y = column("y")

Build = Callable[
    [Sequence[Value], dict[str, OptionValue]], tuple[ChartRequest, ChartData]
]


def _bar(
    xs: Sequence[Value], options: dict[str, OptionValue]
) -> tuple[ChartRequest, ChartData]:
    return (
        chart_request("bar", channels={"x": "x", "y": "y"}, options=options),
        chart_data(
            [column("x", _kind(xs)), Y], [(x, 1.0 + i) for i, x in enumerate(xs)]
        ),
    )


def _kind(xs: Sequence[Value]) -> ValueKind:
    return (
        ValueKind.DATE if any(isinstance(x, date) for x in xs) else ValueKind.CATEGORY
    )


def _stacked(
    xs: Sequence[Value], options: dict[str, OptionValue]
) -> tuple[ChartRequest, ChartData]:
    return (
        chart_request(
            "stacked-100",
            channels={"x": "x", "y": "y", "color": "zone"},
            options=options,
        ),
        chart_data(
            [column("x", _kind(xs)), Y, ZONE],
            [(x, 1.0 + i, "z1") for i, x in enumerate(xs)],
        ),
    )


def _heat(
    xs: Sequence[Value], options: dict[str, OptionValue]
) -> tuple[ChartRequest, ChartData]:
    return (
        chart_request(
            "heatmap",
            channels={"x": "x", "y": "zone", "value": "y"},
            options=options,
        ),
        chart_data(
            [column("x", _kind(xs)), Y, ZONE],
            [(x, 1.0 + i, "z1") for i, x in enumerate(xs)],
        ),
    )


def _box(
    xs: Sequence[Value], options: dict[str, OptionValue]
) -> tuple[ChartRequest, ChartData]:
    names = ("low", "q1", "median", "q3", "high")
    return (
        chart_request(
            "box", channels={"x": "x", **{n: n for n in names}}, options=options
        ),
        chart_data(
            [column("x", _kind(xs)), *[column(n) for n in names]],
            [(x, 1.0, 2.0, 3.0, 4.0, 5.0) for x in xs],
        ),
    )


KINDS: dict[str, tuple[KindSpec, Build]] = {
    "bar": (bar.KIND, _bar),
    "stacked-100": (stacked_100.KIND, _stacked),
    "heatmap": (heatmap.KIND, _heat),
    "box": (box.KIND, _box),
}
BAND_KINDS = pytest.mark.parametrize("name", sorted(KINDS))


def _svg(name: str, xs: Sequence[Value], **options: OptionValue) -> str:
    spec, build = KINDS[name]
    request, data = build(xs, dict(options))
    return render_case(spec, request, data).text


def _weeks(count: int) -> list[Value]:
    return [date(2026, 1, 5) + timedelta(days=7 * i) for i in range(count)]


def _x_axis_texts(svg: str) -> list[str]:
    axis = re.search(r'<g class="ck-axis">(.*?)</g>', svg, re.S)
    assert axis
    return re.findall(r"<text [^>]*>(.*?)</text>", axis.group(1))


@BAND_KINDS
@pytest.mark.parametrize(("weeks", "width"), [(26, 720), (52, 720), (8, 320)])
def test_the_first_band_label_is_never_cut_at_the_left_edge(
    name: str, weeks: int, width: int
) -> None:
    svg = _svg(name, _weeks(weeks), width=width)
    labels = _x_axis_texts(svg)[:-1]  # the last text is the axis title
    assert labels[0] == "2026-01-05"
    assert not any(label.endswith("…") for label in labels)


@pytest.mark.parametrize("name", ["bar", "stacked-100", "box"])
@pytest.mark.parametrize("pair", [("a\tb", "a b"), ("—", None)])
def test_categories_that_format_alike_keep_their_own_bands(
    name: str, pair: tuple[Value, Value]
) -> None:
    svg = _svg(name, list(pair))
    axis = re.search(r'<g class="ck-axis">(.*?)</g>', svg, re.S)
    assert axis
    ticks = re.findall(r'<text x="([^"]+)"', axis.group(1))[:-1]
    assert len(set(ticks)) == 2, "one band per raw category"
    # Marks are <rect>s; the only other rect is a legend swatch, 10 px wide.
    assert len(set(re.findall(r'<rect x="([^"]+)" y="[^"]+" width="(?!10")', svg))) == 2
