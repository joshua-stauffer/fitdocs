"""The `fitdocs.history` package boundary: its import closure, its clock
purity, its silence about the reference tree, and the *reverse* half --
nothing outside the package reaches back into it (load-history spec, task
5.4; Req 1.1, 2.4, 7.5, 8.5). See the "PackageBoundary and SurfacePins"
component in `.kiro/specs/load-history/design.md`.

**Layer shape**, modelled on `tests/load/threshold/test_boundary.py` and
`tests/load/channels/test_purity.py` rather than re-derived:

1. **Import closure** (`TestImportClosure`) -- every module under
   `src/fitdocs/history/` is parsed and its imports resolved to a dotted
   target, then checked against that module's own hand-pinned allowed set
   **by equality**, not by membership alone (peer WARN, 2026-09-11T18:25):
   a module's set of measured import targets must equal its registered
   allowed set exactly, so a *new* import -- even one that would otherwise
   look legitimate (a second `fitdocs.render.charts.*` primitive, say) --
   fails until the registry is updated by hand, and a stale entry for an
   import that was removed fails too. `TestEnumerationIsComplete` closes the
   companion gap: the hand-maintained module list is checked against the
   package directory in both directions, so a new file dropped under the
   package is never invisible to this module.
2. **Forbidden-name scan** (`TestForbiddenNames`) -- independent of the
   per-module registry, so a violation is named directly rather than only
   inferred from an equality mismatch: the ingest layer, the load engine,
   the threshold calculator, the channels package, the profile module, the
   render views, the hero chart, and any YAML parser. Catches a forbidden
   name reached via `from <parent> import <forbidden-submodule>` (e.g.
   `from fitdocs.render import views`), not only a direct
   `import fitdocs.render.views` -- `_forbidden_scan_targets_for_path`
   additionally records the alias-appended candidate for every
   `from X import y`, since `_import_targets` alone (the narrower registry
   Layer 1's equality pin consumes) resolves that form to the bare,
   unforbidden `X`. Runs over an **explicit path list**
   (`_forbidden_scan_paths`) that includes every history module *and*
   `src/fitdocs/render/charts/calendar.py` (round-3 fix) -- belt and
   braces, the same reason the clock scan below also names that file
   explicitly: it is created by this spec but is not itself a history
   module, so it needs its own entry, resolved against its *real*
   enclosing package `fitdocs.render.charts`, to be covered by this layer
   at all.
3. **Clock scan** (`TestClockScan`) -- a raw-text substring scan (not only an
   AST walk) for five literal spellings, across an **explicit path list**
   that includes every module under the package *and*
   `src/fitdocs/render/charts/calendar.py` -- belt and braces, because that
   file is created by this spec but sits outside every other
   `src/fitdocs/history/`-scoped guard in this file by design (it holds
   only layout constants and a pure renderer, covered by the render
   layer's own guards otherwise) -- the forbidden-name scan above is the
   one exception, naming it explicitly too (round-3 fix) for the same
   reason. A raw-text scan is deliberate here, not merely an AST
   attribute walk: the task requires catching a clock spelling **in a
   docstring example** as well as in code, and a docstring is a string
   literal an AST attribute walk never touches at all -- scanning the file's
   own source text catches both uniformly.
4. **Reference-directory scan** (`TestReferenceDirectoryScan`) -- the string
   `docs/reference` appears nowhere under the package, matching the metrics
   package's own rule.
5. **Reverse reachability** (`TestReverseReachability`,
   `_history_import_violations`) -- no module under `src/fitdocs/load/`,
   neither `src/fitdocs/render/views.py` nor `src/fitdocs/sync.py`, and no
   module under `src/fitdocs/ingest/`, imports `fitdocs.history` in any
   form: a plain `import fitdocs.history`, an aliased whole-module import
   (`import fitdocs.history as h`), a `from fitdocs.history import x`, a
   **package-level from-import** (`from fitdocs import history`, aliased or
   not -- the resolved base alone is the bare `"fitdocs"`, so every
   candidate additionally appends each imported alias's own name before
   the comparison), or a relative import resolved against the **enclosing
   package** of the importing module (peer WARN) rather than the module's
   own dotted name -- a package's own `__init__.py` resolves relative names
   against itself, but every other module resolves against its parent.
   The candidate-list construction (bare resolved base, plus
   `resolved.alias.name` per alias) is adopted from, not re-derived from,
   `_performance_import_violations` in
   `../fitdocs-performance-benchmarks/tests/performance/test_reachability.py`
   (~206-234) -- read directly before this layer's round-2 remediation,
   which is what makes "adopted rather than re-derived" true of that
   candidate-list shape specifically; the layer's overall structure (path
   discovery, per-module scan, single assertion) was already modelled on
   that file in round 1. `TestReverseReachabilitySyntheticControls` proves
   the adopted shape against synthetic source for every form named above,
   plus a negative control, independent of what the real tree currently
   contains. This layer's documented blind spot, spelling-bounded like the
   load-channels sibling this file's layer shape is modelled on: `import
   fitdocs` (the bare top-level namespace) followed by an attribute
   reference (`fitdocs.history.run_history(...)`) produces no `ast.Import`
   or `ast.ImportFrom` node naming `fitdocs.history` at all, and is outside
   this scan's reach -- the bare `fitdocs` namespace is deliberately
   **excluded** from every owner-prefix allowance in this module for the
   same reason (peer WARN): admitting it as a stand-in for a real
   `fitdocs.history` import would make the scan trivially satisfiable by an
   import of the bare package, which is not the violation Req 7.5's reverse
   half concerns itself with. Dynamic access is the same class of blind
   spot and equally out of reach: `importlib.import_module("fitdocs.history")`
   and `__import__("fitdocs.history")` are ordinary function calls, not
   `ast.Import` / `ast.ImportFrom` nodes, so neither is visible to an AST
   walk at all -- this scan is static-import-only by construction, not by
   oversight, and is documented as such.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Final

import fitdocs
import fitdocs.history

# --------------------------------------------------------------------------- #
# Module discovery and enumeration completeness
# --------------------------------------------------------------------------- #

#: Every module this boundary owns, hand-maintained -- and checked against the
#: package directory in both directions by `TestEnumerationIsComplete` below,
#: so a new file dropped under the package is never invisible to this module
#: (mirrors `tests/load/threshold/test_boundary.py`'s own
#: `FEATURE_MODULE_NAMES` / `TestEnumerationIsComplete` pair).
HISTORY_MODULE_NAMES: Final[tuple[str, ...]] = (
    "fitdocs.history",
    "fitdocs.history.documents",
    "fitdocs.history.engine",
    "fitdocs.history.model",
    "fitdocs.history.page",
    "fitdocs.history.series",
    "fitdocs.history.settings",
    "fitdocs.history.sources",
)


def _history_package_dir() -> Path:
    path = fitdocs.history.__file__
    assert path is not None, "fitdocs.history has no __file__"
    return Path(path).parent


def _history_module_names_on_disk() -> frozenset[str]:
    """Every `*.py` file anywhere under the history package, as its dotted
    module name -- the ground truth `HISTORY_MODULE_NAMES` is checked
    against, in both directions."""
    root = _history_package_dir()
    names: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.name == "__init__.py":
            parts = rel.parts[:-1]
            dotted = "fitdocs.history" + ("." + ".".join(parts) if parts else "")
        else:
            parts = rel.with_suffix("").parts
            dotted = "fitdocs.history." + ".".join(parts)
        names.add(dotted)
    return frozenset(names)


class TestEnumerationIsComplete:
    def test_every_module_on_disk_is_registered(self) -> None:
        on_disk = _history_module_names_on_disk()
        assert on_disk, "the walk found no modules -- wrong directory or guard broken"
        missing = on_disk - set(HISTORY_MODULE_NAMES)
        assert not missing, (
            f"module(s) on disk are not registered in HISTORY_MODULE_NAMES: "
            f"{sorted(missing)}"
        )

    def test_every_registered_module_exists_on_disk(self) -> None:
        on_disk = _history_module_names_on_disk()
        stale = set(HISTORY_MODULE_NAMES) - on_disk
        assert not stale, (
            f"HISTORY_MODULE_NAMES names module(s) that do not exist on disk: "
            f"{sorted(stale)}"
        )


def _module_path(module_name: str) -> Path:
    if module_name == "fitdocs.history":
        return _history_package_dir() / "__init__.py"
    leaf = module_name.rsplit(".", 1)[-1]
    return _history_package_dir() / f"{leaf}.py"


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
    (peer WARN, 2026-09-11T18:25) -- `importlib.util.resolve_name`'s own
    contract is stated in terms of `__package__`, which is the package's own
    dotted name for a package and the *parent's* dotted name for a leaf
    module (https://docs.python.org/3/library/importlib.html#importlib.util.resolve_name).
    """
    if module_name == "fitdocs.history":
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
    """Every distinct dotted target `module_name` imports from, resolved.

    `import X` and `import X as Y` both resolve to `X` (the alias never
    changes the target). `from fitdocs import contract, docio` -- the
    package's own repeated pattern for reaching the two shared leaves --
    resolves each *name* to `fitdocs.<name>` rather than admitting the bare
    `fitdocs` namespace as a target: `from fitdocs import contract` is a
    real, deliberate, narrow grant (this package's modules use it
    throughout) and is represented as such (`fitdocs.contract`), while a
    bare `import fitdocs` (which this scan would resolve to the unadorned
    `"fitdocs"` target) is deliberately never added to any module's allowed
    set below -- admitting the bare namespace as a stand-in for every
    `fitdocs.*` submodule would make this equality pin vacuous (peer WARN).
    Every other `from X.Y import z` resolves to `X.Y`, its own name-level
    grants left to `tests/test_contract_consumers.py`'s own registry rather
    than re-derived here.
    """
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

