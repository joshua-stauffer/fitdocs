"""The `fitdocs.identity` package boundary (activity-identity, task 7.1;
Req 1.1, 3.10, 9.2).

**Threat model.** These guards defend against *accidental* boundary drift in
ordinary code: someone imports `fitdocs.sync`, opens a file in `roles.py`,
calls a page-reading helper from `matching.py`, reads the clock, or reaches
the contract from a module that should not. They do not defend against
adversarial code. Out of scope, by declaration:

- an imported object copied to a new name before use (`x = pathlib` then
  `x.os.listdir(...)`): attribute chains are resolved only from names bound
  directly by an import statement;
- modules reached from a non-import root (a function argument, a return value);
- a contract *constant* re-exported by another `fitdocs` layer
  (`from fitdocs.layout import SESSION_UUID_FIELD`): a str or int has no
  defining module to resolve, so only re-exported classes and functions are
  seen through `__module__`. Follow-up, not pinned here;
- growth of `pathlib.Path` in a later Python version: `_FS_ATTRIBUTES` is
  derived at import time from the running interpreter, so a method added
  after this file was last run is covered only when it runs there.

**Sweep criterion.** Pins read off the parsed source of every module under
`src/fitdocs/identity/`, plus the objects its imports resolve to at test time.

1. *Imports (an allowlist, one rule for every route).* Every `import` /
   `from ... import` anywhere in the tree (function bodies included, relative
   imports resolved against the module's package) yields dotted targets,
   `from x import y` also yielding `x.y`; a bare `import fitdocs` is a
   violation. A target is allowed only if it is:
   - under `fitdocs.model`, `fitdocs.layout` or `fitdocs.identity` (`layout`
     and `model` were read for I/O: they build paths, strings and values and
     open nothing), except that
   - `fitdocs.docio`, `fitdocs.identity.pages` and `fitdocs.identity.holds`
     (the modules that read or write files) are allowed in `pages` and
     `holds` only;
   - `fitdocs.settings` is allowed only as the explicit per-name allowlist
     `_SETTINGS_NAMES` (`SettingsError`, in `identity/settings.py` only),
     because `load_settings_document` opens the settings file;
   - `fitdocs.contract` in `kinds` and `pages` only;
   - `tomli_w` in `holds` only;
   - under a standard-library name on that module's allowlist
     (`_STDLIB_BASE`, plus `os`, `tempfile`, `tomllib` for `holds`).
   Every other target, standard library or not, is a violation by omission;
   the forbidden layers are also named so the message says why.
2. *Objects, not names (the same rule).* For every accepted `from X import y`,
   `y` is resolved on the real module: a module is checked by its `__name__`,
   and a class or function defined in a `fitdocs` module is checked as
   `<__module__>.<__name__>` (so a contract name imported through `docio` is
   a contract import, and a helper re-exported by `layout` is seen as the
   module that defines it). For every attribute chain rooted at an import-bound
   name, each step is resolved on the real object and every module or defined
   object met is checked the same way, stopping at the first object that is
   neither a module nor defined in `fitdocs` (`pathlib.os.listdir`,
   `typing.sys.modules`, `s.load_settings_document` for `import
   fitdocs.settings as s`).
3. *Dynamic access, flagged wherever named:* `exec`, `eval`, `compile`,
   `__import__`, `globals`, `vars`, `__builtins__`, `getattr`, `setattr`,
   `delattr`, and any dunder attribute other than `__name__` and
   `__getitem__` (the only two identity code reads).
4. *Attribute reach.* A `fitdocs.<...>` attribute chain is put through the
   rule of (1) too (`import fitdocs.model` then `fitdocs.sync.x()`, or
   `fitdocs.contract.X` outside `kinds` and `pages`); a `fitdocs.contract`
   chain counts as importing the contract.
5. *Filesystem.* A module touches the filesystem if it names the builtin
   `open`, an attribute in `_FS_ATTRIBUTES`, or imports `os`, `tempfile` or
   `tomllib` (as a statement or as a resolved object). `_FS_ATTRIBUTES` is
   derived: the public names `pathlib.Path` has and `pathlib.PurePath` lacks.
   Only `pages` and `holds` may touch; (1) keeps every other module away from
   the helpers that do. The derived set includes `.replace`, `.resolve` and
   `.exists` on any receiver, a fail-closed false-positive surface; the
   current modules hit it once, `decision.group` in `planning`, exempted as
   exactly that chain in exactly that module.
6. *Clock.* The attribute names `now`, `utcnow` and `today`, on any receiver.
   `time` and `timeit` are not on any allowlist, so importing them is a
   violation of (1). `datetime.fromtimestamp` converts a supplied value and
   reads no clock, and `from datetime import time` names a class; neither is
   flagged.

This file pins what identity modules import, never who imports identity.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import types
from pathlib import Path
from typing import Final

import pytest

import fitdocs.identity

_PACKAGE = "fitdocs.identity"

#: Every module the package holds, hand-maintained and checked against the
#: directory in both directions.
_MODULES: Final[tuple[str, ...]] = (
    "fitdocs.identity",
    "fitdocs.identity.holds",
    "fitdocs.identity.kinds",
    "fitdocs.identity.matching",
    "fitdocs.identity.pages",
    "fitdocs.identity.planning",
    "fitdocs.identity.roles",
    "fitdocs.identity.settings",
)

_FILESYSTEM_MODULES: Final[frozenset[str]] = frozenset(
    {"fitdocs.identity.pages", "fitdocs.identity.holds"}
)
_CONTRACT_MODULES: Final[frozenset[str]] = frozenset(
    {"fitdocs.identity.kinds", "fitdocs.identity.pages"}
)

#: Named so a violation says why; the allowlist below is what closes the rule.
_FORBIDDEN: Final[tuple[str, ...]] = (
    "fitdocs.sync",
    "fitdocs.render",
    "fitdocs.audit",
    "fitdocs.cli",
    "fitdocs.ingest",
    "fitdocs.metrics",
    "fitdocs.load",
    "fitdocs.history",
    "fitdocs.plans",
    "fitdocs.tiles",
    "fitdocs.inbox",
    "yaml",
    "urllib",
    "socket",
)

#: `fitdocs` layers any identity module may use. `fitdocs.layout` and
#: `fitdocs.model` were read for I/O: both only build paths, strings and
#: values (no `open`, no `Path` read/write/list/test), so they are allowed
#: whole. `docio`, `settings`, `identity.pages` and `identity.holds` are
#: gated separately below.
_LAYERS: Final[frozenset[str]] = frozenset({"model", "layout", "identity"})
#: Modules that read or write files (`docio.read_frontmatter` opens a page,
#: `pages` scans the workouts directory, `holds` reads and writes
#: `held.toml`): importable, by module, name or reached object, only by the
#: filesystem modules themselves.
_FS_HELPERS: Final[tuple[str, ...]] = (
    "fitdocs.docio",
    "fitdocs.identity.pages",
    "fitdocs.identity.holds",
)
#: `fitdocs.settings.load_settings_document` opens the settings file, so a
#: non-filesystem module may bind only the names it uses today.
_SETTINGS = "fitdocs.settings"
_SETTINGS_NAMES: Final[dict[str, frozenset[str]]] = {
    "fitdocs.identity.settings": frozenset({"SettingsError"}),
}
_CONTRACT = "fitdocs.contract"
_THIRD_PARTY: Final[dict[str, str]] = {"tomli_w": "fitdocs.identity.holds"}

#: The standard-library names any identity module may import (what the
#: current modules genuinely import: `collections` for planning's
#: `defaultdict`, `hashlib` for kinds, `pathlib` for the `Path` annotations).
_STDLIB_BASE: Final[frozenset[str]] = frozenset(
    {
        "__future__",
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "enum",
        "hashlib",
        "types",
        "typing",
        "pathlib",
    }
)
#: Per-module additions. holds reads and atomically writes `held.toml`.
_STDLIB_EXTRA: Final[dict[str, frozenset[str]]] = {
    "fitdocs.identity.holds": frozenset({"os", "tempfile", "tomllib"}),
}

_FS_IMPORTS: Final[tuple[str, ...]] = ("os", "tempfile", "tomllib")
#: Derived, not listed: every public name `Path` adds over `PurePath`
#: (Python-version dependent by construction; a new pathlib method is
#: covered the day it exists).
_FS_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    n
    for n in set(dir(pathlib.Path)) - set(dir(pathlib.PurePath))
    if not n.startswith("_")
)
#: The one derived name that is an ordinary field in identity code:
#: `planning` reads `decision.group`. Exempt exactly that chain, in that module.
_GROUP_FIELD_READ: Final[tuple[str, str]] = (
    "fitdocs.identity.planning",
    "decision.group",
)
_CLOCK_ATTRIBUTES: Final[frozenset[str]] = frozenset({"now", "utcnow", "today"})

_ESCAPE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "vars",
        "__builtins__",
        "getattr",
        "setattr",
        "delattr",
    }
)
#: The only dunder attributes identity code reads (`type(x).__name__`,
#: `_STRENGTH.__getitem__`).
_DUNDER_ATTRIBUTES_ALLOWED: Final[frozenset[str]] = frozenset(
    {"__name__", "__getitem__"}
)


# --------------------------------------------------------------------------- #
# Scanners: pure functions of (module name, source text)
# --------------------------------------------------------------------------- #


def _package_of(module: str) -> str:
    """The package a relative import in `module` resolves against: the
    package itself for the package marker, the parent for every other module."""
    return module if module == _PACKAGE else module.rsplit(".", 1)[0]


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _import_targets(module: str, source: str) -> set[str]:
    """Every dotted target `source` imports, in every form, anywhere in the
    tree (function bodies included)."""
    targets: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base: str | None = node.module
            else:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), _package_of(module)
                    )
                except ImportError:
                    base = None
            if base is None:
                targets.add(f"<unresolvable relative import: {ast.unparse(node)}>")
                continue
            if base != "fitdocs":
                targets.add(base)
            targets.update(f"{base}.{a.name}" for a in node.names if a.name != "*")
    return targets


def _attribute_chains(source: str) -> set[str]:
    chains: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            chain = _dotted(node)
            if chain is not None:
                chains.add(chain)
    return chains


def _under(target: str, prefix: str) -> bool:
    return target == prefix or target.startswith(prefix + ".")


def _escape_hatches(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in _ESCAPE_NAMES:
            found.append(f"names {node.id}")
        elif isinstance(node, ast.Attribute) and (
            node.attr in _ESCAPE_NAMES
            or (
                node.attr.startswith("__")
                and node.attr.endswith("__")
                and node.attr not in _DUNDER_ATTRIBUTES_ALLOWED
            )
        ):
            found.append(f"names .{node.attr}")
    return found


def _classify(module: str, target: str) -> str | None:
    """The one import rule: why `module` may not depend on the dotted module
    `target`, or None if it may."""
    stdlib = _STDLIB_BASE | _STDLIB_EXTRA.get(module, frozenset())
    top = target.split(".")[0]
    if target.startswith("<unresolvable"):
        return f"{target}: cannot be resolved to a target"
    if any(_under(target, f) for f in _FORBIDDEN):
        return f"{target}: forbidden"
    if any(_under(target, h) for h in _FS_HELPERS):
        if module in _FILESYSTEM_MODULES:
            return None
        return f"{target}: a filesystem helper, importable by pages and holds only"
    if _under(target, _SETTINGS):
        names = _SETTINGS_NAMES.get(module)
        if names is not None and (
            target == _SETTINGS
            or target.split(".")[2:3]
            and target.split(".")[2] in names
        ):
            return None
        return f"{target}: not one of the fitdocs.settings names this module may use"
    if _under(target, _CONTRACT):
        if module in _CONTRACT_MODULES:
            return None
        return f"{target}: only kinds and pages import the contract"
    if target.startswith("fitdocs.") and target.split(".")[1] in _LAYERS:
        return None
    if top in _THIRD_PARTY:
        if module == _THIRD_PARTY[top]:
            return None
        return f"{target}: third party outside its one module"
    if any(_under(target, s) for s in stdlib):
        return None
    return f"{target}: not an allowed import"


def _bindings(module: str, source: str) -> dict[str, list[object]]:
    """Objects the names bound by imports refer to, resolved at test time.

    Only imports the rule accepts are imported here (a forbidden one is
    already a violation and is never loaded); `import a.b.c` binds the root
    package `a`, `import a.b as x` binds `a.b`, `from fitdocs import y` binds
    the submodule `fitdocs.y`, and any other `from x import y` binds
    `getattr(x, y)`.
    """
    bound: dict[str, list[object]] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _classify(module, alias.name) is not None:
                    continue
                if alias.asname:
                    obj = importlib.import_module(alias.name)
                    bound.setdefault(alias.asname, []).append(obj)
                else:
                    root = alias.name.split(".")[0]
                    bound.setdefault(root, []).append(importlib.import_module(root))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    base: str | None = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), _package_of(module)
                    )
                except ImportError:
                    base = None
            else:
                base = node.module
            if base == "fitdocs":
                # `from fitdocs import settings as s` binds the submodule
                # `fitdocs.settings` (relative forms resolve to this base too).
                for alias in node.names:
                    if alias.name != "*" and not _classify(
                        module, f"fitdocs.{alias.name}"
                    ):
                        bound.setdefault(alias.asname or alias.name, []).append(
                            importlib.import_module(f"fitdocs.{alias.name}")
                        )
                continue
            if base is None or _classify(module, base):
                continue
            owner = importlib.import_module(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                member = getattr(owner, alias.name, None)
                if member is not None:
                    bound.setdefault(alias.asname or alias.name, []).append(member)
    return bound


def _defining_name(obj: object) -> set[str]:
    """`<defining module>.<name>` of a class or function defined in a
    `fitdocs` module (an object reached through `__module__` counts as the
    module it was defined in, name included)."""
    origin = getattr(obj, "__module__", None)
    name = getattr(obj, "__name__", None)
    if isinstance(origin, str) and origin.startswith("fitdocs."):
        return {f"{origin}.{name}" if isinstance(name, str) else origin}
    return set()


def _step(current: object, step: str) -> object:
    """One attribute step on a real object. A step below a `fitdocs` package
    is resolved by importing the dotted submodule first, so the result does
    not depend on which submodules happen to be imported already."""
    name = getattr(current, "__name__", "")
    if (
        isinstance(current, types.ModuleType)
        and hasattr(current, "__path__")
        and name.startswith("fitdocs")
    ):
        try:
            return importlib.import_module(f"{name}.{step}")
        except ImportError:
            pass
    return getattr(current, step, None)


def _object_targets(module: str, source: str) -> set[str]:
    """Names the source reaches through objects rather than through import
    statements: a module bound by an import (`from X import y`, `from fitdocs
    import y`), each module met while following an attribute chain from an
    import-bound name (every step resolved on the real object), and, for the
    first object that is not a module, `<__module__>.<__name__>` when it is
    defined in a `fitdocs` module. A chain stops at that first non-module."""
    found: set[str] = set()
    bound = _bindings(module, source)
    for objs in bound.values():
        for obj in objs:
            if isinstance(obj, types.ModuleType):
                # `import fitdocs.model` binds the root package; a bare
                # `import fitdocs` is a violation of its own (import targets).
                if obj.__name__ != "fitdocs":
                    found.add(obj.__name__)
            else:
                found.update(_defining_name(obj))
    for chain in _attribute_chains(source):
        root, *steps = chain.split(".")
        for start in bound.get(root, []):
            current: object = start
            for step in steps:
                current = _step(current, step)
                if not isinstance(current, types.ModuleType):
                    found.update(_defining_name(current))
                    break
                found.add(current.__name__)
    return found


def _closure_violations(module: str, source: str) -> list[str]:
    found: list[str] = []
    for target in sorted(_import_targets(module, source)):
        why = _classify(module, target)
        if why:
            found.append(why)
    for target in sorted(_object_targets(module, source)):
        why = _classify(module, target)
        if why:
            found.append(f"{why} (reached as an object)")
    for chain in sorted(_attribute_chains(source)):
        if chain.startswith("fitdocs."):
            why = _classify(module, chain)
            if why:
                found.append(f"{why} (reached by attribute)")
    found.extend(f"{h}: dynamic escape hatch" for h in _escape_hatches(source))
    return found


def _contract_imports(module: str, source: str) -> bool:
    return (
        any(_under(t, _CONTRACT) for t in _import_targets(module, source))
        or any(_under(t, _CONTRACT) for t in _object_targets(module, source))
        or any(_under(c, _CONTRACT) for c in _attribute_chains(source))
    )


def _filesystem_touches(module: str, source: str) -> list[str]:
    found = [
        f"imports {t}"
        for t in sorted(
            _import_targets(module, source) | _object_targets(module, source)
        )
        if any(_under(t, m) for m in _FS_IMPORTS)
    ]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == "open":
            found.append("names open")
        elif isinstance(node, ast.Attribute) and node.attr in _FS_ATTRIBUTES:
            if (module, _dotted(node)) == _GROUP_FIELD_READ:
                continue
            found.append(f"names .{node.attr}")
    return found


def _clock_names(module: str, source: str) -> list[str]:
    return [
        f"names .{node.attr}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr in _CLOCK_ATTRIBUTES
    ]


# --------------------------------------------------------------------------- #
# The real tree
# --------------------------------------------------------------------------- #


def _package_dir() -> Path:
    path = fitdocs.identity.__file__
    assert path is not None
    return Path(path).parent


def _path_of(module: str) -> Path:
    if module == _PACKAGE:
        return _package_dir() / "__init__.py"
    return _package_dir() / f"{module.rsplit('.', 1)[1]}.py"


def _source_of(module: str) -> str:
    return _path_of(module).read_text(encoding="utf-8")


def _on_disk() -> frozenset[str]:
    names: set[str] = set()
    for path in _package_dir().rglob("*.py"):
        rel = path.relative_to(_package_dir())
        if rel.name == "__init__.py":
            names.add(".".join((_PACKAGE, *rel.parts[:-1])))
        else:
            names.add(".".join((_PACKAGE, *rel.with_suffix("").parts)))
    return frozenset(names)


class TestEnumeration:
    """The positive control: the walk sees the directory it is meant to."""

    def test_the_package_directory_is_the_source_tree_one(self) -> None:
        assert _package_dir().parts[-3:] == ("src", "fitdocs", "identity")

    def test_every_module_on_disk_is_registered_and_none_is_stale(self) -> None:
        on_disk = _on_disk()
        assert on_disk, "the walk found no modules: wrong directory"
        assert on_disk == set(_MODULES)

    def test_every_registered_module_parses_and_is_scanned(self) -> None:
        for module in _MODULES:
            assert _path_of(module).is_file(), module
        # The scanners are not vacuous on the real tree: they see imports.
        seen = {m: _import_targets(m, _source_of(m)) for m in _MODULES}
        assert all("__future__" in t for t in seen.values())


@pytest.mark.parametrize("module", _MODULES)
def test_import_closure(module: str) -> None:
    assert _closure_violations(module, _source_of(module)) == []


def test_only_pages_and_holds_touch_the_filesystem() -> None:
    touching = {m for m in _MODULES if _filesystem_touches(m, _source_of(m)) != []}
    assert touching == _FILESYSTEM_MODULES


def test_only_kinds_and_pages_import_the_contract() -> None:
    importing = {m for m in _MODULES if _contract_imports(m, _source_of(m))}
    assert importing == _CONTRACT_MODULES


@pytest.mark.parametrize("module", _MODULES)
def test_no_module_names_a_clock(module: str) -> None:
    assert _clock_names(module, _source_of(module)) == []


# --------------------------------------------------------------------------- #
# Synthetic controls: each rule fires on each form it claims to read
# --------------------------------------------------------------------------- #

_LEAF = "fitdocs.identity.roles"
_INIT = "fitdocs.identity"


def _local(code: str) -> str:
    return "def _f(p):\n" + "".join(f"    {line}\n" for line in code.split("\n"))


_CLOSURE_CASES: Final[list[tuple[str, str, str, str]]] = [
    ("plain", _LEAF, "import fitdocs.sync\n", "fitdocs.sync: forbidden"),
    ("aliased", _LEAF, "import fitdocs.render as r\n", "fitdocs.render: forbidden"),
    (
        "from-alias",
        _LEAF,
        "from fitdocs.audit import check as c\n",
        "fitdocs.audit: forbidden",
    ),
    ("submodule", _LEAF, "import fitdocs.sync.sub\n", "fitdocs.sync.sub: forbidden"),
    ("module-as-alias", _LEAF, "from fitdocs import cli\n", "fitdocs.cli: forbidden"),
    ("relative-leaf", _LEAF, "from ..sync import x\n", "fitdocs.sync: forbidden"),
    (
        "relative-leaf-package-alias",
        _LEAF,
        "from .. import sync\n",
        "fitdocs.sync: forbidden",
    ),
    ("relative-init", _INIT, "from ..sync import x\n", "fitdocs.sync: forbidden"),
    ("beyond-top", _LEAF, "from ...sync import x\n", "cannot be resolved"),
    (
        "function-local",
        _LEAF,
        "def f() -> None:\n    import fitdocs.ingest\n",
        "fitdocs.ingest: forbidden",
    ),
    ("bare-fitdocs-alias", _LEAF, "import fitdocs as f\n", "fitdocs: not an allowed"),
    ("yaml", _LEAF, "import yaml\n", "yaml: forbidden"),
    ("urllib", _LEAF, "from urllib.request import urlopen\n", "urllib.request: forb"),
    ("socket", _LEAF, "import socket\n", "socket: forbidden"),
    (
        "attribute-reach",
        _LEAF,
        "import fitdocs.model\nfitdocs.tiles.x()\n",
        "fitdocs.tiles.x: forbidden (reached by attribute)",
    ),
    (
        "attribute-reach-contract",
        _LEAF,
        "import fitdocs.model\nfitdocs.contract.format_session_uuid\n",
        "only kinds and pages import the contract (reached by attribute)",
    ),
    (
        "contract-in-roles",
        _LEAF,
        "from fitdocs.contract import X\n",
        "only kinds and pages import the contract",
    ),
    (
        "contract-module-alias",
        _LEAF,
        "from fitdocs import contract\n",
        "only kinds and pages import the contract",
    ),
    (
        "tomli_w-outside-holds",
        _LEAF,
        "import tomli_w\n",
        "third party outside its one module",
    ),
    ("unknown-third-party", _LEAF, "import numpy\n", "numpy: not an allowed import"),
    # stdlib outside the allowlist: the closed rule
    ("importlib", _LEAF, "import importlib\n", "importlib: not an allowed"),
    (
        "importlib-alias",
        _LEAF,
        'import importlib as il\nil.import_module("fitdocs.sync")\n',
        "importlib: not an allowed",
    ),
    (
        "import_module-alias",
        _LEAF,
        "from importlib import import_module as im\n",
        "importlib: not an allowed",
    ),
    ("builtins", _LEAF, "import builtins\n", "builtins: not an allowed"),
    (
        "builtins-open-alias",
        _LEAF,
        "from builtins import open as o\n",
        "builtins: not an allowed",
    ),
    ("sys", _LEAF, "import sys\n", "sys: not an allowed"),
    ("io-open-alias", _LEAF, "from io import open as o\n", "io: not an allowed"),
    ("io", _LEAF, "import io\n", "io: not an allowed"),
    ("subprocess", _LEAF, "import subprocess\n", "subprocess: not an allowed"),
    ("linecache", _LEAF, "import linecache\n", "linecache: not an allowed"),
    ("os-outside-holds", _LEAF, "import os\n", "os: not an allowed"),
    ("tempfile-outside-holds", _LEAF, "import tempfile\n", "tempfile: not an allowed"),
    ("tomllib-outside-holds", _LEAF, "import tomllib\n", "tomllib: not an allowed"),
    ("shutil", _LEAF, "from shutil import copy\n", "shutil: not an allowed"),
    ("time", _LEAF, "import time\n", "time: not an allowed"),
    ("time-star", _LEAF, "from time import *\n", "time: not an allowed"),
    (
        "time-alias",
        _LEAF,
        "from time import localtime as lt\n",
        "time: not an allowed",
    ),
    ("timeit", _LEAF, "from timeit import default_timer\n", "timeit: not an allowed"),
    # dynamic escape hatches
    ("exec", _LEAF, 'exec("import fitdocs.sync")\n', "names exec"),
    ("eval", _LEAF, 'eval("1")\n', "names eval"),
    ("compile", _LEAF, 'compile("1", "f", "eval")\n', "names compile"),
    ("__import__", _LEAF, '__import__("fitdocs.plans")\n', "names __import__"),
    ("globals", _LEAF, 'globals()["x"]\n', "names globals"),
    ("vars", _LEAF, "vars()\n", "names vars"),
    ("__builtins__", _LEAF, '__builtins__["open"]\n', "names __builtins__"),
    (
        "builtins-attr-import",
        _LEAF,
        "def f(b):\n    return b.__import__('x')\n",
        "names .__import__",
    ),
    (
        "getattr-literal",
        _LEAF,
        'def f(p):\n    return getattr(p, "write_text")\n',
        "names getattr",
    ),
    (
        "setattr-literal",
        _LEAF,
        'def f(p):\n    setattr(p, "x", 1)\n',
        "names setattr",
    ),
    (
        "delattr-literal",
        _LEAF,
        'def f(p):\n    delattr(p, "x")\n',
        "names delattr",
    ),
    (
        "getattr-built-name",
        _LEAF,
        "def f(d):\n    return getattr(d, 'no' + 'w')()\n",
        "names getattr",
    ),
    (
        "getattr-const-variable",
        _LEAF,
        "_N = 'write_text'\ndef f(p):\n    return getattr(p, _N)\n",
        "names getattr",
    ),
    (
        "getattr-fitdocs",
        _LEAF,
        "import fitdocs.model\ndef f():\n    return getattr(fitdocs, 'sy' + 'nc')\n",
        "names getattr",
    ),
    (
        "dunder-dict",
        _LEAF,
        "def f(d):\n    return d.__dict__['now']\n",
        "names .__dict__",
    ),
    (
        "dunder-class",
        _LEAF,
        "def f(d):\n    return d.__class__\n",
        "names .__class__",
    ),
    # objects, not names: a module reached through an allowed module
    (
        "from-pathlib-import-os",
        _LEAF,
        "from pathlib import os\n",
        "os: not an allowed import (reached as an object)",
    ),
    (
        "pathlib-dot-os",
        _LEAF,
        "import pathlib\ndef f(p):\n    return pathlib.os.listdir(p)\n",
        "os: not an allowed import (reached as an object)",
    ),
    (
        "from-datetime-import-sys",
        _LEAF,
        "from datetime import sys\n",
        "sys: not an allowed import (reached as an object)",
    ),
    (
        "from-dataclasses-import-inspect",
        _LEAF,
        "from dataclasses import inspect\n",
        "inspect: not an allowed import (reached as an object)",
    ),
    (
        "from-pathlib-import-io",
        _LEAF,
        "from pathlib import io\n",
        "io: not an allowed import (reached as an object)",
    ),
    (
        "from-typing-import-operator",
        _LEAF,
        "from typing import operator\n",
        "operator: not an allowed import (reached as an object)",
    ),
    (
        "typing-dot-sys-modules",
        _LEAF,
        "import typing\nx = typing.sys.modules\n",
        "sys: not an allowed import (reached as an object)",
    ),
    (
        "layer-reexports-a-module",
        _LEAF,
        "from fitdocs.settings import tomllib\n",
        "fitdocs.settings.tomllib: not one of the fitdocs.settings names",
    ),
    (
        "class-defined-in-the-contract",
        _LEAF,
        "from fitdocs.docio import parse_frontmatter\n",
        "fitdocs.docio.parse_frontmatter: a filesystem helper",
    ),
    (
        "contract-defined-name-through-a-helper-in-holds",
        "fitdocs.identity.holds",
        "from fitdocs.docio import parse_frontmatter\n",
        "fitdocs.contract.parse_frontmatter: only kinds and pages import the contract"
        " (reached as an object)",
    ),
    # helper-mediated filesystem access (R1, R12, R2, R9, R10)
    (
        "R1-docio-name-in-matching",
        "fitdocs.identity.matching",
        "from fitdocs.docio import read_frontmatter\n"
        "def f(p):\n    return read_frontmatter(p)\n",
        "fitdocs.docio.read_frontmatter: a filesystem helper",
    ),
    (
        "R12-docio-module-in-matching",
        "fitdocs.identity.matching",
        "from fitdocs import docio\ndef f(p):\n    return docio.read_frontmatter(p)\n",
        "fitdocs.docio: a filesystem helper",
    ),
    (
        "R12b-docio-object-reached-from-an-alias",
        "fitdocs.identity.matching",
        "import fitdocs.docio as d\ndef f(p):\n    return d.read_frontmatter(p)\n",
        "fitdocs.docio: a filesystem helper",
    ),
    (
        "R2-settings-loader-in-identity-settings",
        "fitdocs.identity.settings",
        "from fitdocs.settings import SettingsError, load_settings_document\n",
        "fitdocs.settings.load_settings_document: not one of",
    ),
    (
        "R2b-settings-loader-by-attribute",
        "fitdocs.identity.settings",
        "import fitdocs.settings\n"
        "def f(r):\n    return fitdocs.settings.load_settings_document(r)\n",
        "fitdocs.settings.load_settings_document: not one of",
    ),
    (
        "R2c-settings-loader-through-a-module-alias",
        "fitdocs.identity.settings",
        "import fitdocs.settings as s\n"
        "def f(r):\n    return s.load_settings_document(r)\n",
        "fitdocs.settings.load_settings_document: not one of",
    ),
    (
        "S1-from-fitdocs-import-settings-alias",
        "fitdocs.identity.settings",
        "from fitdocs import settings as _core\n"
        "def f(r):\n    return _core.load_settings_document(r)\n",
        "fitdocs.settings.load_settings_document: not one of",
    ),
    (
        "S1b-relative-form",
        "fitdocs.identity.settings",
        "from .. import settings as _core\n"
        "def f(r):\n    return _core.load_settings_document(r)\n",
        "fitdocs.settings.load_settings_document: not one of",
    ),
    (
        "S1c-function-local-form",
        "fitdocs.identity.settings",
        "def f(r):\n    from fitdocs import settings\n"
        "    return settings.load_settings_document(r)\n",
        "fitdocs.settings.load_settings_document: not one of",
    ),
    (
        "S2-identity-package-then-submodule",
        _LEAF,
        "from fitdocs import identity as _id\n"
        "def f(r):\n    return _id.holds.load_holds(r)\n",
        "fitdocs.identity.holds.load_holds: a filesystem helper",
    ),
    (
        "settings-name-in-another-module",
        _LEAF,
        "from fitdocs.settings import SettingsError\n",
        "fitdocs.settings.SettingsError: not one of",
    ),
    (
        "R9-pages-in-planning",
        "fitdocs.identity.planning",
        "from fitdocs.identity.pages import scan_pages\n",
        "fitdocs.identity.pages.scan_pages: a filesystem helper",
    ),
    (
        "R10-holds-in-roles",
        _LEAF,
        "from fitdocs.identity.holds import load_holds\n",
        "fitdocs.identity.holds.load_holds: a filesystem helper",
    ),
    (
        "R10b-holds-module-by-relative-import",
        _LEAF,
        "from . import holds\n",
        "fitdocs.identity.holds: a filesystem helper",
    ),
    (
        "sys-modules",
        _LEAF,
        'import sys\nsys.modules["fitdocs.sync"]\n',
        "sys: not an allowed",
    ),
]


@pytest.mark.parametrize(
    ("module", "source", "expected"),
    [c[1:] for c in _CLOSURE_CASES],
    ids=[c[0] for c in _CLOSURE_CASES],
)
def test_closure_scanner_reads_every_form(
    module: str, source: str, expected: str
) -> None:
    assert any(expected in v for v in _closure_violations(module, source))


def test_closure_scanner_accepts_the_allowed_forms() -> None:
    source = (
        "from __future__ import annotations\n"
        "import hashlib\n"
        "from collections import defaultdict\n"
        "from datetime import datetime, time, UTC\n"
        "from pathlib import Path\n"
        "from fitdocs.model import Activity\n"
        "from fitdocs.identity.kinds import SourceKind\n"
        "from .kinds import SourceKind as K\n"
        "from fitdocs import layout\n"
        "def f(a, s):\n"
        "    return s.replace('a', 'b'), fitdocs.layout.X\n"
    )
    assert _closure_violations(_LEAF, source) == []
    assert (
        _closure_violations(
            "fitdocs.identity.settings", "from fitdocs.settings import SettingsError\n"
        )
        == []
    )
    holds = "fitdocs.identity.holds"
    assert (
        _closure_violations(
            holds, "import os\nimport tempfile\nimport tomllib\nimport tomli_w\n"
        )
        == []
    )
    pages = "fitdocs.identity.pages"
    assert _closure_violations(pages, "from fitdocs.contract import X\n") == []
    assert (
        _closure_violations(pages, "import fitdocs.docio\nfitdocs.contract.X\n") == []
    )


_FS_CASES: Final[list[tuple[str, str, str]]] = [
    ("open", "open('x')\n", "names open"),
    ("write_text", _local("p.write_text('x')"), "names .write_text"),
    ("read_text", _local("return p.read_text()"), "names .read_text"),
    ("mkdir", _local("p.mkdir()"), "names .mkdir"),
    ("unlink", _local("p.unlink()"), "names .unlink"),
    ("glob", _local("return p.glob('*')"), "names .glob"),
    ("iterdir", _local("return p.iterdir()"), "names .iterdir"),
    ("exists", _local("return p.exists()"), "names .exists"),
    ("is_file", _local("return p.is_file()"), "names .is_file"),
    ("stat", _local("return p.stat()"), "names .stat"),
    ("owner", _local("return p.owner()"), "names .owner"),
    ("group-call", _local("return p.group()"), "names .group"),
    ("group-bound", _local("g = p.group\nreturn g()"), "names .group"),
    ("from-pathlib-import-os", "from pathlib import os\n", "imports os"),
    ("pathlib-dot-os", "import pathlib\nx = pathlib.os.listdir\n", "imports os"),
    ("is_socket", _local("return p.is_socket()"), "names .is_socket"),
    ("absolute", _local("return p.absolute()"), "names .absolute"),
    ("path-replace", _local("p.replace(p)"), "names .replace"),
    ("import-os", "import os\n", "imports os"),
    ("os-alias", "import os as o\n", "imports os"),
    ("from-os", "from os import replace\n", "imports os"),
    ("os-path", "import os.path\n", "imports os.path"),
    ("tempfile", "import tempfile\n", "imports tempfile"),
    ("tomllib", "import tomllib\n", "imports tomllib"),
]


@pytest.mark.parametrize(
    ("source", "expected"),
    [c[1:] for c in _FS_CASES],
    ids=[c[0] for c in _FS_CASES],
)
def test_filesystem_scanner_reads_every_touch(source: str, expected: str) -> None:
    assert expected in _filesystem_touches(_LEAF, source)


def test_filesystem_attributes_are_derived_from_pathlib() -> None:
    assert {"write_text", "owner", "is_socket", "absolute", "open"} <= _FS_ATTRIBUTES
    # pure-path operations are not filesystem access
    assert not _FS_ATTRIBUTES & {"name", "parent", "with_name", "joinpath", "suffix"}


def test_group_exemption_is_exactly_decision_group_in_planning() -> None:
    planning = "fitdocs.identity.planning"
    assert (
        _filesystem_touches(planning, "def f(decision):\n    return decision.group\n")
        == []
    )
    # a bound-then-called Path.group, another receiver, another module
    assert _filesystem_touches(planning, "def f(p):\n    g = p.group\n    return g()\n")
    assert _filesystem_touches(planning, "def f(d):\n    return d.group\n")
    assert _filesystem_touches(_LEAF, "def f(decision):\n    return decision.group\n")
    assert _filesystem_touches(_LEAF, "def f(p):\n    return p.group()\n")


def test_filesystem_scanner_ignores_pure_path_use_and_annotations() -> None:
    source = (
        "from pathlib import Path\n"
        "def f(p: Path, s: str):\n"
        "    return p.name, p.parent / 'x', p.with_name('y'), s.upper()\n"
    )
    assert _filesystem_touches(_LEAF, source) == []


_CLOCK_CASES: Final[list[tuple[str, str, str]]] = [
    (
        "datetime.now",
        "import datetime\ndatetime.datetime.now()\n",
        "names .now",
    ),
    (
        "bare-datetime.now",
        "from datetime import datetime\ndatetime.now()\n",
        "names .now",
    ),
    (
        "alias-uncalled",
        "from datetime import datetime as dt\nx = dt.now\n",
        "names .now",
    ),
    (
        "utcnow",
        "from datetime import datetime\ndatetime.utcnow()\n",
        "names .utcnow",
    ),
    ("date.today", "from datetime import date\ndate.today()\n", "names .today"),
]


@pytest.mark.parametrize(
    ("source", "expected"),
    [c[1:] for c in _CLOCK_CASES],
    ids=[c[0] for c in _CLOCK_CASES],
)
def test_clock_scanner_reads_every_spelling(source: str, expected: str) -> None:
    assert expected in _clock_names(_LEAF, source)


def test_clock_scanner_ignores_values_the_caller_supplies() -> None:
    source = (
        "from datetime import datetime, time, timedelta\n"
        "def f(a: datetime, t: time, s: float) -> datetime:\n"
        "    return datetime.fromtimestamp(s) + timedelta(hours=1)\n"
    )
    assert _clock_names(_LEAF, source) == []
