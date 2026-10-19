---
id: 2026-10-13-dashboards-docs-claim-no-new-data-means-no-change
title: docs/dashboards.md says a day or a sync with no new data leaves the working tree clean, which is false for charts with a $today window; the packaged skill says it correctly
status: done
importance: low
importance_why: A user who git-commits dashboards and reads the guide expects a quiet working tree after a no-op sync; the shipped example chart itself (`$today - 84`) changes bytes as days pass.
effort: S
kind: docs
area: dashboards, docs/dashboards.md
created: 2026-10-13
surfaced_by: /kiro-validate-impl dashboards (coverage dimension)
pinned_at: 0a98d5c
resume_command: "do: correct docs/dashboards.md lines 155-158 and 636-638 to say a $today window moves each day (as the packaged skill does at SKILL.md:86-92), re-wrap the two over-long lines noted below, and run tests/dashboards/test_docs_dashboards.py [queue: .kiro/queue/2026-10-13-dashboards-docs-claim-no-new-data-means-no-change.md]"
context:
  - docs/dashboards.md
  - src/fitdocs/skills/fitdocs-dashboards/SKILL.md
  - tests/dashboards/test_docs_dashboards.py
blocked_by:
  - dashboards
---

## What
Two sentences in `docs/dashboards.md` state that a run with no new data changes
nothing on disk. A relative chart whose SQL uses `$today` in a window (the
guide's own example, `WHERE start_utc::DATE >= $today - 84`, lines 46-60) returns
different rows as the date moves, so its region and image change on a day with
no new workouts. The packaged skill already says so; the guide does not.

A second, cosmetic fault in the same file rides along: a few prose lines are
not wrapped like the rest of the page.

## Why it matters
The guide's "Version control" section tells the user what to commit and what to
expect. Following it, a user sees a dirty working tree after an idle sync and
cannot tell whether something is wrong.

## Evidence
At 0a98d5c:
- `docs/dashboards.md:155-158`: "It writes its region and image only when the bytes differ, and it never writes the run date or the time, so a day with no new data changes nothing on disk."
- `docs/dashboards.md:636-638`: "Relative charts change only when their rows, their directive or the chart kit change, so a sync that brings no new data leaves the working tree clean."
- `src/fitdocs/skills/fitdocs-dashboards/SKILL.md:86-92`: "A window written with `$today` moves each day, so its rows, and therefore its bytes, can change on a day with no new workouts."
- Wrapping: `docs/dashboards.md:137` is 96 characters ("`Not rendered:` note stays) and the failure is reported. A chart whose directive or region has a") and `:147` is 127 characters ("in `dashboards/assets/` that does not carry the mark. When a `refresh` or `freeze` run, or the pass after an index refresh, has"), where most prose lines are about 80. (`awk 'length($0) > 90'` lists these and the table rows.) Reported by the 7.3 reviewer subagent as "cosmetic".

## How to pick it up
1. Edit the two sentences to add the `$today` caveat (borrow the skill's wording) and keep the true half: a window written as a fixed date range, or a chart over unchanged rows, does not change.
2. Re-wrap lines 137 and 147 to the page's width.
3. Run `uv run pytest tests/dashboards/test_docs_dashboards.py -q`; the docs test pins parts of this page (the live kinds block and quoted sentences), so update any pin that quotes the old sentences.

## Resolution (2026-10-19, commit af769c6, branch chore/docs-0-2)

Both sentences in `docs/dashboards.md` corrected. "Relative and frozen
charts": a run whose rows are unchanged writes nothing; a `$today` window
(like the page's own example) moves each day and can change on a day with no
new workouts; a chart whose SQL does not use `$today` changes only with its
rows, directive or the chart kit. "Version control": the working tree stays
clean after a no-new-data sync only for charts whose SQL does not use
`$today`. The over-long image-cleanup paragraph is re-wrapped; the other
over-long prose lines (`:38`, `:286`) predate the item's evidence and were
left. Pinned by
`tests/dashboards/test_docs_dashboards.py::test_no_new_data_keeps_a_chart_unchanged_only_without_today`
(also asserts the example still uses `$today - 84`; reds on the old page).
