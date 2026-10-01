---
id: 2026-10-01-docs-site-website-doc-anchor-contrast-unpinned
title: "test_website_doc does not pin the GitHub-slug contrast clause nor forbid the retired 'slugged the way GitHub slugs it' sentence"
status: open
importance: low
importance_why: "Re-adding the false sentence the 6.1 review removed would stay green."
effort: S
kind: gap
area: docs-site, tests/sitebuild/test_website_doc.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-website-doc-anchor-contrast-unpinned.md] test_website_doc does not pin the GitHub-slug contrast clause nor forbid the retired 'slug"
context:
  - tests/sitebuild/test_website_doc.py
  - docs/website.md
blocked_by: []
---

## What
After 6.1 round 4 the anchor rule is pinned, but the contrast example `where GitHub would give #foo--bar` and the absence of the retired false sentence are not.

## Why it matters
A future edit can reintroduce the exact falsehood review spent a round removing.

## Evidence
- 6.1 round-4 reviewer mutations N3 (contrast changed) and N4 (retired sentence re-added) both survived (pinned at ba76d03).

## How to pick it up
1. Add `assert "slugged the way GitHub slugs it" not in text` (as test_exit_two_scope does for its retired sentence) and pin the contrast clause.
2. Re-run N3/N4 red.
