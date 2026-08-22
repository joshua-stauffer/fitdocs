"""Tests for the registry's contract-validation gate (task 1.2, Req 3.1, 3.3, 5.6).

``validate_calculator`` is the one gate every calculator -- built-in, packaged,
or local -- passes before ``register()`` inserts it. It is pure introspection:
it never calls ``required_athlete_fields`` or ``compute``, so validating (and
therefore registering) a calculator is side-effect free. ``register()`` raises
a typed error naming the violation or the contested id and never replaces an
incumbent registration; ``unregister()`` is a no-op-safe teardown hook used by
plugin discovery (not part of the plugin-author surface, so it is exercised
here directly rather than via ``fitdocs.load``).

The registry is module-global mutable state and importing ``fitdocs.load`` may
register built-ins on import, so every test that registers runs inside
``isolated_registry`` (:func:`tests.load.conftest.isolated_registry`,
mirroring ``tests/load/test_registry.py``) to guarantee no leakage into the
rest of the suite.
"""

from __future__ import annotations

from typing import Any

import pytest

from fitdocs import Modality
from fitdocs.load import DuplicateCalculatorIdError, InvalidCalculatorError
from fitdocs.load import registry as reg
from fitdocs.load.registry import (
    DuplicateCalculatorIdError as RegistryDuplicateCalculatorIdError,
)
from fitdocs.load.registry import (
    InvalidCalculatorError as RegistryInvalidCalculatorError,
)
from fitdocs.load.registry import validate_calculator
from tests.load.conftest import ComputingCalculator


class _Recorder:
    """A calculator whose declared methods record whether they were called.

    Used to prove ``validate_calculator`` never invokes them.
    """

    calculator_id = "recorder"
    display_name = "Recorder"
    supported_modalities = frozenset({Modality.RUN})

    def __init__(self) -> None:
        self.called = False

    def required_athlete_fields(self) -> tuple[object, ...]:
        self.called = True
        raise AssertionError("required_athlete_fields must not be called")

    def compute(self, *args: object, **kwargs: object) -> object:
        self.called = True
        raise AssertionError("compute must not be called")


class _Base:
    """A structurally valid stub, overridden per-field by malformed variants."""

    calculator_id = "base"
    display_name = "Base"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[object, ...]:
        return ()

    def compute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("compute must not be invoked by validation")


def _make(**overrides: object) -> Any:
    # Deliberately Any, not LoadCalculator: many callers intentionally pass a
    # structurally invalid override (e.g. a non-str calculator_id) to probe
    # validate_calculator()'s rejections, so a precise return type would be a
    # lie for those cases; Any lets both validate_calculator(obj: object) and
    # register(calc: LoadCalculator) accept the same helper without masking
    # any other real type error in this module.
    obj = _Base()
    for key, value in overrides.items():
        setattr(obj, key, value)
    return obj


# --- validate_calculator: acceptance -----------------------------------------
def test_validate_calculator_accepts_a_full_stub_calculator() -> None:
    # Proves validate_calculator accepts a real, fully-shaped implementation of
    # the published contract -- not only this module's minimal _Base stub.
    assert validate_calculator(ComputingCalculator()) is None


def test_validate_calculator_accepts_valid_stub() -> None:
    assert validate_calculator(_Base()) is None


def test_validate_calculator_never_calls_declared_methods() -> None:
    recorder = _Recorder()
    assert validate_calculator(recorder) is None
    assert recorder.called is False


def test_validate_calculator_accepts_arbitrary_object_without_raising() -> None:
    assert validate_calculator(object()) is not None


