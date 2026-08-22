"""Shared calculator stubs for the load-layer test suite (task 1.1).

fitdocs ships no calculator of its own (Amendment 2): the third-party
methodology it once shipped was withdrawn (task 1.3) and the first real
methodology arrives from ``threshold-load``. Until then, and even afterward
for tests that must stay methodology-agnostic, the suite needs a calculator
subject built from nothing but the *published*
:class:`~fitdocs.load.types.LoadCalculator` contract -- no privilege a
third-party plugin author lacks (Req 1.1).

Four stubs cover the outcome and declaration surface every later task needs:

* :class:`ComputingCalculator` reaches :class:`~fitdocs.load.types.Computed`
  for a supported activity once its one declared field is present and
  confirmed. Its ``compute`` assembles the result from a ``notes`` list and an
  ``inputs_used`` list rather than inline literals, and (task 2.1) a
  ``non_selected`` tuple carrying an entry with no computed number and a
  ``flags`` tuple carrying all three quality verdicts -- covering the full
  redefined result vocabulary, not merely the selected value.
* :class:`DecliningCalculator` declares the broad ``Modality.OTHER`` modality
  (covering Walk, Hike, Rowing and Workout) but narrows ``supports`` to refuse
  exactly one sport inside it (``Sport.ROWING``), while its ``compute``
  unconditionally returns :class:`~fitdocs.load.types.Unsupported` regardless
  of sport as defence in depth -- modelling both an arbitrated calculator
  whose declared coverage the support question narrows sport-by-sport, and
  one that still declines the specific activity it is handed even when asked
  to compute it (Req 1.3, Req 1.14, Req 10.5).
* :class:`ScopedFieldCalculator` declares one :class:`~fitdocs.load.types.AthleteField`
  whose key is dotted under its own ``calculator_id`` (``"stub-scoped.<field>"``),
  exercising the profile store's methodology-scoped namespacing without a
  bundled calculator (Req 2.7).
* :class:`HintedCalculator` exposes ``athlete_field_hints`` -- the additive,
  off-protocol instance attribute the generic prompt flow reads via
  ``getattr`` -- so the per-field confirmation-hint seam has a subject with no
  methodology shipped (Req 3.6).

Each stub's matching fixture (``computing_calculator``, ``declining_calculator``,
``scoped_field_calculator``, ``hinted_calculator``) registers exactly that one
instance and unregisters exactly that id on teardown -- never clearing the rest
of the registry -- so a test can compose several stubs at once (e.g. two
supporters for an arbitration test) without leaking either afterward.
``isolated_registry`` is the stronger tool for tests that need a *provably
empty* registry regardless of what is registered on import: it snapshots the
module-global store, clears it, and restores the snapshot afterward.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping

import pytest

from fitdocs import Activity, DerivedMetrics, Modality, Sport
from fitdocs.load import registry
from fitdocs.load.settings import DEFAULT_LOAD_SETTINGS
from fitdocs.load.types import (
    AthleteField,
    Computed,
    InteractionSession,
    LoadCalculator,
    LoadContext,
    LoadOutcome,
    LoadResult,
    MissingInputs,
    NonSelectedValue,
    NotComputed,
    ProfileView,
    QualityFlag,
    Unsupported,
)

__all__ = [
    "COMPUTING_FIELD",
    "HINTED_FIELD",
    "SCOPED_FIELD",
    "ComputingCalculator",
    "DecliningCalculator",
    "HintedCalculator",
    "ScopedFieldCalculator",
    "stub_context",
]


def stub_context() -> LoadContext:
    """A minimal :class:`LoadContext` for tests driving a stub's ``compute``
    directly (no activity date, default settings) -- task 4.1 is what builds
    the real per-activity context from a document and the resolved ``[load]``
    table; this stub-only helper is not that.
    """
    return LoadContext(activity_date=None, settings=DEFAULT_LOAD_SETTINGS)


# --- computing stub (Req 1.1, 1.2, 13.6) ------------------------------------
COMPUTING_FIELD = AthleteField(
    key="level",
    label="Stub computing level",
    kind="int",
    minimum=1,
    maximum=10,
    help_text="A stub input exercising the Computed outcome only.",
)


class ComputingCalculator:
    """Stub calculator reaching :class:`Computed` for a supported activity.

    Declines a non-running activity, reports :class:`MissingInputs` when its
    one declared field is absent, and :class:`NotComputed` when the session
    gives no or a negative confirmation reply -- so it exercises the whole
    outcome union, not only the computing path, while remaining the "computes
    a result" stub the task calls for.
    """

    calculator_id = "stub-computing"
    display_name = "Stub Computing Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (COMPUTING_FIELD,)

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        if activity.modality not in self.supported_modalities:
            return Unsupported(
                reason=(
                    f"{self.display_name} supports running only, "
                    f"not {activity.sport.value}"
                )
            )
        level = profile.get_number(COMPUTING_FIELD.key)
        if level is None:
            return MissingInputs(fields=self.required_athlete_fields())
        confirmed = session.confirm("Confirm stub computed load?")
        if confirmed is None:
            return NotComputed(reason="non-interactive pass")
        if not confirmed:
            return NotComputed(reason="user declined confirmation")

        # Built from lists rather than inline literals so a later additive
        # result field is one more list plus one more keyword.
        notes: list[str] = ["stub computing note"]
        inputs_used: list[tuple[str, str]] = [
            (COMPUTING_FIELD.label, str(int(level))),
        ]
        # Covers the full result vocabulary (task 2.1): a non-selected entry
        # with no computed number (honest absence, never a fabricated 0), and
        # every quality verdict the vocabulary allows.
        non_selected: tuple[NonSelectedValue, ...] = (
            NonSelectedValue(
                key="stub-alt",
                label="Stub alternate channel",
                value=None,
                reason="stub: no alternate channel was computed",
            ),
        )
        flags: tuple[QualityFlag, ...] = (
            QualityFlag(
                key="stub-detected",
                label="Stub detected check",
                verdict="detected",
                detail="stub: condition observed",
            ),
            QualityFlag(
                key="stub-not-detected",
                label="Stub not-detected check",
                verdict="not-detected",
                detail="stub: condition not observed",
            ),
            QualityFlag(
                key="stub-not-assessed",
                label="Stub not-assessed check",
                verdict="not-assessed",
                detail="stub: condition not evaluated",
            ),
        )
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=level * 10.0,
                basis=f"stub computing basis (level {int(level)})",
                non_selected=non_selected,
                flags=flags,
                inputs_used=tuple(inputs_used),
                notes=tuple(notes),
            )
        )


# --- declining stub (Req 1.3, 1.14, 13.6) -----------------------------------
_DECLINED_SPORT = Sport.ROWING


class DecliningCalculator:
    """Stub calculator narrowing a broad modality declaration sport-by-sport,
    and still declining every activity handed to ``compute`` regardless.

    Declares the broad ``Modality.OTHER`` modality, which groups several
    distinct sports (Walk, Hike, Rowing, Workout) -- a *sport-granular*
    narrowing is the only shape that can be told apart from "declares no
    modality": a blanket ``False`` answer for every sport is indistinguishable
    from declining the whole modality outright, and cannot model "covers this
    modality except for one sport inside it" (design.md ~1183, ~1897;
    tasks.md 3.2 Observable, 6.1). So :meth:`supports` narrows out exactly one
    sport, ``Sport.ROWING``, and answers ``True`` for every other sport in
    ``Modality.OTHER`` -- this is a *narrowing* of the modality declaration,
    the only direction ``supports`` may ever move (Req 1.14).

    ``compute`` still unconditionally declines every activity it is handed,
    independent of sport, as defence in depth: Req 10.5's "arbitrated
    calculator answers yes to ``supports`` and still declines at ``compute``"
    path must stay reachable through this stub even after task 4.1's engine
    gate starts using ``supports`` to filter candidates before ``compute`` is
    ever called -- without this, a calculator that only ever refused sports
    ``supports`` already screens out could never demonstrate that path.
    """

    calculator_id = "stub-declining"
    display_name = "Stub Declining Calculator"
    supported_modalities = frozenset({Modality.OTHER})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def supports(self, activity: Activity) -> bool:
        return (
            activity.modality in self.supported_modalities
            and activity.sport is not _DECLINED_SPORT
        )

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Unsupported(
            reason=(
                f"{self.display_name} declines every sport; "
                f"this is a {activity.sport.value} activity"
            )
        )


# --- methodology-scoped-field stub (Req 2.7) --------------------------------
SCOPED_FIELD = AthleteField(
    key="stub-scoped.custom_threshold",
    label="Stub scoped threshold",
    kind="float",
    minimum=0.0,
    maximum=500.0,
    help_text=(
        "A methodology-scoped input namespaced under this calculator's own "
        "profile table, exercising Req 2.7's dotted-key scoping."
    ),
)


class ScopedFieldCalculator:
    """Stub calculator declaring one methodology-scoped :class:`AthleteField`.

    ``SCOPED_FIELD.key`` is dotted under this calculator's own
    ``calculator_id`` (``"stub-scoped.custom_threshold"``), mirroring how
    ``fitdocs.load.profile`` namespaces per-methodology fields so two
    calculators' fields of the same name never collide (Req 2.7). No shipped
    calculator declares a scoped field, so this stub is what exercises the
    seam.
    """

    calculator_id = "stub-scoped"
    display_name = "Stub Scoped-Field Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (SCOPED_FIELD,)

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        if activity.modality not in self.supported_modalities:
            return Unsupported(
                reason=(
                    f"{self.display_name} supports running only, "
                    f"not {activity.sport.value}"
                )
            )
        value = profile.get_number(SCOPED_FIELD.key)
        if value is None:
            return MissingInputs(fields=self.required_athlete_fields())
        confirmed = session.confirm("Confirm stub scoped-field load?")
        if confirmed is None:
            return NotComputed(reason="non-interactive pass")
        if not confirmed:
            return NotComputed(reason="user declined confirmation")
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=value,
                basis="stub scoped-field basis",
                non_selected=(),
                flags=(),
                inputs_used=((SCOPED_FIELD.label, f"{value:g}"),),
                notes=(),
            )
        )


# --- confirmation-hint stub (Req 3.6) ---------------------------------------
HINTED_FIELD = AthleteField(
    key="stub-hinted.baseline",
    label="Stub hinted baseline",
    kind="float",
    minimum=0.0,
    maximum=100.0,
    help_text="A stub input whose confirmation echoes a derived hint (Req 3.6).",
)


def _baseline_hint(value: float) -> str:
    """A stub confirm-hint echoing the entered value (not a real derivation)."""
    return f"Baseline {value:g} noted for confirmation echo (stub hint)."


class HintedCalculator:
    """Stub calculator declaring a per-field confirmation hint (Req 3.6).

    ``athlete_field_hints`` is not on the :class:`LoadCalculator` protocol --
    it is the additive instance attribute the generic prompt flow reads via
    ``getattr`` (``fitdocs.load.engine``), keeping the engine methodology-
    agnostic. No shipped calculator declares a hint, so this stub is what
    exercises the seam.
    """

    calculator_id = "stub-hinted"
    display_name = "Stub Hinted Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def __init__(self) -> None:
        self.athlete_field_hints: Mapping[str, Callable[[float], str]] = {
            HINTED_FIELD.key: _baseline_hint,
        }

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (HINTED_FIELD,)

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        if activity.modality not in self.supported_modalities:
            return Unsupported(
                reason=(
                    f"{self.display_name} supports running only, "
                    f"not {activity.sport.value}"
                )
            )
        value = profile.get_number(HINTED_FIELD.key)
        if value is None:
            return MissingInputs(fields=self.required_athlete_fields())
        confirmed = session.confirm("Confirm stub hinted load?")
        if confirmed is None:
            return NotComputed(reason="non-interactive pass")
        if not confirmed:
            return NotComputed(reason="user declined confirmation")
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=value,
                basis="stub hinted basis",
                non_selected=(),
                flags=(),
                inputs_used=((HINTED_FIELD.label, f"{value:g}"),),
                notes=(),
            )
        )


# Static structural-conformance checks -- a shape mismatch fails mypy --strict.
_COMPUTING_CALC: LoadCalculator = ComputingCalculator()
_DECLINING_CALC: LoadCalculator = DecliningCalculator()
_SCOPED_CALC: LoadCalculator = ScopedFieldCalculator()
_HINTED_CALC: LoadCalculator = HintedCalculator()


# --- fixtures -----------------------------------------------------------
@pytest.fixture
def isolated_registry() -> Iterator[None]:
    """Snapshot, clear, and restore the module-global registry.

    Guarantees a test's registry is provably empty at the start (and can be
    asserted empty again at the end) regardless of what is registered on
    import -- e.g. a withdrawn methodology's calculator that once
    auto-registered on import. Accessing the private
    ``_REGISTRY`` store is acceptable here: it is the only way to fully
    isolate module-global state across tests (mirrors ``test_registry.py``'s
    fixture of the same name).
    """
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)


# NOTE (task 1.2 outcome): ``isolated_registry`` is now defined exactly once,
# here, and yields ``None``. ``test_registry.py`` and
# ``test_registry_validation.py`` no longer define their own copies -- they
# import ``fitdocs.load.registry`` directly rather than receiving it from a
# fixture, so there is no divergent-yield-contract shadowing left to
# reconcile.


@pytest.fixture
def computing_calculator() -> Iterator[ComputingCalculator]:
    """Register a fresh :class:`ComputingCalculator`; unregister it after."""
    calc = ComputingCalculator()
    registry.register(calc)
    try:
        yield calc
    finally:
        registry.unregister(calc.calculator_id)


@pytest.fixture
def declining_calculator() -> Iterator[DecliningCalculator]:
    """Register a fresh :class:`DecliningCalculator`; unregister it after."""
    calc = DecliningCalculator()
    registry.register(calc)
    try:
        yield calc
    finally:
        registry.unregister(calc.calculator_id)


@pytest.fixture
def scoped_field_calculator() -> Iterator[ScopedFieldCalculator]:
    """Register a fresh :class:`ScopedFieldCalculator`; unregister it after."""
    calc = ScopedFieldCalculator()
    registry.register(calc)
    try:
        yield calc
    finally:
        registry.unregister(calc.calculator_id)


@pytest.fixture
def hinted_calculator() -> Iterator[HintedCalculator]:
    """Register a fresh :class:`HintedCalculator`; unregister it after."""
    calc = HintedCalculator()
    registry.register(calc)
    try:
        yield calc
    finally:
        registry.unregister(calc.calculator_id)
