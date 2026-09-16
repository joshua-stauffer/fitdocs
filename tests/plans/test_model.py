"""Tests for the plan model's pure core (training-blocks spec, task 2.1):
identifiers, mesocycle-window derivation, and the row and target checks.
See "PlanModel" in `.kiro/specs/training-blocks/design.md`
(Req 1.4, 1.5, 2.4, 2.6, 2.8, 3.1, 3.2).

One headed section per rule (tasks.md, Test File Ownership: `tests/plans/test_model.py`
-- identifiers, windows, rows and targets -> 2.1; amendments, the trail,
overrides, `build_block` -> 2.2). This task owns only the sections below;
2.2 appends its own headed sections and edits none of these.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.model import Modality, Sport
from fitdocs.plans.model import (
    IDENTIFIER,
    MUTABLE_FIELDS,
    RESERVED_BLOCK_IDS,
    AddOp,
    Amendment,
    AmendmentSpec,
    Block,
    Mesocycle,
    MesocycleTarget,
    Override,
    PlannedWorkout,
    PlanProblem,
    PlanState,
    RemoveOp,
    RowAdded,
    RowChanged,
    RowRemoved,
    TargetChanged,
    TargetOp,
    UpdateOp,
    apply_amendments,
    build_block,
    check_overrides,
    check_rows,
    check_targets,
    is_reserved_block_id,
    mesocycle_number,
    mesocycle_windows,
)


def _row(row_id: str, day: date, *, sport: Sport = Sport.RUN) -> PlannedWorkout:
    return PlannedWorkout(
        id=row_id,
        date=day,
        sport=sport,
        modality=None,
        indoor=None,
        title="Easy run",
        summary="Zone 2",
        prescription="45 minutes easy.",
    )


# -- identifiers ----------------------------------------------------------


class TestIdentifierPattern:
    def test_accepts_lowercase_digits_and_hyphen(self) -> None:
        assert IDENTIFIER.fullmatch("w1-thu-2") is not None

    def test_rejects_uppercase_letter(self) -> None:
        assert IDENTIFIER.fullmatch("W1-thu") is None

    def test_rejects_leading_hyphen(self) -> None:
        assert IDENTIFIER.fullmatch("-w1-thu") is None

    def test_rejects_underscore(self) -> None:
        assert IDENTIFIER.fullmatch("w1_thu") is None


class TestReservedBlockId:
    def test_derived_from_declaration_filename_stem(self) -> None:
        stem = DECLARATION_FILENAME.rsplit(".", 1)[0]
        assert frozenset({stem.lower()}) == RESERVED_BLOCK_IDS

    def test_lowercase_reserved_id_is_reserved(self) -> None:
        assert is_reserved_block_id("agents") is True

    def test_uppercase_reserved_id_is_reserved_case_insensitively(self) -> None:
        # "AGENTS" is fed straight to is_reserved_block_id, never through
        # IDENTIFIER (which would reject it on the uppercase letters alone),
        # so this pins the reserved check on its own.
        assert is_reserved_block_id("AGENTS") is True

    def test_non_reserved_id_is_not_reserved(self) -> None:
        assert is_reserved_block_id("winter-2026") is False


# -- mesocycle windows ------------------------------------------------------


class TestMesocycleWindows:
    def test_exact_multiple_yields_equal_length_windows(self) -> None:
        starts = date(2026, 1, 1)
        ends = date(2026, 1, 28)  # 28 days at length 14 -> two full windows
        windows = mesocycle_windows(starts, ends, 14)
        assert windows == (
            (1, date(2026, 1, 1), date(2026, 1, 14)),
            (2, date(2026, 1, 15), date(2026, 1, 28)),
        )

    def test_short_last_window(self) -> None:
        # 70-day block, 28-day length -> three windows, the last 14 days long.
        starts = date(2026, 1, 1)
        ends = starts + timedelta(days=69)
        windows = mesocycle_windows(starts, ends, 28)
        assert [n for n, _, _ in windows] == [1, 2, 3]
        assert windows[-1] == (3, date(2026, 2, 26), ends)
        assert (windows[-1][2] - windows[-1][1]).days + 1 == 14

    def test_one_day_block(self) -> None:
        starts = date(2026, 1, 1)
        windows = mesocycle_windows(starts, starts, 7)
        assert windows == ((1, starts, starts),)

    def test_length_longer_than_block_yields_one_short_window(self) -> None:
        starts = date(2026, 1, 1)
        ends = date(2026, 1, 10)  # 10 days, length 28
        windows = mesocycle_windows(starts, ends, 28)
        assert windows == ((1, starts, ends),)

    def test_windows_are_contiguous(self) -> None:
        starts = date(2026, 1, 1)
        ends = starts + timedelta(days=69)
        windows = mesocycle_windows(starts, ends, 28)
        for (_, _, last), (_, next_first, _) in zip(windows, windows[1:], strict=False):
            assert next_first == last + timedelta(days=1)

    def test_last_window_ends_on_block_end(self) -> None:
        starts = date(2026, 1, 1)
        ends = starts + timedelta(days=69)
        windows = mesocycle_windows(starts, ends, 28)
        assert windows[-1][2] == ends


class TestMesocycleNumberLookup:
    def test_lookup_at_both_edges_of_a_boundary(self) -> None:
        starts = date(2026, 1, 1)
        assert mesocycle_number(starts, 28, date(2026, 1, 28)) == 1
        assert mesocycle_number(starts, 28, date(2026, 1, 29)) == 2


# -- rows and targets --------------------------------------------------------


class TestCheckRows:
    def test_row_on_last_day_is_in_bounds(self) -> None:
        starts, ends = date(2026, 1, 1), date(2026, 1, 28)
        rows = [_row("w1", ends)]
        assert check_rows(rows, starts=starts, ends=ends, entry="workout") == ()

    def test_row_the_day_after_is_out_of_bounds(self) -> None:
        starts, ends = date(2026, 1, 1), date(2026, 1, 28)
        out = ends + timedelta(days=1)
        rows = [_row("w1", out)]
        problems = check_rows(rows, starts=starts, ends=ends, entry="workout")
        assert len(problems) == 1
        problem = problems[0]
        assert problem.entry == "workout[1] (id w1)"
        assert problem.field == "date"
        assert str(out) in problem.message

    def test_row_on_first_day_is_in_bounds(self) -> None:
        starts, ends = date(2026, 1, 1), date(2026, 1, 28)
        rows = [_row("w1", starts)]
        assert check_rows(rows, starts=starts, ends=ends, entry="workout") == ()

    def test_row_before_first_day_is_out_of_bounds(self) -> None:
        starts, ends = date(2026, 1, 1), date(2026, 1, 28)
        before = starts - timedelta(days=1)
        rows = [_row("w1", before)]
        problems = check_rows(rows, starts=starts, ends=ends, entry="workout")
        assert len(problems) == 1

    def test_names_the_row_by_position_and_id(self) -> None:
        starts, ends = date(2026, 1, 1), date(2026, 1, 28)
        out = ends + timedelta(days=1)
        rows = [_row("w-good", starts), _row("w-bad", out)]
        problems = check_rows(rows, starts=starts, ends=ends, entry="workout")
        assert len(problems) == 1
        assert problems[0].entry == "workout[2] (id w-bad)"


class TestCheckTargets:
    def test_number_within_range_is_valid(self) -> None:
        targets = (MesocycleTarget(1, 400.0, "base"),)
        assert check_targets(targets, count=3) == ()

    def test_number_at_upper_edge_of_range_is_valid(self) -> None:
        # count itself (the last derived mesocycle number) must be accepted,
        # not just numbers strictly below it.
        targets = (MesocycleTarget(3, 400.0, "peak"),)
        assert check_targets(targets, count=3) == ()

    def test_number_outside_range_names_the_number(self) -> None:
        targets = (MesocycleTarget(4, None, "peak"),)
        problems = check_targets(targets, count=3)
        assert len(problems) == 1
        assert problems[0].entry == "mesocycle[4]"
        assert problems[0].field == "number"
        assert "4" in problems[0].message

    def test_number_zero_is_outside_range_and_names_the_number(self) -> None:
        # The lower edge: 0 is the smallest int a careless "0 <=" bound
        # would wrongly accept; the lowest valid number is 1.
        targets = (MesocycleTarget(0, None, "prep"),)
        problems = check_targets(targets, count=3)
        assert len(problems) == 1
        assert problems[0].entry == "mesocycle[0]"
        assert problems[0].field == "number"
        assert "0" in problems[0].message

    def test_duplicate_number_names_the_number(self) -> None:
        # Both numbers are in range (count=3), so only the duplicate rule
        # can be responsible for this problem -- not the range rule.
        targets = (
            MesocycleTarget(2, 100.0, None),
            MesocycleTarget(2, 200.0, None),
        )
        problems = check_targets(targets, count=3)
        assert len(problems) == 1
        assert problems[0].entry == "mesocycle[2]"
        assert "2" in problems[0].message


# -- PlanProblem.describe() --------------------------------------------------


class TestPlanProblemDescribe:
    def test_describe_matches_design_shape(self) -> None:
        problem = PlanProblem(
            entry="workout[2] (id w1-thu)",
            field="date",
            message="2026-12-20 is outside 2026-09-21..2026-12-13",
        )
        assert problem.describe() == (
            "workout[2] (id w1-thu) / date: "
            "2026-12-20 is outside 2026-09-21..2026-12-13"
        )

    def test_describe_without_field(self) -> None:
        problem = PlanProblem(entry="file", field=None, message="could not be read")
        assert problem.describe() == "file: could not be read"


# -- PlanState lookups --------------------------------------------------------


class TestPlanStateLookups:
    def test_row_found_by_id(self) -> None:
        w1, w2 = _row("w1", date(2026, 1, 1)), _row("w2", date(2026, 1, 2))
        state = PlanState(rows=(w1, w2), targets=())
        assert state.row("w2") is w2

    def test_row_missing_returns_none(self) -> None:
        state = PlanState(rows=(), targets=())
        assert state.row("nope") is None

    def test_target_found_by_number(self) -> None:
        # Two targets (ascending numbers, per PlanState.targets' invariant);
        # look up the second so "first" and "the one with that number" are
        # not the same answer.
        t1 = MesocycleTarget(1, 300.0, "base")
        t2 = MesocycleTarget(2, 500.0, "build")
        state = PlanState(rows=(), targets=(t1, t2))
        assert state.target(2) is t2

    def test_target_missing_returns_none(self) -> None:
        state = PlanState(rows=(), targets=())
        assert state.target(1) is None


# -- Mesocycle length and shortness ------------------------------------------


class TestMesocycleProperties:
    def test_days_counts_inclusive_span(self) -> None:
        meso = Mesocycle(
            number=1,
            starts=date(2026, 1, 1),
            ends=date(2026, 1, 14),
            nominal_days=28,
            target_load=None,
            focus=None,
            workouts=(),
        )
        assert meso.days == 14

    def test_is_short_when_days_below_nominal(self) -> None:
        meso = Mesocycle(
            number=3,
            starts=date(2026, 2, 26),
            ends=date(2026, 3, 11),
            nominal_days=28,
            target_load=None,
            focus=None,
            workouts=(),
        )
        assert meso.days == 14
        assert meso.is_short is True

    def test_is_not_short_when_days_equal_nominal(self) -> None:
        meso = Mesocycle(
            number=1,
            starts=date(2026, 1, 1),
            ends=date(2026, 1, 28),
            nominal_days=28,
            target_load=None,
            focus=None,
            workouts=(),
        )
        assert meso.days == 28
        assert meso.is_short is False


# -- 2.2 appends its own headed sections below (amendments, the trail,
#    overrides, build_block); nothing above is theirs to edit.

# Shared bounds for the sections below: two 14-day mesocycles.
_STARTS = date(2026, 1, 1)
_ENDS = date(2026, 1, 28)
_LENGTH = 14
_COUNT = 2


def _base_state() -> PlanState:
    return PlanState(
        rows=(_row("w1", date(2026, 1, 2)), _row("w2", date(2026, 1, 16))),
        targets=(),
    )


# -- amendments: total validation within one amendment -----------------------


class TestTotalValidationWithinOneAmendment:
    def test_two_independent_invalid_ops_are_both_reported(self) -> None:
        # Req 2.2: every problem determinable in one pass is reported, not
        # just the first. Two unrelated invalid ops in the same amendment
        # must both surface.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="two mistakes at once",
            ops=(
                UpdateOp(row_id="ghost", fields={"title": "x"}),
                RemoveOp(row_id="also-ghost"),
            ),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 2
        assert any("ghost)" in p.entry and "update" in p.entry for p in problems)
        assert any("also-ghost" in p.entry and "remove" in p.entry for p in problems)


# -- amendments: UpdateOp --------------------------------------------------


class TestUpdateOp:
    def test_valid_update_changes_the_named_field(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="swap the session",
            ops=(UpdateOp(row_id="w1", fields={"title": "Tempo run"}),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 1
        (change,) = amendments[0].changes
        assert isinstance(change, RowChanged)
        assert change.before.title == "Easy run"
        assert change.after.title == "Tempo run"
        assert states[-1].row("w1") is not None
        assert states[-1].row("w1").title == "Tempo run"  # type: ignore[union-attr]

    def test_unknown_row_id_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="ghost", fields={"title": "Tempo run"}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].entry == "amendment[1].update[0] (id ghost)"

    def test_empty_fields_changes_no_field(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert "no field" in problems[0].message

    def test_field_set_to_its_current_value_changes_no_field(self) -> None:
        # Non-empty fields, but the stated value equals the row's current
        # value -- distinct from the empty-dict case above.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={"title": "Easy run"}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert "no field" in problems[0].message

    def test_unknown_field_key_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={"notes": "extra"}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "fields"

    def test_id_is_not_a_mutable_field(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={"id": "w1-renamed"}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "fields"

    def test_moving_a_row_out_of_bounds_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={"date": _ENDS + timedelta(days=1)}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "date"

    def test_moving_a_row_to_exactly_ends_is_valid(self) -> None:
        # The upper edge is inclusive -- distinct from the day-after-ends
        # problem fixture above.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="push to the last day",
            ops=(UpdateOp(row_id="w1", fields={"date": _ENDS}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 1

    def test_moving_a_row_to_exactly_starts_is_valid(self) -> None:
        # The lower edge is inclusive too -- every other bounds fixture in
        # this section only exercises the upper edge (_ENDS / _ENDS + 1),
        # so this and the fixture below are the only ones that can red a
        # lower-bound mutation in the shared `_row_bounds_problem` helper.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="pull to the first day",
            ops=(UpdateOp(row_id="w1", fields={"date": _STARTS}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 1

    def test_moving_a_row_before_starts_is_a_problem(self) -> None:
        original = _base_state()
        before_starts = _STARTS - timedelta(days=1)
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={"date": before_starts}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "date"
        assert problems[0].entry == "amendment[1].update[0] (id w1)"

    def test_adding_a_modality_to_a_run_row_is_a_problem(self) -> None:
        original = _base_state()  # w1 is a Sport.RUN row
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(UpdateOp(row_id="w1", fields={"modality": Modality.STRENGTH}),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "modality"

    def test_update_on_a_non_first_row_leaves_other_rows_untouched(self) -> None:
        # Updating w2 (not the first row) must not disturb w1 -- pins that
        # the update is applied at w2's own position, not row 0.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="only touch w2",
            ops=(UpdateOp(row_id="w2", fields={"title": "Long run"}),),
        )
        states, _, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert states[-1].row("w2").title == "Long run"  # type: ignore[union-attr]
        assert states[-1].row("w1") == original.rows[0]

    def test_mixed_update_one_field_unchanged_one_changed_is_valid(self) -> None:
        # fields carries one key equal to the current value ("title") and
        # one that actually changes ("summary") -- at least one field
        # differs, so this is valid, and the unchanged field is untouched
        # in `after` too.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="tweak the summary only",
            ops=(
                UpdateOp(
                    row_id="w1", fields={"title": "Easy run", "summary": "New plan"}
                ),
            ),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        (change,) = amendments[0].changes
        assert isinstance(change, RowChanged)
        assert change.after.summary == "New plan"
        assert change.after.title == "Easy run"


# -- amendments: AddOp ------------------------------------------------------


class TestAddOp:
    def test_valid_add_uses_a_fresh_id(self) -> None:
        original = _base_state()
        new_row = _row("w3", date(2026, 1, 3))
        spec = AmendmentSpec(
            date=date(2026, 1, 5), reason="fit in a session", ops=(AddOp(row=new_row),)
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        (change,) = amendments[0].changes
        assert isinstance(change, RowAdded)
        assert change.row is new_row
        assert states[-1].row("w3") is new_row

    def test_add_reusing_an_id_already_in_the_original_plan_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(AddOp(row=_row("w1", date(2026, 1, 3))),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].entry == "amendment[1].add[0] (id w1)"

    def test_add_dated_outside_bounds_is_a_problem(self) -> None:
        # F1: an AddOp is subject to the same date-bounds rule as an
        # UpdateOp, not only the id-uniqueness rule -- otherwise the added
        # row lands in current.rows but no mesocycle, breaking build_block's
        # postcondition.
        original = _base_state()
        out_of_bounds = _ENDS + timedelta(days=1)
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(AddOp(row=_row("w3", out_of_bounds)),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "date"
        assert problems[0].entry == "amendment[1].add[0] (id w3)"

    def test_add_dated_exactly_on_ends_is_valid(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5), reason="fits", ops=(AddOp(row=_row("w3", _ENDS)),)
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 1

    def test_add_dated_exactly_on_starts_is_valid(self) -> None:
        # The lower edge, mirroring the ends-edge fixture above -- neither
        # existing AddOp bounds fixture exercises the lower edge, so this
        # and the fixture below are the only ones that can red a
        # lower-bound mutation in the shared `_row_bounds_problem` helper.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5), reason="fits", ops=(AddOp(row=_row("w3", _STARTS)),)
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 1

    def test_add_dated_before_starts_is_a_problem(self) -> None:
        original = _base_state()
        before_starts = _STARTS - timedelta(days=1)
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(AddOp(row=_row("w3", before_starts)),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "date"
        assert problems[0].entry == "amendment[1].add[0] (id w3)"

    def test_add_with_modality_on_a_run_row_is_a_problem(self) -> None:
        # F1: identical row shape is rejected via UpdateOp
        # (test_adding_a_modality_to_a_run_row_is_a_problem above); an
        # AddOp must apply the same rule, not just id-uniqueness.
        original = _base_state()
        bad_row = _row("w3", date(2026, 1, 3))
        bad_row = replace(bad_row, modality=Modality.STRENGTH)
        spec = AmendmentSpec(
            date=date(2026, 1, 5), reason="oops", ops=(AddOp(row=bad_row),)
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "modality"

    def test_add_reusing_a_removed_ids_history_entry_is_still_a_problem(self) -> None:
        # Req 3.4/2.9 "history": add w3, remove w3, add w3 again -- the
        # third op must still be a problem, naming the third amendment.
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 5),
                reason="add",
                ops=(AddOp(row=_row("w3", date(2026, 1, 3))),),
            ),
            AmendmentSpec(
                date=date(2026, 1, 6), reason="remove", ops=(RemoveOp(row_id="w3"),)
            ),
            AmendmentSpec(
                date=date(2026, 1, 7),
                reason="add again, wrongly",
                ops=(AddOp(row=_row("w3", date(2026, 1, 4))),),
            ),
        ]
        _, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert len(amendments) == 2  # only the add and the remove applied
        assert any(p.entry == "amendment[3].add[0] (id w3)" for p in problems)

    def test_adding_the_same_id_twice_in_one_amendment_is_a_problem(self) -> None:
        # The second op reusing the id an earlier op in the *same*
        # amendment just added must also be rejected -- proves the
        # trial-used-ids set is updated as ops apply, not only across
        # amendments.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="duplicate within one amendment",
            ops=(
                AddOp(row=_row("w3", date(2026, 1, 3))),
                AddOp(row=_row("w3", date(2026, 1, 4))),
            ),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].entry == "amendment[1].add[1] (id w3)"


# -- amendments: RemoveOp ----------------------------------------------------


class TestRemoveOp:
    def test_valid_remove_takes_the_row_out(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5), reason="cancel it", ops=(RemoveOp(row_id="w2"),)
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        (change,) = amendments[0].changes
        assert isinstance(change, RowRemoved)
        assert change.row.id == "w2"
        assert states[-1].row("w2") is None

    def test_removing_an_unknown_id_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5), reason="cancel it", ops=(RemoveOp(row_id="ghost"),)
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].entry == "amendment[1].remove[0] (id ghost)"


# -- amendments: TargetOp ----------------------------------------------------


class TestTargetOp:
    def test_target_on_an_untargeted_mesocycle_is_valid(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="set a target",
            ops=(TargetOp(number=1, target_load=400.0, focus="base"),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        (change,) = amendments[0].changes
        assert isinstance(change, TargetChanged)
        assert change.before == MesocycleTarget(1, None, None)
        assert change.after == MesocycleTarget(1, 400.0, "base")
        assert states[-1].target(1) == MesocycleTarget(1, 400.0, "base")

    def test_target_insertion_keeps_targets_ascending_when_number_sorts_in_the_middle(
        self,
    ) -> None:
        # Three mesocycles, existing targets for 1 and 3; the new TargetOp
        # names 2, which must land *between* them, not be appended last.
        original = PlanState(
            rows=(),
            targets=(
                MesocycleTarget(1, 300.0, "base"),
                MesocycleTarget(3, 600.0, "peak"),
            ),
        )
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="set the middle target",
            ops=(TargetOp(number=2, target_load=450.0, focus=None),),
        )
        states, _, problems = apply_amendments(
            original, [spec], starts=date(2026, 1, 1), ends=date(2026, 3, 1), count=3
        )
        assert problems == ()
        assert [t.number for t in states[-1].targets] == [1, 2, 3]

    def test_target_op_states_only_one_field_keeps_the_other_current(self) -> None:
        # The mesocycle already has a stated focus and no load; the op sets
        # only the load, so the focus must survive unchanged.
        original = PlanState(rows=(), targets=(MesocycleTarget(1, None, "base"),))
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="set the load",
            ops=(TargetOp(number=1, target_load=500.0, focus=None),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        (change,) = amendments[0].changes
        assert isinstance(change, TargetChanged)
        assert change.after == MesocycleTarget(1, 500.0, "base")

    def test_target_op_stating_only_focus_keeps_the_current_load(self) -> None:
        # The reverse of the fixture above: the mesocycle already has a
        # stated load and no focus; the op sets only the focus, so the
        # load must survive unchanged (pins that load isn't wrongly reset
        # to None whenever only focus is stated).
        original = PlanState(rows=(), targets=(MesocycleTarget(1, 400.0, None),))
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="set the focus",
            ops=(TargetOp(number=1, target_load=None, focus="peak"),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        (change,) = amendments[0].changes
        assert isinstance(change, TargetChanged)
        assert change.after == MesocycleTarget(1, 400.0, "peak")

    def test_target_number_out_of_range_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(TargetOp(number=5, target_load=400.0, focus=None),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1
        assert problems[0].field == "number"

    def test_target_with_neither_field_stated_is_a_problem(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="oops",
            ops=(TargetOp(number=1, target_load=None, focus=None),),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert len(problems) == 1


# -- amendments: date order, the stop rule, ordinals -------------------------


class TestMutableFields:
    def test_mutable_fields_spelling(self) -> None:
        # Every PlannedWorkout field except `id`, which identifies the row
        # rather than describing it (design.md "PlanModel" Contracts).
        assert MUTABLE_FIELDS == (
            "date",
            "sport",
            "modality",
            "indoor",
            "title",
            "summary",
            "prescription",
        )


class TestAmendmentOrderAndStop:
    def test_ordinals_are_one_based_in_file_order(self) -> None:
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 5),
                reason="first",
                ops=(UpdateOp(row_id="w1", fields={"title": "Tempo"}),),
            ),
            AmendmentSpec(
                date=date(2026, 1, 6),
                reason="second",
                ops=(UpdateOp(row_id="w2", fields={"title": "Long run"}),),
            ),
        ]
        _, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert isinstance(amendments[0], Amendment)
        assert [a.ordinal for a in amendments] == [1, 2]
        assert [a.date for a in amendments] == [date(2026, 1, 5), date(2026, 1, 6)]
        assert [a.reason for a in amendments] == ["first", "second"]

    def test_equal_dates_are_valid(self) -> None:
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 5),
                reason="first",
                ops=(UpdateOp(row_id="w1", fields={"title": "Tempo"}),),
            ),
            AmendmentSpec(
                date=date(2026, 1, 5),
                reason="second, same day",
                ops=(UpdateOp(row_id="w2", fields={"title": "Long run"}),),
            ),
        ]
        _, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 2

    def test_descending_date_pair_is_a_problem(self) -> None:
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 10),
                reason="first",
                ops=(UpdateOp(row_id="w1", fields={"title": "Tempo"}),),
            ),
            AmendmentSpec(
                date=date(2026, 1, 3),
                reason="earlier than the first, wrongly",
                ops=(UpdateOp(row_id="w2", fields={"title": "Long run"}),),
            ),
        ]
        _, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert len(amendments) == 1  # only the first was applied
        assert any(p.entry == "amendment[2]" and p.field == "date" for p in problems)

    def test_stop_rule_never_reports_a_spurious_unknown_id_for_a_never_added_row(
        self,
    ) -> None:
        # amendment[1] fails outright (unknown row). amendment[2] references
        # an id ("w-new") that amendment[1] would have added had it
        # succeeded. amendment[2] must never be independently checked, so
        # no problem may name "w-new" -- only the "not checked" problem.
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 5),
                reason="fails",
                ops=(UpdateOp(row_id="ghost", fields={"title": "x"}),),
            ),
            AmendmentSpec(
                date=date(2026, 1, 6),
                reason="would reference the never-added row",
                ops=(UpdateOp(row_id="w-new", fields={"title": "y"}),),
            ),
        ]
        states, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert states == (original,)
        assert not any("w-new" in p.entry for p in problems)
        assert any(
            p.entry == "amendment[2..2]" and p.message == "not checked"
            for p in problems
        )

    def test_not_checked_names_the_full_remaining_range(self) -> None:
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 5),
                reason="fails",
                ops=(UpdateOp(row_id="ghost", fields={"title": "x"}),),
            ),
            AmendmentSpec(date=date(2026, 1, 6), reason="skipped", ops=()),
            AmendmentSpec(date=date(2026, 1, 7), reason="also skipped", ops=()),
        ]
        _, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert amendments == ()
        assert any(
            p.entry == "amendment[2..3]" and p.message == "not checked"
            for p in problems
        )

    def test_remove_then_readd_the_same_id_is_a_problem(self) -> None:
        original = _base_state()
        specs = [
            AmendmentSpec(
                date=date(2026, 1, 5), reason="remove it", ops=(RemoveOp(row_id="w1"),)
            ),
            AmendmentSpec(
                date=date(2026, 1, 6),
                reason="add it back, wrongly",
                ops=(AddOp(row=_row("w1", date(2026, 1, 6))),),
            ),
        ]
        states, amendments, problems = apply_amendments(
            original, specs, starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert len(amendments) == 1  # only the remove was applied
        assert any(p.entry == "amendment[2].add[0] (id w1)" for p in problems)

    def test_no_specs_returns_only_the_original_state(self) -> None:
        original = _base_state()
        states, amendments, problems = apply_amendments(
            original, [], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert states == (original,)
        assert states[0] is original
        assert amendments == ()
        assert problems == ()

    def test_states_zero_is_the_original_by_identity(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="anything",
            ops=(UpdateOp(row_id="w1", fields={"title": "Tempo"}),),
        )
        states, _, _ = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert states[0] is original


# -- the trail ----------------------------------------------------------------


class TestRevisionTrail:
    def test_one_move_one_add_one_remove_one_target_change_yields_four_records(
        self,
    ) -> None:
        original = _base_state()
        moved_date = date(2026, 1, 20)
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="a busy amendment",
            ops=(
                UpdateOp(row_id="w1", fields={"date": moved_date}),
                AddOp(row=_row("w3", date(2026, 1, 3))),
                RemoveOp(row_id="w2"),
                TargetOp(number=1, target_load=500.0, focus=None),
            ),
        )
        _, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        assert len(amendments) == 1
        changes = amendments[0].changes
        assert len(changes) == 4

        moved, added, removed, targeted = changes
        assert isinstance(moved, RowChanged)
        assert moved.before.date == date(2026, 1, 2)
        assert moved.after.date == moved_date

        assert isinstance(added, RowAdded)
        assert added.row.id == "w3"

        assert isinstance(removed, RowRemoved)
        assert removed.row.id == "w2"
        assert removed.row.date == date(2026, 1, 16)

        assert isinstance(targeted, TargetChanged)
        assert targeted.before == MesocycleTarget(1, None, None)
        assert targeted.after == MesocycleTarget(1, 500.0, None)


# -- overrides ------------------------------------------------------------


class TestCheckOverrides:
    def test_override_dated_before_the_amendment_that_adds_its_row_is_a_problem(
        self,
    ) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 10),
            reason="add a session",
            ops=(AddOp(row=_row("w3", date(2026, 1, 12))),),
        )
        states, amendments, _ = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        override = Override(
            date=date(2026, 1, 5),
            row_id="w3",
            stems=("w3-run",),
            skipped=False,
            reason=None,
        )
        problems = check_overrides(states, amendments, [override])
        assert len(problems) == 1
        assert problems[0].entry == "override[0] (id w3)"

    def test_override_dated_on_the_same_day_as_the_amendment_is_valid(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 10),
            reason="add a session",
            ops=(AddOp(row=_row("w3", date(2026, 1, 12))),),
        )
        states, amendments, _ = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        override = Override(
            date=date(2026, 1, 10),
            row_id="w3",
            stems=("w3-run",),
            skipped=False,
            reason=None,
        )
        problems = check_overrides(states, amendments, [override])
        assert problems == ()

    def test_override_naming_an_original_row_is_valid_from_the_start(self) -> None:
        original = _base_state()
        states, amendments, _ = apply_amendments(
            original, [], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        override = Override(
            date=date(2025, 1, 1), row_id="w1", stems=(), skipped=True, reason="rest"
        )
        problems = check_overrides(states, amendments, [override])
        assert problems == ()


# -- build_block ----------------------------------------------------------


class TestBuildBlock:
    def test_a_moved_row_is_placed_by_its_current_date_across_a_boundary(self) -> None:
        original = _base_state()  # w1 starts in mesocycle 1 (Jan 2)
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="push it later",
            ops=(UpdateOp(row_id="w1", fields={"date": date(2026, 1, 20)}),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        block = build_block(
            id="winter",
            title="Winter block",
            starts=_STARTS,
            ends=_ENDS,
            goal="Base fitness",
            mesocycle_days=_LENGTH,
            original=original,
            current=states[-1],
            amendments=amendments,
            overrides=(),
        )
        assert isinstance(block, Block)
        assert block.mesocycle_of(date(2026, 1, 20)) == 2
        assert "w1" not in [w.id for w in block.mesocycles[0].workouts]
        assert "w1" in [w.id for w in block.mesocycles[1].workouts]

    def test_two_workouts_on_one_day_render_in_source_order_not_id_order(self) -> None:
        # Ids sort opposite to their source/current-row positions.
        first_by_position = _row("w2-b", date(2026, 1, 5))
        second_by_position = _row("w2-a", date(2026, 1, 5))
        current = PlanState(rows=(first_by_position, second_by_position), targets=())
        block = build_block(
            id="winter",
            title="Winter block",
            starts=_STARTS,
            ends=_ENDS,
            goal="Base fitness",
            mesocycle_days=_LENGTH,
            original=current,
            current=current,
            amendments=(),
            overrides=(),
        )
        assert block.mesocycles[0].workouts == (first_by_position, second_by_position)

    def test_sum_of_mesocycle_row_counts_equals_current_row_count(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="add and remove",
            ops=(
                AddOp(row=_row("w3", date(2026, 1, 20))),
                RemoveOp(row_id="w2"),
            ),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        block = build_block(
            id="winter",
            title="Winter block",
            starts=_STARTS,
            ends=_ENDS,
            goal="Base fitness",
            mesocycle_days=_LENGTH,
            original=original,
            current=states[-1],
            amendments=amendments,
            overrides=(),
        )
        total_in_mesocycles = sum(len(m.workouts) for m in block.mesocycles)
        assert total_in_mesocycles == len(block.current.rows)
        assert total_in_mesocycles == 2  # w1 kept, w2 removed, w3 added

    def test_added_row_follows_original_rows_within_the_same_day(self) -> None:
        original_row = _row("w-orig", date(2026, 1, 5))
        current = PlanState(rows=(original_row,), targets=())
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="fit one more in",
            ops=(AddOp(row=_row("w-added", date(2026, 1, 5))),),
        )
        states, amendments, problems = apply_amendments(
            current, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        block = build_block(
            id="winter",
            title="Winter block",
            starts=_STARTS,
            ends=_ENDS,
            goal="Base fitness",
            mesocycle_days=_LENGTH,
            original=current,
            current=states[-1],
            amendments=amendments,
            overrides=(),
        )
        assert [w.id for w in block.mesocycles[0].workouts] == ["w-orig", "w-added"]

    def test_mesocycle_target_load_and_focus_come_from_current_not_original(
        self,
    ) -> None:
        # A TargetOp sets mesocycle 1's target; mesocycle 2 stays untargeted.
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="set the base target",
            ops=(TargetOp(number=1, target_load=500.0, focus="base"),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        block = build_block(
            id="winter",
            title="Winter block",
            starts=_STARTS,
            ends=_ENDS,
            goal="Base fitness",
            mesocycle_days=_LENGTH,
            original=original,
            current=states[-1],
            amendments=amendments,
            overrides=(),
        )
        assert block.mesocycles[0].target_load == 500.0
        assert block.mesocycles[0].focus == "base"
        assert block.mesocycles[1].target_load is None
        assert block.mesocycles[1].focus is None

    def test_block_wiring_carries_every_constructor_argument_through(self) -> None:
        original = _base_state()
        spec = AmendmentSpec(
            date=date(2026, 1, 5),
            reason="move it",
            ops=(UpdateOp(row_id="w1", fields={"title": "Tempo"}),),
        )
        states, amendments, problems = apply_amendments(
            original, [spec], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        assert problems == ()
        override = Override(
            date=date(2026, 1, 16),
            row_id="w2",
            stems=("w2-run",),
            skipped=False,
            reason=None,
        )
        current = states[-1]
        block = build_block(
            id="winter-2026",
            title="Winter Block",
            starts=_STARTS,
            ends=_ENDS,
            goal="Base fitness",
            mesocycle_days=_LENGTH,
            original=original,
            current=current,
            amendments=amendments,
            overrides=(override,),
        )
        assert block.id == "winter-2026"
        assert block.title == "Winter Block"
        assert block.goal == "Base fitness"
        assert block.starts == _STARTS
        assert block.ends == _ENDS
        assert block.mesocycle_days == _LENGTH
        assert block.original is original
        assert block.current is current
        assert block.amendments == tuple(amendments)
        assert len(block.amendments) > 0
        assert block.overrides == (override,)
        assert block.days == 28


# -- overrides: "nothing else is judged" -------------------------------------


class TestOverridesJudgeOnlyExistence:
    def test_override_with_stems_and_skipped_both_set_is_not_judged(self) -> None:
        # Req 3.8: nothing about an override besides row-id existence is
        # this module's to judge -- an internally-contradictory override
        # (both a logged-workout identifier *and* skipped=True) still
        # passes as long as the row exists as of the override's date.
        original = _base_state()
        override = Override(
            date=date(2026, 1, 2),
            row_id="w1",
            stems=("w1-run",),
            skipped=True,
            reason="contradictory but not this module's to judge",
        )
        states, amendments, _ = apply_amendments(
            original, [], starts=_STARTS, ends=_ENDS, count=_COUNT
        )
        problems = check_overrides(states, amendments, [override])
        assert problems == ()
