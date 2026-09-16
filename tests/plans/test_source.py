"""Tests for the plan-source grammar (training-blocks spec, task 2.3):
`parse_block`, `load_block`, `PlanValidationError`, and the Plan-Source
Grammar table's rules. See "SourceParser" in
`.kiro/specs/training-blocks/design.md`
(Req 1.1, 1.3-1.7, 2.1-2.3, 2.5-2.7, 2.10, 2.12, 3.4, 3.8).

Task File Ownership: this module and `tests/plans/fixtures/*.toml` belong
to task 2.3 alone (tasks.md, Test File Ownership); `tests/plans/conftest.py`
is deliberately never created (two parallel renderer tasks creating it
would conflict by construction -- each loads `fixtures/full.toml` through
this module's `parse_block` directly).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fitdocs.plans.model import PlanProblem
from fitdocs.plans.source import PlanValidationError, load_block, parse_block

FIXTURES = Path(__file__).parent / "fixtures"

BASE = """\
title = "Base"
starts = 2026-03-02
ends = 2026-03-08
goal = "Goal text."
mesocycle_days = 7

[[workout]]
id = "w1-mon"
date = 2026-03-02
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."
"""


def _raises(text: str, *, block_id: str = "test-block") -> tuple[PlanProblem, ...]:
    with pytest.raises(PlanValidationError) as excinfo:
        parse_block(text, block_id=block_id)
    return excinfo.value.problems


def _one(text: str, *, block_id: str = "test-block") -> PlanProblem:
    problems = _raises(text, block_id=block_id)
    assert len(problems) == 1, problems
    return problems[0]


# ===========================================================================
# The minimal valid source.
# ===========================================================================


class TestMinimalFixture:
    def test_parses_to_one_mesocycle_one_row(self) -> None:
        text = (FIXTURES / "minimal.toml").read_text()
        block = parse_block(text, block_id="minimal-block")
        assert block.id == "minimal-block"
        assert block.title == "Minimal block"
        assert len(block.mesocycles) == 1
        assert [w.id for w in block.mesocycles[0].workouts] == ["w1-mon"]
        assert block.overrides == ()
        assert block.amendments == ()


# ===========================================================================
# The full fixture: both renderer goldens' source, no fixtures of their own.
# Observable: mesocycles, trail and overrides match the fixture by inspection.
# ===========================================================================


class TestFullFixtureObservable:
    def test_matches_documented_properties(self) -> None:
        text = (FIXTURES / "full.toml").read_text()
        block = parse_block(text, block_id="base-build")

        windows = [(m.number, m.starts, m.ends, m.is_short) for m in block.mesocycles]
        assert windows == [
            (1, date(2026, 1, 5), date(2026, 1, 11), False),
            (2, date(2026, 1, 12), date(2026, 1, 18), False),
            (3, date(2026, 1, 19), date(2026, 1, 22), True),
        ]

        assert block.mesocycles[0].target_load == 300.0
        assert block.mesocycles[0].focus == "Base"
        # Untargeted originally, targeted by amendment 1.
        assert block.mesocycles[1].target_load == 250.0
        assert block.mesocycles[1].focus == "Build"
        assert block.mesocycles[2].target_load is None
        assert block.mesocycles[2].focus is None

        # 2026-01-08 is a two-workout day in the CURRENT plan (neither
        # amendment touches it): source order "w1-thu-b" then "w1-thu-a",
        # opposite of alphabetical id order -- the property a day-table
        # renderer reading `Mesocycle.workouts` (the current placement,
        # not `original`) must preserve.
        current_meso1_ids = [w.id for w in block.mesocycles[0].workouts]
        assert current_meso1_ids == ["w1-mon", "w1-thu-b", "w1-thu-a", "w1-fri"]
        thu_b_index = current_meso1_ids.index("w1-thu-b")
        thu_a_index = current_meso1_ids.index("w1-thu-a")
        assert thu_b_index < thu_a_index  # source order
        assert sorted(["w1-thu-b", "w1-thu-a"]) != [
            "w1-thu-b",
            "w1-thu-a",
        ]  # id order differs

        assert [w.id for w in block.mesocycles[1].workouts] == []
        # w1-sun moves here (the cross-boundary move), w1-sat is added
        # then removed so it never appears in any current placement.
        assert [w.id for w in block.mesocycles[2].workouts] == ["w1-sun"]

        assert len(block.amendments) == 2
        first, second = block.amendments
        assert first.ordinal == 1
        assert [type(c).__name__ for c in first.changes] == [
            "RowChanged",
            "RowAdded",
            "TargetChanged",
        ]
        assert second.ordinal == 2
        assert [type(c).__name__ for c in second.changes] == [
            "RowChanged",
            "RowRemoved",
        ]

        assert {(o.date, o.row_id, o.stems, o.skipped) for o in block.overrides} == {
            (date(2026, 1, 6), "w1-mon", ("run-2026-01-06-am",), False),
            (date(2026, 1, 9), "w1-fri", (), True),
        }

        # w1-sat was added then removed: present in current.rows history but
        # not in the final mesocycle placement above.
        assert "w1-sat" not in [w.id for w in block.current.rows]
        assert any(row.id == "w1-sat" for row in block.original.rows) is False


# ===========================================================================
# Structural faults: reported, and parsing stops.
# ===========================================================================


class TestStructuralStop:
    def test_reversed_bounds_with_bad_row_yields_one_problem(self) -> None:
        text = """\
