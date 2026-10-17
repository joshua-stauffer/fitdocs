"""Synthetic inbox delivery, recovery output and process-clock comparisons.

The time.time/TZ hook follows tests/test_history_e2e.py. It reaches Python's
date.today() and time.time(); the recovery boundary tests cover other clocks.
"""

from __future__ import annotations

import os
import socket
import stat
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import pytest
from typer.testing import CliRunner, Result

from fitdocs.cli import app
from fitdocs.contract import parse_frontmatter
from fitdocs.layout import DECLARED_DIRS
from fitdocs.wellness import read_series
from tests.fixtures import builder
from tests.wellness.builders_intervals import intervals_delivery_bytes, intervals_record

runner = CliRunner()
D = date(2021, 9, 10)
PAGE = "recovery/recovery.md"
OUTPUTS = (PAGE,) + tuple(
    f"recovery/assets/recovery-{name}.svg"
    for name in ("load", "hrv-sdnn", "hrv-rmssd", "resting-hr", "sleep", "other")
)
FIELDS = {
    "restingHR": 51,
    "hrv": 62,
    "hrvSDNN": 73,
    "sleepSecs": 28004,
    "avgSleepingHR": 45,
    "respiration": 16,
    "spO2": 97,
    "steps": 8018,
    "vo2max": 49,
    "weight": 80,
    "fatigue": 1.1,
    "mood": 1.2,
    "motivation": 1.3,
    "soreness": 1.4,
    "stress": 1.5,
    "injury": 1.6,
    "hydration": 1.7,
}
EXPECTED = {
    "resting_hr_bpm": 51,
    "hrv_rmssd_ms": 62,
    "hrv_sdnn_ms": 73,
    "sleep_s": 28004,
    "sleep_hr_bpm": 45,
    "respiration_brpm": 16,
    "spo2_pct": 97,
    "steps": 8018,
    "vo2max_ml_per_kg_min": 49,
    "weight_kg": 80,
    "fatigue_rating": 1.1,
    "mood_rating": 1.2,
    "motivation_rating": 1.3,
    "soreness_rating": 1.4,
    "stress_rating": 1.5,
    "injury_rating": 1.6,
    "hydration_rating": 1.7,
}


@pytest.fixture(autouse=True)
def _offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HOME", "FITDOCS_INDEX_DIR", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))

    def no_socket(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("recovery e2e attempted a socket")

    monkeypatch.setattr(socket, "socket", no_socket)


def _invoke(root: Path, command: str, *args: str) -> Result:
    return runner.invoke(app, [command, *args, "--out", str(root)])


def _stage(root: Path) -> None:
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n[tiles]\nenabled = false\n"
        "[load.sufficiency]\nmin_duration_s = 1\n"
    )
    (root / "athlete.toml").write_text(
        "[[benchmarks.run.lthr_bpm]]\nvalue = 160\nmeasured_on = 2021-01-01\n"
        "[[benchmarks.ride.lthr_bpm]]\nvalue = 165\nmeasured_on = 2021-01-01\n"
        "[[benchmarks.run.ftp_watts]]\nvalue = 250\nmeasured_on = 2021-01-01\n"
        "[[benchmarks.ride.ftp_watts]]\nvalue = 260\nmeasured_on = 2021-01-01\n"
        "[[benchmarks.run.threshold_pace_s_per_km]]\n"
        "value = 300\nmeasured_on = 2021-01-01\n"
        "[[benchmarks.athlete.max_hr_bpm]]\nvalue = 190\nmeasured_on = 2021-01-01\n"
        "[[benchmarks.athlete.resting_hr_bpm]]\nvalue = 50\nmeasured_on = 2021-01-01\n"
    )
    (inbox / "synthetic.json").write_bytes(
        intervals_delivery_bytes(
            [
                intervals_record(
                    D - timedelta(days=offset),
                    **{field: value + offset for field, value in FIELDS.items()},
                )
                for offset in (2, 1, 0)
            ]
        )
    )
    (inbox / "run.fit").write_bytes(builder.run_fit_bytes())
    (inbox / "ride.fit").write_bytes(builder.ride_fit_bytes())
    with _fake_system_date(datetime(2018, 1, 1, tzinfo=UTC).timestamp(), "UTC"):
        drained = _invoke(root, "sync", "--no-prompt")
    assert drained.exit_code == 0, drained.output
    series = read_series(root)
    assert tuple(
        (
            v.day,
            v.metric.value,
            v.source,
            v.origin,
            v.value,
            type(v.value) is not bool,
            v.canonical,
        )
        for v in series.values
    ) == tuple(
        sorted(
            (
                D - timedelta(days=offset),
                metric,
                "intervals-icu",
                None,
                value + offset,
                True,
                True,
            )
            for offset in (2, 1, 0)
            for metric, value in EXPECTED.items()
        )
    )
    pages = [
        parse_frontmatter(p.read_text())
        for p in (root / "workouts").glob("*.md")
        if p.name != "AGENTS.md"
    ]
    assert len(pages) == 2 and all(
        p is not None
        and isinstance(load := p.get("load_value"), (int, float))
        and not isinstance(load, bool)
        and load > 0
        for p in pages
    ), (pages, drained.output)
    assert not (root / PAGE).exists()


