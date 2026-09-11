---
id: 2026-09-12-history-coverage-rows-and-methodology-prose
title: History page's coverage table and body prose leave two facts implicit -- out-of-span pages, and which methodology produced the series
status: open
importance: medium
importance_why: The page is the athlete's only explanation of what was and was not counted; "all" row totals differ from pages_read whenever a page lies outside the span, and the methodology id appears only in frontmatter.
effort: S
kind: gap
area: load-history, src/fitdocs/history/series.py, src/fitdocs/history/page.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 3.4 and 4.2 (reviewer FOLLOW_UPS)
pinned_at: 8cd0062
resume_command: "do: decide whether coverage_report's 'all' row counts pages outside the series span (and word the page's coverage intro accordingly), and whether the body prose names the methodology; pin both in tests/history/test_page.py and amend design.md"
context:
  - src/fitdocs/history/series.py
  - src/fitdocs/history/page.py
  - tests/history/test_series.py
  - tests/history/test_page.py
  - .kiro/specs/load-history/requirements.md
blocked_by: []
---

## What
1. `coverage_report` rows are built from the included partition inside the
   span; the page's intro says "of N documents read". A page dated outside
   the span (no load, e.g. a race) is read but in no row, so the sums do not
   add up to N and nothing says why.
2. `render_history` writes `methodology:` in frontmatter only. The body's
   constants section quotes tau/k values but never the calculator id, so a
   reader of the rendered page (or a wiki front-end that hides frontmatter)
   cannot tell which methodology produced the curve.

## Evidence
3.4 round-2 and 4.2 round-1 `FOLLOW_UPS`; `tests/history/golden/history.md`
body has no occurrence of the methodology id.

## How to pick it up
Small: one sentence in the coverage intro and one in the constants section,
plus the two assertions. Amend design.md's Page Vocabulary.
