---
id: 2026-11-05-oversize-download-reads-as-could-not-reach-garmin
title: An over-64 MiB Garmin response reads as Garmin being unreachable
status: open
importance: low
importance_why: Needs an activity file over 64 MiB, which is rare; the wording misleads and the failure repeats each pull.
effort: S
kind: bug
area: garmin-connector, src/fitdocs/connectors/http.py, src/fitdocs/connectors/garmin.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "/kiro-impl garmin-connector [queue: .kiro/queue/2026-11-05-oversize-download-reads-as-could-not-reach-garmin.md] Report an oversize response as too large"
context:
  - src/fitdocs/connectors/http.py
  - src/fitdocs/connectors/garmin.py
  - .kiro/specs/garmin-connector/design.md
blocked_by: []
---

## What
`HttpClient` raises `TransportError` for a body over its bound, the same type as a network failure. Garmin's listing then says Garmin "could not be reached" and that the next pull resumes, and a download counts toward the five-in-a-row stop. The transport's retry loop also re-attempts it.

## Why it matters
An activity that can never download is reported as an outage and is retried on every pull.

## Evidence
`src/fitdocs/connectors/http.py:197-198`; `_count_failure` in `garmin.py`. Read, not exercised with a real oversize body (task 3.5 reviewer).

## How to pick it up
Check whether a distinct subclass of `TransportError` lets Garmin name the size without changing other connectors, and whether retrying it is ever useful.
