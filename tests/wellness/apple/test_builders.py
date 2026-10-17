"""Positive controls for synthetic Apple export fixtures."""

from __future__ import annotations

import io
import struct
import zipfile
from collections import Counter
from collections.abc import Iterator
from xml.etree import ElementTree as ET

import pytest

from fitdocs.wellness.formats.apple.records import normalize_device
from fitdocs.wellness.formats.apple.reduce import (
    Writer,
    device_maker_model,
    writer_of,
)
from tests.wellness.apple import builders


def parse(document: bytes) -> ET.Element:
    parser = ET.iterparse(io.BytesIO(document), events=("end",))
    root = ET.Element("unparsed")
    for _event, element in parser:
        root = element
    return root


@pytest.mark.parametrize(
    "preset, expected",
    [
        (builders.WATCH, Writer.WATCH),
        (builders.PHONE, Writer.PHONE),
        (builders.SLEEP_APP, Writer.OTHER),
        (builders.SCALE, Writer.OTHER),
    ],
)
def test_presets_classify_as_their_names_say(
    preset: builders.WriterPreset, expected: Writer
) -> None:
    device = None if preset.device is None else normalize_device(preset.device)
    maker_model = None if device is None else device_maker_model(device)
    assert writer_of([] if maker_model is None else [maker_model]) == expected


@pytest.mark.parametrize(
    "writer, expected",
    [
        (
            "WATCH",
            (
                "Example Apple Watch",
                "9.1",
                "<<HKDevice: 0xabc123>, name:Example Apple Watch, "
                "manufacturer:Apple Inc., model:Watch>",
            ),
        ),
        (
            "PHONE",
            (
                "Example iPhone",
                "17.2",
                "<<HKDevice: 0xdef456>, name:Example iPhone, "
                "manufacturer:Apple Inc., model:iPhone>",
            ),
        ),
        ("SLEEP_APP", ("Example Sleep App", "2.3", None)),
        ("SCALE", ("Example Scale", "3.4", "manufacturer:Example, model:Scale>")),
    ],
)
def test_writer_presets(writer: str, expected: tuple[str, str, str | None]) -> None:
    preset = getattr(builders, writer)
    assert (preset.source_name, preset.source_version, preset.device) == expected


def test_clean_document_counts() -> None:
    root = parse(builders.export_document())
    assert (root.tag, Counter(element.tag for element in root.iter())) == (
        "HealthData",
        Counter(
            {
                "HealthData": 1,
                "ExportDate": 1,
                "Me": 1,
                "Record": 11,
                "MetadataEntry": 2,
                "HeartRateVariabilityMetadataList": 1,
                "InstantaneousBeatsPerMinute": 1,
                "Workout": 1,
                "WorkoutStatistics": 1,
                "Correlation": 1,
                "ActivitySummary": 1,
            }
        ),
    )


def test_document_declaration_and_doctype() -> None:
    document = builders.export_document()
    assert document.startswith(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b"<!DOCTYPE HealthData [\n<!ELEMENT HealthData"
    )


def test_no_doctype() -> None:
    assert b"<!DOCTYPE" not in builders.export_document(include_doctype=False)


def test_document_default_attributes() -> None:
    root = parse(builders.export_document())
    assert (root.attrib, root[0].attrib, root[1].attrib) == (
        {"locale": "en_US"},
        {"value": "2024-02-06 14:30:00 -0800"},
        {
            "HKCharacteristicTypeIdentifierDateOfBirth": "1990-01-02",
            "HKCharacteristicTypeIdentifierBiologicalSex": "HKBiologicalSexNotSet",
        },
    )


def test_default_record_types() -> None:
    root = parse(builders.export_document())
    assert [element.attrib["type"] for element in root.findall("Record")] == [
        "HKQuantityTypeIdentifierRestingHeartRate",
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
        "HKQuantityTypeIdentifierRespiratoryRate",
        "HKQuantityTypeIdentifierOxygenSaturation",
        "HKQuantityTypeIdentifierVO2Max",
        "HKQuantityTypeIdentifierStepCount",
        "HKQuantityTypeIdentifierBodyMass",
        "HKCategoryTypeIdentifierSleepAnalysis",
        "HKQuantityTypeIdentifierHeartRate",
        "HKQuantityTypeIdentifierActiveEnergyBurned",
    ]


def test_default_record_values_and_units() -> None:
    root = parse(builders.export_document())
    assert [
        (element.get("value"), element.get("unit"))
        for element in root.findall("Record")
    ] == [
        ("53", "count/min"),
        ("47.2", "ms"),
        ("14.3", "count/min"),
        ("0.97", "%"),
        ("51.4", "mL/min·kg"),
        ("1234", "count"),
        ("71.25", "kg"),
        ("HKCategoryValueSleepAnalysisAsleepCore", None),
        ("89", "count/min"),
        ("42.6", "kcal"),
    ]


