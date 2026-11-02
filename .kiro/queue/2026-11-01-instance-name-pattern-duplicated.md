---
id: 2026-11-01-instance-name-pattern-duplicated
title: "The ledger's target-name pattern duplicates connectors.settings.INSTANCE_NAME_PATTERN"
status: open
importance: low
importance_why: Kept equal by a test, so drift fails loudly; the cost is the duplication itself.
effort: S
kind: chore
area: publish-core, src/fitdocs/publish/ledger.py, src/fitdocs/connectors/settings.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: move the instance-name pattern to a shared leaf (layout or contract) and import it from both ledger and connectors.settings [queue: .kiro/queue/2026-11-01-instance-name-pattern-duplicated.md]"
context:
  - src/fitdocs/publish/ledger.py
  - src/fitdocs/connectors/settings.py
blocked_by: []
---

## What
`_TARGET_RE` at `src/fitdocs/publish/ledger.py:41` duplicates
`connectors.settings.INSTANCE_NAME_PATTERN`, because the ledger may not import
connectors. A test pins them equal.

## Why it matters
Two copies of one grammar; the pinning test is the only thing keeping them in step.

## Evidence
`src/fitdocs/publish/ledger.py:41`; the equality test (find with
`grep -rn INSTANCE_NAME_PATTERN tests`).

## How to pick it up
Move the pattern to a leaf both may import (layout or contract), switch both
users, keep the equality test or replace it with an identity check.
