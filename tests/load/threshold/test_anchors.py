"""Contract tests for :mod:`fitdocs.load.threshold.anchors` (task 2.3, design:
``BenchmarkResolution``, Req 3.3, 3.4, 3.6, 4.1, 4.2, 4.4, 4.5, 4.6).

``resolve`` is the only module allowed to call ``ProfileView.benchmark`` /
``has_benchmark``; every other module downstream sees only already-resolved
``Benchmark`` objects. These tests exercise it against a call-recording fake
``ProfileView`` that behaves like the real store's per-``(kind, discipline)``
scoping (never falls back on its own) but records every call so the tests can
assert *how* it was asked, not merely what came back -- the one-discipline-
at-a-time and athlete-wide-scope claims cannot be pinned by the return value
alone.

The headline hardware-boundary scenario (a 2024-measured FTP and a 2026-
measured one, each activity resolving its own era) is built with the *older*
benchmark holding the *higher* value, deliberately anti-correlating value and
date, so an implementation that ranked by value rather than by date would
pick the wrong one -- the confounded-fixture trap named in
``change-protocol.md``.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.threshold.anchors import Borrowing, ResolvedAnchors, resolve
from fitdocs.model import Sport


def _bm(
    kind: BenchmarkKind, discipline: Sport | None, value: float, measured_on: date
) -> Benchmark:
    return Benchmark(
        kind=kind, discipline=discipline, value=value, measured_on=measured_on
    )


@dataclasses.dataclass
class _Call:
    method: str
    kind: BenchmarkKind
    discipline: Sport | None
    on: date | None = None


class RecordingProfile:
    """A genuine test double: implements ``ProfileView`` by scoping strictly
    to ``(kind, discipline)`` -- exactly like the real store, no fallback of
    its own -- while recording every call so tests can assert on the call
    pattern, not merely the outcome."""

    def __init__(
        self, entries: dict[tuple[BenchmarkKind, Sport | None], list[Benchmark]]
    ):
        self._entries = entries
        self.calls: list[_Call] = []

    def get_number(self, key: str) -> float | None:
        return None

    def has_benchmark(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        self.calls.append(_Call("has_benchmark", kind, discipline))
        return bool(self._entries.get((kind, discipline)))

    def benchmark(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date | None
    ) -> Benchmark | None:
        self.calls.append(_Call("benchmark", kind, discipline, on))
        assert on is not None
        candidates = [
            entry
            for entry in self._entries.get((kind, discipline), [])
            if entry.measured_on <= on
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda entry: entry.measured_on)


# --- headline: activity date decides, not value (Req 4.1, 4.2, 4.5) --------


class TestHardwareBoundaryDate:
    """A 2024-measured FTP and a 2026-measured FTP, anti-correlated with
    value so a value-ranking implementation would fail this."""

    def _profile(self) -> RecordingProfile:
        return RecordingProfile(
            {
                (BenchmarkKind.FTP_WATTS, Sport.RIDE): [
                    _bm(BenchmarkKind.FTP_WATTS, Sport.RIDE, 260.0, date(2024, 1, 1)),
                    _bm(BenchmarkKind.FTP_WATTS, Sport.RIDE, 150.0, date(2026, 1, 1)),
                ]
            }
        )

    def test_2024_activity_resolves_2024_entry(self) -> None:
        profile = self._profile()
        result = resolve(profile, sport=Sport.RIDE, on=date(2024, 6, 15))
        assert result.ftp == _bm(
            BenchmarkKind.FTP_WATTS, Sport.RIDE, 260.0, date(2024, 1, 1)
        )

    def test_2026_activity_resolves_2026_entry(self) -> None:
        profile = self._profile()
        result = resolve(profile, sport=Sport.RIDE, on=date(2026, 6, 15))
        assert result.ftp == _bm(
            BenchmarkKind.FTP_WATTS, Sport.RIDE, 150.0, date(2026, 1, 1)
        )

    def test_between_the_two_dates_resolves_the_earlier_one(self) -> None:
        # on sits strictly between the two measurement dates -- only the
        # earlier entry qualifies (measured_on <= on); the later, lower-
        # valued entry must not leak in.
        profile = self._profile()
        on = date(2025, 6, 1)
        assert date(2024, 1, 1) < on < date(2026, 1, 1)
        result = resolve(profile, sport=Sport.RIDE, on=on)
        assert result.ftp == _bm(
            BenchmarkKind.FTP_WATTS, Sport.RIDE, 260.0, date(2024, 1, 1)
        )

    def test_reads_no_clock(self) -> None:
        # A fixture date deliberately not equal to today, asserted below, so
        # a mutant that substitutes date.today() for the caller's `on`
        # cannot coincidentally pass.
        profile = self._profile()
        fixture_date = date(2024, 6, 15)
        assert fixture_date != date.today()
        result = resolve(profile, sport=Sport.RIDE, on=fixture_date)
        assert result.ftp == _bm(
            BenchmarkKind.FTP_WATTS, Sport.RIDE, 260.0, date(2024, 1, 1)
        )


# --- own discipline wins over a higher-value fallback (chain order, 3.1-3.4)


class TestOwnDisciplinePreferredOverFallback:
    def test_walk_prefers_its_own_lthr_even_though_it_is_lower_valued(self) -> None:
        # WALK's own entry is deliberately lower-valued than RUN's, so a
        # value-ranking (rather than chain-order) implementation would pick
        # the RUN entry and this would fail.
        profile = RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.WALK): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.WALK, 140.0, date(2020, 1, 1))
                ],
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 160.0, date(2020, 1, 1))
                ],
            }
        )
        result = resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        assert result.lthr == _bm(
            BenchmarkKind.LTHR_BPM, Sport.WALK, 140.0, date(2020, 1, 1)
        )
        assert result.borrowed == ()


# --- borrowing: recorded, names both disciplines, order not swappable ------


class TestBorrowing:
    def _profile(self) -> RecordingProfile:
        return RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 150.0, date(2020, 1, 1))
                ]
            }
        )

    def test_walk_with_only_a_running_threshold_resolves_it_and_records_the_borrowing(
        self,
    ) -> None:
        profile = self._profile()
        result = resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        assert result.lthr == _bm(
            BenchmarkKind.LTHR_BPM, Sport.RUN, 150.0, date(2020, 1, 1)
        )
        assert result.borrowed == (
            Borrowing(
                kind=BenchmarkKind.LTHR_BPM,
                activity_discipline=Sport.WALK,
                anchor_discipline=Sport.RUN,
            ),
        )

    def test_borrowing_names_the_disciplines_in_the_right_slots(self) -> None:
        profile = self._profile()
        result = resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        borrowing = result.borrowed[0]
        # Pinned field-by-field so a transposition of the two Sport-typed
        # fields is caught even though both are the same type.
        assert borrowing.activity_discipline == Sport.WALK
        assert borrowing.anchor_discipline == Sport.RUN
        assert borrowing.activity_discipline != borrowing.anchor_discipline

    def test_hike_borrows_the_same_way(self) -> None:
        profile = RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 155.0, date(2020, 1, 1))
                ]
            }
        )
        result = resolve(profile, sport=Sport.HIKE, on=date(2021, 1, 1))
        assert result.borrowed == (
            Borrowing(
                kind=BenchmarkKind.LTHR_BPM,
                activity_discipline=Sport.HIKE,
                anchor_discipline=Sport.RUN,
            ),
        )


# --- not-on-file vs not-applicable: distinct fixtures, at-most-one ---------


class TestAbsenceClassification:
    def test_measured_after_activity_is_not_applicable_not_not_on_file(self) -> None:
        profile = RecordingProfile(
            {
                (BenchmarkKind.FTP_WATTS, Sport.RUN): [
                    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 250.0, date(2026, 1, 1))
                ]
            }
        )
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        assert result.ftp is None
        assert (BenchmarkKind.FTP_WATTS, Sport.RUN) in result.not_applicable
        assert (BenchmarkKind.FTP_WATTS, Sport.RUN) not in result.not_on_file

    def test_never_measured_is_not_on_file_not_not_applicable(self) -> None:
        profile = RecordingProfile({})
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        assert result.lthr is None
        assert (BenchmarkKind.LTHR_BPM, Sport.RUN) in result.not_on_file
        assert (BenchmarkKind.LTHR_BPM, Sport.RUN) not in result.not_applicable

    def test_a_quantity_never_appears_in_both_absence_lists(self) -> None:
        profile = RecordingProfile(
            {
                (BenchmarkKind.FTP_WATTS, Sport.RUN): [
                    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 250.0, date(2026, 1, 1))
                ]
                # LTHR and THRESHOLD_PACE left entirely absent.
            }
        )
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        on_file_kinds = {kind for kind, _ in result.not_on_file}
        applicable_kinds = {kind for kind, _ in result.not_applicable}
        assert on_file_kinds & applicable_kinds == set()
        # And concretely: FTP is not-applicable, LTHR and threshold pace are
        # not-on-file -- the classification actually differs per kind here.
        assert BenchmarkKind.FTP_WATTS in applicable_kinds
        assert BenchmarkKind.FTP_WATTS not in on_file_kinds
        assert BenchmarkKind.LTHR_BPM in on_file_kinds
        assert BenchmarkKind.THRESHOLD_PACE_S_PER_KM in on_file_kinds


# --- athlete-scoped absence: max/resting HR must never fabricate a default -


class TestAthleteWideAbsence:
    def test_athlete_wide_measured_after_activity_is_not_applicable(self) -> None:
        # Max HR is on file athlete-wide, but only measured after this
        # activity's date -- must resolve to None, not a fabricated default,
        # and must be recorded as not-applicable (not not-on-file).
        profile = RecordingProfile(
            {
                (BenchmarkKind.MAX_HR_BPM, None): [
                    _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2026, 1, 1))
                ],
            }
        )
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        assert result.max_hr is None
        assert result.resting_hr is None
        assert (BenchmarkKind.MAX_HR_BPM, None) in result.not_applicable
        assert (BenchmarkKind.MAX_HR_BPM, None) not in result.not_on_file
        # The tuple's second element is explicitly None -- a set of kinds
        # would not catch it being recorded against `sport` instead.
        matches = [t for t in result.not_applicable if t[0] == BenchmarkKind.MAX_HR_BPM]
        assert matches
        assert matches[0][1] is None

    def test_athlete_wide_never_measured_is_not_on_file(self) -> None:
        profile = RecordingProfile({})
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        assert result.resting_hr is None
        assert (BenchmarkKind.RESTING_HR_BPM, None) in result.not_on_file
        assert (BenchmarkKind.RESTING_HR_BPM, None) not in result.not_applicable
        matches = [
            t for t in result.not_on_file if t[0] == BenchmarkKind.RESTING_HR_BPM
        ]
        assert matches
        assert matches[0][1] is None


# --- chain-wide "on file anywhere" invariant, pinned with a multi-entry ----
# chain that fails to resolve (a single-entry chain cannot pin this) --------


class TestChainWideNotApplicable:
    def test_not_applicable_holds_across_a_multi_entry_chain(self) -> None:
        # WALK's chain for LTHR is (WALK, RUN). Nothing is on file for WALK
        # itself, but RUN carries an entry measured after the activity date
        # -- "on file anywhere in the chain" must still classify this as
        # not-applicable (not not-on-file), recorded against WALK, the
        # activity's own discipline.
        profile = RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 150.0, date(2026, 1, 1))
                ],
            }
        )
        result = resolve(profile, sport=Sport.WALK, on=date(2024, 1, 1))
        assert result.lthr is None
        assert (BenchmarkKind.LTHR_BPM, Sport.WALK) in result.not_applicable
        assert (BenchmarkKind.LTHR_BPM, Sport.WALK) not in result.not_on_file


# --- empty chain: never sought, contributes to neither list (3.5) ---------


class TestEmptyChain:
    def test_walk_ftp_and_threshold_pace_are_never_sought(self) -> None:
        profile = RecordingProfile({})
        result = resolve(profile, sport=Sport.WALK, on=date(2024, 1, 1))
        assert result.ftp is None
        assert result.threshold_pace is None
        queried_kinds = {call.kind for call in profile.calls}
        assert BenchmarkKind.FTP_WATTS not in queried_kinds
        assert BenchmarkKind.THRESHOLD_PACE_S_PER_KM not in queried_kinds
        absent_kinds = {
            kind for kind, _ in (*result.not_on_file, *result.not_applicable)
        }
        assert BenchmarkKind.FTP_WATTS not in absent_kinds
        assert BenchmarkKind.THRESHOLD_PACE_S_PER_KM not in absent_kinds


# --- athlete-wide scope for max/resting HR (3.6) ----------------------------


class TestAthleteWideScope:
    def test_max_and_resting_hr_are_queried_with_discipline_none(self) -> None:
        profile = RecordingProfile(
            {
                (BenchmarkKind.MAX_HR_BPM, None): [
                    _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2020, 1, 1))
                ],
                (BenchmarkKind.RESTING_HR_BPM, None): [
                    _bm(BenchmarkKind.RESTING_HR_BPM, None, 45.0, date(2020, 1, 1))
                ],
            }
        )
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        assert result.max_hr == _bm(
            BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2020, 1, 1)
        )
        assert result.resting_hr == _bm(
            BenchmarkKind.RESTING_HR_BPM, None, 45.0, date(2020, 1, 1)
        )
        # The call pattern itself, not just the outcome: every call for these
        # two kinds must carry discipline=None, and never Sport.RUN -- this
        # distinguishes "the correct scope was passed" from "the store
        # happened to reject a mismatched scope", since this fake never
        # raises on a scope mismatch at all.
        hr_calls = [
            call
            for call in profile.calls
            if call.kind in (BenchmarkKind.MAX_HR_BPM, BenchmarkKind.RESTING_HR_BPM)
        ]
        assert hr_calls, "expected max/resting HR to be queried at all"
        assert all(call.discipline is None for call in hr_calls)
        assert not any(call.discipline == Sport.RUN for call in hr_calls)


# --- one discipline at a time (chain walked, not handed to the store) ------


class TestOneDisciplineAtATime:
    def test_walk_queries_its_own_discipline_before_falling_back_to_running(
        self,
    ) -> None:
        profile = RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 150.0, date(2020, 1, 1))
                ]
            }
        )
        resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        lthr_calls = [
            call for call in profile.calls if call.kind == BenchmarkKind.LTHR_BPM
        ]
        has_benchmark_disciplines = [
            call.discipline for call in lthr_calls if call.method == "has_benchmark"
        ]
        # Both disciplines in the chain are asked individually, in order --
        # never bundled into a single call.
        assert has_benchmark_disciplines == [Sport.WALK, Sport.RUN]

    def test_short_circuits_once_the_own_discipline_is_applicable(self) -> None:
        # WALK's own entry is present and applicable -- RUN must never be
        # consulted at all.
        profile = RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.WALK): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.WALK, 140.0, date(2020, 1, 1))
                ],
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 160.0, date(2020, 1, 1))
                ],
            }
        )
        resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        lthr_calls = [
            call for call in profile.calls if call.kind == BenchmarkKind.LTHR_BPM
        ]
        assert all(call.discipline != Sport.RUN for call in lthr_calls)


# --- five same-typed quantities: transposition is detectable ---------------


class TestFiveQuantitiesAreNotTransposable:
    def _profile(self) -> RecordingProfile:
        return RecordingProfile(
            {
                (BenchmarkKind.FTP_WATTS, Sport.RUN): [
                    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 250.0, date(2023, 1, 1))
                ],
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 160.0, date(2023, 2, 1))
                ],
                (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN): [
                    _bm(
                        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
                        Sport.RUN,
                        300.5,
                        date(2023, 3, 1),
                    )
                ],
                (BenchmarkKind.MAX_HR_BPM, None): [
                    _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2023, 4, 1))
                ],
                (BenchmarkKind.RESTING_HR_BPM, None): [
                    _bm(BenchmarkKind.RESTING_HR_BPM, None, 45.0, date(2023, 5, 1))
                ],
            }
        )

    def test_each_field_holds_its_own_quantity(self) -> None:
        result = resolve(self._profile(), sport=Sport.RUN, on=date(2024, 6, 1))
        assert result.ftp is not None and result.ftp.value == 250.0
        assert result.lthr is not None and result.lthr.value == 160.0
        assert (
            result.threshold_pace is not None and result.threshold_pace.value == 300.5
        )
        assert result.max_hr is not None and result.max_hr.value == 190.0
        assert result.resting_hr is not None and result.resting_hr.value == 45.0
        # Pairwise distinct, so any transposition among the five fields is
        # detectable by value alone.
        values = [
            result.ftp.value,
            result.lthr.value,
            result.threshold_pace.value,
            result.max_hr.value,
            result.resting_hr.value,
        ]
        assert len(set(values)) == 5


# --- repeat calls with equal inputs are equal (4.6) -------------------------


class TestDeterminism:
    def test_repeat_calls_with_equal_inputs_are_equal(self) -> None:
        profile = RecordingProfile(
            {
                (BenchmarkKind.LTHR_BPM, Sport.RUN): [
                    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 150.0, date(2020, 1, 1))
                ],
                (BenchmarkKind.MAX_HR_BPM, None): [
                    _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2020, 1, 1))
                ],
            }
        )
        first = resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        second = resolve(profile, sport=Sport.WALK, on=date(2021, 1, 1))
        # Populated, not vacuous: this result carries a resolved LTHR, a
        # borrowing, a resolved max_hr, and a not-on-file entry for FTP.
        assert first.lthr is not None
        assert first.borrowed != ()
        assert first.max_hr is not None
        assert first.not_on_file != ()
        assert first == second

    def test_resolved_anchors_is_a_real_dataclass_value(self) -> None:
        assert dataclasses.is_dataclass(ResolvedAnchors)


# --- immutability: both dataclasses are frozen, not merely dataclasses -----


class TestImmutability:
    def test_resolved_anchors_is_frozen(self) -> None:
        profile = RecordingProfile({})
        result = resolve(profile, sport=Sport.RUN, on=date(2024, 1, 1))
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.ftp = None  # type: ignore[misc]

    def test_borrowing_is_frozen(self) -> None:
        borrowing = Borrowing(
            kind=BenchmarkKind.LTHR_BPM,
            activity_discipline=Sport.WALK,
            anchor_discipline=Sport.RUN,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            borrowing.kind = BenchmarkKind.FTP_WATTS  # type: ignore[misc]


# --- unsupported sport: precondition, not a reportable outcome -------------


class TestUnsupportedSportPrecondition:
    def test_unsupported_sport_raises_key_error(self) -> None:
        profile = RecordingProfile({})
        with pytest.raises(KeyError):
            resolve(profile, sport=Sport.SWIM, on=date(2024, 1, 1))
