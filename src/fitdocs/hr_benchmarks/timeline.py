"""Build one kind's derived timeline from evidence and hand measurements."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from fitdocs.benchmarks import (
    Benchmark,
    BenchmarkKind,
    BenchmarkSet,
    BenchmarkSource,
    BenchmarkSourceKind,
)

from .types import Evidence, KindRule, Takeover


@dataclass(frozen=True)
class TimelineResult:
    entries: tuple[Benchmark, ...]
    takeovers: tuple[Takeover, ...]


def derive_timeline(
    rule: KindRule, evidence: Sequence[Evidence], recorded: Sequence[Benchmark]
) -> TimelineResult:
    entries: list[Benchmark] = []
    takeovers: list[Takeover] = []
    recorded_days: set[date] = {entry.measured_on for entry in recorded}
    run: list[Evidence] = []
    run_force: Benchmark | None = None

    def append_entry(
        first: Evidence, in_force: Benchmark | None, last: Evidence | None = None
    ) -> None:
        inputs = first.inputs
        if last is not None and rule.kind is BenchmarkKind.RESTING_HR_BPM:
            inputs += (
                "; differed from the value in force by more than "
                f"{rule.step_bpm} bpm on each day from {first.day} to {last.day}"
            )
        is_takeover = in_force is not None and in_force in recorded
        if is_takeover and in_force is not None:
            note = (
                f"Takes over from your hand-recorded {in_force.value:g} bpm of "
                f"{in_force.measured_on}: the evidence differed by "
                f"more than {rule.step_bpm} bpm."
            )
        else:
            note = f"Derived by fitdocs from {first.summary}."
        entry = Benchmark(
            kind=rule.kind,
            discipline=None,
            value=first.value,
            measured_on=first.day,
            note=note,
            applies_from=None,
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method=rule.method.value,
                document=first.document,
                inputs=inputs,
                citation=rule.citation_key,
                series=first.series,
            ),
        )
        entries.append(entry)
        if is_takeover and in_force is not None:
            takeovers.append(Takeover(rule.kind, entry, in_force))

    for candidate in evidence:
        if candidate.day in recorded_days:
            run.clear()
            continue
        in_force = BenchmarkSet((*recorded, *entries)).applicable(
            rule.kind, discipline=None, on=candidate.day
        )
        if in_force is None:
            append_entry(candidate, in_force)
            run.clear()
            continue
        if in_force in recorded and candidate.day <= in_force.measured_on:
            run.clear()
            continue
        if rule.rises_only:
            quiet = candidate.value <= in_force.value + rule.step_bpm
        else:
            quiet = abs(candidate.value - in_force.value) <= rule.step_bpm
        if quiet:
            run.clear()
            continue
        if run and (
            candidate.day != run[-1].day + timedelta(days=1)
            or candidate.key != run[-1].key
            or in_force != run_force
        ):
            run.clear()
        if not run:
            run_force = in_force
        run.append(candidate)
        if len(run) >= rule.confirm_days:
            append_entry(next(iter(run)), run_force, candidate)
            run.clear()

    return TimelineResult(tuple(entries), tuple(takeovers))
