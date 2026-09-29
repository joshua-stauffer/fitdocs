"""Shared fixtures and helpers for the site-build tests.

Tasks 1.1 and 1.3 own this module; later tasks keep their helpers in their own
test modules.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

REQUIRE_ENV = "FITDOCS_REQUIRE_SITE_TOOLING"
SKIP_REASON = "site tooling not installed: uv sync --group docs"


@pytest.fixture
def requires_zensical() -> None:
    """Skip when the docs group is not installed, or fail if it is required.

    The check looks for a ``zensical`` executable next to the running
    interpreter. With ``FITDOCS_REQUIRE_SITE_TOOLING=1`` a missing executable
    fails the test instead of skipping it.
    """
    if (Path(sys.executable).parent / "zensical").exists():
        return
    if os.environ.get(REQUIRE_ENV) == "1":
        pytest.fail(SKIP_REASON)
    pytest.skip(SKIP_REASON)


def copy_fixture_tree(source: Path, tmp_path: Path, name: str = "site") -> Path:
    """Copy the fixture tree ``source`` to ``tmp_path/name``, links preserved."""
    destination = tmp_path / name
    shutil.copytree(source, destination, symlinks=True)
    return destination
