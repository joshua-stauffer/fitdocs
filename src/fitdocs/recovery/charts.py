"""Chart-kit requests for the typed recovery page."""

from __future__ import annotations

from typing import Final

from fitdocs.recovery.baselines import RangePosition
from fitdocs.recovery.view import RecoveryView, SignalView
from fitdocs.render.charts.kit import (
    ChartData,
    ChartRequest,
    Column,
    Value,
    ValueKind,
    render_chart,
)
from fitdocs.units import unit_named
from fitdocs.wellness import METRICS, Metric

CHART_NAMES: Final = (
    "load",
    "hrv-sdnn",
    "hrv-rmssd",
    "resting-hr",
    "sleep",
    "other",
)


def _render(request: ChartRequest, data: ChartData) -> str:
    return render_chart(request, data).text


def _signal_chart(
    name: str, signal: SignalView, *, sleep: bool = False
) -> tuple[str, str]:
    info = METRICS[signal.metric]
    columns = [
        Column("day", ValueKind.DATE),
        Column("value", ValueKind.NUMBER, info.unit, info.label),
    ]
    channels = {"x": "day", "y": "value"}
    if not sleep:
        columns.extend(
            (
                Column("low", ValueKind.NUMBER, info.unit, "normal range low"),
                Column("high", ValueKind.NUMBER, info.unit, "normal range high"),
            )
        )
        channels.update(low="low", high="high")
    columns.extend(
        (
            Column("mean", ValueKind.NUMBER, info.unit, "7-day mean"),
            Column("source", ValueKind.CATEGORY),
        )
    )
    channels.update(mid="mean", segment="source")
    if not sleep:
        columns.append(
            Column("outside", ValueKind.BOOLEAN, label="outside the normal range")
        )
        channels["flag"] = "outside"
    rows: list[tuple[Value, ...]] = []
    for shown in signal.days:
        bd = shown.baseline
        cells: list[Value] = [shown.day, bd.value if bd is not None else None]
        if not sleep:
            cells.extend(
                (
                    bd.range_low if bd is not None else None,
                    bd.range_high if bd is not None else None,
                )
            )
        cells.extend((bd.rolling_mean if bd is not None else None, shown.source))
        if not sleep:
            cells.append(
                bd is not None
                and bd.position in (RangePosition.ABOVE, RangePosition.BELOW)
            )
        rows.append(tuple(cells))
    request = ChartRequest(name, "reference-band", info.label, channels)
    return name, _render(request, ChartData(tuple(columns), tuple(rows)))


def render_charts(view: RecoveryView) -> tuple[tuple[str, str], ...]:
    charts: dict[str, str] = {}
    if view.load.rows:
        request = ChartRequest(
            "load",
            "line",
            "Fitness, fatigue and form",
            {"x": "day", "y": "value", "color": "series"},
            {"y_zero": True},
        )
        data = ChartData(
            (
                Column("day", ValueKind.DATE),
                Column("value", ValueKind.NUMBER, label="daily-average load"),
                Column("series", ValueKind.CATEGORY),
            ),
            tuple(
                (day, getattr(row, role) if row is not None else None, role)
                for day, row in zip(view.window.days(), view.load.rows, strict=True)
                for role in ("fitness", "fatigue", "form")
            ),
        )
        charts[request.ref] = _render(request, data)
    names = {
        Metric.HRV_SDNN_MS: "hrv-sdnn",
        Metric.HRV_RMSSD_MS: "hrv-rmssd",
        Metric.RESTING_HR_BPM: "resting-hr",
    }
    for signal in view.signals:
        name, svg = _signal_chart(names[signal.metric], signal)
        charts[name] = svg
    if view.sleep is not None:
        name, svg = _signal_chart("sleep", view.sleep.total, sleep=True)
        charts[name] = svg
    if view.other is not None:
        panels = []
        for panel in view.other.panels:
            info = METRICS[panel.metric]
            unit = unit_named(info.unit) if info.unit is not None else None
            label = info.label + (f" ({unit.symbol})" if unit is not None else "")
            panels.append((panel, f"{label} · {panel.source}"))
        request = ChartRequest(
            "other",
            "small-multiples",
            "Other signals",
            {"x": "day", "y": "value", "facet": "panel"},
            {"y_axes": "independent"},
        )
        data = ChartData(
            (
                Column("day", ValueKind.DATE),
                Column("value", ValueKind.NUMBER),
                Column("panel", ValueKind.CATEGORY),
            ),
            tuple(
                (day, panel.values[i], label)
                for i, day in enumerate(view.window.days())
                for panel, label in panels
            ),
        )
        charts["other"] = _render(request, data)
    return tuple((name, charts[name]) for name in CHART_NAMES if name in charts)
