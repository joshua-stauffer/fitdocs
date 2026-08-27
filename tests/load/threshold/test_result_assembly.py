"""Contract tests for :mod:`fitdocs.load.threshold.calculator`'s
``ResultAssembly`` responsibility (task 3.2, design: ``ResultAssembly``, Req
3.7, 6.6, 8.1, 8.2, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 10.3, 10.4).

``build_result`` maps a channel selection onto the contract's
:class:`~fitdocs.load.types.LoadResult` without inventing anything: the
selected channel's ``load`` becomes ``value`` verbatim, the selected
channel's identity becomes ``basis``, ``non_selected`` is delegated to
:func:`~fitdocs.load.threshold.selection.non_selected_values`, ``flags`` is
always the empty tuple, ``inputs_used`` opens with five fixed rows followed
by the selected channel's own reported inputs verbatim, and ``notes`` opens
with one entry per borrowed anchor followed by the selected channel's own
notes, each prefixed with the channel's display label.

These tests are built to defeat, not merely exercise:

- every channel carries a *distinct, fractional* load (Req 8.1, 8.10) -- a
  whole-number fixture lets ``round()`` survive undetected, and equal loads
  across channels would hide a sourcing defect behind an accidental tie;
- the selected channel's ``intensity`` is asserted against a value that is
  neither ``0.0`` nor ``1.0`` (Req 8.11) -- every rescaling candidate this
  feature explicitly rejected (``intensity ** 2``, ``sqrt(intensity)``)
  agrees with the identity at exactly ``1.0``, so a fixture pinned there
  would prove nothing;
- the five fixed ``inputs_used`` rows are asserted by exact tuple equality,
  including order, never by membership or a set/dict comparison, so a
  reordering or a swapped pair reds (Req 8.9);
- the coverage figure is asserted for the full string including
  ``"of recorded time"``, never by substring containment of ``"distance"``
  alone, since that word can appear for unrelated reasons (Req 8.12);
- ``flags`` is pinned both by value (``== ()``) and, separately, by
  ``inspect.signature`` showing ``build_result`` accepts no ``flags``
  parameter at all (Req 8.8);
- a ``Borrowing``'s ``activity_discipline`` and ``anchor_discipline`` are
  distinct ``Sport`` values in every borrowing fixture, so a swap between
  them reds (Req 3.4).
"""

from __future__ import annotations

import inspect
from datetime import date

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels.types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
    InsufficiencyReason,
    StreamCoverage,
)
from fitdocs.load.threshold.anchors import Borrowing, ResolvedAnchors
from fitdocs.load.threshold.calculator import (
    build_result,
    format_coverage,
    format_duration,
    format_ratio,
)
from fitdocs.load.threshold.selection import non_selected_values
from fitdocs.load.types import LoadResult
from fitdocs.model import Sport

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _bm(
    kind: BenchmarkKind, discipline: Sport | None, value: float, day: date
) -> Benchmark:
    return Benchmark(kind=kind, discipline=discipline, value=value, measured_on=day)


_ANCHOR_KIND = {
    ChannelId.POWER: BenchmarkKind.FTP_WATTS,
    ChannelId.HEART_RATE: BenchmarkKind.LTHR_BPM,
    ChannelId.PACE: BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
}


def _load(
    channel: ChannelId,
    load: float,
    *,
    intensity: float = 0.5,
    coverage: StreamCoverage | None = None,
    scored_duration_s: float = 3600.0,
    inputs_used: tuple[tuple[str, str], ...] = (),
    notes: tuple[str, ...] = (),
    anchor_discipline: Sport = Sport.RUN,
) -> ChannelLoad:
    """A computed outcome for ``channel`` carrying a distinct, fractional
    ``load`` so no fixture below can pass by an accidental tie or a
    round-number coincidence (Req 8.1, 8.10)."""
    return ChannelLoad(
        channel=channel,
        load=load,
        intensity=intensity,
        anchor=_bm(_ANCHOR_KIND[channel], anchor_discipline, 250.0, date(2026, 1, 1)),
        scored_duration_s=scored_duration_s,
        coverage=coverage
        or StreamCoverage(stream=channel.value, covered_s=3600.0, total_s=3600.0),
        inputs_used=inputs_used,
        notes=notes,
    )


