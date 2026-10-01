"""The `fitdocs.connectors` package boundary: its direct import closure, the
forbidden-name scan, the tree-wide network allow-list, and the clock scan
(connectors spec, task 6.1; Req 1.9, 2.8, 14.2, 14.3). See the
"BoundaryGuard" component in `.kiro/specs/connectors/design.md` (~1502-1526)
and the "Allowed Dependencies" section (~103-120).

**Layer shape**, modelled on `tests/history/test_boundary.py` (import
closure / forbidden-name / clock-scan triad) but narrower per design.md's own
wording for this spec: design.md pins each module's *direct, non-stdlib*
imports only -- `fitdocs.*` targets and third-party top-level names, with
stdlib decided by `sys.stdlib_module_names` -- not the full closure
`tests/history/test_boundary.py` pins (which includes `__future__` and every
stdlib name too). `__future__` is itself a member of
`sys.stdlib_module_names`, so it is excluded here along with every other
stdlib import by the same rule, deliberately.

1. **Direct imports per module** (`TestImportClosure`) -- every module under
   `src/fitdocs/connectors/` parsed; its direct (not transitive) non-stdlib
   import targets pinned by equality against a hand-written literal per
   module (not derived from the source). `from fitdocs.connectors import
   registry` and `from fitdocs.connectors.errors import ConnectorError` both
   resolve to the real submodule they name (`fitdocs.connectors.registry`,
   `fitdocs.connectors.errors`) via `importlib.util.find_spec`, not to the
   bare parent package, so the equality pin names the actual module reached.
   `TestEnumerationIsComplete` checks the hand-maintained module list against
   the package directory in both directions.
2. **Forbidden names** (`TestForbiddenNames`) -- independent of the layer-1
   registry: no connectors module's direct imports contain any name listed
   under design.md's "Allowed Dependencies" as forbidden (by equality or
   dotted descent), nor any third-party top-level name other than `tomli_w`
   in the two modules design.md permits it in. Catches a forbidden name
   reached via `from <parent> import <forbidden-submodule>` too, not only a
   direct `import fitdocs.render.views`.
3. **Tree-wide network allow-list** (`TestNetworkAllowList`, Req 14.2) --
   every `*.py` module under `src/fitdocs/` (not only `connectors/`) is
   scanned for a direct import of `socket`, `ssl`, `http` (any submodule),
   `urllib.request`, `urllib.error`, `ftplib`, `smtplib` or `xmlrpc` (any
   submodule), in both the `import X` and the absolute `from X import y`
   forms (`from urllib import request` counts); relative imports are
   package-internal and skipped. Every offender must be one of the two
   modules design.md names network-capable (`fitdocs/tiles.py`,
   `fitdocs/connectors/http.py`). No
   tree-wide network allow-list test already exists elsewhere in the suite
   (`grep -rn "urllib.request\\|ftplib\\|smtplib\\|xmlrpc" tests/` found none
   scanning the whole tree), so this layer is new rather than an extension of
   an existing one.
4. **Clock scan** (`TestClockScan`, Req 14.3) -- over every module under
   `src/fitdocs/connectors/`, `_clock_offenders` combines a raw-text
   substring scan for the spellings in `_CLOCK_SPELLINGS` (so a spelling in
   a docstring or comment is caught too, as in the history guard) with an
   AST check for the aliasing forms a substring misses (`from time import
   ...`, an aliased `datetime`/`date`/`time` import).

The positive controls run the scans' own functions on synthetic sources:
the closure and forbidden-name rules on modules importing `fitdocs.render`
(through `_import_targets_of_tree`), the network scan on `import socket` and
on the absolute `from` forms, and the clock scan on every spelling and
aliasing form. The tree-wide scan must also find both allowed
network-capable modules and walk more than a hundred files. Negative
controls keep relative imports and the injected clock (`now()`) clean.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Final

import fitdocs
import fitdocs.connectors

# --------------------------------------------------------------------------- #
# Module discovery and enumeration completeness
# --------------------------------------------------------------------------- #

#: Every module this boundary owns, hand-maintained -- and checked against
#: the package directory in both directions by `TestEnumerationIsComplete`
#: below, so a new file dropped under the package is never invisible to this
#: module.
CONNECTORS_MODULE_NAMES: Final[tuple[str, ...]] = (
    "fitdocs.connectors",
    "fitdocs.connectors._atomic",
    "fitdocs.connectors.connect",
    "fitdocs.connectors.credentials",
    "fitdocs.connectors.delivery",
    "fitdocs.connectors.errors",
    "fitdocs.connectors.folder",
    "fitdocs.connectors.http",
    "fitdocs.connectors.ledger",
    "fitdocs.connectors.protocol",
    "fitdocs.connectors.pull",
    "fitdocs.connectors.registry",
    "fitdocs.connectors.secrets",
    "fitdocs.connectors.settings",
)


def _connectors_package_dir() -> Path:
    path = fitdocs.connectors.__file__
    assert path is not None, "fitdocs.connectors has no __file__"
    return Path(path).parent


def _connectors_module_names_on_disk() -> frozenset[str]:
    """Every `*.py` file anywhere under the connectors package, as its
    dotted module name -- the ground truth `CONNECTORS_MODULE_NAMES` is
    checked against, in both directions."""
    root = _connectors_package_dir()
    names: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.name == "__init__.py":
            parts = rel.parts[:-1]
            dotted = "fitdocs.connectors" + ("." + ".".join(parts) if parts else "")
        else:
            parts = rel.with_suffix("").parts
            dotted = "fitdocs.connectors." + ".".join(parts)
        names.add(dotted)
    return frozenset(names)


class TestEnumerationIsComplete:
    def test_registered_names_equal_the_directory_listing(self) -> None:
        on_disk = _connectors_module_names_on_disk()
        assert set(CONNECTORS_MODULE_NAMES) == on_disk, (
            f"registered but missing on disk: "
            f"{set(CONNECTORS_MODULE_NAMES) - on_disk}; "
            f"on disk but not registered: "
            f"{on_disk - set(CONNECTORS_MODULE_NAMES)}"
        )

    def test_the_walk_is_looking_at_the_right_directory(self) -> None:
        on_disk = _connectors_module_names_on_disk()
        assert len(on_disk) >= 10, (
            "the walk found too few modules -- it is looking at the wrong "
            f"directory (found {sorted(on_disk)})"
        )


# --------------------------------------------------------------------------- #
# Direct import resolution
# --------------------------------------------------------------------------- #


def _module_path(module_name: str) -> Path:
    if module_name == "fitdocs.connectors":
        return _connectors_package_dir() / "__init__.py"
    leaf = module_name.rsplit(".", 1)[-1]
    return _connectors_package_dir() / f"{leaf}.py"


def _module_source(module_name: str) -> str:
    return _module_path(module_name).read_text(encoding="utf-8")


def _module_ast(module_name: str) -> ast.Module:
    return ast.parse(
        _module_source(module_name), filename=str(_module_path(module_name))
    )


def _enclosing_package(module_name: str) -> str:
    """The package a relative import in `module_name` resolves against: a
    package's own `__init__.py` resolves a relative import against itself;
    every other (leaf) module resolves against its parent package."""
    if module_name == "fitdocs.connectors":
        return module_name
    return module_name.rsplit(".", 1)[0]


def _is_importable_module(dotted: str) -> bool:
    """Whether `dotted` names a real, importable module (as opposed to a
    plain attribute -- a class, function, or constant -- defined inside its
    parent)."""
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _resolve_import_from(node: ast.ImportFrom, enclosing_package: str) -> str | None:
    """The full dotted target(s) a `from ... import ...` statement reaches.

    `from fitdocs import inbox as inbox_module` resolves the bare `fitdocs`
    base to `fitdocs.inbox`, the real grant. `from fitdocs.connectors import
    registry` resolves its base `fitdocs.connectors` further, per alias, to
    `fitdocs.connectors.registry` when that name is itself a real submodule
    (checked via `importlib.util.find_spec`, not assumed) -- so a module that
    imports a *submodule* by name is pinned at that submodule, while
    `from fitdocs.connectors.errors import (ConnectorError, ...)` -- whose
    base is already the leaf module `fitdocs.connectors.errors` and whose
    names (`ConnectorError`, ...) are not themselves submodules -- resolves
    to the single target `fitdocs.connectors.errors`, not one target per
    imported name.
    """
    if node.level == 0:
        base = node.module
    else:
        dots = "." * node.level
        name = dots + (node.module or "")
        try:
            base = importlib.util.resolve_name(name, enclosing_package)
        except ImportError:
            return None
    if base is None:
        return None
    if base == "fitdocs":
        # Represented by the caller as one target per alias; signal via the
        # sentinel prefix consumed in `_import_targets`.
        return "fitdocs::" + ",".join(alias.name for alias in node.names)
    expanded: set[str] = set()
    any_submodule = False
    for alias in node.names:
        candidate = f"{base}.{alias.name}"
        if _is_importable_module(candidate):
            expanded.add(candidate)
            any_submodule = True
    if any_submodule:
        return "multi::" + ",".join(sorted(expanded))
    return base


def _import_targets(module_name: str) -> frozenset[str]:
    """Every distinct dotted target `module_name` directly imports, resolved
    (`import X` and `import X as Y` both resolve to `X`)."""
    return _import_targets_of_tree(_module_ast(module_name), module_name)


def _import_targets_of_tree(tree: ast.Module, module_name: str) -> frozenset[str]:
    enclosing = _enclosing_package(module_name)
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_from(node, enclosing)
            if resolved is None:
                continue
            if resolved.startswith("fitdocs::"):
                for name in resolved[len("fitdocs::") :].split(","):
                    targets.add(f"fitdocs.{name}")
            elif resolved.startswith("multi::"):
                for name in resolved[len("multi::") :].split(","):
                    targets.add(name)
            else:
                targets.add(resolved)
    return frozenset(targets)


def _is_stdlib(target: str) -> bool:
    top = target.split(".", 1)[0]
    return top in sys.stdlib_module_names


def _non_stdlib_import_targets(module_name: str) -> frozenset[str]:
    """`_import_targets`, filtered to the non-stdlib targets design.md's
    layer 1 pins: `fitdocs.*` dotted targets and third-party top-level
    names, stdlib decided by `sys.stdlib_module_names`."""
    return frozenset(t for t in _import_targets(module_name) if not _is_stdlib(t))


# --------------------------------------------------------------------------- #
# Layer 1: direct, non-stdlib imports per module, pinned by equality
# --------------------------------------------------------------------------- #

#: Every module's exact, measured set of *non-stdlib* direct import targets
#: (design.md "Allowed Dependencies") -- an equality pin, not a membership
#: check: a non-stdlib import added to a module without updating its entry
#: here fails, and a stale entry for a removed import fails too.
#: `tomli_w` appears only in `ledger.py`'s and `credentials.py`'s sets, per
#: design.md.
_ALLOWED_IMPORT_TARGETS: Final[dict[str, frozenset[str]]] = {
    "fitdocs.connectors": frozenset(
        {
            "fitdocs.connectors.errors",
            "fitdocs.connectors.folder",
            "fitdocs.connectors.http",
            "fitdocs.connectors.protocol",
            "fitdocs.connectors.registry",
            "fitdocs.connectors.secrets",
        }
    ),
    "fitdocs.connectors._atomic": frozenset(),
    "fitdocs.connectors.connect": frozenset(
        {
            "fitdocs.connectors.credentials",
            "fitdocs.connectors.errors",
            "fitdocs.connectors.http",
            "fitdocs.connectors.protocol",
            "fitdocs.connectors.secrets",
            "fitdocs.connectors.settings",
        }
    ),
    "fitdocs.connectors.credentials": frozenset(
        {
            "tomli_w",
            "fitdocs.connectors._atomic",
            "fitdocs.connectors.errors",
            "fitdocs.connectors.protocol",
            "fitdocs.connectors.secrets",
            "fitdocs.settings",
        }
    ),
    "fitdocs.connectors.delivery": frozenset(
        {
            "fitdocs.layout",
            "fitdocs.connectors._atomic",
            "fitdocs.connectors.ledger",
            "fitdocs.connectors.protocol",
        }
    ),
    "fitdocs.connectors.errors": frozenset(),
    "fitdocs.connectors.folder": frozenset(
        {
            "fitdocs.inbox",
            "fitdocs.connectors.errors",
            "fitdocs.connectors.protocol",
        }
    ),
    "fitdocs.connectors.http": frozenset(
        {
            "fitdocs.connectors.errors",
            "fitdocs.connectors.secrets",
            "fitdocs.version",
        }
    ),
    "fitdocs.connectors.ledger": frozenset(
        {
            "tomli_w",
            "fitdocs.connectors._atomic",
            "fitdocs.layout",
        }
    ),
    "fitdocs.connectors.protocol": frozenset(
        {
            "fitdocs.connectors.http",
            "fitdocs.connectors.secrets",
        }
    ),
    "fitdocs.connectors.pull": frozenset(
        {
            "fitdocs.layout",
            "fitdocs.connectors.credentials",
            "fitdocs.connectors.delivery",
            "fitdocs.connectors.errors",
            "fitdocs.connectors.http",
            "fitdocs.connectors.ledger",
            "fitdocs.connectors.protocol",
            "fitdocs.connectors.secrets",
            "fitdocs.connectors.settings",
        }
    ),
    "fitdocs.connectors.registry": frozenset(
        {
            "fitdocs.connectors.protocol",
        }
    ),
    "fitdocs.connectors.secrets": frozenset(),
    "fitdocs.connectors.settings": frozenset(
        {
            "fitdocs.connectors.registry",
            "fitdocs.connectors.credentials",
            "fitdocs.connectors.errors",
            "fitdocs.connectors.protocol",
            "fitdocs.settings",
        }
    ),
}


class TestImportClosure:
    def test_registry_covers_exactly_the_enumerated_modules(self) -> None:
        assert set(_ALLOWED_IMPORT_TARGETS) == set(CONNECTORS_MODULE_NAMES)

    def test_every_module_imports_exactly_its_allowed_non_stdlib_targets(
        self,
    ) -> None:
        scanned = 0
        for module_name in CONNECTORS_MODULE_NAMES:
            scanned += 1
            measured = _non_stdlib_import_targets(module_name)
            allowed = _ALLOWED_IMPORT_TARGETS[module_name]
            assert measured == allowed, (
                f"{module_name}: measured non-stdlib imports "
                f"{sorted(measured)} do not equal the pinned allowed set "
                f"{sorted(allowed)} -- unexpected: "
                f"{sorted(measured - allowed)}; missing (pinned but no "
                f"longer imported): {sorted(allowed - measured)}"
            )
        assert scanned == len(CONNECTORS_MODULE_NAMES), (
            "the walk is looking at the wrong set"
        )

    def test_tomli_w_appears_only_in_ledger_and_credentials(self) -> None:
        users = {
            name
            for name, targets in _ALLOWED_IMPORT_TARGETS.items()
            if "tomli_w" in targets
        }
        assert users == {
            "fitdocs.connectors.ledger",
            "fitdocs.connectors.credentials",
        }


# --------------------------------------------------------------------------- #
# Layer 2: forbidden-name scan, independent of the layer-1 registry
# --------------------------------------------------------------------------- #

#: design.md "Allowed Dependencies": forbidden to the package.
_FORBIDDEN_TARGETS: Final[tuple[str, ...]] = (
    "fitdocs.render",
    "fitdocs.load",
    "fitdocs.metrics",
    "fitdocs.ingest",
    "fitdocs.sync",
    "fitdocs.audit",
    "fitdocs.plans",
    "fitdocs.history",
    "fitdocs.performance",
    "fitdocs.contract",
    "fitdocs.docio",
    "fitdocs.docmerge",
    "fitdocs.tiles",
    "fitdocs.plugins",
    "fitdocs.cli",
)

#: Third-party top-level names permitted, and the one module each is
#: permitted in.
_THIRD_PARTY_ALLOWED_MODULES: Final[dict[str, frozenset[str]]] = {
    "tomli_w": frozenset(
        {"fitdocs.connectors.ledger", "fitdocs.connectors.credentials"}
    ),
}


def _matches_forbidden(target: str) -> str | None:
    for forbidden in _FORBIDDEN_TARGETS:
        if target == forbidden or target.startswith(f"{forbidden}."):
            return forbidden
    return None


def _is_stdlib_top(target: str) -> bool:
    return target.split(".", 1)[0] in sys.stdlib_module_names


class TestForbiddenNames:
    def test_no_module_directly_imports_a_forbidden_fitdocs_target(self) -> None:
        scanned = 0
        violations: list[str] = []
        for module_name in CONNECTORS_MODULE_NAMES:
            scanned += 1
            for target in _import_targets(module_name):
                forbidden = _matches_forbidden(target)
                if forbidden is not None:
                    violations.append(f"{module_name} imports {target!r}")
        assert scanned == len(CONNECTORS_MODULE_NAMES), (
            "the walk is looking at the wrong set"
        )
        assert not violations, "\n".join(violations)

    def test_no_third_party_name_other_than_tomli_w_in_its_two_modules(
        self,
    ) -> None:
        scanned = 0
        violations: list[str] = []
        for module_name in CONNECTORS_MODULE_NAMES:
            scanned += 1
            for target in _import_targets(module_name):
                if _is_stdlib_top(target) or target.startswith("fitdocs"):
                    continue
                # Non-stdlib, non-fitdocs: third party.
                top = target.split(".", 1)[0]
                if top != "tomli_w":
                    violations.append(f"{module_name} imports {target!r}")
                elif module_name not in _THIRD_PARTY_ALLOWED_MODULES["tomli_w"]:
                    violations.append(
                        f"{module_name} imports {target!r} outside its allowed modules"
                    )
        assert scanned == len(CONNECTORS_MODULE_NAMES)
        assert not violations, "\n".join(violations)

    def test_positive_control_synthetic_module_importing_render_is_caught(
        self,
    ) -> None:
        for source in (
            "import fitdocs.render\n",
            "from fitdocs import render\n",
            "from .. import render\n",
        ):
            targets = _import_targets_of_tree(
                ast.parse(source), "fitdocs.connectors.pull"
            )
            assert targets == {"fitdocs.render"}, source
            assert _matches_forbidden("fitdocs.render") == "fitdocs.render"
            non_stdlib = frozenset(t for t in targets if not _is_stdlib(t))
            assert non_stdlib != _ALLOWED_IMPORT_TARGETS["fitdocs.connectors.pull"]


# --------------------------------------------------------------------------- #
# Layer 3: tree-wide network allow-list (Req 14.2)
# --------------------------------------------------------------------------- #

#: The only two modules in `src/fitdocs/` permitted to import a
#: network-capable name (design.md "Allowed Dependencies" and the
#: BoundaryGuard layer-3 description).
_NETWORK_ALLOWED_PATHS: Final[frozenset[str]] = frozenset(
    {"fitdocs/tiles.py", "fitdocs/connectors/http.py"}
)

#: Network-capable stdlib names scanned for, tree-wide.
_NETWORK_FORBIDDEN_PREFIXES: Final[tuple[str, ...]] = (
    "socket",
    "ssl",
    "http",
    "urllib.request",
    "urllib.error",
    "ftplib",
    "smtplib",
    "xmlrpc",
)


def _src_root() -> Path:
    path = fitdocs.__file__
    assert path is not None, "fitdocs has no __file__"
    return Path(path).parent


def _relpath_under_src(path: Path, root: Path) -> str:
    return "fitdocs/" + str(path.relative_to(root)).replace("\\", "/")


def _source_imports_network(source: str) -> bool:
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # `from urllib import request` reaches `urllib.request`; a relative
            # import (`from .http import X`) is package-internal, never stdlib.
            names.append(node.module)
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return any(
        name == p or name.startswith(p + ".")
        for name in names
        for p in _NETWORK_FORBIDDEN_PREFIXES
    )


def _module_imports_network(path: Path) -> bool:
    return _source_imports_network(path.read_text(encoding="utf-8"))


class TestNetworkAllowList:
    def test_every_module_importing_network_is_on_the_allow_list(self) -> None:
        root = _src_root()
        scanned = 0
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            scanned += 1
            rel = _relpath_under_src(path, root)
            if _module_imports_network(path) and rel not in _NETWORK_ALLOWED_PATHS:
                offenders.append(rel)
        assert scanned > 100, (
            f"the tree-wide walk found too few files ({scanned}) -- it is "
            "looking at the wrong directory"
        )
        assert not offenders, (
            f"modules importing a network-capable name outside the "
            f"allow-list: {offenders}"
        )

    def test_positive_control_both_allowed_modules_are_found_on_disk(
        self,
    ) -> None:
        root = _src_root()
        found = {
            _relpath_under_src(path, root)
            for path in root.rglob("*.py")
            if _module_imports_network(path)
        }
        assert found >= _NETWORK_ALLOWED_PATHS

    def test_positive_control_synthetic_module_importing_socket_is_caught(
        self, tmp_path: Path
    ) -> None:
        synthetic = tmp_path / "synthetic_network_module.py"
        synthetic.write_text("import socket\n", encoding="utf-8")
        assert _module_imports_network(synthetic) is True

    def test_positive_control_from_import_forms_are_caught(self) -> None:
        for source in (
            "from urllib import request\n",
            "from urllib.request import urlopen\n",
            "from http import client\n",
            "from urllib import parse, error\n",
        ):
            assert _source_imports_network(source) is True, source

    def test_negative_control_non_network_and_relative_forms_are_clean(self) -> None:
        for source in (
            "from urllib.parse import urlsplit\n",
            "from urllib import parse\n",
            "from .http import HttpClient\n",
            "from . import http\n",
        ):
            assert _source_imports_network(source) is False, source

    def test_negative_control_synthetic_module_without_network_is_clean(
        self, tmp_path: Path
    ) -> None:
        synthetic = tmp_path / "synthetic_clean_module.py"
        synthetic.write_text("import os\nimport pathlib\n", encoding="utf-8")
        assert _module_imports_network(synthetic) is False


# --------------------------------------------------------------------------- #
# Layer 4: clock scan (Req 14.3)
# --------------------------------------------------------------------------- #

#: Literal spellings scanned for, raw-text (not only AST), so a docstring
#: example is caught too, not only live code.
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


def _clock_offenders(source: str) -> list[str]:
    """Raw-text clock spellings, plus the two AST forms that defeat a
    qualified-spelling scan: an aliased `datetime`/`date`/`time` import
    (`from datetime import datetime as dt`) and a bare `from time import`."""
    found = [s for s in _CLOCK_SPELLINGS if s in source]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == "time":
            found.append("from time import ...")
        elif isinstance(node, ast.ImportFrom) and node.module == "datetime":
            found.extend(
                f"datetime.{a.name} as {a.asname}"
                for a in node.names
                if a.asname and a.name in {"datetime", "date"}
            )
        elif isinstance(node, ast.Import):
            found.extend(
                f"import {a.name} as {a.asname}"
                for a in node.names
                if a.asname and a.name in {"datetime", "time"}
            )
    return found


def _connectors_module_paths() -> tuple[Path, ...]:
    root = _connectors_package_dir()
    return tuple(sorted(root.rglob("*.py")))


class TestClockScan:
    def test_package_has_no_clock_spelling(self) -> None:
        paths = _connectors_module_paths()
        assert len(paths) >= 10, (
            f"the walk found too few files ({len(paths)}) -- wrong directory"
        )
        offenders: list[str] = []
        for path in paths:
            for hit in _clock_offenders(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.name}: {hit!r}")
        assert not offenders, "\n".join(offenders)

    def test_positive_control_each_clock_form_is_detected(self) -> None:
        for source in (
            *(f"x = {spelling}()\n" for spelling in _CLOCK_SPELLINGS),
            '"""e.g. datetime.now(UTC)"""\n',
            "from time import time\n",
            "from datetime import datetime as dt\n",
            "import time as t\n",
        ):
            assert _clock_offenders(source), source

    def test_negative_control_injected_clock_is_clean(self) -> None:
        assert not _clock_offenders(
            "from datetime import datetime\n"
            "def f(now):\n    return session.now() if now() else None\n"
        )
