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


# --- running-dynamics fixture families (spec running-dynamics, task 1.2) ------
#
# Each test below asserts the raw wire shape is present BEFORE any fitdocs code
# sees it: later tasks' assertions rely on these preconditions.

_Messages = dict[str, list[dict[str, object]]]

_STRYD_NAMES = (
    "Air Power",
    "Form Power",
    "Leg Spring Stiffness",
    "Impact",
    "Leg Spring Stiffness Balance",
    "Impact Loading Rate Balance",
    "Vertical Oscillation Balance",
    "Speed",
    "Distance",
    "Stryd Temperature",
    "Stryd Humidity",
    "Run Profile",
)
_STRYD_DEFINITIONS = (11, 2, 1, 4, 3, 6, 5, 8, 9, 10, 12, 0)
_STRYD_KEYS = {name: pos for pos, name in enumerate(_STRYD_NAMES)}


def _num(value: object) -> float:
    assert isinstance(value, (int, float)) and not isinstance(value, bool), value
    return float(value)


def _decode(data: bytes) -> _Messages:
    messages, errors = builder.decode_messages(data)
    assert errors == []
    return messages


def _dev(record: dict[str, object]) -> dict[int, object]:
    fields = record.get("developer_fields", {})
    assert isinstance(fields, dict)
    return fields


def _dev_of(record: dict[str, object], name: str) -> object:
    return _dev(record)[_STRYD_KEYS[name]]


def _stryd() -> _Messages:
    return _decode(builder.stryd_run_fit_bytes())


def _native() -> _Messages:
    return _decode(builder.run_native_dynamics_fit_bytes())


def _device_zero(messages: _Messages) -> list[dict[str, object]]:
    """The ``device_info`` entries at device index 0 (decoded as ``creator``)."""
    return [m for m in messages["device_info_mesgs"] if m["device_index"] == "creator"]


def _placeholder_indices(records: list[dict[str, object]]) -> list[int]:
    return [i for i, r in enumerate(records) if r["heart_rate"] == 0]


def test_stryd_descriptions_are_the_twelve_in_order_with_swapped_definitions() -> None:
    descriptions = _stryd()["field_description_mesgs"]
    assert [d["field_name"] for d in descriptions] == list(_STRYD_NAMES)
    assert [d["field_definition_number"] for d in descriptions] == list(
        _STRYD_DEFINITIONS
    )
    for description in descriptions:
        assert description["key"] != description["field_definition_number"], description
    air = descriptions[0]
    assert (air["key"], air["field_name"], air["field_definition_number"]) == (
        0,
        "Air Power",
        11,
    )


def test_stryd_native_message_slots_are_on_speed_distance_and_temperature_only() -> (
    None
):
    descriptions = _stryd()["field_description_mesgs"]
    slots = {
        d["field_name"]: d["native_mesg_num"]
        for d in descriptions
        if "native_mesg_num" in d
    }
    assert slots == {"Speed": 6, "Distance": 5, "Stryd Temperature": 13}


def test_stryd_writer_is_stryd_in_file_id_and_device_index_zero() -> None:
    messages = _stryd()
    assert [m["manufacturer"] for m in messages["file_id_mesgs"]] == ["stryd"]
    device_zero = _device_zero(messages)
    assert [m["manufacturer"] for m in device_zero] == ["stryd"]
    assert len(messages["developer_data_id_mesgs"]) == 1


