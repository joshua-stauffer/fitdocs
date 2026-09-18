"""The threshold-load feature's boundary, proved by import and by behavior
(task 5.4, Req 1.5, 11.1-11.7).

Scope note: ``src/fitdocs/load/priority.py`` is task 1.1's leaf and is
guarded by ``tests/load/test_priority.py::TestLeafPurity`` (an import-target
allowlist, a namespace scan and an ``ast.Call`` scan for dynamic
import/exec/eval, mirroring the shape this module reuses below) -- but that
guard is not exhaustive, by its own docstring's account
(``tests/load/test_priority.py:12-40``): an aliased or rebound import
callable (``_f = importlib.import_module; _f(...)``) and a string executed
by ``exec``/``eval`` referenced under a rebound name (``_e = exec;
_e("import fitdocs.load.settings")``) are "genuine gaps in this leaf's own
guard", left open because closing them "requires a builtin-reference
allowlist, which this leaf's guard does not attempt". This module does not
re-derive ``TestLeafPurity``; it covers the modules task 1.1 does not:
``fitdocs/load/threshold/__init__.py``, ``discipline.py``, ``anchors.py``,
``selection.py`` and ``calculator.py`` (collectively ``FEATURE_MODULE_NAMES``
below) -- and, unlike ``TestLeafPurity``, this module's own layer 5 below
*does* adopt a builtin-reference allowlist, so the corresponding gap does
not reopen here (see layer 5's docstring).

**The layer shape, copied deliberately from ``tests/load/test_priority.py``
and ``tests/load/channels/test_purity.py`` rather than re-derived** (see
those modules' docstrings for the three-rounds-each history that produced
it):

1. An **allowlist over sanctioned import targets** (``_import_violations``),
   judged on the full dotted name -- exact match or a proper ``.``-bounded
   submodule, never a bare top-level check (a top-level allowlist containing
   ``"fitdocs"`` would silently admit ``fitdocs.render``). Also restricts
   the *names* imported from ``fitdocs.benchmarks`` to the two data types
   this feature is allowed to touch (Req 11.4's proxy -- see below) and from
   ``fitdocs.load.channels`` to the three per-channel compute functions
   (Req 11.1's proxy) -- and, since the round-1 remediation below, this name
   restriction is enforced against **both** import forms: a target key in
   ``_ALLOWED_NAMES_BY_TARGET`` may never be imported as a whole module
   either (``import fitdocs.benchmarks``, any ``as`` alias included), only
   through ``from <target> import <one of the allowed names>``. Before this
   fix, ``import fitdocs.benchmarks as bm; bm.benchmark_age(...)`` and
   ``import fitdocs.load.channels as ch; ch.grade.running_cost_ratio(...)``
   both survived every test in this module -- the ``ast.Import`` branch
   checked only the target, never the name restriction that branch's sibling
   ``ast.ImportFrom`` branch already enforced.
2. An **allowlist over each module's own global namespace**
   (``_namespace_violations``), keyed on ``__module__`` -- catches a name
   bound via ``from x import y`` that the import-statement scan's ``alias``
   walk might miss for any reason, but is blind to imported plain data
   (``str``, ``tuple``, ``MappingProxyType`` carry no ``__module__``) and to
   every function-local import, which binds no module global at all.
3. An ``ast.Call`` scan (``_dynamic_import_violations``) for the literal
   spellings ``__import__``, ``import_module``, ``<attr>.import_module``,
   ``exec`` and ``eval`` -- catches the class the first two layers cannot: a
   deferred, function-local import statement is still an ``ast.Import``
   node the source-level walk in layer 1 visits (``ast.walk`` does not stop
   at module scope), so layer 1 alone already closes that one; this layer
   closes the separate class of import reached through a *call* rather than
   an import statement, including one inside ``exec``/``eval`` source text,
   which produces no ``ast.Import`` node at all. **Spelling-bounded, not
   name-bounded**: this layer only recognizes the literal callee spellings
   above, so ``_i = __import__; _i("fitdocs.render")`` is not a call to a
   name this layer watches for at all -- and because ``__import__``,
   ``exec`` and ``eval`` are all ``builtins``-owned (``__import__.
   __module__ == "builtins"``), layer 2's namespace scan does not catch the
   alias-binding either, at *either* module or function scope, since
   ``"builtins"`` is itself an allowed namespace top level there. This
   residual -- an aliased reference to one of these five callees, at any
   scope -- is what layer 5 below closes, by allowlisting the builtin
   *reference* itself rather than the call spelling.

A fourth, feature-specific layer (``_io_clock_prompt_violations``) is a
**denylist over specific builtin/method names** -- ``open``, ``input`` and
the clock/filesystem method names the task brief names by example
(``today``, ``now``, ``read_text``, ...). This layer is explicitly weaker
than layers 1-3: it is a denylist, not an allowlist, so its coverage is a
*class*, not a count. It is a reasonable denylist here specifically
*because* layers 1-3 already foreclose importing any module that could
reach the filesystem, the network or the wall clock through an ordinary
import (``pathlib``, ``socket``, ``requests``, ``time`` are all outside the
sanctioned stdlib set) -- the residual this layer targets is deliberately
narrow: builtins that need no import (``open``, ``input``) and methods on
the one already-imported stdlib type that carries a clock method
(``datetime.date``, imported for typing in ``anchors.py``). This layer's own
residual, precisely: a rebound alias to one of the *method names* on the
denylist (e.g. a local variable named ``today`` holding an unrelated
callable, or a stdlib type's own method reached through a different
attribute path) is outside its reach, since it matches on ``attr`` spelling,
not on the resolved callee. It does **not** miss ``_o = open; _o(...)`` --
that specific spelling is caught at both scopes by layer 5 below (``open``
is not ``builtins``-owned, so it was already partly reachable through layer
2 at module scope only; layer 5 closes it at every scope uniformly, which is
why layer 5 rather than a rebound-alias exception is this module's answer
to that case).

A fifth layer (``_builtin_allowlist_violations``), adopted from ``tests/
load/channels/test_purity.py``'s ``_ALLOWED_BUILTINS`` /
``_ALLOWED_BUILTIN_SHADOWS`` idiom rather than re-derived, closes the
residual named under layers 3 and 4 above by allowlisting the *reference*
to a builtin rather than any particular call spelling: every ``ast.Name`` in
``Load`` context naming something in ``dir(builtins)`` must be one of a
short, measured allowlist (the twelve builtins these five modules actually
reference today) or must be locally bound to a non-builtin-spelled name --
and, separately, *binding* a builtin-spelled name at all (``_i =
__import__``, a parameter named ``open``, a comprehension target named
``eval``) is itself a violation unless the spelling is in
``_ALLOWED_BUILTIN_SHADOWS`` (measured empty across these five modules
today). Because ``_i = __import__`` is a ``Load``-context reference to
``__import__`` on its right-hand side, this layer rejects the assignment at
the point the name is read, before any alias ever exists to call -- closing
the layer-3 residual (``__import__``/``import_module``/``exec``/``eval``
aliased under any name, at module *or* function scope) and the layer-4
residual (``_o = open`` at function scope, where layer 2's namespace scan
cannot reach) in one mechanism, the same way the sibling guard closes it for
``fitdocs.load.channels``.

The **no-fusion** guard (``_fusion_violations``, Req 11.7) is the grep-level
structural half the design's "Regression / Boundary" testing-strategy entry
asks for, run with an AST rather than a raw substring match specifically
because a substring scan is defeated by ``getattr(outcome, "load")`` (task
brief) -- ``_is_load_read`` recognizes both spellings. It flags any
expression-combining node (``BinOp``, ``Compare``, ``BoolOp``, ``Call``,
``Tuple``, ``List``, ``Set``) whose subtree contains two or more *load*
reads on syntactically different objects. This is a structural, not a
semantic, check: it cannot see through aliasing (``a = outcomes[ChannelId.
POWER]; b = a; b.load`` next to ``a.load`` would be judged "different
objects" by source text even though they are the same one at runtime, so it
can over-flag but is not known to under-flag on this codebase's actual
style, which never aliases outcomes). The companion **behavioral** proof
that altering a non-selected channel's value changes nothing is already
pinned by ``tests/load/threshold/test_selection.py::
test_select_reads_no_value_altering_non_selected_load_leaves_selection`` --
not duplicated here.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import inspect
from pathlib import Path
from types import ModuleType

FEATURE_MODULE_NAMES: tuple[str, ...] = (
    "fitdocs.load.threshold",
    "fitdocs.load.threshold.discipline",
    "fitdocs.load.threshold.anchors",
    "fitdocs.load.threshold.selection",
    "fitdocs.load.threshold.calculator",
)
"""Every module task 5.4 owns the boundary of. ``fitdocs.load.priority`` is
deliberately excluded -- see the module docstring's scope note.

