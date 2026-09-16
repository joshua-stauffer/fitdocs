"""The `fitdocs.plans` package boundary: its import closure, its clock
purity, its no-source-write guarantee, and the *reverse* half -- nothing
outside the package reaches back into it (training-blocks spec, task 4.4;
Req 3.9, 6.4, 7.2, 7.7, 8.4). See "PackageBoundary and SurfacePins" in
`.kiro/specs/training-blocks/design.md`.

**Layer shape**, adopted from `tests/history/test_boundary.py` (the design's
own instruction) rather than re-derived, with one addition this package's
own hard rules require (`TestNoSourceWrite`) that the history precedent
does not need at all:

1. **Import closure** (`TestImportClosure`) -- every module under
   `src/fitdocs/plans/` is parsed and its imports resolved to a dotted
   target, then checked against that module's own hand-pinned allowed set
   **by equality**. `TestEnumerationIsComplete` closes the companion gap:
   the hand-maintained module list is checked against the package directory
   in both directions.
2. **Forbidden-name scan** (`TestForbiddenNames`) -- independent of the
   per-module registry: the ingest layer, the load package, the history
   package, the render package, `sync`, `audit`, and any YAML parser, each
   matched by equality or dotted descent, including the alias-appended
   candidate for every `from X import y` (`_forbidden_scan_targets_for_path`),
   the same round-2 fix `tests/history/test_boundary.py` records.
3. **Clock scan** (`TestClockScan`) -- a raw-text substring scan (not only an
   AST walk) for five literal spellings, across every module under the
   package -- catching a spelling in a docstring example as well as in code.
   `engine.py`'s own docstring says it "takes no `today`" -- prose that
   never trips this scan, since the scan looks for the five *qualified*
   spellings (`date.today`, and so on), never the bare word `today`.
4. **No-source-write scan** (`TestNoSourceWrite`) -- this plan's own hard
   rule that no module under the package writes, creates, renames or
   deletes anything under the resolved plan-source directory. Two halves:
   a name ban (`write_text`, `write_bytes`, an `open` in a writing mode,
   `os.replace`, `unlink`, `rmdir`, `rename`, `mkdir`) over every module
   *except* `plans/engine.py`, the package's one writing module; and, for
   `engine.py` itself, an AST trace that every one of those calls' write
   target is composed from `layout.block_doc_path`, `layout.planned_doc_path`,
   `layout.block_pages_dir` or `declaration.ensure_declarations` -- see
   `_EngineWriteTargetAudit`'s own docstring for the trace's precise scope
   and its documented limits.
5. **Reverse reachability** (`TestReverseReachability`,
   `_plans_import_violations`) -- no module under `src/fitdocs/load/`,
   `src/fitdocs/ingest/` or `src/fitdocs/history/`, nor `render/views.py`,
   `sync.py` or `audit.py`, imports `fitdocs.plans` in any form: the same
   five-form candidate construction `tests/history/test_boundary.py` uses
   (bare import, aliased whole-module import, `from` import, package-level
   from-import, relative import resolved against the *enclosing package*),
   with the bare `fitdocs` namespace excluded from every allowance for the
   same reason that file's peer WARN records. `TestReverseReachabilitySyntheticControls`
   proves each form against synthetic source, independent of the real tree.
6. **Contract-importer pin** (`TestContractImporters`) -- exactly `{page,
   engine}` import `fitdocs.contract`, a set-equality pin so a third module
   importing it (as `plan-resolution`'s `corpus` module will) reds this test
   before it can slip past `tests/test_contract_consumers.py`'s
   `CONTRACT_BINDINGS` registry unregistered -- written as a plain set
   comparison against `_import_targets`'s own measured result so
   `plan-resolution` widens it to three names in one hunk.
7. **Region-id literal scan** (`TestNoBareRegionIdLiteral`, follow-up from
   the 3.1 reviewer round): no module under the package spells any of
   `fitdocs.contract.PRESERVED_REGIONS`'s ids as a bare string constant --
   the id must come from the contract constant, mirroring
   `tests/test_contract_consumers.py::test_the_render_layer_spells_no_region_id`.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Final

import fitdocs
import fitdocs.contract
import fitdocs.plans

# --------------------------------------------------------------------------- #
# Module discovery and enumeration completeness
# --------------------------------------------------------------------------- #

#: Every module this boundary owns, hand-maintained -- and checked against the
#: package directory in both directions by `TestEnumerationIsComplete` below,
#: so a new file dropped under the package is never invisible to this module.
PLANS_MODULE_NAMES: Final[tuple[str, ...]] = (
    "fitdocs.plans",
    "fitdocs.plans.block_page",
    "fitdocs.plans.engine",
    "fitdocs.plans.model",
    "fitdocs.plans.page",
    "fitdocs.plans.planned_page",
    "fitdocs.plans.resolution",
    "fitdocs.plans.settings",
    "fitdocs.plans.source",
)


def _plans_package_dir() -> Path:
    path = fitdocs.plans.__file__
    assert path is not None, "fitdocs.plans has no __file__"
    return Path(path).parent


def _plans_module_names_on_disk() -> frozenset[str]:
    """Every `*.py` file anywhere under the plans package, as its dotted
    module name -- the ground truth `PLANS_MODULE_NAMES` is checked
    against, in both directions."""
    root = _plans_package_dir()
    names: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.name == "__init__.py":
            parts = rel.parts[:-1]
            dotted = "fitdocs.plans" + ("." + ".".join(parts) if parts else "")
        else:
            parts = rel.with_suffix("").parts
            dotted = "fitdocs.plans." + ".".join(parts)
        names.add(dotted)
    return frozenset(names)


class TestEnumerationIsComplete:
    def test_every_module_on_disk_is_registered(self) -> None:
        on_disk = _plans_module_names_on_disk()
        assert on_disk, "the walk found no modules -- wrong directory or guard broken"
        missing = on_disk - set(PLANS_MODULE_NAMES)
        assert not missing, (
            f"module(s) on disk are not registered in PLANS_MODULE_NAMES: "
            f"{sorted(missing)}"
        )

    def test_every_registered_module_exists_on_disk(self) -> None:
        on_disk = _plans_module_names_on_disk()
        stale = set(PLANS_MODULE_NAMES) - on_disk
        assert not stale, (
            f"PLANS_MODULE_NAMES names module(s) that do not exist on disk: "
            f"{sorted(stale)}"
        )


def _module_path(module_name: str) -> Path:
    if module_name == "fitdocs.plans":
        return _plans_package_dir() / "__init__.py"
    leaf = module_name.rsplit(".", 1)[-1]
    return _plans_package_dir() / f"{leaf}.py"


def _module_source(module_name: str) -> str:
    return _module_path(module_name).read_text(encoding="utf-8")


def _module_ast(module_name: str) -> ast.Module:
    return ast.parse(
        _module_source(module_name), filename=str(_module_path(module_name))
    )


def _enclosing_package(module_name: str) -> str:
    """The package a relative import in `module_name` resolves against.

    A package's own `__init__.py` resolves a relative import against
    itself; every other (leaf) module resolves against its parent package
    (`tests/history/test_boundary.py`'s own peer WARN) --
    `importlib.util.resolve_name`'s contract is stated in terms of
    `__package__`, which is the package's own dotted name for a package and
    the *parent's* dotted name for a leaf module.
    """
    if module_name == "fitdocs.plans":
        return module_name
    return module_name.rsplit(".", 1)[0]


def _resolve_import_from(node: ast.ImportFrom, enclosing_package: str) -> str | None:
    """The full dotted target a `from ... import ...` statement names, or
    `None` if it cannot be resolved (a relative import beyond the top of the
    package tree)."""
    if node.level == 0:
        return node.module
    dots = "." * node.level
    name = dots + (node.module or "")
    try:
        return importlib.util.resolve_name(name, enclosing_package)
    except ImportError:
        return None


def _import_targets(module_name: str) -> frozenset[str]:
    """Every distinct dotted target `module_name` imports from, resolved --
    the same construction `tests/history/test_boundary.py::_import_targets`
    uses: `import X` and `import X as Y` both resolve to `X`; `from fitdocs
    import contract` resolves to `fitdocs.contract` rather than the bare
    `fitdocs`; every other `from X.Y import z` resolves to `X.Y`."""
    tree = _module_ast(module_name)
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
            if resolved == "fitdocs":
                for alias in node.names:
                    targets.add(f"fitdocs.{alias.name}")
            else:
                targets.add(resolved)
    return frozenset(targets)


# --------------------------------------------------------------------------- #
# Layer 1: import closure, pinned by equality per module
# --------------------------------------------------------------------------- #

#: Every module's exact, measured set of import targets -- an equality pin,
#: not a membership check: an import added to a module without updating its
#: entry here fails, and a stale entry for a removed import fails too.
_ALLOWED_IMPORT_TARGETS: Final[dict[str, frozenset[str]]] = {
    "fitdocs.plans": frozenset(
        {
            "__future__",
            "fitdocs.plans.block_page",
            "fitdocs.plans.engine",
            "fitdocs.plans.model",
            "fitdocs.plans.page",
            "fitdocs.plans.planned_page",
            "fitdocs.plans.resolution",
            "fitdocs.plans.settings",
            "fitdocs.plans.source",
        }
    ),
    "fitdocs.plans.block_page": frozenset(
        {
            "__future__",
            "datetime",
            "fitdocs.layout",
            "fitdocs.plans",
            "fitdocs.plans.model",
            "fitdocs.plans.resolution",
        }
    ),
    "fitdocs.plans.engine": frozenset(
        {
            "__future__",
            "os",
            "tempfile",
            "collections.abc",
            "dataclasses",
            "enum",
            "pathlib",
            "typing",
            "fitdocs.contract",
            "fitdocs.declaration",
            "fitdocs.docmerge",
            "fitdocs.layout",
            "fitdocs.plans.block_page",
            "fitdocs.plans.model",
            "fitdocs.plans.planned_page",
            "fitdocs.plans.resolution",
            "fitdocs.plans.settings",
            "fitdocs.plans.source",
            "fitdocs.settings",
        }
    ),
    "fitdocs.plans.model": frozenset(
        {
            "__future__",
            "re",
            "collections.abc",
            "dataclasses",
            "datetime",
            "typing",
            "fitdocs.declaration",
            "fitdocs.model",
        }
    ),
    "fitdocs.plans.page": frozenset(
        {
            "__future__",
            "collections.abc",
            "datetime",
            "typing",
            "fitdocs.contract",
            "fitdocs.docmerge",
            "fitdocs.plans.model",
            "fitdocs.plans.resolution",
        }
    ),
    "fitdocs.plans.planned_page": frozenset(
        {
            "__future__",
            "fitdocs.layout",
            "fitdocs.plans",
            "fitdocs.plans.model",
            "fitdocs.plans.resolution",
        }
    ),
    "fitdocs.plans.resolution": frozenset(
        {
            "__future__",
            "collections.abc",
            "dataclasses",
            "typing",
        }
    ),
    "fitdocs.plans.settings": frozenset(
        {
            "__future__",
            "os",
            "collections.abc",
            "dataclasses",
            "pathlib",
            "typing",
            "fitdocs.layout",
            "fitdocs.settings",
        }
    ),
    "fitdocs.plans.source": frozenset(
        {
            "__future__",
            "math",
            "tomllib",
            "collections.abc",
            "datetime",
            "pathlib",
            "typing",
            "fitdocs.model",
            "fitdocs.plans.model",
        }
    ),
}


class TestImportClosure:
    def test_registry_covers_exactly_the_enumerated_modules(self) -> None:
        assert set(_ALLOWED_IMPORT_TARGETS) == set(PLANS_MODULE_NAMES)

    def test_every_module_imports_exactly_its_allowed_targets(self) -> None:
        scanned = 0
        for module_name in PLANS_MODULE_NAMES:
            scanned += 1
            measured = _import_targets(module_name)
            allowed = _ALLOWED_IMPORT_TARGETS[module_name]
            assert measured == allowed, (
                f"{module_name}: measured imports {sorted(measured)} do not "
                f"equal the pinned allowed set {sorted(allowed)} -- "
                f"unexpected: {sorted(measured - allowed)}; "
                f"missing (pinned but no longer imported): "
                f"{sorted(allowed - measured)}"
            )
        assert scanned == len(PLANS_MODULE_NAMES), (
            "the walk is looking at the wrong set"
        )


# --------------------------------------------------------------------------- #
# Layer 2: forbidden-name scan, independent of the registry above
# --------------------------------------------------------------------------- #

#: Forbidden by name (design.md "PackageBoundary and SurfacePins", and this
#: task's own bullet list): the ingest layer, the load package, the history
#: package, the render package, sync, audit, and any YAML parser. Each entry
#: is a dotted prefix -- an import target matches if it equals the entry or
#: is a `.`-bounded descendant of it.
_FORBIDDEN_TARGETS: Final[tuple[str, ...]] = (
    "fitdocs.ingest",
    "fitdocs.load",
    "fitdocs.history",
    "fitdocs.render",
    "fitdocs.sync",
    "fitdocs.audit",
    "yaml",
)


def _matches_forbidden(target: str) -> str | None:
    for forbidden in _FORBIDDEN_TARGETS:
        if target == forbidden or target.startswith(f"{forbidden}."):
            return forbidden
    return None


def _forbidden_scan_targets_for_path(
    path: Path, enclosing_package: str
) -> frozenset[str]:
    """Every dotted target this scan checks against `_FORBIDDEN_TARGETS`,
    wider than `_import_targets`: for every `from X import y`, this
    additionally records the alias-appended candidate `X.y`, catching
    `from fitdocs.render import views` by name even though `_import_targets`
    alone would resolve it to the bare, unforbidden `fitdocs.render`
    (`tests/history/test_boundary.py`'s own round-2 fix, adopted)."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_from(node, enclosing_package)
            if resolved is None:
                continue
            if resolved == "fitdocs":
                for alias in node.names:
                    targets.add(f"fitdocs.{alias.name}")
            else:
                targets.add(resolved)
            for alias in node.names:
                targets.add(f"{resolved}.{alias.name}")
    return frozenset(targets)


class TestForbiddenNames:
    def test_no_module_imports_a_forbidden_target(self) -> None:
        pairs = tuple(
            (_module_path(name), _enclosing_package(name))
            for name in PLANS_MODULE_NAMES
        )
        assert pairs, "the walk found no files -- wrong path list"
        scanned = 0
        offenders: list[str] = []
        for path, enclosing_package in pairs:
            scanned += 1
            for target in _forbidden_scan_targets_for_path(path, enclosing_package):
                forbidden = _matches_forbidden(target)
                if forbidden is not None:
                    offenders.append(f"{path.name} imports {target} ({forbidden})")
        assert scanned == len(PLANS_MODULE_NAMES), (
            "the walk is looking at the wrong set"
        )
        assert not offenders, offenders


# --------------------------------------------------------------------------- #
# Layer 3: clock scan -- raw-text substring, code or docstring alike
# --------------------------------------------------------------------------- #

#: The five literal spellings the design names by example -- a qualified
#: attribute access, so `"today"` alone (used freely in `engine.py`'s own
#: prose, e.g. "This module takes no `today`") never trips this scan; only
#: the qualified form a real clock read or a docstring example naming one
#: would use does.
_CLOCK_SPELLINGS: Final[tuple[str, ...]] = (
    "date.today",
    "datetime.now",
    "datetime.utcnow",
    "time.time",
    "time.monotonic",
)


class TestClockScan:
    def test_no_clock_spelling_appears_anywhere_in_code_or_docstring(self) -> None:
        paths = tuple(_module_path(name) for name in PLANS_MODULE_NAMES)
        assert paths, "the walk found no files -- wrong path list"
        offenders: list[str] = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for spelling in _CLOCK_SPELLINGS:
                if spelling in text:
                    offenders.append(f"{path.name}: {spelling}")
        assert not offenders, offenders


# --------------------------------------------------------------------------- #
# Layer 4: no-source-write scan
# --------------------------------------------------------------------------- #

#: The write-shaped names this plan's hard rule forbids anywhere under the
#: package, except `plans/engine.py` -- the package's one writing module.
_WRITE_METHOD_NAMES: Final[frozenset[str]] = frozenset(
    {"write_text", "write_bytes", "unlink", "rmdir", "rename", "mkdir"}
)

#: `plans/engine.py` is the package's only writing module (design.md,
#: "PlanEngine"); every other module under the package is held to a
#: blanket name ban.
_ENGINE_MODULE: Final[str] = "fitdocs.plans.engine"


def _os_module_names(tree: ast.Module) -> frozenset[str]:
    """Every local name bound to the `os` module itself anywhere in `tree` --
    the bare `os` from a plain `import os`, any `import os as X` alias
    (round-1 review fix: `import os as _os` then `_os.replace(...)` must be
    caught exactly as `os.replace(...)` is), and an unaliased `import
    os.<submodule>` (round-2 review fix, item 5: `import os.path` binds the
    top-level name `os` in the importing module's namespace, exactly as a
    plain `import os` does -- but only when unaliased; `import os.path as
    X` binds `X` to the *submodule* `os.path`, never to `os` itself, so
    that form is correctly left unrecorded here)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    names.add(alias.asname or "os")
                elif alias.name.startswith("os.") and alias.asname is None:
                    names.add("os")
    return frozenset(names)


def _os_replace_names(tree: ast.Module) -> frozenset[str]:
    """Every local bare name bound directly to `os.replace` anywhere in
    `tree` -- `replace` (or its alias) from `from os import replace [as Y]`
    (round-1 review fix: `from os import replace as _r; _r(...)` must be
    caught too)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "replace":
                    names.add(alias.asname or "replace")
    return frozenset(names)


def _os_replace_target(
    call: ast.Call, *, os_names: frozenset[str], replace_names: frozenset[str]
) -> ast.expr | None:
    """If `call` is a call to `os.replace` -- under any import-aliasing form
    `_os_module_names`/`_os_replace_names` resolved for this module -- return
    the replace *target* (its second positional argument), else `None`."""
    func = call.func
    is_replace_call = (
        isinstance(func, ast.Attribute)
        and func.attr == "replace"
        and isinstance(func.value, ast.Name)
        and func.value.id in os_names
    ) or (isinstance(func, ast.Name) and func.id in replace_names)
    if not is_replace_call:
        return None
    return call.args[1] if len(call.args) >= 2 else None


def _open_write_target(call: ast.Call) -> ast.expr | None:
    """If `call` is a call to the builtin `open` *or* a `.open(...)` method
    call (round-1 review fix: `Path.open("w")` is exactly as much a write as
    `Path.write_text(...)` and was previously invisible to this scan) in a
    writing mode (`'w'`/`'a'`/`'x'`), return the path being opened -- the
    first positional argument for the builtin form, the receiver for the
    method form. Returns `None` for anything else, including a builtin
    `open`/`.open()` call with no mode argument at all (the default mode for
    both is `'r'`, never a write)."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "open":
        target = call.args[0] if call.args else None
        mode_index = 1
    elif isinstance(func, ast.Attribute) and func.attr == "open":
        target = func.value
        mode_index = 0
    else:
        return None
    mode: object = None
    if len(call.args) > mode_index:
        mode_arg = call.args[mode_index]
        if isinstance(mode_arg, ast.Constant):
            mode = mode_arg.value
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            mode = keyword.value.value
    if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x")):
        return target
    return None


def _write_name_offenders_in_tree(tree: ast.Module) -> list[str]:
    """Every offending write-shaped call or name this tree spells, by kind
    -- the single scanner both the real-module ban (`TestNoSourceWrite`) and
    its synthetic controls run, so a control proves the production scanner
    itself catches a shape, never a hand-rolled copy of it (round-1 review
    fix, item 9)."""
    os_names = _os_module_names(tree)
    replace_names = _os_replace_names(tree)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _WRITE_METHOD_NAMES:
            offenders.append(f"L{node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Call):
            if (
                _os_replace_target(node, os_names=os_names, replace_names=replace_names)
                is not None
            ):
                offenders.append(f"L{node.lineno}: os.replace")
            elif _open_write_target(node) is not None:
                offenders.append(f"L{node.lineno}: open(..., writing mode)")
    return offenders


def _write_name_offenders(module_name: str) -> list[str]:
    return _write_name_offenders_in_tree(_module_ast(module_name))


class TestNoSourceWrite:
    def test_no_module_but_engine_spells_a_write_shaped_name(self) -> None:
        scanned = 0
        offenders: dict[str, list[str]] = {}
        for module_name in PLANS_MODULE_NAMES:
            if module_name == _ENGINE_MODULE:
                continue
            scanned += 1
            found = _write_name_offenders(module_name)
            if found:
                offenders[module_name] = found
        assert scanned == len(PLANS_MODULE_NAMES) - 1, (
            "the walk is looking at the wrong set"
        )
        assert not offenders, offenders

    def test_synthetic_module_with_a_stray_write_text_is_caught(self) -> None:
        """Positive control: `_write_name_offenders_in_tree` over synthetic
        source containing a stray `Path(...).write_text(...)` call is
        non-empty -- proving the scan itself, not merely today's clean
        tree."""
        offenders = _write_name_offenders_in_tree(
            ast.parse(
                "from pathlib import Path\n"
                "\n"
                "def leak(source_dir: Path) -> None:\n"
                '    (source_dir / "x.md").write_text("oops", encoding="utf-8")\n'
            )
        )
        assert offenders != [], "a stray write_text call was not caught"

    def test_synthetic_module_with_a_stray_path_open_write_is_caught(self) -> None:
        """Positive control (round-1 review fix, item 1): `p.open("w")` is a
        write exactly as much as `p.write_text(...)` is, and must be caught
        by the same scanner."""
        offenders = _write_name_offenders_in_tree(
            ast.parse(
                "from pathlib import Path\n"
                "\n"
                "def leak(p: Path) -> None:\n"
                "    with p.open('w') as handle:\n"
                "        handle.write('oops')\n"
            )
        )
        assert offenders != [], "a stray Path.open('w') call was not caught"

    def test_synthetic_module_with_a_stray_aliased_os_replace_is_caught(self) -> None:
        """Positive control (round-1 review fix, item 2): both alias forms
        of `os.replace` -- `import os as X; X.replace(...)` and
        `from os import replace as Y; Y(...)` -- must be caught, not only
        the bare `os.replace(...)` spelling."""
        offenders_module_alias = _write_name_offenders_in_tree(
            ast.parse(
                "import os as _os\n"
                "\n"
                "def leak(src: str, dst: str) -> None:\n"
                "    _os.replace(src, dst)\n"
            )
        )
        assert offenders_module_alias != [], "import os as _os; _os.replace(...) missed"

        offenders_name_alias = _write_name_offenders_in_tree(
            ast.parse(
                "from os import replace as _r\n"
                "\n"
                "def leak(src: str, dst: str) -> None:\n"
                "    _r(src, dst)\n"
            )
        )
        assert offenders_name_alias != [], (
            "from os import replace as _r; _r(...) was not caught"
        )

    def test_synthetic_module_with_an_unaliased_submodule_import_os_replace_is_caught(
        self,
    ) -> None:
        """Positive control (round-2 review fix, item 5): an unaliased
        `import os.path` binds the bare name `os` exactly as `import os`
        does, so `os.replace(...)` reached that way must be caught too --
        previously only `alias.name == "os"` was recorded, so the `os.`
        submodule form was invisible."""
        offenders = _write_name_offenders_in_tree(
            ast.parse(
                "import os.path\n"
                "\n"
                "def leak(src: str, dst: str) -> None:\n"
                "    os.replace(src, dst)\n"
            )
        )
        assert offenders != [], "import os.path; os.replace(...) was not caught"

    def test_synthetic_module_with_no_write_shaped_name_is_not_flagged(self) -> None:
        """Negative control: ordinary read-only source, structurally similar
        to a real plans module -- including a plain `import os` used only
        for `os.path.normpath` (`plans/settings.py`'s own real shape) -- is
        not flagged."""
        offenders = _write_name_offenders_in_tree(
            ast.parse(
                "import os\n"
                "from pathlib import Path\n"
                "\n"
                "def read(path: Path) -> str:\n"
                "    os.path.normpath(str(path))\n"
                "    return path.read_text(encoding='utf-8')\n"
            )
        )
        assert offenders == []


# --------------------------------------------------------------------------- #
# Layer 4b: engine.py's write targets trace back to the layout helpers
# --------------------------------------------------------------------------- #

#: The three layout helpers and the one declaration helper `engine.py`'s
#: writes must compose from (design.md, "PlanEngine"); a name is a "safe
#: root" when it is one of these calls, or is built from one through the
#: propagation rules `_EngineWriteTargetAudit` documents.
_LAYOUT_HELPER_NAMES: Final[frozenset[str]] = frozenset(
    {"block_doc_path", "planned_doc_path", "block_pages_dir"}
)

#: `_atomic_write`'s own first parameter is trusted *inside that one
#: function's body*; every call *site* of `_atomic_write` elsewhere in the
#: module is itself audited as a write-shaped call in its own right (its
#: first argument is the write target), so trusting the parameter here does
#: not smuggle an unaudited path through -- see `_write_call_target`.
_ATOMIC_WRITE_FUNCTION: Final[str] = "_atomic_write"

#: For every statement kind `_walk_stmt` models with a dedicated branch,
#: the exact field names that branch's own logic consumes -- read by
#: `_delegate_remaining_fields` at runtime (the single source of truth
#: `_walk_stmt`'s branches and `TestFieldCoverageSweep` both use, round-4
#: review fix, item 1) to decide which fields still need the generic
#: `_walk_field_value` treatment. A kind absent from this dict (every kind
#: with no dedicated branch, e.g. `ast.Match`) has nothing consumed, so
#: `_delegate_remaining_fields` walks every one of its fields generically.
#: `TestFieldCoverageSweep` asserts every entry here is an actual subset of
#: the real `kind._fields` -- a typo'd field name would otherwise be
#: silently inert (an unknown field name in `consumed` just means nothing
#: is ever skipped, which is safe but would hide the typo).
_CONSUMED_FIELDS: Final[dict[type[ast.stmt], frozenset[str]]] = {
    ast.FunctionDef: frozenset({"body"}),
    ast.AsyncFunctionDef: frozenset({"body"}),
    ast.ClassDef: frozenset({"body"}),
    ast.If: frozenset({"test", "body", "orelse"}),
    ast.For: frozenset({"target", "iter", "body", "orelse"}),
    ast.AsyncFor: frozenset({"target", "iter", "body", "orelse"}),
    ast.While: frozenset({"test", "body", "orelse"}),
    ast.Try: frozenset({"body", "handlers", "orelse", "finalbody"}),
    ast.TryStar: frozenset({"body", "handlers", "orelse", "finalbody"}),
    ast.With: frozenset({"items", "body"}),
    ast.AsyncWith: frozenset({"items", "body"}),
    ast.Assign: frozenset({"targets", "value"}),
    ast.AnnAssign: frozenset({"target", "annotation", "value"}),
    ast.AugAssign: frozenset({"target", "value"}),
    ast.Expr: frozenset({"value"}),
    ast.Delete: frozenset({"targets"}),
    ast.Global: frozenset({"names"}),
    ast.Nonlocal: frozenset({"names"}),
    ast.Import: frozenset({"names"}),
    ast.ImportFrom: frozenset({"names"}),
}

#: Per explicitly modelled kind, the field names that carry no expression
#: or nested statement at all -- a bare identifier, a `str`/`int`/`None`
#: value, or (for `AugAssign`) an operator enum -- and so are correctly
#: absent from both `_CONSUMED_FIELDS` and anything `_walk_field_value`
#: would ever act on. `TestFieldCoverageSweep` uses this to state the
#: round-4 review's own completeness claim precisely: every field of an
#: explicitly modelled kind is either consumed, or delegated generically,
#: or named here as carrying nothing to walk -- never silently unaccounted
#: for.
_IDENTIFIER_OR_SIMPLE_FIELDS: Final[dict[type[ast.stmt], frozenset[str]]] = {
    ast.FunctionDef: frozenset({"name", "type_comment"}),
    ast.AsyncFunctionDef: frozenset({"name", "type_comment"}),
    ast.ClassDef: frozenset({"name"}),
    ast.If: frozenset(),
    ast.For: frozenset({"type_comment"}),
    ast.AsyncFor: frozenset({"type_comment"}),
    ast.While: frozenset(),
    ast.Try: frozenset(),
    ast.TryStar: frozenset(),
    ast.With: frozenset({"type_comment"}),
    ast.AsyncWith: frozenset({"type_comment"}),
    ast.Assign: frozenset({"type_comment"}),
    ast.AnnAssign: frozenset({"simple"}),
    ast.AugAssign: frozenset({"op"}),
    ast.Expr: frozenset(),
    ast.Delete: frozenset(),
    ast.Global: frozenset(),
    ast.Nonlocal: frozenset(),
    ast.Import: frozenset(),
    ast.ImportFrom: frozenset({"module", "level"}),
}

#: Per explicitly modelled kind, the field names carrying a node (or a
#: list of nodes) that `_walk_stmt`'s own branch does *not* consume
#: directly and so are picked up by `_delegate_remaining_fields`'s generic
#: `_walk_field_value` dispatch. Together with `_CONSUMED_FIELDS` and
#: `_IDENTIFIER_OR_SIMPLE_FIELDS`, this is the third of three hand-written
#: sets `TestFieldCoverageSweep` asserts exactly partition `kind._fields`
#: -- so a field this walker forgot to account for in *any* of the three
#: reds that test, rather than silently falling through unaudited (round-4
#: review fix, item 1).
_DELEGATED_NODE_FIELDS: Final[dict[type[ast.stmt], frozenset[str]]] = {
    ast.FunctionDef: frozenset({"decorator_list", "args", "returns"}),
    ast.AsyncFunctionDef: frozenset({"decorator_list", "args", "returns"}),
    ast.ClassDef: frozenset({"bases", "keywords", "decorator_list"}),
    ast.If: frozenset(),
    ast.For: frozenset(),
    ast.AsyncFor: frozenset(),
    ast.While: frozenset(),
    ast.Try: frozenset(),
    ast.TryStar: frozenset(),
    ast.With: frozenset(),
    ast.AsyncWith: frozenset(),
    ast.Assign: frozenset(),
    ast.AnnAssign: frozenset(),
    ast.AugAssign: frozenset(),
    ast.Expr: frozenset(),
    ast.Delete: frozenset(),
    ast.Global: frozenset(),
    ast.Nonlocal: frozenset(),
    ast.Import: frozenset(),
    ast.ImportFrom: frozenset(),
}


class _EngineWriteTargetAudit:
    """Traces every write-shaped call in `plans/engine.py` back to one of
    `_LAYOUT_HELPER_NAMES` (or, inside `_atomic_write` itself, to that
    function's own first parameter -- every call *site* of `_atomic_write`
    is itself a write-shaped call this same audit checks, since
    `_atomic_write(...)` is recognized by `_write_call_target` with its
    first argument as the write target).

    **Every scope audited** (round-2 review fix, item 2): the module body
    is itself a scope; every `ClassDef` body is its own fresh scope, and
    every method inside it (a `FunctionDef`/`AsyncFunctionDef`) gets a
    further fresh scope of its own dispatched the same way a top-level
    function's body is; every `FunctionDef`/`AsyncFunctionDef`, however
    deeply nested, gets a fresh scope. Round 1 only ever entered a
    top-level `FunctionDef`, so a bare write-shaped call at module level, or
    one inside a class method, was invisible to this audit entirely.

    **Per-scope, order-sensitive analysis** (round-1 review fix, item 3):
    each scope (as enumerated just above) gets its own fresh
    `derived`/`containers` state -- a name derived while analyzing one
    scope proves nothing about a same-named local in a *different* one, so
    a new function that reuses a name like `child` from another function's
    own analysis is audited from scratch, deriving nothing for free.
    Within one scope, statements are walked in program order, and a name's
    derived status is *live*, not monotonic: assigning a derived name to
    something unsafe **invalidates** it -- `target = block_doc_path(...)`
    followed later by `target = source_dir / "leak.md"` un-derives
    `target`, so a write through it after the rebind is flagged.

    **Every binding form is held to the same sound default** (round-2
    review fix, item 1: five forms rebound a derived name to an unsafe
    value *without* invalidating it, contradicting the paragraph above as
    it stood after round 1; round-3 added tuple/list `for`- and
    `with`-targets and `Import`/`ImportFrom`; round-4 adds the two forms
    below): a `Name` target not satisfying one of the derivation rules
    below is always *discarded*, never left derived from an earlier,
    unrelated statement, for every one of: `Assign` (every target, so
    `a = b = unsafe` invalidates both `a` and `b`), `AnnAssign` with a
    value (`p: Path = ...`, identically to `Assign`), `AugAssign`
    (`p /= "../../plans/leak.md"` -- this walker never models what an
    augmented assignment operator actually computes, so it is unconditionally
    discarded), every element of a `Tuple`/`List` assignment, `for`- or
    `with`-target except the one `tempfile.mkstemp` special case below
    (recursively, via `_discard_names_in`, so a nested tuple element is
    covered too), a walrus `(name := ...)` anywhere in a scanned expression
    (`_scan_expr`'s own pre-pass, applied before that same expression's
    write-calls are judged, since a rebind and a write can share one
    expression, e.g. `if (p := source_dir / "leak.md"):`), `del name` /
    `global name` / `nonlocal name`, an `Import`/`ImportFrom` binding
    (round-3 review fix, item 2), **`except <type> as name:`** (round-4
    review fix, item 2 -- `handler.name` is discarded before the handler's
    own body is walked, since it names a fresh exception object every
    time, never a layout-helper path), and **every name a `match` pattern
    captures** (round-4 review fix, item 2 -- `MatchAs.name` (`case x:`,
    `case Point() as p:`), `MatchStar.name` (`case [*rest]:`) and
    `MatchMapping.rest` (`case {**rest}:`), discarded via
    `_discard_match_pattern_captures` before the case's `guard` and `body`
    are walked, recursively through `MatchOr`/`MatchSequence`/`MatchClass`
    sub-patterns, since none of these forms is a layout-helper call).

    **No field is silently skipped** (round-4 review fix, item 1: the
    previous three rounds fixed the statement *kinds* a write could hide
    inside, but every explicitly modelled branch still consumed only the
    fields its own derivation logic needed and returned, leaving every
    *other* field of that same node -- a decorator, a parameter default or
    annotation, a class base or keyword, an `except` clause's exception
    type -- unscanned entirely, all of them places Python itself evaluates
    an expression, hence places a write-shaped call can legally sit): every
    branch in `_walk_stmt` now ends by calling `_delegate_remaining_fields`
    with the exact set of field names its own logic already consumed:
    whatever remains is walked generically by `_walk_field_value`, the
    same dispatcher the final fallthrough (a statement kind with *no*
    dedicated branch at all, e.g. `Match`) now reaches too, by calling
    `_delegate_remaining_fields` with nothing pre-consumed -- one
    mechanism, not the two separate ones (a per-branch ad hoc scan, and a
    once-separate `_walk_generic`) round 3 left in place. `_walk_field_value`
    dispatches on the field's own runtime type,
    not on which statement it came from: an `ast.expr` is scanned; an
    `ast.arguments` (a `FunctionDef`/`AsyncFunctionDef`'s `args`) has every
    parameter annotation and every positional/keyword default scanned via
    `_scan_arguments`, in the *enclosing* scope, matching Python's own
    evaluation order (defaults and annotations evaluate at `def`-time,
    before the function body ever runs); an `ast.keyword` (a `ClassDef`'s
    `keywords`, e.g. `class Foo(metaclass=Meta):`) has its `value` scanned;
    an `ast.withitem` has its `context_expr` scanned and its target applied;
    a nested `ast.stmt` is walked; an `ast.match_case` has its pattern's
    captures discarded, its `guard` scanned, and its `body` walked; a `list`
    recurses element-wise; anything else (an identifier, a constant, an
    operator enum, `None`) is inert and walked to nothing.
    `TestFieldCoverageSweep` is the mechanical proof this holds for every
    explicitly modelled kind: `_CONSUMED_FIELDS[kind]` -- the single
    registry both `_walk_stmt`'s branches and the test read -- is asserted
    to be an actual subset of `kind._fields`, and four dedicated positive
    controls (a decorator argument, a parameter default, a class base, and
    an `except` clause's type) each prove the specific field class the
    round-4 review named is no longer silently skipped.

    **Propagation rules**, applied statement by statement in program order,
    within one scope: a name is "derived" when it is (a) the direct result
    of calling a layout helper; (b) assigned from another derived name, a
    subscript of a derived name, or the **`.parent`** attribute of a
    derived name specifically -- no other attribute access propagates
    derivedness (round-1 review fix, item 9: a blanket "any attribute of a
    safe value is safe" overclaimed for `.stem`, `.name` and every other
    attribute, none of which need stay inside the owned tree); (c) a dict
    literal or dict comprehension whose values are all derived (a
    *container*); (d) the loop variable of a `for x in container:` where
    `container` is a derived container, or of `for x in y.iterdir():` /
    `for x in container.values():` (optionally wrapped in `sorted(...)`,
    as `engine.py`'s own scans are) where `y` or `container` is derived;
    (e) a list that only ever has derived values `.append`ed to it (a
    *container*, by the same rule as (c)); (f) `tempfile.mkstemp`'s own
    temp-file output, when its `dir=` keyword names a derived location, and
    `Path(x)` wrapping an already-derived name `x`.

    Write-shaped calls audited (`_write_call_target`, built from the same
    three helpers `_write_name_offenders_in_tree` uses --
    `_WRITE_METHOD_NAMES`, `_os_replace_target`, `_open_write_target` --
    so the two guards never drift apart on what counts as a write):
    `.write_text`/`.write_bytes`/`.unlink`/`.rmdir`/`.rename`/`.mkdir`
    method calls, `_atomic_write(...)` calls, `os.replace(...)` calls under
    any aliased import form, and a builtin `open`/`.open(...)` call in a
    writing mode.

    **Documented scope and limit** (Step 5's own gate: an honest boundary,
    not a silent one): this is intraprocedural per scope and
    **path-insensitive in a genuinely permissive direction, not a
    conservative one** -- every branch of an `if`/`try`/`for` is treated as
    always taken, so (i) a name derived on only one branch is still
    considered derived after the branches rejoin, *and*, symmetrically,
    (ii) an unsafe rebind on one branch followed by a safe rebind on a
    *different* (not sequentially later) branch is accepted regardless of
    which branch execution would actually take. Neither direction is safe
    in the ordinary sense of "conservative" -- both can let a real write
    through unflagged, and this is measured, not hypothetical: an
    `if len(entries) > 10: target = source_dir / "leaked.md" else: target
    = block_doc_path(...)` followed by one `target.write_text(...)` passes
    *this* audit outright (round-3 review finding -- the previous
    docstring here overclaimed that `tests/test_confinement.py`'s runtime
    guard "exists to close" this gap; measured directly instead: staged
    against the confinement fixture's own one-row source, that same
    mutation passes the runtime guard too, because the fixture's run takes
    only the `else` branch and never executes the unsafe one at all -- a
    fixture whose run happened to exercise the `if len(entries) > 10`
    branch would be caught by the runtime guard, but nothing in this suite
    exercises it, so the runtime guard is not a general backstop for this
    audit's path-insensitivity, only a *conditional* one whose coverage
    depends on which branch a given fixture's run happens to take).
    Comprehension and lambda scopes are not modelled at all: a
    comprehension target (`[x for x in ...]`) or a lambda parameter
    default that shadows a name this audit has derived in the enclosing
    scope is judged by the *outer* name's status, never its own (Python's
    own scoping rules give a comprehension and a lambda their own local
    namespace, which this audit does not track separately). A value passed
    into a *nested* function definition is not followed beyond trusting
    `_atomic_write`'s own first parameter inside that one function's own
    scope, independently checked by auditing every call *site* of
    `_atomic_write` the same way any other write-shaped call is. A write
    reached through a private helper this module does not yet call,
    composing a path some way this audit's propagation rules do not name,
    would need the rules extended, not merely re-run. Its positive control
    (`test_a_synthetic_engine_style_write_from_the_source_directory_is_caught`)
    proves it catches the shape of write this task names by name; its
    rebinding control
    (`test_a_rebind_to_an_unsafe_value_after_a_safe_one_is_caught`) proves
    it is not merely additive over a name once seen safe; its
    cross-function control
    (`test_a_new_function_reusing_another_functions_derived_name_is_caught`)
    proves a name's derivedness never leaks across function scopes; its
    module-level and class-method controls
    (`test_a_module_level_write_is_caught`,
    `test_a_class_method_write_is_caught`) prove every scope this class
    docstring enumerates is actually entered, not merely top-level
    functions; `TestStatementKindSweep` is the proof every concrete
    `ast.stmt` subclass Python 3.11 defines is either explicitly modelled
    above or reaches `_delegate_remaining_fields`'s generic dispatch
    (round-4 review fix, item 4: after
    round 3 this covered every *statement kind*, but not, until round 4's
    "no field is silently skipped" rule above, every *expression field* of
    each -- the qualified claim is: every concrete `ast.stmt` subclass, and
    every expression field of each, whether consumed by a dedicated branch
    or delegated generically).

    **This is the audit's contract, stated once, after four review rounds
    converged on it**: this is a static, intraprocedural, per-scope,
    path-insensitive trace over every statement kind and every expression
    field Python 3.11's grammar defines. Five gaps are disclosed, not
    accidental: four are not this audit's job to close, and the fifth is a
    queued follow-up. **Path-insensitivity**
    (documented above, with a measured counter-example); **comprehension
    and lambda scoping** (documented above -- not tracked as separate
    namespaces); **interprocedural data flow** (a value passed into a
    nested function or returned from a call this module does not itself
    define is not followed beyond `_atomic_write`'s own first parameter,
    independently checked at every call site); and **dynamic dispatch**
    (`getattr`, `globals()`, `eval`, or any other reflective way of reaching
    a name or a method this audit resolves lexically). The fifth, **callable
    aliasing**, is a gap the reviewer measured and the controller queued
    rather than closed in the round that found it: a write-shaped reference
    bound to a name and called later (`_aw = _atomic_write; _aw(unsafe, text)`
    or `w = unsafe.write_text; w(text)`) is a plain `Name` call at the site
    where the write happens, and `_write_call_target` recognises writes only
    at the `Call` whose `func` is the write attribute itself -- see the
    `.kiro/queue/` item on the engine audit's callable aliasing.
    `tests/test_confinement.py`'s `plan` entry point and its own precise
    negative-half test are the *behavioural* layer for all five: they
    observe what a real run actually wrote, which is why the confinement
    guard's coverage of a
    path-insensitivity gap is real but conditional on the staged fixture's
    run taking the unsafe branch (documented above), never a blanket
    guarantee this static audit can lean on. Together the two layers are
    the guard training-blocks task 4.4 registers: this class the static
    half, the confinement guard the runtime half.
    """

    def __init__(self, tree: ast.Module) -> None:
        self._tree = tree
        self._os_names = _os_module_names(tree)
        self._replace_names = _os_replace_names(tree)
        self._offenders: list[str] = []
        # The module body is itself a scope -- a bare write-shaped call at
        # module level, never inside any function, is audited too (round-2
        # review fix, item 2: only top-level `FunctionDef`s were audited
        # before, so `if False: Path("/x").write_text(...)` at module scope
        # was invisible).
        self._walk_scope(tree.body, function_node=None)

    def offenders(self) -> list[str]:
        return list(self._offenders)

    def _walk_scope(
        self,
        stmts: list[ast.stmt],
        *,
        function_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
    ) -> None:
        """Walk one fresh scope's statement list -- the module body, a
        class body (round-2 review fix, item 2: a class method's write was
        previously invisible, since only top-level `FunctionDef`s were
        ever entered), or a function's own body -- with its own fresh
        `derived`/`containers` state. `function_node` is the enclosing
        `FunctionDef`/`AsyncFunctionDef` when `stmts` is that function's
        own body (`None` for the module body and for a class body), used
        only to seed `_atomic_write`'s own first-parameter trust."""
        derived: set[str] = set()
        containers: set[str] = set()
        if (
            function_node is not None
            and function_node.name == _ATOMIC_WRITE_FUNCTION
            and function_node.args.args
        ):
            derived.add(function_node.args.args[0].arg)
        self._walk_body(stmts, derived, containers)

    # -- expression-level safety --------------------------------------------

    def _is_safe_root(
        self, expr: ast.expr, derived: set[str], containers: set[str]
    ) -> bool:
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
            if expr.func.id in _LAYOUT_HELPER_NAMES:
                return True
            # `Path(x)` wrapping an already-derived name stays derived --
            # `_atomic_write`'s own `tmp_path = Path(tmp_name)`.
            if expr.func.id == "Path" and len(expr.args) == 1:
                return self._is_safe_root(expr.args[0], derived, containers)
            return False
        if isinstance(expr, ast.Name):
            return expr.id in derived or expr.id in containers
        if isinstance(expr, ast.Subscript):
            return self._is_safe_root(expr.value, derived, containers)
        if isinstance(expr, ast.Attribute):
            # Only `.parent` of a derived path stays inside the owned tree.
            if expr.attr == "parent":
                return self._is_safe_root(expr.value, derived, containers)
            return False
        return False

    def _dict_values_all_safe(
        self, expr: ast.expr, derived: set[str], containers: set[str]
    ) -> bool:
        if isinstance(expr, ast.Dict):
            return bool(expr.values) and all(
                self._is_safe_root(value, derived, containers)
                for value in expr.values
                if value is not None
            )
        if isinstance(expr, ast.DictComp):
            return self._is_safe_root(expr.value, derived, containers)
        return False

    # -- write-shaped call detection (shared with TestNoSourceWrite) -------

    def _write_call_target(self, call: ast.Call) -> tuple[ast.expr | None, str] | None:
        """`(target, label)` if `call` is one of the four write-shaped call
        forms this audit and `TestNoSourceWrite`'s scan both recognize,
        else `None`."""
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr in _WRITE_METHOD_NAMES
        ):
            return call.func.value, f"L{call.lineno}: .{call.func.attr}"
        if (
            isinstance(call.func, ast.Name)
            and call.func.id == _ATOMIC_WRITE_FUNCTION
            and call.args
        ):
            return call.args[0], f"L{call.lineno}: {_ATOMIC_WRITE_FUNCTION}(...)"
        replace_target = _os_replace_target(
            call, os_names=self._os_names, replace_names=self._replace_names
        )
        if replace_target is not None:
            return replace_target, f"L{call.lineno}: os.replace"
        open_target = _open_write_target(call)
        if open_target is not None:
            return open_target, f"L{call.lineno}: open(..., writing mode)"
        return None

    def _scan_expr(
        self, expr: ast.expr | None, derived: set[str], containers: set[str]
    ) -> None:
        """Scan one expression, in two passes over its own subtree (round-2
        review fix, item 1: a walrus rebind, e.g. `if (p := source_dir /
        "leak.md"):`, must take effect before a write-shaped call elsewhere
        in the *same* expression is judged safe, and `ast.walk`'s traversal
        order does not otherwise guarantee that): first, every `NamedExpr`
        (`:=`) rebinds its target exactly as `_apply_single_target` would;
        only then is every call in the expression audited against the
        now-current `derived`/`containers` state."""
        if expr is None:
            return
        for node in ast.walk(expr):
            if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                self._apply_single_target(node.target, node.value, derived, containers)
        for node in ast.walk(expr):
            if not isinstance(node, ast.Call):
                continue
            found = self._write_call_target(node)
            if found is None:
                continue
            target, label = found
            if target is None or not self._is_safe_root(target, derived, containers):
                self._offenders.append(
                    f"{label} target not traceable to a layout helper"
                )

    # -- statement-level, order-sensitive walk ------------------------------

    def _walk_body(
        self, stmts: list[ast.stmt], derived: set[str], containers: set[str]
    ) -> None:
        for stmt in stmts:
            self._walk_stmt(stmt, derived, containers)

    def _walk_stmt(
        self, stmt: ast.stmt, derived: set[str], containers: set[str]
    ) -> None:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            # A nested function gets its own fresh scope -- see the class
            # docstring's cross-function control. `function_node=stmt` seeds
            # `_atomic_write`'s own first-parameter trust when this is that
            # function (round-2 review fix, item 2's own dispatch point).
            self._walk_scope(stmt.body, function_node=stmt)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.ClassDef):
            # A class body is its own fresh scope too (round-2 review fix,
            # item 2): a method inside it dispatches through the
            # `FunctionDef` branch above, on its own next fresh scope; any
            # class-body-level statement is audited directly here.
            self._walk_scope(stmt.body, function_node=None)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.If):
            self._scan_expr(stmt.test, derived, containers)
            self._walk_body(stmt.body, derived, containers)
            self._walk_body(stmt.orelse, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.For | ast.AsyncFor):
            self._scan_expr(stmt.iter, derived, containers)
            self._apply_for_target(stmt, derived, containers)
            self._walk_body(stmt.body, derived, containers)
            self._walk_body(stmt.orelse, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.While):
            self._scan_expr(stmt.test, derived, containers)
            self._walk_body(stmt.body, derived, containers)
            self._walk_body(stmt.orelse, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.Try | ast.TryStar):
            # `TryStar` (`except*`) has exactly `Try`'s own fields (round-3
            # review fix, item 1) -- held to the same rule.
            self._walk_body(stmt.body, derived, containers)
            for handler in stmt.handlers:
                # Round-4 review fix, item 1: `handler.type` (the exception
                # type expression) was previously never scanned. Round-4
                # review fix, item 2: `handler.name` (`except E as p:`)
                # names a fresh exception object every call -- never a
                # layout-helper path -- so it is discarded, the same sound
                # default every other binding form uses, before the
                # handler's own body is walked.
                if handler.type is not None:
                    self._scan_expr(handler.type, derived, containers)
                if handler.name is not None:
                    derived.discard(handler.name)
                    containers.discard(handler.name)
                self._walk_body(handler.body, derived, containers)
            self._walk_body(stmt.orelse, derived, containers)
            self._walk_body(stmt.finalbody, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.With | ast.AsyncWith):
            for item in stmt.items:
                self._scan_expr(item.context_expr, derived, containers)
                self._apply_with_item(item, derived, containers)
            self._walk_body(stmt.body, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.Assign):
            self._scan_expr(stmt.value, derived, containers)
            for target in stmt.targets:
                self._apply_single_target(target, stmt.value, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.AnnAssign):
            # Round-4 review fix, item 1: `annotation` was previously never
            # scanned.
            self._scan_expr(stmt.annotation, derived, containers)
            # Round-2 review fix, item 1: a re-annotated rebind
            # (`p: Path = source_dir / "leak.md"`) is held to the same
            # rule `Assign` is -- an annotation-only statement (no `value`)
            # binds nothing at runtime, so it needs no state update at all.
            if stmt.value is not None:
                self._scan_expr(stmt.value, derived, containers)
                self._apply_single_target(stmt.target, stmt.value, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.AugAssign):
            # Round-2 review fix, item 1: `p /= "../../plans/leak.md"`
            # rebinds `p` to a value this audit cannot reason about at all
            # (it never understands what `/=`, `+=`, etc. actually compute)
            # -- the sound default is to discard, never to leave a
            # previously-derived name derived through an operator this
            # walker does not model.
            self._scan_expr(stmt.value, derived, containers)
            if isinstance(stmt.target, ast.Name):
                derived.discard(stmt.target.id)
                containers.discard(stmt.target.id)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.Expr):
            self._scan_expr(stmt.value, derived, containers)
            self._apply_append(stmt.value, derived, containers)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.Delete):
            # Round-2 review fix, item 1: `del p` -- the sound default,
            # discard.
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    derived.discard(target.id)
                    containers.discard(target.id)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.Global | ast.Nonlocal):
            # Round-2 review fix, item 1: a name reintroduced from an outer
            # scope is never something this per-function analysis derived
            # itself -- discard.
            for name in stmt.names:
                derived.discard(name)
                containers.discard(name)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        if isinstance(stmt, ast.Import | ast.ImportFrom):
            # Round-3 review fix, item 2: a name (re)bound by an import
            # statement inside a scope is never something this analysis
            # derived itself -- discard, the sound default every other
            # binding form above uses. `alias.asname` when aliased, else
            # the first dotted component of `alias.name` (`import a.b.c`
            # binds the top-level name `a` in the importing scope, exactly
            # as `_os_module_names` already accounts for with `import
            # os.path`).
            for alias in stmt.names:
                name = alias.asname or alias.name.split(".")[0]
                derived.discard(name)
                containers.discard(name)
            self._delegate_remaining_fields(stmt, derived, containers)
            return
        # Every statement kind this walker does not specifically model --
        # `Return`, `Raise`, `Assert`, `Pass`, `Break`, `Continue`,
        # `ast.Match` (whose `cases` carry a nested statement list per
        # case, handled by `_walk_field_value`'s own `match_case` branch),
        # and any future statement kind a later Python version adds -- is
        # walked through the fully GENERIC fallthrough below, which is
        # `_delegate_remaining_fields` with nothing pre-consumed: the exact
        # same mechanism every explicitly modelled branch above now falls
        # back on for whatever it didn't consume itself (round-4 review
        # fix, item 1 -- previously a separate, narrower `_walk_generic`
        # existed only for this fallthrough case, so an explicit branch's
        # own *unconsumed* fields had no equivalent path to reach it at
        # all).
        self._delegate_remaining_fields(stmt, derived, containers)

    def _delegate_remaining_fields(
        self, stmt: ast.stmt, derived: set[str], containers: set[str]
    ) -> None:
        """Walk every field of `stmt` **not** named in `_CONSUMED_FIELDS`
        for its own type, generically, via `ast.iter_fields` (round-4
        review fix, item 1's "no field is silently skipped" rule): every
        caller -- every explicit branch in `_walk_stmt`, and `_walk_stmt`'s
        own final fallthrough with an empty consumed set -- routes through
        this one method, so a decorator, a parameter default or
        annotation, a class base or keyword, an `except` clause's type, or
        any field of any statement kind this walker does not explicitly
        name is still walked rather than silently dropped because a branch
        `return`ed before reaching it. `_CONSUMED_FIELDS.get(type(stmt),
        frozenset())` is empty for every statement kind with no dedicated
        branch (so every one of its fields is delegated) and, for a kind
        that class DOES special-case, empty for its own no-op fields
        (an identifier, `None`, an operator enum) which
        `_walk_field_value` would ignore anyway."""
        consumed = _CONSUMED_FIELDS.get(type(stmt), frozenset())
        for name, value in ast.iter_fields(stmt):
            if name in consumed:
                continue
            self._walk_field_value(value, derived, containers)

    def _walk_field_value(
        self, value: object, derived: set[str], containers: set[str]
    ) -> None:
        """Walk one field's value generically, dispatching on its own
        runtime type rather than on which statement or field it came from
        -- the single mechanism `_delegate_remaining_fields` uses for every
        unconsumed field of every statement kind (round-4 review fix, item
        1)."""
        if value is None:
            return
        if isinstance(value, ast.expr):
            self._scan_expr(value, derived, containers)
        elif isinstance(value, ast.arguments):
            # `FunctionDef`/`AsyncFunctionDef.args` -- every parameter
            # annotation and every positional/keyword default, scanned in
            # the *enclosing* scope (Python evaluates both at `def`-time,
            # before the function body ever runs).
            self._scan_arguments(value, derived, containers)
        elif isinstance(value, ast.keyword):
            # A `ClassDef.keywords` entry (`class Foo(metaclass=Meta):`).
            self._scan_expr(value.value, derived, containers)
        elif isinstance(value, ast.withitem):
            self._scan_expr(value.context_expr, derived, containers)
            self._apply_with_item(value, derived, containers)
        elif isinstance(value, ast.stmt):
            self._walk_stmt(value, derived, containers)
        elif isinstance(value, ast.match_case):
            # Round-4 review fix, item 2: the pattern's own captures
            # (`MatchAs.name`, `MatchStar.name`, `MatchMapping.rest`) are
            # discarded before `guard` and `body` are walked, since guard
            # and body both run *after* the pattern has bound them.
            self._discard_match_pattern_captures(value.pattern, derived, containers)
            self._scan_expr(value.guard, derived, containers)
            self._walk_body(value.body, derived, containers)
        elif isinstance(value, list):
            for item in value:
                self._walk_field_value(item, derived, containers)
        # else: an identifier (`str`), a constant, an operator enum, or
        # some other non-node value -- nothing to walk.

    def _scan_arguments(
        self, args: ast.arguments, derived: set[str], containers: set[str]
    ) -> None:
        """Every expression `ast.arguments` carries: each positional-only,
        positional-or-keyword, keyword-only, `*args` and `**kwargs`
        parameter's own `annotation`, and every positional and keyword
        default value -- all evaluated in the *enclosing* scope at
        `def`-time (round-4 review fix, item 1)."""
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            if arg.annotation is not None:
                self._scan_expr(arg.annotation, derived, containers)
        if args.vararg is not None and args.vararg.annotation is not None:
            self._scan_expr(args.vararg.annotation, derived, containers)
        if args.kwarg is not None and args.kwarg.annotation is not None:
            self._scan_expr(args.kwarg.annotation, derived, containers)
        for default in args.defaults:
            self._scan_expr(default, derived, containers)
        for kw_default in args.kw_defaults:
            if kw_default is not None:
                self._scan_expr(kw_default, derived, containers)

    def _discard_match_pattern_captures(
        self, pattern: ast.pattern, derived: set[str], containers: set[str]
    ) -> None:
        """Recursively discard every name a `match` pattern captures
        (round-4 review fix, item 2): `MatchAs.name` (`case x:`, `case
        Point() as p:`), `MatchStar.name` (`case [*rest]:`) and
        `MatchMapping.rest` (`case {**rest}:`) each bind a name in the
        case's own scope exactly as an assignment target does, and this
        audit does not reason about what a match pattern actually
        captures -- the sound default, as for every other binding form, is
        to discard. Recurses through `MatchOr`/`MatchSequence`/
        `MatchClass`/nested `MatchAs` sub-patterns; `MatchValue`,
        `MatchSingleton` and the bare wildcard `case _:` (`MatchAs` with
        `pattern=None, name=None`) bind nothing."""
        if isinstance(pattern, ast.MatchAs):
            if pattern.name is not None:
                derived.discard(pattern.name)
                containers.discard(pattern.name)
            if pattern.pattern is not None:
                self._discard_match_pattern_captures(
                    pattern.pattern, derived, containers
                )
        elif isinstance(pattern, ast.MatchStar):
            if pattern.name is not None:
                derived.discard(pattern.name)
                containers.discard(pattern.name)
        elif isinstance(pattern, ast.MatchMapping):
            if pattern.rest is not None:
                derived.discard(pattern.rest)
                containers.discard(pattern.rest)
            for sub_pattern in pattern.patterns:
                self._discard_match_pattern_captures(sub_pattern, derived, containers)
        elif isinstance(pattern, ast.MatchOr | ast.MatchSequence):
            for sub_pattern in pattern.patterns:
                self._discard_match_pattern_captures(sub_pattern, derived, containers)
        elif isinstance(pattern, ast.MatchClass):
            for sub_pattern in pattern.patterns:
                self._discard_match_pattern_captures(sub_pattern, derived, containers)
            for sub_pattern in pattern.kwd_patterns:
                self._discard_match_pattern_captures(sub_pattern, derived, containers)

    def _apply_single_target(
        self,
        target: ast.expr,
        value: ast.expr,
        derived: set[str],
        containers: set[str],
    ) -> None:
        """Apply one assignment's effect on `derived`/`containers` for a
        single target expression -- shared by `Assign` (once per target,
        supporting `a = b = value`) and `AnnAssign`. The **sound default**
        (round-2 review fix, item 1): a `Name` target not satisfying any
        derivation rule below is *discarded*, never left derived from an
        earlier, unrelated assignment; a non-`Name`/`Tuple`/`List` target
        (an `Attribute` or `Subscript`, e.g. `self.x = ...`) binds no local
        name at all and is left alone."""
        if isinstance(target, ast.Name):
            if self._is_safe_root(value, derived, containers):
                derived.add(target.id)
                containers.discard(target.id)
            elif self._dict_values_all_safe(value, derived, containers):
                containers.add(target.id)
                derived.discard(target.id)
            else:
                # An unsafe value rebinds a previously-derived name away
                # from safety (round-1 review fix, item 3).
                derived.discard(target.id)
                containers.discard(target.id)
            return
        if isinstance(target, ast.Tuple | ast.List):
            self._apply_tuple_target(target, value, derived, containers)

    def _discard_names_in(
        self, target: ast.expr, derived: set[str], containers: set[str]
    ) -> None:
        """Recursively discard every `Name` bound inside `target` -- covers
        an arbitrarily nested tuple/list/starred target (`for p, (q, r) in
        ...`, `with cm as (p, q):`), used by `_apply_for_target`,
        `_apply_with_item` and `_apply_tuple_target`'s own non-`mkstemp`
        elements (round-3 review fix, item 2: a tuple/list for-target or
        with-target previously received *no* state update at all, so a
        previously-derived name reused there stayed derived forever)."""
        if isinstance(target, ast.Name):
            derived.discard(target.id)
            containers.discard(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            for element in target.elts:
                self._discard_names_in(element, derived, containers)
        elif isinstance(target, ast.Starred):
            self._discard_names_in(target.value, derived, containers)

    def _apply_tuple_target(
        self,
        target: ast.Tuple | ast.List,
        value: ast.expr,
        derived: set[str],
        containers: set[str],
    ) -> None:
        """`fd, tmp_name = tempfile.mkstemp(dir=directory, ...)` -- the temp
        file's own name is derived when the directory it was created in is;
        every *other* element (round-2 review fix, item 1: previously only
        `elts[1]` was ever discarded, so a name reused as `elts[0]` -- e.g.
        `fd` -- that happened to already be derived from earlier code
        stayed derived forever, even though this statement rebinds it to an
        unrelated value, a file descriptor, never a path) is discarded via
        `_discard_names_in`, recursively -- round-3 review fix, item 2:
        covers a nested tuple/list element too (`(a, (b, c)) = value`),
        not only a bare `Name` element."""
        derived_second: ast.Name | None = None
        if len(target.elts) == 2:
            first, second = target.elts
            if (
                isinstance(second, ast.Name)
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "mkstemp"
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id == "tempfile"
            ):
                dir_keyword = next(
                    (kw for kw in value.keywords if kw.arg == "dir"), None
                )
                if dir_keyword is not None and self._is_safe_root(
                    dir_keyword.value, derived, containers
                ):
                    derived.add(second.id)
                    containers.discard(second.id)
                    derived_second = second
        for element in target.elts:
            if element is not derived_second:
                self._discard_names_in(element, derived, containers)

    def _apply_with_item(
        self, item: ast.withitem, derived: set[str], containers: set[str]
    ) -> None:
        """`with <context_expr> as <optional_vars>:` -- round-2 review fix,
        item 1: `optional_vars` previously received no state update at all,
        so `with open(...) as p:` left a *previously*-derived `p` still
        derived even though it is now bound to a file object, never a
        path. A `Name` target is held to the same rule `_apply_single_target`
        uses: derived only when `context_expr` is itself safe, discarded
        otherwise. A tuple/list target (`with cm as (p, q):`, round-3
        review fix, item 2 -- previously left entirely unhandled) is never
        analyzed for derivation at all -- discard every name it binds."""
        if isinstance(item.optional_vars, ast.Name):
            self._apply_single_target(
                item.optional_vars, item.context_expr, derived, containers
            )
        elif item.optional_vars is not None:
            self._discard_names_in(item.optional_vars, derived, containers)

    def _apply_append(
        self, expr: ast.expr, derived: set[str], containers: set[str]
    ) -> None:
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "append"
            and isinstance(expr.func.value, ast.Name)
            and expr.args
            and self._is_safe_root(expr.args[0], derived, containers)
        ):
            containers.add(expr.func.value.id)

    def _apply_for_target(
        self,
        stmt: ast.For | ast.AsyncFor,
        derived: set[str],
        containers: set[str],
    ) -> None:
        if not isinstance(stmt.target, ast.Name):
            # Round-3 review fix, item 2: a tuple/list for-target (`for p,
            # q in ...`) was previously never analyzed at all (an early
            # `return`) -- discard every name it binds, the same sound
            # default every other unmodelled binding form uses.
            self._discard_names_in(stmt.target, derived, containers)
            return
        loop_var = stmt.target.id
        iterable = stmt.iter
        # `sorted(x, key=...)` iterates the same elements `x` does --
        # unwrap it before classifying the source (`for child in
        # sorted(pages_dir.iterdir(), key=...)`).
        if (
            isinstance(iterable, ast.Call)
            and isinstance(iterable.func, ast.Name)
            and iterable.func.id == "sorted"
            and iterable.args
        ):
            iterable = iterable.args[0]
        source_is_derived = False
        if isinstance(iterable, ast.Name):
            source_is_derived = iterable.id in containers or iterable.id in derived
        elif isinstance(iterable, ast.Call) and isinstance(
            iterable.func, ast.Attribute
        ):
            receiver = iterable.func.value
            if iterable.func.attr in ("iterdir", "values"):
                source_is_derived = self._is_safe_root(
                    receiver, derived, containers
                ) or (isinstance(receiver, ast.Name) and receiver.id in containers)
        if source_is_derived:
            derived.add(loop_var)
        else:
            derived.discard(loop_var)


