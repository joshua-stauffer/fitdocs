---
id: 2026-09-30-docs-site-symlinks-in-repo-owned-website-dirs
title: Symlinks in website/assets or website/overrides are followed or skipped silently by the docs-site stager
status: open
importance: low
importance_why: Repo-owned source, so reviewed; but no guard refuses a tracked symlink under website/, unlike content symlinks.
effort: S
kind: gap
area: docs-site, scripts/sitebuild/stage.py
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "do: refuse symlinks and special files in scripts/sitebuild/stage.py _read_dir (or guard tracked website/ files); add tests"
context:
  - scripts/sitebuild/stage.py
  - tests/sitebuild/test_stage.py
blocked_by: []
---

## What
`stage._read_dir` uses `rglob` plus `is_file()`, which follows symlinked files and silently skips dangling links and special files in `website/assets` and `website/overrides`.

## Evidence
docs-site 3.2 mutations L20/L21 survive tests/sitebuild/test_stage.py (2026-09-30).

## How to pick it up
Refuse non-regular entries in `_read_dir` with a clear error, or add a repository guard that no tracked file under website/ is a symlink.
