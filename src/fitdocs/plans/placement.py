"""Place the words: the vocabulary, the per-block reconciliation record, and
the `Resolution` value the two wave-1 renderers consume (plan-resolution
spec, task 2.4). See "Placement" (`src/fitdocs/plans/placement.py`) in
`.kiro/specs/plan-resolution/design.md` (Req 3.7, 4.3, 4.5, 5.3, 6.3-6.7,
7.1-7.7).

Pure: no `Path`, no clock, no I/O. This module, `plans.aggregate` and
`plans.reconcile` (which 3.1 adds) are the only modules of this package
that import `fitdocs.history` -- this one for exactly two names,
`MethodologyChoice` and `MethodologyProblem`, imported as the package root
(`import fitdocs.history`) rather than a `from`-import, so the boundary
test's forbidden-target scan can admit exactly this module's root import
(its own exemption-map entry) while every real `fitdocs.history.<submodule>`
import stays forbidden everywhere, this module included.

**`BlockReconciliation` is defined here** -- the lowest module that reads
it (`place_resolution` takes one; `reconcile.py`, one module up, imports it
from here rather than the reverse, which would be a cycle the boundary
test's equality pin reds).

**The vocabulary lives here and nowhere else** (Req 7.7): the five
`RowState` values and three `Confidence` values (imported from
`plans.matching`, never re-spelled), plus the eight constants below. Links
route through `page.link_text` for text and `layout.logged_rel_link_from_block`
/ `layout.logged_rel_link_from_planned` for hrefs, depending on which page
the fragment renders on (Req 7.5); numbers through `page.format_load`; a
recorded time as `f"{t:%H:%M}"` of the logged workout's own local wall
clock -- never a clock this module reads and never the pass's `today`,
which this module's signatures do not even accept (Req 5.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import fitdocs.history
from fitdocs import layout
from fitdocs.model import Sport
from fitdocs.plans import page
from fitdocs.plans.aggregate import MesocycleLoad
from fitdocs.plans.corpus import Corpus, LoggedWorkout
from fitdocs.plans.matching import Confidence, ReconcileProblem, RowOutcome, RowState
from fitdocs.plans.model import Block, PlannedWorkout
from fitdocs.plans.resolution import MesocycleResolution, Resolution, RowResolution

__all__ = [
    "BlockReconciliation",
    "actual_load_sentence",
    "place_resolution",
]

# --- vocabulary (Req 7.7) ----------------------------------------------------

NOT_COMPUTED = "not computed"
AT_LEAST = "at least"
NO_TARGET = "no target"
NOT_FOUND = "not found"
UNSCORED = "unscored"
ACTUAL_LOAD = "Actual load:"
UNPLANNED = "Unplanned:"
EXCLUDED = "Excluded from the sum (scored under another methodology):"


# --- the per-block reconciliation record (Req 3.7, 4.3, 4.5) ----------------


@dataclass(frozen=True)
class BlockReconciliation:
    """One block's whole reconciliation: every current row's outcome, every
    mesocycle's load picture, the run's chosen methodology or the problem
    that kept one from being chosen, and every override problem found (Req
    3.7, 4.3, 4.5)."""

    block_id: str
    rows: tuple[RowOutcome, ...]
    mesocycles: tuple[MesocycleLoad, ...]
    methodology: fitdocs.history.MethodologyChoice | fitdocs.history.MethodologyProblem
    problems: tuple[ReconcileProblem, ...]

    def counts(self) -> Mapping[RowState, int]:
        """Every `RowState`, zero included, over `rows` (invariant:
        `sum(counts().values()) == len(rows)`)."""
        counts: dict[RowState, int] = {state: 0 for state in RowState}
        for row in self.rows:
            counts[row.state] += 1
        return counts

    @property
    def ambiguous(self) -> tuple[str, ...]:
        """The row ids of every `AMBIGUOUS` row, in block order (`rows`'
        own order)."""
        return tuple(
            row.row_id for row in self.rows if row.confidence is Confidence.AMBIGUOUS
        )

    @property
    def unplanned_count(self) -> int:
        """`sum(len(m.unplanned) for m in mesocycles)`."""
        return sum(len(mesocycle.unplanned) for mesocycle in self.mesocycles)


# --- shared phrase helpers ----------------------------------------------------


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"


def _agrees(count: int) -> str:
    """The verb agreeing with `<count> logged workout(s)` as subject --
    `"matches"` for the singular subject (`count == 1`), `"match"` for the
    plural. design.md's grammar table shows only the plural sentence; the
    singular verb is this module's own choice, made here to keep the
    sentence grammatical when exactly one logged workout fulfils a row."""
    return "matches" if count == 1 else "match"


def logged_phrase(workout: LoggedWorkout) -> str:
    """The sport value (`"unknown sport"` when `None`), with a
    parenthesised, comma-joined modality (only when `sport is Sport.WORKOUT`
    and stated) and `page.INDOOR_WORD`'s word when `indoor` is `True` -- the
    same shape as `page.sport_phrase`, over a `LoggedWorkout` rather than a
    `PlannedWorkout`."""
    if workout.sport is None:
        return "unknown sport"
    extras: list[str] = []
    if workout.sport is Sport.WORKOUT and workout.modality is not None:
        extras.append(str(workout.modality))
    if workout.indoor:
        extras.append(page.INDOOR_WORD)
    if not extras:
        return str(workout.sport)
    return f"{workout.sport} ({', '.join(extras)})"


def load_phrase(workout: LoggedWorkout, methodology: str | None) -> str:
    """`"load 45"` when scored under `methodology`; `"load 45 under other
    (excluded from the sum)"` when scored under a different one;
    :data:`UNSCORED` when `workout.load is None`. With `methodology is
    None`, a scored workout always reads plain (there is no "chosen" to
    compare against)."""
    if workout.load is None:
        return UNSCORED
    formatted = f"load {page.format_load(workout.load)}"
    if methodology is not None and workout.methodology != methodology:
        return f"{formatted} under other (excluded from the sum)"
    return formatted


def _block_link(stem: str) -> str:
    return f"[{page.link_text(stem)}]({layout.logged_rel_link_from_block(stem)})"


def _planned_link(stem: str) -> str:
    return f"[{page.link_text(stem)}]({layout.logged_rel_link_from_planned(stem)})"


def _fulfilling_bullet(stem: str, corpus: Corpus) -> str:
    """`"- <link> -- Run, 07:15, load 45"`, planned-page depth -- one bullet
    per fulfilling logged page (Req 7.4)."""
    workout = corpus.by_stem(stem)
    assert workout is not None, f"stem {stem!r} not found in corpus"
    parts = [logged_phrase(workout)]
    if workout.start_time is not None:
        parts.append(f"{workout.start_time:%H:%M}")
    parts.append(load_phrase(workout, None))
    return f"- {_planned_link(stem)} -- {', '.join(parts)}"


def _group_ids(
    block: Block, row_id: str, competitors: tuple[str, ...]
) -> tuple[str, ...]:
    """`row_id` and every id in `competitors`, in `block.current.rows`
    order -- the one block-order truth every competing row's section agrees
    on, regardless of which row's section is being rendered."""
    ids = {row_id, *competitors}
    return tuple(row.id for row in block.current.rows if row.id in ids)


