"""Advisory writer lock for an analytics index file."""

from __future__ import annotations

import errno
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses msvcrt below.
    fcntl = None  # type: ignore[assignment]


class WriterBusy(Exception):
    """Another process already holds this index's writer lock."""


@contextmanager
def writer_lock(path: Path) -> Iterator[None]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    locked = False
    unlock: Callable[[], None]
    try:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if _is_contention(error):
                    raise WriterBusy(f"writer lock is held for {path}") from error
                raise
            locked = True

            def unlock_fcntl() -> None:
                fcntl.flock(fd, fcntl.LOCK_UN)

            unlock = unlock_fcntl
        else:
            import msvcrt

            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                if _is_contention(error):
                    raise WriterBusy(f"writer lock is held for {path}") from error
                raise
            locked = True

            def unlock_msvcrt() -> None:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

            unlock = unlock_msvcrt

        try:
            yield
        finally:
            if locked:
                unlock()
    finally:
        os.close(fd)


def _is_contention(error: OSError) -> bool:
    return error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}
