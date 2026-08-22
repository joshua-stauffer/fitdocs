"""Tests for calculator arbitration (task 3.2, Req 1.6, 8.4, 10.1-10.4, 13.5).

Arbitration is a pure policy decision: resolve exactly one calculator for an
activity, or state why not, with fixed total precedence -- forced id >
configured default > sole supporter (narrowed by the contract's support
question) > (none | ambiguity). These tests never touch a filesystem and use
only :class:`~tests.load.conftest.DecliningCalculator` and a small local stub
declaring the same broad modality, to exercise the narrowing behavior the
2026-07-25 design re-validation added.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fitdocs import Activity, DerivedMetrics, Modality, Provenance, Samples, Sport
from fitdocs.load import registry as reg
from fitdocs.load.arbitrate import (
    Ambiguous,
    NoCalculator,
    Selected,
    arbitrate,
    validate_configured,
)
from fitdocs.load.registry import UnknownCalculatorError
from fitdocs.load.types import (
    AthleteField,
    InteractionSession,
    LoadCalculator,
    LoadContext,
    LoadOutcome,
    ProfileView,
    Unsupported,
)
from fitdocs.model import SCHEMA_VERSION, SessionSummary

from .conftest import DecliningCalculator


def _samples() -> Samples:
    return Samples(
        time_s=(),
        heart_rate_bpm=(),
        power_w=(),
        cadence_rpm=(),
        speed_mps=(),
        distance_m=(),
        altitude_m=(),
        latitude_deg=(),
        longitude_deg=(),
        temperature_c=(),
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


def _activity(*, modality: Modality, sport: Sport) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=_samples(),
        sets=(),
        devices=(),
    )


def _run_activity() -> Activity:
    return _activity(modality=Modality.RUN, sport=Sport.RUN)


def _rowing_activity() -> Activity:
    return _activity(modality=Modality.OTHER, sport=Sport.ROWING)


def _hike_activity() -> Activity:
    return _activity(modality=Modality.OTHER, sport=Sport.HIKE)


def _workout_activity() -> Activity:
    return _activity(modality=Modality.OTHER, sport=Sport.WORKOUT)


class _StubCalculator:
    """Minimal calculator supporting exactly one bare modality, no narrowing."""

    def __init__(self, calculator_id: str, modality: Modality) -> None:
        self.calculator_id = calculator_id
        self.display_name = f"Stub {calculator_id}"
        self.supported_modalities = frozenset({modality})

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


class _HikeOnlyCalculator:
    """Declares the broad ``Modality.OTHER`` but narrows ``supports`` to the
    single sport ``Hike`` -- the second declarer needed to compose with
    :class:`DecliningCalculator` (which narrows out only ``Rowing``) so all
    three narrowing sub-cases (selected / no-calculator / ambiguous) are
    reachable from two calculators sharing one modality.
    """

    calculator_id = "stub-hike-only"
    display_name = "Stub Hike-Only Calculator"
    supported_modalities = frozenset({Modality.OTHER})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def supports(self, activity: Activity) -> bool:
        return (
            activity.modality in self.supported_modalities
            and activity.sport is Sport.HIKE
        )

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Unsupported(reason="stub never computes")


# Static structural-conformance checks -- a shape mismatch fails mypy --strict.
_STUB_CALC: LoadCalculator = _StubCalculator("stub-x", Modality.RUN)
_HIKE_ONLY_CALC: LoadCalculator = _HikeOnlyCalculator()

_SETTINGS_FILE = Path("/data-root/fitdocs.toml")


# --- forced id: sport-blind, unconditional Selected -------------------------
def test_forced_id_selects_regardless_of_registry_contents(
    isolated_registry: None,
) -> None:
    calc = _StubCalculator("only-one", Modality.RUN)
    reg.register(calc)

    outcome = arbitrate(_run_activity(), forced_id="only-one", default_calculator=None)

    assert outcome == Selected(calculator=calc)


def test_forced_id_selects_even_when_it_does_not_support_the_activity(
    isolated_registry: None,
) -> None:
    """Req 10.5: substituting a different calculator for a declining one is
    forbidden, so the forced path is not narrowed by sport here -- the engine
    settles that question downstream."""
    calc = DecliningCalculator()
    reg.register(calc)

    outcome = arbitrate(
        _rowing_activity(), forced_id="stub-declining", default_calculator=None
    )

    assert outcome == Selected(calculator=calc)


def test_forced_id_overrides_a_valid_configured_default(
    isolated_registry: None,
) -> None:
    forced = _StubCalculator("forced-one", Modality.RUN)
    default = _StubCalculator("default-one", Modality.RUN)
    reg.register(forced)
    reg.register(default)

    outcome = arbitrate(
        _run_activity(), forced_id="forced-one", default_calculator="default-one"
    )

    assert outcome == Selected(calculator=forced)


def test_forced_id_overrides_a_stale_configured_default(
    isolated_registry: None,
) -> None:
    """An explicit request makes a stale configured default irrelevant, not
    fatal (Req 10.3) -- arbitrate never even looks at it."""
    forced = _StubCalculator("forced-two", Modality.RUN)
    reg.register(forced)

    outcome = arbitrate(
        _run_activity(),
        forced_id="forced-two",
        default_calculator="not-registered-at-all",
    )

    assert outcome == Selected(calculator=forced)


# --- configured default: sport-blind, unconditional Selected ----------------
def test_configured_default_beats_several_supporters(isolated_registry: None) -> None:
    default = _StubCalculator("the-default", Modality.RUN)
    other = _StubCalculator("also-supports", Modality.RUN)
    reg.register(default)
    reg.register(other)

    outcome = arbitrate(
        _run_activity(), forced_id=None, default_calculator="the-default"
    )

    assert outcome == Selected(calculator=default)


def test_configured_default_that_does_not_support_the_activity_still_selects(
    isolated_registry: None,
) -> None:
    """The configured path is sport-blind by design; that the document ends
    up unsupported is the engine's concern (the support check), not
    arbitration's (Req 10.1)."""
    calc = DecliningCalculator()
    reg.register(calc)

    outcome = arbitrate(
        _rowing_activity(), forced_id=None, default_calculator="stub-declining"
    )

    assert outcome == Selected(calculator=calc)


