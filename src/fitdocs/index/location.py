"""Resolve the disposable index cache outside each data root."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.settings import SettingsError

INDEX_DIR_ENV: Final[str] = "FITDOCS_INDEX_DIR"
XDG_CACHE_HOME_ENV: Final[str] = "XDG_CACHE_HOME"
INDEX_FILENAME: Final[str] = "index.duckdb"


class IndexLocationError(SettingsError):
    """The configured index location is invalid or unsafe."""


@dataclass(frozen=True)
class IndexLocation:
    """Resolved paths owned by one data root's index cache."""

    data_root: Path
    base_dir: Path
    directory: Path
    database: Path
    wal: Path
    lock: Path
    building: Path
    staged: Path


def resolve_index_base(environ: Mapping[str, str], home: Path) -> Path:
    """Resolve FITDOCS_INDEX_DIR, XDG_CACHE_HOME, then the home cache."""
    dedicated = environ.get(INDEX_DIR_ENV, "")
    if dedicated:
        candidate = Path(dedicated)
        if not candidate.is_absolute():
            raise IndexLocationError(
                f"{INDEX_DIR_ENV}={dedicated!r} is not an absolute path"
            )
        return candidate

    xdg = environ.get(XDG_CACHE_HOME_ENV, "")
    if xdg:
        candidate = Path(xdg)
        if candidate.is_absolute():
            return candidate / "fitdocs" / "index"

    return home / ".cache" / "fitdocs" / "index"


def data_root_key(data_root: Path) -> str:
    """Return a readable slug and canonical-path digest for a data root."""
    resolved = data_root.resolve()
    slug = re.sub(r"[^a-z0-9]+", "-", resolved.name.lower()).strip("-")[:24]
    if not slug:
        slug = "root"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


def resolve_index_location(
    data_root: Path, environ: Mapping[str, str], home: Path
) -> IndexLocation:
    """Resolve all index paths and refuse a directory inside the data root."""
    resolved_root = data_root.resolve()
    base_dir = resolve_index_base(environ, home).resolve()
    directory = (base_dir / data_root_key(resolved_root)).resolve()
    if directory.is_relative_to(resolved_root):
        raise IndexLocationError(
            f"index directory {directory} is the data root {resolved_root} "
            "or lies inside it"
        )
    return IndexLocation(
        data_root=resolved_root,
        base_dir=base_dir,
        directory=directory,
        database=directory / INDEX_FILENAME,
        wal=directory / f"{INDEX_FILENAME}.wal",
        lock=directory / "index.lock",
        building=directory / f"{INDEX_FILENAME}.building",
        staged=directory / f"{INDEX_FILENAME}.rebuilt",
    )


def ensure_directory(location: IndexLocation) -> None:
    """Create missing cache directories owner-only without chmodding existing ones."""
    missing: list[Path] = []
    current = location.directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
