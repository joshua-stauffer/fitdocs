"""Integration proof of anchoring, borrowing, and channel-selection fallback
across realistic multi-benchmark data (task 5.1, feature validation,
design.md ``## Testing Strategy`` -- ``### Integration Tests``).

Drives :class:`~fitdocs.load.threshold.calculator.ThresholdCalculator` (and,
for the anchor-resolution scenario, :func:`~fitdocs.load.threshold.anchors.
resolve` directly) over hand-built :class:`~fitdocs.model.Activity` /
:class:`~fitdocs.metrics.types.DerivedMetrics` / profile-double fixtures --
no sync pipeline, no filesystem -- since the scenarios this task proves
(anchor resolution, borrowing, fallback, channel-selection order) are all
reachable from ``ThresholdCalculator.compute`` alone.

``_HistoryProfile`` deliberately does NOT mirror
``test_calculator.py``'s ``StubProfile`` (187-219) hand-rolled idiom: it holds a
real :class:`~fitdocs.benchmarks.BenchmarkSet` and forwards to it, so a
mutation to the store's own ranking rule is visible through this file rather
than shadowed by a second copy of that rule.

Five scenarios, one per task bullet, plus two fixtures added under review to
close a gap each task bullet's Observable already implied (Req 4.4, 6.4):

1. **Anchor resolution across a hardware boundary** -- two anti-correlated
   running FTP entries (the *older* entry carries the *larger* value, so
   ranking by measurement date and ranking by value disagree -- the
   confounded-fixture trap this repo's own change-protocol calls out by
   this exact example) plus regeneration against an independently-ordered,
   equivalent profile; a real heart-rate number computed but excluded from
   the configured order (Req 6.4); and a date before every entry on file,
   which is *not applicable* rather than *not on file* (Req 4.4).
2. **Walk borrows the running LTHR, then stops** -- a two-state transition,
   both halves asserted: before a walk LTHR is on file, and after.
3. **Walk has no power anchor** -- a walk with a full power stream and a
   running FTP on file still reports the power channel's own no-benchmark
   reason and is scored from heart rate.
4. **Fallback in both directions** -- a run falls pace -> power; a ride
   falls power -> heart rate. Both fixtures make the selected channel
   *not* the configured order's first entry. A third fixture proves the
   converse: a channel excluded from the configured order, even when it
   itself computes, is never selected (Req 6.4).
5. **All three channels always evaluated** -- a run selected on pace still
   carries a real, non-zero heart-rate number among its diagnostics.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from fitdocs import Activity, DerivedMetrics, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind, BenchmarkSet
from fitdocs.load.channels import heart_rate_compute, power_compute
from fitdocs.load.channels.types import ChannelId, ChannelLoad, SufficiencySettings
from fitdocs.load.priority import ChannelPriority
from fitdocs.load.settings import LoadSettings
from fitdocs.load.threshold.anchors import resolve
from fitdocs.load.threshold.calculator import ThresholdCalculator
from fitdocs.load.types import Computed, LoadContext, NotComputed
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# Fixture builders (self-contained -- this file owns no production module and
# borrows no helper from a sibling test module)
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


def _samples(
    n_seconds: int = 600,
    *,
    heart_rate_bpm: int | None = 150,
    power_w: int | None = 200,
    speed_mps: float | None = 4.0,
) -> Samples:
    """A stream long enough (600s, well over the 60s default minimum) with
    each channel independently controllable: ``None`` leaves that channel
    entirely unrecorded, so a test can build "full power, no distance" (the
    pace-fallback fixture) or "full heart rate, no power" (the ride-fallback
    fixture) without any channel silently carrying data it should not. No
    altitude stream anywhere, so the pace channel never applies grade
    adjustment -- outside this feature's own boundary.
    """
    n = n_seconds + 1
    time_s = tuple(float(i) for i in range(n))
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    hr = (heart_rate_bpm,) * n if heart_rate_bpm is not None else none_ints
    power = (power_w,) * n if power_w is not None else none_ints
    distance = (
        tuple(speed_mps * i for i in range(n)) if speed_mps is not None else none_floats
    )
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


def _activity(*, sport: Sport, modality: Modality, samples: Samples) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="1" * 64, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=None,
        summary=_summary(),
        laps=(),
        samples=samples,
        sets=(),
        devices=(),
    )


def _metrics(
    *, normalized_power_w: float | None = 200.0, moving_time_s: float | None = 600.0
) -> DerivedMetrics:
    return DerivedMetrics(
        normalized_power_w=normalized_power_w, moving_time_s=moving_time_s
    )


def _bm(
    kind: BenchmarkKind, discipline: Sport | None, value: float, day: date
) -> Benchmark:
    return Benchmark(kind=kind, discipline=discipline, value=value, measured_on=day)


class _HistoryProfile:
    """A :class:`~fitdocs.load.types.ProfileView` double that **delegates**
    date-scoped selection to :class:`~fitdocs.benchmarks.BenchmarkSet`
    itself -- the same object the real ``athlete-benchmarks`` store holds --
    rather than re-implementing the "applicable on or before ``on``, most
    recently measured wins" rule a second time. A double is only honest
    about the production rule it stands in for when it does not restate
    that rule; holding the real container and forwarding to
    :meth:`BenchmarkSet.applicable` / :meth:`BenchmarkSet.has` is what makes
    a mutation to that rule (in ``benchmarks.py``) visible through this
    double instead of being absorbed by a second, independent
    implementation of it.

    ``get_number`` is the only member this double still fabricates --
    :class:`ProfileView` is a :class:`~typing.Protocol`, and no scenario in
    this file reads a raw numeric field.
    """

    def __init__(self, benchmarks: Sequence[Benchmark] = ()) -> None:
        self._set = BenchmarkSet(tuple(benchmarks))

    def get_number(self, key: str) -> float | None:
        return None

    def benchmark(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date | None
    ) -> Benchmark | None:
        if on is None:
            return None
        return self._set.applicable(kind, discipline=discipline, on=on)

    def has_benchmark(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        return self._set.has(kind, discipline=discipline)


class _RaisingSession:
    """An :class:`InteractionSession` double that raises on any attribute
    touch -- ``ThresholdCalculator.compute`` never asks, never confirms
    (Req 9.7)."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"compute must never touch session.{name}")


