"""Tests for `fitdocs.performance.derive` (design: DerivationLeaf, Req
2.1-2.8, 3.1-3.9, 8.7).

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
from fitdocs.load.channels.types import SufficiencySettings
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


# =============================================================================
# lactate-threshold heart rate (task 3.2)
# =============================================================================


def _hr_samples(
    time_s: tuple[float, ...], heart_rate_bpm: tuple[int | None, ...]
) -> Samples:
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm,
        power_w=(),
        cadence_rpm=(),
        speed_mps=(),
        distance_m=(),
        altitude_m=(),
        latitude_deg=(),
        longitude_deg=(),
        temperature_c=(),
    )


def _hr_activity(
    *,
    sport: Sport,
    modality: Modality,
    samples: Samples,
) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="2" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(total_distance_m=None, total_elapsed_time_s=None),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


_HR_ON = date(2024, 5, 1)
_HR_DOCUMENT = "workouts/2024-05-01-lthr-test.md"
_DEFAULT_SUFFICIENCY = SufficiencySettings()


def test_full_coverage_forty_minute_effort_derives_a_whole_number() -> None:
    """A 40-minute (2400 s) effort with full heart-rate coverage derives
    (Req 3.1). The two half-weighted segments (148 bpm, 149 bpm) average to
    exactly 148.5 -- a tie that Python's banker's `round()` would send to
    148 (the even neighbour) while the away-from-zero rule sends it to 149,
    so this fixture also discriminates `whole_bpm` from a bare `round()`.

    Mutation this dies on: `round()` instead of `models.whole_bpm` (the
    value would be `148` instead of `149`).
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (148, 149, 149))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.value == 149.0
    assert outcome.value != 148.0
    assert float(outcome.value).is_integer()
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.discipline is Sport.RUN
    assert outcome.method is DerivationMethod.SUSTAINED_EFFORT_MEAN_HR
    assert outcome.measured_on == _HR_ON
    assert outcome.citation_key == sources.LTHR_DURATION_WINDOW_CHOICE.key
    assert outcome.note != ""
    assert f"{2400.0:g}" in outcome.inputs


def test_derived_value_is_the_time_weighted_mean_not_the_sample_count_mean() -> None:
    """Req 3.2: the derived number is the time-weighted mean over the whole
    effort, not an unweighted sample-count mean. The two candidates are
    computed independently here and asserted unequal before either is
    compared against the outcome (fixture discrimination): a heavy 2000 s
    interval at 100 bpm followed by a light 400 s interval at 200 bpm
    time-weights to ~116.67 bpm, while the plain arithmetic mean of the
    three recorded values is ~133.33 bpm.

    Mutation this dies on: computing an unweighted sample-count mean
    instead of `models.time_weighted_mean` -- the outcome would then equal
    the sample-count candidate instead.
    """
    time_s = (0.0, 2000.0, 2400.0)
    values: tuple[int | None, ...] = (100, 200, 100)
    samples = _hr_samples(time_s, values)

    time_weighted = models.time_weighted_mean(samples, values)
    sample_count_mean = sum(v for v in values if v is not None) / len(
        [v for v in values if v is not None]
    )
    assert time_weighted is not None
    # The two candidates must actually differ, or this fixture would not
    # discriminate between the two averaging rules at all.
    assert time_weighted != pytest.approx(sample_count_mean)

    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.HARD)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.value == pytest.approx(models.whole_bpm(time_weighted))
    assert outcome.value != pytest.approx(models.whole_bpm(sample_count_mean))


def test_derived_value_is_the_whole_effort_average_not_the_final_third() -> None:
    """Req 3.2: never a selected portion, never a leading/trailing
    segment discarded. A 3000 s effort in three equal 1000 s segments at
    100/150/200 bpm time-weights to exactly 150 bpm over the whole effort,
    while averaging only the final third would give 200 bpm.

    Mutation this dies on: averaging only the final third of the effort --
    the outcome would then equal `200.0` instead of `150.0`.

    Also pins the note's whole-effort statement (Req 3.9): it must read as
    covering the whole recorded effort, never as a discarded-segment
    protocol.

    Mutation this dies on: the note reading "mean over the final 20
    minutes" instead of naming the whole recorded effort.
    """
    time_s = (0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0)
    values: tuple[int | None, ...] = (100, 100, 150, 150, 200, 200, 200)
    samples = _hr_samples(time_s, values)
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.TEST)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.value == 150.0
    assert outcome.value != 200.0
    assert "whole recorded effort" in outcome.note
    assert "final 20 minutes" not in outcome.note


