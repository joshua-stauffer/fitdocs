---
id: 2026-09-12-label-in-fixture-name-anti-pattern
title: Document a label-in-fixture-name anti-pattern in change-protocol's Fixture Discrimination section
status: open
importance: low
importance_why: This exact pattern cost two rejection rounds on task 4.2 and is not yet named anywhere in steering, so it can recur unrecognized.
effort: S
kind: docs
area: .kiro/steering/change-protocol.md
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: add a named row to change-protocol.md § Fixture Discrimination for the label-in-fixture-name anti-pattern"
context:
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

A fixture NAME containing the label an assertion searches for, in a
message that embeds the document path (`b_undecodable.md` combined with
`assert "undecodable" in reason`), satisfied the assertion under a
relabelled production string. This anti-pattern is not currently named in
`change-protocol.md`'s Fixture Discrimination section.

## Why it matters

It cost two rejection rounds on task 4.2 before being caught. A named row
in the steering doc lets a future reviewer recognize it on sight instead of
re-deriving it.

## Evidence

- (4.2 r2 reviewer) "steering candidate: 'label-in-fixture-name'
  anti-pattern -- a fixture NAME containing the label an assertion searches
  for in a message that embeds the document path (e.g. `b_undecodable.md`
  and `assert 'undecodable' in reason`). Add a row to change-protocol §
  Named anti-patterns. steering, S."

## How to pick it up

1. Read `.kiro/steering/change-protocol.md` § Fixture Discrimination
   (referred to as "Named anti-patterns" by the reviewer) for the existing
   table format.
2. Add a row for "label-in-fixture-name": a fixture whose name contains the
   string label an assertion searches for, where the assertion message
   embeds the fixture's path/name, can pass even after the production
   string is relabelled — name discrimination independent of the fixture's
   own filename.
3. Cite the 4.2 task's `b_undecodable.md` / `assert "undecodable" in
   reason` example as the concrete instance.
</content>
