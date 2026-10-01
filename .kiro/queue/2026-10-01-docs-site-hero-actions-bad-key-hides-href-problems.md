---
id: 2026-10-01-docs-site-hero-actions-bad-key-hides-href-problems
title: "A `hero_actions` entry with a bad key hides the href problems of the other entries in the same run"
status: open
importance: low
importance_why: "Partial miss of Req 2.9 (every violation in one run); costs the author one extra build round."
effort: S
kind: bug
area: docs-site, scripts/sitebuild/content.py, scripts/sitebuild/links.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-hero-actions-bad-key-hides-href-problems.md] A `hero_actions` entry with a bad key hides the href problems of the other entries in the "
context:
  - scripts/sitebuild/content.py
  - scripts/sitebuild/links.py
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What
When any `hero_actions` entry has a shape violation, `_hero_actions` returns None, so `Page.hero_actions` is empty and `check_links` never sees the other entries' hrefs. Their problems surface only after the shape is fixed.

## Why it matters
Requirement 2.9 says a build reports every violation it finds in one run; here a later run reveals new ones.

## Evidence
- `scripts/sitebuild/content.py:283` `def _hero_actions(` returns None at `:294` on a violation; `scripts/sitebuild/links.py:399` iterates `page.hero_actions or ()` (pinned at ba76d03).
- Reported by the 6.1 round-3 reviewer: probe with entries `guides/nope/`, `http://x.com` plus an extra key reports only `entry 3: key 'extra' ...`. Not re-run by the controller.

## How to pick it up
1. Read `_hero_actions` and the `check_links` hero branch.
2. Keep the well-formed entries' hrefs for link checking even when another entry is malformed (or report href problems from raw entries).
3. Add a test in `tests/sitebuild/test_links.py` or `test_pipeline.py` with one malformed entry and two bad hrefs, asserting all three problems in one run.
