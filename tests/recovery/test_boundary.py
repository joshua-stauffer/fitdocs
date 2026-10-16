"""Recovery imports, clock/network scans, engine reachability and facade closure."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path

import pytest

import fitdocs.wellness

_ROOT = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
_RECOVERY = _ROOT / "recovery"
_PLANNED_MODULES = (
    "constants",
    "baselines",
    "__init__",
    "view",
    "charts",
    "page",
    "engine",
)
_RANKS = {
    "constants": 10,
    "baselines": 20,
    "__init__": 30,
    "view": 40,
    "charts": 50,
    "page": 60,
    "engine": 70,
}
_ALLOWED_IMPORTS = {
    "constants": {
        "__future__",
        "collections.abc",
        "dataclasses",
        "enum",
        "typing",
        "fitdocs.citation",
        "fitdocs.wellness",
    },
    "baselines": {
        "__future__",
        "math",
        "dataclasses",
        "datetime",
        "enum",
        "fitdocs.recovery.constants",
        "fitdocs.wellness",
    },
    "__init__": {"fitdocs.recovery.constants", "fitdocs.recovery.baselines"},
    "view": {
        "__future__",
        "dataclasses",
        "datetime",
        "typing",
        "fitdocs.wellness",
        "fitdocs.recovery.baselines",
        "fitdocs.recovery.constants",
        "fitdocs.history",
    },
    "charts": {
        "__future__",
        "typing",
        "fitdocs.recovery.baselines",
        "fitdocs.wellness",
        "fitdocs.recovery.view",
        "fitdocs.render.charts.kit",
        "fitdocs.units",
    },
    "page": {
        "__future__",
        "json",
        "re",
        "collections.abc",
        "dataclasses",
        "datetime",
        "typing",
        "fitdocs.wellness",
        "fitdocs.recovery.baselines",
        "fitdocs.recovery.constants",
        "fitdocs.recovery.view",
        "fitdocs.contract",
        "fitdocs.layout",
        "fitdocs.render.charts.kit",
        "fitdocs.render.charts.kit.format",
        "fitdocs.render.attribution",
    },
    "engine": {
        "__future__",
        "dataclasses",
        "enum",
        "os",
        "tempfile",
        "pathlib",
        "fitdocs.wellness",
        "fitdocs.recovery.baselines",
        "fitdocs.recovery.view",
        "fitdocs.recovery.charts",
        "fitdocs.recovery.page",
        "fitdocs.history",
        "fitdocs.declaration",
        "fitdocs.layout",
        "fitdocs.contract",
        "fitdocs.render.charts.kit",
    },
}
_FORBIDDEN = {
    "duckdb",
    "fitdocs.index",
    "fitdocs.query",
    "fitdocs.dashboards",
    "fitdocs.sync",
    "fitdocs.inbox",
    "fitdocs.ingest",
    "fitdocs.model",
    "fitdocs.connectors",
    "fitdocs.tiles",
    "fitdocs.load",
    "fitdocs.benchmarks",
    "fitdocs.cli",
}
_NETWORK = {
    "http",
    "urllib",
    "socket",
    "ssl",
    "ftplib",
    "smtplib",
    "requests",
    "httpx",
    "aiohttp",
}
_CLOCK_TEXT = (
    "date.today",
    "datetime.now",
    "datetime.utcnow",
    "time.time",
    "time.monotonic",
    "astimezone()",
)


def _paths(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob("*.py")))


def _module(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _scan(
    root: Path, guard: Callable[[str, str], set[str]]
) -> tuple[set[str], set[str]]:
    visited: set[str] = set()
    violations: set[str] = set()
    for path in _paths(root):
        module = _module(root, path)
        visited.add(module)
        violations.update(guard(path.read_text(encoding="utf-8"), module))
    return visited, violations


def _check_walk(root: Path, visited: set[str]) -> None:
    expected = {_module(root, path) for path in root.glob("**/*.py")}
    assert visited, "empty recovery walk: wrong directory"
    assert visited == expected, "incomplete recovery walk"


def _base(node: ast.ImportFrom, anchor: str) -> str:
    return (
        resolve_name("." * node.level + (node.module or ""), anchor)
        if node.level
        else node.module or ""
    )


def _candidates(source: str, anchor: str) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _base(node, anchor)
            targets.add(base)
            targets.update(f"{base}.{alias.name}" for alias in node.names)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            targets.add(node.args[0].value)
    targets.update(_dynamic_targets(source, anchor))
    return targets


def _is_module(target: str) -> bool:
    if target == "fitdocs.recovery":
        return True
    if target.startswith("fitdocs.recovery."):
        relative = target.removeprefix("fitdocs.recovery.")
        return "." not in relative and (relative.islower() or relative == "__init__")
    if target.startswith("fitdocs.wellness."):
        relative = target.removeprefix("fitdocs.wellness.")
        if "." not in relative:
            return relative not in fitdocs.wellness.__all__
    if target.startswith("fitdocs."):
        path = _ROOT.joinpath(*target.split(".")[1:])
        return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()
    return False


def _import_targets(source: str) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _base(node, "fitdocs.recovery")
            modules = {
                f"{base}.{alias.name}"
                for alias in node.names
                if _is_module(f"{base}.{alias.name}")
            }
            targets.update(modules or {base})
    targets.update(_dynamic_targets(source, "fitdocs.recovery"))
    return targets


def _imports(source: str, module: str) -> set[str]:
    if module not in _RANKS:
        return {"unranked:" + module}
    measured = _import_targets(source)
    violations = (
        set() if measured == _ALLOWED_IMPORTS[module] else {"imports:" + module}
    )
    for target in measured:
        if target == "fitdocs.recovery" or target.startswith("fitdocs.recovery."):
            internal = (
                "__init__"
                if target == "fitdocs.recovery"
                else target.removeprefix("fitdocs.recovery.")
            )
            if internal not in _RANKS:
                violations.add("unranked:" + internal)
            elif _RANKS[internal] >= _RANKS[module]:
                violations.add("rank:" + internal)
        elif target.startswith("fitdocs."):
            if target not in _ALLOWED_IMPORTS[module]:
                violations.add("dependency:" + target)
        elif target.split(".")[0] not in sys.stdlib_module_names:
            violations.add("dependency:" + target)
    return violations


def _forbidden(source: str, module: str) -> set[str]:
    violations: set[str] = set()
    direct = _import_targets(source)
    for target in _candidates(source, "fitdocs.recovery"):
        for prefix in _FORBIDDEN:
            if target == prefix or target.startswith(prefix + "."):
                violations.add("forbidden:" + prefix)
        if target.startswith("fitdocs.wellness.") and (
            target in direct or _is_module(target)
        ):
            violations.add("forbidden:" + target)
    return violations


_UNKNOWN = object()


@dataclass(frozen=True)
class _Binding:
    symbol: str = ""
    literal: object = _UNKNOWN
    mapping: dict[str, _Binding] | None = None


class _Bindings(ast.NodeVisitor):
    def __init__(
        self,
        anchor: str = "fitdocs.recovery",
        bindings: dict[str, _Binding] | None = None,
    ) -> None:
        self.anchor = anchor
        self.bindings = dict(bindings or {})
        self.bindings.setdefault("__package__", _Binding(literal=anchor))
        self.class_enclosing: dict[str, _Binding] | None = None
        self.dynamic: set[str] = set()
        self.violations: set[str] = set()

    def _prime(self, statements: list[ast.stmt]) -> None:
        pending: list[ast.AST] = list(statements)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.visit(node)
            pending.extend(ast.iter_child_nodes(node))

    def visit_Module(self, node: ast.Module) -> None:
        self._prime(node.body)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            symbol = alias.name if alias.asname else alias.name.split(".")[0]
            self.bindings[name] = _Binding(symbol=symbol)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = _base(node, self.anchor)
        for alias in node.names:
            self.bindings[alias.asname or alias.name] = _Binding(
                symbol=f"{base}.{alias.name}"
            )

    def _binding(self, node: ast.expr) -> _Binding:
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id, _Binding(symbol=node.id))
        if isinstance(node, ast.Constant):
            return _Binding(literal=node.value)
        if isinstance(node, ast.Attribute):
            return _Binding(symbol=self._binding(node.value).symbol + "." + node.attr)
        if isinstance(node, ast.Dict):
            mapping: dict[str, _Binding] = {}
            for key, value in zip(node.keys, node.values, strict=True):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    return _Binding()
                mapping[key.value] = self._binding(value)
            return _Binding(mapping=mapping)
        if isinstance(node, (ast.Tuple, ast.List)):
            values = [self._binding(item).literal for item in node.elts]
            if all(value is not _UNKNOWN for value in values):
                return _Binding(literal=tuple(values))
        if isinstance(node, ast.Call):
            target = self._dynamic_target(node)
            if target is not None:
                importer = self._binding(node.func).symbol
                fromlist = self._argument(node, "fromlist", 3)
                if importer in {"__import__", "builtins.__import__"} and not (
                    fromlist and fromlist.literal is not _UNKNOWN and fromlist.literal
                ):
                    target = target.split(".")[0]
                return _Binding(symbol=target)
            name = self._binding(node.func).symbol
            if name in {"datetime.date", "datetime.datetime"}:
                return _Binding(symbol=name)
            base, _, method = name.rpartition(".")
            if base in {"datetime.date", "datetime.datetime"} and method in {
                "fromtimestamp",
                "fromisoformat",
                "astimezone",
                "replace",
            }:
                return _Binding(symbol=base)
            if name == "globals" and not node.args and not node.keywords:
                return _Binding(mapping={"__package__": _Binding(literal=self.anchor)})
        return _Binding()

    def _argument(self, node: ast.Call, name: str, position: int) -> _Binding | None:
        if len(node.args) > position and not any(
            isinstance(arg, ast.Starred) for arg in node.args[: position + 1]
        ):
            return self._binding(node.args[position])
        for keyword in node.keywords:
            if keyword.arg == name:
                return self._binding(keyword.value)
            if keyword.arg is None:
                mapping = self._binding(keyword.value).mapping
                if mapping is not None and name in mapping:
                    return mapping[name]
        return None

    def _dynamic_target(self, node: ast.Call) -> str | None:
        importer = self._binding(node.func).symbol
        if importer not in {
            "__import__",
            "builtins.__import__",
            "importlib.import_module",
        }:
            return None
        argument = self._argument(node, "name", 0)
        if argument is None or not isinstance(argument.literal, str):
            return None
        name = argument.literal
        if importer == "importlib.import_module":
            if not name.startswith("."):
                return name
            package = self._argument(node, "package", 1)
            anchor = package.literal if package else None
        else:
            level_argument = self._argument(node, "level", 4)
            level = level_argument.literal if level_argument else 0
            if not isinstance(level, int) or level < 0:
                return None
            if level == 0:
                return name if not name.startswith(".") else None
            namespace = self._argument(node, "globals", 1)
            mapping = namespace.mapping if namespace else None
            package = mapping.get("__package__") if mapping is not None else None
            anchor = package.literal if package else None
            name = "." * level + name
        if not isinstance(anchor, str):
            return None
        try:
            return resolve_name(name, anchor)
        except (ImportError, ValueError):
            return None

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        binding = self._binding(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = binding

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        if isinstance(node.target, ast.Name) and node.value is not None:
            self.bindings[node.target.id] = self._binding(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        target = self._dynamic_target(node)
        if target is not None:
            fromlist = self._argument(node, "fromlist", 3)
            names = fromlist.literal if fromlist else _UNKNOWN
            requested = (
                {
                    f"{target}.{name}"
                    for name in names
                    if isinstance(name, str) and _is_module(f"{target}.{name}")
                }
                if isinstance(names, tuple)
                else set()
            )
            self.dynamic.update(requested or {target})
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expression in node.decorator_list:
            self.visit(expression)
        self.visit(node.args)
        if node.returns:
            self.visit(node.returns)
        parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            parameters.append(node.args.vararg)
        if node.args.kwarg:
            parameters.append(node.args.kwarg)
        self._scope(node.body, [parameter.arg for parameter in parameters])
        self.bindings[node.name] = _Binding()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in [*node.bases, *node.decorator_list]:
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)
        self._scope(node.body, class_scope=True)
        self.bindings[node.name] = _Binding()

    def _scope(
        self,
        body: list[ast.stmt],
        shadowed: list[str] | None = None,
        *,
        class_scope: bool = False,
    ) -> None:
        inherited = (
            self.class_enclosing if self.class_enclosing is not None else self.bindings
        )
        child = type(self)(self.anchor, inherited)
        if class_scope:
            child.class_enclosing = inherited
        for name in shadowed or []:
            child.bindings[name] = _Binding()
        child._prime(body)
        for statement in body:
            child.visit(statement)
        self.dynamic.update(child.dynamic)
        self.violations.update(child.violations)


class _ClockGuard(_Bindings):
    def visit_Call(self, node: ast.Call) -> None:
        name = self._binding(node.func).symbol
        if name.startswith("time.") or name in {
            "datetime.date.today",
            "datetime.datetime.today",
            "datetime.datetime.now",
            "datetime.datetime.utcnow",
            "date.today",
            "datetime.today",
            "datetime.now",
            "datetime.utcnow",
        }:
            self.violations.add("clock")
        method = name.rsplit(".", 1)[-1]
        if method in {"astimezone", "fromtimestamp"}:
            position = 0 if method == "astimezone" else 1
            timezone = self._argument(node, "tz", position)
            if timezone is None or timezone.literal is None:
                self.violations.add("clock")
        super().visit_Call(node)


def _clock(source: str, module: str) -> set[str]:
    guard = _ClockGuard()
    guard.visit(ast.parse(source))
    if any(spelling in source for spelling in _CLOCK_TEXT):
        guard.violations.add("clock")
    return guard.violations


def _network(source: str, module: str) -> set[str]:
    targets = _candidates(source, "fitdocs.recovery")
    targets.update(
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )
    return {
        "network:" + prefix
        for prefix in _NETWORK
        if any(
            target == prefix or target.startswith(prefix + ".") for target in targets
        )
        or prefix + "." in source
    }


def _outside_engine_importers(root: Path) -> tuple[set[str], set[str]]:
    scanned: set[str] = set()
    importers: set[str] = set()
    for path in _paths(root):
        if path.is_relative_to(root / "recovery"):
            continue
        relative = path.relative_to(root).with_suffix("")
        parts = relative.parts[:-1] if path.name == "__init__.py" else relative.parts
        module = ".".join(("fitdocs", *parts))
        scanned.add(module)
        anchor = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
        targets = _candidates(path.read_text(encoding="utf-8"), anchor)
        if any(
            target == "fitdocs.recovery.engine"
            or target.startswith("fitdocs.recovery.engine.")
            for target in targets
        ):
            importers.add(module)
    return scanned, importers


def _check_reverse(root: Path) -> None:
    scanned, importers = _outside_engine_importers(root)
    expected = {
        ".".join(
            (
                "fitdocs",
                *(
                    path.relative_to(root).parts[:-1]
                    if path.name == "__init__.py"
                    else path.relative_to(root).with_suffix("").parts
                ),
            )
        )
        for path in root.glob("**/*.py")
        if not path.is_relative_to(root / "recovery")
    }
    assert scanned, "empty reverse walk"
    assert scanned == expected, "incomplete reverse walk"
    assert importers <= {"fitdocs.cli"}, (
        f"outside engine importers: {sorted(importers)}"
    )


def _facade_delta() -> set[str]:
    script = """
