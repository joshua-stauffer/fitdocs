---
id: 2026-10-01-docs-site-internal-import-direction-unenforced
title: "No test enforces scripts.sitebuild's internal import direction (e.g. model must not import pipeline)"
status: open
importance: low
importance_why: "Current code follows the design; a reverse import would pass silently."
effort: S
kind: gap
area: docs-site, tests/sitebuild/test_repo_wiring.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-internal-import-direction-unenforced.md] No test enforces scripts.sitebuild's internal import direction (e.g. model must not import"
context:
  - tests/sitebuild/test_repo_wiring.py
  - .kiro/specs/docs-site/design.md
blocked_by: []
---

## What
The import guard in test_repo_wiring.py accepts any `scripts.sitebuild.*` import from any module. Design calls a reverse import a defect. check_site's import set is also unpinned.

## Why it matters
Layering erodes without a red test.

## Evidence
- `tests/sitebuild/test_repo_wiring.py` `test_build_logic_imports_only_the_standard_library_yaml_and_the_package` (pinned at ba76d03). Reported by the design-validation reviewer.

## How to pick it up
1. Encode design § Architecture's allowed edges as a table and assert each module's `scripts.sitebuild` imports are a subset.
2. Mutate: add `from scripts.sitebuild import pipeline` to model.py, confirm red.
