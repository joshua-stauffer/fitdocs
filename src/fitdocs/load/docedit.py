"""Safe surgery on already-generated workout documents (design: LoadDocEditor).

This module edits a document workout-docs already wrote: it classifies the
reserved ``load`` region, replaces *only* that region's inner content, and
upserts the three managed frontmatter keys -- without ever re-serializing the
golden, workout-docs-emitted YAML (Req 7.1, 7.2, 7.4-7.6). It builds strictly
on ``fitdocs.docmerge``'s public region grammar and treats the document as the
store of record: the load payload lives in the region, the frontmatter keys are
a derived, restorable projection of it.

Two properties make the surgery trustworthy:

* **Byte-locality.** Region replacement rewrites only the bytes between the
  ``load`` markers; frontmatter upsert removes and re-appends only its own three
  managed lines inside the existing fence. Every other byte of the document --
  other regions, generated body, unmanaged frontmatter -- is preserved exactly.
* **Loud damage.** Region reads go through :func:`~fitdocs.docmerge.extract_regions`,
  so damaged markers raise :class:`~fitdocs.docmerge.RegionError`, which the
  engine treats as a per-document conflict. Structural problems this module
  itself detects (no ``load`` region, no frontmatter fence for an upsert) raise
  :class:`LoadDocError`.

Classification recognizes the workout-docs placeholder by importing the document
contract's ``LOAD_NOT_COMPUTED`` constant (single source of truth) and recognizes
the tool's own current-format results via :func:`~fitdocs.load.render.parse_payload`;
anything else is ``FOREIGN`` -- user-owned content the engine never overwrites
without an explicit recompute (Req 7.6). A payload written under a *prior*
result-format version is recognized without being decoded, via
:func:`~fitdocs.load.render.inspect_payload`: one stamped ``"computed"`` (or
whose status cannot be determined) is ``SUPERSEDED`` -- a result this tool can
no longer read, protected from automatic recomputation (Req 11.2, 11.3, 13.4) --
while one stamped ``"unsupported"`` classifies plain ``UNSUPPORTED``, because it
records no result and rejoins the compute path (Req 7.7).

**Everything this module knows about a document comes from
:mod:`fitdocs.contract`** (design: DocumentContract): the region id it edits
(:data:`~fitdocs.contract.LOAD_REGION`), the keys it manages
(:data:`~fitdocs.contract.LOAD_KEYS`), the placeholder it classifies against, the
frontmatter fence, and the frontmatter parse. None of them is spelled twice, so
the region this editor writes into is the region the renderer emits and the
regeneration merge preserves, and the keys it upserts are the keys the contract
publishes as managed (wiki-contract Req 1.1, 1.4, 6.2). :data:`LOAD_KEYS` is
re-exported here under its long-standing name :data:`FRONTMATTER_LOAD_KEYS` so
this module's public surface is unchanged by the consolidation.

Pure: no file I/O, no timestamps. Reads of frontmatter go through the contract's
read-only parser; writes are line-level string edits, never YAML re-emission.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from fitdocs.contract import (
    LOAD_KEYS,
    LOAD_NOT_COMPUTED,
    LOAD_REGION,
    frontmatter_close_index,
    parse_frontmatter,
)
from fitdocs.docmerge import (
    begin_marker,
    end_marker,
    extract_regions,
)
from fitdocs.load.render import (
    LOAD_PAYLOAD_VERSION,
    LoadPayload,
    PayloadStamp,
    inspect_payload,
    parse_payload,
)
from fitdocs.load.types import LoadResult

__all__ = [
    "FRONTMATTER_LOAD_KEYS",
    "LoadDocError",
    "RegionClassification",
    "RegionState",
    "apply_frontmatter_load",
    "classify_load_region",
    "read_frontmatter_load",
    "replace_load_region",
    "strip_frontmatter_load",
]


class LoadDocError(Exception):
    """A structural problem the doc editor itself detects.

    Raised when a document has no reserved ``load`` region (classification or
    replacement) or no leading frontmatter fence (upsert). Damaged region
    *markers* are workout-docs's grammar and surface as
    :class:`~fitdocs.docmerge.RegionError` instead -- this exception is for the
    editor's own preconditions.
    """


class RegionState(Enum):
    """How a document's ``load`` region content classifies (Req 7.5, 7.6)."""

    PLACEHOLDER = auto()
    """Content equals the workout-docs ``LOAD_NOT_COMPUTED`` placeholder."""
    COMPUTED = auto()
    """A recognized, current-format ``fitdocs-load`` payload, ``computed``."""
    UNSUPPORTED = auto()
    """An ``unsupported`` payload -- current format, or a prior format whose
    stamped status recorded no result (Req 7.7): nothing for 11.3 to protect,
    so it rejoins the compute path."""
    SUPERSEDED = auto()
    """A prior-format payload whose stamped status recorded a computed result
    (or could not be determined) -- a result this tool can no longer read, so
    it is protected from automatic recomputation (Req 11.2, 11.3, 13.4)."""
    FOREIGN = auto()
    """Anything else -- user-owned content, never overwritten without recompute."""


