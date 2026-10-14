"""Windowed maximum-heart-rate evidence from synthetic session peaks."""

from datetime import date
from math import inf, nextafter

import pytest

from fitdocs.hr_benchmarks.maximum import max_evidence
from fitdocs.hr_benchmarks.types import Evidence
from tests.hr_benchmarks.builders import session_peak


@pytest.mark.parametrize("count", [0, 1, 2])
def test_fewer_than_three_sessions_gives_no_default(count: int) -> None:
    sessions = [
        session_peak(date(2024, 6, 1), f"workouts/{i}.md", 180.0 + i)
        for i in range(count)
    ]
    assert max_evidence(sessions) == ()


def test_unsorted_ranked_peaks_and_leave_day_lowering() -> None:
    sessions = [
        session_peak(date(2024, 1, 3), "workouts/fourth.md", 186.0),
        session_peak(date(2024, 1, 1), "workouts/median.md", 187.2),
        session_peak(date(2024, 1, 3), "workouts/lowest.md", 181.1),
        session_peak(date(2024, 1, 2), "workouts/highest.md", 189.4),
    ]
    assert (
        [s.day for s in sessions] != sorted(s.day for s in sessions)
        and len({s.day for s in sessions}) < len(sessions)
        and max_evidence(sessions)
        == (
            Evidence(
                date(2024, 1, 3),
                187,
                "workouts",
                "workouts/median.md",
                None,
                "median of the three highest 30-second "
                "sustained peaks (189.4, 187.2, 186.0 bpm)"
                " among 4 sessions dated 2023-01-04 to 2024-01-03",
                "workout heart rate, 365 days ending 2024-01-03",
            ),
            Evidence(
                date(2024, 12, 31),
                186,
                "workouts",
                "workouts/fourth.md",
                None,
                "median of the three highest 30-second "
                "sustained peaks (189.4, 186.0, 181.1 bpm)"
                " among 3 sessions dated 2024-01-02 to 2024-12-31",
                "workout heart rate, 365 days ending 2024-12-31",
            ),
        )
    )


def test_window_includes_364_day_old_session_but_excludes_365() -> None:
    sessions = [
        session_peak(date(2023, 12, 31), "workouts/low.md", 189.1),
        session_peak(date(2023, 1, 1), "workouts/old.md", 219.1),
        session_peak(date(2023, 12, 31), "workouts/current.md", 209.1),
        session_peak(date(2023, 12, 31), "workouts/next.md", 199.1),
    ]
    assert max_evidence(sessions) == (
        Evidence(
            date(2023, 12, 31),
            209,
            "workouts",
            "workouts/current.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (219.1, 209.1, 199.1 bpm)"
            " among 4 sessions dated 2023-01-01 to 2023-12-31",
            "workout heart rate, 365 days ending 2023-12-31",
        ),
        Evidence(
            date(2024, 1, 1),
            199,
            "workouts",
            "workouts/next.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (209.1, 199.1, 189.1 bpm)"
            " among 3 sessions dated 2023-01-02 to 2024-01-01",
            "workout heart rate, 365 days ending 2024-01-01",
        ),
    )


def test_future_session_does_not_supply_earlier_evidence() -> None:
    sessions = [
        session_peak(date(2024, 1, 10), "workouts/future.md", 213.0),
        session_peak(date(2024, 1, 1), "workouts/first.md", 163.0),
        session_peak(date(2024, 1, 2), "workouts/second.md", 173.0),
    ]
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 1, 10),
            173,
            "workouts",
            "workouts/second.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (213.0, 173.0, 163.0 bpm)"
            " among 3 sessions dated 2023-01-11 to 2024-01-10",
            "workout heart rate, 365 days ending 2024-01-10",
        ),
    )


