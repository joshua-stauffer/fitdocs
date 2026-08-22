"""Tests for the calculator registry (task 1.3, Req 1.5, 1.6).

The registry is the id-addressable community-contribution seam: it preserves
registration order, rejects duplicate ids, raises a typed error on unknown
lookup, and filters to the calculators that declare support for a given
modality. These tests pin that mechanism with small stub calculators rather
than any real methodology.

The registry is module-global mutable state, and importing anything under
``fitdocs.load`` may register built-ins (Req 1.5, 13.2). So every test runs
inside :func:`~tests.load.conftest.isolated_registry`, which snapshots the
registry's internal store, clears it for the test, and restores it afterward
-- the tests fully control what is registered regardless of built-ins.
"""

from __future__ import annotations

import pytest

from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs.load import registry as reg
from fitdocs.load.types import (
    AthleteField,
    InteractionSession,
    LoadCalculator,
    LoadContext,
    LoadOutcome,
    ProfileView,
    Unsupported,
)


# --- stub calculator --------------------------------------------------------
class StubCalculator:
    """A minimal calculator that structurally satisfies :class:`LoadCalculator`.

    Only the registry-relevant attributes (``calculator_id``,
    ``supported_modalities``) carry per-instance meaning; ``compute`` exists to
    satisfy the protocol and is never exercised by these mechanism tests.
    """

    def __init__(
        self,
        calculator_id: str,
        supported_modalities: frozenset[Modality],
    ) -> None:
        self.calculator_id = calculator_id
        self.display_name = f"Stub {calculator_id}"
        self.supported_modalities = supported_modalities

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Unsupported(reason="stub never computes")


# Static structural-conformance check: mypy checks only `files = ["src"]"
# (pyproject.toml), so this annotation is not itself statically verified --
# it is kept in sync with the real 5-parameter `compute` shape so it does not
# make a conformance claim nothing checks (Req 1.14 remediation, finding 5).
_CALC: LoadCalculator = StubCalculator("static", frozenset({Modality.RUN}))


# --- registration order -----------------------------------------------------
def test_registration_order_preserved(isolated_registry: None) -> None:
    a = StubCalculator("a", frozenset({Modality.RUN}))
    b = StubCalculator("b", frozenset({Modality.BIKE}))
    c = StubCalculator("c", frozenset({Modality.SWIM}))
    reg.register(a)
    reg.register(b)
    reg.register(c)

    assert reg.available() == (a, b, c)


def test_available_returns_a_tuple(isolated_registry: None) -> None:
    reg.register(StubCalculator("only", frozenset({Modality.RUN})))
    assert isinstance(reg.available(), tuple)


# --- duplicate rejection ----------------------------------------------------
def test_duplicate_id_rejected(isolated_registry: None) -> None:
    reg.register(StubCalculator("dup", frozenset({Modality.RUN})))

    with pytest.raises(ValueError) as exc_info:
        reg.register(StubCalculator("dup", frozenset({Modality.BIKE})))

    # The message must name the offending id so the user can locate it.
    assert "dup" in str(exc_info.value)
    # The first registration must survive the rejected duplicate untouched.
    assert reg.get("dup").supported_modalities == frozenset({Modality.RUN})
    assert len(reg.available()) == 1


# --- unknown lookup ---------------------------------------------------------
def test_get_returns_registered_instance(isolated_registry: None) -> None:
    calc = StubCalculator("known", frozenset({Modality.RUN}))
    reg.register(calc)
    assert reg.get("known") is calc


def test_unknown_lookup_raises_typed_error(isolated_registry: None) -> None:
    from fitdocs.load.registry import UnknownCalculatorError

    reg.register(StubCalculator("first", frozenset({Modality.RUN})))
    reg.register(StubCalculator("other", frozenset({Modality.BIKE})))

    with pytest.raises(UnknownCalculatorError) as exc_info:
        reg.get("nope")

    message = str(exc_info.value)
    # The message must name the unknown id and list the registered ids so the
    # user can see what they could have asked for.
    assert "nope" in message
    assert "first" in message
    assert "other" in message


# --- sport filtering --------------------------------------------------------
def test_for_modality_filters_and_preserves_order(
    isolated_registry: None,
) -> None:
    run_a = StubCalculator("run_a", frozenset({Modality.RUN}))
    bike = StubCalculator("bike", frozenset({Modality.BIKE}))
    run_b = StubCalculator("run_b", frozenset({Modality.RUN, Modality.OTHER}))
    reg.register(run_a)
    reg.register(bike)
    reg.register(run_b)

    # Only run-supporting calculators, in registration order (run_a before run_b).
    assert reg.for_modality(Modality.RUN) == (run_a, run_b)
    assert reg.for_modality(Modality.BIKE) == (bike,)


def test_for_modality_unsupported_returns_empty(isolated_registry: None) -> None:
    reg.register(StubCalculator("run_only", frozenset({Modality.RUN})))

    # No calculator supports STRENGTH -> empty tuple, not an error.
    result = reg.for_modality(Modality.STRENGTH)
    assert result == ()
    assert isinstance(result, tuple)


def test_for_modality_returns_a_tuple(isolated_registry: None) -> None:
    reg.register(StubCalculator("r", frozenset({Modality.RUN})))
    assert isinstance(reg.for_modality(Modality.RUN), tuple)
