"""Synthetic archive entries exercise the pure merge contract."""

from datetime import date

import pytest

from fitdocs.wellness.merge import Conflict, MergeResult, merge
from fitdocs.wellness.model import DaySnapshot, Metric, SeriesValue
from fitdocs.wellness.spec import ParsedEntry, Supersession

DAY = date(2024, 2, 3)
HR = Metric.RESTING_HR_BPM
WEIGHT = Metric.WEIGHT_KG


def snapshot(
    value: float | None,
    *,
    revision: str | None = None,
    ordinal: int = 0,
    origin: str | None = None,
    day: date = DAY,
    metric: Metric = HR,
    covers: frozenset[Metric] | None = None,
) -> DaySnapshot:
    return DaySnapshot(
        day,
        frozenset({metric}) if covers is None else covers,
        {} if value is None else {metric: value},
        {} if origin is None else {metric: origin},
        revision,
        ordinal,
    )


def entry(
    ref: str,
    *snapshots: DaySnapshot,
    source: str = "source",
    format_id: str = "format",
    supersession: Supersession = Supersession.NONE,
) -> ParsedEntry:
    return ParsedEntry(ref, format_id, source, supersession, snapshots)


def default_order(metric: Metric) -> tuple[str, ...]:
    return ("source",)


def test_empty_entries() -> None:
    assert merge([], order_for=default_order) == MergeResult((), ())


@pytest.mark.parametrize("reverse", [False, True])
def test_later_revision_beats_value_and_ref_order(reverse: bool) -> None:
    entries = [
        entry("z", snapshot(90, revision="2024-01-01", origin="older")),
        entry("a", snapshot(40, revision="2024-02-01", origin="newer")),
        entry("zz", snapshot(100, origin="unrevised")),
    ]
    if reverse:
        entries.reverse()
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", "newer", 40, True),), ()
    )


def test_later_covered_absence_removes_older_value() -> None:
    entries = [
        entry("z", snapshot(70, revision="2024-01-01")),
        entry("a", snapshot(None, revision="2024-02-01")),
    ]
    assert merge(entries, order_for=default_order) == MergeResult((), ())


def test_later_uncovered_metric_does_not_remove_value() -> None:
    entries = [
        entry("z", snapshot(70, revision="2024-01-01", origin="device")),
        entry("a", snapshot(None, revision="2024-02-01", covers=frozenset())),
    ]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", "device", 70, True),), ()
    )


def test_unrevised_absence_beside_present_value() -> None:
    entries = [entry("a", snapshot(60)), entry("z", snapshot(None))]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", None, 60, True),), ()
    )


@pytest.mark.parametrize("revision", [None, "2024-02-01"])
def test_equal_values_use_greatest_ref_then_ordinal_origin_without_conflict(
    revision: str | None,
) -> None:
    entries = [
        entry(
            "z",
            snapshot(60, revision=revision, ordinal=0, origin="wrong-ordinal"),
            snapshot(60, revision=revision, ordinal=1, origin="winner"),
        ),
        entry("a", snapshot(60, revision=revision, ordinal=9, origin="wrong-ref")),
    ]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", "winner", 60, True),), ()
    )


@pytest.mark.parametrize("revision", [None, "2024-02-01"])
def test_conflict_selects_ref_before_ordinal_and_sorts_other_pairs(
    revision: str | None,
) -> None:
    entries = [
        entry(
            "z",
            snapshot(80, revision=revision, ordinal=0, origin="wrong-ordinal"),
            snapshot(40, revision=revision, ordinal=1, origin="winner"),
        ),
        entry(
            "b",
            snapshot(75, revision=revision, ordinal=8),
            snapshot(50, revision=revision, ordinal=7),
        ),
        entry("a", snapshot(90, revision=revision, ordinal=9, origin="wrong-ref")),
        entry("c", snapshot(40, revision=revision, ordinal=0)),
        entry("zz", snapshot(None, revision=revision, ordinal=10)),
    ]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", "winner", 40, True),),
        (
            Conflict(
                DAY,
                HR,
                "source",
                "z",
                40,
                (("a", 90), ("b", 50), ("b", 75), ("c", 40), ("z", 80)),
            ),
        ),
    )


def test_older_disagreement_is_not_a_conflict() -> None:
    entries = [
        entry("z", snapshot(90, revision="1")),
        entry("a", snapshot(40, revision="2")),
        entry("b", snapshot(40, revision="2")),
    ]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", None, 40, True),), ()
    )


