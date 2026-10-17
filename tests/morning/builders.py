"""Synthetic, source-attributed wellness inputs for morning-of tests."""

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date
from pathlib import Path

from fitdocs import compute_metrics, parse_fit
from fitdocs.contract import (
    DOC_VERSION,
    LOAD_NOT_COMPUTED,
    LOAD_REGION,
    MORNING_PLACEHOLDER,
    MORNING_REGION,
    NOTES_PLACEHOLDER,
    NOTES_REGION,
    region_block,
)
from fitdocs.render import DocContext, render_document
from fitdocs.wellness import Metric, SeriesValue, WellnessSeries
from tests.fixtures import builder
from tests.wellness.builders_series import write_series


def series_value(
    day: date,
    value: float,
    *,
    metric: Metric,
    source: str,
    canonical: bool,
    origin: str | None = None,
) -> SeriesValue:
    return SeriesValue(day, metric, source, origin, value, canonical)


def wellness_series(values: Iterable[SeriesValue]) -> WellnessSeries:
    items = tuple(values)
    keys = {(item.day, item.metric, item.source) for item in items}
    if len(keys) != len(items):
        raise ValueError("duplicate day, metric and source")
    groups = {(item.day, item.metric) for item in items}
    canonicals = Counter((item.day, item.metric) for item in items if item.canonical)
    if any(canonicals[group] != 1 for group in groups):
        raise ValueError("exactly one canonical value required per day and metric")
    return WellnessSeries(values=tuple(sorted(items)))


def stage_series(data_root: Path, series: WellnessSeries) -> tuple[Path, ...]:
    return write_series(data_root, series.values)


def workout_page(
    day: date | None = date(2021, 9, 8),
    *,
    doc_version: int | str | None = DOC_VERSION,
    morning: str = MORNING_PLACEHOLDER,
) -> str:
    """A synthetic workout document with the renderer's region layout."""
    frontmatter = ["---", "type: workout"]
    if doc_version is not None:
        frontmatter.append(f"doc_version: {doc_version}")
    if day is not None:
        frontmatter.append(f"date: {day.isoformat()}")
    frontmatter.append("---")
    return (
        "\n\n".join(
            (
                "\n".join(frontmatter),
                "# Synthetic workout",
                region_block(NOTES_REGION, NOTES_PLACEHOLDER).rstrip("\n"),
                "## Summary\n\nSynthetic workout summary.",
                region_block(MORNING_REGION, morning).rstrip("\n"),
                "## Training Load\n\n"
                + region_block(LOAD_REGION, LOAD_NOT_COMPUTED).rstrip("\n"),
            )
        )
        + "\n"
    )


def rendered_page(fit_bytes: bytes | None = None) -> str:
    """Render sanctioned synthetic FIT bytes into a complete workout page."""
    activity = parse_fit(builder.run_fit_bytes() if fit_bytes is None else fit_bytes)
    context = DocContext(
        activity=activity,
        metrics=compute_metrics(activity),
        athlete=None,
        doc_stem="2021-09-08-synthetic-workout-0146",
        source_refs=("fit-archive/synthetic.fit",),
        tz=UTC,
    )
    return render_document(context).markdown
