---
id: 2026-10-13-stale-image-cleanup-oserror-escapes-and-skip-is-silent
title: remove_stale_images lets an OSError escape after every page is written, and a skipped cleanup is reported as nothing removed
status: open
importance: medium
importance_why: A failed unlink after a run has already rewritten pages ends the command with a traceback (or, in the chained pass, a misleading `not refreshed` line) with no problem code; and when cleanup is skipped the report is indistinguishable from a clean run.
effort: S
kind: bug
area: dashboards, src/fitdocs/dashboards/storage.py, src/fitdocs/dashboards/engine.py, src/fitdocs/cli.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 5.3, ruling R12; 5.3 reviewer)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-design dashboards [queue: .kiro/queue/2026-10-13-stale-image-cleanup-oserror-escapes-and-skip-is-silent.md] handle a stale-image cleanup OSError and report a skipped cleanup"
context:
  - src/fitdocs/dashboards/storage.py
  - src/fitdocs/dashboards/engine.py
  - src/fitdocs/dashboards/problems.py
  - src/fitdocs/cli.py
  - tests/dashboards/test_storage.py
  - tests/dashboards/test_engine.py
  - .kiro/specs/dashboards/tasks.md
  - .kiro/specs/dashboards/design.md
blocked_by:
  - dashboards
---

## What
Two faces of one gap in the stale-image cleanup that `refresh` and `freeze`
run after all pages (Req 6.4, 6.5).

1. **An OSError escapes.** `remove_stale_images` does `os.listdir`,
   `os.unlink(image)` and `os.rmdir(folder)` with no handler
   (`src/fitdocs/dashboards/storage.py:439, 444, 455, 458-459`). A permission
   or I/O error propagates out of `run_dashboards`
   (`src/fitdocs/dashboards/engine.py:1262`) after every page and snapshot has
   been written. Ruling R12 (`.kiro/specs/dashboards/tasks.md:1530`) recorded it
   as "a cleanup OSError is unhandled (queued)".
2. **A skipped cleanup is silent.** `remove_stale_images` returns `None` when it
   skips (unreadable page, non-UTF-8 markdown, linked location), and the engine
   turns that into `()` with `removed = remove_stale_images(...) or ()`
   (`engine.py:1262`). The report then says nothing was removed, exactly as for
   a run with nothing to remove. No `DashboardCode` covers it (there are 38
   codes in `problems.py`; none is about cleanup).

## Why it matters
For (1) the user sees a Python traceback from `fitdocs dashboard refresh`, or
from the chained pass the one line `Dashboards: not refreshed; PermissionError:
...` even though the pages were refreshed, so the message is false. For (2) a
stale image the user expects gone stays, with no hint why.

## Evidence
Run against 0a98d5c (the session probe `stale_oserror.py` lived under
`/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/43144b56-a94d-45f3-a857-8e0a466250cf/scratchpad/`,
wiped on reboot):

```
case1 (marked stale image in a read-only assets/p/ folder):
  remove_stale_images(root) raised PermissionError [Errno 13] Permission denied: '.../dashboards/assets/p/old.svg'
case2 (the only page chmod 000):
  remove_stale_images(root) returned None        # the engine turns this into ()
image still there: True
```

- `cli.py` `dashboard` command catches `TargetError`, `IndexLocationError` and `KeyboardInterrupt` only (`src/fitdocs/cli.py:2179-2185`), so case 1 is a traceback there.
- The chained pass catches `Exception` and prints `Dashboards: not refreshed; {type}: {message}.` (`cli.py:616-620`).
- The 5.3 reviewer's "skipped cleanup is silent" finding is the same code path as item 2 (reported, confirmed here).

## How to pick it up
1. Read `remove_stale_images` (`storage.py:414-460`), `run_dashboards` (`engine.py:1225-1270`) and `.kiro/specs/dashboards/design.md` § Storage and § System Flows for where cleanup sits.
2. Decide the shape: catch `OSError` per file inside `remove_stale_images` and return what was removed plus what failed, and add a problem or notice code (for example `cleanup_failed` / `cleanup_skipped`) carried on `RunReport`. A skipped cleanup gets a notice that names the reason.
3. Add a code to `DashboardCode` only with its table row in `report.py`, the docs and the skill. Tests: a read-only folder (as above) must yield a reported failure, exit status per `report.failed`, and the pages still written; an unreadable page must yield a skip notice.

## Open questions
Is a cleanup failure a `report.failed` outcome (exit 1) or a notice? Req 6.4/6.5 are silent. Whether a skipped cleanup is a notice (exit 0) or a problem.