title = "Bad block"
starts = 2026-05-10
ends = 2026-05-01
goal = "Goal."
mesocycle_days = 7

[[workout]]
id = "BAD ID"
date = 2026-05-10
sport = "Nope"
title = "x"
summary = "x"
prescription = "x"
"""
        problem = _one(text)
        assert problem.entry == "block"
        assert problem.field == "ends"
        assert "before starts" in problem.message

    def test_missing_starts_and_ends_stop(self) -> None:
        text = """\
title = "Bad block"
goal = "Goal."
mesocycle_days = 7
"""
        problems = _raises(text)
        fields = {p.field for p in problems}
        assert fields == {"starts", "ends"}

    def test_missing_mesocycle_days_stops(self) -> None:
        text = """\
title = "Bad block"
starts = 2026-05-01
ends = 2026-05-07
goal = "Goal."
"""
        problem = _one(text)
        assert problem.entry == "block"
        assert problem.field == "mesocycle_days"


class TestThreeIndependentFaults:
    def test_reports_three_problems_in_document_order(self) -> None:
        text = """\
starts = 2026-04-06
ends = 2026-04-12
goal = "Goal."
mesocycle_days = 7

[[mesocycle]]
number = "one"

[[workout]]
id = "w1-mon"
date = 2026-04-06
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."
extra = "nope"
"""
        problems = _raises(text)
        assert len(problems) == 3
        assert problems[0].entry == "block" and problems[0].field == "title"
        assert problems[1].entry == "mesocycle[0]" and problems[1].field == "number"
        assert (
            problems[2].entry == "workout[1] (id w1-mon)"
            and problems[2].field == "extra"
        )


# ===========================================================================
# Bare TOML dates only.
# ===========================================================================


class TestDateForm:
    def test_quoted_date_is_rejected(self) -> None:
        text = BASE.replace("starts = 2026-03-02\n", 'starts = "2026-03-02"\n')
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "starts"
        assert "unquoted" in problem.message

    def test_datetime_is_rejected(self) -> None:
        text = BASE.replace("starts = 2026-03-02\n", "starts = 2026-03-02T00:00:00\n")
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "starts"
        assert "unquoted" in problem.message


# ===========================================================================
# `bool` rejected wherever a number is expected.
# ===========================================================================


class TestMesocycleDaysBoolean:
    def test_bool_mesocycle_days_is_rejected(self) -> None:
        text = BASE.replace("mesocycle_days = 7", "mesocycle_days = true")
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "mesocycle_days"
        assert "integer" in problem.message

    def test_zero_mesocycle_days_is_rejected(self) -> None:
        text = BASE.replace("mesocycle_days = 7", "mesocycle_days = 0")
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "mesocycle_days"
        assert "at least 1" in problem.message


class TestBoundsEdgeCase:
    def test_ends_equal_to_starts_parses_as_one_mesocycle(self) -> None:
        text = BASE.replace("ends = 2026-03-08\n", "ends = 2026-03-02\n").replace(
            "mesocycle_days = 7\n", "mesocycle_days = 1\n"
        )
        block = parse_block(text, block_id="test-block")
        assert len(block.mesocycles) == 1
        assert block.mesocycles[0].is_short is False
        assert (
            block.mesocycles[0].starts == block.mesocycles[0].ends == date(2026, 3, 2)
        )


# ===========================================================================
# Unknown keys at every level.
# ===========================================================================


class TestUnknownKeys:
    def test_top_level_unknown_key(self) -> None:
        # Must precede `[[workout]]` -- TOML assigns a bare key to whatever
        # table header preceded it, not back to the document root.
        text = BASE.replace(
            "mesocycle_days = 7\n", "mesocycle_days = 7\nnonsense = 1\n"
        )
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "nonsense"

    def test_workout_unknown_key(self) -> None:
        text = BASE.replace(
            'prescription = "30 minutes easy."\n',
            'prescription = "30 minutes easy."\nnonsense = 1\n',
        )
        problem = _one(text)
        assert problem.entry == "workout[1] (id w1-mon)" and problem.field == "nonsense"

    def test_amendment_unknown_key(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "test"
nonsense = 1

[[amendment.update]]
id = "w1-mon"
title = "Renamed"
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1]" and problem.field == "nonsense"

    def test_override_unknown_key(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
stems = ["x"]
nonsense = 1
"""
        )
        problem = _one(text)
        assert (
            problem.entry == "override[0] (id w1-mon)" and problem.field == "nonsense"
        )


