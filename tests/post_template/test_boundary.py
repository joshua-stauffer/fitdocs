"""The `fitdocs.post_template` package boundary (post-templates task 1.6;
Req 13.1, 13.4). See "Allowed Dependencies" in
`.kiro/specs/post-templates/design.md`.

Modelled on `tests/publish/test_boundary.py` and `tests/query/test_boundary.py`,
whose import resolver, network-capable standard-library list and clock and
randomness scan are reused. Four scans, each a function of a root directory so
a test can drive it against a scratch tree:

1. **Import table.** Every module's exact set of direct non-standard-library
   import targets, pinned by equality against `_ALLOWED_IMPORT_TARGETS` and
   checked against the directory in both directions.
2. **Forbidden names**, independent of the table.
3. **Clock and randomness spellings**, matched against raw text.
4. **Reverse importers.** Outside the package only `fitdocs.cli` imports it.

A scan that saw no module raises, so a walk over an empty directory cannot
pass. A walk over the wrong non-empty directory is caught by the live-walk
assertions in `TestRealPackage`, which compare what the walks enumerate with
the package and with the real source tree.

**Adding a module.** Each later task appends one entry for its module to
`_ALLOWED_IMPORT_TARGETS`. The clock scan reads raw text, so no docstring or
comment in the package may quote a spelling.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

import fitdocs
import fitdocs.post_template
from tests.publish.test_boundary import (
    _FORBIDDEN_STDLIB,
    _clock_and_random_offenders,
    _import_set_mismatch,
    _import_targets_of_tree,
    _non_stdlib,
)
from tests.query.test_boundary import _import_targets as _query_import_targets

_PACKAGE: Final = "fitdocs.post_template"

#: Every module's exact set of direct non-standard-library import targets.
#: APPEND one entry here when you add a module under `fitdocs/post_template/`.
_ALLOWED_IMPORT_TARGETS: Final[dict[str, frozenset[str]]] = {
    "fitdocs.post_template": frozenset(),
    "fitdocs.post_template.model": frozenset({"fitdocs.publish.request"}),
    "fitdocs.post_template.region": frozenset(
        {"fitdocs.contract", "fitdocs.post_template.model", "fitdocs.publish.request"}
    ),
    "fitdocs.post_template.resolve": frozenset(
        {
            "fitdocs.post_template.model",
            "fitdocs.post_template.template",
            "fitdocs.query.command",
            "fitdocs.query.statement",
        }
    ),
    "fitdocs.post_template.template": frozenset(
        {
            "fitdocs.layout",
            "fitdocs.publish.template",
            "fitdocs.publish.values",
            "fitdocs.settings",
        }
    ),
}

#: Forbidden targets for every module in the package (design: "Allowed
#: Dependencies"), each together with its submodules. `duckdb` is reached only
#: through `fitdocs.query`, and the CLI sits above the package.
_FORBIDDEN_TARGETS: Final[tuple[str, ...]] = (
    "duckdb",
    "fitdocs.index",
    "fitdocs.dashboards",
    "fitdocs.render",
    "fitdocs.load",
    "fitdocs.metrics",
    "fitdocs.ingest",
    "fitdocs.sync",
    "fitdocs.cli",
    *_FORBIDDEN_STDLIB,
)

#: The only module outside the package that may import it.
_ALLOWED_IMPORTERS: Final[frozenset[str]] = frozenset({"fitdocs.cli"})


# --------------------------------------------------------------------------- #
# Enumeration (a function of the root directory)
# --------------------------------------------------------------------------- #


def _package_dir() -> Path:
    path = fitdocs.post_template.__file__
    assert path is not None
    return Path(path).parent


def _src_root() -> Path:
    path = fitdocs.__file__
    assert path is not None
    return Path(path).parent


def _dotted(rel: Path, prefix: str) -> tuple[str, bool]:
    """(dotted module name, is a package) of a `*.py` path relative to a root."""
    is_package = rel.name == "__init__.py"
    parts = rel.parts[:-1] if is_package else rel.with_suffix("").parts
    return ".".join((prefix, *parts)), is_package


def _package_modules(root: Path) -> dict[str, tuple[Path, bool]]:
    """Every module under `root`, named as if `root` were the package."""
    found: dict[str, tuple[Path, bool]] = {}
    for path in sorted(root.rglob("*.py")):
        name, is_package = _dotted(path.relative_to(root), _PACKAGE)
        found[name] = (path, is_package)
    return found


def _seen(modules: object, what: str) -> None:
    if not modules:
        raise AssertionError(f"{what}: the scan saw no module")


def _tree(path: Path, name: str) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=name)


# --------------------------------------------------------------------------- #
# The four scans
# --------------------------------------------------------------------------- #


def _import_table_problems(root: Path, table: dict[str, frozenset[str]]) -> list[str]:
    modules = _package_modules(root)
    _seen(modules, "import table")
    problems: list[str] = []
    missing = sorted(set(table) - set(modules))
    unregistered = sorted(set(modules) - set(table))
    if missing:
        problems.append(f"registered but missing on disk: {missing}")
    if unregistered:
        problems.append(f"on disk but not registered: {unregistered}")
    for name, (path, is_package) in modules.items():
        if name not in table:
            continue
        measured = _non_stdlib(
            _import_targets_of_tree(_tree(path, name), name, is_package=is_package)
        )
        extra, stale = _import_set_mismatch(measured, table[name])
        if extra or stale:
            problems.append(
                f"{name}: unexpected {sorted(extra)}; "
                f"pinned but no longer imported {sorted(stale)}"
            )
    return problems


def _forbidden_reason(target: str) -> str | None:
    if target == "?":
        return "unresolvable dynamic import"
    for forbidden in _FORBIDDEN_TARGETS:
        if target == forbidden or target.startswith(forbidden + "."):
            return f"forbidden {forbidden}"
    return None


def _forbidden_problems(root: Path) -> list[str]:
    modules = _package_modules(root)
    _seen(modules, "forbidden names")
    problems: list[str] = []
    for name, (path, is_package) in modules.items():
        targets = _import_targets_of_tree(
            _tree(path, name), name, is_package=is_package
        )
        for target in sorted(targets):
            reason = _forbidden_reason(target)
            if reason is not None:
                problems.append(f"{name} imports {target!r}: {reason}")
    return problems


def _clock_problems(root: Path) -> list[str]:
    modules = _package_modules(root)
    _seen(modules, "clock and randomness")
    return [
        f"{name}: {hit!r}"
        for name, (path, _) in modules.items()
        for hit in _clock_and_random_offenders(path.read_text(encoding="utf-8"))
    ]


#: The one package module that may import `fitdocs.query` (design: "Allowed
#: Dependencies"; the query guard lists it as a third importer).
_QUERY_IMPORTER: Final = "fitdocs.post_template.resolve"


def _is_query_target(target: str) -> bool:
    return target == "fitdocs.query" or target.startswith("fitdocs.query.")


def _query_targets(name: str, path: Path, is_package: bool) -> frozenset[str]:
    """Every `fitdocs.query` target a module imports, by both repo resolvers."""
    source = path.read_text(encoding="utf-8")
    found = _query_import_targets(
        source, name + ".__init__" if is_package else name
    ) | _import_targets_of_tree(_tree(path, name), name, is_package=is_package)
    return frozenset(t for t in found if _is_query_target(t))


def _query_importer_problems(root: Path) -> list[str]:
    """Package modules other than the resolver that import `fitdocs.query`."""
    modules = _package_modules(root)
    _seen(modules, "query importers")
    return [
        f"{name} imports {sorted(targets)}"
        for name, (path, is_package) in modules.items()
        if name != _QUERY_IMPORTER
        and (targets := _query_targets(name, path, is_package))
    ]


def _reverse_scan(src_root: Path) -> tuple[list[str], frozenset[str]]:
    """(problems, modules seen): modules outside `<src_root>/post_template`
    that import the package and are not in `_ALLOWED_IMPORTERS`. `src_root`
    stands for `src/fitdocs`. Targets are the union of the two repo resolvers,
    the query guard's (relative and dynamic forms with `fromlist` and
    `package`) and the publish guard's."""
    outside: dict[str, tuple[Path, bool]] = {}
    for path in sorted(src_root.rglob("*.py")):
        rel = path.relative_to(src_root)
        if rel.parts[0] == "post_template":
            continue
        name, is_package = _dotted(rel, "fitdocs")
        outside[name] = (path, is_package)
    _seen(outside, "reverse importers")
    problems: list[str] = []
    for name, (path, is_package) in outside.items():
        if name in _ALLOWED_IMPORTERS:
            continue
        source = path.read_text(encoding="utf-8")
        targets = _query_import_targets(
            source, name + ".__init__" if is_package else name
        ) | _import_targets_of_tree(_tree(path, name), name, is_package=is_package)
        if any(t == _PACKAGE or t.startswith(_PACKAGE + ".") for t in targets):
            problems.append(f"{name} imports the post-template package")
    return problems, frozenset(outside)


