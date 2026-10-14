"""Deterministic wellness series codecs and the shared read interface."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

import tomli_w

from fitdocs.wellness import registry
from fitdocs.wellness.archive import ArchiveListing
from fitdocs.wellness.merge import Conflict
from fitdocs.wellness.model import Metric, SeriesValue, is_origin
from fitdocs.wellness.settings import WellnessSettings, effective_order

SERIES_VERSION: Final = 1
SERIES_HEADER: Final = "day,metric,source,origin,value,canonical"


class SeriesReadError(Exception):
    def __init__(self, path: Path, line: int | None, reason: str) -> None:
        self.path = str(path)
        self.line = line
        self.reason = reason
        super().__init__(f"{path}{f':{line}' if line is not None else ''}: {reason}")


def format_value(value: float) -> str:
    number = float(value)
    return (
        str(int(number))
        if number.is_integer() and abs(number) < 2**53
        else repr(number)
    )


def encode_year(values: Iterable[SeriesValue]) -> bytes:
    lines = [SERIES_HEADER]
    for value in sorted(
        values, key=lambda value: (value.day, value.metric.value, value.source)
    ):
        lines.append(
            f"{value.day.isoformat()},{value.metric.value},{value.source},"
            f"{value.origin or ''},{format_value(value.value)},"
            f"{str(value.canonical).lower()}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def decode_year(path: Path, data: bytes) -> tuple[SeriesValue, ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SeriesReadError(path, 1, "invalid UTF-8") from exc
    lines = text.split("\n")
    if lines[0] != SERIES_HEADER:
        raise SeriesReadError(path, 1, "wrong series header")
    if not text.endswith("\n") or "\r" in text:
        raise SeriesReadError(path, len(lines), "expected LF-terminated lines")
    values: list[SeriesValue] = []
    for number, line in enumerate(lines[1:-1], 2):
        try:
            day_text, metric_text, source, origin, number_text, canonical = line.split(
                ","
            )
            day = date.fromisoformat(day_text)
            if day.isoformat() != day_text:
                raise ValueError("non-ISO day")
            metric = Metric(metric_text)
            if not is_origin(source) or (origin and not is_origin(origin)):
                raise ValueError("invalid source or origin token")
            value = float(number_text)
            if not math.isfinite(value) or format_value(value) != number_text:
                raise ValueError("noncanonical numeric value")
            if canonical not in ("true", "false"):
                raise ValueError("canonical must be true or false")
            item = SeriesValue(
                day, metric, source, origin or None, value, canonical == "true"
            )
            if values and (item.day, item.metric, item.source) <= (
                values[-1].day,
                values[-1].metric,
                values[-1].source,
            ):
                raise ValueError("rows must be unique and sorted")
            values.append(item)
        except ValueError as exc:
            raise SeriesReadError(path, number, str(exc)) from exc
    return tuple(values)


@dataclass(frozen=True)
class ManifestFile:
    path: str
    sha256: str
    values: int


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    format: str
    rules_version: int
    state: str


@dataclass(frozen=True)
class Manifest:
    inputs: str
    default_order: tuple[str, ...] = ()
    metric_orders: Mapping[Metric, tuple[str, ...]] = field(default_factory=dict)
    files: tuple[ManifestFile, ...] = ()
    entries: tuple[ManifestEntry, ...] = ()
    conflicts: tuple[Conflict, ...] = ()


@dataclass(frozen=True)
class NewerSeries:
    series_version: int


def encode_manifest(manifest: Manifest) -> bytes:
    document: dict[str, Any] = {
        "generator": "fitdocs",
        "series_version": SERIES_VERSION,
        "inputs": manifest.inputs,
        "precedence": {
            "default": list(manifest.default_order),
            "metrics": {
                metric.value: list(order)
                for metric, order in sorted(manifest.metric_orders.items())
            },
        },
        "files": [
            {"path": item.path, "sha256": item.sha256, "values": item.values}
            for item in sorted(manifest.files, key=lambda item: item.path)
        ],
        "entries": [
            {
                "path": item.path,
                "format": item.format,
                "rules_version": item.rules_version,
                "state": item.state,
            }
            for item in sorted(manifest.entries, key=lambda item: item.path)
        ],
        "conflicts": [
            {
                "day": item.day,
                "metric": item.metric.value,
                "source": item.source,
                "kept_entry": item.kept_entry,
                "kept_value": item.kept_value,
                "other_entries": [ref for ref, _ in item.others],
                "other_values": [value for _, value in item.others],
            }
            for item in sorted(
                manifest.conflicts,
                key=lambda item: (item.day, item.metric, item.source),
            )
        ],
    }
    return tomli_w.dumps(document).encode("utf-8")


def _string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("expected string")
    return value


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("expected nonnegative integer")
    return value


def _order(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("expected source order array")
    result = tuple(_string(source) for source in value)
    if len(set(result)) != len(result) or any(
        not is_origin(source) for source in result
    ):
        raise ValueError("invalid source order")
    return result


def decode_manifest(path: Path, data: bytes) -> Manifest | NewerSeries:
    try:
        document = tomllib.loads(data.decode("utf-8"))
        if document["generator"] != "fitdocs":
            raise ValueError("wrong generator")
        version = _integer(document["series_version"])
        if version > SERIES_VERSION:
            return NewerSeries(version)
        if version != SERIES_VERSION:
            raise ValueError("unsupported series version")
        precedence = document["precedence"]
        files = tuple(
            ManifestFile(
                _string(item["path"]), _string(item["sha256"]), _integer(item["values"])
            )
            for item in document["files"]
        )
        if len({item.path for item in files}) != len(files):
            raise ValueError("duplicate year file")
        for item in files:
            if re.fullmatch(r"wellness/[0-9]{4}\.csv", item.path) is None:
                raise ValueError("invalid series file path")
            if re.fullmatch(r"[0-9a-f]{64}", item.sha256) is None:
                raise ValueError("invalid file digest")
        entries = tuple(
            ManifestEntry(
                _string(item["path"]),
                _string(item["format"]),
                _integer(item["rules_version"]),
                _string(item["state"]),
            )
            for item in document["entries"]
        )
        if any(item.state not in ("contributed", "superseded") for item in entries):
            raise ValueError("invalid entry state")
        conflicts = []
        for item in document["conflicts"]:
            if type(item["day"]) is not date:
                raise ValueError("expected conflict date")
            conflicts.append(
                Conflict(
                    item["day"],
                    Metric(item["metric"]),
                    _string(item["source"]),
                    _string(item["kept_entry"]),
                    float(item["kept_value"]),
                    tuple(
                        (_string(ref), float(value))
                        for ref, value in zip(
                            item["other_entries"], item["other_values"], strict=True
                        )
                    ),
                )
            )
        return Manifest(
            _string(document["inputs"]),
            _order(precedence["default"]),
            {
                Metric(metric): _order(order)
                for metric, order in precedence["metrics"].items()
            },
            files,
            entries,
            tuple(conflicts),
        )
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise SeriesReadError(path, None, f"invalid manifest: {exc}") from exc


@dataclass(frozen=True)
class WellnessSeries:
    values: tuple[SeriesValue, ...] = ()

    def is_empty(self) -> bool:
        return not self.values

    def days(self) -> tuple[date, ...]:
        return tuple(sorted({value.day for value in self.values}))

    def for_day(self, day: date) -> tuple[SeriesValue, ...]:
        return tuple(value for value in self.values if value.day == day)

    def canonical(self, metric: Metric, day: date) -> SeriesValue | None:
        return next(
            (
                value
                for value in self.for_day(day)
                if value.metric == metric and value.canonical
            ),
            None,
        )

    def value(self, metric: Metric, day: date, source: str) -> SeriesValue | None:
        return next(
            (
                value
                for value in self.for_day(day)
                if value.metric == metric and value.source == source
            ),
            None,
        )

    def sources(self, metric: Metric) -> tuple[str, ...]:
        return tuple(
            sorted({value.source for value in self.values if value.metric == metric})
        )

    def by_source(self, metric: Metric, source: str) -> tuple[SeriesValue, ...]:
        return tuple(
            value
            for value in self.values
            if value.metric == metric and value.source == source
        )

    def canonical_series(self, metric: Metric) -> tuple[SeriesValue, ...]:
        return tuple(
            value for value in self.values if value.metric == metric and value.canonical
        )


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SeriesReadError(path, None, str(exc)) from exc


def _manifest(data_root: Path) -> Manifest | None:
    path = data_root / "wellness/manifest.toml"
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SeriesReadError(path, None, str(exc)) from exc
    manifest = decode_manifest(path, data)
    if isinstance(manifest, NewerSeries):
        raise SeriesReadError(
            path, None, f"newer series version {manifest.series_version}"
        )
    return manifest


def read_series(data_root: Path) -> WellnessSeries:
    manifest = _manifest(data_root)
    if manifest is None:
        return WellnessSeries()
    values = tuple(
        value
        for item in manifest.files
        for value in decode_year(data_root / item.path, _read(data_root / item.path))
    )
    return WellnessSeries(
        tuple(sorted(values, key=lambda value: (value.day, value.metric, value.source)))
    )


def series_files(data_root: Path) -> tuple[Path, ...]:
    manifest = _manifest(data_root)
    if manifest is None:
        return ()
    return (
        data_root / "wellness/manifest.toml",
        *(
            data_root / item.path
            for item in manifest.files
            if (data_root / item.path).exists()
        ),
    )


def inputs_digest(listing: ArchiveListing, settings: WellnessSettings) -> str:
    document = {
        "series_version": SERIES_VERSION,
        "formats": sorted([[form.id, form.rules_version] for form in registry.FORMATS]),
        "entries": sorted(entry.ref for entry in listing.entries),
        "precedence": {
            metric.value: list(effective_order(settings, metric)) for metric in Metric
        },
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