def _insufficient(
    channel: ChannelId, detail: str = "no benchmark on file"
) -> ChannelInsufficient:
    return ChannelInsufficient(
        channel=channel, reason=InsufficiencyReason.NO_BENCHMARK, detail=detail
    )


def _anchors(borrowed: tuple[Borrowing, ...] = ()) -> ResolvedAnchors:
    return ResolvedAnchors(
        ftp=None,
        lthr=None,
        threshold_pace=None,
        max_hr=None,
        resting_hr=None,
        borrowed=borrowed,
        not_on_file=(),
        not_applicable=(),
    )


# The headline scenario: a Run activity, three channels each computing a
# distinct, fractional load, pace selected by the configured order. No
# borrowing -- Run never borrows an anchor.
_PACE_LOAD = _load(
    ChannelId.PACE,
    241.7752,
    intensity=0.912,
    coverage=StreamCoverage(stream="distance", covered_s=3592.9, total_s=3600.0),
    scored_duration_s=3800.0,
    inputs_used=(
        ("Threshold pace", "300.0 s/km"),
        ("Anchor discipline", "Run"),
        ("Measured on", "2026-01-01"),
    ),
    notes=("gap-adjusted for elevation",),
)
_POWER_LOAD = _load(ChannelId.POWER, 88.123, intensity=0.333)
_HR_LOAD = _load(ChannelId.HEART_RATE, 55.987, intensity=0.667)

_ORDER: tuple[ChannelId, ...] = (ChannelId.PACE, ChannelId.POWER, ChannelId.HEART_RATE)

_OUTCOMES: dict[ChannelId, ChannelOutcome] = {
    ChannelId.PACE: _PACE_LOAD,
    ChannelId.POWER: _POWER_LOAD,
    ChannelId.HEART_RATE: _HR_LOAD,
}


def _happy_result() -> LoadResult:
    return build_result(
        selected=_PACE_LOAD,
        outcomes=_OUTCOMES,
        order=_ORDER,
        anchors=_anchors(),
        discipline=Sport.RUN,
    )


# ---------------------------------------------------------------------------
# value / basis (Req 8.1, 8.2, 8.10, 10.3, 10.4)
# ---------------------------------------------------------------------------


def test_value_is_the_selected_channels_load_verbatim() -> None:
    """The selected channel's exact, unrounded, unadjusted load is the one
    value that counts (Req 8.1, 8.10). ``241.7752`` deliberately carries
    four decimal places -- design says "unrounded and unadjusted", which a
    three-decimal fixture pins only up to three places. Mutation probes
    (documented, run by hand):

    - ``value=round(selected.load, 1)`` reds this exact-equality assertion,
      because ``241.7752`` is not a round number: ``round(241.7752, 1) ==
      241.8 != 241.7752``.
    - ``value=round(selected.load, 3)`` also reds this assertion:
      ``round(241.7752, 3) == 241.775 != 241.7752``.
    - ``value=outcomes[ChannelId.POWER].load`` (a non-selected channel) reds
      this assertion, because ``88.123 != 241.7752`` -- every channel here
      carries a distinct fractional load precisely so this substitution is
      observable (Req 8.10).
    """
    result = _happy_result()
    assert result.value == 241.7752


def test_basis_is_the_selected_channels_identity() -> None:
    result = _happy_result()
    assert result.basis == "pace"


def test_basis_is_non_empty() -> None:
    """Postcondition: ``basis`` is never empty (design.md Postconditions)."""
    result = _happy_result()
    assert result.basis != ""


