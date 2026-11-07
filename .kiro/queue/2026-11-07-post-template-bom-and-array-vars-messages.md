---
id: 2026-11-07-post-template-bom-and-array-vars-messages
title: "Improve post-template.toml messages for a UTF-8 BOM and [[vars]]"
status: open
importance: low
importance_why: "Two common hand-editing mistakes produce confusing messages."
effort: S
kind: gap
area: "post-templates, src/fitdocs/post_template/template.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: in post_template/template.py, give a UTF-8 BOM and an array-of-tables [[vars]] each one clear problem [queue: .kiro/queue/2026-11-07-post-template-bom-and-array-vars-messages.md]"
context:
  - src/fitdocs/post_template/template.py
blocked_by: []
---

## What
A file with a UTF-8 BOM is refused as `Invalid statement (at line 1, column 1)`, as settings.py does. `[[vars]]` (an array of tables) yields a vars-shape problem plus an unknown-placeholder problem for each use.

## Why it matters
Editors on Windows add BOMs; `[[vars]]` is a natural TOML guess.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it.

## How to pick it up
1. Strip or name the BOM.
2. Detect a list `vars` and report one problem.
3. Add tests.
