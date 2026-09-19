---
id: 2026-09-19-contributing-silent-on-fork-pr-secret-step
title: CONTRIBUTING.md does not say that fork pull requests fail the `gates` job at the secret-write step by design
status: open
importance: medium
importance_why: The first external contributor sees a red CI run they cannot fix and no document explains it.
effort: S
kind: docs
area: distribution, CONTRIBUTING.md, .github/workflows/ci.yml
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: add a short paragraph to CONTRIBUTING.md's quality-gates section stating that secrets are empty on fork PRs so the encumbered-content gate fails closed (`gate_not_run`) there, that the three gates before it are the contributor's signal, and that a maintainer re-runs the gate on a branch in the repository; pin the polarity phrase in tests/test_contributing_doc.py"
context:
  - CONTRIBUTING.md
  - .github/workflows/ci.yml
  - tests/test_contributing_doc.py
  - tests/test_ci_workflow.py
blocked_by: []
---

## What
ci.yml's comment block explains the fork behaviour; CONTRIBUTING.md's "The three quality gates" says CI runs the gates on every push and PR but nothing about the secret step.

## Why it matters
Contributors read CONTRIBUTING, not workflow comments. A red check with `gate_not_run` looks like a broken project.

## Evidence
Implementation Note 6.2; ci.yml comment ~lines 63-69; validation coverage report finding 8 (2026-09-19).

## How to pick it up
One paragraph plus one assertion. Done when tests/test_contributing_doc.py pins the sentence and `uv run pytest tests/test_contributing_doc.py -q` is green.
