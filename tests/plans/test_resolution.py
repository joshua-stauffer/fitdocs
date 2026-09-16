"""Tests for the resolution seam (training-blocks spec, task 3.1). See
"ResolutionSeam" in `.kiro/specs/training-blocks/design.md`
(Req 4.7, 5.4, 6.1).

Test File Ownership (tasks.md): this module is 3.1's alone.
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs.plans.resolution import (
    UNRESOLVED_ROW,
    MesocycleResolution,
    Resolution,
    RowResolution,
    unresolved,
)

# --- unresolved() and UNRESOLVED_ROW (Req 6.1) -------------------------------


def test_unresolved_returns_empty_mappings() -> None:
    """The engine's default: no row and no mesocycle has been reconciled,
    and no block-level lines are stated."""
    result = unresolved()
    assert result.rows == {}
    assert result.mesocycles == {}
    assert result.block_lines == ()


def test_unresolved_row_cell_is_the_word_unresolved() -> None:
    """Pinned by value, not merely by length: a row absent from a caller's
    `Resolution.rows` mapping must literally read "unresolved" in the
    block table."""
    assert UNRESOLVED_ROW.cell == "unresolved"


def test_unresolved_row_section_is_one_line() -> None:
    assert UNRESOLVED_ROW.section == ("Not yet reconciled against logged workouts.",)
    assert len(UNRESOLVED_ROW.section) == 1


# --- shape: frozen dataclasses over Mapping (Req 6.2, 6.3) ------------------


def test_row_resolution_is_frozen() -> None:
    row = RowResolution(cell="ok", section=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.cell = "changed"  # type: ignore[misc]


def test_mesocycle_resolution_defaults_to_no_extra_lines() -> None:
    """A caller naming a mesocycle without extra lines still constructs --
    `before_table`/`after_table` default to `()`, not a required argument."""
    meso = MesocycleResolution()
    assert meso.before_table == ()
    assert meso.after_table == ()


def test_resolution_block_lines_defaults_to_empty() -> None:
    """A caller supplying only rows and mesocycles still constructs --
    `block_lines` defaults to `()`, so an empty block-level section is the
    default rather than a required argument."""
    resolution = Resolution(rows={}, mesocycles={})
    assert resolution.block_lines == ()


def test_resolution_holds_caller_supplied_rows_and_mesocycles() -> None:
    """A caller-built `Resolution` carries exactly what it was given --
    distinct, pairwise-different values at each of the two mapping's two
    keys, so a swapped assignment would be visible."""
    row_a = RowResolution(cell="done", section=("A",))
    row_b = RowResolution(cell="skipped", section=("B",))
    meso_1 = MesocycleResolution(before_table=("first",))
    meso_2 = MesocycleResolution(after_table=("second",))
    resolution = Resolution(
        rows={"a": row_a, "b": row_b},
        mesocycles={1: meso_1, 2: meso_2},
        block_lines=("block note",),
    )
    assert resolution.rows["a"] is row_a
    assert resolution.rows["b"] is row_b
    assert resolution.mesocycles[1] is meso_1
    assert resolution.mesocycles[2] is meso_2
    assert resolution.block_lines == ("block note",)