# ===========================================================================
# CRLF normalised; control characters rejected.
# ===========================================================================


class TestCRLFNormalization:
    def test_crlf_normalised_in_prescription(self) -> None:
        text = BASE.replace(
            'prescription = "30 minutes easy."',
            'prescription = "Warm-up.\\r\\nMain set.\\r\\nCool-down."',
        )
        block = parse_block(text, block_id="test-block")
        row = block.original.rows[0]
        assert row.prescription == "Warm-up.\nMain set.\nCool-down."
        assert "\r" not in row.prescription


class TestMultiLineTrailingNewline:
    """Controller decision (review round 1, 2026-09-16): a TOML `\"\"\"`
    value written with its closing quotes on their own line carries a
    trailing `\\n` that is a layout artifact, not prose -- stripped after
    CRLF normalisation, before the non-empty check."""

    def test_trailing_newline_before_closing_quotes_is_stripped(self) -> None:
        text = BASE.replace(
            'goal = "Goal text."',
            'goal = """\nLine one.\nLine two.\n"""',
        )
        block = parse_block(text, block_id="test-block")
        assert block.goal == "Line one.\nLine two."
        assert not block.goal.endswith("\n")

    def test_leading_whitespace_is_preserved(self) -> None:
        """Regression (review round 2): only the trailing `\\n` before the
        closing `\"\"\"` is a layout artifact. Leading whitespace on a
        line -- an indented list item, say -- is prose, not layout, and
        must survive (`.strip()` would wrongly remove it too)."""
        text = BASE.replace(
            'goal = "Goal text."',
            'goal = """\n  - indented item\nsecond line\n"""',
        )
        block = parse_block(text, block_id="test-block")
        assert block.goal == "  - indented item\nsecond line"


class TestControlCharacter:
    """The disallowed-character rule is deliberately the same character
    class `page.yaml_string` (design PageVocabulary) rejects --
    `str.isprintable()`, excepting `\\n`/`\\t` -- so that class of
    render-time failure cannot arise from a source this parser accepted
    (addendum to this task, 2026-09-16). `page.py` does not exist yet
    (task 3.1), so this module cannot import or exercise it; the claim is
    about the two character classes matching by construction, not about a
    render having been run."""

    def test_bell_character_rejected_in_title(self) -> None:
        text = BASE.replace('title = "Easy run"', 'title = "Easy run \\u0007"')
        problem = _one(text)
        assert problem.entry == "workout[1] (id w1-mon)" and problem.field == "title"
        assert "U+0007" in problem.message

    def test_no_break_space_rejected_in_goal(self) -> None:
        """A no-break space (U+00A0) is not an ASCII control character --
        the old `ord(char) < 0x20` rule would have missed it -- but it is
        not `str.isprintable()`, and `page.yaml_string` rejects it too."""
        text = BASE.replace('goal = "Goal text."', 'goal = "Goal\\u00a0text."')
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "goal"
        assert "U+00A0" in problem.message

    def test_tab_allowed_in_prescription(self) -> None:
        text = BASE.replace(
            'prescription = "30 minutes easy."',
            'prescription = "Warm-up\\tmain set\\tcool-down."',
        )
        block = parse_block(text, block_id="test-block")
        assert block.original.rows[0].prescription == "Warm-up\tmain set\tcool-down."


# ===========================================================================
# Required top-level fields; empty strings.
# ===========================================================================


class TestRequiredTopLevelFields:
    def test_missing_title(self) -> None:
        text = BASE.replace('title = "Base"\n', "")
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "title"
        assert "required" in problem.message

    def test_empty_goal(self) -> None:
        text = BASE.replace('goal = "Goal text."', 'goal = "   "')
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "goal"
        assert "empty" in problem.message


# ===========================================================================
# Sport / modality vocabulary.
# ===========================================================================