def _outputs(root: Path) -> dict[str, bytes]:
    return {path: (root / path).read_bytes() for path in OUTPUTS}


def _protected_inputs(root: Path) -> dict[str, tuple[object, ...]]:
    declarations = {Path(directory) / "AGENTS.md" for directory in DECLARED_DIRS}
    ancestors = {parent for path in declarations for parent in path.parents}
    state = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] == "recovery" or relative in declarations:
            continue
        metadata = path.lstat()
        # Declaration writes may change their ancestor directories' timestamps.
        timestamps = (
            ()
            if relative in ancestors
            else (
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )
        )
        state[relative.as_posix()] = (
            path.read_bytes() if path.is_file() else None,
            metadata.st_mode,
            *timestamps,
        )
    return state


def _generate(root: Path) -> dict[str, bytes]:
    _stage(root)
    protected = _protected_inputs(root)
    result = _invoke(root, "recovery")
    assert result.exit_code == 0, result.output
    assert set(
        p.relative_to(root).as_posix()
        for p in (root / "recovery").rglob("*")
        if p.is_file() and p.name != "AGENTS.md"
    ) == set(OUTPUTS)
    assert _protected_inputs(root) == protected
    outputs = _outputs(root)
    page = outputs[PAGE].decode()
    frontmatter = parse_frontmatter(page)
    assert frontmatter is not None and (
        frontmatter["as_of"],
        frontmatter["window_start"],
        frontmatter["window_end"],
    ) == ("2021-09-10", "2021-06-13", "2021-09-10")
    sleep = page.split("## Sleep\n", 1)[1].split("\n## ", 1)[0]
    assert [line for line in sleep.splitlines() if line.startswith("| ")] == [
        "| Signal | 2021-09-10 | 7-day mean | 60-day mean |",
        "| --- | --- | --- | --- |",
        "| Sleep | 7:46:44 | 7:46:45 | — |",
        "| Sleeping HR | 45 bpm | 46 bpm | — |",
    ]
    assert not any(
        label
        in outputs["recovery/assets/recovery-sleep.svg"]
        + outputs["recovery/assets/recovery-other.svg"]
        for label in (
            b"Deep sleep",
            b"Light sleep",
            b"REM sleep",
            b"Awake",
            b"Body battery",
            b"Stress level",
        )
    )
    for path, data in outputs.items():
        assert str(root).encode() not in data
        if path.endswith(".svg"):
            svg = ET.fromstring(data)
            assert len(list(svg.iter())) > 20 and b"No data" not in data, path
    return outputs


def test_inbox_to_recovery_then_unchanged_and_check(tmp_path: Path) -> None:
    root = tmp_path / "data"
    first = _generate(root)
    before = {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }
    result = _invoke(root, "recovery")
    assert result.exit_code == 0, result.output
    assert [
        line for line in result.output.splitlines() if line.startswith("recovery/")
    ] == [f"{path}: unchanged" for path in (*OUTPUTS[1:], PAGE)]
    assert _outputs(root) == first
    assert {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    } == before
    checked = _invoke(root, "check")
    assert checked.exit_code == 0 and "No findings:" in checked.output, checked.output


