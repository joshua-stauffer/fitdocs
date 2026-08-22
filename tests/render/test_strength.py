"""Strength set grouping, rest attribution, and sets-table rendering (task 3.5).

These pin :mod:`fitdocs.render.strength` against the approved StrengthRenderer
interface (design §StrengthRenderer; reference §4 ``set | reps | load | rest``)
and the missing-data-honesty rules (Req 9.2, 9.3, 9.4, 9.6, 13.3).

Grouping and rest attribution are proven against **synthetic** ``StrengthSet``
tuples constructed directly over the model dataclass, so multi-set runs, a
non-consecutive same-name run (A, B, A), an unresolved-name group, and the
active/rest/active attribution case are each asserted exactly. Blanks-vs-zeros
and end-to-end grouping are additionally proven against the real parsed strength
fixture (``parse_fit``), whose sets carry a recorded ``0.0`` kg bodyweight set (a
true zero) and an unresolvable exercise name (``None``).
"""

from __future__ import annotations

from fitdocs import parse_fit
from fitdocs.model import StrengthSet
from fitdocs.render.format import ABSENT
from fitdocs.render.strength import (
    ExerciseGroup,
    SetRow,
    group_sets,
    sets_section,
)
from tests.fixtures import builder


def _set(
    set_type: str | None = "active",
    *,
    duration_s: float | None = None,
    repetitions: int | None = None,
    weight_kg: float | None = None,
    exercise_name: str | None = None,
    message_index: int = 0,
) -> StrengthSet:
    """A ``StrengthSet`` with test-relevant fields set and the rest at ``None``."""
    return StrengthSet(
        set_type=set_type,
        start_time=None,
        duration_s=duration_s,
        repetitions=repetitions,
        weight_kg=weight_kg,
        category=None,
        exercise_name=exercise_name,
        message_index=message_index,
    )


# --- group_sets: grouping by consecutive resolved name -----------------------


def test_three_consecutive_active_same_name_is_one_group() -> None:
    """Three consecutive active sets sharing a name -> ONE group, three rows,
    numbered 1..3 within the exercise (Req 9.2)."""
    sets = (
        _set(exercise_name="squat", repetitions=5, weight_kg=100.0),
        _set(exercise_name="squat", repetitions=5, weight_kg=100.0),
        _set(exercise_name="squat", repetitions=3, weight_kg=110.0),
    )
    groups = group_sets(sets)

    assert len(groups) == 1
    group = groups[0]
    assert group.name == "squat"
    assert tuple(row.number for row in group.rows) == (1, 2, 3)
    assert group.rows[0].reps == 5
    assert group.rows[2].weight_kg == 110.0


def test_name_change_starts_a_new_group() -> None:
    """When the resolved name changes, a new group begins (Req 9.2)."""
    sets = (
        _set(exercise_name="squat", repetitions=5),
        _set(exercise_name="deadlift", repetitions=3),
    )
    groups = group_sets(sets)

    assert [g.name for g in groups] == ["squat", "deadlift"]
    assert all(len(g.rows) == 1 for g in groups)
    # Row numbering restarts per group.
    assert groups[0].rows[0].number == 1
    assert groups[1].rows[0].number == 1


def test_non_consecutive_same_name_is_not_merged() -> None:
    """A, B, A produces THREE groups -- non-consecutive same-name runs are never
    merged back together (Req 9.2)."""
    sets = (
        _set(exercise_name="bench", repetitions=8),
        _set(exercise_name="row", repetitions=8),
        _set(exercise_name="bench", repetitions=6),
    )
    groups = group_sets(sets)

    assert [g.name for g in groups] == ["bench", "row", "bench"]
    assert all(len(g.rows) == 1 for g in groups)


def test_unresolved_name_groups_under_none_no_guess() -> None:
    """An active set with ``exercise_name is None`` groups under a ``name=None``
    ExerciseGroup and never acquires a guessed name (Req 9.3)."""
    sets = (_set(exercise_name=None, repetitions=12, weight_kg=20.0),)
    groups = group_sets(sets)

    assert len(groups) == 1
    assert groups[0].name is None
    assert len(groups[0].rows) == 1


