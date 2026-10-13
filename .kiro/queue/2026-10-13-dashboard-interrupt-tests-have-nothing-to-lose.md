---
id: 2026-10-13-dashboard-interrupt-tests-have-nothing-to-lose
title: The real-process dashboard interrupt test starts from a page with no region, image or snapshot, and no real-process test interrupts the post-index pass
status: open
importance: low
importance_why: The "nothing was overwritten or cleaned" assertions in the interrupt test hold trivially, and Req 13.7 (interrupt during the chained pass) is pinned only by a fake that raises KeyboardInterrupt from a stub.
effort: M
kind: gap
area: dashboards, tests/dashboards/test_interrupt.py, tests/dashboards/test_pass.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 6.3 reviewer)
pinned_at: 0a98d5c
resume_command: "do: add a second real-process case to tests/dashboards/test_interrupt.py whose page already holds a rendered region, an image and a frozen snapshot, and a third that sends SIGINT during the chained pass of fitdocs sync (Req 13.7); both must assert the earlier bytes survive and the exit is 130 [queue: .kiro/queue/2026-10-13-dashboard-interrupt-tests-have-nothing-to-lose.md]"
context:
  - tests/dashboards/test_interrupt.py
  - tests/dashboards/test_pass.py
  - tests/dashboards/conftest.py
  - src/fitdocs/cli.py
  - .kiro/specs/dashboards/requirements.md
blocked_by:
  - dashboards
---

## What
Two related holes in the interrupt coverage of the dashboards run.

1. **Nothing to overwrite.** `test_sigint_during_a_running_chart_ends_the_run_cleanly`
   (`tests/dashboards/test_interrupt.py:171`) writes one page holding a single
   new relative chart (`write_page(fixture.root, "p", page_text(directive_block(keys)))`, line 185),
   with no region, no image and no snapshot. Its assertions that the page is
   byte-identical, that `dashboards/` is untouched, that no `*.svg` exists and
   that no `.dashboards-*.tmp` is left (lines 163-168) would also pass if the
   run had never been going to write anything. The test cannot observe an
   interrupted run overwriting an earlier region, replacing an image, or the
   cleanup deleting one.
2. **No real-process test of the chained pass.** Req 13.7 says an interrupt of
   the pass after an index refresh ends the command exactly as an interrupt of
   the index refresh does. The only tests are fakes:
   `tests/dashboards/test_pass.py:391-425` raises `KeyboardInterrupt` from a
   monkeypatched `has_dashboards` and `run_dashboards`. No test starts
   `fitdocs sync` (or `regen`, `load`, `pull --sync`) as a process and signals
   it during the dashboard pass. `grep -n "sync\|regen\|refresh" tests/dashboards/test_interrupt.py`
   finds only the `dashboard refresh` argv at lines 125-126.

## Why it matters
The Req 7.10 and 14.8 promise is that an interrupt loses nothing already on
disk. The current test is green for a run that would have lost it. The chained
pass is the path an athlete hits most (every sync), and the real-process
behaviour of DuckDB under SIGINT has already differed from the fakes once (see
`2026-10-13-sigint-ignored-during-streaming-query-statements`).

## Evidence
Verified by reading at 0a98d5c:
- `tests/dashboards/test_interrupt.py:171-197` builds the page (line 185); `assert_untouched(before, snapshot_of(dashboards))` at line 164 compares the directory before and after a run that, uninterrupted, would have created a region and an image; the page has no earlier output to lose.
- `src/fitdocs/cli.py:575-620` (`_run_dashboard_pass`) documents "an interrupt (`BaseException`) is not caught"; its callers are `sync_command` (line 827), `_run_drain_passes` (914), `regen_command` (1013) and `load_command` (1049).
- The reviewer's note is the origin: "6.3 fixture has no previously rendered region/asset/snapshot (cannot observe an interrupted run overwriting/cleaning); 13.7 has no real-process test for interrupt during the post-index pass".

## How to pick it up
1. Read `tests/dashboards/test_interrupt.py` end to end and `tests/dashboards/conftest.py` (`indexed_dashboard_root`, `copy_dashboard_root`).
2. Case A: first run `fitdocs dashboard refresh` to completion over a page with a relative chart and a frozen one, record `snapshot_of(dashboards)`, then edit the SQL so the relative chart re-runs a minutes-long aggregating statement, send SIGINT, and assert the earlier region, image and snapshot bytes are unchanged (a page whose region would have been rewritten but for the interrupt).
3. Case B: a `fitdocs sync --no-prompt` over a source folder with a dashboard page whose chart is minutes long; send SIGINT once the marker appears. Assert exit 130 and the documents the sync wrote before the pass are intact. Check what exit code and stderr line an interrupt of the index refresh produces today and assert the same.
4. Keep every wait bounded and the process group killed in `finally`, as the existing test does. Use aggregating statements only until the streaming-statement item is fixed.

## Open questions
The expected exit and stderr text for an interrupt during the chained pass: Req 13.7 says "exactly as an interrupt during the index refresh does", and nothing in the repo shows what that is for a full `sync`. Measure it first.
