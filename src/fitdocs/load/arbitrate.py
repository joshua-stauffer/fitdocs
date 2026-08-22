"""Arbitration: resolve exactly one calculator for an activity, or state why
not (Amendment 1; design re-validation 2026-07-25; Req 1.6, 8.4, 10.1-10.4,
13.5).

Precedence is fixed and total: an explicitly requested identifier beats the
configured default, which beats the sole calculator supporting *this
activity*, which -- with no default configured -- resolves to either no
calculator at all or an ambiguity naming the sorted candidate identifiers.
Registration or discovery order is never consulted: several supporters with
no configured default is an ambiguity, not "the first one found" (Req 10.1,
10.2).

A forced id or a configured default is returned as :class:`Selected`
**regardless of the activity's sport** -- substituting a different calculator
for one that declines is exactly what Req 10.5 forbids, so for that path the
sport question is settled downstream, in the engine's own (unconditional)
support check, not here (Req 10.3).

**The no-default branch narrows its candidates by the contract's support
question**, after the registry's cheap modality prefilter
(:func:`~fitdocs.load.registry.for_modality`). Both requirements governing
this branch (1.6, 10.2) are written in terms of the activity's *sport*, and
the contract answers exactly that question through
:func:`~fitdocs.load.types.supports_activity` (Req 1.14). Without this
narrowing, two calculators declaring the same catch-all modality -- the shape
a real calculator needs to reach a few sports inside a broad modality -- would
resolve a document in a third, uncovered sport to a misleading
:class:`Ambiguous`, directing the user toward a default that cannot help
because *neither* candidate covers that sport, where Reqs 7.7 and 10.5 demand
the honest unsupported state instead. Narrowing makes all three sub-cases
correct: several declare and several support the activity -> ``Ambiguous``;
several declare and exactly one supports it -> ``Selected``; several declare
and none supports it -> ``NoCalculator``.

This module is pure: no filesystem, no document knowledge, and no
*methodology execution* -- it asks ``supports_activity``, which the contract
guarantees is prompt-free, athlete-data-free and side-effect-free (Req 1.14),
but it never calls ``compute``. It imports only :mod:`fitdocs.load.types` and
:mod:`fitdocs.load.registry`, performs no I/O, and is fully deterministic:
identical registry contents, identical configuration and an identical
activity always yield the identical outcome.

**The engine's own support check (task 4.1) stays unconditional.** On the
no-default path, ``supports_activity`` is therefore asked twice -- once here,
to select; once in the engine, to enforce. That is deliberate: selection
(this module, Req 1.6) and enforcement (the engine, Reqs 3.1, 7.7, 10.5) are
different requirements, and the engine must not have to know which precedence
branch produced its :class:`Selected`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fitdocs import Activity, Modality
from fitdocs.load import registry
from fitdocs.load.registry import UnknownCalculatorError
from fitdocs.load.types import LoadCalculator, supports_activity

__all__ = [
    "Ambiguous",
    "ArbitrationOutcome",
    "NoCalculator",
    "Selected",
    "arbitrate",
    "validate_configured",
]


@dataclass(frozen=True)
class Selected:
    """Exactly one calculator was resolved for this activity."""

    calculator: LoadCalculator
    """The calculator to use. Not yet checked against the activity's sport
    when this came from the forced or configured path -- that check is the
    engine's, not arbitration's (Req 10.3, 10.5)."""


@dataclass(frozen=True)
class Ambiguous:
    """No default is configured and more than one registered calculator
    supports this activity (Req 10.2)."""

    candidates: tuple[str, ...]
    """The registered ids that support *this activity*, sorted for
    deterministic messaging. Always length >= 2."""


@dataclass(frozen=True)
class NoCalculator:
    """No registered calculator both declares this activity's modality and
    supports this activity (Req 1.6)."""

    modality: Modality
    """Message context only -- the honest unsupported state names the
    activity's *sport*; the caller holds the activity and renders it."""


ArbitrationOutcome = Selected | Ambiguous | NoCalculator
"""The closed set of arbitration outcomes."""


def arbitrate(
    activity: Activity,
    *,
    forced_id: str | None,
    default_calculator: str | None,
) -> ArbitrationOutcome:
    """Resolve exactly one calculator for ``activity``, or state why not.

    Precedence: ``forced_id`` (Req 8.4, 10.3) beats ``default_calculator``
    (Req 10.1) beats the sole calculator, among those declaring the
    activity's modality, that answers :func:`~fitdocs.load.types.
    supports_activity` for this activity (Req 1.6, 10.2). Registration order
    is never consulted.

    A ``forced_id`` or ``default_calculator`` is returned as
    :class:`Selected` unconditionally -- **not** narrowed by the activity's
    sport, per Req 10.5 (see module docstring). Only the no-default branch
    narrows.

    **Precondition**: :func:`validate_configured` has already been called
    for this pass with the same ``forced_id``/``default_calculator``, so the
    id actually in play is known to be registered and this function never
    raises.
    """
    if forced_id is not None:
        return Selected(calculator=registry.get(forced_id))
    if default_calculator is not None:
        return Selected(calculator=registry.get(default_calculator))

    candidates = sorted(
        (
            calculator
            for calculator in registry.for_modality(activity.modality)
            if supports_activity(calculator, activity)
        ),
        key=lambda calculator: calculator.calculator_id,
    )
    if not candidates:
        return NoCalculator(modality=activity.modality)
    if len(candidates) == 1:
        return Selected(calculator=candidates[0])
    return Ambiguous(candidates=tuple(c.calculator_id for c in candidates))


def validate_configured(
    forced_id: str | None,
    default_calculator: str | None,
    *,
    settings_file: Path,
) -> None:
    """Validate only the identifier actually in play, up front (Req 10.4).

    ``forced_id`` takes precedence: when supplied, it alone is validated and
    ``default_calculator`` is never even inspected -- an explicit request
    makes a stale configured default irrelevant rather than fatal (Req
    10.3). Otherwise ``default_calculator`` is validated when configured.
    When neither is supplied, this is a no-op: the no-default arbitration
    branch validates nothing up front because it has no single id to check.

    Raises :class:`~fitdocs.load.registry.UnknownCalculatorError` naming the
    offending value, where it came from (the ``--calculator`` flag, or the
    ``[load] default_calculator`` key in ``settings_file``), and the
    registered identifiers -- with no fallback attempted.
    """
    if forced_id is not None:
        _validate_registered(forced_id, source="the --calculator flag")
        return
    if default_calculator is not None:
        _validate_registered(
            default_calculator,
            source=f"the [load] default_calculator key in {settings_file}",
        )


def _validate_registered(calculator_id: str, *, source: str) -> None:
    registered_ids = tuple(c.calculator_id for c in registry.available())
    if calculator_id in registered_ids:
        return
    registered = ", ".join(registered_ids) or "none"
    raise UnknownCalculatorError(
        f"unknown calculator id {calculator_id!r} configured via {source}; "
        f"registered: {registered}"
    )
