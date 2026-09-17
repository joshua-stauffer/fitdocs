"""Tests for `fitdocs.plans.placement` (plan-resolution spec, task 2.4). See
"Placement" in `.kiro/specs/plan-resolution/design.md` (Req 3.7, 4.3, 4.5,
5.3, 6.3-6.7, 7.1-7.7).

Test File Ownership (tasks.md): this module, `tests/plans/golden/reconciled-*.md`
and `tests/plans/fixtures/reconcile/*.toml` belong to 2.4 alone. The block
is built from `fixtures/reconcile/full.toml` through the wave-1 parser
(`parse_block`); every `LoggedWorkout` is built directly, never through a
filesystem scan (`plans.corpus` is task 2.1's); `match_rows` and
`aggregate_mesocycles` (tasks 2.2, 2.3) build the real `MatchResult` and
`MesocycleLoad` tuples this module's own `BlockReconciliation` wraps.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

from markdown_it import MarkdownIt

import fitdocs.history
from fitdocs.model import Modality, Sport
from fitdocs.plans import page
from fitdocs.plans.aggregate import MesocycleLoad, aggregate_mesocycles
from fitdocs.plans.block_page import render_block_page
from fitdocs.plans.corpus import Corpus, LoggedWorkout
from fitdocs.plans.matching import Confidence, RowOutcome, RowState, match_rows
from fitdocs.plans.model import Block
from fitdocs.plans.placement import (
    EXCLUDED,
    BlockReconciliation,
    actual_load_sentence,
    logged_phrase,
    place_resolution,
    row_cell,
    row_section,
)
from fitdocs.plans.planned_page import render_planned_page
from fitdocs.plans.resolution import Resolution
from fitdocs.plans.source import parse_block

_MD = MarkdownIt("commonmark")

_FIXTURES = Path(__file__).parent / "fixtures" / "reconcile"
_GOLDEN = Path(__file__).parent / "golden"

TODAY = date(2026, 2, 24)
"""Placed inside the fixture block (mesocycle 4, a rest day) so the wave-1
block page prints it on the day table -- only the built `Resolution` value
is required to stay clean of it (design's own "no-today" postcondition)."""


# ===========================================================================
# Fixture builders
# ===========================================================================


def _block() -> Block:
    text = (_FIXTURES / "full.toml").read_text(encoding="utf-8")
    return parse_block(text, block_id="reconcile-fixture")


def _logged(
    stem: str,
    *,
    day: date | None,
    sport: Sport | None = Sport.RUN,
    load: float | None = None,
    methodology: str | None = None,
    start_time: datetime | None = None,
) -> LoggedWorkout:
    return LoggedWorkout(
        stem=stem,
        path=f"workouts/{stem}.md",
        day=day,
        sport=sport,
        modality=None,
        indoor=None,
        start_time=start_time,
        load=load,
        methodology=methodology,
    )


def _corpus() -> Corpus:
    """Every logged workout the fixture block's rows and mesocycles need,
    built directly -- never through `scan_corpus` (this task's boundary is
    `Placement` alone, not `corpus`)."""
    workouts = (
        _logged(
            "w1-mon-log",
            day=date(2026, 2, 2),
            load=45,
            methodology="threshold",
            # Non-UTC offset deliberately (round-2 item 1): the bullet must
            # print this page's own local wall clock (07:15), never a value
            # `astimezone(UTC)` would have produced (12:15) -- see
            # `TestRowSection.test_matched_exact_section` below.
            start_time=datetime(
                2026, 2, 2, 7, 15, tzinfo=timezone(timedelta(hours=-5))
            ),
        ),
        _logged(
            "w1-tue-log-a",
            day=date(2026, 2, 3),
            sport=Sport.RIDE,
            load=30,
            methodology="threshold",
            start_time=datetime(2026, 2, 3, 6, 0, tzinfo=UTC),
        ),
        _logged(
            "w1-tue-log-b",
            day=date(2026, 2, 3),
            sport=Sport.RIDE,
            load=25,
            methodology="threshold",
            start_time=datetime(2026, 2, 3, 6, 30, tzinfo=UTC),
        ),
        _logged(
            "w1-tue-log-c",
            day=date(2026, 2, 3),
            sport=Sport.RIDE,
            load=20,
            methodology="threshold",
            start_time=datetime(2026, 2, 3, 7, 0, tzinfo=UTC),
        ),
        _logged(
            "w1-wed-ride-log",
            day=date(2026, 2, 4),
            sport=Sport.RIDE,
            load=40,
            methodology="threshold",
        ),
        _logged("w1-fri-log", day=date(2026, 2, 6), load=50, methodology="threshold"),
        _logged(
            "w2-existing-log",
            day=date(2026, 2, 9),
            sport=Sport.RIDE,
            load=200,
            methodology="threshold",
        ),
        _logged("w2-unscored-log", day=date(2026, 2, 11), load=None, methodology=None),
        _logged(
            "w2-excluded-log",
            day=date(2026, 2, 12),
            load=150,
            methodology="banister",
        ),
        _logged("m3-unscored-a", day=date(2026, 2, 18), load=None, methodology=None),
        _logged("m3-unscored-b", day=date(2026, 2, 19), load=None, methodology=None),
        _logged(
            "m3-excluded-log",
            day=date(2026, 2, 20),
            load=80,
            methodology="banister",
        ),
        _logged(
            "m4-unplanned-log",
            day=date(2026, 2, 28),
            sport=Sport.RIDE,
            load=60,
            methodology="threshold",
        ),
    )
    return Corpus(workouts=tuple(sorted(workouts, key=lambda w: w.order_key)))


_CHOICE = fitdocs.history.MethodologyChoice(
    "threshold", "configured", (("banister", 1),)
)
_PROBLEM = fitdocs.history.MethodologyProblem(
    "the archive records more than one methodology and none was requested "
    "or configured: 'banister' (1 pages), 'threshold' (7 pages). Pass "
    "--methodology, or set [history].methodology or "
    "[load].default_calculator, to choose one."
)


def _reconciliation(
    block: Block,
    corpus: Corpus,
    *,
    methodology: fitdocs.history.MethodologyChoice
    | fitdocs.history.MethodologyProblem
    | None,
) -> BlockReconciliation:
    match_result = match_rows(block, corpus, today=TODAY)
    choice = (
        methodology
        if isinstance(methodology, fitdocs.history.MethodologyChoice)
        else None
    )
    mesocycles = aggregate_mesocycles(
        block, corpus, claimed=match_result.claimed, choice=choice
    )
    return BlockReconciliation(
        block_id=block.id,
        rows=match_result.rows,
        mesocycles=mesocycles,
        methodology=methodology if methodology is not None else _PROBLEM,
        problems=match_result.problems,
    )


def _outcome(
    row_id: str,
    state: RowState,
    *,
    stems: tuple[str, ...] = (),
    confidence: Confidence | None = None,
    missing: tuple[str, ...] = (),
    competitors: tuple[str, ...] = (),
    same_day: tuple[tuple[str, str | None], ...] = (),
    override_index: int | None = None,
    override_date: date | None = None,
    reason: str | None = None,
) -> RowOutcome:
    return RowOutcome(
        row_id=row_id,
        state=state,
        stems=stems,
        confidence=confidence,
        missing=missing,
        override_index=override_index,
        override_date=override_date,
        reason=reason,
        competitors=competitors,
        same_day=same_day,
    )


def _mesocycle(
    *,
    number: int = 1,
    target: float | None = None,
    methodology: str | None = "threshold",
    pages: tuple[LoggedWorkout, ...] = (),
    scored: tuple[LoggedWorkout, ...] = (),
    unscored: tuple[LoggedWorkout, ...] = (),
    excluded: tuple[LoggedWorkout, ...] = (),
    unplanned: tuple[LoggedWorkout, ...] = (),
) -> MesocycleLoad:
    return MesocycleLoad(
        number=number,
        target=target,
        methodology=methodology,
        pages=pages,
        scored=scored,
        unscored=unscored,
        excluded=excluded,
        unplanned=unplanned,
    )


def _scored_page(
    stem: str, load: float, methodology: str = "threshold"
) -> LoggedWorkout:
    return _logged(stem, day=date(2026, 1, 1), load=load, methodology=methodology)


def _unscored_page(stem: str) -> LoggedWorkout:
    return _logged(stem, day=date(2026, 1, 1), load=None, methodology=None)


# ===========================================================================
# Goldens: one block, one under a methodology problem, two planned pages
# ===========================================================================


class TestGoldens:
    def test_block_golden_exact(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        rendered = render_block_page(block, resolution)
        expected = (_GOLDEN / "reconciled-block.md").read_text(encoding="utf-8")
        assert rendered == expected

    def test_block_golden_under_methodology_problem(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_PROBLEM)
        resolution = place_resolution(block, reconciliation, corpus)
        rendered = render_block_page(block, resolution)
        expected = (_GOLDEN / "reconciled-block-problem.md").read_text(encoding="utf-8")
        assert rendered == expected

    def test_planned_golden_ambiguous_row(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        row = block.current.row("w1-fri-a")
        assert row is not None
        rendered = render_planned_page(block, row, resolution)
        expected = (_GOLDEN / "reconciled-planned-w1-fri-a.md").read_text(
            encoding="utf-8"
        )
        assert rendered == expected

    def test_planned_golden_overridden_row(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        row = block.current.row("w2-mon")
        assert row is not None
        rendered = render_planned_page(block, row, resolution)
        expected = (_GOLDEN / "reconciled-planned-w2-mon.md").read_text(
            encoding="utf-8"
        )
        assert rendered == expected

    def test_byte_identical_across_two_calls(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        first = render_block_page(
            block, place_resolution(block, reconciliation, corpus)
        )
        second = render_block_page(
            block, place_resolution(block, reconciliation, corpus)
        )
        assert first == second


# ===========================================================================
# Grammar fragments land in their slot and nowhere else
# ===========================================================================


class TestFragmentsLandInTheirSlot:
    def _resolution(
        self,
    ) -> tuple[Block, Corpus, BlockReconciliation, Resolution]:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        return (
            block,
            corpus,
            reconciliation,
            place_resolution(block, reconciliation, corpus),
        )

    def test_matched_exact_cell_only_on_its_own_row(self) -> None:
        _, _, _, resolution = self._resolution()
        assert (
            resolution.rows["w1-mon"].cell
            == "matched: [w1-mon-log](../workouts/w1-mon-log.md)"
        )
        for row_id, entry in resolution.rows.items():
            if row_id != "w1-mon":
                assert "w1-mon-log" not in entry.cell

    def test_absorbed_cell_names_every_stem_once(self) -> None:
        _, _, _, resolution = self._resolution()
        cell = resolution.rows["w1-tue"].cell
        assert cell.startswith("matched (absorbed 3): ")
        for stem in ("w1-tue-log-a", "w1-tue-log-b", "w1-tue-log-c"):
            # Each stem appears twice in its own bullet (link text and
            # href) and nowhere else in the cell.
            assert cell.count(stem) == 2

    def test_ambiguous_section_names_both_rows_once(self) -> None:
        _, _, _, resolution = self._resolution()
        section = resolution.rows["w1-fri-a"].section[0]
        assert section.count("`w1-fri-a`") == 1
        assert section.count("`w1-fri-b`") == 1

    def test_overridden_cell_and_section_are_isolated_to_their_row(self) -> None:
        _, _, _, resolution = self._resolution()
        assert "w2-missing-log" not in resolution.rows["w2-tue"].cell
        assert "w2-missing-log" in resolution.rows["w2-mon"].cell

    def test_block_lines_carry_no_row_cell_text(self) -> None:
        """The count line legitimately names the `upcoming` state word
        (Req 4.3); what must never appear at block level is a *cell*'s own
        colon-terminated form (`"matched: "`, a specific row's stems)."""
        _, _, _, resolution = self._resolution()
        for line in resolution.block_lines:
            assert "matched: " not in line
            assert "w1-mon-log" not in line


# ===========================================================================
# Structural postconditions
# ===========================================================================


class TestStructuralPostconditions:
    def test_check_resolution_raises_nothing(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        page.check_resolution(block, resolution)  # raises on failure

    def test_no_cell_holds_a_newline_or_a_pipe(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        for entry in resolution.rows.values():
            assert "\n" not in entry.cell
            assert "|" not in entry.cell

    def test_no_section_line_is_a_fence_line(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        for entry in resolution.rows.values():
            for line in entry.section:
                assert not page.is_fence_line(line)

    def test_every_row_id_and_mesocycle_number_present(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        assert set(resolution.rows) == {row.row_id for row in reconciliation.rows}
        assert set(resolution.mesocycles) == {
            mesocycle.number for mesocycle in reconciliation.mesocycles
        }


class TestNoTodayPostcondition:
    """`today` (2026-02-24) is inside the fixture block, on a rest day
    (mesocycle 4), so the wave-1 day table prints it on the page -- only
    the built `Resolution` *value* is required to stay clean of it. No
    override, unplanned or excluded logged workout in the fixture is dated
    `today` (the fixture's own docstring states this constraint beside this
    assertion, per the task brief)."""

    def test_no_string_in_the_resolution_value_contains_today(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        needle = TODAY.isoformat()
        for entry in resolution.rows.values():
            assert needle not in entry.cell
            for line in entry.section:
                assert needle not in line
        for extra in resolution.mesocycles.values():
            for line in extra.before_table:
                assert needle not in line
            for line in extra.after_table:
                assert needle not in line
        for line in resolution.block_lines:
            assert needle not in line

    def test_today_appears_on_the_rendered_block_page(self) -> None:
        """The design's page-level trap, demonstrated rather than narrated:
        `today` is absent from every `Resolution` string above, yet the
        wave-1 day table prints it on the rendered page -- that rest-day
        row is not built from `Resolution` data at all."""
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        rendered = render_block_page(block, resolution)
        assert TODAY.isoformat() in rendered


# ===========================================================================
# logged_phrase: every branch, by exact string
# ===========================================================================


class TestLoggedPhrase:
    def test_unknown_sport(self) -> None:
        workout = _logged("x", day=date(2026, 1, 1), sport=None)
        assert logged_phrase(workout) == "unknown sport"

    def test_workout_sport_with_modality_and_indoor(self) -> None:
        workout = LoggedWorkout(
            stem="x",
            path="workouts/x.md",
            day=date(2026, 1, 1),
            sport=Sport.WORKOUT,
            modality=Modality.STRENGTH,
            indoor=True,
            start_time=None,
            load=None,
            methodology=None,
        )
        assert logged_phrase(workout) == (
            f"Workout ({Modality.STRENGTH}, {page.INDOOR_WORD})"
        )

    def test_non_workout_sport_with_modality_has_no_parenthesis(self) -> None:
        # Only `Sport.WORKOUT` ever surfaces the modality extra; a modality
        # stated on any other sport (here `Sport.RUN`) is not displayed.
        workout = LoggedWorkout(
            stem="x",
            path="workouts/x.md",
            day=date(2026, 1, 1),
            sport=Sport.RUN,
            modality=Modality.RUN,
            indoor=False,
            start_time=None,
            load=None,
            methodology=None,
        )
        assert logged_phrase(workout) == "Run"

    def test_indoor_false_carries_no_indoor_word(self) -> None:
        workout = LoggedWorkout(
            stem="x",
            path="workouts/x.md",
            day=date(2026, 1, 1),
            sport=Sport.RIDE,
            modality=None,
            indoor=False,
            start_time=None,
            load=None,
            methodology=None,
        )
        assert logged_phrase(workout) == "Ride"

    def test_indoor_none_carries_no_indoor_word(self) -> None:
        workout = _logged("x", day=date(2026, 1, 1), sport=Sport.RIDE)
        assert logged_phrase(workout) == "Ride"


# ===========================================================================
# actual_load_sentence: every grammar case, by exact string (design.md's
# own examples)
# ===========================================================================


class TestActualLoadSentence:
    def test_complete_with_target(self) -> None:
        mesocycle = _mesocycle(
            target=1200,
            pages=tuple(_scored_page(f"s{i}", 236) for i in range(5)),
            scored=tuple(_scored_page(f"s{i}", 236) for i in range(5)),
        )
        assert actual_load_sentence(mesocycle) == (
            "Actual load: 1180 -- 5 of 5 logged workouts scored under "
            "threshold; 98% of target."
        )

    def test_complete_with_no_target(self) -> None:
        mesocycle = _mesocycle(
            target=None,
            pages=tuple(_scored_page(f"s{i}", 236) for i in range(5)),
            scored=tuple(_scored_page(f"s{i}", 236) for i in range(5)),
        )
        assert actual_load_sentence(mesocycle) == (
            "Actual load: 1180 -- 5 of 5 logged workouts scored under "
            "threshold; no target."
        )

    def test_lower_bound(self) -> None:
        scored = (
            _scored_page("s0", 300),
            _scored_page("s1", 300),
            _scored_page("s2", 300),
        )
        unscored = (_unscored_page("u0"), _unscored_page("u1"))
        mesocycle = _mesocycle(
            target=1200, pages=scored + unscored, scored=scored, unscored=unscored
        )
        assert actual_load_sentence(mesocycle) == (
            "Actual load: at least 900 -- 3 of 5 logged workouts scored "
            "under threshold, 2 unscored; at least 75% of target."
        )

    def test_with_exclusions(self) -> None:
        scored = tuple(_scored_page(f"s{i}", 236) for i in range(5))
        excluded = (_scored_page("e0", 999, "banister"),)
        mesocycle = _mesocycle(
            target=1200, pages=scored + excluded, scored=scored, excluded=excluded
        )
        assert actual_load_sentence(mesocycle) == (
            "Actual load: 1180 -- 5 of 5 logged workouts scored under "
            "threshold, 1 excluded (scored under other); 98% of target."
        )

    def test_none_scored(self) -> None:
        unscored = tuple(_unscored_page(f"u{i}") for i in range(4))
        mesocycle = _mesocycle(target=1200, pages=unscored, unscored=unscored)
        assert actual_load_sentence(mesocycle) == (
            "Actual load: not computed -- 0 of 4 logged workouts scored "
            "under threshold."
        )

    def test_no_pages(self) -> None:
        mesocycle = _mesocycle(target=1200, pages=())
        assert actual_load_sentence(mesocycle) == (
            "Actual load: not computed -- no logged workout in this window."
        )

    def test_no_methodology(self) -> None:
        mesocycle = _mesocycle(
            target=1200, methodology=None, pages=(_unscored_page("u0"),)
        )
        assert actual_load_sentence(mesocycle) == (
            "Actual load: not computed -- no methodology chosen (see Resolution below)."
        )


# ===========================================================================
# The methodology line: the "inferred" source phrase, by exact string
# ===========================================================================


class TestMethodologyLine:
    def test_inferred_source_reads_the_full_phrase(self) -> None:
        block = _block()
        corpus = _corpus()
        choice = fitdocs.history.MethodologyChoice("threshold", "inferred", ())
        rec = BlockReconciliation(
            block_id=block.id, rows=(), mesocycles=(), methodology=choice, problems=()
        )
        resolution = place_resolution(block, rec, corpus)
        assert resolution.block_lines[2] == (
            "Methodology: threshold (inferred from the logged workouts)."
        )


# ===========================================================================
# row_cell: the overridden edge case, by exact string
# ===========================================================================


class TestRowCellOverridden:
    def test_zero_existing_one_missing_is_exactly_this_string(self) -> None:
        outcome = _outcome(
            "r1",
            RowState.OVERRIDDEN,
            stems=(),
            missing=("stem",),
            override_index=0,
            override_date=date(2026, 1, 1),
        )
        assert row_cell(outcome) == "overridden: `stem` (not found)"

    def test_one_existing_one_missing_no_leading_comma_before_the_link(self) -> None:
        outcome = _outcome(
            "r1",
            RowState.OVERRIDDEN,
            stems=("existing-stem",),
            missing=("missing-stem",),
            override_index=0,
            override_date=date(2026, 1, 1),
        )
        assert row_cell(outcome) == (
            "overridden: [existing-stem](../workouts/existing-stem.md), "
            "`missing-stem` (not found)"
        )


class TestRowCellLinkText:
    def test_stem_containing_bracket_is_escaped(self) -> None:
        outcome = _outcome(
            "r1", RowState.MATCHED, stems=("run[key]",), confidence=Confidence.EXACT
        )
        assert row_cell(outcome) == (r"matched: [run\[key\]](../workouts/run[key].md)")


# ===========================================================================
# The count line
# ===========================================================================


class TestRowSection:
    def test_matched_exact_section(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        outcome = next(row for row in reconciliation.rows if row.row_id == "w1-mon")
        row = block.current.row("w1-mon")
        assert row is not None
        section = row_section(block, row, outcome, corpus)
        # The bullet's time (07:15) is `w1-mon-log`'s own local wall clock,
        # recorded at a `-05:00` offset -- `astimezone(UTC)` would print
        # 12:15 instead.
        assert section == (
            "Matched (exact): one logged workout on this day is of this "
            "type, and no other planned workout competes for it.",
            "- [w1-mon-log](../../workouts/w1-mon-log.md) -- Run, 07:15, load 45",
        )

    def test_matched_absorbed_section(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        outcome = next(row for row in reconciliation.rows if row.row_id == "w1-tue")
        row = block.current.row("w1-tue")
        assert row is not None
        section = row_section(block, row, outcome, corpus)
        assert section == (
            "Matched (absorbed): 3 logged workouts on this day are of "
            "this type, and no other planned workout competes for them; "
            "all 3 are taken as this workout.",
            "- [w1-tue-log-a](../../workouts/w1-tue-log-a.md) -- Ride, 06:00, load 30",
            "- [w1-tue-log-b](../../workouts/w1-tue-log-b.md) -- Ride, 06:30, load 25",
            "- [w1-tue-log-c](../../workouts/w1-tue-log-c.md) -- Ride, 07:00, load 20",
        )

    def test_not_logged_ambiguous_competitor_section(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        outcome = next(row for row in reconciliation.rows if row.row_id == "w1-fri-b")
        row = block.current.row("w1-fri-b")
        assert row is not None
        section = row_section(block, row, outcome, corpus)
        assert section == (
            "Not logged: no logged workout on 2026-02-06 is of this type.",
            "",
            "2 planned workouts of this type on this day competed for 1 "
            "logged workout, assigned to `w1-fri-a` by start-time order.",
            "",
            "Logged on this day:",
            "- [w1-fri-log](../../workouts/w1-fri-log.md) -- Run (taken by `w1-fri-a`)",
        )

    def test_upcoming_section(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        outcome = next(row for row in reconciliation.rows if row.row_id == "w4-thu")
        row = block.current.row("w4-thu")
        assert row is not None
        section = row_section(block, row, outcome, corpus)
        assert section == ("Upcoming.",)

    def test_not_logged_same_day_unclaimed(self) -> None:
        """A hand-built outcome (the real fixture leaves no same-day entry
        unclaimed): `claimant is None` prints the bare bullet, no
        parenthesis."""
        block = _block()
        corpus = _corpus()
        row = block.current.row("w1-wed-run")
        assert row is not None
        outcome = _outcome(
            "w1-wed-run",
            RowState.NOT_LOGGED,
            same_day=(("w1-wed-ride-log", None),),
        )
        section = row_section(block, row, outcome, corpus)
        assert section == (
            "Not logged: no logged workout on 2026-02-04 is of this type.",
            "",
            "Logged on this day:",
            "- [w1-wed-ride-log](../../workouts/w1-wed-ride-log.md) -- Ride",
        )

    def test_not_logged_same_day_ride_taken_by_another_row(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        outcome = next(row for row in reconciliation.rows if row.row_id == "w1-wed-run")
        row = block.current.row("w1-wed-run")
        assert row is not None
        section = row_section(block, row, outcome, corpus)
        assert section == (
            "Not logged: no logged workout on 2026-02-04 is of this type.",
            "",
            "Logged on this day:",
            "- [w1-wed-ride-log](../../workouts/w1-wed-ride-log.md) -- "
            "Ride (taken by `w1-wed-ride`)",
        )

    def test_skipped_with_reason(self) -> None:
        outcome = _outcome(
            "r1",
            RowState.SKIPPED,
            override_index=0,
            override_date=date(2026, 2, 10),
            reason="Illness",
        )
        block = _block()
        row = block.current.row("w2-tue")
        assert row is not None
        section = row_section(block, row, outcome, _corpus())
        assert section == (
            "Skipped by the plan source (override dated 2026-02-10): Illness.",
        )

    def test_skipped_with_no_reason_ends_at_the_parenthesis(self) -> None:
        outcome = _outcome(
            "r1", RowState.SKIPPED, override_index=0, override_date=date(2026, 2, 10)
        )
        block = _block()
        row = block.current.row("w2-tue")
        assert row is not None
        section = row_section(block, row, outcome, _corpus())
        assert section == ("Skipped by the plan source (override dated 2026-02-10).",)


class TestCountLine:
    def test_all_upcoming(self) -> None:
        block = _block()
        corpus = _corpus()
        # `place_resolution` looks up each outcome's row by id in
        # `block.current`, so the count line is pinned here over a
        # purpose-built reconciliation naming three of the real fixture
        # block's row ids, all `UPCOMING` -- independent of the golden's
        # own richer, mixed-state count line above.
        real_rows = tuple(
            _outcome(row.id, RowState.UPCOMING) for row in block.current.rows[:3]
        )
        rec = BlockReconciliation(
            block_id=block.id,
            rows=real_rows,
            mesocycles=(),
            methodology=_CHOICE,
            problems=(),
        )
        resolution = place_resolution(block, rec, corpus)
        assert resolution.block_lines[0] == "Planned workouts: 3 -- 3 upcoming."

    def test_no_rows(self) -> None:
        block = _block()
        corpus = _corpus()
        rec = BlockReconciliation(
            block_id=block.id, rows=(), mesocycles=(), methodology=_CHOICE, problems=()
        )
        resolution = place_resolution(block, rec, corpus)
        assert resolution.block_lines[0] == "Planned workouts: 0."


# ===========================================================================
# The block lines' three conditional lines are each pinned to their own
# condition, not printed unconditionally
# ===========================================================================


class TestBlockLinesOmitAbsentSections:
    def test_no_ambiguous_and_no_problems_yields_the_count_and_methodology_lines(
        self,
    ) -> None:
        """No `Ambiguous:` line (no ambiguous row), no `Problems:` line (no
        problem) and no `(k ambiguous)` suffix on the matched count (no
        ambiguous row) -- `block_lines` is exactly the count line, a blank
        separator, and the methodology line below over two plain
        `MATCHED`, `EXACT` rows and no problems."""
        rec = BlockReconciliation(
            block_id="b",
            rows=(
                _outcome(
                    "w1-mon",
                    RowState.MATCHED,
                    stems=("w1-mon-log",),
                    confidence=Confidence.EXACT,
                ),
                _outcome(
                    "w1-wed-ride",
                    RowState.MATCHED,
                    stems=("w1-wed-ride-log",),
                    confidence=Confidence.EXACT,
                ),
            ),
            mesocycles=(),
            methodology=_CHOICE,
            problems=(),
        )
        assert place_resolution(_block(), rec, _corpus()).block_lines == (
            "Planned workouts: 2 -- 2 matched.",
            "",
            "Methodology: threshold (configured).",
        )


# ===========================================================================
# The `indoor` word is `page.INDOOR_WORD` itself, never a second, bare
# spelling this module could drift from (Req 7.7)
# ===========================================================================


class TestIndoorWordIsNotRespelled:
    def test_source_has_no_bare_constant_equal_to_indoor_word(self) -> None:
        """An AST pin, not a runtime one: a bare `"indoor"` literal is
        equal by value to `page.INDOOR_WORD` at runtime, so only the source
        can tell the two apart, even though the literal is a second spelling
        this module could drift from. Walk every `ast.Constant` in this
        module's own source and assert none of them equals
        `page.INDOOR_WORD` by value -- a docstring merely mentioning
        `page.INDOOR_WORD` as prose is a different (longer) string and
        does not trip this."""
        source_path = Path(inspect.getfile(place_resolution))
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        constants = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)]
        assert constants, "the walk found no ast.Constant nodes -- not a real parse"
        assert not any(constant.value == page.INDOOR_WORD for constant in constants)


# ===========================================================================
# The after-table lines: order and the singular-count grammar
# ===========================================================================


class TestAfterTableLines:
    def test_unplanned_listing_comes_before_excluded(self) -> None:
        block = _block()
        corpus = _corpus()
        unplanned = (
            _logged(
                "unplanned-x1", day=date(2026, 1, 5), load=10, methodology="threshold"
            ),
            _logged(
                "unplanned-x2", day=date(2026, 1, 6), load=15, methodology="threshold"
            ),
        )
        excluded = (
            _logged(
                "excluded-x1", day=date(2026, 1, 7), load=20, methodology="banister"
            ),
        )
        mesocycle = _mesocycle(
            number=9, methodology="threshold", unplanned=unplanned, excluded=excluded
        )
        rec = BlockReconciliation(
            block_id=block.id,
            rows=(),
            mesocycles=(mesocycle,),
            methodology=_CHOICE,
            problems=(),
        )
        resolution = place_resolution(block, rec, corpus)
        assert resolution.mesocycles[9].after_table == (
            "Unplanned: 2 logged workouts in this window match no planned workout.",
            "- [unplanned-x1](../workouts/unplanned-x1.md) -- 2026-01-05, Run, load 10",
            "- [unplanned-x2](../workouts/unplanned-x2.md) -- 2026-01-06, Run, load 15",
            "",
            "Excluded from the sum (scored under another methodology):",
            "- [excluded-x1](../workouts/excluded-x1.md) -- 2026-01-07, Run, "
            "load 20 under other (excluded from the sum)",
        )

    def test_one_unplanned_workout_uses_the_singular_verb(self) -> None:
        block = _block()
        corpus = _corpus()
        unplanned = (
            _logged(
                "unplanned-only", day=date(2026, 1, 5), load=10, methodology="threshold"
            ),
        )
        mesocycle = _mesocycle(number=9, methodology="threshold", unplanned=unplanned)
        rec = BlockReconciliation(
            block_id=block.id,
            rows=(),
            mesocycles=(mesocycle,),
            methodology=_CHOICE,
            problems=(),
        )
        resolution = place_resolution(block, rec, corpus)
        assert resolution.mesocycles[9].after_table[0] == (
            "Unplanned: 1 logged workout in this window matches no planned workout."
        )


# ===========================================================================
# BlockReconciliation invariants
# ===========================================================================


class TestBlockReconciliationInvariants:
    def test_counts_sum_to_row_count(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        assert sum(reconciliation.counts().values()) == len(reconciliation.rows)

    def test_ambiguous_names_the_one_matched_row_of_the_real_fixture(self) -> None:
        """The real fixture's `w1-fri-a` / `w1-fri-b` competing pair puts
        exactly one row in `.ambiguous`: `confidence` is set only on the
        `MATCHED` row (`w1-fri-a`); `w1-fri-b` is `NOT_LOGGED` with
        `confidence is None`, so it never appears here (see
        `TestRowSection.test_not_logged_ambiguous_competitor_section` for
        its own section)."""
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        assert reconciliation.ambiguous == ("w1-fri-a",)

    def test_ambiguous_preserves_block_order_not_sorted(self) -> None:
        """Block order here (`row-c`, `row-a`, `row-b`) differs from both
        the ascending and the descending sort of the ids, so a mutation
        that sorts `ambiguous` in either direction reds against this
        assertion."""
        ambiguous = Confidence.AMBIGUOUS
        outcomes = (
            _outcome("row-c", RowState.MATCHED, stems=("s1",), confidence=ambiguous),
            _outcome("row-a", RowState.MATCHED, stems=("s2",), confidence=ambiguous),
            _outcome("row-b", RowState.MATCHED, stems=("s3",), confidence=ambiguous),
        )
        rec = BlockReconciliation(
            block_id="b", rows=outcomes, mesocycles=(), methodology=_CHOICE, problems=()
        )
        assert rec.ambiguous == ("row-c", "row-a", "row-b")

    def test_unplanned_count_sums_the_mesocycles(self) -> None:
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        assert reconciliation.unplanned_count == sum(
            len(mesocycle.unplanned) for mesocycle in reconciliation.mesocycles
        )
        assert reconciliation.unplanned_count == 4

    def test_counts_include_every_state_with_zero(self) -> None:
        rec = BlockReconciliation(
            block_id="b", rows=(), mesocycles=(), methodology=_CHOICE, problems=()
        )
        counts = rec.counts()
        assert set(counts) == set(RowState)
        assert all(value == 0 for value in counts.values())


# ===========================================================================
# The blank-line separator between paragraph-level lines is a CommonMark
# necessity, not decoration -- `_after_table_lines`, `_block_lines` and
# `_split_section` all join their entries with a bare `"\n"` (block_page.py,
# planned_page.py), under which a plain line directly after a list item is
# a *lazy continuation* of that item and two adjacent plain lines soft-wrap
# into one paragraph. Pinned first at the object level (the general
# invariant below, called only from the three fixture-walk tests it feeds,
# over every rendered tuple this fixture reaches) and then by parsing the
# *rendered page* with `markdown-it-py` (a real dependency, `pyproject.toml`)
# -- the real proof, since a golden byte-diff alone would not show a list
# had absorbed the heading below it.
# ===========================================================================


def _assert_no_lazy_continuation_or_soft_wrap(lines: tuple[str, ...]) -> None:
    """Over one rendered tuple (`after_table`, `block_lines` or a row's
    `section`): no bullet line (`"- ..."`) is ever directly followed by a
    non-empty, non-bullet line (that would be a CommonMark lazy
    continuation, absorbing the follower into the bullet's own list item),
    and no two non-empty, non-bullet ("paragraph-level") lines are ever
    directly adjacent (CommonMark would soft-wrap them into one paragraph).
    A non-bullet line directly followed by a bullet line is fine -- a list
    may interrupt a paragraph without a blank line between them (the
    `Problems:` and `Logged on this day:` headers rely on exactly this)."""
    for index in range(len(lines) - 1):
        prev, nxt = lines[index], lines[index + 1]
        if not nxt:
            continue
        if prev.startswith("- ") and not nxt.startswith("- "):
            raise AssertionError(
                f"line {nxt!r} directly follows bullet line {prev!r} with no "
                "blank line between them -- CommonMark would lazily "
                "continue it into the bullet's own list item"
            )
        if prev and not prev.startswith("- ") and not nxt.startswith("- "):
            raise AssertionError(
                f"paragraph-level lines {prev!r} and {nxt!r} are directly "
                "adjacent with no blank line between them -- CommonMark "
                "would soft-wrap them into one paragraph"
            )


class TestBlankLineSeparationIsCommonMarkSound:
    def test_after_table_lines_of_both_goldens(self) -> None:
        """Both methodologies produce all 4 fixture mesocycles, with 3 of
        them non-empty (having any `after_table` lines at all) under
        `_CHOICE` and 2 under `_PROBLEM` (mesocycle 1, every page claimed,
        has an empty `after_table` in both cases; mesocycle 2's
        excluded-only listing exists only under `_CHOICE`, which is the
        3-vs-2 difference) -- asserted explicitly so an
        empty `mesocycles` dict, or one whose values are all empty tuples,
        cannot pass this test vacuously."""
        block = _block()
        corpus = _corpus()
        expected_nonempty = {_CHOICE: 3, _PROBLEM: 2}
        for methodology in (_CHOICE, _PROBLEM):
            reconciliation = _reconciliation(block, corpus, methodology=methodology)
            resolution = place_resolution(block, reconciliation, corpus)
            assert len(resolution.mesocycles) == 4
            nonempty = 0
            for extra in resolution.mesocycles.values():
                _assert_no_lazy_continuation_or_soft_wrap(extra.after_table)
                if extra.after_table:
                    nonempty += 1
            assert nonempty == expected_nonempty[methodology]

    def test_block_lines_of_both_goldens(self) -> None:
        block = _block()
        corpus = _corpus()
        for methodology in (_CHOICE, _PROBLEM):
            reconciliation = _reconciliation(block, corpus, methodology=methodology)
            resolution = place_resolution(block, reconciliation, corpus)
            assert resolution.block_lines
            _assert_no_lazy_continuation_or_soft_wrap(resolution.block_lines)

    def test_every_row_section_of_both_goldens(self) -> None:
        """The fixture block has 11 current rows in both methodologies, and
        every one of them has a non-empty `section` -- asserted explicitly
        so an empty `rows` dict cannot pass this test vacuously."""
        block = _block()
        corpus = _corpus()
        for methodology in (_CHOICE, _PROBLEM):
            reconciliation = _reconciliation(block, corpus, methodology=methodology)
            resolution = place_resolution(block, reconciliation, corpus)
            assert len(resolution.rows) == 11
            for row_resolution in resolution.rows.values():
                assert row_resolution.section
                _assert_no_lazy_continuation_or_soft_wrap(row_resolution.section)

    def test_excluded_heading_starts_its_own_top_level_paragraph(self) -> None:
        """The real proof: parse the *rendered block page* -- carrying both
        of the fixture's `EXCLUDED` headings, mesocycle 2 (excluded-only,
        which is always its own top-level paragraph regardless of the blank
        line under test) and mesocycle 3 (the both-listings case, the one
        this test actually pins) -- with `markdown-it-py` and confirm each
        `EXCLUDED` heading opens a fresh, top-level (`level == 0`) paragraph
        of its own rather than being embedded in the inline content of the
        preceding bullet.

        A `next(...)` search for the first exact match is not enough: with
        two `EXCLUDED` headings in the rendered page, dropping the blank
        `""` `_after_table_lines` inserts before mesocycle 3's `EXCLUDED`
        only swallows *that* heading into the preceding bullet's own inline
        token (as `"...(excluded from the sum)\\nExcluded from the sum
        ..."`, no longer matching `== EXCLUDED`); mesocycle 2's heading is
        unaffected and still matches exactly, so a `next(...)` search would
        find it first and this test would stay green under that mutation.
        Collecting every exact match instead, and separately asserting no
        inline token's content contains `EXCLUDED` embedded with a literal
        `"\\n"` (the swallowed form), catches it: dropping the blank drops
        the exact-match count from 2 to 1 and trips the swallowed-form
        assertion."""
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        rendered = render_block_page(block, resolution)
        tokens = _MD.parse(rendered)
        inline_tokens = [tok for tok in tokens if tok.type == "inline"]
        for tok in inline_tokens:
            if tok.content != EXCLUDED:
                assert not (EXCLUDED in tok.content and "\n" in tok.content), (
                    f"{EXCLUDED!r} was swallowed into a larger paragraph "
                    f"instead of starting its own: {tok.content!r}"
                )
        heading_indices = [
            i
            for i, tok in enumerate(tokens)
            if tok.type == "inline" and tok.content == EXCLUDED
        ]
        assert len(heading_indices) == 2, (
            "expected exactly 2 EXCLUDED headings -- mesocycle 2 "
            "(excluded-only) and mesocycle 3 (both-listings) -- got "
            f"{len(heading_indices)}"
        )
        for heading_index in heading_indices:
            paragraph_open = tokens[heading_index - 1]
            assert paragraph_open.type == "paragraph_open"
            assert paragraph_open.level == 0, (
                "the EXCLUDED heading is nested inside a list item "
                f"(level {paragraph_open.level}) rather than starting its "
                "own top-level paragraph"
            )

    def test_block_lines_paragraphs_are_not_merged(self) -> None:
        """The `## Resolution` section's `Planned workouts:` and
        `Methodology:` lines parse as two distinct top-level paragraphs,
        never one soft-wrapped paragraph carrying both sentences.
        Mutation: drop the blank `""` `_block_lines` inserts between them
        (placement.py) and this test reds, since the two sentences then
        share one inline token whose content embeds a literal `\\n`."""
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        rendered = render_block_page(block, resolution)
        tokens = _MD.parse(rendered)
        inline_contents = [tok.content for tok in tokens if tok.type == "inline"]
        assert any(
            content.startswith("Planned workouts:") for content in inline_contents
        )
        assert any(
            content.startswith("Methodology:") and "\n" not in content
            for content in inline_contents
        )

    def test_logged_on_this_day_paragraph_follows_a_blank_line(self) -> None:
        """The NOT_LOGGED/UPCOMING split section: rendering `w1-fri-b`'s
        planned page (the real fixture's competing pair -- state sentence,
        competitor sentence, `Logged on this day:` listing, all three
        present) and parsing it confirms the competitor sentence is its own
        top-level paragraph, not folded into the state sentence above it.
        Mutation: drop either blank `""` `_split_section` inserts
        (placement.py) and this test reds."""
        block = _block()
        corpus = _corpus()
        reconciliation = _reconciliation(block, corpus, methodology=_CHOICE)
        resolution = place_resolution(block, reconciliation, corpus)
        row = block.current.row("w1-fri-b")
        assert row is not None
        rendered = render_planned_page(block, row, resolution)
        tokens = _MD.parse(rendered)
        inline_contents = [tok.content for tok in tokens if tok.type == "inline"]
        assert any(
            content.startswith("Not logged:") and "\n" not in content
            for content in inline_contents
        )
        assert any(
            content.startswith("2 planned workouts of this type")
            and "\n" not in content
            for content in inline_contents
        )
        assert any(content == "Logged on this day:" for content in inline_contents)
