"""Tests for `fitdocs.load.qa.flags.evaluate_flags` (design: FlagAssembly,
task 3.1).

Covers Requirements 1.1-1.10, 3.8, 5.8, 7.6, 7.7 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and design.md's
"FlagAssembly" component section.

**Own test module** (Test File Ownership): every constructed
:class:`Activity`, :class:`ChannelOutcome`, :class:`Benchmark` and
:class:`DerivedMetrics` this task needs is built here.

**The 2.3 -> 3.1 Implementation Note.** Req 3.9's divergence regression case
(same load, same duration, both channels at ~0.58 intensity) cannot
distinguish a *symmetric* ``.load``-for-``.intensity`` field swap anywhere
in this assembly from a correct read -- that premise forces equal
intensities under the shared relation either way. It catches only a
one-sided swap. This module's own end-to-end coverage does not lean on
divergence's existing test for that guarantee; the fixtures below read the
same typed fields divergence itself reads (``.intensity``, never ``.load``)
and are proven with fixtures whose ``.intensity`` and ``.load`` values
differ, which a symmetric swap would visibly break.
"""

from __future__ import annotations

from datetime import date, timedelta

from fitdocs import Activity, DerivedMetrics, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelLoad,
    ChannelOutcome,
    StreamCoverage,
)
from fitdocs.load.qa import cadence, divergence, drift, staleness
from fitdocs.load.qa.cadence import CadenceLockOutcome
from fitdocs.load.qa.divergence import DivergenceOutcome
from fitdocs.load.qa.drift import DriftOutcome
from fitdocs.load.qa.flags import evaluate_flags
from fitdocs.load.qa.staleness import StalenessOutcome
from fitdocs.load.qa.types import FLAG_LABELS, FLAG_ORDER, FlagKey, FlagSettings
from fitdocs.model import SCHEMA_VERSION, SessionSummary

ACTIVITY_DATE = date(2026, 6, 1)


# ---------------------------------------------------------------------------
# Shared builders (this module's own, per Test File Ownership)
# ---------------------------------------------------------------------------


def _samples(
    *,
    time_s: tuple[float, ...] = (),
    heart_rate_bpm: tuple[int | None, ...] | None = None,
    cadence_rpm: tuple[float | None, ...] | None = None,
) -> Samples:
    n = len(time_s)
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm if heart_rate_bpm is not None else (None,) * n,
        power_w=(None,) * n,
        cadence_rpm=cadence_rpm if cadence_rpm is not None else (None,) * n,
        speed_mps=(None,) * n,
        distance_m=(None,) * n,
        altitude_m=(None,) * n,
        latitude_deg=(None,) * n,
        longitude_deg=(None,) * n,
        temperature_c=(None,) * n,
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


def _activity(*, modality: Modality, samples: Samples) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=Sport.RUN if modality is Modality.RUN else Sport.RIDE,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


def _benchmark(
    measured_on: date, *, applies_from: date | None = None, value: float = 270.0
) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=value,
        measured_on=measured_on,
        applies_from=applies_from,
    )


def _channel_load(
    *,
    channel: ChannelId = ChannelId.POWER,
    intensity: float,
    load: float,
    anchor: Benchmark,
) -> ChannelLoad:
    return ChannelLoad(
        channel=channel,
        load=load,
        intensity=intensity,
        anchor=anchor,
        scored_duration_s=3600.0,
        coverage=StreamCoverage(stream=channel.value, covered_s=3600.0, total_s=3600.0),
        inputs_used=((channel.value, "raw"),),
    )


def _no_metrics() -> DerivedMetrics:
    return DerivedMetrics(decoupling_pct=None, efficiency_factor=None)


def _default_kwargs(
    *,
    activity: Activity | None = None,
    metrics: DerivedMetrics | None = None,
    outcomes: dict[ChannelId, ChannelOutcome] | None = None,
    selected: ChannelId = ChannelId.POWER,
    activity_date: date | None = ACTIVITY_DATE,
    staleness_window_days: int = 90,
    settings: FlagSettings | None = None,
) -> dict[str, object]:
    """A complete, self-consistent set of ``evaluate_flags`` kwargs everyone
    reaches NOT_ASSESSED against (non-running modality, no cadence, HR
    absent, no decoupling metric, current-ish anchor) unless a test
    overrides a specific field to steer one check somewhere else."""
    anchor = _benchmark(ACTIVITY_DATE - timedelta(days=10))
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=anchor
    )
    return {
        "activity": activity
        if activity is not None
        else _activity(modality=Modality.BIKE, samples=_samples()),
        "metrics": metrics if metrics is not None else _no_metrics(),
        "outcomes": outcomes
        if outcomes is not None
        else {ChannelId.POWER: selected_load},
        "selected": selected,
        "activity_date": activity_date,
        "staleness_window_days": staleness_window_days,
        "settings": settings if settings is not None else FlagSettings(),
    }


