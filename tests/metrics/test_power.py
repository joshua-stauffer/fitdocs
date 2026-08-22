"""Hand-computed tests for the advanced power and heart-rate series metrics.

These exercise :mod:`fitdocs.metrics.power`: normalized power, intensity factor,
variability index, efficiency factor, and aerobic decoupling. Every expected
number below is hand-computed so the formulas are pinned, not merely
snapshotted.

The invariants under test:

* **NP from the 1 Hz resample** -- constant power resamples to itself so NP
  equals that constant; a series that varies on a timescale longer than the
  30 s rolling window yields NP *above* the arithmetic mean power (the
  fourth-power weighting), while sub-window jitter is smoothed away (Req 8.4).
* **Threshold-gated ratios** -- intensity factor needs a caller FTP, variability
  index needs average power; either missing -> ``None`` (Req 8.5, 8.6).
* **Efficiency factor by modality** -- output is NP for bike, avg speed in m/min
  for run, and undefined (``None``) for other modalities (Req 8.7).
* **Decoupling across halves** -- positive when the output-to-HR ratio drops in
  the second half (aerobic drift); ``None`` unless both halves carry paired
  output+HR samples (Req 8.8).
* **None propagation** -- nothing raises for missing data; absent inputs yield
  ``None`` throughout (Req 12.1).
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect

import pytest

from fitdocs import metrics
from fitdocs.metrics import power, sources
from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)

# --- test-model builders ----------------------------------------------------


def _summary(
    *,
    avg_heart_rate_bpm: int | None = None,
    max_heart_rate_bpm: int | None = None,
    avg_power_w: int | None = None,
    avg_speed_mps: float | None = None,
) -> SessionSummary:
    """A ``SessionSummary`` with every field ``None`` except those overridden.

    Only the fields these series metrics read through the aggregate helpers
    (average HR, average speed) are exposed; the rest stay ``None``.
    """
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=avg_heart_rate_bpm,
        max_heart_rate_bpm=max_heart_rate_bpm,
        avg_power_w=avg_power_w,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=avg_speed_mps,
        max_speed_mps=None,
    )


def _samples(
    time_s: tuple[float, ...] = (),
    *,
    heart_rate_bpm: tuple[int | None, ...] | None = None,
    power_w: tuple[int | None, ...] | None = None,
    speed_mps: tuple[float | None, ...] | None = None,
) -> Samples:
    """A ``Samples`` whose channels default to all-``None`` arrays of length
    ``len(time_s)``; pass a channel explicitly to populate it. Channels these
    metrics never read (position, altitude, temperature, ...) stay all-``None``.
    """
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm if heart_rate_bpm is not None else none_ints,
        power_w=power_w if power_w is not None else none_ints,
        cadence_rpm=none_floats,
        speed_mps=speed_mps if speed_mps is not None else none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _activity(
    *,
    modality: Modality = Modality.BIKE,
    summary: SessionSummary | None = None,
    samples: Samples | None = None,
) -> Activity:
    """An otherwise-trivial ``Activity`` with a chosen modality, summary, and
    samples. Modality drives the efficiency-factor / decoupling output channel."""
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="", source_path=None, decode_errors=()),
        sport=Sport.RIDE,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=summary if summary is not None else _summary(),
        laps=(),
        samples=samples if samples is not None else _samples(),
        sets=(),
        devices=(),
    )


# --- module wiring ----------------------------------------------------------


def test_module_imports_from_metrics_package() -> None:
    # power lives under the metrics package (design File Structure Plan).
    assert power is metrics.power


# --- 1. normalized power: constant power resamples to itself (Req 8.4) -------


def test_normalized_power_constant_equals_that_power() -> None:
    # Constant 200 W at 1 Hz for 2400 s (span 2399 >= 30). The 1 Hz resample is
    # all 200, the 30 s trailing rolling mean is all 200, and
    # NP = mean(200**4) ** 0.25 = (200**4) ** 0.25 = 200.0 exactly.
    time_s = tuple(float(k) for k in range(2400))
    watts: tuple[int | None, ...] = (200,) * 2400
    samples = _samples(time_s, power_w=watts)
    np_value = power.normalized_power(samples)
    assert np_value == pytest.approx(200.0)


# --- 2. normalized power: variable series inflates NP above avg (Req 8.4) ----


def test_normalized_power_variable_exceeds_average_power() -> None:
    # 60 s blocks alternating 300 W and 0 W, six blocks (three high, three low)
    # = 360 s at 1 Hz. The arithmetic mean power is 150 W. Because the power
    # varies on a 60 s timescale -- longer than the 30 s rolling window -- the
    # rolling mean still reaches 300 W in the steady centre of each high block,
    # so the fourth-power mean pushes NP well ABOVE the 150 W average (the whole
    # point of normalized power). NP can never exceed the peak 300 W.
    block_s = 60
    n_blocks = 6
    watts_list: list[int | None] = []
    for b in range(n_blocks):
        watts_list.extend([300 if b % 2 == 0 else 0] * block_s)
    watts: tuple[int | None, ...] = tuple(watts_list)
    time_s = tuple(float(k) for k in range(len(watts)))
    avg_power = sum(w for w in watts if w is not None) / len(watts)
    assert avg_power == pytest.approx(150.0)

    np_value = power.normalized_power(_samples(time_s, power_w=watts))
    assert np_value is not None
    assert np_value > avg_power  # fourth-power weighting inflates NP
    assert np_value < 300.0  # ... but never past the peak power


def test_normalized_power_exact_value_pins_fourth_power_exponent() -> None:
    # Two 60 s blocks at 1 Hz -- 300 W then 100 W -- span 119 s (>= 30 s), 120
    # resampled points (the 1 Hz resample is the identity for 1 Hz integer
    # times). Task 13.1: the 30 s trailing rolling mean ``ra30`` only exists
    # once a FULL 30 s window is behind the index, so the series starts at
    # i = 29 (not i = 0) and runs for 91 points (i = 29..119), not 120. Over
    # that series ``ra30`` is exactly:
    #   * 300.0 for i = 29..59  (31 points; window wholly inside the 300 W
    #     block),
    #   * a linear ramp 300 -> 100 over i = 60..88  (29 points; window
    #     straddles the step, e.g. ra30[60] = (29*300 + 1*100)/30 =
    #     8800/30 = 293.333...),
    #   * 100.0 for i = 89..119 (31 points; window wholly inside the 100 W
    #     block).
    # (The now-removed leading partial-window points i = 0..28 were also
    # 300.0 each -- the 300 W block starts at t=0 -- so this fixture pins the
    # window-completeness change on point COUNT/weighting, not on any of
    # those points individually being wrong.)
    #
    # NP = mean(ra30 ** 4) ** 0.25. The ramp terms are thirds (e.g.
    # ra30[60] = 880/3, so ra30[60]**4 has denominator 3**4 = 81); summing
    # the 31 terms of 300**4, the 29 ramp terms (each an exact fraction with
    # denominator dividing 81), and the 31 terms of 100**4 gives the exact
    # fraction sum(ra30 ** 4) = 26143379840000/81 (independent
    # reimplementation, not the module under test). Dividing by the 91-point
    # series length: mean(ra30**4) = 26143379840000/7371 =
    # 3546788745.0820785..., and NP = that value ** 0.25 =
    # 244.03877169307256 W. This literal is hand-derived from an
    # INDEPENDENT reimplementation of the documented algorithm and asserted
    # directly (NOT recomputed via the module).
    #
    # Before this change (partial-window ``ra30`` of 120 points, i = 0..119,
    # with i = 0..28 an extra 29 points ALSO at 300.0) the same fixture gave
    # NP = 261.09384206589294 W -- HIGHER, not lower, because those 29 extra
    # points diluted the ramp-down's share of the mean (they inflate the
    # count of high-value points relative to the low/ramp ones). This
    # fixture alone does not demonstrate the amendment's general "dropping
    # LOW leading points raises NP" direction -- that requires leading points
    # BELOW the window's eventual value, which this fixture's constant-300
    # start does not have; see
    # ``test_normalized_power_complete_window_raises_np_over_partial_window``
    # below for that case.
    #
    # It still pins the exponent at 4: the quadratic mean (exponent 2 -- the
    # mutation) of the SAME 91-point complete-window series gives
    # 218.64272181950125 W, 25.40 W away from the literal below (over 25 W).
    # So mutating the module's exponent 4 -> 2 fails this assertion, whereas
    # the loose-bounds test above (150 < NP < 300) survives that mutation.
    block_s = 60
    watts: tuple[int | None, ...] = tuple([300] * block_s + [100] * block_s)
    time_s = tuple(float(k) for k in range(len(watts)))

    np_value = power.normalized_power(_samples(time_s, power_w=watts))
    assert np_value is not None
    assert np_value == pytest.approx(244.03877169307256, rel=1e-9)
    # Sanity rails: the fourth-power mean sits strictly between the arithmetic
    # mean (200 W) and the peak (300 W).
    assert 200.0 < np_value < 300.0


def test_normalized_power_complete_window_raises_np_over_partial_window() -> None:
    # Task 13.1's actual claim: dropping the LOW leading partial-window
    # averages RAISES normalized power. That direction needs a fixture whose
    # leading points are below the window's eventual steady value -- unlike
    # the step-fixture above, whose 300 W block starts at t=0 (so its
    # leading partial windows are already at the steady value, not below
    # it).
    #
    # Fixture: 29 s at 0 W (a cold start / not-yet-pedaling stretch -- one
    # second short of the 30 s window), then 300 W for the remaining 61 s
    # (90 samples total, span 89 s >= 30 s min span).
    #
    # OLD (partial-window) ra30, independently reimplemented:
    #   * i = 0..28 (29 points): window is the i+1 leading zeros only ->
    #     ra30[i] = 0.0 each (all still inside the 0 W stretch).
    #   * i = 29..89 (61 points, the full 90-sample series): i = 29 is the
    #     first index with a full 30 s window, so old and new ``ra30`` are
    #     IDENTICAL from here on (see below).
    # NEW (complete-window) ra30 starts at i = 29 directly, i.e. it is
    # exactly the old series with the leading 29 zeros dropped -- the old
    # series is `[0.0] * 29 + new_ra30` (90 points total; new_ra30 has 61).
    #
    # new_ra30, worked by hand: for i = 29..57 (29 points) the window
    # [i-29..i] holds (58-i) leftover zeros and (i-28) 300s, so
    # ra30[i] = 300*(i-28)/30 = 10*(i-28) W -- an exact-integer ramp
    # 10, 20, ..., 290 for i = 29..57. For i = 58..89 (32 points) the window
    # no longer touches the zero stretch at all, so ra30[i] = 300.0 exactly.
    #
    # sum(new_ra30 ** 4) = sum_{k=1}^{29} (10k)**4 + 32 * 300**4
    #                    = 10000 * sum_{k=1}^{29} k**4 + 32 * 8.1e9
    #   sum_{k=1}^{29} k**4 = 29*30*59*2609/30 = 29*59*2609 = 4,463,999
    #                       (closed form n(n+1)(2n+1)(3n^2+3n-1)/30, n=29)
    #   => 10000 * 4,463,999 = 44,639,990,000
    #   => 32 * 8,100,000,000 = 259,200,000,000
    #   => sum(new_ra30 ** 4) = 303,839,990,000 EXACTLY (integer arithmetic,
    #      independent of the module under test).
    #
    # NEW: mean over 61 points = 303,839,990,000 / 61 = 4,980,983,442.62295...
    #   NP_new = that ** 0.25 = 265.66159423758893 W.
    # OLD: mean over 90 points (61 nonzero + 29 exact zeros contribute
    #   nothing to the sum) = 303,839,990,000 / 90 = 3,375,999,888.88888...
    #   NP_old = that ** 0.25 = 241.0463756814967 W.
    #
    # NP_old and NP_new share the same sum(ra30**4); they differ only in the
    # divisor (90 vs 61), so NP_old = NP_new * (61/90)**0.25 exactly -- a
    # closed-form relationship confirming both by hand, not one recomputed
    # from the other via the module.
    #
    # Direction: NP_new (265.66 W) > NP_old (241.05 W) -- dropping the 29 low
    # (0 W) leading partial-window points RAISES normalized power, exactly
    # the amendment's stated direction.
    zeros_s = 29
    plateau_s = 61
    watts: tuple[int | None, ...] = tuple([0] * zeros_s + [300] * plateau_s)
    time_s = tuple(float(k) for k in range(len(watts)))

    np_value = power.normalized_power(_samples(time_s, power_w=watts))
    assert np_value is not None
    assert np_value == pytest.approx(265.66159423758893, rel=1e-9)
    # Direction claim, asserted explicitly (not merely implied by the exact
    # value above): the complete-window NP sits strictly above what the
    # removed partial-window algorithm would have produced on this same
    # series.
    old_partial_window_np = 241.0463756814967
    assert np_value > old_partial_window_np


# --- 3. normalized power: too-short / no-power -> None (Req 8.4, 12.1) -------


def test_normalized_power_none_below_thirty_seconds() -> None:
    # 20 samples spanning 19 s (< 30 s of power-stream span) -> None.
    time_s = tuple(float(k) for k in range(20))
    watts: tuple[int | None, ...] = (100,) * 20
    assert power.normalized_power(_samples(time_s, power_w=watts)) is None


def test_normalized_power_none_when_power_channel_entirely_absent() -> None:
    # A 60 s span but the power channel is entirely None -> NP is not meaningful
    # for a no-power activity -> None (never a fabricated 0.0).
    time_s = tuple(float(k) for k in range(60))
    assert power.normalized_power(_samples(time_s)) is None


def test_normalized_power_none_for_empty_samples() -> None:
    assert power.normalized_power(_samples(())) is None


def test_normalized_power_coasting_zeros_are_real_data() -> None:
    # A recorded 0 W (coasting) is real and stays 0 in the resample; only a None
    # power sample becomes 0 for "not recorded". Mixed 250/0 over 60 s computes
    # a finite NP without raising, and it stays within [0, peak].
    time_s = tuple(float(k) for k in range(60))
    watts: tuple[int | None, ...] = tuple(250 if k % 2 == 0 else 0 for k in range(60))
    np_value = power.normalized_power(_samples(time_s, power_w=watts))
    assert np_value is not None
    assert 0.0 < np_value <= 250.0


def test_resample_power_1hz_none_gap_forward_fills_the_preceding_sample() -> None:
    # Direct unit test on the resample helper itself (Req 12.3, maintainer
    # ruling 2026-07-30: an unrecorded (``None``) power sample is a dropout,
    # not coasting, and forward-fills as the most recently RECORDED value --
    # never a fabricated 0.0). Raw samples at 1 Hz: 300 W, then two
    # consecutive dropouts, then 100 W. Distinguishing values on either side
    # of the gap (300 before, 100 after) rule out both a fabricated-zero fill
    # AND a "fill with the value that comes after" rule -- only "carry the
    # LAST RECORDED value forward" produces this exact series.
    time_s = (0.0, 1.0, 2.0, 3.0)
    power_w: tuple[int | None, ...] = (300, None, None, 100)
    resampled = power._resample_power_1hz(time_s, power_w)
    assert resampled == [300.0, 300.0, 300.0, 100.0]


def test_resample_power_1hz_scans_every_sample_between_two_grid_seconds() -> None:
    # Reviewer-found defect (2026-07-30 remediation round): a naive
    # implementation that updates ``last_recorded`` only from the single raw
    # sample the bisect happens to land on for a given grid second can skip
    # an intervening recorded reading entirely when two raw samples share (or
    # fall within) the same grid second. Raw samples at t = 0.0, 1.0, 1.0, 2.0
    # with power 100, 200, None, None: the recorded 200 W at the SECOND t=1.0
    # sample must still be picked up for grid second 1, even though the
    # sample the bisect lands on for that second is the trailing ``None`` --
    # scanning every sample between the previous grid second's pick and this
    # one (not only the bisected one) is what finds it.
    time_s = (0.0, 1.0, 1.0, 2.0)
    power_w: tuple[int | None, ...] = (100, 200, None, None)
    resampled = power._resample_power_1hz(time_s, power_w)
    assert resampled == [100.0, 200.0, 200.0]


def test_resample_power_1hz_leading_none_truncates_the_grid() -> None:
    # Maintainer ruling (2026-07-30, extending the forward-fill ruling):
    # before the very first recorded reading there is no prior value to
    # forward-fill from at all, so there is nothing to fabricate a value
    # for either -- the resample grid itself starts at the first RECORDED
    # sample instead. Two leading Nones (a power meter not yet reporting),
    # then a recorded 200 W, then a trailing None (forward-fills from that
    # 200 W): the grid has only 2 points (offsets 0, 1 relative to the first
    # recorded sample at raw time 2.0), not 4 -- the leading dead air is
    # gone, not replaced by any fill value.
    time_s = (0.0, 1.0, 2.0, 3.0)
    power_w: tuple[int | None, ...] = (None, None, 200, None)
    resampled = power._resample_power_1hz(time_s, power_w)
    assert resampled == [200.0, 200.0]


def test_resample_power_1hz_returns_empty_when_nothing_is_ever_recorded() -> None:
    # Defensive case: a power channel that is entirely None has no first
    # recorded sample to start the grid from, so there is nothing to
    # resample at all -- returns [] rather than raising or fabricating a
    # series. (normalized_power itself already refuses this case earlier,
    # via its own all-None guard, so this path is reached directly here
    # rather than through that function.)
    time_s = (0.0, 1.0, 2.0)
    power_w: tuple[int | None, ...] = (None, None, None)
    assert power._resample_power_1hz(time_s, power_w) == []


def test_normalized_power_leading_dropout_is_truncated_not_fabricated() -> None:
    # Quantifies the leading-dropout fix directly: a 300 W ride whose power
    # meter takes 5 s / 10 s / 20 s to start reporting, followed by 90 s of
    # steady 300 W (total span comfortably above the 30 s minimum either
    # way). Truncating the grid to start at the first recorded sample turns
    # this into a genuinely constant 300 W stream once resampled, so NP is
    # EXACTLY 300.0 regardless of how long the lead-in dropout is -- proving
    # the leading None samples are dropped rather than dragging NP down as
    # a fabricated 0.0 would (a fabricated-zero fill would instead pull NP
    # below 300 by an amount that grows with the dropout's length).
    plateau_s = 90
    for lead_in in (5, 10, 20):
        watts: tuple[int | None, ...] = tuple([None] * lead_in) + tuple(
            [300] * plateau_s
        )
        time_s = tuple(float(k) for k in range(len(watts)))
        np_value = power.normalized_power(_samples(time_s, power_w=watts))
        assert np_value is not None
        assert np_value == pytest.approx(300.0), lead_in


def test_normalized_power_none_gap_forward_fills_from_preceding_sample() -> None:
    # NP-level pin, same maintainer ruling: a defined power channel over a
    # 59 s span (1 Hz, >= 30 s) with a 10 s dropout in the MIDDLE (idx
    # 25..34), 300 W before the gap and 100 W after it -- distinguishing
    # values on either side, unlike a same-value-both-sides fixture, which
    # cannot tell "forward-fill the preceding value" apart from "forward-fill
    # the following value" or "drop the gap" (all three would coincide when
    # both sides are equal).
    n = 60
    gap = range(25, 35)
    time_s = tuple(float(k) for k in range(n))
    p_none: tuple[int | None, ...] = tuple(
        None if k in gap else (300 if k < 25 else 100) for k in range(n)
    )
    # The forward-fill this session's ruling actually specifies: the gap
    # carries the PRECEDING recorded value (300), built by hand rather than
    # via the module under test.
    p_forward_filled: tuple[int | None, ...] = tuple(
        300 if k < 35 else 100 for k in range(n)
    )
    # The two rejected alternatives: fabricate a 0.0 (the old, now-falsified
    # behavior)...
    p_zero: tuple[int | None, ...] = tuple(
        0 if k in gap else (300 if k < 25 else 100) for k in range(n)
    )
    # ... and carry the FOLLOWING value backward instead of the preceding one
    # forward.
    p_backward_filled: tuple[int | None, ...] = tuple(
        300 if k < 25 else 100 for k in range(n)
    )

    np_none = power.normalized_power(_samples(time_s, power_w=p_none))
    np_forward_filled = power.normalized_power(
        _samples(time_s, power_w=p_forward_filled)
    )
    np_zero = power.normalized_power(_samples(time_s, power_w=p_zero))
    np_backward_filled = power.normalized_power(
        _samples(time_s, power_w=p_backward_filled)
    )
    assert np_none is not None
    assert np_forward_filled is not None
    assert np_zero is not None
    assert np_backward_filled is not None

    # Pins the actual rule: the None-gap series matches carrying the
    # preceding value forward, exactly.
    assert np_none == pytest.approx(np_forward_filled)
    # ... and rules out both rejected alternatives, which give materially
    # different values on this fixture (distinguishing values on either side
    # of the gap is what makes this comparison meaningful).
    assert np_none != pytest.approx(np_zero)
    assert np_none != pytest.approx(np_backward_filled)


# --- 4. intensity factor (Req 8.5) ------------------------------------------


def test_intensity_factor_np_over_ftp() -> None:
    assert power.intensity_factor(200.0, 200.0) == pytest.approx(1.0)
    assert power.intensity_factor(240.0, 200.0) == pytest.approx(1.2)


def test_intensity_factor_none_without_np_or_ftp() -> None:
    assert power.intensity_factor(200.0, None) is None
    assert power.intensity_factor(None, 200.0) is None
    assert power.intensity_factor(None, None) is None


def test_intensity_factor_none_for_nonpositive_ftp() -> None:
    # A zero or negative FTP cannot yield a meaningful ratio -> None (no
    # ZeroDivision, no fabricated value).
    assert power.intensity_factor(200.0, 0.0) is None
    assert power.intensity_factor(200.0, -50.0) is None


# --- 5. variability index (Req 8.6) -----------------------------------------


def test_variability_index_np_over_avg_power() -> None:
    assert power.variability_index(200.0, 200.0) == pytest.approx(1.0)
    # NP above avg -> VI above 1 (220 / 150).
    assert power.variability_index(220.0, 150.0) == pytest.approx(220.0 / 150.0)


def test_variability_index_none_without_inputs() -> None:
    assert power.variability_index(200.0, None) is None
    assert power.variability_index(None, 200.0) is None
    assert power.variability_index(200.0, 0.0) is None


# --- 6. efficiency factor by modality (Req 8.7) -----------------------------


def test_efficiency_factor_bike_is_np_over_avg_hr() -> None:
    # Bike: output = NP. NP 240, avg HR 150 -> EF = 240 / 150 = 1.6.
    act = _activity(
        modality=Modality.BIKE,
        summary=_summary(avg_heart_rate_bpm=150),
    )
    assert power.efficiency_factor(act, 240.0) == pytest.approx(1.6)


def test_efficiency_factor_run_is_avg_speed_mpm_over_avg_hr() -> None:
    # Run: output = avg speed in m/min = 3.0 m/s * 60 = 180 m/min; avg HR 150
    # -> EF = 180 / 150 = 1.2. The NP argument is irrelevant for a run.
    act = _activity(
        modality=Modality.RUN,
        summary=_summary(avg_heart_rate_bpm=150, avg_speed_mps=3.0),
    )
    assert power.efficiency_factor(act, None) == pytest.approx(1.2)


def test_efficiency_factor_none_for_other_modality() -> None:
    # Strength/other modalities have no defined EF output -> None even with NP
    # and HR present.
    act = _activity(
        modality=Modality.STRENGTH,
        summary=_summary(avg_heart_rate_bpm=150),
    )
    assert power.efficiency_factor(act, 240.0) is None


def test_efficiency_factor_none_without_avg_hr() -> None:
    # Bike with NP but no HR anywhere -> None.
    act = _activity(modality=Modality.BIKE, summary=_summary())
    assert power.efficiency_factor(act, 240.0) is None


def test_efficiency_factor_bike_none_without_np() -> None:
    # Bike with HR but no NP output -> None.
    act = _activity(modality=Modality.BIKE, summary=_summary(avg_heart_rate_bpm=150))
    assert power.efficiency_factor(act, None) is None


def test_efficiency_factor_run_none_without_speed() -> None:
    # Run with HR but no speed channel or session speed -> None.
    act = _activity(modality=Modality.RUN, summary=_summary(avg_heart_rate_bpm=150))
    assert power.efficiency_factor(act, None) is None


# --- 7. aerobic decoupling across halves (Req 8.8) --------------------------


def test_decoupling_bike_positive_when_hr_rises_second_half() -> None:
    # time_s (0,1,2,3), span 3, midpoint 1.5. First half = t <= 1.5 (idx 0,1),
    # second half = t > 1.5 (idx 2,3). Constant 200 W; HR 150 then 160.
    #   EF_first  = mean(200,200) / mean(150,150) = 200/150 = 4/3
    #   EF_second = mean(200,200) / mean(160,160) = 200/160 = 5/4
    #   decoupling = (4/3 - 5/4) / (4/3) * 100 = (1/16) * 100 = 6.25 %
    act = _activity(
        modality=Modality.BIKE,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            power_w=(200, 200, 200, 200),
            heart_rate_bpm=(150, 150, 160, 160),
        ),
    )
    assert power.decoupling_pct(act) == pytest.approx(6.25)


def test_decoupling_run_positive_uses_speed_output() -> None:
    # Run uses speed as the output channel. Constant 3.0 m/s; HR 150 then 160.
    #   EF_first  = 3/150, EF_second = 3/160
    #   decoupling = (3/150 - 3/160) / (3/150) * 100 = 6.25 %
    act = _activity(
        modality=Modality.RUN,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            speed_mps=(3.0, 3.0, 3.0, 3.0),
            heart_rate_bpm=(150, 150, 160, 160),
        ),
    )
    assert power.decoupling_pct(act) == pytest.approx(6.25)


def test_decoupling_flat_series_is_zero() -> None:
    # No drift: constant power AND constant HR -> EF_first == EF_second -> 0.0.
    act = _activity(
        modality=Modality.BIKE,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            power_w=(200, 200, 200, 200),
            heart_rate_bpm=(150, 150, 150, 150),
        ),
    )
    assert power.decoupling_pct(act) == pytest.approx(0.0)


def test_decoupling_negative_when_hr_drops_second_half() -> None:
    # HR falls in the second half -> the output/HR ratio RISES -> negative
    # decoupling (the sign convention: positive = drift).
    act = _activity(
        modality=Modality.BIKE,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            power_w=(200, 200, 200, 200),
            heart_rate_bpm=(160, 160, 150, 150),
        ),
    )
    result = power.decoupling_pct(act)
    assert result is not None
    assert result < 0.0


def test_decoupling_none_when_a_half_lacks_paired_data() -> None:
    # Second half has no HR -> no paired sample there -> None.
    act = _activity(
        modality=Modality.BIKE,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            power_w=(200, 200, 200, 200),
            heart_rate_bpm=(150, 150, None, None),
        ),
    )
    assert power.decoupling_pct(act) is None


def test_decoupling_uses_only_paired_samples_within_a_half() -> None:
    # A half can carry unpaired samples as long as it has >= 1 paired sample;
    # unpaired samples (missing HR or output) are ignored. Six samples,
    # midpoint 2.5: first half idx 0,1,2 -> paired means (power 200 / hr 150);
    # second half idx 3,4,5 with one None-HR sample dropped -> (200 / 160).
    #   EF_first = 200/150, EF_second = 200/160 -> decoupling 6.25 %.
    act = _activity(
        modality=Modality.BIKE,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
            power_w=(200, 200, 200, 200, 200, 200),
            heart_rate_bpm=(150, 150, None, 160, None, 160),
        ),
    )
    assert power.decoupling_pct(act) == pytest.approx(6.25)


def test_decoupling_none_for_other_modality() -> None:
    # Strength/other have no output channel for decoupling -> None even with
    # power and HR present.
    act = _activity(
        modality=Modality.OTHER,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            power_w=(200, 200, 200, 200),
            heart_rate_bpm=(150, 150, 160, 160),
        ),
    )
    assert power.decoupling_pct(act) is None


def test_decoupling_none_for_empty_samples() -> None:
    act = _activity(modality=Modality.BIKE, samples=_samples(()))
    assert power.decoupling_pct(act) is None


def test_decoupling_none_when_first_half_output_is_zero() -> None:
    # First-half output mean 0 (all coasting zeros) -> EF_first 0 -> None rather
    # than a division by zero. Recorded zeros are real data, but a zero EF has
    # no meaningful percentage change.
    act = _activity(
        modality=Modality.BIKE,
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            power_w=(0, 0, 200, 200),
            heart_rate_bpm=(150, 150, 160, 160),
        ),
    )
    assert power.decoupling_pct(act) is None


# --- 8. None propagation, no raises (Req 12.1) ------------------------------


def test_series_metrics_never_raise_on_missing_data() -> None:
    # An empty activity: every series metric returns None and nothing raises.
    act = _activity(modality=Modality.BIKE, samples=_samples(()))
    np_value = power.normalized_power(act.samples)
    assert np_value is None
    assert power.intensity_factor(np_value, None) is None
    assert power.variability_index(np_value, None) is None
    assert power.efficiency_factor(act, np_value) is None
    assert power.decoupling_pct(act) is None


# --- 9. constants read from their records, not bare literals (task 10.2;
#         Req 8.4, 15.1, 15.5, 15.6, 15.8) ------------------------------------


def _numeric_constants_in_source(module: object) -> list[int | float]:
    """Every bare ``int``/``float`` literal an AST walk finds in ``module``'s
    own source text (booleans excluded -- ``bool`` is an ``int`` subclass in
    Python and ``True``/``False`` carry no methodological weight here)."""
    tree = ast.parse(inspect.getsource(module))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ]


def test_module_source_has_no_bare_np_window_exponent_or_span_literal() -> None:
    """The normalized-power rolling-window width (historically the bare
    literal ``30``), the averaging exponent (historically the two independent
    literals ``4`` and ``0.25``), and the minimum span (historically the bare
    literal ``30.0``) must all be read from their records
    (:mod:`fitdocs.metrics.sources`), not re-declared inline.

    Non-vacuous: the module carries plenty of OTHER numeric literals (``0.0``,
    ``1``, ``2.0``, ``60.0``, loop bounds, ...), so this first asserts the walk
    actually visited a non-trivial number of constants, and that it is scanning
    THIS module rather than some other one, before checking that none of the
    four historical values is among them -- a walk that silently found nothing,
    or was pointed at the wrong module, would pass for the wrong reason.
    """
    assert power.__name__ == "fitdocs.metrics.power"  # scanning THIS module
    constants = _numeric_constants_in_source(power)
    assert len(constants) > 5, (
        f"AST walk over {power.__name__} found suspiciously few numeric "
        f"constants ({constants!r}); the scan may not be reaching the module body"
    )
    assert 30 not in constants
    assert 30.0 not in constants
    assert 4 not in constants
    assert 0.25 not in constants


def test_module_source_does_not_name_the_working_reference_document() -> None:
    """Req 15.5: no constant in this module may be cited to
    ``docs/reference/fitdocs-ai-reference.md``, or any other working document
    under ``docs/reference/``, as its source -- not even in a docstring."""
    source = inspect.getsource(power)
    assert "docs/reference" not in source
    assert "fitdocs-ai-reference" not in source


def test_np_rolling_window_is_read_from_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 8.4: the rolling-mean window width is bound from
    :data:`fitdocs.metrics.sources.NP_ROLLING_WINDOW_S` at import time -- not
    a coincidentally-equal literal.

    ``30`` is both the shipped record value and the historical bare literal,
    so an assertion that merely checks the module constant equals ``30``
    would be pre-satisfied by either. This test instead swaps the record for a
    narrower window (``10`` s) on the exact 300 W / 100 W step series used in
    ``test_normalized_power_exact_value_pins_fourth_power_exponent`` and
    confirms NP equals the value hand-derived for exactly this mutation under
    the complete-window (task 13.1) algorithm -- ``250.70040675650532``, from
    a fourth-power mean of a COMPLETE window-10 trailing rolling mean (the
    series starting at index 9, 111 points, not 120) over the same step
    series -- a shorter window shortens the transition ramp and changes the
    fourth-power mean, so a stale or ineffective window swap would compute a
    different, wrong number here.
    """
    original = sources.NP_ROLLING_WINDOW_S
    mutated = dataclasses.replace(original, value=10)
    monkeypatch.setattr(sources, "NP_ROLLING_WINDOW_S", mutated)
    importlib.reload(power)
    try:
        assert power._NP_ROLLING_WINDOW_S == 10
        block_s = 60
        watts: tuple[int | None, ...] = tuple([300] * block_s + [100] * block_s)
        time_s = tuple(float(k) for k in range(len(watts)))
        np_value = power.normalized_power(_samples(time_s, power_w=watts))
        assert np_value is not None
        assert np_value == pytest.approx(250.70040675650532, rel=1e-9)
    finally:
        # Restore before the monkeypatch fixture's own teardown, so every
        # later test sees the module reloaded against the ORIGINAL record --
        # reload mutates the shared module object in place, so a stale
        # reload here would leak into tests that run after this one.
        monkeypatch.setattr(sources, "NP_ROLLING_WINDOW_S", original)
        importlib.reload(power)
    # Assert the restoration itself, inside this same test and after the
    # ``finally`` above has run -- so a deleted or defeated restoration reds
    # right here, regardless of what any neighbouring test does or does not
    # happen to reload afterwards.
    assert original.value == power._NP_ROLLING_WINDOW_S


