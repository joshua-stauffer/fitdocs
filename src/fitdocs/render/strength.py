"""Strength set grouping and sets-table rendering (Req 9.2, 9.3, 9.4, 9.6, 13.3).

This is the StrengthRenderer component: it turns the ordered, recorded
:class:`~fitdocs.model.StrengthSet` stream into per-exercise groups and renders
each as a ``set | reps | load | rest`` markdown table (reference §4). It is pure,
deterministic, and does no I/O; it reads only the immutable activity model.

Two rules carry the honesty contract (Req 13.3), both guarded with ``is None``
rather than truthiness so a recorded zero is never mistaken for missing data:

- An **unrecorded** field (``None``) renders blank -- the in-table absence marker
  :data:`~fitdocs.render.format.ABSENT` (Req 9.4).
- A **recorded zero** is genuine: a bodyweight set's ``weight_kg == 0.0`` renders
  ``"0 kg"``, never blank (Req 9.4, 13.3).

Grouping and attribution (Req 9.2, 9.3):

- A *displayable* set (any set whose ``set_type`` is not ``"rest"`` -- ``active``
  sets, and any other/unrecorded type) becomes one table row. Grouping never
  drops a recorded set.
- Consecutive displayable sets sharing the same resolved ``exercise_name`` form
  one :class:`ExerciseGroup`; when the name changes a new group starts. A
  non-consecutive same-name run (``A, B, A``) yields three groups -- runs are
  never merged back together. An unresolved name (``None``) groups under a
  ``name=None`` group rendered as ``"Unknown exercise"`` -- never guessed
  (Req 9.3). A ``"rest"`` set between two same-name sets does **not** break the
  group (rest, then another set of the same exercise, is one exercise).
- :attr:`SetRow.number` is **per-group** (``1, 2, 3`` within each exercise) --
  the natural reading of the reference's per-exercise table.
- A ``"rest"`` set is never its own row: its ``duration_s`` attributes to the
  ``rest`` column of the immediately preceding displayable set's row (Req 9.2).
  A rest with no preceding displayable set is dropped. When two rests follow one
  set, only the immediately following one attributes (the row's ``rest_s`` is
  filled once, then left alone).

When there is nothing to display -- no sets, or only rest sets -- the section is
omitted entirely (``""``), never an empty scaffold (Req 9.6).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fitdocs.model import StrengthSet
from fitdocs.render.format import cell, fmt_duration, fmt_int

_REST_SET_TYPE = "rest"
_UNKNOWN_LABEL = "Unknown exercise"
_COLUMNS = ("Set", "Reps", "Load", "Rest")


@dataclass(frozen=True)
class ExerciseGroup:
    """A run of consecutive displayable sets sharing one resolved exercise name.

    ``name`` is the resolved ``exercise_name`` verbatim, or ``None`` when it was
    never resolved -- rendered as ``"Unknown exercise"``, never guessed.
    """

    name: str | None
    rows: tuple[SetRow, ...]


@dataclass(frozen=True)
class SetRow:
    """One set's table row. ``number`` is 1-based within its exercise group.

    ``reps``/``weight_kg`` mirror the recorded set (a recorded ``0.0`` is a true
    zero); ``rest_s`` is the duration of the rest set that immediately followed
    this set, or ``None`` when none did.
    """

    number: int
    reps: int | None
    weight_kg: float | None
    rest_s: float | None


class _RowBuilder:
    """Mutable accumulator for one row, frozen into a :class:`SetRow` at the end.

    ``rest_s`` is filled by the immediately following rest set; ``_rest_set``
    guards against a second consecutive rest overwriting it.
    """

    __slots__ = ("number", "reps", "weight_kg", "rest_s", "_rest_set")

    def __init__(self, number: int, reps: int | None, weight_kg: float | None) -> None:
        self.number = number
        self.reps = reps
        self.weight_kg = weight_kg
        self.rest_s: float | None = None
        self._rest_set = False

    def attribute_rest(self, duration_s: float | None) -> None:
        """Attribute the immediately following rest set's duration once."""
        if not self._rest_set:
            self.rest_s = duration_s
            self._rest_set = True

    def freeze(self) -> SetRow:
        return SetRow(
            number=self.number,
            reps=self.reps,
            weight_kg=self.weight_kg,
            rest_s=self.rest_s,
        )


def group_sets(sets: tuple[StrengthSet, ...]) -> tuple[ExerciseGroup, ...]:
    """Group the recorded set stream into per-exercise :class:`ExerciseGroup`s.

    Walks ``sets`` in recorded order. Consecutive displayable sets sharing a
    resolved ``exercise_name`` form one group (Req 9.2); an unresolved name forms
    a ``name=None`` group (Req 9.3). A ``"rest"`` set is not a row -- its duration
    attributes to the preceding displayable row (Req 9.2). Returns ``()`` when no
    displayable set exists (Req 9.6).
    """
    groups: list[tuple[str | None, list[_RowBuilder]]] = []
    current: tuple[str | None, list[_RowBuilder]] | None = None
    last_row: _RowBuilder | None = None

    for item in sets:
        if item.set_type == _REST_SET_TYPE:
            if last_row is not None:
                last_row.attribute_rest(item.duration_s)
            continue

        if current is None or current[0] != item.exercise_name:
            current = (item.exercise_name, [])
            groups.append(current)
        row = _RowBuilder(len(current[1]) + 1, item.repetitions, item.weight_kg)
        current[1].append(row)
        last_row = row

    return tuple(
        ExerciseGroup(name=name, rows=tuple(row.freeze() for row in rows))
        for name, rows in groups
    )


def sets_section(sets: tuple[StrengthSet, ...]) -> str:
    """Render the sets section body: one ``set | reps | load | rest`` table per
    exercise group.

    Returns ``""`` when there is nothing to display -- no sets, or only rest sets
    -- so the section is omitted entirely rather than scaffolded empty (Req 9.6).
    Unrecorded fields render blank; recorded zeros render as genuine values
    (Req 9.4, 13.3).
    """
    groups = group_sets(sets)
    if not groups:
        return ""
    return "\n\n".join(_group_block(group) for group in groups)


def _group_block(group: ExerciseGroup) -> str:
    """A bold exercise label followed by its ``set | reps | load | rest`` table."""
    label = _UNKNOWN_LABEL if group.name is None else group.name
    lines = [_row(_COLUMNS), _row(("---",) * len(_COLUMNS))]
    lines.extend(_set_row(row) for row in group.rows)
    return f"**{label}**\n\n" + "\n".join(lines)


def _set_row(row: SetRow) -> str:
    """One table row; blanks for unrecorded fields, genuine values for zeros."""
    return _row(
        (
            str(row.number),
            cell(None if row.reps is None else str(row.reps)),
            cell(fmt_int(row.weight_kg, "kg")),
            cell(fmt_duration(row.rest_s)),
        )
    )


def _row(cells: Sequence[str]) -> str:
    """One markdown table row from its cells."""
    return "| " + " | ".join(cells) + " |"
