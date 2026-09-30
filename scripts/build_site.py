"""The website build command (design: BuildSiteCli; task 3.5).

``python -m scripts.build_site build | serve | status``, run from anywhere:
relative paths, and a relative ``FITDOCS_SITE_CONTENT``, are read from the
repository root and never from the working directory.

Exit codes: ``0`` success, ``1`` the input has problems (one rendered line
each on stderr, the generator output after them with ``--verbose``), ``2`` the
command could not run (a missing content directory, a missing generator, a
refused build root, an empty ``--content``, or a serve process that died).
A run that exits 2 before building or serving has touched nothing.

Argument parsing and exit codes only; the work is in ``scripts.sitebuild``.
Imports only the standard library and ``scripts.sitebuild``.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from scripts.sitebuild.content import (
    ContentDirMissing,
    count_included_pages,
    resolve_content_dir,
)
from scripts.sitebuild.generator import GeneratorMissing, generator_executable
from scripts.sitebuild.model import CONTENT_ENV_VAR
from scripts.sitebuild.pipeline import (
    DEFAULT_BUILD_ROOT,
    DEFAULT_PREVIEW_ROOT,
    BuildRootRefused,
    build,
    guard_root,
)
from scripts.sitebuild.preview import serve

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADDR = "127.0.0.1:8000"


class CannotRun(Exception):
    """The command could not start; the message is the one line to print."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_site",
        description="Build, preview or inspect the project website.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add_content(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--content",
            default=None,
            metavar="PATH",
            help=(
                f"Content directory (default: ${CONTENT_ENV_VAR}, "
                "then website/content/)"
            ),
        )

    def add_build_dir(sub: argparse.ArgumentParser, default: Path) -> None:
        sub.add_argument(
            "--build-dir",
            type=Path,
            default=None,
            metavar="PATH",
            help=f"Build root (default: {default})",
        )

    build_parser = commands.add_parser("build", help="Build the site once")
    add_content(build_parser)
    add_build_dir(build_parser, DEFAULT_BUILD_ROOT)
    build_parser.add_argument(
        "--verbose",
        action="store_true",
        help="After a failure, also print the generator's own output",
    )

    serve_parser = commands.add_parser(
        "serve", help="Preview the site, rebuilding on change"
    )
    add_content(serve_parser)
    add_build_dir(serve_parser, DEFAULT_PREVIEW_ROOT)
    serve_parser.add_argument(
        "--addr",
        default=DEFAULT_ADDR,
        metavar="HOST:PORT",
        help=f"Address to serve on (default: {DEFAULT_ADDR})",
    )

    status_parser = commands.add_parser(
        "status", help="Print has_content=true or has_content=false"
    )
    add_content(status_parser)
    return parser


def _anchored(path: Path) -> Path:
    """``path`` as given if absolute, else read from the repository root."""
    return path if path.is_absolute() else REPO_ROOT / path


def _resolve_content(option_text: str | None) -> Path:
    """The content directory (1.1); a missing one is `CannotRun` (1.2).

    An empty ``--content`` is refused: as a path it would read as ``.``, the
    repository root.
    """
    if option_text == "":
        raise CannotRun("--content must not be empty")
    option = None if option_text is None else Path(option_text)
    environ: dict[str, str] = {}
    from_env = os.environ.get(CONTENT_ENV_VAR)
    if from_env:
        environ[CONTENT_ENV_VAR] = str(_anchored(Path(from_env)))
    try:
        resolved = resolve_content_dir(
            None if option is None else _anchored(option), environ, REPO_ROOT
        )
    except ContentDirMissing as exc:
        raise CannotRun(str(exc)) from exc
    return resolved.path.resolve()


def _resolve_root(option: Path | None, default: Path, content: Path) -> Path:
    """The build root, refused if it is in the repo wrongly or overlaps the content."""
    try:
        root = guard_root(
            _anchored(default if option is None else option), repo_root=REPO_ROOT
        )
    except BuildRootRefused as exc:
        raise CannotRun(str(exc)) from exc
    if _same_or_ancestor(root, content) or _same_or_ancestor(content, root):
        raise CannotRun(
            f"refusing to use {root} as the build root: it overlaps the content "
            f"directory {content}"
        )
    return root


def _same_or_ancestor(inner: Path, outer: Path) -> bool:
    """Whether ``outer`` is ``inner`` or one of its ancestors, by file identity."""
    for candidate in (inner, *inner.parents):
        try:
            if os.path.samefile(candidate, outer):
                return True
        except OSError:
            continue
    return False


def _require_generator() -> None:
    try:
        generator_executable()
    except GeneratorMissing as exc:
        raise CannotRun(str(exc)) from exc


def _run(args: argparse.Namespace) -> int:
    content = _resolve_content(args.content)
    if args.command == "status":
        found = count_included_pages(content) > 0
        print(f"has_content={'true' if found else 'false'}")
        return 0
    if args.command == "serve":
        root = _resolve_root(args.build_dir, DEFAULT_PREVIEW_ROOT, content)
        _require_generator()
        return serve(content, root, repo_root=REPO_ROOT, addr=args.addr)
    root = _resolve_root(args.build_dir, DEFAULT_BUILD_ROOT, content)
    _require_generator()
    outcome = build(content, root, repo_root=REPO_ROOT)
    if outcome.ok:
        print(f"built {outcome.page_count} pages into {root}/html")
        return 0
    for problem in outcome.problems:
        print(problem.render(), file=sys.stderr)
    if args.verbose and outcome.generator_output:
        text = outcome.generator_output
        print(text, end="" if text.endswith("\n") else "\n", file=sys.stderr)
    return 1


def main(argv: Sequence[str]) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _run(args)
    except CannotRun as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