Hand-maintained, deliberately -- **and therefore checked against the
directory it claims to enumerate, in both directions, by
``TestEnumerationIsComplete`` below.** Round-1 remediation, Finding 1: before
that test existed, a new module dropped under ``src/fitdocs/load/threshold/``
(e.g. a ``fusion.py`` containing ``import fitdocs.render`` and
``a.load + b.load``) was invisible to every guard in this file -- none of
them ever inspected that file's source at all, because nothing walked the
directory to discover it. ``TestEnumerationIsComplete`` closes that by
asserting set equality against ``_threshold_module_names_on_disk()``, which
*does* walk the directory; every other test in this module still consults
the hand-written tuple above (unchanged in shape, still readable as an
explicit list), but can no longer silently omit a real file, in either
direction: an extra name in the tuple with no file on disk reds exactly like
a file on disk with no name in the tuple.
"""


def _threshold_package_dir() -> Path:
    import fitdocs.load.threshold as threshold_package  # noqa: PLC0415

    path = threshold_package.__file__
    assert path is not None, "fitdocs.load.threshold has no __file__"
    return Path(path).parent


def _threshold_module_names_on_disk() -> frozenset[str]:
    """Every ``*.py`` file anywhere under the threshold package (recursive,
    round-2 remediation, Finding 1), expressed as the dotted module name
    this file's own ``FEATURE_MODULE_NAMES`` tuple uses -- ``__init__.py``
    maps to the package name itself (or, for a subpackage, to that
    subpackage's own dotted name), every other file maps to
    ``<package>.<relative dotted path>``. Before this fix the walk used
    ``glob("*.py")`` (one directory level only), so a file placed one
    directory deeper -- e.g. ``helpers/__init__.py`` -- was invisible to
    this enumeration and, transitively, to every guard in this module that
    trusts ``FEATURE_MODULE_NAMES``."""
    names: set[str] = set()
    package_dir = _threshold_package_dir()
    for path in package_dir.rglob("*.py"):
        relative = path.relative_to(package_dir)
        parts = list(relative.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = path.stem
        dotted = ".".join(["fitdocs", "load", "threshold", *parts])
        names.add(dotted)
    return frozenset(names)


class TestEnumerationIsComplete:
    """Round-1 remediation, Finding 1: ``FEATURE_MODULE_NAMES`` is a
    hand-maintained tuple, so nothing about its own shape stops it from
    silently omitting a real file. This class is the tripwire: every other
    class in this module trusts the tuple, so this one instead trusts the
    filesystem and demands they agree, in both directions.
    """

    def test_walk_of_the_package_directory_is_not_vacuous(self) -> None:
        on_disk = _threshold_module_names_on_disk()
        assert len(on_disk) >= 5, (
            f"vacuous walk: expected at least 5 modules under "
            f"{_threshold_package_dir()}, found {len(on_disk)} -- the walk "
            f"is looking at the wrong directory"
        )

    def test_feature_module_names_names_exactly_the_files_on_disk(self) -> None:
        on_disk = _threshold_module_names_on_disk()
        declared = frozenset(FEATURE_MODULE_NAMES)
        undeclared_on_disk = sorted(on_disk - declared)
        declared_but_absent = sorted(declared - on_disk)
        assert undeclared_on_disk == [], (
            f"file(s) under {_threshold_package_dir()} are not named in "
            f"FEATURE_MODULE_NAMES, so no boundary guard in this module ever "
            f"inspects their source: {undeclared_on_disk}"
        )
        assert declared_but_absent == [], (
            f"FEATURE_MODULE_NAMES names module(s) with no file on disk: "
            f"{declared_but_absent}"
        )


def _feature_modules() -> tuple[ModuleType, ...]:
    return tuple(importlib.import_module(name) for name in FEATURE_MODULE_NAMES)


def _source_for(module: ModuleType) -> tuple[str, str]:
    path = inspect.getsourcefile(module)
    assert path is not None, f"could not locate source for {module.__name__}"
    return Path(path).read_text(encoding="utf-8"), path


# ---------------------------------------------------------------------------
# Layer 1: import-target allowlist
# ---------------------------------------------------------------------------

_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "__future__",
        "dataclasses",
        "collections",
        "types",
        "typing",
        "datetime",
        "fitdocs",
    }
)

_ALLOWED_FITDOCS_EXACT_TARGETS: frozenset[str] = frozenset(
    {
        "fitdocs.model",
        "fitdocs.benchmarks",
        "fitdocs.metrics.types",
        "fitdocs.load.channels",
        "fitdocs.load.channels.types",
        "fitdocs.load.types",
        "fitdocs.load.qa",
    }
)
"""Every non-sibling ``fitdocs.*`` target this feature may import (design.md
"Allowed Dependencies"), matched exactly -- deliberately **not**
prefix-matched, so that e.g. ``fitdocs.load.channels.grade`` (an internal
arithmetic helper -- the Req 11.1 proxy) is not mistaken for a submodule of
the sanctioned ``fitdocs.load.channels`` package import. ``fitdocs.load.qa``
joined this set for the ``activity-qa-flags`` feature's own task 3.2 (design:
``CalculatorIntegration`` Dependencies -- "Outbound -- ``qa.flags.
evaluate_flags`` (P0)"), name-restricted below to the one assembly function
``compute`` calls after a successful channel selection -- not a blanket hole
onto every quality-condition-detection name this package exports."""

_ALLOWED_SIBLING_PREFIX: str = "fitdocs.load.threshold"
"""Modules under this feature's own package may freely import each other
(the calculator imports ``anchors``, ``discipline`` and ``selection``)."""

_ALLOWED_NAMES_BY_TARGET: dict[str, frozenset[str]] = {
    "fitdocs.benchmarks": frozenset({"Benchmark", "BenchmarkKind"}),
    "fitdocs.load.channels": frozenset(
        {"heart_rate_compute", "pace_compute", "power_compute"}
    ),
    "fitdocs.load.qa": frozenset({"evaluate_flags"}),
}
"""Even where the *target* is sanctioned, only these *names* may be
imported from it -- ``fitdocs.benchmarks`` restricted to the two plain data
types (Req 11.4's proxy: no ``benchmark_age``, no ``parse_benchmarks``, no
``benchmarks_to_document``, so this feature cannot read, write, validate,
migrate or compute a staleness verdict for the benchmark store even by
accident), ``fitdocs.load.channels`` restricted to the three top-level
compute functions (Req 11.1's proxy: no internal grade/weighting/sufficiency
helper is ever imported directly, so this feature implements no channel
arithmetic of its own -- it only calls the channel layer's own public
functions), and ``fitdocs.load.qa`` restricted to ``evaluate_flags`` alone --
no flag type, no per-check reading, no per-check module is ever imported
directly, so this feature computes no quality condition of its own and
consults the quality-flag layer only through its one sanctioned assembly
entry point."""


def _is_sanctioned_fitdocs_target(dotted: str) -> bool:
    return (
        dotted in _ALLOWED_FITDOCS_EXACT_TARGETS
        or dotted == _ALLOWED_SIBLING_PREFIX
        or dotted.startswith(_ALLOWED_SIBLING_PREFIX + ".")
    )


def _import_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """Every import-shaped escape from this feature's sanctioned surface.

    Scans the AST directly (not the live namespace -- see the module
    docstring's layer 2 note for why that alone would be insufficient).
    ``ast.walk`` visits nodes at every nesting level, so a deferred,
    function-local ``import fitdocs.render`` is caught here exactly like a
    top-level one (task brief: layer 2, not layer 1, is the one blind to a
    deferred import).

    Round-1 remediation, Findings 2 and 3: a target listed in
    ``_ALLOWED_NAMES_BY_TARGET`` is sanctioned *only* through
    ``from <target> import <allowed name>`` -- an ``ast.Import`` of that
    same target (``import fitdocs.benchmarks``, under any ``as`` alias) is
    rejected outright below, because there is no way to import a whole
    module and still respect a restriction stated over its *names*. Before
    this fix, ``import fitdocs.benchmarks as bm; bm.benchmark_age(...)`` and
    ``import fitdocs.load.channels as ch; ch.grade.running_cost_ratio(...)``
    both passed every test in this module -- the ``ast.Import`` branch
    checked only ``_is_sanctioned_fitdocs_target``, never
    ``_ALLOWED_NAMES_BY_TARGET``, so the name restriction applied to the
    ``from``-form of exactly the same two targets simply did not exist for
    the plain-``import`` form.
    """
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                unsanctioned_fitdocs = top_level == "fitdocs" and not (
                    _is_sanctioned_fitdocs_target(alias.name)
                )
                name_restricted_target = alias.name in _ALLOWED_NAMES_BY_TARGET
                if (
                    top_level not in _ALLOWED_TOP_LEVEL
                    or unsanctioned_fitdocs
                    or name_restricted_target
                ):
                    offenders.append(f"import {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                offenders.append(
                    f"relative import from level {node.level} (line {node.lineno})"
                )
                continue
            module = node.module or ""
            top_level = module.split(".")[0]
            if top_level == "fitdocs":
                if not _is_sanctioned_fitdocs_target(module):
                    offenders.append(f"from {module} import ... (line {node.lineno})")
                    continue
                allowed_names = _ALLOWED_NAMES_BY_TARGET.get(module)
                if allowed_names is not None:
                    for alias in node.names:
                        if alias.name not in allowed_names:
                            offenders.append(
                                f"from {module} import {alias.name} "
                                f"(line {node.lineno})"
                            )
            elif top_level not in _ALLOWED_TOP_LEVEL:
                offenders.append(f"from {module} import ... (line {node.lineno})")
    return offenders


class TestImportBoundary:
    """Req 1.5, 11.2, 11.3, 11.4, 11.5, 11.6: the import-target allowlist
    that structurally forecloses the CLI, the renderer, the load pass, the
    document editor, the load-section renderer, the calculator registry,
    calculator arbitration, the benchmark store's read/write/validate/
    migrate/staleness surface and any aggregation module -- none of those
    names is anywhere in the sanctioned set, so importing any of them is a
    violation regardless of which feature module does it or how deeply
    nested the import statement is. Quality-condition detection is **not**
    a blanket foreclosure any more: the ``activity-qa-flags`` feature's own
    task 3.2 sanctions exactly one name, ``evaluate_flags``, through exactly
    one target, ``fitdocs.load.qa`` -- every other name that package exports
    (every flag type, every per-check reading, every per-check module) stays
    foreclosed, so this feature still computes no quality condition of its
    own (see ``_ALLOWED_NAMES_BY_TARGET``'s docstring).
    """

    def test_every_feature_module_has_no_import_violation(self) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _import_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_scan_is_not_vacuous(self) -> None:
        scanned = 0
        for module in _feature_modules():
            source, _ = _source_for(module)
            tree = ast.parse(source)
            scanned += sum(
                1
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            )
        # threshold/__init__.py has exactly one import statement of its own
        # (`from __future__ import annotations`, an ast.ImportFrom node --
        # round-1 remediation, Finding 9: an earlier draft of this comment
        # claimed zero); the package as a whole must have scanned real
        # import statements somewhere, or this whole layer is silently
        # checking nothing.
        assert scanned > 0, "the walk scanned no import statements at all"

    def test_walk_over_an_empty_module_set_is_not_mistaken_for_a_pass(self) -> None:
        # Direct proof that a vacuous walk is not silently green: pointing
        # the same counting logic at an empty source produces zero scanned
        # imports, and the assertion above would (correctly) fail on it.
        tree = ast.parse("")
        scanned = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        )
        assert scanned == 0

    def test_priority_module_import_leaf_is_covered_elsewhere(self) -> None:
        # Documents, rather than duplicates, the scope note above: fail
        # loudly if that module or its guard test class is ever removed
        # without this module's docstring being updated.
        import fitdocs.load.priority as priority_module

        assert priority_module.__name__ == "fitdocs.load.priority"
        from tests.load.test_priority import TestLeafPurity  # noqa: PLC0415

        assert hasattr(TestLeafPurity, "test_module_imports_only_allowed_names")

    def test_whole_module_import_of_a_name_restricted_target_is_rejected(
        self,
    ) -> None:
        """Round-1 remediation, Findings 2 and 3: a bare ``import`` of a
        target that ``_ALLOWED_NAMES_BY_TARGET`` restricts is a violation
        even though the target itself is sanctioned -- before this fix,
        neither survived only through the ``from``-form allowlist check
        (which both plainly satisfy, since it is never reached); they
        survived because the ``ast.Import`` branch never consulted
        ``_ALLOWED_NAMES_BY_TARGET`` at all.
        """
        offenders = _import_violations("import fitdocs.benchmarks\n")
        assert offenders != [], (
            "import fitdocs.benchmarks (whole module) was not caught"
        )

        offenders = _import_violations("import fitdocs.benchmarks as bm\n")
        assert offenders != [], "import fitdocs.benchmarks as bm was not caught"

        offenders = _import_violations("import fitdocs.load.channels as ch\n")
        assert offenders != [], "import fitdocs.load.channels as ch was not caught"

        offenders = _import_violations("import fitdocs.load.qa as qa\n")
        assert offenders != [], "import fitdocs.load.qa as qa was not caught"

    def test_the_from_form_of_a_name_restricted_target_is_still_sanctioned(
        self,
    ) -> None:
        # Negative control: the fix above must not foreclose the legitimate
        # from-form this feature's real modules actually use.
        offenders = _import_violations(
            "from fitdocs.benchmarks import Benchmark, BenchmarkKind\n"
        )
        assert offenders == []
        offenders = _import_violations(
            "from fitdocs.load.channels import (\n"
            "    heart_rate_compute,\n"
            "    pace_compute,\n"
            "    power_compute,\n"
            ")\n"
        )
        assert offenders == []
        offenders = _import_violations("from fitdocs.load.qa import evaluate_flags\n")
        assert offenders == []

    def test_qa_target_admits_only_evaluate_flags(self) -> None:
        """The ``activity-qa-flags`` feature's own extension (task 3.2,
        design: ``CalculatorIntegration``) is narrow, not a blanket hole onto
        ``fitdocs.load.qa``'s whole re-export surface: every other name that
        package exports -- a flag type, a per-check reading, a settings
        value -- is still a violation, even though the *target* itself is
        now sanctioned."""
        offenders = _import_violations("from fitdocs.load.qa import FlagSettings\n")
        assert offenders != [], (
            "from fitdocs.load.qa import FlagSettings was not caught"
        )

        offenders = _import_violations("from fitdocs.load.qa import FlagKey\n")
        assert offenders != [], "from fitdocs.load.qa import FlagKey was not caught"

    def test_sibling_whole_module_import_without_a_name_restriction_is_fine(
        self,
    ) -> None:
        # Negative control: _ALLOWED_NAMES_BY_TARGET only restricts the two
        # keyed targets -- an ordinary sibling whole-module import (which
        # calculator.py actually performs) must not be caught by the same
        # branch.
        offenders = _import_violations("import fitdocs.load.threshold.selection\n")
        assert offenders == []


# ---------------------------------------------------------------------------
# Layer 2: module-namespace allowlist
# ---------------------------------------------------------------------------

_ALLOWED_NAMESPACE_MODULES: frozenset[str] = frozenset(
    {
        "__future__",
        "builtins",
        "dataclasses",
        "collections.abc",
        "types",
        "typing",
        "datetime",
        "fitdocs.model",
        "fitdocs.benchmarks",
        "fitdocs.metrics.types",
        "fitdocs.load.channels",
        "fitdocs.load.channels.types",
        "fitdocs.load.types",
        "fitdocs.load.qa.flags",
        "fitdocs.load.threshold",
        "fitdocs.load.threshold.discipline",
        "fitdocs.load.threshold.anchors",
        "fitdocs.load.threshold.selection",
        "fitdocs.load.threshold.calculator",
    }
)
"""``fitdocs.load.qa.flags`` -- not ``fitdocs.load.qa`` -- is the entry here:
``evaluate_flags``'s ``__module__`` is its *defining* submodule, the same
reason ``heart_rate_compute`` et al. report ``fitdocs.load.channels.
heart_rate`` rather than the ``fitdocs.load.channels`` package they are
imported through (see the channels submodule-prefix carve-out in
``_namespace_violations`` below). Exact, not prefix-matched: only this one
submodule, for only this one name."""


def _namespace_violations(module: ModuleType) -> list[tuple[str, str]]:
    offenders: list[tuple[str, str]] = []
    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        if inspect.ismodule(value):
            owner = value.__name__
        else:
            owner = getattr(value, "__module__", None)
        if owner is None:
            continue
        if owner == module.__name__:
            continue
        top_level = owner.split(".")[0]
        # A name re-exported through fitdocs.load.channels's own __init__
        # (heart_rate_compute, pace_compute, power_compute) still reports
        # its *defining* submodule as __module__ (e.g.
        # fitdocs.load.channels.heart_rate), not the package it was
        # imported through -- allow any submodule of the one sanctioned
        # channels target, mirroring _is_sanctioned_fitdocs_target's own
        # submodule allowance for the sibling package.
        if owner == "fitdocs.load.channels" or owner.startswith(
            "fitdocs.load.channels."
        ):
            continue
        # "fitdocs" is deliberately excluded from the allowed top levels
        # here: every sanctioned fitdocs.* name must appear explicitly in
        # _ALLOWED_NAMESPACE_MODULES, so a bare top-level match can never
        # substitute for it the way it could for a stdlib module.
        allowed_top_levels = {"builtins"}.union(_ALLOWED_TOP_LEVEL - {"fitdocs"})
        if (
            owner not in _ALLOWED_NAMESPACE_MODULES
            and top_level not in allowed_top_levels
        ):
            offenders.append((name, owner))
    return offenders


class TestNamespaceBoundary:
    """Companion to the import-statement scan: catches a name bound via
    ``from x import y`` under a rebinding the statement-level scan's alias
    walk might miss. Documented blind spot (task brief, and see the module
    docstring): plain data (``str``, ``tuple``, ``MappingProxyType``) has no
    ``__module__`` and is invisible to this layer, and a function-local
    import binds no module global at all -- layer 1 covers both of those.
    """

    def test_every_feature_module_namespace_is_clean(self) -> None:
        for module in _feature_modules():
            offenders = _namespace_violations(module)
            assert offenders == [], f"{module.__name__}: {offenders}"


# ---------------------------------------------------------------------------
# Layer 3: dynamic-import / exec / eval call scan
# ---------------------------------------------------------------------------

_DYNAMIC_IMPORT_CALLEES: frozenset[str] = frozenset(
    {"__import__", "import_module", "exec", "eval"}
)


def _dynamic_import_violations(source: str, *, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _DYNAMIC_IMPORT_CALLEES:
            offenders.append(f"{func.id}(...) call (line {node.lineno})")
        elif isinstance(func, ast.Attribute) and func.attr == "import_module":
            offenders.append(f"...import_module(...) call (line {node.lineno})")
    return offenders


class TestDynamicImportBoundary:
    def test_every_feature_module_has_no_dynamic_import_call(self) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _dynamic_import_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"


# ---------------------------------------------------------------------------
# Layer 4: filesystem / clock / prompting call-name denylist
# ---------------------------------------------------------------------------

_FORBIDDEN_BARE_CALLS: frozenset[str] = frozenset({"open", "input"})
_FORBIDDEN_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "today",
        "now",
        "utcnow",
        "fromtimestamp",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "open",
    }
)


def _io_clock_prompt_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """A denylist, not an allowlist -- see the module docstring's note on
    why this one layer is a class-bounded, not spelling-bounded, guard: it
    matches these specific call-site spellings and is blind to a rebound
    alias to a method name it does not itself watch for. The specific
    ``_o = open; _o(...)`` alias residual named in earlier drafts of this
    docstring is **not** this layer's own gap -- see layer 5 below, which
    closes it (and the analogous ``__import__``/``exec``/``eval`` alias
    residual from layer 3) by allowlisting the builtin *reference* directly.
    """
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _FORBIDDEN_BARE_CALLS:
            offenders.append(f"{func.id}(...) call (line {node.lineno})")
        elif isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_METHOD_NAMES:
            offenders.append(f"...{func.attr}(...) call (line {node.lineno})")
    return offenders


class TestNoFilesystemClockNetworkPromptReference:
    """Req 1.5: consults no network service, no clock, no language model.
    Network is closed structurally by the import allowlist above (no
    ``requests``, ``urllib``, ``socket`` or similar can be imported at all);
    this layer covers the two classes of reference that need no import --
    builtins (``open``, ``input``) and a method on an already-imported
    stdlib type (``datetime.date.today()``)."""

    def test_every_feature_module_has_no_forbidden_call(self) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _io_clock_prompt_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"


# ---------------------------------------------------------------------------
# Layer 5: builtin-reference allowlist (round-1 remediation, Findings 4 & 6)
# ---------------------------------------------------------------------------

_ALLOWED_BUILTINS: frozenset[str] = frozenset(
    {
        "AssertionError",
        "bool",
        "dict",
        "divmod",
        "float",
        "frozenset",
        "int",
        "isinstance",
        "list",
        "set",
        "str",
        "tuple",
    }
)
"""Every builtin these five modules actually reference today (measured by
walking their source), mirroring ``tests/load/channels/test_purity.py``'s
``_ALLOWED_BUILTINS`` idiom rather than re-deriving it. Widening this set is
a deliberate, reviewable act."""

_ALLOWED_BUILTIN_SHADOWS: frozenset[str] = frozenset()
"""The exact set of local bindings permitted to share a spelling with a real
builtin -- measured empty across all five feature modules today, exactly
like the sibling guard's own pin."""


def _locally_bound_names(tree: ast.AST) -> set[str]:
    """Every name ``tree`` binds itself, anywhere -- import targets/aliases,
    ``def``/``class`` names, assignment targets, and parameter names."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
    return bound


def _builtin_shadow_violations(tree: ast.AST) -> list[str]:
    """Every binding of a name in ``dir(builtins)`` that is not in
    ``_ALLOWED_BUILTIN_SHADOWS`` -- rejects the *binding* itself, at any
    scope, rather than trying to model Python scoping (which ``ast.walk``
    cannot do). This is what makes ``_i = __import__`` a violation: the
    assignment target ``_i`` is not itself builtin-spelled, but the fix
    below also inspects the right-hand side as an ordinary ``Load``
    reference, which is where that particular case is actually caught (see
    ``_builtin_allowlist_violations``) -- this function instead closes the
    complementary case, a builtin-*spelled* binding such as a parameter
    named ``open`` or a comprehension target named ``eval``, mirroring the
    sibling guard's own round-6 fix.
    """
    builtin_names = frozenset(dir(builtins))
    violations: list[str] = []
    for node in ast.walk(tree):
        name: str | None = None
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".")[0]
                if (
                    bound_name in builtin_names
                    and bound_name not in _ALLOWED_BUILTIN_SHADOWS
                ):
                    violations.append(
                        f"L{node.lineno}: import binds builtin-spelled name "
                        f"`{bound_name}`"
                    )
            continue
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            name = node.id
        elif isinstance(node, ast.arg):
            name = node.arg
        if (
            name is not None
            and name in builtin_names
            and name not in _ALLOWED_BUILTIN_SHADOWS
        ):
            violations.append(f"L{lineno}: local binding shadows builtin `{name}`")
    return violations


def _builtin_allowlist_violations(
    source: str, *, filename: str = "<test>"
) -> list[str]:
    """Every ``ast.Name`` in ``Load`` context naming a real builtin that is
    not locally bound and not in ``_ALLOWED_BUILTINS``, plus every
    builtin-shadowing binding (``_builtin_shadow_violations``). This is what
    closes ``_i = __import__``: the right-hand side ``__import__`` is a
    ``Load``-context ``ast.Name`` referencing a real builtin, ``_i`` is
    locally bound so it is exempt from *this* check on later reference, but
    the reference on the assignment's own right-hand side is not exempt and
    is not in ``_ALLOWED_BUILTINS`` -- so the assignment itself reds, before
    ``_i`` is ever called.

    Also flags any reference to ``__builtins__`` itself (round-2
    remediation, Finding 2): ``__builtins__`` is not in ``dir(builtins)``
    (it names the module/dict a module's globals carry, not a builtin
    value), so the loop below would not otherwise see it, and
    ``__builtins__["open"](...)`` reaches ``open`` through an
    ``ast.Subscript`` whose ``func`` is not a ``Name``/``Attribute`` at all
    -- invisible to layers 3 and 4 (the call-spelling scan) and to the
    ``ast.Name``/``ast.Attribute`` handling above. This is exactly task
    4.1's deferred survivor (a ``compute`` that writes a file to disk) in a
    spelling round-1's fix did not cover: before this fix,
    ``__builtins__["open"]("/tmp/x", "w").write("escaped")`` inside
    ``compute`` passed the full suite and the file was genuinely created.
    Flagging the bare reference -- ``ast.Name`` with ``id == "__builtins__"``
    or ``ast.Attribute`` with ``attr == "__builtins__"`` -- closes the route
    regardless of what is subsequently subscripted or called on it.
    """
    tree = ast.parse(source, filename=filename)
    bound = _locally_bound_names(tree)
    builtin_names = frozenset(dir(builtins))
    violations: list[str] = list(_builtin_shadow_violations(tree))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in builtin_names
            and node.id not in bound
            and node.id not in _ALLOWED_BUILTINS
        ):
            violations.append(f"L{node.lineno}: builtin `{node.id}` not allowlisted")
        elif (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "__builtins__"
        ) or (isinstance(node, ast.Attribute) and node.attr == "__builtins__"):
            violations.append(
                f"L{node.lineno}: `__builtins__` referenced as a mapping/module "
                f"escapes the builtin-reference allowlist"
            )
    return violations


class TestBuiltinReferenceBoundary:
    """Round-1 remediation, Findings 4 and 6: closes the alias residual
    named under layers 3 and 4 -- an aliased reference to ``__import__``,
    ``import_module``, ``exec``, ``eval`` or ``open``, at module *or*
    function scope -- by allowlisting the builtin *reference* rather than
    any particular call spelling.
    """

    def test_every_feature_module_has_no_unsanctioned_builtin_reference(self) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _builtin_allowlist_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_aliased_dunder_import_at_module_scope_is_caught(self) -> None:
        offenders = _builtin_allowlist_violations(
            '_i = __import__\n_i("fitdocs.render")\n'
        )
        assert offenders != [], "_i = __import__ at module scope was not caught"

    def test_aliased_dunder_import_at_function_scope_is_caught(self) -> None:
        offenders = _builtin_allowlist_violations(
            'def f():\n    _i = __import__\n    _i("fitdocs.render")\n'
        )
        assert offenders != [], "_i = __import__ at function scope was not caught"

    def test_aliased_open_at_function_scope_is_caught(self) -> None:
        offenders = _builtin_allowlist_violations(
            'def f():\n    _o = open\n    _o("x")\n'
        )
        assert offenders != [], "_o = open at function scope was not caught"

    def test_aliased_exec_and_eval_are_caught(self) -> None:
        offenders = _builtin_allowlist_violations("_e = exec\n")
        assert offenders != [], "_e = exec was not caught"
        offenders = _builtin_allowlist_violations("_v = eval\n")
        assert offenders != [], "_v = eval was not caught"

    def test_dunder_builtins_reached_as_a_mapping_is_caught(self) -> None:
        # The negative-space proof for the ``__builtins__`` closure -- the
        # only layer-5 case whose synthetic test was missing, which is why a
        # production-side probe was needed to confirm it in review. This is
        # the spelling that re-opened task 4.1's deferred survivor: a
        # subscript call's ``func`` is an ``ast.Subscript``, not a ``Name``
        # or ``Attribute``, so both the forbidden-call denylist and the
        # builtin allowlist were structurally blind to it while the file was
        # genuinely written and the whole suite stayed green.
        offenders = _builtin_allowlist_violations('__builtins__["open"]("x", "w")\n')
        assert offenders != [], '__builtins__["open"] subscript was not caught'
        offenders = _builtin_allowlist_violations("x = mod.__builtins__\n")
        assert offenders != [], "mod.__builtins__ attribute was not caught"

    def test_ordinary_sanctioned_builtins_are_not_flagged(self) -> None:
        # Negative control: the twelve builtins these modules actually use
        # must not be caught by the allowlist meant to admit them.
        snippet = (
            "def f(x):\n"
            "    if isinstance(x, (int, float)):\n"
            "        return bool(divmod(int(x), 2))\n"
            "    return frozenset(tuple(dict(a=1).items())) == set()\n"
        )
        offenders = _builtin_allowlist_violations(snippet)
        assert offenders == []

    def test_a_parameter_named_open_is_a_shadow_violation(self) -> None:
        # Negative-space proof for _builtin_shadow_violations: binding a
        # builtin-spelled name at all is rejected, not merely a later
        # unsanctioned reference to the real builtin.
        offenders = _builtin_allowlist_violations("def f(open):\n    return open\n")
        assert offenders != [], "a parameter named `open` was not caught"


# ---------------------------------------------------------------------------
# Req 11.2: no result type, no document
# ---------------------------------------------------------------------------

_CONTRACT_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "LoadResult",
        "NonSelectedValue",
        "QualityFlag",
        "LoadOutcome",
        "LoadContext",
        "ProfileView",
        "LoadCalculator",
        "Computed",
        "Unsupported",
        "MissingInputs",
        "NotComputed",
    }
)


def _class_definition_violations(source: str, *, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in _CONTRACT_TYPE_NAMES:
            offenders.append(f"class {node.name} (line {node.lineno})")
    return offenders


class TestNoResultTypeDefinedNoDocumentTouched:
    """Req 11.2: defines no result type, no machine-readable payload, no
    frontmatter key, no rendered output; writes and reads no document.

    The "no document" half is covered by the filesystem denylist above (no
    ``open``, no ``Path(...).read_text()``/``write_text()``); this
    complements it with a structural check that none of the contract's own
    result types is *defined* (only imported and constructed) inside this
    feature -- ``training-load`` owns every one of these names.
    """

    def test_no_feature_module_defines_a_contract_type(self) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _class_definition_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"


# ---------------------------------------------------------------------------
# Req 11.7: no fusion, structurally
# ---------------------------------------------------------------------------

_COMBINING_NODE_TYPES: tuple[type[ast.AST], ...] = (
    ast.BinOp,
    ast.Compare,
    ast.BoolOp,
    ast.Call,
    ast.Tuple,
    ast.List,
    ast.Set,
)


def _is_load_read(node: ast.AST) -> ast.expr | None:
    """If ``node`` reads a ``load`` field -- either ``x.load`` or
    ``getattr(x, "load")`` (the task brief's own example of what a
    substring scan misses) -- return the ``x`` sub-expression it reads it
    from; otherwise ``None``."""
    if isinstance(node, ast.Attribute) and node.attr == "load":
        return node.value
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "load"
    ):
        return node.args[0]
    return None


def _fusion_violations(source: str, *, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, _COMBINING_NODE_TYPES):
            continue
        reads: list[tuple[int, str]] = []
        for sub in ast.walk(node):
            base = _is_load_read(sub)
            if base is not None:
                reads.append((sub.lineno, ast.unparse(base)))
        distinct_objects = {text for _, text in reads}
        if len(distinct_objects) >= 2:
            offenders.append(
                f"{type(node).__name__} at line {node.lineno} reads "
                f"'.load' from {sorted(distinct_objects)}"
            )
    return offenders


class TestNoFusion:
    """Req 11.7, design.md "Regression / Boundary": no module in this
    feature reads two channels' ``load`` values in one expression.
    AST-based, not a raw substring match, specifically because
    ``getattr(outcome, "load")`` defeats a substring scan (task brief).

    Structural coverage only -- see the module docstring for the
    documented aliasing blind spot. The **behavioral** half of Req 11.7
    (altering a non-selected channel's value provably changes nothing) is
    already pinned by ``tests/load/threshold/test_selection.py::
    test_select_reads_no_value_altering_non_selected_load_leaves_selection``
    and is not duplicated here.
    """

    def test_no_feature_module_reads_two_channels_load_in_one_expression(
        self,
    ) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _fusion_violations(source, filename=path)
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_guard_recognizes_the_getattr_spelling_directly(self) -> None:
        # Direct proof the guard is not merely a dressed-up substring
        # match: this synthetic snippet contains no literal ".load"
        # attribute access at all, only two getattr() calls, and must
        # still be flagged.
        snippet = 'def f(a, b):\n    return getattr(a, "load") + getattr(b, "load")\n'
        offenders = _fusion_violations(snippet, filename="<synthetic>")
        assert offenders != []

    def test_guard_does_not_flag_a_single_repeated_read_of_the_same_object(
        self,
    ) -> None:
        # A false-positive check: reading the *same* object's .load twice
        # (e.g. a conditional expression) is not fusion.
        snippet = "def f(a):\n    return a.load if a.load > 0 else None\n"
        offenders = _fusion_violations(snippet, filename="<synthetic>")
        assert offenders == []

    def test_guard_flags_a_binop_combining_two_different_channels(self) -> None:
        snippet = "def f(power, hr):\n    return power.load + hr.load\n"
        offenders = _fusion_violations(snippet, filename="<synthetic>")
        assert offenders != []


# ---------------------------------------------------------------------------
# Req 11.1, 11.3, 11.4, 11.5, 11.6: named residuals, not asserted here
# ---------------------------------------------------------------------------


class TestBoundaryDocumentedNotReasserted:
    """Requirements whose closure rides entirely on the import-target
    allowlist above (``TestImportBoundary``) rather than a dedicated
    assertion of their own -- named here so a reader of this file's test
    list is not left to guess which class carries which requirement.

    * **Req 11.1** (no channel arithmetic, no sufficiency rule, no grade
      model of its own): the ``fitdocs.load.channels`` name-restriction in
      ``_ALLOWED_NAMES_BY_TARGET``, now enforced against **both** import
      forms (round-1 remediation, Finding 3) -- ``import fitdocs.load.
      channels`` and every ``as``-aliased spelling of it are import
      violations in their own right, exactly like a disallowed
      ``from``-import, so this feature can only ever call
      ``power_compute``/``heart_rate_compute``/``pace_compute``, never an
      internal helper reached through a module alias such as
      ``ch.grade.running_cost_ratio`` (previously an unmeasured claim: that
      exact spelling survived every test in this module until this fix).
    * **Req 11.3** (no calculator arbitration, no registry consultation):
      ``fitdocs.load.registry`` and ``fitdocs.load.arbitrate`` are simply
      absent from ``_ALLOWED_FITDOCS_EXACT_TARGETS`` -- importing either
      anywhere in this feature is an import violation.
    * **Req 11.4** (no benchmark store read/write/validate/migrate/
      staleness): the ``fitdocs.benchmarks`` name-restriction to
      ``{"Benchmark", "BenchmarkKind"}``, now enforced against **both**
      import forms (round-1 remediation, Finding 2) -- ``benchmark_age``,
      ``parse_benchmarks`` and ``benchmarks_to_document`` are outside that
      set for the ``from``-form, and ``import fitdocs.benchmarks``/
      ``import fitdocs.benchmarks as bm`` are now rejected outright, closing
      the whole-module alias route to the same three names that previously
      survived (``bm.benchmark_age(...)``).
    * **Req 11.5** (no quality-condition detection): **corrected mechanism**
      (round-1 remediation, Finding 7) -- an earlier draft of this bullet
      claimed closure because "no quality-flag module is in the sanctioned
      target set at all", which is false: ``QualityFlag`` lives in
      ``fitdocs.load.types`` (``src/fitdocs/load/types.py:152``), a
      sanctioned, name-unrestricted import target, so this feature *can*
      import and construct one. What actually forecloses Req 11.5 is task
      3.2's own contract pin, ``tests/load/threshold/test_result_assembly.
      py::test_flags_is_the_empty_tuple`` -- ``build_result`` accepts no
      ``flags`` parameter and always assembles the empty tuple, so a
      feature module that imports ``QualityFlag`` and constructs one still
      cannot get it into the result this feature returns without also
      editing ``calculator.py``'s own ``compute``, which is exactly the
      change that test pins against.
    * **Req 11.6** (no aggregation over time, no threshold estimation):
      **declared, not fully closed** (round-1 remediation, Finding 8) -- the
      import allowlist forecloses reading more than one activity's worth of
      input from any sanctioned target, but does not by itself foreclose
      accumulating a value *across separate calls* to this feature's own
      ``compute`` via a module-level mutable container (e.g. a module-global
      ``list``/``dict``/``set`` that a later call ``.append``s or
      ``[key] =``s into) -- a class of in-process aggregation that no import
      restriction reaches, since it requires no additional import at all.
      ``TestNoModuleGlobalMutableContainer`` below is the discriminating
      carrier for this residual: it rejects any module-level container
      binding that is later mutated in place anywhere in the same module,
      which is the shape a "read across activities" accumulator would need
      to take under this feature's own compute-is-called-once-per-activity
      contract. It is a structural, not semantic, guard -- see that class's
      own docstring for what it does and does not reach.

    This class defines no test method of its own -- it is documentation,
    not an additional assertion; the load-bearing check for every
    requirement it names is ``TestImportBoundary::
    test_every_feature_module_has_no_import_violation`` above, except Req
    11.5 (``test_result_assembly.py::test_flags_is_the_empty_tuple``, named
    above) and Req 11.6 (``TestNoModuleGlobalMutableContainer`` below).
    """


# ---------------------------------------------------------------------------
# Req 11.6: no module-global mutable container (round-1 remediation,
# Finding 8)
# ---------------------------------------------------------------------------

_MUTATING_CONTAINER_METHODS: frozenset[str] = frozenset(
    {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "update",
        "add",
        "discard",
        "setdefault",
        "popitem",
    }
)
_MUTABLE_CONSTRUCTOR_NAMES: frozenset[str] = frozenset(
    {"list", "dict", "set", "defaultdict", "deque", "Counter", "OrderedDict"}
)


def _is_mutable_container_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in _MUTABLE_CONSTRUCTOR_NAMES:
            return True
    return False


def _module_global_mutable_container_violations(
    source: str, *, filename: str = "<test>"
) -> list[str]:
    """Every module-level ``list``/``dict``/``set``-valued binding (a raw
    literal or a call to one of the standard mutable-container
    constructors) that is later **mutated in place** anywhere else in the
    same module -- via a mutating method call (``.append``, ``.update``,
    ...) or a subscript assignment (``name[key] = ...``).

    Deliberately narrower than "no module-level mutable container binding
    at all": this module's own real files bind several module-level ``dict``
    literals as static lookup tables (``CHANNEL_LABELS``,
    ``_BORROWING_CHANNEL_LABEL``, ``_CHANNEL_BENCHMARK_KINDS``,
    ``_FIELD_BY_BENCHMARK_REF``), which are legitimate and are never
    mutated after their own definition -- flagging every such binding would
    be a false positive on real, already-reviewed code. What Req 11.6
    actually forbids is *accumulation over time*: a module-global container
    that some later call (typically inside ``compute``) grows or writes into
    across separate invocations. This scan's positive signal is exactly
    that later mutation, not the mere existence of a mutable literal --
    ``__all__`` is exempt by name (an ordinary list literal, never mutated,
    that every one of these modules may legitimately bind) though it would
    also simply never match, since it is never a mutation target either.

    Structural, not semantic: it cannot see a mutation reached only through
    an alias (``_x = _SEEN_LOADS; _x.append(...)``) or one written from a
    string executed via ``exec``/``eval`` (already foreclosed for other
    reasons by layers 3 and 5 above). It also does not reach a
    reassignment-based accumulator (``global _total; _total = _total +
    load``), which rebinds rather than mutates -- a narrower residual,
    documented rather than closed, since this feature's real modules use
    neither shape today and a rebinding accumulator inside a function still
    requires a ``global`` statement, which is itself unusual enough in this
    codebase's own style to be conspicuous on review.
    """
    tree = ast.parse(source, filename=filename)
    module_level_names: set[str] = set()
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if (
            target is not None
            and isinstance(target, ast.Name)
            and target.id != "__all__"
            and value is not None
            and _is_mutable_container_literal(value)
        ):
            module_level_names.add(target.id)

    offenders: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_CONTAINER_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in module_level_names
        ):
            offenders.append(
                f"L{node.lineno}: {node.func.value.id}.{node.func.attr}(...) "
                f"mutates a module-level container"
            )
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id in module_level_names
        ):
            offenders.append(
                f"L{node.lineno}: {node.value.id}[...] = ... mutates a "
                f"module-level container"
            )
    return offenders


class TestNoModuleGlobalMutableContainer:
    """Req 11.6's discriminating carrier -- see
    ``_module_global_mutable_container_violations`` for exactly what this
    does and does not reach."""

    def test_every_feature_module_has_no_mutated_module_global_container(
        self,
    ) -> None:
        for module in _feature_modules():
            source, path = _source_for(module)
            offenders = _module_global_mutable_container_violations(
                source, filename=path
            )
            assert offenders == [], f"{module.__name__}: {offenders}"

    def test_scan_is_not_vacuous_against_a_real_module_with_dict_literals(
        self,
    ) -> None:
        # selection.py binds a real module-level dict literal
        # (CHANNEL_LABELS) -- confirm the candidate-detection half of the
        # walk actually finds it, so a green result above is not simply an
        # empty candidate set.
        import fitdocs.load.threshold.selection as selection_module  # noqa: PLC0415

        source, _ = _source_for(selection_module)
        tree = ast.parse(source)
        candidates = {
            node.target.id
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and _is_mutable_container_literal(node.value)
        }
        assert "CHANNEL_LABELS" in candidates, (
            "the candidate-detection walk did not find a known real "
            "module-level dict literal -- the mutation check below it would "
            "be vacuously passing"
        )

    def test_a_module_level_list_appended_to_inside_a_function_is_caught(
        self,
    ) -> None:
        snippet = (
            "_SEEN_LOADS: list[float] = []\n\n\n"
            "def compute(selected):\n"
            "    _SEEN_LOADS.append(selected.load)\n"
            "    return selected\n"
        )
        offenders = _module_global_mutable_container_violations(snippet)
        assert offenders != [], "a module-level list.append(...) was not caught"

    def test_a_module_level_dict_written_by_subscript_is_caught(self) -> None:
        snippet = (
            "_TOTALS: dict[str, float] = {}\n\n\n"
            "def accumulate(key, value):\n"
            "    _TOTALS[key] = value\n"
        )
        offenders = _module_global_mutable_container_violations(snippet)
        assert offenders != [], "a module-level dict[key] = ... was not caught"

    def test_a_static_lookup_dict_that_is_only_ever_read_is_not_flagged(
        self,
    ) -> None:
        # Negative control, matching this feature's real style: a
        # module-level dict literal used purely as a read-only lookup table
        # must not be flagged.
        snippet = (
            '_LABELS: dict[str, str] = {"a": "Alpha", "b": "Beta"}\n\n\n'
            "def label_for(key):\n"
            "    return _LABELS[key]\n"
        )
        offenders = _module_global_mutable_container_violations(snippet)
        assert offenders == []

    def test_dunder_all_list_literal_is_not_flagged(self) -> None:
        # Negative control: __all__ is a legitimate module-level list
        # literal every real feature module may bind.
        snippet = '__all__ = ["A", "B"]\n'
        offenders = _module_global_mutable_container_violations(snippet)
        assert offenders == []