def test_default_hrv_children_and_nested_record() -> None:
    root = parse(builders.export_document())
    hrv = root.findall("Record")[1]
    nested = root.findall("Correlation/Record")[0]
    assert (
        [element.attrib for element in hrv.findall("MetadataEntry")],
        hrv.findall("HeartRateVariabilityMetadataList/InstantaneousBeatsPerMinute")[
            0
        ].attrib,
        nested.attrib["value"],
    ) == (
        [{"key": "z-key", "value": "009"}, {"key": "a-key", "value": "second"}],
        {"bpm": "63", "time": "2024-02-03 01:00:00 -0800"},
        "99999",
    )


def test_custom_record_verbatim_attributes_and_children() -> None:
    element = ET.fromstring(
        builders.record_xml(
            "CustomType",
            writer=builders.PHONE,
            start="2024-03-04 23:30:00 +0900",
            end="2024-03-05 00:10:00 +0900",
            creation="2024-03-05 00:11:00 +0900",
            value="007.50",
            unit="custom&unit",
            metadata=(("z", '9&<"'), ("a", "two")),
            children='<Extra value="42"/>',
        )
    )
    assert (element.attrib, [(child.tag, child.attrib) for child in element]) == (
        {
            "type": "CustomType",
            "sourceName": "Example iPhone",
            "sourceVersion": "17.2",
            "device": "<<HKDevice: 0xdef456>, name:Example iPhone, "
            "manufacturer:Apple Inc., model:iPhone>",
            "unit": "custom&unit",
            "creationDate": "2024-03-05 00:11:00 +0900",
            "startDate": "2024-03-04 23:30:00 +0900",
            "endDate": "2024-03-05 00:10:00 +0900",
            "value": "007.50",
        },
        [
            ("MetadataEntry", {"key": "z", "value": '9&<"'}),
            ("MetadataEntry", {"key": "a", "value": "two"}),
            ("Extra", {"value": "42"}),
        ],
    )


def test_record_attribute_overrides_and_omissions() -> None:
    element = ET.fromstring(
        builders.record_xml(
            "CustomType",
            attributes={
                "sourceName": None,
                "startDate": "naive",
                "newAttribute": "extra",
            },
            unit=None,
            writer=builders.SLEEP_APP,
        )
    )
    assert element.attrib == {
        "type": "CustomType",
        "sourceVersion": "2.3",
        "creationDate": "2024-02-03 08:01:00 -0800",
        "startDate": "naive",
        "endDate": "2024-02-03 08:00:00 -0800",
        "value": "1",
        "newAttribute": "extra",
    }


def test_custom_document_selection() -> None:
    root = parse(
        builders.export_document(
            records=[builders.record_xml("OnlyType", value="67")],
            export_date="2024-03-01 01:00:00 +0900",
            include_me=False,
            include_scaffold=False,
            extra_elements=['<Other value="91"/>'],
            locale="fr_FR",
        )
    )
    assert (root.attrib, [(child.tag, child.attrib) for child in root]) == (
        {"locale": "fr_FR"},
        [
            ("ExportDate", {"value": "2024-03-01 01:00:00 +0900"}),
            (
                "Record",
                {
                    "type": "OnlyType",
                    "sourceName": "Example Apple Watch",
                    "sourceVersion": "9.1",
                    "device": "<<HKDevice: 0xabc123>, name:Example Apple Watch, "
                    "manufacturer:Apple Inc., model:Watch>",
                    "creationDate": "2024-02-03 08:01:00 -0800",
                    "startDate": "2024-02-02 22:00:00 -0800",
                    "endDate": "2024-02-03 08:00:00 -0800",
                    "value": "67",
                },
            ),
            ("Other", {"value": "91"}),
        ],
    )


def test_empty_document_without_export_date() -> None:
    root = parse(
        builders.export_document(
            records=(), export_date=None, include_me=False, include_scaffold=False
        )
    )
    assert list(root) == []


@pytest.mark.parametrize(
    "defect, message",
    [
        ("malformed_doctype", "syntax error"),
        ("control_character", "not well-formed \\(invalid token\\)"),
        ("duplicate_start_date", "duplicate attribute"),
    ],
)
def test_each_defect_breaks_iterparse(defect: str, message: str) -> None:
    document = builders.export_document(
        malformed_doctype=defect == "malformed_doctype",
        control_character=defect == "control_character",
        duplicate_start_date=defect == "duplicate_start_date",
    )
    with pytest.raises(ET.ParseError, match=message):
        parse(document)


def test_all_defects_present() -> None:
    document = builders.export_document(
        malformed_doctype=True, control_character=True, duplicate_start_date=True
    )
    assert (
        document.count(b"CDATA #IMPLIED CDATA #IMPLIED"),
        document.count(b"Example\x0b Apple Watch"),
        document.count(
            b'startDate="2024-02-02 22:00:00 -0800" '
            b'startDate="2024-02-03 01:23:00 -0800"'
        ),
    ) == (1, 1, 1)


