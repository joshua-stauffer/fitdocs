"""Resolve every planned row of a block to exactly one state (plan-resolution
spec, task 2.2). See "Matcher" (`src/fitdocs/plans/matching.py`) in
`.kiro/specs/plan-resolution/design.md` (Req 2.1-2.7, 3.1-3.9, 4.1-4.4).

This module is pure: no `Path`, no I/O, no clock. It imports only
`fitdocs.plans.corpus`, `fitdocs.plans.model` and the standard library. The
`today` parameter is a `date` value the caller (the pass module) resolved;
this module reads no clock of its own and uses `today` for nothing beyond
telling `NOT_LOGGED` from `UPCOMING` (Req 2.6).

**How a row is resolved** (design.md "How a row is resolved"):
1. A row named by an effective override (the winning entry for its id, by
   greatest `(date, index)`) is `SKIPPED` (the override marks it skipped) or
   `OVERRIDDEN` (the override names stems); a stem the corpus lacks is
   `missing` and reported once; a stem two effective overrides both name is
   kept on both rows and reported once as a conflict.
2. Every other row's candidates are every logged workout on its date whose
   type matches (`is_candidate`), with every stem any effective override
   claims removed first -- claimed, existing or not.
3. Rows without an override, on one day, whose candidate sets intersect
   (transitively) form a competition group. A group of one row with one
   candidate is `EXACT`; with several, `ABSORBED`. A group of two or more
   rows resolves by a greedy assignment: each row, in block order, takes the
   first unassigned candidate in its own set by `order_key`; a row that
   takes one is `MATCHED` / `AMBIGUOUS`, naming the other rows in the group
   as `competitors`; a row that takes none is `NOT_LOGGED` / `UPCOMING`,
   with the same `competitors`; unassigned candidates stay unclaimed.
4. A row with no stems and no override is `NOT_LOGGED` when its date is
   before `today`, else `UPCOMING`.
5. A `NOT_LOGGED` / `UPCOMING` row lists every logged workout of its own day
   (`same_day`), each with the id of the row of this block that claimed it,
   if any.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from fitdocs.plans.corpus import Corpus, LoggedWorkout
from fitdocs.plans.model import Block, Override, PlannedWorkout

__all__ = [
    "RowState",
    "Confidence",
    "RowOutcome",
    "ReconcileProblem",
    "MatchResult",
    "match_rows",
]


class RowState(StrEnum):
    """The five states every planned row resolves to (Req 2.1)."""

    MATCHED = "matched"
    OVERRIDDEN = "overridden"
    SKIPPED = "skipped"
    NOT_LOGGED = "not logged"
    UPCOMING = "upcoming"


class Confidence(StrEnum):
    """The three confidence labels a `MATCHED` row carries, and no other
    (Req 3.9)."""

    EXACT = "exact"
    ABSORBED = "absorbed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class RowOutcome:
    """One current row's resolved state (Req 2.1-2.7, 3.1-3.9, 4.1-4.5).

    Invariants: `confidence is not None` iff `state is MATCHED`; `state is
    MATCHED` implies `stems`; `state is OVERRIDDEN` implies `stems or
    missing`; `state in {SKIPPED, NOT_LOGGED, UPCOMING}` implies not
    `stems`; a stem appears in at most one `MATCHED` row.
    """

    row_id: str
    state: RowState
    stems: tuple[str, ...]
    confidence: Confidence | None
    missing: tuple[str, ...]
    override_index: int | None
    override_date: date | None
    reason: str | None
    competitors: tuple[str, ...]
    same_day: tuple[tuple[str, str | None], ...]


@dataclass(frozen=True)
class ReconcileProblem:
    """One independently reported override problem: a missing stem or a
    stem two effective overrides both name (Req 4.3, 4.4)."""

    entry: str
    message: str

    def describe(self) -> str:
        """`"<entry>: <message>"`."""
        return f"{self.entry}: {self.message}"


@dataclass(frozen=True)
class MatchResult:
    """Every current row's outcome, the stems this block claims, and every
    override problem found (Req 2.1, 4.2-4.4)."""

    rows: tuple[RowOutcome, ...]
    claimed: frozenset[str]
    problems: tuple[ReconcileProblem, ...]


def effective_overrides(block: Block) -> Mapping[str, tuple[int, Override]]:
    """For each `row_id` named by any of `block.overrides`, the entry with
    the greatest `(date, index)` -- `index` being the entry's position in
    `block.overrides` (Req 4.1). A later position in the source wins a tie
    on `date`."""
    winners: dict[str, tuple[int, Override]] = {}
    for index, override in enumerate(block.overrides):
        current = winners.get(override.row_id)
        if current is None or (override.date, index) > (
            current[1].date,
            current[0],
        ):
            winners[override.row_id] = (index, override)
    return winners


def is_candidate(row: PlannedWorkout, logged: LoggedWorkout) -> bool:
    """Whether `logged` is a type-and-date candidate for `row` (Req 3.1,
    3.2): equal dates, equal sports, equal modality when `row` states one,
    and an indoor flag that agrees when `row` states one -- an unrecorded
    flag on `logged` agreeing only with `row.indoor is False`. An undated
    page or one whose sport could not be read never qualifies (Req 1.3,
    1.4). Nothing else is consulted (Req 2.7)."""
    if logged.day is None or logged.day != row.date:
        return False
    if logged.sport is None or logged.sport != row.sport:
        return False
    if row.modality is not None and logged.modality != row.modality:
        return False
    if row.indoor is True and logged.indoor is not True:
        return False
    return not (row.indoor is False and logged.indoor is True)


def _override_outcome(index: int, override: Override, corpus: Corpus) -> RowOutcome:
    """The `SKIPPED` / `OVERRIDDEN` outcome for the row this effective
    override names (Req 3.3, 4.3, 4.5)."""
    stems = tuple(stem for stem in override.stems if corpus.by_stem(stem) is not None)
    missing = tuple(stem for stem in override.stems if corpus.by_stem(stem) is None)
    state = RowState.SKIPPED if override.skipped else RowState.OVERRIDDEN
    return RowOutcome(
        row_id=override.row_id,
        state=state,
        stems=stems,
        confidence=None,
        missing=missing,
        override_index=index,
        override_date=override.date,
        reason=override.reason,
        competitors=(),
        same_day=(),
    )


def _override_problems(
    winners: Mapping[str, tuple[int, Override]], corpus: Corpus
) -> tuple[frozenset[str], tuple[ReconcileProblem, ...]]:
    """The stems every effective override claims (existing or not, Req
    4.2), and every missing-stem / two-overrides-one-stem problem, source
    ordered by the lowest override index involved, missing before conflict
    on a tie (Req 4.3, 4.4)."""
    stem_owners: dict[str, list[tuple[int, Override]]] = {}
    for index, override in winners.values():
        for stem in override.stems:
            stem_owners.setdefault(stem, []).append((index, override))
    claimed = frozenset(stem_owners)

    ordered: list[tuple[int, int, ReconcileProblem]] = []
    for index, override in winners.values():
        for stem in override.stems:
            if corpus.by_stem(stem) is None:
                ordered.append(
                    (
                        index,
                        0,
                        ReconcileProblem(
                            entry=f"override[{index}] (id {override.row_id})",
                            message=(
                                f"stem `{stem}` not found among the logged workouts"
                            ),
                        ),
                    )
                )
    for stem, owners in stem_owners.items():
        if len(owners) > 1:
            owners_sorted = sorted(owners, key=lambda item: item[0])
            names = " and ".join(
                f"override[{i}] (id {o.row_id})" for i, o in owners_sorted
            )
            ordered.append(
                (
                    owners_sorted[0][0],
                    1,
                    ReconcileProblem(
                        entry=names,
                        message=f"stem `{stem}` is claimed by more than one override",
                    ),
                )
            )
    ordered.sort(key=lambda item: (item[0], item[1]))
    return claimed, tuple(item[2] for item in ordered)


def _split_state(row: PlannedWorkout, *, today: date) -> RowState:
    """`NOT_LOGGED` when `row.date` is before `today`, else `UPCOMING` (Req
    2.4, 2.5, 2.6)."""
    return RowState.NOT_LOGGED if row.date < today else RowState.UPCOMING


def _singleton_outcome(
    row: PlannedWorkout, cands: list[LoggedWorkout], *, today: date
) -> RowOutcome:
    """A competition group of one row: no candidate is the split; one is
    `EXACT`; several are `ABSORBED` with all of them, in `order_key` order
    (Req 3.3, 3.4, 3.8)."""
    ordered = sorted(cands, key=lambda logged: logged.order_key)
    if not ordered:
        return RowOutcome(
            row_id=row.id,
            state=_split_state(row, today=today),
            stems=(),
            confidence=None,
            missing=(),
            override_index=None,
            override_date=None,
            reason=None,
            competitors=(),
            same_day=(),
        )
    confidence = Confidence.EXACT if len(ordered) == 1 else Confidence.ABSORBED
    return RowOutcome(
        row_id=row.id,
        state=RowState.MATCHED,
        stems=tuple(logged.stem for logged in ordered),
        confidence=confidence,
        missing=(),
        override_index=None,
        override_date=None,
        reason=None,
        competitors=(),
        same_day=(),
    )


def _competition_outcomes(
    rows: Mapping[str, PlannedWorkout],
    group: list[str],
    candidates: Mapping[str, list[LoggedWorkout]],
    *,
    today: date,
) -> dict[str, RowOutcome]:
    """A competition group of two or more rows: each row, in block order (the
    order `group` is already built in), takes the first unassigned candidate
    in its own set by `order_key`; a row that takes one is `MATCHED` /
    `AMBIGUOUS`; a row that takes none is `NOT_LOGGED` / `UPCOMING`; both
    name the group's other rows as `competitors` (Req 3.5, 3.6)."""
    used_stems: set[str] = set()
    assigned: dict[str, LoggedWorkout | None] = {}
    for row_id in group:
        ordered = sorted(candidates[row_id], key=lambda logged: logged.order_key)
        chosen = next((c for c in ordered if c.stem not in used_stems), None)
        if chosen is not None:
            used_stems.add(chosen.stem)
        assigned[row_id] = chosen

    outcomes: dict[str, RowOutcome] = {}
    for row_id in group:
        competitors = tuple(other for other in group if other != row_id)
        chosen = assigned[row_id]
        if chosen is not None:
            outcomes[row_id] = RowOutcome(
                row_id=row_id,
                state=RowState.MATCHED,
                stems=(chosen.stem,),
                confidence=Confidence.AMBIGUOUS,
                missing=(),
                override_index=None,
                override_date=None,
                reason=None,
                competitors=competitors,
                same_day=(),
            )
        else:
            outcomes[row_id] = RowOutcome(
                row_id=row_id,
                state=_split_state(rows[row_id], today=today),
                stems=(),
                confidence=None,
                missing=(),
                override_index=None,
                override_date=None,
                reason=None,
                competitors=competitors,
                same_day=(),
            )
    return outcomes