# ---------------------------------------------------------------------------
# Postcondition: exactly four flags, one per FlagKey, in FLAG_ORDER
# ---------------------------------------------------------------------------


def test_returns_exactly_four_flags_one_per_key_in_flag_order() -> None:
    flags = evaluate_flags(**_default_kwargs())  # type: ignore[arg-type]

    assert len(flags) == 4
    assert tuple(flag.key for flag in flags) == tuple(key.value for key in FLAG_ORDER)
    assert {flag.key for flag in flags} == {key.value for key in FlagKey}


def test_output_order_is_flag_order_not_internal_check_order() -> None:
    """A fixture where cadence (called first inside ``evaluate_flags``)
    reaches NOT_ASSESSED while staleness (called last) reaches DETECTED --
    varying which checks land which verdicts, so this test is not merely a
    restatement of the all-not-assessed/all-detected cases above.

    This fixture alone does not, by construction, prove the output order is
    enforced rather than a coincidence of `evaluate_flags`'s internal call
    order (which already happens to match `FLAG_ORDER`): that property is
    what `tuple(flag.key for flag in flags) == tuple(key.value for key in
    FLAG_ORDER)` below actually pins, verified by mutation (reviewer-
    confirmed and re-confirmed in this task's own discrimination gate):
    reordering `evaluate_flags`'s final `tuple(by_key[key] for key in
    FLAG_ORDER)` to iterate `reversed(FLAG_ORDER)` reds this assertion, even
    though a coincidental dict-insertion-order return (`by_key.values()`)
    does not, which is why the check is against `FLAG_ORDER` explicitly
    rather than against this fixture's own call order."""
    stale_anchor = _benchmark(ACTIVITY_DATE - timedelta(days=1000))
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=stale_anchor
    )
    kwargs = _default_kwargs(
        activity=_activity(modality=Modality.BIKE, samples=_samples()),  # not-assessed
        outcomes={ChannelId.POWER: selected_load},
    )

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    assert tuple(flag.key for flag in flags) == tuple(key.value for key in FLAG_ORDER)
    by_key = {flag.key: flag for flag in flags}
    assert by_key[FlagKey.CADENCE_LOCK.value].verdict == "not-assessed"
    assert by_key[FlagKey.BENCHMARK_STALENESS.value].verdict == "detected"


# ---------------------------------------------------------------------------
# Each flag's label names its own check (reviewer finding 3): swapping two
# checks' labels in the assembly's by_key construction must be visible.
# ---------------------------------------------------------------------------


def test_each_flags_label_matches_its_own_key() -> None:
    flags = evaluate_flags(**_default_kwargs())  # type: ignore[arg-type]

    for flag in flags:
        assert flag.label == FLAG_LABELS[FlagKey(flag.key)]


# ---------------------------------------------------------------------------
# Postcondition: verdict is always one of exactly the three contract literals
# ---------------------------------------------------------------------------


def test_every_verdict_is_one_of_the_three_contract_literals() -> None:
    flags = evaluate_flags(**_default_kwargs())  # type: ignore[arg-type]

    for flag in flags:
        assert flag.verdict in {"detected", "not-detected", "not-assessed"}


# ---------------------------------------------------------------------------
# Postcondition: every detail is non-empty, across representative outcome
# combinations covering each check reaching each of its own outcomes.
# ---------------------------------------------------------------------------


def _running_locked_samples() -> Samples:
    """A stream that satisfies the cadence-lock check's LOCKED verdict:
    heart rate exactly twice cadence (full-cycle match), close and
    correlated, sustained across several 120s spans."""
    n = 40
    time_s = tuple(float(i) * 10.0 for i in range(n))
    cadence = tuple(80.0 + i for i in range(n))
    heart_rate = tuple(int(c * 2) for c in cadence)
    return _samples(time_s=time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)


