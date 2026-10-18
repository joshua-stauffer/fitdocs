"""Printed morning facts, canonical stamps and markdown regions."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest

import fitdocs.morning.block as module
from fitdocs.morning.block import (
    MORNING_BLOCK_VERSION,
    MORNING_HEADING,
    STAMP_PATTERN,
    MorningBlock,
    MorningInputs,
    RowSource,
    SignalRow,
    SleepRow,
    Windows,
    parse_stamp,
    render_region,
)
from fitdocs.recovery import METHODS, RangePosition
from fitdocs.recovery.page import _FORBIDDEN_PHRASE_PATTERN
from fitdocs.render.attribution import WellnessAttribution
from fitdocs.wellness import METRICS, Metric, SeriesValue, WellnessSeries
from tests.morning.builders import series_value, wellness_series

D = date(2024, 3, 5)
GOLDEN = Path(__file__).with_name("golden")
SHAPES = (
    "signals_only",
    "sleep_only",
    "both",
    "garmin_sole",
    "garmin_contributing",
    "carried_source",
)
EXPECTED_FACTS = (
    '{"attribution":"none","day":"2024-03-05","signals":'
    '[["hrv_sdnn_ms","watch-é",["apple"],"61 ms",null,null,null],'
    '["resting_hr_bpm","watch-é",["apple"],"55 bpm",null,null,null]],'
    '"sleep":[["sleep_s","bed",["local"],"7:30:01",null,null]],'
    '"windows":[7,60]}'
)


def observation(
    offset: int,
    value: float,
    metric: Metric = Metric.RESTING_HR_BPM,
    *,
    source: str = "watch-é",
    origin: str | None = "apple",
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        value,
        metric=metric,
        source=source,
        canonical=True,
        origin=origin,
    )


def block_from(values: tuple[SeriesValue, ...]) -> MorningBlock:
    return cast(MorningBlock, MorningInputs.of(wellness_series(values)).block(D))


def reordered_blocks() -> tuple[
    WellnessSeries, WellnessSeries, MorningBlock, MorningBlock
]:
    first = wellness_series(
        (
            observation(0, 61.0, Metric.HRV_SDNN_MS),
            observation(0, 55.1),
            observation(0, 27001.0, Metric.SLEEP_S, source="bed", origin="local"),
        )
    )
    second = WellnessSeries(values=tuple(reversed(first.values)))
    return (
        first,
        second,
        cast(MorningBlock, MorningInputs.of(first).block(D)),
        cast(MorningBlock, MorningInputs.of(second).block(D)),
    )


def shape_block(shape: str) -> MorningBlock:
    source = RowSource("watch-a", ("apple",), False)
    signals: tuple[SignalRow, ...] = (
        SignalRow(
            Metric.HRV_SDNN_MS,
            "61 ms",
            "55 ms",
            "52 to 66 ms",
            RangePosition.WITHIN,
            source,
        ),
        SignalRow(
            Metric.HRV_RMSSD_MS,
            "43 ms",
            "37 ms",
            "40 to 58 ms",
            RangePosition.BELOW,
            source,
        ),
        SignalRow(
            Metric.RESTING_HR_BPM,
            "57 bpm",
            "63 bpm",
            "47 to 59 bpm",
            RangePosition.ABOVE,
            source,
        ),
    )
    sleep: tuple[SleepRow, ...] = (
        SleepRow(Metric.SLEEP_S, "7:12:00", "7:01:30", "6:55:10", source),
        SleepRow(Metric.SLEEP_DEEP_S, "1:02:03", None, None, source),
    )
    if shape == "sleep_only":
        signals = ()
    elif shape == "signals_only":
        sleep = ()
    elif shape == "carried_source":
        signals = (
            replace(signals[2], day_value=None, source=RowSource("watch-a", (), True)),
        )
        sleep = ()
    attribution = WellnessAttribution.NONE
    if shape in ("garmin_sole", "garmin_contributing"):
        source = RowSource("garmin-device", ("garmin",), shape == "garmin_contributing")
        signals = tuple(replace(row, source=source) for row in signals)
        sleep = tuple(replace(row, source=source) for row in sleep)
        attribution = (
            WellnessAttribution.SOLE
            if shape == "garmin_sole"
            else WellnessAttribution.CONTRIBUTING
        )
    return MorningBlock(D, Windows(7, 60), signals, sleep, attribution)


def test_nonempty_region_has_heading() -> None:
    assert "\n\n## Morning Of\n\n" in render_region(shape_block("both"))


def test_format_constants() -> None:
    assert (MORNING_BLOCK_VERSION, MORNING_HEADING, STAMP_PATTERN.pattern) == (
        1,
        "Morning Of",
        r"^<!-- fitdocs-morning:v([1-9][0-9]*) ([0-9a-f]{64}) -->$",
    )


@pytest.mark.parametrize("shape", SHAPES)
def test_region_bytes_match_golden(shape: str) -> None:
    assert (
        render_region(shape_block(shape)).encode("utf-8")
        == (GOLDEN / f"{shape}.md").read_bytes()
    )


def test_empty_region() -> None:
    assert render_region(None) == ""


def test_generated_stamp_grammar() -> None:
    line = render_region(shape_block("both")).splitlines()[0]
    assert STAMP_PATTERN.fullmatch(line) is not None


def test_generated_stamp_records_version_and_fingerprint() -> None:
    block = shape_block("both")
    assert parse_stamp(render_region(block)) == (1, block.fingerprint())


def test_final_newline() -> None:
    assert render_region(shape_block("both")).endswith("\n")


def test_sparse_native_signal_prints_each_absent_cell() -> None:
    block = block_from((observation(0, 55.1),))
    assert render_region(block).splitlines()[-1] == (
        "| Resting HR | 55 bpm | – | – | – | watch-é (apple) |"
    )


@pytest.mark.parametrize("version", (1, 12))
def test_parse_stamp_uses_first_line(version: int) -> None:
    digest = "0123456789abcdef" * 4
    assert parse_stamp(
        f"<!-- fitdocs-morning:v{version} {digest} -->\ntrailing content"
    ) == (version, digest)


@pytest.mark.parametrize(
    "content",
    (
        "",
        "\n<!-- fitdocs-morning:v1 " + "a" * 64 + " -->",
        "prefix <!-- fitdocs-morning:v1 " + "a" * 64 + " -->",
        "<!-- fitdocs-morning:v1 " + "a" * 64 + " --> suffix",
        "<!-- fitdocs-morning:v0 " + "a" * 64 + " -->",
        "<!-- fitdocs-morning:v01 " + "a" * 64 + " -->",
        "<!-- fitdocs-morning:v1 " + "A" * 64 + " -->",
        "<!-- fitdocs-morning:v1 " + "a" * 63 + " -->",
        "<!-- fitdocs-morning:v1 " + "a" * 65 + " -->",
        "<!-- fitdocs-morning:v1  " + "a" * 64 + " -->",
    ),
    ids=(
        "empty",
        "later-line",
        "prefix",
        "suffix",
        "zero",
        "leading-zero",
        "upper",
        "short",
        "long",
        "spacing",
    ),
)
def test_parse_stamp_rejects_invalid_first_line(content: str) -> None:
    assert parse_stamp(content) is None


def test_reordered_native_input_is_a_different_order() -> None:
    first, second, _, _ = reordered_blocks()
    assert first.values != second.values


def test_reordered_inputs_give_equal_printed_facts() -> None:
    _, _, first, second = reordered_blocks()
    assert first.facts() == second.facts()


def test_reordered_inputs_give_equal_fingerprints() -> None:
    _, _, first, second = reordered_blocks()
    assert first.fingerprint() == second.fingerprint()


def test_native_facts_exact_canonical_json() -> None:
    _, _, first, _ = reordered_blocks()
    assert first.facts() == EXPECTED_FACTS


def test_fingerprint_is_sha256_of_utf8_printed_facts() -> None:
    _, _, first, _ = reordered_blocks()
    assert (
        first.fingerprint()
        == hashlib.sha256(EXPECTED_FACTS.encode("utf-8")).hexdigest()
    )


def test_full_row_fact_encoding() -> None:
    block = MorningBlock(
        D,
        Windows(5, 40),
        (
            SignalRow(
                Metric.HRV_SDNN_MS,
                "61 ms",
                "55 ms",
                "52 to 66 ms",
                RangePosition.WITHIN,
                RowSource("s|é", ("garmin", "z"), True),
            ),
        ),
        (
            SleepRow(
                Metric.SLEEP_S,
                "7:12:00",
                "7:01:30",
                "6:55:10",
                RowSource("bed", (), True),
            ),
        ),
        WellnessAttribution.CONTRIBUTING,
    )
    assert block.facts() == (
        '{"attribution":"contributing","day":"2024-03-05","signals":'
        '[["hrv_sdnn_ms","s|é",["garmin","z"],"61 ms","55 ms","52 to 66 ms","within"]],'
        '"sleep":[["sleep_s","bed",[],"7:12:00","7:01:30","6:55:10"]],"windows":[5,40]}'
    )


@pytest.mark.parametrize("observable", ("fingerprint", "region"))
def test_subprecision_native_resting_hr_change(observable: str) -> None:
    first = block_from((observation(0, 55.10),))
    second = block_from((observation(0, 55.20),))
    actual = (
        (first.fingerprint(), second.fingerprint())
        if observable == "fingerprint"
        else (render_region(first), render_region(second))
    )
    assert actual[0] == actual[1]


@pytest.mark.parametrize("change", ("figure", "origin"))
def test_changed_printed_fact_changes_fingerprint(change: str) -> None:
    value = observation(0, 55.1)
    first = block_from((value,))
    second = block_from(
        (
            replace(value, value=59.1)
            if change == "figure"
            else replace(value, origin="local"),
        )
    )
    assert first.fingerprint() != second.fingerprint()


def test_ignored_steps_leave_facts_and_region_unchanged() -> None:
    values = (observation(0, 55.1), observation(0, 1234.0, Metric.STEPS))
    first = block_from(values)
    second = block_from((values[0], replace(values[1], value=9876.0)))
    assert (first.facts(), first.fingerprint(), render_region(first)) == (
        second.facts(),
        second.fingerprint(),
        render_region(second),
    )


def test_newly_recorded_already_listed_origin_leaves_region_unchanged() -> None:
    values = tuple(
        observation(i, 55.0 + i, origin=None if i == -1 else "apple")
        for i in (-2, -1, 0)
    )
    first = block_from(values)
    second = block_from(tuple(replace(value, origin="apple") for value in values))
    assert render_region(first) == render_region(second)


@pytest.mark.parametrize(
    "metric", (Metric.RESTING_HR_BPM, Metric.SLEEP_S), ids=("signal", "sleep")
)
@pytest.mark.parametrize("field", ("label", "source", "origin"))
def test_markdown_escaping(
    field: str, metric: Metric, monkeypatch: pytest.MonkeyPatch
) -> None:
    if field == "label":
        monkeypatch.setattr(
            module,
            "METRICS",
            {
                **METRICS,
                metric: replace(METRICS[metric], label="Label|*é"),
            },
        )
    block = block_from(
        (
            observation(
                0,
                27001.0 if metric == Metric.SLEEP_S else 55.1,
                metric,
                source="watch|*é" if field == "source" else "watch-é",
                origin="apple|*" if field == "origin" else "apple",
            ),
        )
    )
    cells = render_region(block).splitlines()[-1].split(" | ")
    assert cells[0 if field == "label" else -1] == (
        "| Label\\|\\*é"
        if field == "label"
        else "watch\\|\\*é (apple) |"
        if field == "source"
        else "watch-é (apple\\|\\*) |"
    )


def test_windows_and_iso_sentence_follow_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "METHODS",
        {
            metric: replace(method, rolling_days=5, baseline_days=40)
            for metric, method in METHODS.items()
        },
    )
    block = block_from((observation(0, 55.1), observation(0, 27001.0, Metric.SLEEP_S)))
    text = render_region(block)
    assert (text.split("\n\n")[2], text.splitlines()[6], text.splitlines()[10]) == (
        "Wellness for 2024-03-05, the day of this workout, against the "
        "athlete's own baseline for each source: 5-day means cover "
        "2024-03-01 to 2024-03-05, and normal ranges and 40-day means cover "
        "2024-01-25 to 2024-03-04.",
        "| Signal | 2024-03-05 | 5-day mean | Normal range | "
        "5-day mean vs range | Source |",
        "| Signal | Night ending 2024-03-05 | 5-day mean | 40-day mean | Source |",
    )


@pytest.mark.parametrize("shape", SHAPES)
def test_rendered_regions_are_descriptive(shape: str) -> None:
    assert _FORBIDDEN_PHRASE_PATTERN.search(render_region(shape_block(shape))) is None


def test_forbidden_phrase_positive_control() -> None:
    assert _FORBIDDEN_PHRASE_PATTERN.search("readiness") is not None


def regenerate_goldens() -> None:
    GOLDEN.mkdir(exist_ok=True)
    for shape in SHAPES:
        (GOLDEN / f"{shape}.md").write_bytes(
            render_region(shape_block(shape)).encode("utf-8")
        )


if __name__ == "__main__":
    regenerate_goldens()
