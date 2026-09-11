"""Tests for `fitdocs.performance.derive` (design: DerivationLeaf, Req
2.1-2.8, 8.7).

`tests/performance/test_derive.py` is created by task 3.1 with the
"threshold pace" section below; tasks 3.2, 3.3 and 3.4 append their own
headed sections and edit no other.
"""

from __future__ import annotations

from datetime import date

import pytest

from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.contract import EffortKind, EffortTag
from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
)
from fitdocs.performance import derive, models, sources
from fitdocs.performance.types import (
    DeclineReason,
    DerivationDeclined,
    DerivationMethod,
    DerivedBenchmark,
)

# =============================================================================
# threshold pace (task 3.1)
# =============================================================================


def _summary(
    *, total_distance_m: float | None, total_elapsed_time_s: float | None
) -> SessionSummary:
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=total_elapsed_time_s,
        total_timer_time_s=None,
        total_distance_m=total_distance_m,
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


def _run_activity(
    *,
    recorded_distance_m: float | None,
    recorded_time_s: float | None,
) -> Activity:
    empty_samples = Samples(
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
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="1" * 64, source_path=None, decode_errors=()),
        sport=Sport.RUN,
        modality=Modality.RUN,
        is_indoor=False,
        start_time=None,
        summary=_summary(
            total_distance_m=recorded_distance_m,
            total_elapsed_time_s=recorded_time_s,
        ),
        laps=(),
        samples=empty_samples,
        sets=(),
        devices=(),
    )


def _tag(
    *,
    kind: EffortKind = EffortKind.RACE,
    distance_m: float | None = None,
    time_s: float | None = None,
) -> EffortTag:
    return EffortTag(kind=kind, distance_m=distance_m, time_s=time_s, event=None)


_ON = date(2024, 3, 17)
_DOCUMENT = "workouts/2024-03-17-race.md"