def test_value_and_basis_agree_for_a_heart_rate_selection_too() -> None:
    """The mapping is channel-agnostic: selecting heart rate carries the
    same ``value``/``basis`` relationship pace did above."""
    result = build_result(
        selected=_HR_LOAD,
        outcomes=_OUTCOMES,
        order=(ChannelId.HEART_RATE, ChannelId.PACE, ChannelId.POWER),
        anchors=_anchors(),
        discipline=Sport.RUN,
    )
    assert result.value == 55.987
    assert result.basis == "heart_rate"


def test_value_and_basis_come_from_selected_even_when_not_first_in_order() -> None:
    """Req 8.1, 8.2, 8.10, 10.3: ``value`` and ``basis`` are read from
    ``selected`` -- never from ``order[0]``. Every other fixture in this
    file happens to select ``order[0]``, which leaves a same-shaped
    ``order[0]``-sourcing defect unobservable; this is the one fixture where
    the selected channel is deliberately *not* first in the configured
    order, exactly the priority-walk scenario Req 6.3 exists to produce
    (pace insufficient, power selected next).

    Mutation probes (documented, run by hand):

    - ``channel_id = order[0]`` in ``build_result`` reds both ``basis``
      assertions below: it would read ``"pace"``, not ``"power"``.
    - ``value = outcomes[order[0]].load`` reds this test: pace
      is insufficient, so ``outcomes[order[0]]`` is a ``ChannelInsufficient``
      with no ``.load`` attribute, and the call raises ``AttributeError``
      before the assertion is even reached.
    """
    result = build_result(
        selected=_POWER_LOAD,
        outcomes={
            ChannelId.PACE: _insufficient(ChannelId.PACE),
            ChannelId.POWER: _POWER_LOAD,
            ChannelId.HEART_RATE: _HR_LOAD,
        },
        order=(ChannelId.PACE, ChannelId.POWER, ChannelId.HEART_RATE),
        anchors=_anchors(),
        discipline=Sport.RUN,
    )
    assert result.value == 88.123
    assert result.basis == "power"
    assert result.inputs_used[0] == ("Channel", "Power")
    non_selected_by_key = {record.key: record for record in result.non_selected}
    assert non_selected_by_key["pace"].value is None


# ---------------------------------------------------------------------------
# calculator_id / display_name
# ---------------------------------------------------------------------------


def test_calculator_id_and_display_name_are_fixed() -> None:
    result = _happy_result()
    assert result.calculator_id == "threshold"
    assert result.display_name == "Threshold Load"


# ---------------------------------------------------------------------------
# non_selected (Req 8.3, 8.4, 8.5, 8.9 -- delegated to selection.py, whose
# own suite pins the per-reason behavior; here we pin only that build_result
# delegates rather than reimplementing it)
# ---------------------------------------------------------------------------


def test_non_selected_matches_the_selection_steps_own_function() -> None:
    """``non_selected`` is exactly what ``non_selected_values`` returns for
    the same inputs -- build_result must not reimplement or filter it
    (Req 8.3, 8.9). Per-reason correctness (a channel beaten by priority vs.
    a channel outside the configured order vs. an insufficient channel) is
    PRESERVED-ONLY here: it is pinned by ``tests/load/threshold/
    test_selection.py``'s own suite, not re-proven in this file."""
    result = _happy_result()
    expected = non_selected_values(
        _OUTCOMES, order=_ORDER, selected=ChannelId.PACE, discipline=Sport.RUN
    )
    assert result.non_selected == expected
    assert len(result.non_selected) == 2
    assert {record.key for record in result.non_selected} == {"power", "heart_rate"}


