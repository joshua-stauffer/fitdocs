"""The plain values crossing into and out of a publish target, and the one
link rule and one label rule (publish-core Req 9.3, 9.4, 12.3).

Imports only the standard library and the vocabulary, so no target, page or
credential code can ride in on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from fitdocs.publish.outcomes import PublishCode

MAX_LINK_LENGTH: Final[int] = 2048
MAX_LABEL_LENGTH: Final[int] = 64

_LINK_REFUSED: Final[frozenset[str]] = frozenset('<>()[]"`\\')


@dataclass(frozen=True)
class Post:
    title: str  # one line, non-empty
    description: str  # newline-separated, may be empty


@dataclass(frozen=True)
class CompletedActivity:
    """The completed activity a workout page records."""

    sport: str  # the page's recorded sport, verbatim ("Run")
    start: datetime  # aware, at the offset the device recorded
    elapsed_s: float | None  # base file's session elapsed time, else None
    distance_m: float | None  # base file's session distance, else None
    source_shas: tuple[str, ...]  # archived files' sha256, ascending rank, base last
    base_fit: Path | None  # fit-archive/<base sha>.fit when it is a file


@dataclass(frozen=True)
class PublishRequest:
    publication_id: str  # 32 lowercase hex characters
    post: Post
    subject: CompletedActivity  # the only subject kind in this version
    recorded_link: str | None  # the link recorded for this page and target, if any


@dataclass(frozen=True)
class PublishResult:
    code: PublishCode
    link: str | None = None


# Brackets end a markdown link text; U+2028/U+2029 are line separators that a
# markdown renderer may treat as a line break inside the one-line region.
_LABEL_REFUSED = frozenset("[]\u2028\u2029")


def _is_control(char: str) -> bool:
    point = ord(char)
    return point < 0x20 or 0x7F <= point <= 0x9F


def valid_link(link: object) -> bool:
    """An https link with a host, bounded, free of anything that breaks markdown."""
    if not isinstance(link, str) or len(link) > MAX_LINK_LENGTH:
        return False
    if not link.startswith("https://"):
        return False
    for char in link:
        if char.isspace() or _is_control(char) or char in _LINK_REFUSED:
            return False
    try:
        host = urlsplit(link).hostname
    except ValueError:
        return False
    return bool(host)


def valid_label(label: object) -> bool:
    """A non-empty, bounded label: no control character, bracket or line separator."""
    if not isinstance(label, str):
        return False
    if not 0 < len(label) <= MAX_LABEL_LENGTH:
        return False
    return not any(_is_control(c) or c in _LABEL_REFUSED for c in label)
