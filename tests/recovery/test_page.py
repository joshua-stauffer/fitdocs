"""Synthetic recovery markdown, part 1."""

from __future__ import annotations

import math
import statistics
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.history import HISTORY_TYPE, compute_history, read_history_inputs
from fitdocs.recovery import Baselines, page
from fitdocs.recovery.view import RecoveryView, build_view
from fitdocs.render.attribution import wellness_attribution, wellness_attribution_line
from fitdocs.render.charts.kit import Column, Value, ValueKind
from fitdocs.render.charts.kit.format import format_value
from fitdocs.wellness import METRICS, Metric, SeriesValue
from tests.recovery.builders import series_value, wellness_series, workout_page

D = date(2025, 5, 1)
BASE = (Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS, Metric.RESTING_HR_BPM)
SLEEP = (
    Metric.SLEEP_S,
    Metric.SLEEP_DEEP_S,
    Metric.SLEEP_LIGHT_S,
    Metric.SLEEP_REM_S,
    Metric.SLEEP_AWAKE_S,
    Metric.SLEEP_HR_BPM,
)
NAMES = ("hrv-sdnn", "hrv-rmssd", "resting-hr")
CHARTS = tuple(
    (name, f"<svg>{name}</svg>") for name in ("load", *NAMES, "sleep", "other")
)
GOLDEN = Path(__file__).with_name("golden") / "page-part1.md"


def value(
    offset: int,
    number: float,
    metric: Metric = BASE[2],
    source: str = "watch",
    origin: str | None = "garmin",
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        number,
        metric=metric,
        source=source,
        canonical=True,
        origin=origin,
    )


def model(
    values: list[SeriesValue],
    *,
    limit: int = 12,
    root: Path | None = None,
    methodology: str = "chosen",
) -> RecoveryView:
    series = wellness_series(values)
    load = (
        None
        if root is None
        else compute_history(read_history_inputs(root), methodology=methodology)
    )
    result = build_view(series, Baselines.of(series), load, panel_limit=limit)
    if result is None:
        raise ValueError("nonempty synthetic series required")
    return result


def full_view() -> RecoveryView:
    values = [
        value(
            i,
            seed + ((i + 62) % 7) * step + (seed * 0.8 if i >= -8 else 0),
            metric,
            f"watch{j}",
        )
        for j, (metric, seed, step) in enumerate(
            zip(
                (*BASE, *SLEEP),
                (31, 83, 57, 25001, 1101, 8701, 3901, 101, 61),
                (4, 11, 1.3, 311, 79, 233, 137, 31, 17),
                strict=True,
            )
        )
        for i in range(-62, -1)
    ]
    # Sleep rows follow the total-sleep source.
    values = [replace(v, source="watch3") if v.metric in SLEEP else v for v in values]
    values.extend(
        (
            value(0, 2.375, Metric.MOOD_RATING, "rating"),
            value(0, 8123, Metric.STEPS, "pedometer"),
        )
    )
    return model(values)


def text(view: RecoveryView) -> str:
    return page.render_page(view, CHARTS).markdown


def section(markdown: str, heading: str) -> list[str]:
    start = markdown.split(f"## {heading}\n", 1)[1]
    return [line for line in start.split("\n## ", 1)[0].splitlines() if line]


def fmt(number: float | None, metric: Metric) -> str:
    return format_value(
        number,
        Column("value", ValueKind.NUMBER, METRICS[metric].unit, METRICS[metric].label),
        with_unit=True,
    )


@pytest.mark.parametrize(
    "field,expected",
    [
        ("title", 'title: "Recovery"'),
        ("type", 'type: "recovery"'),
        ("generator", 'generator: "fitdocs"'),
        ("recovery_version", "recovery_version: 1"),
        ("baselines_version", "baselines_version: 1"),
        ("as_of", 'as_of: "2025-05-01"'),
        ("window_start", 'window_start: "2025-02-01"'),
        ("window_end", 'window_end: "2025-05-01"'),
    ],
)
def test_frontmatter(field: str, expected: str) -> None:
    assert (
        next(
            line
            for line in text(full_view()).splitlines()
            if line.startswith(field + ":")
        )
        == expected
    )


