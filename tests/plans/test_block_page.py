"""Tests for the block page renderer (training-blocks spec, task 3.2). See
"BlockPage" in `.kiro/specs/training-blocks/design.md`
(Req 3.7, 4.2-4.11, 5.6, 6.2, 6.3).

Test File Ownership (tasks.md): `tests/plans/test_block_page.py` and
`tests/plans/golden/block*.md` are 3.2's alone. No fixture is added under
`tests/plans/fixtures/`: the golden renders 2.3's `full.toml` (its
properties are fixed in that task's docstring and reproduced in this
module's comments where a specific value is pinned), loaded here through
`parse_block` -- no `conftest.py`.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from fitdocs import layout
from fitdocs.model import Modality, Sport
from fitdocs.plans.block_page import render_block_page
from fitdocs.plans.model import (
    Amendment,
    Block,
    MesocycleTarget,
    PlannedWorkout,
    PlanState,
    RowChanged,
    build_block,
)
from fitdocs.plans.resolution import (
    MesocycleResolution,
    Resolution,
    RowResolution,
    unresolved,
)
from fitdocs.plans.source import parse_block

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"

_BLOCK_ID = "base-build"


def _full_block() -> Block:
    text = (_FIXTURES / "full.toml").read_text(encoding="utf-8")
    return parse_block(text, block_id=_BLOCK_ID)


def _row(
    row_id: str,
    day: date,
    *,
    sport: Sport = Sport.RUN,
    title: str = "Title",
    summary: str = "Summary",
    prescription: str = "Do it.",
) -> PlannedWorkout:
    return PlannedWorkout(
        id=row_id,
        date=day,
        sport=sport,
        modality=None,
        indoor=None,
        title=title,
        summary=summary,
        prescription=prescription,
    )


def _empty_block() -> Block:
    """A block with no rows and no stated targets at all --
    `PlanState(rows=(), targets=())` holds neither -- so every mesocycle
    is both empty (all rest days) and untargeted (`Target load: none`
    twice in the golden), and the revision record says plainly that there
    were no planned workouts and no mesocycle targets as first written
    (design.md's second golden)."""
    starts = date(2026, 3, 2)
    ends = date(2026, 3, 15)  # 14 days, mesocycle_days=7 -> two even mesocycles
    empty = PlanState(rows=(), targets=())
    return build_block(
        id="recovery-week",
        title="Recovery week",
        starts=starts,
        ends=ends,
        goal="Deload and recover before the next block.",
        mesocycle_days=7,
        original=empty,
        current=empty,
        amendments=(),
        overrides=(),
    )


# --- golden: 2.3's full fixture (Req 3.7, 4.2-4.11, 5.6) ---------------------


def test_full_fixture_matches_golden() -> None:
    block = _full_block()
    rendered = render_block_page(block, unresolved())
    expected = (_GOLDEN / "block.md").read_text(encoding="utf-8")
    assert rendered == expected


def test_empty_block_matches_golden() -> None:
    block = _empty_block()
    rendered = render_block_page(block, unresolved())
    expected = (_GOLDEN / "block-empty.md").read_text(encoding="utf-8")
    assert rendered == expected


def test_empty_block_says_no_planned_workouts_and_no_amendments() -> None:
    rendered = render_block_page(_empty_block(), unresolved())
    assert "No planned workouts as first written." in rendered
    assert "No amendments." in rendered
    assert "No mesocycle targets as first written." in rendered


# --- postconditions: fence, banner, one notes region (Req 4.2, 4.9) --------


def test_opens_with_the_frontmatter_fence() -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert rendered.startswith("---\n")


def test_banner_appears_exactly_once_outside_any_region() -> None:
    from fitdocs.contract import DOC_BANNER

    rendered = render_block_page(_full_block(), unresolved())
    assert rendered.count(DOC_BANNER) == 1
    banner_index = rendered.index(DOC_BANNER)
    begin_index = rendered.index("<!-- fitdocs:begin:notes -->")
    end_index = rendered.index("<!-- fitdocs:end:notes -->")
    assert banner_index < begin_index < end_index


def test_exactly_one_notes_region_pair() -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert rendered.count("<!-- fitdocs:begin:notes -->") == 1
    assert rendered.count("<!-- fitdocs:end:notes -->") == 1


def test_notes_region_bare_right_after_the_title() -> None:
    """Named mutation: place `notes_region()` after the summary lines
    instead of right after the H1 -- this reds."""
    rendered = render_block_page(_full_block(), unresolved())
    title_index = rendered.index("# Base build")
    after_title = rendered[title_index:].split("\n\n", 2)
    # after_title[0] is the H1 line itself; the very next block must be
    # the bare notes region, not "Starts: ...".
    assert after_title[1].startswith("<!-- fitdocs:begin:notes -->")


def test_byte_identical_across_two_calls() -> None:
    block = _full_block()
    resolution = unresolved()
    first = render_block_page(block, resolution)
    second = render_block_page(block, resolution)
    assert first == second


# --- date-coverage postcondition (Req 4.5) -----------------------------------


def test_day_tables_cover_every_date_exactly_once() -> None:
    """Named mutation: drop the rest rows from `_day_rows` -- this reds
    directly (both goldens go missing their rest rows). This assertion
    additionally catches a *duplicated* rest row for the same date, which
    `sorted(set(found)) == expected_days` alone cannot: a duplicate
    collapses right back into the same set and still compares equal. A
    legitimate multi-workout day (2026-01-08) repeats its date across two
    WORKOUT rows by design, so the property this pins is narrower: every
    rest-row date is unique, and no date is both a rest row and a workout
    row anywhere in the page."""
    block = _full_block()
    rendered = render_block_page(block, unresolved())
    row_pattern = re.compile(
        r"^\| (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{4}-\d{2}-\d{2}) \|(.*)\|$"
    )
    rest_days: list[date] = []
    workout_days: list[date] = []
    for line in rendered.split("\n"):
        match = row_pattern.match(line)
        if match is None:
            continue
        day = date.fromisoformat(match.group(1))
        if "_rest_" in match.group(2):
            rest_days.append(day)
        else:
            workout_days.append(day)

    expected_days = []
    day = block.starts
    while day <= block.ends:
        expected_days.append(day)
        day += timedelta(days=1)

    assert rest_days  # the walk actually found rest rows to check
    assert len(rest_days) == len(set(rest_days))
    assert set(rest_days).isdisjoint(workout_days)
    assert set(rest_days) | set(workout_days) == set(expected_days)


def test_two_workout_day_keeps_source_order_not_id_order() -> None:
    """`full.toml`'s 2026-01-08 carries "w1-thu-b" before "w1-thu-a" in
    file order -- ids that sort alphabetically opposite to that order.
    Named mutation: sort a day's rows by id in `_day_rows` -- this reds."""
    block = _full_block()
    rendered = render_block_page(block, unresolved())
    b_index = rendered.index("w1-thu-b")
    a_index = rendered.index("w1-thu-a")
    assert b_index < a_index


# --- placement test: a caller-built Resolution lands in its own slot (Req 6.2) --


def test_resolution_fragments_land_in_their_slot_and_nowhere_else() -> None:
    block = _full_block()
    # A pipe in the row-cell sentinel pins that the resolution cell passes
    # through `cell()` too (design.md: "every table cell through cell()"):
    # the escaped form must appear once, the raw (unescaped) form never.
    row_sentinel = "SENTINEL-ROW|CELL-7f3a"
    row_sentinel_escaped = "SENTINEL-ROW\\|CELL-7f3a"
    section_sentinel = "SENTINEL-ROW-SECTION-91be"  # never rendered by the block page
    before_sentinel = "SENTINEL-BEFORE-TABLE-c04d"
    after_sentinel = "SENTINEL-AFTER-TABLE-e615"
    block_sentinel = "SENTINEL-BLOCK-LINES-a2c9"

    resolution = Resolution(
        rows={"w1-mon": RowResolution(cell=row_sentinel, section=(section_sentinel,))},
        mesocycles={
            1: MesocycleResolution(
                before_table=(before_sentinel,), after_table=(after_sentinel,)
            )
        },
        block_lines=(block_sentinel,),
    )
    rendered = render_block_page(block, resolution)

    assert rendered.count(row_sentinel_escaped) == 1
    assert rendered.count(row_sentinel) == 0
    assert rendered.count(section_sentinel) == 0
    assert rendered.count(before_sentinel) == 1
    assert rendered.count(after_sentinel) == 1
    assert rendered.count(block_sentinel) == 1
    assert rendered.count("## Resolution") == 1

    lines = rendered.split("\n")
    target_index = next(i for i, line in enumerate(lines) if line == "Target load: 300")
    before_index = next(i for i, line in enumerate(lines) if line == before_sentinel)
    header_index = next(
        i for i, line in enumerate(lines) if line.startswith("| Day | Sport")
    )
    # Named mutation: place `after_table` lines before the table -- this reds.
    assert target_index < before_index < header_index

    # Mesocycle 1's window is 2026-01-05..2026-01-11; its LAST calendar day
    # (Sun 2026-01-11) is a rest day in the current plan (amendment 2 moves
    # "w1-sun" off this date), so it is the last row of the day table.
    # Anchoring on the table's FIRST row alone cannot distinguish "after
    # the table" from "mid-table" -- inserting `after_table` right after
    # the first row would still satisfy "somewhere after the first row,
    # before the next heading". Anchoring on the LAST row, immediately
    # (one blank line) before the sentinel, rules that out.
    after_index = next(i for i, line in enumerate(lines) if line == after_sentinel)
    assert lines[after_index - 1] == ""
    assert lines[after_index - 2] == "| Sun 2026-01-11 | | _rest_ | | |"
    next_heading_index = next(
        i for i in range(after_index, len(lines)) if lines[i].startswith("## ")
    )
    assert after_index < next_heading_index

    block_index = next(i for i, line in enumerate(lines) if line == block_sentinel)
    mesocycle_headings = [
        i for i, line in enumerate(lines) if line.startswith("## Mesocycle")
    ]
    revision_index = next(
        i for i, line in enumerate(lines) if line == "## Revision record"
    )
    assert max(mesocycle_headings) < block_index < revision_index
    # N7/N8: `before_table` and the block-level `## Resolution` heading
    # must each be its own blank-separated paragraph, not glued to its
    # neighbour with a single "\n" -- the ordering assertions above alone
    # do not distinguish "on its own paragraph" from "glued to the
    # previous line with one newline" (both still put `before_index`
    # after `target_index` and before `header_index`).
    assert lines[before_index - 1] == ""
    assert lines[before_index + 1] == ""
    assert lines[block_index - 1] == ""
    assert lines[block_index - 2] == "## Resolution"


def test_resolution_fills_the_same_slots_without_changing_structure() -> None:
    """Req 6.2: a supplied `Resolution` must render "into the same slots
    ... without any other change to the pages' structure." Peel the
    caller-supplied content back out of the render and the result must be
    byte-identical to the default (`unresolved()`) render -- i.e. the
    golden. This is a different, stronger property than the placement
    test's index-based ordering checks, and pins three ways the render
    could still add or drop structure while every ordering check stays
    green:
      - N7: glue `before_table` to `Target load:` with a single `"\\n"`
        instead of `"\\n\\n"` in `_mesocycle_section` -- `target_index <
        before_index < header_index` in the placement test is unaffected
        by which separator was used, so it stays green; here, peeling out
        only `"\\n\\n" + before_sentinel` leaves a dangling single `"\\n"`
        that does not match the golden's `"\\n\\n"` between `Target
        load:` and the table.
      - N8: emit `"## Resolution\\n"` instead of `"## Resolution\\n\\n"`
        before `resolution.block_lines` in `render_block_page` -- same
        blind spot.
      - N11: append a stray `"\\n\\n## Interloper"` heading after
        `after_table` -- nothing upstream asserts that nothing else
        changed; peeling out the four known insertions leaves the
        interloper heading behind, so the result no longer equals the
        golden.
    """
    block = _full_block()
    row_sentinel = "SENTINEL-ROW|CELL-7f3a"
    row_sentinel_escaped = "SENTINEL-ROW\\|CELL-7f3a"
    before_sentinel = "SENTINEL-BEFORE-TABLE-c04d"
    after_sentinel = "SENTINEL-AFTER-TABLE-e615"
    block_sentinel = "SENTINEL-BLOCK-LINES-a2c9"

    resolution = Resolution(
        rows={"w1-mon": RowResolution(cell=row_sentinel, section=())},
        mesocycles={
            1: MesocycleResolution(
                before_table=(before_sentinel,), after_table=(after_sentinel,)
            )
        },
        block_lines=(block_sentinel,),
    )
    rendered = render_block_page(block, resolution)

    peeled = rendered.replace(row_sentinel_escaped, "unresolved")
    peeled = peeled.replace("\n\n" + before_sentinel, "")
    peeled = peeled.replace("\n\n" + after_sentinel, "")
    peeled = peeled.replace("## Resolution\n\n" + block_sentinel + "\n\n", "")

    assert peeled == render_block_page(block, unresolved())


def test_no_block_lines_means_no_resolution_section() -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert "## Resolution" not in rendered


# --- ValueError from page.check_resolution (Req 6.3) -------------------------


def test_unknown_row_id_raises() -> None:
    block = _full_block()
    resolution = Resolution(
        rows={"does-not-exist": RowResolution(cell="x", section=())},
        mesocycles={},
    )
    with pytest.raises(ValueError, match="does-not-exist"):
        render_block_page(block, resolution)


def test_unknown_mesocycle_number_raises() -> None:
    block = _full_block()
    resolution = Resolution(rows={}, mesocycles={99: MesocycleResolution()})
    with pytest.raises(ValueError, match="99"):
        render_block_page(block, resolution)


def test_multiline_cell_raises() -> None:
    block = _full_block()
    resolution = Resolution(
        rows={"w1-mon": RowResolution(cell="line one\nline two", section=())},
        mesocycles={},
    )
    with pytest.raises(ValueError):
        render_block_page(block, resolution)


# --- forbidden-phrase pin over the default render (Req 4.7) -----------------


@pytest.mark.parametrize(
    "phrase", ["matched", "skipped", "upcoming", "not logged", "load_value"]
)
def test_forbidden_phrase_absent_from_default_render(phrase: str) -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert phrase not in rendered


# --- revision record shapes (Req 3.7, 4.8) -----------------------------------


def test_as_first_written_table_uses_original_dates_not_current() -> None:
    """ "w1-sun" is moved by amendment 2 from 2026-01-11 to 2026-01-20.
    Named mutation: build the "As first written" table over
    `block.current.rows` instead of `block.original.rows` -- this reds
    (the row would carry the amended date instead of the original one)."""
    rendered = render_block_page(_full_block(), unresolved())
    as_first_written = rendered.split("### As first written", 1)[1].split(
        "### Amendment", 1
    )[0]
    assert "| w1-sun | 2026-01-11 |" in as_first_written
    assert "2026-01-20" not in as_first_written


def test_short_mesocycle_states_the_shortness_clause() -> None:
    """Named mutation: omit the ` -- shorter than the stated L` clause --
    this reds."""
    rendered = render_block_page(_full_block(), unresolved())
    assert (
        "## Mesocycle 3 -- 2026-01-19 to 2026-01-22 (4 days) -- shorter "
        "than the stated 7 days" in rendered
    )


def test_unset_target_before_an_amendment_renders_as_unset_not_empty() -> None:
    """Mesocycle 2 has no stated target before amendment 1 sets one.
    Named mutation: `_format_load_or_unset`/`_format_focus_or_unset` return
    `""` instead of `"(unset)"` for `None` -- this reds."""
    rendered = render_block_page(_full_block(), unresolved())
    assert "target load (unset) -> 250" in rendered
    assert 'focus (unset) -> "Build"' in rendered


def test_bracket_in_title_is_escaped_in_the_link_text() -> None:
    """ "w1-thu-b"'s title carries a `]` ("Long run [key]"). Named mutation:
    stop routing the link text through `link_text()` -- this reds. (Pins
    design.md's own stated rule -- "every link text through `link_text()`"
    -- directly, rather than any claim about how a given markdown renderer
    would parse an unescaped bracket; CommonMark itself balances nested
    `[`/`]` pairs, so an unescaped `]` here would not, in fact, break every
    renderer's link parsing.)"""
    rendered = render_block_page(_full_block(), unresolved())
    link = f"[Long run \\[key\\]]({layout.planned_rel_link(_BLOCK_ID, 'w1-thu-b')})"
    assert link in rendered
    assert "[Long run [key]]" not in rendered


def test_pipe_in_summary_is_escaped_as_a_table_cell() -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert "Zone 2 \\| easy effort" in rendered


def test_row_added_and_removed_bullets_present() -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert (
        '- Added `w1-sat` -- 2026-01-10, Run, "Long run" -- Zone 2 endurance'
        in rendered
    )
    assert '- Removed `w1-sat` -- 2026-01-10, Run, "Long run"' in rendered


def test_prescription_change_is_a_was_now_blockquote() -> None:
    rendered = render_block_page(_full_block(), unresolved())
    assert "- `w1-mon`: prescription changed" in rendered
    assert "  - was:" in rendered
    assert "    > 45 minutes easy, conversational pace." in rendered
    assert "  - now:" in rendered
    assert "    > 60 minutes easy, extended after feeling strong." in rendered


# --- hand-built blocks: fixtures no `full.toml` scenario reaches --------------


def _order_check_block() -> Block:
    """Hand-built via `build_block`, never through the parser (allowed in
    this test module -- the "no fixtures" rule in Test File Ownership
    concerns `tests/plans/fixtures/` only). The original plan's row order
    is 01-10, 01-06, 01-08 in FILE order -- deliberately not date order --
    so a renderer that quietly sorted "As first written" by date instead
    of using file order would still pass against `full.toml`'s golden
    (whose original rows happen to already be date-ordered) but not here.
    One row's title carries a `|` to pin `cell()` escaping on this
    table's Title column, which nothing in `full.toml` exercises (the
    only `|` there is in a summary, and the only `]` is in a title, but
    never a `|` in a title)."""
    rows = (
        _row("w-b", date(2026, 2, 10), title="Track | Field"),
        _row("w-a", date(2026, 2, 6)),
        _row("w-c", date(2026, 2, 8)),
    )
    state = PlanState(rows=rows, targets=())
    return build_block(
        id="order-check",
        title="Order check",
        starts=date(2026, 2, 1),
        ends=date(2026, 2, 28),
        goal="Check source order and escaping.",
        mesocycle_days=28,
        original=state,
        current=state,
        amendments=(),
        overrides=(),
    )


def test_as_first_written_table_keeps_source_order_not_date_order() -> None:
    """Named mutation: `sorted(block.original.rows, key=lambda r: r.date)`
    in place of `block.original.rows` -- this reds here even though it
    would stay green against `full.toml`'s golden, whose original rows
    are already date-ordered."""
    rendered = render_block_page(_order_check_block(), unresolved())
    b_index = rendered.index("| w-b |")
    a_index = rendered.index("| w-a |")
    c_index = rendered.index("| w-c |")
    assert b_index < a_index < c_index


def test_as_first_written_table_escapes_a_pipe_in_the_title() -> None:
    """Named mutation: drop `page.cell(...)` around the Title column in
    `_revision_record_section` -- this reds."""
    rendered = render_block_page(_order_check_block(), unresolved())
    assert "Track \\| Field" in rendered
    assert "Track | Field" not in rendered


def test_row_changed_bullet_lists_fields_in_mutable_fields_order() -> None:
    """A single amendment changing `title`, `summary`, `modality` and
    `indoor` together on one `Workout` row (never `date`, `sport` or
    `prescription`, so none of those branches mask the others).
    `MUTABLE_FIELDS` is `(date, sport, modality, indoor, title, summary,
    prescription)`, so the inline bullet must list `modality`, then
    `indoor`, then `title`, then `summary`, in that order. `full.toml`'s
    only `RowChanged` records are a prescription change and a date
    change, so none of these four fields is otherwise reachable. Named
    mutation: iterate
    `sorted(MUTABLE_FIELDS)` (alphabetical) instead of `MUTABLE_FIELDS`
    -- this reds, since alphabetical order puts `indoor` before
    `modality` and `prescription` before `sport`/`summary`/`title`."""
    before_row = _row(
        "w-x", date(2026, 2, 10), sport=Sport.WORKOUT, title="A", summary="S1"
    )
    after_row = replace(
        before_row, modality=Modality.STRENGTH, indoor=True, title="B", summary="S2"
    )
    change = RowChanged(before=before_row, after=after_row)
    amendment = Amendment(
        ordinal=1,
        date=date(2026, 2, 12),
        reason="Exercise every single-line field kind",
        changes=(change,),
    )
    original = PlanState(rows=(before_row,), targets=())
    current = PlanState(rows=(after_row,), targets=())
    block = build_block(
        id="kinds-check",
        title="Kinds check",
        starts=date(2026, 2, 1),
        ends=date(2026, 2, 28),
        goal="Exercise every revision-bullet field kind.",
        mesocycle_days=28,
        original=original,
        current=current,
        amendments=(amendment,),
        overrides=(),
    )
    rendered = render_block_page(block, unresolved())
    assert (
        "- `w-x`: modality (unset) -> strength; indoor (unset) -> true; "
        'title "A" -> "B"; summary "S1" -> "S2"'
    ) in rendered


def test_original_target_with_only_focus_renders_focus_only_sentence() -> None:
    """A mesocycle target stated with a focus but no target load, as
    originally written. `full.toml`'s only original target states both
    (mesocycle 1: 300, "Base"), so the focus-only branch of
    `_target_summary` is otherwise unreached. Named mutation:
    `_target_summary` returns `f"{number}: none"` whenever `target_load`
    is `None`, ignoring `focus` entirely -- this reds."""
    original = PlanState(
        rows=(), targets=(MesocycleTarget(number=1, target_load=None, focus="Sharpen"),)
    )
    block = build_block(
        id="focus-only",
        title="Focus only",
        starts=date(2026, 2, 1),
        ends=date(2026, 2, 28),
        goal="Exercise the focus-only target sentence.",
        mesocycle_days=28,
        original=original,
        current=original,
        amendments=(),
        overrides=(),
    )
    rendered = render_block_page(block, unresolved())
    assert "Mesocycle targets as first written: 1: none (Sharpen)" in rendered
