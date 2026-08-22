"""Session-preferred scalar aggregates: motion, heart rate, power, cadence.

Every metric here follows one rule (design "generalization"): a recorded
session-summary value wins; otherwise the value is derived from the raw sample
channel; otherwise the metric is ``None``. That rule lives in one private
helper, :func:`_session_or_channel`, so all twelve metrics apply it uniformly.

Two invariants are load-bearing:

- **``None`` means "not recorded".** Absent inputs yield ``None`` -- never a
  fabricated ``0`` or default -- and each metric is independent, so an absent
  channel never suppresses an unrelated one (Req 12.1, 12.2).
- **A recorded ``0`` is real data.** Presence is tested with ``is not None``,
  never truthiness, so a ``0`` power sample (coasting) is counted in the
  average and a recorded ``0.0`` timer is returned as-is (Req 12.3).

This module covers Req 7.1-7.6, 8.1-8.3, 9.1-9.5, and 11.3: motion, heart
rate, power, cadence, elevation, temperature, and calories.

Two values here carry a methodological choice and are cited per Req 15 to
their own record rather than to any working reference document (Req 15.5):
the moving-time movement threshold, :data:`_MOVING_SPEED_THRESHOLD_MPS`, read
from its record :data:`fitdocs.metrics.sources.MOVING_SPEED_THRESHOLD_MPS`;
and the altitude-smoothing window, :data:`_ALTITUDE_SMOOTHING_WINDOW`, read
from its record :data:`fitdocs.metrics.sources.ALTITUDE_SMOOTHING_WINDOW`.
Both records are :class:`~fitdocs.citation.FitdocsChoice`\\ s
(``MOVING_THRESHOLD_CHOICE``, ``ALTITUDE_WINDOW_CHOICE``) -- fitdocs' own
choice, not read from any published work. Every other formula in this module
carries no constant that needs a citation (Req 15.7: unit conversions and
arithmetic identities are exempt).

This module imports :mod:`fitdocs.model`, :mod:`fitdocs.metrics.sources`, and
the standard library only -- never :mod:`fitdocs.ingest` or the FIT SDK.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Final

from fitdocs.metrics import sources
from fitdocs.model import Activity, Samples

# --- shared helpers ---------------------------------------------------------


def _session_or_channel(
    session_value: float | None,
    channel_fn: Callable[[], float | None],
) -> float | None:
    """Return the recorded ``session_value`` when present, else the channel-
    derived value. A recorded ``0`` is a real value, so presence is tested with
    ``is not None`` (Req 12.3); ``channel_fn`` is evaluated lazily, only when no
    session value exists."""
    return session_value if session_value is not None else channel_fn()


def _mean_non_none(values: Iterable[float | None]) -> float | None:
    """Arithmetic mean of the non-``None`` values, or ``None`` when every value
    is ``None`` (or the channel is empty). Recorded zeros are ordinary values
    and are included in the mean (Req 12.3)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _max_non_none(values: Iterable[float | None]) -> float | None:
    """Maximum of the non-``None`` values, or ``None`` when every value is
    ``None`` (or the channel is empty)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return max(present)


def _min_non_none(values: Iterable[float | None]) -> float | None:
    """Minimum of the non-``None`` values, or ``None`` when every value is
    ``None`` (or the channel is empty). Mirrors :func:`_max_non_none`; a
    recorded ``0`` is an ordinary value and can be the minimum (Req 12.3)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return min(present)


def _last_non_none(values: Sequence[float | None]) -> float | None:
    """The last non-``None`` value in ``values``, or ``None`` when there is
    none. Used for cumulative channels (distance) where the final recorded
    reading is the total."""
    for v in reversed(values):
        if v is not None:
            return v
    return None


# --- time, distance, speed, pace (Req 7) ------------------------------------

