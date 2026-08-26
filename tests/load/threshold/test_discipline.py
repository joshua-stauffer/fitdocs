"""Contract tests for :mod:`fitdocs.load.threshold.discipline` (task 2.1,
Req 2.1, 2.4, 2.6, 3.1, 3.2, 3.5).

``discipline.py`` is pure data plus two lookups: which sports the threshold
calculator scores (``SUPPORTED_SPORTS``), the coarse modality pre-filter
(``DECLARED_MODALITIES``), and which discipline's benchmark anchors each
channel for a supported sport (``ANCHOR_PLANS`` / ``anchor_plan``).

These tests pin the exact membership of both sets (not merely "non-empty"),
the exact per-sport anchor-plan table by value -- with dedicated negative
assertions against hand-built Walk/Hike-swapped and Run/Ride-swapped tables,
since a real routing defect on a sibling task (walk/hike default sharing)
left an entire suite green -- the identical-key-sets postcondition, the
``KeyError`` precondition for an unsupported sport, and the absence of
``Modality.STRENGTH`` from the declared modality set.
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs.load.threshold.discipline import (
    ANCHOR_PLANS,
    DECLARED_MODALITIES,
    SUPPORTED_SPORTS,
    AnchorPlan,
    anchor_plan,
    is_supported,
)
from fitdocs.model import Modality, Sport


class TestSupportedSports:
    def test_exact_membership(self) -> None:
        assert (
            frozenset({Sport.RUN, Sport.RIDE, Sport.WALK, Sport.HIKE})
            == SUPPORTED_SPORTS
        )

    def test_unsupported_sports_are_excluded(self) -> None:
        # Every Sport member not in the four supported ones must be absent --
        # walked explicitly rather than checking one sport, so a future
        # Sport addition that silently joined SUPPORTED_SPORTS would be
        # caught by test_exact_membership above, and this documents which
        # three today's real enum members are refused.
        for sport in (Sport.SWIM, Sport.ROWING, Sport.WORKOUT):
            assert sport not in SUPPORTED_SPORTS

    def test_is_supported_matches_the_set_for_every_real_sport(self) -> None:
        scanned = 0
        for sport in Sport:
            scanned += 1
            assert is_supported(sport) == (sport in SUPPORTED_SPORTS)
        assert scanned == 7, "the walk over Sport did not see all real members"

    def test_is_supported_true_for_each_supported_sport_individually(self) -> None:
        assert is_supported(Sport.RUN) is True
        assert is_supported(Sport.RIDE) is True
        assert is_supported(Sport.WALK) is True
        assert is_supported(Sport.HIKE) is True

    def test_is_supported_false_for_each_unsupported_sport_individually(self) -> None:
        assert is_supported(Sport.SWIM) is False
        assert is_supported(Sport.ROWING) is False
        assert is_supported(Sport.WORKOUT) is False

    def test_supported_sports_is_a_real_frozenset(self) -> None:
        assert isinstance(SUPPORTED_SPORTS, frozenset)
        with pytest.raises(AttributeError):
            SUPPORTED_SPORTS.add(Sport.SWIM)  # type: ignore[attr-defined]


class TestDeclaredModalities:
    def test_exact_membership(self) -> None:
        assert (
            frozenset({Modality.RUN, Modality.BIKE, Modality.OTHER})
            == DECLARED_MODALITIES
        )

    def test_strength_is_excluded(self) -> None:
        assert Modality.STRENGTH not in DECLARED_MODALITIES

    def test_swim_is_excluded(self) -> None:
        # Swim is not a supported sport either, and Modality.SWIM exists as
        # its own modality (unlike Walk/Hike, which share Modality.OTHER),
        # so nothing needs it declared.
        assert Modality.SWIM not in DECLARED_MODALITIES

    def test_every_real_modality_is_classified_one_way_or_the_other(self) -> None:
        scanned = 0
        for modality in Modality:
            scanned += 1
            declared = modality in DECLARED_MODALITIES
            if modality in (Modality.RUN, Modality.BIKE, Modality.OTHER):
                assert declared is True
            else:
                assert declared is False
        assert scanned == 5, "the walk over Modality did not see all real members"

    def test_declared_modalities_is_a_real_frozenset(self) -> None:
        assert isinstance(DECLARED_MODALITIES, frozenset)
        with pytest.raises(AttributeError):
            DECLARED_MODALITIES.add(Modality.STRENGTH)  # type: ignore[attr-defined]


class TestAnchorPlanTable:
    """Pins ``ANCHOR_PLANS`` by exact value, then adds standalone negative
    assertions distinguishing it from the two hand-built wrong tables the
    task brief calls out by name (Walk/Hike swap, Run/Ride swap)."""

    def _expected(self) -> dict[Sport, AnchorPlan]:
        return {
            Sport.RUN: AnchorPlan(
                ftp=(Sport.RUN,), lthr=(Sport.RUN,), threshold_pace=(Sport.RUN,)
            ),
            Sport.RIDE: AnchorPlan(
                ftp=(Sport.RIDE,), lthr=(Sport.RIDE,), threshold_pace=()
            ),
            Sport.WALK: AnchorPlan(
                ftp=(), lthr=(Sport.WALK, Sport.RUN), threshold_pace=()
            ),
            Sport.HIKE: AnchorPlan(
                ftp=(), lthr=(Sport.HIKE, Sport.RUN), threshold_pace=()
            ),
        }

    def test_full_table_matches_the_documented_plan_exactly(self) -> None:
        assert dict(ANCHOR_PLANS) == self._expected()

    def test_each_entry_matches_individually(self) -> None:
        # Companion to the whole-table check: names each field of each
        # sport's plan explicitly, so a review reading only this test still
        # sees the full table without cross-referencing _expected().
        assert ANCHOR_PLANS[Sport.RUN].ftp == (Sport.RUN,)
        assert ANCHOR_PLANS[Sport.RUN].lthr == (Sport.RUN,)
        assert ANCHOR_PLANS[Sport.RUN].threshold_pace == (Sport.RUN,)

        assert ANCHOR_PLANS[Sport.RIDE].ftp == (Sport.RIDE,)
        assert ANCHOR_PLANS[Sport.RIDE].lthr == (Sport.RIDE,)
        assert ANCHOR_PLANS[Sport.RIDE].threshold_pace == ()

        assert ANCHOR_PLANS[Sport.WALK].ftp == ()
        assert ANCHOR_PLANS[Sport.WALK].lthr == (Sport.WALK, Sport.RUN)
        assert ANCHOR_PLANS[Sport.WALK].threshold_pace == ()

        assert ANCHOR_PLANS[Sport.HIKE].ftp == ()
        assert ANCHOR_PLANS[Sport.HIKE].lthr == (Sport.HIKE, Sport.RUN)
        assert ANCHOR_PLANS[Sport.HIKE].threshold_pace == ()

    def test_table_is_not_equal_to_a_walk_hike_swapped_table(self) -> None:
        # A routing defect on a sibling task (task 1.2) swapped the Walk and
        # Hike keys and left the whole suite green, because the fixture
        # gave both the same value and they share a default elsewhere in
        # this repo. Walk and Hike's lthr chains differ only in their first
        # element, so this hand-built table -- with exactly that one
        # substitution -- must compare unequal to the real one.
        swapped = self._expected()
        swapped[Sport.WALK] = AnchorPlan(
            ftp=(), lthr=(Sport.HIKE, Sport.RUN), threshold_pace=()
        )
        swapped[Sport.HIKE] = AnchorPlan(
            ftp=(), lthr=(Sport.WALK, Sport.RUN), threshold_pace=()
        )
        assert dict(ANCHOR_PLANS) != swapped

    def test_table_is_not_equal_to_a_run_ride_swapped_table(self) -> None:
        swapped = self._expected()
        swapped[Sport.RUN] = AnchorPlan(
            ftp=(Sport.RIDE,), lthr=(Sport.RIDE,), threshold_pace=()
        )
        swapped[Sport.RIDE] = AnchorPlan(
            ftp=(Sport.RUN,), lthr=(Sport.RUN,), threshold_pace=(Sport.RUN,)
        )
        assert dict(ANCHOR_PLANS) != swapped

    def test_walk_and_hike_plans_are_not_equal_to_each_other(self) -> None:
        assert ANCHOR_PLANS[Sport.WALK] != ANCHOR_PLANS[Sport.HIKE]

    def test_run_and_ride_plans_are_not_equal_to_each_other(self) -> None:
        assert ANCHOR_PLANS[Sport.RUN] != ANCHOR_PLANS[Sport.RIDE]

    def test_table_is_not_equal_to_an_ftp_lthr_field_swapped_table(self) -> None:
        # ftp and lthr are tied for Ride (both (RIDE,)) but not for Walk/Hike
        # (ftp is () while lthr is a two-element chain), so a whole-table
        # field swap changes the Walk and Hike entries and must compare
        # unequal to the real table.
        swapped = {
            sport: AnchorPlan(
                ftp=plan.lthr, lthr=plan.ftp, threshold_pace=plan.threshold_pace
            )
            for sport, plan in self._expected().items()
        }
        assert dict(ANCHOR_PLANS) != swapped

    def test_table_is_not_equal_to_an_ftp_pace_field_swapped_table(self) -> None:
        # ftp and threshold_pace are tied for Walk/Hike (both ()) but not
        # for Ride (ftp is (RIDE,) while threshold_pace is ()), so a
        # whole-table field swap changes the Ride entry and must compare
        # unequal to the real table.
        swapped = {
            sport: AnchorPlan(
                ftp=plan.threshold_pace, lthr=plan.lthr, threshold_pace=plan.ftp
            )
            for sport, plan in self._expected().items()
        }
        assert dict(ANCHOR_PLANS) != swapped

    def test_key_set_matches_supported_sports_exactly(self) -> None:
        assert frozenset(ANCHOR_PLANS.keys()) == SUPPORTED_SPORTS

    def test_key_set_would_notice_an_extra_or_missing_sport(self) -> None:
        # Independent of the module's own postcondition assert (which could
        # in principle be stripped by python -O): a table missing an entry,
        # or carrying one SUPPORTED_SPORTS lacks, must not compare equal to
        # the real key set.
        assert frozenset(ANCHOR_PLANS.keys()) != frozenset(
            {Sport.RUN, Sport.RIDE, Sport.WALK}
        )
        assert frozenset(ANCHOR_PLANS.keys()) != frozenset(
            {Sport.RUN, Sport.RIDE, Sport.WALK, Sport.HIKE, Sport.SWIM}
        )

    def test_anchor_plans_mapping_is_immutable(self) -> None:
        with pytest.raises(TypeError):
            ANCHOR_PLANS[Sport.RUN] = ANCHOR_PLANS[Sport.RIDE]  # type: ignore[index]

    def test_anchor_plan_instances_are_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            ANCHOR_PLANS[Sport.RUN].ftp = ()  # type: ignore[misc]


class TestAnchorPlanInvariants:
    """Swept across every supported sport, not spot-checked (design.md
    invariants: no repeat within a chain, non-empty chain starts with the
    activity's own sport)."""

    @pytest.mark.parametrize("sport", [Sport.RUN, Sport.RIDE, Sport.WALK, Sport.HIKE])
    def test_no_chain_contains_a_repeated_discipline(self, sport: Sport) -> None:
        plan = anchor_plan(sport)
        for chain in (plan.ftp, plan.lthr, plan.threshold_pace):
            assert len(chain) == len(set(chain)), f"{sport}: repeat in {chain}"

    @pytest.mark.parametrize("sport", [Sport.RUN, Sport.RIDE, Sport.WALK, Sport.HIKE])
    def test_non_empty_chain_starts_with_its_own_sport(self, sport: Sport) -> None:
        plan = anchor_plan(sport)
        for chain in (plan.ftp, plan.lthr, plan.threshold_pace):
            if chain:
                assert chain[0] == sport, f"{sport}: chain does not start with itself"

    def test_walk_and_hike_have_no_power_anchor(self) -> None:
        assert anchor_plan(Sport.WALK).ftp == ()
        assert anchor_plan(Sport.HIKE).ftp == ()

    def test_walk_and_hike_have_no_pace_anchor(self) -> None:
        assert anchor_plan(Sport.WALK).threshold_pace == ()
        assert anchor_plan(Sport.HIKE).threshold_pace == ()

    def test_walk_and_hike_have_a_two_element_heart_rate_chain(self) -> None:
        assert anchor_plan(Sport.WALK).lthr == (Sport.WALK, Sport.RUN)
        assert anchor_plan(Sport.HIKE).lthr == (Sport.HIKE, Sport.RUN)

    def test_run_and_ride_anchor_only_on_themselves(self) -> None:
        run_plan = anchor_plan(Sport.RUN)
        for chain in (run_plan.ftp, run_plan.lthr, run_plan.threshold_pace):
            assert chain in ((), (Sport.RUN,))
            if chain:
                assert chain == (Sport.RUN,)

        ride_plan = anchor_plan(Sport.RIDE)
        for chain in (ride_plan.ftp, ride_plan.lthr, ride_plan.threshold_pace):
            assert chain in ((), (Sport.RIDE,))
            if chain:
                assert chain == (Sport.RIDE,)


class TestAnchorPlanPrecondition:
    def test_unsupported_sport_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            anchor_plan(Sport.SWIM)

    def test_unsupported_sport_does_not_return_a_default_plan(self) -> None:
        # pytest.raises above already fails the test if anchor_plan softened
        # the refusal into a return value of any kind (default AnchorPlan,
        # None, ...) rather than raising -- this is the same precondition
        # exercised against the other two unsupported real sports, so a fix
        # that only special-cased Swim would still be caught.
        for sport in (Sport.ROWING, Sport.WORKOUT):
            with pytest.raises(KeyError):
                anchor_plan(sport)
