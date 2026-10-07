"""Project athlete-profile benchmark entries and their in-force periods."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from fitdocs import Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind, BenchmarkSet
from fitdocs.index.derived.inputs import digest, file_digest
from fitdocs.index.producer import CorpusSnapshot, Rows
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.load.profile import PROFILE_FILENAME, load_profile

UNIT_TOKENS: Final[Mapping[BenchmarkKind, str]] = {
    BenchmarkKind.FTP_WATTS: "w",
    BenchmarkKind.LTHR_BPM: "bpm",
    BenchmarkKind.THRESHOLD_PACE_S_PER_KM: "s_per_km",
    BenchmarkKind.MAX_HR_BPM: "bpm",
    BenchmarkKind.RESTING_HR_BPM: "bpm",
}

BENCHMARKS_TABLE: Final[TableSpec] = TableSpec(
    name="benchmarks",
    description=(
        "One row per benchmark entry in athlete.toml. Equals the athlete "
        "profile's own reading of athlete.toml (the reading fitdocs "
        "derive-benchmarks and the training-load pass use), for the inputs "
        "as of the last refresh."
    ),
    columns=(
        ColumnSpec(
            "kind", ColumnType.VARCHAR, "Benchmark kind recorded in athlete.toml."
        ),
        ColumnSpec(
            "discipline",
            ColumnType.VARCHAR,
            "Sport scope; NULL for athlete-wide benchmarks.",
        ),
        ColumnSpec(
            "value",
            ColumnType.DOUBLE,
            "Recorded value in the unit named by unit; never converted.",
        ),
        ColumnSpec("unit", ColumnType.VARCHAR, "Unit token for the benchmark kind."),
        ColumnSpec(
            "measured_on", ColumnType.DATE, "Calendar day the benchmark was measured."
        ),
        ColumnSpec(
            "applies_from",
            ColumnType.DATE,
            "Calendar day the entry applies from; NULL when not recorded.",
        ),
        ColumnSpec(
            "source_kind",
            ColumnType.VARCHAR,
            "Whether the source is derived or measured; NULL when absent.",
        ),
        ColumnSpec(
            "source_method",
            ColumnType.VARCHAR,
            "Derivation method; NULL when not recorded.",
        ),
        ColumnSpec(
            "source_page",
            ColumnType.VARCHAR,
            "Data-root-relative page used to derive the entry; NULL when not recorded.",
        ),
        ColumnSpec(
            "source_citation",
            ColumnType.VARCHAR,
            "Citation key for a derived entry; NULL when not recorded.",
        ),
    ),
)

BENCHMARK_PERIODS_TABLE: Final[TableSpec] = TableSpec(
    name="benchmark_periods",
    description=(
        "One row per period during which one benchmark entry is in force for "
        "its kind and discipline. Equals the athlete profile's own in-force "
        "rule (the rule the training-load pass applies before its "
        "cross-discipline borrowing), for the inputs as of the last refresh. "
        "Per discipline as recorded: no cross-discipline borrowing."
    ),
    columns=(
        ColumnSpec("kind", ColumnType.VARCHAR, "Benchmark kind in force."),
        ColumnSpec(
            "discipline",
            ColumnType.VARCHAR,
            "Recorded sport scope; NULL for athlete-wide benchmarks.",
        ),
        ColumnSpec(
            "starts_on", ColumnType.DATE, "First calendar day the entry is in force."
        ),
        ColumnSpec(
            "ends_before",
            ColumnType.DATE,
            "First calendar day the entry is no longer in force; "
            "NULL while still in force.",
        ),
        ColumnSpec(
            "value",
            ColumnType.DOUBLE,
            "Recorded value in the unit named by unit; never converted.",
        ),
        ColumnSpec("unit", ColumnType.VARCHAR, "Unit token for the benchmark kind."),
        ColumnSpec(
            "measured_on",
            ColumnType.DATE,
            "Calendar day the in-force entry was measured.",
        ),
        ColumnSpec(
            "retroactive",
            ColumnType.BOOLEAN,
            "Whether this period precedes the entry's measured day.",
        ),
    ),
)


@dataclass(frozen=True)
class InForcePeriod:
    """An uninterrupted date range selecting one benchmark entry."""

    kind: BenchmarkKind
    discipline: Sport | None
    starts_on: date
    ends_before: date | None
    entry: Benchmark
    retroactive: bool


def in_force_periods(benchmarks: BenchmarkSet) -> tuple[InForcePeriod, ...]:
    """Return the intervals selected by the profile's applicability rule."""
    groups: list[tuple[BenchmarkKind, Sport | None]] = []
    for entry in benchmarks.entries:
        group = (entry.kind, entry.discipline)
        if group not in groups:
            groups.append(group)

    result: list[InForcePeriod] = []
    for kind, discipline in groups:
        entries = tuple(
            entry
            for entry in benchmarks.entries
            if entry.kind is kind and entry.discipline == discipline
        )
        breakpoints = sorted(
            {
                point
                for entry in entries
                for point in (entry.measured_on, entry.applies_from)
                if point is not None
            }
        )
        current: tuple[Benchmark, bool] | None = None
        starts_on: date | None = None
        for point in breakpoints:
            selected_entry = benchmarks.applicable(
                kind, discipline=discipline, on=point
            )
            selected: tuple[Benchmark, bool] | None = (
                (selected_entry, point < selected_entry.measured_on)
                if selected_entry is not None
                else None
            )
            if selected == current:
                continue
            if current is not None and starts_on is not None:
                result.append(
                    InForcePeriod(
                        kind=kind,
                        discipline=discipline,
                        starts_on=starts_on,
                        ends_before=point,
                        entry=current[0],
                        retroactive=current[1],
                    )
                )
            current = selected
            starts_on = point if selected is not None else None
        if current is not None and starts_on is not None:
            result.append(
                InForcePeriod(
                    kind=kind,
                    discipline=discipline,
                    starts_on=starts_on,
                    ends_before=None,
                    entry=current[0],
                    retroactive=current[1],
                )
            )
    return tuple(result)


@dataclass(frozen=True)
class BenchmarkProducer:
    """Expose profile entries and date intervals as corpus-level tables."""

    name: str = "derived.benchmarks"
    tables: tuple[TableSpec, ...] = (BENCHMARKS_TABLE, BENCHMARK_PERIODS_TABLE)

    def fingerprint(self, corpus: CorpusSnapshot) -> str:
        return digest({"profile": file_digest(corpus.data_root / PROFILE_FILENAME)})

    def rows(self, corpus: CorpusSnapshot) -> Rows:
        profile = load_profile(corpus.data_root)
        benchmarks = tuple(
            (
                entry.kind.value,
                entry.discipline.value if entry.discipline is not None else None,
                float(entry.value),
                UNIT_TOKENS[entry.kind],
                entry.measured_on,
                entry.applies_from,
                entry.source.kind.value if entry.source is not None else None,
                entry.source.method if entry.source is not None else None,
                entry.source.document if entry.source is not None else None,
                entry.source.citation if entry.source is not None else None,
            )
            for entry in profile.benchmarks.entries
        )
        periods = tuple(
            (
                period.kind.value,
                period.discipline.value if period.discipline is not None else None,
                period.starts_on,
                period.ends_before,
                float(period.entry.value),
                UNIT_TOKENS[period.kind],
                period.entry.measured_on,
                period.retroactive,
            )
            for period in in_force_periods(profile.benchmarks)
        )
        return {"benchmarks": benchmarks, "benchmark_periods": periods}


BENCHMARK_PRODUCER: Final[BenchmarkProducer] = BenchmarkProducer()