def test_np_averaging_exponent_is_read_from_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 8.4: the averaging exponent -- both the power and its root -- is
    bound from :data:`fitdocs.metrics.sources.NP_AVERAGING_EXPONENT` at import
    time, and the root tracks the record as that exponent's reciprocal rather
    than a fixed ``0.25``.

    ``4`` is both the shipped record value and (with its root ``0.25``) the
    historical pair of independent literals, so an equality check against the
    shipped value alone cannot tell "read from the record" apart from "still
    hard-coded". This test swaps the record to exponent ``2`` on the exact
    300 W / 100 W step series from
    ``test_normalized_power_exact_value_pins_fourth_power_exponent`` and
    confirms NP equals the *quadratic*-mean value that test's own comment
    hand-derives for exactly this mutation over the complete-window (task
    13.1) ``ra30`` series (``218.64272181950125``) -- which only happens if
    BOTH the power and the root moved to 2 and 0.5 respectively. A collapsed
    constant whose root stayed hard-coded at ``0.25`` would compute a
    different, wrong number here.
    """
    original = sources.NP_AVERAGING_EXPONENT
    mutated = dataclasses.replace(original, value=2)
    monkeypatch.setattr(sources, "NP_AVERAGING_EXPONENT", mutated)
    importlib.reload(power)
    try:
        assert power._NP_AVERAGING_EXPONENT == 2
        block_s = 60
        watts: tuple[int | None, ...] = tuple([300] * block_s + [100] * block_s)
        time_s = tuple(float(k) for k in range(len(watts)))
        np_value = power.normalized_power(_samples(time_s, power_w=watts))
        assert np_value is not None
        assert np_value == pytest.approx(218.64272181950125, rel=1e-9)
    finally:
        monkeypatch.setattr(sources, "NP_AVERAGING_EXPONENT", original)
        importlib.reload(power)
    assert original.value == power._NP_AVERAGING_EXPONENT


def test_np_min_span_is_read_from_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 8.4, 15.8: the minimum power-stream span is bound from
    :data:`fitdocs.metrics.sources.NP_MIN_SPAN_S` at import time -- not a
    coincidentally-equal literal.

    ``30.0`` is both the shipped record value and the historical bare
    literal, so this test swaps the record for a wider minimum (``40.0`` s)
    and confirms a 35 s span -- above the shipped 30 s minimum, so it
    computes NP today -- is refused (``None``) once the record raises the
    floor past it.
    """
    original = sources.NP_MIN_SPAN_S
    mutated = dataclasses.replace(original, value=40.0)
    monkeypatch.setattr(sources, "NP_MIN_SPAN_S", mutated)
    importlib.reload(power)
    try:
        assert power._NP_MIN_SPAN_S == 40.0
        n = 36  # 1 Hz samples spanning 35 s
        time_s = tuple(float(k) for k in range(n))
        watts: tuple[int | None, ...] = (200,) * n
        assert power.normalized_power(_samples(time_s, power_w=watts)) is None
    finally:
        monkeypatch.setattr(sources, "NP_MIN_SPAN_S", original)
        importlib.reload(power)
    assert original.value == power._NP_MIN_SPAN_S


