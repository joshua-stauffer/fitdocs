---
id: 2026-11-01-connector-session-construction-duplicated
title: "Data-session construction is duplicated in connectors.pull and publish.targets"
status: open
importance: low
importance_why: Drift risk only; both copies work today.
effort: S
kind: chore
area: src/fitdocs/connectors/pull.py, src/fitdocs/publish/targets.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: extract one shared data-session builder and use it from connectors/pull.py and publish/targets.py [queue: .kiro/queue/2026-11-01-connector-session-construction-duplicated.md]"
context:
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/publish/targets.py
blocked_by: []
---

## What
The data session is built the same way in two places with no shared builder.

## Why it matters
A change to one (headers, timeouts, redaction fields) must be found and repeated
in the other.

## Evidence
`src/fitdocs/connectors/pull.py:712-723` and `src/fitdocs/publish/targets.py:~187-196`.

## How to pick it up
Compare the two blocks, put one builder where both may import it (respecting the
publish/connectors import rules), and switch both.
