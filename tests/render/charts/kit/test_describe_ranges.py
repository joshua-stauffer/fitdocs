"""Every SVG kind's description names and formats its ranges by the drawn axis.

A numeric value axis is crossed with each unit family: a duration reads as a
clock, a pace, a percent, a quantity and a clock-basis date-time do not. The
channel sentence carries the same title as the axis, so a sub-hour duration
reads ``(m:ss)`` in both the sentence and the range.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds import area, bar, hbar, histogram, line, scatter
from fitdocs.render.charts.kit.schema import KindSpec
from tests.render.charts.kit._helpers import chart_data, chart_request, render_case

SVG = "{http://www.w3.org/2000/svg}"
SPECS: dict[str, KindSpec] = {
    "line": line.KIND,
    "area": area.KIND,
    "bar": bar.KIND,
    "hbar": hbar.KIND,
    "scatter": scatter.KIND,
    "histogram": histogram.KIND,
}


@dataclass(frozen=True)
class Family:
    """One value-column shape: its column and three pairwise-distinct values."""

    name: str
    column: Column
    values: tuple[Value, Value, Value]


FAMILIES = {
    f.name: f
    for f in (
        Family(
            "duration-kind",
            Column("moving", ValueKind.DURATION),
            (timedelta(seconds=95), timedelta(seconds=600), timedelta(seconds=1234)),
        ),
        Family(
            "duration-kind-hours",
            Column("moving", ValueKind.DURATION),
            (timedelta(seconds=95), timedelta(seconds=7300), timedelta(seconds=4000)),
        ),
        Family(
            "number-s",
            Column("moving_s", ValueKind.NUMBER, unit="s"),
            (95, 600, 1234),
        ),
        Family(
            "pace",
            Column("pace_s_per_km", ValueKind.NUMBER, unit="s_per_km"),
            (270, 345, 300),
        ),
        Family(
            "percent",
            Column("grade_pct", ValueKind.NUMBER, unit="pct"),
            (0.0, 87.5, 40.0),
        ),
        Family(
            "quantity",
            Column("distance_km", ValueKind.NUMBER, unit="km"),
            (3.5, 42.2, 10.0),
        ),
        Family(
            "clock",
            Column("start_utc", ValueKind.DATETIME, unit="utc"),
            (
                datetime(2026, 3, 2, 6, 15),
                datetime(2026, 3, 2, 18, 40),
                datetime(2026, 3, 2, 12, 5),
            ),
        ),
    )
}
VALUE_FAMILIES = [n for n in FAMILIES if n != "clock"]
ORDINAL = Column("n", ValueKind.NUMBER)
LABEL = Column("label", ValueKind.CATEGORY)


def _render(
    kind: str, channels: dict[str, Column], rows: Sequence[Sequence[Value]]
) -> tuple[str, list[str]]:
    """The ``<desc>`` text and every ``<text>`` of ``kind`` over ``rows``."""
    request = chart_request(
        kind, channels={ch: c.name for ch, c in channels.items()}, title="T"
    )
    data = chart_data(list(channels.values()), rows)
    root = ET.fromstring(render_case(SPECS[kind], request, data).text)
    desc = root.find(f"{SVG}desc")
    assert desc is not None and desc.text is not None
    return desc.text, ["".join(t.itertext()) for t in root.iter(f"{SVG}text")]


Build = Callable[[Family], tuple[dict[str, Column], list[tuple[Value, ...]]]]


def _xy(value_channel: str) -> Build:
    """x and y both numeric; ``value_channel`` carries the family, the other 1..3."""

    def build(f: Family) -> tuple[dict[str, Column], list[tuple[Value, ...]]]:
        if value_channel == "y":
            return {"x": ORDINAL, "y": f.column}, [
                (n, v) for n, v in zip((1, 2, 3), f.values, strict=True)
            ]
        return {"x": f.column, "y": ORDINAL}, [
            (v, n) for n, v in zip((1, 2, 3), f.values, strict=True)
        ]

    return build


def _bar(f: Family) -> tuple[dict[str, Column], list[tuple[Value, ...]]]:
    return {"x": LABEL, "y": f.column}, list(zip("abc", f.values, strict=True))


def _hbar(f: Family) -> tuple[dict[str, Column], list[tuple[Value, ...]]]:
    return {"y": LABEL, "x": f.column}, list(zip("abc", f.values, strict=True))


def _histogram(f: Family) -> tuple[dict[str, Column], list[tuple[Value, ...]]]:
    return {"x": f.column}, [(v,) for v in f.values]


# the expected description around a (title, low, high) range, per kind and axis
Y_AXIS = "{K} chart: T. x: n; y: {t}. 3 rows. n from 1 to 3; {t} from {lo} to {hi}."
X_AXIS = "{K} chart: T. x: {t}; y: n. 3 rows. {t} from {lo} to {hi}; n from 1 to 3."
AXES: dict[tuple[str, str], tuple[Build, str]] = {
    ("line", "y"): (_xy("y"), Y_AXIS.replace("{K}", "Line")),
    ("line", "x"): (_xy("x"), X_AXIS.replace("{K}", "Line")),
    ("area", "y"): (_xy("y"), Y_AXIS.replace("{K}", "Area")),
    ("area", "x"): (_xy("x"), X_AXIS.replace("{K}", "Area")),
    ("scatter", "y"): (_xy("y"), Y_AXIS.replace("{K}", "Scatter")),
    ("scatter", "x"): (_xy("x"), X_AXIS.replace("{K}", "Scatter")),
    ("bar", "y"): (
        _bar,
        "Bar chart: T. x: label; y: {t}. 3 rows."
        " label from a to c; {t} from {lo} to {hi}.",
    ),
    ("hbar", "x"): (
        _hbar,
        "Hbar chart: T. y: label; x: {t}. 3 rows. {t} from {lo} to {hi}.",
    ),
    ("histogram", "x"): (
        _histogram,
        "Histogram chart: T. x: {t}. 3 rows."
        " {t} from {lo} to {hi}; Count from {c0} to {c1}.",
    ),
}
# family -> (drawn axis title, low, high); the title is what the axis draws too
RANGES = {
    "duration-kind": ("moving (m:ss)", "1:35", "20:34"),
    "duration-kind-hours": ("moving (h:mm:ss)", "0:01:35", "2:01:40"),
    "number-s": ("moving (m:ss)", "1:35", "20:34"),
    "pace": ("pace (min/km)", "4:30 /km", "5:45 /km"),
    "percent": ("grade (%)", "0.0%", "87.5%"),
    "quantity": ("distance (km)", "3.5 km", "42.2 km"),
}
# the histogram's Count range, which depends on the bins the family's data fills
COUNTS = {
    "duration-kind": ("1", "1"),
    "duration-kind-hours": ("1", "1"),
    "number-s": ("1", "1"),
    "pace": ("1", "1"),
    "percent": ("1", "2"),
    "quantity": ("0", "2"),
}


@pytest.mark.parametrize("family", sorted(RANGES))
@pytest.mark.parametrize(("kind", "axis"), sorted(AXES))
def test_a_value_axis_description_names_and_formats_by_unit_family(
    kind: str, axis: str, family: str
) -> None:
    build, template = AXES[(kind, axis)]
    channels, rows = build(FAMILIES[family])
    title, low, high = RANGES[family]
    c0, c1 = COUNTS[family]
    text, texts = _render(kind, channels, rows)
    assert text == template.format(t=title, lo=low, hi=high, c0=c0, c1=c1)
    assert title in texts  # the sentence names the axis as drawn


@pytest.mark.parametrize("kind", ["line", "area", "scatter"])
def test_a_clock_basis_date_time_axis_is_not_formatted_as_a_duration(
    kind: str,
) -> None:
    channels, rows = _xy("x")(FAMILIES["clock"])
    text, texts = _render(kind, channels, rows)
    title = "start (UTC, 2026-03-02)"
    assert text == (
        f"{kind.capitalize()} chart: T. x: {title}; y: n. 3 rows."
        f" {title} from 2026-03-02 06:15 UTC to 2026-03-02 18:40 UTC;"
        " n from 1 to 3."
    )
    assert title in texts
