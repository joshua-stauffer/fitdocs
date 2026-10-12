"""Tests for the kit's scales: domains, positions, ticks and labels (chart-kit
Req 6.1, 6.2, 6.3, 6.4, 6.5, 6.7)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date, datetime
from typing import get_type_hints

import pytest

from fitdocs.render.charts.kit.data import Column, ValueKind, to_number
from fitdocs.render.charts.kit.layout import FONT_TEXT, text_width
from fitdocs.render.charts.kit.scales import (
    BandScale,
    NumericScale,
    ScaleType,
    Side,
    Tick,
    band_scale,
    numeric_scale,
)

NUMBER = Column("x", ValueKind.NUMBER)
COUNT = Column("count", ValueKind.NUMBER)
DATE = Column("day", ValueKind.DATE)
DATETIME = Column("start", ValueKind.DATETIME, unit="utc")
DURATION = Column("elapsed", ValueKind.DURATION)
PACE = Column("pace_s_per_km", ValueKind.NUMBER, unit="s_per_km")
SECONDS = Column("moving_s", ValueKind.NUMBER, unit="s")
PERCENT = Column("grade_pct", ValueKind.NUMBER, unit="pct")


def ordinal(year: int, month: int, day: int) -> float:
    return float(date(year, month, day).toordinal())


def moment(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
) -> float:
    number = to_number(
        datetime(year, month, day, hour, minute, second, microsecond),
        ValueKind.DATETIME,
    )
    assert number is not None
    return number


def vertical(
    values: Sequence[float],
    column: Column = NUMBER,
    *,
    length: float = 288.0,
    scale: ScaleType = ScaleType.LINEAR,
    include_zero: bool = False,
    nice: bool = True,
    integer: bool = False,
) -> NumericScale:
    """A vertical axis: pixel range runs from ``length`` (bottom) up to 0."""
    return numeric_scale(
        values,
        column,
        length,
        0.0,
        scale=scale,
        include_zero=include_zero,
        nice=nice,
        horizontal=False,
        integer=integer,
    )


def horizontal(
    values: Sequence[float],
    column: Column = NUMBER,
    *,
    length: float,
    start: float = 40.0,
    scale: ScaleType = ScaleType.LINEAR,
    include_zero: bool = False,
    nice: bool = True,
    integer: bool = False,
) -> NumericScale:
    return numeric_scale(
        values,
        column,
        start,
        start + length,
        scale=scale,
        include_zero=include_zero,
        nice=nice,
        horizontal=True,
        integer=integer,
    )


def labels(scale: NumericScale) -> list[str]:
    return [t.label for t in scale.ticks]


def values_of(scale: NumericScale) -> list[float]:
    return [t.value for t in scale.ticks]


def label_gaps(scale: NumericScale) -> list[float]:
    """Pixels between the extents of adjacent centred labels, from the layout
    estimate (not from the scale's own fit check)."""
    extents = [
        (
            scale.position(t.value) - text_width(t.label, FONT_TEXT) / 2,
            scale.position(t.value) + text_width(t.label, FONT_TEXT) / 2,
        )
        for t in scale.ticks
    ]
    return [b[0] - a[1] for a, b in zip(extents, extents[1:], strict=False)]


# ------------------------------------------------------------------ shapes


def test_enums_and_records_are_pinned() -> None:
    assert [(m.name, m.value) for m in ScaleType] == [
        ("LINEAR", "linear"),
        ("LOG", "log"),
        ("TIME", "time"),
    ]
    assert [(m.name, m.value) for m in Side] == [
        ("LEFT", "left"),
        ("RIGHT", "right"),
        ("BOTTOM", "bottom"),
    ]
    assert [f.name for f in dataclasses.fields(Tick)] == ["value", "label"]
    assert [f.name for f in dataclasses.fields(NumericScale)][:7] == [
        "type",
        "lo",
        "hi",
        "start_px",
        "end_px",
        "ticks",
        "column",
    ]
    assert [f.name for f in dataclasses.fields(BandScale)] == [
        "categories",
        "start_px",
        "end_px",
        "labelled",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        Tick(1.0, "1").label = "2"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        BandScale(("a",), 0.0, 1.0, (0,)).start_px = 2.0  # type: ignore[misc]
    hints = get_type_hints(NumericScale)
    assert hints["clock_date"] == date | None
    assert hints["hours"] is bool


def test_scale_is_frozen() -> None:
    scale = vertical([0.0, 10.0])
    with pytest.raises(dataclasses.FrozenInstanceError):
        scale.lo = 1.0  # type: ignore[misc]


# ------------------------------------------------------------ scale choice


def test_scale_type_follows_the_column_kind() -> None:
    assert vertical([1.0, 5.0]).type is ScaleType.LINEAR
    assert vertical([1.0, 5.0], DURATION).type is ScaleType.LINEAR
    assert vertical([1.0, 5.0], scale=ScaleType.LOG).type is ScaleType.LOG
    assert vertical([1.0, 5.0], DURATION, scale=ScaleType.LOG).type is ScaleType.LOG
    assert vertical([ordinal(2024, 1, 1), ordinal(2024, 1, 9)], DATE).type is (
        ScaleType.TIME
    )
    assert vertical([moment(2024, 1, 1), moment(2024, 1, 1, 6)], DATETIME).type is (
        ScaleType.TIME
    )


def test_a_log_scale_is_refused_for_dates_and_a_time_scale_for_numbers() -> None:
    with pytest.raises(ValueError, match="log"):
        vertical([ordinal(2024, 1, 1), ordinal(2024, 1, 9)], DATE, scale=ScaleType.LOG)
    with pytest.raises(ValueError, match="time"):
        vertical([1.0, 5.0], scale=ScaleType.TIME)
    for kind in (ValueKind.CATEGORY, ValueKind.BOOLEAN):
        with pytest.raises(ValueError, match="no numeric scale"):
            vertical([1.0, 5.0], Column("c", kind))


def test_scale_inputs_are_checked() -> None:
    with pytest.raises(ValueError, match="at least one value"):
        vertical([])
    with pytest.raises(ValueError, match="finite"):
        vertical([1.0, float("nan")])
    with pytest.raises(ValueError, match="finite"):
        vertical([1.0, float("inf")])
    with pytest.raises(ValueError, match="positive"):
        vertical([0.0, 5.0], scale=ScaleType.LOG)
    with pytest.raises(ValueError, match="positive"):
        vertical([-1.0, 5.0], scale=ScaleType.LOG)


# ------------------------------------------------------------- position


def test_position_maps_the_domain_onto_the_pixel_range() -> None:
    scale = vertical([0.0, 100.0], length=200.0)  # domain 0..100, 200 px up to 0
    assert (scale.lo, scale.hi) == (0.0, 100.0)
    assert scale.position(0.0) == 200.0
    assert scale.position(25.0) == 150.0
    assert scale.position(100.0) == 0.0
    across = horizontal([0.0, 100.0], length=400.0, start=60.0)
    assert across.position(0.0) == 60.0
    assert across.position(25.0) == 160.0
    assert across.position(100.0) == 460.0


def test_log_position_is_by_decade() -> None:
    scale = vertical([1.0, 1000.0], length=300.0, scale=ScaleType.LOG)
    assert (scale.lo, scale.hi) == (1.0, 1000.0)
    assert scale.position(1.0) == pytest.approx(300.0)
    assert scale.position(10.0) == pytest.approx(200.0)
    assert scale.position(100.0) == pytest.approx(100.0)
    assert scale.position(1000.0) == pytest.approx(0.0)
    assert scale.position(31.622776601683793) == pytest.approx(150.0)


# ---------------------------------------------------- tick counts (Req 6.2)


def test_vertical_tick_count_is_length_over_36_clamped_to_2_and_8() -> None:
    # 180 px -> 5 ticks allowed -> step 20 (5 ticks); a /48 divisor allows 3 -> step 50.
    assert values_of(vertical([0.0, 80.0], length=180.0)) == [0, 20, 40, 60, 80]
    # 36 px -> floor 1, clamped up to 2: two ticks enclose 1..9 as 0 and 10.
    assert values_of(vertical([1.0, 9.0], length=36.0)) == [0, 10]
    # 1000 px -> floor 27, clamped down to 8 -> step 20, not 5.
    assert values_of(vertical([0.0, 100.0], length=1000.0)) == [
        0, 20, 40, 60, 80, 100,
    ]  # fmt: skip
    # 288 px -> 8 ticks allowed: raw 100/7 = 14.3 -> step 20.
    assert labels(vertical([0.0, 100.0], length=288.0)) == [
        "0", "20", "40", "60", "80", "100",
    ]  # fmt: skip


def test_vertical_tick_cap_is_8_not_9() -> None:
    # 1000 px: 8 ticks give step 20 (5 ticks); a cap of 9 gives step 10.
    assert values_of(vertical([0.0, 80.0], length=1000.0)) == [0, 20, 40, 60, 80]


def test_horizontal_tick_count_starts_at_length_over_48() -> None:
    # 240 px -> 5 ticks allowed -> step 50 (3 ticks); a vertical axis of the
    # same length allows 6 and takes step 20.
    assert values_of(horizontal([0.0, 100.0], length=240.0)) == [0, 50, 100]
    assert values_of(vertical([0.0, 100.0], length=240.0)) == [0, 20, 40, 60, 80, 100]


def test_number_tick_decimals_follow_the_step() -> None:
    scale = vertical([0.0, 1.0], length=144.0)
    assert labels(scale) == ["0.0", "0.5", "1.0"]
    assert values_of(vertical([0.0, 0.3], length=180.0)) == [0.0, 0.1, 0.2, 0.3]
    assert labels(vertical([0.0, 0.3], length=180.0)) == ["0.0", "0.1", "0.2", "0.3"]


def test_percent_ticks_carry_the_symbol_and_other_units_do_not() -> None:
    assert labels(vertical([0.0, 80.0], PERCENT, length=180.0)) == [
        "0%", "20%", "40%", "60%", "80%",
    ]  # fmt: skip
    watts = Column("power_w", ValueKind.NUMBER, unit="w")
    assert labels(vertical([0.0, 80.0], watts, length=180.0)) == [
        "0", "20", "40", "60", "80",
    ]  # fmt: skip


def test_ticks_that_straddle_zero_are_measured_not_trusted_to_max_count() -> None:
    # linear_ticks returns 3 ticks for max_count 2 when lo < 0 < hi.
    scale = vertical([-3.0, 4.0], length=36.0)
    assert values_of(scale) == [-5.0, 0.0, 5.0]
    assert (scale.lo, scale.hi) == (-5.0, 5.0)
    assert labels(scale) == ["-5", "0", "5"]


# ----------------------------------------------- degenerate domains (Req 6.4)


@pytest.mark.parametrize(
    ("value", "include_zero", "integer", "domain"),
    [
        # |v|/10 = 0.5 is on the ladder; |v| itself (5) would give (0, 10).
        (5.0, False, False, (4.5, 5.5)),
        # |v|/10 = 7 -> 10 (the ladder step at or above it).
        (70.0, False, False, (60.0, 80.0)),
        # the sign does not matter.
        (-5.0, False, False, (-5.5, -4.5)),
        # zero without include_zero pads by one unit.
        (0.0, False, False, (-1.0, 1.0)),
        # include_zero before degeneracy: 0..v is not degenerate ...
        (5.0, True, False, (0.0, 5.0)),
        (-5.0, True, False, (-5.0, 0.0)),
        # ... but every value 0 under include_zero is [0, 1] ...
        (0.0, True, False, (0.0, 1.0)),
        (0.0, True, True, (0.0, 1.0)),
        # integer axes pad by 1.
        (5.0, False, True, (4.0, 6.0)),
        (0.0, False, True, (-1.0, 1.0)),
    ],
)
def test_linear_degenerate_domains(
    value: float,
    include_zero: bool,
    integer: bool,
    domain: tuple[float, float],
) -> None:
    for values in ([value], [value, value, value]):
        for nice in (False, True):
            scale = vertical(
                values,
                include_zero=include_zero,
                nice=nice,
                integer=integer,
                length=180.0,
            )
            if nice:  # the enclosing ticks may only widen the stated domain
                assert scale.lo <= domain[0] and domain[1] <= scale.hi
            else:
                assert (scale.lo, scale.hi) == domain
            assert scale.lo < scale.hi
            assert scale.lo <= value <= scale.hi


def test_include_zero_applies_before_the_degenerate_rule() -> None:
    scale = vertical([0.0, 0.0], include_zero=True, nice=False)
    assert (scale.lo, scale.hi) == (0.0, 1.0)
    assert labels(scale) == ["0.0", "0.2", "0.4", "0.6", "0.8", "1.0"]


def test_duration_degenerate_pad_uses_the_duration_ladder() -> None:
    # |v|/10 = 45 s -> the duration ladder's 60, not the decimal ladder's 50.
    scale = vertical([450.0], DURATION, nice=False)
    assert (scale.lo, scale.hi) == (390.0, 510.0)


def test_log_degenerate_domain_is_a_decade_each_side_then_decade_rounded() -> None:
    exact = vertical([100.0], scale=ScaleType.LOG, nice=False)
    assert (exact.lo, exact.hi) == (10.0, 1000.0)
    # 3 -> (0.3, 30) exactly, or decade-rounded (0.1, 100).
    assert vertical([3.0], scale=ScaleType.LOG, nice=False).lo == 0.3
    assert vertical([3.0], scale=ScaleType.LOG, nice=False).hi == 30.0
    rounded = vertical([3.0], scale=ScaleType.LOG, nice=True)
    assert (rounded.lo, rounded.hi) == (0.1, 100.0)
    assert labels(rounded) == ["0.1", "1.0", "10.0", "100.0"]


def test_date_degenerate_domain_is_one_day_each_side() -> None:
    day = ordinal(2024, 5, 15)
    scale = vertical([day, day], DATE, length=288.0)
    assert (scale.lo, scale.hi) == (day - 1, day + 1)
    assert values_of(scale) == [day - 1, day, day + 1]
    assert labels(scale) == ["2024-05-14", "2024-05-15", "2024-05-16"]


def test_datetime_degenerate_domain_is_an_hour_each_side() -> None:
    noon = moment(2024, 5, 15, 12)
    scale = vertical([noon], DATETIME, length=288.0)
    assert (scale.lo, scale.hi) == (noon - 3600, noon + 3600)
    assert labels(scale) == ["11:00", "11:30", "12:00", "12:30", "13:00"]


# --------------------------------------------------- nice versus exact


def test_nice_encloses_the_data_at_ticks_and_exact_keeps_the_extent() -> None:
    nice = vertical([-13.0, 47.0], nice=True)
    assert (nice.lo, nice.hi) == (-20.0, 50.0)
    assert values_of(nice) == [-20, -10, 0, 10, 20, 30, 40, 50]
    assert nice.ticks[0].value == nice.lo and nice.ticks[-1].value == nice.hi

    exact = vertical([-13.0, 47.0], nice=False)
    assert (exact.lo, exact.hi) == (-13.0, 47.0)
    assert values_of(exact) == [-10, 0, 10, 20, 30, 40]
    assert labels(exact) == ["-10", "0", "10", "20", "30", "40"]
    assert all(exact.lo <= t.value <= exact.hi for t in exact.ticks)
    assert exact.position(-13.0) == 288.0 and exact.position(47.0) == 0.0


def test_exact_extent_gets_two_ticks_when_enclosing_ones_leave_one_inside() -> None:
    # 1.3..8.7 over 5 ticks: enclosing 0, 5, 10 holds only 5 inside the extent;
    # the count grows until two ticks sit inside.
    scale = vertical([1.3, 8.7], length=180.0, nice=False)
    assert (scale.lo, scale.hi) == (1.3, 8.7)
    assert labels(scale) == ["2", "4", "6", "8"]
    enclosed = vertical([1.3, 8.7], length=180.0, nice=True)
    assert (enclosed.lo, enclosed.hi) == (0.0, 10.0)
    assert labels(enclosed) == ["0", "5", "10"]


def test_exact_extent_keeps_a_tick_a_float_ulp_above_it() -> None:
    top = 0.7 - 0.4  # 0.29999999999999993
    assert top != 0.3
    scale = vertical([0.0, top], length=180.0, nice=False)
    assert labels(scale) == ["0.0", "0.1", "0.2", "0.3"]
    assert scale.hi == top


def test_ticks_equal_to_the_extent_are_kept_when_exact() -> None:
    scale = vertical([0.0, 100.0], length=180.0, nice=False)
    assert values_of(scale) == [0, 50, 100]
    assert (scale.lo, scale.hi) == (0.0, 100.0)


# ------------------------------------------------- zero in magnitude axes


def test_include_zero_extends_a_positive_domain_down_and_negative_up() -> None:
    assert (vertical([40.0, 90.0], include_zero=True, nice=False).lo) == 0.0
    assert (vertical([40.0, 90.0], include_zero=True, nice=False).hi) == 90.0
    assert (vertical([-90.0, -40.0], include_zero=True, nice=False).hi) == 0.0
    assert (vertical([-90.0, -40.0], include_zero=True, nice=False).lo) == -90.0
    assert (vertical([40.0, 90.0], include_zero=False, nice=False).lo) == 40.0
    straddle = vertical([-4.0, 9.0], include_zero=True, nice=False)
    assert (straddle.lo, straddle.hi) == (-4.0, 9.0)


# ----------------------------------------------------------- integer axes


def test_integer_axis_over_counts_has_whole_number_ticks_only() -> None:
    whole = vertical([0.0, 3.0], COUNT, integer=True)
    assert values_of(whole) == [0.0, 1.0, 2.0, 3.0]
    assert labels(whole) == ["0", "1", "2", "3"]
    # Precondition: the same data without the option puts a tick at 0.5.
    free = vertical([0.0, 3.0], COUNT, integer=False)
    assert values_of(free) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert labels(free)[1] == "0.5"


def test_integer_axis_over_all_zero_counts_with_include_zero_is_0_to_1() -> None:
    scale = vertical([0.0, 0.0, 0.0], COUNT, include_zero=True, integer=True)
    assert (scale.lo, scale.hi) == (0.0, 1.0)
    assert values_of(scale) == [0.0, 1.0]
    assert labels(scale) == ["0", "1"]
    free = vertical([0.0, 0.0, 0.0], COUNT, include_zero=True, integer=False)
    assert (free.lo, free.hi) == (0.0, 1.0)
    assert values_of(free) == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


# ----------------------------------------------------------- date axes


def test_date_axis_picks_calendar_labels_by_step() -> None:
    days = vertical([ordinal(2024, 5, 6), ordinal(2024, 5, 12)], DATE, length=288.0)
    assert labels(days) == [f"2024-05-{d:02d}" for d in range(6, 13)]
    assert values_of(days) == [ordinal(2024, 5, d) for d in range(6, 13)]
    weeks = vertical([ordinal(2024, 5, 1), ordinal(2024, 6, 15)], DATE, length=288.0)
    assert labels(weeks) == [
        "2024-05-06", "2024-05-13", "2024-05-20", "2024-05-27",
        "2024-06-03", "2024-06-10",
    ]  # fmt: skip
    months = vertical([ordinal(2024, 1, 1), ordinal(2024, 6, 30)], DATE, length=288.0)
    assert labels(months) == [f"2024-{m:02d}" for m in range(1, 7)]
    quarters = vertical([ordinal(2024, 1, 1), ordinal(2025, 3, 31)], DATE, length=288.0)
    assert labels(quarters) == ["2024-01", "2024-04", "2024-07", "2024-10", "2025-01"]
    halves = vertical([ordinal(2023, 1, 1), ordinal(2025, 12, 31)], DATE, length=288.0)
    assert labels(halves) == [
        "2023-01", "2023-07", "2024-01", "2024-07", "2025-01", "2025-07",
    ]  # fmt: skip
    years = vertical([ordinal(2016, 1, 1), ordinal(2023, 12, 31)], DATE, length=288.0)
    assert labels(years) == [str(y) for y in range(2016, 2024)]
    two_years = vertical([ordinal(2015, 3, 1), ordinal(2024, 6, 1)], DATE, length=288.0)
    assert labels(two_years) == ["2016", "2018", "2020", "2022", "2024"]


def test_date_axis_keeps_the_exact_extent_for_both_nice_settings() -> None:
    lo, hi = ordinal(2024, 5, 6), ordinal(2024, 5, 12)
    for nice in (False, True):
        scale = vertical([hi, lo], DATE, nice=nice)
        assert (scale.lo, scale.hi) == (lo, hi)


def test_720_px_date_axis_over_a_year_never_overlaps_and_320_px_has_fewer() -> None:
    # 2024-03-01 .. 2025-02-28: 364 days; the shortest month gap is 30 days.
    values = [ordinal(2024, 3, 1), ordinal(2025, 2, 28)]
    wide = horizontal(values, DATE, length=720.0)
    narrow = horizontal(values, DATE, length=320.0)

    assert labels(wide) == [
        "2024-03", "2024-04", "2024-05", "2024-06", "2024-07", "2024-08",
        "2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02",
    ]  # fmt: skip
    assert labels(narrow) == ["2024-04", "2024-07", "2024-10", "2025-01"]
    assert len(narrow.ticks) < len(wide.ticks)

    for scale in (wide, narrow):
        gaps = label_gaps(scale)
        assert len(gaps) == len(scale.ticks) - 1 and gaps
        assert min(gaps) >= 10.0
        assert all(
            scale.start_px <= scale.position(t.value) <= scale.end_px
            for t in scale.ticks
        )
    # 30 days over 720 px / 364 days = 59.3 px between centres, 49.28 px labels.
    assert min(label_gaps(wide)) == pytest.approx(
        30 * 720 / 364 - text_width("2024-04", FONT_TEXT)
    )


def test_a_calendar_year_at_720_px_drops_months_for_quarters() -> None:
    # February is 29 days = 57.2 px apart: 49.28 px labels leave 7.9 px < 10.
    scale = horizontal([ordinal(2024, 1, 1), ordinal(2024, 12, 31)], DATE, length=720.0)
    assert labels(scale) == ["2024-01", "2024-04", "2024-07", "2024-10"]
    assert min(label_gaps(scale)) >= 10.0


def test_the_start_tick_count_is_reduced_when_its_labels_overlap() -> None:
    # 100 days at 720 px: 15 weekly ticks are allowed but 70.4 px day labels sit
    # 50.4 px apart; the loop moves to month ticks.
    values = [ordinal(2024, 1, 1), ordinal(2024, 4, 10)]
    scale = horizontal(values, DATE, length=720.0)
    assert labels(scale) == ["2024-01", "2024-02", "2024-03", "2024-04"]
    assert min(label_gaps(scale)) >= 10.0
    # Precondition: the weekly set the loop starts from really does overlap.
    week_gap = 7 * 720 / 100 - text_width("2024-01-01", FONT_TEXT)
    assert week_gap < 0


def test_a_clock_axis_loop_reduces_ticks_until_labels_fit() -> None:
    # 20:00..04:00 across midnight on 320 px: 5 ticks at 2 h are 80 px apart but
    # 'MM-DD HH:MM' labels need 87.4 px; the axis falls back to 3 h steps.
    values = [moment(2024, 5, 6, 20), moment(2024, 5, 7, 4)]
    scale = horizontal(values, DATETIME, length=320.0)
    assert labels(scale) == ["05-06 21:00", "05-07 00:00", "05-07 03:00"]
    assert min(label_gaps(scale)) >= 10.0
    assert scale.clock_date is None


def test_the_fit_loop_settles_on_the_first_count_that_fits() -> None:
    # 20:00..03:00 on 208 px starts at 4 ticks (2 h steps, labels too close);
    # 3 ticks fit and are not the 2-tick fallback.
    values = [moment(2024, 5, 6, 20), moment(2024, 5, 7, 3)]
    scale = horizontal(values, DATETIME, length=208.0)
    assert labels(scale) == ["05-06 21:00", "05-07 00:00", "05-07 03:00"]
    assert min(label_gaps(scale)) >= 10.0


def test_the_fit_loop_falls_back_to_two_ticks_when_nothing_fits() -> None:
    # 20:00..00:00 on 144 px: 3 ticks are 72 px apart and need 87.4 px.
    values = [moment(2024, 5, 6, 20), moment(2024, 5, 7, 0)]
    scale = horizontal(values, DATETIME, length=144.0)
    assert labels(scale) == ["05-06 21:00", "05-07 00:00"]


# ----------------------------------------------------------- date-time axes


def test_datetime_axis_under_two_days_labels_clock_and_returns_the_date() -> None:
    values = [moment(2024, 5, 6, 8), moment(2024, 5, 6, 14, 30)]
    scale = vertical(values, DATETIME, length=288.0)
    # 08:00..14:30 holds 14 half-hour ticks (> 8); hourly 7 fit.
    assert labels(scale) == [f"{h:02d}:00" for h in range(8, 15)]
    assert values_of(scale) == [moment(2024, 5, 6, h) for h in range(8, 15)]
    assert scale.clock_date == date(2024, 5, 6)
    assert (scale.lo, scale.hi) == (values[0], values[1])


def test_datetime_axis_crossing_midnight_labels_month_day_and_time() -> None:
    values = [moment(2024, 5, 6, 20), moment(2024, 5, 7, 4)]
    scale = vertical(values, DATETIME, length=288.0)
    assert labels(scale) == [
        "05-06 20:00", "05-06 22:00", "05-07 00:00", "05-07 02:00", "05-07 04:00",
    ]  # fmt: skip
    assert scale.clock_date is None


def test_datetime_axis_of_two_days_or_more_has_calendar_ticks_at_midnight() -> None:
    values = [moment(2024, 5, 6, 8), moment(2024, 5, 20, 8)]
    scale = vertical(values, DATETIME, length=288.0)
    assert labels(scale) == [f"2024-05-{d:02d}" for d in range(8, 21, 2)]
    assert values_of(scale) == [moment(2024, 5, d) for d in range(8, 21, 2)]
    assert scale.clock_date is None
    just_under = vertical(
        [moment(2024, 5, 6, 8), moment(2024, 5, 8, 7, 59)], DATETIME, length=288.0
    )
    assert labels(just_under) == [
        "05-06 12:00", "05-06 18:00", "05-07 00:00", "05-07 06:00",
        "05-07 12:00", "05-07 18:00", "05-08 00:00", "05-08 06:00",
    ]  # fmt: skip
    exactly = vertical(
        [moment(2024, 5, 6, 8), moment(2024, 5, 8, 8)], DATETIME, length=288.0
    )
    assert labels(exactly) == ["2024-05-07", "2024-05-08"]


def test_clock_ticks_on_an_unaligned_domain_stay_inside_it() -> None:
    lo, hi = moment(2024, 5, 6, 12, 0, 20), moment(2024, 5, 6, 12, 10, 0)
    scale = vertical([lo, hi], DATETIME, length=288.0)
    assert labels(scale) == ["12:05", "12:10"]
    assert values_of(scale) == [moment(2024, 5, 6, 12, 5), moment(2024, 5, 6, 12, 10)]
    assert all(lo <= t.value <= hi for t in scale.ticks)
    assert all(0.0 <= scale.position(t.value) <= 288.0 for t in scale.ticks)
    assert scale.clock_date == date(2024, 5, 6)


def narrow_clock(lo: float, hi: float) -> NumericScale:
    return vertical([lo, hi], DATETIME, length=260.0)


def test_clock_ticks_use_the_exact_tolerance_of_a_small_magnitude() -> None:
    # 12:00:20 .. 12:06:40 on 260 px: six minute ticks (12:01 .. 12:06) fit.
    lo, hi = moment(2024, 5, 6, 12, 0, 20), moment(2024, 5, 6, 12, 6, 40)
    scale = narrow_clock(lo, hi)
    assert labels(scale) == ["12:01", "12:02", "12:03", "12:04", "12:05", "12:06"]
    assert all(lo <= t.value <= hi for t in scale.ticks)


def test_clock_ticks_a_microsecond_outside_the_domain_are_dropped() -> None:
    lo, hi = moment(2024, 5, 6, 12, 0, 0, 20), moment(2024, 5, 6, 12, 10, 0)
    assert lo > moment(2024, 5, 6, 12, 0)
    scale = vertical([lo, hi], DATETIME, length=288.0)
    assert labels(scale) == ["12:05", "12:10"]
    assert all(lo <= t.value <= hi for t in scale.ticks)


def test_clock_domain_holding_no_tick_has_no_ticks() -> None:
    lo, hi = moment(2024, 5, 6, 12, 0, 10), moment(2024, 5, 6, 12, 0, 40)
    scale = vertical([lo, hi], DATETIME, length=288.0)
    assert scale.ticks == ()
    assert (scale.lo, scale.hi) == (lo, hi)
    assert scale.clock_date is None


def test_clock_date_comes_from_the_ticks_not_the_domain() -> None:
    # 23:45 .. 05:00 crosses midnight, but every tick (00:00 .. 05:00) is on the 7th.
    values = [moment(2024, 5, 6, 23, 45), moment(2024, 5, 7, 5)]
    scale = vertical(values, DATETIME, length=288.0)
    assert labels(scale) == [f"{h:02d}:00" for h in range(0, 6)]
    assert scale.clock_date == date(2024, 5, 7)


# ------------------------------------------------------ duration and pace


def test_duration_axis_reaching_an_hour_labels_every_tick_h_mm_ss() -> None:
    scale = vertical([0.0, 5400.0], DURATION, length=288.0)
    assert values_of(scale) == [0, 900, 1800, 2700, 3600, 4500, 5400]
    assert labels(scale) == [
        "0:00:00", "0:15:00", "0:30:00", "0:45:00", "1:00:00", "1:15:00", "1:30:00",
    ]  # fmt: skip
    assert scale.hours is True


def test_duration_axis_under_an_hour_labels_every_tick_m_ss() -> None:
    scale = vertical([0.0, 3000.0], DURATION, length=288.0)
    assert values_of(scale) == [0, 600, 1200, 1800, 2400, 3000]
    assert labels(scale) == ["0:00", "10:00", "20:00", "30:00", "40:00", "50:00"]
    assert scale.hours is False


def test_seconds_unit_columns_use_the_duration_forms_too() -> None:
    scale = vertical([0.0, 5400.0], SECONDS, length=288.0)
    assert labels(scale)[-1] == "1:30:00" and labels(scale)[0] == "0:00:00"
    assert scale.hours is True
    short = vertical([0.0, 3000.0], SECONDS, length=288.0)
    assert labels(short)[1] == "10:00" and short.hours is False


def test_pace_axis_increases_upward_and_labels_m_ss() -> None:
    scale = vertical([270.0, 330.0], PACE, length=200.0)
    assert (scale.lo, scale.hi) == (270.0, 330.0)
    assert values_of(scale) == [270, 285, 300, 315, 330]
    assert labels(scale) == ["4:30", "4:45", "5:00", "5:15", "5:30"]
    assert (scale.start_px, scale.end_px) == (200.0, 0.0)
    # Not inverted: a larger pace value sits higher (a smaller pixel y).
    assert scale.position(270.0) == 200.0
    assert scale.position(300.0) == 100.0
    assert scale.position(330.0) == 0.0
    pixels = [scale.position(t.value) for t in scale.ticks]
    assert pixels == sorted(pixels, reverse=True)


def test_pace_labels_keep_minutes_unbounded_past_an_hour() -> None:
    scale = vertical([3000.0, 4200.0], PACE, length=288.0)
    assert labels(scale)[0] == "50:00" and labels(scale)[-1] == "70:00"
    assert scale.hours is True


def test_negative_duration_ticks_keep_their_sign() -> None:
    scale = vertical([-3600.0, 3600.0], DURATION, length=72.0)
    assert labels(scale) == ["-1:00:00", "0:00:00", "1:00:00"]
    small = vertical([-120.0, 120.0], DURATION, length=72.0)
    assert labels(small) == ["-2:00", "0:00", "2:00"]


def test_log_duration_axis_uses_the_duration_ticks_and_forms() -> None:
    scale = vertical([60.0, 3600.0], DURATION, length=288.0, scale=ScaleType.LOG)
    assert (scale.lo, scale.hi) == (60.0, 3600.0)
    assert values_of(scale) == [60, 120, 300, 600, 1200, 1800, 3600]
    assert labels(scale)[0] == "0:01:00" and labels(scale)[-1] == "1:00:00"


# ------------------------------------------------------------ log axes


def test_log_axis_ticks_are_decades_with_decimals_from_the_smallest() -> None:
    scale = vertical([1.0, 1000.0], scale=ScaleType.LOG, length=288.0)
    assert values_of(scale) == [1, 10, 100, 1000]
    assert labels(scale) == ["1", "10", "100", "1000"]
    fractions = vertical([0.02, 0.9], scale=ScaleType.LOG, length=288.0)
    assert (fractions.lo, fractions.hi) == (0.02, 1.0)
    assert values_of(fractions) == [0.02, 0.05, 0.1, 0.2, 0.5, 1.0]
    assert labels(fractions) == ["0.02", "0.05", "0.10", "0.20", "0.50", "1.00"]


def test_log_axis_with_exact_extent_keeps_ticks_inside_it() -> None:
    scale = vertical([0.02, 0.9], scale=ScaleType.LOG, length=288.0, nice=False)
    assert (scale.lo, scale.hi) == (0.02, 0.9)
    assert values_of(scale) == [0.02, 0.05, 0.1, 0.2, 0.5]


# ------------------------------------------------------------ band scale


def test_band_scale_lays_out_equal_bands_in_order() -> None:
    scale = band_scale(["a", "b", "c", "d"], 100.0, 500.0, font_px=11)
    assert scale.categories == ("a", "b", "c", "d")
    assert (scale.start_px, scale.end_px) == (100.0, 500.0)
    assert scale.band(0) == (100.0, 200.0)
    assert scale.band(3) == (400.0, 500.0)
    assert [scale.centre(i) for i in range(4)] == [150.0, 250.0, 350.0, 450.0]


def test_band_scale_keeps_the_given_order_not_sorted_order() -> None:
    scale = band_scale(["walk", "bike", "run"], 0.0, 300.0, font_px=11)
    assert scale.categories == ("walk", "bike", "run")
    assert [scale.centre(i) for i in range(3)] == [50.0, 150.0, 250.0]
    assert scale.labelled == (0, 1, 2)


def test_band_scale_on_a_vertical_range_keeps_left_before_right() -> None:
    scale = band_scale(["a", "b"], 200.0, 0.0, font_px=11)
    assert scale.band(0) == (100.0, 200.0)
    assert scale.band(1) == (0.0, 100.0)
    assert scale.centre(0) == 150.0 and scale.centre(1) == 50.0


def test_band_scale_labels_every_band_when_the_widest_label_fits() -> None:
    names = ["Ride", "Run", "Swim", "Gym Session"]  # widest 11 chars = 77.44 px
    wide = band_scale(names, 0.0, 400.0, font_px=11)  # 100 px bands, limit 96
    assert text_width("Gym Session", 11) == pytest.approx(77.44)
    assert wide.labelled == (0, 1, 2, 3)


def test_band_scale_fit_is_inclusive_at_the_band_width_minus_4() -> None:
    names = ["abcde"] * 4  # 5 chars * 10 px * 0.64 = 32.0 px
    assert text_width("abcde", 10) == 32.0
    exact = band_scale(names, 0.0, 144.0, font_px=10)  # 36 px bands, limit 32.0
    assert exact.labelled == (0, 1, 2, 3)
    over = band_scale(names, 0.0, 143.0, font_px=10)  # limit 31.75
    assert over.labelled == (0, 2)


def test_band_scale_thins_to_the_smallest_k_that_fits_from_band_0() -> None:
    five = ["abcde"] * 10  # 35.2 px at 11 px
    two = band_scale(five, 0.0, 200.0, font_px=11)  # 20 px bands: k=2 limit 36
    assert two.labelled == (0, 2, 4, 6, 8)
    seven = ["abcdefg"] * 10  # 49.28 px
    three = band_scale(seven, 0.0, 200.0, font_px=11)  # k=2 limit 36, k=3 limit 56
    assert three.labelled == (0, 3, 6, 9)
    assert three.categories == tuple(seven)


def test_band_scale_always_labels_band_0_even_when_nothing_fits() -> None:
    scale = band_scale(["a very long category label"] * 3, 0.0, 30.0, font_px=11)
    assert scale.labelled == (0,)


def test_band_scale_needs_a_category() -> None:
    with pytest.raises(ValueError, match="at least one category"):
        band_scale([], 0.0, 100.0, font_px=11)
