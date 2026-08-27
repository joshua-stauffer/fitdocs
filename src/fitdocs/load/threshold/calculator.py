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

Task 3.3 (``ThresholdCalculator``, Req 1.4-1.7, 2.2, 2.3, 2.5, 2.7, 4.2, 4.3,
5.1-5.4, 6.7, 9.4-9.7, 10.1, 10.2, 10.5, 10.6) adds ``supports`` and
``compute``: the fixed decision sequence -- sport check, date check, resolve
anchors, evaluate all three channels, select, assemble or explain -- that
turns one activity into one :class:`~fitdocs.load.types.LoadOutcome`.

**Why the not-computed case rides ``NotComputed``.** The contract's closed
union offers ``Computed``, ``Unsupported``, ``MissingInputs`` and
``NotComputed``. ``Unsupported`` drives a *document state* and would wrongly
claim the sport is out of scope -- every activity that reaches this point
already passed the sport check. ``MissingInputs`` renders as "missing
required inputs" and would misdescribe a coverage failure (e.g. every
channel gated by too little recorded stream, or a benchmark on file but not
yet in force on this date) as an absent athlete input. ``NotComputed`` is the
variant the engine renders as "skipped, with the calculator's own reason",
which is exactly this case -- so this feature uses it and does not widen a
closed union it does not own.

**``supports`` narrows by sport AND modality, not by sport alone.**
design.md's docstring for ``supports`` says it "may only narrow
DECLARED_MODALITIES, never widen them -- the registry's modality prefilter
runs first". That premise does not hold on every path: ``arbitrate()``'s
``forced_id`` and ``default_calculator`` branches (``arbitrate.py``) return
``Selected`` unconditionally, un-narrowed by ``registry.for_modality`` --
only the no-default candidates branch composes the modality prefilter with
``supports_activity`` first. Under a forced or configured
``default_calculator = "threshold"``, ``supports_activity`` is the *only*
question standing between an activity and the prompt flow (engine.py's own
comment at the support-check call site says as much). A ``supports`` that
answers purely from ``SUPPORTED_SPORTS`` would therefore return ``True`` for
``detect_sport("running", "strength_training")``, whose modality is the
undeclared ``Modality.STRENGTH`` but whose sport is ``Sport.RUN`` -- widening
past ``DECLARED_MODALITIES`` and breaking Req 2.2 for exactly the strength
case that motivated the sport/modality split in the first place. Answering
from *both* ``SUPPORTED_SPORTS`` and ``DECLARED_MODALITIES`` is a genuine
narrowing of the declared modalities (a Rowing or Workout document, both
inside the catch-all ``Modality.OTHER``, is still refused before the prompt
flow -- Req 2.7), and it is what ``load/types.py``'s documented obligation on
every ``supports`` implementation ("must only ever narrow ... never widen")
actually requires here, which the sport-only reading violates on this one
shipped path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.channels import (
    heart_rate_compute,
    pace_compute,
    power_compute,
)
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
    InsufficiencyReason,
    StreamCoverage,
)
from fitdocs.load.threshold.anchors import Borrowing, ResolvedAnchors, resolve
from fitdocs.load.threshold.discipline import (
    DECLARED_MODALITIES,
    SUPPORTED_SPORTS,
    anchor_plan,
)
from fitdocs.load.threshold.selection import (
    CHANNEL_LABELS,
    non_selected_values,
    select,
)
from fitdocs.load.types import (
    AthleteField,
    BenchmarkRef,
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    MissingInputs,
    NotComputed,
    ProfileView,
    Unsupported,
)
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity, Modality, Sport

