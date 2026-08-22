"""Advanced power and heart-rate series metrics: NP, IF, VI, EF, decoupling.

These are the metrics fitdocs.ai imported from Intervals.icu; fitdocs computes
them locally for offline parity (Req 8.4-8.8). Two invariants govern every
function, exactly as in :mod:`fitdocs.metrics.aggregates`:

- **``None`` means "not recorded".** Any missing input yields ``None`` -- never
  a fabricated value -- and nothing raises for absent data (Req 12.1).
- **A recorded ``0`` is real data.** A ``0`` power sample is coasting, a real
  reading counted in the resample. A ``None`` power sample is different: it
  is a genuine dropout, not a recorded absence of power, and it forward-fills
  in the normalized-power resample as the most recently *recorded*
  (non-``None``) power value -- never as a fabricated number (Req 12.3).
  Before the very first recorded power reading there is no prior value to
  forward-fill from at all, so the resample grid itself starts at the first
  recorded sample rather than fabricating anything for the dead air before
  it (a power meter that has not yet started reporting). Presence is tested
  with ``is not None``, never truthiness.

**Normalized power** implements Coggan (2003)'s steps 1-4 (window width,
fourth power, mean, fourth root) of that work's eight computation steps for
NP and TSS together (steps 5-8 carry the derivation on to TSS, whose final
scale -- step 8, the "divide by work at threshold power and multiply by
100" step -- is computed in :mod:`fitdocs.metrics.stress`):

1. **1 Hz resample.** Offsets are normalized to start at zero at the FIRST
   RECORDED (non-``None``) power sample -- not necessarily ``time_s[0]`` --
   and a uniform one-second grid ``0, 1, ..., floor(span)`` is built over
   that truncated span. Any leading samples before the first recorded one
   are dropped from the grid entirely: there is nothing to forward-fill them
   from, and truncating rather than fabricating a value for them keeps every
   window the rolling mean later takes full of genuine data (the window
   *width* is unaffected; only the dead air before the first reading is
   removed). Each grid second then takes the power of the most recent
   sample whose offset is ``<=`` that second (forward-fill); a ``None``
   power at that sample -- a dropout, not a recorded absence of power --
   itself forward-fills as the most recently *recorded* (non-``None``)
   power value, scanning every intervening raw sample rather than only the
   one the grid second lands on, so a recorded reading is never skipped
   because a later, unrecorded sample happens to share or follow within the
   same grid second. A gap genuinely carries the last known reading, never
   a fabricated number. This 1 Hz resample is fitdocs' own step, not one of
   Coggan's eight.
2. **Trailing rolling mean.** ``ra30[i]`` is the mean of the resampled power
   over the *complete* trailing window
   ``[i - _NP_ROLLING_WINDOW_S + 1 .. i]``. The series starts at the first
   index with a full window (``_NP_ROLLING_WINDOW_S - 1``); every earlier
   point, having fewer than :data:`_NP_ROLLING_WINDOW_S` samples behind it
   (counting itself), is dropped rather than averaged over a shorter span,
   matching Coggan's own step 1 ("a 30 second rolling average") exactly.
   Coggan's step 1 text reads "starting at 30 s" -- read literally against
   0-indexed grid offsets, that would place the first output at offset 30 s
   (index 30, a 31-sample window). This module instead treats "30 s"/"30
   second" as naming the window's *width* (30 samples), so the first
   complete window is the 30 samples at offsets ``0 .. 29`` and the first
   ``ra30`` value lands at index 29 (offset 29 s), not index 30. Which
   reading other implementations take is not something this layer has
   established -- ``NP_MIN_SPAN_CHOICE.search_basis`` records that no live
   literature-search tool was available -- so no claim is made about it
   here. The choice is recorded because the text admits both readings and
   nothing else in this module says which one is taken.
3. **Averaging-exponent mean.**
   ``NP = mean(ra30[i] ** _NP_AVERAGING_EXPONENT) ** (1 / _NP_AVERAGING_EXPONENT)``
   -- Coggan's own steps 2-4.

Normalized power requires at least :data:`_NP_MIN_SPAN_S` of power-stream span
(``time_s[-1] - time_s[0] >= _NP_MIN_SPAN_S``) and at least one recorded power
sample; otherwise it is ``None`` (a no-power activity has no meaningful NP, so
an entirely ``None`` power channel returns ``None`` rather than a resample of
all zeros).

Three values here carry a methodological choice and are cited per Req 15 to
their own record rather than to any working reference document (Req 15.5):
the rolling-window width, :data:`_NP_ROLLING_WINDOW_S`, and the averaging
exponent, :data:`_NP_AVERAGING_EXPONENT`, each read from its own record
(:data:`fitdocs.metrics.sources.NP_ROLLING_WINDOW_S`,
:data:`fitdocs.metrics.sources.NP_AVERAGING_EXPONENT`) governed by Coggan
(2003); and the minimum power-stream span, :data:`_NP_MIN_SPAN_S`, read from
its record (:data:`fitdocs.metrics.sources.NP_MIN_SPAN_S`) -- fitdocs' own
choice (``NP_MIN_SPAN_CHOICE``), not read from a published work. There is no
fourth, fill-value constant: every 1 Hz resample point is either a genuine
recorded reading (a coasting ``0``, or the most recently recorded value
carried across a dropout) or, before the first recorded reading, simply
absent from the grid rather than fabricated -- Req 12.3 and Req 15.7's
"a value substituted for an absent reading carries a methodological choice"
therefore never fires here at all. The averaging exponent's root is
taken as that same exponent's reciprocal (``1 / _NP_AVERAGING_EXPONENT``)
rather than an independent literal, so the power and its root cannot drift
apart under a future change to the record.

**Efficiency factor** and **decoupling** follow the pinned definitions from
``research.md`` ("Decision: pin the formulas the reference leaves
undocumented"): the output channel is normalized power (or, per half for
decoupling, mean power) for the bike modality and speed for the run modality;
other modalities have no defined output and yield ``None``.

This module imports :mod:`fitdocs.model`, :mod:`fitdocs.metrics.aggregates`,
:mod:`fitdocs.metrics.sources` (intra-``metrics`` reuse is allowed), and the
standard library only -- never :mod:`fitdocs.ingest` or the FIT SDK.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from typing import Final

from fitdocs.metrics import aggregates, sources
from fitdocs.model import Activity, Modality, Samples

_NP_MIN_SPAN_S: Final[float] = sources.NP_MIN_SPAN_S.value
"""Minimum power-stream span for normalized power below which it is
``None``, read from its record (:data:`fitdocs.metrics.sources.NP_MIN_SPAN_S`)
-- fitdocs' own choice (``NP_MIN_SPAN_CHOICE``), not read from a published
work."""

_NP_ROLLING_WINDOW_S: Final[int] = sources.NP_ROLLING_WINDOW_S.value
"""Width in seconds of the trailing rolling-mean window (``ra30``), read from
its record (:data:`fitdocs.metrics.sources.NP_ROLLING_WINDOW_S`) -- Coggan
(2003)'s own step 1."""