def test_frontmatter_order() -> None:
    assert tuple(
        line.split(":", 1)[0]
        for line in text(full_view()).split("---")[1].strip().splitlines()
    ) == (
        "title",
        "type",
        "generator",
        "recovery_version",
        "baselines_version",
        "as_of",
        "window_start",
        "window_end",
    )


def test_frontmatter_vocabulary() -> None:
    assert page.RECOVERY_FRONTMATTER_KEYS == (
        "title",
        "type",
        "generator",
        "recovery_version",
        "baselines_version",
        "as_of",
        "window_start",
        "window_end",
        "methodology",
    )


def test_recovery_identity() -> None:
    assert (
        page.RECOVERY_TYPE,
        page.RECOVERY_TITLE,
        type(page.RECOVERY_VERSION),
        page.RECOVERY_VERSION,
        page.RECOVERY_TYPE == contract.WORKOUT_TYPE,
        page.RECOVERY_TYPE == HISTORY_TYPE,
    ) == ("recovery", "Recovery", int, 1, False, False)


def test_banner() -> None:
    assert (
        text(full_view()).split("---", 2)[2].split("# Recovery", 1)[0].strip()
        == contract.DOC_BANNER
    )


def test_opening() -> None:
    assert (
        text(full_view())
        .split("Data source: Garmin\n", 1)[1]
        .split("## ", 1)[0]
        .strip()
        == "As of 2025-05-01. Window: 2025-02-01 to 2025-05-01. Each "
        "signal is shown against the athlete's own baseline, "
        "computed separately for every source. This page describes "
        "the data and draws no conclusion from it."
    )


def test_section_order() -> None:
    assert [
        line for line in text(full_view()).splitlines() if line.startswith("## ")
    ] == [
        "## Fitness, Fatigue and Form",
        "## HRV (SDNN)",
        "## HRV (rMSSD)",
        "## Resting HR",
        "## Sleep",
        "## Other Signals",
    ]


@pytest.mark.parametrize("metric,name", tuple(zip(BASE, NAMES, strict=True)))
def test_signal_link(metric: Metric, name: str) -> None:
    assert (
        section(text(full_view()), METRICS[metric].label)[0]
        == f"![{METRICS[metric].label} chart](assets/recovery-{name}.svg)"
    )


@pytest.mark.parametrize("metric", BASE)
@pytest.mark.parametrize("field", ("latest", "mean", "range"))
def test_signal_numbers(metric: Metric, field: str) -> None:
    j = BASE.index(metric)
    seed, step = ((31, 4), (83, 11), (57, 1.3))[j]
    all_values = [
        seed + (i % 7) * step + (seed * 0.8 if i >= 54 else 0) for i in range(61)
    ]
    transform = math.log if j < 2 else float
    inverse = math.exp if j < 2 else float
    rolling = inverse(statistics.mean(map(transform, all_values[-7:])))
    baseline = list(map(transform, all_values[:-1]))
    center, sd = statistics.mean(baseline), statistics.stdev(baseline)
    expected = {
        "latest": f"Latest: 2025-04-29, {fmt(all_values[-1], metric)} (watch{j}).",
        "mean": f"7-day mean: {fmt(rolling, metric)}.",
        "range": f"Normal range: {fmt(inverse(center - 0.5 * sd), metric)} "
        f"to {fmt(inverse(center + 0.5 * sd), metric)}, from 60 of "
        f"the 60 days before.",
    }[field]
    prefix = {"latest": "Latest:", "mean": "7-day mean:", "range": "Normal range:"}[
        field
    ]
    assert (
        next(
            line
            for line in section(text(full_view()), METRICS[metric].label)
            if line.startswith(prefix)
        )
        == expected
    )


@pytest.mark.parametrize("metric", BASE)
@pytest.mark.parametrize("count", (1, 2))
@pytest.mark.parametrize("field", ("mean", "range"))
def test_not_shown(metric: Metric, count: int, field: str) -> None:
    result = model([value(-i, 41 + i * 11, metric) for i in range(count)])
    prefix = "7-day mean" if field == "mean" else "Normal range"
    number, days, minimum = (count, 7, 3) if field == "mean" else (count - 1, 60, 30)
    expected = (
        f"{prefix}: not shown — {number} of the {days} days hold a "
        f"value; at least {minimum} are needed."
    )
    assert (
        next(
            line
            for line in section(text(result), METRICS[metric].label)
            if line.startswith(prefix + ":")
        )
        == expected
    )


