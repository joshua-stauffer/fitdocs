"""Builds the release's one artifact set from the working tree.

Invoked as ``python -m scripts.build_release`` from the repository root.
This script never ships in a built artifact -- the sdist allowlist in
`pyproject.toml` and `release/artifact-policy.toml`'s `[forbidden]` table
both exclude `scripts/*`.

There is no build profile, no prune list, and no per-release selection
between variants (design: "Amendment 2: no profiles"; Requirement 6.10).
One invocation always builds the working tree -- never a copy, never a
variant -- into both a wheel and a source distribution, through the
project's existing build front end (`uv build`) with no build hooks and no
code generation, so the artifact is exactly the tested revision
(Requirements 1.4, 10.2).

Determinism (Requirement 10.5): ``SOURCE_DATE_EPOCH`` is set in the child
process's environment for every build. hatchling honors this variable for
both wheel and sdist member modification times, so two builds of the same
revision with the same epoch produce archives with identical member sets
and identical member contents. When the caller supplies no
``--source-date-epoch``, this module falls back to a fixed constant
(``DEFAULT_SOURCE_DATE_EPOCH``, 1980-01-01T00:00:00Z) rather than the
current time, so an unparameterized build is still reproducible -- the ZIP
format's minimum representable timestamp is the natural floor.

This module is stdlib-only (`argparse`, `os`, `pathlib`, `shutil`,
`subprocess`, `sys`) and imports nothing from `fitdocs`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# The ZIP format's timestamp floor (1980-01-01T00:00:00Z). Used as the
# default SOURCE_DATE_EPOCH when the caller supplies none, so that an
# unparameterized build is still deterministic rather than time-of-day
# dependent.
DEFAULT_SOURCE_DATE_EPOCH = 315532800


class BuildError(RuntimeError):
    """The release build could not be produced."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_release",
        description=(
            "Build the release's one wheel and one source distribution from "
            "the working tree, into a cleared output directory."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("dist"),
        help="Directory to build into; cleared before the build (default: dist)",
    )
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=None,
        help=(
            "Unix timestamp used for archive member modification times; "
            f"defaults to the ZIP epoch floor ({DEFAULT_SOURCE_DATE_EPOCH})"
        ),
    )
    return parser


def _refuses_to_clear(out_dir: Path, repo_root: Path) -> bool:
    """True when clearing ``out_dir`` would remove ``repo_root`` too.

    Refuses when ``out_dir`` *is* the repository root or is any ancestor
    directory of it -- not only its immediate parent -- because clearing an
    ancestor directory removes everything beneath it, the repository root
    included.
    """
    return out_dir == repo_root or out_dir in repo_root.parents


def build(*, out_dir: Path, source_date_epoch: int | None) -> tuple[Path, ...]:
    """Build one wheel and one sdist from the working tree into ``out_dir``.

    ``out_dir`` is cleared (removed and recreated) before the build, so a
    re-run replaces rather than accumulates. A failed or malformed build
    leaves no partial artifact behind: ``out_dir`` is removed again before
    the error propagates.
    """
    resolved_out = out_dir.resolve()
    repo_root = REPO_ROOT.resolve()

    if _refuses_to_clear(resolved_out, repo_root):
        raise ValueError(
            f"refusing to clear {resolved_out}: it is the repository root "
            "or a directory that contains it"
        )

    if resolved_out.exists():
        shutil.rmtree(resolved_out)
    resolved_out.mkdir(parents=True, exist_ok=True)

    uv = shutil.which("uv")
    if uv is None:
        shutil.rmtree(resolved_out, ignore_errors=True)
        raise BuildError(
            "uv is required to build release artifacts but was not found on PATH"
        )

    epoch = (
        source_date_epoch
        if source_date_epoch is not None
        else DEFAULT_SOURCE_DATE_EPOCH
    )
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(epoch)

    result = subprocess.run(
        [uv, "build", "--sdist", "--wheel", "--out-dir", str(resolved_out)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        shutil.rmtree(resolved_out, ignore_errors=True)
        raise BuildError(f"`uv build` failed:\n{result.stdout}\n{result.stderr}")

    wheels = sorted(resolved_out.glob("*.whl"))
    sdists = sorted(resolved_out.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        shutil.rmtree(resolved_out, ignore_errors=True)
        raise BuildError(
            "expected exactly one wheel and one sdist, got "
            f"{len(wheels)} wheel(s) and {len(sdists)} sdist(s) in {resolved_out}"
        )

    return tuple(sorted(wheels + sdists))


def main(argv: Sequence[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        paths = build(out_dir=args.out_dir, source_date_epoch=args.source_date_epoch)
    except Exception as exc:  # noqa: BLE001 -- CLI boundary: any build failure is exit 1
        print(str(exc), file=sys.stderr)
        return 1

    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
