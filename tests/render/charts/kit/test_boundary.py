"""The `fitdocs.render.charts.kit` package boundary (chart-kit 6.5; Req 16.3,
16.4, 18.5; design.md § Architecture, "Dependency direction").

Every `*.py` file under `src/fitdocs/render/charts/kit/` is parsed. Four rules
run over it:

1. **Module tuple** (`TestModuleTuple`): the hand-kept `_MODULES` tuple equals
   the `rglob` of the package both ways, and the rank table names exactly the
   same modules.
2. **Import allow-list and forbidden roots** (`TestImports`): every import
   target is standard library or one of the allow-listed names; the index,
   query, dashboards, model and ingest roots are refused by dotted descent
   independently of the allow-list, as are the stdlib roots that read a clock,
   randomness, the environment, files, processes or the network (`random`,
   `uuid`, `secrets`, `locale`, `time`, `socket`, `ssl`, `http`, `urllib`,
   `ftplib`, `smtplib`, `xmlrpc`, `subprocess`, `os`, `pathlib`, `io`,
   `shutil`, `tempfile`, `glob`).
3. **Layer direction** (`TestLayerDirection`): every import of a kit module
   points at a strictly lower rank, so a kind never imports a kind, `registry`
   or `api`, and `frame` never imports `marks`.
4. **Purity spellings** (`TestPurity`): no clock spelling or name, no
   `os.environ`, `getenv` or `open(`, no dynamic import.

The scan functions also run on synthetic sources (`TestPositiveControls`):
one control per forbidden root, one per import-form, one per clock spelling
(as code and as a docstring example), and the dotted-descent boundary.

Full pins, re-pinned by an appending spec: `_MODULES` and `_RANK`. A new kind
module joins the kind rank; a new shared module gets a rank.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Final

import fitdocs.render.charts.kit

_KIT: Final[str] = "fitdocs.render.charts.kit"

#: Every kit module, relative to the package ("" is the package marker). Hand
#: kept; checked against the directory both ways.
_MODULES: Final[tuple[str, ...]] = (
    "",
    "api",
    "cartesian",
    "cells",
    "data",
    "format",
    "frame",
    "layout",
    "marks",
    "problems",
    "registry",
    "scales",
    "schema",
    "theme",
    "ticks",
    "validate",
    "kinds",
    "kinds.area",
    "kinds.band",
    "kinds.bar",
    "kinds.box",
    "kinds.calendar_heatmap",
    "kinds.dual_axis",
    "kinds.hbar",
    "kinds.heatmap",
    "kinds.histogram",
    "kinds.line",
    "kinds.mean_max",
    "kinds.reference_band",
    "kinds.scatter",
    "kinds.small_multiples",
    "kinds.stacked_100",
    "kinds.stat",
    "kinds.table",
)

#: Layer rank per design § Architecture: `units` (rank 0, outside the kit),
#: `data`, `problems`, `schema`, `format`, `ticks`, `theme`, `layout`,
#: `scales`, `cells` (chart-catalog), `frame`, `marks`, `cartesian`,
#: `validate`, the kinds (one shared rank, `kinds/__init__` included),
#: `registry`, `api`, the package marker.
_RANK: Final[dict[str, int]] = {
    "data": 1,
    "problems": 2,
    "schema": 3,
    "format": 4,
    "ticks": 5,
    "theme": 6,
    "layout": 7,
    "scales": 8,
    "cells": 9,
    "frame": 10,
    "marks": 11,
    "cartesian": 12,
    "validate": 13,
    "kinds": 14,
    "kinds.area": 14,
    "kinds.band": 14,
    "kinds.bar": 14,
    "kinds.box": 14,
    "kinds.calendar_heatmap": 14,
    "kinds.dual_axis": 14,
    "kinds.hbar": 14,
    "kinds.heatmap": 14,
    "kinds.histogram": 14,
    "kinds.line": 14,
    "kinds.mean_max": 14,
    "kinds.reference_band": 14,
    "kinds.scatter": 14,
    "kinds.small_multiples": 14,
    "kinds.stacked_100": 14,
    "kinds.stat": 14,
    "kinds.table": 14,
    "registry": 15,
    "api": 16,
    "": 17,
}

#: Non-stdlib targets any kit module may import, by equality or descent. The
#: kit's own modules are matched separately through `_KIT`.
_ALLOWED_EXTERNAL: Final[tuple[str, ...]] = (
    "fitdocs.render.charts.svg",
    "fitdocs.render.charts.series",
    "fitdocs.render.charts.palette",
    "fitdocs.units",
)

#: Forbidden by equality or descent, independent of the allow-list.
_FORBIDDEN_ROOTS: Final[tuple[str, ...]] = (
    "fitdocs.index",
    "fitdocs.query",
    "fitdocs.dashboards",
    "fitdocs.model",
    "fitdocs.ingest",
    "random",
    "uuid",
    "secrets",
    "locale",
    "time",
    "socket",
    "ssl",
    "http",
    "urllib",
    "ftplib",
    "smtplib",
    "xmlrpc",
    "subprocess",
    "os",
    "pathlib",
    "io",
    "shutil",
    "tempfile",
    "glob",
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

#: Names that are a clock function when imported or reached by attribute. A
#: bare name (a parameter such as `today`) is an injected value, not a clock.
_CLOCK_NAMES: Final[frozenset[str]] = frozenset(
    {
        "now",
        "utcnow",
        "today",
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

#: Raw-text spellings of environment and file access.
_ENVIRONMENT_FILE_PATTERNS: Final[tuple[str, ...]] = (
    r"\bos\.environ\b",
    r"\bgetenv\b",
    r"(?<!\w)open\(",
)

#: Calls that import by string, which no import scan can see through.
_DYNAMIC_IMPORT_NAMES: Final[frozenset[str]] = frozenset(
    {"__import__", "import_module"}
)

_UNRESOLVED: Final[str] = "<relative import escapes the top-level package>"


def _package_dir() -> Path:
    path = fitdocs.render.charts.kit.__file__
    assert path is not None, "the kit package has no __file__"
    return Path(path).parent


def _module_files(root: Path) -> dict[str, Path]:
    """Relative dotted name -> path of every `*.py` file under `root`; the
    marker files are the package ("") and `kinds`."""
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("")
        parts = rel.parts[:-1] if path.name == "__init__.py" else rel.parts
        files[".".join(parts)] = path
    return files


def _full_name(relative: str) -> str:
    return f"{_KIT}.{relative}" if relative else _KIT


def _is_package(relative: str) -> bool:
    return relative in ("", "kinds")


def _is_module(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def _import_targets(tree: ast.Module, relative: str) -> frozenset[str]:
    """Every dotted target `tree` directly imports. Relative imports resolve
    against the module's package; a name imported from a package resolves to
    the submodule when it is one (`from <kit> import marks` ->
    `<kit>.marks`), else to the package itself. A relative import that climbs
    out of the top-level package is reported as `_UNRESOLVED`."""
    module_name = _full_name(relative)
    package = module_name if _is_package(relative) else module_name.rsplit(".", 1)[0]
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module
            else:
                name = "." * node.level + (node.module or "")
                try:
                    base = importlib.util.resolve_name(name, package)
                except ImportError:
                    targets.add(_UNRESOLVED)
                    continue
            if base is None:
                continue
            submodules = {
                f"{base}.{alias.name}"
                for alias in node.names
                if _is_module(f"{base}.{alias.name}")
            }
            targets.update(submodules or {base})
    return frozenset(targets)


def _is_stdlib(target: str) -> bool:
    return target.split(".", 1)[0] in sys.stdlib_module_names


def _matches(target: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        if target == name or target.startswith(f"{name}."):
            return name
    return None


def _allowlist_violations(tree: ast.Module, relative: str) -> list[str]:
    return sorted(
        t
        for t in _import_targets(tree, relative)
        if not _is_stdlib(t) and not _matches(t, (_KIT, *_ALLOWED_EXTERNAL))
    )


def _forbidden_violations(tree: ast.Module, relative: str) -> list[str]:
    return sorted(
        t for t in _import_targets(tree, relative) if _matches(t, _FORBIDDEN_ROOTS)
    )


def _rank_violations(tree: ast.Module, relative: str) -> list[str]:
    """Kit targets that do not sit at a strictly lower rank than `relative`,
    including a kit target the rank table does not name."""
    sender = _RANK[relative]
    found: list[str] = []
    for target in sorted(_import_targets(tree, relative)):
        if target == _KIT:
            name = ""
        elif target.startswith(f"{_KIT}."):
            name = target[len(_KIT) + 1 :]
        else:
            continue
        if name not in _RANK or not _RANK[name] < sender:
            found.append(target)
    return found


def _clock_offenders(source: str) -> list[str]:
    found = [
        s for s in _CLOCK_SPELLINGS if re.search(rf"(?<!\w){re.escape(s)}\b", source)
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in _CLOCK_NAMES:
            found.append(f".{node.attr}")
        elif isinstance(node, ast.ImportFrom):
            found.extend(
                f"from {node.module} import {a.name}"
                for a in node.names
                if a.name in _CLOCK_NAMES
            )
    return found


def _impurity_offenders(source: str) -> list[str]:
    found = [p for p in _ENVIRONMENT_FILE_PATTERNS if re.search(p, source)]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in _DYNAMIC_IMPORT_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_IMPORT_NAMES:
            found.append(f".{node.attr}")
        elif isinstance(node, ast.ImportFrom):
            found.extend(
                f"from {node.module} import {a.name}"
                for a in node.names
                if a.name in _DYNAMIC_IMPORT_NAMES | {"environ", "getenv"}
            )
    return found


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class TestModuleTuple:
    def test_the_tuple_equals_the_directory_both_ways(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        assert set(files) == set(_MODULES), sorted(set(files) ^ set(_MODULES))
        assert len(_MODULES) == len(set(_MODULES))

    def test_the_tuple_is_at_least_thirty_three_modules(self) -> None:
        assert len(_MODULES) >= 33

    def test_the_rank_table_names_the_same_modules(self) -> None:
        assert set(_RANK) == set(_MODULES), sorted(set(_RANK) ^ set(_MODULES))

    def test_the_kinds_and_the_kinds_marker_share_one_rank(self) -> None:
        kind_ranks = {r for name, r in _RANK.items() if name.startswith("kinds")}
        assert kind_ranks == {14}
        assert len([n for n in _RANK if n.startswith("kinds")]) == 18
        assert {r for name, r in _RANK.items() if not name.startswith("kinds")} == (
            set(range(1, 14)) | {15, 16, 17}
        )


class TestImports:
    def test_every_import_is_stdlib_or_allowed(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _allowlist_violations(_parse(path), name) == [], name

    def test_no_module_imports_a_forbidden_root(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _forbidden_violations(_parse(path), name) == [], name


class TestLayerDirection:
    def test_every_kit_import_points_to_a_strictly_lower_rank(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _rank_violations(_parse(path), name) == [], name


class TestPurity:
    def test_no_module_names_a_clock(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _clock_offenders(path.read_text(encoding="utf-8")) == [], name

    def test_no_module_reads_the_environment_opens_a_file_or_imports_dynamically(
        self,
    ) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _impurity_offenders(path.read_text(encoding="utf-8")) == [], name


class TestPositiveControls:
    def test_relative_imports_resolve_against_the_enclosing_package(self) -> None:
        assert _import_targets(ast.parse("from . import data\n"), "frame") == {
            f"{_KIT}.data"
        }
        assert _import_targets(ast.parse("from .data import Column\n"), "frame") == {
            f"{_KIT}.data"
        }
        assert _import_targets(ast.parse("from .. import data\n"), "kinds.line") == {
            f"{_KIT}.data"
        }
        assert _import_targets(ast.parse("from . import line\n"), "kinds") == {
            f"{_KIT}.kinds.line"
        }
        assert _import_targets(ast.parse("from . import api\n"), "") == {f"{_KIT}.api"}

    def test_a_name_imported_from_the_kit_resolves_to_its_submodule(self) -> None:
        tree = ast.parse("from fitdocs.render.charts.kit import marks\n")
        assert _import_targets(tree, "frame") == {f"{_KIT}.marks"}
        assert _rank_violations(tree, "frame") == [f"{_KIT}.marks"]

    def test_a_relative_import_escaping_the_kit_is_reported(self) -> None:
        assert _allowlist_violations(ast.parse("from ... import svg\n"), "frame") == [
            "fitdocs.render"
        ]
        assert _allowlist_violations(
            ast.parse("from ...model import Activity\n"), "frame"
        ) == ["fitdocs.render.model"]
        assert _forbidden_violations(
            ast.parse("from .... import index\n"), "frame"
        ) == ["fitdocs.index"]
        assert _allowlist_violations(ast.parse("from ..... import x\n"), "frame") == [
            _UNRESOLVED
        ]

    def test_each_forbidden_root_is_detected(self) -> None:
        for source, expected in (
            ("import fitdocs.index\n", ["fitdocs.index"]),
            (
                "from fitdocs.index.schema import UNIT_SUFFIXES\n",
                ["fitdocs.index.schema"],
            ),
            ("from fitdocs import index\n", ["fitdocs.index"]),
            ("from fitdocs.query import run\n", ["fitdocs.query"]),
            ("import fitdocs.dashboards.build\n", ["fitdocs.dashboards.build"]),
            ("from fitdocs.model import Activity\n", ["fitdocs.model"]),
            ("from fitdocs.ingest import parse_fit\n", ["fitdocs.ingest"]),
            ("import random\n", ["random"]),
            ("from random import choice\n", ["random"]),
            ("import uuid\n", ["uuid"]),
            ("import secrets\n", ["secrets"]),
            ("import locale\n", ["locale"]),
            ("from time import time\n", ["time"]),
            ("import time as t\n", ["time"]),
            ("import socket\n", ["socket"]),
            ("from urllib.request import urlopen\n", ["urllib.request"]),
            ("from pathlib import Path\n", ["pathlib"]),
            ("import os\n", ["os"]),
            ("import subprocess\n", ["subprocess"]),
            ("import io\n", ["io"]),
            ("import ssl\n", ["ssl"]),
            ("import http.client\n", ["http.client"]),
            ("import ftplib\n", ["ftplib"]),
            ("import smtplib\n", ["smtplib"]),
            ("import xmlrpc.client\n", ["xmlrpc.client"]),
            ("import shutil\n", ["shutil"]),
            ("import tempfile\n", ["tempfile"]),
            ("import glob\n", ["glob"]),
        ):
            assert _forbidden_violations(ast.parse(source), "frame") == expected, source

    def test_each_forbidden_root_is_also_off_the_allow_list(self) -> None:
        for source in (
            "import fitdocs.index\n",
            "from fitdocs.query import run\n",
            "from fitdocs.model import Activity\n",
            "import fitdocs.dashboards\n",
            "from fitdocs.ingest import parse_fit\n",
        ):
            assert _allowlist_violations(ast.parse(source), "frame") != [], source

    def test_a_third_party_import_is_reported(self) -> None:
        assert _allowlist_violations(ast.parse("import numpy\n"), "frame") == ["numpy"]
        assert _allowlist_violations(
            ast.parse("from yaml import safe_load\n"), "frame"
        ) == ["yaml"]
        assert _allowlist_violations(ast.parse("import duckdb\n"), "frame") == [
            "duckdb"
        ]

    def test_allowed_imports_are_not_reported(self) -> None:
        source = (
            "import math\n"
            "from fitdocs.render.charts.svg import el\n"
            "from fitdocs.render.charts.series import gap_segments\n"
            "from fitdocs.render.charts import palette\n"
            "from fitdocs.units import unit_named\n"
            "from fitdocs.render.charts.kit.data import Column\n"
        )
        tree = ast.parse(source)
        assert _allowlist_violations(tree, "marks") == []
        assert _forbidden_violations(tree, "marks") == []

    def test_a_sibling_charts_module_is_not_allowed(self) -> None:
        assert _allowlist_violations(
            ast.parse("from fitdocs.render.charts import hero\n"), "frame"
        ) == ["fitdocs.render.charts.hero"]

    def test_the_rank_check_reports_each_upward_sideways_and_unknown_import(
        self,
    ) -> None:
        for source, relative, expected in (
            ("from . import marks\n", "frame", [f"{_KIT}.marks"]),
            ("from .frame import x\n", "frame", [f"{_KIT}.frame"]),
            ("from .. import registry\n", "kinds.line", [f"{_KIT}.registry"]),
            ("from .. import api\n", "kinds.line", [f"{_KIT}.api"]),
            ("from . import area\n", "kinds.line", [f"{_KIT}.kinds.area"]),
            ("from . import line\n", "kinds", [f"{_KIT}.kinds.line"]),
            ("from .kinds import line\n", "registry", []),
            ("from . import registry\n", "api", []),
            ("from . import api\n", "registry", [f"{_KIT}.api"]),
            ("from fitdocs.render.charts import kit\n", "api", [_KIT]),
            ("from . import brand_new\n", "frame", [_KIT]),
            ("from .brand_new import x\n", "frame", [f"{_KIT}.brand_new"]),
            ("from . import data\n", "frame", []),
            ("from .. import frame\n", "kinds.line", []),
            ("from . import data\n", "problems", []),
            ("from . import problems\n", "data", [f"{_KIT}.problems"]),
            ("from . import frame\n", "cells", [f"{_KIT}.frame"]),
            ("from . import scales\n", "cells", []),
        ):
            assert _rank_violations(ast.parse(source), relative) == expected, source

    def test_every_clock_form_is_detected(self) -> None:
        for source in (
            *(f"x = {spelling}()\n" for spelling in _CLOCK_SPELLINGS),
            '"""e.g. datetime.now(UTC)"""\n',
            '"""e.g. datetime.datetime.now(UTC)"""\n',
            "from time import time_ns\n",
            "from datetime import datetime\nx = datetime.now()\n",
            "from datetime import date\nx = date.today()\n",
            "x = clock.monotonic()\n",
            "x = a.today()\n",
            "from time import sleep\n",
        ):
            assert _clock_offenders(source), source

    def test_each_clock_spelling_is_detected_in_a_docstring(self) -> None:
        for spelling in _CLOCK_SPELLINGS:
            assert _clock_offenders(f'"""e.g. {spelling}(UTC)"""\n') == [spelling], (
                spelling
            )

    def test_descent_needs_the_dot_boundary(self) -> None:
        assert (
            _forbidden_violations(ast.parse("import fitdocs.indexer\n"), "frame") == []
        )
        assert _forbidden_violations(ast.parse("import timeit\n"), "frame") == []
        assert _allowlist_violations(
            ast.parse("import fitdocs.render.charts.svgx\n"), "frame"
        ) == ["fitdocs.render.charts.svgx"]
        assert _allowlist_violations(ast.parse("import fitdocs.unitsx\n"), "frame") == [
            "fitdocs.unitsx"
        ]
        assert _allowlist_violations(
            ast.parse("import fitdocs.render.charts.kitx\n"), "frame"
        ) == ["fitdocs.render.charts.kitx"]

    def test_an_injected_today_parameter_is_not_a_clock(self) -> None:
        assert _clock_offenders("def f(today):\n    return today\n") == []
        assert _clock_offenders("def f(today, now):\n    return today(), now()\n") == []

    def test_timestamp_and_longer_names_are_not_clock_names(self) -> None:
        assert _clock_offenders("x = a.start_time.timestamp()\n") == []
        assert _clock_offenders("x = runtime.time_stamp\n") == []
        assert _clock_offenders("x = time.timestamp\n") == []
        assert _clock_offenders("x = a_time.time\n") == []

    def test_each_impure_form_is_detected(self) -> None:
        for source in (
            "import os\nx = os.environ['A']\n",
            "from os import environ\n",
            "from os import getenv\n",
            "import os\nx = os.getenv('A')\n",
            "x = open('f')\n",
            "x = p.open()\n",
            "x = __import__('os')\n",
            "import importlib\nx = importlib.import_module('os')\n",
            "from importlib import import_module\n",
        ):
            assert _impurity_offenders(source), source

    def test_names_that_merely_contain_open_are_not_impure(self) -> None:
        assert _impurity_offenders("x = reopen(1)\n") == []
        assert _impurity_offenders("x = is_open(1)\n") == []
        assert _impurity_offenders("def f(opening):\n    return opening\n") == []
