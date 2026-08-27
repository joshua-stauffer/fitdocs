"""The honest outcomes for everything ``ThresholdCalculator`` cannot score
(task 5.2, feature validation, design.md ``## Testing Strategy`` -- the
"Undated document", "Missing versus not-applicable" and "No prompt for a
refused sport" Integration Test bullets; Req 2.2, 2.3, 2.7, 9.4, 9.5, 10.1,
10.2, 10.3, 10.4, 10.5, 10.6).

Self-contained (matches ``test_anchoring_e2e.py``'s own convention): no
fixture or double is imported from a sibling test module.

Two registers of proof, matched to what each case actually needs. Seven
calculator-level and four engine-level tests, all listed below:

* **Calculator-level** (:meth:`ThresholdCalculator.compute` called directly,
  ``RaisingSession`` standing in for the session) for the cases decided
  entirely inside the calculator: an unsupported sport by name
  (``test_unsupported_sport_by_name_returns_unsupported_naming_it``), every
  channel insufficient with benchmarks on file
  (``test_every_channel_insufficient_with_benchmarks_on_file_is_not_computed``),
  every channel insufficient with a benchmark never on file, ``MissingInputs``
  (``test_every_channel_insufficient_benchmark_never_on_file_is_missing_inputs``),
  a benchmark on file that postdates the activity, ``NotComputed`` not
  ``MissingInputs``
  (``test_benchmark_postdating_the_activity_is_not_computed_not_missing_inputs``),
  the wording-versus-variant finding
  (``test_late_and_never_provided_reasons_are_not_distinguished_by_wording``),
  the not-computed-to-computed retry
  (``test_not_computed_becomes_computed_once_the_late_benchmark_is_replaced``),
  and the no-numeric-value-anywhere sweep
  (``test_no_absence_outcome_carries_a_numeric_value_anywhere``).
* **Engine-level** (:func:`fitdocs.load.engine.apply_load` over a real data
  root the sync pipeline rendered) for four cases that are about *ordering
  between modules*, not about what the calculator returns: a strength
  activity and a rowing activity, each with an empty athlete profile, must
  never let a prompt reach the interaction session
  (``test_strength_labelled_run_reaches_unsupported_without_compute_invoked``,
  ``test_rowing_refused_by_support_with_no_prompt_asked``); a third,
  strength-labelled activity, this time with a fully populated profile so
  the session claim above cannot apply, proves the sibling half of the same
  requirement -- that ``ThresholdCalculator.compute`` is literally never
  called for a refused activity
  (``test_populated_strength_activity_never_invokes_compute``); and an
  undated document -- a real, GPS-bearing document the sync pipeline
  rendered, its ``date:`` frontmatter line stripped afterward -- must be
  reported not-computed by the date gate alone, before any anchor or
  benchmark lookup runs
  (``test_undated_document_is_not_computed_naming_the_date``). The first
  three force ``[load] default_calculator = "threshold"`` so arbitration's
  sport/modality-blind forced path (training-load Req 10.5) is what selects
  the calculator -- making the engine's own ``supports_activity`` gate
  (``engine.py`` ~483-490), and the calculator's own ``supports()``, the
  *only* thing standing between the activity and the prompt flow. A plain
  no-default pass would let ``arbitrate``'s own narrowing absorb the same
  proof instead, which is a real but different claim. The undated scenario
  does not force a default: its document renders (it carries GPS, so it also
  calls into map rendering -- see ``_ServingTiles`` below), and the date gate
  fires before arbitration's calculator choice matters to this test at all.

**REQ_9_5_REASON_FINDING** (see ``test_late_and_never_provided_reasons_are_not_
distinguished_by_wording`` below): a benchmark that is on file but postdates
the activity, and a benchmark that was never provided at all, are correctly
reported as *different outcome variants* (``NotComputed`` vs
``MissingInputs``) -- but the channel-layer ``detail`` text embedded in the
``NotComputed`` reason is byte-identical between the two, because
``ThresholdCalculator`` never reads ``ResolvedAnchors.not_applicable`` at all
(only ``not_on_file``, inside ``_missing_inputs``). Requirement 9.5's own
"distinguishing reason" is carried entirely by the outcome type, not by any
wording -- this is measured and asserted directly below, not merely
inferred.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from fitdocs import Activity, DerivedMetrics, Modality, Provenance, Samples, Sport
from fitdocs.athlete import load_athlete_inputs
from fitdocs.benchmarks import Benchmark, BenchmarkKind, BenchmarkSet
from fitdocs.layout import SETTINGS_FILE, WORKOUTS_DIR
from fitdocs.load.channels.types import ChannelId, SufficiencySettings
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.priority import ChannelPriority
from fitdocs.load.profile import AthleteProfile, save_profile
from fitdocs.load.settings import LoadSettings
from fitdocs.load.threshold.calculator import ThresholdCalculator
from fitdocs.load.types import (
    Computed,
    LoadContext,
    MissingInputs,
    NotComputed,
    Unsupported,
)
from fitdocs.model import SCHEMA_VERSION, SessionSummary
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import sync
from tests.fixtures import builder

# ---------------------------------------------------------------------------
# Calculator-level fixture builders
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
        provenance=Provenance(sha256="1" * 64, source_path=None, decode_errors=()),
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


def _run_activity(**kwargs: object) -> Activity:
    samples = kwargs.pop("samples", None) or _rich_samples()
    return _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        samples=samples,
        **kwargs,  # type: ignore[arg-type]
    )


def _rich_metrics() -> DerivedMetrics:
    return DerivedMetrics(normalized_power_w=200.0, moving_time_s=600.0)


def _bm(
    kind: BenchmarkKind, discipline: Sport | None, value: float, day: date
) -> Benchmark:
    return Benchmark(kind=kind, discipline=discipline, value=value, measured_on=day)


class _HistoryProfile:
    """A :class:`~fitdocs.load.types.ProfileView` double that **delegates**
    date-scoped selection to a real :class:`~fitdocs.benchmarks.BenchmarkSet`
    rather than re-implementing the "applicable on or before ``on``" rule a
    second time (Fixture Discrimination Gate probe 1) -- a mutation to that
    rule is visible through this double instead of being absorbed by a
    hand-rolled copy of it."""

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
    """An :class:`~fitdocs.load.types.InteractionSession` double that raises
    on **any** attribute access, so any use of ``session`` -- not only a
    call -- is a hard failure rather than a silently tolerated no-op."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"must never touch session.{name}")