def _reverse_importer_problems(src_root: Path) -> list[str]:
    return _reverse_scan(src_root)[0]


# --------------------------------------------------------------------------- #
# On the real package
# --------------------------------------------------------------------------- #


class TestRealPackage:
    def test_import_table_matches_the_package(self) -> None:
        assert _import_table_problems(_package_dir(), _ALLOWED_IMPORT_TARGETS) == []

    def test_the_package_marker_imports_nothing(self) -> None:
        path = _package_dir() / "__init__.py"
        assert (
            _import_targets_of_tree(_tree(path, _PACKAGE), _PACKAGE, is_package=True)
            == frozenset()
        )

    def test_no_module_imports_a_forbidden_name(self) -> None:
        assert _forbidden_problems(_package_dir()) == []

    def test_no_module_reads_a_clock_or_draws_randomness(self) -> None:
        assert _clock_problems(_package_dir()) == []

    def test_only_the_cli_imports_the_package_and_the_walk_is_live(self) -> None:
        problems, seen = _reverse_scan(_src_root())
        assert problems == []
        assert {"fitdocs.cli", "fitdocs.publish.engine"} <= seen
        assert len(seen) > 100
        assert not any(m.startswith(_PACKAGE) for m in seen)

    def test_the_package_walk_is_live(self) -> None:
        assert _package_dir().name == "post_template"
        assert set(_package_modules(_package_dir())) == set(_ALLOWED_IMPORT_TARGETS)

    def test_only_the_resolver_imports_query_and_it_does(self) -> None:
        assert _query_importer_problems(_package_dir()) == []
        modules = _package_modules(_package_dir())
        path, is_package = modules[_QUERY_IMPORTER]
        # A positive control: the scan sees the resolver's own query imports.
        targets = _query_targets(_QUERY_IMPORTER, path, is_package)
        assert "fitdocs.query.command.open_session" in targets
        assert "fitdocs.query.statement.StatementFailed" in targets

    def test_the_allowed_importer_set_is_exactly_the_cli(self) -> None:
        assert frozenset({"fitdocs.cli"}) == _ALLOWED_IMPORTERS