_NP_AVERAGING_EXPONENT: Final[int] = sources.NP_AVERAGING_EXPONENT.value
"""The normalized-power averaging exponent -- the power raised before the
mean, and (as its reciprocal) the root taken after it -- read from its record
(:data:`fitdocs.metrics.sources.NP_AVERAGING_EXPONENT`) -- Coggan (2003)'s
own steps 2-4. Collapsing what were two independent literals (the power and
its root) into one constant with the root as its reciprocal makes it
impossible for the pair to drift apart."""

# --- normalized power (Req 8.4) ---------------------------------------------


def _resample_power_1hz(
    time_s: Sequence[float], power_w: Sequence[int | None]
) -> list[float]:
    """Forward-fill ``power_w`` onto a 1 Hz grid starting at the first
    RECORDED power sample.

    There is nothing to forward-fill a leading ``None`` stretch from -- a
    power meter that has not yet started reporting -- so the grid is
    truncated to start where real data starts, rather than fabricating a
    value for the dead air before it: offsets are shifted to zero at the
    first non-``None`` entry in ``power_w`` (not necessarily ``time_s[0]``),
    and a uniform one-second grid ``0, 1, ..., floor(span)`` is built from
    there. Returns ``[]`` if ``power_w`` is entirely ``None`` (nothing to
    resample at all).

    For each whole second, the power of the most recent sample at or before
    that second is taken (forward-fill). A ``None`` power reading at that
    sample is a dropout, not a recorded absence of power, and itself
    forward-fills as the most recently *recorded* (non-``None``) power
    value: every raw sample between the previous grid second's pick and this
    one is scanned for a recorded reading, not only the single sample the
    grid second lands on, so a recorded value is never skipped merely
    because a later, unrecorded sample shares or follows within the same
    grid second. A gap carries the last known reading, never a fabricated
    number.
    """
    first_recorded = next(
        (i for i, value in enumerate(power_w) if value is not None), None
    )
    if first_recorded is None:
        return []
    first_value = power_w[first_recorded]
    assert first_value is not None  # by construction of first_recorded above
    start = time_s[first_recorded]
    rel = [t - start for t in time_s]  # rel[first_recorded] == 0.0
    span = rel[-1]
    resampled: list[float] = []
    last_recorded = float(first_value)
    scanned_through = first_recorded
    for sec in range(int(span) + 1):
        # Most recent sample whose offset <= this grid second (forward-fill).
        idx = bisect.bisect_right(rel, float(sec)) - 1
        # Fold in every recorded sample between the last one already folded
        # in and this one -- not only the single sample the bisect landed
        # on -- so a recorded reading between two grid seconds is never lost.
        for j in range(scanned_through + 1, idx + 1):
            candidate = power_w[j]
            if candidate is not None:
                last_recorded = float(candidate)
        scanned_through = idx
        resampled.append(last_recorded)
    return resampled


