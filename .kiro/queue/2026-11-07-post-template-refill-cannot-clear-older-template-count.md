---
id: 2026-11-07-post-template-refill-cannot-clear-older-template-count
title: Let refill update the stamp when the template changed but the text did not
status: open
importance: low
importance_why: `check` keeps counting a page as "Filled from an earlier template" after a refill that produced the same text.
effort: S
kind: bug
area: post-templates, src/fitdocs/post_template/engine.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: in post_template/engine.py, rewrite the stamp (not the text) on an UNCHANGED fill when the stamp's template digest differs, or reword check's older-template count [queue: .kiro/queue/2026-11-07-post-template-refill-cannot-clear-older-template-count.md]"
context:
  - src/fitdocs/post_template/engine.py
  - src/fitdocs/post_template/region.py
  - .kiro/specs/post-templates/requirements.md
blocked_by: []
---

## What
When the SQL changes but the composed text does not, the row is UNCHANGED, nothing is written, and the old stamp stays.

## Why it matters
The older-template count never clears, so it stops being a useful signal.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. The validator's probe: `older_template` was 1 before and after `refill PAGE --yes`.

## How to pick it up
1. Check Req 10.11 (identical recomposition writes nothing).
2. Decide whether a stamp-only rewrite is allowed; amend 10.11 if so.
3. Pin it with an engine test.
