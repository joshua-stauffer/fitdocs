---
id: 2026-09-16-training-blocks-design-records-shipped-semantics
title: Amend training-blocks design.md so it states the grammar and rendering semantics that shipped
status: open
importance: high
importance_why: build-training-block teaches this grammar from design.md and plan-resolution consumes its seams; six shipped behaviours are recorded only in tasks.md Implementation Notes, so a downstream spec reading the design will teach or assume the wrong thing.
effort: S
kind: inconsistency
area: training-blocks, .kiro/specs/training-blocks/design.md, .kiro/specs/training-blocks/requirements.md
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks (reviewers of 2.2, 2.3, 3.1, 4.3; feature validation)
pinned_at: 68fe42e
resume_command: "/kiro-spec-design training-blocks [queue: .kiro/queue/2026-09-16-training-blocks-design-records-shipped-semantics.md] Record the six shipped semantics as a design amendment, no code change"
context:
  - .kiro/specs/training-blocks/design.md
  - .kiro/specs/training-blocks/requirements.md
  - .kiro/specs/training-blocks/tasks.md
  - src/fitdocs/plans/model.py
  - src/fitdocs/plans/source.py
  - src/fitdocs/cli.py
blocked_by: []
---

## What
Six behaviours shipped in training-blocks (main 68fe42e) that design.md does
not state, or states differently. Each was a reviewer finding, decided by the
controller, implemented, pinned by tests, and recorded only in tasks.md
`## Implementation Notes`:

1. **`AddOp` rows are held to the original-row rules** (date in bounds;
   modality only with `Workout`) through the same helper `_apply_update`
   uses. design.md:831 names only the id-history rule for `AddOp`; without the
   stricter rule `build_block`'s own postcondition (`sum(len(m.workouts)) ==
   len(current.rows)`) was violated by an out-of-bounds add.
2. **"changes no field" is a value rule**: an `UpdateOp` whose every stated
   value equals the current value is a problem. design.md:828 says only
   "`fields` must be non-empty".
3. **Op labels use a flattened per-amendment index** shared across kinds
   (`amendment[1].add[1]` when an update precedes the add), matching
   `apply_amendments`' `op_index`; design.md:946/1050 examples read as
   per-kind (`update[0]`, `add[0]`). Also: within one amendment ops apply in
   fixed kind order (update, add, remove, mesocycle) because TOML groups
   arrays-of-tables by key -- an add-then-update of one id in one amendment
   reports "no row with id ... exists".
4. **Multi-line fields (`goal`, `prescription`) have trailing newlines
   stripped** after CRLF normalisation (a TOML `"""` value carries one);
   leading whitespace preserved. The grammar table does not say so.
5. **The control-character rule is `not ch.isprintable()`** except `\n`/`\t`
   (rejects NBSP, zero-width and other Unicode separators), mirroring
   `page.yaml_string`'s class so nothing that validates can fail at render
   time. design.md:1039 says "control character".
6. **`_report_plan` prints `  kept (not fitdocs'): <path>`** under `rendered`
   and `unchanged` for every `BlockOutcome.foreign` entry (Req 7.9's
   "reported" otherwise never reached stdout). design.md "#### PlanCommand"'s
   line list omits it.

Plus one prose reconciliation: tasks.md:440 says "never a second spelling of
that name" for the reserved block id while design.md:817 says "never a second
`"agents"` literal" -- they disagree on whether docstring prose counts (the
shipped `model.py` satisfies both).

## Why it matters
`build-training-block` (spec written, not implemented) teaches the source
grammar "exactly as this spec defines it" -- from design.md. Items 3-5 are
grammar facts an athlete or LLM writing a source will hit. `plan-resolution`
re-anchors `plan_command` and reads the PlanCommand line list; item 6 is a
line it must preserve. Item 1-2 are validation semantics the skill's examples
must not contradict.

## Evidence
- `src/fitdocs/plans/model.py` -- `_row_bounds_problem` called from both
  `_apply_update` and `_apply_add`; `_apply_update` docstring states the
  value rule. `tests/plans/test_model.py::TestAddOp::test_add_dated_outside_bounds_is_a_problem`,
  `::test_field_set_to_its_current_value_changes_no_field`.
- `src/fitdocs/plans/source.py` module docstring ("Position-preserving
  placeholders"; the control-character and multi-line paragraphs);
  `tests/plans/test_source.py::TestMultiLineTrailingNewline`,
  `::TestControlCharacter::test_no_break_space_rejected_in_goal`.
- `src/fitdocs/cli.py:1263` -- the kept-foreign line;
  `tests/test_cli_plan.py::test_kept_foreign_page_is_reported_on_a_rendered_block`.
- `.kiro/specs/training-blocks/tasks.md` `## Implementation Notes` (2.2, 2.3,
  4.3 entries) -- the controller's recorded decisions.

## How to pick it up
1. Read the three Implementation Notes entries, then design.md "#### PlanModel"
   (Amendments bullet), "#### SourceParser" (Plan-Source Grammar table and the
   shape-validation bullet), "#### PlanCommand" (the `_report_plan` list).
2. Write an amendment block in design.md (the shape load-history used) and
   edit the six passages in place; add a Req 2.1/2.3 clarification if the
   `isprintable` rule needs one in requirements.md; fix tasks.md:440.
3. Done when `/kiro-spec-status training-blocks` is clean and every sentence
   you changed matches a test in the Evidence list. No code changes.
