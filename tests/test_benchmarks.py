"""Unit tests for the benchmark value vocabulary (design: BenchmarkVocabulary).

Task 1.1 covers the quantity enum, the scope sets, the reserved athlete-wide
scope token, the integral-valued quantity set, the immutable ``Benchmark``
value, and the module's domain error type.

Task 1.2 adds the parser (``parse_benchmarks``) and its inverse serializer
(``benchmarks_to_document``): a table-driven validation matrix (one case per
rejection rule in Requirements 2.1-2.8) and a round-trip test.

Task 1.3 adds date-aware selection (``BenchmarkSet.applicable``) and undated
presence (``BenchmarkSet.has``) (design: BenchmarkSelection).

Task 1.4 adds the pure staleness computation (``benchmark_age``,
``BenchmarkAge``) (design: StalenessCalculation).
"""

from __future__ import annotations

import dataclasses
import math
from datetime import date, datetime, timedelta

import pytest

from fitdocs import Sport
from fitdocs.benchmarks import (
    ATHLETE_SCOPE,
    ATHLETE_SCOPED,
    DISCIPLINE_SCOPED,
    INTEGRAL_KINDS,
    Benchmark,
    BenchmarkAge,
    BenchmarkError,
    BenchmarkKind,
    BenchmarkSet,
    benchmark_age,
    benchmarks_to_document,
    parse_benchmarks,
)


def test_benchmark_kind_members() -> None:
    """The five required quantities are all present with their documented units."""
    assert BenchmarkKind.FTP_WATTS == "ftp_watts"
    assert BenchmarkKind.LTHR_BPM == "lthr_bpm"
    assert BenchmarkKind.THRESHOLD_PACE_S_PER_KM == "threshold_pace_s_per_km"
    assert BenchmarkKind.MAX_HR_BPM == "max_hr_bpm"
    assert BenchmarkKind.RESTING_HR_BPM == "resting_hr_bpm"


def test_scope_sets_partition_all_quantities() -> None:
    """Every quantity is scoped to exactly one of discipline or athlete-wide."""
    assert {
        BenchmarkKind.FTP_WATTS,
        BenchmarkKind.LTHR_BPM,
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
    } == DISCIPLINE_SCOPED
    assert {BenchmarkKind.MAX_HR_BPM, BenchmarkKind.RESTING_HR_BPM} == ATHLETE_SCOPED
    assert DISCIPLINE_SCOPED.isdisjoint(ATHLETE_SCOPED)
    assert set(BenchmarkKind) == DISCIPLINE_SCOPED | ATHLETE_SCOPED


def test_integral_kinds_are_the_bpm_quantities() -> None:
    """The whole-beat quantities (LTHR, max HR, resting HR) are integral."""
    assert {
        BenchmarkKind.LTHR_BPM,
        BenchmarkKind.MAX_HR_BPM,
        BenchmarkKind.RESTING_HR_BPM,
    } == INTEGRAL_KINDS


def test_no_sport_value_collides_with_reserved_athlete_scope_token() -> None:
    """The reserved athlete-wide scope token never collides with a real sport.

    This is the assertion the task text calls out explicitly: discipline
    values reuse the shipped :class:`fitdocs.Sport` vocabulary, and the
    reserved token must be distinguishable from every one of them.
    """
    assert all(sport.value != ATHLETE_SCOPE for sport in Sport)
    assert all(sport.value.lower() != ATHLETE_SCOPE for sport in Sport)


def test_benchmark_value_for_discipline_scoped_quantity() -> None:
    """A discipline-scoped benchmark carries its discipline, value, date and note."""
    benchmark = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=285.0,
        measured_on=date(2026, 3, 14),
        note="Stryd 9-minute test",
    )

    assert benchmark.kind == BenchmarkKind.FTP_WATTS
    assert benchmark.discipline == Sport.RUN
    assert benchmark.value == 285.0
    assert benchmark.measured_on == date(2026, 3, 14)
    assert benchmark.note == "Stryd 9-minute test"


def test_benchmark_value_for_athlete_scoped_quantity() -> None:
    """An athlete-scoped benchmark carries ``discipline=None`` and an optional note."""
    benchmark = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190.0,
        measured_on=date(2025, 11, 9),
    )

    assert benchmark.kind == BenchmarkKind.MAX_HR_BPM
    assert benchmark.discipline is None
    assert benchmark.value == 190.0
    assert benchmark.measured_on == date(2025, 11, 9)
    assert benchmark.note is None


def test_benchmark_applies_from_defaults_to_none() -> None:
    """Amendment 1: ``applies_from`` is trailing and defaulted, so every
    existing keyword construction (with no ``applies_from`` argument at all)
    is unchanged.
    """
    benchmark = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=285.0,
        measured_on=date(2026, 3, 14),
    )

    assert benchmark.applies_from is None


def test_benchmark_applies_from_can_be_set_explicitly() -> None:
    """``applies_from`` accepts an explicit date distinct from ``measured_on``."""
    benchmark = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250.0,
        measured_on=date(2026, 9, 10),
        applies_from=date(2019, 3, 4),
    )

    assert benchmark.applies_from == date(2019, 3, 4)


def test_benchmark_is_immutable() -> None:
    """``Benchmark`` is a frozen value object."""
    benchmark = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=48.0,
        measured_on=date(2025, 1, 1),
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        benchmark.value = 50.0  # type: ignore[misc]


def test_benchmark_error_is_a_plain_domain_error() -> None:
    """``BenchmarkError`` is the module's own domain error type."""
    assert issubclass(BenchmarkError, Exception)
    err = BenchmarkError("bad value")
    assert str(err) == "bad value"


# ---------------------------------------------------------------------------
# Task 1.2: parse_benchmarks / benchmarks_to_document
# ---------------------------------------------------------------------------


def test_absent_benchmarks_region_yields_empty_set() -> None:
    """An `athlete.toml` with no ``[benchmarks]`` table parses to an empty set."""
    result = parse_benchmarks({"ftp_watts": 250})

    assert result == BenchmarkSet(entries=())


def test_empty_document_yields_empty_set() -> None:
    """A wholly empty decoded document also yields an empty set."""
    assert parse_benchmarks({}) == BenchmarkSet(entries=())


def test_unrecognized_keys_inside_an_entry_are_ignored() -> None:
    """An extra key inside an entry table is ignored, not rejected (1.10)."""
    document = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {
                        "value": 285,
                        "measured_on": date(2026, 3, 14),
                        "note": "Stryd test",
                        "some_future_key": "ignored",
                    }
                ]
            }
        }
    }

    result = parse_benchmarks(document)

    assert result == BenchmarkSet(
        entries=(
            Benchmark(
                kind=BenchmarkKind.FTP_WATTS,
                discipline=Sport.RUN,
                value=285,
                measured_on=date(2026, 3, 14),
                note="Stryd test",
            ),
        )
    )


def test_unrecognized_quantity_name_is_ignored_for_forward_compatibility() -> None:
    """A future quantity name under a recognized scope is ignored, not rejected."""
    document = {
        "benchmarks": {
            "run": {"future_quantity": [{"value": 1, "measured_on": date(2026, 1, 1)}]}
        }
    }

    result = parse_benchmarks(document)

    assert result == BenchmarkSet(entries=())


def _entry(scope: str, kind: str, **fields: object) -> dict[str, object]:
    return {"benchmarks": {scope: {kind: [dict(fields)]}}}


