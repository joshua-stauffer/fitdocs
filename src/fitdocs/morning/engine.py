"""Refresh existing workout pages from the current wellness series."""

import os
import tempfile
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from fitdocs import docio
from fitdocs.contract import (
    DOC_VERSION,
    document_date,
    document_version,
    is_workout_document,
)
from fitdocs.docmerge import RegionError
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.morning.block import MorningInputs, render_region
from fitdocs.morning.docedit import read_morning, replace_morning
from fitdocs.wellness import SeriesReadError, read_series


class PageOutcome(StrEnum):
    UPDATED = "updated"
    REMOVED = "removed"
    FAILED = "failed"


@dataclass(frozen=True)
class MorningPage:
    doc: str
    outcome: PageOutcome
    detail: str | None


@dataclass(frozen=True)
class MorningReport:
    pages: tuple[MorningPage, ...]
    unchanged: int
    without_region: int
    newer: int
    series_has_values: bool
    unavailable: str | None

    @property
    def failed(self) -> bool:
        return any(page.outcome == PageOutcome.FAILED for page in self.pages)


def run_morning_pass(data_root: Path) -> MorningReport:
    try:
        series = read_series(data_root)
    except SeriesReadError as exc:
        return MorningReport((), 0, 0, 0, False, str(exc))

    inputs = MorningInputs.of(series)
    rendered: dict[date | None, str] = {}
    pages: list[MorningPage] = []
    unchanged = without_region = newer = 0
    for path in sorted((data_root / WORKOUTS_DIR).glob("*.md")):
        doc = path.relative_to(data_root).as_posix()
        try:
            document = docio.read_document(path)
            if document is None or not is_workout_document(document.frontmatter):
                continue
            version = document_version(document.frontmatter or {})
            if version is not None and version > DOC_VERSION:
                newer += 1
                continue
            current = read_morning(document.text)
            if current is None:
                without_region += 1
                continue
            day = document_date(document.frontmatter)
            if day not in rendered:
                rendered[day] = render_region(
                    inputs.block(day)
                    if day is not None and not series.is_empty()
                    else None
                )
            fresh = rendered[day]
            if fresh == current:
                unchanged += 1
                continue
            _atomic_write(path, replace_morning(document.text, fresh))
            pages.append(
                MorningPage(
                    doc, PageOutcome.UPDATED if fresh else PageOutcome.REMOVED, None
                )
            )
        except (RegionError, OSError) as exc:
            pages.append(MorningPage(doc, PageOutcome.FAILED, str(exc)))
        except Exception as exc:
            pages.append(
                MorningPage(doc, PageOutcome.FAILED, f"{type(exc).__name__}: {exc}")
            )
    return MorningReport(
        tuple(pages), unchanged, without_region, newer, not series.is_empty(), None
    )


def _atomic_write(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=".morning-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
