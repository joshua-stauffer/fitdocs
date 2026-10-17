"""Pure morning-of rows from recovery's shared baselines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fitdocs.recovery import (
    BASELINED_METRICS,
    METHODS,
    SLEEP_METRICS,
    BaselineDay,
    Baselines,
    RangePosition,
)
from fitdocs.render.charts.kit import Column, ValueKind
from fitdocs.render.charts.kit.format import format_value
from fitdocs.wellness import METRICS, Metric, WellnessSeries


@dataclass(frozen=True)
class Windows:
    rolling_days: int
    baseline_days: int


@dataclass(frozen=True)
class SignalRow:
    metric: Metric
    day_value: str | None
    rolling_mean: str | None
    normal_range: str | None
    position: RangePosition | None
    source: str


@dataclass(frozen=True)
class SleepRow:
    metric: Metric
    night_value: str | None
    rolling_mean: str | None
    baseline_mean: str | None
    source: str


@dataclass(frozen=True)
class MorningBlock:
    day: date
    windows: Windows
    signals: tuple[SignalRow, ...]
    sleep: tuple[SleepRow, ...]


@dataclass
class MorningInputs:
    series: WellnessSeries
    baselines: Baselines
    windows: Windows

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
                    bd.source,
                )
            )

        sleep: list[SleepRow] = []
        bd = self.baselines.shown(Metric.SLEEP_S, day)
        if bd is not None and _has_figure(bd):
            sleep.append(_sleep_row(bd))
            for metric in SLEEP_METRICS[1:]:
                stage = self.baselines.on(metric, bd.source, day)
                if stage.value is not None:
                    sleep.append(_sleep_row(stage))

        if not signals and not sleep:
            return None
        return MorningBlock(day, self.windows, tuple(signals), tuple(sleep))


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


def _sleep_row(bd: BaselineDay) -> SleepRow:
    return SleepRow(
        bd.metric,
        _fmt(bd.metric, bd.value),
        _fmt(bd.metric, bd.rolling_mean),
        _fmt(bd.metric, bd.baseline_mean),
        bd.source,
    )
