"""Both training-block document types' vocabulary, the frontmatter emitter,
and the escaping helpers the two renderers share (training-blocks spec,
task 3.1). See "PageVocabulary" (`src/fitdocs/plans/page.py`) in
`.kiro/specs/training-blocks/design.md` (Req 4.2, 4.7, 4.11, 5.2, 5.4, 6.1).

This module and `plans/engine.py` are the package's **only** importers of
`fitdocs.contract`: the two renderers (`plans/block_page.py`,
`plans/planned_page.py`) reach the provenance banner through
:func:`banner` and the notes region through :func:`notes_region`, so
neither renderer binds a single contract name itself. Shared vocabulary --
the frontmatter fence, the ``type``/``generator`` keys, the generator name,
the banner, the notes region id and its placeholder -- is imported from
`fitdocs.contract` here and never re-spelled.

**Frontmatter is plain ordered lines, never a YAML library.** :func:`yaml_string`
is the one string-quoting rule the emitter uses; **every string value is
quoted, always** -- there is no bare-token path (the bare-token defect
class recorded in queue item
``2026-09-12-history-methodology-id-bare-token-yaml-typed`` cannot recur
here, because this module never introduces the shortcut that let it in).
Integers are written bare, booleans as ``true``/``false``, and a ``None``
value omits its key entirely rather than writing a placeholder a later
reader could mistake for a real one.

Three helpers below (:func:`check_resolution`, :func:`is_fence_line`,
:func:`sport_phrase`) exist so that the two parallel renderer tasks add
nothing to this module and duplicate nothing between themselves.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Final

from fitdocs.contract import (
    DOC_BANNER,
    FRONTMATTER_FENCE,
    GENERATOR,
    GENERATOR_KEY,
    NOTES_PLACEHOLDER,
    NOTES_REGION,
    TYPE_KEY,
)
from fitdocs.docmerge import region_block
from fitdocs.plans.model import Block, PlannedWorkout
from fitdocs.plans.resolution import Resolution

__all__ = [
    "BLOCK_FRONTMATTER_KEYS",
    "BLOCK_TYPE",
    "BLOCK_VERSION",
    "BLOCK_VERSION_KEY",
    "GENERATOR",
    "INDOOR_WORD",
    "PLANNED_FRONTMATTER_KEYS",
    "PLANNED_TYPE",
    "PLANNED_VERSION",
    "PLANNED_VERSION_KEY",
    "WEEKDAYS",
    "banner",
    "cell",
    "check_resolution",
    "format_day",
    "format_load",
    "frontmatter",
    "is_fence_line",
    "link_text",
    "notes_region",
    "sport_phrase",
    "yaml_string",
]

# --- document vocabulary (Req 4.2, 5.2) --------------------------------------

BLOCK_TYPE: Final[str] = "training-block"
"""The frontmatter ``type`` value identifying a rendered training-block page.

Distinct from :data:`PLANNED_TYPE`, from :data:`fitdocs.contract.WORKOUT_TYPE`
and from the training-history document's own type -- a test pins all three
inequalities directly, the same discipline `history/page.py` established for
its one document type."""

BLOCK_VERSION: Final[int] = 1
"""The block-page document format's own version number, independent of
:data:`fitdocs.contract.DOC_VERSION` (which versions the workout-document
format) and of the training-history document's own version."""

BLOCK_VERSION_KEY: Final[str] = "block_version"
"""The frontmatter key carrying :data:`BLOCK_VERSION`."""

BLOCK_FRONTMATTER_KEYS: Final[tuple[str, ...]] = (
    "title",
    TYPE_KEY,
    GENERATOR_KEY,
    BLOCK_VERSION_KEY,
    "block",
    "starts",
    "ends",
    "goal",
    "mesocycle_days",
)
"""Every frontmatter key a rendered block page emits, in emission order
(Req 4.2)."""

PLANNED_TYPE: Final[str] = "planned-workout"
"""The frontmatter ``type`` value identifying a rendered planned-workout
page. Distinct from :data:`BLOCK_TYPE`, from
:data:`fitdocs.contract.WORKOUT_TYPE` and from the training-history
document's own type."""