# --------------------------------------------------------------------------- #
# Scratch trees: each scan goes red on its violation
# --------------------------------------------------------------------------- #

_Scratch = Callable[[str], Path]


def _scratch_package(make: _Scratch, extra: dict[str, str]) -> Path:
    """A copy of the real package plus `extra` files (name -> text)."""
    root = make("post-template-scratch")
    for path in _package_dir().rglob("*.py"):
        target = root / path.relative_to(_package_dir())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    for name, text in extra.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def _model_text() -> str:
    return (_package_dir() / "model.py").read_text(encoding="utf-8")


def test_a_clean_scratch_copy_passes_every_package_scan(
    per_test_directory: _Scratch,
) -> None:
    root = _scratch_package(per_test_directory, {})
    assert _import_table_problems(root, _ALLOWED_IMPORT_TARGETS) == []
    assert _forbidden_problems(root) == []
    assert _clock_problems(root) == []


#: One import statement per forbidden name, written out so that dropping an
#: entry from `_FORBIDDEN_TARGETS` leaves its statement undetected.
_FORBIDDEN_STATEMENTS: Final[tuple[str, ...]] = (
    "import duckdb",
    "from duckdb import connect",
    "import fitdocs.index",
    "from fitdocs.index import build",
    "from fitdocs import index",
    "import fitdocs.dashboards",
    "from fitdocs import dashboards",
    "import fitdocs.render",
    "from fitdocs import render",
    "import fitdocs.load",
    "from fitdocs import load",
    "import fitdocs.metrics",
    "from fitdocs import metrics",
    "import fitdocs.ingest",
    "from fitdocs import ingest",
    "import fitdocs.sync",
    "from fitdocs import sync",
    "import fitdocs.cli",
    "from fitdocs import cli",
    "import socket",
    "import ssl",
    "import http.client",
    "import urllib",
    "import urllib.request",
    "import urllib.parse",
    "import ftplib",
    "import smtplib",
    "import poplib",
    "import imaplib",
    "import nntplib",
    "import telnetlib",
    "import xmlrpc.client",
    "import socketserver",
    "import asyncio",
    "import selectors",
    "import select",
    "import webbrowser",
    "import wsgiref.simple_server",
    "import _socket",
    "import _ssl",
    "import asyncore",
    "import asynchat",
    "import smtpd",
    "import multiprocessing",
    "import logging.handlers",
    "import xml.sax",
    "import xml.dom.xmlbuilder",
    "import xml.dom.pulldom",
    'import importlib\nimportlib.import_module("duckdb")',
    "import importlib\nimportlib.import_module(name)",
)


