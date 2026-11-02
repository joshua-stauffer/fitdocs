"""The relay boundary guard: which modules may import what (RelayBoundaryGuard)."""

from __future__ import annotations

import ast
import sys
from collections.abc import Mapping
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

# Dotted stdlib modules that only one relay module may import. The spellings
# caught are `import urllib.request`, `from urllib import request` and
# `from urllib.request import X` (likewise for http.client), at any nesting
# depth in a file; `importlib` and `__import__` calls are not looked for.
# Other `urllib` and `http` submodules are not restricted.
QUALIFIED_PLACEMENT: dict[str, frozenset[str]] = {
    "urllib.request": frozenset({"outbound"}),
    "http.client": frozenset({"outbound"}),
}

SHARED_PACKAGE = "shared"

# Relay modules that are standard-library-only leaves at run time. Each maps to
# the relay modules (dotted, absolute) it may also import at run time. Imports
# nested under `if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:` (the branch
# only, not its `else`) may name the standard library or `fitdocs_relay.*`
# (relative imports included); any other package there is refused.
# Run-time relative imports are refused, so the allow-listed module is spelled
# absolutely.
STDLIB_ONLY_ALLOWED: dict[str, frozenset[str]] = {
    "strava.pages": frozenset({"fitdocs_relay.strava.policy"}),
    "strava.policy": frozenset(),
}


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


def _qualified_imports(path: Path) -> list[tuple[int, str]]:
    """Every absolute import in `path` as (line, dotted module imported)."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            assert node.module is not None
            found.append((node.lineno, node.module))
            found.extend((node.lineno, f"{node.module}.{a.name}") for a in node.names)
    return found


def check_qualified(root: Path) -> tuple[list[str], int]:
    """Violations of QUALIFIED_PLACEMENT under `root`, and files scanned."""
    problems: list[str] = []
    files = _sources(root)
    for path in files:
        module = _module_name(root, path)
        for line, dotted in _qualified_imports(path):
            for guarded, allowed in QUALIFIED_PLACEMENT.items():
                if dotted == guarded and module not in allowed:
                    problems.append(f"{module}:{line} imports {guarded}")
    return sorted(set(problems)), len(files)


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


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )


def _classified_imports(
    node: ast.AST, in_type_checking: bool = False
) -> list[tuple[ast.stmt, bool]]:
    """(import, inside a TYPE_CHECKING branch) for every import under `node`."""
    found: list[tuple[ast.stmt, bool]] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.Import | ast.ImportFrom):
            found.append((child, in_type_checking))
        elif isinstance(child, ast.If) and _is_type_checking(child.test):
            found.extend(_branch_imports(child.body, True))
            found.extend(_branch_imports(child.orelse, in_type_checking))
        else:
            found.extend(_classified_imports(child, in_type_checking))
    return found


def _branch_imports(
    body: list[ast.stmt], in_type_checking: bool
) -> list[tuple[ast.stmt, bool]]:
    return _classified_imports(ast.Module(body=body, type_ignores=[]), in_type_checking)


def check_stdlib_only(
    root: Path, allowed: Mapping[str, frozenset[str]] = STDLIB_ONLY_ALLOWED
) -> tuple[list[str], int]:
    """Run-time imports in `allowed`'s modules beyond the stdlib and the allow-list."""
    scanned = 0
    messages: list[str] = []
    for path in _sources(root):
        module = _module_name(root, path)
        if module not in allowed:
            continue
        scanned += 1
        found: list[tuple[int, str]] = []
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node, in_type_checking in _classified_imports(tree):
            if in_type_checking:
                # Typing-only imports may name the standard library or the relay.
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom) and not node.level
                    else []
                )
                for name in names:
                    top = name.split(".")[0]
                    if top not in sys.stdlib_module_names and top != "fitdocs_relay":
                        found.append(
                            (node.lineno, f"imports {top} under TYPE_CHECKING")
                        )
                continue
            if isinstance(node, ast.ImportFrom) and node.level:
                found.append((node.lineno, "a run-time relative import"))
                continue
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            else:
                assert isinstance(node, ast.ImportFrom) and node.module is not None
                targets = [
                    node.module
                    if node.module in allowed[module]
                    else f"{node.module}.{a.name}"
                    for a in node.names
                ]
            for dotted in targets:
                top = dotted.split(".")[0]
                if top in sys.stdlib_module_names or dotted in allowed[module]:
                    continue
                shown = dotted if top == "fitdocs_relay" else top
                found.append((node.lineno, f"imports {shown}"))
        messages.extend(f"{module}:{line} {what}" for line, what in sorted(found))
    return messages, scanned


