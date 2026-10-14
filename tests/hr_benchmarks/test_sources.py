from __future__ import annotations

import dataclasses

import pytest

from fitdocs.benchmarks import BenchmarkKind
from fitdocs.citation import Citation, CitedConstant, FitdocsChoice, VerificationStatus
from fitdocs.hr_benchmarks import sources
from fitdocs.hr_benchmarks.types import HrMethod

TABLE = {
    "RESTING_WINDOW_DAYS": (28, "resting_hr_baseline_choice"),
    "RESTING_MIN_VALUES": (14, "resting_hr_baseline_choice"),
    "RESTING_STEP_BPM": (3, "resting_hr_timeline_choice"),
    "RESTING_CONFIRM_DAYS": (14, "resting_hr_timeline_choice"),
    "MAX_PLAUSIBLE_LOW_BPM": (30, "max_hr_sample_rejection_choice"),
    "MAX_PLAUSIBLE_HIGH_BPM": (230, "max_hr_sample_rejection_choice"),
    "MAX_RATE_BPM_PER_S": (10, "max_hr_sample_rejection_choice"),
    "MAX_GAP_S": (10, "max_hr_sustained_peak_choice"),
    "MAX_PEAK_WINDOW_S": (30, "max_hr_sustained_peak_choice"),
    "MAX_WINDOW_DAYS": (365, "max_hr_recency_choice"),
    "MAX_TOP_SESSIONS": (3, "max_hr_recency_choice"),
    "MAX_STEP_BPM": (2, "max_hr_timeline_choice"),
    "ROUNDING_HALF_OFFSET": (0.5, "hr_rounding_choice"),
}


@pytest.mark.parametrize("name", TABLE)
def test_constant_table(name: str) -> None:
    constant = getattr(sources, name)
    assert (constant.name, constant.value, type(constant.value)) == (
        name.lower(),
        TABLE[name][0],
        type(TABLE[name][0]),
    )


@pytest.mark.parametrize("name", TABLE)
def test_constant_governing_choice(name: str) -> None:
    constant = getattr(sources, name)
    assert isinstance(constant.source, FitdocsChoice)
    assert constant.source.key == TABLE[name][1]
    assert constant.source.verification is VerificationStatus.FITDOCS_MEASURED


@pytest.mark.parametrize("name", TABLE)
def test_no_unconsulted_corroborators(name: str) -> None:
    assert getattr(sources, name).corroborators == ()


def test_constant_sources_table() -> None:
    assert tuple(getattr(sources, name) for name in TABLE) == sources.CONSTANT_SOURCES


def test_all_declared_constants_in_table() -> None:
    assert {
        name
        for name, value in vars(sources).items()
        if isinstance(value, CitedConstant)
    } == set(TABLE)


def test_shared_choice_groups() -> None:
    groups: dict[str, list[FitdocsChoice]] = {}
    for name, (_, key) in TABLE.items():
        groups.setdefault(key, []).append(getattr(sources, name).source)
    assert {
        key: len({id(source) for source in group}) for key, group in groups.items()
    } == {key: 1 for key in groups}


@pytest.mark.parametrize(
    ("name", "kind", "method", "key", "step", "days"),
    [
        (
            "RESTING_RULE",
            BenchmarkKind.RESTING_HR_BPM,
            HrMethod.RESTING_HR_SERIES_MEDIAN,
            "resting_hr_timeline_choice",
            3,
            14,
        ),
        (
            "MAX_RULE",
            BenchmarkKind.MAX_HR_BPM,
            HrMethod.MAX_HR_SUSTAINED_PEAK,
            "max_hr_timeline_choice",
            2,
            1,
        ),
    ],
)
def test_kind_rules(
    name: str, kind: BenchmarkKind, method: HrMethod, key: str, step: int, days: int
) -> None:
    assert dataclasses.astuple(getattr(sources, name)) == (
        kind,
        method,
        key,
        step,
        days,
    )


def test_empty_blocked_citations() -> None:
    assert frozenset() == sources.BLOCKED_CITATIONS


@pytest.mark.parametrize("key", sorted({key for _, key in TABLE.values()}))
@pytest.mark.parametrize("field_name", ["justification", "search_basis", "measurement"])
def test_choice_record_details(key: str, field_name: str) -> None:
    choice = next(
        getattr(sources, name).source
        for name, (_, source_key) in TABLE.items()
        if source_key == key
    )
    detail = getattr(choice, field_name)
    assert isinstance(detail, str) and bool(detail.strip())


def test_no_unconsulted_citations() -> None:
    assert not any(isinstance(value, Citation) for value in vars(sources).values())
