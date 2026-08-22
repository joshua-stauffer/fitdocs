"""Facade tests for :func:`fitdocs.metrics.compute_metrics`.

``compute_metrics`` is the one-call derivation of the full
:class:`~fitdocs.metrics.types.DerivedMetrics` set. These tests pin the things
the facade owns beyond the already-tested individual functions:

* **The with/without-athlete flip (observable acceptance).** Passing athlete
  inputs flips *only* the seven threshold-dependent fields between ``None``
  and a value; every independent field is byte-for-byte identical across the
  two calls (Req 8.5, 10.5, 11.1, 11.2).
* **Zone facade mapping (Req 10.1, 10.5).** HR values map directly, power
  directly, and pace per-sample as ``1000 / speed_mps`` s/km with
  ``speed <= 0``/``None`` excluded; each channel's time-in-zone is ``None`` when
  its :class:`~fitdocs.metrics.types.ZoneSpec` *or* its underlying channel is
  absent, and a tuple of length ``dividers + 1`` otherwise.
* **Purity, determinism, and never-raising (Req 12.1, 12.2, 13.3).** The facade
  returns a ``DerivedMetrics`` for degenerate activities without raising, and is
  equal on repeat calls with identical inputs.
* **Training-impulse weighting threading (Amendment 1, Req 17).** The
  caller's ``trimp_weighting`` selection is resolved exactly once, before any
  metric is computed (both code intent, not something these tests
  discriminate), and unconditionally -- even when TRIMP itself will be
  ``None`` for lack of thresholds, an unrecognized selection is still rejected
  (Req 17.4 over 17.5 on the error path); an absent selection defaults rather
  than erroring (Req 17.2, pinned by value, not member name); two distinct
  selections produce distinct TRIMP values for identical samples (Req 17.1);
  and :attr:`~fitdocs.metrics.types.DerivedMetrics.trimp_weighting` is
  non-``None`` exactly when :attr:`~fitdocs.metrics.types.DerivedMetrics.trimp`
  is (Req 17.6).

The fixture spans are deliberately short (9 s), so ``normalized_power`` is
``None`` over them; to exercise the NP-dependent threshold fields (intensity
factor, power TSS) a synthetic constant-power bike activity spanning >= 30 s is
built directly from the model types.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from fitdocs.ingest import parse_fit
from fitdocs.metrics import aggregates, compute_metrics, power, sources, stress, zones
from fitdocs.metrics.types import (
    AthleteInputs,
    DerivedMetrics,
    TrimpWeighting,
    ZoneSpec,
)
from fitdocs.model import (
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)

# The seven athlete-input-dependent fields; everything else in DerivedMetrics
# is independent of AthleteInputs and must be unchanged by supplying it.
_THRESHOLD_FIELDS = (
    "intensity_factor",
    "power_tss",
    "trimp",
    "trimp_weighting",
    "hr_time_in_zone_s",
    "power_time_in_zone_s",
    "pace_time_in_zone_s",
)


# --- synthetic model builders (tests are not mypy-checked) ------------------


def _summary(**overrides: object) -> SessionSummary:
    """A ``SessionSummary`` with every field ``None`` unless overridden."""
    fields: dict[str, object] = {
        "sport": None,
        "sub_sport": None,
        "start_time": None,
        "total_elapsed_time_s": None,
        "total_timer_time_s": None,
        "total_distance_m": None,
        "total_calories_kcal": None,
        "total_ascent_m": None,
        "total_descent_m": None,
        "avg_heart_rate_bpm": None,
        "max_heart_rate_bpm": None,
        "avg_power_w": None,
        "max_power_w": None,
        "avg_cadence_rpm": None,
        "max_cadence_rpm": None,
        "avg_speed_mps": None,
        "max_speed_mps": None,
    }
    fields.update(overrides)
    return SessionSummary(**fields)  # type: ignore[arg-type]


def _samples(time_s: tuple[float, ...], **channels: object) -> Samples:
    """A ``Samples`` whose channels default to all-``None`` arrays of the right
    length; pass any channel by name to populate it."""
    n = len(time_s)
    none_tuple = (None,) * n
    defaults: dict[str, object] = {
        "heart_rate_bpm": none_tuple,
        "power_w": none_tuple,
        "cadence_rpm": none_tuple,
        "speed_mps": none_tuple,
        "distance_m": none_tuple,
        "altitude_m": none_tuple,
        "latitude_deg": none_tuple,
        "longitude_deg": none_tuple,
        "temperature_c": none_tuple,
    }
    defaults.update(channels)
    return Samples(time_s=time_s, **defaults)  # type: ignore[arg-type]


def _activity(
    samples: Samples,
    *,
    modality: Modality = Modality.OTHER,
    sport: Sport = Sport.WORKOUT,
    summary: SessionSummary | None = None,
) -> Activity:
    """A minimal synthetic ``Activity`` around ``samples``."""
    return Activity(
        schema_version="1.0",
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=summary if summary is not None else _summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


def _bike_activity_with_power() -> Activity:
    """Constant 200 W / 150 bpm / 5 m/s bike activity spanning 60 s.

    The 60 s span clears the 30 s normalized-power floor, so NP is computable
    (exactly 200 W for a constant series) and the NP-dependent threshold fields
    (IF, power TSS) can actually flip when athlete inputs are supplied.
    """
    n = 61
    time_s = tuple(float(i) for i in range(n))
    summary = _summary(
        total_timer_time_s=60.0,
        total_elapsed_time_s=60.0,
        total_distance_m=300.0,
        avg_power_w=200,
        max_power_w=200,
        avg_heart_rate_bpm=150,
        max_heart_rate_bpm=150,
        avg_speed_mps=5.0,
        max_speed_mps=5.0,
    )
    samples = _samples(
        time_s,
        power_w=(200,) * n,
        heart_rate_bpm=(150,) * n,
        speed_mps=(5.0,) * n,
        distance_m=tuple(5.0 * i for i in range(n)),
    )
    return _activity(samples, modality=Modality.BIKE, sport=Sport.RIDE, summary=summary)


# --- 1. with/without athlete flips only threshold fields (observable) -------


def test_athlete_inputs_flip_only_threshold_fields() -> None:
    activity = _bike_activity_with_power()

    without = compute_metrics(activity)
    athlete = AthleteInputs(
        ftp_watts=200,
        resting_hr_bpm=40,
        max_hr_bpm=190,
        power_zones=ZoneSpec((100, 150, 250)),
        hr_zones=ZoneSpec((120, 160)),
        pace_zones=ZoneSpec((100, 300)),
    )
    with_athlete = compute_metrics(activity, athlete)

    # Every threshold field: None without athlete, a value with athlete.
    for name in _THRESHOLD_FIELDS:
        assert getattr(without, name) is None, f"{name} should be None without athlete"
        assert getattr(with_athlete, name) is not None, f"{name} should flip on"

    # Every independent field is identical across the two calls.
    for f in dataclasses.fields(DerivedMetrics):
        if f.name in _THRESHOLD_FIELDS:
            continue
        assert getattr(without, f.name) == getattr(with_athlete, f.name), f.name

    # The independent fields are actually computed, not merely equal-and-None.
    assert without.normalized_power_w == 200.0
    assert without.avg_power_w == 200
    assert without.moving_time_s == 60.0
    assert without.variability_index == 1.0
    assert without.efficiency_factor is not None

    # And the flipped-on values match their individual functions exactly.
    assert with_athlete.intensity_factor == power.intensity_factor(200.0, 200)
    assert with_athlete.power_tss == stress.power_tss(200.0, 60.0, 200)
    default_pair = sources.weighting_for(None)
    expected_trimp = stress.trimp(activity.samples, 40, 190, default_pair)
    assert expected_trimp is not None
    assert with_athlete.trimp == expected_trimp.value
    assert with_athlete.trimp_weighting == expected_trimp.weighting


def test_without_athlete_never_uses_default_thresholds() -> None:
    # athlete=None is equivalent to AthleteInputs() (all fields None): no
    # threshold-dependent metric may appear.
    activity = _bike_activity_with_power()
    assert compute_metrics(activity) == compute_metrics(activity, AthleteInputs())


# --- 1b. training-impulse weighting threading (Amendment 1, Req 17) --------


def test_two_weighting_selections_produce_different_trimp_values() -> None:
    """Req 17.1: the facade actually threads the caller's selection through to
    :func:`fitdocs.metrics.stress.trimp` rather than always resolving the
    default -- pinned by computing the *same* samples and thresholds under
    both registered selections and requiring the two TRIMP values (and the
    two reported weightings) to differ. A facade that ignored
    ``athlete.trimp_weighting`` and always used the default pair would report
    the identical value (and the identical weighting) for both calls and fail
    this test.
    """
    activity = _bike_activity_with_power()
    male = compute_metrics(
        activity,
        AthleteInputs(
            resting_hr_bpm=40,
            max_hr_bpm=190,
            trimp_weighting=TrimpWeighting.BANISTER_MALE,
        ),
    )
    female = compute_metrics(
        activity,
        AthleteInputs(
            resting_hr_bpm=40,
            max_hr_bpm=190,
            trimp_weighting=TrimpWeighting.BANISTER_FEMALE,
        ),
    )
    assert male.trimp is not None
    assert female.trimp is not None
    assert male.trimp != female.trimp
    assert male.trimp_weighting == TrimpWeighting.BANISTER_MALE
    assert female.trimp_weighting == TrimpWeighting.BANISTER_FEMALE


def test_no_selection_reproduces_the_pre_amendment_value_pinned_by_value() -> None:
    """Req 17.2: supplying no ``trimp_weighting`` must reproduce the exact
    TRIMP value fitdocs computed before Amendment 1 -- pinned here directly
    against the historical formula's own numeric literals (``0.64`` / ``1.92``
    hand-computed inline, not read from :mod:`fitdocs.metrics.sources` at
    all), so a future rename of ``TrimpWeighting.BANISTER_MALE`` cannot weaken
    this guarantee (design.md's open member-naming decision).

    A synthetic single-pair activity is used (rather than the shared bike
    fixture) so the expected value is a hand-computed constant rather than a
    value re-derived through the same resolver under test.
    """
    # rest=60, max=200 -> reserve=140; one pair, dt=60s, earlier HR=130.
    #   HRr = (130-60)/140 = 0.5
    #   trimp = 1.0 * 0.5 * 0.64 * exp(1.92 * 0.5) = 0.8357428714953977
    time_s = (0.0, 60.0)
    samples = _samples(time_s, heart_rate_bpm=(130, 999))
    activity = _activity(samples, modality=Modality.RUN, sport=Sport.RUN)
    dm = compute_metrics(activity, AthleteInputs(resting_hr_bpm=60, max_hr_bpm=200))
    expected = 1.0 * 0.5 * 0.64 * math.exp(1.92 * 0.5)
    assert dm.trimp == pytest.approx(expected, rel=1e-12)
    assert dm.trimp == pytest.approx(0.8357428714953977, rel=1e-12)


def test_unrecognized_weighting_selection_raises_even_when_thresholds_absent() -> None:
    """Req 17.4 over 17.5: an unrecognized selection is a caller error that
    must fail loudly *even when TRIMP would be* ``None`` *anyway* for lack of
    resting/maximum heart rate -- the resolution happens unconditionally,
    before any metric (including the absent-threshold check) is evaluated.
    A facade that only resolved the selection once it knew TRIMP would be
    computable (i.e. after checking the thresholds) would swallow this error
    silently and return a normal ``DerivedMetrics`` instead of raising.
    """
    activity = _activity(_samples((0.0, 1.0)))  # no resting/max HR supplied at all
    with pytest.raises(ValueError) as exc_info:
        compute_metrics(
            activity,
            AthleteInputs(trimp_weighting="not_a_real_selection"),  # type: ignore[arg-type]
        )
    message = str(exc_info.value)
    assert "not_a_real_selection" in message
    for member in TrimpWeighting:
        assert member.value in message


def test_trimp_weighting_absent_when_thresholds_absent_even_with_selection() -> None:
    """The green-making trap this task warns about: reporting the resolved
    weighting whenever the caller supplied *any* non-default
    :class:`AthleteInputs` (rather than exactly when TRIMP itself is present)
    would pass the with/without-athlete flip test above -- whose
    ``with_athlete`` call supplies thresholds (and so is non-default) without
    an explicit ``trimp_weighting``, and whose ``without`` call passes no
    athlete at all (the literal default) -- while destroying Req 17.6's
    invariant. This test supplies a *real* selection with *no* thresholds
    (a non-default ``AthleteInputs`` all the same) and requires both fields
    to stay ``None`` together; it and
    :func:`test_trimp_none_under_every_selection_when_thresholds_absent` are
    exactly what catch that trap -- the flip test above does not.
    """
    activity = _activity(_samples((0.0, 1.0), heart_rate_bpm=(130, 140)))
    dm = compute_metrics(
        activity, AthleteInputs(trimp_weighting=TrimpWeighting.BANISTER_FEMALE)
    )
    assert dm.trimp is None
    assert dm.trimp_weighting is None


def test_trimp_none_under_every_selection_when_thresholds_absent() -> None:
    """Req 17.5: absent resting/maximum heart rate yields ``trimp is None``
    regardless of which selection (including none) was supplied."""
    activity = _activity(_samples((0.0, 1.0), heart_rate_bpm=(130, 140)))
    for selection in (
        None,
        TrimpWeighting.BANISTER_MALE,
        TrimpWeighting.BANISTER_FEMALE,
    ):
        dm = compute_metrics(activity, AthleteInputs(trimp_weighting=selection))
        assert dm.trimp is None
        assert dm.trimp_weighting is None


# --- 2. zone facade mapping (Req 10.1, 10.5) --------------------------------


def test_power_zone_maps_channel_directly(ride_fit_bytes: bytes) -> None:
    activity = parse_fit(ride_fit_bytes)  # alternating 190/210 W over 10 samples
    dm = compute_metrics(activity, AthleteInputs(power_zones=ZoneSpec((150, 205))))
    # Bands: 190 -> band 1, 210 -> band 2; earlier-sample attribution over the
    # nine 1 s gaps => five even indices (190) in band 1, four odd (210) in band 2.
    assert dm.power_time_in_zone_s == (0.0, 5.0, 4.0)


def test_power_zone_none_without_spec(ride_fit_bytes: bytes) -> None:
    activity = parse_fit(ride_fit_bytes)
    assert compute_metrics(activity).power_time_in_zone_s is None


def test_power_zone_none_when_channel_absent(run_fit_bytes: bytes) -> None:
    # The run fixture records no power; a power ZoneSpec still yields None (10.5).
    activity = parse_fit(run_fit_bytes)
    dm = compute_metrics(activity, AthleteInputs(power_zones=ZoneSpec((150, 205))))
    assert dm.power_time_in_zone_s is None


def test_hr_zone_maps_channel_directly(run_fit_bytes: bytes) -> None:
    activity = parse_fit(run_fit_bytes)  # hr = 120,123,...,147 over 10 samples
    dm = compute_metrics(activity, AthleteInputs(hr_zones=ZoneSpec((130,))))
    # hr < 130 for i=0..3 (band 0), >= 132 for i=4..8 (band 1): four vs five gaps.
    assert dm.hr_time_in_zone_s == (4.0, 5.0)


def test_pace_zone_derives_per_sample_from_speed(run_fit_bytes: bytes) -> None:
    activity = parse_fit(run_fit_bytes)  # speed 3.3 m/s => pace 303.03 s/km
    dm = compute_metrics(activity, AthleteInputs(pace_zones=ZoneSpec((250, 350))))
    # 303.03 lands in band 1 for every gap; nine 1 s gaps.
    assert dm.pace_time_in_zone_s == (0.0, 9.0, 0.0)


def test_pace_zone_excludes_nonpositive_and_missing_speed() -> None:
    # speed 0.0 and None both produce no pace and are excluded from every band.
    samples = _samples((0.0, 1.0, 2.0, 3.0), speed_mps=(5.0, 0.0, None, 5.0))
    activity = _activity(samples, modality=Modality.RUN, sport=Sport.RUN)
    dm = compute_metrics(activity, AthleteInputs(pace_zones=ZoneSpec((100, 300))))
    # Only the first gap (earlier speed 5 => pace 200 => band 1) is attributed.
    assert dm.pace_time_in_zone_s == (0.0, 1.0, 0.0)


def test_pace_zone_none_when_speed_channel_absent() -> None:
    samples = _samples((0.0, 1.0, 2.0, 3.0))  # every channel None
    activity = _activity(samples, modality=Modality.RUN, sport=Sport.RUN)
    dm = compute_metrics(activity, AthleteInputs(pace_zones=ZoneSpec((100, 300))))
    assert dm.pace_time_in_zone_s is None


# --- 3. determinism (Req 13.3) ----------------------------------------------


def test_compute_metrics_is_deterministic(ride_fit_bytes: bytes) -> None:
    activity = parse_fit(ride_fit_bytes)
    athlete = AthleteInputs(
        ftp_watts=250,
        resting_hr_bpm=45,
        max_hr_bpm=185,
        power_zones=ZoneSpec((150, 205)),
        hr_zones=ZoneSpec((135,)),
    )
    assert compute_metrics(activity, athlete) == compute_metrics(activity, athlete)


# --- 4. never raises for missing data (Req 12.1, 12.2) ----------------------


def test_minimal_fixture_computes_without_raising(minimal_fit_bytes: bytes) -> None:
    # Records only, no session, sparse channels: many None fields, no exception.
    activity = parse_fit(minimal_fit_bytes)
    dm = compute_metrics(activity)
    assert isinstance(dm, DerivedMetrics)
    assert dm.normalized_power_w is None
    assert dm.intensity_factor is None
    assert dm.power_tss is None
    assert dm.hr_time_in_zone_s is None
    # Independent metrics still computed: hr = 100,101,102,103 -> mean 101.5.
    assert dm.avg_heart_rate_bpm == 101.5

    # With athlete it also never raises; HR channel + thresholds => TRIMP present.
    dm2 = compute_metrics(
        activity,
        AthleteInputs(ftp_watts=200, resting_hr_bpm=40, max_hr_bpm=180),
    )
    assert isinstance(dm2, DerivedMetrics)
    assert dm2.trimp is not None


def test_empty_samples_activity_never_raises() -> None:
    activity = _activity(_samples(()))
    dm = compute_metrics(
        activity, AthleteInputs(ftp_watts=200, hr_zones=ZoneSpec((100,)))
    )
    assert isinstance(dm, DerivedMetrics)
    assert dm.hr_time_in_zone_s is None
    assert dm.normalized_power_w is None


# --- 5. every field wired to the right function (rich fixture) --------------


def test_facade_wires_each_field_to_its_function(run_fit_bytes: bytes) -> None:
    activity = parse_fit(run_fit_bytes)
    athlete = AthleteInputs(
        resting_hr_bpm=45,
        max_hr_bpm=185,
        hr_zones=ZoneSpec((130,)),
        pace_zones=ZoneSpec((250, 350)),
    )
    dm = compute_metrics(activity, athlete)
    np_w = power.normalized_power(activity.samples)

    assert dm.moving_time_s == aggregates.moving_time_s(activity)
    assert dm.elapsed_time_s == aggregates.elapsed_time_s(activity)
    assert dm.distance_m == aggregates.distance_m(activity)
    assert dm.avg_speed_mps == aggregates.avg_speed_mps(activity)
    assert dm.max_speed_mps == aggregates.max_speed_mps(activity)
    assert dm.avg_pace_s_per_km == aggregates.avg_pace_s_per_km(activity)
    assert dm.avg_heart_rate_bpm == aggregates.avg_heart_rate_bpm(activity)
    assert dm.max_heart_rate_bpm == aggregates.max_heart_rate_bpm(activity)
    assert dm.avg_cadence_rpm == aggregates.avg_cadence_rpm(activity)
    assert dm.max_cadence_rpm == aggregates.max_cadence_rpm(activity)
    assert dm.normalized_power_w == np_w
    assert dm.variability_index == power.variability_index(np_w, dm.avg_power_w)
    assert dm.efficiency_factor == power.efficiency_factor(activity, np_w)
    assert dm.decoupling_pct == power.decoupling_pct(activity)
    assert dm.elevation_gain_m == aggregates.elevation_gain_m(activity)
    assert dm.elevation_loss_m == aggregates.elevation_loss_m(activity)
    assert dm.min_altitude_m == aggregates.min_altitude_m(activity)
    assert dm.max_altitude_m == aggregates.max_altitude_m(activity)
    assert dm.min_temperature_c == aggregates.min_temperature_c(activity)
    assert dm.max_temperature_c == aggregates.max_temperature_c(activity)
    assert dm.avg_temperature_c == aggregates.avg_temperature_c(activity)
    assert dm.calories_kcal == aggregates.calories_kcal(activity)
    default_pair = sources.weighting_for(None)
    expected_trimp = stress.trimp(activity.samples, 45, 185, default_pair)
    assert expected_trimp is not None
    assert dm.trimp == expected_trimp.value
    assert dm.trimp_weighting == expected_trimp.weighting
    assert dm.hr_time_in_zone_s == zones.time_in_zone(
        activity.samples.heart_rate_bpm, activity.samples.time_s, ZoneSpec((130,))
    )
    # The run fixture has no power, so every power-derived field is None.
    assert dm.normalized_power_w is None
    assert dm.intensity_factor is None
    assert dm.power_tss is None
