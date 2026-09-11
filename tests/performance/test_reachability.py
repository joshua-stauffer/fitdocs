"""No module under `fitdocs.load.threshold` or `fitdocs.load.channels`
imports `fitdocs.performance`, in any form (task 5.1; Req 9.2, 9.3, 10.1,
10.2, 10.6, 10.7). This is the reverse-direction half of the boundary
`test_purity.py` proves forward: that module proves the four pure modules
import only their own sanctioned surface; this module proves the calculator
and the channel layer never import *them* back -- the dependency the
"Allowed Dependencies" arrow chain in design.md runs strictly one way,
`load.channels` -> `performance.*`, never the reverse, and the calculator
consumes neither.

The scan itself (`_performance_import_violations`) is written fresh for this
module rather than adopted, since it answers a different, narrower question
than any layer in `test_purity.py` or the sibling calculator/channels
guards: not "does this import something unsanctioned" (an allowlist) but
"does this import one specific package, by any spelling" (a single-target
denylist) -- resolved via `importlib.util.resolve_name`, anchored at each
scanned file's own enclosing *package* (never the file's own dotted module
name -- `resolve_name`'s `package` argument is `__package__`, not
`__name__`), the same resolution shape
`tests/load/channels/test_purity.py`'s own `_resolve` helper (lines
433-441) uses -- that helper anchors at the flat `fitdocs.load.channels`
package directly, since that guard's scanned modules all live in one flat
package; this module's `_package_anchor` computes the equivalent anchor
per-file since it spans two separate packages
(`fitdocs.load.threshold`, `fitdocs.load.channels`). This is *not* the
shape `tests/load/threshold/test_boundary.py` uses for its own
`node.level` handling: that guard rejects every `node.level > 0` outright
(test_boundary.py:347-349) rather than resolving it, so no relative import
ever reaches its allowlist at all.

The I/O-and-clock half of this task's brief ("the same scan proves the pure
modules reach no filesystem, network, clock, prompt or rendering") is
satisfied by importing `io_clock_prompt_violations` directly from
`test_purity.py` below and running it again here, against the same four
pure modules -- literally the same function, not a second hand-written copy
that could drift from it. "No rendering" is covered by `test_purity.py`'s
own import allowlist (`fitdocs.render` is not a sanctioned target for any of
the four modules) and re-confirmed here via a planted-violation check
against a synthetic source.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

from fitdocs.performance import derive, models, sources, types
from tests.performance.test_purity import io_clock_prompt_violations

_PURE_MODULES: tuple[ModuleType, ...] = (types, sources, models, derive)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS: tuple[tuple[Path, str], ...] = (
    (_REPO_ROOT / "src" / "fitdocs" / "load" / "threshold", "fitdocs.load.threshold"),
    (_REPO_ROOT / "src" / "fitdocs" / "load" / "channels", "fitdocs.load.channels"),
)


def _package_anchor(package_dir: Path, root_package: str, path: Path) -> str:
    """The dotted name Python's import machinery treats as `__package__` for
    `path` -- the value `importlib.util.resolve_name`'s `package` argument
    expects, never the module's own dotted name. Dropping the file's own
    path component (`parts[:-1]`, unconditionally, whether or not that file
    is `__init__.py`) computes it uniformly: for a leaf module (e.g.
    `heart_rate.py` directly under `fitdocs/load/channels/`) that yields the
    *enclosing* package (`fitdocs.load.channels`) -- one level shallower than
    the module's own dotted name (`fitdocs.load.channels.heart_rate`); for
    `__init__.py` it yields the package itself, since a package's `__init__`
    module's own `__package__` equals its own `__name__`. Both scanned
    directories here are flat (no subpackages -- confirmed directly:
    `find src/fitdocs/load/channels src/fitdocs/load/threshold -name
    '*.py'` lists only direct children), so today every file's anchor is
    simply `root_package`; the general form is kept so a future subpackage
    is anchored correctly without revisiting this function.
    """
    relative = path.relative_to(package_dir)
    parts = list(relative.parts[:-1])
    return ".".join([root_package, *parts]) if parts else root_package


def _iter_scanned_files() -> list[tuple[Path, str]]:
    """Every `.py` file under either scanned directory, paired with the
    package anchor a relative import inside it would resolve against."""
    found: list[tuple[Path, str]] = []
    for package_dir, root_package in _SCAN_ROOTS:
        for path in sorted(package_dir.rglob("*.py")):
            found.append((path, _package_anchor(package_dir, root_package, path)))
    return found


def _performance_import_violations(
    source: str, *, anchor: str, filename: str = "<test>"
) -> list[str]:
    """Every way `source` -- a module whose enclosing package is `anchor`
    (i.e. `anchor` is that module's own `__package__`, produced by
    `_package_anchor`, never its own dotted `__name__`) -- could import
    `fitdocs.performance`: a bare `import fitdocs.performance` (or any
    dotted submodule of it, under any `as` alias -- an aliased whole-module
    import is not a distinct case here, since `ast.Import` carries the
    alias only as `alias.asname`, never affecting `alias.name`, the dotted
    target this function inspects), a `from fitdocs.performance import x` /
    `from fitdocs.performance.x import y`, or a relative form (`from
    ...performance import types`, resolved via
    `importlib.util.resolve_name` against `anchor`, the same resolution
    shape `tests/load/channels/test_purity.py`'s own `_resolve` helper
    uses) that lands on `fitdocs.performance` or a submodule of it.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fitdocs.performance" or alias.name.startswith(
                    "fitdocs.performance."
                ):
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
            if resolved_base is None:
                continue
            # `resolved_base` alone is never sufficient: for `node.module is
            # None` (`from ...package import performance`, or the level-0
            # `from fitdocs import performance`), the stem lives in the
            # imported *name*, not in `node.module` at all, so
            # `resolved_base` names only `package`/`fitdocs`, never
            # `package.performance`/`fitdocs.performance` -- a scan that
            # compared `resolved_base` alone against `fitdocs.performance`
            # would let a level-0 `from fitdocs import performance` (or `...
            # as _p`) through uncaught, since `resolved_base` there is
            # exactly `"fitdocs"`. But `node.module` being present does not
            # make appending the aliases *wrong* either: `from
            # fitdocs.performance import types` and `from fitdocs import
            # performance` are the same violation reached two different
            # ways, and a from-import can always in principle carry a name
            # that is itself a submodule of the resolved base regardless of
            # whether `node.module` was present. So every `ast.ImportFrom`,
            # level 0 or relative, is checked against *both* the bare
            # resolved base (`from fitdocs.performance import types` --
            # `resolved_base` alone already names the package) and, for
            # every imported alias, `resolved_base.alias.name` (`from
            # fitdocs import performance` -- only the appended form names
            # the package) -- analogous to the sibling channels guard's
            # `from . import types` handling, generalised to every alias.
            candidates = [
                resolved_base,
                *(f"{resolved_base}.{alias.name}" for alias in node.names),
            ]
            for candidate in candidates:
                if candidate == "fitdocs.performance" or candidate.startswith(
                    "fitdocs.performance."
                ):
                    violations.append(
                        f"L{node.lineno}: from {'.' * node.level}{node.module or ''} "
                        f"import ... (resolves to {candidate})"
                    )
    return violations


