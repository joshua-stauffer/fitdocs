"""Pure morning-of rows from recovery's shared baselines."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final

from fitdocs.recovery import (
    BASELINED_METRICS,
    METHODS,
    SLEEP_METRICS,
    BaselineDay,
    Baselines,
    RangePosition,
)
from fitdocs.render.attribution import (
    WellnessAttribution,
    wellness_attribution,
    wellness_attribution_line,
)
from fitdocs.render.charts.kit import Column, ValueKind
from fitdocs.render.charts.kit.format import escape_markdown, format_value
from fitdocs.render.format import ABSENT
from fitdocs.wellness import METRICS, Metric, WellnessSeries

MORNING_BLOCK_VERSION: Final[int] = 1
MORNING_HEADING: Final[str] = "Morning Of"
STAMP_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^<!-- fitdocs-morning:v([1-9][0-9]*) ([0-9a-f]{64}) -->$"
)


@dataclass(frozen=True)
class Windows:
    rolling_days: int
    baseline_days: int


@dataclass(frozen=True)
class RowSource:
    source: str
    origins: tuple[str, ...]
    unattributed: bool


@dataclass(frozen=True)
class SignalRow:
    metric: Metric
    day_value: str | None
    rolling_mean: str | None
    normal_range: str | None
    position: RangePosition | None
    source: RowSource


@dataclass(frozen=True)
class SleepRow:
    metric: Metric
    night_value: str | None
    rolling_mean: str | None
    baseline_mean: str | None
    source: RowSource


@dataclass(frozen=True)
class MorningBlock:
    day: date
    windows: Windows
    signals: tuple[SignalRow, ...]
    sleep: tuple[SleepRow, ...]
    attribution: WellnessAttribution

    def facts(self) -> str:
        obj = {
            "day": self.day.isoformat(),
            "windows": [self.windows.rolling_days, self.windows.baseline_days],
            "signals": [
                [
                    row.metric.value,
                    row.source.source,
                    row.source.origins,
                    row.day_value,
                    row.rolling_mean,
                    row.normal_range,
                    row.position.value if row.position is not None else None,
                ]
                for row in self.signals
            ],
            "sleep": [
                [
                    row.metric.value,
                    row.source.source,
                    row.source.origins,
                    row.night_value,
                    row.rolling_mean,
                    row.baseline_mean,
                ]
                for row in self.sleep
            ],
            "attribution": self.attribution.value,
        }
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.facts().encode("utf-8")).hexdigest()


def render_region(block: MorningBlock | None) -> str:
    if block is None:
        return ""
    day = block.day
    rolling = block.windows.rolling_days
    baseline = block.windows.baseline_days
    parts = [
        f"<!-- fitdocs-morning:v{MORNING_BLOCK_VERSION} {block.fingerprint()} -->",
        f"## {MORNING_HEADING}",
    ]
    attribution = wellness_attribution_line(block.attribution)
    if attribution is not None:
        parts.append(attribution)
    parts.append(
        f"Wellness for {day.isoformat()}, the day of this workout, against the "
        f"athlete's own baseline for each source: {rolling}-day means cover "
        f"{(day - timedelta(days=rolling - 1)).isoformat()} to {day.isoformat()}, "
        f"and normal ranges and {baseline}-day means cover "
        f"{(day - timedelta(days=baseline)).isoformat()} to "
        f"{(day - timedelta(days=1)).isoformat()}."
    )
    if block.signals:
        lines = [
            f"| Signal | {day.isoformat()} | {rolling}-day mean | Normal range | "
            f"{rolling}-day mean vs range | Source |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for signal in block.signals:
            position = signal.position.value if signal.position is not None else None
            lines.append(
                f"| {escape_markdown(METRICS[signal.metric].label)} | "
                f"{_cell(signal.day_value)} | {_cell(signal.rolling_mean)} | "
                f"{_cell(signal.normal_range)} | "
                f"{_cell(position)} | "
                f"{_source_cell(signal.source)} |"
            )
        parts.append("\n".join(lines))
    if block.sleep:
        lines = [
            f"| Signal | Night ending {day.isoformat()} | {rolling}-day mean | "
            f"{baseline}-day mean | Source |",
            "| --- | --- | --- | --- | --- |",
        ]
        for sleep in block.sleep:
            lines.append(
                f"| {escape_markdown(METRICS[sleep.metric].label)} | "
                f"{_cell(sleep.night_value)} | {_cell(sleep.rolling_mean)} | "
                f"{_cell(sleep.baseline_mean)} | {_source_cell(sleep.source)} |"
            )
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def parse_stamp(content: str) -> tuple[int, str] | None:
    first_line = content.partition("\n")[0]
    match = STAMP_PATTERN.fullmatch(first_line)
    if match is None:
        return None
    return int(match.group(1)), match.group(2)


def _cell(value: str | None) -> str:
    return ABSENT if value is None else value


def _source_cell(source: RowSource) -> str:
    cell = escape_markdown(source.source)
    if source.origins:
        cell += " (" + ", ".join(escape_markdown(o) for o in source.origins) + ")"
    return cell


@dataclass
class MorningInputs:
    series: WellnessSeries
    baselines: Baselines
    windows: Windows
    _origins: dict[tuple[Metric, str], dict[date, str | None]] = field(
        default_factory=dict, init=False, repr=False
    )

    @classmethod
    def of(cls, series: WellnessSeries) -> MorningInputs:
        pairs = {
            (METHODS[metric].rolling_days, METHODS[metric].baseline_days)
            for metric in BASELINED_METRICS + SLEEP_METRICS
        }
        if len(pairs) != 1:
            raise ValueError(
                "morning-of methods must share rolling and baseline windows"
            )
        rolling_days, baseline_days = pairs.pop()
        return cls(series, Baselines.of(series), Windows(rolling_days, baseline_days))

    def block(self, day: date) -> MorningBlock | None:
        signals: list[SignalRow] = []
        for metric in BASELINED_METRICS:
            bd = self.baselines.shown(metric, day)
            if bd is None or not _has_figure(bd):
                continue
            normal_range = (
                f"{_fmt(metric, bd.range_low, with_unit=False)} to "
                f"{_fmt(metric, bd.range_high)}"
                if bd.range_low is not None and bd.range_high is not None
                else None
            )
            signals.append(
                SignalRow(
                    metric,
                    _fmt(metric, bd.value),
                    _fmt(metric, bd.rolling_mean),
                    normal_range,
                    bd.position,
                    self._row_source(bd),
                )
            )

        sleep: list[SleepRow] = []
        bd = self.baselines.shown(Metric.SLEEP_S, day)
        if bd is not None and _has_figure(bd):
            sleep.append(_sleep_row(bd, self._row_source(bd)))
            for metric in SLEEP_METRICS[1:]:
                stage = self.baselines.on(metric, bd.source, day)
                if stage.value is not None:
                    sleep.append(_sleep_row(stage, self._row_source(stage)))

        if not signals and not sleep:
            return None
        rows: tuple[SignalRow | SleepRow, ...] = (*signals, *sleep)
        sources = [row.source for row in rows]
        origins: set[str | None] = {
            origin for source in sources for origin in source.origins
        }
        if any(source.unattributed for source in sources):
            origins.add(None)
        return MorningBlock(
            day,
            self.windows,
            tuple(signals),
            tuple(sleep),
            wellness_attribution(origins),
        )

    def _row_source(self, bd: BaselineDay) -> RowSource:
        key = (bd.metric, bd.source)
        if key not in self._origins:
            self._origins[key] = {
                value.day: value.origin
                for value in self.series.by_source(bd.metric, bd.source)
            }
        by_day = self._origins[key]
        days: set[date] = set()
        if bd.value is not None:
            days.add(bd.day)
        if bd.rolling_mean is not None:
            days.update(
                bd.day - timedelta(days=offset)
                for offset in range(self.windows.rolling_days)
            )
        if bd.baseline_mean is not None:
            days.update(
                bd.day - timedelta(days=offset)
                for offset in range(1, self.windows.baseline_days + 1)
            )
        origins = [by_day[day] for day in sorted(days) if day in by_day]
        return RowSource(
            bd.source,
            tuple(sorted({origin for origin in origins if origin is not None})),
            None in origins,
        )


def _has_figure(bd: BaselineDay) -> bool:
    return any(v is not None for v in (bd.value, bd.rolling_mean, bd.baseline_mean))


def _fmt(metric: Metric, value: float | None, *, with_unit: bool = True) -> str | None:
    if value is None:
        return None
    info = METRICS[metric]
    return format_value(
        value,
        Column(metric.value, ValueKind.NUMBER, info.unit, info.label),
        with_unit=with_unit,
    )


def _sleep_row(bd: BaselineDay, source: RowSource) -> SleepRow:
    return SleepRow(
        bd.metric,
        _fmt(bd.metric, bd.value),
        _fmt(bd.metric, bd.rolling_mean),
        _fmt(bd.metric, bd.baseline_mean),
        source,
    )
