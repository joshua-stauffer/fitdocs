"""Tests for both document types' vocabulary, the frontmatter emitter and
the escaping helpers (training-blocks spec, task 3.1). See "PageVocabulary"
in `.kiro/specs/training-blocks/design.md` (Req 4.2, 4.11, 5.2).

Test File Ownership (tasks.md): this module is 3.1's alone.
"""

from __future__ import annotations

import locale
from datetime import date

import pytest

from fitdocs import contract, docmerge
from fitdocs.model import Modality, Sport
from fitdocs.plans import page
from fitdocs.plans.model import Block, PlannedWorkout, PlanState, build_block
from fitdocs.plans.resolution import MesocycleResolution, Resolution, RowResolution

# --- document vocabulary: the two types (Req 4.2, 5.2) -----------------------


def test_block_type_differs_from_planned_type() -> None:
    assert page.BLOCK_TYPE != page.PLANNED_TYPE


def test_block_type_differs_from_workout_type() -> None:
    assert page.BLOCK_TYPE != contract.WORKOUT_TYPE


def test_planned_type_differs_from_workout_type() -> None:
    assert page.PLANNED_TYPE != contract.WORKOUT_TYPE


def test_block_type_differs_from_history_type() -> None:
    # "training-history" is spelled here, in the test, not in page.py.
    assert page.BLOCK_TYPE != "training-history"


def test_planned_type_differs_from_history_type() -> None:
    assert page.PLANNED_TYPE != "training-history"


def test_block_frontmatter_keys_pinned_by_value() -> None:
    assert page.BLOCK_FRONTMATTER_KEYS == (
        "title",
        "type",
        "generator",
        "block_version",
        "block",
        "starts",
        "ends",
        "goal",
        "mesocycle_days",
    )


def test_planned_frontmatter_keys_pinned_by_value() -> None:
    assert page.PLANNED_FRONTMATTER_KEYS == (
        "title",
        "type",
        "generator",
        "planned_version",
        "block",
        "planned_id",
        "mesocycle",
        "date",
        "sport",
        "modality",
        "indoor",
    )


# --- the frontmatter emitter: round trip (Req 4.2, 5.2) ----------------------


def test_frontmatter_round_trip_types_and_order() -> None:
    """Every string value comes back `str` -- including tokens a bare-token
    emitter would misparse as an int, a bool, `null`, a date, a hex literal,
    or an underscore-grouped int -- every int comes back `int` (never
    `bool`, since `bool` subclasses `int`), every bool comes back `bool`,
    and the keys are in the given order with a `None` value's key omitted.
    """
    pairs: list[tuple[str, str | int | bool | None]] = [
        ("title", "My Block"),
        ("looks_like_int", "1991"),
        ("looks_like_bool", "true"),
        ("looks_like_null", "null"),
        ("looks_like_hex", "0x1F"),
        ("looks_like_grouped_int", "1_000"),
        ("looks_like_date", "2024-01-01"),
        ("omitted", None),
        ("count", 7),
        ("active", True),
        ("inactive", False),
    ]
    text = page.frontmatter(pairs)
    parsed = contract.parse_frontmatter(text)
    assert parsed is not None
    assert "inactive: false" in text.splitlines()

    for key, value in pairs:
        if value is None:
            assert key not in parsed
            continue
        if isinstance(value, bool):
            assert type(parsed[key]) is bool
            assert parsed[key] is value
        elif isinstance(value, int):
            assert type(parsed[key]) is int
            assert parsed[key] == value
        else:
            assert type(parsed[key]) is str
            assert parsed[key] == value

    assert list(parsed.keys()) == [key for key, value in pairs if value is not None]


def test_frontmatter_multiline_goal_round_trips() -> None:
    goal_text = "First line of the goal.\nSecond line, after amendment."
    text = page.frontmatter([("goal", goal_text)])
    parsed = contract.parse_frontmatter(text)
    assert parsed is not None
    assert parsed["goal"] == goal_text


def test_frontmatter_ends_with_the_fence_and_a_trailing_newline() -> None:
    text = page.frontmatter([("title", "T")])
    assert text.endswith(contract.FRONTMATTER_FENCE + "\n")


