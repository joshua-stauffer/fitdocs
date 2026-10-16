"""Import ranks and the heart-rate package's allowed dependencies."""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2] / "src" / "fitdocs" / "hr_benchmarks"
_PACKAGE = "fitdocs.hr_benchmarks"
_RANKS = {
    "types": 10,
    "sources": 20,
    "peaks": 30,
    "maximum": 30,
    "resting": 30,
    "timeline": 40,
    "inspect": 50,
    "engine": 60,
    "__init__": 70,
}
_PURE_STDLIB = {
    "__future__",
    "array",
    "bisect",
    "contextlib",
    "copy",
    "decimal",
    "fractions",
    "heapq",
    "numbers",
    "operator",
    "re",
    "string",
    "collections",
    "collections.abc",
    "dataclasses",
    "datetime",
    "enum",
    "functools",
    "itertools",
    "math",
    "statistics",
    "typing",
}
_ENGINE_STDLIB = {"pathlib", "re", "tomllib"}
_EXTERNAL = {"fitdocs.benchmarks", "fitdocs.citation"}
_ENGINE_EXTERNAL = {
    "fitdocs.compose.archive",
    "fitdocs.contract",
    "fitdocs.docio",
    "fitdocs.layout",
    "fitdocs.load.profile",
    "fitdocs.load.settings",
    "fitdocs.settings",
    "fitdocs.wellness",
}
_MODEL_NAMES = {"Samples", "Modality", "Sport"}


