"""Read-only wellness tree findings."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fitdocs.settings import SettingsError, load_settings_document
from fitdocs.wellness.archive import list_archive
from fitdocs.wellness.engine import assess_series
from fitdocs.wellness.series import (
    NewerSeries,
    SeriesReadError,
    decode_manifest,
    format_value,
)
from fitdocs.wellness.settings import DEFAULT_WELLNESS_SETTINGS, load_wellness_settings


class WellnessProblemKind(StrEnum):
    ORPHANED_ENTRY = "orphaned_entry"
    SERIES_STALE = "series_stale"
    SERIES_OCCUPIED = "series_occupied"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class WellnessProblem:
    kind: WellnessProblemKind
    subject: str
    detail: str


def inspect_wellness(data_root: Path) -> tuple[WellnessProblem, ...]:
    listing = list_archive(data_root)
    problems = [
        WellnessProblem(
            WellnessProblemKind.ORPHANED_ENTRY,
            orphan.ref,
            f"{orphan.reason}; fitdocs never reads it",
        )
        for orphan in listing.orphans
    ]
    reasons: list[str] = []
    try:
        settings = load_wellness_settings(
            load_settings_document(data_root), data_root=data_root
        )
    except SettingsError as exc:
        settings = DEFAULT_WELLNESS_SETTINGS
        reasons.append(f"series cannot be judged: {exc}")
    assessment = assess_series(data_root, listing, settings)
    reasons.extend(assessment.reasons)
    reasons.extend(
        f"{note.subject}: could not be read: {note.detail}"
        for note in assessment.unreadable
    )
    problems.extend(
        WellnessProblem(WellnessProblemKind.SERIES_OCCUPIED, note.subject, note.detail)
        for note in assessment.blocked
    )
    manifest_path = data_root / "wellness/manifest.toml"
    unavailable = {
        note.subject for note in (*assessment.blocked, *assessment.unreadable)
    }
    if (
        not {"wellness", "wellness/manifest.toml"} & unavailable
        and manifest_path.is_file()
        and not manifest_path.is_symlink()
    ):
        try:
            manifest = decode_manifest(manifest_path, manifest_path.read_bytes())
        except OSError as exc:
            reasons.append(f"wellness/manifest.toml: could not be read: {exc}")
        except (ValueError, SeriesReadError):
            pass
        else:
            if not isinstance(manifest, NewerSeries):
                for conflict in manifest.conflicts:
                    entries = sorted(
                        [conflict.kept_entry, *(ref for ref, _ in conflict.others)]
                    )
                    problems.append(
                        WellnessProblem(
                            WellnessProblemKind.CONFLICT,
                            f"{conflict.day.isoformat()} {conflict.metric.value} "
                            f"{conflict.source}",
                            f"kept {format_value(conflict.kept_value)} "
                            f"from {conflict.kept_entry}; "
                            f"conflicting entries: {', '.join(entries)}",
                        )
                    )
    if reasons:
        problems.append(
            WellnessProblem(
                WellnessProblemKind.SERIES_STALE, "wellness", "; ".join(reasons)
            )
        )
    return tuple(problems)
