"""Digest the exact history and plan engine inputs through index snapshots.

History's ``scan_documents`` (``src/fitdocs/history/documents.py:197-200``)
and the plan corpus's ``scan_corpus`` (``src/fitdocs/plans/corpus.py:184-187``)
scan ``sorted(workouts/*.md)`` through ``docio.read_frontmatter`` and retain
workout documents, as defined by ``is_workout_document``
(``src/fitdocs/contract.py:976-986``). The index's
``scan_workout_pages`` reads the same glob, applies the same predicate, and
captures each accepted document's path and byte fingerprint
(``src/fitdocs/index/corpus.py:55-88``). It uses ``docio.read_document``
(``src/fitdocs/docio.py:103-117``), while ``read_frontmatter`` delegates to that
same read (``src/fitdocs/docio.py:75-91``). ``corpus_snapshot`` places every
accepted workout exactly once in ``pages`` or ``left_out``
(``src/fitdocs/index/corpus.py:91-120``). Therefore the combined snapshot
collections cover the workout-page inputs without rescanning the filesystem;
a file excluded from both collections is not retained as a workout input by
either engine. A page entering or leaving the accepted set adds or removes its
fingerprint.

Held status does not belong in the workout digest: both engines read all
accepted pages. ``page_keys`` separately reflects the index-held subset for
block-table fingerprints.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from fitdocs.index.producer import CorpusSnapshot
from fitdocs.layout import settings_path


def file_digest(path: Path) -> str:
    """Return an exact byte digest or a stable marker without raising."""
    try:
        path.lstat()
        if path.is_symlink():
            return f"symlink:{os.readlink(path)}"
        if path.is_dir():
            return "directory"
        content = path.read_bytes()
    except FileNotFoundError:
        return "absent"
    except Exception as exc:
        return f"unreadable:{type(exc).__name__}"
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def workouts_digest(corpus: CorpusSnapshot) -> str:
    entries = [(page.path, page.document_fingerprint) for page in corpus.pages]
    entries.extend((page.path, page.document_fingerprint) for page in corpus.left_out)
    entries.sort(key=lambda entry: entry[0])
    return digest({"workouts": entries})


def settings_digest(data_root: Path) -> str:
    return file_digest(settings_path(data_root))


def digest(parts: Mapping[str, str | None | Sequence[Sequence[str]]]) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def page_keys(corpus: CorpusSnapshot) -> Mapping[str, str]:
    return {page.path: page.page_key for page in corpus.pages}
