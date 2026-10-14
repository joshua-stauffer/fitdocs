"""Apple record declarations and device text normalization."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import MISSING, FrozenInstanceError, astuple, fields
from enum import StrEnum
from typing import get_args

import pytest

from fitdocs.wellness.formats.apple import records

_RAW_RECORD_ARGUMENTS: dict[str, object] = {
    "type": "HKQuantityTypeIdentifierStepCount",
    "source_name": "Example Apple Watch",
    "source_version": "0009.1",
    "device": "manufacturer:Apple, model:Watch9",
    "unit": "count",
    "creation_date": "2024-02-03 10:45:01 +0900",
    "start_date": "2024-02-02 23:30:00 -0800",
    "end_date": "2024-02-03 00:10:00 -0800",
    "value": "007.50",
}
_CORRECTIONS_ARGUMENTS: dict[str, object] = {
    "doctype_removed": 2,
    "control_characters_removed": 3,
    "duplicate_attributes_removed": 5,
}


@pytest.mark.parametrize(
    "enum, expected",
    [
        (
            records.AppleType,
            {
                "RESTING_HEART_RATE": "HKQuantityTypeIdentifierRestingHeartRate",
                "HRV_SDNN": "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                "RESPIRATORY_RATE": "HKQuantityTypeIdentifierRespiratoryRate",
                "OXYGEN_SATURATION": "HKQuantityTypeIdentifierOxygenSaturation",
                "VO2_MAX": "HKQuantityTypeIdentifierVO2Max",
                "STEP_COUNT": "HKQuantityTypeIdentifierStepCount",
                "BODY_MASS": "HKQuantityTypeIdentifierBodyMass",
                "SLEEP_ANALYSIS": "HKCategoryTypeIdentifierSleepAnalysis",
            },
        ),
        (
            records.SleepState,
            {
                "IN_BED": "HKCategoryValueSleepAnalysisInBed",
                "ASLEEP_UNSPECIFIED": "HKCategoryValueSleepAnalysisAsleepUnspecified",
                "ASLEEP": "HKCategoryValueSleepAnalysisAsleep",
                "AWAKE": "HKCategoryValueSleepAnalysisAwake",
                "CORE": "HKCategoryValueSleepAnalysisAsleepCore",
                "DEEP": "HKCategoryValueSleepAnalysisAsleepDeep",
                "REM": "HKCategoryValueSleepAnalysisAsleepREM",
            },
        ),
    ],
    ids=["AppleType", "SleepState"],
)
def test_enum_identifiers(enum: type[StrEnum], expected: dict[str, str]) -> None:
    assert {name: member.value for name, member in enum.__members__.items()} == expected


@pytest.mark.parametrize("enum", [records.AppleType, records.SleepState])
def test_string_enums(enum: type[StrEnum]) -> None:
    assert issubclass(enum, StrEnum)


def test_record_attributes() -> None:
    assert records.RECORD_ATTRIBUTES == (
        "type",
        "sourceName",
        "sourceVersion",
        "device",
        "unit",
        "creationDate",
        "startDate",
        "endDate",
        "value",
    )


@pytest.mark.parametrize(
    "cls, expected, defaults",
    [
        (
            records.RawRecord,
            {
                "type": "str",
                "source_name": "str | None",
                "source_version": "str | None",
                "device": "str | None",
                "unit": "str | None",
                "creation_date": "str | None",
                "start_date": "str | None",
                "end_date": "str | None",
                "value": "str | None",
                "metadata": "tuple[tuple[str, str], ...]",
            },
            {"metadata": ()},
        ),
        (records.ExportDate, {"text": "str"}, {}),
        (
            records.Corrections,
            {
                "doctype_removed": "int",
                "control_characters_removed": "int",
                "duplicate_attributes_removed": "int",
            },
            {},
        ),
    ],
    ids=["RawRecord", "ExportDate", "Corrections"],
)
def test_fields_and_defaults(
    cls: type[records.RawRecord | records.ExportDate | records.Corrections],
    expected: dict[str, str],
    defaults: dict[str, object],
) -> None:
    assert tuple((field.name, field.type) for field in fields(cls)) == tuple(
        expected.items()
    )
    assert {
        field.name: field.default_factory for field in fields(cls)
    } == dict.fromkeys(expected, MISSING)
    assert {
        field.name: field.default
        for field in fields(cls)
        if field.default is not MISSING
    } == defaults
    assert {field.name: field.kw_only for field in fields(cls)} == dict.fromkeys(
        expected, False
    )


@pytest.mark.parametrize(
    "cls, arguments, field",
    [
        (records.RawRecord, _RAW_RECORD_ARGUMENTS, "type"),
        (
            records.ExportDate,
            {"text": "2024-02-06 14:30:00 -0800"},
            "text",
        ),
        (records.Corrections, _CORRECTIONS_ARGUMENTS, "doctype_removed"),
    ],
    ids=["RawRecord", "ExportDate", "Corrections"],
)
def test_frozen(
    cls: Callable[..., object], arguments: dict[str, object], field: str
) -> None:
    instance = cls(**arguments)
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field, "changed")


@pytest.mark.parametrize(
    "cls, arguments, missing",
    [
        *(
            pytest.param(
                records.RawRecord,
                _RAW_RECORD_ARGUMENTS,
                missing,
                id=f"RawRecord-{missing}",
            )
            for missing in (
                "type",
                "source_name",
                "source_version",
                "device",
                "unit",
                "creation_date",
                "start_date",
                "end_date",
                "value",
            )
        ),
        pytest.param(
            records.ExportDate,
            {"text": "2024-02-06 14:30:00 -0800"},
            "text",
            id="ExportDate-text",
        ),
        *(
            pytest.param(
                records.Corrections,
                _CORRECTIONS_ARGUMENTS,
                missing,
                id=f"Corrections-{missing}",
            )
            for missing in (
                "doctype_removed",
                "control_characters_removed",
                "duplicate_attributes_removed",
            )
        ),
    ],
)
def test_required_constructor_argument(
    cls: Callable[..., object], arguments: dict[str, object], missing: str
) -> None:
    supplied = {name: value for name, value in arguments.items() if name != missing}
    with pytest.raises(TypeError, match=f"'{missing}'"):
        cls(**supplied)


def test_metadata_optional_empty_tuple() -> None:
    factory: Callable[..., records.RawRecord] = records.RawRecord
    record = factory(**_RAW_RECORD_ARGUMENTS)
    assert record.metadata == ()


def test_raw_record_verbatim_text_and_metadata_order() -> None:
    record = records.RawRecord(
        type="HKQuantityTypeIdentifierStepCount",
        source_name="Example Apple Watch",
        source_version="0009.1",
        device="manufacturer:Apple, model:Watch9, hardware:0001",
        unit="count",
        creation_date="2024-02-03 10:45:01 +0900",
        start_date="2024-02-02 23:30:00 -0800",
        end_date="2024-02-03 00:10:00 -0800",
        value="007.50",
        metadata=(("z-key", "009"), ("a-key", "second"), ("z-key", "third")),
    )
    assert astuple(record) == (
        "HKQuantityTypeIdentifierStepCount",
        "Example Apple Watch",
        "0009.1",
        "manufacturer:Apple, model:Watch9, hardware:0001",
        "count",
        "2024-02-03 10:45:01 +0900",
        "2024-02-02 23:30:00 -0800",
        "2024-02-03 00:10:00 -0800",
        "007.50",
        (("z-key", "009"), ("a-key", "second"), ("z-key", "third")),
    )


def test_export_date_verbatim_text() -> None:
    export_date = records.ExportDate("2024-02-06 14:30:00 -0800")
    assert export_date.text == "2024-02-06 14:30:00 -0800"


def test_corrections_supplied_counts() -> None:
    corrections = records.Corrections(2, 3, 5)
    assert astuple(corrections) == (2, 3, 5)


@pytest.mark.parametrize(
    "attribute",
    [
        "source_name",
        "source_version",
        "device",
        "unit",
        "creation_date",
        "start_date",
        "end_date",
        "value",
    ],
)
def test_raw_record_nullable_text(attribute: str) -> None:
    factory: Callable[..., records.RawRecord] = records.RawRecord
    record = factory(**{**_RAW_RECORD_ARGUMENTS, attribute: None})
    assert getattr(record, attribute) is None


def test_export_item_union() -> None:
    assert get_args(records.ExportItem) == (
        records.ExportDate,
        records.RawRecord,
        records.Corrections,
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "<<HKDevice: 0x1a2b3c>, manufacturer:Apple, model:Watch>",
            "manufacturer:Apple, model:Watch",
        ),
        (
            "<<HKDevice: 0xA1B2>, name:Example > Watch, manufacturer:Apple>",
            "name:Example > Watch, manufacturer:Apple",
        ),
        (
            "<<HKDevice: 0x1a2b3c>, name:Example Watch\n"
            "manufacturer:Apple, model:Watch>",
            "name:Example Watch\nmanufacturer:Apple, model:Watch",
        ),
        (
            "manufacturer:Apple, model:Watch>",
            "manufacturer:Apple, model:Watch>",
        ),
        (
            "<<HKDevice: 0xnothex>, manufacturer:Apple, model:Watch>",
            "<<HKDevice: 0xnothex>, manufacturer:Apple, model:Watch>",
        ),
        (
            "prefix <<HKDevice: 0x1a2b3c>, manufacturer:Apple, model:Watch>",
            "prefix <<HKDevice: 0x1a2b3c>, manufacturer:Apple, model:Watch>",
        ),
        (
            "<<HKDevice: 0x1a2b3c>, manufacturer:Apple, model:Watch",
            "<<HKDevice: 0x1a2b3c>, manufacturer:Apple, model:Watch",
        ),
        ("", ""),
        ("<<HKDevice: 0x1a2b3c>, >", ""),
        ("<<HKDevice: 0x0>, name:Example Watch>", "name:Example Watch"),
        (
            "<<HKDevice: 0x0123456789abcdefABCDEF>, name:Example Watch>",
            "name:Example Watch",
        ),
        (
            "<<HKDevice: 0x1a2b3c>, \t name:Example Watch \t>",
            "\t name:Example Watch \t",
        ),
        (
            "<<HKDevice: 0x>, name:Example Watch>",
            "<<HKDevice: 0x>, name:Example Watch>",
        ),
        (
            "<<HKDevice: 0x1g>, name:Example Watch>",
            "<<HKDevice: 0x1g>, name:Example Watch>",
        ),
        (
            "<<HKDevice: 0x1a2b3c>, name:Example Watch>junk",
            "<<HKDevice: 0x1a2b3c>, name:Example Watch>junk",
        ),
    ],
    ids=[
        "wrapped",
        "upper-hex",
        "multiline",
        "unwrapped",
        "non-hex",
        "not-leading",
        "no-end",
        "empty",
        "wrapped-empty",
        "one-hex",
        "full-hex-range",
        "payload-whitespace",
        "empty-address",
        "mixed-nonhex-address",
        "trailing-junk",
    ],
)
def test_normalize_device(text: str, expected: str) -> None:
    assert records.normalize_device(text) == expected
