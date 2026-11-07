---
id: 2026-11-07-post-template-control-characters-in-values
title: "Refuse control characters in post-template variable values"
status: open
importance: medium
importance_why: "A NUL or ESC from a variable reaches a published post title, while page values and the template title already refuse them."
effort: S
kind: gap
area: "post-templates, src/fitdocs/post_template/resolve.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-post-template-control-characters-in-values.md] Decide whether variable text values refuse control characters"
context:
  - src/fitdocs/post_template/resolve.py
  - src/fitdocs/publish/values.py
  - src/fitdocs/publish/compose.py
  - .kiro/specs/post-templates/requirements.md
blocked_by: []
---

## What
`to_text` in `post_template/resolve.py` refuses line breaks and comment markers in a text value, but passes other control characters (NUL, ESC, `\x1c`, tab). Page values (`publish.values._verbatim`) and the template title (Req 1.9, `has_control_character`) refuse them. Neither `compose_post` nor `read_post_region` checks again.

## Why it matters
A query returning `'a' || chr(0) || 'b'` fills `a\x00b` into a post title that publish then sends to a target.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. A real resolve of `SELECT 'a' || chr(0) || 'b'` gave `'a\x00b'`. See `src/fitdocs/publish/values.py:79-87` and `src/fitdocs/publish/compose.py:94`. Req 3.9 and the design's `str` row permit it as written.

## How to pick it up
1. Read Req 3.8/3.9 and design.md's `to_text` type table.
2. Decide with the maintainer whether to reuse `publish.values.has_control_character` in `to_text`.
3. If yes, amend Req 3.9 and add one refusal per control-character class in `tests/post_template/test_resolve_variable.py`.

## Open questions
Whether tab is allowed (the title refuses it; a description might not need to).