# Each case: (label, document, expected substrings that must all appear in the
# raised message -- proving it names the offending discipline/quantity/value).
REJECTION_CASES: list[tuple[str, dict[str, object], tuple[str, ...]]] = [
    (
        "missing_value",
        _entry("run", "ftp_watts", measured_on=date(2026, 1, 1)),
        ("run", "ftp_watts"),
    ),
    (
        "string_value",
        _entry("run", "ftp_watts", value="two-fifty", measured_on=date(2026, 1, 1)),
        ("run", "ftp_watts", "two-fifty"),
    ),
    (
        "boolean_value",
        _entry("run", "ftp_watts", value=True, measured_on=date(2026, 1, 1)),
        ("run", "ftp_watts"),
    ),
    (
        "zero_value",
        _entry("run", "ftp_watts", value=0, measured_on=date(2026, 1, 1)),
        ("run", "ftp_watts", "0"),
    ),
    (
        "negative_value",
        _entry("run", "ftp_watts", value=-10, measured_on=date(2026, 1, 1)),
        ("run", "ftp_watts", "-10"),
    ),
    (
        "nan_value",
        _entry("run", "ftp_watts", value=math.nan, measured_on=date(2026, 1, 1)),
        ("run", "ftp_watts"),
    ),
    (
        "fractional_bpm_value",
        _entry("athlete", "max_hr_bpm", value=190.5, measured_on=date(2026, 1, 1)),
        ("athlete", "max_hr_bpm", "190.5"),
    ),
    (
        "missing_measured_on",
        _entry("run", "ftp_watts", value=250),
        ("run", "ftp_watts"),
    ),
    (
        "non_date_measured_on",
        _entry("run", "ftp_watts", value=250, measured_on="2026-01-01"),
        ("run", "ftp_watts"),
    ),
    (
        "datetime_measured_on_rejected_even_though_it_subclasses_date",
        _entry(
            "run", "ftp_watts", value=250, measured_on=datetime(2026, 1, 1, 0, 0, 0)
        ),
        ("run", "ftp_watts"),
    ),
    (
        "unrecognized_discipline_table",
        # Athlete-scoped quantity (max_hr_bpm), not discipline-scoped: if 2.5's
        # own rejection in `_resolve_scope` were ever deleted, the entry would
        # resolve to the athlete scope and `_check_scope`'s 2.6 rule (which
        # only fires for a *scope/kind* mismatch) would have nothing to
        # object to, so this case would only fail if 2.5 itself still raises.
        _entry("unicycle", "max_hr_bpm", value=190, measured_on=date(2026, 1, 1)),
        ("unicycle", "recognized names", "run"),
    ),
    (
        "discipline_scoped_quantity_under_athlete_scope",
        _entry(ATHLETE_SCOPE, "ftp_watts", value=250, measured_on=date(2026, 1, 1)),
        ("ftp_watts", ATHLETE_SCOPE),
    ),
    (
        "athlete_scoped_quantity_under_a_discipline",
        _entry("run", "max_hr_bpm", value=190, measured_on=date(2026, 1, 1)),
        ("max_hr_bpm", ATHLETE_SCOPE),
    ),
    (
        "scalar_where_array_of_tables_belongs",
        {"benchmarks": {"run": {"ftp_watts": 250}}},
        ("run", "ftp_watts"),
    ),
    (
        "non_table_element_inside_array_of_tables",
        # The array itself is well-formed (a list), but one of its elements is
        # a scalar rather than a table (design.md Implementation Notes: "A
        # non-list at that path, or a non-table element, raises with the
        # offending path (2.8)").
        {"benchmarks": {"run": {"ftp_watts": [250]}}},
        ("run", "ftp_watts[0]"),
    ),
    (
        "non_string_note",
        _entry("run", "ftp_watts", value=250, measured_on=date(2026, 1, 1), note=7),
        ("run", "ftp_watts", "note"),
    ),
    (
        # Amendment 1 (1.12, 2.11): applies_from must be a bare date, held to
        # exactly measured_on's strictness -- a datetime (which subclasses
        # date) is rejected even though a looser isinstance check would pass
        # it, mirroring the existing "datetime_measured_on_rejected" case.
        "datetime_applies_from_rejected_even_though_it_subclasses_date",
        _entry(
            "run",
            "ftp_watts",
            value=250,
            measured_on=date(2026, 9, 10),
            applies_from=datetime(2019, 3, 4, 0, 0, 0),
        ),
        ("run", "ftp_watts", "applies_from"),
    ),
    (
        # Amendment 1 (1.12, 2.11), round-6 remediation: a quoted ISO date --
        # the realistic hand-edit mistake, and the value `non_date_measured_on`
        # above feeds -- is rejected for applies_from too. Without this case
        # a coercion inserted ahead of the bare-date check (`raw =
        # date.fromisoformat(raw)` for a str) left the suite green.
        "non_date_applies_from_string",
        _entry(
            "run",
            "ftp_watts",
            value=250,
            measured_on=date(2026, 9, 10),
            applies_from="2019-03-04",
        ),
        ("run", "ftp_watts", "applies_from", "2019-03-04"),
    ),
    (
        # Same rule, a non-str non-date value: a bare year integer.
        "non_date_applies_from_int",
        _entry(
            "run",
            "ftp_watts",
            value=250,
            measured_on=date(2026, 9, 10),
            applies_from=2019,
        ),
        ("run", "ftp_watts", "applies_from", "2019"),
    ),
    (
        # Amendment 1 (1.12, 2.11): applies_from after measured_on is
        # rejected -- the field may only reach backward in time, never
        # forward past the measurement it is declared on.
        "applies_from_after_measured_on_rejected",
        _entry(
            "run",
            "ftp_watts",
            value=250,
            measured_on=date(2026, 9, 10),
            applies_from=date(2026, 9, 11),
        ),
        ("run", "ftp_watts", "applies_from"),
    ),
    (
        # Amendment 1 (1.12, 2.11), round-3 remediation: the same
        # after-measured_on rejection, but on an *athlete-scoped* entry
        # (discipline=None) -- 2.11 applies to any benchmark entry, not only
        # a discipline-scoped one. Round-3 found every applies_from fixture
        # in this file used Sport.RUN/Sport.RIDE; this closes that gap for
        # the rejection layer.
        "athlete_scoped_applies_from_after_measured_on_rejected",
        _entry(
            ATHLETE_SCOPE,
            "max_hr_bpm",
            value=190,
            measured_on=date(2026, 6, 1),
            applies_from=date(2026, 6, 2),
        ),
        (ATHLETE_SCOPE, "max_hr_bpm", "applies_from"),
    ),
    (
        "scalar_where_scope_table_belongs",
        {"benchmarks": {"run": 250}},
        ("run",),
    ),
    (
        "scalar_where_benchmarks_table_belongs",
        {"benchmarks": 250},
        ("benchmarks",),
    ),
]


@pytest.mark.parametrize(
    "document, expected_substrings",
    [case[1:] for case in REJECTION_CASES],
    ids=[case[0] for case in REJECTION_CASES],
)
def test_parse_benchmarks_rejection_matrix(
    document: dict[str, object], expected_substrings: tuple[str, ...]
) -> None:
    """Every malformed shape in Requirement 2 is rejected with a message
    naming the offending discipline, quantity, or value."""
    with pytest.raises(BenchmarkError) as excinfo:
        parse_benchmarks(document)

    message = str(excinfo.value)
    for substring in expected_substrings:
        assert substring in message, f"expected {substring!r} in message: {message!r}"


def test_duplicate_measurement_date_is_rejected() -> None:
    """Two entries sharing discipline, quantity and measured_on are rejected."""
    document = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {"value": 250, "measured_on": date(2026, 1, 1)},
                    {"value": 260, "measured_on": date(2026, 1, 1)},
                ]
            }
        }
    }

    with pytest.raises(BenchmarkError) as excinfo:
        parse_benchmarks(document)

    message = str(excinfo.value)
    assert "run" in message
    assert "ftp_watts" in message
    assert "2026-01-01" in message


def test_duplicate_measurement_date_does_not_choose_one_entry() -> None:
    """A duplicate-date rejection is a hard failure, not a silent pick of one entry."""
    document = {
        "benchmarks": {
            "athlete": {
                "max_hr_bpm": [
                    {"value": 190, "measured_on": date(2025, 6, 1)},
                    {"value": 192, "measured_on": date(2025, 6, 1)},
                ]
            }
        }
    }

    with pytest.raises(BenchmarkError):
        parse_benchmarks(document)


def test_duplicate_measurement_date_is_rejected_even_with_distinct_applies_from() -> (
    None
):
    """Round-4 remediation: the duplicate-key rule stays
    ``(discipline, kind, measured_on)`` -- an ``applies_from`` value is not
    part of the key. Two entries sharing discipline, quantity and
    ``measured_on`` are rejected even when their ``applies_from`` values
    differ, which would falsely disambiguate them under a widened key of
    ``(discipline, kind, measured_on, applies_from)``.
    """
    applies_from_a = date(2016, 2, 3)
    applies_from_b = date(2017, 5, 6)
    # Reachability: the two applies_from values genuinely differ, so a
    # widened key would treat these as two distinct entries rather than a
    # duplicate.
    assert applies_from_a != applies_from_b

    document = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {
                        "value": 245,
                        "measured_on": date(2026, 7, 4),
                        "applies_from": applies_from_a,
                    },
                    {
                        "value": 255,
                        "measured_on": date(2026, 7, 4),
                        "applies_from": applies_from_b,
                    },
                ]
            }
        }
    }

    with pytest.raises(BenchmarkError) as excinfo:
        parse_benchmarks(document)

    message = str(excinfo.value)
    assert "run" in message
    assert "ftp_watts" in message
    assert "2026-07-04" in message


def test_lowercase_discipline_table_is_accepted() -> None:
    """A hand-written lowercase discipline table (matching the design's own
    physical data model example, e.g. ``[[benchmarks.run.ftp_watts]]``) is
    accepted and resolved to the ``Sport`` vocabulary -- ambiguity 1's decision:
    hand-editability wins, the parser is case-insensitive on the scope token."""
    document = {
        "benchmarks": {
            "run": {"ftp_watts": [{"value": 285, "measured_on": date(2026, 3, 14)}]}
        }
    }

    result = parse_benchmarks(document)

    assert result.entries == (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=285,
            measured_on=date(2026, 3, 14),
        ),
    )


def test_uppercase_sport_value_discipline_table_is_also_accepted() -> None:
    """The parser is case-insensitive both ways: the shipped ``Sport.value``
    spelling (``"Run"``) is also accepted, not only the lowercase form."""
    document = {
        "benchmarks": {
            "Run": {"ftp_watts": [{"value": 285, "measured_on": date(2026, 3, 14)}]}
        }
    }

    result = parse_benchmarks(document)

    assert result.entries[0].discipline == Sport.RUN


def test_integral_kind_value_is_stored_as_int() -> None:
    """A whole-beat quantity's accepted value is stored as ``int`` -- ambiguity
    2's decision -- so the serializer never emits a synthetic ``.0`` the user
    did not write.

    The fixture supplies ``190.0`` (a whole *float*), not the already-``int``
    ``190`` -- only a float input distinguishes a parser that actually
    converts to ``int`` from one that returns the raw value unchanged. A
    second entry with the plain ``int`` form ``190`` is kept alongside it
    (on a distinct ``measured_on`` to avoid the natural-key duplicate
    check) so both accepted spellings stay covered.
    """
    document = {
        "benchmarks": {
            "athlete": {
                "max_hr_bpm": [
                    {"value": 190.0, "measured_on": date(2025, 11, 9)},
                    {"value": 190, "measured_on": date(2025, 11, 16)},
                ]
            }
        }
    }

    result = parse_benchmarks(document)

    assert result.entries[0].value == 190
    assert isinstance(result.entries[0].value, int)
    assert not isinstance(result.entries[0].value, bool)

    assert result.entries[1].value == 190
    assert isinstance(result.entries[1].value, int)
    assert not isinstance(result.entries[1].value, bool)


def test_non_integral_kind_accepts_a_float_value() -> None:
    """A non-integral quantity (threshold pace) accepts a float value unchanged."""
    document = {
        "benchmarks": {
            "run": {
                "threshold_pace_s_per_km": [
                    {"value": 255.0, "measured_on": date(2026, 3, 14)}
                ]
            }
        }
    }

    result = parse_benchmarks(document)

    assert result.entries[0].value == 255.0


def test_benchmarks_to_document_groups_by_scope_and_quantity_sorted_by_date() -> None:
    """The serializer emits entries grouped by scope/quantity, date-ascending."""
    entries = (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=285,
            measured_on=date(2026, 3, 14),
            note="Stryd 9-minute test",
        ),
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=262,
            measured_on=date(2024, 5, 2),
            note="Apple Watch native power",
        ),
        Benchmark(
            kind=BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=190,
            measured_on=date(2025, 11, 9),
        ),
    )

    document = benchmarks_to_document(entries)

    benchmarks = document["benchmarks"]
    assert isinstance(benchmarks, dict)
    run_ftp = benchmarks["run"]["ftp_watts"]
    assert [entry["measured_on"] for entry in run_ftp] == [
        date(2024, 5, 2),
        date(2026, 3, 14),
    ]
    assert benchmarks[ATHLETE_SCOPE]["max_hr_bpm"][0]["value"] == 190


