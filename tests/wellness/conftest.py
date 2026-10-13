"""Wellness fixtures rooted in pytest's temporary directories."""

from pathlib import Path

import pytest

from tests.wellness._helpers import make_data_root


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return make_data_root(tmp_path)
