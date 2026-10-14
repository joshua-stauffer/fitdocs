"""Settings and normalized wellness evidence for the heart-rate stage."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.layout import settings_path, wellness_series_path
from fitdocs.load.settings import LoadSettings, load_load_settings
from fitdocs.wellness import (
    Metric,
    SeriesReadError,
    effective_order,
    load_wellness_settings,
    read_series,
)

from .resting import resting_evidence
from .types import Evidence, HrFailure


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