def test_two_latest_entries_of_same_format_raise() -> None:
    entries = [
        entry("a", supersession=Supersession.LATEST_ENTRY),
        entry("b", supersession=Supersession.LATEST_ENTRY),
    ]
    with pytest.raises(ValueError):
        merge(entries, order_for=default_order)


def test_latest_format_beside_none_and_distinct_latest_format() -> None:
    entries = [
        entry("a", snapshot(60), supersession=Supersession.LATEST_ENTRY),
        entry(
            "b",
            snapshot(None),
            format_id="other",
            supersession=Supersession.LATEST_ENTRY,
        ),
        entry("c", snapshot(60), format_id="plain"),
        entry("d", snapshot(60), format_id="plain"),
    ]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, HR, "source", None, 60, True),), ()
    )


def test_metric_precedence_retains_all_sources_and_skips_missing_top() -> None:
    entries = [
        entry("z", snapshot(90), snapshot(71, metric=WEIGHT), source="a"),
        entry("a", snapshot(80), snapshot(None, metric=WEIGHT), source="m"),
        entry("m", snapshot(60), snapshot(81, metric=WEIGHT), source="z"),
    ]

    def order_for(metric: Metric) -> tuple[str, ...]:
        return ("m", "z", "a") if metric == HR else ("m", "a", "z")

    assert merge(entries, order_for=order_for) == MergeResult(
        (
            SeriesValue(DAY, HR, "a", None, 90, False),
            SeriesValue(DAY, HR, "m", None, 80, True),
            SeriesValue(DAY, HR, "z", None, 60, False),
            SeriesValue(DAY, WEIGHT, "a", None, 71, True),
            SeriesValue(DAY, WEIGHT, "z", None, 81, False),
        ),
        (),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_values_and_conflicts_sorted_by_day_metric_name_source(reverse: bool) -> None:
    later = date(2024, 2, 4)
    rows = [
        (later, HR, "z", 46),
        (DAY, HR, "a", 43),
        (later, Metric.MAX_HR_BPM, "a", 44),
        (DAY, Metric.MAX_HR_BPM, "z", 42),
        (later, HR, "a", 47),
        (DAY, HR, "z", 41),
        (later, Metric.MAX_HR_BPM, "z", 45),
        (DAY, Metric.MAX_HR_BPM, "a", 40),
    ]
    entries = [
        entry(
            f"{source}-winner",
            *(
                snapshot(value, day=day, metric=metric, ordinal=index)
                for index, (day, metric, row_source, value) in enumerate(rows)
                if row_source == source
            ),
            source=source,
        )
        for source in ["z", "a"]
    ] + [
        entry(
            f"{source}-loser",
            *(
                snapshot(value + 50, day=day, metric=metric, ordinal=index)
                for index, (day, metric, row_source, value) in enumerate(rows)
                if row_source == source
            ),
            source=source,
        )
        for source in ["a", "z"]
    ]
    if reverse:
        entries.reverse()
    expected_rows = [
        (DAY, Metric.MAX_HR_BPM, "a", 40),
        (DAY, Metric.MAX_HR_BPM, "z", 42),
        (DAY, HR, "a", 43),
        (DAY, HR, "z", 41),
        (later, Metric.MAX_HR_BPM, "a", 44),
        (later, Metric.MAX_HR_BPM, "z", 45),
        (later, HR, "a", 47),
        (later, HR, "z", 46),
    ]
    assert merge(entries, order_for=lambda metric: ("z", "a")) == MergeResult(
        tuple(
            SeriesValue(day, metric, source, None, value, source == "z")
            for day, metric, source, value in expected_rows
        ),
        tuple(
            Conflict(
                day,
                metric,
                source,
                f"{source}-winner",
                value,
                ((f"{source}-loser", value + 50),),
            )
            for day, metric, source, value in expected_rows
        ),
    )


def test_shared_covers_with_one_missing_value_resolves_metrics_independently() -> None:
    covers = frozenset({HR, WEIGHT})
    entries = [
        entry("older", DaySnapshot(DAY, covers, {HR: 70, WEIGHT: 90}, {}, "1", 0)),
        entry(
            "newer", DaySnapshot(DAY, covers, {WEIGHT: 71}, {WEIGHT: "scale"}, "2", 0)
        ),
    ]
    assert merge(entries, order_for=default_order) == MergeResult(
        (SeriesValue(DAY, WEIGHT, "source", "scale", 71, True),), ()
    )
