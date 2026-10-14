"""Synthetic per-source daily resting-heart-rate evidence."""

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import pytest

from fitdocs.hr_benchmarks.resting import resting_evidence
from fitdocs.hr_benchmarks.types import Evidence


def _days(start: date, readings: Sequence[float]) -> dict[date, float]:
    return {start + timedelta(days=i): value for i, value in enumerate(readings)}


def _run(
    values: Mapping[str, Mapping[date, float]], order: Sequence[str] = ()
) -> tuple[Evidence, ...]:
    return resting_evidence(
        values,
        order=order,
        series_metric="supplied_metric",
        document_for_year=lambda year: f"injected-pages/{year}.csv",
    )


@pytest.mark.parametrize("values", [{}, {"empty": {}}, {"a": {}, "b": {}}])
def test_empty_sources_supply_no_default(
    values: dict[str, dict[date, float]],
) -> None:
    assert _run(values) == ()


@pytest.mark.parametrize("count", [1, 7, 13])
def test_unformed_source_supplies_no_default(count: int) -> None:
    assert _run({"watch": _days(date(2024, 1, 1), [61.0] * count)}) == ()


def test_fourteen_values_form_on_the_fourteenth_day() -> None:
    assert _run({"watch": _days(date(2024, 1, 1), [61.0] * 14)}) == (
        Evidence(
            date(2024, 1, 14),
            61,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-14",
            "watch resting heart rate, 28-day median",
        ),
    )


def test_inclusive_window_excludes_day_28_and_drops_below_minimum() -> None:
    values = {
        "watch": {
            date(2023, 12, 31): 210.0,
            date(2024, 1, 1): 90.0,
            **_days(date(2024, 1, 16), [40.0] * 6 + [60.0] * 7),
        },
        "decoy": {date(2024, 1, 30): 111.0},
    }
    assert _run(values, ("watch", "decoy")) == (
        Evidence(
            date(2024, 1, 27),
            60,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-27",
            "watch resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 28),
            60,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-28",
            "watch resting heart rate, 28-day median",
        ),
    )


def test_calendar_gap_keeps_baseline_and_stops_at_global_latest_day() -> None:
    assert _run(
        {
            "watch": _days(date(2024, 1, 1), [67.0] * 14),
            "decoy": {date(2024, 1, 16): 100.0},
        }
    ) == (
        Evidence(
            date(2024, 1, 14),
            67,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-14",
            "watch resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 15),
            67,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-15",
            "watch resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 16),
            67,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-16",
            "watch resting heart rate, 28-day median",
        ),
    )


