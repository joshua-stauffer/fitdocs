---
id: 2026-09-19-prompts-print-swallows-y-n-markup
title: load/prompts.py prints prompt text without markup=False, so rich swallows a `[y/N]` options tag
status: open
importance: low
importance_why: Latent: both current callers pass default=True, whose `[Y/n]` survives; any default=False confirm would hide its options.
effort: S
kind: bug
area: athlete-benchmarks, src/fitdocs/load/prompts.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (6.2 soft-wrap fix reviewer)
pinned_at: b29bde8
resume_command: "do: add markup=False (and highlight=False) to every self._console.print in src/fitdocs/load/prompts.py and pin one default=False confirm's rendered options"
context:
  - src/fitdocs/load/prompts.py
  - tests/load/
blocked_by: []
---

## What
`Console.print('Continue? [y/N] ...')` renders `Continue?  ...` because rich parses `[y/N]` as a style tag; `[Y/n]` starts with an uppercase letter and survives. Nine prints in prompts.py, none with markup=False.

## Why it matters
A user asked a yes/no question would not see the options; the default would silently apply.

## Evidence
Verified by the 6.2 soft-wrap fix reviewer with a one-line Console probe (2026-09-19); `grep -n _console.print src/fitdocs/load/prompts.py`.

## How to pick it up
Nine one-word edits plus one test with a default=False confirm. Done when the rendered prompt contains `[y/N]`.