# --- no default: narrowed candidate selection --------------------------------
def test_empty_registry_yields_no_calculator(isolated_registry: None) -> None:
    outcome = arbitrate(_run_activity(), forced_id=None, default_calculator=None)

    assert outcome == NoCalculator(modality=Modality.RUN)


def test_one_supporter_is_selected(isolated_registry: None) -> None:
    calc = _StubCalculator("sole-supporter", Modality.RUN)
    reg.register(calc)

    outcome = arbitrate(_run_activity(), forced_id=None, default_calculator=None)

    assert outcome == Selected(calculator=calc)


def test_two_supporters_with_no_default_resolve_to_sorted_ambiguity(
    isolated_registry: None,
) -> None:
    calc_b = _StubCalculator("bbb", Modality.RUN)
    calc_a = _StubCalculator("aaa", Modality.RUN)
    reg.register(calc_b)
    reg.register(calc_a)

    outcome = arbitrate(_run_activity(), forced_id=None, default_calculator=None)

    assert outcome == Ambiguous(candidates=("aaa", "bbb"))


def test_non_supporting_calculator_is_not_a_candidate(isolated_registry: None) -> None:
    """A calculator registered for a different modality never enters
    candidate selection at all (the registry's cheap modality prefilter)."""
    calc = _StubCalculator("bike-only", Modality.BIKE)
    reg.register(calc)

    outcome = arbitrate(_run_activity(), forced_id=None, default_calculator=None)

    assert outcome == NoCalculator(modality=Modality.RUN)


# --- 2026-07-25 design re-validation: narrowing by supports_activity --------
def test_declaring_the_modality_but_narrowed_out_resolves_selected(
    isolated_registry: None,
) -> None:
    """Two calculators declare Modality.OTHER; only DecliningCalculator
    supports Workout (HikeOnlyCalculator narrows to Hike only) -> exactly
    one supports this activity -> Selected, not Ambiguous."""
    declining = DecliningCalculator()
    hike_only = _HikeOnlyCalculator()
    reg.register(declining)
    reg.register(hike_only)

    outcome = arbitrate(_workout_activity(), forced_id=None, default_calculator=None)

    assert outcome == Selected(calculator=declining)


def test_neither_supporting_narrows_to_no_calculator(isolated_registry: None) -> None:
    """Both calculators declare Modality.OTHER; neither supports Rowing
    (DecliningCalculator narrows Rowing out, HikeOnlyCalculator narrows to
    Hike only) -> NoCalculator, not a misleading Ambiguous directing the
    user to a default that could not have helped."""
    declining = DecliningCalculator()
    hike_only = _HikeOnlyCalculator()
    reg.register(declining)
    reg.register(hike_only)

    outcome = arbitrate(_rowing_activity(), forced_id=None, default_calculator=None)

    assert outcome == NoCalculator(modality=Modality.OTHER)