def _engine_source_tree() -> ast.Module:
    return _module_ast(_ENGINE_MODULE)


class TestEngineWriteTargetsTraceToLayoutHelpers:
    def test_every_write_call_in_engine_resolves_to_a_layout_helper(self) -> None:
        """The real `plans/engine.py`: every write-shaped call's target
        traces to a layout helper -- including every `_atomic_write(...)`
        call *site*, since `_write_call_target` treats it as a write-shaped
        call in its own right with its first argument as the target (the
        old, separate call-site test is folded into this single assertion:
        a call site with an untraceable argument shows up here exactly as a
        direct `.write_text()` with one would)."""
        audit = _EngineWriteTargetAudit(_engine_source_tree())
        assert audit.offenders() == []

    def test_a_synthetic_engine_style_write_from_the_source_directory_is_caught(
        self,
    ) -> None:
        """Positive control, and the required named mutation
        ("make the engine write `source_dir / 'x.md'`"): a write whose
        target is built directly from a `source_dir`-shaped name, never
        passed through a layout helper, is caught -- proving the audit
        catches the shape of write this task names, independent of what
        `engine.py` currently contains."""
        synthetic = ast.parse(
            "from pathlib import Path\n"
            "\n"
            "def leak(source_dir: Path) -> None:\n"
            '    stray = source_dir / "x.md"\n'
            '    stray.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(synthetic)
        assert audit.offenders() != [], (
            "a write target built directly from source_dir was not caught"
        )

    def test_a_write_composed_from_block_doc_path_is_not_flagged(self) -> None:
        """Negative control: the real shape (`block_doc_path(...)` feeding a
        write) is not flagged -- otherwise this guard would be vacuous."""
        synthetic = ast.parse(
            "from pathlib import Path\n"
            "\n"
            "def write(data_root: Path, block_id: str) -> None:\n"
            "    target = block_doc_path(data_root, block_id)\n"
            '    target.write_text("ok", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(synthetic)
        assert audit.offenders() == []

    def test_a_rebind_to_an_unsafe_value_after_a_safe_one_is_caught(self) -> None:
        """Round-1 review fix, item 3: a name derived from a layout helper
        and then *rebound* to something unsafe before the write must still
        be flagged -- the previous module-wide fixed-point pass only ever
        added names to `derived` and treated a first safe assignment as
        permanent, so this rebind sailed through it."""
        synthetic = ast.parse(
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str, source_dir: Path) -> None:\n"
            "    target = block_doc_path(data_root, block_id)\n"
            '    target = source_dir / "leak.md"\n'
            '    target.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(synthetic)
        assert audit.offenders() != [], (
            "a rebind to an unsafe value after a safe one was not caught"
        )

    def test_a_rebind_to_a_safe_value_after_an_unsafe_one_is_not_flagged(self) -> None:
        """Negative control for the rebind rule: the reverse order (unsafe,
        then safe) must *not* be flagged, proving the rule tracks the
        current value rather than merely poisoning a name for good once any
        unsafe assignment touches it."""
        synthetic = ast.parse(
            "from pathlib import Path\n"
            "\n"
            "def write(data_root: Path, block_id: str, source_dir: Path) -> None:\n"
            '    target = source_dir / "unused.md"\n'
            "    target = block_doc_path(data_root, block_id)\n"
            '    target.write_text("ok", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(synthetic)
        assert audit.offenders() == []

    def test_a_new_function_reusing_another_functions_derived_name_is_caught(
        self,
    ) -> None:
        """Round-1 review fix, item 3 (round-2 review fix, item 3: the
        original version of this control was confounded -- `render`'s own
        `pages_dir` parameter was never itself derived, so `render`'s own
        `child.unlink()` was *already* an offender independent of `leak`,
        and the assertion held even with `leak` deleted entirely. Fixed by
        making `render` derive `pages_dir` legitimately, and asserting the
        offender list is *exactly* one entry, at `leak`'s own line): a name
        derived while analyzing one function proves nothing about a
        same-named local in a *different* function -- a new helper that
        reuses the name `child` from another function's own analysis must
        be audited from scratch."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def render(data_root: Path, block_id: str) -> None:\n"
            "    pages_dir = block_pages_dir(data_root, block_id)\n"
            "    for child in sorted(pages_dir.iterdir(), key=lambda e: e.name):\n"
            "        child.unlink()\n"
            "\n"
            "def leak(source_dir: Path) -> None:\n"
            '    child = source_dir / "leak.md"\n'
            "    child.unlink()\n"
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() == [
            "L10: .unlink target not traceable to a layout helper"
        ], (
            "expected exactly one offender, at leak's own unlink call -- "
            f"got {audit.offenders()!r}"
        )

    def test_an_augassign_rebind_to_an_unsafe_value_is_caught(self) -> None:
        """Round-2 review fix, item 1: `p /= "../../plans/leak.md"` must
        invalidate a previously-derived `p`, exactly as a plain `Assign`
        rebind does."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            '    p /= "../../plans/leak.md"\n'
            '    p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "an AugAssign rebind to unsafe was not caught"

    def test_an_annotated_rebind_to_an_unsafe_value_is_caught(self) -> None:
        """Round-2 review fix, item 1: `p: Path = source_dir / "leak.md"`
        rebinding a previously-derived `p` must invalidate it, exactly as
        an unannotated `Assign` rebind does."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str, source_dir: Path) -> None:\n"
            "    p: Path = block_doc_path(data_root, block_id)\n"
            '    p: Path = source_dir / "leak.md"\n'
            '    p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "an AnnAssign rebind to unsafe was not caught"

    def test_a_tuple_unpack_first_element_rebind_is_caught(self) -> None:
        """Round-2 review fix, item 1: the `tempfile.mkstemp` tuple-unpack
        special case previously discarded only `elts[1]`; a name reused as
        `elts[0]` that happened to already be derived from earlier code
        stayed derived forever, even though this statement rebinds it to an
        unrelated value (a file descriptor, never a path)."""
        source = (
            "from pathlib import Path\n"
            "import tempfile\n"
            "\n"
            "def leak(data_root: Path, block_id: str) -> None:\n"
            "    fd = block_doc_path(data_root, block_id)\n"
            "    fd, tmp_name = tempfile.mkstemp(dir=fd)\n"
            '    fd.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], (
            "a tuple-unpack first-element rebind to unsafe was not caught"
        )

    def test_a_with_as_rebind_to_an_unsafe_value_is_caught(self) -> None:
        """Round-2 review fix, item 1: `with open(...) as p:` rebinding a
        previously-derived `p` to a context manager's result (never a
        layout-helper path) must invalidate it."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str, source_dir: Path) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            "    with open(str(source_dir)) as p:\n"
            '        p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a with-as rebind to unsafe was not caught"

    def test_a_walrus_rebind_to_an_unsafe_value_is_caught(self) -> None:
        """Round-2 review fix, item 1: a walrus rebind
        (`if (p := source_dir / "leak.md"):`) must invalidate a
        previously-derived `p` before the body that uses it runs."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str, source_dir: Path) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            '    if (p := source_dir / "leak.md"):\n'
            '        p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a walrus rebind to unsafe was not caught"

    def test_a_for_tuple_target_rebind_is_caught(self) -> None:
        """Round-3 review fix, item 2: `_apply_for_target` previously
        returned early for a tuple/list for-target (`for p, q in ...`),
        leaving a previously-derived `p` still derived even though the
        loop rebinds it to an unrelated value on every iteration."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str, source_dir: Path) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            '    for p, q in [(source_dir / "leak.md", 1)]:\n'
            "        pass\n"
            '    p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() == [
            "L7: .write_text target not traceable to a layout helper"
        ]

    def test_a_with_tuple_target_rebind_is_caught(self) -> None:
        """Round-3 review fix, item 2: `_apply_with_item` previously
        handled only a bare `Name` target, leaving a previously-derived `p`
        still derived after `with cm as (p, q):` rebinds it."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            "    with make_cm() as (p, q):\n"
            '        p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() == [
            "L6: .write_text target not traceable to a layout helper"
        ]

    def test_an_import_binding_discards_a_previously_derived_name(self) -> None:
        """Round-3 review fix, item 2: an `Import`/`ImportFrom` statement
        rebinding a previously-derived name (an unusual but syntactically
        valid shadowing import) must discard it, the same sound default
        every other binding form uses."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            "    import p\n"
            '    p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "an import rebind was not caught"

    def test_a_module_level_write_is_caught(self) -> None:
        """Round-2 review fix, item 2: a write-shaped call at module level,
        never inside any function, was previously invisible to this audit
        entirely -- only top-level `FunctionDef`s were ever entered."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "if False:\n"
            '    Path("/x/leak.md").write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a module-level write was not caught"

    def test_a_class_method_write_is_caught(self) -> None:
        """Round-2 review fix, item 2: a write-shaped call inside a class
        method was previously invisible, for the same reason."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "class Leaker:\n"
            "    def leak(self, source_dir: Path) -> None:\n"
            '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a class-method write was not caught"


def _all_stmt_subclasses() -> frozenset[type[ast.stmt]]:
    """Every concrete `ast.stmt` subclass this Python version defines,
    discovered recursively via `__subclasses__()` rather than a
    hand-maintained list (round-3 review fix, item 1) -- so a future Python
    version's new statement kind reds `TestStatementKindSweep`'s own
    completeness assertion rather than silently going unaudited."""
    found: set[type[ast.stmt]] = set()
    frontier: list[type[ast.stmt]] = [ast.stmt]
    while frontier:
        current = frontier.pop()
        for subclass in current.__subclasses__():
            if subclass not in found:
                found.add(subclass)
                frontier.append(subclass)
    return frozenset(found)


#: Statement kinds that can carry a nested statement list (a "body") --
#: `_walk_stmt` either models these explicitly (`If`, `For`, `AsyncFor`,
#: `While`, `Try`, `TryStar`, `With`, `AsyncWith`, `FunctionDef`,
#: `AsyncFunctionDef`, `ClassDef`) or reaches their nested body only
#: through the generic fallthrough's `match_case` handling (`Match`).
_BODY_BEARING_STMT_KINDS: Final[frozenset[type[ast.stmt]]] = frozenset(
    {
        ast.Match,
        ast.TryStar,
        ast.Try,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    }
)

#: Statement kinds with no nested body that `_walk_stmt` models explicitly
#: because they bind or rebind a name (`Assign`, `AnnAssign`, `AugAssign`,
#: `Delete`, `Global`, `Nonlocal`, `Import`, `ImportFrom`) or drive the
#: `.append` container rule (`Expr`).
_EXPLICIT_NO_BODY_STMT_KINDS: Final[frozenset[type[ast.stmt]]] = frozenset(
    {
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.Delete,
        ast.Global,
        ast.Nonlocal,
        ast.Import,
        ast.ImportFrom,
        ast.Expr,
    }
)

#: Statement kinds with no nested body and no binding effect of their own
#: -- covered structurally by `_delegate_remaining_fields`'s generic
#: expression scan alone (no dedicated branch, nothing pre-consumed).
_GENERIC_NO_BODY_STMT_KINDS: Final[frozenset[type[ast.stmt]]] = frozenset(
    {ast.Assert, ast.Break, ast.Continue, ast.Pass, ast.Raise, ast.Return}
)

#: One synthetic module per body-bearing statement kind, each embedding an
#: unsafe write (`source_dir / "leak.md"` -> `.write_text(...)`, `source_dir`
#: never derived) inside that statement's own nested body, paired with the
#: exact one-line offender the audit must report -- proving each of these
#: 12 kinds is actually walked into, not merely a member of a registry
#: (round-3 review fix, item 1's own exhaustive sweep).
_BODY_BEARING_WRITE_SOURCES: Final[dict[type[ast.stmt], tuple[str, str]]] = {
    ast.Match: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path, k: int) -> None:\n"
        "    match k:\n"
        "        case 1:\n"
        '            (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n'
        "        case _:\n"
        "            pass\n",
        "L6",
    ),
    ast.TryStar: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path) -> None:\n"
        "    try:\n"
        "        pass\n"
        "    except* ValueError:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L7",
    ),
    ast.Try: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path) -> None:\n"
        "    try:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n'
        "    except ValueError:\n"
        "        pass\n",
        "L5",
    ),
    ast.If: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path) -> None:\n"
        "    if True:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.For: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path) -> None:\n"
        "    for _ in range(1):\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.AsyncFor: (
        "from pathlib import Path\n"
        "\n"
        "async def leak(source_dir: Path) -> None:\n"
        "    async for _ in something():\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.While: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path) -> None:\n"
        "    while True:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n'
        "        break\n",
        "L5",
    ),
    ast.With: (
        "from pathlib import Path\n"
        "\n"
        "def leak(source_dir: Path) -> None:\n"
        '    with open("x") as f:\n'
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.AsyncWith: (
        "from pathlib import Path\n"
        "\n"
        "async def leak(source_dir: Path) -> None:\n"
        "    async with make_cm() as f:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.FunctionDef: (
        "from pathlib import Path\n"
        "\n"
        "def outer(source_dir: Path) -> None:\n"
        "    def inner() -> None:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.AsyncFunctionDef: (
        "from pathlib import Path\n"
        "\n"
        "def outer(source_dir: Path) -> None:\n"
        "    async def inner() -> None:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
    ast.ClassDef: (
        "from pathlib import Path\n"
        "\n"
        "class Leaker:\n"
        "    def leak(self, source_dir: Path) -> None:\n"
        '        (source_dir / "leak.md").write_text("leak", encoding="utf-8")\n',
        "L5",
    ),
}


class TestStatementKindSweep:
    """The exhaustive sweep round-3 review demands: every concrete
    `ast.stmt` subclass Python 3.11 defines is accounted for, either by a
    dedicated branch in `_walk_stmt` or by the generic fallthrough, and --
    for the 12 kinds that can carry a nested statement list or a binding --
    proved to actually route a write buried inside that nested structure to
    exactly one offender, not merely assumed to."""

    def test_every_concrete_stmt_subclass_is_accounted_for(self) -> None:
        discovered = _all_stmt_subclasses()
        assert discovered, "the walk found no ast.stmt subclasses -- wrong Python?"
        classified = (
            _BODY_BEARING_STMT_KINDS
            | _EXPLICIT_NO_BODY_STMT_KINDS
            | _GENERIC_NO_BODY_STMT_KINDS
        )
        assert discovered == classified, (
            f"unclassified: {sorted(c.__name__ for c in discovered - classified)}; "
            f"classified but no longer a concrete ast.stmt subclass: "
            f"{sorted(c.__name__ for c in classified - discovered)}"
        )

    def test_body_bearing_sources_cover_exactly_the_registered_kinds(self) -> None:
        assert set(_BODY_BEARING_WRITE_SOURCES) == _BODY_BEARING_STMT_KINDS

    def test_a_write_nested_inside_each_body_bearing_statement_kind_is_caught(
        self,
    ) -> None:
        for kind, (source, offender_line) in _BODY_BEARING_WRITE_SOURCES.items():
            audit = _EngineWriteTargetAudit(ast.parse(source))
            offenders = audit.offenders()
            assert len(offenders) == 1 and offenders[0].startswith(
                f"{offender_line}:"
            ), (
                f"{kind.__name__}: expected exactly one offender at "
                f"{offender_line} -- got {offenders!r}"
            )

    def test_the_three_classification_sets_are_pairwise_disjoint(self) -> None:
        """Round-4 review fix, item 3: nothing previously asserted the
        three sets partition `_all_stmt_subclasses()` *without overlap* --
        adding `ast.Match` to a second set alongside its real home in
        `_BODY_BEARING_STMT_KINDS` left
        `test_every_concrete_stmt_subclass_is_accounted_for` green, since a
        union does not notice a member counted twice."""
        pairs = (
            (_BODY_BEARING_STMT_KINDS, _EXPLICIT_NO_BODY_STMT_KINDS),
            (_BODY_BEARING_STMT_KINDS, _GENERIC_NO_BODY_STMT_KINDS),
            (_EXPLICIT_NO_BODY_STMT_KINDS, _GENERIC_NO_BODY_STMT_KINDS),
        )
        for left, right in pairs:
            overlap = left & right
            assert not overlap, (
                f"not pairwise disjoint: {sorted(c.__name__ for c in overlap)}"
            )


# --------------------------------------------------------------------------- #
# Layer 4c: field coverage -- no field of a modelled statement is skipped
# --------------------------------------------------------------------------- #


class TestFieldCoverageSweep:
    """Round-4 review fix, item 1's own mechanical proof: for every
    statement kind `_walk_stmt` models with a dedicated branch,
    `_CONSUMED_FIELDS`, `_IDENTIFIER_OR_SIMPLE_FIELDS` and
    `_DELEGATED_NODE_FIELDS` -- three independently hand-written sets --
    partition `kind._fields` exactly, so a field left out of all three
    reds here; the six positive controls below then prove specific fields
    the round-4 review named by example are genuinely reached at runtime,
    not merely accounted for on paper."""

    def test_the_three_field_sets_partition_every_kinds_fields_exactly(self) -> None:
        scanned = 0
        for kind, consumed in _CONSUMED_FIELDS.items():
            scanned += 1
            all_fields = frozenset(kind._fields)
            simple = _IDENTIFIER_OR_SIMPLE_FIELDS.get(kind, frozenset())
            delegated = _DELEGATED_NODE_FIELDS.get(kind, frozenset())
            assert consumed <= all_fields, (
                f"{kind.__name__}: _CONSUMED_FIELDS names a field that "
                f"doesn't exist: {consumed - all_fields}"
            )
            assert simple <= all_fields, (
                f"{kind.__name__}: _IDENTIFIER_OR_SIMPLE_FIELDS names a "
                f"field that doesn't exist: {simple - all_fields}"
            )
            assert delegated <= all_fields, (
                f"{kind.__name__}: _DELEGATED_NODE_FIELDS names a field "
                f"that doesn't exist: {delegated - all_fields}"
            )
            assert not (consumed & simple), (
                f"{kind.__name__}: field(s) in both consumed and simple: "
                f"{consumed & simple}"
            )
            assert not (consumed & delegated), (
                f"{kind.__name__}: field(s) in both consumed and "
                f"delegated: {consumed & delegated}"
            )
            assert not (simple & delegated), (
                f"{kind.__name__}: field(s) in both simple and delegated: "
                f"{simple & delegated}"
            )
            unaccounted = sorted(all_fields - consumed - simple - delegated)
            assert consumed | simple | delegated == all_fields, (
                f"{kind.__name__}: {unaccounted} accounted for by none of "
                "the three sets"
            )
        assert scanned == len(_CONSUMED_FIELDS), "the walk is looking at the wrong set"

    def test_a_decorator_argument_write_is_caught(self) -> None:
        """Round-4 review fix, item 1: `decorator_list` was never scanned
        -- a write buried in a decorator expression was invisible."""
        source = (
            "from pathlib import Path\n"
            "\n"
            '@Path("/x/leak.md").write_text("leak", encoding="utf-8")\n'
            "def leak() -> None:\n"
            "    pass\n"
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a decorator-argument write was not caught"

    def test_a_parameter_default_write_is_caught(self) -> None:
        """Round-4 review fix, item 1: `args.defaults` (and, by the same
        `_scan_arguments` mechanism, every parameter's own `annotation`)
        was never scanned -- a write hidden in a default value expression
        was invisible, exactly the round-4 review's own named mutation
        (`def _leak(..., w=lambda d: (d / "leak.md").write_text("x")):`)."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(\n"
            '    w: Path = Path("/x/leak.md").write_text("leak", encoding="utf-8"),\n'
            ") -> None:\n"
            "    pass\n"
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a parameter-default write was not caught"

    def test_a_class_base_write_is_caught(self) -> None:
        """Round-4 review fix, item 1: `ClassDef.bases`/`keywords` were
        never scanned."""
        source = (
            "from pathlib import Path\n"
            "\n"
            'class Leaker(Path("/x/leak.md").write_text("leak", encoding="utf-8")):\n'
            "    pass\n"
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a class-base write was not caught"

    def test_an_except_type_write_is_caught(self) -> None:
        """Round-4 review fix, item 1: `ExceptHandler.type` was never
        scanned."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak() -> None:\n"
            "    try:\n"
            "        pass\n"
            '    except Path("/x/leak.md").write_text("leak", encoding="utf-8"):\n'
            "        pass\n"
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "an except-type write was not caught"

    def test_an_except_as_binding_discards_a_previously_derived_name(self) -> None:
        """Round-4 review fix, item 2: `except E as p:` rebinds `p` to a
        fresh exception object every time -- never a layout-helper path --
        so a previously-derived `p` must be discarded before the handler's
        own body is walked."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError as p:\n"
            '        p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "an except-as rebind was not caught"

    def test_a_match_capture_pattern_discards_a_previously_derived_name(self) -> None:
        """Round-4 review fix, item 2: a bare `match` capture pattern
        (`case p:`) rebinds `p` to whatever the subject was, never a
        layout-helper path -- must be discarded before the case `body` is
        walked."""
        source = (
            "from pathlib import Path\n"
            "\n"
            "def leak(data_root: Path, block_id: str, k: int) -> None:\n"
            "    p = block_doc_path(data_root, block_id)\n"
            "    match k:\n"
            "        case p:\n"
            '            p.write_text("leak", encoding="utf-8")\n'
        )
        audit = _EngineWriteTargetAudit(ast.parse(source))
        assert audit.offenders() != [], "a match capture-pattern rebind was not caught"


# --------------------------------------------------------------------------- #
# Layer 5: reverse reachability -- nothing outside the package reaches in
# --------------------------------------------------------------------------- #

_PACKAGE_ROOT: Final[Path] = Path(fitdocs.__file__).resolve().parent


def _module_name_for_path(path: Path) -> str:
    rel = path.relative_to(_PACKAGE_ROOT)
    if rel.name == "__init__.py":
        parts = rel.parts[:-1]
        return "fitdocs" + ("." + ".".join(parts) if parts else "")
    return "fitdocs." + ".".join(rel.with_suffix("").parts)


def _reachability_targets() -> tuple[Path, ...]:
    """Every file this layer must scan: every module under
    `src/fitdocs/load/`, `src/fitdocs/ingest/` and `src/fitdocs/history/`,
    plus `render/views.py`, `sync.py` and `audit.py` -- discovered by
    walking the directories, not a hand-maintained list."""
    load_paths = tuple(sorted((_PACKAGE_ROOT / "load").rglob("*.py")))
    ingest_paths = tuple(sorted((_PACKAGE_ROOT / "ingest").rglob("*.py")))
    history_paths = tuple(sorted((_PACKAGE_ROOT / "history").rglob("*.py")))
    assert load_paths and ingest_paths and history_paths, (
        "the walk is looking at the wrong directory -- "
        f"load_paths={len(load_paths)}, ingest_paths={len(ingest_paths)}, "
        f"history_paths={len(history_paths)}"
    )
    named_paths = (
        _PACKAGE_ROOT / "render" / "views.py",
        _PACKAGE_ROOT / "sync.py",
        _PACKAGE_ROOT / "audit.py",
    )
    return load_paths + ingest_paths + history_paths + named_paths


def _plans_import_violations(
    source: str, *, anchor: str, filename: str = "<test>"
) -> list[str]:
    """Every way `source` -- a module whose enclosing package is `anchor`
    -- could import `fitdocs.plans`: a bare `import fitdocs.plans` (or any
    dotted submodule of it, under any `as` alias), a `from fitdocs.plans
    import x` / `from fitdocs.plans.x import y`, a package-level from-import
    (`from fitdocs import plans`, aliased or not), or a relative form
    resolved via `importlib.util.resolve_name` against `anchor` -- the same
    candidate-list construction
    `tests/history/test_boundary.py::_history_import_violations` uses,
    adopted rather than re-derived."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fitdocs.plans" or alias.name.startswith(
                    "fitdocs.plans."
                ):
                    spelling = f"import {alias.name}"
                    if alias.asname:
                        spelling += f" as {alias.asname}"
                    violations.append(f"L{node.lineno}: {spelling}")
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_from(node, anchor)
            if resolved is None:
                continue
            candidates = [
                resolved,
                *(f"{resolved}.{alias.name}" for alias in node.names),
            ]
            for candidate in candidates:
                if candidate == "fitdocs.plans" or candidate.startswith(
                    "fitdocs.plans."
                ):
                    names = ", ".join(alias.name for alias in node.names)
                    dots = "." * node.level
                    spelled_module = dots + (node.module or "")
                    violations.append(
                        f"L{node.lineno}: from {spelled_module} import {names} "
                        f"(resolves to {candidate})"
                    )
                    break
    return violations


def _imports_plans(path: Path) -> str | None:
    module_name = _module_name_for_path(path)
    enclosing = (
        module_name.rsplit(".", 1)[0] if path.name != "__init__.py" else module_name
    )
    violations = _plans_import_violations(
        path.read_text(encoding="utf-8"), anchor=enclosing, filename=str(path)
    )
    return violations[0] if violations else None


class TestReverseReachability:
    def test_nothing_outside_the_package_imports_fitdocs_plans(self) -> None:
        targets = _reachability_targets()
        assert targets, "the walk found no files -- wrong path list"
        offenders: list[str] = []
        for path in targets:
            spelling = _imports_plans(path)
            if spelling is not None:
                offenders.append(f"{path}: {spelling}")
        assert not offenders, offenders


class TestReverseReachabilitySyntheticControls:
    """Positive and negative controls for `_plans_import_violations` against
    synthetic source, independent of what the real tree currently contains
    -- these close the gap the real-file scan above cannot: it only ever
    proves today's shipped code has no violation, never that the scan would
    catch one if it appeared."""

    def test_absolute_import_is_caught(self) -> None:
        offenders = _plans_import_violations(
            "import fitdocs.plans\n", anchor="fitdocs.load.channels.heart_rate"
        )
        assert offenders != [], "import fitdocs.plans was not caught"

    def test_aliased_whole_module_import_is_caught(self) -> None:
        offenders = _plans_import_violations(
            "import fitdocs.plans as p\n", anchor="fitdocs"
        )
        assert offenders != [], "aliased whole-module import was not caught"

    def test_package_level_from_import_is_caught(self) -> None:
        offenders = _plans_import_violations(
            "from fitdocs import plans\n", anchor="fitdocs.render"
        )
        assert offenders != [], "from fitdocs import plans was not caught"

    def test_package_level_from_import_aliased_is_caught(self) -> None:
        offenders = _plans_import_violations(
            "from fitdocs import plans as p\n", anchor="fitdocs"
        )
        assert offenders != [], "from fitdocs import plans as p was not caught"

    def test_submodule_from_import_is_caught(self) -> None:
        offenders = _plans_import_violations(
            "from fitdocs.plans import model\n", anchor="fitdocs.load.engine"
        )
        assert offenders != [], "from fitdocs.plans import model was not caught"

    def test_relative_import_is_caught_from_a_leaf_modules_own_anchor(self) -> None:
        anchor = "fitdocs.load"
        assert importlib.util.resolve_name("..plans", anchor) == "fitdocs.plans"
        offenders = _plans_import_violations(
            "from ..plans import model\n", anchor=anchor
        )
        assert offenders != [], "relative import from a leaf module was not caught"

    def test_relative_import_is_caught_from_an_init_modules_own_anchor(self) -> None:
        anchor = "fitdocs.load"
        assert importlib.util.resolve_name("..plans", anchor) == "fitdocs.plans"
        offenders = _plans_import_violations("from .. import plans\n", anchor=anchor)
        assert offenders != [], "relative import from an __init__ module was not caught"

    def test_unrelated_relative_import_is_not_flagged(self) -> None:
        anchor = "fitdocs.load"
        assert importlib.util.resolve_name(".settings", anchor) == (
            "fitdocs.load.settings"
        )
        offenders = _plans_import_violations(
            "from .settings import load_load_settings\n", anchor=anchor
        )
        assert offenders == []


# --------------------------------------------------------------------------- #
# Layer 6: the contract-importer pin (widens to three by `plan-resolution`)
# --------------------------------------------------------------------------- #

#: Per importer, the exact set of names it from-imports from
#: `fitdocs.contract` -- an equality pin, not merely "imports the module at
#: all" (round-1 review fix, item 8): an extra `from fitdocs.contract import
#: GENERATOR, is_generated` added to `engine.py` (which already legitimately
#: imports `is_generated`) previously satisfied the module-level pin below
#: (still exactly `{page, engine}` import the module) while silently
#: widening what `engine.py` binds beyond what
#: `tests/test_contract_consumers.py::CONTRACT_BINDINGS` registers for it.
#: Written as a dict so `plan-resolution`'s `corpus` entry is one added key.
_CONTRACT_FROM_IMPORT_NAMES: Final[dict[str, frozenset[str]]] = {
    "fitdocs.plans.page": frozenset(
        {
            "DATE_KEY",
            "DOC_BANNER",
            "FRONTMATTER_FENCE",
            "GENERATOR",
            "GENERATOR_KEY",
            "INDOOR_KEY",
            "MODALITY_KEY",
            "TYPE_KEY",
            "NOTES_REGION",
            "NOTES_PLACEHOLDER",
            "SPORT_KEY",
        }
    ),
    "fitdocs.plans.engine": frozenset({"is_generated"}),
}


def _contract_from_import_names(module_name: str) -> frozenset[str]:
    """Every name `module_name` from-imports from `fitdocs.contract`,
    keyed by the *source* name in the contract (an aliased import such as
    `from fitdocs.contract import GENERATOR as G` still counts as
    importing `GENERATOR`, not `G`)."""
    tree = _module_ast(module_name)
    enclosing = _enclosing_package(module_name)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_from(node, enclosing)
            if resolved == "fitdocs.contract":
                for alias in node.names:
                    names.add(alias.name)
    return frozenset(names)


class TestContractImporters:
    def test_exactly_page_and_engine_import_fitdocs_contract(self) -> None:
        importers = {
            module_name
            for module_name in PLANS_MODULE_NAMES
            if "fitdocs.contract" in _import_targets(module_name)
        }
        assert importers == set(_CONTRACT_FROM_IMPORT_NAMES)

    def test_each_contract_importer_binds_exactly_its_registered_names(self) -> None:
        """Round-1 review fix, item 8: not merely "imports the module", but
        binds *exactly* the names `tests/test_contract_consumers.py::CONTRACT_BINDINGS`
        registers for it -- no more, no less."""
        for module_name, expected in _CONTRACT_FROM_IMPORT_NAMES.items():
            measured = _contract_from_import_names(module_name)
            assert measured == expected, (
                f"{module_name}: measured contract from-imports "
                f"{sorted(measured)} != registered {sorted(expected)}"
            )


# --------------------------------------------------------------------------- #
# Layer 7: no bare region-id literal (3.1 reviewer follow-up)
# --------------------------------------------------------------------------- #


class TestNoBareRegionIdLiteral:
    def test_no_module_spells_a_preserved_region_id_itself(self) -> None:
        offenders: dict[str, list[str]] = {}
        for module_name in PLANS_MODULE_NAMES:
            tree = _module_ast(module_name)
            spelled = sorted(
                {
                    node.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value in fitdocs.contract.PRESERVED_REGIONS
                }
            )
            if spelled:
                offenders[module_name] = spelled
        assert not offenders, (
            f"the plans package spells region ids itself ({offenders}); "
            "import NOTES_REGION from fitdocs.contract instead"
        )


# --------------------------------------------------------------------------- #
# Layer 8: no local rebinding of a contract name (round-1 review fix, item 4)
# --------------------------------------------------------------------------- #

#: The seven names `plans.page` from-imports plus `is_generated`
#: (`plans.engine`) -- `tests/test_public_api.py`'s `is`-identity checks on
#: `GENERATOR` cannot rule out a *re-spelled, byte-identical* local
#: constant: CPython interns short identifier-shaped string literals, so a
#: second `GENERATOR: Final[str] = "fitdocs"` in `page.py` still passes
#: `is fitdocs.contract.GENERATOR` (measured, not assumed -- see that
#: file's own corrected comments). This scan closes the gap directly rather
#: than relying on identity alone.
_CONTRACT_BOUND_NAMES: Final[frozenset[str]] = frozenset(
    {
        "DOC_BANNER",
        "FRONTMATTER_FENCE",
        "GENERATOR",
        "GENERATOR_KEY",
        "TYPE_KEY",
        "NOTES_REGION",
        "NOTES_PLACEHOLDER",
        "is_generated",
    }
)


def _contract_name_rebindings_in_tree(tree: ast.AST) -> list[str]:
    """Every `Assign`/`AnnAssign` in `tree` that binds a name in
    `_CONTRACT_BOUND_NAMES` -- the single scanner both the real-package
    check and its own positive control run (round-2 review fix, item 6:
    the control previously re-implemented this logic inline, the same
    round-1 item-9 pattern this round's review flags again -- a control
    that exercises a hand-rolled copy proves the copy, not the production
    scanner)."""
    found: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        lineno = 0
        if isinstance(node, ast.Assign):
            targets = node.targets
            lineno = node.lineno
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            lineno = node.lineno
        for target in targets:
            if isinstance(target, ast.Name) and target.id in _CONTRACT_BOUND_NAMES:
                found.append(f"L{lineno}: {target.id}")
    return found


class TestNoLocalContractNameRebinding:
    def test_no_module_assigns_a_contract_name_itself(self) -> None:
        """No module under the package binds any of `_CONTRACT_BOUND_NAMES`
        via an `Assign` or `AnnAssign` -- the from-import in `page.py` (the
        seven) or `engine.py` (`is_generated`) is the only legitimate
        binding site for each."""
        offenders: dict[str, list[str]] = {}
        for module_name in PLANS_MODULE_NAMES:
            found = _contract_name_rebindings_in_tree(_module_ast(module_name))
            if found:
                offenders[module_name] = found
        assert not offenders, offenders

    def test_synthetic_module_with_a_respelled_generator_constant_is_caught(
        self,
    ) -> None:
        """Positive control: a re-spelled, byte-identical local `GENERATOR`
        constant -- the exact mutation that survives both `is`-identity
        checks in `tests/test_public_api.py` (interning) -- is caught here,
        through the same `_contract_name_rebindings_in_tree` the real scan
        above calls."""
        found = _contract_name_rebindings_in_tree(
            ast.parse('GENERATOR: str = "fitdocs"\n')
        )
        assert found != [], "a re-spelled GENERATOR constant was not caught"