def test_ride_derives_under_the_ride_discipline_not_run() -> None:
    """Req 3.8: recorded under the activity's own discipline. A cycling
    activity derives under `Sport.RIDE`, never borrowed across disciplines
    into `Sport.RUN`.

    Mutation this dies on: treating `RIDE` as `RUN` (hard-coding
    `Sport.RUN` as the discipline) -- `outcome.discipline` would then equal
    `Sport.RUN` instead.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RIDE, modality=Modality.BIKE, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.discipline is Sport.RIDE


def test_ninety_minute_effort_declines_outside_the_validity_window() -> None:
    """A 90-minute (5400 s) effort with full coverage is above the LTHR
    window's upper bound (Req 3.3): declines, names the observed duration
    and both bounds, and never clamps. `required` names the upper bound
    specifically.
    """
    samples = _hr_samples((0.0, 5400.0), (150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.OUTSIDE_VALIDITY_WINDOW
    min_s = sources.LTHR_MIN_DURATION_S.value
    max_s = sources.LTHR_MAX_DURATION_S.value
    assert f"{5400.0:g}" in outcome.detail
    assert f"{min_s:g}" in outcome.detail
    assert f"{max_s:g}" in outcome.detail
    assert outcome.observed == pytest.approx(5400.0)
    assert outcome.required == pytest.approx(max_s)
    assert outcome.required != pytest.approx(min_s)


def test_window_is_judged_on_the_recorded_span_not_the_official_time() -> None:
    """Req 3.3 names the *recorded* duration. Here the tag's official time
    sits exactly on the window's lower bound and the recorded span agrees
    with it within the tolerance, so the span gate passes and only the
    recorded span -- 1440 s, below the bound -- can explain the decline.
    """
    min_s = sources.LTHR_MIN_DURATION_S.value
    samples = _hr_samples((0.0, 720.0, 1440.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=min_s)
    assert abs(1440.0 - min_s) <= sources.EFFORT_SPAN_TOLERANCE.value * min_s

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.reason is DeclineReason.OUTSIDE_VALIDITY_WINDOW
    assert outcome.observed == pytest.approx(1440.0)
    assert outcome.required == pytest.approx(min_s)
    assert f"{1440.0:g}" in outcome.detail


def test_short_effort_declines_below_the_validity_window() -> None:
    """A 1000 s effort with full coverage is below the LTHR window's lower
    bound (Req 3.3): declines naming the lower bound as `required`, mirror
    of the above-window case.
    """
    samples = _hr_samples((0.0, 1000.0), (150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.OUTSIDE_VALIDITY_WINDOW
    min_s = sources.LTHR_MIN_DURATION_S.value
    max_s = sources.LTHR_MAX_DURATION_S.value
    assert outcome.required == pytest.approx(min_s)
    assert outcome.required != pytest.approx(max_s)


@pytest.mark.parametrize("bound", ["min", "max"])
def test_duration_exactly_at_window_bounds_is_not_declined(bound: str) -> None:
    """The window is closed (inclusive at both ends): a duration exactly at
    either published bound derives rather than declining.

    Mutation this dies on: flipping either bound comparison from `<=` to
    `<` reds the corresponding case; a single fixture at one bound alone
    cannot catch a flip at the other, hence both cases here.
    """
    bound_s = (
        sources.LTHR_MIN_DURATION_S.value
        if bound == "min"
        else sources.LTHR_MAX_DURATION_S.value
    )
    samples = _hr_samples((0.0, bound_s), (150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)


def test_unmeasurable_recorded_span_declines_missing_input_never_raises() -> None:
    """A single-sample recording (`models.recorded_span_s` returns `None`:
    fewer than two samples means no consecutive pair to measure a span
    from) declines `MISSING_INPUT` naming an absent observed value, rather
    than raising or fabricating a `0.0` duration that would then be
    compared against `tag.time_s` or the validity window. Controller
    ruling: `required` on this decline is `None` too -- a measurable span
    is what this leaf actually requires here, not the window's lower
    bound, so naming a floor as `required` would misstate what is missing.

    Mutation this dies on: restoring the `0.0` fallback for a `None`
    recorded duration -- this fixture, whose tag carries no `time_s` so the
    span-mismatch branch is skipped, would then fall through to the shared
    sufficiency gate on a single-sample stream, which measures no span
    between samples and declines `TOO_SHORT` with a fabricated
    `observed=0.0` instead of `MISSING_INPUT` with `observed=None`.
    """
    samples = _hr_samples((0.0,), (150,))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.MISSING_INPUT
    assert outcome.observed is None
    assert outcome.required is None
    assert outcome.detail != ""


def test_too_short_recording_declines_below_the_minimum_duration() -> None:
    """Req 3.4: a recording shorter than `settings.min_duration_s` (the
    default is 60 s) declines `TOO_SHORT` -- distinct from
    `OUTSIDE_VALIDITY_WINDOW`, whose own lower bound
    (`sources.LTHR_MIN_DURATION_S`) is well above this one. A 30 s, fully
    covered recording never reaches the window gate at all.

    Mutation this dies on: ignoring the sufficiency gate's `TOO_SHORT`
    verdict (e.g. mapping it to `OUTSIDE_VALIDITY_WINDOW` or skipping
    straight to the window check) -- `outcome.reason` would then differ
    from `DeclineReason.TOO_SHORT`.
    """
    samples = _hr_samples((0.0, 15.0, 30.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.TOO_SHORT
    assert outcome.observed == pytest.approx(30.0)
    assert outcome.required == pytest.approx(60.0)


def test_stream_absent_declines_distinctly_from_sparse_coverage() -> None:
    """Req 3.5: no heart rate anywhere declines with a reason distinct from
    an insufficiently covered stream.

    Mutation this dies on: mapping `STREAM_ABSENT` to the same reason as
    `STREAM_COVERAGE` (collapsing the two verdicts) -- this fixture's
    reason would then equal `STREAM_COVERAGE` instead.
    """
    samples = _hr_samples((0.0, 2400.0), (None, None))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.STREAM_ABSENT
    assert outcome.detail != ""
    assert "heart rate" in outcome.detail


def test_sparse_coverage_below_minimum_declines_with_observed_fraction() -> None:
    """Req 3.4: coverage below the configured minimum declines with the
    observed fraction and the required minimum in the detail. 1200 s of a
    2400 s effort is covered (fraction 0.5), below the default 0.80
    minimum.

    Mutation this dies on: reporting a fixed placeholder fraction instead
    of the measured one -- `observed` would then not equal the true
    `0.5` fraction this fixture actually produces.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (150, None, None))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.STREAM_COVERAGE
    assert outcome.observed == pytest.approx(0.5)
    assert outcome.observed != pytest.approx(1.0)
    assert outcome.required == pytest.approx(0.80)
    assert "0.5" in outcome.detail


