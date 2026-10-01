"""Keep a served site equal to the last content that built cleanly (7.1-7.4).

``serve`` builds into ``<root>/check`` and, only when that build succeeded, syncs
its planned tree *in place* into ``<root>/live`` (``sync_tree``: ``zensical
serve`` watches ``live/``, and whether it notices a renamed or swapped directory
depends on the platform). The serve process starts on ``live/`` after the first
success and is terminated when the loop exits, however it exits. A failed build
prints its problem lines and leaves ``live/`` alone. Changes are found by polling
``(mtime_ns, size)`` snapshots of the content directory, ``website/overrides/``,
``website/assets/`` and the template. Standard library plus ``scripts.sitebuild``.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from scripts.sitebuild.config import TEMPLATE_PATH
from scripts.sitebuild.generator import GENERATOR_PATH, start_serve
from scripts.sitebuild.model import Problem
from scripts.sitebuild.pipeline import build, guard_root
from scripts.sitebuild.stage import sync_tree

_TERMINATE_TIMEOUT = 5.0


def snapshot(paths: Sequence[Path]) -> dict[str, tuple[int, int]]:
    """``(mtime_ns, size)`` for every file at or under ``paths``.

    Every entry that is not a directory is recorded: files, and links, where a
    link to a directory is recorded as a link and not followed. A watched path
    that is itself a link to a directory is walked into. An absent path, or an
    entry that vanishes mid-walk, is skipped. Creating, changing (mtime or size)
    or deleting such an entry alters the result; an empty directory is not
    recorded.
    """
    found: dict[str, tuple[int, int]] = {}
    for path in paths:
        _record(found, path)
        for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
            for name in (*filenames, *dirnames):  # a link to a directory is listed here
                _record(found, Path(dirpath) / name)
    return found


def _record(found: dict[str, tuple[int, int]], path: Path) -> None:
    try:
        info = path.lstat()
    except OSError:
        return
    if not stat.S_ISDIR(info.st_mode):
        found[str(path)] = (info.st_mtime_ns, info.st_size)


def serve(
    content_dir: Path,
    root: Path,
    *,
    repo_root: Path,
    addr: str,
    poll_interval: float = 0.5,
    stop: threading.Event | None = None,
    out: TextIO = sys.stderr,
) -> int:
    """Build, serve and rebuild on change until ``stop`` is set or Ctrl-C; return 0.

    If the serve process exits on its own (a bound port, say), one
    ``site generator: serve exited with status N`` line goes to ``out`` and the
    return value is 2, the "could not run" code of the CLI contract.
    """
    stop = threading.Event() if stop is None else stop
    root = guard_root(root, repo_root=repo_root)
    check, live = root / "check", root / "live"
    watched = [
        content_dir,
        repo_root / "website" / "overrides",
        repo_root / "website" / "assets",
        repo_root / TEMPLATE_PATH,
    ]
    process: subprocess.Popen[bytes] | None = None
    try:
        while True:
            current = snapshot(watched)
            outcome = build(content_dir, check, repo_root=repo_root)
            tree = outcome.tree
            if outcome.ok and tree is not None:
                sync_tree(tree, live)
                if process is None:
                    process = start_serve(live, addr)
            else:
                for problem in outcome.problems:
                    print(problem.render(), file=out)
            while True:
                if stop.wait(poll_interval):
                    return 0
                if process is not None and process.poll() is not None:
                    died = Problem(
                        GENERATOR_PATH,
                        "",
                        f"serve exited with status {process.returncode}",
                    )
                    print(died.render(), file=out)
                    return 2
                if snapshot(watched) != current:
                    break
    except KeyboardInterrupt:
        return 0
    finally:
        if process is not None:
            _terminate(process)


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Stop the serve process, killing it if it ignores the request."""
    process.terminate()
    try:
        process.wait(timeout=_TERMINATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


__all__ = ["serve", "snapshot"]