@dataclass(frozen=True)
class RegionClassification:
    """The result of classifying a document's ``load`` region content.

    ``payload`` and ``stamp`` are never both set. ``payload`` is populated only
    for a *current-format* ``COMPUTED``/``UNSUPPORTED`` region -- the ordinary
    case, where the full :class:`~fitdocs.load.render.LoadPayload` is already
    decoded. ``stamp`` is populated for ``SUPERSEDED``, and for an
    ``UNSUPPORTED`` region reached from a non-current payload whose stamped
    status was ``"unsupported"`` -- the old body is never decoded, only the
    state and the best-effort :class:`~fitdocs.load.render.PayloadStamp` are
    known. Both are ``None`` for ``PLACEHOLDER`` and ``FOREIGN``.
    """

    state: RegionState
    payload: LoadPayload | None
    stamp: PayloadStamp | None


FRONTMATTER_LOAD_KEYS: Final[tuple[str, ...]] = LOAD_KEYS
"""The three managed frontmatter keys this module upserts and strips (Req 7.2).

A re-export of :data:`fitdocs.contract.LOAD_KEYS` -- the *same tuple object*, not
a copy -- kept under this module's original name so existing importers are
unaffected. The definition moved to the contract because the question these keys
answer (are they fitdocs' or the user's?) is an ownership question, and the
answer has to be the same one the published managed-key set gives (Req 6.2).
"""


# --- region classification & replacement ------------------------------------


def classify_load_region(markdown: str) -> RegionClassification:
    """Classify the document's ``load`` region content (Req 7.5, 7.6, 7.7, 11.2,
    11.3, 13.4).

    Extracts regions (a :class:`~fitdocs.docmerge.RegionError` from damaged
    markers propagates as a per-document conflict) and inspects the ``load``
    region's inner content against this table:

    | Marker version | Stamped status | State | Rationale |
    | --- | --- | --- | --- |
    | current | decodes | COMPUTED / UNSUPPORTED | ordinary |
    | current | body invalid | FOREIGN | corrupted own format (7.6) |
    | non-current | ``"computed"`` | SUPERSEDED | a result to protect (11.2-13.4) |
    | non-current | ``"unsupported"`` | UNSUPPORTED | no result to protect (7.7) |
    | non-current | undeterminable | SUPERSEDED | protective default |

    Content equal to the imported ``LOAD_NOT_COMPUTED`` placeholder yields
    ``PLACEHOLDER``; content with no payload-comment line at all (including one
    whose body fails even :func:`~fitdocs.load.render.inspect_payload`'s
    permissive match, e.g. an empty body) yields ``FOREIGN``. Both carry no
    payload and no stamp. A non-current ``UNSUPPORTED`` region rejoins the
    compute path on the next pass -- a no-op-equivalent diff while the sport
    stays unsupported, and a real fill once a calculator lands (Req 7.7) --
    without ever decoding the old body; only its :class:`PayloadStamp` is kept.
    Raises :class:`LoadDocError` when the document has no ``load`` region.
    """
    content = _load_region_content(markdown)
    payload = parse_payload(content)
    if payload is not None:
        state = (
            RegionState.COMPUTED
            if payload.status == "computed"
            else (RegionState.UNSUPPORTED)
        )
        return RegionClassification(state, payload, None)
    if content == LOAD_NOT_COMPUTED:
        return RegionClassification(RegionState.PLACEHOLDER, None, None)
    stamp = inspect_payload(content)
    if stamp is None:
        return RegionClassification(RegionState.FOREIGN, None, None)
    if stamp.version == LOAD_PAYLOAD_VERSION:
        # A current-format marker whose body parse_payload rejected: corrupted
        # own-format content, never silently overwritten (Req 7.6).
        return RegionClassification(RegionState.FOREIGN, None, None)
    if stamp.status == "unsupported":
        # No result to protect -- rejoin the compute path (Req 7.7).
        return RegionClassification(RegionState.UNSUPPORTED, None, stamp)
    # stamp.status is "computed" (a result to protect) or undeterminable (the
    # protective default): both classify SUPERSEDED (Req 11.2, 11.3, 13.4).
    return RegionClassification(RegionState.SUPERSEDED, None, stamp)