def match_rows(block: Block, corpus: Corpus, *, today: date) -> MatchResult:
    """Resolve every row of `block.current.rows` to exactly one
    `RowOutcome`, in that order (Req 2.1-2.7, 3.1-3.9, 4.1-4.4)."""
    winners = effective_overrides(block)
    claimed_by_override, override_problems = _override_problems(winners, corpus)

    outcomes: dict[str, RowOutcome] = {}
    for row in block.current.rows:
        if row.id in winners:
            index, override = winners[row.id]
            outcomes[row.id] = _override_outcome(index, override, corpus)

    unoverridden = [row for row in block.current.rows if row.id not in winners]
    rows_by_id = {row.id: row for row in unoverridden}
    candidates: dict[str, list[LoggedWorkout]] = {
        row.id: [
            logged
            for logged in corpus.workouts
            if logged.stem not in claimed_by_override and is_candidate(row, logged)
        ]
        for row in unoverridden
    }

    parent: dict[str, str] = {row.id: row.id for row in unoverridden}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    stem_to_rows: dict[str, list[str]] = {}
    for row in unoverridden:
        for logged in candidates[row.id]:
            stem_to_rows.setdefault(logged.stem, []).append(row.id)
    for sharing in stem_to_rows.values():
        for other in sharing[1:]:
            union(sharing[0], other)

    groups: dict[str, list[str]] = {}
    for row in unoverridden:
        groups.setdefault(find(row.id), []).append(row.id)

    for group in groups.values():
        if len(group) == 1:
            row_id = group[0]
            outcomes[row_id] = _singleton_outcome(
                rows_by_id[row_id], candidates[row_id], today=today
            )
        else:
            outcomes.update(
                _competition_outcomes(rows_by_id, group, candidates, today=today)
            )

    claimed = frozenset(stem for outcome in outcomes.values() for stem in outcome.stems)
    claim_map: dict[str, str] = {}
    for outcome in outcomes.values():
        for stem in outcome.stems:
            claim_map[stem] = outcome.row_id

    final_rows: list[RowOutcome] = []
    for row in block.current.rows:
        outcome = outcomes[row.id]
        if outcome.state in (RowState.NOT_LOGGED, RowState.UPCOMING):
            same_day = tuple(
                (logged.stem, claim_map.get(logged.stem))
                for logged in corpus.on_day(row.date)
            )
            outcome = replace(outcome, same_day=same_day)
        final_rows.append(outcome)

    return MatchResult(
        rows=tuple(final_rows), claimed=claimed, problems=override_problems
    )
