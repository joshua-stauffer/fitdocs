---
id: 2026-09-17-inbox-drain-leaves-source-fit-in-inbox
title: Draining the inbox leaves the ingested .fit in inbox/ (fit-archive holds the copy) -- intended?
status: open
importance: low
importance_why: If intended nothing to do; if not, every drain re-ingests the same file until the athlete deletes it.
effort: S
kind: research
area: inbox spec, src/fitdocs/sync.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 3.2 round-3 review)
pinned_at: fbba78b
resume_command: "do: read the inbox spec's requirement on what happens to a drained file, confirm against src/fitdocs/sync.py, and close this item as intended or turn it into a bug"
context:
  - src/fitdocs/sync.py
  - .kiro/specs/inbox
blocked_by: []
---

## Evidence
- 3.2 round-3 review scratch run: `inbox/run.fit` still present alongside `fit-archive/<sha>.fit` after `fitdocs sync --out <root> --no-prompt` with `settle_seconds = 0`.
