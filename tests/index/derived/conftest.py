"""Synthetic derived-index corpus and public index-operation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Final

import pytest

from fitdocs.athlete import load_athlete_inputs
from fitdocs.index.build import run_index_command
from fitdocs.index.corpus import corpus_snapshot, scan_workout_pages
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.location import INDEX_DIR_ENV, resolve_index_location
from fitdocs.index.producer import CorpusSnapshot
from fitdocs.index.refresh import IndexReport, Outcome, refresh_after_command
from fitdocs.index.store import open_index, read_bookkeeping
from fitdocs.layout import WORKOUTS_DIR, source_ref
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import SyncReport, sync
from tests.fixtures import builder, merge

TODAY: Final[date] = date(2026, 2, 24)
_INDEX_BASE = "fitdocs-derived-index"
_HOME_NAME = "fitdocs-derived-no-home"


class _OfflineTiles:
    attribution = "Synthetic fixture tiles"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"synthetic-tile" for ref in refs}


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _frontmatter_page(
    *,
    day: str,
    sport: str,
    sha: str | None,
    load: int | None = None,
    methodology: str | None = None,
) -> str:
    lines = ["---", "type: workout", f'date: "{day}"', f"sport: {sport}"]
    if sha is not None:
        lines.extend(["sources:", f"  - {source_ref(sha)}"])
    if load is not None:
        lines.append(f"load_value: {load}")
    if methodology is not None:
        lines.append(f"load_methodology: {methodology}")
    lines.extend(
        [
            "---",
            "",
            "<!-- fitdocs:begin:load -->",
            "_Training load not computed._",
            "<!-- fitdocs:end:load -->",
            "",
        ]
    )
    return "\n".join(lines)


def build_fixture_root(
    root: Path,
    *,
    methodology: bool = True,
    composed: bool = False,
) -> Path:
    """Write one deterministic, synthetic fixture corpus under ``root``."""
    root.mkdir(parents=True, exist_ok=True)
    method_setting = 'methodology = "threshold"\n' if methodology else ""
    _write(
        root,
        "fitdocs.toml",
        "[history]\n"
        + method_setting
        + 'coverage_threshold = 0.7\n\n[plans]\npath = "plans"\n',
    )
    pages = (
        ("2026-02-02-run-a", "2026-02-02", "Run", "1" * 64, 11, "threshold"),
        ("2026-02-05-run-b", "2026-02-05", "Run", "2" * 64, 17, "banister_1991"),
        ("2026-02-03-ride-a", "2026-02-03", "Ride", "3" * 64, 23, "threshold"),
        ("2026-02-03-ride-b", "2026-02-03", "Ride", "4" * 64, 31, "threshold"),
        ("2026-02-04-run-a", "2026-02-04", "Run", "5" * 64, 43, "banister_1991"),
        ("2026-02-09-override-log", "2026-02-09", "Run", "6" * 64, 59, "threshold"),
        ("2026-02-12-unplanned", "2026-02-12", "Run", "7" * 64, 71, "threshold"),
        ("2026-02-13-no-load", "2026-02-13", "Run", "8" * 64, None, None),
        ("2026-02-14-no-load", "2026-02-14", "Run", "9" * 64, None, None),
    )
    for stem, day, sport, sha, load, method in pages:
        _write(
            root,
            f"{WORKOUTS_DIR}/{stem}.md",
            _frontmatter_page(
                day=day, sport=sport, sha=sha, load=load, methodology=method
            ),
        )
    # This loaded workout intentionally has no archive reference.
    _write(
        root,
        f"{WORKOUTS_DIR}/2026-02-14-left-out.md",
        _frontmatter_page(
            day="2026-02-15", sport="Run", sha=None, load=83, methodology="threshold"
        ),
    )
    source_record = (
        '{ kind = "derived", method = "synthetic-method", '
        'document = "workouts/derived.md", inputs = "synthetic-inputs", '
        'citation = "synthetic-citation" }'
    )
    athlete_text = """profile_version = 2
ftp_watts = 999
max_hr_bpm = 201

[benchmarks.ride]
ftp_watts = [
  { value = 260, measured_on = 2026-02-10, applies_from = 2026-01-01 },
  { value = 271, measured_on = 2026-02-05, applies_from = 2026-02-01 },
]

[benchmarks.run]
ftp_watts = [
  { value = 283, measured_on = 2026-02-07 },
]
lthr_bpm = [
  { value = 172, measured_on = 2026-02-06, source = SOURCE_RECORD },
]

[benchmarks.athlete]
max_hr_bpm = [
  { value = 203, measured_on = 2026-02-01 },
]
""".replace("SOURCE_RECORD", source_record)
    _write(root, "athlete.toml", athlete_text)
    plan = """title = "Derived fixture block"
starts = 2026-02-02
ends = 2026-02-28
goal = "Synthetic resolution cases"
mesocycle_days = 7

[[mesocycle]]
number = 1
target_load = 100
focus = "Base"

[[workout]]
id = "exact"
date = 2026-02-02
sport = "Run"
title = "Exact run"
summary = "Exact confidence"
prescription = "Synthetic."