import json
import sys
import fitdocs.wellness
baseline = set(sys.modules)
import fitdocs.recovery
loaded = set(sys.modules) - baseline
print(json.dumps(sorted(loaded)))
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=_ROOT.parent.parent,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return set(json.loads(result.stdout))


def _check_facade(delta: set[str]) -> None:
    allowed = {
        "fitdocs.recovery",
        "fitdocs.recovery.constants",
        "fitdocs.recovery.baselines",
        "fitdocs.citation",
    }
    assert delta <= allowed, f"facade unexpected imports: {sorted(delta - allowed)}"


def _row_source(module: str) -> str:
    return (
        "\n".join(f"import {name}" for name in sorted(_ALLOWED_IMPORTS[module])) + "\n"
    )


def _plant(root: Path, module: str, source: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{module}.py").write_text(source, encoding="utf-8")


@pytest.mark.parametrize("module", _PLANNED_MODULES)
@pytest.mark.parametrize(
    "layer, extra, expected",
    [
        ("imports", "import fractions\n", "imports:"),
        ("forbidden", "from fitdocs import inbox as box\n", "forbidden:"),
        ("clock", '__import__("time").time()\n', "clock"),
        ("network", "import urllib.request as wire\n", "network:"),
    ],
)
def test_every_planned_module_is_scanned(
    tmp_path: Path, module: str, layer: str, extra: str, expected: str
) -> None:
    guards = {
        "imports": _imports,
        "forbidden": _forbidden,
        "clock": _clock,
        "network": _network,
    }
    other = "constants" if module != "constants" else "baselines"
    _plant(tmp_path, other, _row_source(other))
    _plant(tmp_path, module, _row_source(module) + extra)
    visited, violations = _scan(tmp_path, guards[layer])
    _check_walk(tmp_path, visited)
    assert any(item.startswith(expected) for item in violations), sorted(violations)


@pytest.mark.parametrize("module", _PLANNED_MODULES)
def test_allowed_row_passes_and_removed_import_fails(
    tmp_path: Path, module: str
) -> None:
    _plant(tmp_path, module, _row_source(module))
    visited, violations = _scan(tmp_path, _imports)
    _check_walk(tmp_path, visited)
    assert not violations, sorted(violations)
    first, _, remainder = _row_source(module).partition("\n")
    _plant(tmp_path, module, remainder)
    _, violations = _scan(tmp_path, _imports)
    assert violations == {f"imports:{module}"}, (first, violations)


@pytest.mark.parametrize(
    "source, module, expected",
    [
        ("from . import engine", "constants", "rank:engine"),
        ("from .baselines import Baselines", "constants", "rank:baselines"),
        ("import fitdocs.recovery.constants", "constants", "rank:constants"),
        ("from fitdocs import recovery", "baselines", "rank:__init__"),
        ("from . import unknown", "engine", "unranked:unknown"),
        ("import numpy", "engine", "dependency:numpy"),
        (
            "from fitdocs.render.charts.kit import describe_kinds",
            "view",
            "imports:view",
        ),
        (
            "from fitdocs.wellness import series",
            "engine",
            "forbidden:fitdocs.wellness.series",
        ),
    ],
)
def test_import_directions_and_dependencies(
    tmp_path: Path, source: str, module: str, expected: str
) -> None:
    guard = _forbidden if expected.startswith("forbidden:") else _imports
    _plant(tmp_path, module, _row_source(module) + source + "\n")
    _, violations = _scan(tmp_path, guard)
    assert expected in violations, sorted(violations)


@pytest.mark.parametrize(
    "target",
    sorted(_FORBIDDEN) + ["fitdocs.wellness.series", "fitdocs.wellness.unplanned"],
)
@pytest.mark.parametrize("style", ("direct", "aliased", "from", "relative", "nested"))
def test_forbidden_import_spellings(tmp_path: Path, target: str, style: str) -> None:
    parent, _, name = target.rpartition(".")
    forms = {
        "direct": f"import {target}",
        "aliased": f"import {target} as forbidden_alias",
        "from": f"from {parent} import {name} as forbidden_alias"
        if parent
        else f"import {target}",
        "relative": f"from ..{parent.removeprefix('fitdocs').lstrip('.')} import {name}"
        if parent
        else f"import {target}",
        "nested": (
            f"class Scope:\n    def method(self):\n        import {target} as hidden"
        ),
    }
    _plant(tmp_path, "constants", forms[style] + "\n")
    _, violations = _scan(tmp_path, _forbidden)
    assert f"forbidden:{target}" in violations, sorted(violations)


@pytest.mark.parametrize(
    "source",
    [
        "import datetime; datetime.date.today()",
        "import datetime as d; d.datetime.now()",
        "from datetime import date as d; d.today()",
        "from datetime import datetime as d; d.utcnow()",
        "import time as t; t.monotonic()",
        "from time import time as read; read()",
        '__import__("time").time()',
        'import importlib as i; i.import_module("time").time()',
        (
            "def outer():\n    from datetime import date as d\n"
            "    def inner():\n        return d.today()"
        ),
        "class Scope:\n    import time as t\n    value = t.time()",
        (
            "class Scope:\n    def method(self):\n"
            "        import time as t\n        return t.time()"
        ),
        "value.astimezone()",
        "value.astimezone(tz=None)",
        "value.astimezone(None)",
        "value.fromtimestamp(123)",
        'example = "date.today"',
    ],
)
def test_clock_and_machine_timezone_spellings(tmp_path: Path, source: str) -> None:
    _plant(tmp_path, "baselines", source + "\n")
    _, violations = _scan(tmp_path, _clock)
    assert "clock" in violations, sorted(violations)


@pytest.mark.parametrize("target", sorted(_NETWORK))
@pytest.mark.parametrize("style", ("import", "from", "dynamic", "importlib", "text"))
def test_network_spellings(tmp_path: Path, target: str, style: str) -> None:
    sources = {
        "import": f"def nested():\n    import {target} as transport",
        "from": f"from {target} import client as transport",
        "dynamic": f'__import__("{target}")',
        "importlib": f'import importlib as i; i.import_module("{target}")',
        "text": f'example = "{target}.client"',
    }
    _plant(tmp_path, "engine", sources[style] + "\n")
    _, violations = _scan(tmp_path, _network)
    assert f"network:{target}" in violations, sorted(violations)


@pytest.mark.parametrize("relative", [".", "missing"])
def test_walk_rejects_empty_wrong_and_partial_roots(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(AssertionError, match="empty"):
        _check_walk(tmp_path / relative, set())
    _plant(tmp_path, "constants", _row_source("constants"))
    _plant(tmp_path, "engine", _row_source("engine"))
    with pytest.raises(AssertionError, match="incomplete"):
        _check_walk(tmp_path, {"constants"})


def test_unknown_module_is_scanned_and_rejected(tmp_path: Path) -> None:
    _plant(tmp_path, "constants", _row_source("constants"))
    _plant(tmp_path, "unplanned", "pass\n")
    visited, violations = _scan(tmp_path, _imports)
    _check_walk(tmp_path, visited)
    assert violations == {"unranked:unplanned"}


@pytest.mark.parametrize(
    "source",
    [
        "import fitdocs.recovery.engine as e",
        "from fitdocs.recovery import engine as e",
        "from ..recovery.engine import run_recovery",
        "from ..recovery import engine",
        (
            "class Scope:\n    def method(self):\n"
            "        from fitdocs.recovery.engine import run_recovery"
        ),
    ],
)
@pytest.mark.parametrize("package_marker", [False, True], ids=["leaf", "package"])
def test_reverse_walk_rejects_scanned_outside_importer(
    tmp_path: Path, source: str, package_marker: bool
) -> None:
    _plant(tmp_path / "recovery", "engine", "pass\n")
    _plant(tmp_path, "cli", "from fitdocs.recovery import engine\n")
    _plant(tmp_path / "other", "valid", "import math\n")
    bad = "__init__" if package_marker else "bad"
    bad_name = "fitdocs.other" if package_marker else "fitdocs.other.bad"
    _plant(tmp_path / "other", bad, source + "\n")
    scanned, importers = _outside_engine_importers(tmp_path)
    assert scanned == {"fitdocs.cli", "fitdocs.other.valid", bad_name}
    assert importers == {"fitdocs.cli", bad_name}
    with pytest.raises(AssertionError, match="outside"):
        _check_reverse(tmp_path)


def test_reverse_walk_rejects_empty_and_accepts_only_cli(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="empty"):
        _check_reverse(tmp_path)
    _plant(tmp_path, "cli", "from fitdocs.recovery import engine\n")
    _check_reverse(tmp_path)
    _plant(tmp_path, "cli", "import math\n")
    _check_reverse(tmp_path)


@pytest.mark.parametrize(
    "unexpected",
    ["fitdocs.history", "fitdocs.render", "fitdocs.recovery.engine", "fitdocs.units"],
)
def test_facade_closure_positive_control(unexpected: str) -> None:
    with pytest.raises(AssertionError, match="facade"):
        _check_facade({"fitdocs.recovery", unexpected})


def test_design_rows_cover_every_planned_module() -> None:
    assert set(_RANKS) == set(_PLANNED_MODULES)
    assert set(_ALLOWED_IMPORTS) == set(_PLANNED_MODULES)


def test_recovery_import_rows() -> None:
    visited, violations = _scan(_RECOVERY, _imports)
    _check_walk(_RECOVERY, visited)
    assert not violations, sorted(violations)


@pytest.mark.parametrize(
    "guard", [_forbidden, _clock, _network], ids=["forbidden", "clock", "network"]
)
def test_recovery_forbidden_imports_clock_and_network(
    guard: Callable[[str, str], set[str]],
) -> None:
    visited, violations = _scan(_RECOVERY, guard)
    _check_walk(_RECOVERY, visited)
    assert not violations, sorted(violations)


def test_only_cli_may_import_recovery_engine() -> None:
    _check_reverse(_ROOT)


def test_facade_import_delta_in_fresh_interpreter() -> None:
    delta = _facade_delta()
    assert {
        "fitdocs.recovery",
        "fitdocs.recovery.constants",
        "fitdocs.recovery.baselines",
    } <= delta
    _check_facade(delta)


def test_reverse_walk_rejects_partial_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _plant(tmp_path, "cli", "import math\n")
    _plant(tmp_path, "other", "import math\n")
    monkeypatch.setattr(
        sys.modules[__name__],
        "_outside_engine_importers",
        lambda root: ({"fitdocs.cli"}, set()),
    )
    with pytest.raises(AssertionError, match="incomplete"):
        _check_reverse(tmp_path)


_DYNAMIC_STYLES = (
    "builtin",
    "builtin_import",
    "builtin_assign",
    "builtin_annotated",
    "importlib",
    "importlib_import",
    "importlib_assign",
    "importlib_chain",
)


def _dynamic_source(style: str, target: str) -> str:
    forms = {
        "builtin": f"__import__({target!r})",
        "builtin_import": f"from builtins import __import__ as load; load({target!r})",
        "builtin_assign": f"load = __import__; again = load; again({target!r})",
        "builtin_annotated": f"load: object = __import__; a = b = load; b({target!r})",
        "importlib": f"import importlib as library; library.import_module({target!r})",
        "importlib_import": (
            f"from importlib import import_module as load; load({target!r})"
        ),
        "importlib_assign": (
            f"library: object = __import__('importlib'); load = library.import_module; "
            f"again = load; again({target!r})"
        ),
        "importlib_chain": f"__import__('importlib').import_module({target!r})",
    }
    return forms[style] + "\n"


def _dynamic_targets(source: str, anchor: str) -> set[str]:
    guard = _Bindings(anchor)
    guard.visit(ast.parse(source))
    return guard.dynamic


@pytest.mark.parametrize("style", _DYNAMIC_STYLES)
@pytest.mark.parametrize("nested", [False, True], ids=["module", "function"])
def test_literal_dynamic_targets_and_aliases(style: str, nested: bool) -> None:
    source = _dynamic_source(style, "fitdocs.inbox")
    if nested:
        source = "def probe():\n" + "\n".join(
            "    " + line for line in source.splitlines()
        )
    expected = {"fitdocs.inbox"}
    if style in {"importlib_assign", "importlib_chain"}:
        expected.add("importlib")
    assert _dynamic_targets(source, "fitdocs.recovery") == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "import importlib; importlib.import_module('..inbox', package=__package__)",
            {"fitdocs.inbox"},
        ),
        (
            (
                "from importlib import import_module as load; package = '"
                "fitdocs'; load('.inbox', package)"
            ),
            {"fitdocs.inbox"},
        ),
        (
            (
                "load = __import__('importlib').import_module; package: s"
                "tr = 'fitdocs'; load(name='.inbox', package=package)"
            ),
            {"importlib", "fitdocs.inbox"},
        ),
        (
            "__import__('inbox', globals={'__package__': 'fitdocs'}, level=1)",
            {"fitdocs.inbox"},
        ),
        (
            "load: object = __import__; load('inbox', globals=globals(), level=2)",
            {"fitdocs.inbox"},
        ),
        (
            (
                "load = __import__; name: str = 'numpy'; another = name; "
                "load(name=another)"
            ),
            {"numpy"},
        ),
        (
            (
                "import importlib; args = {'name': '.inbox', 'package': '"
                "fitdocs'}; importlib.import_module(**args)"
            ),
            {"fitdocs.inbox"},
        ),
    ],
)
def test_relative_and_keyword_literal_dynamic_targets(
    source: str, expected: set[str]
) -> None:
    assert _dynamic_targets(source, "fitdocs.recovery") == expected