def test_parser_accepts_applies_from_on_an_entry() -> None:
    """Amendment 1 (1.12): a valid ``applies_from`` on an entry is accepted
    and stored on the resulting ``Benchmark``.
    """
    document = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {
                        "value": 250,
                        "measured_on": date(2026, 9, 10),
                        "applies_from": date(2019, 3, 4),
                    }
                ]
            }
        }
    }

    result = parse_benchmarks(document)

    assert result.entries[0].applies_from == date(2019, 3, 4)


def test_parser_accepts_applies_from_equal_to_measured_on() -> None:
    """``applies_from == measured_on`` is accepted, not rejected as "after"."""
    document = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {
                        "value": 250,
                        "measured_on": date(2026, 9, 10),
                        "applies_from": date(2026, 9, 10),
                    }
                ]
            }
        }
    }

    result = parse_benchmarks(document)

    assert result.entries[0].applies_from == date(2026, 9, 10)


def test_parser_accepts_applies_from_on_an_athlete_scoped_entry() -> None:
    """Round-3 remediation (1.12, athlete-wide axis): a valid ``applies_from``
    on an *athlete-scoped* entry (``discipline=None``) is accepted and
    stored, exactly as for a discipline-scoped one -- 1.12 says "on any
    benchmark entry", not only a discipline-scoped entry.
    """
    document = {
        "benchmarks": {
            ATHLETE_SCOPE: {
                "max_hr_bpm": [
                    {
                        "value": 187,
                        "measured_on": date(2027, 2, 14),
                        "applies_from": date(2018, 5, 20),
                    }
                ]
            }
        }
    }

    result = parse_benchmarks(document)

    assert len(result.entries) == 1
    assert result.entries[0].kind == BenchmarkKind.MAX_HR_BPM
    assert result.entries[0].discipline is None
    assert result.entries[0].applies_from == date(2018, 5, 20)


def test_benchmarks_to_document_emits_applies_from_after_measured_on() -> None:
    """The serializer emits ``applies_from`` (after ``measured_on``) when
    present.
    """
    entries = (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=250,
            measured_on=date(2026, 9, 10),
            applies_from=date(2019, 3, 4),
        ),
    )

    document = benchmarks_to_document(entries)

    record = document["benchmarks"]["run"]["ftp_watts"][0]  # type: ignore[index]
    assert "applies_from" in record
    assert record["applies_from"] == date(2019, 3, 4)
    keys = list(record.keys())
    assert keys.index("measured_on") < keys.index("applies_from")


def test_benchmarks_to_document_omits_applies_from_when_absent() -> None:
    """The serializer omits the ``applies_from`` key entirely for an entry
    that has none -- it is never emitted as an explicit ``None``.
    """
    entries = (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=250,
            measured_on=date(2026, 9, 10),
        ),
    )

    document = benchmarks_to_document(entries)

    record = document["benchmarks"]["run"]["ftp_watts"][0]  # type: ignore[index]
    assert "applies_from" not in record


def test_benchmarks_to_document_emits_applies_from_for_athlete_scoped_entry() -> None:
    """Round-3 remediation (1.12, athlete-wide axis): the serializer also
    emits ``applies_from`` for an athlete-scoped entry (``discipline=None``),
    under the reserved ``athlete`` scope table, not only for a
    discipline-scoped one.
    """
    entries = (
        Benchmark(
            kind=BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=187,
            measured_on=date(2027, 2, 14),
            applies_from=date(2018, 5, 20),
        ),
    )

    document = benchmarks_to_document(entries)

    record = document["benchmarks"][ATHLETE_SCOPE]["max_hr_bpm"][0]  # type: ignore[index]
    assert "applies_from" in record
    assert record["applies_from"] == date(2018, 5, 20)


def test_benchmarks_to_document_omits_applies_from_for_athlete_scope_when_absent() -> (
    None
):
    """Companion to the omission test above for the athlete-wide scope: an
    athlete-scoped entry with no ``applies_from`` never gets one fabricated.
    """
    entries = (
        Benchmark(
            kind=BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=185,
            measured_on=date(2023, 3, 3),
        ),
    )

    document = benchmarks_to_document(entries)

    record = document["benchmarks"][ATHLETE_SCOPE]["max_hr_bpm"][0]  # type: ignore[index]
    assert "applies_from" not in record


def test_round_trip_parse_of_serialize_preserves_applies_from() -> None:
    """The round-trip property holds for an entry carrying ``applies_from``,
    alongside a second entry that carries none -- both survive
    parse(serialize(entries)).
    """
    entries = (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=250,
            measured_on=date(2026, 9, 10),
            applies_from=date(2019, 3, 4),
        ),
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=262,
            measured_on=date(2024, 5, 2),
        ),
    )
    original = BenchmarkSet(entries=entries)

    round_tripped = parse_benchmarks(benchmarks_to_document(list(entries)))

    assert set(round_tripped.entries) == set(original.entries)
    assert len(round_tripped.entries) == len(original.entries)


def test_round_trip_preserves_applies_from_equal_to_measured_on() -> None:
    """An entry whose ``applies_from`` equals its ``measured_on`` still
    round-trips ``applies_from`` -- the serializer must not treat the two
    dates being equal as a reason to omit the key (design BenchmarkVocabulary
    Amendment 1: "the round trip holds either way").
    """
    entries = (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=270.0,
            measured_on=date(2025, 7, 1),
            applies_from=date(2025, 7, 1),
        ),
    )

    document = benchmarks_to_document(entries)

    record = document["benchmarks"]["run"]["ftp_watts"][0]  # type: ignore[index]
    assert record["applies_from"] == record["measured_on"] == date(2025, 7, 1)

    round_tripped = parse_benchmarks(document)

    assert round_tripped.entries[0].applies_from == date(2025, 7, 1)


def test_round_trip_parse_of_serialize_equals_original_set() -> None:
    """``parse(serialize(entries)) == entries`` for a representative history."""
    entries = (
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=262,
            measured_on=date(2024, 5, 2),
            note="Apple Watch native power",
        ),
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=285,
            measured_on=date(2026, 3, 14),
            note="Stryd 9-minute test",
        ),
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RIDE,
            value=248,
            measured_on=date(2026, 2, 1),
        ),
        Benchmark(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            discipline=Sport.RUN,
            value=231.5,
            measured_on=date(2022, 4, 18),
            # Round-3 remediation (residual): closes the kind axis's last
            # gap -- no applies_from fixture anywhere in this file used
            # THRESHOLD_PACE_S_PER_KM before this. Value/dates chosen
            # pairwise-distinct from every other entry in this set and
            # elsewhere in the file.
            applies_from=date(2011, 9, 7),
        ),
        Benchmark(
            kind=BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=190,
            measured_on=date(2025, 11, 9),
            # Round-3 remediation (athlete-wide axis): applies_from on an
            # athlete-scoped entry must round-trip too, not only on a
            # discipline-scoped one.
            applies_from=date(2015, 4, 12),
        ),
        Benchmark(
            kind=BenchmarkKind.RESTING_HR_BPM,
            discipline=None,
            value=48,
            measured_on=date(2025, 1, 1),
            # Round-3 remediation: covers the *other* athlete-scoped kind so
            # both members of ATHLETE_SCOPED carry an applies_from fixture
            # somewhere in this file.
            applies_from=date(2010, 8, 3),
        ),
    )
    original = BenchmarkSet(entries=entries)

    document = benchmarks_to_document(list(entries))
    round_tripped = parse_benchmarks(document)

    # Order-independent: the parser and serializer are free to reorder by
    # scope/quantity/date, but the resulting *set* of entries must match.
    assert set(round_tripped.entries) == set(original.entries)
    # Guard the entry count as well as the set.
    assert len(round_tripped.entries) == len(original.entries)
    # Round-3 remediation: pin the athlete-scoped applies_from values
    # explicitly too, not only through set equality -- these assertions
    # read the field from the *re-parsed* entries directly, independent of
    # whatever `original` happens to carry, so they catch a parser or
    # serializer that silently drops `applies_from` even though the two
    # literal `original` entries below still carry it (built from literals,
    # not derived from the document under test).
    round_tripped_by_kind = {entry.kind: entry for entry in round_tripped.entries}
    assert round_tripped_by_kind[BenchmarkKind.MAX_HR_BPM].applies_from == date(
        2015, 4, 12
    )
    assert round_tripped_by_kind[BenchmarkKind.RESTING_HR_BPM].applies_from == date(
        2010, 8, 3
    )
    # Round-3 remediation (residual): pin THRESHOLD_PACE_S_PER_KM's
    # applies_from explicitly, both on the serialized document (key present,
    # equal to the literal date) and on the re-parsed entry -- not only
    # through the set-equality check above.
    pace_record = document["benchmarks"]["run"]["threshold_pace_s_per_km"][0]  # type: ignore[index]
    assert "applies_from" in pace_record
    assert pace_record["applies_from"] == date(2011, 9, 7)
    assert round_tripped_by_kind[
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    ].applies_from == date(2011, 9, 7)


# --- Task 1.3: date-aware selection and undated presence -------------------
#
# The maximality property that ``applicable`` must satisfy for every
# (kind, discipline, on) is exercised exhaustively by
# ``test_applicable_selects_the_date_maximal_qualifying_entry`` below; the
# example tests in this section document the rule's shape for a reader
# rather than proving it.

_RUN_FTP_EARLY = Benchmark(
    kind=BenchmarkKind.FTP_WATTS,
    discipline=Sport.RUN,
    value=260,
    measured_on=date(2024, 1, 1),
    note="Apple Watch baseline",
)
_RUN_FTP_LATE = Benchmark(
    kind=BenchmarkKind.FTP_WATTS,
    discipline=Sport.RUN,
    value=245,
    measured_on=date(2024, 7, 1),
    note="midseason retest",
)
_RUN_FTP_MID = Benchmark(
    kind=BenchmarkKind.FTP_WATTS,
    discipline=Sport.RUN,
    value=230,
    measured_on=date(2024, 6, 1),
    note="Apple Watch retest, after a layoff",
)
_RUN_FTP_FUTURE = Benchmark(
    kind=BenchmarkKind.FTP_WATTS,
    discipline=Sport.RUN,
    value=300,
    measured_on=date(2026, 1, 1),
    note="Stryd",
)
_RIDE_FTP_LATE = Benchmark(
    kind=BenchmarkKind.FTP_WATTS,
    discipline=Sport.RIDE,
    value=999,
    measured_on=date(2024, 7, 1),
    note="wrong discipline -- must never win",
)


