"""The quality-flag layer's boundary and permanent exclusions, proved by
import and by behavior (task 4.3).

Covers Requirements 1.9, 8.4, 9.1-9.9 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and design.md's
"Architecture integration" and "Non-Goals" sections. This module pins four
things about ``src/fitdocs/load/qa/``:

1. It performs no I/O, consults no clock or random source, and invokes no
   language model (task bullet 1).
2. No module in the package imports the load engine, the renderer, the
   document editor, the calculator registry, the document contract, the
   threshold calculator (including its channel-selection logic) or the
   benchmark-store module, and only ``qa/flags.py`` imports the load
   contract, ``fitdocs.load.types``; the one legitimate benchmark-module
   import (``fitdocs.benchmarks``, used only by ``staleness.py``) is
   restricted to the three plain data types and function it actually reads
   (task bullet 2; Round-2 review finding 1 widened this from a bare
   six-target denylist to also cover Req 9.3's "selects no channel" and Req
   9.4's "resolves no benchmark", which the six-target list alone did not
   reach).
3. The computed load value is bit-identical with and without verdicts for
   the same activity -- the never-a-load-combiner constraint made mechanical
   rather than declarative (task bullet 3).
4. The package registers no calculator (proven behaviorally, task bullet 4)
   and resolves no benchmark / selects no channel / touches no coverage
   table (proven structurally by bullet 2's import-boundary scan: none of
   the modules that could do any of these is importable at all).

**Ground truth this module protects, not fixes** (confirmed by grep before
writing a single assertion): the package is exactly 8 files --
``__init__.py``, ``types.py``, ``sources.py``, ``cadence.py``,
``divergence.py``, ``drift.py``, ``staleness.py``, ``flags.py``. Only
``flags.py`` imports ``fitdocs.load.types``; no file imports
``fitdocs.load.engine``, ``fitdocs.load.render``, ``fitdocs.render``,
``fitdocs.load.docedit``, ``fitdocs.load.registry`` or ``fitdocs.contract``.
This module is a validation-only guard against future drift -- if any
assertion below actually failed against the real package, that would be a
first-ever production defect in this spec and is reported, never quietly
patched around.

**Technique borrowed, not the target list.** ``tests/load/channels/test_purity.py``
(task 4.2 of ``load-channels``) already solved "resolve every relative-import
spelling to its absolute dotted form before comparing" via
``importlib.util.resolve_name`` anchored on the package's own dotted name.
That resolution technique is reused verbatim below (see ``_resolve_module``);
the forbidden-target *list* is different, because unlike ``load/channels``
this package legitimately imports several ``fitdocs.load.channels.*``
modules, ``fitdocs.benchmarks`` and ``fitdocs.metrics.types`` (all shown in
the dependency graph in design.md's "Architecture integration" section) --
so this guard is a specific denylist of the six named modules, not a
blanket "no fitdocs.load sibling at all" rule.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from fitdocs import Activity, DerivedMetrics, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate_compute, pace_compute, power_compute
from fitdocs.load.channels.types import ChannelId, SufficiencySettings
from fitdocs.load.threshold.anchors import resolve as resolve_anchors
from fitdocs.load.threshold.calculator import build_result
from fitdocs.load.types import QualityFlag
from fitdocs.model import SCHEMA_VERSION, SessionSummary

_QA_PACKAGE = "fitdocs.load.qa"
_QA_DIR = Path(__file__).resolve().parents[3] / "src" / "fitdocs" / "load" / "qa"

_EXPECTED_FILES = frozenset(
    {
        "__init__.py",
        "types.py",
        "sources.py",
        "cadence.py",
        "divergence.py",
        "drift.py",
        "staleness.py",
        "flags.py",
    }
)


def test_package_file_discovery_finds_exactly_the_eight_modules() -> None:
    """Positive control: prove the walk below is looking at the right
    directory and finds all 8 files, not zero and not some subset -- a
    guard that silently scans nothing would pass every assertion vacuously."""
    py_files = sorted(p.name for p in _QA_DIR.glob("*.py"))
    assert set(py_files) == _EXPECTED_FILES, (
        f"expected exactly {sorted(_EXPECTED_FILES)} under {_QA_DIR}, "
        f"found {py_files} -- the walk is looking at the wrong directory "
        f"or the package shape changed"
    )
    assert len(py_files) == 8


# ===========================================================================
# Bullet 2: import-boundary scan -- no engine, renderer, docedit, registry,
# contract anywhere; only flags.py reaches the load contract.
# ===========================================================================

_ALWAYS_FORBIDDEN: tuple[str, ...] = (
    "fitdocs.load.engine",
    "fitdocs.load.render",
    "fitdocs.render",
    "fitdocs.load.docedit",
    "fitdocs.load.registry",
    "fitdocs.contract",
    # Round-2 review finding 1: 9.3 ("selects no channel") and 9.4
    # ("resolves no benchmark") name the calculator's own selection logic
    # and the benchmark store's resolution path -- neither is reachable
    # through the six targets above, since ``fitdocs.load.threshold`` (the
    # calculator, including its ``selection`` submodule) and
    # ``fitdocs.load.profile`` (the benchmark store) are both distinct
    # dotted prefixes.
    "fitdocs.load.threshold",
    "fitdocs.load.profile",
)
"""Forbidden for every one of the 8 files, ``flags.py`` included."""

_LOAD_CONTRACT = "fitdocs.load.types"
"""Forbidden for every file except ``flags.py``, which is the one sanctioned
importer of the load contract (design.md's "Architecture integration")."""

_NAME_RESTRICTED_TARGETS: dict[str, frozenset[str]] = {
    "fitdocs.benchmarks": frozenset({"Benchmark", "BenchmarkAge", "benchmark_age"}),
}
"""Round-2 review finding 1: ``fitdocs.benchmarks`` is a legitimate target
(``staleness.py`` reads ``Benchmark``, ``BenchmarkAge`` and
``benchmark_age`` -- the exact set below, confirmed against that file's own
import line), but the module also exposes benchmark-store read/write/parse
functions this package must never reach (Req 9.4: "shall not read, write,
validate or migrate the benchmark store"). Every name imported from a
name-restricted target must be in the allowed set, and a whole-module
import of a name-restricted target (``import fitdocs.benchmarks``) is
forbidden outright -- it would grant unrestricted attribute access to every
name on the module, defeating the restriction the same way an unrestricted
``import fitdocs.load.channels as ch`` would defeat a target restriction
(the exact escape ``tests/load/threshold/test_boundary.py``'s own docstring
names as the fix its whole-module-import branch was added for)."""


def _resolve_module(node: ast.ImportFrom) -> str | None:
    """Resolve an ``ast.ImportFrom`` node to its absolute dotted module
    name, handling relative imports at any level via
    :func:`importlib.util.resolve_name` anchored on the qa package's own
    name -- the same technique ``tests/load/channels/test_purity.py``
    established for exactly this problem (its ``_resolve`` helper)."""
    if node.level == 0:
        return node.module
    dots = "." * node.level
    name = dots + (node.module or "")
    try:
        return importlib.util.resolve_name(name, _QA_PACKAGE)
    except ImportError:
        return None


def _import_targets(source: str, *, filename: str = "<test>") -> list[tuple[str, int]]:
    """Every absolute dotted name a piece of source code references via an
    import statement or a dynamic ``__import__``/``importlib.import_module``
    call with a literal string argument -- ``ast.Import`` names verbatim,
    ``ast.ImportFrom`` both as its resolved base module and as each
    name-qualified candidate (so ``from fitdocs.load import engine``
    produces both ``fitdocs.load`` and ``fitdocs.load.engine``)."""
    tree = ast.parse(source, filename=filename)
    results: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_module(node)
            if base is None:
                continue
            results.append((base, node.lineno))
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = f"{base}.{alias.name}" if base else alias.name
                results.append((candidate, node.lineno))
        elif isinstance(node, ast.Call):
            func = node.func
            is_dynamic_import = (
                isinstance(func, ast.Name)
                and func.id in ("__import__", "import_module")
            ) or (isinstance(func, ast.Attribute) and func.attr == "import_module")
            if (
                is_dynamic_import
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                results.append((node.args[0].value, node.lineno))
    return results


def _matches_forbidden(target: str, forbidden: tuple[str, ...]) -> str | None:
    for name in forbidden:
        if target == name or target.startswith(name + "."):
            return name
    return None


def _name_restriction_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """For every target in :data:`_NAME_RESTRICTED_TARGETS`: a whole-module
    import (``import fitdocs.benchmarks``, any alias) is always forbidden,
    and a ``from <target> import <name>`` is forbidden unless ``<name>`` is
    in that target's allowed set. Resolves relative imports the same way
    :func:`_resolve_module` does, so this closes the identical relative-
    spelling gap the denylist scan closes."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _NAME_RESTRICTED_TARGETS:
                    violations.append(
                        f"{filename}:{node.lineno}: import {alias.name} "
                        f"(whole-module import of a name-restricted target)"
                    )
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_module(node)
            if base is None:
                continue
            allowed = _NAME_RESTRICTED_TARGETS.get(base)
            if allowed is None:
                continue
            for alias in node.names:
                if alias.name == "*" or alias.name not in allowed:
                    violations.append(
                        f"{filename}:{node.lineno}: from {base} import "
                        f"{alias.name} not in allowed set {sorted(allowed)}"
                    )
    return violations


def _boundary_violations(
    source: str, *, filename: str, is_flags_module: bool
) -> list[str]:
    forbidden = (
        _ALWAYS_FORBIDDEN if is_flags_module else _ALWAYS_FORBIDDEN + (_LOAD_CONTRACT,)
    )
    violations = []
    for target, lineno in _import_targets(source, filename=filename):
        match = _matches_forbidden(target, forbidden)
        if match is not None:
            violations.append(
                f"{filename}:{lineno}: {target!r} crosses forbidden boundary {match!r}"
            )
    violations.extend(_name_restriction_violations(source, filename=filename))
    return violations


def test_no_module_imports_a_forbidden_boundary_target() -> None:
    """Bullet 2, first half: no file among the 8 imports the load engine,
    the renderer (either spelling), the document editor, the calculator
    registry or the document contract; the 7 non-``flags.py`` files
    additionally may not import the load contract."""
    py_files = sorted(_QA_DIR.glob("*.py"))
    assert len(py_files) == 8, "vacuous walk -- see the file-discovery test"

    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _boundary_violations(
            path.read_text(encoding="utf-8"),
            filename=path.name,
            is_flags_module=(path.name == "flags.py"),
        )
        if found:
            violations[path.name] = found

    assert violations == {}, f"forbidden boundary import(s): {violations}"


def test_only_flags_module_imports_the_load_contract() -> None:
    """Bullet 2, second half, stated positively (not just "everyone else is
    forbidden" -- that alone would pass vacuously if a future refactor
    silently dropped the legitimate import from ``flags.py``, breaking the
    calculator integration without this guard ever noticing)."""
    flags_source = (_QA_DIR / "flags.py").read_text(encoding="utf-8")
    flags_targets = {target for target, _ in _import_targets(flags_source)}
    assert _LOAD_CONTRACT in flags_targets, (
        "flags.py no longer imports fitdocs.load.types -- the one sanctioned "
        "reach into the load contract is gone, which would silently break "
        "the calculator integration"
    )

    for path in sorted(_QA_DIR.glob("*.py")):
        if path.name == "flags.py":
            continue
        targets = {
            target for target, _ in _import_targets(path.read_text(encoding="utf-8"))
        }
        assert _LOAD_CONTRACT not in targets, (
            f"{path.name} imports {_LOAD_CONTRACT}, which only flags.py may"
        )


def test_flags_module_import_presence_check_would_catch_its_own_removal() -> None:
    """Fixture-discrimination companion to the positive half above: mutate a
    copy of ``flags.py``'s source with the load-contract import stripped out
    and confirm the same detection logic used above flags the absence --
    proving the positive assertion is not vacuously true because the
    detector can never fail."""
    flags_source = (_QA_DIR / "flags.py").read_text(encoding="utf-8")
    assert "fitdocs.load.types" in flags_source
    mutated = flags_source.replace("from fitdocs.load.types import QualityFlag\n", "")
    assert mutated != flags_source, (
        "mutation did not change the source -- fix the fixture"
    )
    mutated_targets = {target for target, _ in _import_targets(mutated)}
    assert _LOAD_CONTRACT not in mutated_targets, (
        "mutated source still resolves to the load contract -- the mutation "
        "fixture itself is broken"
    )


@pytest.mark.parametrize(
    ("label", "source", "target"),
    [
        (
            "engine_absolute_import",
            "import fitdocs.load.engine\n",
            "fitdocs.load.engine",
        ),
        (
            "engine_absolute_from",
            "from fitdocs.load.engine import compute\n",
            "fitdocs.load.engine",
        ),
        (
            "engine_parent_then_attribute",
            "from fitdocs.load import engine\n",
            "fitdocs.load.engine",
        ),
        (
            "engine_relative_level_2",
            "from ..engine import compute\n",
            "fitdocs.load.engine",
        ),
        (
            "render_absolute_import",
            "import fitdocs.load.render\n",
            "fitdocs.load.render",
        ),
        (
            "render_top_level_absolute",
            "import fitdocs.render\n",
            "fitdocs.render",
        ),
        (
            "render_top_level_submodule",
            "from fitdocs.render.charts import Chart\n",
            "fitdocs.render",
        ),
        (
            "render_relative_level_3",
            "from ...render import charts\n",
            "fitdocs.render",
        ),
        (
            "docedit_absolute_from",
            "from fitdocs.load.docedit import DocumentEditor\n",
            "fitdocs.load.docedit",
        ),
        (
            "docedit_relative_level_2",
            "from ..docedit import DocumentEditor\n",
            "fitdocs.load.docedit",
        ),
        (
            "registry_absolute_import",
            "import fitdocs.load.registry\n",
            "fitdocs.load.registry",
        ),
        (
            "registry_absolute_from",
            "from fitdocs.load.registry import register\n",
            "fitdocs.load.registry",
        ),
        (
            "registry_relative_level_2",
            "from ..registry import register\n",
            "fitdocs.load.registry",
        ),
        (
            "contract_absolute_from",
            "from fitdocs.contract import DocumentContract\n",
            "fitdocs.contract",
        ),
        (
            "contract_relative_level_3",
            "from ...contract import DocumentContract\n",
            "fitdocs.contract",
        ),
        (
            "dynamic_import_module",
            'importlib.import_module("fitdocs.load.engine")\n',
            "fitdocs.load.engine",
        ),
        (
            "dunder_import",
            '__import__("fitdocs.load.registry")\n',
            "fitdocs.load.registry",
        ),
        # Round-2 review finding 1: the reviewer's own five adversarial
        # spellings for Req 9.3 ("selects no channel") and 9.4 ("resolves no
        # benchmark"), reproduced verbatim so the guard is proven against
        # the exact cases that defeated round 1.
        (
            "threshold_selection_absolute_from",
            "from fitdocs.load.threshold.selection import select\n",
            "fitdocs.load.threshold",
        ),
        (
            "threshold_selection_relative_level_2",
            "from ..threshold.selection import select\n",
            "fitdocs.load.threshold",
        ),
        (
            "profile_absolute_from",
            "from fitdocs.load.profile import AthleteProfile\n",
            "fitdocs.load.profile",
        ),
    ],
)
def test_boundary_scanner_catches_every_reported_spelling(
    label: str, source: str, target: str
) -> None:
    """Every forbidden category, at every spelling the task's own text
    names, run against synthetic sources (this task's boundary forbids
    editing the real modules to prove the same point)."""
    violations = _boundary_violations(source, filename=label, is_flags_module=False)
    assert violations != [], f"{label}: offending import {target!r} was not caught"


@pytest.mark.parametrize(
    ("label", "source"),
    [
        # Round-2 review finding 1's remaining two reviewer spellings: the
        # benchmark-store escape through a legitimate-looking
        # ``fitdocs.benchmarks`` import, restricted to disallowed names.
        (
            "benchmarks_parse_benchmarks",
            "from fitdocs.benchmarks import parse_benchmarks\n",
        ),
        (
            "benchmarks_benchmark_set",
            "from fitdocs.benchmarks import BenchmarkSet\n",
        ),
        (
            "benchmarks_whole_module_import",
            "import fitdocs.benchmarks\n",
        ),
        (
            "benchmarks_whole_module_import_aliased",
            "import fitdocs.benchmarks as bm\n",
        ),
    ],
)
def test_boundary_scanner_catches_the_benchmark_store_name_restriction_leak(
    label: str, source: str
) -> None:
    violations = _boundary_violations(source, filename=label, is_flags_module=False)
    assert violations != [], f"{label}: disallowed benchmarks reference was not caught"


def test_boundary_scanner_does_not_flag_the_sanctioned_benchmark_names() -> None:
    """Negative control matching ``staleness.py``'s real import line
    exactly: ``Benchmark``, ``BenchmarkAge`` and ``benchmark_age`` stay
    green, individually and together."""
    real_import = (_QA_DIR / "staleness.py").read_text(encoding="utf-8")
    assert "from fitdocs.benchmarks import Benchmark, BenchmarkAge, benchmark_age" in (
        real_import
    ), "staleness.py's real import line changed -- update the fixture to match"
    violations = _boundary_violations(
        "from fitdocs.benchmarks import Benchmark, BenchmarkAge, benchmark_age\n",
        filename="<sanctioned>",
        is_flags_module=False,
    )
    assert violations == [], f"sanctioned benchmark names wrongly flagged: {violations}"


@pytest.mark.parametrize(
    ("label", "source"),
    [
        (
            "load_contract_absolute_from_non_flags",
            "from fitdocs.load.types import QualityFlag\n",
        ),
        (
            "load_contract_relative_level_2_non_flags",
            "from ..types import QualityFlag\n",
        ),
    ],
)
def test_boundary_scanner_catches_the_load_contract_leak_outside_flags(
    label: str, source: str
) -> None:
    """The load-contract-specific half of the denylist, only active for
    non-``flags.py`` files -- proven both to fire when active..."""
    violations = _boundary_violations(source, filename=label, is_flags_module=False)
    assert violations != [], f"{label}: load-contract import was not caught"


def test_boundary_scanner_does_not_flag_the_load_contract_inside_flags() -> None:
    """...and proven not to fire for ``flags.py`` itself, which is
    sanctioned to import exactly this name."""
    source = "from fitdocs.load.types import QualityFlag\n"
    violations = _boundary_violations(source, filename="flags.py", is_flags_module=True)
    assert violations == [], (
        f"flags.py's sanctioned import was wrongly flagged: {violations}"
    )


def test_boundary_scanner_does_not_flag_sanctioned_imports() -> None:
    """Negative control: the real, legitimate cross-package imports this
    package uses (design.md's dependency graph: channels, benchmarks,
    metrics, model, and intra-package relative imports) must never be
    flagged."""
    sanctioned_sources = [
        "from fitdocs.load.channels.types import ChannelId, ChannelLoad\n",
        "from fitdocs.load.channels.sufficiency import stream_coverage\n",
        "from fitdocs.load.channels.sources import Citation\n",
        "from fitdocs.benchmarks import Benchmark, benchmark_age\n",
        "from fitdocs.metrics.types import DerivedMetrics\n",
        "from fitdocs.model import Activity, Modality, Samples\n",
        "from .types import FlagSettings\n",
        "from . import cadence, divergence, drift, staleness\n",
        "import statistics\n",
        "from dataclasses import dataclass\n",
    ]
    for source in sanctioned_sources:
        violations = _boundary_violations(
            source, filename="<sanctioned>", is_flags_module=False
        )
        assert violations == [], (
            f"sanctioned import wrongly flagged: {source!r} -> {violations}"
        )


# ===========================================================================
# Bullet 1: no I/O, no path in/out, no clock, no random source, no LLM.
# ===========================================================================

_FORBIDDEN_IO_OR_RANDOM_MODULES: tuple[str, ...] = (
    "pathlib",
    "random",
    "secrets",
    "time",
    "requests",
    "urllib",
    "http",
    "socket",
    "ftplib",
    "smtplib",
    "httpx",
    "subprocess",
    "openai",
    "anthropic",
    "langchain",
)

_FORBIDDEN_CLOCK_ATTRS = frozenset({"now", "today", "utcnow"})
_FORBIDDEN_CALL_NAMES = frozenset({"open"})


def _side_effect_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """AST scan for forbidden I/O, clock, random and LLM references. Type
    imports of ``date``/``datetime`` are fine (``staleness.py`` and
    ``flags.py`` both legitimately take a ``date`` parameter) -- it is a
    *call* to a clock-reading method, an import of a forbidden module, or a
    call to a forbidden builtin that is flagged, never the type name."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _FORBIDDEN_IO_OR_RANDOM_MODULES:
                    violations.append(f"{filename}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if top in _FORBIDDEN_IO_OR_RANDOM_MODULES:
                violations.append(f"{filename}:{node.lineno}: from {module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALL_NAMES:
                violations.append(f"{filename}:{node.lineno}: {func.id}(...) call")
            elif (
                isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_CLOCK_ATTRS
            ):
                violations.append(
                    f"{filename}:{node.lineno}: .{func.attr}(...) clock call"
                )
            elif isinstance(func, ast.Attribute) and func.attr == "open":
                violations.append(f"{filename}:{node.lineno}: .open(...) call")
    return violations


def test_package_performs_no_io_consults_no_clock_or_random_no_llm() -> None:
    py_files = sorted(_QA_DIR.glob("*.py"))
    assert len(py_files) == 8, "vacuous walk -- see the file-discovery test"

    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _side_effect_violations(
            path.read_text(encoding="utf-8"), filename=path.name
        )
        if found:
            violations[path.name] = found

    assert violations == {}, (
        f"forbidden I/O, clock, random or LLM reference(s): {violations}"
    )


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("injected_open_call", "def f(p):\n    return open(p)\n"),
        (
            "injected_datetime_now",
            "from datetime import datetime\ndef f():\n    return datetime.now()\n",
        ),
        (
            "injected_date_today",
            "from datetime import date\ndef f():\n    return date.today()\n",
        ),
        ("injected_random_import", "import random\n"),
        ("injected_secrets_import", "import secrets\n"),
        ("injected_pathlib_import", "import pathlib\n"),
        ("injected_requests_import", "import requests\n"),
        ("injected_openai_import", "import openai\n"),
    ],
)
def test_side_effect_scanner_catches_every_injected_violation(
    label: str, source: str
) -> None:
    violations = _side_effect_violations(source, filename=label)
    assert violations != [], f"{label}: injected violation was not caught"


def test_side_effect_scanner_does_not_flag_the_legitimate_date_type_usage() -> None:
    """Negative control: ``staleness.py`` and ``flags.py`` legitimately take
    and use a ``date`` *type* (never call a clock method on it)."""
    source = (
        "from datetime import date\n"
        "def f(activity_date: date, window_days: int) -> bool:\n"
        "    return activity_date.toordinal() > window_days\n"
    )
    violations = _side_effect_violations(source, filename="<legit>")
    assert violations == [], f"legitimate date-type usage wrongly flagged: {violations}"


# ===========================================================================
# Bullet 1 (continued): no function signature names a filesystem path.
# ===========================================================================


def _path_annotated_signatures(source: str, *, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    found: list[str] = []

    def _names_path(expr: ast.expr | None) -> bool:
        if expr is None:
            return False
        for sub in ast.walk(expr):
            if isinstance(sub, ast.Name) and sub.id == "Path":
                return True
            if isinstance(sub, ast.Attribute) and sub.attr == "Path":
                return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # Round-2 review finding 3: every argument kind, not just
            # ``args``/``kwonlyargs`` -- ``posonlyargs`` (``def f(p: Path,
            # /)``), ``vararg`` (``def f(*paths: Path)``) and ``kwarg``
            # (``def f(**paths: Path)``) can each carry a ``Path``
            # annotation too.
            arg_holders: list[ast.arg] = list(node.args.posonlyargs) + list(
                node.args.args
            )
            arg_holders += list(node.args.kwonlyargs)
            if node.args.vararg is not None:
                arg_holders.append(node.args.vararg)
            if node.args.kwarg is not None:
                arg_holders.append(node.args.kwarg)
            annotations = [
                a.annotation for a in arg_holders if a.annotation is not None
            ]
            if node.returns is not None:
                annotations.append(node.returns)
            if any(_names_path(a) for a in annotations):
                found.append(f"{filename}:{node.lineno}: {node.name}")
    return found


def test_no_function_signature_names_a_filesystem_path() -> None:
    py_files = sorted(_QA_DIR.glob("*.py"))
    assert len(py_files) == 8, "vacuous walk -- see the file-discovery test"

    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _path_annotated_signatures(
            path.read_text(encoding="utf-8"), filename=path.name
        )
        if found:
            violations[path.name] = found

    assert violations == {}, f"function signature(s) naming a Path: {violations}"


def test_path_signature_scanner_catches_an_injected_path_parameter() -> None:
    source = "from pathlib import Path\ndef f(p: Path) -> None:\n    pass\n"
    found = _path_annotated_signatures(source, filename="<injected>")
    assert found != [], "injected Path-typed parameter was not caught"


def test_path_signature_scanner_catches_an_injected_path_return() -> None:
    source = "from pathlib import Path\ndef f() -> Path:\n    ...\n"
    found = _path_annotated_signatures(source, filename="<injected>")
    assert found != [], "injected Path-typed return was not caught"


@pytest.mark.parametrize(
    ("label", "source"),
    [
        # Round-2 review finding 3: positional-only, *args and **kwargs
        # annotations, none of which the round-1 scanner inspected.
        ("posonly", "from pathlib import Path\ndef f(p: Path, /):\n    pass\n"),
        ("vararg", "from pathlib import Path\ndef f(*paths: Path):\n    pass\n"),
        ("kwarg", "from pathlib import Path\ndef f(**paths: Path):\n    pass\n"),
    ],
)
def test_path_signature_scanner_catches_every_argument_kind(
    label: str, source: str
) -> None:
    found = _path_annotated_signatures(source, filename=label)
    assert found != [], f"{label}: injected Path-typed argument was not caught"


# ===========================================================================
# Bullet 3: the computed load value is bit-identical with and without
# verdicts -- the never-a-load-combiner constraint made mechanical.
# ===========================================================================


def _summary() -> SessionSummary:
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def _run_activity() -> Activity:
    n = 601
    time_s = tuple(float(i) for i in range(n))
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    distance = tuple(4.0 * i for i in range(n))
    samples = Samples(
        time_s=time_s,
        heart_rate_bpm=none_ints,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=distance,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=Sport.RUN,
        modality=Modality.RUN,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


_ANCHOR_DATE = date(2026, 1, 1)


class _StubProfileWithPace:
    """A minimal :class:`ProfileView` double carrying exactly one
    threshold-pace benchmark, enough for ``resolve_anchors`` to produce a
    real :class:`ResolvedAnchors` for a Run without pulling in
    ``athlete-benchmarks``."""

    def get_number(self, key: str) -> float | None:
        return None

    def benchmark(
        self, kind: object, *, discipline: object, on: object
    ) -> Benchmark | None:
        if kind == BenchmarkKind.THRESHOLD_PACE_S_PER_KM:
            return Benchmark(
                kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
                discipline=Sport.RUN,
                value=240.0,
                measured_on=_ANCHOR_DATE,
            )
        return None

    def has_benchmark(self, kind: object, *, discipline: object) -> bool:
        return kind == BenchmarkKind.THRESHOLD_PACE_S_PER_KM


def test_build_result_value_is_bit_identical_with_and_without_flags() -> None:
    """The mechanical proof design.md's "never a load combiner" language
    calls for: identical selection inputs, differing only in ``flags``,
    yield byte-identical ``value``/``basis``/``non_selected``/
    ``inputs_used``/``notes`` -- everything except ``.flags`` itself.
    Task 3.2's own ``test_build_result_flags_reach_only_the_flags_field``
    covers similar ground at the calculator's own test-file boundary; this
    module owns proving it as this package's own boundary guarantee, per
    this task's Observable ("fails ... on any change that would let a
    verdict reach a load value")."""
    activity = _run_activity()
    metrics = DerivedMetrics(normalized_power_w=None, moving_time_s=600.0)
    settings = SufficiencySettings()
    anchor_benchmark = Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=240.0,
        measured_on=_ANCHOR_DATE,
    )
    outcome = pace_compute(
        activity, metrics, threshold_pace=anchor_benchmark, settings=settings
    )
    from fitdocs.load.channels.types import ChannelLoad

    assert isinstance(outcome, ChannelLoad), (
        f"fixture must select a real ChannelLoad, got {outcome!r}"
    )

    # non_selected_values() reads every CANONICAL_CHANNELS entry, so power
    # and heart-rate outcomes must be present too (both insufficient here --
    # the fixture activity carries no power or heart-rate stream).
    outcomes = {
        ChannelId.PACE: outcome,
        ChannelId.POWER: power_compute(activity, metrics, ftp=None, settings=settings),
        ChannelId.HEART_RATE: heart_rate_compute(
            activity,
            metrics,
            lthr=None,
            resting_hr=None,
            max_hr=None,
            settings=settings,
        ),
    }
    order = (ChannelId.PACE,)
    anchors = resolve_anchors(_StubProfileWithPace(), sport=Sport.RUN, on=_ANCHOR_DATE)

    real_flags = (
        QualityFlag(
            key="cadence-lock",
            label="Cadence lock",
            verdict="detected",
            detail="synthetic",
        ),
        QualityFlag(
            key="benchmark-staleness",
            label="Benchmark staleness",
            verdict="not-assessed",
            detail="synthetic",
        ),
    )

    without_flags = build_result(
        selected=outcome,
        outcomes=outcomes,
        order=order,
        anchors=anchors,
        discipline=Sport.RUN,
    )
    with_flags = build_result(
        selected=outcome,
        outcomes=outcomes,
        order=order,
        anchors=anchors,
        discipline=Sport.RUN,
        flags=real_flags,
    )

    assert without_flags.flags == ()
    assert with_flags.flags == real_flags
    for field_name in (
        "calculator_id",
        "display_name",
        "value",
        "basis",
        "non_selected",
        "inputs_used",
        "notes",
    ):
        assert getattr(without_flags, field_name) == getattr(with_flags, field_name), (
            f"{field_name} differs between with-flags and without-flags results -- "
            f"a verdict reached a field it must not"
        )


# ===========================================================================
# Bullet 4: registers no calculator, resolves no benchmark, selects no
# channel, touches no coverage table.
# ===========================================================================


def test_importing_qa_registers_no_additional_calculator() -> None:
    """Importing ``fitdocs.load.qa`` registers no additional calculator
    beyond the one ``fitdocs.load.__init__`` already registers -- run in a
    fresh subprocess, since the rest of the suite has already imported
    ``fitdocs.load.qa`` by the time this test runs in-process.

    **Round-2 review finding 2, corrected.** The prior revision of this test
    also asserted ``registry.available()`` was identical immediately before
    and immediately after an explicit ``import fitdocs.load.qa`` line, with
    a docstring claiming that comparison proved isolation. It did not:
    ``src/fitdocs/load/__init__.py`` line 32 already does
    ``from fitdocs.load.qa import FlagKey, FlagSettings``, so by the time
    ``from fitdocs.load import registry`` (this script's own first line)
    finishes -- which requires fully executing ``fitdocs/load/__init__.py``,
    package initializers always run in full before any of their attributes
    are accessible -- ``fitdocs.load.qa`` is already in ``sys.modules`` and
    the calculator is already registered. The subsequent explicit
    ``import fitdocs.load.qa`` was therefore always a cache hit, and
    ``before == after`` compared the registry against itself with nothing
    happening in between; it never exercised the mechanism the docstring
    described. The only assertion that ever did real work was
    ``len(after) == 1`` -- confirmed by the round-2 reviewer injecting a
    rogue registration into ``qa/__init__.py`` and observing
    ``before == after`` stay ``True`` while ``len(after) == 1`` correctly
    went red. That one assertion is kept below, honestly labeled; the
    vacuous comparison is dropped rather than kept as false evidence."""
    script = (
        "from fitdocs.load import registry\n"
        "import fitdocs.load.qa\n"
        "after = registry.available()\n"
        "assert len(after) == 1, after\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK", result.stdout
