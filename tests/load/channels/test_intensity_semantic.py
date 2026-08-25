"""Cross-channel proof that the one shared intensity semantic holds away
from threshold, for power, heart rate and pace alike (task 5.3).

Covers Requirements 1.11, 5.11, 8.7 -- see
``.kiro/specs/load-channels/requirements.md`` and design.md's "Testing
Strategy" -> "Integration Tests" -> "Intensity semantic, at more than one
point" and the ``HeartRateChannel`` "Implementation Notes" worked table
(the "resting 48 / max 190 / LTHR 165" table in design.md's
``HeartRateChannel`` section, currently at lines 1061-1067).

**Read-only over the channel modules** (task boundary): this module imports
``power``, ``heart_rate`` and ``pace`` and calls their public ``compute``
functions only, plus ``weighting.BANISTER_TRIMP_MODEL`` directly, at two
independent sites below (``_bare_impulse_ratio`` and
``test_heart_rate_load_is_numerically_identical_to_the_impulse_ratio_load``),
to compute expectations independently of ``heart_rate.compute``. No source
module
under ``src/fitdocs/load/channels/`` is edited by this task -- the
mutation-based discrimination evidence for this module's assertions was
gathered by editing a channel module's source line, observing the suite, and
reverting it, entirely outside this file's own content; that process and its
results are recorded in the task's Status Report, not here.

**WHY A THRESHOLD-ONLY ASSERTION PROVES NOTHING (the reason this module
exists at all).** The shared semantic this feature defines is
``load == hours * intensity**2 * 100``. At the single point ``intensity ==
1.0`` (exactly threshold), ``x``, ``sqrt(x)`` and ``x**2`` all evaluate to
``1.0`` -- an impulse ratio, its square root, and its square are numerically
identical there. A test that only holds an activity at threshold therefore
passes under *any* candidate intensity definition and proves nothing about
which one is actually implemented: this is exactly the trap that shipped the
original defect this task's amendment exists to prevent (spec.json's
2026-07-25 amendment note; heart_rate.py previously reported
``intensity = impulse_ratio``, the *square* of what power and pace report,
and it coincided with them only at 1.0, which the pre-amendment scale-
invariance test alone could not detect). Most assertions below are therefore
anchored away from 1.0; three tests below are anchored *at* exactly 1.0
(threshold) instead, and are required there by the task's "at threshold and
at sub-threshold" -- they exist to hold the boundary green while the
sub-threshold anchors go red under a wrong definition, which is what this
module's sensitivity test (below) demonstrates directly. Measured directly
against this module's
own fixtures (RESTING=48, MAX=190, LTHR=165, one hour at a constant rate --
see ``test_heart_rate_intensity_bare_impulse_ratio_measured_deltas`` below,
which runs and asserts these exact figures rather than merely stating them):
at 120 bpm the bare impulse ratio is ``0.33488820475342274`` against a
reported intensity of ``0.5786952606972194`` (delta ``0.2438070559437967``);
at 140 bpm the ratio is ``0.5607873353156503`` against ``0.7488573531158322``
(delta ``0.18807001780018195``). The two deltas straddle the ``0.20`` default
``divergence_max_intensity_delta`` the (out-of-boundary) ``activity-qa-flags``
feature will compare against (``.kiro/specs/activity-qa-flags/design.md``,
line 1464): the 120 bpm delta, ``0.2438``, is *above* 0.20 and would trip that
flag's default divergence comparison, while the 140 bpm delta, ``0.1881``, is
*below* 0.20 and would **not**. Neither anchor is tied to the other (0.244 vs
0.188, not repeated values). This module's own assertions, at ``rel=1e-9``,
catch a mis-scaled heart-rate intensity at both anchors regardless -- which is
a stronger reason for this module to exist than either anchor alone crossing
the other feature's coarser threshold.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate, pace, power
from fitdocs.load.channels.types import ChannelLoad, SufficiencySettings
from fitdocs.load.channels.weighting import BANISTER_TRIMP_MODEL
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# fixture builders -- self-contained in this module, following the same
# shape as test_worked_examples.py's (task 5.1), not imported from any
# single-channel test module (task boundary: read-only subject, own test
# module).
# ---------------------------------------------------------------------------

_SETTINGS = SufficiencySettings()

# The heart-rate benchmark trio used throughout this module -- the same
# resting/max/LTHR triple the design's own worked table (design.md
# lines 1058-1071) uses, so the deltas quoted in this module's docstring are
# reproducible against a documented anchor rather than an arbitrary one.
_RESTING_HR = 48
_MAX_HR = 190
_LTHR = 165


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


def _hr_result(heart_rate_bpm: int, *, n_seconds: int = 3600) -> ChannelLoad:
    result = heart_rate.compute(
        _hr_activity(n_seconds, heart_rate_bpm),
        DerivedMetrics(),
        lthr=_lthr(_LTHR),
        resting_hr=_resting_hr(_RESTING_HR),
        max_hr=_max_hr(_MAX_HR),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    return result


def _matching_power_result(*, load: float, n_seconds: int) -> ChannelLoad:
    """A power-channel result carrying exactly ``load`` over ``n_seconds`` of
    moving time, constructed from the semantic itself
    (``intensity == sqrt(load / (hours * 100))``) rather than by guessing an
    NP/FTP pair -- so the construction cannot silently be wrong (the
    "indistinguishable outcome" trap: this helper does not smuggle in the
    conclusion, because the power channel's own ``intensity = np_w /
    ftp.value`` is computed independently of this helper's algebra and is
    checked against ``load`` explicitly by every caller below via the
    ``power_result.load == pytest.approx(load, ...)`` assertion)."""
    hours = n_seconds / 3600.0
    intensity = math.sqrt(load / (hours * 100.0))
    ftp = 200.0
    np_w = ftp * intensity
    result = power.compute(
        _power_activity(n_seconds, watts=round(np_w)),
        DerivedMetrics(normalized_power_w=np_w, moving_time_s=float(n_seconds)),
        ftp=_ftp(ftp),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    return result


# ---------------------------------------------------------------------------
# Bullet 1: per channel, load == hours * intensity**2 * 100, away from
# threshold, within a stated relative tolerance (Req 1.11).
# ---------------------------------------------------------------------------

_RELATIVE_TOLERANCE = 1e-9


def test_power_intensity_semantic_holds_away_from_threshold() -> None:
    """Sub-threshold power (IF 0.575, NP 161 W / FTP 280 W), a non-round
    duration (4500 s = 1.25 h) chosen so a hard-coded ``hours == 1``
    shortcut could not pass this test by accident."""
    duration_s = 4500.0
    np_w, ftp_w = 161.0, 280.0
    result = power.compute(
        _power_activity(int(duration_s), watts=int(np_w)),
        DerivedMetrics(normalized_power_w=np_w, moving_time_s=duration_s),
        ftp=_ftp(ftp_w),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(0.575)
    assert result.intensity != pytest.approx(1.0)

    hours = result.scored_duration_s / 3600.0
    expected_load = hours * result.intensity**2 * 100.0
    assert result.load == pytest.approx(expected_load, rel=_RELATIVE_TOLERANCE)


def test_pace_intensity_semantic_holds_away_from_threshold() -> None:
    """Sub-threshold pace (intensity 0.7, gap speed 3.5 m/s / threshold
    speed 5.0 m/s), a non-round duration (2700 s = 0.75 h)."""
    duration_s = 2700
    gap_speed_mps = 3.5
    result = pace.compute(
        _pace_activity(duration_s, gap_speed_mps),
        DerivedMetrics(moving_time_s=float(duration_s)),
        threshold_pace=_threshold_pace(200.0),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(0.7)
    assert result.intensity != pytest.approx(1.0)

    hours = result.scored_duration_s / 3600.0
    expected_load = hours * result.intensity**2 * 100.0
    assert result.load == pytest.approx(expected_load, rel=_RELATIVE_TOLERANCE)


@pytest.mark.parametrize("heart_rate_bpm", [120, 140], ids=["120bpm", "140bpm"])
def test_heart_rate_intensity_semantic_holds_away_from_threshold(
    heart_rate_bpm: int,
) -> None:
    """Sub-threshold heart rate (120 and 140 bpm against LTHR 165), a
    non-round duration (2400 s = 40 min) distinct from the 3600 s used by
    the cross-channel anchors below, so this assertion is not merely a
    restatement of those under a shared fixture."""
    duration_s = 2400
    result = heart_rate.compute(
        _hr_activity(duration_s, heart_rate_bpm),
        DerivedMetrics(),
        lthr=_lthr(_LTHR),
        resting_hr=_resting_hr(_RESTING_HR),
        max_hr=_max_hr(_MAX_HR),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity != pytest.approx(1.0)

    hours = result.scored_duration_s / 3600.0
    expected_load = hours * result.intensity**2 * 100.0
    assert result.load == pytest.approx(expected_load, rel=_RELATIVE_TOLERANCE)


# ---------------------------------------------------------------------------
# Bullet 2: cross-channel agreement at more than one point -- threshold AND
# two sub-threshold anchors where the linear (bare impulse ratio) and the
# square-root intensity definitions differ by a wide, pairwise-distinct
# margin (Req 8.7, 5.11).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heart_rate_bpm", [165, 120, 140], ids=["165bpm-threshold", "120bpm", "140bpm"]
)
def test_cross_channel_intensity_agrees_at_threshold_and_sub_threshold_anchors(
    heart_rate_bpm: int,
) -> None:
    """A heart-rate result and a power result carrying the *same* load over
    the *same* one-hour duration report the same intensity -- at threshold
    (165 bpm) and at two clearly sub-threshold anchors (120, 140 bpm) where
    a linear and a square-root intensity definition diverge by roughly 0.24
    and 0.19 respectively (see this module's docstring for the measured
    figures). The power result's ``load`` is asserted equal to the
    heart-rate result's ``load`` first, so a construction error in
    ``_matching_power_result`` cannot silently make the intensities agree by
    accident (the "indistinguishable outcome" hazard)."""
    hr_result = _hr_result(heart_rate_bpm)
    power_result = _matching_power_result(load=hr_result.load, n_seconds=3600)

    assert power_result.load == pytest.approx(hr_result.load, rel=_RELATIVE_TOLERANCE)
    assert power_result.intensity == pytest.approx(
        hr_result.intensity, rel=_RELATIVE_TOLERANCE
    )


# ---------------------------------------------------------------------------
# Bullet 4: sensitivity demonstration -- substituting the bare impulse ratio
# for the heart-rate channel's reported intensity must fail the
# cross-channel assertion above at the sub-threshold anchors while still
# passing at threshold. Computed directly here from
# BANISTER_TRIMP_MODEL, the same production seam heart_rate.compute injects
# by default, never by editing heart_rate.py (task boundary: read-only).
# ---------------------------------------------------------------------------


def _bare_impulse_ratio(heart_rate_bpm: int, *, n_seconds: int = 3600) -> float:
    """The candidate intensity heart_rate.py reported before Req 5.11's
    amendment: the *unsquared* mean impulse rate relative to threshold,
    computed the same way :func:`heart_rate.compute` computes ``load``
    (``activity_impulse / reference * 100``) and then expressed as a ratio
    the same way ``heart_rate.py``'s module docstring defines "the bare
    impulse rate" (``(load / 100) / (scored_duration_s / 3600)``) -- but
    stopping short of the square root that turns it into ``intensity``."""
    samples = _hr_samples(n_seconds, heart_rate_bpm)
    activity_impulse = BANISTER_TRIMP_MODEL.activity_impulse(
        samples, resting_hr=_RESTING_HR, max_hr=_MAX_HR
    )
    reference = BANISTER_TRIMP_MODEL.hourly_impulse_at(
        _LTHR, resting_hr=_RESTING_HR, max_hr=_MAX_HR
    )
    assert activity_impulse is not None
    assert reference is not None and reference > 0
    load = activity_impulse / reference * 100.0
    hours = n_seconds / 3600.0
    return (load / 100.0) / hours


def test_heart_rate_intensity_bare_impulse_ratio_measured_deltas() -> None:
    """Pins the exact numbers this module's docstring quotes, so a future
    edit to the fixtures (resting/max/LTHR, or the anchor bpm values) cannot
    silently invalidate the prose claim without this assertion catching it
    first."""
    for bpm, expected_ratio, expected_intensity, expected_delta in (
        (120, 0.33488820475342274, 0.5786952606972194, 0.2438070559437967),
        (140, 0.5607873353156503, 0.7488573531158322, 0.18807001780018195),
    ):
        ratio = _bare_impulse_ratio(bpm)
        intensity = _hr_result(bpm).intensity
        assert ratio == pytest.approx(expected_ratio, rel=1e-9)
        assert intensity == pytest.approx(expected_intensity, rel=1e-9)
        assert (intensity - ratio) == pytest.approx(expected_delta, rel=1e-9)


@pytest.mark.parametrize(
    ("heart_rate_bpm", "expect_agreement"),
    [(165, True), (120, False), (140, False)],
    ids=["165bpm-threshold-still-agrees", "120bpm-diverges", "140bpm-diverges"],
)
def test_substituting_bare_ratio_fails_cross_channel_agreement_only_away_from_threshold(
    heart_rate_bpm: int, expect_agreement: bool
) -> None:
    """The task's required sensitivity demonstration: substituting the bare
    impulse ratio for the heart-rate channel's reported intensity must fail
    the cross-channel agreement assertion at the sub-threshold anchors while
    still passing at threshold -- proving this module's assertions actually
    discriminate the square-root definition from the linear one, not merely
    from an arbitrary wrong constant."""
    hr_result = _hr_result(heart_rate_bpm)
    power_result = _matching_power_result(load=hr_result.load, n_seconds=3600)
    assert power_result.load == pytest.approx(hr_result.load, rel=_RELATIVE_TOLERANCE)
    substituted_intensity = _bare_impulse_ratio(heart_rate_bpm)

    agrees = substituted_intensity == pytest.approx(
        power_result.intensity, rel=_RELATIVE_TOLERANCE
    )
    assert agrees is expect_agreement


# ---------------------------------------------------------------------------
# Bullet 5: the heart-rate loads used here are numerically identical to the
# impulse-ratio loads -- the intensity definition (Req 5.11) moved no load
# value (Req 1.7: load is computed independently of intensity).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("heart_rate_bpm", [120, 140, 165])
def test_heart_rate_load_is_numerically_identical_to_the_impulse_ratio_load(
    heart_rate_bpm: int,
) -> None:
    """``heart_rate.compute``'s ``load`` is compared against a load computed
    independently -- directly through ``BANISTER_TRIMP_MODEL``, never by
    calling ``heart_rate.compute`` a second time -- using exactly the
    formula the pre-5.11 channel used for its (identically-named) ``load``:
    ``activity_impulse / reference * 100``. Because the amendment changed
    only how intensity is *reported*, not this formula, the two must agree
    to floating-point precision regardless of which intensity definition is
    in effect."""
    samples = _hr_samples(3600, heart_rate_bpm)
    activity_impulse = BANISTER_TRIMP_MODEL.activity_impulse(
        samples, resting_hr=_RESTING_HR, max_hr=_MAX_HR
    )
    reference = BANISTER_TRIMP_MODEL.hourly_impulse_at(
        _LTHR, resting_hr=_RESTING_HR, max_hr=_MAX_HR
    )
    assert activity_impulse is not None
    assert reference is not None and reference > 0
    independent_load = activity_impulse / reference * 100.0

    result = _hr_result(heart_rate_bpm)
    assert result.load == pytest.approx(independent_load, rel=_RELATIVE_TOLERANCE)
