"""The calculator registry: the id-addressable community-contribution seam.

Every load methodology plugs in here. The registry keeps calculators in
registration order, addresses them by their unique ``calculator_id``, and
filters to the calculators that declare support for a given modality --
a cheap prefilter that :mod:`fitdocs.load.arbitrate` narrows further by the
contract's support question before selecting one (Req 1.6, 10.1-10.4).
**Registration order is never used to pick a calculator**: which one runs is
a policy decision made by arbitration, not an accident of registration or
discovery order, and ``--calculator`` can always select exactly one by id
(Req 1.5, 1.6).

The store is a module-level ``dict`` keyed by ``calculator_id``; a ``dict``
preserves insertion order, which *is* registration order. This module itself
registers no calculator of its own -- it is pure mechanism, never a
methodology -- but importing :mod:`fitdocs.load` registers fitdocs' one
built-in, ``threshold`` (``threshold-load``, Req 1.1-1.3), through this same
:func:`register` function before any plugin author or downstream spec adds
another. This module does no I/O. Its only non-stdlib imports are the
``fitdocs`` public :class:`~fitdocs.Modality` type and the
:class:`~fitdocs.load.types.LoadCalculator` contract it stores.

Every registration -- built-in, packaged, or local -- passes through one
validation gate, :func:`validate_calculator`, before it enters the registry
(plugin-api, Req 3.1, 3.3, 5.6). The validator is pure introspection: it never
calls a calculator's declared methods, so validating (and therefore
registering) a calculator has no side effects.
"""

from __future__ import annotations

from collections.abc import Iterable

from fitdocs import Modality
from fitdocs.load.types import LoadCalculator

__all__ = [
    "DuplicateCalculatorIdError",
    "InvalidCalculatorError",
    "UnknownCalculatorError",
    "available",
    "for_modality",
    "get",
    "register",
    "unregister",
    "validate_calculator",
]

_REGISTRY: dict[str, LoadCalculator] = {}
"""Module-global store keyed by ``calculator_id`` in registration order."""


class UnknownCalculatorError(Exception):
    """Raised when a calculator id is looked up that is not registered.

    The message names the requested id and lists the registered ids so the
    user can see what they could have asked for.
    """


class InvalidCalculatorError(ValueError):
    """Raised when a calculator offered for registration fails the contract.

    Subclasses :class:`ValueError` so existing callers and tests that catch
    ``ValueError`` for a rejected registration keep working unchanged.
    """


class DuplicateCalculatorIdError(ValueError):
    """Raised when a calculator claims an id that is already registered.

    The incumbent registration is left untouched. Subclasses
    :class:`ValueError` so existing callers and tests that catch
    ``ValueError`` for a rejected registration keep working unchanged.

    Carries the contested :attr:`calculator_id` so a caller that catches this
    (e.g. ``plugins._load_local_file``, where the offending id is not otherwise
    in hand) can name the incumbent's origin without parsing the message
    (Req 3.3).
    """

    def __init__(self, message: str, *, calculator_id: str) -> None:
        super().__init__(message)
        self.calculator_id = calculator_id


def validate_calculator(obj: object) -> str | None:
    """Return ``None`` when ``obj`` satisfies the calculator contract, else a
    human-readable reason naming the first violated member.

    Checked in order: ``calculator_id`` is a non-empty ``str``;
    ``display_name`` is a non-empty ``str``; ``supported_modalities`` is a
    non-empty iterable whose every element is a :class:`~fitdocs.Modality`;
    ``required_athlete_fields`` is callable; ``compute`` is callable.

    Never calls ``required_athlete_fields`` or ``compute`` -- registration
    stays side-effect free (plugin-api, Req 3.1, 5.6). Accepts any object
    without raising; a malformed shape (including a missing attribute)
    produces a reason rather than an exception.
    """
    calculator_id = getattr(obj, "calculator_id", None)
    if not isinstance(calculator_id, str) or not calculator_id:
        return "calculator_id must be a non-empty str"

    display_name = getattr(obj, "display_name", None)
    if not isinstance(display_name, str) or not display_name:
        return "display_name must be a non-empty str"

    supported_modalities = getattr(obj, "supported_modalities", None)
    if supported_modalities is None or isinstance(supported_modalities, (str, bytes)):
        return "supported_modalities must be a non-empty iterable of Modality"
    if not isinstance(supported_modalities, Iterable):
        return "supported_modalities must be a non-empty iterable of Modality"
    modalities = list(supported_modalities)
    if not modalities or not all(isinstance(m, Modality) for m in modalities):
        return "supported_modalities must be a non-empty iterable of Modality"

    if not callable(getattr(obj, "required_athlete_fields", None)):
        return "required_athlete_fields must be callable"

    if not callable(getattr(obj, "compute", None)):
        return "compute must be callable"

    return None


def register(calculator: LoadCalculator) -> None:
    """Register ``calculator`` under its ``calculator_id`` in registration order.

    Validates ``calculator`` against the contract first (Req 3.1); a rejected
    calculator never enters the registry and :class:`InvalidCalculatorError`
    is raised, naming the violated member.

    Raises :class:`DuplicateCalculatorIdError` if a calculator with the same
    id is already registered (the message names the id); the existing
    registration is left untouched (Req 3.3). Both error types subclass
    :class:`ValueError`.
    """
    reason = validate_calculator(calculator)
    if reason is not None:
        raise InvalidCalculatorError(
            f"calculator {calculator!r} does not satisfy the contract: {reason}"
        )

    calculator_id = calculator.calculator_id
    if calculator_id in _REGISTRY:
        raise DuplicateCalculatorIdError(
            f"a calculator is already registered under id {calculator_id!r}",
            calculator_id=calculator_id,
        )
    _REGISTRY[calculator_id] = calculator


def unregister(calculator_id: str) -> None:
    """Remove ``calculator_id`` from the registry when present; a no-op
    otherwise.

    Registry-internal teardown for discovery state (used by
    ``plugins.reset()``); deliberately not part of the plugin-author public
    surface.
    """
    _REGISTRY.pop(calculator_id, None)


def get(calculator_id: str) -> LoadCalculator:
    """Return the calculator registered under ``calculator_id``.

    Raises :class:`UnknownCalculatorError` when no calculator is registered
    under that id; the message names the id and lists the registered ids.
    """
    try:
        return _REGISTRY[calculator_id]
    except KeyError:
        registered = ", ".join(_REGISTRY) or "none"
        raise UnknownCalculatorError(
            f"unknown calculator id {calculator_id!r}; registered: {registered}"
        ) from None


def available() -> tuple[LoadCalculator, ...]:
    """Return all registered calculators in registration order."""
    return tuple(_REGISTRY.values())


def for_modality(modality: Modality) -> tuple[LoadCalculator, ...]:
    """Return, in registration order, the calculators that support ``modality``.

    A calculator supports ``modality`` when ``modality`` is in its
    ``supported_modalities``. When none do, the result is an empty tuple, not
    an error (Req 1.6).
    """
    return tuple(
        calculator
        for calculator in _REGISTRY.values()
        if modality in calculator.supported_modalities
    )
