"""The live index fixture shared by the dashboards tests."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.index.location import resolve_index_location
from tests.fixtures import builder
from tests.query._helpers import (
    FIXTURE_TODAY,
    DerivedInputs,
    copy_indexed_root,
    write_fixture_inputs,
)


@dataclass(frozen=True)
class IndexedDashboardRoot:
    """A data root with a built index, and the environment that finds it."""

    root: Path
    index_dir: Path
    home: Path
    environ: Mapping[str, str]
    today: date


def copy_dashboard_root(
    fixture: IndexedDashboardRoot, tmp_path: Path
) -> IndexedDashboardRoot:
    """A writable copy of the shared root with its own index and environment."""
    root, index_dir = copy_indexed_root(fixture.root, fixture.index_dir, tmp_path)
    home = tmp_path / "home"
    environ = {"HOME": str(home), "FITDOCS_INDEX_DIR": str(tmp_path / "index-cache")}
    return IndexedDashboardRoot(root, index_dir, home, environ, fixture.today)


_ATHLETE = """profile_version = 2
ftp_watts = 250
resting_hr_bpm = 45
max_hr_bpm = 190
hr_zones = [100, 120, 140, 160]
power_zones = [100, 150, 200, 250]
pace_zones = [240, 300, 360, 420]
"""


@pytest.fixture(scope="module")
def indexed_dashboard_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[IndexedDashboardRoot]:
    base = tmp_path_factory.mktemp("dashboards-indexed")
    root = base / "data"
    root.mkdir()
    home = base / "home"
    home.mkdir()
    index_base = base / "index-cache"
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setenv("HOME", str(home))
        isolated.setenv("FITDOCS_INDEX_DIR", str(index_base))
        isolated.delenv("XDG_CACHE_HOME", raising=False)
        import fitdocs.cli as cli_module

        isolated.setattr(cli_module, "_today", lambda: FIXTURE_TODAY)
        (root / "fitdocs.toml").write_text(
            "[tiles]\nenabled = false\n"
            '[load]\ndefault_calculator = "threshold"\n'
            "benchmark_staleness_days = 4000\n"
            "[load.sufficiency]\nmin_duration_s = 1\n",
            encoding="utf-8",
        )
        write_fixture_inputs(root, _ATHLETE, DerivedInputs(files={}, athlete_toml=""))
        source = base / "source"
        source.mkdir()
        (source / "run.fit").write_bytes(builder.run_fit_bytes())
        (source / "ride.fit").write_bytes(builder.ride_fit_bytes())
        synced = CliRunner().invoke(
            app, ["sync", str(source), "--out", str(root), "--no-prompt"]
        )
        assert synced.exit_code == 0, synced.output
        indexed = CliRunner().invoke(app, ["index", "--out", str(root)])
        assert indexed.exit_code == 0, indexed.output
        location = resolve_index_location(root, os.environ, home)
        environ = {
            "HOME": str(home),
            "FITDOCS_INDEX_DIR": str(index_base),
        }
        yield IndexedDashboardRoot(
            root=root,
            index_dir=location.directory,
            home=home,
            environ=environ,
            today=FIXTURE_TODAY,
        )
        assert not (home / ".cache" / "fitdocs").exists()
        assert not (home / ".fitdocs").exists()