__all__ = [
    "ATHLETE_FIELDS",
    "CALCULATOR_ID",
    "DISPLAY_NAME",
    "THRESHOLD_CALCULATOR",
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


CALCULATOR_ID: Final[str] = "threshold"
DISPLAY_NAME: Final[str] = "Threshold Load"


@dataclass(frozen=True)
class ThresholdCalculator:
    """fitdocs' built-in threshold-based training-load methodology (Req 1.1).

    A frozen dataclass with the three contract attributes and three methods
    -- nothing a plugin author could not write. Tasks 3.1 and 3.2 land
    :meth:`required_athlete_fields` and the module-level :func:`build_result`
    respectively; task 3.3 (``ThresholdCalculator``) adds :attr:`
    supported_modalities`, :meth:`supports` and :meth:`compute` -- the
    contract's fixed decision sequence, documented in full on
    :meth:`compute`.
    """

    calculator_id: str = CALCULATOR_ID
    display_name: str = DISPLAY_NAME
    supported_modalities: frozenset[Modality] = DECLARED_MODALITIES

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        """The athlete inputs this methodology declares it needs (Req 1.1,
        9.1). Static -- takes no activity, see the module docstring's
        known-limitation note."""
        return ATHLETE_FIELDS

    def supports(self, activity: Activity) -> bool:
        """True iff ``activity`` is both a supported sport and inside the
        declared modalities (Req 2.5, 2.6, 2.7).

        Optional and off-Protocol (design.md Amendment 2): ``LoadCalculator``
        declares no ``supports`` member, and defining one here is additive.
        The engine reaches it through ``supports_activity(calculator,
        activity)``, which prefers this answer by ``getattr`` and otherwise
        falls back to ``supported_modalities`` membership.

        Answers from ``SUPPORTED_SPORTS`` **and** ``DECLARED_MODALITIES``,
        not sport alone -- see the module docstring's "``supports`` narrows
        by sport AND modality" note for why the sport-only reading widens
        past the declared modalities on the forced/default arbitration path
        and breaks Req 2.2 for a strength activity whose normalized sport is
        ``Sport.RUN`` (``detect_sport`` has no ``Sport.STRENGTH`` member; a
        ``strength_training`` sub-sport only overrides the *modality*). This
        is a genuine narrowing of ``DECLARED_MODALITIES``, never a widening:
        the ``and`` conjunct is itself the narrowing -- a sport does not
        carry a modality, so answering from the sport set alone can only
        ever be equal-or-wider than answering from both sets together, never
        narrower. ``ANCHOR_PLANS``/``SUPPORTED_SPORTS`` exhaustiveness is
        proven separately, in ``test_discipline.py`` and ``test_fields.py``.

        Asked BEFORE the prompt flow, so an activity inside a declared
        modality but outside the supported sport set -- a Rowing or generic
        Workout document, both inside the catch-all ``Modality.OTHER`` --
        never costs the athlete a question (Req 2.7).
        """
        return activity.sport in SUPPORTED_SPORTS and (
            activity.modality in DECLARED_MODALITIES
        )

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        """Compute a typed load outcome for ``activity`` (design:
        ``ThresholdCalculator`` Service Interface, Postconditions 1-6).

        The fixed decision sequence, in the order it is decided:

        1. ``activity.sport not in SUPPORTED_SPORTS or activity.modality not
           in DECLARED_MODALITIES`` -> :class:`Unsupported` naming the sport
           (Req 2.2, 2.3, 2.5, 2.7). The same sport-AND-modality conjunction
           :meth:`supports` answers from (see the module docstring's
           "``supports`` narrows by sport AND modality" note), so the two
           stay provably in agreement -- a strength-labelled Run
           (``detect_sport("running", "strength_training")`` -> ``(Sport.
           RUN, Modality.STRENGTH)``) is refused here exactly as it is by
           ``supports``, never computing a heart-rate-derived value for it
           (Req 2.2). Normally unreachable because :meth:`supports` already
           said no; retained as defence in depth so an unsupported activity
           reaching ``compute`` through any path costs no lookup and no
           channel call.
        2. ``context.activity_date is None`` -> :class:`NotComputed` naming
           the absent date (Req 4.3) -- the start time is a UTC instant, the
           document is named from a local calendar date, and scoring must
           agree with the file name (Req 4.1), so this reads only
           ``context.activity_date``, never ``activity.start_time``.
        3. Otherwise resolve the anchors, then evaluate **all three**
           channels with those anchors and ``context.settings.sufficiency``
           (Req 5.1, 5.2, 5.3) -- every channel regardless of what the
           configured order prefers, so the diagnostics are complete and the
           heart-rate outcome exists even when another channel is selected.
        4. A selection -> :class:`Computed` carrying :func:`build_result`.
        5. No selection, and at least one channel in the configured order
           reported a missing benchmark whose quantity is in
           ``anchors.not_on_file`` -> :class:`MissingInputs` carrying the
           corresponding declared fields, in ``ATHLETE_FIELDS`` declaration
           order (Req 9.4).
        6. No selection otherwise -> :class:`NotComputed` whose reason names
           every evaluated channel and its reason, in
           :data:`~fitdocs.load.threshold.selection.CANONICAL_CHANNELS`
           order (Req 10.1, 10.2).

        Never raises (Req 1.7): every failure path returns one of the
        contract's four typed outcomes. ``session`` is never used (Req 9.7)
        -- this calculator asks nothing and confirms nothing. Applies no
        sufficiency rule, no rounding and no adjustment of a channel's
        reported load or intensity (Req 5.4); every channel's outcome is
        carried forward unmodified into :func:`build_result` or the
        not-computed reason. Reads the configured order from
        ``context.settings.channel_priority`` and the sufficiency config
        from ``context.settings.sufficiency``; opens, locates or re-reads no
        settings or profile file (Req 1.6). Identical inputs yield an
        identical outcome, reason strings included (Req 1.4, 10.6).
        """
        del session  # Req 9.7: this calculator asks nothing, confirms nothing.

        if (
            activity.sport not in SUPPORTED_SPORTS
            or activity.modality not in DECLARED_MODALITIES
        ):
            return Unsupported(
                reason=f"{activity.sport} is not a sport the threshold "
                "calculator scores"
            )

        if context.activity_date is None:
            return NotComputed(
                reason=(
                    "activity carries no local calendar date to resolve "
                    "benchmarks against"
                )
            )

        sport = activity.sport
        anchors = resolve(profile, sport=sport, on=context.activity_date)
        sufficiency = context.settings.sufficiency

        outcomes: dict[ChannelId, ChannelOutcome] = {
            ChannelId.POWER: power_compute(
                activity, metrics, ftp=anchors.ftp, settings=sufficiency
            ),
            ChannelId.HEART_RATE: heart_rate_compute(
                activity,
                metrics,
                lthr=anchors.lthr,
                resting_hr=anchors.resting_hr,
                max_hr=anchors.max_hr,
                settings=sufficiency,
            ),
            ChannelId.PACE: pace_compute(
                activity,
                metrics,
                threshold_pace=anchors.threshold_pace,
                settings=sufficiency,
            ),
        }

        order = context.settings.channel_priority.for_discipline(sport)
        selected_id = select(outcomes, order)

        if selected_id is not None:
            selected_outcome = outcomes[selected_id]
            assert isinstance(selected_outcome, ChannelLoad)  # select()'s own guarantee
            result = build_result(
                selected=selected_outcome,
                outcomes=outcomes,
                order=order,
                anchors=anchors,
                discipline=sport,
            )
            return Computed(result=result)

        missing_fields = _missing_inputs(outcomes, order=order, anchors=anchors)
        if missing_fields:
            return MissingInputs(fields=missing_fields)

        return NotComputed(reason=_not_computed_reason(outcomes, order, sport))


THRESHOLD_CALCULATOR: Final[ThresholdCalculator] = ThresholdCalculator()
"""The one shipped instance (design: Service Interface). Registering it is
task 4.1's job -- importing this module for a test registers nothing and
mutates no global state."""


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


# ---------------------------------------------------------------------------
# ThresholdCalculator's own decision helpers (task 3.3)
# ---------------------------------------------------------------------------

_CHANNEL_BENCHMARK_KINDS: Final[Mapping[ChannelId, tuple[BenchmarkKind, ...]]] = {
    ChannelId.POWER: (BenchmarkKind.FTP_WATTS,),
    ChannelId.HEART_RATE: (
        BenchmarkKind.LTHR_BPM,
        BenchmarkKind.MAX_HR_BPM,
        BenchmarkKind.RESTING_HR_BPM,
    ),
    ChannelId.PACE: (BenchmarkKind.THRESHOLD_PACE_S_PER_KM,),
}
"""Which benchmark quantities each channel's ``compute`` consumes (Req 9.4).
Used only to decide whether a channel's :data:`InsufficiencyReason.
NO_BENCHMARK` traces back to a quantity that is genuinely not on file
anywhere (``anchors.not_on_file``) versus one that is on file but not
applicable to this date (``anchors.not_applicable``, which reports
:class:`NotComputed` instead -- Req 9.5)."""

_FieldRef = tuple[BenchmarkKind, Sport | None]
_FIELD_BY_BENCHMARK_REF: Final[Mapping[_FieldRef, AthleteField]] = {
    (field.benchmark.kind, field.benchmark.discipline): field
    for field in ATHLETE_FIELDS
    if field.benchmark is not None
}
"""``ATHLETE_FIELDS`` indexed by the exact ``(kind, discipline)`` it
declares -- e.g. ``(FTP_WATTS, Sport.RUN)`` -> the Running FTP field. Built
from the real table, not a hand-authored copy, so a future field addition or
removal cannot silently desync this lookup."""


def _declared_field_for_absence(
    kind: BenchmarkKind, discipline: Sport | None
) -> AthleteField:
    """The declared :class:`AthleteField` that would resolve a
    ``ResolvedAnchors.not_on_file`` entry (Req 9.4).

    An athlete-wide quantity (``discipline is None``) maps directly. A
    discipline-scoped quantity maps to the *last* entry of that sport's
    anchor chain -- the guaranteed-to-resolve entry ``ATHLETE_FIELDS``'
    module docstring documents declaring -- since ``not_on_file`` records the
    activity's own sport, not the chain entry that produced the verdict (see
    ``ResolvedAnchors``' own docstring), and only that last entry is ever
    declared as an athlete input for a borrowing sport such as Walk or Hike.
    """
    if discipline is None:
        return _FIELD_BY_BENCHMARK_REF[(kind, None)]
    chain = _chain_for_kind(kind, discipline)
    return _FIELD_BY_BENCHMARK_REF[(kind, chain[-1])]


def _chain_for_kind(kind: BenchmarkKind, discipline: Sport) -> tuple[Sport, ...]:
    """The anchor chain ``discipline``'s plan declares for ``kind`` -- the
    same three chains :func:`~fitdocs.load.threshold.anchors.resolve` walks,
    read back out by benchmark kind rather than by field name."""
    plan = anchor_plan(discipline)
    if kind is BenchmarkKind.FTP_WATTS:
        return plan.ftp
    if kind is BenchmarkKind.LTHR_BPM:
        return plan.lthr
    if kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM:
        return plan.threshold_pace
    raise AssertionError(  # pragma: no cover - defensive; only reached for an
        # athlete-wide kind, which the caller (_declared_field_for_absence)
        # never routes here (discipline is None short-circuits first).
        f"{kind} has no discipline-scoped anchor chain"
    )


def _missing_inputs(
    outcomes: Mapping[ChannelId, ChannelOutcome],
    *,
    order: tuple[ChannelId, ...],
    anchors: ResolvedAnchors,
) -> tuple[AthleteField, ...]:
    """The declared fields to name in :class:`MissingInputs` (Postcondition
    5, Req 9.4), or ``()`` when nothing blocking is on the not-on-file list.

    Only channels in the *configured* ``order`` are consulted -- a channel
    excluded from the order can never be selected, so a benchmark that
    blocks only that channel is not a reason to ask the athlete for
    anything. A channel qualifies when its outcome is :class:`
    ChannelInsufficient` with reason :data:`InsufficiencyReason.
    NO_BENCHMARK` **and** at least one of the quantities it consumes
    (:data:`_CHANNEL_BENCHMARK_KINDS`) is in ``anchors.not_on_file`` --
    distinguishing "never provided" from "on file but not applicable to this
    date" (Req 9.5), which contributes to :class:`NotComputed` instead.

    The returned fields are deduplicated and ordered by their position in
    ``ATHLETE_FIELDS`` -- declaration order, not the order channels were
    walked or the order their quantities were resolved (Req 9.4).
    """
    not_on_file_by_kind: dict[BenchmarkKind, Sport | None] = {
        kind: discipline for kind, discipline in anchors.not_on_file
    }
    needed_kinds: set[BenchmarkKind] = set()
    for channel_id in order:
        outcome = outcomes[channel_id]
        if not isinstance(outcome, ChannelInsufficient):
            continue
        if outcome.reason is not InsufficiencyReason.NO_BENCHMARK:
            continue
        for kind in _CHANNEL_BENCHMARK_KINDS[channel_id]:
            if kind in not_on_file_by_kind:
                needed_kinds.add(kind)

    if not needed_kinds:
        return ()

    fields = {
        _declared_field_for_absence(kind, not_on_file_by_kind[kind]).key: (
            _declared_field_for_absence(kind, not_on_file_by_kind[kind])
        )
        for kind in needed_kinds
    }
    return tuple(field for field in ATHLETE_FIELDS if field.key in fields)


def _not_computed_reason(
    outcomes: Mapping[ChannelId, ChannelOutcome],
    order: tuple[ChannelId, ...],
    sport: Sport,
) -> str:
    """The not-computed reason, naming every evaluated channel and why it
    produced no selected value, in ``CANONICAL_CHANNELS`` order
    (Postcondition 6, Req 10.1, 10.2).

    Delegates the per-channel wording to :func:`~fitdocs.load.threshold.
    selection.non_selected_values` with ``selected=None`` -- with no
    selection, no computed-and-in-order branch of that function can fire (a
    channel in ``order`` producing :class:`ChannelLoad` would have made
    :func:`~fitdocs.load.threshold.selection.select` return a channel), so
    every record is either an insufficiency's own ``detail`` or -- for a
    channel that computed a load but sits outside the configured order --
    the "not in the configured order" reason. Reusing this function keeps
    the wording identical to the diagnostics :func:`build_result` records
    for the very same channels on a *different* activity that did select,
    rather than maintaining a second, driftable phrasing here.
    """
    records = non_selected_values(
        outcomes, order=order, selected=None, discipline=sport
    )
    return "no channel produced a load: " + "; ".join(
        f"{record.label}: {record.reason}" for record in records
    )
