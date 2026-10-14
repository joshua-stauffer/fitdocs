"""Synthetic complete findings over dated benchmark collections."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from fitdocs.benchmarks import (
    Benchmark,
    BenchmarkKind,
    BenchmarkSet,
    BenchmarkSource,
    BenchmarkSourceKind,
    parse_benchmarks,
)
from fitdocs.hr_benchmarks.inspect import (
    back_reach_cover,
    current_takeovers,
    inconsistencies,
    takeovers,
)
from fitdocs.hr_benchmarks.sources import MAX_RULE, RESTING_RULE
from fitdocs.hr_benchmarks.timeline import TimelineResult, derive_timeline
from fitdocs.hr_benchmarks.types import (
    BackReach,
    Evidence,
    Inconsistency,
    Takeover,
    Violation,
)
from fitdocs.model import Sport


def _d(day: int) -> date:
    return date(2024, 1, day)


def _b(
    kind: BenchmarkKind,
    day: int,
    value: int,
    *,
    derived: bool = False,
    applies: int | None = None,
    discipline: Sport | None = None,
    measured: bool = False,
) -> Benchmark:
    source = (
        BenchmarkSource(
            BenchmarkSourceKind.DERIVED, "synthetic", "page", "inputs", "choice"
        )
        if derived
        else BenchmarkSource(BenchmarkSourceKind.MEASURED)
        if measured
        else None
    )
    return Benchmark(
        kind,
        discipline,
        value,
        _d(day),
        applies_from=_d(applies) if applies is not None else None,
        source=source,
    )


def _max(
    day: int, value: int, *, derived: bool = False, applies: int | None = None
) -> Benchmark:
    return _b(BenchmarkKind.MAX_HR_BPM, day, value, derived=derived, applies=applies)


def _rest(
    day: int, value: int, *, derived: bool = False, applies: int | None = None
) -> Benchmark:
    return _b(
        BenchmarkKind.RESTING_HR_BPM, day, value, derived=derived, applies=applies
    )


def _lt(
    day: int,
    value: int,
    discipline: Sport,
    *,
    applies: int | None = None,
    derived: bool = False,
) -> Benchmark:
    return _b(
        BenchmarkKind.LTHR_BPM,
        day,
        value,
        discipline=discipline,
        applies=applies,
        derived=derived,
    )


def test_takeovers_full_pairs_sorted_by_kind_then_date() -> None:
    mx_old = _max(1, 203)
    mx_d1 = _max(2, 195, derived=True)
    mx_d2 = _max(4, 179, derived=True)
    mx_hand = _max(3, 188)
    rs_old = _b(BenchmarkKind.RESTING_HR_BPM, 1, 71, measured=True)
    rs_d = _rest(3, 63, derived=True)
    rs_later = _rest(4, 55, derived=True)
    pace_hand = _b(BenchmarkKind.THRESHOLD_PACE_S_PER_KM, 1, 340, discipline=Sport.RUN)
    pace_d = _b(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        2,
        310,
        discipline=Sport.RUN,
        derived=True,
    )
    lt_hand = _lt(1, 162, Sport.RIDE)
    lt_d = _lt(2, 153, Sport.RIDE, derived=True)
    expected = (
        Takeover(BenchmarkKind.MAX_HR_BPM, _max(2, 195, derived=True), _max(1, 203)),
        Takeover(BenchmarkKind.MAX_HR_BPM, _max(4, 179, derived=True), _max(3, 188)),
        Takeover(
            BenchmarkKind.RESTING_HR_BPM,
            _rest(3, 63, derived=True),
            _b(BenchmarkKind.RESTING_HR_BPM, 1, 71, measured=True),
        ),
    )
    assert (
        takeovers(
            BenchmarkSet(
                (
                    rs_later,
                    rs_d,
                    mx_d2,
                    pace_d,
                    lt_d,
                    mx_hand,
                    mx_d1,
                    rs_old,
                    mx_old,
                    lt_hand,
                    pace_hand,
                )
            )
        )
        == expected
    )


def test_takeover_selects_on_derived_day_when_backreach_starts_that_day() -> None:
    expected = (
        Takeover(
            BenchmarkKind.MAX_HR_BPM,
            _max(5, 193, derived=True),
            _max(20, 184, applies=5),
        ),
    )
    assert (
        takeovers(BenchmarkSet((_max(20, 184, applies=5), _max(5, 193, derived=True))))
        == expected
    )


def test_derived_without_any_hand_is_not_takeover() -> None:
    assert (
        takeovers(
            BenchmarkSet((_max(3, 191, derived=True), _rest(2, 59, derived=True)))
        )
        == ()
    )


def test_generated_walk_has_two_literal_pairs_and_structural_equality() -> None:
    hands = (_max(20, 188, applies=1), _max(25, 183))
    evidence = (
        Evidence(_d(2), 196, "device", "session-2", None, "window-2", "peak-2"),
        Evidence(_d(26), 178, "device", "session-26", None, "window-26", "peak-26"),
    )
    expected = (
        Takeover(
            BenchmarkKind.MAX_HR_BPM,
            Benchmark(
                BenchmarkKind.MAX_HR_BPM,
                None,
                196,
                _d(2),
                "Takes over from your hand-recorded 188 bpm of 2024-01-20 "
                "(it applied here through its applies-from date): "
                "the evidence differed by more than 2 bpm.",
                source=BenchmarkSource(
                    BenchmarkSourceKind.DERIVED,
                    "max_hr_sustained_peak",
                    "session-2",
                    "window-2",
                    "max_hr_timeline_choice",
                ),
            ),
            _max(20, 188, applies=1),
        ),
        Takeover(
            BenchmarkKind.MAX_HR_BPM,
            Benchmark(
                BenchmarkKind.MAX_HR_BPM,
                None,
                178,
                _d(26),
                "Takes over from your hand-recorded 183 bpm of 2024-01-25: "
                "the evidence differed by more than 2 bpm.",
                source=BenchmarkSource(
                    BenchmarkSourceKind.DERIVED,
                    "max_hr_sustained_peak",
                    "session-26",
                    "window-26",
                    "max_hr_timeline_choice",
                ),
            ),
            _max(25, 183),
        ),
    )
    walk = derive_timeline(MAX_RULE, evidence, hands)
    structural = takeovers(BenchmarkSet((*reversed(walk.entries), *reversed(hands))))
    assert structural == walk.takeovers == expected


@pytest.mark.parametrize("later", ["none", "hand", "derived", "backreach"])
def test_current_takeovers_use_latest_measurement_of_each_kind(later: str) -> None:
    mx_hand = _max(1, 201)
    mx_d = _max(5, 194, derived=True)
    rs_hand = _rest(2, 71)
    rs_d = _rest(4, 64, derived=True)
    additions = {
        "none": (),
        "hand": (_max(8, 182),),
        "derived": (_max(8, 180, derived=True),),
        "backreach": (_max(20, 185, applies=5),),
    }
    expected = (
        (Takeover(BenchmarkKind.MAX_HR_BPM, _max(5, 194, derived=True), _max(1, 201)),)
        if later == "none"
        else ()
    ) + (
        Takeover(
            BenchmarkKind.RESTING_HR_BPM, _rest(4, 64, derived=True), _rest(2, 71)
        ),
    )
    assert (
        current_takeovers(
            BenchmarkSet((rs_d, mx_d, rs_hand, mx_hand, *additions[later]))
        )
        == expected
    )


def test_future_backreach_takeover_is_not_current() -> None:
    assert (
        current_takeovers(
            BenchmarkSet((_max(5, 194, derived=True), _max(20, 185, applies=5)))
        )
        == ()
    )


@pytest.mark.parametrize(
    "mode,end", [("full", 20), ("shrink", 7), ("before", 2), ("older", 2)]
)
def test_backreach_full_shrunk_and_empty(mode: str, end: int) -> None:
    hand = _max(20, 183, applies=2)
    additions = {
        "full": (),
        "shrink": (_max(7, 197, derived=True),),
        "before": (_max(1, 195, derived=True),),
        "older": (_max(1, 187),),
    }
    expected = (
        BackReach(BenchmarkKind.MAX_HR_BPM, _max(20, 183, applies=2), _d(2), _d(end)),
    )
    assert back_reach_cover(BenchmarkSet((*additions[mode], hand))) == expected


def test_backreach_two_future_hands_earliest_measurement_and_kind_isolation() -> None:
    expected = (
        BackReach(BenchmarkKind.MAX_HR_BPM, _max(20, 191, applies=6), _d(6), _d(20)),
        BackReach(BenchmarkKind.MAX_HR_BPM, _max(25, 178, applies=2), _d(2), _d(6)),
        BackReach(BenchmarkKind.RESTING_HR_BPM, _rest(28, 58, applies=1), _d(1), _d(9)),
    )
    entries = (
        _rest(28, 58, applies=1),
        _max(25, 178, applies=2),
        _max(20, 191, applies=6),
        _rest(9, 65, derived=True),
        _max(27, 181),
        _max(30, 180, derived=True),
    )
    assert back_reach_cover(BenchmarkSet(entries)) == expected


def test_backreach_omits_derived_and_hands_without_applies_from() -> None:
    assert (
        back_reach_cover(
            BenchmarkSet(
                (
                    _max(4, 190),
                    _rest(6, 61, derived=True, applies=1),
                    _lt(20, 152, Sport.RUN, applies=1),
                )
            )
        )
        == ()
    )


@pytest.mark.parametrize(
    "mx,rs,derived_side",
    [(49, 50, "max"), (50, 50, "max"), (48, 52, "rest"), (53, 53, "rest")],
)
def test_maximum_not_above_rest_and_threshold_suppression(
    mx: int, rs: int, derived_side: str
) -> None:
    expected = (
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(3),
            None,
            None,
            _max(2, mx, derived=derived_side == "max"),
            _rest(3, rs, derived=derived_side == "rest"),
            None,
        ),
    )
    assert (
        inconsistencies(
            BenchmarkSet(
                (
                    _lt(1, 160, Sport.RUN),
                    _rest(3, rs, derived=derived_side == "rest"),
                    _max(2, mx, derived=derived_side == "max"),
                )
            )
        )
        == expected
    )


@pytest.mark.parametrize(
    "lt,bad", [(50, True), (49, True), (190, False), (120, False), (191, True)]
)
@pytest.mark.parametrize("derived_side", ["max", "rest"])
def test_threshold_reserve_endpoints(lt: int, bad: bool, derived_side: str) -> None:
    expected = (
        (
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                _d(3),
                None,
                Sport.RUN,
                _max(1, 190, derived=derived_side == "max"),
                _rest(2, 50, derived=derived_side == "rest"),
                _lt(3, lt, Sport.RUN),
            ),
        )
        if bad
        else ()
    )
    assert (
        inconsistencies(
            BenchmarkSet(
                (
                    _lt(3, lt, Sport.RUN),
                    _rest(2, 50, derived=derived_side == "rest"),
                    _max(1, 190, derived=derived_side == "max"),
                )
            )
        )
        == expected
    )


@pytest.mark.parametrize(
    "case",
    [
        "hand-max",
        "hand-threshold",
        "derived-lthr",
        "missing-max",
        "missing-rest",
        "missing-lthr",
        "lthr-not-yet",
    ],
)
def test_inconsistencies_do_not_fabricate_or_report_hand_only(case: str) -> None:
    entries = {
        "hand-max": (_max(1, 49), _rest(2, 50), _lt(3, 160, Sport.RUN)),
        "hand-threshold": (_max(1, 190), _rest(2, 50), _lt(3, 191, Sport.RUN)),
        "derived-lthr": (
            _max(1, 190),
            _rest(2, 50),
            _lt(3, 191, Sport.RUN, derived=True),
        ),
        "missing-max": (_rest(2, 50, derived=True), _lt(3, 191, Sport.RUN)),
        "missing-rest": (_max(1, 190, derived=True), _lt(3, 191, Sport.RUN)),
        "missing-lthr": (_max(1, 190, derived=True), _rest(2, 50)),
        "lthr-not-yet": (
            _max(10, 190, derived=True),
            _rest(10, 50),
            _lt(20, 120, Sport.RUN),
        ),
    }
    assert inconsistencies(BenchmarkSet(entries[case])) == ()


def test_two_disciplines_no_borrowing_sorted_with_distinct_thresholds() -> None:
    expected = (
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(2),
            _d(8),
            Sport.RUN,
            _max(1, 190, derived=True),
            _rest(1, 50),
            _lt(2, 193, Sport.RUN),
        ),
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(8),
            None,
            Sport.RIDE,
            _max(1, 190, derived=True),
            _rest(1, 50),
            _lt(8, 44, Sport.RIDE),
        ),
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(8),
            None,
            Sport.RUN,
            _max(1, 190, derived=True),
            _rest(1, 50),
            _lt(8, 198, Sport.RUN),
        ),
    )
    entries = (
        _lt(8, 198, Sport.RUN),
        _lt(2, 193, Sport.RUN),
        _lt(8, 44, Sport.RIDE),
        _lt(2, 162, Sport.RIDE),
        _rest(1, 50),
        _max(1, 190, derived=True),
    )
    assert inconsistencies(BenchmarkSet(entries)) == expected


def test_max_violation_merges_across_unrelated_lthr_breakpoints() -> None:
    expected = (
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(2),
            _d(10),
            None,
            _max(2, 48, derived=True),
            _rest(1, 51),
            None,
        ),
    )
    entries = (
        _lt(6, 177, Sport.RUN),
        _max(10, 194, derived=True),
        _lt(4, 162, Sport.RIDE),
        _max(2, 48, derived=True),
        _rest(1, 51),
    )
    assert inconsistencies(BenchmarkSet(entries)) == expected


def test_threshold_violation_merges_across_other_discipline_breakpoint() -> None:
    expected = (
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(3),
            None,
            Sport.RUN,
            _max(1, 190, derived=True),
            _rest(2, 50),
            _lt(3, 194, Sport.RUN),
        ),
    )
    entries = (
        _lt(8, 151, Sport.RIDE),
        _lt(3, 194, Sport.RUN),
        _rest(2, 50),
        _max(1, 190, derived=True),
    )
    assert inconsistencies(BenchmarkSet(entries)) == expected


@pytest.mark.parametrize("changed", ["max", "rest", "lthr"])
def test_same_numeric_value_with_new_entry_splits_period(changed: str) -> None:
    mx = _max(1, 190, derived=True)
    rs = _rest(2, 50)
    lt = _lt(3, 194, Sport.RUN)
    addition = {
        "max": _max(8, 190, derived=True),
        "rest": _rest(8, 50),
        "lthr": _lt(8, 194, Sport.RUN),
    }[changed]
    expected = (
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(3),
            _d(8),
            Sport.RUN,
            _max(1, 190, derived=True),
            _rest(2, 50),
            _lt(3, 194, Sport.RUN),
        ),
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(8),
            None,
            Sport.RUN,
            _max(8 if changed == "max" else 1, 190, derived=True),
            _rest(8 if changed == "rest" else 2, 50),
            _lt(8 if changed == "lthr" else 3, 194, Sport.RUN),
        ),
    )
    assert inconsistencies(BenchmarkSet((addition, lt, rs, mx))) == expected


def test_applies_from_breakpoints_and_violation_switch() -> None:
    expected = (
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(3),
            _d(5),
            None,
            _max(2, 48, derived=True),
            _rest(20, 51, applies=3),
            None,
        ),
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(5),
            _d(9),
            Sport.RIDE,
            _max(5, 192, derived=True),
            _rest(20, 51, applies=3),
            _lt(22, 49, Sport.RIDE, applies=4),
        ),
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(9),
            _d(20),
            Sport.RUN,
            _max(5, 192, derived=True),
            _rest(20, 51, applies=3),
            _lt(25, 195, Sport.RUN, applies=9),
        ),
    )
    entries = (
        _lt(25, 195, Sport.RUN, applies=9),
        _lt(22, 49, Sport.RIDE, applies=4),
        _lt(9, 164, Sport.RIDE),
        _rest(20, 51, applies=3),
        _max(5, 192, derived=True),
        _max(2, 48, derived=True),
        _max(20, 200),
    )
    assert inconsistencies(BenchmarkSet(entries)) == expected


@pytest.mark.parametrize(
    "inspect",
    [takeovers, current_takeovers, back_reach_cover, inconsistencies],
    ids=["takeovers", "current", "cover", "inconsistencies"],
)
def test_inspection_preserves_deep_input_state(
    inspect: Callable[[BenchmarkSet], object],
) -> None:
    benchmarks = BenchmarkSet(
        (
            _max(2, 194, derived=True),
            _max(20, 186, applies=1),
            _rest(1, 55),
            _lt(4, 199, Sport.RUN),
        )
    )
    before = deepcopy(asdict(benchmarks))
    inspect(benchmarks)
    assert asdict(benchmarks) == before


def test_period_order_uses_start_before_violation() -> None:
    expected = (
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(3),
            _d(10),
            Sport.RUN,
            _max(1, 190, derived=True),
            _rest(2, 50),
            _lt(3, 194, Sport.RUN),
        ),
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(10),
            _d(15),
            None,
            _max(10, 47, derived=True),
            _rest(2, 50),
            None,
        ),
        Inconsistency(
            Violation.THRESHOLD_OUTSIDE_RESERVE,
            _d(15),
            None,
            Sport.RUN,
            _max(15, 189, derived=True),
            _rest(2, 50),
            _lt(3, 194, Sport.RUN),
        ),
    )
    entries = (
        _max(15, 189, derived=True),
        _max(10, 47, derived=True),
        _lt(3, 194, Sport.RUN),
        _rest(2, 50),
        _max(1, 190, derived=True),
    )
    assert inconsistencies(BenchmarkSet(entries)) == expected


def test_maximum_applies_from_starts_period_before_measurement() -> None:
    expected = (
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(4),
            _d(21),
            None,
            _max(20, 50, applies=4),
            _rest(1, 55, derived=True),
            None,
        ),
    )
    entries = (_max(21, 190), _max(20, 50, applies=4), _rest(1, 55, derived=True))
    assert inconsistencies(BenchmarkSet(entries)) == expected


def test_empty_set_produces_empty_collections() -> None:
    benchmarks = BenchmarkSet(())
    assert (
        takeovers(benchmarks),
        current_takeovers(benchmarks),
        back_reach_cover(benchmarks),
        inconsistencies(benchmarks),
    ) == ((), (), (), ())


@pytest.mark.parametrize("changed", ["max", "rest"])
def test_max_violation_same_value_new_entry_splits_period(changed: str) -> None:
    expected = (
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(2),
            _d(8),
            None,
            _max(1, 49, derived=True),
            _rest(2, 53),
            None,
        ),
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST,
            _d(8),
            None,
            None,
            _max(8 if changed == "max" else 1, 49, derived=True),
            _rest(8 if changed == "rest" else 2, 53),
            None,
        ),
    )
    addition = _max(8, 49, derived=True) if changed == "max" else _rest(8, 53)
    assert (
        inconsistencies(
            BenchmarkSet((addition, _rest(2, 53), _max(1, 49, derived=True)))
        )
        == expected
    )


@pytest.mark.parametrize("violation", ["threshold", "maximum"])
def test_same_entries_recurring_after_valid_gap_stay_separate(violation: str) -> None:
    entries: tuple[Benchmark, ...]
    if violation == "threshold":
        entries = (
            _lt(20, 200, Sport.RUN, applies=1),
            _lt(10, 120, Sport.RUN, applies=5),
            _max(1, 190, derived=True),
            _rest(1, 50),
        )
        expected = (
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                _d(1),
                _d(5),
                Sport.RUN,
                _max(1, 190, derived=True),
                _rest(1, 50),
                _lt(20, 200, Sport.RUN, applies=1),
            ),
            Inconsistency(
                Violation.THRESHOLD_OUTSIDE_RESERVE,
                _d(20),
                None,
                Sport.RUN,
                _max(1, 190, derived=True),
                _rest(1, 50),
                _lt(20, 200, Sport.RUN, applies=1),
            ),
        )
    else:
        entries = (
            _max(20, 50, applies=1),
            _max(10, 190, applies=5),
            _rest(1, 60, derived=True),
        )
        expected = (
            Inconsistency(
                Violation.MAX_NOT_ABOVE_REST,
                _d(1),
                _d(5),
                None,
                _max(20, 50, applies=1),
                _rest(1, 60, derived=True),
                None,
            ),
            Inconsistency(
                Violation.MAX_NOT_ABOVE_REST,
                _d(20),
                None,
                None,
                _max(20, 50, applies=1),
                _rest(1, 60, derived=True),
                None,
            ),
        )
    assert inconsistencies(BenchmarkSet(entries)) == expected


@pytest.mark.parametrize("earlier_value", [55, 50])
def test_generated_resting_walk_restarts_at_future_hand_change_and_keeps_cover(
    earlier_value: int,
) -> None:
    hands = (
        Benchmark(
            BenchmarkKind.RESTING_HR_BPM,
            None,
            50,
            date(2024, 2, 20),
            applies_from=_d(1),
        ),
        Benchmark(
            BenchmarkKind.RESTING_HR_BPM,
            None,
            earlier_value,
            date(2024, 2, 10),
            applies_from=_d(8),
        ),
    )
    evidence = tuple(
        Evidence(
            _d(1) + timedelta(days=offset),
            60,
            "synthetic",
            "wellness/2024.csv",
            "synthetic:resting_hr_bpm",
            "synthetic window",
            "synthetic resting level",
        )
        for offset in range(20)
    )
    expected_walk = TimelineResult((), ())
    expected_cover = (
        BackReach(
            BenchmarkKind.RESTING_HR_BPM,
            Benchmark(
                BenchmarkKind.RESTING_HR_BPM,
                None,
                earlier_value,
                date(2024, 2, 10),
                applies_from=_d(8),
            ),
            _d(8),
            date(2024, 2, 10),
        ),
        BackReach(
            BenchmarkKind.RESTING_HR_BPM,
            Benchmark(
                BenchmarkKind.RESTING_HR_BPM,
                None,
                50,
                date(2024, 2, 20),
                applies_from=_d(1),
            ),
            _d(1),
            _d(8),
        ),
    )
    walk = derive_timeline(RESTING_RULE, evidence, hands)
    assert walk == expected_walk
    assert back_reach_cover(BenchmarkSet((*hands, *walk.entries))) == expected_cover


@pytest.mark.parametrize(
    ("kind", "value"),
    [(BenchmarkKind.MAX_HR_BPM, 190), (BenchmarkKind.RESTING_HR_BPM, 50)],
    ids=["max", "rest"],
)
@pytest.mark.parametrize("measured", [False, True], ids=["absent", "measured"])
def test_equal_applies_measurement_parser_valid(
    kind: BenchmarkKind, value: int, measured: bool
) -> None:
    raw: dict[str, object] = {
        "value": value,
        "measured_on": date(2024, 1, 20),
        "applies_from": date(2024, 1, 20),
    }
    if measured:
        raw["source"] = {"kind": "measured"}
    expected = (
        BackReach(
            kind,
            Benchmark(
                kind,
                None,
                value,
                date(2024, 1, 20),
                applies_from=date(2024, 1, 20),
                source=BenchmarkSource(BenchmarkSourceKind.MEASURED)
                if measured
                else None,
            ),
            date(2024, 1, 20),
            date(2024, 1, 20),
        ),
    )
    entries = parse_benchmarks({"benchmarks": {"athlete": {kind.value: [raw]}}})
    assert back_reach_cover(entries) == expected


@pytest.mark.parametrize(
    ("kind", "value"),
    [(BenchmarkKind.MAX_HR_BPM, 190), (BenchmarkKind.RESTING_HR_BPM, 50)],
    ids=["max", "rest"],
)
def test_measured_origin_full_cover_parser_valid(
    kind: BenchmarkKind, value: int
) -> None:
    expected = (
        BackReach(
            kind,
            Benchmark(
                kind,
                None,
                value,
                date(2024, 1, 20),
                applies_from=date(2024, 1, 1),
                source=BenchmarkSource(BenchmarkSourceKind.MEASURED),
            ),
            date(2024, 1, 1),
            date(2024, 1, 20),
        ),
    )
    entries = parse_benchmarks(
        {
            "benchmarks": {
                "athlete": {
                    kind.value: [
                        {
                            "value": value,
                            "measured_on": date(2024, 1, 20),
                            "applies_from": date(2024, 1, 1),
                            "source": {"kind": "measured"},
                        }
                    ]
                }
            }
        }
    )
    assert back_reach_cover(entries) == expected


@pytest.mark.parametrize("violation", ["maximum", "threshold"])
def test_one_breakpoint_nonempty_open_period_parser_valid(violation: str) -> None:
    raw: dict[str, object] = {
        "athlete": {
            "max_hr_bpm": [
                {
                    "value": 49 if violation == "maximum" else 190,
                    "measured_on": date(2024, 1, 1),
                    "source": {
                        "kind": "derived",
                        "method": "synthetic",
                        "document": "page",
                        "inputs": "inputs",
                        "citation": "choice",
                    },
                }
            ],
            "resting_hr_bpm": [{"value": 50, "measured_on": date(2024, 1, 1)}],
        }
    }
    if violation == "threshold":
        raw["run"] = {"lthr_bpm": [{"value": 191, "measured_on": date(2024, 1, 1)}]}
    expected = (
        Inconsistency(
            Violation.MAX_NOT_ABOVE_REST
            if violation == "maximum"
            else Violation.THRESHOLD_OUTSIDE_RESERVE,
            date(2024, 1, 1),
            None,
            None if violation == "maximum" else Sport.RUN,
            Benchmark(
                BenchmarkKind.MAX_HR_BPM,
                None,
                49 if violation == "maximum" else 190,
                date(2024, 1, 1),
                source=BenchmarkSource(
                    BenchmarkSourceKind.DERIVED,
                    "synthetic",
                    "page",
                    "inputs",
                    "choice",
                ),
            ),
            Benchmark(BenchmarkKind.RESTING_HR_BPM, None, 50, date(2024, 1, 1)),
            None
            if violation == "maximum"
            else Benchmark(BenchmarkKind.LTHR_BPM, Sport.RUN, 191, date(2024, 1, 1)),
        ),
    )
    entries = parse_benchmarks({"benchmarks": raw})
    assert inconsistencies(entries) == expected
