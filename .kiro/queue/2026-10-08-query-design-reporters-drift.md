---
id: 2026-10-08-query-design-reporters-drift
title: Align the analytics-query design with the inline CLI reporting
status: open
importance: low
importance_why: design.md names reporters that do not exist and omits three dependency edges; the drift misleads later readers.
effort: S
kind: docs
area: analytics-query, .kiro/specs/analytics-query/design.md
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: align the analytics-query design with the inline CLI reporting [queue: .kiro/queue/2026-10-08-query-design-reporters-drift.md]"
context:
  - .kiro/specs/analytics-query/design.md
  - src/fitdocs/cli.py
  - src/fitdocs/query/command.py
blocked_by: []
---

## What
design.md:357 and the traceability rows 3.2 and 9.2 (lines 477 and 511) name `_report_query_outcome` and `_query_notice`. Neither exists: reporting is inline in `query_command`. The mermaid graph also omits cli→sandbox, cli→statement and command→registry. `command.py` compares against the literal "computed" instead of the `ComputedState` member.

## Why it matters
Accepted architecture drift that nobody owns tends to compound.

## Evidence
Reported by the 2026-10-08 validation reviewer (notes N3, N5, N6). The design lines were verified by grep at the pinned commit.

## How to pick it up
Either extract the two reporters from `query_command` to match the design, or edit the design to describe the inline reporting. Add the three graph edges and replace the string literal with the enum member.
