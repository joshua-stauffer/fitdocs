"""Represented-float linear tick and public-render regressions."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from datetime import date

import pytest

from fitdocs.render.charts.kit import (
    ChartData,
    ChartRequest,
    Column,
    ValueKind,
    render_chart,
)
from fitdocs.render.charts.kit.scales import ScaleType, numeric_scale
from fitdocs.render.charts.kit.ticks import linear_ticks


@pytest.mark.parametrize(
    "lo,hi,count",
    [
        (72.99999999999999, 73.0, 2),
        (math.nextafter(73.0, -math.inf), 73.0, 3),
        (73.0, math.nextafter(73.0, math.inf), 5),
        (-73.0, -72.99999999999999, 8),
        (73.0, 73.00000001, 5),
        (0.0, 0.1 + 0.2, 6),
        (1e10, 1e10 + 0.00001, 5),
        (-1e10 - 0.00001, -1e10, 3),
    ],
)
def test_linear_candidates_enclose_represented_data(
    lo: float, hi: float, count: int
) -> None:
    lower, upper, ticks = linear_ticks(lo, hi, count, duration=False)
    assert all(math.isfinite(v) for v in (lower, upper, *ticks))
    assert 2 <= len(ticks) <= count
    assert all(a < b for a, b in zip(ticks, ticks[1:], strict=False))
    assert lower <= lo < hi <= upper
    assert (lower, upper) == (ticks[0], ticks[-1])


@pytest.mark.parametrize(
    "lo,hi,horizontal",
    [
        (72.99999999999999, 73.0, False),
        (73.0, math.nextafter(73.0, math.inf), True),
        (-73.0, -72.99999999999999, False),
        (73.0, 73.00000001, True),
        (73.0000000013, 73.0000000087, False),
    ],
)
def test_unequal_number_extent_retains_distinct_inside_ticks(
    lo: float, hi: float, horizontal: bool
) -> None:
    start, end = (0.0, 640.0) if horizontal else (240.0, 0.0)
    scale = numeric_scale(
        (lo, hi),
        Column("value", ValueKind.NUMBER),
        start,
        end,
        scale=ScaleType.LINEAR,
        include_zero=False,
        nice=False,
        horizontal=horizontal,
    )
    assert (scale.lo, scale.hi) == (lo, hi)
    positions = tuple(scale.position(t.value) for t in scale.ticks)
    assert all(math.isfinite(p) for p in positions)
    assert len(set(positions)) == len(positions) >= 2
    assert all(lo <= t.value <= hi for t in scale.ticks)
    assert (scale.position(lo), scale.position(hi)) == (start, end)


@pytest.mark.parametrize(
    "kind,raw,other,numeric_x",
    [
        ("reference-band", 73.0, math.exp(sum([math.log(73.0)] * 3) / 3), False),
        ("line", 73.0, math.exp(sum([math.log(73.0)] * 3) / 3), False),
        ("small-multiples", 73.0, math.exp(sum([math.log(73.0)] * 3) / 3), False),
        ("reference-band", 73.0, math.nextafter(73.0, math.inf), False),
        ("line", 73.0, math.nextafter(73.0, math.inf), True),
        ("small-multiples", 73.0, math.nextafter(73.0, math.inf), False),
    ],
)
def test_public_charts_render_close_finite_values(
    kind: str, raw: float, other: float, numeric_x: bool
) -> None:
    columns = (
        Column("day", ValueKind.NUMBER if numeric_x else ValueKind.DATE),
        Column("value", ValueKind.NUMBER, "ms"),
        Column("mean", ValueKind.NUMBER, "ms"),
        Column("source", ValueKind.CATEGORY),
    )
    channels = {"x": "day", "y": "value"}
    if kind == "reference-band":
        channels.update(mid="mean", segment="source")
    if kind == "small-multiples":
        channels["facet"] = "source"
    rows = (
        (raw if numeric_x else date(2021, 9, 8), raw, None, "synthetic"),
        (other if numeric_x else date(2021, 9, 9), other, other, "synthetic"),
    )
    output = render_chart(
        ChartRequest("precision", kind, "Synthetic HRV", channels),
        ChartData(columns, rows),
    )
    svg = ET.fromstring(output.text)
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert len(list(svg.iter())) > 20
