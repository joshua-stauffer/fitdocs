"""Root conftest: make bytecode caching unable to falsify mutation evidence.

`change-protocol.md` § Fixture Discrimination makes every new assertion owe an
apply/observe-red/revert/observe-green cycle. CPython's default `.pyc`
invalidation compares the source's **mtime and size** against the values in the
cache header, and the mutations that gate mandates routinely change neither --
`= 2` to `= 3`, `< 1` to `< 0`, flipping a `not`. When such a mutation is also
reverted inside a single filesystem mtime second, the cached bytecode still
looks valid and the interpreter keeps executing the mutated code.

That corrupts the gate in both directions. The revert reports green while the
suite runs the mutation; or the mutation never takes effect and an implementer
concludes a real assertion does not discriminate -- a confident, evidence-backed,
wrong conclusion, which is harder to catch than no evidence at all.

Reproduced in this repo (`2026-07-26-stale-pyc-can-falsify-mutation-evidence`):
after a same-size mutation and a same-second revert, `git diff` was empty and
the source read `LOAD_PAYLOAD_VERSION = 2` while the interpreter reported `3`.

The fix is structural rather than procedural, because a step an agent must
remember is a step that gets skipped: purge any bytecode cache under `src/`
before the first import of the package under test, and stop writing new ones for
the rest of the session. Both run on every pytest invocation, which is the one
thing every mutation observation has in common.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"


def _purge_src_bytecode() -> None:
    """Delete every `__pycache__` under `src/`, before anything imports it.

    Positive control on the walk: `src/` must exist. A guard that silently
    scans zero directories is the `vacuous walk` anti-pattern this repo has
    already shipped twice, and it would fail exactly the same way here -- the
    purge would appear to run and protect nothing.
    """
    assert _SRC.is_dir(), f"expected the package source at {_SRC}"
    for cache_dir in _SRC.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)


# Order matters: purge what a stray `python -c` may have left behind, then stop
# anything this session runs from writing more. Together they mean a stale cache
# entry for `src/` cannot exist during a pytest run, so no mutation observation
# can read one. The purge runs at rootdir-conftest import, which pytest loads
# before it collects `tests/` -- i.e. before `fitdocs` is imported.
_purge_src_bytecode()
sys.dont_write_bytecode = True

# `sys.dont_write_bytecode` governs this interpreter only, and it is not enough
# on its own: eight test modules spawn a `sys.executable` subprocess that imports
# fitdocs, and each child re-created the caches mid-run until this was added.
# Those are the worst entries of all -- written *during* the suite, so a mutation
# cycle around a subprocess test would read them stale. The environment variable
# is the one form a child process inherits.
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
