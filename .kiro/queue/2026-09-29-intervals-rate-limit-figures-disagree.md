---
id: 2026-09-29-intervals-rate-limit-figures-disagree
title: The intervals-connector brief and research quote different intervals.icu rate limits; neither is established as current
status: open
importance: low
importance_why: The design depends on neither figure (it retries on 429 and reports), but the connectors docs will advise backfilling "under the service's rate limits", and a wrong figure in the brief will be copied.
effort: S
kind: chore
area: intervals-connector, .kiro/specs/intervals-connector/brief.md, .kiro/specs/intervals-connector/research.md
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, intervals-connector writer)
pinned_at: f500dc1
resume_command: "do: establish intervals.icu's current API rate limits (the maintainer's live check, intervals-connector task 1.1, or intervals.icu's own API documentation), then correct the Rate limits bullet in .kiro/specs/intervals-connector/brief.md and the matching finding in research.md to one figure set with its source and read date, under the change ritual for spec docs"
context:
  - .kiro/specs/intervals-connector/brief.md
  - .kiro/specs/intervals-connector/research.md
  - .kiro/specs/intervals-connector/design.md
blocked_by: []
---

## What
The brief says "30 requests/s over 1 s and 132 per 10 s, per the developer's
forum post", plus a secondary report of 5,000 a day. research.md quotes
intervals.icu's API-access forum thread instead: 5000 requests per day and
2500 per rolling 15-minute window for API-key callers, plus 10 calls per
second per IP address, and notes the disagreement.

## Why it matters
Low. Nothing in the design paces requests against a figure. The brief is
the document future sessions read first, so it should not carry a figure
the research contradicts.

## Evidence
- `.kiro/specs/intervals-connector/brief.md:43-45` -- the brief's figures.
- `.kiro/specs/intervals-connector/research.md:81-85` -- the thread's
  figures and "The figures disagree and may change; the design depends on
  neither."
- `.kiro/specs/intervals-connector/design.md:53` -- "Client-side pacing below
  the service's rate limits" is a non-goal; `:772` the docs' backfill advice.
- intervals-connector task 1.1 (~:107-124) does not currently ask the live
  check to record rate limits.

## How to pick it up
1. Read the two passages above.
2. Get the current figures from intervals.icu (response headers seen during
   task 1.1, or its published API documentation) -- never from a third-party
   summary.
3. Edit the brief and research to agree; done when one figure set with a
   source and date appears in both.
