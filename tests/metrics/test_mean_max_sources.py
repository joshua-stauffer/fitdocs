"""Pins mean-max duration and continuity choices as records, not literals."""

from __future__ import annotations

from fitdocs.citation import Citation, CitedConstant
from fitdocs.metrics import mean_max_sources as sources

EXPECTED_DURATIONS_S = (
    1,
    5,
    10,
    15,
    20,
    30,
    45,
    60,
    120,
    180,
    240,
    300,
    360,
    480,
    600,
    720,
    900,
    1200,
    1800,
    2400,
    2700,
    3600,
    5400,
    7200,
    10800,
    14400,
    18000,
    21600,
)
EXPECTED_DURATION_NAMES = (
    "mean_max_duration_1_s",
    "mean_max_duration_5_s",
    "mean_max_duration_10_s",
    "mean_max_duration_15_s",
    "mean_max_duration_20_s",
    "mean_max_duration_30_s",
    "mean_max_duration_45_s",
    "mean_max_duration_60_s",
    "mean_max_duration_120_s",
    "mean_max_duration_180_s",
    "mean_max_duration_240_s",
    "mean_max_duration_300_s",
    "mean_max_duration_360_s",
    "mean_max_duration_480_s",
    "mean_max_duration_600_s",
    "mean_max_duration_720_s",
    "mean_max_duration_900_s",
    "mean_max_duration_1200_s",
    "mean_max_duration_1800_s",
    "mean_max_duration_2400_s",
    "mean_max_duration_2700_s",
    "mean_max_duration_3600_s",
    "mean_max_duration_5400_s",
    "mean_max_duration_7200_s",
    "mean_max_duration_10800_s",
    "mean_max_duration_14400_s",
    "mean_max_duration_18000_s",
    "mean_max_duration_21600_s",
)


def test_duration_set_has_the_pinned_count_range_and_values() -> None:
    values = tuple(constant.value for constant in sources.MEAN_MAX_DURATIONS_S)
    names = tuple(constant.name for constant in sources.MEAN_MAX_DURATIONS_S)

    assert len(values) == 28
    assert tuple(sorted(values)) == EXPECTED_DURATIONS_S
    assert names == EXPECTED_DURATION_NAMES


def test_duration_set_is_strictly_ascending() -> None:
    values = tuple(constant.value for constant in sources.MEAN_MAX_DURATIONS_S)

    assert all(left < right for left, right in zip(values, values[1:], strict=False))


def test_constants_use_their_choice_records_by_identity() -> None:
    assert all(
        constant.source is sources.MEAN_MAX_DURATIONS_CHOICE
        for constant in sources.MEAN_MAX_DURATIONS_S
    )
    assert sources.MEAN_MAX_MAX_STEP_S.source is sources.MEAN_MAX_MAX_STEP_CHOICE
    assert sources.MEAN_MAX_MAX_STEP_S.value == 5.0
    assert sources.MEAN_MAX_MAX_STEP_S.name == "mean_max_max_step_s"


def test_choice_keys_match_the_records_contract() -> None:
    assert sources.MEAN_MAX_DURATIONS_CHOICE.key == "mean_max_durations_choice"
    assert sources.MEAN_MAX_MAX_STEP_CHOICE.key == "mean_max_max_step_choice"


def test_sources_collection_is_exactly_the_module_constants() -> None:
    module_constants = tuple(
        value for value in vars(sources).values() if isinstance(value, CitedConstant)
    )

    assert len(sources.MEAN_MAX_SOURCES) == 29
    assert len({constant.name for constant in sources.MEAN_MAX_SOURCES}) == 29
    assert len(module_constants) == 29
    assert {id(constant) for constant in sources.MEAN_MAX_SOURCES} == {
        id(constant) for constant in module_constants
    }
    assert (
        *sources.MEAN_MAX_DURATIONS_S,
        sources.MEAN_MAX_MAX_STEP_S,
    ) == sources.MEAN_MAX_SOURCES


def test_choices_have_justification_and_live_search_basis() -> None:
    choices = (
        sources.MEAN_MAX_DURATIONS_CHOICE,
        sources.MEAN_MAX_MAX_STEP_CHOICE,
    )
    assert all(choice.justification.strip() for choice in choices)
    assert all(choice.search_basis.strip() for choice in choices)
    assert all(choice.measurement is None for choice in choices)
    assert not any(isinstance(value, Citation) for value in vars(sources).values())


def test_records_module_does_not_name_reference_docs() -> None:
    from pathlib import Path

    module_text = Path(sources.__file__).read_text(encoding="utf-8")
    assert "docs/reference" not in module_text