class TestForbiddenNamesGoRed:
    def test_the_statements_cover_every_listed_name(self) -> None:
        """Two-sided: each listed name has a statement, and the statements name
        nothing unlisted (a name added to the list needs its statement)."""
        covered: set[str] = set()
        for statement in _FORBIDDEN_STATEMENTS:
            for target in _import_targets_of_tree(
                ast.parse(statement), "fitdocs.post_template.scratch"
            ):
                for forbidden in _FORBIDDEN_TARGETS:
                    if target == forbidden or target.startswith(forbidden + "."):
                        covered.add(forbidden)
        assert covered == set(_FORBIDDEN_TARGETS)

    @pytest.mark.parametrize("statement", _FORBIDDEN_STATEMENTS)
    def test_a_scratch_copy_of_model_adding_the_import_is_red(
        self, statement: str, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "model.py").write_text(
            statement + "\n" + _model_text(), encoding="utf-8"
        )
        assert _forbidden_problems(root), statement

    @pytest.mark.parametrize(
        "statement",
        [
            "import os",
            "import logging",
            "from datetime import date",
            "from fitdocs.publish.request import Post",
            "from fitdocs.publish import compose",
            "from fitdocs import contract",
            "import xml.etree.ElementTree",
        ],
    )
    def test_permitted_imports_are_clean(
        self, statement: str, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "extra.py").write_text(statement + "\n", encoding="utf-8")
        assert _forbidden_problems(root) == []

    def test_an_import_in_another_module_and_in_the_marker_is_red(
        self, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {"extra.py": "import duckdb\n"})
        assert [p for p in _forbidden_problems(root) if "post_template.extra" in p]
        root = _scratch_package(per_test_directory, {"__init__.py": "import duckdb\n"})
        assert _forbidden_problems(root)


class TestImportTableGoesRed:
    def test_an_unpinned_import_is_red(self, per_test_directory: _Scratch) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "model.py").write_text(
            "from fitdocs.publish.compose import compose_post\n" + _model_text(),
            encoding="utf-8",
        )
        problems = _import_table_problems(root, _ALLOWED_IMPORT_TARGETS)
        assert any("fitdocs.publish.compose" in p for p in problems)

    def test_a_dropped_import_leaves_a_stale_entry(
        self, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "model.py").write_text("import os\n", encoding="utf-8")
        problems = _import_table_problems(root, _ALLOWED_IMPORT_TARGETS)
        assert any("fitdocs.publish.request" in p for p in problems)

    def test_an_unregistered_and_a_missing_module_are_red(
        self, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {"sneaky.py": "import os\n"})
        problems = _import_table_problems(root, _ALLOWED_IMPORT_TARGETS)
        assert any("fitdocs.post_template.sneaky" in p for p in problems)
        table = {**_ALLOWED_IMPORT_TARGETS, "fitdocs.post_template.gone": frozenset()}
        problems = _import_table_problems(
            _scratch_package(per_test_directory, {}), table
        )
        assert any("fitdocs.post_template.gone" in p for p in problems)

    def test_a_subpackage_is_enumerated(self, per_test_directory: _Scratch) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "sub").mkdir()
        (root / "sub" / "__init__.py").write_text("", encoding="utf-8")
        (root / "sub" / "deep.py").write_text("", encoding="utf-8")
        problems = _import_table_problems(root, _ALLOWED_IMPORT_TARGETS)
        assert any("fitdocs.post_template.sub.deep" in p for p in problems)
        assert any("'fitdocs.post_template.sub'" in p for p in problems)

    def test_a_relative_import_is_resolved(self, per_test_directory: _Scratch) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "extra.py").write_text("from . import model\n", encoding="utf-8")
        table = {**_ALLOWED_IMPORT_TARGETS, "fitdocs.post_template.extra": frozenset()}
        problems = _import_table_problems(root, table)
        assert any("fitdocs.post_template.model" in p for p in problems)