# --- the row cell (block-page depth; Req 7.1, 7.2) ---------------------------


def row_cell(outcome: RowOutcome) -> str:
    """One line, no pipe, block-page depth links (Req 7.1, 7.2). The
    overridden cell is the `overridden: ` prefix plus one comma-join over
    the existing stems' links first and the missing stems' `` `stem` (not
    found) `` items after -- with zero existing stems, exactly
    `` overridden: `stem` (not found) `` (no leading comma)."""
    if outcome.state is RowState.MATCHED:
        assert outcome.confidence is not None
        links = ", ".join(_block_link(stem) for stem in outcome.stems)
        if outcome.confidence is Confidence.EXACT:
            return f"{RowState.MATCHED.value}: {links}"
        if outcome.confidence is Confidence.ABSORBED:
            return (
                f"{RowState.MATCHED.value} "
                f"({Confidence.ABSORBED.value} {len(outcome.stems)}): {links}"
            )
        return f"{RowState.MATCHED.value} ({Confidence.AMBIGUOUS.value}): {links}"
    if outcome.state is RowState.OVERRIDDEN:
        parts = [_block_link(stem) for stem in outcome.stems]
        parts.extend(f"`{stem}` ({NOT_FOUND})" for stem in outcome.missing)
        return f"{RowState.OVERRIDDEN.value}: {', '.join(parts)}"
    return outcome.state.value


