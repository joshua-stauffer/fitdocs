"""Self-tests for the deterministic synthetic ``.fit`` fixture builder.

These lock the contract task 1.3 promises the rest of the suite (Req 13.2):
every valid fixture encodes to bytes that pass the SDK integrity check and
decode back to the expected message families; the corrupt variants fail the
right check; and every fixture is byte-for-byte reproducible so downstream
golden snapshots are stable.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import pytest
from garmin_fit_sdk import Decoder, Stream

from fitdocs import parse_fit
from tests.fixtures import builder


def _is_fit(data: bytes) -> bool:
    return Decoder(Stream.from_byte_array(data)).is_fit()


def _check_integrity(data: bytes) -> bool:
    return Decoder(Stream.from_byte_array(data)).check_integrity()


def _read(data: bytes) -> tuple[dict[str, list[dict[str, object]]], list[object]]:
    """Reset + read a fresh stream with the flags task 2's wrapper mirrors."""
    stream = Stream.from_byte_array(data)
    decoder = Decoder(stream)
    stream.reset()
    messages, errors = decoder.read(
        apply_scale_and_offset=True,
        expand_components=True,
        convert_datetimes_to_dates=False,
    )
    return messages, list(errors)


# --- valid fixtures ---------------------------------------------------------

_VALID_CASES: list[tuple[Callable[[], bytes], set[str], set[str]]] = [
    (builder.run_fit_bytes, {"record_mesgs", "session_mesgs", "lap_mesgs"}, set()),
    (builder.ride_fit_bytes, {"record_mesgs", "session_mesgs"}, {"set_mesgs"}),
    (
        builder.strength_fit_bytes,
        {"record_mesgs", "session_mesgs", "set_mesgs"},
        {"lap_mesgs"},
    ),
    (builder.minimal_fit_bytes, {"record_mesgs"}, {"session_mesgs", "lap_mesgs"}),
    # --- task 1.6 real-shaped variants ---
    (
        builder.run_native_power_sparse_hr_fit_bytes,
        {"record_mesgs", "session_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
    (
        builder.run_no_gps_fit_bytes,
        {"record_mesgs", "session_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
    (
        builder.ride_no_power_fit_bytes,
        {"record_mesgs", "session_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
    (
        builder.strength_no_sets_fit_bytes,
        {"record_mesgs", "session_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
    (
        builder.session_dev_fields_fit_bytes,
        {"record_mesgs", "session_mesgs", "field_description_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
    (
        builder.reexport_a_fit_bytes,
        {"record_mesgs", "session_mesgs", "field_description_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
    (
        builder.reexport_b_fit_bytes,
        {"record_mesgs", "session_mesgs", "field_description_mesgs"},
        {"set_mesgs", "lap_mesgs"},
    ),
]


@pytest.mark.parametrize(("bytes_fn", "expected", "absent"), _VALID_CASES)
def test_valid_fixture_passes_integrity_and_has_expected_messages(
    bytes_fn: Callable[[], bytes],
    expected: set[str],
    absent: set[str],
) -> None:
    data = bytes_fn()
    assert isinstance(data, bytes)
    assert _is_fit(data) is True
    assert _check_integrity(data) is True

    messages, errors = _read(data)
    assert errors == []
    assert expected <= set(messages), f"missing {expected - set(messages)}"
    assert absent.isdisjoint(messages), f"unexpected {absent & set(messages)}"


def test_run_fixture_has_three_laps_and_gps() -> None:
    messages, _ = _read(builder.run_fit_bytes())
    assert len(messages["lap_mesgs"]) == 3
    first = messages["record_mesgs"][0]
    # Semicircle round-trip is exact: the decoded raw value equals the encoded
    # semicircle, and re-deriving degrees recovers the authored latitude.
    assert first["position_lat"] == builder.to_semicircles(40.0)
    assert abs(first["position_lat"] * (180.0 / 2**31) - 40.0) < 1e-6


def test_ride_fixture_has_power_but_no_gps() -> None:
    record = _read(builder.ride_fit_bytes())[0]["record_mesgs"][0]
    assert record.get("power") is not None
    assert record.get("position_lat") is None


# --- corrupt / degenerate variants ------------------------------------------


def test_non_fit_bytes_is_not_recognized_as_fit() -> None:
    assert _is_fit(builder.non_fit_bytes()) is False


def test_truncated_fit_fails_integrity_though_header_survives() -> None:
    data = builder.truncated_fit_bytes()
    # The 14-byte header survives truncation, so is_fit stays True; the missing
    # tail makes the file CRC / size check fail.
    assert _is_fit(data) is True
    assert _check_integrity(data) is False


def test_bad_message_fixture_decodes_overall_with_message_errors() -> None:
    data = builder.bad_message_fit_bytes()
    # Passes the decode wrapper's gates (is_fit + integrity) so read() runs...
    assert _is_fit(data) is True
    assert _check_integrity(data) is True
    messages, errors = _read(data)
    # ...yet surfaces a non-empty error list while the valid records still decode.
    assert len(errors) >= 1
    assert len(messages.get("record_mesgs", [])) >= 1


# --- strength set contract --------------------------------------------------


def test_strength_sets_include_missing_fields_and_bodyweight_zero() -> None:
    sets = builder.strength_messages()["set_mesgs"]
    weights = [s.get("weight") for s in sets]
    # A recorded bodyweight set keeps its true 0.0 kg (distinct from missing).
    assert 0.0 in weights
    # At least one set deliberately omits both weight and repetitions.
    assert any(s.get("weight") is None and s.get("repetitions") is None for s in sets)
    # category / category_subtype are present so name resolution has inputs,
    # and one subtype is intentionally unresolvable.
    assert any(s.get("category") is not None for s in sets)
    assert any(s.get("category_subtype") == 999 for s in sets)


# --- task 1.6 real-shaped variants (workout-docs Req 4.1) -------------------
#
# Each new builder reproduces one real-data shape the workout-docs layer must
# handle, decoded through the project's own ``parse_fit`` so the asserted shape
# is exactly what the renderers will consume.


def test_native_power_sparse_hr_fixture_has_power_and_hr_holes() -> None:
    """Native power on every sample; heart rate is sparse with real None holes."""
    activity = parse_fit(builder.run_native_power_sparse_hr_fit_bytes())
    hr = activity.samples.heart_rate_bpm
    power = activity.samples.power_w

    assert len(power) > 0
    # Native running power is recorded on every sample (Apple Watch / Stryd).
    assert all(value is not None for value in power)
    # Heart rate has genuine gaps (no interpolation), roughly ~60% coverage.
    assert any(value is None for value in hr)
    assert any(value is not None for value in hr)
    coverage = sum(value is not None for value in hr) / len(hr)
    assert 0.5 <= coverage <= 0.7
    # Distance is present so the hero chart's distance x-axis is available.
    assert all(value is not None for value in activity.samples.distance_m)


def test_no_gps_run_fixture_has_no_position_or_altitude() -> None:
    """Outdoor run with GPS/altitude entirely absent, other channels intact."""
    samples = parse_fit(builder.run_no_gps_fit_bytes()).samples

    assert all(value is None for value in samples.latitude_deg)
    assert all(value is None for value in samples.longitude_deg)
    assert all(value is None for value in samples.altitude_m)
    # Independent channels still record honestly.
    assert any(value is not None for value in samples.heart_rate_bpm)
    assert all(value is not None for value in samples.distance_m)
    assert all(value is not None for value in samples.speed_mps)


def test_ride_no_power_fixture_omits_power_but_keeps_hr_and_speed() -> None:
    """Ride without a power channel: HR + speed drive the hero fallback."""
    activity = parse_fit(builder.ride_no_power_fit_bytes())

    assert activity.modality == "bike"
    assert activity.summary.avg_power_w is None
    assert activity.summary.max_power_w is None
    assert all(value is None for value in activity.samples.power_w)
    assert any(value is not None for value in activity.samples.heart_rate_bpm)
    assert all(value is not None for value in activity.samples.speed_mps)


def test_strength_no_sets_fixture_is_hr_only_with_empty_sets() -> None:
    """Strength session with HR-only records and NO set messages at all."""
    activity = parse_fit(builder.strength_no_sets_fit_bytes())

    assert activity.modality == "strength"
    # No set_mesgs -> empty sets tuple; never a scaffolded empty row (Req 9.6).
    assert activity.sets == ()
    assert any(value is not None for value in activity.samples.heart_rate_bpm)
    # No distance and no power anywhere (records or session).
    assert all(value is None for value in activity.samples.distance_m)
    assert all(value is None for value in activity.samples.power_w)
    assert activity.summary.total_distance_m is None
    assert activity.summary.avg_power_w is None
    assert activity.summary.avg_heart_rate_bpm is not None


_SUPPLEMENTAL_DEV_FIELDS = {
    "WORKOUT RPE ESTIMATED",
    "SESSION WEATHER HUMIDITY",
    "AVG METs",
}


def test_session_developer_fields_fixture_carries_uuid_and_supplementals() -> None:
    """Session dev fields expose a 16-byte SESSION UUID and the supplementals."""
    fields = parse_fit(builder.session_dev_fields_fit_bytes()).developer_fields

    uuid = fields["SESSION UUID"]
    assert isinstance(uuid, tuple)
    assert len(uuid) == 16
    assert all(isinstance(byte, int) for byte in uuid)
    # The recognized supplemental fields ride alongside the UUID.
    assert set(fields) >= _SUPPLEMENTAL_DEV_FIELDS


def test_reexport_pair_shares_session_uuid_but_differs_in_bytes() -> None:
    """A re-export pair: same SESSION UUID (stable identity), different bytes."""
    first = builder.reexport_a_fit_bytes()
    second = builder.reexport_b_fit_bytes()

    # Genuinely different files -- a real re-export changes the bytes/sha256...
    assert hashlib.sha256(first).hexdigest() != hashlib.sha256(second).hexdigest()

    # ...yet both record the identical stable session identity, so downstream
    # dedup converges on one document instead of duplicating (Req 3.6).
    uuid_first = parse_fit(first).developer_fields["SESSION UUID"]
    uuid_second = parse_fit(second).developer_fields["SESSION UUID"]
    assert uuid_first == uuid_second
    assert isinstance(uuid_first, tuple)
    assert len(uuid_first) == 16


# --- determinism (Req 13.2 / workout-docs Req 4.1) --------------------------

_ALL_BUILDERS: list[Callable[[], bytes]] = [
    builder.run_fit_bytes,
    builder.ride_fit_bytes,
    builder.strength_fit_bytes,
    builder.minimal_fit_bytes,
    builder.non_fit_bytes,
    builder.truncated_fit_bytes,
    builder.bad_message_fit_bytes,
    # task 1.6 real-shaped variants -- byte-identical on every rebuild (Req 4.1).
    builder.run_native_power_sparse_hr_fit_bytes,
    builder.run_no_gps_fit_bytes,
    builder.ride_no_power_fit_bytes,
    builder.strength_no_sets_fit_bytes,
    builder.session_dev_fields_fit_bytes,
    builder.reexport_a_fit_bytes,
    builder.reexport_b_fit_bytes,
]


@pytest.mark.parametrize("bytes_fn", _ALL_BUILDERS)
def test_fixture_bytes_are_reproducible(bytes_fn: Callable[[], bytes]) -> None:
    assert bytes_fn() == bytes_fn()


# --- conftest wiring --------------------------------------------------------


def test_conftest_exposes_valid_bytes_fixtures(
    run_fit_bytes: bytes,
    ride_fit_bytes: bytes,
    strength_fit_bytes: bytes,
    minimal_fit_bytes: bytes,
) -> None:
    for data in (run_fit_bytes, ride_fit_bytes, strength_fit_bytes, minimal_fit_bytes):
        assert isinstance(data, bytes)
        assert _is_fit(data) is True


def test_conftest_exposes_real_shaped_variant_fixtures(
    run_native_power_sparse_hr_fit_bytes: bytes,
    run_no_gps_fit_bytes: bytes,
    ride_no_power_fit_bytes: bytes,
    strength_no_sets_fit_bytes: bytes,
    session_dev_fields_fit_bytes: bytes,
    reexport_a_fit_bytes: bytes,
    reexport_b_fit_bytes: bytes,
) -> None:
    for data in (
        run_native_power_sparse_hr_fit_bytes,
        run_no_gps_fit_bytes,
        ride_no_power_fit_bytes,
        strength_no_sets_fit_bytes,
        session_dev_fields_fit_bytes,
        reexport_a_fit_bytes,
        reexport_b_fit_bytes,
    ):
        assert isinstance(data, bytes)
        assert _is_fit(data) is True