def test_halfway_rounds_up_and_same_day_candidates_are_unique() -> None:
    sessions = [
        session_peak(date(2024, 6, 7), "workouts/low.md", 171.25),
        session_peak(date(2024, 6, 7), "workouts/high.md", 193.75),
        session_peak(date(2024, 6, 7), "workouts/half.md", 182.5),
    ]
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 6, 7),
            183,
            "workouts",
            "workouts/half.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (193.8, 182.5, 171.2 bpm)"
            " among 3 sessions dated 2023-06-09 to 2024-06-07",
            "workout heart rate, 365 days ending 2024-06-07",
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_tied_peak_uses_date_before_document(reverse: bool) -> None:
    sessions = [
        session_peak(date(2024, 2, 3), "workouts/high.md", 204.0),
        session_peak(date(2024, 2, 2), "workouts/a-later.md", 194.0),
        session_peak(date(2024, 2, 1), "workouts/z-earlier.md", 194.0),
    ]
    if reverse:
        sessions.reverse()
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 2, 3),
            194,
            "workouts",
            "workouts/z-earlier.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (204.0, 194.0, 194.0 bpm)"
            " among 3 sessions dated 2023-02-04 to 2024-02-03",
            "workout heart rate, 365 days ending 2024-02-03",
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_tied_peak_and_day_uses_document(reverse: bool) -> None:
    sessions = [
        session_peak(date(2024, 3, 4), "workouts/high.md", 207.0),
        session_peak(date(2024, 3, 4), "workouts/z-last.md", 197.0),
        session_peak(date(2024, 3, 4), "workouts/a-first.md", 197.0),
    ]
    if reverse:
        sessions.reverse()
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 3, 4),
            197,
            "workouts",
            "workouts/a-first.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (207.0, 197.0, 197.0 bpm)"
            " among 3 sessions dated 2023-03-06 to 2024-03-04",
            "workout heart rate, 365 days ending 2024-03-04",
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_distinct_raw_peaks_in_same_display_bucket_keep_median_page(
    reverse: bool,
) -> None:
    sessions = [
        session_peak(date(2024, 2, 3), "workouts/high.md", 190.9),
        session_peak(date(2024, 2, 2), "workouts/a-median.md", 180.44),
        session_peak(date(2024, 2, 1), "workouts/z-low.md", 180.43),
    ]
    if reverse:
        sessions.reverse()
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 2, 3),
            180,
            "workouts",
            "workouts/a-median.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (190.9, 180.4, 180.4 bpm)"
            " among 3 sessions dated 2023-02-04 to 2024-02-03",
            "workout heart rate, 365 days ending 2024-02-03",
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_raw_median_below_half_boundary_rounds_down(reverse: bool) -> None:
    sessions = [
        session_peak(date(2024, 6, 7), "workouts/high.md", 190.9),
        session_peak(date(2024, 6, 6), "workouts/median.md", 180.49),
        session_peak(date(2024, 6, 5), "workouts/low.md", 170.2),
    ]
    if reverse:
        sessions.reverse()
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 6, 7),
            180,
            "workouts",
            "workouts/median.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (190.9, 180.5, 170.2 bpm)"
            " among 3 sessions dated 2023-06-09 to 2024-06-07",
            "workout heart rate, 365 days ending 2024-06-07",
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_adjacent_raw_peaks_keep_the_later_median_page(reverse: bool) -> None:
    sessions = [
        session_peak(date(2024, 4, 3), "workouts/high.md", 190.9),
        session_peak(
            date(2024, 4, 2), "workouts/a-adjacent-median.md", nextafter(31.4, inf)
        ),
        session_peak(date(2024, 4, 1), "workouts/z-low.md", 31.4),
    ]
    if reverse:
        sessions.reverse()
    assert max_evidence(sessions) == (
        Evidence(
            date(2024, 4, 3),
            31,
            "workouts",
            "workouts/a-adjacent-median.md",
            None,
            "median of the three highest 30-second "
            "sustained peaks (190.9, 31.4, 31.4 bpm)"
            " among 3 sessions dated 2023-04-05 to 2024-04-03",
            "workout heart rate, 365 days ending 2024-04-03",
        ),
    )
