"""Shared analytics-index fixture helper tests for task 4.2."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

import pytest

from fitdocs.index.store import IndexOpenError, create_index, open_index
from tests.index._helpers import forge_storage_version, hold_index


def _assert_process_gone(pid: int) -> None:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    finally:
        with suppress(ChildProcessError):
            os.waitpid(pid, 0)
    pytest.fail("hold_index left its subprocess alive")


def test_forge_version_64_preserves_fresh_index_header(tmp_path: Path) -> None:
    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    original = path.read_bytes()

    forge_storage_version(path, 69)
    version_69_data = path.read_bytes()
    version_69_header = version_69_data[:4096]
    assert version_69_header != original[:4096]
    assert int.from_bytes(version_69_header[12:20], "little") == 69
    assert version_69_data[4096:] == original[4096:]

    forge_storage_version(path, 64)

    assert path.read_bytes() == original


def test_hold_index_blocks_writer_then_releases_and_reaps_process(
    tmp_path: Path,
) -> None:
    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass

    with hold_index(path, read_only=False) as holder_pid, pytest.raises(IndexOpenError):
        open_index(path, read_only=False)

    _assert_process_gone(holder_pid)
    with open_index(path, read_only=False):
        pass


def test_hold_index_reaps_process_after_body_exception(tmp_path: Path) -> None:
    path = tmp_path / "index.duckdb"
    with create_index(path):
        pass
    holder_pid: int | None = None

    with (
        pytest.raises(RuntimeError, match="synthetic body failure"),
        hold_index(path, read_only=True) as child_pid,
    ):
        holder_pid = child_pid
        raise RuntimeError("synthetic body failure")

    assert holder_pid is not None
    _assert_process_gone(holder_pid)


def test_hold_index_reaps_process_after_startup_failure(tmp_path: Path) -> None:
    with (
        pytest.raises(RuntimeError, match="failed to open index"),
        hold_index(tmp_path / "absent.duckdb", read_only=True),
    ):
        pytest.fail("an absent database cannot be held")


def test_review_failed_startup_calls_cleanup_on_the_spawned_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import tests.index._helpers as helper

    helper_module = cast(Any, helper)
    original_popen = subprocess.Popen
    original_cleanup = helper._kill_and_reap
    processes: list[subprocess.Popen[str]] = []
    cleanups: list[subprocess.Popen[str]] = []

    def spawn(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    def cleanup(process: subprocess.Popen[str]) -> None:
        cleanups.append(process)
        original_cleanup(process)

    monkeypatch.setattr(helper_module.subprocess, "Popen", spawn)
    monkeypatch.setattr(helper, "_kill_and_reap", cleanup)
    try:
        with (
            pytest.raises(RuntimeError, match="failed to open index"),
            hold_index(tmp_path / "absent-startup.duckdb", read_only=True),
        ):
            pytest.fail("an absent database cannot be held")
    finally:
        for process in processes:
            original_cleanup(process)

    assert len(processes) == 1
    assert cleanups == processes
    assert processes[0].returncode is not None


def test_review_startup_timeout_uses_bound_and_reaps_real_child(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import tests.index._helpers as helper

    helper_module = cast(Any, helper)
    original_queue = queue.Queue
    original_popen = subprocess.Popen
    original_cleanup = helper._kill_and_reap
    timeouts: list[object] = []
    processes: list[subprocess.Popen[str]] = []

    class QueueProbe:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.queue: queue.Queue[str | None] = original_queue(*args, **kwargs)

        def put(self, item: str | None) -> None:
            self.queue.put(item)

        def get(self, *args: Any, **kwargs: Any) -> str | None:
            timeouts.append(kwargs.get("timeout"))
            raise queue.Empty

    def spawn(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(helper_module.queue, "Queue", QueueProbe)
    monkeypatch.setattr(helper_module.subprocess, "Popen", spawn)
    path = tmp_path / "startup-timeout.duckdb"
    with create_index(path):
        pass
    try:
        with (
            pytest.raises(RuntimeError, match="startup timed out"),
            hold_index(path, read_only=True),
        ):
            pytest.fail("forced timeout must not yield")
    finally:
        for process in processes:
            original_cleanup(process)

    assert timeouts == [15]
    assert len(processes) == 1
    assert processes[0].returncode is not None


def test_review_each_reap_wait_has_a_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import tests.index._helpers as helper

    helper_module = cast(Any, helper)
    original_popen = subprocess.Popen
    original_cleanup = helper._kill_and_reap
    processes: list[subprocess.Popen[str]] = []
    real_waits: list[tuple[subprocess.Popen[str], Any]] = []
    wait_timeouts: list[object] = []

    def spawn(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
        process = original_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait
        real_waits.append((process, real_wait))
        forced_timeout = False

        def wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            nonlocal forced_timeout
            timeout = wait_kwargs.get("timeout")
            wait_timeouts.append(timeout)
            if not forced_timeout:
                forced_timeout = True
                raise subprocess.TimeoutExpired(
                    "child wait", timeout=cast(float, timeout)
                )
            return real_wait(*wait_args, **wait_kwargs)

        cast(Any, process).wait = wait
        return process

    monkeypatch.setattr(helper_module.subprocess, "Popen", spawn)
    path = tmp_path / "bounded-reap.duckdb"
    with create_index(path):
        pass
    try:
        with hold_index(path, read_only=False):
            pass
    finally:
        for process, real_wait in real_waits:
            cast(Any, process).wait = real_wait
            original_cleanup(process)

    assert wait_timeouts == [5, 5]
    assert len(processes) == 1
    assert processes[0].returncode is not None