def test_normalized_power_min_span_boundary_is_strict() -> None:
    """Req 8.4: the minimum-span comparison is strict (``<``), not inclusive
    (``<=``) -- a span exactly at
    :data:`fitdocs.metrics.sources.NP_MIN_SPAN_S` computes normalized power,
    and a span a hair under it refuses. Read live from the record rather than
    a hand-typed ``30.0`` so a future change to the record does not silently
    stop this test from meaning what it says."""
    min_span = sources.NP_MIN_SPAN_S.value
    at_minimum = power.normalized_power(_samples((0.0, min_span), power_w=(200, 200)))
    assert at_minimum is not None

    just_under = power.normalized_power(
        _samples((0.0, min_span - 1e-6), power_w=(200, 200))
    )
    assert just_under is None


def test_normalized_power_empty_ra30_guard_is_a_reachable_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 13.1: dropping the low partial-window averages makes
    ``_trailing_rolling_mean`` return an EMPTY list whenever the resampled
    series is shorter than the window -- previously impossible, since the
    old partial-window formula always produced one output point per input
    point (never empty for a non-empty input). ``normalized_power``'s
    ``if not ra30: return None`` guard existed before this task purely as
    documentation; after this task it is a real, reachable code path.

    It is UNREACHABLE today through the public two live records alone
    (:data:`fitdocs.metrics.sources.NP_MIN_SPAN_S` == 30.0 ==
    :data:`fitdocs.metrics.sources.NP_ROLLING_WINDOW_S`, so any span that
    clears the span gate always yields a resample at least as long as the
    window) -- which is exactly why the task calls it a "backstop" rather
    than dead code: the two constants are independent records, and this
    test proves the backstop fires correctly (returns ``None``, does not
    raise ZeroDivisionError or IndexError) the moment a future edit narrows
    :data:`NP_MIN_SPAN_S` below :data:`NP_ROLLING_WINDOW_S`, without waiting
    for that edit to actually happen.
    """
    original = sources.NP_MIN_SPAN_S
    # Narrow the min-span floor to 5 s -- far below the shipped 30 s rolling
    # window -- so a 10 s span clears the (mutated) span gate but is still
    # shorter than the (unmutated) rolling window.
    mutated = dataclasses.replace(original, value=5.0)
    monkeypatch.setattr(sources, "NP_MIN_SPAN_S", mutated)
    importlib.reload(power)
    try:
        assert power._NP_MIN_SPAN_S == 5.0
        assert power._NP_ROLLING_WINDOW_S > 10  # window still wider than this span
        n = 11  # 1 Hz samples spanning 10 s -- clears the mutated 5 s floor
        time_s = tuple(float(k) for k in range(n))
        watts: tuple[int | None, ...] = (200,) * n
        # Direct proof the helper itself returns [] here, before checking the
        # public function's guard consumes that emptiness correctly:
        resampled = power._resample_power_1hz(time_s, watts)
        assert power._trailing_rolling_mean(resampled, power._NP_ROLLING_WINDOW_S) == []
        assert power.normalized_power(_samples(time_s, power_w=watts)) is None
    finally:
        monkeypatch.setattr(sources, "NP_MIN_SPAN_S", original)
        importlib.reload(power)
    assert original.value == power._NP_MIN_SPAN_S
