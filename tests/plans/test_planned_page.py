"""Tests for the planned-workout page renderer (training-blocks spec, task
3.3). See "PlannedPage" in `.kiro/specs/training-blocks/design.md`
(Req 3.6, 5.2, 5.3, 5.4, 5.7, 6.2, 6.3).

Test File Ownership (tasks.md): this module and `tests/plans/golden/planned*.md`
belong to 3.3 alone -- `tests/plans/fixtures/full.toml` is 2.3's fixture,
loaded through the parser here rather than duplicated.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fitdocs import contract, docmerge
from fitdocs import layout as layout_
from fitdocs.model import Modality, Sport
from fitdocs.plans import page
from fitdocs.plans.model import Block, PlannedWorkout, PlanState, build_block
from fitdocs.plans.planned_page import render_planned_page
from fitdocs.plans.resolution import Resolution, RowResolution
from fitdocs.plans.source import parse_block

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


def _full_block() -> Block:
    text = (FIXTURES / "full.toml").read_text()
    return parse_block(text, block_id="base-build")


def _simple_block(row: PlannedWorkout) -> Block:
    """A minimal one-row block for tests that need a row the full fixture
    does not carry (e.g. a `|` in the prescription)."""
    state = PlanState(rows=(row,), targets=())
    return build_block(
        id="simple-block",
        title="Simple Block",
        starts=date(2026, 1, 1),
        ends=date(2026, 1, 14),
        goal="Build an aerobic base.",
        mesocycle_days=7,
        original=state,
        current=state,
        amendments=(),
        overrides=(),
    )


# ===========================================================================
# Golden: the full fixture's "Workout (strength, indoor)" row, three-line
# prescription. Read end to end against the design's stated shapes.
# ===========================================================================


class TestGolden:
    def test_w1_fri_matches_the_golden_file(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        expected = (GOLDEN / "planned.md").read_text()
        assert text == expected


# ===========================================================================
# Frontmatter: planned key order, modality/indoor only when stated.
# ===========================================================================


class TestFrontmatter:
    def test_run_row_omits_modality_and_indoor_keys(self) -> None:
        block = _full_block()
        row = block.current.row("w1-mon")
        assert row is not None
        assert row.modality is None
        assert row.indoor is None
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        front = contract.parse_frontmatter(text)
        assert front is not None
        # Checked against the *parsed* mapping, not a literal text search:
        # the only thing a reader is promised is what parses back out.
        assert "modality" not in front
        assert "indoor" not in front

    def test_workout_row_with_indoor_unset_omits_indoor_key(self) -> None:
        # A Workout row carrying a modality but no stated `indoor` (None,
        # not False) -- the sibling row to the golden's indoor=True one --
        # must still omit the key.
        row = PlannedWorkout(
            id="w-strength",
            date=date(2026, 1, 3),
            sport=Sport.WORKOUT,
            modality=Modality.STRENGTH,
            indoor=None,
            title="Strength",
            summary="Circuit",
            prescription="3 rounds.",
        )
        block = _simple_block(row)
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        front = contract.parse_frontmatter(text)
        assert front is not None
        assert "modality" in front  # falsity check: modality itself IS present
        assert "indoor" not in front

    def test_workout_row_with_indoor_false_also_omits_indoor_key(self) -> None:
        row = PlannedWorkout(
            id="w-strength2",
            date=date(2026, 1, 3),
            sport=Sport.WORKOUT,
            modality=Modality.STRENGTH,
            indoor=False,
            title="Strength",
            summary="Circuit",
            prescription="3 rounds.",
        )
        block = _simple_block(row)
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        front = contract.parse_frontmatter(text)
        assert front is not None
        assert "indoor" not in front

    def test_date_round_trips_through_document_date(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        front = contract.parse_frontmatter(text)
        assert contract.document_date(front) == row.date

    def test_h1_title_is_verbatim_not_bracket_escaped(self) -> None:
        # "w1-thu-b"'s title in the shared fixture carries a `]` (falsity in
        # the starting state: the raw title really contains one). A
        # production path that routed the H1 through `page.link_text`
        # (bracket-escaping, the routing this page's own back-link text
        # legitimately uses elsewhere) would visibly change this line.
        block = _full_block()
        row = block.current.row("w1-thu-b")
        assert row is not None
        assert row.title == "Long run [key]"
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        assert "# Long run [key]" in text

    def test_frontmatter_title_is_verbatim_not_pipe_escaped(self) -> None:
        # A title with `|`: a production path that routed the frontmatter
        # `title` value through `page.cell()` (pipe-escaping) would come
        # back through `contract.parse_frontmatter` reading a literal
        # backslash before the pipe, not the row's own value.
        row = PlannedWorkout(
            id="w-pipe-title",
            date=date(2026, 1, 3),
            sport=Sport.RUN,
            modality=None,
            indoor=None,
            title="Long run | fast finish",
            summary="S",
            prescription="P",
        )
        block = _simple_block(row)
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        front = contract.parse_frontmatter(text)
        assert front is not None
        assert front["title"] == row.title
        # The H1 is the same value, also verbatim: routing it through
        # `page.cell()` would render `# Long run \| fast finish`.
        assert f"# {row.title}" in text
        assert "\\|" not in text


class TestSummaryVerbatim:
    def test_summary_pipe_is_not_escaped(self) -> None:
        # "w1-mon"'s summary in the shared fixture carries a `|` (falsity
        # in the starting state: the raw source really contains one, so an
        # implementation that routed the summary through `page.cell()`
        # would visibly change this text, not merely leave it unchanged).
        block = _full_block()
        row = block.current.row("w1-mon")
        assert row is not None
        assert "|" in row.summary
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        assert f"_{row.summary}_" in text
        assert "_Zone 2 | easy effort_" in text
        assert "\\|" not in text


# ===========================================================================
# Mesocycle number: the CURRENT date's window, not the original row's.
# ===========================================================================


class TestMesocycleAcrossAMove:
    def test_moved_row_uses_the_current_window_not_the_original(self) -> None:
        block = _full_block()
        row = block.current.row("w1-sun")
        assert row is not None
        assert row.date == date(2026, 1, 20)
        original_row = block.original.row("w1-sun")
        assert original_row is not None
        assert original_row.date == date(2026, 1, 11)
        # Falsity in the starting state: the ORIGINAL date's mesocycle is 1,
        # genuinely different from the correct answer below.
        assert block.mesocycle_of(original_row.date) == 1
        assert block.mesocycle_of(row.date) == 3

        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        front = contract.parse_frontmatter(text)
        assert front is not None
        assert front["mesocycle"] == 3
        assert front["mesocycle"] != 1


# ===========================================================================
# Resolution section: caller-built content, the unresolved default, and the
# fence rejection.
# ===========================================================================


class TestResolutionSection:
    def test_caller_built_section_lands_under_the_resolution_heading(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        resolution = Resolution(
            rows={
                "w1-fri": RowResolution(
                    cell="matched",
                    section=(
                        "A distinctive-sentinel-xyzzy line one.",
                        "A distinctive-sentinel-xyzzy line two.",
                    ),
                )
            },
            mesocycles={},
        )
        text = render_planned_page(block, row, resolution)
        assert text.count("A distinctive-sentinel-xyzzy line one.") == 1
        assert text.count("A distinctive-sentinel-xyzzy line two.") == 1
        lines = text.splitlines()
        heading_index = lines.index("## Resolution")
        first_index = lines.index("A distinctive-sentinel-xyzzy line one.")
        second_index = lines.index("A distinctive-sentinel-xyzzy line two.")
        assert first_index > heading_index
        # The two section lines must be adjacent (joined by a single `\n`,
        # never a blank-line-separated paragraph break): a caller-supplied
        # multi-line section is `RowResolution.section`'s own line breaks,
        # not a place this renderer re-paragraphs.
        assert second_index == first_index + 1
        # "at the end": the exact tail, byte for byte -- nothing after the
        # second sentinel line but the section's own trailing newline.
        assert text.endswith(
            "## Resolution\n\n"
            "A distinctive-sentinel-xyzzy line one.\n"
            "A distinctive-sentinel-xyzzy line two.\n"
        )

    def test_no_supplied_row_falls_back_to_the_unresolved_default(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        assert "Not yet reconciled against logged workouts." in text

    def test_fence_line_in_the_section_is_rejected(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        resolution = Resolution(
            rows={"w1-fri": RowResolution(cell="x", section=("---",))},
            mesocycles={},
        )
        with pytest.raises(ValueError):
            render_planned_page(block, row, resolution)


# ===========================================================================
# check_resolution delegation: an unknown row id in the resolution.
# ===========================================================================


class TestUnknownId:
    def test_unknown_row_id_in_resolution_raises(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        resolution = Resolution(
            rows={"not-a-real-row": RowResolution(cell="x", section=())},
            mesocycles={},
        )
        with pytest.raises(ValueError, match="not-a-real-row"):
            render_planned_page(block, row, resolution)


# ===========================================================================
# No region marker; byte-equality; the back-link.
# ===========================================================================


class TestNoRegionAndDeterminism:
    def test_no_region_marker_anywhere(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        assert docmerge.begin_marker(contract.NOTES_REGION) not in text
        assert docmerge.end_marker(contract.NOTES_REGION) not in text
        assert "fitdocs:begin" not in text
        assert "fitdocs:end" not in text

    def test_byte_identical_across_two_calls(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        resolution = Resolution(rows={}, mesocycles={})
        first = render_planned_page(block, row, resolution)
        second = render_planned_page(block, row, resolution)
        assert first == second


class TestBackLink:
    def test_link_target_and_text(self) -> None:
        block = _full_block()
        row = block.current.row("w1-fri")
        assert row is not None
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        target = layout_.block_rel_link(block.id)
        fragment = f"[{page.link_text(block.title)}]({target})"
        assert fragment in text

    def test_back_link_title_escapes_brackets(self) -> None:
        # A title with `[`/`]`: a production path that forgets to route the
        # title through `page.link_text` renders the raw brackets, not the
        # escaped `\\[...\\]` this test looks for.
        row = PlannedWorkout(
            id="w-bracket",
            date=date(2026, 1, 3),
            sport=Sport.RUN,
            modality=None,
            indoor=None,
            title="A row",
            summary="S",
            prescription="P",
        )
        state = PlanState(rows=(row,), targets=())
        block = build_block(
            id="bracket-block",
            title="Block [Phase 1]",
            starts=date(2026, 1, 1),
            ends=date(2026, 1, 14),
            goal="Goal.",
            mesocycle_days=7,
            original=state,
            current=state,
            amendments=(),
            overrides=(),
        )
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        assert "Block \\[Phase 1\\]" in text
        assert "[Block [Phase 1]](" not in text


# ===========================================================================
# The prescription is rendered verbatim, never through page.cell() -- a `|`
# would otherwise be escaped. The full fixture's prescriptions carry none,
# so this builds its own row (task instruction: an inline Block rather than
# editing the shared fixture).
# ===========================================================================


class TestPrescriptionVerbatim:
    def test_prescription_pipe_is_not_escaped(self) -> None:
        row = PlannedWorkout(
            id="w-pipe",
            date=date(2026, 1, 3),
            sport=Sport.RUN,
            modality=None,
            indoor=None,
            title="Intervals",
            summary="Track work",
            prescription="6 x 800m at 5k pace | 400m jog recovery.",
        )
        block = _simple_block(row)
        text = render_planned_page(block, row, Resolution(rows={}, mesocycles={}))
        assert "6 x 800m at 5k pace | 400m jog recovery." in text
        assert "6 x 800m at 5k pace \\| 400m jog recovery." not in text
