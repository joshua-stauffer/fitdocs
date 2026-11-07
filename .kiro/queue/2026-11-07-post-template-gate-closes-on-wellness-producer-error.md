---
id: 2026-11-07-post-template-gate-closes-on-wellness-producer-error
title: "Decide whether a derived.wellness index error should block post-template fills"
status: open
importance: low
importance_why: "A persistent wellness-series read error silently blocks every fill while `fitdocs index` reports success."
effort: S
kind: inconsistency
area: "post-templates, analytics-index, src/fitdocs/cli.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-post-template-gate-closes-on-wellness-producer-error.md] Decide whether non-fatal producer errors close the fill gate"
context:
  - src/fitdocs/cli.py
  - .kiro/specs/post-templates/requirements.md
  - .kiro/specs/analytics-index/requirements.md
blocked_by: []
---

## What
`cli._index_gate` closes on ANY producer error. `fitdocs index` treats a `derived.wellness` error as non-fatal and exits 0 (analytics-index Amendment 2).

## Why it matters
Fills stop with a one-line note, and the user has no reason to suspect the index.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. See the `index_command` exemption in `src/fitdocs/cli.py` (around 673-676) and the `_index_gate` producer_errors check. Req 6.4 as written requires the current behavior.

## How to pick it up
1. Ask the maintainer whether wellness producer errors should be exempt from the gate.
2. If so, amend Req 6.4 and exempt the same producers `index_command` exempts.