def test_applicable_returns_the_latest_qualifying_entry() -> None:
    """3.1, 3.2: filters to ``measured_on <= on`` and picks the latest *date*,
    not the largest value.

    Four run-FTP entries are on file, with value order deliberately
    non-monotonic in date order (260, 245, 230, 300): the earliest
    (2024-01-01, 260), the correct answer (2024-07-01, 245), the mid one
    (2024-06-01, 230) and a future one (2026-01-01, 300, excluded by the
    date filter).
    """
    entries = BenchmarkSet(
        entries=(_RUN_FTP_EARLY, _RUN_FTP_LATE, _RUN_FTP_MID, _RUN_FTP_FUTURE)
    )

    result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )

    assert result is not None
    assert result.value == 245
    assert result.measured_on == date(2024, 7, 1)
    assert result.note == "midseason retest"


def test_applicable_same_day_measurement_applies() -> None:
    """A measurement dated the same day as the query date applies (3.1)."""
    entries = BenchmarkSet(entries=(_RUN_FTP_EARLY, _RUN_FTP_MID))

    result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 6, 1)
    )

    assert result is not None
    assert result.measured_on == date(2024, 6, 1)
    assert result.value == 230


def test_applicable_never_returns_a_later_dated_entry_than_the_query_date() -> None:
    """3.3: a later measurement never applies to an earlier activity.

    The only entry on file is dated after the query date, so an activity one
    day earlier must see nothing applicable -- not the later-measured entry.
    """
    entries = BenchmarkSet(entries=(_RUN_FTP_MID,))

    result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 5, 31)
    )

    assert result is None


def test_applicable_ignores_entries_from_another_discipline() -> None:
    """No cross-discipline fallback: a later-dated entry in another
    discipline must never be preferred over an earlier-dated entry in the
    requested one, and a discipline with nothing on file returns ``None``
    rather than borrowing another discipline's value.
    """
    entries = BenchmarkSet(entries=(_RUN_FTP_EARLY, _RIDE_FTP_LATE))

    result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )

    assert result is not None
    assert result.value == 260
    assert result.discipline == Sport.RUN

    swim_result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.SWIM, on=date(2024, 8, 1)
    )
    assert swim_result is None


def test_applicable_ignores_entries_of_another_kind_in_the_same_scope() -> None:
    """Only the requested *quantity* qualifies, even within the same
    (discipline) scope. A later-dated entry of a different ``BenchmarkKind``
    must never be preferred over an earlier-dated entry of the requested
    kind.
    """
    run_ftp = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=240,
        measured_on=date(2024, 1, 1),
    )
    run_lthr = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=170,
        measured_on=date(2024, 6, 1),
    )
    entries = BenchmarkSet(entries=(run_ftp, run_lthr))

    result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )

    assert result is not None
    assert result.kind is BenchmarkKind.FTP_WATTS
    assert result.value == 240


def test_has_ignores_entries_of_another_kind_or_discipline() -> None:
    """3.5: ``has`` reports presence of the exact requested (kind,
    discipline), not merely that the set is non-empty.

    Also includes an athlete-wide entry of the *same kind* (``FTP_WATTS``
    with ``discipline=None``) alongside the run-scoped one, so that
    ``has(FTP_WATTS, discipline=RIDE)`` being false is not merely a
    consequence of no ``FTP_WATTS`` entry existing at all -- there is one,
    just in the wrong scope, and it must not satisfy the RIDE query either.
    """
    athlete_wide_ftp_decoy = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=None,
        value=999,
        measured_on=date(2024, 1, 1),
    )
    entries = BenchmarkSet(entries=(_RUN_FTP_EARLY, athlete_wide_ftp_decoy))

    assert entries.has(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True
    assert entries.has(BenchmarkKind.LTHR_BPM, discipline=Sport.RUN) is False
    assert entries.has(BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE) is False
    assert entries.has(BenchmarkKind.MAX_HR_BPM, discipline=None) is False


def test_applicable_all_future_history_returns_none_while_presence_stays_true() -> None:
    """3.3, 3.5: an all-future history yields no applicable benchmark, but
    ``has`` still reports the quantity is on file at all.
    """
    entries = BenchmarkSet(entries=(_RUN_FTP_FUTURE,))

    assert (
        entries.applicable(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 1, 1)
        )
        is None
    )
    assert entries.has(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


# --- Amendment 1: tier-2 (applies_from) selection -------------------------


def test_applicable_tier2_picks_earliest_measured_on_not_latest_applies_from() -> None:
    """3.10: when tier 1 is empty, tier 2 returns the entry measured
    *soonest after* the activity -- i.e. the smallest ``measured_on`` among
    the ``applies_from``-qualifying entries.

    Designed to defeat the plausible wrong rule "the entry with the latest
    ``applies_from``": entry A is measured later (2026-05-01) but declares
    the *later* applies_from (2020-06-01); entry B is measured earlier
    (2026-01-01) but declares the *earlier* applies_from (2020-01-01). So
    "earliest measured" (B) and "latest applies_from" (A) disagree, and the
    correct rule must select B.
    """
    entry_a = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=999,
        measured_on=date(2026, 5, 1),
        applies_from=date(2020, 6, 1),
    )
    entry_b = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=111,
        measured_on=date(2026, 1, 1),
        applies_from=date(2020, 1, 1),
    )
    entries = BenchmarkSet(entries=(entry_a, entry_b))
    on = date(2024, 1, 1)

    # Reachability: confirm tier 1 is genuinely empty for this query -- both
    # measured_on dates fall after `on`.
    assert entry_a.measured_on > on
    assert entry_b.measured_on > on
    # Reachability: confirm both entries' applies_from genuinely qualify.
    assert entry_a.applies_from is not None and entry_a.applies_from <= on
    assert entry_b.applies_from is not None and entry_b.applies_from <= on

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.value == 111
    assert result.measured_on == date(2026, 1, 1)
    # 3.11: the applies_from date accompanies the returned benchmark too.
    assert result.applies_from == date(2020, 1, 1)


def test_applicable_tier2_picks_earliest_measured_on_when_orders_disagree() -> None:
    """3.10: companion to
    ``test_applicable_tier2_picks_earliest_measured_on_not_latest_applies_from``,
    which needs a second fixture where ``measured_on`` order and
    ``applies_from`` order *disagree* rather than move together.

    In the sibling test, entry A (measured later, applies_from later) and
    entry B (measured earlier, applies_from earlier) move in the same
    direction: picking by ``min(measured_on)`` and picking by
    ``min(applies_from)`` both land on B, so that fixture alone cannot tell
    the correct rule (earliest ``measured_on``) apart from the wrong one
    (earliest ``applies_from``). Here entry C is measured *earlier*
    (2026-01-01) but declares the *later* applies_from (2020-06-01), and
    entry D is measured *later* (2026-05-01) but declares the *earlier*
    applies_from (2020-01-01) -- the two orders now disagree, so
    ``min(measured_on)`` (correct, selects C) and ``min(applies_from)``
    (wrong, would select D) diverge.
    """
    entry_c = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=333,
        measured_on=date(2026, 1, 1),
        applies_from=date(2020, 6, 1),
    )
    entry_d = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=444,
        measured_on=date(2026, 5, 1),
        applies_from=date(2020, 1, 1),
    )
    entries = BenchmarkSet(entries=(entry_c, entry_d))
    on = date(2024, 1, 1)

    # Reachability: tier 1 is genuinely empty, and both entries' applies_from
    # genuinely qualify.
    assert entry_c.measured_on > on
    assert entry_d.measured_on > on
    assert entry_c.applies_from is not None and entry_c.applies_from <= on
    assert entry_d.applies_from is not None and entry_d.applies_from <= on

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.value == 333
    assert result.measured_on == date(2026, 1, 1)


def test_applicable_tier2_never_leaks_across_discipline_or_kind() -> None:
    """3.10, 3.3 revised: tier 2 must filter to the requested ``(kind,
    discipline)`` exactly as tier 1 does -- a retroactive entry in another
    discipline, or of another kind in the requested discipline, must never
    be substituted when the requested ``(kind, discipline)`` has no entry
    on file at all.
    """
    ride_ftp_retroactive = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=222,
        measured_on=date(2026, 2, 1),
        applies_from=date(2020, 1, 1),
    )
    run_lthr_retroactive = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=150,
        measured_on=date(2026, 3, 1),
        applies_from=date(2020, 2, 1),
    )
    entries = BenchmarkSet(entries=(ride_ftp_retroactive, run_lthr_retroactive))
    on = date(2024, 1, 1)

    # Reachability: both decoys really do qualify for tier 2 in their own
    # (kind, discipline) -- proven by querying them directly -- so a `None`
    # result for the FTP/RUN query below cannot be explained by neither
    # decoy being retroactive at all.
    ride_result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, on=on
    )
    assert ride_result is not None
    assert ride_result.value == 222
    lthr_result = entries.applicable(
        BenchmarkKind.LTHR_BPM, discipline=Sport.RUN, on=on
    )
    assert lthr_result is not None
    assert lthr_result.value == 150

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is None


def test_applicable_tier2_boundary_applies_from_equal_to_on_is_inclusive() -> None:
    """3.10: "on or before" is inclusive at the tier-2 boundary too --
    ``applies_from == on`` qualifies, not only ``applies_from < on``.
    """
    entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=260,
        measured_on=date(2026, 1, 1),
        applies_from=date(2024, 1, 1),
    )
    entries = BenchmarkSet(entries=(entry,))
    on = date(2024, 1, 1)

    # Reachability: measured_on is after `on` (tier 1 empty) and
    # applies_from is exactly `on`, not before it.
    assert entry.measured_on > on
    assert entry.applies_from == on

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.value == 260


