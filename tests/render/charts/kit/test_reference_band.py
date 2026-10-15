"""Reference-band cases and behavioral contracts; main() writes goldens."""

from __future__ import annotations

import dataclasses
import itertools
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from fitdocs.render.charts.kit import registry, validate
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.format import display_label
from fitdocs.render.charts.kit.kinds import reference_band as module
from fitdocs.render.charts.kit.kinds.reference_band import KIND
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    FramePlan,
    LegendEntry,
    Rect,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.marks import band_path, line_series
from fitdocs.render.charts.kit.scales import NumericScale, ScaleType, numeric_scale
from fitdocs.render.charts.kit.schema import ChartRequest, OptionValue
from fitdocs.render.charts.kit.theme import SeriesStyle, Shape, series_style, shape_path
from fitdocs.render.charts.svg import el, fmt_num
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

SVG = "{http://www.w3.org/2000/svg}"
COLUMNS = (
    column("time", label="Day"),
    column("value", unit="m", label="Observed"),
    column("floor", unit="m", label="Lower"),
    column("ceiling", unit="m", label="Upper"),
    column("centre", unit="m", label="Baseline"),
    column("source", ValueKind.CATEGORY, label="Source"),
    column("outside", ValueKind.BOOLEAN, label="Outside"),
)
CHANNELS = dict(
    zip(
        ("x", "y", "low", "high", "mid", "segment", "flag"),
        (c.name for c in COLUMNS),
        strict=True,
    )
)
ROWS: tuple[tuple[Value, ...], ...] = (
    (5.0, 39.0, 15.0, 65.0, 32.0, "Alpha", None),
    (1.0, 41.0, 10.0, 60.0, 30.0, "Beta", True),
    (4.0, 43.0, 14.0, 64.0, None, "Alpha", False),
    (2.0, 45.0, None, 62.0, 31.0, "Beta", False),
    (3.0, 47.0, 12.0, None, 33.0, "Alpha", None),
    (6.0, None, 16.0, 66.0, 34.0, "Alpha", True),
    (None, 900.0, 800.0, 1000.0, 850.0, "Beta", True),
)


def request(
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
) -> ChartRequest:
    return chart_request(
        "reference-band", title="Recovery sample", channels=channels, options=options
    )


def render(
    rows: Sequence[Sequence[Value]] = ROWS,
    channels: Mapping[str, str] = CHANNELS,
    columns: Sequence[Column] = COLUMNS,
    options: Mapping[str, OptionValue] | None = None,
) -> str:
    return render_case(KIND, request(channels, options), chart_data(columns, rows)).text


def case(
    name: str,
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
    columns: Sequence[Column] = COLUMNS,
) -> Case:
    return Case(name, request(channels), chart_data(columns, rows))


SWITCH = (
    (4.0, 24.0, 4.0, 44.0, 14.0, "A", False),
    (1.0, 21.0, 1.0, 41.0, 11.0, "A", True),
    (5.0, 25.0, 5.0, 45.0, 15.0, "A", None),
    (2.0, 22.0, 2.0, 42.0, 12.0, "A", False),
    (3.0, 23.0, 3.0, 43.0, 13.0, "B", False),
    (6.0, 26.0, 6.0, 46.0, 16.0, "A", False),
)
LONE = (
    (1.0, 11.0, 1.0, 31.0, None, "A", False),
    (2.0, 12.0, None, 32.0, 22.0, "A", None),
    (3.0, 13.0, 3.0, None, None, "A", False),
    (4.0, 14.0, 4.0, 34.0, None, "A", True),
    (5.0, 15.0, None, None, 25.0, "A", False),
)
CASES = (
    case("typical", ROWS),
    case("empty", ()),
    case(
        "all_absent",
        (
            (1.0, None, None, None, None, "A", False),
            (None, 2.0, 1.0, 3.0, 2.5, "B", True),
        ),
    ),
    case(
        "long_labels",
        ROWS,
        columns=tuple(
            dataclasses.replace(
                c, label=(c.label or "") + " synthetic descriptive label " * 5
            )
            for c in COLUMNS
        ),
    ),
    case("single", ((2.0, 17.0, 13.0, 13.0, 19.0, "A", True),)),
    case(
        "negative",
        (
            (1.0, -7.0, -11.0, 3.0, -5.0, "A", True),
            (2.0, -2.0, -9.0, 5.0, -3.0, "B", False),
        ),
    ),
    case(
        "at_bound",
        tuple(
            (
                float(i),
                float(20 + i % 13),
                float(5 + i % 7),
                float(50 + i % 11),
                float(30 + i % 17),
                "A" if i < 500 else "B",
                i % 100 == 0,
            )
            for i in range(1000)
        ),
    ),
    case(
        "no_band", ROWS, {k: v for k, v in CHANNELS.items() if k not in ("low", "high")}
    ),
    case(
        "absent_segment",
        (
            (3.0, 13.0, 3.0, 33.0, 23.0, "A", False),
            (1.0, 11.0, 1.0, 31.0, 21.0, None, True),
            (2.0, 12.0, 2.0, 32.0, 22.0, "B", False),
        ),
    ),
    case("segment_switch", SWITCH),
    case("lone_edges", LONE),
)


def root(text: str) -> ET.Element:
    return ET.fromstring(text)


def group(text: str, name: str) -> ET.Element | None:
    return root(text).find(f"{SVG}g[@class='{name}']")


def marks(text: str) -> list[ET.Element]:
    g = group(text, "ck-marks")
    return [] if g is None else list(g)


def desc(text: str) -> str | None:
    return root(text).findtext(f"{SVG}desc")


def legends(text: str) -> list[str | None]:
    g = group(text, "ck-legend")
    return [] if g is None else [e.text for e in g if e.tag == SVG + "text"]


@pytest.mark.parametrize("edge", ("low", "high"))
def test_missing_edge(edge: str) -> None:
    channels = {k: v for k, v in CHANNELS.items() if k != edge}
    actual = validate.validate_request(
        request(channels), COLUMNS, KIND, registry.kind_names()
    )
    assert [(p.code.value, p.channel) for p in actual] == [("missing_channel", edge)]


@pytest.mark.parametrize("role", ("y", "low", "high", "mid"))
@pytest.mark.parametrize("mismatch", ("kind", "unit"))
def test_mismatch(role: str, mismatch: str) -> None:
    columns = tuple(
        dataclasses.replace(c, kind=ValueKind.DURATION, unit=None)
        if mismatch == "kind" and c.name == CHANNELS[role]
        else dataclasses.replace(c, unit="w")
        if mismatch == "unit" and c.name == CHANNELS[role]
        else c
        for c in COLUMNS
    )
    actual = validate.validate_request(request(), columns, KIND, registry.kind_names())
    expected_roles = ("low", "high", "mid") if role == "y" else (role,)
    assert [(p.code.value, p.channel, p.column) for p in actual] == [
        (("channel_kind" if mismatch == "kind" else "unit_mismatch"), r, CHANNELS[r])
        for r in expected_roles
    ]


@pytest.mark.parametrize(
    "name,rows,expected",
    (
        (
            "order",
            (
                (3.0, 20.0, 1.0, 8.0, 4.0, "A", False),
                (1.0, 21.0, 9.0, 2.0, 5.0, "A", False),
                (2.0, 22.0, 10.0, 3.0, 6.0, "A", False),
            ),
            [("value_order", 1, 2, "low", "floor")],
        ),
        (
            "duplicate",
            (
                (3.0, 20.0, 1.0, 8.0, 4.0, "A", False),
                (1.0, 21.0, 2.0, 9.0, 5.0, "A", False),
                (2.0, 22.0, 3.0, 10.0, 6.0, "A", False),
                (1.0, 23.0, 4.0, 11.0, 7.0, "A", False),
                (3.0, 24.0, 5.0, 12.0, 8.0, "A", False),
            ),
            [("duplicate_position", 3, None, None, None)],
        ),
        (
            "bound",
            tuple((float(i), 21.0, 2.0, 9.0, 5.0, "A", False) for i in range(1001)),
            [("over_bound", None, 1001, None, None)],
        ),
        (
            "segments",
            tuple((float(i), 21.0, 2.0, 9.0, 5.0, str(i), False) for i in range(9)),
            [("too_many_series", None, None, "segment", "source")],
        ),
    ),
)
def test_refusal(
    name: str,
    rows: Sequence[Sequence[Value]],
    expected: list[tuple[str, int | None, int | None, str | None, str | None]],
) -> None:
    actual = problems_of(KIND, request(), chart_data(COLUMNS, rows))
    assert [
        (p.code.value, p.row, p.rows, p.channel, p.column) for p in actual
    ] == expected


@pytest.mark.parametrize(
    "rows",
    (
        (
            (1.0, 17.0, 3.0, 3.0, 11.0, "A", False),
            (2.0, 19.0, None, 500.0, 13.0, "A", None),
            (3.0, 23.0, -400.0, None, 15.0, "A", True),
        ),
        tuple((float(i), 21.0, 2.0, 9.0, 5.0, str(i % 8), False) for i in range(1000)),
        (
            (None, 17.0, 3.0, 5.0, 11.0, "A", False),
            (None, 19.0, 4.0, 6.0, 13.0, "A", None),
            (1.0, 23.0, 5.0, 7.0, 15.0, "A", True),
        ),
    ),
)
def test_valid_boundaries(rows: Sequence[Sequence[Value]]) -> None:
    assert len(marks(render(rows))) > 0


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_golden(case: Case) -> None:
    assert_golden(
        golden_path("reference-band", case.name, "svg"),
        render_case(KIND, case.request, case.data).text,
    )


def test_declaration() -> None:
    assert (
        [
            (c.name, tuple(k.value for k in c.accepts), c.required)
            for c in KIND.channels
        ],
        [(o.name, o.default) for o in KIND.options],
        KIND.bound.limit,
        KIND.bound.counts,
        KIND.bound.over.value,
        KIND.max_series,
    ) == (
        [
            ("x", ("number", "duration", "date", "datetime"), True),
            ("y", ("number", "duration"), True),
            ("low", ("number", "duration"), False),
            ("high", ("number", "duration"), False),
            ("mid", ("number", "duration"), False),
            ("segment", ("category",), False),
            ("flag", ("boolean",), False),
        ],
        [("y_zero", False), ("width", 720), ("height", 320)],
        1000,
        "rows",
        "refuse",
        8,
    )


def test_registration() -> None:
    assert registry.kind_names() == (
        "line",
        "area",
        "bar",
        "hbar",
        "scatter",
        "histogram",
        "stat",
        "table",
        "calendar-heatmap",
        "heatmap",
        "dual-axis",
        "band",
        "box",
        "mean-max",
        "small-multiples",
        "stacked-100",
        "reference-band",
    )


def test_segment_switch() -> None:
    actual = marks(render(SWITCH))
    assert [
        (
            e.tag.removeprefix(SVG),
            len(re.findall("M|L", e.get("d", ""))),
            len(e.get("points", "").split()),
            e.get("stroke-dasharray"),
        )
        for e in actual
        if e.get("fill-opacity") or e.tag == SVG + "polyline"
    ] == [
        ("path", 4, 0, None),
        ("polyline", 0, 2, None),
        ("path", 6, 0, None),
        ("polyline", 0, 3, None),
    ]


def test_legend() -> None:
    text = render()
    g = group(text, "ck-legend")
    assert (
        legends(text),
        [
            (
                e.tag.removeprefix(SVG),
                e.get("stroke-linecap"),
                e.get("fill"),
                e.get("stroke"),
            )
            for e in (g if g is not None else [])
            if e.tag != SVG + "text"
        ],
    ) == (
        ["Beta", "Alpha", "Observed", "Baseline", "Lower to Upper", "Outside"],
        [
            ("path", "round", "none", series_style(0).color),
            ("path", "square", "none", series_style(1).color),
            ("path", "round", "none", "#7f7f7f"),
            ("line", None, None, "#7f7f7f"),
            ("rect", None, "#7f7f7f", None),
            ("path", None, "#7f7f7f", None),
        ],
    )


@pytest.mark.parametrize("flag", (True, False, None))
def test_flag(flag: bool | None) -> None:
    actual = marks(render(((1.0, 11.0, 1.0, 31.0, 21.0, "A", flag),)))
    assert len([e for e in actual if e.get("fill") == "#7f7f7f"]) == (
        1 if flag is True else 0
    )


def test_absent_segment_order() -> None:
    assert legends(render(CASES[8].data.rows))[:3] == ["B", "A", "—"]


def test_absent_segment_without_mark() -> None:
    assert legends(
        render(
            (
                (1.0, None, None, None, None, None, False),
                (2.0, 12.0, 2.0, 32.0, 22.0, "A", False),
            )
        )
    ) == ["A", "Observed", "Baseline", "Lower to Upper", "Outside"]


def test_counts_and_description() -> None:
    assert desc(render()) == (
        "Reference-band chart: Recovery sample. x: Day; y: Observed (m);"
        " low: Lower (m); high: Upper (m); mid: Baseline (m); segment: Source;"
        " flag: Outside. 7 rows, 2 series. Not drawn: 1 row without x,"
        " 1 row without y, 1 row without low, 1 row without high,"
        " 1 row without mid. Day from 1 to 6;"
        " Observed (m) from 10 m to 66 m."
    )