PLANNED_VERSION: Final[int] = 1
"""The planned-workout document format's own version number, independent of
:data:`BLOCK_VERSION` and of :data:`fitdocs.contract.DOC_VERSION`."""

PLANNED_VERSION_KEY: Final[str] = "planned_version"
"""The frontmatter key carrying :data:`PLANNED_VERSION`."""

PLANNED_FRONTMATTER_KEYS: Final[tuple[str, ...]] = (
    "title",
    TYPE_KEY,
    GENERATOR_KEY,
    PLANNED_VERSION_KEY,
    "block",
    "planned_id",
    "mesocycle",
    "date",
    "sport",
    "modality",
    "indoor",
)
"""Every frontmatter key a rendered planned-workout page may emit, in
emission order (Req 5.2). ``modality`` is written only when the row states
one; the flag key here is written only when it is stated ``True`` -- a
stated ``False`` and an unstated flag both omit the key, since neither is
distinguishable to a reader and either is honest absence. Each of these four
key spellings (the date, the sport, the movement modality, and the flag
naming whether the session happens under a roof) appears exactly once **as
a string literal in this tuple**; the flag's spelling appears once more,
as :data:`INDOOR_WORD`, so a future rebinding onto a published contract
constant touches exactly two literals per key, or one for the other three."""

WEEKDAYS: Final[tuple[str, ...]] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
"""Indexed by :meth:`datetime.date.weekday`. Deliberately a fixed tuple
rather than ``date.strftime("%a")``: `strftime`'s weekday abbreviation is
locale-dependent, and this package reads no locale, so the block page's
rendered day-of-week text is identical on every machine regardless of the
process locale (Req 4.11)."""

INDOOR_WORD: Final[str] = "indoor"
"""The word :func:`sport_phrase` appends when a row's flag is stated `True`
-- deliberately the same spelling as the last entry of
:data:`PLANNED_FRONTMATTER_KEYS`, and this module's only other *string
literal* spelling of that word (a field access such as ``row.indoor``,
naming the model's own attribute, is not a re-spelling of this vocabulary
and is not counted here)."""

# --- the frontmatter emitter (Req 4.2, 5.2) ----------------------------------


def yaml_string(value: str, *, field: str) -> str:
    """Quote ``value`` for the frontmatter block, escaping ``\\``, ``"``,
    newline and tab, and rejecting any other character that is neither
    printable nor one of those two (Req 4.11).

    Every string value this module's :func:`frontmatter` emits is quoted
    through this function -- there is no bare-token path. Raises
    ``ValueError`` naming ``field`` for a character (a carriage return,
    among others) that would otherwise either break the block's YAML syntax
    or embed something unreadable in it.
    """
    for character in value:
        if character.isprintable() or character in ("\n", "\t"):
            continue
        raise ValueError(
            f"{field} contains a character that is neither printable, "
            f"newline nor tab: {character!r}"
        )
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def frontmatter(pairs: Sequence[tuple[str, str | int | bool | None]]) -> str:
    """Render a frontmatter block as ordered plain-text lines, fenced by
    :data:`fitdocs.contract.FRONTMATTER_FENCE` (Req 4.2, 5.2).

    Every string value is quoted through :func:`yaml_string`, always;
    integers are written bare; booleans as ``true``/``false``; a ``None``
    value omits its key from the block entirely. Returns the block including
    both fence lines and a trailing newline; the result parses through
    :func:`fitdocs.contract.parse_frontmatter` directly, in the given key
    order.
    """
    lines: list[str] = [FRONTMATTER_FENCE]
    for key, value in pairs:
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {yaml_string(value, field=key)}")
    lines.append(FRONTMATTER_FENCE)
    return "\n".join(lines) + "\n"


def banner() -> str:
    """The one-line provenance banner every generated document carries
    (Req 4.2, 5.2) -- the only way either renderer reaches
    :data:`fitdocs.contract.DOC_BANNER`."""
    return DOC_BANNER


