"""Native command workflows over synthetic FIT and archived wellness inputs."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner, Result

from fitdocs.cli import app
from fitdocs.contract import document_date, document_start_time
from fitdocs.docio import read_document
from fitdocs.index.fingerprint import document_fingerprint
from fitdocs.index.location import resolve_index_location
from fitdocs.index.store import open_index
from fitdocs.morning.docedit import read_morning, replace_morning
from fitdocs.wellness import Metric
from tests.fixtures.builder import small_sport_fit_bytes
from tests.morning.builders import series_value, stage_series, wellness_series
from tests.wellness.builders_garmin import (
    garmin_file_bytes,
    garmin_file_name,
    garmin_sleep_record,
)
from tests.wellness.builders_intervals import intervals_delivery_bytes, intervals_record

DAY = date(2021, 9, 8)
LATER = DAY + timedelta(days=90)
RUNNER = CliRunner()


@contextmanager
def _fake_system_date(fixed_timestamp: float, *, tz: str) -> Iterator[None]:
    """Locally copy the history E2E clock hook and restore process settings."""
    original_time = time.time
    original_tz = os.environ.get("TZ")
    original_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    time.time = lambda: fixed_timestamp
    os.environ["TZ"] = tz
    os.environ["SOURCE_DATE_EPOCH"] = str(int(fixed_timestamp))
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        yield
    finally:
        time.time = original_time
        for key, value in (("TZ", original_tz), ("SOURCE_DATE_EPOCH", original_epoch)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if hasattr(time, "tzset"):
            time.tzset()


@pytest.fixture(autouse=True)
def _environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(tmp_path / "index-cache"))
    with _fake_system_date(978307200.0, tz="UTC"):
        yield


def _root(tmp_path: Path) -> tuple[Path, Path]:
    root, source = tmp_path / "data", tmp_path / "source"
    root.mkdir()
    source.mkdir()
    (root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n[inbox]\nsettle_seconds = 0\n"
    )
    return root, source


def _fit(day_offset: int, serial: int) -> bytes:
    return small_sport_fit_bytes(
        serial, "hiking", timestamp_offset=12 * 3600 + day_offset * 86400
    )


def _invoke(root: Path, *args: str) -> Result:
    result = RUNNER.invoke(app, [*args, "--out", str(root)])
    assert result.exit_code == 0, result.output
    return result


def _pages(root: Path) -> dict[date, Path]:
    pages = {}
    for page in (root / "workouts").glob("*.md"):
        document = read_document(page)
        if document is not None and document.frontmatter:
            day = document_date(document.frontmatter)
            if day is not None:
                pages[day] = page
    return pages


def _block(page: Path) -> str:
    return read_morning(page.read_text()) or ""


def _source_scenario(tmp_path: Path) -> tuple[Path, Path, dict[date, Path]]:
    root, source = _root(tmp_path)
    for offset, serial in ((0, 7301), (1, 7302)):
        (source / f"day-{offset}.fit").write_bytes(_fit(offset, serial))
    stage_series(
        root,
        wellness_series(
            series_value(
                DAY + timedelta(days=offset),
                value,
                metric=Metric.RESTING_HR_BPM,
                source="intervals-icu",
                canonical=True,
            )
            for offset, value in ((0, 47), (1, 61))
        ),
    )
    _invoke(root, "sync", str(source), "--no-prompt")
    pages = _pages(root)
    assert set(pages) == {DAY, DAY + timedelta(days=1)}
    return root, source, pages


@pytest.mark.parametrize(("offset", "value"), [(0, 47), (1, 61)])
def test_explicit_source_fills_both_dates_in_the_same_run(
    tmp_path: Path, offset: int, value: int
) -> None:
    _root_path, _source, pages = _source_scenario(tmp_path)
    block = _block(pages[DAY + timedelta(days=offset)])
    assert f"| Resting HR | {value} bpm |" in block


@pytest.mark.parametrize("observable", ["bytes", "mtime", "report"])
def test_second_source_sync_is_unchanged(tmp_path: Path, observable: str) -> None:
    root, source, pages = _source_scenario(tmp_path)
    assert tuple(
        "## Morning Of\n" in _block(pages[day])
        for day in (DAY, DAY + timedelta(days=1))
    ) == (True, True)
    before_bytes = {day: page.read_bytes() for day, page in pages.items()}
    before_mtimes = {day: page.stat().st_mtime_ns for day, page in pages.items()}
    result = _invoke(root, "sync", str(source), "--no-prompt")
    actual: object
    expected: object
    if observable == "bytes":
        actual = {day: page.read_bytes() for day, page in pages.items()}
        expected = before_bytes
    elif observable == "mtime":
        actual = {day: page.stat().st_mtime_ns for day, page in pages.items()}
        expected = before_mtimes
    else:
        actual = [line for line in result.output.splitlines() if "Morning of:" in line]
        expected = []
    assert actual == expected


def test_copied_root_refills_identical_blocks_in_another_zone_and_date(
    tmp_path: Path,
) -> None:
    root, source, pages = _source_scenario(tmp_path)
    before = {day: _block(page) for day, page in pages.items()}
    assert tuple(
        "## Morning Of\n" in before[day] for day in (DAY, DAY + timedelta(days=1))
    ) == (True, True)
    starts = [
        document_start_time(read_document(pages[day]).frontmatter)  # type: ignore[union-attr]
        for day in (DAY, DAY + timedelta(days=1))
    ]
    assert [
        (
            start.astimezone(UTC).date(),
            start.astimezone(ZoneInfo("Pacific/Kiritimati")).date(),
        )
        for start in starts
        if start is not None
    ] == [
        (DAY, DAY + timedelta(days=1)),
        (DAY + timedelta(days=1), DAY + timedelta(days=2)),
    ]
    copied = tmp_path / "copied-data"
    shutil.copytree(root, copied)
    copied_pages = _pages(copied)
    for page in copied_pages.values():
        page.write_text(replace_morning(page.read_text(), ""))
    assert tuple(_block(copied_pages[day]) for day in sorted(copied_pages)) == ("", "")
    with _fake_system_date(2208988800.0, tz="Pacific/Kiritimati"):
        _invoke(copied, "sync", str(source), "--no-prompt")
    assert {day: _block(page) for day, page in copied_pages.items()} == before


def _delivery(root: Path, name: str, *, first_value: int) -> None:
    inbox = root / "inbox"
    inbox.mkdir(exist_ok=True)
    (inbox / name).write_bytes(
        intervals_delivery_bytes(
            [
                intervals_record(
                    DAY,
                    updated="2021-12-11T00:00:00Z"
                    if first_value == 53
                    else "2021-12-10T00:00:00Z",
                    restingHR=first_value,
                ),
                intervals_record(LATER, updated="2021-12-10T00:00:00Z", restingHR=63),
            ]
        )
    )


def _drain_scenario(tmp_path: Path) -> tuple[Path, dict[date, Path]]:
    root, _source = _root(tmp_path)
    _delivery(root, "first.json", first_value=47)
    (root / "inbox/first.fit").write_bytes(_fit(0, 7401))
    (root / "inbox/later.fit").write_bytes(_fit(90, 7402))
    _invoke(root, "sync", "--no-prompt")
    pages = _pages(root)
    assert set(pages) == {DAY, LATER}
    return root, pages


@pytest.mark.parametrize(("day", "value"), [(DAY, 47), (LATER, 63)])
def test_drain_fills_workouts_from_archived_deliveries_in_the_same_run(
    tmp_path: Path, day: date, value: int
) -> None:
    _root_path, pages = _drain_scenario(tmp_path)
    assert f"| Resting HR | {value} bpm |" in _block(pages[day])


@pytest.mark.parametrize(
    "observable", ["affected", "unaffected-bytes", "unaffected-mtime"]
)
def test_revised_delivery_changes_only_the_affected_populated_page(
    tmp_path: Path, observable: str
) -> None:
    root, pages = _drain_scenario(tmp_path)
    assert all("## Morning Of\n" in _block(pages[day]) for day in (DAY, LATER))
    before = {day: page.read_bytes() for day, page in pages.items()}
    before_mtime = pages[LATER].stat().st_mtime_ns
    _delivery(root, "revision.json", first_value=53)
    _invoke(root, "sync", "--no-prompt")
    if observable == "affected":
        assert pages[DAY].read_bytes() != before[DAY]
    elif observable == "unaffected-bytes":
        assert pages[LATER].read_bytes() == before[LATER]
    else:
        assert pages[LATER].stat().st_mtime_ns == before_mtime


@pytest.mark.parametrize(
    "expected",
    [
        "| Sleep | 7:00:00 |",
        "| Deep sleep | 1:00:00 |",
        "| Light sleep | 4:00:00 |",
        "| REM sleep | 2:00:00 |",
        "| Awake in sleep | 5:00 |",
        "## Morning Of\n\nData source: Garmin\n",
    ],
    ids=["total", "deep", "light", "rem", "awake", "attribution"],
)
def test_native_garmin_sleep_export_fills_stages_and_attribution(
    tmp_path: Path, expected: str
) -> None:
    root, _source = _root(tmp_path)
    inbox = root / "inbox"
    inbox.mkdir()
    (inbox / "sleep-workout.fit").write_bytes(_fit(0, 7501))
    (inbox / garmin_file_name("sleep", DAY, DAY)).write_bytes(
        garmin_file_bytes(
            [
                garmin_sleep_record(
                    DAY, deep_s=3600, light_s=14400, rem_s=7200, awake_s=300
                )
            ]
        )
    )
    _invoke(root, "sync", "--no-prompt")
    assert expected in _block(_pages(root)[DAY])


def test_same_run_index_postpass_fingerprints_the_refreshed_page(
    tmp_path: Path,
) -> None:
    root, source, pages = _source_scenario(tmp_path)
    _invoke(root, "index")
    page = pages[DAY]
    location = resolve_index_location(root, os.environ, Path.home())
    relative = page.relative_to(root).as_posix()
    with open_index(location.database, read_only=True) as connection:
        before = connection.execute(
            "SELECT document_fingerprint FROM index_pages WHERE path = ?", [relative]
        ).fetchall()
    stage_series(
        root,
        wellness_series(
            [
                series_value(
                    DAY,
                    73,
                    metric=Metric.RESTING_HR_BPM,
                    source="intervals-icu",
                    canonical=True,
                )
            ]
        ),
    )
    _invoke(root, "sync", str(source), "--no-prompt")
    fingerprint = document_fingerprint(relative, page.read_bytes())
    assert before != [(fingerprint,)]
    with open_index(location.database, read_only=True) as connection:
        after = connection.execute(
            "SELECT document_fingerprint FROM index_pages WHERE path = ?", [relative]
        ).fetchall()
    assert after == [(fingerprint,)]


@pytest.mark.parametrize("observable", ["status", "page"])
def test_damaged_markers_fail_sync_and_name_the_page(
    tmp_path: Path, observable: str
) -> None:
    root, source, pages = _source_scenario(tmp_path)
    page = pages[DAY]
    page.write_text(page.read_text().replace("<!-- fitdocs:end:morning -->", "", 1))
    result = RUNNER.invoke(
        app, ["sync", str(source), "--no-prompt", "--out", str(root)]
    )
    if observable == "status":
        assert result.exit_code == 1
    else:
        assert f"Morning of: could not update workouts/{page.name}:" in result.output
