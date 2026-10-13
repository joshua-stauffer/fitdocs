"""The engine's output does not depend on the process, timezone, locale or hash seed.

The parent starts child processes of this module (``python -m
tests.dashboards.test_determinism ROOT``); each stages the same pages in its own
data root, runs the engine with a fake source and a fixed date, and prints the
SHA-256 of every file under ``dashboards/`` plus probes of its UTC offset and
hash seed. LC_ALL is not probed: fitdocs never calls setlocale, so the
locale reaches the engine only through Python's UTF-8 mode (on in the C child,
off in the C.UTF-8 child). The parent compares the digests.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from fitdocs.dashboards.engine import Action, RunRequest, run_dashboards
from fitdocs.render.charts.kit import ChartData, Column, ValueKind
from tests.dashboards._helpers import (
    FakeSource,
    chart_data,
    date_column,
    directive_block,
    make_data_root,
    number_column,
    page_text,
    write_page,
)

RUN_DATE = date(2031, 4, 5)
SQL_RELATIVE = "select relative"
SQL_FROZEN = "select frozen"
CHILD_TIMEOUT_S = 120


def _relative_data() -> ChartData:
    # The latest value is 05:00 local: more than 5 hours east of UTC, the UTC date
    # is the day before.
    return chart_data(
        (Column("moment", ValueKind.DATETIME), number_column("value")),
        [
            (datetime(2021, 9, 8, 5, 0, 0), 3.0),
            (datetime(2021, 9, 2, 17, 30, 0), 7.0),
            (datetime(2021, 9, 5, 9, 15, 0), 5.0),
        ],
    )


def _frozen_data() -> ChartData:
    return chart_data(
        (date_column("day"), number_column("distance_km", unit="km")),
        [
            (date(2021, 9, 8), 12.5),
            (date(2021, 9, 1), 8.25),
            (date(2021, 9, 4), 10.0),
        ],
    )


def _directive(chart_id: str, kind: str, mode: str, sql: str) -> str:
    return directive_block(
        [
            ("id", chart_id),
            ("kind", kind),
            ("mode", mode),
            ("title", f"Title of {chart_id}"),
            ("window", "last 12 weeks"),
            ("sql", f"|\n  {sql}"),
            (
                "channels",
                "\n  x: "
                + ("moment" if mode == "relative" else "day")
                + "\n  y: "
                + ("value" if mode == "relative" else "distance_km"),
            ),
        ]
    )


def stage_and_run(root: Path) -> dict[str, str]:
    """Stage the pages under ``root``, run a refresh, return digest by path."""
    write_page(
        root,
        "alpha",
        page_text(
            "Prose first.",
            _directive("moments", "line", "relative", SQL_RELATIVE),
        ),
    )
    write_page(
        root,
        "beta",
        page_text(
            "Other prose.",
            _directive("distances", "scatter", "frozen", SQL_FROZEN),
        ),
    )
    source = FakeSource()
    source.queue(SQL_RELATIVE + "\n", _relative_data())
    source.queue(SQL_FROZEN + "\n", _frozen_data())
    report = run_dashboards(
        RunRequest(Action.REFRESH, root, (), RUN_DATE), source.opener()
    )
    assert not report.failed, report
    digests: dict[str, str] = {}
    base = root / "dashboards"
    for current, _dirs, names in os.walk(base):
        for name in names:
            path = Path(current) / name
            digests[path.relative_to(base).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


def probes() -> dict[str, object]:
    offset = datetime(2021, 9, 8, 5, 0, 0).astimezone().utcoffset()
    assert offset is not None
    return {
        "utcoffset_s": offset.total_seconds(),
        "hash": hash("determinism-probe"),
    }


def child_main(root: Path) -> None:
    print(json.dumps({"digests": stage_and_run(root), "probes": probes()}))


def _run_child(
    tmp_path: Path, name: str, tz: str, lc_all: str, seed: str
) -> dict[str, dict[str, object]]:
    root = make_data_root(tmp_path, name)
    completed = subprocess.run(
        [sys.executable, "-m", "tests.dashboards.test_determinism", str(root)],
        check=False,
        capture_output=True,
        text=True,
        timeout=CHILD_TIMEOUT_S,
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "TZ": tz,
            "LC_ALL": lc_all,
            "PYTHONHASHSEED": seed,
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr
    parsed: dict[str, dict[str, object]] = json.loads(completed.stdout)
    return parsed


def test_pages_images_and_snapshots_are_identical_across_environments(
    tmp_path: Path,
) -> None:
    runs = [
        _run_child(tmp_path, "utc", "UTC", "C", "0"),
        _run_child(tmp_path, "pacific", "America/Los_Angeles", "C.UTF-8", "1"),
        _run_child(tmp_path, "auckland", "Pacific/Auckland", "C", "1"),
    ]
    # The environments really differ, so equality below is not self-referential.
    assert len({run["probes"]["utcoffset_s"] for run in runs}) == 3
    assert len({run["probes"]["hash"] for run in runs}) == 2
    first = runs[0]["digests"]
    assert sorted(first) == [
        "alpha.md",
        "assets/alpha/moments.svg",
        "assets/beta/distances.snapshot-1.json",
        "assets/beta/distances.svg",
        "beta.md",
    ]
    for run in runs[1:]:
        assert run["digests"] == first


if __name__ == "__main__":
    child_main(Path(sys.argv[1]))