def _context(
    *, activity_date: date | None, channel_priority: ChannelPriority | None = None
) -> LoadContext:
    settings = LoadSettings(
        default_calculator=None,
        sufficiency=SufficiencySettings(),
        channel_priority=(
            channel_priority if channel_priority is not None else ChannelPriority()
        ),
    )
    return LoadContext(activity_date=activity_date, settings=settings)


def _run_activity(*, samples: Samples | None = None) -> Activity:
    return _activity(
        sport=Sport.RUN, modality=Modality.RUN, samples=samples or _samples()
    )


def _walk_activity(*, samples: Samples | None = None) -> Activity:
    return _activity(
        sport=Sport.WALK, modality=Modality.OTHER, samples=samples or _samples()
    )


def _ride_activity(*, samples: Samples | None = None) -> Activity:
    return _activity(
        sport=Sport.RIDE, modality=Modality.BIKE, samples=samples or _samples()
    )


# ---------------------------------------------------------------------------
# Athlete-wide and Run-discipline benchmarks shared across sections 1 and 2
# (declared here so section 1's fixture can also exercise heart rate, Req
# 6.4).
# ---------------------------------------------------------------------------

_ATHLETE_MAX_HR = _bm(BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2025, 1, 1))
_ATHLETE_RESTING_HR = _bm(BenchmarkKind.RESTING_HR_BPM, None, 50.0, date(2025, 1, 1))
_RUN_LTHR = _bm(BenchmarkKind.LTHR_BPM, Sport.RUN, 165.0, date(2026, 1, 1))


# ---------------------------------------------------------------------------
# 1. Anchor resolution across a hardware boundary + regeneration
#    (Req 4.1, 4.4, 4.5, 4.6)
# ---------------------------------------------------------------------------

# Deliberately anti-correlated: the OLDER entry carries the LARGER value, so
# "most recently measured" and "largest value" disagree once both entries
# are applicable (the LATE date, where a value-ranked resolver would still
# pick the OLD, larger entry) -- this is the exact confounded-fixture trap
# change-protocol.md's "Fixture Discrimination" section names. The
# discrimination is run live below: ``benchmarks.py``'s own ``applicable``
# is what ``_HistoryProfile`` now delegates to, so mutating its ranking key
# there reds ``test_hardware_boundary_each_dated_activity_resolves_its_own_entry``
# directly.
_OLD_FTP = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 310.0, date(2020, 1, 1))
_NEW_FTP = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 250.0, date(2026, 1, 1))