def _running_offset_samples() -> Samples:
    """A stream with perfect heart-rate/cadence correlation (r == 1.0, so
    the association condition always holds) but a constant 8 bpm median
    offset -- straddling the default ``cadence_lock_max_delta_bpm`` (5.0)
    and a loosened one (10.0), so only the closeness condition, and thus the
    verdict, flips between the two settings values."""
    n = 40
    time_s = tuple(float(i) * 10.0 for i in range(n))
    cadence = tuple(80.0 + i for i in range(n))
    heart_rate = tuple(int(c * 2) + 8 for c in cadence)
    return _samples(time_s=time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)


def _running_clear_samples() -> Samples:
    """A stream with enough paired coverage and full spans, but no lock:
    heart rate and cadence are numerically far apart and uncorrelated."""
    n = 20
    time_s = tuple(float(i) * 20.0 for i in range(n))
    cadence = tuple(80.0 for _ in range(n))
    heart_rate = tuple(150 + (i % 3) * 10 for i in range(n))
    return _samples(time_s=time_s, heart_rate_bpm=heart_rate, cadence_rpm=cadence)


def test_all_four_not_assessed_simultaneously_has_non_empty_details() -> None:
    kwargs = _default_kwargs()  # bike modality, no HR insufficiency wired, etc.
    # Force divergence NOT_ASSESSED too: selected channel IS heart rate.
    anchor = _benchmark(ACTIVITY_DATE - timedelta(days=10))
    hr_load = _channel_load(
        channel=ChannelId.HEART_RATE, intensity=0.9, load=200.0, anchor=anchor
    )
    kwargs["outcomes"] = {ChannelId.HEART_RATE: hr_load}
    kwargs["selected"] = ChannelId.HEART_RATE
    kwargs["activity_date"] = None  # forces staleness NOT_ASSESSED

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    assert len(flags) == 4
    for flag in flags:
        assert flag.verdict == "not-assessed"
        assert flag.detail != ""

    # Reviewer finding 6: pin each not-assessed basis to its own check's
    # actual reason, not just non-emptiness -- computed independently, by
    # calling each check's own module directly with the same inputs
    # `evaluate_flags` uses internally, so a generic constant string
    # ("not assessed") substituted for any one of the four would red here.
    by_key = {flag.key: flag for flag in flags}
    activity = kwargs["activity"]
    assert isinstance(activity, Activity)
    cadence_reading = cadence.detect(
        activity.samples, modality=activity.modality, settings=FlagSettings()
    )
    assert cadence_reading.not_assessed_reason is not None
    cadence_flag = by_key[FlagKey.CADENCE_LOCK.value]
    assert cadence_flag.detail == cadence_reading.not_assessed_reason

    divergence_reading = divergence.evaluate(
        kwargs["outcomes"],  # type: ignore[arg-type]
        selected=ChannelId.HEART_RATE,
        settings=FlagSettings(),
    )
    assert divergence_reading.not_assessed_reason is not None
    assert (
        by_key[FlagKey.CHANNEL_DIVERGENCE.value].detail
        == divergence_reading.not_assessed_reason
    )

    drift_reading = drift.evaluate(_no_metrics(), settings=FlagSettings())
    assert drift_reading.not_assessed_reason is not None
    drift_flag = by_key[FlagKey.AEROBIC_DRIFT.value]
    assert drift_flag.detail == drift_reading.not_assessed_reason

    staleness_reading = staleness.evaluate(hr_load, activity_date=None, window_days=90)
    assert staleness_reading.not_assessed_reason is not None
    assert (
        by_key[FlagKey.BENCHMARK_STALENESS.value].detail
        == staleness_reading.not_assessed_reason
    )

    # Each reason is also distinct from the other three, so a cross-wire
    # between checks (not just a generic constant) would be visible too.
    reasons = {
        cadence_reading.not_assessed_reason,
        divergence_reading.not_assessed_reason,
        drift_reading.not_assessed_reason,
        staleness_reading.not_assessed_reason,
    }
    assert len(reasons) == 4


