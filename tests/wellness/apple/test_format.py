"""Apple format composition through the public registry contracts."""

from __future__ import annotations

import ast
import gzip
import hashlib
import importlib
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from fitdocs.wellness import registry
from fitdocs.wellness.formats import apple
from fitdocs.wellness.formats.apple.records import AppleType
from fitdocs.wellness.formats.apple.reduce import POLICIES
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import HEAD_BYTES, CandidateProbe
from fitdocs.wellness.spec import ArchiveForm, ExtractContext, SourceKind, Supersession
from tests.wellness._helpers import CountingOpener, check_bounded_reads
from tests.wellness.apple.builders import (
    CDA_DOCUMENT,
    SCALE,
    WriterPreset,
    export_document,
    export_zip,
    record_xml,
)

WATCH = WriterPreset(
    "Example Apple Watch", "9.1", "manufacturer:Apple Inc., model:Watch"
)

codec = importlib.import_module("fitdocs.wellness.formats.apple.extract")

DECLARATIONS = (
    ("FORMAT_ID", "apple-health"),
    ("ARCHIVED_SUFFIX", ".jsonl.gz"),
    ("RULES_VERSION", 1),
    ("SOURCE.id", "apple-health"),
    ("SOURCE.display_name", "Apple Health"),
    ("SOURCE.kind", SourceKind.HUB),
    ("FORMAT.id", "apple-health"),
    ("FORMAT.display_name", "Apple Health export"),
    ("FORMAT.suffixes", frozenset({".zip", ".xml"})),
    ("FORMAT.archive_form", ArchiveForm.EXTRACT),
    ("FORMAT.archived_suffix", ".jsonl.gz"),
    ("FORMAT.rules_version", 1),
    ("FORMAT.supersession", Supersession.LATEST_ENTRY),
)


@pytest.mark.parametrize(("field", "expected"), DECLARATIONS)
def test_declarations(field: str, expected: object) -> None:
    value: Any = apple
    for component in field.split("."):
        value = getattr(value, component)
    assert value == expected


@pytest.mark.parametrize("field", ["recognize", "extract", "parse", "entry_order"])
def test_callable_bindings(field: str) -> None:
    assert getattr(apple.FORMAT, field) is getattr(apple, field)


def test_source_binding() -> None:
    assert apple.FORMAT.source is apple.SOURCE


def test_metrics() -> None:
    expected = frozenset(
        metric for policy in POLICIES.values() for metric in policy.metrics
    )
    assert (apple.METRICS, apple.FORMAT.metrics) == (expected, expected)


@pytest.mark.parametrize(
    "name",
    ["FORMAT_ID", "ARCHIVED_SUFFIX", "RULES_VERSION", "METRICS", "SOURCE", "FORMAT"],
)
def test_final_declarations(name: str) -> None:
    tree = ast.parse(Path(apple.__file__).read_text())
    annotation = next(
        node.annotation
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == name
    )
    expected = {
        "FORMAT_ID": "Final[str]",
        "ARCHIVED_SUFFIX": "Final[str]",
        "RULES_VERSION": "Final[int]",
        "METRICS": "Final[frozenset[Metric]]",
        "SOURCE": "Final[SourceSpec]",
        "FORMAT": "Final[FormatSpec]",
    }
    assert ast.unparse(annotation) == expected[name]


def test_actual_registration() -> None:
    assert (
        registry.source_named("apple-health"),
        registry.format_named("apple-health"),
    ) == (apple.SOURCE, apple.FORMAT)
    registry.validate_registry()


CANDIDATES = (
    ("english", "renamed.zip", export_zip(), True),
    ("translated", "renamed.zip", export_zip(variant="translated"), True),
    ("zip64", "renamed.zip", export_zip(force_zip64=True), True),
    ("bare", "data.xml", export_document(), True),
    ("garmin", "renamed.zip", export_zip(variant="garmin"), False),
    ("cda", "export_cda.xml", CDA_DOCUMENT, False),
    ("gpx", "route.xml", b"<?xml version='1.0'?><gpx/>", False),
    ("ambiguous", "renamed.zip", export_zip(variant="ambiguous"), False),
    ("other", "data.txt", export_document(), False),
    ("bad-zip", "invalid.zip", b"not a zip", False),
)