def test_official_time_within_tolerance_of_recorded_span_is_not_declined() -> None:
    """A tag's official time (2000 s) and a recorded span (2100 s, built as
    `official_time_s * (1 + tolerance)` from round numbers that stay exact
    in binary floating point) sit exactly on the 5% tolerance boundary --
    `|recorded - official| == tolerance * official` bit-for-bit, not merely
    approximately -- and still derive rather than declining
    `EFFORT_SPAN_MISMATCH`: the window is closed (`>` not `>=`).

    Mutation this dies on: flipping the comparison from `>` to `>=` reds
    this boundary fixture while leaving comfortably-inside fixtures green.
    """
    tolerance = sources.EFFORT_SPAN_TOLERANCE.value
    official_time_s = 2000.0
    recorded_span_s = official_time_s * (1 + tolerance)
    difference = abs(recorded_span_s - official_time_s)
    threshold = tolerance * official_time_s
    assert difference == threshold  # exact, not merely approximate

    samples = _hr_samples((0.0, 1200.0, recorded_span_s), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=official_time_s)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)


def test_official_time_disagreeing_with_recorded_span_declines_span_mismatch() -> None:
    """Req 3.6: the tag's official time (2000 s) disagrees with the
    recorded span (2400 s, a 20% difference) by more than the 5%
    tolerance -- declines naming both durations, stating that locating the
    effort inside a longer recording is out of scope.

    Mutation this dies on: ignoring the span-tolerance check entirely --
    this fixture, whose HR stream and window gates both pass cleanly,
    would then derive instead of declining.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=2000.0)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.EFFORT_SPAN_MISMATCH
    assert "2400" in outcome.detail
    assert "2000" in outcome.detail
    assert "out of scope" in outcome.detail
    assert outcome.observed == pytest.approx(2400.0)
    assert outcome.required == pytest.approx(2000.0)


def test_official_time_longer_than_recorded_span_declines_span_mismatch() -> None:
    """Req 3.6, tolerance direction: the official time (3000 s) is now the
    *longer* duration and the recording (2400 s) the shorter one -- every
    other span-mismatch fixture in this module has the recording longer
    than the official time, so a one-sided tolerance check (comparing only
    `recorded - official`) would survive undetected without this fixture.

    Mutation this dies on: a one-sided check such as
    `(recorded - tag.time_s) > tolerance * tag.time_s` (dropping `abs`) --
    this fixture would then derive instead of declining, since
    `recorded - tag.time_s` is negative here.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=3000.0)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.EFFORT_SPAN_MISMATCH
    assert "2400" in outcome.detail
    assert "3000" in outcome.detail
    assert outcome.observed == pytest.approx(2400.0)
    assert outcome.required == pytest.approx(3000.0)