def test_all_four_detected_simultaneously_has_non_empty_details() -> None:
    activity = _activity(modality=Modality.RUN, samples=_running_locked_samples())
    anchor = _benchmark(ACTIVITY_DATE - timedelta(days=1000))  # very stale
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=anchor
    )
    hr_load = _channel_load(
        channel=ChannelId.HEART_RATE, intensity=0.2, load=5.0, anchor=anchor
    )
    metrics = DerivedMetrics(decoupling_pct=20.0, efficiency_factor=1.5)
    settings = FlagSettings(
        cadence_lock_window_s=20,
        cadence_lock_min_duration_s=60,
    )
    kwargs = _default_kwargs(
        activity=activity,
        metrics=metrics,
        outcomes={ChannelId.POWER: selected_load, ChannelId.HEART_RATE: hr_load},
        selected=ChannelId.POWER,
        settings=settings,
    )

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    assert len(flags) == 4
    for flag in flags:
        assert flag.verdict == "detected", (flag.key, flag.verdict, flag.detail)
        assert flag.detail != ""


def test_cadence_clear_reaches_not_detected_with_non_empty_detail() -> None:
    activity = _activity(modality=Modality.RUN, samples=_running_clear_samples())
    settings = FlagSettings(cadence_lock_window_s=20, cadence_lock_min_duration_s=60)
    kwargs = _default_kwargs(activity=activity, settings=settings)

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    cadence_flag = by_key[FlagKey.CADENCE_LOCK.value]
    assert cadence_flag.verdict == "not-detected"
    # Pin real content, not just non-emptiness (reviewer finding 2): the
    # observed locked duration, the configured minimum, and the exact
    # "time-weighted ... paired coverage" phrasing Requirement 8 requires to
    # distinguish this figure from the document's own sample-count coverage
    # table.
    assert "locked together for 0s" in cadence_flag.detail
    assert "configured minimum 60s" in cadence_flag.detail
    assert "time-weighted heart-rate/cadence paired coverage" in cadence_flag.detail


def test_divergence_agreed_reaches_not_detected() -> None:
    anchor = _benchmark(ACTIVITY_DATE - timedelta(days=10))
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.60, load=100.0, anchor=anchor
    )
    hr_load = _channel_load(
        channel=ChannelId.HEART_RATE, intensity=0.58, load=95.0, anchor=anchor
    )
    kwargs = _default_kwargs(
        outcomes={ChannelId.POWER: selected_load, ChannelId.HEART_RATE: hr_load},
        selected=ChannelId.POWER,
    )

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    divergence_flag = by_key[FlagKey.CHANNEL_DIVERGENCE.value]
    assert divergence_flag.verdict == "not-detected"
    # Pin real content, not just non-emptiness (reviewer finding 2), and pin
    # which ROLE each figure plays, not just its presence (reviewer round 2
    # finding): the contiguous phrase below is broken by swapping
    # selected_intensity and heart_rate_intensity, not just by removing one.
    assert "intensity 0.600 vs heart-rate intensity 0.580" in divergence_flag.detail
    assert "difference 0.020, configured tolerance 0.200" in divergence_flag.detail


def test_drift_coupled_reaches_not_detected() -> None:
    metrics = DerivedMetrics(decoupling_pct=2.0, efficiency_factor=None)
    kwargs = _default_kwargs(metrics=metrics)

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    drift_flag = by_key[FlagKey.AEROBIC_DRIFT.value]
    assert drift_flag.verdict == "not-detected"
    # Pin which ROLE each figure plays (reviewer round 2 finding): this
    # phrase is broken by swapping observed decoupling_pct (2.0) and
    # configured reference_pct (5.0, the default), not just by removing one.
    assert "aerobic decoupling 2.0% vs configured reference 5.0%" in drift_flag.detail


def test_drift_detail_reference_pct_reflects_non_default_setting() -> None:
    """The `_drift_detail` basis's `reference_pct` is read from the reading
    (`FlagSettings.aerobic_drift_max_pct` threaded through `drift.evaluate`),
    never the module's shipped default. Every other drift-detail fixture in
    this module uses the default 5.0%, which cannot distinguish a correctly
    threaded reading from a hardcoded `5.0` literal -- this fixture uses a
    non-default `aerobic_drift_max_pct` and asserts the configured figure
    the detail reports.

    Mutation (named, applied, confirmed red, reverted, confirmed green): in
    `flags.py`'s `_drift_detail`, hardcode the module's default constant
    (5.0) in place of `reading.reference_pct`.
    """
    metrics = DerivedMetrics(decoupling_pct=2.0, efficiency_factor=None)
    settings = FlagSettings(aerobic_drift_max_pct=8.0)
    kwargs = _default_kwargs(metrics=metrics, settings=settings)

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    drift_flag = by_key[FlagKey.AEROBIC_DRIFT.value]
    assert drift_flag.verdict == "not-detected"
    assert "aerobic decoupling 2.0% vs configured reference 8.0%" in drift_flag.detail
    assert "reference 5.0%" not in drift_flag.detail


