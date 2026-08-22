"""The region marker grammar and safe merge (design: RegionMerger).

This leaf module owns the fitdocs *region grammar*: the machine-recognizable
markers that delimit every content region a regeneration must not destroy
(Req 10.1-10.4, 11.3). It is pure mechanism and fully generic over region ids --
one algorithm, not one per region.

Policy lives elsewhere. *Which* ids a document reserves, which of them a user
owns and which the tool fills, and the exact text a freshly rendered region
carries are the document contract's business: see :mod:`fitdocs.contract`
(``PRESERVED_REGIONS``, ``USER_REGIONS``, ``TOOL_REGIONS``, the placeholders,
and ``LOAD_NOT_COMPUTED``). Nothing here reads that policy; callers pass ids in.

Grammar
-------
A region is delimited by a *begin* and an *end* marker, each an HTML comment on
its own line at column zero::

    <!-- fitdocs:begin:notes -->
    ...inner content, verbatim...
    <!-- fitdocs:end:notes -->

Both markers are invisible in rendered markdown and survive normal editing
(Req 10.1). Regions never nest, and each id appears at most once per document.
Markers are matched at the start of a line; an indented lookalike is not treated
as a marker (keeping the contract simple and predictable). Ids are matched
*exactly* -- ``notes`` never collides with ``notes2``.

Newline convention
------------------
``region_block(id, content)`` emits three newline-terminated lines: the begin
marker, then exactly one content block, then the end marker --
``f"{begin}\\n{content}\\n{end}\\n"``. Exactly one ``\\n`` separates the content
from each marker, and :func:`extract_regions` strips exactly that one separator
newline, so ``extract_regions(region_block(id, c))[id] == c`` for *any* ``c``
(including empty, multi-line, and trailing-newline content). This round-trip is
the contract the whole module is built to preserve.

Damage and conflict are loud
----------------------------
:func:`extract_regions` raises :class:`RegionError` on any structural damage --
a begin with no end, an end with no begin, a duplicated id, an out-of-order or
mismatched end, or a nested begin (Req 10.3). :func:`merge_regions` carries each
existing region's content verbatim into a fresh render and fully replaces the
generated content outside regions (Req 10.2, 10.4, 11.3); it raises
:class:`RegionError` when the existing document is damaged, or when it holds a
region the fresh render lacks -- silent content loss is forbidden.

This module is pure: it performs no file I/O and touches only ``re`` from the
standard library. It imports nothing else from the package -- not even the
contract whose ids it operates on -- so every layer is free to depend on it.
"""

from __future__ import annotations

import re
from typing import Final

# A marker occupies a whole line at column zero: an HTML comment naming the kind
# (begin/end) and the region id. The id is captured greedily up to " -->" and the
# line must end there, so ids are matched exactly (`notes` never matches `notes2`)
# and a marker never partially matches a longer token.
_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"^<!-- fitdocs:(?P<kind>begin|end):(?P<id>[A-Za-z0-9_-]+) -->$",
    re.MULTILINE,
)


class RegionError(Exception):
    """A document's region markers are damaged, or a merge would lose content.

    Raised for unbalanced, duplicated, out-of-order, mismatched, or nested
    markers (Req 10.3), and by :func:`merge_regions` when the existing document
    holds a region the fresh render lacks. The message names the offending region
    id and the structural problem so a user can restore the markers.
    """


def begin_marker(region_id: str) -> str:
    """The begin marker line's text: ``<!-- fitdocs:begin:<id> -->`` (no newline)."""
    return f"<!-- fitdocs:begin:{region_id} -->"


def end_marker(region_id: str) -> str:
    """The end marker line's text: ``<!-- fitdocs:end:<id> -->`` (no newline)."""
    return f"<!-- fitdocs:end:{region_id} -->"


def region_block(region_id: str, content: str) -> str:
    """Compose a region: begin-marker line, one content block, end-marker line.

    Layout is ``f"{begin}\\n{content}\\n{end}\\n"`` -- exactly one separator
    newline on each side of ``content`` -- so ``content`` (empty, multi-line, or
    trailing-newline) round-trips verbatim through :func:`extract_regions`.
    """
    return f"{begin_marker(region_id)}\n{content}\n{end_marker(region_id)}\n"


