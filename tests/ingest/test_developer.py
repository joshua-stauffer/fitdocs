"""Unit tests for ``fitdocs.ingest.developer`` (running-dynamics 1.4-1.7, 1.10, 1.12).

The decoder's rule, in order: the sentinel of the declared base type, the
float32 shortest decimal, then the declared scale/offset.
"""

from __future__ import annotations

import dataclasses
import math
import struct

import pytest
from garmin_fit_sdk.fit import BASE_TYPE_DEFINITIONS

from fitdocs.ingest.developer import (
    INVALID_VALUES,
    FieldDescription,
    application_ids,
    decode_developer_value,
    parse_field_descriptions,
)

_UINT8 = 0x02
_SINT16 = 0x03
_UINT16 = 0x04
_STRING = 0x07
_FLOAT32 = 0x08
_FLOAT64 = 0x09
_UINT8Z = 0x0A
_UINT32Z = 0x0C
_BYTE = 0x0D

# The base types with no integer invalid value: string, float32, float64.
_NON_INTEGER = {_STRING, _FLOAT32, _FLOAT64}


def _description(
    base_type: int | None,
    scale: int | float | None = None,
    offset: int | float | None = None,
) -> FieldDescription:
    return FieldDescription(
        key=0,
        name="F",
        developer_data_index=0,
        field_definition_number=0,
        base_type=base_type,
        units=None,
        scale=scale,
        offset=offset,
    )


