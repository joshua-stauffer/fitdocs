"""The shared document I/O: the one filesystem read every ``workouts/*.md``
scanner uses, and :func:`write_bytes_if_changed`, the atomic write-only-if-
changed for chart assets.

The read (design: DocumentContract, wiki-contract task 7.2).

:func:`fitdocs.contract.parse_frontmatter` is a pure leaf that never touches
the filesystem (its own module docstring states this as an invariant every
module in the package may rely on), so *something* above it has to actually
open the file. Before this module existed, that "something" was written out
**twice**, byte-for-byte identically, in :mod:`fitdocs.sync` (behind
:func:`~fitdocs.sync.find_document` and a per-regeneration document discovery)
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
:func:`~fitdocs.identity.pages.scan_pages`, and never scanned by
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

import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.contract import frontmatter_block_error, parse_frontmatter

__all__ = [
    "REMEDY_REPLACE_SYMLINK",
    "SYMLINK_DETAIL",
    "read_frontmatter",
    "read_frontmatter_diagnosed",
    "write_bytes_if_changed",
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
    document = read_document(path)
    return None if document is None else document.frontmatter


def read_frontmatter_diagnosed(
    path: Path,
) -> tuple[dict[str, object] | None, str | None]:
    """:func:`read_frontmatter`, plus *why* when the file is unreadable.

    Returns ``(frontmatter, reason)``. ``reason`` is a one-line description
    exactly when ``path`` is something the athlete evidently meant as a
    document but that cannot be read as one: an OS or decode failure, or a
    closed leading ``---`` block whose YAML cannot be parsed or constructed
    (for example ``date: 2026-02-30``). It is ``None`` for a file that is
    simply not a fitdocs document -- a symlink (refused unread, as in
    :func:`read_frontmatter`), a directory, no leading fence, or a block that
    parses to something other than a mapping -- so a caller can report the
    first kind without also reporting ``workouts/AGENTS.md``. A readable
    mapping returns ``(frontmatter, None)``. Never raises;
    :func:`read_frontmatter`'s contract is untouched.
    """
    if path.is_symlink() or path.is_dir():
        return None, None
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None, "the file is not valid UTF-8 text"
    except OSError as exc:
        return None, f"the file could not be read: {exc.strerror or exc}"
    frontmatter = parse_frontmatter(text)
    if frontmatter is not None:
        return frontmatter, None
    error = frontmatter_block_error(text)
    return None, None if error is None else _block_reason(error)


def _block_reason(detail: str) -> str:
    first_line = (detail.strip().splitlines() or ["unparseable YAML"])[0]
    return f"the frontmatter block could not be parsed: {first_line}"


@dataclass(frozen=True)
class DocumentRead:
    """The original document bytes, decoded text and parsed frontmatter."""

    data: bytes
    text: str
    frontmatter: dict[str, object] | None


def read_document(path: Path) -> DocumentRead | None:
    """Read a document once, returning its bytes and interpretations, or None.

    The symlink refusal is shared with :func:`read_frontmatter`. Unreadable or
    undecodable files yield ``None``; malformed or absent frontmatter is kept
    as a document with ``frontmatter=None``. This function never raises.
    """
    if path.is_symlink():
        return None
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return DocumentRead(data, text, parse_frontmatter(text))


def write_bytes_if_changed(path: Path, data: bytes) -> bool:
    """Write ``data`` to ``path`` unless a regular file there already holds it.

    Returns ``True`` if written. An identical regular file is left untouched
    (content and modification time). Otherwise the bytes go to a hidden temp
    file in ``path.parent`` (``.{name}.<random>.tmp``), are flushed and
    fsynced, and :func:`os.replace` swaps it onto ``path``, so a reader sees
    the previous complete bytes or ``data``, never a partial file. The temp
    file is removed on any failure. A symlink at ``path`` is never read or
    written through: it is replaced by the new regular file. A read error
    while comparing counts as "differs".
    """
    try:
        # lstat, so a symlink is never "regular"; only a regular file is read.
        if stat.S_ISREG(os.lstat(path).st_mode) and path.read_bytes() == data:
            return False
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    # O_EXCL creation at the default 0o666 & ~umask, like Path.write_bytes
    # (mkstemp would force 0o600).
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True