@pytest.mark.parametrize("count", [0, 3, 17])
def test_bulk_records(count: int) -> None:
    records = list(builders.bulk_records(count))
    root = parse(builders.export_document(records=records, include_scaffold=False))
    assert [
        (element.get("type"), element.get("value"), element.get("unit"))
        for element in root.findall("Record")
    ] == [
        ("HKQuantityTypeIdentifierHeartRate", str(60 + index), "count/min")
        for index in range(count)
    ]


@pytest.mark.parametrize(
    "variant, names",
    [
        (
            "english",
            ["apple_health_export/export.xml", "apple_health_export/export_cda.xml"],
        ),
        ("translated", ["exportation/sante.xml", "exportation/sante_cda.xml"]),
        (
            "macosx",
            [
                "__MACOSX/apple_health_export/export.xml",
                "__MACOSX/apple_health_export/export_cda.xml",
            ],
        ),
        ("garmin", ["DI_CONNECT/DI-Connect-Wellness/wellness.json"]),
        (
            "ambiguous",
            [
                "first/health.xml",
                "first/health_cda.xml",
                "second/data.xml",
                "second/data_cda.xml",
            ],
        ),
    ],
)
def test_zip_variant_names(variant: builders.ZipVariant, names: list[str]) -> None:
    with zipfile.ZipFile(io.BytesIO(builders.export_zip(variant=variant))) as archive:
        assert archive.namelist() == names


def test_zip_custom_payload_deflate_and_companion() -> None:
    document = builders.export_document(records=(), include_scaffold=False)
    with zipfile.ZipFile(
        io.BytesIO(
            builders.export_zip(document, variant="translated", include_macosx=True)
        )
    ) as archive:
        assert [
            (info.filename, info.compress_type, archive.read(info))
            for info in archive.infolist()
        ] == [
            ("exportation/sante.xml", zipfile.ZIP_DEFLATED, document),
            (
                "exportation/sante_cda.xml",
                zipfile.ZIP_DEFLATED,
                b'<?xml version="1.0" encoding="UTF-8"?>\n<ClinicalDocument/>\n',
            ),
            ("__MACOSX/exportation/sante.xml", zipfile.ZIP_DEFLATED, document),
            (
                "__MACOSX/exportation/sante_cda.xml",
                zipfile.ZIP_DEFLATED,
                b'<?xml version="1.0" encoding="UTF-8"?>\n<ClinicalDocument/>\n',
            ),
        ]


def test_zip_default_document() -> None:
    with zipfile.ZipFile(io.BytesIO(builders.export_zip())) as archive:
        root = parse(archive.read("apple_health_export/export.xml"))
    assert len(root.findall("Record")) == 10


def test_garmin_zip_contents() -> None:
    with zipfile.ZipFile(io.BytesIO(builders.export_zip(variant="garmin"))) as archive:
        assert (
            archive.read("DI_CONNECT/DI-Connect-Wellness/wellness.json")
            == b'{"dailySummary":[{"calendarDate":"2024-02-03","steps":4321}]}\n'
        )


def test_custom_zip_members() -> None:
    with zipfile.ZipFile(
        io.BytesIO(builders.zip_members({"z.xml": b"last", "a.xml": b"first"}))
    ) as archive:
        assert [
            (info.filename, info.date_time, archive.read(info))
            for info in archive.infolist()
        ] == [
            ("z.xml", (2024, 2, 6, 12, 0, 0), b"last"),
            ("a.xml", (2024, 2, 6, 12, 0, 0), b"first"),
        ]


@pytest.mark.parametrize("forced", [False, True])
def test_zip64_local_header(forced: bool) -> None:
    payload = builders.export_zip(force_zip64=forced)
    header = struct.unpack_from("<4s5H3I2H", payload)
    name_length, extra_length = header[-2:]
    extra = payload[30 + name_length : 30 + name_length + extra_length]
    assert (header[0], header[7] == 0xFFFFFFFF, header[8], extra[:4]) == (
        b"PK\x03\x04",
        forced,
        0xFFFFFFFF if forced else len(builders.export_document()),
        b"\x01\x00\x10\x00" if forced else b"",
    )


def test_zip64_reader_roundtrip() -> None:
    with zipfile.ZipFile(io.BytesIO(builders.export_zip(force_zip64=True))) as archive:
        root = parse(archive.read("apple_health_export/export.xml"))
    assert (root.tag, len(root.findall("Record"))) == ("HealthData", 10)


def test_bulk_is_iterator() -> None:
    assert isinstance(builders.bulk_records(3), Iterator)


def test_default_writer_assignments() -> None:
    root = parse(builders.export_document())
    assert [element.get("sourceName") for element in root.findall("Record")] == [
        "Example Apple Watch",
        "Example Apple Watch",
        "Example Apple Watch",
        "Example Apple Watch",
        "Example Apple Watch",
        "Example iPhone",
        "Example Scale",
        "Example Apple Watch",
        "Example Apple Watch",
        "Example Sleep App",
    ]
