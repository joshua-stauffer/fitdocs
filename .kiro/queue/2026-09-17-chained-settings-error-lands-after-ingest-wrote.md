---
id: 2026-09-17-chained-settings-error-lands-after-ingest-wrote
title: On a chained sync a malformed [history]/[load] table exits 2 after ingest and the load pass have written; sync/regen are now sensitive to [history]
status: open
importance: low
importance_why: Design-sanctioned ("nothing written" holds for the pass, not the command) but new athlete-facing behaviour worth a sentence in the ownership contract or README.
effort: S
kind: docs
area: plan-resolution, docs/ownership-contract.md, README.md
created: 2026-09-17
surfaced_by: /kiro-validate-impl plan-resolution (integration dimension)
pinned_at: fbba78b
resume_command: "do: add one sentence to docs/ownership-contract.md's sync bullet (and README's sync paragraph if it lists settings faults) that a malformed [history] or [load] table now ends sync/regen with the configuration exit after the document and load passes have run"
context:
  - docs/ownership-contract.md
  - README.md
  - src/fitdocs/cli.py
blocked_by: []
---

## Evidence
- Validation integration run: malformed `[history]` on a chained `sync` → ingest and load wrote, then exit 2 from `_run_plan_pass`.
