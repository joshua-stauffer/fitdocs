"""The closed vocabularies and the two outcome values every other component
in :mod:`fitdocs.performance` speaks in (design: PerformanceTypes, Req 5.10,
7.3, 7.4).

Holds no arithmetic, no I/O and no citation record. `DeclineReason` includes,
by identical string value, every :class:`~fitdocs.load.channels.types.
InsufficiencyReason` member ``sufficiency.evaluate`` can actually return --
``TOO_SHORT``, ``STREAM_ABSENT``, ``STREAM_COVERAGE`` -- so a stream decline
reads identically in both this pass's report and the training-load pass's
(Req 7.4). :meth:`DeclineReason.from_insufficiency` is exhaustively decided
rather than total: it maps those three by identical value and raises
``ValueError`` for every other ``InsufficiencyReason`` member (``NO_BENCHMARK``,
``BENCHMARKS_INCONSISTENT``, ``MODEL_NOT_DEFINED``, ``NOT_COMPUTABLE``) --
verdicts the sufficiency gate never produces for this pass -- because
inventing a decline reason for a verdict that cannot arrive would fabricate
an outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.channels.types import InsufficiencyReason


class DerivationMethod(StrEnum):
    """The closed method-name vocabulary this feature writes. Deliberately
    not owned by the benchmark store: the store validates a provenance
    record's shape and origin class, not the method name it carries (Req
    5.10), so this vocabulary can grow without changing the store."""

    RIEGEL_RACE_EQUIVALENCE = "riegel_race_equivalence"
    SUSTAINED_EFFORT_MEAN_HR = "sustained_effort_mean_hr"
    TIME_TRIAL_MEAN_POWER = "time_trial_mean_power"
    TWENTY_MINUTE_POWER_FACTOR = "twenty_minute_power_factor"


class DeclineReason(StrEnum):
    """The closed, published vocabulary a declined derivation's reason is
    drawn from (Req 7.3). The three stream-condition members carry
    ``InsufficiencyReason``'s own string values so a stream decline reads
    identically in both reports (Req 7.4)."""

    SPORT_NOT_COVERED = "sport_not_covered"
    EFFORT_KIND_NOT_USED = "effort_kind_not_used"
    UNDATED_DOCUMENT = "undated_document"
    MISSING_INPUT = "missing_input"
    OUTSIDE_VALIDITY_WINDOW = "outside_validity_window"
    EFFORT_SPAN_MISMATCH = "effort_span_mismatch"
    METHOD_UNVERIFIED = "method_unverified"
    SUPERSEDED_BY_RECORDED = "superseded_by_recorded"
    STREAM_ABSENT = "stream_absent"
    STREAM_COVERAGE = "stream_coverage"
    TOO_SHORT = "too_short"

    @classmethod
    def from_insufficiency(cls, reason: InsufficiencyReason) -> DeclineReason:
        """The three verdicts ``sufficiency.evaluate`` can actually return,
        mapped by identical string value. Every other ``InsufficiencyReason``
        member raises ``ValueError`` -- a programming error, since the gate
        never produces one of those verdicts for this pass -- rather than
        being silently coerced into a fabricated reason."""
        if reason is InsufficiencyReason.STREAM_ABSENT:
            return cls.STREAM_ABSENT
        if reason is InsufficiencyReason.STREAM_COVERAGE:
            return cls.STREAM_COVERAGE
        if reason is InsufficiencyReason.TOO_SHORT:
            return cls.TOO_SHORT
        raise ValueError(
            f"InsufficiencyReason.{reason.name} cannot arrive at this pass "
            "and has no corresponding DeclineReason"
        )


@dataclass(frozen=True)
class DerivedBenchmark:
    """A successfully derived, dated benchmark value with its full
    provenance (Req 5.2, 7.2)."""

    kind: BenchmarkKind
    discipline: Sport
    value: float
    measured_on: date
    method: DerivationMethod
    citation_key: str
    inputs: str
    note: str
    document: str  # data-root-relative POSIX path


@dataclass(frozen=True)
class DerivationDeclined:
    """A refused derivation, carrying a reason from the closed vocabulary
    rather than a fabricated zero (Req 7.3)."""

    kind: BenchmarkKind
    method: DerivationMethod | None
    reason: DeclineReason
    detail: str
    observed: float | None = None
    required: float | None = None


DerivationOutcome = DerivedBenchmark | DerivationDeclined