def test_stryd_records_carry_the_placeholder_zeros_and_pause() -> None:
    records = _stryd()["record_mesgs"]
    assert len(records) >= 40
    zeros = _placeholder_indices(records)
    assert len(zeros) == 4
    assert zeros[0] == 0
    assert zeros[1:] == [zeros[1], zeros[1] + 1, zeros[1] + 2]
    native_dynamics = (
        "power",
        "cadence",
        "enhanced_speed",
        "step_length",
        "vertical_oscillation",
        "stance_time",
        "stance_time_balance",
    )
    for i in zeros:
        for field in native_dynamics:
            assert records[i][field] == 0, (i, field)
        for name in _STRYD_NAMES[:7] + ("Speed",):
            assert _dev_of(records[i], name) == 0, (i, name)
    pause = zeros[1:]
    held = records[pause[0] - 1]["distance"]
    assert _num(held) > 0
    assert [records[i]["distance"] for i in pause] == [held] * 3
    assert _num(records[pause[-1] + 1]["distance"]) > _num(held)
    running = [r for i, r in enumerate(records) if i not in zeros]
    for field in native_dynamics:
        assert all(_num(r[field]) > 0 for r in running), field


def test_stryd_records_carry_all_eleven_record_developer_fields() -> None:
    records = _stryd()["record_mesgs"]
    for record in records:
        assert sorted(_dev(record)) == list(range(11))


def test_stryd_native_channels_present_and_absent_as_designed() -> None:
    records = _stryd()["record_mesgs"]
    for record in records:
        for field in (
            "position_lat",
            "position_long",
            "distance",
            "enhanced_speed",
            "enhanced_altitude",
            "power",
            "heart_rate",
            "cadence",
            "step_length",
            "vertical_oscillation",
            "stance_time",
            "stance_time_balance",
        ):
            assert field in record, field
        for field in ("vertical_ratio", "temperature"):
            assert field not in record, field


def test_stryd_sentinel_zero_gate_and_air_power_records() -> None:
    records = _stryd()["record_mesgs"]
    zeros = _placeholder_indices(records)
    running = [i for i in range(len(records)) if i not in zeros]
    sentinel = [i for i in running if _dev_of(records[i], "Form Power") == 65535]
    assert len(sentinel) == 1
    assert _num(_dev_of(records[sentinel[0]], "Air Power")) > 0
    zero_balance = [
        i for i in running if _dev_of(records[i], "Vertical Oscillation Balance") == 0.0
    ]
    assert len(zero_balance) == 1
    assert _num(records[zero_balance[0]]["vertical_oscillation"]) > 0
    zero_air = [i for i in running if _dev_of(records[i], "Air Power") == 0]
    assert len(zero_air) == 1
    form = _dev_of(records[zero_air[0]], "Form Power")
    assert form != 65535 and _num(form) > 0


def test_stryd_float32_developer_fields_are_not_two_decimal_on_running_records() -> (
    None
):
    records = _stryd()["record_mesgs"]
    zeros = _placeholder_indices(records)
    zero_balance = [
        i
        for i, r in enumerate(records)
        if i not in zeros and _dev_of(r, "Vertical Oscillation Balance") == 0.0
    ]
    assert len(zero_balance) == 1  # the one intended exact value, exempted below
    float32_names = [
        d["field_name"]
        for d in _stryd()["field_description_mesgs"]
        if d["fit_base_type_id"] == builder.BASE_TYPE["FLOAT32"]
    ]
    assert len(float32_names) == 7
    checked = 0
    for name in float32_names:
        for i, record in enumerate(records):
            if i in zeros or (
                i in zero_balance and name == "Vertical Oscillation Balance"
            ):
                continue
            value = _num(_dev_of(record, str(name)))
            assert round(value, 2) != value, (name, i, value)
            assert abs(round(value, 2) - value) < 1e-5, (name, i, value)
            checked += 1
    assert checked == 7 * (len(records) - len(zeros)) - 1


def test_stryd_stride_channels_vary_and_humidity_reaches_104() -> None:
    records = _stryd()["record_mesgs"]
    zeros = _placeholder_indices(records)
    running = [r for i, r in enumerate(records) if i not in zeros]
    for name in _STRYD_NAMES[:7]:
        assert len({_dev_of(r, name) for r in running}) >= 4, name
    for field in ("vertical_oscillation", "stance_time", "step_length"):
        assert len({r[field] for r in running}) >= 4, field
    humidity = [_num(_dev_of(r, "Stryd Humidity")) for r in records]
    assert max(humidity) == 104
    assert humidity.count(104) == 1


