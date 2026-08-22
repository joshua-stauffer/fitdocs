"""Tests for the session-summary, activity-fallback, and device extractor.

These exercise :func:`fitdocs.ingest.summary.extract_summary` and
:func:`fitdocs.ingest.summary.extract_devices` on hand-built message dicts (the
extractors work on plain decoded dicts, so no binary fixtures are needed for the
unit cases) plus integration-style checks that decode the run fixture. Coverage:

* every :class:`SessionSummary` field maps from its FIT session key, with an
  absent key yielding ``None`` and a recorded ``0`` preserved as a real zero
  (Req 4.1, 12.3);
* speed prefers the ``enhanced_*`` variant when present/non-None, else the basic
  variant (Req 3.3 parity);
* the FIRST session message is used when several exist (Req 4.1);
* with no session message, ``total_timer_time_s`` falls back to the first
  activity message while every other field stays ``None`` (Req 4.2);
* both message lists empty -> an all-``None`` summary, no error;
* devices deduplicate by ``(device_index, serial_number)`` keeping the LAST
  report, distinct devices stay separate, absent fields are ``None``, and an
  empty device list yields an empty tuple (Req 4.5).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

import pytest
from garmin_fit_sdk import Encoder
from garmin_fit_sdk.fit import BASE_TYPE

from fitdocs.ingest.summary import (
    _developer_value,
    extract_developer_fields,
    extract_developer_fields_with_declared_scale,
    extract_devices,
    extract_summary,
)
from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
    fit_datetime,
)
from tests.fixtures.builder import decode_messages

# A fixed FIT-epoch second used as t0 (never wall-clock time).
TS0 = 1_000_000_000

# Global FIT message numbers for the developer-field round-trip fixtures.
_MESG_DEVELOPER_DATA_ID = 207
_MESG_FIELD_DESCRIPTION = 206
_MESG_SESSION = 18


def _assert_only_these_set(summary: SessionSummary, **expected: object) -> None:
    """Assert ``summary`` has exactly ``expected`` set and every other field None."""
    for field in dataclasses.fields(summary):
        value = getattr(summary, field.name)
        if field.name in expected:
            assert value == expected[field.name], field.name
        else:
            assert value is None, field.name


# --- Session mapping (Req 4.1) ----------------------------------------------


def test_full_session_maps_every_field() -> None:
    """A complete session dict maps each field; start_time is tz-aware UTC."""
    session = {
        "sport": "running",
        "sub_sport": "generic",
        "start_time": TS0,
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3550.0,
        "total_distance": 10000.0,
        "total_calories": 620,
        "total_ascent": 120.0,
        "total_descent": 118.0,
        "avg_heart_rate": 152,
        "max_heart_rate": 178,
        "avg_power": 240,
        "max_power": 410,
        "avg_cadence": 86,
        "max_cadence": 94,
        "avg_speed": 2.77,
        "max_speed": 3.4,
    }

    summary = extract_summary([session], [])

    assert summary.sport == "running"
    assert summary.sub_sport == "generic"
    assert summary.start_time == fit_datetime(TS0)
    assert summary.start_time is not None
    assert summary.start_time.tzinfo is not None
    assert summary.total_elapsed_time_s == 3600.0
    assert summary.total_timer_time_s == 3550.0
    assert summary.total_distance_m == 10000.0
    assert summary.total_calories_kcal == 620
    assert summary.total_ascent_m == 120.0
    assert summary.total_descent_m == 118.0
    assert summary.avg_heart_rate_bpm == 152
    assert summary.max_heart_rate_bpm == 178
    assert summary.avg_power_w == 240
    assert summary.max_power_w == 410
    assert summary.avg_cadence_rpm == 86
    assert summary.max_cadence_rpm == 94
    assert summary.avg_speed_mps == 2.77
    assert summary.max_speed_mps == 3.4


def test_absent_session_fields_are_none() -> None:
    """A sparse session leaves unrecorded fields None but returns a summary (4.1)."""
    summary = extract_summary([{"sport": "cycling"}], [])

    _assert_only_these_set(summary, sport="cycling")


def test_recorded_zero_is_preserved_not_none() -> None:
    """A recorded ``0`` stays a real zero, distinct from missing (Req 12.3)."""
    session = {
        "total_ascent": 0,
        "total_descent": 0,
        "avg_power": 0,
        "total_distance": 0.0,
    }

    summary = extract_summary([session], [])

    assert summary.total_ascent_m == 0
    assert summary.total_ascent_m is not None
    assert summary.total_descent_m == 0
    assert summary.avg_power_w == 0
    assert summary.total_distance_m == 0.0


def test_first_session_message_is_used() -> None:
    """With several session messages the FIRST one wins (Req 4.1)."""
    summary = extract_summary(
        [{"sport": "running"}, {"sport": "cycling"}],
        [],
    )

    assert summary.sport == "running"


# --- Enhanced speed preference (Req 3.3 parity) -----------------------------


def test_enhanced_speed_preferred_over_basic() -> None:
    """When both variants are present the enhanced speed wins."""
    session = {
        "enhanced_avg_speed": 5.5,
        "avg_speed": 5.0,
        "enhanced_max_speed": 7.2,
        "max_speed": 7.0,
    }

    summary = extract_summary([session], [])

    assert summary.avg_speed_mps == 5.5
    assert summary.max_speed_mps == 7.2


def test_basic_speed_used_when_enhanced_absent_or_none() -> None:
    """Absent or ``None`` enhanced speed falls back to the basic variant."""
    absent = extract_summary([{"avg_speed": 4.2, "max_speed": 6.0}], [])
    assert absent.avg_speed_mps == 4.2
    assert absent.max_speed_mps == 6.0

    none_enhanced = extract_summary(
        [{"enhanced_avg_speed": None, "avg_speed": 4.2}],
        [],
    )
    assert none_enhanced.avg_speed_mps == 4.2


def test_component_expanded_enhanced_speed_falls_back_to_basic() -> None:
    """A list-valued session ``enhanced_*`` speed falls back to the basic scalar.

    Regression guard for the same FIT component-expansion shape that crashed lap
    extraction on real files: ``expand_components=True`` can decode ``enhanced_*``
    as a redundant array (e.g. ``[3.17, 3.17]``); the shared enhanced-preference
    helper must fall back to the plain scalar rather than hand a list to the
    numeric coercer (which would crash the whole parse).
    """
    session = {
        "enhanced_avg_speed": [3.17, 3.17],
        "avg_speed": 3.17,
        "enhanced_max_speed": [4.0, 4.0],
        "max_speed": 4.0,
    }

    summary = extract_summary([session], [])

    assert summary.avg_speed_mps == 3.17
    assert summary.max_speed_mps == 4.0


# --- Activity fallback (Req 4.2) --------------------------------------------


def test_activity_fallback_populates_only_timer_time() -> None:
    """No session -> total_timer_time_s from the activity; everything else None."""
    activity = {
        "timestamp": TS0 + 3600,  # activity END time -- must NOT become start_time
        "total_timer_time": 3600.0,
        "num_sessions": 1,
    }

    summary = extract_summary([], [activity])

    _assert_only_these_set(summary, total_timer_time_s=3600.0)
    # start_time is deliberately left None: the activity timestamp is an END time.
    assert summary.start_time is None


def test_activity_fallback_first_activity_used() -> None:
    """The FIRST activity message supplies the fallback timer time."""
    summary = extract_summary(
        [],
        [{"total_timer_time": 100.0}, {"total_timer_time": 999.0}],
    )

    assert summary.total_timer_time_s == 100.0


def test_all_empty_yields_all_none_summary() -> None:
    """Both lists empty -> a SessionSummary with every field None, no error."""
    summary = extract_summary([], [])

    _assert_only_these_set(summary)


def test_no_session_no_activity_timer_time_stays_none() -> None:
    """A session-less file without activity messages leaves timer time None."""
    summary = extract_summary([], [])

    assert summary.total_timer_time_s is None


# --- Devices (Req 4.5) ------------------------------------------------------


def test_devices_dedup_keeps_last_report() -> None:
    """Repeated (device_index, serial) reports collapse to the LAST values (4.5)."""
    reports = [
        {
            "device_index": 0,
            "serial_number": 42,
            "manufacturer": "garmin",
            "battery_status": "good",
            "software_version": 4.1,
        },
        {
            "device_index": 0,
            "serial_number": 42,
            "manufacturer": "garmin",
            "battery_status": "low",  # later report -> this must win
            "software_version": 4.2,
        },
    ]

    devices = extract_devices(reports)

    assert len(devices) == 1
    assert devices[0].battery_status == "low"
    assert devices[0].software_version == 4.2
    assert devices[0].device_index == 0
    assert devices[0].serial_number == 42


def test_devices_distinct_identities_kept_separate() -> None:
    """Two different (device_index, serial) pairs yield two entries in order."""
    reports = [
        {"device_index": 0, "serial_number": 1, "manufacturer": "garmin"},
        {"device_index": 1, "serial_number": 2, "manufacturer": "wahoo"},
    ]

    devices = extract_devices(reports)

    assert len(devices) == 2
    assert devices[0].manufacturer == "garmin"
    assert devices[1].manufacturer == "wahoo"


def test_devices_absent_fields_are_none() -> None:
    """A device report with only an index -> all other fields None (4.5)."""
    devices = extract_devices([{"device_index": 3}])

    assert len(devices) == 1
    device = devices[0]
    assert device.device_index == 3
    assert device.manufacturer is None
    assert device.product_name is None
    assert device.serial_number is None
    assert device.software_version is None
    assert device.battery_status is None


def test_devices_product_name_falls_back_to_string_product() -> None:
    """When product_name is absent but ``product`` is a string, the name uses it."""
    named = extract_devices([{"device_index": 0, "product_name": "Edge 840"}])
    assert named[0].product_name == "Edge 840"

    fallback = extract_devices([{"device_index": 0, "product": "Forerunner 965"}])
    assert fallback[0].product_name == "Forerunner 965"

    # A numeric product code is not a name -> product_name stays None (no fabrication).
    numeric = extract_devices([{"device_index": 0, "product": 2697}])
    assert numeric[0].product_name is None


def test_devices_empty_input_yields_empty_tuple() -> None:
    """No device_info messages -> an empty tuple, not None (4.5)."""
    assert extract_devices([]) == ()


# --- device_index 'creator' -> 0 (Part C) -----------------------------------


def test_creator_device_index_maps_to_zero() -> None:
    """A 'creator' device index normalizes to the true int 0 (Part C)."""
    devices = extract_devices(
        [{"device_index": "creator", "serial_number": 5, "manufacturer": "garmin"}]
    )

    assert len(devices) == 1
    assert devices[0].device_index == 0


def test_creator_reports_dedup_and_field_matches_key() -> None:
    """Two 'creator' reports (same serial) collapse to one, keeping the last (Part C).

    The stored ``device_index`` is the int 0 -- equal to the normalized dedup key --
    so a device that reports its index as the string 'creator' and another that (in
    principle) reports it as the int 0 are the same device, never split.
    """
    devices = extract_devices(
        [
            {"device_index": "creator", "serial_number": 5, "battery_status": "good"},
            {"device_index": 0, "serial_number": 5, "battery_status": "low"},
        ]
    )

    assert len(devices) == 1
    assert devices[0].device_index == 0
    assert devices[0].battery_status == "low"  # last report wins


def test_other_non_int_device_index_stays_none() -> None:
    """An exotic non-int, non-'creator' index still maps to None in the field."""
    devices = extract_devices([{"device_index": "front", "serial_number": 9}])

    assert len(devices) == 1
    assert devices[0].device_index is None


# --- Unknown-enum-as-int robustness (Part B) --------------------------------


def test_int_valued_sport_does_not_crash_and_coerces() -> None:
    """An unknown ``sport`` decoded as a raw int coerces to its str, never crashing."""
    summary = extract_summary([{"sport": 999, "sub_sport": 42}], [])

    assert summary.sport == "999"
    assert summary.sub_sport == "42"


def test_int_valued_device_enums_do_not_crash_and_coerce() -> None:
    """Int-valued ``manufacturer``/``battery_status`` coerce to str, never crashing."""
    devices = extract_devices(
        [{"device_index": 0, "manufacturer": 7, "battery_status": 3}]
    )

    assert devices[0].manufacturer == "7"
    assert devices[0].battery_status == "3"


# --- Integration-style checks (real decoded fixture) ------------------------


def test_run_session_maps_through(run_fit_bytes: bytes) -> None:
    """The decoded run session maps through to a populated summary (Req 4.1)."""
    messages, _ = decode_messages(run_fit_bytes)

    summary = extract_summary(
        messages["session_mesgs"],
        messages.get("activity_mesgs") or [],
    )

    assert summary.sport == "running"
    assert summary.sub_sport == "generic"
    assert summary.start_time == fit_datetime(1_000_000_000)
    assert summary.total_distance_m == pytest.approx(29.7)
    assert summary.total_calories_kcal == 60
    assert summary.total_ascent_m == 9
    assert summary.total_descent_m == 0
    assert summary.avg_heart_rate_bpm == 133
    assert summary.max_heart_rate_bpm == 147
    # Both enhanced and basic avg speed are 3.3 in the fixture -> enhanced chosen.
    assert summary.avg_speed_mps == pytest.approx(3.3)
    # The run carries no power channel, so power stays None.
    assert summary.avg_power_w is None


def test_run_devices_extract(run_fit_bytes: bytes) -> None:
    """The decoded run device_info maps to one deduped DeviceInfo (Req 4.5)."""
    messages, _ = decode_messages(run_fit_bytes)

    devices = extract_devices(messages["device_info_mesgs"])

    assert len(devices) == 1
    device = devices[0]
    assert device.manufacturer == "garmin"
    assert device.serial_number == 1001
    assert device.product_name == "SyntheticRunWatch"
    assert device.software_version == pytest.approx(4.2)
    assert device.battery_status == "good"
    # Real FIT decodes the reporting device's index as the string enum 'creator'
    # (FIT value 0); it is normalized back to the true int 0 (Part C).
    assert device.device_index == 0


# --- Developer fields (Req 14.1-14.4) ---------------------------------------
#
# Discovered SDK convention (garmin-fit-sdk 21.208.0), verified by encode ->
# decode round-trip below: each decoded ``field_description`` message carries the
# described name under ``field_name`` and an integer ``key`` equal to its
# position in ``field_description_mesgs``. The developer values recorded on a
# message are exposed under ``session['developer_fields']`` as a dict keyed by
# that SAME integer ``key`` (NOT the ``field_definition_number``); array values
# come back as Python lists, scalars as-is. A described field the session did not
# record is simply absent from that dict. The extractor links name -> value via
# the field description's ``key`` and converts list values to tuples.


def _decode_dev_field_file(
    field_specs: list[tuple[str, int, int | None]],
    recorded: dict[str, object],
    field_def_numbers: list[int] | None = None,
    scale_offsets: dict[str, tuple[int | None, int | None]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Encode + decode a FIT file with developer field descriptions on a session.

    ``field_specs`` is a list of ``(field_name, fit_base_type_id, array_len)``;
    ``array_len`` is ``None`` for a scalar field. ``recorded`` maps a subset of
    those field names to the value recorded on the session (a name omitted from
    ``recorded`` is described but NOT recorded, exercising the omission path).

    ``field_def_numbers`` optionally sets each description's
    ``field_definition_number`` (defaults to the field's index). Passing values
    that differ from the index makes ``field_definition_number != key`` in the
    decoded output, which proves the extractor links by the decode-order ``key``.

    ``scale_offsets`` optionally maps a field name to a ``(scale, offset)`` pair
    to declare on that field's description; either element left ``None`` is left
    UNDECLARED on the wire (the key is omitted from the encoded message, exactly
    like a real file that never mentions it -- not encoded as a literal ``None``,
    which the FIT wire format cannot represent). A name absent from
    ``scale_offsets`` declares neither (today's corpus shape).

    Returns ``(field_description_mesgs, session_mesgs)`` exactly as the project's
    decode flags yield them. Encoding is inline here (the shared fixture builder
    is deliberately not touched for this one-off dev-field shape).
    """
    dev_data_id = {
        "mesg_num": _MESG_DEVELOPER_DATA_ID,
        "developer_data_index": 0,
        "application_id": list(range(16)),
    }
    encoder = Encoder()
    dev_values: dict[str, object] = {}
    field_description_mesgs: list[dict[str, object]] = []
    for index, (name, base_type, array_len) in enumerate(field_specs):
        field_desc: dict[str, object] = {
            "mesg_num": _MESG_FIELD_DESCRIPTION,
            "developer_data_index": 0,
            "field_definition_number": (
                index if field_def_numbers is None else field_def_numbers[index]
            ),
            "fit_base_type_id": base_type,
            "field_name": name,
        }
        if array_len is not None:
            field_desc["array"] = array_len
        if scale_offsets is not None and name in scale_offsets:
            scale, offset = scale_offsets[name]
            if scale is not None:
                field_desc["scale"] = scale
            if offset is not None:
                field_desc["offset"] = offset
        key = f"k{index}"
        encoder.add_developer_field(key, dev_data_id, field_desc)
        field_description_mesgs.append(field_desc)
        if name in recorded:
            dev_values[key] = recorded[name]

    encoder.write_mesg(dev_data_id)
    for field_desc in field_description_mesgs:
        encoder.write_mesg(field_desc)
    session: dict[str, object] = {
        "mesg_num": _MESG_SESSION,
        "start_time": TS0,
        "sport": "running",
    }
    if dev_values:
        session["developer_fields"] = dev_values
    encoder.write_mesg(session)

    messages, _ = decode_messages(bytes(encoder.close()))
    return messages["field_description_mesgs"], messages["session_mesgs"]