def test_non_selected_forwards_the_actual_configured_order_not_a_fixed_one() -> None:
    """Req 6.4, 8.4: the exact ``order`` argument -- not some hardcoded
    stand-in -- is what ``non_selected_values`` uses to decide whether an
    absent-from-``order`` computed channel gets the "not in the configured
    order" reason. Heart rate here computes a load but is left out of
    ``order`` entirely.

    Req 6.6: the same ``order`` is also what the "Selection order" input row
    renders, and this is the only fixture whose ``order`` is not the
    three-channel default -- so the row assertion below is what stops a
    *same-shaped constant* (most plausibly ``DEFAULT_PRIORITY.for_discipline``
    instead of the caller's configured order) from silently showing every
    athlete the defaults.

    Mutation probes, both run: replacing the ``order=order`` forwarded
    argument in ``build_result`` with a hardcoded ``(POWER, HEART_RATE,
    PACE)`` reds the reason assertion -- heart rate would then read as
    *beaten by priority* ("prefers Pace") instead of *absent from the
    configured order*, because the hardcoded tuple contains it. Hardcoding
    any three-channel tuple in the ``"Selection order"`` join reds the row
    assertion."""
    result = build_result(
        selected=_PACE_LOAD,
        outcomes=_OUTCOMES,
        order=(ChannelId.PACE, ChannelId.POWER),
        anchors=_anchors(),
        discipline=Sport.RUN,
    )
    non_selected_by_key = {record.key: record for record in result.non_selected}
    assert "not in the configured order" in non_selected_by_key["heart_rate"].reason
    assert result.inputs_used[1] == ("Selection order", "pace > power")


# ---------------------------------------------------------------------------
# flags (Req 8.8)
# ---------------------------------------------------------------------------


def test_flags_is_the_empty_tuple() -> None:
    result = _happy_result()
    assert result.flags == ()


def test_build_result_accepts_no_flags_parameter() -> None:
    """Structural pin, not vacuous introspection: the signature's parameter
    *names* are checked, not merely ``hasattr`` on some unrelated object
    (Req 8.8; see the roadmap decision-7 extension-point note in
    calculator.py). Mutation probe: adding ``flags: tuple[QualityFlag,
    ...] = ()`` to ``build_result``'s signature reds this assertion."""
    signature = inspect.signature(build_result)
    assert "flags" not in signature.parameters
    assert set(signature.parameters) == {
        "selected",
        "outcomes",
        "order",
        "anchors",
        "discipline",
    }


# ---------------------------------------------------------------------------
# inputs_used (Req 3.7, 6.6, 8.6, 8.9, 8.11, 8.12)
# ---------------------------------------------------------------------------


def test_inputs_used_opens_with_five_fixed_rows_in_order() -> None:
    """The five fixed rows, exact values, exact order (Req 6.6, 8.6, 8.9).

    Mutation probes:

    - swapping any two of the five rows reds this assertion, because the
      comparison is against the full ordered tuple, not a set of pairs;
    - reordering only the ``order`` argument used to build the
      ``"Selection order"`` string (e.g. sorting it) reds the second row.
    """
    result = _happy_result()
    assert result.inputs_used[0] == ("Channel", "Pace")
    assert result.inputs_used[1] == ("Selection order", "pace > power > heart_rate")
    assert result.inputs_used[2] == ("Intensity", "0.912")
    assert result.inputs_used[3] == ("Scored duration", "1:03:20")
    assert result.inputs_used[4] == ("Coverage", "distance 99.8% of recorded time")


def test_inputs_used_appends_the_selected_channels_own_inputs_verbatim() -> None:
    """Req 3.7, 8.9: the selected channel's own inputs are appended
    verbatim, in the channel's own order -- not reversed, not resorted.
    ``_PACE_LOAD`` deliberately carries three distinct rows (Req 3.7's
    anchor value, discipline and measurement date) so a reordering is
    observable.

    Mutation probe: ``*reversed(selected.inputs_used)`` in ``build_result``
    reds this assertion -- the three rows would appear in the opposite
    order."""
    result = _happy_result()
    assert result.inputs_used[5:] == (
        ("Threshold pace", "300.0 s/km"),
        ("Anchor discipline", "Run"),
        ("Measured on", "2026-01-01"),
    )


def test_inputs_used_row_order_is_pinned_not_just_membership() -> None:
    """A set/dict comparison of the five fixed rows would not notice a
    reordering; this asserts the full tuple, in order, in one call (Req
    8.9). Mutation probe: swapping ``inputs_used[0]`` and ``inputs_used[1]``
    in ``build_result`` reds this assertion but would not red a
    ``set(...)``-based one."""
    result = _happy_result()
    assert result.inputs_used[:5] == (
        ("Channel", "Pace"),
        ("Selection order", "pace > power > heart_rate"),
        ("Intensity", "0.912"),
        ("Scored duration", "1:03:20"),
        ("Coverage", "distance 99.8% of recorded time"),
    )