def test_staleness_current_reaches_not_detected() -> None:
    kwargs = _default_kwargs()  # default anchor is 10 days old, window 90

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    staleness_flag = by_key[FlagKey.BENCHMARK_STALENESS.value]
    assert staleness_flag.verdict == "not-detected"
    # Pin which ROLE each figure plays (reviewer round 2 finding): observed
    # age (10 days) is distinct from configured window (90 days), and this
    # phrase is broken by swapping the two, not just by removing one.
    assert "10 day(s) old (configured window 90 days)" in staleness_flag.detail


def test_staleness_basis_reports_the_selected_channels_own_anchor() -> None:
    """Req 5.1 integration-level guard: the staleness verdict reports on the
    benchmark that anchored the SELECTED channel, never a benchmark that
    anchored a non-selected channel. Every other fixture in this module
    gives every channel the SAME anchor `measured_on` date, which cannot
    distinguish "read the selected channel's anchor" from "read some other
    channel's anchor" -- this fixture gives the selected channel (POWER) and
    a non-selected channel (HEART_RATE) DIFFERENT `measured_on` dates, far
    enough apart that both the reported age and the reported date diverge.

    Mutation (named, applied, confirmed red, reverted, confirmed green): in
    `flags.py`, read a different channel's `ChannelLoad.anchor` instead of
    `outcomes[selected].anchor` inside `evaluate_flags`'s staleness call --
    e.g. hardcode `outcomes[ChannelId.HEART_RATE]` regardless of `selected`.
    """
    selected_measured_on = ACTIVITY_DATE - timedelta(days=10)
    other_measured_on = ACTIVITY_DATE - timedelta(days=200)
    selected_anchor = _benchmark(selected_measured_on)
    other_anchor = _benchmark(other_measured_on)
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=selected_anchor
    )
    other_load = _channel_load(
        channel=ChannelId.HEART_RATE, intensity=0.2, load=5.0, anchor=other_anchor
    )
    kwargs = _default_kwargs(
        outcomes={ChannelId.POWER: selected_load, ChannelId.HEART_RATE: other_load},
        selected=ChannelId.POWER,
    )

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    staleness_flag = by_key[FlagKey.BENCHMARK_STALENESS.value]
    assert staleness_flag.verdict == "not-detected"
    assert selected_measured_on.isoformat() in staleness_flag.detail
    assert "10 day(s) old (configured window 90 days)" in staleness_flag.detail
    assert other_measured_on.isoformat() not in staleness_flag.detail
    assert "200 day(s) old" not in staleness_flag.detail


# ---------------------------------------------------------------------------
# Req 5.8: the RETROACTIVE-specific basis, with and without applies_from
# ---------------------------------------------------------------------------


def test_retroactive_with_applies_from_names_the_declared_date() -> None:
    applies_from = ACTIVITY_DATE - timedelta(days=5)
    measured_on = ACTIVITY_DATE + timedelta(days=30)
    anchor = _benchmark(measured_on, applies_from=applies_from)
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=anchor
    )
    kwargs = _default_kwargs(outcomes={ChannelId.POWER: selected_load})

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    staleness_flag = by_key[FlagKey.BENCHMARK_STALENESS.value]
    assert staleness_flag.verdict == "not-detected"
    assert measured_on.isoformat() in staleness_flag.detail
    assert applies_from.isoformat() in staleness_flag.detail
    assert "30" in staleness_flag.detail  # days after the activity
    # Req 5.8's window element
    assert "configured window 90 days" in staleness_flag.detail