_MOVING_SPEED_THRESHOLD_MPS: Final[float] = sources.MOVING_SPEED_THRESHOLD_MPS.value
"""The moving-time movement threshold in m/s, read from its record
(:data:`fitdocs.metrics.sources.MOVING_SPEED_THRESHOLD_MPS`) -- fitdocs' own
choice (``MOVING_THRESHOLD_CHOICE``), not read from a published work. A pair
is judged moving when the earlier sample's speed exceeds this floor, and
otherwise falls back to whether cumulative distance increases across the
pair -- so a present-but-low speed (at or below the threshold) still falls
through to the distance check, not only a speed-less channel (Req 7.1)."""


def _derive_moving_time_s(samples: Samples) -> float | None:
    """Sum ``dt`` over consecutive sample pairs judged "moving": the earlier
    sample's speed exceeds :data:`_MOVING_SPEED_THRESHOLD_MPS`, or cumulative
    distance increases across the pair. Returns ``None`` when there is no
    usable speed or distance channel to decide movement, or fewer than two
    samples."""
    time_s = samples.time_s
    speed = samples.speed_mps
    distance = samples.distance_m
    has_speed = any(s is not None for s in speed)
    has_distance = any(d is not None for d in distance)
    if not (has_speed or has_distance) or len(time_s) < 2:
        return None
    total = 0.0
    for i in range(len(time_s) - 1):
        s = speed[i]
        moving = s is not None and s > _MOVING_SPEED_THRESHOLD_MPS
        if not moving:
            d0 = distance[i]
            d1 = distance[i + 1]
            moving = d0 is not None and d1 is not None and d1 > d0
        if moving:
            total += time_s[i + 1] - time_s[i]
    return total


def moving_time_s(activity: Activity) -> float | None:
    """Moving time in seconds (Req 7.1): session timer total when recorded, else
    derived from moving sample pairs, else ``None``."""
    return _session_or_channel(
        activity.summary.total_timer_time_s,
        lambda: _derive_moving_time_s(activity.samples),
    )


def _derive_elapsed_time_s(samples: Samples) -> float | None:
    """Span of the timestamp channel: last offset minus first (``0.0`` for a
    single sample), or ``None`` when there are no samples."""
    time_s = samples.time_s
    if not time_s:
        return None
    return time_s[-1] - time_s[0]


def elapsed_time_s(activity: Activity) -> float | None:
    """Elapsed time in seconds (Req 7.2): session elapsed total when recorded,
    else the span of record timestamps, else ``None``."""
    return _session_or_channel(
        activity.summary.total_elapsed_time_s,
        lambda: _derive_elapsed_time_s(activity.samples),
    )


def distance_m(activity: Activity) -> float | None:
    """Total distance in metres (Req 7.3): session total when recorded, else the
    final cumulative value of the distance channel, else ``None``."""
    return _session_or_channel(
        activity.summary.total_distance_m,
        lambda: _last_non_none(activity.samples.distance_m),
    )


def avg_speed_mps(activity: Activity) -> float | None:
    """Average speed in m/s (Req 7.4): session value when recorded, else the mean
    of non-``None`` speed samples, else ``None``."""
    return _session_or_channel(
        activity.summary.avg_speed_mps,
        lambda: _mean_non_none(activity.samples.speed_mps),
    )


def max_speed_mps(activity: Activity) -> float | None:
    """Maximum speed in m/s (Req 7.4): session value when recorded, else the max
    of non-``None`` speed samples, else ``None``."""
    return _session_or_channel(
        activity.summary.max_speed_mps,
        lambda: _max_non_none(activity.samples.speed_mps),
    )


def avg_pace_s_per_km(activity: Activity) -> float | None:
    """Average pace in seconds per kilometre (Req 7.5): moving time divided by
    distance when both are available and distance is positive, else ``None``.
    Composed from :func:`distance_m` and :func:`moving_time_s`."""
    distance = distance_m(activity)
    moving = moving_time_s(activity)
    if distance is None or moving is None or distance <= 0:
        return None
    return moving / (distance / 1000.0)


# --- heart rate, power, cadence (Req 8.1-8.3) -------------------------------