# --- validate_calculator: rejections ------------------------------------------
def test_validate_calculator_rejects_missing_calculator_id() -> None:
    class _NoId:
        display_name = "No Id"
        supported_modalities = frozenset({Modality.RUN})

        def required_athlete_fields(self) -> tuple[object, ...]:
            return ()

        def compute(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("compute must not be invoked by validation")

    reason = validate_calculator(_NoId())
    assert reason is not None
    assert "calculator_id" in reason


def test_validate_calculator_rejects_blank_calculator_id() -> None:
    reason = validate_calculator(_make(calculator_id=""))
    assert reason is not None
    assert "calculator_id" in reason


def test_validate_calculator_rejects_non_str_calculator_id() -> None:
    reason = validate_calculator(_make(calculator_id=123))
    assert reason is not None
    assert "calculator_id" in reason


def test_validate_calculator_rejects_missing_display_name() -> None:
    class _NoName:
        calculator_id = "no-name"
        supported_modalities = frozenset({Modality.RUN})

        def required_athlete_fields(self) -> tuple[object, ...]:
            return ()

        def compute(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("compute must not be invoked by validation")

    reason = validate_calculator(_NoName())
    assert reason is not None
    assert "display_name" in reason


def test_validate_calculator_rejects_blank_display_name() -> None:
    reason = validate_calculator(_make(display_name=""))
    assert reason is not None
    assert "display_name" in reason


def test_validate_calculator_rejects_non_str_display_name() -> None:
    reason = validate_calculator(_make(display_name=123))
    assert reason is not None
    assert "display_name" in reason


def test_validate_calculator_rejects_empty_supported_modalities() -> None:
    reason = validate_calculator(_make(supported_modalities=frozenset()))
    assert reason is not None
    assert "supported_modalities" in reason


def test_validate_calculator_rejects_non_modality_supported_modalities() -> None:
    reason = validate_calculator(_make(supported_modalities=["run", "bike"]))
    assert reason is not None
    assert "supported_modalities" in reason


def test_validate_calculator_rejects_non_callable_required_athlete_fields() -> None:
    reason = validate_calculator(_make(required_athlete_fields="not callable"))
    assert reason is not None
    assert "required_athlete_fields" in reason


def test_validate_calculator_rejects_non_callable_compute() -> None:
    reason = validate_calculator(_make(compute="not callable"))
    assert reason is not None
    assert "compute" in reason


# --- register(): validation gate ---------------------------------------------
def test_register_rejects_malformed_calculator(isolated_registry: None) -> None:
    with pytest.raises(RegistryInvalidCalculatorError):
        reg.register(_make(calculator_id=""))

    assert "" not in [calc.calculator_id for calc in reg.available()]
    assert reg.available() == ()


def test_register_raises_invalid_calculator_error_is_value_error(
    isolated_registry: None,
) -> None:
    with pytest.raises(ValueError):
        reg.register(_make(display_name=""))


# --- register(): duplicate-id gate -------------------------------------------
def test_register_duplicate_id_raises_typed_error_and_keeps_incumbent(
    isolated_registry: None,
) -> None:
    first = _make(calculator_id="dup")
    reg.register(first)

    second = _make(calculator_id="dup", display_name="Impostor")
    with pytest.raises(RegistryDuplicateCalculatorIdError) as exc_info:
        reg.register(second)

    assert "dup" in str(exc_info.value)
    assert reg.get("dup") is first
    assert len(reg.available()) == 1


def test_register_duplicate_calculator_id_error_is_value_error(
    isolated_registry: None,
) -> None:
    reg.register(_make(calculator_id="dup2"))
    with pytest.raises(ValueError):
        reg.register(_make(calculator_id="dup2"))


# --- unregister() -------------------------------------------------------------
def test_unregister_removes_present_id(isolated_registry: None) -> None:
    reg.register(_make(calculator_id="gone"))
    reg.unregister("gone")
    assert reg.available() == ()


def test_unregister_absent_id_is_noop(isolated_registry: None) -> None:
    reg.register(_make(calculator_id="stays"))
    reg.unregister("does-not-exist")
    assert len(reg.available()) == 1
    assert reg.get("stays") is not None


# --- public surface -----------------------------------------------------------
def test_error_types_importable_from_load_public_surface() -> None:
    assert InvalidCalculatorError is RegistryInvalidCalculatorError
    assert DuplicateCalculatorIdError is RegistryDuplicateCalculatorIdError
    assert issubclass(InvalidCalculatorError, ValueError)
    assert issubclass(DuplicateCalculatorIdError, ValueError)
