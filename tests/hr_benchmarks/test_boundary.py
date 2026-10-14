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