def test_intensity_is_emitted_verbatim_never_rescaled() -> None:
    """Req 8.11: the channel's reported intensity is emitted as-is under the
    single ``"Intensity"`` label. ``0.912`` is deliberately neither ``0.0``
    nor ``1.0`` -- every rescaling this feature explicitly rejected
    (``intensity ** 2 == 0.831744``, ``sqrt(intensity) == 0.95499...``)
    agrees with the identity only at those two points, so a fixture pinned
    there would prove nothing (Req 8.11).

    Mutation probes (documented, run by hand):

    - ``format_ratio(selected.intensity ** 2)`` reds this assertion:
      ``0.912 ** 2 == 0.831744``, formatted ``"0.832"`` != ``"0.912"``.
    - ``format_ratio(selected.intensity ** 0.5)`` reds this assertion:
      ``0.912 ** 0.5 == 0.9549869...``, formatted ``"0.955"`` != ``"0.912"``.
    """
    result = _happy_result()
    assert result.inputs_used[2] == ("Intensity", "0.912")
    assert 0.912 not in (0.0, 1.0)
    assert format_ratio(0.912**2) != format_ratio(0.912)
    assert format_ratio(0.912**0.5) != format_ratio(0.912)


def test_coverage_names_its_measurement_basis() -> None:
    """Req 8.12: the coverage figure names the stream and the domain it was
    measured over, so it is never mistaken for the workout document's own
    sample-count coverage table. Asserted by full-string equality, not
    substring containment of ``"distance"`` alone -- that word can appear on
    the result for unrelated reasons (e.g. a note), so a substring check
    would not discriminate a missing ``" of recorded time"`` suffix."""
    result = _happy_result()
    coverage_row = result.inputs_used[4]
    assert coverage_row == ("Coverage", "distance 99.8% of recorded time")
    assert coverage_row[1] != "distance 99.8%"
    assert coverage_row[1].endswith(" of recorded time")


# ---------------------------------------------------------------------------
# notes (Req 3.4, 8.7)
# ---------------------------------------------------------------------------


def test_a_borrowed_anchor_produces_a_note_naming_both_disciplines() -> None:
    """Postcondition (design.md): a borrowed anchor produces a note of the
    documented form, naming both disciplines. ``activity_discipline`` and
    ``anchor_discipline`` are distinct ``Sport`` values here (Hike, Run) so a
    swap between them is observable (Req 3.4).

    Mutation probe: swapping ``borrowing.activity_discipline`` and
    ``borrowing.anchor_discipline`` inside the note-formatting helper reds
    this exact-string assertion (it would read "...anchored on the Hike...;
    no Run threshold is on file." instead)."""
    hr_hike = _load(
        ChannelId.HEART_RATE, 61.5, intensity=0.4, anchor_discipline=Sport.RUN
    )
    borrowing = Borrowing(
        kind=BenchmarkKind.LTHR_BPM,
        activity_discipline=Sport.HIKE,
        anchor_discipline=Sport.RUN,
    )
    result = build_result(
        selected=hr_hike,
        outcomes={
            ChannelId.HEART_RATE: hr_hike,
            ChannelId.POWER: _insufficient(ChannelId.POWER),
            ChannelId.PACE: _insufficient(ChannelId.PACE),
        },
        order=(ChannelId.HEART_RATE,),
        anchors=_anchors(borrowed=(borrowing,)),
        discipline=Sport.HIKE,
    )
    assert result.notes[0] == (
        "Heart-rate channel anchored on the Run lactate threshold heart "
        "rate; no Hike threshold is on file."
    )


