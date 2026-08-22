"""The channel result vocabulary and the sufficiency value (design:
ChannelVocabulary).

This leaf module owns three things and nothing else:

1. **The result vocabulary.** :class:`ChannelId` names the three channels;
   :class:`InsufficiencyReason` is the closed set of reasons a channel can
   fail to produce an honest number; :class:`ChannelLoad` and
   :class:`ChannelInsufficient` are the two possible outcomes, combined into
   the closed, two-variant :data:`ChannelOutcome` union with no third state
   (Req 1.1-1.5). :class:`StreamCoverage` carries a stream's measured
   coverage with its fraction derived, never stored (Req 2.7).
2. **The shared intensity semantic**, stated once on
   :attr:`ChannelLoad.intensity`'s own docstring and nowhere else in this
   package (Req 1.11). Every channel this feature adds later is written to
   satisfy that definition rather than to invent its own; the heart-rate
   channel reports the square root of its impulse ratio specifically so it
   holds on all three (task 3.2).
3. **The resolved sufficiency configuration and its one gating guard.**
   :class:`SufficiencySettings` is a plain, frozen value -- the *reading* of
   it from the settings file lives in ``load/settings.py``, outside this
   package, so no module under ``fitdocs/load/channels/`` imports it or any
   other settings machinery (Req 3.9). :func:`require_kind` is the guard
   every channel calls before anchoring on a caller-supplied benchmark: a
   benchmark of the wrong quantity is a programming error, not something to
   compute from (Req 1.9).

Holds no arithmetic beyond ``StreamCoverage.fraction`` and
``SufficiencySettings.minimum_for`` -- both pure projections of already-held
fields, not derived measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from fitdocs.benchmarks import Benchmark, BenchmarkKind


class ChannelId(StrEnum):
    """The three training-load channels this feature computes (Req 1.1).
    Closed -- exactly these three, each a stable, addressable identifier."""

    POWER = "power"
    HEART_RATE = "heart_rate"
    PACE = "pace"


class InsufficiencyReason(StrEnum):
    """The closed set of reasons a channel can decline to compute a load
    (Req 1.5). Distinguishes at least: no applicable anchoring benchmark;
    anchoring benchmarks that are individually valid but mutually
    inconsistent; a required stream that records no value at all; a required
    stream whose coverage is below the configured minimum; an activity
    shorter than the configured minimum duration; a channel model not
    defined for the activity's modality; and a required derived value that
    could not be computed from the data present.

    Only :data:`STREAM_COVERAGE` and :data:`TOO_SHORT` are the two
    "threshold reasons" that carry ``observed``/``required`` on
    :class:`ChannelInsufficient` (Req 1.4)."""

    NO_BENCHMARK = "no_benchmark"
    BENCHMARKS_INCONSISTENT = "benchmarks_inconsistent"
    STREAM_ABSENT = "stream_absent"
    STREAM_COVERAGE = "stream_coverage"
    TOO_SHORT = "too_short"
    MODEL_NOT_DEFINED = "model_not_defined"
    NOT_COMPUTABLE = "not_computable"


@dataclass(frozen=True)
class StreamCoverage:
    """The measured coverage of one stream over an activity's recorded span.

    ``fraction`` is derived, never stored (Req 2.7): a caller that wants the
    ratio always gets it computed fresh from ``covered_s`` and ``total_s``,
    so the two can never silently drift apart. The gate that produces this
    value never constructs one with ``total_s <= 0`` -- a span of zero or
    fewer than two samples is insufficiency, not a degenerate coverage.
    """

    stream: str
    covered_s: float
    total_s: float

    @property
    def fraction(self) -> float:
        return self.covered_s / self.total_s


@dataclass(frozen=True)
class ChannelLoad:
    """A channel's computed result (Req 1.3).

    Carries the channel identifier, the load value, the intensity ratio
    relative to threshold, the anchoring benchmark, the scored duration, the
    measured stream coverage, the ordered inputs that produced the value,
    and any notes. Every field but ``notes`` is required -- nothing lets a
    channel construct one of these while omitting ``coverage`` or
    ``scored_duration_s``, which is the structural guarantee behind Req 2.7
    ("the gate passing still reports coverage and duration").
    """

    channel: ChannelId
    load: float
    intensity: float
    """Threshold-relative effort, dimensionless, exactly 1.0 at threshold.

    ONE semantic for all three channels, stated here and nowhere else:

        load == (scored_duration_s / 3600) * intensity ** 2 * 100

    Power reports ``np / ftp``, pace reports ``gap_speed / threshold_speed``,
    and heart rate reports the *square root* of its impulse ratio precisely
    so that this relation holds identically on all three (Req 1.11, and task
    3.2 for the heart-rate channel's square root).
    """
    anchor: Benchmark
    scored_duration_s: float
    coverage: StreamCoverage
    inputs_used: tuple[tuple[str, str], ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChannelInsufficient:
    """A channel's typed statement of why no honest load exists (Req 1.4).

    Carries the channel identifier, a reason drawn from the closed
    :class:`InsufficiencyReason` set, a human-readable explanation, and --
    for exactly the two threshold reasons (:data:`InsufficiencyReason.
    STREAM_COVERAGE`, :data:`InsufficiencyReason.TOO_SHORT`) -- the observed
    value and the value that was required. ``observed`` and ``required``
    default to ``None`` and are left unset for every other reason.
    """

    channel: ChannelId
    reason: InsufficiencyReason
    detail: str
    observed: float | None = None
    required: float | None = None


ChannelOutcome = ChannelLoad | ChannelInsufficient
"""A channel's result: exactly one of a computed load or a typed
insufficiency (Req 1.2). Closed, two-variant, and folded exhaustively
downstream in the same ``assert_never`` style the shipped ``LoadOutcome``
already uses -- there is no third state and no "computed but unreliable"
variant."""


DEFAULT_MIN_STREAM_COVERAGE: Final[float] = 0.80
"""The documented default minimum stream coverage (Req 3.3, 3.10). Matches
the published, citable coverage requirement TrainingPeaks states for
power-based TSS -- see ``TRAININGPEAKS_COVERAGE_GATE`` in ``sources.py``.
That source's own text supports the figure only for the bike/power case;
applying it as a single cross-channel default across power, heart-rate and
pace is fitdocs' own scope decision, recorded on the citation itself rather
than overstated here."""

DEFAULT_MIN_DURATION_S: Final[int] = 60
"""The documented default minimum activity duration (Req 3.3). This one is
fitdocs' own, not a published figure: 60 s is twice the 30 s rolling window
the shipped normalized-power algorithm needs, the longest window any
channel's inputs require."""


@dataclass(frozen=True)
class SufficiencySettings:
    """The resolved data-sufficiency configuration (Req 3.2, 3.3, 3.9).

    A plain, frozen value -- *reading* one of these from the settings file is
    ``load/settings.py``'s job, outside this package, so no channel or
    sufficiency-gate module here ever reads, locates, or re-reads a settings
    file itself (Req 3.9). Carries one shared minimum coverage, one shared
    minimum duration, and an optional per-channel coverage override that
    resolves to the shared minimum when unset (Req 3.2).
    """

    min_duration_s: int = DEFAULT_MIN_DURATION_S
    min_stream_coverage: float = DEFAULT_MIN_STREAM_COVERAGE
    power_min_stream_coverage: float | None = None
    hr_min_stream_coverage: float | None = None
    pace_min_stream_coverage: float | None = None

    def minimum_for(self, channel: ChannelId) -> float:
        """The minimum stream coverage that applies to ``channel``: its own
        override when one is set, the shared minimum otherwise (Req 3.2)."""
        override = {
            ChannelId.POWER: self.power_min_stream_coverage,
            ChannelId.HEART_RATE: self.hr_min_stream_coverage,
            ChannelId.PACE: self.pace_min_stream_coverage,
        }[channel]
        return override if override is not None else self.min_stream_coverage


def require_kind(benchmark: Benchmark, expected: BenchmarkKind) -> None:
    """Guard against a caller anchoring a channel on a benchmark of the
    wrong quantity (Req 1.9).

    Every channel calls this before computing from a caller-supplied
    benchmark. A mismatch is a programming error, not something to compute
    a value from -- it fails loudly with both the benchmark's actual kind
    and the kind the channel expects named in the message, rather than
    silently producing a wrong number.
    """
    if benchmark.kind is not expected:
        raise ValueError(
            f"wrong benchmark quantity: expected {expected.value!r}, "
            f"got {benchmark.kind.value!r}"
        )
