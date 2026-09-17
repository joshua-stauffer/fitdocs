"""Tests for `fitdocs.load.qa.divergence.evaluate` (design: DivergenceAnalysis,
task 2.3).

Covers Requirements 1.3, 1.4, 1.5, 1.10, 3.1-3.7, 3.9 -- see
``.kiro/specs/activity-qa-flags/requirements.md`` and design.md's
"DivergenceAnalysis" component section.

**Own test module** (Test File Ownership / "Shared test fixture" note in
tasks.md): every constructed :class:`ChannelOutcome` this task needs is
built here, not added to ``tests/load/qa/conftest.py``, which task 2.1 owns
and tasks 2.3/2.4/2.5 must not touch to keep their ``(P)`` markers safe.

**Why the sub-threshold regression case (Req 3.9) is the module's most
important test.** Before ``load-channels`` Requirement 1.11 landed,
heart-rate intensity was the *square* of what power and pace reported for
the same load, so the two scales coincided only at exactly 1.0 (threshold);
every check that only ever probed threshold effort passed while the
comparison was wrong everywhere else, reading *divergent* on easy aerobic
sessions where the channels actually agreed. A fixture built *at* threshold
cannot distinguish the corrected definition from that defective one --
``sqrt(x)``, ``x`` and ``x**2`` are all ``1.0`` at ``x == 1.0``. The
fixtures below therefore anchor well below threshold (``intensity ~= 0.58``,
never near ``1.0``) wherever this module's core invariant is pinned.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
    InsufficiencyReason,
    StreamCoverage,
)
from fitdocs.load.qa.divergence import DivergenceOutcome, evaluate
from fitdocs.load.qa.types import FlagSettings
from fitdocs.model import Sport

# ---------------------------------------------------------------------------
# fixture builders -- self-contained in this module (task boundary above)
# ---------------------------------------------------------------------------

_ANCHOR_KIND: dict[ChannelId, BenchmarkKind] = {
    ChannelId.POWER: BenchmarkKind.FTP_WATTS,
    ChannelId.HEART_RATE: BenchmarkKind.LTHR_BPM,
    ChannelId.PACE: BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
}


def _anchor(channel: ChannelId) -> Benchmark:
    return Benchmark(
        kind=_ANCHOR_KIND[channel],
        discipline=Sport.RUN,
        value=100.0,
        measured_on=date(2026, 1, 1),
    )


def _coverage(channel: ChannelId, total_s: float) -> StreamCoverage:
    return StreamCoverage(stream=channel.value, covered_s=total_s, total_s=total_s)


def _channel_load(
    channel: ChannelId,
    *,
    intensity: float,
    load: float,
    scored_duration_s: float = 3600.0,
) -> ChannelLoad:
    """Build a :class:`ChannelLoad` with an arbitrary, independently chosen
    ``load`` -- deliberately *not* recomputed from ``intensity`` via the
    shared semantic, so tests that vary ``load`` while holding ``intensity``
    fixed genuinely prove this module never reads ``.load``."""
    return ChannelLoad(
        channel=channel,
        load=load,
        intensity=intensity,
        anchor=_anchor(channel),
        scored_duration_s=scored_duration_s,
        coverage=_coverage(channel, scored_duration_s),
        inputs_used=(),
    )


def _insufficient(channel: ChannelId, *, detail: str) -> ChannelInsufficient:
    return ChannelInsufficient(
        channel=channel,
        reason=InsufficiencyReason.STREAM_ABSENT,
        detail=detail,
    )


_SETTINGS = FlagSettings(divergence_max_intensity_delta=0.20)


# ---------------------------------------------------------------------------
# 1. heart-rate selected -> not-assessed, no self-comparison (Req 3.5)
# ---------------------------------------------------------------------------


def test_heart_rate_selected_reports_not_assessed() -> None:
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.7, load=50.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.HEART_RATE, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.NOT_ASSESSED
    assert reading.selected_channel is ChannelId.HEART_RATE
    assert reading.selected_intensity is None
    assert reading.heart_rate_intensity is None
    assert reading.delta is None
    assert reading.tolerance == 0.20
    assert reading.not_assessed_reason is not None
    assert "no second channel" in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# 2. heart-rate insufficient -> not-assessed, reason carried verbatim (Req 3.6)
# ---------------------------------------------------------------------------


def test_heart_rate_insufficient_carries_reason_verbatim() -> None:
    detail = "heart-rate stream recorded no value anywhere in this activity"
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.7, load=50.0),
        ChannelId.HEART_RATE: _insufficient(ChannelId.HEART_RATE, detail=detail),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.NOT_ASSESSED
    assert reading.selected_intensity is None
    assert reading.heart_rate_intensity is None
    assert reading.delta is None
    # Verbatim: identity-equal string content, not a paraphrase or rebuild.
    assert reading.not_assessed_reason == detail


def test_heart_rate_outcome_absent_reports_not_assessed_not_keyerror() -> None:
    """Req 1.10: the module shall not raise for absent channel data. Today
    `threshold-load` always evaluates all three channels, so `outcomes`
    always carries a HEART_RATE entry in practice -- but this module must
    not assume that and crash with a `KeyError` if it ever didn't (design's
    Implementation Notes name this exact scenario as a revalidation
    trigger)."""
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.7, load=50.0),
        # ChannelId.HEART_RATE deliberately omitted entirely.
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.NOT_ASSESSED
    assert reading.selected_intensity is None
    assert reading.heart_rate_intensity is None
    assert reading.delta is None
    assert reading.not_assessed_reason is not None
    assert reading.not_assessed_reason != ""
    # Distinct from the ChannelInsufficient-carried-detail path above.
    assert (
        reading.not_assessed_reason
        != "heart-rate stream recorded no value anywhere in this activity"
    )
    assert "not evaluated" in reading.not_assessed_reason


# ---------------------------------------------------------------------------
# 3. divergent / agreed, both carrying intensities, delta and tolerance
#    (Req 3.2, 3.3) -- vary which channel is selected (PACE here, not POWER)
#    and which channel reads higher, to avoid a "compares against a
#    constant" implementation passing.
# ---------------------------------------------------------------------------


def test_divergent_when_delta_exceeds_tolerance_selected_higher() -> None:
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.PACE: _channel_load(ChannelId.PACE, intensity=0.90, load=72.9),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.60, load=36.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.PACE, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.DIVERGENT
    assert reading.selected_channel is ChannelId.PACE
    assert reading.selected_intensity == 0.90
    assert reading.heart_rate_intensity == 0.60
    assert reading.delta == pytest.approx(0.30)
    assert reading.tolerance == 0.20
    assert reading.not_assessed_reason is None


def test_divergent_when_delta_exceeds_tolerance_heart_rate_higher() -> None:
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.50, load=25.0),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.85, load=72.25
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.DIVERGENT
    assert reading.delta == pytest.approx(0.35)


def test_agreed_when_delta_within_tolerance() -> None:
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.PACE: _channel_load(ChannelId.PACE, intensity=0.65, load=42.25),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.70, load=49.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.PACE, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.AGREED
    assert reading.selected_intensity == 0.65
    assert reading.heart_rate_intensity == 0.70
    assert reading.delta == pytest.approx(0.05)
    assert reading.tolerance == 0.20
    assert reading.not_assessed_reason is None


# ---------------------------------------------------------------------------
# Boundary-exactness: delta == tolerance is AGREED (not DIVERGENT); a small
# increment above tolerance is DIVERGENT. Pins the `>` (not `>=`) choice.
# ---------------------------------------------------------------------------


def test_delta_exactly_equal_to_tolerance_is_agreed() -> None:
    # heart_rate_intensity pinned at 0.0 so the subtraction below is exact
    # in binary floating point: 0.20 - 0.0 == 0.20 bit-for-bit, which lets
    # this test pin the `>` (not `>=`) boundary precisely rather than
    # merely approximately.
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.20, load=4.0),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.0, load=0.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.delta == _SETTINGS.divergence_max_intensity_delta
    assert reading.outcome is DivergenceOutcome.AGREED


def test_delta_just_above_tolerance_is_divergent() -> None:
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.21, load=4.41),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.0, load=0.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.delta > _SETTINGS.divergence_max_intensity_delta
    assert reading.outcome is DivergenceOutcome.DIVERGENT


def test_non_default_tolerance_is_actually_read_from_settings() -> None:
    """The tolerance the module compares against must come from
    ``settings.divergence_max_intensity_delta``, not a hardcoded copy of the
    module's own default (which also happens to be 0.20, so every other
    fixture in this module that uses ``_SETTINGS`` alone cannot tell the two
    apart). Configure a deliberately NON-default tolerance (0.35) with a
    delta (0.30) that the shipped default (0.20) would call DIVERGENT but
    the configured 0.35 calls AGREED."""
    settings = FlagSettings(divergence_max_intensity_delta=0.35)
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.90, load=72.9),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.60, load=36.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=settings)

    assert reading.delta == pytest.approx(0.30)
    assert reading.tolerance == 0.35
    assert reading.outcome is DivergenceOutcome.AGREED


# ---------------------------------------------------------------------------
# 4. Req 3.4, 3.7, 3.9 -- the module reads only .intensity, never .load.
# ---------------------------------------------------------------------------


def test_equal_intensities_with_wildly_different_loads_still_agree() -> None:
    """Two channels reporting the *same* intensity but wildly different
    ``load`` values must still read AGREED with delta == 0.0: proves the
    module never reads `.load` (Req 3.4, 3.7). This is also the test that
    discriminates a bug that reads `.load` where `.intensity` belongs on
    *both* sides of the comparison at once -- the Req 3.9 regression test
    above cannot, by construction of its own premise (see the scope note in
    its docstring), because its two loads are equal too."""
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.65, load=5.0),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.65, load=5000.0
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.AGREED
    assert reading.delta == 0.0


def _intensity_from_load(load: float, scored_duration_s: float) -> float:
    """Solve the shared relation ``load == hours * intensity**2 * 100`` for
    ``intensity`` given ``load`` and ``scored_duration_s``. Used to derive
    the regression fixture's intensity FROM its load, rather than choosing
    the two independently, so the fixture is tied to the real semantic
    rather than two numbers that merely happen to match."""
    hours = scored_duration_s / 3600.0
    return math.sqrt(load / (hours * 100.0))


def test_sub_threshold_regression_reports_agreed_with_zero_delta() -> None:
    """Req 3.9's regression case: the selected channel and the heart-rate
    channel report the SAME load for the SAME scored duration at an effort
    clearly BELOW threshold (intensity ~= 0.58, load ~= 33.5 for one hour --
    the exact numbers design.md's worked table uses, corresponding to a
    120 bpm heart rate against the corrected shared intensity semantic).
    ``intensity`` is derived FROM ``load`` via the shared relation
    (:func:`_intensity_from_load`), not chosen independently, so the two
    fields are genuinely linked rather than coincidentally equal.

    A fixture built AT threshold (intensity == 1.0) cannot distinguish this
    from the historical defect, where heart-rate intensity was the square of
    the other channels' intensity for the same load: `sqrt(x) == x == x**2`
    only at `x == 1.0`. This fixture is deliberately anchored well below
    that point and must never be "simplified" back to a threshold-only case.

    **Scope note on what this specific test can and cannot discriminate.**
    Req 3.9's own premise is "the same load for the same scored duration" --
    which, under the shared relation, necessarily makes the two channels'
    *intensities* equal too. That means a hypothetical bug that swaps
    ``.intensity`` for ``.load`` on *both* sides of the comparison is
    mathematically indistinguishable from correct behaviour by this fixture
    alone: both readings are equal either way, so both a correct and a fully
    field-swapped implementation report AGREED with delta 0.0 here. That
    mutation is caught instead by
    ``test_equal_intensities_with_wildly_different_loads_still_agree``
    below, whose fixture deliberately gives the two channels equal
    intensities but *unequal* loads for exactly this reason. This test's own
    job is narrower and different: pinning the corrected sub-threshold scale
    (Req 3.9's historical defect), not field selection.
    """
    load = 33.64  # design.md's worked-table figure for 120 bpm, one hour
    scored_duration_s = 3600.0
    intensity = _intensity_from_load(load, scored_duration_s)
    assert intensity == pytest.approx(0.58, abs=1e-3)
    assert intensity < 0.9  # guard: genuinely sub-threshold, not near 1.0

    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.PACE: _channel_load(
            ChannelId.PACE,
            intensity=intensity,
            load=load,
            scored_duration_s=scored_duration_s,
        ),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE,
            intensity=intensity,
            load=load,
            scored_duration_s=scored_duration_s,
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.PACE, settings=_SETTINGS)

    assert reading.outcome is DivergenceOutcome.AGREED
    assert reading.delta == 0.0


# ---------------------------------------------------------------------------
# 5. Req 3.8 (lighter touch here; task 3.1 owns the full proof) -- the
#    non-HR selected channel generalizes: PACE is exercised above, POWER
#    below, so the function does not special-case one channel.
# ---------------------------------------------------------------------------


def test_power_selected_also_supported() -> None:
    outcomes: dict[ChannelId, ChannelOutcome] = {
        ChannelId.POWER: _channel_load(ChannelId.POWER, intensity=0.55, load=30.25),
        ChannelId.HEART_RATE: _channel_load(
            ChannelId.HEART_RATE, intensity=0.55, load=30.25
        ),
    }

    reading = evaluate(outcomes, selected=ChannelId.POWER, settings=_SETTINGS)

    assert reading.selected_channel is ChannelId.POWER
    assert reading.outcome is DivergenceOutcome.AGREED
