"""The pace channel: grade-adjusted speed against a threshold pace, on the
same scale as the other two channels (design: PaceChannel).

**Modality checked first (Req 6.7).** Before any benchmark is even looked
at, :func:`compute` checks ``activity.modality``: any modality other than
:data:`~fitdocs.model.Modality.RUN` is
:data:`~fitdocs.load.channels.types.InsufficiencyReason.MODEL_NOT_DEFINED`,
naming the activity's own modality in the reported detail -- and only the
modality, never a suggestion of which other channel might have been used
instead (Req 6.7's second half: this module does not select, rank, or
recommend between channels, matching Req 9.1's boundary). A wrong-quantity
benchmark on a non-running activity never even reaches
:func:`~fitdocs.load.channels.types.require_kind`: the modality gate runs
first, so it never raises there.

**Unit conversion happens here, not in the benchmark store (Req 6.2).**
``threshold_pace.value`` is seconds per kilometre, exactly as
``athlete.toml`` records it (see
:data:`fitdocs.benchmarks.BenchmarkKind.THRESHOLD_PACE_S_PER_KM`); this
module converts it to metres per second itself
(``1000.0 / threshold_pace.value``), and no caller is expected to have
converted it first.

**Anchoring discipline (Req 6.3, 1.9), same shape as the other two
channels.** :func:`compute` anchors exclusively on the ``threshold_pace``
:class:`~fitdocs.benchmarks.Benchmark` it is handed -- no default, no
estimate, no derived value substituted in its place. A supplied benchmark of
the wrong quantity is checked with
:func:`~fitdocs.load.channels.types.require_kind` immediately after the
modality gate, before anything else, and raises rather than being computed
from; an absent benchmark, or one whose value is not strictly positive, is
the distinct
:data:`~fitdocs.load.channels.types.InsufficiencyReason.NO_BENCHMARK`
insufficiency.

**Gate on distance; the not-computable reason (Req 6.5, 6.6).** The shared
:func:`~fitdocs.load.channels.sufficiency.evaluate` gate runs against
``activity.samples.distance_m`` -- the pace channel's own
``pace_min_stream_coverage`` override, when configured, applies here, via
:func:`~fitdocs.load.channels.types.SufficiencySettings.minimum_for`. Once
that gate passes,
:data:`~fitdocs.load.channels.types.InsufficiencyReason.NOT_COMPUTABLE` is
reported when the moving duration
(``metrics.moving_time_s``) is absent or not strictly positive, or when the
accumulated distance
:func:`~fitdocs.load.channels.grade.equivalent_distance` returns cannot be
derived or is not strictly positive.

**The altitude decision is a separate, shared-minimum question (Req 7.6),
composed from :mod:`~fitdocs.load.channels.grade`.** Whether grade
adjustment is applied is decided by running the *same* sufficiency gate a
second time, over ``activity.samples.altitude_m`` -- but with an *explicit*
``minimum=settings.min_stream_coverage``, the shared cross-channel minimum,
**not** ``settings.pace_min_stream_coverage``. Altitude here is a
refinement input to the pace channel's own computation, not a channel of
its own, so the question "is there enough altitude data to trust a grade
adjustment" is judged against the same bar every channel's own primary
stream would be judged against by default, never against the pace
channel's own (possibly stricter or laxer) override -- see
``sufficiency.py``'s own docstring for why ``evaluate``'s ``minimum``
parameter exists for exactly this one caller. When that altitude gate
fails, for *any* reason (absent, too-short span, or thin coverage), this
module never reports insufficiency for it: grade adjustment is simply not
applied, :func:`~fitdocs.load.channels.grade.equivalent_distance` is called
with ``apply_grade=False``, and the returned :class:`ChannelLoad` carries
one note explaining that adjustment was not applied and why. The
``distance`` stream's own gate, its reported coverage, and the moving
duration are computed identically either way, so a with-altitude and a
without-altitude run of the same course report the *same* ``coverage``
and ``scored_duration_s`` -- the two *measured* values -- while ``load``,
``intensity``, ``notes``, and the grade-dependent entries of
``inputs_used`` (``grade_adjusted_speed_mps``,
``grade_adjustment_applied``) all differ (Req 7.6,
7.7 reaching into this channel: grade adjustment affects only intensity
and its reported inputs, never a measured value).

**Composition, not restatement (design: "Channel -- pace.py").** This
module computes no gradient, no smoothed altitude, and no cost-ratio
polynomial itself: all of that is
:func:`fitdocs.load.channels.grade.equivalent_distance`, called unchanged,
exactly the way ``power.py`` calls ``power_tss`` and ``heart_rate.py``
calls its injected weighting model. ``equivalent_distance`` is imported as
a module-level name so the delegation is a real, observable call.

**The intervals.icu formulation, matched (Req 6.1, 6.8).**
``intensity = gap_speed / threshold_speed``,
``load = (moving_time_s / 3600) * intensity ** 2 * 100``, over *moving*
time, not elapsed time (``metrics.moving_time_s``, the same shipped moving-
time derivation the power channel already reads) -- see
:data:`fitdocs.load.channels.sources.INTERVALS_ICU_PACE_LOAD`. This is the
*published form* of the one shared intensity semantic
(``load == hours * intensity ** 2 * 100``): the relation holds here by
construction, exactly as it does for the power channel's ``np / ftp``.

**The one stated divergence (Req 6.8), from the alternative published
method, not from intervals.icu.** fitdocs matches intervals.icu's own
pace-load formulation exactly: grade-adjusted pace over moving time, with
no variability-index normalization step. An *alternative* published
running-load family normalizes for pace variability
(analogous to power's normalized-power treatment); intervals.icu's own
formulation, which this channel matches, does not -- see the
``pace_load_not_variability_normalized`` entry of
:data:`fitdocs.load.channels.sources.DIVERGENCES`, cited here rather than
restated (see task 1.1).

**Feature boundary (Req 9.1).** This module does not decide whether the
pace channel's number should be preferred over the power or heart-rate
channel's for the same activity; that selection lives outside this
package's boundary entirely.
"""

