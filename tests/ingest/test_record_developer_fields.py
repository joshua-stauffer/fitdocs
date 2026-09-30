"""Record-level developer fields on the activity (running-dynamics 1.1-1.11, 6.5).

The Stryd fixture's description table pairs values by SDK key (position in the
file) while its ``field_definition_number`` values are deliberately different, so
a reader pairing by definition number reads the wrong series.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from fitdocs import Activity, parse_fit
from fitdocs.ingest.developer import extract_record_developer_fields
from fitdocs.ingest.records import retained_records
from tests.fixtures import builder
from tests.fixtures.builder import (
    BASE_TYPE,
    DevFieldSpec,
    developer_field_run_fit_bytes,
)

_RECORD_LEVEL_POSITIONS = tuple(
    range(11)
)  # position 11 is the session-only Run Profile
_UINT16 = BASE_TYPE["UINT16"]


def _stryd_expected(position: int) -> tuple[object, ...]:
    """The fixture's own recorded series for one description position.

    The one uint16 sentinel (65535 on Form Power) is "not recorded".
    """
    series = []
    for _native, recorded in builder._stryd_records():
        value = recorded[position]
        series.append(None if position == 1 and value == 65535 else value)
    return tuple(series)


@pytest.fixture(scope="module")
def stryd() -> Activity:
    return parse_fit(builder.stryd_run_fit_bytes())


def test_mapping_keys_are_exactly_the_eleven_record_level_names(
    stryd: Activity,
) -> None:
    expected = {builder._STRYD_DESCRIPTIONS[p].name for p in _RECORD_LEVEL_POSITIONS}
    assert len(expected) == 11
    assert set(stryd.record_developer_fields) == expected
    assert "Run Profile" not in stryd.record_developer_fields


def test_every_channel_has_one_value_per_sample(stryd: Activity) -> None:
    assert len(stryd.samples.time_s) == 44
    for name, channel in stryd.record_developer_fields.items():
        assert len(channel.values) == len(stryd.samples.time_s), name


def test_provenance_is_carried_verbatim_from_the_description(stryd: Activity) -> None:
    application_id = "".join(f"{b:02x}" for b in builder._application_id(0))
    assert len(application_id) == 32
    assert application_id != application_id.upper()  # has letters: case is observable
    for position in _RECORD_LEVEL_POSITIONS:
        spec = builder._STRYD_DESCRIPTIONS[position]
        channel = stryd.record_developer_fields[spec.name]
        assert channel.name == spec.name
        assert channel.units == spec.units
        assert channel.developer_data_index == 0
        assert channel.field_definition_number == spec.definition_number
        assert channel.application_id == application_id
        assert channel.declared_scale is False


@pytest.mark.parametrize("position", _RECORD_LEVEL_POSITIONS)
def test_values_equal_the_fixture_series_at_every_sample(
    stryd: Activity, position: int
) -> None:
    name = builder._STRYD_DESCRIPTIONS[position].name
    expected = _stryd_expected(position)
    actual = stryd.record_developer_fields[name].values
    assert actual == expected
    # Equality alone passes 0 for 0.0, so the types are compared as well.
    assert [type(v) for v in actual] == [type(v) for v in expected]


def test_the_exact_value_pins_are_not_trivial() -> None:
    """Preconditions of the per-sample pins: zeros present, series pairwise varied."""
    for position in (1, 2, 3, 4, 5, 6):
        series = _stryd_expected(position)
        assert 0 in series or 0.0 in series, position  # zeros are in the expectation
    form_power = _stryd_expected(1)
    assert form_power[builder._STRYD_SENTINEL_INDEX] is None
    assert len({v for v in _stryd_expected(2)}) >= 8  # several distinct values


def test_placeholder_zeros_are_kept_in_the_generic_mapping(stryd: Activity) -> None:
    form_power = stryd.record_developer_fields["Form Power"].values
    assert form_power[0] == 0
    assert form_power[builder._STRYD_SENTINEL_INDEX] is None
    balance = stryd.record_developer_fields["Vertical Oscillation Balance"].values
    assert balance[builder._STRYD_ZERO_BALANCE_INDEX] == 0.0


def test_humidity_104_is_decoded_not_bounded(stryd: Activity) -> None:
    values = stryd.record_developer_fields["Stryd Humidity"].values
    assert 104 in values
    assert values[builder._STRYD_HUMIDITY_104_INDEX] == 104


def test_native_speed_and_distance_are_the_native_values(stryd: Activity) -> None:
    natives = [native for native, _ in builder._stryd_records()]
    developer = stryd.record_developer_fields
    dev_speed = developer["Speed"].values
    dev_distance = developer["Distance"].values
    assert stryd.samples.speed_mps == tuple(n["enhanced_speed"] for n in natives)
    assert stryd.samples.distance_m == tuple(n["distance"] for n in natives)
    # The developer series differ from the native ones at every running record.
    running = [i for i, n in enumerate(natives) if n["enhanced_speed"] != 0.0]
    assert running
    for i in running:
        assert dev_speed[i] != stryd.samples.speed_mps[i]
        assert dev_distance[i] != stryd.samples.distance_m[i]


# --- Synthetic files ---------------------------------------------------------


def test_declared_scale_and_offset_decode_as_value_over_scale_minus_offset() -> None:
    descriptions = (
        DevFieldSpec("Scaled", _UINT16, 1, units="x", scale=10, offset=3),
        DevFieldSpec("Plain", _UINT16, 2, units="x"),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions,
        records=[({}, {0: 95, 1: 95}), ({}, {0: 100, 1: 100})],
    )
    fields = parse_fit(data).record_developer_fields
    # 95/10 - 3 = 6.5 and 100/10 - 3 = 7.0; (95-3)/10 or 95/(10-3) would differ.
    assert fields["Scaled"].values == (6.5, 7.0)
    assert fields["Scaled"].declared_scale is True
    assert fields["Plain"].values == (95, 100)
    assert fields["Plain"].declared_scale is False
    assert fields["Plain"].units == "x"
    assert fields["Scaled"].units == "x"


def test_a_scale_zero_description_is_omitted_and_nothing_raises() -> None:
    descriptions = (
        DevFieldSpec("Zero Scale", _UINT16, 1, scale=0),
        DevFieldSpec("Fine", _UINT16, 2),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions, records=[({}, {0: 7, 1: 8}), ({}, {0: 9, 1: 10})]
    )
    fields = parse_fit(data).record_developer_fields
    assert set(fields) == {"Fine"}
    assert fields["Fine"].values == (8, 10)


def test_a_repeated_index_and_definition_number_decodes_against_the_first() -> None:
    descriptions = (
        DevFieldSpec("First", _UINT16, 5, units="a"),
        DevFieldSpec("Second", _UINT16, 5, units="b", scale=10),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions, records=[({}, {0: 11, 1: 21}), ({}, {0: 12, 1: 22})]
    )
    fields = parse_fit(data).record_developer_fields
    assert set(fields) == {"First"}
    # The wire carries the last-written value under the shared slot; it is decoded
    # by the first description (units "a", no scale), not the second (scale 10).
    assert fields["First"].values == (21, 22)
    assert fields["First"].units == "a"
    assert fields["First"].declared_scale is False


def test_two_recorded_descriptions_sharing_a_name_expose_the_later_one() -> None:
    descriptions = (
        DevFieldSpec("Same", _UINT16, 1, units="early", developer_data_index=0),
        DevFieldSpec(
            "Same", _UINT16, 2, units="late", scale=10, developer_data_index=1
        ),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions, records=[({}, {0: 1, 1: 101}), ({}, {0: 2, 1: 102})]
    )
    fields = parse_fit(data).record_developer_fields
    assert list(fields) == ["Same"]
    late = fields["Same"]
    assert late.values == (10.1, 10.2)
    assert late.units == "late"
    assert late.field_definition_number == 2
    assert late.developer_data_index == 1
    assert late.application_id == "".join(
        f"{b:02x}" for b in builder._application_id(1)
    )
    assert late.declared_scale is True


@pytest.mark.parametrize(
    ("later_records", "later_scale"),
    [({}, 10), ({1: 65535}, 10), ({1: 7}, 0)],
    ids=["unrecorded", "sentinel", "scale0"],
)
def test_a_later_same_named_description_with_no_values_leaves_the_earlier(
    later_records: dict[int, object],
    later_scale: int,
) -> None:
    descriptions = (
        DevFieldSpec("Same", _UINT16, 1, units="early", developer_data_index=0),
        DevFieldSpec(
            "Same",
            _UINT16,
            2,
            units="late",
            scale=later_scale,
            developer_data_index=1,
        ),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions,
        records=[({}, {0: 1, **later_records}), ({}, {0: 2, **later_records})],
    )
    fields = parse_fit(data).record_developer_fields
    assert list(fields) == ["Same"]
    early = fields["Same"]
    assert early.values == (1, 2)
    assert early.units == "early"
    assert early.field_definition_number == 1
    assert early.developer_data_index == 0
    assert early.application_id == "".join(
        f"{b:02x}" for b in builder._application_id(0)
    )
    assert early.declared_scale is False


_RECORDS: list[dict[str, object]] = [{"timestamp": 1, "developer_fields": {0: 5}}]


def _bare_description(**extra: object) -> dict[str, object]:
    return {"field_name": "Bare", "key": 0, "fit_base_type_id": 0x84, **extra}


@pytest.mark.parametrize(
    "data_ids", [[], [{"developer_data_index": 0}]], ids=["no-message", "no-id"]
)
def test_application_id_is_none_when_the_file_records_none(
    data_ids: list[dict[str, object]],
) -> None:
    channels = extract_record_developer_fields(
        [_bare_description(developer_data_index=0)], data_ids, _RECORDS
    )
    assert channels["Bare"].application_id is None
    assert channels["Bare"].values == (5,)


def test_an_absent_index_definition_number_and_units_stay_none() -> None:
    channel = extract_record_developer_fields([_bare_description()], [], _RECORDS)[
        "Bare"
    ]
    assert channel.developer_data_index is None
    assert channel.field_definition_number is None
    assert channel.units is None
    assert channel.application_id is None
    assert channel.declared_scale is False


def test_an_offset_only_description_counts_as_declared() -> None:
    channel = extract_record_developer_fields(
        [_bare_description(offset=2)], [], _RECORDS
    )["Bare"]
    assert channel.declared_scale is True
    assert channel.values == (3,)


def test_no_developer_field_fills_a_native_temperature(stryd: Activity) -> None:
    # The Stryd fixture records no native temperature; its Stryd Temperature
    # description carries native slot 13.
    assert stryd.samples.temperature_c == (None,) * 44
    assert stryd.record_developer_fields["Stryd Temperature"].values != (None,) * 44


def test_developer_fields_with_native_slots_fill_no_native_channel() -> None:
    float32 = BASE_TYPE["FLOAT32"]
    descriptions = (
        DevFieldSpec("Dev Speed", float32, 8, native_mesg_num=6),
        DevFieldSpec("Dev Distance", float32, 9, native_mesg_num=5),
        DevFieldSpec("Dev Temperature", BASE_TYPE["SINT8"], 10, native_mesg_num=13),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions,
        records=[
            ({"heart_rate": 120 + i}, {0: 3.5 + i, 1: 10.5 + i, 2: 20 + i})
            for i in range(3)
        ],
    )
    activity = parse_fit(data)
    for name in ("Dev Speed", "Dev Distance", "Dev Temperature"):
        assert all(v is not None for v in activity.record_developer_fields[name].values)
    assert activity.samples.speed_mps == (None,) * 3
    assert activity.samples.distance_m == (None,) * 3
    assert activity.samples.temperature_c == (None,) * 3


def test_unrecorded_and_all_sentinel_fields_are_omitted() -> None:
    descriptions = (
        DevFieldSpec("Recorded", _UINT16, 1),
        DevFieldSpec("Unrecorded", _UINT16, 2),
        DevFieldSpec("All Sentinel", _UINT16, 3),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions,
        records=[({}, {0: 4, 2: 65535}), ({}, {0: 5, 2: 65535})],
    )
    fields = parse_fit(data).record_developer_fields
    assert set(fields) == {"Recorded"}


def test_a_partly_recorded_field_has_none_where_it_was_not_recorded() -> None:
    data = developer_field_run_fit_bytes(
        descriptions=(DevFieldSpec("Sparse", _UINT16, 1),),
        records=[({}, {0: 3}), ({}, {}), ({}, {0: 5}), ({}, {0: 65535}), ({}, {0: 0})],
    )
    fields = parse_fit(data).record_developer_fields
    # Not carried, carried as the sentinel, and a recorded zero are three states.
    assert fields["Sparse"].values == (3, None, 5, None, 0)


def test_a_file_with_no_descriptions_yields_an_empty_read_only_mapping() -> None:
    data = developer_field_run_fit_bytes(descriptions=(), records=[({}, {}), ({}, {})])
    fields = parse_fit(data).record_developer_fields
    assert len(fields) == 0
    assert isinstance(fields, MappingProxyType)
    with pytest.raises(TypeError):
        fields["x"] = None  # type: ignore[index]


def test_a_non_developer_fixture_yields_an_empty_mapping(run_fit_bytes: bytes) -> None:
    fields = parse_fit(run_fit_bytes).record_developer_fields
    assert len(fields) == 0
    assert isinstance(fields, MappingProxyType)


def test_application_id_is_per_developer_data_index() -> None:
    descriptions = (
        DevFieldSpec("On Zero", _UINT16, 1, developer_data_index=0),
        DevFieldSpec("On One", _UINT16, 1, developer_data_index=1),
    )
    data = developer_field_run_fit_bytes(
        descriptions=descriptions, records=[({}, {0: 1, 1: 2})]
    )
    fields = parse_fit(data).record_developer_fields
    zero = "".join(f"{b:02x}" for b in builder._application_id(0))
    one = "".join(f"{b:02x}" for b in builder._application_id(1))
    assert zero != one
    assert fields["On Zero"].application_id == zero
    assert fields["On One"].application_id == one
    assert fields["On One"].developer_data_index == 1


def test_values_stay_aligned_with_samples_when_a_record_has_no_timestamp() -> None:
    data = developer_field_run_fit_bytes(
        descriptions=(DevFieldSpec("Aligned", _UINT16, 1),),
        records=[
            ({}, {0: 11}),
            ({"timestamp": None, "heart_rate": 90}, {0: 12}),
            ({}, {0: 13}),
        ],
    )
    activity = parse_fit(data)
    assert len(activity.samples.time_s) == 2
    assert activity.record_developer_fields["Aligned"].values == (11, 13)


def test_retained_records_drops_only_records_without_a_timestamp() -> None:
    records: list[dict[str, object]] = [
        {"timestamp": 5, "a": 1},
        {"a": 2},
        {"timestamp": None, "a": 3},
        {"timestamp": 0, "a": 4},
    ]
    assert retained_records(records) == [records[0], records[3]]
