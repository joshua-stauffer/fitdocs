---
id: 2026-09-30-docs-site-relative-links-to-llms-txt-refused
title: A relative content link to the generated llms.txt or llms-full.txt is refused by the docs-site link checker
status: open
importance: low
importance_why: A Working-with-LLMs page naturally links the index; today it must use the absolute https://fitdocs.ai/llms.txt URL.
effort: S
kind: gap
area: docs-site, scripts/sitebuild/links.py
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "/kiro-spec-design docs-site [queue: .kiro/queue/2026-09-30-docs-site-relative-links-to-llms-txt-refused.md] Accept relative links to the generated llms files"
context:
  - .kiro/specs/docs-site/design.md
  - scripts/sitebuild/links.py
  - tests/sitebuild/test_links.py
blocked_by: []
---

## What
`check_links` accepts only included assets and page URLs, so `[idx](../llms.txt)` on `llms/prompts.md` gives `link ../llms.txt is neither an included asset nor a page URL`, although both files are published at the site root.

## Evidence
docs-site 2.8 reviewer probe (2026-09-30). The maintainer's draft (checked 2026-09-30) uses no such relative link.

## How to pick it up
Treat `RESERVED_ROOT_NAMES` resolved at the site root as valid targets in `check_links`; amend design § LinkChecker; add a test.
