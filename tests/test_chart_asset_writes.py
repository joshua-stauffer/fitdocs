"""Workout chart assets are written only when their bytes change.

compact-chart-assets task 5.2 (Req 6.1, 6.2, 6.3, 6.4): the sync asset writer
sends every asset through ``fitdocs.docio.write_bytes_if_changed``. Archives
here are synthetic (a handful of generated records, a drawn-tile stub).
"""

from __future__ import annotations

import math
import os
from datetime import timedelta, timezone
from pathlib import Path

import pytest

import fitdocs.sync as sync_module
from fitdocs.athlete import ATHLETE_FILE, load_athlete_inputs
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.render import Asset
from fitdocs.sync import regen, sync
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileStore
from tests.fixtures import builder
from tests.support import tiles as tile_factory

_TZ = timezone(timedelta(hours=-6))
_DAY = 86_400
_OLD_NS = 1_500_000_000_000_000_000  # 2017, far from any real clock


def _run_fit(
    *,
    day: int,
    hr_step: int,
    time_created: int = builder.FIT_TIMESTAMP_BASE,
) -> bytes:
    """A 10-minute GPS run with power and dynamics, starting ``day`` days in.

    ``hr_step`` reshapes the heart-rate channel (the chart normalizes, so a
    constant shift would not show), so the hero chart differs between two
    values while the route (and so the map) does not.
    """
    start = builder.FIT_TIMESTAMP_BASE + day * _DAY
    records: list[tuple[dict[str, object], dict[int, object]]] = []
    distance = 0.0
    for i in range(600):
        speed = 3.0 + 0.5 * math.sin(i / 40)
        distance += speed
        angle = i / 90
        records.append(
            (
                {
                    "timestamp": start + i,
                    "distance": round(distance, 2),
                    "enhanced_speed": round(speed, 3),
                    "heart_rate": 140 + (i * hr_step) % 23,
                    "power": 200 + (i * 5) % 41,
                    "vertical_oscillation": 80 + (i * 3) % 17,
                    "stance_time": 240 + (i * 11) % 29,
                    "position_lat": builder.to_semicircles(0.004 * math.sin(angle)),
                    "position_long": builder.to_semicircles(0.006 * math.cos(angle)),
                },
                {},
            )
        )
    return builder.developer_field_run_fit_bytes(
        descriptions=(),
        records=records,
        serial=1400 + day,
        time_created=time_created,
        session_start=start,
        session_distance_m=round(distance, 2),
    )


def _tiles(data_root: Path) -> TileStore:
    return TileStore(
        data_root, DEFAULT_TILE_SETTINGS, fetch=tile_factory.fetch_stub((16, 16))
    )


def _write_athlete(data_root: Path) -> None:
    """HR zones and thresholds, which unlock the zone-strip asset."""
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / ATHLETE_FILE).write_text(
        "resting_hr_bpm = 45\nmax_hr_bpm = 190\nhr_zones = [120, 140, 155, 170]\n",
        encoding="utf-8",
    )


def _sync(data_root: Path, source: Path) -> None:
    report = sync(
        source,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
    )
    assert report.failures == ()


def _regen(data_root: Path) -> None:
    report = regen(
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
    )
    assert report.failures == ()


def _asset_dir(data_root: Path) -> Path:
    return data_root / WORKOUTS_DIR / "assets"


