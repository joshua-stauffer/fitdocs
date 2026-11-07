---
id: 2026-11-07-post-template-check-shows-nothing-for-index-behind
title: Show values in check for a page the index does not hold as it is now
status: open
importance: low
importance_why: Right after emptying a region, check PAGE shows no values, although Req 9.6 reads as if it should show them with a flag.
effort: S
kind: inconsistency
area: post-templates, src/fitdocs/post_template/engine.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-post-template-check-shows-nothing-for-index-behind.md] Rule whether check PAGE resolves values for an INDEX_BEHIND page"
context:
  - src/fitdocs/post_template/engine.py
  - .kiro/specs/post-templates/requirements.md
  - tests/post_template/test_check_refill.py
blocked_by: []
---

## What
`check PAGE` on an INDEX_BEHIND page gives no variables and no post; `tests/post_template/test_check_refill.py` pins `variables == ()`.

## Why it matters
The most common check after an edit is uninformative until the user runs `fitdocs index`.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. Req 9.6 says "the values shown may be out of date", which suggests values are shown.

## How to pick it up
1. Ask the maintainer how to read 9.4/9.6.
2. If values should show, resolve them in check with the flag kept, and update the test.
