"""The channel layer's boundary, proved by import and by behavior (task 4.2).

Covers Requirements 1.10, 8.3, 9.1-9.7 -- see
``.kiro/specs/load-channels/requirements.md`` and design.md's "Package
surface -- ``src/fitdocs/load/channels/__init__.py`` and the pin"
(ChannelSurface / PublicSurfacePin) section. This module owns exactly one
thing task 4.1 does not: the *boundary*, not the *surface*. Task 4.1's
``tests/test_public_api.py`` pins what the package publishes; this module
pins what the package may depend on, what interfaces it may touch, that it
is deterministic, and that every numeric constant it defines is cited.

**Maintainer ruling 2026-08-25 (see ``tasks.md`` task 4.2), declared
deviation from design.md:1239-1241.** design.md says importing
``fitdocs.load.channels`` must import none of ``engine``, ``registry``,
``profile``, ``types``, ``settings``, ``cli`` or ``render``. Three of those
seven -- ``registry``, ``settings``, ``types`` -- are **structurally
unassertable at package-import granularity**: Python executes a package's
own ``__init__.py`` before any of its subpackages, and
``src/fitdocs/load/__init__.py`` imports all three of ``fitdocs.load.registry``,
``fitdocs.load.settings`` and ``fitdocs.load.types`` at module scope (its own
lines 18, 28, 33) -- before ``fitdocs.load.channels`` is ever reached.
Measured identically on ``main`` at ``2a1cc3b`` (pre-dating this whole
feature) and on this branch (see
:func:`test_measured_premise_the_three_names_leak_from_the_parent_package`
below), so no edit inside ``channels/`` can change it -- the leak happens one
import earlier, in code this task's boundary does not reach. This module
therefore asserts the design's *intent* -- the dependency runs one way, from
``channels`` toward nothing else in ``fitdocs.load`` -- via **two**
complementary assertions instead of the one design.md names:

* :func:`test_package_import_excludes_the_four_genuinely_absent_load_modules`
  -- package-import level, the four names design.md lists that really are
  absent from ``sys.modules`` after ``import fitdocs.load.channels``:
  ``engine``, ``profile``, ``cli``, ``render``.
* :func:`test_no_leaf_module_imports_a_fitdocs_load_sibling` -- leaf level,
  covering all seven names (plus any future one): no ``.py`` file *inside*
  ``fitdocs/load/channels/`` imports anything under ``fitdocs.load`` other
  than ``fitdocs.load.channels`` itself. This is the property the design is
  actually protecting -- the dependency direction -- and it does not inherit
  the parent-package leak, because it inspects each leaf module's own
  source, not the process-wide ``sys.modules`` table a parent import
  populates first.

Amending design.md to record this split is tracked separately at queue item
``2026-08-24-channels-package-import-purity-unsatisfiable`` and is out of
this task's boundary (read-only).

**Round-3 debug-directed fix, 2026-08-25.** Rounds 1 and 2 of this task both
shipped a *denylist* over AST spellings of forbidden constructs
(:func:`_sibling_load_imports`'s three hand-written branches,
``_FORBIDDEN_IO_MODULES``'s enumerated module list) and both were rejected
for the identical defect: that enumeration is unbounded. Round 2's own fix
-- six more spellings -- was found by round 2's own review to have five more
survivors in the same family, one inside the guard file the fix itself was
written in. The "Allowlist-shaped structural guard" section below replaces
the *load-bearing* role of both denylists with six exhaustive allowlists
over the module's own global namespace (imports, builtins, dunder attribute
access, def/class names, module-level bindings, ``Sport``/``Modality``
member references), on a completeness argument that does not depend on
having enumerated every spelling -- see that section's own banner comment
for the argument and the corrected Requirement 1.10 / 8.3 / 9.1-9.8 sweep.
The two superseded denylists are kept below, demoted to diagnostics only
(their own docstrings say so); nothing below relies on them for coverage
any more.
"""

from __future__ import annotations

import ast
import builtins
import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate, pace, power
from fitdocs.load.channels.types import ChannelLoad, SufficiencySettings
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

_CHANNELS_DIR = (
    Path(__file__).resolve().parents[3] / "src" / "fitdocs" / "load" / "channels"
)
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ===========================================================================
# Shared fixture builders (duplicated in miniature from the channel test
# modules deliberately). ``tests/load/channels/`` *is* a package
# (``__init__.py`` present; ``importlib.import_module`` on a sibling test
# module succeeds) -- importing fixtures from ``test_power.py`` et al. is
# mechanically possible. The duplication is kept anyway: this module owns no
# channel-specific behavior of its own, and importing production-adjacent
# fixtures from a *test* module would make this module's own vacuity and
# fixture-discrimination guarantees depend on an unrelated file changing
# shape, which is the coupling the rest of this module goes out of its way
# to avoid everywhere else.
# ===========================================================================


def _none_floats(n: int) -> tuple[float | None, ...]:
    return (None,) * n


def _samples(
    time_s: tuple[float, ...],
    *,
    power_w: tuple[int | None, ...] | None = None,
    heart_rate_bpm: tuple[int | None, ...] | None = None,
    distance_m: tuple[float | None, ...] | None = None,
) -> Samples:
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm if heart_rate_bpm is not None else none_ints,
        power_w=power_w if power_w is not None else none_ints,
        cadence_rpm=_none_floats(n),
        speed_mps=_none_floats(n),
        distance_m=distance_m if distance_m is not None else _none_floats(n),
        altitude_m=_none_floats(n),
        latitude_deg=_none_floats(n),
        longitude_deg=_none_floats(n),
        temperature_c=_none_floats(n),
    )


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


def _activity(*, modality: Modality, sport: Sport, samples: Samples) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


_SETTINGS = SufficiencySettings()
_DENSE_TIME = tuple(float(i) for i in range(3601))


def _power_call() -> tuple[Activity, DerivedMetrics, Benchmark, SufficiencySettings]:
    activity = _activity(
        modality=Modality.BIKE,
        sport=Sport.RIDE,
        samples=_samples(_DENSE_TIME, power_w=tuple(200 for _ in range(3601))),
    )
    metrics = DerivedMetrics(normalized_power_w=180.0, moving_time_s=3600.0)
    ftp = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=200.0,
        measured_on=date(2026, 1, 1),
    )
    return activity, metrics, ftp, _SETTINGS


def _heart_rate_call() -> tuple[
    Activity, DerivedMetrics, Benchmark, Benchmark, Benchmark, SufficiencySettings
]:
    activity = _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=_samples(_DENSE_TIME, heart_rate_bpm=tuple(140 for _ in range(3601))),
    )
    metrics = DerivedMetrics()
    lthr = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=None,
        value=165.0,
        measured_on=date(2026, 1, 1),
    )
    resting = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=50.0,
        measured_on=date(2026, 1, 1),
    )
    maxhr = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190.0,
        measured_on=date(2026, 1, 1),
    )
    return activity, metrics, lthr, resting, maxhr, _SETTINGS


def _pace_call() -> tuple[Activity, DerivedMetrics, Benchmark, SufficiencySettings]:
    distance_m = tuple(3.6 * i for i in range(3601))
    activity = _activity(
        modality=Modality.RUN,
        sport=Sport.RUN,
        samples=_samples(_DENSE_TIME, distance_m=distance_m),
    )
    metrics = DerivedMetrics(moving_time_s=3600.0)
    threshold_pace = Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=278.0,
        measured_on=date(2026, 1, 1),
    )
    return activity, metrics, threshold_pace, _SETTINGS


# ===========================================================================
# (a) Package-import level: the four genuinely-absent names (maintainer
#     ruling, bullet 1).
# ===========================================================================

# The two-name ambiguity in the task/design wording for "cli" and "render"
# (no ``fitdocs.load.cli`` module exists on disk -- only top-level
# ``fitdocs.cli`` -- and both ``fitdocs.load.render`` and top-level
# ``fitdocs.render`` exist) is resolved by checking every plausible reading
# rather than picking one: all five are asserted absent.
_PACKAGE_LEVEL_FORBIDDEN = (
    "fitdocs.load.engine",
    "fitdocs.load.profile",
    "fitdocs.cli",
    "fitdocs.render",
    "fitdocs.load.render",
)

_PACKAGE_IMPORT_PROBE = """\
import sys
import fitdocs.load.channels
present = sorted(m for m in sys.modules if m.startswith("fitdocs."))
forbidden = {forbidden!r}
leaked = sorted(m for m in forbidden if m in sys.modules)
print(len(present))
print(",".join(leaked))
"""


def test_measured_premise_the_three_names_leak_from_the_parent_package() -> None:
    """Positive control for the whole module's framing: proves, freshly,
    that ``registry``/``settings``/``types`` really do land in
    ``sys.modules`` merely from ``import fitdocs.load.channels`` -- not
    because ``channels`` imports them, but because ``fitdocs/load/__init__.py``
    (lines 18, 28, 33) imports all three before ``channels`` is ever
    reached. If a future edit to ``fitdocs/load/__init__.py`` stopped doing
    that, this test would fail, which is the signal that the maintainer
    ruling's premise no longer holds and design.md's original wording
    should be re-tried.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _PACKAGE_IMPORT_PROBE.format(forbidden=())],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=_REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, fitdocs.load.channels\n"
            'print("\\n".join(sorted(m for m in sys.modules '
            'if m.startswith("fitdocs."))))',
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=_REPO_ROOT,
    )
    assert probe.returncode == 0, probe.stderr
    present = set(probe.stdout.splitlines())
    leaked_siblings = {
        "fitdocs.load.registry",
        "fitdocs.load.settings",
        "fitdocs.load.types",
    }
    assert leaked_siblings <= present, (
        f"expected {leaked_siblings} to leak from the parent package's own "
        f"__init__.py; measured sys.modules only contained {present}"
    )


def test_package_import_excludes_the_four_genuinely_absent_load_modules() -> None:
    """Package-import-level half of the maintainer ruling: none of the four
    modules design.md names that are genuinely absent from
    ``fitdocs/load/__init__.py``'s own eager imports appear in
    ``sys.modules`` after ``import fitdocs.load.channels``, in a fresh
    subprocess so no earlier test's imports can pollute the answer.
    """
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _PACKAGE_IMPORT_PROBE.format(forbidden=_PACKAGE_LEVEL_FORBIDDEN),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=_REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    present_count_line, leaked_line = completed.stdout.splitlines()
    present_count = int(present_count_line)
    leaked = [m for m in leaked_line.split(",") if m]
    assert present_count > 10, (
        "vacuous import: fewer than 10 fitdocs.* modules loaded after "
        "'import fitdocs.load.channels' -- the probe is not exercising the "
        "real package"
    )
    assert leaked == [], f"forbidden module(s) leaked into sys.modules: {leaked}"


def test_package_level_probe_actually_detects_a_forbidden_import() -> None:
    """Fixture-discrimination companion for the probe script above: proves
    the detection logic itself -- not the real ``channels`` package, which
    this task's boundary forbids editing -- can catch a genuine leak. Runs
    the identical probe against a subprocess that imports one of the four
    forbidden modules directly (simulating what a future ``channels/__init__.py``
    edit importing ``fitdocs.load.engine`` would produce) and confirms the
    ``leaked`` list is non-empty. Measured: ``fitdocs.load.engine`` itself
    eagerly imports ``fitdocs.load.profile`` and ``fitdocs.load.render`` (its
    own lines 107, 115), so injecting it also leaks those two transitively --
    a stronger result than injecting just one name, asserted as a superset
    rather than an exact match so a future change to ``engine.py``'s own
    imports cannot silently break this companion.
    """
    script = """\
import sys
import fitdocs.load.engine  # simulates a forbidden import inside channels/
import fitdocs.load.channels
present = sorted(m for m in sys.modules if m.startswith("fitdocs."))
forbidden = ("fitdocs.load.engine", "fitdocs.load.profile", "fitdocs.cli",
             "fitdocs.render", "fitdocs.load.render")
leaked = sorted(m for m in forbidden if m in sys.modules)
print(len(present))
print(",".join(leaked))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=_REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    _, leaked_line = completed.stdout.splitlines()
    leaked = set(leaked_line.split(","))
    assert "fitdocs.load.engine" in leaked, (
        f"probe failed to detect the injected forbidden import: {leaked}"
    )


# ===========================================================================
# (b) Leaf level: no module inside channels/ imports any fitdocs.load.*
#     sibling at all (covers all seven names, plus any future one).
# ===========================================================================


