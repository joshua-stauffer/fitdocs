"""Synthetic DuckDB file and lock helpers shared by index tests."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_HOLD_SCRIPT = r"""
import os
import sys
from pathlib import Path
from fitdocs.index.store import open_index

try:
    connection = open_index(Path(sys.argv[1]), read_only=sys.argv[2] == "True")
except BaseException as error:
    print(f"OPEN_ERROR {type(error).__name__}: {error}", flush=True)
    raise
print(f"HOLDING {os.getpid()}", flush=True)
sys.stdin.readline()
connection.close()
"""


def _kill_and_reap(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    if process.stdin is not None:
        process.stdin.close()


@contextmanager
def hold_index(path: Path, *, read_only: bool) -> Iterator[int]:
    """Hold a facade-opened database in a child until the context exits."""
    process = subprocess.Popen(
        [sys.executable, "-c", _HOLD_SCRIPT, str(path), str(read_only)],
        cwd=_REPOSITORY_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    lines: queue.Queue[str | None] = queue.Queue(maxsize=1)

    def read_startup_line() -> None:
        assert process.stdout is not None
        lines.put(process.stdout.readline())

    reader = threading.Thread(target=read_startup_line, daemon=True)
    reader.start()
    try:
        try:
            line = lines.get(timeout=15)
        except queue.Empty as error:
            raise RuntimeError("failed to open index: startup timed out") from error
        if line is None or not line.startswith("HOLDING "):
            detail = "no startup line" if line is None else line.rstrip()
            raise RuntimeError(f"failed to open index: {detail}")
        yield int(line.split()[1])
    finally:
        _kill_and_reap(process)
        reader.join(timeout=1)


def forge_storage_version(path: Path, version: int) -> None:
    """Rewrite header bytes 12–20 and recompute the bytes 8–4096 checksum."""
    data = bytearray(path.read_bytes())
    if len(data) < 4096:
        raise ValueError("database file is shorter than its first block")
    data[12:20] = version.to_bytes(8, "little", signed=False)
    checksum = 5381
    multiplier = 0xBF58476D1CE4E5B9
    mask = (1 << 64) - 1
    for offset in range(8, 4096, 8):
        word = int.from_bytes(data[offset : offset + 8], "little")
        checksum = (checksum ^ (word * multiplier)) & mask
    data[0:8] = checksum.to_bytes(8, "little")
    path.write_bytes(data)
