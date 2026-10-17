"""Pure morning-of row and figure behavior on synthetic wellness series."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from typing import cast

import pytest

from fitdocs.morning import block as block_module
from fitdocs.morning.block import (
    MorningBlock,
    MorningInputs,
    RowSource,
    SignalRow,
    SleepRow,
    Windows,
)
from fitdocs.recovery import METHODS, BaselineDay, Baselines, RangePosition
from fitdocs.recovery import baselines as baselines_module
from fitdocs.render.attribution import WellnessAttribution
from fitdocs.render.charts.kit import Column, Value, ValueKind
from fitdocs.render.charts.kit.format import format_value
from fitdocs.wellness import METRICS, Metric, SeriesValue, WellnessSeries
from tests.morning.builders import series_value, wellness_series

D = date(2024, 6, 15)
SIGNALS = (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS, Metric.RESTING_HR_BPM)
SLEEP = (
    Metric.SLEEP_S,
    Metric.SLEEP_DEEP_S,
    Metric.SLEEP_LIGHT_S,
    Metric.SLEEP_REM_S,
    Metric.SLEEP_AWAKE_S,
    Metric.SLEEP_HR_BPM,
)


def expected_block(
    day: date,
    windows: Windows,
    signals: tuple[SignalRow, ...],
    sleep: tuple[SleepRow, ...],
) -> MorningBlock:
    return MorningBlock(day, windows, signals, sleep, WellnessAttribution.NONE)


def observation(
    offset: int,
    value: float,
    metric: Metric,
    source: str = "watch-a",
    *,
    canonical: bool = True,
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        value,
        metric=metric,
        source=source,
        canonical=canonical,
    )


def fmt(metric: Metric, value: float | None, *, unit: bool = True) -> str | None:
    if value is None:
        return None
    info = METRICS[metric]
    return format_value(
        value,
        Column(metric.value, ValueKind.NUMBER, info.unit, info.label),
        with_unit=unit,
    )


def signal_row(bd: BaselineDay) -> SignalRow:
    normal_range = (
        f"{fmt(bd.metric, bd.range_low, unit=False)} to {fmt(bd.metric, bd.range_high)}"
        if bd.range_low is not None and bd.range_high is not None
        else None
    )
    return SignalRow(
        bd.metric,
        fmt(bd.metric, bd.value),
        fmt(bd.metric, bd.rolling_mean),
        normal_range,
        bd.position,
        RowSource(bd.source, (), True),
    )


def sleep_row(bd: BaselineDay) -> SleepRow:
    return SleepRow(
        bd.metric,
        fmt(bd.metric, bd.value),
        fmt(bd.metric, bd.rolling_mean),
        fmt(bd.metric, bd.baseline_mean),
        RowSource(bd.source, (), True),
    )


def signal_series() -> WellnessSeries:
    return wellness_series(
        observation(
            offset,
            base * (1 if offset % 2 else 4),
            metric,
            source,
            canonical=source == preferred,
        )
        for metric, preferred, bases in (
            (Metric.HRV_SDNN_MS, "watch-a", (11.0, 37.0)),
            (Metric.HRV_RMSSD_MS, "watch-b", (23.0, 59.0)),
            (Metric.RESTING_HR_BPM, "watch-a", (48.0, 56.0)),
        )
        for source, base in zip(("watch-a", "watch-b"), bases, strict=True)
        for offset in range(-60, 1)
    )


def test_signal_figures_match_shared_baselines_in_fixed_order() -> None:
    series = signal_series()
    baselines = Baselines.of(series)
    expected = tuple(
        signal_row(cast(BaselineDay, baselines.shown(metric, D))) for metric in SIGNALS
    )
    assert MorningInputs.of(series).block(D) == expected_block(
        D, Windows(7, 60), expected, ()
    )


@pytest.mark.parametrize(
    ("recent", "position"),
    (
        (30.0, RangePosition.BELOW),
        (60.0, RangePosition.WITHIN),
        (90.0, RangePosition.ABOVE),
    ),
    ids=("below", "within", "above"),
)
def test_signal_range_position_is_passed_through(
    recent: float, position: RangePosition
) -> None:
    series = wellness_series(
        observation(offset, recent if offset >= -6 else 60.0, Metric.RESTING_HR_BPM)
        for offset in range(-60, 1)
    )
    bd = Baselines.of(series).on(Metric.RESTING_HR_BPM, "watch-a", D)
    assert MorningInputs.of(series).block(D) == expected_block(
        D, Windows(7, 60), (replace(signal_row(bd), position=position),), ()
    )


def test_signal_figures_use_shared_baselines_without_canonical_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = signal_series()
    canonical = WellnessSeries.canonical
    calls: list[tuple[Metric, date]] = []

    def recording_canonical(
        self: WellnessSeries, metric: Metric, day: date
    ) -> SeriesValue | None:
        calls.append((metric, day))
        return canonical(self, metric, day)

    monkeypatch.setattr(WellnessSeries, "canonical", recording_canonical)
    MorningInputs.of(series).block(D)
    assert calls == []


def test_baselines_are_constructed_once_across_repeated_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = signal_series()
    original = cast(
        Callable[[type[Baselines], WellnessSeries], Baselines],
        Baselines.__dict__["of"].__func__,
    )
    calls: list[WellnessSeries] = []

    def recording_of(cls: type[Baselines], value: WellnessSeries) -> Baselines:
        calls.append(value)
        return original(cls, value)

    monkeypatch.setattr(Baselines, "of", classmethod(recording_of))
    inputs = MorningInputs.of(series)
    inputs.block(D)
    inputs.block(D)
    inputs.block(D + timedelta(days=1))
    other = wellness_series((observation(0, 61.0, Metric.RESTING_HR_BPM),))
    MorningInputs.of(other).block(D)
    assert calls == [series, other]


def test_only_present_figures_reach_the_shared_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = format_value
    calls: list[Value] = []

    def recording_format(value: Value, column: Column, *, with_unit: bool) -> str:
        calls.append(value)
        return original(value, column, with_unit=with_unit)

    monkeypatch.setattr(block_module, "format_value", recording_format)
    series = wellness_series(
        (
            observation(0, 60.0, Metric.RESTING_HR_BPM),
            observation(0, 27061.0, Metric.SLEEP_S),
            observation(0, 0.0, Metric.SLEEP_DEEP_S),
        )
    )
    MorningInputs.of(series).block(D)
    assert calls == [60.0, 27061.0, 0.0]


@pytest.mark.parametrize("mode", ("day", "rolling", "baseline"))
@pytest.mark.parametrize("metric", (Metric.RESTING_HR_BPM, Metric.SLEEP_S))
def test_each_available_figure_can_keep_a_row(metric: Metric, mode: str) -> None:
    base = 60.0 if metric == Metric.RESTING_HR_BPM else 27061.0
    offsets = {
        "day": (0,),
        "rolling": (-4, -3, -2),
        "baseline": (-2, *range(-40, -10)),
    }[mode]
    series = wellness_series(observation(i, base, metric) for i in offsets)
    bd = Baselines.of(series).on(metric, "watch-a", D)
    expected = (
        expected_block(D, Windows(7, 60), (signal_row(bd),), ())
        if metric == Metric.RESTING_HR_BPM
        else expected_block(D, Windows(7, 60), (), (sleep_row(bd),))
    )
    assert MorningInputs.of(series).block(D) == expected


@pytest.mark.parametrize("metric", (Metric.RESTING_HR_BPM, Metric.SLEEP_S))
@pytest.mark.parametrize("missing", ("rolling", "baseline"))
def test_window_minimums_leave_only_the_insufficient_figure_absent(
    metric: Metric, missing: str
) -> None:
    offsets = (
        (0, -2, *range(-60, -20)) if missing == "rolling" else tuple(range(-29, 1))
    )
    base = 60.0 if metric == Metric.RESTING_HR_BPM else 27061.0
    series = wellness_series(observation(i, base, metric) for i in offsets)
    if metric == Metric.RESTING_HR_BPM:
        row = SignalRow(
            metric,
            "60 bpm",
            None if missing == "rolling" else "60 bpm",
            "60 to 60 bpm" if missing == "rolling" else None,
            None,
            RowSource("watch-a", (), True),
        )
        expected = expected_block(D, Windows(7, 60), (row,), ())
    else:
        expected = expected_block(
            D,
            Windows(7, 60),
            (),
            (
                SleepRow(
                    metric,
                    "7:31:01",
                    None if missing == "rolling" else "7:31:01",
                    "7:31:01" if missing == "rolling" else None,
                    RowSource("watch-a", (), True),
                ),
            ),
        )
    assert MorningInputs.of(series).block(D) == expected


def sleep_series() -> WellnessSeries:
    return wellness_series(
        observation(
            offset,
            value + offset,
            metric,
            source,
            canonical=source == ("watch-a" if metric == Metric.SLEEP_S else "watch-b"),
        )
        for source, values in (
            ("watch-a", (27061.0, 3601.0, 12602.0, 5403.0, 304.0, 110.0)),
            ("watch-b", (30000.0, 7201.0, 18002.0, 9003.0, 604.0, 180.0)),
        )
        for metric, value in zip(SLEEP, values, strict=True)
        for offset in range(-60, 1)
    )


def test_sleep_figures_and_stage_order_use_total_sleep_source() -> None:
    series = sleep_series()
    baselines = Baselines.of(series)
    expected = tuple(sleep_row(baselines.on(metric, "watch-a", D)) for metric in SLEEP)
    assert MorningInputs.of(series).block(D) == expected_block(
        D, Windows(7, 60), (), expected
    )


def test_total_sleep_without_present_same_source_stages_has_only_total() -> None:
    series = wellness_series(
        (
            observation(0, 27061.0, Metric.SLEEP_S),
            *(observation(i, 3601.0, Metric.SLEEP_DEEP_S) for i in (-3, -2, -1)),
            observation(0, 7201.0, Metric.SLEEP_DEEP_S, "watch-b"),
        )
    )
    assert MorningInputs.of(series).block(D) == expected_block(
        D,
        Windows(7, 60),
        (),
        (
            SleepRow(
                Metric.SLEEP_S, "7:31:01", None, None, RowSource("watch-a", (), True)
            ),
        ),
    )


def test_zero_duration_sleep_stage_is_present() -> None:
    series = wellness_series(
        (
            observation(0, 27061.0, Metric.SLEEP_S),
            observation(0, 0.0, Metric.SLEEP_DEEP_S),
        )
    )
    assert MorningInputs.of(series).block(D) == expected_block(
        D,
        Windows(7, 60),
        (),
        (
            SleepRow(
                Metric.SLEEP_S, "7:31:01", None, None, RowSource("watch-a", (), True)
            ),
            SleepRow(
                Metric.SLEEP_DEEP_S, "0:00", None, None, RowSource("watch-a", (), True)
            ),
        ),
    )


def test_windows_follow_coherent_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        block_module,
        "METHODS",
        {
            metric: replace(method, rolling_days=5, baseline_days=40)
            for metric, method in METHODS.items()
        },
    )
    series = wellness_series((observation(0, 61.0, Metric.RESTING_HR_BPM),))
    assert MorningInputs.of(series).block(D) == expected_block(
        D,
        Windows(5, 40),
        (
            SignalRow(
                Metric.RESTING_HR_BPM,
                "61 bpm",
                None,
                None,
                None,
                RowSource("watch-a", (), True),
            ),
        ),
        (),
    )


@pytest.mark.parametrize("metric", (*SIGNALS, *SLEEP))
@pytest.mark.parametrize("window", ("rolling", "baseline"))
def test_mismatched_method_windows_are_rejected(
    monkeypatch: pytest.MonkeyPatch, metric: Metric, window: str
) -> None:
    monkeypatch.setattr(
        block_module,
        "METHODS",
        {
            m: replace(method, rolling_days=5)
            if m == metric and window == "rolling"
            else replace(method, baseline_days=40)
            if m == metric
            else method
            for m, method in METHODS.items()
        },
    )
    with pytest.raises(ValueError):
        MorningInputs.of(wellness_series(()))


@pytest.mark.parametrize(
    "values",
    (
        (),
        (observation(0, 1234.0, Metric.STEPS), observation(0, 71.0, Metric.WEIGHT_KG)),
        (observation(-200, 61.0, Metric.RESTING_HR_BPM),),
        (observation(-2, 61.0, Metric.RESTING_HR_BPM),),
        (observation(0, 3601.0, Metric.SLEEP_DEEP_S),),
    ),
)
def test_no_supported_figure_returns_none(values: Iterable[SeriesValue]) -> None:
    assert MorningInputs.of(wellness_series(values)).block(D) is None


def test_a_day_change_affects_x_and_x_plus_60_but_neither_neighbor() -> None:
    values = tuple(observation(i, 60.0, Metric.RESTING_HR_BPM) for i in range(-70, 71))
    before = MorningInputs.of(wellness_series(values))
    after = MorningInputs.of(
        wellness_series(
            replace(value, value=200.0) if value.day == D else value for value in values
        )
    )
    assert (
        before.block(D) != after.block(D),
        before.block(D + timedelta(days=60)) != after.block(D + timedelta(days=60)),
    ) == (True, True)
    for day in (D - timedelta(days=1), D + timedelta(days=61)):
        expected = expected_block(
            day,
            Windows(7, 60),
            (
                SignalRow(
                    Metric.RESTING_HR_BPM,
                    "60 bpm",
                    "60 bpm",
                    "60 to 60 bpm",
                    RangePosition.WITHIN,
                    RowSource("watch-a", (), True),
                ),
            ),
            (),
        )
        assert before.block(day) == after.block(day) == expected


@pytest.mark.parametrize("field", ("source", "origins", "unattributed"))
def test_row_source_is_frozen(field: str) -> None:
    source = RowSource("watch-a", ("apple",), False)
    with pytest.raises(FrozenInstanceError):
        setattr(source, field, None)


@pytest.mark.parametrize("metric", (*SIGNALS, *SLEEP))
def test_row_origins_use_the_selected_metric_and_source(metric: Metric) -> None:
    values = [
        replace(observation(i, 65.0, metric, "chosen"), origin=origin)
        for i, origin in ((-2, "zeta"), (-1, "alpha"), (0, "zeta"))
    ]
    values.extend(
        replace(observation(i, 85.0, metric, "decoy", canonical=False), origin="garmin")
        for i in (-2, -1, 0)
    )
    if metric in SLEEP[1:]:
        values.append(
            replace(observation(0, 27000.0, Metric.SLEEP_S, "chosen"), origin="apple")
        )
    series = wellness_series(values)
    bd = Baselines.of(series).on(metric, "chosen", D)
    assert (
        bd.value,
        bd.rolling_count,
        bd.rolling_mean is not None,
        bd.baseline_mean,
    ) == (
        65.0,
        3,
        True,
        None,
    )
    block = cast(MorningBlock, MorningInputs.of(series).block(D))
    rows: tuple[SignalRow | SleepRow, ...] = (*block.signals, *block.sleep)
    row = next(row for row in rows if row.metric == metric)
    assert row.source == RowSource("chosen", ("alpha", "zeta"), False)
    assert block.attribution is WellnessAttribution.NONE


@pytest.mark.parametrize(
    ("mode", "origins", "unattributed", "attribution"),
    (
        ("day", ("garmin",), False, WellnessAttribution.SOLE),
        ("historical", ("apple", "garmin"), False, WellnessAttribution.CONTRIBUTING),
        ("all", ("garmin",), False, WellnessAttribution.SOLE),
        ("unknown", ("garmin",), True, WellnessAttribution.CONTRIBUTING),
        ("other", ("apple", "zeta"), False, WellnessAttribution.NONE),
    ),
    ids=("day-only", "historical-only", "all-garmin", "unknown-origin", "no-garmin"),
)
def test_attribution_uses_all_contributing_values(
    mode: str,
    origins: tuple[str, ...],
    unattributed: bool,
    attribution: WellnessAttribution,
) -> None:
    method = METHODS[Metric.RESTING_HR_BPM]
    offsets = (0,) if mode == "day" else range(-method.baseline_days, 1)
    series = wellness_series(
        replace(
            observation(i, 65.0 + (i % 11), Metric.RESTING_HR_BPM),
            origin=(
                "apple"
                if mode == "historical" and i == 0
                else None
                if mode == "unknown" and i == -10
                else ("apple" if i == -10 else "zeta")
                if mode == "other"
                else "garmin"
            ),
        )
        for i in offsets
    )
    bd = Baselines.of(series).on(Metric.RESTING_HR_BPM, "watch-a", D)
    assert (
        bd.value is not None,
        bd.rolling_mean is not None,
        bd.baseline_mean is not None,
    ) == (True, mode != "day", mode != "day")
    block = cast(MorningBlock, MorningInputs.of(series).block(D))
    assert block.signals[0].source == RowSource("watch-a", origins, unattributed)
    assert block.attribution is attribution


def test_absent_baseline_excludes_its_historical_origins() -> None:
    method = METHODS[Metric.RESTING_HR_BPM]
    series = wellness_series(
        replace(
            observation(i, 65.0, Metric.RESTING_HR_BPM),
            origin="garmin" if i == -method.baseline_days else "apple",
        )
        for i in (-method.baseline_days, -2, -1, 0)
    )
    bd = Baselines.of(series).on(Metric.RESTING_HR_BPM, "watch-a", D)
    assert (
        bd.value,
        bd.rolling_count,
        bd.rolling_mean,
        bd.baseline_count,
        bd.baseline_mean,
    ) == (65.0, 3, 65.0, 3, None)
    block = cast(MorningBlock, MorningInputs.of(series).block(D))
    assert block.signals[0].source == RowSource("watch-a", ("apple",), False)
    assert block.attribution is WellnessAttribution.NONE


@pytest.mark.parametrize("nondefault", (False, True), ids=("default", "configured"))
@pytest.mark.parametrize("window", ("baseline", "rolling"))
def test_origin_window_boundaries(
    monkeypatch: pytest.MonkeyPatch, window: str, nondefault: bool
) -> None:
    methods = {
        metric: replace(method, rolling_days=5, baseline_days=40)
        if nondefault
        else method
        for metric, method in METHODS.items()
    }
    monkeypatch.setattr(block_module, "METHODS", methods)
    monkeypatch.setattr(baselines_module, "METHODS", methods)
    method = methods[Metric.RESTING_HR_BPM]
    lower = (
        -method.baseline_days if window == "baseline" else -(method.rolling_days - 1)
    )
    series = wellness_series(
        replace(
            observation(i, 65.0 + (i % 13), Metric.RESTING_HR_BPM),
            origin="garmin"
            if i in (lower - 1, 1)
            else "inside"
            if i == lower
            else "apple",
        )
        for i in range(lower - 1, 2)
    )
    bd = Baselines.of(series).on(Metric.RESTING_HR_BPM, "watch-a", D)
    assert (
        bd.value is not None,
        bd.rolling_mean is not None,
        bd.baseline_mean is not None,
    ) == (True, True, window == "baseline")
    block = cast(MorningBlock, MorningInputs.of(series).block(D))
    assert block.signals[0].source == RowSource("watch-a", ("apple", "inside"), False)
    assert block.attribution is WellnessAttribution.NONE


def test_origin_maps_are_cached_once_per_metric_source_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alternate = [
        (Metric.HRV_SDNN_MS, "watch-b"),
        (Metric.HRV_RMSSD_MS, "watch-a"),
        (Metric.RESTING_HR_BPM, "watch-b"),
        *((metric, "watch-b") for metric in SLEEP),
    ]
    series = wellness_series(
        (
            *signal_series().values,
            *sleep_series().values,
            *(
                observation(1, 65.0 + i, metric, source)
                for i, (metric, source) in enumerate(alternate)
            ),
        )
    )
    original = WellnessSeries.by_source
    calls: list[tuple[Metric, str]] = []

    def recording_by_source(
        self: WellnessSeries, metric: Metric, source: str
    ) -> tuple[SeriesValue, ...]:
        calls.append((metric, source))
        return original(self, metric, source)

    monkeypatch.setattr(WellnessSeries, "by_source", recording_by_source)
    expected = [
        (Metric.HRV_SDNN_MS, "watch-a"),
        (Metric.HRV_RMSSD_MS, "watch-b"),
        (Metric.RESTING_HR_BPM, "watch-a"),
        *((metric, "watch-a") for metric in SLEEP),
    ]
    inputs = MorningInputs.of(series)
    inputs.block(D)
    assert Counter(calls) == Counter(expected)
    inputs.block(D)
    inputs.block(D + timedelta(days=1))
    inputs.block(D + timedelta(days=1))
    assert Counter(calls) == Counter([*expected, *alternate])
    MorningInputs.of(series).block(D)
    assert Counter(calls) == Counter([*expected, *alternate, *expected])


@pytest.mark.parametrize("metric", (*SIGNALS, *SLEEP))
def test_each_row_can_supply_the_block_attribution(metric: Metric) -> None:
    values = [replace(observation(0, 65.0, metric), origin="garmin")]
    if metric in SLEEP[1:]:
        values.append(replace(observation(0, 27000.0, Metric.SLEEP_S), origin="apple"))
    series = wellness_series(values)
    bd = Baselines.of(series).on(metric, "watch-a", D)
    assert (bd.value, bd.rolling_mean, bd.baseline_mean) == (65.0, None, None)
    block = cast(MorningBlock, MorningInputs.of(series).block(D))
    assert block.attribution is (
        WellnessAttribution.CONTRIBUTING
        if metric in SLEEP[1:]
        else WellnessAttribution.SOLE
    )
