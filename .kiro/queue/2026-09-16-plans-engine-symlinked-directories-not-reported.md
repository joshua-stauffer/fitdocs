---
id: 2026-09-16-plans-engine-symlinked-directories-not-reported
title: The plan engine silently skips a symlink-to-directory in two places the design says to report
status: open
importance: low
importance_why: Untouched in both cases (no data risk), but Req 7.9 and the design say "reported"; a later test could pin the silent behaviour by accident.
effort: S
kind: bug
area: training-blocks, src/fitdocs/plans/engine.py
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks 4.2 (reviewer FOLLOW_UPS)
pinned_at: 68fe42e
resume_command: "do: in src/fitdocs/plans/engine.py make _discover report a symlink-to-directory named *.toml as an invalid source (one problem) and make the stale scan list a symlink-to-directory child of the pages dir in `foreign` instead of skipping it; pin both in tests/plans/test_engine.py"
context:
  - src/fitdocs/plans/engine.py
  - tests/plans/test_engine.py
  - .kiro/specs/training-blocks/design.md
  - .kiro/specs/training-blocks/requirements.md
blocked_by: []
---

## What
1. `_discover` filters `entry.suffix == PLAN_SOURCE_SUFFIX and not entry.is_dir()`
   before its symlink check; `is_dir()` follows links, so a symlink named
   `x.toml` pointing at a directory is excluded silently rather than reported
   `invalid` with one problem (design PlanEngine: "symlinks refused as foreign
   sources, reported as invalid").
2. The stale scan over a block's pages directory tests `child.is_dir()`
   before `is_symlink()`, so a symlink-to-directory child is skipped silently
   instead of being left untouched AND listed in `BlockOutcome.foreign`
   (Req 7.9: "leave it untouched and report it").

## Why it matters
Both files are left alone (safe). But the report is the athlete's only view
of what the run declined to touch, and a symlink in an owned directory is
exactly the kind of foreign occupant the design wants named.

## Evidence
- `src/fitdocs/plans/engine.py:290` (discover filter), `:391` (stale scan
  `child.is_dir()` first). 4.2 reviewer probes (round 1 FOLLOW_UPS) --
  behaviour reported, not independently reproduced here.

## How to pick it up
1. Read `_discover`, `_is_foreign_occupant` and the stale-removal loop in
   `_render_and_write`.
2. Reorder the checks (`is_symlink()` first), add the report entries, and add
   two `tmp_path` tests with a symlinked directory in each position asserting
   the report names it and the target is untouched.
3. Done when `uv run pytest tests/plans/test_engine.py tests/test_confinement.py -q`
   is green.
