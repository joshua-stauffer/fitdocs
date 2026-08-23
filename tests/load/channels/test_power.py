"""Tests for the power channel (``power.py``).

Covers Requirements 1.6, 1.7, 1.9, 1.11, 4.1-4.9 -- see
``.kiro/specs/load-channels/requirements.md`` and the "Channel --
src/fitdocs/load/channels/power.py" / "PowerChannel" component in
design.md.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date

import pytest

from fitdocs import Activity, Modality, Provenance, Samples, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import power
from fitdocs.load.channels.sources import COGGAN_TSS, DIVERGENCES
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    InsufficiencyReason,
    SufficiencySettings,
)
from fitdocs.metrics.stress import power_tss
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import SCHEMA_VERSION, SessionSummary

# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------


def _samples(time_s: tuple[float, ...], power_w: tuple[int | None, ...]) -> Samples:
    n = len(time_s)
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=(None,) * n,
        power_w=power_w,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
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


def _activity(
    *,
    modality: Modality = Modality.BIKE,
    sport: Sport = Sport.RIDE,
    samples: Samples,
) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
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


_DENSE_TIME = tuple(float(i) for i in range(3601))
_FULL_POWER = tuple(200 for _ in range(3601))
"""A fully-covered, one-hour-long power stream -- 3601 one-second samples so
the recorded span is exactly 3600 s -- used whenever a test needs the gate
to pass cleanly and wants to vary only ``metrics``/``ftp``."""


def _dense_activity(
    *, modality: Modality = Modality.BIKE, sport: Sport = Sport.RIDE
) -> Activity:
    return _activity(
        modality=modality, sport=sport, samples=_samples(_DENSE_TIME, _FULL_POWER)
    )


def _ftp(
    value: float,
    *,
    discipline: Sport | None = Sport.RIDE,
    measured_on: date = date(2026, 1, 1),
) -> Benchmark:
    return Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=discipline,
        value=value,
        measured_on=measured_on,
    )


_SETTINGS = SufficiencySettings()


def _metrics(
    *, normalized_power_w: float | None, moving_time_s: float | None
) -> DerivedMetrics:
    return DerivedMetrics(
        normalized_power_w=normalized_power_w, moving_time_s=moving_time_s
    )


# ---------------------------------------------------------------------------
# 1.6 / 4.8 -- one hour at threshold scores exactly 100, intensity 1.0
# (COGGAN_TSS verification case: 3600 s at FTP -> 100.0)
# ---------------------------------------------------------------------------


def test_one_hour_at_threshold_scores_exactly_100_with_intensity_1() -> None:
    metrics = _metrics(normalized_power_w=250.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == 100.0
    assert result.intensity == 1.0


# ---------------------------------------------------------------------------
# 1.11 -- the shared intensity relation, at threshold AND sub-threshold
# ---------------------------------------------------------------------------


def test_intensity_relation_holds_at_threshold() -> None:
    metrics = _metrics(normalized_power_w=250.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    expected = (result.scored_duration_s / 3600) * result.intensity**2 * 100
    assert result.load == pytest.approx(expected)


def test_intensity_relation_holds_at_a_sub_threshold_effort() -> None:
    """Sub-threshold, not the multiplicative-identity case: intensity here
    is 0.75, not 1.0, so a wrong implementation cannot coincide with the
    right one merely because 1.0 is neutral under multiplication."""
    metrics = _metrics(normalized_power_w=150.0, moving_time_s=1800.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(200.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(0.75)
    expected = (result.scored_duration_s / 3600) * result.intensity**2 * 100
    assert expected == pytest.approx(28.125)
    assert result.load == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 4.8 -- Coggan's own worked examples, named COGGAN_TSS
# ---------------------------------------------------------------------------


def test_worked_example_intensity_factor_210_over_280() -> None:
    """:data:`COGGAN_TSS`: IF = 210 / 280 = 0.75."""
    assert COGGAN_TSS.key == "coggan_tss"
    metrics = _metrics(normalized_power_w=210.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(280.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.intensity == pytest.approx(0.75)


def test_worked_example_7080s_np183_ftp215() -> None:
    """:data:`COGGAN_TSS`: 7080 s, NP 183 W, FTP 215 W -> TSS ~= 142 --
    expected derived from the shipped power_tss formula itself, not
    hardcoded."""
    assert COGGAN_TSS.key == "coggan_tss"
    expected = power_tss(183.0, 7080.0, 215.0)
    assert expected is not None
    assert expected == pytest.approx(142, abs=1)
    metrics = _metrics(normalized_power_w=183.0, moving_time_s=7080.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(215.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(expected)


def test_worked_example_5400s_np220_ftp250() -> None:
    """:data:`COGGAN_TSS`: 5400 s, NP 220 W, FTP 250 W -> TSS ~= 116."""
    assert COGGAN_TSS.key == "coggan_tss"
    expected = power_tss(220.0, 5400.0, 250.0)
    assert expected is not None
    assert expected == pytest.approx(116, abs=1)
    metrics = _metrics(normalized_power_w=220.0, moving_time_s=5400.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 4.3 -- delegation, not restatement: pin the CALL PATH
# ---------------------------------------------------------------------------


def test_compute_calls_power_tss_once_with_the_callers_exact_metrics_and_ftp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second, independently-tuned TSS formula could still match one
    fixture's number by coincidence; it cannot make ``power_tss`` itself
    get called. Monkeypatches the module-level ``power_tss`` name
    ``power.py`` calls and asserts it is invoked exactly once with the
    *exact* ``normalized_power_w``/``moving_time_s`` objects read off the
    caller's ``metrics`` (``is``, not just ``==``) and the exact ``ftp.value``
    -- and that the double's return value passes straight through
    unmodified."""
    calls: list[tuple[float, float, float]] = []
    sentinel = 12345.0

    def fake_power_tss(
        np_w: float | None, moving_time_s: float | None, ftp: float | None
    ) -> float | None:
        assert np_w is not None and moving_time_s is not None and ftp is not None
        calls.append((np_w, moving_time_s, ftp))
        return sentinel

    monkeypatch.setattr(power, "power_tss", fake_power_tss)

    metrics = _metrics(normalized_power_w=210.0, moving_time_s=3600.0)
    ftp = _ftp(280.0)
    result = power.compute(_dense_activity(), metrics, ftp=ftp, settings=_SETTINGS)

    assert len(calls) == 1
    called_np, called_moving, called_ftp = calls[0]
    assert called_np is metrics.normalized_power_w
    assert called_moving is metrics.moving_time_s
    assert called_ftp is ftp.value
    assert isinstance(result, ChannelLoad)
    assert result.load == sentinel


