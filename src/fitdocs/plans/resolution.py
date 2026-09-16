"""The resolution seam (training-blocks spec, task 3.1). See "ResolutionSeam"
(`src/fitdocs/plans/resolution.py`) in `.kiro/specs/training-blocks/design.md`
and "Cross-spec obligations (training-blocks ↔ plan-resolution)" item 1,
which this module reproduces verbatim (Req 4.7, 5.4, 6.1).

This is the value the two renderers take beside a `Block`: what a future
`plan-resolution` pass supplies once it can reconcile a planned workout
against a logged one, and the *unresolved* default every render uses until
then. It holds no rendering logic and no downstream vocabulary -- not even
the words a renderer prints for an unresolved row's status beyond the one
value below -- so that a later reconciliation feature changes nothing here
when it starts filling `Resolution` values in.

`Resolution.rows` and `.mesocycles` are `Mapping`, not `dict`: callers pass
plain dicts, and neither this module nor a renderer ever mutates one in
place. A row absent from `rows` renders as :data:`UNRESOLVED_ROW`; a
mesocycle absent from `mesocycles` renders no extra lines; an empty
`block_lines` renders no block-level section at all. `RowResolution.cell`
must contain no newline -- a renderer's structural check (`page.py`'s
`check_resolution`) enforces that, not this module. Every dataclass here is
frozen and therefore unhashable by identity of its mutable-typed fields;
none is ever used as a dict key.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__ = [
    "MesocycleResolution",
    "Resolution",
    "RowResolution",
    "UNRESOLVED_ROW",
    "unresolved",
]


@dataclass(frozen=True)
class RowResolution:
    """One planned workout's resolved status: the block table's single-line
    cell, and the markdown lines the planned page shows under its own
    "## Resolution" heading (Req 4.7, 5.4)."""

    cell: str
    """One line of inline markdown -- the block table's Resolution column."""

    section: tuple[str, ...]
    """Markdown lines under "## Resolution" on the planned page."""


@dataclass(frozen=True)
class MesocycleResolution:
    """Extra lines a mesocycle's block-page section carries around its
    target-load line and its day table, supplied only once something
    reconciles the mesocycle's rows (Req 6.1, 6.2)."""

    before_table: tuple[str, ...] = ()
    """Lines after the "Target load:" line, before the day table."""

    after_table: tuple[str, ...] = ()
    """Lines after the day table."""


@dataclass(frozen=True)
class Resolution:
    """The full resolution a caller supplies to either renderer alongside a
    `Block` (Req 6.1, 6.2, 6.3)."""

    rows: Mapping[str, RowResolution]
    """Keyed by planned-workout id."""

    mesocycles: Mapping[int, MesocycleResolution]
    """Keyed by mesocycle number."""

    block_lines: tuple[str, ...] = ()
    """"## Resolution" lines on the block page, after the mesocycles."""


UNRESOLVED_ROW: Final[RowResolution] = RowResolution(
    cell="unresolved",
    section=("Not yet reconciled against logged workouts.",),
)
"""The status every row renders with until something supplies a real
`RowResolution` for its id (Req 4.7, 5.4) -- this module's only stated
vocabulary."""


def unresolved() -> Resolution:
    """A fresh, fully unresolved `Resolution`: empty row and mesocycle
    mappings, no block-level lines (Req 6.1) -- the engine's default when no
    resolver is supplied."""
    return Resolution(rows={}, mesocycles={}, block_lines=())
