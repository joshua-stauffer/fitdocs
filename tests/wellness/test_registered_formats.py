"""Recognition through the shipped declarations and published payload builders."""

from pathlib import Path
from typing import Literal

import pytest

from fitdocs.wellness import probe, registry
from fitdocs.wellness.formats import garmin, intervals
from fitdocs.wellness.probe import HEAD_BYTES, CandidateProbe
from fitdocs.wellness.spec import FormatSpec
from tests.wellness._helpers import CountingOpener
from tests.wellness.builders_garmin import (
    garmin_biometrics_record,
    garmin_file_bytes,
    garmin_file_name,
    garmin_maxmet_record,
    garmin_sleep_record,
    garmin_uds_record,
    hydration_decoy_bytes,
)
from tests.wellness.builders_intervals import (
    intervals_delivery_bytes,
    intervals_list_bytes,
    intervals_record,
)

DAY = "2000-01-02"
RECORD = intervals_record(DAY, restingHR=57)
SHIPPED = (
    intervals.FORMAT,
    garmin.UDS_FORMAT,
    garmin.SLEEP_FORMAT,
    garmin.MAXMET_FORMAT,
    garmin.BIOMETRICS_FORMAT,
)


def test_shipped_sources() -> None:
    assert registry.SOURCES == (intervals.SOURCE, garmin.SOURCE)


def test_shipped_formats() -> None:
    assert registry.FORMATS == SHIPPED


def test_shipped_registry_validates() -> None:
    registry.validate_registry()


def test_shipped_suffixes() -> None:
    assert registry.candidate_suffixes() == frozenset({".json"})


def test_shipped_source_order() -> None:
    assert registry.default_source_order() == ("garmin-export", "intervals-icu")


GARMIN_KINDS: tuple[
    tuple[Literal["uds", "sleep", "maxmet", "biometrics"], FormatSpec], ...
] = (
    ("uds", garmin.UDS_FORMAT),
    ("sleep", garmin.SLEEP_FORMAT),
    ("maxmet", garmin.MAXMET_FORMAT),
    ("biometrics", garmin.BIOMETRICS_FORMAT),
)

ACCEPTED = [
    pytest.param(
        "renamed.JSON",
        intervals_list_bytes([RECORD]),
        intervals.FORMAT,
        id="intervals-list",
    ),
    pytest.param(
        "renamed.JSON",
        intervals_delivery_bytes([RECORD]),
        intervals.FORMAT,
        id="intervals-envelope",
    ),
    pytest.param(
        "renamed.JSON",
        garmin_file_bytes([garmin_uds_record(DAY, totalSteps=1234)]),
        garmin.UDS_FORMAT,
        id="uds",
    ),
    pytest.param(
        "renamed.JSON",
        garmin_file_bytes([garmin_sleep_record(DAY, deep_s=123)]),
        garmin.SLEEP_FORMAT,
        id="sleep",
    ),
    pytest.param(
        "renamed.JSON",
        garmin_file_bytes(
            [
                garmin_maxmet_record(
                    DAY, sport="RUNNING", vo2max=53, updated="2000-01-02T12:00:00Z"
                )
            ]
        ),
        garmin.MAXMET_FORMAT,
        id="maxmet",
    ),
    pytest.param(
        "renamed.JSON",
        garmin_file_bytes(
            [
                garmin_biometrics_record(
                    DAY, weight_g=73123, measured_at="2000-01-02T12:00:00Z"
                )
            ]
        ),
        garmin.BIOMETRICS_FORMAT,
        id="biometrics",
    ),
    *[
        pytest.param(
            garmin_file_name(kind, DAY, DAY).upper(),
            garmin_file_bytes([]),
            form,
            id=f"empty-{kind}",
        )
        for kind, form in GARMIN_KINDS
    ],
]


@pytest.mark.parametrize("folder", ["inbox", "elsewhere/nested"])
@pytest.mark.parametrize("name,payload,expected", ACCEPTED)
def test_registered_recognition(
    tmp_path: Path, folder: str, name: str, payload: bytes, expected: FormatSpec
) -> None:
    directory = tmp_path / folder
    directory.mkdir(parents=True)
    path = directory / name
    path.write_bytes(payload)
    assert registry.recognize(CandidateProbe.open(path)) == registry.Recognized(
        expected
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(hydration_decoy_bytes(), id="hydration"),
        pytest.param(b'{"a":1}', id="object"),
        pytest.param(b"not JSON", id="non-json"),
        pytest.param(b"[]", id="empty-unnamed"),
    ],
)
def test_registered_decoys(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "arbitrary.json"
    path.write_bytes(payload)
    assert registry.recognize(CandidateProbe.open(path)) == registry.NotRecognized(
        "no supported wellness format reads this file"
    )


def test_registered_oversize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = intervals_list_bytes([RECORD])
    monkeypatch.setattr(probe, "JSON_PROBE_LIMIT", len(payload) - 1)
    path = tmp_path / "large.json"
    path.write_bytes(payload)
    assert registry.recognize(CandidateProbe.open(path)) == registry.NotRecognized(
        "no supported wellness format reads this file"
    )


def test_registered_lazy_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "partial.json"
    path.write_bytes(b" " * HEAD_BYTES + intervals_list_bytes([RECORD]))
    opener = CountingOpener(path, fail_past_head=True)
    opener.install(monkeypatch)
    candidate = CandidateProbe.open(path)
    with pytest.raises(OSError, match="candidate unavailable past head"):
        registry.recognize(candidate)


def test_registered_ambiguous_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "overlap.json"
    path.write_bytes(
        garmin_file_bytes(
            [
                garmin_uds_record(
                    DAY, sleepStartTimestampGMT="2000-01-01T22:00:00Z", vo2MaxValue=53
                )
            ]
        )
    )
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    assert registry.recognize(CandidateProbe.open(path)) == registry.NotRecognized(
        "multiple wellness formats read this file: "
        "garmin-uds, garmin-sleep, garmin-maxmet"
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
