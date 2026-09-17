"""Cadence-lock measurement: paired-stream presence and per-span statistics
(design: CadenceLockDetector, `src/fitdocs/load/qa/cadence.py`).

**Responsibility split between task 2.1 (this task) and task 2.2.** This
module is written under two different responsibility boundaries in strict
sequence: 2.1 owns *measurement* -- turning the raw heart-rate and cadence
arrays into per-span statistics, including each span's own ``locked`` flag,
which is a pure function of that span's own correlation and median delta
against the configured thresholds. 2.2 owns the *verdict* -- summing the
duration of locked spans, comparing that sum against
``settings.cadence_lock_min_duration_s``, and applying the modality /
absent-stream / paired-coverage / span-count not-assessed gates that need
inputs (the modality, the whole-``Samples`` paired coverage, the span count)
this module's two functions do not have in scope. Concretely: a span's
``locked`` field is decided here, in :func:`span_statistics`, using the
conjunctive rule -- ``correlation is not None and correlation >=
settings.cadence_lock_min_correlation and median_delta_bpm <=
settings.cadence_lock_max_delta_bpm`` -- because that decision is fully
determined by the span's own two statistics and the settings already in
scope, and is not the "is the *activity* locked" verdict that needs the
modality/coverage/duration-summing logic only task 2.2 has the inputs for.
2.2 consumes ``span.locked`` as already computed here; it does not
recompute it.

Reads the raw ingested arrays only (Req 2.10): no resampling, forward-fill,
interpolation or gap substitution anywhere in this module.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from fitdocs.model import Samples

from .types import STEPS_PER_CADENCE_REVOLUTION, FlagSettings


@dataclass(frozen=True)
class SpanStatistic:
    """One non-overlapping, full-width span's measured cadence-lock
    statistics (Req 2.1, 2.4).

    Every :class:`SpanStatistic` :func:`span_statistics` returns describes a
    span of exactly ``window_s`` seconds -- a trailing span shorter than the
    configured width is never emitted, which is what lets task 2.2 treat
    ``len(span_statistics(...)) == 0`` as "no full span can be formed" (Req
    2.7) without a second, separate duration check.
    """

    start_s: float
    duration_s: float
    correlation: float | None
    """``None`` when the span is degenerate: fewer than two paired samples,
    or zero variance in the heart-rate or the full-cycle-cadence series over
    the span (Pearson r is undefined there, not merely hard to compute)."""
    median_delta_bpm: float
    """The median of ``|heart_rate_bpm - full_cycle_cadence|`` over the
    span's paired points. Computed even for a degenerate span -- a median
    needs no correlation to be meaningful (only ``correlation`` and
    ``locked`` are affected by degeneracy)."""
    locked: bool
    """``True`` only when ``correlation`` is present and at or above
    ``settings.cadence_lock_min_correlation`` *and* ``median_delta_bpm`` is
    at or below ``settings.cadence_lock_max_delta_bpm`` -- the conjunctive
    rule (Req 2.2), decided per span. Never ``True`` for a degenerate span."""


def paired_presence(samples: Samples) -> tuple[float | None, ...]:
    """The paired-presence view of ``samples``' heart-rate and cadence
    streams (Req 2.1).

    Index *i* holds a float when both ``heart_rate_bpm[i]`` and
    ``cadence_rpm[i]`` were recorded, and ``None`` otherwise -- exactly the
    shape ``fitdocs.load.channels.sufficiency.stream_coverage`` consumes, so
    the paired-coverage gate reuses that one time-weighted coverage
    definition rather than restating it (Req 8.1, 8.2). The float carried at
    a paired index is the recorded heart-rate value itself: only its
    presence, not its magnitude, is meaningful to the coverage gate, and
    reusing a real recorded number (rather than an arbitrary sentinel) keeps
    this view an honest reflection of the two source streams.
    """
    heart_rate_bpm = samples.heart_rate_bpm
    cadence_rpm = samples.cadence_rpm
    return tuple(
        float(hr) if hr is not None and cadence is not None else None
        for hr, cadence in zip(heart_rate_bpm, cadence_rpm, strict=True)
    )


def _span_statistic(
    *,
    start_s: float,
    window_s: int,
    indices: list[int],
    samples: Samples,
    settings: FlagSettings,
) -> SpanStatistic:
    heart_rate_bpm = samples.heart_rate_bpm
    cadence_rpm = samples.cadence_rpm

    hr_values = [float(heart_rate_bpm[i]) for i in indices]  # type: ignore[arg-type]
    full_cycle_values = [
        float(cadence_rpm[i]) * STEPS_PER_CADENCE_REVOLUTION  # type: ignore[arg-type]
        for i in indices
    ]
    deltas = [
        abs(hr - cad) for hr, cad in zip(hr_values, full_cycle_values, strict=True)
    ]
    median_delta_bpm = statistics.median(deltas)

    correlation: float | None = None
    if len(indices) >= 2:
        try:
            correlation = statistics.correlation(hr_values, full_cycle_values)
        except statistics.StatisticsError:
            # Zero variance in one of the two series over this span -- a
            # constant series cannot demonstrate a real statistical
            # association, so this span reports no correlation rather than
            # letting the exception propagate or fabricating one (Req 2.1).
            correlation = None

    locked = (
        correlation is not None
        and correlation >= settings.cadence_lock_min_correlation
        and median_delta_bpm <= settings.cadence_lock_max_delta_bpm
    )

    return SpanStatistic(
        start_s=start_s,
        duration_s=float(window_s),
        correlation=correlation,
        median_delta_bpm=median_delta_bpm,
        locked=locked,
    )


def span_statistics(
    samples: Samples, *, window_s: int, settings: FlagSettings
) -> tuple[SpanStatistic, ...]:
    """Divide the paired samples into successive non-overlapping spans of
    ``window_s`` seconds, anchored at the first paired sample, and measure
    each span's correlation, median delta and lock decision (Req 2.1, 2.2,
    2.3, 2.4, 2.10).

    Only *full-width* spans are emitted: the span boundaries run from the
    first paired sample's own time up to, but not including, the last
    paired sample's time, so a trailing remainder shorter than ``window_s``
    is silently dropped rather than reported as a short span. This is what
    makes ``len(result) == 0`` mean "no full span can be formed" for task
    2.2 (Req 2.7), with no separate duration arithmetic needed there.

    A span that contains no paired sample at all (a mid-activity gap in one
    of the two streams spanning an entire window) is likewise omitted: there
    is nothing to measure -- not even a degenerate correlation or a median
    -- for a span with zero paired points, and fabricating one would violate
    this codebase's absent-data rule. A span with one paired point *is*
    emitted (a median of one value is honest; a correlation is not, so it is
    ``None``).

    Reads ``samples.time_s``, ``samples.heart_rate_bpm`` and
    ``samples.cadence_rpm`` as ingested -- no resampling, forward-fill,
    interpolation or gap substitution (Req 2.10).

    Note for task 2.2, which sums these spans' durations: ``len(result) *
    window_s`` is not the assessed wall-clock extent when interior gaps
    exist. A span can hold sparse interior pairing (as few as one point)
    and still contribute its full ``window_s`` to any later duration sum --
    this is design-sanctioned, gated by the separate paired-coverage
    minimum rather than by anything in this function, not an oversight to
    correct here.
    """
    time_s = samples.time_s
    heart_rate_bpm = samples.heart_rate_bpm
    cadence_rpm = samples.cadence_rpm

    paired_indices = [
        i
        for i in range(len(time_s))
        if heart_rate_bpm[i] is not None and cadence_rpm[i] is not None
    ]
    if not paired_indices:
        return ()

    anchor_s = time_s[paired_indices[0]]
    last_paired_s = time_s[paired_indices[-1]]

    spans: list[SpanStatistic] = []
    span_index = 0
    while True:
        start_s = anchor_s + span_index * window_s
        end_s = start_s + window_s
        if end_s > last_paired_s:
            break

        indices_in_span = [i for i in paired_indices if start_s <= time_s[i] < end_s]
        if indices_in_span:
            spans.append(
                _span_statistic(
                    start_s=start_s,
                    window_s=window_s,
                    indices=indices_in_span,
                    samples=samples,
                    settings=settings,
                )
            )
        span_index += 1

    return tuple(spans)