# --- group_sets: rest attribution --------------------------------------------


def test_rest_attributes_to_preceding_active_and_is_not_a_row() -> None:
    """active, rest, active -> the rest's duration lands in the FIRST active
    set's ``rest_s``; the rest set is NOT its own row (Req 9.2)."""
    sets = (
        _set(exercise_name="press", repetitions=5, weight_kg=40.0),
        _set(set_type="rest", duration_s=90.0),
        _set(exercise_name="press", repetitions=5, weight_kg=40.0),
    )
    groups = group_sets(sets)

    # Same name across the rest -> one group, two rows (rest is not a row).
    assert len(groups) == 1
    rows = groups[0].rows
    assert len(rows) == 2
    assert rows[0].rest_s == 90.0
    assert rows[1].rest_s is None


def test_rest_attributes_to_last_active_across_group_boundary() -> None:
    """A rest following the last active of one exercise attributes to that
    exercise's final row, even when the next active starts a new group."""
    sets = (
        _set(exercise_name="curl", repetitions=10),
        _set(set_type="rest", duration_s=60.0),
        _set(exercise_name="extension", repetitions=10),
    )
    groups = group_sets(sets)

    assert [g.name for g in groups] == ["curl", "extension"]
    assert groups[0].rows[0].rest_s == 60.0
    assert groups[1].rows[0].rest_s is None


def test_leading_rest_with_no_preceding_active_is_dropped() -> None:
    """A rest set with no preceding active set is dropped, never a phantom row."""
    sets = (
        _set(set_type="rest", duration_s=30.0),
        _set(exercise_name="squat", repetitions=5),
    )
    groups = group_sets(sets)

    assert len(groups) == 1
    assert groups[0].name == "squat"
    assert len(groups[0].rows) == 1
    assert groups[0].rows[0].rest_s is None


# --- sets_section: blanks vs recorded zeros ----------------------------------


def test_recorded_zero_weight_renders_genuine_load() -> None:
    """A recorded ``0.0`` kg (bodyweight) renders ``0 kg`` -- a genuine value,
    NOT blank (Req 9.4, 13.3)."""
    out = sets_section((_set(exercise_name="push_up", repetitions=15, weight_kg=0.0),))

    assert "0 kg" in out
    # The load cell is the genuine zero, never the absence marker.
    load_cell = out.splitlines()[-1].split("|")[3].strip()
    assert load_cell == "0 kg"
    assert load_cell != ABSENT


def test_unrecorded_fields_render_blank() -> None:
    """Unrecorded ``weight_kg``/``repetitions`` (``None``) render as the absence
    marker, not a fabricated zero (Req 9.4, 13.3)."""
    out = sets_section(
        (_set(exercise_name="mystery", repetitions=None, weight_kg=None),)
    )

    row = out.splitlines()[-1]
    reps_cell = row.split("|")[2].strip()
    load_cell = row.split("|")[3].strip()
    assert reps_cell == ABSENT
    assert load_cell == ABSENT
    # A None weight must never be rendered as "0 kg".
    assert "0 kg" not in out


def test_rest_column_renders_attributed_duration() -> None:
    """The attributed rest duration renders in the ``rest`` column; an
    unattributed row's rest cell is blank (Req 9.2, 13.3)."""
    out = sets_section(
        (
            _set(exercise_name="dip", repetitions=8, weight_kg=0.0),
            _set(set_type="rest", duration_s=45.0),
        )
    )

    assert "0:45" in out
    rest_cell = out.splitlines()[-1].split("|")[4].strip()
    assert rest_cell == "0:45"


def test_table_uses_reference_column_order() -> None:
    """Columns follow reference §4: ``set | reps | load | rest`` (Req 9.2)."""
    out = sets_section((_set(exercise_name="squat", repetitions=5, weight_kg=100.0),))

    header = next(ln for ln in out.splitlines() if ln.lstrip().startswith("| Set"))
    labels = [c.strip() for c in header.strip().strip("|").split("|")]
    assert labels == ["Set", "Reps", "Load", "Rest"]


