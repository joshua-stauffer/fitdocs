"""The private atomic-write helper for this package (Requirement 4.3, 7.3, 8.1).

A deliberate private copy of the temp-file-then-``os.replace`` idiom used
elsewhere in fitdocs (``quarantine.py``, ``load/engine.py``,
``history/engine.py``, ``tiles.py``, ``load/profile.py``,
``plans/engine.py``): this package may not import ``fitdocs.docio`` or any
engine module (see "Allowed Dependencies" in design.md), so it cannot reuse a
shared helper. Its site is recorded in queue item
``2026-09-15-atomic-write-helper-copied-per-engine`` for eventual
consolidation.

:func:`write_atomic_new` is the no-clobber variant (``os.link`` instead of
``os.replace``) used for inbox deliveries, which must never overwrite a file
another tool created.

Unlike the other copies, this one ``flush``es and ``fsync``s the temporary
file before ``os.replace`` -- design.md's AtomicWriter component calls for
both.
"""

from __future__ import annotations

import errno
import os
import tempfile
from pathlib import Path

_NO_HARD_LINKS = frozenset({errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM, errno.ENOSYS})


def write_atomic(path: Path, data: bytes, *, prefix: str) -> None:
    """Write ``data`` to ``path`` atomically.

    Creates a dot-prefixed temporary file (mode ``0o600``, via
    :func:`tempfile.mkstemp`) in ``path``'s own directory, writes and
    fsyncs it, then replaces ``path`` with it in one filesystem operation.
    On any failure -- writing, fsyncing, or replacing -- the temporary file
    is removed and ``path`` is left exactly as it was.
    """
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{prefix}-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_atomic_new(path: Path, data: bytes, *, prefix: str) -> None:
    """Write ``data`` to ``path`` atomically, refusing to replace anything.

    Like :func:`write_atomic`, but the final placement is ``os.link`` of the
    fsynced temporary file to ``path`` followed by removing the temporary
    name: ``link`` fails with :class:`FileExistsError` if anything -- a file
    another tool created a moment ago included -- already sits at ``path``,
    where ``os.replace`` would silently overwrite it. On any failure the
    temporary file is removed and ``path`` is left exactly as it was (a hard
    kill can still leave the hidden temporary file behind).

    On a filesystem that cannot make hard links (``link`` raises ``OSError``
    with ``ENOTSUP``, ``EOPNOTSUPP``, ``EPERM`` or ``ENOSYS``), placement
    falls back to checking ``os.path.lexists`` -- :class:`FileExistsError`
    if taken -- and then ``os.replace``. The check-then-replace race window
    reopens only on such filesystems.
    """
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{prefix}-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_path, path)
        except OSError as exc:
            if exc.errno not in _NO_HARD_LINKS:
                raise
            if os.path.lexists(path):
                raise FileExistsError(
                    errno.EEXIST, os.strerror(errno.EEXIST), str(path)
                ) from None
            os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
