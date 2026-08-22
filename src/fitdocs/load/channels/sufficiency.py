"""The shared data-sufficiency gate (design: SufficiencyGate).

One gate serves all three channels (Req 2.1, 2.8): the pieces that vary
across the power, heart-rate and pace channels are only *which* array is
inspected (``values``), *which* channel is asking (``channel``), *which*
stream name is reported (``stream``) and, for the pace channel's altitude
refinement alone, an *explicit* minimum that overrides the per-channel
resolution (Req 3.2). Nothing else about the gate's logic varies.

Coverage is **time-weighted**, not sample-counted (Req 2.2): for each
consecutive sample pair with ``dt = time_s[i+1] - time_s[i] > 0``, the
interval counts toward ``covered_s`` when the *earlier* sample carries a
recorded value. This is precisely the accumulation domain the shipped
``fitdocs.metrics.stress.trimp`` already uses -- see its docstring -- so the
reported fraction describes exactly the span a load computed over the same
stream would itself accumulate over. A device *pause* is one long interval
whose earlier sample does carry a value, so it counts as covered and does not
penalize the gate, matching ``trimp``'s own credit of that interval.

Measured on the raw ingested arrays only (Req 2.3): ``stream_coverage`` never
resamples, forward-fills, or substitutes a gap. Presence is ``is not None``,
so a recorded ``0`` counts as covered (Req 2.10) and only an unrecorded value
counts as missing -- the tool's absent-data rule (a real zero is data; a
missing measurement is ``None``, never a fabricated default) applied here to
stream coverage specifically.

The gate never raises (Req 1.8, 2.9): fewer than two samples, a zero-length
recorded span, and a wholly unrecorded stream are all typed
:class:`~fitdocs.load.channels.types.ChannelInsufficient` outcomes, never an
exception.

Evaluation order is fixed and documented here, once, because it is what
makes the reported reason deterministic when more than one condition fails
(Req 2.5, 2.6):

1. No measurable span, or a span below ``settings.min_duration_s`` ->
   :data:`~fitdocs.load.channels.types.InsufficiencyReason.TOO_SHORT`.
2. A stream that carries no recorded value anywhere in the (now-known-long-
   enough) span -> :data:`~fitdocs.load.channels.types.InsufficiencyReason.
   STREAM_ABSENT`.
3. Coverage below the applicable minimum ->
   :data:`~fitdocs.load.channels.types.InsufficiencyReason.STREAM_COVERAGE`.

An activity that fails both duration and coverage therefore always reports
``TOO_SHORT``: duration is judged first, before coverage is even computed
against a threshold.
"""

from __future__ import annotations

from collections.abc import Sequence

from fitdocs.model import Samples

from .types import (
    ChannelId,
    ChannelInsufficient,
    InsufficiencyReason,
    StreamCoverage,
    SufficiencySettings,
)


def stream_coverage(
    samples: Samples, values: Sequence[object | None], *, stream: str
) -> StreamCoverage | None:
    """Measure ``stream``'s time-weighted coverage over ``samples`` (Req 2.2).

    ``values`` is one of ``samples``' own channel arrays, or a sequence
    aligned to it index-for-index. Returns ``None`` when there are fewer
    than two samples or the total positive inter-sample span is zero (Req
    2.9) -- the gate never constructs a :class:`StreamCoverage` with
    ``total_s <= 0``. Otherwise returns a :class:`StreamCoverage` whose
    ``total_s`` is the summed positive ``dt`` between consecutive samples
    and whose ``covered_s`` is the subset of that span whose *earlier*
    sample is not ``None``.
    """
    time_s = samples.time_s
    n = min(len(time_s), len(values))

    total_s = 0.0
    covered_s = 0.0
    for i in range(n - 1):
        dt = time_s[i + 1] - time_s[i]
        if dt <= 0:
            continue
        total_s += dt
        if values[i] is not None:
            covered_s += dt

    if total_s <= 0:
        return None
    return StreamCoverage(stream=stream, covered_s=covered_s, total_s=total_s)


def evaluate(
    samples: Samples,
    values: Sequence[object | None],
    *,
    channel: ChannelId,
    stream: str,
    settings: SufficiencySettings,
    minimum: float | None = None,
) -> StreamCoverage | ChannelInsufficient:
    """Gate ``stream`` for ``channel``, in the fixed order documented on this
    module (Req 2.1, 2.5, 2.6, 2.8).

    ``minimum``, when given, overrides ``settings.minimum_for(channel)`` --
    it exists for exactly one caller, the pace channel's *altitude* check,
    which is a refinement input rather than a channel of its own and must
    therefore be judged against the shared minimum rather than the pace
    channel's own configured override.
    """
    min_duration_s = settings.min_duration_s
    coverage = stream_coverage(samples, values, stream=stream)

    if coverage is None or coverage.total_s < min_duration_s:
        observed = 0.0 if coverage is None else coverage.total_s
        return ChannelInsufficient(
            channel=channel,
            reason=InsufficiencyReason.TOO_SHORT,
            detail=(
                f"{stream} recorded span {observed:g}s is below the minimum "
                f"duration {min_duration_s:g}s"
            ),
            observed=observed,
            required=float(min_duration_s),
        )

    if coverage.covered_s == 0:
        return ChannelInsufficient(
            channel=channel,
            reason=InsufficiencyReason.STREAM_ABSENT,
            detail=f"{stream} carries no recorded value anywhere in the activity",
        )

    required = minimum if minimum is not None else settings.minimum_for(channel)
    if coverage.fraction < required:
        return ChannelInsufficient(
            channel=channel,
            reason=InsufficiencyReason.STREAM_COVERAGE,
            detail=(
                f"{stream} coverage {coverage.fraction:g} is below the "
                f"configured minimum {required:g}"
            ),
            observed=coverage.fraction,
            required=required,
        )

    return coverage
