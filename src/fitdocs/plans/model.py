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
from collections.abc import Sequence
from dataclasses import dataclass
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
