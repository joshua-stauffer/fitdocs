"""The private atomic-write helper for this package (Requirement 4.3, 7.3, 8.1).

A deliberate private copy of the temp-file-then-``os.replace`` idiom used
elsewhere in fitdocs (``quarantine.py``, ``load/engine.py``,
``history/engine.py``, ``tiles.py``, ``load/profile.py``,
``plans/engine.py``): this package may not import ``fitdocs.docio`` or any
engine module (see "Allowed Dependencies" in design.md), so it cannot reuse a
shared helper. Its site is recorded in queue item
``2026-09-15-atomic-write-helper-copied-per-engine`` for eventual
consolidation.

Unlike the other copies, this one ``flush``es and ``fsync``s the temporary
file before ``os.replace`` -- design.md's AtomicWriter component calls for
both.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


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