_BOUNDARY_MID_DATE = date(2020, 6, 1)  # after _OLD_FTP only
_BOUNDARY_LATE_DATE = date(2026, 6, 1)  # after both

_POWER_ONLY_RUN_ORDER = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})


def test_hardware_boundary_each_dated_activity_resolves_its_own_entry() -> None:
    """A 2020-dated run resolves the 2020 (310W) entry; a 2026-dated run
    resolves the 2026 (250W) entry -- proven both through the raw resolver
    and through the assembled result's own reported inputs (Req 4.1, 4.4,
    4.5). The profile also carries a Run LTHR and athlete-wide max/resting
    HR, all applicable by the LATE date, so heart rate *computes* a real
    number even though ``_POWER_ONLY_RUN_ORDER`` excludes it from the
    configured order -- proving that exclusion, not insufficiency, is why
    it is not selected (Req 6.4)."""
    profile = _HistoryProfile(
        (_OLD_FTP, _NEW_FTP, _RUN_LTHR, _ATHLETE_RESTING_HR, _ATHLETE_MAX_HR)
    )

    mid_anchors = resolve(profile, sport=Sport.RUN, on=_BOUNDARY_MID_DATE)
    assert mid_anchors.ftp == _OLD_FTP
    late_anchors = resolve(profile, sport=Sport.RUN, on=_BOUNDARY_LATE_DATE)
    assert late_anchors.ftp == _NEW_FTP

    activity = _run_activity(samples=_samples(speed_mps=None))
    metrics = _metrics()
    calc = ThresholdCalculator()

    mid_outcome = calc.compute(
        activity,
        metrics,
        profile,
        _RaisingSession(),
        _context(
            activity_date=_BOUNDARY_MID_DATE, channel_priority=_POWER_ONLY_RUN_ORDER
        ),
    )
    assert isinstance(mid_outcome, Computed)
    assert ("ftp_watts", "310") in mid_outcome.result.inputs_used
    assert ("ftp_measured_on", "2020-01-01") in mid_outcome.result.inputs_used

    late_outcome = calc.compute(
        activity,
        metrics,
        profile,
        _RaisingSession(),
        _context(
            activity_date=_BOUNDARY_LATE_DATE, channel_priority=_POWER_ONLY_RUN_ORDER
        ),
    )
    assert isinstance(late_outcome, Computed)
    assert ("ftp_watts", "250") in late_outcome.result.inputs_used
    assert ("ftp_measured_on", "2026-01-01") in late_outcome.result.inputs_used

    late_hr_record = next(
        v
        for v in late_outcome.result.non_selected
        if v.key == ChannelId.HEART_RATE.value
    )
    assert late_hr_record.value is not None
    assert (
        late_hr_record.reason
        == "not selected: this channel is not in the configured order for Run"
    )

    expected_mid = power_compute(
        activity, metrics, ftp=_OLD_FTP, settings=SufficiencySettings()
    )
    assert isinstance(expected_mid, ChannelLoad)
    assert mid_outcome.result.value == expected_mid.load


def test_hardware_boundary_regeneration_resolves_identically() -> None:
    """Two independently-constructed, equivalent profiles -- the same two
    entries, inserted in *reversed* order -- must resolve and assemble an
    identical :class:`~fitdocs.load.types.LoadResult` for the same activity
    and date (Req 4.6). A resolver that depended on insertion order (e.g.
    ``candidates[-1]`` instead of ``max(..., key=measured_on)``) would red
    this by disagreeing with itself across the two profiles; comparing a
    single profile against itself twice could not catch that."""
    profile_forward = _HistoryProfile((_OLD_FTP, _NEW_FTP))
    profile_reversed = _HistoryProfile((_NEW_FTP, _OLD_FTP))

    activity = _run_activity(samples=_samples(speed_mps=None))
    metrics = _metrics()
    calc = ThresholdCalculator()
    context = _context(
        activity_date=_BOUNDARY_LATE_DATE, channel_priority=_POWER_ONLY_RUN_ORDER
    )

    outcome_forward = calc.compute(
        activity, metrics, profile_forward, _RaisingSession(), context
    )
    outcome_reversed = calc.compute(
        activity, metrics, profile_reversed, _RaisingSession(), context
    )
    assert isinstance(outcome_forward, Computed)
    assert isinstance(outcome_reversed, Computed)
    assert outcome_forward.result == outcome_reversed.result


