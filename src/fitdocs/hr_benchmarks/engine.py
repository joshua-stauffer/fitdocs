"""Collect evidence and reconcile the heart-rate benchmark partition."""

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fitdocs import FitDecodeError, docio, parse_fit
from fitdocs.benchmarks import Benchmark, BenchmarkKind, BenchmarkSet
from fitdocs.compose.archive import compose_listed
from fitdocs.contract import document_date, is_workout_document, sha_of_ref, source_refs
from fitdocs.layout import archive_path, settings_path, wellness_series_path
from fitdocs.load.profile import load_profile, save_profile
from fitdocs.load.settings import LoadSettings, load_load_settings
from fitdocs.wellness import (
    Metric,
    SeriesReadError,
    effective_order,
    load_wellness_settings,
    read_series,
)

from .inspect import back_reach_cover, inconsistencies, takeovers
from .maximum import max_evidence
from .peaks import session_peak
from .resting import resting_evidence
from .sources import MAX_RULE, RESTING_RULE
from .timeline import derive_timeline
from .types import (
    HR_KINDS,
    BackReachChange,
    Evidence,
    HrFailure,
    HrStageReport,
    KindOutcome,
    NoEvidenceReason,
    SessionPeak,
    SkippedDocument,
    Takeover,
)


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


def _read_resting_series(
    data_root: Path,
    settings: HrStageSettings,
    hand_dates: Collection[date] = (),
) -> _RestingSeries:
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
        hand_dates=hand_dates,
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
    hand_dates: Collection[date] = (),
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
        max_evidence(peaks, hand_dates=hand_dates),
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


def derive_hr_benchmarks(
    data_root: Path,
    *,
    settings: HrStageSettings,
    dry_run: bool = False,
    other_derived: Sequence[Benchmark] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> HrStageReport:
    profile = load_profile(data_root)
    old = profile.benchmarks
    resting = _read_resting_series(
        data_root,
        settings,
        _hand_dates(old, BenchmarkKind.RESTING_HR_BPM),
    )
    workouts = _read_workout_sessions(
        data_root,
        settings,
        _hand_dates(old, BenchmarkKind.MAX_HR_BPM),
        progress=progress,
    )
    hr_entries: list[Benchmark] = []
    for rule, evidence, kept in (
        (RESTING_RULE, resting.evidence, resting.kept),
        (MAX_RULE, workouts.evidence, workouts.kept),
    ):
        previous = _derived_kind(old, rule.kind)
        recorded = tuple(
            entry
            for entry in old.entries
            if entry.kind is rule.kind and not _is_derived(entry)
        )
        hr_entries.extend(
            previous if kept else derive_timeline(rule, evidence, recorded).entries
        )
    new = profile.with_derived_benchmarks(
        hr_entries, kinds=HR_KINDS, replace_applies_from=True
    )
    changed = frozenset(
        entry
        for entry in new.benchmarks.entries
        if entry.kind in HR_KINDS and _is_derived(entry)
    ) != frozenset(
        entry for entry in old.entries if entry.kind in HR_KINDS and _is_derived(entry)
    )
    written = changed and not dry_run
    if written:
        save_profile(data_root, new)
    outcomes = []
    for kind, kept in (
        (BenchmarkKind.RESTING_HR_BPM, resting.kept),
        (BenchmarkKind.MAX_HR_BPM, workouts.kept),
    ):
        before = _derived_kind(old, kind)
        after = _derived_kind(new.benchmarks, kind)
        outcomes.append(
            KindOutcome(
                kind,
                after,
                tuple(entry for entry in after if entry not in before),
                tuple(entry for entry in before if entry not in after),
                kept,
            )
        )
    previous_takeovers = {_takeover_key(takeover) for takeover in takeovers(old)}
    new_takeovers = tuple(
        takeover
        for takeover in takeovers(new.benchmarks)
        if _takeover_key(takeover) not in previous_takeovers
    )
    before_cover = {
        cover.entry: (cover.starts_on, cover.ends_before)
        for cover in back_reach_cover(old)
    }
    changes = tuple(
        BackReachChange(
            cover.kind,
            cover.entry,
            before_cover[cover.entry],
            (cover.starts_on, cover.ends_before),
        )
        for cover in back_reach_cover(new.benchmarks)
        if before_cover[cover.entry] != (cover.starts_on, cover.ends_before)
    )
    view = new.benchmarks
    if other_derived is not None:
        view = BenchmarkSet(
            tuple(
                entry
                for entry in view.entries
                if entry.kind in HR_KINDS or not _is_derived(entry)
            )
            + tuple(other_derived)
        )
    return HrStageReport(
        workouts.considered,
        workouts.with_evidence,
        workouts.no_evidence,
        workouts.skipped,
        tuple(dict.fromkeys(item.key for item in resting.evidence)),
        tuple(outcomes),
        new_takeovers,
        changes,
        inconsistencies(view),
        resting.failures + workouts.failures,
        resting.notes,
        written,
        changed,
    )


def _hand_dates(benchmarks: BenchmarkSet, kind: BenchmarkKind) -> frozenset[date]:
    return frozenset(
        entry.measured_on
        for entry in benchmarks.entries
        if entry.kind is kind and not _is_derived(entry)
    )


def _is_derived(entry: Benchmark) -> bool:
    return entry.source is not None and entry.source.is_derived


def _derived_kind(
    benchmarks: BenchmarkSet, kind: BenchmarkKind
) -> tuple[Benchmark, ...]:
    return tuple(
        entry
        for entry in benchmarks.entries
        if entry.kind is kind and _is_derived(entry)
    )


def _takeover_key(takeover: Takeover) -> tuple[BenchmarkKind, date, float, date]:
    return (
        takeover.kind,
        takeover.derived.measured_on,
        takeover.derived.value,
        takeover.superseded.measured_on,
    )
