"""Turn a sport and a date into the five anchors the threshold channels take
(design: ``BenchmarkResolution``, Req 3.3, 3.4, 3.6, 4.1, 4.2, 4.4, 4.5, 4.6).

**The only module in the threshold calculator that calls**
:meth:`ProfileView.benchmark` / :meth:`ProfileView.has_benchmark`; the
engine's own prompt flow (``load/prompts.py``) also asks ``has_benchmark``
when deciding whether a declared benchmark field is already on file. The
channels receive already-resolved :class:`~fitdocs.benchmarks.Benchmark`
objects and never see a profile (``load-channels`` Req 9.4) -- this module is
the seam.

Walks each quantity's discipline chain (:func:`~fitdocs.load.threshold.
discipline.anchor_plan`) in order and takes the first *applicable* benchmark,
asking the store for **one discipline at a time**. The store's
``BenchmarkSet.applicable``/``has`` never fall back across discipline or
scope on their own (that invariant is the store's, not this module's) -- the
cross-discipline fallback for Walk/Hike heart rate is entirely this module's
own construction, and every time it fires it is recorded on ``borrowed``,
naming both the activity's own discipline and the discipline the anchor was
actually measured under.

Absence is classified into three states a caller can act on differently:

* **borrowed** -- resolved, but from a discipline other than the activity's
  own (recorded, not an absence at all);
* **not on file** -- no benchmark of that kind/scope exists anywhere along
  the chain (``has_benchmark`` false for every discipline tried);
* **not applicable** -- at least one benchmark of that kind/scope exists
  somewhere along the chain, but none of them is dated on or before the
  activity.

The third is what lets a caller report "measured after this activity" rather
than "never measured", and what stops a prompt loop from re-asking for a
benchmark that is already on file, just not yet in force. A quantity whose
chain is empty for this sport (e.g. threshold pace for Walk) contributes
``None`` and appears in **neither** list -- it was never sought (3.5).

Maximum and resting heart rate carry no discipline at all: they are always
sought in the athlete-wide scope (``discipline=None``), matching
:data:`fitdocs.benchmarks.ATHLETE_SCOPED`, never through a chain and never
eligible for ``borrowed``.

Pure with respect to the filesystem and the clock: ``on`` is the caller's own
argument -- the activity's local calendar date sourced from
``LoadContext.activity_date`` -- and this module reads no clock and no other
date of the activity's (4.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.threshold.discipline import anchor_plan
from fitdocs.load.types import ProfileView
from fitdocs.model import Sport


@dataclass(frozen=True)
class Borrowing:
    """One quantity resolved from a discipline other than the activity's own.

    Names both disciplines explicitly rather than leaving the reader to infer
    which is which from position or context (3.4).
    """

    kind: BenchmarkKind
    activity_discipline: Sport
    anchor_discipline: Sport


@dataclass(frozen=True)
class ResolvedAnchors:
    """The five anchors a supported activity resolves to, plus the borrowing
    and absence bookkeeping the calculator and channels need (design:
    ``BenchmarkResolution`` Service Interface).

    The ``Sport`` recorded in each ``not_on_file`` / ``not_applicable`` tuple
    is always the activity's own discipline -- the scope the anchor was
    sought *for* -- never the chain entry that happened to be probed when the
    verdict was reached. For a single-entry chain (every non-empty
    ``ANCHOR_PLANS`` chain today has ``chain[0] == sport``; the five empty
    ones return before any absence branch is reached) the two coincide, but the
    invariant is chain-wide: ``not_on_file``/``not_applicable`` report
    whether the quantity is on file or applicable *anywhere along the
    chain*, recorded against the activity's discipline, not the discipline
    that produced the verdict.
    """

    ftp: Benchmark | None
    lthr: Benchmark | None
    threshold_pace: Benchmark | None
    max_hr: Benchmark | None
    resting_hr: Benchmark | None
    borrowed: tuple[Borrowing, ...]
    not_on_file: tuple[tuple[BenchmarkKind, Sport | None], ...]
    not_applicable: tuple[tuple[BenchmarkKind, Sport | None], ...]


def resolve(profile: ProfileView, *, sport: Sport, on: date) -> ResolvedAnchors:
    """Resolve every anchor a threshold-calculator channel could need for one
    activity, dated ``on`` (4.1).

    Precondition: ``sport`` is supported (see ``discipline.is_supported``) --
    :func:`~fitdocs.load.threshold.discipline.anchor_plan` raises
    ``KeyError`` otherwise, and this function does not catch it.
    """
    plan = anchor_plan(sport)
    borrowed: list[Borrowing] = []
    not_on_file: list[tuple[BenchmarkKind, Sport | None]] = []
    not_applicable: list[tuple[BenchmarkKind, Sport | None]] = []

    def resolve_discipline_scoped(
        kind: BenchmarkKind, chain: tuple[Sport, ...]
    ) -> Benchmark | None:
        if not chain:
            # Never sought for this sport -- contributes to neither list (3.5).
            return None
        any_on_file = False
        for discipline in chain:
            if not profile.has_benchmark(kind, discipline=discipline):
                continue
            any_on_file = True
            found = profile.benchmark(kind, discipline=discipline, on=on)
            if found is not None:
                if discipline != sport:
                    borrowed.append(
                        Borrowing(
                            kind=kind,
                            activity_discipline=sport,
                            anchor_discipline=discipline,
                        )
                    )
                return found
        if any_on_file:
            not_applicable.append((kind, sport))
        else:
            not_on_file.append((kind, sport))
        return None

    def resolve_athlete_scoped(kind: BenchmarkKind) -> Benchmark | None:
        if not profile.has_benchmark(kind, discipline=None):
            not_on_file.append((kind, None))
            return None
        found = profile.benchmark(kind, discipline=None, on=on)
        if found is None:
            not_applicable.append((kind, None))
        return found

    ftp = resolve_discipline_scoped(BenchmarkKind.FTP_WATTS, plan.ftp)
    lthr = resolve_discipline_scoped(BenchmarkKind.LTHR_BPM, plan.lthr)
    threshold_pace = resolve_discipline_scoped(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM, plan.threshold_pace
    )
    max_hr = resolve_athlete_scoped(BenchmarkKind.MAX_HR_BPM)
    resting_hr = resolve_athlete_scoped(BenchmarkKind.RESTING_HR_BPM)

    return ResolvedAnchors(
        ftp=ftp,
        lthr=lthr,
        threshold_pace=threshold_pace,
        max_hr=max_hr,
        resting_hr=resting_hr,
        borrowed=tuple(borrowed),
        not_on_file=tuple(not_on_file),
        not_applicable=tuple(not_applicable),
    )
