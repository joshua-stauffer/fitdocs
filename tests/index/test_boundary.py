"""Lazy DuckDB import and store-SQL boundary guards for task 4.1."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.index.store import open_index, read_bookkeeping
from tests.fixtures import builder

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
_INDEX_IMPORTERS = frozenset(
    {
        "fitdocs.cli",
        "fitdocs.query.statement",  # Created by analytics-query task 3.1.
        "fitdocs.query.sandbox",  # Created by analytics-query task 2.2.
        "fitdocs.query.freshness",  # Created by analytics-query task 4.1.
        "fitdocs.query.schemaview",  # Created by analytics-query task 4.2.
        "fitdocs.query.command",  # Created by analytics-query task 5.2.
    }
)
_REQUIRED_INDEX_IMPORTERS = frozenset({"fitdocs.cli"})


def _imports_index_runtime(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fitdocs.index" or alias.name.startswith(
                    "fitdocs.index."
                ):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "fitdocs.index" or node.module.startswith(
                "fitdocs.index."
            ):
                return True
            if node.module == "fitdocs" and any(
                alias.name == "index" for alias in node.names
            ):
                return True
    return False


def _unlisted_index_importers(sources: dict[str, str]) -> set[str]:
    return {
        module
        for module, source in sources.items()
        if _imports_index_runtime(source) and module not in _INDEX_IMPORTERS
    }


def _source_module(path: Path) -> str:
    relative = path.relative_to(_REPO_ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _external_index_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@dataclass(frozen=True)
class _UntouchedCommandObservation:
    outputs: dict[str, str]
    duckdb_loaded: dict[str, bool]
    cache_before: dict[str, tuple[int, int, str]]
    cache_expected: dict[str, tuple[int, int, str]]
    sentinel_expected: dict[str, tuple[int, int, str]]
    cache_after: dict[str, tuple[int, int, str]]


@pytest.fixture(scope="module")
def _untouched_command_observation(
    tmp_path_factory: pytest.TempPathFactory,
) -> _UntouchedCommandObservation:
    sandbox = tmp_path_factory.mktemp("untouched-index-commands")
    source = sandbox / "source"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    root = sandbox / "data"
    root.mkdir()
    (root / "fitdocs.toml").write_text(
        "[connectors.folder-src]\n"
        'connector = "folder"\n'
        f'path = "{source.as_posix()}"\n',
        encoding="utf-8",
    )
    index_base = sandbox / "index-cache"
    synthetic_home = sandbox / "home"
    synthetic_home.mkdir()
    environment = {
        **os.environ,
        "FITDOCS_INDEX_DIR": str(index_base),
        "HOME": str(synthetic_home),
        "XDG_CACHE_HOME": str(sandbox / "xdg-cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    with patch.dict(os.environ, environment, clear=True):
        synced = CliRunner().invoke(app, ["sync", str(source), "--out", str(root)])
        assert synced.exit_code == 0, synced.output
        built = CliRunner().invoke(app, ["index", "--out", str(root)])
        assert built.exit_code == 0, built.output

    databases = list(index_base.rglob("index.duckdb"))
    assert len(databases) == 1
    database = databases[0]
    assert database.stat().st_size > 0
    with open_index(database, read_only=True) as connection:
        indexed_before_edit = read_bookkeeping(connection)
    assert indexed_before_edit is not None
    assert len(indexed_before_edit.pages) == 1
    indexed_page = next(iter(indexed_before_edit.pages.values()))
    assert indexed_page.path.startswith("workouts/")
    pages = [
        path for path in (root / "workouts").glob("*.md") if path.name != "AGENTS.md"
    ]
    assert len(pages) == 1
    page = pages[0]
    original = page.read_bytes()
    edited = page.read_text(encoding="utf-8").replace(
        "title:", "effort: race\ntitle:", 1
    )
    page.write_text(edited, encoding="utf-8")
    assert page.read_bytes() != original

    sentinel_one = database.parent / "snapshot-alpha.bin"
    sentinel_two = database.parent / "snapshot-beta.bin"
    sentinel_one_bytes = b"alpha-snapshot"
    sentinel_two_bytes = b"beta-snapshot-content"
    sentinel_one.write_bytes(sentinel_one_bytes)
    sentinel_two.write_bytes(sentinel_two_bytes)
    sentinel_one_mtime = 1_700_000_000_000_000_001
    sentinel_two_mtime = 1_700_000_005_000_000_002
    os.utime(sentinel_one, ns=(sentinel_one_mtime, sentinel_one_mtime))
    os.utime(sentinel_two, ns=(sentinel_two_mtime, sentinel_two_mtime))
    before = _external_index_snapshot(index_base)
    actual_files = tuple(
        sorted(path for path in index_base.rglob("*") if path.is_file())
    )
    expected_before = {
        path.relative_to(index_base).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in actual_files
    }
    assert set(before) == {
        path.relative_to(index_base).as_posix() for path in actual_files
    }
    sentinel_expected = {
        sentinel_one.relative_to(index_base).as_posix(): (
            len(sentinel_one_bytes),
            sentinel_one_mtime,
            hashlib.sha256(sentinel_one_bytes).hexdigest(),
        ),
        sentinel_two.relative_to(index_base).as_posix(): (
            len(sentinel_two_bytes),
            sentinel_two_mtime,
            hashlib.sha256(sentinel_two_bytes).hexdigest(),
        ),
    }
    assert len(before) >= 3

    invocations = {
        "check": ["check", "--out", str(root)],
        "history": ["history", "--out", str(root)],
        "plan": ["plan", "--out", str(root)],
        "derive-benchmarks": ["derive-benchmarks", "--out", str(root)],
        "plugins": ["plugins", "--out", str(root)],
        "skill": ["skill"],
        "version": ["--version"],
        "connect": ["connect", "folder-src", "--out", str(root)],
        "pull": ["pull", "--out", str(root)],
    }
    # The independent populated-row pin above ensures this is not only a
    # schema/meta preservation check.
    with open_index(database, read_only=True) as connection:
        indexed = read_bookkeeping(connection)
    assert indexed is not None
    assert len(indexed.pages) == 1
    assert next(iter(indexed.pages.values())).path.startswith("workouts/")
    child = (
        "import json, sys\n"
        "from typer.testing import CliRunner\n"
        "from fitdocs.cli import app\n"
        "result = CliRunner().invoke(app, json.loads(sys.argv[1]))\n"
        "print(json.dumps({'exit_code': result.exit_code, 'output': result.output, "
        "'exception': None if result.exception is None else "
        "type(result.exception).__name__, "
        "'duckdb_loaded': 'duckdb' in sys.modules}))\n"
    )
    outputs: dict[str, str] = {}
    duckdb_loaded: dict[str, bool] = {}
    for name, arguments in invocations.items():
        completed = subprocess.run(
            [sys.executable, "-c", child, json.dumps(arguments)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=_REPO_ROOT,
            env=environment,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads(completed.stdout)
        assert result["exception"] is None, (name, result)
        outputs[name] = result["output"]
        duckdb_loaded[name] = result["duckdb_loaded"]

    return _UntouchedCommandObservation(
        outputs=outputs,
        duckdb_loaded=duckdb_loaded,
        cache_before=before,
        cache_expected=expected_before,
        sentinel_expected=sentinel_expected,
        cache_after=_external_index_snapshot(index_base),
    )


def test_untouched_commands_do_not_import_duckdb(
    _untouched_command_observation: _UntouchedCommandObservation,
) -> None:
    assert set(_untouched_command_observation.outputs) == {
        "check",
        "history",
        "plan",
        "derive-benchmarks",
        "plugins",
        "skill",
        "version",
        "connect",
        "pull",
    }
    assert not any(_untouched_command_observation.duckdb_loaded.values())


def test_untouched_commands_do_not_print_index_reports(
    _untouched_command_observation: _UntouchedCommandObservation,
) -> None:
    index_lines = {
        name: [
            line for line in output.splitlines() if line.lstrip().startswith("Index:")
        ]
        for name, output in _untouched_command_observation.outputs.items()
    }
    assert not any(index_lines.values()), index_lines


def test_untouched_commands_preserve_every_external_index_file(
    _untouched_command_observation: _UntouchedCommandObservation,
) -> None:
    assert (
        _untouched_command_observation.cache_before
        == _untouched_command_observation.cache_expected
    )
    for name, expected in _untouched_command_observation.sentinel_expected.items():
        assert _untouched_command_observation.cache_before[name] == expected
    assert (
        _untouched_command_observation.cache_after
        == _untouched_command_observation.cache_before
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


def test_index_runtime_imports_are_confined_to_cli() -> None:
    files = tuple(
        path
        for path in _SOURCE_ROOT.rglob("*.py")
        if not path.is_relative_to(_SOURCE_ROOT / "index")
    )
    assert len(files) > 100
    importers = {
        _source_module(path): path.read_text(encoding="utf-8") for path in files
    }
    assert _REQUIRED_INDEX_IMPORTERS <= _INDEX_IMPORTERS
    assert {
        module for module, source in importers.items() if _imports_index_runtime(source)
    } <= _INDEX_IMPORTERS


def test_index_importer_guard_rejects_unlisted_and_does_not_resolve_allowlist() -> None:
    assert _unlisted_index_importers(
        {"fitdocs.history.engine": "from fitdocs.index import refresh\n"}
    ) == {"fitdocs.history.engine"}
    # An allowlisted importer absent from this fixed input is not an error:
    # the guard checks observed import edges and does not import/resolve names.
    assert _unlisted_index_importers({}) == set()
    assert (
        _unlisted_index_importers(
            {"fitdocs.query.statement": "from fitdocs.index import registry\n"}
        )
        == set()
    )


@pytest.mark.parametrize(
    "source",
    [
        "import fitdocs.index\n",
        "import fitdocs.index.refresh\n",
        "import fitdocs.index.refresh as refresh\n",
        "import fitdocs.index as index_runtime\n",
        "from fitdocs.index import refresh\n",
        "from fitdocs.index import refresh as refresh_runtime\n",
        "from fitdocs import index\n",
        "from fitdocs import index as index_runtime\n",
    ],
    ids=[
        "plain-root",
        "plain-submodule",
        "aliased-submodule",
        "aliased-root",
        "from-submodule",
        "from-aliased-submodule",
        "from-fitdocs-root",
        "from-aliased-fitdocs-root",
    ],
)
def test_index_import_guard_detects_supported_ast_import_forms(source: str) -> None:
    assert _imports_index_runtime(source)


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


def test_store_sql_guard_reaches_schema_and_insert_statements() -> None:
    source = _STORE_PATH.read_text(encoding="utf-8")
    constants = _string_constants_without_docstrings(source)
    assert any(value.startswith("CREATE TABLE ") for value in constants)
    assert any(value.startswith("INSERT INTO ") for value in constants)


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