def test_power_tss_name_is_the_real_shipped_object_by_identity() -> None:
    """The monkeypatch test above proves the *shape* of delegation on one
    call; this proves the un-patched name ``power.power_tss`` genuinely
    *is* :func:`fitdocs.metrics.stress.power_tss` -- an ``is`` identity
    check, not a value-equality comparison. A value-equality version of
    this test (``result.load == fresh_power_tss(...)``) is the exact
    defect this spec has shipped before: it stays green under a lambda
    reimplementation that never calls the shipped function at all, and
    under production rebinding its call site to a private alias
    (``_shipped_power_tss = power_tss`` then calling
    ``_shipped_power_tss(...)``) -- both keep numeric agreement while
    breaking the delegation this test exists to pin. Identity on the
    module attribute itself has no such hole: either ``power.power_tss``
    is the one object :mod:`fitdocs.metrics.stress` defines, or it is not.
    """
    from fitdocs.metrics import stress as fresh_stress

    assert power.power_tss is fresh_stress.power_tss  # type: ignore[attr-defined]


def test_module_defines_no_second_function_and_rebinds_power_tss_nowhere() -> None:
    """Structural (Req 4.3): this module delegates to ``power_tss`` by name
    (asserted below), defines exactly one ``def``, ``compute``, and never
    reassigns the module-level ``power_tss`` name to anything else. The
    ``def`` check alone cannot see a restated formula stashed in a
    module-level ``lambda`` bound to a fresh name and called instead of
    the shipped one, or bound directly over ``power_tss`` itself (e.g.
    ``power_tss = lambda np_w, moving_time_s, ftp: ...``) -- both keep
    ``"power_tss("`` present in the source as a call site while quietly
    replacing what it points to, so this test also walks for any
    ``ast.Lambda`` node and for any ``ast.Assign``/``ast.AnnAssign`` whose
    target is named ``power_tss``, neither of which this module should
    ever contain (the name enters this module exactly once, via the
    top-level ``from fitdocs.metrics.stress import power_tss``)."""
    source = inspect.getsource(power)
    tree = ast.parse(source)
    assert "power_tss(" in source

    defined_functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ]
    assert {fn.name for fn in defined_functions} == {"compute"}

    lambdas = [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)]
    assert lambdas == []

    def _assigned_names(node: ast.AST) -> set[str]:
        names: set[str] = set()
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        return names

    reassigned = set()
    for node in ast.walk(tree):
        reassigned |= _assigned_names(node)
    assert "power_tss" not in reassigned