def test_both_supporting_narrows_to_ambiguous(isolated_registry: None) -> None:
    """Both calculators declare Modality.OTHER and both support Hike
    (DecliningCalculator only narrows out Rowing) -> Ambiguous with both ids
    sorted."""
    declining = DecliningCalculator()
    hike_only = _HikeOnlyCalculator()
    reg.register(declining)
    reg.register(hike_only)

    outcome = arbitrate(_hike_activity(), forced_id=None, default_calculator=None)

    assert outcome == Ambiguous(
        candidates=tuple(sorted([declining.calculator_id, hike_only.calculator_id]))
    )


def test_narrowing_never_reinstates_a_calculator_the_modality_prefilter_dropped(
    isolated_registry: None,
) -> None:
    """A calculator declaring a *different* modality can never become a
    candidate, no matter what a hypothetical ``supports`` would answer --
    the registry prefilter runs first and is never widened."""
    other_modality = _StubCalculator("wrong-modality", Modality.BIKE)
    reg.register(other_modality)

    outcome = arbitrate(_hike_activity(), forced_id=None, default_calculator=None)

    assert outcome == NoCalculator(modality=Modality.OTHER)


# --- determinism / registration-order independence --------------------------
def test_ambiguity_ignores_registration_order(isolated_registry: None) -> None:
    """Registering in the opposite order yields the identical sorted
    candidates -- registration order is never consulted (Req 10.1, 10.2)."""
    calc_a = _StubCalculator("aaa", Modality.RUN)
    calc_b = _StubCalculator("bbb", Modality.RUN)
    reg.register(calc_a)
    reg.register(calc_b)

    outcome = arbitrate(_run_activity(), forced_id=None, default_calculator=None)

    assert outcome == Ambiguous(candidates=("aaa", "bbb"))


# --- validate_configured (Req 10.4) ------------------------------------------
def test_validate_configured_is_a_no_op_with_nothing_configured(
    isolated_registry: None,
) -> None:
    validate_configured(None, None, settings_file=_SETTINGS_FILE)


def test_validate_configured_accepts_a_registered_forced_id(
    isolated_registry: None,
) -> None:
    reg.register(_StubCalculator("known", Modality.RUN))

    validate_configured("known", None, settings_file=_SETTINGS_FILE)


def test_validate_configured_accepts_a_registered_default(
    isolated_registry: None,
) -> None:
    reg.register(_StubCalculator("known", Modality.RUN))

    validate_configured(None, "known", settings_file=_SETTINGS_FILE)


def test_unregistered_forced_id_raises_naming_value_source_and_registered(
    isolated_registry: None,
) -> None:
    reg.register(_StubCalculator("known", Modality.RUN))

    with pytest.raises(UnknownCalculatorError) as exc_info:
        validate_configured("nope", None, settings_file=_SETTINGS_FILE)

    message = str(exc_info.value)
    assert "nope" in message
    assert "--calculator" in message
    assert "known" in message


def test_unregistered_default_raises_naming_value_source_and_registered(
    isolated_registry: None,
) -> None:
    reg.register(_StubCalculator("known", Modality.RUN))

    with pytest.raises(UnknownCalculatorError) as exc_info:
        validate_configured(None, "stale-default", settings_file=_SETTINGS_FILE)

    message = str(exc_info.value)
    assert "stale-default" in message
    assert "default_calculator" in message
    assert str(_SETTINGS_FILE) in message
    assert "known" in message


def test_unregistered_default_message_names_empty_registry(
    isolated_registry: None,
) -> None:
    with pytest.raises(UnknownCalculatorError) as exc_info:
        validate_configured(None, "anything", settings_file=_SETTINGS_FILE)

    assert "none" in str(exc_info.value)


def test_forced_id_takes_precedence_in_validation_over_a_stale_default(
    isolated_registry: None,
) -> None:
    """Only the id actually in play is validated: a forced id that is
    registered means a stale, unregistered default is never even
    inspected."""
    reg.register(_StubCalculator("valid-forced", Modality.RUN))

    validate_configured("valid-forced", "not-registered", settings_file=_SETTINGS_FILE)
