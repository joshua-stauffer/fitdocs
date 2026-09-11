"""Single-writer guard: the derivation pass is imported by exactly the
command layer (task 4.5; design: PassEngine / Guards "Single writer"; Req
1.10, 9.4, 9.5, 10.3, 10.8).

The whole feature's confinement to one write path rests on one fact holding
statically, not merely behaviourally: nothing but `fitdocs.cli` ever reaches
`fitdocs.performance.engine.derive_benchmarks` -- the one function that
derives, reconciles and writes a benchmark. A behavioural test cannot prove
this: a second caller that never happens to run during the suite is
invisible to it. This module walks the AST of every module under
`src/fitdocs` instead (test modules are never part of this package's source
tree, so no exclusion of them is needed) and asserts the entry point is
*imported* by exactly one file.

The scan covers three import shapes -- the two the task names plus the
package-level reach a reviewer round found unguarded:

* a whole-module import of `fitdocs.performance.engine` (any alias) -- the
  module that *defines* `derive_benchmarks`, importable directly;
* an import of the name `derive_benchmarks` itself, from either
  `fitdocs.performance.engine` (its defining module) or `fitdocs.performance`
  (its published re-export, `tests/test_public_api.py`'s own surface pin) --
  any alias, including every relative spelling of both, resolved via
  `importlib.util.resolve_name` against each scanned file's own enclosing
  *package* (never its own dotted module name) -- the identical resolution
  ruling `tests/performance/test_reachability.py::_performance_import_
  violations` documents and `tests/load/channels/test_purity.py` already
  relies on;
* a whole-*package* import of `fitdocs.performance` or
  `fitdocs.performance.engine` themselves (`import fitdocs.performance`,
  `from fitdocs import performance`, `from . import performance`,
  `from .performance import engine`, any alias) followed elsewhere by
  attribute access (`_perf.derive_benchmarks(...)`, `_p.derive_benchmarks`).
  A module that imports the *package* rather than the *name* reaches the
  entry point exactly as statically as one that imports the name directly --
  the AST records only the import statement, not the later attribute
  access, so this shape is flagged at the import site itself, on the same
  footing as the other two.

`fitdocs/performance/engine.py` (the definition) and
`fitdocs/performance/__init__.py` (the one sanctioned re-export
`tests/test_public_api.py` already requires to exist, task 4.3's own
addition to the published surface) are excluded from the scanned set: one
*is* the entry point, the other *is* its publication, and neither is a
second caller in the sense this guard polices. Excluding them is what lets
"imported by exactly one module" mean "one module other than its own
definition and its own publication" -- `fitdocs.cli`'s own import, landed by
task 4.4 and present in the tree this task scans.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Final

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src" / "fitdocs"

#: The entry point's own definition and its one sanctioned re-export --
#: excluded from the scan for the reason the module docstring gives.
_EXCLUDED_FILES: frozenset[Path] = frozenset(
    {
        _SRC_ROOT / "performance" / "engine.py",
        _SRC_ROOT / "performance" / "__init__.py",
    }
)

#: The one sanctioned caller (design: PassEngine Service Interface; task
#: 4.4's `derive-benchmarks` CLI command), named relative to `src/fitdocs`.
SANCTIONED_CALLERS: frozenset[Path] = frozenset({Path("cli.py")})


def _package_anchor(path: Path) -> str:
    """The dotted name Python's import machinery treats as `__package__` for
    `path` -- the value `importlib.util.resolve_name`'s `package` argument
    expects, never the module's own dotted name. Dropping the file's own
    path component unconditionally (`parts[:-1]`, whether or not the file is
    `__init__.py`) computes it uniformly, generalising
    `tests/performance/test_reachability.py::_package_anchor`'s identical
    ruling from one flat directory to every subpackage under `src/fitdocs`."""
    relative = path.relative_to(_SRC_ROOT).with_suffix("")
    parts = list(relative.parts[:-1])
    return ".".join(["fitdocs", *parts]) if parts else "fitdocs"


def _iter_scanned_files() -> list[Path]:
    """Every `.py` file under `src/fitdocs`, excluding the entry point's own
    definition and publication sites (module docstring)."""
    return sorted(
        path for path in _SRC_ROOT.rglob("*.py") if path not in _EXCLUDED_FILES
    )


#: The two modules whose *name itself* reaches the entry point, whether
#: imported whole (`import fitdocs.performance.engine`), by attribute
#: (`from fitdocs import performance`, later `performance.derive_benchmarks`),
#: or by name (`from fitdocs.performance import derive_benchmarks`).
_SANCTIONED_MODULES: Final = ("fitdocs.performance", "fitdocs.performance.engine")


def derive_benchmarks_import_violations(
    source: str, *, anchor: str, filename: str = "<test>"
) -> list[str]:
    """Every way `source` -- a module whose enclosing package is `anchor` --
    could reach the pass entry point (module docstring's three shapes).

    A whole-module `ast.Import` is matched two ways: its dotted target alone
    (`alias.name`) equal to `fitdocs.performance.engine` (the defining
    module, importable directly; `alias.asname` never affects that field, so
    an aliased whole-module import is caught identically to the unaliased
    form), OR equal to `fitdocs.performance` itself (the package -- a module
    that imports the *package* reaches `derive_benchmarks` by attribute
    access exactly as statically as one that imports the name, so it is
    flagged at the import site regardless of whether an attribute access is
    visible in this file). An `ast.ImportFrom` is resolved to its absolute
    target first (relative forms via `importlib.util.resolve_name` against
    `anchor`, level-0 forms taken as written) and then checked two ways
    against the same two sanctioned targets: an imported name equal to
    `derive_benchmarks` (covering `from fitdocs.performance.engine import
    derive_benchmarks` and `from fitdocs.performance import
    derive_benchmarks`, any alias, any relative spelling), OR -- covering
    `from fitdocs import performance`, `from . import performance`, and
    `from .performance import engine` -- an imported name whose *resolved
    dotted form* (`resolved_base + "." + alias.name`) equals one of the two
    sanctioned modules, which is exactly the package-import-by-another-name
    shape a submodule or sibling import produces.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _SANCTIONED_MODULES:
                    spelling = f"import {alias.name}"
                    if alias.asname:
                        spelling += f" as {alias.asname}"
                    violations.append(f"L{node.lineno}: {spelling}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    resolved_base: str | None = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), anchor
                    )
                except ImportError:
                    resolved_base = None
            else:
                resolved_base = node.module
            for alias in node.names:
                imported_dotted = (
                    f"{resolved_base}.{alias.name}" if resolved_base else None
                )
                if resolved_base in _SANCTIONED_MODULES and (
                    alias.name == "derive_benchmarks"
                ):
                    spelling = f"{alias.name}"
                    if alias.asname:
                        spelling += f" as {alias.asname}"
                    violations.append(
                        f"L{node.lineno}: from {'.' * node.level}"
                        f"{node.module or ''} import {spelling} "
                        f"(resolves to {resolved_base}.derive_benchmarks)"
                    )
                elif imported_dotted in _SANCTIONED_MODULES:
                    spelling = f"{alias.name}"
                    if alias.asname:
                        spelling += f" as {alias.asname}"
                    violations.append(
                        f"L{node.lineno}: from {'.' * node.level}"
                        f"{node.module or ''} import {spelling} "
                        f"(resolves to {imported_dotted})"
                    )
    return violations


def _derive_benchmarks_importers() -> dict[Path, list[str]]:
    """Every scanned module that imports the pass entry point, keyed by its
    `src/fitdocs`-relative path and valued by the offending line(s)."""
    importers: dict[Path, list[str]] = {}
    for path in _iter_scanned_files():
        anchor = _package_anchor(path)
        offenders = derive_benchmarks_import_violations(
            path.read_text(encoding="utf-8"), anchor=anchor, filename=str(path)
        )
        if offenders:
            importers[path.relative_to(_SRC_ROOT)] = offenders
    return importers


def test_scan_covers_a_non_trivial_number_of_files() -> None:
    """Non-vacuity: the walk really did look at a real package tree, not an
    empty or wrong directory (change-protocol's "vacuous walk" anti-pattern)."""
    scanned = _iter_scanned_files()
    assert len(scanned) >= 30, (
        f"vacuous walk: expected at least 30 modules under src/fitdocs, "
        f"found {len(scanned)} -- the walk is looking at the wrong directory"
    )


def test_derive_benchmarks_is_imported_by_exactly_the_command_layer() -> None:
    """Req 1.10, 9.4, 9.5, 10.3, 10.8: no module other than `fitdocs.cli` may
    derive, write, or reconcile a derived benchmark. `fitdocs.cli`'s import
    (task 4.4) is already in the tree this scan walks, so this pins the real,
    current state rather than a disclosed future one.
    """
    importers = _derive_benchmarks_importers()
    assert set(importers) == SANCTIONED_CALLERS, (
        f"derive_benchmarks is imported by {sorted(str(p) for p in importers)} "
        f"({importers}), expected exactly "
        f"{sorted(str(p) for p in SANCTIONED_CALLERS)}"
    )


def test_whole_module_import_of_engine_is_caught() -> None:
    offenders = derive_benchmarks_import_violations(
        "import fitdocs.performance.engine\n", anchor="fitdocs.audit"
    )
    assert offenders != [], "import fitdocs.performance.engine was not caught"


def test_aliased_whole_module_import_of_engine_is_caught() -> None:
    offenders = derive_benchmarks_import_violations(
        "import fitdocs.performance.engine as eng\n", anchor="fitdocs.audit"
    )
    assert offenders != [], "aliased whole-module import was not caught"


def test_from_performance_import_derive_benchmarks_is_caught() -> None:
    offenders = derive_benchmarks_import_violations(
        "from fitdocs.performance import derive_benchmarks\n", anchor="fitdocs.audit"
    )
    assert offenders != [], (
        "from fitdocs.performance import derive_benchmarks was not caught"
    )


def test_from_performance_engine_import_derive_benchmarks_is_caught() -> None:
    offenders = derive_benchmarks_import_violations(
        "from fitdocs.performance.engine import derive_benchmarks\n",
        anchor="fitdocs.audit",
    )
    assert offenders != [], (
        "from fitdocs.performance.engine import derive_benchmarks was not caught"
    )


def test_aliased_from_import_is_caught() -> None:
    offenders = derive_benchmarks_import_violations(
        "from fitdocs.performance import derive_benchmarks as db\n",
        anchor="fitdocs.audit",
    )
    assert offenders != [], "aliased from-import was not caught"


def test_relative_import_reaching_derive_benchmarks_is_caught_from_sibling_pkg() -> (
    None
):
    # `anchor` is the real enclosing package `_package_anchor` computes for
    # `load/engine.py` -- confirmed directly against
    # `importlib.util.resolve_name` below, not assumed.
    anchor = _package_anchor(_SRC_ROOT / "load" / "engine.py")
    assert anchor == "fitdocs.load"
    assert importlib.util.resolve_name("..performance", anchor) == "fitdocs.performance"
    offenders = derive_benchmarks_import_violations(
        "from ..performance import derive_benchmarks\n", anchor=anchor
    )
    assert offenders != [], (
        "relative import of derive_benchmarks from a sibling package was not caught"
    )


def test_relative_import_reaching_the_engine_module_is_caught_from_an_init_module() -> (
    None
):
    anchor = _package_anchor(_SRC_ROOT / "load" / "__init__.py")
    assert anchor == "fitdocs.load"
    assert (
        importlib.util.resolve_name("..performance.engine", anchor)
        == "fitdocs.performance.engine"
    )
    offenders = derive_benchmarks_import_violations(
        "from ..performance.engine import derive_benchmarks as _db\n", anchor=anchor
    )
    assert offenders != [], (
        "relative import of derive_benchmarks from an __init__.py-anchored "
        "package was not caught"
    )


def test_whole_package_import_of_performance_is_caught() -> None:
    """`import fitdocs.performance` reaches `derive_benchmarks` by later
    attribute access (`_perf.derive_benchmarks(...)`) exactly as statically as
    importing the name -- it must be flagged at the import site itself.
    """
    offenders = derive_benchmarks_import_violations(
        "import fitdocs.performance\n", anchor="fitdocs.audit"
    )
    assert offenders != [], "import fitdocs.performance was not caught"


def test_aliased_whole_package_import_of_performance_is_caught() -> None:
    offenders = derive_benchmarks_import_violations(
        "import fitdocs.performance as _perf\n", anchor="fitdocs.audit"
    )
    assert offenders != [], "aliased import fitdocs.performance was not caught"


def test_from_fitdocs_import_performance_is_caught() -> None:
    """`from fitdocs import performance` then `performance.derive_benchmarks`
    -- the package-by-another-name shape a top-level sibling import produces.
    """
    offenders = derive_benchmarks_import_violations(
        "from fitdocs import performance\n", anchor="fitdocs.audit"
    )
    assert offenders != [], "from fitdocs import performance was not caught"


def test_relative_import_of_performance_package_is_caught() -> None:
    """`from . import performance`, resolved against a scanned file's own
    enclosing package (e.g. `fitdocs.sync`'s anchor, `fitdocs`)."""
    anchor = _package_anchor(_SRC_ROOT / "sync.py")
    assert anchor == "fitdocs"
    assert importlib.util.resolve_name(".", anchor) == "fitdocs"
    offenders = derive_benchmarks_import_violations(
        "from . import performance as _perf\n", anchor=anchor
    )
    assert offenders != [], "from . import performance was not caught"


def test_relative_import_of_performance_engine_submodule_is_caught() -> None:
    """`from .performance import engine`, covering the submodule-by-name
    shape distinct from `from .performance import derive_benchmarks`."""
    anchor = _package_anchor(_SRC_ROOT / "cli.py")
    assert anchor == "fitdocs"
    assert (
        importlib.util.resolve_name(".performance.engine", anchor)
        == "fitdocs.performance.engine"
    )
    offenders = derive_benchmarks_import_violations(
        "from .performance import engine\n", anchor=anchor
    )
    assert offenders != [], "from .performance import engine was not caught"


def test_unrelated_from_import_of_a_sibling_performance_name_is_not_flagged() -> None:
    # Negative control: a real, sanctioned import of a *different* name from
    # the same package must not be caught -- otherwise every consumer of
    # `fitdocs.performance`'s pure vocabulary would trip this guard.
    offenders = derive_benchmarks_import_violations(
        "from fitdocs.performance import DeclineReason\n", anchor="fitdocs.audit"
    )
    assert offenders == []


def test_unrelated_whole_module_import_of_a_sibling_module_is_not_flagged() -> None:
    offenders = derive_benchmarks_import_violations(
        "import fitdocs.performance.derive\n", anchor="fitdocs.audit"
    )
    assert offenders == []


def test_package_anchor_drops_the_files_own_component_for_a_leaf_and_an_init() -> None:
    """Falsity in the starting state and reachability, in one assertion:
    both a leaf module and an `__init__.py` in the *same* directory must
    resolve to the *same* anchor -- the directory, not the file."""
    leaf = _package_anchor(_SRC_ROOT / "render" / "frontmatter.py")
    init = _package_anchor(_SRC_ROOT / "render" / "__init__.py")
    assert leaf == "fitdocs.render"
    assert init == "fitdocs.render"
