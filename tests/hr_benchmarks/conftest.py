from pathlib import Path

import pytest

from tests.hr_benchmarks.builders import make_data_root


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return make_data_root(tmp_path / "data")
