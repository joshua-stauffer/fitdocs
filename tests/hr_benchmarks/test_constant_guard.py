"""Exact-site exemptions for numeric literals outside bound constant records."""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest

from tests.hr_benchmarks.test_boundary import _ROOT, _module_key, _module_paths

_ARITHMETIC_MODULES = {"peaks", "maximum", "resting", "timeline", "inspect"}


class ExemptionCategory(StrEnum):
    ARITHMETIC_IDENTITY = "arithmetic_identity"
    INDEX = "index"
    UNIT_CONVERSION = "unit_conversion"


@dataclass(frozen=True)
class LiteralExemption:
    module: str
    line: int
    column: int
    value: int | float
    category: ExemptionCategory
    reason: str


_EXEMPTIONS: tuple[LiteralExemption, ...] = ()


def _literal_violations(
    source: str, module: str, exemptions: tuple[LiteralExemption, ...] = ()
) -> list[str]:
    tree = ast.parse(source)
    aliases = {"float": "float", "int": "int"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "builtins":
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            for target in node.targets:
                if isinstance(target, ast.Name) and node.value.id in aliases:
                    aliases[target.id] = aliases[node.value.id]
    found: set[tuple[int, int, int | float | str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            found.add((node.lineno, node.col_offset, cast(int | float, node.value)))
        elif (
            isinstance(node, ast.Call)
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            func = node.func
            converter = (
                aliases.get(func.id, "")
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "builtins"
                else ""
            )
            if converter in {"int", "float"}:
                found.add((node.lineno, node.col_offset, node.args[0].value))
    allowed = {
        (e.line, e.column, e.value)
        for e in exemptions
        if e.module == module and e.reason.strip()
    }
    violations = [
        f"{module}:{line}:{column}: bare literal {value!r}"
        for line, column, value in found - allowed
    ]
    for exemption in exemptions:
        if exemption.module == module:
            site = (exemption.line, exemption.column, exemption.value)
            if site not in found:
                violations.append(f"unused exemption: {exemption}")
    return violations


def _arithmetic_violations(paths: list[Path], root: Path = _ROOT) -> list[str]:
    violations: list[str] = []
    for path in paths:
        key = _module_key(path, root)
        if key in _ARITHMETIC_MODULES:
            violations.extend(_literal_violations(path.read_text(), key, _EXEMPTIONS))
    return violations


def test_arithmetic_literals_on_disk() -> None:
    paths = _module_paths()
    assert paths, "empty constant-guard walk"
    assert _arithmetic_violations(paths) == []


@pytest.mark.parametrize(
    "module", ("peaks", "maximum", "resting", "timeline", "inspect")
)
@pytest.mark.parametrize(
    "source,rejected",
    [
        ("window = 365", True),
        ("window = sources.MAX_WINDOW_DAYS.value", False),
    ],
    ids=("bare-literal", "bound-record"),
)
def test_arithmetic_walk_with_future_module(
    tmp_path: Path, module: str, source: str, rejected: bool
) -> None:
    (tmp_path / f"{module}.py").write_text(source)
    (tmp_path / "sources.py").write_text("MAX_WINDOW_DAYS = 365")
    assert bool(_arithmetic_violations(_module_paths(tmp_path), tmp_path)) is rejected


@pytest.mark.parametrize(
    "source",
    [
        "window = 365",
        "window = -365",
        "offset = 0.5",
        "n = 3",
        "window = float('365')",
        "window = int('365')",
        "from builtins import float as F\nwindow = F('365')",
        "converter = float\nwindow = converter('365')",
        "def f():\n    return 365",
        "total = 0",
        "last = values[1]",
    ],
)
def test_bare_literals(source: str) -> None:
    assert _literal_violations(source, "maximum")


@pytest.mark.parametrize(
    "source",
    [
        "window = sources.MAX_WINDOW_DAYS.value",
        "flag = True",
        "missing = None",
        "label = '365'",
        "values: int | float",
        "from .sources import MAX_WINDOW_DAYS as W\nwindow = W.value",
    ],
)
def test_non_literals(source: str) -> None:
    assert _literal_violations(source, "maximum") == []


@pytest.mark.parametrize(
    "source,category,reason",
    [
        ("total = 0", ExemptionCategory.ARITHMETIC_IDENTITY, "additive identity"),
        ("last = values[1]", ExemptionCategory.INDEX, "second tuple member"),
        (
            "km = metres / 1000",
            ExemptionCategory.UNIT_CONVERSION,
            "metres to kilometres",
        ),
    ],
)
def test_exact_exemption(source: str, category: ExemptionCategory, reason: str) -> None:
    literal = next(
        n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Constant)
    )
    exemption = LiteralExemption(
        "maximum",
        literal.lineno,
        literal.col_offset,
        cast(int, literal.value),
        category,
        reason,
    )
    assert _literal_violations(source, "maximum", (exemption,)) == []


@pytest.mark.parametrize("change", ["module", "line", "column", "value", "reason"])
def test_wrong_exemption(change: str) -> None:
    exemption = LiteralExemption(
        "maximum", 1, 8, 0, ExemptionCategory.ARITHMETIC_IDENTITY, "additive identity"
    )
    changes = {
        "module": replace(exemption, module="resting"),
        "line": replace(exemption, line=2),
        "column": replace(exemption, column=9),
        "value": replace(exemption, value=365),
        "reason": replace(exemption, reason=""),
    }
    exemption = changes[change]
    assert _literal_violations("total = 0", "maximum", (exemption,))


@pytest.mark.parametrize(
    "source",
    [
        "total = 0\nwindow = 365",
        "total = 0\nother = 0",
        "pair = (0, 0)",
    ],
)
def test_exemption_does_not_cover_another_site(source: str) -> None:
    exemption = LiteralExemption(
        "maximum", 1, 8, 0, ExemptionCategory.ARITHMETIC_IDENTITY, "additive identity"
    )
    assert _literal_violations(source, "maximum", (exemption,))


def test_unused_exemption() -> None:
    exemption = LiteralExemption(
        "maximum", 1, 8, 0, ExemptionCategory.ARITHMETIC_IDENTITY, "additive identity"
    )
    assert _literal_violations(
        "total = sources.MAX_WINDOW_DAYS.value", "maximum", (exemption,)
    )
