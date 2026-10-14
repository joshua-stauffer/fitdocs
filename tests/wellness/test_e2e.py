"""Synthetic wellness deliveries through the real CLI and index."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import socket
from pathlib import Path
from typing import Any, NoReturn

import pytest
from typer.testing import CliRunner, Result

from fitdocs.cli import app
from fitdocs.quarantine import load_quarantine
from fitdocs.wellness import read_series
from tests.fixtures import builder
from tests.wellness.builders_garmin import (
    garmin_biometrics_record,
    garmin_file_bytes,
    garmin_maxmet_record,
    garmin_sleep_record,
    garmin_uds_record,
)
from tests.wellness.builders_intervals import (
    intervals_delivery_bytes,
    intervals_list_bytes,
    intervals_record,
)

runner = CliRunner()
_SETTINGS = "[inbox]\nsettle_seconds = 0\n[tiles]\nenabled = false\n"


@pytest.fixture(autouse=True)
def _isolated_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, directory in (
        ("HOME", "home"),
        ("FITDOCS_INDEX_DIR", "index"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        monkeypatch.setenv(name, str(tmp_path / directory))

    def no_socket(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("wellness CLI attempted a socket")

    monkeypatch.setattr(socket, "socket", no_socket)


def _root(tmp_path: Path, *, move: bool = False) -> Path:
    root = tmp_path / "data"
    (root / "inbox").mkdir(parents=True)
    settings = (
        _SETTINGS.replace(
            "settle_seconds",
            'disposition = "move"\nprocessed_dir = "processed"\nsettle_seconds',
        )
        if move
        else _SETTINGS
    )
    (root / "fitdocs.toml").write_text(settings)
    return root


def _invoke(root: Path, command: str, *args: str) -> Result:
    return runner.invoke(app, [command, *args, "--out", str(root)])


def _counts(result: Result) -> dict[str, int]:
    return {
        label.strip(): int(count)
        for label, count in re.findall(
            r"│ ([^│\n]+) │\s*(\d+) │", result.stdout.split("└", 1)[0]
        )
    }


def _series_state(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (root / "wellness").iterdir()
        if path.is_file()
    }


def _rows(root: Path) -> list[list[object]]:
    result = _invoke(
        root,
        "query",
        "SELECT day, metric, source, origin, value, canonical "
        "FROM wellness_daily ORDER BY day, metric, source",
        "--format",
        "json",
    )
    if result.exit_code:
        pytest.fail(f"query failed: {result.output} {result.exception}")
    rows: list[list[object]] = json.loads(result.stdout)["rows"]
    return rows


def test_mixed_cli_lifecycle_and_automatic_index_refresh(tmp_path: Path) -> None:
    root = _root(tmp_path)
    inbox = root / "inbox"
    deliveries = {
        "list.json": intervals_list_bytes(
            [
                intervals_record(
                    "2028-06-12", updated="2028-06-13T10:00:00Z", restingHR=43
                )
            ]
        ),
        "envelope.json": intervals_delivery_bytes(
            [intervals_record("2028-06-13", hrv=61)], origins={"hrv": "oura"}
        ),
        "uds.json": garmin_file_bytes(
            [garmin_uds_record("2028-06-14", totalSteps=7654)]
        ),
        "sleep.json": garmin_file_bytes(
            [garmin_sleep_record("2028-06-15", deep_s=3600, light_s=7200, rem_s=1800)]
        ),
        "maxmet.json": garmin_file_bytes(
            [
                garmin_maxmet_record(
                    "2028-06-16",
                    sport="RUNNING",
                    vo2max=52,
                    updated="2028-06-16T08:00:00Z",
                )
            ]
        ),
        "weight.json": garmin_file_bytes(
            [
                garmin_biometrics_record(
                    "2028-06-17", weight_g=73250, measured_at="2028-06-17T09:00:00Z"
                )
            ]
        ),
    }
    for name, payload in deliveries.items():
        (inbox / name).write_bytes(payload)
    (inbox / "activity.fit").write_bytes(builder.small_sport_fit_bytes(8913, "running"))
    identity = builder._file_id(4200000081)
    identity["type"] = "monitoring_b"
    (inbox / "monitoring.fit").write_bytes(builder.encode([identity]))
    (inbox / "unknown.json").write_bytes(b'{"unrelated":123}')
    (inbox / "ignored.gpx").write_bytes(b"<gpx/>")

    first = _invoke(root, "sync", "--no-prompt")
    assert first.exit_code == 0, (first.output, first.exception)
    assert _counts(first) == {
        "Written": 1,
        "Skipped": 1,
        "Failed": 0,
        "Warnings": 1,
        "Deferred": 0,
        "Quarantined": 0,
        "Moved": 0,
        "Move failures": 0,
        "Unrecognized": 1,
        "Wellness archived": 6,
        "Wellness skipped": 0,
        "Wellness failed": 0,
    }
    expected: list[list[object]] = [
        ["2028-06-12", "resting_hr_bpm", "intervals-icu", None, 43.0, True],
        ["2028-06-13", "hrv_rmssd_ms", "intervals-icu", "oura", 61.0, True],
        ["2028-06-14", "steps", "garmin-export", "garmin", 7654.0, True],
        ["2028-06-15", "sleep_deep_s", "garmin-export", "garmin", 3600.0, True],
        ["2028-06-15", "sleep_light_s", "garmin-export", "garmin", 7200.0, True],
        ["2028-06-15", "sleep_rem_s", "garmin-export", "garmin", 1800.0, True],
        ["2028-06-15", "sleep_s", "garmin-export", "garmin", 12600.0, True],
        [
            "2028-06-16",
            "vo2max_run_ml_per_kg_min",
            "garmin-export",
            "garmin",
            52.0,
            True,
        ],
        ["2028-06-17", "weight_kg", "garmin-export", "garmin", 73.25, True],
    ]
    actual = [
        [v.day.isoformat(), v.metric.value, v.source, v.origin, v.value, v.canonical]
        for v in read_series(root).values
    ]
    assert actual == expected
    indexed = _invoke(root, "index")
    assert indexed.exit_code == 0, indexed.output
    assert _rows(root) == expected
    checked = _invoke(root, "check")
    assert checked.exit_code == 0, checked.output

    before = _series_state(root)
    second = _invoke(root, "sync", "--no-prompt")
    assert second.exit_code == 0, second.output
    assert (
        _counts(second)["Wellness archived"],
        _counts(second)["Wellness skipped"],
    ) == (0, 6)
    assert "Wellness series:" not in second.stdout
    assert _series_state(root) == before
    regenerated = _invoke(root, "regen")
    assert regenerated.exit_code == 0, regenerated.output
    assert "Wellness series:" not in regenerated.stdout
    assert _series_state(root) == before

    (inbox / "list.json").write_bytes(
        intervals_list_bytes(
            [
                intervals_record(
                    "2028-06-12", updated="2028-06-14T10:00:00Z", restingHR=47
                )
            ]
        )
    )
    changed = _invoke(root, "sync", "--no-prompt")
    assert changed.exit_code == 0, changed.output
    assert "Wellness series: rebuilt" in changed.stdout
    expected[0][4] = 47.0
    assert _rows(root) == expected


def test_invalid_delivery_then_quarantine_without_another_archive_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    bad = root / "inbox" / "bad.json"
    payload = garmin_file_bytes([garmin_uds_record("invalid-day", totalSteps=313)])
    bad.write_bytes(payload)
    source_state = (bad.read_bytes(), bad.stat().st_mtime_ns)
    module = importlib.import_module("fitdocs.sync")
    original = module.archive_identified
    attempts: list[Path] = []

    def archive(*args: Any, **kwargs: Any) -> Any:
        attempts.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "archive_identified", archive)
    first = _invoke(root, "sync", "--no-prompt")
    assert first.exit_code == 1, first.output
    assert (_counts(first)["Wellness failed"], _counts(first)["Quarantined"]) == (1, 0)
    record = load_quarantine(root)
    assert [(e.sha256, e.name, e.reason) for e in record.entries] == [
        (
            hashlib.sha256(payload).hexdigest(),
            "bad.json",
            "invalid Garmin calendar date",
        )
    ]
    second = _invoke(root, "sync", "--no-prompt")
    assert second.exit_code == 0, second.output
    assert (_counts(second)["Wellness failed"], _counts(second)["Quarantined"]) == (
        0,
        1,
    )
    assert attempts == [bad]
    assert (bad.read_bytes(), bad.stat().st_mtime_ns) == source_state
    assert load_quarantine(root) == record


@pytest.mark.parametrize("explicit_source", [False, True])
def test_monitoring_fit_stays_unmodified_under_move(
    tmp_path: Path, explicit_source: bool
) -> None:
    root = _root(tmp_path, move=True)
    candidate = root / "inbox" / "monitoring.fit"
    identity = builder._file_id(4200000082)
    identity["type"] = "monitoring_b"
    candidate.write_bytes(builder.encode([identity]))
    before = (candidate.read_bytes(), candidate.stat().st_mtime_ns)
    result = _invoke(
        root,
        "sync",
        *([str(candidate.parent)] if explicit_source else []),
        "--no-prompt",
    )
    assert result.exit_code == 0, result.output
    counts = _counts(result)
    assert (
        counts["Written"],
        counts["Skipped"],
        counts["Failed"],
        counts["Warnings"],
    ) == (0, 1, 0, 1)
    assert "monitoring.fit" in result.stdout and "monitoring_b" in result.stdout
    assert (candidate.read_bytes(), candidate.stat().st_mtime_ns) == before
    assert list((root / "fit-archive").glob("*.fit")) == []
    assert list((root / "workouts").glob("*.md")) == [root / "workouts" / "AGENTS.md"]
    assert load_quarantine(root).entries == ()