def _context(
    *,
    activity_date: date | None,
    channel_priority: ChannelPriority | None = None,
    sufficiency: SufficiencySettings | None = None,
) -> LoadContext:
    settings = LoadSettings(
        default_calculator=None,
        sufficiency=sufficiency if sufficiency is not None else SufficiencySettings(),
        channel_priority=(
            channel_priority if channel_priority is not None else ChannelPriority()
        ),
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


# ---------------------------------------------------------------------------
# 1. Unsupported sport by name (Req 2.2, 2.3)
# ---------------------------------------------------------------------------


def test_unsupported_sport_by_name_returns_unsupported_naming_it() -> None:
    """A ``Workout`` activity -- inside the declared catch-all
    ``Modality.OTHER`` -- is refused by the sport set alone, never by the
    modality gate. Mutation (PRODUCTION-SIDE, ``calculator.py``): dropping
    the sport clause from ``compute``'s step-1 condition (leaving only the
    modality check) lets a ``Workout`` activity fall through to anchor
    resolution, where ``anchor_plan(Sport.WORKOUT)`` raises ``KeyError`` --
    turning this test's clean ``Unsupported`` assertion into an uncaught
    exception. Applied, observed red (``KeyError``), reverted, confirmed
    green.
    """
    activity = _activity(
        sport=Sport.WORKOUT, modality=Modality.OTHER, samples=_empty_samples()
    )
    outcome = ThresholdCalculator().compute(
        activity,
        DerivedMetrics(),
        _HistoryProfile(),
        _RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, Unsupported)
    assert not isinstance(outcome, (Computed, MissingInputs, NotComputed))
    assert "Workout" in outcome.reason
    assert outcome.reason != ""


# ---------------------------------------------------------------------------
# 2. Every channel insufficient, blockers unrelated to any missing
#    benchmark, on file in full (Req 10.1, 10.2)
# ---------------------------------------------------------------------------


def test_every_channel_insufficient_with_benchmarks_on_file_is_not_computed() -> None:
    """Every channel is blocked by a data condition (an activity far
    shorter than the configured minimum duration), not by an absent
    benchmark -- the full running benchmark set is on file. Must be
    ``NotComputed``, never ``MissingInputs`` (no channel's insufficiency
    reason is ``NO_BENCHMARK``), and the reason must name each of the three
    channels with its own detail.

    Mutation (PRODUCTION-SIDE, ``calculator.py``'s ``_not_computed_reason``):
    replacing ``f"{record.label}: {record.reason}"`` with bare
    ``record.reason`` drops every channel label from the assembled reason,
    reddening the per-channel-name assertions below. Applied, observed red,
    reverted, confirmed green.
    """
    activity = _run_activity(samples=_rich_samples(n_seconds=5))
    strict = SufficiencySettings(min_duration_s=10_000)
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        _HistoryProfile(_FULL_RUN_BENCHMARKS),
        _RaisingSession(),
        _context(activity_date=_DATE, sufficiency=strict),
    )
    assert isinstance(outcome, NotComputed)
    assert not isinstance(outcome, MissingInputs)
    for label in ("Power:", "Heart rate:", "Pace:"):
        assert label in outcome.reason
    assert outcome.reason != ""


