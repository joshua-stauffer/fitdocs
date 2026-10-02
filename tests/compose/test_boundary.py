"""The `fitdocs.compose` package boundary (channel-merge 1.2; Req 7.2;
design.md § Allowed Dependencies and § Testing Strategy > Guards).

Every `*.py` file under `src/fitdocs/compose/`, the package marker included,
is parsed. Three rules run over it:

1. **Per-module allowlist** (`TestImportAllowlist`): each module's direct
   imports are resolved to dotted targets and every non-stdlib target must be
   in that module's hand-written allowlist, which names all seven planned
   modules: the marker plus `types`, `stretches`, `alignment`, `donation`,
   `composer` and `archive`. `TestPositiveControls` asserts the scanned set
   equals those seven exactly, so an eighth module, or a missing one, fails.
2. **Forbidden names** (`TestForbiddenNames`): independent of the allowlist,
   no module imports the hard-rule packages (`fitdocs.sync`, `render`, ...),
   `yaml`, `urllib`, `socket` or `time`; outside `archive.py` none imports a
   filesystem module (`pathlib`, `os`, ...) or `fitdocs.contract`,
   `fitdocs.layout`, `fitdocs.ingest`.
3. **Clock names** (`TestClockNames`): no module names a clock function.

The scan functions are also run on synthetic sources, so a rule that stopped
matching would show up as a positive control going red.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Final

import fitdocs.compose

#: The seven planned modules, by dotted name: the package marker and the six
#: submodules. `archive` alone may touch the filesystem.
_ALL_SEVEN: Final[tuple[str, ...]] = (
    "fitdocs.compose",
    "fitdocs.compose.types",
    "fitdocs.compose.stretches",
    "fitdocs.compose.alignment",
    "fitdocs.compose.donation",
    "fitdocs.compose.composer",
    "fitdocs.compose.archive",
)

_CORE_EXTERNAL: Final[frozenset[str]] = frozenset(
    {
        "fitdocs.model",
        "fitdocs.identity.kinds",
        "fitdocs.identity.matching",
    }
)

#: Per-module allowed non-stdlib import targets (design.md § Allowed
#: Dependencies). Written as literals, not derived from the sources.
_ALLOWED: Final[dict[str, frozenset[str]]] = {
    "fitdocs.compose": frozenset(),
    "fitdocs.compose.types": frozenset({"fitdocs.model", "fitdocs.identity.kinds"}),
    "fitdocs.compose.stretches": _CORE_EXTERNAL | {"fitdocs.compose.types"},
    "fitdocs.compose.alignment": _CORE_EXTERNAL
    | {"fitdocs.compose.types", "fitdocs.compose.stretches"},
    "fitdocs.compose.donation": _CORE_EXTERNAL | {"fitdocs.compose.types"},
    "fitdocs.compose.composer": _CORE_EXTERNAL
    | {
        "fitdocs.compose.types",
        "fitdocs.compose.alignment",
        "fitdocs.compose.donation",
    },
    "fitdocs.compose.archive": _CORE_EXTERNAL
    | {
        "fitdocs.compose.composer",
        "fitdocs.contract",
        "fitdocs.layout",
        "fitdocs.ingest",
        "fitdocs.compose.types",
    },
}

#: Hard rules: no compose module imports these (by equality or descent).
_FORBIDDEN_TARGETS: Final[tuple[str, ...]] = (
    "fitdocs.sync",
    "fitdocs.render",
    "fitdocs.load",
    "fitdocs.metrics",
    "fitdocs.performance",
    "fitdocs.history",
    "fitdocs.plans",
    "fitdocs.audit",
    "fitdocs.cli",
    "fitdocs.tiles",
    "fitdocs.inbox",
    "fitdocs.connectors",
    "yaml",
    "urllib",
    "socket",
    "time",
)

#: Targets only `compose/archive.py` may import.
_ARCHIVE_ONLY_TARGETS: Final[tuple[str, ...]] = (
    "fitdocs.contract",
    "fitdocs.layout",
    "fitdocs.ingest",
    "pathlib",
    "os",
    "shutil",
    "tempfile",
    "glob",
    "io",
)

_ARCHIVE: Final[str] = "fitdocs.compose.archive"

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

#: Names that are a clock function when called or imported.
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


def _package_dir() -> Path:
    path = fitdocs.compose.__file__
    assert path is not None, "fitdocs.compose has no __file__"
    return Path(path).parent


def _module_files(root: Path) -> dict[str, Path]:
    """Dotted name -> path of every `*.py` file under `root`; the marker is
    `fitdocs.compose` itself."""
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).with_suffix("")
        parts = rel.parts[:-1] if path.name == "__init__.py" else rel.parts
        files[".".join(("fitdocs", "compose", *parts))] = path
    return files


def _is_module(dotted: str) -> bool:
    if dotted in _ALLOWED:
        return True
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def _import_targets(tree: ast.Module, module_name: str) -> frozenset[str]:
    """Every dotted target `tree` directly imports. A name imported from a
    package resolves to the submodule when it is one (`from fitdocs import
    sync` -> `fitdocs.sync`), else to the package itself."""
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module
            else:
                package = (
                    module_name
                    if module_name == "fitdocs.compose"
                    else module_name.rsplit(".", 1)[0]
                )
                name = "." * node.level + (node.module or "")
                try:
                    base = importlib.util.resolve_name(name, package)
                except ImportError:
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


def _allowlist_violations(
    tree: ast.Module, module_name: str, allowed: frozenset[str]
) -> list[str]:
    return sorted(
        t
        for t in _import_targets(tree, module_name)
        if not _is_stdlib(t) and t not in allowed
    )


def _forbidden_violations(tree: ast.Module, module_name: str) -> list[str]:
    found: list[str] = []
    for target in sorted(_import_targets(tree, module_name)):
        if _matches(target, _FORBIDDEN_TARGETS) or (
            module_name != _ARCHIVE and _matches(target, _ARCHIVE_ONLY_TARGETS)
        ):
            found.append(target)
    return found


def _clock_offenders(source: str) -> list[str]:
    found = [
        s for s in _CLOCK_SPELLINGS if re.search(rf"(?<!\w){re.escape(s)}\b", source)
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in _CLOCK_NAMES:
            found.append(f".{node.attr}")
        elif isinstance(node, ast.Name) and node.id in _CLOCK_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.ImportFrom):
            found.extend(
                f"from {node.module} import {a.name}"
                for a in node.names
                if a.name in _CLOCK_NAMES
            )
    return found


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class TestImportAllowlist:
    def test_every_scanned_module_imports_only_its_allowed_targets(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _allowlist_violations(_parse(path), name, _ALLOWED[name]) == [], name

    def test_allowlist_names_the_seven_planned_modules(self) -> None:
        assert set(_ALLOWED) == set(_ALL_SEVEN)

    def test_relative_imports_resolve_against_the_enclosing_package(self) -> None:
        assert _import_targets(
            ast.parse("from . import types\n"), "fitdocs.compose.composer"
        ) == {"fitdocs.compose.types"}
        assert _import_targets(
            ast.parse("from .. import render\n"), "fitdocs.compose.composer"
        ) == {"fitdocs.render"}
        assert _import_targets(
            ast.parse("from . import types\n"), "fitdocs.compose"
        ) == {"fitdocs.compose.types"}

    def test_a_disallowed_import_is_reported(self) -> None:
        tree = ast.parse("import fitdocs.sync\nfrom fitdocs.model import Activity\n")
        assert _allowlist_violations(
            tree, "fitdocs.compose.types", _ALLOWED["fitdocs.compose.types"]
        ) == ["fitdocs.sync"]

    def test_composer_import_is_allowed_in_archive_only(self) -> None:
        tree = ast.parse("from fitdocs.compose import composer\n")
        assert _allowlist_violations(tree, _ARCHIVE, _ALLOWED[_ARCHIVE]) == []
        assert _allowlist_violations(
            tree, "fitdocs.compose.stretches", _ALLOWED["fitdocs.compose.stretches"]
        ) == ["fitdocs.compose.composer"]

    def test_the_archive_only_targets_are_not_allowed_elsewhere(self) -> None:
        for name, allowed in _ALLOWED.items():
            if name == _ARCHIVE:
                continue
            for target in ("fitdocs.contract", "fitdocs.layout", "fitdocs.ingest"):
                assert target not in allowed, (name, target)
        assert {"fitdocs.contract", "fitdocs.layout", "fitdocs.ingest"} <= _ALLOWED[
            _ARCHIVE
        ]

    def test_the_marker_is_scanned_and_allowed_no_non_stdlib_import(self) -> None:
        assert "fitdocs.compose" in _module_files(_package_dir())
        assert _ALLOWED["fitdocs.compose"] == frozenset()


class TestForbiddenNames:
    def test_no_scanned_module_imports_a_forbidden_name(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _forbidden_violations(_parse(path), name) == [], name

    def test_each_forbidden_form_is_detected(self) -> None:
        for source, expected in (
            ("import fitdocs.sync\n", ["fitdocs.sync"]),
            ("from fitdocs import render\n", ["fitdocs.render"]),
            ("from fitdocs.render.views import x\n", ["fitdocs.render.views"]),
            ("import yaml\n", ["yaml"]),
            ("from urllib import request\n", ["urllib.request"]),
            ("import socket\n", ["socket"]),
            ("import time\n", ["time"]),
            ("from time import sleep\n", ["time"]),
            ("import pathlib\n", ["pathlib"]),
            ("from fitdocs.layout import archive_path\n", ["fitdocs.layout"]),
            ("from fitdocs import ingest\n", ["fitdocs.ingest"]),
            ("import fitdocs.contract\n", ["fitdocs.contract"]),
        ):
            assert (
                _forbidden_violations(ast.parse(source), "fitdocs.compose.composer")
                == expected
            ), source

    def test_archive_alone_may_import_the_filesystem_and_adapter_modules(self) -> None:
        source = (
            "import pathlib\n"
            "from fitdocs.contract import sha_of_ref\n"
            "from fitdocs.layout import archive_path\n"
            "from fitdocs.ingest import parse_fit\n"
        )
        tree = ast.parse(source)
        assert _forbidden_violations(tree, _ARCHIVE) == []
        assert _forbidden_violations(tree, "fitdocs.compose.types") != []

    def test_archive_is_still_barred_from_the_hard_rule_packages(self) -> None:
        tree = ast.parse("import fitdocs.sync\n")
        assert _forbidden_violations(tree, _ARCHIVE) == ["fitdocs.sync"]


class TestClockNames:
    def test_no_scanned_module_names_a_clock(self) -> None:
        files = _module_files(_package_dir())
        assert files, "the walk is looking at the wrong directory"
        for name, path in files.items():
            assert _clock_offenders(path.read_text(encoding="utf-8")) == [], name

    def test_each_clock_form_is_detected(self) -> None:
        for source in (
            *(f"x = {spelling}()\n" for spelling in _CLOCK_SPELLINGS),
            '"""e.g. datetime.now(UTC)"""\n',
            '"""e.g. datetime.datetime.now(UTC)"""\n',
            "from time import time_ns\n",
            "from datetime import datetime\nx = datetime.now()\n",
            "x = clock.monotonic()\n",
            "x = sleep(1)\n",
        ):
            assert _clock_offenders(source), source

    def test_timestamp_and_timezone_are_not_clock_names(self) -> None:
        assert _clock_offenders("x = a.start_time.timestamp()\n") == []
        assert (
            _clock_offenders(
                "from datetime import datetime\nx = datetime.timezone.utc\n"
            )
            == []
        )

    def test_a_spelling_inside_a_longer_name_is_not_a_clock_name(self) -> None:
        assert _clock_offenders("x = runtime.time_stamp\n") == []
        assert _clock_offenders("x = clock.timestamp_of(y)\n") == []
        assert _clock_offenders("x = a_time.time_unit\n") == []
        assert _clock_offenders("x = time.timestamp\n") == []
        assert _clock_offenders("x = a_time.time\n") == []

    def test_an_injected_clock_parameter_is_not_a_clock_name(self) -> None:
        assert _clock_offenders("def f(clock):\n    return clock\n") == []


class TestPositiveControls:
    def test_the_scanned_modules_are_exactly_the_seven_allowlisted(self) -> None:
        files = _module_files(_package_dir())
        assert set(files) == set(_ALLOWED), sorted(set(files) ^ set(_ALLOWED))
        assert set(files) == set(_ALL_SEVEN)

    def test_the_walk_found_the_types_module(self) -> None:
        assert "fitdocs.compose.types" in _module_files(_package_dir())

    def test_a_module_without_an_allowlist_entry_is_detected(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "surprise.py").write_text("x = 1\n", encoding="utf-8")
        files = _module_files(tmp_path)
        assert files == {"fitdocs.compose.surprise": tmp_path / "surprise.py"}
        assert set(files) - set(_ALLOWED) == {"fitdocs.compose.surprise"}

    def test_an_empty_directory_finds_no_types_module(self, tmp_path: Path) -> None:
        assert "fitdocs.compose.types" not in _module_files(tmp_path)


_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_ADDRESS: Final[re.Pattern[str]] = re.compile(
    r"https?://[^ )]*" + "stryd", re.IGNORECASE
)
_FEATURE_FILES: Final[tuple[str, ...]] = (
    "src/fitdocs/compose/*.py",
    "src/fitdocs/render/provenance.py",
    "tests/compose/*.py",
    "tests/fixtures/merge.py",
    "tests/fixtures/test_merge_fixtures.py",
    "tests/render/test_provenance.py",
    "tests/test_compose_e2e.py",
    "tests/test_compose_passes_e2e.py",
    "docs/ownership-contract.md",
    "CHANGELOG.md",
    ".kiro/specs/channel-merge/*.md",
)


def _address_offenders(root: Path) -> tuple[list[str], int]:
    """Every feature file under ``root`` that names a Stryd web address, and
    how many files were scanned."""
    offenders: list[str] = []
    scanned = 0
    for pattern in _FEATURE_FILES:
        for path in sorted(root.glob(pattern)):
            scanned += 1
            if _ADDRESS.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(root).as_posix())
    return offenders, scanned


class TestNoServiceAddress:
    """Req 9.3: no Stryd web or service address in this feature's code, tests,
    specification or documentation."""

    def test_no_feature_file_names_one(self) -> None:
        offenders, scanned = _address_offenders(_REPO_ROOT)
        assert scanned >= 30, "the walk is looking at the wrong directory"
        assert offenders == []

    def test_an_address_in_any_scanned_file_is_detected(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "fitdocs" / "compose"
        target.mkdir(parents=True)
        (target / "types.py").write_text(
            "see https://www." + "stryd" + ".com/x\n", encoding="utf-8"
        )
        (target / "clean.py").write_text("x = 1\n", encoding="utf-8")
        offenders, scanned = _address_offenders(tmp_path)
        assert (offenders, scanned) == (["src/fitdocs/compose/types.py"], 2)
