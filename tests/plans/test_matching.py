"""Tests for `fitdocs.plans.matching` (plan-resolution spec, task 2.2). See
"Matcher" in `.kiro/specs/plan-resolution/design.md` (Req 2.1-2.7, 3.1-3.9,
4.1-4.4).

Task File Ownership: this module belongs to task 2.2 alone (tasks.md, Test
File Ownership). Every block is built as inline TOML text through the
wave-1 parser `parse_block` (no fixture file, no `tests/plans/conftest.py`
-- 2.2 and 2.3 are parallel and would both need one); every logged workout
is built directly through `LoggedWorkout` via the `_logged` helper below (no
page files, no frontmatter, no `.fit` file, no `scan_corpus`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fitdocs.model import Modality, Sport
from fitdocs.plans.corpus import Corpus, LoggedWorkout
from fitdocs.plans.matching import (
    Confidence,
    MatchResult,
    ReconcileProblem,
    RowOutcome,
    RowState,
    effective_overrides,
    is_candidate,
    match_rows,
)
from fitdocs.plans.model import Block
from fitdocs.plans.source import parse_block

#: Safely after every test date below that is not itself exercising the
#: split, so a row with no stems and no override resolves NOT_LOGGED rather
#: than UPCOMING unless the test says otherwise.
TODAY = date(2026, 4, 1)


def _source(*, starts: str, ends: str, body: str) -> str:
    return (
        'title = "Test block"\n'
        f"starts = {starts}\n"
        f"ends = {ends}\n"
        'goal = "Goal text."\n'
        "mesocycle_days = 62\n"
        "\n" + body
    )


def _row(
    row_id: str,
    day: str,
    sport: str,
    *,
    modality: str | None = None,
    indoor: bool | None = None,
) -> str:
    lines = [
        "[[workout]]",
        f'id = "{row_id}"',
        f"date = {day}",
        f'sport = "{sport}"',
    ]
    if modality is not None:
        lines.append(f'modality = "{modality}"')
    if indoor is not None:
        lines.append(f"indoor = {'true' if indoor else 'false'}")
    lines += [
        'title = "Title"',
        'summary = "Summary"',
        'prescription = "Prescription."',
    ]
    return "\n".join(lines) + "\n"


def _override(
    day: str,
    row_id: str,
    *,
    stems: tuple[str, ...] = (),
    skipped: bool = False,
    reason: str | None = None,
) -> str:
    lines = ["[[override]]", f"date = {day}", f'id = "{row_id}"']
    if skipped:
        lines.append("skipped = true")
    else:
        stems_toml = ", ".join(f'"{stem}"' for stem in stems)
        lines.append(f"stems = [{stems_toml}]")
    if reason is not None:
        lines.append(f'reason = "{reason}"')
    return "\n".join(lines) + "\n"


def _block(*, starts: str, ends: str, body: str, block_id: str = "test-block") -> Block:
    return parse_block(_source(starts=starts, ends=ends, body=body), block_id=block_id)


def _logged(
    stem: str,
    *,
    day: date | None,
    sport: Sport | None,
    modality: Modality | None = None,
    indoor: bool | None = None,
    start_time: datetime | None = None,
) -> LoggedWorkout:
    return LoggedWorkout(
        stem=stem,
        path=f"workouts/{stem}.md",
        day=day,
        sport=sport,
        modality=modality,
        indoor=indoor,
        start_time=start_time,
        load=None,
        methodology=None,
    )


def _at(hour: int) -> datetime:
    return datetime(2026, 3, 2, hour, 0, tzinfo=UTC)


def _outcome(result: MatchResult, row_id: str) -> RowOutcome:
    matches = [outcome for outcome in result.rows if outcome.row_id == row_id]
    assert len(matches) == 1, (row_id, result.rows)
    return matches[0]


# ===========================================================================
# Base case: exact match; a same-day other-sport page listed for a
# not-logged row.
# ===========================================================================


class TestBaseCase:
    def test_exact_match(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w1-mon", "2026-03-02", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-am", day=date(2026, 3, 2), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w1-mon")
        assert outcome.state is RowState.MATCHED
        assert outcome.confidence is Confidence.EXACT
        assert outcome.stems == ("run-am",)

    def test_same_day_other_sport_page_listed(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w1-mon", "2026-03-02", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("ride-am", day=date(2026, 3, 2), sport=Sport.RIDE),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w1-mon")
        assert outcome.state is RowState.NOT_LOGGED
        assert outcome.stems == ()
        assert outcome.same_day == (("ride-am", None),)


# ===========================================================================
# Split session: one row, three same-type pages, stems named opposite of
# start-time order -> absorbed with all three in start-time order.
# ===========================================================================


class TestSplitSession:
    def test_absorbed_in_start_time_order(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w1-mon", "2026-03-02", "Run"),
        )
        # Alphabetical stem order is a, m, z; start-time order -- the
        # correct answer -- is z, m, a; the corpus is declared latest-first
        # (a, m, z). So neither an alphabetical sort nor corpus declaration
        # order yields the expected list, and the `sorted(...) !=` assertion
        # below keeps the fixture adversarial to an alphabetical sort.
        # (Reversing declaration order would also yield it; that variant is
        # pinned by `test_third_row_of_another_type_stays_out_of_the_group`,
        # whose corpus is declared in start-time order.)
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-a", day=date(2026, 3, 2), sport=Sport.RUN, start_time=_at(8)
                ),
                _logged(
                    "run-m", day=date(2026, 3, 2), sport=Sport.RUN, start_time=_at(7)
                ),
                _logged(
                    "run-z", day=date(2026, 3, 2), sport=Sport.RUN, start_time=_at(6)
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w1-mon")
        assert outcome.state is RowState.MATCHED
        assert outcome.confidence is Confidence.ABSORBED
        assert outcome.stems == ("run-z", "run-m", "run-a")
        assert sorted(outcome.stems) != list(outcome.stems)


# ===========================================================================
# Competing rows.
# ===========================================================================


class TestCompetingRows:
    def test_two_rows_two_pages_both_ambiguous_cross_referenced(self) -> None:
        # Row ids and corpus declaration order are both adversarial: the
        # block declares `w-mon-b` before `w-mon-a` (the reverse of
        # `sorted(group)`'s alphabetical order), and the corpus is declared
        # latest-page-first (the reverse of `order_key`'s start-time order).
        # Neither alphabetical id order nor corpus declaration order can
        # stand in for the row's own block-declared order or its candidates'
        # `order_key` sort.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon-b", "2026-03-02", "Run")
            + _row("w-mon-a", "2026-03-02", "Run"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-a-later",
                    day=date(2026, 3, 2),
                    sport=Sport.RUN,
                    start_time=_at(8),
                ),
                _logged(
                    "run-z-earlier",
                    day=date(2026, 3, 2),
                    sport=Sport.RUN,
                    start_time=_at(6),
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        first = _outcome(result, "w-mon-b")
        second = _outcome(result, "w-mon-a")
        assert first.state is RowState.MATCHED
        assert first.confidence is Confidence.AMBIGUOUS
        assert first.stems == ("run-z-earlier",)
        assert first.competitors == ("w-mon-a",)
        assert second.state is RowState.MATCHED
        assert second.confidence is Confidence.AMBIGUOUS
        assert second.stems == ("run-a-later",)
        assert second.competitors == ("w-mon-b",)

    def test_two_rows_one_page_first_ambiguous_second_not_logged(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-tue-a", "2026-03-03", "Run")
            + _row("w-tue-b", "2026-03-03", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-only", day=date(2026, 3, 3), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        first = _outcome(result, "w-tue-a")
        second = _outcome(result, "w-tue-b")
        assert first.state is RowState.MATCHED
        assert first.confidence is Confidence.AMBIGUOUS
        assert first.stems == ("run-only",)
        assert first.competitors == ("w-tue-b",)
        assert second.state is RowState.NOT_LOGGED
        assert second.stems == ()
        assert second.competitors == ("w-tue-a",)
        assert second.same_day == (("run-only", "w-tue-a"),)

    def test_third_row_of_another_type_stays_out_of_the_group(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-wed-run", "2026-03-04", "Run")
            + _row("w-wed-ride", "2026-03-04", "Ride"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-1", day=date(2026, 3, 4), sport=Sport.RUN, start_time=_at(6)
                ),
                _logged(
                    "run-2", day=date(2026, 3, 4), sport=Sport.RUN, start_time=_at(7)
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        run_outcome = _outcome(result, "w-wed-run")
        ride_outcome = _outcome(result, "w-wed-ride")
        assert run_outcome.state is RowState.MATCHED
        assert run_outcome.confidence is Confidence.ABSORBED
        assert run_outcome.stems == ("run-1", "run-2")
        assert run_outcome.competitors == ()
        assert ride_outcome.state is RowState.NOT_LOGGED
        assert ride_outcome.competitors == ()


# ===========================================================================
# Partial overlap: a generic Workout row and a Workout (strength) row
# against one strength and one bike page -> one group, both ambiguous.
# ===========================================================================


class TestPartialOverlap:
    def test_one_group_both_ambiguous(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-thu-generic", "2026-03-05", "Workout")
            + _row("w-thu-strength", "2026-03-05", "Workout", modality="strength"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "zzz-bike-page",
                    day=date(2026, 3, 5),
                    sport=Sport.WORKOUT,
                    modality=Modality.BIKE,
                    start_time=_at(6),
                ),
                _logged(
                    "strength-page",
                    day=date(2026, 3, 5),
                    sport=Sport.WORKOUT,
                    modality=Modality.STRENGTH,
                    start_time=_at(7),
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        generic = _outcome(result, "w-thu-generic")
        strength = _outcome(result, "w-thu-strength")
        assert generic.state is RowState.MATCHED
        assert generic.confidence is Confidence.AMBIGUOUS
        assert generic.competitors == ("w-thu-strength",)
        assert strength.state is RowState.MATCHED
        assert strength.confidence is Confidence.AMBIGUOUS
        assert strength.competitors == ("w-thu-generic",)
        assert {generic.stems[0], strength.stems[0]} == {
            "zzz-bike-page",
            "strength-page",
        }


# ===========================================================================
# Cross-day: a page dated one day after, or one day before, never a
# candidate.
# ===========================================================================


class TestCrossDay:
    def test_page_dated_one_day_after_never_matches(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-fri", "2026-03-06", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-next-day", day=date(2026, 3, 7), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-fri")
        assert outcome.state is RowState.NOT_LOGGED
        assert outcome.stems == ()
        assert outcome.same_day == ()

    def test_page_dated_one_day_before_never_matches(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-sat", "2026-03-07", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-prev-day", day=date(2026, 3, 6), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-sat")
        assert outcome.state is RowState.NOT_LOGGED
        assert outcome.stems == ()
        assert outcome.same_day == ()


# ===========================================================================
# Type rules.
# ===========================================================================


class TestTypeRules:
    def test_strength_row_vs_other_modality_page(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-strength", "2026-03-08", "Workout", modality="strength"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "other-page",
                    day=date(2026, 3, 8),
                    sport=Sport.WORKOUT,
                    modality=Modality.OTHER,
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-strength")
        assert outcome.state is RowState.NOT_LOGGED

    def test_run_row_vs_walk_page(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-run", "2026-03-09", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("walk-page", day=date(2026, 3, 9), sport=Sport.WALK),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-run")
        assert outcome.state is RowState.NOT_LOGGED

    def test_indoor_true_row_vs_page_without_key(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-indoor-true", "2026-03-10", "Run", indoor=True),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-no-indoor-key",
                    day=date(2026, 3, 10),
                    sport=Sport.RUN,
                    indoor=None,
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-indoor-true")
        assert outcome.state is RowState.NOT_LOGGED

    def test_indoor_unstated_row_vs_indoor_true_page(self) -> None:
        # Req 3.1: a row that states no `indoor` at all ignores the flag
        # entirely, so it still matches a page explicitly `indoor = true`.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-indoor-unstated", "2026-03-16", "Run"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-indoor-page",
                    day=date(2026, 3, 16),
                    sport=Sport.RUN,
                    indoor=True,
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-indoor-unstated")
        assert outcome.state is RowState.MATCHED
        assert outcome.confidence is Confidence.EXACT
        assert outcome.stems == ("run-indoor-page",)

    def test_indoor_true_row_vs_indoor_true_page(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-indoor-true", "2026-03-11", "Run", indoor=True),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-indoor", day=date(2026, 3, 11), sport=Sport.RUN, indoor=True
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-indoor-true")
        assert outcome.state is RowState.MATCHED
        assert outcome.confidence is Confidence.EXACT
        assert outcome.stems == ("run-indoor",)

    def test_indoor_false_row_vs_page_without_key(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-indoor-false", "2026-03-12", "Run", indoor=False),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-no-indoor-key",
                    day=date(2026, 3, 12),
                    sport=Sport.RUN,
                    indoor=None,
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-indoor-false")
        assert outcome.state is RowState.MATCHED
        assert outcome.confidence is Confidence.EXACT
        assert outcome.stems == ("run-no-indoor-key",)


# ===========================================================================
# Override precedence.
# ===========================================================================


class TestOverridePrecedence:
    def test_override_replaces_an_exact_match(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override(
                "2026-03-02",
                "w-mon",
                stems=("override-stem",),
                reason="Swapped for the recorded page.",
            ),
        )
        corpus = Corpus(
            workouts=(
                _logged("run-exact", day=date(2026, 3, 2), sport=Sport.RUN),
                _logged("override-stem", day=date(2026, 3, 2), sport=Sport.RUN),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.state is RowState.OVERRIDDEN
        assert outcome.stems == ("override-stem",)
        assert outcome.override_date == date(2026, 3, 2)
        assert outcome.reason == "Swapped for the recorded page."

    def test_later_of_two_overrides_by_date_wins(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _row("w-mon-b", "2026-03-02", "Run")
            + _override("2026-01-01", "w-mon", stems=("early-stem",))
            + _override("2026-02-01", "w-mon", stems=("late-stem",)),
        )
        corpus = Corpus(
            workouts=(
                _logged("early-stem", day=date(2026, 3, 2), sport=Sport.RUN),
                _logged("late-stem", day=date(2026, 3, 2), sport=Sport.RUN),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.stems == ("late-stem",)
        assert outcome.override_index == 1
        # The superseded (non-effective) override's stem is claimed by no
        # one, so it stays available as a candidate for another row.
        other = _outcome(result, "w-mon-b")
        assert other.state is RowState.MATCHED
        assert other.confidence is Confidence.EXACT
        assert other.stems == ("early-stem",)
        assert result.problems == ()

    def test_equal_dates_later_position_in_file_wins(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override("2026-01-01", "w-mon", stems=("first-stem",))
            + _override("2026-01-01", "w-mon", stems=("second-stem",)),
        )
        corpus = Corpus(
            workouts=(
                _logged("first-stem", day=date(2026, 3, 2), sport=Sport.RUN),
                _logged("second-stem", day=date(2026, 3, 2), sport=Sport.RUN),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.stems == ("second-stem",)
        assert outcome.override_index == 1

    def test_claimed_stem_leaves_another_rows_candidates(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon-a", "2026-03-02", "Run")
            + _row("w-mon-b", "2026-03-02", "Run")
            + _override("2026-03-02", "w-mon-a", stems=("run-only",)),
        )
        corpus = Corpus(
            workouts=(_logged("run-only", day=date(2026, 3, 2), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        overridden = _outcome(result, "w-mon-a")
        other = _outcome(result, "w-mon-b")
        assert overridden.state is RowState.OVERRIDDEN
        assert overridden.stems == ("run-only",)
        assert other.state is RowState.NOT_LOGGED
        assert other.stems == ()
        # `same_day` names the OVERRIDDEN row as the claimant, not just any
        # MATCHED row.
        assert other.same_day == (("run-only", "w-mon-a"),)

    def test_missing_stem_recorded_and_reported(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override("2026-03-02", "w-mon", stems=("ghost-stem",)),
        )
        corpus = Corpus(workouts=())
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.state is RowState.OVERRIDDEN
        assert outcome.stems == ()
        assert outcome.missing == ("ghost-stem",)
        assert len(result.problems) == 1
        problem = result.problems[0]
        assert isinstance(problem, ReconcileProblem)
        assert problem.entry == "override[0] (id w-mon)"
        assert (
            problem.message == "stem `ghost-stem` not found among the logged workouts"
        )
        expected_message = "stem `ghost-stem` not found among the logged workouts"
        assert problem.describe() == f"override[0] (id w-mon): {expected_message}"

    def test_two_missing_stems_on_one_override_each_reported_in_order(
        self,
    ) -> None:
        # A single override names two stems, non-alphabetically ordered, and
        # the corpus is empty: every fixture up to now has at most one
        # missing stem per override, so the `missing` tuple truncated to its
        # first element (`[:1]`) and a problems loop walking the stems in
        # reverse both survive them (a problems loop restricted to the first
        # stem is already caught by
        # `test_still_overridden_by_the_stems_that_exist`).
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-ghosts", "2026-03-02", "Run")
            + _override("2026-03-02", "w-ghosts", stems=("zeta-ghost", "alpha-ghost")),
        )
        result = match_rows(block, Corpus(workouts=()), today=TODAY)
        outcome = _outcome(result, "w-ghosts")
        assert outcome.state is RowState.OVERRIDDEN
        assert outcome.stems == ()
        assert outcome.missing == ("zeta-ghost", "alpha-ghost")
        assert len(result.problems) == 2
        assert result.problems[0].entry == "override[0] (id w-ghosts)"
        assert result.problems[1].entry == "override[0] (id w-ghosts)"
        assert "zeta-ghost" in result.problems[0].message
        assert "alpha-ghost" in result.problems[1].message

    def test_two_overrides_on_one_stem_one_conflict_both_keep_it(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon-a", "2026-03-02", "Run")
            + _row("w-mon-b", "2026-03-03", "Run")
            + _override("2026-03-02", "w-mon-a", stems=("shared-stem",))
            + _override("2026-03-03", "w-mon-b", stems=("shared-stem",)),
        )
        corpus = Corpus(
            workouts=(_logged("shared-stem", day=date(2026, 3, 2), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        first = _outcome(result, "w-mon-a")
        second = _outcome(result, "w-mon-b")
        assert first.stems == ("shared-stem",)
        assert second.stems == ("shared-stem",)
        conflict_problems = [p for p in result.problems if "shared-stem" in p.message]
        assert len(conflict_problems) == 1
        assert "override[0]" in conflict_problems[0].entry
        assert "override[1]" in conflict_problems[0].entry

    def test_three_overrides_on_one_stem_one_conflict_names_all_three(
        self,
    ) -> None:
        # Three effective overrides (not two) claiming the same stem must
        # still yield exactly one `ReconcileProblem`, naming all three
        # owners -- the two-override case alone cannot distinguish a
        # single all-owners problem from a per-pair emission (one problem
        # per (first, other) pair), which here would produce two, not one.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon-a", "2026-03-02", "Run")
            + _row("w-mon-b", "2026-03-03", "Run")
            + _row("w-mon-c", "2026-03-04", "Run")
            + _override("2026-03-02", "w-mon-a", stems=("shared-stem",))
            + _override("2026-03-03", "w-mon-b", stems=("shared-stem",))
            + _override("2026-03-04", "w-mon-c", stems=("shared-stem",)),
        )
        corpus = Corpus(
            workouts=(_logged("shared-stem", day=date(2026, 3, 2), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        first = _outcome(result, "w-mon-a")
        second = _outcome(result, "w-mon-b")
        third = _outcome(result, "w-mon-c")
        assert first.stems == ("shared-stem",)
        assert second.stems == ("shared-stem",)
        assert third.stems == ("shared-stem",)
        conflict_problems = [p for p in result.problems if "shared-stem" in p.message]
        assert len(conflict_problems) == 1
        assert conflict_problems[0].entry == (
            "override[0] (id w-mon-a) and override[1] (id w-mon-b) and "
            "override[2] (id w-mon-c)"
        )

    def test_skipped_with_reason(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override("2026-03-02", "w-mon", skipped=True, reason="Injured."),
        )
        corpus = Corpus(workouts=())
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.state is RowState.SKIPPED
        assert outcome.stems == ()
        assert outcome.reason == "Injured."
        assert outcome.override_date == date(2026, 3, 2)


# ===========================================================================
# The split: today - 1, today, today + 1.
# ===========================================================================


class TestTheSplit:
    def test_not_logged_upcoming_boundary(self) -> None:
        today = date(2026, 3, 15)
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-before", "2026-03-14", "Run")
            + _row("w-today", "2026-03-15", "Run")
            + _row("w-after", "2026-03-16", "Run"),
        )
        result = match_rows(block, Corpus(workouts=()), today=today)
        assert _outcome(result, "w-before").state is RowState.NOT_LOGGED
        assert _outcome(result, "w-today").state is RowState.UPCOMING
        assert _outcome(result, "w-after").state is RowState.UPCOMING

    def test_singleton_matched_row_dated_today_is_still_matched(self) -> None:
        # Req 2.6 splits `NOT_LOGGED` from `UPCOMING` only for a row with no
        # stems; a row dated exactly `today` that *does* have a candidate
        # must still resolve MATCHED/EXACT, not fall into the split.
        today = date(2026, 3, 15)
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-today-matched", "2026-03-15", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-today", day=date(2026, 3, 15), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=today)
        outcome = _outcome(result, "w-today-matched")
        assert outcome.state is RowState.MATCHED
        assert outcome.confidence is Confidence.EXACT
        assert outcome.stems == ("run-today",)


# ===========================================================================
# Undated and unknown-sport pages never candidates.
# ===========================================================================


class TestNeverCandidates:
    def test_undated_page_never_a_candidate(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run"),
        )
        corpus = Corpus(workouts=(_logged("run-undated", day=None, sport=Sport.RUN),))
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.state is RowState.NOT_LOGGED
        # An undated page cannot be `row.date`'s same-day listing either.
        assert outcome.same_day == ()

    def test_unknown_sport_page_never_a_candidate(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-unknown-sport", day=date(2026, 3, 2), sport=None),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.state is RowState.NOT_LOGGED
        assert outcome.same_day == (("run-unknown-sport", None),)


# ===========================================================================
# Every invariant of the outcome.
# ===========================================================================


class TestInvariants:
    def test_invariants_hold_across_a_mixed_block(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-exact", "2026-03-02", "Run")
            + _row("w-absorbed", "2026-03-03", "Run")
            + _row("w-ambiguous-a", "2026-03-04", "Run")
            + _row("w-ambiguous-b", "2026-03-04", "Run")
            + _row("w-overridden", "2026-03-05", "Run")
            + _row("w-skipped", "2026-03-06", "Run")
            + _row("w-not-logged", "2026-03-07", "Run")
            + _override("2026-03-05", "w-overridden", stems=("override-stem",))
            + _override("2026-03-06", "w-skipped", skipped=True),
        )
        corpus = Corpus(
            workouts=(
                _logged("exact-stem", day=date(2026, 3, 2), sport=Sport.RUN),
                _logged(
                    "absorbed-1",
                    day=date(2026, 3, 3),
                    sport=Sport.RUN,
                    start_time=_at(6),
                ),
                _logged(
                    "absorbed-2",
                    day=date(2026, 3, 3),
                    sport=Sport.RUN,
                    start_time=_at(7),
                ),
                _logged(
                    "amb-1", day=date(2026, 3, 4), sport=Sport.RUN, start_time=_at(6)
                ),
                _logged(
                    "amb-2", day=date(2026, 3, 4), sport=Sport.RUN, start_time=_at(7)
                ),
                _logged("override-stem", day=date(2026, 3, 5), sport=Sport.RUN),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        assert len(result.rows) == 7

        seen_stems: set[str] = set()
        for outcome in result.rows:
            assert (outcome.confidence is not None) == (
                outcome.state is RowState.MATCHED
            )
            if outcome.state is RowState.MATCHED:
                assert outcome.stems
                for stem in outcome.stems:
                    assert stem not in seen_stems, "a stem matched more than one row"
                    seen_stems.add(stem)
            elif outcome.state is RowState.OVERRIDDEN:
                assert outcome.stems or outcome.missing
            else:
                assert outcome.stems == ()
            # `same_day` is populated only for the two states that list it
            # (Req 3.7); every other state's `same_day` stays empty even
            # though this fixture has same-day pages for the matched rows.
            if outcome.state not in (RowState.NOT_LOGGED, RowState.UPCOMING):
                assert outcome.same_day == ()

        assert result.claimed == frozenset(
            stem for outcome in result.rows for stem in outcome.stems
        )
        assert _outcome(result, "w-not-logged").state is RowState.NOT_LOGGED
        # `competitors` is scoped to the row's own competition group, not the
        # whole block: `w-ambiguous-a`'s only competitor is `w-ambiguous-b`,
        # never any of the other five unrelated rows in this block.
        assert _outcome(result, "w-ambiguous-a").competitors == ("w-ambiguous-b",)


# ===========================================================================
# Unit-level pins for `effective_overrides` and `is_candidate` directly.
# ===========================================================================


class TestEffectiveOverridesUnit:
    def test_greatest_date_then_position_wins(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override("2026-01-01", "w-mon", stems=("a",))
            + _override("2026-02-01", "w-mon", stems=("b",))
            + _override("2026-02-01", "w-mon", stems=("c",)),
        )
        winners = effective_overrides(block)
        index, override = winners["w-mon"]
        assert index == 2
        assert override.stems == ("c",)


class TestIsCandidateUnit:
    def test_nothing_but_day_sport_modality_indoor_is_consulted(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run"),
        )
        row = block.current.rows[0]
        matching = _logged("run-am", day=date(2026, 3, 2), sport=Sport.RUN)
        assert is_candidate(row, matching) is True
        wrong_day = _logged("run-wrong-day", day=date(2026, 3, 3), sport=Sport.RUN)
        assert is_candidate(row, wrong_day) is False
        wrong_sport = _logged("ride-am", day=date(2026, 3, 2), sport=Sport.RIDE)
        assert is_candidate(row, wrong_sport) is False


# ===========================================================================
# Transitive closure: A∩B≠∅, B∩C≠∅, A∩C=∅ must still fold into one group.
# ===========================================================================


class TestCompetingRowsTransitiveClosure:
    def test_a_chain_of_pairwise_overlaps_forms_one_group(self) -> None:
        # `ra` only overlaps `strength-page` (Workout/strength); `rc` only
        # overlaps `bike-page` (Workout/bike); `rb` (no modality stated)
        # overlaps both and is the sole link between `ra` and `rc`. These
        # three tests together pin the union-find and the per-row
        # assignment against several plausible-but-wrong implementations:
        # linking only roots that are each still their own root (rather
        # than following `find` through an already-merged chain) drops the
        # `rb`-`rc` link and leaves `rc` in a group of its own; assigning
        # from the group's pooled candidates instead of each row's own
        # candidate set lets a row take a page its own type/date rule would
        # never have produced. `bike-page` is declared earliest (06:00) and
        # `strength-page` second (07:00) here -- opposite of the pooled
        # order a pooling bug would use -- so `ra` (whose own candidate set
        # never includes `bike-page`) still resolves to `strength-page`
        # only because assignment is restricted to its own set.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("ra", "2026-03-13", "Workout", modality="strength")
            + _row("rb", "2026-03-13", "Workout")
            + _row("rc", "2026-03-13", "Workout", modality="bike"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "bike-page",
                    day=date(2026, 3, 13),
                    sport=Sport.WORKOUT,
                    modality=Modality.BIKE,
                    start_time=_at(6),
                ),
                _logged(
                    "strength-page",
                    day=date(2026, 3, 13),
                    sport=Sport.WORKOUT,
                    modality=Modality.STRENGTH,
                    start_time=_at(7),
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        ra = _outcome(result, "ra")
        rb = _outcome(result, "rb")
        rc = _outcome(result, "rc")
        assert ra.state is RowState.MATCHED
        assert ra.confidence is Confidence.AMBIGUOUS
        assert ra.stems == ("strength-page",)
        assert ra.competitors == ("rb", "rc")
        assert rb.state is RowState.MATCHED
        assert rb.confidence is Confidence.AMBIGUOUS
        assert rb.stems == ("bike-page",)
        assert rb.competitors == ("ra", "rc")
        assert rc.state is RowState.NOT_LOGGED
        assert rc.stems == ()
        assert rc.competitors == ("ra", "rb")
        assert rc.same_day == (("bike-page", "rb"), ("strength-page", "ra"))

    def test_chain_with_the_linking_row_declared_first(self) -> None:
        # Same chain (`ra` strength-only, `rc` bike-only, `rb` the generic
        # link) with `rb` declared first in block order, so the union-find
        # must fold `ra` and `rc` into `rb`'s group regardless of which end
        # of the chain is unioned first.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("rb", "2026-03-13", "Workout")
            + _row("ra", "2026-03-13", "Workout", modality="strength")
            + _row("rc", "2026-03-13", "Workout", modality="bike"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "strength-page",
                    day=date(2026, 3, 13),
                    sport=Sport.WORKOUT,
                    modality=Modality.STRENGTH,
                    start_time=_at(6),
                ),
                _logged(
                    "bike-page",
                    day=date(2026, 3, 13),
                    sport=Sport.WORKOUT,
                    modality=Modality.BIKE,
                    start_time=_at(7),
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        ra = _outcome(result, "ra")
        rb = _outcome(result, "rb")
        rc = _outcome(result, "rc")
        # `rb`, declared and processed first, takes the earlier of its two
        # own candidates (`strength-page`), leaving `ra` -- whose only
        # candidate is now taken -- without one.
        assert rb.state is RowState.MATCHED
        assert rb.stems == ("strength-page",)
        assert ra.state is RowState.NOT_LOGGED
        assert ra.stems == ()
        assert rc.state is RowState.MATCHED
        assert rc.stems == ("bike-page",)
        assert ra.competitors == ("rb", "rc")
        assert rb.competitors == ("ra", "rc")
        assert rc.competitors == ("rb", "ra")
        matched_stems = [
            o.stems[0] for o in (ra, rb, rc) if o.state is RowState.MATCHED
        ]
        assert len(matched_stems) == len(set(matched_stems))

    def test_chain_with_the_linking_row_declared_last(self) -> None:
        # Same chain with `rb` declared last in block order.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("ra", "2026-03-13", "Workout", modality="strength")
            + _row("rc", "2026-03-13", "Workout", modality="bike")
            + _row("rb", "2026-03-13", "Workout"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "strength-page",
                    day=date(2026, 3, 13),
                    sport=Sport.WORKOUT,
                    modality=Modality.STRENGTH,
                    start_time=_at(6),
                ),
                _logged(
                    "bike-page",
                    day=date(2026, 3, 13),
                    sport=Sport.WORKOUT,
                    modality=Modality.BIKE,
                    start_time=_at(7),
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        ra = _outcome(result, "ra")
        rb = _outcome(result, "rb")
        rc = _outcome(result, "rc")
        # `ra` and `rc`, processed before `rb`, each take their own sole
        # candidate first, leaving `rb` -- whose set is now exhausted --
        # without one.
        assert ra.state is RowState.MATCHED
        assert ra.stems == ("strength-page",)
        assert rc.state is RowState.MATCHED
        assert rc.stems == ("bike-page",)
        assert rb.state is RowState.NOT_LOGGED
        assert rb.stems == ()
        assert ra.competitors == ("rc", "rb")
        assert rc.competitors == ("ra", "rb")
        assert rb.competitors == ("ra", "rc")
        matched_stems = [
            o.stems[0] for o in (ra, rb, rc) if o.state is RowState.MATCHED
        ]
        assert len(matched_stems) == len(set(matched_stems))


# ===========================================================================
# An unassigned candidate in a competition group stays unclaimed.
# ===========================================================================


class TestUnassignedCandidateStaysUnclaimed:
    def test_the_third_candidate_is_never_claimed(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-a", "2026-03-14", "Run") + _row("w-b", "2026-03-14", "Run"),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "r1", day=date(2026, 3, 14), sport=Sport.RUN, start_time=_at(6)
                ),
                _logged(
                    "r2", day=date(2026, 3, 14), sport=Sport.RUN, start_time=_at(7)
                ),
                _logged(
                    "r3", day=date(2026, 3, 14), sport=Sport.RUN, start_time=_at(8)
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        first = _outcome(result, "w-a")
        second = _outcome(result, "w-b")
        assert first.stems == ("r1",)
        assert second.stems == ("r2",)
        assert result.claimed == frozenset({"r1", "r2"})


# ===========================================================================
# `indoor = false` row vs an explicit `indoor: true` page never matches.
# ===========================================================================


class TestIndoorFalseRowVsIndoorTruePage:
    def test_indoor_false_row_vs_indoor_true_page(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-indoor-false-2", "2026-03-15", "Run", indoor=False),
        )
        corpus = Corpus(
            workouts=(
                _logged(
                    "run-indoor-page",
                    day=date(2026, 3, 15),
                    sport=Sport.RUN,
                    indoor=True,
                ),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-indoor-false-2")
        assert outcome.state is RowState.NOT_LOGGED


# ===========================================================================
# Override precedence: still overridden by whichever named stems exist.
# ===========================================================================


class TestOverridePrecedenceExtra:
    def test_still_overridden_by_the_stems_that_exist(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override("2026-03-02", "w-mon", stems=("exists-stem", "ghost-stem")),
        )
        corpus = Corpus(
            workouts=(_logged("exists-stem", day=date(2026, 3, 2), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.state is RowState.OVERRIDDEN
        assert outcome.stems == ("exists-stem",)
        assert outcome.missing == ("ghost-stem",)
        assert len(result.problems) == 1
        # A missing stem is never `claimed` -- only the stems an outcome
        # actually carries are.
        assert result.claimed == frozenset({"exists-stem"})


# ===========================================================================
# The split applies on the competition-loser path too (Req 3.6, "by its
# date"), and an UPCOMING row also lists `same_day`.
# ===========================================================================


class TestSplitOnCompetitionLoserPath:
    def test_second_row_of_a_competition_group_dated_today_is_upcoming(
        self,
    ) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-04-30",
            body=_row("w-a", "2026-04-01", "Run") + _row("w-b", "2026-04-01", "Run"),
        )
        corpus = Corpus(
            workouts=(_logged("run-only", day=date(2026, 4, 1), sport=Sport.RUN),)
        )
        result = match_rows(block, corpus, today=TODAY)
        first = _outcome(result, "w-a")
        second = _outcome(result, "w-b")
        assert first.state is RowState.MATCHED
        assert first.stems == ("run-only",)
        assert second.state is RowState.UPCOMING
        assert second.stems == ()
        assert second.competitors == ("w-a",)
        assert second.same_day == (("run-only", "w-a"),)


# ===========================================================================
# `MatchResult.rows` follows `block.current.rows`' own declaration order.
# ===========================================================================


class TestRowsFollowBlockOrder:
    def test_rows_follow_block_declaration_order_not_date_order(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-later", "2026-03-20", "Run")
            + _row("w-earlier", "2026-03-10", "Run"),
        )
        result = match_rows(block, Corpus(workouts=()), today=TODAY)
        assert [o.row_id for o in result.rows] == [r.id for r in block.current.rows]
        assert [o.row_id for o in result.rows] == ["w-later", "w-earlier"]


# ===========================================================================
# `problems` is source ordered by the lowest override index involved.
# ===========================================================================


class TestProblemsSourceOrder:
    def test_problems_ordered_by_lowest_override_index(self) -> None:
        # `winners` (the effective-override map) is keyed by row_id, so its
        # iteration order is insertion order: `b`'s entry is inserted first
        # (override[0]) and later *updated in place* by override[2], which
        # does not move it -- so the map still yields `b` before `a` even
        # though `b`'s effective index (2) is greater than `a`'s (1). A
        # fixture where winner-map order already matched index order could
        # not discriminate a missing sort from one that is present, so this
        # one is built so the two orders differ: override[0] on `b` is
        # superseded by the later-dated override[2] also on `b`, and
        # override[1] on `a` is the sole (and so winning) entry for `a`.
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("a", "2026-03-02", "Run")
            + _row("b", "2026-03-03", "Run")
            + _override("2026-01-01", "b", stems=("ghost-b-early",))
            + _override("2026-01-15", "a", stems=("ghost-a",))
            + _override("2026-02-01", "b", stems=("ghost-b-late",)),
        )
        result = match_rows(block, Corpus(workouts=()), today=TODAY)
        assert [p.entry for p in result.problems] == [
            "override[1] (id a)",
            "override[2] (id b)",
        ]


# ===========================================================================
# Overridden stems keep the override's own declared order, not sorted.
# ===========================================================================


class TestOverriddenStemOrder:
    def test_overridden_stems_keep_the_overrides_own_order(self) -> None:
        block = _block(
            starts="2026-03-01",
            ends="2026-03-31",
            body=_row("w-mon", "2026-03-02", "Run")
            + _override("2026-03-02", "w-mon", stems=("zeta", "alpha")),
        )
        corpus = Corpus(
            workouts=(
                _logged("zeta", day=date(2026, 3, 2), sport=Sport.RUN),
                _logged("alpha", day=date(2026, 3, 2), sport=Sport.RUN),
            )
        )
        result = match_rows(block, corpus, today=TODAY)
        outcome = _outcome(result, "w-mon")
        assert outcome.stems == ("zeta", "alpha")


# ===========================================================================
# The closed enum vocabulary (Req 2.1, 3.9; design.md "Matcher" contract).
# ===========================================================================


class TestEnumVocabulary:
    def test_row_state_and_confidence_vocabularies_are_pinned(self) -> None:
        assert [s.value for s in RowState] == [
            "matched",
            "overridden",
            "skipped",
            "not logged",
            "upcoming",
        ]
        assert [c.value for c in Confidence] == [
            "exact",
            "absorbed",
            "ambiguous",
        ]