@pytest.mark.parametrize(
    ("label", "name", "raw", "accepted"), CANDIDATES, ids=[row[0] for row in CANDIDATES]
)
def test_recognize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    name: str,
    raw: bytes,
    accepted: bool,
) -> None:
    if name.endswith(".zip") and label != "bad-zip":
        expanded = BytesIO(raw)
        with zipfile.ZipFile(expanded, "a", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("padding/data.bin", b"x" * (3 * HEAD_BYTES))
        raw = expanded.getvalue()
    else:
        raw += b" " * (3 * HEAD_BYTES)
    path = tmp_path / name
    path.write_bytes(raw)
    counting = CountingOpener(path)
    counting.install(monkeypatch)
    probe = CandidateProbe.open(path)
    claimed = apple.recognize(probe)
    registered = registry.recognize(probe)
    assert (claimed, isinstance(registered, registry.Recognized)) == (
        accepted,
        accepted,
    )
    assert sum(read.returned for read in counting.reads) > 0
    check_bounded_reads(counting.reads)
    assert all(
        (read.start == 0 and read.requested == HEAD_BYTES)
        or (probe.suffix == ".zip" and read.start >= len(raw) - 65558)
        or (
            probe.suffix == ".zip"
            and read.start == counting.central_offset
            and read.requested == counting.central_size
        )
        for read in counting.reads
    )


@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "zip"])
def test_large_recognition_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, zipped: bool
) -> None:
    raw = export_document(
        [], extra_elements=["<Padding>" + "x" * 2_100_000 + "</Padding>"]
    )
    if zipped:
        sink = BytesIO()
        with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("apple_health_export/export.xml", raw)
            for index in range(4000):
                archive.writestr(f"extra/{index:04d}-" + "x" * 230, b"")
        raw = sink.getvalue()
    path = tmp_path / ("data.zip" if zipped else "data.xml")
    path.write_bytes(raw)
    counting = CountingOpener(path)
    counting.install(monkeypatch)
    assert apple.recognize(CandidateProbe.open(path))
    assert sum(read.returned for read in counting.reads) > 0
    check_bounded_reads(counting.reads)
    assert all(
        (read.start == 0 and read.requested == HEAD_BYTES)
        or (zipped and read.start >= len(raw) - 65558)
        or (
            zipped
            and read.start == counting.central_offset
            and read.requested == counting.central_size
        )
        for read in counting.reads
    )


def document() -> bytes:
    records = []
    for kind, value, unit in (
        (AppleType.RESTING_HEART_RATE, "53", "count/min"),
        (AppleType.HRV_SDNN, "47.2", "ms"),
        (AppleType.RESPIRATORY_RATE, "14.3", "count/min"),
        (AppleType.OXYGEN_SATURATION, "0.97", "%"),
        (AppleType.VO2_MAX, "51.4", "mL/min·kg"),
        (AppleType.STEP_COUNT, "1234", "count"),
        (AppleType.BODY_MASS, "71.25", "kg"),
    ):
        records.append(
            record_xml(
                kind,
                value=value,
                unit=unit,
                start="2024-02-03 01:00:00 -0800",
                end="2024-02-03 02:00:00 -0800",
                writer=SCALE if kind is AppleType.BODY_MASS else WATCH,
            )
        )
    for state, start, end in (
        ("Deep", "2024-02-02 22:00:00", "2024-02-02 23:00:00"),
        ("Core", "2024-02-02 23:00:00", "2024-02-03 01:00:00"),
        ("REM", "2024-02-03 01:00:00", "2024-02-03 04:00:00"),
        ("Awake", "2024-02-03 04:00:00", "2024-02-03 04:30:00"),
    ):
        records.append(
            record_xml(
                AppleType.SLEEP_ANALYSIS,
                writer=WATCH,
                value="HKCategoryValueSleepAnalysis"
                + ("Asleep" if state != "Awake" else "")
                + state,
                start=start + " -0800",
                end=end + " -0800",
            )
        )
    return export_document(records)


