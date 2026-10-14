"""Immutable vocabulary and values for the heart-rate stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.model import Sport

HR_KINDS: Final[frozenset[BenchmarkKind]] = frozenset(
    {BenchmarkKind.RESTING_HR_BPM, BenchmarkKind.MAX_HR_BPM}
)


class HrMethod(StrEnum):
    RESTING_HR_SERIES_MEDIAN = "resting_hr_series_median"
    MAX_HR_SUSTAINED_PEAK = "max_hr_sustained_peak"


@dataclass(frozen=True)
class SessionPeak:
    day: date
    document: str
    peak_bpm: float


class NoEvidenceReason(StrEnum):
    UNDATED = "undated"
    ARCHIVE_MISSING = "archive_missing"
    ARCHIVE_UNDECODABLE = "archive_undecodable"
    NO_HEART_RATE = "no_heart_rate"
    CADENCE_LOCKED = "cadence_locked"
    NO_SUSTAINED_STRETCH = "no_sustained_stretch"


@dataclass(frozen=True)
class Evidence:
    day: date
    value: int
    key: str
    document: str
    series: str | None
    inputs: str
    summary: str


@dataclass(frozen=True)
class KindRule:
    kind: BenchmarkKind
    method: HrMethod
    citation_key: str
    step_bpm: int
    confirm_days: int


@dataclass(frozen=True)
class Takeover:
    kind: BenchmarkKind
    derived: Benchmark
    superseded: Benchmark


@dataclass(frozen=True)
class BackReach:
    kind: BenchmarkKind
    entry: Benchmark
    starts_on: date
    ends_before: date


@dataclass(frozen=True)
class BackReachChange:
    kind: BenchmarkKind
    entry: Benchmark
    before: tuple[date, date]
    after: tuple[date, date]


class Violation(StrEnum):
    MAX_NOT_ABOVE_REST = "max_not_above_rest"
    THRESHOLD_OUTSIDE_RESERVE = "threshold_outside_reserve"


@dataclass(frozen=True)
class Inconsistency:
    violation: Violation
    starts_on: date
    ends_before: date | None
    discipline: Sport | None
    max_hr: Benchmark
    resting_hr: Benchmark
    lthr: Benchmark | None


@dataclass(frozen=True)
class SkippedDocument:
    document: str
    reason: NoEvidenceReason
    detail: str


@dataclass(frozen=True)
class HrFailure:
    kind: BenchmarkKind
    subject: str
    reason: str


@dataclass(frozen=True)
class KindOutcome:
    kind: BenchmarkKind
    entries: tuple[Benchmark, ...]
    added: tuple[Benchmark, ...]
    removed: tuple[Benchmark, ...]
    kept: bool


@dataclass(frozen=True)
class HrStageReport:
    considered: int
    with_evidence: int
    no_evidence: tuple[tuple[NoEvidenceReason, int], ...]
    skipped: tuple[SkippedDocument, ...]
    resting_sources: tuple[str, ...]
    kinds: tuple[KindOutcome, ...]
    takeovers: tuple[Takeover, ...]
    back_reach_changes: tuple[BackReachChange, ...]
    inconsistencies: tuple[Inconsistency, ...]
    failures: tuple[HrFailure, ...]
    notes: tuple[str, ...]
    written: bool
    changed: bool