[[workout]]
id = "absorbed"
date = 2026-02-03
sport = "Ride"
title = "Absorbed ride"
summary = "Absorbed confidence"
prescription = "Synthetic."

[[workout]]
id = "ambiguous-a"
date = 2026-02-04
sport = "Run"
title = "Ambiguous A"
summary = "Ambiguous confidence"
prescription = "Synthetic."

[[workout]]
id = "ambiguous-b"
date = 2026-02-04
sport = "Run"
title = "Ambiguous B"
summary = "Unmatched competitor"
prescription = "Synthetic."

[[workout]]
id = "override"
date = 2026-02-09
sport = "Run"
title = "Override"
summary = "Explicit stems"
prescription = "Synthetic."

[[workout]]
id = "skip"
date = 2026-02-10
sport = "Run"
title = "Skipped"
summary = "Skipped row"
prescription = "Synthetic."

[[workout]]
id = "not-logged"
date = 2026-02-11
sport = "Run"
title = "Past row"
summary = "Not logged"
prescription = "Synthetic."

[[workout]]
id = "no-sources-match"
date = 2026-02-15
sport = "Run"
title = "No source match"
summary = "No-sources page match"
prescription = "Synthetic."

[[workout]]
id = "upcoming"
date = 2026-02-24
sport = "Run"
title = "Future row"
summary = "Upcoming"
prescription = "Synthetic."

[[override]]
date = 2026-02-08
id = "override"
stems = ["2026-02-09-override-log", "missing-override-stem"]
reason = "Synthetic override"

[[override]]
date = 2026-02-08
id = "skip"
skipped = true
reason = "Synthetic skip"
"""
    _write(root, "plans/derived.toml", plan)
    _write(
        root, "plans/invalid.toml", 'title = "Invalid source"\nstarts = "not-a-date"\n'
    )
    if composed:
        source = root / "composed-source"
        ride_pair = merge.ride_pair_fit_bytes()
        sources = (
            ("run/power.fit", builder.run_native_power_sparse_hr_fit_bytes()),
            ("ride/garmin.fit", ride_pair[0]),
            ("ride/healthfit.fit", ride_pair[1]),
        )
        for relative, data in sources:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return root


def _index_args(root: Path, today: date) -> tuple[dict[str, str], Path]:
    base = root.parent / _INDEX_BASE / root.name
    home = root.parent / _HOME_NAME / root.name
    return {INDEX_DIR_ENV: str(base)}, home


def snapshot_of(root: Path, *, today: date) -> CorpusSnapshot:
    scan = scan_workout_pages(root)
    environ, home = _index_args(root, today)
    location = resolve_index_location(root, environ, home)
    held = None
    if location.database.is_file():
        with open_index(location.database, read_only=True) as conn:
            bookkeeping = read_bookkeeping(conn)
            if bookkeeping is not None:
                held = frozenset(bookkeeping.pages)
    return corpus_snapshot(
        root,
        scan,
        today=today,
        athlete_fingerprint=athlete_fingerprint(load_athlete_inputs(root)),
        held=held,
    )


def build_index(root: Path, *, today: date, rebuild: bool = False) -> IndexReport:
    environ, home = _index_args(root, today)
    return run_index_command(
        root,
        environ=environ,
        home=home,
        athlete=load_athlete_inputs(root),
        today=today,
        rebuild=rebuild,
        progress=None,
    )


def refresh(
    root: Path, *, today: date, handoff: HandoffCollector | None = None
) -> IndexReport:
    environ, home = _index_args(root, today)
    return refresh_after_command(
        root,
        environ=environ,
        home=home,
        handoff=handoff,
        today=today,
        progress=None,
    )


def read_table(root: Path, name: str) -> tuple[tuple[object, ...], ...]:
    environ, home = _index_args(root, TODAY)
    location = resolve_index_location(root, environ, home)
    with open_index(location.database, read_only=True) as conn:
        return tuple(conn.execute(f'SELECT * FROM "{name}" ORDER BY ALL').fetchall())


def sync_with_handoff(
    root: Path, source_dir: Path, *, today: date
) -> tuple[SyncReport, IndexReport, HandoffCollector]:
    collector = HandoffCollector()
    report = sync(
        source_dir,
        root,
        athlete=load_athlete_inputs(root),
        tz=timezone(timedelta(hours=-6)),
        tiles=_OfflineTiles(),
        on_rendered=collector.add,
    )
    assert report.failures == ()
    index_report = refresh(root, today=today, handoff=collector)
    assert index_report.outcome is Outcome.REFRESHED
    result = index_report.result
    assert result is not None
    written = set(report.written)
    assert written
    assert written.issubset(set(result.added) | set(result.updated))
    return report, index_report, collector


@pytest.fixture
def derived_root(tmp_path: Path) -> Path:
    return build_fixture_root(tmp_path / "derived-root")


@pytest.fixture
def composed_source(tmp_path: Path) -> Path:
    root = build_fixture_root(tmp_path / "composed-data", composed=True)
    return root / "composed-source"
