---
id: 2026-11-07-post-template-check-refused-file-says-nothing-about-sql
title: "Say the SQL was not checked when check's template file is refused"
status: open
importance: low
importance_why: "A refused file hides that its SQL was never checked."
effort: S
kind: gap
area: "post-templates, src/fitdocs/post_template/engine.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: in post_template/engine.py run_check, add an explicit 'the SQL was not checked because the file was refused' line when the template is refused [queue: .kiro/queue/2026-11-07-post-template-check-refused-file-says-nothing-about-sql.md]"
context:
  - src/fitdocs/post_template/engine.py
  - src/fitdocs/post_template/report.py
blocked_by: []
---

## What
With a refused template, `run_check` never runs the SQL check and does not say so, unless the index is also unavailable.

## Why it matters
The user fixes the file, reruns, and only then learns about SQL problems.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it.

## How to pick it up
1. Add the line to check's report.
2. Pin it in test_check_refill.py and test_report.py.