def test_lone_edges() -> None:
    actual = marks(render(LONE))
    assert (
        len([e for e in actual if e.tag == SVG + "line"]),
        len([e for e in actual if e.get("stroke-width") == "5"]),
        len([e for e in actual if e.get("fill-opacity")]),
        len([e for e in actual if e.tag == SVG + "polyline"]),
    ) == (2, 2, 0, 0)


def main() -> None:
    for c in CASES:
        write_golden(
            golden_path("reference-band", c.name, "svg"),
            render_case(KIND, c.request, c.data).text,
        )


if __name__ == "__main__":
    main()


@pytest.mark.parametrize(
    "omit", ("low-high", "mid", "segment", "flag", "low-high-mid-segment-flag")
)
def test_optional_channels(omit: str) -> None:
    omitted = omit.split("-")
    channels = {k: v for k, v in CHANNELS.items() if k not in omitted}
    text = render(
        (
            (1.0, 17.0, 3.0, 43.0, 31.0, "A", True),
            (2.0, 19.0, 5.0, 45.0, 33.0, "A", False),
        ),
        channels,
    )
    expected = (
        ([] if "segment" in omitted else ["A"])
        + ["Observed"]
        + ([] if "mid" in omitted else ["Baseline"])
        + ([] if "low" in omitted else ["Lower to Upper"])
        + ([] if "flag" in omitted else ["Outside"])
    )
    assert legends(text) == expected


@pytest.mark.parametrize("zero", (False, True))
def test_scale_arguments(monkeypatch: pytest.MonkeyPatch, zero: bool) -> None:
    from fitdocs.render.charts.kit.layout import FramePlan, Rect
    from fitdocs.render.charts.kit.scales import NumericScale, ScaleType

    captured: list[object] = []
    plan = FramePlan(
        997,
        451,
        21.0,
        (),
        29.0,
        Rect(101.0, 103.0, 307.0, 211.0),
        122.0,
        333.0,
        355.0,
        (370.0,),
    )
    monkeypatch.setattr(module, "plan_frame", lambda *args, **kwargs: plan)

    def scale(
        values: Sequence[float],
        column: Column,
        start_px: float,
        end_px: float,
        *,
        scale: ScaleType,
        include_zero: bool,
        nice: bool,
        horizontal: bool,
    ) -> NumericScale:
        captured.append(
            (
                list(values),
                column.name,
                start_px,
                end_px,
                scale.value,
                include_zero,
                nice,
                horizontal,
            )
        )
        return NumericScale(
            ScaleType.LINEAR,
            0.0,
            100.0,
            0.0 if horizontal else 100.0,
            100.0 if horizontal else 0.0,
            (),
            column,
        )

    monkeypatch.setattr(module, "numeric_scale", scale)
    rows = (
        (3.0, 23.0, 5.0, 45.0, 35.0, "A", False),
        (1.0, 17.0, 3.0, 43.0, 31.0, "A", True),
        (2.0, 19.0, -400.0, None, 33.0, "A", None),
        (4.0, 29.0, None, 500.0, 37.0, "A", False),
        (None, 900.0, 800.0, 1000.0, 850.0, "A", True),
    )
    render(rows, options={"y_zero": zero, "width": 997, "height": 451})
    assert captured == [
        (
            [17.0, 31.0, 3.0, 43.0, 19.0, 33.0, 23.0, 35.0, 5.0, 45.0, 29.0, 37.0],
            "value",
            314.0,
            103.0,
            "linear",
            zero,
            True,
            False,
        ),
        ([1.0, 2.0, 3.0, 4.0], "time", 101.0, 408.0, "linear", False, False, True),
        ([1.0, 2.0, 3.0, 4.0], "time", 101.0, 408.0, "linear", False, False, True),
    ]


def test_geometry_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitdocs.render.charts.kit.scales import NumericScale, ScaleType

    captured: dict[str, list[object]] = {"band": [], "line": [], "shape": []}

    def scale(
        values: Sequence[float],
        column: Column,
        start_px: float,
        end_px: float,
        *,
        scale: ScaleType,
        include_zero: bool,
        nice: bool,
        horizontal: bool,
    ) -> NumericScale:
        return NumericScale(
            ScaleType.LINEAR,
            0.0,
            100.0,
            0.0 if horizontal else 100.0,
            100.0 if horizontal else 0.0,
            (),
            column,
        )

    original_band, original_line, original_shape = (
        band_path,
        line_series,
        shape_path,
    )

    def band(xs: Sequence[float], low: Sequence[float], high: Sequence[float]) -> str:
        captured["band"].append((list(xs), list(low), list(high)))
        return original_band(xs, low, high)

    def line(
        points: Sequence[tuple[float, float | None]], style: SeriesStyle
    ) -> list[str]:
        captured["line"].append(
            (list(points), style.color, style.dash, style.shape.value)
        )
        return original_line(points, style)

    def shape(shape: Shape, centres: Sequence[tuple[float, float]], color: str) -> str:
        captured["shape"].append((shape.value, list(centres), color))
        return original_shape(shape, centres, color)

    monkeypatch.setattr(module, "numeric_scale", scale)
    monkeypatch.setattr(module, "band_path", band)
    monkeypatch.setattr(module, "line_series", line)
    monkeypatch.setattr(module, "shape_path", shape)
    rows = (
        (4.0, 29.0, 9.0, 49.0, 39.0, "B", True),
        (1.0, 17.0, 3.0, 43.0, 31.0, "A", None),
        (3.0, None, 7.0, 47.0, None, "B", False),
        (2.0, 19.0, 5.0, 45.0, 33.0, "A", True),
    )
    render(rows)
    assert captured == {
        "band": [
            ([1.0, 2.0], [97.0, 95.0], [57.0, 55.0]),
            ([3.0, 4.0], [93.0, 91.0], [53.0, 51.0]),
        ],
        "line": [
            ([(1.0, 69.0), (2.0, 67.0)], series_style(0).color, None, "circle"),
            ([(3.0, None), (4.0, 61.0)], series_style(1).color, "6 3", "square"),
        ],
        "shape": [
            ("circle", [(1.0, 83.0), (2.0, 81.0)], series_style(0).color),
            ("square", [(4.0, 71.0)], series_style(1).color),
            ("triangle-up", [(2.0, 257.0), (4.0, 257.0)], "#7f7f7f"),
        ],
    }


@pytest.mark.parametrize(
    "kind,values,range_text",
    (
        (ValueKind.NUMBER, (3.0, 1.0, 2.0), "Day from 1 to 3"),
        (
            ValueKind.DURATION,
            (timedelta(seconds=180), timedelta(seconds=60), timedelta(seconds=120)),
            "Day (m:ss) from 1:00 to 3:00",
        ),
        (
            ValueKind.DATE,
            (date(2026, 1, 3), date(2026, 1, 1), date(2026, 1, 2)),
            "Day from 2026-01-01 to 2026-01-03",
        ),
        (
            ValueKind.DATETIME,
            (
                datetime(2026, 1, 1, 12, 0),
                datetime(2026, 1, 1, 10, 0),
                datetime(2026, 1, 1, 11, 0),
            ),
            "Day (2026-01-01) from 2026-01-01 10:00 to 2026-01-01 12:00",
        ),
    ),
)
def test_x_kinds(kind: ValueKind, values: tuple[Value, ...], range_text: str) -> None:
    columns = (dataclasses.replace(COLUMNS[0], kind=kind), *COLUMNS[1:])
    rows = tuple(
        (x, 17.0 + i, 3.0 + i, 43.0 + i, 31.0 + i, "A", i == 0)
        for i, x in enumerate(values)
    )
    text = render(rows, columns=columns)
    assert range_text in (desc(text) or "")


def test_duration_y() -> None:
    columns = tuple(
        dataclasses.replace(c, kind=ValueKind.DURATION, unit=None)
        if c.name in ("value", "floor", "ceiling", "centre")
        else c
        for c in COLUMNS
    )
    rows = (
        (
            1.0,
            timedelta(seconds=270),
            timedelta(seconds=240),
            timedelta(seconds=345),
            timedelta(seconds=300),
            "A",
            False,
        ),
        (
            2.0,
            timedelta(seconds=330),
            timedelta(seconds=255),
            timedelta(seconds=375),
            timedelta(seconds=315),
            "A",
            True,
        ),
    )
    assert "Observed (m:ss) from 4:00 to 6:15" in (
        desc(render(rows, columns=columns)) or ""
    )


@pytest.mark.parametrize(
    "options",
    (
        {"width": 997, "height": 451},
        {"width": 320, "height": 160},
        {"width": 1600, "height": 1200},
    ),
)
def test_sizes(options: Mapping[str, OptionValue]) -> None:
    rendered = root(render(options=options))
    assert (rendered.get("width"), rendered.get("height")) == (
        str(options["width"]),
        str(options["height"]),
    )


def test_zero_option() -> None:
    rows = (
        (1.0, 67.0, 53.0, 93.0, 81.0, "A", False),
        (2.0, 69.0, 55.0, 95.0, 83.0, "A", True),
    )

    def labels(zero: bool) -> list[str | None]:
        return [
            e.text
            for g in root(render(rows, options={"y_zero": zero})).findall(
                f"{SVG}g[@class='ck-axis']"
            )
            for e in g
            if e.tag == SVG + "text" and e.get("text-anchor") == "end"
        ]

    assert ("0" in labels(False), "0" in labels(True)) == (False, True)


@pytest.mark.parametrize("missing", ("low", "high", "mid", "y", "x"))
def test_independent_absence(missing: str) -> None:
    rows: list[list[Value]] = [
        list(r)
        for r in (
            (1.0, 17.0, 3.0, 43.0, 31.0, "A", False),
            (2.0, 19.0, 5.0, 45.0, 33.0, "A", False),
            (3.0, 21.0, 7.0, 47.0, 35.0, "A", False),
            (4.0, 23.0, 9.0, 49.0, 37.0, "A", False),
            (5.0, 25.0, 11.0, 51.0, 39.0, "A", False),
        )
    ]
    rows[2][list(CHANNELS).index(missing)] = None
    actual = marks(render(rows))
    bands = [e for e in actual if e.get("fill-opacity")]
    lines = [e for e in actual if e.tag == SVG + "polyline"]
    points = [e for e in actual if e.get("stroke-width") == "7"]
    assert (
        [len(re.findall("M|L", e.get("d", ""))) for e in bands],
        [len(e.get("points", "").split()) for e in lines],
        [e.get("d", "").count("M") for e in points],
    ) == (
        {
            "low": ([4, 4], [5], [5]),
            "high": ([4, 4], [5], [5]),
            "mid": ([10], [2, 2], [5]),
            "y": ([10], [5], [4]),
            "x": ([8], [4], [4]),
        }[missing]
    )


@pytest.mark.parametrize(
    "name,rows,expected",
    (
        ("empty", (), "Reference-band chart: Recovery sample. No data: no rows."),
        (
            "absent",
            ((1.0, None, None, None, None, "A", False),),
            "Reference-band chart: Recovery sample. "
            "No data: none of the 1 row has a value to draw.",
        ),
    ),
)
def test_no_data(name: str, rows: Sequence[Sequence[Value]], expected: str) -> None:
    text = render(rows)
    assert (marks(text), desc(text), root(text).get("height")) == ([], expected, "320")


def test_at_bound_size() -> None:
    assert len(render_case(KIND, CASES[6].request, CASES[6].data).text.encode()) < 80000


def test_absent_counts_all_channels() -> None:
    rows = (
        (1.0, 17.0, 3.0, 43.0, 31.0, "A", False),
        (2.0, None, None, 45.0, None, "A", False),
        (3.0, None, 7.0, None, None, "A", False),
        (4.0, None, None, None, None, "A", False),
        (None, None, None, None, None, "A", False),
    )
    assert (
        "Not drawn: 1 row without x, 3 rows without y, 2 rows without low,"
        " 2 rows without high, 3 rows without mid." in (desc(render(rows)) or "")
    )


def test_unbound_counts() -> None:
    text = render(
        (
            (1.0, None, None, None, None, "A", False),
            (2.0, 17.0, None, None, None, "A", False),
        ),
        {"x": "time", "y": "value"},
    )
    assert "Not drawn: 1 row without y." in (desc(text) or "")


def test_request_order() -> None:
    assert render(
        channels=dict(reversed(list(CHANNELS.items()))),
        options={"height": 451, "width": 997, "y_zero": True},
    ) == render(options={"y_zero": True, "width": 997, "height": 451})


def test_row_order() -> None:
    assert render(tuple(reversed(ROWS))) == render()


def test_flag_only() -> None:
    rows = (
        (4.0, None, None, None, None, "A", True),
        (1.0, None, None, None, None, "B", None),
        (2.0, None, None, None, None, "A", True),
        (3.0, None, None, None, None, "B", False),
        (None, None, None, None, None, "B", True),
    )
    text = render(rows)
    actual = marks(text)
    assert ([e.get("d", "").count("M") for e in actual], legends(text), desc(text)) == (
        [2],
        ["A", "Observed", "Baseline", "Lower to Upper", "Outside"],
        (
            "Reference-band chart: Recovery sample. x: Day; y: Observed (m);"
            " low: Lower (m); high: Upper (m); mid: Baseline (m); segment: Source;"
            " flag: Outside. 5 rows, 2 series. Not drawn: 1 row without x,"
            " 4 rows without y, 4 rows without low, 4 rows without high,"
            " 4 rows without mid. Day from 2 to 4."
            " Observed (m) range: no numeric values to draw."
        ),
    )