def _stats(data_root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        p.name: (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(_asset_dir(data_root).iterdir())
    }


def _age_assets(data_root: Path) -> None:
    for path in _asset_dir(data_root).iterdir():
        os.utime(path, ns=(_OLD_NS, _OLD_NS))


def _stage(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    _write_athlete(data_root)
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.fit").write_bytes(_run_fit(day=0, hr_step=7))
    (source / "b.fit").write_bytes(_run_fit(day=1, hr_step=7))
    _sync(data_root, source)
    return data_root, source


def _page_assets(stats: dict[str, object], stem: str) -> set[str]:
    return {name for name in stats if name.startswith(stem)}


def _stems(data_root: Path) -> list[str]:
    return sorted(p.stem for p in (data_root / WORKOUTS_DIR).glob("20*.md"))


def test_a_second_regen_leaves_every_asset_mtime_unchanged(tmp_path: Path) -> None:
    """Req 6.1, 6.3: bytes equal to the file on disk mean no write, for the
    hero, the dynamics chart and the map alike."""
    data_root, _ = _stage(tmp_path)
    _age_assets(data_root)
    before = _stats(data_root)
    kinds = {name.rsplit("-", 1)[1] for name in before}
    assert kinds == {"hero.svg", "dynamics.svg", "map.svg", "zones.svg"}
    assert len(before) == 8
    assert {mtime for mtime, _ in before.values()} == {_OLD_NS}

    _regen(data_root)

    after = _stats(data_root)
    assert after == before


def test_an_unconditional_rewrite_would_move_the_mtime(tmp_path: Path) -> None:
    """The precondition of the test above: rewriting an aged asset does move
    its mtime_ns, so an unchanged mtime_ns is evidence of no write."""
    data_root, _ = _stage(tmp_path)
    _age_assets(data_root)
    victim = next(iter(_asset_dir(data_root).iterdir()))
    victim.write_bytes(victim.read_bytes())
    assert victim.stat().st_mtime_ns != _OLD_NS


def test_only_the_changed_pages_changed_assets_move(tmp_path: Path) -> None:
    """Req 6.1, 6.2: a corrected re-export of one activity (reshaped heart rate,
    same route) rewrites that page's changed charts and nothing else."""
    data_root, source = _stage(tmp_path)
    stem_a, stem_b = _stems(data_root)
    _age_assets(data_root)
    before = _stats(data_root)

    newer = tmp_path / "newer"
    newer.mkdir()
    later = builder.FIT_TIMESTAMP_BASE + 3_600
    (newer / "b2.fit").write_bytes(_run_fit(day=1, hr_step=5, time_created=later))
    _sync(data_root, newer)
    after = _stats(data_root)

    assert _stems(data_root) == [stem_a, stem_b]  # precondition: one page each
    assert after.keys() == before.keys()
    moved = {n for n in after if after[n][0] != _OLD_NS}
    changed = {n for n in after if after[n][1] != before[n][1]}
    assert changed  # precondition: the new export changed some bytes
    assert moved == changed
    assert moved <= _page_assets(after, stem_b)
    assert f"{stem_b}-map.svg" not in moved  # same route, same bytes, same mtime
    # Page A's clause pins sync's per-page scope (only B was re-synced), not the
    # writer.
    assert not moved & _page_assets(after, stem_a)


def _write_via_sync(data_root: Path, assets: tuple[Asset, ...]) -> None:
    sync_module._write_assets(data_root, assets)


def test_same_size_different_bytes_are_written(tmp_path: Path) -> None:
    """Req 6.2: a changed asset of the same length is still replaced."""
    path = _asset_dir(tmp_path) / "x-hero.svg"
    _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>aaaa</svg>"),))
    os.utime(path, ns=(_OLD_NS, _OLD_NS))

    _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>bbbb</svg>"),))
    assert path.read_text(encoding="utf-8") == "<svg>bbbb</svg>"
    assert path.stat().st_mtime_ns != _OLD_NS


def test_identical_bytes_are_not_rewritten_and_new_files_are_created(
    tmp_path: Path,
) -> None:
    """Req 6.1, 6.2: equal bytes keep their mtime; a missing file (in a
    missing directory) is created."""
    path = _asset_dir(tmp_path) / "x-hero.svg"
    assert not path.parent.exists()  # precondition
    _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>é</svg>"),))
    assert path.read_bytes() == "<svg>é</svg>".encode()
    os.utime(path, ns=(_OLD_NS, _OLD_NS))

    _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>é</svg>"),))
    assert path.stat().st_mtime_ns == _OLD_NS


def test_a_write_that_dies_midway_leaves_the_previous_complete_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.2: the swap onto the path is what fails, and the path still holds
    the previous bytes, with no temporary file left beside it."""
    path = _asset_dir(tmp_path) / "x-hero.svg"
    _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>old</svg>"),))
    calls: list[tuple[object, object]] = []

    def failing_replace(src: object, dst: object) -> None:
        calls.append((src, dst))
        raise OSError("injected failure at the swap")

    monkeypatch.setattr("fitdocs.docio.os.replace", failing_replace)
    with pytest.raises(OSError, match="injected failure at the swap"):
        _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>new!</svg>"),))

    assert len(calls) == 1  # precondition: the swap was reached
    assert path.read_text(encoding="utf-8") == "<svg>old</svg>"
    assert sorted(p.name for p in path.parent.iterdir()) == ["x-hero.svg"]


def test_the_output_steps_run_in_the_crash_healing_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.4: assets, stale-asset removal, move, document, archive -- the
    order the writer had before the change-aware helper."""
    steps = (
        "_write_assets",
        "_remove_stale_assets",
        "_move_document",
        "_write_document",
        "_write_archive",
    )
    seen: list[str] = []

    def recording(step: str) -> object:
        real = getattr(sync_module, step)

        def wrapper(*args: object, **kwargs: object) -> object:
            seen.append(step)
            return real(*args, **kwargs)

        return wrapper

    for step in steps:
        monkeypatch.setattr(sync_module, step, recording(step))
    _stage(tmp_path)

    # Two pages, none moved: each page task runs the steps it needs, in order.
    assert set(seen) == set(steps) - {"_move_document"}
    per_page = len(seen) // 2
    assert seen[:per_page] == [
        "_write_assets",
        "_remove_stale_assets",
        "_write_document",
        "_write_archive",
    ]
    assert seen[per_page:] == seen[:per_page]


def test_a_first_write_that_dies_midway_leaves_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.2, no file yet: the path never holds partial content, and no
    temporary file is left."""
    path = _asset_dir(tmp_path) / "x-hero.svg"
    path.parent.mkdir(parents=True)
    calls: list[object] = []

    def failing_replace(src: object, dst: object) -> None:
        calls.append(src)
        raise OSError("injected failure at the swap")

    monkeypatch.setattr("fitdocs.docio.os.replace", failing_replace)
    with pytest.raises(OSError, match="injected failure at the swap"):
        _write_via_sync(tmp_path, (Asset("assets/x-hero.svg", "<svg>new</svg>"),))

    assert len(calls) == 1  # precondition: the swap was reached
    assert not path.exists()
    assert list(path.parent.iterdir()) == []
