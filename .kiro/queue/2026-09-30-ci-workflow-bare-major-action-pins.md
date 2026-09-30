---
id: 2026-09-30-ci-workflow-bare-major-action-pins
title: ci.yml pins actions to bare majors while docs.yml requires exact tags
status: open
importance: low
importance_why: Two pin policies in one repo; bare majors float.
effort: S
kind: inconsistency
area: distribution, .github/workflows/ci.yml
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "do: pin ci.yml actions to exact tags and tighten tests/test_ci_workflow.py's pin regex"
context:
  - .github/workflows/ci.yml
  - tests/test_ci_workflow.py
blocked_by: []
---

## What
`.github/workflows/ci.yml` uses `actions/checkout@v4` and `actions/upload-artifact@v4`; docs-site 10.8 requires exact `vX.Y.Z` or a SHA in docs.yml. tests/test_ci_workflow.py docstring (g) allows `@v\d+`.

## How to pick it up
Pin ci.yml to exact tags (verify with `gh api repos/<o>/<r>/git/ref/tags/<t>`) and tighten test_ci_workflow.py's pin regex.
