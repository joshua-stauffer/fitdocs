"""Synthetic timeline walks for one supplied heart-rate rule."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from fitdocs.benchmarks import (
    Benchmark,
    BenchmarkKind,
    BenchmarkSource,
    BenchmarkSourceKind,
)
from fitdocs.hr_benchmarks.sources import MAX_RULE, RESTING_RULE
from fitdocs.hr_benchmarks.timeline import TimelineResult, derive_timeline
from fitdocs.hr_benchmarks.types import Evidence, HrMethod, KindRule, Takeover
from tests.hr_benchmarks.builders import hand_benchmark


def _e(day: int, value: int, key: str = "watch") -> Evidence:
    return Evidence(
        date(2024, 1, 1) + timedelta(days=day - 1),
        value,
        key,
        f"document-{day}",
        f"{key}:metric-{day}",
        f"inputs-{day}",
        f"summary-{day}",
    )


def _points(result: TimelineResult) -> list[tuple[date, float]]:
    return [(entry.measured_on, entry.value) for entry in result.entries]


@pytest.mark.parametrize(
    "rule,value,method,citation",
    [
        (RESTING_RULE, 61, "resting_hr_series_median", "resting_hr_timeline_choice"),
        (MAX_RULE, 197, "max_hr_sustained_peak", "max_hr_timeline_choice"),
    ],
    ids=["resting", "maximum"],
)
def test_first_entry_uses_supplied_evidence_without_confirmation(
    rule: KindRule, value: int, method: str, citation: str
) -> None:
    assert derive_timeline(rule, [_e(1, value)], []) == TimelineResult(
        (
            Benchmark(
                kind=rule.kind,
                discipline=None,
                value=value,
                measured_on=date(2024, 1, 1),
                note="Derived by fitdocs from summary-1.",
                applies_from=None,
                source=BenchmarkSource(
                    kind=BenchmarkSourceKind.DERIVED,
                    method=method,
                    document="document-1",
                    inputs="inputs-1",
                    citation=citation,
                    series="watch:metric-1",
                ),
            ),
        ),
        (),
    )


@pytest.mark.parametrize("rule", [RESTING_RULE, MAX_RULE], ids=["resting", "maximum"])
@pytest.mark.parametrize("has_hand", [False, True], ids=["no-hand", "hand"])
def test_no_evidence_supplies_no_entry(rule: KindRule, has_hand: bool) -> None:
    recorded = [hand_benchmark(rule.kind, date(2023, 12, 31), 77)] if has_hand else []
    assert derive_timeline(rule, [], recorded) == TimelineResult((), ())


@pytest.mark.parametrize(
    "rule,value,count,expected",
    [
        (RESTING_RULE, 63, 14, []),
        (RESTING_RULE, 57, 14, []),
        (RESTING_RULE, 64, 14, [(date(2024, 1, 1), 64)]),
        (RESTING_RULE, 56, 14, [(date(2024, 1, 1), 56)]),
        (MAX_RULE, 192, 1, []),
        (MAX_RULE, 188, 1, []),
        (MAX_RULE, 193, 1, [(date(2024, 1, 1), 193)]),
        (MAX_RULE, 187, 1, []),
        (MAX_RULE, 100, 1, []),
    ],
    ids=[
        "rest-plus-step",
        "rest-minus-step",
        "rest-rise",
        "rest-fall",
        "max-plus-step",
        "max-minus-step",
        "max-rise",
        "max-fall-never-starts",
        "max-far-below",
    ],
)
def test_strict_step_in_both_directions(
    rule: KindRule, value: int, count: int, expected: list[tuple[date, float]]
) -> None:
    hand_value = 60 if rule.kind is BenchmarkKind.RESTING_HR_BPM else 190
    hand = hand_benchmark(rule.kind, date(2023, 12, 31), hand_value)
    assert (
        _points(
            derive_timeline(
                rule, [_e(day, value) for day in range(1, count + 1)], [hand]
            )
        )
        == expected
    )


@pytest.mark.parametrize("rule", [RESTING_RULE, MAX_RULE], ids=["resting", "maximum"])
def test_hand_measurement_day_supplies_no_evidence(rule: KindRule) -> None:
    hand = hand_benchmark(rule.kind, date(2024, 1, 1), 60)
    count = 14 if rule.kind is BenchmarkKind.RESTING_HR_BPM else 1
    assert derive_timeline(
        rule, [_e(day, 99) for day in range(1, count + 1)], [hand]
    ) == TimelineResult((), ())


def test_hand_takeover_records_full_note_source_and_pair() -> None:
    hand = hand_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        date(2023, 12, 31),
        190,
        note="athlete note",
        measured=True,
    )
    expected = Benchmark(
        BenchmarkKind.MAX_HR_BPM,
        None,
        196,
        date(2024, 1, 2),
        "Takes over from your hand-recorded 190 bpm of 2023-12-31: "
        "the evidence differed by more than 2 bpm.",
        None,
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-2",
            inputs="inputs-2",
            citation="max_hr_timeline_choice",
            series="watch:metric-2",
        ),
    )
    assert derive_timeline(MAX_RULE, [_e(2, 196)], [hand]) == TimelineResult(
        (expected,), (Takeover(BenchmarkKind.MAX_HR_BPM, expected, hand),)
    )


def test_hand_cover_holds_against_evidence_dated_on_or_before_it() -> None:
    hand = hand_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        date(2024, 1, 10),
        190,
        applies_from=date(2024, 1, 1),
    )
    covered = [_e(day, 205) for day in range(1, 11)]
    assert derive_timeline(MAX_RULE, covered, [hand]) == TimelineResult((), ())


def test_evidence_after_a_covering_hand_takes_over_without_back_reach_note() -> None:
    hand = hand_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        date(2024, 1, 10),
        190,
        applies_from=date(2024, 1, 1),
    )
    first = Benchmark(
        BenchmarkKind.MAX_HR_BPM,
        None,
        195,
        date(2024, 1, 11),
        "Takes over from your hand-recorded 190 bpm of 2024-01-10: "
        "the evidence differed by more than 2 bpm.",
        None,
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-11",
            inputs="inputs-11",
            citation="max_hr_timeline_choice",
            series="watch:metric-11",
        ),
    )
    assert derive_timeline(
        MAX_RULE, [_e(2, 205), _e(11, 195), _e(12, 192)], [hand]
    ) == TimelineResult((first,), (Takeover(BenchmarkKind.MAX_HR_BPM, first, hand),))


def test_resting_hand_cover_holds_and_the_run_restarts_after_it() -> None:
    hand = hand_benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        date(2024, 1, 20),
        60,
        applies_from=date(2024, 1, 1),
    )
    values = [_e(day, 67) for day in range(1, 35)]
    assert _points(derive_timeline(RESTING_RULE, values, [hand])) == [
        (date(2024, 1, 21), 67)
    ]


def test_derived_maximum_never_falls_against_a_derived_value() -> None:
    result = derive_timeline(MAX_RULE, [_e(1, 200), _e(2, 190), _e(3, 150)], [])
    assert _points(result) == [(date(2024, 1, 1), 200)]


def test_derived_maximum_needs_more_than_the_step_to_rise() -> None:
    result = derive_timeline(MAX_RULE, [_e(1, 200), _e(2, 202), _e(3, 203)], [])
    assert _points(result) == [(date(2024, 1, 1), 200), (date(2024, 1, 3), 203)]


def test_resting_still_falls_symmetrically() -> None:
    values = [_e(1, 60), *[_e(day, 50) for day in range(2, 16)]]
    assert _points(derive_timeline(RESTING_RULE, values, [])) == [
        (date(2024, 1, 1), 60),
        (date(2024, 1, 2), 50),
    ]


def test_future_hand_without_back_reach_does_not_mask_initial_entry() -> None:
    hand = hand_benchmark(BenchmarkKind.MAX_HR_BPM, date(2024, 1, 10), 196)
    assert _points(derive_timeline(MAX_RULE, [_e(2, 196), _e(12, 205)], [hand])) == [
        (date(2024, 1, 2), 196),
        (date(2024, 1, 12), 205),
    ]


@pytest.mark.parametrize("count", [13, 14], ids=["thirteen", "fourteen"])
def test_resting_confirmation_dates_and_binds_first_evidence(count: int) -> None:
    hand = hand_benchmark(BenchmarkKind.RESTING_HR_BPM, date(2023, 12, 31), 60)
    first = Evidence(
        date(2024, 1, 1),
        65,
        "first-key",
        "first-document.csv",
        "first-source:resting",
        "first-inputs",
        "first-summary",
    )
    following = [replace(_e(day, 69), key="first-key") for day in range(2, count + 1)]
    expected = Benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        None,
        65,
        date(2024, 1, 1),
        "Takes over from your hand-recorded 60 bpm of 2023-12-31: "
        "the evidence differed by more than 3 bpm.",
        None,
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="resting_hr_series_median",
            document="first-document.csv",
            inputs="first-inputs; differed from the value in force by more than "
            "3 bpm on each day from 2024-01-01 to 2024-01-14",
            citation="resting_hr_timeline_choice",
            series="first-source:resting",
        ),
    )
    assert derive_timeline(RESTING_RULE, [first, *following], [hand]) == (
        TimelineResult((), ())
        if count == 13
        else TimelineResult(
            (expected,), (Takeover(BenchmarkKind.RESTING_HR_BPM, expected, hand),)
        )
    )


@pytest.mark.parametrize("interruption", ["gap", "agree", "source"])
@pytest.mark.parametrize("tail_count", [13, 14], ids=["short", "complete"])
def test_resting_run_restarts_after_each_interruption(
    interruption: str, tail_count: int
) -> None:
    hand = hand_benchmark(BenchmarkKind.RESTING_HR_BPM, date(2023, 12, 31), 60)
    prefix = [_e(day, 65) for day in range(1, 14)]
    if interruption == "gap":
        middle: list[Evidence] = []
        start = 15
        key = "watch"
    elif interruption == "agree":
        middle = [_e(14, 63)]
        start = 15
        key = "watch"
    else:
        middle = []
        start = 14
        key = "other"
    tail = [_e(day, 68, key) for day in range(start, start + tail_count)]
    assert _points(
        derive_timeline(RESTING_RULE, [*prefix, *middle, *tail], [hand])
    ) == ([] if tail_count == 13 else [(date(2024, 1, start), 68)])


@pytest.mark.parametrize("tail_count", [13, 14], ids=["short", "complete"])
def test_hand_measurement_interrupts_resting_run(tail_count: int) -> None:
    hands = [
        hand_benchmark(BenchmarkKind.RESTING_HR_BPM, date(2023, 12, 31), 60),
        hand_benchmark(BenchmarkKind.RESTING_HR_BPM, date(2024, 1, 14), 61),
    ]
    values = [_e(day, 67) for day in range(1, 15 + tail_count)]
    assert _points(derive_timeline(RESTING_RULE, values, hands)) == (
        [] if tail_count == 13 else [(date(2024, 1, 15), 67)]
    )


def test_new_hand_recomputes_later_entries_against_new_value() -> None:
    values = [_e(1, 195), _e(3, 194), _e(4, 199), _e(5, 202)]
    old = hand_benchmark(BenchmarkKind.MAX_HR_BPM, date(2023, 12, 31), 188)
    new = hand_benchmark(BenchmarkKind.MAX_HR_BPM, date(2024, 1, 2), 191)
    before = derive_timeline(MAX_RULE, values, [old])
    after = derive_timeline(MAX_RULE, values, [new, old])
    assert (_points(before), _points(after)) == (
        [(date(2024, 1, 1), 195), (date(2024, 1, 4), 199), (date(2024, 1, 5), 202)],
        [
            (date(2024, 1, 1), 195),
            (date(2024, 1, 3), 194),
            (date(2024, 1, 4), 199),
            (date(2024, 1, 5), 202),
        ],
    )


@pytest.mark.parametrize("rule", [RESTING_RULE, MAX_RULE], ids=["resting", "maximum"])
def test_future_evidence_keeps_previously_decided_entries(rule: KindRule) -> None:
    prefix = [_e(1, 60)]
    future = [_e(day, 68) for day in range(2, 16)]
    before = derive_timeline(rule, prefix, [])
    after = derive_timeline(rule, [*prefix, *future], [])
    assert (_points(before), _points(after)) == (
        [(date(2024, 1, 1), 60)],
        [(date(2024, 1, 1), 60), (date(2024, 1, 2), 68)],
    )


def test_custom_rule_is_forwarded_to_selection_confirmation_and_provenance() -> None:
    rule = KindRule(
        BenchmarkKind.RESTING_HR_BPM,
        HrMethod.MAX_HR_SUSTAINED_PEAK,
        "custom-citation",
        7,
        2,
        False,
    )
    hand = hand_benchmark(BenchmarkKind.RESTING_HR_BPM, date(2023, 12, 31), 60)
    expected = Benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        None,
        69,
        date(2024, 1, 2),
        "Takes over from your hand-recorded 60 bpm of 2023-12-31: "
        "the evidence differed by more than 7 bpm.",
        None,
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-2",
            inputs="inputs-2; differed from the value in "
            "force by more than 7 bpm on each day from 2024-01-02 to 2024-01-03",
            citation="custom-citation",
            series="watch:metric-2",
        ),
    )
    assert derive_timeline(rule, [_e(1, 67), _e(2, 69), _e(3, 71)], [hand]) == (
        TimelineResult(
            (expected,), (Takeover(BenchmarkKind.RESTING_HR_BPM, expected, hand),)
        )
    )


@pytest.mark.parametrize("rule,value", [(RESTING_RULE, 211), (MAX_RULE, 31)])
def test_evidence_values_are_not_clamped(rule: KindRule, value: int) -> None:
    assert _points(derive_timeline(rule, [_e(1, value)], [])) == [
        (date(2024, 1, 1), value)
    ]


def test_result_is_frozen() -> None:
    assert vars(TimelineResult)["__dataclass_params__"].frozen is True


def test_ordinary_resting_confirmation_uses_first_summary_and_source() -> None:
    evidence = [
        _e(1, 60),
        Evidence(
            date(2024, 1, 2),
            65,
            "run-key",
            "run-first.csv",
            "first:metric",
            "run-first-inputs",
            "run-first-summary",
        ),
        *[replace(_e(day, 69), key="run-key") for day in range(3, 16)],
    ]
    expected = Benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        None,
        65,
        date(2024, 1, 2),
        "Derived by fitdocs from run-first-summary.",
        None,
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="resting_hr_series_median",
            document="run-first.csv",
            inputs="run-first-inputs; differed from "
            "the value in force by more than 3 bpm on each day from "
            "2024-01-02 to 2024-01-15",
            citation="resting_hr_timeline_choice",
            series="first:metric",
        ),
    )
    assert derive_timeline(RESTING_RULE, evidence, []).entries[1:] == (expected,)


def test_hand_inputs_remain_unchanged() -> None:
    hand = hand_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        date(2023, 12, 31),
        190,
        note="athlete note",
        applies_from=date(2023, 1, 1),
        measured=True,
    )
    recorded = [hand]
    derive_timeline(MAX_RULE, [_e(2, 197)], recorded)
    assert recorded == [
        Benchmark(
            BenchmarkKind.MAX_HR_BPM,
            None,
            190,
            date(2023, 12, 31),
            "athlete note",
            date(2023, 1, 1),
            BenchmarkSource(kind=BenchmarkSourceKind.MEASURED),
        )
    ]


def test_absent_series_is_preserved() -> None:
    evidence = replace(_e(1, 196), series=None)
    assert derive_timeline(MAX_RULE, [evidence], []).entries[0].source == (
        BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-1",
            inputs="inputs-1",
            citation="max_hr_timeline_choice",
            series=None,
        )
    )


def test_source_switch_confirmed_entry_names_new_source() -> None:
    evidence = [
        _e(1, 60, "old"),
        *[_e(day, 65, "old") for day in range(2, 15)],
        *[_e(day, 69, "new") for day in range(15, 29)],
    ]
    assert derive_timeline(RESTING_RULE, evidence, []).entries[1:] == (
        Benchmark(
            BenchmarkKind.RESTING_HR_BPM,
            None,
            69,
            date(2024, 1, 15),
            "Derived by fitdocs from summary-15.",
            None,
            BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="resting_hr_series_median",
                document="document-15",
                inputs="inputs-15; differed from the value in force by more than "
                "3 bpm on each day from 2024-01-15 to 2024-01-28",
                citation="resting_hr_timeline_choice",
                series="new:metric-15",
            ),
        ),
    )


def test_multiple_hand_takeovers_return_complete_ordered_pairs() -> None:
    old = hand_benchmark(BenchmarkKind.MAX_HR_BPM, date(2023, 12, 31), 188)
    new = hand_benchmark(BenchmarkKind.MAX_HR_BPM, date(2024, 1, 2), 191)
    first = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=195,
        measured_on=date(2024, 1, 1),
        note="Takes over from your hand-recorded 188 bpm of 2023-12-31: "
        "the evidence differed by more than 2 bpm.",
        applies_from=None,
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-1",
            inputs="inputs-1",
            citation="max_hr_timeline_choice",
            series="watch:metric-1",
        ),
    )
    second = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=199,
        measured_on=date(2024, 1, 4),
        note="Takes over from your hand-recorded 191 bpm of 2024-01-02: "
        "the evidence differed by more than 2 bpm.",
        applies_from=None,
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-4",
            inputs="inputs-4",
            citation="max_hr_timeline_choice",
            series="watch:metric-4",
        ),
    )
    third = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=202,
        measured_on=date(2024, 1, 5),
        note="Derived by fitdocs from summary-5.",
        applies_from=None,
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_hr_sustained_peak",
            document="document-5",
            inputs="inputs-5",
            citation="max_hr_timeline_choice",
            series="watch:metric-5",
        ),
    )
    expected = TimelineResult(
        (first, second, third),
        (
            Takeover(
                BenchmarkKind.MAX_HR_BPM,
                first,
                Benchmark(
                    kind=BenchmarkKind.MAX_HR_BPM,
                    discipline=None,
                    value=188,
                    measured_on=date(2023, 12, 31),
                    note=None,
                    applies_from=None,
                    source=None,
                ),
            ),
            Takeover(
                BenchmarkKind.MAX_HR_BPM,
                second,
                Benchmark(
                    kind=BenchmarkKind.MAX_HR_BPM,
                    discipline=None,
                    value=191,
                    measured_on=date(2024, 1, 2),
                    note=None,
                    applies_from=None,
                    source=None,
                ),
            ),
        ),
    )
    assert (
        derive_timeline(
            MAX_RULE, [_e(1, 195), _e(3, 190), _e(4, 199), _e(5, 202)], [new, old]
        )
        == expected
    )