def test_retroactive_without_applies_from_states_the_absence() -> None:
    measured_on = ACTIVITY_DATE + timedelta(days=30)
    anchor = _benchmark(measured_on, applies_from=None)
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=anchor
    )
    kwargs = _default_kwargs(outcomes={ChannelId.POWER: selected_load})

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    staleness_flag = by_key[FlagKey.BENCHMARK_STALENESS.value]
    assert staleness_flag.verdict == "not-detected"
    assert measured_on.isoformat() in staleness_flag.detail
    assert "no applies-from date" in staleness_flag.detail
    assert applies_from_absent_marker_not_a_date(staleness_flag.detail)
    # Req 5.8's window element
    assert "configured window 90 days" in staleness_flag.detail


def applies_from_absent_marker_not_a_date(detail: str) -> bool:
    """Guards against a fabricated date standing in for the absence: the
    text must not contain the activity date or any obviously date-shaped
    ISO string beyond the measurement date already asserted above, in the
    applies-from clause specifically."""
    return "declared it applies from" not in detail


def test_retroactive_verdict_is_never_detected_or_not_assessed() -> None:
    for applies_from in (None, ACTIVITY_DATE - timedelta(days=1)):
        measured_on = ACTIVITY_DATE + timedelta(days=7)
        anchor = _benchmark(measured_on, applies_from=applies_from)
        selected_load = _channel_load(
            channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=anchor
        )
        kwargs = _default_kwargs(outcomes={ChannelId.POWER: selected_load})

        flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

        by_key = {flag.key: flag for flag in flags}
        verdict = by_key[FlagKey.BENCHMARK_STALENESS.value].verdict
        assert verdict == "not-detected"


# ---------------------------------------------------------------------------
# Req 4.5/1.8: no fabricated numeric stand-in for a None efficiency_factor
# ---------------------------------------------------------------------------


def test_drift_detected_with_no_efficiency_factor_has_no_fabricated_figure() -> None:
    metrics = DerivedMetrics(decoupling_pct=20.0, efficiency_factor=None)
    kwargs = _default_kwargs(metrics=metrics)

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    drift_flag = by_key[FlagKey.AEROBIC_DRIFT.value]
    assert drift_flag.verdict == "detected"
    assert "efficiency factor" not in drift_flag.detail
    assert " 0" not in drift_flag.detail
    assert "N/A" not in drift_flag.detail


def test_drift_coupled_with_no_efficiency_factor_has_no_fabricated_figure() -> None:
    metrics = DerivedMetrics(decoupling_pct=1.0, efficiency_factor=None)
    kwargs = _default_kwargs(metrics=metrics)

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    drift_flag = by_key[FlagKey.AEROBIC_DRIFT.value]
    assert drift_flag.verdict == "not-detected"
    assert "efficiency factor" not in drift_flag.detail
    assert " 0" not in drift_flag.detail
    assert "N/A" not in drift_flag.detail


def test_drift_detected_with_efficiency_factor_states_it() -> None:
    metrics = DerivedMetrics(decoupling_pct=20.0, efficiency_factor=1.23)
    kwargs = _default_kwargs(metrics=metrics)

    flags = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    by_key = {flag.key: flag for flag in flags}
    drift_flag = by_key[FlagKey.AEROBIC_DRIFT.value]
    assert "efficiency factor" in drift_flag.detail
    assert "1.23" in drift_flag.detail


# ---------------------------------------------------------------------------
# Req 7.6: equal inputs -> equal tuple, string for string, on repeat calls
# ---------------------------------------------------------------------------


def test_equal_inputs_produce_string_equal_tuple_on_repeat_calls() -> None:
    kwargs = _default_kwargs()

    first = evaluate_flags(**kwargs)  # type: ignore[arg-type]
    second = evaluate_flags(**kwargs)  # type: ignore[arg-type]

    assert first == second
    assert tuple((f.key, f.label, f.verdict, f.detail) for f in first) == tuple(
        (f.key, f.label, f.verdict, f.detail) for f in second
    )


# ---------------------------------------------------------------------------
# Settings/activity_date/staleness_window_days threading proof: a non-
# default FlagSettings flips a check's verdict through evaluate_flags, not
# just when calling that check's own module directly.
# ---------------------------------------------------------------------------