def test_configured_rank_falls_back_then_wins_back_without_current_value() -> None:
    values = {
        "a-low": _days(date(2024, 1, 1), [45.0] * 7 + [58.0] * 7),
        "z-high": _days(date(2024, 1, 2), [75.0] * 7 + [88.0] * 7),
        "decoy": {date(2024, 1, 16): 110.0},
    }
    assert _run(values, ("absent", "z-high", "a-low")) == (
        Evidence(
            date(2024, 1, 14),
            52,
            "a-low",
            "injected-pages/2024.csv",
            "a-low:supplied_metric",
            "median of 14 daily values from a-low on the 28 days ending 2024-01-14",
            "a-low resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 15),
            82,
            "z-high",
            "injected-pages/2024.csv",
            "z-high:supplied_metric",
            "median of 14 daily values from z-high on the 28 days ending 2024-01-15",
            "z-high resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 16),
            82,
            "z-high",
            "injected-pages/2024.csv",
            "z-high:supplied_metric",
            "median of 14 daily values from z-high on the 28 days ending 2024-01-16",
            "z-high resting heart rate, 28-day median",
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_unknown_sources_are_ranked_by_id(reverse: bool) -> None:
    values = {
        "z": _days(date(2024, 1, 1), [99.0] * 14),
        "m": _days(date(2024, 1, 1), [71.0] * 14),
        "a": _days(date(2024, 1, 1), [63.0] * 14),
    }
    if reverse:
        values = dict(reversed(values.items()))
    assert _run(values, ("absent",)) == (
        Evidence(
            date(2024, 1, 14),
            63,
            "a",
            "injected-pages/2024.csv",
            "a:supplied_metric",
            "median of 14 daily values from a on the 28 days ending 2024-01-14",
            "a resting heart rate, 28-day median",
        ),
    )


def test_two_unformed_sources_are_not_pooled() -> None:
    assert (
        _run(
            {
                "a": _days(date(2024, 1, 1), [51.0] * 7),
                "b": _days(date(2024, 1, 8), [91.0] * 7),
            }
        )
        == ()
    )


def test_configured_source_precedes_lexically_earlier_unlisted_source() -> None:
    assert _run(
        {
            "a-unlisted": _days(date(2024, 1, 1), [93.0] * 14),
            "z-configured": _days(date(2024, 1, 1), [53.0] * 14),
        },
        ("z-configured",),
    ) == (
        Evidence(
            date(2024, 1, 14),
            53,
            "z-configured",
            "injected-pages/2024.csv",
            "z-configured:supplied_metric",
            "median of 14 daily values from z-configured "
            "on the 28 days ending 2024-01-14",
            "z-configured resting heart rate, 28-day median",
        ),
    )


def test_formed_sources_keep_their_own_unadjusted_values() -> None:
    assert _run(
        {
            "a": _days(date(2024, 1, 1), [51.0] * 14),
            "b": _days(date(2024, 1, 1), [91.0] * 14),
        },
        ("a", "b"),
    ) == (
        Evidence(
            date(2024, 1, 14),
            51,
            "a",
            "injected-pages/2024.csv",
            "a:supplied_metric",
            "median of 14 daily values from a on the 28 days ending 2024-01-14",
            "a resting heart rate, 28-day median",
        ),
    )


def test_even_median_differs_from_mean() -> None:
    assert _run(
        {
            "watch": _days(
                date(2024, 1, 1),
                [40.0] * 7 + [60.0] * 6 + [200.0],
            )
        }
    ) == (
        Evidence(
            date(2024, 1, 14),
            50,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-14",
            "watch resting heart rate, 28-day median",
        ),
    )


def test_odd_median_uses_middle_value() -> None:
    assert _run(
        {
            "watch": _days(
                date(2024, 1, 1),
                [40.0] * 7 + [80.0] * 7 + [61.5],
            )
        }
    ) == (
        Evidence(
            date(2024, 1, 14),
            60,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-14",
            "watch resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 15),
            62,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 15 daily values from watch on the 28 days ending 2024-01-15",
            "watch resting heart rate, 28-day median",
        ),
    )


@pytest.mark.parametrize("raw,whole", [(50.5, 51), (50.49, 50)])
def test_rounds_raw_median_once_half_up(raw: float, whole: int) -> None:
    assert _run({"watch": _days(date(2024, 1, 1), [raw] * 14)}) == (
        Evidence(
            date(2024, 1, 14),
            whole,
            "watch",
            "injected-pages/2024.csv",
            "watch:supplied_metric",
            "median of 14 daily values from watch on the 28 days ending 2024-01-14",
            "watch resting heart rate, 28-day median",
        ),
    )


def test_document_year_follows_evidence_day_across_year_boundary() -> None:
    assert _run(
        {
            "a": _days(date(2023, 12, 18), [57.5] * 14),
            "b": {date(2024, 1, 2): 110.0},
        },
        ("a", "b"),
    ) == (
        Evidence(
            date(2023, 12, 31),
            58,
            "a",
            "injected-pages/2023.csv",
            "a:supplied_metric",
            "median of 14 daily values from a on the 28 days ending 2023-12-31",
            "a resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 1),
            58,
            "a",
            "injected-pages/2024.csv",
            "a:supplied_metric",
            "median of 14 daily values from a on the 28 days ending 2024-01-01",
            "a resting heart rate, 28-day median",
        ),
        Evidence(
            date(2024, 1, 2),
            58,
            "a",
            "injected-pages/2024.csv",
            "a:supplied_metric",
            "median of 14 daily values from a on the 28 days ending 2024-01-02",
            "a resting heart rate, 28-day median",
        ),
    )
