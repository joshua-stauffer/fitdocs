"""The system zone the CLI dates pages by (workout-docs Amendment 6, Req 2.10).

A page whose file records no local time is dated in the system's zone at the
offset that zone had on the activity's own date, never at the offset in force
when the command runs. ``cli._system_zone`` names the zone from ``TZ`` (an IANA
key, optionally ``:``-prefixed, or a zone file's path) and otherwise from the
``/etc/localtime`` zone file; a platform that names neither keeps today's fixed
offset. The end-to-end cases run ``fitdocs sync`` under a pinned ``TZ`` with a
January and a July file in one run, plus a file that records its own offset.
"""

from __future__ import annotations

import shutil
import time
import zoneinfo
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from fitdocs.cli import _system_zone, app
from fitdocs.model import FIT_EPOCH
from tests.fixtures import builder
from tests.fixtures.builder import FIT_TIMESTAMP_BASE

runner = CliRunner()

_JANUARY = datetime(2024, 1, 10, 12, tzinfo=UTC)
_JULY = datetime(2024, 7, 10, 12, tzinfo=UTC)
_MISSING = Path("/nonexistent/localtime")


def _offsets(zone: tzinfo) -> tuple[timedelta | None, timedelta | None]:
    return (_JANUARY.astimezone(zone).utcoffset(), _JULY.astimezone(zone).utcoffset())


def _zone_file(key: str) -> Path:
    for root in zoneinfo.TZPATH:
        candidate = Path(root) / key
        if candidate.is_file():
            return candidate
    pytest.skip(f"no system zone file for {key}")


@pytest.mark.parametrize("tz", ["Europe/Berlin", ":Europe/Berlin"])
def test_tz_key_names_a_zone_with_both_offsets(tz: str) -> None:
    assert _offsets(_system_zone(tz, _MISSING)) == (
        timedelta(hours=1),
        timedelta(hours=2),
    )


def test_tz_path_reads_that_zone_file(tmp_path: Path) -> None:
    copied = tmp_path / "zone"
    shutil.copyfile(_zone_file("America/New_York"), copied)
    assert _offsets(_system_zone(f":{copied}", _MISSING)) == (
        timedelta(hours=-5),
        timedelta(hours=-4),
    )


def test_without_tz_the_localtime_file_names_the_zone(tmp_path: Path) -> None:
    localtime = tmp_path / "localtime"
    shutil.copyfile(_zone_file("America/Denver"), localtime)
    assert _offsets(_system_zone(None, localtime)) == (
        timedelta(hours=-7),
        timedelta(hours=-6),
    )


def test_tz_wins_over_the_localtime_file(tmp_path: Path) -> None:
    localtime = tmp_path / "localtime"
    shutil.copyfile(_zone_file("America/Denver"), localtime)
    assert _offsets(_system_zone("Europe/Berlin", localtime)) == (
        timedelta(hours=1),
        timedelta(hours=2),
    )


@pytest.mark.parametrize("tz", [None, "Not/AZone", "CET-1CEST,M3.5.0,M10.5.0/3"])
def test_an_unnamed_zone_keeps_the_current_offset(tz: str | None) -> None:
    zone = _system_zone(tz, _MISSING)
    now = datetime.now().astimezone()
    assert zone.utcoffset(now) == now.utcoffset()


# --- end to end: one sync run, three files ------------------------------------


@pytest.fixture
def berlin() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", "Europe/Berlin")
        if hasattr(time, "tzset"):
            time.tzset()
        try:
            yield
        finally:
            patch.delenv("TZ", raising=False)
    if hasattr(time, "tzset"):
        time.tzset()


def _fit_seconds(instant: datetime) -> int:
    return int((instant - FIT_EPOCH).total_seconds()) - FIT_TIMESTAMP_BASE


def _start_times(data_root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for page in sorted((data_root / "workouts").glob("*.md")):
        text = page.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue  # the directory's AGENTS.md
        front = yaml.safe_load(text.split("---\n", 2)[1])
        found[page.stem] = front["start_time"]
    return found


def test_sync_dates_each_page_at_its_own_offset(tmp_path: Path, berlin: None) -> None:
    source = tmp_path / "source"
    source.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()
    winter = datetime(2024, 1, 10, 17, 5, tzinfo=UTC)
    summer = datetime(2024, 7, 10, 16, 5, tzinfo=UTC)
    abroad = datetime(2024, 3, 2, 3, 30, tzinfo=UTC)
    (source / "winter.fit").write_bytes(
        builder.small_sport_fit_bytes(
            4200000301, "running", timestamp_offset=_fit_seconds(winter)
        )
    )
    (source / "summer.fit").write_bytes(
        builder.small_sport_fit_bytes(
            4200000302, "running", timestamp_offset=_fit_seconds(summer)
        )
    )
    (source / "abroad.fit").write_bytes(
        builder.small_sport_fit_bytes(
            4200000303,
            "running",
            timestamp_offset=_fit_seconds(abroad),
            local_offset_s=-5 * 3600,
        )
    )

    result = runner.invoke(
        app, ["sync", str(source), "--out", str(data_root), "--no-prompt"]
    )

    assert result.exit_code == 0, result.output
    assert _start_times(data_root) == {
        "2024-01-10-run-1805": "2024-01-10T18:05:00+01:00",
        "2024-07-10-run-1805": "2024-07-10T18:05:00+02:00",
        "2024-03-01-run-2230": "2024-03-01T22:30:00-05:00",
    }
