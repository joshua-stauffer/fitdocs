"""The ``fitdocs.metrics`` layer: pure derived-metric computation.

This package computes derived metrics (aggregates, power/HR series metrics,
zone occupancy, and training-stress numbers) as pure functions over the
activity model. It depends only on :mod:`fitdocs.model` and its own metric
submodules; it never imports the ``garmin-fit-sdk`` or :mod:`fitdocs.ingest`
(``metrics`` never imports ``ingest``).

:func:`compute_metrics` is the *facade*: one call derives the full 30-field
:class:`~fitdocs.metrics.types.DerivedMetrics` set by wiring the individual pure
functions in :mod:`fitdocs.metrics.aggregates`, :mod:`fitdocs.metrics.power`,
:mod:`fitdocs.metrics.zones`, and :mod:`fitdocs.metrics.stress`. It holds no
formulas of its own -- only composition -- so the three cross-cutting invariants
of the layer hold end to end:

- **Never raises for missing data (Req 12.1).** Every input is optional; absent
  data yields ``None`` per field, never an exception. The one exception path is
  :class:`~fitdocs.metrics.types.ZoneSpec` construction (the *caller's*
  concern), which fails fast on malformed dividers -- never inside this facade.
- **Each field independently ``None``-able (Req 12.1, 12.2).** A missing channel
  or athlete input nulls only the fields that need it; independent fields are
  computed normally.
- **Pure and deterministic (Req 13.3).** No I/O, no hidden state; identical
  inputs yield an equal ``DerivedMetrics`` on every call.

Threshold- and channel-dependence, mirroring the design's facade-mapping note:

- Intensity factor and power TSS need the caller's FTP; TRIMP needs resting and
  maximum heart rate -- absent, those fields are ``None`` (Req 8.5, 11.1, 11.2).
- Time-in-zone maps channels: heart rate and power *directly*, pace *derived*
  per sample as ``1000 / speed_mps`` s/km (a sample with ``speed <= 0`` or
  ``None`` contributes no pace). Each channel's time-in-zone is ``None`` when its
  :class:`ZoneSpec` is absent *or* the channel records no value (Req 10.1,
  10.5), and a tuple of ``len(dividers) + 1`` seconds otherwise.

**Training-impulse weighting (Amendment 1, Req 17).** ``athlete.trimp_weighting``
is resolved to a :class:`~fitdocs.metrics.sources.WeightingPair` through
:func:`fitdocs.metrics.sources.weighting_for` exactly once, before any metric
is computed, and unconditionally -- even when resting or maximum heart rate is
absent and TRIMP will be ``None`` regardless. An unrecognized selection is a
caller error and is rejected loudly there (Req 17.4) rather than only when the
metric would otherwise have been computable; a ``None`` selection resolves to
the pre-Amendment-1 default (Req 17.2). :func:`fitdocs.metrics.stress.trimp`
is then called with the resolved pair and returns both the value and the
selection that produced it in one :class:`~fitdocs.metrics.stress.TrimpResult`
(or ``None``), which this facade unpacks into
:attr:`~fitdocs.metrics.types.DerivedMetrics.trimp` and
:attr:`~fitdocs.metrics.types.DerivedMetrics.trimp_weighting` -- it does not
decide either field itself, and ``trimp_weighting`` is non-``None`` exactly
when ``trimp`` is (Req 17.6).
"""

from __future__ import annotations

from collections.abc import Sequence

from fitdocs.metrics import aggregates, power, sources, stress, zones
from fitdocs.metrics.types import AthleteInputs, DerivedMetrics, ZoneSpec
from fitdocs.model import Activity

__all__ = ["compute_metrics"]


