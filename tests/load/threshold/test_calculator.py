"""Contract tests for :mod:`fitdocs.load.threshold.calculator`'s
``ThresholdCalculator`` responsibility (task 3.3, design:
``ThresholdCalculator``, Req 1.4-1.7, 2.2, 2.3, 2.5, 2.7, 4.2, 4.3, 5.1-5.4,
6.7, 9.4-9.7, 10.1, 10.2, 10.5, 10.6).

``supports`` and ``compute`` implement the fixed decision sequence -- sport
check, date check, resolve anchors, evaluate all three channels, select,
assemble or explain -- documented in full on ``ThresholdCalculator.compute``
and in ``calculator.py``'s module docstring (including the deliberate
sport-AND-modality reading of ``supports`` that Task 3.3's task brief calls
out as a design.md/reality conflict).

These tests are built to defeat, not merely exercise -- see the docstring on
each test group below for the specific confusion it is built to catch. The
headline traps, called out once here rather than per-test:

- **order is the whole point of the six-step sequence.** A fixture that only
  ever satisfies one branch (e.g. an unsupported sport that also happens to
  carry a date) proves nothing about *precedence* -- every ordering test
  below deliberately satisfies two branches at once so only the fixed order
  decides the outcome.
- **all three channels are evaluated regardless of the configured order.**
  Proven positively: a Run selected on Pace still carries a real Heart-rate
  *value* (not just a reason) among its non-selected diagnostics.
- **``MissingInputs`` fields are declaration order, not configured-channel
  order and not alphabetical.** The one distinguishing fixture below uses a
  configured order that is the reverse of ``ATHLETE_FIELDS``' declaration
  order for the fields it triggers, and confirms alphabetical order would
  *also* differ -- see that test's own docstring for why "resolution order"
  (the fixed ftp/lthr/threshold_pace/max_hr/resting_hr sequence
  ``anchors.resolve`` always walks in) cannot be distinguished from
  declaration order by any fixture: ``ATHLETE_FIELDS`` was deliberately
  authored in that same conceptual sequence, so the two coincide by
  construction for any single supported sport.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import pytest

from fitdocs import Activity, DerivedMetrics, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import heart_rate_compute, pace_compute, power_compute
from fitdocs.load.channels.types import ChannelId, ChannelLoad, SufficiencySettings
from fitdocs.load.priority import ChannelPriority
from fitdocs.load.qa import FlagSettings, evaluate_flags
from fitdocs.load.settings import DEFAULT_STALENESS_WINDOW_DAYS, LoadSettings
from fitdocs.load.threshold.anchors import resolve
from fitdocs.load.threshold.calculator import (
    ATHLETE_FIELDS,
    CALCULATOR_ID,
    DISPLAY_NAME,
    THRESHOLD_CALCULATOR,
    ThresholdCalculator,
    build_result,
)
from fitdocs.load.threshold.discipline import DECLARED_MODALITIES, SUPPORTED_SPORTS
from fitdocs.load.types import (
    Computed,
    LoadContext,
    MissingInputs,
    NotComputed,
    QualityFlag,
    Unsupported,
)
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


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


def _empty_samples(n: int = 2) -> Samples:
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=tuple(float(i) for i in range(n)),
        heart_rate_bpm=none_ints,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _rich_samples(
    n_seconds: int = 600,
    *,
    heart_rate_bpm: int | None = 150,
    power_w: int | None = 200,
    speed_mps: float | None = 4.0,
) -> Samples:
    """A stream long enough (default 600 s >> the 60 s default minimum) and
    fully covered on every channel this feature scores, so power, heart-rate
    and pace can all independently compute a load. Passing ``None`` for a
    channel keeps it entirely unrecorded (all-``None``), for the tests that
    need exactly one channel to fail on data rather than on benchmarks. No
    altitude stream, so the pace channel never applies grade adjustment --
    irrelevant to this feature's own boundary."""
    n = n_seconds + 1
    time_s = tuple(float(i) for i in range(n))
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    hr = (heart_rate_bpm,) * n if heart_rate_bpm is not None else none_ints
    power = (power_w,) * n if power_w is not None else none_ints
    distance: tuple[float | None, ...]
    if speed_mps is not None:
        distance = tuple(speed_mps * i for i in range(n))
    else:
        distance = none_floats
    return Samples(
        time_s=time_s,
        heart_rate_bpm=hr,
        power_w=power,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=distance,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _activity(
    *,
    sport: Sport,
    modality: Modality,
    samples: Samples,
    start_time: datetime | None = None,
) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=start_time,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


def _rich_metrics(
    *, normalized_power_w: float | None = 200.0, moving_time_s: float | None = 600.0
) -> DerivedMetrics:
    return DerivedMetrics(
        normalized_power_w=normalized_power_w, moving_time_s=moving_time_s
    )


def _bm(
    kind: BenchmarkKind, discipline: Sport | None, value: float, day: date
) -> Benchmark:
    return Benchmark(kind=kind, discipline=discipline, value=value, measured_on=day)


class StubProfile:
    """A :class:`ProfileView` backed by an in-memory list of benchmarks,
    honoring the store's real "applicable on or before ``on``" and "on file
    at all" semantics -- so :func:`~fitdocs.load.threshold.anchors.resolve`
    behaves exactly as it would against the real store, without pulling in
    ``athlete-benchmarks``."""

    def __init__(self, benchmarks: Sequence[Benchmark] = ()) -> None:
        self._benchmarks = tuple(benchmarks)

    def get_number(self, key: str) -> float | None:
        return None

    def _matching(
        self, kind: BenchmarkKind, discipline: Sport | None
    ) -> tuple[Benchmark, ...]:
        return tuple(
            b for b in self._benchmarks if b.kind == kind and b.discipline == discipline
        )

    def benchmark(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date | None
    ) -> Benchmark | None:
        candidates = [
            b
            for b in self._matching(kind, discipline)
            if on is not None and b.measured_on <= on
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda b: b.measured_on)

    def has_benchmark(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        return bool(self._matching(kind, discipline))


class RaisingSession:
    """An :class:`InteractionSession` double that raises on **any** attribute
    access, so any use of ``session`` by ``compute`` -- not only a call, an
    attribute lookup too -- is a hard failure rather than a silently
    tolerated no-op (Req 9.7)."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(
            f"ThresholdCalculator.compute must never touch session.{name}"
        )


def _context(
    *,
    activity_date: date | None,
    channel_priority: ChannelPriority | None = None,
    sufficiency: SufficiencySettings | None = None,
    benchmark_staleness_days: int | None = None,
    flags: FlagSettings | None = None,
) -> LoadContext:
    settings = LoadSettings(
        default_calculator=None,
        sufficiency=sufficiency if sufficiency is not None else SufficiencySettings(),
        channel_priority=(
            channel_priority if channel_priority is not None else ChannelPriority()
        ),
        benchmark_staleness_days=(
            benchmark_staleness_days
            if benchmark_staleness_days is not None
            else DEFAULT_STALENESS_WINDOW_DAYS
        ),
        flags=flags if flags is not None else FlagSettings(),
    )
    return LoadContext(activity_date=activity_date, settings=settings)


_DATE = date(2026, 6, 1)

_FULL_RUN_BENCHMARKS = (
    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2026, 1, 1)),
    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 170.0, date(2026, 1, 1)),
    _bm(BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 240.0, date(2026, 1, 1)),
    _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2026, 1, 1)),
    _bm(BenchmarkKind.RESTING_HR_BPM, None, 50.0, date(2026, 1, 1)),
)

_POWER_THEN_HR_ORDER = ChannelPriority(
    by_discipline={Sport.RUN: (ChannelId.POWER, ChannelId.HEART_RATE)}
)
"""A configured order excluding pace, shared by the ``MissingInputs`` /
``NotComputed`` distinguishing tests below."""

_LATE_FTP_PLUS_HR_BENCHMARKS = (
    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2030, 1, 1)),  # not_applicable
    _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 170.0, date(2026, 1, 1)),
    _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2026, 1, 1)),
    _bm(BenchmarkKind.RESTING_HR_BPM, None, 50.0, date(2026, 1, 1)),
    # threshold_pace deliberately absent (not_on_file), but PACE is excluded
    # from `_POWER_THEN_HR_ORDER`.
)


def _run_activity(**kwargs: object) -> Activity:
    samples = kwargs.pop("samples", None) or _rich_samples()
    return _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        samples=samples,
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Module-level constants and the shipped instance
# ---------------------------------------------------------------------------


def test_calculator_id_and_display_name() -> None:
    assert CALCULATOR_ID == "threshold"
    assert DISPLAY_NAME == "Threshold Load"
    calc = ThresholdCalculator()
    assert calc.calculator_id == CALCULATOR_ID
    assert calc.display_name == DISPLAY_NAME
    assert calc.supported_modalities == DECLARED_MODALITIES


def test_threshold_calculator_shipped_instance_is_a_default_construction() -> None:
    assert ThresholdCalculator() == THRESHOLD_CALCULATOR


# ---------------------------------------------------------------------------
# supports() -- Req 2.5, 2.6, 2.7; probe 8
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sport", "modality"),
    [
        (Sport.RUN, Modality.RUN),
        (Sport.RIDE, Modality.BIKE),
        (Sport.WALK, Modality.OTHER),
        (Sport.HIKE, Modality.OTHER),
    ],
)
def test_supports_true_for_the_four_supported_sports(
    sport: Sport, modality: Modality
) -> None:
    activity = _activity(sport=sport, modality=modality, samples=_empty_samples())
    assert ThresholdCalculator().supports(activity) is True


@pytest.mark.parametrize(
    ("sport", "modality"),
    [
        (Sport.ROWING, Modality.OTHER),
        (Sport.WORKOUT, Modality.OTHER),
        (Sport.SWIM, Modality.SWIM),
    ],
)
def test_supports_false_for_unsupported_sports_inside_declared_modalities(
    sport: Sport, modality: Modality
) -> None:
    """Rowing and Workout sit inside the declared catch-all ``Modality.OTHER``
    -- the sport set, not the modality set, is what refuses them (Req 2.5)."""
    activity = _activity(sport=sport, modality=modality, samples=_empty_samples())
    assert ThresholdCalculator().supports(activity) is False


def test_supports_false_for_strength_training_despite_run_sport() -> None:
    """The design-vs-reality conflict this task resolves: ``Sport`` has no
    strength member, so ``detect_sport("running", "strength_training")``
    yields ``(Sport.RUN, Modality.STRENGTH)`` -- a sport-only ``supports``
    answers ``True`` here, widening past ``DECLARED_MODALITIES``. Answering
    from sport AND modality refuses it (Req 2.2)."""
    activity = _activity(
        sport=Sport.RUN, modality=Modality.STRENGTH, samples=_empty_samples()
    )
    assert Sport.RUN in SUPPORTED_SPORTS  # the sport alone would admit this
    assert Modality.STRENGTH not in DECLARED_MODALITIES
    assert ThresholdCalculator().supports(activity) is False


def test_supports_false_for_unrecognized_sport() -> None:
    activity = _activity(
        sport=Sport.WORKOUT, modality=Modality.OTHER, samples=_empty_samples()
    )
    assert ThresholdCalculator().supports(activity) is False


@pytest.mark.parametrize(
    ("sport", "modality"),
    [
        (Sport.ROWING, Modality.OTHER),
        (Sport.WORKOUT, Modality.OTHER),
        (Sport.SWIM, Modality.SWIM),
        (Sport.RUN, Modality.STRENGTH),
    ],
)
def test_supports_agrees_with_what_compute_refuses(
    sport: Sport, modality: Modality
) -> None:
    """The support answer and ``compute``'s own defence-in-depth sport-AND-
    modality check must agree for every activity ``supports`` refuses (Req
    2.7) -- including a strength-labelled Run, whose sport alone would be
    admitted but whose modality is not declared (Req 2.2)."""
    activity = _activity(sport=sport, modality=modality, samples=_empty_samples())
    calc = ThresholdCalculator()
    assert calc.supports(activity) is False
    outcome = calc.compute(
        activity,
        DerivedMetrics(),
        StubProfile(),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Unsupported)
    assert str(sport) in outcome.reason


def test_compute_refuses_a_strength_labelled_run_with_no_computed_value() -> None:
    """Req 2.2: ``compute`` shall return the unsupported outcome naming the
    sport and shall NOT compute a heart-rate-derived value for it.
    ``detect_sport("running", "strength_training")`` yields exactly this
    ``(Sport.RUN, Modality.STRENGTH)`` pair -- rich heart-rate and power
    streams are present and a full run benchmark set is on file, so a
    sport-only step-1 check would compute a heart-rate-derived load here;
    the sport-AND-modality conjunction must refuse before any channel is
    evaluated at all."""
    activity = _activity(
        sport=Sport.RUN, modality=Modality.STRENGTH, samples=_rich_samples()
    )
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Unsupported)
    assert not isinstance(outcome, Computed)
    assert "Run" in outcome.reason


# ---------------------------------------------------------------------------
# compute() sequencing -- probe 1: sport check precedes date check
# ---------------------------------------------------------------------------


def test_unsupported_sport_with_no_date_is_unsupported_not_not_computed() -> None:
    """Satisfies *two* branch conditions at once (unsupported sport AND no
    date) so only the fixed order -- sport check first -- decides which
    outcome comes back."""
    activity = _activity(
        sport=Sport.ROWING, modality=Modality.OTHER, samples=_empty_samples()
    )
    outcome = ThresholdCalculator().compute(
        activity,
        DerivedMetrics(),
        StubProfile(),
        RaisingSession(),
        _context(activity_date=None),
    )
    assert isinstance(outcome, Unsupported)
    assert "Rowing" in outcome.reason


def test_supported_sport_with_no_date_is_not_computed_naming_the_date() -> None:
    activity = _run_activity()
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=None),
    )
    assert isinstance(outcome, NotComputed)
    assert "date" in outcome.reason.lower()


def test_unsupported_sport_reason_names_the_sport() -> None:
    activity = _activity(
        sport=Sport.WORKOUT, modality=Modality.OTHER, samples=_empty_samples()
    )
    outcome = ThresholdCalculator().compute(
        activity,
        DerivedMetrics(),
        StubProfile(),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Unsupported)
    assert "Workout" in outcome.reason


# ---------------------------------------------------------------------------
# All three channels are always evaluated -- Req 5.1; probe 2
# ---------------------------------------------------------------------------


def test_a_run_with_power_heart_rate_and_distance_produces_three_outcomes() -> None:
    activity = _run_activity()
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Computed)
    # Default running order is pace > power > heart rate: selection is pace.
    assert outcome.result.basis == ChannelId.PACE.value
    non_selected_keys = {v.key for v in outcome.result.non_selected}
    assert non_selected_keys == {ChannelId.POWER.value, ChannelId.HEART_RATE.value}


def test_a_run_selected_on_pace_still_records_a_heart_rate_value() -> None:
    """A mutation that stops evaluating channels once one succeeds must red
    this: the heart-rate value must be present, not merely a reason, even
    though pace wins the selection (the comparison the planned quality-flag
    feature consumes)."""
    activity = _run_activity()
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.PACE.value
    hr_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.HEART_RATE.value
    )
    assert hr_record.value is not None
    assert hr_record.value > 0.0


def test_computed_value_and_intensity_are_the_selected_channels_own_exactly() -> None:
    """Req 5.4: ``compute`` applies no rounding and no rescaling of a
    channel's reported load or intensity. Recomputes the winning channel
    (Pace, on the default Run order) directly against the same anchors and
    settings, and asserts the assembled result carries that channel's
    ``load``/``intensity`` byte-for-byte -- not merely a plausible-looking
    float. A ``round(...)`` or a ``* 2.0`` rescale inserted before
    ``build_result`` changes either value and reds this assertion; neither
    is visible to a test that only calls ``build_result`` directly, since
    that call cannot see an adjustment ``compute`` applies before it."""
    activity = _run_activity()
    metrics = _rich_metrics()
    profile = StubProfile(_FULL_RUN_BENCHMARKS)
    context = _context(activity_date=_DATE)
    outcome = ThresholdCalculator().compute(
        activity, metrics, profile, RaisingSession(), context
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.PACE.value

    anchors = resolve(profile, sport=Sport.RUN, on=_DATE)
    expected = pace_compute(
        activity,
        metrics,
        threshold_pace=anchors.threshold_pace,
        settings=context.settings.sufficiency,
    )
    assert isinstance(expected, ChannelLoad)
    assert outcome.result.value == expected.load
    intensity_input = next(v for k, v in outcome.result.inputs_used if k == "Intensity")
    assert intensity_input == f"{expected.intensity:.3f}"


# ---------------------------------------------------------------------------
# Config is read from context, not from defaults -- Req 1.6; probe 7
# ---------------------------------------------------------------------------


def test_non_default_channel_priority_changes_the_selection() -> None:
    """A run's default order prefers pace; a non-default order preferring
    heart rate first must select heart rate instead. Substituting
    ``ChannelPriority()`` (the default) for the configured value would
    select pace and red this assertion."""
    activity = _run_activity()
    non_default_order = ChannelPriority(
        by_discipline={
            Sport.RUN: (ChannelId.HEART_RATE, ChannelId.PACE, ChannelId.POWER)
        }
    )
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=non_default_order),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.HEART_RATE.value
    # The configured (non-default) order must reach build_result verbatim,
    # not the module's own DEFAULT_CHANNEL_PRIORITY value for Run -- a
    # hardcoded `order=(POWER, HEART_RATE, PACE)` would still select heart
    # rate -- not because it leads that tuple (POWER does), but because the
    # mutation replaces only build_result's argument while select() keeps
    # walking the configured order -- and would print a visibly wrong
    # ordering.
    selection_order_input = dict(outcome.result.inputs_used)["Selection order"]
    assert selection_order_input == " > ".join(
        entry.value for entry in non_default_order.by_discipline[Sport.RUN]
    )
    pace_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.PACE.value
    )
    assert pace_record.reason == (
        "not selected: the configured order for Run prefers Heart rate"
    )
    # Sanity: the DEFAULT order would have selected pace instead (proves the
    # non-default fixture actually differs in effect, not only in value).
    default_outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(default_outcome, Computed)
    assert default_outcome.result.basis == ChannelId.PACE.value


def test_ride_non_selected_reason_names_ride_not_run() -> None:
    """A ``discipline=sport`` argument hardcoded to ``Sport.RUN`` at the
    ``build_result`` call site is invisible to every Run fixture in this
    module -- Run is already the value that would be hardcoded. A Ride whose
    Power AND Heart-rate channels both compute (default Ride order prefers
    Power) is the one fixture that can tell the two apart: the Heart-rate
    non-selected reason must name Ride, never Run."""
    activity = _activity(
        sport=Sport.RIDE,
        modality=Modality.BIKE,
        samples=_rich_samples(),
    )
    benchmarks = (
        _bm(BenchmarkKind.FTP_WATTS, Sport.RIDE, 250.0, date(2026, 1, 1)),
        _bm(BenchmarkKind.LTHR_BPM, Sport.RIDE, 165.0, date(2026, 1, 1)),
        _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2026, 1, 1)),
        _bm(BenchmarkKind.RESTING_HR_BPM, None, 50.0, date(2026, 1, 1)),
    )
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(benchmarks),
        RaisingSession(),
        _context(activity_date=_DATE),  # default Ride order: power > heart rate
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.POWER.value
    hr_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.HEART_RATE.value
    )
    assert hr_record.value is not None  # heart rate genuinely computed
    assert "for Ride" in hr_record.reason
    assert "for Run" not in hr_record.reason


def test_non_default_sufficiency_minimum_reaches_the_channels() -> None:
    """A minimum duration far above the fixture's 600 s must flip every
    channel to insufficient (``TOO_SHORT``), so the whole activity goes
    unselected -- substituting the default ``SufficiencySettings()`` would
    compute normally and red this assertion."""
    activity = _run_activity()
    strict = SufficiencySettings(min_duration_s=10_000)
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE, sufficiency=strict),
    )
    assert isinstance(outcome, NotComputed)
    assert "too_short" not in outcome.reason  # reason is prose, not the enum value
    for label in ("Power", "Heart rate", "Pace"):
        assert label in outcome.reason

    # Sanity: the DEFAULT sufficiency computes normally on the same activity.
    default_outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(default_outcome, Computed)


# ---------------------------------------------------------------------------
# 4.1: context.activity_date, never activity.start_time
# ---------------------------------------------------------------------------


def test_uses_context_activity_date_not_activity_start_time() -> None:
    """``start_time`` is given a UTC calendar date that DIFFERS from
    ``context.activity_date``: an FTP measured strictly between the two
    dates resolves as applicable only if the context date -- not the start
    time -- is what is compared against. Sourcing from ``start_time`` would
    treat the benchmark as not-yet-applicable and red this assertion."""
    context_date = date(2026, 6, 15)
    start_time = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)  # far earlier UTC date
    activity = _run_activity(start_time=start_time)
    ftp_measured_between = _bm(
        BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2026, 3, 1)
    )
    profile = StubProfile((ftp_measured_between,))
    power_only = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        profile,
        RaisingSession(),
        _context(activity_date=context_date, channel_priority=power_only),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.POWER.value


def test_uses_context_activity_date_not_the_wall_clock() -> None:
    """The benchmark is measured strictly AFTER ``context.activity_date`` but
    strictly BEFORE today's date, so a substitution of ``date.today()`` for
    ``context.activity_date`` would make the benchmark wrongly applicable, so
    the outcome becomes ``Computed`` and this test's assertion reds. Both the
    fixture's context date and the benchmark date are far in the past relative
    to any plausible ``today`` the suite could run under."""
    context_date = date(2020, 6, 15)
    activity = _run_activity()
    ftp_measured_later = _bm(
        BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2020, 7, 1)
    )
    profile = StubProfile((ftp_measured_later,))
    power_only = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        profile,
        RaisingSession(),
        _context(activity_date=context_date, channel_priority=power_only),
    )
    # Positive form pins *why* the activity is unscored -- the benchmark is on
    # file but not yet in force -- rather than merely that it is: any breakage
    # preventing a computed result would satisfy a bare negative.
    assert isinstance(outcome, NotComputed)
    assert not isinstance(outcome, Computed)


# ---------------------------------------------------------------------------
# session is never used -- Req 9.7; probe 6
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sport", "modality", "activity_date", "benchmarks"),
    [
        (Sport.ROWING, Modality.OTHER, _DATE, ()),
        (Sport.RUN, Modality.RUN, None, ()),
        (Sport.RUN, Modality.RUN, _DATE, _FULL_RUN_BENCHMARKS),
        (Sport.RUN, Modality.RUN, _DATE, ()),
    ],
)
def test_session_is_never_touched(
    sport: Sport,
    modality: Modality,
    activity_date: date | None,
    benchmarks: tuple[Benchmark, ...],
) -> None:
    samples = _rich_samples() if sport == Sport.RUN else _empty_samples()
    activity = _activity(sport=sport, modality=modality, samples=samples)
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(benchmarks),
        RaisingSession(),
        _context(activity_date=activity_date),
    )
    assert outcome is not None  # RaisingSession would have raised, not returned


# ---------------------------------------------------------------------------
# Never raises -- Req 1.7; probe 9
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sport", "modality", "samples", "activity_date", "benchmarks"),
    [
        (Sport.ROWING, Modality.OTHER, _empty_samples(), _DATE, ()),
        (Sport.WORKOUT, Modality.OTHER, _empty_samples(), _DATE, ()),
        (Sport.RUN, Modality.RUN, _empty_samples(), _DATE, ()),
        (Sport.RUN, Modality.RUN, _empty_samples(), None, ()),
        (Sport.RUN, Modality.RUN, _rich_samples(), _DATE, _FULL_RUN_BENCHMARKS),
        (Sport.WALK, Modality.OTHER, _empty_samples(), _DATE, ()),
    ],
)
def test_compute_never_raises(
    sport: Sport,
    modality: Modality,
    samples: Samples,
    activity_date: date | None,
    benchmarks: tuple[Benchmark, ...],
) -> None:
    activity = _activity(sport=sport, modality=modality, samples=samples)
    outcome = ThresholdCalculator().compute(
        activity,
        DerivedMetrics(),
        StubProfile(benchmarks),
        RaisingSession(),
        _context(activity_date=activity_date),
    )
    assert isinstance(outcome, (Computed, Unsupported, MissingInputs, NotComputed))


# ---------------------------------------------------------------------------
# MissingInputs vs NotComputed -- Req 9.4, 9.5; probe 3, step 5 precedes 6
# ---------------------------------------------------------------------------


def test_missing_inputs_when_a_configured_channel_has_no_benchmark_on_file() -> None:
    activity = _run_activity()
    order = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(()),  # nothing on file at all
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=order),
    )
    assert isinstance(outcome, MissingInputs)
    assert outcome.fields == (
        next(f for f in ATHLETE_FIELDS if f.key == "benchmarks.run.ftp_watts"),
    )


def test_not_computed_not_missing_inputs_when_benchmark_postdates_activity() -> None:
    """Req 9.5: on file, just not applicable to this date -- must be
    ``NotComputed``, distinguishing this from the never-provided case above.
    Swapping ``not_applicable`` for ``not_on_file`` in the source would make
    this MissingInputs and red."""
    activity = _run_activity()
    order = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    late_ftp = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2030, 1, 1))
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile((late_ftp,)),
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=order),
    )
    assert isinstance(outcome, NotComputed)
    assert not isinstance(outcome, MissingInputs)


def test_missing_inputs_fields_are_in_declaration_order() -> None:
    """Three quantities are simultaneously blocked by a genuinely absent
    benchmark: threshold pace, LTHR (plus max/resting HR), and FTP. The
    configured channel order is PACE, HEART_RATE, POWER -- the exact
    *reverse* of these fields' relative position in ``ATHLETE_FIELDS``
    (FTP < LTHR < pace < max_hr < resting_hr) -- and alphabetical order by
    label ("Maximum...", "Resting...", "Running FTP...", "Running LTHR...",
    "Running threshold pace...") differs from both. Only declaration order
    survives all three permutations.

    ("Resolution order" -- the fixed ftp/lthr/threshold_pace/max_hr/
    resting_hr sequence ``anchors.resolve`` always walks in -- cannot be
    distinguished from declaration order by any fixture for a single sport:
    ``ATHLETE_FIELDS`` was deliberately authored in that same conceptual
    sequence, so the two coincide by construction here. That pairing is
    UNPINNED by this suite for exactly that structural reason.)
    """
    activity = _run_activity()
    order = ChannelPriority(
        by_discipline={
            Sport.RUN: (ChannelId.PACE, ChannelId.HEART_RATE, ChannelId.POWER)
        }
    )
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(()),  # nothing on file: every quantity is not_on_file
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=order),
    )
    assert isinstance(outcome, MissingInputs)
    expected_keys = [
        "benchmarks.run.ftp_watts",
        "benchmarks.run.lthr_bpm",
        "benchmarks.run.threshold_pace_s_per_km",
        "benchmarks.athlete.max_hr_bpm",
        "benchmarks.athlete.resting_hr_bpm",
    ]
    assert [f.key for f in outcome.fields] == expected_keys
    # The channel-order (reverse) and alphabetical orderings, spelled out so
    # the assertion above cannot be satisfied by accident:
    channel_order_keys = [
        "benchmarks.run.threshold_pace_s_per_km",
        "benchmarks.run.lthr_bpm",
        "benchmarks.athlete.max_hr_bpm",
        "benchmarks.athlete.resting_hr_bpm",
        "benchmarks.run.ftp_watts",
    ]
    alphabetical_keys = sorted(
        expected_keys,
        key=lambda k: next(f.label for f in ATHLETE_FIELDS if f.key == k),
    )
    assert [f.key for f in outcome.fields] != channel_order_keys
    assert [f.key for f in outcome.fields] != alphabetical_keys


def test_missing_inputs_only_counts_channels_in_the_configured_order() -> None:
    """A quantity that is genuinely not on file, but whose sole consuming
    channel is EXCLUDED from the configured order, must not trigger
    ``MissingInputs`` -- that channel can never be selected regardless."""
    activity_no_hr = _run_activity(samples=_rich_samples(heart_rate_bpm=None))
    outcome = ThresholdCalculator().compute(
        activity_no_hr,
        _rich_metrics(),
        StubProfile(_LATE_FTP_PLUS_HR_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=_POWER_THEN_HR_ORDER),
    )
    assert isinstance(outcome, NotComputed)
    assert not isinstance(outcome, MissingInputs)


def test_missing_inputs_requires_the_no_benchmark_reason_specifically() -> None:
    """A channel can be insufficient for a reason OTHER than
    ``NO_BENCHMARK`` while its own consumed quantity is genuinely
    ``not_on_file`` -- Pace's own evaluation order checks the activity's
    modality BEFORE it ever looks at the benchmark, so a Run activity built
    with a non-running modality reports ``MODEL_NOT_DEFINED`` for Pace even
    though Running threshold pace is absent from the profile entirely. That
    must NOT count toward ``MissingInputs`` -- only a channel whose own
    reason is ``NO_BENCHMARK`` may. Deleting the ``reason is not
    InsufficiencyReason.NO_BENCHMARK`` guard in ``_missing_inputs`` makes
    this ``MissingInputs`` instead."""
    activity = _activity(
        sport=Sport.RUN, modality=Modality.OTHER, samples=_rich_samples()
    )
    order = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.PACE,)})
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(()),  # nothing on file: threshold pace is not_on_file
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=order),
    )
    assert isinstance(outcome, NotComputed)
    assert not isinstance(outcome, MissingInputs)


# ---------------------------------------------------------------------------
# NotComputed reason names every channel, in CANONICAL_CHANNELS order --
# Req 10.1, 10.2; probe 4, step 5 precedes 6 (a not-on-file entry exists but
# does not gate MissingInputs since its channel is excluded from order)
# ---------------------------------------------------------------------------


def test_not_computed_reason_names_every_channel_distinctly_and_in_order() -> None:
    activity = _run_activity(samples=_rich_samples(heart_rate_bpm=None))
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(_LATE_FTP_PLUS_HR_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=_POWER_THEN_HR_ORDER),
    )
    assert isinstance(outcome, NotComputed)
    power_i = outcome.reason.index("Power:")
    hr_i = outcome.reason.index("Heart rate:")
    pace_i = outcome.reason.index("Pace:")
    assert power_i < hr_i < pace_i  # CANONICAL_CHANNELS order
    power_detail = outcome.reason[power_i:hr_i]
    hr_detail = outcome.reason[hr_i:pace_i]
    pace_detail = outcome.reason[pace_i:]
    assert power_detail != hr_detail
    assert hr_detail != pace_detail
    assert power_detail != pace_detail


# ---------------------------------------------------------------------------
# Determinism -- Req 1.4, 10.6; probe 10
# ---------------------------------------------------------------------------


def test_computed_outcome_is_identical_across_repeated_calls() -> None:
    activity = _run_activity()
    calc = ThresholdCalculator()
    profile = StubProfile(_FULL_RUN_BENCHMARKS)
    context = _context(activity_date=_DATE)
    metrics = _rich_metrics()
    first = calc.compute(activity, metrics, profile, RaisingSession(), context)
    second = calc.compute(activity, metrics, profile, RaisingSession(), context)
    assert isinstance(first, Computed)
    assert isinstance(second, Computed)
    assert first.result == second.result


def test_not_computed_reason_is_identical_across_repeated_calls() -> None:
    activity = _run_activity(samples=_rich_samples(heart_rate_bpm=None))
    calc = ThresholdCalculator()
    profile = StubProfile(_LATE_FTP_PLUS_HR_BENCHMARKS)
    context = _context(activity_date=_DATE, channel_priority=_POWER_THEN_HR_ORDER)
    metrics = _rich_metrics()
    first = calc.compute(activity, metrics, profile, RaisingSession(), context)
    second = calc.compute(activity, metrics, profile, RaisingSession(), context)
    assert isinstance(first, NotComputed)
    assert isinstance(second, NotComputed)
    assert first.reason == second.reason
    assert first.reason != ""


# ---------------------------------------------------------------------------
# Each channel receives an already-resolved Benchmark, and a borrowed anchor
# reaches the result -- proves compute() wires anchors.resolve() through to
# build_result rather than duplicating or short-circuiting it (Req 3.4, 4.2)
# ---------------------------------------------------------------------------


def test_walk_borrows_running_lthr_and_the_result_records_it() -> None:
    activity = _activity(
        sport=Sport.WALK,
        modality=Modality.OTHER,
        samples=_rich_samples(power_w=None, speed_mps=None),
    )
    benchmarks = (
        _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 170.0, date(2026, 1, 1)),
        _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2026, 1, 1)),
        _bm(BenchmarkKind.RESTING_HR_BPM, None, 50.0, date(2026, 1, 1)),
    )
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(benchmarks),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.HEART_RATE.value
    assert any("Run" in note and "Walk" in note for note in outcome.result.notes)
    # Req 6.7: the pace channel reports "not defined for this modality" as an
    # ordinary reason, carried forward verbatim -- never treated as an error
    # (a raise would have failed this test before reaching this line at all).
    pace_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.PACE.value
    )
    assert pace_record.value is None
    assert "modality" in pace_record.reason.lower()


# ---------------------------------------------------------------------------
# Computed despite an unrelated missing benchmark -- Req 9.6
# ---------------------------------------------------------------------------


def test_computed_result_not_missing_inputs_when_an_unrelated_benchmark_is_absent() -> (
    None
):
    """A Ride with power fully on file but LTHR entirely absent: the
    configured order prefers power, which computes and is selected, so the
    outcome must be ``Computed`` -- the absent (and, for this order,
    irrelevant to selection) LTHR must not be reported as missing inputs."""
    activity = _activity(
        sport=Sport.RIDE,
        modality=Modality.BIKE,
        samples=_rich_samples(),
    )
    benchmarks = (_bm(BenchmarkKind.FTP_WATTS, Sport.RIDE, 250.0, date(2026, 1, 1)),)
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        StubProfile(benchmarks),
        RaisingSession(),
        _context(activity_date=_DATE),  # default Ride order: power > heart rate
    )
    assert isinstance(outcome, Computed)
    assert not isinstance(outcome, MissingInputs)
    assert outcome.result.basis == ChannelId.POWER.value


# ---------------------------------------------------------------------------
# A not-computed/missing-inputs outcome is retryable -- Req 10.5
# ---------------------------------------------------------------------------


def test_not_computed_becomes_computed_once_the_missing_benchmark_is_supplied() -> None:
    """The calculator holds no state across calls: scoring the identical
    activity a second time, against a profile that now carries the
    previously-absent benchmark, computes normally."""
    activity = _run_activity()
    order = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    context = _context(activity_date=_DATE, channel_priority=order)
    calc = ThresholdCalculator()

    first = calc.compute(
        activity, _rich_metrics(), StubProfile(()), RaisingSession(), context
    )
    assert isinstance(first, MissingInputs)

    supplied = StubProfile(
        (_bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2026, 1, 1)),)
    )
    second = calc.compute(
        activity, _rich_metrics(), supplied, RaisingSession(), context
    )
    assert isinstance(second, Computed)
    assert second.result.basis == ChannelId.POWER.value


# ---------------------------------------------------------------------------
# The 11.x boundary: no import of anything outside the calculator's own
# dependency set at this module's own level is asserted in test_boundary.py
# (task 5.4), out of this task's scope -- not duplicated here.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CalculatorIntegration (task 3.2, Req 7.1-7.3, 7.5)
# ---------------------------------------------------------------------------


def test_computed_result_carries_four_flags_matching_evaluate_flags_directly() -> None:
    """Req 7.1: a computed result's ``flags`` is exactly what a direct call
    to ``evaluate_flags`` produces from the same inputs -- reconstructed
    independently here (not captured from the call ``compute`` itself made),
    so this proves the threading is correct end to end, not merely that
    *some* four flags were attached."""
    activity = _run_activity()
    metrics = _rich_metrics()
    profile = StubProfile(_FULL_RUN_BENCHMARKS)
    context = _context(activity_date=_DATE)

    outcome = ThresholdCalculator().compute(
        activity, metrics, profile, RaisingSession(), context
    )
    assert isinstance(outcome, Computed)
    assert len(outcome.result.flags) == 4

    anchors = resolve(profile, sport=Sport.RUN, on=_DATE)
    sufficiency = context.settings.sufficiency
    outcomes = {
        ChannelId.POWER: power_compute(
            activity, metrics, ftp=anchors.ftp, settings=sufficiency
        ),
        ChannelId.HEART_RATE: heart_rate_compute(
            activity,
            metrics,
            lthr=anchors.lthr,
            resting_hr=anchors.resting_hr,
            max_hr=anchors.max_hr,
            settings=sufficiency,
        ),
        ChannelId.PACE: pace_compute(
            activity,
            metrics,
            threshold_pace=anchors.threshold_pace,
            settings=sufficiency,
        ),
    }
    expected = evaluate_flags(
        activity=activity,
        metrics=metrics,
        outcomes=outcomes,
        selected=ChannelId.PACE,  # default Run order selects pace
        activity_date=_DATE,
        staleness_window_days=context.settings.benchmark_staleness_days,
        settings=context.settings.flags,
    )
    assert outcome.result.basis == ChannelId.PACE.value
    assert outcome.result.flags == expected


def test_flags_evaluated_only_on_the_computed_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 7.3: ``evaluate_flags`` is called exactly once, only on the path
    that reaches ``Computed`` -- never for ``Unsupported``, ``MissingInputs``
    or ``NotComputed``. Spies on the name ``calculator.py`` calls, so a
    mutation that adds a call on any non-computed path is caught regardless
    of what that call's arguments would be."""
    import fitdocs.load.threshold.calculator as calculator_module

    calls: list[object] = []
    real_evaluate_flags = calculator_module.evaluate_flags

    def _spy(**kwargs: object) -> tuple[QualityFlag, ...]:
        calls.append(kwargs)
        return real_evaluate_flags(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(calculator_module, "evaluate_flags", _spy)

    # Unsupported: strength-labelled run, refused before any date/channel work.
    unsupported_activity = _activity(
        sport=Sport.RUN, modality=Modality.STRENGTH, samples=_rich_samples()
    )
    unsupported_outcome = ThresholdCalculator().compute(
        unsupported_activity,
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(unsupported_outcome, Unsupported)
    assert calls == []

    # NotComputed: no activity date at all.
    no_date_outcome = ThresholdCalculator().compute(
        _run_activity(),
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        _context(activity_date=None),
    )
    assert isinstance(no_date_outcome, NotComputed)
    assert calls == []

    # MissingInputs: nothing on file at all for the one configured channel.
    order = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    missing_outcome = ThresholdCalculator().compute(
        _run_activity(),
        _rich_metrics(),
        StubProfile(()),
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=order),
    )
    assert isinstance(missing_outcome, MissingInputs)
    assert calls == []

    # NotComputed (evaluated-but-none-selected): benchmark postdates activity.
    late_ftp = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2030, 1, 1))
    postdated_outcome = ThresholdCalculator().compute(
        _run_activity(),
        _rich_metrics(),
        StubProfile((late_ftp,)),
        RaisingSession(),
        _context(activity_date=_DATE, channel_priority=order),
    )
    assert isinstance(postdated_outcome, NotComputed)
    assert calls == []

    # Computed: exactly one call, on the selected path.
    computed_context = _context(activity_date=_DATE)
    computed_outcome = ThresholdCalculator().compute(
        _run_activity(),
        _rich_metrics(),
        StubProfile(_FULL_RUN_BENCHMARKS),
        RaisingSession(),
        computed_context,
    )
    assert isinstance(computed_outcome, Computed)
    assert len(calls) == 1
    call_kwargs = calls[0]
    assert computed_outcome.result.flags == real_evaluate_flags(**call_kwargs)  # type: ignore[arg-type]

    # Structural threading proof (Req 7.1): each of the three per-pass-context
    # values reaches `evaluate_flags` genuinely, not defaulted or hardcoded.
    # `settings` is checked by identity -- `context.settings.flags` is a
    # single already-constructed `FlagSettings` instance, so substituting a
    # fresh default construction in `compute` would still pass an
    # *equality*-based check but fail this one.
    assert call_kwargs["activity_date"] == computed_context.activity_date  # type: ignore[index]
    assert (
        call_kwargs["staleness_window_days"]  # type: ignore[index]
        == computed_context.settings.benchmark_staleness_days
    )
    assert call_kwargs["settings"] is computed_context.settings.flags  # type: ignore[index]


def test_build_result_flags_reach_only_the_flags_field() -> None:
    """Req 7.2: two ``build_result`` calls with identical inputs except
    ``flags`` differ in the ``flags`` field and in no other -- the exact
    shape design.md's Invariants section calls for."""
    activity = _run_activity()
    metrics = _rich_metrics()
    profile = StubProfile(_FULL_RUN_BENCHMARKS)
    context = _context(activity_date=_DATE)
    anchors = resolve(profile, sport=Sport.RUN, on=_DATE)
    sufficiency = context.settings.sufficiency
    outcomes = {
        ChannelId.POWER: power_compute(
            activity, metrics, ftp=anchors.ftp, settings=sufficiency
        ),
        ChannelId.HEART_RATE: heart_rate_compute(
            activity,
            metrics,
            lthr=anchors.lthr,
            resting_hr=anchors.resting_hr,
            max_hr=anchors.max_hr,
            settings=sufficiency,
        ),
        ChannelId.PACE: pace_compute(
            activity,
            metrics,
            threshold_pace=anchors.threshold_pace,
            settings=sufficiency,
        ),
    }
    order = context.settings.channel_priority.for_discipline(Sport.RUN)
    selected = outcomes[ChannelId.PACE]
    assert isinstance(selected, ChannelLoad)

    real_flags = (
        QualityFlag(
            key="cadence-lock", label="Cadence lock", verdict="not-assessed", detail="x"
        ),
    )

    without_flags = build_result(
        selected=selected,
        outcomes=outcomes,
        order=order,
        anchors=anchors,
        discipline=Sport.RUN,
    )
    with_flags = build_result(
        selected=selected,
        outcomes=outcomes,
        order=order,
        anchors=anchors,
        discipline=Sport.RUN,
        flags=real_flags,
    )

    assert without_flags.flags == ()
    assert with_flags.flags == real_flags
    for field_name in (
        "calculator_id",
        "display_name",
        "value",
        "basis",
        "non_selected",
        "inputs_used",
        "notes",
    ):
        assert getattr(without_flags, field_name) == getattr(with_flags, field_name), (
            field_name
        )


def test_non_default_staleness_window_flips_the_staleness_verdict_through_compute() -> (
    None
):
    """Req 7.1, threading proof: ``context.settings.benchmark_staleness_days``
    is genuinely read, not defaulted or hardcoded. The Run benchmarks are
    measured 2026-01-01, the activity is dated 2026-06-01 (151 days) -- the
    default 84-day window reads stale, a 400-day window reads current. If
    ``compute`` ever substituted the default window for the configured one,
    both calls would agree and this would red."""
    activity = _run_activity()
    metrics = _rich_metrics()
    profile = StubProfile(_FULL_RUN_BENCHMARKS)

    default_window_context = _context(activity_date=_DATE)
    wide_window_context = _context(activity_date=_DATE, benchmark_staleness_days=400)
    assert (
        default_window_context.settings.benchmark_staleness_days
        != wide_window_context.settings.benchmark_staleness_days
    )

    default_outcome = ThresholdCalculator().compute(
        activity, metrics, profile, RaisingSession(), default_window_context
    )
    wide_outcome = ThresholdCalculator().compute(
        activity, metrics, profile, RaisingSession(), wide_window_context
    )
    assert isinstance(default_outcome, Computed)
    assert isinstance(wide_outcome, Computed)

    def _staleness_verdict(result: object) -> str:
        flag = next(
            f
            for f in result.flags
            if f.key == "benchmark-staleness"  # type: ignore[attr-defined]
        )
        return flag.verdict

    assert _staleness_verdict(default_outcome.result) == "detected"
    assert _staleness_verdict(wide_outcome.result) == "not-detected"
