---
id: 2026-10-01-docs-site-duplicated-helpers-and-path-literals
title: "scripts/sitebuild duplicates an ancestry helper and repeats website/ path literals"
status: open
importance: low
importance_why: "Hygiene; a moved directory must be edited in several places."
effort: S
kind: chore
area: docs-site, scripts/build_site.py, scripts/sitebuild/pipeline.py, scripts/sitebuild/preview.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-duplicated-helpers-and-path-literals.md] scripts/sitebuild duplicates an ancestry helper and repeats website/ path literals"
context:
  - scripts/sitebuild/pipeline.py
  - scripts/sitebuild/preview.py
  - scripts/build_site.py
blocked_by: []
---

## What
`pipeline._index_of` and `build_site._same_or_ancestor` both decide ancestry by file identity. `"website"/"assets"` and `"website"/"overrides"` appear in pipeline.py and preview.py; `"website"/"content"` in content.py. Only TEMPLATE_PATH is shared.

## Why it matters
Drift risk between build and preview if a path changes.

## Evidence
- `scripts/sitebuild/pipeline.py:93`, `:137-138`; `scripts/sitebuild/preview.py:82-83`; `scripts/build_site.py:147` (pinned at ba76d03).

## How to pick it up
1. Hoist the website/ paths to constants (model.py or config.py per the allowed import direction).
2. Have build_site reuse pipeline's ancestry helper.
3. Full `tests/sitebuild` green.
