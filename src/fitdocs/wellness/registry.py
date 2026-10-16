"""Wellness declarations, validation and content recognition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from fitdocs.wellness.formats import apple, garmin, intervals
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import (
    ArchiveForm,
    FormatSpec,
    SourceKind,
    SourceSpec,
    Supersession,
)

SOURCES: Final[tuple[SourceSpec, ...]] = (intervals.SOURCE, garmin.SOURCE, apple.SOURCE)
FORMATS: Final[tuple[FormatSpec, ...]] = (
    intervals.FORMAT,
    garmin.UDS_FORMAT,
    garmin.SLEEP_FORMAT,
    garmin.MAXMET_FORMAT,
    garmin.BIOMETRICS_FORMAT,
    apple.FORMAT,
)


@dataclass(frozen=True)
class Recognized:
    format: FormatSpec


@dataclass(frozen=True)
class NotRecognized:
    reason: str


def recognize(probe: CandidateProbe) -> Recognized | NotRecognized:
    claims: list[FormatSpec] = []
    for form in FORMATS:
        if probe.suffix not in form.suffixes:
            continue
        try:
            if form.recognize(probe):
                claims.append(form)
        except OSError:
            raise
        except Exception:
            continue
    if len(claims) == 1:
        return Recognized(claims[0])
    if not claims:
        return NotRecognized("no supported wellness format reads this file")
    return NotRecognized(
        "multiple wellness formats read this file: "
        + ", ".join(form.id for form in claims)
    )


def format_named(format_id: str) -> FormatSpec | None:
    return next((form for form in FORMATS if form.id == format_id), None)


def source_named(source_id: str) -> SourceSpec | None:
    return next((source for source in SOURCES if source.id == source_id), None)


def candidate_suffixes() -> frozenset[str]:
    return frozenset(suffix for form in FORMATS for suffix in form.suffixes)


def default_source_order() -> tuple[str, ...]:
    ranks = {SourceKind.DEVICE: 0, SourceKind.HUB: 1, SourceKind.RELAY: 2}
    return tuple(
        source.id
        for source in sorted(
            SOURCES, key=lambda source: (ranks[source.kind], source.id)
        )
    )


def validate_registry() -> None:
    for declarations in (SOURCES, FORMATS):
        seen: set[str] = set()
        for declaration in declarations:
            if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", declaration.id) is None:
                raise ValueError(f"invalid id {declaration.id!r}")
            if declaration.id in seen:
                raise ValueError(f"duplicate id {declaration.id!r}")
            seen.add(declaration.id)
    metrics_by_source: dict[str, set[object]] = {}
    for form in FORMATS:
        error: str | None = None
        if form.source not in SOURCES:
            error = "unknown source"
        elif any(
            suffix == ".fit" or suffix != suffix.lower() or not suffix.startswith(".")
            for suffix in form.suffixes
        ):
            error = "invalid suffix"
        elif (
            form.archive_form is ArchiveForm.ORIGINAL
            and form.archived_suffix not in form.suffixes
        ):
            error = "original archived suffix not recognized"
        elif form.archive_form is ArchiveForm.ORIGINAL and form.extract is not None:
            error = "original format has an extractor"
        elif form.archive_form is ArchiveForm.EXTRACT and form.extract is None:
            error = "extract format needs an extractor"
        elif (
            form.supersession is Supersession.LATEST_ENTRY and form.entry_order is None
        ):
            error = "latest-entry format needs entry_order"
        elif form.rules_version < 1:
            error = "rules_version must be at least 1"
        used = metrics_by_source.setdefault(form.source.id, set())
        if error is None and used.intersection(form.metrics):
            error = "overlapping metrics within source"
        if error is not None:
            raise ValueError(f"format {form.id!r}: {error}")
        used.update(form.metrics)
