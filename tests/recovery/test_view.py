"""Behavior of the recovery page model."""

from __future__ import annotations

import math
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from fitdocs.history import HistoryComputation, compute_history, read_history_inputs
from fitdocs.recovery import BaselineDay, Baselines, RangePosition
from fitdocs.recovery.view import build_view
from fitdocs.wellness import Metric, SeriesValue
from tests.recovery.builders import series_value, wellness_series, workout_page

D = date(2025, 5, 1)
R = Metric.RESTING_HR_BPM
T = Metric.SLEEP_S
OTHER = tuple(
    Metric(name)
    for name in (
        "respiration_brpm",
        "spo2_pct",
        "stress_level",
        "body_battery_highest",
        "body_battery_lowest",
        "steps",
        "weight_kg",
        "vo2max_ml_per_kg_min",
        "vo2max_run_ml_per_kg_min",
        "vo2max_ride_ml_per_kg_min",
        "fatigue_rating",
        "soreness_rating",
        "mood_rating",
        "motivation_rating",
        "stress_rating",
        "injury_rating",
        "hydration_rating",
    )
)
SLEEP = tuple(
    Metric(name)
    for name in (
        "sleep_s",
        "sleep_deep_s",
        "sleep_light_s",
        "sleep_rem_s",
        "sleep_awake_s",
        "sleep_hr_bpm",
    )
)
BASE = (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS, R)


def v(
    offset: int,
    value: float = 50,
    *,
    metric: Metric = R,
    source: str = "a",
    canonical: bool = True,
    origin: str | None = "local",
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        value,
        metric=metric,
        source=source,
        canonical=canonical,
        origin=origin,
    )


def view(
    values: list[SeriesValue],
    *,
    limit: int = 12,
    load: HistoryComputation | None = None,
) -> Any:
    series = wellness_series(values)
    return build_view(series, Baselines.of(series), load, panel_limit=limit)


def test_empty() -> None:
    assert view([]) is None


def test_window_and_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [v(-100), v(0, 23)]
    monkeypatch.setattr(time, "time", lambda: 946684800.0)
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    if hasattr(time, "tzset"):
        time.tzset()
    first = view(values)
    monkeypatch.setattr(time, "time", lambda: 1893456000.0)
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    if hasattr(time, "tzset"):
        time.tzset()
    second = view(values)
    monkeypatch.undo()
    if hasattr(time, "tzset"):
        time.tzset()
    assert (first, second.window.as_of, second.window.start, second.window.days()) == (
        second,
        D,
        date(2025, 2, 1),
        tuple(date(2025, 2, 1) + timedelta(days=i) for i in range(90)),
    )


@pytest.mark.parametrize("metric", BASE)
@pytest.mark.parametrize("offset", [-90, -89, 0])
def test_sections_and_absent(metric: Metric, offset: int) -> None:
    result = view([v(offset, metric=metric), v(0, metric=Metric.STEPS)])
    present = offset >= -89
    assert (tuple(s.metric for s in result.signals), result.absent) == (
        (metric,) if present else (),
        tuple(m for m in (*BASE, T) if m != metric or not present),
    )


@pytest.mark.parametrize("metric", BASE)
def test_shown_and_latest(metric: Metric) -> None:
    values = [
        v(-4, 81, metric=metric),
        v(-2, 42, metric=metric, source="z"),
        v(-2, 199, metric=metric, canonical=False),
        v(0, metric=Metric.STEPS),
    ]
    result = view(values).signals[0]
    assert (
        len(result.days),
        [
            (
                x.day,
                x.source,
                None
                if x.baseline is None
                else (
                    x.baseline.metric,
                    x.baseline.source,
                    x.baseline.day,
                    x.baseline.value,
                ),
            )
            for x in result.days[-6:]
        ],
        (result.latest.day, result.latest.source, result.latest.baseline.value),
    ) == (
        90,
        [
            (D + timedelta(days=-5), None, None),
            (D + timedelta(days=-4), "a", (metric, "a", D + timedelta(days=-4), 81)),
            (D + timedelta(days=-3), "a", (metric, "a", D + timedelta(days=-3), None)),
            (D + timedelta(days=-2), "z", (metric, "z", D + timedelta(days=-2), 42)),
            (D + timedelta(days=-1), "z", (metric, "z", D + timedelta(days=-1), None)),
            (D, "z", (metric, "z", D, None)),
        ],
        (D + timedelta(days=-2), "z", 42),
    )


