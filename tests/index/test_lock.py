from __future__ import annotations

import errno
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _lock_module() -> Any:
    import fitdocs.index.lock as lock_module

    return lock_module


def _probe_lock(
    path: Path, *, timeout: float = 2.0
) -> subprocess.CompletedProcess[str]:
    script = """
import sys
from pathlib import Path
from fitdocs.index.lock import WriterBusy, writer_lock
try:
    with writer_lock(Path(sys.argv[1])):
        print('acquired', flush=True)
except WriterBusy:
    print('busy', flush=True)
"""
    try:
        return subprocess.run(
            [sys.executable, "-c", script, str(path)],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("lock probe subprocess blocked past its timeout")


def _wait_for_ready(child: subprocess.Popen[str], ready: Path) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if ready.exists():
            return
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            pytest.fail(f"lock holder exited before acquiring: {stdout} {stderr}")
        time.sleep(0.01)
    pytest.fail("lock holder did not signal acquisition before timeout")


def _start_holder(path: Path, ready: Path) -> subprocess.Popen[str]:
    script = """
import sys
import time
from pathlib import Path
from fitdocs.index.lock import writer_lock
with writer_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text('ready', encoding='utf-8')
    print('locked', flush=True)
    time.sleep(60)
"""
    return subprocess.Popen(
        [sys.executable, "-c", script, str(path), str(ready)],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _kill_and_reap(child: subprocess.Popen[str]) -> None:
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=5)


def test_subprocess_contention_and_process_death_release_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "index.lock"
    ready = tmp_path / "holder-ready"
    holder = _start_holder(lock_path, ready)
    try:
        _wait_for_ready(holder, ready)
        assert lock_path.exists()
        assert ready.read_text(encoding="utf-8") == "ready"

        busy = _probe_lock(lock_path)
        assert busy.returncode == 0
        assert busy.stdout.strip() == "busy"

        sigkill = getattr(signal, "SIGKILL", None)
        if sigkill is None:
            holder.kill()
        else:
            holder.send_signal(sigkill)
        holder.wait(timeout=5)
        assert holder.returncode is not None
        assert lock_path.exists()
        acquired_after_death = _probe_lock(lock_path)
        assert acquired_after_death.returncode == 0
        assert acquired_after_death.stdout.strip() == "acquired"
    finally:
        _kill_and_reap(holder)


def test_existing_lock_file_is_never_modified(tmp_path: Path) -> None:
    lock_path = tmp_path / "index.lock"
    original = b"old synthetic lock contents\x00\xff\n"
    lock_path.write_bytes(original)
    old_time_ns = 946684800_123456789
    os.utime(lock_path, ns=(old_time_ns, old_time_ns))
    before = lock_path.stat()
    assert before.st_size == len(original)
    assert before.st_mtime_ns == old_time_ns

    with _lock_module().writer_lock(lock_path):
        assert lock_path.read_bytes() == original

    after = lock_path.stat()
    assert lock_path.read_bytes() == original
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_new_lock_file_has_private_mode(tmp_path: Path) -> None:
    lock_path = tmp_path / "new.lock"
    assert not lock_path.exists()

    with _lock_module().writer_lock(lock_path):
        assert lock_path.exists()
        assert lock_path.stat().st_mode & 0o777 == 0o600


def test_lock_is_held_during_body_and_released_on_normal_exit(tmp_path: Path) -> None:
    lock_path = tmp_path / "index.lock"
    with _lock_module().writer_lock(lock_path):
        while_held = _probe_lock(lock_path)
        assert while_held.returncode == 0
        assert while_held.stdout.strip() == "busy"

    after_normal_exit = _probe_lock(lock_path)
    assert after_normal_exit.returncode == 0
    assert after_normal_exit.stdout.strip() == "acquired"


def test_lock_is_released_when_body_raises(tmp_path: Path) -> None:
    lock_path = tmp_path / "index.lock"
    failure = RuntimeError("synthetic body failure")
    with pytest.raises(RuntimeError) as raised, _lock_module().writer_lock(lock_path):
        raise failure
    assert raised.value is failure

    after_exception_exit = _probe_lock(lock_path)
    assert after_exception_exit.returncode == 0
    assert after_exception_exit.stdout.strip() == "acquired"


_CONTENTION_ERRNOS = tuple(
    dict.fromkeys((errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK))
)


@pytest.mark.parametrize("backend", ("fcntl", "msvcrt"))
@pytest.mark.parametrize(
    "scenario",
    (
        ("normal", None),
        ("body_error", None),
        *(("busy", error_number) for error_number in _CONTENTION_ERRNOS),
        ("unexpected_error", errno.EIO),
        ("unlock_error", errno.EIO),
    ),
    ids=(
        "normal",
        "body-error",
        *(f"busy-errno-{value}" for value in _CONTENTION_ERRNOS),
        "unexpected-error",
        "unlock-error",
    ),
)
def test_backend_call_and_cleanup_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    scenario: tuple[str, int | None],
) -> None:
    lock_module = _lock_module()
    scenario_name, error_number = scenario
    fd = 42001
    path = tmp_path / "matrix.lock"
    events: list[tuple[object, ...]] = []

    def open_spy(open_path: Path, flags: int, mode: int = 0o777) -> int:
        events.append(("open", open_path, flags, mode))
        return fd

    def close_spy(open_fd: int) -> None:
        events.append(("close", open_fd))

    monkeypatch.setattr(os, "open", open_spy)
    monkeypatch.setattr(os, "close", close_spy)

    if scenario_name in {"busy", "unexpected_error", "unlock_error"}:
        injected_error = OSError(error_number, f"synthetic {scenario_name}")
    else:
        injected_error = None

    class FakeFcntl:
        LOCK_EX = 1
        LOCK_NB = 4
        LOCK_UN = 8

        @staticmethod
        def flock(actual_fd: int, operation: int) -> None:
            events.append(("fcntl", actual_fd, operation))
            if injected_error is not None and (
                (scenario_name in {"busy", "unexpected_error"} and operation == 5)
                or (scenario_name == "unlock_error" and operation == 8)
            ):
                raise injected_error

    class FakeMsvcrt(ModuleType):
        LK_LOCK = 100
        LK_NBLCK = 101
        LK_UNLCK = 102

        def __init__(self) -> None:
            super().__init__("msvcrt")

        def locking(self, actual_fd: int, operation: int, count: int) -> None:
            events.append(("msvcrt", actual_fd, operation, count))
            if injected_error is not None and (
                (scenario_name in {"busy", "unexpected_error"} and operation == 101)
                or (scenario_name == "unlock_error" and operation == 102)
            ):
                raise injected_error

    if backend == "fcntl":
        monkeypatch.setattr(lock_module, "fcntl", FakeFcntl)
        acquired_event: tuple[object, ...] = ("fcntl", 42001, 5)
        released_event: tuple[object, ...] = ("fcntl", 42001, 8)
    else:
        monkeypatch.setattr(lock_module, "fcntl", None)
        monkeypatch.setitem(sys.modules, "msvcrt", FakeMsvcrt())
        acquired_event = ("msvcrt", 42001, 101, 1)
        released_event = ("msvcrt", 42001, 102, 1)

    opened_event = ("open", path, os.O_RDWR | os.O_CREAT, 0o600)
    closed_event = ("close", 42001)
    body_event = ("body",)
    expected_events = [opened_event, acquired_event]
    body_events: list[tuple[object, ...]] = []
    raised_error: BaseException | None = None

    if scenario_name == "busy":
        with (
            pytest.raises(lock_module.WriterBusy) as raised,
            lock_module.writer_lock(path),
        ):
            body_events.append(body_event)
        raised_error = raised.value.__cause__
    elif scenario_name == "unexpected_error":
        with pytest.raises(OSError) as raised, lock_module.writer_lock(path):
            body_events.append(body_event)
        raised_error = raised.value
    elif scenario_name == "unlock_error":
        with pytest.raises(OSError) as raised, lock_module.writer_lock(path):
            body_events.append(body_event)
            events.append(body_event)
        raised_error = raised.value
        expected_events.append(body_event)
        expected_events.append(released_event)
    elif scenario_name == "body_error":
        body_error = RuntimeError("synthetic body error")
        with pytest.raises(RuntimeError) as raised, lock_module.writer_lock(path):
            body_events.append(body_event)
            events.append(body_event)
            raise body_error
        assert raised.value is body_error
        expected_events.append(body_event)
        expected_events.append(released_event)
    else:
        with lock_module.writer_lock(path):
            body_events.append(body_event)
            events.append(body_event)
        expected_events.append(body_event)
        expected_events.append(released_event)

    expected_events.append(closed_event)
    assert events == expected_events
    assert body_events == (
        [] if scenario_name in {"busy", "unexpected_error"} else [body_event]
    )
    if injected_error is not None:
        assert raised_error is injected_error