# --- the row section (planned-page depth; Req 7.1, 7.3, 7.4) ---------------


def _override_or_skip_sentence(label: str, outcome: RowOutcome) -> str:
    assert outcome.override_date is not None
    date_iso = outcome.override_date.isoformat()
    base = f"{label} by the plan source (override dated {date_iso})"
    return f"{base}: {outcome.reason}." if outcome.reason else f"{base}."


def _matched_section(
    block: Block, row: PlannedWorkout, outcome: RowOutcome, corpus: Corpus
) -> tuple[str, ...]:
    assert outcome.confidence is not None
    if outcome.confidence is Confidence.EXACT:
        lines = [
            "Matched (exact): one logged workout on this day is of this "
            "type, and no other planned workout competes for it."
        ]
    elif outcome.confidence is Confidence.ABSORBED:
        n = len(outcome.stems)
        lines = [
            f"Matched (absorbed): {n} logged workouts on this day are of "
            "this type, and no other planned workout competes for them; "
            f"all {n} are taken as this workout."
        ]
    else:
        group = _group_ids(block, row.id, outcome.competitors)
        ids_text = ", ".join(f"`{row_id}`" for row_id in group)
        lines = [
            f"Matched (ambiguous): {len(group)} planned workouts of this "
            f"type on this day ({ids_text}) compete for the logged "
            "workouts; assigned by start-time order. Settle it with an "
            "override entry naming this row and the logged workout stems."
        ]
    lines.extend(_fulfilling_bullet(stem, corpus) for stem in outcome.stems)
    return tuple(lines)


def _overridden_section(outcome: RowOutcome, corpus: Corpus) -> tuple[str, ...]:
    lines = [_override_or_skip_sentence("Overridden", outcome)]
    lines.extend(_fulfilling_bullet(stem, corpus) for stem in outcome.stems)
    lines.extend(
        f"- `{stem}` -- {NOT_FOUND} among the logged workouts"
        for stem in outcome.missing
    )
    return tuple(lines)


def _split_section(
    block: Block, row: PlannedWorkout, outcome: RowOutcome, corpus: Corpus
) -> tuple[str, ...]:
    if outcome.state is RowState.NOT_LOGGED:
        lines = [
            f"Not logged: no logged workout on {row.date.isoformat()} is of this type."
        ]
    else:
        lines = ["Upcoming."]

    if outcome.competitors:
        group = _group_ids(block, row.id, outcome.competitors)
        claimed: list[str] = []
        for _, claimant in outcome.same_day:
            if claimant in group and claimant not in claimed:
                claimed.append(claimant)
        ordered_claimants = [row_id for row_id in group if row_id in claimed]
        names = ", ".join(f"`{row_id}`" for row_id in ordered_claimants)
        m = len(ordered_claimants)
        lines.append(
            f"{len(group)} planned workouts of this type on this day "
            f"competed for {m} {_plural(m, 'logged workout')}, assigned to "
            f"{names} by start-time order."
        )

    if outcome.same_day:
        lines.append("Logged on this day:")
        for stem, claimant in outcome.same_day:
            workout = corpus.by_stem(stem)
            assert workout is not None, f"stem {stem!r} not found in corpus"
            phrase = logged_phrase(workout)
            link = _planned_link(stem)
            if claimant is not None:
                lines.append(f"- {link} -- {phrase} (taken by `{claimant}`)")
            else:
                lines.append(f"- {link} -- {phrase}")

    return tuple(lines)


