---
id: 2026-11-07-post-template-resolve-next-steps-use-backticks
title: "Drop markdown backticks from the resolver's plain-text next steps"
status: open
importance: low
importance_why: "The text output prints literal backticks next to engine steps without them."
effort: S
kind: chore
area: "post-templates, src/fitdocs/post_template/resolve.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: remove markdown backticks from Unavailable next steps in post_template/resolve.py and update their tests [queue: .kiro/queue/2026-11-07-post-template-resolve-next-steps-use-backticks.md]"
context:
  - src/fitdocs/post_template/resolve.py
  - tests/post_template/test_resolve.py
blocked_by: []
---

## What
`open_resolver`'s Unavailable next steps read like "run `fitdocs index`" (resolve.py around 196/200), while engine-written steps have no backticks.

## Why it matters
Mixed styles in one output.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it.

## How to pick it up
1. Edit the strings.
2. Update the pinned tests.