def _sibling_load_imports(source: str, *, filename: str = "<test>") -> list[str]:
    """**Demoted to a diagnostic, 2026-08-25 (round 3) -- no longer the
    load-bearing guard against a ``fitdocs.load`` sibling import.** This
    function's prior docstring asserted the dynamic-import class of escape
    "is closed" and named ``fitdocs.load.types`` as its own worked example --
    the exact module a two-line mutation (``_f = importlib.import_module``
    then ``_f("fitdocs.load.types")``) defeated it with in round 2's review.
    That claim is retracted here. The load-bearing guard against *any*
    external import (siblings under ``fitdocs.load`` included) is now
    :func:`_import_allowlist_violations` in the "Allowlist-shaped structural
    guard" section below, which pins the exhaustive set of sanctioned import
    *targets* rather than enumerating forbidden call-site *spellings* of
    reaching an unsanctioned one, and is not defeated by aliasing, by
    rebinding ``importlib.import_module`` to a new name, or by any dynamic
    call-site shape this function does not happen to match.

    What remains genuinely useful here, and why this function is kept rather
    than deleted: it still runs (via
    :func:`test_no_leaf_module_imports_a_fitdocs_load_sibling`, still
    exercised below) and, on the specific spellings it recognizes, produces a
    more specific and more readable failure message -- naming the resolved
    sibling module and the exact import spelling -- than the allowlist's
    generic "target not allowlisted". It is a diagnostic convenience layered
    on top of a guard that no longer needs it to be sound, not a second
    independent line of defense against every one of its own recognized
    spellings equally: nine of the eleven spellings
    :func:`test_sibling_import_detection_catches_every_reported_spelling`
    below exercises are also independently caught by
    :func:`_import_allowlist_violations` (verified directly, not assumed --
    each targets an import statement outside the twelve sanctioned targets).
    Two are not: ``importlib.import_module("fitdocs.load.types")`` and
    ``__import__("fitdocs.load.registry")`` as bare *call* fixtures with no
    accompanying import statement in the same synthetic source. Those two
    specific fixtures are artifacts of the unit -- a real leaf module would
    need ``import importlib`` (caught by the import allowlist) or a bare
    ``__import__`` reference (caught by :func:`_builtin_allowlist_violations`
    instead, as `dunder_import` in
    :func:`test_builtin_allowlist_detection_catches_every_dangerous_builtin`
    above exercises) to reach either call at all -- but stated as measured
    fact about these two fixtures specifically, not glossed over as "every
    spelling", since that overclaim is exactly this task's recurring defect.
    """
    tree = ast.parse(source, filename=filename)
    forbidden: list[str] = []

    def _resolve(node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        dots = "." * node.level
        name = dots + (node.module or "")
        try:
            return importlib.util.resolve_name(name, "fitdocs.load.channels")
        except ImportError:
            return None

    def _is_sibling(resolved: str | None) -> bool:
        if resolved is None:
            return False
        if resolved == "fitdocs.load" or resolved.startswith("fitdocs.load."):
            return not (
                resolved == "fitdocs.load.channels"
                or resolved.startswith("fitdocs.load.channels.")
            )
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_sibling(alias.name):
                    forbidden.append(f"import {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve(node)
            imported_names = {alias.name for alias in node.names}
            if resolved == "importlib" and "import_module" in imported_names:
                forbidden.append(
                    f"from importlib import import_module (line {node.lineno})"
                )
            elif resolved == "fitdocs" and "load" in imported_names:
                forbidden.append(
                    f"from fitdocs import load (line {node.lineno}) -- grants "
                    f"attribute access to every fitdocs.load sibling"
                )
            elif resolved == "fitdocs.load":
                extra = imported_names - {"channels"}
                if extra:
                    forbidden.append(
                        f"from fitdocs.load import {sorted(extra)} (line {node.lineno})"
                    )
            elif _is_sibling(resolved):
                spelling = ("." * node.level) + (node.module or "")
                forbidden.append(
                    f"from {spelling} import ... "
                    f"(resolves to {resolved}, line {node.lineno})"
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in (
                "__import__",
                "import_module",
            ):
                forbidden.append(f"{func.id}(...) call (line {node.lineno})")
            elif isinstance(func, ast.Attribute) and func.attr == "import_module":
                forbidden.append(
                    f"importlib.import_module(...) call (line {node.lineno})"
                )

    return forbidden


def test_no_leaf_module_imports_a_fitdocs_load_sibling() -> None:
    """Leaf-level half of the maintainer ruling: no ``.py`` file under
    ``src/fitdocs/load/channels/`` imports anything under ``fitdocs.load``
    other than ``fitdocs.load.channels`` (itself). This is the property
    design.md's package-level wording was protecting, stated at the
    granularity where it is actually assertable.
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        f"vacuous walk: expected at least 9 modules under {_CHANNELS_DIR}, "
        f"found {len(py_files)} -- the walk is looking at the wrong directory"
    )
    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _sibling_load_imports(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if found:
            violations[path.name] = found
    assert violations == {}, f"forbidden fitdocs.load.* sibling import(s): {violations}"


def test_sibling_import_detection_catches_every_reported_spelling() -> None:
    """Fixture-discrimination companion for :func:`_sibling_load_imports`,
    run against synthetic sources (this task's boundary forbids editing the
    real channel modules to prove the same point).
    """
    offenders = {
        "absolute_import": "import fitdocs.load.settings\n",
        "absolute_import_from": "from fitdocs.load.settings import LoadSettings\n",
        "relative_level_2": "from ..settings import LoadSettings\n",
        "relative_level_2_module": "from .. import settings\n",
        "parent_then_attribute": "from fitdocs.load import settings\n",
        "dynamic_import_module": 'importlib.import_module("fitdocs.load.types")\n',
        "dunder_import": '__import__("fitdocs.load.registry")\n',
        # Finding 2 remediation: the bare-name call form, reached via
        # `from importlib import import_module` (an ast.Name func, not an
        # ast.Attribute) -- the standard idiom, previously unmatched.
        "importlib_bare_import_statement": "from importlib import import_module\n",
        "importlib_bare_call": (
            "from importlib import import_module\n"
            'import_module("fitdocs.load.settings")\n'
        ),
        # Finding 6 remediation: the parent-then-attribute form one level up
        # from `from fitdocs.load import types` -- `from fitdocs import
        # load` grants attribute access to every fitdocs.load sibling
        # (registry, settings, types, ...) without "fitdocs.load" ever
        # appearing as a dotted prefix on the imported name.
        "grandparent_then_attribute": "from fitdocs import load\n",
        "grandparent_then_attribute_aliased": "from fitdocs import load as _load\n",
    }
    for label, source in offenders.items():
        found = _sibling_load_imports(source)
        assert found != [], f"{label}: offending import was not caught"

    # negative controls: sanctioned intra-package imports must never be
    # flagged, at every spelling this package's real leaf modules actually
    # use (measured against the real files above).
    sanctioned = {
        "self_relative": "from .types import ChannelId\n",
        "self_relative_level_1_module": "from . import types\n",
        "self_absolute": "from fitdocs.load.channels.types import ChannelId\n",
        "self_parent_then_attribute": "from fitdocs.load import channels\n",
        "unrelated_stdlib": "import math\n",
        "unrelated_third_party": "from fitdocs.model import Samples\n",
        "unrelated_import_module_name": "import_module_registry = {}\n",
    }
    for label, source in sanctioned.items():
        found = _sibling_load_imports(source)
        assert found == [], f"{label}: false positive on a sanctioned import: {found}"


# ===========================================================================
# Interface-purity: no filesystem, network, clock, or prompting reference.
# ===========================================================================

_FORBIDDEN_IO_MODULES = (
    "pathlib",
    "os",
    "io",
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "time",
    "random",
    # Finding 7 remediation: unambiguous filesystem/process/prompting
    # modules missed by the prior sweep -- none has a legitimate use inside
    # a pure channel-computation layer (Req 1.10: "read no file ... prompt
    # for nothing").
    "subprocess",
    "tempfile",
    "shutil",
    "glob",
    "getpass",
)
_CLOCK_ATTRS = ("now", "today", "utcnow")
# `sys.stdin` specifically (not all of `sys`, which has legitimate
# non-IO uses such as `sys.maxsize`) -- matched the same
# bare-``ast.Attribute`` way as the clock attrs, per Finding 7.
_PROMPT_ATTRS = ("stdin",)
_FORBIDDEN_BUILTIN_CALLS = ("open", "input")


def _interface_references(source: str, *, filename: str = "<test>") -> list[str]:
    """Every reference in ``source`` to a filesystem, network, process,
    clock, or prompting interface: a forbidden stdlib import (including,
    since Finding 7, ``subprocess``/``tempfile``/``shutil``/``glob``/
    ``getpass``), a bare ``open``/``input`` call, a ``.now``/``.today``/
    ``.utcnow`` attribute access, or a ``.stdin`` attribute access (matched
    as a bare :class:`ast.Attribute`, not only when it is a call's ``func``,
    so an aliased reference such as ``_clock = date.today`` or
    ``_in = sys.stdin`` is caught the same as ``date.today()`` -- the exact
    defect shape ``test_contract.py``'s sibling guard documents for the same
    reason).

    **Demoted, 2026-08-25 (round 3), corrected 2026-08-25 (round 4): the
    stdlib-import half of this helper** (``_FORBIDDEN_IO_MODULES``) is no
    longer load-bearing -- every module it names is, by construction, absent
    from the exhaustive allowlist :func:`_import_allowlist_violations`
    checks against, so any import this half catches, that function catches
    too (and catches more of, since it is not limited to a hand-picked
    list). It is kept as a diagnostic for the same reason
    :func:`_sibling_load_imports` is: a more specific failure message on the
    spellings it recognizes. **What remains genuinely load-bearing here, and
    not subsumed by the allowlist section:** the ``open``/``input``
    builtin-call detection is subsumed by the builtin allowlist below
    (neither is in ``_ALLOWED_BUILTINS``), but the
    ``.now``/``.today``/``.utcnow`` clock *attribute*-access detection is
    **not** subsumed -- round 4's import allowlist pins imported *names*,
    not attribute access on an object already reached through a sanctioned
    import, and every leaf already receives ``Benchmark`` instances (a
    sanctioned type) carrying a ``measured_on: date`` field, so
    ``some_benchmark.measured_on.today()`` reaches a live ``date`` object
    without any import of ``datetime`` at all -- the allowlist sections pin
    imports, builtins, def/class names, and module-level bindings, but do
    not restrict ordinary (non-dunder) attribute access on an object reached
    through a sanctioned channel, so the clock-attribute check is the sole
    guard against that specific reach and stays load-bearing.
    (Round-3 correction, round-4 fixed: round 3's docstring here claimed
    ``datetime`` "is not a sanctioned import target, so a leaf cannot reach
    the clock by importing it directly" as if that closed the import route
    entirely -- it did not: round 3's target-only allowlist sanctioned all
    of ``fitdocs.model``, and ``from fitdocs.model import datetime`` (a real,
    live attribute of that module -- verified: ``fitdocs.model.datetime is
    datetime.datetime``) reached the same live clock class directly, no
    ``Benchmark`` object needed. Round 4's name-level allowlist closes that
    specific route, since ``datetime`` is not in ``fitdocs.model``'s
    allowlisted name set (``Activity``, ``Modality``, ``Samples``) -- but the
    ``Benchmark.measured_on`` route above is unaffected by that fix, since it
    needs no unsanctioned import at all, which is exactly why the
    clock-attribute check remains load-bearing rather than becoming fully
    redundant.)

    The ``.stdin`` half was claimed here, in round 3, to be "fully subsumed
    (no sanctioned import surfaces ``sys``)" -- **false as written**:
    ``dataclasses``, ``typing`` and ``enum`` each do their own internal
    ``import sys``, so each exposes ``sys`` as an ordinary attribute of
    itself, and round 3's target-only allowlist sanctioned all three targets
    without restricting which *names* could be pulled from them --
    ``from dataclasses import sys as _sys`` (and the ``typing``/``enum``
    equivalents) reached a live ``sys.modules`` before this round's fix,
    confirmed live against ``power.py`` (see the module banner comment).
    Round 4's name-level allowlist closes that specific route (``sys`` is
    not in any of the three targets' allowlisted name sets). A BFS attribute
    probe from eleven of the seventeen sanctioned import names (round 5:
    the other six -- ``annotations``, ``Sequence``, ``dataclass``,
    ``StrEnum``, ``Final``, ``Protocol`` -- are not walked by that probe;
    see U3's restatement below) finds no path to the ``sys`` module today
    (measured, not assumed -- see
    :func:`test_reachability_probe_finds_no_fitdocs_load_module_via_attribute_chains`'s
    sibling probe in this task's own investigation), so ``.stdin`` is, as far
    as this task's own probing establishes, subsumed by the name-level
    import allowlist for every route found so far -- kept here only for the
    more specific diagnostic message, not because a fresh, unfound route is
    claimed impossible.

    Req 1.10's "invoke no language model" clause is UNPINNED by this
    helper: there is no fixed set of stdlib names or attributes that names
    "call an LLM" the way ``open``/``socket``/``subprocess`` name filesystem
    or process interfaces, so no AST shape below asserts it.
    """
    tree = ast.parse(source, filename=filename)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _FORBIDDEN_IO_MODULES:
                    hits.append(f"import {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _FORBIDDEN_IO_MODULES:
                hits.append(f"from {node.module} import ... (line {node.lineno})")
        elif isinstance(node, ast.Attribute) and (
            node.attr in _CLOCK_ATTRS or node.attr in _PROMPT_ATTRS
        ):
            hits.append(f".{node.attr} reference (line {node.lineno})")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_BUILTIN_CALLS
        ):
            hits.append(f"{node.func.id}(...) call (line {node.lineno})")
    return hits


def test_no_module_references_a_filesystem_network_clock_or_prompting_interface() -> (
    None
):
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _interface_references(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if found:
            violations[path.name] = found
    assert violations == {}, f"forbidden interface reference(s): {violations}"


def test_interface_reference_detection_catches_every_reported_spelling() -> None:
    offenders = {
        "open_call": "open('x')\n",
        "input_call": "input()\n",
        "import_pathlib": "import pathlib\n",
        "import_os": "from os import path\n",
        "import_socket": "import socket\n",
        "import_time": "import time\n",
        "clock_call": "from datetime import date\ndate.today()\n",
        "clock_alias": "from datetime import date\n_clock = date.today\n",
        # Finding 7 remediation.
        "import_subprocess": "import subprocess\n",
        "import_tempfile": "import tempfile\n",
        "import_shutil": "import shutil\n",
        "import_glob": "import glob\n",
        "import_getpass": "import getpass\n",
        "stdin_reference": "import sys\n_in = sys.stdin\n",
        "stdin_call": "import sys\nsys.stdin.readline()\n",
    }
    for label, source in offenders.items():
        found = _interface_references(source)
        assert found != [], f"{label}: offending reference was not caught"

    sanctioned = {
        "recorded_date_field": (
            "from datetime import date\nmeasured_on: date\nx = measured_on.year\n"
        ),
        "unrelated_stdlib": "import math\nmath.sqrt(4)\n",
        "unrelated_call": "def f():\n    return 1\nf()\n",
        # `sys` itself has legitimate non-IO uses (e.g. sys.maxsize); only
        # `.stdin` is forbidden, not the whole module.
        "sys_non_stdin_attr": "import sys\nx = sys.maxsize\n",
    }
    for label, source in sanctioned.items():
        found = _interface_references(source)
        assert found == [], f"{label}: false positive: {found}"


# ===========================================================================
# No module selects between channels, computes a quality flag, resolves a
# benchmark, or maps a modality to a discipline.
# ===========================================================================

# The exact, current, intra-package import adjacency (module stem -> the
# fitdocs.load.channels.* submodules it imports from). Constructed by
# reading the real files, not invented -- see the raw grep this docstring is
# derived from in this task's own investigation. Asserted as an *exact*
# mapping (not a subset check) so it is a genuine structural pin: a future
# edit adding an import from ``power.py`` to ``heart_rate.py`` -- i.e. one
# channel starting to know about another, the shape a channel-selection
# function would need -- changes this mapping and reddens the assertion.
_EXPECTED_INTRA_PACKAGE_IMPORTS: dict[str, frozenset[str]] = {
    "__init__": frozenset(
        {"heart_rate", "pace", "power", "sources", "types", "weighting"}
    ),
    "grade": frozenset(),
    "heart_rate": frozenset({"sufficiency", "types", "weighting"}),
    "pace": frozenset({"grade", "sufficiency", "types"}),
    "power": frozenset({"sufficiency", "types"}),
    "sources": frozenset(),
    "sufficiency": frozenset({"types"}),
    "types": frozenset(),
    "weighting": frozenset(),
}


def _intra_package_imports(source: str, *, filename: str = "<test>") -> frozenset[str]:
    """The set of ``fitdocs.load.channels.<x>`` submodule stems ``source``
    imports from or imports directly, across every spelling this task's own
    mutation sweep exercised: relative-with-module (``from .x import Y``),
    absolute (``from fitdocs.load.channels.x import Y``), relative
    module-only (``from . import x``, where ``node.module is None`` and the
    stem lives in the imported *name* instead), and a bare/aliased
    ``ast.Import`` of the fully-qualified submodule
    (``import fitdocs.load.channels.x [as alias]``) -- the two spellings
    that landed green against ``power.py`` in the prior round because only
    ``ast.ImportFrom`` with a truthy ``node.module`` was inspected."""
    tree = ast.parse(source, filename=filename)
    stems: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("fitdocs.load.channels."):
                    rest = alias.name[len("fitdocs.load.channels.") :]
                    if rest:
                        stems.add(rest.split(".")[0])
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level > 0:
            if node.module:
                stems.add(node.module.split(".")[0])
            else:
                # from . import x / from .. import x -- the stem is the
                # imported name itself, not ``node.module`` (which is None).
                for alias in node.names:
                    stems.add(alias.name.split(".")[0])
        elif node.module and node.module.startswith("fitdocs.load.channels."):
            rest = node.module[len("fitdocs.load.channels.") :]
            if rest:
                stems.add(rest.split(".")[0])
    return frozenset(stems)


def test_no_channel_leaf_module_imports_another_channel_leaf_module() -> None:
    """Structural proof that no module selects between channels: the three
    ``compute`` entry points (``power.py``, ``heart_rate.py``, ``pace.py``)
    never import one another, which is what a channel-selecting function
    would require. Checked against the real files, with the exact expected
    adjacency asserted (not merely "no cross-channel edge") so the pin
    covers the whole package's dependency shape, not one hand-picked pair.
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    measured: dict[str, frozenset[str]] = {}
    for path in py_files:
        stem = path.stem
        measured[stem] = _intra_package_imports(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
    assert measured == _EXPECTED_INTRA_PACKAGE_IMPORTS

    leaves = {"power", "heart_rate", "pace"}
    for leaf in leaves:
        assert measured[leaf].isdisjoint(leaves - {leaf}), (
            f"{leaf}.py imports another channel leaf module directly: "
            f"{measured[leaf] & (leaves - {leaf})}"
        )


def test_intra_package_import_detection_is_sensitive_to_a_new_cross_channel_edge() -> (
    None
):
    """Fixture-discrimination companion: proves the walk actually reddens if
    a channel leaf module starts importing a sibling leaf module, using a
    synthetic source (the real files are out of this task's read-only
    boundary)."""
    found = _intra_package_imports("from .heart_rate import compute as hr\n")
    assert found == frozenset({"heart_rate"})
    found_absolute = _intra_package_imports(
        "from fitdocs.load.channels.pace import compute as p\n"
    )
    assert found_absolute == frozenset({"pace"})
    # Req 9.1 remediation: the two spellings that previously left
    # `test_no_channel_leaf_module_imports_another_channel_leaf_module` green
    # against a genuine cross-channel edge inserted into power.py --
    # `from . import heart_rate` (node.module is None at level 1) and a bare
    # `ast.Import` of the fully-qualified submodule.
    found_relative_module_only = _intra_package_imports("from . import heart_rate\n")
    assert found_relative_module_only == frozenset({"heart_rate"})
    found_bare_import = _intra_package_imports(
        "import fitdocs.load.channels.heart_rate as _hr\n"
    )
    assert found_bare_import == frozenset({"heart_rate"})


def _quality_flag_reference(source: str) -> bool:
    """Whether ``source`` names ``QualityFlag`` anywhere -- string-level, not
    only as an import, so a future re-export or ``getattr`` string reaching
    it would still be caught, deliberately not sharing any code with
    :func:`_sibling_load_imports` so the two guards do not share a single
    point of failure."""
    return "QualityFlag" in source


def test_no_module_references_quality_flag() -> None:
    """No module computes a quality flag: ``QualityFlag`` (``fitdocs.load.types``)
    never appears as an identifier anywhere in the package's source.
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    offenders = [
        path.name
        for path in py_files
        if _quality_flag_reference(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"QualityFlag referenced in: {offenders}"


def test_quality_flag_detection_catches_the_identifier(tmp_path: Path) -> None:
    """Fixture-discrimination companion, run through the exact same helper
    :func:`test_no_module_references_quality_flag` calls, against a
    synthetic file under ``tmp_path`` scanned the identical way (``.py``
    glob + ``read_text``) -- not merely a bare string-containment assertion
    disconnected from the production guard's own code path."""
    offender = tmp_path / "hypothetical.py"
    offender.write_text(
        "from fitdocs.load.types import QualityFlag\n", encoding="utf-8"
    )
    clean = tmp_path / "clean.py"
    clean.write_text(
        "from fitdocs.load.channels.types import ChannelId\n", encoding="utf-8"
    )

    py_files = sorted(tmp_path.glob("*.py"))
    assert len(py_files) == 2, "vacuity check: the synthetic directory was not scanned"
    offenders = [
        path.name
        for path in py_files
        if _quality_flag_reference(path.read_text(encoding="utf-8"))
    ]
    assert offenders == ["hypothetical.py"]


_ALLOWED_BENCHMARKS_IMPORTS = frozenset({"Benchmark", "BenchmarkKind"})


def _benchmark_import_names(source: str, *, filename: str = "<test>") -> frozenset[str]:
    """Every name ``source`` imports from ``fitdocs.benchmarks``."""
    tree = ast.parse(source, filename=filename)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "fitdocs.benchmarks":
            names.update(alias.name for alias in node.names)
    return frozenset(names)


def test_no_module_calls_a_benchmark_resolution_function() -> None:
    """No module resolves a benchmark: every ``fitdocs.benchmarks`` import
    across the package names only the two *type* symbols channels are
    handed an already-resolved instance of (``Benchmark``, ``BenchmarkKind``)
    -- never one of that module's own resolution/parsing functions
    (``parse_benchmarks``, ``benchmark_age``, ``benchmarks_to_document``,
    etc). A channel receives its benchmark as a caller-supplied argument and
    never looks one up itself (design: "anchors exclusively on the ...
    benchmark it is handed").
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, list[str]] = {}
    for path in py_files:
        extra = (
            _benchmark_import_names(
                path.read_text(encoding="utf-8"), filename=str(path)
            )
            - _ALLOWED_BENCHMARKS_IMPORTS
        )
        if extra:
            violations[path.name] = sorted(extra)
    assert violations == {}, f"benchmark-resolution symbol(s) imported: {violations}"


def test_benchmark_import_scan_actually_scans_a_real_offender() -> None:
    """Fixture-discrimination companion for :func:`_benchmark_import_names`,
    on synthetic source (real files are out of this task's read-only
    boundary): a benchmark-resolution import is caught, and the sanctioned
    two-type import is not."""
    offender = _benchmark_import_names(
        "from fitdocs.benchmarks import parse_benchmarks\n"
    )
    assert offender - _ALLOWED_BENCHMARKS_IMPORTS == {"parse_benchmarks"}

    sanctioned = _benchmark_import_names(
        "from fitdocs.benchmarks import Benchmark, BenchmarkKind\n"
    )
    assert sanctioned - _ALLOWED_BENCHMARKS_IMPORTS == set()


def _modality_keyed_mapping_hits(source: str, *, filename: str = "<test>") -> int:
    """Count of dict-literal keys in ``source`` that are an attribute access
    on ``Sport`` or ``Modality`` -- the shape a modality/discipline lookup
    table would take. A plain equality check (``activity.modality is not
    Modality.RUN``, an ``ast.Compare``, not an ``ast.Dict``) is not this
    shape and is not counted."""
    tree = ast.parse(source, filename=filename)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if (
                isinstance(key, ast.Attribute)
                and isinstance(key.value, ast.Name)
                and key.value.id in ("Sport", "Modality")
            ):
                count += 1
    return count


def test_no_module_defines_a_modality_or_sport_keyed_mapping() -> None:
    """No module maps a modality to a discipline: no dict literal anywhere in
    the package has a key that is an attribute access on ``Sport`` or
    ``Modality``. The pace channel's own single
    ``activity.modality is not Modality.RUN`` equality check is unaffected --
    checking one's own applicability is not mapping a modality to a
    discipline.
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, int] = {}
    for path in py_files:
        count = _modality_keyed_mapping_hits(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if count:
            violations[path.name] = count
    assert violations == {}, (
        f"modality/sport-keyed mapping literal(s) found: {violations}"
    )


def test_modality_mapping_detection_catches_the_shape() -> None:
    """Fixture-discrimination companion for :func:`_modality_keyed_mapping_hits`,
    on synthetic source: two dict entries keyed on ``Sport`` members are
    both counted, and the pace channel's own equality-check shape is not."""
    assert (
        _modality_keyed_mapping_hits(
            "x = {Sport.RUN: 'running', Sport.RIDE: 'cycling'}\n"
        )
        == 2
    )
    assert (
        _modality_keyed_mapping_hits(
            "if activity.modality is not Modality.RUN:\n    pass\n"
        )
        == 0
    )


# ===========================================================================
# Allowlist-shaped structural guard (task 4.2, round 3 debug-directed fix).
#
# Rounds 1 and 2 above each shipped a *denylist* over AST spellings of
# forbidden constructs. Both were rejected for the identical defect: that
# enumeration is unbounded. This section instead pins the module's global
# namespace *exhaustively*, on the following completeness argument:
#
# A module's global namespace contains (a) every name the module binds
# itself -- via an imported *name* (not merely a sanctioned import *target*;
# round 3 pinned only the target, which is exactly the gap round 4 closed --
# see :func:`_import_allowlist_violations` and Finding 1 in this task's own
# history), a module-level assignment in any binding form the language
# offers at module scope (plain assignment, annotated assignment,
# ``for``/``with``/``except``/``match``-``case`` targets, augmented
# assignment, or a walrus target including one written inside a
# comprehension -- round 3 pinned only plain and annotated assignment,
# round 4 added the rest except the comprehension-walrus and match-pattern
# forms, which round 5 closed after Finding 3 found them still open; see
# :func:`_module_level_bindings`), or a top-level (or nested, walked via
# ``ast.walk``) ``def``/``class``; **and (b) names the import protocol
# hands every module without that module binding them itself** --
# ``__name__``, ``__doc__``, ``__package__``, ``__loader__``, ``__spec__``,
# ``__file__``, ``__cached__``, ``__builtins__``, ``__path__``, ``__all__``
# (a fixed, finite set fixed by the import protocol itself, not by this
# module's own choices). Round 4 pinned only imported-name reach into (a);
# it did not pin (b) at all -- ``'__builtins__' in dir(builtins)`` is
# ``False``, so the builtin-name check never saw it, and no check inspected
# a bare ``ast.Name`` reference at all (only ``ast.Attribute``) -- which is
# exactly how Finding 1 (round 5, this task's own adversarial re-check)
# reached ``sys.modules`` with no attribute access and no unsanctioned
# import in the expression at all. Round 5 closes (b): any bare ``ast.Name``
# in ``Load`` context whose ``id`` both starts and ends with ``__`` is
# rejected by :func:`_dunder_attribute_violations`, closing the *class* of
# such references (the shape, not one enumerated spelling), so a future
# CPython addition to (b)'s fixed set needs no new rule here.
#
# The checks below pin (a) exhaustively (imported names, module-level
# bindings in every binding form the language offers at module scope, def/
# class names) and (b) by shape (any dunder-spelled bare name reference),
# plus two rules closing two channels that reach outside a module's own
# namespace without going through either, *when that reach is expressed as
# syntax this module's own AST walk sees*: the real-builtins namespace
# (``dir(builtins)``, guarded fifteen lines above by the finite, measured
# ``_ALLOWED_BUILTINS`` allowlist plus the exact-set binding pin
# :data:`_ALLOWED_BUILTIN_SHADOWS`), and dunder *attribute* access, itself
# only as an ``ast.Attribute`` node (``.__globals__``, ``.__mro__``,
# ``.__subclasses__``, ``importlib.__import__``, ...) -- not reach through
# either channel spelled inside a string that a runtime string-formatting
# call then resolves against a live object, which is U6, declared below,
# not closed here. Any new external reach through a name this module binds
# itself, or through one of the fixed import-protocol dunders, expressed as
# an AST shape one of these checks walks, must appear as one of those
# things and redden the corresponding assertion.
#
# **This is narrower than "any new external reach must redden an
# assertion," full stop** -- that broader sentence shipped in rounds 3 and
# 4 and was falsified twice (Findings 1 and 2, round 5): an object
# constructed *in situ* at runtime, bound under no name at all (a generator
# expression's ``.gi_frame``, for instance), is reachable through neither
# (a) nor (b) and is not closed by anything in this module -- declared,
# not chased, as U4 below. This banner's claim is scoped to reach *through
# a name -- this module's own or the import protocol's -- that the source
# text itself contains*; runtime object construction with no such name is
# outside that scope by definition, not an oversight this banner elides.
#
# This is a claim about *reach through this module's own bound names, plus
# the fixed import-protocol names every module receives*, not a claim that
# no property a "pure module" could violate is left open. It does not
# close, and is not presented as closing: the semantic gaps declared
# separately below as U1 (a modality-to-discipline mapping written
# without touching the ``Sport``/``Modality`` enums or a dict literal); U2
# (invoking a language model); U3 (attribute reach into a sanctioned
# import's transitive namespace, bounded by the currently-bound root set);
# U4 (round 5 -- reach through an object built in situ at runtime, bound
# under no name the source text contains, such as a generator expression's
# own frame); the structural fragility noted where :func:`_enum_member_refs`
# is defined (a local alias of ``Modality`` defeats the exact-attribute-
# spelling match); or Req 8.3's class-body gap (a numeric constant added to
# an existing class's own body is not a module-level binding at all, and is
# closed separately, not by this argument, by
# :func:`_class_body_numeric_constant_names` below). That argument does not
# depend on having thought of every spelling of "forbidden", which is
# exactly what rounds 1 and 2 depended on and exactly why both were found
# incomplete -- but it is bounded by what "this module's own bound names,
# plus the fixed import-protocol dunders" actually means in Python, and
# round 4's and round 5's own findings (an imported name from a sanctioned
# target; a bare dunder name; a comprehension-walrus and a match-pattern
# binding; a frame reached through no bound name at all) are proof that
# stating the boundary precisely, and re-deriving it against a fresh
# adversarial reading rather than restating the prior round's version, is
# still required every round.
#
# All six allowlists below were re-measured directly against the nine leaf
# modules as they exist on this branch right now (not copied from the
# debugger's investigation) -- see
# ``/private/tmp/claude-501/.../scratchpad/measure_verify.py`` for the
# independent measurement script this task's own investigation ran. Re-run
# it (or an equivalent walk) before trusting these sets if the leaf modules
# have changed since: a stale allowlist reds on arrival, which is the
# failure mode the assertion messages below exist to make legible rather
# than mysterious to the next editor.
#
# **These are exact-set pins, not lower bounds.** A future editor adding a
# legitimate new import, helper function, or module-level constant to any
# leaf module *will* redden the corresponding assertion here. That is the
# pin working as designed -- the module already accepts this trade-off for
# ``_EXPECTED_INTRA_PACKAGE_IMPORTS`` above -- and every assertion message
# below says explicitly what changed (the symmetric-difference form, not a
# bare "mismatch") and that widening the allowlist is a deliberate,
# reviewable act, not a check to silence by copying the new value in without
# looking at it.
# ===========================================================================

# Round-4 debug-directed fix (task 4.2, this round). Round 3's
# ``_ALLOWED_IMPORT_TARGETS`` pinned the *target* of an import (the dotted
# module path after ``from``/``import``) but not the *name* pulled out of
# it. That let ``from dataclasses import sys as _sys`` through cleanly --
# ``dataclasses`` is a sanctioned target, so the target-only check never
# looked at what was actually imported from it, and ``sys`` (an attribute
# three of the eleven sanctioned stdlib/local targets below happen to
# expose -- measured: ``dataclasses``, ``enum`` and ``typing`` each do
# their own internal ``import sys``, so ``hasattr(<module>, "sys")`` is
# ``True`` for those three and ``False`` for ``__future__`` and
# ``collections.abc``) gave a leaf full reach to ``sys.modules`` and
# everything reachable through it via any of those three. This mapping pins
# the exact **names** sanctioned for each target instead of the target
# alone, re-measured directly against the nine leaf modules exactly as
# ``_ALLOWED_IMPORT_TARGETS`` was (see the module banner comment above):
# every ``from <target> import <name>`` in the package today appears
# exactly once as a ``target: {name, ...}`` entry below, and nothing else
# does. ``math`` is imported bare (``import math``, no ``from``) and is
# handled by the separate ``_ALLOWED_BARE_IMPORT_TARGETS`` set below rather
# than this name-keyed mapping, since a bare import has no "name" to pin --
# it binds the whole module object under its own name. That is a narrower
# gap than the ``from``-import one this fix closes: ``math`` is a C
# extension exposing only numeric functions and float/int constants (no
# module, class, or function attribute reachable via ``dir(math)`` --
# checked directly, not assumed, and (round 5, Finding 9) asserted rather
# than only stated in prose, by
# :func:`test_guard_premises_math_and_dunder_builtins_hold`, below), so
# binding the whole module object adds no reach beyond what the sanctioned
# names below already grant.
_ALLOWED_IMPORT_NAMES: dict[str, frozenset[str]] = {
    "__future__": frozenset({"annotations"}),
    "collections.abc": frozenset({"Sequence"}),
    "dataclasses": frozenset({"dataclass"}),
    "enum": frozenset({"StrEnum"}),
    "typing": frozenset({"Final", "Protocol"}),
    "fitdocs.benchmarks": frozenset({"Benchmark", "BenchmarkKind"}),
    "fitdocs.citation": frozenset({"Citation", "VerificationStatus"}),
    "fitdocs.metrics": frozenset({"sources"}),
    "fitdocs.metrics.stress": frozenset({"power_tss", "trimp"}),
    "fitdocs.metrics.types": frozenset({"DerivedMetrics"}),
    "fitdocs.model": frozenset({"Activity", "Modality", "Samples"}),
}
_ALLOWED_BARE_IMPORT_TARGETS = frozenset({"math"})


def _import_allowlist_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """Every ``ast.Import``/``ast.ImportFrom`` anywhere in ``source``
    (:func:`ast.walk`, so a function-local import is covered too, not only
    module-scope ones) that reaches outside the sanctioned surface -- either
    a target outside ``_ALLOWED_IMPORT_NAMES``/``_ALLOWED_BARE_IMPORT_TARGETS``,
    or (round-4 fix) a ``from <target> import <name>`` whose *target* is
    sanctioned but whose *name* is not one of that target's own allowlisted
    names -- and does not resolve to ``fitdocs.load.channels`` itself or one
    of its own submodules (that half is already covered, as an *exact*
    adjacency mapping rather than a mere "is a submodule" check, by
    ``_EXPECTED_INTRA_PACKAGE_IMPORTS`` above). Relative imports are resolved
    the same way :func:`_sibling_load_imports` already does, via
    :func:`importlib.util.resolve_name`.

    ``ast.Import`` (the ``import x`` form, as opposed to ``from x import
    y``) is held to a stricter rule than simple allowlist membership for
    *dotted* targets specifically: **any dotted target is rejected
    outright**, regardless of what it resolves to. ``import a.b`` binds only
    the name ``a`` in the importing scope -- so the reach a consumer of that
    binding actually has is the *root* package, not the (possibly
    sanctioned-looking) submodule spelled out in the statement. This is the
    rule that rejects ``import fitdocs.load.channels.heart_rate as _hr`` (an
    intra-package cross-channel import spelled as a root-binding ``import``
    rather than a ``from`` statement, so it does not appear in
    ``_EXPECTED_INTRA_PACKAGE_IMPORTS`` at all) -- one rule for every dotted
    bare import, rather than one more entry in an enumeration. A bare,
    *non-dotted* ``import fitdocs`` is a separate case: it is rejected by
    the ordinary allowlist-membership check below (``"fitdocs" not in
    _ALLOWED_BARE_IMPORT_TARGETS``), not by the dotted-target rule, since it
    has no dot to trigger it -- both branches converge on "reject", but for
    different, precisely stated reasons, not one rule covering both. The
    package's own nine leaf modules use the ``from x import y`` form
    exclusively today except for one bare, non-dotted ``import math`` in
    ``heart_rate.py`` -- which this rule passes cleanly, since ``math`` is
    both non-dotted and in ``_ALLOWED_BARE_IMPORT_TARGETS``.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if "." in target:
                    violations.append(
                        f"L{node.lineno}: import {target} -- dotted `import` "
                        f"target binds only its root package, which is not "
                        f"separately allowlisted for this form"
                    )
                elif target not in _ALLOWED_BARE_IMPORT_TARGETS:
                    violations.append(
                        f"L{node.lineno}: import {target} not allowlisted"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    resolved: str | None = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""),
                        "fitdocs.load.channels",
                    )
                except ImportError:
                    resolved = None
            else:
                resolved = node.module
            if resolved is None:
                violations.append(f"L{node.lineno}: unresolvable relative import")
                continue
            if resolved == "fitdocs.load.channels" or resolved.startswith(
                "fitdocs.load.channels."
            ):
                continue
            allowed_names = _ALLOWED_IMPORT_NAMES.get(resolved)
            if allowed_names is None:
                violations.append(
                    f"L{node.lineno}: from {resolved} import ... not allowlisted"
                )
                continue
            for alias in node.names:
                if alias.name not in allowed_names:
                    violations.append(
                        f"L{node.lineno}: from {resolved} import {alias.name} "
                        f"-- name not in that target's own allowlisted set "
                        f"{sorted(allowed_names)}"
                    )
    return violations


_ALLOWED_BUILTINS = frozenset(
    {
        "ValueError",
        "bool",
        "dict",
        "float",
        "frozenset",
        "int",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "object",
        "property",
        "range",
        "str",
        "sum",
        "tuple",
    }
)


_ALLOWED_BUILTIN_SHADOWS: frozenset[str] = frozenset()
"""The exact set of local bindings (``Store``-context ``ast.Name``, ``ast.arg``,
``def``/``class`` name, or import target/alias) permitted to share a
spelling with a real builtin (``name in dir(builtins)``) -- measured empty
across all nine leaf modules today. **Round 6, Finding 1** replaced the prior
whole-module "any binding anywhere exempts every same-spelled reference"
approximation with this exact-set pin, the same idiom already used elsewhere
in this module: a leaf has no legitimate reason to bind a name colliding with
a builtin at any scope, so the binding itself is the violation rather than
something that quietly exempts a later reference. Widening this set is a
deliberate, reviewable act, exactly like widening ``_ALLOWED_BUILTINS``."""


def _locally_bound_names(tree: ast.AST) -> set[str]:
    """Every name ``tree`` binds itself, anywhere -- import targets/aliases,
    ``def``/``class`` names, assignment targets, and parameter names -- so
    that :func:`_builtin_allowlist_violations` can tell a genuine reference
    to a builtin apart from a local name that merely shares a builtin's
    spelling (e.g. a parameter named ``str``).

    **Round 6, Finding 1 -- what this exemption no longer covers, and why.**
    Earlier rounds' docstring claimed a locally-bound name "shadows the check
    for the rest of its scope"; that was false. ``ast.walk`` does not model
    Python scoping, so a name bound inside a comprehension or lambda --
    which does **not** shadow the builtin at a module-scope reference site --
    was nonetheless treated as if it did, letting
    ``_warm = [open for open in (0,)]; _o = open`` exempt a genuine
    module-scope reference to the real ``open`` builtin. This function still
    reports every such binding (comprehension targets included) for ordinary,
    non-builtin local names, where the whole-module approximation is harmless.
    For names that collide with a real builtin, :func:`_builtin_allowlist_violations`
    no longer trusts this function's exemption at all -- see
    :func:`_builtin_shadow_violations`, which instead rejects the *binding*
    itself, at any scope, unless it is in :data:`_ALLOWED_BUILTIN_SHADOWS`.
    """
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
    """Every binding (``Store``-context ``ast.Name``, ``ast.arg``,
    ``def``/``class`` name, or import target/alias) of a name in
    ``dir(builtins)`` that is not in :data:`_ALLOWED_BUILTIN_SHADOWS`.

    This is the fix for **round 6, Finding 1**: rather than trying to model
    scoping (which ``ast.walk`` cannot do) to decide whether a given binding
    shadows a given reference, this rejects the binding itself, at any
    scope, whenever its spelling collides with a real builtin. That closes
    ``_warm = [open for open in (0,)]``, ``[eval for eval in (0,)]`` and
    ``[getattr for getattr in (0,)]`` directly -- each binds a builtin-spelled
    name via a comprehension target, which is exactly the shape that used to
    earn a whole-module exemption under the old approximation.
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
    """Every ``ast.Name`` in :class:`ast.Load` context in ``source`` that
    names a real builtin (``dir(builtins)``) and is not locally bound (see
    :func:`_locally_bound_names`) and is not one of the seventeen measured,
    sanctioned builtins above, **plus** every builtin-shadowing binding
    itself (see :func:`_builtin_shadow_violations`, round 6, Finding 1).
    Kills ``__import__``, ``getattr``, ``eval``, ``exec``, ``compile``,
    ``globals``, ``vars``, ``open``, ``input``, ``type``, and every other
    unsanctioned builtin with one finite rule instead of enumerating each
    dangerous one -- and, since round 6, does not let a comprehension- or
    lambda-scoped binding of one of those names exempt a module-scope
    reference to the real builtin.
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
    return violations


def _dunder_attribute_violations(source: str, *, filename: str = "<test>") -> list[str]:
    """Every ``ast.Attribute`` in ``source`` whose ``attr`` both starts and
    ends with ``__``, plus (round 5's fix -- Finding 1) every bare
    ``ast.Name`` in :class:`ast.Load` context whose ``id`` both starts and
    ends with ``__``: the two namespace-bypassing introspection channels
    that reach outside a module's own bound names entirely.

    The attribute half closes ``.__globals__``, ``.__mro__``,
    ``.__subclasses__`` and ``importlib.__import__`` permanently rather than
    one spelling at a time -- but only when the access is *syntactic*, an
    ``ast.Attribute`` node in the source; the same dunder reached through a
    string a runtime call (``str.format``, and any other string-templating
    call) resolves against a live object is invisible to this walk, since
    the dunder spelling then lives inside an ``ast.Constant``, not an
    ``ast.Attribute`` -- declared, not closed, as U6 below. The bare-name
    half closes a route the attribute
    check cannot see at all: inside an imported module, ``__builtins__`` is
    bound as a plain module global -- not something the module itself
    assigns, but something the import machinery hands every module -- and
    referencing it is an ``ast.Name`` node, never an ``ast.Attribute``, so
    ``_b = __builtins__["__import__"]`` (a subscript on a bare name) reached
    ``sys.modules`` with **no** ``.`` in the expression at all, confirmed
    live against ``power.compute`` (39/39 passed, full suite green,
    byte-identical, before this fix). ``'__builtins__' in dir(builtins)`` is
    ``False``, so :func:`_builtin_allowlist_violations` never saw it either.

    The set of such names a module receives from the import protocol without
    binding them itself is fixed and finite -- ``__name__``, ``__doc__``,
    ``__package__``, ``__loader__``, ``__spec__``, ``__file__``,
    ``__cached__``, ``__builtins__``, ``__path__``, ``__all__`` among them --
    but this rule does not enumerate that set (an enumeration is exactly the
    denylist shape rounds 1 and 2 were rejected for); it rejects the *shape*
    (leading and trailing double underscore) of any such reference in
    ``Load`` context, so it also closes ``__class__`` (zero-arg ``super()``
    machinery -- unused by any leaf class today, verified by grep) and any
    other current or future dunder without a fresh enumeration. It does not
    reject a *Store*-context dunder name (``__all__ = [...]`` remains
    legitimate module-level metadata) since assigning to a name the module
    itself owns is not the reach this rule closes.
    """
    tree = ast.parse(source, filename=filename)
    violations = [
        f"L{node.lineno}: dunder attribute access `.{node.attr}`"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr.startswith("__")
        and node.attr.endswith("__")
    ]
    violations.extend(
        f"L{node.lineno}: dunder name reference `{node.id}`"
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id.startswith("__")
        and node.id.endswith("__")
    )
    return violations


# Exact per-module top-level (and nested -- walked via ``ast.walk``, not
# ``tree.body``, so a helper ``def`` nested inside another function is
# covered too) def/class name allowlist. This is the *only* thing in this
# module that pins Req 9.6 ("shall not implement a strength-training load, a
# modelled running-power estimate, or a build-time power-calibrated
# heart-rate regression"): each of those would need a new, differently-named
# function, and none is in any leaf's allowlist below.
_EXPECTED_DEFS: dict[str, frozenset[str]] = {
    "__init__": frozenset(),
    "grade": frozenset(
        {
            "GradeAdjustment",
            "equivalent_distance",
            "running_cost_ratio",
            "smoothed_altitude",
        }
    ),
    "heart_rate": frozenset({"compute"}),
    "pace": frozenset({"compute"}),
    "power": frozenset({"compute"}),
    "sources": frozenset({"Divergence"}),
    "sufficiency": frozenset({"evaluate", "stream_coverage"}),
    "types": frozenset(
        {
            "ChannelId",
            "ChannelInsufficient",
            "ChannelLoad",
            "InsufficiencyReason",
            "StreamCoverage",
            "SufficiencySettings",
            "require_kind",
            "fraction",
            "minimum_for",
        }
    ),
    "weighting": frozenset(
        {
            "BanisterTrimpModel",
            "HeartRateIntensityModel",
            "_one_hour_at",
            "activity_impulse",
            "hourly_impulse_at",
        }
    ),
}


def _module_defs(source: str, *, filename: str = "<test>") -> frozenset[str]:
    tree = ast.parse(source, filename=filename)
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )


# Exact per-module module-level-binding allowlist (``ast.Assign``/
# ``ast.AnnAssign`` targets in ``tree.body`` only -- module scope, not
# nested). 24 names total, measured directly against this branch's leaf
# modules. This both pins new external reach via a fresh module-level
# constant, and strengthens provenance: a new constant of *any* shape now
# reddens here even in the tuple/subscript/imported-attribute shapes
# :func:`_module_level_numeric_constant_names` above honestly documents it
# does not walk.
_EXPECTED_MODULE_LEVEL_BINDINGS: dict[str, frozenset[str]] = {
    "__init__": frozenset({"__all__"}),
    "grade": frozenset(
        {
            "ALTITUDE_SMOOTHING_WINDOW",
            "MINETTI_LEVEL_COST_J_PER_KG_PER_M",
            "MINETTI_MAX_ABS_GRADIENT",
            "MINETTI_RUNNING_COEFFICIENTS",
            "MIN_GRADIENT_DISTANCE_M",
            "_NOT_APPLIED_NOTE",
        }
    ),
    "heart_rate": frozenset({"_MISSING_NAMES"}),
    "pace": frozenset({"_NO_BENCHMARK_DETAIL", "_SECONDS_PER_KM_TO_MPS"}),
    "power": frozenset({"_NO_BENCHMARK_DETAIL"}),
    "sources": frozenset(
        {
            "BANISTER_TRIMP",
            "BLOCKED_CITATIONS",
            "CITATIONS",
            "COGGAN_TSS",
            "DIVERGENCES",
            "INTERVALS_ICU_HRSS",
            "INTERVALS_ICU_PACE_LOAD",
            "MINETTI_2002",
            "TRAININGPEAKS_COVERAGE_GATE",
        }
    ),
    "sufficiency": frozenset(),
    "types": frozenset(
        {"ChannelOutcome", "DEFAULT_MIN_DURATION_S", "DEFAULT_MIN_STREAM_COVERAGE"}
    ),
    "weighting": frozenset({"BANISTER_TRIMP_MODEL"}),
}


_SCOPE_BOUNDARY_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _module_level_bindings(source: str, *, filename: str = "<test>") -> frozenset[str]:
    """Every name module-scope code binds -- not only the plain ``x = 1`` /
    ``x: int = 1`` forms round 3 pinned (``tree.body``-only ``ast.Assign``/
    ``ast.AnnAssign``), but every binding form the language offers at module
    scope: ``for x in ...``, ``with ... as x``, ``except ... as x``, ``x +=
    1`` (augmented assignment is still a binding, even though it also
    reads), and the walrus operator (``if (x := ...):``). Recurses through
    ordinary control-flow statements (``if``, ``for``, ``while``, ``with``,
    ``try``) since none of those introduces a new scope in Python -- a
    binding made inside one, at the top level of a module, is a
    module-level binding exactly as if it had been written unconditionally.
    Does **not** recurse into anything that *does* introduce its own scope
    (``def``/``class``/``lambda``/comprehensions, ``_SCOPE_BOUNDARY_NODES``)
    -- a name bound there is local to that scope, not the module's;
    ``def``/``class`` names themselves are pinned separately by
    :func:`_module_defs`, and a class's own body is pinned separately, for
    numeric constants specifically, by
    :func:`_class_body_numeric_constant_names` (Req 8.3's class-body half,
    round 4's fix).

    **Exception, round 5's fix (Finding 3):** a comprehension is a scope
    boundary for its own loop variables, but PEP 572 makes a walrus
    (``:=``) *inside* a comprehension bind the nearest **enclosing**
    scope, not the comprehension's own -- so
    ``if [(_FUDGE := 0.83) for _ in (0,)]: pass`` at module scope binds
    ``_FUDGE`` as a real module global even though it sits inside a
    ``ListComp``. Confirmed live: appended to ``power.py``, this module's
    entire suite stayed green (before this fix), and ``mypy``/``ruff`` both
    stayed clean too. When a scope-boundary child is one of the four
    comprehension node types, this walk still skips its ordinary loop
    variables but first collects any ``ast.NamedExpr`` target nested inside
    it, so the module-level leak is caught without treating the
    comprehension's own bound names as module-level.

    Round 3's version only inspected ``tree.body`` for bare ``ast.Assign``/
    ``ast.AnnAssign`` nodes, which is why ``for _EVIL in (1, 2): pass`` and
    ``if (_EVIL2 := 42): pass`` at module scope both bound a name invisibly
    to every allowlist below -- fixed here.

    One more binding form, caught separately below rather than by the
    scope-limited walk above: ``global x`` inside a function body (even an
    *existing*, already-allowlisted function such as ``compute``, and even
    nested arbitrarily deep) declares that an assignment to ``x`` inside
    that function binds the *module's* own namespace, not a local one --
    this task's own adversarial re-check found that ``global _SUDO`` plus
    ``_SUDO = 42`` inserted into ``power.compute`` leaves every check in
    this module green otherwise, since the scope-limited walk above
    deliberately never descends into a function body at all. Caught by a
    second, unscoped ``ast.walk`` collecting every ``ast.Global`` node's
    declared names, since a ``global`` declaration is itself unambiguous
    regardless of how deeply nested the function containing it is.

    Two more binding forms, round 5's fix (Finding 3): ``match``/``case``
    capture patterns. ``ast.MatchAs.name``, ``ast.MatchStar.name`` and
    ``ast.MatchMapping.rest`` are each a plain identifier string, not a
    ``Store``-context ``ast.Name`` node, so the ordinary ``ast.Name``/
    ``ast.Store`` check above never sees them even though the ``match``
    statement itself is not a scope boundary and this walk already
    recurses into it. Confirmed live: ``match 0.83:\n    case
    float(_FUDGE2):\n        pass`` appended to ``power.py`` left this
    module's entire suite green (before this fix).
    """
    tree = ast.parse(source, filename=filename)
    names: set[str] = set()

    def _walk_scope(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SCOPE_BOUNDARY_NODES):
                if isinstance(
                    child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
                ):
                    for inner in ast.walk(child):
                        if isinstance(inner, ast.NamedExpr) and isinstance(
                            inner.target, ast.Name
                        ):
                            names.add(inner.target.id)
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
            elif (
                isinstance(child, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar))
                and child.name
            ):
                names.add(child.name)
            elif isinstance(child, ast.MatchMapping) and child.rest:
                names.add(child.rest)
            _walk_scope(child)

    _walk_scope(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            names.update(node.names)
    return frozenset(names)


# Exact per-module ``Sport``/``Modality`` member-reference allowlist -- the
# structural half of Req 9.5 ("shall not map an activity's modality to a
# benchmark discipline"). Every module except ``pace`` references neither
# enum's members at all; ``pace`` references exactly ``Modality.RUN`` once
# (its own applicability check, ``activity.modality is not Modality.RUN``).
_EXPECTED_ENUM_MEMBER_REFS: dict[str, frozenset[str]] = {
    "pace": frozenset({"Modality.RUN"}),
}


def _enum_member_refs(source: str, *, filename: str = "<test>") -> frozenset[str]:
    """**Fragility, stated rather than hidden (round 4):** this matches only
    an ``ast.Attribute`` whose ``.value`` is an ``ast.Name`` spelled exactly
    ``Sport`` or ``Modality`` -- a local alias defeats it. ``_M = Modality``
    followed by ``_disc = {_M.RUN: "running"}`` inside a leaf's ``compute``
    leaves this entire module's suite green: the reference is real (``_M``
    is ``Modality``), but its AST shape is ``Attribute(value=Name(id="_M"))``,
    which does not match ``in ("Sport", "Modality")`` below. This is the
    same class of gap U1 (declared below) already names for Req 9.5's
    general semantic form -- restated here at the specific mechanism this
    helper uses, not fixed, since closing it soundly would need name-binding
    analysis (does ``_M`` resolve to ``Modality`` at this point?) that an
    ``ast.walk`` over bare attribute shapes cannot do.
    """
    tree = ast.parse(source, filename=filename)
    return frozenset(
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in ("Sport", "Modality")
    )


def test_guard_premises_math_and_dunder_builtins_hold() -> None:
    """Round 5, Finding 9: two runtime facts this module's guards rest on
    without asserting, made self-verifying so an interpreter upgrade that
    changed either is caught here rather than silently invalidating an
    unasserted claim.

    Premise 1 (``_ALLOWED_IMPORT_NAMES``'s ``math`` exemption, see the
    module banner comment near ``_ALLOWED_BARE_IMPORT_TARGETS``): ``math``
    is a C extension exposing only numeric functions and float/int
    constants -- no attribute reachable via ``dir(math)`` is itself a
    module, a class, or an ``inspect.isfunction``-recognized Python
    function -- so binding the whole module object under ``import math``
    adds no reach beyond what the sanctioned import *names* already grant.
    (This does not assert ``math``'s own numeric functions are absent --
    they are the sanctioned surface, not a residual -- only that none of
    them is itself a further carrier to another module, class or
    function.)

    Premise 2 (:func:`_dunder_attribute_violations`'s bare-dunder-name
    rule, Finding 1): ``'__builtins__' in dir(builtins)`` is ``False`` in
    CPython -- the reason a plain builtin-name check never sees
    ``__builtins__`` and a dedicated bare-``ast.Name`` rule was needed at
    all.
    """
    import inspect
    import math
    import types as _types

    carriers = [
        name
        for name in dir(math)
        if not (name.startswith("__") and name.endswith("__"))
        and (
            isinstance(getattr(math, name), _types.ModuleType)
            or inspect.isclass(getattr(math, name))
            or inspect.isfunction(getattr(math, name))
        )
    ]
    assert carriers == [], (
        f"math now exposes a module/class/function attribute: {carriers} -- "
        f"the `math` bare-import exemption's premise no longer holds"
    )

    assert "__builtins__" not in dir(builtins), (
        "__builtins__ is now a real attribute of the builtins module -- the "
        "premise that a bare-name check was needed alongside the builtin-"
        "name allowlist no longer holds as stated"
    )


def test_import_allowlist_permits_no_target_outside_the_measured_twelve() -> None:
    """Import half of the round-3/round-4 fix: no leaf module imports
    anything outside the twelve measured, sanctioned external targets (plus
    its own package, covered separately) -- and, since round 4, no leaf
    module imports a *name* from a sanctioned target that is not itself one
    of that target's own measured, sanctioned names (``_ALLOWED_IMPORT_NAMES``).
    Round 3's target-only form of this guard is exactly what let ``from
    dataclasses import sys`` through; this is the guard against every
    import-based escape the three prior rounds enumerated one-by-one --
    ``fitdocs.load.*`` siblings, ``subprocess``/``tempfile``/``shutil``/
    ``glob``/``getpass``, ``importlib``, a bare ``import fitdocs``, a
    sanctioned-target/unsanctioned-name import such as ``from dataclasses
    import sys`` -- for every spelling this task's own mutation catalogue
    named, since it is an allowlist, not a denylist. It is not a claim of
    completeness beyond the module's own global namespace; see the
    "Allowlist-shaped structural guard" banner comment above for exactly
    what completeness argument this and its five sibling allowlists
    jointly support.
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _import_allowlist_violations(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if found:
            violations[path.name] = found
    assert violations == {}, (
        f"import target/name outside the sanctioned allowlist: {violations} "
        f"-- widening _ALLOWED_IMPORT_NAMES or _ALLOWED_BARE_IMPORT_TARGETS "
        f"is a deliberate, reviewable act, not something to do without "
        f"reading why each new target or name is safe"
    )


def test_import_allowlist_detection_catches_the_sixteen_known_escape_spellings() -> (
    None
):
    """Fixture-discrimination companion, run against every import-based
    escape spelling this task's own mutation catalogue (round 1's six, round
    2's remaining import-shaped survivors, plus round 4's four
    sanctioned-target/unsanctioned-name escapes -- Finding 1: ``from
    dataclasses import sys``, and its ``typing``/``enum``/``builtins``
    siblings) names, on synthetic source (real files are out of this task's
    read-only boundary)."""
    offenders = {
        "relative_sibling": "from .. import settings\n",
        "relative_sibling_module": "from ..settings import LoadSettings\n",
        "parent_then_attribute": "from fitdocs.load import settings\n",
        "grandparent_then_attribute": "from fitdocs import load as _load\n",
        "bare_fqn_alias": "import fitdocs.load.channels.heart_rate as _hr\n",
        "bare_import_module": "from importlib import import_module\n",
        "import_subprocess": "import subprocess\n",
        "import_tempfile_shutil_glob": "import tempfile, shutil, glob\n",
        "import_getpass": "import getpass\n",
        "import_benchmarks_module": "from fitdocs import benchmarks as _bm\n",
        "aliased_import_module": "import importlib\n_f = importlib.import_module\n",
        "bare_import_fitdocs": "import fitdocs\n",
        # Round 4 / Finding 1: sanctioned *target*, unsanctioned *name* --
        # the class of escape round 3's target-only allowlist missed
        # entirely, live-verified to reach ``sys.modules`` before this fix.
        "sanctioned_target_unsanctioned_name_dataclasses": (
            "from dataclasses import sys as _sys\n"
        ),
        "sanctioned_target_unsanctioned_name_typing": "from typing import sys\n",
        "sanctioned_target_unsanctioned_name_enum": "from enum import sys as _sys\n",
        "sanctioned_target_unsanctioned_name_builtins": (
            "from dataclasses import builtins as _b\n"
        ),
        # Corrected docstring claim (round 3 -> round 4) in
        # `_interface_references`: `fitdocs.model` is a sanctioned target,
        # and `datetime` is a real, live attribute of that module
        # (`fitdocs.model.datetime is datetime.datetime`) -- not in
        # `fitdocs.model`'s own allowlisted name set.
        "sanctioned_target_unsanctioned_name_fitdocs_model": (
            "from fitdocs.model import datetime\n"
        ),
    }
    for label, source in offenders.items():
        found = _import_allowlist_violations(source)
        assert found != [], f"{label}: offending import was not caught"

    sanctioned = {
        "self_relative": "from .types import ChannelId\n",
        "self_relative_module": "from . import types\n",
        "self_absolute": "from fitdocs.load.channels.types import ChannelId\n",
        "unrelated_stdlib": "import math\n",
        "sanctioned_from_import": "from fitdocs.model import Samples\n",
        "sanctioned_third_party": "from fitdocs.metrics.types import DerivedMetrics\n",
    }
    for label, source in sanctioned.items():
        found = _import_allowlist_violations(source)
        assert found == [], f"{label}: false positive on a sanctioned import: {found}"


def test_builtin_allowlist_permits_no_reference_outside_the_measured_seventeen() -> (
    None
):
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _builtin_allowlist_violations(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if found:
            violations[path.name] = found
    assert violations == {}, (
        f"builtin-allowlist violation(s): {violations} -- a `not allowlisted` "
        f"line names a builtin *reference*, widened via _ALLOWED_BUILTINS; a "
        f"`local binding shadows builtin` line names a *binding* of a "
        f"builtin-spelled name (round 6, Finding 1) and is widened via "
        f"_ALLOWED_BUILTIN_SHADOWS instead -- adding the name to "
        f"_ALLOWED_BUILTINS does not clear a binding violation. Either is a "
        f"deliberate, reviewable act"
    )


def test_builtin_allowlist_detection_catches_every_dangerous_builtin() -> None:
    """Fixture-discrimination companion: every dynamic-reach builtin the two
    prior rounds worried about individually is caught by one rule, and the
    seventeen sanctioned builtins are not false-flagged."""
    offenders = {
        "dunder_import": "__import__('os')\n",
        "getattr_call": "getattr(object(), 'x')\n",
        "eval_call": "eval('1')\n",
        "exec_call": "exec('pass')\n",
        "compile_call": "compile('1', '<s>', 'eval')\n",
        "globals_call": "globals()\n",
        "vars_call": "vars()\n",
        "open_call": "open('x')\n",
        "input_call": "input()\n",
        "type_call": "type('X', (), {})\n",
        # Round 6, Finding 1 -- a comprehension target that binds a name
        # spelled like a real builtin used to exempt a later module-scope
        # reference to that builtin under the old whole-module
        # approximation. Each of these three was hand-verified live against
        # ``grade.running_cost_ratio``/``power.compute`` before this fix:
        # the full suite (2759 passed, 5 skipped) stayed green with each in
        # place, and reds afterward.
        "comprehension_shadowed_open": (
            "_warm = [open for open in (0,)]\n"
            "_o = open\n"
            "_txt = _o('/etc/hosts').read()\n"
        ),
        "comprehension_shadowed_eval": (
            "_warm = [eval for eval in (0,)]\neval(\"__import__('sys').modules\")\n"
        ),
        "comprehension_shadowed_getattr": (
            "_warm = [getattr for getattr in (0,)]\ngetattr(object(), '__class__')\n"
        ),
    }
    for label, source in offenders.items():
        found = _builtin_allowlist_violations(source)
        assert found != [], f"{label}: offending builtin reference was not caught"

    sanctioned_source = (
        "x: int = 1\n"
        "y: float = 1.0\n"
        "z: bool = True\n"
        "s: str = 'a'\n"
        "d: dict = {}\n"
        "t: tuple = ()\n"
        "fs: frozenset = frozenset()\n"
        "lst: list = []\n"
        "def f(a: object) -> object:\n"
        "    if isinstance(a, str):\n"
        "        return len(a)\n"
        "    return max(min(1, 2), sum([1, 2]), range(3).start)\n"
        "class C:\n"
        "    p = property(lambda self: 1)\n"
        "try:\n"
        "    pass\n"
        "except ValueError:\n"
        "    pass\n"
    )
    found = _builtin_allowlist_violations(sanctioned_source)
    assert found == [], f"false positive on sanctioned builtins: {found}"

    # Round 6, Finding 1: earlier rounds asserted a same-scope shadow (a
    # parameter named after a forbidden builtin) was exempted -- that
    # sentence and this assertion were themselves the mechanism the
    # comprehension mutations above exploited at a *different* scope. There
    # is no longer any locally-bound-name exemption for a name that collides
    # with a real builtin, same-scope or not: the binding itself is now the
    # violation.
    same_scope_shadow = "def f(open: int) -> int:\n    return open\n"
    assert _builtin_allowlist_violations(same_scope_shadow) != []


def test_no_leaf_module_references_a_dunder_attribute() -> None:
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, list[str]] = {}
    for path in py_files:
        found = _dunder_attribute_violations(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if found:
            violations[path.name] = found
    assert violations == {}, f"dunder attribute reference(s): {violations}"


def test_dunder_attribute_detection_catches_every_reported_spelling() -> None:
    offenders = {
        "globals_attr": "x = f.__globals__\n",
        "mro_attr": "x = type(y).__mro__\n",
        "subclasses_call": "x = object.__subclasses__()\n",
        "importlib_dunder_import": "importlib.__import__('os')\n",
        # Round 5, Finding 1: a bare dunder *name* in Load context, no
        # attribute access at all -- ``_b = __builtins__["__import__"]``
        # confirmed live against ``power.compute`` before this fix.
        "bare_builtins_subscript": '_b = __builtins__["__import__"]\n',
        "bare_builtins_assignment": "_z = __builtins__\n",
        "bare_file_assignment": "_p = __file__\n",
    }
    for label, source in offenders.items():
        found = _dunder_attribute_violations(source)
        assert found != [], f"{label}: offending dunder attribute was not caught"

    sanctioned = {
        "ordinary_attr": "x = benchmark.value\n",
        "dunder_all_assignment_not_attribute": "__all__ = ('x',)\n",
    }
    for label, source in sanctioned.items():
        found = _dunder_attribute_violations(source)
        assert found == [], f"{label}: false positive: {found}"


def test_every_leaf_modules_top_level_defs_match_the_measured_allowlist() -> None:
    """Req 9.6's only pin in this module: no leaf module defines a function
    or class outside its exact, measured set. A new
    ``modelled_running_power_w`` in ``heart_rate.py``, a strength-load
    calculator, or a build-time power-calibrated heart-rate regression would
    each need a new def name, and none is allowlisted anywhere.
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    measured: dict[str, frozenset[str]] = {}
    for path in py_files:
        measured[path.stem] = _module_defs(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
    diffs = {
        stem: {
            "new": sorted(measured[stem] - _EXPECTED_DEFS.get(stem, frozenset())),
            "removed": sorted(_EXPECTED_DEFS.get(stem, frozenset()) - measured[stem]),
        }
        for stem in measured
        if measured[stem] != _EXPECTED_DEFS.get(stem, frozenset())
    }
    assert diffs == {}, (
        f"top-level def/class set changed: {diffs} -- if this is a "
        f"deliberate, reviewed addition, update _EXPECTED_DEFS to match; if "
        f"it is not, it is exactly the class of defect Req 9.6 forbids"
    )


def test_def_allowlist_detection_catches_a_new_function() -> None:
    found = _module_defs(
        "def compute():\n    pass\n\n\ndef modelled_running_power_w(x):\n    return x\n"
    )
    assert found == frozenset({"compute", "modelled_running_power_w"})


def test_every_leaf_modules_module_level_bindings_match_the_measured_allowlist() -> (
    None
):
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    measured: dict[str, frozenset[str]] = {}
    for path in py_files:
        measured[path.stem] = _module_level_bindings(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
    diffs = {
        stem: {
            "new": sorted(
                measured[stem] - _EXPECTED_MODULE_LEVEL_BINDINGS.get(stem, frozenset())
            ),
            "removed": sorted(
                _EXPECTED_MODULE_LEVEL_BINDINGS.get(stem, frozenset()) - measured[stem]
            ),
        }
        for stem in measured
        if measured[stem] != _EXPECTED_MODULE_LEVEL_BINDINGS.get(stem, frozenset())
    }
    assert diffs == {}, (
        f"module-level binding set changed: {diffs} -- if this is a "
        f"deliberate, reviewed addition, update "
        f"_EXPECTED_MODULE_LEVEL_BINDINGS to match; a new binding here is "
        f"also, by construction, a new uncited constant unless the module's "
        f"docstring is updated in the same change"
    )


def test_module_level_binding_detection_catches_a_new_constant() -> None:
    found = _module_level_bindings("X = 1\nY: float = 2.0\n")
    assert found == frozenset({"X", "Y"})


def test_module_level_binding_detection_catches_every_module_scope_binding_form() -> (
    None
):
    """Fixture-discrimination companion for round 4's fix: ``for``, walrus,
    ``with ... as``, ``except ... as``, and augmented-assignment targets at
    module scope are all module-level bindings -- and a name bound only
    inside a ``def``/``class``/lambda/comprehension is *not* one, since that
    scope is not the module's."""
    assert _module_level_bindings("for _EVIL in (1, 2):\n    pass\n") == frozenset(
        {"_EVIL"}
    )
    assert _module_level_bindings("if (_EVIL2 := 42):\n    pass\n") == frozenset(
        {"_EVIL2"}
    )
    assert _module_level_bindings("with open('x') as _f:\n    pass\n") == frozenset(
        {"_f"}
    )
    assert _module_level_bindings(
        "try:\n    pass\nexcept ValueError as _e:\n    pass\n"
    ) == frozenset({"_e"})
    assert _module_level_bindings("_x = 0\n_x += 1\n") == frozenset({"_x"})

    # `global x` inside a function body is a module-level binding even
    # though the assignment itself is written inside a scope boundary this
    # function otherwise never descends into -- this task's own adversarial
    # re-check found this gap after the fix above was first written.
    assert _module_level_bindings(
        "def f():\n    global _SUDO\n    _SUDO = 42\n"
    ) == frozenset({"_SUDO"})

    # Scope exemption: a name bound only inside a def/class/lambda is not a
    # module-level binding, and must not be reported as one.
    assert (
        _module_level_bindings(
            "class C:\n    A = 1\n\n\ndef f():\n    B = 2\n    return B\n"
        )
        == frozenset()
    )

    # Round 5's fix (Finding 3): a walrus target inside a comprehension
    # binds the *enclosing* (here, module) scope per PEP 572, even though
    # the comprehension itself is a scope boundary for its own loop
    # variable -- confirmed live against ``power.py`` before this fix.
    assert _module_level_bindings(
        "if [(_FUDGE := 0.83) for _ in (0,)]:\n    pass\n"
    ) == frozenset({"_FUDGE"})
    # The comprehension's own loop variable is *not* leaked.
    assert "_" not in _module_level_bindings(
        "if [(_FUDGE := 0.83) for _ in (0,)]:\n    pass\n"
    )

    # Round 5's fix (Finding 3): match/case capture patterns are module-level
    # bindings, and are not `ast.Name`/`ast.Store` nodes at all -- confirmed
    # live against ``power.py`` before this fix.
    assert _module_level_bindings(
        "match 0.83:\n    case float(_FUDGE2):\n        pass\n"
    ) == frozenset({"_FUDGE2"})
    assert _module_level_bindings(
        "match [0.83]:\n    case [*_REST]:\n        pass\n"
    ) == frozenset({"_REST"})
    assert _module_level_bindings(
        "match {'a': 1}:\n    case {'a': 1, **_REMAINDER}:\n        pass\n"
    ) == frozenset({"_REMAINDER"})


def test_every_leaf_modules_enum_member_refs_match_the_measured_allowlist() -> None:
    """Structural half of Req 9.5: no module references a ``Sport``/
    ``Modality`` member outside the one measured, sanctioned reference
    (``pace``'s own ``Modality.RUN`` applicability check)."""
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    measured: dict[str, frozenset[str]] = {}
    for path in py_files:
        measured[path.stem] = _enum_member_refs(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
    diffs = {
        stem: {
            "new": sorted(
                measured[stem] - _EXPECTED_ENUM_MEMBER_REFS.get(stem, frozenset())
            ),
            "removed": sorted(
                _EXPECTED_ENUM_MEMBER_REFS.get(stem, frozenset()) - measured[stem]
            ),
        }
        for stem in measured
        if measured[stem] != _EXPECTED_ENUM_MEMBER_REFS.get(stem, frozenset())
    }
    assert diffs == {}, f"Sport/Modality member-reference set changed: {diffs}"


def test_enum_member_ref_detection_catches_a_new_reference() -> None:
    found = _enum_member_refs("x = Sport.RIDE\ny = Modality.SWIM\n")
    assert found == frozenset({"Sport.RIDE", "Modality.SWIM"})


def test_reachability_probe_finds_no_fitdocs_load_module_via_attribute_chains() -> None:
    """Residual U3 (declared below), closed rather than left open: a BFS over
    non-dunder attribute chains from the objects the leaf modules' own
    sanctioned imports bind reaches zero modules under ``fitdocs.load``.
    This is a runtime probe, not a static one -- it complements, rather than
    substitutes for, the static import allowlist above, and is bounded (a
    max chain length and an identity-based visited set) so it terminates
    even if a future sanctioned import introduces a reference cycle.
    """
    import inspect
    import types as _types

    from fitdocs.benchmarks import Benchmark, BenchmarkKind
    from fitdocs.citation import Citation, VerificationStatus
    from fitdocs.metrics import sources as metrics_sources
    from fitdocs.metrics.stress import power_tss, trimp
    from fitdocs.metrics.types import DerivedMetrics
    from fitdocs.model import Activity, Modality, Samples

    roots: dict[str, object] = {
        "metrics_sources": metrics_sources,
        "power_tss": power_tss,
        "trimp": trimp,
        "DerivedMetrics": DerivedMetrics,
        "Activity": Activity,
        "Modality": Modality,
        "Samples": Samples,
        "Benchmark": Benchmark,
        "BenchmarkKind": BenchmarkKind,
        "Citation": Citation,
        "VerificationStatus": VerificationStatus,
    }
    seen: set[int] = set()
    hits: list[tuple[str, str]] = []
    queue: list[tuple[str, object]] = list(roots.items())
    walked = 0
    while queue:
        path, obj = queue.pop(0)
        if id(obj) in seen or len(path) > 200:
            continue
        seen.add(id(obj))
        walked += 1
        if isinstance(obj, _types.ModuleType) and obj.__name__.startswith(
            "fitdocs.load"
        ):
            hits.append((path, obj.__name__))
            continue
        for attr in dir(obj):
            if attr.startswith("__") and attr.endswith("__"):
                continue
            try:
                value = getattr(obj, attr)
            except Exception:  # noqa: BLE001 -- probing arbitrary attrs
                continue
            if (
                isinstance(value, _types.ModuleType)
                or inspect.isclass(value)
                or isinstance(value, _types.FunctionType)
            ):
                queue.append((f"{path}.{attr}", value))
    assert walked > 10, (
        "vacuous probe: fewer than 10 objects walked -- the roots are not "
        "exercising the real sanctioned-import surface"
    )
    assert hits == [], f"fitdocs.load module(s) reachable via attribute chains: {hits}"


# ===========================================================================
# Declared residuals -- properties this module's structural pins do *not*
# close, named honestly rather than silently left implied-covered. A guard
# that claims more than it delivers has been this task's defect twice
# (rounds 1 and 2 both shipped a denylist whose own docstring overclaimed
# closure); this module does not ship a third overclaiming docstring.
#
# U1 (Req 9.5, general form -- "shall not map an activity's modality to a
# benchmark discipline"). What is pinned above (Req 9.5's *structural* half)
# is: no dict literal keyed on a ``Sport``/``Modality`` member
# (``test_no_module_defines_a_modality_or_sport_keyed_mapping``), and the
# exact set of ``Sport``/``Modality`` member references
# (``test_every_leaf_modules_enum_member_refs_match_the_measured_allowlist``).
# What is NOT pinned: a modality-to-discipline mapping written entirely
# inside a function body over *string* literals, never touching the
# ``Sport``/``Modality`` enums or a dict literal at all. Proof, by mutation:
# inserting ``_d = {"run": "running", "ride": "cycling"}`` as the first
# statement of ``pace.compute`` leaves this module's entire suite green --
# no AST shape pinned above distinguishes that dict (module-level-binding
# allowlist does not see it, since it is function-local; def allowlist does
# not see it, since it defines no new function; the dict-keyed-on-enum-member
# check does not see it, since its keys are string literals, not enum
# members) from ordinary control-flow logic. The structural proxies pinned
# above are what is pinned, not the semantic property Req 9.5 actually
# names; U1 states that gap rather than papering over it with a guard that
# would need to re-derive "is this dict a modality mapping" from its
# *values* rather than its *shape*, which is exactly the kind of semantic
# judgment an AST walk cannot make soundly.
#
# U2 (Req 1.10, "invoke no language model"). Already correctly declared in
# :func:`_interface_references`'s own docstring above -- restated here only
# so this module's residuals are discoverable from one place. No fixed set
# of stdlib names or attributes names "call an LLM" the way ``open``/
# ``socket``/``subprocess`` name filesystem or process interfaces, so no AST
# shape in this module asserts it.
#
# U3 (attribute reach into a sanctioned import's transitive namespace) is
# closed against the *currently-bound root set*, not against every possible
# attribute-reachable root -- restated here, round 5, from round 4's own
# restatement (which itself said "the currently-bound root set", not
# "every root a future import could add"; round 5 narrows that further,
# below, per Finding 2). See
# :func:`test_reachability_probe_finds_no_fitdocs_load_module_via_attribute_chains`
# above, a runtime BFS over non-dunder attribute chains from the eleven
# objects the leaves' own sanctioned *names* bind today, asserting nothing
# under ``fitdocs.load`` is reachable (measured: zero hits, >10 objects
# walked, effectively instant). Round 3's roots were exactly the leaves'
# sanctioned import *targets*; Finding 1 (round 4) showed a target being
# sanctioned did not mean every name importable from it was one of those
# eleven roots -- ``from dataclasses import sys`` bound a twelfth root
# (``sys``) the probe above never walked from, because round 3's allowlist
# let it through without the probe's own root list ever being asked to
# grow. What keeps the root set closed *going forward*, so the probe stays
# meaningful without a human re-deriving its root list every round, is
# round 4's name-level import allowlist (:func:`_import_allowlist_violations`,
# ``_ALLOWED_IMPORT_NAMES``): it is exact-set-pinned to precisely
# seventeen names, of which the probe's ``roots`` dict binds and walks from
# exactly eleven -- ``annotations``, ``Sequence``, ``dataclass``,
# ``StrEnum``, ``Final`` and ``Protocol`` are sanctioned, already-bound
# names the probe never constructs an object from or walks (measured:
# ``_ALLOWED_IMPORT_NAMES``'s values union to seventeen distinct names; the
# probe's ``roots`` dict has eleven keys). **Not "the same eleven names,"
# as a prior round of this task stated it** -- what actually holds, and is
# the claim this paragraph now makes, is narrower: any *new* imported name
# (whether or not it lands among the six never-walked ones) reddens the
# import allowlist before it can be added to the probe's root set at all,
# so the set of names available to construct a probe root from cannot
# silently grow. This says nothing about whether the six never-walked
# roots themselves reach ``fitdocs.load`` by attribute chain; an
# independent depth-5 BFS from all seventeen names plus ``math`` (run
# during this task's own review) found zero modules reached beyond
# ``sources`` and ``math``, and no path to ``sys`` or ``fitdocs.load`` --
# so the conclusion holds today, but that BFS is not part of this suite,
# and this paragraph does not claim the probe itself covers those six. Any
# new imported name reddens
# ``test_import_allowlist_permits_no_target_outside_the_measured_twelve``
# before it can be added to a root list at all. **This is a claim about
# roots the module binds under a name.** It says nothing about an object
# constructed and walked with no bound root at all -- that gap is U4,
# below, not closed by U3 and not claimed to be.
#
# U4 (round 5, Finding 2 -- runtime frame/generator introspection reaching
# outside the bound-root set U3 covers). Proof, by mutation: inserted as
# the first three statements inside ``power.compute``'s body (module-scope
# placement would instead be caught by the module-level-binding allowlist,
# for the unrelated reason that it binds three new names -- the residual is
# specifically the *reach*, not the binding, so the proving mutation must
# sit where no binding-form check already fires):
#     _fr = (0 for _ in ()).gi_frame
#     _imp = _fr.f_builtins["__import__"]
#     _leak = _imp("sys").modules.get("fitdocs.load.registry")
# leaves this module's entire suite green (measured: 40/40 passed -- the
# module ships 40 tests; round 5's "39/39" here was stale, re-measured round
# 6, Finding 4).
# ``gi_frame``, ``f_builtins``, ``f_back`` and ``f_globals`` are each an
# ordinary, non-dunder attribute (so :func:`_dunder_attribute_violations`
# does not fire), reached from a generator expression built *in situ* --
# not from any of the eleven names ``_ALLOWED_IMPORT_NAMES``/the U3 probe's
# ``roots`` dict track, and not from any builtin name either (round 4's
# builtin allowlist governs *names referenced*, and no builtin name is
# referenced here at all). This is declared, not chased: the fix this task
# was warned not to make is a frame-introspection denylist (``gi_frame``,
# ``f_builtins``, ``f_back``, ``f_globals``, and whatever else CPython's
# introspection surface exposes next) -- exactly the enumeration shape
# rounds 1 and 2 were rejected for, restarted one abstraction level up. A
# guard with an honestly-stated, mutation-proven residual is shippable; one
# that claims more than it delivers is not.
#
# U5 (round 6, Finding 2 -- class-body provenance guard is literal/
# negated-literal shape only). :func:`_class_body_numeric_constant_names`
# below uses the identical shape test
# :func:`_module_level_numeric_constant_names` uses (``ast.Constant``/
# ``-ast.Constant``), so a class-body constant introduced through any other
# shape is invisible to it, exactly as a module-level constant of another
# shape would evade the numeric extractor (were it not for the separate
# binding-allowlist backstop -- which has no class-body analogue). Proof, by
# mutation, applied to ``SufficiencySettings`` in ``types.py``, each on the
# full suite (2759 passed, 5 skipped, unchanged):
#     SECRET_FUDGE_FACTOR = 0.83 * 1.0      # ast.BinOp
#     _HOLD = (SECRET_FUDGE := 0.83)        # ast.NamedExpr, binds two names
# "Any other shape" names both the *value* shape (the two mutations above)
# and the *statement* form: a ``for`` or ``match`` statement in a class
# body (e.g. ``for _i in (0.83,): SECRET_FUDGE = _i`` inside
# ``SufficiencySettings``) also survives, since the guard walks only the
# class body's own ``Assign``/``AnnAssign`` statements, not an assignment
# nested inside another statement in that body -- covered by this same
# "any other shape" residual, not a separate one.
# Fix considered and rejected for this round: a ``_class_body_bindings``
# exact-set name pin mirroring :func:`_module_level_bindings` would close
# this, but is a wider change than this round's mandate; the narrower,
# verified-true statement is preferred here -- this module's own Req 8.3
# prose (below) is corrected to say "literal/negated-literal shape" rather
# than the unqualified "any … numeric constant" round 3 originally claimed.
# design.md's own text is unaffected by this: it never made the
# per-shape claim to begin with, and this task's boundary does not extend
# to editing design.md.
#
# U6 (round 7 -- dunder reach through a runtime string-formatting call, not
# an ``ast.Attribute``). Proof, by mutation, inserted as the first
# statement inside ``power.compute``'s body (module-scope placement would
# instead redden the module-level-binding allowlist, for the unrelated
# reason that it binds a new name -- the residual is specifically the
# *reach*, not the binding, so the proving mutation must sit where no
# binding-form check already fires, exactly as U4's does):
#     _leak = "{0.__globals__[power_tss].__module__}".format(power_tss)
# leaves this module's entire suite green (measured: 2759 passed, 5
# skipped, exit 0, unchanged). This genuinely performs the dunder access --
# ``_leak`` evaluates to ``'fitdocs.metrics.stress'`` -- and
# ``"{0.__globals__}".format(power_tss)`` alone yields a 12437-character
# rendering of the module's globals, containing ``__builtins__``, both
# measured directly against this branch. The only ``ast.Attribute`` node in
# the mutated source is ``.format``, itself not a dunder-spelled attribute,
# so :func:`_dunder_attribute_violations` does not fire; the dunder spelling
# lives inside the ``ast.Constant`` format-template string, a node shape
# that function's ``ast.Attribute``/dunder-``ast.Name`` walk does not
# parse as Python syntax at all. **F-strings are covered, not exempt** --
# an f-string's ``{obj.__globals__}`` expression parses to a real
# ``ast.Attribute`` node at compile time, which is exactly why the
# ``str.format`` template-string spelling is the gap and not a second
# instance of an already-closed one. This is declared, not chased: closing
# it requires either parsing format-template strings as a second grammar
# (a shape rounds 1 and 2 were rejected for one abstraction level down --
# a denylist over template-string contents) or a denylist over which
# *method names* on a string constant are "introspection-shaped"
# (``.format`` today, whatever else CPython's string-templating surface
# offers next) -- the same enumeration shape this task's round 6 mandate
# explicitly forbids introducing. The reach this mutation demonstrates is
# also bounded: ``str.format`` yields strings only, never a callable or
# other live object, so what leaks through this specific gap is limited to
# whatever information a formatted string can encode -- not, by itself, a
# route to calling anything.
#
# U7 (round 7 -- an uncited numeric constant as a function-signature
# default). Proof, by mutation, applied to ``power.compute``'s existing,
# already-allowlisted signature:
#     def compute(..., _fudge: float = 0.83) -> ChannelOutcome:
# leaves this module's entire suite green (measured: 2759 passed, 5
# skipped, exit 0, unchanged). A parameter default is not a module-level
# binding at all -- :func:`_module_level_bindings`'s own docstring above
# states it treats ``FunctionDef`` as a scope boundary it does not recurse
# into, so ``args.defaults`` (evaluated at ``def``-execution time, in the
# *enclosing* scope, but never walked here) is invisible to it entirely;
# the def's own *name* is pinned separately, by :func:`_module_defs` --
# not by this function at all. It is also not a
# ``tree.body`` ``Assign``/``AnnAssign`` the numeric-constant extractor
# walks, and not a class-body statement :func:`_class_body_numeric_constant_names`
# walks; ``compute`` is already a member of ``_EXPECTED_DEFS`` for
# ``power``, so adding a defaulted keyword-only parameter to its existing
# signature changes no def/class name either. Req 8.3 ("shall not
# introduce a numeric constant without a citation and a stated verification
# status") is violated by this shape -- a channel gaining a tunable
# parameter with an uncited magic default is a realistic edit, not an
# exotic one -- and no assertion in this module names it; the Req 8.3 sweep
# entry below is corrected to say so rather than let its "module-level
# constant of any shape" wording be read as covering this shape too.
# ===========================================================================


# ===========================================================================
# Requirement sweep, corrected. Round 2 mis-mapped determinism under Req 9.6
# and provenance under Req 9.7; both are wrong per the requirement text this
# sweep was read directly from (``.kiro/specs/load-channels/requirements.md``).
# Round 4 additionally corrects: the Req 8.3 entry below now also names the
# class-body half (:func:`_class_body_numeric_constant_names`, closing
# Finding 3), and every mention of ``_ALLOWED_IMPORT_TARGETS`` is replaced
# with ``_ALLOWED_IMPORT_NAMES``/``_ALLOWED_BARE_IMPORT_TARGETS`` (round 3's
# single target-only set was split in two by round 4's fix -- see the
# "Allowlist-shaped structural guard" banner comment above).
#
# Req 1.10 (purity/determinism/IO -- "equal result for equal inputs...
#   read no file, open no network connection, consult no clock, prompt for
#   nothing, read no configuration of its own, and invoke no language
#   model"): determinism half by the determinism trio below (dies on
#   ``test_determinism_assertion_actually_catches_a_nondeterministic_channel``'s
#   monkeypatch companion); file/network/clock/prompting half by
#   ``test_no_module_references_a_filesystem_network_clock_or_prompting_interface``
#   plus the import allowlist above (dies on mutation R1.5/R1.6: ``import
#   subprocess``/``tempfile``/``shutil``/``glob``/``getpass``); "read no
#   configuration of its own" by ``test_import_allowlist_permits_no_target...``
#   (dies on R2.3a: ``import fitdocs`` then
#   ``fitdocs.load.settings.DEFAULT_LOAD_SETTINGS...``); "invoke no language
#   model" is UNPINNED (U2 above). Also dies, for the file/network/clock/
#   config-reading clauses alike, on round 4's own mutation family
#   (``from dataclasses import sys as _sys`` then
#   ``_sys.modules["builtins"].open(...)``/``.input(...)``,
#   ``_sys.modules["time"].time()``, ``_sys.modules["socket"].socket()``, or
#   ``_sys.modules["fitdocs.load.settings"].DEFAULT_LOAD_SETTINGS``) via the
#   name-level import allowlist, before any of those calls is ever reached.
# Req 8.3 (provenance -- "shall not introduce a numeric constant without a
#   citation and a stated verification status"):
#   ``test_every_constant_defining_module_names_a_citation_except_the_known_gap``,
#   strengthened by
#   ``test_every_leaf_modules_module_level_bindings_match_the_measured_allowlist``
#   (a new *module-level* constant of any shape -- meaning a binding this
#   module's own ``_module_level_bindings`` walk sees: ``tree.body``
#   ``Assign``/``AnnAssign`` and the other module-scope binding forms it
#   enumerates -- including the tuple/subscript/imported-attribute shapes
#   the numeric-constant extractor above honestly does not walk, reddens
#   the binding allowlist even if it evades the numeric-literal extraction
#   (this does not reach a numeric default inside a function's own
#   signature, which is neither a module-level binding nor a class-body
#   statement -- that is U7, declared above, not closed here), and --
#   round 4's fix, extended by
#   round 5 to close the comprehension-walrus and match/case-pattern forms
#   Finding 3 found still open -- reddens it regardless of which
#   module-scope *binding form* introduces it, not only plain/annotated
#   assignment), and (round 4, Finding 3) by
#   ``test_no_leaf_modules_class_body_defines_an_unallowlisted_numeric_constant``
#   for the one shape both the numeric extractor and the module-level-binding
#   allowlist miss identically: a numeric constant added directly to the
#   *body* of an existing, already-allowlisted class (a class-body name lives
#   in the class's own namespace, never the module's). Dies on: an uncited
#   new module-level constant of any shape/binding-form without updating both
#   its docstring and the binding allowlist, or an uncited new class-body
#   numeric constant **of the literal or negated-literal shape**
#   (``ast.Constant``/``-ast.Constant``, matching
#   :func:`_module_level_numeric_constant_names`'s own shape test) without
#   updating the class-body allowlist -- not, as round 3 stated it, "any
#   module" as an unqualified claim; a constant introduced some other way
#   this module has not found is not thereby claimed caught. **Round 6,
#   Finding 2 named the residual explicitly:** a class-body constant of any
#   *other* shape -- e.g. ``SECRET_FUDGE_FACTOR = 0.83 * 1.0`` (an
#   ``ast.BinOp``) or a class-body walrus (``_HOLD = (SECRET_FUDGE :=
#   0.83)``) -- evades both this guard and the module-level-binding
#   allowlist identically, since neither walks a class's own ``body`` for
#   non-literal shapes. That residual is U5, proven by mutation in the
#   class-body section below; it is not closed here.
# Req 9.1 (no channel selects/ranks/falls back/decides which value is used):
#   ``test_no_channel_leaf_module_imports_another_channel_leaf_module``
#   (``_EXPECTED_INTRA_PACKAGE_IMPORTS``, kept unchanged). Dies on mutation
#   R1.1 (``from . import heart_rate`` inserted into ``power.py``) -- this is
#   the one mutation of the sixteen the new allowlist tests do *not* kill
#   themselves (the target resolves under the package's own adjacency pin,
#   deliberately, per the fix plan), but the pre-existing, unmodified
#   ``_EXPECTED_INTRA_PACKAGE_IMPORTS`` exact-match assertion still dies on
#   it, since ``power``'s measured intra-package import set gains
#   ``heart_rate``. Also dies on round 4's own mutation
#   (``_sys.modules["fitdocs.load.channels.heart_rate"].compute`` reached via
#   ``from dataclasses import sys as _sys``) via the name-level import
#   allowlist -- a different mechanism than the cross-channel-import case
#   above, but the same requirement clause.
# Req 9.2 (no quality/divergence flag, cadence-lock verdict, or
#   benchmark-staleness verdict): ``test_no_module_references_quality_flag``
#   for the flag identifier directly; the benchmark-staleness half by
#   ``test_no_module_calls_a_benchmark_resolution_function`` plus the import
#   allowlist (dies on R2.1b: ``from fitdocs import benchmarks as _bm`` then
#   ``_bm.benchmark_age`` -- the bare ``from fitdocs import benchmarks``
#   already reds the import allowlist, since ``fitdocs`` alone is not a
#   sanctioned target). Narrower than it may look: a cadence-lock or
#   staleness verdict written as a *new, separately named* function or
#   module-level constant would redden the def or binding allowlist -- but a
#   verdict computed inline, with no new name at all (e.g. an
#   ``if``/``return`` inside ``compute`` itself), is the same class of gap
#   U1 already declares for Req 9.5, and is not separately re-declared here
#   only to avoid repeating it. Also dies on round 4's own mutation
#   (``_sys.modules["fitdocs.benchmarks"].benchmark_age`` reached via
#   ``from dataclasses import sys as _sys``) via the name-level import
#   allowlist.
# Req 9.3 (no read/write/render document, frontmatter key, or
#   machine-readable payload): ``test_no_module_references_a_filesystem_...``
#   for ``pathlib``/``os``/``io``, reinforced by the import allowlist (none
#   of ``pathlib``, ``os``, ``io``, ``fitdocs.render`` is a sanctioned
#   target).
# Req 9.4 (no benchmark resolution from file/date/discipline; consume only
#   what is handed): ``test_no_module_calls_a_benchmark_resolution_function``
#   plus the import allowlist. Dies on mutation R2.1 (``from fitdocs import
#   benchmarks as _bm`` then ``_bm.parse_benchmarks({})`` inside
#   ``compute``) -- the import statement alone reds the allowlist before the
#   call site is ever reached. Also dies on round 4's own mutation
#   (``_sys.modules["fitdocs.benchmarks"].parse_benchmarks({})`` reached via
#   ``from dataclasses import sys as _sys``) via the name-level import
#   allowlist.
# Req 9.5 (no modality-to-discipline mapping): structural half pinned by
#   ``test_no_module_defines_a_modality_or_sport_keyed_mapping`` and
#   ``test_every_leaf_modules_enum_member_refs_match_the_measured_allowlist``;
#   dies on mutation R2.4a (dict-literal form, also independently caught by
#   the module-level-binding allowlist since the dict needs a new binding
#   name). The general form is declared UNPINNED as U1 above; mutation R2.4b
#   (if/return function form) reds only because it needs a new function
#   name (``test_every_leaf_modules_top_level_defs_match_the_measured_allowlist``),
#   not because the mapping itself is detected -- stated honestly in U1
#   rather than claimed as coverage this requirement does not have.
# Req 9.6 (no strength-training load, modelled running-power estimate, or
#   build-time power-calibrated heart-rate regression):
#   ``test_every_leaf_modules_top_level_defs_match_the_measured_allowlist``,
#   the *only* pin on this requirement in this module. Dies on mutation
#   R2.5 (``modelled_running_power_w`` defined in ``heart_rate.py``) --
#   ``heart_rate``'s allowlisted def set is exactly ``{compute}``.
# Req 9.7 (no calculator registration, registry consult, or arbitration):
#   the import allowlist. Dies on mutation R2.3b (``import fitdocs`` then
#   ``fitdocs.load.registry.available()``) -- ``import fitdocs`` alone reds
#   the allowlist before the attribute access is ever reached, via plain
#   non-membership in ``_ALLOWED_BARE_IMPORT_TARGETS`` (``fitdocs`` is a
#   non-dotted target, so this is the ordinary bare-import-membership branch,
#   not the dotted-target rule -- that rule is what separately rejects
#   ``import fitdocs.load.channels.heart_rate as _hr`` in mutation R1.2). Also
#   dies on round 4's own mutation (``_sys.modules["fitdocs.load.registry"]``
#   reached via ``from dataclasses import sys as _sys``) via the name-level
#   half of the same allowlist.
# Req 9.8 (shall not change the shipped derived-metric definitions this
#   layer consumes): out of this module's scope by construction -- it is a
#   claim about ``fitdocs.metrics``'s own behavior being unchanged, not
#   about anything expressible as a structural property of
#   ``fitdocs/load/channels/``'s own source; not asserted here, and not
#   claimed to be.
# ===========================================================================


# ===========================================================================
# Determinism: every channel computed twice over identical inputs agrees.
# ===========================================================================


def test_power_channel_is_deterministic_across_repeated_computation() -> None:
    activity, metrics, ftp, settings = _power_call()
    first = power.compute(activity, metrics, ftp=ftp, settings=settings)
    second = power.compute(activity, metrics, ftp=ftp, settings=settings)
    assert isinstance(first, ChannelLoad)
    assert first == second


def test_heart_rate_channel_is_deterministic_across_repeated_computation() -> None:
    activity, metrics, lthr, resting, maxhr, settings = _heart_rate_call()
    first = heart_rate.compute(
        activity,
        metrics,
        lthr=lthr,
        resting_hr=resting,
        max_hr=maxhr,
        settings=settings,
    )
    second = heart_rate.compute(
        activity,
        metrics,
        lthr=lthr,
        resting_hr=resting,
        max_hr=maxhr,
        settings=settings,
    )
    assert isinstance(first, ChannelLoad)
    assert first == second


def test_pace_channel_is_deterministic_across_repeated_computation() -> None:
    activity, metrics, threshold_pace, settings = _pace_call()
    first = pace.compute(
        activity, metrics, threshold_pace=threshold_pace, settings=settings
    )
    second = pace.compute(
        activity, metrics, threshold_pace=threshold_pace, settings=settings
    )
    assert isinstance(first, ChannelLoad)
    assert first == second


def test_determinism_assertion_actually_catches_a_nondeterministic_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture-discrimination companion for the three determinism assertions
    above: proves the "compute twice, compare" pattern actually catches a
    non-deterministic implementation. Since production code cannot be edited
    in this boundary, the non-determinism is injected via monkeypatch --
    wrapping the real ``power.compute`` so every *other* call perturbs the
    returned ``load`` by a tiny, call-count-dependent amount (deterministic
    in the sense that it does not depend on the wall clock or ``random``, but
    still varies call-to-call the way a stray cache-keyed-on-object-identity
    or an uninitialized accumulator bug would). The wrapped version must fail
    the "compute twice, compare" pattern where the real one passes.
    """
    real_compute = power.compute
    call_count = {"n": 0}

    def _flaky_compute(*args: object, **kwargs: object) -> object:
        call_count["n"] += 1
        result = real_compute(*args, **kwargs)  # type: ignore[arg-type]
        if call_count["n"] % 2 == 0 and isinstance(result, ChannelLoad):
            from dataclasses import replace

            return replace(result, load=result.load + 1e-6)
        return result

    monkeypatch.setattr(power, "compute", _flaky_compute)

    activity, metrics, ftp, settings = _power_call()
    first = power.compute(activity, metrics, ftp=ftp, settings=settings)
    second = power.compute(activity, metrics, ftp=ftp, settings=settings)
    assert isinstance(first, ChannelLoad)
    assert isinstance(second, ChannelLoad)
    assert first != second, (
        "the injected non-determinism did not perturb the result -- the "
        "monkeypatch itself is not wired correctly"
    )


# ===========================================================================
# Provenance: every module defining a numeric constant names a citation key
# in its own module docstring.
# ===========================================================================


def _module_level_numeric_constant_names(
    source: str, *, filename: str = "<test>"
) -> list[str]:
    """Names of every module-level assignment whose value is a bare numeric
    literal (``int``/``float``), or a unary-minus of one -- the shape a
    ``Final[float] = 0.80``-style constant takes. Deliberately narrow, and
    **not** exhaustive over every shape "numeric constant" could mean: a
    tuple of numbers, a value derived by subscripting another constant, or a
    value read off an imported module's attribute are all still "numeric
    constants" by the task's own wording, but none of the three is walked by
    this function, and no companion walk exists elsewhere in this module to
    cover them either. Measured, live examples of all three shapes, left
    genuinely un-inspected by the provenance sweep below:
    ``src/fitdocs/load/channels/grade.py``'s ``MINETTI_RUNNING_COEFFICIENTS``
    (line 86, a tuple literal), ``MINETTI_LEVEL_COST_J_PER_KG_PER_M`` (line
    100, ``MINETTI_RUNNING_COEFFICIENTS[-1]``, a subscript), and
    ``ALTITUDE_SMOOTHING_WINDOW`` (line 113,
    ``metrics_sources.ALTITUDE_SMOOTHING_WINDOW.value``, an imported-module
    attribute). Measured directly against ``grade.py``'s own module
    docstring: ``MINETTI_RUNNING_COEFFICIENTS`` and
    ``ALTITUDE_SMOOTHING_WINDOW`` are named there by identifier;
    ``MINETTI_LEVEL_COST_J_PER_KG_PER_M`` is named only inside a *function*
    docstring (``running_cost_ratio``'s), not the module ``__doc__`` this
    task's provenance rule actually reads. This gap is in the *guard's*
    coverage, not a claim about whether the underlying values are provenanced
    -- it is left open by this task's boundary rather than closed, and is
    not asserted anywhere below.
    """
    tree = ast.parse(source, filename=filename)
    names: list[str] = []
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target = node.target
            value = node.value
        if target is None or not isinstance(target, ast.Name) or value is None:
            continue
        is_numeric = isinstance(value, (ast.Constant,)) and isinstance(
            value.value, (int, float)
        )
        is_negated_numeric = (
            isinstance(value, ast.UnaryOp)
            and isinstance(value.op, ast.USub)
            and isinstance(value.operand, ast.Constant)
            and isinstance(value.operand.value, (int, float))
        )
        if is_numeric or is_negated_numeric:
            names.append(target.id)
    return names


def _citation_names_from_sources_module() -> frozenset[str]:
    """The real, current set of citation binding names (``COGGAN_TSS``,
    ``BANISTER_TRIMP``, ...) defined in ``sources.py`` -- read from that
    module's own AST rather than hardcoded, so a citation rename or
    addition is picked up automatically rather than silently drifting stale.
    """
    source = (_CHANNELS_DIR / "sources.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="sources.py")
    names: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "Citation"
        ):
            names.add(node.target.id)
    return frozenset(names)


def test_citation_names_extraction_finds_the_real_citations() -> None:
    """Vacuity check for :func:`_citation_names_from_sources_module`: the
    real ``sources.py`` defines at least six ``Citation`` bindings (measured:
    ``COGGAN_TSS``, ``BANISTER_TRIMP``, ``MINETTI_2002``,
    ``INTERVALS_ICU_PACE_LOAD``, ``INTERVALS_ICU_HRSS``,
    ``TRAININGPEAKS_COVERAGE_GATE``). A regex or AST pattern that matched
    nothing would let every provenance assertion below pass vacuously."""
    names = _citation_names_from_sources_module()
    assert len(names) >= 6, f"vacuous extraction: found only {names}"
    assert "COGGAN_TSS" in names
    assert "TRAININGPEAKS_COVERAGE_GATE" in names


# The known, pre-existing gap this task's own handoff note flags:
# ``types.py`` defines two numeric constants
# (``DEFAULT_MIN_STREAM_COVERAGE``, ``DEFAULT_MIN_DURATION_S``) and predates
# the "name a citation key in the module docstring" convention every leaf
# module task 2.1-3.3 followed. Measured directly: neither citation name
# appears anywhere in ``types.py``'s own top-level module docstring (the
# ``TRAININGPEAKS_COVERAGE_GATE`` mention lives on
# ``DEFAULT_MIN_STREAM_COVERAGE``'s own *trailing* docstring, a different,
# non-``__doc__`` string -- and ``DEFAULT_MIN_DURATION_S``'s trailing
# docstring names no citation at all, explicitly documenting itself as
# "fitdocs' own, not a published figure"). This module does not weaken the
# provenance rule to paper over that pre-existing gap: reporting the true
# state honestly, rather than loosening the assertion until it passes, is
# the choice that keeps this guard meaningful for every module added after
# it. So the assertion below pins the *true*, current state: every
# constant-defining
# module cites in its module docstring **except** the one named,
# pre-existing exception, which is itself asserted to still be exactly
# ``types``, not silently grown to cover a future violation elsewhere.
_KNOWN_UNCITED_MODULES = frozenset({"types"})


def test_every_constant_defining_module_names_a_citation_except_the_known_gap() -> None:
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    citation_names = _citation_names_from_sources_module()

    modules_with_constants: set[str] = set()
    uncited: set[str] = set()
    for path in py_files:
        source = path.read_text(encoding="utf-8")
        constant_names = _module_level_numeric_constant_names(
            source, filename=str(path)
        )
        if not constant_names:
            continue
        modules_with_constants.add(path.stem)
        tree = ast.parse(source, filename=str(path))
        docstring = ast.get_docstring(tree) or ""
        if not any(key in docstring for key in citation_names):
            uncited.add(path.stem)

    assert modules_with_constants, (
        "vacuous sweep: no module in the package defines any module-level "
        "numeric constant -- the extractor is not matching real content"
    )
    assert uncited == _KNOWN_UNCITED_MODULES, (
        f"provenance rule violated by an undeclared module (or the known gap "
        f"was silently fixed and this allowlist is now stale): {uncited}"
    )


def test_provenance_walk_actually_flags_an_uncited_constant() -> None:
    """Fixture-discrimination companion: proves the extraction + docstring
    check catches a genuinely uncited numeric constant, and does not flag a
    cited one, on synthetic source."""
    citation_names = _citation_names_from_sources_module()
    assert citation_names, "vacuity check: no citation names extracted at all"
    one_citation = next(iter(citation_names))

    uncited_source = '"""No citation here."""\nSOME_CONSTANT = 42\n'
    cited_source = f'"""See {one_citation}."""\nSOME_CONSTANT = 42\n'

    for source, expect_flag in ((uncited_source, True), (cited_source, False)):
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree) or ""
        constant_names = _module_level_numeric_constant_names(source)
        assert constant_names == ["SOME_CONSTANT"]
        is_cited = any(key in docstring for key in citation_names)
        assert is_cited is not expect_flag


def test_numeric_constant_extraction_ignores_non_numeric_module_level_assignments() -> (
    None
):
    """Fixture-discrimination companion for
    :func:`_module_level_numeric_constant_names`: a string constant, a
    ``Citation(...)`` call, and a tuple are not flagged as numeric --
    proving the extractor discriminates on *type*, not merely on "is this a
    module-level assignment"."""
    source = (
        "GREETING: str = 'hello'\n"
        "PAIR = (1, 2)\n"
        "REAL_NUMBER: float = 0.5\n"
        "NEGATIVE: float = -0.5\n"
    )
    names = _module_level_numeric_constant_names(source)
    assert names == ["REAL_NUMBER", "NEGATIVE"], names


# ===========================================================================
# Req 8.3, class-body half (round 4 fix, Finding 3). A numeric constant
# added directly to the body of an existing, already-allowlisted class
# (e.g. ``SECRET_FUDGE_FACTOR = 0.83`` inside ``ChannelLoad``) is invisible
# to both provenance guards above: :func:`_module_level_numeric_constant_names`
# only walks ``tree.body`` (module scope, not a class's own ``body``), and
# the module-level-binding allowlist above sees only names bound in the
# *module's* namespace -- a class-body name lives in the class's own
# namespace, reachable as ``ChannelLoad.SECRET_FUDGE_FACTOR``, not as a
# bare module-level name, so it does not appear in either walk. This section
# closes that gap **for the literal and negated-literal shapes only** --
# ``ast.Constant``/``-ast.Constant``, the same shape test
# :func:`_module_level_numeric_constant_names` uses -- on the same
# "exact-set pin, re-measured against the real leaf modules" pattern as the
# rest of this module: no leaf-module class defines any numeric-literal
# class-body attribute today (verified below), so the allowlist is the
# empty set, and any class body that starts to needs one must add it
# explicitly.
#
# **Round 6, Finding 2 -- named residual, not closed here.** A class-body
# constant of a *different* shape -- ``SECRET_FUDGE_FACTOR = 0.83 * 1.0``
# (``ast.BinOp``) or a class-body walrus (``_HOLD = (SECRET_FUDGE :=
# 0.83)``) -- evades this guard identically to how it evades the
# module-level guards above, hand-verified: each mutation applied to
# ``SufficiencySettings`` in ``types.py`` left the full suite green (2759
# passed, 5 skipped). This is U5: an honestly-stated residual of the same
# shape as U2-U4 above, not a claim this section does not deliver on.
# ===========================================================================


def _class_body_numeric_constant_names(
    source: str, *, filename: str = "<test>"
) -> dict[str, list[str]]:
    """Every numeric-literal-valued ``ast.Assign``/``ast.AnnAssign`` directly
    inside a top-level ``ast.ClassDef``'s own ``body`` (not nested further,
    matching :func:`_module_level_numeric_constant_names`'s own scope --
    module scope there, class scope here), keyed by the owning class's name.
    Uses the identical numeric-literal / negated-numeric-literal shape test
    as :func:`_module_level_numeric_constant_names` so the two stay provably
    consistent rather than drifting into two different definitions of
    "numeric constant".
    """
    tree = ast.parse(source, filename=filename)
    found: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        names: list[str] = []
        for stmt in node.body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                value = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                target = stmt.target
                value = stmt.value
            if target is None or not isinstance(target, ast.Name) or value is None:
                continue
            is_numeric = isinstance(value, ast.Constant) and isinstance(
                value.value, (int, float)
            )
            is_negated_numeric = (
                isinstance(value, ast.UnaryOp)
                and isinstance(value.op, ast.USub)
                and isinstance(value.operand, ast.Constant)
                and isinstance(value.operand.value, (int, float))
            )
            if is_numeric or is_negated_numeric:
                names.append(target.id)
        if names:
            found[node.name] = names
    return found


def test_no_leaf_modules_class_body_defines_an_unallowlisted_numeric_constant() -> None:
    """Req 8.3's class-body half: no leaf-module class defines a
    numeric-literal constant directly in its own body. Closes the gap
    Finding 3 (round 4 review) named -- see the section banner above.
    Measured: the allowlist is the empty set; every leaf-module class today
    defines only typed fields (no bare numeric class attribute).
    """
    py_files = sorted(_CHANNELS_DIR.glob("*.py"))
    assert len(py_files) >= 9, (
        "vacuous walk: the walk is looking at the wrong directory"
    )
    violations: dict[str, dict[str, list[str]]] = {}
    for path in py_files:
        found = _class_body_numeric_constant_names(
            path.read_text(encoding="utf-8"), filename=str(path)
        )
        if found:
            violations[path.name] = found
    assert violations == {}, (
        f"numeric constant(s) defined directly in a class body: {violations} "
        f"-- uncited, and invisible to the module-level provenance pins "
        f"above; if this is deliberate, add a citation and update this test"
    )


def test_class_body_numeric_constant_detection_catches_the_shape() -> None:
    found = _class_body_numeric_constant_names(
        "class C:\n"
        "    x: int\n"
        "    SECRET_FUDGE_FACTOR = 0.83\n"
        "    NEGATIVE = -1\n"
        "    NAME = DEFAULT\n"
        "    LABEL = 'x'\n"
    )
    assert found == {"C": ["SECRET_FUDGE_FACTOR", "NEGATIVE"]}

    # Vacuity/false-positive check: a class with no numeric class-body
    # constant produces no entry at all, not an empty list.
    clean = _class_body_numeric_constant_names(
        "class D:\n    name: str\n    def m(self) -> int:\n        return 1\n"
    )
    assert clean == {}