@pytest.mark.parametrize(
    "source",
    [
        "__import__(compute_name())",
        "import importlib; importlib.import_module('.inbox')",
        "import importlib; importlib.import_module('.inbox', package=get_package())",
        "load = ordinary_method; load('fitdocs.inbox')",
        "load = __import__; load = ordinary_method; load('fitdocs.inbox')",
        (
            "import importlib as load; def_placeholder = float; load "
            "= def_placeholder; load('fitdocs.inbox')"
        ),
        "def probe(__import__):\n    __import__('numpy')",
    ],
)
def test_dynamic_target_resolution_has_finite_limits(source: str) -> None:
    assert _dynamic_targets(source, "fitdocs.recovery") == set()


@pytest.mark.parametrize(
    "source",
    [
        "timer = __import__('time'); timer.perf_counter()",
        "timer: object = __import__('time'); timer.perf_counter()",
        "root = __import__('time'); timer = root; timer.process_time()",
        "first = second = __import__('time'); second.perf_counter()",
        "from datetime import datetime as stamp; read_clock = stamp.now; read_clock()",
        (
            "from datetime import datetime as stamp; read_clock: obje"
            "ct = stamp.now; read_clock()"
        ),
        (
            "from datetime import datetime as stamp; read = stamp.utc"
            "now; again = read; again()"
        ),
        "stamp = __import__('datetime').datetime; read = stamp.today; read()",
        "from time import perf_counter as read; again: object = read; again()",
        (
            "load = __import__; timer = load('time'); read = timer.pe"
            "rf_counter; again = read; again()"
        ),
        (
            "def outer():\n    timer: object = __import__('time')\n    "
            "def inner():\n        timer.perf_counter()"
        ),
        (
            "class Scope:\n    timer = __import__('time')\n    value = "
            "timer.perf_counter()"
        ),
        (
            "class Scope:\n    def method(self):\n        timer: object"
            " = __import__('time')\n        timer.perf_counter()"
        ),
        "import time as timer\ndef probe():\n    read = timer.perf_counter\n    read()",
    ],
)
def test_assigned_clock_aliases(source: str, tmp_path: Path) -> None:
    _plant(tmp_path, "baselines", source + "\n")
    _, violations = _scan(tmp_path, _clock)
    assert violations == {"clock"}


