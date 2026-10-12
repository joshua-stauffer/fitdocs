"""Storage: every filesystem read and write of the dashboards feature.

Writes go below ``<data-root>/dashboards/`` only, and only as an atomic
temp-file-then-rename (or temp-file-then-link, for a snapshot, which must never
replace a file). A symbolic link is never followed: each directory level is
inspected with ``lstat``, every file read is opened with ``O_NOFOLLOW``, and a
temp file is created with ``O_EXCL``, which also refuses a link at its name.

This module takes no clock and holds no policy about *what* a page may contain;
it moves bytes, and it refuses anything that is not what fitdocs expects to
find.
"""

from __future__ import annotations

import contextlib
import enum
import errno
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from fitdocs.contract import GENERATED_PREFIX, is_generated
from fitdocs.dashboards.grammar import CHART_ID_RE, PAGE_NAME_RE
from fitdocs.dashboards.snapshot import SNAPSHOT_NAME_RE
from fitdocs.layout import ASSETS_SUBDIR, DASHBOARDS_DIR

ASSET_MARK: Final = f"{GENERATED_PREFIX} -->"  # prefixed to every image written
_DECLARATION_FILE: Final = "AGENTS.md"  # the generated ownership declaration
_PAGE_SUFFIX: Final = ".md"
_IMAGE_SUFFIX: Final = ".svg"
_TEMP_PREFIX: Final = ".dashboards-"
_TEMP_SUFFIX: Final = ".tmp"

_Kind = Literal["missing", "symlink", "directory", "file", "other"]


class Refusal(enum.Enum):
    """Why a page could not be read."""

    SYMLINK = "symlink"
    NOT_REGULAR = "not_regular"
    UNREADABLE = "unreadable"
    NOT_UTF8 = "not_utf8"


@dataclass(frozen=True)
class PageFile:
    """One page as read: its name (no ``.md``), path, exact bytes and text."""

    name: str
    path: Path
    raw: bytes
    text: str


# -- names and paths -----------------------------------------------------------


def _slug(value: str, what: str) -> None:
    pattern = PAGE_NAME_RE if what == "page" else CHART_ID_RE
    if not pattern.fullmatch(value):
        raise ValueError(f"{what} {value!r} is not a slug")


def asset_rel_path(page: str, chart: str) -> str:
    """``assets/<page>/<chart>.svg``: from the page name and chart id only."""
    _slug(page, "page")
    _slug(chart, "chart")
    return f"{ASSETS_SUBDIR}/{page}/{chart}{_IMAGE_SUFFIX}"


def dashboards_root(data_root: Path) -> Path:
    return data_root / DASHBOARDS_DIR


def _assets_root(data_root: Path) -> Path:
    return dashboards_root(data_root) / ASSETS_SUBDIR


# -- inspecting what is on disk ------------------------------------------------


def _kind(path: Path) -> _Kind:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return "missing"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def _dir_refusal(path: Path, label: str) -> str | None:
    kind = _kind(path)
    if kind == "symlink":
        return f"{label} is a symbolic link"
    if kind in ("file", "other"):
        return f"{label} is not a directory"
    return None


def location_refusal(data_root: Path) -> str | None:
    """Why ``dashboards/`` or ``dashboards/assets/`` cannot be used, else ``None``."""
    return _dir_refusal(
        dashboards_root(data_root), f"{DASHBOARDS_DIR}/"
    ) or _dir_refusal(_assets_root(data_root), f"{DASHBOARDS_DIR}/{ASSETS_SUBDIR}/")


