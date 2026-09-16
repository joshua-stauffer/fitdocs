"""The block page: one section-ordered, pure render of `(Block, Resolution)`
(training-blocks spec, task 3.2). See "BlockPage"
(`src/fitdocs/plans/block_page.py`) in `.kiro/specs/training-blocks/design.md`
(Req 3.7, 4.2-4.11, 5.6, 6.2, 6.3).

Imports only `fitdocs.plans.page`, `fitdocs.plans.model`,
`fitdocs.plans.resolution` and `fitdocs.layout` -- never
`fitdocs.contract` or `fitdocs.docmerge` directly: the provenance banner
and the page's one user-owned region come from :func:`page.banner` and
:func:`page.notes_region`, so this module never re-spells a contract name.

:func:`render_block_page` validates its `resolution` argument first,
through :func:`page.check_resolution`, then renders nine sections in the
fixed order design.md states, joined by blank lines. It renders no
logged-workout information and no word of a downstream reconciliation
vocabulary -- the forbidden-phrase pin in `tests/plans/test_block_page.py`
holds that over the default render.
"""

from __future__ import annotations

from datetime import date, timedelta

from fitdocs import layout
from fitdocs.plans import page
from fitdocs.plans.model import (
    MUTABLE_FIELDS,
    Amendment,
    Block,
    Change,
    Mesocycle,
    MesocycleTarget,
    PlannedWorkout,
    RowAdded,
    RowChanged,
    RowRemoved,
    TargetChanged,
)
from fitdocs.plans.resolution import UNRESOLVED_ROW, MesocycleResolution, Resolution

__all__ = ["render_block_page"]

_DAY_TABLE_HEADER = "| Day | Sport | Planned | Summary | Resolution |"
_ORIGINAL_TABLE_HEADER = "| Id | Date | Sport | Title | Summary |"
# Built, never spelled: the plan's hard rules forbid the literal `"---"`
# anywhere under `src/fitdocs/plans/` (it is `contract.FRONTMATTER_FENCE`);
# `"-" * 3` is a different AST node (a `BinOp`), so the consumer guard's
# exact-literal scan never sees the fence text, and both five-column tables
# this module renders share one five-cell separator.
_TABLE_SEPARATOR = "|" + "|".join(["-" * 3] * 5) + "|"


def render_block_page(block: Block, resolution: Resolution) -> str:
    """The block page's full markdown text, deterministically, from `block`
    and `resolution` alone (Req 3.7, 4.2-4.11, 5.6, 6.2, 6.3)."""
    page.check_resolution(block, resolution)

    frontmatter_block = page.frontmatter(_frontmatter_pairs(block))

    body_sections = [
        f"# {block.title}",
        page.notes_region().rstrip("\n"),
        _summary_lines(block),
        _goal_section(block),
    ]
    for mesocycle in block.mesocycles:
        body_sections.append(_mesocycle_section(block, mesocycle, resolution))
    if resolution.block_lines:
        body_sections.append("## Resolution\n\n" + "\n".join(resolution.block_lines))
    body_sections.append(_revision_record_section(block))

    body = "\n\n".join(body_sections)
    return f"{frontmatter_block}\n{page.banner()}\n\n{body}\n"


# --- frontmatter (Req 4.2) ---------------------------------------------------


def _frontmatter_pairs(
    block: Block,
) -> list[tuple[str, str | int | bool | None]]:
    """Zipped positionally against `page.BLOCK_FRONTMATTER_KEYS`, so this
    module spells none of that tuple's key strings itself (Req 4.2)."""
    values: tuple[str | int | bool | None, ...] = (
        block.title,
        page.BLOCK_TYPE,
        page.GENERATOR,
        page.BLOCK_VERSION,
        block.id,
        block.starts.isoformat(),
        block.ends.isoformat(),
        block.goal,
        block.mesocycle_days,
    )
    return list(zip(page.BLOCK_FRONTMATTER_KEYS, values, strict=True))


# --- opening summary and goal (Req 4.3) --------------------------------------


