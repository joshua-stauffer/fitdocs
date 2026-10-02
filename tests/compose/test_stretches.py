"""Whole-second instants and stretch cutting (channel-merge 2.1; Req 3.1, 3.2;
design.md § Stretches).

Every instant below is a literal POSIX second built from ``T0``; within one
fixture the instants are pairwise distinct, and every expected value is written
out rather than computed from the code under test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fitdocs.compose.stretches import (
    PAUSE_GAP_S,
    instants,
    resume_instants,
    split_stretches,
)
from tests.compose.builders import make_activity

#: 2026-01-01T00:00:00Z as a POSIX second.
T0 = 1767225600
START = datetime(2026, 1, 1, tzinfo=UTC)


def test_start_literal_is_the_posix_second_the_tests_assume() -> None:
    assert int(START.timestamp()) == T0


def test_pause_gap_is_one_second() -> None:
    assert PAUSE_GAP_S == 1


class TestInstants:
    def test_start_plus_offset_as_posix_second(self) -> None:
        act = make_activity(START, [0, 1, 3, 10])
        assert instants(act) == (T0, T0 + 1, T0 + 3, T0 + 10)

    def test_instants_are_ints(self) -> None:
        act = make_activity(START, [0, 4])
        assert [type(i) for i in instants(act)] == [int, int]

    def test_start_is_part_of_the_instant(self) -> None:
        a = make_activity(START, [0, 5, 9])
        b = make_activity(START + timedelta(seconds=7200), [0, 5, 9])
        assert instants(a) == (T0, T0 + 5, T0 + 9)
        assert instants(b) == (T0 + 7200, T0 + 7205, T0 + 7209)

    def test_offset_zone_does_not_move_the_instant(self) -> None:
        zoned = datetime(2026, 1, 1, 5, tzinfo=timezone(timedelta(hours=5)))
        act = make_activity(zoned, [0, 2])
        assert instants(act) == (T0, T0 + 2)

    def test_non_whole_offset_has_no_instant(self) -> None:
        act = make_activity(START, [0, 1, 2.5, 3, 4.25, 5.5, 6.75])
        assert instants(act) == (T0, T0 + 1, None, T0 + 3, None, None, None)

    def test_round_halves_and_near_wholes_are_not_whole(self) -> None:
        # 2.5 and 3.5 sit on either side of banker's rounding; 4.1 is near a
        # whole second.
        act = make_activity(START, [2.5, 3.5, 4.1])
        assert instants(act) == (None, None, None)

    def test_fractional_start_with_complementary_offset_is_whole(self) -> None:
        start = START.replace(microsecond=500_000)
        act = make_activity(start, [0.5, 1.0, 2.5])
        assert instants(act) == (T0 + 1, None, T0 + 3)

    def test_float_offsets_that_are_whole_count(self) -> None:
        act = make_activity(START, [2.0, 7.0])
        assert instants(act) == (T0 + 2, T0 + 7)

    def test_no_recorded_start_means_no_instants(self) -> None:
        act = make_activity(None, [0, 1, 2])
        assert instants(act) == (None, None, None)

    def test_no_samples_means_no_instants(self) -> None:
        assert instants(make_activity(START, [])) == ()


class TestResumeInstants:
    def test_one_second_step_is_not_a_pause(self) -> None:
        assert resume_instants([100, 101, 102, 103]) == frozenset()

    def test_two_second_step_is_a_pause(self) -> None:
        assert resume_instants([100, 101, 103, 104]) == frozenset({103})

    def test_every_gap_over_one_second_resumes(self) -> None:
        assert resume_instants([100, 105, 106, 112, 113]) == frozenset({105, 112})

    def test_first_instant_is_not_a_resume(self) -> None:
        assert resume_instants([500, 501]) == frozenset()

    def test_none_entries_are_skipped_for_the_previous_instant(self) -> None:
        assert resume_instants([100, None, 101, None, None, 104]) == frozenset({104})

    def test_none_between_adjacent_seconds_does_not_pause(self) -> None:
        assert resume_instants([100, None, 101]) == frozenset()

    def test_leading_none_has_no_previous(self) -> None:
        assert resume_instants([None, 100, 101]) == frozenset()

    def test_empty_and_all_none(self) -> None:
        assert resume_instants([]) == frozenset()
        assert resume_instants([None, None]) == frozenset()


class TestSplitStretches:
    def test_continuous_samples_are_one_stretch(self) -> None:
        extra = [100, 101, 102, 103]
        assert split_stretches(extra, extra) == (range(0, 4),)

    def test_two_second_step_splits_one_second_step_does_not(self) -> None:
        extra = [100, 101, 102, 104, 105, 106]
        base = [100, 101, 102, 103, 104, 105, 106]
        # base is continuous, so the one cut is the extra's own pause at 104
        assert resume_instants(base) == frozenset()
        assert split_stretches(extra, base) == (range(0, 3), range(3, 6))

    def test_base_pause_splits_a_continuous_extra(self) -> None:
        extra = [100, 101, 102, 103, 104, 105]
        base = [100, 101, 102, 104, 105]
        assert resume_instants(extra) == frozenset()
        assert split_stretches(extra, base) == (range(0, 4), range(4, 6))

    def test_extra_pause_the_base_lacks_splits_it(self) -> None:
        extra = [100, 101, 103, 104]
        base = [100, 101, 102, 103, 104]
        assert resume_instants(base) == frozenset()
        assert split_stretches(extra, base) == (range(0, 2), range(2, 4))

    def test_pauses_of_both_files_cut_at_each_distinct_instant(self) -> None:
        extra = [100, 101, 102, 103, 106, 107, 108, 109, 110]
        base = [100, 101, 102, 103, 104, 105, 106, 107, 109, 110]
        assert resume_instants(extra) == frozenset({106})
        assert resume_instants(base) == frozenset({109})
        assert split_stretches(extra, base) == (
            range(0, 4),
            range(4, 7),
            range(7, 9),
        )

    def test_sample_exactly_at_a_resume_instant_opens_the_stretch(self) -> None:
        extra = [100, 101, 102, 104, 105]
        base = [100, 101, 102, 103, 104, 105]
        stretches_ = split_stretches(extra, base)
        assert stretches_ == (range(0, 3), range(3, 5))
        assert 3 in stretches_[1] and 3 not in stretches_[0]

    def test_cut_instant_the_extra_has_no_sample_at(self) -> None:
        # the base resumes at 103; the extra has no sample at that second
        extra = [100, 101, 102, 104, 105]
        base = [100, 101, 103, 104, 105]
        assert resume_instants(extra) == frozenset({104})
        assert resume_instants(base) == frozenset({103})
        assert split_stretches(extra, base) == (
            range(0, 3),
            range(3, 5),
        )

    def test_cut_between_consecutive_extra_samples_leaves_no_empty_range(self) -> None:
        # cuts at 104, 106 and 107: the extra's samples at 101 and 106 straddle 104
        extra = [100, 101, 106, 107]
        base = [100, 101, 102, 104, 105, 107]
        assert resume_instants(base) == frozenset({104, 107})
        assert resume_instants(extra) == frozenset({106})
        assert split_stretches(extra, base) == (range(0, 2), range(2, 3), range(3, 4))

    def test_none_instants_belong_to_no_stretch(self) -> None:
        extra: list[int | None] = [None, 100, 101, None, 103, 104, None]
        base = [100, 101, 102, 103, 104]
        found = split_stretches(extra, base)
        assert found == (range(1, 3), range(4, 6))
        members = {i for r in found for i in r}
        assert 0 not in members and 6 not in members

    def test_all_none_extra_has_no_stretches(self) -> None:
        assert split_stretches([None, None], [100, 101]) == ()

    def test_empty_extra_has_no_stretches(self) -> None:
        assert split_stretches([], [100, 101]) == ()

    def test_none_between_extra_samples_of_one_stretch_stays_inside_it(self) -> None:
        extra: list[int | None] = [100, None, 101]
        assert split_stretches(extra, [100, 101]) == (range(0, 3),)