def _read_nofollow(path: Path) -> bytes:
    """The file's bytes; a symbolic link at ``path`` raises ``OSError`` (ELOOP)."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def _existing_directory(path: Path) -> bool:
    return _kind(path) == "directory"


def _page_directory(data_root: Path, page: str) -> Path | None:
    """``assets/<page>/`` when it and every level above it is a real directory."""
    folder = _assets_root(data_root) / page
    levels = (dashboards_root(data_root), _assets_root(data_root), folder)
    return folder if all(_existing_directory(level) for level in levels) else None


def _prepare_directory(data_root: Path, page: str) -> Path | str:
    """``assets/<page>/``, created on demand, or the reason it cannot be used.

    ``dashboards/`` itself is never created: it must already exist.
    """
    folder = _assets_root(data_root) / page
    levels = (
        (dashboards_root(data_root), f"{DASHBOARDS_DIR}/", False),
        (_assets_root(data_root), f"{DASHBOARDS_DIR}/{ASSETS_SUBDIR}/", True),
        (folder, f"{DASHBOARDS_DIR}/{ASSETS_SUBDIR}/{page}/", True),
    )
    for path, label, create in levels:
        refusal = _dir_refusal(path, label)
        if refusal is not None:
            return refusal
        if _kind(path) == "missing":
            if not create:
                raise FileNotFoundError(f"{label} does not exist")
            os.mkdir(path)
    return folder


# -- atomic writing ------------------------------------------------------------


def _discard(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)


def _write_temp(directory: Path, data: bytes, mode: int | None = None) -> Path:
    temp = directory / f"{_TEMP_PREFIX}{os.urandom(8).hex()}{_TEMP_SUFFIX}"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if mode is not None:
            os.chmod(temp, mode)
    except BaseException:
        _discard(temp)
        raise
    return temp


def _atomic_replace(path: Path, data: bytes, mode: int | None = None) -> None:
    temp = _write_temp(path.parent, data, mode)
    try:
        os.replace(temp, path)
    except BaseException:
        _discard(temp)
        raise


# -- pages ---------------------------------------------------------------------


def list_markdown(data_root: Path) -> tuple[str, ...]:
    """Names (without ``.md``) of the ``*.md`` entries directly in ``dashboards/``.

    Sorted by code point. ``AGENTS.md``, the generated declaration, is not
    listed. An entry that is a link or a directory is listed too, so that
    :func:`read_page` can refuse it by name. A ``dashboards/`` that is absent, a
    link or not a directory lists nothing.
    """
    directory = dashboards_root(data_root)
    if not _existing_directory(directory):
        return ()
    return tuple(
        sorted(
            entry[: -len(_PAGE_SUFFIX)]
            for entry in os.listdir(directory)
            if entry.endswith(_PAGE_SUFFIX)
            and len(entry) > len(_PAGE_SUFFIX)
            and entry != _DECLARATION_FILE
        )
    )


def read_page(data_root: Path, name: str) -> PageFile | Refusal:
    """The page ``dashboards/<name>.md``, or why it cannot be read safely."""
    if not name or "/" in name:
        raise ValueError(f"page name {name!r} must be one non-empty path segment")
    if _kind(dashboards_root(data_root)) == "symlink":
        return Refusal.SYMLINK
    path = dashboards_root(data_root) / f"{name}{_PAGE_SUFFIX}"
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        return Refusal.UNREADABLE
    if stat.S_ISLNK(mode):
        return Refusal.SYMLINK
    if not stat.S_ISREG(mode):
        return Refusal.NOT_REGULAR
    try:
        raw = _read_nofollow(path)
    except OSError as error:
        return Refusal.SYMLINK if error.errno == errno.ELOOP else Refusal.UNREADABLE
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return Refusal.NOT_UTF8
    return PageFile(name=name, path=path, raw=raw, text=text)


def replace_page(page: PageFile, text: str) -> Literal["written", "changed"]:
    """Replace the page's bytes with ``text`` unless they moved since it was read.

    ``"changed"`` writes nothing. Raises ``OSError`` for a page or its directory
    that is now a link, no longer a regular file, or unreadable; the caller
    reports it. ``text`` is encoded as UTF-8 with no newline translation.
    """
    if _kind(page.path.parent) == "symlink":
        raise OSError(f"{page.path.parent.name}/ is a symbolic link")
    mode = os.lstat(page.path).st_mode
    if stat.S_ISLNK(mode):
        raise OSError(f"{page.path.name} is a symbolic link")
    if not stat.S_ISREG(mode):
        raise OSError(f"{page.path.name} is not a regular file")
    if _read_nofollow(page.path) != page.raw:
        return "changed"
    _atomic_replace(page.path, text.encode("utf-8"), stat.S_IMODE(mode))
    return "written"


# -- chart images --------------------------------------------------------------


def write_asset(
    data_root: Path, page: str, chart: str, svg: str
) -> Literal["written", "unchanged", "foreign"]:
    """Write ``assets/<page>/<chart>.svg`` with the mark, only when it would change.

    ``"foreign"``: a directory level is a link or not a directory, or the image
    path holds a link, a non-file, or a file that does not carry the mark;
    nothing is written.
    """
    _slug(page, "page")
    _slug(chart, "chart")
    folder = _prepare_directory(data_root, page)
    if isinstance(folder, str):
        return "foreign"
    path = folder / f"{chart}{_IMAGE_SUFFIX}"
    data = f"{ASSET_MARK}\n{svg}".encode()
    kind = _kind(path)
    if kind not in ("missing", "file"):
        return "foreign"
    if kind == "file":
        existing = _marked_bytes(path)
        if existing is None:
            return "foreign"
        if existing == data:
            return "unchanged"
    _atomic_replace(path, data)
    return "written"


def _marked_bytes(path: Path) -> bytes | None:
    """The file's bytes when it is readable UTF-8 carrying the mark, else ``None``."""
    try:
        data = _read_nofollow(path)
        return data if is_generated(data.decode("utf-8")) else None
    except (OSError, UnicodeDecodeError):
        return None


# -- snapshots -----------------------------------------------------------------


def _generations(folder: Path, chart: str) -> dict[int, str]:
    """Generation number to file name, for the chart's snapshot names in ``folder``."""
    found: dict[int, str] = {}
    for entry in os.listdir(folder):
        match = SNAPSHOT_NAME_RE.fullmatch(entry)
        if match is not None and match.group("id") == chart:
            found[int(match.group("generation"))] = entry
    return found


