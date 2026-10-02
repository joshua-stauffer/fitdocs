---
id: 2026-10-02-pull-auth-failure-and-settings-error-wording
title: fitdocs pull words an auth failure as "AuthFailure: HTTP 401 Check…" (no kind word, no separator), unlike fitdocs connect, and connector settings errors repeat the key name
status: open
importance: low
importance_why: Cosmetic, but it is user-facing error text; docs/connectors.md says the pull report "names the rejection", which holds only loosely.
effort: S
kind: inconsistency
area: connectors, src/fitdocs/connectors/pull.py, src/fitdocs/connectors/settings.py
created: 2026-10-02
surfaced_by: /kiro-validate-impl intervals-connector (integration validator, UPSTREAM to connectors)
pinned_at: 9d08482
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-pull-auth-failure-and-settings-error-wording.md] Align pull-time auth-failure wording with connect and stop doubling the key in settings errors"
context:
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/connect.py
  - src/fitdocs/connectors/errors.py
  - src/fitdocs/connectors/settings.py
  - docs/connectors.md
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
- **Pull-time auth failures.** `pull.py::_instance_error` renders an
  `AuthFailure` as `f"{type(exc).__name__}: {exc}"`, then appends the next step
  after a single space. An empty-bodied 401 therefore prints `AuthFailure:
  HTTP 401 Check the credentials and run ...`. It has no kind word (connect
  prints `rejected:`) and no separator before the next step.
- **Settings errors.** A connector settings error is wrapped with the
  framework's key prefix while the connector's own message also names the key,
  giving `... sources: sources must be ...`.

## Why it matters
The same failure reads differently from `fitdocs connect` and `fitdocs pull`,
and the doubled key looks like a bug. docs/connectors.md claims the report
names the rejection.

## Evidence
- `src/fitdocs/connectors/pull.py:254-257`: `detail = redactor.redact(f"{type(exc).__name__}: {exc}")`,
  then `detail = f"{detail} {step}"` for an `AuthFailure`.
- The CLI outputs quoted above were observed by the integration validator,
  which drove `fitdocs pull` and `fitdocs connect` with a scripted transport
  in a sandbox (reviewer subagent; outputs not re-run by the controller). The
  doubled `sources: sources` prefix comes from that run; the controller has
  not verified it.

## How to pick it up
1. Reproduce both with a FakeTransport CLI test (copy the sandbox pattern in
   `tests/connectors/test_intervals_pull.py`).
2. Render `AuthFailure` with its kind's word and a sentence separator,
   matching `connect.py`'s report. Fix the double prefix in the settings
   wrapper or in intervals' `_sources_error`, whichever owns it.
3. Re-pin the affected messages in tests/connectors and check docs/connectors.md.