def test_unresolved_group_renders_unknown_exercise_label() -> None:
    """A ``name=None`` group renders under ``Unknown exercise`` with no guessed
    name (Req 9.3)."""
    out = sets_section((_set(exercise_name=None, repetitions=6, weight_kg=50.0),))

    assert "**Unknown exercise**" in out


# --- sets_section: no-sets omission ------------------------------------------


def test_empty_sets_section_is_omitted() -> None:
    """No sets at all -> the section is omitted entirely (Req 9.6)."""
    assert sets_section(()) == ""
    assert group_sets(()) == ()


def test_rest_only_sets_section_is_omitted() -> None:
    """Only rest sets (nothing to display) -> ``""`` -- never an empty scaffold
    (Req 9.6)."""
    sets = (
        _set(set_type="rest", duration_s=30.0),
        _set(set_type="rest", duration_s=45.0),
    )
    assert group_sets(sets) == ()
    assert sets_section(sets) == ""


def test_section_has_no_header_when_scaffold_would_be_empty() -> None:
    """The omission is total: no table header, no bold label, no whitespace."""
    out = sets_section(())
    assert "Set" not in out
    assert "Unknown exercise" not in out
    assert out == ""


# --- determinism -------------------------------------------------------------


def test_section_is_deterministic() -> None:
    """Identical input yields byte-identical section output (Req 13)."""
    sets = (
        _set(exercise_name="squat", repetitions=5, weight_kg=100.0),
        _set(set_type="rest", duration_s=90.0),
        _set(exercise_name="squat", repetitions=5, weight_kg=100.0),
    )
    assert sets_section(sets) == sets_section(sets)


# --- real parsed strength fixture --------------------------------------------


def test_real_fixture_groups_and_attributes() -> None:
    """The real strength fixture groups into bench (60 kg x 10), bodyweight
    push-up (0 kg x 15), and an unresolved group; the trailing rest attributes to
    the preceding (unresolved) active set's row and is not its own row."""
    sets = parse_fit(builder.strength_fit_bytes()).sets
    groups = group_sets(sets)

    # Three active sets with three distinct resolved names -> three groups.
    assert len(groups) == 3
    assert groups[0].name == "barbell_bench_press"
    assert groups[1].name == "alternating_staggered_push_up"
    assert groups[2].name is None  # unresolvable -> Unknown, never guessed

    # One row per active set; the rest set produced NO extra row.
    assert sum(len(g.rows) for g in groups) == 3

    bench = groups[0].rows[0]
    assert (bench.reps, bench.weight_kg, bench.rest_s) == (10, 60.0, None)

    pushup = groups[1].rows[0]
    assert (pushup.reps, pushup.weight_kg) == (15, 0.0)  # bodyweight true zero

    unknown = groups[2].rows[0]
    assert unknown.reps is None and unknown.weight_kg is None
    assert unknown.rest_s == 30.0  # trailing rest attributed here


def test_real_fixture_section_honours_blanks_and_zeros() -> None:
    """The rendered fixture section shows bodyweight ``0 kg``, whole ``60 kg``,
    the ``Unknown exercise`` label, the attributed rest, and blank cells for the
    unrecorded reps/load -- never a fabricated zero for missing data."""
    sets = parse_fit(builder.strength_fit_bytes()).sets
    out = sets_section(sets)

    assert "**barbell_bench_press**" in out
    assert "**alternating_staggered_push_up**" in out
    assert "**Unknown exercise**" in out
    assert "60 kg" in out
    assert "0 kg" in out  # genuine bodyweight zero
    assert "0:30" in out  # attributed rest

    # The unresolved active row: reps and load are blank (ABSENT), not zeros.
    unknown_block = out.split("**Unknown exercise**", 1)[1]
    data_row = unknown_block.strip().splitlines()[-1]
    cells = [c.strip() for c in data_row.strip().strip("|").split("|")]
    assert cells[1] == ABSENT  # reps blank
    assert cells[2] == ABSENT  # load blank


def test_group_and_row_types_are_frozen_dataclasses() -> None:
    """The public shapes are the approved frozen dataclasses (design contract)."""
    groups = group_sets((_set(exercise_name="squat", repetitions=5),))
    assert isinstance(groups[0], ExerciseGroup)
    assert isinstance(groups[0].rows[0], SetRow)
