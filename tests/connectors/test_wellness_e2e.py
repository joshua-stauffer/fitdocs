"""Synthetic intervals wellness through the CLI, inbox, archive and series."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.http import HttpResponse
from fitdocs.connectors.pull import PullReport, WellnessPullReport
from fitdocs.sync import drain
from fitdocs.wellness import read_series
from fitdocs.wellness.engine import SeriesStatus
from tests.connectors.conftest import FakeTransport
from tests.fixtures import builder

_NOW = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(
    seconds=builder.FIT_TIMESTAMP_BASE
)
_DAY = _NOW.date()
_RECORDS = [
    {"id": str(_DAY), "updated": "revision-m", "restingHR": 41, "hrv": 63},
    {
        "id": str(_DAY - timedelta(days=2)),
        "updated": "revision-z",
        "restingHR": 53,
        "hrv": 72,
    },
    {
        "id": str(_DAY - timedelta(days=1)),
        "updated": "revision-a",
        "restingHR": 47,
        "hrv": 91,
    },
]
_PAYLOAD = (
    json.dumps(
        {
            "format": "fitdocs.intervals-icu-wellness",
            "version": 1,
            "origins": {"restingHR": "garmin", "hrv": "garmin"},
            "records": [_RECORDS[1], _RECORDS[2], _RECORDS[0]],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    + b"\n"
)
_SHA = hashlib.sha256(_PAYLOAD).hexdigest()
_DELIVERY = f"intervals/wellness-{_DAY - timedelta(days=2)}_{_DAY}.json"
_ARCHIVE = f"wellness-archive/intervals-icu/{_SHA}.json"


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> _FrozenDatetime:
        frozen = cls.fromtimestamp(_NOW.timestamp(), tz or UTC)
        return frozen if tz is not None else frozen.replace(tzinfo=None)


def _ok(value: object) -> HttpResponse:
    return HttpResponse(200, {}, json.dumps(value).encode())


def _files(root: Path, pattern: str) -> tuple[tuple[str, bytes, int], ...]:
    return tuple(
        (str(path.relative_to(root)), path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.glob(pattern))
        if path.is_file()
    )


def test_intervals_pull_sync_archives_series_and_second_pull_cleans_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n"
        '[connectors.intervals]\nconnector = "intervals"\nwellness = true\n'
    )
    monkeypatch.setenv(env_var_name("intervals", "api_key"), "ik-synthetic-7Q2x9")
    monkeypatch.setattr(cli, "datetime", _FrozenDatetime)
    monkeypatch.setattr(cli, "_local_tz", lambda: timezone(timedelta(hours=-7)))
    # One activity window, twelve historical wellness windows, then athlete.
    transport = FakeTransport(
        [
            _ok([]),
            *[_ok(_RECORDS)] * 12,
            _ok({"garmin_wellness_keys": ["hrv", "restingHR"]}),
            _ok([]),
            _ok(_RECORDS),
        ]
    )
    monkeypatch.setattr(cli, "_connector_transport", lambda: transport)
    before_drain: list[tuple[object, ...]] = []
    drain_reports: list[Any] = []
    pull_reports: list[PullReport] = []
    real_drain = drain
    real_report_drain = cli._report_drain
    real_report_pull = cli._report_pull

    def capture_drain(*args: Any, **kwargs: Any) -> Any:
        before_drain.append(
            (
                _files(tmp_path, "inbox/intervals/*"),
                _files(tmp_path, "wellness-archive/*/*.json"),
                _files(tmp_path, "wellness/*"),
            )
        )
        return real_drain(*args, **kwargs)

    def capture_report_drain(report: Any, **kwargs: Any) -> None:
        drain_reports.append(report)
        real_report_drain(report, **kwargs)

    def capture_report_pull(report: PullReport) -> None:
        pull_reports.append(report)
        real_report_pull(report)

    monkeypatch.setattr(cli, "drain", capture_drain)
    monkeypatch.setattr(cli, "_report_drain", capture_report_drain)
    monkeypatch.setattr(cli, "_report_pull", capture_report_pull)
    assert (
        _files(tmp_path, "inbox/intervals/*"),
        _files(tmp_path, "wellness-archive/*/*.json"),
        read_series(tmp_path).values,
    ) == ((), (), ())

    runner = CliRunner()
    arguments = ["pull", "intervals", "--sync", "--no-prompt", "--out", str(tmp_path)]
    first = runner.invoke(cli.app, arguments)
    assert first.exit_code == 0, first.output
    delivered = _files(tmp_path, "inbox/intervals/*")
    assert tuple((path, data) for path, data, _mtime in delivered) == (
        (f"inbox/{_DELIVERY}", _PAYLOAD),
    )
    assert before_drain == [(delivered, (), ())]
    archive = _files(tmp_path, "wellness-archive/*/*.json")
    assert tuple((path, data) for path, data, _mtime in archive) == (
        (_ARCHIVE, _PAYLOAD),
    )
    assert [
        (str(value.day), value.metric.value, value.source, value.origin, value.value)
        for value in read_series(tmp_path).values
    ] == [
        (str(_DAY - timedelta(days=2)), "hrv_rmssd_ms", "intervals-icu", "garmin", 72),
        (
            str(_DAY - timedelta(days=2)),
            "resting_hr_bpm",
            "intervals-icu",
            "garmin",
            53,
        ),
        (str(_DAY - timedelta(days=1)), "hrv_rmssd_ms", "intervals-icu", "garmin", 91),
        (
            str(_DAY - timedelta(days=1)),
            "resting_hr_bpm",
            "intervals-icu",
            "garmin",
            47,
        ),
        (str(_DAY), "hrv_rmssd_ms", "intervals-icu", "garmin", 63),
        (str(_DAY), "resting_hr_bpm", "intervals-icu", "garmin", 41),
    ]
    series = _files(tmp_path, "wellness/*")
    assert (
        [report.wellness_series.status for report in drain_reports],
        bool(series),
    ) == (
        [SeriesStatus.REBUILT],
        True,
    )

    second = runner.invoke(cli.app, arguments)
    assert second.exit_code == 0, second.output
    assert (
        [
            (report.instances[0].removed, report.instances[0].wellness)
            for report in pull_reports[1:]
        ],
        _files(tmp_path, "inbox/intervals/*"),
    ) == ([((_DELIVERY,), WellnessPullReport(3, 3, (), (), (), (), (), None))], ())
    assert before_drain[1:] == [((), archive, series)]
    assert (
        _files(tmp_path, "wellness-archive/*/*.json"),
        _files(tmp_path, "wellness/*"),
        [report.wellness_series.status for report in drain_reports[1:]],
    ) == (archive, series, [SeriesStatus.UNCHANGED])


def test_file_snapshot_records_exact_bytes_mtimes_and_order(tmp_path: Path) -> None:
    (tmp_path / "zeta.json").write_bytes(b"last\x00")
    (tmp_path / "alpha.json").write_bytes(b"first\xff")
    (tmp_path / "directory.json").mkdir()
    os.utime(tmp_path / "zeta.json", ns=(91_000_000_003, 91_000_000_003))
    os.utime(tmp_path / "alpha.json", ns=(87_000_000_001, 87_000_000_001))
    assert _files(tmp_path, "*.json") == (
        ("alpha.json", b"first\xff", 87_000_000_001),
        ("zeta.json", b"last\x00", 91_000_000_003),
    )
