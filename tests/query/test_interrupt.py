"""Real-process interrupt behavior of ``fitdocs query`` (Req 6.6)."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.query.test_crash_vectors import _child_environment
from tests.query.test_spill import _SPILL_MEMORY_LIMIT

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Runs the real CLI. The only addition is a marker file written when the
# connection is asked to execute the user's statement. On duckdb 1.2.0 that
# call itself runs the whole statement (a result-fetch hook would only fire
# after it finished), so the marker is written on entry and the test waits a
# further moment for DuckDB to be inside it.
_CHILD = """
import sys
from pathlib import Path
import os
import fitdocs.index.store as store
from fitdocs.query import sandbox

if os.environ.get("SPILL_TEST_MEMORY_LIMIT"):
    sandbox.RESOURCE_SETTINGS = {
        "memory_limit": os.environ["SPILL_TEST_MEMORY_LIMIT"],
        "threads": 2,
        "max_temp_directory_size": "4GB",
    }

_original = store.IndexConnection.execute
_marker = Path(sys.argv.pop(1))
_statement = sys.argv[2]

def _execute(self, sql, *args, **kwargs):
    if sql == _statement:
        _marker.write_text("running")
    return _original(self, sql, *args, **kwargs)

store.IndexConnection.execute = _execute
from fitdocs.cli import app

app()
"""

# Minutes of work on any machine; only an interrupt or the deadline ends it.
_JOIN_STATEMENT = (
    "SELECT sum(a.range * b.range) FROM range(100000000) a, range(100000000) b"
)
# Under the test_spill.py memory limit this sorts through the spill directory.
_SPILLING_STATEMENT = (
    "SELECT sum(total) FROM ("
    "SELECT row_number() OVER (ORDER BY i DESC) AS total "
    "FROM range(400000000) t(i))"
)
_EXIT_INTERRUPTED = 130


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _spill_files(base: Path) -> list[Path]:
    return [
        path
        for directory in base.rglob("query-spill-*")
        for path in directory.rglob("*")
        if path.is_file() and path.stat().st_size > 0
    ]


def _interrupt_once(
    root: Path,
    environment: dict[str, str],
    base: Path,
    statement: str,
    memory_limit: str,
    trial: int,
) -> None:
    marker = base / f"running-{trial}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CHILD,
            str(marker),
            "query",
            statement,
            "--out",
            str(root),
            "--timeout",
            "300",
        ],
        cwd=_REPO_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 60
        while not marker.exists():
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline, "the statement never started"
            time.sleep(0.05)
        time.sleep(0.5)  # DuckDB is well inside a minutes-long statement
        if memory_limit:
            assert _spill_files(base), "the spilling statement has not spilled yet"
        assert process.poll() is None, process.communicate()
        started = time.monotonic()
        process.send_signal(signal.SIGINT)
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            pytest.fail(f"trial {trial}: no exit within 20 s of SIGINT")
        elapsed = time.monotonic() - started
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)

    assert process.returncode == _EXIT_INTERRUPTED, (trial, stdout, stderr)
    assert stdout == ""
    assert stderr == "Query interrupted.\n"
    assert "Traceback" not in stderr
    assert elapsed < 20
    assert not _alive(process.pid)
    assert list(base.rglob("query-spill-*")) == []


# Without the interrupt call the hang is intermittent: 8 of 14 manual CLI runs
# hung (3 of 3, 2 of 3 and 3 of 8 in successive batches). A single run would
# pass a regression by chance, so the join case repeats.
@pytest.mark.parametrize(
    ("statement", "memory_limit", "trials"),
    [(_JOIN_STATEMENT, "", 14), (_SPILLING_STATEMENT, _SPILL_MEMORY_LIMIT, 2)],
    ids=["join", "spilling-sort"],
)
def test_sigint_during_running_statement_exits_cleanly(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    statement: str,
    memory_limit: str,
    trials: int,
) -> None:
    root, source_index = indexed_root
    base = tmp_path / "child"
    base.mkdir()
    environment = _child_environment(
        source_index, base / "home", base / "index", base / "tmp"
    )
    environment["SPILL_TEST_MEMORY_LIMIT"] = memory_limit
    for trial in range(trials):
        _interrupt_once(root, environment, base, statement, memory_limit, trial)
