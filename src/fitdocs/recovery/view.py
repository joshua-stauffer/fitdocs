"""Recovery page data assembled without rendering or I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from fitdocs.history import DayRow, HistoryComputation, day_rows
from fitdocs.recovery.baselines import BaselineDay, Baselines, RangePosition
from fitdocs.recovery.constants import BASELINED_METRICS, METHODS, SLEEP_METRICS
from fitdocs.wellness import Metric, WellnessSeries

WINDOW_DAYS: Final[int] = 90
OTHER_SIGNALS: Final[tuple[Metric, ...]] = (
    Metric.RESPIRATION_BRPM,
    Metric.SPO2_PCT,
    Metric.STRESS_LEVEL,
    Metric.BODY_BATTERY_HIGHEST,
    Metric.BODY_BATTERY_LOWEST,
    Metric.STEPS,
    Metric.WEIGHT_KG,
    Metric.VO2MAX_ML_PER_KG_MIN,
    Metric.VO2MAX_RUN_ML_PER_KG_MIN,
    Metric.VO2MAX_RIDE_ML_PER_KG_MIN,
    Metric.FATIGUE_RATING,
    Metric.SORENESS_RATING,
    Metric.MOOD_RATING,
    Metric.MOTIVATION_RATING,
    Metric.STRESS_RATING,
    Metric.INJURY_RATING,
    Metric.HYDRATION_RATING,
)


@dataclass(frozen=True)
class Window:
    as_of: date
    start: date

    def days(self) -> tuple[date, ...]:
        return tuple(self.start + timedelta(days=i) for i in range(WINDOW_DAYS))


@dataclass(frozen=True)
class ShownDay:
    day: date
    source: str | None
    baseline: BaselineDay | None


@dataclass(frozen=True)
class MarkedRun:
    first: date
    last: date
    position: RangePosition
    source: str


@dataclass(frozen=True)
class SourceChange:
    day: date
    before: str
    after: str


@dataclass(frozen=True)
class SourceNote:
    source: str
    origins: tuple[str, ...]
    days_shown: int


@dataclass(frozen=True)
class SignalView:
    metric: Metric
    days: tuple[ShownDay, ...]
    latest: ShownDay | None
    runs: tuple[MarkedRun, ...]
    changes: tuple[SourceChange, ...]
    sources: tuple[SourceNote, ...]


@dataclass(frozen=True)
class SleepView:
    total: SignalView
    night: date | None
    rows: tuple[BaselineDay, ...]


@dataclass(frozen=True)
class Panel:
    metric: Metric
    source: str
    values: tuple[float | None, ...]
    origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class OtherView:
    panels: tuple[Panel, ...]
    overflow: tuple[tuple[Metric, str], ...]


@dataclass(frozen=True)
class LoadView:
    methodology: str | None
    rows: tuple[DayRow | None, ...]
    unavailable_days: int
    note: str | None


@dataclass(frozen=True)
class CoverageRow:
    metric: Metric
    source: str
    days_with_value: int


@dataclass(frozen=True)
class RecoveryView:
    window: Window
    load: LoadView
    signals: tuple[SignalView, ...]
    sleep: SleepView | None
    other: OtherView | None
    coverage: tuple[CoverageRow, ...]
    absent: tuple[Metric, ...]
    origins: frozenset[str | None]


def _signal(metric: Metric, baselines: Baselines, days: tuple[date, ...]) -> SignalView:
    shown = tuple(
        ShownDay(day, baselines.shown_source(metric, day), baselines.shown(metric, day))
        for day in days
    )
    latest = next(
        (
            item
            for item in reversed(shown)
            if item.baseline is not None and item.baseline.value is not None
        ),
        None,
    )
    runs: list[MarkedRun] = []
    changes: list[SourceChange] = []
    previous: str | None = None
    for item in shown:
        if item.source is not None:
            # Days with no shown source do not reset the comparison
            # (recovery design Amendment 1).
            if previous is not None and previous != item.source:
                changes.append(SourceChange(item.day, previous, item.source))
            previous = item.source
        bd = item.baseline
        if bd is None or bd.position not in (RangePosition.ABOVE, RangePosition.BELOW):
            continue
        if (
            runs
            and runs[-1].last == item.day - timedelta(days=1)
            and runs[-1].position == bd.position
            and runs[-1].source == bd.source
        ):
            last = runs[-1]
            runs[-1] = MarkedRun(last.first, item.day, bd.position, bd.source)
        else:
            runs.append(MarkedRun(item.day, item.day, bd.position, bd.source))
    sources = tuple(
        SourceNote(
            source,
            tuple(
                sorted(
                    {
                        item.baseline.origin
                        for item in shown
                        if item.source == source
                        and item.baseline is not None
                        and item.baseline.value is not None
                        and item.baseline.origin is not None
                    }
                )
            ),
            sum(item.source == source for item in shown),
        )
        for source in sorted({item.source for item in shown if item.source is not None})
    )
    return SignalView(metric, shown, latest, tuple(runs), tuple(changes), sources)


def _load(computation: HistoryComputation | None, days: tuple[date, ...]) -> LoadView:
    if computation is None:
        return LoadView(None, (), len(days), "No workout page records a training load.")
    by_day = {
        row.day: row
        for row in day_rows(computation.series, computation.model, computation.weeks)
    }
    rows = tuple(by_day.get(day) for day in days)
    return LoadView(
        computation.choice.methodology,
        rows,
        sum(row is None or row.suppressed for row in rows),
        None,
    )


def build_view(
    series: WellnessSeries,
    baselines: Baselines,
    load: HistoryComputation | None,
    *,
    panel_limit: int,
) -> RecoveryView | None:
    if series.is_empty():
        return None
    as_of = series.days()[-1]
    window = Window(as_of, as_of - timedelta(days=WINDOW_DAYS - 1))
    days = window.days()
    page_metrics = (*BASELINED_METRICS, *SLEEP_METRICS, *OTHER_SIGNALS)
    values: dict[tuple[Metric, str], dict[date, tuple[float, str | None]]] = {}
    for item in series.values:
        values.setdefault((item.metric, item.source), {})[item.day] = (
            item.value,
            item.origin,
        )
    qualifying = {
        (m, s): sum(window.start <= day <= window.as_of for day in records)
        for (m, s), records in values.items()
        if m in page_metrics
    }
    qualifying = {key: count for key, count in qualifying.items() if count > 0}
    present = {metric for metric, _ in qualifying}
    signals = tuple(
        _signal(metric, baselines, days)
        for metric in BASELINED_METRICS
        if metric in present
    )
    sleep = None
    if Metric.SLEEP_S in present:
        total = _signal(Metric.SLEEP_S, baselines, days)
        latest = total.latest
        rows = (
            ()
            if latest is None or latest.source is None
            else tuple(
                bd
                for metric in SLEEP_METRICS
                if (bd := baselines.on(metric, latest.source, latest.day)).value
                is not None
            )
        )
        sleep = SleepView(total, latest.day if latest is not None else None, rows)
    pairs = tuple(
        (metric, source)
        for metric in OTHER_SIGNALS
        for source in sorted(source for m, source in qualifying if m == metric)
    )
    panels = tuple(
        Panel(
            metric,
            source,
            tuple(
                record[0]
                if (record := values[(metric, source)].get(day)) is not None
                else None
                for day in days
            ),
            tuple(
                sorted(
                    {
                        record[1]
                        for day in days
                        if (record := values[(metric, source)].get(day)) is not None
                        and record[1] is not None
                    }
                )
            ),
        )
        for metric, source in pairs[:panel_limit]
    )
    other = OtherView(panels, pairs[panel_limit:]) if pairs else None
    coverage = tuple(
        CoverageRow(metric, source, qualifying[(metric, source)])
        for metric in page_metrics
        for source in sorted(s for m, s in qualifying if m == metric)
    )
    origins: set[str | None] = set()

    def collect(bd: BaselineDay, *, baseline: bool) -> None:
        records = values.get((bd.metric, bd.source), {})
        offsets: set[int] = {0} if bd.value is not None else set()
        method = METHODS[bd.metric]
        if bd.rolling_mean is not None:
            offsets.update(range(method.rolling_days))
        if baseline and bd.baseline_mean is not None:
            offsets.update(range(1, method.baseline_days + 1))
        origins.update(
            record[1]
            for offset in offsets
            if (record := records.get(bd.day - timedelta(days=offset))) is not None
        )

    for signal in signals:
        for shown_day in signal.days:
            if shown_day.baseline is not None:
                collect(shown_day.baseline, baseline=True)
    if sleep is not None:
        for shown_day in sleep.total.days:
            if shown_day.baseline is not None:
                collect(shown_day.baseline, baseline=False)
        for bd in sleep.rows:
            collect(bd, baseline=True)
    for panel in panels:
        origins.update(
            record[1]
            for day in days
            if (record := values[(panel.metric, panel.source)].get(day)) is not None
        )
    absent = tuple(
        metric
        for metric in (*BASELINED_METRICS, Metric.SLEEP_S)
        if metric not in present
    )
    return RecoveryView(
        window,
        _load(load, days),
        signals,
        sleep,
        other,
        coverage,
        absent,
        frozenset(origins),
    )
