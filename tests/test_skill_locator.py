"""Pins for :mod:`fitdocs.agentskill` (design: AgentSkillLocator, task 1.1).

Each test names the production mutation it exists to red; see
change-protocol § Fixture Discrimination.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

import fitdocs
from fitdocs import agentskill
from fitdocs.agentskill import (
    BLOCK_SKILL_NAME,
    INBOX_SKILL_NAME,
    PACKAGED_SKILLS,
    SKILL_FILENAME,
    SKILLS_DIR,
    skill_file,
    skill_files,
    skill_root,
)

_PUBLIC_NAMES = {
    "SKILLS_DIR",
    "SKILL_FILENAME",
    "BLOCK_SKILL_NAME",
    "INBOX_SKILL_NAME",
    "PACKAGED_SKILLS",
    "skill_root",
    "skill_file",
    "skill_files",
}


def _installed_skills_dir() -> Path:
    """The real, unpatched installed ``skills/`` directory (not a fixture)."""
    from importlib.resources import files as real_files

    return Path(str(real_files("fitdocs") / SKILLS_DIR))


def test_registry_contains_the_block_skill_name() -> None:
    assert BLOCK_SKILL_NAME in PACKAGED_SKILLS


def test_registry_contains_the_inbox_skill_name() -> None:
    assert INBOX_SKILL_NAME in PACKAGED_SKILLS
    assert INBOX_SKILL_NAME == "fitdocs-workouts"


def test_registry_order_is_block_then_inbox() -> None:
    assert PACKAGED_SKILLS == (BLOCK_SKILL_NAME, INBOX_SKILL_NAME)


def test_skill_root_is_a_real_directory_named_for_the_skill() -> None:
    root = skill_root(BLOCK_SKILL_NAME)
    assert root is not None
    assert root.is_dir()
    assert root.name == BLOCK_SKILL_NAME


def test_skill_file_is_inside_the_root() -> None:
    root = skill_root(BLOCK_SKILL_NAME)
    file_path = skill_file(BLOCK_SKILL_NAME)
    assert root is not None
    assert file_path is not None
    assert file_path == root / SKILL_FILENAME
    assert file_path.is_file()


def test_skill_files_contains_the_skill_file_and_nothing_outside_root() -> None:
    root = skill_root(BLOCK_SKILL_NAME)
    file_path = skill_file(BLOCK_SKILL_NAME)
    listing = skill_files(BLOCK_SKILL_NAME)
    assert isinstance(listing, tuple)
    assert file_path in listing
    assert root is not None
    for path in listing:
        assert path.is_relative_to(root)


def test_unregistered_name_resolves_absent() -> None:
    assert skill_root("no-such-skill") is None
    assert skill_file("no-such-skill") is None
    assert skill_files("no-such-skill") == ()


def _make_fake_package(tmp_path: Path) -> Path:
    """Build ``tmp_path/pkg/skills/build-training-block/`` with no SKILL.md."""
    package_root = tmp_path / "pkg"
    skill_dir = package_root / SKILLS_DIR / BLOCK_SKILL_NAME
    skill_dir.mkdir(parents=True)
    return package_root


def test_absence_fixture_missing_skill_md_resolves_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = _make_fake_package(tmp_path)
    monkeypatch.setattr(agentskill, "files", _fake_files_returning(package_root))

    # Falsity in the starting state: the directory exists (so a directory-
    # existence-only check would wrongly report present).
    assert (package_root / SKILLS_DIR / BLOCK_SKILL_NAME).is_dir()

    assert skill_root(BLOCK_SKILL_NAME) is None
    assert skill_file(BLOCK_SKILL_NAME) is None
    assert skill_files(BLOCK_SKILL_NAME) == ()


def test_absence_fixture_positive_control_proves_monkeypatch_is_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = _make_fake_package(tmp_path)
    monkeypatch.setattr(agentskill, "files", _fake_files_returning(package_root))
    assert skill_root(BLOCK_SKILL_NAME) is None  # before-state: absent

    (package_root / SKILLS_DIR / BLOCK_SKILL_NAME / SKILL_FILENAME).write_text(
        "---\nname: x\n---\nbody\n"
    )

    root = skill_root(BLOCK_SKILL_NAME)
    assert root is not None
    assert root == package_root / SKILLS_DIR / BLOCK_SKILL_NAME


def test_skill_files_sorted_by_relative_posix_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = _make_fake_package(tmp_path)
    monkeypatch.setattr(agentskill, "files", _fake_files_returning(package_root))
    skill_dir = package_root / SKILLS_DIR / BLOCK_SKILL_NAME

    # Files created in this order (SKILL.md, z-last.md, nested/n-middle.md,
    # a-first.md, nested/0-first.md); the asserted relative-path order below
    # (SKILL.md, a-first.md, nested/0-first.md, nested/n-middle.md,
    # z-last.md) was checked to differ from every alternative ordering the
    # named mutations below produce: reverse-sorted order (z-last.md would
    # come first, not last); a "top-level files, then subdirectory files"
    # grouping (both nested/* entries would come after every top-level
    # file, whereas nested/0-first.md sorts before z-last.md here);
    # basename-only sorting (nested/0-first.md's basename "0-first.md"
    # sorts before "SKILL.md", but its relative path "nested/0-first.md"
    # sorts after "a-first.md"); and the unsorted `Path.rglob` traversal
    # order observed on this filesystem for this exact fixture, ["a-first.md",
    # "SKILL.md", "nested", "z-last.md", "nested/n-middle.md",
    # "nested/0-first.md"] (directories included) -- itself also caught by
    # the "no sort at all" mutation because it differs from the asserted
    # order.
    (skill_dir / SKILL_FILENAME).write_text("body\n")
    (skill_dir / "z-last.md").write_text("z\n")
    (skill_dir / "nested").mkdir()
    (skill_dir / "nested" / "n-middle.md").write_text("n\n")
    (skill_dir / "a-first.md").write_text("a\n")
    (skill_dir / "nested" / "0-first.md").write_text("0\n")

    listing = skill_files(BLOCK_SKILL_NAME)
    expected = tuple(sorted(listing, key=lambda p: p.relative_to(skill_dir).as_posix()))
    assert listing == expected
    # The assertion is non-vacuous: ascending order is NOT the reverse order,
    # so a reverse-sort mutation is distinguishable from a correct one.
    assert listing != tuple(reversed(listing))
    relative_names = [p.relative_to(skill_dir).as_posix() for p in listing]
    assert relative_names == [
        "SKILL.md",
        "a-first.md",
        "nested/0-first.md",
        "nested/n-middle.md",
        "z-last.md",
    ]


def _fake_files_returning(package_root: Path) -> Callable[[str], Path]:
    def _fake(_anchor: str) -> Path:
        return package_root

    return _fake


def test_registered_names_and_installed_directories_match_both_ways() -> None:
    skills_dir = _installed_skills_dir()
    assert skills_dir.is_dir()
    subdirectory_names = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert subdirectory_names, (
        "the walk found no skill directories -- check SKILLS_DIR / the install layout"
    )
    assert subdirectory_names == set(PACKAGED_SKILLS)
    assert not (skills_dir / "__init__.py").exists()


def test_module_import_set_is_exactly_the_declared_four() -> None:
    source = inspect.getsource(agentskill)
    tree = ast.parse(source)
    module_names: set[str] = set()
    scanned = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_names.add(alias.name)
                scanned += 1
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            module_names.add(node.module)
            scanned += 1
    assert scanned, "the AST walk found no import statements -- wrong source"
    assert module_names == {
        "__future__",
        "importlib.resources",
        "pathlib",
        "typing",
    }


def test_no_locator_name_is_in_the_public_all() -> None:
    assert not (_PUBLIC_NAMES & set(fitdocs.__all__))
