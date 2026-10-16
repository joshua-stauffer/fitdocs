"""Recovery guide fields and its user-facing entry points (task 5.1)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from fitdocs.recovery.constants import METHODS
from fitdocs.wellness import Metric

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "recovery.md"


def _section(text: str, heading: str) -> str:
    level = len(heading.split(" ", 1)[0])
    match = re.search(
        rf"^{re.escape(heading)}\n(.*?)(?=^#{{1,{level}}} |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise ValueError(f"missing section {heading}")
    return " ".join(match.group(1).split())


@pytest.mark.parametrize(
    "name,field",
    [
        ("ROLLING_DAYS", "rolling_days"),
        ("MIN_ROLLING_VALUES", "min_rolling"),
        ("BASELINE_DAYS", "baseline_days"),
        ("MIN_BASELINE_VALUES", "min_baseline"),
        ("RANGE_SD_MULTIPLE", "range_multiple"),
    ],
)
def test_named_constant_matches_live_method(name: str, field: str) -> None:
    method = METHODS[Metric.HRV_RMSSD_MS]
    row = f"| `{name}` | {getattr(method, field)} |"
    assert row in _section(GUIDE.read_text(), "## Method")


@pytest.mark.parametrize(
    "heading,statement",
    [
        pytest.param(
            "## Run the command",
            "```sh fitdocs recovery ```",
            id="command",
        ),
        pytest.param(
            "## Run the command",
            "Run it after a drain that archived wellness or changed the "
            "wellness series, "
            "or when you want a fresh recovery page.",
            id="when",
        ),
        pytest.param(
            "## Run the command",
            "Data-root resolution is `--out` > `FITDOCS_DATA` > `.fitdocs/data-root`.",
            id="root",
        ),
        pytest.param(
            "## Run the command",
            "Use `fitdocs recovery --out /path/to/wiki --methodology threshold` "
            "to select a root and load methodology explicitly.",
            id="options",
        ),
        pytest.param(
            "## Run the command",
            "The command reads the normalized wellness series and workout documents; "
            "it writes `recovery/recovery.md` and relative SVG images in "
            "`recovery/assets/`.",
            id="inputs-outputs",
        ),
        pytest.param(
            "## Run the command",
            "The report prints `As of`, `Window`, `Methodology`, then each relative "
            "path with `written`, `unchanged`, `removed`, `foreign` or `failed`.",
            id="report",
        ),
        pytest.param(
            "## Run the command",
            "An empty wellness series writes nothing; an unreadable series reports "
            "the error and asks you to run `fitdocs sync` or `fitdocs regen`.",
            id="empty-invalid",
        ),
        pytest.param(
            "## Read the page",
            "The as-of day is the latest day in the wellness series, not today's date; "
            "the display window is 90 calendar days including that day.",
            id="window",
        ),
        pytest.param(
            "### Fitness, Fatigue and Form",
            "Uses the same computation as `fitdocs history`, under the selected "
            "load methodology, from loads already recorded on workout pages.",
            id="load",
        ),
        pytest.param(
            "### Fitness, Fatigue and Form",
            "Missing load coverage stays absent, including weeks suppressed for low "
            "coverage; without recorded load, the section explains why no chart "
            "is shown.",
            id="load-absence",
        ),
        pytest.param(
            "### HRV (SDNN), HRV (rMSSD) and Resting HR",
            "Each available signal has its own section: a chart, latest value and "
            "source, 7-day mean, normal range, above/below runs, source changes "
            "and sources shown.",
            id="signal-sections",
        ),
        pytest.param(
            "### Sleep",
            "Shows total sleep and its 7-day mean in the chart, with no normal range.",
            id="sleep-chart",
        ),
        pytest.param(
            "### Sleep",
            "The table uses the latest shown total-sleep night and that source: "
            "total, deep, light, REM, awake and sleep HR appear only when present "
            "on that night, with 7-day and 60-day means where formed.",
            id="sleep-table",
        ),
        pytest.param(
            "### Other Signals",
            "Shows recorded values in independent panels per metric and source, "
            "without a baseline; pairs beyond the panel limit are named as "
            "not charted.",
            id="other",
        ),
        pytest.param(
            "### Coverage",
            "Counts days with a value in the display window for each metric and "
            "source, and lists absent HRV, resting-HR and total-sleep signals.",
            id="coverage",
        ),
        pytest.param(
            "### Method and References",
            "Method on the generated page is the reference for constants, governing "
            "citations, corroboration and departures; References lists the "
            "cited works.",
            id="references",
        ),
        pytest.param(
            "## Method",
            "The page cites Plews et al. (2013) for log-HRV averaging, "
            "Plews et al. (2014) for the weekly minimum and Vesterinen et al. (2016) "
            "for the range multiplier, with application differences stated "
            "as departures.",
            id="citations",
        ),
        pytest.param(
            "## Method",
            "For a day D, the rolling window is D−6 through D, including D; "
            "the baseline is D−60 through D−1, excluding D.",
            id="method-windows",
        ),
        pytest.param(
            "## Method",
            "A rolling mean needs at least 3 present days; a baseline mean and "
            "sample SD need at least 30 present days.",
            id="formed-counts",
        ),
        pytest.param(
            "## Method",
            "HRV (SDNN and rMSSD separately) uses natural-log means and "
            "mean ± 0.5 sample SD on the log scale, exponentiated back to ms.",
            id="log-hrv",
        ),
        pytest.param(
            "## Method",
            "Resting HR uses linear means and mean ± 0.5 sample SD in bpm; "
            "sample SD uses n − 1 baseline days in its denominator.",
            id="linear-resting-sd",
        ),
        pytest.param(
            "## Method",
            "Sleep signals use linear 7-day and 60-day means, without a range.",
            id="sleep-method",
        ),
        pytest.param(
            "## Method",
            "A day is marked only when its 7-day mean is strictly below or above "
            "the bounds, not because its single daily value is outside them.",
            id="marked-quantity",
        ),
        pytest.param(
            "## Method",
            "The preceding-60-day baseline, 30-value minimum and sample-SD "
            "denominator are fitdocs choices; the generated Method explains "
            "the cited work's scope and each departure rather than claiming "
            "one published method covers the whole page.",
            id="method-scope",
        ),
        pytest.param(
            "## Sources",
            "Each rolling mean and baseline uses one metric and one source; "
            "values from different "
            "sources are not pooled and SDNN is not converted to or mixed with rMSSD.",
            id="independent-baselines",
        ),
        pytest.param(
            "## Sources",
            "The shown source is that metric's canonical source on D; if absent, "
            "use its most recent canonical source from D−1 through D−6, "
            "otherwise show no source.",
            id="shown-source",
        ),
        pytest.param(
            "## Sources",
            "Only the source identifier is carried, never yesterday's value; "
            "a source change immediately selects the new source's own means and range.",
            id="source-carry",
        ),
        pytest.param(
            "## Missing values",
            "Absent daily values stay absent, not zero; charts leave gaps.",
            id="missing-daily",
        ),
        pytest.param(
            "## Missing values",
            "Signal sections say `not shown` and give the present-day count, "
            "window length and required minimum when a mean or range cannot form.",
            id="not-shown",
        ),
        pytest.param(
            "## Missing values",
            "An unavailable signal section is omitted and named in Coverage; "
            "a formed mean or range can still be shown on a day with no daily value.",
            id="missing-section",
        ),
        pytest.param(
            "## Garmin attribution",
            "When any wellness value used by a printed or charted figure records "
            "Garmin origin, an attribution line appears directly beneath `# Recovery`.",
            id="attribution-position",
        ),
        pytest.param(
            "## Garmin attribution",
            "It reads `Data source: Garmin` when all such values have Garmin origin, "
            "or `Data sources: Garmin and other sources` when origins are mixed "
            "or include an unrecorded origin.",
            id="attribution-lines",
        ),
        pytest.param(
            "## Garmin attribution",
            "With no Garmin origin among values actually used, there is no "
            "attribution line; an unformed statistic uses no values for attribution.",
            id="attribution-absence",
        ),
        pytest.param(
            "## Garmin attribution",
            "Chart images carry no Garmin attribution stamp.",
            id="chart-attribution",
        ),
        pytest.param(
            "## Descriptive limits",
            "The page makes no readiness score, verdict, health or performance "
            "inference, training recommendation or forecast; normal range "
            "describes the athlete's own data, not a clinical threshold.",
            id="limits",
        ),
        pytest.param(
            "## Descriptive limits",
            "It runs offline as a standalone command, not as part of sync, regen, "
            "load or history, and does not change workout pages or wellness inputs.",
            id="standalone",
        ),
        pytest.param(
            "## Dashboard authors",
            "The chart kind is `reference-band`: bind `x` and `y`, optionally "
            "paired `low`/`high`, `mid`, `segment` and boolean `flag` channels.",
            id="kind-channels",
        ),
        pytest.param(
            "## Dashboard authors",
            "It draws daily points, a reference band and an optional mean line; "
            "absent daily values omit points, absent bounds break the band, "
            "absent mid values break the mean line, and segment changes "
            "break both band and line.",
            id="band-behavior",
        ),
        pytest.param(
            "## Dashboard authors",
            "Flags are caller-supplied markers, not a calculation of readiness "
            "or a verdict; see [Dashboards](dashboards.md) for directive syntax.",
            id="dashboard-link",
        ),
    ],
)
def test_guide_field_in_its_section(heading: str, statement: str) -> None:
    assert statement in _section(GUIDE.read_text(), heading)


def test_index_row_links_to_recovery_guide() -> None:
    index = ROOT / "docs" / "index.md"
    match = re.search(r"^\| \[Recovery\]\(([^)]+)\) \|", index.read_text(), re.M)
    assert match is not None
    assert (index.parent / match.group(1)).resolve() == GUIDE
    assert (index.parent / match.group(1)).is_file()


def test_project_url_links_to_recovery_guide() -> None:
    urls = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["urls"]
    assert urls.get("Recovery") == (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/recovery.md"
    )
    relative = urls["Recovery"].split("/blob/main/", 1)[1]
    assert (ROOT / relative).is_file()


def test_readme_recovery_ownership() -> None:
    readme = (ROOT / "README.md").read_text()
    ownership = _section(readme, "## Ownership")
    assert "`recovery/`, `recovery/assets/`" in ownership


def test_readme_recovery_history_sentence() -> None:
    readme = (ROOT / "README.md").read_text()
    history = readme.split("4. **Show training history.**", 1)[1].split("5. **", 1)[0]
    assert (
        "`fitdocs recovery` puts wellness signals against their own per-source "
        "baselines beside the load history; see "
        "[Recovery](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/recovery.md)."
    ) in " ".join(history.split())