def _trailing_rolling_mean(values: Sequence[float], window: int) -> list[float]:
    """Mean of ``values`` over each complete trailing window
    ``[i - window + 1 .. i]``.

    The series starts at the first index with a full window
    (``window - 1``); every earlier point -- with fewer than ``window``
    points behind it -- is dropped rather than averaged over a shorter span,
    per Coggan (2003)'s own step 1 ("a 30 second rolling average"), which
    specifies windows of the full width throughout. Returns an empty list
    when ``values`` has fewer than ``window`` points. Computed with a running
    sum in one pass.
    """
    if len(values) < window:
        return []
    running = sum(values[:window])
    result: list[float] = [running / window]
    for i in range(window, len(values)):
        running += values[i] - values[i - window]
        result.append(running / window)
    return result


def normalized_power(samples: Samples) -> float | None:
    """Normalized power in watts (Req 8.4), or ``None``.

    Returns ``None`` when there are fewer than two samples, when the
    *overall* power-stream span (including any leading dropout) is under
    :data:`_NP_MIN_SPAN_S`, or when the power channel is entirely unrecorded
    (all ``None``) -- a no-power activity has no meaningful NP. Otherwise
    resamples power to 1 Hz starting at the first RECORDED sample (a
    recorded ``0`` is kept as real coasting data; an unrecorded ``None``
    sample forward-fills as the most recently recorded power value instead;
    a leading stretch before the first recorded sample is truncated rather
    than fabricated), takes the :data:`_NP_ROLLING_WINDOW_S`-second trailing
    rolling mean ``ra30`` over the truncated series, and returns
    ``mean(ra30 ** _NP_AVERAGING_EXPONENT) ** (1 / _NP_AVERAGING_EXPONENT)``.
    If truncation leaves fewer resampled points than the rolling window
    needs, ``ra30`` is empty and this returns ``None`` (the same guard that
    handles a too-short activity) rather than a value computed from mostly
    fabricated data. A recorded ``0`` power sample is real coasting data and
    is kept (Req 12.3).
    """
    time_s = samples.time_s
    power_w = samples.power_w
    if len(time_s) < 2:
        return None
    if time_s[-1] - time_s[0] < _NP_MIN_SPAN_S:
        return None
    if all(p is None for p in power_w):
        return None
    resampled = _resample_power_1hz(time_s, power_w)
    ra30 = _trailing_rolling_mean(resampled, _NP_ROLLING_WINDOW_S)
    if not ra30:
        return None
    exponent = _NP_AVERAGING_EXPONENT
    averaging_mean = sum(value**exponent for value in ra30) / len(ra30)
    return float(averaging_mean ** (1 / exponent))


# --- intensity factor and variability index (Req 8.5, 8.6) ------------------


