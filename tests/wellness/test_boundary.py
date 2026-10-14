"""Static import, clock and network boundaries for the wellness package."""

from __future__ import annotations

import ast
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2] / "src" / "fitdocs" / "wellness"
_RANKS = {
    "model": 10,
    "probe": 10,
    "spec": 20,
    "formats.__init__": 30,
    "formats.intervals": 30,
    "formats.garmin": 30,
    "registry": 40,
    "settings": 50,
    "merge": 50,
    "archive": 50,
    "series": 60,
    "intake": 70,
    "engine": 70,
    "inspect": 80,
    "__init__": 90,
}
_NETWORK = {"http", "urllib", "socket", "ssl", "ftplib", "smtplib"}
_EXTERNAL = {"fitdocs.layout", "fitdocs.settings", "fitdocs.units", "tomli_w"}


def _wellness_module(name: str) -> str:
    relative = name.removeprefix("fitdocs.wellness.")
    if relative == "fitdocs.wellness":
        return "__init__"
    if relative not in _RANKS and relative + ".__init__" in _RANKS:
        return relative + ".__init__"
    return relative


def _from_base(node: ast.ImportFrom, module: str) -> str:
    package = "fitdocs.wellness"
    if "." in module:
        package += "." + module.rsplit(".", 1)[0]
    if not node.level:
        return node.module or ""
    try:
        return resolve_name("." * node.level + (node.module or ""), package)
    except ImportError:
        return "invalid-relative-import"


def _allowed(name: str, module: str) -> str | None:
    if name == "fitdocs.wellness" or name.startswith("fitdocs.wellness."):
        target = _wellness_module(name)
        if target not in _RANKS:
            return "unranked:" + target
        if _RANKS[target] >= _RANKS[module]:
            return "rank:" + target
        return None
    root = name.split(".")[0]
    if name in _EXTERNAL or (root in sys.stdlib_module_names and root not in _NETWORK):
        return None
    return "import:" + name


class _Guard(ast.NodeVisitor):
    def __init__(self, module: str, aliases: dict[str, str] | None = None) -> None:
        self.module = module
        self.aliases = dict(aliases or {})
        self.violations: set[str] = set()

    def _prime_imports(self, statements: list[ast.stmt]) -> None:
        pending: list[ast.AST] = list(statements)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.visit(node)
            pending.extend(ast.iter_child_nodes(node))

    def visit_Module(self, node: ast.Module) -> None:
        self._prime_imports(node.body)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            violation = _allowed(alias.name, self.module)
            if violation:
                self.violations.add(violation)
            self.aliases[alias.asname or alias.name.split(".")[0]] = (
                alias.name if alias.asname else alias.name.split(".")[0]
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = _from_base(node, self.module)
        for alias in node.names:
            name = base
            if base in {"fitdocs", "fitdocs.wellness", "fitdocs.wellness.formats"}:
                name = base + "." + alias.name
            violation = _allowed(name, self.module)
            if violation:
                self.violations.add(violation)
            self.aliases[alias.asname or alias.name] = base + "." + alias.name

    def _name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return self._name(node.value) + "." + node.attr
        return ""

    def visit_Call(self, node: ast.Call) -> None:
        name = self._name(node.func)
        if name.startswith("time.") or name in {
            "datetime.date.today",
            "datetime.datetime.now",
            "datetime.datetime.utcnow",
            "date.today",
            "datetime.now",
            "datetime.utcnow",
        }:
            self.violations.add("clock")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "astimezone"
            and not node.args
            and not node.keywords
        ):
            self.violations.add("timezone")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns:
            self.visit(node.returns)
        child = _Guard(self.module, self.aliases)
        child._prime_imports(node.body)
        for statement in node.body:
            child.visit(statement)
        self.violations.update(child.violations)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for expression in [*node.bases, *node.decorator_list]:
            self.visit(expression)
        for keyword in node.keywords:
            self.visit(keyword.value)
        child = _Guard(self.module, self.aliases)
        child._prime_imports(node.body)
        for statement in node.body:
            child.visit(statement)
        self.violations.update(child.violations)


def _violations(source: str, module: str) -> set[str]:
    if module not in _RANKS:
        return {"unranked:" + module}
    guard = _Guard(module)
    guard.visit(ast.parse(source))
    return guard.violations


def _scan(root: Path) -> tuple[set[str], set[str]]:
    visited: set[str] = set()
    violations: set[str] = set()
    for path in root.rglob("*.py"):
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        visited.add(module)
        violations.update(_violations(path.read_text(encoding="utf-8"), module))
    return visited, violations


