"""Contract tests for :mod:`fitdocs.load.types` (task 1.2, Req 1.1-1.4).

These tests pin the *shape* of the pluggable calculator seam rather than any
behaviour: a stub :class:`LoadCalculator` structurally satisfies the protocol
and drives every :data:`LoadOutcome` variant from its inputs, a single
exhaustive handler folds the closed union with ``assert_never`` in the
fallthrough (so mypy --strict flags a dropped variant), and the dataclasses are
frozen with tuple sequence fields for deterministic downstream rendering.

The exhaustiveness guarantee is proven statically -- this module is in
``[tool.mypy].files`` (pyproject.toml), so the bare ``uv run mypy`` covers it
-- not at runtime: if a new outcome type were added to :data:`LoadOutcome`
without a branch in :func:`_describe`, ``assert_never`` would receive a
non-``Never`` argument and mypy would fail.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from typing import Protocol, assert_never

import pytest

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
from fitdocs.load.settings import DEFAULT_LOAD_SETTINGS, LoadSettings
from fitdocs.load.types import (
    AthleteField,
    BenchmarkRef,
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
    supports_activity,
)
from fitdocs.model import SCHEMA_VERSION

_LEVEL_KEY = "stub.level"


# --- fit-ingest fixtures (minimal, real types) ------------------------------
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


def _ride_activity() -> Activity:
    return _activity(modality=Modality.BIKE, sport=Sport.RIDE)


# --- stub contract implementations ------------------------------------------
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
    """A scripted :class:`InteractionSession`: no real TTY, just queued replies.

    ``confirm`` replays a fixed reply (``None`` models a declined / non-
    interactive session); the remaining primitives return ``None`` -- the
    contract's "no answer, never assume consent" default.
    """

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


class StubCalculator:
    """A calculator that structurally satisfies :class:`LoadCalculator` and
    returns each :data:`LoadOutcome` variant based purely on its inputs.

    Deliberately a **plain duck-typed class that does not subclass
    :class:`LoadCalculator`** -- proving Req 1.14's core on the harder
    subject: it writes no ``supports`` member of its own, yet
    :func:`~fitdocs.load.types.supports_activity` still answers for it by its
    declared :attr:`supported_modalities`, with no subclassing and no
    registration-time mutation of the calculator object (see
    :func:`test_default_supports_agrees_with_the_modality_test_for_every_modality`
    below).
    """

    calculator_id = "stub"
    display_name = "Stub Methodology"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (
            AthleteField(
                key=_LEVEL_KEY,
                label="Stub level",
                kind="int",
                minimum=1,
                maximum=10,
                help_text="a stub input used only in contract tests",
            ),
        )

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
        level = profile.get_number(_LEVEL_KEY)
        if level is None:
            return MissingInputs(fields=self.required_athlete_fields())
        confirmed = session.confirm("Confirm computed load?")
        if confirmed is None:
            return NotComputed(reason="non-interactive pass")
        if not confirmed:
            return NotComputed(reason="user declined confirmation")
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=level * 10.0,
                basis="stub basis",
                non_selected=(),
                flags=(),
                inputs_used=(("Stub level", str(int(level))),),
                notes=("stub note",),
            )
        )


def _context() -> LoadContext:
    """A minimal :class:`LoadContext` for driving ``compute`` directly."""
    return LoadContext(activity_date=None, settings=DEFAULT_LOAD_SETTINGS)


# Static structural-conformance checks -- a shape mismatch fails mypy --strict
# (this module is in `[tool.mypy].files`, pyproject.toml).
_CALC: LoadCalculator = StubCalculator()
_PROFILE: ProfileView = StubProfile()
_SESSION: InteractionSession = ScriptedSession()


def _describe(outcome: LoadOutcome) -> str:
    """Exhaustively fold the closed :data:`LoadOutcome` union.

    ``assert_never`` in the fallthrough is the closed-union guarantee: adding a
    new outcome type without a branch here makes mypy --strict reject this file.
    """
    if isinstance(outcome, Computed):
        return f"computed:{outcome.result.value}"
    if isinstance(outcome, Unsupported):
        return f"unsupported:{outcome.reason}"
    if isinstance(outcome, MissingInputs):
        return f"missing:{len(outcome.fields)}"
    if isinstance(outcome, NotComputed):
        return f"notcomputed:{outcome.reason}"
    assert_never(outcome)


# --- tests ------------------------------------------------------------------
def test_stub_calculator_conforms_to_protocol() -> None:
    calc: LoadCalculator = StubCalculator()
    assert calc.calculator_id == "stub"
    assert calc.display_name == "Stub Methodology"
    assert calc.supported_modalities == frozenset({Modality.RUN})
    fields = calc.required_athlete_fields()
    assert isinstance(fields, tuple)
    assert fields[0].key == _LEVEL_KEY
    assert fields[0].kind == "int"


def test_compute_declines_unsupported_sport() -> None:
    outcome = StubCalculator().compute(
        _ride_activity(),
        DerivedMetrics(),
        StubProfile(),
        ScriptedSession(),
        _context(),
    )
    assert isinstance(outcome, Unsupported)
    assert "Ride" in outcome.reason
    assert _describe(outcome) == f"unsupported:{outcome.reason}"


def test_compute_reports_missing_inputs() -> None:
    outcome = StubCalculator().compute(
        _run_activity(),
        DerivedMetrics(),
        StubProfile(),
        ScriptedSession(confirm_reply=True),
        _context(),
    )
    assert isinstance(outcome, MissingInputs)
    assert outcome.fields[0].key == _LEVEL_KEY
    assert _describe(outcome) == "missing:1"


def test_compute_not_computed_when_non_interactive() -> None:
    outcome = StubCalculator().compute(
        _run_activity(),
        DerivedMetrics(),
        StubProfile({_LEVEL_KEY: 3.0}),
        ScriptedSession(confirm_reply=None),
        _context(),
    )
    assert isinstance(outcome, NotComputed)
    assert outcome.reason == "non-interactive pass"
    assert _describe(outcome) == "notcomputed:non-interactive pass"


def test_compute_not_computed_when_declined() -> None:
    outcome = StubCalculator().compute(
        _run_activity(),
        DerivedMetrics(),
        StubProfile({_LEVEL_KEY: 3.0}),
        ScriptedSession(confirm_reply=False),
        _context(),
    )
    assert isinstance(outcome, NotComputed)
    assert "declined" in outcome.reason


def test_compute_returns_computed_when_confirmed() -> None:
    session = ScriptedSession(confirm_reply=True)
    outcome = StubCalculator().compute(
        _run_activity(),
        DerivedMetrics(),
        StubProfile({_LEVEL_KEY: 3.0}),
        session,
        _context(),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.calculator_id == "stub"
    assert outcome.result.value == 30.0
    assert outcome.result.non_selected == ()
    assert outcome.result.flags == ()
    assert _describe(outcome) == "computed:30.0"


def test_describe_handles_every_outcome_variant() -> None:
    field = AthleteField(key="k", label="l", kind="int", minimum=1, maximum=2)
    result = LoadResult(
        calculator_id="stub",
        display_name="Stub",
        value=1.0,
        basis="a basis",
        non_selected=(),
        flags=(),
        inputs_used=(("l", "1"),),
        notes=("n",),
    )
    outcomes: tuple[LoadOutcome, ...] = (
        Computed(result=result),
        Unsupported(reason="nope"),
        MissingInputs(fields=(field,)),
        NotComputed(reason="declined"),
    )
    described = [_describe(o) for o in outcomes]
    assert described == [
        "computed:1.0",
        "unsupported:nope",
        "missing:1",
        "notcomputed:declined",
    ]


def test_load_result_is_frozen() -> None:
    result = LoadResult(
        calculator_id="stub",
        display_name="Stub",
        value=1.0,
        basis="a basis",
        non_selected=(),
        flags=(),
        inputs_used=(("l", "1"),),
        notes=(),
    )
    # Attribute name via a variable: frozen assignment must raise at runtime,
    # while a direct ``result.value = ...`` would (correctly) be a mypy error.
    frozen_attr = "value"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(result, frozen_attr, 2.0)


def test_athlete_field_is_frozen_and_help_text_optional() -> None:
    field = AthleteField(key="k", label="l", kind="float", minimum=0.0, maximum=1.0)
    assert field.help_text is None
    frozen_attr = "label"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(field, frozen_attr, "x")


# --- AthleteField's benchmark member (task 4.1, Req 8.1) ---------------------


def test_athlete_field_declares_benchmark_as_the_last_field_defaulting_to_none() -> (
    None
):
    """``benchmark`` is appended after ``help_text`` so every existing
    positional/keyword construction keeps working (design's ProfileContract).

    Mutation caught: reordering ``benchmark`` before ``help_text`` in the
    dataclass body, or dropping it entirely, reddens the field-order
    assertion below -- run by hand (both mutations tried, both observed red,
    then reverted).
    """
    field_names = [f.name for f in dataclasses.fields(AthleteField)]
    assert field_names == [
        "key",
        "label",
        "kind",
        "minimum",
        "maximum",
        "help_text",
        "benchmark",
    ]
    # Every pre-existing positional/keyword construction (no ``benchmark``
    # argument at all) still produces a field defaulting to ``None`` --
    # Req 7.4's "keyed numeric access retained" depends on this not becoming
    # a required constructor argument.
    field = AthleteField(key="k", label="l", kind="int", minimum=1, maximum=2)
    assert field.benchmark is None

    # The field's *declared* type is pinned too, not just its name/position:
    # nothing in ``src/`` yet consumes this field for mypy to enforce it, so
    # a substitution like ``benchmark: object | None`` would pass every other
    # gate here.
    last_field = dataclasses.fields(AthleteField)[-1]
    assert last_field.type == "BenchmarkRef | None"


def test_athlete_field_accepts_a_benchmark_ref_naming_the_table_not_a_value_path() -> (
    None
):
    """A declared benchmark field's ``key`` identifies the table an entry
    lives in (``benchmarks.<scope>.<kind>``), never a value path -- the field
    itself carries the query shape via :class:`BenchmarkRef` (Req 8.1)."""
    ref = BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RUN)
    field = AthleteField(
        key="benchmarks.run.ftp_watts",
        label="Running FTP",
        kind="float",
        minimum=1.0,
        maximum=2000.0,
        benchmark=ref,
    )
    assert field.benchmark is not None
    assert field.benchmark.kind is BenchmarkKind.FTP_WATTS
    assert field.benchmark.discipline is Sport.RUN


def test_benchmark_ref_field_order_is_kind_then_discipline() -> None:
    """Positive control distinguishing the two :class:`BenchmarkRef` fields by
    *position*, not only by keyword -- a keyword-only construction would not
    catch the two fields being swapped in the dataclass body.

    Mutation caught: swapping the declaration order of ``kind`` and
    ``discipline`` in :class:`BenchmarkRef` makes the positional construction
    below bind ``Sport.RUN`` to ``kind`` and ``BenchmarkKind.FTP_WATTS`` to
    ``discipline`` -- reddening this assertion (run by hand, observed red,
    reverted).
    """
    field_names = [f.name for f in dataclasses.fields(BenchmarkRef)]
    assert field_names == ["kind", "discipline"]
    ref = BenchmarkRef(BenchmarkKind.FTP_WATTS, Sport.RUN)  # positional
    assert ref.kind is BenchmarkKind.FTP_WATTS
    assert ref.discipline is Sport.RUN

    # ``dataclasses.fields()`` names/order alone say nothing about the
    # *declared* type of each field -- pin those too, since nothing in
    # ``src/`` yet consumes ``BenchmarkRef`` for mypy to check on its behalf
    # (pyproject.toml's ``files = ["src"]`` also excludes this test file).
    field_types = [(f.name, f.type) for f in dataclasses.fields(BenchmarkRef)]
    assert field_types == [("kind", "BenchmarkKind"), ("discipline", "Sport | None")]


def test_benchmark_ref_is_frozen() -> None:
    ref = BenchmarkRef(kind=BenchmarkKind.MAX_HR_BPM, discipline=None)
    frozen_attr = "kind"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(ref, frozen_attr, BenchmarkKind.LTHR_BPM)


# --- ProfileView's benchmark queries (task 4.1, Req 7.1, 7.2, 7.5, 7.7) ------


def test_profile_view_benchmark_queries_take_discipline_and_date_explicitly() -> None:
    """Req 7.5: discipline and date travel as explicit keyword arguments, not
    encoded into a key string -- ``benchmark``/``has_benchmark`` take no
    single string-only parameter that could carry structured data.

    Mutation caught: collapsing ``benchmark``'s signature to
    ``def benchmark(self, key: str) -> Benchmark | None`` (a single string
    parameter, mirroring ``get_number``) still satisfies *some* Protocol
    shape but drops ``discipline``/``on`` from the parameter set this
    assertion names -- reddening it (run by hand, observed red, reverted).
    """
    import inspect

    benchmark_sig = inspect.signature(ProfileView.benchmark)
    benchmark_params = list(benchmark_sig.parameters)
    assert benchmark_params == ["self", "kind", "discipline", "on"]
    has_benchmark_params = list(inspect.signature(ProfileView.has_benchmark).parameters)
    assert has_benchmark_params == ["self", "kind", "discipline"]

    # Req 7.5's keyword-only intent: ``discipline``/``on`` cannot be passed
    # positionally, so a caller can never confuse which is which.
    assert benchmark_sig.parameters["discipline"].kind is inspect.Parameter.KEYWORD_ONLY
    assert benchmark_sig.parameters["on"].kind is inspect.Parameter.KEYWORD_ONLY

    # ``inspect.signature(...).parameters`` discards annotations entirely --
    # binding only names/order/kind -- so the declared *type* of ``on`` is
    # pinned separately here. ``on`` must stay ``date | None``: design's
    # ProfileContract postconditions make the undated case explicit
    # ("on=None -- an undated document -- yields None"), and
    # ``LoadContext.activity_date`` is itself ``date | None``, so the
    # documented call ``profile.benchmark(..., on=context.activity_date)``
    # must keep type-checking under mypy --strict for plugin authors.
    assert benchmark_sig.parameters["on"].annotation == "date | None"


def test_profile_view_benchmark_queries_reach_the_protocol_typed_double() -> None:
    """Runtime half of the structural-conformance claim: ``_PROFILE`` is typed
    ``ProfileView`` and calling ``.benchmark``/``.has_benchmark`` through that
    reference actually reaches :class:`StubProfile`'s implementation, not
    just an annotation mypy never checks for this file (``files = ["src"]``,
    pyproject.toml -- the same caveat :data:`_CALC` above documents).

    Mutation caught: deleting ``StubProfile.has_benchmark`` (or ``.benchmark``)
    turns this call into an ``AttributeError`` at runtime, since Python
    performs no static Protocol check -- reddening this test (run by hand,
    observed red as ``AttributeError``, reverted).
    """
    kind = BenchmarkKind.FTP_WATTS
    assert _PROFILE.benchmark(kind, discipline=Sport.RUN, on=None) is None
    assert _PROFILE.has_benchmark(kind, discipline=Sport.RUN) is False


def test_sequence_fields_are_tuples() -> None:
    non_selected = (
        NonSelectedValue(key="hr", label="HR channel", value=None, reason="no data"),
    )
    flags = (
        QualityFlag(
            key="cadence-lock",
            label="Cadence lock",
            verdict="detected",
            detail="cadence variance below threshold",
        ),
    )
    result = LoadResult(
        calculator_id="stub",
        display_name="Stub",
        value=1.0,
        basis="a basis",
        non_selected=non_selected,
        flags=flags,
        inputs_used=(("l", "1"),),
        notes=("a", "b"),
    )
    assert isinstance(result.inputs_used, tuple)
    assert isinstance(result.notes, tuple)
    assert isinstance(result.non_selected, tuple)
    assert isinstance(result.flags, tuple)
    missing = MissingInputs(
        fields=(
            AthleteField(key="k", label="l", kind="int", minimum=None, maximum=None),
        )
    )
    assert isinstance(missing.fields, tuple)


# --- redefined-contract vocabulary (Req 1.8-1.11) ---------------------------


def test_non_selected_value_is_frozen() -> None:
    entry = NonSelectedValue(key="hr", label="HR channel", value=5.0, reason="lower")
    frozen_attr = "value"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(entry, frozen_attr, 6.0)


def test_quality_flag_is_frozen() -> None:
    flag = QualityFlag(
        key="cadence-lock", label="Cadence lock", verdict="detected", detail="d"
    )
    frozen_attr = "verdict"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(flag, frozen_attr, "not-detected")


def test_non_selected_value_may_carry_no_computed_number() -> None:
    """A ``value is None`` entry records absence explicitly (Req 1.11, 9.1) --
    never a fabricated ``0``."""
    entry = NonSelectedValue(
        key="power", label="Power channel", value=None, reason="no power meter"
    )
    assert entry.value is None
    assert entry.value != 0
    assert entry.value != 0.0


def test_load_result_with_nothing_to_diagnose_carries_empty_collections() -> None:
    """A methodology with nothing to diagnose supplies empty tuples -- nothing
    is fabricated on its behalf (Req 1.11)."""
    result = LoadResult(
        calculator_id="stub",
        display_name="Stub",
        value=1.0,
        basis="a basis",
        non_selected=(),
        flags=(),
        inputs_used=(),
        notes=(),
    )
    assert result.non_selected == ()
    assert result.flags == ()


def test_load_result_value_is_the_only_field_of_its_kind() -> None:
    """Structural pin for Req 1.10: no diagnostic type shares ``value``'s name,
    type position, or field name -- the selected value cannot be confused with
    a diagnostic entry."""
    result_fields = {f.name: f.type for f in dataclasses.fields(LoadResult)}
    non_selected_fields = {f.name for f in dataclasses.fields(NonSelectedValue)}
    flag_fields = {f.name for f in dataclasses.fields(QualityFlag)}

    # "value" only appears as LoadResult's single scalar float -- never on the
    # diagnostic types under that name, and the diagnostic types' own "value"
    # (NonSelectedValue) is an Optional, a different type position entirely.
    assert result_fields["value"] == "float"
    assert "value" not in flag_fields
    assert "value" in non_selected_fields  # deliberately typed float | None, not float

    # LoadResult carries no bare scalar under the diagnostic types' names.
    assert "verdict" not in result_fields
    assert "reason" not in result_fields


# --- Amendment 3: the per-pass context (Req 1.12-1.15) ----------------------


def test_load_context_is_frozen_and_carries_exactly_two_fields() -> None:
    context = _context()
    field_names = {f.name for f in dataclasses.fields(LoadContext)}
    assert field_names == {"activity_date", "settings"}

    frozen_attr = "activity_date"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(context, frozen_attr, None)


def test_load_context_settings_type_is_a_type_checking_only_annotation() -> None:
    """The single Req 14.7 exception: ``LoadSettings`` is referenced only for
    the annotation (a string, thanks to ``from __future__ import annotations``)
    -- ``types.py`` itself never imports ``fitdocs.load.settings`` at runtime."""
    fields_by_name = {f.name: f for f in dataclasses.fields(LoadContext)}
    assert fields_by_name["activity_date"].type == "date | None"
    assert fields_by_name["settings"].type == "LoadSettings"


def test_load_context_accepts_settings_and_a_dated_or_undated_activity_date() -> None:
    import datetime

    a_date = datetime.date(2026, 1, 1)
    dated = LoadContext(activity_date=a_date, settings=LoadSettings())
    undated = LoadContext(activity_date=None, settings=DEFAULT_LOAD_SETTINGS)
    assert dated.activity_date == a_date
    assert undated.activity_date is None
    assert undated.settings == DEFAULT_LOAD_SETTINGS


def _protocol_member_names(protocol: type) -> set[str]:
    """Every member ``protocol`` exposes, for the forbidden-member check
    below (task 6.4 round 2, Req 1.13): ``dir()`` alone omits annotation-only
    Protocol members entirely -- a plain

        class ProfileView(Protocol):
            activity_date: date | None

    is a real (structurally binding) Protocol member that never appears in
    ``dir(ProfileView)``, so a ``dir()``-only check is bypassable by the
    natural, non-``@property`` spelling of a forbidden member. This instead
    unions ``dir()`` with every class in ``protocol.__mro__``'s own
    ``__annotations__`` (a Protocol base could carry an annotation-only
    member too), catching both the ``@property`` spelling (visible via
    ``dir()``) and the annotation-only spelling (visible only via
    ``__annotations__``).
    """
    names = set(dir(protocol))
    for klass in protocol.__mro__:
        names |= set(getattr(klass, "__annotations__", {}))
    return names


def test_dir_is_blind_to_a_bare_annotation_but_the_union_helper_is_not() -> None:
    """Executable, self-contained proof of the failure mode
    :func:`_protocol_member_names` exists to close -- independent of
    :class:`ProfileView`, so it keeps discriminating even if that Protocol's
    own shape changes.

    Repo-wide audit (2026-07-27, queue item
    ``2026-07-26-protocol-purity-guards-miss-annotations``): this file holds
    the only "Protocol/class exposes no X" purity guard in the suite that is
    built on ``dir()`` -- and it is the only one that needed fixing.
    Two other purity guards exist and were examined, not missed: `Divergence`
    carries no ``key`` field (``tests/load/channels/test_sources.py:202-204``,
    ``assert "key" not in field_names``) and ``LoadResult`` carries no bare
    ``value``/``verdict``/``reason`` scalar under the diagnostic types' names
    (``test_load_result_value_is_the_only_field_of_its_kind``,
    ``tests/load/test_types.py:499-504``).
    Both are built on ``dataclasses.fields()``, which *does* see annotation-only
    fields (a dataclass field is always an annotation), so neither shares this
    module's blind spot and neither needed switching.
    :class:`~fitdocs.tiles.TileSource`, :class:`InteractionSession`, and
    :class:`LoadCalculator` -- the repo's other three ``Protocol`` classes --
    carry no member-exposure guard at all (blind or otherwise), so there was
    nothing to switch there either.

    Every ``hasattr``/``vars``/``__dict__`` site in ``tests/`` was also
    examined; none of them is a second instance of this blind spot, but they
    are not all one shape. Categories found: module-level negative-export
    guards (``tests/test_contract.py``, ``tests/test_contract_consumers.py``);
    a ``vars(module)`` call-count spy (``tests/load/test_settings.py:506``);
    positive public-API presence checks, the opposite risk direction, where a
    bare annotation would correctly fail rather than slip through
    (``tests/test_public_api.py``, ``tests/test_contract_consumers.py:346``,
    ``tests/test_docs_guarantees.py``); an instance-level absence check next
    to this test in this same file (in
    ``test_default_supports_agrees_with_the_modality_test_for_every_modality``,
    ``assert not hasattr(calc, "supports")`` -- ``calc`` is a plain instance
    with no declared ``supports`` attribute at all, not a Protocol whose
    member set can be spelled as a bare class-body annotation); and
    ``hasattr(os, "geteuid")`` platform probes unrelated to any Protocol
    (``tests/test_declaration.py``, ``tests/test_drain.py``,
    ``tests/test_audit.py``, ``tests/test_inbox_e2e.py``). ``inspect.getmembers``
    in ``tests/metrics/test_stress.py`` filters to ``inspect.isfunction``, which
    an annotation-only member can never satisfy, and every ``Protocol``
    doc-example check in ``tests/test_docs_guarantees.py`` is mypy-driven
    structural typing, not a runtime member-set assertion.

    If a future purity guard is added for any of the three unguarded
    Protocols, or for a new one, it MUST be built on
    :func:`_protocol_member_names` (or an equivalent ``__mro__``-walked
    ``__annotations__`` union), not on ``dir()`` alone -- this test is the
    standing proof of why.
    """

    class _DecoyBase(Protocol):
        inherited: int  # annotation only, lives on the base -- never on _Decoy itself

    class _Decoy(_DecoyBase, Protocol):
        smuggled: int  # annotation only: no assignment, no @property

    # The blind spot: a bare annotation never reaches dir(), on the class
    # itself or on a Protocol base it inherits from.
    assert "smuggled" not in dir(_Decoy)
    assert "inherited" not in dir(_Decoy)

    # A non-__mro__-walked reading of __annotations__ is also blind to the
    # inherited member: a subclass that defines any annotation of its own
    # (as _Decoy does, with "smuggled") gets its *own* __annotations__ dict,
    # which shadows the base's -- getattr(_Decoy, "__annotations__", {})
    # never sees "inherited" at all.
    assert "inherited" not in getattr(_Decoy, "__annotations__", {})

    # The fix: unioning dir() with every __mro__ class's __annotations__ sees
    # both the class's own bare annotation and one inherited from a Protocol
    # base -- the two ways this failure mode can be spelled.
    assert "smuggled" in _protocol_member_names(_Decoy)
    assert "inherited" in _protocol_member_names(_Decoy)


def test_profile_view_protocol_exposes_no_per_pass_member() -> None:
    """Req 1.13: ``ProfileView`` stays a store view -- no activity date, no
    configured window, no resolved load configuration.

    Mutation caught: adding any of the three forbidden members as a plain
    annotation (e.g. ``activity_date: date | None`` directly on the class
    body, no ``@property``) reddens this test -- confirmed by running that
    exact mutation, which a ``dir()``-only check does not catch (``dir()``
    never lists an annotation-only Protocol member at all).
    """
    members = _protocol_member_names(ProfileView)
    assert "activity_date" not in members
    assert "staleness_window_days" not in members
    assert "load_settings" not in members
    # It still exposes the store queries it declares -- the pre-existing
    # keyed access plus the two benchmark queries this task adds (Req 7.1,
    # 7.2, 7.4). (These are inclusion checks only; they do not assert that
    # no other member exists.)
    assert "get_number" in members
    assert "benchmark" in members
    assert "has_benchmark" in members


def test_default_supports_agrees_with_the_modality_test_for_every_modality() -> None:
    """Req 1.14: a calculator declaring nothing more specific than
    ``supported_modalities`` answers the support question by modality
    membership -- proven here against :class:`StubCalculator`, a plain class
    that does **not** subclass :class:`LoadCalculator` and writes no
    ``supports`` of its own. ``supports_activity`` is the single entry point
    the training-load layer asks (tasks 3.2 and 4.1 both call it), so this is
    also the seam a duck-typed calculator with no ``supports`` must resolve
    through -- not a per-calculator attribute call."""
    calc = StubCalculator()
    assert not hasattr(calc, "supports")
    for modality in Modality:
        activity = _activity(modality=modality, sport=Sport.RUN)
        expected = modality in calc.supported_modalities
        assert supports_activity(calc, activity) is expected


class _CustomSupportsCalculator:
    """A duck-typed calculator that writes its own ``supports`` -- proves
    :func:`supports_activity` prefers that answer over the modality-membership
    default (Req 1.14), in both directions. ``supports`` here is deliberately
    the *inverse* of modality membership for every activity this test drives,
    so a mutation that ignores the custom ``supports`` and falls back to
    membership disagrees with this test for every assertion, not just one --
    reducing ``supports_activity`` to the bare membership check must redden
    this test."""

    calculator_id = "custom-supports"
    display_name = "Custom Supports Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def supports(self, activity: Activity) -> bool:
        return activity.modality not in self.supported_modalities

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        raise NotImplementedError


def test_custom_supports_answer_is_used_over_modality_membership() -> None:
    """Req 1.14: a calculator that defines its own ``supports`` has that
    answer used by :func:`supports_activity`, not the modality-membership
    default -- checked for an activity inside the declared modality and one
    outside it, so the custom answer is exercised in both directions and
    differs from the membership answer in both cases."""
    calc = _CustomSupportsCalculator()
    inside = _activity(modality=Modality.RUN, sport=Sport.RUN)
    outside = _activity(modality=Modality.BIKE, sport=Sport.RIDE)

    membership_inside = Modality.RUN in calc.supported_modalities
    membership_outside = Modality.BIKE in calc.supported_modalities
    assert membership_inside is True
    assert membership_outside is False

    assert supports_activity(calc, inside) is calc.supports(inside)
    assert supports_activity(calc, outside) is calc.supports(outside)
    assert supports_activity(calc, inside) is not membership_inside
    assert supports_activity(calc, outside) is not membership_outside


def test_not_computed_is_the_unions_fourth_variant() -> None:
    outcome: LoadOutcome = NotComputed(reason="a reason")
    assert isinstance(outcome, NotComputed)
    assert _describe(outcome) == "notcomputed:a reason"


def test_not_confirmed_resolves_nowhere_in_the_package() -> None:
    """Req 1.15: the rename is total -- the old name is absent from every
    module under ``src/fitdocs``, not merely from this module's ``__all__``."""
    import pathlib

    import fitdocs

    src_root = pathlib.Path(fitdocs.__file__).resolve().parent
    offenders = [
        path
        for path in src_root.rglob("*.py")
        if "NotConfirmed" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