def notes_region() -> str:
    """The block page's ``notes`` region, freshly composed with its
    instructive placeholder (Req 4.2) -- the only way the block renderer
    reaches :data:`fitdocs.contract.NOTES_REGION` and
    :data:`fitdocs.contract.NOTES_PLACEHOLDER`. The engine replaces the
    placeholder with an existing page's region body via ``merge_regions``;
    this function only ever produces the fresh form."""
    return region_block(NOTES_REGION, NOTES_PLACEHOLDER)


# --- shared structural and escaping helpers (Req 4.7, 4.11, 5.4) ------------


def check_resolution(block: Block, resolution: Resolution) -> None:
    """Validate ``resolution`` against ``block`` before either renderer uses
    it (Req 4.7, 5.4, 6.2, 6.3): every key of ``resolution.rows`` must be a
    current row id of ``block``, every key of ``resolution.mesocycles`` must
    lie in ``1..len(block.mesocycles)``, and every row's ``cell`` must be a
    single line. Raises ``ValueError`` naming the offender; renders nothing
    and returns ``None`` when every check passes.
    """
    current_row_ids = {row.id for row in block.current.rows}
    for row_id, row_resolution in resolution.rows.items():
        if row_id not in current_row_ids:
            raise ValueError(
                f"resolution names row id {row_id!r}, which is not a "
                "current row of this block"
            )
        if "\n" in row_resolution.cell:
            raise ValueError(f"resolution row {row_id!r}'s cell must be a single line")
    mesocycle_count = len(block.mesocycles)
    for number in resolution.mesocycles:
        if not (1 <= number <= mesocycle_count):
            raise ValueError(
                f"resolution names mesocycle {number}, which is outside "
                f"1..{mesocycle_count}"
            )


def is_fence_line(line: str) -> bool:
    """Whether ``line`` is exactly the frontmatter fence (Req 5.4) -- an
    equality test, never a prefix match, so a fence line carrying trailing
    text is not mistaken for the fence itself. Lets a planned page's
    resolution section refuse a fence in caller-supplied content without
    importing a contract name.
    """
    return line == FRONTMATTER_FENCE


def sport_phrase(row: PlannedWorkout) -> str:
    """The sport value alone, or followed by a parenthesised, comma-joined
    list of the stated movement modality and :data:`INDOOR_WORD`'s word when
    the row's flag is stated `True` (Req 4.11) -- four shapes, pinned by the
    test module rather than restated here. A stated `False` and an unstated
    flag both add nothing.
    """
    extras: list[str] = []
    if row.modality is not None:
        extras.append(str(row.modality))
    if row.indoor:
        extras.append(INDOOR_WORD)
    if not extras:
        return str(row.sport)
    return f"{row.sport} ({', '.join(extras)})"


def cell(text: str) -> str:
    """Escape ``|`` as ``\\|`` for a markdown table cell (Req 4.11). Raises
    ``ValueError`` on a newline -- the parser already forbids one in any
    field this reaches, so reaching here with one is a programming error."""
    if "\n" in text:
        raise ValueError("cell text must not contain a newline")
    return text.replace("|", "\\|")


def link_text(text: str) -> str:
    """:func:`cell`'s escaping, plus ``[`` and ``]`` escaped for use inside a
    markdown link's text (Req 4.11)."""
    escaped = cell(text)
    return escaped.replace("[", "\\[").replace("]", "\\]")


def format_day(day: date) -> str:
    """``"Tue 2026-09-22"`` -- :data:`WEEKDAYS` beside the ISO date
    (Req 4.11)."""
    return f"{WEEKDAYS[day.weekday()]} {day.isoformat()}"


def format_load(value: float) -> str:
    """An integral load as integer text (``1200.0`` -> ``"1200"``), else one
    decimal place (``1234.56`` -> ``"1234.6"``) (Req 4.11)."""
    if value == int(value):
        return str(int(value))
    return f"{value:.1f}"
