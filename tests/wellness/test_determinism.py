"""Series bytes across independent interpreter timezones and hash seeds."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.wellness.builders_garmin import garmin_file_bytes, garmin_sleep_record
from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record

_BUILD = """
import sys
from pathlib import Path
from fitdocs.wellness.intake import identify, archive_identified, Identified, Archived
from fitdocs.wellness.engine import rebuild_series, SeriesStatus
from fitdocs.wellness.settings import DEFAULT_WELLNESS_SETTINGS
root = Path(sys.argv[1])
for path in sorted((root / 'inbox').iterdir()):
    identified = identify(path)
    if not isinstance(identified, Identified):
        raise RuntimeError(identified)
    archived = archive_identified(root, path, identified, None)
    if not isinstance(archived, Archived):
        raise RuntimeError(archived)
report = rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=True)
if report.status != SeriesStatus.REBUILT:
    raise RuntimeError(report)
"""


def _build(root: Path, zone: str, seed: str) -> dict[str, bytes]:
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    before = garmin_sleep_record("2028-01-03", deep_s=111, light_s=222, rem_s=333)
    before["sleepEndTimestampGMT"] = "2028-01-03T17:59:00-08:00"
    boundary = garmin_sleep_record("2028-01-04", deep_s=444, light_s=555, rem_s=777)
    boundary["sleepEndTimestampGMT"] = "2028-01-03T18:00:00-08:00"
    (inbox / "sleep.json").write_bytes(garmin_file_bytes([boundary, before]))
    (inbox / "intervals.json").write_bytes(
        intervals_list_bytes(
            [
                intervals_record("2027-12-31", restingHR=67, hrv=48),
                intervals_record("2028-01-05", steps=8912),
            ]
        )
    )
    environment = {
        **os.environ,
        "TZ": zone,
        "PYTHONHASHSEED": seed,
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(root / "home"),
        "FITDOCS_INDEX_DIR": str(root / "index"),
        "XDG_CACHE_HOME": str(root / "cache"),
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", _BUILD, str(root)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        pytest.fail(f"child build failed: {result.stdout}\n{result.stderr}")
    return {
        path.relative_to(root / "wellness").as_posix(): path.read_bytes()
        for path in (root / "wellness").rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("axis", ["timezone", "hashseed"])
def test_series_tree_bytes_are_independent_of_process_environment(
    tmp_path: Path, axis: str
) -> None:
    first = _build(tmp_path / "first", "Pacific/Auckland", "11")
    second = _build(
        tmp_path / "second",
        "America/Los_Angeles" if axis == "timezone" else "Pacific/Auckland",
        "11" if axis == "timezone" else "4",
    )
    assert first == second
    assert set(first) == {"2027.csv", "2028.csv", "manifest.toml"}
    assert b"2027-12-31,resting_hr_bpm,intervals-icu,,67,true\n" in first["2027.csv"]
    assert b"2028-01-03,sleep_s,garmin-export,garmin,666,true\n" in first["2028.csv"]
    assert b"2028-01-04,sleep_s,garmin-export,garmin,1776,true\n" in first["2028.csv"]
    assert b'format = "garmin-sleep"' in first["manifest.toml"]
    assert b'format = "intervals-icu"' in first["manifest.toml"]
