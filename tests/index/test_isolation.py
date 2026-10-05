"""The shared test fixture keeps index files out of the user's home."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_index_directory_is_absolute_and_outside_home() -> None:
    index_dir = Path(os.environ["FITDOCS_INDEX_DIR"])

    assert index_dir.is_absolute()
    assert not index_dir.is_relative_to(Path.home())


def test_index_directory_does_not_reuse_previous_test(tmp_path: Path) -> None:
    marker = Path(os.environ["FITDOCS_INDEX_DIR"]) / "from-previous-test"
    marker.write_text("test isolation", encoding="utf-8")


def test_index_directory_has_no_marker_from_previous_test() -> None:
    marker = Path(os.environ["FITDOCS_INDEX_DIR"]) / "from-previous-test"

    assert not marker.exists()


@pytest.mark.parametrize("original_value", ["/private/tmp/index-env-sentinel", None])
def test_index_directory_environment_is_restored_after_pytest(
    tmp_path: Path, original_value: str | None
) -> None:
    plugin_dir = tmp_path / "pytest_plugins"
    plugin_dir.mkdir()
    result_path = tmp_path / "environment-after-session.json"
    plugin = plugin_dir / "index_env_probe.py"
    plugin.write_text(
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    Path(os.environ['INDEX_ENV_RESULT']).write_text(\n"
        "        json.dumps(os.environ.get('FITDOCS_INDEX_DIR'))\n"
        "    )\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["INDEX_ENV_RESULT"] = str(result_path)
    if original_value is None:
        env.pop("FITDOCS_INDEX_DIR", None)
    else:
        env["FITDOCS_INDEX_DIR"] = original_value
    python_path = [str(plugin_dir), *env.get("PYTHONPATH", "").split(os.pathsep)]
    env["PYTHONPATH"] = os.pathsep.join(part for part in python_path if part)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/index/test_isolation.py::test_index_directory_is_absolute_and_outside_home",
            "tests/index/test_isolation.py::test_index_directory_does_not_reuse_previous_test",
            "tests/index/test_isolation.py::test_index_directory_has_no_marker_from_previous_test",
            "-p",
            "index_env_probe",
        ],
        check=False,
        cwd=Path(__file__).parents[2],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result_path.read_text(encoding="utf-8")) == original_value
