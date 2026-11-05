---
id: 2026-11-05-garmin-docs-after-the-live-check
title: Add what the live check confirms to the Garmin docs
status: open
importance: low
importance_why: Setup is already documented; these details would ease a first key.
effort: S
kind: docs
area: garmin-connector, docs/connectors.md
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: After task 7.2, add to docs/connectors.md the facts the live check confirms about Garmin key creation"
context:
  - docs/connectors.md
  - .kiro/specs/garmin-connector/brief.md
  - .kiro/specs/garmin-connector/research.md
blocked_by: [garmin-connector]
---

## What
The Garmin section gives no menu path for creating a key and does not say Garmin allows one key at a time, because neither could be stated from the public material used.

## Why it matters
An athlete renewing a key may need to delete the old one first and has to discover that.

## Evidence
`.kiro/specs/garmin-connector/brief.md` records the one-key limit. The task 6.1 reviewer judged omitting the menu path correct on provenance (Req 14.1).

## How to pick it up
Record what the maintainer observes in `research.md`, then add it to the section, stating only what was observed.