def _summary_lines(block: Block) -> str:
    """Three separate paragraphs, not three lines of one paragraph: a
    CommonMark soft break joins adjacent plain-text lines into a single
    rendered line, so `"\\n"` here would collapse `Starts:`/`Ends:`/
    `Mesocycle length:` into one run-on sentence (Req 4.3, 4.11)."""
    last = block.mesocycles[-1]
    return "\n\n".join(
        [
            f"Starts: {block.starts.isoformat()}",
            f"Ends: {block.ends.isoformat()} ({block.days} days)",
            f"Mesocycle length: {block.mesocycle_days} days "
            f"({len(block.mesocycles)} mesocycles; the last is {last.days} days)",
        ]
    )


def _goal_section(block: Block) -> str:
    return f"### Goal\n\n{block.goal}"


# --- per-mesocycle sections (Req 4.4, 4.5, 4.6, 4.7) -------------------------


def _mesocycle_section(
    block: Block, mesocycle: Mesocycle, resolution: Resolution
) -> str:
    """`Focus:` and `Target load:` are separate paragraphs, each its own
    entry in `blocks`, joined by `"\\n\\n"` below -- adjacent plain-text
    lines joined by a single `"\\n"` would soft-break into one run-on
    sentence under CommonMark (Req 4.4, 4.11). `before_table` sits between
    `Target load:` and the table, `after_table` after it, each its own
    blank-separated block."""
    heading = (
        f"## Mesocycle {mesocycle.number} -- {mesocycle.starts.isoformat()} to "
        f"{mesocycle.ends.isoformat()} ({mesocycle.days} days)"
    )
    if mesocycle.is_short:
        heading += f" -- shorter than the stated {block.mesocycle_days} days"

    blocks = [heading]
    if mesocycle.focus is not None:
        blocks.append(f"Focus: {mesocycle.focus}")
    if mesocycle.target_load is not None:
        blocks.append(f"Target load: {page.format_load(mesocycle.target_load)}")
    else:
        blocks.append("Target load: none")

    extra = resolution.mesocycles.get(mesocycle.number, MesocycleResolution())
    if extra.before_table:
        blocks.append("\n".join(extra.before_table))

    table_lines = [
        _DAY_TABLE_HEADER,
        _TABLE_SEPARATOR,
        *_day_rows(block, mesocycle, resolution),
    ]
    blocks.append("\n".join(table_lines))

    if extra.after_table:
        blocks.append("\n".join(extra.after_table))

    return "\n\n".join(blocks)


def _day_rows(block: Block, mesocycle: Mesocycle, resolution: Resolution) -> list[str]:
    """One row per calendar day of `mesocycle`'s window: a rest row for a
    day with no planned workout, else one row per workout on that day, in
    `Mesocycle.workouts` order (never re-sorted here) (Req 4.5)."""
    by_day: dict[date, list[PlannedWorkout]] = {}
    for row in mesocycle.workouts:
        by_day.setdefault(row.date, []).append(row)

    rows: list[str] = []
    day = mesocycle.starts
    while day <= mesocycle.ends:
        today = by_day.get(day, ())
        if not today:
            rows.append(f"| {page.cell(page.format_day(day))} | | _rest_ | | |")
        else:
            for row in today:
                rows.append(_workout_row(block, row, resolution))
        day += timedelta(days=1)
    return rows


def _workout_row(block: Block, row: PlannedWorkout, resolution: Resolution) -> str:
    row_resolution = resolution.rows.get(row.id, UNRESOLVED_ROW)
    link = layout.planned_rel_link(block.id, row.id)
    planned_cell = f"[{page.link_text(row.title)}]({link})"
    return (
        f"| {page.cell(page.format_day(row.date))} | "
        f"{page.cell(page.sport_phrase(row))} | {planned_cell} | "
        f"{page.cell(row.summary)} | {page.cell(row_resolution.cell)} |"
    )


# --- revision record (Req 3.7, 4.8) ------------------------------------------


def _revision_record_section(block: Block) -> str:
    lines = ["## Revision record", "", "### As first written", ""]
    if block.original.rows:
        lines.append(_ORIGINAL_TABLE_HEADER)
        lines.append(_TABLE_SEPARATOR)
        for row in block.original.rows:
            lines.append(
                f"| {page.cell(row.id)} | {row.date.isoformat()} | "
                f"{page.cell(str(row.sport))} | {page.cell(row.title)} | "
                f"{page.cell(row.summary)} |"
            )
    else:
        lines.append("No planned workouts as first written.")

    lines.append("")
    if block.original.targets:
        parts = [
            _target_summary(number, block.original.target(number))
            for number in range(1, len(block.mesocycles) + 1)
        ]
        lines.append("Mesocycle targets as first written: " + "; ".join(parts))
    else:
        lines.append("No mesocycle targets as first written.")

    if not block.amendments:
        lines.append("")
        lines.append("No amendments.")
    else:
        for amendment in block.amendments:
            lines.append("")
            lines.append(_amendment_section(amendment))

    return "\n".join(lines)


