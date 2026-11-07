---
id: 2026-11-07-publish-values-test-copies-name-grammar
title: Use is_placeholder_name in tests/publish/test_values.py instead of a copied regex
status: open
importance: low
importance_why: A third copy of the placeholder-name grammar can drift silently.
effort: S
kind: chore
area: publish-core, tests/publish/test_values.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: replace the inline placeholder-name regex at tests/publish/test_values.py:62 with publish.template.is_placeholder_name [queue: .kiro/queue/2026-11-07-publish-values-test-copies-name-grammar.md]"
context:
  - tests/publish/test_values.py
  - src/fitdocs/publish/template.py
blocked_by: []
---

## What
`tests/publish/test_values.py:62` asserts `re.fullmatch(r"[a-z][a-z0-9_]*", name)` rather than calling `is_placeholder_name`, which post-templates 1.3 exported.

## Why it matters
A grammar change would leave this test asserting the old rule.

## Evidence
Reported by the 1.3 reviewer subagent; the line reference is from its grep.

## How to pick it up
1. Swap in the function.
2. Run tests/publish.