@pytest.mark.parametrize("metric", BASE)
def test_no_runs(metric: Metric) -> None:
    result = model([value(i, 53, metric) for i in range(-61, 1)])
    assert (
        section(text(result), METRICS[metric].label)[-2]
        == "No day of the window has a 7-day mean outside the normal range."
    )


@pytest.mark.parametrize("direction,number", [("above", 180), ("below", 10)])
@pytest.mark.parametrize("length", (1, 4))
def test_run(direction: str, number: float, length: int) -> None:
    result = model([value(i, number if i > -length else 50) for i in range(-65, 1)])
    expected_date = "2025-05-01" if length == 1 else "2025-04-28 to 2025-05-01"
    assert [
        line for line in section(text(result), "Resting HR") if line.startswith("- ")
    ] == [f"- {expected_date}: {direction} (watch)"]


def changes_view() -> RecoveryView:
    return model(
        [
            value(-6, 50, source="old*_", origin="a|b"),
            value(-5, 60, source="old*_", origin="z&"),
            value(-2, 80, source="new[1]", origin=None),
            value(0, 90, source="new[1]", origin="local~"),
        ]
    )


def test_source_change() -> None:
    assert (
        next(
            line
            for line in section(text(changes_view()), "Resting HR")
            if line.startswith("On ")
        )
        == "On 2025-04-29 the shown source changed from old\\*\\_ to "
        "new\\[1\\]; from that day the 7-day mean and normal range "
        "are new\\[1\\]'s own."
    )


@pytest.mark.parametrize(
    "source,expected",
    [
        ("old", "Sources shown: old\\*\\_ (origins a\\|b, z\\&) on 4 days."),
        ("new", "Sources shown: new\\[1\\] (origins local\\~) on 3 days."),
    ],
)
def test_source_notes(source: str, expected: str) -> None:
    assert [
        line
        for line in section(text(changes_view()), "Resting HR")
        if line.startswith("Sources shown:")
    ][1 if source == "old" else 0] == expected


def test_unrecorded_origin() -> None:
    assert (
        section(text(model([value(0, 51, origin=None)])), "Resting HR")[-1]
        == "Sources shown: watch (origins not recorded) on 1 days."
    )


@pytest.mark.parametrize("metric", SLEEP)
@pytest.mark.parametrize("field", ("label", "value", "rolling", "baseline"))
def test_sleep_numbers(metric: Metric, field: str) -> None:
    j = SLEEP.index(metric)
    seed, step = (
        (25001, 311),
        (1101, 79),
        (8701, 233),
        (3901, 137),
        (101, 31),
        (61, 17),
    )[j]
    values = [seed + i % 7 * step + (seed * 0.8 if i >= 54 else 0) for i in range(61)]
    expected = (
        METRICS[metric].label,
        fmt(values[-1], metric),
        fmt(statistics.mean(values[-7:]), metric),
        fmt(statistics.mean(values[:-1]), metric),
    )
    row = section(text(full_view()), "Sleep")[3 + j]
    assert (
        row.split(" | ")[
            {"label": 0, "value": 1, "rolling": 2, "baseline": 3}[field]
        ].strip("| ")
        == expected[{"label": 0, "value": 1, "rolling": 2, "baseline": 3}[field]]
    )


def test_sleep_header() -> None:
    assert section(text(full_view()), "Sleep")[:3] == [
        "![Sleep chart](assets/recovery-sleep.svg)",
        "| Signal | 2025-04-29 | 7-day mean | 60-day mean |",
        "| --- | --- | --- | --- |",
    ]


@pytest.mark.parametrize("metric", SLEEP[1:5])
def test_zero_stage(metric: Metric) -> None:
    result = model([value(0, 23001, Metric.SLEEP_S), value(0, 0, metric)])
    assert section(text(result), "Sleep")[4:] == [
        f"| {METRICS[metric].label} | 0:00 | — | — |"
    ]


def test_sleep_missing_stages() -> None:
    assert section(text(model([value(0, 23001, Metric.SLEEP_S)])), "Sleep")[3:] == [
        "| Sleep | 6:23:21 | — | — |"
    ]


