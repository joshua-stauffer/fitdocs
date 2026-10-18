"""Read and splice the refreshed morning region."""

import re

from fitdocs.contract import MORNING_REGION
from fitdocs.docmerge import begin_marker, end_marker, extract_regions


class MorningRegionMissing(Exception):
    """The document has no morning region to replace."""


def read_morning(markdown: str) -> str | None:
    """Read the morning content, propagating damage in any region's markers."""
    return extract_regions(markdown).get(MORNING_REGION)


def replace_morning(markdown: str, content: str) -> str:
    """Replace the morning content while preserving the surrounding document."""
    if MORNING_REGION not in extract_regions(markdown):
        raise MorningRegionMissing("document has no morning region to replace")

    begin = begin_marker(MORNING_REGION)
    end = end_marker(MORNING_REGION)
    pattern = re.compile(
        rf"^{re.escape(begin)}\n.*?\n{re.escape(end)}$",
        re.MULTILINE | re.DOTALL,
    )
    replacement = f"{begin}\n{content}\n{end}"
    new_markdown, count = pattern.subn(lambda _match: replacement, markdown, count=1)
    if count != 1:  # pragma: no cover - extract_regions guaranteed a match
        raise MorningRegionMissing("could not locate the morning region markers")
    return new_markdown