@pytest.mark.parametrize(
    "source",
    [
        "__import__('datetime').datetime.fromtimestamp(timestamp=float())",
        (
            "__import__('datetime').datetime.fromtimestamp(float(), _"
            "_import__('datetime').timezone.utc).astimezone(**{})"
        ),
        "__import__('datetime').datetime.fromtimestamp(timestamp=float(), **options)",
        "__import__('datetime').datetime.fromtimestamp(float(), **{})",
        "value.astimezone(**options)",
        "value.astimezone(**{'tz': None})",
        "zone = None; value.astimezone(tz=zone)",
        (
            "zone: object = None; other = zone; value.fromtimestamp(t"
            "imestamp=float(), tz=other)"
        ),
        "value.fromtimestamp(timestamp=float(), tz=None)",
        "read = __import__('datetime').datetime.fromtimestamp; read(timestamp=float())",
        "convert = value.astimezone; again = convert; again(**{})",
    ],
)
def test_timezone_presence_uses_its_actual_argument(
    source: str, tmp_path: Path
) -> None:
    _plant(tmp_path, "baselines", source + "\n")
    _, violations = _scan(tmp_path, _clock)
    assert violations == {"clock"}


@pytest.mark.parametrize(
    "source",
    [
        (
            "from datetime import datetime, UTC; datetime.fromtimesta"
            "mp(float(), UTC).astimezone(UTC)"
        ),
        (
            "__import__('datetime').datetime.fromtimestamp(timestamp="
            "float(), tz=__import__('datetime').timezone.utc)"
        ),
        (
            "__import__('datetime').datetime.fromtimestamp(float(), _"
            "_import__('datetime').timezone.utc)"
        ),
        (
            "from datetime import datetime, timezone; zone = timezone"
            ".utc; datetime.fromtimestamp(timestamp=float(), tz=zone)"
        ),
        (
            "from datetime import datetime, UTC; zone: object = UTC; "
            "stamp = datetime.fromtimestamp(float(), zone); stamp.ast"
            "imezone(tz=UTC)"
        ),
        (
            "from datetime import datetime, UTC; stamp = datetime.fro"
            "mtimestamp(float(), UTC); stamp.astimezone(**{'tz': UTC}"
            ")"
        ),
        (
            "from datetime import datetime, UTC; args = {'timestamp':"
            " float(), 'tz': UTC}; datetime.fromtimestamp(**args)"
        ),
        (
            "from datetime import datetime, UTC; args = {'tz': UTC}; "
            "stamp = datetime.fromtimestamp(float(), UTC); stamp.asti"
            "mezone(**args)"
        ),
        "from datetime import date; value = date(2000, 1, 1); value.isoformat()",
        (
            "from datetime import datetime; value = datetime(2000, 1,"
            " 1); value.isoformat()"
        ),
        (
            "class Ordinary:\n    def now(self):\n        return float("
            ")\nvalue = Ordinary(); read = value.now; read()"
        ),
        (
            "import time as timer\nclass Ordinary:\n    def perf_counte"
            "r(self):\n        return float()\ndef consume(timer):\n    "
            "return timer.perf_counter()\nconsume(Ordinary())"
        ),
        (
            "import time as timer\nclass Ordinary:\n    def perf_counte"
            "r(self):\n        return float()\ntimer = Ordinary(); time"
            "r.perf_counter()"
        ),
        (
            "def first():\n    timer = __import__('time')\nclass Ordina"
            "ry:\n    def perf_counter(self):\n        return float()\nd"
            "ef second():\n    timer = Ordinary(); return timer.perf_c"
            "ounter()\nsecond()"
        ),
    ],
)
def test_explicit_utc_constructors_and_ordinary_methods_are_accepted(
    source: str, tmp_path: Path
) -> None:
    exec(source, {})
    _plant(tmp_path, "baselines", source + "\n")
    _, violations = _scan(tmp_path, _clock)
    assert not violations, sorted(violations)


