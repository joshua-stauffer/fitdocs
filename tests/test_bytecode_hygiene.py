"""The bytecode-cache guarantee the fixture-discrimination gate depends on.

`change-protocol.md` § Fixture Discrimination requires every new assertion to be
verified by mutating production code, observing red, reverting, and observing
green. CPython validates a `.pyc` against the source's mtime and size, both of
which a same-size mutation reverted within one second leaves unchanged -- so the
interpreter can keep running mutated code across the revert, or never run the
mutation at all.

The root `conftest.py` removes the hazard rather than documenting a step around
it. These tests pin that it is actually in force during a run, because the
failure it prevents is silent: nothing about a stale cache makes the suite look
wrong, which is exactly what makes it dangerous.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"


def test_the_session_does_not_write_bytecode_for_the_package_under_test() -> None:
    """Nothing this session imports may leave a `.pyc` behind.

    Without this, a mutation applied mid-session writes a cache entry that a
    same-second, same-size revert does not invalidate.
    """
    assert sys.dont_write_bytecode is True


def test_no_bytecode_cache_exists_under_src_during_the_run() -> None:
    """No cached bytecode for `src/` may be readable while the suite runs.

    Disabling writes alone is not enough: a stray `uv run python -c` outside
    pytest writes caches that persist, and those are precisely the entries a
    later mutation cycle would read stale. The root conftest purges them before
    the first import, so by collection time there are none.
    """
    assert _SRC.is_dir(), f"expected the package source at {_SRC}"
    caches = sorted(str(p.relative_to(_SRC)) for p in _SRC.rglob("__pycache__"))
    assert caches == [], f"bytecode caches survived under src/: {caches}"
