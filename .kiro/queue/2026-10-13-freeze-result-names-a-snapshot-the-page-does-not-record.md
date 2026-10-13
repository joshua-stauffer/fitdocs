---
id: 2026-10-13-freeze-result-names-a-snapshot-the-page-does-not-record
title: After a freeze whose page write fails, ChartResult.snapshot names the newly created snapshot while the page still records the old one
status: open
importance: low
importance_why: The JSON report names a snapshot the page does not point at; the new file is a harmless extra generation (never deleted, adopted on the next run), but a consumer reading the report is misinformed.
effort: S
kind: bug
area: dashboards, src/fitdocs/dashboards/engine.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 5.3 reviewer)
pinned_at: 0a98d5c
resume_command: "do: when _replace_page fails (page_changed or write_failed) set each affected ChartResult.snapshot back to the path the page still records, or document that it means 'created this run'; add an engine test for a freeze whose page write fails [queue: .kiro/queue/2026-10-13-freeze-result-names-a-snapshot-the-page-does-not-record.md]"
context:
  - src/fitdocs/dashboards/engine.py
  - src/fitdocs/dashboards/report.py
  - tests/dashboards/test_engine.py
  - .kiro/specs/dashboards/design.md
blocked_by:
  - dashboards
---

## What
Per page the engine writes new snapshots, then images, then replaces the page
once (`_run_page`, `src/fitdocs/dashboards/engine.py:1179-1230`).
`_write_snapshots` sets `each.snapshot = path` the moment the snapshot file
exists (`engine.py:1107`), and `ChartResult(snapshot=each.snapshot)` reports it
(`engine.py:1212`). If the later `_replace_page` fails (`write_failed`) or the
page changed during the run (`page_changed`), the page keeps its old region and
still records the old snapshot, but the result and the JSON report
(`report.py:80` serialises `chart.snapshot`) name the new one.

## Why it matters
`fitdocs dashboard freeze --format json` tells an agent that chart `c` is now
drawn from `snapshot-3` while the page still records `snapshot-2`. The design
accepts a leftover extra generation after a failed re-freeze, but it does not
say the report may name it.

## Evidence
Reported by the 5.3 reviewer subagent, reproduced in this session at 0a98d5c.
Code: `engine.py:1107` assigns before the page write, `engine.py:1194-1196`
(inside `_run_page`) runs `_write_snapshots`, `_write_assets`, `_replace_page`
in that order, and `engine.py:1212` reads `each.snapshot` unconditionally.

Probe (a pytest file in the session scratchpad,
`/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/43144b56-a94d-45f3-a857-8e0a466250cf/scratchpad/test_probe_freeze_snapshot.py`,
wiped on reboot; it renders a frozen chart, then freezes it again with
`engine.replace_page` raising `OSError("disk full")`), observed output:

```
RUN1 region: <!-- fitdocs:snapshot assets/p/c.snapshot-1.json -->
FREEZE result: outcome failed snapshot assets/p/c.snapshot-2.json problems ['write_failed']
page still records: <!-- fitdocs:snapshot assets/p/c.snapshot-1.json -->
snapshot files: ['c.snapshot-1.json', 'c.snapshot-2.json']
```

The tasks.md 5.3 note
(`.kiro/specs/dashboards/tasks.md:1531`) records "A failed re-freeze can leave an
unused extra generation".

## How to pick it up
1. Add an engine test first: freeze a frozen chart with `replace_page` monkeypatched to raise `OSError` (see the existing pattern at `tests/dashboards/test_engine.py:1796-1830`); assert what `ChartResult.snapshot` holds.
2. Decide the meaning of the field (planned/recorded path versus created path). If it means "the path the page records", reset it for charts whose edit was not written; if it means "created this run", rename or document it.
3. Update `design.md` § Engine and the report docs accordingly.

## Open questions
Which meaning the field should carry; the 5.3 note took "created path, else planned, else None" (`tasks.md:1517-1518`) without considering the failed page write.