@pytest.mark.parametrize("metric", (*BASE, Metric.SLEEP_S))
def test_absent_section(metric: Metric) -> None:
    assert f"## {METRICS[metric].label}\n" not in text(
        model([value(0, 123, Metric.STEPS)])
    )


def test_other() -> None:
    assert section(text(full_view()), "Other Signals") == [
        "![Other signals chart](assets/recovery-other.svg)",
        "Shown as recorded, one panel per metric and source, with no baseline.",
    ]


def test_overflow() -> None:
    result = model(
        [value(0, 123, Metric.STEPS, "a"), value(0, 2.375, Metric.MOOD_RATING, "b|[]")],
        limit=1,
    )
    assert (
        section(text(result), "Other Signals")[-1]
        == "Also recorded in this window but not charted: Mood (rating) (b\\|\\[\\])."
    )


def test_other_absent() -> None:
    assert "## Other Signals\n" not in text(model([value(0, 54)]))


def test_no_load() -> None:
    assert section(text(full_view()), "Fitness, Fatigue and Form") == [
        "No workout page records a training load, so fitness, "
        "fatigue and form are not shown."
    ]


def load_view(root: Path, *, suppressed: bool, outside: bool) -> RecoveryView:
    start = date(2025, 4, 7) if outside else date(2025, 2, 1)
    length = 14 if outside else 90
    for i in range(length):
        workout_page(
            root,
            f"w{i}",
            start + timedelta(days=i),
            None
            if suppressed and (7 if outside else 9) <= i < (13 if outside else 15)
            else 13 + i,
            methodology="independent",
        )
    (root / "fitdocs.toml").write_text(
        "[history]\ncoverage_threshold = 0.8\n", encoding="utf-8"
    )
    return model([value(0, 51)], root=root, methodology="independent")


@pytest.mark.parametrize("field", ("frontmatter", "link", "methodology"))
def test_load_identity(tmp_path: Path, field: str) -> None:
    markdown = text(load_view(tmp_path, suppressed=True, outside=True))
    expected = {
        "frontmatter": "methodology: independent",
        "link": "![Fitness, fatigue and form chart](assets/recovery-load.svg)",
        "methodology": "Computed exactly as fitdocs history computes it, under "
        "the methodology independent.",
    }[field]
    assert expected in markdown.splitlines()


@pytest.mark.parametrize(
    "suppressed,outside,count",
    [(False, True, 76), (True, True, 83), (False, False, 0), (True, False, 7)],
)
def test_load_unavailable(
    tmp_path: Path, suppressed: bool, outside: bool, count: int
) -> None:
    lines = section(
        text(load_view(tmp_path, suppressed=suppressed, outside=outside)),
        "Fitness, Fatigue and Form",
    )
    assert [line for line in lines if "days of the window" in line] == (
        []
        if count == 0
        else [
            f"{count} days of the window have no fitness, fatigue or "
            f"form: they fall outside the load series or in a week "
            f"suppressed for low coverage."
        ]
    )


@pytest.mark.parametrize(
    "origins,expected",
    [
        (("garmin",), "Data source: Garmin"),
        (("garmin", None), "Data sources: Garmin and other sources"),
        (("garmin", "apple"), "Data sources: Garmin and other sources"),
    ],
)
def test_attribution_position(origins: tuple[str | None, ...], expected: str) -> None:
    result = model(
        [value(i, 51 + i, origin=origin) for i, origin in enumerate(origins)]
    )
    assert (
        text(result).splitlines()[text(result).splitlines().index("# Recovery") + 1]
        == expected
    )


@pytest.mark.parametrize("origin", (None, "apple"))
def test_attribution_absent(origin: str | None) -> None:
    result = model([value(0, 51, origin=origin)])
    assert wellness_attribution_line(wellness_attribution(result.origins)) is None
    assert not any(line.startswith("Data source") for line in text(result).splitlines())


@pytest.mark.parametrize("as_list", (False, True))
def test_result_charts(as_list: bool) -> None:
    result = page.render_page(full_view(), list(CHARTS) if as_list else CHARTS)
    assert (type(result.charts), result.charts) == (tuple, CHARTS)


