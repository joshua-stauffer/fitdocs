---
id: 2026-08-18-design-table-parser-blind-to-pipeless-rows
title: The design-table row parser's count anchor is blind to pipe-less and indented rows
status: open
importance: low
importance_why: The natural-format addition it was built to catch is caught and measured; only a row written unlike all thirteen siblings slips through.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_verify.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.4 review round 3)
pinned_at: c3d2201
resume_command: "do: change the design-table body-row filter in tests/purge/test_verify.py from line.startswith('|') to '|' in line.strip(), so a GFM-legal row without a leading pipe or indented by up to three spaces still counts"
context:
  - tests/purge/test_verify.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`test_row_names_matches_the_design_table_in_the_table_s_own_order` counts the
`#### ReplacementVerification` table's body rows and asserts the count against
`_DESIGN_TABLE_ROWS`, which is what makes the guard catch a row **added** to
`design.md` rather than only a row dropped or reordered.

The filter is `line.startswith("|")`. GitHub-flavoured Markdown also renders a
row that omits the leading pipe, and one indented by up to three spaces. Both
are real rows; neither is counted.

## Why it matters

Low, and the bound is worth recording so nobody re-derives it. The case the
anchor exists for — a row added in the table's own format — **is** caught, and
was measured twice. Slipping past it requires writing a fourteenth row in a
format none of the thirteen siblings uses.

Recording it because the anchor's whole purpose is to make an addition
impossible to miss, and a reader should know the exact shape of the remaining
hole rather than assuming there is none.

## Evidence

Reported by the task 7.4 reviewer, which measured both cases against the live
tree at `b7c5a3d`: a 14th row written as
`A brand new fourteenth check | F, W | ... | fine` (no leading pipe), and the
same row indented two spaces — each left `tests/purge/test_verify.py` at
**89 passed**.

The same reviewer confirmed the in-format cases are caught: a 14th row in the
table's own format reds at `test_verify.py:211` with
`AssertionError: the table has 14 body rows, not 13`; a dropped row and a
reordered pair red via the cursor at `:214`/`:217`; an emptied table body reds
at `:211` rather than passing on zero rows.

Not independently re-derived by the controller, which measured only the
in-format addition, the drop, and the anchor-removed control.

## How to pick it up

One-line change: filter on `"|" in line.strip()` instead of
`line.startswith("|")`. Verify by inserting a pipe-less 14th row and an
indented one, watching each red, then restoring `design.md` byte-identically.
Done when both formats are counted.