def test_stryd_developer_speed_and_distance_diverge_from_native() -> None:
    records = _stryd()["record_mesgs"]
    zeros = _placeholder_indices(records)
    for i, record in enumerate(records):
        if i in zeros:
            continue
        assert (
            abs(_num(_dev_of(record, "Speed")) - _num(record["enhanced_speed"])) > 0.1
        )
        assert abs(_num(_dev_of(record, "Distance")) - _num(record["distance"])) > 0.1


def test_stryd_laps_and_session_quirks() -> None:
    messages = _stryd()
    laps = messages["lap_mesgs"]
    assert len(laps) == 4
    for lap in laps:
        for field in ("avg_heart_rate", "max_heart_rate", "avg_cadence"):
            assert field not in lap, field
    session = messages["session_mesgs"][0]
    assert session["num_laps"] == 1
    assert session["timestamp"] == laps[-1]["start_time"]
    assert session["timestamp"] != laps[-1]["timestamp"]
    for field in ("avg_heart_rate", "max_heart_rate"):
        assert field not in session, field
    assert _num(session["total_elapsed_time"]) > 0
    assert _num(session["total_timer_time"]) > 0
    assert session["sport"] == "running"
    assert sorted(_dev(session)) == [_STRYD_KEYS["Run Profile"]]
    assert isinstance(_dev(session)[_STRYD_KEYS["Run Profile"]], str)


def test_stryd_manufacturer_variant_differs_only_in_the_two_writer_messages() -> None:
    default = _stryd()
    variant = _decode(builder.stryd_run_fit_bytes(manufacturer="garmin"))
    assert default.keys() == variant.keys()
    for name in default:
        if name in ("file_id_mesgs", "device_info_mesgs"):
            continue
        assert default[name] == variant[name], name
    for name in ("file_id_mesgs", "device_info_mesgs"):
        assert default[name] != variant[name], name
        for a, b in zip(default[name], variant[name], strict=True):
            assert a["manufacturer"] == "stryd"
            assert b["manufacturer"] == "garmin"
            assert a["product"] == b["product"]
            # The decoder derives ``garmin_product`` from a ``garmin``
            # manufacturer's raw product number; nothing else may differ.
            assert "garmin_product" not in a
            rest_a = {k: v for k, v in a.items() if k != "manufacturer"}
            rest_b = {
                k: v
                for k, v in b.items()
                if k not in ("manufacturer", "garmin_product")
            }
            assert rest_a == rest_b


def test_native_dynamics_records_carry_native_dynamics_only() -> None:
    messages = _native()
    records = messages["record_mesgs"]
    assert len(records) >= 10
    for record in records:
        for field in ("vertical_oscillation", "stance_time", "vertical_ratio"):
            assert _num(record[field]) > 0, field
        for field in ("stance_time_balance", "step_length", "developer_fields"):
            assert field not in record, field
        for field in ("heart_rate", "distance", "position_lat", "position_long"):
            assert field in record, field
        assert "enhanced_speed" in record or "speed" in record


def test_native_dynamics_session_uuid_contains_255() -> None:
    messages = _native()
    names = [d["field_name"] for d in messages["field_description_mesgs"]]
    assert names == [spec[0] for spec in builder._SESSION_DEV_FIELD_SPECS]
    session = messages["session_mesgs"][0]
    by_key = {d["key"]: d["field_name"] for d in messages["field_description_mesgs"]}
    values = {by_key[k]: v for k, v in _dev(session).items()}
    uuid = values["SESSION UUID"]
    assert isinstance(uuid, list) and len(uuid) == 16
    assert 255 in uuid
    assert uuid != list(builder._SESSION_UUID_BYTES)
    assert values["AVG METs"] == builder._SESSION_DEV_FIELD_VALUES["AVG METs"]


