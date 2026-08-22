"""Hand-computed tests for the session-preferred aggregate metrics.

These exercise :mod:`fitdocs.metrics.aggregates`: motion, heart-rate, power, and
cadence scalars that prefer a recorded session value and fall back to a
channel-derived value, returning ``None`` when neither is available. Every
expected number below is hand-computed so the formulas are pinned, not merely
snapshotted.

The invariants under test:

* **Session wins** -- a recorded summary value is returned even when the channel
  would compute something different (Req 7-8).
* **Channel fallback** -- with the summary field ``None`` the value is derived
  from the raw channel, excluding ``None`` samples (Req 7.4, 8.1-8.3).
* **True zeros preserved** -- a recorded ``0`` is real data, counted in
  averages, never dropped as if missing (Req 12.3).
* **None propagation** -- an absent channel yields ``None`` while independent
  metrics still compute; nothing raises for missing data (Req 12.1, 12.2).
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect

import pytest

from fitdocs import metrics
from fitdocs.metrics import aggregates, sources
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
    total_elapsed_time_s: float | None = None,
    total_timer_time_s: float | None = None,
    total_distance_m: float | None = None,
    total_calories_kcal: int | None = None,
    total_ascent_m: float | None = None,
    total_descent_m: float | None = None,
    avg_heart_rate_bpm: int | None = None,
    max_heart_rate_bpm: int | None = None,
    avg_power_w: int | None = None,
    max_power_w: int | None = None,
    avg_cadence_rpm: float | None = None,
    max_cadence_rpm: float | None = None,
    avg_speed_mps: float | None = None,
    max_speed_mps: float | None = None,
) -> SessionSummary:
    """A ``SessionSummary`` with every field ``None`` except those overridden.

    Exposes as keyword arguments the fields tasks 5.2 (motion/HR/power/cadence)
    and 5.3 (calories, ascent/descent) read; the rest (sport, ...) stay ``None``
    -- irrelevant here and owned by other tasks.
    """
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=total_elapsed_time_s,
        total_timer_time_s=total_timer_time_s,
        total_distance_m=total_distance_m,
        total_calories_kcal=total_calories_kcal,
        total_ascent_m=total_ascent_m,
        total_descent_m=total_descent_m,
        avg_heart_rate_bpm=avg_heart_rate_bpm,
        max_heart_rate_bpm=max_heart_rate_bpm,
        avg_power_w=avg_power_w,
        max_power_w=max_power_w,
        avg_cadence_rpm=avg_cadence_rpm,
        max_cadence_rpm=max_cadence_rpm,
        avg_speed_mps=avg_speed_mps,
        max_speed_mps=max_speed_mps,
    )


def _samples(
    time_s: tuple[float, ...] = (),
    *,
    heart_rate_bpm: tuple[int | None, ...] | None = None,
    power_w: tuple[int | None, ...] | None = None,
    cadence_rpm: tuple[float | None, ...] | None = None,
    speed_mps: tuple[float | None, ...] | None = None,
    distance_m: tuple[float | None, ...] | None = None,
    altitude_m: tuple[float | None, ...] | None = None,
    temperature_c: tuple[float | None, ...] | None = None,
) -> Samples:
    """A ``Samples`` whose channels default to all-``None`` arrays of length
    ``len(time_s)``; pass a channel explicitly to populate it. Position channels
    are irrelevant to these aggregates and left all-``None``."""
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm if heart_rate_bpm is not None else none_ints,
        power_w=power_w if power_w is not None else none_ints,
        cadence_rpm=cadence_rpm if cadence_rpm is not None else none_floats,
        speed_mps=speed_mps if speed_mps is not None else none_floats,
        distance_m=distance_m if distance_m is not None else none_floats,
        altitude_m=altitude_m if altitude_m is not None else none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=temperature_c if temperature_c is not None else none_floats,
    )


def _activity(
    *,
    summary: SessionSummary | None = None,
    samples: Samples | None = None,
) -> Activity:
    """An otherwise-trivial ``Activity`` wrapping the given summary and samples."""
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="", source_path=None, decode_errors=()),
        sport=Sport.RUN,
        modality=Modality.RUN,
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
    # aggregates lives under the metrics package (design File Structure Plan).
    assert aggregates is metrics.aggregates


# --- 1. session-recorded value wins over the channel ------------------------


def test_avg_power_prefers_session_over_channel() -> None:
    # Channel would average 100 W, but the session recorded 200 W -> 200 wins.
    act = _activity(
        summary=_summary(avg_power_w=200),
        samples=_samples((0.0, 1.0, 2.0), power_w=(100, 100, 100)),
    )
    assert aggregates.avg_power_w(act) == 200


def test_max_heart_rate_prefers_session_over_channel() -> None:
    act = _activity(
        summary=_summary(max_heart_rate_bpm=180),
        samples=_samples((0.0, 1.0), heart_rate_bpm=(120, 130)),
    )
    assert aggregates.max_heart_rate_bpm(act) == 180


def test_avg_speed_prefers_session_over_channel() -> None:
    act = _activity(
        summary=_summary(avg_speed_mps=3.0),
        samples=_samples((0.0, 1.0), speed_mps=(9.0, 9.0)),
    )
    assert aggregates.avg_speed_mps(act) == 3.0


def test_distance_prefers_session_total_over_channel() -> None:
    act = _activity(
        summary=_summary(total_distance_m=5000.0),
        samples=_samples((0.0, 1.0), distance_m=(0.0, 123.0)),
    )
    assert aggregates.distance_m(act) == 5000.0


def test_elapsed_prefers_session_total_over_channel() -> None:
    act = _activity(
        summary=_summary(total_elapsed_time_s=3600.0),
        samples=_samples((0.0, 10.0, 20.0)),
    )
    assert aggregates.elapsed_time_s(act) == 3600.0


# --- 2. channel fallback, None excluded -------------------------------------


def test_avg_hr_channel_fallback_excludes_none() -> None:
    # (120, None, 130): the None sample is excluded -> mean(120, 130) == 125.0.
    act = _activity(samples=_samples((0.0, 1.0, 2.0), heart_rate_bpm=(120, None, 130)))
    assert aggregates.avg_heart_rate_bpm(act) == 125.0


def test_max_hr_channel_fallback_excludes_none() -> None:
    act = _activity(samples=_samples((0.0, 1.0, 2.0), heart_rate_bpm=(120, None, 130)))
    assert aggregates.max_heart_rate_bpm(act) == 130


def test_avg_and_max_power_channel_fallback() -> None:
    act = _activity(samples=_samples((0.0, 1.0, 2.0), power_w=(100, 200, 300)))
    assert aggregates.avg_power_w(act) == 200.0
    assert aggregates.max_power_w(act) == 300


def test_avg_and_max_speed_channel_fallback() -> None:
    act = _activity(samples=_samples((0.0, 1.0, 2.0), speed_mps=(2.0, 4.0, 6.0)))
    assert aggregates.avg_speed_mps(act) == 4.0
    assert aggregates.max_speed_mps(act) == 6.0


def test_avg_and_max_cadence_channel_fallback_excludes_none() -> None:
    act = _activity(
        samples=_samples((0.0, 1.0, 2.0), cadence_rpm=(80.0, None, 90.0)),
    )
    assert aggregates.avg_cadence_rpm(act) == 85.0
    assert aggregates.max_cadence_rpm(act) == 90.0


# --- 3. moving time heuristic (Req 7.1) -------------------------------------


def test_moving_time_prefers_session_timer() -> None:
    # Timer recorded -> returned directly, ignoring the (stopped) channel.
    act = _activity(
        summary=_summary(total_timer_time_s=999.0),
        samples=_samples((0.0, 1.0, 2.0), speed_mps=(0.0, 0.0, 0.0)),
    )
    assert aggregates.moving_time_s(act) == 999.0


def test_moving_time_speed_threshold_counts_only_moving_pairs() -> None:
    # dt is 1 s per pair. Earlier-sample speed decides each pair:
    #   i=0 speed 1.0 > 0.5  -> moving (+1)
    #   i=1 speed 0.0        -> stopped
    #   i=2 speed 2.0 > 0.5  -> moving (+1)
    #   i=3 speed 0.3        -> stopped (<= 0.5 threshold)
    # -> 2.0 s of moving time.
    act = _activity(
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0, 4.0),
            speed_mps=(1.0, 0.0, 2.0, 0.3, 5.0),
        )
    )
    assert aggregates.moving_time_s(act) == 2.0


def test_moving_time_distance_increase_counts_without_speed_channel() -> None:
    # No speed channel; movement inferred purely from distance increases.
    #   i=0 dist 0->5  increases -> moving (+1)
    #   i=1 dist 5->5  flat      -> stopped
    #   i=2 dist 5->12 increases -> moving (+1)
    # -> 2.0 s.
    act = _activity(
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            distance_m=(0.0, 5.0, 5.0, 12.0),
        )
    )
    assert aggregates.moving_time_s(act) == 2.0


def test_moving_time_none_without_usable_channel() -> None:
    # Timestamps but no speed and no distance channel -> nothing to decide with.
    act = _activity(samples=_samples((0.0, 1.0, 2.0)))
    assert aggregates.moving_time_s(act) is None


def test_moving_time_recorded_zero_timer_is_real() -> None:
    # A recorded 0.0 timer is a true value (Req 12.3), not a fallback trigger.
    act = _activity(
        summary=_summary(total_timer_time_s=0.0),
        samples=_samples((0.0, 1.0), speed_mps=(5.0, 5.0)),
    )
    assert aggregates.moving_time_s(act) == 0.0


# --- 4. elapsed and distance channel fallbacks ------------------------------


def test_elapsed_channel_fallback_last_minus_first() -> None:
    act = _activity(samples=_samples((10.0, 20.0, 45.0)))
    assert aggregates.elapsed_time_s(act) == 35.0


def test_elapsed_single_sample_is_zero() -> None:
    act = _activity(samples=_samples((7.0,)))
    assert aggregates.elapsed_time_s(act) == 0.0


def test_distance_channel_fallback_uses_last_non_none() -> None:
    # Last non-None cumulative value is 100.0 (the trailing None is skipped).
    act = _activity(
        samples=_samples((0.0, 1.0, 2.0, 3.0), distance_m=(0.0, 50.0, 100.0, None))
    )
    assert aggregates.distance_m(act) == 100.0


# --- 5. average pace (Req 7.5) ----------------------------------------------


def test_avg_pace_composed_from_distance_and_moving_time() -> None:
    # 5000 m over 1500 s of moving time -> 1500 / (5000/1000) == 300 s/km.
    act = _activity(
        summary=_summary(total_distance_m=5000.0, total_timer_time_s=1500.0),
    )
    assert aggregates.avg_pace_s_per_km(act) == 300.0


def test_avg_pace_none_when_distance_zero() -> None:
    # Distance 0 (a recorded zero) cannot yield a pace -> None, no ZeroDivision.
    act = _activity(
        summary=_summary(total_distance_m=0.0, total_timer_time_s=1500.0),
    )
    assert aggregates.avg_pace_s_per_km(act) is None


def test_avg_pace_none_when_inputs_missing() -> None:
    act = _activity()
    assert aggregates.avg_pace_s_per_km(act) is None


# --- 6. true zeros preserved (Req 12.3) -------------------------------------


def test_avg_power_counts_recorded_zeros() -> None:
    # (0, 200, 0, 200): coasting zeros ARE counted -> mean == 100.0, not 200.0.
    act = _activity(samples=_samples((0.0, 1.0, 2.0, 3.0), power_w=(0, 200, 0, 200)))
    assert aggregates.avg_power_w(act) == 100.0
    assert aggregates.max_power_w(act) == 200


# --- 7. None propagation, independence, and no raises (Req 12.1, 12.2) ------


def test_absent_power_channel_is_none_while_hr_still_computes() -> None:
    # No power channel and no session power -> power metrics None; HR present
    # and independent -> still computed.
    act = _activity(samples=_samples((0.0, 1.0, 2.0), heart_rate_bpm=(100, 110, 120)))
    assert aggregates.avg_power_w(act) is None
    assert aggregates.max_power_w(act) is None
    assert aggregates.avg_heart_rate_bpm(act) == 110.0
    assert aggregates.max_heart_rate_bpm(act) == 120


def test_empty_activity_all_metrics_none_no_error() -> None:
    # Empty samples + empty summary: every metric is None and nothing raises.
    act = _activity()
    assert aggregates.moving_time_s(act) is None
    assert aggregates.elapsed_time_s(act) is None
    assert aggregates.distance_m(act) is None
    assert aggregates.avg_speed_mps(act) is None
    assert aggregates.max_speed_mps(act) is None
    assert aggregates.avg_pace_s_per_km(act) is None
    assert aggregates.avg_heart_rate_bpm(act) is None
    assert aggregates.max_heart_rate_bpm(act) is None
    assert aggregates.avg_power_w(act) is None
    assert aggregates.max_power_w(act) is None
    assert aggregates.avg_cadence_rpm(act) is None
    assert aggregates.max_cadence_rpm(act) is None


# --- 8. elevation: session totals win (Req 9.1, 9.2) -------------------------


def test_elevation_prefers_session_ascent_descent_over_altitude() -> None:
    # Session recorded ascent/descent -> returned directly, ignoring the
    # (differently-shaped) altitude channel entirely.
    act = _activity(
        summary=_summary(total_ascent_m=250.0, total_descent_m=180.0),
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            altitude_m=(100.0, 101.0, 100.0, 101.0),
        ),
    )
    assert aggregates.elevation_gain_m(act) == 250.0
    assert aggregates.elevation_loss_m(act) == 180.0


# --- 9. elevation smoothing fallback (Req 9.1, 9.2) -------------------------
#
# Algorithm under test (pinned in the aggregates docstring): a *trailing*
# None-skipping boxcar of width 10. For each index i the smoothed point is the
# mean of the non-None altitude samples in altitude[max(0, i-9) .. i] (the <=10
# samples ending at i). Gain = sum of positive deltas, loss = sum of magnitudes
# of negative deltas, taken over consecutive defined smoothed points. Every
# expected number below is hand-computed against exactly that window.


def test_elevation_smoothing_damps_jitter_below_raw_deltas() -> None:
    # altitude = (100, 101, 100, 101), no session ascent/descent. n=4 < window
    # 10, so each smoothed point is the cumulative mean of altitude[0..i]:
    #   s0 = 100
    #   s1 = (100+101)/2      = 100.5
    #   s2 = (100+101+100)/3  = 100.333... (301/3)
    #   s3 = (100+101+100+101)/4 = 100.5   (402/4)
    # deltas: +0.5, -1/6, +1/6  ->  gain = 0.5 + 1/6 = 2/3 ; loss = 1/6.
    # Raw (unsmoothed) deltas would be +1,-1,+1 -> gain 2.0, loss 1.0; the
    # smoothed numbers are far smaller, proving smoothing is applied.
    act = _activity(
        samples=_samples((0.0, 1.0, 2.0, 3.0), altitude_m=(100.0, 101.0, 100.0, 101.0)),
    )
    assert aggregates.elevation_gain_m(act) == pytest.approx(2.0 / 3.0)
    assert aggregates.elevation_loss_m(act) == pytest.approx(1.0 / 6.0)
    # Damping guard: smoothed gain/loss stay well under the raw-delta sums.
    assert aggregates.elevation_gain_m(act) < 1.0  # not the raw 2.0
    assert aggregates.elevation_loss_m(act) < 0.5  # not the raw 1.0


def test_elevation_smoothing_window_slides_at_width_ten() -> None:
    # A monotonic ramp of 12 samples (0,1,...,11) exercises the width-10 slide:
    #   i<=9:  s[i] = mean(0..i)         -> 0, .5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5
    #   i=10:  mean(1..10)  = 55/10      -> 5.5   (index 0 slides out of window)
    #   i=11:  mean(2..11)  = 65/10      -> 6.5   (index 1 slides out)
    # The smoothed series is monotonically increasing, so loss == 0 and gain
    # telescopes to s[11]-s[0] = 6.5 - 0 = 6.5.
    altitude: tuple[float | None, ...] = tuple(float(k) for k in range(12))
    time_s: tuple[float, ...] = tuple(float(k) for k in range(12))
    act = _activity(samples=_samples(time_s, altitude_m=altitude))
    assert aggregates.elevation_gain_m(act) == pytest.approx(6.5)
    assert aggregates.elevation_loss_m(act) == 0.0


def test_elevation_steady_climb_approximates_true_climb() -> None:
    # A steady 100 -> 110 climb over 101 samples (step 0.1). Monotonic, so
    # loss == 0. The trailing boxcar lags at the end by the window mean:
    #   s[0]   = 100 (window just [0])
    #   s[100] = mean(a[91..100]) = 100 + 0.1*95.5 = 109.55
    # gain telescopes to 109.55 - 100 = 9.55 -- within the boxcar's edge lag of
    # the true climb of 10.0 (this is the whole point: gain ~= true climb).
    altitude: tuple[float | None, ...] = tuple(100.0 + 0.1 * k for k in range(101))
    time_s: tuple[float, ...] = tuple(float(k) for k in range(101))
    act = _activity(samples=_samples(time_s, altitude_m=altitude))
    assert aggregates.elevation_loss_m(act) == 0.0
    assert aggregates.elevation_gain_m(act) == pytest.approx(9.55)
    assert 9.0 < aggregates.elevation_gain_m(act) < 10.0  # ~= true climb of 10


# --- 10. min/max altitude and temperature min/max/avg (Req 9.3, 9.4) --------


def test_min_max_altitude_from_channel_excludes_none() -> None:
    act = _activity(
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            altitude_m=(100.0, None, 105.0, 98.0),
        )
    )
    assert aggregates.min_altitude_m(act) == 98.0
    assert aggregates.max_altitude_m(act) == 105.0


def test_temperature_min_max_avg_from_channel_excludes_none() -> None:
    # (20, None, 22, 24): None excluded -> min 20, max 24, mean (20+22+24)/3 = 22.
    act = _activity(
        samples=_samples(
            (0.0, 1.0, 2.0, 3.0),
            temperature_c=(20.0, None, 22.0, 24.0),
        )
    )
    assert aggregates.min_temperature_c(act) == 20.0
    assert aggregates.max_temperature_c(act) == 24.0
    assert aggregates.avg_temperature_c(act) == 22.0


def test_recorded_zero_altitude_and_temperature_are_real() -> None:
    # A recorded 0 is data, not missing (Req 12.3): 0.0 is the true minimum and
    # is counted in the temperature mean.
    act = _activity(
        samples=_samples(
            (0.0, 1.0),
            altitude_m=(0.0, 5.0),
            temperature_c=(0.0, 10.0),
        )
    )
    assert aggregates.min_altitude_m(act) == 0.0
    assert aggregates.max_altitude_m(act) == 5.0
    assert aggregates.min_temperature_c(act) == 0.0
    assert aggregates.avg_temperature_c(act) == 5.0


# --- 11. calories passthrough, never estimated (Req 11.3) -------------------


def test_calories_passthrough_returns_recorded_int() -> None:
    act = _activity(summary=_summary(total_calories_kcal=450))
    result = aggregates.calories_kcal(act)
    assert result == 450
    assert isinstance(result, int)


def test_calories_none_when_session_did_not_record() -> None:
    # No session calories and no channel from which they could ever be derived
    # -> None. There is no estimation path.
    act = _activity(
        summary=_summary(total_calories_kcal=None),
        samples=_samples(
            (0.0, 1.0, 2.0),
            heart_rate_bpm=(120, 130, 140),
            power_w=(100, 200, 300),
        ),
    )
    assert aggregates.calories_kcal(act) is None


# --- 12. absent channels -> None, independent metrics still compute ---------
#         (Req 9.5, 12.1, 12.2)


def test_absent_altitude_none_while_temperature_still_computes() -> None:
    # No altitude channel and no session ascent/descent -> every elevation
    # metric None; temperature is independent and still computes.
    act = _activity(
        samples=_samples((0.0, 1.0, 2.0), temperature_c=(15.0, 16.0, 17.0)),
    )
    assert aggregates.elevation_gain_m(act) is None
    assert aggregates.elevation_loss_m(act) is None
    assert aggregates.min_altitude_m(act) is None
    assert aggregates.max_altitude_m(act) is None
    assert aggregates.min_temperature_c(act) == 15.0
    assert aggregates.max_temperature_c(act) == 17.0
    assert aggregates.avg_temperature_c(act) == 16.0


def test_absent_temperature_none_while_altitude_still_computes() -> None:
    act = _activity(
        samples=_samples((0.0, 1.0, 2.0), altitude_m=(200.0, 210.0, 205.0)),
    )
    assert aggregates.min_temperature_c(act) is None
    assert aggregates.max_temperature_c(act) is None
    assert aggregates.avg_temperature_c(act) is None
    assert aggregates.min_altitude_m(act) == 200.0
    assert aggregates.max_altitude_m(act) == 210.0


def test_empty_activity_elevation_temperature_calories_none_no_error() -> None:
    # Empty samples + empty summary: every 5.3 metric is None and nothing raises
    # (Req 9.5, 12.1).
    act = _activity()
    assert aggregates.elevation_gain_m(act) is None
    assert aggregates.elevation_loss_m(act) is None
    assert aggregates.min_altitude_m(act) is None
    assert aggregates.max_altitude_m(act) is None
    assert aggregates.min_temperature_c(act) is None
    assert aggregates.max_temperature_c(act) is None
    assert aggregates.avg_temperature_c(act) is None
    assert aggregates.calories_kcal(act) is None


# --- 13. constants read from their records, not bare literals (task 10.1;
#         Req 7.1, 9.1, 9.2, 15.1, 15.5, 15.6, 15.8) --------------------------


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


def test_module_source_has_no_bare_threshold_or_window_literal() -> None:
    """The moving-time movement threshold (historically the bare literal
    ``0.5``) and the altitude-smoothing window (historically the bare literal
    ``10``) must both be read from their records
    (:mod:`fitdocs.metrics.sources`), not re-declared inline.

    Non-vacuous: the module carries plenty of OTHER numeric literals (``0.0``,
    ``1``, ``1000.0``, loop bounds, ...), so this first asserts the walk
    actually visited a non-trivial number of constants before checking that
    neither the threshold's nor the window's value is among them -- a walk
    that silently found nothing would pass for the wrong reason.
    """
    constants = _numeric_constants_in_source(aggregates)
    assert len(constants) > 5, (
        f"AST walk over {aggregates.__name__} found suspiciously few numeric "
        f"constants ({constants!r}); the scan may not be reaching the module body"
    )
    assert 0.5 not in constants
    assert 10 not in constants


def test_module_source_does_not_name_the_working_reference_document() -> None:
    """Req 15.5: no constant in this module may be cited to
    ``docs/reference/fitdocs-ai-reference.md``, or any other working document
    under ``docs/reference/``, as its source -- not even in a docstring."""
    source = inspect.getsource(aggregates)
    assert "docs/reference" not in source
    assert "fitdocs-ai-reference" not in source


def test_moving_time_threshold_is_read_from_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 7.1: the moving-time movement threshold is bound from
    :data:`fitdocs.metrics.sources.MOVING_SPEED_THRESHOLD_MPS` at import time
    -- not a coincidentally-equal literal.

    ``0.5`` is both the shipped record value and the historical bare literal,
    so an assertion that merely checks the module constant equals ``0.5``
    would be pre-satisfied by either -- it cannot tell "read from the record"
    apart from "still a hard-coded literal that happens to match". This test
    instead swaps the record for one with a materially different threshold
    (``2.5`` m/s), reloads the module so the swap takes effect, and confirms a
    steady 1.0 m/s sample -- "moving" at the shipped 0.5 m/s threshold -- is
    "stopped" once the record's own value rises past it.
    """
    original = sources.MOVING_SPEED_THRESHOLD_MPS
    mutated = dataclasses.replace(original, value=2.5)
    monkeypatch.setattr(sources, "MOVING_SPEED_THRESHOLD_MPS", mutated)
    importlib.reload(aggregates)
    try:
        assert aggregates._MOVING_SPEED_THRESHOLD_MPS == 2.5
        act = _activity(
            samples=_samples((0.0, 1.0, 2.0), speed_mps=(1.0, 1.0, 1.0)),
        )
        assert aggregates.moving_time_s(act) == 0.0
    finally:
        # Restore before the monkeypatch fixture's own teardown, so every
        # later test sees the module reloaded against the ORIGINAL record --
        # reload mutates the shared module object in place, so a stale
        # reload here would leak into tests that run after this one.
        monkeypatch.setattr(sources, "MOVING_SPEED_THRESHOLD_MPS", original)
        importlib.reload(aggregates)
    # Assert the restoration itself, inside this same test and after the
    # ``finally`` above has run -- so a deleted or defeated restoration reds
    # right here, regardless of what any neighbouring test does or does not
    # happen to reload afterwards.
    assert original.value == aggregates._MOVING_SPEED_THRESHOLD_MPS