class TestSportVocabulary:
    def test_invalid_sport_lists_the_seven(self) -> None:
        text = BASE.replace('sport = "Run"', 'sport = "Football"')
        problem = _one(text)
        assert problem.entry == "workout[1] (id w1-mon)" and problem.field == "sport"
        for name in ("Run", "Ride", "Swim", "Walk", "Hike", "Rowing", "Workout"):
            assert name in problem.message

    def test_lowercase_sport_rejected(self) -> None:
        text = BASE.replace('sport = "Run"', 'sport = "run"')
        problem = _one(text)
        assert problem.field == "sport"


class TestModalityRule:
    def test_modality_rejected_for_non_workout_sport(self) -> None:
        text = BASE.replace(
            'sport = "Run"\n',
            'sport = "Run"\nmodality = "run"\n',
        )
        problem = _one(text)
        assert problem.field == "modality"
        assert "Workout" in problem.message

    def test_modality_vocabulary(self) -> None:
        text = BASE.replace('sport = "Run"\n', 'sport = "Workout"\nmodality = "yoga"\n')
        problem = _one(text)
        assert problem.field == "modality"
        for name in ("run", "bike", "swim", "strength", "other"):
            assert name in problem.message

    def test_modality_allowed_with_workout_sport(self) -> None:
        text = BASE.replace(
            'sport = "Run"\n', 'sport = "Workout"\nmodality = "strength"\n'
        )
        block = parse_block(text, block_id="test-block")
        row = block.original.rows[0]
        assert row.sport.value == "Workout"
        assert row.modality is not None and row.modality.value == "strength"

    def test_invalid_sport_does_not_also_report_modality(self) -> None:
        """When `sport` itself fails to parse, the modality-vs-sport rule
        must not fire a second, dependent problem off the resulting
        `sport_value is None` -- only the sport problem is reported."""
        text = BASE.replace(
            'sport = "Run"\n',
            'sport = "Football"\nmodality = "run"\n',
        )
        problems = _raises(text)
        assert len(problems) == 1
        assert problems[0].field == "sport"


class TestIndoorType:
    def test_indoor_must_be_bool(self) -> None:
        text = BASE.replace('sport = "Run"\n', 'sport = "Run"\nindoor = "yes"\n')
        problem = _one(text)
        assert problem.field == "indoor"


# ===========================================================================
# Single-line fields; identifiers; duplicate ids.
# ===========================================================================


class TestSingleLineFields:
    def test_title_with_line_break_rejected(self) -> None:
        text = BASE.replace('title = "Easy run"', 'title = "Easy\\nrun"')
        problem = _one(text)
        assert problem.field == "title"
        assert "single line" in problem.message

    def test_empty_summary_rejected(self) -> None:
        text = BASE.replace('summary = "Zone 2"', 'summary = "   "')
        problem = _one(text)
        assert problem.field == "summary"

    def test_empty_prescription_rejected(self) -> None:
        text = BASE.replace('prescription = "30 minutes easy."', 'prescription = "   "')
        problem = _one(text)
        assert problem.field == "prescription"


class TestIdentifiers:
    def test_bad_id_format_rejected(self) -> None:
        text = BASE.replace('id = "w1-mon"', 'id = "W1_Mon"')
        problems = _raises(text)
        assert any(
            p.field == "id" and "lowercase identifier" in p.message for p in problems
        )

    def test_reserved_block_id_rejected(self) -> None:
        problem = _one(BASE, block_id="agents")
        assert problem.entry == "block" and problem.field == "id"
        assert "agents" in problem.message.lower()

    def test_bad_block_id_format_rejected(self) -> None:
        problem = _one(BASE, block_id="Not_Valid")
        assert problem.entry == "block" and problem.field == "id"

    def test_duplicate_ids_named_at_both_entries(self) -> None:
        text = BASE.replace(
            'prescription = "30 minutes easy."\n',
            'prescription = "30 minutes easy."\n\n'
            "[[workout]]\n"
            'id = "w1-mon"\n'
            "date = 2026-03-03\n"
            'sport = "Run"\n'
            'title = "Another run"\n'
            'summary = "Zone 2"\n'
            'prescription = "30 minutes easy."\n',
        )
        problems = _raises(text)
        assert len(problems) == 1
        problem = problems[0]
        assert problem.entry == "workout[2] (id w1-mon)"
        assert "workout[1]" in problem.message


# ===========================================================================
# Mesocycle targets: shape and delegated range/duplicate checks.
# ===========================================================================


