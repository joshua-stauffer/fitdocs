"""Tests for the set extractor (Req 6.1-6.5, 12.3).

These exercise :func:`fitdocs.ingest.sets.extract_sets` on the decoded strength
fixture's ``set_mesgs`` (partial fields, a bodyweight zero, an unresolvable
subtype) plus hand-built dicts for the cases the fixture cannot express (an
``exercise_title`` refinement -- present only on structured workouts -- and an
unknown category). Coverage:

* one :class:`StrengthSet` per set message in recorded order (Req 6.1);
* recorded fields map through faithfully while every unrecorded field stays
  ``None`` (Req 6.2), and a recorded bodyweight ``weight=0.0`` is preserved as a
  true zero rather than dropped (Req 6.2, 12.3);
* the exercise name resolves via the SDK Profile category/subtype lookup when
  resolvable (Req 6.3), and stays ``None`` -- never guessed -- when the subtype,
  category, or whole category is absent or unknown (Req 6.3, 6.5);
* a structured-workout ``exercise_title`` whose ``message_index`` matches a set's
  ``wkt_step_index`` overrides the Profile name, while a non-matching title
  leaves the Profile result in place;
* an empty set list yields an empty tuple with no error -- the normal case for
  the user's real watch files (Req 6.4);
* nothing is fabricated: a rest set carrying only type and duration reports
  ``None`` for every other field (Req 6.5).
"""

from __future__ import annotations

from datetime import datetime

from fitdocs.ingest.sets import extract_sets
from fitdocs.model import StrengthSet, fit_datetime
from tests.fixtures import builder

# The fixed FIT-epoch second the fixture builder uses as t0 (never wall-clock).
TS0 = 1_000_000_000


def _fixture_set_mesgs() -> list[dict[str, object]]:
    """The decoded strength fixture's four set messages (partial fields)."""
    return builder.strength_messages()["set_mesgs"]


# --- One-per-set, recorded order (Req 6.1) ----------------------------------


def test_one_strength_set_per_message_in_recorded_order() -> None:
    """N set messages yield N StrengthSets in the recorded order (Req 6.1)."""
    sets = extract_sets(_fixture_set_mesgs(), [])

    assert len(sets) == 4
    assert all(isinstance(item, StrengthSet) for item in sets)
    assert [item.message_index for item in sets] == [0, 1, 2, 3]


# --- Faithful fields + None for absent (Req 6.2) ----------------------------


def test_recorded_fields_map_through_and_absent_fields_are_none() -> None:
    """A set missing weight and reps reports them ``None``; recorded fields map
    through verbatim (Req 6.2)."""
    partial = extract_sets(_fixture_set_mesgs(), [])[2]

    assert partial.weight_kg is None
    assert partial.repetitions is None
    assert partial.set_type == "active"
    assert partial.duration_s == 30.0
    assert partial.category == "bench_press"
    assert partial.start_time == fit_datetime(TS0 + 240)


def test_start_time_converts_to_utc_datetime() -> None:
    """A recorded ``start_time`` becomes a tz-aware UTC datetime (Req 2.4)."""
    first = extract_sets(_fixture_set_mesgs(), [])[0]

    assert isinstance(first.start_time, datetime)
    assert first.start_time == fit_datetime(TS0 + 10)


# --- Bodyweight zero preserved (Req 6.2, 12.3) ------------------------------


def test_bodyweight_zero_weight_is_preserved_not_dropped() -> None:
    """A recorded ``weight=0.0`` bodyweight set keeps the true zero (Req 12.3)."""
    bodyweight = extract_sets(_fixture_set_mesgs(), [])[1]

    assert bodyweight.weight_kg == 0.0
    assert bodyweight.weight_kg is not None
    assert bodyweight.repetitions == 15


# --- Name resolution via the Profile lookup (Req 6.3) -----------------------


def test_exercise_name_resolved_from_profile_category_subtype() -> None:
    """A resolvable category/subtype yields the SDK Profile exercise name (Req 6.3)."""
    sets = extract_sets(_fixture_set_mesgs(), [])

    assert sets[0].exercise_name == "barbell_bench_press"
    assert sets[1].exercise_name == "alternating_staggered_push_up"


