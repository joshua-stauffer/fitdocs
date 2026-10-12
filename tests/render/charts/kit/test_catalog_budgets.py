"""Byte budgets of the catalog kinds' typical charts and their at-bound ceiling.

Requirement 12.4. The numbers here are the source of truth: the design's
initial budgets, lowered to measured + 25% (rounded up to 100) where the
measurement left more than 40% headroom, and set to measured + 25% by
controller ruling where the measurement exceeded the design (calendar-heatmap, box, stacked-100).
The measured sizes are recorded in tasks.md, Implementation Notes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.api import render_chart
from fitdocs.render.charts.kit.data import ChartData, Value, ValueKind
from fitdocs.render.charts.kit.registry import KINDS
from fitdocs.render.charts.kit.schema import ChartRequest
from tests.render.charts.kit._helpers import chart_data, chart_request, column
from tests.render.charts.kit.goldens import GOLDEN_ROOT

START = date(2025, 1, 6)
AT_BOUND_CEILING = 80_000
CATALOG_KINDS = (
    "calendar-heatmap",
    "heatmap",
    "dual-axis",
    "band",
    "box",
    "mean-max",
    "small-multiples",
    "stacked-100",
)


def _render(request: ChartRequest, data: ChartData) -> str:
    return render_chart(request, data).text


# --- the typical charts, named by the design -----------------------------------


def _calendar_heatmap() -> str:
    day = column("day", ValueKind.DATE)
    km = column("distance_km", unit="km")
    rows: list[tuple[Value, ...]] = []
    for i in range(365):
        if i % 17 == 3:
            rows.append((START + timedelta(days=i), None))
        elif i % 7 == 2:
            rows.append((START + timedelta(days=i), 0.0))
        else:
            rows.append(
                (START + timedelta(days=i), round(1.0 + ((i * 5) % 19) * 0.5, 1))
            )
    request = chart_request(
        "calendar-heatmap",
        title="Daily distance",
        channels={"date": "day", "value": "distance_km"},
    )
    return _render(request, chart_data((day, km), rows))


def _heatmap() -> str:
    zone = column("zone")
    week = column("week", ValueKind.DATE)
    time_s = column("time_s", unit="s")
    rows: list[tuple[Value, ...]] = [
        (z + 1, START + timedelta(weeks=w), float((w * 37 + z * 11) % 97) * 60)
        for z in range(5)
        for w in range(52)
    ]
    request = chart_request(
        "heatmap",
        title="Zone time",
        channels={"x": "week", "y": "zone", "value": "time_s"},
    )
    return _render(request, chart_data((zone, week, time_s), rows))


def _dual_axis() -> str:
    day = column("day", ValueKind.DATE)
    pace = column("pace_s_per_km", unit="s")
    hr = column("hr_bpm", unit="bpm")
    rows: list[tuple[Value, ...]] = [
        (
            START + timedelta(days=i),
            270.0 + ((i * 37) % 211) / 7 + i / 90,
            140.0 + ((i * 53) % 97) / 3 + i / 120,
        )
        for i in range(365)
    ]
    request = chart_request(
        "dual-axis",
        title="Pace and heart rate",
        channels={"x": "day", "y": "pace_s_per_km", "y2": "hr_bpm"},
    )
    return _render(request, chart_data((day, pace, hr), rows))


def _band() -> str:
    week = column("week", ValueKind.DATE)
    low = column("hr_p10_bpm", unit="bpm")
    high = column("hr_p90_bpm", unit="bpm")
    mid = column("hr_p50_bpm", unit="bpm")
    rows: list[tuple[Value, ...]] = []
    for i in range(52):
        base = 120.0 + ((i * 37) % 211) / 9 + i / 7
        rows.append(
            (START + timedelta(weeks=i), base, base + 20.0 + (i % 7), base + 9.0)
        )
    request = chart_request(
        "band",
        title="Heart rate spread",
        channels={
            "x": "week",
            "low": "hr_p10_bpm",
            "high": "hr_p90_bpm",
            "mid": "hr_p50_bpm",
        },
    )
    return _render(request, chart_data((week, low, high, mid), rows))


def _box() -> str:
    block = column("block", ValueKind.CATEGORY)
    names = ("low_w", "q1_w", "median_w", "q3_w", "high_w")
    rows: list[tuple[Value, ...]] = []
    for i in range(12):
        low = 100.0 + (i * 37) % 61 + i / 3
        q1 = low + 10 + i % 5 + 0.37
        median = q1 + (i * 7) % 9 + 1.21
        q3 = median + (i * 3) % 8 + 1.43
        high = q3 + (i * 5) % 11 + 2.17
        rows.append((f"Block {i:02d}", low, q1, median, q3, high))
    request = chart_request(
        "box",
        title="Weekly power",
        channels={
            "x": "block",
            "low": "low_w",
            "q1": "q1_w",
            "median": "median_w",
            "q3": "q3_w",
            "high": "high_w",
        },
    )
    columns = (block, *(column(name, unit="w") for name in names))
    return _render(request, chart_data(columns, rows))


def _mean_max() -> str:
    from fitdocs.metrics.mean_max_sources import MEAN_MAX_DURATIONS_S

    period = column("period", ValueKind.CATEGORY)
    duration = column("duration_s", unit="s")
    power = column("power_w", unit="w")
    durations = tuple(float(c.value) for c in MEAN_MAX_DURATIONS_S)[:28]
    assert len(durations) == 28
    rows: list[tuple[Value, ...]] = [
        (
            d,
            round(1500.0 / (1 + i / 3) + 200 - p * 17 + ((i * 13) % 7) / 3, 2),
            f"Season {p}",
        )
        for p in range(3)
        for i, d in enumerate(durations)
    ]
    request = chart_request(
        "mean-max",
        title="Power curve",
        channels={"x": "duration_s", "y": "power_w", "color": "period"},
    )
    return _render(request, chart_data((duration, power, period), rows))


def _small_multiples() -> str:
    week = column("week", ValueKind.DATE)
    km = column("distance_km", unit="km")
    shoe = column("shoe", ValueKind.CATEGORY)
    rows: list[tuple[Value, ...]] = [
        (
            START + timedelta(weeks=w),
            10.0 + ((p * 31 + w * 17) % 53) / 3 + w / 10,
            f"Shoe {p}",
        )
        for p in range(6)
        for w in range(52)
    ]
    request = chart_request(
        "small-multiples",
        title="Shoe mileage",
        channels={"x": "week", "y": "distance_km", "facet": "shoe"},
    )
    return _render(request, chart_data((week, km, shoe), rows))


def _stacked_100() -> str:
    zone = column("zone", ValueKind.CATEGORY)
    week = column("week", ValueKind.DATE)
    seconds = column("time_in_zone_s", unit="s")
    rows: list[tuple[Value, ...]] = [
        (
            f"Z{z + 1}",
            START + timedelta(weeks=w),
            float(60 + (w * 31 + z * 17) % 97) * 20,
        )
        for w in range(52)
        for z in range(5)
    ]
    request = chart_request(
        "stacked-100",
        title="Time in zone",
        channels={"x": "week", "y": "time_in_zone_s", "color": "zone"},
    )
    return _render(request, chart_data((zone, week, seconds), rows))


#: name -> (builder, byte budget). Design budget -> test budget, measured size:
#: calendar-heatmap 16,000 -> 20,200 (measured 16,150; EXCEEDS the design, by
#: controller ruling measured + 25%); heatmap 14,000 kept (13,197); dual-axis
#: 16,000 kept (14,828); band 8,000 -> 6,700 (5,306; over 40% headroom);
#: box 6,000 -> 13,300 (10,605; EXCEEDS, controller ruling); mean-max 8,000 kept
#: (5,835); small-multiples 18,000 -> 12,700 (10,111); stacked-100 22,000 ->
#: 28,600 (22,823; EXCEEDS, controller ruling).
TYPICAL: dict[str, tuple[Callable[[], str], int]] = {
    "calendar-heatmap 365 days": (_calendar_heatmap, 20_200),
    "heatmap 52x5": (_heatmap, 14_000),
    "dual-axis 2x365": (_dual_axis, 16_000),
    "band 52 weeks with mid": (_band, 6_700),
    "box 12 boxes": (_box, 13_300),
    "mean-max 3x28": (_mean_max, 8_000),
    "small-multiples 6x52": (_small_multiples, 12_700),
    "stacked-100 52x5": (_stacked_100, 28_600),
}


@pytest.mark.parametrize("name", list(TYPICAL))
def test_typical_chart_fits_its_budget(name: str) -> None:
    build, budget = TYPICAL[name]
    size = len(build().encode())
    assert size <= budget, f"{name}: {size} > {budget}"


# --- the at-bound ceiling --------------------------------------------------------


def test_every_catalog_at_bound_golden_is_under_the_ceiling() -> None:
    assert {s.name for s in KINDS} >= set(CATALOG_KINDS)
    for name in CATALOG_KINDS:
        (path,) = GOLDEN_ROOT.glob(f"{name}/at_bound.*")
        size = path.stat().st_size
        assert size > 1_000, path  # a bound-sized golden, not a stub
        assert size <= AT_BOUND_CEILING, f"{path}: {size} > {AT_BOUND_CEILING}"