def replace_load_region(markdown: str, content: str) -> str:
    """Replace only the ``load`` region's inner content, byte-preserving all else.

    Every other byte of ``markdown`` -- frontmatter, other regions, generated
    body, and the newlines adjacent to the markers -- is preserved exactly; only
    the text between the ``load`` begin/end markers becomes ``content``. Built on
    docmerge's public marker grammar: a :class:`~fitdocs.docmerge.RegionError`
    from damaged markers propagates, and a document without a ``load`` region
    raises :class:`LoadDocError`. Invariant:
    ``extract_regions(replace_load_region(md, c))["load"] == c``.
    """
    # extract_regions both validates the grammar (RegionError propagates) and
    # confirms the load region exists before we splice.
    if LOAD_REGION not in extract_regions(markdown):
        raise LoadDocError(
            "document has no reserved 'load' region to replace -- expected "
            f"'{begin_marker(LOAD_REGION)}' ... '{end_marker(LOAD_REGION)}'"
        )

    begin = begin_marker(LOAD_REGION)
    end = end_marker(LOAD_REGION)
    # ^begin\n{inner}\n{end}$ with the markers anchored to column zero (MULTILINE)
    # and DOTALL so {inner} may span lines; non-greedy stops at the first end
    # marker. The trailing newline after the end marker line is outside the match
    # and therefore preserved verbatim.
    pattern = re.compile(
        rf"^{re.escape(begin)}\n.*?\n{re.escape(end)}$",
        re.MULTILINE | re.DOTALL,
    )
    replacement = f"{begin}\n{content}\n{end}"
    # A function replacement avoids re-interpreting backslashes/group refs in
    # ``content``.
    new_markdown, count = pattern.subn(lambda _match: replacement, markdown, count=1)
    if count != 1:  # pragma: no cover - extract_regions already guaranteed a match
        raise LoadDocError("could not locate the 'load' region markers to replace")
    return new_markdown


def _load_region_content(markdown: str) -> str:
    """Return the ``load`` region's inner content, or raise :class:`LoadDocError`.

    A :class:`~fitdocs.docmerge.RegionError` from damaged markers propagates.
    """
    regions = extract_regions(markdown)
    try:
        return regions[LOAD_REGION]
    except KeyError:
        raise LoadDocError(
            "document has no reserved 'load' region -- expected "
            f"'{begin_marker(LOAD_REGION)}' ... '{end_marker(LOAD_REGION)}'"
        ) from None


# --- frontmatter load keys --------------------------------------------------


def apply_frontmatter_load(markdown: str, result: LoadResult) -> str:
    """Upsert the managed load keys inside the frontmatter by line-level edit.

    Removes any existing ``load_value``/``load_methodology``/``load_basis``
    lines and appends fresh ones just before the closing ``---`` -- the
    workout-docs YAML is never re-serialized, so its bytes never drift (Req
    7.2). Values come from ``result``: ``load_value`` as a numeric scalar (one
    decimal, trailing ``.0`` dropped) sourced from ``result.value``,
    ``load_methodology`` as ``result.calculator_id`` (Req 10.6), and
    ``load_basis`` as ``result.basis``. ``load_basis`` is emitted
    unconditionally -- ``result.basis`` is always present, so unlike the old
    ``load_zone`` key this replaces, the third key is never conditionally
    omitted. No diagnostic (``non_selected``, ``flags``) has a frontmatter
    projection at all. Idempotent; every non-managed frontmatter line and the
    entire body are preserved exactly. Raises :class:`LoadDocError` when there
    is no leading frontmatter fence.
    """
    lines = markdown.split("\n")
    close = frontmatter_close_index(lines)
    if close is None:
        raise LoadDocError(
            "document has no leading '---' frontmatter block to hold load keys"
        )
    kept = [line for line in lines[1:close] if not _is_managed_line(line)]
    managed = _managed_lines(result)
    new_lines = [lines[0], *kept, *managed, *lines[close:]]
    return "\n".join(new_lines)


