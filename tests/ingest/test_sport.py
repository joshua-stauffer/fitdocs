"""Tests for the sport detector (Req 5.1-5.6).

These exercise :func:`fitdocs.ingest.sport.detect_sport`, a pure function over
two raw FIT strings (``sport``, ``sub_sport``) returning a normalized
``(Sport, Modality, is_indoor)`` triple. The cases are table-driven so every
mapped sport, the never-failing unknown/absent fallback, the strength modality
override, and each machine-bound indoor sub-sport are each asserted explicitly.
Coverage:

* every mapped FIT sport normalizes to its :class:`Sport` label (Req 5.1, 5.2);
* an unrecognized sport, ``None``, and (defensively) a non-string value all fall
  back to :attr:`Sport.WORKOUT` without raising (Req 5.3);
* exactly one modality is assigned, run/cycling/swimming mapping to
  run/bike/swim and everything else to ``other`` (Req 5.4);
* a ``strength_training`` sub-sport forces :attr:`Modality.STRENGTH`, winning
  over the sport-derived modality regardless of sport (Req 5.5);
* each verified machine-bound sub-sport flags ``is_indoor=True`` while ambiguous
  or outdoor/absent sub-sports do not (Req 5.6).
"""

from __future__ import annotations

import pytest

from fitdocs.ingest.sport import INDOOR_SUB_SPORTS, detect_sport
from fitdocs.model import Modality, Sport

# --- Sport map: every mapped FIT sport -> normalized label (Req 5.1, 5.2) ---

_SPORT_CASES = [
    ("cycling", Sport.RIDE),
    ("running", Sport.RUN),
    ("swimming", Sport.SWIM),
    ("walking", Sport.WALK),
    ("hiking", Sport.HIKE),
    ("rowing", Sport.ROWING),
    ("training", Sport.WORKOUT),
    ("fitness_equipment", Sport.WORKOUT),
    ("generic", Sport.WORKOUT),
]


@pytest.mark.parametrize(("sport", "expected"), _SPORT_CASES)
def test_mapped_sport_normalizes_to_label(sport: str, expected: Sport) -> None:
    """Each mapped FIT sport string yields its normalized label (Req 5.1, 5.2)."""
    label, _modality, _is_indoor = detect_sport(sport, None)

    assert label is expected


# --- Unknown / absent fallback never fails (Req 5.3) ------------------------

_FALLBACK_SPORTS: list[object] = [
    "not_a_real_sport",
    "",
    "CYCLING",  # case-sensitive: only the exact lowercase FIT string maps
    None,
    123,  # defensively: a non-string value must not raise
    object(),
]


@pytest.mark.parametrize("sport", _FALLBACK_SPORTS)
def test_unknown_or_absent_sport_falls_back_to_workout(sport: object) -> None:
    """An unrecognized, absent, or non-string sport -> Workout, no raise (Req 5.3)."""
    label, _modality, _is_indoor = detect_sport(sport, None)  # type: ignore[arg-type]

    assert label is Sport.WORKOUT


# --- Modality: exactly one, mapped per movement (Req 5.4) -------------------

_MODALITY_CASES = [
    ("running", Modality.RUN),
    ("cycling", Modality.BIKE),
    ("swimming", Modality.SWIM),
    ("walking", Modality.OTHER),
    ("hiking", Modality.OTHER),
    ("rowing", Modality.OTHER),
    ("training", Modality.OTHER),
    ("fitness_equipment", Modality.OTHER),
    ("generic", Modality.OTHER),
    ("not_a_real_sport", Modality.OTHER),
    (None, Modality.OTHER),
]


@pytest.mark.parametrize(("sport", "expected"), _MODALITY_CASES)
def test_modality_is_single_and_mapped(sport: str | None, expected: Modality) -> None:
    """Each sport yields exactly one modality per the movement map (Req 5.4)."""
    _label, modality, _is_indoor = detect_sport(sport, None)

    assert modality is expected
    assert isinstance(modality, Modality)


# --- Strength wins over the sport-derived modality (Req 5.5) -----------------

_STRENGTH_SPORTS: list[str | None] = [
    "training",
    "fitness_equipment",
    "running",  # strength sub-sport overrides even a run sport
    "cycling",
    "generic",
    None,
]