def row_section(
    block: Block, row: PlannedWorkout, outcome: RowOutcome, corpus: Corpus
) -> tuple[str, ...]:
    """The label's rule in a sentence, one bullet per fulfilling logged
    page with its sport phrase, wall-clock time when recorded and load
    phrase, the override date and reason, the competitor sentence, the
    same-day listing -- planned-page depth links (Req 7.1, 7.3, 7.4)."""
    if outcome.state is RowState.MATCHED:
        return _matched_section(block, row, outcome, corpus)
    if outcome.state is RowState.OVERRIDDEN:
        return _overridden_section(outcome, corpus)
    if outcome.state is RowState.SKIPPED:
        return (_override_or_skip_sentence("Skipped", outcome),)
    return _split_section(block, row, outcome, corpus)


# --- the actual-load sentence (Req 6.3-6.7) ----------------------------------


def actual_load_sentence(mesocycle: MesocycleLoad) -> str:
    """The text after `"Actual load: "`, exactly the grammar design.md
    tabulates (Req 6.3-6.7) -- reused verbatim by the report."""
    if mesocycle.methodology is None:
        return (
            f"{ACTUAL_LOAD} {NOT_COMPUTED} -- "
            "no methodology chosen (see Resolution below)."
        )
    if not mesocycle.pages:
        return f"{ACTUAL_LOAD} {NOT_COMPUTED} -- no logged workout in this window."

    considered = mesocycle.considered
    scored_n = len(mesocycle.scored)
    excluded_n = len(mesocycle.excluded)
    noun_clause = (
        f"logged workout scored under {mesocycle.methodology}"
        if considered == 1
        else f"logged workouts scored under {mesocycle.methodology}"
    )
    clause = f"{scored_n} of {considered} {noun_clause}"

    total = mesocycle.total
    if total is None:
        if excluded_n:
            clause += f", {excluded_n} excluded (scored under other)"
        return f"{ACTUAL_LOAD} {NOT_COMPUTED} -- {clause}."

    if mesocycle.lower_bound:
        clause += f", {len(mesocycle.unscored)} unscored"
    if excluded_n:
        clause += f", {excluded_n} excluded (scored under other)"

    prefix = (
        f"{AT_LEAST} {page.format_load(total)}"
        if mesocycle.lower_bound
        else page.format_load(total)
    )
    if mesocycle.target is None:
        tail = NO_TARGET
    else:
        percent = mesocycle.percent_of_target
        assert percent is not None
        tail = (
            f"{AT_LEAST} {percent}% of target"
            if mesocycle.lower_bound
            else f"{percent}% of target"
        )

    return f"{ACTUAL_LOAD} {prefix} -- {clause}; {tail}."


def _mesocycle_bullet(workout: LoggedWorkout, methodology: str | None) -> str:
    assert workout.day is not None
    return (
        f"- {_block_link(workout.stem)} -- {workout.day.isoformat()}, "
        f"{logged_phrase(workout)}, {load_phrase(workout, methodology)}"
    )


def _after_table_lines(mesocycle: MesocycleLoad) -> tuple[str, ...]:
    """The unplanned and excluded listings after the day table (Req 6.6,
    6.7)."""
    lines: list[str] = []
    if mesocycle.unplanned:
        n = len(mesocycle.unplanned)
        lines.append(
            f"{UNPLANNED} {n} {_plural(n, 'logged workout')} in this window "
            f"{_agrees(n)} no planned workout."
        )
        lines.extend(
            _mesocycle_bullet(workout, mesocycle.methodology)
            for workout in mesocycle.unplanned
        )
    if mesocycle.excluded:
        lines.append(EXCLUDED)
        lines.extend(
            _mesocycle_bullet(workout, mesocycle.methodology)
            for workout in mesocycle.excluded
        )
    return tuple(lines)


