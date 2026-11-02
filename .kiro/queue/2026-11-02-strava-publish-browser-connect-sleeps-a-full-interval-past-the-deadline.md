---
id: 2026-11-02-strava-publish-browser-connect-sleeps-a-full-interval-past-the-deadline
title: "browser_connect's poll loop sleeps a whole interval after the deadline has passed"
status: open
importance: low
importance_why: "A terminal user waits up to one provider interval longer than the stated time limit."
effort: S
kind: bug
area: "src/fitdocs/connectors/browser_connect.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 5.6 review and validate-impl"
pinned_at: 964cc419
resume_command: "do: clip the final sleep in browser_connect's engine to the remaining time and add a test with a fake clock (read .kiro/queue/2026-11-02-strava-publish-browser-connect-sleeps-a-full-interval-past-the-deadline.md first)"
context:
  - src/fitdocs/connectors/browser_connect.py
  - .kiro/specs/strava-publish/design.md
blocked_by: []
---

## What
The consent poll sleeps `started.interval_s` each loop and checks the deadline only after the sleep.

## Why it matters
Overrun of up to one interval (seconds) beyond the documented limit.

## Evidence
`src/fitdocs/connectors/browser_connect.py:246`: `sleep(started.interval_s)` (loop context not fully re-read; overrun is the reviewer's claim).

## How to pick it up
Read the loop around :246, compute `min(interval, remaining)`, test with an injected clock and sleep.