def test_official_pair_anchors_when_both_present_and_differs_from_recorded() -> None:
    """Official beats recorded (Req 2.2, 2.4): the official pair (5000 m,
    1200 s) and the recorded pair (10000 m, 3000 s) are deliberately
    different distances *and* different times, so they solve to different
    paces -- the fixture cannot be satisfied by either rule alone.

    Mutation this dies on: preferring the recorded pair over the official
    pair (swap which pair feeds the model) -- the derived value would then
    equal the recorded-pair pace instead, and the assertion below on the
    exact official-pair value would go red.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=3000.0)
    tag = _tag(distance_m=5000.0, time_s=1200.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)
    official_pace = models.threshold_pace_s_per_km(distance_m=5000.0, time_s=1200.0)
    recorded_pace = models.threshold_pace_s_per_km(distance_m=10000.0, time_s=3000.0)
    assert official_pace is not None and recorded_pace is not None
    # The two candidate answers must actually differ, or this fixture would
    # not discriminate between "official" and "recorded" at all.
    assert official_pace != recorded_pace
    assert outcome.value == pytest.approx(official_pace)
    assert outcome.value != pytest.approx(recorded_pace)
    assert outcome.inputs == (
        "official distance 5000 m, official time 1200 s (effort tag)"
    )


def test_recorded_pair_anchors_the_value_when_tag_carries_neither() -> None:
    """No official pair at all (Req 2.3): falls back to the activity's
    recorded distance and recorded elapsed time, and says so in `inputs`.
    """
    activity = _run_activity(recorded_distance_m=8000.0, recorded_time_s=2000.0)
    tag = _tag(distance_m=None, time_s=None)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)
    expected_pace = models.threshold_pace_s_per_km(distance_m=8000.0, time_s=2000.0)
    assert expected_pace is not None
    assert outcome.value == pytest.approx(expected_pace)
    assert outcome.inputs == (
        "recorded distance 8000 m, recorded elapsed time 2000 s (activity)"
    )


def test_mixed_case_uses_recorded_distance_with_the_official_time() -> None:
    """The tag carries `time_s` alone (Req 2.3, 2.4): the recorded distance
    is used, paired with the tag's *official* time -- not the activity's own
    recorded elapsed time, which is deliberately set to a different value
    here so the two are never confounded.

    Mutation this dies on: using the recorded elapsed time instead of the
    tag's official time in this branch (i.e. falling through to the fully
    recorded pair) -- the derived value would then equal the
    fully-recorded-pair pace, and the exact-value assertion below would go
    red.
    """
    activity = _run_activity(recorded_distance_m=6000.0, recorded_time_s=9999.0)
    tag = _tag(distance_m=None, time_s=1500.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)
    mixed_pace = models.threshold_pace_s_per_km(distance_m=6000.0, time_s=1500.0)
    fully_recorded_pace = models.threshold_pace_s_per_km(
        distance_m=6000.0, time_s=9999.0
    )
    assert mixed_pace is not None and fully_recorded_pace is not None
    assert mixed_pace != fully_recorded_pace
    assert outcome.value == pytest.approx(mixed_pace)
    assert outcome.value != pytest.approx(fully_recorded_pace)
    assert "recorded distance 6000 m (activity)" in outcome.inputs
    assert "official time 1500 s (effort tag)" in outcome.inputs
    # Falsity in the starting state / not confounded with the fully-recorded
    # wording this test must NOT produce:
    assert "recorded elapsed time" not in outcome.inputs


@pytest.mark.parametrize(
    ("distance_m", "time_s", "expected_substring"),
    [
        (
            None,
            1200.0,
            "distance (None m)",
        ),  # missing distance, fully recorded fallback
        (10000.0, None, "time (None s)"),  # missing time, fully recorded fallback
        (0.0, 1200.0, "distance (0 m)"),  # non-positive distance
        (10000.0, float("inf"), "time (inf s)"),  # non-finite time
    ],
)
def test_missing_or_invalid_recorded_input_declines_missing_input(
    distance_m: float | None, time_s: float | None, expected_substring: str
) -> None:
    """Req 2.6: `detail` names the specific missing or invalid input, not
    merely a non-empty string.

    Mutation this dies on: replacing `detail` with a constant non-empty
    string -- `detail != ""` stays green but `expected_substring in
    outcome.detail` goes red, one case per input.
    """
    activity = _run_activity(recorded_distance_m=distance_m, recorded_time_s=time_s)
    tag = _tag(distance_m=None, time_s=None)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.MISSING_INPUT
    assert outcome.detail != ""
    assert expected_substring in outcome.detail


def test_below_validity_window_declines_naming_duration_and_both_bounds() -> None:
    """A 200 s race is below Riegel's published lower bound (Req 2.5):
    declines, names the observed duration and both bounds, and never
    clamps (the outcome carries no derived value at all). `required` names
    the lower bound specifically, since that is the bound actually crossed.
    """
    activity = _run_activity(recorded_distance_m=None, recorded_time_s=None)
    tag = _tag(distance_m=1000.0, time_s=200.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.OUTSIDE_VALIDITY_WINDOW
    min_s = sources.RIEGEL_MIN_DURATION_S.value
    max_s = sources.RIEGEL_MAX_DURATION_S.value
    assert f"{200.0:g}" in outcome.detail
    assert f"{min_s:g}" in outcome.detail
    assert f"{max_s:g}" in outcome.detail
    # required names the bound actually crossed (the lower one here), not
    # the bound the duration already satisfies.
    assert outcome.required == pytest.approx(min_s)
    assert outcome.required != pytest.approx(max_s)


def test_above_validity_window_declines_naming_duration_and_both_bounds() -> None:
    """A 4-hour (14400 s) race is above Riegel's published upper bound (Req
    2.5): declines the same way, and the raw observed duration -- never a
    value clamped to the bound -- is what the outcome carries. `required`
    names the upper bound specifically, since that is the bound crossed.
    """
    activity = _run_activity(recorded_distance_m=None, recorded_time_s=None)
    tag = _tag(distance_m=42195.0, time_s=14400.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.OUTSIDE_VALIDITY_WINDOW
    min_s = sources.RIEGEL_MIN_DURATION_S.value
    max_s = sources.RIEGEL_MAX_DURATION_S.value
    assert f"{14400.0:g}" in outcome.detail
    assert f"{min_s:g}" in outcome.detail
    assert f"{max_s:g}" in outcome.detail
    # Never clamped: the observed value on the outcome is the raw 14400 s,
    # not the 13800 s upper bound.
    assert outcome.observed == pytest.approx(14400.0)
    assert outcome.observed != pytest.approx(max_s)
    # required names the bound actually crossed (the upper one here), not
    # the bound the duration already satisfies.
    assert outcome.required == pytest.approx(max_s)
    assert outcome.required != pytest.approx(min_s)


@pytest.mark.parametrize(
    ("distance_m", "time_s"),
    [
        (1000.0, "min"),  # exactly the lower bound
        (42195.0, "max"),  # exactly the upper bound
    ],
)
def test_duration_exactly_at_bounds_is_inside_the_window_not_declined(
    distance_m: float, time_s: str
) -> None:
    """The window is closed (inclusive at both ends): a duration exactly at
    either published bound derives rather than declining.

    Mutation this dies on: flipping the lower-bound comparison from `<=` to
    `<` reds the `min` case; flipping the upper-bound comparison from `<=`
    to `<` reds the `max` case. A single fixture at the lower bound alone
    cannot catch an upper-bound flip, hence both cases here.
    """
    bound_s = (
        sources.RIEGEL_MIN_DURATION_S.value
        if time_s == "min"
        else sources.RIEGEL_MAX_DURATION_S.value
    )
    activity = _run_activity(recorded_distance_m=None, recorded_time_s=None)
    tag = _tag(distance_m=distance_m, time_s=bound_s)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)


def test_official_time_inside_window_derives_even_when_recorded_time_is_outside() -> (
    None
):
    """The official pair (Req 2.2) governs the validity-window gate, not the
    activity's recorded elapsed time: the official pair here (5000 m,
    1200 s) is inside the window, but the recorded pair (10000 m, 14400 s)
    is outside it.

    Mutation this dies on: gating on `activity.summary.total_elapsed_time_s`
    instead of the solved `time_s` -- the recorded 14400 s is outside the
    window, so a mis-gated implementation would wrongly decline
    `OUTSIDE_VALIDITY_WINDOW` here instead of deriving.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=14400.0)
    tag = _tag(distance_m=5000.0, time_s=1200.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.inputs == (
        "official distance 5000 m, official time 1200 s (effort tag)"
    )


def test_official_time_outside_window_declines_even_when_recorded_time_is_inside() -> (
    None
):
    """Mirror of the case above: the official pair (5000 m, 14400 s) is
    outside the window, but the recorded pair (10000 m, 1200 s) is inside
    it. The gate must still act on the official (solved) time.

    Mutation this dies on: gating on `activity.summary.total_elapsed_time_s`
    instead of the solved `time_s` -- the recorded 1200 s is inside the
    window, so a mis-gated implementation would wrongly derive instead of
    declining `OUTSIDE_VALIDITY_WINDOW` with `observed == 14400`.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=1200.0)
    tag = _tag(distance_m=5000.0, time_s=14400.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.OUTSIDE_VALIDITY_WINDOW
    assert outcome.observed == pytest.approx(14400.0)


@pytest.mark.parametrize("kind", [EffortKind.TEST, EffortKind.HARD])
def test_non_race_kind_declines_effort_kind_not_used(kind: EffortKind) -> None:
    """A running test or hard effort yields no threshold pace (Req 2.8): the
    routing table names pace race-only for running.

    Mutation this dies on: treating a `test`/`hard` kind as `race` (dropping
    or widening the kind check) -- this fixture, which supplies a perfectly
    valid official pair, would then derive a value instead of declining.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=3000.0)
    tag = _tag(kind=kind, distance_m=5000.0, time_s=1200.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.EFFORT_KIND_NOT_USED
    assert outcome.detail != ""
    # The method is still the race-equivalence model even on a decline: the
    # leaf always attempts one method, it just refuses to apply it here.
    assert outcome.method is DerivationMethod.RIEGEL_RACE_EQUIVALENCE


def test_undated_document_declines_when_on_is_none() -> None:
    """`on is None` declines `UNDATED_DOCUMENT` (Req 7.6) even though every
    other input is a perfectly valid official pair -- the date gate is
    unconditional.

    Mutation this dies on: dating from `date.today()` instead of declining
    -- this fixture would then produce a `DerivedBenchmark` whose
    `measured_on` is today's date rather than an outcome with no value at
    all.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=3000.0)
    tag = _tag(distance_m=5000.0, time_s=1200.0)

    outcome = derive.threshold_pace(activity, tag, on=None, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.UNDATED_DOCUMENT
    assert _DOCUMENT in outcome.detail


def test_undated_document_gate_precedes_the_kind_gate() -> None:
    """The undated gate runs before the kind gate (design DerivationLeaf
    postcondition): a `hard`-tagged effort -- which would otherwise decline
    `EFFORT_KIND_NOT_USED` -- declines `UNDATED_DOCUMENT` when `on is None`,
    because the date gate is checked unconditionally, first.

    Mutation this dies on: swapping the two gates back (kind check before
    the `on is None` check) -- this `hard`-tagged, undated fixture would
    then decline `EFFORT_KIND_NOT_USED` instead.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=3000.0)
    tag = _tag(kind=EffortKind.HARD, distance_m=5000.0, time_s=1200.0)

    outcome = derive.threshold_pace(activity, tag, on=None, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is DeclineReason.UNDATED_DOCUMENT


def test_derived_value_is_dated_at_the_passed_on_date_not_the_wall_clock() -> None:
    """The derived value's `measured_on` is exactly the `on` argument -- a
    fixed date far from today, so a `date.today()` implementation could
    never accidentally match it.

    Mutation this dies on: dating from `date.today()` instead of `on`.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=3000.0)
    tag = _tag(distance_m=5000.0, time_s=1200.0)
    fixed_on = date(2019, 6, 1)
    assert fixed_on != date.today()

    outcome = derive.threshold_pace(activity, tag, on=fixed_on, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.measured_on == fixed_on


def test_derived_value_carries_the_governing_citation_key_and_method() -> None:
    """Req 8.7: the governing citation key is in `citation_key`; the method
    is the closed vocabulary member for the race-equivalence model; the
    kind, discipline and document match the call; `note` names the governing
    model and the one-hour solve target it was solved for.
    """
    activity = _run_activity(recorded_distance_m=10000.0, recorded_time_s=3000.0)
    tag = _tag(distance_m=5000.0, time_s=1200.0)

    outcome = derive.threshold_pace(activity, tag, on=_ON, document=_DOCUMENT)

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.citation_key == sources.RIEGEL_1981.key
    assert outcome.citation_key == "riegel_1981"
    assert outcome.method is DerivationMethod.RIEGEL_RACE_EQUIVALENCE
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.discipline is Sport.RUN
    assert outcome.document == _DOCUMENT
    assert outcome.note != ""
    assert "Riegel" in outcome.note
    assert "RIEGEL_SOLVE_TARGET_S" in outcome.note


@pytest.mark.parametrize(
    (
        "kind",
        "on",
        "distance_m",
        "time_s",
        "recorded_distance_m",
        "recorded_time_s",
        "expected_reason",
    ),
    [
        pytest.param(
            EffortKind.HARD,
            _ON,
            5000.0,
            1200.0,
            10000.0,
            3000.0,
            DeclineReason.EFFORT_KIND_NOT_USED,
            id="kind",
        ),
        pytest.param(
            EffortKind.RACE,
            None,
            5000.0,
            1200.0,
            10000.0,
            3000.0,
            DeclineReason.UNDATED_DOCUMENT,
            id="undated",
        ),
        pytest.param(
            EffortKind.RACE,
            _ON,
            None,
            None,
            None,
            None,
            DeclineReason.MISSING_INPUT,
            id="missing_input",
        ),
        pytest.param(
            EffortKind.RACE,
            _ON,
            1000.0,
            200.0,
            None,
            None,
            DeclineReason.OUTSIDE_VALIDITY_WINDOW,
            id="window",
        ),
    ],
)
def test_never_raises_on_a_decline_path(
    kind: EffortKind,
    on: date | None,
    distance_m: float | None,
    time_s: float | None,
    recorded_distance_m: float | None,
    recorded_time_s: float | None,
    expected_reason: DeclineReason,
) -> None:
    """Sweep over every reachable decline reason on this leaf (kind,
    undated, missing input, window): each returns rather than raises, and
    each carries a non-empty `detail` (design invariant).

    Mutation this dies on: any single decline branch raising instead of
    returning would fail its own parametrize case here; a wrong reason on
    any one branch fails `expected_reason` for that case specifically.
    """
    activity = _run_activity(
        recorded_distance_m=recorded_distance_m, recorded_time_s=recorded_time_s
    )
    tag = _tag(kind=kind, distance_m=distance_m, time_s=time_s)

    outcome = derive.threshold_pace(activity, tag, on=on, document=_DOCUMENT)

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    assert outcome.reason is expected_reason
    assert outcome.detail != ""
    assert outcome.method is DerivationMethod.RIEGEL_RACE_EQUIVALENCE
