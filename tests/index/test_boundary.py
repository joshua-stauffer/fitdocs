"""Lazy DuckDB import and store-SQL boundary guards for task 4.1."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_SOURCE_ROOT = _REPO_ROOT / "src" / "fitdocs"
_STORE_PATH = _SOURCE_ROOT / "index" / "store.py"
_FORBIDDEN_SQL_TOKENS = (
    "INSTALL ",
    "LOAD ",
    "ATTACH",
    "COPY ",
    "EXPORT ",
    "http://",
    "https://",
    "PRAGMA",
)


def _duckdb_imports(paths: tuple[Path, ...]) -> list[tuple[Path, int]]:
    violations: list[tuple[Path, int]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        importlib_aliases: set[str] = set()
        import_module_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "importlib":
                        importlib_aliases.add(alias.asname or "importlib")
            elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_aliases.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Import)
                and any(
                    alias.name == "duckdb" or alias.name.startswith("duckdb.")
                    for alias in node.names
                )
                or isinstance(node, ast.ImportFrom)
                and node.module
                and (node.module == "duckdb" or node.module.startswith("duckdb."))
            ):
                violations.append((path, node.lineno))
            elif isinstance(node, ast.Call):
                target = node.func
                dynamic_duckdb = (
                    (isinstance(target, ast.Name) and target.id == "__import__")
                    or (
                        isinstance(target, ast.Name)
                        and target.id in import_module_aliases
                    )
                    or (
                        isinstance(target, ast.Attribute)
                        and target.attr == "import_module"
                        and isinstance(target.value, ast.Name)
                        and target.value.id in importlib_aliases
                    )
                )
                import_name = (
                    node.args[0]
                    if node.args
                    else next(
                        (
                            keyword.value
                            for keyword in node.keywords
                            if keyword.arg == "name"
                        ),
                        None,
                    )
                )
                if (
                    dynamic_duckdb
                    and isinstance(import_name, ast.Constant)
                    and isinstance(import_name.value, str)
                    and (
                        import_name.value == "duckdb"
                        or import_name.value.startswith("duckdb.")
                    )
                ):
                    violations.append((path, node.lineno))
    return violations


def _duckdb_import_contexts(path: Path) -> set[tuple[str | None, bool]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents: dict[ast.AST, ast.AST] = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    contexts: set[tuple[str | None, bool]] = set()
    for node in ast.walk(tree):
        imports_duckdb = (
            isinstance(node, ast.Import)
            and any(alias.name == "duckdb" for alias in node.names)
        ) or (isinstance(node, ast.ImportFrom) and node.module == "duckdb")
        if not imports_duckdb:
            continue
        function_name: str | None = None
        under_type_checking = False
        ancestor = parents.get(node)
        while ancestor is not None:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_name = ancestor.name
            elif (
                isinstance(ancestor, ast.If)
                and isinstance(ancestor.test, ast.Name)
                and ancestor.test.id == "TYPE_CHECKING"
            ):
                under_type_checking = True
            ancestor = parents.get(ancestor)
        contexts.add((function_name, under_type_checking))
    return contexts


def _string_constants_without_docstrings(source: str) -> list[str]:
    tree = ast.parse(source)
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
        ):
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstring_nodes.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
    ]


def _sql_guard_violations(source: str) -> list[str]:
    violations: list[str] = []
    for value in _string_constants_without_docstrings(source):
        if any(token in value for token in _FORBIDDEN_SQL_TOKENS) or re.match(
            r"^\s*SET\b", value
        ):
            violations.append(value)
    return violations


def test_only_index_store_imports_duckdb_and_scan_reaches_repository() -> None:
    files = tuple(_SOURCE_ROOT.rglob("*.py"))
    assert len(files) > 100
    assert _STORE_PATH in files
    violations = _duckdb_imports(files)
    assert all(path == _STORE_PATH for path, _ in violations)
    assert len(violations) == 2
    assert _duckdb_import_contexts(_STORE_PATH) == {
        (None, True),
        ("_connect", False),
    }


@pytest.mark.parametrize(
    "source",
    [
        "import duckdb\n",
        "import duckdb as database\n",
        "import duckdb.engine as database_engine\n",
        "from duckdb import connect as open_db\n",
        "from duckdb.engine import DuckDBPyConnection\n",
        "from duckdb.engine import DuckDBPyConnection as connection_type\n",
        "import importlib as loader\nloader.import_module('duckdb')\n",
        "import importlib as loader\nloader.import_module('duckdb.engine')\n",
        "from importlib import import_module as load\nload('duckdb')\n",
        "from importlib import import_module as load\nload('duckdb.engine')\n",
        "import importlib as loader\nloader.import_module(name='duckdb')\n",
        "import importlib as loader\nloader.import_module(name='duckdb.engine')\n",
        "from importlib import import_module as load\nload(name='duckdb')\n",
        "from importlib import import_module as load\nload(name='duckdb.engine')\n",
        "__import__('duckdb')\n",
        "__import__('duckdb.engine')\n",
        "__import__(name='duckdb')\n",
        "__import__(name='duckdb.engine')\n",
    ],
)
def test_duckdb_import_guard_detects_each_import_form(
    tmp_path: Path, source: str
) -> None:
    synthetic = tmp_path / "synthetic_import.py"
    synthetic.write_text(source, encoding="utf-8")
    found = _duckdb_imports((synthetic,))
    assert len(found) == 1
    assert found[0][0] == synthetic


def test_store_sql_guard_scans_reachable_setting_constant_but_not_docstrings() -> None:
    source = _STORE_PATH.read_text(encoding="utf-8")
    constants = _string_constants_without_docstrings(source)
    assert "autoinstall_known_extensions" in constants
    assert _sql_guard_violations(source) == []


@pytest.mark.parametrize(
    "constant",
    [
        '"INSTALL httpfs"',
        '"https://x"',
        '"SET autoinstall_known_extensions = true"',
    ],
)
def test_store_sql_guard_flags_synthetic_forbidden_constants(constant: str) -> None:
    source = f"VALUE = {constant}\n"
    assert _sql_guard_violations(source) == [ast.literal_eval(constant)]


@pytest.mark.parametrize(
    "token",
    [
        "INSTALL ",
        "LOAD ",
        "ATTACH",
        "COPY ",
        "EXPORT ",
        "http://",
        "https://",
        "PRAGMA",
    ],
)
def test_store_sql_guard_covers_every_forbidden_token(token: str) -> None:
    source = f"VALUE = {token!r}\n"
    assert token in _FORBIDDEN_SQL_TOKENS
    assert _sql_guard_violations(source) == [token]


def test_store_sql_guard_excludes_real_docstrings_but_keeps_nested_literals() -> None:
    docstrings = """
