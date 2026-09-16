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

from datetime import date, timedelta

from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.model import Sport
from fitdocs.plans.model import (
    IDENTIFIER,
    RESERVED_BLOCK_IDS,
    Mesocycle,
    MesocycleTarget,
    PlannedWorkout,
    PlanProblem,
    PlanState,
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
