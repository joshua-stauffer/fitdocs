"""Best-effort windows follow recorded, channel-specific continuity."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from fitdocs.metrics import mean_max, mean_max_sources
from fitdocs.model import Samples


def _samples(
    times: Iterable[float],
    *,
    power: Iterable[int | None] | None = None,
    speed: Iterable[float | None] | None = None,
    heart_rate: Iterable[int | None] | None = None,
) -> Samples:
    time_s = tuple(times)
    count = len(time_s)
    return Samples(
        time_s=time_s,
        power_w=tuple(power) if power is not None else (None,) * count,
        speed_mps=tuple(speed) if speed is not None else (None,) * count,
        heart_rate_bpm=(
            tuple(heart_rate) if heart_rate is not None else (None,) * count
        ),
        cadence_rpm=(None,) * count,
        distance_m=(None,) * count,
        altitude_m=(None,) * count,
        latitude_deg=(None,) * count,
        longitude_deg=(None,) * count,
        temperature_c=(None,) * count,
    )


def _reference(
    times: tuple[float, ...],
    values: tuple[int | float | None, ...],
    durations: tuple[int, ...],
    max_step: float,
) -> tuple[tuple[int, float | None, float | None], ...]:
    """Enumerate every held-value window in every allowed stretch."""
    recorded = [
        (time, value)
        for time, value in zip(times, values, strict=True)
        if value is not None and math.isfinite(value)
    ]
    stretches: list[list[tuple[float, int | float]]] = []
    for pair in recorded:
        if not stretches or pair[0] - stretches[-1][-1][0] > max_step:
            stretches.append([])
        stretches[-1].append(pair)

    grids: list[tuple[float, tuple[int | float, ...]]] = []
    for stretch in stretches:
        origin = stretch[0][0]
        last = stretch[-1][0]
        grid: list[int | float] = []
        cursor = 0
        for second in range(math.floor(last - origin) + 1):
            instant = origin + second
            while cursor + 1 < len(stretch) and stretch[cursor + 1][0] <= instant:
                cursor += 1
            grid.append(stretch[cursor][1])
        grids.append((origin, tuple(grid)))

    points: list[tuple[int, float | None, float | None]] = []
    for duration in durations:
        best: float | None = None
        best_start: float | None = None
        for origin, grid_values in grids:
            for start in range(len(grid_values) - duration + 1):
                average = sum(grid_values[start : start + duration]) / duration
                if best is None or average > best:
                    best, best_start = average, origin + start
        points.append((duration, best, best_start))
    return tuple(points)


def _assert_reference(
    actual: tuple[mean_max.MeanMaxPoint, ...],
    expected: tuple[tuple[int, float | None, float | None], ...],
) -> None:
    assert tuple(point.duration_s for point in actual) == tuple(
        point[0] for point in expected
    )
    for point, (duration, value, start) in zip(actual, expected, strict=True):
        assert point.duration_s == duration
        assert (
            point.value == pytest.approx(value, rel=1e-12)
            if value is not None
            else point.value is None
        )
        assert (
            point.start_s == pytest.approx(start)
            if start is not None
            else point.start_s is None
        )


@pytest.fixture
def short_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (1, 2, 3, 4, 5, 6, 7))
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_MAX_STEP_S", 5.0)


def test_types_and_record_access_at_call_time(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tuple(channel.value for channel in mean_max.MeanMaxChannel) == (
        "power_w",
        "speed_mps",
        "heart_rate_bpm",
    )
    assert mean_max.MeanMaxPoint(1, 12.5, 3.0).value == 12.5
    point = mean_max.MeanMaxPoint(1, 12.5, 3.0)
    with pytest.raises(FrozenInstanceError):
        point.value = 14.0  # type: ignore[misc]
    samples = _samples((0, 1, 2), power=(4, 8, 12))
    assert mean_max.mean_max_durations_s() == (1, 2, 3, 4, 5, 6, 7)
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (1, 3))
    curve = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert tuple(point.duration_s for point in curve) == (1, 3)
    assert curve == (
        mean_max.MeanMaxPoint(1, 12.0, 2.0),
        mean_max.MeanMaxPoint(3, 8.0, 0.0),
    )


def test_pause_higher_than_each_within_stretch_and_step_boundary(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (4,))
    paused = _samples(
        (0, 1, 2, 3, 9, 10, 11, 12),
        power=(1, 2, 3, 100, 101, 4, 5, 6),
    )
    paused_curve = mean_max.mean_max_curve(paused, mean_max.MeanMaxChannel.POWER)
    _assert_reference(
        paused_curve,
        _reference(paused.time_s, paused.power_w, (4,), 5.0),
    )
    unbroken_pause = _reference(paused.time_s, paused.power_w, (4,), 10.0)
    assert unbroken_pause[0][1] is not None
    assert paused_curve[0].value is not None
    assert unbroken_pause[0][1] > paused_curve[0].value
    assert paused_curve[0] == mean_max.MeanMaxPoint(4, 29.0, 9.0)

    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", tuple(range(1, 13)))
    samples = _samples((0, 5, 10, 16, 21), power=(13, 17, 19, 97, 101))
    curve = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    expected = _reference(samples.time_s, samples.power_w, tuple(range(1, 13)), 5.0)
    _assert_reference(curve, expected)
    assert curve[10].value is not None
    assert curve[11] == mean_max.MeanMaxPoint(12, None, None)


def test_channel_dropout_and_zero_missing_nonfinite_values(short_records: None) -> None:
    samples = _samples(
        (0, 1, 2, 3, 4, 5, 6, 7),
        power=(31, 0, 37, 41, 43, 47, 53, 59),
        speed=(1.1, 1.7, 2.3, 3.1, 4.9, 5.3, 6.7, 7.9),
        heart_rate=(71, 73, None, None, None, None, None, 89),
    )
    speeds = samples.speed_mps[:5] + (float("nan"),) + samples.speed_mps[6:]
    samples = _samples(
        samples.time_s,
        power=samples.power_w,
        speed=speeds,
        heart_rate=samples.heart_rate_bpm,
    )
    for channel, values in (
        (mean_max.MeanMaxChannel.POWER, samples.power_w),
        (mean_max.MeanMaxChannel.SPEED, samples.speed_mps),
        (mean_max.MeanMaxChannel.HEART_RATE, samples.heart_rate_bpm),
    ):
        actual = mean_max.mean_max_curve(samples, channel)
        expected = _reference(samples.time_s, values, (1, 2, 3, 4, 5, 6, 7), 5.0)
        _assert_reference(actual, expected)
    power = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    heart_rate = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.HEART_RATE)
    assert power[3].value == 50.5
    assert heart_rate[6].value is None

    coasting = _samples((0, 1, 2, 3), power=(50, 0, 0, 0))
    coasting_curve = mean_max.mean_max_curve(coasting, mean_max.MeanMaxChannel.POWER)
    assert coasting_curve[3] == mean_max.MeanMaxPoint(4, 12.5, 0.0)


def test_earliest_tie_irregular_hold_grid_and_exact_supported_length(
    short_records: None,
) -> None:
    tied = _samples((0, 1, 2, 3, 4, 5), power=(2, 17, 31, 2, 17, 31))
    tied_curve = mean_max.mean_max_curve(tied, mean_max.MeanMaxChannel.POWER)
    assert tied_curve[2] == mean_max.MeanMaxPoint(3, 50 / 3, 0.0)

    irregular = _samples((0, 3, 6), power=(7, 19, 43))
    irregular_curve = mean_max.mean_max_curve(irregular, mean_max.MeanMaxChannel.POWER)
    assert irregular_curve == (
        mean_max.MeanMaxPoint(1, 43.0, 6.0),
        mean_max.MeanMaxPoint(2, 31.0, 5.0),
        mean_max.MeanMaxPoint(3, 27.0, 4.0),
        mean_max.MeanMaxPoint(4, 25.0, 3.0),
        mean_max.MeanMaxPoint(5, 21.4, 2.0),
        mean_max.MeanMaxPoint(6, 19.0, 1.0),
        mean_max.MeanMaxPoint(7, 121 / 7, 0.0),
    )


def test_window_requires_each_second_and_result_is_unrounded(
    short_records: None,
) -> None:
    samples = _samples(
        (0, 1, 2, 3),
        speed=(1.12345678901, 1.22345678901, 1.32345678901, 1.42345678901),
    )
    actual = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.SPEED)
    expected = _reference(samples.time_s, samples.speed_mps, (1, 2, 3, 4, 5, 6, 7), 5.0)
    _assert_reference(actual, expected)
    assert actual[3].value == pytest.approx(1.27345678901, rel=1e-12)
    assert actual[4] == mean_max.MeanMaxPoint(5, None, None)


def test_duration_and_max_step_records_are_patched_live(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    samples = _samples((0, 1, 2, 3, 4, 5, 6), power=(3, 11, 23, 37, 53, 71, 91))
    baseline = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER) == baseline
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_MAX_STEP_S", 0.5)
    split = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert baseline[2].value == pytest.approx(71.66666666666667)
    assert split[2].value is None
    assert baseline != split


def test_empty_samples_return_none_points_for_every_duration(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (1, 2, 3))
    empty = _samples((), power=())
    actual = mean_max.mean_max_curve(empty, mean_max.MeanMaxChannel.POWER)
    assert tuple(point.duration_s for point in actual) == (1, 2, 3)
    assert tuple((point.value, point.start_s) for point in actual) == (
        (None, None),
        (None, None),
        (None, None),
    )


def test_entirely_unrecorded_channel_returns_none_points_for_every_duration(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (1, 2, 3))
    missing = _samples((0, 1, 2), power=(None, None, None))
    actual = mean_max.mean_max_curve(missing, mean_max.MeanMaxChannel.POWER)
    assert tuple(point.duration_s for point in actual) == (1, 2, 3)
    assert tuple((point.value, point.start_s) for point in actual) == (
        (None, None),
        (None, None),
        (None, None),
    )


def test_latest_duplicate_timestamp_wins_and_fractional_origin_is_preserved(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (1,))
    duplicate = _samples((0, 1, 1, 2), power=(3, 7, 101, 13))
    duplicate_curve = mean_max.mean_max_curve(duplicate, mean_max.MeanMaxChannel.POWER)
    assert duplicate_curve == (mean_max.MeanMaxPoint(1, 101.0, 1.0),)

    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (7, 8))
    fractional = _samples((0.25, 3.25, 6.25), power=(7, 19, 43))
    fractional_curve = mean_max.mean_max_curve(
        fractional, mean_max.MeanMaxChannel.POWER
    )
    assert fractional_curve == (
        mean_max.MeanMaxPoint(7, 121 / 7, 0.25),
        mean_max.MeanMaxPoint(8, None, None),
    )


def test_equal_maxima_across_stretches_keep_the_earlier_stretch(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (2,))
    samples = _samples((0, 1, 10, 11), power=(3, 13, 5, 11))
    actual = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert actual == (mean_max.MeanMaxPoint(2, 8.0, 0.0),)


def test_integer_channels_keep_exact_prefix_sums_at_large_values(
    short_records: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (3,))
    large = 2**53
    for channel, keyword in (
        (mean_max.MeanMaxChannel.POWER, "power"),
        (mean_max.MeanMaxChannel.HEART_RATE, "heart_rate"),
    ):
        samples = _samples((0, 1, 2), **{keyword: (large, 1, 1)})
        actual = mean_max.mean_max_curve(samples, channel)
        assert actual == (mean_max.MeanMaxPoint(3, (large + 2) / 3, 0.0),)


def test_shipped_cited_constants_are_unwrapped_at_call_time() -> None:
    records = mean_max_sources.MEAN_MAX_DURATIONS_S
    assert tuple(point.value for point in records) == mean_max.mean_max_durations_s()
    assert all(hasattr(record, "value") for record in records)
    samples = _samples((0, 1, 2), power=(4, 8, 12))
    curve = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert curve[0] == mean_max.MeanMaxPoint(1, 12.0, 2.0)


def test_actual_cited_constant_values_control_the_curve_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duration_record = replace(mean_max_sources.MEAN_MAX_DURATIONS_S[0], value=2)
    step_record = mean_max_sources.MEAN_MAX_MAX_STEP_S
    monkeypatch.setattr(mean_max_sources, "MEAN_MAX_DURATIONS_S", (duration_record,))
    monkeypatch.setattr(
        mean_max_sources, "MEAN_MAX_MAX_STEP_S", replace(step_record, value=0.5)
    )
    samples = _samples((0, 1, 2), power=(11, 23, 37))
    split = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert split == (mean_max.MeanMaxPoint(2, None, None),)

    monkeypatch.setattr(
        mean_max_sources, "MEAN_MAX_MAX_STEP_S", replace(step_record, value=1.0)
    )
    joined = mean_max.mean_max_curve(samples, mean_max.MeanMaxChannel.POWER)
    assert joined == (mean_max.MeanMaxPoint(2, 30.0, 1.0),)


def test_literal_scan_checks_the_rule_source() -> None:
    source = mean_max.__file__
    assert source is not None
    text = Path(source).read_text(encoding="utf-8")
    assert text
    import ast

    tree = ast.parse(text)
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
    ]
    assert literals
    assert all(value in (0, 1) for value in literals)
    imports = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert set(imports) == {
        "__future__",
        "dataclasses",
        "enum",
        "itertools",
        "typing",
        "fitdocs.metrics",
        "fitdocs.model",
    }
