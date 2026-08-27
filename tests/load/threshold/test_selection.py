"""Contract tests for :mod:`fitdocs.load.threshold.selection` (task 2.2, Req
5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.3, 8.4, 8.5, 8.9).

``selection.py`` is two pure functions: ``select`` walks a configured order
and returns the first computed channel, or ``None``; ``non_selected_values``
records every other channel, in the fixed canonical order, with a value or
the channel's own reason.

These tests are built to defeat, not merely exercise:

- a selector that reads ``order`` at all correctly but that also peeks at a
  load's magnitude, intensity, coverage or anchor recency (Req 6.5) -- proven
  behaviorally with a fixture that gives the first channel in ``order`` a
  *middle* value on every other dimension, one channel above it and one
  below, so ranking by any of those fields in *either* direction returns a
  different channel; corroborated by a structural ``inspect.getsource`` scan
  for a stray attribute read.
- a selector that returns records in the configured order rather than the
  fixed canonical order (Req 8.9) -- proven with a configured order that is
  a genuine permutation of the canonical order, never equal to it;
- a selector that confuses "computed but beaten" with "computed but out of
  order" (Req 6.4, 8.4) -- each reason gets its own fixture and its own
  mutation, and neither substring alone is asserted;
- a selector that pads an absent value with ``0.0`` (Req 8.5) -- asserted
  with ``value is None``, never ``not value``;
- a selector whose three channels tie on load, hiding a routing defect
  behind an accidental pairwise symmetry -- every fixture below uses three
  distinct load values.
"""

from __future__ import annotations

import inspect
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
from fitdocs.load.threshold import selection
from fitdocs.load.threshold.selection import (
    CANONICAL_CHANNELS,
    CHANNEL_LABELS,
    non_selected_values,
    select,
)
from fitdocs.model import Sport

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _bench(kind: BenchmarkKind, value: float, day: date) -> Benchmark:
    return Benchmark(kind=kind, discipline=Sport.RUN, value=value, measured_on=day)


def _load(
    channel: ChannelId,
    value: float,
    *,
    intensity: float = 1.0,
    covered_s: float = 3600.0,
    measured_on: date = date(2026, 1, 1),
) -> ChannelLoad:
    """A computed outcome for ``channel`` carrying a *distinct* load value
    so pairwise channel swaps are never masked by a tie. ``intensity``,
    ``covered_s`` and ``measured_on`` default to values shared across every
    fixture but can be varied independently of ``value`` so a selector
    ranking by one of them (rather than walking ``order``) can be caught
    (Req 6.5)."""
    kind = {
        ChannelId.POWER: BenchmarkKind.FTP_WATTS,
        ChannelId.HEART_RATE: BenchmarkKind.LTHR_BPM,
        ChannelId.PACE: BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
    }[channel]
    return ChannelLoad(
        channel=channel,
        load=value,
        intensity=intensity,
        anchor=_bench(kind, 250.0, measured_on),
        scored_duration_s=3600.0,
        coverage=StreamCoverage(
            stream=channel.value, covered_s=covered_s, total_s=3600.0
        ),
        inputs_used=(("input", "value"),),
    )


def _insufficient(channel: ChannelId, detail: str) -> ChannelInsufficient:
    return ChannelInsufficient(
        channel=channel, reason=InsufficiencyReason.NO_BENCHMARK, detail=detail
    )


# Three pairwise-distinct load values used throughout. Each carries a
# fractional remainder that ``round(load)`` and ``round(load, 1)`` both
# disturb, so an equality assertion against these constants pins Req 5.4's
# "carried verbatim" claim rather than surviving a rounding mutant by
# accident (whole numbers survive both).
POWER_LOAD = 111.4375
HR_LOAD = 222.6875
PACE_LOAD = 333.0625


def _outcomes(
    power: ChannelOutcome, hr: ChannelOutcome, pace: ChannelOutcome
) -> dict[ChannelId, ChannelOutcome]:
    return {ChannelId.POWER: power, ChannelId.HEART_RATE: hr, ChannelId.PACE: pace}


