---
id: 2026-10-01-docs-yml-stale-env-comment-and-trigger-paths
title: "docs.yml: the workflow `env` comment talks about typer `--help`, and the trigger paths omit files the site tests import"
status: open
importance: low
importance_why: "Misleading comment; a change to conftest.py or the __init__ files skips the generator-backed site tests."
effort: S
kind: chore
area: docs-site, .github/workflows/docs.yml
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-yml-stale-env-comment-and-trigger-paths.md] docs.yml: the workflow `env` comment talks about typer `--help`, and the trigger paths omi"
context:
  - .github/workflows/docs.yml
  - tests/test_docs_workflow.py
blocked_by: []
---

## What
The `env:` comment was copied from ci.yml (typer/rich `--help` styling); in docs.yml the real reason is Zensical's always-on ANSI colour. The `paths` filter omits `conftest.py`, `tests/conftest.py`, `scripts/__init__.py` and `tests/__init__.py`.

## Why it matters
A maintainer reading the comment draws the wrong reason; a conftest change runs CI (without the generator) but not docs.yml (with it).

## Evidence
- `.github/workflows/docs.yml:36-39` comment; `on.push.paths` list (pinned at ba76d03).
- Reported by the design-validation reviewer; comment confirmed by the controller, path list confirmed by grep.

## How to pick it up
1. Rewrite the comment to name Zensical's ANSI output.
2. Add the four paths to both push and pull_request lists (the YAML anchor keeps them equal).
3. Update `tests/test_docs_workflow.py` path pins; run `uvx --from actionlint-py actionlint .github/workflows/docs.yml`.
