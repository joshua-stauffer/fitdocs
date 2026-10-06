"""Isolated HOME fixtures for analytics query tests."""

from __future__ import annotations

from pathlib import Path

import pytest

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