def test_applicable_tier2_selects_athlete_scoped_entry_with_applies_from() -> None:
    """Round-3 remediation (3.10, 3.3 revised, athlete-wide axis): tier 2
    resolves an athlete-scoped entry (``discipline=None``) exactly as it
    does a discipline-scoped one -- every existing tier-2 test in this file
    used ``Sport.RUN``/``Sport.RIDE``. A single query date between
    ``applies_from`` and ``measured_on`` exercises tier 2; a second query
    date on or after ``measured_on`` exercises tier 1 for the *same* entry,
    so both tiers stay live for this scope.
    """
    entry = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=187,
        measured_on=date(2027, 2, 14),
        applies_from=date(2018, 5, 20),
        note="lab test, retroactive",
    )
    entries = BenchmarkSet(entries=(entry,))
    tier2_on = date(2021, 6, 15)
    tier1_on = date(2027, 6, 1)

    # Reachability: tier 1 is genuinely empty at tier2_on (measured_on is
    # after it) and applies_from genuinely qualifies (on or before it).
    assert entry.measured_on > tier2_on
    assert entry.applies_from is not None and entry.applies_from <= tier2_on
    # Reachability for the tier-1 query: measured_on is on or before it.
    assert entry.measured_on <= tier1_on

    tier2_result = entries.applicable(
        BenchmarkKind.MAX_HR_BPM, discipline=None, on=tier2_on
    )
    tier1_result = entries.applicable(
        BenchmarkKind.MAX_HR_BPM, discipline=None, on=tier1_on
    )

    assert tier2_result is not None
    assert tier2_result.value == 187
    assert tier2_result.applies_from == date(2018, 5, 20)
    assert tier1_result is not None
    assert tier1_result.value == 187
    assert tier1_result.measured_on == date(2027, 2, 14)


def test_applicable_tier2_selects_threshold_pace_entry_with_applies_from() -> None:
    """Round-3 remediation (residual, kind axis): tier 2 resolves a
    ``THRESHOLD_PACE_S_PER_KM`` entry too -- no tier-2 test in this file
    used that kind before this. Mirrors
    ``test_applicable_tier2_selects_athlete_scoped_entry_with_applies_from``
    but for the discipline-scoped pace quantity, with value/dates
    pairwise-distinct from every other fixture in the file.
    """
    entry = Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=238.0,
        measured_on=date(2028, 1, 10),
        applies_from=date(2013, 7, 22),
    )
    entries = BenchmarkSet(entries=(entry,))
    on = date(2019, 11, 1)

    # Reachability: tier 1 is genuinely empty (measured_on is after `on`)
    # and applies_from genuinely qualifies (on or before `on`).
    assert entry.measured_on > on
    assert entry.applies_from is not None and entry.applies_from <= on

    result = entries.applicable(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM, discipline=Sport.RUN, on=on
    )

    assert result is not None
    assert result.value == 238.0
    assert result.applies_from == date(2013, 7, 22)


def test_applicable_tier2_not_applicable_for_athlete_scope_before_applies_from() -> (
    None
):
    """Round-3 remediation (3.10, athlete-wide axis): an athlete-scoped
    entry's ``applies_from`` that has not yet been reached does not
    qualify -- ``applicable`` reports ``None`` while ``has`` still reports
    presence, mirroring
    ``test_applicable_applies_from_after_query_date_is_not_applicable``
    (which uses a discipline-scoped entry) for the athlete-wide scope.
    """
    entry = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=187,
        measured_on=date(2027, 2, 14),
        applies_from=date(2018, 5, 20),
    )
    entries = BenchmarkSet(entries=(entry,))
    on = date(2015, 1, 1)

    # Reachability: both measured_on and applies_from fall after `on`, so
    # neither tier qualifies.
    assert entry.measured_on > on
    assert entry.applies_from is not None and entry.applies_from > on

    result = entries.applicable(BenchmarkKind.MAX_HR_BPM, discipline=None, on=on)

    assert result is None
    assert entries.has(BenchmarkKind.MAX_HR_BPM, discipline=None) is True


def test_applicable_tier2_repeated_calls_stay_equal_regardless_of_entry_order() -> None:
    """3.8: mirrors
    ``test_applicable_repeated_calls_stay_equal_regardless_of_entry_order``
    but exercises tier 2 specifically -- determinism there also rests on the
    parser's duplicate-key invariant, not on stored order, even though tier
    2 picks a *minimum* rather than tier 1's *maximum*. Two retroactive
    candidates with distinct ``measured_on`` so that ``retroactive[-1]`` and
    ``retroactive[0]`` disagree with each other and with the correct answer
    depending on stored order.
    """
    earlier_retroactive = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=210,
        measured_on=date(2024, 3, 1),
        applies_from=date(2020, 1, 1),
    )
    later_retroactive = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=220,
        measured_on=date(2024, 6, 1),
        applies_from=date(2020, 2, 1),
    )
    on = date(2023, 1, 1)
    forward = BenchmarkSet(entries=(earlier_retroactive, later_retroactive))
    reversed_ = BenchmarkSet(entries=(later_retroactive, earlier_retroactive))

    result_forward = forward.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on
    )
    result_reversed = reversed_.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on
    )

    assert result_forward == result_reversed
    # Literal anchor: without this, an implementation that returns None
    # unconditionally would still satisfy the self-compare above.
    assert result_forward is not None
    assert result_forward.value == 210
    assert result_forward.measured_on == date(2024, 3, 1)


def test_applicable_returns_applies_from_alongside_measured_on_and_note() -> None:
    """3.11: when ``applicable`` resolves a tier-2 entry, the returned
    ``Benchmark`` carries its ``applies_from`` (as well as its
    ``measured_on`` and ``note``) so a caller can report that the anchor
    was measured after the activity and applied by the athlete's
    declaration.
    """
    entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=date(2026, 9, 10),
        note="prompt answer",
        applies_from=date(2019, 3, 4),
    )
    entries = BenchmarkSet(entries=(entry,))
    on = date(2020, 1, 1)

    # Reachability: tier 1 is empty (measured_on is after `on`), tier 2
    # qualifies (applies_from is on or before `on`).
    assert entry.measured_on > on
    assert entry.applies_from is not None and entry.applies_from <= on

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.applies_from == date(2019, 3, 4)
    assert result.measured_on == date(2026, 9, 10)
    assert result.note == "prompt answer"
    # Whole-entry equality: the tier-2 path returns the stored entry with
    # every field intact, so a copy with any one field stripped is rejected
    # here even if the three field assertions above were later trimmed.
    assert result == entry


def test_applicable_tier1_entry_beats_a_closer_retroactive_entry() -> None:
    """3.10: a tier-1 entry (measured on or before ``on``) always wins over
    a tier-2 (retroactive) one, even when the retroactive entry's
    ``measured_on`` is calendar-closer to ``on`` than the tier-1 entry's.
    """
    tier1_entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=240,
        measured_on=date(2024, 1, 1),
    )
    retroactive_entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=999,
        measured_on=date(2024, 8, 15),
        applies_from=date(2020, 1, 1),
    )
    entries = BenchmarkSet(entries=(tier1_entry, retroactive_entry))
    on = date(2024, 8, 1)

    # Reachability: tier 1 genuinely has a qualifying entry, and the
    # retroactive entry really is measured closer to `on` than it.
    assert tier1_entry.measured_on <= on
    assert (retroactive_entry.measured_on - on).days < (
        on - tier1_entry.measured_on
    ).days

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.value == 240
    assert result.measured_on == date(2024, 1, 1)


def test_applicable_applies_from_after_query_date_is_not_applicable() -> None:
    """3.10, 3.5: an ``applies_from`` later than ``on`` does not qualify --
    ``applicable`` reports ``None``, but ``has`` still reports presence.
    """
    entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=date(2026, 5, 1),
        applies_from=date(2025, 1, 1),
    )
    entries = BenchmarkSet(entries=(entry,))
    on = date(2024, 1, 1)

    # Reachability: confirm applies_from really is after `on` and measured_on
    # really is after `on` too (so neither tier qualifies).
    assert entry.applies_from is not None and entry.applies_from > on
    assert entry.measured_on > on

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is None
    assert entries.has(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


def test_applicable_never_returns_an_entry_with_neither_qualifying_date() -> None:
    """3.10: an entry whose ``measured_on`` is after ``on`` and whose
    ``applies_from`` is either absent or also after ``on`` is never
    returned. Combines a no-``applies_from`` decoy and an
    ``applies_from``-too-late decoy alongside a genuinely retroactive entry,
    so the returned entry must be the retroactive one, not either decoy.
    """
    no_applies_from_decoy = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=901,
        measured_on=date(2026, 2, 1),
    )
    applies_from_too_late_decoy = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=902,
        measured_on=date(2026, 3, 1),
        applies_from=date(2025, 1, 1),
    )
    genuinely_retroactive = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=903,
        measured_on=date(2026, 4, 1),
        applies_from=date(2020, 1, 1),
    )
    entries = BenchmarkSet(
        entries=(
            no_applies_from_decoy,
            applies_from_too_late_decoy,
            genuinely_retroactive,
        )
    )
    on = date(2024, 1, 1)

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.value == 903


def test_applicable_applies_from_equal_to_measured_on_behaves_as_if_absent() -> None:
    """``applies_from == measured_on`` is accepted but changes nothing --
    ``applicable`` for a set holding such an entry returns exactly what it
    would for the same entry with no ``applies_from`` at all, at a query
    date on either side of ``measured_on``.
    """
    with_equal_applies_from = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=240,
        measured_on=date(2024, 6, 1),
        applies_from=date(2024, 6, 1),
    )
    without_applies_from = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=240,
        measured_on=date(2024, 6, 1),
    )
    set_with = BenchmarkSet(entries=(with_equal_applies_from,))
    set_without = BenchmarkSet(entries=(without_applies_from,))

    # Round-3 remediation (finding 2): anchor each iteration to a literal
    # verdict too, not only a self-referential compare between the two
    # sides -- a self-compare alone would still pass an `applicable` that
    # returned `None` unconditionally for both sets.
    expected_results: dict[date, bool] = {
        date(2024, 1, 1): False,  # before measured_on/applies_from: neither tier fires
        date(2024, 6, 1): True,  # on measured_on: tier 1 fires
        date(2024, 12, 1): True,  # after measured_on: tier 1 fires
    }

    for on, expect_result in expected_results.items():
        result_with = set_with.applicable(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on
        )
        result_without = set_without.applicable(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on
        )
        if expect_result:
            assert result_with is not None and result_with.value == 240
            assert result_without is not None and result_without.value == 240
        else:
            assert result_with is None
            assert result_without is None
        assert (result_with is None) == (result_without is None)
        if result_with is not None and result_without is not None:
            assert result_with.value == result_without.value
            assert result_with.measured_on == result_without.measured_on


