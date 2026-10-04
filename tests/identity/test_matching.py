"""Tests for the cross-source match rule (Req 3.1-3.8, 3.11; Amendment 1).

The rule is exercised over :class:`SessionKey` values, one difference per pair:

* every tolerance has a pair exactly at its value (inclusive, so it matches) and
  a pair one unit beyond (it does not), so widening a constant by one unit or
  turning ``<=`` into ``<`` changes a verdict;
* the hand-built pairs carry no device digest except in the device-tier cases,
  and no phone copy except in the shifted-tier cases and the zero-shift cases;
  the pairs built from parsed synthetic files carry the files' own digests;
* every pair verdict is asserted in both argument orders (symmetry);
* the timer test goes through :func:`session_key` on parsed synthetic files,
  since the key itself has no timer field to vary.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from fitdocs.identity import matching
from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.matching import (
    DISTANCE_TOLERANCE_FRACTION,
    DISTANCE_TOLERANCE_M,
    ELAPSED_TOLERANCE_S,
    SHIFT_MAX_HOURS,
    SHIFT_STEP_S,
    SHIFTED_DISTANCE_TOLERANCE_M,
    SHIFTED_ELAPSED_TOLERANCE_S,
    START_TOLERANCE_S,
    TOLERANCE_SOURCES,
    Evidence,
    SessionKey,
    pair_evidence,
    session_key,
)
from fitdocs.ingest import parse_fit
from tests.fixtures import builder, identity

_T0 = datetime(2024, 5, 1, 12, 0, 0, tzinfo=UTC)
_HOUR = timedelta(hours=1)
_DEVICE = "0123456789abcdef"
_OTHER_DEVICE = "fedcba9876543210"


def _key(
    *,
    sport: str = "Run",
    start: datetime | None = _T0,
    elapsed_s: float | None = 3000.0,
    distance_m: float | None = 10_000.0,
    device: str | None = None,
    kind: SourceKind | None = SourceKind.ORIGINAL,
) -> SessionKey:
    return SessionKey(
        sport=sport,
        start=start,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
        device=device,
        kind=kind,
    )


def _check(a: SessionKey, b: SessionKey, expected: Evidence | None) -> None:
    assert pair_evidence(a, b) == expected
    assert pair_evidence(b, a) == expected


# --- constants ---------------------------------------------------------------


def test_constants_have_the_designed_values_and_types() -> None:
    assert START_TOLERANCE_S == 1.0
    assert ELAPSED_TOLERANCE_S == 10.0
    assert DISTANCE_TOLERANCE_M == 5.0
    assert DISTANCE_TOLERANCE_FRACTION == 0.2
    assert SHIFT_STEP_S == 3600
    assert SHIFT_MAX_HOURS == 36
    assert SHIFTED_ELAPSED_TOLERANCE_S == 5.0
    assert SHIFTED_DISTANCE_TOLERANCE_M == 10.0
    for name in ("SHIFT_STEP_S", "SHIFT_MAX_HOURS"):
        assert type(getattr(matching, name)) is int
    for name in (
        "START_TOLERANCE_S",
        "ELAPSED_TOLERANCE_S",
        "DISTANCE_TOLERANCE_M",
        "DISTANCE_TOLERANCE_FRACTION",
        "SHIFTED_ELAPSED_TOLERANCE_S",
        "SHIFTED_DISTANCE_TOLERANCE_M",
    ):
        assert type(getattr(matching, name)) is float


def test_every_constant_has_a_one_line_source() -> None:
    constants = {
        name
        for name in vars(matching)
        if name.endswith(("_S", "_M", "_HOURS", "_FRACTION")) and name.isupper()
    }
    assert constants and set(TOLERANCE_SOURCES) == constants
    for source in TOLERANCE_SOURCES.values():
        assert source and "\n" not in source


def test_evidence_vocabulary() -> None:
    assert [e.value for e in Evidence] == [
        "source",
        "uuid",
        "device",
        "strict",
        "shifted",
    ]


# --- start tolerance (3.2, 3.3, 3.5) ------------------------------------------


@pytest.mark.parametrize(
    ("delta_s", "expected"),
    [(0, Evidence.STRICT), (1, Evidence.STRICT), (2, None)],
)
def test_strict_start_boundary(delta_s: int, expected: Evidence | None) -> None:
    _check(_key(), _key(start=_T0 + timedelta(seconds=delta_s)), expected)


@pytest.mark.parametrize(
    ("delta_s", "expected"),
    [(0, Evidence.DEVICE), (1, Evidence.DEVICE), (2, None)],
)
def test_device_start_boundary(delta_s: int, expected: Evidence | None) -> None:
    # Elapsed and distance are absent so only the device tier can answer.
    a = _key(device=_DEVICE, elapsed_s=None, distance_m=None)
    b = _key(
        device=_DEVICE,
        elapsed_s=None,
        distance_m=None,
        start=_T0 + timedelta(seconds=delta_s),
    )
    _check(a, b, expected)


def test_device_needs_both_devices_and_they_equal() -> None:

    def bare(device: str | None) -> SessionKey:
        return _key(device=device, elapsed_s=None, distance_m=None)

    _check(bare(_DEVICE), bare(_OTHER_DEVICE), None)
    _check(bare(_DEVICE), bare(None), None)
    _check(bare(None), bare(None), None)


def test_device_is_reported_over_strict() -> None:
    _check(_key(device=_DEVICE), _key(device=_DEVICE), Evidence.DEVICE)


# --- strict tier (Amendment 1: A1.1, A1.2) -------------------------------------
#
# The base pair records 10 000 m, so the relative bound (20 % of the longer
# distance) is the governing one; the short-distance pairs exercise the 5 m
# floor. With both distances recorded, elapsed time is never compared.


@pytest.mark.parametrize(
    ("delta_m", "expected"),
    [(2_500.0, Evidence.STRICT), (2_501.0, None)],
)
def test_strict_relative_distance_boundary(
    delta_m: float, expected: Evidence | None
) -> None:
    # 2 500 m of 12 500 m (the longer) is exactly 20 %; 2 501 m of 12 501 m is
    # beyond it.
    _check(_key(), _key(distance_m=10_000.0 + delta_m), expected)


def test_strict_relative_distance_is_of_the_longer_distance() -> None:
    # 2 400 m is 24 % of the shorter (10 000 m) but 19.4 % of the longer
    # (12 400 m): measured against the longer it matches.
    _check(_key(), _key(distance_m=12_400.0), Evidence.STRICT)


@pytest.mark.parametrize(
    ("delta_m", "expected"),
    [(5.0, Evidence.STRICT), (6.0, None)],
)
def test_strict_distance_floor_governs_short_distances(
    delta_m: float, expected: Evidence | None
) -> None:
    # 20 % of 10-16 m is 2-3.2 m, under the 5 m floor, so the floor answers.
    _check(_key(distance_m=10.0), _key(distance_m=10.0 + delta_m), expected)


def test_strict_distance_floor_matches_two_zero_distances() -> None:
    _check(_key(distance_m=0.0), _key(distance_m=0.0), Evidence.STRICT)
    _check(_key(distance_m=0.0), _key(distance_m=5.0), Evidence.STRICT)
    _check(_key(distance_m=0.0), _key(distance_m=6.0), None)


@pytest.mark.parametrize("elapsed_delta_s", [11.0, 210.5, 1_685.2])
def test_elapsed_is_not_compared_when_both_distances_are_recorded(
    elapsed_delta_s: float,
) -> None:
    # The measured Stryd↔HealthFit shape: the copy ends its session when the
    # workout is ended on the watch, the Stryd file at its last timer stop, so
    # elapsed differs by however long the athlete stayed paused.
    stryd = _key(elapsed_s=1_240.0, distance_m=1_888.9)
    copy = _key(
        kind=SourceKind.PHONE_COPY,
        elapsed_s=1_240.0 + elapsed_delta_s,
        distance_m=1_888.89,
    )
    _check(stryd, copy, Evidence.STRICT)


def test_a_truncated_tail_matches() -> None:
    # The measured Stryd file that stopped recording 28 s early: 91.32 m short
    # of 9 237.32 m (0.99 %), elapsed 28.6 s short.
    stryd = _key(elapsed_s=2_879.0, distance_m=9_146.0)
    copy = _key(kind=SourceKind.PHONE_COPY, elapsed_s=2_907.626, distance_m=9_237.32)
    _check(stryd, copy, Evidence.STRICT)


def test_absent_elapsed_with_both_distances_is_strict() -> None:
    _check(_key(elapsed_s=None), _key(), Evidence.STRICT)
    _check(_key(elapsed_s=None), _key(elapsed_s=None), Evidence.STRICT)


@pytest.mark.parametrize(
    ("delta_s", "expected"),
    [(10.0, Evidence.STRICT), (11.0, None)],
)
@pytest.mark.parametrize("missing", ["one", "both"])
def test_strict_elapsed_fallback_boundary_when_a_distance_is_missing(
    delta_s: float, expected: Evidence | None, missing: str
) -> None:
    a = _key(distance_m=None)
    b = _key(
        elapsed_s=3000.0 + delta_s,
        distance_m=None if missing == "both" else 10_000.0,
    )
    _check(a, b, expected)


# --- shifted tier (3.4) -------------------------------------------------------


def _shifted_pair(
    *,
    shift_s: float = 3600,
    elapsed_delta_s: float = 0.0,
    distance_delta_m: float = 0.0,
) -> tuple[SessionKey, SessionKey]:
    original = _key(kind=SourceKind.ORIGINAL)
    copy = _key(
        kind=SourceKind.PHONE_COPY,
        start=_T0 + timedelta(seconds=shift_s),
        elapsed_s=3000.0 + elapsed_delta_s,
        distance_m=10_000.0 + distance_delta_m,
    )
    return original, copy


def test_shifted_baseline_matches() -> None:
    _check(*_shifted_pair(), Evidence.SHIFTED)


@pytest.mark.parametrize(
    ("delta_s", "expected"),
    [
        (5.0, Evidence.SHIFTED),
        (6.0, None),
    ],
)
def test_shifted_elapsed_boundary(delta_s: float, expected: Evidence | None) -> None:
    _check(*_shifted_pair(elapsed_delta_s=delta_s), expected)


@pytest.mark.parametrize(
    ("delta_m", "expected"),
    [
        (10.0, Evidence.SHIFTED),
        (11.0, None),
    ],
)
def test_shifted_distance_boundary(delta_m: float, expected: Evidence | None) -> None:
    _check(*_shifted_pair(distance_delta_m=delta_m), expected)


@pytest.mark.parametrize(
    ("shift_s", "expected"),
    [
        # the 1 s tolerance around a whole hour, both sides, and one unit beyond
        (3600 + 1, Evidence.SHIFTED),
        (3600 - 1, Evidence.SHIFTED),
        (3600 + 2, None),
        (3600 - 2, None),
        # the same at two hours (a step one unit wider would move this one)
        (7200 + 1, Evidence.SHIFTED),
        (7200 + 2, None),
        (7200 - 2, None),
        # the window: 1 h and 36 h are in, 0.5 h and 37 h are out
        (1800, None),
        (36 * 3600, Evidence.SHIFTED),
        (36 * 3600 + 1, Evidence.SHIFTED),
        (36 * 3600 + 2, None),
        (37 * 3600, None),
        # a negative shift (copy earlier than the original)
        (-3600, Evidence.SHIFTED),
        (-36 * 3600, Evidence.SHIFTED),
        (-37 * 3600, None),
        (-(3600 + 2), None),
    ],
)
def test_shift_window_and_step(shift_s: int, expected: Evidence | None) -> None:
    _check(*_shifted_pair(shift_s=shift_s), expected)


def test_zero_shift_is_not_a_shift() -> None:
    # A start within 1 s is zero hours apart. On 20 m and 28 m the strict limit
    # is max(5 m, 20 % of 28 m) = 5.6 m, so the 8 m gap fails it but is inside
    # the shifted 10 m limit: only the shifted tier could accept the pair, and
    # it must not, since k = 0 is outside 1..36.
    for shift_s in (0, 1):
        original, copy = _shifted_pair(shift_s=shift_s)
        _check(
            dataclasses.replace(original, distance_m=20.0),
            dataclasses.replace(copy, distance_m=28.0),
            None,
        )
    # with the strict limits met, a phone copy at zero shift is strict evidence
    _check(*_shifted_pair(shift_s=0), Evidence.STRICT)


def test_whole_hour_shift_without_a_phone_copy_never_matches() -> None:
    for kind in (SourceKind.ORIGINAL, SourceKind.UNKNOWN, None):
        a = _key(kind=kind)
        b = _key(kind=kind, start=_T0 + _HOUR)
        _check(a, b, None)
    # mixed non-phone kinds too
    _check(
        _key(kind=SourceKind.ORIGINAL),
        _key(kind=SourceKind.UNKNOWN, start=_T0 + _HOUR),
        None,
    )


@pytest.mark.parametrize("phone_side", ["a", "b", "both"])
def test_one_phone_copy_on_either_side_is_enough(phone_side: str) -> None:
    a = _key(kind=SourceKind.PHONE_COPY if phone_side != "b" else SourceKind.ORIGINAL)
    b = _key(
        kind=SourceKind.PHONE_COPY if phone_side != "a" else SourceKind.ORIGINAL,
        start=_T0 + 5 * _HOUR,
    )
    _check(a, b, Evidence.SHIFTED)


def test_shifted_needs_both_distances_and_both_elapsed() -> None:
    original, copy = _shifted_pair()
    _check(original, dataclasses.replace(copy, distance_m=None), None)
    _check(dataclasses.replace(original, distance_m=None), copy, None)
    _check(
        dataclasses.replace(original, distance_m=None),
        dataclasses.replace(copy, distance_m=None),
        None,
    )
    _check(original, dataclasses.replace(copy, elapsed_s=None), None)
    _check(dataclasses.replace(original, elapsed_s=None), copy, None)


def test_shifted_needs_the_same_sport() -> None:
    original, copy = _shifted_pair()
    _check(original, dataclasses.replace(copy, sport="Ride"), None)


# --- sport (3.1) ---------------------------------------------------------------


def test_same_everything_of_a_different_sport_never_matches() -> None:
    a = _key(device=_DEVICE)
    b = _key(device=_DEVICE, sport="Ride")
    _check(a, b, None)
    # and without a device, where only the strict tier could have answered
    _check(_key(), _key(sport="Ride"), None)


# --- absent values (3.7, 3.8) --------------------------------------------------


def test_absent_start_matches_nothing() -> None:
    same = _key(device=_DEVICE)
    _check(same, dataclasses.replace(same, start=None), None)
    _check(
        dataclasses.replace(same, start=None),
        dataclasses.replace(same, start=None),
        None,
    )
    original, copy = _shifted_pair()
    _check(original, dataclasses.replace(copy, start=None), None)


def test_absent_elapsed_and_absent_distance_match_by_device_only() -> None:
    # A1.2: no pair of distances and no pair of elapsed times to compare.
    def bare(device: str | None = None) -> SessionKey:
        return _key(elapsed_s=None, distance_m=None, device=device)

    _check(bare(device=_DEVICE), _key(device=_DEVICE), Evidence.DEVICE)
    # no device on either side: nothing to go on, whichever side lacks what
    _check(bare(), _key(), None)
    _check(bare(), bare(), None)
    _check(_key(elapsed_s=None), _key(distance_m=None), None)
    _check(
        _key(elapsed_s=None, distance_m=10_000.0),
        _key(elapsed_s=3000.0, distance_m=None),
        None,
    )
    # different devices: nothing
    _check(bare(device=_DEVICE), _key(device=_OTHER_DEVICE), None)


def test_absent_distance_is_not_compared() -> None:
    # one-sided: the recorded distance has nothing to be compared with
    _check(_key(), _key(distance_m=None), Evidence.STRICT)
    # two-sided
    _check(_key(distance_m=None), _key(distance_m=None), Evidence.STRICT)
    # and recorded distances far apart still reject when both are recorded
    _check(_key(), _key(distance_m=10_000.0 * 2), None)


# --- the two-10k counter-example (3.5) ------------------------------------------


def test_two_ten_k_runs_a_day_apart_are_not_one_session() -> None:
    first, second = identity.ten_k_pair()
    a = session_key(parse_fit(first.data))
    b = session_key(parse_fit(second.data))
    assert a.start is not None and b.start is not None
    assert abs((a.start - b.start).total_seconds()) == 24 * 3600 + 17 * 60
    assert a.elapsed_s is not None and b.elapsed_s is not None
    assert abs(a.elapsed_s - b.elapsed_s) == 60.0
    assert a.distance_m is not None and b.distance_m is not None
    assert abs(a.distance_m - b.distance_m) == 200.0
    _check(a, b, None)
    # the same pair with the second as a phone copy is still not a shift
    _check(a, dataclasses.replace(b, kind=SourceKind.PHONE_COPY), None)


# --- timer time is never evidence (3.6) ------------------------------------------


def _parsed_key(*, timer_s: float) -> SessionKey:
    data = identity.session_fit_bytes(
        sport="running",
        start=builder.FIT_TIMESTAMP_BASE + 700_000_000,
        elapsed_s=3000.0,
        timer_s=timer_s,
        distance_m=10_000.0,
        manufacturer="garmin",
        product=3843,
        serial=1_234_567,
        time_created=builder.FIT_TIMESTAMP_BASE + 700_000_000,
    )
    return session_key(parse_fit(data))


def test_timer_time_is_not_compared() -> None:
    fast = _parsed_key(timer_s=3000.0)
    slow = _parsed_key(timer_s=2600.0)
    # the recordings differ by 400 s of timer only; the keys are the same value
    assert fast == slow
    _check(fast, slow, Evidence.DEVICE)
    # without the device the strict tier still matches on elapsed alone
    _check(
        dataclasses.replace(fast, device=None),
        dataclasses.replace(slow, device=None),
        Evidence.STRICT,
    )


def test_session_key_has_no_timer_field() -> None:
    names = {f.name for f in dataclasses.fields(SessionKey)}
    assert names == {"sport", "start", "elapsed_s", "distance_m", "device", "kind"}


# --- session_key from a parsed file ------------------------------------------------


def test_session_key_reads_the_parsed_activity() -> None:
    species = identity.garmin_original()
    activity = parse_fit(species.data)
    key = session_key(activity)
    assert key.sport == activity.sport.value
    assert key.start == activity.start_time and key.start is not None
    assert key.elapsed_s == species.elapsed_s
    assert key.distance_m == species.distance_m
    assert key.kind is SourceKind.ORIGINAL
    assert key.device is not None


def test_session_key_of_a_healthfit_copy_is_a_phone_copy() -> None:
    assert session_key(parse_fit(identity.healthfit_copy().data)).kind is (
        SourceKind.PHONE_COPY
    )


def test_a_real_species_shift_is_matched_from_parsed_files() -> None:
    original = session_key(parse_fit(identity.garmin_original().data))
    shifted = session_key(parse_fit(identity.healthfit_shifted().data))
    # elapsed 0.5 s and distance 2 m apart, start two hours apart
    _check(original, shifted, Evidence.SHIFTED)


# --- inclusive to floating-point precision ----------------------------------


def test_bounds_exact_in_decimal_are_inclusive_in_binary() -> None:
    # 25.05 - 20.04 is 5.010000000000002 and 0.2 * 25.05 is 5.010000000000001:
    # the gap is 20 % of the longer exactly in decimal and must match.
    _check(_key(distance_m=25.05), _key(distance_m=20.04), Evidence.STRICT)
    # 8.05 - 3.05 is 5.000000000000001: the 5 m floor, exactly.
    _check(_key(distance_m=3.05), _key(distance_m=8.05), Evidence.STRICT)
    # 16.1 - 6.1 is 10.000000000000002: the elapsed fallback's 10 s, exactly.
    _check(
        _key(elapsed_s=6.1, distance_m=None),
        _key(elapsed_s=16.1, distance_m=None),
        Evidence.STRICT,
    )


def test_the_float_slack_admits_rounding_only() -> None:
    # 2 500.001 m on 12 500.001 m is 0.8 mm beyond 20 % of the longer: a slack
    # wider than rounding (1e-4 would admit 0.25 m) turns this into a match.
    _check(_key(), _key(distance_m=12_500.001), None)
    # and 1 ms beyond the elapsed fallback's 10 s
    _check(
        _key(distance_m=None),
        _key(elapsed_s=3010.001, distance_m=None),
        None,
    )