@pytest.mark.parametrize(
    "low,high,message",
    (
        (9.0, 2.0, "Row 1 has low 9 m above high 2 m."),
        (5.2, 5.1, "Row 1 has low 5.2 m above high 5.1 m."),
    ),
)
def test_order_message(low: float, high: float, message: str) -> None:
    rows = (
        (3.0, 17.0, 1.0, 8.0, 4.0, "A", False),
        (1.0, 19.0, low, high, 5.0, "A", False),
    )
    (problem,) = problems_of(KIND, request(), chart_data(COLUMNS, rows))
    assert (problem.message, problem.fix) == (
        message,
        "Swap the low and high bindings, or correct the query so that low "
        "is at most high.",
    )


@pytest.mark.parametrize("mismatch", ("unit", "kind"))
def test_mismatch_details(mismatch: str) -> None:
    columns = tuple(
        dataclasses.replace(c, unit="w")
        if c.name == "floor" and mismatch == "unit"
        else dataclasses.replace(c, kind=ValueKind.DURATION, unit=None)
        if c.name == "floor" and mismatch == "kind"
        else c
        for c in COLUMNS
    )
    (problem,) = validate.validate_request(
        request(), columns, KIND, registry.kind_names()
    )
    expected = (
        (
            "Channel 'low' must have the unit of channel 'y', but "
            "column 'value' has unit 'm' and column 'floor' has unit 'w'.",
            "Bind 'low' to a column with the same unit as 'y'.",
            ("ceiling", "centre"),
        )
        if mismatch == "unit"
        else (
            "Channel 'low' must be the same kind as channel 'y', but "
            "column 'value' is number (unit 'm') and column 'floor' "
            "is duration (no unit).",
            "Bind 'y', 'low', 'high' and 'mid' to columns that are all "
            "number or all duration.",
            ("time", "ceiling", "centre"),
        )
    )
    assert (problem.message, problem.fix, problem.accepted) == expected


def test_zero_values() -> None:
    rows = (
        (1.0, 0.0, -7.0, 13.0, 3.0, "A", False),
        (2.0, 11.0, 0.0, 17.0, 0.0, "A", False),
        (3.0, 15.0, -3.0, 0.0, None, "A", False),
    )
    actual = marks(render(rows))
    assert (
        [e.get("d", "").count("M") for e in actual if e.get("stroke-width") == "7"],
        [len(e.get("points", "").split()) for e in actual if e.tag == SVG + "polyline"],
        [
            len(re.findall("M|L", e.get("d", "")))
            for e in actual
            if e.get("fill-opacity")
        ],
    ) == ([3], [2], [6])


def test_empty_custom_height() -> None:
    assert root(render((), options={"height": 451})).get("height") == "451"


def test_no_unit_y() -> None:
    columns = tuple(dataclasses.replace(c, unit=None) for c in COLUMNS)
    assert "Observed from 10 to 66" in (desc(render(columns=columns)) or "")


@pytest.mark.parametrize("low,high", ((None, None), (500.0, None), (None, -400.0)))
def test_flag_only_lone_edge(low: Value, high: Value) -> None:
    text = render(((1.0, None, low, high, None, "A", True),))
    assert (
        len(marks(text)),
        "range: no numeric values to draw." in (desc(text) or ""),
    ) == (1, True)


def test_legend_flag_shape() -> None:
    g = group(render(), "ck-legend")
    swatches = [] if g is None else [e for e in g if e.tag != SVG + "text"]
    assert [e.get("d", "").endswith("l3.5 7h-7z") for e in swatches] == [
        False,
        False,
        False,
        False,
        False,
        True,
    ]


def test_flag_only_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    from fitdocs.render.charts.kit.scales import NumericScale, ScaleType

    captured: list[object] = []

    def scale(
        values: Sequence[float],
        column: Column,
        start_px: float,
        end_px: float,
        *,
        scale: ScaleType,
        include_zero: bool,
        nice: bool,
        horizontal: bool,
    ) -> NumericScale:
        captured.append(
            (list(values), column.name, scale.value, include_zero, nice, horizontal)
        )
        return NumericScale(ScaleType.LINEAR, 0.0, 100.0, 0.0, 100.0, (), column)

    def shape(shape: Shape, centres: Sequence[tuple[float, float]], color: str) -> str:
        captured.append((shape.value, list(centres), color))
        return shape_path(shape, centres, color)

    monkeypatch.setattr(module, "numeric_scale", scale)
    monkeypatch.setattr(module, "shape_path", shape)
    render(
        (
            (4.0, None, 500.0, None, None, "A", True),
            (2.0, None, None, -400.0, None, "A", True),
            (1.0, None, None, None, None, "A", None),
            (None, None, None, None, None, "A", True),
            (3.0, None, None, None, None, "A", False),
        )
    )
    assert captured == [
        ([2.0, 4.0], "time", "linear", False, False, True),
        ([2.0, 4.0], "time", "linear", False, False, True),
        ("triangle-up", [(2.0, 257.0), (4.0, 257.0)], "#7f7f7f"),
    ]


def test_distinct_counts() -> None:
    rows: list[tuple[Value, ...]] = []
    for i in range(1, 9):
        rows.append(
            (
                float(i),
                None if i == 8 else float(40 + i),
                None if i in (2, 3) else float(i),
                None if i in (4, 5, 6) else float(100 + i),
                None if i in (2, 4, 7, 8) else float(60 + i),
                "A",
                False,
            )
        )
    rows.extend(
        (
            (None, 41.0, 1.0, 101.0, 61.0, "A", True),
            (None, 42.0, 2.0, 102.0, 62.0, "A", None),
        )
    )
    assert (
        "Not drawn: 2 rows without x, 1 row without y, 2 rows without low,"
        " 3 rows without high, 4 rows without mid."
    ) in (desc(render(rows)) or "")


BINDING_PARTITIONS = tuple(itertools.product((False, True), repeat=4))
PARTITION_ROWS: tuple[tuple[Value, ...], ...] = (
    (4.0, 29.0, 9.0, 49.0, 39.0, "B", None),
    (1.0, 17.0, 3.0, 43.0, 31.0, "A", True),
    (3.0, 23.0, 7.0, 47.0, 35.0, "B", False),
    (2.0, 19.0, 5.0, 45.0, 33.0, "A", True),
)


def _partition_channels(
    band: bool, mid: bool, segment: bool, flag: bool
) -> dict[str, str]:
    enabled = {"x", "y"}
    if band:
        enabled.update(("low", "high"))
    if mid:
        enabled.add("mid")
    if segment:
        enabled.add("segment")
    if flag:
        enabled.add("flag")
    return {key: value for key, value in CHANNELS.items() if key in enabled}


def _identity_scales(monkeypatch: pytest.MonkeyPatch) -> None:
    def scale(
        values: Sequence[float],
        column: Column,
        start_px: float,
        end_px: float,
        *,
        scale: ScaleType,
        include_zero: bool,
        nice: bool,
        horizontal: bool,
    ) -> NumericScale:
        return NumericScale(
            ScaleType.LINEAR,
            0.0,
            100.0,
            0.0 if horizontal else 100.0,
            100.0 if horizontal else 0.0,
            (),
            column,
        )

    monkeypatch.setattr(module, "numeric_scale", scale)


def _mark_records(elements: Sequence[ET.Element]) -> list[tuple[str, dict[str, str]]]:
    return [
        (element.tag.removeprefix(SVG), dict(element.attrib)) for element in elements
    ]


def _expected_mark_records(parts: Sequence[str]) -> list[tuple[str, dict[str, str]]]:
    return _mark_records(
        list(
            ET.fromstring(
                '<g xmlns="http://www.w3.org/2000/svg">' + "".join(parts) + "</g>"
            )
        )
    )


def _swatch_records(
    text: str,
) -> list[tuple[str, str | None, str | None, str | None, str | None, str | None, bool]]:
    legend = group(text, "ck-legend")
    return (
        []
        if legend is None
        else [
            (
                element.tag.removeprefix(SVG),
                element.get("fill"),
                element.get("stroke"),
                element.get("stroke-width"),
                element.get("stroke-dasharray"),
                element.get("stroke-linecap"),
                element.get("d", "").endswith("l3.5 7h-7z"),
            )
            for element in legend
            if element.tag != SVG + "text"
        ]
    )


@pytest.mark.parametrize(
    "band,mid,segment,flag", BINDING_PARTITIONS, ids=lambda value: str(int(value))
)
def test_optional_partition_calls(
    monkeypatch: pytest.MonkeyPatch, band: bool, mid: bool, segment: bool, flag: bool
) -> None:
    captured: dict[str, list[object]] = {"band": [], "line": [], "shape": []}

    def draw_band(
        xs: Sequence[float], low: Sequence[float], high: Sequence[float]
    ) -> str:
        captured["band"].append((list(xs), list(low), list(high)))
        return band_path(xs, low, high)

    def draw_line(
        points: Sequence[tuple[float, float | None]], style: SeriesStyle
    ) -> list[str]:
        captured["line"].append((list(points), style))
        return line_series(points, style)

    def draw_shape(
        shape: Shape, centres: Sequence[tuple[float, float]], color: str
    ) -> str:
        captured["shape"].append((shape, list(centres), color))
        return shape_path(shape, centres, color)

    _identity_scales(monkeypatch)
    monkeypatch.setattr(module, "band_path", draw_band)
    monkeypatch.setattr(module, "line_series", draw_line)
    monkeypatch.setattr(module, "shape_path", draw_shape)
    render(PARTITION_ROWS, _partition_channels(band, mid, segment, flag))
    if segment:
        expected_band = (
            [
                ([1.0, 2.0], [97.0, 95.0], [57.0, 55.0]),
                ([3.0, 4.0], [93.0, 91.0], [53.0, 51.0]),
            ]
            if band
            else []
        )
        expected_line = (
            [
                ([(1.0, 69.0), (2.0, 67.0)], series_style(0)),
                ([(3.0, 65.0), (4.0, 61.0)], series_style(1)),
            ]
            if mid
            else []
        )
        expected_shape: list[object] = [
            (Shape.CIRCLE, [(1.0, 83.0), (2.0, 81.0)], series_style(0).color),
            (Shape.SQUARE, [(3.0, 77.0), (4.0, 71.0)], series_style(1).color),
        ]
    else:
        expected_band = (
            [([1.0, 2.0, 3.0, 4.0], [97.0, 95.0, 93.0, 91.0], [57.0, 55.0, 53.0, 51.0])]
            if band
            else []
        )
        expected_line = (
            [([(1.0, 69.0), (2.0, 67.0), (3.0, 65.0), (4.0, 61.0)], series_style(0))]
            if mid
            else []
        )
        expected_shape = [
            (
                Shape.CIRCLE,
                [(1.0, 83.0), (2.0, 81.0), (3.0, 77.0), (4.0, 71.0)],
                series_style(0).color,
            )
        ]
    if flag:
        expected_shape.append(
            (Shape.TRIANGLE_UP, [(1.0, 272.0), (2.0, 272.0)], "#7f7f7f")
        )
    assert captured == {
        "band": expected_band,
        "line": expected_line,
        "shape": expected_shape,
    }


@pytest.mark.parametrize(
    "band,mid,segment,flag", BINDING_PARTITIONS, ids=lambda value: str(int(value))
)
def test_optional_partition_marks(
    monkeypatch: pytest.MonkeyPatch, band: bool, mid: bool, segment: bool, flag: bool
) -> None:
    _identity_scales(monkeypatch)
    text = render(PARTITION_ROWS, _partition_channels(band, mid, segment, flag))
    runs = (
        (
            (
                [1.0, 2.0],
                [97.0, 95.0],
                [57.0, 55.0],
                [(1.0, 69.0), (2.0, 67.0)],
                series_style(0),
            ),
            (
                [3.0, 4.0],
                [93.0, 91.0],
                [53.0, 51.0],
                [(3.0, 65.0), (4.0, 61.0)],
                series_style(1),
            ),
        )
        if segment
        else (
            (
                [1.0, 2.0, 3.0, 4.0],
                [97.0, 95.0, 93.0, 91.0],
                [57.0, 55.0, 53.0, 51.0],
                [(1.0, 69.0), (2.0, 67.0), (3.0, 65.0), (4.0, 61.0)],
                series_style(0),
            ),
        )
    )
    expected: list[str] = []
    for xs, low, high, centre, style in runs:
        if band:
            attrs = {
                "d": band_path(xs, low, high),
                "fill": style.color,
                "fill-opacity": "0.2",
                "stroke": style.color,
                "stroke-width": "1",
            }
            if style.dash is not None:
                attrs["stroke-dasharray"] = style.dash
            expected.append(el("path", attrs))
        if mid:
            expected.extend(line_series(centre, style))
    if segment:
        expected.extend(
            (
                shape_path(
                    Shape.CIRCLE, [(1.0, 83.0), (2.0, 81.0)], series_style(0).color
                ),
                shape_path(
                    Shape.SQUARE, [(3.0, 77.0), (4.0, 71.0)], series_style(1).color
                ),
            )
        )
    else:
        expected.append(
            shape_path(
                Shape.CIRCLE,
                [(1.0, 83.0), (2.0, 81.0), (3.0, 77.0), (4.0, 71.0)],
                series_style(0).color,
            )
        )
    if flag:
        expected.append(
            shape_path(Shape.TRIANGLE_UP, [(1.0, 272.0), (2.0, 272.0)], "#7f7f7f")
        )
    assert _mark_records(marks(text)) == _expected_mark_records(expected)