def read_frontmatter_load(markdown: str) -> Mapping[str, object]:
    """Read the managed load keys from the frontmatter (drift detection, 7.4).

    Reads the leading frontmatter through
    :func:`fitdocs.contract.parse_frontmatter` (read-only) and returns the subset
    of :data:`FRONTMATTER_LOAD_KEYS` present, mapping each to its parsed value
    (``load_value`` as a number, the rest as strings). Returns ``{}`` when there
    is no frontmatter block, it fails to parse, it is not a mapping, or none of
    the managed keys are present. Never writes.

    The parse is the contract's rather than this module's own so that "what this
    document's frontmatter says" has one answer across the whole tool: a block
    the sync scan reads is a block drift detection reads, with no edge where the
    two disagree (Req 1.1, 1.2).
    """
    parsed = parse_frontmatter(markdown)
    if parsed is None:
        return {}
    return {key: parsed[key] for key in FRONTMATTER_LOAD_KEYS if key in parsed}


def strip_frontmatter_load(markdown: str) -> str:
    """Remove the managed load key lines, preserving every other byte (7.5/8.3).

    Deletes any ``load_value``/``load_methodology``/``load_basis`` lines from the
    leading frontmatter block and leaves the rest of the document byte-identical.
    Idempotent: stripping a document with no managed keys (or no frontmatter
    block) is a no-op that returns the input unchanged.
    """
    lines = markdown.split("\n")
    close = frontmatter_close_index(lines)
    if close is None:
        return markdown
    kept = [line for line in lines[1:close] if not _is_managed_line(line)]
    new_lines = [lines[0], *kept, *lines[close:]]
    return "\n".join(new_lines)


# --- frontmatter helpers ----------------------------------------------------


def _is_managed_line(line: str) -> bool:
    """Whether ``line`` is one of this module's managed top-level key lines.

    Only column-zero ``key: ...`` lines whose key is in
    :data:`FRONTMATTER_LOAD_KEYS` match; indented lines (which cannot be a
    top-level managed key) and keyless lines never do.
    """
    if not line or line[0].isspace():
        return False
    key, sep, _ = line.partition(":")
    return sep == ":" and key.strip() in FRONTMATTER_LOAD_KEYS


def _managed_lines(result: LoadResult) -> list[str]:
    """The fresh managed frontmatter lines for ``result`` (Req 7.2, 10.6).

    ``load_basis`` is emitted unconditionally from ``result.basis``, which is
    always present -- unlike the old ``load_zone`` key this replaces, the third
    line is never conditionally omitted. No diagnostic (``non_selected``,
    ``flags``) is projected here at all.
    """
    return [
        f"load_value: {_format_value(result.value)}",
        f"load_methodology: {_yaml_scalar(result.calculator_id)}",
        f"load_basis: {_yaml_scalar(result.basis)}",
    ]


def _format_value(value: float) -> str:
    """Format ``value`` like the region headline: one decimal, drop ``.0``.

    ``1700.0 -> "1700"`` (parses back as ``int``), ``2473.2 -> "2473.2"``
    (parses back as ``float``) -- a numeric YAML scalar in both cases.
    """
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


_SAFE_PLAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9 ()_./+%-]*$"
)
"""A conservative set of values safe to emit as a bare YAML plain scalar."""

_YAML_RESERVED: Final[frozenset[str]] = frozenset(
    {"true", "false", "null", "yes", "no", "on", "off", "none", "~"}
)
"""Words a YAML reader would coerce to a bool/null if left unquoted."""


def _yaml_scalar(value: str) -> str:
    """Emit ``value`` as a YAML scalar, quoting defensively when needed.

    Safe, unambiguous values (identifiers, calculator ids like
    ``stub-computing``) are emitted plain; anything that could
    confuse a YAML reader -- reserved words, number-like text, or characters
    outside the safe set -- is double-quoted via ``json.dumps`` (a valid YAML
    double-quoted flow scalar), so it always parses back to the same string.
    """
    if (
        _SAFE_PLAIN_RE.match(value)
        and value.lower() not in _YAML_RESERVED
        and not _looks_numeric(value)
    ):
        return value
    return json.dumps(value, ensure_ascii=False)


def _looks_numeric(value: str) -> bool:
    """Whether ``value`` would be read as a number if emitted unquoted."""
    try:
        float(value)
    except ValueError:
        return False
    return True