#: Every module's exact, measured set of import targets (Allowed Dependencies,
#: design.md) -- an equality pin (peer WARN), not a membership check: a
#: import added to a module without updating its entry here fails, and a
#: stale entry for a removed import fails too.
_ALLOWED_IMPORT_TARGETS: Final[dict[str, frozenset[str]]] = {
    "fitdocs.history": frozenset(
        {
            "__future__",
            "fitdocs.history.engine",
            "fitdocs.history.model",
            "fitdocs.history.page",
            "fitdocs.history.series",
            "fitdocs.history.settings",
        }
    ),
    "fitdocs.history.documents": frozenset(
        {
            "__future__",
            "math",
            "dataclasses",
            "datetime",
            "pathlib",
            "fitdocs.contract",
            "fitdocs.docio",
            "fitdocs.layout",
        }
    ),
    "fitdocs.history.engine": frozenset(
        {
            "__future__",
            "os",
            "tempfile",
            "dataclasses",
            "pathlib",
            "fitdocs.contract",
            "fitdocs.declaration",
            "fitdocs.history.documents",
            "fitdocs.history.model",
            "fitdocs.history.page",
            "fitdocs.history.series",
            "fitdocs.history.settings",
            "fitdocs.history.sources",
            "fitdocs.layout",
            "fitdocs.load.settings",
            "fitdocs.settings",
        }
    ),
    "fitdocs.history.model": frozenset(
        {
            "__future__",
            "math",
            "collections.abc",
            "dataclasses",
            "fitdocs.history.sources",
        }
    ),
    "fitdocs.history.page": frozenset(
        {
            "__future__",
            "re",
            "collections.abc",
            "dataclasses",
            "datetime",
            "typing",
            "fitdocs.contract",
            "fitdocs.layout",
            "fitdocs.history.documents",
            "fitdocs.history.model",
            "fitdocs.history.series",
            "fitdocs.history.sources",
            "fitdocs.render",
            "fitdocs.render.charts.calendar",
            "fitdocs.render.charts.palette",
        }
    ),
    "fitdocs.history.series": frozenset(
        {
            "__future__",
            "collections",
            "collections.abc",
            "dataclasses",
            "datetime",
            "typing",
            "fitdocs.contract",
            "fitdocs.history.documents",
            "fitdocs.history.model",
        }
    ),
    "fitdocs.history.settings": frozenset(
        {
            "__future__",
            "math",
            "collections.abc",
            "dataclasses",
            "pathlib",
            "typing",
            "fitdocs.history.sources",
            "fitdocs.settings",
        }
    ),
    "fitdocs.history.sources": frozenset(
        {
            "__future__",
            "dataclasses",
            "enum",
            "typing",
            "fitdocs.citation",
        }
    ),
}


