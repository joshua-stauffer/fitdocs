"""The threshold calculator's own :class:`~fitdocs.load.types.LoadCalculator`
implementation (design: ``ThresholdCalculator``).

This task (3.1, ``AthleteFieldDeclaration``, Req 9.1-9.3) lands only the
static athlete-input declaration: the seven benchmarks the shipped prompt
flow must collect to score the supported disciplines. ``supports`` (3.3) and
``compute`` (3.2, 3.3) are added to this same class by later tasks under
their own component boundaries -- this file is deliberately left extendable
rather than stubbed for them.

Each declared field carries a :class:`~fitdocs.load.types.BenchmarkRef`, so
the generic prompt flow persists the athlete's answer as a dated measurement
in the ``benchmarks.<scope>.<kind>`` table (Req 9.1) rather than as a flat
profile value. Declaration is static -- ``required_athlete_fields`` takes no
activity -- which is a known, deliberately deferred limitation: a runner
with no bicycle is still asked for a cycling FTP on every interactive pass.
The fix is contract-level (an activity-aware declaration or a persisted
decline marker) and belongs to ``training-load`` / ``athlete-benchmarks``,
not to this calculator (design.md, ``AthleteFieldDeclaration`` Implementation
Notes).

Walk and Hike threshold heart rate are deliberately **not** declared (Req
9.2): ``discipline.ANCHOR_PLANS`` already lets a Walk or Hike heart-rate
channel fall back to the athlete's Running LTHR, so -- when that Running LTHR
is on file with an entry dated at or before the activity -- a dedicated
Walk/Hike LTHR benchmark would only ever be an optional *refinement* of an
anchor the chain already resolves (design.md, ``AthleteFieldDeclaration``).
The declared set below is exactly the union, over every supported sport and
quantity, of the last (guaranteed-to-resolve) entry in each non-empty anchor
chain, plus the two athlete-wide heart-rate quantities that carry no
discipline and so appear in no chain at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.types import AthleteField, BenchmarkRef
from fitdocs.model import Sport

__all__ = [
    "ATHLETE_FIELDS",
    "ThresholdCalculator",
]

_RUN_FTP: Final[AthleteField] = AthleteField(
    key="benchmarks.run.ftp_watts",
    label="Running FTP (W)",
    kind="int",
    minimum=50,
    maximum=600,
    help_text=(
        "Running functional threshold power in watts: the highest power "
        "output you can sustain for about an hour of running, typically "
        "measured with a foot pod or running-power device over a 20-60 "
        "minute time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RUN),
)

_RIDE_FTP: Final[AthleteField] = AthleteField(
    key="benchmarks.ride.ftp_watts",
    label="Cycling FTP (W)",
    kind="int",
    minimum=50,
    maximum=600,
    help_text=(
        "Cycling functional threshold power in watts: the highest power "
        "output you can sustain for about an hour of cycling, typically "
        "measured with a power meter over a 20-60 minute time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE),
)

_RUN_LTHR: Final[AthleteField] = AthleteField(
    key="benchmarks.run.lthr_bpm",
    label="Running LTHR (bpm)",
    kind="int",
    minimum=80,
    maximum=220,
    help_text=(
        "Running lactate threshold heart rate in beats per minute: the "
        "heart rate at your running lactate threshold, typically measured "
        "with a chest-strap monitor over a 20-30 minute running time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.LTHR_BPM, discipline=Sport.RUN),
)

_RIDE_LTHR: Final[AthleteField] = AthleteField(
    key="benchmarks.ride.lthr_bpm",
    label="Cycling LTHR (bpm)",
    kind="int",
    minimum=80,
    maximum=220,
    help_text=(
        "Cycling lactate threshold heart rate in beats per minute: the "
        "heart rate at your cycling lactate threshold, typically measured "
        "with a chest-strap monitor over a 20-30 minute cycling time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.LTHR_BPM, discipline=Sport.RIDE),
)

_RUN_THRESHOLD_PACE: Final[AthleteField] = AthleteField(
    key="benchmarks.run.threshold_pace_s_per_km",
    label="Running threshold pace (s/km)",
    kind="float",
    minimum=120,
    maximum=900,
    help_text=(
        "Running threshold pace in seconds per kilometer: the pace you can "
        "sustain for about an hour of running, typically measured with a "
        "GPS watch over a 20-60 minute running time trial."
    ),
    benchmark=BenchmarkRef(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM, discipline=Sport.RUN
    ),
)

_MAX_HR: Final[AthleteField] = AthleteField(
    key="benchmarks.athlete.max_hr_bpm",
    label="Maximum heart rate (bpm)",
    kind="int",
    minimum=100,
    maximum=230,
    help_text=(
        "Your athlete-wide maximum heart rate in beats per minute, "
        "typically measured with a chest-strap monitor during an all-out "
        "effort or a graded exercise test, and not specific to running or "
        "cycling."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.MAX_HR_BPM, discipline=None),
)

_RESTING_HR: Final[AthleteField] = AthleteField(
    key="benchmarks.athlete.resting_hr_bpm",
    label="Resting heart rate (bpm)",
    kind="int",
    minimum=25,
    maximum=100,
    help_text=(
        "Your athlete-wide resting heart rate in beats per minute, "
        "typically measured with a chest-strap or wrist monitor immediately "
        "on waking, and not specific to running or cycling."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.RESTING_HR_BPM, discipline=None),
)

ATHLETE_FIELDS: Final[tuple[AthleteField, ...]] = (
    _RUN_FTP,
    _RIDE_FTP,
    _RUN_LTHR,
    _RIDE_LTHR,
    _RUN_THRESHOLD_PACE,
    _MAX_HR,
    _RESTING_HR,
)
"""The seven athlete inputs the threshold calculator declares (Req 9.1-9.3),
in declaration order. Exactly the quantities reachable through a non-empty
anchor chain in :data:`fitdocs.load.threshold.discipline.ANCHOR_PLANS` plus
the two athlete-wide heart-rate quantities -- see
``tests/load/threshold/test_fields.py`` for the invariant proof against that
table."""


@dataclass(frozen=True)
class ThresholdCalculator:
    """fitdocs' built-in threshold-based training-load methodology (Req 1.1).

    This task lands only :meth:`required_athlete_fields`. ``supports`` and
    ``compute`` are added to this class by later tasks (3.2, 3.3) under
    their own component boundaries.
    """

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        """The athlete inputs this methodology declares it needs (Req 1.1,
        9.1). Static -- takes no activity, see the module docstring's
        known-limitation note."""
        return ATHLETE_FIELDS
