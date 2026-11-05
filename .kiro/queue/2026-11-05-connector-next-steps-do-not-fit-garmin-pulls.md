---
id: 2026-11-05-connector-next-steps-do-not-fit-garmin-pulls
title: Framework next steps read wrongly after Garmin pull messages
status: open
importance: low
importance_why: Wording only: reports stay correct in substance, with a misleading or doubled tail.
effort: S
kind: inconsistency
area: connectors, src/fitdocs/connectors/errors.py, src/fitdocs/connectors/pull.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Make connector next steps fit a failure that happened during a data pull rather than a sign-in"
context:
  - src/fitdocs/connectors/errors.py
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/garmin.py
  - .kiro/specs/connectors/requirements.md
blocked_by: []
---

## What
The engine appends a kind's `NEXT_STEPS` text to each `AuthFailure` message. On Garmin paths it reads wrongly: a 429 past the waits ends "fitdocs never retries a sign-in" though the connector repeated the request; a 403 refusal adds "Check the credentials"; a 401 states the reconnect step twice. At connect, UNAVAILABLE says "The service could not be reached" even when the service answered, for example a 200 that is not a token.

## Why it matters
The report still names the failure, but the last sentence can send an athlete to the wrong next step.

## Evidence
`src/fitdocs/connectors/errors.py:68,71,88`; `_instance_error` in `pull.py`. Rendered through `run_pull` by the task 3.3 and 3.5 reviewers, for example: "Garmin refused the activity download (HTTP 403). Garmin's terms let it restrict access; check the key's status on Garmin Connect. Check the credentials and run `fitdocs connect garmin` again."

## How to pick it up
Decide whether a connector can state its own next step in place of the framework's, for example an optional field on `AuthFailure`. Other connectors' wording is pinned by their tests, so keep their output unless changed on purpose.