def test_span_disagreement_just_over_tolerance_declines_span_mismatch() -> None:
    """Req 3.6: pins both the tolerance's magnitude and its base in one
    fixture placed just past the boundary. The official time (2000.0 s)
    and a fully-covered recorded span 101 s longer (2101.0 s) disagree by
    just over the 5% tolerance measured against the *official* time
    (0.05 * 2000.0 = 100.0 s < 101 s), so this declines even though the
    same 101 s difference would sit *under* a 10% tolerance (200.0 s) or
    under a tolerance based on the recorded span instead
    (0.05 * 2101.0 = 105.05 s).

    Mutation this dies on: widening `EFFORT_SPAN_TOLERANCE` from 0.05 to
    0.10 -- the threshold becomes 200.0 s and this fixture derives instead
    of declining.

    Mutation this dies on: computing the threshold as
    `tolerance * recorded_duration_s` instead of `tolerance * tag.time_s`
    -- the threshold becomes 105.05 s and this fixture again derives
    instead of declining.
    """
    samples = _hr_samples((0.0, 1200.0, 2101.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=2000.0)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.reason is DeclineReason.EFFORT_SPAN_MISMATCH
    assert outcome.observed == pytest.approx(2101.0)
    assert outcome.required == pytest.approx(2000.0)


def test_span_mismatch_declines_ahead_of_an_otherwise_valid_window() -> None:
    """Controller ruling, design § Per-quantity gates (`LthrSpan ->
    LthrGate -> LthrWindow`): a 2400 s official time inside a *fully
    covered* 5400 s recording -- a duration that is itself outside the
    LTHR window -- declines `EFFORT_SPAN_MISMATCH`, not
    `OUTSIDE_VALIDITY_WINDOW`. The span gate runs first.

    Mutation this dies on: checking the window before the span (swapping
    the two gates) -- this fixture would then decline
    `OUTSIDE_VALIDITY_WINDOW` instead.
    """
    samples = _hr_samples((0.0, 2700.0, 5400.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=2400.0)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.reason is DeclineReason.EFFORT_SPAN_MISMATCH


def test_span_mismatch_declines_ahead_of_sparse_coverage() -> None:
    """Controller ruling, design § Per-quantity gates (`LthrSpan ->
    LthrGate -> LthrWindow`): the same 2400 s official time inside a
    5400 s recording that is *also* SPARSE (below the coverage minimum)
    still declines `EFFORT_SPAN_MISMATCH`, not `STREAM_COVERAGE`. The span
    gate runs ahead of the sufficiency gate too.

    Mutation this dies on: checking sufficiency before the span (swapping
    the two gates) -- this fixture would then decline `STREAM_COVERAGE`
    instead.
    """
    samples = _hr_samples((0.0, 2700.0, 5400.0), (150, None, None))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE, time_s=2400.0)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.reason is DeclineReason.EFFORT_SPAN_MISMATCH


def test_zero_heart_rate_stream_declines_rather_than_deriving_a_zero() -> None:
    """Hard rule (design § PerformanceTypes postcondition: a derived value
    is finite and positive; never a fabricated zero): an all-zero heart
    rate stream over a validity-window-length recording declines
    `MISSING_INPUT` naming the mean, never a `DerivedBenchmark` carrying
    `0.0`.

    Mutation this dies on: removing the `_finite_positive(mean_bpm)` gate
    on the time-weighted mean -- this fixture would then derive a
    `DerivedBenchmark` with `value == 0.0` instead of declining.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (0, 0, 0))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.MISSING_INPUT
    assert outcome.observed == 0.0
    assert "0 bpm" in outcome.detail
    assert outcome.detail != ""


def test_negative_heart_rate_stream_declines_rather_than_deriving_negative() -> None:
    """Hard rule (design § PerformanceTypes postcondition): a negative
    heart-rate stream (nonsensical, but the gate must not trust a raw
    negative mean into a `DerivedBenchmark`) also declines `MISSING_INPUT`,
    never `DerivedBenchmark(value=-5.0)`, and reports the actual negative
    mean as `observed` rather than dropping it.

    Mutation this dies on: narrowing the `_finite_positive` check on this
    leaf to a strict zero test (`value != 0`) rather than `value > 0` --
    this fixture, whose mean is `-5.0` (nonzero), would then still derive.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (-5, -5, -5))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=_HR_ON,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.MISSING_INPUT
    assert outcome.observed == pytest.approx(-5.0)


