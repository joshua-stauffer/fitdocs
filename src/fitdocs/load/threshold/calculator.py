"""The threshold calculator's own :class:`~fitdocs.load.types.LoadCalculator`
implementation (design: ``ThresholdCalculator``).

Task 3.1 (``AthleteFieldDeclaration``, Req 9.1-9.3) lands the static
athlete-input declaration: the seven benchmarks the shipped prompt flow must
collect to score the supported disciplines. Task 3.2 (``ResultAssembly``,
Req 3.7, 6.6, 8.1, 8.2, 8.6-8.12, 10.3, 10.4) adds :func:`build_result` and
its module-level formatters -- the one place a selection is mapped onto the
contract's :class:`~fitdocs.load.types.LoadResult`. ``supports`` and
``compute`` (3.3) are added to this same class by a later task under its own
component boundary -- this file is deliberately left extendable rather than
stubbed for it.

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

``build_result`` (design: ``ResultAssembly``) maps a channel selection onto
the contract's :class:`~fitdocs.load.types.LoadResult` without inventing
anything: the selected channel's ``load`` becomes ``value`` verbatim
(Req 8.1, 8.10), its ``intensity`` is emitted verbatim under the single
``"Intensity"`` label because ``load-channels`` guarantees one intensity
semantic across all three channels (Req 8.11), and every value is rendered
through the deterministic formatters below so identical inputs produce
byte-identical records (Req 8.9). It deliberately takes no ``flags``
argument -- adding one later is an additive signature change, whereas an
always-empty parameter today would be the anticipatory dead code the roadmap
forbids (Req 8.8).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelLoad,
    ChannelOutcome,
    StreamCoverage,
)
from fitdocs.load.threshold.anchors import Borrowing, ResolvedAnchors
from fitdocs.load.threshold.selection import CHANNEL_LABELS, non_selected_values
from fitdocs.load.types import AthleteField, BenchmarkRef, LoadResult
from fitdocs.model import Sport

__all__ = [
    "ATHLETE_FIELDS",
    "ThresholdCalculator",
    "build_result",
    "format_coverage",
    "format_duration",
    "format_ratio",
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

    Tasks 3.1 and 3.2 land :meth:`required_athlete_fields` and the
    module-level :func:`build_result` respectively. ``supports`` and
    ``compute`` are added to this class by a later task (3.3) under its own
    component boundary.
    """

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        """The athlete inputs this methodology declares it needs (Req 1.1,
        9.1). Static -- takes no activity, see the module docstring's
        known-limitation note."""
        return ATHLETE_FIELDS


# ---------------------------------------------------------------------------
# ResultAssembly (task 3.2)
# ---------------------------------------------------------------------------

_CALCULATOR_ID: Final[str] = "threshold"
_DISPLAY_NAME: Final[str] = "Threshold Load"

_BORROWING_CHANNEL_LABEL: Final[Mapping[BenchmarkKind, str]] = {
    BenchmarkKind.FTP_WATTS: "Power",
    BenchmarkKind.LTHR_BPM: "Heart-rate",
    BenchmarkKind.THRESHOLD_PACE_S_PER_KM: "Pace",
}
"""Which channel a borrowed benchmark kind anchors, for the borrowing note's
subject (Req 3.4, 8.7). Deliberately distinct spelling from
:data:`~fitdocs.load.threshold.selection.CHANNEL_LABELS` ("Heart-rate" here,
"Heart rate" there): both mappings render into prose -- ``CHANNEL_LABELS``
also becomes a note prefix in :func:`build_result`, so the two spellings can
land adjacent in the same ``notes`` tuple -- but the hyphenated form here
exists because design.md's postcondition spells the borrowing note this
way."""

