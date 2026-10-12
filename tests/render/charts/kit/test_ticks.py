"""Tests for the kit's pure tick arithmetic (chart-kit Req 6.2)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.ticks import (
    CLOCK_STEPS,
    DECIMAL_MANTISSAS,
    DURATION_STEPS,
    LOG_DURATION_TICKS,
    CalendarStep,
    calendar_ticks,
    clock_ticks,
    linear_ticks,
    log_ticks,
    nice_step,
)

DAY = 86400.0


# ---------------------------------------------------------------- constants


def test_ladder_constants_are_pinned() -> None:
    assert DECIMAL_MANTISSAS == (1.0, 2.0, 5.0)
    assert DURATION_STEPS == (
        1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800,
        3600, 7200, 10800, 21600, 43200, 86400,
    )  # fmt: skip
    assert LOG_DURATION_TICKS == (
        1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800,
        3600, 7200, 10800, 21600, 43200, 86400,
    )  # fmt: skip
    assert CLOCK_STEPS == (60, 300, 900, 1800, 3600, 7200, 10800, 21600, 43200)


def test_calendar_step_members_are_pinned() -> None:
    assert [(m.name, m.value) for m in CalendarStep] == [
        ("DAY", "day"),
        ("TWO_DAYS", "2day"),
        ("WEEK", "week"),
        ("MONTH", "month"),
        ("QUARTER", "quarter"),
        ("HALF", "half"),
        ("YEAR", "year"),
        ("YEARS_2", "2year"),
        ("YEARS_5", "5year"),
        ("YEARS_10", "10year"),
    ]


# ---------------------------------------------------------------- nice_step


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.0003, 0.0005),
        (0.05, 0.05),
        (0.07, 0.1),
        (0.15, 0.2),
        (1.0, 1.0),
        (1.3, 2.0),
        (2.0, 2.0),
        (3.0, 5.0),
        (5.0, 5.0),
        (5.1, 10.0),
        (37.0, 50.0),
        (480.0, 500.0),
        (6685.7, 10000.0),
    ],
)
def test_nice_step_decimal_is_smallest_ladder_step_at_least_raw(
    raw: float, expected: float
) -> None:
    assert nice_step(raw, duration=False) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.2, 1.0),
        (1.0, 1.0),
        (1.5, 2.0),
        (3.0, 5.0),
        (7.0, 10.0),
        (11.0, 15.0),
        (31.0, 60.0),
        (61.0, 120.0),
        (301.0, 600.0),
        (601.0, 900.0),
        (901.0, 1800.0),
        (1801.0, 3600.0),
        (3601.0, 7200.0),
        (7201.0, 10800.0),
        (10801.0, 21600.0),
        (21601.0, 43200.0),
        (43201.0, 86400.0),
        (86400.0, 86400.0),
        (86401.0, 172800.0),
        (172801.0, 432000.0),
        (432001.0, 864000.0),
        (864001.0, 1728000.0),
    ],
)
def test_nice_step_duration_walks_the_ladder_then_days(
    raw: float, expected: float
) -> None:
    assert nice_step(raw, duration=True) == expected


def test_nice_step_tolerates_float_noise_just_above_a_ladder_step() -> None:
    noisy = 1.0 + 2.0**-52
    assert noisy > 1.0
    assert nice_step(noisy, duration=False) == 1.0
    assert nice_step(0.1 + 0.2 - 0.2, duration=False) == 0.1


@pytest.mark.parametrize(
    ("bad", "match"),
    [(0.0, "positive"), (-1.0, "positive"), (math.nan, "finite"), (math.inf, "finite")],
)
def test_nice_step_rejects_non_positive_and_non_finite(bad: float, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        nice_step(bad, duration=False)


# ------------------------------------------------------------- linear_ticks


def test_linear_decimal_spans_give_niced_domains_and_steps() -> None:
    assert linear_ticks(0, 9.3, 8, duration=False) == (
        0.0,
        10.0,
        (0.0, 2.0, 4.0, 6.0, 8.0, 10.0),
    )
    assert linear_ticks(-4.2, 17, 8, duration=False) == (
        -5.0,
        20.0,
        (-5.0, 0.0, 5.0, 10.0, 15.0, 20.0),
    )
    assert linear_ticks(0.012, 0.087, 8, duration=False) == (
        0.0,
        0.1,
        (0.0, 0.02, 0.04, 0.06, 0.08, 0.1),
    )
    assert linear_ticks(1200, 48000, 8, duration=False) == (
        0.0,
        50000.0,
        (0.0, 10000.0, 20000.0, 30000.0, 40000.0, 50000.0),
    )


def test_linear_outer_edge_rounds_up_not_down() -> None:
    # 9.3 is no multiple of a candidate step: the upper edge is 10, not 8 or 9.
    lo, hi, ticks = linear_ticks(0, 9.3, 11, duration=False)
    assert (lo, hi) == (0.0, 10.0)
    assert ticks[-1] == 10.0
    # and the lower edge rounds down
    lo2, _, ticks2 = linear_ticks(-4.2, 17, 8, duration=False)
    assert lo2 == -5.0
    assert ticks2[0] == -5.0


def test_linear_domain_encloses_data_for_every_span() -> None:
    for lo, hi in ((0, 9.3), (-4.2, 17), (0.012, 0.087), (1200, 48000), (3.3, 3.4)):
        for max_count in (3, 5, 8, 12):
            d_lo, d_hi, ticks = linear_ticks(lo, hi, max_count, duration=False)
            assert d_lo <= lo
            assert d_hi >= hi
            assert (ticks[0], ticks[-1]) == (d_lo, d_hi)


def test_linear_range_straddling_zero_needs_three_ticks_even_when_asked_for_two() -> (
    None
):
    assert linear_ticks(-4.2, 17, 2, duration=False) == (
        -20.0,
        20.0,
        (-20.0, 0.0, 20.0),
    )
    assert linear_ticks(-4.2, 17, 3, duration=False) == (
        -20.0,
        20.0,
        (-20.0, 0.0, 20.0),
    )
    # a range that does not straddle zero honours two
    assert linear_ticks(1, 17, 2, duration=False) == (0.0, 20.0, (0.0, 20.0))
    assert linear_ticks(-17, -1, 2, duration=False) == (-20.0, 0.0, (-20.0, 0.0))


def test_linear_steps_up_when_the_first_candidate_overflows_max_count() -> None:
    # raw step 0.84 -> candidate 1 gives 0..6 = 7 ticks > 6, so step 2 is chosen.
    assert linear_ticks(0.9, 5.1, 6, duration=False) == (0.0, 6.0, (0.0, 2.0, 4.0, 6.0))


def test_linear_float_noise_does_not_push_the_edge_out() -> None:
    # 0.3 / 0.1 == 2.9999999999999996: without tolerance the domain would start at 0.2.
    assert linear_ticks(0.3, 0.9, 7, duration=False) == (
        0.3,
        0.9,
        (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
    )


def test_linear_integer_option_forbids_fractional_steps() -> None:
    assert linear_ticks(0, 3, 8, duration=False, integer=True) == (
        0.0,
        3.0,
        (0.0, 1.0, 2.0, 3.0),
    )
    assert linear_ticks(0, 3, 8, duration=False, integer=False) == (
        0.0,
        3.0,
        (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0),
    )
    # integer defaults to False
    assert linear_ticks(0, 3, 8, duration=False) == linear_ticks(
        0, 3, 8, duration=False, integer=False
    )


def test_linear_integer_option_keeps_larger_ladder_steps() -> None:
    assert linear_ticks(0, 47, 6, duration=False, integer=True) == (
        0.0,
        50.0,
        (0.0, 10.0, 20.0, 30.0, 40.0, 50.0),
    )


def test_linear_duration_spans_use_minute_steps() -> None:
    assert linear_ticks(0, 5400, 10, duration=True) == (
        0.0,
        5400.0,
        (0.0, 600.0, 1200.0, 1800.0, 2400.0, 3000.0, 3600.0, 4200.0, 4800.0, 5400.0),
    )
    assert linear_ticks(0, 5400, 8, duration=True) == (
        0.0,
        5400.0,
        (0.0, 900.0, 1800.0, 2700.0, 3600.0, 4500.0, 5400.0),
    )


def test_linear_duration_never_steps_below_one_second() -> None:
    # a decimal ladder would pick 0.5 here
    assert linear_ticks(0, 3, 10, duration=True) == (0.0, 3.0, (0.0, 1.0, 2.0, 3.0))
    assert linear_ticks(0.2, 0.8, 10, duration=True) == (0.0, 1.0, (0.0, 1.0))


def test_linear_duration_two_day_spans_move_to_day_steps() -> None:
    assert linear_ticks(0, 2 * DAY, 3, duration=True) == (
        0.0,
        2 * DAY,
        (0.0, DAY, 2 * DAY),
    )
    assert linear_ticks(0, 10 * DAY, 12, duration=True) == (
        0.0,
        10 * DAY,
        tuple(i * DAY for i in range(11)),
    )
    # beyond a day the ladder continues 1, 2, 5 x 10^k days
    assert linear_ticks(0, 10 * DAY, 6, duration=True) == (
        0.0,
        10 * DAY,
        (0.0, 2 * DAY, 4 * DAY, 6 * DAY, 8 * DAY, 10 * DAY),
    )


def test_linear_zero_is_a_real_edge_not_absent() -> None:
    assert linear_ticks(-3, 0, 5, duration=False) == (
        -3.0,
        0.0,
        (-3.0, -2.0, -1.0, 0.0),
    )
    assert linear_ticks(0, 0.5, 6, duration=False) == (
        0.0,
        0.5,
        (0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
    )


@pytest.mark.parametrize(
    ("lo", "hi", "max_count", "match"),
    [
        (1, 1, 5, "lo < hi"),
        (2, 1, 5, "lo < hi"),
        (0, 1, 1, "max_count"),
        (0, math.inf, 5, "finite"),
        (math.nan, 1, 5, "finite"),
    ],
)
def test_linear_rejects_degenerate_input(
    lo: float, hi: float, max_count: int, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        linear_ticks(lo, hi, max_count, duration=False)


# ---------------------------------------------------------------- log_ticks


def test_log_three_or_more_decades_use_decades_only() -> None:
    assert log_ticks(1, 1000, 10, duration=False) == (
        1.0,
        1000.0,
        (1.0, 10.0, 100.0, 1000.0),
    )
    assert log_ticks(3, 40000, 10, duration=False) == (
        1.0,
        100000.0,
        (1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0),
    )
    assert log_ticks(0.002, 0.3, 10, duration=False) == (
        0.001,
        1.0,
        (0.001, 0.01, 0.1, 1.0),
    )


def test_log_decade_edges_survive_float_log10_rounding() -> None:
    # log10 of both values is exactly 3.0, yet one lies below 1000 and one above.
    below, above = 999.9999999999999, 1000.0000000000001
    assert math.log10(below) == 3.0
    assert math.log10(above) == 3.0
    assert log_ticks(below, 1e6, 10, duration=False) == (
        100.0,
        1e6,
        (100.0, 1e3, 1e4, 1e5, 1e6),
    )
    assert log_ticks(1, above, 10, duration=False) == (
        1.0,
        1e4,
        (1.0, 10.0, 100.0, 1e3, 1e4),
    )


def test_log_under_three_decades_adds_two_and_five() -> None:
    assert log_ticks(1, 100, 10, duration=False) == (
        1.0,
        100.0,
        (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0),
    )
    # the domain runs from the largest tick <= min to the smallest tick >= max
    assert log_ticks(3, 40, 10, duration=False) == (
        2.0,
        50.0,
        (2.0, 5.0, 10.0, 20.0, 50.0),
    )
    assert log_ticks(0.03, 0.8, 10, duration=False) == (
        0.02,
        1.0,
        (0.02, 0.05, 0.1, 0.2, 0.5, 1.0),
    )


def test_log_decades_are_thinned_to_max_count_keeping_every_kth() -> None:
    domain_lo, domain_hi, ticks = log_ticks(1, 1e12, 5, duration=False)
    assert (domain_lo, domain_hi) == (1.0, 1e12)
    assert ticks == (1.0, 1e3, 1e6, 1e9, 1e12)


def test_log_duration_between_5s_and_2h_includes_one_and_twenty_minutes() -> None:
    lo, hi, ticks = log_ticks(5, 7200, 12, duration=True)
    assert (lo, hi) == (5.0, 7200.0)
    assert ticks == (
        5.0,
        10.0,
        15.0,
        30.0,
        60.0,
        120.0,
        300.0,
        600.0,
        1200.0,
        1800.0,
        3600.0,
        7200.0,
    )
    assert 60.0 in ticks
    assert 1200.0 in ticks


def test_log_duration_domain_snaps_outward_to_ladder_ticks() -> None:
    lo, hi, ticks = log_ticks(7, 4000, 12, duration=True)
    assert (lo, hi) == (5.0, 7200.0)
    assert ticks == (
        5.0,
        10.0,
        15.0,
        30.0,
        60.0,
        120.0,
        300.0,
        600.0,
        1200.0,
        1800.0,
        3600.0,
        7200.0,
    )


def test_log_duration_thins_to_max_count_keeping_every_kth() -> None:
    lo, hi, ticks = log_ticks(5, 7200, 6, duration=True)
    assert (lo, hi) == (5.0, 7200.0)
    assert ticks == (5.0, 15.0, 60.0, 300.0, 1200.0, 3600.0)


def test_log_duration_continues_in_decimal_days() -> None:
    lo, hi, ticks = log_ticks(3600, 1_500_000, 20, duration=True)
    assert (lo, hi) == (3600.0, 1_728_000.0)
    assert ticks == (
        3600.0, 7200.0, 10800.0, 21600.0, 43200.0, 86400.0,
        172800.0, 432000.0, 864000.0, 1728000.0,
    )  # fmt: skip


def test_log_duration_below_one_second_continues_the_decimal_ladder() -> None:
    assert log_ticks(0.3, 4, 10, duration=True) == (0.2, 5.0, (0.2, 0.5, 1.0, 2.0, 5.0))


@pytest.mark.parametrize(
    ("lo", "hi", "max_count", "match"),
    [
        (0, 5, 5, "0 < lo < hi"),
        (-1, 5, 5, "0 < lo < hi"),
        (2, 2, 5, "0 < lo < hi"),
        (5, 2, 5, "0 < lo < hi"),
        (1, 10, 1, "max_count"),
        (1, math.inf, 5, "finite"),
    ],
)
def test_log_rejects_degenerate_input(
    lo: float, hi: float, max_count: int, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        log_ticks(lo, hi, max_count, duration=False)


# ----------------------------------------------------------- calendar_ticks


def test_calendar_ten_day_span_uses_day_then_two_day_steps() -> None:
    first, last = date(2026, 3, 4), date(2026, 3, 13)
    step, ticks = calendar_ticks(first, last, 10)
    assert step is CalendarStep.DAY
    assert ticks == tuple(first + timedelta(days=i) for i in range(10))
    step, ticks = calendar_ticks(first, last, 6)
    assert step is CalendarStep.TWO_DAYS
    assert ticks == (
        date(2026, 3, 5),
        date(2026, 3, 7),
        date(2026, 3, 9),
        date(2026, 3, 11),
        date(2026, 3, 13),
    )


def test_calendar_nine_weeks_tick_on_mondays() -> None:
    step, ticks = calendar_ticks(date(2026, 1, 7), date(2026, 3, 10), 10)
    assert step is CalendarStep.WEEK
    assert ticks == (
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
        date(2026, 2, 2),
        date(2026, 2, 9),
        date(2026, 2, 16),
        date(2026, 2, 23),
        date(2026, 3, 2),
        date(2026, 3, 9),
    )
    assert {d.weekday() for d in ticks} == {0}


def test_calendar_ticks_are_inclusive_of_both_ends() -> None:
    step, ticks = calendar_ticks(date(2026, 3, 2), date(2026, 3, 16), 3)
    assert step is CalendarStep.WEEK
    assert ticks == (date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16))


def test_calendar_fourteen_months_use_months_or_quarters() -> None:
    first, last = date(2025, 1, 15), date(2026, 3, 14)
    step, ticks = calendar_ticks(first, last, 14)
    assert step is CalendarStep.MONTH
    assert ticks == (
        date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1), date(2025, 5, 1),
        date(2025, 6, 1), date(2025, 7, 1), date(2025, 8, 1), date(2025, 9, 1),
        date(2025, 10, 1), date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1),
        date(2026, 2, 1), date(2026, 3, 1),
    )  # fmt: skip
    step, ticks = calendar_ticks(first, last, 8)
    assert step is CalendarStep.QUARTER
    assert ticks == (
        date(2025, 4, 1),
        date(2025, 7, 1),
        date(2025, 10, 1),
        date(2026, 1, 1),
    )


def test_calendar_month_and_year_ticks_on_either_end_are_included() -> None:
    assert calendar_ticks(date(2026, 1, 1), date(2026, 3, 1), 3) == (
        CalendarStep.MONTH,
        (date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)),
    )
    step, ticks = calendar_ticks(date(2020, 1, 1), date(2026, 1, 1), 7)
    assert step is CalendarStep.YEAR
    assert ticks == tuple(date(y, 1, 1) for y in range(2020, 2027))


def test_calendar_three_years_use_half_years() -> None:
    step, ticks = calendar_ticks(date(2025, 1, 15), date(2027, 12, 20), 8)
    assert step is CalendarStep.HALF
    assert ticks == (
        date(2025, 7, 1),
        date(2026, 1, 1),
        date(2026, 7, 1),
        date(2027, 1, 1),
        date(2027, 7, 1),
    )


def test_calendar_six_years_use_years() -> None:
    step, ticks = calendar_ticks(date(2020, 6, 15), date(2026, 6, 14), 8)
    assert step is CalendarStep.YEAR
    assert ticks == tuple(date(y, 1, 1) for y in range(2021, 2027))


def test_calendar_multi_year_steps_use_multiples_of_the_step() -> None:
    step, ticks = calendar_ticks(date(2010, 6, 1), date(2025, 6, 1), 8)
    assert step is CalendarStep.YEARS_2
    assert ticks == tuple(date(y, 1, 1) for y in range(2012, 2026, 2))
    step, ticks = calendar_ticks(date(2000, 6, 1), date(2040, 6, 1), 8)
    assert step is CalendarStep.YEARS_5
    assert ticks == tuple(date(y, 1, 1) for y in range(2005, 2045, 5))
    step, ticks = calendar_ticks(date(1950, 6, 1), date(2020, 6, 1), 8)
    assert step is CalendarStep.YEARS_10
    assert ticks == tuple(date(y, 1, 1) for y in range(1960, 2030, 10))


def test_calendar_beyond_ten_year_steps_keeps_every_kth_to_fit() -> None:
    step, ticks = calendar_ticks(date(1900, 6, 1), date(2040, 6, 1), 8)
    assert step is CalendarStep.YEARS_10
    assert ticks == tuple(date(y, 1, 1) for y in range(1910, 2040, 20))


def test_calendar_single_day_span_has_one_day_tick() -> None:
    assert calendar_ticks(date(2026, 3, 4), date(2026, 3, 4), 5) == (
        CalendarStep.DAY,
        (date(2026, 3, 4),),
    )


def test_calendar_span_with_two_ticks_of_some_step_is_never_tickless() -> None:
    # Mondays Mar 2/9/16/23/30 overflow 4, months hold none: thin the weeks.
    assert calendar_ticks(date(2026, 3, 2), date(2026, 3, 30), 4) == (
        CalendarStep.WEEK,
        (date(2026, 3, 2), date(2026, 3, 16), date(2026, 3, 30)),
    )
    # days 6 and two-day ticks 3 overflow 2, weeks hold none: thin the two-day ticks.
    assert calendar_ticks(date(2026, 3, 3), date(2026, 3, 8), 2) == (
        CalendarStep.TWO_DAYS,
        (date(2026, 3, 3), date(2026, 3, 7)),
    )


def test_calendar_max_count_of_one_still_gets_two_ticks_when_the_span_holds_them() -> (
    None
):
    assert calendar_ticks(date(2026, 3, 3), date(2026, 3, 8), 1) == (
        CalendarStep.TWO_DAYS,
        (date(2026, 3, 3), date(2026, 3, 7)),
    )


def test_calendar_lone_tick_step_is_not_taken_over_a_thinned_finer_step() -> None:
    # Only one Monday (Mar 9) falls in the span, so weeks give a lone tick;
    # two-day ticks Mar 5/7/9/11/13 overflow 2 and are thinned to Mar 5 and 11.
    assert calendar_ticks(date(2026, 3, 4), date(2026, 3, 13), 2) == (
        CalendarStep.TWO_DAYS,
        (date(2026, 3, 5), date(2026, 3, 11)),
    )


@pytest.mark.parametrize(
    ("first", "last", "max_count", "match"),
    [
        (date(2026, 3, 5), date(2026, 3, 4), 5, "first <= last"),
        (date(2026, 3, 4), date(2026, 3, 5), 0, "max_count"),
    ],
)
def test_calendar_rejects_degenerate_input(
    first: date, last: date, max_count: int, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        calendar_ticks(first, last, max_count)


# -------------------------------------------------------------- clock_ticks


def test_clock_three_hour_span_aligns_to_midnight_multiples() -> None:
    # 09:10 to 12:10
    step, ticks = clock_ticks(33000, 43800, 8)
    assert step == 1800
    assert ticks == (34200.0, 36000.0, 37800.0, 39600.0, 41400.0, 43200.0)
    step, ticks = clock_ticks(33000, 43800, 12)
    assert step == 900
    assert ticks == (
        33300.0, 34200.0, 35100.0, 36000.0, 36900.0, 37800.0,
        38700.0, 39600.0, 40500.0, 41400.0, 42300.0, 43200.0,
    )  # fmt: skip


def test_clock_ticks_keep_alignment_across_midnight() -> None:
    step, ticks = clock_ticks(80000, 95000, 6)
    assert step == 3600
    assert ticks == (82800.0, 86400.0, 90000.0, 93600.0)


def test_clock_ticks_include_both_ends_when_they_fall_on_the_step() -> None:
    step, ticks = clock_ticks(0, 7200, 3)
    assert step == 3600
    assert ticks == (0.0, 3600.0, 7200.0)


def test_clock_under_two_days_uses_twelve_hour_steps_at_most() -> None:
    step, ticks = clock_ticks(0, 169200, 6)
    assert step == 43200
    assert ticks == (0.0, 43200.0, 86400.0, 129600.0)
    step, ticks = clock_ticks(0, 169200, 2)
    assert step == 43200
    assert ticks == (0.0, 86400.0)


def test_clock_span_shorter_than_a_step_has_no_ticks() -> None:
    assert clock_ticks(130, 150, 5) == (60, ())


def test_clock_span_with_two_ticks_of_some_step_is_never_tickless() -> None:
    # 60 s ticks 36060..36240 (4) overflow 2; 300 s ticks hold none: thin the minutes.
    assert clock_ticks(36010, 36250, 2) == (60, (36060.0, 36180.0))
    assert clock_ticks(36010, 36130, 1) == (60, (36060.0, 36120.0))
    # minute ticks 35940..36180 (5) overflow 2, 300 s ticks give the lone 36000
    assert clock_ticks(35910, 36210, 2) == (60, (35940.0, 36120.0))
    # an overflowing step is thinned to two ticks even when max_count is 1
    assert clock_ticks(36010, 36250, 1) == (60, (36060.0, 36180.0))


def test_clock_span_holding_one_or_no_tick_of_every_step_keeps_the_finest_step() -> (
    None
):
    assert clock_ticks(36010, 36050, 2) == (60, ())
    assert clock_ticks(36030, 36100, 5) == (60, (36060.0,))


@pytest.mark.parametrize(
    ("lo", "hi", "max_count", "match"),
    [
        (5, 4, 5, "lo <= hi"),
        (0, 100, 0, "max_count"),
        (0, math.inf, 5, "finite"),
    ],
)
def test_clock_rejects_degenerate_input(
    lo: float, hi: float, max_count: int, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        clock_ticks(lo, hi, max_count)


# --------------------------------------------------------------- max_count


@pytest.mark.parametrize("max_count", [2, 3, 4, 5, 6, 8, 10, 12])
def test_every_function_respects_max_count(max_count: int) -> None:
    spans = [(0, 9.3), (0.012, 0.087), (1200, 48000), (0.9, 5.1)]
    if max_count >= 3:  # a range straddling zero cannot be enclosed by two ticks
        spans.append((-4.2, 17))
    for lo, hi in spans:
        for duration in (False, True):
            assert (
                len(linear_ticks(lo, hi, max_count, duration=duration)[2]) <= max_count
            )
        assert (
            len(linear_ticks(lo, hi, max_count, duration=False, integer=True)[2])
            <= max_count
        )
    for lo, hi in ((1, 1e12), (3, 40), (5, 7200), (0.3, 4), (3600, 1_500_000)):
        for duration in (False, True):
            assert len(log_ticks(lo, hi, max_count, duration=duration)[2]) <= max_count
    for first, last in (
        (date(2026, 3, 4), date(2026, 3, 13)),
        (date(2026, 1, 7), date(2026, 3, 10)),
        (date(2025, 1, 15), date(2026, 3, 14)),
        (date(2020, 6, 15), date(2026, 6, 14)),
        (date(1900, 6, 1), date(2040, 6, 1)),
    ):
        assert len(calendar_ticks(first, last, max_count)[1]) <= max_count
    for lo_s, hi_s in ((33000, 43800), (80000, 95000), (0, 169200)):
        assert len(clock_ticks(lo_s, hi_s, max_count)[1]) <= max_count
