"""Recovery chart construction from typed consumer records."""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from fitdocs.history import DayRow
from fitdocs.recovery import BaselineDay, RangePosition, charts
from fitdocs.recovery.view import (
    LoadView,
    OtherView,
    Panel,
    RecoveryView,
    ShownDay,
    SignalView,
    SleepView,
    Window,
)
from fitdocs.render.charts.kit import ChartData, ChartError, ChartRequest, render_chart
from fitdocs.wellness import Metric
from tests.render.charts.kit.test_theme_coverage import HEX_LITERAL, violations

NAMES = ("load", "hrv-sdnn", "hrv-rmssd", "resting-hr", "sleep", "other")
START = date(2025, 2, 1)
DAYS = tuple(START + timedelta(days=i) for i in range(90))
# Four independent daily records plus absent window endpoints.
SPECS = (
    ("hrv-sdnn", "hrv_sdnn_ms", "HRV (SDNN)", "ms", 31.0),
    ("hrv-rmssd", "hrv_rmssd_ms", "HRV (rMSSD)", "ms", 71.0),
    ("resting-hr", "resting_hr_bpm", "Resting HR", "bpm", 111.0),
    ("sleep", "sleep_s", "Sleep", "s", 21001.0),
)


def signal(metric_name: str, base: float) -> SignalView:
    metric = Metric(metric_name)
    items = []
    for i, day in enumerate(DAYS):
        if i not in (43, 44, 45, 46, 47):
            items.append(ShownDay(day, None, None))
            continue
        position = (
            RangePosition.ABOVE,
            RangePosition.BELOW,
            RangePosition.WITHIN,
            None,
            None,
        )[i - 43]
        source = "watch-a" if i in (43, 44) else "watch-z"
        bd = BaselineDay(
            metric,
            source,
            day,
            None if i == 47 else base + i - 43,
            "local",
            None if i == 46 else base + i - 33,
            5,
            base + 29,
            4,
            60,
            None if i == 46 else base + i - 63,
            None if i == 46 else base + i - 23,
            position,
        )
        items.append(ShownDay(day, source, bd))
    return SignalView(metric, tuple(items), items[46], (), (), ())


@pytest.fixture
def view() -> RecoveryView:
    signals = tuple(signal(metric, base) for _, metric, _, _, base in SPECS[:3])
    total = signal("sleep_s", 21001.0)
    stage = replace(
        next(b for d in total.days if (b := d.baseline) is not None),
        metric=Metric.SLEEP_DEEP_S,
        value=0.0,
        rolling_mean=9001.0,
        baseline_mean=8001.0,
    )
    load_rows = tuple(
        DayRow(day, 137, 1, 1, 13.0, 29.0, -16.0, False)
        if i == 43
        else DayRow(day, 191, 2, 2, 41.0, 17.0, 24.0, False)
        if i == 44
        else DayRow(day, 223, 3, 3, None, None, None, True)
        if i == 45
        else None
        for i, day in enumerate(DAYS)
    )
    panels = (
        Panel(
            Metric.SPO2_PCT,
            "pulse-z",
            tuple(97.0 if i == 43 else None for i in range(90)),
        ),
        Panel(
            Metric.STEPS,
            "pedometer-a",
            tuple(8123.0 if i == 44 else None for i in range(90)),
        ),
        Panel(
            Metric.STEPS,
            "pedometer-z",
            tuple(9234.0 if i == 43 else None for i in range(90)),
        ),
    )
    return RecoveryView(
        Window(DAYS[-1], DAYS[0]),
        LoadView("threshold", load_rows, 88, None),
        signals,
        SleepView(total, DAYS[46], (stage,)),
        OtherView(panels, ()),
        (),
        (),
        frozenset({"local"}),
    )


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch, view: RecoveryView) -> tuple[Any, Any]:
    calls = []

    def spy(request: ChartRequest, data: ChartData) -> Any:
        result = render_chart(request, data)
        calls.append((request, data, result.text))
        return result

    monkeypatch.setattr(charts, "render_chart", spy)
    return charts.render_charts(view), calls


def test_names() -> None:
    assert charts.CHART_NAMES == NAMES


def test_output(captured: tuple[Any, Any]) -> None:
    output, calls = captured
    assert (tuple(n for n, _ in output), tuple(svg for _, svg in output)) == (
        NAMES,
        tuple(item[2] for item in calls),
    )


