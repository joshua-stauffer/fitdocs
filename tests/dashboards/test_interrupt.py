"""Real-process interrupt of ``fitdocs dashboard refresh`` (Req 7.10, 13.7, 14.8).

The harness follows ``tests/query/test_interrupt.py``: a child runs the real CLI
over a copy of the real index fixture, a hook on the store's ``execute_named``
writes a marker file when the chart's statement reaches DuckDB, and the test
sends one SIGINT. The trial repeats with a fresh child each time. Every wait is
bounded and the child's process group is killed in a ``finally``.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.dashboards._helpers import (
    assert_untouched,
    directive_block,
    page_text,
    snapshot_of,
    write_page,
)
from tests.dashboards.conftest import IndexedDashboardRoot, copy_dashboard_root

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Runs the real CLI. The only addition is a marker file written when the
# connection is asked to execute, by name, a statement that contains the text
# in argv[2] (the chart binds by name, so ``execute_named`` is the call that
# fires; ``execute`` is hooked too for completeness). On both duckdb versions
# that call itself runs the whole aggregate.
_CHILD = """
import sys
from pathlib import Path
import fitdocs.index.store as store

_original = store.IndexConnection.execute
_marker = Path(sys.argv.pop(1))
_needle = sys.argv.pop(1)

def _execute(self, sql, *args, **kwargs):
    if _needle in sql:
        _marker.write_text("running")
    return _original(self, sql, *args, **kwargs)

_original_named = store.IndexConnection.execute_named

def _execute_named(self, sql, *args, **kwargs):
    if _needle in sql:
        _marker.write_text("running")
    return _original_named(self, sql, *args, **kwargs)

store.IndexConnection.execute = _execute
store.IndexConnection.execute_named = _execute_named
from fitdocs.cli import app

app()
"""

_NEEDLE = "range(100000000)"
# Minutes of work on any machine; an aggregating statement, because duckdb
# honours an interrupt promptly only inside an aggregate (tasks.md 2.2).
_SQL = (
    "SELECT CAST(sum(a.range * b.range) AS VARCHAR) AS label, 1.0 AS value "
    "FROM range(100000000) a, range(100000000) b"
)
_EXIT_INTERRUPTED = 130
# Without any interrupt call the hang is intermittent (7 of 16 runs on duckdb
# 1.5.6, 2 of 6 on 1.2.0), so one trial would pass a regression by chance.
_TRIALS = 14
_BOUND_S = 20.0


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _environment(fixture: IndexedDashboardRoot, base: Path) -> dict[str, str]:
    base.mkdir()
    temp = base / "tmp"
    temp.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            **fixture.environ,
            "TMPDIR": str(temp),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(_REPO_ROOT / "src"),
        }
    )
    environment.pop("XDG_CACHE_HOME", None)
    environment.pop("FITDOCS_DATA", None)
    return environment


def _interrupt_once(
    fixture: IndexedDashboardRoot,
    environment: dict[str, str],
    base: Path,
    trial: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dashboards = fixture.root / "dashboards"
    page = dashboards / "p.md"
    page_before = page.read_bytes()
    before = snapshot_of(dashboards)
    marker = base / f"running-{trial}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CHILD,
            str(marker),
            _NEEDLE,
            "dashboard",
            "refresh",
            "--out",
            str(fixture.root),
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
        assert process.poll() is None, process.communicate()
        started = time.monotonic()
        process.send_signal(signal.SIGINT)
        try:
            stdout, stderr = process.communicate(timeout=_BOUND_S)
        except subprocess.TimeoutExpired:
            pytest.fail(f"trial {trial}: no exit within {_BOUND_S} s of SIGINT")
        elapsed = time.monotonic() - started
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)

    with capsys.disabled():
        print(f"\ntrial {trial}: exited {elapsed:.2f} s after SIGINT")
    assert process.returncode == _EXIT_INTERRUPTED, (trial, stdout, stderr)
    assert stdout == "", (trial, stdout)
    assert stderr.endswith("Dashboard run interrupted.\n"), (trial, stderr)
    assert "Traceback" not in stderr
    assert not _alive(process.pid)
    assert page.read_bytes() == page_before
    assert_untouched(before, snapshot_of(dashboards))
    assert not (dashboards / "assets").exists() or not any(
        (dashboards / "assets").rglob("*.svg")
    )
    assert list(fixture.root.rglob(".dashboards-*.tmp")) == []


def test_sigint_during_a_running_chart_ends_the_run_cleanly(
    indexed_dashboard_root: IndexedDashboardRoot,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = copy_dashboard_root(indexed_dashboard_root, tmp_path)
    keys = [
        ("id", "slow"),
        ("kind", "bar"),
        ("mode", "relative"),
        ("title", "A chart that runs for minutes"),
        ("sql", f"|\n  {_SQL}"),
        ("channels", "\n  x: label\n  y: value"),
    ]
    write_page(fixture.root, "p", page_text(directive_block(keys)))
    base = tmp_path / "child"
    environment = _environment(fixture, base)
    for trial in range(_TRIALS):
        _interrupt_once(fixture, environment, base, trial, capsys)