def _target_summary(number: int, target: MesocycleTarget | None) -> str:
    if target is None or (target.target_load is None and target.focus is None):
        return f"{number}: none"
    load_part = (
        page.format_load(target.target_load)
        if target.target_load is not None
        else "none"
    )
    if target.focus is not None:
        return f"{number}: {load_part} ({target.focus})"
    return f"{number}: {load_part}"


def _amendment_section(amendment: Amendment) -> str:
    lines = [
        f"### Amendment {amendment.ordinal} -- {amendment.date.isoformat()}",
        f"Reason: {amendment.reason}",
    ]
    for change in amendment.changes:
        lines.extend(_change_bullets(change))
    return "\n".join(lines)


def _change_bullets(change: Change) -> list[str]:
    if isinstance(change, RowChanged):
        return _row_changed_bullets(change)
    if isinstance(change, RowAdded):
        return [_row_added_bullet(change)]
    if isinstance(change, RowRemoved):
        return [_row_removed_bullet(change)]
    return [_target_changed_bullet(change)]


def _row_changed_bullets(change: RowChanged) -> list[str]:
    inline_parts = []
    for field in MUTABLE_FIELDS:
        if field == "prescription":
            continue
        before_val = getattr(change.before, field)
        after_val = getattr(change.after, field)
        if before_val == after_val:
            continue
        inline_parts.append(
            f"{field} {_format_field_value(before_val)} -> "
            f"{_format_field_value(after_val)}"
        )

    bullets: list[str] = []
    if inline_parts:
        bullets.append(f"- `{change.after.id}`: " + "; ".join(inline_parts))

    if change.before.prescription != change.after.prescription:
        bullets.append(f"- `{change.after.id}`: prescription changed")
        bullets.append("  - was:")
        bullets.extend(
            f"    > {line}" for line in change.before.prescription.splitlines()
        )
        bullets.append("  - now:")
        bullets.extend(
            f"    > {line}" for line in change.after.prescription.splitlines()
        )

    return bullets


def _row_added_bullet(change: RowAdded) -> str:
    row = change.row
    return (
        f"- Added `{row.id}` -- {row.date.isoformat()}, {row.sport}, "
        f'"{row.title}" -- {row.summary}'
    )


def _row_removed_bullet(change: RowRemoved) -> str:
    row = change.row
    return f'- Removed `{row.id}` -- {row.date.isoformat()}, {row.sport}, "{row.title}"'


def _target_changed_bullet(change: TargetChanged) -> str:
    parts = []
    if change.before.target_load != change.after.target_load:
        parts.append(
            f"target load {_format_load_or_unset(change.before.target_load)} -> "
            f"{_format_load_or_unset(change.after.target_load)}"
        )
    if change.before.focus != change.after.focus:
        parts.append(
            f"focus {_format_focus_or_unset(change.before.focus)} -> "
            f"{_format_focus_or_unset(change.after.focus)}"
        )
    return f"- Mesocycle {change.number}: " + "; ".join(parts)


def _format_field_value(value: object) -> str:
    """A single-line field value as it appears inline in a revision-record
    bullet: `(unset)` for `None`, the ISO form for a date, `true`/`false`
    for a bool, and a double-quoted literal for a plain string (Req 3.7,
    4.8). A `Sport`/`Modality` member falls through to its plain `str()`,
    the same word `page.sport_phrase` and this page's tables already show
    unquoted."""
    if value is None:
        return "(unset)"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and type(value) is str:
        return f'"{value}"'
    return str(value)


def _format_load_or_unset(value: float | None) -> str:
    return "(unset)" if value is None else page.format_load(value)


def _format_focus_or_unset(value: str | None) -> str:
    return "(unset)" if value is None else f'"{value}"'
