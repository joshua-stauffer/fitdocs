"""Apple Health source, format declaration and composition."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Final

from fitdocs.wellness.formats.apple.extract import (
    read_header,
    read_records,
    write_extract,
)
from fitdocs.wellness.formats.apple.reader import (
    iter_items,
    looks_like_export_document,
    main_member,
    open_main_document,
)
from fitdocs.wellness.formats.apple.reduce import POLICIES, DayReducer
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import (
    ArchiveForm,
    ExtractContext,
    FormatSpec,
    SourceKind,
    SourceSpec,
    Supersession,
)

FORMAT_ID: Final[str] = "apple-health"
ARCHIVED_SUFFIX: Final[str] = ".jsonl.gz"
RULES_VERSION: Final[int] = 1
METRICS: Final[frozenset[Metric]] = frozenset(
    metric for policy in POLICIES.values() for metric in policy.metrics
)
SOURCE: Final[SourceSpec] = SourceSpec("apple-health", "Apple Health", SourceKind.HUB)


def recognize(probe: CandidateProbe) -> bool:
    if probe.suffix == ".zip":
        members = probe.zip_members()
        return members is not None and main_member(members) is not None
    if probe.suffix == ".xml":
        return looks_like_export_document(probe.head)
    return False


def extract(candidate: Path, sink: BinaryIO, context: ExtractContext) -> None:
    with open_main_document(candidate) as document:
        write_extract(
            sink,
            iter_items(document, progress=context.progress),
            original_sha256=context.expected_sha256,
            original_size=context.size,
        )


def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
    reducer = DayReducer()
    for record in read_records(stream):
        reducer.add(record)
    yield from reducer.snapshots()


def entry_order(stream: BinaryIO) -> str:
    return read_header(stream).export_date_utc


FORMAT: Final[FormatSpec] = FormatSpec(
    FORMAT_ID,
    "Apple Health export",
    SOURCE,
    frozenset({".zip", ".xml"}),
    ArchiveForm.EXTRACT,
    ARCHIVED_SUFFIX,
    RULES_VERSION,
    METRICS,
    recognize,
    parse,
    supersession=Supersession.LATEST_ENTRY,
    extract=extract,
    entry_order=entry_order,
)