def test_byte_golden() -> None:
    assert text(full_view()).encode() == GOLDEN.read_bytes()


@pytest.mark.parametrize("metric", BASE)
@pytest.mark.parametrize("formed", ("rolling", "baseline"))
def test_independent_missingness(metric: Metric, formed: str) -> None:
    offsets = list(range(-6, 1)) if formed == "rolling" else list(range(-60, -6)) + [0]
    result = model([value(i, 47, metric) for i in offsets])
    expected = (
        [
            "7-day mean: 47 ms." if metric in BASE[:2] else "7-day mean: 47 bpm.",
            "Normal range: not shown — 6 of the 60 days hold a value; "
            "at least 30 are needed.",
        ]
        if formed == "rolling"
        else [
            "7-day mean: not shown — 1 of the 7 days hold a value; at "
            "least 3 are needed.",
            "Normal range: 47 ms to 47 ms, from 54 of the 60 days before."
            if metric in BASE[:2]
            else "Normal range: 47 bpm to 47 bpm, from 54 of the 60 days before.",
        ]
    )
    assert [
        line
        for line in section(text(result), METRICS[metric].label)
        if line.startswith(("7-day mean:", "Normal range:"))
    ] == expected


@pytest.mark.parametrize("formed", ("rolling", "baseline"))
def test_sleep_independent_missingness(formed: str) -> None:
    offsets = list(range(-6, 1)) if formed == "rolling" else list(range(-60, -6)) + [0]
    result = model([value(i, 23001, Metric.SLEEP_S) for i in offsets])
    expected = (
        "| Sleep | 6:23:21 | 6:23:21 | — |"
        if formed == "rolling"
        else "| Sleep | 6:23:21 | — | 6:23:21 |"
    )
    assert section(text(result), "Sleep")[-1] == expected


def test_latest_source_escaping() -> None:
    assert (
        next(
            line
            for line in section(text(changes_view()), "Resting HR")
            if line.startswith("Latest:")
        )
        == "Latest: 2025-05-01, 90 bpm (new\\[1\\])."
    )


def test_sleep_nonselected_source_stage() -> None:
    result = model(
        [value(-2, 23001, Metric.SLEEP_S), value(0, 601, Metric.SLEEP_DEEP_S, "other")]
    )
    assert section(text(result), "Sleep")[3:] == ["| Sleep | 6:23:21 | — | — |"]


@pytest.mark.parametrize(
    "surface",
    (
        "signal-heading",
        "signal-chart",
        "sleep-heading",
        "sleep-chart",
        "sleep-row",
        "overflow",
    ),
)
def test_label_escaping(monkeypatch: pytest.MonkeyPatch, surface: str) -> None:
    for metric in (BASE[2], Metric.SLEEP_S, Metric.SLEEP_DEEP_S, Metric.MOOD_RATING):
        monkeypatch.setitem(METRICS, metric, replace(METRICS[metric], label="lab*|[]"))
    values = [
        value(0, 51),
        value(0, 23001, Metric.SLEEP_S),
        value(0, 0, Metric.SLEEP_DEEP_S),
        value(0, 123, Metric.STEPS),
        value(0, 2.375, Metric.MOOD_RATING, "other"),
    ]
    markdown = text(model(values, limit=1))
    escaped = "lab\\*\\|\\[\\]"
    expected = {
        "signal-heading": f"## {escaped}",
        "signal-chart": f"![{escaped} chart](assets/recovery-resting-hr.svg)",
        "sleep-heading": f"## {escaped}",
        "sleep-chart": f"![{escaped} chart](assets/recovery-sleep.svg)",
        "sleep-row": f"| {escaped} | 0:00 | — | — |",
        "overflow": f"Also recorded in this window but not charted: {escaped} (other).",
    }[surface]
    if surface.endswith("heading"):
        headings = [line for line in markdown.splitlines() if line.startswith("## ")]
        assert headings[1 if surface == "signal-heading" else 2] == expected
    else:
        assert expected in markdown.splitlines()


