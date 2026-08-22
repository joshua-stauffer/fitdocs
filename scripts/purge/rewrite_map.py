"""One-shot extraction of the prior rewrite map's data rows (task 3.1, Req
9.7).

The prior rewrite map -- a single tracked file recording the SHA mapping
from an earlier, unrelated history rewrite -- does not survive this task:
Req 9.7's criterion 7 requires it gone from the working tree, and its rows
are one of the three columns the commit map joins in task 8.1. Before
deletion, its data rows -- `old_sha`, `new_sha`, `subject`, tab-separated --
are extracted to a scratch artifact outside the repository, exactly once,
here.

The file's leading ``#``-prefixed block is its prose header, and it is
**deliberately not extracted**: that header is where the maintainer's
personal email address lives (the from/to pair of the 2026-07-26
``--env-filter`` rewrite this map recorded). Everything this module reads
out is a data row -- an old commit id, a new commit id and a commit
subject line -- never a header line.

Holds no path and no destination: the caller decides where the extracted
rows land (outside the repository) and what the sibling metadata records,
the same separation `scripts/purge/fingerprints.py` keeps between its pure
collection functions and its file-writing callers.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def parse_data_rows(text: str) -> tuple[str, ...]:
    """Every data row in `text`, in file order, verbatim.

    A data row is any line that is neither blank nor `#`-prefixed. The
    source format (`## Naming convention` in tasks.md; the file's own
    header) states the header is `#`-prefixed prose ending immediately
    before the first data row, and that data rows are three tab-separated
    fields (`old_sha`, `new_sha`, `subject`) -- but this function does not
    itself validate the three-field shape; it only separates data rows from
    the header and blank lines, so a caller can inspect field structure
    independently if it needs to.
    """
    rows: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    return tuple(rows)


def write_extracted_rows(rows: Sequence[str], out_path: Path) -> None:
    """Write `rows` to `out_path`, one per line, in order.

    `out_path`'s parent directories are created if needed. An empty `rows`
    sequence writes an empty file rather than raising -- the caller is
    responsible for treating an unexpectedly empty extraction as an error,
    the same way `scripts/purge/fingerprints.py`'s `generate_and_verify`
    refuses to write a vacuous data module rather than silently doing so
    here.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(rows)
    if rows:
        content += "\n"
    out_path.write_text(content, encoding="utf-8")


def read_extracted_rows(path: Path) -> tuple[str, ...]:
    """Read back exactly what `write_extracted_rows` wrote: every non-empty
    line at `path`, in order.

    Exists so a caller can prove round-trip fidelity -- read back what was
    written and compare it, field-by-field and in order, against the rows
    that produced it -- rather than merely asserting the artifact exists.
    """
    text = path.read_text(encoding="utf-8")
    return tuple(line for line in text.splitlines() if line)