def test_native_dynamics_keeps_the_garmin_writer_defaults() -> None:
    messages = _native()
    assert [m["manufacturer"] for m in messages["file_id_mesgs"]] == ["garmin"]
    assert [m["manufacturer"] for m in messages["device_info_mesgs"]] == ["garmin"]


def test_existing_session_uuid_constants_are_untouched() -> None:
    assert tuple(range(100, 116)) == builder._SESSION_UUID_BYTES


@pytest.mark.parametrize(
    "bytes_fn",
    [builder.stryd_run_fit_bytes, builder.run_native_dynamics_fit_bytes],
)
def test_dynamics_fixture_bytes_are_reproducible(
    bytes_fn: Callable[[], bytes],
) -> None:
    first = bytes_fn()
    assert first == bytes_fn()
    assert _is_fit(first) is True
    assert _check_integrity(first) is True


# --- developer_field_run_fit_bytes ------------------------------------------

_HELPER_DESCRIPTIONS = (
    builder.DevFieldSpec("Alpha", builder.BASE_TYPE["UINT16"], 7, units="W"),
    builder.DevFieldSpec(
        "Beta", builder.BASE_TYPE["FLOAT32"], 3, scale=None, native_mesg_num=6
    ),
    builder.DevFieldSpec("Gamma", builder.BASE_TYPE["UINT8"], 0, array=4),
    builder.DevFieldSpec("Delta", builder.BASE_TYPE["UINT16"], 1, scale=100, offset=5),
)
_HELPER_RECORDS = (
    ({"heart_rate": 120}, {0: 11, 1: 2.5}),
    ({"heart_rate": 121}, {0: 12}),
    ({"heart_rate": 122, "timestamp": builder.FIT_TIMESTAMP_BASE + 40}, {}),
)


def _helper(**kwargs: object) -> _Messages:
    args: dict[str, object] = {
        "descriptions": _HELPER_DESCRIPTIONS,
        "records": _HELPER_RECORDS,
    }
    args.update(kwargs)
    return _decode(builder.developer_field_run_fit_bytes(**args))  # type: ignore[arg-type]


def test_helper_writes_each_description_at_its_key_and_definition_number() -> None:
    descriptions = _helper()["field_description_mesgs"]
    assert [d["field_name"] for d in descriptions] == [
        "Alpha",
        "Beta",
        "Gamma",
        "Delta",
    ]
    assert [d["key"] for d in descriptions] == [0, 1, 2, 3]
    assert [d["field_definition_number"] for d in descriptions] == [7, 3, 0, 1]
    assert descriptions[0]["units"] == "W"
    assert descriptions[1]["native_mesg_num"] == 6
    assert descriptions[2]["array"] == 4
    assert (descriptions[3]["scale"], descriptions[3]["offset"]) == (100, 5)
    for optional in ("scale", "offset", "native_mesg_num", "array"):
        assert optional not in descriptions[0], optional


def test_helper_records_carry_only_the_positions_given() -> None:
    records = _helper()["record_mesgs"]
    assert [sorted(_dev(r)) for r in records] == [[0, 1], [0], []]
    assert _dev(records[0])[0] == 11
    assert _dev(records[0])[1] == 2.5
    assert [r["heart_rate"] for r in records] == [120, 121, 122]
    assert records[0]["timestamp"] == builder.FIT_TIMESTAMP_BASE
    assert records[1]["timestamp"] == builder.FIT_TIMESTAMP_BASE + 1
    assert records[2]["timestamp"] == builder.FIT_TIMESTAMP_BASE + 40


def test_helper_session_spans_the_records_with_no_lap_message() -> None:
    messages = _helper()
    assert "lap_mesgs" not in messages
    assert [(m["sport"], m["sub_sport"]) for m in messages["sport_mesgs"]] == [
        ("running", "generic")
    ]
    session = messages["session_mesgs"][0]
    assert session["sport"] == "running"
    assert session["start_time"] == builder.FIT_TIMESTAMP_BASE
    assert session["timestamp"] == builder.FIT_TIMESTAMP_BASE + 40
    assert session["total_elapsed_time"] == 40.0
    assert session["total_timer_time"] == 40.0
    assert len(messages["activity_mesgs"]) == 1