def test_ordered_overflow() -> None:
    result = model(
        [
            value(0, 51),
            value(0, 18, Metric.RESPIRATION_BRPM),
            value(0, 123, Metric.STEPS, "z|"),
            value(0, 70, Metric.WEIGHT_KG, "weight"),
            value(0, 2.375, Metric.MOOD_RATING, "mood"),
        ],
        limit=1,
    )
    assert (
        section(text(result), "Other Signals")[-1]
        == "Also recorded in this window but not charted: Steps "
        "(z\\|), Weight (weight), Mood (rating) (mood)."
    )


@pytest.mark.parametrize(
    "metric,role",
    [(metric, role) for metric in BASE for role in ("value", "mean", "low", "high")]
    + [(metric, role) for metric in SLEEP for role in ("value", "mean")],
)
def test_formatter_column(
    monkeypatch: pytest.MonkeyPatch, metric: Metric, role: str
) -> None:
    seen: list[tuple[object, str, ValueKind, str | None, str | None, bool]] = []
    original = format_value

    def record(number: Value, column: Column, *, with_unit: bool) -> str:
        seen.append(
            (
                round(float(number), 6)
                if isinstance(number, int | float | Decimal)
                and not isinstance(number, bool)
                else None,
                column.name,
                column.kind,
                column.unit,
                column.label,
                type(with_unit) is bool and with_unit,
            )
        )
        return original(number, column, with_unit=with_unit)

    monkeypatch.setattr(page, "format_value", record)
    text(full_view())
    j = (*BASE, *SLEEP).index(metric)
    seed, step = (
        (31, 4),
        (83, 11),
        (57, 1.3),
        (25001, 311),
        (1101, 79),
        (8701, 233),
        (3901, 137),
        (101, 31),
        (61, 17),
    )[j]
    numbers = [seed + i % 7 * step + (seed * 0.8 if i >= 54 else 0) for i in range(61)]
    transform = math.log if metric in BASE[:2] else float
    inverse = math.exp if metric in BASE[:2] else float
    baseline = list(map(transform, numbers[:-1]))
    expected_number = {
        "value": numbers[-1],
        "mean": inverse(statistics.mean(map(transform, numbers[-7:]))),
        "low": inverse(statistics.mean(baseline) - 0.5 * statistics.stdev(baseline)),
        "high": inverse(statistics.mean(baseline) + 0.5 * statistics.stdev(baseline)),
    }[role]
    expected = (
        round(expected_number, 6),
        role,
        ValueKind.NUMBER,
        METRICS[metric].unit,
        {
            "value": METRICS[metric].label,
            "mean": "7-day mean",
            "low": "normal range low",
            "high": "normal range high",
        }[role],
        True,
    )
    fields = (0, 1, 2, 3, 4, 5) if metric in (*BASE, Metric.SLEEP_S) else (0, 2, 3, 5)
    assert tuple(expected[i] for i in fields) in [
        tuple(event[i] for i in fields) for event in seen
    ]


def test_title_line() -> None:
    assert [
        line for line in text(full_view()).splitlines() if line.startswith("# ")
    ] == ["# Recovery"]


def test_methodology_escaping(tmp_path: Path) -> None:
    workout_page(tmp_path, "w", D, 31, methodology="chosen*[]")
    result = model([value(0, 51)], root=tmp_path, methodology="chosen*[]")
    assert (
        section(text(result), "Fitness, Fatigue and Form")[1]
        == "Computed exactly as fitdocs history computes it, under "
        "the methodology chosen\\*\\[\\]."
    )


def test_methodology_frontmatter_quoting(tmp_path: Path) -> None:
    workout_page(tmp_path, "w", D, 31, methodology="chosen*[]")
    result = model([value(0, 51)], root=tmp_path, methodology="chosen*[]")
    assert (
        next(
            line
            for line in text(result).splitlines()
            if line.startswith("methodology:")
        )
        == 'methodology: "chosen*[]"'
    )


def test_real_no_load(tmp_path: Path) -> None:
    workout_page(tmp_path, "w", D, None)
    result = model([value(0, 51)], root=tmp_path)
    assert section(text(result), "Fitness, Fatigue and Form") == [
        "No workout page records a training load, so fitness, "
        "fatigue and form are not shown."
    ]


