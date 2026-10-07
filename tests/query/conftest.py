"""Isolated HOME fixtures for analytics query tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.index.location import resolve_index_location
from tests.fixtures import builder
from tests.query._helpers import (
    FIXTURE_TODAY,
    DerivedInputs,
    write_fixture_inputs,
)
from tests.query._helpers import (
    copy_indexed_root as copy_indexed_root_helper,
)

_REAL_HOME = Path.home()


class HomeDirectory:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __fspath__(self) -> str:
        return str(self.path)

    def __truediv__(self, child: str) -> Path:
        return self.path / child

    def assert_untouched(self) -> None:
        assert tuple(self.path.iterdir()) == ()


@pytest.fixture
def home_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HomeDirectory:
    """Point HOME at an empty temporary directory and expose an emptiness check."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return HomeDirectory(home)


@pytest.fixture(scope="module")
def derived_inputs() -> DerivedInputs:
    """Append point for analytics-derived fixture inputs."""
    return DerivedInputs(files={}, athlete_toml="")


@pytest.fixture(scope="module")
def indexed_root(
    tmp_path_factory: pytest.TempPathFactory, derived_inputs: DerivedInputs
) -> Iterator[tuple[Path, Path]]:
    base = tmp_path_factory.mktemp("query-indexed")
    root = base / "data"
    root.mkdir()
    home = base / "home"
    home.mkdir()
    index_base = base / "index-cache"
    athlete = """profile_version = 2
ftp_watts = 250
resting_hr_bpm = 45
max_hr_bpm = 190
hr_zones = [100, 120, 140, 160]
power_zones = [100, 150, 200, 250]
pace_zones = [240, 300, 360, 420]

[[benchmarks.run.ftp_watts]]
value = 250
measured_on = 2021-09-01
[[benchmarks.run.lthr_bpm]]
value = 165
measured_on = 2021-09-01
[[benchmarks.run.threshold_pace_s_per_km]]
value = 300
measured_on = 2021-09-01
[[benchmarks.ride.ftp_watts]]
value = 250
measured_on = 2021-09-01
[[benchmarks.ride.lthr_bpm]]
value = 165
measured_on = 2021-09-01
[[benchmarks.athlete.max_hr_bpm]]
value = 190
measured_on = 2021-09-01
[[benchmarks.athlete.resting_hr_bpm]]
value = 45
measured_on = 2021-09-01
"""
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setenv("HOME", str(home))
        isolated.setenv("FITDOCS_INDEX_DIR", str(index_base))
        isolated.setenv("XDG_CACHE_HOME", str(base / "user-xdg"))
        isolated.delenv("XDG_CACHE_HOME", raising=False)
        assert "XDG_CACHE_HOME" not in os.environ
        import fitdocs.cli as cli_module

        isolated.setattr(cli_module, "_today", lambda: FIXTURE_TODAY)
        (root / "fitdocs.toml").write_text(
            "[tiles]\nenabled = false\n"
            '[load]\ndefault_calculator = "threshold"\n'
            "benchmark_staleness_days = 4000\n"
            "[load.sufficiency]\nmin_duration_s = 1\n",
            encoding="utf-8",
        )
        write_fixture_inputs(root, athlete, derived_inputs)
        source = base / "source"
        source.mkdir()
        (source / "run.fit").write_bytes(builder.run_fit_bytes())
        (source / "ride.fit").write_bytes(builder.ride_fit_bytes())
        synced = CliRunner().invoke(
            app, ["sync", str(source), "--out", str(root), "--no-prompt"]
        )
        assert synced.exit_code == 0, synced.output
        pages = tuple((root / "workouts").glob("*.md"))
        tagged = pages[0]
        tag = (
            "effort: race\n"
            "effort_distance_m: 42195\n"
            "effort_time_s: 12345\n"
            'effort_event: "Fixture Marathon"\n'
        )
        original = tagged.read_text(encoding="utf-8")
        assert "effort:" not in original
        tagged.write_text(original.replace("---\n", "---\n" + tag, 1), encoding="utf-8")
        indexed = CliRunner().invoke(app, ["index", "--out", str(root)])
        assert indexed.exit_code == 0, indexed.output
        location = resolve_index_location(root, os.environ, home)
        yield root, location.directory
        assert tuple(home.iterdir()) == ()


@pytest.fixture
def use_indexed_root(
    indexed_root: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    root, index_dir = indexed_root
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir.parent))
    import fitdocs.cli as cli_module

    monkeypatch.setattr(cli_module, "_today", lambda: FIXTURE_TODAY)
    return root, index_dir


@pytest.fixture
def copy_indexed_root(
    indexed_root: tuple[Path, Path], tmp_path: Path
) -> tuple[Path, Path]:
    root, index_dir = indexed_root
    return copy_indexed_root_helper(root, index_dir, tmp_path)