@pytest.mark.parametrize("module", _PLANNED_MODULES)
@pytest.mark.parametrize(
    "layer, extra, expected",
    [
        ("imports", "def probe():\n    return __import__('numpy')", "dependency:numpy"),
        (
            "forbidden",
            (
                "def probe():\n    return __import__('importlib').import_m"
                "odule('fitdocs.inbox')"
            ),
            "forbidden:fitdocs.inbox",
        ),
        (
            "network",
            (
                "module = 'socket'; load = __import__('importlib').import"
                "_module; load(module)"
            ),
            "network:socket",
        ),
        (
            "clock_alias",
            "timer: object = __import__('time'); read = timer.perf_counter; read()",
            "clock",
        ),
        (
            "timezone",
            "__import__('datetime').datetime.fromtimestamp(timestamp=float())",
            "clock",
        ),
    ],
)
def test_round2_inputs_are_scanned_in_every_planned_module(
    tmp_path: Path, module: str, layer: str, extra: str, expected: str
) -> None:
    guards = {
        "imports": _imports,
        "forbidden": _forbidden,
        "network": _network,
        "clock_alias": _clock,
        "timezone": _clock,
    }
    other = "constants" if module != "constants" else "baselines"
    _plant(tmp_path, other, _row_source(other))
    _plant(tmp_path, module, _row_source(module) + extra + "\n")
    visited, violations = _scan(tmp_path, guards[layer])
    _check_walk(tmp_path, visited)
    assert expected in violations, sorted(violations)


