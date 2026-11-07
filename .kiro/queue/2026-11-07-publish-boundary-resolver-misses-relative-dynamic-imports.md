---
id: 2026-11-07-publish-boundary-resolver-misses-relative-dynamic-imports
title: Resolve relative dynamic imports in the publish boundary guard
status: open
importance: low
importance_why: The publish guard's forbidden-name layer misses `import_module('.x','pkg')` and `__import__` forms with fromlist or level.
effort: S
kind: gap
area: publish-core, tests/publish/test_boundary.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: make tests/publish/test_boundary.py _import_targets_of_tree resolve relative import_module and __import__ fromlist/level forms like tests/query/test_boundary._import_targets [queue: .kiro/queue/2026-11-07-publish-boundary-resolver-misses-relative-dynamic-imports.md]"
context:
  - tests/publish/test_boundary.py
  - tests/query/test_boundary.py
blocked_by: []
---

## What
`_import_targets_of_tree` (tests/publish/test_boundary.py, around 362-397) does not resolve relative `importlib.import_module('.x', 'pkg')` or `__import__` with fromlist/level. `tests/query/test_boundary._import_targets` does.

## Why it matters
A forbidden import written that way passes the forbidden-name scan; the equality import table softens this.

## Evidence
Reported by the 1.6 reviewer subagent, which probed the forms in scratch.

## How to pick it up
1. Reuse the query resolver, or union the two.
2. Add the forms to the guard's red list.