# ---------------------------------------------------------------------------
# CANONICAL_CHANNELS / CHANNEL_LABELS
# ---------------------------------------------------------------------------


def test_canonical_channels_is_power_heart_rate_pace_in_order() -> None:
    assert CANONICAL_CHANNELS == (ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE)


def test_channel_labels_cover_all_three_channels_with_expected_text() -> None:
    assert CHANNEL_LABELS == {
        ChannelId.POWER: "Power",
        ChannelId.HEART_RATE: "Heart rate",
        ChannelId.PACE: "Pace",
    }


# ---------------------------------------------------------------------------
# select -- priority walk (6.1, 6.2, 6.3, 6.4, 6.5)
# ---------------------------------------------------------------------------


def test_select_picks_the_first_computed_channel_in_the_configured_order() -> None:
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    order = [ChannelId.HEART_RATE, ChannelId.POWER, ChannelId.PACE]
    assert select(outcomes, order) is ChannelId.HEART_RATE


def test_select_skips_earlier_insufficient_channels() -> None:
    outcomes = _outcomes(
        _insufficient(ChannelId.POWER, "no FTP on file"),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    assert select(outcomes, order) is ChannelId.HEART_RATE


def test_select_returns_none_when_every_channel_is_insufficient() -> None:
    outcomes = _outcomes(
        _insufficient(ChannelId.POWER, "no FTP on file"),
        _insufficient(ChannelId.HEART_RATE, "no LTHR on file"),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    assert select(outcomes, order) is None


def test_select_never_returns_a_computed_channel_absent_from_the_order() -> None:
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _insufficient(ChannelId.HEART_RATE, "no LTHR on file"),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    # POWER computed, but the configured order for this discipline never
    # names it -- must not be selected even though it is the only computed
    # channel present.
    order = [ChannelId.HEART_RATE, ChannelId.PACE]
    assert select(outcomes, order) is None


def test_select_with_single_channel_order_finds_a_later_channel() -> None:
    """Design's own validation note: the canonical record order must hold
    whether the configured order was ``["pace", "power"]`` or ``["power"]``
    -- this exercises the single-entry configured order directly."""
    outcomes = _outcomes(
        _insufficient(ChannelId.POWER, "no FTP on file"),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    assert select(outcomes, [ChannelId.PACE]) is ChannelId.PACE


def test_select_reads_no_value_altering_non_selected_load_leaves_selection() -> None:
    """Behavioral proof of Req 6.5. The mutated channel (PACE) is genuinely
    present, computed and *not* selected in both worlds -- the unreachable-
    scenario check -- so the identical selection is real evidence the walk
    never read a value, not a vacuous pass. ``select`` never produces a
    value of its own; that a *selected value* is unchanged is proved where
    one first exists, at the outcome/record level (task 3.2, 3.3)."""
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    baseline = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    mutated = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, 999_999.0),  # wildly different, still computed
    )

    baseline_selected = select(baseline, order)
    mutated_selected = select(mutated, order)

    assert baseline_selected is ChannelId.POWER
    assert mutated_selected is ChannelId.POWER
    assert baseline_selected == mutated_selected

    # The unreachable-scenario guard: PACE really is present and computed
    # (not e.g. accidentally insufficient) in both worlds, and really is
    # not the selected channel -- so this mutation had a real chance to
    # move the answer if magnitude were consulted.
    assert isinstance(baseline[ChannelId.PACE], ChannelLoad)
    assert isinstance(mutated[ChannelId.PACE], ChannelLoad)
    assert baseline[ChannelId.PACE].load != mutated[ChannelId.PACE].load
    assert baseline_selected != ChannelId.PACE


def test_select_ignores_intensity_coverage_anchor_favoring_a_loser() -> None:
    """Behavioral proof that ``select`` ranks by ``order`` position alone,
    never by magnitude, intensity, coverage or anchor recency (Req 6.5). The
    first channel in ``order`` is given a *middle* value on every other
    dimension -- another channel is higher and another is lower on each of
    intensity, coverage and anchor recency -- so a selector ranking by any
    of those fields, in *either* direction, returns a different channel.
    Seating the winner at an extremum would catch only one direction: an
    ascending ranker would pick it for the same reason a descending one
    rejects it."""
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    outcomes = _outcomes(
        _load(
            ChannelId.POWER,
            POWER_LOAD,
            intensity=0.5,
            covered_s=1800.0,
            measured_on=date(2023, 1, 1),
        ),
        _load(
            ChannelId.HEART_RATE,
            HR_LOAD,
            intensity=0.99,
            covered_s=3599.0,
            measured_on=date(2026, 1, 1),
        ),
        _load(
            ChannelId.PACE,
            PACE_LOAD,
            intensity=0.01,
            covered_s=10.0,
            measured_on=date(2020, 1, 1),
        ),
    )
    # The winner must be STRICTLY BETWEEN the other two on every varied
    # dimension -- the unreachable-scenario guard for this fixture. An
    # extremum would leave one ranking direction untested.
    power_outcome = outcomes[ChannelId.POWER]
    hr_outcome = outcomes[ChannelId.HEART_RATE]
    pace_outcome = outcomes[ChannelId.PACE]
    assert isinstance(power_outcome, ChannelLoad)
    assert isinstance(hr_outcome, ChannelLoad)
    assert isinstance(pace_outcome, ChannelLoad)
    assert pace_outcome.intensity < power_outcome.intensity < hr_outcome.intensity
    assert (
        pace_outcome.coverage.covered_s
        < power_outcome.coverage.covered_s
        < hr_outcome.coverage.covered_s
    )
    assert (
        pace_outcome.anchor.measured_on
        < power_outcome.anchor.measured_on
        < hr_outcome.anchor.measured_on
    )

    assert select(outcomes, order) is ChannelId.POWER


def test_select_source_never_reads_load_intensity_coverage_or_anchor() -> None:
    """Structural corroboration (not the only evidence -- paired with the
    behavioral proof above) that the walk touches no ChannelLoad field
    beyond isinstance narrowing."""
    source = inspect.getsource(select)
    for forbidden in (".load", ".intensity", ".coverage", ".anchor", ".measured_on"):
        assert forbidden not in source, f"select() source reads {forbidden!r}"


# ---------------------------------------------------------------------------
# non_selected_values -- canonical order (8.9)
# ---------------------------------------------------------------------------


def test_non_selected_values_canonical_order_independent_of_configured_order() -> None:
    """The configured order below is a genuine permutation, not merely
    absent -- if it happened to equal CANONICAL_CHANNELS this test would not
    distinguish the canonical-order rule from an accidental order-preserving
    implementation."""
    order = [ChannelId.PACE, ChannelId.HEART_RATE, ChannelId.POWER]
    assert tuple(order) != CANONICAL_CHANNELS

    outcomes = _outcomes(
        _insufficient(ChannelId.POWER, "no FTP on file"),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    selected = select(outcomes, order)
    assert selected is ChannelId.HEART_RATE

    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    assert [record.key for record in records] == [
        ChannelId.POWER.value,
        ChannelId.PACE.value,
    ]


def test_non_selected_values_canonical_order_holds_with_single_entry_order() -> None:
    """Design's own validation note, mirrored for the record-order function:
    record order is power, heart rate, pace whether the configured order was
    a full permutation or a single entry."""
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    selected = select(outcomes, [ChannelId.PACE])
    assert selected is ChannelId.PACE

    records = non_selected_values(
        outcomes, order=[ChannelId.PACE], selected=selected, discipline=Sport.RUN
    )
    assert [record.key for record in records] == [
        ChannelId.POWER.value,
        ChannelId.HEART_RATE.value,
    ]


def test_non_selected_values_records_each_channel_exactly_once() -> None:
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    selected = select(outcomes, order)
    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    assert len(records) == 2
    assert {record.key for record in records} == {
        ChannelId.HEART_RATE.value,
        ChannelId.PACE.value,
    }


# ---------------------------------------------------------------------------
# non_selected_values -- the three reasons (5.6, 6.4, 8.4, 8.5)
# ---------------------------------------------------------------------------


def test_non_selected_value_computed_and_beaten_carries_the_priority_reason() -> None:
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    selected = select(outcomes, order)
    assert selected is ChannelId.POWER

    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    hr_record = next(r for r in records if r.key == ChannelId.HEART_RATE.value)
    assert hr_record.value == HR_LOAD
    assert hr_record.reason == (
        "not selected: the configured order for Run prefers Power"
    )
    # Not the "absent from order" reason -- the two must not be confusable.
    assert "not in the configured order" not in hr_record.reason


def test_non_selected_value_computed_absent_from_order_carries_absence_reason() -> None:
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    # HEART_RATE computed but never named in the configured order.
    order = [ChannelId.POWER]
    selected = select(outcomes, order)
    assert selected is ChannelId.POWER

    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    hr_record = next(r for r in records if r.key == ChannelId.HEART_RATE.value)
    assert hr_record.value == HR_LOAD
    assert hr_record.reason == (
        "not selected: this channel is not in the configured order for Run"
    )
    # Not the "beaten by a higher-priority channel" reason.
    assert "prefers" not in hr_record.reason


def test_non_selected_value_insufficient_carries_verbatim_detail_and_no_number() -> (
    None
):
    detail = "no FTP on file for Run as of the activity date"
    outcomes = _outcomes(
        _insufficient(ChannelId.POWER, detail),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    order = [ChannelId.HEART_RATE, ChannelId.POWER, ChannelId.PACE]
    selected = select(outcomes, order)
    assert selected is ChannelId.HEART_RATE

    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    power_record = next(r for r in records if r.key == ChannelId.POWER.value)
    assert power_record.value is None
    assert power_record.reason == detail


def test_non_selected_value_never_carries_zero_in_place_of_absence() -> None:
    """0.0 is falsy, so ``not value`` would pass whether ``value`` is 0.0 or
    None. Assert identity against None, and separately that None is not
    conflated with a real zero float."""
    detail = "no LTHR on file"
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _insufficient(ChannelId.HEART_RATE, detail),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    selected = select(outcomes, order)
    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    hr_record = next(r for r in records if r.key == ChannelId.HEART_RATE.value)
    assert hr_record.value is None
    assert hr_record.value != 0.0


# ---------------------------------------------------------------------------
# non_selected_values -- labels, key tokens (8.3, Integration note)
# ---------------------------------------------------------------------------


def test_non_selected_value_key_is_the_channel_id_value_and_label_from_table() -> None:
    outcomes = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _insufficient(ChannelId.HEART_RATE, "no LTHR on file"),
        _insufficient(ChannelId.PACE, "no threshold pace on file"),
    )
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]
    selected = select(outcomes, order)
    records = non_selected_values(
        outcomes, order=order, selected=selected, discipline=Sport.RUN
    )
    hr_record = next(r for r in records if r.key == "heart_rate")
    assert hr_record.label == "Heart rate"


# ---------------------------------------------------------------------------
# non_selected_values -- reads no value for the selected channel's magnitude
# ---------------------------------------------------------------------------


def test_selected_channel_absent_and_non_selected_values_track_their_own_outcomes() -> (
    None
):
    """``ChannelSelection`` never produces a selected *value* -- ``select``
    returns only an id, and ``non_selected_values`` records everything
    *except* the selected channel. What this module can honestly prove is
    that (a) the selected channel never appears in the non-selected records,
    and (b) each non-selected record's value is exactly its own outcome's
    reported load, in both worlds, even when a sibling channel's load
    changes. "the selected value is unchanged" is discharged where a
    selected value first exists, at task 3.2/3.3."""
    order = [ChannelId.POWER, ChannelId.HEART_RATE, ChannelId.PACE]

    outcomes_a = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, HR_LOAD),
        _load(ChannelId.PACE, PACE_LOAD),
    )
    outcomes_b = _outcomes(
        _load(ChannelId.POWER, POWER_LOAD),
        _load(ChannelId.HEART_RATE, 7.0),  # altered non-selected value
        _load(ChannelId.PACE, 8.0),  # altered non-selected value
    )

    selected_a = select(outcomes_a, order)
    selected_b = select(outcomes_b, order)
    assert selected_a is selected_b is ChannelId.POWER

    records_a = non_selected_values(
        outcomes_a, order=order, selected=selected_a, discipline=Sport.RUN
    )
    records_b = non_selected_values(
        outcomes_b, order=order, selected=selected_b, discipline=Sport.RUN
    )

    # The selected channel (POWER) is absent from both record sets.
    assert ChannelId.POWER.value not in {r.key for r in records_a}
    assert ChannelId.POWER.value not in {r.key for r in records_b}

    hr_a = next(r for r in records_a if r.key == ChannelId.HEART_RATE.value)
    pace_a = next(r for r in records_a if r.key == ChannelId.PACE.value)
    hr_b = next(r for r in records_b if r.key == ChannelId.HEART_RATE.value)
    pace_b = next(r for r in records_b if r.key == ChannelId.PACE.value)

    assert hr_a.value == HR_LOAD
    assert pace_a.value == PACE_LOAD
    assert hr_b.value == 7.0
    assert pace_b.value == 8.0


