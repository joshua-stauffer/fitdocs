"""Pins for the ``skill`` command (design: SkillCommand, task 1.2).

See change-protocol § Fixture Discrimination for the mutation each assertion
here is meant to red; that evidence lives in the implementer's report, not in
this module's comments.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import typer.core
import typer.main
from typer.testing import CliRunner

from fitdocs import agentskill
from fitdocs.agentskill import BLOCK_SKILL_NAME, PACKAGED_SKILLS
from fitdocs.cli import _report_skill_listing, app, skill_command

runner = CliRunner()

_FORBIDDEN_NAMES = {
    "resolve_data_root",
    "_resolved_data_root",
    "load_settings_document",
    "load_athlete_inputs",
    "apply_load",
    "run_history",
    "run_reconcile",
    "_run_plan_pass",
}


def _snapshot(root: Path) -> dict[str, tuple[int, int] | None]:
    """Relative-path -> (size, mtime_ns) for every file, ``None`` for every
    directory, recursively under ``root`` -- a new empty directory changes
    this snapshot even though it holds no file."""
    result: dict[str, tuple[int, int] | None] = {}
    for path in sorted(root.rglob("*")):
        key = str(path.relative_to(root))
        if path.is_file():
            result[key] = (path.stat().st_size, path.stat().st_mtime_ns)
        elif path.is_dir():
            result[key] = None
    return result


def _isolate(monkeypatch: pytest.MonkeyPatch, cwd: Path) -> None:
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    monkeypatch.chdir(cwd)


# --- listing (Req 1.3, 1.6) ---------------------------------------------


def test_listing_exits_zero_one_line_per_registered_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    result = runner.invoke(app, ["skill"])
    assert result.exit_code == 0
    for name in PACKAGED_SKILLS:
        matching = [
            line for line in result.output.splitlines() if line.startswith(name)
        ]
        assert matching, f"expected a line for {name!r}"
        # second field is an existing, absolute directory (Req 1.3).
        field = matching[0][len(name) :].strip()
        assert Path(field).is_absolute()
        assert Path(field).is_dir()


# --- by name, present (Req 1.4) -----------------------------------------


def test_by_name_present_prints_path_then_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    result = runner.invoke(app, ["skill", BLOCK_SKILL_NAME])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) >= 2
    first_path = Path(lines[0])
    assert first_path.is_absolute()
    assert first_path.is_dir()
    assert first_path.name == BLOCK_SKILL_NAME
    # Full-recipe pin (Req 1.4): both the source (line 1's own path) and the
    # destination must appear together, in this exact shape -- checking only
    # "cp -R" or only that the line ends in the skill's name each survive a
    # recipe that drops the destination entirely, because the *source* half
    # already ends in the skill's name.
    assert f"cp -R {first_path} <skills-dir>/{BLOCK_SKILL_NAME}" in lines[1]


# --- by name, unknown (Req 1.5) -----------------------------------------


def test_unknown_name_exits_two_and_lists_packaged_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    result = runner.invoke(app, ["skill", "no-such-skill"])
    assert result.exit_code == 2
    # Naming happens on stderr specifically (task text: "stderr naming it"),
    # via _config_error -- not merely somewhere in the combined output, which
    # a stdout-printing bypass of _config_error would also satisfy.
    assert "no-such-skill" in result.stderr
    assert BLOCK_SKILL_NAME in result.stderr


# --- absence (Req 1.6) ---------------------------------------------------


def _fake_files_returning(package_root: Path) -> Callable[[str], Path]:
    def _fake(_anchor: str) -> Path:
        return package_root

    return _fake


def _make_absent_package(tmp_path: Path) -> Path:
    """``tmp_path/pkg/skills/`` exists but holds no packaged skill directory."""
    package_root = tmp_path / "pkg"
    (package_root / agentskill.SKILLS_DIR).mkdir(parents=True)
    return package_root


def test_absent_skill_listing_exits_two_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    package_root = _make_absent_package(tmp_path)
    monkeypatch.setattr(agentskill, "files", _fake_files_returning(package_root))

    result = runner.invoke(app, ["skill"])

    assert result.exit_code == 2
    # Naming on stderr specifically (task text), via _config_error.
    assert BLOCK_SKILL_NAME in result.stderr
    assert "Traceback" not in result.output
    # The listing itself (stdout, printed before the config error) also names
    # the absent skill, and its absence marker is unambiguous, not merely a
    # path -- Req 1.6's "not present" case.
    assert f"{BLOCK_SKILL_NAME}  (not present in this installation)" in result.stdout


def test_absent_skill_by_name_exits_two_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    package_root = _make_absent_package(tmp_path)
    monkeypatch.setattr(agentskill, "files", _fake_files_returning(package_root))

    result = runner.invoke(app, ["skill", BLOCK_SKILL_NAME])

    assert result.exit_code == 2
    # Naming on stderr specifically (task text), via _config_error.
    assert BLOCK_SKILL_NAME in result.stderr
    assert "Traceback" not in result.output
    # Req 1.6: the by-name absent case reports the installation as
    # incomplete, exactly like the listing's absent case.
    assert "incomplete" in result.stderr


# --- no data root needed; reachability control (Req 1.7) -----------------


def test_no_data_root_needed_exits_zero_while_check_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)

    skill_result = runner.invoke(app, ["skill"])
    assert skill_result.exit_code == 0

    check_result = runner.invoke(app, ["check"])
    assert check_result.exit_code == 2


# --- no writes (Req 1.7) --------------------------------------------------


@pytest.mark.parametrize("args", [["skill"], ["skill", BLOCK_SKILL_NAME]])
def test_no_writes_present_case(
    args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    from fitdocs.agentskill import skill_root

    root = skill_root(BLOCK_SKILL_NAME)
    assert root is not None
    before_cwd = _snapshot(tmp_path)
    before_skill = _snapshot(root)

    result = runner.invoke(app, args)
    assert result.exit_code == 0

    assert _snapshot(tmp_path) == before_cwd
    assert _snapshot(root) == before_skill


def test_no_writes_unknown_name_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    before_cwd = _snapshot(tmp_path)

    result = runner.invoke(app, ["skill", "no-such-skill"])
    assert result.exit_code == 2

    assert _snapshot(tmp_path) == before_cwd


@pytest.mark.parametrize("args", [["skill"], ["skill", BLOCK_SKILL_NAME]])
def test_no_writes_absent_case(
    args: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    package_root = _make_absent_package(tmp_path)
    monkeypatch.setattr(agentskill, "files", _fake_files_returning(package_root))
    before_cwd = _snapshot(tmp_path)
    before_skill_dir = _snapshot(package_root / agentskill.SKILLS_DIR)

    result = runner.invoke(app, args)
    assert result.exit_code == 2

    assert _snapshot(tmp_path) == before_cwd
    assert _snapshot(package_root / agentskill.SKILLS_DIR) == before_skill_dir


# --- parameter set and help (Req 1.3, 1.4) --------------------------------


def test_parameter_set_is_exactly_name() -> None:
    group = cast(typer.core.TyperGroup, typer.main.get_command(app))
    params = group.commands["skill"].params
    assert {p.name for p in params} == {"name"}


def test_skill_appears_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "skill" in result.stdout


# --- docstring: registered count, exit-code case, data-root posture ------


def test_docstring_command_list_names_skill() -> None:
    import fitdocs.cli as cli_module

    assert "fitdocs skill [NAME]" in (cli_module.__doc__ or "")


def test_registered_command_count_matches_docstring_opening() -> None:
    import fitdocs.cli as cli_module

    group = cast(typer.core.TyperGroup, typer.main.get_command(app))
    commands = group.commands
    assert len(commands) == 9, sorted(commands)
    doc = cli_module.__doc__ or ""
    assert "Nine" in doc[:400]
    assert "Four feature commands" not in doc


def test_docstring_exit_code_paragraph_covers_unknown_or_absent_skill() -> None:
    import fitdocs.cli as cli_module

    doc = cli_module.__doc__ or ""
    exit_two_start = doc.index("``2``")
    exit_two_section = doc[exit_two_start : exit_two_start + 800]
    assert "skill" in exit_two_section


def test_docstring_data_root_posture_names_skill_beside_plugins() -> None:
    import fitdocs.cli as cli_module

    doc = cli_module.__doc__ or ""
    posture_start = doc.index("Data-root posture")
    posture_section = doc[posture_start : posture_start + 1200]
    # Whitespace-normalized so a line wrap inside the sentence (as in the
    # pre-task text, which wraps mid-sentence right before "This\nrule") does
    # not defeat a substring check either way.
    normalized = " ".join(posture_section.split())
    assert "``skill``" in normalized
    assert "``plugins``" in normalized
    # A token unique to the *new* sentence -- not merely "skill"/"plugins",
    # which the pre-task sentence already names too (it defers to them, it
    # does not name skill as the second instance of "describes the installed
    # tool, resolves nothing, and cannot fail for want of a data root").
    assert "cannot fail for want of a data root" in normalized
    # A token unique to the *old* sentence, confirming it is gone rather than
    # merely present alongside the new one.
    assert "docs/compatibility.md" not in normalized


# --- AST pins: no data-root machinery reachable ---------------------------


def _names_in(func: Callable[..., object]) -> set[str]:
    source = inspect.getsource(func)
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_skill_command_ast_forbids_data_root_machinery() -> None:
    names = _names_in(skill_command)
    assert names, "the walk scanned no names -- wrong function body"
    assert "skill_root" in names
    assert names.isdisjoint(_FORBIDDEN_NAMES)


def test_report_skill_listing_ast_forbids_data_root_machinery() -> None:
    names = _names_in(_report_skill_listing)
    assert names, "the walk scanned no names -- wrong function body"
    assert "skill_root" in names
    assert names.isdisjoint(_FORBIDDEN_NAMES)
