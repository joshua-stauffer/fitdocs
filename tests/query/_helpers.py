"""Shared synthetic database and indexed-root helpers for query tests."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fitdocs.index.location import resolve_index_location
from fitdocs.index.registry import registered_tables
from fitdocs.index.store import create_index, create_schema


@dataclass(frozen=True)
class DerivedInputs:
    files: Mapping[str, str]
    athlete_toml: str


FIXTURE_TODAY = date(2021, 10, 1)


def plain_database(path: Path, *statements: str) -> Path:

    with create_index(path) as connection:
        for statement in statements:
            connection.execute(statement)
    return path


def schema_only_index(path: Path) -> Path:
    with create_index(path) as connection:
        create_schema(connection, registered_tables())
    return path


def write_fixture_inputs(
    root: Path, base_athlete_toml: str, inputs: DerivedInputs
) -> None:
    resolved_root = root.resolve()
    athlete_path = resolved_root / "athlete.toml"
    athlete_path.write_text(base_athlete_toml + inputs.athlete_toml, encoding="utf-8")
    for relative, contents in inputs.files.items():
        target = (resolved_root / relative).resolve()
        if not target.is_relative_to(resolved_root):
            raise ValueError(f"fixture input path escapes root: {relative!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")


def copy_indexed_root(
    src_root: Path, src_index_dir: Path, dst: Path
) -> tuple[Path, Path]:
    root = dst / "root"
    shutil.copytree(src_root, root)
    home = dst / "home"
    home.mkdir(parents=True, exist_ok=True)
    location = resolve_index_location(
        root,
        environ={"FITDOCS_INDEX_DIR": str(dst / "index-cache")},
        home=home,
    )
    location.directory.mkdir(parents=True, exist_ok=True)
    source_database = src_index_dir / "index.duckdb"
    shutil.copy2(source_database, location.database)
    source_wal = src_index_dir / "index.duckdb.wal"
    if source_wal.exists():
        shutil.copy2(source_wal, location.wal)
    return root, location.directory