# ---------------------------------------------------------------------------
# 1.9 -- the wrong-quantity guard, called at entry, raises rather than
# computing or reporting insufficiency
# ---------------------------------------------------------------------------


def test_wrong_benchmark_kind_raises() -> None:
    wrong = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=160,
        measured_on=date(2026, 1, 1),
    )
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    with pytest.raises(ValueError, match="ftp_watts"):
        power.compute(_dense_activity(), metrics, ftp=wrong, settings=_SETTINGS)


def test_wrong_benchmark_kind_raises_before_the_no_benchmark_check() -> None:
    """The guard runs at entry, strictly before the NO_BENCHMARK check: a
    wrong-kind benchmark whose ``value`` is non-positive (``0``, which the
    NO_BENCHMARK check alone would treat as a plain missing benchmark)
    still raises. ``Benchmark`` is an unvalidated frozen dataclass, so a
    non-positive ``value`` is directly constructible here even though no
    real benchmark store would ever emit one. If ``require_kind`` moved to
    run *after* the ``ftp is None or ftp.value <= 0`` check, this exact
    fixture would silently come back as ``NO_BENCHMARK`` instead of
    raising -- contradicting Req 1.9's "fail loudly" and the "called at
    entry" step this module documents."""
    wrong = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=0,
        measured_on=date(2026, 1, 1),
    )
    metrics = _metrics(normalized_power_w=None, moving_time_s=None)
    empty_activity = _activity(samples=_samples((), ()))
    with pytest.raises(ValueError, match="ftp_watts"):
        power.compute(empty_activity, metrics, ftp=wrong, settings=_SETTINGS)


