"""Import, clock and write boundaries for derived index computations."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _REPO_ROOT / "src" / "fitdocs"
_DERIVED_ROOT = _SOURCE_ROOT / "index" / "derived"
_METRICS_FILES = (
    _SOURCE_ROOT / "metrics" / "mean_max.py",
    _SOURCE_ROOT / "metrics" / "mean_max_sources.py",
)
_CLOCK_CALLS = frozenset({"today", "now", "utcnow", "monotonic"})
_WRITE_CALLS = frozenset({"write_text", "write_bytes", "replace", "mkdir", "unlink"})
_OS_WRITE_CALLS = frozenset(
    {"replace", "rename", "mkdir", "makedirs", "unlink", "remove", "rmdir"}
)
_NETWORK_STDLIB = frozenset({"http", "urllib", "ftplib", "smtplib", "socket", "ssl"})
_HISTORY_SUBMODULES = frozenset(
    path.stem
    for path in (_SOURCE_ROOT / "history").glob("*.py")
    if path.stem != "__init__"
)
_PLANS_SUBMODULES = frozenset(
    path.stem
    for path in (_SOURCE_ROOT / "plans").glob("*.py")
    if path.stem != "__init__"
)


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _import_violations(
    tree: ast.AST,
    *,
    source_kind: str,
    module_name: str = "fitdocs.index.derived.control",
) -> set[str]:
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if not _allowed_module(target, source_kind=source_kind):
                    violations.add(target)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_import_from(node, module_name)
            if module is None or not _allowed_from_base(
                module, source_kind=source_kind
            ):
                violations.add(module or "relative import")
                continue
            for alias in node.names:
                target = f"{module}.{alias.name}"
                if not _allowed_from_name(module, alias.name, source_kind=source_kind):
                    violations.add(target)
    return violations


def _resolve_import_from(node: ast.ImportFrom, module_name: str) -> str | None:
    if node.level == 0:
        return node.module
    package = (
        module_name.removesuffix(".__init__")
        if module_name.endswith(".__init__")
        else module_name.rpartition(".")[0]
    )
    parts = package.split(".")
    if node.level > len(parts):
        return None
    base = parts[: len(parts) - node.level + 1]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _module_name_for_path(path: Path, root: Path, *, package_prefix: str) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    is_initializer = parts[-1] == "__init__"
    if is_initializer:
        parts.pop()
    qualified_parts = ([package_prefix] if package_prefix else []) + parts
    module_name = ".".join(qualified_parts)
    return f"{module_name}.__init__" if is_initializer else module_name


def _stdlib_module(module: str, *, source_kind: str) -> bool:
    root = module.partition(".")[0]
    return root in sys.stdlib_module_names and root not in _NETWORK_STDLIB


def _allowed_module(module: str, *, source_kind: str) -> bool:
    if _stdlib_module(module, source_kind=source_kind):
        return True
    if source_kind == "mean_max":
        return module in {"fitdocs.model", "fitdocs.metrics.mean_max_sources"}
    if source_kind == "mean_max_sources":
        return module == "fitdocs.citation"
    allowed_exact = {
        "fitdocs",
        "fitdocs.benchmarks",
        "fitdocs.history",
        "fitdocs.index.producer",
        "fitdocs.index.schema",
        "fitdocs.layout",
        "fitdocs.load.profile",
        "fitdocs.metrics.mean_max",
        "fitdocs.plans",
        "fitdocs.settings",
    }
    if module in allowed_exact:
        return True
    return module.startswith("fitdocs.index.derived.")


def _allowed_from_base(module: str, *, source_kind: str) -> bool:
    if _stdlib_module(module, source_kind=source_kind):
        return True
    if source_kind == "mean_max":
        return module in {
            "fitdocs.model",
            "fitdocs.metrics",
            "fitdocs.metrics.mean_max_sources",
        }
    if source_kind == "mean_max_sources":
        return module == "fitdocs.citation"
    return module in {
        "fitdocs",
        "fitdocs.benchmarks",
        "fitdocs.history",
        "fitdocs.index",
        "fitdocs.index.derived",
        "fitdocs.index.producer",
        "fitdocs.index.schema",
        "fitdocs.layout",
        "fitdocs.load.profile",
        "fitdocs.metrics",
        "fitdocs.metrics.mean_max",
        "fitdocs.plans",
        "fitdocs.settings",
    } or module.startswith("fitdocs.index.derived.")


def _allowed_from_name(module: str, name: str, *, source_kind: str) -> bool:
    if _stdlib_module(module, source_kind=source_kind):
        return True
    if source_kind == "mean_max":
        return module in {"fitdocs.model", "fitdocs.metrics.mean_max_sources"} or (
            module == "fitdocs.metrics" and name == "mean_max_sources"
        )
    if source_kind == "mean_max_sources":
        return module == "fitdocs.citation"
    if module == "fitdocs.history" and name in _HISTORY_SUBMODULES:
        return False
    if module == "fitdocs.plans" and name in _PLANS_SUBMODULES:
        return False
    if module == "fitdocs":
        return name in {"Sport", "plans"}
    if module == "fitdocs.index":
        return name in {"producer", "schema"}
    if module == "fitdocs.history":
        return True
    if module == "fitdocs.metrics":
        return name == "mean_max_sources"
    if module.startswith("fitdocs.index.derived."):
        return True
    return module in {
        "fitdocs.benchmarks",
        "fitdocs.index.producer",
        "fitdocs.index.schema",
        "fitdocs.index.derived",
        "fitdocs.index.derived.mean_max",
        "fitdocs.index.derived.load_series",
        "fitdocs.index.derived.blocks",
        "fitdocs.index.derived.benchmarks",
        "fitdocs.index.derived.inputs",
        "fitdocs.layout",
        "fitdocs.load.profile",
        "fitdocs.metrics.mean_max",
        "fitdocs.plans",
        "fitdocs.settings",
    }


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".", 1)[0]] = (
                    alias.name if alias.asname else alias.name.split(".", 1)[0]
                )
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_import_from(node, "fitdocs.index.derived.control")
            if module is None:
                continue
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
    return aliases


def _forbidden_call_violations(tree: ast.AST) -> set[str]:
    violations: set[str] = set()
    aliases = _module_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        dotted = ast.unparse(func) if hasattr(ast, "unparse") else name
        resolved = aliases.get(func.id) if isinstance(func, ast.Name) else None
        clock_alias = isinstance(func, ast.Name) and resolved in {
            "time.time",
            "time.monotonic",
        }
        module_clock_alias = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and aliases.get(func.value.id) == "time"
            and func.attr in {"time", "monotonic"}
        )
        if (
            name in _CLOCK_CALLS
            or dotted == "time.time"
            or clock_alias
            or module_clock_alias
        ):
            violations.add(f"clock:{dotted}")
        resolved_write = isinstance(func, ast.Name) and resolved in {
            f"{module}.{operation}"
            for module in ("os", "posix")
            for operation in _OS_WRITE_CALLS
        }
        module_write_alias = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and aliases.get(func.value.id) in {"os", "posix"}
            and func.attr in _OS_WRITE_CALLS
        )
        if (
            name in _WRITE_CALLS
            or dotted in {"os.replace", "os.rename", "posix.rename"}
            or resolved_write
            or module_write_alias
        ):
            violations.add(f"write:{dotted}")
        module_open = resolved in {"builtins.open", "io.open"} or dotted in {
            "builtins.open",
            "io.open",
        }
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module_open = module_open or (
                func.attr == "open" and aliases.get(func.value.id) in {"builtins", "io"}
            )
        is_open = name == "open" or module_open
        if is_open:
            method_open = (
                isinstance(func, ast.Attribute)
                and func.attr == "open"
                and not module_open
            )
            mode_index = 0 if method_open else 1
            mode: object | None = None
            has_mode = len(node.args) > mode_index
            if has_mode:
                mode_node = node.args[mode_index]
                mode = mode_node.value if isinstance(mode_node, ast.Constant) else None
            for keyword in node.keywords:
                if keyword.arg == "mode":
                    has_mode = True
                    mode = (
                        keyword.value.value
                        if isinstance(keyword.value, ast.Constant)
                        else None
                    )
            if has_mode and (
                not isinstance(mode, str) or any(flag in mode for flag in "wax+")
            ):
                violations.add("write:open")
    return violations


def _source_files() -> list[Path]:
    return sorted(_DERIVED_ROOT.rglob("*.py")) + list(_METRICS_FILES)


def _scan_sources(files: list[Path]) -> tuple[dict[Path, ast.Module], dict[Path, str]]:
    trees = {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in files
    }
    sources = {path: path.read_text(encoding="utf-8") for path in files}
    return trees, sources


def _imports_derived(
    tree: ast.AST, module_name: str = "fitdocs.index.registry"
) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from(node, module_name)
            targets = [base or ""]
            if base:
                targets.extend(f"{base}.{alias.name}" for alias in node.names)
        else:
            continue
        if any(
            target == "fitdocs.index.derived"
            or target.startswith("fitdocs.index.derived.")
            for target in targets
        ):
            return True
    return False


def _allowed_derived_importer(module: str, tree: ast.AST) -> bool:
    return not _imports_derived(tree) or module == "fitdocs.index.registry"


def _derived_importers(
    source_root: Path = _SOURCE_ROOT, derived_root: Path = _DERIVED_ROOT
) -> set[str]:
    importers: set[str] = set()
    source_paths = sorted(source_root.rglob("*.py"))
    assert source_paths, "the reverse-import walk scanned no source files"
    expected_paths = set(source_root.rglob("*.py"))
    assert set(source_paths) == expected_paths, (
        "the reverse-import walk omitted source files"
    )
    scanned_paths: set[Path] = set()
    for path in source_paths:
        if path.is_relative_to(derived_root):
            continue
        scanned_paths.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_name = _module_name_for_path(path, source_root, package_prefix="fitdocs")
        if _imports_derived(tree, module_name):
            module = module_name.removesuffix(".__init__")
            importers.add(module)
    assert scanned_paths == expected_paths - set(derived_root.rglob("*.py")), (
        "the reverse-import walk skipped an outside source file"
    )
    return importers


def test_derived_modules_obey_import_clock_and_write_boundaries() -> None:
    files = _source_files()
    assert files, "the walk is looking at the wrong directory"
    derived_files = sorted(_DERIVED_ROOT.rglob("*.py"))
    assert derived_files, "the derived source set is empty"
    assert len(derived_files) == 6
    assert {path.name for path in derived_files} == {
        "__init__.py",
        "benchmarks.py",
        "blocks.py",
        "inputs.py",
        "load_series.py",
        "mean_max.py",
    }
    assert len(files) == len(derived_files) + 2
    assert set(files) == set(derived_files) | set(_METRICS_FILES)
    trees, _ = _scan_sources(files)
    assert set(trees) == set(files), "AST scan omitted a requested source"
    assert len(trees) == len(files), "AST scan did not visit every requested source"
    violations: list[str] = []
    checked_files: set[Path] = set()
    for path, tree in trees.items():
        checked_files.add(path)
        source_kind = (
            "mean_max"
            if path.name == "mean_max.py" and path.parent.name == "metrics"
            else "mean_max_sources"
            if path in _METRICS_FILES
            else "derived"
        )
        module_name = _module_name_for_path(
            path, _SOURCE_ROOT, package_prefix="fitdocs"
        )
        violations.extend(
            f"{path.name}: import {name}"
            for name in _import_violations(
                tree, source_kind=source_kind, module_name=module_name
            )
        )
        violations.extend(
            f"{path.name}: {name}" for name in _forbidden_call_violations(tree)
        )
    assert checked_files == set(trees), (
        "boundary checks did not visit every parsed tree"
    )
    assert not violations, "boundary violations: " + "; ".join(sorted(violations))
    importers = _derived_importers()
    assert importers <= {"fitdocs.index.registry"}


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import duckdb", "duckdb"),
        ("from datetime import date\ndate.today()", "clock:date.today"),
        ("from pathlib import Path\nPath('x').write_text('x')", "write_text"),
        ("from fitdocs.index import store", "fitdocs.index.store"),
        ("from fitdocs.index import derived", "fitdocs.index.derived"),
        ("from fitdocs import cli", "fitdocs.cli"),
        ("from fitdocs.metrics import power", "fitdocs.metrics.power"),
        ("import urllib.request", "urllib.request"),
        ("import fitdocs.history.engine", "fitdocs.history.engine"),
        ("import fitdocs.plans.engine", "fitdocs.plans.engine"),
        ("from fitdocs.history import engine", "fitdocs.history.engine"),
        (
            "from fitdocs.history.engine import compute_history",
            "fitdocs.history.engine",
        ),
        ("from fitdocs.plans import engine", "fitdocs.plans.engine"),
    ],
)
def test_boundary_scanner_rejects_synthetic_forbidden_constructs(
    source: str, expected: str
) -> None:
    tree = ast.parse(source)
    if expected.startswith("clock:") or expected == "write_text":
        violations = _forbidden_call_violations(tree)
    else:
        violations = _import_violations(tree, source_kind="derived")
    assert any(expected in violation for violation in violations)
    if expected == "fitdocs.index.derived":
        assert _imports_derived(tree)
        assert not _allowed_derived_importer("fitdocs.history.engine", tree)
        assert _allowed_derived_importer("fitdocs.index.registry", tree)


def test_mean_max_scanner_rejects_unapproved_metrics_module() -> None:
    tree = ast.parse("from fitdocs.metrics import power")
    assert "fitdocs.metrics.power" in _import_violations(tree, source_kind="mean_max")


@pytest.mark.parametrize(
    "source, source_kind",
    [
        ("from fitdocs.index import store", "mean_max"),
        ("from fitdocs.index import store", "mean_max_sources"),
        ("from fitdocs.metrics.mean_max import mean_max_curve", "mean_max_sources"),
        ("from fitdocs.history import compute_history", "mean_max"),
    ],
)
def test_metrics_modules_reject_imports_outside_their_exact_boundary(
    source: str, source_kind: str
) -> None:
    assert _import_violations(ast.parse(source), source_kind=source_kind)


def test_metrics_import_boundaries_exclude_the_index_at_both_gates() -> None:
    assert not _allowed_from_base("fitdocs.index", source_kind="mean_max")
    assert not _allowed_from_name("fitdocs.index", "store", source_kind="mean_max")
    assert not _allowed_from_base("fitdocs.index", source_kind="mean_max_sources")


@pytest.mark.parametrize(
    "source, source_kind",
    [
        ("from fitdocs.index import producer, schema", "derived"),
        ("from fitdocs.index.derived.inputs import digest", "derived"),
        ("from fitdocs import plans, Sport", "derived"),
        ("from fitdocs.history import compute_history", "derived"),
        ("from fitdocs.metrics.mean_max import mean_max_curve", "derived"),
        ("from fitdocs.metrics import mean_max_sources", "mean_max"),
        ("from fitdocs.model import Samples", "mean_max"),
        ("from fitdocs.citation import CitedConstant", "mean_max_sources"),
        ("import datetime", "derived"),
    ],
)
def test_scanner_accepts_designated_public_imports(
    source: str, source_kind: str
) -> None:
    assert not _import_violations(ast.parse(source), source_kind=source_kind)


@pytest.mark.parametrize(
    "source, module_name, source_kind, allowed",
    [
        ("from ..index import derived", "fitdocs.history.engine", "derived", False),
        (
            "from ..index import derived as d",
            "fitdocs.history.engine",
            "derived",
            False,
        ),
        ("from ..index import *", "fitdocs.history.engine", "derived", False),
        (
            "from .inputs import digest",
            "fitdocs.index.derived.mean_max",
            "derived",
            True,
        ),
        (
            "from fractions import Fraction",
            "fitdocs.metrics.mean_max",
            "mean_max",
            True,
        ),
        (
            "from fitdocs.metrics.mean_max_sources import DURATION_SOURCES",
            "fitdocs.metrics.mean_max",
            "mean_max",
            True,
        ),
        (
            "from ...fitdocs.model import Samples",
            "fitdocs.index.derived.inputs",
            "derived",
            False,
        ),
    ],
)
def test_relative_imports_resolve_against_scanned_package(
    source: str, module_name: str, source_kind: str, allowed: bool
) -> None:
    violations = _import_violations(
        ast.parse(source), source_kind=source_kind, module_name=module_name
    )
    assert not violations if allowed else violations


def test_relative_import_in_package_initializer_uses_its_package() -> None:
    node = ast.parse("from .engine import compute_history").body[0]
    assert isinstance(node, ast.ImportFrom)
    assert (
        _resolve_import_from(node, "fitdocs.history.__init__")
        == "fitdocs.history.engine"
    )


def test_scanned_initializer_path_resolves_its_own_relative_import() -> None:
    path = _DERIVED_ROOT / "__init__.py"
    module_name = _module_name_for_path(path, _SOURCE_ROOT, package_prefix="fitdocs")
    assert module_name == "fitdocs.index.derived.__init__"
    source = ast.parse("from .inputs import digest")
    assert not _import_violations(
        source, source_kind="derived", module_name=module_name
    )


@pytest.mark.parametrize(
    "source",
    [
        "from os import replace as rename\nrename('a', 'b')",
        "from os import rename as move\nmove('a', 'b')",
        "from os import unlink as remove_file\nremove_file('report.md')",
        "from os import mkdir as make_directory\nmake_directory('report-dir')",
        "from builtins import open as op\nop('a', 'w')",
        "from builtins import open as op\nop('a', mode='a')",
        "from builtins import open as op\nop('a', mode=selected_mode)",
        "from io import open as io_open\nio_open('report.md', 'w')",
        "import io as file_io\nfile_io.open('report.md', mode='a')",
        "import io as io_alias\nio_alias.open('report.md', 'w')",
        "from pathlib import Path\nPath('a').open('w')",
        "from pathlib import Path\nPath('a').open(mode='a')",
        "from pathlib import Path\nPath('a').open(mode=selected_mode)",
        "import os as operating\noperating.replace('a', 'b')",
        "import os as operating\noperating.unlink('report.md')",
        "import os as operating\noperating.mkdir('report-dir')",
    ],
)
def test_write_aliases_are_rejected(source: str) -> None:
    assert _forbidden_call_violations(ast.parse(source))


def test_path_open_read_mode_is_allowed() -> None:
    source = "from pathlib import Path\nPath('a').open('r')\nPath('b').open()"
    assert not _forbidden_call_violations(ast.parse(source))


def test_non_open_builtins_module_calls_are_allowed() -> None:
    tree = ast.parse("import builtins as b\nb.pow(2, 3)")
    assert not _forbidden_call_violations(tree)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("object.today()", "clock:object.today"),
        ("object.now()", "clock:object.now"),
        ("object.utcnow()", "clock:object.utcnow"),
        ("object.monotonic()", "clock:object.monotonic"),
        ("object.write_text('x')", "write:object.write_text"),
        ("object.write_bytes(b'x')", "write:object.write_bytes"),
        ("object.replace('x')", "write:object.replace"),
        ("object.mkdir()", "write:object.mkdir"),
        ("object.unlink()", "write:object.unlink"),
    ],
)
def test_each_named_clock_and_write_spelling_is_rejected(
    source: str, expected: str
) -> None:
    assert expected in _forbidden_call_violations(ast.parse(source))


@pytest.mark.parametrize(
    "source, expected",
    [
        ("from time import time as read_clock\nread_clock()", "clock:read_clock"),
        (
            "from time import monotonic as elapsed_clock\nelapsed_clock()",
            "clock:elapsed_clock",
        ),
        (
            "from os import replace as apply_change\napply_change('a', 'b')",
            "write:apply_change",
        ),
        ("from os import rename as move_path\nmove_path('a', 'b')", "write:move_path"),
        ("from os import mkdir as make_path\nmake_path('a')", "write:make_path"),
        ("from os import unlink as remove_path\nremove_path('a')", "write:remove_path"),
        (
            "from posix import replace as apply_change\napply_change('a', 'b')",
            "write:apply_change",
        ),
        (
            "from posix import rename as move_path\nmove_path('a', 'b')",
            "write:move_path",
        ),
        ("from posix import mkdir as make_path\nmake_path('a')", "write:make_path"),
        (
            "from posix import unlink as remove_path\nremove_path('a')",
            "write:remove_path",
        ),
        (
            "import os as filesystem\nfilesystem.rename('a', 'b')",
            "write:filesystem.rename",
        ),
        (
            "import posix as filesystem\nfilesystem.rename('a', 'b')",
            "write:filesystem.rename",
        ),
        ("import builtins as runtime\nruntime.open('r', 'w')", "write:open"),
        ("import io as streams\nstreams.open('r', 'w')", "write:open"),
        ("from builtins import open as file_open\nfile_open('r', 'w')", "write:open"),
        ("from io import open as file_open\nfile_open('r', 'w')", "write:open"),
    ],
)
def test_distinct_clock_write_and_open_aliases_are_rejected(
    source: str, expected: str
) -> None:
    assert expected in _forbidden_call_violations(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    ["from fitdocs.plans import engine", "from fitdocs.history import engine"],
)
def test_history_and_plans_package_submodules_are_rejected(source: str) -> None:
    assert _import_violations(ast.parse(source), source_kind="derived")
    public_object = (
        "from fitdocs.plans import FuturePublicObject\n"
        "from fitdocs.history import FuturePublicObject"
    )
    assert not _import_violations(ast.parse(public_object), source_kind="derived")


@pytest.mark.parametrize(
    "package, submodules",
    [("history", _HISTORY_SUBMODULES), ("plans", _PLANS_SUBMODULES)],
)
def test_history_and_plans_submodule_bases_are_rejected(
    package: str, submodules: frozenset[str]
) -> None:
    assert submodules
    assert all(
        not _allowed_from_base(f"fitdocs.{package}.{name}", source_kind="derived")
        for name in submodules
    )


def test_mean_max_allowed_imports_cover_library_forms() -> None:
    assert not _import_violations(ast.parse("import fractions"), source_kind="mean_max")
    assert not _import_violations(
        ast.parse("from fitdocs.metrics.mean_max_sources import DURATION_SOURCES"),
        source_kind="mean_max",
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("open('x', 'w')", "write:open"),
        ("open('x', mode='a')", "write:open"),
        ("Path('x').open('w')", "write:open"),
        ("Path('x').open(mode='a')", "write:open"),
        ("Path('x').open(mode=mode)", "write:open"),
        ("open('x', mode=mode)", "write:open"),
        ("import os\nos.replace('a', 'b')", "write:os.replace"),
        ("import time\ntime.time()", "clock:time.time"),
        ("from datetime import date\ndate.today()", "clock:date.today"),
        ("from datetime import date as day\nday.today()", "clock:day.today"),
        ("from fitdocs.index import store", "fitdocs.index"),
        ("from fitdocs.index import store as indexed_store", "fitdocs.index"),
        ("import fitdocs.index.store as store", "fitdocs.index.store"),
        ("from fitdocs.index import derived", "fitdocs.index.derived"),
        ("from fitdocs import cli", "fitdocs.cli"),
        ("from fitdocs.metrics import power", "fitdocs.metrics.power"),
        ("import urllib.request", "urllib.request"),
        ("from fitdocs.history import engine", "fitdocs.history.engine"),
        ("from fitdocs.plans.engine import resolve_plan", "fitdocs.plans.engine"),
        ("import time as clock\nclock.time()", "clock:clock.time"),
        ("from os import replace as rename\nrename('a', 'b')", "write:rename"),
        ("from builtins import open as op\nop('a', 'w')", "write:open"),
    ],
)
def test_scanner_reports_write_modes_clock_aliases_and_import_forms(
    source: str, expected: str
) -> None:
    tree = ast.parse(source)
    found = _forbidden_call_violations(tree) | _import_violations(
        tree, source_kind="derived"
    )
    if expected == "fitdocs.index.derived":
        found |= _imports(tree)
    assert any(expected in item for item in found)


@pytest.mark.parametrize(
    "source",
    [
        "from ..index import derived",
        "from ..index import derived as d",
        "from ..index.derived import *",
    ],
)
def test_reverse_walk_resolves_relative_derived_imports(source: str) -> None:
    tree = ast.parse(source)
    assert _imports_derived(tree, "fitdocs.history.engine")
    assert not _allowed_derived_importer("fitdocs.history.engine", tree)


@pytest.mark.parametrize(
    "relative_path, source, expected",
    [
        (
            Path("history/engine.py"),
            "import fitdocs.index.derived",
            "fitdocs.history.engine",
        ),
        (
            Path("history/engine.py"),
            "from ..index import derived",
            "fitdocs.history.engine",
        ),
        (
            Path("history/__init__.py"),
            "from ..index import derived",
            "fitdocs.history",
        ),
    ],
)
def test_reverse_walk_rejects_imports_from_temporary_source_tree(
    tmp_path: Path, relative_path: Path, source: str, expected: str
) -> None:
    source_root = tmp_path / "src" / "fitdocs"
    derived_root = source_root / "index" / "derived"
    derived_root.mkdir(parents=True)
    (derived_root / "__init__.py").write_text("", encoding="utf-8")
    outside_path = source_root / relative_path
    outside_path.parent.mkdir(parents=True, exist_ok=True)
    outside_path.write_text(source, encoding="utf-8")

    importers = _derived_importers(source_root, derived_root)

    assert expected in importers
