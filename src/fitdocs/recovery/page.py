"""Pure recovery frontmatter and signal, sleep, other-signal and load sections."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from fitdocs import contract, layout
from fitdocs.recovery.baselines import BaselineDay
from fitdocs.recovery.constants import BASELINES_VERSION, METHODS
from fitdocs.recovery.view import RecoveryView, SignalView
from fitdocs.render.attribution import wellness_attribution, wellness_attribution_line
from fitdocs.render.charts.kit import Column, ValueKind
from fitdocs.render.charts.kit.format import escape_markdown, format_value
from fitdocs.wellness import METRICS, Metric

RECOVERY_TYPE: Final = "recovery"
RECOVERY_TITLE: Final = "Recovery"
RECOVERY_VERSION: Final = 1
RECOVERY_FRONTMATTER_KEYS: Final = (
    "title",
    "type",
    "generator",
    "recovery_version",
    "baselines_version",
    "as_of",
    "window_start",
    "window_end",
    "methodology",
)


@dataclass(frozen=True)
class RenderedRecovery:
    markdown: str
    charts: tuple[tuple[str, str], ...]


def _count(value: int) -> str:
    return format_value(value, Column("value", ValueKind.NUMBER), with_unit=True)


def _day(value: date) -> str:
    return format_value(value, Column("day", ValueKind.DATE), with_unit=True)


def _value(value: float | None, metric: Metric, role: str = "value") -> str:
    info = METRICS[metric]
    label = {
        "value": info.label,
        "mean": "7-day mean",
        "low": "normal range low",
        "high": "normal range high",
    }[role]
    return format_value(
        value, Column(role, ValueKind.NUMBER, info.unit, label), with_unit=True
    )


def _chart(name: str, label: str) -> str:
    return f"![{escape_markdown(label)} chart]({layout.recovery_asset_rel_path(name)})"


def _mean(bd: BaselineDay) -> str:
    method = METHODS[bd.metric]
    if bd.rolling_mean is not None:
        return f"7-day mean: {_value(bd.rolling_mean, bd.metric, 'mean')}."
    return (
        f"7-day mean: not shown — {_count(bd.rolling_count)} of the "
        f"{_count(method.rolling_days)} days hold a value; "
        f"at least {_count(method.min_rolling)} are needed."
    )


def _range(bd: BaselineDay) -> str:
    method = METHODS[bd.metric]
    if bd.range_low is not None and bd.range_high is not None:
        return (
            f"Normal range: {_value(bd.range_low, bd.metric, 'low')} to "
            f"{_value(bd.range_high, bd.metric, 'high')}, from "
            f"{_count(bd.baseline_count)} "
            f"of the {_count(method.baseline_days)} days before."
        )
    return (
        f"Normal range: not shown — {_count(bd.baseline_count)} of the "
        f"{_count(method.baseline_days)} days hold a value; "
        f"at least {_count(method.min_baseline)} are needed."
    )


def _signal(signal: SignalView, name: str) -> list[str]:
    label = escape_markdown(METRICS[signal.metric].label)
    lines = ["", f"## {label}", "", _chart(name, METRICS[signal.metric].label), ""]
    latest = signal.latest
    if latest is not None and latest.baseline is not None:
        bd = latest.baseline
        lines.extend(
            (
                f"Latest: {_day(latest.day)}, {_value(bd.value, signal.metric)} "
                f"({escape_markdown(bd.source)}).",
                "",
                _mean(bd),
                "",
                _range(bd),
                "",
            )
        )
    if signal.runs:
        for run in signal.runs:
            when = _day(run.first)
            if run.last != run.first:
                when += f" to {_day(run.last)}"
            lines.append(
                f"- {when}: {run.position.value} ({escape_markdown(run.source)})"
            )
    else:
        lines.append("No day of the window has a 7-day mean outside the normal range.")
    for change in signal.changes:
        before = escape_markdown(change.before)
        after = escape_markdown(change.after)
        lines.extend(
            (
                "",
                f"On {_day(change.day)} the shown source changed from "
                f"{before} to {after}; "
                f"from that day the 7-day mean and normal range are {after}'s own.",
            )
        )
    for note in signal.sources:
        origins = (
            ", ".join(escape_markdown(origin) for origin in note.origins)
            or "not recorded"
        )
        lines.extend(
            (
                "",
                f"Sources shown: {escape_markdown(note.source)} (origins {origins}) "
                f"on {_count(note.days_shown)} days.",
            )
        )
    return lines


def render_page(
    view: RecoveryView, charts: Sequence[tuple[str, str]]
) -> RenderedRecovery:
    window = view.window
    lines = [
        contract.FRONTMATTER_FENCE,
        f"title: {json.dumps(RECOVERY_TITLE)}",
        f"type: {json.dumps(RECOVERY_TYPE)}",
        f"generator: {json.dumps(contract.GENERATOR)}",
        f"recovery_version: {_count(RECOVERY_VERSION)}",
        f"baselines_version: {_count(BASELINES_VERSION)}",
        f"as_of: {json.dumps(_day(window.as_of))}",
        f"window_start: {json.dumps(_day(window.start))}",
        f"window_end: {json.dumps(_day(window.as_of))}",
    ]
    if view.load.rows and view.load.methodology is not None:
        methodology = view.load.methodology
        if re.fullmatch(r"[A-Za-z0-9_.-]+", methodology) is None:
            methodology = json.dumps(methodology)
        lines.append(f"methodology: {methodology}")
    lines.extend(
        (contract.FRONTMATTER_FENCE, "", contract.DOC_BANNER, "", f"# {RECOVERY_TITLE}")
    )
    attribution = wellness_attribution_line(wellness_attribution(view.origins))
    if attribution is not None:
        lines.append(attribution)
    lines.extend(
        (
            "",
            f"As of {_day(window.as_of)}. Window: {_day(window.start)} "
            f"to {_day(window.as_of)}. "
            "Each signal is shown against the athlete's own baseline, "
            "computed separately "
            "for every source. This page describes the data and draws "
            "no conclusion from it.",
            "",
            "## Fitness, Fatigue and Form",
            "",
        )
    )
    if view.load.rows:
        lines.extend(
            (
                _chart("load", "Fitness, fatigue and form"),
                "",
                "Computed exactly as fitdocs history computes it, under "
                "the methodology "
                f"{escape_markdown(view.load.methodology or '')}.",
            )
        )
        if view.load.unavailable_days > 0:
            lines.extend(
                (
                    "",
                    f"{_count(view.load.unavailable_days)} days of the window "
                    f"have no fitness, "
                    "fatigue or form: they fall outside the load series or in a week "
                    "suppressed for low coverage.",
                )
            )
    else:
        lines.append(
            "No workout page records a training load, so fitness, "
            "fatigue and form are not shown."
        )
    names = {
        Metric.HRV_SDNN_MS: "hrv-sdnn",
        Metric.HRV_RMSSD_MS: "hrv-rmssd",
        Metric.RESTING_HR_BPM: "resting-hr",
    }
    for signal in view.signals:
        lines.extend(_signal(signal, names[signal.metric]))
    if view.sleep is not None:
        sleep = view.sleep
        night = _day(sleep.night) if sleep.night is not None else "—"
        lines.extend(
            (
                "",
                f"## {escape_markdown(METRICS[Metric.SLEEP_S].label)}",
                "",
                _chart("sleep", METRICS[Metric.SLEEP_S].label),
                "",
                f"| Signal | {night} | 7-day mean | 60-day mean |",
                "| --- | --- | --- | --- |",
            )
        )
        for bd in sleep.rows:
            lines.append(
                f"| {escape_markdown(METRICS[bd.metric].label)} | "
                f"{_value(bd.value, bd.metric)} "
                f"| {_value(bd.rolling_mean, bd.metric, 'mean')} | "
                f"{_value(bd.baseline_mean, bd.metric)} |"
            )
    if view.other is not None:
        lines.extend(
            (
                "",
                "## Other Signals",
                "",
                _chart("other", "Other signals"),
                "",
                "Shown as recorded, one panel per metric and source, with no baseline.",
            )
        )
        if view.other.overflow:
            pairs = ", ".join(
                f"{escape_markdown(METRICS[metric].label)} ({escape_markdown(source)})"
                for metric, source in view.other.overflow
            )
            lines.extend(
                ("", f"Also recorded in this window but not charted: {pairs}.")
            )
    return RenderedRecovery("\n".join(lines) + "\n", tuple(charts))