@pytest.mark.parametrize("style", _DYNAMIC_STYLES)
@pytest.mark.parametrize(
    "target, guard, expected",
    [
        ("numpy", _imports, "dependency:numpy"),
        ("fitdocs.recovery.engine", _imports, "rank:engine"),
        ("fitdocs.inbox", _forbidden, "forbidden:fitdocs.inbox"),
        ("fitdocs.wellness.series", _forbidden, "forbidden:fitdocs.wellness.series"),
        ("socket", _network, "network:socket"),
    ],
)
def test_dynamic_targets_reach_their_intended_guard(
    tmp_path: Path,
    style: str,
    target: str,
    guard: Callable[[str, str], set[str]],
    expected: str,
) -> None:
    _plant(
        tmp_path, "constants", _row_source("constants") + _dynamic_source(style, target)
    )
    _, violations = _scan(tmp_path, guard)
    assert expected in violations, sorted(violations)


@pytest.mark.parametrize("module", _PLANNED_MODULES)
def test_dynamic_import_of_an_already_pinned_target_is_accepted(
    tmp_path: Path, module: str
) -> None:
    target = sorted(_ALLOWED_IMPORTS[module])[0]
    _plant(
        tmp_path,
        module,
        _row_source(module) + f"load = __import__; module = {target!r}; load(module)\n",
    )
    visited, violations = _scan(tmp_path, _imports)
    _check_walk(tmp_path, visited)
    assert not violations, sorted(violations)