"INSTALL module docstring"
class Example:
    "LOAD class docstring"
def regular():
    "ATTACH function docstring"
async def asynchronous():
    "COPY async function docstring"
    return "runtime value"
"""
    assert _sql_guard_violations(docstrings) == []

    nested = """
if True:
    "INSTALL branch-first string"
VALUES = ["LOAD nested list string"]
"""
    assert _sql_guard_violations(nested) == [
        "INSTALL branch-first string",
        "LOAD nested list string",
    ]


def test_store_sql_guard_is_case_sensitive_and_allows_nonleading_set() -> None:
    source = """
LOWER = "install httpfs load ext attach copy export HTTP://x pragma"
SPACED_SET = "   SET enabled = true"
SETUP_WORD = "SETUP enabled = true"
UPDATE = "UPDATE index_meta SET value = 1"
"""
    assert _sql_guard_violations(source) == ["   SET enabled = true"]


def test_store_sql_guard_allows_ordinary_update_set() -> None:
    source = 'VALUE = "UPDATE index_meta SET athlete_fingerprint = $1"\n'
    assert _sql_guard_violations(source) == []


def test_importing_cli_index_modules_and_discovering_plugins_stays_lazy(
    tmp_path: Path,
) -> None:
    script = """
import importlib
import pkgutil
import sys
from pathlib import Path
import fitdocs.cli
import fitdocs.index
modules = tuple(
    pkgutil.walk_packages(fitdocs.index.__path__, fitdocs.index.__name__ + '.')
)
assert any(item.name == 'fitdocs.index.store' for item in modules)
for item in modules:
    importlib.import_module(item.name)
from fitdocs import plugins
from fitdocs.plugins import DEFAULT_PLUGIN_SETTINGS
plugins.discover(Path(sys.argv[1]), DEFAULT_PLUGIN_SETTINGS)
assert 'duckdb' not in sys.modules
print('duckdb-loaded', 'duckdb' in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "synthetic-data-root")],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_REPO_ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "duckdb-loaded False"