REQUESTS = {
    "load": (
        "line",
        "Fitness, fatigue and form",
        (("x", "day"), ("y", "value"), ("color", "series")),
        (("y_zero", True),),
    ),
    "hrv-sdnn": (
        "reference-band",
        "HRV (SDNN)",
        (
            ("x", "day"),
            ("y", "value"),
            ("low", "low"),
            ("high", "high"),
            ("mid", "mean"),
            ("segment", "source"),
            ("flag", "outside"),
        ),
        (),
    ),
    "hrv-rmssd": (
        "reference-band",
        "HRV (rMSSD)",
        (
            ("x", "day"),
            ("y", "value"),
            ("low", "low"),
            ("high", "high"),
            ("mid", "mean"),
            ("segment", "source"),
            ("flag", "outside"),
        ),
        (),
    ),
    "resting-hr": (
        "reference-band",
        "Resting HR",
        (
            ("x", "day"),
            ("y", "value"),
            ("low", "low"),
            ("high", "high"),
            ("mid", "mean"),
            ("segment", "source"),
            ("flag", "outside"),
        ),
        (),
    ),
    "sleep": (
        "reference-band",
        "Sleep",
        (("x", "day"), ("y", "value"), ("mid", "mean"), ("segment", "source")),
        (),
    ),
    "other": (
        "small-multiples",
        "Other signals",
        (("x", "day"), ("y", "value"), ("facet", "panel")),
        (("y_axes", "independent"),),
    ),
}


def expected_columns(name: str) -> tuple[tuple[Any, ...], ...]:
    day = ("day", "date", None, None)
    if name == "load":
        return (
            day,
            ("value", "number", None, "daily-average load"),
            ("series", "category", None, None),
        )
    if name == "other":
        return day, ("value", "number", None, None), ("panel", "category", None, None)
    _, _, label, unit, _ = next(s for s in SPECS if s[0] == name)
    value = ("value", "number", unit, label)
    mean = ("mean", "number", unit, "7-day mean")
    source = ("source", "category", None, None)
    if name == "sleep":
        return day, value, mean, source
    return (
        day,
        value,
        ("low", "number", unit, "normal range low"),
        ("high", "number", unit, "normal range high"),
        mean,
        source,
        ("outside", "boolean", None, "outside the normal range"),
    )


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize(
    "field", ("ref", "kind", "title", "channels", "options", "columns")
)
def test_contract(
    view: RecoveryView, monkeypatch: pytest.MonkeyPatch, name: str, field: str
) -> None:
    count = 0

    def spy(request: ChartRequest, data: ChartData) -> Any:
        nonlocal count
        selected = count == NAMES.index(name)
        count += 1
        if selected:
            kind, title, channels, options = REQUESTS[name]
            actual = {
                "ref": request.ref,
                "kind": request.kind,
                "title": request.title,
                "channels": tuple(request.channels.items()),
                "options": tuple(
                    (k, type(v).__name__, v) for k, v in request.options.items()
                ),
                "columns": tuple(
                    (c.name, c.kind.value, c.unit, c.label) for c in data.columns
                ),
            }
            expected = {
                "ref": name,
                "kind": kind,
                "title": title,
                "channels": channels,
                "options": tuple((k, type(v).__name__, v) for k, v in options),
                "columns": expected_columns(name),
            }
            assert actual[field] == expected[field]
        return render_chart(request, data)

    monkeypatch.setattr(charts, "render_chart", spy)
    charts.render_charts(view)
    assert count == 6