def test_undated_document_declines_before_every_other_gate() -> None:
    """The undated gate runs first, unconditionally (Implementation Notes'
    gate-ordering ruling). This fixture's HR stream is wholly absent
    (would decline `STREAM_ABSENT` on its own merits, the recorded span
    2400 s sitting inside the window) -- if the undated gate ran anywhere
    but first, this fixture would surface that later gate's reason
    instead, so it actually exercises the ordering rather than merely a
    fixture that happens to pass everything else.

    Mutation this dies on: moving the `on is None` check to run after the
    window and stream-sufficiency gates -- this fixture would then decline
    `STREAM_ABSENT` instead of `UNDATED_DOCUMENT`.
    """
    samples = _hr_samples((0.0, 2400.0), (None, None))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)

    outcome = derive.lactate_threshold_hr(
        activity, tag, on=None, document=_HR_DOCUMENT, sufficiency=_DEFAULT_SUFFICIENCY
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.kind is BenchmarkKind.LTHR_BPM
    assert outcome.reason is DeclineReason.UNDATED_DOCUMENT
    assert _HR_DOCUMENT in outcome.detail


def test_lthr_derived_value_is_dated_at_the_passed_on_date_not_the_wall_clock() -> None:
    """The derived value's `measured_on` is exactly the `on` argument -- a
    fixed date far from today, so a `date.today()` implementation could
    never accidentally match it.

    Mutation this dies on: dating from `date.today()` instead of `on`.
    """
    samples = _hr_samples((0.0, 1200.0, 2400.0), (150, 150, 150))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)
    fixed_on = date(2019, 6, 1)
    assert fixed_on != date.today()

    outcome = derive.lactate_threshold_hr(
        activity,
        tag,
        on=fixed_on,
        document=_HR_DOCUMENT,
        sufficiency=_DEFAULT_SUFFICIENCY,
    )

    assert isinstance(outcome, DerivedBenchmark)
    assert outcome.measured_on == fixed_on


def test_wrong_channel_would_apply_the_wrong_coverage_minimum() -> None:
    """Req 3.4: the caller-supplied `hr_min_stream_coverage` override --
    not the power channel's -- governs this leaf's coverage gate. A 70%
    covered stream passes the HR override (50%) but would fail the power
    override (99%) if the leaf mistakenly gated on `ChannelId.POWER`.

    Mutation this dies on: passing `ChannelId.POWER` (or any channel other
    than `ChannelId.HEART_RATE`) to `sufficiency.evaluate` -- this fixture
    would then decline `STREAM_COVERAGE` instead of deriving.
    """
    samples = _hr_samples((0.0, 1680.0, 2400.0), (150, None, None))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)
    settings = SufficiencySettings(
        hr_min_stream_coverage=0.5, power_min_stream_coverage=0.99
    )

    outcome = derive.lactate_threshold_hr(
        activity, tag, on=_HR_ON, document=_HR_DOCUMENT, sufficiency=settings
    )

    assert isinstance(outcome, DerivedBenchmark)