def test_applicable_empty_history_returns_none_with_presence_false() -> None:
    """3.4, 3.5: nothing on file at all -- both queries report absence."""
    entries = BenchmarkSet(entries=())

    assert (
        entries.applicable(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 1, 1)
        )
        is None
    )
    assert entries.has(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is False


def test_has_ignores_dates_entirely() -> None:
    """3.5: presence is true even when nothing on file yet applies."""
    entries = BenchmarkSet(entries=(_RUN_FTP_FUTURE,))

    assert entries.has(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


def test_applicable_athlete_scoped_quantity_selects_by_date_too() -> None:
    """The same latest-qualifying-date rule applies to an athlete-scoped
    quantity (``discipline=None``), not only to discipline-scoped ones.

    Uses resting heart rate, with a value order deliberately non-monotonic
    in date order (48, 40, 44, 38): early (2024-01-01, 48), a dip
    (2024-06-01, 40), the correct answer (2024-07-01, 44) and a future
    entry (2026-01-01, 38) excluded by the date filter at
    ``on=2025-01-01``.
    """
    early = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=48,
        measured_on=date(2024, 1, 1),
    )
    dip = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=40,
        measured_on=date(2024, 6, 1),
    )
    late = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=44,
        measured_on=date(2024, 7, 1),
    )
    future = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=38,
        measured_on=date(2026, 1, 1),
    )
    entries = BenchmarkSet(entries=(dip, future, late, early))

    result = entries.applicable(
        BenchmarkKind.RESTING_HR_BPM, discipline=None, on=date(2025, 1, 1)
    )

    assert result is not None
    assert result.value == 44
    assert result.measured_on == date(2024, 7, 1)


def test_applicable_raises_when_discipline_scoped_kind_given_athlete_scope() -> None:
    """A scope that disagrees with the quantity is a programming error."""
    entries = BenchmarkSet(entries=(_RUN_FTP_EARLY,))

    with pytest.raises(ValueError, match="ftp_watts"):
        entries.applicable(
            BenchmarkKind.FTP_WATTS, discipline=None, on=date(2024, 8, 1)
        )


def test_applicable_raises_when_athlete_scoped_kind_given_a_discipline() -> None:
    """A scope that disagrees with the quantity is a programming error, the
    other direction: an athlete-wide quantity queried under a discipline.
    """
    entries = BenchmarkSet(entries=())

    with pytest.raises(ValueError, match="max_hr_bpm"):
        entries.applicable(
            BenchmarkKind.MAX_HR_BPM, discipline=Sport.RUN, on=date(2024, 8, 1)
        )


def test_has_raises_on_mismatched_scope_too() -> None:
    """The precondition check applies to ``has`` as well as ``applicable``."""
    entries = BenchmarkSet(entries=())

    with pytest.raises(ValueError, match="lthr_bpm"):
        entries.has(BenchmarkKind.LTHR_BPM, discipline=None)


def test_applicable_never_falls_back_to_athlete_wide_scope() -> None:
    """9.5: an athlete-wide entry on file must never satisfy a
    discipline-scoped FTP query -- there is no fallback path, only the
    precondition raise checked above and, absent that mismatch, an ordinary
    ``None`` for "no entry of this exact (kind, discipline)", or the RUN
    entry itself when one is also on file alongside the decoys.

    Three decoys are on file: an athlete-wide max-HR entry, a run-scoped
    LTHR entry, and an athlete-wide FTP entry dated later than the RUN
    entry below. The athlete-wide FTP entry is the scope shape Requirements
    3.4 and 9.5 name.
    """
    max_hr_decoy = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190,
        measured_on=date(2020, 1, 1),
    )
    lthr_decoy = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=170,
        measured_on=date(2024, 7, 1),
    )
    athlete_wide_ftp_decoy = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=None,
        value=999,
        measured_on=date(2024, 7, 15),
    )
    entries = BenchmarkSet(entries=(max_hr_decoy, lthr_decoy, athlete_wide_ftp_decoy))

    result = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )

    assert result is None

    # With a genuine RUN-scoped FTP entry also on file (earlier-dated than
    # the athlete-wide decoy), the query must resolve to that RUN entry --
    # not to the later-dated athlete-wide decoy.
    run_ftp = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=240,
        measured_on=date(2024, 1, 1),
    )
    entries_with_run = BenchmarkSet(
        entries=(max_hr_decoy, lthr_decoy, athlete_wide_ftp_decoy, run_ftp)
    )

    result_with_run = entries_with_run.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )

    assert result_with_run is not None
    assert result_with_run.discipline == Sport.RUN
    assert result_with_run.value == 240


def test_applicable_athlete_scoped_query_never_falls_back_to_another_kind() -> None:
    """The athlete-wide-scope counterpart of the test above: two different
    athlete-wide quantities on file, with the wrong one later-dated, must
    each resolve to their own kind rather than either bleeding into the
    other.
    """
    max_hr = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190,
        measured_on=date(2024, 1, 1),
    )
    resting_hr = Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=48,
        measured_on=date(2024, 6, 1),
    )
    entries = BenchmarkSet(entries=(max_hr, resting_hr))

    max_hr_result = entries.applicable(
        BenchmarkKind.MAX_HR_BPM, discipline=None, on=date(2024, 8, 1)
    )
    resting_hr_result = entries.applicable(
        BenchmarkKind.RESTING_HR_BPM, discipline=None, on=date(2024, 8, 1)
    )

    assert max_hr_result is not None
    assert max_hr_result.kind is BenchmarkKind.MAX_HR_BPM
    assert max_hr_result.value == 190

    assert resting_hr_result is not None
    assert resting_hr_result.kind is BenchmarkKind.RESTING_HR_BPM
    assert resting_hr_result.value == 48


def test_applicable_repeated_calls_with_equal_inputs_return_equal_results() -> None:
    """3.8, 3.9: determinism, including the returned date and note -- not
    only the value.
    """
    entries = BenchmarkSet(
        entries=(
            _RUN_FTP_FUTURE,
            _RUN_FTP_EARLY,
            _RUN_FTP_LATE,
            _RUN_FTP_MID,
            _RIDE_FTP_LATE,
        )
    )

    first = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )
    second = entries.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 8, 1)
    )

    assert first == second
    assert first is not None and second is not None
    assert first.measured_on == second.measured_on == date(2024, 7, 1)
    assert first.note == second.note == "midseason retest"


def test_applicable_repeated_calls_stay_equal_regardless_of_entry_order() -> None:
    """3.8: order of ``entries`` in the ``BenchmarkSet`` must not affect the
    result -- determinism rests on the parser's duplicate-key rejection
    invariant (unique ``(discipline, kind, measured_on)``), not on entries
    being held in any particular stored order.
    """
    forward = BenchmarkSet(
        entries=(_RUN_FTP_EARLY, _RUN_FTP_MID, _RUN_FTP_LATE, _RUN_FTP_FUTURE)
    )
    reversed_ = BenchmarkSet(
        entries=(_RUN_FTP_FUTURE, _RUN_FTP_LATE, _RUN_FTP_MID, _RUN_FTP_EARLY)
    )

    on = date(2024, 8, 1)
    result_forward = forward.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on
    )
    result_reversed = reversed_.applicable(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on
    )

    assert result_forward == result_reversed


_MAXIMALITY_ENTRIES = (
    Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=260,
        measured_on=date(2022, 8, 2),
        note="baseline",
    ),
    Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=255,
        measured_on=date(2023, 11, 15),
        note="winter check",
    ),
    Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=230,
        measured_on=date(2024, 6, 20),
        note="zwift retest",
    ),
    Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=245,
        measured_on=date(2024, 7, 5),
        note="midseason retest",
    ),
    Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=999,
        measured_on=date(2024, 7, 20),
        note="other discipline",
    ),
    Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=None,
        value=888,
        measured_on=date(2024, 7, 25),
        note="athlete-wide decoy",
    ),
    Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=170,
        measured_on=date(2024, 7, 28),
        note="other kind",
    ),
    Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=48,
        measured_on=date(2024, 3, 1),
        note="rhr early",
    ),
    Benchmark(
        kind=BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=44,
        measured_on=date(2024, 7, 10),
        note="rhr mid",
    ),
)
_MAXIMALITY_SET = BenchmarkSet(entries=_MAXIMALITY_ENTRIES)


@pytest.mark.parametrize(
    "kind,discipline",
    [
        (BenchmarkKind.FTP_WATTS, Sport.RUN),
        (BenchmarkKind.FTP_WATTS, Sport.RIDE),
        (BenchmarkKind.LTHR_BPM, Sport.RUN),
        (BenchmarkKind.RESTING_HR_BPM, None),
    ],
)
def test_applicable_selects_the_date_maximal_qualifying_entry(
    kind: BenchmarkKind, discipline: Sport | None
) -> None:
    """3.2: for every query day, ``applicable`` returns a qualifying entry
    and no qualifying entry is dated later than the one returned.

    Swept over every day from 2022-01-01 to 2025-01-01 against a single
    shared, non-monotonic fixture covering all four kind/discipline
    combinations on file, this is the definition of date-maximality
    quantified over the other qualifying entries, not a re-implementation
    of ``max``.
    """
    day = date(2022, 1, 1)
    end = date(2025, 1, 1)
    while day <= end:
        result = _MAXIMALITY_SET.applicable(kind, discipline=discipline, on=day)
        qualifying = [
            entry
            for entry in _MAXIMALITY_ENTRIES
            if entry.kind is kind
            and entry.discipline == discipline
            and entry.measured_on <= day
        ]

        if not qualifying:
            assert result is None
        else:
            assert result is not None
            assert result in qualifying
            assert not [
                entry
                for entry in qualifying
                if result.measured_on < entry.measured_on <= day
            ]

        day += timedelta(days=1)


