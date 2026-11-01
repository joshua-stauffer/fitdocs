"""The published region: render the links line and splice it into a page.

Publish-core task 5.2 (Req 3.8, 12.2, 12.4, 12.5). Links and labels are
checked with `fitdocs.publish.request.valid_link` / `valid_label` before they
reach this module; here they are only written. The splice replaces the inner
content of the `published` region and leaves every other byte of the page
unchanged, the `post` region included.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from fitdocs.contract import PUBLISHED_REGION
from fitdocs.docmerge import begin_marker, end_marker, extract_regions

PUBLISHED_PREFIX: Final[str] = "Published: "
LINK_SEPARATOR: Final[str] = " · "


class PublishedRegionMissing(Exception):
    """The page has no `published` region; it is reported, never given one."""


def published_content(links: Sequence[tuple[str, str, str]]) -> str:
    """The region's inner content from `(target, label, link)` records.

    Empty with no link; otherwise `Published: [label](link) · ...` ordered by
    target name.
    """
    if not links:
        return ""
    ordered = sorted(links, key=lambda record: record[0])
    parts = [f"[{label}]({link})" for _target, label, link in ordered]
    return PUBLISHED_PREFIX + LINK_SEPARATOR.join(parts)


def read_published(markdown: str) -> str | None:
    """The region's inner content, or None when absent.

    Raises `fitdocs.docmerge.RegionError` when any region's markers are damaged.
    """
    return extract_regions(markdown).get(PUBLISHED_REGION)


def replace_published(markdown: str, content: str) -> str:
    """Replace only the `published` region's inner content.

    Raises `RegionError` on damaged markers and `PublishedRegionMissing` when
    the page has no such region.
    """
    if PUBLISHED_REGION not in extract_regions(markdown):
        raise PublishedRegionMissing("the page has no published region to rewrite")
    begin = begin_marker(PUBLISHED_REGION)
    end = end_marker(PUBLISHED_REGION)
    pattern = re.compile(
        rf"^{re.escape(begin)}\n(?:.*?\n)?{re.escape(end)}$",
        re.MULTILINE | re.DOTALL,
    )
    replacement = f"{begin}\n{content}\n{end}"
    result, count = pattern.subn(lambda _match: replacement, markdown, count=1)
    if count != 1:  # unreachable while extract_regions and this pattern agree
        raise PublishedRegionMissing("could not locate the published region markers")
    return result
