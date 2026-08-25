"""End-to-end verification: every channel reproduced against a published
worked example (task 5.1).

Covers Requirements 1.6, 4.8, 5.10, 8.4 -- see
``.kiro/specs/load-channels/requirements.md`` and design.md's "Testing
Strategy" -> "E2E / Verification Tests" section (``test_worked_examples.py``
E2E line and the "Coefficient invariance" line).

**Read-only over the channel modules** (task boundary): this module imports
``power``, ``heart_rate`` and ``pace`` and calls their public ``compute``
functions only. No source module under ``src/fitdocs/load/channels/`` is
edited by this task -- the mutation-based discrimination evidence for this
module's assertions was gathered by editing a channel module's source line,
observing the suite, and reverting it, entirely outside this file's own
content; that process and its results are recorded in the task's Status
Report, not here.

**THE TRAP THIS MODULE IS WRITTEN TO AVOID (Req 8.4).** Banister (1991)
prints three worked training-impulse examples in its Fig. 9.5 / 9.6
captions (pp. 409-410) and NONE of the three satisfies the equation printed
one page earlier (p. 408) -- see
``docs/reference/banister-trimp-primary-sources.md`` D4, and queue item
``2026-07-27-banister-figure-captions-unusable-as-vectors``. Every expected
value in this module is therefore computed from the published *formula*
itself, inline in this file, independently of any production module -- never
transcribed from a caption or from a rounded approximation printed in
design.md. Each computation names its formula's source. (The one deliberate
exception is ``published_tss`` in ``test_power_worked_example_tss``, named
apart from the ``expected_*`` convention precisely because it *is* the
rounded design.md figure -- it anchors the formula's unrounded result to
design.md's citation and is never compared against production output.)
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate, pace, power
from fitdocs.load.channels.sources import (
    BANISTER_TRIMP,
    COGGAN_TSS,
    INTERVALS_ICU_PACE_LOAD,
)
from fitdocs.load.channels.types import ChannelLoad, SufficiencySettings
from fitdocs.metrics import sources as metrics_sources
from fitdocs.metrics.stress import trimp
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# fixture builders -- self-contained in this module (read-only over the
# channel modules; not imported from any single-channel test module)
# ---------------------------------------------------------------------------

_SETTINGS = SufficiencySettings()


def _summary() -> SessionSummary:
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
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def _activity(*, modality: Modality, sport: Sport, samples: Samples) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


def _power_activity(n_seconds: int, watts: int = 200) -> Activity:
    """``n_seconds + 1`` one-second power samples, fully covered -- the
    power channel reads normalized power and moving time from ``metrics``
    directly (composition, not restatement, task 3.1), so the stream's
    actual wattage need only pass the sufficiency gate."""
    time_s = tuple(float(i) for i in range(n_seconds + 1))
    power_w = (watts,) * (n_seconds + 1)
    none_ints: tuple[int | None, ...] = (None,) * (n_seconds + 1)
    none_floats: tuple[float | None, ...] = (None,) * (n_seconds + 1)
    return _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=Samples(
            time_s=time_s,
            heart_rate_bpm=none_ints,
            power_w=power_w,
            cadence_rpm=none_floats,
            speed_mps=none_floats,
            distance_m=none_floats,
            altitude_m=none_floats,
            latitude_deg=none_floats,
            longitude_deg=none_floats,
            temperature_c=none_floats,
        ),
    )


def _ftp(value: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=value,
        measured_on=date(2026, 1, 1),
    )


def _hr_samples(n_seconds: int, heart_rate_bpm: int) -> Samples:
    time_s = tuple(float(i) for i in range(n_seconds + 1))
    none_ints: tuple[int | None, ...] = (None,) * (n_seconds + 1)
    none_floats: tuple[float | None, ...] = (None,) * (n_seconds + 1)
    return Samples(
        time_s=time_s,
        heart_rate_bpm=(heart_rate_bpm,) * (n_seconds + 1),
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _hr_activity(n_seconds: int, heart_rate_bpm: int) -> Activity:
    return _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=_hr_samples(n_seconds, heart_rate_bpm),
    )


def _lthr(value: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=value,
        measured_on=date(2026, 1, 1),
    )


def _resting_hr(value: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=value,
        measured_on=date(2026, 1, 1),
    )


def _max_hr(value: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=value,
        measured_on=date(2026, 1, 1),
    )


def _pace_activity(n_seconds: int, speed_mps: float) -> Activity:
    """``n_seconds + 1`` one-second distance samples advancing at
    ``speed_mps``, no altitude stream at all -- the altitude gate reports
    STREAM_ABSENT, so grade adjustment is never applied and the reported
    speed is exactly ``speed_mps``."""
    time_s = tuple(float(i) for i in range(n_seconds + 1))
    distance_m = tuple(speed_mps * i for i in range(n_seconds + 1))
    none_ints: tuple[int | None, ...] = (None,) * (n_seconds + 1)
    none_floats: tuple[float | None, ...] = (None,) * (n_seconds + 1)
    return _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=Samples(
            time_s=time_s,
            heart_rate_bpm=none_ints,
            power_w=none_ints,
            cadence_rpm=none_floats,
            speed_mps=none_floats,
            distance_m=distance_m,
            altitude_m=none_floats,
            latitude_deg=none_floats,
            longitude_deg=none_floats,
            temperature_c=none_floats,
        ),
    )


def _threshold_pace(s_per_km: float) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=s_per_km,
        measured_on=date(2026, 1, 1),
    )


# ---------------------------------------------------------------------------
# Power channel -- Coggan (2003), :data:`COGGAN_TSS` (Req 4.8, 8.4)
# ---------------------------------------------------------------------------


def test_power_worked_example_intensity_factor() -> None:
    """Coggan (2003): IF = NP / FTP. NP 210 W over FTP 280 W -> IF 0.75
    (``COGGAN_TSS``, §3 "Intensity factor (IF) and training stress score
    (TSS)")."""
    assert COGGAN_TSS.key == "coggan_tss"
    expected_if = 210.0 / 280.0
    assert expected_if == pytest.approx(0.75)

    metrics = DerivedMetrics(normalized_power_w=210.0, moving_time_s=3600.0)
    result = power.compute(
        _power_activity(3600), metrics, ftp=_ftp(280.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(expected_if)


@pytest.mark.parametrize(
    ("duration_s", "np_w", "ftp_w", "published_tss"),
    [
        (7080.0, 183.0, 215.0, 142.0),
        (5400.0, 220.0, 250.0, 116.0),
    ],
    ids=["7080s-np183-ftp215", "5400s-np220-ftp250"],
)
def test_power_worked_example_tss(
    duration_s: float, np_w: float, ftp_w: float, published_tss: float
) -> None:
    """Coggan (2003): ``TSS = duration_s * NP * IF / (FTP * 3600) * 100``,
    computed here from the formula's own text (``COGGAN_TSS`` note), not by
    calling the shipped ``power_tss`` -- so a break in that shipped
    function's arithmetic is what this test is written to catch, not
    merely restated by it. ``published_tss`` is the rounded figure printed
    in design.md line 974-975 / research.md line 106-107 (``TSS ≈ 142`` /
    ``TSS ≈ 116`` for these same duration/NP/FTP triples); the formula's
    unrounded result (142.48, 116.16) agrees with it to within 1."""
    assert COGGAN_TSS.key == "coggan_tss"
    intensity_factor = np_w / ftp_w
    expected_tss = duration_s * np_w * intensity_factor / (ftp_w * 3600.0) * 100.0
    assert expected_tss == pytest.approx(published_tss, abs=1)

    metrics = DerivedMetrics(normalized_power_w=np_w, moving_time_s=duration_s)
    result = power.compute(
        _power_activity(int(duration_s)),
        metrics,
        ftp=_ftp(ftp_w),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(expected_tss, rel=1e-9)


# ---------------------------------------------------------------------------
# Heart-rate channel -- Banister (1991) p. 408, :data:`BANISTER_TRIMP`
# (Req 5.10, 8.4). TRAP: the expected value below is computed from the
# formula's own text, NEVER from a B91 figure caption -- see this module's
# docstring and docs/reference/banister-trimp-primary-sources.md D4.
# ---------------------------------------------------------------------------


def test_heart_rate_worked_example_training_impulse_from_formula() -> None:
    """Banister (1991) p. 408: ``y = 0.64 * e^(1.92x)`` (male),
    ``TRIMP = T(min) * x * y`` where ``x = (HR - HR_rest) / (HR_max -
    HR_rest)``. 30 min at 130 bpm, HR_rest 40, HR_max 200:

        x = (130 - 40) / (200 - 40) = 0.5625
        y = 0.64 * e^(1.92 * 0.5625)
        TRIMP = 30 * x * y

    computed here directly from the published formula (``BANISTER_TRIMP``'s
    own note quotes p. 408 verbatim for the coefficient/exponent pair), not
    from Fig. 9.5/9.6's captions, which the source's own D4 discrepancy
    states are self-inconsistent with this equation and therefore unusable
    as vectors. Verified by calling :func:`fitdocs.metrics.stress.trimp`
    directly -- the same function the heart-rate channel's weighting seam
    delegates to unchanged, per
    ``test_weighting.py::test_activity_impulse_calls_trimp_once_with_the_callers_exact_samples_object``,
    not re-proven here -- rather than by restating the accumulation as an
    independent integration in this test."""
    assert BANISTER_TRIMP.key == "banister_trimp"
    resting_hr, max_hr, hr = 40, 200, 130
    duration_min = 30.0
    x = (hr - resting_hr) / (max_hr - resting_hr)
    y = 0.64 * math.exp(1.92 * x)
    expected = duration_min * x * y

    samples = _hr_samples(int(duration_min * 60), hr)
    weighting = metrics_sources.weighting_for(None)
    result = trimp(samples, resting_hr, max_hr, weighting)
    assert result is not None
    assert result.value == pytest.approx(expected, rel=1e-9)


def test_heart_rate_threshold_identity() -> None:
    """Req 1.6: one hour spent entirely at LTHR scores 100 with an
    intensity of 1.0 -- to floating-point precision (measured
    ``load == 100.00000000000355``, ``intensity == 1.0000000000000178``,
    relative error ~3.5e-14, per ``trimp``'s 3600-term summation against a
    single-interval reference), not exact equality."""
    result = heart_rate.compute(
        _hr_activity(3600, 165),
        DerivedMetrics(),
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(100.0)
    assert result.intensity == pytest.approx(1.0)


def test_heart_rate_load_bit_identical_when_coefficient_rescaled_by_power_of_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 5.10: rescaling the shipped training-impulse multiplicative
    coefficient by a power of two leaves the heart-rate LOAD exactly
    bit-identical while the raw impulse moves -- bounding the blast radius
    of the pending upstream Banister-coefficient re-sourcing, and matching
    ``design.md:1381-1383`` / ``tasks.md:453-455``'s "bit-identical"
    requirement exactly rather than to a relative tolerance. The
    coefficient cancels *algebraically* between the activity's impulse and
    the one-hour-at-threshold reference (both scored through the identical
    call path over the same per-sample-pair summation), and multiplying a
    float by a power of two is exact in IEEE-754 (it only changes the
    exponent field, never the mantissa), so every per-term product and
    every partial sum scales by exactly the same factor and the two loads'
    bit patterns agree exactly -- measured here: ``factor=8.0`` gives
    ``rescaled.load == baseline.load`` (``56.07873353156503`` both times,
    relative error ``0.0``). A non-power-of-two factor does *not* hold:
    ``factor=7.0`` measures ``56.07873353156187`` against the same
    baseline, a relative error of ``~5.6e-14`` -- because scaling by 7
    rounds each per-term product, unlike scaling by a power of two."""
    from dataclasses import replace

    activity = _hr_activity(3600, 140)
    kwargs = dict(
        metrics=DerivedMetrics(),
        lthr=_lthr(165),
        resting_hr=_resting_hr(48),
        max_hr=_max_hr(190),
        settings=_SETTINGS,
    )
    baseline = heart_rate.compute(activity, **kwargs)  # type: ignore[arg-type]
    assert isinstance(baseline, ChannelLoad)

    original_pair = metrics_sources.weighting_for(None)
    factor = 8.0
    rescaled_pair = replace(
        original_pair,
        coefficient=replace(
            original_pair.coefficient, value=original_pair.coefficient.value * factor
        ),
    )
    monkeypatch.setattr(
        metrics_sources, "weighting_for", lambda selection: rescaled_pair
    )
    rescaled = heart_rate.compute(activity, **kwargs)  # type: ignore[arg-type]
    assert isinstance(rescaled, ChannelLoad)

    assert rescaled.load == baseline.load

    baseline_impulse = float(dict(baseline.inputs_used)["impulse"])
    rescaled_impulse = float(dict(rescaled.inputs_used)["impulse"])
    assert rescaled_impulse != pytest.approx(baseline_impulse)
    assert rescaled_impulse == pytest.approx(baseline_impulse * factor, rel=1e-4)


# ---------------------------------------------------------------------------
# Pace channel -- intervals.icu pace-load formulation,
# :data:`INTERVALS_ICU_PACE_LOAD` (Req 4.8 / 8.4 applied to the pace
# channel, 6.1, 6.8)
# ---------------------------------------------------------------------------


def test_pace_worked_example_from_formula() -> None:
    """intervals.icu's published pace-load formulation
    (``INTERVALS_ICU_PACE_LOAD``): ``intensity = gap_speed / threshold_speed``,
    ``load = (moving_time_s / 3600) * intensity**2 * 100``, over moving
    time. Threshold pace 200 s/km -> threshold speed 5.0 m/s; 1800 s of
    moving time at a constant 4.0 m/s (level ground, no altitude stream):

        intensity = 4.0 / 5.0 = 0.8
        load = (1800 / 3600) * 0.8**2 * 100 = 32.0

    computed here directly from the published formula, independently of
    ``pace.py``'s own arithmetic."""
    assert INTERVALS_ICU_PACE_LOAD.key == "intervals_icu_pace_load"
    threshold_speed_mps = 1000.0 / 200.0
    gap_speed_mps = 4.0
    moving_time_s = 1800.0
    expected_intensity = gap_speed_mps / threshold_speed_mps
    expected_load = (moving_time_s / 3600.0) * expected_intensity**2 * 100.0
    assert expected_intensity == pytest.approx(0.8)
    assert expected_load == pytest.approx(32.0)

    result = pace.compute(
        _pace_activity(1800, gap_speed_mps),
        DerivedMetrics(moving_time_s=moving_time_s),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(expected_intensity)
    assert result.load == pytest.approx(expected_load, rel=1e-9)


def test_pace_threshold_identity() -> None:
    """Req 1.6: one hour at threshold pace, level ground, scores exactly
    100 with an intensity of exactly 1.0."""
    result = pace.compute(
        _pace_activity(3600, 5.0),
        DerivedMetrics(moving_time_s=3600.0),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(100.0)
    assert result.intensity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Threshold identity across all three channels, in one place (Req 1.6) --
# deliberately half the scale contract, per the task's own text: a
# threshold-only assertion cannot distinguish a linear intensity from a
# squared one (task 5.3 owns the sub-threshold cross-channel proof).
# ---------------------------------------------------------------------------


def test_threshold_identity_holds_for_all_three_channels_at_once() -> None:
    """One hour held exactly at threshold scores 100 for power, heart rate
    and pace alike, each with an intensity of 1.0 -- exactly for power and
    pace (measured ``== 100.0`` and ``== 1.0``), and to floating-point
    precision for heart rate (measured ``load == 100.00000000000358``,
    ``intensity == 1.0000000000000178``, relative error ~3.6e-14, per
    ``trimp``'s 3600-term summation against a single-interval reference)."""
    power_result = power.compute(
        _power_activity(3600, watts=250),
        DerivedMetrics(normalized_power_w=250.0, moving_time_s=3600.0),
        ftp=_ftp(250.0),
        settings=_SETTINGS,
    )
    hr_result = heart_rate.compute(
        _hr_activity(3600, 172),
        DerivedMetrics(),
        lthr=_lthr(172),
        resting_hr=_resting_hr(50),
        max_hr=_max_hr(195),
        settings=_SETTINGS,
    )
    pace_result = pace.compute(
        _pace_activity(3600, 5.0),
        DerivedMetrics(moving_time_s=3600.0),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )

    for result in (power_result, hr_result, pace_result):
        assert isinstance(result, ChannelLoad)
        assert result.load == pytest.approx(100.0)
        assert result.intensity == pytest.approx(1.0)