def test_frontmatter_omits_a_none_valued_key_entirely() -> None:
    text = page.frontmatter([("title", "Kept"), ("goal", None)])
    assert "goal" not in text
    parsed = contract.parse_frontmatter(text)
    assert parsed is not None
    assert "goal" not in parsed
    assert parsed["title"] == "Kept"


def test_yaml_string_rejects_carriage_return() -> None:
    with pytest.raises(ValueError, match="goal"):
        page.yaml_string("bad\rvalue", field="goal")


def test_yaml_string_accepts_an_ordinary_string() -> None:
    # Falsity-in-start-state companion to the reject test above: an
    # ordinary value is genuinely accepted, not merely "not this one input".
    assert page.yaml_string("plain text", field="title") == '"plain text"'


def test_yaml_string_escapes_backslash_quote_tab_and_newline_byte_for_byte() -> None:
    # One value exercising all four escapes together, pinned by exact bytes:
    # dropping any single one of the four `.replace` calls in `yaml_string`
    # changes this literal expected string, so each is independently pinned.
    raw = 'back\\slash "quoted"\ttab\nline'
    expected = '"back\\\\slash \\"quoted\\"\\ttab\\nline"'
    assert page.yaml_string(raw, field="goal") == expected


def test_yaml_string_backslash_and_quote_round_trip_through_parse_frontmatter() -> None:
    # Behavioural companion to the byte pin above: an unescaped `\` or `"`
    # would either corrupt the YAML the block emits or change what comes
    # back, not merely look different in isolation.
    raw = 'a "quoted" path: C:\\Users\\athlete'
    text = page.frontmatter([("goal", raw)])
    parsed = contract.parse_frontmatter(text)
    assert parsed is not None
    assert parsed["goal"] == raw


# --- banner() and notes_region() (Req 4.2) -----------------------------------


def test_banner_is_the_contract_banner_by_identity() -> None:
    # Identity, not equality: a same-valued local copy of the banner string
    # would satisfy `==` and defeat the point of routing through the
    # contract's one constant.
    assert page.banner() is contract.DOC_BANNER


def test_notes_region_composes_the_contract_notes_region_and_placeholder() -> None:
    regions = docmerge.extract_regions(page.notes_region())
    assert regions == {contract.NOTES_REGION: contract.NOTES_PLACEHOLDER}


# --- escaping helpers (Req 4.11) ---------------------------------------------


def test_cell_escapes_pipe() -> None:
    assert page.cell("a|b") == "a\\|b"


def test_cell_leaves_an_ordinary_string_unescaped() -> None:
    assert page.cell("plain") == "plain"


def test_cell_rejects_a_newline() -> None:
    with pytest.raises(ValueError):
        page.cell("a\nb")


def test_link_text_escapes_brackets() -> None:
    assert page.link_text("[x]") == "\\[x\\]"


def test_link_text_also_escapes_pipe() -> None:
    assert page.link_text("a|[b]") == "a\\|\\[b\\]"


def test_format_load_integral_value() -> None:
    assert page.format_load(1200.0) == "1200"


def test_format_load_fractional_value() -> None:
    assert page.format_load(1234.56) == "1234.6"


def test_weekday_tuple_is_locale_free() -> None:
    """Switching the process `LC_TIME` locale must not change
    `page.WEEKDAYS`'s answer for a known date -- an environment variable
    alone would not exercise this, so the process locale is switched
    directly (skipped when no candidate is installed)."""
    known_date = date(2026, 9, 22)  # a Tuesday
    original = locale.setlocale(locale.LC_TIME)
    switched_to: str | None = None
    try:
        for candidate in ("de_DE.UTF-8", "fr_FR.UTF-8", "de_DE", "fr_FR"):
            try:
                locale.setlocale(locale.LC_TIME, candidate)
                switched_to = candidate
                break
            except locale.Error:
                continue
        if switched_to is None:
            pytest.skip("no non-English LC_TIME locale is installed on this machine")
        # Falsity in the starting state: under this locale, the libc
        # weekday abbreviation genuinely differs from "Tue" (confirmed by
        # the implementer against de_DE.UTF-8: "Di." via strftime), so this
        # pin is not vacuously true regardless of implementation.
        assert known_date.strftime("%a") != "Tue"
        assert page.WEEKDAYS[known_date.weekday()] == "Tue"
        assert page.format_day(known_date) == "Tue 2026-09-22"
    finally:
        locale.setlocale(locale.LC_TIME, original)