def test_changes_and_notes() -> None:
    values = [
        v(-15, origin="alpha"),
        v(-14, origin="zeta"),
        v(-12, origin="zeta"),
        v(-11, source="c", origin="alpha"),
        v(-10, source="c", origin="zeta"),
        v(-2, source="b", origin=None),
        v(0, source="b", origin="beta"),
        v(0, source="unshown", canonical=False, origin="decoy"),
    ]
    result = view(values).signals[0]
    assert (
        [(c.day, c.before, c.after) for c in result.changes],
        [(n.source, n.origins, n.days_shown) for n in result.sources],
    ) == (
        [(D - timedelta(days=11), "a", "c"), (D - timedelta(days=2), "c", "b")],
        [("a", ("alpha", "zeta"), 4), ("b", ("beta",), 3), ("c", ("alpha", "zeta"), 8)],
    )


def test_change_across_gap_and_return() -> None:
    # Days with no shown source (gap longer than the six-day carry) do not
    # reset the comparison: a -> b after the gap is listed, b -> a after a
    # second gap is listed, and a source that returns with nothing different
    # in between is not a change.
    values = [
        v(-40, source="a"),
        v(-20, source="b"),
        v(-10, source="b"),
        v(0, source="a"),
    ]
    result = view(values).signals[0]
    assert [(c.day, c.before, c.after) for c in result.changes] == [
        (D - timedelta(days=20), "a", "b"),
        (D, "b", "a"),
    ]
    returned = view([v(-40, source="a"), v(-20, source="a"), v(0, source="a")])
    assert returned.signals[0].changes == ()


def test_panel_origins() -> None:
    result = view(
        [
            v(0, metric=OTHER[0], source="p", origin="x"),
            v(-1, metric=OTHER[0], source="p", origin=None),
            v(-2, metric=OTHER[0], source="p", origin="b"),
        ]
    )
    assert result.other.panels[0].origins == ("b", "x")


def test_runs() -> None:
    values = [
        v(i, 100, source=s, canonical=s == "a")
        for i in range(-89, -5)
        for s in ("a", "b")
    ]
    values += [
        v(-5, 200),
        v(-4, 200),
        v(-3, 200, source="b"),
        v(-2, 1, source="b"),
        v(-1, 1, source="b"),
        v(0, 1, source="b"),
    ]
    result = view(values).signals[0]
    assert [(r.first, r.last, str(r.position), r.source) for r in result.runs] == [
        (D - timedelta(days=5), D - timedelta(days=4), "above", "a"),
        (D - timedelta(days=3), D - timedelta(days=3), "above", "b"),
        (D - timedelta(days=1), D, "below", "b"),
    ]


@pytest.mark.parametrize(
    "metric,zero",
    [
        (m, z)
        for m in SLEEP
        for z in (False, True)
        if not z or m not in (T, Metric.SLEEP_HR_BPM)
    ],
)
def test_sleep_rows(metric: Metric, zero: bool) -> None:
    amount = 0 if zero else 11 + SLEEP.index(metric)
    values = [
        v(-2, 28000, metric=T),
        v(-1, 29000, metric=T, source="selected"),
        v(0, metric=Metric.STEPS),
    ]
    if metric != T:
        values += [
            v(-1, amount, metric=metric, source="selected", canonical=False),
            v(-1, 88, metric=metric, source="other"),
        ]
    values += (
        [v(-1, 33, metric=Metric.SLEEP_REM_S, source="other")]
        if metric != Metric.SLEEP_REM_S
        else []
    )
    result = view(values).sleep
    expected = [(T, "selected", False, 29000)]
    if metric != T:
        expected += [(metric, "selected", False, amount)]
    assert (
        result.night,
        result.total.latest.source,
        [(r.metric, r.source, isinstance(r.value, bool), r.value) for r in result.rows],
    ) == (D - timedelta(days=1), "selected", expected)


def test_sleep_absent_without_total() -> None:
    assert view([v(0, metric=Metric.SLEEP_DEEP_S)]).sleep is None


@pytest.mark.parametrize("metric", OTHER)
def test_other_metric_order_source_values_and_coverage(metric: Metric) -> None:
    values = [
        v(0, (1.1 + i / 100 if "rating" in m else 41 + i), metric=m, source="z")
        for i, m in enumerate(reversed(OTHER))
    ]
    low, middle, high = (1, 2, 3) if "rating" in metric else (7, 13, 19)
    values += [
        v(-89, low, metric=metric, source="a"),
        v(-1, middle, metric=metric, source="a"),
        v(0, high, metric=metric, source="a", canonical=False),
        v(-90, 4 if "rating" in metric else 97, metric=metric, source="a"),
        v(0, metric=Metric.MIN_HR_BPM),
    ]
    result = view(values, limit=100)
    expected_pairs = [
        (m, s) for m in OTHER for s in (("a", "z") if m == metric else ("z",))
    ]
    assert (
        [(p.metric, p.source, p.values) for p in result.other.panels],
        [
            (r.metric, r.source, type(r.days_with_value), r.days_with_value)
            for r in result.coverage
        ],
    ) == (
        [
            (
                m,
                s,
                (low,) + (None,) * 87 + (middle, high)
                if s == "a"
                else (None,) * 89
                + (
                    (1.1 + (16 - OTHER.index(m)) / 100)
                    if "rating" in m
                    else 57 - OTHER.index(m),
                ),
            )
            for m, s in expected_pairs
        ],
        [(m, s, int, 3 if s == "a" else 1) for m, s in expected_pairs],
    )