def test_no_benchmark_kind_check_when_ftp_is_none() -> None:
    """A ``None`` ftp never reaches ``require_kind`` at all -- confirmed by
    getting NO_BENCHMARK back rather than an ``AttributeError``
    (``'NoneType' object has no attribute 'kind'``) out of a guard that
    tried to read ``.kind`` off ``None``."""
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result = power.compute(_dense_activity(), metrics, ftp=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


# ---------------------------------------------------------------------------
# 4.2 / 4.4 -- NO_BENCHMARK: absent, zero, and negative
# ---------------------------------------------------------------------------


def test_no_benchmark_when_ftp_is_none() -> None:
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result = power.compute(_dense_activity(), metrics, ftp=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.POWER
    assert result.reason is InsufficiencyReason.NO_BENCHMARK
    assert "benchmark" in result.detail
    assert (
        "threshold-power" in result.detail
        or "functional-threshold-power" in result.detail
    )


def test_no_benchmark_when_ftp_value_is_zero() -> None:
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(0.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


def test_no_benchmark_when_ftp_value_is_negative() -> None:
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(-10.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


def test_no_benchmark_beats_a_failing_gate() -> None:
    """Postcondition order (Req 4.4 before 4.6): a missing benchmark is
    reported as NO_BENCHMARK even when the power stream would also fail
    the gate."""
    empty_activity = _activity(samples=_samples((), ()))
    metrics = _metrics(normalized_power_w=None, moving_time_s=None)
    result = power.compute(empty_activity, metrics, ftp=None, settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NO_BENCHMARK


# ---------------------------------------------------------------------------
# 4.6 -- gate on the power stream; passes through the gate's own reason
# ---------------------------------------------------------------------------


def test_stream_absent_when_power_never_recorded() -> None:
    time_s = tuple(float(i) for i in range(120))
    samples = _samples(time_s, (None,) * len(time_s))
    activity = _activity(samples=samples)
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=120.0)
    result = power.compute(activity, metrics, ftp=_ftp(250.0), settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.POWER
    assert result.reason is InsufficiencyReason.STREAM_ABSENT


def test_too_short_when_recorded_span_below_minimum_duration() -> None:
    time_s = (0.0, 1.0, 2.0)
    samples = _samples(time_s, (200, 200, 200))
    activity = _activity(samples=samples)
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=2.0)
    result = power.compute(activity, metrics, ftp=_ftp(250.0), settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.TOO_SHORT


def test_stream_coverage_when_below_configured_minimum() -> None:
    # 120 samples, 1 s apart -> 119 s span; only ~half the span covered.
    time_s = tuple(float(i) for i in range(120))
    power_w = tuple(200 if i < 60 else None for i in range(120))
    samples = _samples(time_s, power_w)
    activity = _activity(samples=samples)
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=59.0)
    result = power.compute(activity, metrics, ftp=_ftp(250.0), settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_COVERAGE
    assert result.observed is not None
    assert result.required == pytest.approx(0.80)


def test_gate_failure_beats_not_computable() -> None:
    """Postcondition order (Req 4.6 before 4.5): a stream that fails the
    gate is reported by the gate's own reason, never NOT_COMPUTABLE, even
    when normalized power and moving time are both also absent."""
    time_s = tuple(float(i) for i in range(120))
    samples = _samples(time_s, (None,) * len(time_s))
    activity = _activity(samples=samples)
    metrics = _metrics(normalized_power_w=None, moving_time_s=None)
    result = power.compute(activity, metrics, ftp=_ftp(250.0), settings=_SETTINGS)
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.STREAM_ABSENT


# ---------------------------------------------------------------------------
# 4.5 -- NOT_COMPUTABLE when NP or moving time is missing, gate having passed
# ---------------------------------------------------------------------------


def test_not_computable_when_normalized_power_missing() -> None:
    metrics = _metrics(normalized_power_w=None, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.channel is ChannelId.POWER
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE
    assert "normalized power" in result.detail or "duration" in result.detail
    assert "benchmark" not in result.detail


def test_not_computable_when_moving_time_missing() -> None:
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=None)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(250.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelInsufficient)
    assert result.reason is InsufficiencyReason.NOT_COMPUTABLE


def test_not_computable_and_no_benchmark_are_pairwise_distinct_reasons() -> None:
    """Defect-species guard: the two reasons this module itself constructs
    must actually be different enum members -- and different ``detail``
    text -- not two fixtures that happen to share one value at either
    site."""
    metrics_missing = _metrics(normalized_power_w=None, moving_time_s=3600.0)
    not_computable = power.compute(
        _dense_activity(), metrics_missing, ftp=_ftp(250.0), settings=_SETTINGS
    )
    no_benchmark = power.compute(
        _dense_activity(), metrics_missing, ftp=None, settings=_SETTINGS
    )
    assert isinstance(not_computable, ChannelInsufficient)
    assert isinstance(no_benchmark, ChannelInsufficient)
    assert not_computable.reason is InsufficiencyReason.NOT_COMPUTABLE
    assert no_benchmark.reason is InsufficiencyReason.NO_BENCHMARK
    assert not_computable.detail != no_benchmark.detail


# ---------------------------------------------------------------------------
# 2.7 (restated on ChannelLoad) -- coverage and duration still reported when
# the gate passes; channel id and anchor identity on the success path
# ---------------------------------------------------------------------------


def test_successful_result_carries_coverage_and_scored_duration() -> None:
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    ftp = _ftp(250.0)
    result = power.compute(_dense_activity(), metrics, ftp=ftp, settings=_SETTINGS)
    assert isinstance(result, ChannelLoad)
    assert result.channel is ChannelId.POWER
    assert result.coverage.stream == "power"
    assert result.coverage.fraction == pytest.approx(1.0)
    assert result.scored_duration_s == 3600.0
    assert result.anchor is ftp


def test_successful_result_reports_true_coverage_not_a_fabricated_one() -> None:
    """The gate-passing fixture used throughout this module (``_FULL_POWER``)
    is 100%-covered, which cannot distinguish a reported ``StreamCoverage``
    from one a broken implementation fabricated wholesale (e.g. always
    reporting ``covered_s == total_s``) -- 100% is what a fabrication would
    guess too. This fixture instead drops out for exactly the trailing
    10% of a 1000 s, evenly-spaced span, so the gate passes (coverage is
    above the 0.80 default) while the reported ``covered_s``/``total_s``
    pin an actual measured fraction the gate computed, not a constant."""
    time_s = tuple(float(i) for i in range(1001))
    power_w = tuple(200 if i < 900 else None for i in range(1001))
    activity = _activity(samples=_samples(time_s, power_w))
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=900.0)
    result = power.compute(activity, metrics, ftp=_ftp(250.0), settings=_SETTINGS)
    assert isinstance(result, ChannelLoad)
    assert result.coverage.total_s == pytest.approx(1000.0)
    assert result.coverage.covered_s == pytest.approx(900.0)
    assert result.coverage.fraction == pytest.approx(0.9)


def test_stricter_min_duration_from_settings_reds_a_default_passing_fixture() -> None:
    """Every other fixture in this module passes the module-level default
    ``_SETTINGS = SufficiencySettings()`` -- so nothing here pins that
    ``compute``'s ``settings`` parameter is the one actually consulted by
    the gate rather than, say, a hardcoded default built inside
    ``compute`` itself. A 90 s activity passes the default 60 s minimum
    duration; handed a caller-supplied ``SufficiencySettings`` whose
    ``min_duration_s`` is raised to 120, the identical activity must fail
    the gate with TOO_SHORT instead."""
    time_s = tuple(float(i) for i in range(91))
    power_w = tuple(200 for _ in range(91))
    activity = _activity(samples=_samples(time_s, power_w))
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=90.0)
    ftp = _ftp(250.0)

    passes_default = power.compute(
        activity, metrics, ftp=ftp, settings=SufficiencySettings()
    )
    assert isinstance(passes_default, ChannelLoad)

    stricter = SufficiencySettings(min_duration_s=120)
    fails_stricter = power.compute(activity, metrics, ftp=ftp, settings=stricter)
    assert isinstance(fails_stricter, ChannelInsufficient)
    assert fails_stricter.reason is InsufficiencyReason.TOO_SHORT


def test_stricter_power_coverage_override_reds_a_shared_minimum_passing_fixture() -> (
    None
):
    """Same point as above, isolating the per-channel override path (Req
    3.2, restated at this boundary by Req 4.6's "configured minimum"): a
    fixture whose coverage clears the *shared* 0.80 default but not a
    caller-supplied ``power_min_stream_coverage`` override must fail the
    gate under the stricter settings and pass under the default."""
    time_s = tuple(float(i) for i in range(101))
    # 86 of 100 one-second intervals covered -> coverage 0.86: clears the
    # shared 0.80 default, fails a 0.90 power-specific override.
    power_w = tuple(200 if i < 86 else None for i in range(101))
    activity = _activity(samples=_samples(time_s, power_w))
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=86.0)
    ftp = _ftp(250.0)

    passes_default = power.compute(
        activity, metrics, ftp=ftp, settings=SufficiencySettings()
    )
    assert isinstance(passes_default, ChannelLoad)

    stricter = SufficiencySettings(power_min_stream_coverage=0.90)
    fails_stricter = power.compute(activity, metrics, ftp=ftp, settings=stricter)
    assert isinstance(fails_stricter, ChannelInsufficient)
    assert fails_stricter.reason is InsufficiencyReason.STREAM_COVERAGE
    assert fails_stricter.required == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# 4.7 -- modality-agnostic (running scored too); anchoring discipline and
# measurement date reported among the inputs -- from the BENCHMARK's
# discipline, never the activity's own sport/modality
# ---------------------------------------------------------------------------


def test_running_activity_is_scored_like_any_other_modality() -> None:
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(modality=Modality.RUN, sport=Sport.RUN),
        metrics,
        ftp=_ftp(250.0, discipline=Sport.RUN),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    assert result.load == pytest.approx(power_tss(200.0, 3600.0, 250.0))


def test_inputs_used_carries_anchoring_discipline_and_measurement_date() -> None:
    """The activity's own ``sport`` (``Ride``) and the benchmark's
    ``discipline`` (``Run``) are deliberately DIFFERENT values here: a
    prior version of this fixture set both to ``Run``, so a production
    swap of ``ftp.discipline.value`` for ``activity.sport.value`` (the
    exact "not decided by the activity's own modality" claim this
    module's docstring makes) produced the identical string and stayed
    green. With the two disciplines split, only reading the benchmark's
    own discipline can pass."""
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    measured = date(2026, 3, 14)
    result = power.compute(
        _dense_activity(modality=Modality.BIKE, sport=Sport.RIDE),
        metrics,
        ftp=_ftp(250.0, discipline=Sport.RUN, measured_on=measured),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    inputs = dict(result.inputs_used)
    assert inputs["anchoring_discipline"] == "Run"
    assert inputs["ftp_measured_on"] == measured.isoformat()


def test_inputs_used_reports_athlete_for_a_discipline_less_benchmark() -> None:
    """An athlete-wide benchmark (``discipline=None``, as e.g. a
    max-heart-rate benchmark would carry -- FTP itself is always
    discipline-scoped in practice, but ``compute`` reads whatever
    ``ftp.discipline`` actually holds without assuming) reports the
    reserved ``"athlete"`` token, not a silently different fallback
    string and not the activity's own sport."""
    metrics = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(modality=Modality.BIKE, sport=Sport.RIDE),
        metrics,
        ftp=_ftp(250.0, discipline=None),
        settings=_SETTINGS,
    )
    assert isinstance(result, ChannelLoad)
    inputs = dict(result.inputs_used)
    assert inputs["anchoring_discipline"] == "athlete"


def test_inputs_used_carries_normalized_power_and_ftp() -> None:
    metrics = _metrics(normalized_power_w=183.0, moving_time_s=3600.0)
    result = power.compute(
        _dense_activity(), metrics, ftp=_ftp(215.0), settings=_SETTINGS
    )
    assert isinstance(result, ChannelLoad)
    inputs = dict(result.inputs_used)
    assert inputs["normalized_power_w"] == "183"
    assert inputs["ftp_watts"] == "215"


# ---------------------------------------------------------------------------
# 1.7 -- independence: sequential calls with different inputs never leak
# state into one another
# ---------------------------------------------------------------------------


def test_sequential_calls_are_independent() -> None:
    metrics_a = _metrics(normalized_power_w=200.0, moving_time_s=3600.0)
    result_a = power.compute(
        _dense_activity(), metrics_a, ftp=_ftp(250.0), settings=_SETTINGS
    )

    metrics_b = _metrics(normalized_power_w=None, moving_time_s=None)
    result_b = power.compute(_dense_activity(), metrics_b, ftp=None, settings=_SETTINGS)

    metrics_c = _metrics(normalized_power_w=210.0, moving_time_s=3600.0)
    result_c = power.compute(
        _dense_activity(), metrics_c, ftp=_ftp(280.0), settings=_SETTINGS
    )

    assert isinstance(result_a, ChannelLoad)
    assert result_a.intensity == pytest.approx(0.8)
    assert isinstance(result_b, ChannelInsufficient)
    assert result_b.reason is InsufficiencyReason.NO_BENCHMARK
    assert isinstance(result_c, ChannelLoad)
    assert result_c.intensity == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# 4.9 -- the intervals.icu divergence is recorded, linked to the correct
# DIVERGENCES entry -- this pins the entry's *identity* and a distinctive
# clause from its own *reason* text (not just three common substrings a
# fabricated or even an inverted paragraph could also satisfy)
# ---------------------------------------------------------------------------


def test_module_docstring_names_the_correct_divergence_entry() -> None:
    """Three cheap substrings (the behavior key, "intervals.icu", "does
    not ingest") are necessary but not sufficient: a fabricated causal
    clause, or one that inverts the real reason, can still contain all
    three. This also asserts a distinctive phrase lifted verbatim from
    :data:`DIVERGENCES`' own ``reason`` text -- "fabricate an absence that
    is not real" -- so the module docstring's causal claim is checked
    against the source record it claims to paraphrase, not merely
    checked for topic words."""
    running_power_divergence = next(
        d for d in DIVERGENCES if d.behavior == "running_power_from_recorded_watts"
    )
    assert "fabricate an absence that is not real" in running_power_divergence.reason

    doc = inspect.getdoc(power) or ""
    assert running_power_divergence.behavior in doc
    assert "intervals.icu" in doc
    assert "does not ingest" in doc
    assert "fabricate an absence that is not real" in doc