from __future__ import annotations

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity, Modality

from .grade import equivalent_distance
from .sufficiency import evaluate
from .types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
    InsufficiencyReason,
    SufficiencySettings,
    require_kind,
)

_NO_BENCHMARK_DETAIL = (
    "no threshold-pace benchmark was supplied, or its value is not positive"
)

_SECONDS_PER_KM_TO_MPS = 1000.0


def compute(
    activity: Activity,
    metrics: DerivedMetrics,
    *,
    threshold_pace: Benchmark | None,
    settings: SufficiencySettings,
) -> ChannelOutcome:
    """Score ``activity``'s pace channel, or report why it cannot be scored
    (design: PaceChannel Service Interface).

    Evaluation order, fixed and documented here because it is what makes
    the reported reason deterministic when more than one condition fails:

    1. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       MODEL_NOT_DEFINED` when ``activity.modality`` is not
       :data:`~fitdocs.model.Modality.RUN` (Req 6.7) -- checked before
       anything else, including the wrong-quantity guard, so a non-running
       activity never raises on a wrong-kind benchmark.
    2. :func:`~fitdocs.load.channels.types.require_kind` on
       ``threshold_pace``, when supplied (Req 1.9) -- a benchmark of the
       wrong quantity raises rather than being reported as insufficiency or
       computed from.
    3. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       NO_BENCHMARK` when ``threshold_pace`` is absent, or its ``value`` is
       not strictly positive (Req 6.3, 6.4).
    4. The shared sufficiency gate on ``activity.samples.distance_m`` (Req
       6.5); its own insufficiency, whichever reason it names, is returned
       unchanged.
    5. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       NOT_COMPUTABLE` when ``metrics.moving_time_s`` is absent or not
       strictly positive (Req 6.6) -- checked only once the gate has
       passed.
    6. The altitude refinement gate, against the *shared* minimum, decides
       whether grade adjustment is applied (Req 7.6) -- never reported as
       insufficiency on its own.
    7. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       NOT_COMPUTABLE` when the accumulated distance
       :func:`~fitdocs.load.channels.grade.equivalent_distance` returns
       cannot be derived, or is not strictly positive (Req 6.6).
    8. Otherwise, a :class:`~fitdocs.load.channels.types.ChannelLoad`
       composed from the grade-adjusted speed and the converted threshold
       speed (Req 6.1, 6.2, 6.9).
    """
    if activity.modality is not Modality.RUN:
        return ChannelInsufficient(
            channel=ChannelId.PACE,
            reason=InsufficiencyReason.MODEL_NOT_DEFINED,
            detail=(
                "the pace-load model is defined for the running modality "
                f"only; this activity's modality is {activity.modality.value!r}"
            ),
        )

    if threshold_pace is not None:
        require_kind(threshold_pace, BenchmarkKind.THRESHOLD_PACE_S_PER_KM)

    if threshold_pace is None or threshold_pace.value <= 0:
        return ChannelInsufficient(
            channel=ChannelId.PACE,
            reason=InsufficiencyReason.NO_BENCHMARK,
            detail=_NO_BENCHMARK_DETAIL,
        )

    gated = evaluate(
        activity.samples,
        activity.samples.distance_m,
        channel=ChannelId.PACE,
        stream="distance",
        settings=settings,
    )
    if isinstance(gated, ChannelInsufficient):
        return gated
    coverage = gated

    moving_time_s = metrics.moving_time_s
    if moving_time_s is None or moving_time_s <= 0:
        return ChannelInsufficient(
            channel=ChannelId.PACE,
            reason=InsufficiencyReason.NOT_COMPUTABLE,
            detail=(
                "the scored (moving) duration could not be derived from "
                "the data present, or is not positive"
            ),
        )

    # Req 7.6: the altitude refinement question is judged against the
    # SHARED minimum (settings.min_stream_coverage), explicitly passed --
    # never this channel's own pace_min_stream_coverage override, which
    # `evaluate` would otherwise resolve via `settings.minimum_for`.
    altitude_gate = evaluate(
        activity.samples,
        activity.samples.altitude_m,
        channel=ChannelId.PACE,
        stream="altitude",
        settings=settings,
        minimum=settings.min_stream_coverage,
    )
    apply_grade = not isinstance(altitude_gate, ChannelInsufficient)

    adjustment = equivalent_distance(activity.samples, apply_grade=apply_grade)
    if adjustment is None or adjustment.raw_distance_m <= 0:
        return ChannelInsufficient(
            channel=ChannelId.PACE,
            reason=InsufficiencyReason.NOT_COMPUTABLE,
            detail=(
                "accumulated distance could not be derived from the data "
                "present, or is not positive"
            ),
        )

    gap_speed_mps = adjustment.equivalent_distance_m / moving_time_s
    threshold_speed_mps = _SECONDS_PER_KM_TO_MPS / threshold_pace.value
    intensity = gap_speed_mps / threshold_speed_mps
    load = (moving_time_s / 3600.0) * intensity**2 * 100.0

    notes: tuple[str, ...] = ()
    if not adjustment.applied:
        assert isinstance(altitude_gate, ChannelInsufficient)
        notes = (
            "grade adjustment not applied: altitude stream insufficient "
            f"({altitude_gate.detail})",
        )

    inputs_used = (
        ("grade_adjusted_speed_mps", f"{gap_speed_mps:g}"),
        ("threshold_speed_mps", f"{threshold_speed_mps:g}"),
        ("moving_time_s", f"{moving_time_s:g}"),
        ("grade_adjustment_applied", str(adjustment.applied)),
        ("clamped_intervals", str(adjustment.clamped_intervals)),
    )

    return ChannelLoad(
        channel=ChannelId.PACE,
        load=load,
        intensity=intensity,
        anchor=threshold_pace,
        scored_duration_s=moving_time_s,
        coverage=coverage,
        inputs_used=inputs_used,
        notes=notes,
    )
