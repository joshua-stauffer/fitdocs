"""The plan-source grammar (training-blocks spec). See "SourceParser"
(`src/fitdocs/plans/source.py`) in `.kiro/specs/training-blocks/design.md`.

`parse_block(text, *, block_id)` is pure over text: it parses `text` as
TOML, validates every rule the Plan-Source Grammar table states, and either
raises :class:`PlanValidationError` carrying every independently
determinable problem, or returns a fully assembled `Block`.
`load_block(path, *, block_id)` reads `path`'s bytes, decodes UTF-8, and
delegates -- this is the package's only file read (Req 1.1, 1.2, 3.9).

**Shape validation, then delegation.** Every rule this module can decide
from a table's own keys and value types -- required fields, types, single-
vs multi-line strings, control characters, vocabulary membership,
identifier form, unknown keys -- is checked here, over the *whole*
document, before anything is handed to `PlanModel`. Three faults are
structural (the top-level table is malformed in a way `tomllib` itself
already prevents from occurring for any text that parses; `starts`/`ends`
missing, mistyped, or reversed; `mesocycle_days` missing or not a positive
integer): every later rule needs the block's bounds and mesocycle length,
so these three, and only these three, stop parsing outright. Every other
shape problem is collected and parsing continues, because the grammar's
promise is "every independently determinable problem at once" (Req 2.2).
Once shape validation completes without a structural fault, this module
delegates to `fitdocs.plans.model`'s pure checks -- `check_rows`,
`check_targets`, `apply_amendments`, `check_overrides` -- and merges their
problems after the shape problems, in that order (Req 2.1-2.10, 3.3-3.8).

**Division of labour with `[[amendment.add]]` rows** (see model.py's task
2.2 Implementation Note): this module checks only an added row's *shape* --
types, required keys, unknown keys, single-line fields, sport and modality
*vocabulary* membership, `indoor` typing -- and builds the `PlannedWorkout`.
The date-in-bounds rule and the "`modality` only with `Sport.WORKOUT`" rule
for an added row are `PlanModel.apply_amendments`'s alone (via
`_row_bounds_problem`), so this module never runs them a second time. For
an *original* `[[workout]]` row, by contrast, the design assigns the
modality-only-with-`Workout` rule to this module's shape validation and the
bounds rule to `PlanModel.check_rows` -- the two row kinds are checked by
different halves of the same rule set, and this module is careful never to
duplicate whichever half belongs to `PlanModel`.

**When an amendment is invalid, its overrides are not checked.**
`apply_amendments` truncates its returned `states` at the first invalid
amendment (see its docstring); calling `check_overrides` over that
truncated prefix would silently validate overrides against an
incomplete plan. Design does not name a single spelling for this
case, so this module's choice -- stated once here because
`build-training-block` and any later reader of a `PlanValidationError`
needs to know it: when `apply_amendments` reports any problem and the
source also has one or more `[[override]]` entries, this module reports
exactly one further problem, `entry="override[0..n-1]"` (`n` the override
count), saying overrides were not checked because an amendment was
invalid -- never a per-override "unknown id" problem manufactured from a
plan state that was never actually reached.

**Position-preserving placeholders.** `PlanModel.check_rows` and
`apply_amendments` name a problem by the *position* of the row or
amendment in the list this module hands them (`enumerate(..., start=1)`
inside `PlanModel`), so a row or amendment already excluded for its own
shape fault cannot simply be dropped from that list -- doing so would
relabel every later, otherwise-valid entry. A row whose `date` itself
failed to parse is included with a placeholder date equal to the block's
own `starts` (always in bounds, so the row carries exactly its own "write
it unquoted" shape problem and `check_rows` adds no second, fabricated
"date is outside bounds" finding for it -- pinned by
`TestRowBounds::test_row_with_unparseable_date_does_not_manufacture_a_bounds_problem`,
which also checks a genuinely out-of-bounds row after it keeps its own,
correctly numbered label). An amendment whose `date` or `reason` failed to parse is
included with an empty-`ops` placeholder: when the amendment's own `date`
*did* parse (only some other field, e.g. `reason`, was at fault), the
placeholder is dated at that real, parsed date, and the running "last
known good" date advances to it -- so a genuinely earlier, shape-faulty
amendment still cannot manufacture a spurious out-of-order-dates finding
against a real, later one. Only when `date` itself failed to parse does
the placeholder fall back to the running date, seeded at `date.min` (never
at `starts` -- an amendment dated before the block's own `starts` is
entirely valid, Req 3.5 requires only non-decreasing dates, so seeding at
`starts` was itself a source of spurious findings, fixed after review).

**Overrides get the full positional list too.** `check_overrides` names a
problem by a 0-based `enumerate` over whichever sequence it is given, so a
shape-faulty override cannot simply be dropped from that list either --
every override this module parses (using each field's own best-effort
placeholder when that field itself failed, exactly as `_parse_override`
already does for its return value) is passed to `check_overrides` in full
file order. Any problem `check_overrides` returns whose `entry` names an
index this module already flagged as having its own `date` or `id` shape
fault is discarded -- it can only be an artifact of that entry's
placeholder values, never a genuine finding about the source.
`PlanModel.check_targets`, by contrast, names a problem by the *value* of
`number`, not by list position; a mesocycle target whose own `number`
failed to parse carries no value to label a problem with, so it is simply
excluded (`check_targets` never sees it, and never needed to -- its own
shape problem already stands).

Only :func:`load_block` opens a file; :func:`parse_block` never touches
`Path`, the clock, or anything beyond the `str` it is given.
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from datetime import date as _date
from datetime import datetime as _datetime
from pathlib import Path
from typing import Final

from fitdocs.model import Modality, Sport
from fitdocs.plans.model import (
    IDENTIFIER,
    MUTABLE_FIELDS,
    AddOp,
    AmendmentOp,
    AmendmentSpec,
    Block,
    MesocycleTarget,
    Override,
    PlannedWorkout,
    PlanProblem,
    PlanState,
    RemoveOp,
    TargetOp,
    UpdateOp,
    apply_amendments,
    build_block,
    check_overrides,
    check_rows,
    check_targets,
    is_reserved_block_id,
    mesocycle_windows,
)

_WORKOUT_KEY: Final[str] = Sport.WORKOUT.value.lower()
"""The `[[workout]]` array-of-tables key. This plan's hard rules forbid
spelling the literal lowercase `"workout"` anywhere under
`src/fitdocs/plans/`, yet the source grammar's key for a planned-workout
row *is* that word -- so it is derived once from `Sport.WORKOUT.value`
(`"Workout"`) rather than spelled a second time, tying the TOML key to the
same enum member `sport = "Workout"` names."""

_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "title",
        "starts",
        "ends",
        "goal",
        "mesocycle_days",
        "mesocycle",
        _WORKOUT_KEY,
        "amendment",
        "override",
    }
)
_MESOCYCLE_KEYS: Final[frozenset[str]] = frozenset({"number", "target_load", "focus"})
_WORKOUT_ROW_REQUIRED: Final[frozenset[str]] = frozenset(
    {"id", "date", "sport", "title", "summary", "prescription"}
)
_WORKOUT_ROW_OPTIONAL: Final[frozenset[str]] = frozenset({"modality", "indoor"})
_WORKOUT_ROW_KEYS: Final[frozenset[str]] = _WORKOUT_ROW_REQUIRED | _WORKOUT_ROW_OPTIONAL
_AMENDMENT_KEYS: Final[frozenset[str]] = frozenset(
    {"date", "reason", "update", "add", "remove", "mesocycle"}
)
_UPDATE_KEYS: Final[frozenset[str]] = frozenset({"id", *MUTABLE_FIELDS})
_REMOVE_KEYS: Final[frozenset[str]] = frozenset({"id"})
_TARGET_OP_KEYS: Final[frozenset[str]] = frozenset({"number", "target_load", "focus"})
_OVERRIDE_KEYS: Final[frozenset[str]] = frozenset(
    {"date", "id", "stems", "skipped", "reason"}
)

_UNQUOTED_DATE_MESSAGE: Final[str] = "must be written unquoted, as YYYY-MM-DD"
_IDENTIFIER_MESSAGE: Final[str] = (
    "must be a lowercase identifier of letters, digits and hyphens, beginning "
    "with a letter or digit"
)


class PlanValidationError(Exception):
    """Raised by :func:`parse_block` and :func:`load_block` when the source
    holds one or more problems. `problems` is never empty (Req 2.1, 2.2)."""

    problems: tuple[PlanProblem, ...]

    def __init__(self, problems: tuple[PlanProblem, ...]) -> None:
        if not problems:
            raise ValueError("PlanValidationError requires at least one problem")
        super().__init__("; ".join(problem.describe() for problem in problems))
        self.problems = problems


# ---------------------------------------------------------------------------
# Atomic value validators. Each takes a raw TOML value and returns either the
# parsed value or a single `PlanProblem`, never both and never neither.
# ---------------------------------------------------------------------------


def _control_char_problem(value: str, *, entry: str, field: str) -> PlanProblem | None:
    """A character is disallowed exactly when `page.yaml_string` (design
    PageVocabulary) would refuse it at render time: `str.isprintable()` is
    false and it is neither `\\n` nor `\\t`. `isprintable()` covers every
    ASCII control character *and* the wider Unicode "Other"/"Separator"
    categories -- a no-break space (U+00A0) among them -- so nothing this
    parser accepts can later fail `yaml_string`'s own check (mirrors that
    module's character class deliberately; see this task's report,
    CONCERNS, for the design-wording gap this closes)."""
    for char in value:
        if char in ("\t", "\n"):
            continue
        if not char.isprintable():
            return PlanProblem(
                entry=entry,
                field=field,
                message=f"contains a disallowed character (U+{ord(char):04X})",
            )
    return None


def _single_line(
    value: object, *, entry: str, field: str
) -> tuple[str | None, PlanProblem | None]:
    if isinstance(value, bool) or not isinstance(value, str):
        return None, PlanProblem(entry=entry, field=field, message="must be a string")
    normalized = value.replace("\r\n", "\n")
    if "\n" in normalized:
        return None, PlanProblem(
            entry=entry, field=field, message="must be a single line"
        )
    problem = _control_char_problem(normalized, entry=entry, field=field)
    if problem is not None:
        return None, problem
    if not normalized.strip():
        return None, PlanProblem(entry=entry, field=field, message="must not be empty")
    return normalized, None


def _multi_line(
    value: object, *, entry: str, field: str
) -> tuple[str | None, PlanProblem | None]:
    """`goal` and `prescription` may span lines. A TOML `\"\"\"...\"\"\"`
    value written with its closing quotes on their own line carries a
    trailing `\\n` that is an artifact of how the author laid the TOML
    out, not part of the prose -- stripped here (controller decision,
    2026-09-16, recorded in this task's report) after CRLF normalisation
    and before the non-empty check, so a source that renders can never
    surprise a renderer with a blank trailing line."""
    if isinstance(value, bool) or not isinstance(value, str):
        return None, PlanProblem(entry=entry, field=field, message="must be a string")
    normalized = value.replace("\r\n", "\n").rstrip("\n")
    problem = _control_char_problem(normalized, entry=entry, field=field)
    if problem is not None:
        return None, problem
    if not normalized.strip():
        return None, PlanProblem(entry=entry, field=field, message="must not be empty")
    return normalized, None


def _as_date(
    value: object, *, entry: str, field: str
) -> tuple[_date | None, PlanProblem | None]:
    if isinstance(value, _date) and not isinstance(value, _datetime):
        return value, None
    return None, PlanProblem(entry=entry, field=field, message=_UNQUOTED_DATE_MESSAGE)


def _as_int(
    value: object, *, entry: str, field: str, minimum: int | None = None
) -> tuple[int | None, PlanProblem | None]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None, PlanProblem(entry=entry, field=field, message="must be an integer")
    if minimum is not None and value < minimum:
        return None, PlanProblem(
            entry=entry, field=field, message=f"must be at least {minimum}"
        )
    return value, None


def _as_bool(
    value: object, *, entry: str, field: str
) -> tuple[bool | None, PlanProblem | None]:
    if not isinstance(value, bool):
        return None, PlanProblem(
            entry=entry, field=field, message="must be true or false"
        )
    return value, None


def _as_target_load(
    value: object, *, entry: str, field: str
) -> tuple[float | None, PlanProblem | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, PlanProblem(entry=entry, field=field, message="must be a number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        return None, PlanProblem(
            entry=entry, field=field, message="must be finite and greater than 0"
        )
    return parsed, None


def _unknown_keys(
    table: Mapping[str, object], *, allowed: frozenset[str], entry: str
) -> list[PlanProblem]:
    return [
        PlanProblem(entry=entry, field=key, message="is not a recognised key")
        for key in sorted(table)
        if key not in allowed
    ]


def _as_array_of_tables(
    document: Mapping[str, object], key: str, *, entry: str
) -> tuple[list[Mapping[str, object]], PlanProblem | None]:
    if key not in document:
        return [], None
    value = document[key]
    if not isinstance(value, list):
        return [], PlanProblem(
            entry=entry, field=key, message="must be an array of tables"
        )
    for item in value:
        if not isinstance(item, dict):
            return [], PlanProblem(
                entry=entry, field=key, message="every entry must be a table"
            )
    return list(value), None


# ---------------------------------------------------------------------------
# Row parsing, shared between original `[[workout]]` rows and
# `[[amendment.add]]` rows (see module docstring: division of labour).
# ---------------------------------------------------------------------------


def _parse_workout_row(
    table: Mapping[str, object],
    *,
    entry_base: str,
    enforce_modality_sport_rule: bool,
    fallback_date: _date,
) -> tuple[PlannedWorkout, list[PlanProblem]]:
    """Parse one `[[workout]]`-shaped table. Returns the best-effort row (a
    placeholder in place of any field that failed to parse -- meaningless
    once `problems` is non-empty) and that row's own shape problems."""
    problems: list[PlanProblem] = []

    row_id: str | None = None
    if "id" not in table:
        problems.append(
            PlanProblem(entry=entry_base, field="id", message="is required")
        )
    else:
        row_id, problem = _single_line(table["id"], entry=entry_base, field="id")
        if problem is not None:
            problems.append(problem)

    entry = f"{entry_base} (id {row_id})" if row_id is not None else entry_base

    if row_id is not None and IDENTIFIER.fullmatch(row_id) is None:
        problems.append(
            PlanProblem(entry=entry, field="id", message=_IDENTIFIER_MESSAGE)
        )

    problems.extend(_unknown_keys(table, allowed=_WORKOUT_ROW_KEYS, entry=entry))

    day: _date | None = None
    if "date" not in table:
        problems.append(PlanProblem(entry=entry, field="date", message="is required"))
    else:
        day, problem = _as_date(table["date"], entry=entry, field="date")
        if problem is not None:
            problems.append(problem)

    sport_value: Sport | None = None
    if "sport" not in table:
        problems.append(PlanProblem(entry=entry, field="sport", message="is required"))
    else:
        sport_raw, problem = _single_line(table["sport"], entry=entry, field="sport")
        if problem is not None:
            problems.append(problem)
        elif sport_raw is not None:
            try:
                sport_value = Sport(sport_raw)
            except ValueError:
                allowed = ", ".join(sport.value for sport in Sport)
                problems.append(
                    PlanProblem(
                        entry=entry, field="sport", message=f"must be one of {allowed}"
                    )
                )

    modality_value: Modality | None = None
    if "modality" in table:
        modality_raw, problem = _single_line(
            table["modality"], entry=entry, field="modality"
        )
        if problem is not None:
            problems.append(problem)
        elif modality_raw is not None:
            try:
                modality_value = Modality(modality_raw)
            except ValueError:
                allowed = ", ".join(modality.value for modality in Modality)
                problems.append(
                    PlanProblem(
                        entry=entry,
                        field="modality",
                        message=f"must be one of {allowed}",
                    )
                )
            if (
                enforce_modality_sport_rule
                and modality_value is not None
                and sport_value is not None
                and sport_value is not Sport.WORKOUT
            ):
                problems.append(
                    PlanProblem(
                        entry=entry,
                        field="modality",
                        message="is only allowed when sport is Workout",
                    )
                )

    indoor_value: bool | None = None
    if "indoor" in table:
        indoor_value, problem = _as_bool(table["indoor"], entry=entry, field="indoor")
        if problem is not None:
            problems.append(problem)
            indoor_value = None

    title: str | None = None
    if "title" not in table:
        problems.append(PlanProblem(entry=entry, field="title", message="is required"))
    else:
        title, problem = _single_line(table["title"], entry=entry, field="title")
        if problem is not None:
            problems.append(problem)

    summary: str | None = None
    if "summary" not in table:
        problems.append(
            PlanProblem(entry=entry, field="summary", message="is required")
        )
    else:
        summary, problem = _single_line(table["summary"], entry=entry, field="summary")
        if problem is not None:
            problems.append(problem)

    prescription: str | None = None
    if "prescription" not in table:
        problems.append(
            PlanProblem(entry=entry, field="prescription", message="is required")
        )
    else:
        prescription, problem = _multi_line(
            table["prescription"], entry=entry, field="prescription"
        )
        if problem is not None:
            problems.append(problem)

    row = PlannedWorkout(
        id=row_id if row_id is not None else "",
        date=day if day is not None else fallback_date,
        sport=sport_value if sport_value is not None else Sport.RUN,
        modality=modality_value,
        indoor=indoor_value,
        title=title if title is not None else "",
        summary=summary if summary is not None else "",
        prescription=prescription if prescription is not None else "",
    )
    return row, problems


# ---------------------------------------------------------------------------
# parse_block
# ---------------------------------------------------------------------------


def parse_block(text: str, *, block_id: str) -> Block:
    """Parse `text` as a plan source and validate it fully (Req 1.1, 1.3-1.7,
    2.1-2.3, 2.5-2.7, 2.10, 2.12, 3.4, 3.8). Raises :class:`PlanValidationError`
    carrying every independently determinable problem, in document order
    (shape problems first, then rows, targets, amendments, overrides);
    otherwise returns the assembled :class:`~fitdocs.plans.model.Block`."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PlanValidationError(
            (PlanProblem(entry="file", field=None, message=str(exc)),)
        ) from exc

    problems: list[PlanProblem] = []

    if IDENTIFIER.fullmatch(block_id) is None:
        problems.append(
            PlanProblem(entry="block", field="id", message=_IDENTIFIER_MESSAGE)
        )
    if is_reserved_block_id(block_id):
        problems.append(
            PlanProblem(
                entry="block",
                field="id",
                message=f"{block_id!r} collides with the declaration's filename",
            )
        )

    title: str | None = None
    if "title" not in document:
        problems.append(
            PlanProblem(entry="block", field="title", message="is required")
        )
    else:
        title, problem = _single_line(document["title"], entry="block", field="title")
        if problem is not None:
            problems.append(problem)

    starts: _date | None = None
    if "starts" not in document:
        problems.append(
            PlanProblem(entry="block", field="starts", message="is required")
        )
    else:
        starts, problem = _as_date(document["starts"], entry="block", field="starts")
        if problem is not None:
            problems.append(problem)

    ends: _date | None = None
    if "ends" not in document:
        problems.append(PlanProblem(entry="block", field="ends", message="is required"))
    else:
        ends, problem = _as_date(document["ends"], entry="block", field="ends")
        if problem is not None:
            problems.append(problem)

    goal: str | None = None
    if "goal" not in document:
        problems.append(PlanProblem(entry="block", field="goal", message="is required"))
    else:
        goal, problem = _multi_line(document["goal"], entry="block", field="goal")
        if problem is not None:
            problems.append(problem)

    mesocycle_days: int | None = None
    if "mesocycle_days" not in document:
        problems.append(
            PlanProblem(entry="block", field="mesocycle_days", message="is required")
        )
    else:
        mesocycle_days, problem = _as_int(
            document["mesocycle_days"], entry="block", field="mesocycle_days", minimum=1
        )
        if problem is not None:
            problems.append(problem)

    structural_fault = starts is None or ends is None or mesocycle_days is None
    if starts is not None and ends is not None and ends < starts:
        problems.append(
            PlanProblem(
                entry="block",
                field="ends",
                message=f"{ends} is before starts {starts}",
            )
        )
        structural_fault = True

    if structural_fault:
        raise PlanValidationError(tuple(problems))

    assert starts is not None and ends is not None and mesocycle_days is not None
    windows = mesocycle_windows(starts, ends, mesocycle_days)
    count = len(windows)

    problems.extend(
        PlanProblem(entry="block", field=key, message="is not a recognised key")
        for key in sorted(document)
        if key not in _TOP_LEVEL_KEYS
    )

    # -- mesocycle targets ---------------------------------------------
    mesocycle_entries, problem = _as_array_of_tables(
        document, "mesocycle", entry="block"
    )
    if problem is not None:
        problems.append(problem)
    targets: list[MesocycleTarget] = []
    for index, entry_table in enumerate(mesocycle_entries):
        entry_name = f"mesocycle[{index}]"
        problems.extend(
            _unknown_keys(entry_table, allowed=_MESOCYCLE_KEYS, entry=entry_name)
        )
        number: int | None = None
        if "number" not in entry_table:
            problems.append(
                PlanProblem(entry=entry_name, field="number", message="is required")
            )
        else:
            number, problem = _as_int(
                entry_table["number"], entry=entry_name, field="number"
            )
            if problem is not None:
                problems.append(problem)
        # `target_load`/`focus` are typed regardless of `number`'s validity
        # (mirrors `_parse_target_op`): every independently determinable
        # problem in this entry is collected before deciding, below,
        # whether `number` was usable enough to build a `MesocycleTarget`.
        target_load: float | None = None
        if "target_load" in entry_table:
            target_load, problem = _as_target_load(
                entry_table["target_load"], entry=entry_name, field="target_load"
            )
            if problem is not None:
                problems.append(problem)
        focus: str | None = None
        if "focus" in entry_table:
            focus, problem = _single_line(
                entry_table["focus"], entry=entry_name, field="focus"
            )
            if problem is not None:
                problems.append(problem)
        if number is None:
            continue
        targets.append(
            MesocycleTarget(number=number, target_load=target_load, focus=focus)
        )

    # -- workout rows -----------------------------------------------------
    workout_entries, problem = _as_array_of_tables(
        document, _WORKOUT_KEY, entry="block"
    )
    if problem is not None:
        problems.append(problem)
    rows: list[PlannedWorkout] = []
    for position, table in enumerate(workout_entries, start=1):
        row, row_problems = _parse_workout_row(
            table,
            entry_base=f"{_WORKOUT_KEY}[{position}]",
            enforce_modality_sport_rule=True,
            fallback_date=starts,
        )
        problems.extend(row_problems)
        rows.append(row)

    # Duplicate ids among original rows, named at both entries (Req 2.6).
    seen_at: dict[str, int] = {}
    for position, table in enumerate(workout_entries, start=1):
        raw_id = table.get("id")
        if not isinstance(raw_id, str):
            continue
        if raw_id in seen_at:
            first = seen_at[raw_id]
            problems.append(
                PlanProblem(
                    entry=f"{_WORKOUT_KEY}[{position}] (id {raw_id})",
                    field="id",
                    message=f"also used at {_WORKOUT_KEY}[{first}] (id {raw_id})",
                )
            )
        else:
            seen_at[raw_id] = position

    # -- amendments ---------------------------------------------------------
    amendment_entries, problem = _as_array_of_tables(
        document, "amendment", entry="block"
    )
    if problem is not None:
        problems.append(problem)
    specs: list[AmendmentSpec] = []
    any_amendment_shape_problem = False
    # Seeded at the minimum representable date, never `starts`: an
    # amendment dated before the block's own `starts` is entirely valid
    # (Req 3.5 only requires non-decreasing amendment dates, not dates
    # within the block's bounds), so seeding at `starts` could itself
    # manufacture a spurious "before the previous amendment's date"
    # finding against a real, earlier amendment.
    running_date = _date.min
    for a_index, a_table in enumerate(amendment_entries, start=1):
        entry_base = f"amendment[{a_index}]"
        a_problems: list[PlanProblem] = []
        a_problems.extend(
            _unknown_keys(a_table, allowed=_AMENDMENT_KEYS, entry=entry_base)
        )

        a_date: _date | None = None
        if "date" not in a_table:
            a_problems.append(
                PlanProblem(entry=entry_base, field="date", message="is required")
            )
        else:
            a_date, problem = _as_date(a_table["date"], entry=entry_base, field="date")
            if problem is not None:
                a_problems.append(problem)

        reason: str | None = None
        if "reason" not in a_table:
            a_problems.append(
                PlanProblem(entry=entry_base, field="reason", message="is required")
            )
        else:
            reason, problem = _single_line(
                a_table["reason"], entry=entry_base, field="reason"
            )
            if problem is not None:
                a_problems.append(problem)

        ops: list[AmendmentOp] = []
        shared_index = 0

        update_entries, problem = _as_array_of_tables(
            a_table, "update", entry=entry_base
        )
        if problem is not None:
            a_problems.append(problem)
        for u_table in update_entries:
            op_entry_base = f"{entry_base}.update[{shared_index}]"
            op_problems, op = _parse_update_op(u_table, entry_base=op_entry_base)
            a_problems.extend(op_problems)
            if not op_problems:
                assert op is not None
                ops.append(op)
            shared_index += 1

        add_entries, problem = _as_array_of_tables(a_table, "add", entry=entry_base)
        if problem is not None:
            a_problems.append(problem)
        for add_table in add_entries:
            op_entry_base = f"{entry_base}.add[{shared_index}]"
            row, row_problems = _parse_workout_row(
                add_table,
                entry_base=op_entry_base,
                enforce_modality_sport_rule=False,
                fallback_date=starts,
            )
            a_problems.extend(row_problems)
            if not row_problems:
                ops.append(AddOp(row=row))
            shared_index += 1

        remove_entries, problem = _as_array_of_tables(
            a_table, "remove", entry=entry_base
        )
        if problem is not None:
            a_problems.append(problem)
        for remove_table in remove_entries:
            op_entry_base = f"{entry_base}.remove[{shared_index}]"
            op_problems, r_op = _parse_remove_op(remove_table, entry_base=op_entry_base)
            a_problems.extend(op_problems)
            if not op_problems:
                assert r_op is not None
                ops.append(r_op)
            shared_index += 1

        target_entries, problem = _as_array_of_tables(
            a_table, "mesocycle", entry=entry_base
        )
        if problem is not None:
            a_problems.append(problem)
        for t_table in target_entries:
            op_entry_base = f"{entry_base}.target[{shared_index}]"
            op_problems, t_op = _parse_target_op(t_table, entry_base=op_entry_base)
            a_problems.extend(op_problems)
            if not op_problems:
                assert t_op is not None
                ops.append(t_op)
            shared_index += 1

        problems.extend(a_problems)
        if a_problems or a_date is None:
            # Position-preserving placeholder (module docstring): an empty
            # `ops` amendment keeps every later, shape-valid amendment's
            # ordinal aligned with its true file position. Its date is the
            # amendment's own parsed `date` when that field itself parsed
            # (so a genuinely earlier amendment with some other fault --
            # e.g. a missing `reason` -- still advances the running date
            # correctly and cannot manufacture a spurious out-of-order
            # finding against a real, later amendment); only when `date`
            # itself failed to parse does the placeholder fall back to the
            # running "last known good" date. `apply_amendments` has no
            # way to know this placeholder stands in for a real fault, so
            # `any_amendment_shape_problem` carries that signal onward to
            # the override gate below instead.
            any_amendment_shape_problem = True
            placeholder_date = a_date if a_date is not None else running_date
            specs.append(AmendmentSpec(date=placeholder_date, reason="", ops=()))
            running_date = placeholder_date
        else:
            assert a_date is not None
            specs.append(
                AmendmentSpec(date=a_date, reason=reason or "", ops=tuple(ops))
            )
            running_date = a_date

    # -- overrides ------------------------------------------------------
    override_entries, problem = _as_array_of_tables(document, "override", entry="block")
    if problem is not None:
        problems.append(problem)
    all_overrides: list[Override] = []
    faulty_override_indices: set[int] = set()
    for o_index, o_table in enumerate(override_entries):
        entry_base = f"override[{o_index}]"
        o_problems, override = _parse_override(
            o_table, entry_base=entry_base, block_ends=ends
        )
        problems.extend(o_problems)
        assert override is not None
        all_overrides.append(override)
        if any(p.field in ("date", "id") for p in o_problems):
            faulty_override_indices.add(o_index)

    # -- delegate to PlanModel ------------------------------------------
    problems.extend(check_rows(rows, starts=starts, ends=ends, entry=_WORKOUT_KEY))
    problems.extend(check_targets(targets, count=count))

    states, amendments, amendment_problems = apply_amendments(
        PlanState(rows=tuple(rows), targets=tuple(targets)),
        specs,
        starts=starts,
        ends=ends,
        count=count,
    )
    problems.extend(amendment_problems)

    any_amendment_invalid = bool(amendment_problems) or any_amendment_shape_problem
    if any_amendment_invalid and override_entries:
        problems.append(
            PlanProblem(
                entry=f"override[0..{len(override_entries) - 1}]",
                field=None,
                message="not checked because an amendment was invalid",
            )
        )
    elif not any_amendment_invalid:
        # Every override, in full file order, so a genuine finding about a
        # shape-valid override keeps its true `override[i]` label; any
        # problem this returns about a shape-faulty entry's placeholder
        # values is discarded below (module docstring).
        problems.extend(
            p
            for p in check_overrides(states, amendments, tuple(all_overrides))
            if not any(
                p.entry.startswith(f"override[{i}] ") for i in faulty_override_indices
            )
        )

    if problems:
        raise PlanValidationError(tuple(problems))

    return build_block(
        id=block_id,
        title=title or "",
        starts=starts,
        ends=ends,
        goal=goal or "",
        mesocycle_days=mesocycle_days,
        original=PlanState(rows=tuple(rows), targets=tuple(targets)),
        current=states[-1],
        amendments=amendments,
        overrides=tuple(all_overrides),
    )


def _parse_update_op(
    table: Mapping[str, object], *, entry_base: str
) -> tuple[list[PlanProblem], UpdateOp | None]:
    problems: list[PlanProblem] = []

    row_id: str | None = None
    if "id" not in table:
        problems.append(
            PlanProblem(entry=entry_base, field="id", message="is required")
        )
    else:
        row_id, problem = _single_line(table["id"], entry=entry_base, field="id")
        if problem is not None:
            problems.append(problem)

    entry = f"{entry_base} (id {row_id})" if row_id is not None else entry_base
    problems.extend(_unknown_keys(table, allowed=_UPDATE_KEYS, entry=entry))

    fields: dict[str, object] = {}
    for key in MUTABLE_FIELDS:
        if key not in table:
            continue
        value = table[key]
        parsed: object | None
        field_problem: PlanProblem | None
        if key == "date":
            parsed, field_problem = _as_date(value, entry=entry, field=key)
        elif key == "sport":
            raw, field_problem = _single_line(value, entry=entry, field=key)
            parsed = None
            if field_problem is None and raw is not None:
                try:
                    parsed = Sport(raw)
                except ValueError:
                    allowed = ", ".join(sport.value for sport in Sport)
                    field_problem = PlanProblem(
                        entry=entry, field=key, message=f"must be one of {allowed}"
                    )
        elif key == "modality":
            raw, field_problem = _single_line(value, entry=entry, field=key)
            parsed = None
            if field_problem is None and raw is not None:
                try:
                    parsed = Modality(raw)
                except ValueError:
                    allowed = ", ".join(modality.value for modality in Modality)
                    field_problem = PlanProblem(
                        entry=entry, field=key, message=f"must be one of {allowed}"
                    )
        elif key == "indoor":
            parsed, field_problem = _as_bool(value, entry=entry, field=key)
        elif key in ("title", "summary"):
            parsed, field_problem = _single_line(value, entry=entry, field=key)
        else:  # "prescription"
            parsed, field_problem = _multi_line(value, entry=entry, field=key)

        if field_problem is not None:
            problems.append(field_problem)
        else:
            fields[key] = parsed

    if problems:
        return problems, None
    assert row_id is not None
    return problems, UpdateOp(row_id=row_id, fields=fields)


def _parse_remove_op(
    table: Mapping[str, object], *, entry_base: str
) -> tuple[list[PlanProblem], RemoveOp | None]:
    problems: list[PlanProblem] = []
    problems.extend(_unknown_keys(table, allowed=_REMOVE_KEYS, entry=entry_base))
    row_id: str | None = None
    if "id" not in table:
        problems.append(
            PlanProblem(entry=entry_base, field="id", message="is required")
        )
    else:
        row_id, problem = _single_line(table["id"], entry=entry_base, field="id")
        if problem is not None:
            problems.append(problem)
    if problems:
        return problems, None
    assert row_id is not None
    return problems, RemoveOp(row_id=row_id)


def _parse_target_op(
    table: Mapping[str, object], *, entry_base: str
) -> tuple[list[PlanProblem], TargetOp | None]:
    problems: list[PlanProblem] = []
    problems.extend(_unknown_keys(table, allowed=_TARGET_OP_KEYS, entry=entry_base))

    number: int | None = None
    if "number" not in table:
        problems.append(
            PlanProblem(entry=entry_base, field="number", message="is required")
        )
    else:
        number, problem = _as_int(table["number"], entry=entry_base, field="number")
        if problem is not None:
            problems.append(problem)

    target_load: float | None = None
    if "target_load" in table:
        target_load, problem = _as_target_load(
            table["target_load"], entry=entry_base, field="target_load"
        )
        if problem is not None:
            problems.append(problem)

    focus: str | None = None
    if "focus" in table:
        focus, problem = _single_line(table["focus"], entry=entry_base, field="focus")
        if problem is not None:
            problems.append(problem)

    if problems:
        return problems, None
    assert number is not None
    return problems, TargetOp(number=number, target_load=target_load, focus=focus)


def _parse_override(
    table: Mapping[str, object], *, entry_base: str, block_ends: _date
) -> tuple[list[PlanProblem], Override | None]:
    problems: list[PlanProblem] = []

    # `id` is parsed before `date` (unlike the table's declared key order)
    # so every later problem in this entry -- `date` included -- can carry
    # the `(id ...)` suffix once it is known, matching every other entry
    # kind's naming convention.
    row_id: str | None = None
    if "id" not in table:
        problems.append(
            PlanProblem(entry=entry_base, field="id", message="is required")
        )
    else:
        row_id, problem = _single_line(table["id"], entry=entry_base, field="id")
        if problem is not None:
            problems.append(problem)

    entry = f"{entry_base} (id {row_id})" if row_id is not None else entry_base
    problems.extend(_unknown_keys(table, allowed=_OVERRIDE_KEYS, entry=entry))

    o_date: _date | None = None
    if "date" not in table:
        problems.append(PlanProblem(entry=entry, field="date", message="is required"))
    else:
        o_date, problem = _as_date(table["date"], entry=entry, field="date")
        if problem is not None:
            problems.append(problem)

    stems: tuple[str, ...] = ()
    has_stems = "stems" in table
    if has_stems:
        raw_stems = table["stems"]
        if not isinstance(raw_stems, list) or not raw_stems:
            problems.append(
                PlanProblem(
                    entry=entry, field="stems", message="must be a non-empty array"
                )
            )
            # `has_stems` stays true: the key *was* present, so the
            # stems-or-skipped exclusivity check below must not also
            # complain "one of stems or skipped is required" for a source
            # that plainly tried to state stems and got the array wrong.
        else:
            parsed_stems: list[str] = []
            seen: set[str] = set()
            ok = True
            for item in raw_stems:
                value, problem = _single_line(item, entry=entry, field="stems")
                if problem is not None:
                    problems.append(problem)
                    ok = False
                    continue
                assert value is not None
                if value in seen:
                    problems.append(
                        PlanProblem(
                            entry=entry,
                            field="stems",
                            message=f"{value} is listed more than once",
                        )
                    )
                    ok = False
                    continue
                seen.add(value)
                parsed_stems.append(value)
            if ok:
                stems = tuple(parsed_stems)

    skipped = False
    has_skipped = "skipped" in table
    if has_skipped:
        skipped_value, problem = _as_bool(
            table["skipped"], entry=entry, field="skipped"
        )
        if problem is not None:
            problems.append(problem)
        elif skipped_value is not True:
            problems.append(
                PlanProblem(
                    entry=entry, field="skipped", message="must be true when present"
                )
            )
        else:
            skipped = True

    if has_stems and has_skipped:
        problems.append(
            PlanProblem(
                entry=entry,
                field="stems",
                message="stems and skipped are mutually exclusive",
            )
        )
    elif not has_stems and not has_skipped:
        problems.append(
            PlanProblem(
                entry=entry,
                field="stems",
                message="one of stems or skipped is required",
            )
        )

    reason: str | None = None
    if "reason" in table:
        reason, problem = _single_line(table["reason"], entry=entry, field="reason")
        if problem is not None:
            problems.append(problem)

    override = Override(
        date=o_date if o_date is not None else block_ends,
        row_id=row_id if row_id is not None else "",
        stems=stems,
        skipped=skipped,
        reason=reason,
    )
    return problems, override


def load_block(path: Path, *, block_id: str) -> Block:
    """Read `path`'s bytes, decode UTF-8, and delegate to :func:`parse_block`
    (Req 1.1). This is the package's only file read. An unreadable file or
    one that is not valid UTF-8 is one problem naming `entry="file"`; a
    `tomllib.TOMLDecodeError` raised inside `parse_block` is one problem
    carrying the decoder's message."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlanValidationError(
            (
                PlanProblem(
                    entry="file", field=None, message=f"could not be read: {exc}"
                ),
            )
        ) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlanValidationError(
            (
                PlanProblem(
                    entry="file", field=None, message=f"is not valid UTF-8: {exc}"
                ),
            )
        ) from exc
    return parse_block(text, block_id=block_id)
