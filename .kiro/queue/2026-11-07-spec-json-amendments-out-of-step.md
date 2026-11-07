---
id: 2026-11-07-spec-json-amendments-out-of-step
title: Bring spec.json amendments arrays in step with requirements.md headings
status: open
importance: low
importance_why: Tools reading spec.json miss amendments that requirements.md records.
effort: S
kind: chore
area: .kiro/specs/*/spec.json
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: reconcile the amendments arrays in .kiro/specs/*/spec.json with the Amendment headings in each requirements.md [queue: .kiro/queue/2026-11-07-spec-json-amendments-out-of-step.md]"
context:
  - .kiro/specs/wiki-contract/spec.json
  - .kiro/specs/analytics-index/spec.json
  - .kiro/specs/publish-core/spec.json
blocked_by: []
---

## What
wiki-contract/spec.json has no entry for Amendment 16 (and now 17). analytics-index/spec.json has none for Amendment 2 (and now 4). publish-core/spec.json has no `amendments` key though requirements.md now has Amendment 1. analytics-query gained Amendment 2.

## Why it matters
Status tooling and humans reading spec.json see stale amendment lists.

## Evidence
Reported by the 6.3 reviewer; the post-templates amendments landed at b510d4f1.

## How to pick it up
1. Decide whether spec.json `amendments` is still a maintained field.
2. If so, add the missing entries; if not, remove the field everywhere.