def compute_metrics(
    activity: Activity,
    athlete: AthleteInputs | None = None,
) -> DerivedMetrics:
    """Derive the full :class:`DerivedMetrics` set for ``activity`` (Req 7-13).

    ``athlete`` supplies the optional thresholds, zone boundaries, and
    training-impulse weighting selection that some metrics need; when it is
    ``None`` an empty :class:`AthleteInputs` (all fields ``None``) is used, so
    no threshold-dependent metric is fabricated from a default. Every field is
    populated by an existing pure function; normalized power, average power,
    and moving time are each computed once and reused so the derived stress
    metrics stay consistent with the reported ones.

    Never raises for missing data (Req 12.1): each field is independently
    ``None`` when its inputs are absent (Req 12.2), and the result is pure and
    deterministic (Req 13.3). Raises :class:`ValueError` only for invalid
    caller input: a malformed :class:`ZoneSpec` at the caller's own
    construction site, never here, and (Amendment 1) an unrecognized
    ``athlete.trimp_weighting``, raised here by
    :func:`fitdocs.metrics.sources.weighting_for` (Req 17.4) -- resolved
    unconditionally, before any other metric is computed, so a caller error in
    the selection is never masked by an otherwise-absent TRIMP (Req 17.5 is
    evaluated only after this resolution succeeds).
    """
    if athlete is None:
        athlete = AthleteInputs()

    # Resolved exactly once, unconditionally, before any metric is computed
    # (Req 17.1, 17.2, 17.4): an unrecognized selection must fail loudly even
    # when TRIMP itself would be None for lack of resting/maximum heart rate.
    trimp_weighting_pair = sources.weighting_for(athlete.trimp_weighting)

    # Computed once and reused (the reference derives stress metrics from these).
    np_w = power.normalized_power(activity.samples)
    avg_power = aggregates.avg_power_w(activity)
    moving_time = aggregates.moving_time_s(activity)

    # Pace is derived per sample from speed; a non-positive or missing speed has
    # no defined pace and is excluded (contributes to no zone).
    pace_values: list[float | None] = [
        1000.0 / speed if speed is not None and speed > 0 else None
        for speed in activity.samples.speed_mps
    ]

    def _zone(
        values: Sequence[float | None], spec: ZoneSpec | None
    ) -> tuple[float, ...] | None:
        """Time-in-zone for one channel, or ``None`` when the spec or the channel
        is absent (Req 10.5). Present only when a :class:`ZoneSpec` is supplied
        *and* the channel records at least one value."""
        if spec is None or not any(v is not None for v in values):
            return None
        return zones.time_in_zone(values, activity.samples.time_s, spec)

    # The facade unpacks both fields from the one TrimpResult; it decides
    # neither itself (Req 17.6).
    trimp_result = stress.trimp(
        activity.samples,
        athlete.resting_hr_bpm,
        athlete.max_hr_bpm,
        trimp_weighting_pair,
    )

    return DerivedMetrics(
        moving_time_s=moving_time,
        elapsed_time_s=aggregates.elapsed_time_s(activity),
        distance_m=aggregates.distance_m(activity),
        avg_speed_mps=aggregates.avg_speed_mps(activity),
        max_speed_mps=aggregates.max_speed_mps(activity),
        avg_pace_s_per_km=aggregates.avg_pace_s_per_km(activity),
        avg_heart_rate_bpm=aggregates.avg_heart_rate_bpm(activity),
        max_heart_rate_bpm=aggregates.max_heart_rate_bpm(activity),
        avg_power_w=avg_power,
        max_power_w=aggregates.max_power_w(activity),
        avg_cadence_rpm=aggregates.avg_cadence_rpm(activity),
        max_cadence_rpm=aggregates.max_cadence_rpm(activity),
        normalized_power_w=np_w,
        intensity_factor=power.intensity_factor(np_w, athlete.ftp_watts),
        variability_index=power.variability_index(np_w, avg_power),
        efficiency_factor=power.efficiency_factor(activity, np_w),
        decoupling_pct=power.decoupling_pct(activity),
        elevation_gain_m=aggregates.elevation_gain_m(activity),
        elevation_loss_m=aggregates.elevation_loss_m(activity),
        min_altitude_m=aggregates.min_altitude_m(activity),
        max_altitude_m=aggregates.max_altitude_m(activity),
        min_temperature_c=aggregates.min_temperature_c(activity),
        max_temperature_c=aggregates.max_temperature_c(activity),
        avg_temperature_c=aggregates.avg_temperature_c(activity),
        hr_time_in_zone_s=_zone(activity.samples.heart_rate_bpm, athlete.hr_zones),
        power_time_in_zone_s=_zone(activity.samples.power_w, athlete.power_zones),
        pace_time_in_zone_s=_zone(pace_values, athlete.pace_zones),
        trimp=trimp_result.value if trimp_result is not None else None,
        trimp_weighting=trimp_result.weighting if trimp_result is not None else None,
        power_tss=stress.power_tss(np_w, moving_time, athlete.ftp_watts),
        calories_kcal=aggregates.calories_kcal(activity),
    )
