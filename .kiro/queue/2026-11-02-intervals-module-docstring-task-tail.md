---
id: 2026-11-02-intervals-module-docstring-task-tail
title: intervals.py module docstring carries a stale task-number tail
status: open
importance: low
importance_why: Cosmetic: the docstring cites intervals-connector task numbers that read as this module's and says nothing of the publish half.
effort: XS
kind: docs
area: src/fitdocs/connectors/intervals.py
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-impl intervals-publish [queue: .kiro/queue/2026-11-02-intervals-module-docstring-task-tail.md] Drop task numbers from the intervals module docstring"
context:
  - src/fitdocs/connectors/intervals.py
blocked_by: []
---

## What
The module docstring's last paragraph says 'Task 3.1 declares ... task 3.4 implements the file download' (intervals-connector's numbering).

## Why it matters
Confusing next to intervals-publish's own task numbers; spec task numbers do not belong in code docstrings.

## Evidence
src/fitdocs/connectors/intervals.py ~15-18.

## How to pick it up
Replace the task-number sentence with a description of what the module does (pull, wellness, publish).