@pytest.mark.parametrize("sport", _STRENGTH_SPORTS)
def test_strength_training_sub_sport_forces_strength_modality(
    sport: str | None,
) -> None:
    """``strength_training`` -> Modality.STRENGTH regardless of sport (Req 5.5)."""
    _label, modality, _is_indoor = detect_sport(sport, "strength_training")

    assert modality is Modality.STRENGTH


def test_strength_training_is_not_indoor() -> None:
    """``strength_training`` is strength modality but NOT indoor -- ambiguous (5.6)."""
    label, modality, is_indoor = detect_sport("training", "strength_training")

    assert label is Sport.WORKOUT
    assert modality is Modality.STRENGTH
    assert is_indoor is False


# --- Indoor flag: only verified machine-bound sub-sports (Req 5.6) ----------


@pytest.mark.parametrize("sub_sport", sorted(INDOOR_SUB_SPORTS))
def test_machine_bound_sub_sport_flags_indoor(sub_sport: str) -> None:
    """Every machine-bound indoor sub-sport flags ``is_indoor=True`` (Req 5.6)."""
    _label, _modality, is_indoor = detect_sport("running", sub_sport)

    assert is_indoor is True


def test_indoor_sub_sports_are_the_verified_machine_bound_set() -> None:
    """The indoor set is exactly the verified machine-bound strings (Req 5.6)."""
    assert (
        frozenset(
            {
                "treadmill",
                "spin",
                "indoor_cycling",
                "indoor_rowing",
                "indoor_walking",
                "indoor_running",
                "virtual_activity",
                "elliptical",
                "stair_climbing",
            }
        )
        == INDOOR_SUB_SPORTS
    )


_NOT_INDOOR_SUB_SPORTS: list[object] = [
    "lap_swimming",  # ambiguous: pool vs open water not asserted
    "strength_training",  # ambiguous: gym vs home not asserted
    "cardio_training",  # ambiguous
    "road",  # clearly outdoor
    "trail",
    "open_water",
    "not_a_real_sub_sport",
    "",
    None,
    123,  # defensively: a non-string value must not flag or raise
]


@pytest.mark.parametrize("sub_sport", _NOT_INDOOR_SUB_SPORTS)
def test_ambiguous_or_outdoor_sub_sport_is_not_indoor(sub_sport: object) -> None:
    """Ambiguous, outdoor, absent, or non-string sub-sports stay outdoor (Req 5.6)."""
    _label, _modality, is_indoor = detect_sport("running", sub_sport)  # type: ignore[arg-type]

    assert is_indoor is False


# --- Combined realistic activities (Req 5.1-5.6 together) -------------------

_COMBINED_CASES = [
    ("running", "treadmill", (Sport.RUN, Modality.RUN, True)),
    ("training", "strength_training", (Sport.WORKOUT, Modality.STRENGTH, False)),
    ("cycling", "indoor_cycling", (Sport.RIDE, Modality.BIKE, True)),
    ("cycling", "spin", (Sport.RIDE, Modality.BIKE, True)),
    ("running", "road", (Sport.RUN, Modality.RUN, False)),
    ("swimming", "lap_swimming", (Sport.SWIM, Modality.SWIM, False)),
    ("rowing", "indoor_rowing", (Sport.ROWING, Modality.OTHER, True)),
    (None, None, (Sport.WORKOUT, Modality.OTHER, False)),
]


@pytest.mark.parametrize(("sport", "sub_sport", "expected"), _COMBINED_CASES)
def test_combined_realistic_activities(
    sport: str | None,
    sub_sport: str | None,
    expected: tuple[Sport, Modality, bool],
) -> None:
    """A realistic (sport, sub_sport) pair yields the full expected triple (Req 5)."""
    assert detect_sport(sport, sub_sport) == expected


def test_detect_sport_returns_a_three_tuple() -> None:
    """The return shape is exactly ``(Sport, Modality, bool)`` (design contract)."""
    result = detect_sport("running", "treadmill")

    assert isinstance(result, tuple)
    assert len(result) == 3
    label, modality, is_indoor = result
    assert isinstance(label, Sport)
    assert isinstance(modality, Modality)
    assert isinstance(is_indoor, bool)
