"""The changelog text as a release-note pin should read it.

A test that pins "this entry is in the standing ``## [Unreleased]`` section"
must hold both before and after a release cut. The cut (docs/releasing.md
step 2) renames the section's content into the new ``## [X.Y.Z]`` heading and
leaves ``## [Unreleased]`` empty, so :func:`current_changelog` returns the
text with the newest released section's body standing in as the Unreleased
body -- but only while ``[Unreleased]`` holds no entry of its own. The moment
new work lands there, the pin reads ``[Unreleased]`` alone again and an entry
that sits under any released heading is no longer found.
"""

from __future__ import annotations

import re
from pathlib import Path

_UNRELEASED = "## [Unreleased]"
_RELEASE_HEADING = re.compile(r"(?m)^## \[\d+\.\d+\.\d+\][^\n]*\n")


def current_changelog(text: str) -> str:
    """`text`, with the newest released body in place of an empty Unreleased."""
    head, marker, rest = text.partition(_UNRELEASED)
    if not marker:
        return text
    following = re.search(r"(?m)^## \[", rest)
    unreleased_body = rest[: following.start()] if following else rest
    if re.search(r"(?m)^- ", unreleased_body):
        return text
    release = _RELEASE_HEADING.match(rest, following.start()) if following else None
    if release is None:
        return text
    return head + marker + "\n" + rest[release.end() :]


def read_current_changelog(path: Path) -> str:
    return current_changelog(path.read_text(encoding="utf-8"))
