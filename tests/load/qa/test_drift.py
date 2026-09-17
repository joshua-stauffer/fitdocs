"""Tests for `fitdocs.load.qa.drift.evaluate` (design: AerobicDriftCheck,
task 2.4).

Covers Requirements 1.4, 1.5, 1.8, 1.10, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and design.md's
"AerobicDriftCheck" component section.

**Own test module** (Test File Ownership / "Shared test fixture" note in
tasks.md): every constructed :class:`DerivedMetrics` this task needs is
built here, not added to ``tests/load/qa/conftest.py``, which task 2.1 owns
and tasks 2.3/2.4/2.5 must not touch to keep their ``(P)`` markers safe.
"""

from __future__ import annotations

from fitdocs.load.qa.drift import DriftOutcome, evaluate
from fitdocs.load.qa.types import DEFAULT_AEROBIC_DRIFT_MAX_PCT, FlagSettings
from fitdocs.metrics.types import DerivedMetrics


def test_decoupling_none_is_not_assessed_naming_unavailability_and_scope() -> None:
    """Req 4.4: an absent decoupling percentage reaches NOT_ASSESSED, and the
    reason states both that the metric was unavailable for this activity and
    that it is defined for running and cycling only -- both parts belong in
    the text, not just "unavailable"."""
    metrics = DerivedMetrics(decoupling_pct=None, efficiency_factor=None)
    reading = evaluate(metrics, settings=FlagSettings())

    assert reading.outcome is DriftOutcome.NOT_ASSESSED
    assert reading.decoupling_pct is None
    assert reading.not_assessed_reason is not None
    assert "unavailable" in reading.not_assessed_reason
    assert "running and cycling" in reading.not_assessed_reason
    assert reading.reference_pct == DEFAULT_AEROBIC_DRIFT_MAX_PCT


def test_decoupling_above_reference_is_drifted() -> None:
    """Req 4.2: strictly above the configured reference reaches DRIFTED,
    carrying both the observed decoupling percentage and the reference."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=5.1, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.DRIFTED
    assert reading.decoupling_pct == 5.1
    assert reading.reference_pct == 5.0
    assert reading.not_assessed_reason is None


def test_decoupling_exactly_at_reference_is_coupled_not_drifted() -> None:
    """Boundary-exactness: exactly equal to the configured reference is
    COUPLED, not DRIFTED -- the design says "exceeds", strict inequality."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=5.0, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.COUPLED
    assert reading.decoupling_pct == 5.0
    assert reading.reference_pct == 5.0


def test_decoupling_below_reference_is_coupled() -> None:
    """Req 4.2: strictly below the configured reference reaches COUPLED,
    carrying both the observed decoupling percentage and the reference."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=2.5, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.COUPLED
    assert reading.decoupling_pct == 2.5
    assert reading.reference_pct == 5.0


def test_settings_reference_is_actually_read_not_hardcoded_to_default() -> None:
    """The "settings value equals module default" trap: construct a
    NON-default `aerobic_drift_max_pct` and a decoupling percentage that
    verdicts differently at the configured value than at the shipped
    default (5.0) would. 7.0 is COUPLED at a configured reference of 10.0,
    but would be DRIFTED at the shipped default -- so this only passes if
    `settings.aerobic_drift_max_pct` is genuinely read, not hardcoded."""
    assert DEFAULT_AEROBIC_DRIFT_MAX_PCT == 5.0
    settings = FlagSettings(aerobic_drift_max_pct=10.0)
    metrics = DerivedMetrics(decoupling_pct=7.0, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.COUPLED
    assert reading.reference_pct == 10.0


def test_decoupling_zero_is_coupled_not_not_assessed() -> None:
    """Zero-vs-absent trap: `decoupling_pct=0.0` is a real, meaningful
    "perfectly coupled" reading, not an absent one -- a truthiness check
    (`if not metrics.decoupling_pct`) would misreport it as NOT_ASSESSED.
    Only an `is None` check distinguishes the two (Req 4.2, 4.4)."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=0.0, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.COUPLED
    assert reading.decoupling_pct == 0.0
    assert reading.not_assessed_reason is None