def expected_rows(name: str) -> tuple[tuple[Any, ...], ...]:
    if name == "load":
        return tuple(
            (
                day,
                (
                    (13.0, 29.0, -16.0)
                    if i == 43
                    else (41.0, 17.0, 24.0)
                    if i == 44
                    else (None, None, None)
                )[j],
                role,
            )
            for i, day in enumerate(DAYS)
            for j, role in enumerate(("fitness", "fatigue", "form"))
        )
    if name == "other":
        return tuple(
            (day, value if i == offset else None, panel)
            for i, day in enumerate(DAYS)
            for value, offset, panel in (
                (97.0, 43, "SpO2 (%) · pulse-z"),
                (8123.0, 44, "Steps · pedometer-a"),
                (9234.0, 43, "Steps · pedometer-z"),
            )
        )
    base = next(s[4] for s in SPECS if s[0] == name)
    rows: list[tuple[Any, ...]] = []
    for i, day in enumerate(DAYS):
        present = i in (43, 44, 45, 46, 47)
        value = base + i - 43 if i in (43, 44, 45, 46) else None
        mean = base + i - 33 if i in (43, 44, 45, 47) else None
        source = ("watch-a" if i in (43, 44) else "watch-z") if present else None
        if name == "sleep":
            rows.append((day, value, mean, source))
        else:
            low = base + i - 63 if i in (43, 44, 45, 47) else None
            high = base + i - 23 if i in (43, 44, 45, 47) else None
            rows.append((day, value, low, high, mean, source, i in (43, 44)))
    return tuple(rows)


ROW_FIELDS = tuple((name, col[0]) for name in NAMES for col in expected_columns(name))


@pytest.mark.parametrize(("name", "column"), ROW_FIELDS)
def test_rows(
    view: RecoveryView, monkeypatch: pytest.MonkeyPatch, name: str, column: str
) -> None:
    count = 0

    def spy(request: ChartRequest, data: ChartData) -> Any:
        nonlocal count
        selected = count == NAMES.index(name)
        count += 1
        if selected:
            index = next(
                i for i, col in enumerate(expected_columns(name)) if col[0] == column
            )
            actual = tuple((type(row[index]).__name__, row[index]) for row in data.rows)
            expected = tuple(
                (type(row[index]).__name__, row[index]) for row in expected_rows(name)
            )
            assert actual == expected
        return render_chart(request, data)

    monkeypatch.setattr(charts, "render_chart", spy)
    charts.render_charts(view)
    assert count == 6


@pytest.mark.parametrize("name", NAMES)
def test_svg(captured: tuple[Any, Any], name: str) -> None:
    output, _ = captured
    assert violations(dict(output)[name]) == []


@pytest.mark.parametrize("mask", range(64))
def test_sections(view: RecoveryView, mask: int) -> None:
    enabled = {name for i, name in enumerate(NAMES) if mask & (1 << i)}
    selection = replace(
        view,
        load=view.load if "load" in enabled else LoadView(None, (), 90, "Absent"),
        signals=tuple(
            s
            for s, name in zip(view.signals, NAMES[1:4], strict=True)
            if name in enabled
        ),
        sleep=view.sleep if "sleep" in enabled else None,
        other=view.other if "other" in enabled else None,
    )
    assert tuple(name for name, _ in charts.render_charts(selection)) == tuple(
        n for n in NAMES if n in enabled
    )


