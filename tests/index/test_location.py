from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from fitdocs.index.location import (
    IndexLocationError,
    data_root_key,
    ensure_directory,
    resolve_index_base,
    resolve_index_location,
)
from fitdocs.settings import SettingsError


def test_resolution_order_across_all_environment_combinations(tmp_path: Path) -> None:
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    override = tmp_path / "override"
    cases = [
        ({"FITDOCS_INDEX_DIR": str(override), "XDG_CACHE_HOME": str(xdg)}, override),
        (
            {"FITDOCS_INDEX_DIR": "", "XDG_CACHE_HOME": str(xdg)},
            xdg / "fitdocs" / "index",
        ),
        (
            {"FITDOCS_INDEX_DIR": "", "XDG_CACHE_HOME": "relative-cache"},
            home / ".cache" / "fitdocs" / "index",
        ),
        ({"FITDOCS_INDEX_DIR": ""}, home / ".cache" / "fitdocs" / "index"),
        ({"XDG_CACHE_HOME": str(xdg)}, xdg / "fitdocs" / "index"),
        ({}, home / ".cache" / "fitdocs" / "index"),
    ]
    for environ, expected in cases:
        assert resolve_index_base(environ, home) == expected


def test_empty_override_is_skipped_and_nonempty_relative_override_is_refused(
    tmp_path: Path,
) -> None:
    assert resolve_index_base({"FITDOCS_INDEX_DIR": ""}, tmp_path / "home") == (
        tmp_path / "home" / ".cache" / "fitdocs" / "index"
    )
    with pytest.raises(IndexLocationError) as raised:
        resolve_index_base({"FITDOCS_INDEX_DIR": "relative/index"}, tmp_path / "home")
    assert "FITDOCS_INDEX_DIR" in str(raised.value)
    assert "relative/index" in str(raised.value)
    assert issubclass(IndexLocationError, SettingsError)


def test_root_key_uses_canonical_path_slug_and_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "My Athlete!"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    link = tmp_path / "alias"
    link.symlink_to(root, target_is_directory=True)
    relative_root = Path(os.path.relpath(root, Path.cwd()))
    canonical = root.resolve()
    expected = f"my-athlete-{hashlib.sha256(str(canonical).encode()).hexdigest()[:16]}"
    other_parent = tmp_path / "other-parent"
    other_parent.mkdir()
    same_name_other_root = other_parent / "My Athlete!"
    assert data_root_key(same_name_other_root) != expected
    assert data_root_key(relative_root) == expected
    assert data_root_key(link) == expected
    long_root = tmp_path / ("A" * 30)
    assert data_root_key(long_root).startswith("a" * 24 + "-")


def test_empty_slug_falls_back_to_root(tmp_path: Path) -> None:
    root = tmp_path / "!!!"
    digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    assert data_root_key(root) == f"root-{digest}"


@pytest.mark.parametrize("index_base_kind", ["equal", "inside", "symlink-inside"])
def test_refuses_data_root_and_descendants_with_resolved_paths(
    tmp_path: Path, index_base_kind: str
) -> None:
    root = tmp_path / "athlete"
    root.mkdir()
    inside = root / "cache"
    inside.mkdir()
    if index_base_kind == "equal":
        base = tmp_path / "equal-base"
        base.mkdir()
        (base / data_root_key(root)).symlink_to(root, target_is_directory=True)
    elif index_base_kind == "inside":
        base = inside
    else:
        base = tmp_path / "cache-base"
        base.mkdir()
        (base / data_root_key(root)).symlink_to(inside, target_is_directory=True)
    expected_directory = (base.resolve() / data_root_key(root)).resolve()
    if index_base_kind == "equal":
        assert expected_directory == root.resolve()
    with pytest.raises(IndexLocationError) as raised:
        resolve_index_location(
            root, {"FITDOCS_INDEX_DIR": str(base)}, tmp_path / "home"
        )
    message = str(raised.value)
    assert f"index directory {expected_directory}" in message
    assert f"is the data root {root.resolve()}" in message


def test_sibling_sharing_root_prefix_is_allowed(tmp_path: Path) -> None:
    root = tmp_path / "athlete"
    root.mkdir()
    base = tmp_path / "athlete-cache"
    location = resolve_index_location(
        root, {"FITDOCS_INDEX_DIR": str(base)}, tmp_path / "home"
    )
    assert location.directory == base / data_root_key(root)


def test_location_paths_are_all_within_directory(tmp_path: Path) -> None:
    root = tmp_path / "athlete"
    root.mkdir()
    root_link = tmp_path / "athlete-link"
    root_link.symlink_to(root, target_is_directory=True)
    real_base = tmp_path / "real-cache"
    real_base.mkdir()
    base_link = tmp_path / "cache-link"
    base_link.symlink_to(real_base, target_is_directory=True)
    location = resolve_index_location(
        root_link, {"FITDOCS_INDEX_DIR": str(base_link)}, tmp_path / "home"
    )
    assert location.data_root == root.resolve()
    assert location.base_dir == real_base.resolve()
    assert location.directory == real_base / data_root_key(root)
    assert location.database == location.directory / "index.duckdb"
    assert location.wal == location.directory / "index.duckdb.wal"
    assert location.lock == location.directory / "index.lock"
    assert location.building == location.directory / "index.duckdb.building"
    assert location.staged == location.directory / "index.duckdb.rebuilt"


def test_index_file_paths_are_confined_to_the_directory(tmp_path: Path) -> None:
    root = tmp_path / "athlete"
    root.mkdir()
    location = resolve_index_location(
        root, {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")}, tmp_path / "home"
    )
    for path in (
        location.database,
        location.wal,
        location.lock,
        location.building,
        location.staged,
    ):
        assert path.is_relative_to(location.directory)


def test_ensure_directory_creates_owner_only_dirs_and_preserves_existing_mode(
    tmp_path: Path,
) -> None:
    root = tmp_path / "athlete"
    root.mkdir()
    existing_parent = tmp_path / "existing-parent"
    existing_parent.mkdir(mode=0o755)
    existing_parent.chmod(0o755)
    location = resolve_index_location(
        root,
        {"FITDOCS_INDEX_DIR": str(existing_parent / "missing" / "nested" / "cache")},
        tmp_path / "home",
    )
    ensure_directory(location)
    assert stat.S_IMODE(existing_parent.stat().st_mode) == 0o755
    created_paths = [
        location.base_dir,
        location.base_dir.parent,
        location.base_dir.parent.parent,
        location.directory,
    ]
    assert all(path.is_dir() for path in created_paths)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o700 for path in created_paths)

    existing_base = tmp_path / "existing-cache"
    existing_base.mkdir(mode=0o755)
    existing_base.chmod(0o755)
    existing_location = resolve_index_location(
        root, {"FITDOCS_INDEX_DIR": str(existing_base)}, tmp_path / "home"
    )
    existing_location.directory.mkdir(mode=0o755)
    existing_location.directory.chmod(0o755)
    before = stat.S_IMODE(existing_location.directory.stat().st_mode)
    ensure_directory(existing_location)
    assert stat.S_IMODE(existing_base.stat().st_mode) == 0o755
    assert stat.S_IMODE(existing_location.directory.stat().st_mode) == before == 0o755
