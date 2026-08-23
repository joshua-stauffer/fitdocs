"""The power channel: Coggan NP -> IF -> TSS (design: PowerChannel).

**Composition, not restatement (Req 4.1, 4.3).** This module computes
nothing that is not already computed elsewhere: normalized power and moving
time are read off the caller's already-derived
:class:`~fitdocs.metrics.types.DerivedMetrics` (the shipped
:mod:`fitdocs.metrics` facade populates both, via
:mod:`fitdocs.metrics.power` and :mod:`fitdocs.metrics.aggregates`
respectively), and the load itself is
:func:`fitdocs.metrics.stress.power_tss`, called unchanged. This module
restates neither the 30 s rolling-average window nor the first-seconds
treatment nor the gap handling normalized power depends on, and it restates
no line of the TSS arithmetic. :func:`compute` imports ``power_tss`` as a
module-level name (as ``fitdocs.load.channels.weighting`` does for
``trimp``) precisely so the delegation is a real, observable call rather
than an inlined reimplementation that happens to agree numerically.

**Anchoring discipline (Req 4.2, 4.4, 1.9).** :func:`compute` anchors
exclusively on the ``ftp`` :class:`~fitdocs.benchmarks.Benchmark` it is
handed -- no default, no estimate, no flat-key fallback, and no other field
on ``activity`` or ``metrics`` is ever read as a substitute threshold. A
supplied benchmark of the wrong quantity is a programming error and fails
loudly (:func:`~fitdocs.load.channels.types.require_kind`, called first,
before any other check) rather than being computed from; an absent
benchmark, or one whose value is not strictly positive, is the distinct
:data:`~fitdocs.load.channels.types.InsufficiencyReason.NO_BENCHMARK`
insufficiency -- a typed report, not a raised error, because "no benchmark
on file" is ordinary missing data, not a caller mistake.

**Modality-agnostic (Req 4.7).** Nothing in this module inspects
``activity.sport`` or ``activity.modality``: any activity that records
power -- running included -- is scored the same way, and the discipline
that produced the anchoring benchmark is reported in ``inputs_used``
alongside the benchmark's own measurement date, not decided by the
activity's own modality.

**The intervals.icu divergence (Req 4.9).** fitdocs computes a running
power load from the watts a device recorded (Apple Watch native running
power, Stryd, and similar), where intervals.icu does not ingest those
running-power fields natively -- see the
``running_power_from_recorded_watts``
:class:`~fitdocs.load.channels.sources.Divergence` entry in
``fitdocs.load.channels.sources.DIVERGENCES``, whose own ``reason`` states
this plainly: running power meters and watches increasingly record watts
directly, and refusing to score them because one platform does not ingest
the field would fabricate an absence that is not real. No running-power
*model* (Stryd RSS, GOVSS, Skiba) is implemented here or anywhere in this
package -- only the recorded watts, run through the same Coggan arithmetic
every other power-recording modality uses, are consumed.

**The reference intensity form (Req 1.11).** ``intensity = np / ftp`` is
the *reference* definition of the one intensity semantic shared by all
three channels (``load == hours * intensity**2 * 100``): the shipped
``power_tss`` is algebraically ``hours * (np/ftp)**2 * 100`` already
(``IF = np/ftp``, ``TSS = hours * np * IF / ftp * 100 == hours * IF**2 *
100``), so this channel satisfies the relation by construction rather than
by a second, independently-tuned computation. The heart-rate and pace
channels are defined to match this form, not the other way around.
"""

from __future__ import annotations

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.metrics.stress import power_tss
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity

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
    "no functional-threshold-power benchmark was supplied, or its value is not positive"
)


def compute(
    activity: Activity,
    metrics: DerivedMetrics,
    *,
    ftp: Benchmark | None,
    settings: SufficiencySettings,
) -> ChannelOutcome:
    """Score ``activity``'s power channel, or report why it cannot be
    scored (design: PowerChannel Service Interface).

    Evaluation order, fixed and documented here because it is what makes
    the reported reason deterministic when more than one condition fails:

    1. If ``ftp`` is supplied, :func:`~fitdocs.load.channels.types.
       require_kind` is called on it first, before anything else -- a
       benchmark of the wrong quantity raises rather than being reported as
       insufficiency or computed from (Req 1.9).
    2. An absent ``ftp``, or one whose ``value`` is not strictly positive,
       is :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       NO_BENCHMARK` (Req 4.2, 4.4) -- decided before the stream is gated,
       so a missing benchmark is reported as a missing benchmark even when
       the power stream also happens to be insufficient.
    3. The shared sufficiency gate is evaluated on ``activity.samples.
       power_w`` (Req 4.6); its own insufficiency, whichever reason it
       names, is returned unchanged.
    4. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       NOT_COMPUTABLE` when ``metrics.normalized_power_w`` or
       ``metrics.moving_time_s`` is ``None`` (Req 4.5) -- checked only once
       the gate has passed, so a stream that fails the gate is never
       reported as merely "not computable".
    5. Otherwise, a :class:`~fitdocs.load.channels.types.ChannelLoad`
       composed from ``power_tss`` (Req 4.1, 4.3).
    """
    if ftp is not None:
        require_kind(ftp, BenchmarkKind.FTP_WATTS)

    if ftp is None or ftp.value <= 0:
        return ChannelInsufficient(
            channel=ChannelId.POWER,
            reason=InsufficiencyReason.NO_BENCHMARK,
            detail=_NO_BENCHMARK_DETAIL,
        )

    gated = evaluate(
        activity.samples,
        activity.samples.power_w,
        channel=ChannelId.POWER,
        stream="power",
        settings=settings,
    )
    if isinstance(gated, ChannelInsufficient):
        return gated
    coverage = gated

    np_w = metrics.normalized_power_w
    moving_time_s = metrics.moving_time_s
    if np_w is None or moving_time_s is None:
        return ChannelInsufficient(
            channel=ChannelId.POWER,
            reason=InsufficiencyReason.NOT_COMPUTABLE,
            detail=(
                "normalized power or the scored (moving) duration could not "
                "be derived from the data present"
            ),
        )

    load = power_tss(np_w, moving_time_s, ftp.value)
    assert load is not None  # every input power_tss requires is present and ftp > 0

    discipline = "athlete" if ftp.discipline is None else ftp.discipline.value
    inputs_used = (
        ("normalized_power_w", f"{np_w:g}"),
        ("ftp_watts", f"{ftp.value:g}"),
        ("anchoring_discipline", discipline),
        ("ftp_measured_on", ftp.measured_on.isoformat()),
    )

    return ChannelLoad(
        channel=ChannelId.POWER,
        load=load,
        intensity=np_w / ftp.value,
        anchor=ftp,
        scored_duration_s=moving_time_s,
        coverage=coverage,
        inputs_used=inputs_used,
    )
