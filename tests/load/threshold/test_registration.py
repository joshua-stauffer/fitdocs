"""Contract tests for the threshold calculator's registration (task 4.1,
design: ``BuiltInRegistration`` / ``PublicSurfacePin``, Req 1.1, 1.2, 1.3,
11.2, 11.3).

``fitdocs.load``'s own package initializer (``src/fitdocs/load/__init__.py``)
imports ``THRESHOLD_CALCULATOR`` from
:mod:`fitdocs.load.threshold.calculator` and calls
:func:`fitdocs.load.registry.register` on it -- the same call, through the
same :func:`~fitdocs.load.registry.validate_calculator` gate, every
third-party calculator's registration goes through (Req 1.2). Registration
does NOT live in :mod:`fitdocs.load.threshold` or in
:mod:`fitdocs.load.threshold.calculator` itself -- both modules make no
``register()`` call of their own -- so no import path through this package
ever registers the built-in a *second* time, even though, because this
package is nested under ``fitdocs.load``, Python necessarily runs
``fitdocs/load/__init__.py`` (and so performs the ONE registration) on the
way to importing any leaf here.

Every test below is written to be robust to run order: module import is
process-global, so several tests here run a fresh interpreter in a
subprocess rather than trust in-process state left by whichever test
happened to import ``fitdocs.load`` first. Each test is also confirmed to
pass standalone (``pytest tests/load/threshold/test_registration.py -k
<name>``), not only as part of the full suite.
"""

from __future__ import annotations

import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path

from fitdocs import Modality
from fitdocs.load import THRESHOLD_CALCULATOR, registry
from fitdocs.load.registry import (
    DuplicateCalculatorIdError,
    InvalidCalculatorError,
    validate_calculator,
)
from fitdocs.plugins import DEFAULT_PLUGIN_SETTINGS, BuiltIn, discover

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CALCULATOR_PATH = (
    _PROJECT_ROOT / "src" / "fitdocs" / "load" / "threshold" / "calculator.py"
)


# --- 1.1: a fresh interpreter registers exactly one calculator, "threshold" -