def test_hardware_boundary_before_any_entry_is_not_applicable_not_absent() -> None:
    """A Run dated before every entry on file (FTP, resting HR, max HR) puts
    each of those quantities on file but with nothing dated on or before
    the activity -- the *not applicable* absence state (Req 4.4) -- which
    the FTP quantity specifically never reaches at either date used above,
    because at ``_BOUNDARY_MID_DATE`` the 2020 entry is still applicable.
    (Other quantities on that same profile *do* reach the absence branch at
    that date; this test is about reaching it for a quantity whose only
    entries all postdate the activity.) Distinguished from *not on file* -- exercised
    here too, for the Run LTHR this profile never carries -- by asserting
    each quantity lands in exactly one of the two lists, never both."""
    profile = _HistoryProfile(
        (_OLD_FTP, _NEW_FTP, _ATHLETE_RESTING_HR, _ATHLETE_MAX_HR)
    )
    before_every_entry = date(2019, 1, 1)

    anchors = resolve(profile, sport=Sport.RUN, on=before_every_entry)

    assert anchors.ftp is None
    assert (BenchmarkKind.FTP_WATTS, Sport.RUN) in anchors.not_applicable
    assert (BenchmarkKind.FTP_WATTS, Sport.RUN) not in anchors.not_on_file

    assert anchors.resting_hr is None
    assert (BenchmarkKind.RESTING_HR_BPM, None) in anchors.not_applicable
    assert (BenchmarkKind.RESTING_HR_BPM, None) not in anchors.not_on_file

    assert anchors.max_hr is None
    assert (BenchmarkKind.MAX_HR_BPM, None) in anchors.not_applicable
    assert (BenchmarkKind.MAX_HR_BPM, None) not in anchors.not_on_file

    assert anchors.lthr is None
    assert (BenchmarkKind.LTHR_BPM, Sport.RUN) in anchors.not_on_file
    assert (BenchmarkKind.LTHR_BPM, Sport.RUN) not in anchors.not_applicable


# ---------------------------------------------------------------------------
# 2. Walk borrows the running LTHR, then stops (Req 3.3, 3.4)
# ---------------------------------------------------------------------------

_WALK_LTHR = _bm(BenchmarkKind.LTHR_BPM, Sport.WALK, 130.0, date(2026, 2, 1))
_WALK_DATE = date(2026, 6, 1)

_BORROWED_NOTE = (
    "Heart-rate channel anchored on the Run lactate threshold heart rate; "
    "no Walk threshold is on file."
)