def extract_regions(markdown: str) -> dict[str, str]:
    """Map each region id to its inner content, verbatim, or raise on damage.

    Scans ``markdown`` for well-formed marker pairs and returns ``{id: content}``
    where ``content`` is the text between the begin and end marker lines, captured
    byte-for-byte (the single separator newline adjacent to each marker is
    stripped -- the inverse of :func:`region_block`). Any id with well-formed
    markers is extracted (the mechanism is generic; :func:`merge_regions` decides
    what a missing region means).

    Raises :class:`RegionError` on structural damage (Req 10.3): a begin with no
    matching end, an end with no open begin (including out-of-order or mismatched
    ends), a duplicated id, or a nested begin. The message names the region and
    the problem.
    """
    return {
        region_id: content for region_id, (content, _, _) in _scan(markdown).items()
    }


def merge_regions(fresh: str, existing: str) -> str:
    """Carry ``existing``'s region content into ``fresh``; raise on conflict.

    For every region ``fresh`` defines, its inner content is replaced with
    ``existing``'s content for the same id, verbatim -- preserving user-authored
    ``notes``/``workout`` and the training-load-filled ``load`` region identically
    (Req 10.2, 11.3). Everything outside regions comes from ``fresh``, so
    generated (non-editable) content is fully replaced (Req 10.4). A region in
    ``fresh`` but not in ``existing`` (a brand-new document, or a newly added
    region) keeps ``fresh``'s content -- that is not a conflict.

    Raises :class:`RegionError` (Req 10.3) when ``existing`` has damaged markers
    (the error propagates from extraction -- the conflict-on-damage path) or when
    ``existing`` holds a region id ``fresh`` does not, since dropping it would
    silently lose content.
    """
    fresh_spans = _scan(fresh)
    existing_regions = extract_regions(existing)

    # Any preserved region present in `existing` but absent from `fresh` would be
    # silently dropped by the splice below -- refuse instead of overwriting.
    missing = [
        region_id for region_id in existing_regions if region_id not in fresh_spans
    ]
    if missing:
        joined = ", ".join(sorted(missing))
        raise RegionError(
            f"the existing document contains region(s) [{joined}] that the "
            "freshly rendered document does not have; refusing to overwrite it, "
            "as regenerating would silently drop that content"
        )

    # Splice `existing` content into `fresh` in document order, keeping every byte
    # of `fresh` outside the replaced inner spans.
    parts: list[str] = []
    cursor = 0
    for region_id, (_, content_start, content_end) in fresh_spans.items():
        if region_id not in existing_regions:
            continue
        parts.append(fresh[cursor:content_start])
        parts.append(existing_regions[region_id])
        cursor = content_end
    parts.append(fresh[cursor:])
    return "".join(parts)


def _scan(markdown: str) -> dict[str, tuple[str, int, int]]:
    """Scan for region marker pairs, returning ``{id: (content, start, end)}``.

    ``content`` is the verbatim inner text; ``start``/``end`` are its slice bounds
    within ``markdown`` (used by :func:`merge_regions` to splice without touching
    surrounding bytes). Regions are returned in document order (dict insertion
    order). Raises :class:`RegionError` on any structural damage.
    """
    regions: dict[str, tuple[str, int, int]] = {}
    open_id: str | None = None
    open_end: int = 0  # index just past the open begin marker's line-ending newline

    for match in _MARKER_RE.finditer(markdown):
        kind = match.group("kind")
        region_id = match.group("id")
        if kind == "begin":
            if open_id is not None:
                raise RegionError(
                    f"region '{region_id}' begins before region '{open_id}' is "
                    f"closed; regions must not nest -- add the missing "
                    f"'{end_marker(open_id)}' or remove the stray begin marker"
                )
            if region_id in regions:
                raise RegionError(
                    f"region '{region_id}' is opened twice; each region id may "
                    "appear at most once per document -- remove the duplicate block"
                )
            open_id = region_id
            # `$` matches just before the newline, so match.end() indexes that
            # newline; inner content starts on the next line.
            open_end = match.end() + 1
        else:  # kind == "end"
            if open_id is None:
                raise RegionError(
                    f"end marker for region '{region_id}' has no matching begin "
                    f"marker before it -- add '{begin_marker(region_id)}' or "
                    "remove the stray end marker"
                )
            if region_id != open_id:
                raise RegionError(
                    f"end marker for region '{region_id}' does not match the open "
                    f"region '{open_id}' -- markers are out of order or crossed; "
                    f"expected '{end_marker(open_id)}'"
                )
            # The end marker starts at column zero, so the char before it is the
            # newline terminating the last content line; drop that one newline.
            content_end = match.start() - 1
            regions[region_id] = (markdown[open_end:content_end], open_end, content_end)
            open_id = None

    if open_id is not None:
        raise RegionError(
            f"region '{open_id}' has a begin marker with no matching end marker "
            f"-- add '{end_marker(open_id)}' to close it"
        )
    return regions
