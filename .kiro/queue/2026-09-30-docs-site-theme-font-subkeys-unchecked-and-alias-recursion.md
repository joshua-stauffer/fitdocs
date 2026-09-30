---
id: 2026-09-30-docs-site-theme-font-subkeys-unchecked-and-alias-recursion
title: docs-site config allowlist does not check `theme.font` sub-keys, and dump_config recurses forever on a self-referencing template
status: open
importance: low
importance_why: A font sub-key typo is silently ignored by Zensical; a pathological template crashes the build with RecursionError instead of a Problem.
effort: S
kind: gap
area: docs-site, scripts/sitebuild/config.py
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "do: extend scripts/sitebuild/config.py check_config to theme.font sub-keys and refuse recursive templates in load_template; add tests"
context:
  - scripts/sitebuild/config.py
  - tests/sitebuild/test_config.py
blocked_by: []
---

## What
- `check_config` stops at theme keys, so any nested mapping under `theme.font` passes unchecked (config.py `_check_theme`).
- `dump_config` uses a SafeDumper with `ignore_aliases`, so a self-referencing template (`a: &x [*x]`) raises RecursionError.

## Evidence
Reviewer probes during docs-site 2.4 (2026-09-30).

## How to pick it up
Add a `theme.font` sub-key allowlist (text, code) and refuse recursive structures in `load_template`.