def avg_heart_rate_bpm(activity: Activity) -> float | None:
    """Average heart rate in bpm (Req 8.1): session value when recorded, else the
    mean of non-``None`` heart-rate samples, else ``None``."""
    return _session_or_channel(
        activity.summary.avg_heart_rate_bpm,
        lambda: _mean_non_none(activity.samples.heart_rate_bpm),
    )


def max_heart_rate_bpm(activity: Activity) -> float | None:
    """Maximum heart rate in bpm (Req 8.1): session value when recorded, else the
    max of non-``None`` heart-rate samples, else ``None``."""
    return _session_or_channel(
        activity.summary.max_heart_rate_bpm,
        lambda: _max_non_none(activity.samples.heart_rate_bpm),
    )


def avg_power_w(activity: Activity) -> float | None:
    """Average power in watts (Req 8.2): session value when recorded, else the
    mean of non-``None`` power samples (recorded zeros included), else
    ``None``."""
    return _session_or_channel(
        activity.summary.avg_power_w,
        lambda: _mean_non_none(activity.samples.power_w),
    )


def max_power_w(activity: Activity) -> float | None:
    """Maximum power in watts (Req 8.2): session value when recorded, else the
    max of non-``None`` power samples, else ``None``."""
    return _session_or_channel(
        activity.summary.max_power_w,
        lambda: _max_non_none(activity.samples.power_w),
    )


def avg_cadence_rpm(activity: Activity) -> float | None:
    """Average cadence in rpm (Req 8.3): session value when recorded, else the
    mean of non-``None`` cadence samples, else ``None``."""
    return _session_or_channel(
        activity.summary.avg_cadence_rpm,
        lambda: _mean_non_none(activity.samples.cadence_rpm),
    )


def max_cadence_rpm(activity: Activity) -> float | None:
    """Maximum cadence in rpm (Req 8.3): session value when recorded, else the
    max of non-``None`` cadence samples, else ``None``."""
    return _session_or_channel(
        activity.summary.max_cadence_rpm,
        lambda: _max_non_none(activity.samples.cadence_rpm),
    )


# --- elevation, altitude, temperature, calories (Req 9, 11.3) ---------------

_ALTITUDE_SMOOTHING_WINDOW: Final[int] = sources.ALTITUDE_SMOOTHING_WINDOW.value
"""Boxcar width for altitude smoothing, read from its record
(:data:`fitdocs.metrics.sources.ALTITUDE_SMOOTHING_WINDOW`) -- fitdocs' own
choice (``ALTITUDE_WINDOW_CHOICE``), not read from a published work.
Smoothing damps single-sample jitter so a noisy altitude trace does not
inflate the derived climb (Req 9.1, 9.2)."""


def _smoothed_altitude(altitude: Sequence[float | None]) -> list[float]:
    """Altitude smoothed by a *trailing* ``None``-skipping boxcar of width
    :data:`_ALTITUDE_SMOOTHING_WINDOW`.

    This pins fitdocs' own choice of a ``None``-skipping boxcar-smoothed
    altitude to one exact window alignment: for each index ``i`` the smoothed
    point is the arithmetic mean of the non-``None`` altitude samples within
    ``altitude[max(0, i - window + 1) .. i]`` -- the ``<= window`` samples
    *ending* at ``i``. A window that contains no recorded sample produces no
    smoothed point (that index is skipped). The returned list holds the
    defined smoothed points in index order; :func:`_altitude_gain_loss` sums
    the deltas between consecutive entries. Averaging over the trailing
    window damps single-sample jitter, which is the whole reason this module
    smooths before differencing.

    A recorded ``0`` altitude is a real sample and participates in its windows
    (Req 12.3); only ``None`` is skipped.
    """
    window = _ALTITUDE_SMOOTHING_WINDOW
    smoothed: list[float] = []
    for i in range(len(altitude)):
        lo = max(0, i - window + 1)
        present = [a for a in altitude[lo : i + 1] if a is not None]
        if present:
            smoothed.append(sum(present) / len(present))
    return smoothed


