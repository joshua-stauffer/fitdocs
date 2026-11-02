"""Tests for the strict tier of the match rule (strava-publish 6.3, 15.2).

Every boundary has a pair exactly at the tolerance (it matches) and a pair just
beyond it (it does not).
"""

from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fitdocs.identity import strict
from fitdocs.identity.strict import (
    DISTANCE_TOLERANCE_FRACTION,
    DISTANCE_TOLERANCE_M,
    ELAPSED_TOLERANCE_S,
    START_TOLERANCE_S,
    StrictFacts,
    strict_match,
    within,
)

T0 = datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)


def facts(
    *,
    sport: str = "running",
    start: datetime | None = T0,
    elapsed_s: float | None = 3000.0,
    distance_m: float | None = 10000.0,
) -> StrictFacts:
    return StrictFacts(sport, start, elapsed_s, distance_m)


def both_ways(a: StrictFacts, b: StrictFacts) -> bool:
    forward = strict_match(a, b)
    assert strict_match(b, a) is forward
    return forward


def test_constants_are_the_measured_values() -> None:
    assert (
        START_TOLERANCE_S,
        ELAPSED_TOLERANCE_S,
        DISTANCE_TOLERANCE_M,
        DISTANCE_TOLERANCE_FRACTION,
    ) == (1.0, 10.0, 5.0, 0.2)


@pytest.mark.parametrize(
    ("delta", "tolerance", "expected"),
    [
        (1.0, 1.0, True),
        (1.0 * (1.0 + 1e-9), 1.0, True),  # the slack's own edge, equal not less
        (1.000001, 1.0, False),
        (0.0, 0.0, True),
        (0.5, 1.0, True),
    ],
)
def test_within_is_inclusive(delta: float, tolerance: float, expected: bool) -> None:
    assert within(delta, tolerance) is expected


def test_within_forgives_a_last_place_overshoot() -> None:
    # 25.05 - 20.04 exceeds 0.2 * 25.05 by one unit in the last place.
    delta = 25.05 - 20.04
    assert delta > DISTANCE_TOLERANCE_FRACTION * 25.05
    assert within(delta, DISTANCE_TOLERANCE_FRACTION * 25.05)


@pytest.mark.parametrize(
    ("offset_s", "expected"),
    [(0.0, True), (1.0, True), (-1.0, True), (1.000001, False), (-1.000001, False)],
)
def test_start_tolerance(offset_s: float, expected: bool) -> None:
    other = facts(start=T0 + timedelta(seconds=offset_s))
    assert both_ways(facts(), other) is expected


@pytest.mark.parametrize(
    ("other_distance", "expected"),
    [
        (11000.0, True),  # gap 1000 against 20 % of 11000 = 2200
        (12500.0, True),  # gap 2500 == 20 % of 12500 exactly
        (12500.5, False),  # gap 2500.5 > 2500.1
    ],
)
def test_distance_at_twenty_percent(other_distance: float, expected: bool) -> None:
    assert both_ways(facts(), facts(distance_m=other_distance)) is expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (0.0, 5.0, True),  # gap at the 5 m floor; 20 % of 5 m is only 1 m
        (0.0, 5.01, False),  # just over the floor
        (20.0, 25.0, True),  # gap 5 == floor; 20 % of 25 is also 5
        (20.0, 25.05, False),
    ],
)
def test_distance_at_the_five_metre_floor(a: float, b: float, expected: bool) -> None:
    assert both_ways(facts(distance_m=a), facts(distance_m=b)) is expected


@pytest.mark.parametrize(
    ("other_elapsed", "expected"),
    [(3010.0, True), (2990.0, True), (3010.01, False), (2989.99, False)],
)
def test_missing_distance_compares_elapsed(
    other_elapsed: float, expected: bool
) -> None:
    a = facts(distance_m=None)
    b = facts(distance_m=None, elapsed_s=other_elapsed)
    assert both_ways(a, b) is expected
    one_sided = facts(elapsed_s=other_elapsed)
    assert both_ways(a, one_sided) is expected


def test_far_distances_with_equal_elapsed_never_match() -> None:
    a = facts(distance_m=10000.0, elapsed_s=3000.0)
    b = facts(distance_m=14000.0, elapsed_s=3000.0)
    assert not both_ways(a, b)


def test_close_distances_with_far_elapsed_still_match() -> None:
    a = facts(distance_m=10000.0, elapsed_s=3000.0)
    b = facts(distance_m=10001.0, elapsed_s=4685.0)
    assert both_ways(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (facts(distance_m=None, elapsed_s=None), facts(distance_m=None)),
        (facts(distance_m=None), facts(distance_m=None, elapsed_s=None)),
        (facts(distance_m=None, elapsed_s=None), facts(elapsed_s=None)),
    ],
)
def test_missing_distance_and_missing_elapsed_never_match(
    a: StrictFacts, b: StrictFacts
) -> None:
    assert not both_ways(a, b)


def test_sport_must_be_equal() -> None:
    assert not both_ways(facts(), facts(sport="cycling"))


@pytest.mark.parametrize("which", ["a", "b"])
def test_missing_start_never_matches(which: str) -> None:
    missing = facts(start=None)
    present = facts()
    pair = (missing, present) if which == "a" else (present, missing)
    assert not strict_match(*pair)
    assert not strict_match(missing, missing)


def test_module_imports_only_the_standard_library() -> None:
    source = Path(strict.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import leaves the standard library"
            assert node.module is not None
            names.add(node.module.split(".")[0])
    assert names, "the walk found no imports; it is looking at the wrong file"
    assert "dataclasses" in names
    assert names <= set(sys.stdlib_module_names)
