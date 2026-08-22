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
            value=255.0,
            measured_on=date(2026, 3, 14),
        ),
        Benchmark(
            kind=BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=190,
            measured_on=date(2025, 11, 9),
        ),
        Benchmark(
            kind=BenchmarkKind.RESTING_HR_BPM,
            discipline=None,
            value=48,
            measured_on=date(2025, 1, 1),
        ),
    )
    original = BenchmarkSet(entries=entries)

    round_tripped = parse_benchmarks(benchmarks_to_document(list(entries)))

    # Order-independent: the parser and serializer are free to reorder by
    # scope/quantity/date, but the resulting *set* of entries must match.
    assert set(round_tripped.entries) == set(original.entries)
    # Guard the entry count as well as the set.
    assert len(round_tripped.entries) == len(original.entries)


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


def test_benchmark_age_raises_when_measured_on_is_after_activity_date() -> None:
    """4.6: selection never yields such a benchmark; a measurement dated
    after the activity is a programming error and raises rather than being
    reported as current.
    """
    activity_date = date(2026, 3, 1)
    measured_on = activity_date + timedelta(days=1)

    with pytest.raises(ValueError):
        benchmark_age(
            activity_date=activity_date, measured_on=measured_on, window_days=84
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
