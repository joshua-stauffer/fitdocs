"""Contract tests for :mod:`fitdocs.load.threshold.calculator`'s
``AthleteFieldDeclaration`` responsibility (task 3.1, design:
``AthleteFieldDeclaration``, Req 9.1, 9.2, 9.3).

``ATHLETE_FIELDS`` is a static seven-row table: the athlete inputs the
shipped prompt flow must collect to score the four supported disciplines
(running and cycling FTP, running and cycling LTHR, running threshold pace)
plus the two athlete-wide heart-rate quantities. It carries no Walk or Hike
LTHR (9.2) -- ``discipline.ANCHOR_PLANS`` already lets a Walk or Hike
heart-rate channel fall back to Running's LTHR, so a dedicated Walk/Hike
threshold field would only ever refine an anchor the chain already resolves.

Two pairs of rows (Running/Cycling FTP, Running/Cycling LTHR) share an
identical numeric range and ``kind``, and differ only in which discipline
their ``BenchmarkRef`` names -- exactly the shape a Run/Ride transposition
slips through unnoticed, so every field below is pinned by exact,
field-by-field equality (label, kind, minimum, maximum, help text, and the
full ``BenchmarkRef``), not by membership in a set. The headline invariant --
the declared set is exactly the quantities reachable through a non-empty
``ANCHOR_PLANS`` chain plus the two athlete-wide heart-rate quantities -- is
derived from the real ``discipline.ANCHOR_PLANS`` table so that a future
chain edit without a matching field declaration reds this suite directly,
with no local double-authored copy of the anchor policy to drift from it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import pytest

from fitdocs.benchmarks import ATHLETE_SCOPED, DISCIPLINE_SCOPED, BenchmarkKind
from fitdocs.load.threshold.calculator import ATHLETE_FIELDS, ThresholdCalculator
from fitdocs.load.threshold.discipline import ANCHOR_PLANS, AnchorPlan
from fitdocs.load.types import AthleteField, BenchmarkRef
from fitdocs.model import Sport

# ---------------------------------------------------------------------------
# The exact expected table, authored independently of calculator.py's private
# module-level constants so this file pins calculator.py's *values*, not its
# internal names.
# ---------------------------------------------------------------------------

_RUN_FTP = AthleteField(
    key="benchmarks.run.ftp_watts",
    label="Running FTP (W)",
    kind="int",
    minimum=50,
    maximum=600,
    help_text=(
        "Running functional threshold power in watts: the highest power "
        "output you can sustain for about an hour of running, typically "
        "measured with a foot pod or running-power device over a 20-60 "
        "minute time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RUN),
)

_RIDE_FTP = AthleteField(
    key="benchmarks.ride.ftp_watts",
    label="Cycling FTP (W)",
    kind="int",
    minimum=50,
    maximum=600,
    help_text=(
        "Cycling functional threshold power in watts: the highest power "
        "output you can sustain for about an hour of cycling, typically "
        "measured with a power meter over a 20-60 minute time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE),
)

_RUN_LTHR = AthleteField(
    key="benchmarks.run.lthr_bpm",
    label="Running LTHR (bpm)",
    kind="int",
    minimum=80,
    maximum=220,
    help_text=(
        "Running lactate threshold heart rate in beats per minute: the "
        "heart rate at your running lactate threshold, typically measured "
        "with a chest-strap monitor over a 20-30 minute running time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.LTHR_BPM, discipline=Sport.RUN),
)

_RIDE_LTHR = AthleteField(
    key="benchmarks.ride.lthr_bpm",
    label="Cycling LTHR (bpm)",
    kind="int",
    minimum=80,
    maximum=220,
    help_text=(
        "Cycling lactate threshold heart rate in beats per minute: the "
        "heart rate at your cycling lactate threshold, typically measured "
        "with a chest-strap monitor over a 20-30 minute cycling time trial."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.LTHR_BPM, discipline=Sport.RIDE),
)

_RUN_PACE = AthleteField(
    key="benchmarks.run.threshold_pace_s_per_km",
    label="Running threshold pace (s/km)",
    kind="float",
    minimum=120,
    maximum=900,
    help_text=(
        "Running threshold pace in seconds per kilometer: the pace you can "
        "sustain for about an hour of running, typically measured with a "
        "GPS watch over a 20-60 minute running time trial."
    ),
    benchmark=BenchmarkRef(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM, discipline=Sport.RUN
    ),
)

_MAX_HR = AthleteField(
    key="benchmarks.athlete.max_hr_bpm",
    label="Maximum heart rate (bpm)",
    kind="int",
    minimum=100,
    maximum=230,
    help_text=(
        "Your athlete-wide maximum heart rate in beats per minute, "
        "typically measured with a chest-strap monitor during an all-out "
        "effort or a graded exercise test, and not specific to running or "
        "cycling."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.MAX_HR_BPM, discipline=None),
)

_RESTING_HR = AthleteField(
    key="benchmarks.athlete.resting_hr_bpm",
    label="Resting heart rate (bpm)",
    kind="int",
    minimum=25,
    maximum=100,
    help_text=(
        "Your athlete-wide resting heart rate in beats per minute, "
        "typically measured with a chest-strap or wrist monitor immediately "
        "on waking, and not specific to running or cycling."
    ),
    benchmark=BenchmarkRef(kind=BenchmarkKind.RESTING_HR_BPM, discipline=None),
)

_EXPECTED_ORDER: tuple[AthleteField, ...] = (
    _RUN_FTP,
    _RIDE_FTP,
    _RUN_LTHR,
    _RIDE_LTHR,
    _RUN_PACE,
    _MAX_HR,
    _RESTING_HR,
)


class TestExactDeclaration:
    def test_exact_field_tuple_in_declaration_order(self) -> None:
        assert ATHLETE_FIELDS == _EXPECTED_ORDER

    def test_exact_count_is_seven(self) -> None:
        assert len(ATHLETE_FIELDS) == 7

    def test_required_athlete_fields_returns_the_same_static_tuple(self) -> None:
        calculator = ThresholdCalculator()
        assert calculator.required_athlete_fields() == ATHLETE_FIELDS
        # Called twice with no arguments -- static, not activity-dependent.
        first = calculator.required_athlete_fields()
        second = calculator.required_athlete_fields()
        assert first == second


class TestPerFieldPinning:
    """Every field pinned individually by attribute, not only via the whole-
    tuple equality above, so a failure names the exact row and attribute a
    reviewer must inspect."""

    # ``expected`` comes from ``_EXPECTED_ORDER``, authored independently of
    # ``ATHLETE_FIELDS`` above -- collection-safe. ``ATHLETE_FIELDS`` itself
    # is indexed lazily inside the test body (not in the argvalue list), so
    # a field removed from the declaration reds this named test with the
    # rest of the suite still collected and running, rather than aborting
    # collection with an opaque ``IndexError``.
    @pytest.mark.parametrize(
        "index,expected",
        list(enumerate(_EXPECTED_ORDER)),
        ids=[
            "run_ftp",
            "ride_ftp",
            "run_lthr",
            "ride_lthr",
            "run_pace",
            "max_hr",
            "resting_hr",
        ],
    )
    def test_row(self, index: int, expected: AthleteField) -> None:
        assert index < len(ATHLETE_FIELDS), (
            f"row {index} ({expected.key}) is no longer declared"
        )
        field = ATHLETE_FIELDS[index]
        assert field.key == expected.key
        assert field.label == expected.label
        assert field.kind == expected.kind
        assert field.minimum == expected.minimum
        assert field.maximum == expected.maximum
        assert field.help_text == expected.help_text
        assert field.benchmark == expected.benchmark


class TestRunRideTranspositionWithinASharedRangePair:
    """Probe 1: the two FTP rows and the two LTHR rows each share a range --
    prove a Run<->Ride swap within a pair is caught, not merely that some
    field exists with that range."""

    def test_run_ftp_discipline_is_run_not_ride(self) -> None:
        run_ftp = ATHLETE_FIELDS[0]
        assert run_ftp.benchmark is not None
        assert run_ftp.benchmark.discipline is Sport.RUN
        assert run_ftp.benchmark.discipline is not Sport.RIDE

    def test_ride_ftp_discipline_is_ride_not_run(self) -> None:
        ride_ftp = ATHLETE_FIELDS[1]
        assert ride_ftp.benchmark is not None
        assert ride_ftp.benchmark.discipline is Sport.RIDE
        assert ride_ftp.benchmark.discipline is not Sport.RUN

    def test_run_lthr_discipline_is_run_not_ride(self) -> None:
        run_lthr = ATHLETE_FIELDS[2]
        assert run_lthr.benchmark is not None
        assert run_lthr.benchmark.discipline is Sport.RUN
        assert run_lthr.benchmark.discipline is not Sport.RIDE

    def test_ride_lthr_discipline_is_ride_not_run(self) -> None:
        ride_lthr = ATHLETE_FIELDS[3]
        assert ride_lthr.benchmark is not None
        assert ride_lthr.benchmark.discipline is Sport.RIDE
        assert ride_lthr.benchmark.discipline is not Sport.RUN


class TestKindIsPinnedPerField:
    """Probe 2: five of seven rows are ``int``, one is ``float`` -- pin each
    independently, including a distinct positive check that the float row
    really is ``"float"`` and not merely not-``"int"``."""

    def test_int_fields(self) -> None:
        int_fields = (
            ATHLETE_FIELDS[0],
            ATHLETE_FIELDS[1],
            ATHLETE_FIELDS[2],
            ATHLETE_FIELDS[3],
            ATHLETE_FIELDS[5],
            ATHLETE_FIELDS[6],
        )
        for field in int_fields:
            assert field.kind == "int"

    def test_threshold_pace_is_float(self) -> None:
        assert ATHLETE_FIELDS[4].kind == "float"

    def test_exactly_one_float_field(self) -> None:
        kinds = [field.kind for field in ATHLETE_FIELDS]
        assert kinds.count("float") == 1
        assert kinds.count("int") == 6


class TestRangeBoundsPinning:
    """Probe 3: ranges are same-typed numbers, easy to transpose -- prove
    min/max swap and cross-row range swap both red, and that ``kind`` is
    checked as the declared Literal rather than inferred from
    ``50 == 50.0``."""

    def test_minimum_is_strictly_less_than_maximum_for_every_row(self) -> None:
        for field in ATHLETE_FIELDS:
            assert field.minimum is not None
            assert field.maximum is not None
            assert field.minimum < field.maximum

    def test_ftp_range_is_50_to_600(self) -> None:
        for field in (ATHLETE_FIELDS[0], ATHLETE_FIELDS[1]):
            assert field.minimum == 50
            assert field.maximum == 600

    def test_lthr_range_is_80_to_220(self) -> None:
        for field in (ATHLETE_FIELDS[2], ATHLETE_FIELDS[3]):
            assert field.minimum == 80
            assert field.maximum == 220

    def test_threshold_pace_range_is_120_to_900(self) -> None:
        field = ATHLETE_FIELDS[4]
        assert field.minimum == 120
        assert field.maximum == 900

    def test_max_hr_range_is_100_to_230(self) -> None:
        field = ATHLETE_FIELDS[5]
        assert field.minimum == 100
        assert field.maximum == 230

    def test_resting_hr_range_is_25_to_100(self) -> None:
        field = ATHLETE_FIELDS[6]
        assert field.minimum == 25
        assert field.maximum == 100

    def test_declared_kind_is_not_inferred_from_bound_python_type(self) -> None:
        # 50 == 50.0 in Python, so a bound-type check alone cannot tell
        # "int" from "float" apart; the declared Literal on the field must
        # be checked directly.
        run_ftp = ATHLETE_FIELDS[0]
        run_pace = ATHLETE_FIELDS[4]
        assert run_ftp.minimum == 50 == 50.0
        assert run_ftp.kind == "int"
        assert run_pace.kind == "float"
        assert run_ftp.kind != run_pace.kind

    def test_the_seven_rows_use_exactly_five_distinct_ranges_with_the_two_shared_pairs(
        self,
    ) -> None:
        # Guards a cross-row range swap that lands on a range no other row
        # uses (e.g. max-hr's 100-230 swapped onto resting-hr).
        ranges = [(field.minimum, field.maximum) for field in ATHLETE_FIELDS]
        distinct_ranges = {
            (ATHLETE_FIELDS[0].minimum, ATHLETE_FIELDS[0].maximum),
            (ATHLETE_FIELDS[2].minimum, ATHLETE_FIELDS[2].maximum),
            (ATHLETE_FIELDS[4].minimum, ATHLETE_FIELDS[4].maximum),
            (ATHLETE_FIELDS[5].minimum, ATHLETE_FIELDS[5].maximum),
            (ATHLETE_FIELDS[6].minimum, ATHLETE_FIELDS[6].maximum),
        }
        # FTP and LTHR each appear twice (shared by discipline), the other
        # three ranges are unique -- five distinct range values in total.
        assert len(distinct_ranges) == 5
        assert ranges[0] == ranges[1]  # the two FTP rows share a range
        assert ranges[2] == ranges[3]  # the two LTHR rows share a range


class TestNoWalkOrHikeThresholdHeartRate:
    """Probe 5 (Req 9.2): assert the exact count and exact set of
    (kind, discipline) pairs declared, not mere absence of a "Walk"/"Hike"
    substring: no help text in the table mentions walking or hiking either
    way, so a `"walk" not in help_text` check would pass vacuously and prove
    nothing about whether a Walk/Hike field is actually declared."""

    def test_no_field_carries_walk_or_hike_discipline(self) -> None:
        disciplines = {
            field.benchmark.discipline
            for field in ATHLETE_FIELDS
            if field.benchmark is not None
        }
        assert Sport.WALK not in disciplines
        assert Sport.HIKE not in disciplines
        assert disciplines == {Sport.RUN, Sport.RIDE, None}

    def test_no_field_declares_lthr_for_walk_or_hike_specifically(self) -> None:
        lthr_disciplines = {
            field.benchmark.discipline
            for field in ATHLETE_FIELDS
            if field.benchmark is not None
            and field.benchmark.kind is BenchmarkKind.LTHR_BPM
        }
        assert lthr_disciplines == {Sport.RUN, Sport.RIDE}
        assert len(lthr_disciplines) == 2


class TestHelpTextNamesDisciplineAndMeasurement:
    """Probe 6 (Req 9.3): help text must both name the discipline plainly and
    say how the value is measured. Checked against ``help_text`` alone
    (never ``label``, which trivially contains the discipline for each of
    the five discipline-scoped rows), so emptying ``help_text`` -- leaving
    only the label -- reds."""

    # ``index`` is resolved against ``ATHLETE_FIELDS`` lazily in the test
    # body, not in the argvalue list, so this parametrize is collection-safe
    # even if a field is removed from the declaration (see ``test_row``
    # above for the same pattern and its rationale).
    @pytest.mark.parametrize(
        "index,discipline_token",
        [
            (0, "running"),
            (1, "cycling"),
            (2, "running"),
            (3, "cycling"),
            (4, "running"),
        ],
        ids=["run_ftp", "ride_ftp", "run_lthr", "ride_lthr", "run_pace"],
    )
    def test_discipline_scoped_help_text_names_its_discipline(
        self, index: int, discipline_token: str
    ) -> None:
        assert index < len(ATHLETE_FIELDS), f"row {index} is no longer declared"
        field = ATHLETE_FIELDS[index]
        assert field.help_text is not None
        lowered = field.help_text.lower()
        assert discipline_token in lowered
        assert "measured" in lowered

    def test_athlete_wide_help_text_states_not_discipline_specific(self) -> None:
        for field in (ATHLETE_FIELDS[5], ATHLETE_FIELDS[6]):
            assert field.help_text is not None
            lowered = field.help_text.lower()
            assert "measured" in lowered
            assert "not specific to running or cycling" in lowered

    def test_run_ftp_help_text_does_not_name_cycling(self) -> None:
        # Guards a help-text swap between the two FTP rows: running FTP's
        # own help text must not itself describe cycling.
        assert "cycling" not in ATHLETE_FIELDS[0].help_text.lower()

    def test_ride_ftp_help_text_does_not_name_running(self) -> None:
        assert "running" not in ATHLETE_FIELDS[1].help_text.lower()


class TestBenchmarkRefScopeAgreement:
    """Probe 7: the two athlete-wide rows carry ``discipline=None``; the five
    discipline-scoped rows do not. Checked against ``benchmarks.py``'s own
    ``ATHLETE_SCOPED``/``DISCIPLINE_SCOPED`` sets (not a hand-copied list),
    and via a direct assertion so a mismatch fails in this test, not by
    ``BenchmarkSet``/``BenchmarkRef`` raising somewhere else."""

    def test_athlete_scoped_kinds_have_no_discipline(self) -> None:
        for field in ATHLETE_FIELDS:
            assert field.benchmark is not None
            if field.benchmark.kind in ATHLETE_SCOPED:
                assert field.benchmark.discipline is None

    def test_discipline_scoped_kinds_have_a_discipline(self) -> None:
        for field in ATHLETE_FIELDS:
            assert field.benchmark is not None
            if field.benchmark.kind in DISCIPLINE_SCOPED:
                assert field.benchmark.discipline is not None

    def test_exactly_two_athlete_scoped_and_five_discipline_scoped_fields(self) -> None:
        athlete_scoped_count = sum(
            1
            for field in ATHLETE_FIELDS
            if field.benchmark is not None and field.benchmark.kind in ATHLETE_SCOPED
        )
        discipline_scoped_count = sum(
            1
            for field in ATHLETE_FIELDS
            if field.benchmark is not None and field.benchmark.kind in DISCIPLINE_SCOPED
        )
        assert athlete_scoped_count == 2
        assert discipline_scoped_count == 5


class TestEveryFieldCarriesABenchmarkRef:
    def test_every_field_has_a_benchmark(self) -> None:
        for field in ATHLETE_FIELDS:
            assert field.benchmark is not None
            assert isinstance(field.benchmark, BenchmarkRef)

    def test_every_field_key_identifies_its_benchmark_table(self) -> None:
        # AthleteField.key identifies the *table* the entry lives in
        # (benchmarks.<scope>.<kind>), not a flat value path.
        for field in ATHLETE_FIELDS:
            assert field.benchmark is not None
            scope = (
                field.benchmark.discipline.value.lower()
                if field.benchmark.discipline is not None
                else "athlete"
            )
            assert field.key == f"benchmarks.{scope}.{field.benchmark.kind.value}"


# ---------------------------------------------------------------------------
# Probe 4 / headline invariant: the declared set is exactly the quantities
# reachable through a non-empty ANCHOR_PLANS chain (its last, guaranteed-to-
# resolve entry) plus the two athlete-wide heart-rate quantities.
# ---------------------------------------------------------------------------

_CHAIN_KIND_BY_ATTR: Mapping[str, BenchmarkKind] = {
    "ftp": BenchmarkKind.FTP_WATTS,
    "lthr": BenchmarkKind.LTHR_BPM,
    "threshold_pace": BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
}


def _reachable_benchmark_refs(
    plans: Mapping[Sport, AnchorPlan],
) -> frozenset[tuple[BenchmarkKind, Sport | None]]:
    """The (kind, discipline) pairs a non-empty anchor chain in ``plans``
    guarantees resolvable: the *last* entry of each non-empty chain, since
    every earlier entry is an optional refinement the chain can already fall
    back past (design.md ``AthleteFieldDeclaration``, Req 9.2)."""
    reachable: set[tuple[BenchmarkKind, Sport | None]] = set()
    for plan in plans.values():
        for attr, kind in _CHAIN_KIND_BY_ATTR.items():
            chain: tuple[Sport, ...] = getattr(plan, attr)
            if chain:
                reachable.add((kind, chain[-1]))
    return frozenset(reachable)


_ATHLETE_WIDE_REFS: frozenset[tuple[BenchmarkKind, Sport | None]] = frozenset(
    {
        (BenchmarkKind.MAX_HR_BPM, None),
        (BenchmarkKind.RESTING_HR_BPM, None),
    }
)


class TestAnchorPlanInvariant:
    def test_chain_kind_map_covers_every_anchor_plan_field(self) -> None:
        # ``_reachable_benchmark_refs`` only walks the attrs named in
        # ``_CHAIN_KIND_BY_ATTR``; if ``AnchorPlan`` grows a fourth chain
        # quantity that map is not updated for, the helper silently ignores
        # it and the invariant below stays green. Derive the expected attr
        # set from the dataclass itself so a new field reds here.
        anchor_plan_fields = {field.name for field in dataclasses.fields(AnchorPlan)}
        assert set(_CHAIN_KIND_BY_ATTR) == anchor_plan_fields

    def test_declared_set_matches_anchor_plan_derived_set(self) -> None:
        declared = frozenset(
            (field.benchmark.kind, field.benchmark.discipline)
            for field in ATHLETE_FIELDS
            if field.benchmark is not None
        )
        expected = _reachable_benchmark_refs(ANCHOR_PLANS) | _ATHLETE_WIDE_REFS
        assert declared == expected
        assert len(declared) == 7

    def test_helper_excludes_walk_and_hike_own_chain_entries(self) -> None:
        # Sanity check on the helper itself: Walk's and Hike's own LTHR
        # chains start with Walk/Hike but *end* in Run, so the last-entry
        # rule the invariant above relies on must not surface a
        # Walk/Hike-scoped LTHR pair.
        reachable = _reachable_benchmark_refs(ANCHOR_PLANS)
        assert (BenchmarkKind.LTHR_BPM, Sport.WALK) not in reachable
        assert (BenchmarkKind.LTHR_BPM, Sport.HIKE) not in reachable
        assert (BenchmarkKind.LTHR_BPM, Sport.RUN) in reachable

    def test_helper_would_require_a_new_chain_terminus_if_one_were_added(
        self,
    ) -> None:
        # Models "add a chain entry without declaring its field" locally
        # (without mutating the real, shared ANCHOR_PLANS table): a
        # hypothetical Walk power chain terminating on Walk itself is not
        # among today's declared fields, so the helper's output for that
        # hypothetical table must diverge from the real declared set --
        # proving the derivation is sensitive to a new chain terminus, not
        # merely a passthrough of whatever ATHLETE_FIELDS already says.
        hypothetical_plans = dict(ANCHOR_PLANS)
        hypothetical_plans[Sport.WALK] = dataclasses.replace(
            hypothetical_plans[Sport.WALK], ftp=(Sport.WALK,)
        )
        hypothetical_reachable = _reachable_benchmark_refs(hypothetical_plans)
        declared = frozenset(
            (field.benchmark.kind, field.benchmark.discipline)
            for field in ATHLETE_FIELDS
            if field.benchmark is not None
        )
        assert hypothetical_reachable != _reachable_benchmark_refs(ANCHOR_PLANS)
        assert (BenchmarkKind.FTP_WATTS, Sport.WALK) in hypothetical_reachable
        assert (BenchmarkKind.FTP_WATTS, Sport.WALK) not in declared


class TestNoNonBoundaryMembers:
    """The declaration boundary adds no `compute`, `supports`, or contract
    attribute -- those are later tasks' responsibility, sharing this file."""

    def test_calculator_has_no_compute_yet(self) -> None:
        assert not hasattr(ThresholdCalculator, "compute")

    def test_calculator_has_no_supports_yet(self) -> None:
        assert not hasattr(ThresholdCalculator, "supports")

    def test_calculator_is_a_frozen_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ThresholdCalculator)
        instance = ThresholdCalculator()
        with pytest.raises(dataclasses.FrozenInstanceError):
            instance.some_new_attribute = "not allowed"  # type: ignore[attr-defined]
