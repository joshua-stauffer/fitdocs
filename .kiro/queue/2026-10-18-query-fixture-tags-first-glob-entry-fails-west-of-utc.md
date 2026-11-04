---
id: 2026-10-18-query-fixture-tags-first-glob-entry-fails-west-of-utc
title: Two analytics-query tests hard-code a UTC page date and fail under a negative-offset TZ
status: open
importance: low
importance_why: Test-only; CI runs in UTC, so a contributor west of UTC sees two red tests that say nothing about their change. The flaky half of the original item is fixed.
effort: S
kind: bug
area: analytics-query, tests/query/conftest.py
created: 2026-10-18
surfaced_by: second review of chore/q-local-tz (full suite under TZ=America/New_York in a git-archive copy), reproduced by the controller on an origin/main archive
pinned_at: 1ad6b6f
resume_command: "do: make tests/query/test_skill_examples.py expect the page date the fixture actually produced, or pin the zone, so that it passes under TZ=UTC, America/New_York and Asia/Tokyo (read .kiro/queue/2026-10-18-query-fixture-tags-first-glob-entry-fails-west-of-utc.md first)"
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

## Update 2026-11-04
The fixture half is fixed (b8cc3e4f): `indexed_root` now sorts the pages, excludes `AGENTS.md`, and asserts that the tag landed. This item's first assumption was also wrong: the unsorted glob failed on CI too, in UTC, depending on directory order, and that is why it was fixed.

Two tests remain red under `TZ=America/New_York` (2 failed, 38 passed; UTC and Asia/Tokyo pass 40). They are `test_every_skill_sql_fence_runs_and_returns_topic_rows` and `test_thresholds_example_includes_a_historical_closed_period`. Both expect the ride on 2021-09-08 (`tests/query/test_skill_examples.py:281`), but `sync` dates the page 2021-09-07 from the host zone, because the fixture file carries no recorded offset. The same two failed at 61c2ece1, before the fixture fix.
