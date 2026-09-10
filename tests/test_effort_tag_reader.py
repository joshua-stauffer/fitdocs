"""Tests for :func:`fitdocs.contract.effort_tag` (task 1.2, Req 1.3, 2.2-2.6,
2.8, 3.1-3.3, 3.6, 3.7, 5.1-5.3, 5.6).

Every fixture that exercises a validation rule pairs a value that *violates*
it with a sibling that satisfies it -- never a pre-satisfied fixture (see
``.kiro/steering/change-protocol.md``'s Fixture Discrimination section).
"""

import math

from fitdocs.contract import (
    EFFORT_DISTANCE_KEY,
    EFFORT_EVENT_KEY,
    EFFORT_KEY,
    EFFORT_TIME_KEY,
    EffortKind,
    EffortTag,
    EffortTagProblem,
    InvalidEffortTag,
    effort_tag,
)

# --- absent (Req 1.3, 5.2) ---------------------------------------------------


def test_none_frontmatter_is_absent() -> None:
    assert effort_tag(None) is None


def test_frontmatter_with_no_effort_key_is_absent() -> None:
    assert effort_tag({"title": "Easy Run", "sport": "running"}) is None


def test_frontmatter_with_only_unrelated_keys_is_absent_not_malformed() -> None:
    """An empty-looking mapping never becomes a malformed tag by accident."""
    result = effort_tag({})
    assert result is None


# --- a full valid tag (Req 2.1, 2.3, 2.4) -----------------------------------


def test_full_valid_tag_all_four_keys() -> None:
    result = effort_tag(
        {
            EFFORT_KEY: "race",
            EFFORT_DISTANCE_KEY: 42195,
            EFFORT_TIME_KEY: 10800,
            EFFORT_EVENT_KEY: "[[Boston Marathon 2024]]",
        }
    )
    assert result == EffortTag(
        kind=EffortKind.RACE,
        distance_m=42195.0,
        time_s=10800.0,
        event="[[Boston Marathon 2024]]",
    )


def test_distance_and_time_are_stored_as_float_not_int() -> None:
    """Req 2.3/3.2: numeric fields are stored as `float`, even when the
    input value is an `int` that would already satisfy `== 42195.0` /
    `== 10800.0` -- an `isinstance` check is needed because Python's `int`
    would otherwise pass the equality check unnoticed. mypy's numeric tower
    accepts `int` where `float` is declared with no `type: ignore`, so this
    assertion, not mypy, is what pins the conversion. Named mutation:
    replace `distance_m = distance_number` / `time_s = time_number` with the
    raw input value (or drop the `float()` conversion inside
    `_positive_finite_float`) -- this reds (`isinstance(..., float)` is
    `False` for an `int`)."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: 42195, EFFORT_TIME_KEY: 10800}
    )
    assert isinstance(result, EffortTag)
    assert isinstance(result.distance_m, float)
    assert isinstance(result.time_s, float)


def test_kind_only_tag_is_valid_with_none_fields() -> None:
    result = effort_tag({EFFORT_KEY: "test"})
    assert result == EffortTag(
        kind=EffortKind.TEST, distance_m=None, time_s=None, event=None
    )


def test_time_only_tag_is_valid_distance_is_none() -> None:
    """Design's stated observable: time may stand alone without distance."""
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: 3600})
    assert isinstance(result, EffortTag)
    assert result.time_s == 3600.0
    assert result.distance_m is None


# --- K1: effort required whenever another effort key is present (Req 2.5) --


def test_orphan_distance_without_effort_is_malformed_k1() -> None:
    """Violates K1: distance present, `effort` absent -- not read as untagged."""
    result = effort_tag({EFFORT_DISTANCE_KEY: 42195, EFFORT_TIME_KEY: 10800})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_KEY,
                "required whenever any other effort key is present; expected "
                "one of race, test, hard",
            ),
        )
    )


def test_orphan_time_without_effort_is_malformed_k1() -> None:
    """Sibling of the distance-orphan case: time alone, still needs `effort`."""
    result = effort_tag({EFFORT_TIME_KEY: 3600})
    assert isinstance(result, InvalidEffortTag)
    assert result.problems == (
        EffortTagProblem(
            EFFORT_KEY,
            "required whenever any other effort key is present; expected "
            "one of race, test, hard",
        ),
    )


def test_orphan_event_without_effort_is_malformed_k1() -> None:
    """Req 2.5 names all three of distance/time/event as K1 triggers; this
    fixture is the only one exercising the event leg of the trigger tuple.
    Named mutation: drop EFFORT_EVENT_KEY from the trigger tuple at K1's
    `has_other_effort_key` check -- this reds (result becomes None)."""
    result = effort_tag({EFFORT_EVENT_KEY: "[[Boston Marathon 2024]]"})
    assert isinstance(result, InvalidEffortTag)
    assert result.problems == (
        EffortTagProblem(
            EFFORT_KEY,
            "required whenever any other effort key is present; expected "
            "one of race, test, hard",
        ),
    )


