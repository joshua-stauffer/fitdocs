"""Relay conftest: make bytecode caching unable to falsify mutation evidence.

Mirrors the root `conftest.py`. CPython's default `.pyc` invalidation compares
the source's mtime and size, and a one-token mutation reverted inside one
filesystem second changes neither, so the interpreter can keep running the
mutated code. Purge every `__pycache__` under `src/` before the package under
test is first imported, and stop this session and its child processes from
writing new ones.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"


def _purge_src_bytecode() -> None:
    """Delete every `__pycache__` under `src/`; `src/` must exist (no vacuous purge)."""
    assert _SRC.is_dir(), f"expected the package source at {_SRC}"
    for cache_dir in _SRC.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


_purge_src_bytecode()
sys.dont_write_bytecode = True
# The environment variable is the one form a subprocess inherits.
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