def _module_paths(root: Path = _ROOT) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _module_key(path: Path, root: Path = _ROOT) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _from_base(node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    try:
        return resolve_name("." * node.level + (node.module or ""), _PACKAGE)
    except ImportError:
        return "invalid-relative-import"


def _allowed_import(target: str, module: str, name: str | None) -> bool:
    if target == _PACKAGE or target.startswith(_PACKAGE + "."):
        key = "__init__" if target == _PACKAGE else target.removeprefix(_PACKAGE + ".")
        return key in _RANKS and _RANKS[key] < _RANKS[module]
    if target in _PURE_STDLIB or target in _EXTERNAL:
        return True
    if target == "fitdocs.model":
        return name in _MODEL_NAMES
    if module == "peaks" and target == "fitdocs.load.qa.cadence":
        return True
    if module == "peaks" and target == "fitdocs.load.qa.types":
        return name == "FlagSettings"
    if module == "engine":
        if target in _ENGINE_STDLIB or target in _ENGINE_EXTERNAL:
            return True
        if target == "fitdocs":
            return name in {"parse_fit", "FitDecodeError"}
    return False


def _import_violations(source: str, module: str) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _allowed_import(alias.name, module, None):
                    violations.append(f"L{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node)
            for alias in node.names:
                target = base
                name: str | None = alias.name
                if (
                    base == _PACKAGE
                    or (
                        base == "fitdocs"
                        and alias.name not in {"parse_fit", "FitDecodeError"}
                    )
                    or (
                        base == "fitdocs.wellness"
                        and alias.name
                        in {
                            "archive",
                            "series",
                            "engine",
                            "intake",
                            "settings",
                            "model",
                            "merge",
                            "probe",
                            "spec",
                            "formats",
                            "registry",
                            "inspect",
                        }
                    )
                ):
                    target = base + "." + alias.name
                    name = None
                if alias.name == "*" or not _allowed_import(target, module, name):
                    violations.append(
                        f"L{node.lineno}: from {target} import {alias.name}"
                    )
    return violations


def test_import_walk_covers_disk() -> None:
    paths = _module_paths()
    assert paths, "empty heart-rate module walk"
    assert set(paths) == set(_ROOT.rglob("*.py")), "incomplete module walk"
    for path in paths:
        key = _module_key(path)
        assert key in _RANKS, f"unranked module: {key}"
        assert _import_violations(path.read_text(), key) == [], str(path)


@pytest.mark.parametrize(
    "source,module",
    [
        ("import fitdocs.index", "types"),
        ("from fitdocs import query as q", "engine"),
        ("from .. import index as ix", "engine"),
        ("from fitdocs.index.store import connect", "engine"),
        ("import duckdb as db", "engine"),
        ("from fitdocs import performance", "engine"),
        ("import fitdocs.render", "engine"),
        ("from fitdocs import sync", "engine"),
        ("from fitdocs import cli", "engine"),
        ("import fitdocs.wellness.series as s", "engine"),
        ("from fitdocs.wellness import series", "engine"),
        ("from ..wellness import archive", "engine"),
        ("from fitdocs.wellness import read_series", "resting"),
        ("from pathlib import Path", "maximum"),
        ("from fitdocs.layout import wellness_series_path", "resting"),
        ("from fitdocs import parse_fit", "peaks"),
        ("from fitdocs import something_else", "engine"),
        ("from fitdocs.hr_benchmarks.timeline import derive_timeline", "sources"),
        ("from .maximum import max_evidence", "peaks"),
        ("from . import engine", "timeline"),
        ("import fitdocs.hr_benchmarks", "engine"),
        ("from fitdocs.hr_benchmarks.unknown import x", "engine"),
        ("from .types import *", "sources"),
        ("from fitdocs.model import Activity", "types"),
        ("import fitdocs.model as m", "peaks"),
        ("from fitdocs.load.qa.types import FlagSettings", "maximum"),
        ("from fitdocs.load.qa.types import FlagKind", "peaks"),
        ("from fitdocs.load.qa.cadence import cadence_lock", "resting"),
        ("import socket", "engine"),
        ("from urllib.request import urlopen", "engine"),
        ("import time", "engine"),
        ("import rich.prompt", "engine"),
        ("def f():\n    from fitdocs.index import store", "engine"),
        ("from .... import index", "engine"),
    ],
)
def test_forbidden_import(source: str, module: str) -> None:
    assert _import_violations(source, module)


@pytest.mark.parametrize(
    "source,module",
    [
        ("from dataclasses import dataclass\nfrom datetime import date", "types"),
        ("from bisect import bisect_left\nfrom heapq import nlargest", "maximum"),
        ("from operator import attrgetter\nfrom fractions import Fraction", "maximum"),
        (
            "from decimal import Decimal\nfrom collections.abc import Iterable",
            "resting",
        ),
        ("from fitdocs.benchmarks import Benchmark, BenchmarkKind", "types"),
        ("from fitdocs.model import Sport as S", "types"),
        ("from fitdocs.model import Samples, Modality", "peaks"),
        ("from fitdocs.citation import CitedConstant", "sources"),
        ("from fitdocs.hr_benchmarks.types import HrMethod", "sources"),
        ("from .types import Evidence as E", "timeline"),
        ("from . import sources as s", "maximum"),
        ("import fitdocs.hr_benchmarks.sources as s", "maximum"),
        ("from fitdocs.hr_benchmarks import peaks", "timeline"),
        ("from fitdocs.load.qa.types import FlagSettings as F", "peaks"),
        ("import fitdocs.load.qa.cadence as c", "peaks"),
        ("from pathlib import Path", "engine"),
        ("from fitdocs import parse_fit, FitDecodeError", "engine"),
        ("from fitdocs.wellness import read_series, Metric", "engine"),
        ("from .. import wellness as w", "engine"),
        ("from fitdocs.compose.archive import compose_archived", "engine"),
        ("from fitdocs.load.profile import load_profile", "engine"),
        ("from .engine import derive_hr_benchmarks", "__init__"),
        ("from .types import HrStageReport", "__init__"),
        ("from .timeline import derive_timeline", "inspect"),
        ("from .inspect import inconsistencies", "engine"),
    ],
)
def test_sanctioned_import(source: str, module: str) -> None:
    assert _import_violations(source, module) == []


_MODULE_FILES = {
    "__init__.py",
    "types.py",
    "sources.py",
    "peaks.py",
    "maximum.py",
    "resting.py",
    "timeline.py",
    "inspect.py",
    "engine.py",
}


def test_literal_module_inventory() -> None:
    assert {
        path.relative_to(_ROOT).as_posix() for path in _module_paths(_ROOT)
    } == _MODULE_FILES


def _fitdocs_paths(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _references(source: str, module: str) -> set[str]:
    """Resolve static imports, attribute chains and literal dynamic imports.

    Simple name assignments are aliases. Computed strings, getattr and exec are
    outside this syntax inventory.
    """
    tree = ast.parse(source)
    aliases: dict[str, str] = {"__import__": "__import__"}
    targets: set[str] = set()
    package = module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split(".")[0]] = (
                    item.name if item.asname else item.name.split(".")[0]
                )
                targets.add(item.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            for item in node.names:
                target = base + "." + item.name
                aliases[item.asname or item.name] = target
                targets.add(target)

    def qualified(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return aliases.get(node.id)
        if isinstance(node, ast.Attribute):
            base = qualified(node.value)
            return None if base is None else base + "." + node.attr
        if isinstance(node, ast.Call):
            function = qualified(node.func)
            if function in {"__import__", "importlib.import_module"} and node.args:
                argument = node.args[0]
                if isinstance(argument, ast.Constant) and isinstance(
                    argument.value, str
                ):
                    target = argument.value
                    if function == "__import__":
                        level = next(
                            (kw.value for kw in node.keywords if kw.arg == "level"),
                            node.args[4] if len(node.args) > 4 else None,
                        )
                        if (
                            isinstance(level, ast.Constant)
                            and isinstance(level.value, int)
                            and level.value > 0
                        ):
                            target = resolve_name("." * level.value + target, package)
                    if target.startswith("."):
                        literal_package = next(
                            (kw.value for kw in node.keywords if kw.arg == "package"),
                            node.args[1] if len(node.args) > 1 else None,
                        )
                        if not isinstance(
                            literal_package, ast.Constant
                        ) or not isinstance(literal_package.value, str):
                            return None
                        target = resolve_name(target, literal_package.value)
                    return target
        return None

    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    for _ in range(len(assignments) + 1):
        for node in assignments:
            value = qualified(node.value)
            if value is not None:
                for binding in node.targets:
                    if isinstance(binding, ast.Name):
                        aliases[binding.id] = value
    for node in ast.walk(tree):
        value = qualified(node)
        if value is not None:
            targets.add(value)
            if isinstance(node, ast.Call) and qualified(node.func) == "__import__":
                fromlist = next(
                    (kw.value for kw in node.keywords if kw.arg == "fromlist"), None
                )
                if fromlist is None and len(node.args) > 3:
                    fromlist = node.args[3]
                if isinstance(fromlist, (ast.List, ast.Tuple)):
                    targets.update(
                        value + "." + item.value
                        for item in fromlist.elts
                        if isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    )
    return targets


def _external_violations(source: str, module: str) -> list[str]:
    if module == _PACKAGE or module.startswith(_PACKAGE + "."):
        return []
    targets = {
        target
        for target in _references(source, module)
        if target == _PACKAGE or target.startswith(_PACKAGE + ".")
    }
    if module == "fitdocs.cli":
        allowed = {
            _PACKAGE,
            *(
                _PACKAGE + "." + name
                for name in (
                    "HrStageReport",
                    "HrStageSettings",
                    "derive_hr_benchmarks",
                    "load_hr_stage_settings",
                    "engine",
                )
            ),
            *(
                _PACKAGE + ".engine." + name
                for name in (
                    "HrStageSettings",
                    "derive_hr_benchmarks",
                    "load_hr_stage_settings",
                )
            ),
        }
        targets -= allowed
    elif module == "fitdocs.audit":
        targets = {
            target
            for target in targets
            if target != _PACKAGE + ".inspect"
            and not target.startswith(_PACKAGE + ".inspect.")
        }
    return sorted(targets)


def test_external_walk_includes_callers_and_downstream_packages() -> None:
    root = _ROOT.parent
    assert {
        "cli.py",
        "audit.py",
        "sync.py",
        "load/__init__.py",
        "load/threshold/__init__.py",
        "load/channels/__init__.py",
        "load/qa/__init__.py",
        "performance/__init__.py",
        "wellness/__init__.py",
        "index/__init__.py",
    } <= {path.relative_to(root).as_posix() for path in _fitdocs_paths(root)}


def test_external_walk_matches_disk() -> None:
    root = _ROOT.parent
    assert set(_fitdocs_paths(root)) == set(root.rglob("*.py"))


def test_only_cli_and_audit_import_the_hr_stage() -> None:
    root = _ROOT.parent
    assert [
        (path.relative_to(root).as_posix(), violation)
        for path in _fitdocs_paths(root)
        for violation in _external_violations(
            path.read_text(),
            "fitdocs." + _module_key(path, root),
        )
    ] == []


@pytest.mark.parametrize(
    "module,source,forbidden",
    [
        (
            "fitdocs.cli",
            "from fitdocs.hr_benchmarks import derive_hr_benchmarks as run",
            False,
        ),
        (
            "fitdocs.cli",
            "from .hr_benchmarks.engine import derive_hr_benchmarks",
            False,
        ),
        (
            "fitdocs.cli",
            "from fitdocs.hr_benchmarks import "
            "HrStageReport, HrStageSettings, load_hr_stage_settings",
            False,
        ),
        (
            "fitdocs.audit",
            "from .hr_benchmarks.inspect import inconsistencies as inspect",
            False,
        ),
        ("fitdocs.hr_benchmarks.engine", "from .inspect import takeovers", False),
        (
            "fitdocs.sync",
            "from fitdocs.hr_benchmarks import derive_hr_benchmarks as run",
            True,
        ),
        (
            "fitdocs.sync",
            "from .hr_benchmarks.engine import derive_hr_benchmarks",
            True,
        ),
        (
            "fitdocs.audit",
            "from fitdocs.hr_benchmarks import derive_hr_benchmarks",
            True,
        ),
        ("fitdocs.cli", "from .hr_benchmarks.inspect import takeovers", True),
        (
            "fitdocs.load.channels.heart_rate",
            "import fitdocs.hr_benchmarks as hr",
            True,
        ),
        (
            "fitdocs.load.threshold.calculator",
            "from ...hr_benchmarks import derive_hr_benchmarks",
            True,
        ),
        ("fitdocs.load.qa.cadence", "from fitdocs import hr_benchmarks as hr", True),
        (
            "fitdocs.performance.engine",
            "from ..hr_benchmarks.inspect import takeovers",
            True,
        ),
        ("fitdocs.wellness.engine", "import fitdocs as f\nhr = f.hr_benchmarks", True),
        ("fitdocs.index.store", "import fitdocs.hr_benchmarks.engine", True),
        ("fitdocs.sync", "__import__('fitdocs.hr_benchmarks.engine')", True),
        ("fitdocs.sync", "loader = __import__\nloader('fitdocs.hr_benchmarks')", True),
        (
            "fitdocs.sync",
            "import importlib as il\nil.import_module('fitdocs.hr_benchmarks')",
            True,
        ),
        (
            "fitdocs.sync",
            "from importlib import import_module as load\nagain = load\n"
            "again('.hr_benchmarks', package='fitdocs')",
            True,
        ),
        (
            "fitdocs.sync",
            "import fitdocs as f\nparent = f\nhr = parent.hr_benchmarks\n"
            "run = hr.derive_hr_benchmarks",
            True,
        ),
        ("fitdocs.sync", "__import__('fitdocs', fromlist=['hr_benchmarks'])", True),
        ("fitdocs.sync", "__import__('fitdocs', {}, {}, ('hr_benchmarks',))", True),
        (
            "fitdocs.cli",
            "import importlib as il\nhr = "
            "il.import_module('.hr_benchmarks', 'fitdocs')\n"
            "run = hr.derive_hr_benchmarks",
            False,
        ),
        (
            "fitdocs.audit",
            "import fitdocs.hr_benchmarks.inspect as inspect\nscan = inspect.takeovers",
            False,
        ),
        (
            "fitdocs.load.__init__",
            "from ..hr_benchmarks import derive_hr_benchmarks",
            True,
        ),
        (
            "fitdocs.sync",
            "__import__('hr_benchmarks', globals(), "
            "fromlist=['derive_hr_benchmarks'], level=1)",
            True,
        ),
        ("fitdocs.sync", "from fitdocs.benchmarks import Benchmark", False),
    ],
    ids=[
        "cli-facade",
        "cli-engine-relative",
        "cli-settings-report",
        "audit-inspect",
        "internal",
        "sync-facade",
        "sync-engine",
        "audit-writer",
        "cli-inspect",
        "channels-package",
        "threshold-relative",
        "qa-parent-import",
        "performance-inspect",
        "wellness-qualified",
        "index-engine",
        "builtin-literal",
        "builtin-alias",
        "importlib-qualified",
        "importlib-alias-relative",
        "assigned-attribute",
        "builtin-fromlist-keyword",
        "builtin-fromlist-positional",
        "cli-dynamic-relative",
        "audit-qualified",
        "package-init-relative",
        "builtin-relative-level",
        "ordinary-leaf",
    ],
)
def test_external_import_controls(module: str, source: str, forbidden: bool) -> None:
    assert bool(_external_violations(source, module)) is forbidden


@pytest.mark.parametrize("forbidden", [False, True], ids=["legal", "violator"])
def test_external_tree_controls(tmp_path: Path, forbidden: bool) -> None:
    (tmp_path / "sync.py").write_text(
        "from fitdocs.hr_benchmarks import derive_hr_benchmarks"
        if forbidden
        else "from fitdocs.benchmarks import Benchmark"
    )
    assert (
        bool(
            [
                issue
                for path in _fitdocs_paths(tmp_path)
                for issue in _external_violations(
                    path.read_text(), "fitdocs." + path.stem
                )
            ]
        )
        is forbidden
    )


_CONSTANT_KEYS = {
    "resting_window_days",
    "resting_min_values",
    "resting_step_bpm",
    "resting_confirm_days",
    "max_plausible_low_bpm",
    "max_plausible_high_bpm",
    "max_rate_bpm_per_s",
    "max_gap_s",
    "max_peak_window_s",
    "max_window_days",
    "max_top_sessions",
    "max_step_bpm",
    "rounding_half_offset",
}
_FORBIDDEN_SETTINGS = _CONSTANT_KEYS | {
    "hr_derivation_enabled",
    "max_hr_floor",
    "hand_expiry_days",
}


def _settings_violations(source: str) -> list[str]:
    return sorted(
        {
            node.value.lower()
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.lower() in _FORBIDDEN_SETTINGS
        }
    )


def test_settings_walk_has_no_hr_constant_keys() -> None:
    root = _ROOT.parent
    paths = sorted(root.rglob("settings.py")) + [_ROOT / "engine.py"]
    assert {
        "settings.py",
        "load/settings.py",
        "wellness/settings.py",
        "hr_benchmarks/engine.py",
    } <= {path.relative_to(root).as_posix() for path in paths}
    assert [
        (str(path), issue)
        for path in paths
        for issue in _settings_violations(path.read_text())
    ] == []


@pytest.mark.parametrize("key", sorted(_FORBIDDEN_SETTINGS))
def test_settings_key_violator_controls(key: str) -> None:
    assert _settings_violations(f'value = document.get("{key}")') == [key]


@pytest.mark.parametrize(
    "source",
    [
        'value = document["wellness"]["precedence"]',
        'value = document.get("load", {}).get("flags")',
    ],
    ids=["wellness-precedence", "load-flags"],
)
def test_settings_key_positive_controls(source: str) -> None:
    assert _settings_violations(source) == []


def test_hr_settings_have_only_existing_settings_projections() -> None:
    from dataclasses import fields

    from fitdocs.hr_benchmarks.engine import HrStageSettings

    assert tuple(field.name for field in fields(HrStageSettings)) == (
        "load",
        "resting_order",
    )