def test_callers_settings_govern_not_the_default_settings() -> None:
    """Req 3.4: the caller-supplied `SufficiencySettings` governs the gate,
    never a default constructed in its place. An 85% covered stream passes
    the *default* 80% minimum but must decline against a caller-supplied
    95% minimum.

    Mutation this dies on: constructing a fresh default `SufficiencySettings()`
    instead of using the caller-supplied `sufficiency` argument -- this
    fixture would then derive (85% clears the default 80%) instead of
    declining against the caller's stricter 95%.
    """
    samples = _hr_samples((0.0, 2040.0, 2400.0), (150, None, None))
    activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
    tag = _tag(kind=EffortKind.RACE)
    strict_settings = SufficiencySettings(hr_min_stream_coverage=0.95)

    outcome = derive.lactate_threshold_hr(
        activity, tag, on=_HR_ON, document=_HR_DOCUMENT, sufficiency=strict_settings
    )

    assert isinstance(outcome, DerivationDeclined)
    assert outcome.reason is DeclineReason.STREAM_COVERAGE
    assert outcome.required == pytest.approx(0.95)
    assert outcome.required != pytest.approx(0.80)


def test_all_three_effort_kinds_are_used_for_lthr() -> None:
    """Req 3.1: the LTHR routing table names all three effort kinds for
    both covered sports (unlike `threshold_pace`, which is race-only) --
    swept exhaustively rather than spot-checked on a single kind.

    Mutation this dies on: gating on `tag.kind is EffortKind.RACE` (copying
    `threshold_pace`'s kind gate) -- the `test`/`hard` cases here would
    then decline `EFFORT_KIND_NOT_USED` instead of deriving.
    """
    for kind in (EffortKind.RACE, EffortKind.TEST, EffortKind.HARD):
        samples = _hr_samples((0.0, 1200.0, 2400.0), (150, 150, 150))
        activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
        tag = _tag(kind=kind)

        outcome = derive.lactate_threshold_hr(
            activity,
            tag,
            on=_HR_ON,
            document=_HR_DOCUMENT,
            sufficiency=_DEFAULT_SUFFICIENCY,
        )

        assert isinstance(outcome, DerivedBenchmark)


def test_lthr_never_raises_on_a_decline_path() -> None:
    """Sweep over every reachable `DeclineReason` on this leaf -- seven
    distinct reasons, enumerated from the gate order in
    `lactate_threshold_hr`'s own docstring: undated, missing input (via
    either of its two reachable routes -- an unmeasurable recorded span,
    or a covered, in-window stream whose mean is non-positive), span
    mismatch, too-short, stream-absent, sparse coverage, and outside the
    validity window. Each returns rather than raises, and each carries a
    non-empty `detail` (design invariant).
    """
    fixtures: list[
        tuple[
            date | None,
            tuple[float, ...],
            tuple[int | None, ...],
            float | None,
            DeclineReason,
        ]
    ] = [
        (
            None,
            (0.0, 1200.0, 2400.0),
            (150, 150, 150),
            None,
            DeclineReason.UNDATED_DOCUMENT,
        ),
        (
            _HR_ON,
            (0.0,),
            (150,),
            None,
            DeclineReason.MISSING_INPUT,
        ),
        (
            _HR_ON,
            (0.0, 1200.0, 2400.0),
            (0, 0, 0),
            None,
            DeclineReason.MISSING_INPUT,
        ),
        (_HR_ON, (0.0, 15.0, 30.0), (150, 150, 150), None, DeclineReason.TOO_SHORT),
        (_HR_ON, (0.0, 2400.0), (None, None), None, DeclineReason.STREAM_ABSENT),
        (
            _HR_ON,
            (0.0, 1200.0, 2400.0),
            (150, None, None),
            None,
            DeclineReason.STREAM_COVERAGE,
        ),
        (
            _HR_ON,
            (0.0, 5400.0),
            (150, 150),
            None,
            DeclineReason.OUTSIDE_VALIDITY_WINDOW,
        ),
        (
            _HR_ON,
            (0.0, 1200.0, 2400.0),
            (150, 150, 150),
            2000.0,
            DeclineReason.EFFORT_SPAN_MISMATCH,
        ),
    ]
    for on, time_s, values, tag_time_s, expected_reason in fixtures:
        samples = _hr_samples(time_s, values)
        activity = _hr_activity(sport=Sport.RUN, modality=Modality.RUN, samples=samples)
        tag = _tag(kind=EffortKind.RACE, time_s=tag_time_s)

        outcome = derive.lactate_threshold_hr(
            activity,
            tag,
            on=on,
            document=_HR_DOCUMENT,
            sufficiency=_DEFAULT_SUFFICIENCY,
        )

        assert isinstance(outcome, DerivationDeclined)
        assert outcome.kind is BenchmarkKind.LTHR_BPM
        assert outcome.reason is expected_reason
        assert outcome.detail != ""
        assert outcome.method is DerivationMethod.SUSTAINED_EFFORT_MEAN_HR
