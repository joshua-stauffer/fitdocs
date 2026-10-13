"""Synthetic format contract checks."""

import io
import json
from datetime import date
from pathlib import Path

import pytest

from fitdocs.wellness.formats import intervals
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import WellnessFormatError
from tests.wellness.builders_intervals import (
    intervals_delivery_bytes,
    intervals_list_bytes,
    intervals_record,
)

# All mapped measurements are distinct, including the seven fractional ratings.
FIELDS = {
    "restingHR": ("resting_hr_bpm", 51),
    "hrv": ("hrv_rmssd_ms", 62),
    "hrvSDNN": ("hrv_sdnn_ms", 73),
    "sleepSecs": ("sleep_s", 28004),
    "avgSleepingHR": ("sleep_hr_bpm", 45),
    "respiration": ("respiration_brpm", 16),
    "spO2": ("spo2_pct", 97),
    "steps": ("steps", 8018),
    "vo2max": ("vo2max_ml_per_kg_min", 49),
    "weight": ("weight_kg", 80),
    "fatigue": ("fatigue_rating", 1.1),
    "mood": ("mood_rating", 1.2),
    "motivation": ("motivation_rating", 1.3),
    "soreness": ("soreness_rating", 1.4),
    "stress": ("stress_rating", 1.5),
    "injury": ("injury_rating", 1.6),
    "hydration": ("hydration_rating", 1.7),
}


def parsed(payload: bytes) -> tuple[DaySnapshot, ...]:
    return tuple(intervals.parse(io.BytesIO(payload)))


def test_single_value() -> None:
    assert parsed(intervals_list_bytes([intervals_record("2025-02-03", restingHR=51)]))[
        0
    ].values == {Metric.RESTING_HR_BPM: 51}


@pytest.mark.parametrize("field", FIELDS)
def test_field_mapping(field: str) -> None:
    record = intervals_record(
        "2025-02-03", **{key: value for key, (_, value) in FIELDS.items()}
    )
    metric, expected = FIELDS[field]
    assert parsed(intervals_list_bytes([record]))[0].values[Metric(metric)] == expected


def test_declarations() -> None:
    assert intervals.DELIVERY_FORMAT == "fitdocs.intervals-icu-wellness"
    assert intervals.DELIVERY_VERSION == 1
    assert {key: value.value for key, value in intervals.FIELD_METRICS.items()} == {
        key: metric for key, (metric, _) in FIELDS.items()
    }
    assert (
        intervals.SOURCE.id,
        intervals.SOURCE.display_name,
        intervals.SOURCE.kind.value,
    ) == ("intervals-icu", "intervals.icu", "relay")
    form = intervals.FORMAT
    assert (
        form.id,
        form.display_name,
        form.source,
        form.suffixes,
        form.archive_form.value,
        form.archived_suffix,
        form.rules_version,
        form.metrics,
        form.supersession.value,
        form.extract,
        form.entry_order,
    ) == (
        "intervals-icu",
        "intervals.icu",
        intervals.SOURCE,
        frozenset({".json"}),
        "original",
        ".json",
        1,
        frozenset(Metric(metric) for metric, _ in FIELDS.values()),
        "none",
        None,
        None,
    )


@pytest.mark.parametrize(
    "payload,expected",
    [
        ([{"id": "2025-02-03", "restingHR": 51}], True),
        ([{"id": "2025-02-03", "updated": None}], True),
        ([{"id": "2025-02-03"}], False),
        ([], False),
        ([{"restingHR": 51}], False),
        ([{"calendarDate": "2025-02-03", "restingHeartRate": 51}], False),
        ([{"id": 20250203, "restingHR": 51}], False),
        ([{"id": "20250203", "restingHR": 51}], False),
        ([{"id": "2025-02-03", "restingHR": 51}, 1], False),
        ({"format": "fitdocs.intervals-icu-wellness", "version": 1}, True),
        ({"format": "fitdocs.intervals-icu-wellness", "version": 2}, False),
        ({"format": "other", "version": 1}, False),
    ],
)
def test_recognition(tmp_path: Path, payload: object, expected: bool) -> None:
    path = tmp_path / "synthetic.json"
    path.write_bytes(json.dumps(payload).encode())
    assert intervals.FORMAT.recognize(CandidateProbe.open(path)) is expected


def test_snapshot() -> None:
    records = [
        intervals_record(
            "2025-02-04", updated="2025-02-03T22:30:01+02:00", restingHR=51
        ),
        intervals_record("2025-02-03", updated="2025-02-03T20:30:01Z", restingHR=52),
    ]
    first, second = parsed(intervals_list_bytes(records))
    assert (first.day, second.day) == (date(2025, 2, 4), date(2025, 2, 3))
    assert (first.ordinal, second.ordinal) == (0, 1)
    assert first.revision == second.revision == "2025-02-03T20:30:01.000000Z"
    assert first.covers == frozenset(Metric(metric) for metric, _ in FIELDS.values())