# ---------------------------------------------------------------------------
# 3. Every channel insufficient, a required benchmark never on file at all
#    (Req 9.4)
# ---------------------------------------------------------------------------


def test_every_channel_insufficient_benchmark_never_on_file_is_missing_inputs() -> None:
    """Nothing at all is on file for a Run activity whose configured order
    covers all three channels: every channel's insufficiency is
    ``NO_BENCHMARK`` and every underlying quantity is genuinely absent, so
    the outcome must name the declared fields rather than a generic
    not-computed prose reason.

    Mutation (PRODUCTION-SIDE, ``calculator.py``'s ``_missing_inputs``):
    inverting ``if kind in not_on_file_by_kind:`` to ``if kind not in
    not_on_file_by_kind:`` makes every genuinely-absent quantity look
    resolved and every resolved quantity look absent -- with nothing on
    file, no kind is ever "found", so ``needed_kinds`` becomes empty and the
    outcome becomes ``NotComputed`` instead. Applied, observed red
    (``isinstance(outcome, MissingInputs)`` fails), reverted, confirmed
    green.
    """
    activity = _run_activity()
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        _HistoryProfile(()),  # nothing on file at all
        _RaisingSession(),
        _context(activity_date=_DATE),
    )
    assert isinstance(outcome, MissingInputs)
    assert not isinstance(outcome, NotComputed)
    expected_keys = {
        "benchmarks.run.ftp_watts",
        "benchmarks.run.lthr_bpm",
        "benchmarks.run.threshold_pace_s_per_km",
        "benchmarks.athlete.max_hr_bpm",
        "benchmarks.athlete.resting_hr_bpm",
    }
    assert {f.key for f in outcome.fields} == expected_keys
    # Structural, not merely observed: MissingInputs carries no value field at
    # all -- there is no way for this outcome to smuggle a number.
    assert not hasattr(outcome, "value")
    assert not hasattr(outcome, "result")


# ---------------------------------------------------------------------------
# 4. A benchmark on file whose only entry postdates the activity (Req 9.5)
# ---------------------------------------------------------------------------


def test_benchmark_postdating_the_activity_is_not_computed_not_missing_inputs() -> None:
    """A Running FTP is on file, but its only entry is dated strictly after
    the activity -- ``NotComputed`` with the distinguishing outcome variant,
    never ``MissingInputs`` (Req 9.5). Configured order names only Power, so
    this is the sole quantity in play.

    Mutation (PRODUCTION-SIDE, ``anchors.py``): swapping the two branches of
    ``if any_on_file: not_applicable.append(...) else:
    not_on_file.append(...)`` files a postdating benchmark under
    ``not_on_file`` instead, which ``_missing_inputs`` then picks up --
    turning this into ``MissingInputs``. Applied, observed red
    (``isinstance(outcome, NotComputed)`` fails), reverted, confirmed green.
    """
    activity = _run_activity()
    power_only = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    late_ftp = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2030, 1, 1))
    outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        _HistoryProfile((late_ftp,)),
        _RaisingSession(),
        _context(activity_date=_DATE, channel_priority=power_only),
    )
    assert isinstance(outcome, NotComputed)
    assert not isinstance(outcome, MissingInputs)
    assert outcome.reason != ""


