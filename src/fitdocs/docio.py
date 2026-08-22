"""The one filesystem read shared by every ``workouts/*.md`` scanner (design:
DocumentContract, wiki-contract task 7.2).

:func:`fitdocs.contract.parse_frontmatter` is a pure leaf that never touches
the filesystem (its own module docstring states this as an invariant every
module in the package may rely on), so *something* above it has to actually
open the file. Before this module existed, that "something" was written out
**twice**, byte-for-byte identically, in :mod:`fitdocs.sync` (behind
:func:`~fitdocs.sync.find_document` and :func:`~fitdocs.sync._discover_documents`)
and in :mod:`fitdocs.load.engine` (behind
:func:`~fitdocs.load.engine._discover_workout_docs`) -- and a review round
caught that the second copy had silently fallen behind the first, missing the
symlink refusal the first had already grown. Collapsing both into this one
function is what makes a *third* divergence structurally impossible: there is
now exactly one place this read can drift from the audit's read of the same
kind of path (:func:`fitdocs.audit._read_document`).

Why the refusal lives here, at the read, rather than at each write site
------------------------------------------------------------------------
``read_text``/``write_text`` both follow a symlink, and the two writers this
read feeds would misbehave in two *different* ways if a discovery path ever
matched one: the sync engine's document rewrite
(:func:`fitdocs.sync._write_outputs`, via plain ``Path.write_text``) would
write straight through the link, silently overwriting whatever file sits at
the far end -- quite possibly outside the data root entirely (wiki-contract
Req 7.5, 7.6); the training-load pass's atomic temp-file-then-``os.replace``
swap (:func:`fitdocs.load.engine._atomic_write`) does not follow the link at
all -- ``os.replace`` onto a symlink destination replaces the link itself,
leaving the far-end file untouched but destroying the user's symlink in place
of leaving it alone. Neither outcome is acceptable, and refusing the symlink
here, at the one read every discovery path shares, prevents both: it is never
matched by :func:`~fitdocs.sync.find_document`, never enumerated by
:func:`~fitdocs.sync._discover_documents`, and never scanned by
:func:`~fitdocs.load.engine.apply_load`, so neither write site downstream ever
gets the chance to reach it. (Nothing about this changes if a future writer
uses a different write primitive: the point of refusing at the read is that
it does not matter which write primitive a caller uses.)

This module performs I/O and is therefore **not** a pure leaf like
:mod:`fitdocs.contract` -- it is the thin wrapper the contract's own docstring
anticipates ("reading a document is this engine's job while interpreting it is
the contract's"), just no longer duplicated once per engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fitdocs.contract import parse_frontmatter

__all__ = [
    "REMEDY_REPLACE_SYMLINK",
    "SYMLINK_DETAIL",
    "read_frontmatter",
]

SYMLINK_DETAIL: Final[str] = "this path is a symlink and is not followed"
"""The observed-detail half of the symlink refusal this module enforces.

Named once, here, so every caller that reports on a refused symlink --
:mod:`fitdocs.audit`'s finding and :mod:`fitdocs.sync`'s
:class:`~fitdocs.sync.DocWarning` -- describes the same path with the exact
same sentence, rather than each inventing (and independently drifting from)
its own wording."""

REMEDY_REPLACE_SYMLINK: Final[str] = (
    "replace the symlink with the document itself, or remove it"
)
"""The remedy half of the symlink refusal, shared for the same reason as
:data:`SYMLINK_DETAIL`."""


def read_frontmatter(path: Path) -> dict[str, object] | None:
    """Read a file and parse its leading frontmatter, or ``None`` if unusable.

    A symlink at ``path`` is refused unconditionally, before any read is
    attempted -- see the module docstring for why this is the one place that
    refusal belongs. It is treated exactly like any other unreadable or
    undecodable file: simply not a fitdocs document this scan recognizes, with
    no exception raised.

    Never raises, on either half. An unreadable or undecodable file yields
    ``None`` here; a missing or unterminated ``---`` fence, YAML that fails to
    parse, or a non-mapping block yields ``None`` from
    :func:`fitdocs.contract.parse_frontmatter` (Req 1.2). In every case the
    caller simply skips the file and the scan continues.
    """
    if path.is_symlink():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_frontmatter(text)
