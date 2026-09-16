"""The planned-workout page renderer (training-blocks spec, task 3.3). See
"PlannedPage" (`src/fitdocs/plans/planned_page.py`) in
`.kiro/specs/training-blocks/design.md` (Req 3.6, 5.2, 5.3, 5.4, 5.7, 6.2,
6.3).

Pure: `render_planned_page(block, row, resolution) -> str` takes no clock,
no `Path`, does no I/O. Imports `fitdocs.plans.page` (the shared vocabulary,
frontmatter emitter and escaping helpers), `fitdocs.plans.model` and
`fitdocs.plans.resolution` (value types) and `fitdocs.layout` (the one
link helper this page needs) -- never `fitdocs.contract` or
`fitdocs.docmerge` directly: the banner comes through `page.banner()`, and
this page carries no region at all (there is nothing here for a later
reconciliation pass to merge back in, unlike the block page's notes
region), so `fitdocs.docmerge` is never imported.

The four frontmatter key spellings this module must not re-spell as string
literals -- `date`, `sport`, `modality`, `indoor` -- are taken positionally
from `page.PLANNED_FRONTMATTER_KEYS` (design item 6: those spellings are
confined to `page.py`).
"""

from __future__ import annotations

from fitdocs import layout
from fitdocs.plans import page
from fitdocs.plans.model import Block, PlannedWorkout
from fitdocs.plans.resolution import UNRESOLVED_ROW, Resolution

__all__ = ["render_planned_page"]


def render_planned_page(
    block: Block, row: PlannedWorkout, resolution: Resolution
) -> str:
    """Render one planned-workout page from `(block, row, resolution)` (Req
    3.6, 5.2, 5.3, 5.4, 5.7, 6.2, 6.3).

    Validates `resolution` first through `page.check_resolution` (raises
    `ValueError` naming the offender -- an unknown row id, an unknown
    mesocycle number, or a multi-line cell). Then rejects a `## Resolution`
    section line equal to the frontmatter fence (`page.is_fence_line`),
    which would otherwise let caller-supplied content terminate the
    frontmatter block early if it ever preceded it -- checked here even
    though this section always renders last, so the same structural rule
    holds regardless of section order.

    The mesocycle number is `block.mesocycle_of(row.date)` -- the window
    containing the row's *current* date, never its date as first written
    (`block.original`), so a row moved across a mesocycle boundary by an
    amendment renders under its new mesocycle.

    The prescription renders verbatim, never through `page.cell()`: `cell()`
    exists for single-line markdown table cells (and raises on a newline),
    while the prescription is prose that may span lines, so escaping its
    `|` characters would both misrepresent the source and, for a multi-line
    prescription, raise.
    """
    page.check_resolution(block, resolution)

    entry = resolution.rows.get(row.id, UNRESOLVED_ROW)
    for line in entry.section:
        if page.is_fence_line(line):
            raise ValueError(
                f"resolution section for row {row.id!r} contains a line "
                "equal to the frontmatter fence"
            )

    mesocycle = block.mesocycle_of(row.date)

    keys = page.PLANNED_FRONTMATTER_KEYS
    values: tuple[str | int | bool | None, ...] = (
        row.title,
        page.PLANNED_TYPE,
        page.GENERATOR,
        page.PLANNED_VERSION,
        block.id,
        row.id,
        mesocycle,
        row.date.isoformat(),
        row.sport.value,
        row.modality.value if row.modality is not None else None,
        True if row.indoor else None,
    )
    # `page.frontmatter` returns the block already terminated by a fence
    # line plus its own trailing newline (pinned by 3.1); stripping that
    # newline before joining below with the blank-line separator is what
    # keeps exactly one blank line between the fence and the banner -- the
    # same shape `history/page.py` (`frontmatter.rstrip("\n")`) and the
    # sibling block page use, rather than the two blank lines an unstripped
    # join would leave.
    front = page.frontmatter(list(zip(keys, values, strict=True))).rstrip("\n")

    link = layout.block_rel_link(block.id)
    back_link_text = page.link_text(block.title)
    heading = f"# {row.title}"
    planned_line = (
        f"Planned for {page.format_day(row.date)} -- {page.sport_phrase(row)} -- "
        f"mesocycle {mesocycle} of [{back_link_text}]({link})."
    )
    summary_line = f"_{row.summary}_"
    prescription_section = "## Prescription\n\n" + row.prescription
    resolution_section = "## Resolution\n\n" + "\n".join(entry.section)

    sections = [
        front,
        page.banner(),
        heading,
        planned_line,
        summary_line,
        prescription_section,
        resolution_section,
    ]
    return "\n\n".join(sections) + "\n"
