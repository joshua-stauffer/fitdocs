"""Synthetic Apple Health XML and ZIP fixtures, using invented data only."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Literal
from xml.sax.saxutils import quoteattr

ZipVariant = Literal["english", "translated", "macosx", "garmin", "ambiguous"]


@dataclass(frozen=True)
class WriterPreset:
    source_name: str
    source_version: str
    device: str | None


WATCH = WriterPreset(
    "Example Apple Watch",
    "9.1",
    "<<HKDevice: 0xabc123>, name:Example Apple Watch, "
    "manufacturer:Apple Inc., model:Watch>",
)
PHONE = WriterPreset(
    "Example iPhone",
    "17.2",
    "<<HKDevice: 0xdef456>, name:Example iPhone, "
    "manufacturer:Apple Inc., model:iPhone>",
)
SLEEP_APP = WriterPreset("Example Sleep App", "2.3", None)
SCALE = WriterPreset("Example Scale", "3.4", "manufacturer:Example, model:Scale>")

START = "2024-02-02 22:00:00 -0800"
END = "2024-02-03 08:00:00 -0800"
CREATION = "2024-02-03 08:01:00 -0800"
EXPORT_DATE = "2024-02-06 14:30:00 -0800"
INVENTED_DOB = "1990-01-02"
ENGLISH_MAIN = "apple_health_export/export.xml"
TRANSLATED_MAIN = "exportation/sante.xml"
CDA_DOCUMENT = b'<?xml version="1.0" encoding="UTF-8"?>\n<ClinicalDocument/>\n'

_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
_DOCTYPE = """<!DOCTYPE HealthData [
<!ELEMENT HealthData (ExportDate,Me?,(Record|Workout|Correlation|ActivitySummary)*)>
<!ATTLIST HealthData locale CDATA #REQUIRED>
<!ELEMENT ExportDate EMPTY>
<!ATTLIST ExportDate value CDATA #REQUIRED>
<!ELEMENT Me EMPTY>
<!ATTLIST Me HKCharacteristicTypeIdentifierDateOfBirth CDATA #IMPLIED
              HKCharacteristicTypeIdentifierBiologicalSex CDATA #IMPLIED>
<!ELEMENT Record (MetadataEntry*,HeartRateVariabilityMetadataList?)>
<!ATTLIST Record type CDATA #REQUIRED sourceName CDATA #REQUIRED
                sourceVersion CDATA #IMPLIED device CDATA #IMPLIED
                unit CDATA #IMPLIED creationDate CDATA #REQUIRED
                startDate CDATA #REQUIRED endDate CDATA #REQUIRED value CDATA #IMPLIED>
<!ELEMENT MetadataEntry EMPTY>
<!ATTLIST MetadataEntry key CDATA #REQUIRED value CDATA #REQUIRED>
<!ELEMENT HeartRateVariabilityMetadataList (InstantaneousBeatsPerMinute*)>
<!ELEMENT InstantaneousBeatsPerMinute EMPTY>
<!ATTLIST InstantaneousBeatsPerMinute bpm CDATA #REQUIRED time CDATA #REQUIRED>
<!ELEMENT Workout (WorkoutStatistics*)>
<!ATTLIST Workout workoutActivityType CDATA #REQUIRED duration CDATA #IMPLIED>
<!ELEMENT WorkoutStatistics EMPTY>
<!ATTLIST WorkoutStatistics startDate CDATA #IMPLIED>
<!ELEMENT Correlation (Record*)>
<!ATTLIST Correlation type CDATA #REQUIRED>
<!ELEMENT ActivitySummary EMPTY>
<!ATTLIST ActivitySummary dateComponents CDATA #REQUIRED>
]>
"""


def _attributes(attributes: Mapping[str, str | None]) -> str:
    return "".join(
        f" {name}={quoteattr(value)}"
        for name, value in attributes.items()
        if value is not None
    )


def record_xml(
    record_type: str,
    *,
    writer: WriterPreset = WATCH,
    start: str = START,
    end: str = END,
    creation: str = CREATION,
    value: str = "1",
    unit: str | None = None,
    metadata: Iterable[tuple[str, str]] = (),
    children: str = "",
    attributes: Mapping[str, str | None] | None = None,
) -> str:
    """Build a record; overrides can omit attributes or supply invalid test text."""
    fields = {
        "type": record_type,
        "sourceName": writer.source_name,
        "sourceVersion": writer.source_version,
        "device": writer.device,
        "unit": unit,
        "creationDate": creation,
        "startDate": start,
        "endDate": end,
        "value": value,
    }
    if attributes is not None:
        fields.update(attributes)
    entries = "".join(
        f"<MetadataEntry{_attributes({'key': key, 'value': text})}/>"
        for key, text in metadata
    )
    return f"<Record{_attributes(fields)}>{entries}{children}</Record>"


def default_records() -> list[str]:
    values = (
        ("HKQuantityTypeIdentifierRestingHeartRate", "53", "count/min", WATCH),
        ("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", "47.2", "ms", WATCH),
        ("HKQuantityTypeIdentifierRespiratoryRate", "14.3", "count/min", WATCH),
        ("HKQuantityTypeIdentifierOxygenSaturation", "0.97", "%", WATCH),
        ("HKQuantityTypeIdentifierVO2Max", "51.4", "mL/min·kg", WATCH),
        ("HKQuantityTypeIdentifierStepCount", "1234", "count", PHONE),
        ("HKQuantityTypeIdentifierBodyMass", "71.25", "kg", SCALE),
        (
            "HKCategoryTypeIdentifierSleepAnalysis",
            "HKCategoryValueSleepAnalysisAsleepCore",
            None,
            WATCH,
        ),
        ("HKQuantityTypeIdentifierHeartRate", "89", "count/min", WATCH),
        ("HKQuantityTypeIdentifierActiveEnergyBurned", "42.6", "kcal", SLEEP_APP),
    )
    return [
        record_xml(
            record_type,
            writer=writer,
            value=value,
            unit=unit,
            metadata=(("z-key", "009"), ("a-key", "second")) if index == 1 else (),
            children=(
                "<HeartRateVariabilityMetadataList><InstantaneousBeatsPerMinute "
                'bpm="63" time="2024-02-03 01:00:00 -0800"/>'
                "</HeartRateVariabilityMetadataList>"
                if index == 1
                else ""
            ),
        )
        for index, (record_type, value, unit, writer) in enumerate(values)
    ]


def bulk_records(count: int) -> Iterator[str]:
    """Yield N unread heart-rate records with distinct invented values."""
    for index in range(count):
        yield record_xml(
            "HKQuantityTypeIdentifierHeartRate", value=str(60 + index), unit="count/min"
        )


def export_document(
    records: Iterable[str] | None = None,
    *,
    export_date: str | None = EXPORT_DATE,
    include_me: bool = True,
    include_scaffold: bool = True,
    include_doctype: bool = True,
    malformed_doctype: bool = False,
    control_character: bool = False,
    duplicate_start_date: bool = False,
    extra_elements: Iterable[str] = (),
    locale: str = "en_US",
) -> bytes:
    """Compose a document, accepting raw child XML for later fault fixtures."""
    doctype = _DOCTYPE if include_doctype else ""
    if malformed_doctype:
        doctype = _DOCTYPE.replace(
            "startDate CDATA #IMPLIED>", "startDate CDATA #IMPLIED CDATA #IMPLIED>"
        )
    elements: list[str] = []
    if export_date is not None:
        elements.append(f"<ExportDate{_attributes({'value': export_date})}/>")
    if include_me:
        elements.append(
            f'<Me HKCharacteristicTypeIdentifierDateOfBirth="{INVENTED_DOB}" '
            'HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexNotSet"/>'
        )
    elements.extend(default_records() if records is None else records)
    if include_scaffold:
        duplicate = (
            ' startDate="2024-02-03 01:23:00 -0800"' if duplicate_start_date else ""
        )
        elements.append(
            '<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="37">'
            f'<WorkoutStatistics startDate="{START}"{duplicate}/></Workout>'
        )
        elements.append(
            '<Correlation type="HKCorrelationTypeIdentifierBloodPressure">'
            + record_xml("HKQuantityTypeIdentifierStepCount", value="99999")
            + "</Correlation>"
        )
        elements.append('<ActivitySummary dateComponents="2024-02-03"/>')
    elements.extend(extra_elements)
    document = (
        _DECLARATION
        + doctype
        + f"<HealthData{_attributes({'locale': locale})}>\n"
        + "\n".join(elements)
        + "\n</HealthData>\n"
    )
    if control_character:
        document = document.replace(
            'sourceName="Example Apple Watch"',
            'sourceName="Example\x0b Apple Watch"',
            1,
        )
    return document.encode("utf-8")


def zip_members(members: Mapping[str, bytes], *, force_zip64: bool = False) -> bytes:
    sink = io.BytesIO()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            info = zipfile.ZipInfo(name, date_time=(2024, 2, 6, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            with archive.open(info, "w", force_zip64=force_zip64) as member:
                member.write(content)
    return sink.getvalue()


def export_zip(
    document: bytes | None = None,
    *,
    variant: ZipVariant = "english",
    force_zip64: bool = False,
    include_macosx: bool = False,
) -> bytes:
    document = export_document() if document is None else document
    if variant == "garmin":
        members = {
            "DI_CONNECT/DI-Connect-Wellness/wellness.json": (
                b'{"dailySummary":[{"calendarDate":"2024-02-03","steps":4321}]}\n'
            )
        }
    else:
        main_names = {
            "english": (ENGLISH_MAIN,),
            "translated": (TRANSLATED_MAIN,),
            "macosx": ("__MACOSX/" + ENGLISH_MAIN,),
            "ambiguous": ("first/health.xml", "second/data.xml"),
        }[variant]
        members = {}
        for name in main_names:
            members[name] = document
            members[name[:-4] + "_cda.xml"] = CDA_DOCUMENT
        if include_macosx:
            members.update(
                {
                    "__MACOSX/" + name: content
                    for name, content in tuple(members.items())
                }
            )
    return zip_members(members, force_zip64=force_zip64)
