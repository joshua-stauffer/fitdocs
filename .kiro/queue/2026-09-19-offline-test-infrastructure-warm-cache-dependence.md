---
id: 2026-09-19-offline-test-infrastructure-warm-cache-dependence
title: Subprocess tests that build or install go online on a cold uv cache; there is no project-wide network guard for subprocess tests
status: open
importance: medium
importance_why: CI's cache is uv-sync-only, so several tests pass only via an online warm step; nothing detects a test that silently goes online.
effort: M
kind: chore
area: tests/, .github/workflows/ci.yml
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: add a shared tests/ helper implementing the try-offline -> warm-online-once -> retry-offline shape used by tests/test_packaging.py and tests/test_preserved_guarantees.py, consider a CI pre-warm step (`uv tool install --from` of the built wheel once) so the suite itself runs fully offline, and evaluate a session-level socket guard for subprocess-based tests"
context:
  - tests/test_packaging.py
  - tests/test_preserved_guarantees.py
  - tests/test_release_workflow.py
  - .github/workflows/ci.yml
blocked_by: []
---

## What
Three test files now carry private copies of the offline/warm/retry pattern. `uv build` re-fetches hatchling's index when the cache is stale; `uv tool install --offline` fails against a uv-sync-only cache.

## Why it matters
Task 7.2's observable 'the whole run stays offline' holds on a warm cache only; a regression that adds runtime network access inside a subprocess would not trip the in-process `_no_socket` guard.

## Evidence
Implementation Notes 6.4, 7.1, 7.2; agent-log WARN 2026-09-19 (uv-sync-only CI cache).

## How to pick it up
Extract the helper first (pure refactor, three call sites), then the CI pre-warm, then the guard. Done when `UV_OFFLINE=1 uv run --offline pytest -q` passes on a cache warmed by one documented command.