@pytest.mark.parametrize("limit", [3, 12])
def test_panel_limit(limit: int) -> None:
    values = [
        v(
            0,
            i + 1,
            metric=Metric.STEPS,
            source=f"s{i:02}",
            canonical=i == 0,
            origin=f"o{i}",
        )
        for i in reversed(range(13))
    ]
    result = view(values, limit=limit)
    assert (
        [(p.metric, p.source) for p in result.other.panels],
        result.other.overflow,
        result.origins,
    ) == (
        [(Metric.STEPS, f"s{i:02}") for i in range(limit)],
        tuple((Metric.STEPS, f"s{i:02}") for i in range(limit, 13)),
        frozenset(f"o{i}" for i in range(limit)),
    )


def test_other_absent() -> None:
    assert view([v(0)]).other is None


def test_no_load(tmp_path: Path) -> None:
    workout_page(tmp_path, "loadless", D, None)
    load = compute_history(read_history_inputs(tmp_path), methodology="threshold")
    result = view([v(0)], load=load)
    assert (
        result.load.rows,
        result.load.methodology,
        result.load.unavailable_days,
        bool(result.load.note),
        tuple(s.metric for s in result.signals),
    ) == ((), None, 90, True, (R,))


def test_load_alignment_and_suppression(tmp_path: Path) -> None:
    for i in range(14):
        workout_page(
            tmp_path,
            f"w{i}",
            date(2025, 4, 7) + timedelta(days=i),
            10 + i if i < 7 or i == 13 else None,
            methodology="chosen",
        )
    (tmp_path / "fitdocs.toml").write_text(
        "[history]\ncoverage_threshold = 0.8\n", encoding="utf-8"
    )
    load = compute_history(read_history_inputs(tmp_path), methodology="chosen")
    result = view([v(0)], load=load).load
    assert (
        result.methodology,
        result.note,
        result.unavailable_days,
        [
            (
                r.day,
                r.recorded_load,
                type(r.suppressed),
                r.suppressed,
                r.fitness is None,
                r.fatigue is None,
                r.form is None,
            )
            if r is not None
            else None
            for r in result.rows
        ],
    ) == (
        "chosen",
        None,
        83,
        [None] * 65
        + [
            (
                date(2025, 4, 7) + timedelta(days=i),
                float(10 + i) if i < 7 or i == 13 else 0.0,
                bool,
                i >= 7,
                i >= 7,
                i >= 7,
                i >= 7,
            )
            for i in range(14)
        ]
        + [None] * 11,
    )


def history_values(metric: Metric, offsets: list[int]) -> list[SeriesValue]:
    return [
        item
        for i in offsets
        for item in (
            v(
                i,
                50,
                metric=metric,
                source="history",
                canonical=False,
                origin="garmin" if i == -60 else f"history{i}",
            ),
            v(i, 71, metric=metric, source="decoy", origin="decoy"),
        )
    ]