# ``max(qualifying, key=lambda entry: (entry.measured_on, entry.value))`` is
# a provably equivalent mutant of the production selection key: Req 2.7's
# duplicate-key rejection makes the tiebreaker unreachable, and any
# tie-broken result is still date-maximal, so it is not expected to fail
# the property test above.


# --- Task 1.4: benchmark_age / BenchmarkAge (design: StalenessCalculation) --


def test_benchmark_age_exactly_at_the_window_is_current() -> None:
    """4.1, 4.2: an age equal to the window is current, not stale."""
    activity_date = date(2026, 3, 14)
    measured_on = activity_date - timedelta(days=53)

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=53
    )

    assert result.age_days == 53
    assert result.window_days == 53
    assert result.is_stale is False


def test_benchmark_age_is_immutable() -> None:
    """``BenchmarkAge`` is a frozen value object."""
    verdict = benchmark_age(
        activity_date=date(2026, 3, 14),
        measured_on=date(2026, 1, 20),
        window_days=53,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.is_stale = True  # type: ignore[misc]


def test_benchmark_age_one_day_inside_the_window_is_current() -> None:
    """4.2: an age one day less than the window is current."""
    activity_date = date(2026, 3, 14)
    measured_on = activity_date - timedelta(days=52)

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=53
    )

    assert result.age_days == 52
    assert result.window_days == 53
    assert result.is_stale is False


def test_benchmark_age_one_day_beyond_the_window_is_stale() -> None:
    """4.2: an age one day past the window is stale."""
    activity_date = date(2026, 3, 14)
    measured_on = activity_date - timedelta(days=54)

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=53
    )

    assert result.age_days == 54
    assert result.window_days == 53
    assert result.is_stale is True


def test_benchmark_age_reports_a_non_default_window_alongside_a_non_round_age() -> None:
    """4.4: the reported window is the supplied 137 and the reported age is 23.

    ``window_days`` is nothing near the documented 84-day default, and
    ``age_days`` differs from it, so the two numbers cannot be confused for
    one another.
    """
    activity_date = date(2025, 9, 1)
    measured_on = activity_date - timedelta(days=23)

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=137
    )

    assert result.age_days == 23
    assert result.window_days == 137
    assert result.is_stale is False


def test_benchmark_age_stale_case_with_independent_age_and_window() -> None:
    """4.1, 4.2, 4.4: a second combination in which the age (45), the window
    (10) and the stale flag all differ from the other cases in this module.
    """
    activity_date = date(2024, 1, 20)
    measured_on = activity_date - timedelta(days=45)

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=10
    )

    assert result.age_days == 45
    assert result.window_days == 10
    assert result.is_stale is True


def test_benchmark_age_returns_a_benchmark_age_value() -> None:
    """The return type is the documented value object, not a bare tuple."""
    activity_date = date(2026, 1, 1)
    result = benchmark_age(
        activity_date=activity_date, measured_on=activity_date, window_days=1
    )
    assert isinstance(result, BenchmarkAge)


def test_benchmark_age_returns_negative_age_when_measured_after_activity() -> None:
    """4.6 revised (Amendment 1): a retroactively-applied entry's
    ``measured_on`` can legitimately be after ``activity_date`` (tier 2's
    whole reason to exist), so ``benchmark_age`` no longer raises for it --
    it reports the negative ``age_days`` the subtraction yields and
    ``is_stale=False``.
    """
    activity_date = date(2026, 3, 1)
    measured_on = activity_date + timedelta(days=1)

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=84
    )

    assert result.age_days == -1
    assert result.is_stale is False


def test_benchmark_age_negative_age_far_beyond_the_window_is_still_current() -> None:
    """4.6 revised: even a large negative age (measured far after the
    activity) is current, not stale -- the sign alone decides, not a
    magnitude comparison that a mutant could satisfy by chance for -1 but
    not for a larger negative value.
    """
    activity_date = date(2020, 1, 1)
    measured_on = activity_date + timedelta(days=365 * 4)  # ~4 years later

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=84
    )

    assert result.age_days < -84
    assert result.is_stale is False


def test_benchmark_age_negative_for_athlete_scoped_retroactive_entry() -> None:
    """Round-3 remediation (4.6 revised, athlete-wide axis, fourth layer):
    ``benchmark_age`` is scope-agnostic (it takes no ``kind``/``discipline``
    at all), but this pins the negative-age, not-stale verdict using the
    exact dates of the athlete-scoped (``discipline=None``) tier-2 fixture
    exercised above, so the axis closes in the staleness layer too, not only
    in selection.
    """
    activity_date = date(2021, 6, 15)
    measured_on = date(2027, 2, 14)

    # Reachability: the retroactive measurement genuinely falls after the
    # activity it applies to.
    assert measured_on > activity_date

    result = benchmark_age(
        activity_date=activity_date, measured_on=measured_on, window_days=84
    )

    assert result.age_days < 0
    assert result.is_stale is False


def test_benchmark_age_window_days_guard_still_raises_for_a_retroactive_entry() -> None:
    """4.6 revised: the ``window_days < 1`` guard stays loud even when
    ``measured_on`` is after ``activity_date`` -- the two checks are
    independent.
    """
    activity_date = date(2026, 3, 1)
    measured_on = activity_date + timedelta(days=1)

    with pytest.raises(ValueError):
        benchmark_age(
            activity_date=activity_date, measured_on=measured_on, window_days=0
        )


@pytest.mark.parametrize("window_days", [0, -1, -30])
def test_benchmark_age_raises_when_window_days_is_below_one(window_days: int) -> None:
    """4.6: a window below one day is a programming error and raises."""
    activity_date = date(2026, 3, 1)

    with pytest.raises(ValueError):
        benchmark_age(
            activity_date=activity_date,
            measured_on=activity_date,
            window_days=window_days,
        )


# --- Round-5 remediation: mixed-presence groups at every applies_from/
# measured_on-reading site --------------------------------------------------
#
# Round 5 found that nearly every applies_from fixture in this file sits
# alone in a single-entry array or in a homogeneous group (every entry
# carries applies_from, or none do). Every production site that reads
# applies_from or measured_on *in a group context* is therefore untested
# against a **mixed group**: entries of the same scope+kind, with distinct
# measured_on, where some carry applies_from and some do not. The tests
# below close that class rather than adding isolated fixtures.


def test_applicable_tier1_qualifying_entry_with_applies_from_still_wins_tier1() -> None:
    """Round-5 finding 1 (3.10, critical): a tier-1-qualifying entry that
    *also* carries ``applies_from`` must still win tier 1 -- carrying
    ``applies_from`` does not demote an entry out of tier 1. ``entry_x`` is
    both tier-1-qualifying (measured on or before ``on``) and marked
    retroactive to an even earlier date; ``entry_y`` is a plain, undated-
    declaration entry measured earlier still. Design (3.10): "a tier-1 entry
    always beats a tier-2 one" -- and ``entry_x`` is unambiguously tier-1
    here, so it must be selected over ``entry_y`` by the ordinary
    latest-measured-on tier-1 rule, not sidelined into tier 2 by the mere
    presence of ``applies_from``.

    Mutation: appending ``and entry.applies_from is None`` to the
    ``qualifying`` list comprehension in ``BenchmarkSet.applicable`` silently
    excludes ``entry_x`` from tier 1, leaving only ``entry_y`` qualifying and
    returning its value (200) instead of ``entry_x``'s (300).

    Round-6 remediation (3.11 on the tier-1 path): the returned entry must
    also still carry its ``applies_from`` -- the only other 3.11 fixture is
    tier-2-only, so a tier-1 return with ``applies_from`` stripped off was
    left green by the whole suite until the last two assertions below.
    """
    entry_x = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=300,
        measured_on=date(2022, 1, 1),
        applies_from=date(2015, 1, 1),
    )
    entry_y = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=200,
        measured_on=date(2020, 1, 1),
    )
    entries = BenchmarkSet(entries=(entry_x, entry_y))
    on = date(2024, 1, 1)

    # Reachability: both entries genuinely qualify for tier 1 (measured on or
    # before `on`), and entry_x's measured_on is strictly later than
    # entry_y's, so a correct tier-1 max must prefer entry_x.
    assert entry_x.measured_on <= on and entry_y.measured_on <= on
    assert entry_x.measured_on > entry_y.measured_on
    assert entry_x.applies_from is not None

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)

    assert result is not None
    assert result.value == 300
    assert result.measured_on == date(2022, 1, 1)
    assert result.applies_from == date(2015, 1, 1)
    assert result == entry_x


def test_applicable_scope_check_still_raises_with_a_retroactive_entry_on_file() -> None:
    """Round-6 suggestion: the scope precondition (``ValueError`` on a
    kind/discipline mismatch) is unconditional -- it fires the same way over
    a set that holds a retroactive entry as over one that holds none. The
    existing scope-mismatch tests use plain entries only.
    """
    retroactive = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=257,
        measured_on=date(2026, 4, 9),
        applies_from=date(2018, 11, 23),
    )
    entries = BenchmarkSet(entries=(retroactive,))
    assert any(entry.applies_from is not None for entry in entries.entries)

    with pytest.raises(ValueError, match="ftp_watts"):
        entries.applicable(
            BenchmarkKind.FTP_WATTS, discipline=None, on=date(2020, 1, 1)
        )
    with pytest.raises(ValueError, match="ftp_watts"):
        entries.has(BenchmarkKind.FTP_WATTS, discipline=None)


