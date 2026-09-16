"""The plan model's pure core (training-blocks spec). See "PlanModel"
(`src/fitdocs/plans/model.py`) in `.kiro/specs/training-blocks/design.md`.

This module is pure: no `Path`, no clock, no I/O, no TOML. It imports only
`Sport` and `Modality` from `fitdocs.model` and `DECLARATION_FILENAME` from
`fitdocs.declaration` (for the reserved block id), and nothing else from the
`fitdocs.plans` package.

**Task 2.1** (this task) declares the value types, the identifier pattern
and the reserved block-id set, mesocycle-window derivation and the lookup of
a mesocycle number for a date, and the row and target checks.

**Task 2.2** extends this module in place, strictly sequentially, with the
amendment operations and their records, the revision trail (`Amendment`,
`Change` and its four record kinds), `Override`, `Block`, `apply_amendments`,
`check_overrides` and `build_block` -- it adds names and changes nothing this
task wrote.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Final

from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.model import Modality, Sport

IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"[a-z0-9][a-z0-9-]*")
"""Lowercase letters, digits and hyphens, beginning with a letter or digit
(Req 2.6). Matched with `fullmatch`, never `match` -- a bare `match` would
also accept a candidate with disallowed trailing characters, since this
pattern carries no `$` anchor of its own."""

RESERVED_BLOCK_IDS: Final[frozenset[str]] = frozenset(
    {DECLARATION_FILENAME.rsplit(".", 1)[0].lower()}
)
"""Derived at import from `DECLARATION_FILENAME`'s stem -- never a second
spelling of that name -- and compared case-insensitively against a
candidate block id by :func:`is_reserved_block_id` (macOS: a block id
differing from that stem only in case still collides on disk) (Req 2.6)."""


def is_reserved_block_id(candidate: str) -> bool:
    """Whether `candidate` collides with the reserved block id, compared
    case-insensitively (Req 2.6)."""
    return candidate.lower() in RESERVED_BLOCK_IDS


@dataclass(frozen=True)
class PlannedWorkout:
    """One planned session (Req 1.5, 1.6, 1.7)."""

    id: str
    date: date
    sport: Sport
    modality: Modality | None  # stated only when sport is Sport.WORKOUT
    indoor: bool | None  # None = not stated
    title: str  # single line
    summary: str  # single line
    prescription: str  # may span lines


@dataclass(frozen=True)
class MesocycleTarget:
    """A per-mesocycle target load and/or focus, as the source states it
    (Req 1.4)."""

    number: int
    target_load: float | None  # > 0 and finite when present
    focus: str | None


@dataclass(frozen=True)
class PlanState:
    """The rows and targets of a plan at one point in its history (as
    originally written, or after some prefix of amendments)."""

    rows: tuple[PlannedWorkout, ...]  # insertion order; ids unique
    targets: tuple[MesocycleTarget, ...]  # ascending number; numbers unique

    def row(self, row_id: str) -> PlannedWorkout | None:
        for candidate in self.rows:
            if candidate.id == row_id:
                return candidate
        return None

    def target(self, number: int) -> MesocycleTarget | None:
        for candidate in self.targets:
            if candidate.number == number:
                return candidate
        return None


@dataclass(frozen=True)
class Mesocycle:
    """A derived mesocycle: its window, its nominal and actual length, its
    target, and the rows placed in it (Req 3.1, 3.2)."""

    number: int
    starts: date
    ends: date
    nominal_days: int
    target_load: float | None
    focus: str | None
    workouts: tuple[PlannedWorkout, ...]  # date-ordered; source order within a day

    @property
    def days(self) -> int:
        """The window's actual, inclusive length in days."""
        return (self.ends - self.starts).days + 1

    @property
    def is_short(self) -> bool:
        """Whether this window is shorter than the block's stated mesocycle
        length -- true only for the last mesocycle of a block whose total
        length is not an exact multiple of that length."""
        return self.days < self.nominal_days