def intensity_factor(np_w: float | None, ftp: float | None) -> float | None:
    """Intensity factor: normalized power divided by caller FTP (Req 8.5).

    ``None`` unless both ``np_w`` and ``ftp`` are present and ``ftp`` is
    positive.
    """
    if np_w is None or ftp is None or ftp <= 0:
        return None
    return np_w / ftp


def variability_index(np_w: float | None, avg_power: float | None) -> float | None:
    """Variability index: normalized power divided by average power (Req 8.6).

    ``None`` unless both ``np_w`` and ``avg_power`` are present and
    ``avg_power`` is positive.
    """
    if np_w is None or avg_power is None or avg_power <= 0:
        return None
    return np_w / avg_power


# --- efficiency factor (Req 8.7) --------------------------------------------


def efficiency_factor(activity: Activity, np_w: float | None) -> float | None:
    """Efficiency factor: output divided by average heart rate (Req 8.7).

    The output is normalized power (``np_w``) for the bike modality and average
    speed in metres per minute (``avg_speed_mps * 60``) for the run modality;
    every other modality has no defined output and yields ``None``. Average
    speed and heart rate are read through :mod:`fitdocs.metrics.aggregates` so
    the session-preferred-then-channel rule applies uniformly. ``None`` when the
    output or the average heart rate is unavailable (or the heart rate is not
    positive).
    """
    avg_hr = aggregates.avg_heart_rate_bpm(activity)
    if avg_hr is None or avg_hr <= 0:
        return None
    if activity.modality == Modality.BIKE:
        output = np_w
    elif activity.modality == Modality.RUN:
        avg_speed = aggregates.avg_speed_mps(activity)
        output = avg_speed * 60.0 if avg_speed is not None else None
    else:
        return None
    if output is None:
        return None
    return output / avg_hr


# --- aerobic decoupling (Req 8.8) -------------------------------------------


def _half_efficiency(
    time_s: Sequence[float],
    output: Sequence[float | None],
    heart_rate: Sequence[int | None],
    in_half: Callable[[float], bool],
) -> float | None:
    """Output-to-HR ratio over one activity half, using only paired samples.

    A sample is *paired* when both its output and heart rate are recorded; the
    ratio is ``mean(paired output) / mean(paired HR)``. Returns ``None`` when
    the half has no paired sample or the paired heart-rate mean is zero.
    """
    outputs: list[float] = []
    heart_rates: list[float] = []
    for i, offset in enumerate(time_s):
        if not in_half(offset):
            continue
        out_value = output[i]
        hr_value = heart_rate[i]
        if out_value is not None and hr_value is not None:
            outputs.append(float(out_value))
            heart_rates.append(float(hr_value))
    if not outputs:
        return None
    mean_hr = sum(heart_rates) / len(heart_rates)
    if mean_hr == 0:
        return None
    return (sum(outputs) / len(outputs)) / mean_hr


def decoupling_pct(activity: Activity) -> float | None:
    """Aerobic decoupling as a percentage (Req 8.8), or ``None``.

    Splits the samples at the elapsed-time midpoint
    ``mid = time_s[0] + (time_s[-1] - time_s[0]) / 2`` -- first half is
    ``time_s <= mid``, second half is ``time_s > mid``. The output channel is
    power for the bike modality and speed for the run modality; other modalities
    yield ``None``. Per half the efficiency is ``mean(output) / mean(HR)`` over
    samples where both are recorded, and

        ``decoupling = (EF_first - EF_second) / EF_first * 100``.

    A positive result is aerobic drift (heart rate rising relative to output).
    Returns ``None`` unless both halves carry at least one paired sample and the
    first half's efficiency is non-zero.
    """
    if activity.modality == Modality.BIKE:
        output: Sequence[float | None] = activity.samples.power_w
    elif activity.modality == Modality.RUN:
        output = activity.samples.speed_mps
    else:
        return None
    time_s = activity.samples.time_s
    if not time_s:
        return None
    heart_rate = activity.samples.heart_rate_bpm
    mid = time_s[0] + (time_s[-1] - time_s[0]) / 2.0
    ef_first = _half_efficiency(time_s, output, heart_rate, lambda t: t <= mid)
    ef_second = _half_efficiency(time_s, output, heart_rate, lambda t: t > mid)
    if ef_first is None or ef_second is None or ef_first == 0:
        return None
    return (ef_first - ef_second) / ef_first * 100.0
