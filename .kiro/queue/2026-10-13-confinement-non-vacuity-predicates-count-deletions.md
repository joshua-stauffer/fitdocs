---
id: 2026-10-13-confinement-non-vacuity-predicates-count-deletions
title: The confinement guard's non-vacuity predicates test membership in a touched set that includes deleted paths, so a run that deleted its output satisfies them
status: open
importance: low
importance_why: The guard's second half ("the run really wrote something") exists to stop a pipeline that silently stopped writing from passing; a pipeline that deleted its page or image would pass it instead.
effort: S
kind: gap
area: wiki-contract, dashboards, tests/test_confinement.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 6.4 reviewer)
pinned_at: 0a98d5c
resume_command: "do: have tests/test_confinement.py give non_vacuous predicates the created-or-modified paths (split _touched into created, modified and deleted) so a deletion cannot satisfy them, starting with the dashboard predicates, and add one deletion control per predicate family [queue: .kiro/queue/2026-10-13-confinement-non-vacuity-predicates-count-deletions.md]"
context:
  - tests/test_confinement.py
  - .kiro/specs/wiki-contract/requirements.md
  - .kiro/queue/2026-09-17-confinement-and-boundary-guard-gaps.md
blocked_by:
  - dashboards
---

## What
`_touched` returns every path created, modified or deleted between two
snapshots (`tests/test_confinement.py:238-246`; it unions the key sets and
compares with an `_ABSENT` default). Each entry point's `non_vacuous` predicate
receives that one tuple and checks membership, for example
`_dashboard_files` (line 1338) tests `_DASHBOARD_PAGE_FILE in touched` and the
asset and snapshot names. Membership cannot distinguish a write from a
deletion.

## Why it matters
`test_entry_point_writes_only_inside_the_permitted_locations` asserts the run
"produced its own observable write" so that a pipeline which silently stopped
writing cannot pass by doing nothing. A pipeline that instead deleted the page
and the images it should have written would pass the dashboard predicates, and
the confinement half is satisfied too, because deletions inside owned paths are
permitted.

## Evidence
At 0a98d5c:

```
before = {page, load.svg, peak.svg, peak.snapshot-1.json}   # the four files a dashboard run writes
touched = _touched(before, {})                              # the run DELETED all four
-> ('data/dashboards/assets/board/load.svg', 'data/dashboards/assets/board/peak.snapshot-1.json',
    'data/dashboards/assets/board/peak.svg', 'data/dashboards/board.md')
_wrote_a_first_freeze_and_a_drawn_page(touched) -> True
```

The other predicates have the same shape, for example
`_wrote_index_file` (`any(path.endswith("/index.duckdb") for path in touched)`,
line 425-426). Reported by the 6.4 reviewer subagent; reproduced here for the
dashboard predicate.

## How to pick it up
1. Read `_touched`, `assert_confined` and the `non_vacuous` field of `EntryPoint`, with its docstring, in `tests/test_confinement.py` (lines 225-260 and 1117-1136).
2. Return a small structure from the snapshot diff (created, modified, deleted) and pass the created-or-modified paths to `non_vacuous`; keep `assert_confined` over all three.
3. Add one control per predicate family: a synthetic before/after in which the run only deletes must fail the predicate. Done means no predicate is satisfied by a deletion.

## Open questions
Whether any entry point's legitimate observable write is a deletion (a rename counts as one delete and one create today; `_renamed_a_workout_document` at line 961 needs both and should keep passing).
