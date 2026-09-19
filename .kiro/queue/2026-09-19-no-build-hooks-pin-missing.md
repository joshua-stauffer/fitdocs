---
id: 2026-09-19-no-build-hooks-pin-missing
title: Nothing pins that pyproject.toml declares no build hooks or code generation (Req 10.2 'no build step alters behaviour')
status: open
importance: low
importance_why: The design claim rests on reading the manifest; a `[tool.hatch.build.hooks.*]` table added later would go unnoticed by tests.
effort: S
kind: gap
area: distribution, pyproject.toml, tests/test_preserved_guarantees.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: add a test asserting pyproject.toml has no [tool.hatch.build.hooks*] tables and no `build-system.backend-path`, with a mutation that adds an empty hooks table"
context:
  - pyproject.toml
  - tests/test_preserved_guarantees.py
  - .kiro/specs/distribution/design.md
blocked_by: []
---

## What
Implementation Note 2.1 records the gap; 7.2 pinned reproducibility and goldens but not the absence of hooks.

## Why it matters
A build hook is exactly the mechanism that lets the published artifact differ from the tested revision.

## Evidence
Implementation Note 2.1; validation coverage report finding 4 (2026-09-19).

## How to pick it up
One tomllib read and two assertions in tests/test_preserved_guarantees.py. Done when adding `[tool.hatch.build.hooks.custom]` reds it.
