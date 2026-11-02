---
id: 2026-11-01-relay-ruff-config-hand-copy
title: 'The relay''s ruff settings are a hand copy of the root''s, and two ruff versions resolve'
status: open
importance: low
importance_why: Lint verdicts can silently differ between the two projects; nothing fails when the copies drift.
effort: S
kind: chore
area: relay/pyproject.toml, pyproject.toml
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 1.3 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-ruff-config-hand-copy.md] Pin the relay's ruff settings and version against the root's"
context:
  - relay/pyproject.toml
  - pyproject.toml
  - relay/uv.lock
  - uv.lock
blocked_by: []
---

## What
The relay is its own project with its own ruff run. Its `[tool.ruff]` table (target-version, lint select) was copied by hand from the root's, and no test checks that the two stay equal. The relay floor is `ruff>=0.9`, which resolves to a different version from the root's.

## Why it matters
The same source line can pass one project's lint and fail the other's. A rule added to one table is silently absent from the other.

## Evidence
- `relay/pyproject.toml:37-42`: `target-version = "py311"`, `select = ["E", "F", "I", "UP", "B", "SIM"]`.
- `pyproject.toml:85-94`: the same values.
- `relay/uv.lock:539-540`: ruff 0.17.3. `uv.lock:663-664`: ruff 0.15.21.

## How to pick it up
1. Decide whether a test should pin the two tables equal, or whether the relay should pin its ruff to the root's version.
2. Add the cheaper of the two (a test that parses both pyproject files is a few lines).
3. Done when changing either `select` alone turns a test red.