def _float32(value: float) -> float:
    """The double a decoder hands back for a float32 written as ``value``."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


# --- the invalid-value table --------------------------------------------------


def test_invalid_value_table_equals_the_sdk_for_each_integer_base_type() -> None:
    integer_codes = sorted(set(BASE_TYPE_DEFINITIONS) - _NON_INTEGER)

    compared = 0
    for code in integer_codes:
        assert INVALID_VALUES[code] == BASE_TYPE_DEFINITIONS[code]["invalid"], code
        compared += 1

    assert compared == 14
    assert sorted(INVALID_VALUES) == integer_codes


# --- sentinels ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base_type", "sentinel"),
    [
        (_UINT8, 0xFF),
        (_UINT16, 0xFFFF),
        (_SINT16, 0x7FFF),
        (_UINT32Z, 0),
        (_BYTE, 0xFF),
    ],
)
def test_scalar_sentinel_is_not_recorded(base_type: int, sentinel: int) -> None:
    assert decode_developer_value(sentinel, _description(base_type)) is None


def test_a_value_next_to_the_sentinel_is_kept() -> None:
    """Neighbours of a sentinel survive; ``0`` is data unless the type is ``z``."""
    assert decode_developer_value(0xFFFE, _description(_UINT16)) == 0xFFFE
    assert decode_developer_value(1, _description(_UINT32Z)) == 1
    assert decode_developer_value(0, _description(_UINT8)) == 0
    assert decode_developer_value(0, _description(_UINT8Z)) is None


@pytest.mark.parametrize("base_type", [_FLOAT32, _FLOAT64])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_float_scalar_is_not_recorded(base_type: int, value: float) -> None:
    assert decode_developer_value(value, _description(base_type)) is None


def test_integer_array_of_only_sentinels_is_not_recorded() -> None:
    assert decode_developer_value([255, 255, 255], _description(_UINT8)) is None


def test_integer_array_with_one_valid_element_is_unchanged() -> None:
    assert decode_developer_value([255, 255, 7], _description(_UINT8)) == (255, 255, 7)


def test_float_array_with_one_nan_keeps_its_finite_elements() -> None:
    decoded = decode_developer_value([1.5, math.nan, 2.5], _description(_FLOAT32))

    assert decoded == (1.5, None, 2.5)


def test_float_array_of_only_non_finite_elements_is_not_recorded() -> None:
    assert decode_developer_value([math.nan, math.inf], _description(_FLOAT32)) is None


# --- float32 shortest decimal ---------------------------------------------------


def test_float32_two_decimal_value_becomes_its_shortest_decimal() -> None:
    raw = _float32(11.37)
    assert raw != 11.37  # precondition: float32 cannot hold 11.37 exactly

    assert decode_developer_value(raw, _description(_FLOAT32)) == 11.37


def test_float32_value_needing_nine_digits_keeps_all_nine() -> None:
    raw = _float32(15.949965476989746)
    target = struct.pack("<f", raw)
    # Precondition: eight significant digits do not reach the same 32-bit
    # pattern, nine do.
    assert struct.pack("<f", float(f"{raw:.8g}")) != target
    assert struct.pack("<f", 15.9499655) == target

    assert decode_developer_value(raw, _description(_FLOAT32)) == 15.9499655


def test_float64_value_is_not_rounded_to_float32_digits() -> None:
    raw = _float32(11.37)

    assert decode_developer_value(raw, _description(_FLOAT64)) == raw


# --- declared scale after rounding ------------------------------------------------


def test_declared_scale_and_offset_apply_to_the_rounded_float32_value() -> None:
    raw = _float32(32.74)
    description = _description(_FLOAT32, scale=2, offset=10)
    # Precondition: the two orders of operation give different results here.
    assert raw / 2 - 10 != 32.74 / 2 - 10

    assert decode_developer_value(raw, description) == 32.74 / 2 - 10


# --- pass-through -----------------------------------------------------------------


@pytest.mark.parametrize("base_type", [None, 0x1F])
def test_absent_or_unknown_base_type_passes_a_value_through(
    base_type: int | None,
) -> None:
    description = _description(base_type)

    assert decode_developer_value(255, description) == 255
    assert decode_developer_value(0xFFFF, description) == 0xFFFF
    nan = decode_developer_value(math.nan, description)
    assert isinstance(nan, float) and math.isnan(nan)


def test_string_base_type_has_no_sentinel_check() -> None:
    assert decode_developer_value(0, _description(_STRING)) == 0
    assert decode_developer_value("abc", _description(_STRING)) == "abc"


def test_a_declared_scale_divides_an_integer_after_the_sentinel_check() -> None:
    description = _description(_UINT16, scale=10)

    assert decode_developer_value(1234, description) == pytest.approx(123.4)
    assert decode_developer_value(0xFFFF, description) is None


# --- application_ids --------------------------------------------------------------


def test_application_ids_accepts_only_a_sixteen_entry_byte_list() -> None:
    good = list(range(16))
    good_hex = bytes(good).hex()
    assert good_hex == "000102030405060708090a0b0c0d0e0f"

    def only_good_survives(decoy: object) -> None:
        mesgs = [
            {"developer_data_index": 0, "application_id": good},
            {"developer_data_index": 1, "application_id": decoy},
        ]
        assert dict(application_ids(mesgs)) == {0: good_hex}, decoy

    only_good_survives(list(range(15)))
    only_good_survives(list(range(17)))
    only_good_survives([*range(15), 256])
    only_good_survives([*range(15), -1])
    only_good_survives([*range(15), "a"])
    only_good_survives(tuple(range(16)))
    only_good_survives(bytes(range(16)))
    only_good_survives(None)


def test_application_ids_without_an_integer_index_is_skipped() -> None:
    mesgs = [{"developer_data_index": "x", "application_id": list(range(16))}]

    assert dict(application_ids(mesgs)) == {}


# --- parse_field_descriptions ---------------------------------------------------


def test_parse_field_descriptions_keeps_file_order_and_skips_unusable_ones() -> None:
    mesgs = [
        {"key": 0, "field_name": "B", "fit_base_type_id": 0x84},
        {"key": 1, "field_name": 7},
        {"key": "2", "field_name": "C"},
        {"key": 3, "field_name": "A", "units": "W", "scale": 10, "offset": 5},
    ]

    parsed = parse_field_descriptions(mesgs)

    assert [d.name for d in parsed] == ["B", "A"]
    assert [d.key for d in parsed] == [0, 3]
    assert parsed[0].base_type == 0x04  # 0x84 masked to its base type
    assert parsed[0].scale is None and parsed[0].units is None
    assert (parsed[1].units, parsed[1].scale, parsed[1].offset) == ("W", 10, 5)


def test_a_description_has_no_native_slot() -> None:
    """A parsed description has no field for a native message or field number."""
    mesgs = [
        {
            "key": 0,
            "field_name": "Speed",
            "native_mesg_num": 20,
            "native_field_num": 6,
        }
    ]

    parsed = parse_field_descriptions(mesgs)

    assert len(parsed) == 1
    assert {f.name for f in dataclasses.fields(parsed[0])} == {
        "key",
        "name",
        "developer_data_index",
        "field_definition_number",
        "base_type",
        "units",
        "scale",
        "offset",
    }


def test_float32_array_elements_are_each_rounded_to_their_shortest_decimal() -> None:
    raw = _float32(11.37)
    assert raw != 11.37  # precondition: the element is float32-inexact

    decoded = decode_developer_value([raw, math.nan, 2.5], _description(_FLOAT32))

    assert decoded == (11.37, None, 2.5)
