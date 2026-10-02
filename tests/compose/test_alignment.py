"""Whole-hour shift, per-stretch lag and placement (channel-merge 2.3; Req 2.6,
3.3-3.9; design.md § Alignment).

Fixtures are hand-built: within one fixture every channel value is
pairwise-distinct, a "lag +L" extra is built as ``extra(t) = base(t + L)``, and
every expected value is a literal. Where a test states a precondition about
how many samples matched and were compared at a lag, it asserts it with the
test-side ``counts`` helper.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest

import fitdocs.compose.alignment as alignment_module
from fitdocs.compose.alignment import (
    ALIGNMENT_KEYS,
    ALIGNMENT_SOURCES,
    MAX_LAG_S,
    MIN_MATCHED_SAMPLES,
    AlignmentKey,
    align_extra,
    establish_lag,
    hour_shift_s,
)
from fitdocs.compose.types import StretchLag
from tests.compose.builders import make_activity

START = datetime(2026, 1, 1, tzinfo=UTC)


def dist(t: int) -> float:
    """A strictly increasing, pairwise-distinct cumulative distance (m)."""
    return (100000 + 37 * t * t + 11 * t) / 100.0


def power(t: int) -> int:
    """A pairwise-distinct power (W)."""
    return 150 + 4 * t


def hr(t: int) -> int:
    """A pairwise-distinct heart rate (bpm)."""
    return 90 + 2 * t


def counts(
    stretch: range,
    extra_instants: Sequence[int | None],
    extra_values: Sequence[float | int | None],
    base_index: Mapping[int, int],
    base_values: Sequence[float | int | None],
    resolution: float,
    lag: int,
) -> tuple[int, int]:
    """Test-side ``(matched, compared)`` at ``lag``, for fixture preconditions."""
    matched = compared = 0
    for j in stretch:
        t = extra_instants[j]
        v = extra_values[j]
        if t is None or v is None or (t + lag) not in base_index:
            continue
        b = base_values[base_index[t + lag]]
        if b is None:
            continue
        compared += 1
        if abs(v - b) < resolution / 2:
            matched += 1
    return matched, compared


class TestConstants:
    def test_alignment_keys_are_exactly_distance_then_power(self) -> None:
        expected = (
            AlignmentKey("distance_m", 0.01, "distance"),
            AlignmentKey("power_w", 1.0, "power"),
        )
        assert expected == ALIGNMENT_KEYS

    def test_min_matched_samples_is_five(self) -> None:
        assert MIN_MATCHED_SAMPLES == 5

    def test_max_lag_is_two(self) -> None:
        assert MAX_LAG_S == 2

    def test_every_constant_has_a_one_line_source(self) -> None:
        assert set(ALIGNMENT_SOURCES) == {
            "PAUSE_GAP_S",
            "MAX_LAG_S",
            "MIN_MATCHED_SAMPLES",
            "ALIGNMENT_KEYS",
        }
        for name, source in ALIGNMENT_SOURCES.items():
            assert source.strip() == source and source, name
            assert "\n" not in source, name

    def test_shift_constants_are_imported_not_restated(self) -> None:
        tree = ast.parse(inspect.getsource(alignment_module))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "fitdocs.identity.matching"
            for alias in node.names
        }
        assert imported == {"SHIFT_MAX_HOURS", "SHIFT_STEP_S", "START_TOLERANCE_S"}
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, int)
        ]
        assert literals, "the walk found no literals: wrong module"
        assert 3600 not in literals
        assert 36 not in literals


class TestHourShift:
    @pytest.mark.parametrize(
        ("delta_s", "expected"),
        [
            (3600, 3600),
            (129600, 129600),  # k = 36
            (133200, 0),  # k = 37
            (3601, 3600),  # 1 s off a whole hour
            (3599, 3600),
            (3602, 0),  # 2 s off
            (3598, 0),
            (129601, 129600),
            (129602, 0),
            (-3600, -3600),
            (-129600, -129600),
            (-133200, 0),
            (-3601, -3600),
            (-3602, 0),
            (0, 0),
            (1800, 0),
            (5400, 0),  # k rounds to 2, 1800 s off
            (7200, 7200),
        ],
    )
    def test_whole_hour_to_within_one_second(self, delta_s: int, expected: int) -> None:
        assert hour_shift_s(START, START + timedelta(seconds=delta_s)) == expected

    def test_absent_start_is_no_shift(self) -> None:
        later = START + timedelta(hours=1)
        assert hour_shift_s(None, later) == 0
        assert hour_shift_s(START, None) == 0
        assert hour_shift_s(None, None) == 0


class TestKeysAndLagRule:
    def test_two_stretches_each_placed_by_their_own_lag(self) -> None:
        base_offsets = list(range(40))
        extra_offsets = list(range(12)) + list(range(20, 32))
        base = make_activity(
            START, base_offsets, distance_m=[dist(t) for t in base_offsets]
        )
        extra = make_activity(
            START,
            extra_offsets,
            distance_m=[dist(t + 1) for t in range(12)]
            + [dist(t) for t in range(20, 32)],
        )
        placement = align_extra(base, extra)
        assert placement.alignment.hour_shift_s == 0
        assert placement.alignment.stretches == (
            StretchLag(0, 12, 1, "distance_m"),
            StretchLag(12, 24, 0, "distance_m"),
        )
        assert placement.extra_index == (
            None, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,  # fmt: skip
            None, None, None, None, None, None, None,
            12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
            None, None, None, None, None, None, None, None,
        )  # fmt: skip

    def test_distance_lag_wins_over_heart_rate_at_another_lag(self) -> None:
        offsets = list(range(30))
        base = make_activity(
            START,
            offsets,
            distance_m=[dist(t) for t in offsets],
            heart_rate_bpm=[hr(t) for t in offsets],
        )
        extra_offsets = list(range(1, 21))
        extra = make_activity(
            START,
            extra_offsets,
            distance_m=[dist(t + 1) for t in extra_offsets],
            heart_rate_bpm=[hr(t - 1) for t in extra_offsets],
        )
        base_index = {t: t for t in offsets}
        stretch = range(20)
        e_inst = list(extra_offsets)
        # Precondition: heart rate alone would establish -1, distance +1.
        hr_extra = list(extra.samples.heart_rate_bpm)
        hr_base = list(base.samples.heart_rate_bpm)
        assert establish_lag(stretch, e_inst, hr_extra, base_index, hr_base, 1.0) == -1
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 20, 1, "distance_m"),)
        assert placement.extra_index[2:22] == tuple(range(20))
        assert placement.extra_index[:2] == (None, None)
        assert placement.extra_index[22:] == (None,) * 8

    def test_distance_lag_beats_the_power_lag(self) -> None:
        offsets = list(range(30))
        base = make_activity(
            START,
            offsets,
            distance_m=[dist(t) for t in offsets],
            power_w=[power(t) for t in offsets],
        )
        extra_offsets = list(range(2, 22))
        extra = make_activity(
            START,
            extra_offsets,
            distance_m=[dist(t + 1) for t in extra_offsets],
            power_w=[power(t) for t in extra_offsets],
        )
        base_index = {t: t for t in offsets}
        stretch = range(20)
        e_inst = list(extra_offsets)
        # Precondition: power alone would establish 0, distance +1.
        p_extra = list(extra.samples.power_w)
        p_base = list(base.samples.power_w)
        assert establish_lag(stretch, e_inst, p_extra, base_index, p_base, 1.0) == 0
        assert counts(stretch, e_inst, p_extra, base_index, p_base, 1.0, 0) == (20, 20)
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 20, 1, "distance_m"),)
        assert placement.extra_index[3:23] == tuple(range(20))

    def test_power_is_used_when_the_extra_has_no_distance(self) -> None:
        offsets = list(range(30))
        base = make_activity(
            START,
            offsets,
            distance_m=[dist(t) for t in offsets],
            power_w=[power(t) for t in offsets],
        )
        extra_offsets = list(range(2, 22))
        extra = make_activity(
            START, extra_offsets, power_w=[power(t + 1) for t in extra_offsets]
        )
        assert set(extra.samples.distance_m) == {None}
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 20, 1, "power_w"),)
        assert placement.extra_index[3:23] == tuple(range(20))

    def test_power_is_used_when_distance_matches_nowhere(self) -> None:
        offsets = list(range(30))
        base = make_activity(
            START,
            offsets,
            distance_m=[dist(t) for t in offsets],
            power_w=[power(t) for t in offsets],
        )
        extra_offsets = list(range(2, 22))
        extra = make_activity(
            START,
            extra_offsets,
            distance_m=[dist(t) + 50.0 for t in extra_offsets],
            power_w=[power(t - 1) for t in extra_offsets],
        )
        base_index = {t: t for t in offsets}
        d_extra = list(extra.samples.distance_m)
        d_base = list(base.samples.distance_m)
        for lag in range(-2, 3):
            matched, compared = counts(
                range(20), list(extra_offsets), d_extra, base_index, d_base, 0.01, lag
            )
            assert (matched, compared) == (0, 20)
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 20, -1, "power_w"),)
        assert placement.extra_index[1:21] == tuple(range(20))

    def test_heart_rate_cadence_and_step_length_never_establish_a_lag(self) -> None:
        offsets = list(range(30))
        base = make_activity(
            START,
            offsets,
            heart_rate_bpm=[hr(t) for t in offsets],
            cadence_rpm=[160 + t for t in offsets],
            step_length_mm=[800 + 10 * t for t in offsets],
        )
        extra_offsets = list(range(2, 22))
        extra = make_activity(
            START,
            extra_offsets,
            heart_rate_bpm=[hr(t + 1) for t in extra_offsets],
            cadence_rpm=[160 + t + 1 for t in extra_offsets],
            step_length_mm=[800 + 10 * (t + 1) for t in extra_offsets],
        )
        base_index = {t: t for t in offsets}
        for channel, resolution in (
            ("heart_rate_bpm", 1.0),
            ("cadence_rpm", 1.0),
            ("step_length_mm", 1.0),
        ):
            lag = establish_lag(
                range(20),
                list(extra_offsets),
                list(getattr(extra.samples, channel)),
                base_index,
                list(getattr(base.samples, channel)),
                resolution,
            )
            assert lag == 1, channel
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 20, 0, None),)
        assert placement.extra_index[2:22] == tuple(range(20))

    def test_distance_resolution_is_a_hundredth_of_a_metre(self) -> None:
        offsets = list(range(30))
        base = make_activity(START, offsets, distance_m=[dist(t) for t in offsets])
        extra_offsets = list(range(2, 22))
        near = make_activity(
            START, extra_offsets, distance_m=[dist(t) + 0.004 for t in extra_offsets]
        )
        far = make_activity(
            START, extra_offsets, distance_m=[dist(t) + 0.006 for t in extra_offsets]
        )
        assert align_extra(base, near).alignment.stretches == (
            StretchLag(0, 20, 0, "distance_m"),
        )
        base_index = {t: t for t in offsets}
        far_values = [dist(t) + 0.006 for t in extra_offsets]
        base_values = [dist(t) for t in offsets]
        assert counts(
            range(20), list(extra_offsets), far_values, base_index, base_values, 0.01, 0
        ) == (0, 20)  # fmt: skip
        assert align_extra(base, far).alignment.stretches == (
            StretchLag(0, 20, 0, None),
        )

    def test_power_resolution_is_a_watt(self) -> None:
        offsets = list(range(30))
        base = make_activity(START, offsets, power_w=[power(t) for t in offsets])
        extra_offsets = list(range(2, 22))
        near = make_activity(
            START, extra_offsets, power_w=[power(t) + 0.4 for t in extra_offsets]
        )
        assert align_extra(base, near).alignment.stretches == (
            StretchLag(0, 20, 0, "power_w"),
        )


class TestEstablishLag:
    """Direct tests: instants are arbitrary ints, base_index a literal map."""

    def _base(self, n: int) -> tuple[dict[int, int], list[float | None]]:
        return {t: t for t in range(n)}, [dist(t) for t in range(n)]

    def test_window_reaches_two_each_way_and_stops_there(self) -> None:
        index, base_vals = self._base(40)
        inst = list(range(10, 20))
        for lag, expected in ((2, 2), (-2, -2), (3, None), (-3, None)):
            extra = [dist(t + lag) for t in inst]
            got = establish_lag(range(10), inst, extra, index, base_vals, 0.01)
            assert got == expected, lag
        extra3 = [dist(t + 3) for t in inst]
        assert counts(range(10), inst, extra3, index, base_vals, 0.01, 2) == (0, 10)

    def test_four_matches_fall_back_though_a_majority(self) -> None:
        index, base_vals = self._base(30)
        inst = list(range(5, 11))
        extra = [dist(t + 1) for t in inst[:4]] + [dist(t) + 70.0 for t in inst[4:]]
        assert counts(range(6), inst, extra, index, base_vals, 0.01, 1) == (4, 6)
        for lag in (-2, -1, 0, 2):
            assert counts(range(6), inst, extra, index, base_vals, 0.01, lag)[0] < 4
        assert 2 * 4 > 6
        assert establish_lag(range(6), inst, extra, index, base_vals, 0.01) is None

    def test_five_matches_of_five_compared_establish(self) -> None:
        index, base_vals = self._base(30)
        inst = list(range(5, 10))
        extra = [dist(t + 1) for t in inst]
        assert counts(range(5), inst, extra, index, base_vals, 0.01, 1) == (5, 5)
        assert establish_lag(range(5), inst, extra, index, base_vals, 0.01) == 1

    def test_five_matches_of_twenty_compared_fall_back(self) -> None:
        index, base_vals = self._base(40)
        inst = list(range(5, 25))
        extra = [dist(t + 1) for t in inst[:5]] + [dist(t) + 70.0 for t in inst[5:]]
        assert counts(range(20), inst, extra, index, base_vals, 0.01, 1) == (5, 20)
        for lag in (-2, -1, 0, 2):
            assert counts(range(20), inst, extra, index, base_vals, 0.01, lag)[0] < 5
        assert establish_lag(range(20), inst, extra, index, base_vals, 0.01) is None

    def test_exactly_half_is_not_more_than_half(self) -> None:
        index, base_vals = self._base(40)
        inst = list(range(5, 17))
        extra = [dist(t + 1) for t in inst[:6]] + [dist(t) + 70.0 for t in inst[6:]]
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 1) == (6, 12)
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) is None

    def test_majority_is_over_the_samples_compared_at_the_winning_lag(self) -> None:
        # 5 of 9 compared at +2, while 11 are compared at lag 0.
        index = {t: t for t in range(11)}
        base_vals: list[float | None] = [dist(t) for t in range(11)]
        inst = list(range(12))
        extra = [dist(t + 2) for t in inst[:5]] + [dist(t) + 70.0 for t in inst[5:]]
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 2) == (5, 9)
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 0) == (0, 11)
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) == 2

    def test_majority_fails_at_the_winning_lag_though_it_would_at_lag_zero(
        self,
    ) -> None:
        # 5 of 10 compared at +2 (not more than half); lag 0 compares only 8.
        index = {t: t for t in range(4, 14)}
        base_vals: list[float | None] = [dist(t) for t in range(14)]
        inst = list(range(12))
        extra = [dist(t + 2) if 2 <= t <= 6 else dist(t) + 70.0 for t in inst]
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 2) == (5, 10)
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 0) == (0, 8)
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) is None

    def test_a_tie_between_two_lags_establishes_nothing(self) -> None:
        # Even samples match the base at lag 0, odd ones at lag +1; the base is
        # blank where the other lag would look, so each lag matches 6 of the 6
        # it compares and the majority holds at both.
        inst = [3 * j for j in range(12)]
        base_vals: list[float | None] = [None] * 40
        extra: list[float | None] = []
        for j, t in enumerate(inst):
            if j % 2 == 0:
                base_vals[t] = dist(t)
                extra.append(dist(t))
            else:
                base_vals[t + 1] = dist(t + 1)
                extra.append(dist(t + 1))
        index = {t: t for t in range(40)}
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 0) == (6, 6)
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 1) == (6, 6)
        for lag in (-2, -1, 2):
            assert counts(range(12), inst, extra, index, base_vals, 0.01, lag)[0] == 0
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) is None

    def test_a_stationary_stretch_falls_back(self) -> None:
        index = {t: t for t in range(30)}
        base_vals: list[float | None] = [500.0] * 30
        inst = list(range(5, 17))
        extra: list[float | None] = [500.0] * 12
        for lag in range(-2, 3):
            assert counts(range(12), inst, extra, index, base_vals, 0.01, lag) == (
                12,
                12,
            )
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) is None

    def test_stationary_distance_falls_back_through_align_extra(self) -> None:
        offsets = list(range(30))
        base = make_activity(START, offsets, distance_m=[500.0] * 30)
        extra_offsets = list(range(5, 17))
        extra = make_activity(START, extra_offsets, distance_m=[500.0] * 12)
        base_index = {t: t for t in offsets}
        for lag in range(-2, 3):
            assert counts(
                range(12), extra_offsets, [500.0] * 12, base_index, [500.0] * 30,
                0.01, lag,
            ) == (12, 12)  # fmt: skip
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 12, 0, None),)
        assert placement.extra_index[5:17] == tuple(range(12))

    def test_samples_whose_extra_value_is_absent_are_not_compared(self) -> None:
        index, base_vals = self._base(30)
        inst = list(range(5, 17))
        extra: list[float | None] = [dist(t + 1) for t in inst[:6]] + [None] * 6
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 1) == (6, 6)
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) == 1

    def test_samples_whose_base_value_is_absent_are_not_compared(self) -> None:
        index, base_vals = self._base(30)
        base_blank: list[float | None] = list(base_vals)
        inst = list(range(5, 17))
        extra = [dist(t + 1) for t in inst[:6]] + [dist(t + 1) for t in inst[6:]]
        for t in range(12, 18):
            base_blank[t] = None
        assert counts(range(12), inst, extra, index, base_blank, 0.01, 1) == (6, 6)
        assert establish_lag(range(12), inst, extra, index, base_blank, 0.01) == 1

    def test_samples_off_the_base_timeline_are_not_compared(self) -> None:
        index = {t: t for t in range(0, 12)}
        base_vals: list[float | None] = [dist(t) for t in range(30)]
        inst = list(range(6, 18))
        extra = [dist(t + 1) for t in inst]
        assert counts(range(12), inst, extra, index, base_vals, 0.01, 1) == (5, 5)
        assert establish_lag(range(12), inst, extra, index, base_vals, 0.01) == 1

    def test_a_sample_without_an_instant_is_skipped(self) -> None:
        index, base_vals = self._base(30)
        inst: list[int | None] = [5, 6, 7, None, 9, 10, 11]
        extra = [
            dist(t + 1) if t is not None else 12345.0 for t in inst
        ]  # distinct from every base value
        assert establish_lag(range(7), inst, extra, index, base_vals, 0.01) == 1

    def test_a_difference_of_half_a_resolution_is_not_a_match(self) -> None:
        index = {t: t for t in range(20)}
        base_vals: list[float | None] = [float(100 + 3 * t) for t in range(20)]
        inst = list(range(5, 10))
        exactly_half = [100.0 + 3 * t + 0.5 for t in inst]
        assert counts(range(5), inst, exactly_half, index, base_vals, 1.0, 0) == (0, 5)
        assert (
            establish_lag(range(5), inst, exactly_half, index, base_vals, 1.0) is None
        )

    def test_a_difference_below_half_a_resolution_matches(self) -> None:
        index = {t: t for t in range(20)}
        base_vals: list[float | None] = [float(100 + 3 * t) for t in range(20)]
        inst = list(range(5, 10))
        near = [100.0 + 3 * t + 0.4 for t in inst]
        assert counts(range(5), inst, near, index, base_vals, 1.0, 0) == (5, 5)
        assert establish_lag(range(5), inst, near, index, base_vals, 1.0) == 0

    def test_a_difference_above_half_a_resolution_does_not_match(self) -> None:
        index = {t: t for t in range(20)}
        base_vals: list[float | None] = [float(100 + 3 * t) for t in range(20)]
        inst = list(range(5, 10))
        far = [100.0 + 3 * t + 0.6 for t in inst]
        assert counts(range(5), inst, far, index, base_vals, 1.0, 0) == (0, 5)
        assert establish_lag(range(5), inst, far, index, base_vals, 1.0) is None

    def test_only_the_stretch_is_read(self) -> None:
        index, base_vals = self._base(40)
        inst = list(range(5, 25))
        # Samples 0-9 match at +1; samples 10-19 are not in the stretch.
        extra = [dist(t + 1) for t in inst[:10]] + [dist(t) + 70.0 for t in inst[10:]]
        assert establish_lag(range(10), inst, extra, index, base_vals, 0.01) == 1
        assert establish_lag(range(10, 20), inst, extra, index, base_vals, 0.01) is None


class TestFallback:
    def test_unmatched_stretch_is_placed_at_exact_timestamps_and_recorded(
        self,
    ) -> None:
        offsets = list(range(30))
        base = make_activity(START, offsets, distance_m=[dist(t) for t in offsets])
        extra_offsets = list(range(3, 15))
        junk = [dist(t) + 70.0 for t in extra_offsets]
        extra = make_activity(START, extra_offsets, distance_m=junk)
        base_index = {t: t for t in offsets}
        for lag in range(-2, 3):
            assert counts(
                range(12), extra_offsets, junk, base_index,
                [dist(t) for t in offsets], 0.01, lag,
            ) == (0, 12)  # fmt: skip
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 12, 0, None),)
        assert placement.extra_index == (
            None, None, None, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
            None, None, None, None, None, None, None, None, None, None,
            None, None, None, None, None,
        )  # fmt: skip

    def test_sample_without_a_whole_second_instant_is_not_placed(self) -> None:
        offsets = list(range(30))
        base = make_activity(START, offsets, distance_m=[dist(t) for t in offsets])
        extra_offsets = [2, 3, 4, 5, 5.5, 6, 7, 8, 9, 10]
        values = [dist(3), dist(4), dist(5), dist(6), 12345.0] + [
            dist(t + 1) for t in (6, 7, 8, 9, 10)
        ]
        extra = make_activity(START, extra_offsets, distance_m=values)
        assert extra.samples.time_s[4] == 5.5
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 10, 1, "distance_m"),)
        # the half-second sample (extra index 4) sits inside the stretch and is
        # placed nowhere; its neighbours place by the lag.
        assert placement.extra_index[3:13] == (0, 1, 2, 3, 5, 6, 7, 8, 9, None)
        assert 4 not in placement.extra_index

    def test_base_without_a_start_has_nothing_to_place_on(self) -> None:
        base = make_activity(None, [0, 1, 2])
        extra = make_activity(START, [0, 1, 2])
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 3, 0, None),)
        assert placement.alignment.hour_shift_s == 0
        assert placement.extra_index == (None, None, None)


class TestPlacement:
    def test_duplicated_base_instants_take_the_first_index(self) -> None:
        base = make_activity(START, [0, 1, 2, 2, 3, 4])
        extra = make_activity(START, [0, 1, 2, 3, 4])
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 5, 0, None),)
        assert placement.extra_index == (0, 1, 2, None, 3, 4)

    def test_a_fallback_stretch_after_a_lagged_one_is_not_lagged(self) -> None:
        base_offsets = list(range(40))
        base = make_activity(
            START, base_offsets, distance_m=[dist(t) for t in base_offsets]
        )
        extra_offsets = list(range(12)) + list(range(20, 32))
        extra = make_activity(
            START,
            extra_offsets,
            distance_m=[dist(t + 1) for t in range(12)] + [None] * 12,
        )
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (
            StretchLag(0, 12, 1, "distance_m"),
            StretchLag(12, 24, 0, None),
        )
        assert placement.extra_index[20:32] == tuple(range(12, 24))

    def test_samples_of_a_stretch_place_in_file_order(self) -> None:
        base = make_activity(START, [0, 1, 2, 3, 4])
        extra = make_activity(START, [0, 1, 2, 2, 3, 4])
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (StretchLag(0, 6, 0, None),)
        assert placement.extra_index == (0, 1, 2, 4, 5)

    def test_two_samples_claiming_one_base_sample_keep_the_first(self) -> None:
        # The base pauses between t=9 and t=12, cutting the continuous extra
        # run in two. Stretch 1 (t 0-11) lags +2, so its t=10 and t=11 land on
        # the base samples at t=12 and t=13; stretch 2 (t 12-25) lags 0 and
        # wants those same two base samples.
        base_offsets = list(range(10)) + list(range(12, 26))
        base = make_activity(
            START, base_offsets, distance_m=[dist(t) for t in base_offsets]
        )
        extra_offsets = list(range(26))
        values = [dist(t + 2) for t in range(12)] + [dist(t) for t in range(12, 26)]
        extra = make_activity(START, extra_offsets, distance_m=values)
        placement = align_extra(base, extra)
        assert placement.alignment.stretches == (
            StretchLag(0, 12, 2, "distance_m"),
            StretchLag(12, 26, 0, "distance_m"),
        )
        assert placement.extra_index == (
            None, None, 0, 1, 2, 3, 4, 5, 6, 7,
            10, 11,
            14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
        )  # fmt: skip
        # samples 8 and 9 land off the base's timeline (t=10, 11), 12 and 13
        # lost their base samples to samples 10 and 11.
        placed = [j for j in placement.extra_index if j is not None]
        assert 8 not in placed and 9 not in placed
        assert 12 not in placed and 13 not in placed
        assert len(placed) == len(set(placed))


class TestHourShiftedPlacement:
    def _pair(self, shift: timedelta) -> tuple[object, object]:
        base_offsets = list(range(10)) + list(range(11, 21))
        base = make_activity(
            START, base_offsets, distance_m=[dist(t) for t in base_offsets]
        )
        values = (
            [dist(t) for t in range(10)] + [123456.0] + [dist(t) for t in range(11, 21)]
        )
        extra = make_activity(START + shift, list(range(21)), distance_m=values)
        return base, extra

    @pytest.mark.parametrize("hours", [1, 36, -1, -36])
    def test_extra_is_moved_toward_the_base_before_splitting(self, hours: int) -> None:
        base, extra = self._pair(timedelta(hours=hours))
        placement = align_extra(base, extra)  # type: ignore[arg-type]
        assert placement.alignment.hour_shift_s == hours * 3600
        assert placement.alignment.stretches == (
            StretchLag(0, 11, 0, "distance_m"),
            StretchLag(11, 21, 0, "distance_m"),
        )
        assert placement.extra_index == (
            0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
            11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        )  # fmt: skip

    @pytest.mark.parametrize("hours", [37, -37])
    def test_beyond_thirty_six_hours_nothing_lines_up(self, hours: int) -> None:
        base, extra = self._pair(timedelta(hours=hours))
        placement = align_extra(base, extra)  # type: ignore[arg-type]
        assert placement.alignment.hour_shift_s == 0
        assert placement.extra_index == (None,) * 20

    def test_one_second_off_a_whole_hour_is_applied_two_is_not(self) -> None:
        base, extra_1 = self._pair(timedelta(hours=1, seconds=1))
        _, extra_2 = self._pair(timedelta(hours=1, seconds=2))
        applied = align_extra(base, extra_1)  # type: ignore[arg-type]
        assert applied.alignment.hour_shift_s == 3600
        assert applied.extra_index[:3] == (0, 1, 2)
        refused = align_extra(base, extra_2)  # type: ignore[arg-type]
        assert refused.alignment.hour_shift_s == 0
        assert refused.extra_index == (None,) * 20

    def test_without_a_shift_the_extra_is_not_moved(self) -> None:
        base, extra = self._pair(timedelta(0))
        placement = align_extra(base, extra)  # type: ignore[arg-type]
        assert placement.alignment.hour_shift_s == 0
        assert placement.extra_index[:3] == (0, 1, 2)