@pytest.mark.parametrize(
    "band,mid,segment,flag", BINDING_PARTITIONS, ids=lambda value: str(int(value))
)
def test_optional_partition_legend(
    band: bool, mid: bool, segment: bool, flag: bool
) -> None:
    text = render(PARTITION_ROWS, _partition_channels(band, mid, segment, flag))
    neutral = "#7f7f7f" if segment else series_style(0).color
    expected_labels = ["A", "B"] if segment else []
    expected_swatches: list[
        tuple[str, str | None, str | None, str | None, str | None, str | None, bool]
    ] = []
    if segment:
        expected_swatches.extend(
            (
                ("path", "none", series_style(0).color, "7", None, "round", False),
                ("path", "none", series_style(1).color, "7", None, "square", False),
            )
        )
    expected_labels.append("Observed")
    expected_swatches.append(("path", "none", neutral, "7", None, "round", False))
    if mid:
        expected_labels.append("Baseline")
        expected_swatches.append(("line", None, neutral, "1.8", None, None, False))
    if band:
        expected_labels.append("Lower to Upper")
        expected_swatches.append(("rect", neutral, None, None, None, None, False))
    if flag:
        expected_labels.append("Outside")
        expected_swatches.append(("path", neutral, None, None, None, None, True))
    assert (legends(text), _swatch_records(text)) == (
        expected_labels,
        expected_swatches,
    )


@pytest.mark.parametrize(
    "mid,flag,present_y",
    tuple(itertools.product((False, True), repeat=3)),
    ids=lambda value: str(int(value)),
)
def test_unbound_lone_marks(
    monkeypatch: pytest.MonkeyPatch, mid: bool, flag: bool, present_y: bool
) -> None:
    _identity_scales(monkeypatch)
    text = render(
        ((2.0, 17.0 if present_y else None, 13.0, 41.0, 29.0, "unused", True),),
        _partition_channels(True, mid, False, flag),
    )
    color = series_style(0).color
    expected = [
        el(
            "line",
            {
                "x1": "2",
                "y1": "87",
                "x2": "2",
                "y2": "59",
                "stroke": color,
                "stroke-width": "1.8",
                "stroke-linecap": "round",
            },
        )
    ]
    if mid:
        expected.extend(line_series([(2.0, 71.0)], series_style(0)))
    if present_y:
        expected.append(shape_path(Shape.CIRCLE, [(2.0, 83.0)], color))
    if flag:
        expected.append(
            shape_path(
                Shape.TRIANGLE_UP, [(2.0, 272.0 if present_y else 257.0)], "#7f7f7f"
            )
        )
    assert _mark_records(marks(text)) == _expected_mark_records(expected)


@pytest.mark.parametrize("role", ("y", "low", "high", "mid"))
@pytest.mark.parametrize("mismatch", ("kind", "unit", "unit_absent"))
def test_every_mismatch_diagnostic(role: str, mismatch: str) -> None:
    columns = tuple(
        dataclasses.replace(c, kind=ValueKind.DURATION, unit=None)
        if c.name == CHANNELS[role] and mismatch == "kind"
        else dataclasses.replace(c, unit="w" if mismatch == "unit" else None)
        if c.name == CHANNELS[role]
        else c
        for c in COLUMNS
    ) + (
        column("numeric_m", unit="m"),
        column("numeric_w", unit="w"),
        column("duration_ok", ValueKind.DURATION),
    )
    actual = validate.validate_request(request(), columns, KIND, registry.kind_names())
    problem_roles = ("low", "high", "mid") if role == "y" else (role,)
    kind_candidates = {
        "y": ("duration_ok",),
        "low": ("time", "ceiling", "centre", "numeric_m", "numeric_w"),
        "high": ("time", "floor", "centre", "numeric_m", "numeric_w"),
        "mid": ("time", "floor", "ceiling", "numeric_m", "numeric_w"),
    }
    unit_candidates = {
        "low": ("ceiling", "centre", "numeric_m"),
        "high": ("floor", "centre", "numeric_m"),
        "mid": ("floor", "ceiling", "numeric_m"),
    }
    expected = []
    for problem_role in problem_roles:
        name = CHANNELS[problem_role]
        if mismatch == "kind":
            first_kind, other_kind = (
                ("duration", "number") if role == "y" else ("number", "duration")
            )
            first_unit, other_unit = (
                ("no unit", "unit 'm'") if role == "y" else ("unit 'm'", "no unit")
            )
            message = (
                f"Channel '{problem_role}' must be the same kind as channel 'y', "
                f"but column 'value' is {first_kind} ({first_unit}) and column "
                f"'{name}' is {other_kind} ({other_unit})."
            )
            fix = (
                "Bind 'y', 'low', 'high' and 'mid' to columns that are all "
                "number or all duration."
            )
            accepted = kind_candidates[role]
            code = "channel_kind"
        else:
            changed_unit = "unit 'w'" if mismatch == "unit" else "no unit"
            first_unit, other_unit = (
                (changed_unit, "unit 'm'")
                if role == "y"
                else ("unit 'm'", changed_unit)
            )
            message = (
                f"Channel '{problem_role}' must have the unit of channel 'y', but "
                f"column 'value' has {first_unit} and column '{name}' has {other_unit}."
            )
            fix = f"Bind '{problem_role}' to a column with the same unit as 'y'."
            accepted = (
                (("numeric_w",) if mismatch == "unit" else ("time",))
                if role == "y"
                else unit_candidates[role]
            )
            code = "unit_mismatch"
        expected.append((code, problem_role, name, message, fix, accepted))
    assert [
        (p.code.value, p.channel, p.column, p.message, p.fix, p.accepted)
        for p in actual
    ] == expected


@pytest.mark.parametrize("refusal", ("duplicate", "bound", "segments"))
def test_refusal_diagnostics(refusal: str) -> None:
    expected: tuple[str, int | None, int | None, str | None, str | None, str, str]
    if refusal == "duplicate":
        rows: Sequence[Sequence[Value]] = (
            (41.0, 17.0, 3.0, 43.0, 31.0, "A", False),
            (23.0, 19.0, 5.0, 45.0, 33.0, "A", False),
            (11.0, 21.0, 7.0, 47.0, 35.0, "A", False),
            (23.0, 29.0, 9.0, 49.0, 39.0, "A", False),
            (41.0, 31.0, 11.0, 51.0, 37.0, "A", False),
        )
        expected = (
            "duplicate_position",
            3,
            None,
            None,
            None,
            "Row 3 repeats row 1, which has the same Day (23).",
            "Aggregate the rows that share this position, or bind a column to x "
            "that separates them.",
        )
    elif refusal == "bound":
        rows = tuple((float(i), 17.0, 3.0, 43.0, 31.0, "A", False) for i in range(1001))
        expected = (
            "over_bound",
            None,
            1001,
            None,
            None,
            "reference-band draws at most 1000 rows; this data has 1001.",
            "Aggregate the rows (for example by day or week) or limit them "
            "to at most 1000.",
        )
    else:
        rows = tuple((float(i), 17.0, 3.0, 43.0, 31.0, str(i), False) for i in range(9))
        expected = (
            "too_many_series",
            None,
            None,
            "segment",
            "source",
            "reference-band draws at most 8 segments; the segment channel yields 9.",
            "Filter the rows or bind a segment column with at most 8 distinct values.",
        )
    actual = problems_of(KIND, request(), chart_data(COLUMNS, rows))
    assert [
        (p.code.value, p.row, p.rows, p.channel, p.column, p.message, p.fix)
        for p in actual
    ] == [expected]


@pytest.mark.parametrize("edge", ("low", "high"))
def test_missing_edge_diagnostics(edge: str) -> None:
    channels = {key: value for key, value in CHANNELS.items() if key != edge}
    actual = validate.validate_request(
        request(channels), COLUMNS, KIND, registry.kind_names()
    )
    assert [(p.code.value, p.channel, p.message, p.fix) for p in actual] == [
        (
            "missing_channel",
            edge,
            f"Channel '{edge}' must be bound when the other band edge is bound.",
            f"Bind '{edge}', or leave both band edges unbound.",
        )
    ]


@pytest.mark.parametrize("kind", (ValueKind.NUMBER, ValueKind.DURATION))
def test_order_diagnostics_without_unit(kind: ValueKind) -> None:
    columns = tuple(
        dataclasses.replace(c, kind=kind, unit=None)
        if c.name in ("value", "floor", "ceiling", "centre")
        else c
        for c in COLUMNS
    )
    values = (17.0, 300.002, 300.001, 31.0)
    y, low, high, mid = (
        tuple(timedelta(seconds=value) for value in values)
        if kind is ValueKind.DURATION
        else values
    )
    actual = problems_of(
        KIND, request(), chart_data(columns, ((1.0, y, low, high, mid, "A", False),))
    )
    message = (
        "Row 0 has low 300.002 s above high 300.001 s."
        if kind is ValueKind.DURATION
        else "Row 0 has low 300.002 above high 300.001."
    )
    assert [(p.code.value, p.row, p.message, p.fix) for p in actual] == [
        (
            "value_order",
            0,
            message,
            "Swap the low and high bindings, or correct the query so that low "
            "is at most high.",
        )
    ]


@pytest.mark.parametrize("role", ("y", "mid", "band"))
@pytest.mark.parametrize(
    "segment,flag",
    tuple(itertools.product((False, True), repeat=2)),
    ids=lambda value: str(int(value)),
)
def test_isolated_numeric_marks(
    monkeypatch: pytest.MonkeyPatch, role: str, segment: bool, flag: bool
) -> None:
    _identity_scales(monkeypatch)
    channels = _partition_channels(role == "band", role == "mid", segment, flag)
    rows = (
        (
            2.0,
            19.0 if role == "y" else None,
            15.0 if role == "band" else None,
            45.0 if role == "band" else None,
            33.0 if role == "mid" else None,
            "A",
            None,
        ),
        (
            1.0,
            17.0 if role == "y" else None,
            13.0 if role == "band" else None,
            41.0 if role == "band" else None,
            31.0 if role == "mid" else None,
            "A",
            False,
        ),
    )
    if role == "y":
        expected = [
            shape_path(Shape.CIRCLE, [(1.0, 83.0), (2.0, 81.0)], series_style(0).color)
        ]
    elif role == "mid":
        expected = line_series([(1.0, 69.0), (2.0, 67.0)], series_style(0))
    else:
        expected = [
            el(
                "path",
                {
                    "d": band_path([1.0, 2.0], [87.0, 85.0], [59.0, 55.0]),
                    "fill": series_style(0).color,
                    "fill-opacity": "0.2",
                    "stroke": series_style(0).color,
                    "stroke-width": "1",
                },
            )
        ]
    assert _mark_records(marks(render(rows, channels))) == _expected_mark_records(
        expected
    )


@pytest.mark.parametrize(
    "band,mid,segment",
    tuple(itertools.product((False, True), repeat=3)),
    ids=lambda value: str(int(value)),
)
def test_flag_only_binding_partitions(
    monkeypatch: pytest.MonkeyPatch, band: bool, mid: bool, segment: bool
) -> None:
    _identity_scales(monkeypatch)
    rows = (
        (4.0, None, None, None, None, "A", True),
        (1.0, None, 500.0, None, None, "B", False),
        (2.0, None, None, -400.0, None, "A", True),
        (3.0, None, None, None, None, "B", None),
        (None, None, None, None, None, "B", True),
    )
    text = render(rows, _partition_channels(band, mid, segment, True))
    expected_marks = [
        shape_path(Shape.TRIANGLE_UP, [(2.0, 257.0), (4.0, 257.0)], "#7f7f7f")
    ]
    neutral = "#7f7f7f" if segment else series_style(0).color
    expected_labels = ["A"] if segment else []
    expected_swatches: list[
        tuple[str, str | None, str | None, str | None, str | None, str | None, bool]
    ] = []
    if segment:
        expected_swatches.append(
            ("path", "none", series_style(1).color, "7", None, "square", False)
        )
    expected_labels.append("Observed")
    expected_swatches.append(("path", "none", neutral, "7", None, "round", False))
    if mid:
        expected_labels.append("Baseline")
        expected_swatches.append(("line", None, neutral, "1.8", None, None, False))
    if band:
        expected_labels.append("Lower to Upper")
        expected_swatches.append(("rect", neutral, None, None, None, None, False))
    expected_labels.append("Outside")
    expected_swatches.append(("path", neutral, None, None, None, None, True))
    assert (_mark_records(marks(text)), legends(text), _swatch_records(text)) == (
        _expected_mark_records(expected_marks),
        expected_labels,
        expected_swatches,
    )


ScaleContract = tuple[list[float], Column, float, float, ScaleType, bool, bool, bool]
PlanContract = tuple[int, int, list[LegendEntry], float, float, bool, bool, int]
SIZE_CONTEXTS = ((720, 320), (320, 160), (1600, 1200))
Y_CONTEXTS = (
    (ValueKind.NUMBER, None),
    (ValueKind.NUMBER, "m"),
    (ValueKind.NUMBER, "s"),
    (ValueKind.NUMBER, "s_per_km"),
    (ValueKind.DURATION, None),
)