def extracted(path: Path, *, progress: Any = None) -> BytesIO:
    sink = BytesIO()
    raw = path.read_bytes()
    apple.extract(
        path, sink, ExtractContext(hashlib.sha256(raw).hexdigest(), len(raw), progress)
    )
    return sink


def test_extract_parse(tmp_path: Path) -> None:
    path = tmp_path / "data.xml"
    raw = document()
    path.write_bytes(raw)
    progress: list[tuple[int, int]] = []
    sink = extracted(path, progress=lambda read, size: progress.append((read, size)))
    assert not sink.closed
    assert progress == [(len(raw), len(raw))]
    header = codec.read_header(BytesIO(sink.getvalue()))
    assert (
        header.original_sha256,
        header.original_size,
        header.export_date,
        header.export_date_utc,
    ) == (
        hashlib.sha256(raw).hexdigest(),
        len(raw),
        "2024-02-06 14:30:00 -0800",
        "2024-02-06T22:30:00Z",
    )
    values = {
        Metric.RESTING_HR_BPM: 53,
        Metric.HRV_SDNN_MS: 47.2,
        Metric.RESPIRATION_BRPM: 14.3,
        Metric.SPO2_PCT: 97,
        Metric.VO2MAX_ML_PER_KG_MIN: 51.4,
        Metric.STEPS: 1234,
        Metric.WEIGHT_KG: 71.25,
        Metric.SLEEP_S: 21600,
        Metric.SLEEP_DEEP_S: 3600,
        Metric.SLEEP_LIGHT_S: 7200,
        Metric.SLEEP_REM_S: 10800,
        Metric.SLEEP_AWAKE_S: 1800,
    }
    assert tuple(apple.parse(BytesIO(sink.getvalue()))) == (
        DaySnapshot(
            date(2024, 2, 3),
            frozenset(values),
            values,
            {metric: "apple" for metric in values if metric is not Metric.WEIGHT_KG},
            None,
            0,
        ),
    )


@pytest.mark.parametrize("zipped", [False, True], ids=["bare", "zip"])
def test_original_unchanged(tmp_path: Path, zipped: bool) -> None:
    raw = export_zip(document()) if zipped else document()
    path = tmp_path / ("data.zip" if zipped else "data.xml")
    path.write_bytes(raw)
    before = path.stat().st_mtime_ns
    try:
        extracted(path)
    finally:
        assert (path.read_bytes(), path.stat().st_mtime_ns) == (raw, before)


def test_zip_bare_record_lines(tmp_path: Path) -> None:
    lines = []
    for name, raw in (("data.xml", document()), ("data.zip", export_zip(document()))):
        path = tmp_path / name
        path.write_bytes(raw)
        lines.append(gzip.decompress(extracted(path).getvalue()).splitlines()[1:])
    assert (len(lines[0]), lines[0] == lines[1]) == (12, True)


def test_utc_entry_order(tmp_path: Path) -> None:
    orders = []
    for index, stamp in enumerate(
        ("2024-03-01 01:00:00 +0900", "2024-02-29 20:00:00 -0800")
    ):
        path = tmp_path / f"{index}.xml"
        path.write_bytes(export_document([], export_date=stamp))
        orders.append(apple.entry_order(BytesIO(extracted(path).getvalue())))
    assert (orders, orders[0] < orders[1]) == (
        ["2024-02-29T16:00:00Z", "2024-03-01T04:00:00Z"],
        True,
    )


def test_header_only_entry_order(tmp_path: Path) -> None:
    path = tmp_path / "data.xml"
    path.write_bytes(document())
    first = gzip.decompress(extracted(path).getvalue()).splitlines()[0]
    corrupt = gzip.compress(first + b"\nnot JSON\n", mtime=0)
    assert apple.entry_order(BytesIO(corrupt)) == "2024-02-06T22:30:00Z"