def test_aerobic_drift_max_pct_setting_is_threaded_through_to_flip_verdict() -> None:
    metrics = DerivedMetrics(decoupling_pct=6.0, efficiency_factor=None)

    default_kwargs = _default_kwargs(metrics=metrics)
    default_flags = evaluate_flags(**default_kwargs)  # type: ignore[arg-type]
    default_by_key = {flag.key: flag for flag in default_flags}
    assert default_by_key[FlagKey.AEROBIC_DRIFT.value].verdict == "detected"

    loose_settings = FlagSettings(aerobic_drift_max_pct=50.0)
    loose_kwargs = _default_kwargs(metrics=metrics, settings=loose_settings)
    loose_flags = evaluate_flags(**loose_kwargs)  # type: ignore[arg-type]
    loose_by_key = {flag.key: flag for flag in loose_flags}
    assert loose_by_key[FlagKey.AEROBIC_DRIFT.value].verdict == "not-detected"


def test_cadence_max_delta_bpm_setting_is_threaded_through_to_flip_verdict() -> None:
    """Reviewer finding 4: the drift and divergence threading tests above
    each flip a verdict through ``evaluate_flags`` with a non-default
    setting; the cadence check had no equivalent, so the existing
    non-default-cadence-settings fixtures elsewhere in this module (which
    happen to reach the same verdict under defaults too) could not
    discriminate a hardcoded ``FlagSettings()`` passed to
    ``cadence.detect`` from the real threaded ``settings`` argument."""
    activity = _activity(modality=Modality.RUN, samples=_running_offset_samples())

    default_settings = FlagSettings(
        cadence_lock_window_s=20, cadence_lock_min_duration_s=60
    )
    default_kwargs = _default_kwargs(activity=activity, settings=default_settings)
    default_flags = evaluate_flags(**default_kwargs)  # type: ignore[arg-type]
    default_by_key = {flag.key: flag for flag in default_flags}
    assert default_by_key[FlagKey.CADENCE_LOCK.value].verdict == "not-detected"

    loose_settings = FlagSettings(
        cadence_lock_window_s=20,
        cadence_lock_min_duration_s=60,
        cadence_lock_max_delta_bpm=10.0,
    )
    loose_kwargs = _default_kwargs(activity=activity, settings=loose_settings)
    loose_flags = evaluate_flags(**loose_kwargs)  # type: ignore[arg-type]
    loose_by_key = {flag.key: flag for flag in loose_flags}
    assert loose_by_key[FlagKey.CADENCE_LOCK.value].verdict == "detected"


def test_divergence_max_intensity_delta_setting_is_threaded_through() -> None:
    anchor = _benchmark(ACTIVITY_DATE - timedelta(days=10))
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.70, load=100.0, anchor=anchor
    )
    hr_load = _channel_load(
        channel=ChannelId.HEART_RATE, intensity=0.60, load=80.0, anchor=anchor
    )
    outcomes = {ChannelId.POWER: selected_load, ChannelId.HEART_RATE: hr_load}

    tight_settings = FlagSettings(divergence_max_intensity_delta=0.05)
    tight_kwargs = _default_kwargs(outcomes=outcomes, settings=tight_settings)
    tight_flags = evaluate_flags(**tight_kwargs)  # type: ignore[arg-type]
    tight_by_key = {flag.key: flag for flag in tight_flags}
    assert tight_by_key[FlagKey.CHANNEL_DIVERGENCE.value].verdict == "detected"

    loose_settings = FlagSettings(divergence_max_intensity_delta=0.50)
    loose_kwargs = _default_kwargs(outcomes=outcomes, settings=loose_settings)
    loose_flags = evaluate_flags(**loose_kwargs)  # type: ignore[arg-type]
    loose_by_key = {flag.key: flag for flag in loose_flags}
    assert loose_by_key[FlagKey.CHANNEL_DIVERGENCE.value].verdict == "not-detected"


def test_staleness_window_days_argument_is_threaded_through() -> None:
    anchor = _benchmark(ACTIVITY_DATE - timedelta(days=50))
    selected_load = _channel_load(
        channel=ChannelId.POWER, intensity=0.9, load=200.0, anchor=anchor
    )
    outcomes = {ChannelId.POWER: selected_load}

    tight_kwargs = _default_kwargs(outcomes=outcomes, staleness_window_days=10)
    tight_flags = evaluate_flags(**tight_kwargs)  # type: ignore[arg-type]
    tight_by_key = {flag.key: flag for flag in tight_flags}
    assert tight_by_key[FlagKey.BENCHMARK_STALENESS.value].verdict == "detected"

    loose_kwargs = _default_kwargs(outcomes=outcomes, staleness_window_days=365)
    loose_flags = evaluate_flags(**loose_kwargs)  # type: ignore[arg-type]
    loose_by_key = {flag.key: flag for flag in loose_flags}
    assert loose_by_key[FlagKey.BENCHMARK_STALENESS.value].verdict == "not-detected"