def _altitude_gain_loss(altitude: Sequence[float | None]) -> tuple[float, float] | None:
    """Return ``(gain, loss)`` in metres from the smoothed altitude series, or
    ``None`` when fewer than two smoothed points are defined (nothing to
    difference).

    Over consecutive defined smoothed points, ``gain`` sums the positive deltas
    and ``loss`` sums the magnitudes of the negative deltas; both are returned as
    non-negative magnitudes. This is the shared derivation behind
    :func:`elevation_gain_m` and :func:`elevation_loss_m`.
    """
    smoothed = _smoothed_altitude(altitude)
    if len(smoothed) < 2:
        return None
    gain = 0.0
    loss = 0.0
    for earlier, later in zip(smoothed, smoothed[1:], strict=False):
        delta = later - earlier
        if delta > 0:
            gain += delta
        elif delta < 0:
            loss += -delta
    return gain, loss


def _channel_elevation_gain(altitude: Sequence[float | None]) -> float | None:
    """Smoothed-altitude elevation gain, or ``None`` when it cannot be derived."""
    result = _altitude_gain_loss(altitude)
    return result[0] if result is not None else None


def _channel_elevation_loss(altitude: Sequence[float | None]) -> float | None:
    """Smoothed-altitude elevation loss (positive magnitude), or ``None`` when it
    cannot be derived."""
    result = _altitude_gain_loss(altitude)
    return result[1] if result is not None else None


def elevation_gain_m(activity: Activity) -> float | None:
    """Elevation gain in metres (Req 9.1): session ``total_ascent`` when
    recorded, else the sum of positive deltas of the boxcar-smoothed altitude
    series (see :func:`_smoothed_altitude`), else ``None``."""
    return _session_or_channel(
        activity.summary.total_ascent_m,
        lambda: _channel_elevation_gain(activity.samples.altitude_m),
    )


def elevation_loss_m(activity: Activity) -> float | None:
    """Elevation loss in metres as a positive magnitude (Req 9.2): session
    ``total_descent`` when recorded, else the summed magnitudes of negative
    deltas of the *same* boxcar-smoothed altitude series used for gain, else
    ``None``."""
    return _session_or_channel(
        activity.summary.total_descent_m,
        lambda: _channel_elevation_loss(activity.samples.altitude_m),
    )


def min_altitude_m(activity: Activity) -> float | None:
    """Minimum altitude in metres (Req 9.3): min of non-``None`` altitude
    samples, else ``None``. No session field exists for this; it is always
    channel-derived."""
    return _min_non_none(activity.samples.altitude_m)


def max_altitude_m(activity: Activity) -> float | None:
    """Maximum altitude in metres (Req 9.3): max of non-``None`` altitude
    samples, else ``None``."""
    return _max_non_none(activity.samples.altitude_m)


def min_temperature_c(activity: Activity) -> float | None:
    """Minimum temperature in degrees Celsius (Req 9.4): min of non-``None``
    temperature samples, else ``None``."""
    return _min_non_none(activity.samples.temperature_c)


def max_temperature_c(activity: Activity) -> float | None:
    """Maximum temperature in degrees Celsius (Req 9.4): max of non-``None``
    temperature samples, else ``None``."""
    return _max_non_none(activity.samples.temperature_c)


def avg_temperature_c(activity: Activity) -> float | None:
    """Average temperature in degrees Celsius (Req 9.4): mean of non-``None``
    temperature samples (recorded zeros included), else ``None``."""
    return _mean_non_none(activity.samples.temperature_c)


def calories_kcal(activity: Activity) -> int | None:
    """Total calories in kcal (Req 11.3): the recorded session value passed
    through *unchanged*, or ``None`` when the session did not record it.

    Calories are never estimated or derived from any channel -- there is no
    fallback path here by design (Req 11.3). If the file did not record
    calories, the metric is ``None``.
    """
    return activity.summary.total_calories_kcal
