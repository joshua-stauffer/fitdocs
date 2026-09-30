---
id: 2026-09-30-docs-site-llms-text-fields-with-newlines-or-brackets
title: A docs-site title, description or summary containing a newline, `]` or `)` breaks the llms.txt structure
status: open
importance: low
importance_why: A malformed llms.txt entry misleads the LLM clients the index exists for; the loader accepts such values today.
effort: S
kind: gap
area: docs-site, scripts/sitebuild/content.py, scripts/sitebuild/outline.py
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "/kiro-spec-design docs-site [queue: .kiro/queue/2026-09-30-docs-site-llms-text-fields-with-newlines-or-brackets.md] Refuse or escape newline/bracket characters in llms text fields"
context:
  - .kiro/specs/docs-site/design.md
  - scripts/sitebuild/content.py
  - scripts/sitebuild/outline.py
  - tests/sitebuild/test_outline.py
blocked_by: []
---

## What
`content._text_field` accepts any non-blank string, so a frontmatter `title` or `description` can contain a newline, `]` or `)`. `outline.render_llms` then emits a broken `- [title](url): description` item, and `render_llms_full` a split `# title` heading. A multi-line `site_description` is only partly blockquoted. A body whose first line is whitespace-only keeps a visually blank line in llms-full.

## Why it matters
llms.txt is a machine-read index; a split list item or link drops or corrupts an entry.

## Evidence
- `load_content` on `title: "Home\rPage"` returns no problems; `render_llms_full` gives `# Home\nPage`.
- tests/sitebuild/test_outline.py pins today's split output by exact literal (`- [B\nC](...)`, `# B\nC`), so a fix updates those literals.

## How to pick it up
1. Decide: refuse such values in `_validate` (a Problem naming file and key) or escape them in outline.
2. Implement, update the test_outline.py literals, add a content test.