class TestMesocycleTargetShape:
    def test_mesocycle_as_plain_table_rejected(self) -> None:
        text = BASE.replace(
            "mesocycle_days = 7\n",
            "mesocycle_days = 7\n\n[mesocycle]\nnumber = 1\n",
        )
        problem = _one(text)
        assert problem.entry == "block" and problem.field == "mesocycle"
        assert "array of tables" in problem.message

    def test_target_load_must_be_positive(self) -> None:
        text = BASE.replace(
            "mesocycle_days = 7\n",
            "mesocycle_days = 7\n\n[[mesocycle]]\nnumber = 1\ntarget_load = 0\n",
        )
        problem = _one(text)
        assert problem.entry == "mesocycle[0]" and problem.field == "target_load"

    def test_focus_must_be_single_line(self) -> None:
        text = BASE.replace(
            "mesocycle_days = 7\n",
            'mesocycle_days = 7\n\n[[mesocycle]]\nnumber = 1\nfocus = "a\\nb"\n',
        )
        problem = _one(text)
        assert problem.entry == "mesocycle[0]" and problem.field == "focus"

    def test_number_out_of_range_delegated_to_model(self) -> None:
        text = BASE.replace(
            "mesocycle_days = 7\n",
            "mesocycle_days = 7\n\n[[mesocycle]]\nnumber = 5\n",
        )
        problem = _one(text)
        assert problem.entry == "mesocycle[5]" and problem.field == "number"

    def test_target_load_must_be_a_number_not_a_bool(self) -> None:
        text = BASE.replace(
            "mesocycle_days = 7\n",
            "mesocycle_days = 7\n\n[[mesocycle]]\nnumber = 1\ntarget_load = true\n",
        )
        problem = _one(text)
        assert problem.entry == "mesocycle[0]" and problem.field == "target_load"
        assert "number" in problem.message

    def test_target_load_and_focus_typed_before_bad_number_stops_target(self) -> None:
        """`number`, `target_load` and `focus` are each independently typed
        even when `number` itself is malformed: a bad `number` only stops
        the entry from becoming a `MesocycleTarget` (so it is excluded from
        `check_targets`), it does not stop `target_load`/`focus` from being
        checked too."""
        text = BASE.replace(
            "mesocycle_days = 7\n",
            'mesocycle_days = 7\n\n[[mesocycle]]\nnumber = "one"\nfocus = 5\n',
        )
        problems = _raises(text)
        assert len(problems) == 2
        assert problems[0].entry == "mesocycle[0]" and problems[0].field == "number"
        assert problems[1].entry == "mesocycle[0]" and problems[1].field == "focus"


# ===========================================================================
# Row bounds and modality-vs-sport for original rows (delegation split).
# ===========================================================================


class TestRowBounds:
    def test_row_out_of_bounds_delegated_to_model(self) -> None:
        text = BASE.replace("date = 2026-03-02\n", "date = 2027-01-01\n")
        problem = _one(text)
        assert problem.entry == "workout[1] (id w1-mon)" and problem.field == "date"
        assert "outside" in problem.message

    def test_row_problem_precedes_target_problem(self) -> None:
        """Document order (module docstring, design Contracts postcondition):
        rows before targets. Both problems here are delegated (`check_rows`,
        `check_targets`), so this pins the *order the two delegated calls
        are merged in*, not merely that both fire."""
        text = BASE.replace("date = 2026-03-02\n", "date = 2027-01-01\n").replace(
            "mesocycle_days = 7\n",
            "mesocycle_days = 7\n\n[[mesocycle]]\nnumber = 99\n",
        )
        problems = _raises(text)
        assert len(problems) == 2
        assert (
            problems[0].entry == "workout[1] (id w1-mon)"
            and problems[0].field == "date"
        )
        assert problems[1].entry == "mesocycle[99]" and problems[1].field == "number"

    def test_row_with_unparseable_date_does_not_manufacture_a_bounds_problem(
        self,
    ) -> None:
        """Regression (review round 3): a row whose `date` itself fails to
        parse (`workout[1]`, quoted here) is still included in the list
        `check_rows` receives, using a placeholder date equal to the
        block's own `starts` -- position-preserving, per the module
        docstring -- so it must report exactly its own "write it unquoted"
        problem and nothing else: no second, fabricated "date is outside
        bounds" finding for the same row from the placeholder. A second,
        genuinely out-of-bounds row (`workout[2]`) still gets its own real
        bounds finding, correctly labelled `workout[2]`, not shifted."""
        text = """\
title = "Base"
starts = 2026-03-02
ends = 2026-03-08
goal = "Goal text."
mesocycle_days = 7

[[workout]]
id = "w1-mon"
date = "2026-03-02"
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."

[[workout]]
id = "w1-tue"
date = 2027-01-01
sport = "Run"
title = "Easy run"
summary = "Zone 2"
prescription = "30 minutes easy."
"""
        problems = _raises(text)
        assert len(problems) == 2
        assert problems[0].entry == "workout[1] (id w1-mon)"
        assert problems[0].field == "date"
        assert "unquoted" in problems[0].message
        assert problems[1].entry == "workout[2] (id w1-tue)"
        assert problems[1].field == "date"
        assert "outside" in problems[1].message


