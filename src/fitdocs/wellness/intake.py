"""Per-candidate wellness intake outcomes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fitdocs.layout import WELLNESS_ARCHIVE_DIR
from fitdocs.wellness import archive
from fitdocs.wellness.archive import ArchiveEntry
from fitdocs.wellness.formats.intervals import DELIVERY_FORMAT, DELIVERY_VERSION
from fitdocs.wellness.probe import CandidateProbe, hash_file
from fitdocs.wellness.registry import NotRecognized, recognize
from fitdocs.wellness.spec import ArchiveForm, FormatSpec


@dataclass(frozen=True)
class Identified:
    format: FormatSpec
    sha256: str
    size: int


@dataclass(frozen=True)
class IntakeUnrecognized:
    reason: str


@dataclass(frozen=True)
class IntakeDeferred:
    reason: str


@dataclass(frozen=True)
class Archived:
    entry: ArchiveEntry


@dataclass(frozen=True)
class AlreadyArchived:
    entry: ArchiveEntry


@dataclass(frozen=True)
class Failed:
    reason: str


def identify(path: Path) -> Identified | IntakeUnrecognized | IntakeDeferred:
    try:
        probe = CandidateProbe.open(path)
        recognized = recognize(probe)
        if isinstance(recognized, NotRecognized):
            payload = probe.json() if probe.suffix == ".json" else None
            if (
                isinstance(payload, dict)
                and payload.get("format") == DELIVERY_FORMAT
                and payload.get("version") != DELIVERY_VERSION
            ):
                return IntakeUnrecognized(
                    "written by a newer fitdocs "
                    f"(delivery version {payload.get('version')})"
                )
            return IntakeUnrecognized(recognized.reason)
        sha256, size = hash_file(path)
        return Identified(recognized.format, sha256, size)
    except OSError as error:
        return IntakeDeferred(
            f"could not be read ({error}); left in place and retried on a later drain"
        )


def archive_identified(
    data_root: Path,
    path: Path,
    identified: Identified,
    progress: Callable[[int, int], None] | None,
) -> Archived | AlreadyArchived | IntakeDeferred | Failed:
    ref = archive.entry_ref(identified.format, identified.sha256)
    entry = ArchiveEntry(identified.format, identified.sha256, data_root / ref, ref)
    try:
        for directory in (data_root / WELLNESS_ARCHIVE_DIR, entry.path.parent):
            if directory.is_symlink():
                raise OSError("archive directory is a symlink")
        if entry.path.is_symlink() or (
            entry.path.exists() and not entry.path.is_file()
        ):
            raise OSError("occupied path is not a regular archive entry")
        if entry.path.is_file():
            return AlreadyArchived(entry)
    except OSError as error:
        return IntakeDeferred(str(error))
    if identified.format.archive_form is ArchiveForm.ORIGINAL:
        result = archive.commit_original(
            data_root, identified.format, path, identified.sha256
        )
    else:
        result = archive.commit_extract(
            data_root,
            identified.format,
            path,
            identified.sha256,
            identified.size,
            progress,
        )
    if isinstance(result, archive.Committed):
        return Archived(result.entry)
    if isinstance(result, archive.Exists):
        return AlreadyArchived(result.entry)
    if isinstance(result, (archive.Changed, archive.Unreadable)):
        return IntakeDeferred(result.reason)
    return Failed(result.reason)