@pytest.mark.parametrize("style", _DYNAMIC_STYLES)
@pytest.mark.parametrize("package_marker", [False, True], ids=["leaf", "package"])
def test_dynamic_engine_importers_are_scanned_and_rejected(
    tmp_path: Path, style: str, package_marker: bool
) -> None:
    _plant(tmp_path / "recovery", "engine", "pass\n")
    _plant(tmp_path, "cli", "import math\n")
    _plant(tmp_path / "other", "valid", "import math\n")
    bad = "__init__" if package_marker else "bad"
    bad_name = "fitdocs.other" if package_marker else "fitdocs.other.bad"
    _plant(tmp_path / "other", bad, _dynamic_source(style, "fitdocs.recovery.engine"))
    scanned, importers = _outside_engine_importers(tmp_path)
    assert scanned == {"fitdocs.cli", "fitdocs.other.valid", bad_name}
    assert importers == {bad_name}
    with pytest.raises(AssertionError, match="outside"):
        _check_reverse(tmp_path)


@pytest.mark.parametrize("package_marker", [False, True], ids=["leaf", "package"])
def test_relative_dynamic_engine_importer_and_cli_subset(
    tmp_path: Path, package_marker: bool
) -> None:
    _plant(tmp_path / "recovery", "engine", "pass\n")
    source = (
        "from importlib import import_module as load; load('..rec"
        "overy.engine', package=__package__)\n"
    )
    bad = "__init__" if package_marker else "bad"
    bad_name = "fitdocs.other" if package_marker else "fitdocs.other.bad"
    _plant(tmp_path / "other", bad, source)
    scanned, importers = _outside_engine_importers(tmp_path)
    assert scanned == {bad_name}
    assert importers == {bad_name}
    with pytest.raises(AssertionError, match="outside"):
        _check_reverse(tmp_path)
    _plant(tmp_path / "other", bad, "import math\n")
    _plant(
        tmp_path, "cli", _dynamic_source("importlib_chain", "fitdocs.recovery.engine")
    )
    _check_reverse(tmp_path)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("__import__('fitdocs', fromlist=('inbox',))", {"fitdocs.inbox"}),
        (
            (
                "load: object = __import__; names = ['series']; load('fit"
                "docs.wellness', fromlist=names)"
            ),
            {"fitdocs.wellness.series"},
        ),
        (
            "__import__('fitdocs.recovery', fromlist=['engine'])",
            {"fitdocs.recovery.engine"},
        ),
        ("__import__('fitdocs.wellness', fromlist=['Metric'])", {"fitdocs.wellness"}),
        ("__import__('fitdocs.recovery', fromlist=['*'])", {"fitdocs.recovery"}),
    ],
)
def test_literal_fromlist_distinguishes_modules_from_public_objects(
    source: str, expected: set[str]
) -> None:
    assert _dynamic_targets(source, "fitdocs.recovery") == expected


@pytest.mark.parametrize("kind", ["clock", "dynamic"])
def test_class_locals_do_not_leak_into_method_global_names(kind: str) -> None:
    sources = {
        "clock": """
class Ordinary:
    def perf_counter(self):
        return float()
timer = Ordinary()
class Scope:
    timer = __import__('time')
    def read(self):
        return timer.perf_counter()
Scope().read()
""",
        "dynamic": """
def load(name):
    return float()
class Scope:
    load = __import__
    def read(self):
        return load('numpy')
Scope().read()
""",
    }
    source = sources[kind]
    exec(source, {})
    if kind == "clock":
        violations = _clock(source, "baselines")
    else:
        violations = _dynamic_targets(source, "fitdocs.recovery")
    assert not violations, sorted(violations)