class TestNoCalculatorOrChannelModuleImportsThisPackage:
    def test_scan_covers_a_non_trivial_number_of_files(self) -> None:
        scanned = _iter_scanned_files()
        assert len(scanned) >= 12, (
            f"vacuous walk: expected at least 12 modules across "
            f"load/threshold and load/channels, found {len(scanned)} -- the "
            f"walk is looking at the wrong directories"
        )

    def test_no_scanned_module_imports_fitdocs_performance(self) -> None:
        violations: dict[str, list[str]] = {}
        for path, anchor in _iter_scanned_files():
            offenders = _performance_import_violations(
                path.read_text(encoding="utf-8"), anchor=anchor, filename=str(path)
            )
            if offenders:
                violations[str(path.relative_to(_REPO_ROOT))] = offenders
        assert violations == {}, (
            f"forbidden fitdocs.performance import(s): {violations}"
        )

    def test_absolute_import_is_caught(self) -> None:
        offenders = _performance_import_violations(
            "import fitdocs.performance\n", anchor="fitdocs.load.channels.heart_rate"
        )
        assert offenders != [], "import fitdocs.performance was not caught"

    def test_aliased_whole_module_import_is_caught(self) -> None:
        offenders = _performance_import_violations(
            "import fitdocs.performance.engine as eng\n",
            anchor="fitdocs.load.threshold.calculator",
        )
        assert offenders != [], "aliased whole-module import was not caught"

    def test_level_zero_from_import_of_the_package_itself_is_caught(self) -> None:
        # Round-3 remediation: `from fitdocs import performance` is a
        # level-0 `ast.ImportFrom` with `node.module == "fitdocs"` and a
        # single alias named `performance` -- the *package itself*, not one
        # of its submodules, imported by name. `resolved_base` alone
        # (`"fitdocs"`) never equals `fitdocs.performance` and never starts
        # with `fitdocs.performance.`, so a scan that only ever compared the
        # bare resolved base would let this through uncaught; only the
        # appended `resolved_base.alias.name` form ("fitdocs.performance")
        # catches it. Anchored at a real scanned package
        # (`fitdocs.load.channels`, the same anchor `_iter_scanned_files`
        # assigns to every leaf module in that package), not a synthetic
        # anchor.
        offenders = _performance_import_violations(
            "from fitdocs import performance\n", anchor="fitdocs.load.channels"
        )
        assert offenders != [], "from fitdocs import performance was not caught"

    def test_level_zero_from_import_of_the_package_itself_aliased_is_caught(
        self,
    ) -> None:
        # Same escape, under an `as` alias -- `alias.asname` never affects
        # `alias.name`, the field this scan inspects, so the aliased form
        # must be caught identically to the unaliased one above.
        offenders = _performance_import_violations(
            "from fitdocs import performance as _p\n",
            anchor="fitdocs.load.threshold",
        )
        assert offenders != [], "from fitdocs import performance as _p was not caught"

    def test_from_import_of_a_submodule_is_caught(self) -> None:
        offenders = _performance_import_violations(
            "from fitdocs.performance import types\n",
            anchor="fitdocs.load.channels.power",
        )
        assert offenders != [], "from fitdocs.performance import types was not caught"

    def test_from_import_of_a_name_inside_a_submodule_is_caught(self) -> None:
        offenders = _performance_import_violations(
            "from fitdocs.performance.types import DerivationMethod\n",
            anchor="fitdocs.load.threshold.discipline",
        )
        assert offenders != [], (
            "from fitdocs.performance.types import DerivationMethod was not caught"
        )

    def test_relative_import_reaching_the_package_is_caught_from_a_leaf_module(
        self,
    ) -> None:
        # `anchor` is the *enclosing package* `_package_anchor` computes for
        # the real leaf module `heart_rate.py` -- `fitdocs.load.channels`,
        # never the leaf module's own dotted name. Three leading dots from
        # that anchor resolve past `channels`, `load` and `fitdocs` itself,
        # landing on `fitdocs.performance` -- confirmed directly against
        # `importlib.util.resolve_name` below, not assumed.
        channels_dir = _REPO_ROOT / "src" / "fitdocs" / "load" / "channels"
        anchor = _package_anchor(
            channels_dir, "fitdocs.load.channels", channels_dir / "heart_rate.py"
        )
        assert anchor == "fitdocs.load.channels"
        assert importlib.util.resolve_name("...performance", anchor) == (
            "fitdocs.performance"
        )
        offenders = _performance_import_violations(
            "from ...performance import types as _pt\n", anchor=anchor
        )
        assert offenders != [], (
            "three-dot relative import reaching fitdocs.performance from a "
            "leaf module's own enclosing package was not caught"
        )

    def test_relative_import_reaching_the_package_is_caught_from_an_init_module(
        self,
    ) -> None:
        # Same resolution, anchored at a real `__init__.py` file's own
        # enclosing package instead of a leaf module's -- `_package_anchor`
        # computes the identical shape for both (see its own docstring),
        # exercised here against the actual file rather than assumed.
        threshold_dir = _REPO_ROOT / "src" / "fitdocs" / "load" / "threshold"
        anchor = _package_anchor(
            threshold_dir, "fitdocs.load.threshold", threshold_dir / "__init__.py"
        )
        assert anchor == "fitdocs.load.threshold"
        assert importlib.util.resolve_name("...performance.types", anchor) == (
            "fitdocs.performance.types"
        )
        offenders = _performance_import_violations(
            "from ...performance.types import DerivationMethod as _dm\n",
            anchor=anchor,
        )
        assert offenders != [], (
            "three-dot relative import reaching fitdocs.performance.types "
            "from an __init__.py-anchored package was not caught"
        )

    def test_unrelated_relative_import_is_not_flagged(self) -> None:
        # Negative control: a relative import that resolves to something
        # else entirely (fitdocs.load.channels.types, a real sanctioned
        # sibling import in this package) must not be caught. Assert the
        # resolved value directly, not merely that the offender list stays
        # empty -- a broken resolution that silently returned `None` or the
        # wrong target would also leave this list empty, for the wrong
        # reason.
        anchor = "fitdocs.load.channels"
        assert importlib.util.resolve_name(".types", anchor) == (
            "fitdocs.load.channels.types"
        )
        offenders = _performance_import_violations(
            "from .types import ChannelId\n", anchor=anchor
        )
        assert offenders == []

    def test_unrelated_absolute_import_is_not_flagged(self) -> None:
        offenders = _performance_import_violations(
            "from fitdocs.benchmarks import Benchmark\n",
            anchor="fitdocs.load.channels.power",
        )
        assert offenders == []


class TestPureModulesReachNoFilesystemNetworkClockPromptOrRendering:
    """Task 5.1's own wording: "the same scan proves the pure modules reach
    no filesystem, network, clock, prompt ... or rendering" -- the same
    `io_clock_prompt_violations` function `test_purity.py` defines and pins
    against these same four modules, imported and re-run here rather than
    duplicated, so the two guards cannot silently drift apart. "No
    rendering" is additionally confirmed directly: a synthetic
    `fitdocs.render` import, fed through `test_purity.py`'s own import
    allowlist, is caught.
    """

    def test_every_pure_module_has_no_forbidden_reference(self) -> None:
        import inspect

        for module in _PURE_MODULES:
            path = inspect.getsourcefile(module)
            assert path is not None
            source = Path(path).read_text(encoding="utf-8")
            offenders = io_clock_prompt_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_planted_render_import_is_caught_by_the_import_allowlist(self) -> None:
        from tests.performance.test_purity import _import_allowlist_violations

        offenders = _import_allowlist_violations(
            "from fitdocs.render import build_page\n",
            module_name="fitdocs.performance.derive",
        )
        assert offenders != [], "from fitdocs.render import build_page was not caught"
