"""Benchmark-staleness surfacing for the selected channel's anchor (design:
StalenessSurfacing, `src/fitdocs/load/qa/staleness.py`).

**Surfaces, never computes.** The age, the window and the stale-or-current
verdict all come from `fitdocs.benchmarks.benchmark_age`; this module
contributes routing only, no arithmetic of its own (Req 5.2). It does not
re-decide whether an anchor applies to the activity -- that is the store's
own two-tier selection, already resolved by the time a `ChannelLoad` exists.

**No pre-call ordering guard.** An earlier revision of this task checked
``measured_on <= activity_date`` before calling `benchmark_age` and reported
a violation as *not-assessed*, on the premise that the store *raised* for
that ordering. `athlete-benchmarks` Amendment 1 retired that premise:
`benchmark_age` no longer raises when the benchmark was measured after the
activity -- it returns a negative ``age_days`` -- and selection yields such
an anchor only when the athlete declared it, via `Benchmark.applies_from`,
to apply retroactively. The guard is gone; every input this module can be
handed reaches `benchmark_age` unconditionally once an activity date exists
(design: "No pre-call ordering guard"; Req 5.8).

**A negative age is its own outcome, `RETROACTIVE`.** It is never `STALE`
(arithmetically impossible: a negative age never exceeds a positive window)
and never `NOT_ASSESSED` (the check ran to completion) -- it is read from
the sign of `BenchmarkAge.age_days` as the store's own signal, and the
reading carries the anchor so a later basis can state the athlete's
``applies_from`` beside ``measured_on`` (Req 5.8). A `RETROACTIVE` reading
whose anchor carries no ``applies_from`` (structurally unreachable through
the store's own contract, but not enforced by this module) still reaches
`RETROACTIVE`, never a raise and never `NOT_ASSESSED` -- the age is what it
is (Req 1.8, 1.10).

**Requirement 5.5, precisely.** "Computed without an anchoring benchmark
carrying a measurement date" has exactly one *reachable* instance -- an
activity with no calendar date -- because `ChannelLoad.anchor` is a
non-optional `Benchmark` and `Benchmark.measured_on` is a non-optional
`date`. `StalenessReading.anchor` is therefore non-optional too: the
structural unreachability of an absent anchor is recorded at the type
rather than defended by a branch that could never run.

**Never raises, no clock, no second window** (Req 1.10, 5.4, 5.6, 5.7): the
reading is a pure function of ``selected``, ``activity_date`` and
``window_days`` alone. The `Benchmark` is carried by reference and never
modified. This module defines no staleness-window constant of its own --
the caller's ``window_days`` is used exactly as passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from fitdocs.benchmarks import Benchmark, BenchmarkAge, benchmark_age
from fitdocs.load.channels.types import ChannelLoad


class StalenessOutcome(StrEnum):
    """The four-value outcome this check can reach (Req 5.3, 5.5, 5.8).
    Closed -- exactly these four."""

    STALE = "stale"
    CURRENT = "current"
    RETROACTIVE = "retroactive"
    """Measured after the activity; applied by the athlete's declaration
    (Req 5.8). Distinct from `STALE`, `CURRENT` and `NOT_ASSESSED`."""
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class StalenessReading:
    """This check's own typed result, before `FlagAssembly` maps it onto the
    contract's three-value verdict vocabulary.

    ``anchor`` is never ``None`` -- the selected channel always carries one
    (Req 5.1, 5.5). ``age`` is populated for every outcome except
    `StalenessOutcome.NOT_ASSESSED`, where there is no figure to report
    (Req 1.5, 1.8). ``not_assessed_reason`` is populated only for
    `StalenessOutcome.NOT_ASSESSED`.
    """

    outcome: StalenessOutcome
    anchor: Benchmark
    age: BenchmarkAge | None
    not_assessed_reason: str | None


def evaluate(
    selected: ChannelLoad,
    *,
    activity_date: date | None,
    window_days: int,
) -> StalenessReading:
    """Turn the selected channel's anchor into a staleness reading (Req
    5.1-5.8).

    **Gate order, exactly**:

    1. ``activity_date is None`` -> `StalenessOutcome.NOT_ASSESSED`, naming
       the absent calendar date -- the sole reachable *not-assessed* path
       (Req 5.5).
    2. Otherwise, call `benchmark_age` unconditionally -- no ordering check
       against ``selected.anchor.measured_on`` runs first (Req 5.8) -- and
       read its result in one place: ``age.age_days < 0`` ->
       `StalenessOutcome.RETROACTIVE`; else ``age.is_stale`` ->
       `StalenessOutcome.STALE`; else `StalenessOutcome.CURRENT` (Req 5.3,
       5.8).

    Every reached reading carries ``selected.anchor`` unmodified (Req 5.6)
    and, when not *not-assessed*, the `BenchmarkAge` `benchmark_age`
    computed. ``window_days`` is threaded straight into `benchmark_age`,
    never re-read from a constant or a second default (Req 5.7). Pure: no
    clock is consulted, so the verdict depends only on the three arguments
    and reproduces identically for a past activity regenerated later (Req
    5.4).
    """
    anchor = selected.anchor

    if activity_date is None:
        return StalenessReading(
            outcome=StalenessOutcome.NOT_ASSESSED,
            anchor=anchor,
            age=None,
            not_assessed_reason=(
                "the activity carries no calendar date to evaluate the "
                "anchoring benchmark's age against"
            ),
        )

    age = benchmark_age(
        activity_date=activity_date,
        measured_on=anchor.measured_on,
        window_days=window_days,
    )

    if age.age_days < 0:
        outcome = StalenessOutcome.RETROACTIVE
    elif age.is_stale:
        outcome = StalenessOutcome.STALE
    else:
        outcome = StalenessOutcome.CURRENT

    return StalenessReading(
        outcome=outcome,
        anchor=anchor,
        age=age,
        not_assessed_reason=None,
    )