# --- the block-level lines (Req 4.3, 4.5) ------------------------------------

_COUNT_ORDER: tuple[RowState, ...] = (
    RowState.MATCHED,
    RowState.OVERRIDDEN,
    RowState.SKIPPED,
    RowState.NOT_LOGGED,
    RowState.UPCOMING,
)


def _count_line(reconciliation: BlockReconciliation) -> str:
    """`Planned workouts: <N>` -- ` -- ` and the comma-join of `<count>
    <state>` for exactly the states whose count is `>= 1`, in the fixed
    order matched, overridden, skipped, not logged, upcoming; `matched`
    carries ` (<k> ambiguous)` only when `k >= 1`; zero-count states
    omitted; a block with no rows reads `Planned workouts: 0.`."""
    n = len(reconciliation.rows)
    if n == 0:
        return "Planned workouts: 0."
    counts = reconciliation.counts()
    parts: list[str] = []
    for state in _COUNT_ORDER:
        count = counts.get(state, 0)
        if count < 1:
            continue
        if state is RowState.MATCHED and reconciliation.ambiguous:
            parts.append(
                f"{count} {state.value} "
                f"({len(reconciliation.ambiguous)} {Confidence.AMBIGUOUS.value})"
            )
        else:
            parts.append(f"{count} {state.value}")
    return f"Planned workouts: {n} -- {', '.join(parts)}."


def _methodology_line(
    methodology: fitdocs.history.MethodologyChoice | fitdocs.history.MethodologyProblem,
) -> str:
    if isinstance(methodology, fitdocs.history.MethodologyChoice):
        source_words = {
            "configured": "configured",
            "inferred": "inferred from the logged workouts",
            "requested": "requested",
        }
        source_word = source_words[methodology.source]
        return f"Methodology: {methodology.methodology} ({source_word})."
    return f"Methodology: none chosen -- {methodology.detail}"


def _block_lines(reconciliation: BlockReconciliation) -> tuple[str, ...]:
    lines: list[str] = [
        _count_line(reconciliation),
        _methodology_line(reconciliation.methodology),
    ]
    if reconciliation.ambiguous:
        ids = ", ".join(f"`{row_id}`" for row_id in reconciliation.ambiguous)
        lines.append(f"Ambiguous: {ids} -- settle them with override entries.")
    if reconciliation.problems:
        lines.append("Problems:")
        lines.extend(f"- {problem.describe()}" for problem in reconciliation.problems)
    return tuple(lines)


# --- the resolution builder (Req 3.7, 4.3, 4.5, 6.1-6.7, 7.1-7.6) -----------


def place_resolution(
    block: Block, reconciliation: BlockReconciliation, corpus: Corpus
) -> Resolution:
    """Fill the wave-1 `Resolution` seam for every current row and every
    mesocycle of `reconciliation` (Req 3.7, 4.3, 4.5, 6.1-6.7, 7.1-7.6)."""
    rows: dict[str, RowResolution] = {}
    for outcome in reconciliation.rows:
        row = block.current.row(outcome.row_id)
        assert row is not None, f"row {outcome.row_id!r} is not a current row"
        rows[outcome.row_id] = RowResolution(
            cell=row_cell(outcome),
            section=row_section(block, row, outcome, corpus),
        )

    mesocycles: dict[int, MesocycleResolution] = {}
    for mesocycle in reconciliation.mesocycles:
        mesocycles[mesocycle.number] = MesocycleResolution(
            before_table=(actual_load_sentence(mesocycle),),
            after_table=_after_table_lines(mesocycle),
        )

    return Resolution(
        rows=rows,
        mesocycles=mesocycles,
        block_lines=_block_lines(reconciliation),
    )
