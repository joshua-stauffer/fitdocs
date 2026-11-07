"""Decide a ``post`` region's state and write filled text (post-templates task 2.2).

Pure: the region arrives as its inner text and leaves as text. Requirements
4.6, 4.7, 5.1 to 5.4, 5.10 and 8.4.

The grammar of the provenance line and the waiting predicate live in
:mod:`fitdocs.contract`, which publish needs too; this module reuses them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from fitdocs.contract import POST_FILL_STAMP, is_waiting_post
from fitdocs.post_template.model import RegionState
from fitdocs.publish.request import Post

__all__ = ["FillStamp", "classify", "render_filled"]


@dataclass(frozen=True)
class FillStamp:
    template: str  # 64 lowercase hex, the template digest
    as_of: datetime  # naive local start
    text: str  # 64 lowercase hex, SHA-256 of the text below the comment


_LINE_END: Final = "\n"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _escape(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def _parse_stamp(line: str) -> FillStamp | None:
    """The stamp a line holds, or None when it is not one fitdocs could have written."""
    match = POST_FILL_STAMP.fullmatch(line)
    if match is None:
        return None
    try:
        as_of = datetime.fromisoformat(match["as_of"])
    except ValueError:
        return None
    return FillStamp(match["template"], as_of, match["text"])


def classify(content: str) -> tuple[RegionState, FillStamp | None]:
    """A region's state from its bytes, checked as waiting, filled, then the athlete's.

    The stamp is returned only for a Filled region.
    """
    if is_waiting_post(content):
        return RegionState.WAITING, None
    line, _, rest = content.partition(_LINE_END)
    stamp = _parse_stamp(line)
    if stamp is not None and _digest(rest) == stamp.text:
        return RegionState.FILLED, stamp
    return RegionState.ATHLETES, None


def render_filled(post: Post, *, template_digest: str, as_of: datetime) -> str:
    """The region content for ``post``: the stamp line, a newline, then the text.

    Every brace of the title and description is doubled so that the publish
    reader and template parser give the post back unchanged.
    """
    if as_of.tzinfo is not None:
        raise ValueError("as_of must be naive")
    text = _escape(post.title)
    if post.description:
        text += "\n\n" + _escape(post.description)
    precision = "microseconds" if as_of.microsecond else "seconds"
    stamp = (
        f"<!-- fitdocs:post-fill template={template_digest}"
        f" as_of={as_of.isoformat(timespec=precision)}"
        f" text={_digest(text)} -->"
    )
    return stamp + "\n" + text
