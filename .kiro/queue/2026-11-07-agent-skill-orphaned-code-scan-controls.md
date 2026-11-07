---
id: 2026-11-07-agent-skill-orphaned-code-scan-controls
title: Remove or re-home the agent-skill code-scan positive controls
status: open
importance: low
importance_why: Two positive-control tests now guard a scanner with no real consumer, and one reads skill text (Req 14.8).
effort: S
kind: chore
area: tests/test_agent_skill.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: delete or re-home test_code_scan_flags_a_stray_word_in_a_span_or_prose and test_code_scan_allows_only_the_pinned_constants_and_ignores_placeholders in tests/test_agent_skill.py [queue: .kiro/queue/2026-11-07-agent-skill-orphaned-code-scan-controls.md]"
context:
  - tests/test_agent_skill.py
  - .kiro/specs/post-templates/tasks.md
blocked_by: []
---

## What
post-templates 6.2 deleted `test_every_code_the_publishing_section_names_is_a_vocabulary_value`, a doc-binding test. Its scanner helpers (`_unexplained_words`, `_span_words`, `_code_like_tokens`, `_PUBLISHING_ALLOWED_WORDS`) are now used only by the two positive controls.

## Why it matters
Dead test machinery, and one of the two still reads documentation.

## Evidence
Reported by the 6.2 reviewer; see tests/test_agent_skill.py around 2220, 2244 and 2250.

## How to pick it up
1. Confirm no other caller.
2. Delete the helpers and both controls, or keep them only if a code test needs them.