_BORROWING_QUANTITY_NAME: Final[Mapping[BenchmarkKind, str]] = {
    BenchmarkKind.FTP_WATTS: "threshold power",
    BenchmarkKind.LTHR_BPM: "lactate threshold heart rate",
    BenchmarkKind.THRESHOLD_PACE_S_PER_KM: "threshold pace",
}
"""The human-readable quantity name for a borrowed benchmark kind's note."""


def format_ratio(value: float) -> str:
    """Format a dimensionless ratio (intensity or any other) to three
    decimals, deterministically (Req 8.9, Implementation Notes)."""
    return f"{value:.3f}"


def format_coverage(coverage: StreamCoverage) -> str:
    """Format a channel's measured stream coverage as a percentage to one
    decimal, naming the stream it was measured on and the basis it was
    measured over -- e.g. ``"distance 99.8% of recorded time"`` -- so it is
    never mistaken for the workout document's own sample-count coverage
    table (Req 8.12)."""
    return f"{coverage.stream} {coverage.fraction * 100:.1f}% of recorded time"


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as ``H:MM:SS``, deterministically
    (Req 8.9, Implementation Notes)."""
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _format_borrowing(borrowing: Borrowing) -> str:
    """One note naming both disciplines a borrowed anchor spans (Req 3.4),
    e.g. ``"Heart-rate channel anchored on the Run lactate threshold heart
    rate; no Hike threshold is on file."``."""
    channel_label = _BORROWING_CHANNEL_LABEL[borrowing.kind]
    quantity_name = _BORROWING_QUANTITY_NAME[borrowing.kind]
    return (
        f"{channel_label} channel anchored on the {borrowing.anchor_discipline} "
        f"{quantity_name}; no {borrowing.activity_discipline} threshold is on "
        "file."
    )


def build_result(
    *,
    selected: ChannelLoad,
    outcomes: Mapping[ChannelId, ChannelOutcome],
    order: tuple[ChannelId, ...],
    anchors: ResolvedAnchors,
    discipline: Sport,
) -> LoadResult:
    """Map a channel selection onto the contract's computed result, inventing
    nothing (design: ``ResultAssembly``, Req 3.7, 6.6, 8.1, 8.2, 8.6-8.12,
    10.3, 10.4).

    ``value`` and ``basis`` are read only from ``selected`` -- never from
    ``outcomes`` or ``anchors`` -- so no field of the result can be derived
    from a non-selected value (Req 8.10). ``flags`` is always the empty
    tuple; this function takes no ``flags`` argument (Req 8.8, and see the
    module docstring's extension-point note).
    """
    channel_id = selected.channel
    label = CHANNEL_LABELS[channel_id]

    non_selected = non_selected_values(
        outcomes, order=order, selected=channel_id, discipline=discipline
    )

    inputs_used: tuple[tuple[str, str], ...] = (
        ("Channel", label),
        ("Selection order", " > ".join(entry.value for entry in order)),
        ("Intensity", format_ratio(selected.intensity)),
        ("Scored duration", format_duration(selected.scored_duration_s)),
        ("Coverage", format_coverage(selected.coverage)),
        *selected.inputs_used,
    )

    # Every Borrowing is noted, not only those anchoring the selected
    # channel: design.md's table says one note per Borrowing, and each note
    # names its own channel, so a note about a borrowed heart-rate anchor
    # cannot be misread as describing a power-based `value`. Today the two
    # readings are indistinguishable -- only Walk/Hike heart rate ever
    # borrows, and Walk/Hike can only select heart rate -- so design.md's
    # table and this comment are the only things recording which reading is
    # intended; no test can currently tell them apart.
    notes: tuple[str, ...] = (
        *(_format_borrowing(borrowing) for borrowing in anchors.borrowed),
        *(f"{label}: {note}" for note in selected.notes),
    )

    return LoadResult(
        calculator_id=_CALCULATOR_ID,
        display_name=_DISPLAY_NAME,
        value=selected.load,
        basis=channel_id.value,
        non_selected=non_selected,
        flags=(),
        inputs_used=inputs_used,
        notes=notes,
    )
