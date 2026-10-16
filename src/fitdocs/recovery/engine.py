"""Read, compute, write and report the recovery page."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from fitdocs.contract import GENERATED_PREFIX, is_generated
from fitdocs.declaration import ensure_declarations
from fitdocs.history import compute_history, read_history_inputs
from fitdocs.layout import (
    RECOVERY_ASSETS_SUBDIR,
    RECOVERY_DIR,
    recovery_asset_path,
    recovery_doc_path,
)
from fitdocs.recovery.baselines import Baselines
from fitdocs.recovery.charts import CHART_NAMES, render_charts
from fitdocs.recovery.page import render_page
from fitdocs.recovery.view import build_view
from fitdocs.render.charts.kit import describe_kinds
from fitdocs.wellness import SeriesReadError, read_series


class FileOutcome(StrEnum):
    """The action taken for a recovery output."""

    WRITTEN = "written"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FOREIGN = "foreign"
    FAILED = "failed"


@dataclass(frozen=True)
class FileResult:
    """One data-root-relative POSIX path and its outcome."""

    path: str
    outcome: FileOutcome
    detail: str | None


@dataclass(frozen=True)
class RecoveryReport:
    """The data window, selected methodology and ordered file outcomes."""

    as_of: date | None
    window_start: date | None
    methodology: str | None
    files: tuple[FileResult, ...]
    note: str | None
    failure: str | None

    @property
    def failed(self) -> bool:
        return self.failure is not None or any(
            item.outcome == FileOutcome.FAILED for item in self.files
        )


def _existing(path: Path) -> tuple[bool, bytes | None]:
    """Classify an occupant without following a symlink."""
    if path.is_symlink():
        return True, None
    if path.exists() and not path.is_file():
        return True, None
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except FileNotFoundError:
        return False, None
    except (OSError, UnicodeDecodeError):
        return True, None
    return not is_generated(text), data


def _atomic_write(path: Path, data: bytes) -> None:
    """Replace a whole file using a temporary in its own directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=".recovery-", suffix=".tmp"
    )
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _reason(exc: OSError) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _write_if_changed(root: Path, path: Path, text: str) -> FileResult:
    relative = path.relative_to(root).as_posix()
    foreign, existing = _existing(path)
    if foreign:
        return FileResult(
            relative, FileOutcome.FOREIGN, "foreign occupant; left untouched"
        )
    data = text.encode("utf-8")
    if existing == data:
        return FileResult(relative, FileOutcome.UNCHANGED, None)
    try:
        _atomic_write(path, data)
    except OSError as exc:
        return FileResult(relative, FileOutcome.FAILED, _reason(exc))
    return FileResult(relative, FileOutcome.WRITTEN, None)


def run_recovery(data_root: Path, *, methodology: str | None = None) -> RecoveryReport:
    """Rebuild recovery outputs from the public wellness and history readers."""
    try:
        series = read_series(data_root)
    except SeriesReadError as exc:
        return RecoveryReport(
            None,
            None,
            None,
            (),
            None,
            f"{exc}; run fitdocs sync or fitdocs regen to rebuild the wellness series",
        )
    if series.is_empty():
        return RecoveryReport(
            None,
            None,
            None,
            (),
            "The wellness series holds no value; nothing was written.",
            None,
        )

    inputs = read_history_inputs(data_root)
    computation = compute_history(inputs, methodology=methodology)
    panel_limit = next(
        item["bound"]["limit"]
        for item in describe_kinds()
        if item["name"] == "small-multiples"
    )
    view = build_view(
        series, Baselines.of(series), computation, panel_limit=panel_limit
    )
    assert view is not None
    charts = dict(render_charts(view))
    ordered_charts = tuple(
        (name, charts[name]) for name in CHART_NAMES if name in charts
    )
    page = render_page(view, ordered_charts)

    directory = data_root / RECOVERY_DIR
    for location in (directory, directory / RECOVERY_ASSETS_SUBDIR):
        if location.is_symlink() or (location.exists() and not location.is_dir()):
            return RecoveryReport(
                view.window.as_of,
                view.window.start,
                view.load.methodology,
                (
                    FileResult(
                        location.relative_to(data_root).as_posix(),
                        FileOutcome.FOREIGN,
                        "foreign location; left untouched",
                    ),
                ),
                None,
                None,
            )

    ensure_declarations(data_root)
    results: list[FileResult] = []
    for name, svg in ordered_charts:
        results.append(
            _write_if_changed(
                data_root,
                recovery_asset_path(data_root, name),
                f"{GENERATED_PREFIX} -->\n" + svg,
            )
        )
    page_path = recovery_doc_path(data_root)
    if any(item.outcome == FileOutcome.FAILED for item in results):
        results.append(
            FileResult(
                page_path.relative_to(data_root).as_posix(),
                FileOutcome.FAILED,
                "not written because a chart failed",
            )
        )
    else:
        results.append(_write_if_changed(data_root, page_path, page.markdown))

    for name in CHART_NAMES:
        if name in charts:
            continue
        path = recovery_asset_path(data_root, name)
        foreign, existing = _existing(path)
        relative = path.relative_to(data_root).as_posix()
        if foreign:
            results.append(
                FileResult(
                    relative, FileOutcome.FOREIGN, "foreign occupant; left untouched"
                )
            )
        elif existing is not None:
            try:
                path.unlink()
            except OSError as exc:
                results.append(FileResult(relative, FileOutcome.FAILED, _reason(exc)))
            else:
                results.append(FileResult(relative, FileOutcome.REMOVED, None))
    return RecoveryReport(
        view.window.as_of,
        view.window.start,
        view.load.methodology,
        tuple(results),
        None,
        None,
    )
