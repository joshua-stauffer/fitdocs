"""Pure structural inspection of dated heart-rate benchmarks."""

from dataclasses import replace
from datetime import date
from itertools import pairwise

from fitdocs.benchmarks import Benchmark, BenchmarkKind, BenchmarkSet
from fitdocs.model import Sport

from .types import HR_KINDS, BackReach, Inconsistency, Takeover, Violation


def _is_derived(entry: Benchmark) -> bool:
    return entry.source is not None and entry.source.is_derived


def _breakpoints(
    benchmarks: BenchmarkSet, kinds: frozenset[BenchmarkKind]
) -> list[date]:
    return sorted(
        {
            day
            for entry in benchmarks.entries
            if entry.kind in kinds
            for day in (entry.measured_on, entry.applies_from)
            if day is not None
        }
    )


def takeovers(benchmarks: BenchmarkSet) -> tuple[Takeover, ...]:
    found: list[Takeover] = []
    for derived in benchmarks.entries:
        if derived.kind not in HR_KINDS or not _is_derived(derived):
            continue
        without = BenchmarkSet(tuple(e for e in benchmarks.entries if e is not derived))
        hand = without.applicable(derived.kind, discipline=None, on=derived.measured_on)
        if hand is not None and not _is_derived(hand):
            found.append(Takeover(derived.kind, derived, hand))
    return tuple(sorted(found, key=lambda t: (t.kind.value, t.derived.measured_on)))


def current_takeovers(benchmarks: BenchmarkSet) -> tuple[Takeover, ...]:
    return tuple(
        takeover
        for takeover in takeovers(benchmarks)
        if takeover.derived.measured_on
        == max(e.measured_on for e in benchmarks.entries if e.kind is takeover.kind)
    )


def back_reach_cover(benchmarks: BenchmarkSet) -> tuple[BackReach, ...]:
    found: list[BackReach] = []
    for hand in sorted(benchmarks.entries, key=lambda e: (e.kind.value, e.measured_on)):
        if hand.kind not in HR_KINDS or _is_derived(hand) or hand.applies_from is None:
            continue
        periods = [
            (start, end)
            for start, end in pairwise(_breakpoints(benchmarks, frozenset({hand.kind})))
            if start < hand.measured_on
            and benchmarks.applicable(hand.kind, discipline=None, on=start) == hand
        ]
        first = next(iter(periods), None)
        if first is None:
            start = end = hand.applies_from
        else:
            start, _ = first
            _, end = next(reversed(periods))
        found.append(BackReach(hand.kind, hand, start, end))
    return tuple(found)


def inconsistencies(benchmarks: BenchmarkSet) -> tuple[Inconsistency, ...]:
    kinds = HR_KINDS | {BenchmarkKind.LTHR_BPM}
    breaks = _breakpoints(benchmarks, frozenset(kinds))
    disciplines = {
        entry.discipline
        for entry in benchmarks.entries
        if entry.kind is BenchmarkKind.LTHR_BPM and entry.discipline is not None
    }
    grouped: dict[
        tuple[Violation, Sport | None, Benchmark, Benchmark, Benchmark | None],
        list[Inconsistency],
    ] = {}

    def add(finding: Inconsistency) -> None:
        key = (
            finding.violation,
            finding.discipline,
            finding.max_hr,
            finding.resting_hr,
            finding.lthr,
        )
        periods = grouped.setdefault(key, [])
        previous = next(reversed(periods), None)
        if previous is not None and previous.ends_before == finding.starts_on:
            periods.pop()
            periods.append(replace(previous, ends_before=finding.ends_before))
        else:
            periods.append(finding)

    for start, end in pairwise([*breaks, None]):
        if start is None:
            continue
        mx = benchmarks.applicable(BenchmarkKind.MAX_HR_BPM, discipline=None, on=start)
        rs = benchmarks.applicable(
            BenchmarkKind.RESTING_HR_BPM, discipline=None, on=start
        )
        if mx is None or rs is None or not (_is_derived(mx) or _is_derived(rs)):
            continue
        if mx.value <= rs.value:
            add(
                Inconsistency(
                    Violation.MAX_NOT_ABOVE_REST, start, end, None, mx, rs, None
                )
            )
        else:
            for discipline in disciplines:
                lt = benchmarks.applicable(
                    BenchmarkKind.LTHR_BPM, discipline=discipline, on=start
                )
                if lt is not None and not rs.value < lt.value <= mx.value:
                    add(
                        Inconsistency(
                            Violation.THRESHOLD_OUTSIDE_RESERVE,
                            start,
                            end,
                            discipline,
                            mx,
                            rs,
                            lt,
                        )
                    )
    return tuple(
        sorted(
            (period for periods in grouped.values() for period in periods),
            key=lambda p: (
                p.starts_on,
                p.violation.value,
                p.discipline.value if p.discipline is not None else "",
            ),
        )
    )