@dataclass(frozen=True)
class PlanProblem:
    """One independently reported validation problem (Req 2.1, 2.2)."""

    entry: str  # "workout[2] (id w1-thu)", "mesocycle[1]", "file", ...
    field: str | None
    message: str

    def describe(self) -> str:
        """`"workout[2] (id w1-thu) / date: 2026-12-20 is outside
        2026-09-21..2026-12-13"`; without a field, `"<entry>: <message>"`."""
        if self.field is None:
            return f"{self.entry}: {self.message}"
        return f"{self.entry} / {self.field}: {self.message}"


def mesocycle_windows(
    starts: date, ends: date, length: int
) -> tuple[tuple[int, date, date], ...]:
    """Derive the block's mesocycles from its bounds and its stated
    mesocycle length alone: consecutive, numbered from one, each `length`
    days except the last, which ends on `ends` and may be shorter (Req 3.1).

    Preconditions: `starts <= ends`; `length >= 1`.
    """
    total_days = (ends - starts).days + 1
    count = -(-total_days // length)  # ceiling division, exact (no float)
    windows = []
    for number in range(1, count + 1):
        first = starts + timedelta(days=(number - 1) * length)
        last = min(first + timedelta(days=length - 1), ends)
        windows.append((number, first, last))
    return tuple(windows)


def mesocycle_number(starts: date, length: int, day: date) -> int:
    """The 1-based number of the mesocycle window containing `day`, derived
    by arithmetic alone, never a search: the block's windows all share
    `starts` and `length` except the last (which is only ever shorter, never
    longer), so this formula lands in the right window regardless of where
    the last, possibly-short window falls.

    `Block.mesocycle_of` (task 2.2) delegates to this function over
    `(self.starts, self.mesocycle_days, day)`.

    Precondition: `day` is within the block's bounds (checked separately by
    :func:`check_rows`).
    """
    return (day - starts).days // length + 1


def check_rows(
    rows: Sequence[PlannedWorkout], *, starts: date, ends: date, entry: str
) -> tuple[PlanProblem, ...]:
    """Report, for every row whose date falls outside `[starts, ends]`, one
    problem naming that row by its position and id (Req 2.4)."""
    problems = []
    for position, row in enumerate(rows, start=1):
        if not (starts <= row.date <= ends):
            problems.append(
                PlanProblem(
                    entry=f"{entry}[{position}] (id {row.id})",
                    field="date",
                    message=f"{row.date} is outside {starts}..{ends}",
                )
            )
    return tuple(problems)


def check_targets(
    targets: Sequence[MesocycleTarget], *, count: int
) -> tuple[PlanProblem, ...]:
    """Report, for every target naming a mesocycle number outside
    `1..count` or naming one already seen, one problem naming that number
    (Req 2.8)."""
    problems = []
    seen: set[int] = set()
    for target in targets:
        if not (1 <= target.number <= count):
            problems.append(
                PlanProblem(
                    entry=f"mesocycle[{target.number}]",
                    field="number",
                    message=f"{target.number} is outside 1..{count}",
                )
            )
        if target.number in seen:
            problems.append(
                PlanProblem(
                    entry=f"mesocycle[{target.number}]",
                    field="number",
                    message=f"{target.number} is named more than once",
                )
            )
        seen.add(target.number)
    return tuple(problems)


# ============================================================================
# Task 2.2 -- amendments, the revision trail, overrides, Block, build_block.
# Appends only; nothing above this line is 2.2's to edit.
# ============================================================================

MUTABLE_FIELDS: Final[tuple[str, ...]] = (
    "date",
    "sport",
    "modality",
    "indoor",
    "title",
    "summary",
    "prescription",
)
"""The `PlannedWorkout` fields an `UpdateOp` may name -- every field except
`id`, which identifies the row rather than describing it (Req 3.4, 2.9)."""


@dataclass(frozen=True)
class UpdateOp:
    """Change named fields of an existing row, as the source states it
    (Req 3.4)."""

    row_id: str
    fields: Mapping[str, object]  # keys in MUTABLE_FIELDS; values already typed


@dataclass(frozen=True)
class AddOp:
    """Add a new row, as the source states it (Req 3.4)."""

    row: PlannedWorkout


@dataclass(frozen=True)
class RemoveOp:
    """Remove an existing row by id, as the source states it (Req 3.4)."""

    row_id: str


@dataclass(frozen=True)
class TargetOp:
    """Change a mesocycle's target load and/or focus, as the source states
    it (Req 3.4)."""

    number: int
    target_load: float | None
    focus: str | None


AmendmentOp = UpdateOp | AddOp | RemoveOp | TargetOp


@dataclass(frozen=True)
class AmendmentSpec:
    """One amendment as the source states it: a date, a reason and any
    number of operations (Req 3.3, 3.4)."""

    date: date
    reason: str
    ops: tuple[AmendmentOp, ...]


@dataclass(frozen=True)
class RowChanged:
    """The revision-trail record of a successful `UpdateOp` (Req 3.7)."""

    before: PlannedWorkout
    after: PlannedWorkout


@dataclass(frozen=True)
class RowAdded:
    """The revision-trail record of a successful `AddOp` (Req 3.7)."""

    row: PlannedWorkout


@dataclass(frozen=True)
class RowRemoved:
    """The revision-trail record of a successful `RemoveOp` (Req 3.7)."""

    row: PlannedWorkout


@dataclass(frozen=True)
class TargetChanged:
    """The revision-trail record of a successful `TargetOp`. `before` is
    the synthesised `MesocycleTarget(number, None, None)` when the
    mesocycle held no stated target beforehand (Req 3.4, 3.7)."""

    number: int
    before: MesocycleTarget
    after: MesocycleTarget


Change = RowChanged | RowAdded | RowRemoved | TargetChanged


@dataclass(frozen=True)
class Amendment:
    """One amendment after successful application: its 1-based file-order
    ordinal, its date, its reason, and every change it made (Req 3.3, 3.7)."""

    ordinal: int
    date: date
    reason: str
    changes: tuple[Change, ...]


@dataclass(frozen=True)
class Override:
    """One override entry as the source states it. `stems` is empty iff
    `skipped` is true; nothing about that relationship is judged by this
    module (Req 3.8)."""

    date: date
    row_id: str
    stems: tuple[str, ...]
    skipped: bool
    reason: str | None


@dataclass(frozen=True)
class Block:
    """The fully assembled, validated plan: its identity and bounds, the
    plan as first written and as it stands now, the revision trail, the
    override entries, and the derived mesocycles (Req 4.2, 6.4)."""

    id: str
    title: str
    starts: date
    ends: date
    goal: str
    mesocycle_days: int
    original: PlanState
    current: PlanState
    amendments: tuple[Amendment, ...]
    overrides: tuple[Override, ...]
    mesocycles: tuple[Mesocycle, ...]

    @property
    def days(self) -> int:
        """The block's actual, inclusive length in days."""
        return (self.ends - self.starts).days + 1

    def mesocycle_of(self, day: date) -> int:
        """The 1-based number of the mesocycle containing `day`. Delegates
        to :func:`mesocycle_number` over this block's own `starts` and
        `mesocycle_days` -- never a second derivation."""
        return mesocycle_number(self.starts, self.mesocycle_days, day)


def _row_bounds_problem(
    row: PlannedWorkout, *, entry: str, starts: date, ends: date
) -> PlanProblem | None:
    """The one rule set every row in the current plan must satisfy,
    whether it arrived by `UpdateOp` or `AddOp`: its date within
    `[starts, ends]`, and a modality stated only when its sport is
    `Sport.WORKOUT` (Req 2.4, 2.5, 2.9) -- the same rules an original row
    must satisfy (`check_rows`'s bounds half, inlined here because this
    check is per-op and needs its own `entry`/`field` naming). Both
    `_apply_update` and `_apply_add` call this single helper so the two
    paths' rule sets cannot drift apart."""
    if not (starts <= row.date <= ends):
        return PlanProblem(
            entry=entry,
            field="date",
            message=f"{row.date} is outside {starts}..{ends}",
        )
    if row.modality is not None and row.sport is not Sport.WORKOUT:
        return PlanProblem(
            entry=entry,
            field="modality",
            message="modality is only allowed when sport is Sport.WORKOUT",
        )
    return None


def _apply_update(
    op: UpdateOp,
    *,
    ordinal: int,
    op_index: int,
    rows: list[PlannedWorkout],
    starts: date,
    ends: date,
) -> tuple[Change | None, PlanProblem | None]:
    """Design clarification (this task, per requirements 2.9/3.4's
    "changes no field"): the rule is read as a *value* rule, not merely a
    non-empty-mapping rule -- `fields` naming a key whose stated value
    equals the row's current value is *also* "changes no field", not just
    an empty `fields`. Both are checked below and both report the same
    message; a `fields` mapping is valid only when at least one stated key
    differs from the row's current value."""
    entry = f"amendment[{ordinal}].update[{op_index}] (id {op.row_id})"
    position = next((i for i, row in enumerate(rows) if row.id == op.row_id), None)
    if position is None:
        return None, PlanProblem(
            entry=entry, field="row_id", message=f"no row with id {op.row_id} exists"
        )
    if not op.fields:
        return None, PlanProblem(
            entry=entry, field="fields", message="changes no field"
        )
    invalid_keys = sorted(key for key in op.fields if key not in MUTABLE_FIELDS)
    if invalid_keys:
        return None, PlanProblem(
            entry=entry,
            field="fields",
            message=f"{invalid_keys[0]} is not a mutable field",
        )
    before = rows[position]
    if all(getattr(before, key) == value for key, value in op.fields.items()):
        # Every stated key already holds this value -- a no-op update, and
        # "changes no field" applies even though `fields` is non-empty.
        return None, PlanProblem(
            entry=entry, field="fields", message="changes no field"
        )
    # op.fields is `Mapping[str, object]` (values already typed by the
    # source parser, task 2.3); mypy cannot statically match an untyped
    # mapping's values against PlannedWorkout's per-field types.
    after = replace(before, **op.fields)  # type: ignore[arg-type]
    bounds_problem = _row_bounds_problem(after, entry=entry, starts=starts, ends=ends)
    if bounds_problem is not None:
        return None, bounds_problem
    rows[position] = after
    return RowChanged(before=before, after=after), None


def _apply_add(
    op: AddOp,
    *,
    ordinal: int,
    op_index: int,
    rows: list[PlannedWorkout],
    used_ids: set[str],
    starts: date,
    ends: date,
) -> tuple[Change | None, PlanProblem | None]:
    entry = f"amendment[{ordinal}].add[{op_index}] (id {op.row.id})"
    if op.row.id in used_ids:
        return None, PlanProblem(
            entry=entry,
            field="id",
            message=f"{op.row.id} has already been used in this block's history",
        )
    bounds_problem = _row_bounds_problem(op.row, entry=entry, starts=starts, ends=ends)
    if bounds_problem is not None:
        return None, bounds_problem
    used_ids.add(op.row.id)
    rows.append(op.row)
    return RowAdded(row=op.row), None


def _apply_remove(
    op: RemoveOp,
    *,
    ordinal: int,
    op_index: int,
    rows: list[PlannedWorkout],
) -> tuple[Change | None, PlanProblem | None]:
    entry = f"amendment[{ordinal}].remove[{op_index}] (id {op.row_id})"
    position = next((i for i, row in enumerate(rows) if row.id == op.row_id), None)
    if position is None:
        return None, PlanProblem(
            entry=entry, field="row_id", message=f"no row with id {op.row_id} exists"
        )
    removed = rows.pop(position)
    return RowRemoved(row=removed), None


def _apply_target(
    op: TargetOp,
    *,
    ordinal: int,
    op_index: int,
    targets: list[MesocycleTarget],
    count: int,
) -> tuple[Change | None, PlanProblem | None]:
    entry = f"amendment[{ordinal}].target[{op_index}] (mesocycle {op.number})"
    if not (1 <= op.number <= count):
        return None, PlanProblem(
            entry=entry, field="number", message=f"{op.number} is outside 1..{count}"
        )
    if op.target_load is None and op.focus is None:
        return None, PlanProblem(
            entry=entry,
            field="target_load",
            message="neither target_load nor focus is stated",
        )
    position = next((i for i, t in enumerate(targets) if t.number == op.number), None)
    before = (
        targets[position]
        if position is not None
        else MesocycleTarget(op.number, None, None)
    )
    after = MesocycleTarget(
        number=op.number,
        target_load=op.target_load
        if op.target_load is not None
        else before.target_load,
        focus=op.focus if op.focus is not None else before.focus,
    )
    if position is not None:
        targets[position] = after
    else:
        insert_at = next(
            (i for i, t in enumerate(targets) if t.number > op.number), len(targets)
        )
        targets.insert(insert_at, after)
    return TargetChanged(number=op.number, before=before, after=after), None


def _apply_op(
    op: AmendmentOp,
    *,
    ordinal: int,
    op_index: int,
    rows: list[PlannedWorkout],
    targets: list[MesocycleTarget],
    used_ids: set[str],
    starts: date,
    ends: date,
    count: int,
) -> tuple[Change | None, PlanProblem | None]:
    if isinstance(op, UpdateOp):
        return _apply_update(
            op, ordinal=ordinal, op_index=op_index, rows=rows, starts=starts, ends=ends
        )
    if isinstance(op, AddOp):
        return _apply_add(
            op,
            ordinal=ordinal,
            op_index=op_index,
            rows=rows,
            used_ids=used_ids,
            starts=starts,
            ends=ends,
        )
    if isinstance(op, RemoveOp):
        return _apply_remove(op, ordinal=ordinal, op_index=op_index, rows=rows)
    return _apply_target(
        op, ordinal=ordinal, op_index=op_index, targets=targets, count=count
    )


def apply_amendments(
    original: PlanState,
    specs: Sequence[AmendmentSpec],
    *,
    starts: date,
    ends: date,
    count: int,
) -> tuple[tuple[PlanState, ...], tuple[Amendment, ...], tuple[PlanProblem, ...]]:
    """Apply `specs` in file order to `original`, one amendment at a time
    (Req 3.3, 3.4, 3.5, 3.6, 3.7). Each amendment is all-or-nothing: every
    one of its operations must be valid for any of them to take effect. An
    amendment whose date is earlier than the previous amendment's, or which
    holds any invalid operation, is not applied; application then stops,
    and one further problem names every amendment after it as not checked
    (never individually re-validated, so a later amendment referencing a
    row the failed one would have added is never reported as a spurious
    unknown-id problem).

    Returns the state before any amendment, then the state after each
    amendment that was applied (so `states[0] is original`); the applied
    amendments themselves, carrying their trail; and every problem found.
    With no specs, returns `(original,), (), ()` (Postconditions).
    """
    states: list[PlanState] = [original]
    amendments: list[Amendment] = []
    problems: list[PlanProblem] = []
    committed = original
    used_ids: set[str] = {row.id for row in original.rows}
    prev_date: date | None = None
    total = len(specs)

    for index, spec in enumerate(specs):
        ordinal = index + 1
        amendment_problems: list[PlanProblem] = []

        if prev_date is not None and spec.date < prev_date:
            amendment_problems.append(
                PlanProblem(
                    entry=f"amendment[{ordinal}]",
                    field="date",
                    message=(
                        f"{spec.date} is before the previous "
                        f"amendment's date {prev_date}"
                    ),
                )
            )

        trial_rows = list(committed.rows)
        trial_targets = list(committed.targets)
        trial_used_ids = set(used_ids)
        changes: list[Change] = []

        for op_index, op in enumerate(spec.ops):
            change, problem = _apply_op(
                op,
                ordinal=ordinal,
                op_index=op_index,
                rows=trial_rows,
                targets=trial_targets,
                used_ids=trial_used_ids,
                starts=starts,
                ends=ends,
                count=count,
            )
            if problem is not None:
                amendment_problems.append(problem)
            elif change is not None:
                changes.append(change)

        if amendment_problems:
            problems.extend(amendment_problems)
            if ordinal < total:
                problems.append(
                    PlanProblem(
                        entry=f"amendment[{ordinal + 1}..{total}]",
                        field=None,
                        message="not checked",
                    )
                )
            break

        committed = PlanState(rows=tuple(trial_rows), targets=tuple(trial_targets))
        states.append(committed)
        amendments.append(
            Amendment(
                ordinal=ordinal,
                date=spec.date,
                reason=spec.reason,
                changes=tuple(changes),
            )
        )
        used_ids = trial_used_ids
        prev_date = spec.date

    return tuple(states), tuple(amendments), tuple(problems)


def check_overrides(
    states: Sequence[PlanState],
    amendments: Sequence[Amendment],
    overrides: Sequence[Override],
) -> tuple[PlanProblem, ...]:
    """Report, for every override whose `row_id` does not exist in the
    state after applying every amendment dated on or before the override's
    date, one problem naming that override and id. Nothing else about an
    override is judged here (Req 3.8, 2.10).

    `states` and `amendments` are `apply_amendments`' return values: since
    every applied amendment's date is non-decreasing by construction, the
    amendments dated on or before an override's date are always a prefix
    of `amendments`, so `states[len(prefix)]` is the state as of that date.
    """
    problems = []
    for index, override in enumerate(overrides):
        applied = 0
        for amendment in amendments:
            if amendment.date <= override.date:
                applied += 1
            else:
                break
        state = states[applied]
        if state.row(override.row_id) is None:
            problems.append(
                PlanProblem(
                    entry=f"override[{index}] (id {override.row_id})",
                    field="row_id",
                    message=(
                        f"no row with id {override.row_id} exists as of {override.date}"
                    ),
                )
            )
    return tuple(problems)


def build_block(
    *,
    id: str,
    title: str,
    starts: date,
    ends: date,
    goal: str,
    mesocycle_days: int,
    original: PlanState,
    current: PlanState,
    amendments: Sequence[Amendment],
    overrides: Sequence[Override],
) -> Block:
    """Assemble the `Block`: derive its mesocycles from `starts`, `ends`
    and `mesocycle_days` alone (Req 3.1), place each of `current`'s rows in
    the window containing its date (Req 3.2), and order each window's rows
    by date and then by position in `current.rows` -- source order within a
    day, added rows after original ones (Req 4.5)."""
    windows = mesocycle_windows(starts, ends, mesocycle_days)
    mesocycles = []
    for number, first, last in windows:
        target = current.target(number)
        window_rows = [row for row in current.rows if first <= row.date <= last]
        window_rows.sort(key=lambda row: row.date)
        mesocycles.append(
            Mesocycle(
                number=number,
                starts=first,
                ends=last,
                nominal_days=mesocycle_days,
                target_load=target.target_load if target is not None else None,
                focus=target.focus if target is not None else None,
                workouts=tuple(window_rows),
            )
        )
    return Block(
        id=id,
        title=title,
        starts=starts,
        ends=ends,
        goal=goal,
        mesocycle_days=mesocycle_days,
        original=original,
        current=current,
        amendments=tuple(amendments),
        overrides=tuple(overrides),
        mesocycles=tuple(mesocycles),
    )