def test_late_and_never_provided_reasons_are_not_distinguished_by_wording() -> None:
    """REQ_9_5_REASON_FINDING, measured directly: the ``NotComputed`` reason
    for "benchmark on file but postdating the activity" and for "benchmark
    never on file at all" (with Power excluded from the configured order, so
    the never-provided case is also ``NotComputed`` rather than
    ``MissingInputs`` -- isolating the wording comparison from the outcome
    type) are **byte-identical** for the Power channel's own portion of the
    reason. ``ThresholdCalculator`` never reads ``ResolvedAnchors.
    not_applicable`` anywhere in its source (only ``not_on_file``, inside
    ``_missing_inputs``), so no code path exists that could vary the wording
    by which absence state produced it -- confirmed by reading
    ``calculator.py`` and ``channels/power.py``'s single, constant
    ``_NO_BENCHMARK_DETAIL`` string. Requirement 9.5's "reason distinguishing
    that case" is therefore carried **only** by the outcome variant
    (``NotComputed`` in both branches here) and never by the reason text --
    which is why this test isolates the never-provided case to ``NotComputed``
    too, rather than to the differently-typed ``MissingInputs`` case, where
    the variant alone would trivially "distinguish" them for an unrelated
    reason.
    """
    activity = _run_activity(samples=_rich_samples(heart_rate_bpm=None, speed_mps=None))
    # An EMPTY configured order for Run: `_missing_inputs` only ever consults
    # channels *in* `order` (Req 9.4's own scoping rule), so with nothing in
    # `order`, neither fixture can ever become `MissingInputs` regardless of
    # which quantity is absent -- isolating this test to the wording question
    # alone. `non_selected_values` (which builds the `NotComputed` reason)
    # still records every channel's own `ChannelInsufficient.detail` verbatim
    # regardless of `order` membership, so Power's detail still lands in the
    # reason either way.
    empty_order = ChannelPriority(by_discipline={Sport.RUN: ()})
    context = _context(activity_date=_DATE, channel_priority=empty_order)

    late_ftp = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2030, 1, 1))
    late_outcome = ThresholdCalculator().compute(
        activity,
        _rich_metrics(),
        _HistoryProfile((late_ftp,)),
        _RaisingSession(),
        context,
    )
    never_outcome = ThresholdCalculator().compute(
        activity, _rich_metrics(), _HistoryProfile(()), _RaisingSession(), context
    )

    assert isinstance(late_outcome, NotComputed)
    assert isinstance(never_outcome, NotComputed)
    # The finding: identical variant AND identical reason text. If a future
    # change makes these differ, this assertion -- not a passing test -- is
    # the thing that should be revisited; today it holds.
    assert late_outcome.reason == never_outcome.reason


# ---------------------------------------------------------------------------
# 5. The retry: not-computed becomes computed once the missing data is
#    supplied, with nothing else changed (Req 10.5)
# ---------------------------------------------------------------------------


def test_not_computed_becomes_computed_once_the_late_benchmark_is_replaced() -> None:
    """Starts from the genuinely ``NotComputed`` (not ``MissingInputs``)
    postdating-benchmark state above, then re-scores the identical activity,
    metrics and context against a profile that now carries an
    earlier-dated FTP entry instead -- the *only* change between the two
    calls. Asserts both the before state and the after state, and that the
    computed value is a real, non-placeholder number (Fixture
    Discrimination Gate probe 5)."""
    activity = _run_activity()
    power_only = ChannelPriority(by_discipline={Sport.RUN: (ChannelId.POWER,)})
    context = _context(activity_date=_DATE, channel_priority=power_only)
    calc = ThresholdCalculator()
    metrics = _rich_metrics()

    late_ftp = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2030, 1, 1))
    before = calc.compute(
        activity, metrics, _HistoryProfile((late_ftp,)), _RaisingSession(), context
    )
    assert isinstance(before, NotComputed)
    assert not isinstance(before, Computed)

    early_ftp = _bm(BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2026, 1, 1))
    after = calc.compute(
        activity, metrics, _HistoryProfile((early_ftp,)), _RaisingSession(), context
    )
    assert isinstance(after, Computed)
    assert after.result.basis == ChannelId.POWER.value
    assert after.result.value is not None
    assert after.result.value != 0.0


