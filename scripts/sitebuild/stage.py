"""Describe a build root as bytes, write it fresh, or sync it in place (3.3, 7.2).

``plan_tree`` is pure apart from reading files: the two source directories it is
given and the content assets' source paths.
``write_tree`` and ``sync_tree`` write only inside the root they are given and
never follow a symbolic link out of it (1.3). Standard library plus
``scripts.sitebuild``: no third-party imports.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from scripts.sitebuild.model import BRAND_DIR, HOME_PAGE, HOME_TEMPLATE, SiteContent

MANAGED: Final[tuple[str, ...]] = ("mkdocs.yml", "staged", "overrides", "html")
STAGED: Final = "staged"
HTML: Final = "html"

_CONFIG: Final = "mkdocs.yml"
_OVERRIDES: Final = "overrides"
# The managed names a map may contain. ``html/`` is generator output, so no map
# describes it; ``.cache/`` is not managed at all.
_PLANNED: Final[tuple[str, ...]] = (_CONFIG, STAGED, _OVERRIDES)
_FENCE: Final = "---\n"
# The 1-based line the home page's injected ``template:`` line occupies in the
# staged file: straight after the opening fence.
INJECTED_LINE: Final = 2


def plan_tree(
    content: SiteContent,
    *,
    config_text: str,
    llms: str,
    llms_full: str,
    assets_dir: Path,
    overrides_dir: Path,
) -> dict[str, bytes]:
    """The build root as a mapping of root-relative POSIX path to bytes."""
    tree: dict[str, bytes] = {}

    def put(key: str, data: bytes) -> None:
        if key in tree:
            raise ValueError(f"two sources for one staged path: {key}")
        tree[key] = data

    put(_CONFIG, config_text.encode("utf-8"))
    for page in content.pages:
        text = page.staged_text
        if page.path == HOME_PAGE:
            text = _inject_template(text)
        put(f"{STAGED}/{page.path}", text.encode("utf-8"))
    for asset in content.assets:
        put(f"{STAGED}/{asset.path}", asset.source.read_bytes())
    for rel, data in _read_dir(assets_dir):
        put(f"{STAGED}/{BRAND_DIR}/{rel}", data)
    put(f"{STAGED}/llms.txt", llms.encode("utf-8"))
    put(f"{STAGED}/llms-full.txt", llms_full.encode("utf-8"))
    for rel, data in _read_dir(overrides_dir):
        put(f"{_OVERRIDES}/{rel}", data)
    return tree


def write_tree(tree: Mapping[str, bytes], root: Path) -> None:
    """Remove the managed paths of ``root``, then write ``tree`` into it.

    ``.cache/`` and every other entry of the root are left as they are. A key
    that could leave the root raises ``ValueError`` before anything is touched.
    """
    _check_keys(tree)
    root.mkdir(parents=True, exist_ok=True)
    for name in MANAGED:
        _remove(root / name)
    for key in sorted(tree):
        _write_file(root, key, tree[key])


def sync_tree(tree: Mapping[str, bytes], root: Path) -> None:
    """Make ``mkdocs.yml``, ``staged/`` and ``overrides/`` equal ``tree``, in place.

    Files whose bytes differ are rewritten, managed files absent from the map
    are deleted and directories they empty are removed. No directory is renamed,
    or swapped for a new directory, and the top-level ``staged/`` and
    ``overrides/`` directories are kept once they exist. ``html/`` and ``.cache/``
    are not touched.
    """
    _check_keys(tree)
    root.mkdir(parents=True, exist_ok=True)
    files = set(tree)
    dirs = {
        "/".join(key.split("/")[:n])
        for key in tree
        for n in range(1, len(key.split("/")))
    }
    for name in _PLANNED:
        path = root / name
        if _is_real_dir(path):
            _sweep(path, name, files, dirs)
        elif name not in files and name not in dirs:
            _remove(path)
    for key in sorted(tree):
        _write_file(root, key, tree[key], skip_equal=True)


def source_where(path: str, where: str) -> str:
    """Map a generator-reported ``line:col`` back to the content file's line.

    Only the home page carries an injected line, so only its locations after
    that line move up by one; every other path, and a ``where`` that is not
    ``line:col``, comes back unchanged.
    """
    if path != HOME_PAGE:
        return where
    line, sep, col = where.partition(":")
    if not (sep and line.isdecimal() and col.isdecimal()):
        return where
    number = int(line)
    if number <= INJECTED_LINE:
        return where
    return f"{number - 1}:{col}"


def _inject_template(text: str) -> str:
    if not text.startswith(_FENCE):
        raise ValueError(f"{HOME_PAGE}: staged text does not open with a '---' line")
    return f"{_FENCE}template: {HOME_TEMPLATE}\n{text[len(_FENCE) :]}"


def _read_dir(directory: Path) -> list[tuple[str, bytes]]:
    return [
        (path.relative_to(directory).as_posix(), path.read_bytes())
        for path in sorted(directory.rglob("*"))
        if path.is_file()
        and not any(part.startswith(".") for part in path.relative_to(directory).parts)
    ]


def _check_keys(tree: Mapping[str, bytes]) -> None:
    for key in tree:
        parts = key.split("/")
        ok = (
            parts[0] in _PLANNED
            and all(p not in ("", ".", "..") for p in parts)
            and "\0" not in key
            and (len(parts) == 1) == (parts[0] == _CONFIG)
        )
        if not ok:
            raise ValueError(f"not a path inside a build root: {key!r}")


def _is_real_dir(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _remove(path: Path) -> None:
    """Delete a file, a link (never its target) or a whole directory tree."""
    if not os.path.lexists(path):
        return
    if _is_real_dir(path):
        for child in list(path.iterdir()):
            _remove(child)
        path.rmdir()
    else:
        path.unlink()


def _sweep(directory: Path, rel: str, files: set[str], dirs: set[str]) -> None:
    """Delete what the map does not want under a real directory, in place."""
    for child in list(directory.iterdir()):
        child_rel = f"{rel}/{child.name}"
        if _is_real_dir(child):
            if child_rel in dirs:
                _sweep(child, child_rel, files, dirs)
            else:
                _remove(child)
        elif child_rel not in files:
            _remove(child)


def _write_file(root: Path, key: str, data: bytes, *, skip_equal: bool = False) -> None:
    parts = key.split("/")
    directory = root
    for part in parts[:-1]:
        directory = directory / part
        if not _is_real_dir(directory):
            _remove(directory)
            directory.mkdir()
    target = directory / parts[-1]
    if skip_equal and _is_real_file(target):
        if target.read_bytes() == data:
            return
    elif os.path.lexists(target):
        _remove(target)
    with open(target, "wb") as handle:
        handle.write(data)


def _is_real_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False
