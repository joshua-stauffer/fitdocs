"""The ``post`` region grammar, post composition and the post digest
(publish-core Req 3.2-3.7, 4.7, 5.6, 6.1-6.5).

Pure: the region arrives as its inner text and the page's values as a
mapping, so nothing here reads a file, a clock or the network.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from fitdocs.publish.outcomes import PublishCode
from fitdocs.publish.request import Post
from fitdocs.publish.template import (
    MissingValue,
    TargetTemplates,
    TemplateSyntaxError,
    parse_template,
    render,
)
from fitdocs.publish.values import PLACEHOLDERS

_COMMENT: Final = re.compile(r"<!--.*?-->", re.DOTALL)
# Whitespace around any line terminator (\n \r \v \f \x85 U+2028 U+2029) folds
# to one space, so a title is one line whatever its literal text carries.
_TITLE_BREAK: Final = re.compile(r"\s*[\n\r\v\f\x85\u2028\u2029]\s*")


@dataclass(frozen=True)
class PostOverride:
    title: str  # template text
    description: str  # template text


@dataclass(frozen=True)
class Refusal:
    code: PublishCode  # POST_INVALID, TEMPLATE_INVALID, VALUE_MISSING, TITLE_EMPTY
    detail: str | None  # fitdocs-written: placeholder name, or "title, line 1, ..."


def read_post_region(content: str) -> PostOverride | Refusal | None:
    """Read a ``post`` region's inner text: no override, an override, or a refusal."""
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    text = _COMMENT.sub("", text)
    if "<!--" in text:
        return Refusal(
            PublishCode.POST_INVALID,
            "the post region has a hidden comment never closed",
        )
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    if len(lines) > 1 and lines[1].strip():
        return Refusal(
            PublishCode.POST_INVALID,
            "the line after the post title must be blank",
        )
    return PostOverride(lines[0].strip(), "\n".join(lines[2:]))


def override_templates(override: PostOverride) -> TargetTemplates | Refusal:
    """Parse an override's title then description as templates."""
    parsed = []
    for label, text in (
        ("title", override.title),
        ("description", override.description),
    ):
        try:
            parsed.append(parse_template(text, names=PLACEHOLDERS))
        except TemplateSyntaxError as exc:
            return Refusal(PublishCode.TEMPLATE_INVALID, f"{label}, {exc}")
    return TargetTemplates(parsed[0], parsed[1])


def compose_post(
    templates: TargetTemplates, values: Mapping[str, str | None]
) -> Post | Refusal:
    """Render a target's templates over a page's values."""
    title = render(templates.title, values)
    if isinstance(title, MissingValue):
        return Refusal(PublishCode.VALUE_MISSING, title.name)
    description = render(templates.description, values)
    if isinstance(description, MissingValue):
        return Refusal(PublishCode.VALUE_MISSING, description.name)
    title = _TITLE_BREAK.sub(" ", title).strip()
    if not title:
        return Refusal(PublishCode.TITLE_EMPTY, None)
    lines = description.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    return Post(title, "\n".join(lines).rstrip())


def post_digest(post: Post) -> str:
    """Lowercase hex SHA-256 over exactly the title and the description."""
    payload = json.dumps(
        [post.title, post.description], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