def test_helper_session_carries_no_developer_field_without_session_fields() -> None:
    session = _helper()["session_mesgs"][0]
    assert "developer_fields" not in session


def test_helper_session_fields_land_on_the_session_under_their_keys() -> None:
    messages = _helper(session_fields={2: [9, 8, 7, 255], 3: 4})
    session = messages["session_mesgs"][0]
    assert _dev(session) == {2: [9, 8, 7, 255], 3: 4}
    assert "developer_fields" in messages["record_mesgs"][0]


def test_helper_device_manufacturer_alone_changes_device_index_zero_only() -> None:
    messages = _helper(device_manufacturer="stryd")
    assert [m["manufacturer"] for m in messages["file_id_mesgs"]] == ["garmin"]
    zero = _device_zero(messages)
    assert [m["manufacturer"] for m in zero] == ["stryd"]


def test_helper_manufacturer_alone_is_followed_by_the_recording_device() -> None:
    messages = _helper(manufacturer="stryd")
    assert [m["manufacturer"] for m in messages["file_id_mesgs"]] == ["stryd"]
    zero = _device_zero(messages)
    assert [m["manufacturer"] for m in zero] == ["stryd"]


def test_helper_all_defaults_record_garmin_in_both() -> None:
    messages = _helper()
    assert [m["manufacturer"] for m in messages["file_id_mesgs"]] == ["garmin"]
    zero = _device_zero(messages)
    assert [m["manufacturer"] for m in zero] == ["garmin"]


def test_helper_explicit_device_manufacturer_beats_manufacturer() -> None:
    messages = _helper(manufacturer="stryd", device_manufacturer="garmin")
    assert [m["manufacturer"] for m in messages["file_id_mesgs"]] == ["stryd"]
    zero = _device_zero(messages)
    assert [m["manufacturer"] for m in zero] == ["garmin"]


def test_helper_serial_product_and_time_created_reach_file_id() -> None:
    messages = _helper(serial=4242, product=77, time_created=1_000_000_500)
    file_id = messages["file_id_mesgs"][0]
    assert file_id["serial_number"] == 4242
    assert file_id["product"] == 77
    assert file_id["time_created"] == 1_000_000_500
    zero = _device_zero(messages)
    assert zero[0]["serial_number"] == 4242
    default = _helper()["file_id_mesgs"][0]
    assert default["serial_number"] == builder._DEV_FIELD_RUN_SERIAL
    assert (default["product"], default["time_created"]) == (
        1,
        builder.FIT_TIMESTAMP_BASE,
    )


def test_helper_writes_one_developer_data_id_per_distinct_index() -> None:
    specs = (
        builder.DevFieldSpec("One", builder.BASE_TYPE["UINT8"], 0),
        builder.DevFieldSpec(
            "Two", builder.BASE_TYPE["UINT8"], 0, developer_data_index=1
        ),
        builder.DevFieldSpec("Three", builder.BASE_TYPE["UINT8"], 1),
    )
    messages = _helper(descriptions=specs, records=(({}, {0: 1, 1: 2, 2: 3}),))
    ids = messages["developer_data_id_mesgs"]
    assert [m["developer_data_index"] for m in ids] == [0, 1]
    assert ids[0]["application_id"] != ids[1]["application_id"]
    assert [d["developer_data_index"] for d in messages["field_description_mesgs"]] == [
        0,
        1,
        0,
    ]
    assert _dev(messages["record_mesgs"][0]) == {0: 1, 1: 2, 2: 3}


def test_helper_bytes_are_reproducible() -> None:
    def build() -> bytes:
        return builder.developer_field_run_fit_bytes(
            descriptions=_HELPER_DESCRIPTIONS,
            records=_HELPER_RECORDS,
            session_fields={3: 4},
        )

    assert build() == build()
