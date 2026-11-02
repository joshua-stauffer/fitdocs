"""The relay boundary guard: which modules may import what (RelayBoundaryGuard)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "fitdocs_relay"

# Top-level import name -> the only relay modules (dotted, relative to the
# package) allowed to import it. An empty set forbids it everywhere.
THIRD_PARTY_PLACEMENT: dict[str, frozenset[str]] = {
    "fitdocs": frozenset(),
    "sqlite3": frozenset({"storage.sqlite"}),
    "psycopg": frozenset({"storage.postgres"}),
    "psycopg_pool": frozenset({"storage.postgres"}),
    "starlette": frozenset({"answers", "routes", "app", "seam", "serve"}),
    "uvicorn": frozenset({"serve"}),
    "cryptography": frozenset({"crypto"}),
}

SHARED_PACKAGE = "shared"


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> list[tuple[int, str | None, int]]:
    """Every import in `path`: (line, top-level name, or None if relative, level)."""
    found: list[tuple[int, str | None, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, a.name.split(".")[0], 0) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append((node.lineno, None, node.level))
            else:
                assert node.module is not None
                found.append((node.lineno, node.module.split(".")[0], 0))
    return found


def _sources(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def check_placement(root: Path) -> tuple[list[str], int]:
    """Placement violations under `root`, and how many files were scanned."""
    problems: list[str] = []
    files = _sources(root)
    for path in files:
        module = _module_name(root, path)
        for line, top, level in _imports(path):
            if top is None or level:
                continue
            allowed = THIRD_PARTY_PLACEMENT.get(top)
            if allowed is not None and module not in allowed:
                problems.append(f"{module}:{line} imports {top}")
    return problems, len(files)


def check_shared(root: Path) -> tuple[list[str], int]:
    """Violations of the shared-copy rule: stdlib and relative siblings only."""
    shared = root / SHARED_PACKAGE
    problems: list[str] = []
    files = _sources(shared) if shared.is_dir() else []
    for path in files:
        module = _module_name(root, path)
        for line, top, level in _imports(path):
            if top is None:
                if level != 1:
                    problems.append(
                        f"{module}:{line} relative import above its siblings"
                    )
            elif top not in sys.stdlib_module_names:
                problems.append(f"{module}:{line} imports {top}")
    return problems, len(files)


def _write(root: Path, rel: str, source: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


# --- the real tree ----------------------------------------------------------


def test_placement_rules_hold_over_the_package() -> None:
    problems, scanned = check_placement(PACKAGE_ROOT)
    assert scanned, "the walk is looking at the wrong directory"
    assert problems == []


def test_shared_copies_import_only_stdlib_and_siblings() -> None:
    problems, scanned = check_shared(PACKAGE_ROOT)
    assert problems == []
    # The literal count of the files in shared/: __init__.py plus the five
    # copies relay-server and strava-publish pin. Each later spec that appends
    # a pair to scripts/sync_relay_shared.py adds one file here, so that change
    # must raise this number in the same commit.
    assert scanned == 6
    assert sorted(p.name for p in (PACKAGE_ROOT / SHARED_PACKAGE).glob("*.py")) == [
        "__init__.py",
        "outcomes.py",
        "relay_codes.py",
        "relay_envelope.py",
        "relay_targets.py",
        "strict.py",
    ]


# --- positive controls: each rule can fail ---------------------------------


@pytest.mark.parametrize(
    ("module", "source", "expected"),
    [
        ("identity.py", "import fitdocs\n", "identity:1 imports fitdocs"),
        (
            "identity.py",
            "from fitdocs.connectors import x\n",
            "identity:1 imports fitdocs",
        ),
        (
            "storage/sqlite.py",
            "import fitdocs.cli\n",
            "storage.sqlite:1 imports fitdocs",
        ),
        ("identity.py", "import sqlite3\n", "identity:1 imports sqlite3"),
        (
            "storage/postgres.py",
            "import sqlite3\n",
            "storage.postgres:1 imports sqlite3",
        ),
        ("identity.py", "import psycopg\n", "identity:1 imports psycopg"),
        (
            "storage/sqlite.py",
            "from psycopg import sql\n",
            "storage.sqlite:1 imports psycopg",
        ),
        (
            "storage/sqlite.py",
            "import psycopg_pool\n",
            "storage.sqlite:1 imports psycopg_pool",
        ),
        ("storage/__init__.py", "import sqlite3\n", "storage:1 imports sqlite3"),
        ("identity.py", "import starlette.routing\n", "identity:1 imports starlette"),
        (
            "storage/sqlite.py",
            "from starlette import status\n",
            "storage.sqlite:1 imports starlette",
        ),
        ("app.py", "import uvicorn\n", "app:1 imports uvicorn"),
        ("identity.py", "import cryptography\n", "identity:1 imports cryptography"),
        (
            "storage/sqlite.py",
            "from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n",
            "storage.sqlite:1 imports cryptography",
        ),
        ("cli.py", "import uvicorn\n", "cli:1 imports uvicorn"),
        ("cli.py", "x = 1\nimport starlette\n", "cli:2 imports starlette"),
        (
            "storage/__init__.py",
            "def open_storage():\n    import psycopg\n",
            "storage:2 imports psycopg",
        ),
        (
            "identity.py",
            "try:\n    import sqlite3\nexcept ImportError:\n    pass\n",
            "identity:2 imports sqlite3",
        ),
    ],
)
def test_placement_rules_reject_a_forbidden_import(
    tmp_path: Path, module: str, source: str, expected: str
) -> None:
    _write(tmp_path, module, source)
    problems, scanned = check_placement(tmp_path)
    assert scanned == 1
    assert problems == [expected]


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("storage/sqlite.py", "import sqlite3\n"),
        (
            "storage/postgres.py",
            "import psycopg\nfrom psycopg_pool import ConnectionPool\n",
        ),
        ("answers.py", "import starlette.responses\n"),
        ("routes.py", "from starlette.routing import Route\n"),
        ("app.py", "from starlette.applications import Starlette\n"),
        ("seam.py", "import starlette\n"),
        ("serve.py", "import starlette\nimport uvicorn\n"),
        ("crypto.py", "from cryptography.exceptions import InvalidTag\n"),
        (
            "identity.py",
            "import hashlib\nfrom . import contract\nfrom .shared import relay_codes\n",
        ),
    ],
)
def test_placement_rules_admit_the_allowed_homes(
    tmp_path: Path, module: str, source: str
) -> None:
    _write(tmp_path, module, source)
    problems, scanned = check_placement(tmp_path)
    assert scanned == 1
    assert problems == []


def test_the_third_party_table_names_exactly_the_design_placements() -> None:
    design = {
        "fitdocs": frozenset(),
        "sqlite3": frozenset({"storage.sqlite"}),
        "psycopg": frozenset({"storage.postgres"}),
        "psycopg_pool": frozenset({"storage.postgres"}),
        "starlette": frozenset({"answers", "routes", "app", "seam", "serve"}),
        "uvicorn": frozenset({"serve"}),
        "cryptography": frozenset({"crypto"}),
    }
    assert design == THIRD_PARTY_PLACEMENT


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import fitdocs\n", ["shared.relay_codes:1 imports fitdocs"]),
        ("import starlette\n", ["shared.relay_codes:1 imports starlette"]),
        ("from yaml import safe_load\n", ["shared.relay_codes:1 imports yaml"]),
        (
            "from .. import contract\n",
            ["shared.relay_codes:1 relative import above its siblings"],
        ),
        (
            "from ..config import x\n",
            ["shared.relay_codes:1 relative import above its siblings"],
        ),
        ("import enum\nimport json as j\n", []),
        ("from __future__ import annotations\nfrom dataclasses import dataclass\n", []),
        (
            "import fitdocs_relay.config\n",
            ["shared.relay_codes:1 imports fitdocs_relay"],
        ),
        (
            "from fitdocs_relay.shared import relay_envelope\n",
            ["shared.relay_codes:1 imports fitdocs_relay"],
        ),
        (
            "def f():\n    import yaml\n",
            ["shared.relay_codes:2 imports yaml"],
        ),
        (
            "try:\n    from ..config import x\nexcept ImportError:\n    pass\n",
            ["shared.relay_codes:2 relative import above its siblings"],
        ),
        ("from . import relay_envelope\nfrom .relay_envelope import X\n", []),
    ],
)
def test_shared_rule_rejects_non_stdlib_and_non_sibling_imports(
    tmp_path: Path, source: str, expected: list[str]
) -> None:
    _write(tmp_path, "shared/relay_codes.py", source)
    _write(
        tmp_path, "identity.py", "import yaml\n"
    )  # outside shared: ignored by this rule
    problems, scanned = check_shared(tmp_path)
    assert scanned == 1
    assert problems == expected


# --- the walks refuse to pass vacuously ------------------------------------


def test_an_empty_directory_scans_nothing(tmp_path: Path) -> None:
    # check_placement reports a zero count the real-tree placement test rejects.
    assert check_placement(tmp_path) == ([], 0)
    assert check_shared(tmp_path) == ([], 0)


def test_the_real_package_root_holds_python_sources() -> None:
    for name in ("__init__.py", "cli.py", "__main__.py"):
        assert (PACKAGE_ROOT / name).is_file(), name
    assert _module_name(PACKAGE_ROOT, PACKAGE_ROOT / "cli.py") == "cli"
    assert _module_name(PACKAGE_ROOT, PACKAGE_ROOT / "__init__.py") == ""
