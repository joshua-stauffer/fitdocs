"""Settings and normalized wellness evidence for the heart-rate stage."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from fitdocs import FitDecodeError, docio, parse_fit
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.compose.archive import compose_listed
from fitdocs.contract import document_date, is_workout_document, sha_of_ref, source_refs
from fitdocs.layout import archive_path, settings_path, wellness_series_path
from fitdocs.load.settings import LoadSettings, load_load_settings
from fitdocs.wellness import (
    Metric,
    SeriesReadError,
    effective_order,
    load_wellness_settings,
    read_series,
)

from .maximum import max_evidence
from .peaks import session_peak
from .resting import resting_evidence
from .types import Evidence, HrFailure, NoEvidenceReason, SessionPeak, SkippedDocument


@dataclass(frozen=True)
class HrStageSettings:
    load: LoadSettings
    resting_order: tuple[str, ...]


def load_hr_stage_settings(
    document: Mapping[str, object], *, data_root: Path
) -> HrStageSettings:
    wellness = load_wellness_settings(document, data_root=data_root)
    return HrStageSettings(
        load=load_load_settings(document, settings_path(data_root)),
        resting_order=effective_order(wellness, Metric.RESTING_HR_BPM),
    )


@dataclass(frozen=True)
class _RestingSeries:
    evidence: tuple[Evidence, ...]
    kept: bool
    failures: tuple[HrFailure, ...]
    notes: tuple[str, ...]


def _read_resting_series(data_root: Path, settings: HrStageSettings) -> _RestingSeries:
    try:
        series = read_series(data_root)
    except SeriesReadError as exc:
        return _RestingSeries(
            (),
            True,
            (
                HrFailure(
                    BenchmarkKind.RESTING_HR_BPM, "wellness/manifest.toml", str(exc)
                ),
            ),
            (),
        )
    values = {
        source: {
            item.day: item.value
            for item in series.by_source(Metric.RESTING_HR_BPM, source)
        }
        for source in series.sources(Metric.RESTING_HR_BPM)
    }
    if not any(values.values()):
        return _RestingSeries(
            (),
            True,
            (),
            (
                "the wellness series holds no resting heart rate; "
                "derived resting entries kept as on file",
            ),
        )
    evidence = resting_evidence(
        values,
        order=settings.resting_order,
        series_metric=Metric.RESTING_HR_BPM.value,
        document_for_year=lambda year: (
            wellness_series_path(data_root, year).relative_to(data_root).as_posix()
        ),
    )
    return _RestingSeries(evidence, False, (), ())


@dataclass(frozen=True)
class _WorkoutSessions:
    evidence: tuple[Evidence, ...]
    considered: int
    with_evidence: int
    no_evidence: tuple[tuple[NoEvidenceReason, int], ...]
    skipped: tuple[SkippedDocument, ...]
    failures: tuple[HrFailure, ...]
    kept: bool


def _read_workout_sessions(
    data_root: Path,
    settings: HrStageSettings,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> _WorkoutSessions:
    documents = []
    for page in sorted((data_root / "workouts").glob("*.md")):
        frontmatter = docio.read_frontmatter(page)
        if frontmatter is not None and is_workout_document(frontmatter):
            documents.append((page.relative_to(data_root).as_posix(), frontmatter))
    peaks: list[SessionPeak] = []
    counts = dict.fromkeys(NoEvidenceReason, 0)
    skipped: list[SkippedDocument] = []
    failures: list[HrFailure] = []
    for done, (document, frontmatter) in enumerate(documents, 1):
        try:
            day = document_date(frontmatter)
            if day is None:
                counts[NoEvidenceReason.UNDATED] += 1
                continue
            archive = _resolve_workout_archive(data_root, frontmatter)
            if archive is None:
                reason = NoEvidenceReason.ARCHIVE_MISSING
                counts[reason] += 1
                skipped.append(
                    SkippedDocument(document, reason, "archived source not found")
                )
                continue
            try:
                activity = compose_listed(
                    data_root, source_refs(frontmatter), parse_fit(archive.read_bytes())
                ).activity
            except FitDecodeError as exc:
                reason = NoEvidenceReason.ARCHIVE_UNDECODABLE
                counts[reason] += 1
                skipped.append(SkippedDocument(document, reason, str(exc)))
                continue
            except OSError as exc:
                failures.append(HrFailure(BenchmarkKind.MAX_HR_BPM, document, str(exc)))
                continue
            peak = session_peak(
                activity.samples, modality=activity.modality, flags=settings.load.flags
            )
            if isinstance(peak, NoEvidenceReason):
                counts[peak] += 1
            else:
                peaks.append(SessionPeak(day, document, peak))
        finally:
            if progress is not None:
                progress(done, len(documents))
    return _WorkoutSessions(
        max_evidence(peaks),
        len(documents),
        len(peaks),
        tuple(counts.items()),
        tuple(skipped),
        tuple(failures),
        bool(failures),
    )


def _resolve_workout_archive(
    data_root: Path, frontmatter: dict[str, object]
) -> Path | None:
    refs = source_refs(frontmatter)
    if not refs:
        return None
    sha = sha_of_ref(refs[-1])
    if sha is None:
        return None
    archive = archive_path(data_root, sha)
    return archive if archive.is_file() else None
