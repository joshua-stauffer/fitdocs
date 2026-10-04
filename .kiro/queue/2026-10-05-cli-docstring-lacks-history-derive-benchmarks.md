---
id: 2026-10-05-cli-docstring-lacks-history-derive-benchmarks
title: cli.py module docstring has no usage entries for the registered history and derive-benchmarks commands
status: open
importance: low
importance_why: The docstring is the command reference agents read first; two registered commands are missing from it while Phase 10 adds two more entries.
effort: S
kind: docs
area: src/fitdocs/cli.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-query spec writer)
pinned_at: 19fc92e
resume_command: "do: under the change ritual, add usage bullets for `fitdocs history` and `fitdocs derive-benchmarks` to cli.py's module docstring in the style of the existing bullets, checking any test that pins the docstring's command list or count"
context:
  - src/fitdocs/cli.py
  - tests/test_cli_skill.py
blocked_by: []
---

## What
The module docstring of `src/fitdocs/cli.py` (lines 1-60 at 19fc92e) lists
usage bullets for sync, regen, load, check, plan, plugins, skill and connect,
and mentions `history` only inside the plan bullet's chaining note (:31). The
`history` command (`cli.py:699`) and `derive-benchmarks` (`cli.py:1310`) have
no usage entry. analytics-index and analytics-query add bullets for `index`
and `query`.

## Why it matters
The docstring claims "Eleven commands are registered" and is the in-code
command reference; partial lists drift further with each phase.

## Evidence
- `head -60 src/fitdocs/cli.py` at 19fc92e: no `fitdocs history` or `fitdocs derive-benchmarks` bullet.

## How to pick it up
1. Land after or alongside Phase 10's cli.py edits to avoid a conflict (append-only list; keep both on rebase).
2. Add the two bullets with their requirement references.
