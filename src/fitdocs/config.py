"""Data-root resolution with loud failure (Req 2.1, 2.2, 2.3).

This module implements the output-location contract (design: DataRootResolver).
The output directory is resolved by an explicit precedence -- the ``--out`` flag,
then the ``FITDOCS_DATA`` environment variable, then a ``.fitdocs/data-root``
pointer file discovered by walking ``start_dir`` and its ancestors -- and by no
other means. There is no current-working-directory fallback and no implicit
default of any kind (Req 2.3): once a source is configured it must resolve to an
existing directory, or resolution fails loudly, naming the failing source and
listing all three configuration options (Req 2.2). This is deliberate -- a typo
in a path must not silently redirect a user's workout documents.

The resolver is pure and side-effect free: ``env`` and ``start_dir`` are injected
rather than read from ``os.environ`` / ``Path.cwd()``, it never creates the data
root (creating it would defeat the loud-against-typos guarantee -- the sync engine
creates the *subdirectories* under an already-resolved root), and it writes
nothing on any path.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

DATA_ROOT_ENV: Final[str] = "FITDOCS_DATA"
POINTER_RELPATH: Final[str] = ".fitdocs/data-root"

_OPTIONS: Final[str] = (
    "Configure the output location with one of:\n"
    "  - the --out flag\n"
    f"  - the {DATA_ROOT_ENV} environment variable\n"
    f"  - a {POINTER_RELPATH} pointer file"
)


class DataRootError(Exception):
    """The data root could not be resolved to an existing directory (Req 2.2).

    The message names the source that failed (the ``--out`` flag, the
    ``FITDOCS_DATA`` env var, or the ``.fitdocs/data-root`` pointer file) and
    lists all three configuration options, so the user can correct it.
    """


def resolve_data_root(
    explicit: Path | None,
    *,
    env: Mapping[str, str],
    start_dir: Path,
) -> Path:
    """Resolve the data root by the explicit precedence, or fail loudly.

    Precedence (Req 2.1): ``explicit`` > ``env[FITDOCS_DATA]`` > the first
    ``.fitdocs/data-root`` pointer file found walking ``start_dir`` upward. A
    source counts as configured when it is present and non-empty; the first
    configured source is used and must resolve to an existing directory, else a
    :class:`DataRootError` is raised naming it (Req 2.2). An empty/whitespace env
    var or an empty pointer is treated as unset rather than as ``Path('.')`` --
    there is no fallback to the current working directory (Req 2.3).

    A relative pointer target resolves against the pointer *file's* directory
    (not ``start_dir``, not the cwd). The returned path is guaranteed to exist
    and be a directory; nothing is ever created or written.
    """
    if explicit is not None:
        return _require_dir(
            explicit,
            not_exist=f"The --out path does not exist: {explicit}",
            not_dir=f"The --out path is not a directory: {explicit}",
        )

    raw_env = env.get(DATA_ROOT_ENV)
    if raw_env is not None and raw_env.strip():
        value = raw_env.strip()
        return _require_dir(
            Path(value),
            not_exist=(
                f"The {DATA_ROOT_ENV} environment variable points to a "
                f"nonexistent path: {value}"
            ),
            not_dir=(
                f"The {DATA_ROOT_ENV} environment variable points to a "
                f"non-directory path: {value}"
            ),
        )

    pointer = _find_pointer(start_dir)
    if pointer is not None:
        return _resolve_pointer(pointer)

    raise DataRootError(_message("No output location is configured."))


def _find_pointer(start_dir: Path) -> Path | None:
    """Return the first ``.fitdocs/data-root`` file at ``start_dir`` or an ancestor."""
    for base in (start_dir, *start_dir.parents):
        candidate = base / POINTER_RELPATH
        if candidate.is_file():
            return candidate
    return None


def _resolve_pointer(pointer: Path) -> Path:
    """Resolve a found pointer file's first line to an existing directory."""
    lines = pointer.read_text().splitlines()
    first = lines[0].strip() if lines else ""
    if not first:
        raise DataRootError(
            _message(f"The {POINTER_RELPATH} pointer file is empty: {pointer}")
        )

    target = Path(first)
    if target.is_absolute():
        candidate = target
    else:
        # Relative targets resolve against the pointer file's directory; normpath
        # collapses '..' lexically without touching the filesystem or the cwd.
        candidate = Path(os.path.normpath(pointer.parent / target))

    return _require_dir(
        candidate,
        not_exist=(
            f"The {POINTER_RELPATH} pointer file ({pointer}) points to a "
            f"nonexistent path: {candidate}"
        ),
        not_dir=(
            f"The {POINTER_RELPATH} pointer file ({pointer}) points to a "
            f"non-directory path: {candidate}"
        ),
    )


def _require_dir(path: Path, *, not_exist: str, not_dir: str) -> Path:
    """Return *path* if it is an existing directory, else raise (Req 2.2)."""
    if not path.exists():
        raise DataRootError(_message(not_exist))
    if not path.is_dir():
        raise DataRootError(_message(not_dir))
    return path


def _message(lead: str) -> str:
    """Compose a loud error: the source-specific lead plus all three options."""
    return f"{lead}\n\n{_OPTIONS}"