def test_notes_order_borrowings_first_then_channel_notes_prefixed() -> None:
    """Req 8.7: notes open with one entry per borrowed anchor, then the
    selected channel's own notes, each prefixed with the channel's display
    label. Both the ordering and the prefixing are asserted together so a
    mutation that reverses the two groups, or one that drops the prefix, is
    caught by the same test.

    Mutation probes:

    - reversing the two ``(*borrowing_notes, *channel_notes)`` groups in
      ``build_result`` reds this assertion (the channel note would appear
      first);
    - emitting the channel's own notes unprefixed reds the second
      assertion.
    """
    hr_hike = _load(
        ChannelId.HEART_RATE,
        61.5,
        intensity=0.4,
        anchor_discipline=Sport.RUN,
        notes=("gap-adjusted using a borrowed anchor",),
    )
    borrowing = Borrowing(
        kind=BenchmarkKind.LTHR_BPM,
        activity_discipline=Sport.HIKE,
        anchor_discipline=Sport.RUN,
    )
    result = build_result(
        selected=hr_hike,
        outcomes={
            ChannelId.HEART_RATE: hr_hike,
            ChannelId.POWER: _insufficient(ChannelId.POWER),
            ChannelId.PACE: _insufficient(ChannelId.PACE),
        },
        order=(ChannelId.HEART_RATE,),
        anchors=_anchors(borrowed=(borrowing,)),
        discipline=Sport.HIKE,
    )
    assert len(result.notes) == 2
    assert result.notes[0].startswith("Heart-rate channel anchored")
    assert result.notes[1] == "Heart rate: gap-adjusted using a borrowed anchor"


def test_no_borrowing_no_channel_notes_yields_empty_notes() -> None:
    """The happy-path Run scenario borrows nothing and the pace channel
    carries a note, so ``notes`` here is exactly the one prefixed channel
    note -- no borrowing entry is fabricated when ``anchors.borrowed`` is
    empty."""
    result = _happy_result()
    assert result.notes == ("Pace: gap-adjusted for elevation",)


# ---------------------------------------------------------------------------
# Invariant: nothing is derived from a non-selected value (Req 8.10)
# ---------------------------------------------------------------------------


def test_no_number_appears_for_a_channel_that_produced_none() -> None:
    """Req 8.5, 10.4: an insufficient channel contributes no number
    anywhere in the result. Power and pace are insufficient in this
    scenario; heart rate is the selected, computed channel. The two
    insufficient channels' absence is asserted on the delegated
    ``non_selected`` records, which is where such a channel's information
    (or lack of it) can appear at all in this result."""
    hr_only = _load(ChannelId.HEART_RATE, 61.5, intensity=0.4)
    result = build_result(
        selected=hr_only,
        outcomes={
            ChannelId.HEART_RATE: hr_only,
            ChannelId.POWER: _insufficient(ChannelId.POWER, "no benchmark on file"),
            ChannelId.PACE: _insufficient(ChannelId.PACE, "no benchmark on file"),
        },
        order=(ChannelId.HEART_RATE,),
        anchors=_anchors(),
        discipline=Sport.RUN,
    )
    for record in result.non_selected:
        if record.key in {"power", "pace"}:
            assert record.value is None


def test_every_non_selected_reason_is_non_empty() -> None:
    """Postcondition (design.md): every ``NonSelectedValue.reason`` is
    non-empty. PRESERVED-ONLY in substance (``non_selected_values``'s own
    suite pins reason content); asserted here on the composed result so a
    future change to how build_result calls it cannot silently drop it."""
    result = _happy_result()
    for record in result.non_selected:
        assert record.reason != ""


# ---------------------------------------------------------------------------
# Determinism (Req 8.9)
# ---------------------------------------------------------------------------


def test_building_the_same_result_twice_produces_equal_records() -> None:
    first = _happy_result()
    second = _happy_result()
    assert first == second


