"""Derived index operations preserve command output roots across index states."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TypeAlias
from unittest.mock import patch

from typer.testing import CliRunner

from fitdocs.athlete import load_athlete_inputs
from fitdocs.cli import app
from fitdocs.sync import sync
from tests.index.derived.conftest import TODAY, build_fixture_root
from tests.test_confinement import _TZ, _tiles

_Entry: TypeAlias = tuple[str, bytes | str | int | None]
_RUNNER = CliRunner()


def _inventory(root: Path) -> dict[str, _Entry]:
    """Record all relative entries without following symlinks."""
    entries: dict[str, _Entry] = {}

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir()):
            relative = child.relative_to(root).as_posix()
            mode = child.lstat().st_mode
            if stat.S_ISLNK(mode):
                entries[relative] = ("symlink", os.readlink(child))
            elif stat.S_ISDIR(mode):
                entries[relative] = ("directory", None)
                visit(child)
            elif stat.S_ISREG(mode):
                entries[relative] = ("file", child.read_bytes())
            else:
                entries[relative] = ("other", stat.S_IFMT(mode))

    visit(root)
    return entries


def test_inventory_captures_all_entry_kinds_and_changes(tmp_path: Path) -> None:
    root = tmp_path / "inventory-root"
    root.mkdir()
    (root / "empty").mkdir()
    (root / "payload.txt").write_bytes(b"original-bytes")
    (root / "link").symlink_to("payload.txt")
    if hasattr(os, "mkfifo"):
        os.mkfifo(root / "fifo")

    before = _inventory(root)
    assert before["empty"] == ("directory", None)
    assert before["payload.txt"] == ("file", b"original-bytes")
    assert before["link"] == ("symlink", "payload.txt")
    if hasattr(os, "mkfifo"):
        assert before["fifo"] == ("other", stat.S_IFIFO)

    (root / "empty" / "new.txt").write_bytes(b"new")
    with_child = _inventory(root)
    assert with_child != before


def test_inventory_detects_removed_empty_directory(tmp_path: Path) -> None:
    root = tmp_path / "removed-directory-root"
    root.mkdir()
    (root / "empty").mkdir()
    before = _inventory(root)

    (root / "empty").rmdir()

    assert _inventory(root) != before


def test_inventory_detects_content_only_change_to_existing_file(tmp_path: Path) -> None:
    root = tmp_path / "content-change-root"
    root.mkdir()
    file_path = root / "payload.txt"
    file_path.write_bytes(b"original-bytes")
    before = _inventory(root)

    changed_bytes = b"replacement-bytes"
    file_path.write_bytes(changed_bytes)
    after = _inventory(root)

    assert after["payload.txt"] == ("file", changed_bytes)
    assert after != before


def test_inventory_detects_target_only_change_to_existing_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "link-target-change-root"
    root.mkdir()
    (root / "payload.txt").write_bytes(b"payload")
    (root / "alternate.txt").write_bytes(b"alternate")
    link = root / "link"
    link.symlink_to("payload.txt")
    before = _inventory(root)

    link.unlink()
    link.symlink_to("alternate.txt")
    after = _inventory(root)

    assert after["link"] == ("symlink", "alternate.txt")
    assert after != before


def _prepare_root(root: Path) -> Path:
    build_fixture_root(root, composed=True)
    for page in (root / "workouts").glob("*.md"):
        page.unlink()
    (root / "plans" / "invalid.toml").unlink()
    plan_path = root / "plans" / "derived.toml"
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_text = plan_text.replace(', "missing-override-stem"', "")
    plan_text = plan_text.replace(
        """[[override]]
date = 2026-02-08
id = "override"
stems = ["2026-02-09-override-log"]
reason = "Synthetic override"

""",
        "",
    )
    plan_path.write_text(plan_text, encoding="utf-8")
    source = root / "composed-source"
    sync(
        source,
        root,
        athlete=load_athlete_inputs(root),
        tz=_TZ,
        tiles=_tiles(root),
    )
    (root / "fixture-empty-directory").mkdir()
    (root / "fixture-link").symlink_to("fitdocs.toml")
    return source


def _invoke_cli(command: str, root: Path, source: Path, index_dir: Path) -> int:
    args = [command]
    if command == "sync":
        args.append(str(source))
    args.extend(["--out", str(root)])
    with (
        patch.dict(os.environ, {"FITDOCS_INDEX_DIR": str(index_dir)}),
        patch("fitdocs.cli._today", lambda: TODAY),
        patch("fitdocs.tiles._default_fetch", lambda _url: b"synthetic-tile"),
    ):
        result = _RUNNER.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result.exit_code


def _prebuild_index(root: Path, index_dir: Path) -> None:
    from fitdocs.index.location import resolve_index_location

    with (
        patch.dict(os.environ, {"FITDOCS_INDEX_DIR": str(index_dir)}),
        patch("fitdocs.cli._today", lambda: TODAY),
    ):
        result = _RUNNER.invoke(app, ["index", "--out", str(root)])
    assert result.exit_code == 0, result.output
    location = resolve_index_location(
        root, {"FITDOCS_INDEX_DIR": str(index_dir)}, Path.home()
    )
    assert location.database.is_file()


def test_sync_regen_and_load_preserve_data_root_with_or_without_prebuilt_index(
    tmp_path: Path,
) -> None:
    for command in ("sync", "regen", "load"):
        roots: dict[str, Path] = {}
        sources: dict[str, Path] = {}
        index_dirs: dict[str, Path] = {}
        for condition in ("prebuilt", "fresh"):
            root = tmp_path / command / condition / "data"
            sources[condition] = _prepare_root(root)
            roots[condition] = root
            index_dirs[condition] = tmp_path / command / condition / "index"
            if condition == "prebuilt":
                _prebuild_index(root, index_dirs[condition])

        before = {name: _inventory(root) for name, root in roots.items()}
        exit_codes = {
            condition: _invoke_cli(
                command, roots[condition], sources[condition], index_dirs[condition]
            )
            for condition in ("prebuilt", "fresh")
        }
        after = {name: _inventory(root) for name, root in roots.items()}

        assert before["prebuilt"] == before["fresh"]
        assert exit_codes["prebuilt"] == exit_codes["fresh"]
        assert after["prebuilt"] == after["fresh"]


def test_document_contract_and_runtime_dependencies_match_main_baseline() -> None:
    import tomllib

    from fitdocs import contract

    expected_managed_keys = [
        "avg_hr_bpm",
        "avg_power_w",
        "calories_kcal",
        "date",
        "distance_km",
        "doc_version",
        "elevation_gain_m",
        "generator",
        "indoor",
        "load_basis",
        "load_methodology",
        "load_value",
        "modality",
        "moving_time",
        "source_device",
        "source_distance_m",
        "source_elapsed_s",
        "source_kind",
        "sources",
        "sport",
        "start_time",
        "title",
        "type",
        "uuid",
    ]
    expected_dependencies = [
        "garmin-fit-sdk>=21.208.0",
        "typer>=0.12",
        "rich>=13",
        "pyyaml>=6.0",
        "tomli-w>=1.0",
        "duckdb>=1.2,<2",
    ]
    manifest = tomllib.loads(
        (Path(__file__).resolve().parents[3] / "pyproject.toml").read_text()
    )

    assert contract.DOC_VERSION == 9
    assert contract.CONTRACT_VERSION == "9"
    assert sorted(contract.MANAGED_KEYS) == expected_managed_keys
    assert manifest["project"]["dependencies"] == expected_dependencies