# ===========================================================================
# Amendment ops: update, add, remove, mesocycle target.
# ===========================================================================


class TestAmendmentUpdateOp:
    def test_update_unknown_field_is_a_problem(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Adjust"

[[amendment.update]]
id = "w1-mon"
nope = "value"
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].update[0] (id w1-mon)"
        assert problem.field == "nope"

    def test_update_field_with_invalid_sport_vocabulary(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Adjust"

[[amendment.update]]
id = "w1-mon"
sport = "Football"
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].update[0] (id w1-mon)"
        assert problem.field == "sport"

    def test_update_field_with_invalid_modality_vocabulary(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Adjust"

[[amendment.update]]
id = "w1-mon"
modality = "yoga"
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].update[0] (id w1-mon)"
        assert problem.field == "modality"
        for name in ("run", "bike", "swim", "strength", "other"):
            assert name in problem.message

    def test_update_changes_no_field_delegated_to_model(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Adjust"

[[amendment.update]]
id = "w1-mon"
title = "Easy run"
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].update[0] (id w1-mon)"
        assert "changes no field" in problem.message


class TestAmendmentAddOp:
    def test_add_out_of_bounds_yields_exactly_one_problem(self) -> None:
        """Division of labour (module docstring, 2.2's Implementation Note):
        the parser must not duplicate the bounds check for an add row --
        `PlanModel.apply_amendments` alone reports it."""
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Add a session out of bounds"

[[amendment.add]]
id = "w1-far"
date = 2027-01-01
sport = "Run"
title = "Too far out"
summary = "Zone 2"
prescription = "30 minutes easy."
"""
        )
        problems = _raises(text)
        assert len(problems) == 1
        assert problems[0].field == "date"
        assert "outside" in problems[0].message

    def test_add_modality_without_workout_sport_delegated_to_model(self) -> None:
        """Parser does not enforce modality-only-with-Workout for add rows;
        the model does, via the same bounds-problem helper."""
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Add a strength-tagged run"

[[amendment.add]]
id = "w1-added"
date = 2026-03-04
sport = "Run"
modality = "run"
title = "Odd row"
summary = "Zone 2"
prescription = "30 minutes easy."
"""
        )
        problems = _raises(text)
        assert len(problems) == 1
        assert problems[0].field == "modality"
        assert "amendment[1].add[0]" in problems[0].entry

    def test_add_missing_required_key(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Add"

[[amendment.add]]
id = "w1-added"
date = 2026-03-04
sport = "Run"
title = "Missing fields"
"""
        )
        problems = _raises(text)
        assert any(
            p.entry == "amendment[1].add[0] (id w1-added)"
            and p.field in ("summary", "prescription")
            for p in problems
        )

    def test_add_row_id_must_be_a_valid_identifier(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Add"

[[amendment.add]]
id = "W1_Added"
date = 2026-03-04
sport = "Run"
title = "Bad id"
summary = "Zone 2"
prescription = "30 minutes easy."
"""
        )
        problems = _raises(text)
        assert any(
            p.entry == "amendment[1].add[0] (id W1_Added)"
            and p.field == "id"
            and "lowercase identifier" in p.message
            for p in problems
        )