def test_activity_date_argument_is_threaded_through() -> None:
    kwargs_with_date = _default_kwargs()
    flags_with_date = evaluate_flags(**kwargs_with_date)  # type: ignore[arg-type]
    by_key_with_date = {flag.key: flag for flag in flags_with_date}
    with_date_verdict = by_key_with_date[FlagKey.BENCHMARK_STALENESS.value].verdict
    assert with_date_verdict != "not-assessed"

    kwargs_without_date = _default_kwargs(activity_date=None)
    flags_without_date = evaluate_flags(**kwargs_without_date)  # type: ignore[arg-type]
    by_key_without_date = {flag.key: flag for flag in flags_without_date}
    without_date_flag = by_key_without_date[FlagKey.BENCHMARK_STALENESS.value]
    assert without_date_flag.verdict == "not-assessed"


# ---------------------------------------------------------------------------
# Exhaustive outcome-to-verdict mapping coverage: call each mapping function
# with every real enum member and assert BOTH that the mapping's key-set is
# total over that check's own closed outcome enum AND (reviewer finding 7)
# the *specific* expected verdict per member -- a per-member assertion the
# pure key-set-equality check is a tautology against (it cannot fail under
# any total mapping, correct or not; a cross-wired or constant-valued
# mapping still passes it). The `assert_never` fold itself is a static,
# mypy-enforced property (a member with no `case` is a type error under
# `mypy --strict`, verified by this task's own `uv run mypy` run recorded
# in its status report) -- it is not, and this module does not claim it is,
# something a runtime test inspects the source for.
# ---------------------------------------------------------------------------


def test_cadence_outcome_mapping_is_total_and_correct_per_member() -> None:
    from fitdocs.load.qa.flags import _cadence_verdict

    seen = {member: _cadence_verdict(member) for member in CadenceLockOutcome}
    assert set(seen) == set(CadenceLockOutcome)
    assert _cadence_verdict(CadenceLockOutcome.LOCKED) == "detected"
    assert _cadence_verdict(CadenceLockOutcome.CLEAR) == "not-detected"
    assert _cadence_verdict(CadenceLockOutcome.NOT_ASSESSED) == "not-assessed"


def test_divergence_outcome_mapping_is_total_and_correct_per_member() -> None:
    from fitdocs.load.qa.flags import _divergence_verdict

    seen = {member: _divergence_verdict(member) for member in DivergenceOutcome}
    assert set(seen) == set(DivergenceOutcome)
    assert _divergence_verdict(DivergenceOutcome.DIVERGENT) == "detected"
    assert _divergence_verdict(DivergenceOutcome.AGREED) == "not-detected"
    assert _divergence_verdict(DivergenceOutcome.NOT_ASSESSED) == "not-assessed"


def test_drift_outcome_mapping_is_total_and_correct_per_member() -> None:
    from fitdocs.load.qa.flags import _drift_verdict

    seen = {member: _drift_verdict(member) for member in DriftOutcome}
    assert set(seen) == set(DriftOutcome)
    assert _drift_verdict(DriftOutcome.DRIFTED) == "detected"
    assert _drift_verdict(DriftOutcome.COUPLED) == "not-detected"
    assert _drift_verdict(DriftOutcome.NOT_ASSESSED) == "not-assessed"


def test_staleness_outcome_mapping_is_total_and_correct_per_member() -> None:
    from fitdocs.load.qa.flags import _staleness_verdict

    seen = {member: _staleness_verdict(member) for member in StalenessOutcome}
    assert set(seen) == set(StalenessOutcome)
    assert _staleness_verdict(StalenessOutcome.STALE) == "detected"
    assert _staleness_verdict(StalenessOutcome.CURRENT) == "not-detected"
    assert _staleness_verdict(StalenessOutcome.NOT_ASSESSED) == "not-assessed"


def test_staleness_retroactive_maps_to_not_detected_specifically() -> None:
    from fitdocs.load.qa.flags import _staleness_verdict

    assert _staleness_verdict(StalenessOutcome.RETROACTIVE) == "not-detected"