def test_loaded_frontmatter_order(tmp_path: Path) -> None:
    markdown = text(load_view(tmp_path, suppressed=False, outside=True))
    assert tuple(
        line.split(":", 1)[0] for line in markdown.split("---")[1].strip().splitlines()
    ) == (
        "title",
        "type",
        "generator",
        "recovery_version",
        "baselines_version",
        "as_of",
        "window_start",
        "window_end",
        "methodology",
    )


def test_run_source_escaping() -> None:
    result = model(
        [value(i, 180 if i == 0 else 50, source="run*|[]") for i in range(-65, 1)]
    )
    assert [
        line for line in section(text(result), "Resting HR") if line.startswith("- ")
    ] == ["- 2025-05-01: above (run\\*\\|\\[\\])"]


def test_multiple_runs() -> None:
    values = []
    for offset in range(-65, 1):
        for source, number, chosen in (
            ("a|*", 180 if offset in (-3, 0) else 50, offset not in (-2, -1)),
            ("b[]", 10 if offset in (-2, -1) else 150, offset in (-2, -1)),
        ):
            values.append(
                replace(value(offset, number, source=source), canonical=chosen)
            )
    result = model(values)
    assert [
        line for line in section(text(result), "Resting HR") if line.startswith("- ")
    ] == [
        "- 2025-04-28: above (a\\|\\*)",
        "- 2025-04-29 to 2025-04-30: below (b\\[\\])",
        "- 2025-05-01: above (a\\|\\*)",
    ]


def test_multiple_source_changes() -> None:
    result = model(
        [
            value(-8, 51, source="old"),
            value(-6, 61, source="new"),
            value(-3, 71, source="third"),
            value(0, 81, source="new"),
        ]
    )
    assert [
        line for line in section(text(result), "Resting HR") if line.startswith("On ")
    ] == [
        "On 2025-04-25 the shown source changed from old to new; "
        "from that day the 7-day mean and normal range are new's "
        "own.",
        "On 2025-04-28 the shown source changed from new to third; "
        "from that day the 7-day mean and normal range are third's "
        "own.",
        "On 2025-05-01 the shown source changed from third to new; "
        "from that day the 7-day mean and normal range are new's "
        "own.",
    ]


def test_sleep_row_order() -> None:
    assert [
        line.split("|")[1].strip()
        for line in section(text(full_view()), "Sleep")
        if line.startswith("|")
    ][2:] == [
        "Sleep",
        "Deep sleep",
        "Light sleep",
        "REM sleep",
        "Awake in sleep",
        "Sleeping HR",
    ]


@pytest.mark.parametrize("number", (0, 1, 2, 3, 7, 30, 60, 63))
def test_count_formatter(monkeypatch: pytest.MonkeyPatch, number: int) -> None:
    seen: list[tuple[Decimal | None, str, ValueKind, str | None, str | None, bool]] = []

    def record(value: Value, column: Column, *, with_unit: bool) -> str:
        seen.append(
            (
                Decimal(str(value))
                if isinstance(value, int | float | Decimal)
                and not isinstance(value, bool)
                else None,
                column.name,
                column.kind,
                column.unit,
                column.label,
                type(with_unit) is bool and with_unit,
            )
        )
        return format_value(value, column, with_unit=with_unit)

    monkeypatch.setattr(page, "format_value", record)
    text(full_view())
    text(model([value(0, 51)]))
    text(model([value(-1, 61), value(0, 51)]))
    assert (Decimal(number), ValueKind.NUMBER, None, True) in [
        (value, column_kind, unit, with_unit)
        for value, _name, column_kind, unit, _label, with_unit in seen
    ]