# ---------------------------------------------------------------------------
# assert_never exhaustiveness (5.7)
# ---------------------------------------------------------------------------


def test_non_selected_values_source_calls_assert_never_in_its_fold() -> None:
    """Pins that the fold is a real exhaustiveness check, not an
    ``else: pass`` or a bare ``# type: ignore`` fallback that would satisfy
    mypy without ever raising at runtime on an unrecognized variant. Scans
    the function's source with its docstring stripped, and requires the
    call form ``assert_never(outcome)`` rather than the bare token -- the
    bare token also appears in the docstring's prose and would pass even
    with the import removed and the ``case _`` arm replaced by a
    fabricating branch."""
    source = inspect.getsource(non_selected_values)
    docstring = non_selected_values.__doc__ or ""
    code_only = source.replace(docstring, "")
    assert "assert_never(outcome)" in code_only


def test_non_selected_values_raises_on_an_outcome_that_is_neither_variant() -> None:
    """Behavioral corroboration of the exhaustiveness fold: a value that is
    neither ChannelLoad nor ChannelInsufficient falls through every case
    arm and reaches assert_never, which raises rather than silently
    returning a fabricated record."""

    class _RogueOutcome:
        channel = ChannelId.PACE

    outcomes: dict[ChannelId, object] = {
        ChannelId.POWER: _load(ChannelId.POWER, POWER_LOAD),
        ChannelId.HEART_RATE: _insufficient(ChannelId.HEART_RATE, "no LTHR on file"),
        ChannelId.PACE: _RogueOutcome(),
    }
    with pytest.raises(AssertionError):
        non_selected_values(
            outcomes,  # type: ignore[arg-type]
            order=[ChannelId.POWER],
            selected=ChannelId.POWER,
            discipline=Sport.RUN,
        )


# ---------------------------------------------------------------------------
# Purity (5.5 -- through the interface: no I/O, no extra params to smuggle
# state through; the two-function service surface is exhaustive)
# ---------------------------------------------------------------------------


def test_module_exposes_exactly_the_documented_public_names() -> None:
    exported = {name for name in dir(selection) if not name.startswith("_")}
    expected = {
        "CANONICAL_CHANNELS",
        "CHANNEL_LABELS",
        "select",
        "non_selected_values",
        "ChannelId",
        "ChannelInsufficient",
        "ChannelLoad",
        "ChannelOutcome",
        "NonSelectedValue",
        "Sport",
        "Mapping",
        "Sequence",
        "Final",
        "assert_never",
        "annotations",
    }
    assert exported == expected
