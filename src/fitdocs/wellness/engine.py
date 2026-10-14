"""Assess and atomically rebuild the derived wellness series."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fitdocs.wellness.archive import (
    ArchiveListing,
    list_archive,
    parse_entry,
    read_entry_order,
)
from fitdocs.wellness.merge import merge
from fitdocs.wellness.model import Metric, SeriesValue
from fitdocs.wellness.series import (
    SERIES_HEADER,
    Manifest,
    ManifestEntry,
    ManifestFile,
    NewerSeries,
    SeriesReadError,
    decode_manifest,
    decode_year,
    encode_manifest,
    encode_year,
    inputs_digest,
)
from fitdocs.wellness.settings import WellnessSettings, effective_order
from fitdocs.wellness.spec import ParsedEntry, Supersession, WellnessFormatError


class SeriesStatus(StrEnum):
    UNCHANGED = "unchanged"
    REBUILT = "rebuilt"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class SeriesNote:
    subject: str
    detail: str


@dataclass(frozen=True)
class SeriesReport:
    status: SeriesStatus
    written: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    values_added: int = 0
    values_changed: int = 0
    values_removed: int = 0
    canonical_days_changed: int = 0
    conflicts: int = 0
    notes: tuple[SeriesNote, ...] = ()


@dataclass(frozen=True)
class SeriesAssessment:
    fresh: bool
    reasons: tuple[str, ...]
    blocked: tuple[SeriesNote, ...]
    unreadable: tuple[SeriesNote, ...]


def _ref(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


@dataclass
class _Current:
    data: dict[str, bytes]
    manifest: Manifest | None
    blocked: list[SeriesNote]
    unreadable: list[SeriesNote]


def _current(root: Path) -> _Current:
    result = _Current({}, None, [], [])
    directory = root / "wellness"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        result.blocked.append(SeriesNote("wellness", "occupied series directory"))
        return result
    try:
        paths = sorted(directory.iterdir()) if directory.exists() else []
    except OSError as exc:
        result.unreadable.append(SeriesNote("wellness", str(exc)))
        return result
    for path in paths:
        if (
            path.name != "manifest.toml"
            and re.fullmatch(r"[0-9]{4}\.csv", path.name) is None
        ):
            continue
        ref = _ref(root, path)
        if path.is_symlink() or not path.is_file():
            result.blocked.append(SeriesNote(ref, "occupied series path"))
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            result.unreadable.append(SeriesNote(ref, str(exc)))
            continue
        result.data[ref] = data
        if path.name == "manifest.toml":
            try:
                decoded = decode_manifest(path, data)
                if isinstance(decoded, NewerSeries):
                    result.blocked.append(SeriesNote(ref, "written by a newer fitdocs"))
                else:
                    result.manifest = decoded
            except (ValueError, SeriesReadError) as exc:
                result.blocked.append(SeriesNote(ref, str(exc)))
        elif data.split(b"\n", 1)[0] != SERIES_HEADER.encode("utf-8"):
            result.blocked.append(
                SeriesNote(ref, "foreign year file: wrong series header")
            )
    return result


def _assessment(
    current: _Current, listing: ArchiveListing, settings: WellnessSettings
) -> SeriesAssessment:
    reasons: list[str] = []
    manifest = current.manifest
    years = set(current.data) - {"wellness/manifest.toml"}
    if manifest is None:
        if listing.entries or years:
            reasons.append("series manifest is missing")
    else:
        if not listing.entries:
            reasons.append("archive is empty")
        if manifest.inputs != inputs_digest(listing, settings):
            reasons.append("archive, parsing rules or precedence changed")
        if years != {item.path for item in manifest.files}:
            reasons.append("series year files differ from manifest")
        for item in manifest.files:
            data = current.data.get(item.path)
            if data is None or hashlib.sha256(data).hexdigest() != item.sha256:
                reasons.append(f"{item.path}: missing or changed")
    return SeriesAssessment(
        not (reasons or current.blocked or current.unreadable),
        tuple(reasons),
        tuple(current.blocked),
        tuple(current.unreadable),
    )


def assess_series(
    data_root: Path, listing: ArchiveListing, settings: WellnessSettings
) -> SeriesAssessment:
    return _assessment(_current(data_root), listing, settings)


def _counts(
    old: tuple[SeriesValue, ...], new: tuple[SeriesValue, ...]
) -> tuple[int, int, int, int]:
    def values(
        items: tuple[SeriesValue, ...],
    ) -> dict[tuple[object, ...], tuple[object, ...]]:
        return {(v.day, v.metric, v.source): (v.value, v.origin) for v in items}

    before, after = values(old), values(new)
    old_canonical = {
        (v.day, v.metric): (v.source, v.value, v.origin) for v in old if v.canonical
    }
    new_canonical = {
        (v.day, v.metric): (v.source, v.value, v.origin) for v in new if v.canonical
    }
    days = {
        key[0]
        for key in old_canonical.keys() | new_canonical.keys()
        if old_canonical.get(key) != new_canonical.get(key)
    }
    return (
        len(after.keys() - before.keys()),
        sum(before[key] != after[key] for key in before.keys() & after.keys()),
        len(before.keys() - after.keys()),
        len(days),
    )


def _write(root: Path, changed: dict[str, bytes], removed: tuple[str, ...]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        if changed:
            (root / "wellness").mkdir(exist_ok=True)
        for ref, data in changed.items():
            path = root / ref
            descriptor, name = tempfile.mkstemp(
                prefix=".series-", suffix=".tmp", dir=path.parent
            )
            temp = Path(name)
            staged.append((temp, path))
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
        for ref in removed:
            (root / ref).unlink()
        for temp, path in staged:
            os.replace(temp, path)
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)


def rebuild_series(
    data_root: Path, *, settings: WellnessSettings, force: bool
) -> SeriesReport:
    try:
        listing = list_archive(data_root)
    except OSError as exc:
        return SeriesReport(
            SeriesStatus.DEFERRED, notes=(SeriesNote("wellness-archive", str(exc)),)
        )
    current = _current(data_root)
    assessment = _assessment(current, listing, settings)
    if assessment.blocked:
        return SeriesReport(SeriesStatus.BLOCKED, notes=assessment.blocked)
    if assessment.unreadable:
        return SeriesReport(SeriesStatus.DEFERRED, notes=assessment.unreadable)
    if assessment.fresh and not force:
        return SeriesReport(
            SeriesStatus.UNCHANGED,
            conflicts=len(current.manifest.conflicts) if current.manifest else 0,
        )
    old: list[SeriesValue] = []
    for ref, data in current.data.items():
        if ref != "wellness/manifest.toml":
            try:
                old.extend(decode_year(data_root / ref, data))
            except SeriesReadError as exc:
                return SeriesReport(
                    SeriesStatus.DEFERRED, notes=(SeriesNote(ref, exc.reason),)
                )
    parsed: list[ParsedEntry] = []
    entries: list[ManifestEntry] = []
    unreadable: list[SeriesNote] = []
    invalid: list[SeriesNote] = []
    groups = defaultdict(list)
    for entry in listing.entries:
        groups[entry.format.id].append(entry)
    for group in groups.values():
        selected = group
        if group[0].format.supersession is Supersession.LATEST_ENTRY:
            ordered = []
            for entry in group:
                try:
                    ordered.append((read_entry_order(entry), entry.ref, entry))
                except OSError as exc:
                    unreadable.append(SeriesNote(entry.ref, str(exc)))
                except WellnessFormatError as exc:
                    invalid.append(SeriesNote(entry.ref, str(exc)))
            if len(ordered) != len(group):
                continue
            selected = [max(ordered, key=lambda item: (item[0], item[1]))[2]]
        selected_refs = {entry.ref for entry in selected}
        entries.extend(
            ManifestEntry(
                entry.ref,
                entry.format.id,
                entry.format.rules_version,
                "contributed" if entry.ref in selected_refs else "superseded",
            )
            for entry in group
        )
        for entry in selected:
            try:
                parsed.append(parse_entry(entry))
            except OSError as exc:
                unreadable.append(SeriesNote(entry.ref, str(exc)))
            except WellnessFormatError as exc:
                invalid.append(SeriesNote(entry.ref, str(exc)))
    if invalid or unreadable:
        return SeriesReport(
            SeriesStatus.FAILED if invalid else SeriesStatus.DEFERRED,
            notes=tuple(sorted(invalid + unreadable, key=lambda note: note.subject)),
        )
    merged = merge(parsed, order_for=lambda metric: effective_order(settings, metric))
    output: dict[str, bytes] = {}
    for year in sorted({value.day.year for value in merged.values}):
        output[f"wellness/{year:04d}.csv"] = encode_year(
            value for value in merged.values if value.day.year == year
        )
    if listing.entries:
        default_order = effective_order(
            WellnessSettings(settings.precedence, {}), Metric.RESTING_HR_BPM
        )
        orders = {
            metric: effective_order(settings, metric)
            for metric in Metric
            if effective_order(settings, metric) != default_order
        }
        output["wellness/manifest.toml"] = encode_manifest(
            Manifest(
                inputs_digest(listing, settings),
                default_order,
                orders,
                tuple(
                    ManifestFile(
                        ref,
                        hashlib.sha256(data).hexdigest(),
                        sum(
                            value.day.year == int(Path(ref).stem)
                            for value in merged.values
                        ),
                    )
                    for ref, data in output.items()
                ),
                tuple(entries),
                merged.conflicts,
            )
        )
    changed = {
        ref: data for ref, data in output.items() if current.data.get(ref) != data
    }
    removed = tuple(sorted(current.data.keys() - output.keys()))
    added, updated, deleted, canonical = _counts(tuple(old), merged.values)
    destinations = _current(data_root)
    if destinations.blocked:
        return SeriesReport(SeriesStatus.BLOCKED, notes=tuple(destinations.blocked))
    if destinations.unreadable:
        return SeriesReport(SeriesStatus.DEFERRED, notes=tuple(destinations.unreadable))
    try:
        _write(data_root, changed, removed)
    except OSError as exc:
        return SeriesReport(
            SeriesStatus.DEFERRED, notes=(SeriesNote("wellness", str(exc)),)
        )
    return SeriesReport(
        SeriesStatus.REBUILT if changed or removed else SeriesStatus.UNCHANGED,
        tuple(changed),
        removed,
        added,
        updated,
        deleted,
        canonical,
        len(merged.conflicts),
    )
