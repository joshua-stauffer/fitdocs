---
id: 2026-10-18-check-does-not-validate-athlete-inputs
title: `fitdocs check` reports "No findings" for an athlete.toml that `load` and `regen` refuse with exit 2
status: open
importance: medium
importance_why: The audit command is where a user goes to find out why the tool refuses; today it is silent about the athlete inputs that make load/regen exit 2.
effort: S
kind: gap
area: src/fitdocs/audit.py, src/fitdocs/athlete.py, wiki-contract
created: 2026-10-18
surfaced_by: independent review of chore/q-athlete-nonfinite (queue-prerelease session)
pinned_at: 5e37ad3
resume_command: "do: decide whether fitdocs check should call athlete.load_athlete_inputs and emit ATHLETE_PROFILE_UNREADABLE (naming the key) for an athlete.toml that load/regen refuse; implement with a test [queue: .kiro/queue/2026-10-18-check-does-not-validate-athlete-inputs.md]"
context:
  - src/fitdocs/audit.py
  - src/fitdocs/athlete.py
  - .kiro/queue/closed/2026-10-05-athlete-threshold-accepts-nan-inf.md
blocked_by: []
---

## Evidence

With `ftp_watts = nan` (or a wrong-type `ftp_watts`) in athlete.toml: `fitdocs load` and `fitdocs
regen` exit 2 naming the key (since 5e37ad3); `fitdocs check` exits 0 with "No findings".
`audit.py` (~620-634) reads only `load_profile(...).benchmarks` and never calls
`load_athlete_inputs`, so this was already true for wrong-type values before 5e37ad3.

## Decision

Whether `check` should surface athlete-input errors (an existing ATHLETE_PROFILE_UNREADABLE finding
kind, or a new one). Product choice: `check` is the documented diagnostic for "why does fitdocs
refuse".
