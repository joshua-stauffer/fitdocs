"""Read-side package and import-boundary guards for analytics-query task 1.3."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from tests.index.test_boundary import _INDEX_IMPORTERS

_REPO_ROOT = Path(__file__).parents[2]
_SOURCE_ROOT = _REPO_ROOT / "src" / "fitdocs"
_QUERY_IMPORTERS = frozenset({"fitdocs.cli"})


def _source_module(path: Path) -> str:
    relative = path.relative_to(_REPO_ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    return ".".join(parts)


def _import_targets(source: str, module: str) -> set[str]:
    tree = ast.parse(source)
    targets: set[str] = set()
    importlib_aliases: set[str] = set()
    import_module_aliases: set[str] = set()
    builtin_module_aliases: set[str] = set()
    builtin_import_aliases: set[str] = set()
    relative_import_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib" or (
                    alias.name.startswith("importlib.") and alias.asname is None
                ):
                    importlib_aliases.add(alias.asname or "importlib")
                elif alias.name == "builtins":
                    builtin_module_aliases.add(alias.asname or "builtins")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "importlib"
        ):
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "builtins"
        ):
            for alias in node.names:
                if alias.name == "__import__":
                    builtin_import_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level > 0:
            relative_import_names.update(
                alias.asname or alias.name for alias in node.names
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = (
                    module.removesuffix(".__init__")
                    if module.endswith(".__init__")
                    else module.rpartition(".")[0]
                )
                try:
                    imported_from = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except (ImportError, ValueError):
                    continue
            else:
                imported_from = node.module or ""
            if imported_from:
                targets.add(imported_from)
            targets.update(
                f"{imported_from}.{alias.name}"
                for alias in node.names
                if imported_from and alias.name != "*"
            )
        elif isinstance(node, ast.Call):
            target = node.func
            is_builtin_import = (
                isinstance(target, ast.Name)
                and (
                    target.id in builtin_import_aliases
                    or (
                        target.id == "__import__"
                        and target.id not in relative_import_names
                    )
                )
            ) or (
                isinstance(target, ast.Attribute)
                and target.attr == "__import__"
                and isinstance(target.value, ast.Name)
                and target.value.id in builtin_module_aliases
            )
            is_importlib_import = (
                isinstance(target, ast.Name) and target.id in import_module_aliases
            ) or (
                isinstance(target, ast.Attribute)
                and target.attr == "import_module"
                and isinstance(target.value, ast.Name)
                and target.value.id in importlib_aliases
            )
            dynamic = is_builtin_import or is_importlib_import
            module_name = (
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
                dynamic
                and isinstance(module_name, ast.Constant)
                and isinstance(module_name.value, str)
            ):
                resolved_name = module_name.value
                if is_importlib_import and resolved_name.startswith("."):
                    package_node = (
                        node.args[1]
                        if len(node.args) > 1
                        else next(
                            (
                                keyword.value
                                for keyword in node.keywords
                                if keyword.arg == "package"
                            ),
                            None,
                        )
                    )
                    if isinstance(package_node, ast.Constant) and isinstance(
                        package_node.value, str
                    ):
                        try:
                            resolved_name = importlib.util.resolve_name(
                                resolved_name, package_node.value
                            )
                        except (ImportError, ValueError):
                            continue
                elif is_builtin_import:
                    level_node = (
                        node.args[4]
                        if len(node.args) > 4
                        else next(
                            (
                                keyword.value
                                for keyword in node.keywords
                                if keyword.arg == "level"
                            ),
                            None,
                        )
                    )
                    if (
                        isinstance(level_node, ast.Constant)
                        and isinstance(level_node.value, int)
                        and level_node.value > 0
                    ):
                        package = (
                            module.removesuffix(".__init__")
                            if module.endswith(".__init__")
                            else module.rpartition(".")[0]
                        )
                        try:
                            resolved_name = importlib.util.resolve_name(
                                "." * level_node.value + resolved_name, package
                            )
                        except (ImportError, ValueError):
                            continue
                targets.add(resolved_name)
                if is_builtin_import:
                    fromlist_node = (
                        node.args[3]
                        if len(node.args) > 3
                        else next(
                            (
                                keyword.value
                                for keyword in node.keywords
                                if keyword.arg == "fromlist"
                            ),
                            None,
                        )
                    )
                    if isinstance(fromlist_node, (ast.List, ast.Tuple)):
                        targets.update(
                            f"{resolved_name}.{item.value}"
                            for item in fromlist_node.elts
                            if isinstance(item, ast.Constant)
                            and isinstance(item.value, str)
                        )
    return targets


def _unlisted_query_importers(sources: dict[str, str]) -> set[str]:
    return {
        module
        for module, source in sources.items()
        if any(
            target == "fitdocs.query" or target.startswith("fitdocs.query.")
            for target in _import_targets(source, module)
        )
        and module not in _QUERY_IMPORTERS
        and module != "fitdocs.query"
        and not module.startswith("fitdocs.query.")
    }


def test_query_modules_are_registered_as_index_importers() -> None:
    expected = {
        "fitdocs.query.sandbox",
        "fitdocs.query.statement",
        "fitdocs.query.freshness",
        "fitdocs.query.schemaview",
        "fitdocs.query.command",
    }
    assert expected <= _INDEX_IMPORTERS


def test_query_importers_are_confined_and_source_walk_is_live() -> None:
    files = tuple(_SOURCE_ROOT.rglob("*.py"))
    assert len(files) > 100
    sources = {
        _source_module(path): path.read_text(encoding="utf-8")
        for path in files
        if not path.is_relative_to(_SOURCE_ROOT / "query")
    }
    assert _unlisted_query_importers(sources) == set()


def test_query_importer_guard_detects_all_import_forms() -> None:
    forms = (
        "import fitdocs.query.sandbox",
        "import fitdocs.query.command as query_command",
        "from fitdocs.query import statement",
        "from fitdocs import query as query_package",
        "import importlib as loader\nloader.import_module('fitdocs.query.freshness')",
        "from importlib import import_module as load\n"
        "load(name='fitdocs.query.schemaview')",
        "__import__('fitdocs.query.command')",
        "__import__(name='fitdocs.query.statement')",
    )
    for source in forms:
        assert _unlisted_query_importers({"fitdocs.history.engine": source}) == {
            "fitdocs.history.engine"
        }
    assert (
        _unlisted_query_importers(
            {"fitdocs.cli": "from fitdocs.query.command import run_query"}
        )
        == set()
    )
    assert _unlisted_query_importers(
        {
            "fitdocs.history.engine": (
                "import importlib\nimportlib.import_module('fitdocs.query')"
            )
        }
    ) == {"fitdocs.history.engine"}
    assert _unlisted_query_importers(
        {
            "fitdocs.history.engine": "import importlib.util\n"
            "importlib.import_module('fitdocs.query')"
        }
    ) == {"fitdocs.history.engine"}
    assert (
        _unlisted_query_importers(
            {"fitdocs.history.engine": "label = 'fitdocs.query.command'"}
        )
        == set()
    )
    assert (
        _unlisted_query_importers(
            {
                "fitdocs.history.engine": (
                    "def import_module(name): pass\nimport_module('fitdocs.query')"
                )
            }
        )
        == set()
    )
    assert (
        _unlisted_query_importers(
            {"fitdocs.query.command": "from fitdocs.query.statement import run"}
        )
        == set()
    )


def test_source_module_names_regular_and_package_files() -> None:
    assert _source_module(_REPO_ROOT / "src/fitdocs/cli.py") == "fitdocs.cli"
    assert (
        _source_module(_REPO_ROOT / "src/fitdocs/history/__init__.py")
        == "fitdocs.history.__init__"
    )
    assert (
        _source_module(_REPO_ROOT / "src/fitdocs/history/engine.py")
        == "fitdocs.history.engine"
    )


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("fitdocs.history.engine", "from .. import query"),
        ("fitdocs.history.engine", "from .. import query as query_package"),
        ("fitdocs.history.engine", "from ..query import command"),
        ("fitdocs.history.__init__", "from .. import query"),
        ("fitdocs.history.__init__", "from ..query import command as run_query"),
    ],
    ids=[
        "ordinary-from-root",
        "ordinary-from-root-alias",
        "ordinary-from-submodule",
        "package-init-from-root",
        "package-init-from-submodule-alias",
    ],
)
def test_query_importer_guard_resolves_relative_imports(
    module: str, source: str
) -> None:
    assert _unlisted_query_importers({module: source}) == {module}


@pytest.mark.parametrize(
    ("module", "source", "expected"),
    [
        ("fitdocs.history.engine", "from . import query", set()),
        (
            "fitdocs.queryevil",
            "from fitdocs.query.command import run_query",
            {"fitdocs.queryevil"},
        ),
        (
            "fitdocs.query.helpers",
            "from fitdocs.query.command import run_query",
            set(),
        ),
    ],
    ids=["local-relative-query", "near-prefix-is-external", "query-child-exempt"],
)
def test_query_importer_guard_classifies_namespace_edges(
    module: str, source: str, expected: set[str]
) -> None:
    assert _unlisted_query_importers({module: source}) == expected


def test_query_importer_guard_rejects_query_sibling_target() -> None:
    assert (
        _unlisted_query_importers(
            {"fitdocs.history.engine": "import fitdocs.queryevil"}
        )
        == set()
    )


@pytest.mark.parametrize(
    "source",
    ["from fitdocs.query import *"],
    ids=["wildcard"],
)
def test_query_importer_guard_detects_wildcard_from_import(source: str) -> None:
    assert _unlisted_query_importers({"fitdocs.history.engine": source}) == {
        "fitdocs.history.engine"
    }


@pytest.mark.parametrize(
    "source",
    [
        "from .importlib import import_module\nimport_module('fitdocs.query')",
        "from .importlib import import_module as load\nload('fitdocs.query')",
        "from .builtins import __import__\n__import__('fitdocs.query')",
        "from .builtins import __import__ as load\nload('fitdocs.query')",
    ],
    ids=[
        "relative-importlib-no-alias",
        "relative-importlib-alias",
        "relative-builtins-no-alias",
        "relative-builtins-alias",
    ],
)
def test_query_importer_guard_ignores_relative_stdlib_name_bindings(
    source: str,
) -> None:
    assert _unlisted_query_importers({"fitdocs.history.engine": source}) == set()


def test_query_importer_guard_ignores_aliased_importlib_submodule() -> None:
    assert (
        _unlisted_query_importers(
            {
                "fitdocs.history.engine": "import importlib.util as loader\n"
                "loader.import_module('fitdocs.query')"
            }
        )
        == set()
    )


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('.query', 'fitdocs')",
        "import importlib as loader\nloader.import_module('.query', package='fitdocs')",
        "from importlib import import_module as load\nload('.query', 'fitdocs')",
        "__import__('query', globals(), locals(), [], 2)",
        "__import__('query', globals(), locals(), [], level=2)",
        "__import__('fitdocs', globals(), locals(), ('query',))",
        "__import__('fitdocs', globals(), locals(), ['query'])",
        "__import__('fitdocs', globals(), locals(), fromlist=('query',))",
        "__import__('fitdocs', fromlist=['query'])",
        "from builtins import __import__ as load\nload('fitdocs.query')",
        "import builtins as loader\nloader.__import__('fitdocs.query')",
        "from builtins import __import__ as load\n"
        "load('query', globals(), locals(), [], 2)",
        "import builtins as loader\nloader.__import__('query', level=2)",
    ],
    ids=[
        "import-module-positional-package",
        "import-module-keyword-package",
        "import-module-aliased-package",
        "dunder-import-positional-level",
        "dunder-import-keyword-level",
        "dunder-import-tuple-fromlist",
        "dunder-import-list-fromlist",
        "dunder-import-keyword-tuple-fromlist",
        "dunder-import-keyword-list-fromlist",
        "dunder-import-from-builtin-alias",
        "dunder-import-builtins-module-alias",
        "dunder-import-from-builtin-alias-relative",
        "dunder-import-builtins-module-alias-relative",
    ],
)
def test_query_importer_guard_resolves_literal_relative_dynamic_imports(
    source: str,
) -> None:
    assert _unlisted_query_importers({"fitdocs.history.engine": source}) == {
        "fitdocs.history.engine"
    }


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('.query', 'fitdocs.history')",
        "__import__('query', globals(), locals(), [], 1)",
        "__import__('fitdocs.history', globals(), locals(), ('query',))",
    ],
    ids=[
        "import-module-local-relative",
        "dunder-import-local-relative",
        "dunder-import-fromlist-local-relative",
    ],
)
def test_query_importer_guard_allows_local_relative_dynamic_imports(
    source: str,
) -> None:
    assert _unlisted_query_importers({"fitdocs.history.engine": source}) == set()


@pytest.mark.parametrize(
    "source",
    [
        "def load(name):\n    return None\nload('fitdocs.query')",
        "class loader:\n    def __import__(self, name):\n        return None\n"
        "loader.__import__('fitdocs.query')",
    ],
    ids=["local-function", "local-object-method"],
)
def test_query_importer_guard_ignores_unbound_import_call_names(
    source: str,
) -> None:
    assert _unlisted_query_importers({"fitdocs.history.engine": source}) == set()
