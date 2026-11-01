---
id: 2026-11-01-region-splice-adjacent-markers-morning-load
title: "Morning and load region splices report a region missing when its begin and end markers are adjacent"
status: open
importance: low
importance_why: Low-medium; needs a hand-emptied region, but the splice then misreports a region docmerge.extract_regions reads as empty.
effort: S
kind: bug
area: src/fitdocs/morning/docedit.py, src/fitdocs/load/docedit.py, src/fitdocs/publish/links.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: use the begin/(?:.*?\\n)?end regex in replace_morning and replace_load_region, drop the false pragma: no cover, and test adjacent markers (see 2026-10-13-region-splice-regex-duplicated-for-morning) [queue: .kiro/queue/2026-11-01-region-splice-adjacent-markers-morning-load.md]"
context:
  - src/fitdocs/morning/docedit.py
  - src/fitdocs/load/docedit.py
  - src/fitdocs/publish/links.py
  - src/fitdocs/docmerge.py
  - .kiro/queue/2026-10-13-region-splice-regex-duplicated-for-morning.md
blocked_by: []
---

## What
When a region's begin and end markers are adjacent (no line between),
`replace_morning` (`src/fitdocs/morning/docedit.py:25-32`) and
`replace_load_region` (`src/fitdocs/load/docedit.py:~234`) report the region
missing, although `docmerge.extract_regions` returns `''` for it. They use the
regex `^begin\n.*?\nend$` and carry a false `pragma: no cover`. publish-core
fixed the same gap in `src/fitdocs/publish/links.py` with
`^begin\n(?:.*?\n)?end$`.

## Why it matters
The splice and the reader disagree about whether the region exists.

## Evidence
The cited lines; compare `links.py`'s regex. Related existing open item:
`2026-10-13-region-splice-regex-duplicated-for-morning` (do the work there if a
shared `replace_region` lands first).

## How to pick it up
Apply the fixed regex in both (or via the shared helper), remove the pragma, and
add an adjacent-markers test to each.
