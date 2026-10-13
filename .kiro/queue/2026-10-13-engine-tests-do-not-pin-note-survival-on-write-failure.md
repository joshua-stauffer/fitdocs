---
id: 2026-10-13-engine-tests-do-not-pin-note-survival-on-write-failure
title: No engine test pins that a never-rendered chart's earlier `Not rendered:` note survives an image, page or snapshot write failure, although the contract and docs state it
status: open
importance: low
importance_why: The behaviour is right today and documented; a regression that drops or rewrites the note on a failed write would leave the page showing stale error text with the suite green.
effort: S
kind: gap
area: dashboards, tests/dashboards/test_engine.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 7.3 reviewer)
pinned_at: 0a98d5c
resume_command: "do: add three engine tests (image, page and snapshot write failure) that start from a chart already carrying a `Not rendered:` note and assert the region is byte-identical after the failed write; see the reviewer probe quoted in the item [queue: .kiro/queue/2026-10-13-engine-tests-do-not-pin-note-survival-on-write-failure.md]"
context:
  - tests/dashboards/test_engine.py
  - src/fitdocs/dashboards/engine.py
  - docs/dashboards.md
  - docs/ownership-contract.md
blocked_by:
  - dashboards
---

## What
`docs/dashboards.md` (lines 135-137) says that when a chart's image, snapshot or
page cannot be written, its region is left as it was, and "an earlier
`Not rendered:` note stays"; the ownership contract says the region "is left as
it was" (`docs/ownership-contract.md:939-941`). The existing write-failure tests
start from a chart that has never been written: the image test
(`test_an_image_that_cannot_be_written_fails_that_chart_and_drops_its_region`,
`tests/dashboards/test_engine.py` line 1868), the page test
(`test_a_page_that_cannot_be_replaced_is_write_failed_not_page_changed`, line
1796) and the snapshot test
(`test_a_snapshot_that_cannot_be_created_fails_the_chart_and_writes_no_image`,
line 2713) all start from a chart whose region does not exist yet (the image test
and the snapshot test assert that none appears). None starts from a region that
already holds a note, so nothing pins that the note survives.

## Why it matters
The consequence the docs promise is exactly that survival: the page keeps
showing why the chart is blank. If a refactor made a failed write clear or
rewrite the region, the page would show a stale or empty region and every
existing test would still pass.

## Evidence
Reviewer probe `/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/e6978888-5f66-4ba4-8392-5c49f509f8bf/scratchpad/7-3-reviewer/test_probe_7_3.py`
(wiped on reboot). Re-run at 0a98d5c with `pytest -s`, observed output:

```
RUN1 [['sql_failed']]
RUN1 region ['*Not rendered: Boom old error.*', '']
RUN2 [(failed, ['write_failed'], ['The image could not be written: disk full.'])]
RUN2 has region: True
RUN2 region ['*Not rendered: Boom old error.*', '']          # image write failure: note survives
RUN2 [(failed, ['write_failed'])]
RUN2 region ['*Not rendered: Boom old error.*', '']          # page write failure: note survives
SNAP RUN2 [(failed, ['The snapshot could not be written: disk full.'])]
SNAP RUN2 region ['*Not rendered: Boom old error.*', ''] page identical: True   # snapshot write failure: note survives
QUERYFAIL+PAGEFAIL [(failed, ['sql_failed', 'write_failed'])]  has region: False   # fresh chart, page write fails: no region
```

So the behaviour is correct in all three cases; only the pins are missing.
`grep -n "Not rendered" tests/dashboards/test_engine.py` shows the note asserted
after successful runs and for fresh charts (lines 1406-2696), never after a
failed write that follows a note.

## How to pick it up
1. Copy the probe's three cases into `tests/dashboards/test_engine.py` using the module's own helpers (`make_data_root`, `own`/`fro`, `go`, `source_of`, `region_lines`, `page_bytes`; `monkeypatch.setattr(engine, "write_asset" | "replace_page" | "create_snapshot", failing)`).
2. Assert the region lines equal the earlier note exactly and, for the page case, that the page bytes are unchanged.
3. Mutation check: make a failed write clear the region and confirm each test goes red.