class TestAmendmentRemoveOp:
    def test_remove_missing_id(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Remove"

[[amendment.remove]]
nope = 1
"""
        )
        problems = _raises(text)
        assert any(
            p.entry == "amendment[1].remove[0]" and p.field == "id" for p in problems
        )


class TestAmendmentTargetOp:
    def test_target_op_unknown_key(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Retarget"

[[amendment.mesocycle]]
number = 1
nope = 1
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].target[0]" and problem.field == "nope"

    def test_target_op_neither_stated_delegated_to_model(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Retarget"

[[amendment.mesocycle]]
number = 1
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].target[0] (mesocycle 1)"
        assert "target_load" in problem.message

    def test_target_op_missing_number(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Retarget"

[[amendment.mesocycle]]
focus = "Base"
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1].target[0]" and problem.field == "number"
        assert "required" in problem.message


class TestAmendmentShapeStandalone:
    def test_missing_reason_alone(self) -> None:
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
"""
        )
        problem = _one(text)
        assert problem.entry == "amendment[1]" and problem.field == "reason"
        assert "required" in problem.message

    def test_shape_faulty_amendments_own_parsed_date_seeds_the_placeholder(
        self,
    ) -> None:
        """A shape-faulty amendment whose own `date` *did* parse (only
        `reason` is missing here, dated 2026-02-15) uses that real date
        for its placeholder, not the running "last known good" date --
        so a later amendment genuinely dated *before* it (2026-02-10) is
        still correctly reported as out of order: two problems, not one
        (amendment[1]'s own missing `reason`, and amendment[2]'s real
        date-order violation against amendment[1]'s real, parsed date)."""
        text = (
            BASE
            + """
[[amendment]]
date = 2026-02-15

[[amendment]]
date = 2026-02-10
reason = "Actually earlier than amendment 1"
"""
        )
        problems = _raises(text)
        assert len(problems) == 2
        assert problems[0].entry == "amendment[1]" and problems[0].field == "reason"
        assert problems[1].entry == "amendment[2]" and problems[1].field == "date"
        assert "2026-02-15" in problems[1].message

    def test_shape_faulty_amendments_seed_is_not_the_blocks_starts(self) -> None:
        """Regression (review round 1): when a shape-faulty amendment's own
        `date` does *not* parse (missing here, so there is no real date to
        prefer), the placeholder falls back to the running "last known
        good" date -- seeded at `date.min`, never at the block's own
        `starts`. `starts` here is 2026-03-02; seeding at `starts` would
        make the next amendment's entirely valid, earlier date (2026-02-20)
        look "before the previous amendment's date"."""
        text = (
            BASE
            + """
[[amendment]]
reason = "No date stated"

[[amendment]]
date = 2026-02-20
reason = "Dated before the block even starts, and before amendment 1's \
(unstated) date -- but amendment 1 has no real date to be after"
"""
        )
        problems = _raises(text)
        assert len(problems) == 1
        assert problems[0].entry == "amendment[1]" and problems[0].field == "date"

    def test_running_date_advances_past_a_dated_shape_faulty_amendment(self) -> None:
        """Regression (review round 2): `running_date` must actually
        *advance* to a shape-faulty amendment's own placeholder date once
        that date is known (`amendment[1]` here, dated 2026-03-05, missing
        only `reason`), not just use it for that one amendment's own
        placeholder -- otherwise a *later* shape-faulty amendment with no
        date of its own (`amendment[2]`) falls back to a stale running
        date and can be reported as spuriously out of order against
        `amendment[1]`'s real date. Exactly two problems: each
        amendment's own single shape fault, nothing manufactured."""
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-05

[[amendment]]
reason = "No date stated"
"""
        )
        problems = _raises(text)
        assert len(problems) == 2
        assert problems[0].entry == "amendment[1]" and problems[0].field == "reason"
        assert problems[1].entry == "amendment[2]" and problems[1].field == "date"

    def test_running_date_carries_to_a_third_valid_amendment(self) -> None:
        """Extends the regression above: a third, *valid* amendment dated
        earlier than amendment[1]'s real date (2026-03-05) is still
        correctly reported as out of order, because the no-date
        amendment[2]'s placeholder inherited amendment[1]'s real date as
        the running date, rather than resetting it."""
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-05

[[amendment]]
reason = "No date stated"

[[amendment]]
date = 2026-03-04
reason = "Earlier than amendment 1's real date"
"""
        )
        problems = _raises(text)
        assert len(problems) == 3
        assert problems[0].entry == "amendment[1]" and problems[0].field == "reason"
        assert problems[1].entry == "amendment[2]" and problems[1].field == "date"
        assert problems[2].entry == "amendment[3]" and problems[2].field == "date"
        assert "2026-03-05" in problems[2].message


# ===========================================================================
# Overrides: form, exclusivity, and the "not checked" case.
# ===========================================================================


class TestOverrideForm:
    def test_stems_and_skipped_are_mutually_exclusive(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
stems = ["a"]
skipped = true
"""
        )
        problem = _one(text)
        assert problem.entry == "override[0] (id w1-mon)"
        assert "mutually exclusive" in problem.message

    def test_neither_stems_nor_skipped_is_a_problem(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
"""
        )
        problem = _one(text)
        assert "one of stems or skipped" in problem.message

    def test_skipped_false_is_rejected(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
skipped = false
"""
        )
        problems = _raises(text)
        assert any(
            p.field == "skipped" and "must be true" in p.message for p in problems
        )

    def test_duplicate_stems_rejected(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
stems = ["a", "a"]
"""
        )
        problem = _one(text)
        assert problem.field == "stems"
        assert "more than once" in problem.message

    def test_reason_with_line_break_rejected(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
stems = ["a"]
reason = "line one\\nline two"
"""
        )
        problem = _one(text)
        assert problem.field == "reason"
        assert "single line" in problem.message

    def test_empty_stems_rejected(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "w1-mon"
stems = []
"""
        )
        problem = _one(text)
        assert problem.field == "stems"

    def test_override_unknown_id_delegated_to_model(self) -> None:
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "no-such-row"
stems = ["a"]
"""
        )
        problem = _one(text)
        assert problem.entry == "override[0] (id no-such-row)"
        assert "no row with id" in problem.message

    def test_shape_faulty_override_does_not_relabel_a_later_ones_finding(self) -> None:
        """Regression (review round 1): a shape-faulty override used to be
        dropped entirely from the list handed to `check_overrides`, so a
        later override's genuine "unknown id" finding was mislabeled with
        the wrong, shifted 0-based index. `override[0]` here has a quoted
        (shape-invalid) date; `override[1]` is shape-valid but references
        an id that does not exist -- its problem must still say
        `override[1]`, never `override[0]`."""
        text = (
            BASE
            + """