@contextmanager
def _fake_system_date(timestamp: float, tz: str) -> Iterator[None]:
    original_time = time.time
    original_tz = os.environ.get("TZ")
    original_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    time.time = lambda: timestamp
    os.environ["TZ"] = tz
    os.environ["SOURCE_DATE_EPOCH"] = str(int(timestamp))
    time.tzset()
    try:
        yield
    finally:
        time.time = original_time
        for key, original in (
            ("TZ", original_tz),
            ("SOURCE_DATE_EPOCH", original_epoch),
        ):
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
        time.tzset()


def test_dates_timezones_and_independent_roots_produce_identical_bytes(
    tmp_path: Path,
) -> None:
    cases = ((2019, "UTC"), (2019, "Pacific/Kiritimati"), (2031, "UTC"))
    results = []
    dates = []
    for index, (year, tz) in enumerate(cases):
        timestamp = datetime(year, 6, 1, 23, 30, tzinfo=UTC).timestamp()
        with _fake_system_date(timestamp, tz):
            dates.append(date.today())
            results.append(_generate(tmp_path / f"root-{index}"))
    assert dates == [date(2019, 6, 1), date(2019, 6, 2), date(2031, 6, 1)]
    assert results[0] == results[1] == results[2]


@pytest.mark.parametrize(
    "change,field",
    [
        ("bytes", 0),
        ("file-touch", 2),
        ("file-chmod", 1),
        ("file-same-mode-chmod", 3),
        ("directory-touch", 2),
        ("directory-chmod", 1),
        ("directory-same-mode-chmod", 3),
    ],
)
def test_protected_input_snapshot_detects_real_changes(
    tmp_path: Path,
    change: str,
    field: int,
) -> None:
    directory = tmp_path / "inputs"
    directory.mkdir()
    path = directory / "input.txt"
    path.write_bytes(b"before")
    before = _protected_inputs(tmp_path)
    target = directory if change.startswith("directory") else path
    metadata = target.stat()
    if change == "bytes":
        path.write_bytes(b"after!")
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    elif change.endswith("touch"):
        os.utime(
            target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000)
        )
    elif change.endswith("same-mode-chmod"):
        target.chmod(stat.S_IMODE(metadata.st_mode))
    else:
        target.chmod(stat.S_IMODE(metadata.st_mode) ^ stat.S_IWGRP)
    after = _protected_inputs(tmp_path)
    key = target.relative_to(tmp_path).as_posix()
    assert after[key][field] != before[key][field]


def test_protected_snapshot_excludes_read_atime_and_declared_write_ancestors(
    tmp_path: Path,
) -> None:
    workouts = tmp_path / "workouts"
    workouts.mkdir()
    source = workouts / "input.md"
    source.write_bytes(b"synthetic input")
    metadata = source.stat()
    os.utime(source, ns=(metadata.st_mtime_ns - 2_000_000_000, metadata.st_mtime_ns))
    # utime changes ctime too; use a real read for the atime-only control instead.
    before = _protected_inputs(tmp_path)
    source.read_bytes()
    assert _protected_inputs(tmp_path) == before
    (workouts / "AGENTS.md").write_bytes(b"synthetic declaration")
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    (recovery / "recovery.md").write_bytes(b"synthetic recovery")
    assert _protected_inputs(tmp_path) == before
    (workouts / "user-AGENTS.md").write_bytes(b"user input")
    assert _protected_inputs(tmp_path) != before


def test_constant_hrv_delivery_renders_recovery(tmp_path: Path) -> None:
    root = tmp_path / "constant"
    _stage(root)
    (root / "inbox" / "constant.json").write_bytes(
        intervals_delivery_bytes(
            [
                intervals_record(
                    D - timedelta(days=offset),
                    updated="2021-09-11T00:00:00Z",
                    **FIELDS,
                )
                for offset in (2, 1, 0)
            ]
        )
    )
    drained = _invoke(root, "sync", "--no-prompt")
    assert drained.exit_code == 0, drained.output
    assert [
        (v.day, v.value)
        for v in read_series(root).values
        if v.metric.value == "hrv_sdnn_ms"
    ] == [(D - timedelta(days=offset), 73.0) for offset in (2, 1, 0)]
    result = _invoke(root, "recovery")
    assert result.exit_code == 0, (result.output, result.exception)
    outputs = _outputs(root)
    assert outputs[PAGE].startswith(b"---\n")
    for path in OUTPUTS[1:]:
        svg = ET.fromstring(outputs[path])
        assert len(list(svg.iter())) > 20, path