def test_k1_named_mutation_orphan_rule_returns_nothing_instead_of_problem() -> None:
    """Named mutation target: if K1 is made to record no problem, an orphan
    field reads as untagged (``None``) instead of malformed. This test pins
    the *current* correct behavior -- that it is NOT read as untagged -- so
    that mutation reds it.
    """
    result = effort_tag({EFFORT_TIME_KEY: 3600})
    assert result is not None


# --- K2: kind is exactly one of race/test/hard, case-sensitive (Req 2.2) ---


def test_capitalized_kind_is_malformed_k2() -> None:
    """Violates K2: `Race` is not `race` -- case-sensitive exact match."""
    result = effort_tag({EFFORT_KEY: "Race"})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_KEY,
                "must be one of race, test, hard (exact, lowercase); got 'Race'",
            ),
        )
    )


def test_lowercase_kind_is_valid_k2_sibling() -> None:
    """Sibling of the capitalization case: exact lowercase match succeeds."""
    result = effort_tag({EFFORT_KEY: "race"})
    assert isinstance(result, EffortTag)
    assert result.kind == EffortKind.RACE


def test_effort_key_with_no_value_is_malformed_k2() -> None:
    """`effort:` with no value parses to `None`; still a K2 problem, not K1
    (the key IS present -- only its value is invalid)."""
    result = effort_tag({EFFORT_KEY: None})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_KEY,
                "must be one of race, test, hard (exact, lowercase); got None",
            ),
        )
    )


# --- D1/T1: numeric guards -- bool, finite, strictly positive (Req 2.3) ----


def test_distance_true_is_malformed_bool_guard_d1() -> None:
    """`True` is an `int` subclass in Python; the bool guard rejects it
    explicitly. Named mutation: drop the bool guard and this reds (`True`
    would pass as `1.0`)."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: True, EFFORT_TIME_KEY: 10}
    )
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, "must be a positive number of metres; got True"
            ),
        )
    )


def test_distance_zero_is_malformed_strictly_positive_d1() -> None:
    """Named mutation: change `> 0` to `>= 0` and this reds (`0` would pass)."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: 0, EFFORT_TIME_KEY: 10}
    )
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, "must be a positive number of metres; got 0"
            ),
        )
    )


def test_distance_negative_is_malformed_d1() -> None:
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: -5, EFFORT_TIME_KEY: 10}
    )
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, "must be a positive number of metres; got -5"
            ),
        )
    )


def test_distance_infinite_is_malformed_finiteness_d1() -> None:
    """Named mutation: drop the finiteness check and this reds (`inf` would
    pass)."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: math.inf, EFFORT_TIME_KEY: 10}
    )
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, "must be a positive number of metres; got inf"
            ),
        )
    )


def test_distance_as_string_is_malformed_never_parsed_d1() -> None:
    """Req 3.2: strings are never parsed into numbers, even numeric-looking
    ones."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: "10000", EFFORT_TIME_KEY: 10}
    )
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, "must be a positive number of metres; got '10000'"
            ),
        )
    )


def test_distance_wildly_large_int_is_malformed_not_overflow_d1() -> None:
    """Req 5.2: `effort_tag` never raises. A 401-digit int is an ordinary
    Python `int` (YAML has no size limit); converting it to `float` raises
    `OverflowError` unless caught. Named mutation: remove the `try/except
    OverflowError` in `_positive_finite_float` -- this reds with an
    uncaught `OverflowError` instead of a clean D1 problem."""
    big = 10**400
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: big, EFFORT_TIME_KEY: 10}
    )
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, f"must be a positive number of metres; got {big!r}"
            ),
        )
    )


def test_invalid_distance_without_time_reports_only_the_first_failing_rule() -> None:
    """An invalid distance (D1) with no time key present at all must report
    only the D1 problem, not also a D2 ("requires effort_time_s") problem --
    at most one problem per key, the first failing rule. Named mutation:
    change the `elif EFFORT_TIME_KEY not in frontmatter` in the distance
    block to an unconditional second `problems.append(...)` after the D1
    branch -- this reds (two problems instead of one)."""
    result = effort_tag({EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: -5})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY, "must be a positive number of metres; got -5"
            ),
        )
    )