def test_chart_error(view: RecoveryView, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ChartError(())

    def fail(request: ChartRequest, data: ChartData) -> Any:
        raise error

    monkeypatch.setattr(charts, "render_chart", fail)
    with pytest.raises(ChartError) as raised:
        charts.render_charts(view)
    assert raised.value is error


def test_no_colour_literals() -> None:
    tree = ast.parse(Path(charts.__file__).read_text(encoding="utf-8"))
    assert [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and HEX_LITERAL.search(node.value)
    ] == []


OTHER_CASES = (
    ("respiration_brpm", "Respiration (br/min)", 12.0),
    ("spo2_pct", "SpO2 (%)", 96.0),
    ("stress_level", "Stress level", 23.0),
    ("body_battery_highest", "Body battery (highest)", 87.0),
    ("body_battery_lowest", "Body battery (lowest)", 19.0),
    ("steps", "Steps", 7481.0),
    ("weight_kg", "Weight (kg)", 68.0),
    ("vo2max_ml_per_kg_min", "VO2max (mL/kg/min)", 41.0),
    ("vo2max_run_ml_per_kg_min", "VO2max (running) (mL/kg/min)", 51.0),
    ("vo2max_ride_ml_per_kg_min", "VO2max (cycling) (mL/kg/min)", 61.0),
    ("fatigue_rating", "Fatigue (rating)", 1.1),
    ("soreness_rating", "Soreness (rating)", 1.2),
    ("mood_rating", "Mood (rating)", 1.3),
    ("motivation_rating", "Motivation (rating)", 1.4),
    ("stress_rating", "Stress (rating)", 1.5),
    ("injury_rating", "Injury (rating)", 1.6),
    ("hydration_rating", "Hydration (rating)", 1.7),
)


@pytest.mark.parametrize(("metric", "label", "value"), OTHER_CASES)
def test_other_metrics(
    view: RecoveryView,
    monkeypatch: pytest.MonkeyPatch,
    metric: str,
    label: str,
    value: float,
) -> None:
    panel = Panel(
        Metric(metric),
        "sensor-own",
        tuple(value if i == 44 else None for i in range(90)),
    )
    selected = replace(view, other=OtherView((panel,), ()))

    def spy(request: ChartRequest, data: ChartData) -> Any:
        if request.ref == "other":
            assert data.rows == tuple(
                (day, value if i == 44 else None, f"{label} · sensor-own")
                for i, day in enumerate(DAYS)
            )
        return render_chart(request, data)

    monkeypatch.setattr(charts, "render_chart", spy)
    assert tuple(name for name, _ in charts.render_charts(selected)) == NAMES


def test_catalog_metadata(view: RecoveryView, monkeypatch: pytest.MonkeyPatch) -> None:
    from fitdocs.wellness import METRICS

    updated = dict(METRICS)
    updated[Metric.HRV_SDNN_MS] = replace(
        updated[Metric.HRV_SDNN_MS], label="Catalog SDNN", unit="bpm"
    )
    updated[Metric.STEPS] = replace(
        updated[Metric.STEPS], label="Catalog steps", unit="kg"
    )
    monkeypatch.setattr(charts, "METRICS", updated)
    count = 0

    def spy(request: ChartRequest, data: ChartData) -> Any:
        nonlocal count
        count += 1
        if request.ref == "hrv-sdnn":
            assert (
                request.title,
                tuple((c.unit, c.label) for c in data.columns[1:5]),
            ) == (
                "Catalog SDNN",
                (
                    ("bpm", "Catalog SDNN"),
                    ("bpm", "normal range low"),
                    ("bpm", "normal range high"),
                    ("bpm", "7-day mean"),
                ),
            )
        if request.ref == "other":
            assert tuple(dict.fromkeys(row[2] for row in data.rows)) == (
                "SpO2 (%) · pulse-z",
                "Catalog steps (kg) · pedometer-a",
                "Catalog steps (kg) · pedometer-z",
            )
        return render_chart(request, data)

    monkeypatch.setattr(charts, "render_chart", spy)
    charts.render_charts(view)
    assert count == 6


SVG = "{http://www.w3.org/2000/svg}"


def test_output_order_from_permuted_signals(view: RecoveryView) -> None:
    selection = replace(
        view, signals=(view.signals[2], view.signals[0], view.signals[1])
    )
    assert tuple(name for name, _ in charts.render_charts(selection)) == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_real_svg_window_description(view: RecoveryView, name: str) -> None:
    root = ET.fromstring(dict(charts.render_charts(view))[name])
    assert "day from 2025-02-01 to 2025-05-01;" in root.findtext(SVG + "desc", "")


# Coordinates are fixed expectations for the synthetic Feb 1 to May 1 window.
AXIS_TICKS = {
    "load": (
        ("37.12", "2025-02"),
        ("242.95", "2025-03"),
        ("470.83", "2025-04"),
        ("691.36", "2025-05"),
    ),
    "hrv-sdnn": (
        ("32.64", "2025-02"),
        ("239.88", "2025-03"),
        ("469.32", "2025-04"),
        ("691.36", "2025-05"),
    ),
    "hrv-rmssd": (
        ("37.12", "2025-02"),
        ("242.95", "2025-03"),
        ("470.83", "2025-04"),
        ("691.36", "2025-05"),
    ),
    "resting-hr": (
        ("37.12", "2025-02"),
        ("242.95", "2025-03"),
        ("470.83", "2025-04"),
        ("691.36", "2025-05"),
    ),
    "sleep": (
        ("65.28", "2025-02"),
        ("262.25", "2025-03"),
        ("480.32", "2025-04"),
        ("691.36", "2025-05"),
    ),
    "other": (("51.2", "2025-02"), ("158.46", "2025-04")),
}


@pytest.mark.parametrize("name", NAMES)
def test_real_svg_time_axis(view: RecoveryView, name: str) -> None:
    root = ET.fromstring(dict(charts.render_charts(view))[name])
    axes = root.findall(f".//{SVG}g[@class='ck-axis']")
    actual = tuple(
        (
            (axis[0].get("x1"), axis[0].get("x2")),
            tuple(
                (text.get("x"), text.text)
                for text in axis.findall(SVG + "text")
                if text.text is not None and text.text.startswith("2025-")
            ),
        )
        for axis in axes
        if any(
            text.text is not None and text.text.startswith("2025-")
            for text in axis.findall(SVG + "text")
        )
    )
    left = {
        "load": "37.12",
        "hrv-sdnn": "32.64",
        "hrv-rmssd": "37.12",
        "resting-hr": "37.12",
        "sleep": "65.28",
        "other": "51.2",
    }[name]
    assert actual == (
        ((left, "213" if name == "other" else "691.36"), AXIS_TICKS[name]),
    ) * (3 if name == "other" else 1)


MARK_GEOMETRY = {
    "load": (
        "353.21,181.15 360.56,112.55",
        "353.21,141.95 360.56,171.35",
        "353.21,252.2 360.56,154.2",
    ),
    "hrv-sdnn": ("350.9,140.37 358.3,137.4",),
    "hrv-rmssd": ("353.21,140.37 360.56,137.4",),
    "resting-hr": ("353.21,140.37 360.56,137.4",),
    "sleep": ("367.77,118.27 374.8,105.2",),
    "other": ("M129.37 72.26h0", "M131.19 60.53h0", "M129.37 74.22h0"),
}


@pytest.mark.parametrize("name", NAMES)
def test_real_svg_mark_geometry(view: RecoveryView, name: str) -> None:
    root = ET.fromstring(dict(charts.render_charts(view))[name])
    tag, attribute = ("path", "d") if name == "other" else ("polyline", "points")
    actual = tuple(
        mark.get(attribute)
        for group in root.findall(f".//{SVG}g[@class='ck-marks']")
        for mark in group.findall(SVG + tag)
    )
    assert actual == MARK_GEOMETRY[name]


CARRIED_ROWS = {
    "hrv-sdnn": {
        "above": (date(2025, 3, 20), None, 32.0, 52.0, 62.0, "watch-z", True),
        "below": (date(2025, 3, 20), None, 32.0, 52.0, 20.0, "watch-z", True),
    },
    "hrv-rmssd": {
        "above": (date(2025, 3, 20), None, 72.0, 92.0, 102.0, "watch-z", True),
        "below": (date(2025, 3, 20), None, 72.0, 92.0, 60.0, "watch-z", True),
    },
    "resting-hr": {
        "above": (date(2025, 3, 20), None, 112.0, 132.0, 142.0, "watch-z", True),
        "below": (date(2025, 3, 20), None, 112.0, 132.0, 100.0, "watch-z", True),
    },
}


@pytest.mark.parametrize("name", ("hrv-sdnn", "hrv-rmssd", "resting-hr"))
@pytest.mark.parametrize("position", ("above", "below"))
def test_carried_day_outside_without_daily_value(
    view: RecoveryView, monkeypatch: pytest.MonkeyPatch, name: str, position: str
) -> None:
    index = NAMES[1:4].index(name)
    selected_signal = view.signals[index]
    base = SPECS[index][4]
    bd = replace(
        next(
            b
            for shown in selected_signal.days
            if shown.day == DAYS[47] and (b := shown.baseline) is not None
        ),
        value=None,
        rolling_mean=base + (31 if position == "above" else -11),
        baseline_mean=base + 11,
        baseline_sd=20.0,
        range_low=base + 1,
        range_high=base + 21,
        position=RangePosition(position),
    )
    updated = replace(
        selected_signal,
        days=tuple(
            replace(shown, baseline=bd) if i == 47 else shown
            for i, shown in enumerate(selected_signal.days)
        ),
    )
    selected = replace(
        view,
        signals=tuple(updated if i == index else s for i, s in enumerate(view.signals)),
    )
    count = 0

    def spy(request: ChartRequest, data: ChartData) -> Any:
        nonlocal count
        if request.ref == name:
            count += 1
            row = data.rows[47]
            assert (type(row[-1]), row) == (bool, CARRIED_ROWS[name][position])
        return render_chart(request, data)

    monkeypatch.setattr(charts, "render_chart", spy)
    charts.render_charts(selected)
    assert count == 1
