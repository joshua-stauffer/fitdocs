---
id: 2026-09-12-load-history-spec-docs-reconcile-with-shipped-code
title: load-history design/tasks/research carry seventeen statements the implementation deliberately deviated from or that were wrong as written
status: open
importance: medium
importance_why: The design is the document the next spec (performance-model-fit) reads; each stale sentence is a wrong assumption waiting to be built on, and the tasks.md Implementation Notes -- not the design -- currently hold the truth.
effort: M
kind: docs
area: load-history, .kiro/specs/load-history/design.md, .kiro/specs/load-history/tasks.md, .kiro/specs/load-history/research.md
created: 2026-09-12
surfaced_by: /kiro-impl load-history (reviewer follow-ups across tasks 2.1, 3.1, 3.2, 3.4, 3.5, 4.1, 4.2, 5.2, 5.4)
pinned_at: 8cd0062
resume_command: "do: amend .kiro/specs/load-history/{design,tasks,research}.md so every statement below matches what shipped, recording each as a dated amendment in spec.json"
context:
  - .kiro/specs/load-history/design.md
  - .kiro/specs/load-history/tasks.md
  - .kiro/specs/load-history/research.md
  - .kiro/specs/load-history/spec.json
blocked_by: []
---

## What
Each of the following is a design/tasks/research sentence that the code (by
a controller decision recorded in tasks.md's `## Implementation Notes`) or a
reviewer's measurement contradicts:

1. design.md ~343–361 and the sequence diagram: `select_methodology` runs
   before the empty-archive check. Shipped: the engine gates "no page records
   a load" FIRST (Req 1.10 otherwise turns into exit 2). tasks.md 5.2 bullets
   list them in the old order.
2. design.md ~1092 blanket precondition "`pages` is the scan's included
   partition, sorted": false for `select_methodology` and wrong for
   `criterion_points`, which takes the full scan (Req 6.3).
3. tasks.md 2.1/2.3 "at both the fitness and the fatigue seed" vs design.md
   ~730 / research.md ~136 "1.20%/1.12%" = tau 42 vs 45; shipped: all three
   (45/42/15) stated and pinned.
4. design.md:349 `coverage_by_year` vs contract `coverage_report`.
5. design.md:421 `MethodologyChoice.inferred` vs contract field `source`.
6. design.md:429 `CalendarMarker.detail is None` -- no such field; the
   observable lives in HistoryPage.
7. design.md:1494 `calendar.py` "covered by the render layer's existing
   guards" -- no render guard scans its imports; 5.4's boundary test does.
8. design.md ~88–110 Allowed Dependencies omit `fitdocs.render.format`,
   `fitdocs.declaration`, `contract.parse_frontmatter`/`DOC_VERSION`/
   `WORKOUT_TYPE`, all measured in the package's import closure.
9. design.md ~907 / task 3.1 "documents.py is the package's only importer of
   the contract": page.py imports it too (registered in 5.4).
10. design.md `WeekRow.sessions` undefined; shipped as `pages_with_load`.
11. design.md ~1588–1591 Error Handling vs the DocumentScan component
    (see the sibling HIGH item on unreadable documents).
12. research.md:266 "landed by this spec's task 4.3" -- it is 5.5.
13. tasks.md 3.1 / design.md:952 named mutation "sort by path only (two
    same-day pages swap)" is unreachable: the sorted glob already orders
    same-day pages by path.
14. `CriterionPoints.by_kind` omits zero-count kinds (design silent; page
    derives 0); race markers come from the full scan, span-clipped (design
    silent; recorded in tasks.md Implementation Notes and an engine.py
    comment).
15. design.md traceability row 5.8 names `render_history_document`; the
    contract block and the code say `render_history`.
16. design.md "seam performance-model-fit plugs into" (`ModelConstants`,
    `ConstantProvenance`, `SEED_CONSTANTS`) is not on
    `fitdocs.history.__all__`; say whether the seam is the package surface
    or `history.sources`.
17. The weekly table's "Sessions" column is by construction equal to the
    "Pages w/ load" numerator (`WeekRow.sessions = pages_with_load`);
    either drop the column or give `sessions` its own meaning.

## Why it matters
`performance-model-fit` is gated on this page's exact form and will read
the design, not the Implementation Notes.

## Evidence
Each line cites its design/tasks/research location; the Implementation
Notes at the bottom of tasks.md record the decisions; the code is on
`impl/load-history` at 8cd0062.

## How to pick it up
Read tasks.md `## Implementation Notes` first, then walk the seventeen
sites. Amend in place with an "Amendment (2026-09-12)" marker per the
wiki-contract precedent; add one `amendments` entry to spec.json. Done
when `/kiro-spec-status load-history` reads clean and no listed sentence
contradicts the code.