# ---------------------------------------------------------------------------
# 6. No path emits a zero, a default, or a placeholder load (Req 10.4)
# ---------------------------------------------------------------------------


def test_no_absence_outcome_carries_a_numeric_value_anywhere() -> None:
    """Sweeps every non-``Computed`` outcome variant produced above and
    confirms none of them can carry a number at all -- ``Unsupported`` and
    ``NotComputed`` hold only a ``reason: str``; ``MissingInputs`` holds only
    ``fields: tuple[AthleteField, ...]``. This is a structural guarantee
    (the dataclasses have no numeric field), checked directly rather than
    inferred from ``not value`` (which would also pass for a fabricated
    ``0.0`` -- Fixture Discrimination Gate probe 4)."""
    unsupported = ThresholdCalculator().compute(
        _activity(
            sport=Sport.WORKOUT, modality=Modality.OTHER, samples=_empty_samples()
        ),
        DerivedMetrics(),
        _HistoryProfile(),
        _RaisingSession(),
        _context(activity_date=_DATE),
    )
    missing = ThresholdCalculator().compute(
        _run_activity(),
        _rich_metrics(),
        _HistoryProfile(()),
        _RaisingSession(),
        _context(activity_date=_DATE),
    )
    not_computed = ThresholdCalculator().compute(
        _run_activity(),
        _rich_metrics(),
        _HistoryProfile(_FULL_RUN_BENCHMARKS),
        _RaisingSession(),
        _context(activity_date=None),
    )
    assert isinstance(unsupported, Unsupported)
    assert isinstance(missing, MissingInputs)
    assert isinstance(not_computed, NotComputed)
    for outcome in (unsupported, missing, not_computed):
        assert not hasattr(outcome, "value")
        assert not hasattr(outcome, "result")


# ---------------------------------------------------------------------------
# Engine-level: strength and rowing must never reach compute() or the
# session at all (Req 2.2, 2.7)
# ---------------------------------------------------------------------------

_TZ = timezone(timedelta(hours=-6))


