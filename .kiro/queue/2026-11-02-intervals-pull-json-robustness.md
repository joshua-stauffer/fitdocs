---
id: 2026-11-02-intervals-pull-json-robustness
title: intervals.icu pull and key-check JSON parsing can raise on hostile bodies
status: open
importance: low
importance_why: A deeply nested or huge-number 200 body raises RecursionError/OverflowError out of the pull instead of a connector error.
effort: S
kind: robustness
area: intervals-connector, wellness-pull, src/fitdocs/connectors/intervals.py
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-impl intervals-connector [queue: .kiro/queue/2026-11-02-intervals-pull-json-robustness.md] Harden pull-path JSON parsing like the publish path"
context:
  - src/fitdocs/connectors/intervals.py
  - tests/connectors/test_intervals.py
blocked_by: []
---

## What
The pull, wellness and key-check paths catch only ValueError/UnicodeError around json.loads, and `_remote_activity` calls float() on any int. The publish path (intervals-publish 2.3) catches RecursionError and treats float() OverflowError as absent.

## Why it matters
A pathological body ends a pull with an unhandled exception rather than a reported connector failure.

## Evidence
src/fitdocs/connectors/intervals.py ~304-305, 367-368, 441-442 (except clauses); `_remote_activity` float(elapsed). Observed by the 2.3 reviewer: b'[' * 200000 raises RecursionError; int('9'*400) raises OverflowError.

## How to pick it up
Mirror `_listed_activities` / `_listed_activity`: catch RecursionError, convert then check finiteness, decode strictly as UTF-8. Add tests with the same hostile bodies.
