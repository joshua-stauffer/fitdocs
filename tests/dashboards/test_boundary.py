"""The `fitdocs.dashboards` package boundary (dashboards 8.4; Req 14.10, 20.2,
20.3, 20.4; design.md § Architecture and § Allowed Dependencies).

Every `*.py` file under `src/fitdocs/dashboards/`, the package marker
included, is parsed with the import-target parser of
`tests/query/test_boundary.py` (static and function-level imports, plus
literal-argument `importlib` / `__import__` calls). Six rules run over it:

1. **Module set** (`TestModuleSet`): the literal module tuple equals the
   `rglob` of the package both ways.
2. **Rank matrix** (`TestRankMatrix`): every intra-package import points to a
   strictly lower rank of `problems -> grammar -> directive -> snapshot ->
   region -> source -> storage -> kinds -> engine -> report -> binding`; the
   marker imports no module of the package and none imports it.
3. **Allowed imports** (`TestAllowedImports`): per-module third-party and
   `fitdocs.*` allowlists with dotted descent, plus an independent
   forbidden-name list and the network modules.
4. **Clock** (`TestClockNames`): no module names a clock function or
   spelling; a `.today` attribute is legal only on the injected `request`,
   `stored` and `snapshot` values.
5. **No dynamic imports** (`TestNoDynamicImports`): no module imports
   `importlib`, `builtins`, `pkgutil`, `runpy` or `zipimport`, names
   `__import__`, `import_module` or `__builtins__`, or calls bare `exec`,
   `eval` or `compile`. Known limits of a static scan, not closed
   (illustrative, not exhaustive): a module object reached through an
   attribute of an allowed import; a name assembled at run time and looked up
   in `sys.modules` or a global dict; any other standard-library module that
   runs source text or imports by name (for example
   `code.InteractiveInterpreter().runsource`). The clock rule (4) likewise
   cannot see `today` reached through `operator.attrgetter("today")`, or a
   date class rebound to an allowed base name inside a function
   (`snapshot = date; snapshot.today()`).
6. **Importers** (`TestOnlyTheCliImports`): only `fitdocs.cli` imports
   `fitdocs.dashboards` from the rest of `src/fitdocs`.

The landed graph differs from design.md § Allowed Dependencies in one rule:
`fitdocs.units` is allowed in `engine` as well as `binding` (the engine
re-derives units on decoded snapshots; tasks.md Implementation Notes, 5.3
R11). The scan functions also run on synthetic sources, and the rule lists
are pinned by literal copies, so an emptied rule or a dropped list entry goes
red.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Final

import fitdocs.dashboards
from tests.query.test_boundary import _import_targets

_PACKAGE: Final[str] = "fitdocs.dashboards"
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_SOURCE_ROOT: Final[Path] = _REPO_ROOT / "src" / "fitdocs"

#: Rank order of design § Architecture, lowest first.
_RANK_ORDER: Final[tuple[str, ...]] = (
    "problems",
    "grammar",
    "directive",
    "snapshot",
    "region",
    "source",
    "storage",
    "kinds",
    "engine",
    "report",
    "binding",
)

#: The package marker is docstring-only: it imports no module of the package
#: (rank -1 is below every target) and no module may import it.
_RANKS: Final[dict[str, int]] = {
    **{f"{_PACKAGE}.{name}": rank for rank, name in enumerate(_RANK_ORDER)},
    _PACKAGE: -1,
}

#: The module set, by dotted name; the marker is the package itself.
_MODULES: Final[tuple[str, ...]] = (_PACKAGE, *(f"{_PACKAGE}.{n}" for n in _RANK_ORDER))

_KIT: Final[str] = "fitdocs.render.charts.kit"
_KIT_FORMAT: Final[str] = f"{_KIT}.format"
_QUERY_ROOTS: Final[tuple[str, ...]] = (
    "fitdocs.query.command",
    "fitdocs.query.statement",
    "fitdocs.query.format",
)

#: Non-stdlib, non-intra-package roots each module may import (dotted
#: descent). Written as literals. `fitdocs.render.charts.kit` is allowed
#: everywhere; its `format` submodule is added for `region` alone.
_ALLOWED_EXTERNAL: Final[dict[str, tuple[str, ...]]] = {
    _PACKAGE: (),
    f"{_PACKAGE}.problems": (_KIT,),
    f"{_PACKAGE}.grammar": (),
    f"{_PACKAGE}.directive": ("yaml",),
    f"{_PACKAGE}.snapshot": (_KIT,),
    f"{_PACKAGE}.region": (_KIT, _KIT_FORMAT),
    f"{_PACKAGE}.source": (_KIT,),
    f"{_PACKAGE}.storage": ("fitdocs.layout", "fitdocs.contract"),
    f"{_PACKAGE}.kinds": (_KIT,),
    f"{_PACKAGE}.engine": (_KIT, "fitdocs.units", "fitdocs.layout", "fitdocs.contract"),
    f"{_PACKAGE}.report": (),
    f"{_PACKAGE}.binding": (_KIT, "fitdocs.units", *_QUERY_ROOTS),
}

#: Hard rules: no module imports these (equality or descent), whatever its
#: allowlist says. `fitdocs.render` is handled apart (only the kit facade).
_FORBIDDEN_ROOTS: Final[tuple[str, ...]] = (
    "duckdb",
    "fitdocs.index",
    "fitdocs.sync",
    "fitdocs.history",
    "fitdocs.plans",
    "fitdocs.load",
    "fitdocs.model",
    "fitdocs.ingest",
    "fitdocs.connectors",
    "fitdocs.tiles",
    "fitdocs.plugins",
    "fitdocs.cli",
    "socket",
    "urllib",
    "http",
    "ssl",
    "time",
)

#: Spellings scanned for in the raw text, so a docstring example counts.
_CLOCK_SPELLINGS: Final[tuple[str, ...]] = (
    "datetime.now",
    "date.today",
    "time.time",
    "datetime.utcnow",
    "datetime.today",
    "time.monotonic",
    "time.perf_counter",
    "time.localtime",
    "time.gmtime",
)

#: Names that are a clock function when named, called or imported. `today` is
#: handled apart: the run request carries an injected `today` field.
_CLOCK_NAMES: Final[frozenset[str]] = frozenset(
    {
        "now",
        "utcnow",
        "time_ns",
        "monotonic",
        "monotonic_ns",
        "perf_counter",
        "perf_counter_ns",
        "localtime",
        "gmtime",
        "sleep",
    }
)


#: The only bases a `.today` attribute may have: the injected run request and
#: the stored and decoded snapshot values.
_TODAY_BASES: Final[frozenset[str]] = frozenset({"request", "stored", "snapshot"})

#: Import roots that make a dynamic import possible; no module needs one.
_DYNAMIC_ROOTS: Final[tuple[str, ...]] = (
    "importlib",
    "builtins",
    "pkgutil",
    "runpy",
    "zipimport",
)
#: Bare builtins that run or compile source text.
_DYNAMIC_CALLS: Final[frozenset[str]] = frozenset({"exec", "eval", "compile"})
_DYNAMIC_NAMES: Final[frozenset[str]] = frozenset({"__import__", "import_module"})


def _package_dir() -> Path:
    path = fitdocs.dashboards.__file__
    assert path is not None, "fitdocs.dashboards has no __file__"
    return Path(path).parent


def _module_files(root: Path) -> dict[str, Path]:
    """Dotted name -> path of every `*.py` file under `root`; the marker is
    `fitdocs.dashboards` itself."""
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("")
        parts = rel.parts[:-1] if path.name == "__init__.py" else rel.parts
        files[".".join((*_PACKAGE.split("."), *parts))] = path
    return files


def _parser_name(module: str) -> str:
    """The module name `_import_targets` resolves relative imports against: a
    package marker carries a trailing `.__init__`."""
    return f"{module}.__init__" if module == _PACKAGE else module


def _targets(source: str, module: str) -> set[str]:
    return _import_targets(source, _parser_name(module))


def _is_stdlib(target: str) -> bool:
    return target.split(".", 1)[0] in sys.stdlib_module_names


def _under(target: str, root: str) -> bool:
    return target == root or target.startswith(f"{root}.")


def _under_any(target: str, roots: tuple[str, ...]) -> bool:
    return any(_under(target, root) for root in roots)


def _is_submodule(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def _is_covered_ancestor(target: str, targets: set[str]) -> bool:
    """A package that only appears because a `from <package> import <name>`
    also produced `<package>.<name>`."""
    return any(other.startswith(f"{target}.") for other in targets)


def _kit_submodule(target: str) -> str | None:
    """The kit submodule `target` names, when it is one: `ChartData` is a name
    on the facade, `format` is a module."""
    if not target.startswith(f"{_KIT}."):
        return None
    head = ".".join(target.split(".")[: len(_KIT.split(".")) + 1])
    return head if _is_submodule(head) else None


def _forbidden(target: str, targets: set[str]) -> bool:
    if _under_any(target, _FORBIDDEN_ROOTS):
        return True
    if _under(target, "fitdocs.render"):
        if _under(target, _KIT):
            return False
        return not _is_covered_ancestor(target, targets)
    return False


def _external_violations(source: str, module: str) -> set[str]:
    """Non-stdlib, non-intra-package targets outside the module's allowlist,
    plus every forbidden target."""
    targets = _targets(source, module)
    allowed = _ALLOWED_EXTERNAL[module]
    found: set[str] = set()
    for target in targets:
        if _under(target, _PACKAGE):
            continue
        if _forbidden(target, targets):
            found.add(target)
            continue
        if _is_stdlib(target):
            continue
        kit_module = _kit_submodule(target)
        if kit_module is not None:
            if not _under(kit_module, _KIT_FORMAT) or _KIT_FORMAT not in allowed:
                found.add(target)
            continue
        if _under_any(target, allowed):
            continue
        if _is_covered_ancestor(target, targets):
            continue
        found.add(target)
    return found


def _forbidden_violations(source: str, module: str) -> set[str]:
    targets = _targets(source, module)
    return {
        t
        for t in targets
        if not _under(t, _PACKAGE)
        and (_forbidden(t, targets) or _kit_format_outside_region(t, module))
    }


def _kit_format_outside_region(target: str, module: str) -> bool:
    return _under(target, _KIT_FORMAT) and module != f"{_PACKAGE}.region"


def _intra_targets(source: str, module: str) -> set[str]:
    """The package modules `source` imports, each resolved to the longest
    known module prefix (`...grammar.SLUG` -> `...grammar`). The bare package
    that `from fitdocs.dashboards import grammar` also yields is dropped when
    a more specific module came with it."""
    targets = _targets(source, module)
    resolved: set[str] = set()
    for target in targets:
        if not _under(target, _PACKAGE):
            continue
        known = [m for m in _RANKS if _under(target, m)]
        resolved.add(max(known, key=len) if known else target)
    if any(r != _PACKAGE for r in resolved):
        resolved.discard(_PACKAGE)
    return resolved


def _rank_violations(source: str, module: str) -> set[tuple[str, str]]:
    """Intra-package imports that do not point to a strictly lower rank."""
    own = _RANKS[module]
    return {
        (module, target)
        for target in _intra_targets(source, module)
        if target == _PACKAGE or _RANKS[target] >= own
    }


def _clock_offenders(source: str) -> list[str]:
    found = [
        s for s in _CLOCK_SPELLINGS if re.search(rf"(?<!\w){re.escape(s)}\b", source)
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.extend(
                f"import as {a.asname}" for a in node.names if a.asname in _TODAY_BASES
            )
        if isinstance(node, ast.Attribute):
            if node.attr in _CLOCK_NAMES:
                found.append(f".{node.attr}")
            elif node.attr == "today" and not (
                isinstance(node.value, ast.Name) and node.value.id in _TODAY_BASES
            ):
                found.append(".today")
        elif isinstance(node, ast.Name) and node.id in _CLOCK_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "today":
                found.append("today()")
            elif (
                isinstance(func, ast.Name)
                and func.id == "getattr"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in (*_CLOCK_NAMES, "today")
            ):
                found.append(f"getattr({node.args[1].value})")
        elif isinstance(node, ast.ImportFrom):
            found.extend(
                f"from {node.module} import {a.name}"
                for a in node.names
                if a.name in _CLOCK_NAMES or a.name == "today"
            )
    return found


def _dynamic_import_violations(source: str, module: str) -> set[str]:
    """Roots and names through which an import could be made with a name the
    static scan cannot read."""
    found = {t for t in _targets(source, module) if _under_any(t, _DYNAMIC_ROOTS)}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and (
            node.id in _DYNAMIC_NAMES or node.id == "__builtins__"
        ):
            found.add(node.id)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _DYNAMIC_CALLS
        ):
            found.add(f"{node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_NAMES:
            found.add(node.attr)
    return found


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _scanned() -> dict[str, str]:
    files = _module_files(_package_dir())
    assert files, "the walk is looking at the wrong directory"
    return {name: _read(path) for name, path in files.items()}


class TestModuleSet:
    def test_the_literal_tuple_equals_the_rglob_both_ways(self) -> None:
        files = _module_files(_package_dir())
        assert set(files) == set(_MODULES), sorted(set(files) ^ set(_MODULES))
        assert set(_ALLOWED_EXTERNAL) == set(_MODULES)
        assert set(_RANKS) == set(_MODULES)
        assert len(_MODULES) == len(set(_MODULES))

    def test_the_walk_saw_the_whole_package(self) -> None:
        files = _module_files(_package_dir())
        assert len(files) >= 11
        assert _PACKAGE in files
        assert f"{_PACKAGE}.engine" in files

    def test_an_unlisted_module_is_detected(self, tmp_path: Path) -> None:
        (tmp_path / "surprise.py").write_text("x = 1\n", encoding="utf-8")
        files = _module_files(tmp_path)
        assert files == {f"{_PACKAGE}.surprise": tmp_path / "surprise.py"}
        assert set(files) - set(_MODULES) == {f"{_PACKAGE}.surprise"}

    def test_a_nested_module_is_walked(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "sub" / "deep.py").write_text("", encoding="utf-8")
        assert set(_module_files(tmp_path)) == {
            f"{_PACKAGE}.sub",
            f"{_PACKAGE}.sub.deep",
        }

    def test_an_empty_directory_finds_no_engine(self, tmp_path: Path) -> None:
        assert f"{_PACKAGE}.engine" not in _module_files(tmp_path)


class TestRankMatrix:
    def test_the_rank_order_is_the_design_order(self) -> None:
        assert _RANK_ORDER == (
            "problems",
            "grammar",
            "directive",
            "snapshot",
            "region",
            "source",
            "storage",
            "kinds",
            "engine",
            "report",
            "binding",
        )
        assert _RANKS[_PACKAGE] == -1
        assert [_RANKS[f"{_PACKAGE}.{n}"] for n in _RANK_ORDER] == list(range(11))

    def test_every_intra_package_import_points_to_a_lower_rank(self) -> None:
        scanned = _scanned()
        edges = {
            (name, target)
            for name, source in scanned.items()
            for target in _intra_targets(source, name)
        }
        assert len(edges) >= 15, "the scan found too few intra-package imports"
        for name, source in scanned.items():
            assert _rank_violations(source, name) == set(), name

    def test_the_engine_never_imports_the_binding(self) -> None:
        scanned = _scanned()
        engine = f"{_PACKAGE}.engine"
        assert _intra_targets(scanned[engine], engine)
        assert f"{_PACKAGE}.binding" not in _intra_targets(scanned[engine], engine)

    def test_the_binding_imports_only_problems_and_source_from_the_package(
        self,
    ) -> None:
        binding = f"{_PACKAGE}.binding"
        assert _intra_targets(_scanned()[binding], binding) == {
            f"{_PACKAGE}.problems",
            f"{_PACKAGE}.source",
        }

    def test_an_upward_or_sideways_import_is_reported(self) -> None:
        engine = f"{_PACKAGE}.engine"
        binding, report = f"{_PACKAGE}.binding", f"{_PACKAGE}.report"
        for source, expected in (
            ("from fitdocs.dashboards.binding import x\n", binding),
            ("import fitdocs.dashboards.report\n", report),
            ("from fitdocs.dashboards import binding\n", binding),
            ("from . import binding\n", binding),
            ("from .report import x\n", report),
            ("from fitdocs.dashboards import x\n", _PACKAGE),
            ("import fitdocs.dashboards\n", _PACKAGE),
            ("from fitdocs.dashboards.engine import x\n", engine),
            (
                "import importlib\n"
                "importlib.import_module('fitdocs.dashboards.binding')\n",
                binding,
            ),
            ("__import__('fitdocs.dashboards.report')\n", report),
        ):
            assert _rank_violations(source, engine) == {(engine, expected)}, source

    def test_the_marker_imports_nothing_and_none_may_import_it(self) -> None:
        marker = f"{_PACKAGE}"
        for source, target in (
            ("from .binding import x\n", f"{_PACKAGE}.binding"),
            ("from . import problems\n", f"{_PACKAGE}.problems"),
            ("import fitdocs.dashboards.grammar\n", f"{_PACKAGE}.grammar"),
        ):
            assert _rank_violations(source, marker) == {(marker, target)}, source
        assert _rank_violations("import json\n", marker) == set()
        binding = f"{_PACKAGE}.binding"
        assert _rank_violations("from .problems import x\n", binding) == set()
        assert _rank_violations("import fitdocs.dashboards\n", binding) == {
            (binding, _PACKAGE)
        }
        assert _rank_violations("from . import grammar\n", f"{_PACKAGE}.grammar") == {
            (f"{_PACKAGE}.grammar", f"{_PACKAGE}.grammar")
        }

    def test_a_lower_rank_import_is_not_reported(self) -> None:
        for source in (
            "from fitdocs.dashboards.grammar import SLUG\n",
            "from fitdocs.dashboards import grammar\n",
            "from . import grammar\n",
            "import fitdocs.dashboards.problems\n",
        ):
            assert _rank_violations(source, f"{_PACKAGE}.directive") == set(), source

    def test_a_non_package_import_is_not_an_intra_package_edge(self) -> None:
        assert _intra_targets("import fitdocs.dashboards_extra\n", _PACKAGE) == set()
        assert _intra_targets("import json\n", _PACKAGE) == set()


class TestAllowedImports:
    def test_every_module_imports_only_its_allowed_externals(self) -> None:
        for name, source in _scanned().items():
            assert _external_violations(source, name) == set(), name

    def test_no_module_imports_a_forbidden_name(self) -> None:
        for name, source in _scanned().items():
            assert _forbidden_violations(source, name) == set(), name

    def test_the_scan_sees_the_landed_external_imports(self) -> None:
        scanned = _scanned()
        seen = {
            name: {t for t in _targets(src, name) if not _under(t, _PACKAGE)}
            for name, src in scanned.items()
        }
        assert "yaml" in seen[f"{_PACKAGE}.directive"]
        assert _KIT_FORMAT in seen[f"{_PACKAGE}.region"]
        assert "fitdocs.query.command" in seen[f"{_PACKAGE}.binding"]
        assert "fitdocs.units" in seen[f"{_PACKAGE}.binding"]
        assert "fitdocs.units" in seen[f"{_PACKAGE}.engine"]
        assert "fitdocs.layout" in seen[f"{_PACKAGE}.storage"]
        assert "fitdocs.contract" in seen[f"{_PACKAGE}.storage"]

    def test_the_allowlist_encodes_the_per_module_rules(self) -> None:
        def holders(root: str) -> set[str]:
            return {
                m.removeprefix(f"{_PACKAGE}.")
                for m, roots in _ALLOWED_EXTERNAL.items()
                if any(_under(root, r) for r in roots)
            }

        assert holders("yaml") == {"directive"}
        assert holders("fitdocs.query.command") == {"binding"}
        assert {
            m.removeprefix(f"{_PACKAGE}.")
            for m, roots in _ALLOWED_EXTERNAL.items()
            if _KIT_FORMAT in roots
        } == {"region"}
        assert holders("fitdocs.units") == {"binding", "engine"}
        assert holders("fitdocs.layout") == {"storage", "engine"}
        assert holders("fitdocs.contract") == {"storage", "engine"}

    def test_each_external_rule_has_a_violating_source(self) -> None:
        engine, region = f"{_PACKAGE}.engine", f"{_PACKAGE}.region"
        for source, module, expected in (
            ("import yaml\n", engine, {"yaml"}),
            (
                "from yaml import safe_load\n",
                f"{_PACKAGE}.binding",
                {"yaml.safe_load"},
            ),
            ("import yaml\n", f"{_PACKAGE}.directive", set()),
            (
                "from fitdocs.query import command\n",
                engine,
                {"fitdocs.query.command"},
            ),
            ("import fitdocs.query.command\n", engine, {"fitdocs.query.command"}),
            (
                "from fitdocs.query.format import ResultSet\n",
                f"{_PACKAGE}.storage",
                {"fitdocs.query.format.ResultSet"},
            ),
            ("from fitdocs.query.statement import X\n", f"{_PACKAGE}.binding", set()),
            (
                "from fitdocs.render.charts.kit.format import clean_text\n",
                engine,
                {
                    "fitdocs.render.charts.kit.format",
                    "fitdocs.render.charts.kit.format.clean_text",
                },
            ),
            (
                "from fitdocs.render.charts.kit import format\n",
                engine,
                {"fitdocs.render.charts.kit.format"},
            ),
            (
                "from fitdocs.render.charts.kit.format import clean_text\n",
                region,
                set(),
            ),
            ("from fitdocs.render.charts.kit import format\n", region, set()),
            ("from fitdocs.render.charts.kit import ChartData\n", engine, set()),
            (
                "from fitdocs.units import unit_for_column\n",
                region,
                {"fitdocs.units.unit_for_column"},
            ),
            ("from fitdocs.units import unit_for_column\n", engine, set()),
            (
                "from fitdocs.units import unit_for_column\n",
                f"{_PACKAGE}.binding",
                set(),
            ),
            (
                "from fitdocs.layout import DASHBOARDS_DIR\n",
                f"{_PACKAGE}.binding",
                {"fitdocs.layout.DASHBOARDS_DIR"},
            ),
            (
                "from fitdocs.contract import is_generated\n",
                region,
                {"fitdocs.contract.is_generated"},
            ),
            (
                "from fitdocs.render.charts import svg\n",
                engine,
                {"fitdocs.render.charts.svg"},
            ),
            ("import fitdocs.render.views\n", engine, {"fitdocs.render.views"}),
            ("from fitdocs.render import charts\n", engine, {"fitdocs.render.charts"}),
            ("import numpy\n", engine, {"numpy"}),
            ("import socket\n", engine, {"socket"}),
            ("import time\n", engine, {"time"}),
            ("from urllib import request\n", engine, {"urllib", "urllib.request"}),
            ("import http.client\n", engine, {"http.client"}),
            ("import ssl\n", engine, {"ssl"}),
            ("import importlib\nimportlib.import_module('yaml')\n", engine, {"yaml"}),
            (
                "from importlib import import_module as load\nload('numpy.linalg')\n",
                engine,
                {"numpy.linalg"},
            ),
            ("import builtins\nbuiltins.__import__('yaml')\n", engine, {"yaml"}),
            ("import json\nimport re\n", engine, set()),
        ):
            assert _external_violations(source, module) == expected, (source, module)

    def test_each_forbidden_name_is_detected_in_every_import_form(self) -> None:
        engine = f"{_PACKAGE}.engine"
        for root in _FORBIDDEN_ROOTS:
            dotted = f"{root}.child"
            for source in (
                f"import {root}\n",
                f"import {dotted}\n",
                f"from {root} import child\n",
                f"from {dotted} import thing\n",
                f"import importlib\nimportlib.import_module({root!r})\n",
                f"import importlib as loader\nloader.import_module(name={dotted!r})\n",
                f"from importlib import import_module as load\nload({root!r})\n",
                f"__import__({root!r})\n",
                f"import builtins\nbuiltins.__import__({dotted!r})\n",
                f"def f():\n    import {root}\n",
            ):
                found = _forbidden_violations(source, engine)
                assert found, source
                assert all(_under(t, root) for t in found), (source, found)

    def test_a_relative_import_of_a_forbidden_sibling_package_is_detected(self) -> None:
        engine = f"{_PACKAGE}.engine"
        assert _forbidden_violations("from .. import sync\n", engine) == {
            "fitdocs.sync"
        }
        assert _forbidden_violations("from ..index import store\n", engine) == {
            "fitdocs.index",
            "fitdocs.index.store",
        }
        assert _forbidden_violations("from ..render import views\n", engine) == {
            "fitdocs.render.views"
        }
        assert _forbidden_violations(
            "import importlib\nimportlib.import_module('.sync', package='fitdocs')\n",
            engine,
        ) == {"fitdocs.sync"}

    def test_network_modules_are_forbidden_by_dotted_descent(self) -> None:
        engine = f"{_PACKAGE}.engine"
        for source, expected in (
            ("import socket\n", {"socket"}),
            ("import urllib.request\n", {"urllib.request"}),
            ("from urllib import request\n", {"urllib", "urllib.request"}),
            ("from http import client\n", {"http", "http.client"}),
            ("import http.server\n", {"http.server"}),
            ("import ssl\n", {"ssl"}),
            ("import importlib\nimportlib.import_module('socket')\n", {"socket"}),
        ):
            assert _forbidden_violations(source, engine) == expected, source

    def test_a_longer_name_is_not_a_forbidden_name(self) -> None:
        engine = f"{_PACKAGE}.engine"
        for source in (
            "import fitdocs.sync_extra\n",
            "import fitdocs.loader\n",
            "import fitdocs.indexer\n",
            "import httpx_like\n",
            "import timeit\n",
            "import fitdocs.cli_extra\n",
            "import sockets\n",
        ):
            assert _forbidden_violations(source, engine) == set(), source

    def test_a_string_is_not_an_import(self) -> None:
        engine = f"{_PACKAGE}.engine"
        assert _external_violations("x = 'yaml'\ny = 'fitdocs.sync'\n", engine) == set()
        assert (
            _external_violations(
                "def local_import_module(n):\n    return n\n"
                "local_import_module('duckdb')\n",
                engine,
            )
            == set()
        )

    def test_function_level_imports_are_scanned(self) -> None:
        engine = f"{_PACKAGE}.engine"
        assert _external_violations("def f():\n    import yaml\n", engine) == {"yaml"}


class TestForbiddenLists:
    def test_the_forbidden_roots_are_the_literal_ones(self) -> None:
        literal = (
            "duckdb",
            "fitdocs.index",
            "fitdocs.sync",
            "fitdocs.history",
            "fitdocs.plans",
            "fitdocs.load",
            "fitdocs.model",
            "fitdocs.ingest",
            "fitdocs.connectors",
            "fitdocs.tiles",
            "fitdocs.plugins",
            "fitdocs.cli",
            "socket",
            "urllib",
            "http",
            "ssl",
            "time",
        )
        assert literal == _FORBIDDEN_ROOTS
        engine = f"{_PACKAGE}.engine"
        for root in literal:
            assert _forbidden_violations(f"import {root}\n", engine) == {root}, root
        assert _forbidden_violations(
            "import time\nx = time.strftime('%Y')\n", engine
        ) == {"time"}
        assert _forbidden_violations("from time import strftime\n", engine) == {
            "time",
            "time.strftime",
        }

    def test_the_kit_format_rule_runs_on_synthetic_sources(self) -> None:
        engine, region = f"{_PACKAGE}.engine", f"{_PACKAGE}.region"
        direct = "from fitdocs.render.charts.kit.format import clean_text\n"
        facade = "from fitdocs.render.charts.kit import format\n"
        assert _forbidden_violations(direct, engine) == {
            "fitdocs.render.charts.kit.format",
            "fitdocs.render.charts.kit.format.clean_text",
        }
        assert _forbidden_violations(facade, engine) == {
            "fitdocs.render.charts.kit.format"
        }
        assert _forbidden_violations(direct, region) == set()
        assert _forbidden_violations(facade, region) == set()
        assert (
            _forbidden_violations(
                "from fitdocs.render.charts.kit import ChartData\n", engine
            )
            == set()
        )

    def test_the_other_render_modules_are_forbidden_in_every_module(self) -> None:
        for name in _MODULES:
            assert _forbidden_violations("import fitdocs.render.views\n", name) == {
                "fitdocs.render.views"
            }, name
            assert _forbidden_violations("import fitdocs.render\n", name) == {
                "fitdocs.render"
            }, name

    def test_the_allowlist_map_is_the_literal_one(self) -> None:
        kit, fmt = _KIT, _KIT_FORMAT
        query = (
            "fitdocs.query.command",
            "fitdocs.query.statement",
            "fitdocs.query.format",
        )
        expected = {
            "": (),
            ".problems": (kit,),
            ".grammar": (),
            ".directive": ("yaml",),
            ".snapshot": (kit,),
            ".region": (kit, fmt),
            ".source": (kit,),
            ".storage": ("fitdocs.layout", "fitdocs.contract"),
            ".kinds": (kit,),
            ".engine": (kit, "fitdocs.units", "fitdocs.layout", "fitdocs.contract"),
            ".report": (),
            ".binding": (kit, "fitdocs.units", *query),
        }
        assert {_PACKAGE + k: v for k, v in expected.items()} == _ALLOWED_EXTERNAL


class TestClockNames:
    def test_no_module_names_a_clock(self) -> None:
        for name, source in _scanned().items():
            assert _clock_offenders(source) == [], name

    def test_each_clock_form_is_detected(self) -> None:
        for source in (
            '"""e.g. datetime.now(UTC)"""\n',
            '"""e.g. date.today()"""\n',
            "from time import time_ns\n",
            "from datetime import date\nx = date.today()\n",
            "from datetime import date\nx = date\ny = x.today()\n",
            "from datetime import date\nx = today()\n",
            "from datetime import today\n",
            "from datetime import datetime\nx = datetime.now()\n",
            "x = clock.monotonic()\n",
            "x = sleep(1)\n",
        ):
            assert _clock_offenders(source), source

    def test_an_uncalled_or_aliased_clock_is_detected(self) -> None:
        for source in (
            "from datetime import date as _day\n"
            "from dataclasses import field\n"
            "x = field(default_factory=_day.today)\n",
            "from datetime import date as d\nf = d.today\n",
            "import datetime as dt\nx = dt.date.today\n",
            "import datetime\nx = datetime.date.today()\n",
            "from datetime import date\nx = (lambda d: d.today)(date)\n",
            "import functools\nfrom datetime import date as d\n"
            "f = functools.partial(d.today)\n",
            "from datetime import date\nx = getattr(date, 'today')\n",
            "from datetime import datetime as d\nf = d.now\n",
            "from datetime import datetime as d\nf = d.utcnow\n",
        ):
            assert _clock_offenders(source), source

    def test_the_clock_name_and_spelling_lists_are_the_literal_ones(self) -> None:
        names = (
            "now",
            "utcnow",
            "time_ns",
            "monotonic",
            "monotonic_ns",
            "perf_counter",
            "perf_counter_ns",
            "localtime",
            "gmtime",
            "sleep",
        )
        spellings = (
            "datetime.now",
            "date.today",
            "time.time",
            "datetime.utcnow",
            "datetime.today",
            "time.monotonic",
            "time.perf_counter",
            "time.localtime",
            "time.gmtime",
        )
        assert frozenset(names) == _CLOCK_NAMES
        assert spellings == _CLOCK_SPELLINGS
        for name in names:
            assert _clock_offenders(f"x = {name}\n"), name
            assert _clock_offenders(f"x = a.{name}\n"), name
            assert _clock_offenders(f"from m import {name}\n"), name
        for spelling in spellings:
            assert _clock_offenders(f'"""{spelling}"""\n') == [spelling], spelling

    def test_an_import_alias_cannot_borrow_a_legal_today_base(self) -> None:
        for base in ("request", "stored", "snapshot"):
            source = f"from datetime import date as {base}\nx = {base}.today()\n"
            assert _clock_offenders(source) == [f"import as {base}"], base
            assert _clock_offenders(f"import datetime as {base}\n") == [
                f"import as {base}"
            ], base
        assert _clock_offenders("from datetime import date as d\n") == []

    def test_an_injected_today_is_not_a_clock(self) -> None:
        assert {"request", "stored", "snapshot"} == _TODAY_BASES
        assert _clock_offenders("def f(today):\n    return today\n") == []
        assert _clock_offenders("r = Request(today=today)\n") == []
        for base in ("request", "stored", "snapshot"):
            assert _clock_offenders(f"x = {base}.today\n") == [], base
            assert _clock_offenders(f"x = {base}.today.isoformat()\n") == [], base
        assert _clock_offenders("x = other.today\n") == [".today"]
        assert _clock_offenders("x = request.child.today\n") == [".today"]

    def test_timestamp_and_timezone_are_not_clock_names(self) -> None:
        assert _clock_offenders("x = a.start_time.timestamp()\n") == []
        assert _clock_offenders("x = datetime.timezone.utc\n") == []
        assert _clock_offenders("x = runtime.time_stamp\n") == []
        assert _clock_offenders("x = a_time.time\n") == []


class TestNoDynamicImports:
    def test_no_module_reaches_for_a_dynamic_import(self) -> None:
        for name, source in _scanned().items():
            assert _dynamic_import_violations(source, name) == set(), name

    def test_each_dynamic_form_is_detected_whatever_its_argument(self) -> None:
        engine = f"{_PACKAGE}.engine"
        for source, expected in (
            (
                "import importlib\nimportlib.import_module(name)\n",
                {"importlib", "import_module"},
            ),
            (
                "import importlib\nimportlib.import_module('json')\n",
                {"importlib", "import_module"},
            ),
            (
                "from importlib import import_module\nimport_module(name)\n",
                {"importlib", "importlib.import_module", "import_module"},
            ),
            ("import importlib.util\n", {"importlib.util"}),
            ("__import__(name)\n", {"__import__"}),
            (
                "import builtins\nbuiltins.__import__(name)\n",
                {"builtins", "__import__"},
            ),
            (
                "from builtins import __import__ as load\nload(name)\n",
                {"builtins", "builtins.__import__"},
            ),
            ("def f():\n    import importlib\n", {"importlib"}),
        ):
            assert _dynamic_import_violations(source, engine) == expected, source

    def test_the_routes_that_import_without_a_name_are_detected(self) -> None:
        engine = f"{_PACKAGE}.engine"
        for source, expected in (
            ('__builtins__["__import__"]("duckdb")\n', {"__builtins__"}),
            ('exec("import duckdb")\n', {"exec()"}),
            ('eval("__import__(1)")\n', {"eval()"}),
            ('compile("import duckdb", "f", "exec")\n', {"compile()"}),
            ('import pkgutil\npkgutil.resolve_name("duckdb")\n', {"pkgutil"}),
            ('import runpy\nrunpy.run_module("duckdb")\n', {"runpy"}),
            ("import zipimport\n", {"zipimport"}),
            ("from pkgutil import resolve_name\n", {"pkgutil", "pkgutil.resolve_name"}),
        ):
            assert _dynamic_import_violations(source, engine) == expected, source

    def test_a_method_named_like_a_builtin_is_not_one(self) -> None:
        engine = f"{_PACKAGE}.engine"
        for source in (
            "import re\nx = re.compile('a')\n",
            "x = obj.exec('a')\ny = obj.eval\n",
            "def compile_all(exec_path):\n    return exec_path\n",
        ):
            assert _dynamic_import_violations(source, engine) == set(), source

    def test_the_dynamic_lists_are_the_literal_ones(self) -> None:
        assert _DYNAMIC_ROOTS == (
            "importlib",
            "builtins",
            "pkgutil",
            "runpy",
            "zipimport",
        )
        assert {"exec", "eval", "compile"} == _DYNAMIC_CALLS
        assert {"__import__", "import_module"} == _DYNAMIC_NAMES
        engine = f"{_PACKAGE}.engine"
        assert _dynamic_import_violations("import importlib\n", engine) == {"importlib"}
        assert _dynamic_import_violations("import builtins\n", engine) == {"builtins"}
        assert _dynamic_import_violations("x = a.import_module\n", engine) == {
            "import_module"
        }
        assert _dynamic_import_violations("x = a.__import__\n", engine) == {
            "__import__"
        }
        assert _dynamic_import_violations("x = import_module\n", engine) == {
            "import_module"
        }

    def test_a_longer_name_is_not_a_dynamic_import(self) -> None:
        engine = f"{_PACKAGE}.engine"
        assert (
            _dynamic_import_violations(
                "import importlib_x\nx = import_modules\n", engine
            )
            == set()
        )


class TestOnlyTheCliImports:
    @staticmethod
    def _module_name(path: Path) -> str:
        relative = path.relative_to(_SOURCE_ROOT.parent).with_suffix("")
        return ".".join(relative.parts)

    @staticmethod
    def _importers(sources: dict[str, str]) -> set[str]:
        """Modules outside the package that import it (any depth, any form)."""
        return {
            module
            for module, source in sources.items()
            if not _under(module, _PACKAGE)
            and any(_under(t, _PACKAGE) for t in _import_targets(source, module))
        }

    def test_only_the_cli_imports_the_package(self) -> None:
        files = [
            p
            for p in sorted(_SOURCE_ROOT.rglob("*.py"))
            if not _under(self._module_name(p), _PACKAGE)
        ]
        assert len(files) > 100, "the walk is looking at the wrong directory"
        sources = {self._module_name(p): _read(p) for p in files}
        importers = self._importers(sources)
        assert importers == {"fitdocs.cli"}

    def test_each_import_form_is_seen_and_a_non_cli_importer_is_reported(self) -> None:
        for source in (
            "import fitdocs.dashboards\n",
            "import fitdocs.dashboards.report\n",
            "from fitdocs.dashboards import report\n",
            "from fitdocs.dashboards.report import render_text\n",
            "from fitdocs import dashboards\n",
            "from . import dashboards\n",
            "from .dashboards import report\n",
            "def f():\n    from fitdocs.dashboards.report import x\n",
            "import importlib\nimportlib.import_module('fitdocs.dashboards.report')\n",
            "import importlib\n"
            "importlib.import_module('.dashboards', package='fitdocs')\n",
            "__import__('fitdocs.dashboards')\n",
        ):
            assert self._importers({"fitdocs.sync": source}) == {"fitdocs.sync"}, source

    def test_a_sibling_name_is_not_an_importer(self) -> None:
        for source in (
            "import fitdocs.dashboards_extra\n",
            "x = 'fitdocs.dashboards'\n",
            "from fitdocs import dashboard\n",
        ):
            assert self._importers({"fitdocs.sync": source}) == set(), source

    def test_a_module_inside_the_package_is_not_an_outside_importer(self) -> None:
        sources = {f"{_PACKAGE}.report": "from fitdocs.dashboards import problems\n"}
        assert self._importers(sources) == set()

    def test_the_cli_import_is_seen_by_the_scan(self) -> None:
        source = _read(_SOURCE_ROOT / "cli.py")
        targets = _import_targets(source, "fitdocs.cli")
        assert any(_under(t, _PACKAGE) for t in targets)
