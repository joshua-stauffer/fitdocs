"""Child-process compatibility and statement-screening crash vectors."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from fitdocs.index.store import duckdb_version

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_CHILD = "from fitdocs.cli import app; app()"


def _child_environment(
    source_index: Path,
    child_home: Path,
    child_index: Path,
    child_tmp: Path,
) -> dict[str, str]:
    child_home.mkdir(parents=True)
    child_index.mkdir(parents=True)
    child_tmp.mkdir(parents=True)
    shutil.copytree(source_index, child_index / source_index.name)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(child_home),
            "TMPDIR": str(child_tmp),
            "FITDOCS_INDEX_DIR": str(child_index),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(_REPO_ROOT / "src"),
        }
    )
    environment.pop("XDG_CACHE_HOME", None)
    return environment


def _run_child(
    argv: list[str], *, environment: dict[str, str], timeout_s: float = 20
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        argv,
        cwd=_REPO_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
        pytest.fail(
            "query child exceeded its finite deadline and was killed/reaped; "
            f"stdout={stdout!r}, stderr={stderr!r}"
        )
    return_code = process.returncode
    assert return_code is not None
    return subprocess.CompletedProcess(argv, return_code, stdout, stderr)


@pytest.fixture
def query_child_context(
    indexed_root: tuple[Path, Path], tmp_path: Path
) -> tuple[Path, Path, Path]:
    root, index_dir = indexed_root
    child_base = tmp_path / "children"
    child_base.mkdir()
    return root, index_dir, child_base


def test_child_uses_the_installed_index_duckdb_compatibility_version(
    query_child_context: tuple[Path, Path, Path],
) -> None:
    _, source_index, child_base = query_child_context
    environment = _child_environment(
        source_index,
        child_base / "version-home",
        child_base / "version-index",
        child_base / "version-tmp",
    )
    argv = [
        sys.executable,
        "-c",
        "from fitdocs.index.store import duckdb_version; print(duckdb_version())",
    ]

    result = _run_child(argv, environment=environment)

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{duckdb_version()}\n"
    assert result.stderr == ""
    assert tuple(Path(environment["HOME"]).iterdir()) == ()


def test_multi_statement_logging_vector_is_refused_before_side_effects(
    query_child_context: tuple[Path, Path, Path],
) -> None:
    root, source_index, child_base = query_child_context
    logs = child_base / "multi-statement-logs"
    sql = (
        "SELECT * FROM enable_logging(storage='file', "
        f"storage_path='{logs}'); SELECT 42"
    )
    environment = _child_environment(
        source_index,
        child_base / "multi-home",
        child_base / "multi-index",
        child_base / "multi-tmp",
    )
    argv = [
        sys.executable,
        "-c",
        _CLI_CHILD,
        "query",
        sql,
        "--out",
        str(root),
    ]

    result = _run_child(argv, environment=environment)

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert result.stderr == "Query refused: fitdocs query runs exactly one statement.\n"
    assert result.stdout == ""
    assert not logs.exists()
    assert tuple(Path(environment["HOME"]).iterdir()) == ()


def test_single_statement_logging_vector_never_crashes_or_creates_logs(
    query_child_context: tuple[Path, Path, Path],
) -> None:
    root, source_index, child_base = query_child_context
    logs = child_base / "single-statement-logs"
    sql = f"SELECT * FROM enable_logging(storage='file', storage_path='{logs}')"
    environment = _child_environment(
        source_index,
        child_base / "single-home",
        child_base / "single-index",
        child_base / "single-tmp",
    )
    argv = [
        sys.executable,
        "-c",
        _CLI_CHILD,
        "query",
        sql,
        "--out",
        str(root),
    ]

    result = _run_child(argv, environment=environment)

    assert result.returncode in (0, 1), (result.stdout, result.stderr)
    assert not logs.exists()
    assert tuple(Path(environment["HOME"]).iterdir()) == ()