def test_distance_positive_float_with_time_is_valid_d1_sibling() -> None:
    """Sibling of the D1 violations: a genuine positive finite number, paired
    with time, is valid."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: 5000.5, EFFORT_TIME_KEY: 1200}
    )
    assert isinstance(result, EffortTag)
    assert result.distance_m == 5000.5


def test_time_true_is_malformed_bool_guard_t1() -> None:
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: True})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_TIME_KEY, "must be a positive number of seconds; got True"
            ),
        )
    )


def test_time_zero_is_malformed_strictly_positive_t1() -> None:
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: 0})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_TIME_KEY, "must be a positive number of seconds; got 0"
            ),
        )
    )


def test_time_negative_is_malformed_t1() -> None:
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: -5})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_TIME_KEY, "must be a positive number of seconds; got -5"
            ),
        )
    )


def test_time_infinite_is_malformed_finiteness_t1() -> None:
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: math.inf})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_TIME_KEY, "must be a positive number of seconds; got inf"
            ),
        )
    )


def test_time_as_string_is_malformed_never_parsed_t1() -> None:
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: "10000"})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_TIME_KEY, "must be a positive number of seconds; got '10000'"
            ),
        )
    )


def test_time_wildly_large_int_is_malformed_not_overflow_t1() -> None:
    """Req 5.2 sibling of the distance overflow case, for `effort_time_s`.
    Named mutation: same as the distance case -- remove the
    `try/except OverflowError` in `_positive_finite_float` -- this reds
    with an uncaught `OverflowError`."""
    big = 10**400
    result = effort_tag({EFFORT_KEY: "race", EFFORT_TIME_KEY: big})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_TIME_KEY, f"must be a positive number of seconds; got {big!r}"
            ),
        )
    )


def test_time_positive_int_alone_is_valid_t1_sibling() -> None:
    result = effort_tag({EFFORT_KEY: "hard", EFFORT_TIME_KEY: 1800})
    assert isinstance(result, EffortTag)
    assert result.time_s == 1800.0


# --- D2: distance requires time (Req 2.4) -----------------------------------


def test_distance_without_time_is_malformed_d2() -> None:
    """Violates D2: a valid, positive distance with no time at all."""
    result = effort_tag({EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: 42195})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_DISTANCE_KEY,
                "requires effort_time_s: a course distance is an official "
                "result only together with its time",
            ),
        )
    )


def test_distance_with_time_is_valid_d2_sibling() -> None:
    """Sibling of the D2 violation: adding time alone is enough to satisfy
    it."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: 42195, EFFORT_TIME_KEY: 10800}
    )
    assert isinstance(result, EffortTag)
    assert result.distance_m == 42195.0
    assert result.time_s == 10800.0


# --- E1: event is non-empty text, stored as written (Req 2.6, 3.7) ---------


def test_event_nested_list_from_unquoted_wikilink_is_malformed_e1() -> None:
    """Req 3.7: an unquoted wikilink YAML reads as a nested list, and the
    detail states the value must be quoted text."""
    value = [["Boston Marathon 2024"]]
    result = effort_tag({EFFORT_KEY: "race", EFFORT_EVENT_KEY: value})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_EVENT_KEY,
                "must be non-empty text; quote a wikilink, e.g. effort_event: "
                f'"[[Boston Marathon 2024]]"; got {value!r}',
            ),
        )
    )


def test_event_empty_string_is_malformed_e1() -> None:
    result = effort_tag({EFFORT_KEY: "race", EFFORT_EVENT_KEY: "   "})
    assert result == InvalidEffortTag(
        problems=(
            EffortTagProblem(
                EFFORT_EVENT_KEY,
                "must be non-empty text; quote a wikilink, e.g. effort_event: "
                "\"[[Boston Marathon 2024]]\"; got '   '",
            ),
        )
    )


def test_event_valid_string_is_stored_as_written_e1_sibling() -> None:
    """Sibling of the E1 violations, and Req 2.6: stored exactly as written,
    not stripped even though it has surrounding text."""
    result = effort_tag(
        {EFFORT_KEY: "race", EFFORT_EVENT_KEY: "[[Boston Marathon 2024]] "}
    )
    assert isinstance(result, EffortTag)
    assert result.event == "[[Boston Marathon 2024]] "


# --- ordering: at most one problem per key, EFFORT_KEYS order (Req 5.6) ----


def test_two_problems_report_in_effort_keys_order() -> None:
    """A page wrong on two different keys reports `effort` before
    `effort_time_s` (EFFORT_KEYS order), not reverse. This pins the code's
    append order for this fixture, which coincides with EFFORT_KEYS order
    here; see `test_four_problem_page_reports_in_effort_keys_order` for a
    fixture that also distinguishes append order from EFFORT_KEYS order
    across the distance/time blocks. Named mutation: reverse the final
    tuple and this reds."""
    result = effort_tag({EFFORT_KEY: "Race", EFFORT_TIME_KEY: -5})
    assert isinstance(result, InvalidEffortTag)
    assert result.problems == (
        EffortTagProblem(
            EFFORT_KEY,
            "must be one of race, test, hard (exact, lowercase); got 'Race'",
        ),
        EffortTagProblem(
            EFFORT_TIME_KEY, "must be a positive number of seconds; got -5"
        ),
    )


