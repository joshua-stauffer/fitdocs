"""Tests for the per-sample channel extractor (Req 3.1-3.6).

These exercise :func:`fitdocs.ingest.records.extract_samples` directly on
hand-built ``record_mesgs`` dicts (the extractor works on plain decoded dicts, so
no binary fixtures are needed for the unit cases) plus one integration-style
check that decodes the ride fixture. Coverage:

* parallel arrays stay equal-length and index-aligned, with ``None`` exactly at
  the gaps (Req 3.1, 3.2);
* the *enhanced* speed/altitude variant wins when present/non-None, else the
  basic variant is used per-sample (Req 3.3);
* semicircle positions convert to decimal degrees, and absent positions stay
  ``None`` (Req 3.4);
* already-scaled speed/distance/altitude/temperature pass through in their model
  units unchanged (Req 3.5);
* raw values are preserved verbatim -- no smoothing/resampling (Req 3.6);
* records lacking a ``timestamp`` are the only record-level exclusion;
* ``time_s`` offsets honour an explicit anchor, else anchor to the first record.
"""

from __future__ import annotations

import pytest

from fitdocs.ingest.records import extract_samples
from fitdocs.model import Samples, fit_datetime
from tests.fixtures.builder import decode_messages, to_semicircles

# A fixed FIT-epoch second used as t0 (never wall-clock time).
TS0 = 1_000_000_000


def _all_channels(samples: Samples) -> tuple[tuple[object, ...], ...]:
    """Every one of the 10 parallel channel arrays, for length-invariant checks."""
    return (
        samples.time_s,
        samples.heart_rate_bpm,
        samples.power_w,
        samples.cadence_rpm,
        samples.speed_mps,
        samples.distance_m,
        samples.altitude_m,
        samples.latitude_deg,
        samples.longitude_deg,
        samples.temperature_c,
    )


def _assert_all_equal_length(samples: Samples, expected: int) -> None:
    """Invariant: all 10 channel arrays share exactly ``expected`` entries."""
    for array in _all_channels(samples):
        assert len(array) == expected


def test_channel_arrays_align_with_none_holes() -> None:
    """A middle record omitting heart_rate/power yields aligned ``None`` holes.

    All 10 arrays stay length 3; the gap sits at index 1 while its neighbours
    keep their values (Req 3.1, 3.2).
    """
    records = [
        {
            "timestamp": TS0 + 0,
            "heart_rate": 120,
            "power": 200,
            "cadence": 85,
            "enhanced_speed": 3.0,
            "distance": 0.0,
            "enhanced_altitude": 100.0,
            "temperature": 20,
        },
        # index 1 deliberately omits heart_rate and power.
        {
            "timestamp": TS0 + 1,
            "cadence": 86,
            "enhanced_speed": 3.1,
            "distance": 3.1,
            "enhanced_altitude": 101.0,
            "temperature": 20,
        },
        {
            "timestamp": TS0 + 2,
            "heart_rate": 124,
            "power": 205,
            "cadence": 87,
            "enhanced_speed": 3.2,
            "distance": 6.3,
            "enhanced_altitude": 102.0,
            "temperature": 21,
        },
    ]

    samples, timestamps = extract_samples(records, None)

    _assert_all_equal_length(samples, 3)
    assert len(timestamps) == 3
    # The gap is None at index 1 only; neighbours are untouched (Req 3.2).
    assert samples.heart_rate_bpm == (120, None, 124)
    assert samples.power_w == (200, None, 205)
    # Channels present on the middle record are still populated there.
    assert samples.cadence_rpm == (85, 86, 87)


def test_enhanced_speed_altitude_preferred_when_both_present() -> None:
    """Both variants present -> the enhanced value wins (Req 3.3)."""
    records = [
        {
            "timestamp": TS0,
            "enhanced_speed": 5.5,
            "speed": 5.0,
            "enhanced_altitude": 250.0,
            "altitude": 240.0,
        }
    ]

    samples, _ = extract_samples(records, None)

    assert samples.speed_mps == (5.5,)
    assert samples.altitude_m == (250.0,)


def test_basic_speed_altitude_used_when_enhanced_absent() -> None:
    """Only the basic keys present (no enhanced keys) -> basic values used (Req 3.3).

    ``expand_components=True`` synthesizes enhanced variants in decoded fixtures,
    so this fallback path is exercised with a hand-built basic-only record.
    """
    records = [{"timestamp": TS0, "speed": 5.0, "altitude": 240.0}]

    samples, _ = extract_samples(records, None)

    assert samples.speed_mps == (5.0,)
    assert samples.altitude_m == (240.0,)


def test_enhanced_none_falls_back_to_basic_per_sample() -> None:
    """A present-but-None enhanced key falls back to the basic variant (Req 3.3)."""
    records = [
        {
            "timestamp": TS0,
            "enhanced_speed": None,
            "speed": 4.2,
            "enhanced_altitude": None,
            "altitude": 300.0,
        }
    ]

    samples, _ = extract_samples(records, None)

    assert samples.speed_mps == (4.2,)
    assert samples.altitude_m == (300.0,)


def test_component_expanded_enhanced_channel_falls_back_to_basic() -> None:
    """A list-valued ``enhanced_*`` channel falls back to the basic scalar (Req 3.3).

    Regression guard for the FIT component-expansion shape (``expand_components=True``
    can decode an ``enhanced_*`` field as a redundant array) that crashed lap
    extraction on real files. A per-sample list value must not reach the numeric
    channel coercer; the basic scalar is used instead.
    """
    records = [
        {
            "timestamp": TS0,
            "enhanced_speed": [4.2, 4.2],
            "speed": 4.2,
            "enhanced_altitude": [300.0, 300.0],
            "altitude": 300.0,
        }
    ]

    samples, _ = extract_samples(records, None)

    assert samples.speed_mps == (4.2,)
    assert samples.altitude_m == (300.0,)


