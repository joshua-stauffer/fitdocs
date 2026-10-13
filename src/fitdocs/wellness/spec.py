"""Declarations and exchange types shared by wellness formats."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe


class SourceKind(StrEnum):
    DEVICE = "device"
    HUB = "hub"
    RELAY = "relay"


@dataclass(frozen=True)
class SourceSpec:
    id: str
    display_name: str
    kind: SourceKind


class ArchiveForm(StrEnum):
    ORIGINAL = "original"
    EXTRACT = "extract"


class Supersession(StrEnum):
    NONE = "none"
    LATEST_ENTRY = "latest-entry"


class WellnessFormatError(Exception):
    """The bytes are not a valid instance of the format (source-level)."""


@dataclass(frozen=True)
class ExtractContext:
    expected_sha256: str
    size: int
    progress: Callable[[int, int], None] | None


@dataclass(frozen=True)
class FormatSpec:
    id: str
    display_name: str
    source: SourceSpec
    suffixes: frozenset[str]
    archive_form: ArchiveForm
    archived_suffix: str
    rules_version: int
    metrics: frozenset[Metric]
    recognize: Callable[[CandidateProbe], bool]
    parse: Callable[[BinaryIO], Iterator[DaySnapshot]]
    supersession: Supersession = Supersession.NONE
    extract: Callable[[Path, BinaryIO, ExtractContext], None] | None = None
    entry_order: Callable[[BinaryIO], str] | None = None


@dataclass(frozen=True)
class ParsedEntry:
    entry_ref: str
    format_id: str
    source_id: str
    supersession: Supersession
    snapshots: tuple[DaySnapshot, ...]