@pytest.mark.parametrize("updated", [None, "broken", "2025-02-03T12:00:00", 123])
def test_absent_revision(updated: object) -> None:
    assert (
        parsed(intervals_list_bytes([intervals_record("2025-02-03", updated=updated)]))[
            0
        ].revision
        is None
    )


@pytest.mark.parametrize("value", [None, 0, -1, 251, float("nan"), float("inf")])
def test_absent_value(value: object) -> None:
    assert (
        parsed(intervals_list_bytes([intervals_record("2025-02-03", restingHR=value)]))[
            0
        ].values
        == {}
    )


@pytest.mark.parametrize("value", [True, False, "51", [], {}])
def test_invalid_number(value: object) -> None:
    with pytest.raises(WellnessFormatError):
        parsed(intervals_list_bytes([intervals_record("2025-02-03", restingHR=value)]))


@pytest.mark.parametrize("day", ["2025-02-30", "20250203", "bad", None, 1])
def test_invalid_day(day: object) -> None:
    with pytest.raises(WellnessFormatError):
        parsed(intervals_list_bytes([{"id": day}]))


def test_duplicate() -> None:
    with pytest.raises(WellnessFormatError):
        parsed(intervals_list_bytes([{"id": "2025-02-03"}, {"id": "2025-02-03"}]))


def test_origins_and_computed() -> None:
    record = intervals_record(
        "2025-02-03",
        restingHR=51,
        hrv=None,
        ctl=101,
        atl=102,
        rampRate=103,
        ctlLoad=104,
        atlLoad=105,
        sportInfo={"vo2max": 88},
        sleepScore=106,
        readiness=107,
        invented=108,
    )
    snapshot = parsed(
        intervals_delivery_bytes(
            [record], origins={"restingHR": "garmin", "hrv": "apple", "weight": "other"}
        )
    )[0]
    assert snapshot.values == {Metric.RESTING_HR_BPM: 51}
    assert snapshot.origins == {Metric.RESTING_HR_BPM: "garmin"}
    assert parsed(intervals_list_bytes([record]))[0].origins == {}


@pytest.mark.parametrize(
    "origins", [{"hrv": "Bad"}, {"hrv": 1}, {"hrv": None}, [], None]
)
def test_invalid_origins(origins: object) -> None:
    with pytest.raises(WellnessFormatError):
        parsed(
            json.dumps(
                {
                    "format": "fitdocs.intervals-icu-wellness",
                    "version": 1,
                    "records": [{"id": "2025-02-03"}],
                    "origins": origins,
                }
            ).encode()
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"broken",
        b"{}",
        b"1",
        b"[1]",
        b'{"format":"fitdocs.intervals-icu-wellness","version":2,"records":[]}',
        b'{"format":"fitdocs.intervals-icu-wellness","version":1,"records":{}}',
    ],
)
def test_invalid_container(payload: bytes) -> None:
    with pytest.raises(WellnessFormatError):
        parsed(payload)


def test_builders(tmp_path: Path) -> None:
    assert intervals_record(date(2025, 2, 3), restingHR=51, invented="é") == {
        "id": "2025-02-03",
        "updated": None,
        "restingHR": 51,
        "invented": "é",
    }
    assert intervals_record("2025-02-03", updated="stamp", ctl=12) == {
        "id": "2025-02-03",
        "updated": "stamp",
        "ctl": 12,
    }
    assert (
        intervals_list_bytes([{"id": "2025-02-04"}, {"id": "2025-02-03"}])
        == b'[{"id": "2025-02-04"}, {"id": "2025-02-03"}]'
    )
    records = [
        {"id": "2025-02-04", "restingHR": 52},
        {"id": "2025-02-03", "restingHR": 51, "note": "é"},
    ]
    payload = intervals_delivery_bytes(records, origins={"restingHR": "garmin"})
    assert (
        payload
        == (
            '{"format":"fitdocs.intervals-icu-wellness",'
            '"origins":{"restingHR":"garmin"},"records":['
            '{"id":"2025-02-03","note":"é","restingHR":51},'
            '{"id":"2025-02-04","restingHR":52}],"version":1}\n'
        ).encode()
    )
    assert (
        intervals_delivery_bytes([])
        == b'{"format":"fitdocs.intervals-icu-wellness","records":[],"version":1}\n'
    )
    path = tmp_path / "delivery.json"
    path.write_bytes(payload)
    assert intervals.FORMAT.recognize(CandidateProbe.open(path)) is True
    assert [snapshot.values for snapshot in parsed(payload)] == [
        {Metric.RESTING_HR_BPM: 51},
        {Metric.RESTING_HR_BPM: 52},
    ]
