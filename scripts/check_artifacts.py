"""Artifact conformance checker (design: ArtifactChecker).

Opens the release's one wheel and one source distribution, enumerates their
members, and reads their distribution metadata -- the source tree is never
consulted. Applies four checks and reports every violation it finds rather
than stopping at the first (task 2.2; the design's fifth and sixth checks --
the encumbered-content scan and the version-consistency check -- are added by
tasks 2.3 and 2.4):

* ``MISSING_REQUIRED`` -- a member `release/artifact-policy.toml` requires is
  absent from the artifact's regular files.
* ``FORBIDDEN_MEMBER`` -- a member (file or directory entry) matches a
  forbidden glob pattern, compared case-sensitively on every platform via
  `fnmatch.fnmatchcase` (plain `fnmatch.fnmatch` lower-cases on Windows only,
  which would let a differently-cased forbidden path through there alone).
* ``LINK_MEMBER`` -- a member is a symbolic or hard link, whatever its
  target: a link's bytes are its target path, so no later content scan can
  see through it, which is why this is reported unconditionally rather than
  folded into a content check.
* ``METADATA_INCOMPLETE`` -- a metadata field the policy requires is missing
  or empty (all values empty after `str.strip`), plus two checks the policy
  cannot express as a field list: `Requires-Dist` must be present at least
  once, and the message body (the long description) must be non-empty.

Invoked as ``python -m scripts.check_artifacts`` from the repository root.
Exit codes: ``0`` clean, ``1`` one or more violations found, ``2`` a hard
error (a missing or malformed policy file, or a dist directory that does not
contain exactly one wheel and one sdist). Writes nothing to disk; prints a
violation listing to stderr, or a one-line confirmation to stdout when clean.

This module is stdlib-only (`zipfile`, `tarfile`, `fnmatch`, `email`,
`dataclasses`, `enum`, `pathlib`, `argparse`, `sys`) plus
`scripts.artifact_policy`; it imports nothing from `fitdocs` and, for this
task, nothing from `tests` (task 2.3 adds exactly two such imports for the
encumbered-content gate).
"""

from __future__ import annotations