def test_two_problem_page_describe_renders_both_in_order() -> None:
    """Req 5.6: `describe()` is the one renderer every reporter shares."""
    result = effort_tag({EFFORT_KEY: "Race", EFFORT_TIME_KEY: -5})
    assert isinstance(result, InvalidEffortTag)
    assert result.describe() == (
        "effort: must be one of race, test, hard (exact, lowercase); got 'Race'; "
        "effort_time_s: must be a positive number of seconds; got -5"
    )


def test_four_problem_page_reports_in_effort_keys_order() -> None:
    """A page wrong on all four keys reports effort, effort_distance_m,
    effort_time_s, effort_event -- EFFORT_KEYS order -- distinguishing the
    relative order of the distance and time blocks, which the two-problem
    fixture above cannot (it carries no distance problem at all, so the
    relative order of the distance and time blocks is unobservable in it).
    Named mutation: swap the distance block (D1/D2) with the time
    block (T1) in the source -- this reds (distance and time problems swap
    positions in the tuple)."""
    result = effort_tag(
        {
            EFFORT_KEY: "Race",
            EFFORT_DISTANCE_KEY: -1,
            EFFORT_TIME_KEY: -5,
            EFFORT_EVENT_KEY: "",
        }
    )
    assert isinstance(result, InvalidEffortTag)
    assert result.problems == (
        EffortTagProblem(
            EFFORT_KEY,
            "must be one of race, test, hard (exact, lowercase); got 'Race'",
        ),
        EffortTagProblem(
            EFFORT_DISTANCE_KEY, "must be a positive number of metres; got -1"
        ),
        EffortTagProblem(
            EFFORT_TIME_KEY, "must be a positive number of seconds; got -5"
        ),
        EffortTagProblem(
            EFFORT_EVENT_KEY,
            "must be non-empty text; quote a wikilink, e.g. effort_event: "
            "\"[[Boston Marathon 2024]]\"; got ''",
        ),
    )


# --- sport-blindness (Req 2.8) ------------------------------------------


def test_reader_is_sport_blind_strength_page_reads_the_same() -> None:
    """Req 2.8: a strength-modality page tagged the same way reads the same
    concrete tag as a running page. Asserting a concrete expected value on
    both pages (rather than only their mutual equality) rules out a reader
    that is blind to `sport`/`modality` by returning the same *wrong* answer
    (e.g. `None`) for every page regardless of tagging -- the mutual-equality
    check alone cannot distinguish "sport-blind and correct" from
    "sport-blind and always None". Named mutation: insert
    `if "sport" in frontmatter or "modality" in frontmatter: return None` at
    the top of `effort_tag` -- this reds (both pages would read as
    untagged instead of the expected tag)."""
    expected = EffortTag(
        kind=EffortKind.TEST, distance_m=None, time_s=600.0, event=None
    )
    running_frontmatter = {
        EFFORT_KEY: "test",
        EFFORT_TIME_KEY: 600,
        "sport": "running",
    }
    strength_frontmatter = {
        EFFORT_KEY: "test",
        EFFORT_TIME_KEY: 600,
        "modality": "strength",
    }
    assert effort_tag(running_frontmatter) == expected
    assert effort_tag(strength_frontmatter) == expected
    assert effort_tag(running_frontmatter) == effort_tag(strength_frontmatter)


# --- never raises (Req 5.2) --------------------------------------------------


def test_never_raises_on_wildly_wrong_shapes() -> None:
    for garbage in (
        {EFFORT_KEY: object()},
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: object(), EFFORT_TIME_KEY: 5},
        {EFFORT_KEY: ["race"]},
        {EFFORT_KEY: "race", EFFORT_EVENT_KEY: {"nested": "mapping"}},
        {EFFORT_KEY: "race", EFFORT_DISTANCE_KEY: 10**400, EFFORT_TIME_KEY: 10},
        {EFFORT_KEY: "race", EFFORT_TIME_KEY: 10**400},
    ):
        effort_tag(garbage)  # must not raise


# --- pure / repeatable (design invariant) -----------------------------------


def test_same_mapping_yields_equal_result_every_time() -> None:
    frontmatter = {EFFORT_KEY: "race", EFFORT_TIME_KEY: 3600}
    assert effort_tag(frontmatter) == effort_tag(frontmatter)
