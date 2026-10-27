"""The changelog text as a release-note pin should read it.

A test that pins "this entry is in the standing ``## [Unreleased]`` section"
must hold before the release that ships the entry, after the cut that turns
``[Unreleased]`` into ``## [X.Y.Z]``, and after later work lands in a fresh
``[Unreleased]``. :func:`unreleased_since` therefore anchors the pin to the
last release the entry *postdates*: it returns the text with ``[Unreleased]``
plus every released section **newer than** that version merged into one
``## [Unreleased]`` section (``### Added`` bullets of each concatenated under
a single ``### Added``, and so on), followed by the sections at or below that
version untouched. An entry misplaced into the anchor release, or any older
one, is therefore still outside the view and the pin fails.

Entries that postdate a later release (say 0.2.0) anchor to a new
``V0_2_0`` constant here, not to ``V0_1_0``.

The one literal release version the pins are anchored to lives here, in one
file, which ``tests/test_version_identity.py`` permits to carry it.
"""

from __future__ import annotations

import re
from pathlib import Path

#: The release every pin currently in ``[Unreleased]`` postdates.
V0_1_0 = "0.1.0"
#: The release every pin that postdates 0.2.0 anchors to.
V0_2_0 = "0.2.0"

_UNRELEASED = "## [Unreleased]"
_RELEASE_HEADING = re.compile(r"(?m)^## \[(\d+)\.(\d+)\.(\d+)\][^\n]*\n")
_SECTION_HEADING = re.compile(r"(?m)^## \[")
_CATEGORY = re.compile(r"(?m)^### ")


def _categories(body: str) -> list[tuple[str, str]]:
    """`body` as ordered (category name, text after the name line) pairs."""
    chunks = _CATEGORY.split(body)[1:]
    pairs = []
    for chunk in chunks:
        name, _, rest = chunk.partition("\n")
        pairs.append((name, rest.strip("\n")))
    return pairs


def unreleased_since(text: str, since: str) -> str:
    """`text` with ``[Unreleased]`` widened to everything newer than `since`."""
    base = tuple(int(part) for part in since.split("."))
    head, marker, rest = text.partition(_UNRELEASED)
    if not marker:
        return text
    boundaries = [m.start() for m in _SECTION_HEADING.finditer(rest)]
    ends = [*boundaries[1:], len(rest)]
    unreleased_end = boundaries[0] if boundaries else len(rest)
    bodies = [rest[:unreleased_end]]
    tail_start = len(rest)
    for start, end in zip(boundaries, ends, strict=True):
        heading = _RELEASE_HEADING.match(rest, start)
        if heading is None:
            tail_start = start
            break
        if tuple(int(part) for part in heading.groups()) <= base:
            tail_start = start
            break
        bodies.append(rest[heading.end() : end])
    else:
        tail_start = len(rest)
    if len(bodies) == 1:
        return text
    merged: dict[str, list[str]] = {}
    for body in bodies:
        for name, content in _categories(body):
            merged.setdefault(name, []).append(content)
    pieces = [
        f"\n### {name}\n\n" + "\n\n".join(parts) + "\n"
        for name, parts in merged.items()
    ]
    return head + marker + "\n" + "".join(pieces) + "\n" + rest[tail_start:]


def read_unreleased_since(path: Path, since: str) -> str:
    return unreleased_since(path.read_text(encoding="utf-8"), since)