import argparse
import email
import email.message
import fnmatch
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from scripts.artifact_policy import (
    DEFAULT_POLICY_PATH,
    ArtifactPolicy,
    PolicyError,
    load_policy,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[1]


class ViolationKind(StrEnum):
    """The seven finding categories the checker can report.

    Values are the lowercased member names -- a `StrEnum` so a finding
    renders without a conversion step and sorts by its member value. Task
    2.2 implements the first, second, third, and sixth checks below; the
    fourth and fifth belong to task 2.3 (the encumbered-content gate) and
    the seventh to task 2.4 (the version-consistency gate). All seven are
    declared here, in the design's order, so later tasks add behavior
    without touching the enum's shape.
    """

    MISSING_REQUIRED = "missing_required"
    FORBIDDEN_MEMBER = "forbidden_member"
    LINK_MEMBER = "link_member"
    ENCUMBERED_CONTENT = "encumbered_content"
    GATE_NOT_RUN = "gate_not_run"
    METADATA_INCOMPLETE = "metadata_incomplete"
    VERSION_MISMATCH = "version_mismatch"


@dataclass(frozen=True, order=True)
class Violation:
    """One finding, in the project-wide `(subject, detail[, remedy])` shape.

    `subject` is the artifact filename (e.g. `fitdocs-0.1.0.tar.gz`), never
    a field called `artifact` -- kept as the leading field, and `order=True`
    on the dataclass, so a tuple of violations sorts deterministically by
    `(subject, kind, detail, remedy)` with no separate sort key to maintain.
    """

    subject: str
    kind: ViolationKind
    detail: str
    remedy: str


class CheckerError(RuntimeError):
    """A hard error unrelated to any single artifact's contents.

    Raised for a dist directory that does not contain exactly one wheel and
    one sdist, for an sdist whose members disagree about their top-level
    directory, or for an artifact missing the file the metadata check reads
    from. Never raised for a violation -- those are reported, not raised.
    """


@dataclass(frozen=True)
class _Member:
    """One archive member, in the checker's artifact-agnostic shape.

    `name` is the member's path with any sdist `fitdocs-<version>/` prefix
    already stripped, and with a trailing `/` preserved for directory
    entries (so a forbidden pattern like `tests/*` -- which fnmatch also
    matches against the bare `tests/` string, `*` matching zero characters
    -- can still catch a directory entry, not only the files under it).
    """

    name: str
    is_link: bool
    is_dir: bool
    is_regular: bool
    link_target: str = ""


def _find_artifacts(dist_dir: Path) -> tuple[Path, Path]:
    """Locate the dist directory's one wheel and one sdist.

    Anything other than exactly one of each -- zero, or two, of a kind --
    is a hard error, never a violation. `uv build`'s one-byte `.gitignore`
    in the output directory is not matched by either glob and is silently
    ignored, as task 2.1's note requires.
    """
    if not dist_dir.is_dir():
        raise CheckerError(f"dist directory {dist_dir} does not exist")

    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise CheckerError(
            f"expected exactly one wheel in {dist_dir}, found {len(wheels)}: "
            f"{[p.name for p in wheels]!r}"
        )
    if len(sdists) != 1:
        raise CheckerError(
            f"expected exactly one sdist in {dist_dir}, found {len(sdists)}: "
            f"{[p.name for p in sdists]!r}"
        )
    return wheels[0], sdists[0]


def _wheel_link_target(mode: int, zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    if mode == 0o120000:
        return zf.read(info).decode("utf-8", errors="replace")
    return ""


def _load_wheel(path: Path) -> tuple[tuple[_Member, ...], email.message.Message]:
    """Enumerate a wheel's members and parse its `*.dist-info/METADATA`."""
    members: list[_Member] = []
    metadata_bytes: bytes | None = None
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            is_dir = name.endswith("/")
            # S_IFLNK (0o120000) in the Unix mode bits packed into the
            # upper 16 bits of `external_attr`; zipfile carries no
            # link-detection helper of its own. A zip entry written without
            # Unix mode bits at all (`external_attr == 0`, the default for
            # `ZipFile.writestr` with a plain string name, and common for
            # archives produced by tools that never set them) yields
            # `mode == 0` here -- indistinguishable from S_IFREG for this
            # check's purposes, so such an entry is scanned as a regular
            # file, never flagged as a link. hatchling itself never writes
            # a symlink entry into a wheel: its wheel builder resolves each
            # added file with `os.stat` and reads and stores the target
            # file's own bytes (`hatchling/builders/wheel.py`'s
            # `WheelArchive.add_file`), so a real hatchling-built wheel
            # cannot carry a link member at all -- one can only reach a
            # wheel through a foreign archiving tool that writes Unix mode
            # bits directly (e.g. an infozip-style `zip -y`). The sdist is
            # the only hatchling-produced artifact that can carry a link,
            # which is why this checker's own tests plant links in both:
            # a wheel link is a foreign-tool scenario, not a hatchling one,
            # but the check still must not miss it if it happens.
            mode = (info.external_attr >> 16) & 0o170000
            is_link = mode == 0o120000
            is_regular = not is_dir and not is_link
            link_target = _wheel_link_target(mode, zf, info)
            members.append(
                _Member(
                    name=name,
                    is_link=is_link,
                    is_dir=is_dir,
                    is_regular=is_regular,
                    link_target=link_target,
                )
            )
            if is_regular and name.endswith(".dist-info/METADATA"):
                metadata_bytes = zf.read(info)

    if metadata_bytes is None:
        raise CheckerError(f"{path.name}: no '*.dist-info/METADATA' member found")

    metadata = email.message_from_string(metadata_bytes.decode("utf-8"))
    return tuple(members), metadata


def _sdist_top_dir(infos: list[tarfile.TarInfo], subject: str) -> str:
    if not infos:
        raise CheckerError(f"{subject}: sdist has no members")
    top = infos[0].name.split("/", 1)[0]
    for info in infos:
        if info.name != top and not info.name.startswith(top + "/"):
            raise CheckerError(
                f"{subject}: sdist members disagree on the top-level directory "
                f"(expected everything under {top!r}, found {info.name!r})"
            )
    return top


def _load_sdist(path: Path) -> tuple[tuple[_Member, ...], email.message.Message]:
    """Enumerate an sdist's members, with the `fitdocs-<version>/` top
    directory stripped, and parse its `PKG-INFO`.
    """
    members: list[_Member] = []
    pkg_info_bytes: bytes | None = None
    with tarfile.open(path, "r:gz") as tf:
        infos = tf.getmembers()
        top = _sdist_top_dir(infos, path.name)
        for info in infos:
            stripped = info.name[len(top) :].lstrip("/")
            if stripped == "":
                # The top-level directory entry itself; not a member of
                # the package tree the policy or forbidden patterns speak
                # about.
                continue
            is_dir = info.isdir()
            if is_dir and not stripped.endswith("/"):
                stripped += "/"
            is_link = info.issym() or info.islnk()
            is_regular = info.isfile()
            link_target = info.linkname if is_link else ""
            members.append(
                _Member(
                    name=stripped,
                    is_link=is_link,
                    is_dir=is_dir,
                    is_regular=is_regular,
                    link_target=link_target,
                )
            )
            if is_regular and stripped == "PKG-INFO":
                extracted = tf.extractfile(info)
                if extracted is None:
                    raise CheckerError(f"{path.name}: PKG-INFO member is unreadable")
                pkg_info_bytes = extracted.read()

    if pkg_info_bytes is None:
        raise CheckerError(f"{path.name}: no 'PKG-INFO' member found")

    metadata = email.message_from_string(pkg_info_bytes.decode("utf-8"))
    return tuple(members), metadata


def _check_missing_required(
    subject: str, members: tuple[_Member, ...], required: tuple[str, ...]
) -> list[Violation]:
    present = {m.name for m in members if m.is_regular}
    return [
        Violation(
            subject=subject,
            kind=ViolationKind.MISSING_REQUIRED,
            detail=f"required member {name!r} is absent",
            remedy="add it to the package data / sdist allowlist in pyproject.toml",
        )
        for name in required
        if name not in present
    ]


def _check_forbidden(
    subject: str, members: tuple[_Member, ...], patterns: tuple[str, ...]
) -> list[Violation]:
    violations: list[Violation] = []
    for member in members:
        # `fnmatchcase`, not `fnmatch`: the latter case-folds on Windows
        # only, which would let a differently-cased forbidden path through
        # there alone -- this checker must give the same answer everywhere.
        matched = next(
            (p for p in patterns if fnmatch.fnmatchcase(member.name, p)), None
        )
        if matched is not None:
            violations.append(
                Violation(
                    subject=subject,
                    kind=ViolationKind.FORBIDDEN_MEMBER,
                    detail=(
                        f"member {member.name!r} matches forbidden pattern {matched!r}"
                    ),
                    remedy=(
                        "exclude it via the sdist allowlist or the wheel's packaged "
                        "files in pyproject.toml"
                    ),
                )
            )
    return violations


def _check_links(subject: str, members: tuple[_Member, ...]) -> list[Violation]:
    return [
        Violation(
            subject=subject,
            kind=ViolationKind.LINK_MEMBER,
            detail=f"member {member.name!r} is a link to {member.link_target!r}",
            remedy=(
                "exclude it; a link's bytes are its target path and no content "
                "scan can see through it"
            ),
        )
        for member in members
        if member.is_link
    ]


def _check_metadata(
    subject: str,
    metadata: email.message.Message,
    required_fields: tuple[str, ...],
) -> list[Violation]:
    violations: list[Violation] = []
    for field in required_fields:
        values = metadata.get_all(field) or []
        if not any(value.strip() for value in values):
            violations.append(
                Violation(
                    subject=subject,
                    kind=ViolationKind.METADATA_INCOMPLETE,
                    detail=f"required metadata field {field!r} is missing or empty",
                    remedy="declare it under [project] in pyproject.toml",
                )
            )

    # The policy cannot express these two: `Requires-Dist` is a repeatable
    # header, not a single field, and the long description is the message
    # body, not a header at all.
    requires_dist = metadata.get_all("Requires-Dist") or []
    if not any(value.strip() for value in requires_dist):
        violations.append(
            Violation(
                subject=subject,
                kind=ViolationKind.METADATA_INCOMPLETE,
                detail="required metadata field 'Requires-Dist' is missing or empty",
                remedy="declare at least one runtime dependency in pyproject.toml",
            )
        )

    body = metadata.get_payload()
    if not isinstance(body, str):
        body = ""
    if not body.strip():
        violations.append(
            Violation(
                subject=subject,
                kind=ViolationKind.METADATA_INCOMPLETE,
                detail="long description (body) is missing or empty",
                remedy="ensure the README renders into the distribution metadata body",
            )
        )

    return violations


def check_artifacts(
    dist_dir: Path, *, policy: ArtifactPolicy, repo_root: Path
) -> tuple[Violation, ...]:
    """Run every implemented check over the dist directory's one artifact set.

    ``repo_root`` is accepted now, unused, so the signature matches the
    design's `check_artifacts` contract; the encumbered-content gate (task
    2.3) passes it to the purge's token core, which refuses match data that
    resolves inside it.

    Returns every violation found, sorted by `(subject, kind, detail)` --
    deterministic across repeated runs over the same artifacts.
    """
    del repo_root  # reserved for the encumbered-content gate (task 2.3)

    wheel_path, sdist_path = _find_artifacts(dist_dir)
    wheel_subject = wheel_path.name
    sdist_subject = sdist_path.name

    wheel_members, wheel_metadata = _load_wheel(wheel_path)
    sdist_members, sdist_metadata = _load_sdist(sdist_path)

    violations: list[Violation] = []
    violations += _check_missing_required(
        wheel_subject, wheel_members, policy.wheel_required
    )
    violations += _check_missing_required(
        sdist_subject, sdist_members, policy.sdist_required
    )
    violations += _check_forbidden(
        wheel_subject, wheel_members, policy.forbidden_members
    )
    violations += _check_forbidden(
        sdist_subject, sdist_members, policy.forbidden_members
    )
    violations += _check_links(wheel_subject, wheel_members)
    violations += _check_links(sdist_subject, sdist_members)
    violations += _check_metadata(
        wheel_subject, wheel_metadata, policy.required_metadata_fields
    )
    violations += _check_metadata(
        sdist_subject, sdist_metadata, policy.required_metadata_fields
    )

    return tuple(sorted(violations))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.check_artifacts",
        description=(
            "Decide, from the built artifacts alone, whether this release may "
            "be published."
        ),
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Directory holding the built wheel and sdist (default: dist)",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=DEFAULT_POLICY_PATH,
        help="Path to the release policy TOML file",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    policy_path = args.policy if args.policy.is_absolute() else REPO_ROOT / args.policy

    try:
        policy = load_policy(policy_path)
    except PolicyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        violations = check_artifacts(args.dist_dir, policy=policy, repo_root=REPO_ROOT)
    except CheckerError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not violations:
        wheel_path, sdist_path = _find_artifacts(args.dist_dir)
        print(f"clean: {wheel_path.name} {sdist_path.name}")
        return 0

    for violation in violations:
        print(
            f"{violation.kind}\t{violation.subject}\t{violation.detail}\t{violation.remedy}",
            file=sys.stderr,
        )
    print(f"{len(violations)} violation(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
