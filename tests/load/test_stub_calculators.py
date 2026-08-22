"""Self-test for the shared calculator stubs (task 1.1, Req 1.1, 1.3, 2.7, 3.6, 13.6).

Proves the four stubs declared in ``conftest.py`` are exactly what the rest of
the suite -- starting with task 1.2's repin -- will rely on: each is
addressable by identifier once registered via its matching per-stub fixture
(``computing_calculator``, ``declining_calculator``, ``scoped_field_calculator``,
``hinted_calculator``), exercises its declared outcomes, and the registry is
provably empty again once the fixture tears down. Every case also requests
``isolated_registry`` -- declared first so it clears the registry before the
stub fixture registers -- so "empty" is literal, independent of whatever else
(e.g. a withdrawn methodology's calculator that once auto-registered on
import) is registered on import.

The leakage-pair tests near the bottom (``test_four_stub_fixtures_are_all_
registered_together`` / ``test_no_stub_calculator_leaks_into_the_next_test``)
exist specifically to make each of the four fixtures' ``try/finally``
teardown provably load-bearing: drop any one teardown and the second test of
the pair goes red. That pair deliberately skips ``isolated_registry``, whose
own snapshot/restore teardown would otherwise mask a stub fixture's leaked
registration.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from fitdocs import (
    Activity,
    DerivedMetrics,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load import registry, supports_activity
from fitdocs.load.types import (
    Computed,
    MissingInputs,
    NotComputed,
    ProfileView,
    Unsupported,
)
from fitdocs.model import SCHEMA_VERSION
from tests.load.conftest import (
    COMPUTING_FIELD,
    HINTED_FIELD,
    SCOPED_FIELD,
    ComputingCalculator,
    DecliningCalculator,
    HintedCalculator,
    ScopedFieldCalculator,
    stub_context,
)


# --- minimal fit-ingest fixtures (real types, no privilege a plugin author
# lacks -- the same shape any calculator author's own tests would build) ----
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


class StubProfile:
    """Minimal :class:`ProfileView` backed by an in-memory dict."""

    def __init__(self, values: dict[str, float] | None = None) -> None:
        self._values = dict(values or {})

    def get_number(self, key: str) -> float | None:
        return self._values.get(key)

    def benchmark(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date | None
    ) -> Benchmark | None:
        return None

    def has_benchmark(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        return False


class ScriptedSession:
    """A scripted :class:`InteractionSession`: no TTY, just a fixed confirm reply."""

    def __init__(self, *, confirm_reply: bool | None = None) -> None:
        self._confirm_reply = confirm_reply
        self.informed: list[str] = []

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        return self._confirm_reply

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        return None

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        return None

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        return None

    def inform(self, message: str) -> None:
        self.informed.append(message)


_EMPTY_PROFILE: ProfileView = StubProfile()


def test_empty_profile_benchmark_queries_reach_the_stub_implementation() -> None:
    """Reachability check for ``StubProfile.benchmark``/``.has_benchmark``:
    no calculator in this module reads either member, so without a call like
    this one, deleting both methods is a no-op at green -- Python performs no
    static Protocol enforcement, and mypy does not check this file
    (pyproject.toml's ``files = ["src"]``). Measured: removing this test and
    both methods leaves the suite green; keeping the test, deleting only the
    methods reds it with ``AttributeError``."""
    kind = BenchmarkKind.FTP_WATTS
    assert _EMPTY_PROFILE.benchmark(kind, discipline=Sport.RUN, on=None) is None
    assert _EMPTY_PROFILE.has_benchmark(kind, discipline=Sport.RUN) is False


def _ride_activity() -> Activity:
    return _activity(modality=Modality.BIKE, sport=Sport.RIDE)


# --- computing stub: addressable, computes, registry empties out again -----
def test_computing_calculator_is_addressable_and_computes(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
) -> None:
    looked_up = registry.get(computing_calculator.calculator_id)
    assert looked_up is computing_calculator

    session = ScriptedSession(confirm_reply=True)
    profile = StubProfile({COMPUTING_FIELD.key: 5.0})
    outcome = looked_up.compute(
        _run_activity(), DerivedMetrics(), profile, session, stub_context()
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.calculator_id == computing_calculator.calculator_id
    assert outcome.result.value == 50.0

    # Absent input still reaches the typed missing-inputs outcome (Req 1.1).
    missing = looked_up.compute(
        _run_activity(), DerivedMetrics(), _EMPTY_PROFILE, session, stub_context()
    )
    assert isinstance(missing, MissingInputs)
    assert missing.fields == (COMPUTING_FIELD,)


def test_computing_calculator_declines_unsupported_modality(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
) -> None:
    looked_up = registry.get(computing_calculator.calculator_id)
    session = ScriptedSession(confirm_reply=True)
    outcome = looked_up.compute(
        _ride_activity(), DerivedMetrics(), _EMPTY_PROFILE, session, stub_context()
    )
    assert isinstance(outcome, Unsupported)
    assert "running only" in outcome.reason


def test_computing_calculator_distinguishes_not_confirmed_reasons(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
) -> None:
    looked_up = registry.get(computing_calculator.calculator_id)
    profile = StubProfile({COMPUTING_FIELD.key: 5.0})

    non_interactive = ScriptedSession(confirm_reply=None)
    outcome = looked_up.compute(
        _run_activity(), DerivedMetrics(), profile, non_interactive, stub_context()
    )
    assert isinstance(outcome, NotComputed)
    assert outcome.reason == "non-interactive pass"

    declined = ScriptedSession(confirm_reply=False)
    outcome = looked_up.compute(
        _run_activity(), DerivedMetrics(), profile, declined, stub_context()
    )
    assert isinstance(outcome, NotComputed)
    assert outcome.reason == "user declined confirmation"


# --- declining stub: addressable, declines every sport (Req 1.3) -----------
def test_declining_calculator_is_addressable_and_declines(
    isolated_registry: None,
    declining_calculator: DecliningCalculator,
) -> None:
    looked_up = registry.get(declining_calculator.calculator_id)
    assert looked_up is declining_calculator

    session = ScriptedSession(confirm_reply=True)
    outcome = looked_up.compute(
        _run_activity(), DerivedMetrics(), _EMPTY_PROFILE, session, stub_context()
    )
    assert isinstance(outcome, Unsupported)
    assert "declines every sport" in outcome.reason


def test_declining_calculator_supports_narrows_one_sport_in_its_modality(
    isolated_registry: None,
    declining_calculator: DecliningCalculator,
) -> None:
    """Req 1.14: the modality declaration (``Modality.OTHER``) is broad and
    covers several sports; ``supports`` narrows out exactly the one sport it
    refuses (Rowing) while a sibling sport in the same declared modality (Hike)
    still answers ``True`` -- proving the narrowing is sport-granular, not a
    blanket refusal indistinguishable from declaring no modality at all.

    Asked through :func:`supports_activity`, the single seam
    tasks 3.2 and 4.1 both call, not the ``supports`` attribute directly
    (design.md ~1509)."""
    looked_up = registry.get(declining_calculator.calculator_id)

    refused = _activity(modality=Modality.OTHER, sport=Sport.ROWING)
    assert supports_activity(looked_up, refused) is False

    sibling = _activity(modality=Modality.OTHER, sport=Sport.HIKE)
    assert supports_activity(looked_up, sibling) is True

    outside_modality = _activity(modality=Modality.RUN, sport=Sport.RUN)
    assert supports_activity(looked_up, outside_modality) is False


# --- scoped-field stub: addressable, field lives under its own table -------
def test_scoped_field_calculator_is_addressable_and_scoped(
    isolated_registry: None,
    scoped_field_calculator: ScopedFieldCalculator,
) -> None:
    looked_up = registry.get(scoped_field_calculator.calculator_id)
    assert looked_up is scoped_field_calculator

    field = looked_up.required_athlete_fields()[0]
    assert field == SCOPED_FIELD
    assert field.key == f"{scoped_field_calculator.calculator_id}.custom_threshold"

    session = ScriptedSession(confirm_reply=True)
    profile = StubProfile({field.key: 42.0})
    outcome = looked_up.compute(
        _run_activity(), DerivedMetrics(), profile, session, stub_context()
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.value == 42.0


# --- hinted stub: addressable, hint is a getattr-discoverable seam ---------
def test_hinted_calculator_is_addressable_and_declares_hint(
    isolated_registry: None,
    hinted_calculator: HintedCalculator,
) -> None:
    looked_up = registry.get(hinted_calculator.calculator_id)
    assert looked_up is hinted_calculator

    # The generic prompt flow reads this off-protocol attribute via getattr
    # (Req 3.6) -- prove it is present and produces text for the field it hints.
    hints = getattr(looked_up, "athlete_field_hints", {})
    field = looked_up.required_athlete_fields()[0]
    assert field == HINTED_FIELD
    assert field.key in hints
    assert "23" in hints[field.key](23.0)

    session = ScriptedSession(confirm_reply=True)
    profile = StubProfile({field.key: 23.0})
    outcome = looked_up.compute(
        _run_activity(), DerivedMetrics(), profile, session, stub_context()
    )
    assert isinstance(outcome, Computed)


# --- leakage pair: fixture teardown actually empties the registry ----------
# ``isolated_registry`` snapshots and fully restores the whole registry on
# its own teardown, which would mask a stub fixture's own teardown failing
# to unregister -- so this pair deliberately does NOT request
# ``isolated_registry``. The first test registers all four stubs via their
# fixtures and confirms all four ids are present; the second test,
# immediately after in file order and requesting no calculator fixture at
# all, confirms none of the four stub ids (read off the classes, not string
# literals, so an id rename can't make this vacuous) is present anymore --
# proving the *stub fixtures'* own try/finally teardown (not
# isolated_registry's) did the unregistering. This is what makes bullet 3's
# "no stub leaks into another test's registry" assertable rather than merely
# asserted: drop any one fixture's try/finally and the second test below
# goes red.
def test_four_stub_fixtures_are_all_registered_together(
    computing_calculator: ComputingCalculator,
    declining_calculator: DecliningCalculator,
    scoped_field_calculator: ScopedFieldCalculator,
    hinted_calculator: HintedCalculator,
) -> None:
    available_ids = {calc.calculator_id for calc in registry.available()}
    assert computing_calculator.calculator_id in available_ids
    assert declining_calculator.calculator_id in available_ids
    assert scoped_field_calculator.calculator_id in available_ids
    assert hinted_calculator.calculator_id in available_ids


def test_no_stub_calculator_leaks_into_the_next_test() -> None:
    available_ids = {calc.calculator_id for calc in registry.available()}
    assert ComputingCalculator.calculator_id not in available_ids
    assert DecliningCalculator.calculator_id not in available_ids
    assert ScopedFieldCalculator.calculator_id not in available_ids
    assert HintedCalculator.calculator_id not in available_ids