def _overhang_contract(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    left = right = 0.0
    for tick in scale.ticks:
        half = text_width(tick.label, FONT_TEXT) / 2
        pixel = scale.position(tick.value)
        left = max(left, half - pixel + PAD)
        right = max(right, pixel + half - plot.right)
    return left, right


def _real_contract(
    width: int,
    height: int,
    legend: list[LegendEntry],
    x_values: list[float],
    y_values: list[float],
    x_col: Column,
    y_col: Column,
    zero: bool,
    notes: int = 0,
) -> tuple[
    list[PlanContract],
    list[ScaleContract],
    NumericScale | None,
    NumericScale,
    FramePlan,
]:
    has_y = bool(y_values)

    def plan(left: float, right: float) -> tuple[PlanContract, FramePlan]:
        args = (width, height, legend, left, right, True, has_y, notes)
        return args, plan_frame(
            width,
            height,
            legend=legend,
            y_label_width=left,
            x_label_overhang=right,
            has_x_title=True,
            has_y_title=has_y,
            notes=notes,
        )

    first_args, first = plan(0.0, 0.0)
    y_spec: ScaleContract | None = None
    y_scale = None
    label_width = 0.0
    if has_y:
        y_spec = (
            y_values,
            y_col,
            first.plot.bottom,
            first.plot.top,
            ScaleType.LINEAR,
            zero,
            True,
            False,
        )
        y_scale = numeric_scale(
            *y_spec[:4],
            scale=y_spec[4],
            include_zero=y_spec[5],
            nice=y_spec[6],
            horizontal=y_spec[7],
        )
        label_width = max(
            (text_width(tick.label, FONT_TEXT) for tick in y_scale.ticks), default=0.0
        )
        provisional_args, provisional = plan(label_width, 0.0)
    else:
        provisional_args, provisional = first_args, first
    x_first: ScaleContract = (
        x_values,
        x_col,
        provisional.plot.left,
        provisional.plot.right,
        ScaleType.LINEAR,
        False,
        False,
        True,
    )
    x_provisional = numeric_scale(
        *x_first[:4],
        scale=ScaleType.LINEAR,
        include_zero=False,
        nice=False,
        horizontal=True,
    )
    left, right = _overhang_contract(x_provisional, provisional.plot)
    final_args, final = plan(label_width + left, right)
    x_final: ScaleContract = (
        x_values,
        x_col,
        final.plot.left,
        final.plot.right,
        ScaleType.LINEAR,
        False,
        False,
        True,
    )
    x_scale = numeric_scale(
        *x_final[:4],
        scale=ScaleType.LINEAR,
        include_zero=False,
        nice=False,
        horizontal=True,
    )
    plans = (
        [first_args, provisional_args, final_args]
        if has_y
        else [first_args, final_args]
    )
    scales = [y_spec, x_first, x_final] if y_spec is not None else [x_first, x_final]
    return plans, scales, y_scale, x_scale, final


def _observe_real_contract(
    monkeypatch: pytest.MonkeyPatch,
    plans: list[PlanContract],
    scales: list[ScaleContract],
) -> tuple[list[PlanContract], list[ScaleContract]]:
    actual_plans: list[PlanContract] = []
    actual_scales: list[ScaleContract] = []

    def observe_plan(
        width: int,
        height: int,
        *,
        legend: Sequence[LegendEntry],
        y_label_width: float,
        x_label_overhang: float,
        has_x_title: bool,
        has_y_title: bool,
        notes: int,
    ) -> FramePlan:
        actual = (
            width,
            height,
            list(legend),
            y_label_width,
            x_label_overhang,
            has_x_title,
            has_y_title,
            notes,
        )
        index = len(actual_plans)
        assert actual == plans[index]
        actual_plans.append(actual)
        return plan_frame(
            width,
            height,
            legend=legend,
            y_label_width=y_label_width,
            x_label_overhang=x_label_overhang,
            has_x_title=has_x_title,
            has_y_title=has_y_title,
            notes=notes,
        )

    def observe_scale(
        values: Sequence[float],
        column: Column,
        start_px: float,
        end_px: float,
        *,
        scale: ScaleType,
        include_zero: bool,
        nice: bool,
        horizontal: bool,
    ) -> NumericScale:
        actual = (
            list(values),
            column,
            start_px,
            end_px,
            scale,
            include_zero,
            nice,
            horizontal,
        )
        index = len(actual_scales)
        assert actual == scales[index]
        actual_scales.append(actual)
        return numeric_scale(
            values,
            column,
            start_px,
            end_px,
            scale=scale,
            include_zero=include_zero,
            nice=nice,
            horizontal=horizontal,
        )

    monkeypatch.setattr(module, "plan_frame", observe_plan)
    monkeypatch.setattr(module, "numeric_scale", observe_scale)
    return actual_plans, actual_scales


def _literal_legend(
    columns: Sequence[Column],
    band: bool,
    mid: bool,
    segment: bool,
    flag: bool,
    segment_entries: Sequence[tuple[str, int]] = (("A", 0), ("B", 1)),
) -> list[LegendEntry]:
    style = SeriesStyle("#7f7f7f", None, Shape.CIRCLE) if segment else series_style(0)
    result = (
        [
            LegendEntry(label, series_style(index), "shape")
            for label, index in segment_entries
        ]
        if segment
        else []
    )
    result.append(LegendEntry(display_label(columns[1]), style, "shape"))
    if mid:
        result.append(LegendEntry(display_label(columns[4]), style, "line"))
    if band:
        result.append(
            LegendEntry(
                display_label(columns[2]) + " to " + display_label(columns[3]),
                style,
                "block",
            )
        )
    if flag:
        result.append(
            LegendEntry(
                display_label(columns[6]),
                SeriesStyle(style.color, None, Shape.TRIANGLE_UP),
                "shape",
            )
        )
    return result


def _typed_fixture(
    xkind: ValueKind, ykind: ValueKind, yunit: str | None
) -> tuple[
    tuple[Column, ...],
    tuple[tuple[Value, ...], ...],
    list[float],
    list[tuple[float, float, float, float]],
]:
    columns = tuple(
        dataclasses.replace(c, kind=xkind, unit=None)
        if i == 0
        else dataclasses.replace(c, kind=ykind, unit=yunit)
        if i in (1, 2, 3, 4)
        else c
        for i, c in enumerate(COLUMNS)
    )
    raw_x: list[Value]
    if xkind is ValueKind.NUMBER:
        raw_x = [1.17, 2.41, 3.53, 4.89]
        xs = [1.17, 2.41, 3.53, 4.89]
    elif xkind is ValueKind.DURATION:
        xs = [-60.7, 121.2, 86582.3, 173044.4]
        raw_x = [timedelta(seconds=x) for x in xs]
    elif xkind is ValueKind.DATE:
        raw_x = [date(2026, 1, i) for i in range(1, 5)]
        xs = [float(date(2026, 1, i).toordinal()) for i in range(1, 5)]
    else:
        raw_x = [
            datetime(2026, 1, i, i, i + 1, i + 2, (i + 3) * 1000) for i in range(1, 5)
        ]
        xs = [
            float(
                date(2026, 1, i).toordinal() * 86400
                + (i * 3600 + (i + 1) * 60 + i + 2 + (i + 3) / 1000)
            )
            for i in range(1, 5)
        ]
    numeric = [
        (17.0, 3.0, 43.0, 31.0),
        (19.0, 5.0, 45.0, 33.0),
        (23.0, 7.0, 47.0, 35.0),
        (29.0, 9.0, 49.0, 39.0),
    ]
    if ykind is ValueKind.DURATION:
        numeric = [
            (-1020.0, -300.0, 88980.0, 5460.0),
            (1140.0, 300.0, 2700.0, 1980.0),
            (1380.0, 420.0, 2820.0, 88500.0),
            (174540.0, 540.0, 175740.0, 2340.0),
        ]
    rows = []
    for index in (3, 0, 2, 1):
        values = (
            [timedelta(seconds=value) for value in numeric[index]]
            if ykind is ValueKind.DURATION
            else list(numeric[index])
        )
        rows.append(
            (
                raw_x[index],
                *values,
                "A" if index < 2 else "B",
                (True, True, False, None)[index],
            )
        )
    return columns, tuple(rows), xs, numeric


PLANNING_CONTEXTS = tuple(
    (band, mid, segment, flag, xkind, ykind, unit, 720, 320, False)
    for band, mid, segment, flag in BINDING_PARTITIONS
    for xkind in (
        ValueKind.NUMBER,
        ValueKind.DURATION,
        ValueKind.DATE,
        ValueKind.DATETIME,
    )
    for ykind, unit in Y_CONTEXTS
) + tuple(
    (
        band,
        mid,
        segment,
        flag,
        ValueKind.NUMBER,
        ValueKind.NUMBER,
        "m",
        width,
        height,
        zero,
    )
    for band, mid, segment, flag in BINDING_PARTITIONS
    for width, height in SIZE_CONTEXTS
    for zero in (False, True)
)


def _planning_id(
    context: tuple[
        bool, bool, bool, bool, ValueKind, ValueKind, str | None, int, int, bool
    ],
) -> str:
    band, mid, segment, flag, xkind, ykind, unit, width, height, zero = context
    return (
        f"{int(band)}{int(mid)}{int(segment)}{int(flag)}-"
        f"{xkind.value}-{ykind.value}-{unit}-{width}-{height}-z{int(zero)}"
    )


@pytest.mark.parametrize("context", PLANNING_CONTEXTS, ids=_planning_id)
def test_real_optional_planning(
    monkeypatch: pytest.MonkeyPatch,
    context: tuple[
        bool, bool, bool, bool, ValueKind, ValueKind, str | None, int, int, bool
    ],
) -> None:
    band, mid, segment, flag, xkind, ykind, unit, width, height, zero = context
    columns, rows, xs, numeric = _typed_fixture(xkind, ykind, unit)
    values = []
    for y, low, high, centre in numeric:
        values.append(y)
        if mid:
            values.append(centre)
        if band:
            values.extend((low, high))
    legend = _literal_legend(columns, band, mid, segment, flag)
    plans, scales, y_scale, x_scale, final = _real_contract(
        width, height, legend, xs, values, columns[0], columns[1], zero
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    text = render(
        rows,
        _partition_channels(band, mid, segment, flag),
        columns,
        {"width": width, "height": height, "y_zero": zero},
    )
    assert observed == (plans, scales)
    if y_scale is None:
        raise AssertionError("numeric fixture needs a numeric scale")
    expected = []
    groups = ((0, 1), (2, 3)) if segment else ((0, 1, 2, 3),)
    for index, members in enumerate(groups):
        style = series_style(index)
        if band:
            attrs = {
                "d": band_path(
                    [x_scale.position(xs[i]) for i in members],
                    [y_scale.position(numeric[i][1]) for i in members],
                    [y_scale.position(numeric[i][2]) for i in members],
                ),
                "fill": style.color,
                "fill-opacity": "0.2",
                "stroke": style.color,
                "stroke-width": "1",
            }
            if style.dash:
                attrs["stroke-dasharray"] = style.dash
            expected.append(el("path", attrs))
        if mid:
            expected.extend(
                line_series(
                    [
                        (x_scale.position(xs[i]), y_scale.position(numeric[i][3]))
                        for i in members
                    ],
                    style,
                )
            )
    for index, members in enumerate(groups):
        expected.append(
            shape_path(
                series_style(index).shape,
                [
                    (x_scale.position(xs[i]), y_scale.position(numeric[i][0]))
                    for i in members
                ],
                series_style(index).color,
            )
        )
    if flag:
        expected.append(
            shape_path(
                Shape.TRIANGLE_UP,
                [(x_scale.position(xs[i]), final.plot.bottom - 5) for i in (0, 1)],
                "#7f7f7f",
            )
        )
    assert (
        _mark_records(marks(text)),
        root(text).get("width"),
        root(text).get("height"),
    ) == (_expected_mark_records(expected), str(width), str(height))


@pytest.mark.parametrize("role", ("y", "mid", "band", "lone"))
@pytest.mark.parametrize(
    "segment,flag",
    tuple(itertools.product((False, True), repeat=2)),
    ids=lambda value: str(int(value)),
)
@pytest.mark.parametrize("width,height", SIZE_CONTEXTS, ids=("default", "min", "max"))
def test_real_isolated_planning(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    segment: bool,
    flag: bool,
    width: int,
    height: int,
) -> None:
    band = role in ("band", "lone")
    mid = role == "mid"
    xs = [1.17, 2.41, 3.53, 4.89] if role != "lone" else [2.41]
    ys = [17.0, 19.0, 23.0, 29.0]
    lows = [3.0, 5.0, 7.0, 9.0]
    highs = [43.0, 45.0, 47.0, 49.0]
    mids = [31.0, 33.0, 35.0, 39.0]
    indexes = (3, 0, 2, 1) if role != "lone" else (1,)
    rows = tuple(
        (
            ([1.17, 2.41, 3.53, 4.89][i]),
            ys[i] if role == "y" else None,
            lows[i] if band else None,
            highs[i] if band else None,
            mids[i] if mid else None,
            "A",
            False,
        )
        for i in indexes
    )
    values = {
        "y": ys,
        "mid": mids,
        "band": [3.0, 43.0, 5.0, 45.0, 7.0, 47.0, 9.0, 49.0],
        "lone": [5.0, 45.0],
    }[role]
    legend = _literal_legend(COLUMNS, band, mid, segment, flag, (("A", 0),))
    plans, scales, y_scale, x_scale, final = _real_contract(
        width,
        height,
        legend,
        xs,
        values,
        COLUMNS[0],
        COLUMNS[1],
        False,
        0 if role == "y" else 1,
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    text = render(
        rows,
        _partition_channels(band, mid, segment, flag),
        options={"width": width, "height": height},
    )
    assert observed == (plans, scales)
    if y_scale is None:
        raise AssertionError("isolated numeric fixture needs a numeric scale")
    style = series_style(0)
    if role == "y":
        expected = [
            shape_path(
                Shape.CIRCLE,
                [
                    (x_scale.position(x), y_scale.position(y))
                    for x, y in zip(xs, ys, strict=True)
                ],
                style.color,
            )
        ]
    elif role == "mid":
        expected = line_series(
            [
                (x_scale.position(x), y_scale.position(y))
                for x, y in zip(xs, mids, strict=True)
            ],
            style,
        )
    elif role == "band":
        expected = [
            el(
                "path",
                {
                    "d": band_path(
                        [x_scale.position(x) for x in xs],
                        [y_scale.position(low) for low in lows],
                        [y_scale.position(high) for high in highs],
                    ),
                    "fill": style.color,
                    "fill-opacity": "0.2",
                    "stroke": style.color,
                    "stroke-width": "1",
                },
            )
        ]
    else:
        expected = [
            el(
                "line",
                {
                    "x1": fmt_num(x_scale.position(2.41)),
                    "y1": fmt_num(y_scale.position(5.0)),
                    "x2": fmt_num(x_scale.position(2.41)),
                    "y2": fmt_num(y_scale.position(45.0)),
                    "stroke": style.color,
                    "stroke-width": "1.8",
                    "stroke-linecap": "round",
                },
            )
        ]
    assert _mark_records(marks(text)) == _expected_mark_records(expected)


@pytest.mark.parametrize(
    "band,mid,segment",
    tuple(itertools.product((False, True), repeat=3)),
    ids=lambda value: str(int(value)),
)
@pytest.mark.parametrize(
    "xkind", (ValueKind.NUMBER, ValueKind.DURATION, ValueKind.DATE, ValueKind.DATETIME)
)
@pytest.mark.parametrize("width,height", SIZE_CONTEXTS, ids=("default", "min", "max"))
def test_real_flag_only_planning(
    monkeypatch: pytest.MonkeyPatch,
    band: bool,
    mid: bool,
    segment: bool,
    xkind: ValueKind,
    width: int,
    height: int,
) -> None:
    columns, typed_rows, xs, _ = _typed_fixture(xkind, ValueKind.NUMBER, "m")
    rows = tuple(
        (r[0], None, 500.0 if r[5] == "B" else None, None, None, r[5], r[6])
        for r in typed_rows
    )
    legend = _literal_legend(columns, band, mid, segment, True, (("A", 0),))
    plans, scales, _, x_scale, final = _real_contract(
        width, height, legend, xs[:2], [], columns[0], columns[1], False, 1
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    text = render(
        rows,
        _partition_channels(band, mid, segment, True),
        columns,
        {"width": width, "height": height},
    )
    assert observed == (plans, scales)
    expected = shape_path(
        Shape.TRIANGLE_UP,
        [(x_scale.position(x), final.plot.bottom - 5) for x in xs[:2]],
        "#7f7f7f",
    )
    assert (
        _mark_records(marks(text)),
        root(text).get("width"),
        root(text).get("height"),
        "Observed (m) range: no numeric values to draw." in (desc(text) or ""),
    ) == (_expected_mark_records([expected]), str(width), str(height), True)


@pytest.mark.parametrize(
    "band,mid,segment,flag", BINDING_PARTITIONS, ids=lambda value: str(int(value))
)
@pytest.mark.parametrize("empty", (False, True))
@pytest.mark.parametrize("width,height", SIZE_CONTEXTS, ids=("default", "min", "max"))
def test_real_no_data_size(
    band: bool,
    mid: bool,
    segment: bool,
    flag: bool,
    empty: bool,
    width: int,
    height: int,
) -> None:
    rows = (
        ()
        if empty
        else (
            (1.0, None, None, None, None, "A", False),
            (None, None, 500.0, None, None, "A", True),
        )
    )
    text = render(
        rows,
        _partition_channels(band, mid, segment, flag),
        options={"width": width, "height": height},
    )
    expected = (
        "Reference-band chart: Recovery sample. No data: no rows."
        if empty
        else "Reference-band chart: Recovery sample. "
        "No data: none of the 2 rows has a value to draw."
    )
    assert (
        root(text).get("width"),
        root(text).get("height"),
        marks(text),
        desc(text),
    ) == (str(width), str(height), [], expected)


@pytest.mark.parametrize("representation", ("int", "float", "decimal", "duration"))
@pytest.mark.parametrize("role", ("y", "mid", "low", "high", "equal_band"))
@pytest.mark.parametrize(
    "segment,flag",
    tuple(itertools.product((False, True), repeat=2)),
    ids=lambda value: str(int(value)),
)
def test_real_zero_only(
    monkeypatch: pytest.MonkeyPatch,
    representation: str,
    role: str,
    segment: bool,
    flag: bool,
) -> None:
    def value(number: int) -> Value:
        return (
            timedelta(seconds=number)
            if representation == "duration"
            else Decimal(number)
            if representation == "decimal"
            else float(number)
            if representation == "float"
            else number
        )

    columns = tuple(
        dataclasses.replace(c, kind=ValueKind.DURATION, unit=None)
        if representation == "duration" and i in (1, 2, 3, 4)
        else c
        for i, c in enumerate(COLUMNS)
    )
    y = value(0) if role == "y" else None
    mid = value(0) if role == "mid" else None
    low = (
        value(0 if role in ("low", "equal_band") else -7)
        if role in ("low", "high", "equal_band")
        else None
    )
    high = (
        value(41 if role == "low" else 0)
        if role in ("low", "high", "equal_band")
        else None
    )
    values = {
        "y": [0.0],
        "mid": [0.0],
        "low": [0.0, 41.0],
        "high": [-7.0, 0.0],
        "equal_band": [0.0, 0.0],
    }[role]
    band = role in ("low", "high", "equal_band")
    has_mid = role == "mid"
    legend = _literal_legend(columns, band, has_mid, segment, flag, (("A", 0),))
    plans, scales, _, _, _ = _real_contract(
        720,
        320,
        legend,
        [2.0],
        values,
        columns[0],
        columns[1],
        False,
        0 if role == "y" else 1,
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    text = render(
        ((2.0, y, low, high, mid, "A", None),),
        _partition_channels(band, has_mid, segment, flag),
        columns,
    )
    assert (observed, len(marks(text))) == ((plans, scales), 1)


@pytest.mark.parametrize("role", ("y", "mid", "low", "high"))
@pytest.mark.parametrize(
    "segment,flag",
    tuple(itertools.product((False, True), repeat=2)),
    ids=lambda value: str(int(value)),
)
def test_real_zero_scale_entries(
    monkeypatch: pytest.MonkeyPatch, role: str, segment: bool, flag: bool
) -> None:
    y, low, high, mid = {
        "y": (0.0, -7.0, 13.0, 3.0),
        "mid": (11.0, -7.0, 13.0, 0.0),
        "low": (17.0, 0.0, 41.0, 29.0),
        "high": (-17.0, -7.0, 0.0, -3.0),
    }[role]
    legend = _literal_legend(COLUMNS, True, True, segment, flag, (("A", 0),))
    plans, scales, _, _, _ = _real_contract(
        720, 320, legend, [2.0], [y, mid, low, high], COLUMNS[0], COLUMNS[1], False
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    render(
        ((2.0, y, low, high, mid, "A", False),),
        _partition_channels(True, True, segment, flag),
    )
    assert observed == (plans, scales)


@pytest.mark.parametrize(
    "band,mid,flag",
    tuple(itertools.product((False, True), repeat=3)),
    ids=lambda value: str(int(value)),
)
def test_blank_segment_contract(
    monkeypatch: pytest.MonkeyPatch, band: bool, mid: bool, flag: bool
) -> None:
    _identity_scales(monkeypatch)
    rows = (
        (4.0, 29.0, 9.0, 49.0, 39.0, "B", False),
        (1.0, 17.0, 3.0, 43.0, 31.0, "", None),
        (3.0, 23.0, 7.0, 47.0, 35.0, None, False),
        (2.0, 19.0, 5.0, 45.0, 33.0, "A", None),
        (5.0, 37.0, 11.0, 51.0, 41.0, "—", False),
    )
    text = render(rows, _partition_channels(band, mid, True, flag))
    actual = [
        e.attrib
        for e in marks(text)
        if e.get("stroke-width") == "7"
        or e.get("fill") == series_style(2).color
        or e.get("fill") == series_style(3).color
        or e.get("fill") == series_style(4).color
    ]
    expected = [
        shape_path(series_style(i).shape, [(x, y)], series_style(i).color)
        for i, x, y in (
            (0, 1.0, 83.0),
            (1, 2.0, 81.0),
            (2, 4.0, 71.0),
            (3, 5.0, 63.0),
            (4, 3.0, 77.0),
        )
    ]
    labels = (
        [None, "A", "B", "—", "—", "Observed"]
        + (["Baseline"] if mid else [])
        + (["Lower to Upper"] if band else [])
        + (["Outside"] if flag else [])
    )
    assert (actual, legends(text)) == (
        [record[1] for record in _expected_mark_records(expected)],
        labels,
    )


@pytest.mark.parametrize("count", (8, 9))
def test_blank_segment_cap_check(count: int) -> None:
    segments = ["", None, "—", *[str(i) for i in range(count - 3)]]
    rows = tuple(
        (float(i), 17.0 + i, 3.0 + i, 43.0 + i, 31.0 + i, segment, False)
        for i, segment in enumerate(segments)
    )
    bound = validate.bind_request(request(), COLUMNS, KIND)
    actual = KIND.check(validate.bind_chart(bound, rows))
    expected = (
        []
        if count == 8
        else [
            (
                "too_many_series",
                "segment",
                "source",
                "reference-band draws at most 8 segments; "
                "the segment channel yields 9.",
                "Filter the rows or bind a segment column with at most "
                "8 distinct values.",
            )
        ]
    )
    assert [
        (p.code.value, p.channel, p.column, p.message, p.fix) for p in actual
    ] == expected


@pytest.mark.parametrize("case_name", ("equal", "rows", "segments", "absent_x"))
def test_direct_accepted_check(case_name: str) -> None:
    rows: Sequence[Sequence[Value]]
    if case_name == "equal":
        rows = ((1.0, 17.0, 3.0, 3.0, 31.0, "A", False),)
    elif case_name == "rows":
        rows = tuple(
            (float(i), 17.0, 3.0, 43.0, 31.0, str(i % 8), False) for i in range(1000)
        )
    elif case_name == "segments":
        rows = tuple((float(i), 17.0, 3.0, 43.0, 31.0, str(i), False) for i in range(8))
    else:
        rows = (
            (None, 17.0, 3.0, 43.0, 31.0, "A", False),
            (None, 19.0, 5.0, 45.0, 33.0, "A", False),
            (1.0, 23.0, 7.0, 47.0, 35.0, "A", False),
        )
    bound = validate.bind_request(request(), COLUMNS, KIND)
    assert KIND.check(validate.bind_chart(bound, rows)) == ()


@pytest.mark.parametrize("numeric", (False, True))
@pytest.mark.parametrize("axis", ("x", "y", "flags_x"))
@pytest.mark.parametrize("hours", (False, True))
def test_visible_duration_forms(numeric: bool, axis: str, hours: bool) -> None:
    rows: Sequence[Sequence[Value]]

    def change(c: Column) -> Column:
        return dataclasses.replace(
            c,
            kind=ValueKind.NUMBER if numeric else ValueKind.DURATION,
            unit="s" if numeric else None,
        )

    columns = tuple(
        change(c)
        if (
            (axis in ("x", "flags_x") and i == 0) or (axis == "y" and i in (1, 2, 3, 4))
        )
        else c
        for i, c in enumerate(COLUMNS)
    )

    def value(number: int) -> Value:
        return float(number) if numeric else timedelta(seconds=number)

    if axis == "y":
        low, high = (3000, 5400) if hours else (120, 300)
        rows = (
            (
                1.0,
                value(low + 30),
                value(low),
                value(high),
                value(low + 60),
                "A",
                False,
            ),
            (
                2.0,
                value(high - 30),
                value(low + 15),
                value(high - 15),
                value(high - 60),
                "A",
                True,
            ),
        )
        expected = (
            "Observed (h:mm:ss) from 0:50:00 to 1:30:00"
            if hours
            else "Observed (m:ss) from 2:00 to 5:00"
        )
    else:
        first, last = (30, 3900) if hours else (30, 240)
        rows = (
            (
                (value(last), None, None, None, None, "A", True),
                (value(first), None, None, None, None, "A", True),
            )
            if axis == "flags_x"
            else (
                (value(last), 17.0, 3.0, 43.0, 31.0, "A", True),
                (value(first), 19.0, 5.0, 45.0, 33.0, "A", False),
            )
        )
        expected = (
            "Day (h:mm:ss) from 0:00:30 to 1:05:00"
            if hours
            else "Day (m:ss) from 0:30 to 4:00"
        )
    assert expected in (desc(render(rows, columns=columns)) or "")


@pytest.mark.parametrize(
    "kind,unit",
    (
        (ValueKind.DURATION, None),
        (ValueKind.NUMBER, "s"),
        (ValueKind.NUMBER, None),
        (ValueKind.NUMBER, "m"),
    ),
)
@pytest.mark.parametrize("hours", (False, True))
def test_extreme_unit_branches(kind: ValueKind, unit: str | None, hours: bool) -> None:
    col = dataclasses.replace(COLUMNS[1], kind=kind, unit=unit)
    entries: list[tuple[float, Value]] = [
        (3900.0, timedelta(seconds=3900) if kind is ValueKind.DURATION else 3900.0),
        (30.0, timedelta(seconds=30) if kind is ValueKind.DURATION else 30.0),
    ]
    scale = NumericScale(
        ScaleType.LINEAR, 0.0, 4000.0, 100.0, 0.0, (), col, hours=hours
    )
    expected = ("0:00:30", "1:05:00") if hours else ("0:30", "65:00")
    if kind is ValueKind.NUMBER and unit != "s":
        expected = ("30 m", "3900 m") if unit == "m" else ("30", "3900")
    assert module._extremes(entries, col, scale) == expected


@pytest.mark.parametrize(
    "mid,flag,present_y",
    tuple(itertools.product((False, True), repeat=3)),
    ids=lambda value: str(int(value)),
)
def test_real_lone_context(
    monkeypatch: pytest.MonkeyPatch, mid: bool, flag: bool, present_y: bool
) -> None:
    values = ([17.0] if present_y else []) + ([29.0] if mid else []) + [13.0, 41.0]
    legend = _literal_legend(COLUMNS, True, mid, False, flag)
    plans, scales, y_scale, x_scale, final = _real_contract(
        720,
        320,
        legend,
        [2.41],
        values,
        COLUMNS[0],
        COLUMNS[1],
        False,
        0 if present_y else 1,
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    text = render(
        ((2.41, 17.0 if present_y else None, 13.0, 41.0, 29.0, "unused", True),),
        _partition_channels(True, mid, False, flag),
    )
    assert observed == (plans, scales)
    if y_scale is None:
        raise AssertionError("lone-band fixture needs a numeric scale")
    px = x_scale.position(2.41)
    style = series_style(0)
    expected = [
        el(
            "line",
            {
                "x1": fmt_num(px),
                "y1": fmt_num(y_scale.position(13.0)),
                "x2": fmt_num(px),
                "y2": fmt_num(y_scale.position(41.0)),
                "stroke": style.color,
                "stroke-width": "1.8",
                "stroke-linecap": "round",
            },
        )
    ]
    if mid:
        expected.extend(line_series([(px, y_scale.position(29.0))], style))
    if present_y:
        expected.append(
            shape_path(Shape.CIRCLE, [(px, y_scale.position(17.0))], style.color)
        )
    if flag:
        expected.append(
            shape_path(Shape.TRIANGLE_UP, [(px, final.plot.bottom - 5)], "#7f7f7f")
        )
    assert _mark_records(marks(text)) == _expected_mark_records(expected)


@pytest.mark.parametrize("numeric", (False, True))
def test_duration_tick_expansion_hour_form(numeric: bool) -> None:
    columns = tuple(
        dataclasses.replace(
            c,
            kind=ValueKind.NUMBER if numeric else ValueKind.DURATION,
            unit="s" if numeric else None,
        )
        if i in (1, 2, 3, 4)
        else c
        for i, c in enumerate(COLUMNS)
    )

    def value(number: int) -> Value:
        return float(number) if numeric else timedelta(seconds=number)

    rows = (
        (1.0, value(3100), value(3000), value(3599), value(3300), "A", False),
        (2.0, value(3400), value(3150), value(3550), value(3350), "A", True),
    )
    assert "Observed (h:mm:ss) from 0:50:00 to 0:59:59" in (
        desc(render(rows, columns=columns)) or ""
    )


ZERO_X_CONTEXTS = tuple(
    (False, band, mid, segment, flag) for band, mid, segment, flag in BINDING_PARTITIONS
) + tuple(
    (True, band, mid, segment, True)
    for band, mid, segment in itertools.product((False, True), repeat=3)
)


@pytest.mark.parametrize(
    "flags_only,band,mid,segment,flag",
    ZERO_X_CONTEXTS,
    ids=lambda value: str(int(value)),
)
@pytest.mark.parametrize("xkind", (ValueKind.NUMBER, ValueKind.DURATION))
def test_real_zero_x(
    monkeypatch: pytest.MonkeyPatch,
    flags_only: bool,
    band: bool,
    mid: bool,
    segment: bool,
    flag: bool,
    xkind: ValueKind,
) -> None:
    columns = (dataclasses.replace(COLUMNS[0], kind=xkind), *COLUMNS[1:])
    zero: Value = timedelta(0) if xkind is ValueKind.DURATION else 0
    second: Value = timedelta(seconds=4.89) if xkind is ValueKind.DURATION else 4.89
    rows = (
        (
            second,
            None if flags_only else 19.0,
            None if flags_only else 15.0,
            None if flags_only else 45.0,
            None if flags_only else 33.0,
            "A",
            False,
        ),
        (
            zero,
            None if flags_only else 17.0,
            None if flags_only else 13.0,
            None if flags_only else 43.0,
            None if flags_only else 31.0,
            "A",
            True,
        ),
        (None, 900.0, 800.0, 1000.0, 850.0, "A", True),
    )
    values: list[float] = []
    if not flags_only:
        for y, low, high, centre in (
            (17.0, 13.0, 43.0, 31.0),
            (19.0, 15.0, 45.0, 33.0),
        ):
            values.append(y)
            if mid:
                values.append(centre)
            if band:
                values.extend((low, high))
    xs = [0.0] if flags_only else [0.0, 4.89]
    legend = _literal_legend(columns, band, mid, segment, flag, (("A", 0),))
    plans, scales, y_scale, x_scale, final = _real_contract(
        720, 320, legend, xs, values, columns[0], columns[1], False, 1
    )
    observed = _observe_real_contract(monkeypatch, plans, scales)
    text = render(rows, _partition_channels(band, mid, segment, flag), columns)
    expected = []
    if flag:
        expected.append(
            ET.fromstring(
                shape_path(
                    Shape.TRIANGLE_UP,
                    [(x_scale.position(0.0), final.plot.bottom - 5)],
                    "#7f7f7f",
                )
            ).attrib
        )
    actual = [e.attrib for e in marks(text) if e.get("fill") == "#7f7f7f"]
    assert (observed, actual, bool(marks(text))) == ((plans, scales), expected, True)


def _run_category_legend(
    categories: Sequence[tuple[str | None, int]], band: bool, mid: bool, flag: bool
) -> tuple[
    list[str | None],
    list[tuple[str, str | None, str | None, str | None, str | None, str | None, bool]],
]:
    labels = [
        None if label == "" else "—" if label is None else label
        for label, _ in categories
    ]
    swatches = [
        shape_path(series_style(index).shape, [(0.0, 0.0)], series_style(index).color)
        for _, index in categories
    ]
    labels.append("Observed")
    swatches.append(shape_path(Shape.CIRCLE, [(0.0, 0.0)], "#7f7f7f"))
    if mid:
        labels.append("Baseline")
        swatches.append(el("line", {"stroke": "#7f7f7f", "stroke-width": "1.8"}))
    if band:
        labels.append("Lower to Upper")
        swatches.append(el("rect", {"fill": "#7f7f7f"}))
    if flag:
        labels.append("Outside")
        swatches.append(shape_path(Shape.TRIANGLE_UP, [(0.0, 0.0)], "#7f7f7f"))
    return labels, _swatch_records(
        '<svg xmlns="http://www.w3.org/2000/svg"><g class="ck-legend">'
        + "".join(swatches)
        + "</g></svg>"
    )


@pytest.mark.parametrize(
    "segment", ("A", "B", "", None), ids=("same", "ordinary", "blank", "absent")
)
@pytest.mark.parametrize(
    "gap_edges",
    ((None, None), (130.0, None), (None, 170.0)),
    ids=("both_absent", "low_only", "high_only"),
)
@pytest.mark.parametrize("role", ("band", "mid", "both"))
@pytest.mark.parametrize("present_y", (False, True))
@pytest.mark.parametrize(
    "flag_mode", ("unbound_true", "bound_false", "bound_absent", "bound_true")
)
def test_positioned_gap_predicate_contract(
    monkeypatch: pytest.MonkeyPatch,
    segment: str | None,
    gap_edges: tuple[float | None, float | None],
    role: str,
    present_y: bool,
    flag_mode: str,
) -> None:
    _identity_scales(monkeypatch)
    band, mid, flag = role != "mid", role != "band", flag_mode != "unbound_true"
    flag_value = (
        None
        if flag_mode == "bound_absent"
        else flag_mode in ("unbound_true", "bound_true")
    )
    rows = (
        (5.0, 25.0, 11.0, 51.0, 41.0, "A", False),
        (1.0, 17.0, 3.0, 43.0, 31.0, "A", False),
        (3.0, 77.0 if present_y else None, *gap_edges, None, segment, flag_value),
        (4.0, 23.0, 9.0, 49.0, 39.0, "A", False),
        (2.0, 19.0, 5.0, 45.0, 33.0, "A", False),
    )
    text = render(rows, _partition_channels(band, mid, True, flag))
    color = series_style(0).color
    expected_runs: list[tuple[str, dict[str, str]]] = []
    pairs = (
        ("M1 57L2 55L2 95L1 97Z", "1,69 2,67"),
        ("M4 51L5 49L5 89L4 91Z", "4,61 5,59"),
    )
    if segment == "A":
        if band:
            expected_runs.extend(
                (
                    "path",
                    {
                        "d": path,
                        "fill": color,
                        "fill-opacity": "0.2",
                        "stroke": color,
                        "stroke-width": "1",
                    },
                )
                for path, _ in pairs
            )
        if mid:
            expected_runs.extend(
                (
                    "polyline",
                    {
                        "points": points,
                        "fill": "none",
                        "stroke": color,
                        "stroke-width": "1.8",
                    },
                )
                for _, points in pairs
            )
    else:
        for path, points in pairs:
            if band:
                expected_runs.append(
                    (
                        "path",
                        {
                            "d": path,
                            "fill": color,
                            "fill-opacity": "0.2",
                            "stroke": color,
                            "stroke-width": "1",
                        },
                    )
                )
            if mid:
                expected_runs.append(
                    (
                        "polyline",
                        {
                            "points": points,
                            "fill": "none",
                            "stroke": color,
                            "stroke-width": "1.8",
                        },
                    )
                )
    actual = _mark_records(marks(text))
    assert actual[: len(expected_runs)] == expected_runs
    a_points = [(1.0, 83.0), (2.0, 81.0)]
    if segment == "A" and present_y:
        a_points.append((3.0, 23.0))
    a_points.extend(((4.0, 77.0), (5.0, 75.0)))
    expected_points_flags = [shape_path(Shape.CIRCLE, a_points, color)]
    if segment != "A" and present_y:
        expected_points_flags.append(
            shape_path(Shape.SQUARE, [(3.0, 23.0)], series_style(1).color)
        )
    categories: list[tuple[str | None, int]] = [("A", 0)]
    if segment != "A" and (present_y or flag_mode == "bound_true"):
        categories.append((segment, 1))
    if flag_mode == "bound_true":
        expected_frame = plan_frame(
            720,
            320,
            legend=_literal_legend(
                COLUMNS,
                band,
                mid,
                True,
                flag,
                tuple(
                    ("—" if label is None else label, index)
                    for label, index in categories
                ),
            ),
            y_label_width=0.0,
            x_label_overhang=0.0,
            has_x_title=True,
            has_y_title=True,
            notes=1,
        )
        expected_points_flags.append(
            shape_path(
                Shape.TRIANGLE_UP, [(3.0, expected_frame.plot.bottom - 5)], "#7f7f7f"
            )
        )
    assert actual[len(expected_runs) :] == _expected_mark_records(expected_points_flags)
    assert (legends(text), _swatch_records(text)) == _run_category_legend(
        categories, band, mid, flag
    )


@pytest.mark.parametrize("role", ("band", "mid", "both"))
@pytest.mark.parametrize("lone", (False, True))
@pytest.mark.parametrize("blank_first", (False, True))
@pytest.mark.parametrize("present_y", (False, True))
def test_category_run_owned_styles(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    lone: bool,
    blank_first: bool,
    present_y: bool,
) -> None:
    _identity_scales(monkeypatch)
    categories = ("", "A", "—", None) if blank_first else ("A", "", "—", None)
    rows: list[tuple[Value, ...]] = []
    expected: list[tuple[str, dict[str, str]]] = []
    for index, category in enumerate(categories):
        a, b = 1 + index * 3, 2 + index * 3
        style = series_style(index)
        rows.append(
            (float(a), 17.0 if present_y else None, 3.0, 43.0, 31.0, category, False)
        )
        if not lone:
            rows.append(
                (
                    float(b),
                    19.0 if present_y else None,
                    5.0,
                    45.0,
                    33.0,
                    category,
                    False,
                )
            )
        if role != "mid":
            if lone:
                expected.append(
                    (
                        "line",
                        {
                            "x1": str(a),
                            "y1": "97",
                            "x2": str(a),
                            "y2": "57",
                            "stroke": style.color,
                            "stroke-width": "1.8",
                            "stroke-linecap": "round",
                        },
                    )
                )
            else:
                attrs = {
                    "d": f"M{a} 57L{b} 55L{b} 95L{a} 97Z",
                    "fill": style.color,
                    "fill-opacity": "0.2",
                    "stroke": style.color,
                    "stroke-width": "1",
                }
                if style.dash is not None:
                    attrs["stroke-dasharray"] = style.dash
                expected.append(("path", attrs))
        if role != "band":
            if lone:
                expected.append(
                    (
                        "path",
                        {
                            "d": f"M{a} 69h0",
                            "fill": "none",
                            "stroke": style.color,
                            "stroke-width": "5",
                            "stroke-linecap": "round",
                        },
                    )
                )
            else:
                attrs = {
                    "points": f"{a},69 {b},67",
                    "fill": "none",
                    "stroke": style.color,
                    "stroke-width": "1.8",
                }
                if style.dash is not None:
                    attrs["stroke-dasharray"] = style.dash
                expected.append(("polyline", attrs))
    text = render(
        tuple(reversed(rows)),
        _partition_channels(role != "mid", role != "band", True, False),
    )
    actual = _mark_records(marks(text))
    assert (actual[:-4] if present_y else actual) == expected
    assert (legends(text), _swatch_records(text)) == _run_category_legend(
        list(zip(categories, range(4), strict=True)),
        role != "mid",
        role != "band",
        False,
    )


def _complete_legend_records(
    text: str,
) -> list[tuple[str, dict[str, str], str | None]] | None:
    legend = group(text, "ck-legend")
    return (
        [(child.tag, dict(child.attrib), child.text) for child in legend]
        if legend is not None
        else None
    )


def _identity_legend_plan(
    band: bool,
    mid: bool,
    segment: bool,
    flag: bool,
    entries: Sequence[tuple[str, int]],
    notes: int,
) -> FramePlan:
    return plan_frame(
        720,
        320,
        legend=_literal_legend(COLUMNS, band, mid, segment, flag, entries),
        y_label_width=0.0,
        x_label_overhang=0.0,
        has_x_title=True,
        has_y_title=True,
        notes=notes,
    )


def _planned_complete_legend(
    plan: FramePlan,
) -> list[tuple[str, dict[str, str], str | None]] | None:
    from fitdocs.render.charts.kit import frame

    return _complete_legend_records(
        '<svg xmlns="http://www.w3.org/2000/svg">' + frame.legend(plan) + "</svg>"
    )


@pytest.mark.parametrize("role", ("band", "mid", "both"))
@pytest.mark.parametrize("present_y", (False, True))
@pytest.mark.parametrize(
    "flag_mode", ("unbound_true", "bound_false", "bound_absent", "bound_true")
)
@pytest.mark.parametrize(
    "gap_edges",
    ((None, None), (130.0, None), (None, 170.0)),
    ids=("both_absent", "low_only", "high_only"),
)
def test_unbound_positioned_gap_contract(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    present_y: bool,
    flag_mode: str,
    gap_edges: tuple[float | None, float | None],
) -> None:
    _identity_scales(monkeypatch)
    band, mid, flag = role != "mid", role != "band", flag_mode != "unbound_true"
    flag_value = (
        None
        if flag_mode == "bound_absent"
        else flag_mode in ("unbound_true", "bound_true")
    )
    rows = (
        (5.0, 25.0, 11.0, 51.0, 41.0, "ignored", False),
        (1.0, 17.0, 3.0, 43.0, 31.0, "ignored", False),
        (3.0, 77.0 if present_y else None, *gap_edges, None, "ignored", flag_value),
        (4.0, 23.0, 9.0, 49.0, 39.0, "ignored", False),
        (2.0, 19.0, 5.0, 45.0, 33.0, "ignored", False),
    )
    text = render(rows, _partition_channels(band, mid, False, flag))
    color = series_style(0).color
    expected_runs: list[tuple[str, dict[str, str]]] = []
    if band:
        expected_runs.extend(
            (
                "path",
                {
                    "d": path,
                    "fill": color,
                    "fill-opacity": "0.2",
                    "stroke": color,
                    "stroke-width": "1",
                },
            )
            for path in ("M1 57L2 55L2 95L1 97Z", "M4 51L5 49L5 89L4 91Z")
        )
    if mid:
        expected_runs.extend(
            (
                "polyline",
                {
                    "points": points,
                    "fill": "none",
                    "stroke": color,
                    "stroke-width": "1.8",
                },
            )
            for points in ("1,69 2,67", "4,61 5,59")
        )
    actual = _mark_records(marks(text))
    assert actual[: len(expected_runs)] == expected_runs
    points = [(1.0, 83.0), (2.0, 81.0)]
    if present_y:
        points.append((3.0, 23.0))
    points.extend(((4.0, 77.0), (5.0, 75.0)))
    remainder = [shape_path(Shape.CIRCLE, points, color)]
    plan = _identity_legend_plan(band, mid, False, flag, (), 1)
    if flag_mode == "bound_true":
        remainder.append(
            shape_path(Shape.TRIANGLE_UP, [(3.0, plan.plot.bottom - 5)], "#7f7f7f")
        )
    assert actual[len(expected_runs) :] == _expected_mark_records(remainder)
    assert _complete_legend_records(text) == _planned_complete_legend(plan)


_EIGHT_CATEGORY_INDICES: tuple[tuple[str | None, int], ...] = (
    ("A", 0),
    ("B", 1),
    ("C", 2),
    ("D", 3),
    ("E", 4),
    ("—", 5),
    ("", 6),
    (None, 7),
)


def _eight_style_fixture(
    role: str, lone: bool, present_y: bool
) -> tuple[
    str, list[tuple[str, dict[str, str]]], list[tuple[str, dict[str, str]]], FramePlan
]:
    rows: list[tuple[Value, ...]] = []
    runs: list[tuple[str, dict[str, str]]] = []
    points: list[str] = []
    for category, index in _EIGHT_CATEGORY_INDICES:
        a, b = 1 + 3 * index, 2 + 3 * index
        style = series_style(index)
        rows.append(
            (float(a), 17.0 if present_y else None, 3.0, 43.0, 31.0, category, False)
        )
        if not lone:
            rows.append(
                (
                    float(b),
                    19.0 if present_y else None,
                    5.0,
                    45.0,
                    33.0,
                    category,
                    False,
                )
            )
        if role != "mid":
            if lone:
                runs.append(
                    (
                        "line",
                        {
                            "x1": str(a),
                            "y1": "97",
                            "x2": str(a),
                            "y2": "57",
                            "stroke": style.color,
                            "stroke-width": "1.8",
                            "stroke-linecap": "round",
                        },
                    )
                )
            else:
                attrs = {
                    "d": f"M{a} 57L{b} 55L{b} 95L{a} 97Z",
                    "fill": style.color,
                    "fill-opacity": "0.2",
                    "stroke": style.color,
                    "stroke-width": "1",
                }
                if style.dash is not None:
                    attrs["stroke-dasharray"] = style.dash
                runs.append(("path", attrs))
        if role != "band":
            if lone:
                runs.append(
                    (
                        "path",
                        {
                            "d": f"M{a} 69h0",
                            "fill": "none",
                            "stroke": style.color,
                            "stroke-width": "5",
                            "stroke-linecap": "round",
                        },
                    )
                )
            else:
                attrs = {
                    "points": f"{a},69 {b},67",
                    "fill": "none",
                    "stroke": style.color,
                    "stroke-width": "1.8",
                }
                if style.dash is not None:
                    attrs["stroke-dasharray"] = style.dash
                runs.append(("polyline", attrs))
        if present_y:
            positions = (
                [(float(a), 83.0)] if lone else [(float(a), 83.0), (float(b), 81.0)]
            )
            points.append(shape_path(style.shape, positions, style.color))
    text = render(
        tuple(reversed(rows)),
        _partition_channels(role != "mid", role != "band", True, False),
    )
    entries = tuple(
        ("—" if category is None else category, index)
        for category, index in _EIGHT_CATEGORY_INDICES
    )
    plan = _identity_legend_plan(
        role != "mid", role != "band", True, False, entries, 0 if present_y else 1
    )
    return text, runs, _expected_mark_records(points), plan


@pytest.mark.parametrize("role", ("band", "mid", "both"))
@pytest.mark.parametrize("lone", (False, True))
@pytest.mark.parametrize("present_y", (False, True))
def test_all_eight_complete_runs(
    monkeypatch: pytest.MonkeyPatch, role: str, lone: bool, present_y: bool
) -> None:
    _identity_scales(monkeypatch)
    text, expected_runs, _, _ = _eight_style_fixture(role, lone, present_y)
    actual = _mark_records(marks(text))
    assert (actual[:-8] if present_y else actual) == expected_runs


@pytest.mark.parametrize("role", ("band", "mid", "both"))
@pytest.mark.parametrize("lone", (False, True))
@pytest.mark.parametrize("present_y", (False, True))
def test_all_eight_complete_points(
    monkeypatch: pytest.MonkeyPatch, role: str, lone: bool, present_y: bool
) -> None:
    _identity_scales(monkeypatch)
    text, expected_runs, expected_points, _ = _eight_style_fixture(
        role, lone, present_y
    )
    assert _mark_records(marks(text))[len(expected_runs) :] == expected_points


@pytest.mark.parametrize("role", ("band", "mid", "both"))
@pytest.mark.parametrize("lone", (False, True))
@pytest.mark.parametrize("present_y", (False, True))
def test_all_eight_complete_legends(
    monkeypatch: pytest.MonkeyPatch, role: str, lone: bool, present_y: bool
) -> None:
    _identity_scales(monkeypatch)
    text, _, _, plan = _eight_style_fixture(role, lone, present_y)
    assert _complete_legend_records(text) == _planned_complete_legend(plan)


RECEIVED_LIMIT_CASES = tuple(
    (limit, count, x_present, marked, category)
    for limit in ("rows", "segments")
    for count in ((1000, 1001) if limit == "rows" else (8, 9))
    for x_present in (False, True)
    for marked in (False, True)
    for category in (("ordinary",) if limit == "rows" else ("ordinary", "absent"))
)


def _received_limit_rows(
    limit: str, count: int, x_present: bool, marked: bool, category: str
) -> tuple[tuple[Value, ...], ...]:
    rows: list[tuple[Value, ...]] = [
        (float(i), 17.0, 3.0, 43.0, 31.0, "A" if limit == "rows" else f"S{i}", False)
        for i in range(count)
    ]
    terminal = list(rows[-1])
    if not x_present:
        terminal[0] = None
    if not marked:
        terminal[1:5] = [None] * 4
    if category == "absent":
        terminal[5] = None
    rows[-1] = tuple(terminal)
    return tuple(rows)


def _received_limit_problems(limit: str, count: int) -> list[dict[str, object]]:
    if count == (1000 if limit == "rows" else 8):
        return []
    if limit == "rows":
        return [
            {
                "ref": "c1",
                "kind": "reference-band",
                "code": "over_bound",
                "message": (
                    "reference-band draws at most 1000 rows; this data has 1001."
                ),
                "fix": (
                    "Aggregate the rows (for example by day or week) "
                    "or limit them to at most 1000."
                ),
                "channel": None,
                "column": None,
                "option": None,
                "row": None,
                "rows": 1001,
                "accepted": [],
            }
        ]
    return [
        {
            "ref": "c1",
            "kind": "reference-band",
            "code": "too_many_series",
            "message": (
                "reference-band draws at most 8 segments; the segment channel yields 9."
            ),
            "fix": (
                "Filter the rows or bind a segment column "
                "with at most 8 distinct values."
            ),
            "channel": "segment",
            "column": "source",
            "option": None,
            "row": None,
            "rows": None,
            "accepted": [],
        }
    ]


@pytest.mark.parametrize("limit,count,x_present,marked,category", RECEIVED_LIMIT_CASES)
def test_received_limits_public(
    limit: str, count: int, x_present: bool, marked: bool, category: str
) -> None:
    from fitdocs.render.charts.kit import render_chart
    from fitdocs.render.charts.kit.problems import ChartError

    data = chart_data(
        COLUMNS, _received_limit_rows(limit, count, x_present, marked, category)
    )
    try:
        render_chart(request(), data)
    except ChartError as error:
        returned = False
        actual = [problem.as_dict() for problem in error.problems]
    else:
        returned = True
        actual = []
    assert (returned, actual) == (
        count == (1000 if limit == "rows" else 8),
        _received_limit_problems(limit, count),
    )


@pytest.mark.parametrize(
    "limit,count,x_present,marked,category",
    tuple(
        case for case in RECEIVED_LIMIT_CASES if case[0] == "segments" and case[1] == 9
    ),
)
def test_received_segments_check(
    limit: str, count: int, x_present: bool, marked: bool, category: str
) -> None:
    data = chart_data(
        COLUMNS, _received_limit_rows(limit, count, x_present, marked, category)
    )
    bound = validate.bind_request(request(), COLUMNS, KIND)
    problems = KIND.check(validate.bind_chart(bound, data.rows))
    assert [problem.as_dict() for problem in problems] == _received_limit_problems(
        limit, count
    )