def test_category_array_uses_first_entry() -> None:
    """A FIT array ``category``/``category_subtype`` resolves from the first entry."""
    set_mesgs: list[dict[str, object]] = [
        {
            "message_index": 0,
            "category": ["bench_press", "push_up"],
            "category_subtype": [1, 2],
        }
    ]

    (only,) = extract_sets(set_mesgs, [])

    assert only.category == "bench_press"
    assert only.exercise_name == "barbell_bench_press"


# --- Unresolvable name stays None, never guessed (Req 6.3, 6.5) -------------


def test_unresolvable_subtype_yields_none_name() -> None:
    """A subtype absent from the Profile table (999) leaves the name ``None``
    (Req 6.5)."""
    sets = extract_sets(_fixture_set_mesgs(), [])

    assert sets[2].category == "bench_press"
    assert sets[2].exercise_name is None


def test_unknown_category_yields_none_name() -> None:
    """A category with no ``*_exercise_name`` table leaves the name ``None``
    (Req 6.5)."""
    set_mesgs: list[dict[str, object]] = [
        {"message_index": 0, "category": "not_a_real_category", "category_subtype": 1}
    ]

    (only,) = extract_sets(set_mesgs, [])

    assert only.category == "not_a_real_category"
    assert only.exercise_name is None


def test_missing_category_yields_none_name_and_category() -> None:
    """A set with no category resolves neither the category nor the name (Req 6.5)."""
    set_mesgs: list[dict[str, object]] = [{"message_index": 0, "category_subtype": 1}]

    (only,) = extract_sets(set_mesgs, [])

    assert only.category is None
    assert only.exercise_name is None


# --- exercise_title refinement (structured workouts only) -------------------


def test_matching_exercise_title_name_wins_over_profile() -> None:
    """A set's ``wkt_step_index`` matching an ``exercise_title.message_index`` uses
    the title's ``wkt_step_name`` in place of the Profile lookup."""
    set_mesgs: list[dict[str, object]] = [
        {
            "message_index": 0,
            "category": "bench_press",
            "category_subtype": 1,  # Profile alone -> barbell_bench_press
            "wkt_step_index": 5,
            "set_type": "active",
        }
    ]
    title_mesgs: list[dict[str, object]] = [
        {"message_index": 5, "wkt_step_name": "Tempo Bench Press"}
    ]

    (only,) = extract_sets(set_mesgs, title_mesgs)

    assert only.exercise_name == "Tempo Bench Press"


def test_non_matching_exercise_title_falls_back_to_profile() -> None:
    """A ``wkt_step_index`` with no matching title keeps the Profile-resolved name."""
    set_mesgs: list[dict[str, object]] = [
        {
            "message_index": 0,
            "category": "bench_press",
            "category_subtype": 1,
            "wkt_step_index": 5,
        }
    ]
    title_mesgs: list[dict[str, object]] = [
        {"message_index": 99, "wkt_step_name": "Unrelated"}
    ]

    (only,) = extract_sets(set_mesgs, title_mesgs)

    assert only.exercise_name == "barbell_bench_press"


# --- Empty collection is the normal watch-file case (Req 6.4) ---------------


def test_no_set_messages_yield_empty_tuple() -> None:
    """No set messages yield an empty tuple with no error (Req 6.4)."""
    assert extract_sets([], []) == ()


# --- No fabrication anywhere (Req 6.5) --------------------------------------


def test_rest_set_fabricates_nothing() -> None:
    """A rest set carrying only type and duration reports ``None`` for every other
    field -- no field is ever defaulted (Req 6.5)."""
    rest = extract_sets(_fixture_set_mesgs(), [])[3]

    assert rest.set_type == "rest"
    assert rest.duration_s == 30.0
    assert rest.start_time == fit_datetime(TS0 + 300)
    assert rest.repetitions is None
    assert rest.weight_kg is None
    assert rest.category is None
    assert rest.exercise_name is None


# --- Unknown-enum-as-int robustness (Part B) --------------------------------


def test_int_valued_set_type_does_not_crash_and_coerces() -> None:
    """An unknown ``set_type`` decoded as a raw int coerces to its str, never crashing.

    Under the decoder's ``convert_types_to_strings`` default an unknown enum stays a
    raw int; coercing it faithfully (rather than crashing) keeps whole-file parsing
    alive (Req 6.2 no-fabrication -- the raw value is exposed, not a default).
    """
    set_mesgs: list[dict[str, object]] = [{"message_index": 0, "set_type": 3}]

    (only,) = extract_sets(set_mesgs, [])

    assert only.set_type == "3"
