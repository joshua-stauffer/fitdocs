"""Schema-change discovery from package data, and the two directories' parity."""

from __future__ import annotations

import re
import shutil
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal

import pytest

from fitdocs_relay.storage.interface import StorageError
from fitdocs_relay.storage.migrate import (
    load_changes,
    migrations_directory,
    schema_changes,
)

BACKENDS: tuple[Literal["sqlite", "postgres"], ...] = ("sqlite", "postgres")


def names(directory: Traversable) -> set[str]:
    return {entry.name for entry in directory.iterdir()}


def parity_problems(sqlite_dir: Traversable, postgres_dir: Traversable) -> list[str]:
    """The names in one directory and not the other, one line each."""
    left, right = names(sqlite_dir), names(postgres_dir)
    return [f"only in sqlite: {n}" for n in sorted(left - right)] + [
        f"only in postgres: {n}" for n in sorted(right - left)
    ]


def test_the_two_directories_hold_the_same_file_names() -> None:
    sqlite_dir, postgres_dir = (migrations_directory(b) for b in BACKENDS)
    assert names(sqlite_dir), "the parity check is looking at an empty directory"
    assert parity_problems(sqlite_dir, postgres_dir) == []
    assert "0001_initial.sql" in names(sqlite_dir)


@pytest.mark.parametrize("stray_in", BACKENDS)
def test_a_stray_file_in_either_directory_reds_the_parity_check(
    tmp_path: Path, stray_in: str
) -> None:
    sqlite_copy, postgres_copy = tmp_path / "sqlite", tmp_path / "postgres"
    shutil.copytree(str(migrations_directory("sqlite")), sqlite_copy)
    shutil.copytree(str(migrations_directory("postgres")), postgres_copy)
    assert parity_problems(sqlite_copy, postgres_copy) == []

    (sqlite_copy if stray_in == "sqlite" else postgres_copy).joinpath(
        "0002_stray.sql"
    ).write_text("SELECT 1;\n")

    assert parity_problems(sqlite_copy, postgres_copy) == [
        f"only in {stray_in}: 0002_stray.sql"
    ]


@pytest.mark.parametrize("backend", BACKENDS)
def test_discovery_reads_contiguous_numbered_changes_from_package_data(
    backend: Literal["sqlite", "postgres"],
) -> None:
    changes = schema_changes(backend)
    assert [c.version for c in changes] == list(range(1, len(changes) + 1))
    assert changes[0].name == "0001_initial"
    assert all(re.fullmatch(r"\d{4}_[a-z0-9_]+", c.name) for c in changes)
    on_disk = (
        files("fitdocs_relay.storage") / "migrations" / backend / "0001_initial.sql"
    )
    assert changes[0].sql == on_disk.read_text(encoding="utf-8")
    assert "CREATE TABLE tokens" in changes[0].sql


def _directory(root: Path, *file_names: str) -> Path:
    root.mkdir()
    for name in file_names:
        (root / name).write_text(f"-- {name}\n")
    return root


def test_discovery_orders_by_number_not_by_listing(tmp_path: Path) -> None:
    directory = _directory(tmp_path / "d", "0003_c.sql", "0001_a.sql", "0002_b.sql")
    assert [(c.version, c.name) for c in load_changes(directory)] == [
        (1, "0001_a"),
        (2, "0002_b"),
        (3, "0003_c"),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        ("0002_b.sql",),  # does not start at 1
        ("0001_a.sql", "0003_c.sql"),  # a gap
        ("0001_a.sql", "0001_b.sql"),  # a repeated number
        ("0001_a.sql", "notes.txt"),  # a stray file
        ("0001_a.sql", "1_b.sql"),  # a malformed number
    ],
)
def test_discovery_refuses_what_is_not_contiguous_from_one(
    tmp_path: Path, bad: tuple[str, ...]
) -> None:
    with pytest.raises(StorageError):
        load_changes(_directory(tmp_path / "d", *bad))


def test_a_directory_named_like_a_change_is_not_a_change(tmp_path: Path) -> None:
    directory = _directory(tmp_path / "d", "0001_a.sql")
    (directory / "0002_b.sql").mkdir()
    with pytest.raises(StorageError):
        load_changes(directory)