def _write(root: Path, rel: str, source: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


# --- the real tree ----------------------------------------------------------


def test_placement_rules_hold_over_the_package() -> None:
    problems, scanned = check_placement(PACKAGE_ROOT)
    assert scanned, "the walk is looking at the wrong directory"
    assert problems == []


def test_urllib_request_and_http_client_live_only_in_outbound() -> None:
    problems, scanned = check_qualified(PACKAGE_ROOT)
    assert scanned, "the walk is looking at the wrong directory"
    assert problems == []
    imported = {
        dotted for _, dotted in _qualified_imports(PACKAGE_ROOT / "outbound.py")
    }
    assert set(QUALIFIED_PLACEMENT) <= imported


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


def test_pages_and_policy_are_standard_library_leaves_at_run_time() -> None:
    problems, scanned = check_stdlib_only(PACKAGE_ROOT)
    assert scanned == len(STDLIB_ONLY_ALLOWED) == 2
    assert problems == []


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


@pytest.mark.parametrize(
    ("module", "source", "expected"),
    [
        (
            "identity.py",
            "import urllib.request\n",
            ["identity:1 imports urllib.request"],
        ),
        (
            "identity.py",
            "from urllib import request\n",
            ["identity:1 imports urllib.request"],
        ),
        (
            "storage/sqlite.py",
            "from urllib.request import urlopen\n",
            ["storage.sqlite:1 imports urllib.request"],
        ),
        ("identity.py", "import http.client\n", ["identity:1 imports http.client"]),
        (
            "identity.py",
            "from http import client\n",
            ["identity:1 imports http.client"],
        ),
        (
            "cli.py",
            "def f():\n    from http.client import HTTPSConnection\n",
            ["cli:2 imports http.client"],
        ),
        ("outbound.py", "import urllib.request\nimport http.client\n", []),
        ("outbound.py", "from urllib import request\nfrom http import client\n", []),
        ("config.py", "from urllib.parse import urlsplit\nimport urllib.error\n", []),
        ("serve.py", "from http import HTTPStatus\n", []),
    ],
)
def test_qualified_placement_rejects_and_admits(
    tmp_path: Path, module: str, source: str, expected: list[str]
) -> None:
    _write(tmp_path, module, source)
    problems, scanned = check_qualified(tmp_path)
    assert scanned == 1
    assert problems == expected


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


@pytest.mark.parametrize(
    ("module", "source", "expected"),
    [
        ("strava.pages", "import yaml\n", ["strava.pages:1 imports yaml"]),
        (
            "strava.pages",
            "from starlette import status\n",
            ["strava.pages:1 imports starlette"],
        ),
        (
            "strava.pages",
            "def f():\n    import psycopg\n",
            ["strava.pages:2 imports psycopg"],
        ),
        (
            "strava.pages",
            "from fitdocs_relay.strava.config import LinkSetting\n",
            ["strava.pages:1 imports fitdocs_relay.strava.config.LinkSetting"],
        ),
        (
            "strava.pages",
            "from fitdocs_relay.strava import config\n",
            ["strava.pages:1 imports fitdocs_relay.strava.config"],
        ),
        (
            "strava.pages",
            "from . import config\n",
            ["strava.pages:1 a run-time relative import"],
        ),
        (
            "strava.pages",
            "from .policy import consent_text\n",
            ["strava.pages:1 a run-time relative import"],
        ),
        (
            "strava.pages",
            "import fitdocs_relay.crypto\n",
            ["strava.pages:1 imports fitdocs_relay.crypto"],
        ),
        (
            "strava.pages",
            "from fitdocs_relay import crypto\n",
            ["strava.pages:1 imports fitdocs_relay.crypto"],
        ),
        (
            "strava.pages",
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    pass\nelse:\n"
            "    from fitdocs_relay.strava.config import LinkSetting\n",
            ["strava.pages:5 imports fitdocs_relay.strava.config.LinkSetting"],
        ),
        (
            "strava.pages",
            "from typing import TYPE_CHECKING\n"
            "if not TYPE_CHECKING:\n"
            "    from fitdocs_relay.strava.config import LinkSetting\n",
            ["strava.pages:3 imports fitdocs_relay.strava.config.LinkSetting"],
        ),
        (
            "strava.pages",
            "if DEBUG:\n    import yaml\n",
            ["strava.pages:2 imports yaml"],
        ),
        (
            "strava.pages",
            "import typing\nif typing.DEBUG:\n    import yaml\n",
            ["strava.pages:3 imports yaml"],
        ),
        (
            "strava.pages",
            "import os\nif os.TYPE_CHECKING:\n    import yaml\n",
            ["strava.pages:3 imports yaml"],
        ),
        (
            "strava.pages",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import yaml\n",
            ["strava.pages:3 imports yaml under TYPE_CHECKING"],
        ),
        (
            "strava.pages",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            "    from yaml import safe_load\n",
            ["strava.pages:3 imports yaml under TYPE_CHECKING"],
        ),
        (
            "strava.policy",
            "from fitdocs_relay.strava.policy import consent_text\n",
            ["strava.policy:1 imports fitdocs_relay.strava.policy.consent_text"],
        ),
        (
            "strava.policy",
            "from fitdocs_relay.strava import policy\n",
            ["strava.policy:1 imports fitdocs_relay.strava.policy"],
        ),
    ],
)
def test_stdlib_only_rule_rejects(
    tmp_path: Path, module: str, source: str, expected: list[str]
) -> None:
    _write(tmp_path, module.replace(".", "/") + ".py", source)
    _write(tmp_path, "identity.py", "import yaml\n")  # not a listed module
    problems, scanned = check_stdlib_only(tmp_path)
    assert scanned == 1
    assert problems == expected


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("strava.pages", "import html\nfrom dataclasses import dataclass\n"),
        (
            "strava.pages",
            "from fitdocs_relay.strava.policy import consent_text\n",
        ),
        ("strava.pages", "from fitdocs_relay.strava import policy\n"),
        ("strava.pages", "import fitdocs_relay.strava.policy\n"),
        (
            "strava.pages",
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from fitdocs_relay.strava.config import LinkSetting\n",
        ),
        (
            "strava.policy",
            "import typing\nif typing.TYPE_CHECKING:\n"
            "    from fitdocs_relay.strava.config import LinkSetting\n"
            "    from . import config\n",
        ),
    ],
)
def test_stdlib_only_rule_admits(tmp_path: Path, module: str, source: str) -> None:
    _write(tmp_path, module.replace(".", "/") + ".py", source)
    problems, scanned = check_stdlib_only(tmp_path)
    assert scanned == 1
    assert problems == []


def test_stdlib_only_rule_scans_nothing_in_an_empty_tree(tmp_path: Path) -> None:
    assert check_stdlib_only(tmp_path) == ([], 0)