class _ServingTiles:
    """Basemap-tile source for the engine-level scenarios. The undated
    scenario is built from ``builder.run_fit_bytes()``, which carries GPS, so
    its document does render a map and does call ``resolve``; the strength
    and rowing scenarios use ``builder.small_sport_fit_bytes``, which carries
    none, and never reach rendering."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES = _ServingTiles()


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _doc(data_root: Path, needle: str) -> Path:
    return next(p for p in (data_root / WORKOUTS_DIR).glob("*.md") if needle in p.name)


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


def _populate_full_run_profile(data_root: Path) -> None:
    """Persists every quantity all seven of ``ATHLETE_FIELDS`` declare --
    including Ride's FTP and LTHR, which a Run activity never uses -- so the
    engine's own ``collect_missing_fields`` finds everything already on file
    and never touches ``session`` at all. ``required_athlete_fields`` is
    activity-blind (calculator.py's own documented known limitation): a Run
    document still gets asked for a Ride FTP if one is not already on file,
    so populating only the Run-relevant quantities left this prompt reaching
    ``session`` regardless of the document's own sport -- caught by this
    file's own engine-level test failing red on the very first run before
    this helper covered all seven."""
    profile = AthleteProfile(data={})
    for kind, discipline, value, day in (
        (BenchmarkKind.FTP_WATTS, Sport.RUN, 280.0, date(2020, 1, 1)),
        (BenchmarkKind.FTP_WATTS, Sport.RIDE, 250.0, date(2020, 1, 1)),
        (BenchmarkKind.LTHR_BPM, Sport.RUN, 170.0, date(2020, 1, 1)),
        (BenchmarkKind.LTHR_BPM, Sport.RIDE, 165.0, date(2020, 1, 1)),
        (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 240.0, date(2020, 1, 1)),
        (BenchmarkKind.MAX_HR_BPM, None, 190.0, date(2020, 1, 1)),
        (BenchmarkKind.RESTING_HR_BPM, None, 50.0, date(2020, 1, 1)),
    ):
        profile = profile.with_benchmark(
            kind, discipline=discipline, value=value, measured_on=day
        )
    save_profile(data_root, profile)


def _force_threshold_default(data_root: Path) -> None:
    """Forces ``[load] default_calculator = "threshold"`` so arbitration's
    sport/modality-blind forced path (training-load Req 10.5) is what selects
    ``THRESHOLD_CALCULATOR`` -- making the engine's own ``supports_activity``
    gate, and the calculator's own ``supports()``, the *only* thing standing
    between the activity and the prompt flow (see module docstring)."""
    (data_root / SETTINGS_FILE).write_text(
        '[load]\ndefault_calculator = "threshold"\n', encoding="utf-8"
    )


def test_strength_labelled_run_reaches_unsupported_without_compute_invoked(
    tmp_path: Path,
) -> None:
    """A ``sport="running"``, ``sub_sport="strength_training"`` fixture
    decodes to ``(Sport.RUN, Modality.STRENGTH)`` -- the sport is supported,
    only the modality is not (calculator.py's own documented edge case).
    Forced ``default_calculator`` makes the modality gate, not arbitration's
    own narrowing, the thing under test. Asserts the report never computes
    this document. Whether ``ThresholdCalculator.compute`` is itself ever
    invoked is proved separately, by
    ``test_populated_strength_activity_never_invokes_compute`` below: this
    fixture leaves the profile empty, so any mutation that lets the activity
    past the support gate touches ``session`` and reds on the session double
    first, before a compute-call counter here could ever discriminate
    anything.

    Mutation (PRODUCTION-SIDE, ``discipline.py``): adding ``Modality.
    STRENGTH`` to ``DECLARED_MODALITIES`` makes ``ThresholdCalculator.
    supports()`` answer ``True`` for this activity (its sport is already
    supported), so the engine's gate passes it through to
    ``collect_missing_fields``, which touches ``session`` -- and the session
    double raises on any touch. Applied, observed red (``AssertionError``
    from the session double propagating out of ``apply_load``), reverted,
    confirmed green.
    """
    fit_bytes = builder.small_sport_fit_bytes(
        4001, "running", sub_sport="strength_training"
    )
    data_root = _build_data_root(tmp_path, {"strength_run.fit": fit_bytes})
    doc = _doc(data_root, "strength")
    _force_threshold_default(data_root)

    report = apply_load(data_root, session=_RaisingSession())

    rel = _rel(data_root, doc)
    assert rel in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.computed)
    assert rel not in _docs_of(report.skipped)


def test_rowing_refused_by_support_with_no_prompt_asked(tmp_path: Path) -> None:
    """A Rowing activity -- inside the declared catch-all ``Modality.OTHER``
    -- is refused by the sport set, and the session double raising on any
    attribute access is the direct proof that no prompt is ever asked for
    it: a passing test here means ``session`` was never touched at all, not
    merely that no *prompt text* was logged (Fixture Discrimination Gate
    probe 2's "prove the precondition is reached" reading applied to a
    negative claim). Whether ``ThresholdCalculator.compute`` is itself ever
    invoked is proved separately, by
    ``test_populated_strength_activity_never_invokes_compute`` below, using a
    populated profile -- this fixture's empty profile means any mutation
    that lets the activity past the support gate reds on the session double
    first, so a compute-call counter here could never discriminate anything.

    Mutation (PRODUCTION-SIDE, ``calculator.py``): dropping the sport clause
    from ``ThresholdCalculator.supports()`` (leaving only ``activity.
    modality in DECLARED_MODALITIES``) makes it answer ``True`` for Rowing,
    since ``Modality.OTHER`` is declared. The engine's gate then passes it
    through to ``collect_missing_fields``, which touches ``session`` and
    raises. Applied, observed red (``AssertionError`` propagating out of
    ``apply_load``), reverted, confirmed green.
    """
    fit_bytes = builder.small_sport_fit_bytes(4002, "rowing")
    data_root = _build_data_root(tmp_path, {"row.fit": fit_bytes})
    doc = _doc(data_root, "row")
    _force_threshold_default(data_root)

    report = apply_load(data_root, session=_RaisingSession())

    rel = _rel(data_root, doc)
    assert rel in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.computed)
    assert rel not in _docs_of(report.skipped)


def test_populated_strength_activity_never_invokes_compute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Proves the non-invocation half of Req 2.2/2.7 that the two tests
    above cannot: that ``ThresholdCalculator.compute`` is literally never
    called for a refused activity. This test deliberately populates the
    athlete profile with ``_populate_full_run_profile`` first, so it proves
    *nothing* about prompting -- that is
    ``test_strength_labelled_run_reaches_unsupported_without_compute_
    invoked``'s job, above, whose empty profile is what makes its own
    session-untouched proof meaningful. The two claims need opposite
    fixture states and cannot share one test: with an empty profile, a
    mutation that lets the activity past the support gate reds on the
    session double before a compute-call counter could ever discriminate
    anything (as documented on the two tests above); with a populated
    profile, ``collect_missing_fields`` finds every field already on file
    and ``session`` is never touched at all regardless of the gate, so the
    only thing left for a mutation to expose is whether ``compute`` itself
    ran.

    Mutation (PRODUCTION-SIDE, ``calculator.py``): reducing
    ``ThresholdCalculator.supports()`` to ``activity.sport in
    SUPPORTED_SPORTS`` (dropping the modality clause) makes it answer
    ``True`` for this strength-labelled Run, so the engine's gate passes it
    through to ``compute``, which returns a normal ``Unsupported`` outcome
    naming the sport (measured: ``Run is not a sport the
    threshold calculator scores`` -- it names the sport, never the modality
    that actually caused the refusal). Applied, observed red specifically on
    ``assert calls["n"] == 0`` (this function's last line) -- the outcome
    assertions above it stay green because ``compute``'s own ``Unsupported``
    return still lands in ``report.unsupported`` -- reverted, confirmed
    green.
    """
    calls = {"n": 0}
    original_compute = ThresholdCalculator.compute

    def _counting_compute(
        self: ThresholdCalculator, *args: object, **kwargs: object
    ) -> object:
        calls["n"] += 1
        return original_compute(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ThresholdCalculator, "compute", _counting_compute)

    fit_bytes = builder.small_sport_fit_bytes(
        4003, "running", sub_sport="strength_training"
    )
    data_root = _build_data_root(tmp_path, {"strength_run.fit": fit_bytes})
    doc = _doc(data_root, "strength")
    _force_threshold_default(data_root)
    _populate_full_run_profile(data_root)

    report = apply_load(data_root, session=_RaisingSession())

    rel = _rel(data_root, doc)
    assert rel in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.computed)
    assert rel not in _docs_of(report.skipped)
    assert calls["n"] == 0


# ---------------------------------------------------------------------------
# Undated document (Req 4.3)
# ---------------------------------------------------------------------------


def test_undated_document_is_not_computed_naming_the_date(tmp_path: Path) -> None:
    """A real synced document with its ``date:`` frontmatter line stripped
    is reported not-computed with a reason naming the absent date -- no
    benchmark lookup ever having a chance to succeed, since ``context.
    activity_date`` is ``None`` before any anchor is resolved."""
    fit_bytes = builder.run_fit_bytes()
    data_root = _build_data_root(tmp_path, {"run.fit": fit_bytes})
    doc = _doc(data_root, "run")
    lines = doc.read_text(encoding="utf-8").split("\n")
    undated = [line for line in lines if not line.startswith("date:")]
    doc.write_text("\n".join(undated), encoding="utf-8")
    # Every declared field already on file, so `collect_missing_fields` never
    # touches `session` -- isolating this scenario to the date gate alone.
    _populate_full_run_profile(data_root)

    report = apply_load(data_root, session=_RaisingSession())

    rel = _rel(data_root, doc)
    assert rel in _docs_of(report.skipped)
    assert rel not in _docs_of(report.computed)
    skip_entry = next(e for e in report.skipped if e.doc == rel)
    assert "date" in skip_entry.detail.lower()