[[override]]
date = "2026-03-02"
id = "w1-mon"
stems = ["a"]

[[override]]
date = 2026-03-02
id = "no-such-row"
stems = ["b"]
"""
        )
        problems = _raises(text)
        assert len(problems) == 2
        assert (
            problems[0].entry == "override[0] (id w1-mon)"
            and problems[0].field == "date"
        )
        assert problems[1].entry == "override[1] (id no-such-row)"
        assert problems[1].field == "row_id"
        assert "no row with id" in problems[1].message

    def test_stems_fault_does_not_suppress_the_unknown_id_finding(self) -> None:
        """Regression (review round 2): only a `date`/`id` shape fault
        marks an override as excluded from `check_overrides`'s findings --
        a `stems` fault must not. This override's `date` and `id` both
        parse fine (the id just doesn't exist), so its genuine "unknown
        id" finding must still be reported alongside its own `stems`
        problem: two independently determinable problems, not one."""
        text = (
            BASE
            + """
[[override]]
date = 2026-03-02
id = "no-such-row"
stems = ["a", "a"]
"""
        )
        problems = _raises(text)
        assert len(problems) == 2
        assert problems[0].entry == "override[0] (id no-such-row)"
        assert problems[0].field == "stems"
        assert "more than once" in problems[0].message
        assert problems[1].entry == "override[0] (id no-such-row)"
        assert problems[1].field == "row_id"
        assert "no row with id" in problems[1].message


class TestOverridesNotCheckedAfterInvalidAmendment:
    def test_invalid_amendment_suppresses_override_check(self) -> None:
        """An override referencing a row the failed amendment would have
        added must never be reported as an unknown-id problem: overrides
        are simply "not checked" once an amendment is invalid."""
        text = (
            BASE
            + """
[[amendment]]
date = 2026-03-03
reason = "Add a session, badly"

[[amendment.add]]
id = "w1-added"
date = 2026-03-04
sport = "Run"
title = "Broken"
summary = "Zone 2"
nope = "unknown field makes this op invalid, but that alone isn't enough"
prescription = "30 minutes easy."

[[amendment.remove]]
id = "no-such-row"

[[override]]
date = 2026-03-05
id = "w1-added"
stems = ["a"]
"""
        )
        problems = _raises(text)
        # The add op's unknown key, the remove op's unknown id -- both from
        # this single (invalid) amendment -- plus one "not checked" problem
        # for the override. Never a spurious "no row with id w1-added".
        assert not any(
            "w1-added" in p.entry and "no row" in p.message for p in problems
        )
        not_checked = [p for p in problems if p.entry == "override[0..0]"]
        assert len(not_checked) == 1
        assert "not checked" in not_checked[0].message


# ===========================================================================
# `load_block`: the one file read.
# ===========================================================================


class TestLoadBlock:
    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.toml"
        with pytest.raises(PlanValidationError) as excinfo:
            load_block(path, block_id="test-block")
        problems = excinfo.value.problems
        assert len(problems) == 1
        assert problems[0].entry == "file"

    def test_non_utf8_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bad-encoding.toml"
        path.write_bytes(b"title = \xff\xfe invalid utf8")
        with pytest.raises(PlanValidationError) as excinfo:
            load_block(path, block_id="test-block")
        problems = excinfo.value.problems
        assert len(problems) == 1
        assert problems[0].entry == "file"
        assert "UTF-8" in problems[0].message

    def test_non_toml_file(self, tmp_path: Path) -> None:
        path = tmp_path / "not-toml.toml"
        path.write_text("this is : not [ valid toml")
        with pytest.raises(PlanValidationError) as excinfo:
            load_block(path, block_id="test-block")
        problems = excinfo.value.problems
        assert len(problems) == 1
        assert problems[0].entry == "file"

    def test_valid_file_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "minimal.toml"
        path.write_text((FIXTURES / "minimal.toml").read_text())
        block = load_block(path, block_id="minimal-block")
        assert block.id == "minimal-block"
