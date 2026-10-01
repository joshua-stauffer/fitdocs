---
id: 2026-10-01-sdist-forbidden-prefixes-omit-website
title: "test_packaging's sdist forbidden-prefix list does not include `website/`, so a leak of the site tree into the sdist goes unseen"
status: open
importance: low
importance_why: "Req docs-site 8.3 holds today (verified by a real base-vs-head build) but is only preserved, not pinned."
effort: S
kind: gap
area: distribution, tests/test_packaging.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "do: see .kiro/queue/2026-10-01-sdist-forbidden-prefixes-omit-website.md -- test_packaging's sdist forbidden-prefix list does not include `website/`, so a leak of the site tree"
context:
  - tests/test_packaging.py
  - pyproject.toml
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What
docs-site added a `website/` tree. `tests/test_packaging.py` forbids `tests/ .kiro/ docs/ scripts/ release/` in the sdist, but not `website/`.

## Why it matters
Adding `website` to `[tool.hatch.build.targets.sdist].only-include` would ship the site sources in the sdist with every test green.

## Evidence
- `tests/test_packaging.py:389` `forbidden_prefixes = ("tests/", ".kiro/", "docs/", "scripts/", "release/")` (pinned at ba76d03).
- Validation reviewer probe: adding `"website"` to sdist only-include survived test_release_artifacts, test_packaging, test_preserved_guarantees, test_determinism, test_repo_wiring (259 passed). Not re-run by the controller.

## How to pick it up
1. Add `"website/"` to `forbidden_prefixes` in `tests/test_packaging.py` (or pin exact member sets).
2. Mutate `only-include` to include `website` and confirm red; restore.
