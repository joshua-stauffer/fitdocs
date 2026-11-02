---
id: 2026-11-02-strava-publish-relay-mypy-needs-postgres-extra-locally
title: "Running mypy on the relay locally gives 26 import errors unless the postgres extra is synced"
status: open
importance: low
importance_why: "A recipe gap that sends a fresh session down a false trail."
effort: S
kind: docs
area: "relay/pyproject.toml, .kiro/steering/tech.md"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 1.3 review"
pinned_at: 964cc419
resume_command: "do: state `uv sync --directory relay --extra postgres` in the relay local-validation recipe (tech.md or relay/README.md) (read .kiro/queue/2026-11-02-strava-publish-relay-mypy-needs-postgres-extra-locally.md first)"
context:
  - .kiro/steering/tech.md
  - relay/README.md
  - relay/pyproject.toml
blocked_by: []
---

## What
Local relay mypy reports 26 import errors without the postgres extra; CI installs it.

## Why it matters
Wasted debugging time.

## Evidence
Reported by reviewer subagent (task 1.3), unverified in this run.

## How to pick it up
Reproduce with a clean venv, then add the one-line recipe where the relay validation commands are listed.