def test_efficiency_factor_zero_is_carried_not_coerced_to_none() -> None:
    """Zero-vs-absent trap: `efficiency_factor=0.0` is a real, representable
    value per `DerivedMetrics`' `float | None` typing -- an `... or None`
    passthrough would silently coerce it away. Only a direct passthrough
    preserves it (Req 1.8, 4.5)."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=3.0, efficiency_factor=0.0)
    reading = evaluate(metrics, settings=settings)

    assert reading.efficiency_factor == 0.0
    assert reading.efficiency_factor is not None


def test_not_assessed_reference_pct_is_actually_read_not_hardcoded() -> None:
    """The "settings value equals module default" trap, on the NOT_ASSESSED
    return path specifically: both other not-assessed tests use
    `FlagSettings()`, whose `aerobic_drift_max_pct` happens to equal the
    module default (5.0), so a hardcode of
    `DEFAULT_AEROBIC_DRIFT_MAX_PCT` only on this return path would go
    undetected there. A non-default setting closes that gap."""
    settings = FlagSettings(aerobic_drift_max_pct=12.5)
    metrics = DerivedMetrics(decoupling_pct=None, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.NOT_ASSESSED
    assert reading.reference_pct == 12.5


def test_efficiency_factor_carried_when_decoupling_absent() -> None:
    """Req 1.8, 4.5: EF is present but decoupling_pct is None -- the reading
    reaches NOT_ASSESSED (decoupling drives the outcome) while still
    carrying the EF value, not dropping it because the primary metric was
    absent."""
    metrics = DerivedMetrics(decoupling_pct=None, efficiency_factor=1.62)
    reading = evaluate(metrics, settings=FlagSettings())

    assert reading.outcome is DriftOutcome.NOT_ASSESSED
    assert reading.efficiency_factor == 1.62
    assert reading.not_assessed_reason is not None


def test_efficiency_factor_none_when_absent_and_decoupling_present() -> None:
    """Req 1.8, 4.5: decoupling_pct is present (reaches a real verdict) but
    efficiency_factor is None on the input -- the reading's efficiency_factor
    field is None, never fabricated as 0 or some other stand-in."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=6.0, efficiency_factor=None)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.DRIFTED
    assert reading.efficiency_factor is None


def test_efficiency_factor_carried_when_both_present() -> None:
    """Req 4.5: EF is carried as basis alongside a real decoupling verdict
    when both fields are present on the input metrics."""
    settings = FlagSettings(aerobic_drift_max_pct=5.0)
    metrics = DerivedMetrics(decoupling_pct=3.0, efficiency_factor=1.75)
    reading = evaluate(metrics, settings=settings)

    assert reading.outcome is DriftOutcome.COUPLED
    assert reading.efficiency_factor == 1.75


def test_pure_no_mutation_of_metrics() -> None:
    """Req 4.6: `DerivedMetrics` is itself a frozen dataclass, so no
    implementation of `evaluate` could mutate it without raising
    `FrozenInstanceError` -- the immutability guarantee is the type's own,
    not something this test discriminates on this module's behalf. Kept as
    a documentation-level check that the fields read back unchanged, not as
    a mutation-catching assertion."""
    metrics = DerivedMetrics(decoupling_pct=8.0, efficiency_factor=1.5)
    evaluate(metrics, settings=FlagSettings())

    assert metrics.decoupling_pct == 8.0
    assert metrics.efficiency_factor == 1.5


def test_pure_signature_takes_only_metrics_and_settings() -> None:
    """Req 4.7: depends on no other check's result -- the callable's own
    signature admits only `metrics` and the keyword-only `settings`."""
    import inspect

    params = inspect.signature(evaluate).parameters
    assert list(params) == ["metrics", "settings"]
    assert params["settings"].kind is inspect.Parameter.KEYWORD_ONLY
