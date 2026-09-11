"""Pins for `fitdocs.performance.types` (design: PerformanceTypes, Req 5.10,
7.3, 7.4).
"""

from __future__ import annotations

import dataclasses
import typing
from datetime import date

import pytest

import fitdocs.performance as performance
from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.channels.types import InsufficiencyReason
from fitdocs.performance.types import (
    DeclineReason,
    DerivationDeclined,
    DerivationMethod,
    DerivationOutcome,
    DerivedBenchmark,
)


def test_derivation_method_has_exactly_four_pairwise_distinct_members() -> None:
    members = list(DerivationMethod)
    assert len(members) == 4
    values = {m.value for m in members}
    assert len(values) == 4  # pairwise distinct, not just four names
    assert values == {
        "riegel_race_equivalence",
        "sustained_effort_mean_hr",
        "time_trial_mean_power",
        "twenty_minute_power_factor",
    }


def test_decline_reason_has_exactly_eleven_pairwise_distinct_members() -> None:
    members = list(DeclineReason)
    assert len(members) == 11
    values = {m.value for m in members}
    assert len(values) == 11  # pairwise distinct, not just eleven names
    assert values == {
        "sport_not_covered",
        "effort_kind_not_used",
        "undated_document",
        "missing_input",
        "outside_validity_window",
        "effort_span_mismatch",
        "method_unverified",
        "superseded_by_recorded",
        "stream_absent",
        "stream_coverage",
        "too_short",
    }


def test_shared_decline_reasons_equal_insufficiency_reasons_by_value() -> None:
    # Each shared member's *string value* must equal the real upstream
    # enumeration's value -- not merely exist under the same name.
    assert DeclineReason.STREAM_ABSENT.value == InsufficiencyReason.STREAM_ABSENT.value
    assert (
        DeclineReason.STREAM_COVERAGE.value == InsufficiencyReason.STREAM_COVERAGE.value
    )
    assert DeclineReason.TOO_SHORT.value == InsufficiencyReason.TOO_SHORT.value


def test_from_insufficiency_maps_every_shared_verdict_by_identical_value() -> None:
    shared = {
        InsufficiencyReason.STREAM_ABSENT: DeclineReason.STREAM_ABSENT,
        InsufficiencyReason.STREAM_COVERAGE: DeclineReason.STREAM_COVERAGE,
        InsufficiencyReason.TOO_SHORT: DeclineReason.TOO_SHORT,
    }
    for verdict, expected in shared.items():
        mapped = DeclineReason.from_insufficiency(verdict)
        assert mapped is expected
        assert mapped.value == verdict.value


def test_from_insufficiency_rejects_every_non_shared_verdict() -> None:
    non_shared = set(InsufficiencyReason) - {
        InsufficiencyReason.STREAM_ABSENT,
        InsufficiencyReason.STREAM_COVERAGE,
        InsufficiencyReason.TOO_SHORT,
    }
    # Confirm the decoy set is actually non-empty before relying on it.
    assert non_shared == {
        InsufficiencyReason.NO_BENCHMARK,
        InsufficiencyReason.BENCHMARKS_INCONSISTENT,
        InsufficiencyReason.MODEL_NOT_DEFINED,
        InsufficiencyReason.NOT_COMPUTABLE,
    }
    for verdict in non_shared:
        with pytest.raises(ValueError):
            DeclineReason.from_insufficiency(verdict)


def test_from_insufficiency_is_exhaustively_decided_over_every_member() -> None:
    # Sweep the *entire* upstream enumeration: each member is either mapped
    # by identical value or rejected -- never falls through silently. This
    # is what makes a future member added upstream redden here.
    seen_mapped = 0
    seen_rejected = 0
    for verdict in InsufficiencyReason:
        try:
            mapped = DeclineReason.from_insufficiency(verdict)
        except ValueError:
            seen_rejected += 1
            continue
        assert mapped.value == verdict.value
        seen_mapped += 1
    assert seen_mapped == 3
    assert seen_rejected == 4


def test_derived_benchmark_is_frozen_and_rejects_attribute_assignment() -> None:
    benchmark = DerivedBenchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=170.0,
        measured_on=date(2026, 1, 1),
        method=DerivationMethod.SUSTAINED_EFFORT_MEAN_HR,
        citation_key="banister_1975",
        inputs="mean hr over 42:00",
        note="",
        document="workouts/2026-01-01-run.md",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        benchmark.value = 999.0  # type: ignore[misc]
    # The mutation must not have taken effect even partway.
    assert benchmark.value == 170.0


def test_derived_benchmark_field_order() -> None:
    fields = [f.name for f in dataclasses.fields(DerivedBenchmark)]
    assert fields == [
        "kind",
        "discipline",
        "value",
        "measured_on",
        "method",
        "citation_key",
        "inputs",
        "note",
        "document",
    ]


def test_derivation_declined_field_order_and_defaults() -> None:
    fields = [f.name for f in dataclasses.fields(DerivationDeclined)]
    assert fields == ["kind", "method", "reason", "detail", "observed", "required"]
    declined = DerivationDeclined(
        kind=BenchmarkKind.LTHR_BPM,
        method=None,
        reason=DeclineReason.UNDATED_DOCUMENT,
        detail="no parseable date",
    )
    assert declined.observed is None
    assert declined.required is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        declined.detail = "mutated"  # type: ignore[misc]
    # The mutation must not have taken effect even partway.
    assert declined.detail == "no parseable date"


def test_derivation_outcome_is_the_sealed_union_of_both_outcomes() -> None:
    assert typing.get_args(DerivationOutcome) == (DerivedBenchmark, DerivationDeclined)


def test_package_all_covers_exactly_the_published_names() -> None:
    # Disclosed task-4.3 edit (tasks.md 4.3 "Append the pass entry point to
    # the package's published names ... the one addition to that file after
    # 1.1"): this assertion's own pre-4.3 comment named 4.3 as the task that
    # would invalidate it. `derive_benchmarks` joins the set here, appended
    # last in `__init__.py`'s `__all__` -- the five pre-existing names and
    # their relative order are otherwise unchanged, which the trailing
    # positional check below proves directly (not merely the set check,
    # which cannot see an append-vs-insert difference).
    expected = {
        "DeclineReason",
        "DerivationDeclined",
        "DerivationMethod",
        "DerivationOutcome",
        "DerivedBenchmark",
        "derive_benchmarks",
    }
    assert set(performance.__all__) == expected
    # Every name in __all__ must actually resolve on the module (a real
    # getattr, not merely appearing in the list) and be the same object the
    # types module defines.
    from fitdocs.performance.engine import derive_benchmarks as _derive_benchmarks

    expected_objects = {
        "DeclineReason": DeclineReason,
        "DerivationDeclined": DerivationDeclined,
        "DerivationMethod": DerivationMethod,
        "DerivationOutcome": DerivationOutcome,
        "DerivedBenchmark": DerivedBenchmark,
        "derive_benchmarks": _derive_benchmarks,
    }
    for name in performance.__all__:
        assert getattr(performance, name) is expected_objects[name]
    assert list(performance.__all__)[:5] == [
        "DeclineReason",
        "DerivationDeclined",
        "DerivationMethod",
        "DerivationOutcome",
        "DerivedBenchmark",
    ]
    assert list(performance.__all__)[5] == "derive_benchmarks"
