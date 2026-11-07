---
id: 2026-11-07-post-template-landed-note-compares-region-not-landed-post
title: "Make refill's \"next publish will update\" note compare with the landed post"
status: open
importance: low
importance_why: "The note can promise an update that publish then reports as unchanged."
effort: S
kind: bug
area: "post-templates, src/fitdocs/post_template/model.py, docs/publishing.md"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-post-template-landed-note-compares-region-not-landed-post.md] Base the 10.7 landed-change note on the landed digest"
context:
  - src/fitdocs/post_template/model.py
  - src/fitdocs/post_template/engine.py
  - docs/publishing.md
blocked_by: []
---

## What
`FillReport.landed_changed` names FILLED/WOULD_FILL rows with a landed post whose region text changed. It compares with the old REGION text, not with the landed post's digest.

## Why it matters
After emptying a region and refilling it with the same text, the note says the next publish updates the activity, but publish says `unchanged`. docs/publishing.md (around line 551) repeats the claim.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. Seen in the /kiro-validate-impl end-to-end probe.

## How to pick it up
1. Compare the new post's digest with the ledger's landed digest (`publish.ledger`).
2. Amend Req 10.7's wording if needed.
