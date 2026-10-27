"""The WebP-encoder preflight of the four page-rendering CLI paths (compact-chart-assets
task 5.3, Req 4.4).

With the installed Pillow unable to encode WebP, ``sync SOURCE``, the inbox drain
(``sync`` without SOURCE), ``regen`` and ``pull --sync`` each exit ``2`` with a
message naming the missing capability and the remedy, and leave the data root
exactly as it was: every file's path, bytes and ``st_mtime_ns``, and every
directory, compared before and after.

The encoder is stubbed by monkeypatching ``fitdocs.basemap.encoder_available``
(``require_encoder`` looks it up at call time). Each scenario also runs once with
the encoder present on an identically seeded data root, and asserts that this run
writes a named marker path: that is the precondition that the scenario would write
something early, so a preflight placed after the first write cannot pass.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from fitdocs.cli import app
from fitdocs.wellness.intake import Identified, archive_identified, identify
from tests.fixtures import builder
from tests.support import tiles as tile_factory
from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record

runner = CliRunner()

Snapshot = dict[str, tuple[str, bytes | None, int | None]]


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fitdocs.tiles._default_fetch", tile_factory.fetch_stub())


def _no_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fitdocs.basemap.encoder_available", lambda: False)


def _snapshot(root: Path) -> Snapshot:
    """Every path under *root*: directories by kind, files by bytes and mtime_ns."""
    snap: Snapshot = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            snap[rel] = ("dir", None, None)
        else:
            snap[rel] = ("file", path.read_bytes(), path.stat().st_mtime_ns)
    return snap


def _seed_nothing(data_root: Path, tmp_path: Path) -> list[str]:
    return []


def _seed_source(data_root: Path, tmp_path: Path) -> list[str]:
    source = tmp_path / "src"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    return [str(source)]


def _seed_inbox_file(data_root: Path, tmp_path: Path) -> list[str]:
    inbox = data_root / "inbox"
    inbox.mkdir()
    (inbox / "run.fit").write_bytes(builder.run_fit_bytes())
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n", encoding="utf-8"
    )
    return []


def _seed_wellness_archive(data_root: Path, tmp_path: Path) -> list[str]:
    """An archived wellness entry and no series: ``rebuild_series`` has a series to
    write."""
    path = tmp_path / "wellness.json"
    path.write_bytes(
        intervals_list_bytes([intervals_record(date(2029, 6, 14), restingHR=47)])
    )
    identified = identify(path)
    assert isinstance(identified, Identified)
    archive_identified(data_root, path, identified, None)
    return []


@dataclass(frozen=True)
class Scenario:
    command: tuple[str, ...]
    seed: Callable[[Path, Path], list[str]]
    # A path the command writes, absent from the seeded data root, when the encoder
    # is present.
    marker: str


SCENARIOS: dict[str, Scenario] = {
    "sync-source": Scenario(("sync",), _seed_source, "workouts"),
    "drain-creates-inbox": Scenario(("sync",), _seed_nothing, "inbox"),
    "drain-with-file": Scenario(("sync",), _seed_inbox_file, "workouts"),
    "regen": Scenario(("regen",), _seed_wellness_archive, "wellness/manifest.toml"),
    "pull-sync": Scenario(("pull", "--sync"), _seed_nothing, "inbox"),
}


def _invoke(scenario: Scenario, tmp_path: Path) -> tuple[Path, Snapshot, Result]:
    data_root = tmp_path / "data"
    data_root.mkdir()
    extra = scenario.seed(data_root, tmp_path)
    before = _snapshot(data_root)
    result = runner.invoke(app, [*scenario.command, *extra, "--out", str(data_root)])
    return data_root, before, result


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_with_the_encoder_present_the_scenario_writes_its_marker(
    name: str, tmp_path: Path
) -> None:
    """The precondition for the tests below: this command, on this seeded data
    root, does write something before it could be stopped late."""
    scenario = SCENARIOS[name]

    data_root, before, result = _invoke(scenario, tmp_path)

    assert result.exit_code == 0, result.output
    assert scenario.marker not in before
    assert scenario.marker in _snapshot(data_root)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_without_the_encoder_exit_2_with_remedy_and_nothing_written(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = SCENARIOS[name]
    _no_encoder(monkeypatch)

    data_root, before, result = _invoke(scenario, tmp_path)

    assert result.exit_code == 2, result.output
    output = " ".join(result.output.split())
    assert "no WebP encoder" in output
    assert "uv tool install --reinstall fitdocs" in output
    assert "libwebp" in output
    assert _snapshot(data_root) == before


def test_the_snapshot_sees_changed_bytes_a_changed_mtime_and_a_new_directory(
    tmp_path: Path,
) -> None:
    """The comparison is sensitive to different bytes under an unchanged mtime, to the
    same bytes under a changed mtime, and to an empty directory appearing."""
    (tmp_path / "f").write_bytes(b"x")
    os.utime(tmp_path / "f", ns=(5, 5))
    before = _snapshot(tmp_path)
    (tmp_path / "f").write_bytes(b"y")
    os.utime(tmp_path / "f", ns=(5, 5))
    assert _snapshot(tmp_path) != before
    (tmp_path / "f").write_bytes(b"x")
    os.utime(tmp_path / "f", ns=(6, 6))
    assert _snapshot(tmp_path) != before
    before = _snapshot(tmp_path)
    (tmp_path / "d").mkdir()
    assert _snapshot(tmp_path) != before


@pytest.mark.parametrize(
    "argv",
    [("pull",), ("load",)],
    ids=["pull-without-sync", "load"],
)
def test_commands_that_render_no_pages_do_not_need_the_encoder(
    argv: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_encoder(monkeypatch)
    data_root = tmp_path / "data"
    data_root.mkdir()

    result = runner.invoke(app, [*argv, "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert "WebP" not in result.output
