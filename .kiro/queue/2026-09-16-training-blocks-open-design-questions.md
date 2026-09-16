---
id: 2026-09-16-training-blocks-open-design-questions
title: Four design questions training-blocks reviewers raised that the design does not decide
status: open
importance: medium
importance_why: Each is a rendering or validation choice a downstream spec will otherwise inherit by accident; two touch frozen goldens, so deciding late costs a golden regeneration.
effort: S
kind: spec-work
area: training-blocks, plan-resolution, .kiro/specs/training-blocks/design.md
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks (reviewers of 3.2, 3.3, 4.1, 1.2)
pinned_at: 68fe42e
resume_command: "/kiro-spec-design training-blocks [queue: .kiro/queue/2026-09-16-training-blocks-open-design-questions.md] Decide the four open questions and record each as a design sentence"
context:
  - .kiro/specs/training-blocks/design.md
  - .kiro/specs/plan-resolution/design.md
  - src/fitdocs/plans/block_page.py
  - src/fitdocs/plans/planned_page.py
  - src/fitdocs/plans/settings.py
blocked_by: []
---

## What
Decisions the implementation made by default because design.md is silent:

1. **Revision-record sport column.** The "As first written" table and the
   `Added`/`Removed` bullets show the bare sport (`Workout`) while the day
   table shows `page.sport_phrase` (`Workout (strength, indoor)`), so a
   strength row's modality/indoor never appears in the revision record.
   design.md BlockPage item 9's examples use `Run` only. Changing it moves
   the frozen golden `tests/plans/golden/block.md`.
2. **Empty resolution section.** `RowResolution(section=())` is admitted by
   the seam type; `render_planned_page` then emits `## Resolution\n\n\n` (an
   extra trailing blank line). Decide whether an empty section is legal for
   `plan-resolution`: the renderer omits the blank, or `check_resolution`
   rejects it.
3. **Plan-source directory above the data root.** `resolve_plans_dir` accepts
   a path normalising to the data root's parent or above (`".."` -> `/`);
   design PlanSettings and Req 1.9 forbid only the root itself and owned
   prefixes. Decide whether a parent-of-root source is refused, noted, or
   fine.
4. **Req 8.10 wording.** Because `blocks/` joined `DECLARED_DIRS`, `sync`,
   `regen`, `drain` and `history` now create `blocks/AGENTS.md` on any data
   root even with no plan sources; "the declaration for the rendered location
   is therefore placed by the first run that has a page to write there" is
   true only of the `plan` run in isolation (design.md:374-380 acknowledges
   the same for `history/`). One clarifying sentence.
   Nit alongside: `### Goal` (H3) sits directly under the H1 before the H2
   mesocycle sections -- a heading-level skip some linters flag.

## Why it matters
1 and 2 are shapes plan-resolution renders into; deciding them after that
spec lands means two goldens and a seam change instead of one sentence now.
3 is a data-safety boundary the ownership contract should state either way.

## Evidence
- `src/fitdocs/plans/block_page.py:192` (day table via `sport_phrase`) vs the
  As-first-written table and the Added/Removed bullets in the same module
  (bare `row.sport.value`); `tests/plans/golden/block.md` lines 78-97.
- `render_planned_page(b, row, Resolution(rows={id: RowResolution(cell="x", section=())}, mesocycles={}))`
  ends `'## Resolution\n\n\n'` (reported by the 3.3 reviewer with that probe;
  reproduce with the full fixture).
- `src/fitdocs/plans/settings.py::resolve_plans_dir` -- component-wise owned
  check and equals-root check only; `PlanSettings(path="..")` resolves to `/`
  (4.1 reviewer probe).
- `src/fitdocs/declaration.py::ensure_declarations` iterates every
  `DECLARED_DIRS` entry; `src/fitdocs/sync.py:533,738,988` call it
  unconditionally.

## How to pick it up
1. Read design.md "#### BlockPage" item 9, "#### PlannedPage", "#### PlanSettings",
   and requirements.md 8.10.
2. Decide each; where a golden moves, regenerate it in the same change and
   re-run `uv run pytest tests/plans -q`.
3. Done when each decision is one sentence in design.md and, where behaviour
   changed, one test pins it.

## Open questions
All four are the item.