def _snapshot_rel(page: str, name: str) -> str:
    return f"{ASSETS_SUBDIR}/{page}/{name}"


def create_snapshot(
    data_root: Path, page: str, chart: str, encode_for: Callable[[int], bytes]
) -> str:
    """Create the next generation's snapshot file and return its relative path.

    The generation is one past the highest the chart already has; ``encode_for``
    receives it and returns the bytes. The file is made with ``os.link`` so an
    existing name is never replaced: when the name is taken the next generation
    is tried. Raises ``OSError`` for a link or non-directory level.
    """
    _slug(page, "page")
    _slug(chart, "chart")
    folder = _prepare_directory(data_root, page)
    if isinstance(folder, str):
        raise OSError(folder)
    generation = max(_generations(folder, chart), default=0) + 1
    while True:
        name = f"{chart}.snapshot-{generation}.json"
        temp = _write_temp(folder, encode_for(generation))
        try:
            os.link(temp, folder / name)
        except FileExistsError:
            generation += 1
            continue
        finally:
            _discard(temp)
        return _snapshot_rel(page, name)


def read_snapshot(data_root: Path, rel_path: str) -> bytes | None:
    """The bytes of ``assets/<page>/<chart>.snapshot-<n>.json``, else ``None``.

    ``None``: the path is not of that exact form, a level is a link, or the file
    is missing, a link, not a regular file or unreadable.
    """
    parts = rel_path.split("/")
    if (
        len(parts) != 3
        or parts[0] != ASSETS_SUBDIR
        or not PAGE_NAME_RE.fullmatch(parts[1])
        or not SNAPSHOT_NAME_RE.fullmatch(parts[2])
    ):
        return None
    folder = _page_directory(data_root, parts[1])
    if folder is None or _kind(folder / parts[2]) != "file":
        return None
    try:
        return _read_nofollow(folder / parts[2])
    except OSError:
        return None


def latest_snapshot(data_root: Path, page: str, chart: str) -> str | None:
    """The relative path of the chart's highest-generation snapshot, else ``None``.

    Only regular files count: a link or directory with a snapshot's name is not
    offered.
    """
    _slug(page, "page")
    _slug(chart, "chart")
    folder = _page_directory(data_root, page)
    if folder is None:
        return None
    names = _generations(folder, chart)
    for generation in sorted(names, reverse=True):
        if _kind(folder / names[generation]) == "file":
            return _snapshot_rel(page, names[generation])
    return None


# -- stale images --------------------------------------------------------------


def _page_texts(directory: Path) -> list[str] | None:
    """The text of every regular ``*.md`` below ``directory`` outside ``assets/``.

    ``None`` when any of them (or any directory on the way) cannot be read.
    """

    def fail(error: OSError) -> None:
        raise error

    texts: list[str] = []
    try:
        for current, subdirectories, files in os.walk(directory, onerror=fail):
            here = Path(current)
            if here == directory:
                subdirectories[:] = [s for s in subdirectories if s != ASSETS_SUBDIR]
            for entry in files:
                path = here / entry
                if entry.endswith(_PAGE_SUFFIX) and _kind(path) == "file":
                    texts.append(_read_nofollow(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    return texts


def remove_stale_images(data_root: Path) -> tuple[str, ...] | None:
    """Delete marked chart images no markdown file under ``dashboards/`` mentions.

    Returns the removed paths relative to ``dashboards/``, sorted; ``None`` when
    the run was skipped (``dashboards/`` or ``assets/`` is a link or not a
    directory, or a markdown file could not be read as UTF-8), in which case
    nothing was removed. An image is
    ``assets/<slug>/<slug>.svg``, a regular file carrying the mark; snapshots
    and every other file are never matched. An ``assets/<slug>/`` emptied by the
    removal is removed too.
    """
    directory = dashboards_root(data_root)
    assets = _assets_root(data_root)
    if _kind(directory) == "missing":
        return ()
    if not _existing_directory(directory):
        return None
    if _kind(assets) == "missing":
        return ()
    if not _existing_directory(assets):
        return None
    texts = _page_texts(directory)
    if texts is None:
        return None
    removed: list[str] = []
    for folder_name in sorted(os.listdir(assets)):
        folder = assets / folder_name
        if not PAGE_NAME_RE.fullmatch(folder_name) or not _existing_directory(folder):
            continue
        emptied = False
        for entry in sorted(os.listdir(folder)):
            rel = _snapshot_rel(folder_name, entry)
            image = folder / entry
            if (
                not entry.endswith(_IMAGE_SUFFIX)
                or not PAGE_NAME_RE.fullmatch(entry[: -len(_IMAGE_SUFFIX)])
                or _kind(image) != "file"
                or _marked_bytes(image) is None
                or any(rel in text for text in texts)
            ):
                continue
            os.unlink(image)
            removed.append(rel)
            emptied = True
        if emptied and not os.listdir(folder):
            os.rmdir(folder)
    return tuple(sorted(removed))