def test_result_is_independent_of_the_outcomes_mappings_insertion_order() -> None:
    """Req 8.9: two ``outcomes`` mappings that are equal but built with a
    different insertion order produce equal results -- ``non_selected`` is
    ordered by :data:`~fitdocs.load.threshold.selection.CANONICAL_CHANNELS`,
    not by however the caller happened to populate the mapping. A plain
    dataclass-equality check against a second call with the *same* fixture
    (as above) cannot fail on any mutation this feature makes, since nothing
    in ``build_result`` reads a clock, an RNG, or set/dict iteration order
    directly; reordering the mapping's construction is what actually
    exercises that guarantee."""
    forward_order = {
        ChannelId.PACE: _PACE_LOAD,
        ChannelId.POWER: _POWER_LOAD,
        ChannelId.HEART_RATE: _HR_LOAD,
    }
    reverse_order = {
        ChannelId.HEART_RATE: _HR_LOAD,
        ChannelId.POWER: _POWER_LOAD,
        ChannelId.PACE: _PACE_LOAD,
    }
    assert forward_order == reverse_order
    result_forward = build_result(
        selected=_PACE_LOAD,
        outcomes=forward_order,
        order=_ORDER,
        anchors=_anchors(),
        discipline=Sport.RUN,
    )
    result_reverse = build_result(
        selected=_PACE_LOAD,
        outcomes=reverse_order,
        order=_ORDER,
        anchors=_anchors(),
        discipline=Sport.RUN,
    )
    assert result_forward == result_reverse


# ---------------------------------------------------------------------------
# Formatters (Implementation Notes: "each a module-level helper with its own
# test, because 'deterministic' is only testable if the formatting is
# fixed")
# ---------------------------------------------------------------------------


def test_format_ratio_renders_three_decimals() -> None:
    """Chosen so the 2- and 3-decimal renderings differ observably (Req
    8.9). Mutation probe: changing the format spec to ``.2f`` reds this
    assertion (``"0.91"`` != ``"0.912"``)."""
    assert format_ratio(0.912) == "0.912"
    assert format_ratio(0.912) != f"{0.912:.2f}"


def test_format_coverage_renders_one_decimal_with_basis() -> None:
    """Chosen so the 1- and 2-decimal renderings differ observably. Mutation
    probe (documented, run by hand): changing the format spec to ``.2f``
    reds the exact-equality assertion below -- it renders ``"99.80"``, not
    ``"99.8"``, since ``0.998027... * 100 == 99.802777...``."""
    coverage = StreamCoverage(stream="distance", covered_s=3592.9, total_s=3600.0)
    assert format_coverage(coverage) == "distance 99.8% of recorded time"
    assert format_coverage(coverage) != "distance 99.80% of recorded time"


def test_format_duration_renders_h_mm_ss_crossing_an_hour_and_ten_minutes() -> None:
    """3800 s = 1h 3m 20s, chosen so ``"1:03:20"`` cannot be confused with
    ``"1:3:20"`` (unpadded minutes) or ``"63:20"`` (no hour component) --
    both of which a less careful formatter could plausibly produce."""
    assert format_duration(3800.0) == "1:03:20"
    assert format_duration(3800.0) != "1:3:20"
    assert format_duration(3800.0) != "63:20"


def test_format_duration_pads_single_digit_minutes_and_seconds() -> None:
    assert format_duration(3661.0) == "1:01:01"


def test_format_duration_below_one_hour_keeps_the_zero_hour_component() -> None:
    """Design says ``H:MM:SS`` -- the hour component is always present, even
    when it is zero. A sub-hour scored duration is the common case for this
    feature, yet neither of the two
    fixtures above exercises it.

    ``3599.7`` also pins truncation, not rounding, of the fractional second:
    ``int(3599.7) == 3599`` renders ``"0:59:59"``; a formatter that rounded
    instead would render ``"1:00:00"``.

    Mutation probe: ``f"{minutes:02d}:{secs:02d}"`` when ``hours == 0``
    (dropping the hour component below one hour) reds both assertions
    below -- they would read ``"33:20"`` and ``"59:59"``."""
    assert format_duration(2000.0) == "0:33:20"
    assert format_duration(3599.7) == "0:59:59"
