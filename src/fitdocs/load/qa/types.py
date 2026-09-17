"""The quality-flag vocabulary: check identifiers, display labels, the fixed
emission order and every tunable detection threshold (design: FlagVocabulary).

This leaf module fixes what the four quality checks are called, in what
order they are always emitted, and what a reader can tune. It holds no
arithmetic and imports nothing from ``fitdocs.load.*`` beyond the standard
library (Req 6.4, 6.9, 6.10, 6.11).

**The four checks.** :class:`FlagKey` names them: cadence lock, channel
divergence, aerobic drift and benchmark staleness (Req 1.1). :data:`FLAG_ORDER`
fixes the order they are always emitted in -- a tuple, not a set and not the
enum's declaration order by accident, because that order is user-visible in a
rendered document and is pinned by a test (Req 1.7).

**Every default is greppable at its own definition.** Each ``DEFAULT_*``
constant's docstring states what justifies it: a measurement over the
athlete's real activity corpus, a published figure, or fitdocs' own choice
where neither applies. The divergence tolerance alone rests on neither a
measurement nor a publication and is marked PROVISIONAL, naming the entry
``qa/sources.py`` will define --
``PROVISIONAL_DEFAULTS['divergence_max_intensity_delta']`` -- in a later
task (1.2), rather than being described as measured (Req 6.10, 6.11).

**No staleness window lives here.** The benchmark store already computes and
carries its own configured staleness window; introducing a second one on
:class:`FlagSettings` would let the two drift apart, so this module defines
none (Req 6.9).

This module names ``qa/sources.py`` and its ``PROVISIONAL_DEFAULTS`` registry
prospectively, in prose only -- that module does not exist yet (task 1.2) and
this module does not import it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class FlagKey(StrEnum):
    """The four quality checks this feature defines (Req 1.1). Closed --
    exactly these four, each a stable, addressable identifier that also
    doubles as the check's wire/display key."""

    CADENCE_LOCK = "cadence-lock"
    CHANNEL_DIVERGENCE = "channel-divergence"
    AEROBIC_DRIFT = "aerobic-drift"
    BENCHMARK_STALENESS = "benchmark-staleness"


FLAG_LABELS: Final[Mapping[FlagKey, str]] = {
    FlagKey.CADENCE_LOCK: "Cadence lock",
    FlagKey.CHANNEL_DIVERGENCE: "Channel divergence",
    FlagKey.AEROBIC_DRIFT: "Aerobic drift",
    FlagKey.BENCHMARK_STALENESS: "Benchmark staleness",
}
"""Total over :class:`FlagKey` -- one human-readable display label per check,
rendered into the document's training-load section (Req 1.1)."""

FLAG_ORDER: Final[tuple[FlagKey, ...]] = (
    FlagKey.CADENCE_LOCK,
    FlagKey.CHANNEL_DIVERGENCE,
    FlagKey.AEROBIC_DRIFT,
    FlagKey.BENCHMARK_STALENESS,
)
"""The fixed order every check is emitted in, independent of the activity,
the configuration, or which verdicts were reached (Req 1.7). Contains every
:class:`FlagKey` member exactly once -- asserted by test, not merely assumed
from length."""


STEPS_PER_CADENCE_REVOLUTION: Final[int] = 2
"""FIT records running cadence per limb, not per full movement cycle: steps
per minute is twice the recorded cadence value. This is an ingest semantic
this feature does not own -- it depends on how the ingest layer stores the
FIT cadence field today. Revalidation trigger: if that ingest semantic ever
changes (for example, if cadence is ever ingested already converted to full
cycles per minute), this constant must be revisited and, if the semantic no
longer applies, removed rather than silently left at 2."""

DEFAULT_CADENCE_LOCK_MIN_CORRELATION: Final[float] = 0.90
"""Measured: whole-activity Pearson r between heart rate and cadence over the
real activity corpus peaks at 0.605 across 40 assessable runs (median
0.157), so 0.90 sits well above anything a genuine effort-correlated run
produces."""

DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM: Final[float] = 5.0
"""Measured: real per-run median |HR - steps/min| spans 9-90 bpm across the
corpus, so 5.0 bpm sits below the smallest observed genuine-effort gap."""

DEFAULT_CADENCE_LOCK_WINDOW_S: Final[int] = 120
"""fitdocs' own choice, not measured or published: 120 seconds is long
enough that a span statistic reflects sustained tracking rather than a
momentary coincidence."""

DEFAULT_CADENCE_LOCK_MIN_DURATION_S: Final[int] = 300
"""Measured: the worst false-positive accumulation on the entire real
activity corpus under the conjunctive association-and-closeness rule is 137
seconds, so 300 seconds carries better than 2x headroom over that observed
worst case."""

DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE: Final[float] = 0.50
"""fitdocs' own choice, not measured or published: a check that speaks about
"the activity" needs at least half of it recorded with both channels
paired."""

DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA: Final[float] = 0.20
"""PROVISIONAL -- see ``PROVISIONAL_DEFAULTS['divergence_max_intensity_delta']``,
which task 1.2 lands in ``qa/sources.py``. Neither published nor measured: no
activity in the measured real corpus computed two channels' values at once,
so there is no agreement distribution to set a tolerance against. The value
was originally chosen against a heart-rate intensity scale that has since
been corrected (`load-channels` Requirement 1.11); it is carried forward
under the corrected shared intensity semantic as a stated judgment call, not
a measurement, pending the corpus growing an activity for which two channels
both compute (Req 6.10, 6.11)."""

DEFAULT_AEROBIC_DRIFT_MAX_PCT: Final[float] = 5.0
"""TrainingPeaks-published: the published figure below which an activity is
conventionally described as well-coupled."""


@dataclass(frozen=True)
class FlagSettings:
    """The seven tunable detection thresholds this feature reads from
    ``[load.flags]``, each defaulting to its documented module constant.
    Construction validates nothing -- consistent with the shipped settings
    value types elsewhere in this package, validation is the settings
    reader's job (task 1.3), not this dataclass's (Req 6.4).

    Carries no staleness window: the benchmark store's own configured window
    is the only one this feature uses (Req 6.9)."""

    cadence_lock_min_correlation: float = DEFAULT_CADENCE_LOCK_MIN_CORRELATION
    cadence_lock_max_delta_bpm: float = DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM
    cadence_lock_window_s: int = DEFAULT_CADENCE_LOCK_WINDOW_S
    cadence_lock_min_duration_s: int = DEFAULT_CADENCE_LOCK_MIN_DURATION_S
    cadence_lock_min_paired_coverage: float = DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE
    divergence_max_intensity_delta: float = DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA
    aerobic_drift_max_pct: float = DEFAULT_AEROBIC_DRIFT_MAX_PCT