# --- check_resolution (Req 4.7, 5.4, 6.2, 6.3) -------------------------------


def _make_block() -> Block:
    row = PlannedWorkout(
        id="w1",
        date=date(2026, 1, 2),
        sport=Sport.RUN,
        modality=None,
        indoor=None,
        title="Easy run",
        summary="Easy 40 min",
        prescription="Easy 40 minutes, conversational pace.",
    )
    state = PlanState(rows=(row,), targets=())
    return build_block(
        id="block-a",
        title="Base Block",
        starts=date(2026, 1, 1),
        ends=date(2026, 1, 14),
        goal="Build an aerobic base.",
        mesocycle_days=7,
        original=state,
        current=state,
        amendments=(),
        overrides=(),
    )


def test_check_resolution_passes_for_a_valid_resolution() -> None:
    block = _make_block()
    resolution = Resolution(
        rows={"w1": RowResolution(cell="logged", section=("Matched.",))},
        mesocycles={1: MesocycleResolution(before_table=("note",))},
    )
    page.check_resolution(block, resolution)


def test_check_resolution_rejects_unknown_row_id() -> None:
    block = _make_block()
    resolution = Resolution(
        rows={"not-a-real-row": RowResolution(cell="x", section=())},
        mesocycles={},
    )
    with pytest.raises(ValueError, match="not-a-real-row"):
        page.check_resolution(block, resolution)


def test_check_resolution_rejects_mesocycle_number_zero() -> None:
    block = _make_block()
    assert len(block.mesocycles) == 2
    resolution = Resolution(rows={}, mesocycles={0: MesocycleResolution()})
    with pytest.raises(ValueError, match="0"):
        page.check_resolution(block, resolution)


def test_check_resolution_rejects_mesocycle_number_past_the_end() -> None:
    block = _make_block()
    assert len(block.mesocycles) == 2
    resolution = Resolution(rows={}, mesocycles={3: MesocycleResolution()})
    with pytest.raises(ValueError, match="3"):
        page.check_resolution(block, resolution)


def test_check_resolution_rejects_a_multiline_cell() -> None:
    block = _make_block()
    resolution = Resolution(
        rows={"w1": RowResolution(cell="line one\nline two", section=())},
        mesocycles={},
    )
    with pytest.raises(ValueError, match="w1"):
        page.check_resolution(block, resolution)


# --- is_fence_line (Req 5.4) --------------------------------------------------


def test_is_fence_line_true_for_the_fence() -> None:
    assert page.is_fence_line("---") is True


def test_is_fence_line_false_with_trailing_text() -> None:
    assert page.is_fence_line("--- not a fence") is False


def test_is_fence_line_false_for_an_ordinary_line() -> None:
    assert page.is_fence_line("Just some prose.") is False


# --- sport_phrase (Req 4.11) --------------------------------------------------


def _row(
    sport: Sport, modality: Modality | None, indoor: bool | None
) -> PlannedWorkout:
    return PlannedWorkout(
        id="r",
        date=date(2026, 1, 2),
        sport=sport,
        modality=modality,
        indoor=indoor,
        title="T",
        summary="S",
        prescription="P",
    )


def test_sport_phrase_sport_alone() -> None:
    row = _row(Sport.RUN, None, None)
    assert page.sport_phrase(row) == "Run"


def test_sport_phrase_modality_only() -> None:
    row = _row(Sport.WORKOUT, Modality.STRENGTH, None)
    assert page.sport_phrase(row) == "Workout (strength)"


def test_sport_phrase_flag_only() -> None:
    row = _row(Sport.RIDE, None, True)
    assert page.sport_phrase(row) == "Ride (indoor)"


def test_sport_phrase_modality_and_flag() -> None:
    row = _row(Sport.WORKOUT, Modality.STRENGTH, True)
    assert page.sport_phrase(row) == "Workout (strength, indoor)"


def test_sport_phrase_flag_false_adds_nothing() -> None:
    row = _row(Sport.RIDE, None, False)
    assert page.sport_phrase(row) == "Ride"


def test_sport_phrase_flag_none_adds_nothing() -> None:
    row = _row(Sport.RIDE, None, None)
    assert page.sport_phrase(row) == "Ride"