class TestQueryImporterScanGoesRed:
    @pytest.mark.parametrize(
        "statement",
        [
            "import fitdocs.query",
            "import fitdocs.query.command",
            "from fitdocs import query",
            "from fitdocs.query import command",
            "from fitdocs.query.statement import Restriction",
            "from ..query import command",
            "from .. import query",
            'import importlib\nimportlib.import_module("fitdocs.query.command")',
        ],
    )
    @pytest.mark.parametrize("victim", ["model.py", "region.py", "__init__.py"])
    def test_another_module_importing_query_is_red(
        self, statement: str, victim: str, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {})
        original = (root / victim).read_text(encoding="utf-8")
        (root / victim).write_text(statement + "\n" + original, encoding="utf-8")
        problems = _query_importer_problems(root)
        assert len(problems) == 1, (statement, victim, problems)
        assert problems[0].startswith(
            "fitdocs.post_template"
            + ("" if victim == "__init__.py" else f".{victim[:-3]}")
        )

    def test_the_resolver_itself_and_unrelated_imports_are_clean(
        self, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(
            per_test_directory,
            {"extra.py": "from fitdocs.queryish import x\nimport fitdocs.querying\n"},
        )
        assert _query_importer_problems(root) == []

    def test_an_empty_directory_is_refused(self, per_test_directory: _Scratch) -> None:
        with pytest.raises(AssertionError, match="saw no module"):
            _query_importer_problems(per_test_directory("empty-package"))


class TestClockScanGoesRed:
    @pytest.mark.parametrize(
        "line",
        [
            "x = datetime.now()",
            "x = datetime.datetime.now()",
            "x = datetime.utcnow()",
            "x = date.today()",
            "x = time.time()",
            "x = time.monotonic()",
            "x = time.perf_counter()",
            "import time",
            "from time import monotonic",
            "from datetime import datetime as dt",
            "x = secrets.token_hex(8)",
            "x = uuid.uuid4()",
            "x = random.random()",
            "x = os.urandom(8)",
            '"""a docstring quoting datetime.now(UTC)"""',
            "# a comment quoting time.time()",
        ],
    )
    def test_a_scratch_copy_adding_the_spelling_is_red(
        self, line: str, per_test_directory: _Scratch
    ) -> None:
        root = _scratch_package(per_test_directory, {})
        (root / "model.py").write_text(
            _model_text() + "\n" + line + "\n", encoding="utf-8"
        )
        assert _clock_problems(root), line

    def test_an_injected_clock_is_clean(self, per_test_directory: _Scratch) -> None:
        root = _scratch_package(
            per_test_directory,
            {"extra.py": "def f(now, mint):\n    return now(), mint()\n"},
        )
        assert _clock_problems(root) == []


class TestReverseImporters:
    @staticmethod
    def _src(make: _Scratch, files: dict[str, str]) -> Path:
        root = make("src-fitdocs")
        (root / "post_template").mkdir()
        (root / "post_template" / "__init__.py").write_text("", encoding="utf-8")
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root

    @pytest.mark.parametrize(
        "source",
        [
            "import fitdocs.post_template",
            "import fitdocs.post_template.model",
            "import fitdocs.post_template.model as m",
            "from fitdocs import post_template",
            "from fitdocs.post_template import model",
            "from fitdocs.post_template.model import FillCode",
            "from .post_template import model",
            "from . import post_template",
            'import importlib\nimportlib.import_module("fitdocs.post_template")',
            '__import__("fitdocs.post_template.model")',
            'import importlib\nimportlib.import_module(".post_template", "fitdocs")',
            '__import__("fitdocs", fromlist=["post_template"])',
            '__import__("fitdocs", globals(), locals(), ["post_template"])',
            'loader.import_module("fitdocs.post_template")',
        ],
    )
    def test_a_module_that_is_not_the_cli_importing_the_package_is_red(
        self, source: str, per_test_directory: _Scratch
    ) -> None:
        root = self._src(per_test_directory, {"other.py": source + "\n"})
        assert _reverse_importer_problems(root) == [
            "fitdocs.other imports the post-template package"
        ]

    @pytest.mark.parametrize(
        ("rel", "module"),
        [("__init__.py", "fitdocs"), ("sub/__init__.py", "fitdocs.sub")],
        ids=["root-init-level-1", "sub-init-level-2"],
    )
    def test_a_package_init_resolves_its_relative_dynamic_import(
        self, rel: str, module: str, per_test_directory: _Scratch
    ) -> None:
        level = 1 if rel == "__init__.py" else 2
        source = f'__import__("post_template", globals(), locals(), [], {level})\n'
        root = self._src(per_test_directory, {rel: source})
        assert _reverse_importer_problems(root) == [
            f"{module} imports the post-template package"
        ]

    @pytest.mark.parametrize(
        "source",
        [
            "import fitdocs.post_template.model",
            "from fitdocs.post_template import model",
            "from .post_template import model",
        ],
    )
    def test_the_cli_importing_the_package_is_clean(
        self, source: str, per_test_directory: _Scratch
    ) -> None:
        root = self._src(per_test_directory, {"cli.py": source + "\n"})
        assert _reverse_importer_problems(root) == []

    @pytest.mark.parametrize(
        "rel",
        [
            "cli2.py",
            "clix.py",
            "publish/cli.py",
            "sub/__init__.py",
            "publish/engine.py",
        ],
    )
    def test_the_allowlist_is_exactly_the_cli_module(
        self, rel: str, per_test_directory: _Scratch
    ) -> None:
        """Same text, other names: only `cli.py` at the root is exempt."""
        root = self._src(
            per_test_directory, {rel: "from fitdocs.post_template import model\n"}
        )
        assert len(_reverse_importer_problems(root)) == 1

    def test_modules_inside_the_package_are_not_reverse_importers(
        self, per_test_directory: _Scratch
    ) -> None:
        root = self._src(
            per_test_directory,
            {
                "cli.py": "",
                "post_template/engine.py": "from fitdocs.post_template import model\n",
            },
        )
        assert _reverse_importer_problems(root) == []

    def test_a_label_that_only_looks_like_the_package_is_clean(
        self, per_test_directory: _Scratch
    ) -> None:
        root = self._src(
            per_test_directory,
            {
                "other.py": "label = 'fitdocs.post_template'\n",
                "post_templates.py": "import fitdocs.post_templates_extra\n",
            },
        )
        assert _reverse_importer_problems(root) == []


class TestEveryScanNeedsAModule:
    @pytest.mark.parametrize(
        "scan",
        [
            lambda root: _import_table_problems(root, _ALLOWED_IMPORT_TARGETS),
            _forbidden_problems,
            _clock_problems,
            _reverse_importer_problems,
        ],
        ids=["import-table", "forbidden", "clock", "reverse-importers"],
    )
    def test_an_empty_directory_is_red(
        self, scan: Callable[[Path], object], per_test_directory: _Scratch
    ) -> None:
        with pytest.raises(AssertionError, match="saw no module"):
            scan(per_test_directory("empty"))

    def test_the_reverse_scan_ignores_the_package_when_counting(
        self, per_test_directory: _Scratch
    ) -> None:
        """A tree holding only the package has nothing outside it to scan."""
        root = per_test_directory("only-package")
        (root / "post_template").mkdir()
        (root / "post_template" / "__init__.py").write_text("", encoding="utf-8")
        with pytest.raises(AssertionError, match="saw no module"):
            _reverse_importer_problems(root)

    def test_a_one_module_tree_is_enough(self, per_test_directory: _Scratch) -> None:
        root = per_test_directory("one")
        (root / "__init__.py").write_text("", encoding="utf-8")
        assert _clock_problems(root) == []
        assert _forbidden_problems(root) == []
