---
id: 2026-10-18-query-fixture-tags-first-glob-entry-fails-west-of-utc
title: Four analytics-query tests fail under a negative-offset TZ because the indexed-root fixture tags whatever workouts/*.md entry the glob returns first
status: open
importance: low
importance_why: Test-only; the suite passes under UTC (CI) and positive offsets, but a contributor west of UTC sees 4 red tests that say nothing about their change.
effort: S
kind: bug
area: analytics-query, tests/query/conftest.py
created: 2026-10-18
surfaced_by: second review of chore/q-local-tz (full suite under TZ=America/New_York in a git-archive copy), reproduced by the controller on an origin/main archive
pinned_at: 1ad6b6f
resume_command: "do: make tests/query/conftest.py's indexed_root fixture tag a specific workout page (sorted, AGENTS.md excluded, chosen by stem) instead of the first glob entry, then run tests/query under TZ=America/New_York, UTC and Asia/Tokyo [queue: .kiro/queue/2026-10-18-query-fixture-tags-first-glob-entry-fails-west-of-utc.md]"
context:
  - tests/query/conftest.py
  - tests/query/test_fixtures.py
  - tests/query/test_freshness.py
  - tests/query/test_skill_examples.py
blocked_by: []
---

## What

On an `origin/main` (`1ad6b6f`) archive copy, the controller ran:
`tests/query/test_fixtures.py::test_indexed_root_has_multi_page_nonempty_core_data`,
`tests/query/test_freshness.py::test_page_drift_counts_each_change_on_independent_copies`
and `tests/query/test_skill_examples.py`. The results:

```
TZ=America/New_York: 4 failed, 12 passed
TZ=UTC:              16 passed
TZ=Asia/Tokyo:       16 passed
```

The first failure is `tests/query/test_fixtures.py:87`, `assert len(effort_rows) == 1`
(it got `0`): no page in the index carries the fixture's effort tag.

## Suspected cause (not verified)

`tests/query/conftest.py` (the `indexed_root` fixture) writes pages with
`fitdocs sync` in the host zone. It then takes
`pages = tuple((root / "workouts").glob("*.md"))` and tags `pages[0]`.

That glob is unsorted and includes `workouts/AGENTS.md`. The page names
depend on the zone (`2021-09-07-…` west of UTC, `2021-09-08-…` east), and so
does the directory order. In a western zone the first entry is plausibly
`AGENTS.md`, which has no `---\n` fence, so `replace` changes nothing and no
page is tagged. Confirm this by printing `pages[0]` under
`TZ=America/New_York`.

## How to pick it up

1. Reproduce with the three `TZ` values above.
2. Choose the page explicitly: sort, skip `AGENTS.md`, and match by sport or
   stem. Assert that the tag landed.
3. Done when `tests/query` passes under all three zones.
