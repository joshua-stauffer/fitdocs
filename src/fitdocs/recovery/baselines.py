"""Per-source rolling means and personal baseline ranges."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from fitdocs.recovery.constants import METHODS, Transform
from fitdocs.wellness import Metric, WellnessSeries


class RangePosition(StrEnum):
    """The rolling mean's position in its baseline range."""

    BELOW = "below"
    WITHIN = "within"
    ABOVE = "above"


@dataclass(frozen=True)
class BaselineDay:
    """One source's observation and statistics on a wellness day."""

    metric: Metric
    source: str
    day: date
    value: float | None
    origin: str | None
    rolling_mean: float | None
    rolling_count: int
    baseline_mean: float | None
    baseline_sd: float | None
    baseline_count: int
    range_low: float | None
    range_high: float | None
    position: RangePosition | None


@dataclass(frozen=True)
class Baselines:
    """Date-indexed inputs shared by recovery consumers."""

    _values: dict[tuple[Metric, str], dict[date, tuple[float, str | None]]]
    _canonical: dict[tuple[Metric, date], str]

    @classmethod
    def of(cls, series: WellnessSeries) -> Baselines:
        values: dict[tuple[Metric, str], dict[date, tuple[float, str | None]]] = {}
        canonical: dict[tuple[Metric, date], str] = {}
        for item in series.values:
            if item.metric not in METHODS:
                continue
            values.setdefault((item.metric, item.source), {})[item.day] = (
                item.value,
                item.origin,
            )
            if item.canonical:
                canonical[(item.metric, item.day)] = item.source
        return cls(values, canonical)

    def on(self, metric: Metric, source: str, day: date) -> BaselineDay:
        if metric not in METHODS:
            raise ValueError(f"unsupported baseline metric: {metric}")
        method = METHODS[metric]
        transform = math.log if method.transform == Transform.LOG else float
        inverse = math.exp if method.transform == Transform.LOG else float
        values = self._values.get((metric, source), {})
        daily = values.get(day)
        xs = [
            transform(present[0])
            for offset in range(method.rolling_days - 1, -1, -1)
            if (present := values.get(day - timedelta(days=offset))) is not None
        ]
        ys = [
            transform(present[0])
            for offset in range(method.baseline_days, 0, -1)
            if (present := values.get(day - timedelta(days=offset))) is not None
        ]
        rolling = math.fsum(xs) / len(xs) if len(xs) >= method.min_rolling else None
        mu = sd = None
        if len(ys) >= method.min_baseline:
            mu = math.fsum(ys) / len(ys)
            sd = math.sqrt(math.fsum((y - mu) ** 2 for y in ys) / (len(ys) - 1))
        low = high = None
        position = None
        if mu is not None and sd is not None and method.range_multiple is not None:
            low = mu - method.range_multiple * sd
            high = mu + method.range_multiple * sd
            if rolling is not None:
                if rolling < low:
                    position = RangePosition.BELOW
                elif rolling > high:
                    position = RangePosition.ABOVE
                else:
                    position = RangePosition.WITHIN
        return BaselineDay(
            metric=metric,
            source=source,
            day=day,
            value=daily[0] if daily is not None else None,
            origin=daily[1] if daily is not None else None,
            rolling_mean=inverse(rolling) if rolling is not None else None,
            rolling_count=len(xs),
            baseline_mean=inverse(mu) if mu is not None else None,
            baseline_sd=sd,
            baseline_count=len(ys),
            range_low=inverse(low) if low is not None else None,
            range_high=inverse(high) if high is not None else None,
            position=position,
        )

    def shown_source(self, metric: Metric, day: date) -> str | None:
        for offset in range(METHODS[metric].rolling_days):
            source = self._canonical.get((metric, day - timedelta(days=offset)))
            if source is not None:
                return source
        return None

    def shown(self, metric: Metric, day: date) -> BaselineDay | None:
        source = self.shown_source(metric, day)
        return self.on(metric, source, day) if source is not None else None
