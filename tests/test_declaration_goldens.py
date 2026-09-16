"""Byte-golden pin for the four emitted ``AGENTS.md`` declaration texts.

Task 4.1 originally; extended by ``load-history`` task 1.2 to a third,
``history/``, directory, and by ``training-blocks`` task 1.2 to a fourth,
``blocks/``.

Three review rounds each cleared a named false sentence in
``fitdocs.declaration.declaration_text``'s hand-written prose and each left a
different false sentence standing -- a text asserting the *opposite* of the
truth on every load-bearing claim passed 40/40 substring assertions. Pinning
each directory's *entire* emitted text as a committed byte-golden (mirroring
``tests/render/test_golden_docs.py``'s pattern) turns every future prose change
into a reviewable diff in a committed artifact, rather than an invisible edit
inside an f-string: a paraphrase of any kind fails this suite by construction.

Parameterized over :data:`fitdocs.layout.DECLARED_DIRS`, so adding a declared
directory fails here until its golden is authored -- the same "cannot silently
go unmentioned" property the rest of the suite relies on for region ids.

Regenerating the committed goldens (only when an intentional text change
should update them): ``uv run python -m tests.test_declaration_goldens``. The
tests read those files back and assert byte-equality, so goldens always equal
live ``declaration_text`` output -- never hand-edited.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fitdocs.declaration import declaration_text
from fitdocs.layout import (
    ARCHIVE_DIR,
    BLOCKS_DIR,
    DECLARED_DIRS,
    HISTORY_DIR,
    WORKOUTS_DIR,
)

_GOLDEN_DIR = Path(__file__).parent / "declaration_golden"

# Directory (data-root-relative, POSIX, trailing slash) -> golden filename stem.
# Named so the directory is recoverable from the filename, per task 4.1's fix
# plan step 5. A literal dictionary, not a derivation over `DECLARED_DIRS`: a
# declared directory with no entry here makes both `_golden_path` and the
# parameterized test below raise `KeyError` rather than silently skip it.
_GOLDEN_NAMES: dict[str, str] = {
    f"{WORKOUTS_DIR}/": "workouts",
    f"{HISTORY_DIR}/": "history",
    f"{ARCHIVE_DIR}/": "fit-archive",
    f"{BLOCKS_DIR}/": "blocks",
}


def _golden_path(directory: str) -> Path:
    name = _GOLDEN_NAMES[directory]
    return _GOLDEN_DIR / f"{name}.AGENTS.md"


def _write_goldens() -> None:
    """(Re)generate every committed golden from live ``declaration_text`` output.

    Intended for ``python -m tests.test_declaration_goldens`` only, when an
    intentional prose change should refresh the snapshots.
    """
    _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for directory in DECLARED_DIRS:
        _golden_path(directory).write_text(
            declaration_text(directory), encoding="utf-8"
        )


@pytest.mark.parametrize("directory", DECLARED_DIRS)
def test_declaration_text_matches_committed_golden(directory: str) -> None:
    """The live-composed declaration text equals its committed golden byte-for-byte.

    Every declared directory in :data:`fitdocs.layout.DECLARED_DIRS` must have a
    named entry in :data:`_GOLDEN_NAMES` -- a ``KeyError`` here means a newly
    declared directory has no authored golden yet.
    """
    golden = _golden_path(directory)
    assert golden.exists(), (
        f"no committed golden for {directory!r} at {golden} -- run "
        "`uv run python -m tests.test_declaration_goldens` to author it"
    )
    assert declaration_text(directory) == golden.read_text(encoding="utf-8")


if __name__ == "__main__":
    _write_goldens()
