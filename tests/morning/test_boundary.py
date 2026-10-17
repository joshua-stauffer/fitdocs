"""Import, clock and network boundaries of the morning-of package."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.query.test_boundary import _import_targets

_PACKAGE = "fitdocs.morning"
_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "fitdocs"
_MORNING_ROOT = _SOURCE_ROOT / "morning"

_ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    _PACKAGE: frozenset(),
    f"{_PACKAGE}.block": frozenset(
        {
            "fitdocs.wellness",
            "fitdocs.recovery",
            "fitdocs.render.format",
            "fitdocs.render.attribution",
            "fitdocs.render.charts.kit",
            "fitdocs.render.charts.kit.format",
        }
    ),
    f"{_PACKAGE}.docedit": frozenset({"fitdocs.contract", "fitdocs.docmerge"}),
    f"{_PACKAGE}.engine": frozenset(
        {
            "fitdocs.contract",
            "fitdocs.docio",
            "fitdocs.docmerge",
            "fitdocs.layout",
            "fitdocs.wellness",
            "fitdocs.morning.block",
            "fitdocs.morning.docedit",
        }
    ),
}
_FORBIDDEN = (
    "duckdb",
    "fitdocs.sync",
    "fitdocs.cli",
    "fitdocs.index",
    "fitdocs.query",
    "fitdocs.load",
    "fitdocs.history",
    "fitdocs.ingest",
    "fitdocs.connectors",
    "fitdocs.tiles",
)
_NETWORK_ROOTS = frozenset(
    {
        "urllib",
        "socket",
        "http",
        "ssl",
        "ftplib",
        "smtplib",
        "requests",
        "httpx",
        "aiohttp",
    }
)
_CLOCK_ATTRIBUTES = frozenset({"today", "now", "utcnow", "astimezone"})


def _sources(root: Path, package: str) -> dict[str, str]:
    scanned: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).with_suffix("").parts
        module = ".".join((package, *parts))
        scanned[module] = path.read_text(encoding="utf-8")
    assert scanned, f"no Python files under {root}"
    return scanned


def _under(target: str, root: str) -> bool:
    return target == root or target.startswith(root + ".")


def _is_fitdocs_module(target: str) -> bool:
    if target in _ALLOWED_IMPORTS:
        return True
    if not target.startswith("fitdocs.") or target != target.lower():
        return False
    path = _SOURCE_ROOT.joinpath(*target.split(".")[1:])
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _modules(source: str, module: str) -> set[str]:
    modules: set[str] = set()
    statements = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    for node in statements:
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        else:
            package = (
                module.removesuffix(".__init__")
                if module.endswith(".__init__")
                else module.rpartition(".")[0]
            )
            base = (
                importlib.util.resolve_name(
                    "." * node.level + (node.module or ""), package
                )
                if node.level
                else node.module or ""
            )
            for alias in node.names:
                candidate = f"{base}.{alias.name}"
                modules.add(candidate if _is_fitdocs_module(candidate) else base)
    static = "\n".join(ast.unparse(node) for node in statements)
    dynamic = _import_targets(source, module) - _import_targets(static, module)
    modules.update(dynamic)
    return modules


def _guard_imports(root: Path) -> None:
    for module, source in _sources(root, _PACKAGE).items():
        key = module.removesuffix(".__init__")
        assert key in _ALLOWED_IMPORTS, f"imports: unlisted module {module}"
        external = {
            target
            for target in _modules(source, module)
            if target.split(".")[0] not in sys.stdlib_module_names
        }
        # Task 3.2 closes this staged upper bound to exact equality.
        assert external <= _ALLOWED_IMPORTS[key], f"imports: {module}: {external}"


def _guard_forbidden(root: Path) -> None:
    for module, source in _sources(root, _PACKAGE).items():
        for target in _modules(source, module):
            forbidden = any(_under(target, prefix) for prefix in _FORBIDDEN)
            internal_facade = target.startswith(
                ("fitdocs.wellness.", "fitdocs.recovery.")
            )
            assert not (forbidden or internal_facade), f"forbidden: {module}: {target}"


def _guard_clock(root: Path) -> None:
    for module, source in _sources(root, _PACKAGE).items():
        imports = _import_targets(source, module)
        assert not any(_under(target, "time") for target in imports), f"clock: {module}"
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in _CLOCK_ATTRIBUTES, (
                    f"clock: {module}: {node.attr}"
                )


def _guard_network(root: Path) -> None:
    for module, source in _sources(root, _PACKAGE).items():
        for target in _import_targets(source, module):
            assert target.split(".")[0] not in _NETWORK_ROOTS, (
                f"network: {module}: {target}"
            )


def _guard_reverse(root: Path) -> None:
    for module, source in _sources(root, "fitdocs").items():
        for target in _import_targets(source, module):
            if _under(target, "fitdocs.morning.engine"):
                assert module == "fitdocs.cli", f"reverse: {module}: {target}"
            if _under(module, "fitdocs.render"):
                assert not _under(target, _PACKAGE), f"reverse: {module}: {target}"


_GUARDS: dict[str, Callable[[Path], None]] = {
    "imports": _guard_imports,
    "forbidden": _guard_forbidden,
    "clock": _guard_clock,
    "network": _guard_network,
}


def test_package_marker_is_docstring_only() -> None:
    tree = ast.parse((_MORNING_ROOT / "__init__.py").read_text(encoding="utf-8"))
    assert len(tree.body) == 1 and ast.get_docstring(tree) is not None


def test_importing_package_loads_only_package_and_root() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; import fitdocs.morning; "
            "print(json.dumps(sorted(n for n in sys.modules "
            "if n == 'fitdocs' or n.startswith('fitdocs.'))))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert json.loads(result.stdout) == ["fitdocs", "fitdocs.morning"]


def test_allowed_imports() -> None:
    _guard_imports(_MORNING_ROOT)


def test_allowed_imports_accepts_sanctioned_dependencies(tmp_path: Path) -> None:
    sources = {
        "__init__": '"""Synthetic morning package."""\n',
        "block": (
            "from fitdocs.wellness import Metric, SeriesValue\n"
            "from fitdocs.recovery import Baselines\n"
            "from fitdocs.render.format import ABSENT\n"
            "from fitdocs.render.attribution import WellnessAttribution\n"
            "from fitdocs.render.charts.kit import Column, ValueKind\n"
            "from fitdocs.render.charts.kit.format import format_value\n"
        ),
        "docedit": "from fitdocs import contract, docmerge\n",
        "engine": (
            "from fitdocs import contract, docio, docmerge, layout\n"
            "from fitdocs.wellness import read_series\n"
            "from . import block, docedit\n"
        ),
    }
    for name, source in sources.items():
        (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    _guard_imports(tmp_path)
    _guard_forbidden(tmp_path)


def test_staged_allowed_imports_accepts_partial_block(tmp_path: Path) -> None:
    (tmp_path / "block.py").write_text(
        "from fitdocs.wellness import Metric\n", encoding="utf-8"
    )
    _guard_imports(tmp_path)


def test_staged_allowed_imports_rejects_extra_dependency(tmp_path: Path) -> None:
    (tmp_path / "block.py").write_text(
        "from fitdocs.wellness import Metric\nfrom fitdocs import sync\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="imports"):
        _guard_imports(tmp_path)


def test_forbidden_names() -> None:
    _guard_forbidden(_MORNING_ROOT)


def test_clock() -> None:
    _guard_clock(_MORNING_ROOT)


def test_network() -> None:
    _guard_network(_MORNING_ROOT)


def test_reverse_imports() -> None:
    _guard_reverse(_SOURCE_ROOT)


@pytest.mark.parametrize(
    ("guard", "source"),
    [
        ("imports", "from fitdocs import sync\n"),
        ("imports", "from fitdocs.wellness.model import SeriesValue\n"),
        ("imports", "from fitdocs.morning import engine\n"),
        ("forbidden", "import duckdb\n"),
        ("forbidden", "from fitdocs import sync\n"),
        ("forbidden", "from fitdocs import cli\n"),
        ("forbidden", "from fitdocs import index\n"),
        ("forbidden", "from fitdocs import query\n"),
        ("forbidden", "from fitdocs import load\n"),
        ("forbidden", "from fitdocs import history\n"),
        ("forbidden", "from fitdocs import ingest\n"),
        ("forbidden", "from fitdocs import connectors\n"),
        ("forbidden", "from fitdocs import tiles\n"),
        ("forbidden", "from fitdocs.wellness.model import SeriesValue\n"),
        ("forbidden", "from fitdocs.recovery.baselines import Baselines\n"),
        ("forbidden", "__import__('fitdocs.sync')\n"),
        ("clock", "from datetime import date\ndate.today()\n"),
        ("clock", "from datetime import datetime as D\nD.now()\n"),
        ("clock", "from datetime import datetime\ndatetime.utcnow()\n"),
        ("clock", "from time import monotonic as tick\ntick()\n"),
        ("clock", "value.astimezone()\n"),
        ("network", "import urllib.request\n"),
        ("network", "from socket import socket as connect\n"),
        ("network", "import http.client\n"),
        ("network", "import ssl\n"),
        ("network", "import ftplib\n"),
        ("network", "import smtplib\n"),
        ("network", "import requests\n"),
        ("network", "import httpx\n"),
        ("network", "import aiohttp\n"),
        ("network", "__import__('urllib.request')\n"),
    ],
)
def test_scans_reject_synthetic_modules(
    tmp_path: Path, guard: str, source: str
) -> None:
    (tmp_path / "block.py").write_text(source, encoding="utf-8")
    with pytest.raises(AssertionError, match=guard):
        _GUARDS[guard](tmp_path)


@pytest.mark.parametrize("guard", ["imports", "forbidden", "clock", "network"])
def test_each_package_scan_rejects_an_empty_walk(tmp_path: Path, guard: str) -> None:
    with pytest.raises(AssertionError, match="no Python files"):
        _GUARDS[guard](tmp_path)


def test_reverse_scan_accepts_the_cli(tmp_path: Path) -> None:
    (tmp_path / "cli.py").write_text(
        "from fitdocs.morning import engine\n", encoding="utf-8"
    )
    _guard_reverse(tmp_path)


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("outsider.py", "from fitdocs.morning import engine\n"),
        ("render/outsider.py", "import fitdocs.morning.block\n"),
    ],
)
def test_reverse_scan_rejects_synthetic_importers(
    tmp_path: Path, module: str, source: str
) -> None:
    path = tmp_path / module
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    with pytest.raises(AssertionError, match="reverse"):
        _guard_reverse(tmp_path)


def test_reverse_scan_rejects_an_empty_walk(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="no Python files"):
        _guard_reverse(tmp_path)
