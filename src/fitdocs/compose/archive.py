"""Composing a page's listed archived files for a pass that holds only
`sources` (channel-merge Req 6.1-6.3, 7.2; design.md § ArchiveComposition).

The one module of the package that reads the filesystem.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fitdocs.compose.composer import compose_activity
from fitdocs.compose.types import Composition
from fitdocs.contract import sha_of_ref
from fitdocs.ingest import parse_fit
from fitdocs.layout import archive_path
from fitdocs.model import Activity


def compose_listed(data_root: Path, refs: Sequence[str], base: Activity) -> Composition:
    """Compose ``base`` with the other files ``refs`` lists.

    ``base`` is the activity the caller parsed from ``refs[-1]``. The extras
    are ``refs[:-1]`` in reverse order, so the ref just before the base ranks
    highest. A ref that is not an archive ref, repeats the base's or an earlier
    extra's content hash, or names a file that is not there is skipped. Every
    other ref is parsed; a read or decode error propagates to the caller.
    """
    seen = {base.provenance.sha256}
    extras: list[Activity] = []
    for ref in reversed(refs[:-1]):
        sha = sha_of_ref(ref)
        if sha is None or sha in seen:
            continue
        path = archive_path(data_root, sha)
        if not path.is_file():
            continue
        seen.add(sha)
        extras.append(parse_fit(path.read_bytes()))
    return compose_activity(base, extras)