def test_wellness_boundary() -> None:
    visited, violations = _scan(_ROOT)
    expected = {
        ".".join(path.relative_to(_ROOT).with_suffix("").parts)
        for path in _ROOT.glob("**/*.py")
    }
    assert visited == {
        "model",
        "probe",
        "spec",
        "formats.__init__",
        "formats.intervals",
        "formats.garmin",
        "registry",
        "settings",
        "merge",
        "archive",
        "series",
        "intake",
        "engine",
        "inspect",
        "__init__",
    }, "wellness modules differ from the published rank table"
    assert visited, "wellness walk found no modules"
    assert visited == expected, "wellness walk skipped modules"
    assert not violations, sorted(violations)


@pytest.mark.parametrize(
    "source, module, expected",
    [
        ("import fitdocs.sync", "spec", "import:fitdocs.sync"),
        ("from fitdocs import sync as s", "spec", "import:fitdocs.sync"),
        ("from .. import sync", "spec", "import:fitdocs.sync"),
        ("import duckdb", "spec", "import:duckdb"),
        ("import urllib.request", "spec", "import:urllib.request"),
        ("from urllib import request", "spec", "import:urllib"),
        ("import socket as s", "spec", "import:socket"),
        ("import http.client", "spec", "import:http.client"),
        ("import ssl", "spec", "import:ssl"),
        ("import ftplib", "spec", "import:ftplib"),
        ("import smtplib", "spec", "import:smtplib"),
        ("from datetime import datetime\ndatetime.now()", "spec", "clock"),
        ("import datetime as dt\ndt.datetime.utcnow()", "spec", "clock"),
        ("from datetime import date as d\nd.today()", "spec", "clock"),
        ("from time import monotonic as tick\ntick()", "spec", "clock"),
        ("import time as t\nt.sleep(1)", "spec", "clock"),
        ("def f():\n return dt.datetime.now()\nimport datetime as dt", "spec", "clock"),
        ("async def f():\n import time as t\n t.time()", "spec", "clock"),
        ("class C:\n import time as t\n t.time()", "spec", "clock"),
        ("date.today()", "spec", "clock"),
        ("datetime.now()", "spec", "clock"),
        ("datetime.utcnow()", "spec", "clock"),
        ("value.astimezone()", "spec", "timezone"),
        ("from fitdocs.wellness.engine import rebuild_series", "spec", "rank:engine"),
        ("from . import engine as e", "spec", "rank:engine"),
        ("from .. import registry", "formats.intervals", "rank:registry"),
        ("from .probe import CandidateProbe", "model", "rank:probe"),
        (
            "from . import intervals",
            "formats.__init__",
            "rank:formats.intervals",
        ),
        ("from . import missing", "spec", "unranked:missing"),
        ("def f():\n from datetime import datetime as dt\n dt.now()", "spec", "clock"),
        ("def f():\n from . import engine\n return engine", "spec", "rank:engine"),
        (
            "from time import monotonic as tick\n"
            "def f():\n import math as tick\n return tick.sqrt(4)\ntick()",
            "spec",
            "clock",
        ),
    ],
)
def test_rejects_forbidden_constructs(source: str, module: str, expected: str) -> None:
    assert expected in _violations(source, module)


@pytest.mark.parametrize(
    "source, module",
    [
        ("import json\nfrom pathlib import Path\nimport tomli_w", "model"),
        ("from fitdocs import layout, settings, units", "model"),
        ("from fitdocs.units import unit_named", "model"),
        ("from .model import Metric\nfrom . import probe", "spec"),
        ("from ..spec import FormatSpec", "formats.intervals"),
        ("from .model import Metric", "__init__"),
        ("from . import model", "__init__"),
        ("from .formats import intervals", "registry"),
        ("import datetime as dt\ndt.datetime(2024, 1, 1)", "model"),
        ("value.astimezone(offset)\nvalue.astimezone(tz=offset)", "model"),
        (
            "from time import monotonic as tick\n"
            "def f():\n import math as tick\n return tick.sqrt(4)",
            "spec",
        ),
        ("def f():\n from .model import Metric\n return Metric", "spec"),
    ],
)
def test_accepts_allowed_constructs(source: str, module: str) -> None:
    assert not _violations(source, module)


def test_unranked_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "unexpected.py").write_text('"""Synthetic module."""', encoding="utf-8")
    _, violations = _scan(tmp_path)
    assert "unranked:unexpected" in violations


def test_empty_walk_control(tmp_path: Path) -> None:
    visited, _ = _scan(tmp_path)
    assert not visited