@pytest.mark.parametrize("formed", [False, True])
@pytest.mark.parametrize("metric", BASE)
def test_origins_baseline_formation(metric: Metric, formed: bool) -> None:
    offsets = [-61, -60] + list(range(-59 if formed else -58, -30))
    values = history_values(metric, offsets) + [
        v(0, 123, metric=metric, source="history", origin="own"),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    expected = {"own", "anchor"} | (
        ({"garmin"} | {f"history{i}" for i in offsets if i > -60}) if formed else set()
    )
    assert view(values).origins == frozenset(expected)


@pytest.mark.parametrize("formed", [False, True])
@pytest.mark.parametrize("metric", (*BASE, T))
def test_origins_rolling_formation(metric: Metric, formed: bool) -> None:
    offsets = [-7, -6, -3] if formed else [-7, -3]
    values = history_values(metric, offsets) + [
        v(0, 123, metric=metric, source="history", origin=None),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    expected = {None, "anchor"} | ({"history-6", "history-3"} if formed else set())
    assert view(values).origins == frozenset(expected)


@pytest.mark.parametrize("metric", SLEEP)
def test_sleep_row_origins(metric: Metric) -> None:
    offsets = [-61, -60] + list(range(-59, -31)) + [-6, -3, -1]
    values = history_values(metric, offsets) + [
        v(0, 123, metric=metric, source="history", origin="night"),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    if metric != T:
        values += [v(0, 28000, metric=T, source="history", origin="total")]
    expected = (
        {"night", "anchor"}
        | ({"total"} if metric != T else set())
        | ({"garmin"} | {f"history{i}" for i in offsets if i > -60})
    )
    assert view(values).origins == frozenset(expected)


def test_sleep_chart_does_not_use_historical_baseline() -> None:
    values = history_values(T, list(range(-60, -30))) + [
        v(0, 28000, metric=T, source="history", origin="earlier"),
        v(20, 29000, metric=T, source="new", origin="latest"),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    assert view(values).origins == frozenset({"earlier", "latest", "anchor"})


def test_runs_split_adjacent_directions() -> None:
    values = (
        [v(i, 100) for i in range(-89, -7)]
        + [v(-7, 250)]
        + [v(i, 90) for i in range(-6, 0)]
        + [v(0, 10)]
    )
    assert [
        (r.first, r.last, str(r.position), r.source)
        for r in view(values).signals[0].runs
    ] == [
        (D - timedelta(days=7), D - timedelta(days=1), "above", "a"),
        (D, D, "below", "a"),
    ]


def test_runs_split_unmarked_gap() -> None:
    values = [v(i, 100) for i in range(-89, -10)] + [
        v(-10, 200),
        v(-2, 210),
        v(-1, 220),
        v(0, 230),
    ]
    assert [
        (r.first, r.last, str(r.position), r.source)
        for r in view(values).signals[0].runs
    ] == [
        (D - timedelta(days=10), D - timedelta(days=6), "above", "a"),
        (D, D, "above", "a"),
    ]


@pytest.mark.parametrize("metric", BASE)
def test_origins_baseline_last_day(metric: Metric) -> None:
    offsets = [-61, -60] + list(range(-59, -31)) + [-1]
    values = history_values(metric, offsets) + [
        v(0, 123, metric=metric, source="history", origin="own"),
        v(1, 72, metric=metric, source="after", origin="after"),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    assert view(values).origins == frozenset(
        {"own", "anchor", "after"}
        | ({"garmin"} | {f"history{i}" for i in offsets if i > -60})
    )


@pytest.mark.parametrize("kind", ["within", "no-rolling", "no-range"])
def test_no_marked_runs(kind: str) -> None:
    offsets = (
        range(-89, 1)
        if kind == "within"
        else (list(range(-60, -30)) + [0] if kind == "no-rolling" else [-2, -1, 0])
    )
    result = view([v(i, 100) for i in offsets])
    assert result.signals[0].runs == ()


@pytest.mark.parametrize("metric", (R, *SLEEP))
def test_latest_statistics_forwarded(metric: Metric) -> None:
    values = [v(i, 50, metric=metric, source="selected") for i in range(-60, -30)]
    values += [
        v(-6, 60, metric=metric, source="selected"),
        v(-3, 90, metric=metric, source="selected"),
        v(0, 120, metric=metric, source="selected", origin="latest"),
    ]
    if metric in SLEEP and metric != T:
        values += [v(0, 28000, metric=T, source="selected")]
    result = view(values)
    bd = (
        result.signals[0].latest.baseline
        if metric == R
        else next(row for row in result.sleep.rows if row.metric == metric)
    )
    sd = math.sqrt((86700 - 32 * 51.5625**2) / 31)
    assert bd == BaselineDay(
        metric,
        "selected",
        D,
        120,
        "latest",
        90,
        3,
        51.5625,
        sd,
        32,
        51.5625 - 0.5 * sd if metric == R else None,
        51.5625 + 0.5 * sd if metric == R else None,
        RangePosition.ABOVE if metric == R else None,
    )


def test_signal_order() -> None:
    assert (
        tuple(
            signal.metric
            for signal in view(
                [v(0, 31 + i, metric=m) for i, m in enumerate(reversed(BASE))]
            ).signals
        )
        == BASE
    )


def test_sleep_metric_order() -> None:
    result = view([v(0, 30 + i, metric=m) for i, m in enumerate(reversed(SLEEP))]).sleep
    assert [(row.metric, row.value) for row in result.rows] == [
        (m, 35 - i) for i, m in enumerate(SLEEP)
    ]


def test_load_values_forwarded(tmp_path: Path) -> None:
    for i in range(7):
        workout_page(
            tmp_path,
            f"load{i}",
            D - timedelta(days=6 - i),
            17 + i * 3,
            methodology="distinct",
        )
    load = compute_history(read_history_inputs(tmp_path), methodology="distinct")
    result = view([v(0)], load=load).load
    expected = []
    for i in range(7):
        fitness = sum((17 + 3 * j) * math.exp(-(i - j) / 45) for j in range(i + 1)) * (
            1 - math.exp(-1 / 45)
        )
        fatigue = sum((17 + 3 * j) * math.exp(-(i - j) / 15) for j in range(i + 1)) * (
            1 - math.exp(-1 / 15)
        )
        expected.append(
            (
                D - timedelta(days=6 - i),
                17 + 3 * i,
                1,
                1,
                bool,
                False,
                tuple(
                    (float, round(x, 12)) for x in (fitness, fatigue, fitness - fatigue)
                ),
            )
        )
    assert [
        None
        if row is None
        else (
            row.day,
            row.recorded_load,
            row.pages,
            row.pages_with_load,
            type(row.suppressed),
            row.suppressed,
            tuple(
                None if x is None else (type(x), round(x, 12))
                for x in (row.fitness, row.fatigue, row.form)
            ),
        )
        for row in result.rows
    ] == [None] * 83 + expected


def test_load_window_clips_both_ends(tmp_path: Path) -> None:
    for name, day, amount in (
        ("before", date(2025, 1, 25), 20),
        ("first", date(2025, 2, 1), 30),
        ("last", D, 70),
        ("after", date(2025, 5, 8), 90),
    ):
        workout_page(tmp_path, name, day, amount)
    (tmp_path / "fitdocs.toml").write_text(
        "[history]\ncoverage_threshold = 0.0\n", encoding="utf-8"
    )
    load = compute_history(read_history_inputs(tmp_path), methodology="threshold")
    result = view([v(0)], load=load).load
    assert (
        result.unavailable_days,
        [
            (row.day, row.recorded_load) if row is not None else None
            for row in result.rows
        ],
    ) == (
        0,
        [
            (
                date(2025, 2, 1) + timedelta(days=i),
                30 if i == 0 else (70 if i == 89 else 0),
            )
            for i in range(90)
        ],
    )


@pytest.mark.parametrize("metric", (*BASE, *SLEEP))
def test_baselined_and_sleep_coverage(metric: Metric) -> None:
    values = [
        v(-90, 21, metric=metric),
        v(-89, 31, metric=metric),
        v(-7, 43, metric=metric),
        v(0, 57, metric=metric),
        v(0, 69, metric=metric, source="other", canonical=False),
    ]
    assert [
        (row.metric, row.source, type(row.days_with_value), row.days_with_value)
        for row in view(values).coverage
    ] == [(metric, "a", int, 3), (metric, "other", int, 1)]


@pytest.mark.parametrize("metric", SLEEP)
@pytest.mark.parametrize("formed", [False, True])
def test_sleep_origin_formation(metric: Metric, formed: bool) -> None:
    offsets = [-61, -60] + list(range(-59 if formed else -58, -30))
    values = history_values(metric, offsets) + [
        v(0, 123, metric=metric, source="history", origin="night"),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    if metric != T:
        values += [v(0, 28000, metric=T, source="history", origin="total")]
    expected = {"night", "anchor"} | ({"total"} if metric != T else set())
    if formed:
        expected |= {"garmin"} | {f"history{i}" for i in offsets if i > -60}
    assert view(values).origins == frozenset(expected)


@pytest.mark.parametrize("metric", SLEEP)
@pytest.mark.parametrize("formed", [False, True])
def test_sleep_rolling_origin_formation(metric: Metric, formed: bool) -> None:
    offsets = [-7, -6, -3] if formed else [-7, -3]
    values = history_values(metric, offsets) + [
        v(0, 123, metric=metric, source="history", origin="night"),
        v(89, metric=Metric.STEPS, origin="anchor"),
    ]
    if metric != T:
        values += [v(0, 28000, metric=T, source="history", origin="total")]
    expected = (
        {"night", "anchor"}
        | ({"total"} if metric != T else set())
        | ({"history-6", "history-3"} if formed else set())
    )
    assert view(values).origins == frozenset(expected)


@pytest.mark.parametrize("metric", OTHER)
@pytest.mark.parametrize("dimension", ["metric", "source"])
@pytest.mark.parametrize("offset", [-90, -89, 0])
def test_round2_other_pair_window(metric: Metric, dimension: str, offset: int) -> None:
    values = [
        v(0, 53, origin="anchor"),
        v(
            offset,
            2,
            metric=metric,
            source="aaa-target",
            canonical=offset != 0 or dimension == "metric",
            origin="target",
        ),
    ]
    if dimension == "source":
        values += [v(0, 3, metric=metric, source="zzz-live", origin="live")]
    result = view(values, limit=1)
    eligible = offset >= -89
    target_values = tuple(2 if i == offset + 89 else None for i in range(90))
    expected_panels = (
        [(metric, "aaa-target", target_values)]
        if eligible
        else (
            [(metric, "zzz-live", (None,) * 89 + (3,))] if dimension == "source" else []
        )
    )
    expected_overflow = (
        ((metric, "zzz-live"),) if eligible and dimension == "source" else ()
    )
    expected_coverage = [(R, "a", int, 1)]
    if eligible:
        expected_coverage += [(metric, "aaa-target", int, 1)]
    if dimension == "source":
        expected_coverage += [(metric, "zzz-live", int, 1)]
    expected_origins = {"anchor"} | (
        {"target"} if eligible else ({"live"} if dimension == "source" else set())
    )
    assert (
        result.other is None,
        []
        if result.other is None
        else [(p.metric, p.source, p.values) for p in result.other.panels],
        () if result.other is None else result.other.overflow,
        [
            (r.metric, r.source, type(r.days_with_value), r.days_with_value)
            for r in result.coverage
        ],
        result.origins,
    ) == (
        dimension == "metric" and offset == -90,
        expected_panels,
        expected_overflow,
        expected_coverage,
        frozenset(expected_origins),
    )


@pytest.mark.parametrize("stage", SLEEP[1:])
@pytest.mark.parametrize("offset", [-90, -89, 0])
def test_round2_sleep_total_window(stage: Metric, offset: int) -> None:
    result = view(
        [
            v(offset, 27000, metric=T, source="total-source", origin="total"),
            v(0, 43, metric=stage, source="stage-decoy", origin="stage-decoy"),
            v(0, 7, metric=Metric.STEPS, origin="anchor"),
        ]
    )
    expected_sleep = (
        None
        if offset == -90
        else (D + timedelta(days=offset), [(T, "total-source", 27000)])
    )
    expected_coverage = ([] if offset == -90 else [(T, "total-source", 1)]) + [
        (stage, "stage-decoy", 1),
        (Metric.STEPS, "a", 1),
    ]
    assert (
        None
        if result.sleep is None
        else (
            result.sleep.night,
            [(r.metric, r.source, r.value) for r in result.sleep.rows],
        ),
        [(r.metric, r.source, r.days_with_value) for r in result.coverage],
        result.origins,
    ) == (
        expected_sleep,
        expected_coverage,
        frozenset({"anchor"} | ({"total"} if offset >= -89 else set())),
    )


@pytest.mark.parametrize("metric", (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS))
def test_round2_hrv_complete_record(metric: Metric) -> None:
    index = 0 if metric == Metric.HRV_SDNN_MS else 1
    old = [32 + (i % 7) + 3 * index for i in range(30)]
    recent = [80 + 11 * index, 110 + 13 * index, 170 + 17 * index]
    source = f"selected-{metric}"
    values = [
        v(i - 60, amount, metric=metric, source=source, origin="history")
        for i, amount in enumerate(old)
    ]
    values += [
        v(
            offset,
            amount,
            metric=metric,
            source=source,
            origin="latest" if offset == 0 else "recent",
        )
        for offset, amount in zip((-6, -3, 0), recent, strict=True)
    ]
    bd = view(values).signals[0].latest.baseline
    logs = [math.log(amount) for amount in (*old, *recent[:2])]
    mu = math.fsum(logs) / 32
    sd = math.sqrt(math.fsum((x - mu) ** 2 for x in logs) / 31)
    rolling = math.exp(math.fsum(math.log(amount) for amount in recent) / 3)
    expected = BaselineDay(
        metric,
        source,
        D,
        recent[-1],
        "latest",
        rolling,
        3,
        math.exp(mu),
        sd,
        32,
        math.exp(mu - 0.5 * sd),
        math.exp(mu + 0.5 * sd),
        RangePosition.ABOVE,
    )
    assert (bd, type(bd.rolling_count), type(bd.baseline_count)) == (expected, int, int)


_ROUND2_ZERO_STAGES = (
    Metric.SLEEP_DEEP_S,
    Metric.SLEEP_LIGHT_S,
    Metric.SLEEP_REM_S,
    Metric.SLEEP_AWAKE_S,
)


@pytest.mark.parametrize("metric", _ROUND2_ZERO_STAGES)
@pytest.mark.parametrize(
    "family,formed",
    [
        ("own", False),
        ("rolling", False),
        ("rolling", True),
        ("baseline", False),
        ("baseline", True),
    ],
)
def test_round2_zero_stage_origins(metric: Metric, family: str, formed: bool) -> None:
    zero_origin = "garmin"
    expected: tuple[float, float | None, int, float | None, int]
    values = [
        v(0, 28000, metric=T, source="selected", origin="total"),
        v(89, 5, metric=Metric.STEPS, origin="anchor"),
    ]
    if family == "own":
        values += [v(0, 0, metric=metric, source="selected", origin=zero_origin)]
        expected = (0, None, 1, None, 0)
        expected_origins = {"garmin", "total", "anchor"}
    elif family == "rolling":
        values += [
            v(-6, 0, metric=metric, source="selected", origin=zero_origin),
            v(0, 19, metric=metric, source="selected", origin="night"),
        ]
        if formed:
            values += [v(-3, 14, metric=metric, source="selected", origin="recent")]
        expected = (
            19,
            11 if formed else None,
            3 if formed else 2,
            None,
            2 if formed else 1,
        )
        expected_origins = {"night", "total", "anchor"} | (
            {"garmin", "recent"} if formed else set()
        )
    else:
        older = list(range(14, 43 if formed else 42))
        values += [
            v(-60, 0, metric=metric, source="selected", origin=zero_origin),
            v(0, 19, metric=metric, source="selected", origin="night"),
        ]
        values += [
            v(i - 59, amount, metric=metric, source="selected", origin=f"older-{i}")
            for i, amount in enumerate(older)
        ]
        expected = (19, None, 1, 812 / 30 if formed else None, 30 if formed else 29)
        expected_origins = {"night", "total", "anchor"} | (
            {"garmin"} | {f"older-{i}" for i in range(29)} if formed else set()
        )
    result = view(values)
    row = result.sleep.rows[1]
    assert (
        result.window.start,
        result.sleep.night,
        row.metric,
        row.source,
        row.day,
        row.origin,
        isinstance(row.value, bool),
        (
            row.value,
            row.rolling_mean,
            row.rolling_count,
            row.baseline_mean,
            row.baseline_count,
        ),
        (type(row.rolling_count), type(row.baseline_count)),
        (
            None if row.baseline_sd is None else round(row.baseline_sd, 12),
            row.range_low,
            row.range_high,
            row.position,
        ),
        result.origins,
    ) == (
        D,
        D,
        metric,
        "selected",
        D,
        "garmin" if family == "own" else "night",
        False,
        expected,
        (int, int),
        (
            round(
                math.sqrt(
                    (sum(x * x for x in range(14, 43)) - 30 * (812 / 30) ** 2) / 29
                ),
                12,
            )
            if family == "baseline" and formed
            else None,
            None,
            None,
            None,
        ),
        frozenset(expected_origins),
    )


@pytest.mark.parametrize("metric", (Metric.MIN_HR_BPM, Metric.MAX_HR_BPM))
def test_round2_nonpage_asof(metric: Metric) -> None:
    result = view(
        [v(-11, 77, origin="older"), v(0, 91, metric=metric, origin="latest-nonpage")]
    )
    assert (result.window.as_of, result.window.start, result.window.days()) == (
        D,
        date(2025, 2, 1),
        tuple(date(2025, 2, 1) + timedelta(days=i) for i in range(90)),
    )


def _round3_fixture(
    metric: Metric,
) -> tuple[Any, Baselines, Any, list[int], list[int], list[int], list[int]]:
    index = (*BASE, T).index(metric)
    old_a = [40 + 2 * index + i % 5 for i in range(30)]
    old_b = [65 + 3 * index + i % 7 for i in range(30)]
    recent_a = [80 + 3 * index, 110 + 4 * index, 140 + 5 * index]
    recent_b = [95 + 5 * index, 135 + 6 * index, 185 + 7 * index]
    values = [
        v(i - 72, amount, metric=metric, source=f"{metric}-a", origin="old-a")
        for i, amount in enumerate(old_a)
    ]
    values += [
        v(
            i - 60,
            amount,
            metric=metric,
            source=f"{metric}-b",
            canonical=i > 17,
            origin="old-b",
        )
        for i, amount in enumerate(old_b)
    ]
    values += [
        v(offset, amount, metric=metric, source=f"{metric}-a", origin="recent-a")
        for offset, amount in zip((-18, -15, -12), recent_a, strict=True)
    ]
    values += [
        v(
            offset,
            amount,
            metric=metric,
            source=f"{metric}-b",
            origin="latest-b" if offset == 0 else "recent-b",
        )
        for offset, amount in zip((-6, -3, 0), recent_b, strict=True)
    ]
    values += [v(0, 17, metric=Metric.STEPS, origin="anchor")]
    series = wellness_series(values)
    baselines = Baselines.of(series)
    result: Any = build_view(series, baselines, None, panel_limit=12)
    signal = result.sleep.total if metric == T else result.signals[0]
    return series, baselines, signal, old_a, old_b, recent_a, recent_b


def _round3_expected_record(
    metric: Metric,
    source: str,
    offset: int,
    value: float | None,
    origin: str | None,
    rolling_values: list[int],
    baseline_values: list[int],
    position: RangePosition | None,
) -> BaselineDay:
    transform = (
        math.log if metric in (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS) else float
    )
    inverse = math.exp if metric in (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS) else float
    rolling = (
        inverse(math.fsum(transform(x) for x in rolling_values) / len(rolling_values))
        if len(rolling_values) >= 3
        else None
    )
    mu = (
        math.fsum(transform(x) for x in baseline_values) / len(baseline_values)
        if len(baseline_values) >= 30
        else None
    )
    sd = (
        None
        if mu is None
        else math.sqrt(
            math.fsum((transform(x) - mu) ** 2 for x in baseline_values)
            / (len(baseline_values) - 1)
        )
    )
    low = (
        inverse(mu - 0.5 * sd)
        if mu is not None and sd is not None and metric != T
        else None
    )
    high = (
        inverse(mu + 0.5 * sd)
        if mu is not None and sd is not None and metric != T
        else None
    )
    return BaselineDay(
        metric,
        source,
        D + timedelta(days=offset),
        value,
        origin,
        rolling,
        len(rolling_values),
        None if mu is None else inverse(mu),
        sd,
        len(baseline_values),
        low,
        high,
        position,
    )


def _round3_projection(shown: Any) -> Any:
    if shown is None:
        return None
    bd = shown.baseline
    return (
        shown.day,
        shown.source,
        bd,
        None if bd is None else (type(bd.rolling_count), type(bd.baseline_count)),
    )


@pytest.mark.parametrize("metric", (*BASE, T))
def test_round3_signal_daily_records(metric: Metric) -> None:
    _, baselines, signal, old_a, old_b, recent_a, recent_b = _round3_fixture(metric)
    days = tuple(date(2025, 2, 1) + timedelta(days=i) for i in range(90))
    public_expected = tuple(
        (
            day,
            baselines.shown_source(metric, day),
            bd,
            None if bd is None else (int, int),
        )
        for day in days
        for bd in (baselines.shown(metric, day),)
    )
    position = None if metric == T else RangePosition.ABOVE
    source_a, source_b = f"{metric}-a", f"{metric}-b"
    key_records = (
        None,
        _round3_expected_record(
            metric, source_a, -72, old_a[0], "old-a", [old_a[0]], [], None
        ),
        _round3_expected_record(
            metric,
            source_a,
            -12,
            recent_a[2],
            "recent-a",
            recent_a,
            old_a + recent_a[:2],
            position,
        ),
        _round3_expected_record(
            metric, source_a, -11, None, None, recent_a[1:], old_a[1:] + recent_a, None
        ),
        _round3_expected_record(
            metric, source_b, -6, recent_b[0], "recent-b", recent_b[:1], old_b, None
        ),
        _round3_expected_record(
            metric,
            source_b,
            -3,
            recent_b[1],
            "recent-b",
            recent_b[:2],
            old_b + recent_b[:1],
            None,
        ),
        _round3_expected_record(
            metric,
            source_b,
            0,
            recent_b[2],
            "latest-b",
            recent_b,
            old_b + recent_b[:2],
            position,
        ),
    )
    assert (
        signal.metric,
        tuple(_round3_projection(shown) for shown in signal.days),
        tuple(
            shown.baseline
            for i, shown in enumerate(signal.days)
            if i in (0, 17, 77, 78, 83, 86, 89)
        ),
    ) == (metric, public_expected, key_records)


@pytest.mark.parametrize("metric", (*BASE, T))
def test_round3_signal_latest_record(metric: Metric) -> None:
    _, _, signal, _, old_b, _, recent_b = _round3_fixture(metric)
    source = f"{metric}-b"
    expected = _round3_expected_record(
        metric,
        source,
        0,
        recent_b[2],
        "latest-b",
        recent_b,
        old_b + recent_b[:2],
        None if metric == T else RangePosition.ABOVE,
    )
    assert _round3_projection(signal.latest) == (D, source, expected, (int, int))
