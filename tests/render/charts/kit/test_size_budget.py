"""Byte budgets of typical charts and the ceiling of every at-bound golden.

Requirements 11.4, 11.5. The numbers here are the source of truth. The hbar
20-bar budget was raised from the design's 8,000 to 13,400 by controller ruling
(measured 10,689); the other budgets are the design's or, where the measurement
left more than 40% headroom, lowered to measured + 25% (the measured sizes are
recorded in tasks.md, Implementation Notes).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.api import render_chart
from fitdocs.render.charts.kit.data import ChartData, ValueKind
from fitdocs.render.charts.kit.registry import KINDS
from fitdocs.render.charts.kit.schema import ChartRequest, Output
from tests.render.charts.kit._helpers import Case, chart_data, chart_request, column
from tests.render.charts.kit.goldens import GOLDEN_ROOT

SPORTS = ("run", "bike", "swim")
START = date(2025, 1, 1)
DAY = column("day", ValueKind.DATE)
KM = column("distance_km", unit="km")
SPORT = column("sport", ValueKind.CATEGORY)


def _value(i: int, s: int) -> float:
    """A varied, unrounded distance: thirds (5 + k/3) that the kit must round."""
    return 5.0 + ((i * 7 + s * 13) % 23) / 3


def _daily_rows(
    count: int, step: timedelta, *, gap: range = range(0)
) -> list[tuple[date, float | None, str]]:
    return [
        (
            START + step * i,
            None if (sport == "bike" and i in gap) else _value(i, s),
            sport,
        )
        for s, sport in enumerate(SPORTS)
        for i in range(count)
    ]


def _render(request: ChartRequest, data: ChartData) -> str:
    return render_chart(request, data).text


# --- the typical charts, named by the design -----------------------------------


def _line() -> tuple[str, int]:
    rows = _daily_rows(365, timedelta(days=1), gap=range(100, 110))
    request = chart_request(
        "line",
        title="Distance",
        channels={"x": "day", "y": "distance_km", "color": "sport"},
    )
    return _render(request, chart_data((DAY, KM, SPORT), rows)), len(rows)


def _area_stacked() -> tuple[str, int]:
    rows = _daily_rows(52, timedelta(weeks=1))
    request = chart_request(
        "area",
        title="Distance",
        channels={"x": "day", "y": "distance_km", "color": "sport"},
        options={"stack": True},
    )
    return _render(request, chart_data((DAY, KM, SPORT), rows)), len(rows)


def _bar() -> tuple[str, int]:
    rows = [(START + timedelta(weeks=i), _value(i, 0)) for i in range(52)]
    request = chart_request(
        "bar", title="Distance", channels={"x": "day", "y": "distance_km"}
    )
    return _render(request, chart_data((DAY, KM), rows)), len(rows)


def _bar_stacked() -> tuple[str, int]:
    rows = _daily_rows(52, timedelta(weeks=1))
    request = chart_request(
        "bar",
        title="Distance",
        channels={"x": "day", "y": "distance_km", "color": "sport"},
        options={"stack": True},
    )
    return _render(request, chart_data((DAY, KM, SPORT), rows)), len(rows)


def _hbar() -> tuple[str, int]:
    rows = [(f"Run {i:02d}", 3.0 + ((i * 7) % 19)) for i in range(20)]
    request = chart_request(
        "hbar", title="Distance", channels={"y": "name", "x": "distance_km"}
    )
    columns = (column("name", ValueKind.CATEGORY), KM)
    return _render(request, chart_data(columns, rows)), len(rows)


def _scatter() -> tuple[str, int]:
    rows = [
        (
            1.0 + ((i * 37) % 500) / 10,
            20.0 + ((i * 53) % 311) / 7 + i / 50,
            SPORTS[i % 3],
        )
        for i in range(500)
    ]
    columns = (
        column("distance_km", unit="km"),
        column("elevation_m", unit="m"),
        SPORT,
    )
    request = chart_request(
        "scatter",
        title="Elevation",
        channels={"x": "distance_km", "y": "elevation_m", "color": "sport"},
        options={"trend": True},
    )
    return _render(request, chart_data(columns, rows)), len(rows)


def _histogram() -> tuple[str, int]:
    rows = [(1.0 + ((i * 37) % 1000) / 50,) for i in range(1000)]
    request = chart_request(
        "histogram", title="Distances", channels={"x": "distance_km"}
    )
    return _render(request, chart_data((KM,), rows)), len(rows)


def _table() -> tuple[str, int]:
    columns = (
        DAY,
        column("run_name", ValueKind.CATEGORY),
        KM,
        column("elapsed", ValueKind.DURATION),
        column("hr_bpm", unit="bpm"),
    )
    rows = [
        (
            START + timedelta(days=i),
            f"Run number {i}",
            5.0 + i / 3,
            timedelta(seconds=1800 + i * 61),
            140 + i,
        )
        for i in range(20)
    ]
    return _render(
        chart_request("table", title="Workouts"), chart_data(columns, rows)
    ), 20


def _stat() -> tuple[str, int]:
    columns = (KM, column("prior_km", unit="km"))
    request = chart_request(
        "stat",
        title="Weekly distance",
        channels={"value": "distance_km", "compare": "prior_km"},
    )
    return _render(request, chart_data(columns, [(42.5, 40.0)])), 1


#: name -> (builder, byte budget). hbar 20 bars was RAISED from the design's
#: 8,000 to 13,400 by controller ruling (measured 10,689). The others are the
#: design's budgets, or were lowered to measured + 25% where the measured
#: headroom exceeded 40% (lowered from bar 12,000, histogram 8,000, table
#: 3,000, stat 200).
TYPICAL: dict[str, tuple[Callable[[], tuple[str, int]], int]] = {
    "line 3x365 with a gap": (_line, 24_000),
    "area stacked 3x52": (_area_stacked, 14_000),
    "bar 52 dated": (_bar, 9_424),
    "bar stacked 52x3": (_bar_stacked, 22_000),
    "hbar 20 bars": (_hbar, 13_400),
    "scatter 500 in 3 series with trend": (_scatter, 18_000),
    "histogram of 1000": (_histogram, 5_774),
    "table 20x5": (_table, 1_390),
    "stat": (_stat, 62),
}


@pytest.mark.parametrize("name", list(TYPICAL))
def test_typical_chart_fits_its_budget(name: str) -> None:
    build, budget = TYPICAL[name]
    text, rows = build()
    assert len(text.encode()) <= budget, f"{name}: {len(text.encode())} > {budget}"
    # The fixture carries its full row count into the chart's own description.
    if name != "stat" and not name.startswith("table"):
        assert f" {rows} rows" in text, name


# --- the no-data state and the at-bound ceiling ---------------------------------

# Lowered from the design's 3,000 to 739 (worst measured 591, plus 25%).
NO_DATA_BUDGET = 739
AT_BOUND_CEILING = 80_000


def _kind_cases() -> list[tuple[str, tuple[Case, ...]]]:
    return [
        (
            spec.name,
            importlib.import_module(
                f"tests.render.charts.kit.test_{spec.name.replace('-', '_')}"
            ).CASES,
        )
        for spec in KINDS
    ]


def test_no_data_state_fits_its_budget() -> None:
    from fitdocs.render.charts.kit.registry import kind_named

    checked = 0
    for name, cases in _kind_cases():
        spec = kind_named(name)
        assert spec is not None
        if spec.output is not Output.SVG:
            continue
        (empty,) = [c for c in cases if c.name == "empty"]
        text = _render(empty.request, empty.data)
        assert "No data" in text, name
        assert len(text.encode()) <= NO_DATA_BUDGET, name
        checked += 1
    assert checked == sum(1 for s in KINDS if s.output is Output.SVG) >= 6


def test_every_at_bound_golden_is_under_the_ceiling() -> None:
    expected = [
        name
        for name, cases in _kind_cases()
        if any(c.name == "at_bound" for c in cases)
    ]
    found = sorted(GOLDEN_ROOT.glob("*/at_bound.*"))
    assert sorted(p.parent.name for p in found) == sorted(expected)
    assert len(found) >= 7
    for path in found:
        size = path.stat().st_size
        assert size > 1_000, path  # a bound-sized golden, not a stub
        assert size <= AT_BOUND_CEILING, f"{path}: {size} > {AT_BOUND_CEILING}"