@pytest.mark.parametrize("day", (date(2025, 2, 1), D, date(2025, 4, 29)))
def test_date_formatter(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    markdown = text(full_view())
    expected = {
        date(2025, 2, 1): ('window_start: "2025-02-01"', "2025-02-01"),
        D: ('as_of: "2025-05-01"', 'window_end: "2025-05-01"'),
        date(2025, 4, 29): (
            "Latest: 2025-04-29,",
            "| Signal | 2025-04-29 | 7-day mean | 60-day mean |",
        ),
    }[day]
    assert all(fragment in markdown for fragment in expected)


def main() -> None:
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_bytes(text(full_view()).encode())


if __name__ == "__main__":
    main()


@pytest.mark.parametrize(
    "field",
    (
        "recovery-version",
        "baselines-version",
        "rolling-count",
        "rolling-days",
        "rolling-minimum",
        "formed-baseline-count",
        "formed-baseline-days",
        "baseline-count",
        "baseline-days",
        "baseline-minimum",
        "source-days",
        "unavailable-days",
    ),
)
def test_numeric_formatter_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    def sentinel(number: Value, column: Column, *, with_unit: bool) -> str:
        if (
            isinstance(number, int | float | Decimal)
            and not isinstance(number, bool)
            and Decimal(str(number)) == Decimal(str(number)).to_integral_value()
            and column.kind is ValueKind.NUMBER
            and column.unit is None
            and type(with_unit) is bool
            and with_unit
        ):
            return "N" + format_value(number, column, with_unit=with_unit)
        return format_value(number, column, with_unit=with_unit)

    monkeypatch.setattr(page, "format_value", sentinel)
    if field == "unavailable-days":
        markdown = text(load_view(tmp_path, suppressed=True, outside=True))
        actual = section(markdown, "Fitness, Fatigue and Form")[-1]
        expected = (
            "N83 days of the window have no fitness, fatigue or form: "
            "they fall outside the load series or in a week suppressed "
            "for low coverage."
        )
    elif field in ("recovery-version", "baselines-version"):
        key = field.replace("-", "_")
        actual = next(
            line
            for line in text(full_view()).splitlines()
            if line.startswith(key + ":")
        )
        expected = key + ": N1"
    else:
        formed = field.startswith("formed-") or field == "source-days"
        markdown = text(full_view() if formed else model([value(0, 51)]))
        lines = section(markdown, "Resting HR")
        if field.startswith("rolling-"):
            actual = next(line for line in lines if line.startswith("7-day mean:"))
            expected = (
                "7-day mean: not shown — N1 of the N7 days hold a value; "
                "at least N3 are needed."
            )
        elif field == "source-days":
            actual = next(line for line in lines if line.startswith("Sources shown:"))
            expected = "Sources shown: watch2 (origins garmin) on N63 days."
        elif formed:
            actual = next(line for line in lines if line.startswith("Normal range:"))
            expected = (
                "Normal range: 58 bpm to 72 bpm, from N60 of the N60 days before."
            )
        else:
            actual = next(line for line in lines if line.startswith("Normal range:"))
            expected = (
                "Normal range: not shown — N0 of the N60 days hold a value; "
                "at least N30 are needed."
            )
    assert actual == expected


def test_negative_resting_hr_range() -> None:
    result = model([value(i, 250 if i == -60 else 1) for i in range(-60, 1)])
    assert (
        next(
            line
            for line in section(text(result), "Resting HR")
            if line.startswith("Normal range:")
        )
        == "Normal range: -11 bpm to 21 bpm, from 60 of the 60 days before."
    )


@pytest.mark.parametrize("metric", SLEEP[1:5])
@pytest.mark.parametrize("formed", ("both", "rolling", "baseline", "neither"))
def test_zero_stage_mean_formation(metric: Metric, formed: str) -> None:
    offsets = {
        "both": list(range(-60, 1)),
        "rolling": [-2, -1, 0],
        "baseline": list(range(-60, -6)) + [0],
        "neither": [0],
    }[formed]
    values = [value(i, 23001, Metric.SLEEP_S) for i in range(-60, 1)] + [
        value(i, 0, metric) for i in offsets
    ]
    result = model(values)
    if result.sleep is None:
        raise AssertionError("total sleep forms the sleep section")
    bd = next(row for row in result.sleep.rows if row.metric == metric)
    assert (
        bd.rolling_count,
        bd.baseline_count,
        bd.value,
        bd.rolling_mean,
        bd.baseline_mean,
    ) == {
        "both": (7, 60, 0, 0.0, 0.0),
        "rolling": (3, 2, 0, 0.0, None),
        "baseline": (1, 54, 0, None, 0.0),
        "neither": (1, 0, 0, None, None),
    }[formed]
    rolling = "0:00" if formed in ("both", "rolling") else "—"
    baseline = "0:00" if formed in ("both", "baseline") else "—"
    assert section(text(result), "Sleep")[4] == (
        f"| {METRICS[metric].label} | 0:00 | {rolling} | {baseline} |"
    )