class TestImportClosure:
    def test_registry_covers_exactly_the_enumerated_modules(self) -> None:
        assert set(_ALLOWED_IMPORT_TARGETS) == set(HISTORY_MODULE_NAMES)

    def test_every_module_imports_exactly_its_allowed_targets(self) -> None:
        scanned = 0
        for module_name in HISTORY_MODULE_NAMES:
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
        assert scanned == len(HISTORY_MODULE_NAMES), (
            "the walk is looking at the wrong set"
        )


# --------------------------------------------------------------------------- #
# Layer 2: forbidden-name scan, independent of the registry above
# --------------------------------------------------------------------------- #

#: Forbidden by name (design.md "Allowed Dependencies", and this task's own
#: bullet list): the ingest layer, the load engine, the threshold
#: calculator, the channels package, the profile module, the render views,
#: the hero chart, and any YAML parser. Each entry is a dotted prefix --
#: an import target matches if it equals the entry or is a `.`-bounded
#: descendant of it.
_FORBIDDEN_TARGETS: Final[tuple[str, ...]] = (
    "fitdocs.ingest",
    "fitdocs.load.engine",
    "fitdocs.load.threshold",
    "fitdocs.load.channels",
    "fitdocs.load.profile",
    "fitdocs.load.render",
    "fitdocs.render.views",
    "fitdocs.render.charts.hero",
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
    wider than `_import_targets` (which the equality pin in Layer 1 above
    consumes and which must stay a narrow, hand-curated registry). For
    every `from X import y`, this additionally records the alias-appended
    candidate `X.y` -- round-2 fix, item 2: `_import_targets` alone
    resolves `from fitdocs.render import views` to the bare `fitdocs.render`
    (allowed, since `page.py` legitimately imports
    `fitdocs.render.charts.*`), which is not itself forbidden even though
    `views` -- the name actually imported -- names the forbidden
    `fitdocs.render.views` module. Appending each alias catches that by
    name, independent of whether `X.y` happens to be a real module on disk
    (peer shape, `test_reachability.py`'s own `_performance_import_violations`
    candidate list).

    Takes a file path plus its *enclosing package* directly (round-3 fix,
    item 1), rather than a `HISTORY_MODULE_NAMES` entry, so this layer can
    also scan `render/charts/calendar.py` -- a file this spec creates but
    which is not itself a history module and so has no entry in
    `_module_path`'s history-directory-only lookup. A relative import in
    that file (`from . import hero`, `from .hero import x`) must resolve
    against *its own* real enclosing package, `fitdocs.render.charts`, not
    against `fitdocs.history` -- `_module_path`/`_enclosing_package` would
    silently resolve it wrong (or not at all) since they assume every
    module lives under the history directory."""
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


def _forbidden_scan_paths() -> tuple[tuple[Path, str], ...]:
    """The explicit `(path, enclosing package)` pairs the forbidden-name
    scan runs over: every history module paired with its enclosing package
    (`_enclosing_package`), plus `render/charts/calendar.py` under its *real*
    enclosing package
    `fitdocs.render.charts` -- the same belt-and-braces shape as
    `_clock_scan_paths`, for the same reason (see the module docstring):
    `calendar.py` is created by this spec but is not itself a history
    module, so without this explicit entry it would be invisible to this
    layer."""
    history_pairs = tuple(
        (_module_path(name), _enclosing_package(name)) for name in HISTORY_MODULE_NAMES
    )
    return history_pairs + ((_calendar_path(), "fitdocs.render.charts"),)


class TestForbiddenNames:
    def test_no_module_imports_a_forbidden_target(self) -> None:
        pairs = _forbidden_scan_paths()
        assert pairs, "the walk found no files -- wrong path list"
        assert len(pairs) == len(HISTORY_MODULE_NAMES) + 1, (
            "the walk is looking at the wrong directory -- expected every "
            f"history module plus calendar.py ({len(HISTORY_MODULE_NAMES) + 1} "
            f"files), found {len(pairs)}"
        )
        scanned = 0
        offenders: list[str] = []
        for path, enclosing_package in pairs:
            scanned += 1
            for target in _forbidden_scan_targets_for_path(path, enclosing_package):
                forbidden = _matches_forbidden(target)
                if forbidden is not None:
                    offenders.append(f"{path.name} imports {target} ({forbidden})")
        assert scanned == len(HISTORY_MODULE_NAMES) + 1, (
            "the walk is looking at the wrong set"
        )
        assert not offenders, offenders


# --------------------------------------------------------------------------- #
# Layer 3: clock scan -- raw-text substring, code or docstring alike
# --------------------------------------------------------------------------- #

#: The five literal spellings the design names by example -- a qualified
#: attribute access, so `"today"` alone (used freely in this package's own
#: prose, e.g. `engine.py`'s "This module takes no `today` parameter") never
#: trips this scan; only the qualified form a real clock read or a
#: docstring example naming one would use does.
_CLOCK_SPELLINGS: Final[tuple[str, ...]] = (
    "date.today",
    "datetime.now",
    "datetime.utcnow",
    "time.time",
    "time.monotonic",
)


def _calendar_path() -> Path:
    """`render/charts/calendar.py`, the one file outside `src/fitdocs/history/`
    this spec created -- the single source both explicit path lists in this file
    (`_forbidden_scan_paths`, `_clock_scan_paths`) read, so they cannot
    drift to scanning different files."""
    return Path(fitdocs.__file__).resolve().parent / "render" / "charts" / "calendar.py"


def _clock_scan_paths() -> tuple[Path, ...]:
    """The explicit path list the clock scan runs over: every history
    module, plus `render/charts/calendar.py` -- belt and braces, named
    explicitly because that file is not a history module and so lies
    outside the history-directory-scoped layers (import closure,
    reference scan); `_forbidden_scan_paths` names it explicitly for the
    same reason (see the module docstring)."""
    history_paths = tuple(_module_path(name) for name in HISTORY_MODULE_NAMES)
    return history_paths + (_calendar_path(),)


class TestClockScan:
    def test_no_clock_spelling_appears_anywhere_in_code_or_docstring(self) -> None:
        paths = _clock_scan_paths()
        assert paths, "the walk found no files -- wrong path list"
        assert len(paths) == len(HISTORY_MODULE_NAMES) + 1, (
            "the walk is looking at the wrong directory -- expected every "
            f"history module plus calendar.py ({len(HISTORY_MODULE_NAMES) + 1} "
            f"files), found {len(paths)}"
        )
        offenders: list[str] = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for spelling in _CLOCK_SPELLINGS:
                if spelling in text:
                    offenders.append(f"{path.name}: {spelling}")
        assert not offenders, offenders


# --------------------------------------------------------------------------- #
# Layer 4: reference-directory scan
# --------------------------------------------------------------------------- #


class TestReferenceDirectoryScan:
    def test_docs_reference_string_appears_nowhere_in_the_package(self) -> None:
        scanned = 0
        offenders: list[str] = []
        for module_name in HISTORY_MODULE_NAMES:
            scanned += 1
            text = _module_source(module_name)
            if "docs/reference" in text:
                offenders.append(module_name)
        assert scanned == len(HISTORY_MODULE_NAMES), (
            "the walk is looking at the wrong set"
        )
        assert not offenders, offenders


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
    `src/fitdocs/load/`, `render/views.py`, `sync.py`, and every module
    under `src/fitdocs/ingest/` -- discovered by walking the directories
    (not a hand-maintained list), so a new file under any of the three
    trees is never invisible to this scan."""
    load_paths = tuple(sorted((_PACKAGE_ROOT / "load").rglob("*.py")))
    ingest_paths = tuple(sorted((_PACKAGE_ROOT / "ingest").rglob("*.py")))
    assert load_paths and ingest_paths, (
        "the walk is looking at the wrong directory -- "
        f"load_paths={len(load_paths)}, ingest_paths={len(ingest_paths)}"
    )
    named_paths = (
        _PACKAGE_ROOT / "render" / "views.py",
        _PACKAGE_ROOT / "sync.py",
    )
    return load_paths + ingest_paths + named_paths


def _history_import_violations(
    source: str, *, anchor: str, filename: str = "<test>"
) -> list[str]:
    """Every way `source` -- a module whose enclosing package is `anchor`
    (i.e. `anchor` is that module's own `__package__`, never its own dotted
    `__name__`) -- could import `fitdocs.history`: a bare
    `import fitdocs.history` (or any dotted submodule of it, under any
    `as` alias), a `from fitdocs.history import x` /
    `from fitdocs.history.x import y`, a **package-level from-import**
    (`from fitdocs import history`, aliased or not -- round-2 fix, item 1:
    the resolved module for this form is the bare `"fitdocs"`, a prefix of
    `fitdocs.history` that matches nothing on its own, so every
    `ast.ImportFrom`'s resolved base is additionally paired with each
    imported alias's own name, `f"{resolved}.{alias.name}"`, and that
    appended candidate is what is actually checked against the target),
    or a relative form (`from ..history import x`, `from .. import
    history`) resolved via `importlib.util.resolve_name` against `anchor`
    (peer shape, adopted rather than re-derived: identical candidate-list
    construction to `../fitdocs-performance-benchmarks/tests/performance/
    test_reachability.py`'s own `_performance_import_violations`, ~206-234,
    read directly before writing this function).

    Returns every violation found (not merely the first), each labelled
    with its source line, for use both against the real reachability scan
    below and against synthetic positive/negative controls
    (`TestReverseReachabilitySyntheticControls`).
    """
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fitdocs.history" or alias.name.startswith(
                    "fitdocs.history."
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
                if candidate == "fitdocs.history" or candidate.startswith(
                    "fitdocs.history."
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


def _imports_history(path: Path) -> str | None:
    """The offending import spelling if `path` imports `fitdocs.history` in
    any form, else `None`."""
    module_name = _module_name_for_path(path)
    enclosing = (
        module_name.rsplit(".", 1)[0] if path.name != "__init__.py" else module_name
    )
    violations = _history_import_violations(
        path.read_text(encoding="utf-8"), anchor=enclosing, filename=str(path)
    )
    return violations[0] if violations else None


class TestReverseReachability:
    def test_nothing_outside_the_package_imports_fitdocs_history(self) -> None:
        targets = _reachability_targets()
        assert targets, "the walk found no files -- wrong path list"
        offenders: list[str] = []
        for path in targets:
            spelling = _imports_history(path)
            if spelling is not None:
                offenders.append(f"{path}: {spelling}")
        assert not offenders, offenders


class TestReverseReachabilitySyntheticControls:
    """Positive and negative controls for `_history_import_violations`
    against synthetic source, run independent of any real file on disk --
    the peer shape (`test_reachability.py`'s own
    `TestNoCalculatorOrChannelModuleImportsThisPackage`), adopted rather
    than re-derived. These close the gap the real-file reachability scan
    above cannot: it only ever proves the shipped code has no violation
    *today*, never that the scan itself would catch one if it appeared."""

    def test_absolute_import_is_caught(self) -> None:
        offenders = _history_import_violations(
            "import fitdocs.history\n", anchor="fitdocs.load.channels.heart_rate"
        )
        assert offenders != [], "import fitdocs.history was not caught"

    def test_aliased_whole_module_import_is_caught(self) -> None:
        offenders = _history_import_violations(
            "import fitdocs.history as h\n", anchor="fitdocs"
        )
        assert offenders != [], "aliased whole-module import was not caught"

    def test_package_level_from_import_is_caught(self) -> None:
        # `from fitdocs import history` -- a level-0 `ast.ImportFrom` with
        # `node.module == "fitdocs"` and a single alias named `history`,
        # the package itself imported by name, not one of its submodules.
        # `resolved` alone ("fitdocs") never equals "fitdocs.history" and
        # never starts with "fitdocs.history."; only the appended
        # `resolved.alias.name` candidate ("fitdocs.history") catches it
        # (round-2 fix, item 1). Anchored at a real scanned module
        # (`render/views.py`'s own enclosing package).
        offenders = _history_import_violations(
            "from fitdocs import history\n", anchor="fitdocs.render"
        )
        assert offenders != [], "from fitdocs import history was not caught"

    def test_package_level_from_import_aliased_is_caught(self) -> None:
        # Same escape, under an `as` alias -- `alias.asname` never affects
        # `alias.name`, the field the appended candidate is built from.
        offenders = _history_import_violations(
            "from fitdocs import history as h\n", anchor="fitdocs"
        )
        assert offenders != [], "from fitdocs import history as h was not caught"

    def test_submodule_from_import_is_caught(self) -> None:
        offenders = _history_import_violations(
            "from fitdocs.history import model\n", anchor="fitdocs.load.engine"
        )
        assert offenders != [], "from fitdocs.history import model was not caught"

    def test_relative_import_is_caught_from_a_leaf_modules_own_anchor(self) -> None:
        # A leaf module (e.g. `load/engine.py`) resolves a relative import
        # against its *parent* package, `fitdocs.load` -- confirmed
        # directly against `importlib.util.resolve_name` rather than
        # assumed. Same anchor as the real R1c mutation planted in
        # `load/engine.py`, a different spelling: R1c planted
        # `from .. import history`, this control's synthetic source is
        # `from ..history import model`.
        anchor = "fitdocs.load"
        assert importlib.util.resolve_name("..history", anchor) == "fitdocs.history"
        offenders = _history_import_violations(
            "from ..history import model\n", anchor=anchor
        )
        assert offenders != [], "relative import from a leaf module was not caught"

    def test_relative_import_is_caught_from_an_init_modules_own_anchor(self) -> None:
        # A package's own `__init__.py` (e.g. `load/__init__.py`) resolves
        # a relative import against *itself*, `fitdocs.load` -- the same
        # dotted value as the leaf case above only because `load/__init__.py`
        # and `load/engine.py` share the same parent package; the anchor is
        # derived the opposite way (identity vs. `rsplit`), which is exactly
        # what `_imports_history`'s own `is __init__.py` branch (and
        # `_enclosing_package`) exist to get right. Mirrors the real R18b
        # mutation planted in `load/__init__.py`.
        anchor = "fitdocs.load"
        assert importlib.util.resolve_name("..history", anchor) == "fitdocs.history"
        offenders = _history_import_violations(
            "from .. import history\n", anchor=anchor
        )
        assert offenders != [], "relative import from an __init__ module was not caught"

    def test_unrelated_relative_import_is_not_flagged(self) -> None:
        # Negative control: a relative import that resolves to something
        # else entirely (a real sanctioned sibling import) must not be
        # caught. Assert the resolved value directly, not merely that the
        # offender list stays empty -- a broken resolution that silently
        # returned `None` or the wrong target would also leave this list
        # empty, for the wrong reason.
        anchor = "fitdocs.load"
        assert importlib.util.resolve_name(".settings", anchor) == (
            "fitdocs.load.settings"
        )
        offenders = _history_import_violations(
            "from .settings import load_load_settings\n", anchor=anchor
        )
        assert offenders == []
