"""The relay's pinned copies of the shared modules (design: SharedCopySync)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.sync_relay_shared import (
    REPO_ROOT,
    SHARED_MODULES,
    SYNC_COMMAND,
    drifted,
    main,
)

SHARED_DIR = "relay/src/fitdocs_relay/shared"
SCRIPT = REPO_ROOT / "scripts" / "sync_relay_shared.py"

# The pinned pairs, by literal: relay-server's two, then strava-publish's three.
# Later specs append to SHARED_MODULES, so these are checked as a subset.
PINNED_PAIRS = (
    (
        "src/fitdocs/connectors/relay_codes.py",
        f"{SHARED_DIR}/relay_codes.py",
    ),
    (
        "src/fitdocs/connectors/relay_envelope.py",
        f"{SHARED_DIR}/relay_envelope.py",
    ),
    (
        "src/fitdocs/publish/outcomes.py",
        f"{SHARED_DIR}/outcomes.py",
    ),
    (
        "src/fitdocs/connectors/relay_targets.py",
        f"{SHARED_DIR}/relay_targets.py",
    ),
    (
        "src/fitdocs/identity/strict.py",
        f"{SHARED_DIR}/strict.py",
    ),
)

Pairs = tuple[tuple[str, str], ...]


def byte_drift(root: Path, pairs: Pairs) -> list[str]:
    return drifted(root, pairs)


def orphans(root: Path, pairs: Pairs) -> list[str]:
    """Python files in shared/ other than its own `__init__.py` and the copies."""
    listed = {copy for _, copy in pairs}
    found = sorted(
        p.relative_to(root).as_posix() for p in (root / SHARED_DIR).rglob("*.py")
    )
    marker = f"{SHARED_DIR}/__init__.py"
    return [f for f in found if f not in listed and f != marker]


def missing_literals(pairs: Pairs) -> list[tuple[str, str]]:
    return [pair for pair in PINNED_PAIRS if pair not in pairs]


def foreign_imports(root: Path, pairs: Pairs) -> list[str]:
    """Imports in a source that are neither stdlib nor a listed relative sibling."""
    siblings = {Path(source).stem for source, _ in pairs}
    problems: list[str] = []
    for source, _ in pairs:
        tree = ast.parse((root / source).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in sys.stdlib_module_names:
                        problems.append(f"{source}:{node.lineno} imports {top}")
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    top = (node.module or "").split(".")[0]
                    if top not in sys.stdlib_module_names:
                        problems.append(f"{source}:{node.lineno} imports {top}")
                else:
                    # `from .x import y` names a module; `from . import y` names
                    # the siblings directly.
                    named = (
                        [node.module] if node.module else [a.name for a in node.names]
                    )
                    if node.level != 1 or not all(n in siblings for n in named):
                        problems.append(
                            f"{source}:{node.lineno} relative import of "
                            f"{'.' * node.level}{node.module or ''}"
                        )
    return problems


def _hint(problems: list[str]) -> str:
    return "\n".join(problems) + f"\nre-sync with: {SYNC_COMMAND}"


# --- the real tree ----------------------------------------------------------


def test_the_table_is_non_trivial_and_every_source_exists() -> None:
    assert len(SHARED_MODULES) >= 5
    for source, _ in SHARED_MODULES:
        assert (REPO_ROOT / source).is_file(), source


def test_every_copy_is_byte_identical_to_its_source() -> None:
    problems = byte_drift(REPO_ROOT, SHARED_MODULES)
    assert not problems, _hint(problems)


def test_no_orphan_module_in_shared() -> None:
    assert (REPO_ROOT / SHARED_DIR / "__init__.py").is_file()
    found = orphans(REPO_ROOT, SHARED_MODULES)
    assert not found, _hint(found)


def test_sources_import_only_stdlib_and_listed_siblings() -> None:
    problems = foreign_imports(REPO_ROOT, SHARED_MODULES)
    assert not problems, _hint(problems)


def test_the_five_pinned_pairs_are_present_by_literal() -> None:
    absent = missing_literals(SHARED_MODULES)
    assert not absent, _hint([f"missing pair {p}" for p in absent])


def test_the_shared_marker_states_the_copies_are_never_edited_by_hand() -> None:
    marker = (REPO_ROOT / SHARED_DIR / "__init__.py").read_text(encoding="utf-8")
    assert "never edited by hand" in marker
    assert SYNC_COMMAND in marker


def test_the_copies_are_not_empty() -> None:
    for _, copy in SHARED_MODULES:
        assert (REPO_ROOT / copy).stat().st_size > 1000, copy


# --- positive controls: each check can fail --------------------------------


def _tree(tmp_path: Path) -> Path:
    for source, copy in SHARED_MODULES:
        (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / source).write_bytes((REPO_ROOT / source).read_bytes())
        (tmp_path / copy).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / copy).write_bytes((REPO_ROOT / copy).read_bytes())
    (tmp_path / SHARED_DIR / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


def test_a_clean_copy_of_the_tree_passes_every_check(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert byte_drift(root, SHARED_MODULES) == []
    assert orphans(root, SHARED_MODULES) == []
    assert foreign_imports(root, SHARED_MODULES) == []
    assert missing_literals(SHARED_MODULES) == []


def test_one_appended_byte_in_a_copy_is_drift(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    copy = SHARED_MODULES[1][1]
    with (root / copy).open("ab") as handle:
        handle.write(b"\n")
    assert byte_drift(root, SHARED_MODULES) == [
        f"{copy}: differs from {SHARED_MODULES[1][0]}"
    ]


def test_a_same_size_edit_is_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path)
    copy = SHARED_MODULES[0][1]
    original = (root / copy).read_bytes()
    flipped = bytes([original[0] ^ 1]) + original[1:]
    assert len(flipped) == len(original) and flipped != original
    (root / copy).write_bytes(flipped)
    assert byte_drift(root, SHARED_MODULES) == [
        f"{copy}: differs from {SHARED_MODULES[0][0]}"
    ]
    assert main(["--check"], root=root) == 1
    assert copy in capsys.readouterr().err


def test_a_deleted_copy_is_drift(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    copy = SHARED_MODULES[0][1]
    (root / copy).unlink()
    assert byte_drift(root, SHARED_MODULES) == [
        f"{copy}: missing (source {SHARED_MODULES[0][0]})"
    ]


def test_a_hand_written_module_in_shared_is_an_orphan(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / SHARED_DIR / "helpers.py").write_text("X = 1\n", encoding="utf-8")
    (root / SHARED_DIR / "sub").mkdir()
    (root / SHARED_DIR / "sub" / "__init__.py").write_text("", encoding="utf-8")
    (root / SHARED_DIR / "sub" / "deep.py").write_text("", encoding="utf-8")
    assert orphans(root, SHARED_MODULES) == [
        f"{SHARED_DIR}/helpers.py",
        f"{SHARED_DIR}/sub/__init__.py",
        f"{SHARED_DIR}/sub/deep.py",
    ]


def test_dropping_a_pair_from_the_table_fails_the_literal_check() -> None:
    for index, dropped in enumerate(SHARED_MODULES):
        if dropped not in PINNED_PAIRS:
            continue
        shrunk = SHARED_MODULES[:index] + SHARED_MODULES[index + 1 :]
        assert missing_literals(shrunk) == [dropped]
    # A table that only appends keeps the check green.
    appended = (*SHARED_MODULES, ("src/x.py", f"{SHARED_DIR}/x.py"))
    assert missing_literals(appended) == []


def test_dropping_a_pair_leaves_its_copy_an_orphan() -> None:
    shrunk = SHARED_MODULES[:1]
    assert orphans(REPO_ROOT, shrunk) == sorted(copy for _, copy in SHARED_MODULES[1:])


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("import yaml", "imports yaml"),
        ("import fitdocs.connectors", "imports fitdocs"),
        ("from fitdocs import x", "imports fitdocs"),
        ("from .other import x", "relative import of .other"),
        ("from .. import x", "relative import of .."),
        ("from ..relay_codes import x", "relative import of ..relay_codes"),
        ("from . import other", "relative import of ."),
        ("import enum", None),
        ("from .relay_codes import x", None),
        ("from . import relay_codes", None),
    ],
)
def test_foreign_imports_are_rejected(
    tmp_path: Path, line: str, expected: str | None
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "relay_codes.py").write_text(line + "\n", encoding="utf-8")
    found = foreign_imports(tmp_path, (("src/relay_codes.py", "x/relay_codes.py"),))
    if expected is None:
        assert found == []
    else:
        assert found == [f"src/relay_codes.py:1 {expected}"]


# --- the sync script --------------------------------------------------------


def _source_only_tree(tmp_path: Path) -> Path:
    for source, _ in SHARED_MODULES:
        (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / source).write_bytes((REPO_ROOT / source).read_bytes())
    return tmp_path


def test_write_mode_creates_byte_identical_copies(tmp_path: Path) -> None:
    root = _source_only_tree(tmp_path)
    assert not (root / SHARED_DIR).exists()
    assert main([], root=root) == 0
    for source, copy in SHARED_MODULES:
        assert (root / copy).read_bytes() == (root / source).read_bytes()
    assert drifted(root) == []


def test_write_mode_repairs_a_drifted_copy(tmp_path: Path) -> None:
    root = _source_only_tree(tmp_path)
    assert main([], root=root) == 0
    copy = root / SHARED_MODULES[0][1]
    good = copy.read_bytes()
    copy.write_bytes(good + b"# hand edit\n")
    assert main([], root=root) == 0
    assert copy.read_bytes() == good


def test_check_mode_writes_nothing_and_lists_each_drifted_pair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _source_only_tree(tmp_path)
    assert main(["--check"], root=root) == 1
    err = capsys.readouterr().err
    assert not (root / SHARED_DIR).exists()
    for _, copy in SHARED_MODULES:
        assert copy in err
    assert SYNC_COMMAND in err


def test_check_mode_lists_only_the_drifted_pair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _source_only_tree(tmp_path)
    assert main([], root=root) == 0
    capsys.readouterr()
    assert main(["--check"], root=root) == 0
    assert capsys.readouterr().err == ""
    drifted_copy = SHARED_MODULES[1][1]
    with (root / drifted_copy).open("ab") as handle:
        handle.write(b"x")
    before = (root / drifted_copy).read_bytes()
    assert main(["--check"], root=root) == 1
    err = capsys.readouterr().err
    assert drifted_copy in err
    assert SHARED_MODULES[0][1] not in err
    assert (root / drifted_copy).read_bytes() == before


def test_a_missing_source_exits_2(tmp_path: Path) -> None:
    assert main([], root=tmp_path) == 2
    assert main(["--check"], root=tmp_path) == 2


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # -I: ignore the environment and cwd; -B: write no bytecode under src/.
    return subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_script_runs_as_a_program_over_the_real_tree() -> None:
    result = _run("--check")
    assert (result.returncode, result.stderr) == (0, "")
    assert f"{len(SHARED_MODULES)} shared copies in sync" in result.stdout


def test_the_script_as_a_program_exits_1_on_drift(tmp_path: Path) -> None:
    root = _source_only_tree(tmp_path)
    result = _run("--check", "--root", str(root))
    assert result.returncode == 1
    assert SHARED_MODULES[0][1] in result.stderr
    assert not (root / SHARED_DIR).exists()
    written = _run("--root", str(root))
    assert written.returncode == 0
    assert _run("--check", "--root", str(root)).returncode == 0