def test_moving_time_threshold_boundary_is_strict() -> None:
    """Req 7.1: a speed sample exactly *at* the threshold does not count as
    moving on its own -- the comparison is strict (``>``), not inclusive
    (``>=``). A flat (non-increasing) distance channel is paired with the
    exactly-at-threshold sample so the distance fallback cannot also mark it
    moving; a sample just above the threshold must still be counted."""
    threshold = sources.MOVING_SPEED_THRESHOLD_MPS.value
    at_threshold = _activity(
        samples=_samples(
            (0.0, 1.0, 2.0),
            speed_mps=(threshold, threshold, threshold),
            distance_m=(0.0, 0.0, 0.0),
        ),
    )
    assert aggregates.moving_time_s(at_threshold) == 0.0

    just_above = threshold + 0.000001
    above_threshold = _activity(
        samples=_samples(
            (0.0, 1.0, 2.0),
            speed_mps=(just_above, just_above, just_above),
            distance_m=(0.0, 0.0, 0.0),
        ),
    )
    assert aggregates.moving_time_s(above_threshold) == 2.0


def test_altitude_smoothing_window_is_read_from_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 9.1, 9.2: the altitude-smoothing boxcar width is bound from
    :data:`fitdocs.metrics.sources.ALTITUDE_SMOOTHING_WINDOW` at import time
    -- not a coincidentally-equal literal.

    ``10`` is both the shipped record value and the historical bare literal,
    so this test swaps the record for a narrower window (``2`` samples),
    reloads the module, and confirms elevation gain/loss follow the record
    rather than staying pinned at width 10.
    """
    original = sources.ALTITUDE_SMOOTHING_WINDOW
    mutated = dataclasses.replace(original, value=2)
    monkeypatch.setattr(sources, "ALTITUDE_SMOOTHING_WINDOW", mutated)
    importlib.reload(aggregates)
    try:
        assert aggregates._ALTITUDE_SMOOTHING_WINDOW == 2
        # altitude = (100, 101, 100, 101), no session ascent/descent. Under a
        # width-2 boxcar: s = (100, 100.5, 100.5, 100.5) -> gain 0.5, loss 0.
        # The shipped width-10 boxcar on this exact series gives gain 2/3 and
        # loss 1/6 (see test_elevation_smoothing_damps_jitter_below_raw_deltas
        # above) -- a different pair of numbers, not a coincidence.
        act = _activity(
            samples=_samples(
                (0.0, 1.0, 2.0, 3.0), altitude_m=(100.0, 101.0, 100.0, 101.0)
            ),
        )
        assert aggregates.elevation_gain_m(act) == pytest.approx(0.5)
        assert aggregates.elevation_loss_m(act) == 0.0
    finally:
        monkeypatch.setattr(sources, "ALTITUDE_SMOOTHING_WINDOW", original)
        importlib.reload(aggregates)