def test_fresh_interpreter_registers_exactly_the_threshold_calculator() -> None:
    """Importing ``fitdocs.load`` in a fresh interpreter (never a cached
    ``sys.modules`` re-import, which would run no module-level code and prove
    nothing about a cold import) leaves the registry holding exactly the one
    calculator ``threshold`` -- pinned by identifier, not merely by count.
    """
    code = (
        "import fitdocs.load as load\n"
        "ids = tuple(c.calculator_id for c in load.available())\n"
        "print(f'IDS={ids!r}')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert "IDS=('threshold',)" in result.stdout, result.stdout


# --- 1.1: "exactly one" pinned both ways -------------------------------------


def test_available_is_exactly_the_threshold_calculator_in_process() -> None:
    """In-process mirror of the subprocess test above, at the point in the
    suite this test itself runs: whichever test imported ``fitdocs.load``
    first in this worker, the registry holds exactly
    ``(THRESHOLD_CALCULATOR,)``, never more (a leaked plugin) and never
    fewer (a missed registration).

    This does NOT hold at every point during the suite -- every
    ``isolated_registry`` test clears the registry for its own scope, and
    some ``tests/load/test_arbitration_e2e.py`` tests temporarily exclude
    the built-in to make a stub the sole supporter of a modality -- so this
    assertion is only ever meaningful, and only ever run, here.
    """
    assert registry.available() == (THRESHOLD_CALCULATOR,)


def test_registering_a_second_calculator_makes_available_two() -> None:
    """The "exactly one" pin above is not vacuous: registering a second,
    distinct calculator alongside the built-in genuinely changes
    ``available()`` to hold two entries, proving the equality pin would catch
    an unexpected extra registration rather than only ever comparing against
    itself."""
    extra_id = "test-registration-second-calculator"

    class _Extra:
        calculator_id = extra_id
        display_name = "Extra"
        supported_modalities = frozenset({Modality.RUN})

        def required_athlete_fields(self) -> tuple[object, ...]:
            return ()

        def compute(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("compute must not be invoked by this test")

    registry.register(_Extra())
    try:
        available_ids = {c.calculator_id for c in registry.available()}
        assert available_ids == {"threshold", extra_id}
        assert len(registry.available()) == 2
    finally:
        registry.unregister(extra_id)

    # Restored: back to exactly the built-in.
    assert registry.available() == (THRESHOLD_CALCULATOR,)


def test_unregistering_the_built_in_makes_available_empty() -> None:
    """The other direction: removing the built-in genuinely empties the
    registry (when nothing else is registered), proving the "exactly one"
    pin would also catch the built-in going missing, not only an extra
    entry.

    Asserts the built-in is present BEFORE unregistering it: without that,
    if the product ever failed to register it, this test would unregister
    nothing, observe the already-empty registry, and pass vacuously --
    while still re-registering the built-in in its ``finally``, papering
    over the very defect it exists to catch for every test that runs after
    it (REMEDIATION ROUND 1 finding 5).
    """
    assert registry.available() == (THRESHOLD_CALCULATOR,)  # present before removal
    registry.unregister("threshold")
    try:
        assert registry.available() == ()
    finally:
        registry.register(THRESHOLD_CALCULATOR)

    # Restored.
    assert registry.available() == (THRESHOLD_CALCULATOR,)


# --- 1.2: the built-in needs no privilege a third-party author lacks --------


def test_threshold_calculator_passes_validate_calculator() -> None:
    """The built-in satisfies :func:`~fitdocs.load.registry.validate_calculator`
    -- the same pure-introspection gate a third-party calculator's
    registration passes through -- with no bypass flag or special case."""
    assert validate_calculator(THRESHOLD_CALCULATOR) is None


def test_registering_threshold_a_second_time_raises_the_ordinary_duplicate_error() -> (
    None
):
    """Registering ``THRESHOLD_CALCULATOR`` again -- with it already
    registered by ``fitdocs.load``'s own package initializer -- raises the
    ORDINARY :class:`~fitdocs.load.registry.DuplicateCalculatorIdError` any
    caller gets for a contested id. There is no privileged
    "re-register the built-in" path that silently succeeds or replaces the
    incumbent.

    Asserts the incumbent is present BEFORE attempting the duplicate
    registration: without that, if the product ever failed to register the
    built-in, ``registry.register(THRESHOLD_CALCULATOR)`` below would find no
    incumbent, succeed, and install it -- masking the very defect this test
    exists to catch, and leaving a wrongly-registered built-in in place for
    every test that runs after it (REMEDIATION ROUND 2 finding 3)."""
    assert registry.available() == (THRESHOLD_CALCULATOR,)  # incumbent present
    try:
        registry.register(THRESHOLD_CALCULATOR)
        raise AssertionError("expected DuplicateCalculatorIdError")
    except DuplicateCalculatorIdError as exc:
        assert exc.calculator_id == "threshold"
    # The incumbent registration is untouched (Req 3.3 of plugin-api, carried
    # by registry.register's own contract).
    assert registry.available() == (THRESHOLD_CALCULATOR,)


def test_a_structurally_malformed_threshold_shaped_object_is_rejected() -> None:
    """The gate genuinely inspects the object, rather than special-casing the
    id ``"threshold"``: a same-id object missing a required member is
    rejected exactly like any other malformed calculator would be, naming
    the violated member."""

    class _BrokenThreshold:
        calculator_id = "threshold"
        display_name = "Threshold Load"
        supported_modalities = frozenset({Modality.RUN})
        # No ``required_athlete_fields``, no ``compute``: structurally invalid.

    reason = validate_calculator(_BrokenThreshold())
    assert reason is not None
    assert "required_athlete_fields" in reason

    try:
        registry.register(_BrokenThreshold())  # type: ignore[arg-type]
        raise AssertionError("expected InvalidCalculatorError")
    except InvalidCalculatorError:
        pass
    # Rejected before ever reaching the duplicate-id check, and the real
    # built-in is still the sole "threshold" registration.
    assert registry.get("threshold") is THRESHOLD_CALCULATOR


# --- 1.3: the plugin inventory reports it as a built-in at the installed ----
# --- fitdocs version ---------------------------------------------------------


def test_plugin_inventory_reports_threshold_as_built_in_at_installed_version() -> None:
    """:func:`fitdocs.plugins.discover` reports the ``threshold`` entry with a
    :class:`~fitdocs.plugins.BuiltIn` origin and a version equal to the
    INSTALLED fitdocs version -- not merely a string containing the word
    "built-in" somewhere in a rendering (the CLI table is a presentation
    concern this test does not touch), and not a fabricated or hardcoded
    version literal."""
    report = discover(None, DEFAULT_PLUGIN_SETTINGS)
    entry = next(c for c in report.calculators if c.calculator_id == "threshold")
    assert isinstance(entry.origin, BuiltIn)
    assert entry.version == importlib.metadata.version("fitdocs")
    assert entry.version is not None  # never the fabricated/absent case


# --- the calculator module itself performs no registration of its own ------


def test_calculator_module_source_contains_no_top_level_register_call() -> None:
    """Static proof that :mod:`fitdocs.load.threshold.calculator` never calls
    ``register(...)`` at module top level: an AST walk over its own top-level
    statements finds no ``Call`` whose function name is ``register``. This is
    the property that is actually independent of Python's package-import
    order (unlike an in-process or even a fresh-interpreter dynamic import of
    the module, which necessarily also runs ``fitdocs/load/__init__.py`` --
    and so performs the one real registration -- because this module is
    nested under the ``fitdocs.load`` package)."""
    tree = ast.parse(_CALCULATOR_PATH.read_text(encoding="utf-8"))

    def _calls_register(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "register"
            ):
                return True
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "register"
            ):
                return True
        return False

    top_level_calls = [
        stmt
        for stmt in tree.body
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
    ]
    assert not any(_calls_register(stmt) for stmt in top_level_calls), (
        "calculator.py must not register the built-in itself -- registration "
        "belongs to fitdocs/load/__init__.py alone"
    )


def test_importing_the_calculator_module_directly_registers_exactly_once() -> None:
    """A fresh interpreter that imports ONLY
    ``fitdocs.load.threshold.calculator`` (never ``fitdocs.load`` by name)
    still ends up with exactly one registration -- the one
    ``fitdocs/load/__init__.py`` performs as this module's parent package,
    proven by the previous test to be calculator.py's only source. If
    calculator.py registered a second time on its own, ``fitdocs.load``'s own
    ``register(THRESHOLD_CALCULATOR)`` call would find the id already taken
    and this import would raise ``DuplicateCalculatorIdError`` instead of
    succeeding.
    """
    code = (
        "import fitdocs.load.threshold.calculator as calc\n"
        "from fitdocs.load import registry\n"
        "ids = tuple(c.calculator_id for c in registry.available())\n"
        "print(f'IDS={ids!r}')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_PROJECT_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert "IDS=('threshold',)" in result.stdout, result.stdout