def test_serializer_sorts_mixed_group_by_measured_on_not_applies_from() -> None:
    """Round-5 finding 2 (6.6, important): within one scope+quantity group
    holding both an applies_from-carrying entry and a plain one, the
    serializer's ascending order is by ``measured_on``, never by
    ``applies_from``. ``later_measured`` is measured after
    ``earlier_measured`` but declares an ``applies_from`` earlier than
    either entry's ``measured_on`` -- so "ascending by measured_on" and
    "ascending by applies_from-or-measured_on" disagree, and only the first
    is correct (design: "sorted ascending by measured_on (6.6)").

    Mutation: ``key=lambda benchmark: benchmark.applies_from or
    benchmark.measured_on`` in ``benchmarks_to_document`` reorders
    ``later_measured`` before ``earlier_measured`` because its (fabricated)
    sort key of 2015-01-01 is earlier than ``earlier_measured``'s
    measured_on of 2020-01-01.
    """
    earlier_measured = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.WALK,
        value=180,
        measured_on=date(2020, 1, 1),
    )
    later_measured = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.WALK,
        value=210,
        measured_on=date(2026, 1, 1),
        applies_from=date(2015, 1, 1),
    )
    entries = (later_measured, earlier_measured)

    # Reachability: the two orderings genuinely disagree.
    assert earlier_measured.measured_on < later_measured.measured_on
    assert later_measured.applies_from is not None
    assert later_measured.applies_from < earlier_measured.measured_on

    document = benchmarks_to_document(entries)

    walk_ftp = document["benchmarks"]["walk"]["ftp_watts"]  # type: ignore[index]
    assert [record["measured_on"] for record in walk_ftp] == [
        date(2020, 1, 1),
        date(2026, 1, 1),
    ]
    assert [record["value"] for record in walk_ftp] == [180, 210]


def test_parser_validates_applies_from_against_its_own_entrys_measured_on() -> None:
    """Round-5 finding 3 (2.11, important): ``applies_from``'s "must not
    fall after measured_on" bound is checked against *that entry's own*
    ``measured_on`` -- not the previous element's -- within a multi-element
    array. ``entries[1]``'s ``applies_from`` (2019-01-01) is valid for its
    own ``measured_on`` (2023-06-15) but falls *after* ``entries[0]``'s
    ``measured_on`` (2018-01-01), so a validator that checks against the
    wrong (previous) element would wrongly reject it.

    Mutation: validating ``entries[1].applies_from`` against
    ``entries[0].measured_on`` (the previous array element) instead of its
    own raises ``BenchmarkError`` for this genuinely valid document.
    """
    earlier_entry = {"value": 50, "measured_on": date(2018, 1, 1)}
    later_entry = {
        "value": 48,
        "measured_on": date(2023, 6, 15),
        "applies_from": date(2019, 1, 1),
    }
    document = {
        "benchmarks": {ATHLETE_SCOPE: {"resting_hr_bpm": [earlier_entry, later_entry]}}
    }

    # Reachability: entries[1]'s applies_from is valid against its own
    # measured_on but falls after entries[0]'s measured_on -- the two bounds
    # genuinely disagree.
    assert later_entry["applies_from"] <= later_entry["measured_on"]  # type: ignore[operator]
    assert later_entry["applies_from"] > earlier_entry["measured_on"]  # type: ignore[operator]

    result = parse_benchmarks(document)

    assert len(result.entries) == 2
    by_measured_on = {entry.measured_on: entry for entry in result.entries}
    assert by_measured_on[date(2018, 1, 1)].value == 50
    assert by_measured_on[date(2023, 6, 15)].value == 48
    assert by_measured_on[date(2023, 6, 15)].applies_from == date(2019, 1, 1)


def test_duplicate_key_ignores_applies_from_presence_not_only_its_value() -> None:
    """Round-5 mixed-group sweep, own mutation 1 (2.7): the duplicate-key
    check is keyed on ``(discipline, kind, measured_on)`` alone, regardless
    of whether either entry carries ``applies_from`` at all -- a mixed
    group (one entry with, one without) sharing ``measured_on`` is rejected
    exactly as a homogeneous one is.

    Mutation: widening the duplicate key to
    ``(discipline, kind, measured_on, entry.applies_from is not None)`` --
    i.e. treating "has an applies_from" as part of the identity -- makes
    this mixed pair look like two distinct keys and the parse would
    (wrongly) succeed.
    """
    document = {
        "benchmarks": {
            "rowing": {
                "ftp_watts": [
                    {"value": 265, "measured_on": date(2026, 4, 4)},
                    {
                        "value": 270,
                        "measured_on": date(2026, 4, 4),
                        "applies_from": date(2016, 4, 4),
                    },
                ]
            }
        }
    }

    with pytest.raises(BenchmarkError) as excinfo:
        parse_benchmarks(document)

    message = str(excinfo.value)
    assert "rowing" in message
    assert "ftp_watts" in message
    assert "2026-04-04" in message


def test_applicable_tier2_never_prefers_a_plain_entry_over_retroactive_one() -> None:
    """Round-5 mixed-group sweep, own mutation 2 (3.10, 3.11): among tier-2
    candidates, an entry with no ``applies_from`` at all must never be
    treated as retroactive-qualifying, even if its ``measured_on`` would
    make it the tier-2 minimum. ``plain_future_entry`` has no
    ``applies_from`` and is measured after ``on`` (so it fails tier 1 too);
    it must never surface via tier 2. ``genuinely_retroactive`` is the only
    entry that actually qualifies for tier 2, and its ``measured_on`` is
    *later* than ``plain_future_entry``'s, so a tier-2 filter that
    (wrongly) let ``plain_future_entry`` in would select it instead by the
    tier-2 minimum rule.

    Mutation: changing the tier-2 filter's
    ``entry.applies_from is not None and entry.applies_from <= on`` to
    ``entry.applies_from is None or entry.applies_from <= on`` admits every
    applies_from-less entry into the retroactive pool regardless of its own
    ``measured_on``, and the subsequent ``min`` then picks
    ``plain_future_entry`` (measured 2021-06-01) over
    ``genuinely_retroactive`` (measured 2023-06-01).
    """
    plain_future_entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.ROWING,
        value=111,
        measured_on=date(2021, 6, 1),
    )
    genuinely_retroactive = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.ROWING,
        value=222,
        measured_on=date(2023, 6, 1),
        applies_from=date(2019, 1, 1),
    )
    entries = BenchmarkSet(entries=(plain_future_entry, genuinely_retroactive))
    on = date(2021, 1, 1)

    # Reachability: neither entry qualifies for tier 1 (both measured after
    # `on`); only genuinely_retroactive's applies_from reaches back to `on`;
    # plain_future_entry's measured_on is nonetheless earlier than
    # genuinely_retroactive's, so an incorrect tier-2 pool would prefer it.
    assert plain_future_entry.measured_on > on
    assert genuinely_retroactive.measured_on > on
    assert plain_future_entry.applies_from is None
    assert genuinely_retroactive.applies_from is not None
    assert genuinely_retroactive.applies_from <= on
    assert plain_future_entry.measured_on < genuinely_retroactive.measured_on

    result = entries.applicable(BenchmarkKind.FTP_WATTS, discipline=Sport.ROWING, on=on)

    assert result is not None
    assert result.value == 222
    assert result.measured_on == date(2023, 6, 1)


def test_serializer_attaches_applies_from_to_correct_sibling_after_sorting() -> None:
    """Round-5 mixed-group sweep, own mutation 3 (6.6): after the
    serializer sorts a mixed group by ``measured_on``, each record's
    ``applies_from`` must belong to *that same, now-repositioned* entry --
    not to whichever entry happened to sit at that index before sorting.
    ``entries`` is constructed with the later-measured (no ``applies_from``)
    entry first and the earlier-measured (``applies_from``-carrying) entry
    second, so sorting must move them past one another; only the earlier
    (now first) record may carry ``applies_from``.

    Mutation: reading ``applies_from`` off the *original, unsorted*
    ``entries`` sequence by loop index (e.g. ``entries[i].applies_from``
    inside a ``for i, entry in enumerate(sorted(entries, ...))`` loop)
    instead of off the sorted entry itself attaches ``applies_from`` to the
    wrong record once sorting has actually reordered anything -- the later
    (no-applies_from) entry would end up wrongly bearing it, and the
    earlier (applies_from-carrying) entry would wrongly lose it.
    """
    later_no_applies_from = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.HIKE,
        value=155,
        measured_on=date(2026, 2, 1),
    )
    earlier_with_applies_from = Benchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.HIKE,
        value=150,
        measured_on=date(2022, 3, 3),
        applies_from=date(2012, 7, 7),
    )
    entries = (later_no_applies_from, earlier_with_applies_from)

    # Reachability: the construction order and the post-sort (measured_on)
    # order genuinely disagree, so an index-based misattribution would be
    # observable.
    assert entries[0].measured_on > entries[1].measured_on

    document = benchmarks_to_document(entries)

    hike_lthr = document["benchmarks"]["hike"]["lthr_bpm"]  # type: ignore[index]
    assert [record["measured_on"] for record in hike_lthr] == [
        date(2022, 3, 3),
        date(2026, 2, 1),
    ]
    first_record, second_record = hike_lthr
    assert "applies_from" in first_record
    assert first_record["applies_from"] == date(2012, 7, 7)
    assert "applies_from" not in second_record


# --- Round-5 finding 4 (optional, 2.11): strengthen two rejection-matrix
# messages to also assert the offending index and the offending ISO dates,
# since the production message genuinely carries both. --------------------


def test_rejection_matrix_applies_from_after_measured_on_names_index_and_dates() -> (
    None
):
    """Extends the existing rejection-matrix coverage for
    ``applies_from_after_measured_on_rejected``: the production message
    (``_validate_applies_from``) is built from ``path`` (which already
    includes the entry's array index) and interpolates both ISO dates --
    this pins those substrings explicitly rather than only the discipline
    and quantity names the shared matrix checks.
    """
    document = _entry(
        "run",
        "ftp_watts",
        value=250,
        measured_on=date(2026, 9, 10),
        applies_from=date(2026, 9, 11),
    )

    with pytest.raises(BenchmarkError) as excinfo:
        parse_benchmarks(document)

    message = str(excinfo.value)
    assert "[0]" in message
    assert "2026-09-11" in message
    assert "2026-09-10" in message


def test_rejection_matrix_athlete_scoped_applies_from_names_index_and_dates() -> None:
    """Same strengthening as above, for the athlete-scoped sibling case
    (``athlete_scoped_applies_from_after_measured_on_rejected``)."""
    document = _entry(
        ATHLETE_SCOPE,
        "max_hr_bpm",
        value=190,
        measured_on=date(2026, 6, 1),
        applies_from=date(2026, 6, 2),
    )

    with pytest.raises(BenchmarkError) as excinfo:
        parse_benchmarks(document)

    message = str(excinfo.value)
    assert "[0]" in message
    assert "2026-06-02" in message
    assert "2026-06-01" in message
