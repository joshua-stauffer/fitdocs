---
id: 2026-11-01-connectors-clock-scan-substring-false-positive
title: "The connectors clock scan is a substring test, so time.time matches inside datetime.timedelta"
status: open
importance: low
importance_why: Latent false positive only; no current source trips it.
effort: S
kind: bug
area: connectors, tests/connectors/test_boundary.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: replace the substring clock scan in tests/connectors/test_boundary.py with token or AST matching [queue: .kiro/queue/2026-11-01-connectors-clock-scan-substring-false-positive.md]"
context:
  - tests/connectors/test_boundary.py
blocked_by: []
---

## What
The clock scan near `tests/connectors/test_boundary.py:656` is a plain
substring test, so `time.time` matches inside `datetime.timedelta`.

## Why it matters
Any module that legitimately uses `datetime.timedelta` would be flagged as
reading the clock.

## Evidence
`tests/connectors/test_boundary.py:~656`; a source line containing
`datetime.timedelta` contains the substring `time.time`.

## How to pick it up
1. Read the scan at ~656.
2. Match on tokens or the AST (attribute access `time.time`), not substrings.
3. Add a case with `datetime.timedelta` that must not be flagged.
