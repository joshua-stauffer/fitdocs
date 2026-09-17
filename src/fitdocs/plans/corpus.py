"""The package's one corpus read: every recognized workout page reduced to
what matching and summing need (plan-resolution spec, task 2.1). See
"CorpusScan (`src/fitdocs/plans/corpus.py`)" in
`.kiro/specs/plan-resolution/design.md` (Req 1.1, 1.3, 1.4, 1.5, 1.6, 1.7).

This module, `plans/page.py` and `plans/engine.py` are the package's **only**
importers of `fitdocs.contract` -- the package's third and last (design
"Allowed Dependencies"). It reads exactly seven things per document, each
through its own contract reader (`is_workout_document`, `document_date`,
`document_sport`, `document_modality`, `document_indoor`,
`document_start_time`, `document_load`) and spells no frontmatter key of its
own: mapping the raw sport/modality strings onto :class:`fitdocs.model.Sport`
and :class:`fitdocs.model.Modality` is this module's own job (the contract
may not import `fitdocs.model` -- design §ContractReaders), so an unknown
spelling here is absent, never a raised error and never a fabricated
enumeration member.

It reads no flag, no title, no distance, and no activity-quality flag (Req
1.7): a flagged page is read and counted exactly like any other. Among the
plan-resolution modules this spec adds, this module is the package's one
corpus *read* edge (design.md 234-237): `matching`, `aggregate` and
`placement` are pure functions over the frozen records this module
produces, while `reconcile` reads `fitdocs.toml` settings and writes
through the plan pass -- filesystem work of its own, not corpus reads.

**Discovery**: `<root>/workouts/*.md`, sorted, through
`fitdocs.docio.read_frontmatter` -- the one shared filesystem-plus-frontmatter
read every scanner in the package uses, and the one place a symlink, an
unreadable file, an undecodable file and a missing frontmatter fence are all
refused before this module ever sees them. `Path.glob` is not recursive, so a
file in a subdirectory of `workouts/` is never scanned. A page whose parsed
frontmatter is not a recognized workout document (`is_workout_document` is
`False` -- a planned-workout page, among others) is silently excluded, the
same discipline `fitdocs.history.documents.scan_documents` applies. A missing
`workouts/` directory yields an empty corpus. This function never raises for
a bad page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from fitdocs import docio
from fitdocs.contract import (
    document_date,
    document_indoor,
    document_load,
    document_modality,
    document_sport,
    document_start_time,
    is_workout_document,
)
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.model import Modality, Sport

__all__ = [
    "Corpus",
    "LoggedWorkout",
    "scan_corpus",
]

#: Sentinels `order_key` substitutes for a missing `day` / `start_time` so the
#: tuple stays homogeneously typed while still sorting undated-last and
#: no-start-time-last (design.md's own "with sentinels for None"). Both are
#: strictly greater than any value a real document ever carries: `date.max`
#: for `day`, and `datetime.max` (with an explicit UTC offset, so it always
#: compares against another *aware* `datetime` -- `document_start_time` never
#: returns a naive one) for `start_time`.
_UNDATED_SENTINEL: date = date.max
_NO_START_TIME_SENTINEL: datetime = datetime.max.replace(tzinfo=UTC)


def _map_sport(value: str | None) -> Sport | None:
    """The raw recorded sport string onto :class:`Sport` by value, or `None`
    for an absent or unrecognized spelling (Req 1.4) -- never raised."""
    if value is None:
        return None
    try:
        return Sport(value)
    except ValueError:
        return None


def _map_modality(value: str | None) -> Modality | None:
    """The raw recorded modality string onto :class:`Modality` by value, or
    `None` for an absent or unrecognized spelling -- never raised."""
    if value is None:
        return None
    try:
        return Modality(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class LoggedWorkout:
    """One recognized workout document, reduced to what matching and summing
    need (Req 1.1-1.7).

    `path` is data-root-relative and forward-slash form (`"workouts/<stem>.md"`),
    never absolute. `day` is `None` exactly when the document's own recorded
    date could not be read (Req 1.3) -- it then belongs to no day. `sport` and
    `modality` are `None` when unrecorded *or* unrecognized (Req 1.4).
    `start_time` is the document's own recorded *aware* local start time, or
    `None`. `load` and `methodology` travel together: `methodology is None`
    if and only if `load is None`, inherited unchanged from
    :func:`fitdocs.contract.document_load` (Req 1.5).
    """

    stem: str
    path: str
    day: date | None
    sport: Sport | None
    modality: Modality | None
    indoor: bool | None
    start_time: datetime | None
    load: float | None
    methodology: str | None

    @property
    def order_key(self) -> tuple[bool, date, bool, datetime, str]:
        """The one ordering every consumer of the corpus uses (design.md
        3.8): undated last, then by day, then a missing start time last,
        then by instant, then by stem -- the final tiebreak for two pages on
        the same day at the same (or both-missing) start time."""
        return (
            self.day is None,
            self.day if self.day is not None else _UNDATED_SENTINEL,
            self.start_time is None,
            self.start_time if self.start_time is not None else _NO_START_TIME_SENTINEL,
            self.stem,
        )


@dataclass(frozen=True)
class Corpus:
    """The whole scan's result: every recognized workout page, sorted by
    :attr:`LoggedWorkout.order_key` (design.md's own stated postcondition:
    two scans of an unchanged root are equal)."""

    workouts: tuple[LoggedWorkout, ...]

    def by_stem(self, stem: str) -> LoggedWorkout | None:
        """The workout with this stem, or `None` -- total over
        :attr:`workouts`: every stem present in `workouts` is found."""
        for workout in self.workouts:
            if workout.stem == stem:
                return workout
        return None

    def on_day(self, day: date) -> tuple[LoggedWorkout, ...]:
        """Every workout recorded on `day`, in :attr:`workouts` order."""
        return tuple(workout for workout in self.workouts if workout.day == day)

    def within(self, first: date, last: date) -> tuple[LoggedWorkout, ...]:
        """Every *dated* workout in the inclusive window `[first, last]`, in
        :attr:`workouts` order -- an undated workout is never returned
        (design.md's own stated postcondition)."""
        return tuple(
            workout
            for workout in self.workouts
            if workout.day is not None and first <= workout.day <= last
        )


def scan_corpus(data_root: Path) -> Corpus:
    """Every recognized workout document at `data_root`'s `workouts/` top
    level, reduced to :class:`LoggedWorkout` and sorted by
    :attr:`LoggedWorkout.order_key` (Req 1.1-1.7).

    Reads no `.fit` file, no network resource, and no other directory --
    `<root>/workouts/*.md`, non-recursively, through
    `fitdocs.docio.read_frontmatter`. Never raises for a bad page: a file
    that read helper declines, or whose frontmatter is not a recognized
    workout document, is silently excluded (see the module docstring for
    why). A missing `workouts/` directory yields an empty corpus.
    """
    workouts_dir = data_root / WORKOUTS_DIR
    workouts: list[LoggedWorkout] = []

    if workouts_dir.is_dir():
        for path in sorted(workouts_dir.glob("*.md")):
            frontmatter = docio.read_frontmatter(path)
            if frontmatter is None or not is_workout_document(frontmatter):
                continue
            load_reading = document_load(frontmatter)
            workouts.append(
                LoggedWorkout(
                    stem=path.stem,
                    path=f"{WORKOUTS_DIR}/{path.name}",
                    day=document_date(frontmatter),
                    sport=_map_sport(document_sport(frontmatter)),
                    modality=_map_modality(document_modality(frontmatter)),
                    indoor=document_indoor(frontmatter),
                    start_time=document_start_time(frontmatter),
                    load=load_reading.value if load_reading is not None else None,
                    methodology=(
                        load_reading.methodology if load_reading is not None else None
                    ),
                )
            )

    workouts.sort(key=lambda workout: workout.order_key)
    return Corpus(workouts=tuple(workouts))
