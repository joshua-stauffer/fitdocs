"""Tests for the metric input and result contracts (Req 10.4, 12.1).

These exercise :mod:`fitdocs.metrics.types`, three standalone frozen
dataclasses that form the caller-input and result contracts for every metric
function:

* :class:`ZoneSpec` validates ascending, non-empty dividers and *fails fast*
  (raises :class:`ValueError`) on malformed input, so no silent misbinning can
  fabricate zone data (Req 10.4). ``n`` dividers define ``n + 1`` bands; the
  band-occupancy math itself lives downstream, not here.
* :class:`AthleteInputs` is entirely optional -- every field defaults to
  ``None`` -- because thresholds and zone definitions are caller-supplied and
  may all be absent.
* :class:`DerivedMetrics` carries every derived metric with each field
  independently ``None``-able, so a missing input never fabricates a value
  (Req 12.1).
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs.metrics.types import (
    AthleteInputs,
    DerivedMetrics,
    TrimpWeighting,
    ZoneSpec,
)

# --- ZoneSpec: valid dividers construct (ascending, non-empty) --------------


def test_zonespec_ascending_dividers_construct() -> None:
    spec = ZoneSpec(dividers=(100.0, 150.0, 180.0))
    assert spec.dividers == (100.0, 150.0, 180.0)


def test_zonespec_single_divider_is_valid() -> None:
    # A single divider partitions the line into two bands -- valid.
    spec = ZoneSpec(dividers=(150.0,))
    assert spec.dividers == (150.0,)


def test_zonespec_normalizes_list_to_tuple() -> None:
    # A caller may pass a list; it is normalized to a tuple for hashability.
    spec = ZoneSpec(dividers=[100.0, 150.0, 180.0])  # type: ignore[arg-type]
    assert spec.dividers == (100.0, 150.0, 180.0)
    assert isinstance(spec.dividers, tuple)


# --- ZoneSpec: malformed dividers fail fast (Req 10.4) ----------------------


def test_zonespec_empty_dividers_raise_value_error() -> None:
    with pytest.raises(ValueError):
        ZoneSpec(dividers=())


def test_zonespec_descending_dividers_raise_value_error() -> None:
    with pytest.raises(ValueError):
        ZoneSpec(dividers=(150.0, 100.0))


def test_zonespec_equal_adjacent_dividers_raise_value_error() -> None:
    # Equal adjacent values are *not* strictly ascending -> invalid.
    with pytest.raises(ValueError):
        ZoneSpec(dividers=(100.0, 100.0))


def test_zonespec_partially_non_ascending_raises() -> None:
    with pytest.raises(ValueError):
        ZoneSpec(dividers=(100.0, 150.0, 120.0))


# --- ZoneSpec: frozen -------------------------------------------------------


def test_zonespec_is_frozen() -> None:
    spec = ZoneSpec(dividers=(100.0, 150.0))
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        spec.dividers = (1.0,)  # type: ignore[misc]


# --- ZoneSpec: n dividers -> n + 1 bands (documented contract) --------------


@pytest.mark.parametrize(
    ("dividers", "expected_bands"),
    [
        ((150.0,), 2),
        ((100.0, 150.0), 3),
        ((100.0, 150.0, 180.0), 4),
    ],
)
def test_zonespec_band_count_contract(
    dividers: tuple[float, ...], expected_bands: int
) -> None:
    # Occupancy is computed downstream; here we only pin the band-count
    # contract: n dividers conceptually imply n + 1 bands.
    spec = ZoneSpec(dividers=dividers)
    assert len(spec.dividers) + 1 == expected_bands


# --- AthleteInputs: all optional, individually settable, frozen -------------


def test_athlete_inputs_all_optional_default_none() -> None:
    inputs = AthleteInputs()
    assert inputs.ftp_watts is None
    assert inputs.resting_hr_bpm is None
    assert inputs.max_hr_bpm is None
    assert inputs.hr_zones is None
    assert inputs.power_zones is None
    assert inputs.pace_zones is None
    assert inputs.trimp_weighting is None


def test_athlete_inputs_fields_set_individually() -> None:
    inputs = AthleteInputs(
        ftp_watts=250.0,
        resting_hr_bpm=45,
        max_hr_bpm=190,
        hr_zones=ZoneSpec(dividers=(120.0, 150.0, 170.0)),
        trimp_weighting=TrimpWeighting.BANISTER_FEMALE,
    )
    assert inputs.ftp_watts == 250.0
    assert inputs.resting_hr_bpm == 45
    assert inputs.max_hr_bpm == 190
    assert inputs.hr_zones == ZoneSpec(dividers=(120.0, 150.0, 170.0))
    assert inputs.trimp_weighting == TrimpWeighting.BANISTER_FEMALE
    # Unset zone fields stay None.
    assert inputs.power_zones is None
    assert inputs.pace_zones is None


def test_athlete_inputs_is_frozen() -> None:
    inputs = AthleteInputs()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        inputs.ftp_watts = 300.0  # type: ignore[misc]


def test_athlete_inputs_field_contract() -> None:
    # Exact field names, order, and (string) annotations per the design
    # (Amendment 1 appends trimp_weighting, Req 17.2, 17.3).
    expected = [
        ("ftp_watts", "float | None"),
        ("resting_hr_bpm", "int | None"),
        ("max_hr_bpm", "int | None"),
        ("hr_zones", "ZoneSpec | None"),
        ("power_zones", "ZoneSpec | None"),
        ("pace_zones", "ZoneSpec | None"),
        ("trimp_weighting", "TrimpWeighting | None"),
    ]
    actual = [(f.name, f.type) for f in dataclasses.fields(AthleteInputs)]
    assert actual == expected
    assert len(actual) == 7


# --- DerivedMetrics: constructs all-None, exact field contract, frozen ------

# Exact field names, order, and (string) annotations per the design's 31-field
# DerivedMetrics contract (Amendment 1 inserts trimp_weighting immediately
# after trimp, Req 17.6). Every scalar is ``float | None`` except
# ``calories_kcal`` (``int | None``) and ``trimp_weighting``
# (``TrimpWeighting | None``); the three time-in-zone fields are
# ``tuple[float, ...] | None``.
_DERIVED_FIELDS = [
    ("moving_time_s", "float | None"),
    ("elapsed_time_s", "float | None"),
    ("distance_m", "float | None"),
    ("avg_speed_mps", "float | None"),
    ("max_speed_mps", "float | None"),
    ("avg_pace_s_per_km", "float | None"),
    ("avg_heart_rate_bpm", "float | None"),
    ("max_heart_rate_bpm", "float | None"),
    ("avg_power_w", "float | None"),
    ("max_power_w", "float | None"),
    ("avg_cadence_rpm", "float | None"),
    ("max_cadence_rpm", "float | None"),
    ("normalized_power_w", "float | None"),
    ("intensity_factor", "float | None"),
    ("variability_index", "float | None"),
    ("efficiency_factor", "float | None"),
    ("decoupling_pct", "float | None"),
    ("elevation_gain_m", "float | None"),
    ("elevation_loss_m", "float | None"),
    ("min_altitude_m", "float | None"),
    ("max_altitude_m", "float | None"),
    ("min_temperature_c", "float | None"),
    ("max_temperature_c", "float | None"),
    ("avg_temperature_c", "float | None"),
    ("hr_time_in_zone_s", "tuple[float, ...] | None"),
    ("power_time_in_zone_s", "tuple[float, ...] | None"),
    ("pace_time_in_zone_s", "tuple[float, ...] | None"),
    ("trimp", "float | None"),
    ("trimp_weighting", "TrimpWeighting | None"),
    ("power_tss", "float | None"),
    ("calories_kcal", "int | None"),
]


def test_derived_metrics_has_thirty_one_fields() -> None:
    assert len(dataclasses.fields(DerivedMetrics)) == 31
    assert len(_DERIVED_FIELDS) == 31


def test_derived_metrics_field_contract() -> None:
    actual = [(f.name, f.type) for f in dataclasses.fields(DerivedMetrics)]
    assert actual == _DERIVED_FIELDS


def test_derived_metrics_constructs_all_none() -> None:
    # Every field independently None-able (Req 12.1): the empty constructor
    # yields an all-None instance -- no fabricated zeros or defaults.
    metrics = DerivedMetrics()
    for f in dataclasses.fields(DerivedMetrics):
        assert getattr(metrics, f.name) is None


def test_derived_metrics_fields_settable_and_independent() -> None:
    # Independent None-ability: some fields carry values, others stay None.
    metrics = DerivedMetrics(
        moving_time_s=1800.0,
        distance_m=10000.0,
        calories_kcal=650,
        hr_time_in_zone_s=(60.0, 120.0, 30.0),
        trimp=95.5,
        trimp_weighting=TrimpWeighting.BANISTER_MALE,
    )
    assert metrics.moving_time_s == 1800.0
    assert metrics.distance_m == 10000.0
    assert metrics.calories_kcal == 650
    assert metrics.hr_time_in_zone_s == (60.0, 120.0, 30.0)
    assert metrics.trimp == 95.5
    assert metrics.trimp_weighting == TrimpWeighting.BANISTER_MALE
    # Untouched fields remain None, never fabricated (Req 12.1).
    assert metrics.avg_power_w is None
    assert metrics.power_time_in_zone_s is None


def test_derived_metrics_is_frozen() -> None:
    metrics = DerivedMetrics()
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        metrics.moving_time_s = 1.0  # type: ignore[misc]


# --- TrimpWeighting: enum shape (Req 17.2, 17.3, 17.6) -----------------------
#
# The member *names* are an open maintainer decision (see spec.json's
# open-decisions record and
# .kiro/queue/2026-07-27-trimp-weighting-default-is-sex-named.md); assertions
# here pin the enum's *shape* (member count, distinct string values, StrEnum
# membership) rather than on behavior keyed to a specific member name; a
# rename is a mechanical update to the member references in this file, not a
# redesign of these assertions.


def test_trimp_weighting_has_two_members() -> None:
    assert len(TrimpWeighting) == 2


def test_trimp_weighting_members_have_distinct_string_values() -> None:
    # Direct attribute access (not iteration) so an aliasing mutation -- a
    # second member assigned the first member's string value, which Python's
    # Enum silently collapses into an alias rather than a distinct member --
    # is still caught: iterating ``TrimpWeighting`` would skip the alias and
    # leave this assertion vacuously true.
    assert TrimpWeighting.BANISTER_MALE.value != TrimpWeighting.BANISTER_FEMALE.value
    assert isinstance(TrimpWeighting.BANISTER_MALE.value, str)
    assert isinstance(TrimpWeighting.BANISTER_FEMALE.value, str)


def test_trimp_weighting_is_str_enum() -> None:
    # StrEnum membership matters: the value threads through equality/JSON as a
    # plain string wherever the caller-input/result contracts serialize it.
    for member in TrimpWeighting:
        assert isinstance(member, str)