def test_semicircle_position_converts_to_expected_degrees() -> None:
    """A known semicircle latitude converts to its decimal degrees (Req 3.4)."""
    # 477218588 semicircles == round(40.0 * 2**31 / 180); it maps back to ~40 deg.
    samples, _ = extract_samples([{"timestamp": TS0, "position_lat": 477218588}], None)

    assert samples.latitude_deg[0] == pytest.approx(40.0, abs=1e-6)


def test_semicircle_roundtrip_and_absent_position_is_none() -> None:
    """Round-trip lat/long convert back within tolerance; absent positions None."""
    records = [
        {
            "timestamp": TS0,
            "position_lat": to_semicircles(40.0),
            "position_long": to_semicircles(-105.0),
        },
        {"timestamp": TS0 + 1},  # no position at all -> lat/long None (Req 3.4/3.2)
    ]

    samples, _ = extract_samples(records, None)

    assert samples.latitude_deg[0] == pytest.approx(40.0, abs=1e-6)
    assert samples.longitude_deg[0] == pytest.approx(-105.0, abs=1e-6)
    assert samples.latitude_deg[1] is None
    assert samples.longitude_deg[1] is None


def test_units_pass_through_unchanged() -> None:
    """Already-scaled speed/distance/altitude/temperature are stored as-is (Req 3.5)."""
    records = [
        {
            "timestamp": TS0,
            "enhanced_speed": 4.25,  # m/s
            "distance": 1234.5,  # m
            "enhanced_altitude": 1600.0,  # m
            "temperature": 21,  # deg C
        }
    ]

    samples, _ = extract_samples(records, None)

    assert samples.speed_mps == (4.25,)
    assert samples.distance_m == (1234.5,)
    assert samples.altitude_m == (1600.0,)
    assert samples.temperature_c == (21,)


def test_no_smoothing_raw_values_preserved() -> None:
    """A noisy altitude series is stored verbatim, never averaged (Req 3.6)."""
    altitudes = [100.0, 200.0, 100.0]
    records = [
        {"timestamp": TS0 + i, "enhanced_altitude": alt}
        for i, alt in enumerate(altitudes)
    ]

    samples, _ = extract_samples(records, None)

    assert list(samples.altitude_m) == altitudes


def test_records_without_timestamp_are_dropped() -> None:
    """The only record-level exclusion: records lacking a timestamp are dropped."""
    records = [
        {"timestamp": TS0 + 0, "heart_rate": 100},
        {"heart_rate": 999},  # no timestamp -> dropped, cannot be placed on timeline
        {"timestamp": TS0 + 2, "heart_rate": 102},
    ]

    samples, timestamps = extract_samples(records, None)

    _assert_all_equal_length(samples, 2)
    assert samples.heart_rate_bpm == (100, 102)  # 999 excluded, rest aligned
    assert len(timestamps) == 2
    assert timestamps == (fit_datetime(TS0 + 0), fit_datetime(TS0 + 2))


def test_time_s_uses_explicit_start_anchor() -> None:
    """With an explicit start_time, offsets are measured from that anchor."""
    anchor = fit_datetime(TS0 - 5)  # 5 s before the first retained record
    records = [{"timestamp": TS0 + off} for off in (0, 2, 5)]

    samples, _ = extract_samples(records, anchor)

    assert samples.time_s == (5.0, 7.0, 10.0)
    # Non-decreasing offsets (records are chronological; Req 3.6 forbids reorder).
    assert all(a <= b for a, b in zip(samples.time_s, samples.time_s[1:], strict=False))


def test_time_s_anchors_to_first_record_when_start_none() -> None:
    """start_time=None anchors offsets to the first retained record (starts at 0)."""
    records = [{"timestamp": TS0 + off} for off in (0, 3, 8)]

    samples, timestamps = extract_samples(records, None)

    assert samples.time_s == (0.0, 3.0, 8.0)
    assert timestamps[0] == fit_datetime(TS0)


def test_empty_input_returns_empty_samples() -> None:
    """Empty record list -> empty Samples arrays and empty timestamps tuple."""
    samples, timestamps = extract_samples([], None)

    assert timestamps == ()
    for array in _all_channels(samples):
        assert array == ()


def test_all_untimestamped_returns_empty_samples() -> None:
    """No record carries a timestamp -> empty Samples, empty timestamps."""
    samples, timestamps = extract_samples([{"heart_rate": 5}, {"power": 7}], None)

    assert timestamps == ()
    assert samples.time_s == ()


def test_ride_fixture_records_extract_aligned(ride_fit_bytes: bytes) -> None:
    """Integration-style: decoded ride records extract into aligned channels.

    The ride carries plain speed and power but no GPS/altitude, so those channels
    are populated while position/altitude stay ``None`` -- and every array shares
    one length (Req 3.1, 3.2).
    """
    messages, _ = decode_messages(ride_fit_bytes)
    records = messages["record_mesgs"]

    samples, timestamps = extract_samples(records, None)

    count = len(records)  # every ride record carries a timestamp
    _assert_all_equal_length(samples, count)
    assert len(timestamps) == count
    # Speed and power recorded; altitude and position absent for this fixture.
    assert all(v is not None for v in samples.speed_mps)
    assert all(v is None for v in samples.altitude_m)
    assert all(v is None for v in samples.latitude_deg)
    # Raw alternating power passes through unchanged (Req 3.6).
    assert samples.power_w[0] == 190
    assert samples.power_w[1] == 210
