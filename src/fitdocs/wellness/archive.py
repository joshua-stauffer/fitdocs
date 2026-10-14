"""Archive layout, metadata listing and streamed write-once commits."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO

from fitdocs.layout import WELLNESS_ARCHIVE_DIR, wellness_archive_path
from fitdocs.wellness import registry
from fitdocs.wellness.model import DaySnapshot, accept_value, is_origin
from fitdocs.wellness.probe import CHUNK_BYTES, hash_file
from fitdocs.wellness.spec import (
    ExtractContext,
    FormatSpec,
    ParsedEntry,
    Supersession,
    WellnessFormatError,
)


@dataclass(frozen=True)
class ArchiveEntry:
    format: FormatSpec
    sha256: str
    path: Path
    ref: str


@dataclass(frozen=True)
class Orphan:
    ref: str
    reason: str


@dataclass(frozen=True)
class ArchiveListing:
    entries: tuple[ArchiveEntry, ...]
    orphans: tuple[Orphan, ...]


@dataclass(frozen=True)
class Committed:
    entry: ArchiveEntry
    snapshots: int


@dataclass(frozen=True)
class Exists:
    entry: ArchiveEntry


@dataclass(frozen=True)
class Changed:
    reason: str


@dataclass(frozen=True)
class Unreadable:
    reason: str


@dataclass(frozen=True)
class Invalid:
    reason: str


CommitResult = Committed | Exists | Changed | Unreadable | Invalid


def entry_ref(format: FormatSpec, sha256: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ValueError("archive sha256 must be 64 lowercase hex characters")
    return wellness_archive_path(
        Path(), format.id, sha256, format.archived_suffix
    ).as_posix()


def _entry(data_root: Path, format: FormatSpec, sha256: str) -> ArchiveEntry:
    ref = entry_ref(format, sha256)
    return ArchiveEntry(format, sha256, data_root / ref, ref)


def _file_count(directory: Path) -> int:
    count = 0
    for child in directory.iterdir():
        if child.is_symlink():
            continue
        if child.is_dir():
            count += _file_count(child)
        elif child.is_file():
            count += 1
    return count


def list_archive(data_root: Path) -> ArchiveListing:
    root = data_root / WELLNESS_ARCHIVE_DIR
    entries: list[ArchiveEntry] = []
    orphans: list[Orphan] = []

    def orphan(path: Path, reason: str) -> None:
        orphans.append(Orphan(path.relative_to(data_root).as_posix(), reason))

    if root.is_symlink():
        orphan(root, "symlink")
    elif root.exists():
        for directory in root.iterdir():
            if directory.name == "AGENTS.md" or directory.name.startswith("."):
                continue
            if directory.is_symlink():
                orphan(directory, "symlink")
                continue
            if not directory.is_dir():
                orphan(directory, "expected a format directory")
                continue
            format = registry.format_named(directory.name)
            if format is None:
                orphan(
                    directory,
                    f"unregistered format directory ({_file_count(directory)} files)",
                )
                continue
            pattern = re.compile(r"([0-9a-f]{64})" + re.escape(format.archived_suffix))
            for path in directory.iterdir():
                if path.name == "AGENTS.md" or path.name.startswith("."):
                    continue
                if path.is_symlink():
                    orphan(path, "symlink")
                    continue
                match = pattern.fullmatch(path.name)
                if path.is_file() and match is not None:
                    entries.append(_entry(data_root, format, match[1]))
                else:
                    orphan(
                        path,
                        "not a regular entry with the format's sha256 name and suffix",
                    )
    return ArchiveListing(
        tuple(sorted(entries, key=lambda entry: entry.ref)),
        tuple(sorted(orphans, key=lambda item: item.ref)),
    )


def _snapshots(format: FormatSpec, stream: BinaryIO) -> tuple[DaySnapshot, ...]:
    snapshots: list[DaySnapshot] = []
    for ordinal, snapshot in enumerate(format.parse(stream)):
        if not snapshot.values.keys() <= snapshot.covers:
            raise WellnessFormatError("snapshot values exceed its covers")
        if not snapshot.origins.keys() <= snapshot.values.keys():
            raise WellnessFormatError("snapshot origins exceed its values")
        if any(
            not isinstance(origin, str) or not is_origin(origin)
            for origin in snapshot.origins.values()
        ):
            raise WellnessFormatError("snapshot has an invalid origin")
        for metric, value in snapshot.values.items():
            try:
                accepted = accept_value(metric, value)
            except (TypeError, ValueError, KeyError) as error:
                raise WellnessFormatError("snapshot has an invalid value") from error
            if accepted is None or accepted != value:
                raise WellnessFormatError("snapshot has an invalid value")
        snapshots.append(replace(snapshot, ordinal=ordinal))
    return tuple(snapshots)


def _open_entry(entry: ArchiveEntry) -> BinaryIO:
    if entry.path.is_symlink():
        raise OSError("archive entry is a symlink")
    return entry.path.open("rb")


def parse_entry(entry: ArchiveEntry) -> ParsedEntry:
    with _open_entry(entry) as stream:
        snapshots = _snapshots(entry.format, stream)
    return ParsedEntry(
        entry.ref,
        entry.format.id,
        entry.format.source.id,
        entry.format.supersession,
        snapshots,
    )


def read_entry_order(entry: ArchiveEntry) -> str:
    order = entry.format.entry_order
    if order is None:
        raise WellnessFormatError("format does not declare entry order")
    with _open_entry(entry) as stream:
        return order(stream)


def _entry_exists(entry: ArchiveEntry) -> bool:
    if entry.path.is_symlink() or (entry.path.exists() and not entry.path.is_file()):
        raise OSError("occupied path is not a regular archive entry")
    return entry.path.is_file()


def _prepare(data_root: Path, entry: ArchiveEntry) -> bool:
    for directory in (data_root / WELLNESS_ARCHIVE_DIR, entry.path.parent):
        if directory.is_symlink():
            raise OSError("archive directory is a symlink")
        directory.mkdir(exist_ok=True)
    return _entry_exists(entry)


def _finish(temp: Path, entry: ArchiveEntry) -> CommitResult:
    parsed = parse_entry(replace(entry, path=temp))
    if entry.format.supersession is Supersession.LATEST_ENTRY:
        read_entry_order(replace(entry, path=temp))
    if _entry_exists(entry):
        return Exists(entry)
    os.replace(temp, entry.path)
    return Committed(entry, len(parsed.snapshots))


def commit_original(
    data_root: Path, format: FormatSpec, candidate: Path, expected_sha256: str
) -> CommitResult:
    entry = _entry(data_root, format, expected_sha256)
    temp: Path | None = None
    try:
        if _prepare(data_root, entry):
            return Exists(entry)
        descriptor, name = tempfile.mkstemp(
            prefix=".incoming-", suffix=".tmp", dir=entry.path.parent
        )
        temp = Path(name)
        digest = hashlib.sha256()
        if candidate.is_symlink():
            os.close(descriptor)
            raise OSError("candidate is a symlink")
        with os.fdopen(descriptor, "wb") as sink, candidate.open("rb") as stream:
            while chunk := stream.read(CHUNK_BYTES):
                sink.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            return Changed("candidate changed during the run")
        return _finish(temp, entry)
    except WellnessFormatError as error:
        return Invalid(str(error))
    except OSError as error:
        return Unreadable(str(error))
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def commit_extract(
    data_root: Path,
    format: FormatSpec,
    candidate: Path,
    expected_sha256: str,
    size: int,
    progress: Callable[[int, int], None] | None,
) -> CommitResult:
    entry = _entry(data_root, format, expected_sha256)
    temp: Path | None = None
    try:
        if _prepare(data_root, entry):
            return Exists(entry)
        if candidate.is_symlink():
            raise OSError("candidate is a symlink")
        descriptor, name = tempfile.mkstemp(
            prefix=".incoming-", suffix=".tmp", dir=entry.path.parent
        )
        temp = Path(name)
        extraction_error: Exception | None = None
        with os.fdopen(descriptor, "wb") as sink:
            try:
                if format.extract is None:
                    raise WellnessFormatError("format does not declare an extractor")
                format.extract(
                    candidate, sink, ExtractContext(expected_sha256, size, progress)
                )
            except Exception as error:
                extraction_error = error
        actual_sha256, _ = hash_file(candidate)
        if actual_sha256 != expected_sha256:
            return Changed("candidate changed during the run")
        if extraction_error is not None:
            raise extraction_error
        return _finish(temp, entry)
    except WellnessFormatError as error:
        return Invalid(str(error))
    except OSError as error:
        return Unreadable(str(error))
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
