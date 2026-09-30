"""Site gate (design: SiteGate; task 2.6; requirements 10.3, 10.4, 10.5).

Decides, from directory trees alone, whether a site may be published:
``python -m scripts.check_site ROOT [ROOT ...]``, run from the repository
root so that the ``tests`` package resolves.

Walks every given root and reports **all** findings, never stopping at the
first:

* ``LINK`` -- any symbolic link, whatever it points at. It is never followed
  and its target is never printed: a link's bytes are its target path, so no
  content scan could see through it.
* ``ENCUMBERED_CONTENT`` -- a regular file's content, decoded as UTF-8 with
  ``errors="replace"`` whatever its suffix, matches a forbidden-string token
  or a fingerprinted numeric value.
* ``ENCUMBERED_PATH`` -- an entry's root-relative path (file or directory)
  matches a forbidden-string token.
* ``UNREADABLE`` -- a file that cannot be read, a directory that cannot be
  listed, an entry that could not be examined (its type lookup failed), or an
  entry that is neither a file, directory nor link (opening a FIFO would
  block). Never a skip.
* ``GATE_NOT_RUN`` -- ``FITDOCS_FORBIDDEN_STRINGS`` is unset. Exactly one
  finding and nothing else: a run that could not scan has gated nothing.

Exit codes: ``0`` clean, ``1`` findings, ``2`` a hard error (a root that is
not a directory, or a match-data source that is set but unusable).

A finding names the entry and the KIND of match; it never contains matched
text, because workflow logs are public. That includes the entry's own path
when the path is what matched: such a subject is replaced by an ordinal, and
the same is done for every other finding on that entry.

Imports only the standard library and the purge's guard cores
(``tests._forbidden_strings``, ``tests._content_oracle``,
``tests._content_fingerprints``), the set ``scripts/check_artifacts.py`` uses;
it defines no marker list or fingerprint of its own. The fingerprint
constants are bound by name and read at call time, so a test can patch
``scripts.check_site.FINGERPRINTS``. The guard cores need the ``dev`` group
(``tests._forbidden_strings`` imports ``pytest``).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tests._content_fingerprints import FINGERPRINTS, SALT, WINDOW_LENGTHS
from tests._content_oracle import scan as oracle_scan
from tests._forbidden_strings import (
    ENV_VAR,
    ForbiddenStrings,
    ForbiddenStringsSourceError,
)
from tests._forbidden_strings import load as load_forbidden_strings
from tests._forbidden_strings import matches as forbidden_matches

REPO_ROOT: Path = Path(__file__).resolve().parents[1]


class FindingKind(StrEnum):
    ENCUMBERED_CONTENT = "encumbered_content"
    ENCUMBERED_PATH = "encumbered_path"
    LINK = "link"
    UNREADABLE = "unreadable"
    GATE_NOT_RUN = "gate_not_run"


@dataclass(frozen=True, order=True)
class Finding:
    """One finding, in the project-wide `(subject, detail[, remedy])` shape.

    `subject` is the entry's path under the root as given (or an ordinal
    placeholder when the path itself matched), or `""` for `GATE_NOT_RUN`.
    `detail` never contains matched text.
    """

    subject: str
    kind: FindingKind
    detail: str
    remedy: str


class SiteGateError(RuntimeError):
    """A hard error unrelated to any single entry: a root that is not a
    directory. Never raised for a finding."""


def _check_entry_content(
    subject: str, data: bytes, forbidden: ForbiddenStrings
) -> list[Finding]:
    text = data.decode("utf-8", errors="replace")
    findings: list[Finding] = []
    if forbidden_matches(text, forbidden):
        findings.append(
            Finding(
                subject=subject,
                kind=FindingKind.ENCUMBERED_CONTENT,
                detail=(
                    "content contains a forbidden-string token match -- see the "
                    f"{ENV_VAR} source for which value(s)"
                ),
                remedy="remove or reword the matched content",
            )
        )
    if oracle_scan(text, FINGERPRINTS, WINDOW_LENGTHS, SALT):
        findings.append(
            Finding(
                subject=subject,
                kind=FindingKind.ENCUMBERED_CONTENT,
                detail="content contains a fingerprinted value",
                remedy="remove or replace the matched numeric content",
            )
        )
    return findings


def _walk_root(root: Path, forbidden: ForbiddenStrings) -> list[Finding]:
    findings: list[Finding] = []
    ordinal = 0
    pending: list[tuple[Path, str]] = [(root, str(root))]
    while pending:
        directory, directory_subject = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            findings.append(
                Finding(
                    subject=directory_subject,
                    kind=FindingKind.UNREADABLE,
                    detail=f"directory could not be listed ({type(exc).__name__})",
                    remedy="make the directory listable or remove it",
                )
            )
            continue

        for entry in entries:
            ordinal += 1
            path = Path(entry.path)
            relative = path.relative_to(root)
            path_matched = bool(forbidden_matches(relative.as_posix(), forbidden))
            subject = (
                f"{root}{os.sep}<redacted path #{ordinal}>"
                if path_matched
                else str(path)
            )
            if path_matched:
                findings.append(
                    Finding(
                        subject=subject,
                        kind=FindingKind.ENCUMBERED_PATH,
                        detail="path contains a forbidden-string token match",
                        remedy="rename or remove the entry",
                    )
                )

            try:
                is_link = entry.is_symlink()
                is_dir = not is_link and entry.is_dir(follow_symlinks=False)
                is_file = (
                    not is_link and not is_dir and entry.is_file(follow_symlinks=False)
                )
            except OSError as exc:
                findings.append(
                    Finding(
                        subject=subject,
                        kind=FindingKind.UNREADABLE,
                        detail=f"entry could not be examined ({type(exc).__name__})",
                        remedy="make the entry examinable or remove it",
                    )
                )
                continue

            if is_link:
                findings.append(
                    Finding(
                        subject=subject,
                        kind=FindingKind.LINK,
                        detail="entry is a symbolic link (not followed)",
                        remedy="replace it with the file's own content or remove it",
                    )
                )
            elif is_dir:
                pending.append((path, subject))
            elif is_file:
                try:
                    data = path.read_bytes()
                except OSError as exc:
                    findings.append(
                        Finding(
                            subject=subject,
                            kind=FindingKind.UNREADABLE,
                            detail=f"file could not be read ({type(exc).__name__})",
                            remedy="make the file readable or remove it",
                        )
                    )
                else:
                    findings += _check_entry_content(subject, data, forbidden)
            else:
                findings.append(
                    Finding(
                        subject=subject,
                        kind=FindingKind.UNREADABLE,
                        detail="entry is not a regular file, directory or link",
                        remedy="remove it",
                    )
                )
    return findings


def check_trees(roots: Sequence[Path], *, repo_root: Path) -> tuple[Finding, ...]:
    """Walk every root and return all findings, sorted.

    Raises `SiteGateError` for a root that is not a directory, and lets
    `ForbiddenStringsSourceError` propagate for a set-but-unusable match-data
    source. An unset source is one `GATE_NOT_RUN` finding and no walk.
    """
    for root in roots:
        if not root.is_dir():
            raise SiteGateError(f"site root {root} is not a directory")

    forbidden = load_forbidden_strings(repo_root)
    if forbidden is None:
        return (
            Finding(
                subject="",
                kind=FindingKind.GATE_NOT_RUN,
                detail=f"{ENV_VAR} is unset; the encumbered-content gate did not run",
                remedy=(
                    f"set {ENV_VAR} to the out-of-repository match-data file and re-run"
                ),
            ),
        )

    findings: list[Finding] = []
    for root in roots:
        findings += _walk_root(root, forbidden)
    return tuple(sorted(findings))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.check_site",
        description=(
            "Decide, from directory trees alone, whether the site may be published."
        ),
    )
    parser.add_argument(
        "roots",
        nargs="+",
        type=Path,
        metavar="ROOT",
        help="A directory tree to scan; every root is scanned",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        findings = check_trees(args.roots, repo_root=REPO_ROOT)
    except (SiteGateError, ForbiddenStringsSourceError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not findings:
        print("clean: " + " ".join(str(root) for root in args.roots))
        return 0

    for finding in findings:
        print(
            f"{finding.kind}\t{finding.subject}\t{finding.detail}\t{finding.remedy}",
            file=sys.stderr,
        )
    print(f"{len(findings)} finding(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