def test_walk_borrows_running_lthr_before_a_walk_lthr_exists() -> None:
    """Before state: only the running LTHR is on file, so the walk's heart-
    rate channel anchors on it and the result records the borrowing note,
    naming both disciplines (Req 3.3, 3.4)."""
    profile = _HistoryProfile((_RUN_LTHR, _ATHLETE_RESTING_HR, _ATHLETE_MAX_HR))

    anchors = resolve(profile, sport=Sport.WALK, on=_WALK_DATE)
    assert anchors.lthr == _RUN_LTHR
    assert len(anchors.borrowed) == 1
    borrowing = anchors.borrowed[0]
    assert borrowing.activity_discipline == Sport.WALK
    assert borrowing.anchor_discipline == Sport.RUN

    outcome = ThresholdCalculator().compute(
        _walk_activity(),
        _metrics(),
        profile,
        _RaisingSession(),
        _context(activity_date=_WALK_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.HEART_RATE.value
    assert _BORROWED_NOTE in outcome.result.notes
    assert ("lthr_bpm", "165") in outcome.result.inputs_used


def test_walk_lthr_flips_the_anchor_and_drops_the_borrowing_note() -> None:
    """After state: a dedicated walk LTHR is now on file. The anchor flips
    to it (a different value threads through) and the borrowing note is
    gone -- both halves proven, not merely the note's absence (Req 3.3,
    3.4)."""
    profile = _HistoryProfile(
        (_RUN_LTHR, _WALK_LTHR, _ATHLETE_RESTING_HR, _ATHLETE_MAX_HR)
    )

    anchors = resolve(profile, sport=Sport.WALK, on=_WALK_DATE)
    assert anchors.lthr == _WALK_LTHR
    assert anchors.borrowed == ()

    outcome = ThresholdCalculator().compute(
        _walk_activity(),
        _metrics(),
        profile,
        _RaisingSession(),
        _context(activity_date=_WALK_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.HEART_RATE.value
    assert _BORROWED_NOTE not in outcome.result.notes
    assert outcome.result.notes == ()
    assert ("lthr_bpm", "130") in outcome.result.inputs_used


# ---------------------------------------------------------------------------
# 3. Walk has no power anchor (Req 3.5)
# ---------------------------------------------------------------------------

_POWER_NO_BENCHMARK_DETAIL = (
    "no functional-threshold-power benchmark was supplied, or its value is not positive"
)


def test_walk_with_a_full_power_stream_still_reports_no_power_anchor() -> None:
    """A walk carrying a full, sufficient power stream, with a running FTP
    on file (but no walking one -- the discipline's anchor chain for power
    is deliberately empty), still reports the power channel's own no-
    benchmark reason -- never a value scaled from the running FTP -- and is
    scored from heart rate instead (Req 3.5)."""
    profile = _HistoryProfile(
        (
            _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2025, 1, 1)),
            _RUN_LTHR,
            _ATHLETE_RESTING_HR,
            _ATHLETE_MAX_HR,
        )
    )
    activity = _walk_activity(samples=_samples(power_w=200, speed_mps=None))

    outcome = ThresholdCalculator().compute(
        activity,
        _metrics(),
        profile,
        _RaisingSession(),
        _context(activity_date=_WALK_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.HEART_RATE.value

    power_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.POWER.value
    )
    assert power_record.value is None
    assert power_record.reason == _POWER_NO_BENCHMARK_DETAIL


# ---------------------------------------------------------------------------
# 4. Fallback in both directions (Req 6.2, 6.3, 6.4)
# ---------------------------------------------------------------------------

_RUN_FALLBACK_BENCHMARKS = (
    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2025, 1, 1)),
    _bm(BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 240.0, date(2025, 1, 1)),
    _RUN_LTHR,
    _ATHLETE_RESTING_HR,
    _ATHLETE_MAX_HR,
)
_FALLBACK_DATE = date(2026, 6, 1)


def test_run_with_no_usable_distance_falls_from_pace_to_power() -> None:
    """A run whose distance stream is entirely unrecorded cannot be scored
    on pace -- reported by the shared gate, not the pace benchmark check,
    since a threshold pace IS on file -- and falls through to power, the
    next entry in the default Run order. Selected channel (power) is
    deliberately NOT the configured order's first entry (pace) (Req 6.2,
    6.3)."""
    profile = _HistoryProfile(_RUN_FALLBACK_BENCHMARKS)
    activity = _run_activity(samples=_samples(speed_mps=None))
    default_run_order = ChannelPriority().for_discipline(Sport.RUN)
    assert default_run_order[0] == ChannelId.PACE

    outcome = ThresholdCalculator().compute(
        activity,
        _metrics(),
        profile,
        _RaisingSession(),
        _context(activity_date=_FALLBACK_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.POWER.value
    assert outcome.result.basis != default_run_order[0].value

    pace_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.PACE.value
    )
    assert pace_record.value is None
    assert (
        pace_record.reason
        == "distance carries no recorded value anywhere in the activity"
    )

    hr_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.HEART_RATE.value
    )
    assert hr_record.value is not None
    assert (
        hr_record.reason == "not selected: the configured order for Run prefers Power"
    )


_RIDE_FALLBACK_BENCHMARKS = (
    _bm(BenchmarkKind.FTP_WATTS, Sport.RIDE, 260.0, date(2025, 1, 1)),
    _bm(BenchmarkKind.LTHR_BPM, Sport.RIDE, 160.0, date(2025, 1, 1)),
    _ATHLETE_RESTING_HR,
    _ATHLETE_MAX_HR,
)


def test_ride_with_no_power_falls_from_power_to_heart_rate() -> None:
    """A ride whose power stream is entirely unrecorded cannot be scored on
    power -- reported by the shared gate, since a cycling FTP IS on file --
    and falls through to heart rate, the next entry in the default Ride
    order. Selected channel (heart rate) is deliberately NOT the configured
    order's first entry (power) (Req 6.2, 6.3)."""
    profile = _HistoryProfile(_RIDE_FALLBACK_BENCHMARKS)
    activity = _ride_activity(samples=_samples(power_w=None))
    default_ride_order = ChannelPriority().for_discipline(Sport.RIDE)
    assert default_ride_order[0] == ChannelId.POWER

    outcome = ThresholdCalculator().compute(
        activity,
        _metrics(),
        profile,
        _RaisingSession(),
        _context(activity_date=_FALLBACK_DATE),
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.HEART_RATE.value
    assert outcome.result.basis != default_ride_order[0].value

    power_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.POWER.value
    )
    assert power_record.value is None
    assert (
        power_record.reason
        == "power carries no recorded value anywhere in the activity"
    )


def test_run_configured_order_excludes_a_computing_channel_never_selects_it() -> None:
    """A Run configured to select only from Power (``_POWER_ONLY_RUN_ORDER``)
    with a Run FTP applicable at the activity date, so power has its
    benchmark, but no power stream recorded, so power reports its own
    stream-absent reason -- deliberately NOT ``NO_BENCHMARK``, so
    ``_missing_inputs`` never fires and this scenario cannot be mistaken for
    a ``MissingInputs`` outcome. The profile also carries a full Run
    LTHR/resting/max HR history, so heart rate *does* compute a real load.
    Heart rate must still never be selected, because it is absent from the
    configured order (Req 6.4): the calculator returns ``NotComputed``, and
    its reason names heart rate's own out-of-order wording -- the proof
    this exact scenario, and not the no-channel-computes-at-all case (Req
    6.7), is what actually ran. (Measured, two drifts, each reddening a
    different assertion: swapping this profile for ``_HistoryProfile(())``
    reds the ``NotComputed`` assertion -- with no FTP the power channel
    reports NO_BENCHMARK and the outcome becomes ``MissingInputs``, which
    carries ``fields`` and no ``reason`` at all. Making heart rate unable to
    compute while leaving the FTP in place reds the reason assertion below,
    which is the live-scenario proof: that clause is emitted only from
    ``non_selected_values``' ``case ChannelLoad`` out-of-order branch, so it
    cannot appear for a channel that produced nothing.)"""
    profile = _HistoryProfile(
        (_NEW_FTP, _RUN_LTHR, _ATHLETE_RESTING_HR, _ATHLETE_MAX_HR)
    )
    activity = _run_activity(samples=_samples(power_w=None, speed_mps=None))

    outcome = ThresholdCalculator().compute(
        activity,
        _metrics(),
        profile,
        _RaisingSession(),
        _context(activity_date=_FALLBACK_DATE, channel_priority=_POWER_ONLY_RUN_ORDER),
    )
    assert isinstance(outcome, NotComputed)
    assert (
        "Heart rate: not selected: this channel is not in the configured order for Run"
    ) in outcome.reason


# ---------------------------------------------------------------------------
# 5. All three channels always evaluated (Req 6.2 continuation; the input
#    the planned activity-qa-flags feature consumes)
# ---------------------------------------------------------------------------

_RUN_FULL_BENCHMARKS = (
    _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2025, 1, 1)),
    _bm(BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 240.0, date(2025, 1, 1)),
    _RUN_LTHR,
    _ATHLETE_RESTING_HR,
    _ATHLETE_MAX_HR,
)