def test_developer_fields_round_trip_names_and_raw_values() -> None:
    """Described fields recorded on the session -> name->raw-value mapping (14.1).

    An array-valued field (a 16-byte identifier) comes back as a 16-entry tuple;
    a scalar comes back unchanged (14.2).
    """
    uuid_bytes = list(range(100, 116))  # 16 distinct byte values
    descriptions, sessions = _decode_dev_field_file(
        [
            ("SESSION UUID", BASE_TYPE["UINT8"], 16),
            ("WORKOUT RPE ESTIMATED", BASE_TYPE["UINT8"], None),
        ],
        recorded={"SESSION UUID": uuid_bytes, "WORKOUT RPE ESTIMATED": 7},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert set(mapping) == {"SESSION UUID", "WORKOUT RPE ESTIMATED"}
    # Array value preserved as a TUPLE of the same length (14.2).
    assert mapping["SESSION UUID"] == tuple(uuid_bytes)
    assert isinstance(mapping["SESSION UUID"], tuple)
    assert len(mapping["SESSION UUID"]) == 16
    # Scalar passes through unchanged.
    assert mapping["WORKOUT RPE ESTIMATED"] == 7


def test_developer_field_names_are_verbatim() -> None:
    """The mapping key equals the described ``field_name`` exactly (14.2).

    Spaces and case are preserved with no renaming or interpretation.
    """
    descriptions, sessions = _decode_dev_field_file(
        [("SESSION UUID", BASE_TYPE["UINT8"], 16)],
        recorded={"SESSION UUID": list(range(16))},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert list(mapping) == ["SESSION UUID"]


def test_developer_field_described_but_unrecorded_is_omitted() -> None:
    """A described field the session does NOT record is absent, not None (14.4)."""
    descriptions, sessions = _decode_dev_field_file(
        [
            ("WORKOUT RPE ESTIMATED", BASE_TYPE["UINT8"], None),
            ("AVG METs", BASE_TYPE["UINT8"], None),  # described but not recorded
        ],
        recorded={"WORKOUT RPE ESTIMATED": 6},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert "AVG METs" not in mapping
    assert mapping == {"WORKOUT RPE ESTIMATED": 6}


def test_developer_fields_uses_key_not_field_definition_number() -> None:
    """Values link by decode-order ``key``, not ``field_definition_number`` (14.1).

    The two fields are encoded with ``field_definition_number`` 5 and 9 while their
    decode-order ``key`` is 0 and 1, so ``key != field_definition_number``. The SDK
    exposes the recorded values under the integer ``key`` on the session, so an
    extractor that (wrongly) looked them up by ``field_definition_number`` would
    fail to find them.
    """
    descriptions, sessions = _decode_dev_field_file(
        [("FIELD A", BASE_TYPE["UINT8"], None), ("FIELD B", BASE_TYPE["UINT8"], None)],
        recorded={"FIELD A": 11, "FIELD B": 22},
        field_def_numbers=[5, 9],
    )
    # Guard: the decoded descriptions genuinely diverge ``key`` from
    # ``field_definition_number``, so this test actually exercises the distinction.
    assert [d["key"] for d in descriptions] == [0, 1]
    assert [d["field_definition_number"] for d in descriptions] == [5, 9]

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping == {"FIELD A": 11, "FIELD B": 22}


def test_no_field_descriptions_yields_empty_mapping() -> None:
    """No developer field descriptions -> an empty mapping, no error (14.3)."""
    mapping = extract_developer_fields([], [{"sport": "running"}])

    assert mapping == {}
    assert isinstance(mapping, Mapping)


def test_descriptions_present_but_session_records_none_is_empty() -> None:
    """Descriptions present but the session records none -> empty mapping (14.3)."""
    descriptions, sessions = _decode_dev_field_file(
        [("SESSION UUID", BASE_TYPE["UINT8"], 16)],
        recorded={},  # described, but nothing recorded on the session
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping == {}


def test_empty_session_mesgs_yields_empty_mapping() -> None:
    """No session message at all -> empty mapping, no error (14.3)."""
    mapping = extract_developer_fields([{"field_name": "SESSION UUID", "key": 0}], [])

    assert mapping == {}


def test_developer_field_mapping_is_read_only() -> None:
    """The returned mapping is read-only (cannot be mutated by a consumer)."""
    descriptions, sessions = _decode_dev_field_file(
        [("WORKOUT RPE ESTIMATED", BASE_TYPE["UINT8"], None)],
        recorded={"WORKOUT RPE ESTIMATED": 5},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    with pytest.raises(TypeError):
        mapping["INJECTED"] = 1  # type: ignore[index]


def test_first_session_message_supplies_developer_fields() -> None:
    """When several session messages exist, dev fields read from the FIRST (14.1)."""
    descriptions = [{"field_name": "RPE", "key": 0}]
    sessions = [
        {"developer_fields": {0: 4}},
        {"developer_fields": {0: 9}},
    ]

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping == {"RPE": 4}


# --- Declared scale/offset are applied (Req 14.2, as amended) ---------------
#
# The FIT ``field_description`` message can declare a ``scale`` and/or
# ``offset`` for a developer field. ``garmin-fit-sdk`` parses both into the
# description's decoded dict but never applies them to a developer-field VALUE
# (only to native profile fields) -- so this is applied by the extractor
# itself, per the FIT-protocol formula confirmed by reading the SDK's own
# ``__apply_scale_and_offset``: ``value / scale - offset``.


def test_declared_scale_alone_divides_the_value() -> None:
    """A declared ``scale`` with no ``offset`` divides the raw value (14.2)."""
    descriptions, sessions = _decode_dev_field_file(
        [("POWER TENTHS", BASE_TYPE["UINT16"], None)],
        recorded={"POWER TENTHS": 1234},
        scale_offsets={"POWER TENTHS": (10, None)},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping["POWER TENTHS"] == pytest.approx(123.4)


def test_declared_offset_alone_is_subtracted_against_an_implicit_scale_of_one() -> None:
    """A declared ``offset`` with no ``scale`` still applies (14.2).

    An unusual but legal description: FIT defaults an undeclared scale to 1
    (mirroring garmin-fit-sdk's own default for native fields), so only the
    offset moves the value.
    """
    descriptions, sessions = _decode_dev_field_file(
        [("SHIFTED", BASE_TYPE["UINT16"], None)],
        recorded={"SHIFTED": 1234},
        scale_offsets={"SHIFTED": (None, 5)},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping["SHIFTED"] == 1229


def test_declared_scale_and_offset_both_apply_scale_then_offset() -> None:
    """Both declared: divide by scale, THEN subtract offset (14.2)."""
    descriptions, sessions = _decode_dev_field_file(
        [("BOTH", BASE_TYPE["UINT16"], None)],
        recorded={"BOTH": 1234},
        scale_offsets={"BOTH": (10, 5)},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    # 1234 / 10 - 5 = 118.4 -- NOT (1234 - 5) / 10 = 122.9, pinning formula order.
    assert mapping["BOTH"] == pytest.approx(118.4)
    assert mapping["BOTH"] != pytest.approx(122.9)


def test_declared_scale_applies_elementwise_to_an_array_value() -> None:
    """A declared scale on an array field scales EVERY element (14.2)."""
    descriptions, sessions = _decode_dev_field_file(
        [("TRIPLE", BASE_TYPE["UINT16"], 3)],
        recorded={"TRIPLE": [10, 20, 30]},
        scale_offsets={"TRIPLE": (10, None)},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    expected = (pytest.approx(1.0), pytest.approx(2.0), pytest.approx(3.0))
    assert mapping["TRIPLE"] == expected
    assert isinstance(mapping["TRIPLE"], tuple)


def test_undeclared_scale_and_offset_leave_the_value_unchanged() -> None:
    """Neither declared (today's corpus shape): value passes through as-is (14.2).

    Pinned as its own case (distinct from the pre-existing round-trip test)
    because it is the exact scenario the amendment must NOT regress: nothing
    in the current corpus declares a scale, so this is the byte-identical
    behavior every existing consumer depends on.
    """
    descriptions, sessions = _decode_dev_field_file(
        [("PLAIN", BASE_TYPE["UINT16"], None)],
        recorded={"PLAIN": 1234},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping["PLAIN"] == 1234
    assert isinstance(mapping["PLAIN"], int)  # not coerced to float by unrun arithmetic


def test_declared_scale_of_zero_omits_the_field_rather_than_fabricate() -> None:
    """A declared ``scale`` of ``0`` cannot be divided by (hard no-fabrication rule).

    The maintainer's RULING (2026-07-27, recorded in Amendment 2's revision):
    rather than raise, or emit the raw un-decoded value (which would reinstate
    exactly the wrong-by-a-constant-factor, no-signal shape this amendment
    exists to close), the field is OMITTED entirely from the mapping -- the
    same never-fabricate treatment Req 14.4 gives a described-but-unrecorded
    field. No OTHER described field in the same file is affected.
    """
    descriptions, sessions = _decode_dev_field_file(
        [
            ("ZERO SCALE", BASE_TYPE["UINT16"], None),
            ("SIBLING", BASE_TYPE["UINT16"], None),
        ],
        recorded={"ZERO SCALE": 5, "SIBLING": 42},
        scale_offsets={"ZERO SCALE": (0, None)},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert "ZERO SCALE" not in mapping  # omitted, not 5 (raw), not 0 (fabricated)
    assert mapping["SIBLING"] == 42  # unaffected sibling field still present


def test_declared_scale_on_a_non_numeric_value_passes_through_unscaled() -> None:
    """A declared scale on a non-numeric (string) developer field cannot be applied.

    A malformed but real-world-possible description: the raw value passes
    through un-scaled rather than raising.
    """
    descriptions, sessions = _decode_dev_field_file(
        [("STRING FIELD", BASE_TYPE["STRING"], None)],
        recorded={"STRING FIELD": "hello"},
        scale_offsets={"STRING FIELD": (10, None)},
    )

    mapping = extract_developer_fields(descriptions, sessions)

    assert mapping["STRING FIELD"] == "hello"


def test_declared_scale_names_are_reported_alongside_the_values() -> None:
    """The paired extractor reports WHICH resolved names had a declared scale.

    This is the fact ``render/sections.py`` needs to avoid double-applying its
    own hundredths-guess fallback on top of a value ingest already decoded
    (Fix 1 / the render-layer defect Amendment 2 exists to close): one field
    declares a scale, its sibling does not, and only the declaring one is
    reported.
    """
    descriptions, sessions = _decode_dev_field_file(
        [
            ("DECLARED", BASE_TYPE["UINT16"], None),
            ("UNDECLARED", BASE_TYPE["UINT16"], None),
        ],
        recorded={"DECLARED": 950, "UNDECLARED": 950},
        scale_offsets={"DECLARED": (100, None)},
    )

    values, declared = extract_developer_fields_with_declared_scale(
        descriptions, sessions
    )

    assert values["DECLARED"] == pytest.approx(9.5)
    assert values["UNDECLARED"] == 950
    assert declared == frozenset({"DECLARED"})


def test_declared_scale_names_exclude_an_omitted_zero_scale_field() -> None:
    """A ``scale=0`` field is omitted from BOTH the values and the declared set.

    It cannot appear in the declared-scale set without also appearing in the
    values mapping -- the two must never disagree about a name's presence.
    """
    descriptions, sessions = _decode_dev_field_file(
        [("ZERO SCALE", BASE_TYPE["UINT16"], None)],
        recorded={"ZERO SCALE": 5},
        scale_offsets={"ZERO SCALE": (0, None)},
    )

    values, declared = extract_developer_fields_with_declared_scale(
        descriptions, sessions
    )

    assert "ZERO SCALE" not in values
    assert "ZERO SCALE" not in declared


def test_undeclared_bool_value_preserves_its_type() -> None:
    """An undeclared scale/offset preserves a ``bool`` raw value's TYPE (Req 14.2).

    No real developer field is boolean-typed today, but this pins that the
    pass-through path is genuinely a no-op for every type, not merely
    numerically equivalent -- ``sections.py`` guards ``isinstance(value,
    bool)`` downstream, and a silent ``bool`` -> ``int`` widening here would
    defeat that guard before it ever sees the value.
    """
    assert _developer_value(True, None, None) is True
    assert _developer_value(False, None, None) is False


# --- Model additive-field check (Req 14.1, 14.3) ----------------------------


def _empty_samples() -> Samples:
    return Samples(
        time_s=(),
        heart_rate_bpm=(),
        power_w=(),
        cadence_rpm=(),
        speed_mps=(),
        distance_m=(),
        altitude_m=(),
        latitude_deg=(),
        longitude_deg=(),
        temperature_c=(),
    )


def _all_none_summary() -> SessionSummary:
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


def _minimal_activity(**overrides: object) -> Activity:
    kwargs: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "provenance": Provenance(sha256="deadbeef", source_path=None, decode_errors=()),
        "sport": Sport.RUN,
        "modality": Modality.RUN,
        "is_indoor": False,
        "start_time": None,
        "summary": _all_none_summary(),
        "laps": (),
        "samples": _empty_samples(),
        "sets": (),
        "devices": (),
    }
    kwargs.update(overrides)
    return Activity(**kwargs)  # type: ignore[arg-type]


def test_activity_construction_without_developer_fields_defaults_empty() -> None:
    """Constructing Activity without developer_fields still works: empty default."""
    activity = _minimal_activity()

    assert activity.developer_fields == {}
    assert isinstance(activity.developer_fields, Mapping)
    # The default is read-only (a shared empty mapping is never mutated).
    with pytest.raises(TypeError):
        activity.developer_fields["x"] = 1  # type: ignore[index]


def test_activity_stores_populated_developer_fields() -> None:
    """A populated developer-field mapping is stored verbatim on the Activity."""
    dev = MappingProxyType({"SESSION UUID": tuple(range(16)), "RPE": 7})

    activity = _minimal_activity(developer_fields=dev)

    assert activity.developer_fields["SESSION UUID"] == tuple(range(16))
    assert activity.developer_fields["RPE"] == 7


def test_activity_construction_without_declared_scale_defaults_empty() -> None:
    """``developer_fields_declared_scale`` defaults to empty (Req 14.2, amended)."""
    activity = _minimal_activity()

    assert activity.developer_fields_declared_scale == frozenset()
    assert isinstance(activity.developer_fields_declared_scale, frozenset)


def test_activity_stores_populated_declared_scale_names() -> None:
    """A populated declared-scale set is stored verbatim on the Activity."""
    activity = _minimal_activity(
        developer_fields=MappingProxyType({"AVG METs": 9.5}),
        developer_fields_declared_scale=frozenset({"AVG METs"}),
    )

    assert activity.developer_fields_declared_scale == frozenset({"AVG METs"})