def test_run_selected_on_pace_still_records_a_real_heart_rate_number() -> None:
    """A run with power, heart rate and distance all sufficient selects pace
    (the default Run order's first entry) but still carries a real,
    non-zero heart-rate *value* among its diagnostics -- not merely a
    reason -- computed to the exact value an independent
    ``heart_rate_compute`` call over the same anchors produces. ``assert
    ... is not None`` alone would still pass a placeholder ``0.0``; the
    ``!= 0.0`` and exact-value comparisons below are what rule that out
    (probe 5)."""
    profile = _HistoryProfile(_RUN_FULL_BENCHMARKS)
    activity = _run_activity()
    metrics = _metrics()
    context = _context(activity_date=_FALLBACK_DATE)

    outcome = ThresholdCalculator().compute(
        activity, metrics, profile, _RaisingSession(), context
    )
    assert isinstance(outcome, Computed)
    assert outcome.result.basis == ChannelId.PACE.value

    hr_record = next(
        v for v in outcome.result.non_selected if v.key == ChannelId.HEART_RATE.value
    )
    assert hr_record.value is not None
    assert hr_record.value != 0.0

    anchors = resolve(profile, sport=Sport.RUN, on=_FALLBACK_DATE)
    expected_hr = heart_rate_compute(
        activity,
        metrics,
        lthr=anchors.lthr,
        resting_hr=anchors.resting_hr,
        max_hr=anchors.max_hr,
        settings=context.settings.sufficiency,
    )
    assert isinstance(expected_hr, ChannelLoad)
    assert hr_record.value == expected_hr.load
